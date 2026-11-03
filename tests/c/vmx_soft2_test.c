/* Experimental patch 0104: actual VMX result vs pre-0104 scalar operation.
 * Compile against a prepared runtime, baseline x64, -ffp-contract=off,
 * -DPPU_VMX_SOFT2=1 and include runtime/ppu. No game data is used.
 * Old headers fail to compile: SIMD helper/implementation marker absent. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_vmx.h"
#ifndef PPU_VMX_SOFT2_IMPLEMENTED
#error "patch 0104 is required; do not report a scalar-only pass"
#endif
#if !PPU_VMX_SOFT2 || !defined(PPU_FP_X64) || defined(__FMA__)
#error "test needs PPU_VMX_SOFT2=1 and baseline x64 without FMA"
#endif
static uint32_t rng = 0x106120u;
static uint32_t next(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
static long checks;
static int vector(const uint32_t x[4], const uint32_t y[4], const uint32_t z[4])
{
    uint8_t a[16], b[16], c[16], want[16], actual[16];
    for (unsigned nj = 0; nj < 2; nj++) {
        uint32_t vscr = nj ? VMX_NJ : 0;
        for (int k = 0; k < 4; k++) {
            vmx_sw(a, k, x[k]); vmx_sw(b, k, y[k]); vmx_sw(c, k, z[k]);
            const float fx = vmx_f(vmx_flush(x[k], vscr));
            const float fy = vmx_f(vmx_flush(y[k], vscr));
            const float fz = vmx_f(vmx_flush(z[k], vscr));
            vmx_sw(want, k, vmx_flush(vmx_fix(vmx_u(ppu_fmaf_soft(fx, fz, fy))), vscr));
        }
        for (int alias = 0; alias < 4; alias++) {
            uint8_t aa[16], bb[16], cc[16];
            memcpy(aa, a, 16); memcpy(bb, b, 16); memcpy(cc, c, 16);
            void* dst = alias == 1 ? aa : alias == 2 ? bb : alias == 3 ? cc : actual;
            vmx_vmaddfp(dst, aa, bb, cc, vscr);
            checks++;
            if (memcmp(dst, want, 16)) {
                fprintf(stderr, "FAIL vector %ld NJ=%u alias=%d\n", checks, nj, alias);
                return 1;
            }
        }
    }
    return 0;
}
int main(void)
{
    const unsigned old = _mm_getcsr();
    _mm_setcsr(PPU_MXCSR_CANON);
    /* Signed zeros, both subnormal ends, normal boundary, ties/cancellation,
     * overflow, infinities, signalling/quiet NaNs and payloads, both signs. */
    static const uint32_t edge[] = {
        0, 0x80000000u, 1, 0x80000001u, 0x007fffffu, 0x807fffffu,
        0x00800000u, 0x80800000u, 0x3f000000u, 0xbf000000u,
        0x3f7fffffu, 0x3f800000u, 0x3f800001u, 0xbf800000u,
        0x3f800002u, 0xbf800002u, 0x33800000u, 0xb3800000u, 0x7f7fffffu, 0xff7fffffu,
        0x7f800000u, 0xff800000u, 0x7f800001u, 0xff800001u,
        0x7fc12345u, 0xffc12345u
    };
    const unsigned n = sizeof edge / sizeof edge[0];
    for (unsigned i = 0; i < n; i++) for (unsigned j = 0; j < n; j++) for (unsigned k = 0; k < n; k++) {
        uint32_t x[4], y[4], z[4];
        for (unsigned lane = 0; lane < 4; lane++) {
            x[lane] = edge[(i + lane) % n]; y[lane] = edge[(j + 3 * lane) % n];
            z[lane] = edge[(k + 7 * lane) % n];
        }
        if (vector(x, y, z)) { _mm_setcsr(old); return 1; }
    }
    for (unsigned i = 0; i < 500000; i++) {
        uint32_t x[4], y[4], z[4]; float fx[2], fy[2], fz[2], out[2];
        for (unsigned lane = 0; lane < 4; lane++) {
            x[lane] = next(); y[lane] = next(); z[lane] = next();
        }
        if (vector(x, y, z)) { _mm_setcsr(old); return 1; }
        /* Exercise new helper directly: a vacuous unchanged scalar VMX path
         * cannot satisfy this test. Keep arbitrary signs and finite exponents. */
        for (unsigned lane = 0; lane < 2; lane++) {
            fx[lane] = vmx_f(next() & 0xfeffffffu);
            fy[lane] = vmx_f(next() & 0xfeffffffu);
            fz[lane] = vmx_f(next() & 0xfeffffffu);
        }
        ppu_fmaf_soft2_finite(out, fx, fy, fz);
        for (unsigned lane = 0; lane < 2; lane++) {
            const float want = ppu_fmaf_soft(fx[lane], fy[lane], fz[lane]);
            if (vmx_u(out[lane]) != vmx_u(want)) {
                fprintf(stderr, "FAIL finite helper at %u lane %u\n", i, lane);
                _mm_setcsr(old); return 1;
            }
        }
    }
    _mm_setcsr(old);
    printf("PASS %ld VMX vectors, 1000000 direct finite lanes, exact bits\n", checks);
    return 0;
}
