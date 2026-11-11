/* ps3recomp patch 0126: the SPU helpers of an x86-64 build without SSE4.1 (the SSE2 baseline, for processors before
 * Core 2 "Penryn" / AMD before Bulldozer) against the SSE4.1 build -- the same bits from both.
 *
 * One program cannot hold both forms (spu_helpers.h picks by __SSE4_1__), so this prints a digest of every result
 * over a fixed operand sequence and tests/test_sse2_baseline.py builds it twice (with and without -msse4.1) for each
 * float mode (exact, SPU_NEAR_FLOAT = the sound core, SPU_FAST_FLOAT = the skinning jobs) and compares the lines.
 * Operations: the six float ones (and under SPU_NEAR_FLOAT their known-clean forms, patch 0113, fed with results of
 * the plain ones), shufb, every byte shift / rotate, the generate-controls family, the fsm family.
 * In the baseline build the integer forms are also compared with the scalar _ref loops here (exit 1).
 *
 *     spu_sse2_cross_test [N]      prints "isa <sse41|sse2|scalar> ... digest <op> <hex>" lines
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "spu_context.h"
#include "spu_helpers.h"

static uint64_t s = 88172645463325252ull;
static uint32_t xr(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return (uint32_t)(s >> 11); }
static uint32_t pick(void) {
    static const uint32_t sp[] = {0, 0x80000000u, 1, 0x80000001u, 0x007FFFFFu, 0x807FFFFFu, 0x00800000u, 0x80800000u,
        0x7F7FFFFFu, 0xFF7FFFFFu, 0x7F800000u, 0xFF800000u, 0x7FC00000u, 0x7FFFFFFFu, 0xFFFFFFFFu, 0x3F800000u, 0xBF800000u,
        0x00000010u, 0x01000000u, 0x81000000u, 0x7E800000u, 0x0C800000u, 0x8C800000u, 0x3F7FFFFFu, 0x3F800001u, 0x4B800000u};
    uint32_t r = xr();
    switch (r & 7) {
    case 0: return sp[(r >> 3) % (sizeof sp / 4)];
    case 1: return (r & 0x807FFFFFu) | ((uint32_t)((r >> 23) & 3) << 23);           /* tiny exponents */
    case 2: return (r & 0x807FFFFFu) | ((uint32_t)(252 + ((r >> 23) & 3)) << 23);   /* huge */
    case 3: case 4: { uint32_t e = 100 + (xr() % 60); return (r & 0x807FFFFFu) | (e << 23); }
    default: return xr() ^ (xr() << 11);
    }
}
static u128 pick128(void) { u128 r; for (int k = 0; k < 4; k++) r._u32[k] = pick(); return r; }
static u128 rnd128(void) { u128 r; for (int k = 0; k < 4; k++) r._u32[k] = xr() ^ (xr() << 11); return r; }

enum { FA, FS, FM, FMA, FMS, FNMS, KFA, KFS, KFM, KFMA, KFMS, KFNMS, SHUFB, ROTQBY, SHLQBY, ROTQBYBI, SHLQBYBI, ROTQMBY,
       ROTQMBYBI, ROTQBYI, SHLQBYI, ROTQMBYI, CBD, CHD, CWD, CDD, CBX, CHX, CWX, CDX, FSMB, FSMH, FSM, NOPS };
static const char* const NAMES[NOPS] = {"fa", "fs", "fm", "fma", "fms", "fnms", "fa_k", "fs_k", "fm_k", "fma_k", "fms_k",
    "fnms_k", "shufb", "rotqby", "shlqby", "rotqbybi", "shlqbybi", "rotqmby", "rotqmbybi", "rotqbyi", "shlqbyi",
    "rotqmbyi", "cbd", "chd", "cwd", "cdd", "cbx", "chx", "cwx", "cdx", "fsmb", "fsmh", "fsm"};
static uint64_t dig[NOPS];
static long long fails;
static void put(int op, u128 v) {
    uint64_t h = dig[op] ? dig[op] : 1469598103934665603ull;
    for (int i = 0; i < 4; i++) { h ^= v._u32[i]; h *= 1099511628211ull; h ^= h >> 29; }
    dig[op] = h;
}
static void same(int op, u128 got, u128 want) {
    if (memcmp(&got, &want, 16) && fails++ < 10)
        printf("FAIL %s: got %08X %08X %08X %08X want %08X %08X %08X %08X\n", NAMES[op], got._u32[0], got._u32[1],
               got._u32[2], got._u32[3], want._u32[0], want._u32[1], want._u32[2], want._u32[3]);
}
#define INT2(OP, f, x, y)  do { const u128 v_ = f(x, y); put(OP, v_); same(OP, v_, f##_ref(x, y)); } while (0)

