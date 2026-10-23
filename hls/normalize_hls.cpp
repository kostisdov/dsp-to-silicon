// z/|z| for HLS: one sample per clock, no divider and no square root.
// Bit-exact with normalize_a() in dsp2si/models.py.
#include "normalize_hls.h"
#include "rsqrt_tables.h"

// round half up, then shift right by sh (2..17), saturate to Q1.15
static sample_t round_sat(ap_int<35> v, ap_uint<5> sh) {
    ap_int<35> r = (v + (ap_int<35>(1) << (sh - 1))) >> sh;
    if (r > 32767) return 32767;
    if (r < -32768) return -32768;
    return r;
}

void normalize_hls(sample_t i, sample_t q, sample_t &x, sample_t &y) {
#pragma HLS PIPELINE II=1
#pragma HLS BIND_STORAGE variable=RSQRT_BASE type=rom_1p impl=lutram
#pragma HLS BIND_STORAGE variable=RSQRT_SLOPE type=rom_1p impl=lutram

    // 1. power, exact: |I|, |Q| <= 2^15, so P < 2^31
    ap_uint<32> p = ap_uint<32>(i * i) + ap_uint<32>(q * q);
    if (p == 0) {
        x = 0;
        y = 0;
        return;
    }

    // 2. normalise by an even shift: m = P << s lies in [2^30, 2^32)
    ap_uint<5> s = p.countLeadingZeros() & 0x1E;
    ap_uint<32> m = p << s;

    // 3. table lookup with linear interpolation: r ~ 2^16 / sqrt(m / 2^32)
    ap_uint<9> k = m(31, 23);
    ap_uint<10> f = m(22, 13);
    ap_uint<18> r = RSQRT_BASE[k - 128] - ((RSQRT_SLOPE[k - 128] * f + 512) >> 10);

    // 4. undo the normalisation: x = i * r / 2^(17 - s/2)
    ap_uint<5> sh = 17 - (s >> 1);
    x = round_sat(i * r, sh);
    y = round_sat(q * r, sh);
}
