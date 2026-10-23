"""Build each RTL design with Icarus Verilog and run the cocotb bit-exactness test.

    uv run python -m dsp2si.export      # vectors and tables first
    uv run pytest tests/test_rtl.py
"""

import os
import pathlib

import pytest
from cocotb_tools.runner import get_runner

ROOT = pathlib.Path(__file__).resolve().parents[1]
RTL = ROOT / "rtl"
VECTORS = ROOT / "build" / "vectors.txt"

DESIGNS = {
    "a": ("normalize_lut", {"BASE_HEX": f'"{RTL / "rsqrt_base.hex"}"', "SLOPE_HEX": f'"{RTL / "rsqrt_slope.hex"}"'}),
    "b": ("normalize_cordic", {}),
}


@pytest.mark.skipif(not VECTORS.exists(), reason="run `python -m dsp2si.export` first")
@pytest.mark.parametrize("kind", ["a", "b"])
def test_rtl_bit_exact(kind):
    top, params = DESIGNS[kind]
    runner = get_runner("icarus")
    build_dir = ROOT / "build" / f"sim_{top}"
    runner.build(
        sources=[RTL / f"{top}.v"],
        includes=[RTL],
        hdl_toplevel=top,
        parameters=params,
        build_dir=build_dir,
        always=True,
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel=top,
        test_module="cocotb_normalize",
        test_dir=ROOT / "tb",
        build_dir=build_dir,
        extra_env={
            "DUT_KIND": kind,
            "VECTORS": str(VECTORS),
            "N_VECTORS": os.environ.get("N_VECTORS", "0"),
            "PYTHONPATH": str(ROOT / "tb"),
        },
    )
