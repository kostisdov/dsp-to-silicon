"""Figures and numbers for the article, in the palette of kostisdov.github.io.

    uv run python scripts/figures.py

Writes SVGs to figures/ and every quoted number to figures/results.json.
Resource counts are read from the Yosys reports in build/synth (run scripts/synth.sh first).
"""

import json
import pathlib
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from dsp2si.models import (CordicCfg, RsqrtCfg, errors, normalize_a, normalize_b, normalize_float,
                           rsqrt_tables, stimulus, FRAC, OUT_MAX, OUT_MIN)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

PAPER, INK, INK_SOFT = "#fbfaf8", "#221e17", "#5c554a"
ACCENT, ACCENT_DEEP, RULE, SAGE, STONE = "#c34a22", "#1e3d52", "#d8cfbc", "#6f8b6a", "#9a9285"
plt.rcParams.update({
    "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
    "font.family": "serif", "font.serif": ["Georgia", "Times New Roman", "DejaVu Serif"],
    "font.size": 12, "text.color": INK, "axes.edgecolor": RULE, "axes.labelcolor": INK_SOFT,
    "xtick.color": INK_SOFT, "ytick.color": INK_SOFT, "axes.linewidth": 0.8, "axes.grid": False,
    "svg.fonttype": "none", "legend.frameon": False,
})


def clean(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)


# ---------------------------------------------------------------- fig 1: the table

def fig_table(res):
    cfg = RsqrtCfg()
    u = np.linspace(0.25, 1, 4000, endpoint=False)
    exact = 1 / np.sqrt(u)

    # a coarse table, to make the segments visible
    k = np.arange(2, 9)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    a1.plot(u, exact, color=INK, lw=1.2, label=r"$1/\sqrt{u}$")
    a1.plot(k / 8, 1 / np.sqrt(k / 8), "o-", color=ACCENT, ms=4, lw=1, label="6 segments, interpolated")
    a1.set_xlabel("normalised power $u$")
    a1.set_ylabel(r"$1/\sqrt{u}$")
    a1.legend(loc="upper right", fontsize=10)
    clean(a1)

    # the real table: error of R in units of its own LSB (2^-16)
    base, slope = rsqrt_tables(cfg)
    A, F = cfg.addr_bits, cfg.frac_bits
    m = np.round(u * 2**32).astype(np.int64)
    kk = m >> (32 - A)
    f = (m >> (32 - A - F)) & ((1 << F) - 1)
    r_interp = base[kk - (1 << (A - 2))] - ((slope[kk - (1 << (A - 2))] * f + (1 << (F - 1))) >> F)
    r_near = base[kk - (1 << (A - 2))]
    e_i = r_interp - exact * 2**16
    e_n = r_near - exact * 2**16
    a2.semilogy(u, np.abs(e_n) + 1e-3, color=STONE, lw=0.8, label="nearest entry only")
    a2.semilogy(u, np.abs(e_i) + 1e-3, color=ACCENT, lw=0.9, label="linear interpolation")
    a2.set_xlabel("normalised power $u$")
    a2.set_ylabel("|error| of $R$ (LSB of $2^{-16}$)")
    a2.set_ylim(1e-2, 2e3)
    a2.legend(loc="upper right", fontsize=10)
    clean(a2)
    save(fig, "fig1-rsqrt-table.svg")
    res["table"] = {"entries": int(len(base)), "base_bits": 18, "slope_bits": 10,
                    "max_err_interp_lsb16": float(np.abs(e_i).max()), "max_err_nearest_lsb16": float(np.abs(e_n).max())}


# ---------------------------------------------------------------- fig 2: accuracy vs cost

def fig_sweep(res, i, q):
    rows_a, rows_b = [], []
    for A in range(5, 11):
        x, y = normalize_a(i, q, RsqrtCfg(A, 10))
        rows_a.append((3 * 2 ** (A - 2), errors(x, y, i, q)["max_lsb"]))
    for n in range(8, 23):
        x, y = normalize_b(i, q, CordicCfg(n, 5))
        rows_b.append((n, errors(x, y, i, q)["max_lsb"]))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    ea = np.array(rows_a)
    eb = np.array(rows_b)
    a1.loglog(ea[:, 0], ea[:, 1], "o-", color=ACCENT, ms=4)
    a1.set_xscale("log", base=2)
    a1.set_xticks(ea[:, 0], [str(int(v)) for v in ea[:, 0]])
    a1.minorticks_off()
    a1.set_xlabel("table entries (A: 1/sqrt by table)")
    a1.set_ylabel("worst-case error (output LSB)")
    a2.semilogy(eb[:, 0], eb[:, 1], "o-", color=ACCENT_DEEP, ms=4)
    a2.set_xlabel("micro-rotations (B: CORDIC)")
    for a in (a1, a2):
        a.axhline(1, color=INK_SOFT, lw=0.8, ls=(0, (3, 3)))
        clean(a)
    a1.text(ea[0, 0], 1.15, "1 LSB", color=INK_SOFT, fontsize=10)
    save(fig, "fig2-accuracy-vs-cost.svg")
    res["sweep_a"] = [{"entries": int(e), "max_lsb": float(v)} for e, v in rows_a]
    res["sweep_b"] = [{"iters": int(n), "max_lsb": float(v)} for n, v in rows_b]


