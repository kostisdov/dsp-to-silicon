"""cocotb testbench: stream the golden vectors through the RTL, one sample per clock,
and check every output bit-exactly against the fixed-point model.

The architecture under test is chosen with the DUT_KIND environment variable:
'a' (table-based, columns xa ya) or 'b' (CORDIC, columns xb yb).
"""

import collections
import os

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

COLS = {"a": (2, 3), "b": (4, 5)}


@cocotb.test()
async def bit_exact_against_golden_model(dut):
    kind = os.environ["DUT_KIND"]
    data = np.loadtxt(os.environ["VECTORS"], dtype=np.int64)
    limit = int(os.environ.get("N_VECTORS", "0")) or len(data)
    data = data[:limit]
    cx, cy = COLS[kind]

    Clock(dut.clk, 10, unit="ns").start()
    dut.in_valid.value = 0
    dut.i.value = 0
    dut.q.value = 0

    pending = collections.deque()
    checked = mismatches = 0
    feed = iter(data)
    done_feeding = False
    idle = 0

    while True:
        await FallingEdge(dut.clk)

        # sample: outputs change on the rising edge, so they are stable here
        if str(dut.out_valid.value) == "1":
            i, q, ex, ey = pending.popleft()
            gx, gy = dut.x.value.to_signed(), dut.y.value.to_signed()
            if (gx, gy) != (ex, ey):
                if mismatches < 10:
                    dut._log.error(f"i={i} q={q}: rtl=({gx},{gy}) golden=({ex},{ey})")
                mismatches += 1
            checked += 1

        # drive the next sample
        row = None if done_feeding else next(feed, None)
        if row is None:
            done_feeding = True
            dut.in_valid.value = 0
            idle += 1
            if not pending or idle > 64:
                break
        else:
            i, q = int(row[0]), int(row[1])
            dut.i.value = i
            dut.q.value = q
            dut.in_valid.value = 1
            pending.append((i, q, int(row[cx]), int(row[cy])))

    dut._log.info(f"checked {checked} samples, {mismatches} mismatches")
    assert not pending, f"{len(pending)} samples never came out of the pipeline"
    assert checked == len(data)
    assert mismatches == 0
