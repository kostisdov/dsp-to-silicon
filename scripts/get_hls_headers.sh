#!/bin/sh
# Fetch AMD's open-source arbitrary-precision types (Apache-2.0) and patch them for libc++.
set -e
cd "$(dirname "$0")/.."
[ -d third_party/hls_types ] || git clone -q --depth 1 https://github.com/Xilinx/HLS_arbitrary_Precision_Types.git third_party/hls_types
cd third_party/hls_types && rm -rf .git
git apply --unsafe-paths --directory=. ../hls_types-libcxx.patch 2>/dev/null || patch -p1 -N < ../hls_types-libcxx.patch || true
