/*
 * The title's thread-local random generator, made a function of the match
 * (desync hunt, docs/NETPLAY.md "Desync hunt").
 *
 * 0x3AFC3C is the generator most of the game draws from: a shuffled LCG
 * (x * 0x19660D + 0x3C6EF35F, a 32-word Bays-Durham table) kept in the
 * calling thread's TLS -- TLS+0 the state, +0x10094 a "seeded" byte, +0x10098
 * the last draw, +0x1009C the table; every draw is made by the main thread, so
 * it is the main thread's TLS block (0x0E000000). Netplay reseeded the
 * Mersenne Twister and the C rand() at its sync points, never this one, and
 * two kinds of callers share it:
 *
 *   - the scene (menus, the game mode, the fight: the scene task 0x10BD8 ->
 *     0x25D708 -> 0x54A34 -> 0x5160C -> 0x15498): the fighters, their move
 *     effects, the camera (0x878CC: the angle and distance of a camera move,
 *     drawn here) and the game mode's set-up at FIGHT START;
 *   - the effect and stage tasks beside it (0x108C0 -> 0xB8370 / 0x9DD90 /
 *     0x1FBE08, and 0x268418's stage emitter 0xA1768, ~10 draws a frame):
 *     particles, and bursts of 9-11 draws when an effect first plays -- on
 *     the frame its data has come in from the file thread, which no loader
 *     drain waits for, so a frame or a few apart on two PCs (runs t4_a/t4_b:
 *     the burst at frame 470 in one run, 477 in the other).
 *
 * So the camera of the fight drew numbers that depended on (a) the whole
 * history of the process -- a game that had played other opponents and one
 * just started began FIGHT START with different states (the owner's 1.0.0
 * logs: every frame different from the first compared one, after an opponent
 * switch) -- and (b) when effect data finished loading. The camera itself is
 * left out of the netplay hashes as cosmetic, but it is not: the camera-
 * projected screen x of the fighters (+0x6C8 of a fighter block, 0x10090708 /
 * 0x10090FD8, also left out) decides at 0x808D8 which of them stands on the
 * left (+0x1C2/+0x1C3), and with it which way an up or down tap sidesteps. Two
 * PCs with different camera draws turned the same sidestep different ways and
 * the fight came apart (runs r1/r2/s1: two runs of one scripted match, no
 * network, no rollback, the camera and then the fighters' input apart from
 * frame 1546).
 *
 * The fix (tls_rand_install, tls_rand_reseed):
 *   - the scene draws from the TLS generator as before; every other draw on
 *     the main thread (outside the scene task) comes from a private generator
 *     in host memory, so effects and stage emitters cannot move the scene's
 *     sequence, whenever they run (and a rollback's draw cut, which skips some
 *     of them in re-simulated frames, cannot either);
 *   - netplay reseeds the TLS generator at every sync point (frame 0 of a
 *     session, every scene barrier) from the match seed, like the Twister and
 *     rand(), so the history of the process no longer reaches the match.
 * T5_TLS_RAND=0 turns both off (the old behaviour, for comparisons).
 *
 * Diagnostics: T5_RAND_TRACE=1 counts rand() (0x369228) and TLS-generator calls
 * per thread and caller (rb_rand.log, every 10 s), =2 logs each distinct
 * caller chain of the TLS generator once, =3 per frame how many draws came
 * from inside the fight update (0x15498) and from elsewhere, and the state.
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
#include <tuple>

#include "ppu_recomp.h"
#include "rb.h"
#include "rb_detour.h"

extern "C" uint32_t t5_df_mode_cur(void);    /* src/directfight/df_fight.cpp: the mode manager's current / next mode */
extern "C" uint32_t t5_df_mode_next(void);

