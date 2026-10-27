/*
 * The sound side across rollbacks (docs/ROLLBACK.md section 20).
 *
 * What the game does (NPUB30009 v01.00): the fight logic starts every sound
 * effect and voice through the game's sound manager, 0xAC594(group, id,
 * channel, flags, pos, handle_out), which hands it to the sound library's
 * play core (0x32886C / 0x328884 -> 0x3285B8) at once: the library allocates
 * one of its 192 tracks and sets it up. Once per frame the main loop's sound
 * update (0xAA1D4 -> 0xAA200, gated by the enable word 0x10065B70) runs the
 * game-side sound bookkeeping (0xAAA18, 0xAC424, 0x9BFE8) and then the
 * library's tick (0x32819C: every track's sequencer, envelopes, 3D pan, and
 * the commands to the SPU sound core). The library's state (tracks,
 * allocator, at 0x40049210 / 0x400017C0) lives in the first heap chunk, which
 * the rollback never restores: it is output state, like the sound core.
 *
 * The phase-9 loop zeroed the enable word in re-simulated frames. That kept
 * the library from ticking extra times, but (1) the fight logic's play calls
 * still ran in those frames -- a re-simulated frame started its sounds a
 * second time, and (2) the game-side bookkeeping skipped the re-simulated
 * frames on one peer and ran them live on the other, so what the sound side
 * hands the fight (handles, intro records) went apart between the peers.
 *
 * T5_RB_SOUND=resim (the default) does what Tekken 6 Native Online's 2.2.4
 * does: the sound update runs in re-simulated frames like in any other frame,
 * and no sound is started twice --
 *   - every play call is logged per frame: group, channel, flags, id (for
 *     channel-less sounds), the handle it wrote back and its return value;
 *   - a rollback pass re-simulates frames g..f-1. In it, a play call that
 *     finds an entry no run of this pass has matched yet -- in its own frame,
 *     or the nearest frame of the pass when the corrected timeline moved the
 *     sound by a frame or two -- is not passed on: the sound started the
 *     first time keeps playing, and the handle it got is written back where
 *     the game expects it, so the fight state is what it was after the first
 *     run. A play call with no entry is a sound of the corrected timeline and
 *     starts now (late by the rollback depth). An entry no run of the pass
 *     asked for again is a sound of the mispredicted timeline: it plays on,
 *     nothing is cut;
 *   - the library's other calls the game makes (see kApi): a stop is never
 *     applied in a re-simulated frame (repeats of the first run's stops were
 *     done already; a stop only the corrected timeline makes would cut a
 *     sound); a music/bank event a run of the pass made already is not
 *     repeated (a music switch issued twice made the stream reader abort in
 *     phase 7); the status query gets the answer the first run of the frame
 *     got for the same handle;
 *   - the library's tick is skipped in re-simulated frames (it runs exactly
 *     once per displayed frame, like the sound core: the tracks are output
 *     state and must not advance faster because frames were re-simulated).
 * Voices (channel >= 0) are matched without their id: the game picks a voice
 * variation from the C rand(), which a side thread consumes at its own pace,
 * so a re-simulated frame may ask for another variation of the same voice.
 *
 * The calls are reached through entry detours of the lifted functions
 * (rb_detour.cpp); only main-thread calls are matched.
 *
 * T5_RB_SOUND=skip is the phase-9 behaviour, T5_RB_SOUND=raw runs everything
 * in re-simulated frames (no dedupe, the tick too) -- both for comparison.
 * T5_RB_SNDTRACE=1 logs every play call, library call and tick to rb_sound.log
 * (tools/rollback_sound_compare.py reads it).
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../platform/t5_win.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <array>
#include <utility>

#include "sys_ppu_thread.h"
#include "rb.h"
#include "rb_detour.h"

extern "C" uint8_t* vm_base;

namespace rb {

namespace {
constexpr uint32_t kGamePlaySE = 0x000AC594;   /* game sound manager: play(group, id, ch, flags, pos, handle_out) */
constexpr uint32_t kLibTick    = 0x0032819C;   /* sound library: per-frame update of the 192 tracks */
GuestFn o_play = nullptr, o_tick = nullptr;
SoundMode g_mode = SoundMode::Skip;
bool g_installed = false, g_trace_on = false;
FILE* g_trace = nullptr;

