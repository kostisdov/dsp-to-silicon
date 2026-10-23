"""Check that the RTL verification catches small bugs: apply one-line mutations to a copy of
the RTL and count the samples the cocotb testbench flags on the full vector set.

    uv run python scripts/mutation_test.py
"""

import json
import pathlib
import shutil
import tempfile

from cocotb_tools.runner import get_runner

ROOT = pathlib.Path(__file__).resolve().parents[1]
VECTORS = ROOT / "build" / "vectors.txt"

MUTATIONS = [
    ("a", "normalize_lut", "interpolation rounding constant 2048 -> 2047", "22'd2048", "22'd2047"),
    ("a", "normalize_lut", "output rounding removed", "r = (val + (36'sd1 <<< (sh - 5'd1))) >>> sh;", "r = val >>> sh;"),
    ("b", "normalize_cordic", "output rounding removed", "r = (val + (1 <<< (GUARD - 1))) >>> GUARD;", "r = val >>> GUARD;"),
    ("b", "normalize_cordic", "last micro-rotation sign inverted", "wire neg = yj[W-1];", "wire neg = (j == ITERS - 1) ? ~yj[W-1] : yj[W-1];"),
]


def run(kind, top, rtl_dir):
    params = {}
    if kind == "a":
        params = {"BASE_HEX": f'"{rtl_dir / "rsqrt_base.hex"}"', "SLOPE_HEX": f'"{rtl_dir / "rsqrt_slope.hex"}"'}
    build = rtl_dir / "sim"
    report = rtl_dir / "report.txt"
    runner = get_runner("icarus")
    runner.build(sources=[rtl_dir / f"{top}.v"], includes=[rtl_dir], hdl_toplevel=top, parameters=params,
                 build_dir=build, always=True, timescale=("1ns", "1ps"))
    runner.test(hdl_toplevel=top, test_module="cocotb_normalize", test_dir=ROOT / "tb", build_dir=build,
                extra_env={"DUT_KIND": kind, "VECTORS": str(VECTORS), "REPORT": str(report),
                           "PYTHONPATH": str(ROOT / "tb")})
    checked, bad = map(int, report.read_text().split())
    return checked, bad


def main():
    results = []
    for kind, top, name, old, new in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            rtl = pathlib.Path(tmp)
            for f in (ROOT / "rtl").iterdir():
                if f.is_file():
                    shutil.copy(f, rtl / f.name)
            src = (rtl / f"{top}.v").read_text()
            assert old in src, name
            (rtl / f"{top}.v").write_text(src.replace(old, new, 1))
            checked, bad = run(kind, top, rtl)
        results.append({"design": kind.upper(), "mutation": name, "flagged": bad, "checked": checked})
        print(f"{kind.upper()}: {name}: {bad} of {checked} samples flagged")
    (ROOT / "figures" / "mutations.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
