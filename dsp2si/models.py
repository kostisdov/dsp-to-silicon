"""Reference models for z/|z| (unit-phasor normalisation of a complex sample).

Every fixed-point function here works on Python/NumPy integers and is the golden
reference model: the HLS C++ and the Verilog must be bit-accurate to it. Arithmetic right shifts (>>) on
signed integers floor towards minus infinity, exactly like Verilog's >>> on signed
operands, so the two agree on every bit.

Formats
  input  I, Q : signed 16-bit, Q1.15 (value = I / 2**15)
  output X, Y : signed 16-bit, Q1.15, rounded half up and saturated to [-32768, 32767]
  z = 0       : output (0, 0)
"""

from dataclasses import dataclass
import math

import numpy as np

W_IN = 16
FRAC = W_IN - 1                      # Q1.15
OUT_MAX, OUT_MIN = (1 << FRAC) - 1, -(1 << FRAC)


# ---------------------------------------------------------------- float reference

def normalize_float(i, q):
    """What the algorithm designer writes first: z / |z| in double precision."""
    z = (np.asarray(i, float) + 1j * np.asarray(q, float))
    mag = np.abs(z)
    out = np.where(mag > 0, z / np.where(mag > 0, mag, 1), 0)
    return out.real, out.imag


def sat(v):
    return np.clip(v, OUT_MIN, OUT_MAX)


def round_shift(v, sh):
    """Round half up, then arithmetic shift right by sh (array of shifts allowed, sh >= 1)."""
    return (v + (np.int64(1) << (sh - 1))) >> sh


# ---------------------------------------------------------------- architecture A: table-based 1/sqrt

@dataclass(frozen=True)
class RsqrtCfg:
    addr_bits: int = 9      # A: table address bits taken from the normalised power
    frac_bits: int = 12     # F: interpolation fraction bits
    r_frac: int = 17        # table values R = 1/sqrt(u) in unsigned Q2.17 (u in [1/4, 1) -> R in (1, 2])


def rsqrt_tables(cfg: RsqrtCfg):
    """Base values T[k] = round(2**r_frac / sqrt(k / 2**A)) and slopes D[k] = T[k] - T[k+1],
    for k = 2**(A-2) ... 2**A - 1 (the normalised power always has its top two bits != 00)."""
    A = cfg.addr_bits
    k = np.arange(1 << (A - 2), (1 << A) + 1, dtype=np.int64)
    t = np.round((1 << cfg.r_frac) / np.sqrt(k / (1 << A))).astype(np.int64)
    base, slope = t[:-1], t[:-1] - t[1:]
    return base, slope


def clz32(p):
    """Leading zeros of a 32-bit unsigned value (p > 0)."""
    p = np.asarray(p, dtype=np.int64)
    bit_length = np.zeros_like(p)
    for b in range(32):
        bit_length = np.where((p >> b) > 0, b + 1, bit_length)
    return 32 - bit_length


def normalize_a(i, q, cfg: RsqrtCfg = RsqrtCfg(), trace=False):
    """Fixed-point golden model of architecture A.

    1. P = I^2 + Q^2                                   (unsigned, <= 2**31)
    2. s = clz(P) rounded down to even; m = P << s     (m in [2**30, 2**32): u = m / 2**32 in [1/4, 1))
    3. k = m >> (32 - A); f = next F bits of m
       R = T[k] - ((D[k] * f + 2**(F-1)) >> F)         (~ 2**r_frac / sqrt(u))
    4. X = sat(round(I * R / 2**(r_frac + 1 - s/2)))   (since 1/sqrt(P) = 2**(s/2 - 16) / sqrt(u))
    """
    A, F = cfg.addr_bits, cfg.frac_bits
    i = np.asarray(i, dtype=np.int64)
    q = np.asarray(q, dtype=np.int64)
    base, slope = rsqrt_tables(cfg)
    off = 1 << (A - 2)

    p = i * i + q * q
    zero = p == 0
    ps = np.where(zero, 1, p)
    s = clz32(ps) & ~1
    m = (ps << s) & 0xFFFFFFFF
    k = m >> (32 - A)
    f = (m >> (32 - A - F)) & ((1 << F) - 1)
    r = base[k - off] - ((slope[k - off] * f + (1 << (F - 1))) >> F)
    sh = cfg.r_frac + 1 - (s >> 1)
    x = np.where(zero, 0, sat(round_shift(i * r, sh)))
    y = np.where(zero, 0, sat(round_shift(q * r, sh)))
    if trace:
        return x, y, dict(p=p, s=s, m=m, k=k, f=f, r=r, sh=sh)
    return x, y


# ---------------------------------------------------------------- architecture B: CORDIC, signs only

