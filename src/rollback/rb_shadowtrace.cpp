/*
 * Diagnostics: the fighters' shadow box (stage-27 start desync hunt, 1.1.2).
 *
 * T5_RB_SHADOW_TRACE=1 logs every run of the shadow projector's fit
 * (0x15A3A0, called from the render pass 0x268418 -> 0x15A974) to
 * rb_shadow.log: the logical frame, re-simulated or not, the projector's
 * extents and eye/target after the fit, and per fighter the skeleton pointer
 * ([fighter+0x8A4]+0x10) with a hash of its bone block and the six bone
 * positions the fit reads. Two PCs' logs diff per frame to the input that
 * differs. Off by default; costs nothing then.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ppu_recomp.h"
#include "rb.h"
#include "rb_detour.h"
#include "rb_state.h"

extern "C" uint8_t* vm_base;

namespace rb {
namespace {
GuestFn g_orig = nullptr;
FILE* g_log = nullptr;
inline uint32_t r32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline float rf(uint32_t a) { uint32_t v = r32(a); float f; memcpy(&f, &v, 4); return f; }
uint64_t fnv(uint32_t a, uint32_t n)
{
    uint64_t h = 0xcbf29ce484222325ull;
    for (uint32_t i = 0; i < n; i++) { h ^= vm_base[a + i]; h *= 0x100000001b3ull; }
    return h;
}
void h_fit(ppu_context* ctx)
{
    const uint32_t obj = (uint32_t)ctx->gpr[3];
    g_orig(ctx);
    if (!g_log) return;
    fprintf(g_log, "S %u %d ph %u obj %08X ext %.6f %.6f %.6f %.6f eye %.6f %.6f %.6f tgt %.6f %.6f %.6f dir %.6f %.6f %.6f",
            sim_frame(), bypass_on() ? 1 : 0, r32(0x1008F070u), obj, rf(obj + 0x80), rf(obj + 0x84), rf(obj + 0x88), rf(obj + 0x8C),
            rf(obj + 0x50), rf(obj + 0x54), rf(obj + 0x58), rf(obj + 0x60), rf(obj + 0x64), rf(obj + 0x68),
            rf(obj + 0x70), rf(obj + 0x74), rf(obj + 0x78));
    for (int i = 0; i < 2; i++) {
        const uint32_t f = r32(0x10091AB0u + 4 * i);
        if (!f) continue;
        const uint32_t sk = r32(f + 0x8A4), bones = sk ? r32(sk + 0x10) : 0;
        /* x: how many of the bone block's pages (and the skeleton's) are left out of the rollback state right now (job pages) */
        uint32_t x = 0;
        if (bones) for (uint32_t pg = bones & ~0xFFFu; pg < bones + 0xD00; pg += 0x1000) x += excluded_page(pg) ? 1 : 0;
        if (sk && excluded_page(sk & ~0xFFFu)) x += 100;
        fprintf(g_log, " | P%d %08X sk %08X b %08X x %u h %016llx", i + 1, f, sk, bones, x, bones ? (unsigned long long)fnv(bones, 0xD00) : 0ull);
        static const uint32_t kOff[] = { 0x100, 0x220, 0x4F0, 0x730, 0xA00, 0xC40 };
        if (bones) for (uint32_t o : kOff) fprintf(g_log, " %.4f,%.4f,%.4f", rf(bones + o), rf(bones + o + 4), rf(bones + o + 8));
    }
    fprintf(g_log, " | rec %.6f %.6f %.6f %.6f | jobpages %u\n", rf(0x100996C8u), rf(0x100996CCu), rf(0x100996D0u), rf(0x100996D4u), state_job_pages());
    fflush(g_log);
}
} // namespace

/* Per boundary (rb_net.cpp boundary(), frames up to T5_RB_SHADOW_TRACE_TO, default 400): hashes of
 * the hashed regions taken whole (no skip list), of each fighter block, of
 * each fighter's bone block and of the shadow projector -- the last entry for
 * a frame is its final state (a rollback writes it again). */
void shadowtrace_boundary(uint32_t f, bool resim)
{
    static uint32_t to = 0;
    if (!g_log) return;
    if (!to) { const char* e = getenv("T5_RB_SHADOW_TRACE_TO"); to = e && *e ? (uint32_t)atoi(e) : 400; }
    if (f > to) return;
    fprintf(g_log, "B %u %d ph %u r %016llx %016llx %016llx %016llx", f, resim ? 1 : 0, r32(0x1008F070u),
            (unsigned long long)fnv(0x1008E000u, 0x4000), (unsigned long long)fnv(0x10099600u, 0x600),
            (unsigned long long)fnv(0x100A0900u, 0x200), (unsigned long long)fnv(0x100A3B00u, 0x300));
    for (int i = 0; i < 2; i++) {
        const uint32_t fb = r32(0x10091AB0u + 4 * i);
        if (!fb) { fprintf(g_log, " | P%d -", i + 1); continue; }
        const uint32_t sk = r32(fb + 0x8A4), bones = sk ? r32(sk + 0x10) : 0;
        fprintf(g_log, " | P%d %016llx b %016llx", i + 1, (unsigned long long)fnv(fb, 0x8D0), bones ? (unsigned long long)fnv(bones, 0xD00) : 0ull);
    }
    fprintf(g_log, " | prj %016llx\n", (unsigned long long)fnv(0x10627500u, 0xB0));
    fflush(g_log);
}

void shadowtrace_install()
{
    static bool done = false;
    if (done || !detour_ready()) return;
    const char* e = getenv("T5_RB_SHADOW_TRACE");
    if (!e || *e != '1') return;
    done = true;
    g_log = fopen("rb_shadow.log", "w");
    if (!detour(0x15A3A0u, h_fit, &g_orig)) { note("shadow trace: 0x15A3A0 not detourable"); return; }
    note("shadow trace: the shadow box fit 0x15A3A0 -> rb_shadow.log");
}

} // namespace rb
