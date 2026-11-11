/* Patch 0127: rsx_fp_texture_mask (libs/video/rsx_fp_decompiler.c) against the decompiler itself.
 *
 * Patch 0081's tier-1 binding path binds only the texture units a fragment program samples; a unit
 * outside the mask keeps the white texture and the default sampler. The
 * oracle is what the GPU runs: the HLSL rsx_fp_decompile_ex makes of the program. For random
 * programs (texture ops on random units, inline constants after any source of type CONST, random
 * cube masks) no texture of a unit outside the mask may be named in the HLSL, except in its own
 * declaration. Two narrowed analyses must be caught by the same oracle on the same programs: one
 * that forgets TXB/TXL, one that does not step over inline constants. Built by tests/test_perf_019.py;
 * the runtime file is included as it is. */
#include "rsx_fp_decompiler.c"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned long long rng = 0x2545F4914F6CDD1Dull;
static u32 rnd(void)
{
    rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
    return (u32)(rng >> 16);
}
/* the decompiler reads half-word swapped big-endian words (rsx_fp_read_word) */
static void wr(u8* p, u32 v)
{
    const u32 be = (v << 16) | (v >> 16);
    p[0] = (u8)(be >> 24); p[1] = (u8)(be >> 16); p[2] = (u8)(be >> 8); p[3] = (u8)be;
}

/* mutants: 1 = TXB/TXL forgotten, 2 = inline constants not stepped over */
static u32 mask_mutant(const u8* uc, u32 max_bytes, int mutant)
{
    u32 off = 0, mask = 0;
    while (off + 16 <= max_bytes) {
        const u32 w0 = rsx_fp_read_word(uc + off), w1 = rsx_fp_read_word(uc + off + 4);
        const u32 w2 = rsx_fp_read_word(uc + off + 8), w3 = rsx_fp_read_word(uc + off + 12);
        off += 16;
        const u32 op = (w0 & FP_OPCODE_MASK) >> FP_OPCODE_SHIFT;
        if (op == OP_TEX || op == OP_TXP || op == OP_TXD || (mutant != 1 && (op == OP_TXL || op == OP_TXB)))
            mask |= 1u << ((w0 & FP_TEX_UNIT_MASK) >> FP_TEX_UNIT_SHIFT);
        if (mutant != 2 && ((w1 & 3u) == FP_REG_TYPE_CONST || (w2 & 3u) == FP_REG_TYPE_CONST ||
                            (w3 & 3u) == FP_REG_TYPE_CONST) && off + 16 <= max_bytes)
            off += 16;
        if (w0 & FP_END) break;
    }
    return mask;
}

/* units outside mask the HLSL names (not counting a declaration "rsx_texN : register") */
static u32 outside(const char* hlsl, u32 mask)
{
    u32 o = 0;
    for (u32 u = 0; u < 16; u++) {
        if ((mask >> u) & 1u) continue;
        char arr[24], one[24];
        snprintf(arr, sizeof arr, "rsx_tex[%u]", u);
        snprintf(one, sizeof one, "rsx_tex%u", u);
        if (strstr(hlsl, arr)) o |= 1u << u;
        const size_t n = strlen(one);
        for (const char* p = strstr(hlsl, one); p; p = strstr(p + 1, one)) {
            if (p[n] >= '0' && p[n] <= '9') continue;
            if (!strncmp(p + n, " : register", 11)) continue;
            o |= 1u << u;
            break;
        }
    }
    return o;
}

static char hlsl[1 << 20];

