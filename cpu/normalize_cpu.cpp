// z/|z| as written for a CPU: the processor already has floating-point multiply,
// square root and divide units, so the code is the formula.
#include <complex>

std::complex<float> normalize_cpu(std::complex<float> z) {
    float m = std::abs(z);  // sqrt(re^2 + im^2)
    return m > 0.0f ? z / m : std::complex<float>(0.0f, 0.0f);
}
