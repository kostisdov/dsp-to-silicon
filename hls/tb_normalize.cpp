// C simulation (C-sim): the HLS function must match the bit-accurate Python golden model.
// The CPU float version is measured against the same vectors for comparison.
#include <cmath>
#include <complex>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

#include "normalize_hls.h"

std::complex<float> normalize_cpu(std::complex<float> z);

int main(int argc, char **argv) {
    std::ifstream in(argc > 1 ? argv[1] : "build/vectors.txt");
    std::string line;
    long n = 0, mismatches = 0;
    double cpu_max = 0;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ss(line);
        int i, q, xa, ya, xb, yb;
        ss >> i >> q >> xa >> ya >> xb >> yb;

        sample_t x, y;
        normalize_hls(sample_t(i), sample_t(q), x, y);
        if (x.to_int() != xa || y.to_int() != ya) {
            if (mismatches < 10)
                std::printf("MISMATCH i=%d q=%d: hls=(%d,%d) golden=(%d,%d)\n", i, q, x.to_int(), y.to_int(), xa, ya);
            mismatches++;
        }

        // CPU float, scaled to Q1.15 LSBs, against the double-precision formula
        std::complex<float> c = normalize_cpu({float(i), float(q)});
        double m = std::hypot(double(i), double(q));
        if (m > 0) {
            double ex = std::fabs(c.real() * 32768.0 - i / m * 32768.0);
            double ey = std::fabs(c.imag() * 32768.0 - q / m * 32768.0);
            cpu_max = std::fmax(cpu_max, std::fmax(ex, ey));
        }
        n++;
    }
    std::printf("%ld vectors, %ld HLS mismatches against the golden model\n", n, mismatches);
    std::printf("CPU float error before quantisation: max %.2e LSB\n", cpu_max);
    return mismatches != 0;
}