int main(int argc, char** argv) {
    const long long n = argc > 1 ? atoll(argv[1]) : 3000000;
    for (long long i = 0; i < n; i++) {
        u128 a = pick128(), b = pick128(), c = pick128();
        if ((i & 15) == 0) for (int k = 0; k < 4; k++) c._u32[k] = a._u32[k] ^ 0x80000000u, b._u32[k] = 0x3F800000u;
        if ((i & 15) == 1) for (int k = 0; k < 4; k++) b._u32[k] = a._u32[k] ^ 0x80000000u ^ (xr() & 3);   /* near cancel */
        const u128 r0 = spu_fa(a, b), r1 = spu_fs(a, b), r2 = spu_fm(a, b);
        put(FA, r0); put(FS, r1); put(FM, r2);
        put(FMA, spu_fma(a, b, c)); put(FMS, spu_fms(a, b, c)); put(FNMS, spu_fnms(a, b, c));
        /* the known-clean forms: an operand marked 1 must be a result of one of the six operations */
        put(KFA, spu_fa_k(r0, b, 1, 0)); put(KFA, spu_fa_k(a, r1, 0, 1)); put(KFA, spu_fa_k(r0, r2, 1, 1));
        put(KFS, spu_fs_k(r0, r1, 1, 1)); put(KFS, spu_fs_k(a, r2, 0, 1));
        put(KFM, spu_fm_k(r0, r1, 1, 1)); put(KFM, spu_fm_k(r2, b, 1, 0));
        put(KFMA, spu_fma_k(r0, r1, r2, 1, 1, 1)); put(KFMA, spu_fma_k(a, r1, c, 0, 1, 0));
        put(KFMS, spu_fms_k(r0, b, r2, 1, 0, 1)); put(KFNMS, spu_fnms_k(r2, r1, c, 1, 1, 0));

        /* integer forms: every count / position in the low bits, the high bits random or extreme */
        const u128 x = rnd128();
        u128 y = rnd128();
        const uint32_t lo = (uint32_t)(i & 0xFF);
        y._u32[0] = ((i >> 8) & 3) == 0 ? lo : ((i >> 8) & 3) == 1 ? lo | 0xFFFFFF00u : ((i >> 8) & 3) == 2 ? lo | 0x80000000u
                                                                                    : lo | (xr() << 8);
        const int imm = (int)(int8_t)(uint8_t)i;
        INT2(ROTQBY, spu_rotqby, x, y); INT2(SHLQBY, spu_shlqby, x, y); INT2(ROTQBYBI, spu_rotqbybi, x, y);
        INT2(SHLQBYBI, spu_shlqbybi, x, y); INT2(ROTQMBY, spu_rotqmby, x, y); INT2(ROTQMBYBI, spu_rotqmbybi, x, y);
        INT2(ROTQBYI, spu_rotqbyi, x, imm); INT2(SHLQBYI, spu_shlqbyi, x, imm); INT2(ROTQMBYI, spu_rotqmbyi, x, imm);
        u128 z = rnd128();
        INT2(CBD, spu_cbd, y, imm); INT2(CHD, spu_chd, y, imm); INT2(CWD, spu_cwd, y, imm); INT2(CDD, spu_cdd, y, imm);
        INT2(CBX, spu_cbx, y, z); INT2(CHX, spu_chx, y, z); INT2(CWX, spu_cwx, y, z); INT2(CDX, spu_cdx, y, z);
        const int mode = (int)(i % 6);
        for (int k = 0; k < 16; k++) {
            if (mode == 0) z._u8[k] &= 0x1F;
            else if (mode == 1) z._u8[k] = (uint8_t)((i + k * 17) & 0xFF);
            else if (mode == 2 && (xr() & 7)) z._u8[k] &= 0x7F;
        }
        if (mode >= 4) {          /* whole-word controls (the SSE2 form's fast path), and near misses of them */
            for (int w = 0; w < 4; w++) z._u32[w] = 0x00010203u + 0x04040404u * (xr() & 7);
            if (mode == 5) {
                const uint32_t q = xr();
                if (q & 1) z._u8[(q >> 1) & 15] ^= (uint8_t)(1u << ((q >> 5) & 7));
                else z._u32[(q >> 1) & 3] += 0x04040404u * ((q >> 3) & 15);
            }
        }
        if ((i & 63) == 5) z = spu_cwd(y, imm);         /* controls as the game makes them */
        if ((i & 63) == 6) z = spu_cdd(y, imm);
        if ((i & 63) == 7) z = spu_chd(y, imm);
        { const u128 v = spu_shufb(x, y, z); put(SHUFB, v); same(SHUFB, v, spu_shufb_ref(x, y, z)); }
        u128 m = rnd128();
        m._u32[0] = (uint32_t)(i & 0xFFFF) | ((i >> 16) & 1 ? (xr() << 16) : 0);
        { const u128 v = spu_fsmb(m); put(FSMB, v); same(FSMB, v, spu_fsmb_ref(m)); }
        { const u128 v = spu_fsmh(m); put(FSMH, v); same(FSMH, v, spu_fsmh_ref(m)); }
        { const u128 v = spu_fsm(m);  put(FSM, v);  same(FSM, v, spu_fsm_ref(m)); }
    }
#if defined(__SSE4_1__)
    const char* isa = "sse41";
#elif defined(SPU_X86_SSE2)
    const char* isa = "sse2";
#else
    const char* isa = "scalar";
#endif
#if defined(SPU_NEAR_FLOAT)
    const char* fl = "near";
#elif defined(SPU_FAST_FLOAT)
    const char* fl = "fast";
#else
    const char* fl = "exact";
#endif
    printf("isa %s float %s vectors %lld ref-failures %lld\n", isa, fl, n, fails);
    for (int op = 0; op < NOPS; op++) printf("digest %s %016llx\n", NAMES[op], (unsigned long long)dig[op]);
    return fails != 0;
}
