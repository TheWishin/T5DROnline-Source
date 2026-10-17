/*
 * Indirect-call interposer (ps3recomp patch 0016: ps3_icall_hook) used two ways:
 *
 *   - the DRAW CUT: while a frame is re-simulated, the engine's draw-packet
 *     submission functions (reached through vtables only, see docs/ROLLBACK.md
 *     section 6) are routed to a stub that returns 0, so a re-simulated frame
 *     runs the fight logic without building a picture nobody will see;
 *   - per-target inclusive/exclusive timing of every vtable call on the main
 *     thread (T5_RB_ICALL_TIMING=1, over the sampled windows), which is how
 *     the cut set was found: the time a target costs minus what its own
 *     indirect callees cost.
 *
 * The hook is consulted on every indirect call of every thread, so it bails
 * on the thread id first (one compare); everything else happens only on the
 * main thread and only while a window or the cut is on.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <intrin.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <atomic>
#include <vector>
#include <algorithm>

#include "ppu_recomp.h"
#include "rb.h"

extern "C" uint8_t* vm_base;

extern "C" {
typedef int (*ps3_icall_hook_fn)(ppu_context* ctx, uint32_t target);
extern ps3_icall_hook_fn ps3_icall_hook;
void ps3_indirect_call_direct(ppu_context* ctx, uint32_t target);
}

namespace rb {

namespace {

/* ---- the cut set ------------------------------------------------------------- */
/* The built-in cut (NPUB30009 v01.00), found with the profiler and the
 * write-fault tracer and verified by the gameplay-hash test (docs/ROLLBACK.md
 * section 6): the two model-draw entry points (each fighter's draw traversal:
 * matrices, materials, the skinning job kick) and the NU::Draw packet
 * writers they and the stage/effect draws call. All return 0 to their
 * callers when live, so the stub returns 0 too. */
const uint32_t kDrawCut[] = {
    0x00387324, 0x003872A8,                                         /* model draw (vtable +0x34 of the model object) */
    0x00355C70, 0x00355B34, 0x003559E4, 0x00357F88,                 /* 16-byte packet moves / packet header */
    0x00389788, 0x00389820, 0x003898D0, 0x00389A88, 0x00389A0C,     /* packet builders */
    0x00389AA0, 0x0038988C, 0x00397AF8, 0x00354160, 0x00353E68,     /* packet builders, draw-list append */
    0x00158D6C, 0x001357A0, 0x001EC6FC, 0x0009DC04, 0x00264220,     /* stage / effect / shadow draw passes (vtable targets; gameplay hash unchanged without them) */
};
/* The draw thread's side of it (NU::Draw request manager, the thread that
 * turns the lists into GCM commands): its per-packet handlers, cut on every
 * thread but the main one while re-simulating. The lists a re-simulated
 * frame still produces (packets pushed by direct calls) are then skipped
 * instead of processed, and the main thread's two waits on the draw thread
 * (sys_cond_wait in 0x357714, sys_event_queue_receive in 0x380A10) collapse
 * from 1.5 + 0.7-8 ms to ~0.3 ms (run d2, docs/ROLLBACK.md section 10).
 * T5_RB_CUT2=addr,... overrides, T5_RB_CUT2=none disables. */
const uint32_t kDrawCut2[] = {
    0x00392498, 0x00392334, 0x003552E0, 0x00397B54, 0x00385DBC, 0x0032659C, 0x00359A08, 0x0035E998, 0x0035933C,
    0x00389914, 0x00389B28, 0x00355B78, 0x00385814, 0x0039229C, 0x00364CDC, 0x0036432C, 0x00362FDC, 0x0035ACEC,
};
/* Open-addressed set of guest targets; read on the hot path, written at setup. */
constexpr uint32_t kSetN = 1024;
uint32_t g_cut_key[kSetN];
uint32_t g_cut2_key[kSetN];                  /* T5_RB_CUT2: targets cut on the OTHER threads (the draw thread's packet handlers) */
std::atomic<bool> g_cut_on{ false };
std::atomic<uint64_t> g_cut_hits{ 0 }, g_cut2_hits{ 0 };
uint32_t g_cut_count = 0, g_cut2_count = 0;
uint64_t g_tm_tid = 0;                       /* T5_RB_ICALL_TID: time this guest thread instead of the main thread */

/* The rand() shield. The draw passes call the C library's rand()/random()
 * (0x369228, state 0x1074F218 + the lagged generators behind it, 0x10C bytes
 * -- the range the gameplay hash covers) on some stages (18, 24: every
 * frame), so a re-simulated frame without the draw left the generator in a
 * different state from the original frame and the fight's own rand() users
 * diverged. On live frames every cut target now runs with the generator
 * swapped to a private copy (the draw keeps its own random stream) and the
 * fight's state is put back afterwards: the draw can no longer touch it, on
 * either peer, so re-simulating without the draw reproduces it. Nested cut
 * targets share the outermost swap. T5_RB_RANDSHIELD=0 disables it. */
