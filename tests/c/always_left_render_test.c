/*
 * Unit test of "Always left" in the renderer (ps3recomp patch 0086, libs/video/rsx_always_left.h; docs/NETPLAY.md
 * "Always left"):
 *
 *   al_vp_eval        a vertex program run on the CPU gives what its shader gives: the HUD's kind of program
 *                     (position = attribute 0 through constants 256/257/259/467, times w; TEX0 = a constant),
 *                     a pass-through, a matrix (DP4), the legacy multiply (0 * INF = 0), and 0 for what it does
 *                     not model (branches, indexed constants, conditional writes, no end bit).
 *   al_hud_*          one frame's HUD is laid out mirrored in the next: a string keeps its letters in order and
 *                     moves as a whole to the mirrored place, a flipped pair (the bars' frames) is mirrored, a
 *                     lone quad moves by itself, a centred one stays.
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

static al_hud H;

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
/* ... with its own texture coordinates at the left and right edge */
static al_quad QU(uint64_t tex, float x0, float x1, float y0, float y1, float u0, float u1)
{
    al_quad q = Q(tex, x0, x1, y0, y1, u1 < u0);
    q.u0 = u0;
    q.u1 = u1;
    return q;
}
static float placed_x0(const al_quad* q, int* m);
static int placed_mirror(const al_quad* q) { int m = 0; (void)placed_x0(q, &m); return m; }
/* where q's left edge lands this frame, in pixels; *m = mirrored */
static float placed_x0(const al_quad* q, int* m)
{
    const float dx = al_hud_place(&H, q, m);
    if (*m) return (-q->x1 + 1.0f) * 640.0f;
    return (q->x0 + dx + 1.0f) * 640.0f;
}

enum { FONT = 1, BAR = 2, FILL = 3, ICON = 4, DIGIT5 = 5, DIGIT9 = 6, DIGIT4 = 7, MARKS = 8, PLATE = 9 };

static void hud_frame(int with_extra)
{
    /* P1's name (left), P2's name (right), the timer (centre, bigger), bar frames (a flipped pair), fills */
    al_quad qs[] = {
        Q(FONT, 216, 236, 40, 60, 0), Q(FONT, 238, 258, 40, 60, 0),
        Q(FONT, 1000, 1020, 40, 60, 0), Q(FONT, 1022, 1042, 40, 60, 0), Q(FONT, 1044, 1064, 40, 60, 0),
        Q(FONT, 620, 638, 30, 70, 0), Q(FONT, 642, 660, 30, 70, 0),
        Q(BAR, 100, 560, 70, 90, 0), Q(BAR, 720, 1180, 70, 90, 1),
        Q(FILL, 100, 400, 72, 88, 0), Q(FILL, 900, 1180, 72, 88, 1),
    };
    for (unsigned i = 0; i < sizeof qs / sizeof qs[0]; i++) al_hud_note(&H, &qs[i]);
    if (with_extra) { al_quad e = Q(ICON, 1100, 1140, 100, 140, 0); al_hud_note(&H, &e); }
}

