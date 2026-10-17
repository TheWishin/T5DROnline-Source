/* Rollback netplay loop -- see rb_net.h. */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <algorithm>

#include "rb.h"
#include "rb_state.h"
#include "rb_net.h"

extern "C" int cellAtrac_rb_live_rings(uint32_t* ea, uint32_t* size, int cap);   /* patch 0024 */
extern "C" void cellAtrac_rb_rolled_back(void);

namespace rb { namespace net {

namespace {
constexpr uint32_t kMinVblanks = 0x106D4D98;  /* present pacing: min vblanks per frame (u64) */
bool g_enabled = false, g_active = false, g_verbose = false, g_skipsound = true;   /* T5_RB_NET_SKIPSOUND=0 keeps the sound update in re-simulated frames */
bool g_offered = false, g_timesync = true;
uint32_t g_start = 0, g_maxpred = 8;
uint32_t g_warmup = 420;         /* T5_RB_NET_WARMUP: frames after the start during which no prediction is allowed: the stage
                                  * still streams in (a rollback into a load in flight broke the game in test f1) and the
                                  * fight-start phases ("Round 1", "Fight!") pass -- a rollback across one of those left
                                  * the peers a phase apart (run e150, frame 210) */
uint32_t g_started_at = 0;
/* Fight phase transitions (0x1008F070: fight start, KO, round end / start) are
 * not reproduced by a re-simulation (they wait on sound / loader state the
 * rollback does not restore): a rollback that straddles one leaves the peers
 * a phase apart (runs e50/g50 at the round end). So a phase change seen at a
 * live boundary raises the rollback floor to that boundary and puts the loop
 * into lockstep (every input confirmed before a frame runs) for
 * T5_RB_NET_PHASE_LOCK frames, so no rollback reaches across the transition
 * and the frames right after it (round end sequence, next round's start) are
 * never predicted. */
constexpr uint32_t kPhaseWord = 0x1008F070u;
uint32_t g_phase_lock = 600, g_lock_until = 0, g_last_phase = 0xFFFFFFFFu, g_phase_changes = 0;
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

/* resim in progress */
bool     g_resim = false;
uint32_t g_resim_target = 0;     /* the live frame the resim returns to */
uint32_t g_resim_from = 0;
LARGE_INTEGER g_qpf, g_resim_t0;

/* statistics (reported every 300 frames) */
struct Stats {
    uint32_t frames = 0, rollbacks = 0, resim_frames = 0, max_depth = 0, stalls = 0, predicted = 0, sleeps = 0;
    double rollback_ms = 0, rollback_ms_max = 0, stall_ms = 0, commit_ms = 0, sleep_ms = 0, lead_sum = 0;
    uint32_t depth_hist[17] = {};
} g_st, g_tot;
LARGE_INTEGER g_t_window;

double ms_since(LARGE_INTEGER t0) { LARGE_INTEGER t; QueryPerformanceCounter(&t); return 1000.0 * (double)(t.QuadPart - t0.QuadPart) / (double)g_qpf.QuadPart; }

np::PadInput remote_for(uint32_t g, bool* predicted)
{
    np::PadInput in;
    if (np::rb_remote(g, &in)) { *predicted = false; g_last_remote = in; return in; }
    *predicted = true;
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

void report()
{
    const double win_ms = ms_since(g_t_window);
    QueryPerformanceCounter(&g_t_window);
    char hist[160]; int n = 0;
    for (int d = 1; d <= 16; d++) if (g_st.depth_hist[d]) n += snprintf(hist + n, sizeof hist - n, " %d:%u", d, g_st.depth_hist[d]);
    note("rbnet: %u frames in %.1f s (%.1f fps), %u rollbacks (%u frames re-simulated, max depth %u, depth histogram%s), %.2f ms per rollback (max %.2f), "
         "%u stalls (%.1f ms), %u frames ran on predicted input, %u time-sync sleeps (%.0f ms), avg advantage %.2f frames, commit avg %.2f ms, peer ack %u, desync mismatches %u, phase changes %u",
         g_st.frames, win_ms / 1000.0, g_st.frames * 1000.0 / (win_ms > 0 ? win_ms : 1), g_st.rollbacks, g_st.resim_frames, g_st.max_depth, n ? hist : " -",
         g_st.rollbacks ? g_st.rollback_ms / g_st.rollbacks : 0.0, g_st.rollback_ms_max, g_st.stalls, g_st.stall_ms, g_st.predicted,
         g_st.sleeps, g_st.sleep_ms, g_st.frames ? g_st.lead_sum / g_st.frames : 0.0,
         g_st.frames ? g_st.commit_ms / g_st.frames : 0.0, np::rb_peer_ack(), np::rb_mismatches(), g_phase_changes);
    g_tot.frames += g_st.frames; g_tot.rollbacks += g_st.rollbacks; g_tot.resim_frames += g_st.resim_frames;
    g_tot.max_depth = std::max(g_tot.max_depth, g_st.max_depth); g_tot.stalls += g_st.stalls; g_tot.predicted += g_st.predicted;
    g_tot.rollback_ms += g_st.rollback_ms; g_tot.rollback_ms_max = std::max(g_tot.rollback_ms_max, g_st.rollback_ms_max);
    g_tot.stall_ms += g_st.stall_ms; g_tot.commit_ms += g_st.commit_ms; g_tot.sleeps += g_st.sleeps; g_tot.sleep_ms += g_st.sleep_ms;
    for (int d = 0; d < 17; d++) g_tot.depth_hist[d] += g_st.depth_hist[d];
    g_st = Stats();
}
} // namespace

/* rollback is on offer when T5_RB_MODE is unset or "net" (and netplay is on) */
static bool offered_by_env()
{
    const char* m = getenv("T5_RB_MODE");
    const char* nm = getenv("T5_NET_MODE");
    if (!nm || !*nm) return false;
    /* The default online mode (the stage-specific mismatch of run m2 was the
     * rand() word, docs/ROLLBACK.md section 12); T5_RB_MODE=lockstep or off
     * keeps the delay-based lockstep, the test modes (test, measure) are not
     * netplay. */
    /* Opt-in until peer-to-peer hash agreement is shown: in rollback mode
     * the netplay sync check has no per-frame hashes to compare (it reports
     * every frame as mismatching), so a desync would go unnoticed. */
    if (!m || !*m) return false;
    return !strcmp(m, "net");
}

void offer()
{
    if (g_offered) return;
    g_offered = true;
    if (!offered_by_env()) return;
    np::rb_offer(true);
    note("rbnet: rollback offered to the peer (T5_RB_MODE=lockstep keeps the delay-based lockstep)");
}

bool enabled()
{
    static int e = -1;
    if (e < 0) {
        e = offered_by_env() ? 1 : 0;
        if (e) {
            if (const char* s = getenv("T5_RB_NET_START")) { if (!strncmp(s, "frame:", 6)) g_start = (uint32_t)atoi(s + 6); else g_start = (uint32_t)atoi(s); }
            if (const char* s = getenv("T5_RB_NET_MAXPRED")) g_maxpred = (uint32_t)std::max(1, std::min(16, atoi(s)));
            if (const char* s = getenv("T5_RB_NET_WARMUP")) g_warmup = (uint32_t)atoi(s);
            if (const char* s = getenv("T5_RB_NET_PHASE_LOCK")) g_phase_lock = (uint32_t)atoi(s);
            if (const char* s = getenv("T5_NET_DESYNC_DUMP")) { g_dump = *s == '1'; if (g_dump) g_dump_ring = (uint8_t*)calloc(kDumpFrames, kDumpBytes); }
            if (const char* s = getenv("T5_RB_NET_LOG")) g_verbose = *s == '1';
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
    g_delay = np::delay();
    np::rb_begin(f);
    if (g_skipsound && sound_word()) state_add_mask(sound_word(), 4);
    state_init();
    wr32(kMinVblanks, 0); wr32(kMinVblanks + 4, 0);   /* no vblank pacing in the present: re-simulated frames must not wait for one */
    g_active = true;
    g_started_at = f;
    g_last_phase = rd32(kPhaseWord);
    g_checked = g_hash_sent = g_floor = f;
    g_last_remote = np::kNeutral;
    np::PadInput r;
    for (uint32_t g = f; g > 0 && g + 64 > f; g--) if (np::rb_remote(g - 1, &r)) { g_last_remote = r; break; }
    QueryPerformanceCounter(&g_t_window);
    note("rbnet: rollback loop takes over at frame %u (delay %d, max prediction %u frames, peer inputs known for < %u)",
         f, g_delay, g_maxpred, np::rb_remote_contig());
}

void scene_change(uint32_t nf)
{
    g_floor = nf;
    g_checked = std::max(g_checked, nf);
    g_hash_sent = std::max(g_hash_sent, nf);
    state_drop_logs();
    if (g_verbose) note("rbnet: scene barrier at %u: rollback floor raised", nf);
}

uint32_t on_boundary(uint32_t f, bool scene_flag, np::PadInput out[2])
{
    double cms = 0;
    const uint32_t dirty = state_commit(f, nullptr, &cms);
    (void)dirty;
    /* the gameplay hash (the netplay desync check's regions): what the peers
     * compare once every input before f is confirmed; a rollback re-simulates
     * the boundary and overwrites it before it is handed over */
    g_hash[f % kHist] = state_game_hash(); g_hash_tag[f % kHist] = f + 1;
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
            g_lock_until = f + g_phase_lock;
            if (g_verbose) note("rbnet: frame %u: fight phase %u -> %u: lockstep for %u frames", f, g_last_phase, phase, g_phase_lock);
        }
        g_last_phase = phase;
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
        /* the local input for frame f + delay, sent at once */
        np::rb_sample_local(f);
    }
    np::rb_poll();

    if (g_timesync && !g_resim && g_lead_n >= g_lead_win && np::mode() != np::Mode::Local && !np::rb_peer_lost()) {
        double m = 0, t = 0;
        for (int i = 0; i < g_lead_win; i++) { m += g_lead_mine[i]; t += g_lead_theirs[i]; }
        const double adv = (m - t) / (2.0 * g_lead_win);   /* frames this side is ahead of the peer */
        g_st.lead_sum += adv;
        if (adv >= 1.0 && f - g_last_sleep_frame >= (uint32_t)g_ts_interval) {
            const int frames = std::min(g_ts_max, (int)adv);
            const double ms = frames * g_frame_ms;
            if (g_ts_flip) ts_sleep_request(ms);   /* taken in this frame's flip wait (rb_hooks.cpp) */
            else { LARGE_INTEGER t0; QueryPerformanceCounter(&t0); np::rb_wait_remote(UINT32_MAX - 1, (uint32_t)ms); (void)t0; }   /* at the boundary, socket pumped */
            g_last_sleep_frame = f;
            g_st.sleeps++; g_st.sleep_ms += ms;
            if (g_verbose) note("rbnet: frame %u: %.1f frames ahead of the peer, slept %d frame(s)", f, adv, frames);
        }
    }

    uint32_t rc = np::rb_remote_contig();
    /* a scene change (or a prediction window exhausted) waits for the peer */
    const bool warm = f < g_started_at + g_warmup || f < g_lock_until;   /* lockstep until the fight has settled / past a phase change */
    const uint32_t need = (scene_flag || warm) ? f : (f > g_maxpred ? f - g_maxpred : 0);
    if (rc < need && !np::rb_peer_lost()) {
        LARGE_INTEGER t0; QueryPerformanceCounter(&t0);
        rc = np::rb_wait_remote(need - 1, 2000);
        const double ms = ms_since(t0);
        g_st.stalls++; g_st.stall_ms += ms;
        if (g_verbose || ms > 100) note("rbnet: frame %u waited %.1f ms for the peer's input up to frame %u (%s)", f, ms, need - 1,
                                        scene_flag ? "scene change" : warm ? "warm-up" : "prediction window");
    }

    /* mispredictions among the frames now confirmed */
    const uint32_t upto = std::min(rc, f);
    uint32_t first_wrong = UINT32_MAX;
    for (uint32_t g = g_checked; g < upto; g++) {
        if (g_used_tag[g % kHist] != g + 1 || !g_pred[g % kHist]) continue;
        np::PadInput real;
        if (!np::rb_remote(g, &real)) break;
        if (!(real == g_used[g % kHist])) { first_wrong = g; break; }
    }
    g_checked = std::max(g_checked, upto);
    if (first_wrong != UINT32_MAX) {
        const uint32_t depth = f - first_wrong;
        uint32_t pages = 0; double rms = 0;
        bool ok = first_wrong >= g_floor && state_rollback(first_wrong, &pages, &rms);
        if (!ok) {
            note("rbnet: frame %u: misprediction at %u (%u frames back) cannot be rolled back (oldest reachable %u, floor %u) -- DESYNC likely",
                 f, first_wrong, depth, state_oldest_frame(), g_floor);
        } else {
            cellAtrac_rb_rolled_back();   /* the title's pending stream adds were decided before this */
            g_st.rollbacks++; g_st.depth_hist[std::min<uint32_t>(depth, 16)]++;
            if (depth > g_st.max_depth) g_st.max_depth = depth;
            QueryPerformanceCounter(&g_resim_t0);
            g_resim = true; g_resim_from = first_wrong; g_resim_target = f;
            set_bypass(true);
            if (g_skipsound) sound_skip(true);
            cut_set(true);
            if (g_verbose) note("rbnet: frame %u: rollback to %u (%u frames), %u pages restored in %.2f ms", f, first_wrong, depth, pages, rms);
            inputs_for(first_wrong, out);
            return first_wrong;
        }
    }

    /* final hashes: every input before g is confirmed and no rollback is pending */
    for (uint32_t g = std::max(g_hash_sent, g_floor); g <= upto && g <= f; g++) {
        if (g_hash_tag[g % kHist] == g + 1) np::rb_push_hash(g, g_hash[g % kHist]);
        g_hash_sent = g + 1;
    }

    if (g_st.frames && (g_st.frames % 300) == 0) report();
    inputs_for(f, out);
    np::rb_log_frame(f, out, g_hash[f % kHist], g_pred[f % kHist], f < upto);
    return f;
}

} } // namespace rb::net