constexpr uint32_t kRandState = 0x1074F218u, kRandLen = 0x10Cu;
bool g_shield = false, g_shield_init = false;   /* T5_RB_RANDSHIELD=1: swap the rand() state around the cut targets on live frames (not needed: the draw does not call rand(), see rb_state.cpp kGameSkip) */
uint8_t g_shield_priv[kRandLen];
int g_shield_depth = 0;
std::atomic<uint64_t> g_shield_calls{ 0 };

inline uint32_t slot_of(uint32_t t) { return (t * 2654435761u) & (kSetN - 1); }
bool set_has(const uint32_t* keys, uint32_t t)
{
    for (uint32_t i = slot_of(t), n = 0; n < kSetN; n++, i = (i + 1) & (kSetN - 1)) {
        if (keys[i] == t) return true;
        if (!keys[i]) return false;
    }
    return false;
}
void set_add(uint32_t* keys, uint32_t* count, uint32_t t)
{
    if (!t || set_has(keys, t)) return;
    for (uint32_t i = slot_of(t), n = 0; n < kSetN; n++, i = (i + 1) & (kSetN - 1))
        if (!keys[i]) { keys[i] = t; (*count)++; return; }
}
inline bool cut_has(uint32_t t) { return set_has(g_cut_key, t); }
inline void cut_add(uint32_t t) { set_add(g_cut_key, &g_cut_count, t); }

/* ---- timing ------------------------------------------------------------------- */
struct Tm { uint32_t key; uint32_t calls; uint64_t incl, excl; uint32_t ret0; };
constexpr uint32_t kTmN = 8192;
Tm g_tm[kTmN];
std::atomic<bool> g_tm_on{ false };
bool g_tm_enabled = false;
struct Frame { uint32_t target; uint64_t t0, children; };
Frame g_stk[1024];
int g_sp = 0;
uint64_t g_tsc_hz = 0;

Tm& tm_slot(uint32_t t)
{
    for (uint32_t i = (t * 2654435761u) & (kTmN - 1);; i = (i + 1) & (kTmN - 1)) {
        if (g_tm[i].key == t || g_tm[i].key == 0) { g_tm[i].key = t; return g_tm[i]; }
    }
}

/* ---- the hook ----------------------------------------------------------------- */
int hook(ppu_context* ctx, uint32_t target)
{
    if (ctx->thread_id != main_tid()) {
        if (g_cut2_count && g_cut_on.load(std::memory_order_relaxed) && set_has(g_cut2_key, target)) {
            ctx->gpr[3] = 0;
            g_cut2_hits.fetch_add(1, std::memory_order_relaxed);
            return 1;
        }
        if (!g_tm_tid || ctx->thread_id != g_tm_tid) return 0;
    } else {
        if (cut_has(target)) {
            if (g_cut_on.load(std::memory_order_relaxed)) {
                ctx->gpr[3] = 0;
                g_cut_hits.fetch_add(1, std::memory_order_relaxed);
                return 1;
            }
            if (g_shield && !g_tm_on.load(std::memory_order_relaxed)) {
                if (g_shield_depth++ == 0) {
                    uint8_t live[kRandLen];
                    if (!g_shield_init) { g_shield_init = true; memcpy(g_shield_priv, vm_base + kRandState, kRandLen); }
                    memcpy(live, vm_base + kRandState, kRandLen);
                    memcpy(vm_base + kRandState, g_shield_priv, kRandLen);
                    ps3_indirect_call_direct(ctx, target);
                    memcpy(g_shield_priv, vm_base + kRandState, kRandLen);
                    memcpy(vm_base + kRandState, live, kRandLen);
                    g_shield_calls.fetch_add(1, std::memory_order_relaxed);
                } else {
                    ps3_indirect_call_direct(ctx, target);
                }
                g_shield_depth--;
                return 1;
            }
        }
        if (g_tm_tid) return 0;
    }
    if (!g_tm_on.load(std::memory_order_relaxed) || g_sp >= 1024) return 0;
    Frame& f = g_stk[g_sp++];
    f.target = target; f.children = 0; f.t0 = __rdtsc();
    ps3_indirect_call_direct(ctx, target);
    const uint64_t dt = __rdtsc() - f.t0;
    g_sp--;
    Tm& t = tm_slot(target);
    t.calls++; t.incl += dt; t.excl += dt - f.children; t.ret0 += (uint32_t)ctx->gpr[3] == 0;
    if (g_sp > 0) g_stk[g_sp - 1].children += dt;
    return 1;
}