static void test_hud(void)
{
    memset(&H, 0, sizeof H);
    H.px_w = 640.0f; H.px_h = 360.0f;
    int m;

    /* the first frame: nothing known yet, every quad goes to its own mirrored place */
    al_quad g1 = Q(FONT, 1000, 1020, 40, 60, 0);
    CHECK(near(placed_x0(&g1, &m), 260.0f) && !m, "first frame: a lone glyph to its own mirrored place");

    hud_frame(0);
    al_hud_frame_end(&H);
    CHECK(H.n_cur == 0, "the frame's quads are consumed");
    /* elements: P1 name, P2 name, timer, two bar frames, two fills = 7 */
    CHECK(H.n_el == 7, "7 elements, got %u", H.n_el);

    /* P2's name -> the left, letters in order, at P1's name's mirrored place (1280 - 1064 = 216) */
    al_quad a = Q(FONT, 1000, 1020, 40, 60, 0), b = Q(FONT, 1022, 1042, 40, 60, 0), c = Q(FONT, 1044, 1064, 40, 60, 0);
    const float xa = placed_x0(&a, &m), xb = placed_x0(&b, &m), xc = placed_x0(&c, &m);
    CHECK(near(xa, 216.0f) && near(xb, 238.0f) && near(xc, 260.0f) && !m, "P2's name: %f %f %f", xa, xb, xc);
    /* P1's name -> the right (1280 - 258 = 1022) */
    al_quad p = Q(FONT, 216, 236, 40, 60, 0);
    CHECK(near(placed_x0(&p, &m), 1022.0f) && !m, "P1's name to the right: %f", placed_x0(&p, &m));
    /* the timer stays, digits in order */
    al_quad t0 = Q(FONT, 620, 638, 30, 70, 0), t1 = Q(FONT, 642, 660, 30, 70, 0);
    CHECK(near(placed_x0(&t0, &m), 620.0f) && near(placed_x0(&t1, &m), 642.0f), "the timer stays as it is");
    /* a changed digit (other letter, same place) still belongs to the timer */
    al_quad t2 = Q(FONT, 621, 637, 30, 70, 0);
    CHECK(near(placed_x0(&t2, &m), 621.0f), "a new digit in the timer's place stays");
    /* the bar frames: mirrored, each takes the other's look */
    al_quad f1 = Q(BAR, 100, 560, 70, 90, 0), f2 = Q(BAR, 720, 1180, 70, 90, 1);
    CHECK(near(placed_x0(&f1, &m), 720.0f) && m == 1, "P1's frame mirrored to the right");
    CHECK(near(placed_x0(&f2, &m), 100.0f) && m == 1, "P2's frame mirrored to the left");
    /* the fills: different lengths, no pair: moved, anchored at the outer edge on the other side */
    al_quad l1 = Q(FILL, 100, 400, 72, 88, 0), l2 = Q(FILL, 900, 1180, 72, 88, 1);
    CHECK(near(placed_x0(&l1, &m), 880.0f) && !m, "P1's fill to the right, ending at the edge: %f",
          placed_x0(&l1, &m));
    CHECK(near(placed_x0(&l2, &m), 100.0f) && !m, "P2's fill to the left, from the edge");
    /* the fill shrank since the last frame: still moved by its own box's mirror (anchored at the edge) */
    al_quad l3 = Q(FILL, 950, 1180, 72, 88, 1);
    CHECK(near(placed_x0(&l3, &m), 100.0f) && !m, "a shrunk fill stays at the edge: %f", placed_x0(&l3, &m));
    /* something new (no element of the last frame covers it): its own mirrored place */
    al_quad e = Q(ICON, 1100, 1140, 100, 140, 0);
    CHECK(near(placed_x0(&e, &m), 140.0f) && !m, "a new quad: its own mirrored place");

    /* a frame with the extra icon, then one without: the layout follows the last frame only */
    hud_frame(1);
    al_hud_frame_end(&H);
    CHECK(H.n_el == 8, "8 elements with the icon");
    hud_frame(0);
    al_hud_frame_end(&H);
    CHECK(H.n_el == 7, "7 again");

    /* two strings on one line far apart stay two elements; the same text on both sides is no pair (not flipped) */
    memset(&H, 0, sizeof H);
    H.px_w = 640.0f; H.px_h = 360.0f;
    al_quad r[] = { Q(FONT, 100, 120, 600, 620, 0), Q(FONT, 122, 142, 600, 620, 0),
                    Q(FONT, 1138, 1158, 600, 620, 0), Q(FONT, 1160, 1180, 600, 620, 0) };
    for (int i = 0; i < 4; i++) al_hud_note(&H, &r[i]);
    al_hud_frame_end(&H);
    CHECK(H.n_el == 2, "two strings on one line: %u elements", H.n_el);
    CHECK(!H.el[0].mirror && !H.el[1].mirror, "the same text on both sides is not mirrored");
    CHECK(near(placed_x0(&r[0], &m), 1138.0f) && near(placed_x0(&r[1], &m), 1160.0f) && !m,
          "the left text, readable, at the right");

    /* a glyph shadow pass and the glyphs again (drawn twice, overlapping): one element */
    memset(&H, 0, sizeof H);
    H.px_w = 640.0f; H.px_h = 360.0f;
    al_quad s[] = { Q(FONT, 1001, 1021, 41, 61, 0), Q(FONT, 1023, 1043, 41, 61, 0),
                    Q(FONT, 1000, 1020, 40, 60, 0), Q(FONT, 1022, 1042, 40, 60, 0) };
    for (int i = 0; i < 4; i++) al_hud_note(&H, &s[i]);
    al_hud_frame_end(&H);
    CHECK(H.n_el == 1, "shadow and glyphs: one element (%u)", H.n_el);
}

