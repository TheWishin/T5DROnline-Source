/* Rollback netplay loop -- see rb_net.h. */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <algorithm>
#include <atomic>

#include "rb.h"
#include "rb_state.h"
#include "rb_net.h"

extern "C" uint8_t* vm_base;
extern "C" void lat_log_(char kind, const char* fmt, ...);   /* ps3recomp patch 0034: PS3_LATENCY_LOG */
extern "C" volatile int g_lat_log_on;
#define LATLOG(...) do { if (g_lat_log_on) lat_log_(__VA_ARGS__); } while (0)
extern "C" int cellAtrac_rb_live_rings(uint32_t* ea, uint32_t* size, int cap);   /* patch 0024 */
extern "C" void cellAtrac_rb_rolled_back(void);   /* patch 0024/0025: the title's stream reader was rewound with it */
extern "C" int t5_df_game_mode(void);             /* src/directfight/df_fight.cpp: the game's mode manager is in the game mode (4) */

namespace rb { namespace net {

namespace {
constexpr uint32_t kMinVblanks = 0x106D4D98;  /* present pacing: min vblanks per frame (u64) */
bool g_enabled = false, g_active = false, g_verbose = false, g_skipsound = true;   /* T5_RB_NET_SKIPSOUND=0 keeps the sound update in re-simulated frames */
bool g_offered = false, g_timesync = true;
uint32_t g_start = 0, g_maxpred = 8;
/* Lockstep windows (every input confirmed before a frame runs, so nothing is
 * predicted and no rollback can later reach into them):
 *   T5_RB_NET_WARMUP      frames after the loop starts and after every next
 *                         match's sync point. 420 in phases 4-9, when a rollback
 *                         into the stage still streaming in broke the game (test
 *                         f1) and one across the intro phases left the peers a
 *                         phase apart (e150). With direct fight the intro rule
 *                         below covers both, so the default is 0 then.
 *   T5_RB_NET_LOAD_LOCK   frames after a load completed outside the intro (60).
 *   T5_RB_NET_PHASE_LOCK  frames after a fight phase change seen at a live
 *                         boundary. 600 in phases 6-9, because transitions
 *                         re-simulated with the sound update skipped came out a
 *                         phase apart (e50/g50, the round end). With the sound
 *                         side run in re-simulated frames (rb_sound.cpp) the KO,
 *                         round end and match end re-simulate like any frame;
 *                         the windows made the game crawl at high latency (input
 *                         delay 1, RTT 150: one-way latency per frame), so the
 *                         default is 0 (docs/ROLLBACK.md section 20). */
uint32_t g_warmup = 420;
uint32_t g_saved_minvb[2] = { 0, 1 };   /* the present's min vblanks (u64) before start() zeroed it */
uint32_t g_started_at = 0;
constexpr uint32_t kPhaseWord = 0x1008F070u;
uint32_t g_phase_lock = 0, g_lock_until = 0, g_last_phase = 0xFFFFFFFFu, g_phase_changes = 0;
uint32_t g_load_lock = 60;       /* T5_RB_NET_LOAD_LOCK: lockstep frames after a load completed (loader drain waited) */
uint32_t g_loads = 0;
/* The fight intro takes no input. From the match-start barrier to "Fight!"
 * the phase word is 7..12 (7: the game mode starts, 8-12: stage and character
 * intros, 17: fighting; select screens use 1-5). With direct fight, a frame
 * whose input is decided at a boundary in those phases gets neutral input on
 * both PCs -- this side sends neutral, and predicts neutral for the peer's
 * frames decided in the same phases (the intro runs on timers and loads, not
 * on input, so both PCs see the same phases at the same boundaries). The
 * intro then has no mispredictions, no rollback ever reaches into it, and the
 * loads that happen there (stage, characters, voice banks) need no lockstep:
 * the intro runs at full speed at any latency. T5_RB_NET_INTRO=0 turns it off. */
/* The game mode's first frames come before phase 7: the select mode hands
 * over with the phase word at 5, the game mode sets 0, then 2, then 7 (probe
 * of an offline fight: FIGHT START at phase 2, 7 one frame later). The first
 * boundary of a session (lockstep frame 0) is one of them: a press sampled
 * there went out (release dry run 0.1.6: the harness pressed at frame 2), the
 * peer had predicted neutral, rolled back 9 frames into the fight's first
 * loading frames, and its loading never finished -- the other PC waited at
 * the loading's end until it gave the match up. So in the game mode
 * (t5_df_game_mode(): mode 4) every phase up to 12 is intro; at a select
 * screen (mode 6, phases 0-5) the driver's presses must go through. */
bool g_intro_rule = false;
uint8_t  g_phase_at[4096]; uint32_t g_phase_tag[4096];   /* phase word at the boundary of frame f (before f ran) */
bool     g_intro_flag[4096];                             /* ... and whether that boundary was in the intro */
bool intro_phase(uint32_t p, bool game_mode) { return p <= 12 && (p >= 7 || game_mode); }
bool intro_at(uint32_t b) { return g_intro_rule && g_phase_tag[b % 4096] == b + 1 && g_intro_flag[b % 4096]; }
uint32_t g_intro_frames = 0;
double g_wait_acc_ms = 0;   /* time the next live frame waited for the peer (speed accounting) */
/* time sync */
constexpr int kLeadWinMax = 60;
int g_lead_win = 20, g_ts_interval = 10, g_ts_max = 2;
bool g_ts_flip = false;          /* T5_RB_NET_TS_FLIP=1: take the sleep in the flip wait (delays the whole pipeline; stalled run n9, off) */
LARGE_INTEGER g_t_frame0; uint32_t g_frames_timed = 0; double g_frame_ms = 1000.0 / 60.0;   /* measured frame time (last 60 live frames) */   /* T5_RB_NET_TS=win,interval,max: averaging window, frames between sleeps, max frames per sleep */
int g_lead_mine[kLeadWinMax], g_lead_theirs[kLeadWinMax]; int g_lead_n = 0;
uint32_t g_last_sleep_frame = 0;
int g_delay = 0;

/* per-frame history, by frame number */
constexpr uint32_t kHist = 4096;
uint64_t     g_hash[kHist];      uint32_t g_hash_tag[kHist];      /* H[f] at the boundary of f */
np::PadInput g_used[kHist];      uint32_t g_used_tag[kHist];      /* the remote input frame f was simulated with */
bool         g_pred[kHist];                                       /* ... and whether it was a prediction */

uint32_t g_checked = 0;          /* mispredictions resolved for frames < this */
/* T5_NET_DESYNC_DUMP=1: the gameplay bytes of the last 64 boundaries, written
 * to rb_desync_f<frame>.bin when the peer's hash for that frame differs (both
 * sides do; tools/netplay_memdiff.py diffs the two files) */
constexpr uint32_t kDumpFrames = 64, kDumpBytes = 0x6000;
bool g_dump = false; uint32_t g_dumps = 0;
uint8_t* g_dump_ring = nullptr; uint32_t g_dump_tag[kDumpFrames], g_dump_len[kDumpFrames];
uint32_t g_hash_sent = 0;        /* final hashes handed over for frames < this */
uint32_t g_floor = 0;            /* no rollback before this frame (start / scene barrier) */
np::PadInput g_last_remote = np::kNeutral;

/* early rollback (T5_RB_NET_EARLY, default on): see early_check() */
bool     g_early_on = true;
uint32_t g_next_f = 0;                   /* the frame of the next live boundary */
uint32_t g_early_f = UINT32_MAX;         /* that boundary began before its tick */
uint32_t g_early_committed = 0;          /* the next boundary's snapshot was taken early (early_commit) */
bool     g_tick_waited = false;
std::atomic<bool> g_early_tick_seen{ false };
LARGE_INTEGER g_early_last_check = {};
void (*g_tick_waiter)() = nullptr;
/* T5_RB_NET_SAMPLE=N: stack samples of the main thread over the first N
 * rollbacks' re-simulations ("S" lines in T5_RB_LOG, rb_sample.cpp) */
uint32_t g_sample_left = 0;
bool     g_sampling = false;
/* resim in progress */
bool     g_resim = false;
uint32_t g_resim_target = 0;     /* the live frame the resim returns to */
uint32_t g_resim_from = 0;
LARGE_INTEGER g_qpf, g_resim_t0;

/* statistics (reported every 300 frames) */
struct Stats {
    uint32_t frames = 0, rollbacks = 0, resim_frames = 0, max_depth = 0, stalls = 0, predicted = 0, sleeps = 0;
    uint32_t sound_zero = 0;
    double rollback_ms = 0, rollback_ms_max = 0, stall_ms = 0, commit_ms = 0, sleep_ms = 0, lead_sum = 0, restore_ms = 0;
    double stall_ms_lock = 0;   /* of stall_ms: waits in the lockstep windows (match start, loads, phase changes) */
    uint32_t early_rollbacks = 0;   /* rollbacks done before the frame's tick (early) */
    double early_commit_ms = 0;     /* snapshot time taken before the tick (early_commit) */
    double early_wait_ms = 0;       /* time an early boundary waited for its tick */
    uint32_t depth_hist[17] = {};
} g_st, g_tot;
LARGE_INTEGER g_t_window;

double ms_since(LARGE_INTEGER t0) { LARGE_INTEGER t; QueryPerformanceCounter(&t); return 1000.0 * (double)(t.QuadPart - t0.QuadPart) / (double)g_qpf.QuadPart; }

np::PadInput remote_for(uint32_t g, bool* predicted)
{
    np::PadInput in;
    if (np::rb_remote(g, &in)) { *predicted = false; g_last_remote = in; return in; }
    *predicted = true;
    if (g >= (uint32_t)g_delay && intro_at(g - (uint32_t)g_delay)) return np::kNeutral;   /* the peer sends neutral for it */
    return g_last_remote;   /* prediction: the last confirmed input repeats */
}

void inputs_for(uint32_t g, np::PadInput out[2])
{
    const int slot = np::local_slot();
    bool pred = false;
    np::PadInput rem = remote_for(g, &pred);
    g_used[g % kHist] = rem; g_used_tag[g % kHist] = g + 1; g_pred[g % kHist] = pred;
    if (pred) g_st.predicted++;
    out[slot] = np::rb_local(g);
    out[1 - slot] = rem;
}

/* displayed-frame times: wall time between two live boundaries (what the
 * player sees; a rollback's re-simulation lands in the frame it happens in) */
constexpr int kFtBins = 400;     /* 0.5 ms bins up to 200 ms */
uint32_t g_ft_win[kFtBins], g_ft_all[kFtBins];
LARGE_INTEGER g_t_live; bool g_t_live_ok = false;
void ft_add(double ms)
{
    int b = (int)(ms * 2.0); if (b < 0) b = 0; if (b >= kFtBins) b = kFtBins - 1;
    g_ft_win[b]++; g_ft_all[b]++;
}
double ft_pct(const uint32_t* h, double q)
{
    uint64_t n = 0; for (int i = 0; i < kFtBins; i++) n += h[i];
    if (!n) return 0;
    uint64_t want = (uint64_t)(q * (double)n), acc = 0;
    for (int i = 0; i < kFtBins; i++) { acc += h[i]; if (acc > want) return (i + 1) * 0.5; }
    return kFtBins * 0.5;
}

void report()
{
    const double win_ms = ms_since(g_t_window);
    QueryPerformanceCounter(&g_t_window);
    char hist[160]; int n = 0;
    for (int d = 1; d <= 16; d++) if (g_st.depth_hist[d]) n += snprintf(hist + n, sizeof hist - n, " %d:%u", d, g_st.depth_hist[d]);
    const SoundStats ss = sound_stats(true);
    note("rbnet: %u frames in %.1f s (%.1f fps), %u rollbacks (%u frames re-simulated, max depth %u, depth histogram%s), %.2f ms per rollback (max %.2f; "
         "restore %.2f ms of it), %u stalls (%.1f ms, %.1f ms of them in lockstep windows), %u frames ran on predicted input, %u time-sync sleeps (%.0f ms), avg advantage %.2f frames, commit avg %.2f ms, peer ack %u, desync mismatches %u, phase changes %u, "
         "sounds: %u started live, %u kept from a first run, %u new in re-simulated frames, %u from mispredicted frames played on, "
         "stops in re-simulated frames: %u repeats skipped, %u new not applied; %u status answers replayed; music/bank events: %u repeats skipped, %u new",
         g_st.frames, win_ms / 1000.0, g_st.frames * 1000.0 / (win_ms > 0 ? win_ms : 1), g_st.rollbacks, g_st.resim_frames, g_st.max_depth, n ? hist : " -",
         g_st.rollbacks ? g_st.rollback_ms / g_st.rollbacks : 0.0, g_st.rollback_ms_max,
         g_st.rollbacks ? g_st.restore_ms / g_st.rollbacks : 0.0, g_st.stalls, g_st.stall_ms, g_st.stall_ms_lock, g_st.predicted,
         g_st.sleeps, g_st.sleep_ms, g_st.frames ? g_st.lead_sum / g_st.frames : 0.0,
         g_st.frames ? g_st.commit_ms / g_st.frames : 0.0, np::rb_peer_ack(), np::rb_mismatches(), g_phase_changes,
         ss.started_live, ss.deduped, ss.started_resim, ss.orphaned, ss.stops_kept, ss.stops_suppressed, ss.queries_replayed, ss.events_kept, ss.events_new);
    note("rbnet: frame times (displayed frames) this window p50 %.1f ms p99 %.1f ms max %.1f ms; whole run p50 %.1f p99 %.1f; intro frames with neutral input %u, loads %u",
         ft_pct(g_ft_win, 0.5), ft_pct(g_ft_win, 0.99), ft_pct(g_ft_win, 0.99999), ft_pct(g_ft_all, 0.5), ft_pct(g_ft_all, 0.99), g_intro_frames, g_loads);
    { char cs[512]; state_commit_stats(cs, sizeof cs, true); note("rbnet: snapshots: %s", cs); }
    note("rbnet: early rollbacks (before the frame's tick, in the time it waited for it) %u of %u, %.1f ms waited for the tick after them; "
         "snapshots taken early %.2f ms per frame; direct-call cut hits %llu",
         g_st.early_rollbacks, g_st.rollbacks, g_st.early_wait_ms, g_st.frames ? g_st.early_commit_ms / g_st.frames : 0.0,
         (unsigned long long)dcut_hits());
    memset(g_ft_win, 0, sizeof g_ft_win);
    g_tot.frames += g_st.frames; g_tot.rollbacks += g_st.rollbacks; g_tot.resim_frames += g_st.resim_frames;
    g_tot.max_depth = std::max(g_tot.max_depth, g_st.max_depth); g_tot.stalls += g_st.stalls; g_tot.predicted += g_st.predicted;
    g_tot.rollback_ms += g_st.rollback_ms; g_tot.rollback_ms_max = std::max(g_tot.rollback_ms_max, g_st.rollback_ms_max);
    g_tot.stall_ms += g_st.stall_ms; g_tot.commit_ms += g_st.commit_ms; g_tot.sleeps += g_st.sleeps; g_tot.sleep_ms += g_st.sleep_ms;
    for (int d = 0; d < 17; d++) g_tot.depth_hist[d] += g_st.depth_hist[d];
    g_st = Stats();
}
} // namespace

/* rollback is on offer when T5_RB_MODE is unset or "net" (and netplay is on) */
bool offered_by_env()
{
    const char* m = getenv("T5_RB_MODE");
    const char* nm = getenv("T5_NET_MODE");
    const char* ctl = getenv("T5_CTL_DIR");
    if (ctl && *ctl) return !m || !*m || !strcmp(m, "net");   /* a persistent game: every session is a direct fight */
    if (!nm || !*nm) return false;
    /* The default online mode (rollback10, docs/ROLLBACK.md section 20: two
     * matches plus a rematch in one process at RTT 0/50/150 with 3 % loss, in
     * sync, sound started once). T5_RB_MODE=off (or lockstep) keeps the
     * delay-based lockstep; a peer that does not offer rollback (an older
     * build, or one with T5_RB_MODE=off) gets the lockstep on both sides. The
     * test modes (test, measure) are not netplay. The default covers the
     * online flow (the lobby starts the match with direct fight:
     * T5_NET_START=external); menu-driven sessions from boot keep the
     * lockstep, which re-aligns the menus' scene changes -- T5_RB_MODE=net
     * offers rollback there too. */
    if (!m || !*m) {
        const char* st = getenv("T5_NET_START");
        return st && !strcmp(st, "external");
    }
    return !strcmp(m, "net");
}

void offer()
{
    if (g_offered) return;
    g_offered = true;
    if (!offered_by_env()) return;
    {   /* the rollback state needs the write watch on the guest memory: without it, no offer (lockstep) */
        void* addrs[4]; ULONG_PTR count = 4; DWORD gran = 0;
        if (GetWriteWatch(0, vm_base + 0x10000000u, 0x1000, addrs, &count, &gran) != 0) {
            note("rbnet: guest memory has no write watch (PS3_VM_WRITE_WATCH) -- rollback not offered, the match runs in lockstep");
            return;
        }
    }
    np::rb_offer(true);
    note("rbnet: rollback offered to the peer (T5_RB_MODE=off keeps the delay-based lockstep)");
}

bool enabled()
{
    static int e = -1;
    if (e < 0) {
        e = offered_by_env() ? 1 : 0;
        if (e) {
            if (const char* s = getenv("T5_RB_NET_START")) { if (!strncmp(s, "frame:", 6)) g_start = (uint32_t)atoi(s + 6); else g_start = (uint32_t)atoi(s); }
            if (const char* s = getenv("T5_RB_NET_MAXPRED")) g_maxpred = (uint32_t)std::max(1, std::min(16, atoi(s)));
            if (const char* s = getenv("T5_RB_NET_PHASE_LOCK")) g_phase_lock = (uint32_t)atoi(s);
            if (const char* s = getenv("T5_RB_NET_LOAD_LOCK")) g_load_lock = (uint32_t)atoi(s);
            g_intro_rule = (getenv("T5_FIGHT") && *getenv("T5_FIGHT")) || (getenv("T5_FIGHT_FILE") && *getenv("T5_FIGHT_FILE")) ||
                           (getenv("T5_CTL_DIR") && *getenv("T5_CTL_DIR"));
            if (const char* s = getenv("T5_RB_NET_INTRO")) g_intro_rule = g_intro_rule && *s != '0';
            if (g_intro_rule) g_warmup = 0;   /* the intro takes no input: nothing there to wait for */
            if (const char* s = getenv("T5_RB_NET_WARMUP")) g_warmup = (uint32_t)atoi(s);
            if (const char* s = getenv("T5_NET_DESYNC_DUMP")) { g_dump = *s == '1'; if (g_dump) g_dump_ring = (uint8_t*)calloc(kDumpFrames, kDumpBytes); }
            if (const char* s = getenv("T5_RB_NET_LOG")) g_verbose = *s == '1';
            if (const char* s = getenv("T5_RB_NET_SAMPLE")) g_sample_left = (uint32_t)atoi(s);
            if (const char* s = getenv("T5_RB_NET_EARLY")) g_early_on = *s != '0';
            if (const char* s = getenv("T5_RB_NET_SKIPSOUND")) g_skipsound = *s != '0';
            if (const char* s = getenv("T5_RB_NET_TIMESYNC")) g_timesync = *s != '0';
            if (const char* s = getenv("T5_RB_NET_TS_FLIP")) g_ts_flip = *s == '1';
            if (const char* s = getenv("T5_RB_NET_TS")) {
                int w = 0, i = 0, m = 0;
                if (sscanf(s, "%d,%d,%d", &w, &i, &m) == 3) { g_lead_win = std::max(5, std::min(kLeadWinMax, w)); g_ts_interval = std::max(1, i); g_ts_max = std::max(1, std::min(8, m)); }
            }
            QueryPerformanceFrequency(&g_qpf);
        }
        g_enabled = e == 1;
    }
    /* agreed in the HELLO (both sides offer it); until the handshake is done this is false */
    return g_enabled && (g_active || np::rb_negotiated());
}
bool active() { return g_active; }
bool bypass() { return bypass_on(); }
uint32_t start_frame() { return g_start; }

void start(uint32_t f)
{
    if (g_active) return;
    sound_install();   /* no-op when static init could install it; the game-DLL build gets it here */
    dcut_install();
    g_delay = np::rb_apply_delay();
    np::rb_begin(f);
    if (g_skipsound && sound_word()) state_add_mask(sound_word(), 4);
    {   /* the full-state page hash is the test mode's; the peers compare the gameplay hash */
        const char* ph = getenv("T5_RB_NET_PAGEHASH");
        state_set_page_hashing(ph && *ph == '1');
    }
    state_init();
    g_saved_minvb[0] = rd32(kMinVblanks); g_saved_minvb[1] = rd32(kMinVblanks + 4);
    wr32(kMinVblanks, 0); wr32(kMinVblanks + 4, 0);   /* no vblank pacing in the present: re-simulated frames must not wait for one */
    g_active = true;
    g_started_at = f;
    g_next_f = f; g_early_f = UINT32_MAX; g_tick_waited = false; g_early_tick_seen = false;
    g_last_phase = rd32(kPhaseWord);
    g_checked = g_hash_sent = g_floor = f;
    g_last_remote = np::kNeutral;
    np::PadInput r;
    for (uint32_t g = f; g > 0 && g + 64 > f; g--) if (np::rb_remote(g - 1, &r)) { g_last_remote = r; break; }
    QueryPerformanceCounter(&g_t_window);
    note("rbnet: rollback loop takes over at frame %u (delay %d, max prediction %u frames, peer inputs known for < %u)",
         f, g_delay, g_maxpred, np::rb_remote_contig());
}

void session_reset()
{
    if (!g_active) return;
    if (g_resim) { set_bypass(false); sound_skip(false); cut_set(false); g_resim = false; }
    /* The game goes on without the loop (back to a select screen for the
     * next opponent): what start() changed in it goes back -- the present's
     * vblank pacing -- and the sound hooks forget the session's frames (a
     * session that ended inside a re-simulation left them "re-simulating":
     * every later play call matched against stale entries, every library
     * tick skipped, every stop dropped). */
    wr32(kMinVblanks, g_saved_minvb[0]); wr32(kMinVblanks + 4, g_saved_minvb[1]);
    sound_reset();
    report();
    note("rbnet: session over: the loop stops (whole session: %u frames, %u rollbacks, %u stalls)",
         g_tot.frames, g_tot.rollbacks, g_tot.stalls);
    g_active = false;
    memset(g_hash_tag, 0, sizeof g_hash_tag);
    memset(g_used_tag, 0, sizeof g_used_tag);
    memset(g_phase_tag, 0, sizeof g_phase_tag);
    g_checked = g_hash_sent = g_floor = g_started_at = g_lock_until = 0;
    g_last_phase = 0xFFFFFFFFu;
    g_lead_n = 0; g_last_sleep_frame = 0; g_frames_timed = 0; g_t_live_ok = false;
    g_wait_acc_ms = 0; g_delay = 0;
    g_next_f = 0; g_early_f = UINT32_MAX; g_tick_waited = false; g_early_tick_seen = false; g_early_committed = 0;
    g_last_remote = np::kNeutral;
    g_st = Stats(); g_tot = Stats();
    state_reset();
}

bool final_hash(uint32_t f, uint64_t* h)
{
    if (!g_active || g_hash_tag[f % kHist] != f + 1 || f >= g_hash_sent) return false;
    *h = g_hash[f % kHist];
    return true;
}

void load_seen(uint32_t f, double ms)
{
    if (!g_active) return;
    g_loads++;
    if (intro_at(f)) { if (g_verbose) note("rbnet: frame %u: a load in the intro (%.1f ms waited): no lockstep needed", f, ms); return; }
    if (f + g_load_lock > g_lock_until) g_lock_until = f + g_load_lock;
    if (g_verbose) note("rbnet: frame %u: the loaders were busy (%.1f ms waited): lockstep until %u", f, ms, g_lock_until);
}

void scene_change(uint32_t nf)
{
    /* the next match: its fight loads (stage, characters) in the first few
     * hundred frames, so the warm-up applies again */
    if (nf + g_warmup > g_lock_until) g_lock_until = nf + g_warmup;
    g_floor = nf;
    g_checked = std::max(g_checked, nf);
    /* nf itself is not compared either: a side that did not jump hashed its
     * boundary before the barrier's RNG reseed, one that jumped after it */
    g_hash_sent = std::max(g_hash_sent, nf + 1);
    state_drop_logs();
    if (g_verbose) note("rbnet: scene barrier at %u: rollback floor raised", nf);
}

static uint32_t boundary(uint32_t f, bool scene_flag, np::PadInput out[2]);

/* At the frame's tick: frame timing, the time-sync lead, and this PC's input
 * for frame f + delay (sent at once; neutral in the intro). */
static void live_tick_part(uint32_t f)
{
    { LARGE_INTEGER t; QueryPerformanceCounter(&t);
      if (g_t_live_ok) ft_add(1000.0 * (double)(t.QuadPart - g_t_live.QuadPart) / (double)g_qpf.QuadPart);
      g_t_live = t; g_t_live_ok = true; }
    /* the frame time this machine actually runs at (sleeps are in frames) */
    if (g_frames_timed == 0) QueryPerformanceCounter(&g_t_frame0);
    if (++g_frames_timed == 60) { g_frame_ms = std::max(5.0, std::min(100.0, ms_since(g_t_frame0) / 60.0)); g_frames_timed = 0; }
    /* time sync: my lead = my frame minus the peer's frame as implied by its
     * latest input (sampled delay frames ahead of its boundary) */
    {
        const uint32_t rc0 = np::rb_remote_contig();
        const int peer_frame = (int)rc0 - 1 - g_delay;
        const int mine = (int)f - peer_frame;
        np::rb_set_lead(mine);
        g_lead_mine[g_lead_n % g_lead_win] = mine;
        g_lead_theirs[g_lead_n % g_lead_win] = np::rb_peer_lead();
        g_lead_n++;
    }
    const bool intro = intro_at(f);
    if (intro) g_intro_frames++;
    np::rb_sample_local(f, intro);
}

/* The early boundary waits here for the frame's vblank tick (the frame
 * semaphore's post), unless the tick came while it re-simulated. */
static void tick_wait()
{
    LATLOG('W', "%d", g_early_tick_seen ? 1 : 0);   /* PS3_LATENCY_LOG: the early boundary waits for its tick (1: it came already) */
    if (!g_early_tick_seen && g_tick_waiter) {
        LARGE_INTEGER t0; QueryPerformanceCounter(&t0);
        g_tick_waiter();
        g_st.early_wait_ms += ms_since(t0);
    }
    g_tick_waited = true;
}

/* The first frame g < min(rc, f) whose confirmed remote input differs from
 * the prediction it was simulated with (UINT32_MAX: none). */
static uint32_t scan_mispredictions(uint32_t f, uint32_t rc)
{
    const uint32_t upto = std::min(rc, f);
    uint32_t first_wrong = UINT32_MAX;
    for (uint32_t g = g_checked; g < upto; g++) {
        if (g_used_tag[g % kHist] != g + 1 || !g_pred[g % kHist]) continue;
        np::PadInput real;
        if (!np::rb_remote(g, &real)) break;
        if (!(real == g_used[g % kHist])) { first_wrong = g; break; }
    }
    g_checked = std::max(g_checked, upto);
    return first_wrong;
}

/* Restore the boundary of first_wrong and set up its re-simulation up to f;
 * false if the logs do not reach back that far. */
static bool start_rollback(uint32_t f, uint32_t first_wrong, np::PadInput out[2])
{
    const uint32_t depth = f - first_wrong;
    uint32_t pages = 0; double rms = 0;
    bool ok = first_wrong >= g_floor && state_rollback(first_wrong, &pages, &rms);
    if (!ok) {
        note("rbnet: frame %u: misprediction at %u (%u frames back) cannot be rolled back (oldest reachable %u, floor %u) -- DESYNC likely",
             f, first_wrong, depth, state_oldest_frame(), g_floor);
        return false;
    }
    cellAtrac_rb_rolled_back();   /* the music stream reader is rewound with the title: the library sorts its feeds out */
    LATLOG('M', "%u %u %.2f", f, first_wrong, rms);   /* PS3_LATENCY_LOG: rollback from f to first_wrong (restore ms) */
    g_st.rollbacks++; g_st.depth_hist[std::min<uint32_t>(depth, 16)]++; g_st.restore_ms += rms;
    if (depth > g_st.max_depth) g_st.max_depth = depth;
    QueryPerformanceCounter(&g_resim_t0);
    if (g_sample_left) { g_sample_left--; sample_start(); g_sampling = true; }   /* T5_RB_NET_SAMPLE */
    g_resim = true; g_resim_from = first_wrong; g_resim_target = f;
    set_bypass(true);
    if (g_skipsound && sound_word() && rd32(sound_word()) == 0) {   /* a frame committed while re-simulated: sound_skip(false) puts the live value back */
        g_st.sound_zero++;
        if (g_st.sound_zero <= 3) note("rbnet: frame %u: the restore of %u brought the sound update's enable word back as zero (committed during a re-simulation); the live value is put back after this one", f, first_wrong);
    }
    if (g_skipsound) sound_skip(true);
    cut_set(true);
    if (g_verbose) note("rbnet: frame %u: rollback to %u (%u frames), %u pages restored in %.2f ms", f, first_wrong, depth, pages, rms);
    inputs_for(first_wrong, out);
    return true;
}

uint32_t on_boundary(uint32_t f, bool scene_flag, np::PadInput out[2])
{
    const uint32_t run = boundary(f, scene_flag, out);
    set_sim_frame(run);   /* the sound side keys its per-frame start log on it (rb_sound.cpp) */
    return run;
}

static uint32_t boundary(uint32_t f, bool scene_flag, np::PadInput out[2])
{
    LATLOG('N', "%u %d %d", f, g_resim ? 1 : 0, g_early_f == f ? 1 : 0);   /* PS3_LATENCY_LOG: boundary f (resim, early) */
    g_phase_at[f % 4096] = (uint8_t)rd32(kPhaseWord); g_phase_tag[f % 4096] = f + 1;
    g_intro_flag[f % 4096] = intro_phase(rd32(kPhaseWord), t5_df_game_mode() != 0);
    double cms = 0;
    const uint32_t dirty = state_commit(f, nullptr, &cms);
    (void)dirty;
    /* the gameplay hash (the netplay desync check's regions): what the peers
     * compare once every input before f is confirmed; a rollback re-simulates
     * the boundary and overwrites it before it is handed over */
    g_hash[f % kHist] = state_game_hash(); g_hash_tag[f % kHist] = f + 1;
    /* direct fight: the game mode's start, loading and intros (phase 0..12) are
     * not compared -- their state follows the loading, whose progress differs
     * between a game that has played and a fresh one (t5_hooks.cpp kIntroHash) */
    if (g_intro_rule && rd32(kPhaseWord) <= 12) g_hash[f % kHist] = 0x4F52544E49ull;
    if (g_dump) { g_dump_tag[f % kDumpFrames] = f + 1; g_dump_len[f % kDumpFrames] = state_game_bytes(g_dump_ring + (size_t)(f % kDumpFrames) * kDumpBytes, kDumpBytes); }
    for (uint32_t mf; g_dump && np::take_mismatch(&mf);) {
        if (g_dump_tag[mf % kDumpFrames] != mf + 1 || g_dumps >= 20) continue;
        char path[64]; snprintf(path, sizeof path, "rb_desync_f%06u.bin", mf);
        if (FILE* fp = fopen(path, "wb")) { fwrite(g_dump_ring + (size_t)(mf % kDumpFrames) * kDumpBytes, 1, g_dump_len[mf % kDumpFrames], fp); fclose(fp); g_dumps++; }
    }

    if (g_resim) {
        /* boundary inside a re-simulation: frame f-1 was re-run */
        g_st.resim_frames++;
        if (f < g_resim_target) { inputs_for(f, out); return f; }
        /* back at the live frame: the waits and the draw are back on */
        g_resim = false;
        set_bypass(false);
        sound_skip(false);
        cut_set(false);
        const double ms = ms_since(g_resim_t0);
        g_st.rollback_ms += ms; if (ms > g_st.rollback_ms_max) g_st.rollback_ms_max = ms;
        if (g_sampling) { sample_stop("netresim"); g_sampling = false; }
        if (g_verbose) note("rbnet: rollback %u -> %u done in %.2f ms (%u frames re-simulated)", g_resim_target, g_resim_from, ms, g_resim_target - g_resim_from);
    } else {
        g_st.commit_ms += cms;
        g_st.frames++;
        /* the title's ATRAC streaming rings are the feeder thread's: never rewound */
        if ((f % 30) == 0) {
            uint32_t ea[16], sz[16];
            const int n = cellAtrac_rb_live_rings(ea, sz, 16);
            for (int i = 0; i < n; i++)
                if (state_add_exclude(ea[i], sz[i])) note("rbnet: ATRAC streaming ring %08X+%X excluded from the rollback state", ea[i], sz[i]);
        }
        /* a phase transition since the last live boundary: barrier + lockstep window */
        const uint32_t phase = rd32(kPhaseWord);
        if (g_last_phase != 0xFFFFFFFFu && phase != g_last_phase) {
            g_phase_changes++;
            /* no floor: a misprediction just before the transition must still
             * be corrected (with a floor it became an uncorrectable desync:
             * runs h0/h150, "cannot be rolled back ... floor 210"); the
             * lockstep window keeps every frame after the transition
             * confirmed, so only the few frames right before it can ever be
             * re-simulated across it */
            if (f + g_phase_lock > g_lock_until) g_lock_until = f + g_phase_lock;   /* never shortens a warm-up or load window */
            if (g_verbose) note("rbnet: frame %u: fight phase %u -> %u: lockstep for %u frames", f, g_last_phase, phase, g_phase_lock);
        }
        g_last_phase = phase;
        if (!(g_early_f == f && !g_tick_waited)) live_tick_part(f);
    }
    /* Early rollback (T5_RB_NET_EARLY, docs/ROLLBACK.md section 26): this
     * boundary began when the previous frame was translated, before its
     * vblank tick, because a misprediction was already known (early_check).
     * Every rollback known now runs in that idle time; then the boundary
     * waits for the tick and does the live part (the local input is read at
     * the tick, as without it). */
    if (g_early_f == f && !g_tick_waited) {
        np::rb_poll();
        const uint32_t g = scan_mispredictions(f, np::rb_remote_contig());
        if (g != UINT32_MAX && start_rollback(f, g, out)) { g_st.early_rollbacks++; return g; }
        tick_wait();
        live_tick_part(f);
    }
    np::rb_poll();

    if (g_timesync && !g_resim && g_lead_n >= g_lead_win && np::mode() != np::Mode::Local && !np::rb_peer_lost()) {
        /* a trimmed mean (the middle 60 %): a lost or late packet makes one
         * side's estimate jump by a frame or two for a few frames, and the
         * plain mean then called for sleeps (each a repeated frame on the
         * screen) that the next window had to undo; a median of these whole
         * frames rounded half-frame advantages up and slept more, not less
         * (latency branch, docs/ROLLBACK.md section 26) */
        int d[kLeadWinMax];
        for (int i = 0; i < g_lead_win; i++) d[i] = g_lead_mine[i] - g_lead_theirs[i];
        std::sort(d, d + g_lead_win);
        const int cut = g_lead_win / 5;
        double sum = 0;
        for (int i = cut; i < g_lead_win - cut; i++) sum += d[i];
        const double adv = sum / (2.0 * (g_lead_win - 2 * cut));   /* frames this side is ahead of the peer */
        g_st.lead_sum += adv;
        if (adv >= 1.0 && f - g_last_sleep_frame >= (uint32_t)g_ts_interval) {
            const int frames = std::min(g_ts_max, (int)adv);
            const double ms = frames * g_frame_ms;
            if (g_ts_flip) ts_sleep_request(ms);   /* taken in this frame's flip wait (rb_hooks.cpp) */
            else { LARGE_INTEGER t0; QueryPerformanceCounter(&t0); np::rb_wait_remote(UINT32_MAX - 1, (uint32_t)ms); (void)t0; }   /* at the boundary, socket pumped */
            g_last_sleep_frame = f;
            g_st.sleeps++; g_st.sleep_ms += ms;
            g_wait_acc_ms += ms;
            if (g_verbose) note("rbnet: frame %u: %.1f frames ahead of the peer, slept %d frame(s)", f, adv, frames);
        }
    }

    uint32_t rc = np::rb_remote_contig();
    /* a scene change (or a prediction window exhausted) waits for the peer */
    const bool warm = f < g_started_at + g_warmup || f < g_lock_until;   /* lockstep until the fight has settled / past a phase change */
    /* lockstep means the frame about to run (f, inputs_for(f) below) has the
     * peer's input in hand, not just the frames before it: waiting for f - 1
     * only still ran f on a prediction, and the 1-frame rollbacks that
     * followed inside the round-end window re-issued the title's music
     * switch and its stream reader gave up (j50c, docs/ROLLBACK.md 18) */
    const uint32_t need = (scene_flag || warm) ? f + 1 : (f > g_maxpred ? f - g_maxpred : 0);
    if (rc < need && !np::rb_peer_lost()) {
        LARGE_INTEGER t0; QueryPerformanceCounter(&t0);
        rc = np::rb_wait_remote(need - 1, 2000);
        const double ms = ms_since(t0);
        g_st.stalls++; g_st.stall_ms += ms; if (warm) g_st.stall_ms_lock += ms;
        g_wait_acc_ms += ms;
        if (g_verbose || ms > 100) note("rbnet: frame %u waited %.1f ms for the peer's input up to frame %u (%s)", f, ms, need - 1,
                                        scene_flag ? "scene change" : warm ? "warm-up" : "prediction window");
    }

    /* mispredictions among the frames now confirmed */
    const uint32_t upto = std::min(rc, f);
    const uint32_t first_wrong = scan_mispredictions(f, rc);
    if (first_wrong != UINT32_MAX && start_rollback(f, first_wrong, out)) return first_wrong;

    /* final hashes: every input before g is confirmed and no rollback is pending */
    for (uint32_t g = std::max(g_hash_sent, g_floor); g <= upto && g <= f; g++) {
        /* the boundary of a scene barrier is not compared: the side that got
         * there first skips frames, the other runs them (a fight's loading
         * ends frames apart on a game that has played and a fresh one) */
        if (scene_flag && g == f) break;
        if (g_hash_tag[g % kHist] == g + 1) np::rb_push_hash(g, g_hash[g % kHist]);
        g_hash_sent = g + 1;
    }

    if (g_st.frames && (g_st.frames % 300) == 0) report();
    np::rb_account_frame((uint64_t)(g_wait_acc_ms * 1000.0));
    g_wait_acc_ms = 0;
    inputs_for(f, out);
    np::rb_log_frame(f, out, g_hash[f % kHist], g_pred[f % kHist], f < upto);
    g_next_f = f + 1;
    g_early_f = UINT32_MAX; g_tick_waited = false; g_early_tick_seen = false;
    return f;
}

/* The flip-status poll of the main thread (rb_hooks.cpp), while its frame waits
 * for the vblank tick: once the frame is translated and presented (the GPU
 * side reads no guest memory any more), a rollback already known can start
 * now instead of after the tick. True = report the flip done, so the title
 * goes on to its frame semaphore, where the boundary runs at once
 * (t5_hooks.cpp early_pending) and waits for the tick itself. */
bool early_check()
{
    if (!g_active || !g_early_on || g_resim || bypass_on()) return false;
    const uint32_t f = g_next_f;
    if (g_early_f == f) return true;
    if (!f || f < g_lock_until || f < g_started_at + g_warmup) return false;
    LARGE_INTEGER t; QueryPerformanceCounter(&t);
    if (g_early_last_check.QuadPart && t.QuadPart - g_early_last_check.QuadPart < g_qpf.QuadPart / 2000) return false;   /* every 0.5 ms */
    g_early_last_check = t;
    np::rb_poll();
    const uint32_t upto = std::min(np::rb_remote_contig(), f);
    bool wrong = false;
    for (uint32_t g = g_checked; g < upto && !wrong; g++) {
        if (g_used_tag[g % kHist] != g + 1 || !g_pred[g % kHist]) continue;
        np::PadInput real;
        if (!np::rb_remote(g, &real)) break;
        wrong = !(real == g_used[g % kHist]);
    }
    if (!wrong) return false;
    g_early_f = f; g_tick_waited = false; g_early_tick_seen = false;
    return true;
}
bool early_pending() { return g_early_f != UINT32_MAX && !g_tick_waited; }
/* The snapshot of the next boundary taken as soon as the frame is translated,
 * in the time it waits for its tick (the boundary then only adds what was
 * written since: the vblank handler's few pages). */
void early_commit()
{
    if (!g_active || !g_early_on || g_resim || bypass_on()) return;
    const uint32_t f = g_next_f;
    if (!f || g_early_committed == f) return;
    g_early_committed = f;
    double cms = 0;
    state_commit(f, nullptr, &cms);
    g_st.early_commit_ms += cms;
}
/* the vblank's post of the frame semaphore while an early boundary re-simulates
 * (swallowed like every post during a re-simulation): it was this frame's tick */
void early_tick_posted() { if (g_early_f != UINT32_MAX && !g_tick_waited) g_early_tick_seen = true; }
void set_tick_waiter(void (*fn)()) { g_tick_waiter = fn; }

} } // namespace rb::net