uint64_t tsc_hz()
{
    if (g_tsc_hz) return g_tsc_hz;
    LARGE_INTEGER f, a, b; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&a);
    const uint64_t t0 = __rdtsc();
    do { QueryPerformanceCounter(&b); } while ((b.QuadPart - a.QuadPart) * 50 < f.QuadPart);
    const uint64_t t1 = __rdtsc();
    g_tsc_hz = (t1 - t0) * (uint64_t)f.QuadPart / (uint64_t)(b.QuadPart - a.QuadPart);
    return g_tsc_hz;
}

} // namespace

void icall_install()
{
    static bool done = false;
    if (done) return;
    done = true;
    if (const char* e = getenv("T5_RB_ICALL_TIMING")) g_tm_enabled = *e == '1';
    if (const char* e = getenv("T5_RB_RANDSHIELD")) g_shield = *e != '0';
    if (g_shield) note("rand() shield around the draw passes: on");
    if (const char* e = getenv("T5_RB_ICALL_TID")) g_tm_tid = (uint64_t)atoi(e);
    const char* spec2 = getenv("T5_RB_CUT2");
    if (spec2 && !strcmp(spec2, "none")) { note("draw-thread cut: disabled (T5_RB_CUT2=none)"); }
    else if (spec2 && *spec2) {
        const char* p = spec2;
        while (*p) { char* z; uint32_t a = (uint32_t)strtoul(p, &z, 16); if (z == p) break; set_add(g_cut2_key, &g_cut2_count, a); p = z; while (*p == ',' || *p == ' ') p++; }
        note("draw-thread cut: %u targets from T5_RB_CUT2", g_cut2_count);
    } else {
        for (uint32_t t : kDrawCut2) set_add(g_cut2_key, &g_cut2_count, t);
        note("draw-thread cut: %u built-in targets", g_cut2_count);
    }
    /* T5_RB_CUT: "addr,addr,..." (hex) replaces the built-in cut set; "none"
     * disables the cut (the resim then costs a full frame, as in phase 1). */
    const char* spec = getenv("T5_RB_CUT");
    if (spec && !strcmp(spec, "none")) { note("draw cut: disabled (T5_RB_CUT=none)"); }
    else if (spec && *spec) {
        const char* p = spec;
        while (*p) { char* z; uint32_t a = (uint32_t)strtoul(p, &z, 16); if (z == p) break; cut_add(a); p = z; while (*p == ',' || *p == ' ') p++; }
        note("draw cut: %u targets from T5_RB_CUT", g_cut_count);
    } else {
        for (uint32_t t : kDrawCut) cut_add(t);
        note("draw cut: %u built-in targets", g_cut_count);
    }
    ps3_icall_hook = hook;
}

void cut_set(bool on) { g_cut_on = on; }
uint64_t cut_hits() { return g_cut_hits.load() + g_cut2_hits.load(); }

void icall_timing_start()
{
    if (!g_tm_enabled) return;
    g_sp = 0;
    g_tm_on = true;
}

void icall_timing_stop(const char* tag)
{
    if (!g_tm_enabled || !g_tm_on) return;
    g_tm_on = false;
    const double ms = 1000.0 / (double)tsc_hz();
    std::vector<const Tm*> v;
    uint64_t total_excl = 0;
    for (const Tm& t : g_tm) if (t.key) { v.push_back(&t); total_excl += t.excl; }
    std::sort(v.begin(), v.end(), [](const Tm* a, const Tm* b) { return a->excl > b->excl; });
    logline("I --- %s: %zu targets, %.2f ms exclusive in total, sorted by exclusive time ---", tag, v.size(), total_excl * ms);
    for (size_t i = 0; i < v.size() && i < 80; i++)
        logline("I %08X calls %u ret0 %u incl %.3f ms excl %.3f ms", v[i]->key, v[i]->calls, v[i]->ret0, v[i]->incl * ms, v[i]->excl * ms);
    std::sort(v.begin(), v.end(), [](const Tm* a, const Tm* b) { return a->incl > b->incl; });
    logline("I --- %s: sorted by inclusive time ---", tag);
    for (size_t i = 0; i < v.size() && i < 60; i++)
        logline("I %08X calls %u ret0 %u incl %.3f ms excl %.3f ms", v[i]->key, v[i]->calls, v[i]->ret0, v[i]->incl * ms, v[i]->excl * ms);
    memset(g_tm, 0, sizeof g_tm);
}

} // namespace rb
