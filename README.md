# From math to silicon

One small DSP block, z/|z| (normalise a complex sample to unit magnitude), carried from a
floating-point formula to two pipelined FPGA designs that are verified bit-accurate against a
fixed-point golden model.

| Stage | Where | Check |
|---|---|---|
| Float reference | `dsp2si/models.py` `normalize_float` | the formula |
| Fixed-point golden models | `dsp2si/models.py` `normalize_a`, `normalize_b` | worst case < 1 LSB over all 2³² inputs (`tools/exhaustive.cpp`, `make exhaustive`) |
| CPU C++ vs HLS C++ | `cpu/`, `hls/` | HLS C simulation bit-accurate on 100,015 vectors (`make csim`) |
| Verilog RTL | `rtl/normalize_lut.v`, `rtl/normalize_cordic.v` | cocotb RTL verification, bit-accurate on 100,015 vectors (`tests/test_rtl.py`) |
| Resources | `scripts/synth.sh` | Yosys `synth_xilinx`, 7-series (estimates, not Vivado) |

**A, table-based 1/sqrt.** P = I² + Q², an even leading-zero shift into [1/4, 1), a 384-entry
table (19-bit base, 10-bit slope) with 12-bit linear interpolation, two multiplies, a rounding
shift. Latency 6, one sample per clock.

**B, CORDIC.** A common left shift, a ±90° pre-rotation, then 18 stages that run the vectoring
pass on z and the inverse rotation on (1/K, 0) with the same signs, 8 guard bits. No angle, no
arctan table, no multipliers. Latency 20, one sample per clock.

Accuracy over all 2³² inputs; resources from Yosys (LUTs include INV cells):

| | worst error | RMS error | latency | LUT | FF | DSP48 | BRAM |
|---|---|---|---|---|---|---|---|
| A | 0.795 LSB | 0.296 LSB | 6 | 796 | 139 | 5 | 0 |
| B | 0.797 LSB | 0.306 LSB | 20 | 2514 | 1926 | 0 | 0 |

`make mutations` injects one-line bugs into a copy of the RTL and reports how many of the
100,015 samples the testbench flags (921 for a one-LSB change in an interpolation constant).

## Run

```sh
brew install icarus-verilog yosys     # verilator optional, for linting
uv sync
make all                              # vectors, HLS C-sim, exhaustive check, tests, synthesis, figures
```

`third_party/hls_types` is AMD's open-source `ap_int`/`ap_fixed` (Apache-2.0), fetched by
`scripts/get_hls_headers.sh` with a two-line patch so it compiles against libc++ on macOS.

Article: [From math to silicon: a DSP block on FPGA](https://kostisdov.github.io/posts/from-math-to-silicon/).

## License

MIT, see `LICENSE`. `third_party/hls_types-libcxx.patch` modifies AMD's Apache-2.0 headers and is
distributed under the Apache License 2.0.