@dataclass(frozen=True)
class CordicCfg:
    iters: int = 18         # N micro-rotations
    guard: int = 8          # extra fractional bits inside the datapath
    prenorm: bool = True    # block normalisation before the micro-rotations (off only to show why it matters)


def cordic_gain(n):
    return math.prod(math.sqrt(1 + 2.0 ** (-2 * j)) for j in range(n))


def normalize_b(i, q, cfg: CordicCfg = CordicCfg(), trace=False):
    """Fixed-point golden model of architecture B.

    Vectoring pass on (x, y) = z: each step picks d = +1 if y < 0 else -1 and rotates by
    -d*atan(2**-j) towards the x axis. The rotation pass applies the same signs to
    (u, v) = (1/K, 0), rotating it by +angle(z): the result is z/|z| without ever
    computing the angle. A common left shift first makes the result independent of |z|, and a
    +/-90 degree pre-rotation brings z into the right half plane.
    """
    N, G = cfg.iters, cfg.guard
    i = np.asarray(i, dtype=np.int64)
    q = np.asarray(q, dtype=np.int64)
    zero = (i == 0) & (q == 0)

    # block normalisation: z/|z| does not depend on scale, so shift I and Q left together until
    # the larger magnitude reaches bit 14. Without it a small z loses its angle in the shifts.
    a = np.maximum(np.abs(i), np.abs(q))
    sh = np.maximum(0, FRAC - 1 - (32 - clz32(np.where(a == 0, 1, a)) - 1))
    if not cfg.prenorm:
        sh = np.zeros_like(sh)
    i_n, q_n = i << sh, q << sh

    # pre-rotation: if I < 0, rotate z by -90 deg (Q >= 0) or +90 deg (Q < 0); undo on the output
    left = i_n < 0
    up = q_n >= 0
    x = np.where(left, np.where(up, q_n, -q_n), i_n) << G
    y = np.where(left, np.where(up, -i_n, i_n), q_n) << G

    one = (1 << (FRAC + G))
    u = np.full_like(i, int(round(one / cordic_gain(N))))
    v = np.zeros_like(i)
    for j in range(N):
        d = np.where(y < 0, 1, -1)           # rotate towards y = 0
        x, y = x - d * (y >> j), y + d * (x >> j)
        u, v = u + d * (v >> j), v - d * (u >> j)   # the inverse rotation, same signs
    # undo the pre-rotation on the unit phasor
    u2 = np.where(left, np.where(up, -v, v), u)
    v2 = np.where(left, np.where(up, u, -u), v)
    xo = np.where(zero, 0, sat(round_shift(u2, G)))
    yo = np.where(zero, 0, sat(round_shift(v2, G)))
    if trace:
        return xo, yo, dict(x=x, y=y, u=u, v=v)
    return xo, yo


# ---------------------------------------------------------------- error metrics

def errors(x, y, i, q):
    """Error of a fixed-point output against the float reference, in output LSBs."""
    fx, fy = normalize_float(i, q)
    ex = np.asarray(x) - fx * (1 << FRAC)
    ey = np.asarray(y) - fy * (1 << FRAC)
    # +1.0 is not representable in Q1.15: count the unavoidable saturation as zero error
    ex = np.where((fx * (1 << FRAC) > OUT_MAX) & (np.asarray(x) == OUT_MAX), 0, ex)
    ey = np.where((fy * (1 << FRAC) > OUT_MAX) & (np.asarray(y) == OUT_MAX), 0, ey)
    e = np.maximum(np.abs(ex), np.abs(ey))
    return {"max_lsb": float(e.max()), "rms_lsb": float(np.sqrt(np.mean(ex**2 + ey**2) / 2))}


def stimulus(n=200_000, seed=1):
    """Random samples with log-uniform magnitude (every octave equally), plus hard cases."""
    rng = np.random.default_rng(seed)
    mag = 2.0 ** rng.uniform(0, 15, n)                  # 1 LSB ... full scale
    ang = rng.uniform(-np.pi, np.pi, n)
    i = np.clip(np.round(mag * np.cos(ang)), OUT_MIN, OUT_MAX).astype(np.int64)
    q = np.clip(np.round(mag * np.sin(ang)), OUT_MIN, OUT_MAX).astype(np.int64)
    corners = np.array([(OUT_MIN, OUT_MIN), (OUT_MIN, 0), (0, OUT_MIN), (OUT_MAX, OUT_MAX),
                        (OUT_MAX, 0), (0, OUT_MAX), (1, 0), (0, 1), (-1, 0), (0, -1), (1, 1),
                        (-1, -1), (OUT_MIN, OUT_MAX), (OUT_MAX, OUT_MIN), (0, 0)], dtype=np.int64)
    i = np.concatenate([corners[:, 0], i])
    q = np.concatenate([corners[:, 1], q])
    return i, q