# ---------------------------------------------------------------- fig 3: error vs input magnitude

def fig_magnitude(res):
    octs = np.arange(0, 15.01, 0.5)
    ang = np.linspace(-np.pi, np.pi, 1024, endpoint=False)
    curves = {"A: table": lambda i, q: normalize_a(i, q),
              "B: CORDIC": lambda i, q: normalize_b(i, q),
              "B without block normalisation": lambda i, q: normalize_b(i, q, CordicCfg(prenorm=False))}
    col = {"A: table": ACCENT, "B: CORDIC": ACCENT_DEEP, "B without block normalisation": STONE}
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    res["vs_magnitude"] = {}
    for name, fn in curves.items():
        worst = []
        for o in octs:
            mag = 2.0 ** o
            i = np.clip(np.round(mag * np.cos(ang)), OUT_MIN, OUT_MAX).astype(np.int64)
            q = np.clip(np.round(mag * np.sin(ang)), OUT_MIN, OUT_MAX).astype(np.int64)
            keep = (i != 0) | (q != 0)
            x, y = fn(i[keep], q[keep])
            worst.append(errors(x, y, i[keep], q[keep])["max_lsb"])
        ax.semilogy(octs, worst, "-", color=col[name], lw=1.6 if "without" not in name else 1.1, label=name)
        res["vs_magnitude"][name] = [float(v) for v in worst]
    ax.axhline(1, color=INK_SOFT, lw=0.8, ls=(0, (3, 3)))
    ax.set_xlabel(r"input magnitude $\log_2 |z|$ (LSB)")
    ax.set_ylabel("worst-case error (output LSB)")
    ax.legend(loc="upper right", fontsize=10)
    clean(ax)
    save(fig, "fig3-error-vs-magnitude.svg")


# ---------------------------------------------------------------- fig 4: resources

def read_stat(top):
    text = (ROOT / "build" / "synth" / f"{top}.stat").read_text()
    cells = {name: int(n) for n, name in re.findall(r"^\s+(\d+)\s+(\w+)\s*$", text, re.M)}
    lut = sum(v for k, v in cells.items() if re.fullmatch(r"LUT[1-6]", k))
    ff = sum(v for k, v in cells.items() if k in ("FDRE", "FDSE", "FDCE", "FDPE"))
    srl = sum(v for k, v in cells.items() if k.startswith("SRL"))
    dsp = cells.get("DSP48E1", 0)
    bram = sum(v for k, v in cells.items() if k.startswith("RAMB"))
    return {"LUT": lut, "FF": ff, "SRL": srl, "DSP48": dsp, "BRAM": bram, "CARRY4": cells.get("CARRY4", 0)}


def fig_resources(res):
    a, b = read_stat("normalize_lut"), read_stat("normalize_cordic")
    res["resources"] = {"A": a, "B": b}
    cats = ["LUT", "FF", "DSP48"]
    fig, axes = plt.subplots(1, 3, figsize=(9, 3.2))
    for ax, c in zip(axes, cats):
        ax.bar([0, 1], [a[c], b[c]], color=[ACCENT, ACCENT_DEEP], width=0.6)
        for xpos, v in zip([0, 1], [a[c], b[c]]):
            ax.text(xpos, v, f"{v}", ha="center", va="bottom", fontsize=11, color=INK)
        ax.set_xticks([0, 1], ["A: table", "B: CORDIC"])
        ax.set_title(c, fontsize=12, color=INK)
        ax.set_yticks([])
        ax.set_ylim(0, max(a[c], b[c], 1) * 1.18)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
    save(fig, "fig4-resources.svg")


def main():
    res = {}
    i, q = stimulus(100_000, seed=3)
    fig_table(res)
    fig_sweep(res, i, q)
    fig_magnitude(res)
    fig_resources(res)
    xa, ya = normalize_a(i, q)
    xb, yb = normalize_b(i, q)
    res["accuracy"] = {"A": errors(xa, ya, i, q), "B": errors(xb, yb, i, q)}
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("accuracy", "resources", "table")}, indent=1))


if __name__ == "__main__":
    main()
