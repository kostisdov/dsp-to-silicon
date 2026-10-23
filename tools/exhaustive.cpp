// Exhaustive worst-case error of the two fixed-point models over all 2^32 inputs.
// Plain int64 re-implementations of normalize_a / normalize_b in dsp2si/models.py;
// `--vectors` mode cross-checks them against the Python golden outputs first.
//
//   exhaustive a <addr_bits> <frac_bits> <r_frac>
//   exhaustive b <iters> <guard>
//   exhaustive vectors <file> <a-params...> -- <b-params...>   (see main)
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using i64 = int64_t;
static const i64 OUT_MAX = 32767, OUT_MIN = -32768;

static i64 sat(i64 v) { return v > OUT_MAX ? OUT_MAX : (v < OUT_MIN ? OUT_MIN : v); }
static i64 round_shift(i64 v, int sh) { return (v + (i64(1) << (sh - 1))) >> sh; }  // >> floors, like numpy
static int bit_length(uint64_t v) { return v ? 64 - __builtin_clzll(v) : 0; }

struct ModelA {
    int A, F, R;
    std::vector<i64> base, slope;
    ModelA(int A_, int F_, int R_) : A(A_), F(F_), R(R_) {
        for (i64 k = i64(1) << (A - 2); k <= (i64(1) << A); k++)
            base.push_back(i64(std::nearbyint(std::ldexp(1.0, R) / std::sqrt(double(k) / double(i64(1) << A)))));
        for (size_t j = 0; j + 1 < base.size(); j++) slope.push_back(base[j] - base[j + 1]);
        base.pop_back();
    }
    void run(i64 i, i64 q, i64 &x, i64 &y) const {
        i64 p = i * i + q * q;
        if (p == 0) { x = y = 0; return; }
        int s = (32 - bit_length(uint64_t(p))) & ~1;
        i64 m = (p << s) & 0xFFFFFFFFLL;
        i64 k = m >> (32 - A);
        i64 f = (m >> (32 - A - F)) & ((i64(1) << F) - 1);
        i64 off = i64(1) << (A - 2);
        i64 r = base[k - off] - ((slope[k - off] * f + (i64(1) << (F - 1))) >> F);
        int sh = R + 1 - (s >> 1);
        x = sat(round_shift(i * r, sh));
        y = sat(round_shift(q * r, sh));
    }
};

struct ModelB {
    int N, G;
    i64 inv_gain;
    ModelB(int N_, int G_) : N(N_), G(G_) {
        double k = 1;
        for (int j = 0; j < N; j++) k *= std::sqrt(1 + std::ldexp(1.0, -2 * j));
        inv_gain = i64(std::nearbyint(std::ldexp(1.0, 15 + G) / k));
    }
    void run(i64 i, i64 q, i64 &xo, i64 &yo) const {
        if (i == 0 && q == 0) { xo = yo = 0; return; }
        i64 a = std::max(std::llabs(i), std::llabs(q));
        int sh = std::max(0, 14 - (bit_length(uint64_t(a)) - 1));
        i64 in = i << sh, qn = q << sh;
        bool left = in < 0, up = qn >= 0;
        i64 x = (left ? (up ? qn : -qn) : in) << G;
        i64 y = (left ? (up ? -in : in) : qn) << G;
        i64 u = inv_gain, v = 0;
        for (int j = 0; j < N; j++) {
            i64 d = y < 0 ? 1 : -1;
            i64 xn = x - d * (y >> j), yn = y + d * (x >> j);
            i64 un = u + d * (v >> j), vn = v - d * (u >> j);
            x = xn; y = yn; u = un; v = vn;
        }
        i64 u2 = left ? (up ? -v : v) : u;
        i64 v2 = left ? (up ? u : -u) : v;
        xo = sat(round_shift(u2, G));
        yo = sat(round_shift(v2, G));
    }
};

// error in output LSB against exact z/|z|, the unavoidable +1.0 -> 32767 saturation counted as 0;
// returns the larger component error and adds both squared errors to sq
static double err(i64 i, i64 q, i64 x, i64 y, long double &sq) {
    double m = std::sqrt(double(i * i + q * q));
    double fx = double(i) / m * 32768.0, fy = double(q) / m * 32768.0;
    double ex = (fx > OUT_MAX && x == OUT_MAX) ? 0 : std::fabs(double(x) - fx);
    double ey = (fy > OUT_MAX && y == OUT_MAX) ? 0 : std::fabs(double(y) - fy);
    sq += ex * ex + ey * ey;
    return std::max(ex, ey);
}

template <class M>
static void exhaustive(const M &model) {
    unsigned nt = std::max(1u, std::thread::hardware_concurrency());
    std::atomic<int> next{-32768};
    std::mutex mu;
    double worst = 0;
    i64 wi = 0, wq = 0;
    long double sum2 = 0;
    std::vector<std::thread> th;
    for (unsigned t = 0; t < nt; t++)
        th.emplace_back([&] {
            double w = 0; i64 bi = 0, bq = 0; long double s2 = 0;
            for (int i; (i = next++) <= 32767;)
                for (i64 q = -32768; q <= 32767; q++) {
                    if (i == 0 && q == 0) continue;
                    i64 x, y;
                    model.run(i, q, x, y);
                    double e = err(i, q, x, y, s2);
                    if (e > w) { w = e; bi = i; bq = q; }
                }
            std::lock_guard<std::mutex> g(mu);
            sum2 += s2;
            if (w > worst) { worst = w; wi = bi; wq = bq; }
        });
    for (auto &t : th) t.join();
    std::printf("worst %.4f LSB at (I,Q)=(%lld,%lld), rms %.4f LSB per component, 2^32-1 inputs\n",
                worst, (long long)wi, (long long)wq, double(std::sqrt(sum2 / (2 * (4294967296.0L - 1)))));
}

int main(int argc, char **argv) {
    std::string mode = argc > 1 ? argv[1] : "";
    if (mode == "a" && argc == 5) exhaustive(ModelA(atoi(argv[2]), atoi(argv[3]), atoi(argv[4])));
    else if (mode == "b" && argc == 4) exhaustive(ModelB(atoi(argv[2]), atoi(argv[3])));
    else if (mode == "vectors" && argc == 8) {
        ModelA a(atoi(argv[3]), atoi(argv[4]), atoi(argv[5]));
        ModelB b(atoi(argv[6]), atoi(argv[7]));
        std::ifstream in(argv[2]);
        std::string line;
        long n = 0, bad = 0;
        while (std::getline(in, line)) {
            if (line.empty() || line[0] == '#') continue;
            std::istringstream ss(line);
            i64 i, q, xa, ya, xb, yb, x, y;
            ss >> i >> q >> xa >> ya >> xb >> yb;
            a.run(i, q, x, y); bad += (x != xa || y != ya);
            b.run(i, q, x, y); bad += (x != xb || y != yb);
            n++;
        }
        std::printf("%ld vectors, %ld mismatches between C++ and Python models\n", n, bad);
        return bad != 0;
    } else {
        std::fprintf(stderr, "usage: exhaustive a A F R | b N G | vectors FILE A F R N G\n");
        return 2;
    }
}
