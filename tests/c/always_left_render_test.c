/*
 * Unit test of "Always left" in the renderer (ps3recomp patch 0086, libs/video/rsx_always_left.h; docs/NETPLAY.md
 * "Always left"):
 *
 *   al_vp_eval        a vertex program run on the CPU gives what its shader gives: the HUD's kind of program
 *                     (position = attribute 0 through constants 256/257/259/467, times w; TEX0 = a constant),
 *                     a pass-through, a matrix (DP4), the legacy multiply (0 * INF = 0), and 0 for what it does
 *                     not model (branches, indexed constants, conditional writes, no end bit).
 *   al_hud_place      every draw of one side of the top HUD band (bar frame, both fill layers at any length,
 *                     plates, each glyph of a name) moves by half the width, so a side arrives whole, glyphs in
 *                     order, fills inside their own frames (issue #31); the timer and everything below the band
 *                     (centre titles, intro text, REPLAY) stay; a both-sides batch stays whole. Stateless: the
 *                     same answer on every frame, the first mirrored one included. The HUD shapes are the
 *                     game's as measured (docs/ALWAYS_LEFT_FIX.md), typed in here as numbers.
 *   al_hud_clip       diagnostics can distinguish a centred raw quad from its side-clipped visible fill.
 *
 * The programs are written for this test (the decompiler's encoding, rsx_vp_decompiler.c), not taken from the
 * game. With -DAL_WITH_DECOMPILER (a ps3recomp tree on the include path) the HUD program is also run through
 * rsx_vp_decompiler.c, which must read the same instructions out of the words (the encoder here is right).
 *
 *   always_left_render_test   prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * Built by tests/test_always_left.py with clang-cl or cl; rsx_always_left.h is taken from patch 0086 itself.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#ifdef AL_WITH_DECOMPILER
#include "rsx_vp_decompiler.c"
#endif
#include "rsx_always_left.h"

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); \
        }                                                                       \
    } while (0)

/* ------------------------------------------------------------------ an NV40 vertex program encoder */

enum { T_TEMP = 1, T_IN = 2, T_CONST = 3 };
/* a 17-bit source: type, temp index, swizzle "xyzw" letters, negate */
static uint32_t src(int type, int tmp, const char* swz, int neg)
{
    uint32_t s = (uint32_t)type | ((uint32_t)tmp << 2);
    const int sh[4] = { 14, 12, 10, 8 };
    for (int k = 0; k < 4; k++) {
        const char c = swz[k];
        const uint32_t v = c == 'x' ? 0u : c == 'y' ? 1u : c == 'z' ? 2u : 3u;
        s |= v << sh[k];
    }
    if (neg) s |= 1u << 16;
    return s;
}

typedef struct {
    uint32_t vec_op, sca_op, s0, s1, s2, input, cnst;
    uint32_t dst_tmp;       /* 0x3F = none */
    uint32_t dst_out;       /* 0x1F = none */
    uint32_t sca_tmp;       /* 0x3F = none */
    const char* vmask;      /* "xyzw" subset */
    const char* smask;
    int vec_result, end, index_const, cond_test, cond, saturate;
} ins_t;

static int has(const char* m, char c) { return m && strchr(m, c) != NULL; }

static void put_le(uint8_t* p, uint32_t w) { p[0] = (uint8_t)w; p[1] = (uint8_t)(w >> 8); p[2] = (uint8_t)(w >> 16); p[3] = (uint8_t)(w >> 24); }

static void encode(uint8_t* out, const ins_t* i)
{
    uint32_t d0 = 0, d1 = 0, d2 = 0, d3 = 0;
    d0 |= (i->dst_tmp & 0x3Fu) << 15;
    d0 |= (uint32_t)(i->saturate & 1) << 26;
    d0 |= (uint32_t)(i->vec_result & 1) << 30;
    d0 |= (uint32_t)(i->cond_test & 1) << 13;
    d0 |= ((uint32_t)i->cond & 7u) << 10;
    d1 |= (i->s0 >> 9) & 0xFFu;
    d1 |= (i->input & 0xFu) << 8;
    d1 |= (i->cnst & 0x3FFu) << 12;
    d1 |= (i->vec_op & 0x1Fu) << 22;
    d1 |= (i->sca_op & 0x1Fu) << 27;
    d2 |= (i->s2 >> 11) & 0x3Fu;
    d2 |= (i->s1 & 0x1FFFFu) << 6;
    d2 |= (i->s0 & 0x1FFu) << 23;
    d3 |= (uint32_t)(i->end & 1);
    d3 |= (uint32_t)(i->index_const & 1) << 1;
    d3 |= (i->dst_out & 0x1Fu) << 2;
    d3 |= (i->sca_tmp & 0x3Fu) << 7;
    d3 |= (uint32_t)has(i->vmask, 'w') << 13 | (uint32_t)has(i->vmask, 'z') << 14 |
          (uint32_t)has(i->vmask, 'y') << 15 | (uint32_t)has(i->vmask, 'x') << 16;
    d3 |= (uint32_t)has(i->smask, 'w') << 17 | (uint32_t)has(i->smask, 'z') << 18 |
          (uint32_t)has(i->smask, 'y') << 19 | (uint32_t)has(i->smask, 'x') << 20;
    d3 |= (i->s2 & 0x7FFu) << 21;
    put_le(out, d0); put_le(out + 4, d1); put_le(out + 8, d2); put_le(out + 12, d3);
}

