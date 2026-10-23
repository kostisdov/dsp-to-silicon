#pragma once
#include <ap_int.h>

typedef ap_int<16> sample_t;  // signed Q1.15

void normalize_hls(sample_t i, sample_t q, sample_t &x, sample_t &y);