int main(void)
{
    static const u32 ops[] = { OP_MOV, OP_MUL, OP_ADD, OP_MAD, OP_DP3, OP_DP4, OP_MIN, OP_MAX, OP_FRC,
                               OP_RCP, OP_RSQ, OP_EX2, OP_LG2, OP_LRP, OP_DDX, OP_DDY, OP_KIL, OP_NRM,
                               OP_TEX, OP_TEX, OP_TEX, OP_TXP, OP_TXP, OP_TXD, OP_TXL, OP_TXL, OP_TXB, OP_TXB };
    const int programs = 30000;
    long checks = 0, decompiled = 0, sampled = 0, bad = 0, caught[3] = {0, 0, 0}, narrowed[3] = {0, 0, 0};
    u8 uc[96 * 16];
    for (int t = 0; t < programs; t++) {
        const u32 n = 1 + rnd() % 32;
        u32 off = 0;
        for (u32 i = 0; i < n && off + 32 <= sizeof uc; i++) {
            const u32 op = ops[rnd() % (sizeof ops / sizeof ops[0])];
            u32 w0 = rnd() & ~(FP_OPCODE_MASK | FP_TEX_UNIT_MASK | FP_END | FP_OUT_NONE);
            w0 |= op << FP_OPCODE_SHIFT;
            w0 |= (rnd() % 16) << FP_TEX_UNIT_SHIFT;
            w0 = (w0 & ~FP_OUT_REG_MASK) | ((rnd() % 4) << FP_OUT_REG_SHIFT);
            if (i + 1 == n) w0 |= FP_END;
            u32 w1 = rnd(), w2 = rnd() & ~FP_BRANCH, w3 = rnd();
            /* unconditional mostly; source types: temps, inputs, constants often */
            if (rnd() % 4) w1 |= FP_EXEC_IF_LT | FP_EXEC_IF_EQ | FP_EXEC_IF_GR;
            w1 = (w1 & ~3u) | (rnd() % 3 ? (rnd() % 2) : FP_REG_TYPE_CONST);
            w2 = (w2 & ~3u) | (rnd() % 4 ? FP_REG_TYPE_TEMP : FP_REG_TYPE_CONST);
            w3 = (w3 & ~3u) | (rnd() % 5 ? FP_REG_TYPE_TEMP : FP_REG_TYPE_CONST);
            wr(uc + off, w0); wr(uc + off + 4, w1); wr(uc + off + 8, w2); wr(uc + off + 12, w3);
            off += 16;
            if ((w1 & 3u) == FP_REG_TYPE_CONST || (w2 & 3u) == FP_REG_TYPE_CONST || (w3 & 3u) == FP_REG_TYPE_CONST) {
                /* an inline constant: random words, which may look like a texture op themselves */
                for (int k = 0; k < 4; k++) wr(uc + off + 4 * k, rnd() % 3 ? 0x3F800000u : rnd());
                off += 16;
            }
        }
        const u32 cube = (rnd() % 4 == 0) ? (rnd() & 0xFFFFu) : 0u;
        const u32 mask = rsx_fp_texture_mask(uc, off);
        if (rsx_fp_decompile_ex(uc, off, 0, cube, hlsl, sizeof hlsl) <= 0) continue;
        decompiled++;
        checks++;
        if (mask) sampled++;
        if (outside(hlsl, mask)) {
            bad++;
            if (bad <= 5) printf("WRONG program %d: mask 0x%04X, read outside 0x%04X\n", t, mask, outside(hlsl, mask));
        }
        for (int m = 1; m <= 2; m++) {
            const u32 mm = mask_mutant(uc, off, m);
            if (mm != mask) narrowed[m]++;
            if (outside(hlsl, mm)) caught[m]++;
        }
    }
    printf("programs %d decompiled %ld with a texture %ld\n", programs, decompiled, sampled);
    printf("mutant TXB/TXL forgotten: differs %ld caught %ld\n", narrowed[1], caught[1]);
    printf("mutant inline constants not skipped: differs %ld caught %ld\n", narrowed[2], caught[2]);
    if (bad || decompiled < programs / 2 || caught[1] == 0 || caught[2] == 0) {
        printf("FAIL %ld wrong\n", bad);
        return 1;
    }
    printf("PASS %ld checks\n", checks);
    return 0;
}
