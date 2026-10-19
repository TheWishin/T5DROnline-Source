/*
 * Unit test of the stage blur / glow handling (ps3recomp patch 0043, libs/video/rsx_fp_decompiler.c;
 * docs/RENDER_PERF.md "Stage blur and glow"):
 *
 *   rsx_fp_texture_tap_mask   the texture units a fragment program samples two or more times: a filter
 *                             kernel (blur, glow, soft downsample) when the unit is a render target. The
 *                             runtime reads such a scaled target through its guest-size view, so the taps
 *                             cover what they cover at Native.
 *   rsx_fp_apply_single_tap   PS3_STAGE_BLUR=0: every tap of such a unit reads one coordinate -- the
 *                             kernel's centre tap when it has one, else the mean of the taps.
 *
 * The fragment programs here are written for this test (in the decompiler's output form), not taken from
 * a game. Every program the single-tap pass changes is compiled with D3DCompile (ps_5_0) when
 * d3dcompiler_47.dll is on this PC, and the centre it picks is checked by evaluating the same rule in C.
 *
 *   stage_blur_test      prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * The runtime file is included as it is (some of its functions are static). Built by
 * tests/test_stage_blur.py with clang-cl or cl.
 */
#include "rsx_fp_decompiler.c"

#include <windows.h>
#include <math.h>

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); \
        }                                                                       \
    } while (0)

/* ------------------------------------------------------------------ fragment program ucode */

/* One 32-bit word as the RSX stores it: big-endian with the two 16-bit halves swapped
 * (rsx_fp_read_word undoes both). */
static void put_word(u8* p, u32 w)
{
    const u32 v = (w << 16) | (w >> 16);
    p[0] = (u8)(v >> 24); p[1] = (u8)(v >> 16); p[2] = (u8)(v >> 8); p[3] = (u8)v;
}

/* an instruction: opcode, texture unit, END bit; SRC0 type (TEMP or CONST: a CONST pulls an inline
 * 16-byte constant slot after the instruction); `branch` sets the branch bit of DWORD2 */
static u32 put_insn(u8* p, u32 op, u32 unit, int end, u32 src0_type, int branch, const u8 inline_const[16])
{
    put_word(p + 0, (op << FP_OPCODE_SHIFT) | (unit << FP_TEX_UNIT_SHIFT) | (end ? FP_END : 0));
    put_word(p + 4, src0_type << FP_REG_TYPE_SHIFT);
    put_word(p + 8, branch ? FP_BRANCH : 0);
    put_word(p + 12, 0);
    if (src0_type == FP_REG_TYPE_CONST) {
        memcpy(p + 16, inline_const, 16);
        return 32;
    }
    return 16;
}

static void test_tap_mask(void)
{
    u8 fp[512];
    u32 n;
    u8 tex_like[16];

    /* unit 0 three times, unit 1 once, unit 2 twice (TXP + TXB) */
    n = 0;
    n += put_insn(fp + n, OP_TEX, 0, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TEX, 1, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TEX, 0, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TXP, 2, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_MAD, 0, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TXB, 2, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TEX, 0, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_MOV, 0, 1, FP_REG_TYPE_TEMP, 0, NULL);
    CHECK(rsx_fp_texture_mask(fp, n) == 0x7u, "texture mask %X", rsx_fp_texture_mask(fp, n));
    CHECK(rsx_fp_texture_tap_mask(fp, n) == 0x5u, "tap mask %X (want units 0 and 2)", rsx_fp_texture_tap_mask(fp, n));

    /* a single read of each unit: no kernel (the plain downsample, the heat haze) */
    n = 0;
    n += put_insn(fp + n, OP_TEX, 0, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TEX, 1, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_MUL, 0, 1, FP_REG_TYPE_TEMP, 0, NULL);
    CHECK(rsx_fp_texture_tap_mask(fp, n) == 0, "single reads: tap mask %X", rsx_fp_texture_tap_mask(fp, n));

    /* an inline constant whose bytes look like a TEX of unit 3 is data, not a second read */
    put_word(tex_like + 0, (OP_TEX << FP_OPCODE_SHIFT) | (3u << FP_TEX_UNIT_SHIFT));
    memset(tex_like + 4, 0, 12);
    n = 0;
    n += put_insn(fp + n, OP_TEX, 3, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_MUL, 0, 0, FP_REG_TYPE_CONST, 0, tex_like);
    n += put_insn(fp + n, OP_MOV, 0, 1, FP_REG_TYPE_TEMP, 0, NULL);
    CHECK(rsx_fp_texture_tap_mask(fp, n) == 0, "inline constant counted as a read: %X", rsx_fp_texture_tap_mask(fp, n));
    CHECK(rsx_fp_program_size(fp, sizeof fp) == n, "program size %u, want %u", rsx_fp_program_size(fp, sizeof fp), n);

    /* the branch bit: the opcode field is something else then */
    n = 0;
    n += put_insn(fp + n, OP_TEX, 1, 0, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TEX, 1, 0, FP_REG_TYPE_TEMP, 1, NULL);
    n += put_insn(fp + n, OP_MOV, 0, 1, FP_REG_TYPE_TEMP, 0, NULL);
    CHECK(rsx_fp_texture_tap_mask(fp, n) == 0, "branch counted as a read: %X", rsx_fp_texture_tap_mask(fp, n));

    /* nothing after END is read; a missing END stops at max_bytes */
    n = 0;
    n += put_insn(fp + n, OP_TEX, 4, 1, FP_REG_TYPE_TEMP, 0, NULL);
    n += put_insn(fp + n, OP_TEX, 4, 0, FP_REG_TYPE_TEMP, 0, NULL);
    CHECK(rsx_fp_texture_tap_mask(fp, n) == 0, "read past END: %X", rsx_fp_texture_tap_mask(fp, n));
    CHECK(rsx_fp_texture_tap_mask(NULL, 64) == 0, "NULL program");
}

