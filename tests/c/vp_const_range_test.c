/* Patch 0123: rsx_vp_const_mask / rsx_vp_const_range (libs/video/rsx_vp_decompiler.c) against the
 * decompiler itself.
 *
 * A draw now copies only the transform constants its vertex program can read. The oracle is what
 * the GPU runs: the HLSL rsx_vp_decompile makes of the program. For random programs (every source
 * field often a constant, random opcodes, index bits, swizzles) every vp_c[N] the HLSL reads must be
 * in the mask, an indexed vp_c[(...)] only appears with all 512 set, and the range is the mask's
 * first and last constant. A narrowed analysis (one that forgets source 2, or the index bit) must be
 * caught by the same oracle on the same programs. Built by tests/test_perf_123.py; the runtime file
 * is included as it is. */
#include "rsx_vp_decompiler.c"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long long rng = 0x9E3779B97F4A7C15ull;
static u32 rnd(void)
{
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return (u32)(rng >> 16);
}
static void wr_le(u8* p, u32 v) { p[0] = (u8)v; p[1] = (u8)(v >> 8); p[2] = (u8)(v >> 16); p[3] = (u8)(v >> 24); }

/* the mutants: 1 = source 2 forgotten, 2 = the index bit ignored */
static void mask_mutant(const u8* uc, u32 max_bytes, u64 m[8], int mutant)
{
    for (int k = 0; k < 8; k++) m[k] = 0;
    for (u32 off = 0; off + 16 <= max_bytes; off += 16) {
        const u32 d1 = rd_le(uc + off + 4), d2 = rd_le(uc + off + 8), d3 = rd_le(uc + off + 12);
        const u32 s0 = ((d2 >> 23) & 0x1FF) | ((d1 & 0xFF) << 9), s1 = (d2 >> 6) & 0x1FFFF;
        const u32 s2 = ((d3 >> 21) & 0x7FF) | ((d2 & 0x3F) << 11);
        if ((s0 & 3u) == 3u || (s1 & 3u) == 3u || (mutant != 1 && (s2 & 3u) == 3u)) {
            if (mutant != 2 && ((d3 >> 1) & 1u)) break;
            const u32 c = ((d1 >> 12) & 0x3FFu) & 511u;
            m[c >> 6] |= 1ull << (c & 63);
        }
        if (d3 & 1u) return;
    }
    for (int k = 0; k < 8; k++) m[k] = ~0ull;
}

/* reads of vp_c in the HLSL the mask does not hold (an indexed read counts unless all 512 are set) */
static int outside(const char* hlsl, const u64 m[8], int* reads)
{
    int n = 0, all = 1;
    for (int k = 0; k < 8; k++) all &= m[k] == ~0ull;
    const char* scan = strstr(hlsl, "float4 vp_c[512];");
    scan = scan ? scan + 17 : hlsl;
    for (const char* p = strstr(scan, "vp_c["); p; p = strstr(p + 5, "vp_c[")) {
        (*reads)++;
        const char* q = p + 5;
        if (*q == '(') { if (!all) n++; continue; }
        const unsigned long c = strtoul(q, NULL, 10);
        if (c >= 512 || !(m[c >> 6] >> (c & 63) & 1u)) n++;
    }
    return n;
}

static char hlsl[1 << 20];

