/* ps3recomp patch 0113: under SPU_NEAR_FLOAT the six float operations never give a denormal or a -0 lane -- the
 * fast path flushes both to +0, the exact path (taken for exponent-255 operands and results) makes neither. That is
 * what lets the SPU lifter's register promotion leave out the denormal flush of an operand that holds such a result
 * (spu_fa_k ..., tools/spu_regpromo.py "known-clean"). Built by tests/test_spu_regpromo.py with -msse4.1
 * -DSPU_NEAR_FLOAT against a patched ps3recomp tree; random and special operands, cancellations.
 *
 *     spu_clean_float_test N      exit 1 if any result lane is not clean
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "spu_context.h"
#include "spu_helpers.h"
static uint64_t s = 88172645463325252ull;
static uint32_t xr(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return (uint32_t)s; }
static uint32_t pick(void) {
    static const uint32_t sp[] = {0, 0x80000000u, 1, 0x80000001u, 0x007FFFFFu, 0x807FFFFFu, 0x00800000u, 0x80800000u,
        0x7F7FFFFFu, 0xFF7FFFFFu, 0x7F800000u, 0xFF800000u, 0x7FC00000u, 0x7FFFFFFFu, 0xFFFFFFFFu, 0x3F800000u, 0xBF800000u,
        0x00000010u, 0x01000000u, 0x81000000u, 0x7E800000u, 0x0C800000u, 0x8C800000u};
    uint32_t r = xr();
    switch (r & 7) {
    case 0: return sp[(r >> 3) % (sizeof sp / 4)];
    case 1: return (r & 0x807FFFFFu) | ((uint32_t)((r >> 23) & 3) << 23);           /* tiny exponents */
    case 2: return (r & 0x807FFFFFu) | ((uint32_t)(252 + ((r >> 23) & 3)) << 23);   /* huge */
    case 3: { uint32_t e = 100 + (xr() % 60); return (r & 0x807FFFFFu) | (e << 23); }
    default: return xr();
    }
}
static int clean(uint32_t x) { return x == 0 || (x & 0x7FFFFFFFu) >= 0x00800000u; }
int main(int argc, char** argv) {
    long long n = argc > 1 ? atoll(argv[1]) : 20000000, bad = 0, slow = 0;
    for (long long i = 0; i < n; i++) {
        u128 a, b, c;
        for (int k = 0; k < 4; k++) { a._u32[k] = pick(); b._u32[k] = pick(); c._u32[k] = pick(); }
        /* correlate lanes sometimes: c = -(a*b) style cancellation */
        if ((i & 15) == 0) for (int k = 0; k < 4; k++) c._u32[k] = a._u32[k] ^ 0x80000000u, b._u32[k] = 0x3F800000u;
        u128 r[6] = {spu_fa(a, b), spu_fs(a, b), spu_fm(a, b), spu_fma(a, b, c), spu_fms(a, b, c), spu_fnms(a, b, c)};
        for (int o = 0; o < 6; o++) for (int k = 0; k < 4; k++) if (!clean(r[o]._u32[k])) {
            if (bad++ < 10) printf("op %d lane %d -> %08x (a %08x b %08x c %08x)\n", o, k, r[o]._u32[k], a._u32[k], b._u32[k], c._u32[k]);
        }
        for (int k = 0; k < 4; k++) if ((r[0]._u32[k] & 0x7F800000u) == 0x7F800000u) { slow++; break; }
    }
    printf("%lld vectors x 6 ops: %lld unclean lanes, %lld vectors with an exponent-255 sum\n", n, bad, slow);
    return bad != 0;
}