/* ------------------------------------------------------------------ the single-tap pass */

static const char k_head[] =
    "struct PSInput {\n"
    "    float4 position : SV_POSITION; float4 col0 : COLOR0; float4 col1 : COLOR1;\n"
    "    float4 fog : FOG;\n"
    "    float4 tc0:TEXCOORD0; float4 tc1:TEXCOORD1; float4 tc2:TEXCOORD2; float4 tc3:TEXCOORD3;\n"
    "    float4 tc4:TEXCOORD4; float4 tc5:TEXCOORD5; float4 tc6:TEXCOORD6; float4 tc7:TEXCOORD7;\n"
    "};\n"
    "Texture2D    rsx_tex[16] : register(t0);\n"
    "SamplerState rsx_samp[16] : register(s0);\n"
    "cbuffer PSConstants : register(b1) {\n"
    "    float4 fp_constants[4];\n"
    "    float4 fp_alpha;\n"
    "};\n";

/* A soft-focus downsample in the form the decompiler writes: a centre tap (tc1) and three taps
 * around it, weighted, then a curve; unit 1 is an ordinary texture read once. */
static const char k_soft[] =
    "float4 main(PSInput input) : SV_TARGET {\n"
    "    float4 r[48]; float4 h[48];\n"
    "    [unroll] for (int _i = 0; _i < 48; _i++) { r[_i] = (float4)0; h[_i] = (float4)0; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc1).xyzw).xy)); r[2].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(((r[2]).xyzw) * ((fp_constants[0]).xxxx)); h[0].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc0).xyzw).xy)); r[2].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(((r[2]).xyzw) * ((fp_constants[0]).yyyy) + ((h[0]).xyzw)); h[0].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc2).xyzw).xy)); r[2].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(((r[2]).xyzw) * ((fp_constants[0]).zzzz) + ((h[0]).xyzw)); h[0].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc3).xyzw).xy)); r[2].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(((r[2]).xyzw) * ((fp_constants[0]).wwww) + ((h[0]).xyzw)); h[0].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(rsx_tex[1].Sample(rsx_samp[1], ((input.tc4).xyzw).xy)); r[3].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(((h[0]).xyzw) * ((r[3]).xyzw)); h[0].xyzw = _v.xyzw; }\n"
    "    float4 _o = h[0];\n"
    "    return (_o == _o) ? _o : (float4)0;\n"
    "}\n";

/* a kernel with a dependent read: the second tap's coordinate comes from the first tap */
static const char k_dependent[] =
    "float4 main(PSInput input) : SV_TARGET {\n"
    "    float4 r[48]; float4 h[48];\n"
    "    [unroll] for (int _i = 0; _i < 48; _i++) { r[_i] = (float4)0; h[_i] = (float4)0; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc0).xyzw).xy)); r[0].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((r[0]).xyzw).xy)); r[1].xyzw = _v.xyzw; }\n"
    "    float4 _o = r[0] + r[1];\n"
    "    return (_o == _o) ? _o : (float4)0;\n"
    "}\n";

