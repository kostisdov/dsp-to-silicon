# Article outline: from math to silicon

Working title options
- From math to silicon
- What a square root costs in hardware
- z/|z| in silicon

Suggested description (site style): *A DSP algorithm is designed in floating point and shipped
in fixed-point logic. Following one small block, z/|z|, from formula to two verified FPGA
pipelines shows where the effort goes: word lengths, the operations a CPU gets for free,
and proving the hardware matches the model bit for bit.*

All numbers below come from `figures/results.json` and the test logs; rerun with `make all`.

---

## 1. The block

- z/|z|: scale a complex sample to unit magnitude, keep its phase. Used in AGC, phase
  tracking, constant-modulus equalisers, before a phase detector.
- Spec chosen for the article: I, Q signed 16-bit Q1.15 in; X, Y Q1.15 out; one sample per
  clock; worst-case error under 1 LSB of the output; z = 0 maps to 0.
- On a CPU it is two lines (snippet: `cpu/normalize_cpu.cpp`). The float result is within
  0.003 LSB of exact: accuracy is free there. In logic, every bit of it has to be paid for.

## 2. From float to fixed point

- The float model (`normalize_float`) defines *behaviour*; the fixed-point model defines
  *bits*. The second one is the golden reference everything else is checked against.
- Choices to make explicit: formats (Q1.15 in and out), where rounding happens (round half
  up, once, at the output), saturation (+1.0 is not representable in Q1.15, so 32767).
- Key property that the whole design exploits: z/|z| is scale-invariant. Normalising the
  input by a power of two changes nothing in the result and everything in the precision.
- Error budget: target < 1 LSB worst case. Both designs land at the same accuracy
  (A 0.94 LSB, B 0.98 LSB worst case; RMS 0.32 LSB for both, against ~0.29 for ideal rounding),
  which makes the cost comparison fair.

## 3. Why 1/x and sqrt are the hard part

- A CPU has a divider and a square-root unit; an FPGA fabric has adders, LUTs, small
  multipliers (DSP48 slices) and block RAM. Division and square root must be built.
- The menu: shift-and-add (leading-zero count, barrel shifter), CORDIC (rotations by
  atan(2^-j), adds and shifts only), tables with interpolation, Newton–Raphson refinement.
- Combine the two operations: z/|z| = z · (I² + Q²)^(-1/2). One reciprocal square root
  instead of a square root followed by a division.

## 4. Architecture A: normalise, look up, interpolate

- Steps (snippet: the four commented steps of `hls/normalize_hls.cpp`):
  1. P = I² + Q², exact in 32 bits.
  2. Even shift s = clz(P) rounded down, m = P << s in [2^30, 2^32): u = m/2^32 in [1/4, 1).
     Even, so that the square root of 2^s is an exact shift by s/2.
  3. 1/sqrt(u) from a 384-entry table addressed by the top 9 bits of m, linearly
     interpolated with the next 10 bits. Base 18 bits, slope 10 bits per entry.
  4. Multiply I and Q by the result and shift by 17 − s/2, rounding once.
- Figure 1 (`fig1-rsqrt-table.svg`): the table and its error. Nearest entry alone: up to
  489 LSB of 2^-16; with interpolation: 1.7 LSB. Interpolation costs one small multiplier;
  matching it without interpolation would need a table about 290 times larger.
- Figure 2 left (`fig2-accuracy-vs-cost.svg`): table size against worst-case error;
  384 entries is the smallest that meets 1 LSB.
- Mention: one Newton step would allow a much smaller table at the cost of extra
  multipliers (not built here).

## 5. Architecture B: CORDIC without the angle

- Vectoring CORDIC rotates z onto the x axis with micro-rotations of ±atan(2^-j); the signs
  d_j encode the angle. Rotating (1/K, 0) with the *same* signs in the opposite direction
  yields e^(jθ) = z/|z| directly: no angle register, no arctan table.
- Two details that the fixed-point model forced:
  - a ±90° pre-rotation into the right half plane (CORDIC converges for |θ| < 99.9°);
  - block normalisation: a common left shift of I and Q. Without it, small inputs lose
    their angle in the shifts. Figure 3 (`fig3-error-vs-magnitude.svg`): without it the
    error exceeds 1000 LSB at the smallest magnitudes; with it both designs stay under
    1 LSB at every magnitude. The same scale invariance as in A.
- Figure 2 right: 18 micro-rotations with 5 guard bits are needed for < 1 LSB.

## 6. CPU C++ against HLS C++

- Side by side: `cpu/normalize_cpu.cpp` (the formula) and `hls/normalize_hls.cpp`
  (arbitrary-precision `ap_int`/`ap_uint` types, explicit widths, explicit rounding,
  `#pragma HLS PIPELINE II=1`, the table bound to LUT ROM).
- Points: HLS C++ is still C++, but it describes hardware: every width is a cost, every
  operation is a circuit, the loop-free body is one pipeline stage per clock. The approximation
  is in the code, not in a library call.
- Verified: the HLS C simulation matches the Python golden model on 100,015 of 100,015 vectors.
- Honest note: synthesis with Vitis HLS was not run (macOS); the C simulation uses AMD's
  open-source `ap_int` headers. Vitis also ships `hls::rsqrt` / `hls::sqrt` in `hls_math.h`
  if a library approximation is acceptable.

## 7. HLS or RTL

- Both architectures written as hand Verilog: `rtl/normalize_lut.v` (6 pipeline stages)
  and `rtl/normalize_cordic.v` (20 stages, a generate loop of identical micro-rotations).
- When HLS: algorithm-heavy blocks, fast exploration of word lengths, C-level verification.
  When RTL: tight control of pipelining and resources, structures HLS does not express well,
  or blocks reused for years.

## 8. Verification: proving the bits

- cocotb testbench (`tb/cocotb_normalize.py`): streams vectors into the pipeline one per
  clock, checks every output bit-exactly against the golden model. Random inputs with
  log-uniform magnitude (every octave equally) plus corner cases (±full scale, 1 LSB, zero).
- Result: 100,015 of 100,015 samples bit-exact for both designs, in Icarus Verilog.
- The test catches real bugs: changing one rounding constant by one (512 → 511) fails on
  the first affected sample; removing the CORDIC output rounding fails 1,399 of 2,000.
- Why bit-exact rather than "close enough": the golden model already carries the error
  analysis; any difference in the RTL is a bug, not noise.

## 9. What it costs

- Figure 4 (`fig4-resources.svg`), Yosys `synth_xilinx` for a 7-series device (estimates):

  | | LUT | FF | DSP48 | BRAM |
  |---|---|---|---|---|
  | A: table | 739 | 137 | 5 | 0 |
  | B: CORDIC | 2478 | 1692 | 0 | 0 |

- Reading: at one sample per clock, the "multiplier-free" CORDIC costs 3.4× the LUTs and
  12× the flip-flops of the table design; it wins only when DSP slices are the scarce
  resource. An iterative CORDIC (one stage reused 18 times) would be far smaller at 1/18 of
  the throughput.
- The table (384 × 28 bits) went into LUTs, not block RAM; Vivado may choose differently.
- No timing numbers: Yosys does not give a reliable Fmax for 7-series.

## 10. Closing

- The formula took two lines; the hardware took a word-length budget, two
  approximations, a normalisation trick, and a bit-exact proof. The proof is what makes the
  rest trustworthy.

---

Code to link: the repository (to be published), e.g. github.com/kostisdov/dsp-to-silicon.