struct Entry {
    int32_t grp, ch, id; uint32_t flags; bool pos;
    uint32_t out;                 /* guest address of the handle the call wrote (0 = none) */
    uint32_t out_val;             /* ... and the value it wrote */
    uint64_t ret;
    bool used;                    /* matched (or made) by a run in the current rollback pass */
    bool orphan;                  /* counted as orphaned already */
};
constexpr uint32_t kFrames = 128, kPerFrame = 24;
struct FrameLog { uint32_t tag; uint32_t n; Entry e[kPerFrame]; };
FrameLog g_log[kFrames];

uint32_t g_frame = 0, g_last_live = 0; bool g_resim = false;
uint32_t g_pass_from = 0, g_pass_to = 0;   /* the frames the current rollback pass re-simulates */
SoundStats g_st;

bool same_key(const Entry& e, int32_t grp, int32_t ch, int32_t id, uint32_t flags, bool pos)
{
    if (e.grp != grp || e.ch != ch || e.flags != flags || e.pos != pos) return false;
    return ch >= 0 || e.id == id;   /* voices on a channel: any variation is the same voice */
}

/* frames of the pass, nearest to f first: f, f-1, f+1, f-2, ... */
template <class F> bool nearest_in_pass(uint32_t f, F try_frame)
{
    const uint32_t span = g_pass_to >= g_pass_from ? g_pass_to - g_pass_from : 0;
    for (uint32_t d = 0; d <= span; d++) {
        if (f >= g_pass_from + d && f - d <= g_pass_to && try_frame(f - d)) return true;
        if (d && f + d <= g_pass_to && f + d >= g_pass_from && try_frame(f + d)) return true;
    }
    return false;
}

bool g_novoice = false;   /* T5_RB_SND_NOVOICE=1 (audio tests): the fighters' voices are not started */

void h_play(ppu_context* ctx)
{
    if (ctx->thread_id != main_tid()) { o_play(ctx); return; }
    const int32_t grp = (int32_t)ctx->gpr[3], id = (int32_t)ctx->gpr[4], ch = (int32_t)ctx->gpr[5];
    /* The voices (group 5 on channel 1 for P1, group 6 on channel 2 for P2)
     * are picked, and played at all, by a draw from the C rand(), which a side
     * thread consumes at its own pace: they differ from run to run and between
     * the two PCs. An onset count of the sound effects leaves them out. */
    if (g_novoice && ((grp == 5 && ch == 1) || (grp == 6 && ch == 2))) { ctx->gpr[3] = 0; return; }
    const uint32_t flags = (uint32_t)ctx->gpr[6];
    const bool pos = (uint32_t)ctx->gpr[7] != 0;
    const uint32_t out = (uint32_t)ctx->gpr[8];
    FrameLog& L = g_log[g_frame % kFrames];
    if (L.tag != g_frame + 1) { L.tag = g_frame + 1; L.n = 0; }

    if (g_mode == SoundMode::Resim && g_resim) {
        /* a sound some run of this pass's frames started -- this frame's own
         * first run, or a neighbour's when the corrected timeline moved it by
         * a frame or two -- keeps playing */
        Entry* hit = nullptr; uint32_t hit_f = 0;
        nearest_in_pass(g_frame, [&](uint32_t k) {
            FrameLog& K = g_log[k % kFrames];
            if (K.tag != k + 1) return false;
            for (uint32_t i = 0; i < K.n; i++)
                if (!K.e[i].used && same_key(K.e[i], grp, ch, id, flags, pos)) { hit = &K.e[i]; hit_f = k; return true; }
            return false;
        });
        if (hit) {
            hit->used = true;
            if (out && hit->out == out) wr32(out, hit->out_val);
            ctx->gpr[3] = hit->ret;
            g_st.deduped++;
            if (hit_f != g_frame) g_st.deduped_moved++;
            if (g_trace) fprintf(g_trace, "D %u grp=%d id=%d (first run: %d at %u) ch=%d f=%x pos=%d out=%x\n", g_frame, grp, id, hit->id, hit_f, ch, flags, pos ? 1 : 0, out);
            return;
        }
    }
    o_play(ctx);
    if (g_resim) g_st.started_resim++; else g_st.started_live++;
    if (L.n < kPerFrame) {
        Entry& e = L.e[L.n++];
        e.grp = grp; e.ch = ch; e.id = id; e.flags = flags; e.pos = pos;
        e.out = out; e.out_val = out ? rd32(out) : 0; e.ret = ctx->gpr[3]; e.used = true; e.orphan = false;
    } else g_st.log_full++;
    if (g_trace) fprintf(g_trace, "%c %u grp=%d id=%d ch=%d f=%x pos=%d out=%x -> %x late=%u\n", g_resim ? 'N' : 'G', g_frame, grp, id, ch, flags, pos ? 1 : 0, out,
                         out ? rd32(out) : 0, g_resim ? g_last_live + 1 - g_frame : 0);
}

