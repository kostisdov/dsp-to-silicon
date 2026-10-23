"""Figures and numbers for the article, in the palette of kostisdov.github.io.

    uv run python scripts/figures.py

Writes SVGs to figures/ and every quoted number to figures/results.json.
Resource counts are read from the Yosys reports in build/synth (run scripts/synth.sh first).
"""

import json
import pathlib
import re
import subprocess
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
    e_i = r_interp - exact * 2**cfg.r_frac
    e_n = r_near - exact * 2**cfg.r_frac
    a2.semilogy(u, np.abs(e_n) + 1e-3, color=STONE, lw=0.8, label="entry below, no interpolation")
    a2.semilogy(u, np.abs(e_i) + 1e-3, color=ACCENT, lw=0.9, label="linear interpolation")
    a2.set_xlabel("normalised power $u$")
    a2.set_ylabel("|error| of $R$ (LSB of $2^{-17}$)")
    a2.set_ylim(1e-2, 2e3)
    a2.legend(loc="upper right", fontsize=10)
    clean(a2)
    save(fig, "fig1-rsqrt-table.svg")
    # worst case over every (address, fraction) cell, at both ends of the bits below the fraction
    off = 1 << (A - 2)
    K, Fm = np.meshgrid(np.arange(off, 1 << A), np.arange(1 << F), indexing="ij")
    w_i = w_n = 0.0
    for sub in (0, (1 << (32 - A - F)) - 1):
        mm = (K << (32 - A)) | (Fm << (32 - A - F)) | sub
        ex = 2.0 ** cfg.r_frac / np.sqrt(mm / 2.0 ** 32)
        ri = base[K - off] - ((slope[K - off] * Fm + (1 << (F - 1))) >> F)
        w_i = max(w_i, float(np.abs(ri - ex).max()))
        w_n = max(w_n, float(np.abs(base[K - off] - ex).max()))
    res["table"] = {"entries": int(len(base)), "base_bits": int(base.max()).bit_length(), "slope_bits": 10,
                    "max_slope": int(slope.max()), "lsb": f"2^-{cfg.r_frac}",
                    "max_err_interp_lsb": w_i, "max_err_entry_below_lsb": w_n}


# ---------------------------------------------------------------- fig 2: accuracy vs cost

EXH = ROOT / "build" / "exhaustive"


def exhaustive(*args):
    """Worst case and RMS over all 2^32 inputs, from tools/exhaustive.cpp."""
    out = subprocess.run([str(EXH), *map(str, args)], capture_output=True, text=True, check=True).stdout
    w, rms = re.search(r"worst ([\d.]+) LSB.*rms ([\d.]+) LSB", out).groups()
    return float(w), float(rms)


def fig_sweep(res, i, q):
    cfg_a, cfg_b = RsqrtCfg(), CordicCfg()
    rows_a = [(3 * 2 ** (A - 2), exhaustive("a", A, cfg_a.frac_bits, cfg_a.r_frac)[0]) for A in range(5, 11)]
    rows_b = [(n, exhaustive("b", n, cfg_b.guard)[0]) for n in range(8, 23)]
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
    # INV cells are LUT1s on a 7-series device
    lut = sum(v for k, v in cells.items() if re.fullmatch(r"LUT[1-6]|INV", k))
    ff = sum(v for k, v in cells.items() if k in ("FDRE", "FDSE", "FDCE", "FDPE"))
    srl = sum(v for k, v in cells.items() if k.startswith("SRL"))
    dsp = cells.get("DSP48E1", 0)
    bram = sum(v for k, v in cells.items() if k.startswith("RAMB"))
    return {"LUT": lut, "FF": ff, "SRL": srl, "DSP48": dsp, "BRAM": bram, "CARRY4": cells.get("CARRY4", 0)}


# Artix-7 XC7A35T, a small and common 7-series part, as the yardstick
DEVICE = {"name": "Artix-7 XC7A35T", "LUT": 20800, "FF": 41600, "DSP48": 90, "BRAM": 50}


def fig_resources(res):
    a, b = read_stat("normalize_lut"), read_stat("normalize_cordic")
    res["resources"] = {"A": a, "B": b, "device": DEVICE}
    rows = [("LUT", "LUTs"), ("FF", "Flip-flops"), ("DSP48", "DSP slices")]  # neither design uses block RAM
    fig, ax = plt.subplots(figsize=(8.5, 2.8))
    h = 0.36
    for r, (key, label) in enumerate(rows):
        y0 = len(rows) - 1 - r
        for off, d, col, name in ((h / 2, a, ACCENT, "A: table"), (-h / 2, b, ACCENT_DEEP, "B: CORDIC")):
            pct = 100 * d[key] / DEVICE[key]
            ax.barh(y0 + off, pct, height=h * 0.92, color=col, label=name if r == 0 else None)
            ax.text(pct + 0.25, y0 + off, f"{d[key]:,}", va="center", fontsize=10, color=INK)
    ax.set_yticks(range(len(rows)), [lab for _, lab in rows][::-1])
    ax.set_xlabel(f"share of an {DEVICE['name']} (%)")
    ax.set_xlim(0, 14)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower right", fontsize=10)
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
    ca, cb = RsqrtCfg(), CordicCfg()
    wa, ra = exhaustive("a", ca.addr_bits, ca.frac_bits, ca.r_frac)
    wb, rb = exhaustive("b", cb.iters, cb.guard)
    res["accuracy_exhaustive"] = {"A": {"max_lsb": wa, "rms_lsb": ra}, "B": {"max_lsb": wb, "rms_lsb": rb},
                                  "inputs": 2**32 - 1}
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("accuracy_exhaustive", "resources", "table")}, indent=1))


if __name__ == "__main__":
    main()
