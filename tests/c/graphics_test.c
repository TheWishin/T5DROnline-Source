/*
 * Unit test of the graphics settings for weak graphics cards (ps3recomp patch 0079,
 * libs/video/rsx_fp_decompiler.c; docs/RENDER_PERF.md "Graphics settings for weak graphics cards"):
 *
 *   rsx_fp_apply_shadow_compare   a shadow sampler (a depth texture read with a depth compare) becomes
 *                                 rsx_shadow2d(...); with zfunc bit 16 (PS3_SHADOWS=0) the call returns what
 *                                 an empty map gives -- the far plane (1.0) compared with the reference --
 *                                 and the texture is not read. Without bit 16 the program is the one patch
 *                                 0073 and earlier wrote, byte for byte.
 *
 * The fragment program here is written for this test (in the decompiler's output form), not taken from a
 * game. Both forms are compiled with D3DCompile (ps_5_0) when d3dcompiler_47.dll is on this PC.
 *
 *   graphics_test      prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * The runtime file is included as it is (some of its functions are static). Built by
 * tests/test_graphics_settings.py with clang-cl or cl.
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

/* A lit material in the form Tekken 5 DR's use: the colour texture on unit 0, the shadow map on unit 2
 * read projectively (TXP) into r2, then diffuse * (1 - r2). */
static const char k_lit[] =
    "float4 main(PSInput input) : SV_TARGET {\n"
    "    float4 r[48]; float4 h[48];\n"
    "    [unroll] for (int _i = 0; _i < 48; _i++) { r[_i] = (float4)0; h[_i] = (float4)0; }\n"
    "    { float4 _v = (float4)(rsx_tex[0].Sample(rsx_samp[0], ((input.tc0).xyzw).xy)); r[0].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(rsx_tex[2].Sample(rsx_samp[2], ((input.tc2).xyzw).xy / ((input.tc2).xyzw).w)); r[2].xyzw = _v.xyzw; }\n"
    "    { float4 _v = (float4)(((r[0]).xyzw) * (1.0 - (r[2]).xxxx)); h[0].xyzw = _v.xyzw; }\n"
    "    float4 _o = h[0];\n"
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

/* the helper's compare, as the HLSL does it (rsx_zcmp) */
static float zcmp(float d, float r, int f)
{
    return f == 1 ? (float)(d < r) : f == 2 ? (float)(d == r) : f == 3 ? (float)(d <= r) :
           f == 4 ? (float)(d > r) : f == 5 ? (float)(d != r) : f == 6 ? (float)(d >= r) : f == 7 ? 1.0f : 0.0f;
}

static void test_shadows(void)
{
    static char on[16384], off[16384];
    u32 zf[16] = {0};
    snprintf(on, sizeof on, "%s%s", k_head, k_lit);
    snprintf(off, sizeof off, "%s%s", k_head, k_lit);

    /* shadows on (patch 0073 and earlier): LESS, fixed-point depth (bit 8), linear (PCF) */
    zf[2] = 1u | 8u;
    CHECK(rsx_fp_apply_shadow_compare(on, sizeof on, 1u << 2, zf, 1u << 2, 0) == 1, "on: one call site");
    CHECK(count(on, "rsx_shadow2d(rsx_tex[2], rsx_samp[2], ((input.tc2).xyzw), 1, 9, 1)") == 1,
          "on: the call (projective, func 9, linear)\n%s", on);
    CHECK(count(on, "rsx_tex[0].Sample(rsx_samp[0]") == 1, "on: unit 0 untouched");
    compile_ok(on, "shadows on");

    /* shadows off: zfunc bit 16 -- the same call with func 25, the helper returns before any read */
    zf[2] = 1u | 8u | 16u;
    CHECK(rsx_fp_apply_shadow_compare(off, sizeof off, 1u << 2, zf, 1u << 2, 0) == 1, "off: one call site");
    CHECK(count(off, "rsx_shadow2d(rsx_tex[2], rsx_samp[2], ((input.tc2).xyzw), 1, 25, 1)") == 1,
          "off: the call (func 25)\n%s", off);
    CHECK(count(off, "if (f & 16) return (float4)rsx_zcmp(1.0, r, f & 7);") == 1, "off: the helper's early return");
    {   /* the early return comes after the reference is made and clamped, before the texture is read */
        const char* ret = strstr(off, "if (f & 16)");
        const char* clamp = strstr(off, "if (f & 8) r = saturate(r);");
        const char* gather = strstr(off, "GatherRed");
        CHECK(ret && clamp && gather && clamp < ret && ret < gather, "off: order of clamp / return / read");
    }
    compile_ok(off, "shadows off");

    /* an empty map: lit for the compare the game uses (texel LESS ref = in shadow), at every reference
     * depth of a fixed-point map (clamped to [0, 1]) */
    for (int i = 0; i <= 20; i++) {
        const float r = (float)i / 20.0f;
        CHECK(zcmp(1.0f, r, 1) == 0.0f, "LESS: an empty map shadows ref %g", r);
        CHECK(zcmp(1.0f, r, 3) == (r >= 1.0f ? 1.0f : 0.0f), "LEQUAL at ref %g", r);
    }

    /* the other units and the unchanged parts of the program stay byte-identical between on and off */
    {
        const char* a = strstr(on, "float4 main(PSInput");
        const char* b = strstr(off, "float4 main(PSInput");
        CHECK(a && b, "main present");
        const char* p = b ? strstr(b, ", 25, 1)") : NULL;
        if (a && p) {           /* the only difference in main: the func number of the call */
            char mb[4096];
            snprintf(mb, sizeof mb, "%.*s, 9, 1)%s", (int)(p - b), b, p + strlen(", 25, 1)"));
            CHECK(strcmp(a, mb) == 0, "main differs elsewhere:\n%s\n---\n%s", a, mb);
        }
    }
}

int main(void)
{
    HMODULE dc = LoadLibraryA("d3dcompiler_47.dll");
    g_compile = dc ? (d3dcompile_fn)(void*)GetProcAddress(dc, "D3DCompile") : NULL;
    test_shadows();
    printf("D3DCompile: %s (%d programs compiled)\n", g_compile ? "used" : "not on this PC", g_compiled);
    if (g_fails) {
        printf("FAIL %d of %d checks\n", g_fails, g_checks);
        return 1;
    }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