/* ---- the library's other entry points: stops, the status query, events ----
 * A re-simulated frame repeats whatever its first run told the library. A
 * stop or an event (music, bank) some run of this pass's frames already made
 * (same function, same arguments; the nearest frame first) is not passed on
 * again and gets that run's return value. A stop no earlier run made is the
 * corrected timeline's: it is not applied either (a rollback never cuts a
 * sound -- what the mispredicted frames started plays on, and live frames stop
 * what they stop). An event no earlier run made goes through (the corrected
 * timeline changes the music). A status query gets the answer the first run
 * of the same frame got for the same handle, so the re-simulated frame sees
 * the sound as it was at that frame, not as it is now. */
enum class Kind { Stop, Query, Event };
struct ApiFn { uint32_t addr; int nargs; Kind kind; const char* name; };
const ApiFn kApi[] = {
    { 0x00328CC4, 1, Kind::Stop,  "stop group" },        /* from 0xACABC / 0xAD1C8 (round transitions, throws) */
    { 0x00328D68, 1, Kind::Stop,  "stop handle" },       /* from 0xAC798 */
    { 0x00326C34, 1, Kind::Query, "status of handle" },  /* from 0xAC83C */
    { 0x003349B0, 2, Kind::Event, "stream event" },      /* from 0xAAF44 (music) */
    { 0x00334628, 2, Kind::Event, "stream event" },      /* from 0xAAE74 */
    { 0x0033465C, 1, Kind::Event, "stream event" },      /* from 0xA9C18 / 0xAAE74 (r3 only) */
    { 0x003271DC, 2, Kind::Event, "bank event" },        /* from 0xAA4C0 */
    { 0x00329158, 1, Kind::Event, "bank event" },        /* from 0xAA344 / 0xAADE0 (r3 only: r4 is whatever the last call left) */
    { 0x00331E20, 1, Kind::Event, "bank event" },        /* from 0xA99F0 / 0xA9CC4 (r3, r5 = 0) */
    { 0x003270E0, 1, Kind::Event, "bank event" },        /* from 0xA99F0 / 0xA9CC4 (r3 and f1) */
};
constexpr int kApiN = (int)(sizeof kApi / sizeof kApi[0]);
GuestFn o_api[kApiN];
bool g_api_on[kApiN];

struct Call { uint8_t fn; bool used; uint64_t a[2]; uint64_t ret; };
constexpr uint32_t kCallsPerFrame = 32;
struct CallLog { uint32_t tag; uint32_t n; Call c[kCallsPerFrame]; };
CallLog g_calls[kFrames];