static uint32_t f2u(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static void setc(uint32_t c[512][4], int i, float x, float y, float z, float w)
{
    c[i][0] = f2u(x); c[i][1] = f2u(y); c[i][2] = f2u(z); c[i][3] = f2u(w);
}
static int near(float a, float b) { return fabsf(a - b) <= 1e-4f * (1.0f + fabsf(b)); }

#define NOV 0x3Fu
#define NOO 0x1Fu
static const ins_t Z = { 0, 0, 0, 0, 0, 0, 0, NOV, NOO, NOV, "", "", 0, 0, 0, 0, 0, 0 };

static uint32_t C[512][4];

/* The HUD's kind of program, re-created:
 *   o7 = c466; r0 = v0.yyyy * c257; r1 = v0.xxxx * c256 + r0; r0.x = 1 / c465.x; r1 = r1 + c259;
 *   r0.y = 1 / c465.y; r1 = r1 + c467.xxxx; o8.xy = v8.xy * r0.xy; o0.xy = r1.xy * r1.w; o0.zw = r1.zw */
static int hud_program(uint8_t* uc)
{
    ins_t p[10];
    for (int k = 0; k < 10; k++) p[k] = Z;
    p[0].vec_op = 1; p[0].cnst = 466; p[0].s0 = src(T_CONST, 0, "xyzw", 0); p[0].vec_result = 1; p[0].dst_out = 7;
    p[0].vmask = "xyzw";
    p[1].vec_op = 2; p[1].input = 0; p[1].cnst = 257; p[1].s0 = src(T_IN, 0, "yyyy", 0);
    p[1].s1 = src(T_CONST, 0, "xyzw", 0); p[1].dst_tmp = 0; p[1].vmask = "xyzw";
    p[2].vec_op = 4; p[2].input = 0; p[2].cnst = 256; p[2].s0 = src(T_IN, 0, "xxxx", 0);
    p[2].s1 = src(T_CONST, 0, "xyzw", 0); p[2].s2 = src(T_TEMP, 0, "xyzw", 0); p[2].dst_tmp = 1; p[2].vmask = "xyzw";
    p[3].sca_op = 2; p[3].cnst = 465; p[3].s2 = src(T_CONST, 0, "xxxx", 0); p[3].sca_tmp = 0; p[3].smask = "x";
    p[4].vec_op = 3; p[4].cnst = 259; p[4].s0 = src(T_TEMP, 1, "xyzw", 0); p[4].s2 = src(T_CONST, 0, "xyzw", 0);
    p[4].dst_tmp = 1; p[4].vmask = "xyzw";
    p[5].sca_op = 2; p[5].cnst = 465; p[5].s2 = src(T_CONST, 0, "yyyy", 0); p[5].sca_tmp = 0; p[5].smask = "y";
    p[6].vec_op = 3; p[6].cnst = 467; p[6].s0 = src(T_TEMP, 1, "xyzw", 0); p[6].s2 = src(T_CONST, 0, "xxxx", 0);
    p[6].dst_tmp = 1; p[6].vmask = "xyzw";
    p[7].vec_op = 2; p[7].input = 8; p[7].s0 = src(T_IN, 0, "xyxx", 0); p[7].s1 = src(T_TEMP, 0, "xyxx", 0);
    p[7].vec_result = 1; p[7].dst_out = 8; p[7].vmask = "xy";
    p[8].vec_op = 2; p[8].s0 = src(T_TEMP, 1, "xyxx", 0); p[8].s1 = src(T_TEMP, 1, "wwww", 0);
    p[8].vec_result = 1; p[8].dst_out = 0; p[8].vmask = "xy";
    p[9].vec_op = 1; p[9].s0 = src(T_TEMP, 1, "zzzw", 0); p[9].vec_result = 1; p[9].dst_out = 0; p[9].vmask = "zw";
    p[9].end = 1;
    for (int k = 0; k < 10; k++) encode(uc + 16 * k, &p[k]);
    return 10 * 16;
}

static void test_vp(void)
{
    uint8_t uc[16 * 16];
    float in[16][4], o[16][4];
    memset(in, 0, sizeof in);
    for (int i = 0; i < 16; i++) in[i][3] = 1.0f;

    /* the HUD's kind: a 2D position in pixels mapped to -1..1 */
    memset(C, 0, sizeof C);
    setc(C, 256, 1.0f / 640.0f, 0, 0, 0);
    setc(C, 257, 0, -1.0f / 360.0f, 0, 0);
    setc(C, 259, -1.0f, 1.0f, 0.5f, 0.0f);
    setc(C, 467, 1.0f, 0, 0, 0);             /* .x added to all four: w = 1, x + 1 - 1 */
    setc(C, 465, 512.0f, 544.0f, 0, 0);
    setc(C, 466, 0.25f, 0.5f, 0.75f, 1.0f);
    const int n = hud_program(uc);
    in[0][0] = 1000.0f; in[0][1] = 40.0f;
    in[8][0] = 256.0f; in[8][1] = 272.0f;
    CHECK(al_vp_eval(uc, (uint32_t)n, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 1, "HUD program runs");
    /* r1 = (1000/640 - 1 + 1, -40/360 + 1 + 1, 0.5 + 1, 0 + 1) */
    const float rx = 1000.0f / 640.0f - 1.0f + 1.0f, ry = -40.0f / 360.0f + 1.0f + 1.0f, rz = 1.5f, rw = 1.0f;
    CHECK(near(o[0][0], rx * rw) && near(o[0][1], ry * rw), "o0.xy = r1.xy * r1.w: %f %f", o[0][0], o[0][1]);
    CHECK(near(o[0][2], rz) && near(o[0][3], rw), "o0.zw = r1.zw: %f %f", o[0][2], o[0][3]);
    CHECK(near(o[7][0], 0.25f) && near(o[7][3], 1.0f), "o7 = c466");
    CHECK(near(o[8][0], 0.5f) && near(o[8][1], 0.5f), "o8.xy = v8.xy / c465.xy: %f %f", o[8][0], o[8][1]);
    CHECK(near(o[1][3], 1.0f) && o[1][0] == 0.0f, "unwritten outputs are (0,0,0,1)");

#ifdef AL_WITH_DECOMPILER
    {
        static char hlsl[256 * 1024];
        rsx_vp_set_branch_base(0);
        CHECK(rsx_vp_decompile(uc, (uint32_t)n, hlsl, sizeof hlsl) > 0, "the decompiler reads the test program");
        CHECK(strstr(hlsl, "vp_mul(((v[0]).yyyy),((vp_c[257]).xyzw))") != NULL, "decompiler: MUL v0.yyyy c257");
        CHECK(strstr(hlsl, "vp_mul(((v[0]).xxxx),((vp_c[256]).xyzw))+((r[0]).xyzw)") != NULL, "decompiler: MAD");
        CHECK(strstr(hlsl, "(1.0/((vp_c[465]).xxxx).x)") != NULL, "decompiler: RCP c465.x");
        CHECK(strstr(hlsl, "((r[1]).xyzw)+((vp_c[467]).xxxx)") != NULL, "decompiler: ADD reads src0 + src2");
        CHECK(strstr(hlsl, "o[0].xy = _v.xy") != NULL && strstr(hlsl, "o[0].zw = _v.zw") != NULL,
              "decompiler: o0 written in two parts");
        CHECK(strstr(hlsl, "r[0].y = _v.y") != NULL, "decompiler: the scalar unit's temp and mask");
    }
#endif

    /* a pass-through: o0 = v0, o7.xy = v8 */
    {
        ins_t p[2] = { Z, Z };
        p[0].vec_op = 1; p[0].input = 0; p[0].s0 = src(T_IN, 0, "xyzw", 0); p[0].vec_result = 1; p[0].dst_out = 0;
        p[0].vmask = "xyzw";
        p[1].vec_op = 1; p[1].input = 8; p[1].s0 = src(T_IN, 0, "xyxx", 0); p[1].vec_result = 1; p[1].dst_out = 7;
        p[1].vmask = "xy"; p[1].end = 1;
        encode(uc, &p[0]); encode(uc + 16, &p[1]);
        in[0][0] = -0.5f; in[0][1] = 0.25f; in[0][2] = 0.1f; in[0][3] = 1.0f;
        in[8][0] = 0.75f; in[8][1] = 0.125f;
        CHECK(al_vp_eval(uc, 32, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 1, "pass-through runs");
        CHECK(o[0][0] == -0.5f && o[0][1] == 0.25f && o[0][3] == 1.0f, "pass-through o0");
        CHECK(o[7][0] == 0.75f && o[7][1] == 0.125f, "pass-through o7");
    }

    /* a matrix (DP4 per row, negated source, saturate) */
    {
        ins_t p[4];
        for (int k = 0; k < 4; k++) {
            p[k] = Z;
            p[k].vec_op = 7; p[k].input = 0; p[k].cnst = (uint32_t)(10 + k);
            p[k].s0 = src(T_IN, 0, "xyzw", 0); p[k].s1 = src(T_CONST, 0, "xyzw", k == 1);
            p[k].vec_result = 1; p[k].dst_out = 0;
            p[k].vmask = k == 0 ? "x" : k == 1 ? "y" : k == 2 ? "z" : "w";
        }
        p[2].saturate = 1;
        p[3].end = 1;
        for (int k = 0; k < 4; k++) encode(uc + 16 * k, &p[k]);
        setc(C, 10, 2, 0, 0, 1);      /* x = 2x + 1 */
        setc(C, 11, 0, 3, 0, 0);      /* y = -(3y) */
        setc(C, 12, 0, 0, 5, 0);      /* z = sat(5z) */
        setc(C, 13, 0, 0, 0, 1);
        in[0][0] = 1; in[0][1] = 2; in[0][2] = 0.5f; in[0][3] = 1;
        CHECK(al_vp_eval(uc, 64, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 1, "matrix runs");
        CHECK(o[0][0] == 3.0f && o[0][1] == -6.0f && o[0][2] == 1.0f && o[0][3] == 1.0f,
              "matrix: %f %f %f %f", o[0][0], o[0][1], o[0][2], o[0][3]);
    }

    /* the legacy multiply: 0 * INF is 0, as the shader's vp_mul */
    {
        ins_t p = Z;
        p.vec_op = 2; p.input = 0; p.cnst = 20; p.s0 = src(T_IN, 0, "xyzw", 0); p.s1 = src(T_CONST, 0, "xyzw", 0);
        p.vec_result = 1; p.dst_out = 0; p.vmask = "xyzw"; p.end = 1;
        encode(uc, &p);
        C[20][0] = 0x7F800000u; C[20][1] = 0x7F800000u; C[20][2] = 0; C[20][3] = f2u(1.0f);
        in[0][0] = 0.0f; in[0][1] = 2.0f; in[0][2] = 3.0f; in[0][3] = 1.0f;
        CHECK(al_vp_eval(uc, 16, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 1, "mul runs");
        CHECK(o[0][0] == 0.0f && isinf(o[0][1]) && o[0][2] == 0.0f, "0 * INF = 0, 2 * INF = INF, 3 * 0 = 0");
    }

    /* not modelled -> 0 */
    {
        ins_t p = Z;
        p.vec_op = 1; p.s0 = src(T_IN, 0, "xyzw", 0); p.vec_result = 1; p.dst_out = 0; p.vmask = "xyzw";
        p.end = 0;
        encode(uc, &p);
        CHECK(al_vp_eval(uc, 16, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 0, "no end bit -> 0");
        p.end = 1; p.index_const = 1; encode(uc, &p);
        CHECK(al_vp_eval(uc, 16, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 0, "indexed constant -> 0");
        p.index_const = 0; p.cond_test = 1; p.cond = 4; encode(uc, &p);
        CHECK(al_vp_eval(uc, 16, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 0, "conditional write -> 0");
        p.cond = 7; encode(uc, &p);
        CHECK(al_vp_eval(uc, 16, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 1, "cond 'always' runs");
        p.cond_test = 0; p.sca_op = 0x09; p.smask = ""; encode(uc, &p);   /* BRI */
        CHECK(al_vp_eval(uc, 16, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 0, "a branch -> 0");
        p.sca_op = 0; p.vec_op = 0x0D; encode(uc, &p);                     /* ARL */
        CHECK(al_vp_eval(uc, 16, (const float (*)[4])in, (const uint32_t (*)[4])C, o) == 0, "ARL -> 0");
    }
}

/* ------------------------------------------------------------------ the HUD */

static al_hud H = { 640.0f, 360.0f };

/* a quad from pixel coordinates (1280 x 720, y down -> clip y up) */
static al_quad Q(uint64_t tex, float x0, float x1, float y0, float y1, int uflip)
{
    al_quad q;
    q.tex = tex;
    q.x0 = x0 / 640.0f - 1.0f; q.x1 = x1 / 640.0f - 1.0f;
    q.y0 = 1.0f - y1 / 360.0f; q.y1 = 1.0f - y0 / 360.0f;
    q.uflip = uflip;
    q.u0 = uflip ? 1.0f : 0.0f;
    q.u1 = uflip ? 0.0f : 1.0f;
    return q;
}
/* where a draw of n vertices lands: its left edge in pixels; *why = the reason */
static float placed_n(const al_quad* q, uint32_t n, int* why)
{
    const float dx = al_hud_place(q, n, why);
    return (q->x0 + dx + 1.0f) * 640.0f;
}
static float placed(const al_quad* q) { int why; return placed_n(q, 4, &why); }

enum { FONT = 1, FRAME = 2, LIFE = 3, DRAIN = 4, TITLE = 5, DIGIT = 6, GLOW = 7, PLATE = 8, RANK = 9, REPLAY = 10 };

/* One fight frame of Tekken 5 DR's HUD as the game draws it (always-left trace of a 1.2.0 local fight, guest
 * 1280 x 720, one draw per quad, in drawing order): the timer's two digits, the bars' glow, the bar frames, two
 * fill layers per side, name plates, rank plates. Numbers only, typed in from the trace. */
static const struct { int tex; float x0, x1, y0, y1; int uflip; } kHud[] = {
    { DIGIT, 564.7f, 666.0f, 39.3f, 98.0f, 0 },   { DIGIT, 618.0f, 719.3f, 39.3f, 98.0f, 0 },
    { GLOW, 396.7f, 575.3f, 68.0f, 121.3f, 0 },   { GLOW, 706.7f, 885.3f, 68.0f, 121.3f, 1 },
    { FRAME, 41.3f, 588.0f, 42.7f, 85.3f, 0 },    { LIFE, 238.7f, 569.3f, 42.7f, 85.3f, 1 },
    { DRAIN, 243.9f, 569.3f, 42.7f, 85.3f, 1 },   { FRAME, 693.3f, 1240.0f, 42.7f, 85.3f, 1 },
    { LIFE, 712.0f, 1138.9f, 42.7f, 85.3f, 0 },   { DRAIN, 712.0f, 1138.9f, 42.7f, 85.3f, 0 },
    { RANK, 53.3f, 181.3f, 114.7f, 178.7f, 0 },   { PLATE, 53.3f, 477.3f, 81.3f, 121.3f, 0 },
    { PLATE, 804.0f, 1228.0f, 81.3f, 121.3f, 1 }, { RANK, 1100.0f, 1228.0f, 114.7f, 178.7f, 0 },
};

static void test_hud_game_frame(void)
{
    /* Every draw of a side moves by exactly half the width; the timer stays. The result is independent of
     * anything drawn before (no frame history), so the first mirrored frame is the same as every later one. */
    for (int pass = 0; pass < 3; pass++) {
        for (unsigned i = 0; i < sizeof kHud / sizeof kHud[0]; i++) {
            const al_quad q = Q(kHud[i].tex, kHud[i].x0, kHud[i].x1, kHud[i].y0, kHud[i].y1, kHud[i].uflip);
            int why;
            const float x = placed_n(&q, 4, &why);
            if (kHud[i].tex == DIGIT)
                CHECK(near(x, kHud[i].x0) && why == AL_STAY_ACROSS, "pass %d draw %u: timer digit stays", pass, i);
            else if (kHud[i].x1 <= 640.0f)
                CHECK(near(x, kHud[i].x0 + 640.0f) && why == AL_MOVE, "pass %d draw %u: P1 side to the right: %f",
                      pass, i, x);
            else
                CHECK(near(x, kHud[i].x0 - 640.0f) && why == AL_MOVE, "pass %d draw %u: P2 side to the left: %f",
                      pass, i, x);
        }
    }
    /* Issue #31: P1's fill touches the timer (569 vs 564.7) -- the old frame-history rule took it for part of
     * the centre and left it on the left while its frame moved right. Each fill must follow its own frame,
     * full, damaged, nearly empty, and with unequal life on the two sides. */
    const al_quad f1 = Q(FRAME, 41.3f, 588.0f, 42.7f, 85.3f, 0), f2 = Q(FRAME, 693.3f, 1240.0f, 42.7f, 85.3f, 1);
    for (int step = 0; step <= 8; step++) {
        const float life = (float)step / 8.0f, other = 1.0f - life * 0.5f;
        const float p1_left = 569.3f - (569.3f - 62.0f) * life, p2_right = 712.0f + (1219.3f - 712.0f) * other;
        const al_quad l1 = Q(LIFE, p1_left, 569.3f, 42.7f, 85.3f, 1);
        const al_quad d1 = Q(DRAIN, p1_left - 20.0f, 569.3f, 42.7f, 85.3f, 1);
        const al_quad l2 = Q(LIFE, 712.0f, p2_right, 42.7f, 85.3f, 0);
        const al_quad d2 = Q(DRAIN, 712.0f, p2_right, 42.7f, 85.3f, 0);
        CHECK(near(placed(&l1) - placed(&f1), p1_left - 41.3f), "life %.3f: P1 fill keeps its place in its frame", life);
        CHECK(near(placed(&d1) - placed(&f1), p1_left - 20.0f - 41.3f), "life %.3f: P1 drain keeps its place", life);
        CHECK(near(placed(&l2) - placed(&f2), 712.0f - 693.3f), "life %.3f: P2 fill keeps its place in its frame", life);
        CHECK(near(placed(&d2) - placed(&f2), 712.0f - 693.3f), "life %.3f: P2 drain keeps its place", life);
        CHECK(placed(&l1) >= 640.0f && placed(&d1) >= 640.0f, "life %.3f: P1's fill and drain on the right", life);
        CHECK(placed(&l2) + (l2.x1 - l2.x0) * 640.0f <= 640.0f, "life %.3f: P2's fill on the left", life);
    }
    /* A name, glyph by glyph: order and spacing kept, whatever its length; it lands under its own moved bar. */
    const char* names[] = { "WWWWWWWWWWWWWWWW", "il.Ab 12 Zy", "i", "SuperStarSag" };
    for (unsigned k = 0; k < 4; k++) {
        const size_t len = strlen(names[k]);
        for (int side = 0; side < 2; side++) {
            const float x0 = side ? 1226.0f - 14.67f * (float)len : 58.0f;   /* P2 right-aligned, P1 left-aligned */
            const al_quad frame = side ? f2 : f1;
            for (size_t i = 0; i < len; i++) {
                const float gx = x0 + 14.67f * (float)i;
                const al_quad g = Q(FONT, gx, gx + 23.3f, 89.3f, 112.7f, 0);
                CHECK(near(placed(&g), gx + (side ? -640.0f : 640.0f)), "name %u side %d glyph %u in order", k, side,
                      (unsigned)i);
                CHECK(placed(&g) >= placed(&frame) && placed(&g) + 23.3f <= placed(&frame) + 547.0f,
                      "name %u side %d glyph %u under its own bar", k, side, (unsigned)i);
            }
        }
    }
}

static void test_hud_centre_and_titles(void)
{
    int why;
    /* below the band: centre titles one quad per letter (a letter on one half must not move), ROUND and its
     * separate "1", intro text across the bottom, REPLAY (bottom right) */
    const al_quad letter_left = Q(TITLE, 381.3f, 520.0f, 278.9f, 366.9f, 0);
    const al_quad letter_right = Q(TITLE, 760.0f, 898.7f, 278.9f, 366.9f, 0);
    CHECK(near(placed_n(&letter_left, 4, &why), 381.3f) && why == AL_STAY_BELOW_BAND, "a title letter left of the middle stays");
    CHECK(near(placed_n(&letter_right, 4, &why), 760.0f) && why == AL_STAY_BELOW_BAND, "a title letter right of the middle stays");
    const al_quad round1 = Q(TITLE, 445, 695, 255, 300, 0), one = Q(FONT, 719, 785, 255, 300, 0);
    CHECK(near(placed(&round1), 445.0f) && near(placed(&one), 719.0f), "ROUND 1 stays together");
    const al_quad intro = Q(FONT, 898.7f, 922.0f, 632.7f, 656.0f, 0), replay = Q(REPLAY, 920.0f, 1250.7f, 582.7f, 686.7f, 0);
    CHECK(near(placed(&intro), 898.7f) && near(placed(&replay), 920.0f), "intro text and REPLAY stay");
    /* the band's edge: the rank plate (bottom 178.7) moves, a quad reaching below 216 stays */
    const al_quad rank = Q(RANK, 1100.0f, 1228.0f, 114.7f, 178.7f, 0), low = Q(RANK, 1100.0f, 1228.0f, 150.0f, 217.0f, 0);
    CHECK(near(placed(&rank), 460.0f), "the rank plate is in the band");
    CHECK(near(placed_n(&low, 4, &why), 1100.0f) && why == AL_STAY_BELOW_BAND, "below the band stays");
    /* a timer digit, any digit: across the middle, stays */
    const al_quad nine = Q(DIGIT, 590.0f, 691.3f, 39.3f, 98.0f, 0);
    CHECK(near(placed_n(&nine, 4, &why), 590.0f) && why == AL_STAY_ACROSS, "a single centred digit stays");
    /* a batch with elements of both sides is left whole (never cut); a small quad across the middle is centred */
    const al_quad batch = Q(FONT, 58, 1226, 89.3f, 112.7f, 0);
    CHECK(near(placed_n(&batch, 64, &why), 58.0f) && why == AL_STAY_BATCH, "a both-sides batch stays whole");
    CHECK(near(placed_n(&batch, 6, &why), 58.0f) && why == AL_STAY_ACROSS, "six vertices across the middle: centred");
    /* exactly at the middle: a quad ending at x = 640 is on the left */
    const al_quad edge = Q(GLOW, 540, 640, 60, 100, 0);
    CHECK(near(placed_n(&edge, 4, &why), 1180.0f) && why == AL_MOVE, "a quad ending at the middle moves right");
}

/* The round intro's PLAYER DATA strip (trace of a 1.2.0 local fight): two panels at mirrored places, each
 * reaching past its screen edge, the numbers one draw per glyph. Each panel takes the other's place, the
 * numbers move by half the width in order and land inside their own moved panel. */
static void test_hud_player_data(void)
{
    int why;
    const al_quad p1 = Q(PLATE, -13.6f, 565.1f, 522.1f, 594.1f, 0), p2 = Q(PLATE, 716.3f, 1294.9f, 522.1f, 594.1f, 0);
    CHECK(near(placed_n(&p1, 4, &why), 714.9f) && why == AL_SWAP_PANEL, "P1's panel at P2's place: %f", placed(&p1));
    CHECK(near(placed_n(&p2, 4, &why), -14.9f) && why == AL_SWAP_PANEL, "P2's panel at P1's place: %f", placed(&p2));
    for (int side = 0; side < 2; side++) {
        const al_quad panel = side ? p2 : p1;
        const float px0 = placed(&panel), px1 = px0 + (panel.x1 - panel.x0) * 640.0f;
        const float x0 = side ? 916.0f : 195.3f;
        float last = -1e9f;
        for (int i = 0; i < 10; i++) {
            const float gx = x0 + 25.0f * (float)i;
            const al_quad g = Q(FONT, gx, gx + 23.3f, 557.3f, 580.7f, 0);
            const float x = placed_n(&g, 4, &why);
            CHECK(near(x, gx + (side ? -640.0f : 640.0f)) && why == AL_MOVE, "side %d glyph %d moves by half", side, i);
            CHECK(x > last && x >= px0 && x + 23.3f <= px1, "side %d glyph %d in order, inside its panel", side, i);
            last = x;
        }
    }
    /* just outside the strip: the intro line (632..656) and REPLAY (582..686) stay; so does a centred title */
    const al_quad below = Q(FONT, 300, 323, 590, 613, 0), title = Q(TITLE, 380, 900, 520, 590, 0);
    CHECK(near(placed_n(&below, 4, &why), 300.0f) && why == AL_STAY_BELOW_BAND, "a glyph reaching below 600 stays");
    CHECK(near(placed_n(&title, 4, &why), 380.0f) && why == AL_STAY_BELOW_BAND, "a centred quad in the strip stays");
}

/* ---- the frame's side HUD placed together (al_hud_layout): the normal view's layout ---- */

/* the frame's real texture identities matter here: art the game flips shares one texture per kind */
enum { T_FONT = 101, T_FRAME, T_LIFE, T_DRAIN, T_MARKS, T_NPLATE, T_RANK, T_DATA1, T_DATA2 };

typedef struct { al_quad q[AL_PEND_MAX]; uint8_t cm[AL_PEND_MAX], mir[AL_PEND_MAX]; float dx[AL_PEND_MAX]; uint32_t n; } lay_t;
static lay_t L;
static uint32_t lay_add(uint64_t tex, float x0, float x1, float y0, float y1, int uflip)
{
    L.q[L.n] = Q(tex, x0, x1, y0, y1, uflip);
    L.cm[L.n] = 1;
    return L.n++;
}
/* where item i lands: its left and right edge in pixels */
static void lay_box(uint32_t i, float* a, float* b)
{
    const al_quad* q = &L.q[i];
    if (L.mir[i]) { *a = (1.0f - q->x1) * 640.0f; *b = (1.0f - q->x0) * 640.0f; }
    else { *a = (q->x0 + L.dx[i] + 1.0f) * 640.0f; *b = (q->x1 + L.dx[i] + 1.0f) * 640.0f; }
}
static int lay_name(float x_first, int right_aligned, const char* s, uint32_t* first)
{
    const int len = (int)strlen(s);
    const float x0 = right_aligned ? x_first - 14.67f * (float)(len - 1) : x_first;
    *first = L.n;
    for (int i = 0; i < len; i++) {
        if (s[i] == ' ') continue;     /* the game draws no glyph for a space */
        const float gx = x0 + 14.67f * (float)i;
        lay_add(T_FONT, gx, gx + 23.3f, 89.3f, 112.7f, 0);
    }
    return len;
}

/* One frame of the game's side HUD (the 1.2.0 trace's boxes and flips; textures by kind), life p1/p2 0..1. */
static void lay_frame(float p1, float p2, const char* n1, const char* n2, uint32_t* idx)
{
    memset(&L, 0, sizeof L);
    idx[0] = lay_add(T_MARKS, 396.7f, 575.3f, 68.0f, 121.3f, 0);
    idx[1] = lay_add(T_MARKS, 706.7f, 885.3f, 68.0f, 121.3f, 1);
    idx[2] = lay_add(T_FRAME, 41.3f, 588.0f, 42.7f, 85.3f, 0);
    const float l1 = 569.3f - (569.3f - 62.0f) * p1, r2 = 712.0f + (1219.3f - 712.0f) * p2;
    idx[3] = p1 > 0.0f ? lay_add(T_LIFE, l1, 569.3f, 42.7f, 85.3f, 1) : ~0u;
    idx[4] = p1 > 0.0f ? lay_add(T_DRAIN, l1, 569.3f, 42.7f, 85.3f, 1) : ~0u;
    idx[5] = lay_add(T_FRAME, 693.3f, 1240.0f, 42.7f, 85.3f, 1);
    idx[6] = p2 > 0.0f ? lay_add(T_LIFE, 712.0f, r2, 42.7f, 85.3f, 0) : ~0u;
    idx[7] = p2 > 0.0f ? lay_add(T_DRAIN, 712.0f, r2, 42.7f, 85.3f, 0) : ~0u;
    idx[8] = lay_add(T_RANK, 53.3f, 181.3f, 114.7f, 178.7f, 0);
    idx[9] = lay_add(T_NPLATE, 53.3f, 477.3f, 81.3f, 121.3f, 0);
    idx[10] = lay_add(T_NPLATE, 804.0f, 1228.0f, 81.3f, 121.3f, 1);
    idx[11] = lay_add(T_RANK, 1100.0f, 1228.0f, 114.7f, 178.7f, 0);
    lay_name(58.0f, 0, n1, &idx[12]);
    idx[13] = L.n;
    lay_name(1226.0f - 23.3f, 1, n2, &idx[14]);
    idx[15] = L.n;
    al_hud_layout(L.q, L.cm, L.n, L.mir, L.dx);
}

static void test_hud_layout_normal_look(void)
{
    const char* names[][2] = { { "WWWWWWWWWWWWWWWW", "il.Ab 12 Zy" }, { "i", "SuperStarSag" },
                               { "AlphaHostLeft001", "zz_joinerP2_iiii" }, { "A   B", "x  y  z" } };
    for (unsigned k = 0; k < 4; k++)
        for (int step = 0; step <= 8; step++) {
            const float p1 = (float)step / 8.0f, p2 = 1.0f - 0.5f * p1;
            uint32_t ix[16];
            lay_frame(p1, p2, names[k][0], names[k][1], ix);
            float a, b;
            /* art the game flips: mirrored, each at the other side's place */
            lay_box(ix[5], &a, &b);
            CHECK(L.mir[ix[5]] && near(a, 40.0f) && near(b, 586.7f), "P2's frame at the left frame's place: %f..%f", a, b);
            lay_box(ix[2], &a, &b);
            CHECK(L.mir[ix[2]] && near(a, 692.0f) && near(b, 1238.7f), "P1's frame at the right frame's place");
            lay_box(ix[1], &a, &b);
            CHECK(L.mir[ix[1]] && near(a, 394.7f) && near(b, 573.3f), "P2's round marks at the left marks' place");
            CHECK(L.mir[ix[0]] && L.mir[ix[9]] && L.mir[ix[10]], "marks and name plates mirrored");
            /* the fills: drain like the normal view's bar on that side -- the left bar anchored at the timer end */
            if (ix[6] != ~0u) {
                lay_box(ix[6], &a, &b);
                CHECK((L.mir[ix[6]] || ix[3] == ~0u) && near(b, 568.0f), "life %d: P2's fill on the left, anchored at the timer end: %f", step, b);
                lay_box(ix[7], &a, &b);
                CHECK(near(b, 568.0f), "life %d: P2's drain anchored there too", step);
            }
            if (ix[3] != ~0u) {
                lay_box(ix[3], &a, &b);
                CHECK(L.mir[ix[3]] && near(a, 710.7f), "life %d: P1's fill on the right, anchored at the timer end: %f", step, a);
            }
            /* rank plates (writing on them): moved to the other plate's place, not mirrored */
            lay_box(ix[8], &a, &b);
            CHECK(!L.mir[ix[8]] && near(a, 1098.7f) && near(b, 1226.7f), "P1's rank plate at the right plate's place");
            lay_box(ix[11], &a, &b);
            CHECK(!L.mir[ix[11]] && near(a, 52.0f) && near(b, 180.0f), "P2's rank plate at the left plate's place");
            /* names: whole, in order, P2's left-aligned at the left edge, P1's right-aligned at the right edge */
            float prev = -1e9f, first = 0, last = 0;
            for (uint32_t i = ix[14]; i < ix[15]; i++) {
                lay_box(i, &a, &b);
                CHECK(!L.mir[i] && a > prev, "name %u: P2's glyph %u in order, not mirrored", k, i - ix[14]);
                if (i == ix[14]) first = a;
                last = b; prev = a;
            }
            CHECK(near(first, 1280.0f - 1226.0f), "name %u: P2's name starts at the left edge: %f", k, first);
            CHECK(last < 640.0f, "name %u: P2's name on the left", k);
            prev = -1e9f;
            for (uint32_t i = ix[12]; i < ix[13]; i++) {
                lay_box(i, &a, &b);
                CHECK(!L.mir[i] && a > prev, "name %u: P1's glyph %u in order", k, i - ix[12]);
                prev = a; last = b;
            }
            CHECK(near(last, 1280.0f - 58.0f), "name %u: P1's name ends at the right edge: %f", k, last);
        }
    /* a KO'd side draws no fill: the other side's fill (its texture now only unflipped) keeps its place */
    uint32_t ix[16];
    lay_frame(0.0f, 0.6f, "AB", "CD", ix);
    float a, b;
    lay_box(ix[6], &a, &b);
    CHECK(near(b, 568.0f), "P1 KO'd: P2's fill still anchored at the left bar's timer end: %f..%f", a, b);
    /* the same frame laid out twice gives the same answer (nothing remembered) */
    lay_frame(0.4f, 0.7f, "WWWW", "ZZ", ix);
    float before[AL_PEND_MAX];
    for (uint32_t i = 0; i < L.n; i++) lay_box(i, &before[i], &b);
    lay_frame(0.4f, 0.7f, "WWWW", "ZZ", ix);
    int same = 1;
    for (uint32_t i = 0; i < L.n; i++) { lay_box(i, &a, &b); same &= near(a, before[i]); }
    CHECK(same, "the layout depends on this frame's draws only");
    /* culling on: never mirrored (the winding would flip), placed at the mirrored box instead */
    memset(&L, 0, sizeof L);
    const uint32_t f = lay_add(T_FRAME, 693.3f, 1240.0f, 42.7f, 85.3f, 1);
    L.cm[f] = 0;
    al_hud_layout(L.q, L.cm, L.n, L.mir, L.dx);
    lay_box(f, &a, &b);
    CHECK(!L.mir[f] && near(a, 40.0f) && near(b, 586.7f), "culled art: box mirrored, art kept");
    /* the PLAYER DATA strip: panels swap places, each side's numbers move as one line */
    memset(&L, 0, sizeof L);
    const uint32_t p1 = lay_add(T_DATA1, -13.6f, 565.1f, 522.1f, 594.1f, 0);
    const uint32_t p2 = lay_add(T_DATA2, 716.3f, 1294.9f, 522.1f, 594.1f, 0);
    const uint32_t g0 = L.n;
    for (int i = 0; i < 6; i++) {
        const float gx = 195.3f + (i < 3 ? 25.0f * (float)i : 120.0f + 25.0f * (float)i);   /* "0 W" ... "0 L" */
        lay_add(T_FONT, gx, gx + 23.3f, 557.3f, 580.7f, 0);
    }
    al_hud_layout(L.q, L.cm, L.n, L.mir, L.dx);
    float prev;
    lay_box(p1, &a, &b);
    CHECK(near(a, 714.9f), "P1's panel at P2's place: %f", a);
    lay_box(p2, &a, &b);
    CHECK(near(a, -14.9f), "P2's panel at P1's place");
    float pa, pb;
    lay_box(p1, &pa, &pb);
    prev = -1e9f;
    for (uint32_t i = g0; i < L.n; i++) {
        lay_box(i, &a, &b);
        CHECK(a > prev && a >= pa && b <= pb, "P1's number %u in order inside its moved panel", i - g0);
        prev = a;
    }
}

/* Patch 0110 (review fix-31-hpbar P2): a flush in the middle of the HUD (full ring, readback) runs the first
 * part of the side draws before the rest is known. Each later part must follow what was placed: a name split
 * between glyphs keeps its glyphs in order at their spacing (before: "ABCD" flushed after "B" showed "CDAB"), a
 * texture mirrored in an earlier part stays mirrored. Every split point of a whole frame's HUD is tried. */
static void test_hud_layout_split_by_a_flush(void)
{
    uint32_t ix[16];
    lay_frame(0.6f, 0.8f, "ABCD", "WXYZ", ix);
    const uint32_t n = L.n;
    static al_quad q[AL_PEND_MAX];
    static uint8_t cm[AL_PEND_MAX];
    memcpy(q, L.q, sizeof q);
    memcpy(cm, L.cm, sizeof cm);
    int teeth = 0;
    for (uint32_t cut = 1; cut < n; cut++) {
        static al_placed placed[AL_PEND_MAX];
        uint32_t n_placed = 0;
        al_hud_layout_frame(q, cm, cut, L.mir, L.dx, placed, &n_placed, AL_PEND_MAX);
        al_hud_layout_frame(q + cut, cm + cut, n - cut, L.mir + cut, L.dx + cut, placed, &n_placed, AL_PEND_MAX);
        for (int side = 0; side < 2; side++) {
            const uint32_t from = side ? ix[14] : ix[12], to = side ? ix[15] : ix[13];
            float prev_a = -1e9f;
            for (uint32_t i = from; i < to; i++) {
                float a, b;
                lay_box(i, &a, &b);
                CHECK(!L.mir[i] && a > prev_a, "cut %u: name %d glyph %u in order", cut, side, i - from);
                if (i > from)
                    CHECK(near(a - prev_a, 14.67f), "cut %u: name %d glyph %u keeps its spacing (%f)", cut, side,
                          i - from, a - prev_a);
                CHECK(side ? b < 640.0f : a > 640.0f, "cut %u: name %d on the mirrored side", cut, side);
                prev_a = a;
            }
        }
        /* art the game flips: mirrored in every part once a part saw its flip (a part that ran before the
         * texture's flip was drawn could not know it: P1's plate alone in the first part is placed like text) */
        CHECK(L.mir[ix[1]] && L.mir[ix[10]] && (cut == 10 || L.mir[ix[9]]) && (cut == 1 || L.mir[ix[0]]),
              "cut %u: marks / name plates mirrored", cut);
        CHECK(n_placed >= 4, "cut %u: the parts' groups are kept for the frame (%u)", cut, n_placed);
        /* the old way (each part on its own) puts a split name out of order */
        if (cut > ix[14] && cut < ix[15]) {
            al_hud_layout(q, cm, cut, L.mir, L.dx);
            al_hud_layout(q + cut, cm + cut, n - cut, L.mir + cut, L.dx + cut);
            float a0, b0, a1, b1;
            lay_box(cut - 1, &a0, &b0);
            lay_box(cut, &a1, &b1);
            teeth += a1 < a0;
        }
    }
    CHECK(teeth > 0, "the old per-part layout reorders a split name (the test has teeth): %d", teeth);
    /* unsplit: the frame layout is the old layout exactly */
    static al_placed placed[AL_PEND_MAX];
    uint32_t n_placed = 0;
    static uint8_t m2[AL_PEND_MAX];
    static float d2[AL_PEND_MAX];
    al_hud_layout(q, cm, n, L.mir, L.dx);
    al_hud_layout_frame(q, cm, n, m2, d2, placed, &n_placed, AL_PEND_MAX);
    int same = 1;
    for (uint32_t i = 0; i < n; i++) same &= m2[i] == L.mir[i] && d2[i] == L.dx[i];
    CHECK(same, "one list per frame: the same layout as before 0110");
}

/* Diagnostics: a centred raw quad whose visible scissor part is on one side is flagged (side_clipped_center);
 * al_hud_clip keeps texture identity and direction. */
static void test_hud_scissor_diagnostics(void)
{
    const al_quad raw = Q(LIFE, 0, 1280, 40, 90, 0);
    al_quad visible = raw;
    CHECK(al_hud_clip(&H, &visible, 100, 58, 560, 68), "nonempty bar scissor");
    CHECK(near((visible.x0 + 1) * 640, 100) && near((visible.x1 + 1) * 640, 560), "visible x box");
    CHECK(near((1 - visible.y1) * 360, 58) && near((1 - visible.y0) * 360, 68), "visible y box");
    CHECK(visible.tex == raw.tex && visible.uflip == raw.uflip && visible.u0 == raw.u0 && visible.u1 == raw.u1,
          "clipping does not alter texture identity/direction");
    CHECK(al_hud_side_clipped_center(&raw, &visible), "side-clipped centre marker");
    al_quad bar = Q(LIFE, 100, 400, 58, 68, 0), clipped = bar;
    CHECK(al_hud_clip(&H, &clipped, 0, 0, 1280, 720), "full scissor: nonempty");
    CHECK(near(clipped.x0, bar.x0) && near(clipped.x1, bar.x1), "full scissor: original bounds");
    CHECK(!al_hud_side_clipped_center(&bar, &clipped), "ordinary side bar is not a centred raw quad");
    clipped = bar;
    CHECK(!al_hud_clip(&H, &clipped, 200, 58, 200, 68), "zero-width scissor: empty");
    clipped = bar;
    CHECK(!al_hud_clip(&H, &clipped, 1400, 58, 1500, 68), "off-screen scissor: empty");
    al_quad empty = raw;
    empty.x1 = empty.x0;
    CHECK(!al_hud_side_clipped_center(&raw, &empty), "empty visible box has no marker");
}

static void test_picture_quad_and_scissor(void)
{
    const float quad[4][2] = { { -1, -1 }, { 1, -1 }, { 1, 1 }, { -1, 1 } };
    const float triangles[6][2] = { { -1, -1 }, { 1, -1 }, { 1, 1 }, { -1, -1 }, { 1, 1 }, { -1, 1 } };
    const float glyph[4][2] = { { 0.5f, 0.7f }, { 0.6f, 0.7f }, { 0.6f, 0.8f }, { 0.5f, 0.8f } };
    const float repeated[4][2] = { { -1, -1 }, { 1, -1 }, { 1, 1 }, { 1, 1 } };
    float camera_moved[4][2];
    CHECK(al_picture_quad(quad, 4, 640, 360), "four-corner scene copy recognized");
    CHECK(al_picture_quad(triangles, 6, 640, 360), "two-triangle scene copy recognized");
    CHECK(!al_picture_quad(glyph, 4, 640, 360), "HUD glyph cannot become a scene copy from stale bindings");
    CHECK(!al_picture_quad(repeated, 4, 640, 360), "all four different corners required");
    CHECK(!al_picture_quad(quad, 3, 640, 360), "partial copy rejected");
    CHECK(!al_picture_quad(quad, 4, 0, 360), "invalid target rejected");
    for (int i = 0; i < 4; i++) { camera_moved[i][0] = quad[i][0] + 0.02f; camera_moved[i][1] = quad[i][1]; }
    CHECK(!al_picture_quad((const float (*)[2])camera_moved, 4, 640, 360), "camera-dependent bounds are not a fullscreen copy");
    camera_moved[0][0] = NAN;
    CHECK(!al_picture_quad((const float (*)[2])camera_moved, 4, 640, 360), "non-finite evaluated coordinates rejected");
    {
        int l = 900, r = 1180;
        al_clip_scissor(1280, -640, 0, &l, &r);
        CHECK(l == 260 && r == 540, "bar clipping follows the same half shift");
        l = 100; r = 560;
        al_clip_scissor(1280, 640, 0, &l, &r);
        CHECK(l == 740 && r == 1200, "other half clipping follows its bar");
        l = 10; r = 100;
        al_clip_scissor(1280, -640, 0, &l, &r);
        CHECK(l == 0 && r == 0, "fully offscreen left becomes empty before unsigned conversion");
        l = 1200; r = 1270;
        al_clip_scissor(1280, 640, 0, &l, &r);
        CHECK(l == 1280 && r == 1280, "fully offscreen right becomes empty");
        l = 100; r = 560;
        al_clip_scissor(1280, 0, 1, &l, &r);
        CHECK(l == 720 && r == 1180, "scene-copy scissor reflects with the picture");
    }
}

int main(void)
{
    test_vp();
    test_hud_game_frame();
    test_hud_centre_and_titles();
    test_hud_player_data();
    test_hud_layout_normal_look();
    test_hud_layout_split_by_a_flush();
    test_hud_scissor_diagnostics();
    test_picture_quad_and_scissor();
    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
