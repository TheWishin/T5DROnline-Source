/* ppu_fma_soft (runtime/ppu/ppu_fp_det.h): the exact software fused multiply-add a PC without FMA3 runs for
 * every fmadd of the game (ps3recomp patch 0084 adds a double-only path for the common case; docs/RENDER_PERF.md
 * "1.1.7: 2-core PCs and GitHub #12").
 *
 *   fma_soft_test check N   N random cases against vfmadd (needs a CPU with FMA3): prints "differ D", exit 1 if any
 *   fma_soft_test bench     ns per call over a fixed set of ordinary operands: prints "ns X"
 *
 * Built by tests/test_weak_cpu_117.py for the x86-64 baseline (no -mfma), so the header's software path is the
 * one under test; with -DPPU_FMA_SOFT_INT_ONLY the integer path alone (the speed comparison). */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <immintrin.h>
#include <windows.h>
#include "ppu_fp_det.h"

void ppu_fp_thread_init(const char* w) { (void)w; }
void ppu_fp_env_fix(uint32_t s, const char* w) { (void)s; (void)w; }
uint32_t ppu_fp_env_violations(void) { return 0; }

static uint64_t st = 0x9E3779B97F4A7C15ull;
static uint64_t rnd(void) { st ^= st << 13; st ^= st >> 7; st ^= st << 17; return st; }
__attribute__((target("fma"))) static double ref_fma(double a, double b, double c)
{ return _mm_cvtsd_f64(_mm_fmadd_sd(_mm_set_sd(a), _mm_set_sd(b), _mm_set_sd(c))); }
static double d_of(uint64_t u) { double d; memcpy(&d, &u, 8); return d; }
static uint64_t u_of(double d) { uint64_t u; memcpy(&u, &d, 8); return u; }
/* exponent e0 +- spread; short significands (ties, exact results), runs of ones, single bits */
static double gd(int e0, int spread)
{
    uint64_t r = rnd();
    int e = e0 + (int)(rnd() % (uint64_t)(2 * spread + 1)) - spread;
    if (e < 0) e = 0;
    if (e > 2046) e = 2046;
    switch (rnd() & 7) {
    case 0: r &= ~((1ull << (rnd() % 53)) - 1); break;
    case 1: r |= (1ull << (rnd() % 52)) - 1; break;
    case 2: r = (r & 0x8000000000000000ull) | (1ull << (rnd() % 52)) | (rnd() & 1); break;
    default: break;
    }
    return d_of((r & 0x800FFFFFFFFFFFFFull) | ((uint64_t)e << 52));
}

int main(int argc, char** argv)
{
    if (argc > 1 && !strcmp(argv[1], "check")) {
        const long n = argc > 2 ? atol(argv[2]) : 20000000L;
        long bad = 0;
        for (long i = 0; i < n; i++) {
            double a, b, c;
            switch (i % 8) {
            case 0: a = gd(1023, 450); b = gd(1023, 450); c = gd(1023, 900); break;           /* the double-only window */
            case 1: a = gd(1023, 30); b = gd(1023, 30); c = gd(1023, 70); break;
            case 2: a = gd(1023, 400); b = gd(1023, 400); c = d_of(u_of(-(a * b)) + (rnd() % 7) - 3); break;  /* cancellation */
            case 3: { a = gd(1023, 5); b = gd(1023, 5);                                     /* c near half an ulp of a*b */
                      const double h = d_of(u_of(a * b) & 0xFFF0000000000000ull) * 0x1p-53;
                      c = (rnd() & 1 ? h : -h) * (double)(1 + (rnd() % 3)); break; }
            case 4: a = gd(573 + (int)(rnd() % 3), 1); b = gd(1473 - (int)(rnd() % 3), 1);   /* the window's edges */
                    c = gd(122 + (int)(rnd() % 1803), 0); break;
            case 5: a = gd(1023 - 440, 15); b = gd(1023 - 440, 15); c = gd(1023 - 880, 25); break;  /* small results */
            case 6: a = gd(1023, 1023); b = gd(1023, 1023); c = gd(1023, 1023); break;       /* anything finite */
            default: a = d_of(rnd()); b = d_of(rnd()); c = d_of(rnd()); break;               /* any bits */
            }
            const uint64_t r0 = u_of(ref_fma(a, b, c)), r1 = u_of(ppu_fma_soft(a, b, c));
            const int nan = (r0 & 0x7FFFFFFFFFFFFFFFull) > 0x7FF0000000000000ull &&
                            (r1 & 0x7FFFFFFFFFFFFFFFull) > 0x7FF0000000000000ull;
            if (r0 != r1 && !nan && bad++ < 5)
                printf("fma_soft(%a, %a, %a) = %a, vfmadd %a\n", a, b, c, d_of(r1), d_of(r0));
        }
        printf("differ %ld of %ld\n", bad, n);
        return bad != 0;
    }
    /* bench: ordinary operands (what game code multiplies), the calls in a dependent chain */
    enum { M = 1 << 14 };
    static double A[M], B[M], C[M];
    for (int i = 0; i < M; i++) { A[i] = gd(1023, 12); B[i] = gd(1023, 12); C[i] = gd(1023, 16); }
    LARGE_INTEGER f, t0, t1;
    QueryPerformanceFrequency(&f);
    double best = 1e9, s = 0.0;
    for (int rep = 0; rep < 5; rep++) {
        QueryPerformanceCounter(&t0);
        for (int k = 0; k < 100; k++)
            for (int i = 0; i < M; i++) s += ppu_fma_soft(A[i], B[i], C[i]);
        QueryPerformanceCounter(&t1);
        const double ns = (double)(t1.QuadPart - t0.QuadPart) / (double)f.QuadPart * 1e9 / (100.0 * M);
        if (ns < best) best = ns;
    }
    printf("ns %.3f (sum %g)\n", best, s);
    return 0;
}