void api_call(int i, ppu_context* ctx)
{
    if (ctx->thread_id != main_tid() || g_mode != SoundMode::Resim) { o_api[i](ctx); return; }
    const ApiFn& fn = kApi[i];
    uint64_t a[2] = { ctx->gpr[3], fn.nargs > 1 ? ctx->gpr[4] : 0 };
    CallLog& L = g_calls[g_frame % kFrames];
    if (L.tag != g_frame + 1) { L.tag = g_frame + 1; L.n = 0; }
    if (g_resim) {
        Call* hit = nullptr;
        auto look = [&](uint32_t k) {
            CallLog& K = g_calls[k % kFrames];
            if (K.tag != k + 1) return false;
            for (uint32_t j = 0; j < K.n; j++)
                if (!K.c[j].used && K.c[j].fn == i && K.c[j].a[0] == a[0] && K.c[j].a[1] == a[1]) { hit = &K.c[j]; return true; }
            return false;
        };
        if (fn.kind == Kind::Query) look(g_frame); else nearest_in_pass(g_frame, look);
        if (hit) {
            hit->used = true;
            ctx->gpr[3] = hit->ret;
            if (fn.kind == Kind::Stop) g_st.stops_kept++; else if (fn.kind == Kind::Query) g_st.queries_replayed++; else g_st.events_kept++;
            if (g_trace) fprintf(g_trace, "R %u %s %06X %llx %llx -> %llx (an earlier run's)\n", g_frame, fn.name, fn.addr, (unsigned long long)a[0], (unsigned long long)a[1], (unsigned long long)hit->ret);
            return;
        }
        if (fn.kind == Kind::Stop) {
            g_st.stops_suppressed++;
            ctx->gpr[3] = 0;
            if (g_trace) fprintf(g_trace, "S %u %s %06X %llx not applied (re-simulated frame)\n", g_frame, fn.name, fn.addr, (unsigned long long)a[0]);
            return;
        }
        if (fn.kind == Kind::Event) g_st.events_new++;
    }
    o_api[i](ctx);
    if (L.n < kCallsPerFrame) { Call& c = L.c[L.n++]; c.fn = (uint8_t)i; c.used = true; c.a[0] = a[0]; c.a[1] = a[1]; c.ret = ctx->gpr[3]; }
    else g_st.log_full++;
    if (g_trace) fprintf(g_trace, "%c %u %s %06X %llx %llx -> %llx\n", g_resim ? 'n' : 'g', g_frame, fn.name, fn.addr, (unsigned long long)a[0], (unsigned long long)a[1], (unsigned long long)ctx->gpr[3]);
}
template <int I> void api_hook(ppu_context* ctx) { api_call(I, ctx); }
template <int... I> constexpr std::array<GuestFn, sizeof...(I)> make_api_hooks(std::integer_sequence<int, I...>) { return { &api_hook<I>... }; }

void h_tick(ppu_context* ctx)
{
    if (g_mode == SoundMode::Resim && g_resim && ctx->thread_id == main_tid()) {
        g_st.ticks_skipped++;
        ctx->gpr[3] = 0;
        return;
    }
    if (g_trace && ctx->thread_id == main_tid()) fprintf(g_trace, "U %u %d\n", g_frame, g_resim ? 1 : 0);
    o_tick(ctx);
}
} // namespace

SoundMode sound_mode() { return g_mode; }

