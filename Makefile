# From math to silicon: z/|z| as float, fixed point, HLS C++ and Verilog.
# Requires uv, clang++, icarus-verilog and yosys (brew install icarus-verilog yosys).

HLS_INC := third_party/hls_types/include

.PHONY: all headers vectors csim test synth figures clean

all: vectors csim test synth figures

headers:
	@test -d $(HLS_INC) || scripts/get_hls_headers.sh

vectors:
	uv run python -m dsp2si.export

csim: headers vectors
	clang++ -std=c++17 -O2 -I$(HLS_INC) -Ihls hls/normalize_hls.cpp hls/tb_normalize.cpp cpu/normalize_cpu.cpp -o build/csim
	./build/csim build/vectors.txt

test: vectors
	uv run pytest -q

synth:
	scripts/synth.sh

figures: synth
	uv run python scripts/figures.py

clean:
	rm -rf build sim_build
