/* ps3recomp patch 0114: the four-lane VMX float ops (vaddfp, vsubfp, vmaddfp, vnmsubfp) against the scalar
 * loops they replace (ppu_vmx.h *_scalar), bit for bit. Built twice by tests/test_vmx_vec.py: for the x86-64
 * baseline (ppu_fmaf_soft: double product, TwoSum, round to odd) and for x86-64-v3 (vfmadd), each with
 * -ffp-contract=off as the lifted code.
 *
 *     vmx_vec_test check N     N random cases per op and VSCR[NJ] setting, plus every pair/triple of the
 *                              special values; aliased destinations; exit 1 on any difference
 *     vmx_vec_test bench       ns per vmaddfp, vector and scalar
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <windows.h>
#include "ppu_vmx.h"

#ifndef PPU_VMX_VEC
#error "ppu_vmx.h has no four-lane float ops (patch 0114)"
#endif

static uint64_t s = 0x9E3779B97F4A7C15ull;
static uint32_t xr(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return (uint32_t)(s >> 11); }

static const uint32_t SPECIAL[] = {
    0x00000000u, 0x80000000u, 0x00000001u, 0x80000001u, 0x007FFFFFu, 0x807FFFFFu, 0x00400000u, 0x00800000u,
    0x80800000u, 0x00800001u, 0x3F800000u, 0xBF800000u, 0x3F800001u, 0x3F7FFFFFu, 0x40000000u, 0x7F7FFFFFu,
    0xFF7FFFFFu, 0x7F000000u, 0x7F800000u, 0xFF800000u, 0x7FC00000u, 0xFFC00000u, 0x7F800001u, 0x7FBFFFFFu,
    0xFFFFFFFFu, 0x33800000u, 0x34000000u, 0xB3800000u, 0x4B000000u, 0x4B000001u, 0x0C800000u, 0x26800000u};
#define NSPECIAL (int)(sizeof SPECIAL / sizeof SPECIAL[0])

static uint32_t word(void)
{
    const uint32_t r = xr();
    switch (r & 7) {
    case 0: return SPECIAL[(r >> 3) % NSPECIAL];
    case 1: return (r & 0x807FFFFFu) | (((r >> 23) & 3u) << 23);            /* denormal and tiny */
    case 2: return (r & 0x807FFFFFu) | ((250u + ((r >> 23) & 7u)) << 23);   /* huge, Inf, NaN */
    case 3: return (r & 0x807FFFFFu) | ((110u + (xr() % 40u)) << 23);        /* ordinary */
    case 4: return (r & 0x80000000u) | 0x3F800000u | (xr() & 0x7Fu);         /* near 1: cancellation */
    default: return xr() ^ (xr() << 21);
    }
}
static void put(uint8_t* v, int i, uint32_t w) { vmx_sw(v, i, w); }

typedef void (*f2)(void*, const void*, const void*, uint32_t);
typedef void (*f3)(void*, const void*, const void*, const void*, uint32_t);
static void w_add(void* d, const void* a, const void* b, uint32_t v) { vmx_vaddfp(d, a, b, v); }
static void w_add_s(void* d, const void* a, const void* b, uint32_t v) { vmx_vaddfp_scalar(d, a, b, v); }
static void w_sub(void* d, const void* a, const void* b, uint32_t v) { vmx_vsubfp(d, a, b, v); }
static void w_sub_s(void* d, const void* a, const void* b, uint32_t v) { vmx_vsubfp_scalar(d, a, b, v); }
static void w_mad(void* d, const void* a, const void* b, const void* c, uint32_t v) { vmx_vmaddfp(d, a, b, c, v); }
static void w_mad_s(void* d, const void* a, const void* b, const void* c, uint32_t v) { vmx_vmaddfp_scalar(d, a, b, c, v); }
static void w_nms(void* d, const void* a, const void* b, const void* c, uint32_t v) { vmx_vnmsubfp(d, a, b, c, v); }
static void w_nms_s(void* d, const void* a, const void* b, const void* c, uint32_t v) { vmx_vnmsubfp_scalar(d, a, b, c, v); }