/* the same coordinate twice: already one tap */
static const char k_same[] =
    "float4 main(PSInput input) : SV_TARGET {\n"
    "    float4 r[48]; float4 h[48];\n"
    "    [unroll] for (int _i = 0; _i < 48; _i++) { r[_i] = (float4)0; h[_i] = (float4)0; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc0).xyzw).xy)); r[0].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc0).xyzw).xy)); r[1].xyzw = _v.xyzw; }\n"
    "    float4 _o = r[0] * r[1];\n"
    "    return (_o == _o) ? _o : (float4)0;\n"
    "}\n";

static int count(const char* s, const char* needle)
{
    int n = 0;
    for (const char* p = strstr(s, needle); p; p = strstr(p + 1, needle)) n++;
    return n;
}

typedef HRESULT (WINAPI* d3dcompile_fn)(LPCVOID, SIZE_T, LPCSTR, const void*, void*, LPCSTR, LPCSTR, UINT, UINT,
                                       void**, void**);
static d3dcompile_fn g_compile;
static int g_compiled;

/* ID3DBlob's vtable without the D3D headers: QueryInterface, AddRef, Release, GetBufferPointer, GetBufferSize */
typedef struct { void* (WINAPI* fn[5])(void*); } blob_vtbl;
typedef struct { const blob_vtbl* vt; } blob;

static void compile_ok(const char* hlsl, const char* what)
{
    if (!g_compile) return;
    void *code = NULL, *err = NULL;
    const HRESULT hr = g_compile(hlsl, strlen(hlsl), what, NULL, NULL, "main", "ps_5_0", 0, 0, &code, &err);
    CHECK(SUCCEEDED(hr), "%s does not compile: %s", what,
          err ? (const char*)((blob*)err)->vt->fn[3](err) : "(no message)");
    if (code) ((blob*)code)->vt->fn[2](code);
    if (err) ((blob*)err)->vt->fn[2](err);
    g_compiled++;
}

static char* program(const char* body, char* buf, size_t size)
{
    snprintf(buf, size, "%s%s", k_head, body);
    return buf;
}

/* the rule rsx_fp_apply_single_tap writes into the program, in C: the tap nearest the taps' mean when it is
 * less than half the kernel's radius from it, else the mean */
static void centre(const float (*t)[2], int n, float out[2])
{
    float m[2] = {0, 0};
    for (int k = 0; k < n; k++) { m[0] += t[k][0] / n; m[1] += t[k][1] / n; }
    float dmin = 3.4e38f, dmax = 0, b[2] = {m[0], m[1]};
    for (int k = 0; k < n; k++) {
        const float d = (t[k][0] - m[0]) * (t[k][0] - m[0]) + (t[k][1] - m[1]) * (t[k][1] - m[1]);
        if (d < dmin) { dmin = d; b[0] = t[k][0]; b[1] = t[k][1]; }
        if (d > dmax) dmax = d;
    }
    if (dmin < 0.25f * dmax) { out[0] = b[0]; out[1] = b[1]; } else { out[0] = m[0]; out[1] = m[1]; }
}

