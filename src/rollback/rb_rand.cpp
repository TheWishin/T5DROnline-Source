/*
 * The C library rand() of the title, one generator per thread (desync hunt,
 * docs/NETPLAY.md "Desync hunt").
 *
 * rand() (0x369228: state = state * 0x6C078965 + 12345, the state word at
 * 0x1074F218 through the TOC slot r2+0x8C) is shared by the main thread's
 * fight and by a side thread -- a stage effect (0x12C558 <- 0x12CF34 <-
 * 0x1230AC) that draws at its own pace, a few to a few dozen times a second
 * depending on the stage. Which draw the main thread gets therefore depends
 * on how far the side thread got: on the other PC's speed, a hitch, a
 * rollback (the restore puts the word back, the side thread does not draw
 * again). The netplay hashes leave the word out (docs/ROLLBACK.md section 12)
 * because the fight never seemed to read it -- but it does: the voices
 * (+0x314 of a fighter block: whether and which grunt), and through the
 * fighters' secondary motion the camera, whose side decides which way an
 * up/down tap sidesteps (desync hunt runs r1/r2: two runs of one scripted
 * match in one process, no network, no rollback, parted at the camera after
 * ~1550 frames and then in the fighters' input).
 *
 * The fix: every thread but the main one draws from its own generator (the
 * same formula, its own state in host memory). The main thread's sequence then
 * depends on the main thread's draws alone -- the same on both PCs, re-made
 * exactly by a re-simulation -- and the side thread's effect stays what it
 * was, its own business. srand() from any thread seeds the shared word as
 * before (the netplay reseeds run on the main thread).
 *
 * T5_RAND_SPLIT=0 turns it off; T5_RAND_TRACE=1 counts the calls per guest
 * thread and caller (rb_rand.log, every 10 s).
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <atomic>
#include <map>
#include <mutex>
#include <string>

#include "ppu_recomp.h"
#include "rb.h"
#include "rb_detour.h"

namespace rb {

namespace {
constexpr uint32_t kRand = 0x369228u;
GuestFn o_rand = nullptr;
bool g_split = true, g_trace = false, g_installed = false;
std::atomic<uint64_t> g_side_calls{ 0 };
thread_local uint32_t t_state = 0;
thread_local bool t_seeded = false;

std::mutex g_mu;
std::map<std::pair<uint64_t, uint32_t>, uint64_t> g_calls;   /* (guest thread, caller) -> calls */
ULONGLONG g_last_dump = 0;
FILE* g_log = nullptr;

void trace(ppu_context* ctx)
{
    std::lock_guard<std::mutex> lk(g_mu);
    g_calls[{ ctx->thread_id, (uint32_t)ctx->lr }]++;
    const ULONGLONG now = GetTickCount64();
    if (now - g_last_dump < 10000) return;
    g_last_dump = now;
    if (!g_log) g_log = fopen("rb_rand.log", "w");
    if (!g_log) return;
    fprintf(g_log, "--- rand() calls by guest thread and caller (last 10 s), main thread %llu\n", (unsigned long long)main_tid());
    for (auto& kv : g_calls) fprintf(g_log, "tid %llu lr %08X calls %llu\n", (unsigned long long)kv.first.first, kv.first.second, (unsigned long long)kv.second);
    fflush(g_log);
    g_calls.clear();
}

void h_rand(ppu_context* ctx)
{
    if (g_trace) trace(ctx);
    if (!g_split || ctx->thread_id == main_tid()) { o_rand(ctx); return; }
    if (!t_seeded) { t_state = 0x2545F491u ^ (uint32_t)(ctx->thread_id * 0x9E3779B9u); t_seeded = true; }
    t_state = t_state * 0x6C078965u + 12345u;
    ctx->gpr[3] = (uint64_t)(t_state & 0x7FFFFFFFu);   /* extsw + rldicl r3,r9,0,33: the low 31 bits */
    g_side_calls.fetch_add(1, std::memory_order_relaxed);
}
} // namespace

/* Main thread, before the game's threads draw (static init in the exe build;
 * the game-DLL build: the first frame boundary, once the lifted table is out). */
void rand_install()
{
    static bool done = false;
    if (done || !detour_ready()) return;
    done = true;
    { const char* e = getenv("T5_RAND_SPLIT"); g_split = !(e && *e == '0'); }
    { const char* e = getenv("T5_RAND_TRACE"); g_trace = e && *e == '1'; }
    if (!g_split && !g_trace) return;
    g_installed = detour(kRand, h_rand, &o_rand);
    note("rand(): %s", !g_installed ? "the detour could not be installed -- one shared generator (desyncs possible)"
                       : g_split ? "the main thread's own generator; other threads draw from theirs (T5_RAND_SPLIT=0: shared)"
                                 : "shared generator, calls traced (T5_RAND_TRACE)");
}

uint64_t rand_side_calls() { return g_side_calls.load(); }

namespace {
struct AutoInstall { AutoInstall() { rand_install(); } } g_auto;   /* the exe build: the table is there at static init */
}

} // namespace rb