static long long differ, cases;
static void report(const char* op, const uint8_t* a, const uint8_t* b, const uint8_t* c, const uint8_t* x,
                   const uint8_t* y, uint32_t vscr, int alias)
{
    if (differ++ < 12) {
        printf("DIFFER %s nj=%d alias=%d:", op, (vscr & VMX_NJ) != 0, alias);
        for (int i = 0; i < 4; i++)
            printf(" [%08x %08x %08x -> vec %08x scalar %08x]", vmx_w(a, i), vmx_w(b, i), c ? vmx_w(c, i) : 0,
                   vmx_w(x, i), vmx_w(y, i));
        printf("\n");
    }
}
/* alias: 0 = separate destination, 1 = d is a, 2 = d is b, 3 = d is c */
static void one2(const char* op, f2 v, f2 sc, const uint8_t* a, const uint8_t* b, uint32_t vscr, int alias)
{
    uint8_t x[16], y[16], va[16], vb[16];
    memcpy(va, a, 16); memcpy(vb, b, 16);
    if (alias == 1) { v(va, va, vb, vscr); memcpy(x, va, 16); memcpy(va, a, 16); sc(va, va, vb, vscr); memcpy(y, va, 16); }
    else if (alias == 2) { v(vb, va, vb, vscr); memcpy(x, vb, 16); memcpy(vb, b, 16); sc(vb, va, vb, vscr); memcpy(y, vb, 16); }
    else { v(x, a, b, vscr); sc(y, a, b, vscr); }
    cases++;
    if (memcmp(x, y, 16)) report(op, a, b, NULL, x, y, vscr, alias);
}
static void one3(const char* op, f3 v, f3 sc, const uint8_t* a, const uint8_t* b, const uint8_t* c, uint32_t vscr,
                 int alias)
{
    uint8_t x[16], y[16], t[3][16];
    memcpy(t[0], a, 16); memcpy(t[1], b, 16); memcpy(t[2], c, 16);
    if (alias) {
        uint8_t* dst = t[alias - 1];
        v(dst, t[0], t[1], t[2], vscr); memcpy(x, dst, 16);
        memcpy(t[0], a, 16); memcpy(t[1], b, 16); memcpy(t[2], c, 16);
        sc(dst, t[0], t[1], t[2], vscr); memcpy(y, dst, 16);
    } else { v(x, a, b, c, vscr); sc(y, a, b, c, vscr); }
    cases++;
    if (memcmp(x, y, 16)) report(op, a, b, c, x, y, vscr, alias);
}
static void all_ops(const uint8_t* a, const uint8_t* b, const uint8_t* c, uint32_t vscr, int alias)
{
    one2("vaddfp", w_add, w_add_s, a, b, vscr, alias > 2 ? 0 : alias);
    one2("vsubfp", w_sub, w_sub_s, a, b, vscr, alias > 2 ? 0 : alias);
    one3("vmaddfp", w_mad, w_mad_s, a, b, c, vscr, alias);
    one3("vnmsubfp", w_nms, w_nms_s, a, b, c, vscr, alias);
}

static int check(long long n)
{
    uint8_t a[16], b[16], c[16];
    for (int nj = 0; nj < 2; nj++) {
        const uint32_t vscr = nj ? VMX_NJ : 0;
        /* every special triple, each in all four lanes (lanes rotate the roles) */
        for (int i = 0; i < NSPECIAL; i++)
            for (int j = 0; j < NSPECIAL; j++)
                for (int k = 0; k < NSPECIAL; k++) {
                    for (int l = 0; l < 4; l++) {
                        put(a, l, SPECIAL[(i + l) % NSPECIAL]); put(b, l, SPECIAL[(j + 3 * l) % NSPECIAL]);
                        put(c, l, SPECIAL[(k + 5 * l) % NSPECIAL]);
                    }
                    all_ops(a, b, c, vscr, 0);
                }
        for (long long t = 0; t < n; t++) {
            for (int l = 0; l < 4; l++) { put(a, l, word()); put(b, l, word()); put(c, l, word()); }
            if ((t & 7) == 0)            /* b = -(a*c) rounded: exact or near cancellation */
                for (int l = 0; l < 4; l++) {
                    float fa, fc; uint32_t wa = vmx_w(a, l), wc = vmx_w(c, l);
                    memcpy(&fa, &wa, 4); memcpy(&fc, &wc, 4);
                    float p = -(fa * fc); uint32_t wp; memcpy(&wp, &p, 4);
                    put(b, l, wp ^ (xr() & 3u));
                }
            if ((t & 7) == 1)            /* a*c + b just off a halfway point of b's float: the double sum lands on
                                            it and only round to odd gives the right single (rounding twice does not) */
                for (int l = 0; l < 4; l++) {
                    const int e = (int)(xr() % 60u) - 30;                    /* product exponent */
                    const uint32_t sa = xr() & 0x80000000u, sc = xr() & 0x80000000u;
                    const uint32_t wa = sa | ((uint32_t)(127 + e / 2) << 23) | (1u << 3);          /* 1 + 2^-20 */
                    const uint32_t wc = sc | ((uint32_t)(126 + e - e / 2) << 23) | 0x7FFFF8u;    /* 2 - 2^-20 = 2(1 - 2^-21) */
                    /* product ~ 2^e (1 + 2^-20)(1 - 2^-21) * 2 ... its top bit at 2^(e+1); b one float ulp of 2^(e+2) above */
                    const uint32_t wb = (xr() & 0x80000000u) | ((uint32_t)(127 + e + 24) << 23) | (xr() & 0x7FFFFFu);
                    put(a, l, wa); put(c, l, wc); put(b, l, (xr() & 1) ? wb : (wb ^ 0x80000000u));
                }
            all_ops(a, b, c, vscr, (int)(t & 3));
        }
    }
    printf("%lld cases (4 ops, NJ off and on, aliased destinations), differ %lld\n", cases, differ);
    return differ != 0;
}

static double bench(f3 f)
{
    static uint8_t v[64][16];
    for (int i = 0; i < 64; i++) for (int l = 0; l < 4; l++) put(v[i], l, 0x3F000000u | (xr() & 0x7FFFFFu));
    LARGE_INTEGER t0, t1, fq; QueryPerformanceFrequency(&fq); QueryPerformanceCounter(&t0);
    const int n = 20000000;
    static uint8_t out[64][16];
    for (int i = 0; i < n; i++) f(out[i & 63], v[i & 63], v[(i + 1) & 63], v[(i + 2) & 63], VMX_NJ);
    QueryPerformanceCounter(&t1);
    return (double)(t1.QuadPart - t0.QuadPart) / fq.QuadPart * 1e9 / n;
}

int main(int argc, char** argv)
{
    if (argc > 1 && !strcmp(argv[1], "bench")) {
        const double v = bench(w_mad), sc = bench(w_mad_s);
        printf("vmaddfp ns vector %.2f scalar %.2f\n", v, sc);
        return 0;
    }
    return check(argc > 2 ? atoll(argv[2]) : 2000000);
}
