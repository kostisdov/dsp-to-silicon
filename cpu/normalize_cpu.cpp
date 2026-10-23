// z/|z| as written for a CPU: the processor already has floating-point multiply,
// square root and divide units. Written as z * (re^2 + im^2)^(-1/2), the same
// reciprocal square root that both FPGA designs compute.
#include <cmath>
#include <complex>

std::complex<float> normalize_cpu(std::complex<float> z) {
    const float p = std::norm(z);  // re^2 + im^2
    return p > 0.0f ? z * (1.0f / std::sqrt(p)) : std::complex<float>{};
}