static void test_single_tap(void)
{
    static char buf[64 * 1024];

    /* the soft-focus kernel: unit 0 changes, unit 1 (read once) does not */
    program(k_soft, buf, sizeof buf);
    compile_ok(buf, "soft (as written)");
    int r = rsx_fp_apply_single_tap(buf, sizeof buf, 0x3u, 0);
    CHECK(r == 1, "soft: %d units changed, want 1", r);
    CHECK(count(buf, "rsx_tex[0].Sample(rsx_samp[0], rsx_tap0)") == 4, "soft: every unit-0 tap reads rsx_tap0");
    CHECK(count(buf, "rsx_tex[0].Sample(rsx_samp[0], ((input.") == 0, "soft: a unit-0 tap kept its coordinate");
    CHECK(count(buf, "rsx_tex[1].Sample(rsx_samp[1], ((input.tc4).xyzw).xy)") == 1, "soft: unit 1 changed");
    CHECK(count(buf, "float2 rsx_tap0 = (") == 1, "soft: the centre is computed once");
    CHECK(strstr(buf, "float2 rsx_tap0") > strstr(buf, "float4 main(PSInput input) : SV_TARGET {"),
          "soft: the centre is computed inside main");
    CHECK(strstr(buf, "float2 rsx_tap0") < strstr(buf, "float4 r[48]"), "soft: the centre comes first in main");
    CHECK(count(buf, "rsx_TEX") == 0, "soft: a marker was left");
    compile_ok(buf, "soft (one tap)");
    { char again[sizeof buf]; memcpy(again, buf, sizeof buf);
      CHECK(rsx_fp_apply_single_tap(again, sizeof again, 0x1u, 0) == 0, "soft: a second pass changes it again");
      CHECK(strcmp(again, buf) == 0, "soft: a second pass changed the text"); }

    /* a dependent read stays as it is (the coordinate is not an interpolant) */
    program(k_dependent, buf, sizeof buf);
    { char before[sizeof buf]; memcpy(before, buf, sizeof buf);
      CHECK(rsx_fp_apply_single_tap(buf, sizeof buf, 0x1u, 0) == 0, "dependent: changed");
      CHECK(strcmp(before, buf) == 0, "dependent: the text changed"); }

    /* one distinct coordinate, a unit outside the mask, a cube unit: unchanged */
    program(k_same, buf, sizeof buf);
    { char before[sizeof buf]; memcpy(before, buf, sizeof buf);
      CHECK(rsx_fp_apply_single_tap(buf, sizeof buf, 0x1u, 0) == 0, "same coordinate: changed");
      CHECK(rsx_fp_apply_single_tap(buf, sizeof buf, 0x2u, 0) == 0, "unit outside the program: changed");
      CHECK(strcmp(before, buf) == 0, "the text changed"); }
    program(k_soft, buf, sizeof buf);
    { char before[sizeof buf]; memcpy(before, buf, sizeof buf);
      CHECK(rsx_fp_apply_single_tap(buf, sizeof buf, 0x1u, 0x1u) == 0, "cube unit: changed");
      CHECK(rsx_fp_apply_single_tap(buf, sizeof buf, 0, 0) == 0, "empty mask: changed");
      CHECK(strcmp(before, buf) == 0, "the text changed"); }

    /* no room: -1, never a write past the buffer */
    { const size_t need = strlen(k_head) + strlen(k_soft) + 1;
      char* tight = (char*)malloc(need + 8);
      program(k_soft, tight, need + 8);
      memset(tight + need, 0x5A, 8);
      CHECK(rsx_fp_apply_single_tap(tight, (u32)need, 0x1u, 0) == -1, "no room: not -1");
      CHECK(tight[need] == 0x5A && tight[need + 7] == 0x5A, "no room: wrote past the buffer");
      free(tight); }

    /* the centre rule: a kernel with a centre tap picks it; a symmetric one takes the mean */
    { const float soft[4][2] = { {0, 0}, {0, -2}, {-1, 1.732f}, {1, 1.732f} };    /* centre + three around it */
      const float kawase[4][2] = { {-1.5f, -1.5f}, {1.5f, -1.5f}, {-1.5f, 1.5f}, {1.5f, 1.5f} };
      const float two[2][2] = { {0, 0}, {4, 0} };                                   /* two taps: the mean */
      float c[2];
      centre(soft, 4, c);
      CHECK(c[0] == 0 && c[1] == 0, "soft kernel: centre %g %g, want the centre tap", c[0], c[1]);
      centre(kawase, 4, c);
      CHECK(fabsf(c[0]) < 1e-6f && fabsf(c[1]) < 1e-6f, "diagonal kernel: centre %g %g, want the mean", c[0], c[1]);
      centre(two, 2, c);
      CHECK(c[0] == 2 && c[1] == 0, "two taps: %g %g, want the mean", c[0], c[1]); }
}

int main(void)
{
    HMODULE dc = LoadLibraryA("d3dcompiler_47.dll");
    g_compile = dc ? (d3dcompile_fn)(void*)GetProcAddress(dc, "D3DCompile") : NULL;
    test_tap_mask();
    test_single_tap();
    printf("D3DCompile: %s (%d programs compiled)\n", g_compile ? "used" : "not on this PC", g_compiled);
    if (g_fails) {
        printf("FAIL %d of %d checks\n", g_fails, g_checks);
        return 1;
    }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
