#!/bin/sh
# Resource estimates with Yosys for a Xilinx 7-series target (estimates, not Vivado results).
set -e
cd "$(dirname "$0")/../rtl"
mkdir -p ../build/synth
for top in normalize_lut normalize_cordic; do
  yosys -q -l ../build/synth/$top.log \
    -p "read_verilog -I. $top.v; synth_xilinx -family xc7 -top $top; tee -o ../build/synth/$top.stat stat" >/dev/null
done
echo "reports in build/synth/"