/* what the game draws (1.1.8 test runs, RSX_ALWAYS_LEFT_DUMP): the timer one texture per digit, the round
 * marks' plates one texture at mirrored places with the marks in different parts of it, the PLAYER DATA
 * plates the same picture on both sides */
static void test_hud_game_shapes(void)
{
    memset(&H, 0, sizeof H);
    H.px_w = 640.0f; H.px_h = 360.0f;
    int m;
    al_quad d1 = Q(DIGIT5, 564.7f, 666.0f, 39.3f, 98.0f, 0), d2 = Q(DIGIT9, 618.0f, 719.3f, 39.3f, 98.0f, 0);
    al_quad k1 = QU(MARKS, 396.7f, 575.3f, 68, 121.3f, 0.0f, 1.0f), k2 = QU(MARKS, 706.7f, 885.3f, 68, 121.3f, 1.0f, 0.0f);
    al_quad p1 = Q(PLATE, 53.3f, 477.3f, 81.3f, 121.3f, 0), p2 = Q(PLATE, 804.0f, 1228.0f, 81.3f, 121.3f, 0);
    /* two different letters of the font at mirrored places (other u, same direction): no pair */
    al_quad g1 = QU(FONT, 100, 120, 600, 620, 0.10f, 0.12f), g2 = QU(FONT, 1160, 1180, 600, 620, 0.30f, 0.32f);
    al_quad all[] = { d1, d2, k1, k2, p1, p2, g1, g2 };
    for (int i = 0; i < 8; i++) al_hud_note(&H, &all[i]);
    al_hud_frame_end(&H);
    CHECK(H.n_el == 7, "timer one element, marks two, plates two, letters two: %u", H.n_el);
    /* the timer (its digits across the middle) stays: "59" stays "59" */
    const float x1 = placed_x0(&d1, &m), x2 = placed_x0(&d2, &m);
    CHECK(near(x1, 564.7f) && near(x2, 618.0f) && !m, "timer digits stay: %f %f", x1, x2);
    al_quad d3 = Q(DIGIT4, 564.7f, 666.0f, 39.3f, 98.0f, 0);
    CHECK(near(placed_x0(&d3, &m), 564.7f) && !m, "a new digit texture stays too");
    /* a big title across the middle, one quad per letter (FIGHT): every letter stays */
    al_quad f = Q(ICON, 575.8f, 1330.9f, 254.1f, 591.2f, 0);
    CHECK(near(placed_x0(&f, &m), 575.8f) && !m, "a letter of FIGHT stays");
    CHECK(!placed_mirror(&g1) && !placed_mirror(&g2), "different letters at mirrored places are not mirrored");
    CHECK(near(placed_x0(&g1, &m), 1160.0f), "a letter moves readable");
    /* the marks: a flipped pair, mirrored (the marks stay next to the timer) */
    {   /* "ROUND" across the middle and its "1", another quad touching it: both stay ("R1UND" otherwise) */
        al_hud r2;
        memcpy(&r2, &H, sizeof r2);
        memset(&H, 0, sizeof H);
        H.px_w = 640.0f; H.px_h = 360.0f;
        al_quad rd = Q(ICON, 445, 695, 255, 300, 0), one = Q(FONT, 719, 785, 255, 300, 0);   /* 24 px away, as in the game */
        al_quad far = Q(FONT, 900, 930, 255, 300, 0);
        al_hud_note(&H, &rd); al_hud_note(&H, &one); al_hud_note(&H, &far);
        al_hud_frame_end(&H);
        CHECK(near(placed_x0(&rd, &m), 445.0f) && near(placed_x0(&one, &m), 719.0f), "ROUND 1 stays together");
        CHECK(near(placed_x0(&far, &m), 350.0f), "something far from it on the line still moves");
        memcpy(&H, &r2, sizeof r2);
    }
    CHECK(near(placed_x0(&k1, &m), 704.7f) && m == 1, "P1's marks mirrored to the right");
    CHECK(near(placed_x0(&k2, &m), 394.7f) && m == 1, "P2's marks mirrored to the left");
    /* the same picture on both sides: moved, not mirrored (writing on it stays readable) */
    CHECK(near(placed_x0(&p2, &m), 52.0f) && !m, "P2's plate moved, not mirrored: %f", placed_x0(&p2, &m));
    CHECK(near(placed_x0(&p1, &m), 802.7f) && !m, "P1's plate moved, not mirrored");
}

int main(void)
{
    test_vp();
    test_hud();
    test_hud_game_shapes();
    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
