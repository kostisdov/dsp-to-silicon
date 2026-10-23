# From math to silicon

One small DSP block, z/|z| (normalise a complex sample to unit magnitude), carried from a
floating-point formula to two pipelined FPGA designs that are verified bit-exact against a
fixed-point golden model.

| Stage | Where | Check |
|---|---|---|
| Float reference | `dsp2si/models.py` `normalize_float` | the formula |
| Fixed-point golden models | `dsp2si/models.py` `normalize_a`, `normalize_b` | < 1 LSB of the float reference (`tests/test_models.py`) |
| CPU C++ vs HLS C++ | `cpu/`, `hls/` | HLS C simulation bit-exact on 100,015 vectors (`make csim`) |
| Verilog RTL | `rtl/normalize_lut.v`, `rtl/normalize_cordic.v` | cocotb, bit-exact on 100,015 vectors (`tests/test_rtl.py`) |
| Resources | `scripts/synth.sh` | Yosys `synth_xilinx`, 7-series (estimates, not Vivado) |

**A, table-based 1/sqrt.** P = I² + Q², an even leading-zero shift into [1/4, 1), a 384-entry
table with linear interpolation, two multiplies, a rounding shift. Latency 6, one sample per clock.

**B, CORDIC.** A common left shift, a ±90° pre-rotation, then 18 stages that run the vectoring
pass on z and the inverse rotation on (1/K, 0) with the same signs. No angle, no arctan table,
no multipliers. Latency 20, one sample per clock.

| | worst error | RMS error | LUT | FF | DSP48 | BRAM |
|---|---|---|---|---|---|---|
| A | 0.94 LSB | 0.32 LSB | 739 | 137 | 5 | 0 |
| B | 0.98 LSB | 0.32 LSB | 2478 | 1692 | 0 | 0 |

## Run

```sh
brew install icarus-verilog yosys     # verilator optional, for linting
uv sync
make all                              # vectors, HLS C-sim, tests, synthesis, figures
```

`third_party/hls_types` is AMD's open-source `ap_int`/`ap_fixed` (Apache-2.0), fetched by
`scripts/get_hls_headers.sh` with a two-line patch so it compiles against libc++ on macOS.