namespace rb {

namespace {
constexpr uint32_t kRand = 0x369228u;        /* C library rand(): traced only */
constexpr uint32_t kTlsRand = 0x3AFC3Cu;     /* the TLS generator */
constexpr uint32_t kSceneTask = 0x10BD8u;    /* the scene task's update: menus, game mode, fight */
constexpr uint32_t kTlsSeeded = 0x10094u, kTlsLast = 0x10098u, kTlsTable = 0x1009Cu;
constexpr uint32_t kA = 0x19660Du, kC = 0x3C6EF35Fu;

GuestFn o_rand = nullptr, o_tls_rand = nullptr, o_scene = nullptr;
bool g_on = true, g_isolating = false;
int g_trace = 0;
thread_local int t_scene = 0;                /* main thread: inside the scene task */
std::atomic<uint64_t> g_private_draws{ 0 };

/* the private generator: the same algorithm, in host memory (main thread only) */
struct Shuffle { uint32_t s = 0x6E5D3C2Bu, last = 0, tab[32] = {}; bool init = false; } g_priv;
uint32_t priv_draw()
{
    Shuffle& p = g_priv;
    if (!p.init) {
        for (int i = 0; i < 8; i++) p.s = p.s * kA + kC;
        for (int i = 0; i < 32; i++) { p.s = p.s * kA + kC; p.tab[i] = p.s; }
        p.last = p.tab[31];
        p.init = true;
    }
    p.s = p.s * kA + kC;
    const uint32_t i = p.last & 31;
    p.last = p.tab[i];
    p.tab[i] = p.s;
    return p.last & 0x3FFFFFFFu;
}

/* ---- diagnostics (T5_RAND_TRACE) ---- */
std::mutex g_mu;
std::map<std::pair<uint64_t, uint32_t>, uint64_t> g_calls;                    /* rand(): (thread, caller) */
std::map<std::tuple<uint64_t, uint32_t, uint32_t>, uint64_t> g_tls_calls;     /* TLS generator: (thread, r13, caller) */
ULONGLONG g_last_dump = 0;
FILE* g_log = nullptr;
FILE* trace_log() { if (!g_log) g_log = fopen("rb_rand.log", "w"); return g_log; }

void trace_dump_locked()
{
    const ULONGLONG now = GetTickCount64();
    if (now - g_last_dump < 10000) return;
    g_last_dump = now;
    FILE* f = trace_log();
    if (!f) return;
    fprintf(f, "--- calls by guest thread and caller (last 10 s), main thread %llu, private draws %llu\n",
            (unsigned long long)main_tid(), (unsigned long long)g_private_draws.load());
    for (auto& kv : g_calls) fprintf(f, "rand(): tid %llu lr %08X calls %llu\n", (unsigned long long)kv.first.first, kv.first.second,
                                     (unsigned long long)kv.second);
    for (auto& kv : g_tls_calls) fprintf(f, "TLS rng: tid %llu r13 %08X lr %08X calls %llu\n", (unsigned long long)std::get<0>(kv.first),
                                         std::get<1>(kv.first), std::get<2>(kv.first), (unsigned long long)kv.second);
    fflush(f);
    g_calls.clear(); g_tls_calls.clear();
}

void trace_tls(ppu_context* ctx, bool priv)
{
    std::lock_guard<std::mutex> lk(g_mu);
    g_tls_calls[{ ctx->thread_id, priv ? 0u : (uint32_t)ctx->gpr[13], (uint32_t)ctx->lr }]++;
    if (g_trace == 3) {
        static uint32_t cur = UINT32_MAX, nf = 0, no = 0, np = 0;
        const uint32_t f = sim_frame();
        if (f != cur) {
            if (cur != UINT32_MAX && trace_log())
                fprintf(g_log, "F %u fight %u other %u private %u state %08X\n", cur, nf, no, np,
                        _byteswap_ulong(*(const uint32_t*)(vm_base + (uint32_t)ctx->gpr[13] - 0x7000u)));
            cur = f; nf = no = np = 0;
        }
        if (priv) np++;
        else if (guest_backtrace(16).find("func_00015498") != std::string::npos) nf++;
        else no++;
    }
    if (g_trace == 2) {
        static std::map<std::string, int> chains;
        std::string c = guest_backtrace(24);
        if (chains[c]++ == 0 && trace_log())
            fprintf(g_log, "TLS rng chain (frame %u, mode %u->%u, phase %u%s): %s\n", sim_frame(), t5_df_mode_cur(), t5_df_mode_next(),
                    _byteswap_ulong(*(const uint32_t*)(vm_base + 0x1008F070u)), priv ? ", private" : "", c.c_str());
    }
    trace_dump_locked();
}

void h_scene(ppu_context* ctx)
{
    t_scene++;
    o_scene(ctx);
    t_scene--;
}

void h_tls_rand(ppu_context* ctx)
{
    const bool priv = g_isolating && t_scene == 0 && ctx->thread_id == main_tid();
    if (g_trace) trace_tls(ctx, priv);
    if (priv) {
        ctx->gpr[3] = (uint64_t)priv_draw();
        g_private_draws.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    o_tls_rand(ctx);
}

void h_rand(ppu_context* ctx)
{
    { std::lock_guard<std::mutex> lk(g_mu); g_calls[{ ctx->thread_id, (uint32_t)ctx->lr }]++; trace_dump_locked(); }
    o_rand(ctx);
}
} // namespace

/* Main thread, before the scene runs (static init in the exe build; the
 * game-DLL build: the first frame boundary, once the lifted table is out). */
void rand_install()
{
    static bool done = false;
    if (done || !detour_ready()) return;
    done = true;
    { const char* e = getenv("T5_TLS_RAND"); g_on = !(e && *e == '0'); }
    { const char* e = getenv("T5_RAND_TRACE"); g_trace = (e && *e >= '1' && *e <= '3') ? *e - '0' : 0; }
    if (g_trace) note("rand(): calls traced (T5_RAND_TRACE=%d): %s", g_trace, detour(kRand, h_rand, &o_rand) ? "yes" : "not detourable");
    if (!g_on && !g_trace) return;
    const bool scene = g_on && detour(kSceneTask, h_scene, &o_scene);
    const bool tls = detour(kTlsRand, h_tls_rand, &o_tls_rand);
    g_isolating = g_on && scene && tls;
    note("TLS random generator: %s", g_isolating ? "the scene's own stream; effect and stage draws from a private one (T5_TLS_RAND=0: shared)"
                                     : !g_on ? "shared (T5_TLS_RAND=0)" : "the detours could not be installed -- one shared stream (desyncs possible)");
}

/* Netplay's sync points (frame 0 of a session, every scene barrier): the TLS
 * generator of the main thread (its TLS block at tls_base) starts over from the
 * seed -- its state word, and the "seeded" byte cleared, so the next draw fills
 * the table from it as the game's first draw ever did. */
void tls_rand_reseed(uint32_t tls_base, uint32_t seed)
{
    if (!g_on || !tls_base || !vm_base) return;
    const uint32_t be = _byteswap_ulong(seed);
    memcpy(vm_base + tls_base, &be, 4);
    vm_base[tls_base + kTlsSeeded] = 0;
    memset(vm_base + tls_base + kTlsLast, 0, 4 + 32 * 4);
    (void)kTlsTable;
}

uint64_t rand_private_draws() { return g_private_draws.load(); }

namespace {
struct AutoInstall { AutoInstall() { rand_install(); } } g_auto;   /* the exe build: the table is there at static init */
}

} // namespace rb