void sound_install()
{
    static bool done = false;
    if (done) return;
    /* the game-DLL build publishes the lifted table when the DLL is loaded,
     * after static init: then this runs again from the loop's start */
    if (!detour_ready()) { note("sound: lifted code not loaded yet -- the sound hooks go in when the rollback loop starts"); return; }
    done = true;
    const char* m = getenv("T5_RB_SOUND");
    g_mode = SoundMode::Resim;
    if (m && !strcmp(m, "skip")) g_mode = SoundMode::Skip;
    else if (m && !strcmp(m, "raw")) g_mode = SoundMode::Raw;
    /* legacy switches of the test mode / the loop: "do not skip" = raw */
    if (!m && ((getenv("T5_RB_SKIPSOUND") && *getenv("T5_RB_SKIPSOUND") == '0') || (getenv("T5_RB_NET_SKIPSOUND") && *getenv("T5_RB_NET_SKIPSOUND") == '0')))
        g_mode = SoundMode::Raw;
    { const char* nv = getenv("T5_RB_SND_NOVOICE"); g_novoice = nv && *nv == '1'; }
    const char* t = getenv("T5_RB_SNDTRACE");
    g_trace_on = t && *t == '1';
    if (g_trace_on) g_trace = fopen("rb_sound.log", "w");
    if (g_mode == SoundMode::Resim || g_trace_on) {
        g_installed = detour(kGamePlaySE, h_play, &o_play) && detour(kLibTick, h_tick, &o_tick);
        static const auto hooks = make_api_hooks(std::make_integer_sequence<int, kApiN>{});
        for (int i = 0; i < kApiN && g_installed; i++) {
            g_api_on[i] = detour(kApi[i].addr, hooks[i], &o_api[i]);
            if (!g_api_on[i] && kApi[i].kind != Kind::Event) g_installed = false;   /* stops and the query are required; an event we cannot see is logged */
        }
        if (!g_installed && g_mode == SoundMode::Resim) {
            g_mode = SoundMode::Skip;
            note("sound: the play/tick detours could not be installed -- falling back to skipping the sound update in re-simulated frames");
        }
    }
    sndheap_install();
    calltrace_install();
    shadowtrace_install();   /* T5_RB_SHADOW_TRACE=1 (diagnostics, rb_shadowtrace.cpp) */
    note("sound in re-simulated frames: %s", g_mode == SoundMode::Resim ? "resim (update runs, starts deduplicated, library tick once per displayed frame)"
                                            : g_mode == SoundMode::Skip ? "skip (sound update off)" : "raw (everything runs again)");
}

void sound_begin_frame(uint32_t f, bool resim)
{
    if (resim && !g_resim) {
        /* a rollback pass begins: frames f .. the last live frame run again;
         * what their earlier runs started and told the library is up for
         * matching once more */
        g_pass_from = f; g_pass_to = g_last_live;
        for (uint32_t k = g_pass_from; k <= g_pass_to; k++) {
            FrameLog& K = g_log[k % kFrames];
            if (K.tag == k + 1) for (uint32_t i = 0; i < K.n; i++) K.e[i].used = false;
            CallLog& C = g_calls[k % kFrames];
            if (C.tag == k + 1) for (uint32_t i = 0; i < C.n; i++) C.c[i].used = false;
        }
    } else if (!resim && g_resim) {
        /* the pass is over: a sound an earlier run started that no run of the
         * pass asked for again belongs to the mispredicted timeline -- it plays on */
        for (uint32_t k = g_pass_from; k <= g_pass_to; k++) {
            FrameLog& K = g_log[k % kFrames];
            if (K.tag != k + 1) continue;
            for (uint32_t i = 0; i < K.n; i++)
                if (!K.e[i].used && !K.e[i].orphan) {
                    K.e[i].orphan = true; g_st.orphaned++;
                    if (g_trace) fprintf(g_trace, "O %u grp=%d id=%d ch=%d f=%x\n", k, K.e[i].grp, K.e[i].id, K.e[i].ch, K.e[i].flags);
                }
        }
    }
    g_frame = f; g_resim = resim;
    if (!resim) {   /* first run of f */
        g_last_live = f;
        g_log[f % kFrames].tag = f + 1; g_log[f % kFrames].n = 0;
        g_calls[f % kFrames].tag = f + 1; g_calls[f % kFrames].n = 0;
    }
}

void sound_reset()
{
    g_resim = false;
    g_frame = g_last_live = g_pass_from = g_pass_to = 0;
    for (uint32_t k = 0; k < kFrames; k++) { g_log[k].tag = 0; g_log[k].n = 0; g_calls[k].tag = 0; g_calls[k].n = 0; }
}

SoundStats sound_stats(bool reset)
{
    SoundStats s = g_st;
    if (reset) g_st = SoundStats();
    return s;
}

} // namespace rb