int main(void)
{
    const int programs = 20000;
    long checks = 0, reads = 0, bad = 0, decompiled = 0, narrowed = 0, caught[3] = {0, 0, 0};
    u8 uc[64 * 16];
    for (int t = 0; t < programs; t++) {
        const u32 n = 1 + rnd() % 24;
        for (u32 i = 0; i < n; i++) {
            u32 d0 = rnd(), d1 = rnd(), d2 = rnd(), d3 = rnd();
            /* mostly real opcodes: vector 0x00..0x19, scalar 0x00..0x10 */
            d1 = (d1 & ~(0x3FFu << 22)) | ((rnd() % 0x1A) << 22) | ((rnd() % 0x11) << 27);
            /* source register types: constants often (3), temps, inputs */
            u32 s0 = ((d2 >> 23) & 0x1FF) | ((d1 & 0xFF) << 9), s1 = (d2 >> 6) & 0x1FFFF;
            u32 s2 = ((d3 >> 21) & 0x7FF) | ((d2 & 0x3F) << 11);
            s0 = (s0 & ~3u) | (rnd() % 4 ? 3u : rnd() % 3); s1 = (s1 & ~3u) | (rnd() % 3 ? 3u : 1u);
            s2 = (s2 & ~3u) | (rnd() % 3 ? 3u : 2u);
            d1 = (d1 & ~0xFFu) | (s0 >> 9);
            d2 = (d2 & ~(0x1FFu << 23)) | ((s0 & 0x1FF) << 23);
            d2 = (d2 & ~(0x1FFFFu << 6)) | (s1 << 6);
            d2 = (d2 & ~0x3Fu) | (s2 >> 11);
            d3 = (d3 & ~(0x7FFu << 21)) | ((s2 & 0x7FF) << 21);
            if (rnd() % 8) d3 &= ~2u;                 /* indexed constants now and then */
            d3 = (d3 & ~1u) | (i + 1 == n ? 1u : 0u); /* the end bit on the last */
            wr_le(uc + i * 16, d0); wr_le(uc + i * 16 + 4, d1); wr_le(uc + i * 16 + 8, d2); wr_le(uc + i * 16 + 12, d3);
        }
        u64 mask[8];
        u32 lo = 0, hi = 0;
        const int exact = rsx_vp_const_mask(uc, n * 16, mask);
        if (exact) narrowed++;
        /* the range is the mask's first and last constant */
        if (rsx_vp_const_range(uc, n * 16, &lo, &hi) != exact) bad++;
        for (u32 c = 0; c < 512; c++)
            if ((mask[c >> 6] >> (c & 63) & 1u) && (lo > hi || c < lo || c > hi)) { bad++; break; }
        if (rsx_vp_decompile(uc, n * 16, hlsl, sizeof hlsl) < 0) continue;
        decompiled++;
        int r = 0;
        const int o = outside(hlsl, mask, &r);
        reads += r; checks++;
        if (o && bad++ < 5) printf("FAIL program %d: %d read(s) outside the mask\n", t, o);
        for (int m = 1; m <= 2; m++) {
            u64 mm[8]; int rr = 0;
            mask_mutant(uc, n * 16, mm, m);
            if (outside(hlsl, mm, &rr)) caught[m]++;
        }
    }
    /* hand-made: MOV o0, c[37] and the same read indexed */
    {
        memset(uc, 0, sizeof uc);
        const u32 src0 = 3u | (0xE4u << 8);           /* constant, swizzle */
        const u32 d1 = (0x01u << 22) | (37u << 12) | (src0 >> 9);
        const u32 d2 = (src0 & 0x1FF) << 23;
        const u32 d3 = (0xFu << 13) | 1u;             /* vector write mask, end */
        wr_le(uc + 4, d1); wr_le(uc + 8, d2); wr_le(uc + 12, d3);
        u32 lo, hi;
        const int ex = rsx_vp_const_range(uc, 16, &lo, &hi);
        printf("MOV c[37]: exact %d range %u..%u\n", ex, lo, hi);
        if (!ex || lo != 37 || hi != 37) bad++;
        wr_le(uc + 12, d3 | 2u);
        rsx_vp_const_range(uc, 16, &lo, &hi);
        printf("indexed: range %u..%u\n", lo, hi);
        if (lo != 0 || hi != 511) bad++;
    }
    printf("%ld programs decompiled, %ld with a narrowed mask, %ld constant reads checked, %ld wrong\n",
           decompiled, narrowed, reads, bad);
    printf("mutants caught: forgetting source 2 in %ld programs, ignoring the index bit in %ld\n", caught[1], caught[2]);
    if (bad || !caught[1] || !caught[2] || narrowed < programs / 20 || reads < programs) {
        printf("FAILED\n");
        return 1;
    }
    printf("PASS %ld checks\n", checks);
    return 0;
}
