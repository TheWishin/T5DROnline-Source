/*
 * T5_RB_MODE=test: rollback save / restore / re-simulate test (docs/ROLLBACK.md).
 *
 * Runs the game normally with scripted pads. From T5_RB_START on, at the frame
 * boundary (main thread, right after its per-frame semaphore wait returned,
 * i.e. just before the sim of logical frame f runs):
 *   - every frame: the state module commits the frame (incremental hash H[f]
 *     of the state regions, undo log of the frame that just ran, shadow refresh)
 *   - every T5_RB_SAVE_EVERY frames a rollback point P is chosen; T5_RB_RESIM
 *     frames later the state is rolled back to P through the undo logs, the
 *     hash is checked against H[P], and the N frames are re-simulated with the
 *     same inputs, with the present/flip/semaphore waits bypassed and the draw
 *     cut on. At each re-simulated boundary the hash is compared with the one
 *     the uninterrupted run recorded. Then the game continues normally from
 *     the re-simulated state.
 *
 * Pad input is deterministic per logical frame: the keyread thread is parked
 * (its vblank wakes are swallowed) and its tick runs on the main thread at
 * every boundary with the script's input for that frame (np's finding).
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <algorithm>

#include "rb.h"
#include "rb_state.h"
#include "../directfight/df.h"

extern "C" uint8_t* vm_base;
extern "C" void cellAtrac_rb_rolled_back(void);   /* patch 0024/0025 */

namespace rb {

namespace {

/* keyread (np's t5_hooks.cpp findings) */
constexpr uint32_t kKeyreadObj    = 0x104CB5E0;
constexpr uint32_t kKeyreadQuit   = 0x104CCDF4;
constexpr uint32_t kRingResetFlag = 0x104CCDF8;
constexpr uint32_t kRing          = 0x104CCDFC;
constexpr uint32_t kRingWriteIdx  = 0x104CCE3C;
constexpr uint32_t kFnTickCounter = 0x09A204;
constexpr uint32_t kFnPadUpdate   = 0x08F3A4;
constexpr uint32_t kFnRingReset   = 0x120764;  /* the loop's reset path (0x120CFC); 0x120D2C is a no-op */
constexpr uint32_t kFnPortMask    = 0x08F6F0;
constexpr uint32_t kFnRingAdvance = 0x12071C;
constexpr uint32_t kFnTickTail    = 0x13F91C;
constexpr uint32_t kMinVblanks    = 0x106D4D98;  /* present pacing: min vblanks per frame (u64) */

/* Content of the pages written during the frames after the rollback point
 * (the uninterrupted run's frames P..P+N-1): the reference a re-simulated
 * frame must reproduce exactly. */
struct Captured { uint32_t ea; uint64_t hash; uint8_t* data; };
constexpr uint32_t kCapFrames = 16, kCapPages = 16384;
std::vector<Captured> g_cap[kCapFrames];   /* g_cap[k]: the pages frame P+k wrote, content at the boundary of P+k+1 */
uint32_t g_cap_frame0 = 0, g_cap_n = 0;
uint8_t* g_cap_buf = nullptr;
uint32_t g_cap_used = 0;
int g_capture_left = 0;
std::vector<Captured>* g_cap_cur = nullptr;
void capture_page(uint32_t ea, uint64_t h)
{
    if (!g_cap_cur || g_cap_used >= kCapPages) return;
    uint8_t* d = g_cap_buf + (size_t)g_cap_used++ * 0x1000;
    memcpy(d, vm_base + ea, 0x1000);
    g_cap_cur->push_back({ ea, h, d });
}
/* The original run's content of page ea at the boundary of logical frame f. */
const uint8_t* original_content(uint32_t ea, uint32_t f, uint64_t* h)
{
    int kmax = (int)std::min<uint32_t>(g_cap_n, f - g_cap_frame0);
    for (int k = kmax - 1; k >= 0; k--)
        for (const Captured& c : g_cap[k]) if (c.ea == ea) { if (h) *h = c.hash; return c.data; }
    return nullptr;
}
uint64_t* g_snap_page_hash = nullptr;   /* per-page hashes at the rollback point */

/* After re-simulating frame f: which pages differ from what the original
 * frame produced (captured content for pages it wrote, the rollback point's
 * hash for the rest), and where inside them. */
std::vector<uint32_t> g_diff_pages;   /* the pages the last diff found (for the dynamic write-fault trace) */
void diff_against_original(uint32_t f, int max_pages)
{
    int shown = 0, total = 0;
    g_diff_pages.clear();
    std::string all;   /* every differing page, compact (runs of pages as first-last) */
    uint32_t run0 = 0, runl = 0;
    auto flush_run = [&]() { if (!run0) return; char t[32]; snprintf(t, sizeof t, run0 == runl ? " %X" : " %X-%X", run0 >> 12, runl >> 12); all += t; run0 = 0; };
    for (size_t ri = 0; ri < kSaveN; ri++) {
        const Range& r = kSave[ri];
        for (uint32_t ea = r.base; ea < r.base + r.len; ea += 0x1000) {
            if (excluded_page(ea) || hash_excluded_page(ea)) continue;
            uint64_t oh = g_snap_page_hash[ea >> 12];
            const uint8_t* ref = original_content(ea, f, &oh);
            if (state_page_hash(ea) == oh) continue;
            total++;
            if (run0 && ea == runl + 0x1000) runl = ea; else { flush_run(); run0 = runl = ea; }
            if (g_diff_pages.size() < 64) g_diff_pages.push_back(ea);
            if (shown++ >= max_pages) continue;
            if (!ref) { note("resim %u vs original: page %08X differs (not written by the original frames; no reference content)", f, ea); continue; }
            const uint32_t* a = (const uint32_t*)(vm_base + ea);
            const uint32_t* b = (const uint32_t*)ref;
            char line[400]; int n = 0, nd = 0;
            for (int i = 0; i < 1024 && n < 300; i++)
                if (a[i] != b[i]) { nd++; if (nd <= 12) n += snprintf(line + n, sizeof line - n, " +%03X:%08X/%08X", i * 4, (unsigned)_byteswap_ulong(a[i]), (unsigned)_byteswap_ulong(b[i])); }
            note("resim %u vs original: page %08X differs in %d words:%s", f, ea, nd, line);
        }
    }
    flush_run();
    note("resim %u vs original: %d page(s) differ:%s", f, total, all.size() > 900 ? (all.substr(0, 900) + " ...").c_str() : all.c_str());
}

/* On a gameplay-hash mismatch: which words of the gameplay regions differ from
 * the original run (captured pages), the first few with addresses. */
void diff_gameplay(uint32_t f)
{
    static const Range kGame[] = {
        { 0x10099F24u, 0x70 }, { 0x104CCDFCu, 0x40 }, { 0x106D4D88u, 0x8 }, { 0x10095168u, 0x9C0 }, { 0x10053578u, 0x4 },
        { 0x10076920u, 0x4 }, { 0x1074F218u, 0x10C }, { 0x1008E000u, 0x4000 }, { 0x10099600u, 0x600 }, { 0x100A0900u, 0x200 },
        { 0x100A3B00u, 0x300 },
    };
    int shown = 0, total = 0;
    char line[600]; int n = 0;
    for (const Range& r : kGame) {
        for (uint32_t ea = r.base & ~0xFFFu; ea < r.base + r.len; ea += 0x1000) {
            const uint8_t* ref = original_content(ea, f, nullptr);
            if (!ref) continue;
            const uint32_t lo = std::max(ea, r.base), hi = std::min(ea + 0x1000, r.base + r.len);
            for (uint32_t a = lo & ~3u; a < hi; a += 4) {
                uint32_t x, y; memcpy(&x, vm_base + a, 4); memcpy(&y, ref + (a - ea), 4);
                if (x == y) continue;
                total++;
                if (shown++ < 16) n += snprintf(line + n, sizeof line - n, " %08X:%08X/%08X", a, (unsigned)_byteswap_ulong(x), (unsigned)_byteswap_ulong(y));
            }
        }
    }
    note("gameplay diff at %u: %d word(s) differ (resim/original):%s", f, total, line);
}

/* ---- recorded history ------------------------------------------------------------ */
constexpr uint32_t kHist = 4096;
uint64_t g_hist_hash[kHist], g_hist_game[kHist];
uint32_t g_hist_tag[kHist];
uint32_t g_game_mismatches = 0;

/* ---- control ----------------------------------------------------------------------- */
uint32_t g_start = 2700, g_save_every = 60, g_resim = 8, g_rollbacks_max = 1000000;
uint32_t g_logical = 0;          /* logical frame about to be simulated */
bool g_trace_on = false;         /* T5_RB_TRACE=1: syscall timeline of one normal and one resim frame */
int  g_sample = 0;               /* T5_RB_SAMPLE=1: stack samples + icall timing over the first T5_RB_SAMPLE_N resims;
                                  * 2: also over 30 normal frames before the test starts */
uint32_t g_sample_n = 3;
uint64_t g_cut_hits0 = 0;
bool g_skipsound = false;        /* T5_RB_SKIPSOUND=1: re-simulated frames skip the sound update */
uint32_t g_cut_tail = 1;
bool g_start_auto = false;       /* T5_RB_START=auto: T5_RB_START_DELAY (300) frames after the game mode (4) is first seen (direct fight) */
uint32_t g_start_delay = 300;
int g_stage = -1;                /* T5_RB_STAGE=17..34: force the stage (written to 0x1008F088 from the stage confirm until the test starts, as direct-fight does) */
bool g_stage_said = false;         /* T5_RB_CUT_TAIL: the last k re-simulated frames run WITHOUT the cut (like the live frame
                                  * after a real rollback), so the final boundary's hash must equal the original's */
int g_wft_state = 0;
uint32_t g_wft_frames = 1;       /* T5_RB_WFT_FRAMES: how many frames the normal-frame trace window stays open */
uint32_t g_wft_left = 0;
int g_normal_window = 0;
int  g_trace_state = 0;
uint32_t g_resim_left = 0;       /* > 0: re-simulating */
uint32_t g_resim_target = 0;     /* logical frame at which the resim ends */
uint32_t g_rollbacks = 0, g_mismatches = 0, g_resim_frames = 0, g_rollback_fail = 0, g_cut_diffs = 0;
uint64_t g_saved_minvb = 1;
bool g_diag_done = false, g_gdiag_done = false;
uint32_t g_snap_frame = 0;
uint64_t g_snap_hash = 0;
bool     g_have_snap = false;
LARGE_INTEGER g_qpf, g_last, g_resim_t0;
/* CPU time of this thread (QueryThreadCycleTime): the cost of a frame without
 * the wall-clock noise of other processes on the machine. */
ULONG64 g_cyc_last = 0, g_cyc_resim0 = 0, g_cyc_normal = 0;
uint32_t g_cyc_normal_n = 0;
ULONG64 cycles_now() { ULONG64 c = 0; QueryThreadCycleTime(GetCurrentThread(), &c); return c; }
bool g_inited = false;
double g_resim_ms_total = 0, g_commit_ms_total = 0, g_restore_ms_total = 0;
uint32_t g_commit_n = 0, g_restore_pages_total = 0;
double g_commit_ms_max = 0;

/* One keyread tick on the main thread (np's keyread_tick): samples the pads
 * (our override answers with the script for g_logical) into the ring. */
bool g_paddbg = false;
void keyread_tick()
{
    if (rd32(kKeyreadQuit)) return;
    if (df_drives()) {   /* the direct fight's pad override answers with what we inject for this logical frame */
        for (int p = 0; p < 2; p++) df::inject(p, true, script_input(p, g_logical).buttons);
    }
    gcall(kFnTickCounter);
    wr32(kKeyreadObj + 0x1810, 0);
    const uint32_t calls0 = pad_calls();
    gcall(kFnPadUpdate);
    if (rd32(kRingResetFlag)) gcall(kFnRingReset);
    const uint32_t slot = (rd32(kRingWriteIdx) & 15) * 2;
    const uint16_t m0 = (uint16_t)gcall(kFnPortMask, 0);
    const uint16_t m1 = (uint16_t)gcall(kFnPortMask, 1);
    if (g_paddbg && (g_logical % 100) < 3) {
        const PadInput in = script_input(0, g_logical);
        note("tick f=%u: pad calls +%u, script P1 %04X, game pad block %08X %08X, masks %04X %04X, wi %u ri %u reset %u",
             g_logical, pad_calls() - calls0, in.buttons, rd32(0x10099F24), rd32(0x10099F28), m0, m1,
             rd32(kRingWriteIdx), rd32(0x104CCE40), rd32(kRingResetFlag));
    }
    uint16_t be0 = _byteswap_ushort(m0), be1 = _byteswap_ushort(m1);
    memcpy(vm_base + kRing + slot, &be0, 2);
    memcpy(vm_base + kRing + 0x20 + slot, &be1, 2);
    gcall(kFnRingAdvance);
    gcall(kFnTickTail);
}

} // namespace

void test_on_frame(ppu_context* ctx)
{
    (void)ctx;
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    if (!g_inited) {
        g_inited = true;
        QueryPerformanceFrequency(&g_qpf);
        g_last = now;
        if (const char* e = getenv("T5_RB_START")) { if (!strcmp(e, "auto")) { g_start_auto = true; g_start = UINT32_MAX; } else g_start = (uint32_t)atoi(e); }
        if (const char* e = getenv("T5_RB_START_DELAY")) g_start_delay = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_SAVE_EVERY")) g_save_every = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_RESIM")) g_resim = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_ROLLBACKS")) g_rollbacks_max = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_PADDBG")) g_paddbg = *e == '1';
        if (const char* e = getenv("T5_RB_SAMPLE")) g_sample = atoi(e);
        if (const char* e = getenv("T5_RB_SAMPLE_N")) g_sample_n = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_CUT_TAIL")) g_cut_tail = (uint32_t)atoi(e);
        if (const char* e = getenv("T5_RB_SKIPSOUND")) g_skipsound = *e == '1';
        if (const char* e = getenv("T5_RB_STAGE")) g_stage = atoi(e);
        if (g_skipsound && sound_word()) { state_add_mask(sound_word(), 4); note("sound update skipped in re-simulated frames (word %08X)", sound_word()); }
        wft_install();
        sound_install();   /* the game-DLL build: the lifted table exists only now */
        dcut_install();
        if (const char* e = getenv("T5_RB_WFT_FRAMES")) g_wft_frames = (uint32_t)std::max(1, atoi(e));
        if (const char* e = getenv("T5_RB_TRACE")) { g_trace_on = *e == '1'; if (g_trace_on) trace_install(); }
        g_cap_buf = (uint8_t*)VirtualAlloc(nullptr, (size_t)kCapPages * 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        g_snap_page_hash = (uint64_t*)calloc(1u << 20, sizeof(uint64_t));
        if (const char* e = getenv("T5_RB_HASH_EXCLUDE")) {
            const char* q = e;
            while (*q) {
                char* z; uint32_t a = (uint32_t)strtoul(q, &z, 16); if (z == q || *z != ':') break; q = z + 1;
                uint32_t l = (uint32_t)strtoul(q, &z, 16); if (z == q) break; q = z;
                state_add_hash_exclude(a, l);
                while (*q == ',') q++;
            }
        }
        note("test mode: start %u, rollback point every %u, resim %u frames", g_start, g_save_every, g_resim);
    }
    const double dt_ms = 1000.0 * (double)(now.QuadPart - g_last.QuadPart) / (double)g_qpf.QuadPart;
    g_last = now;
    {   /* T5_RB_WFT_AT=frame: arm the write-fault tracer at that boundary for T5_RB_WFT_FRAMES frames, whatever the test does */
        static uint32_t at = 0, left = 0; static bool rd = false;
        if (!rd) { rd = true; if (const char* e = getenv("T5_RB_WFT_AT")) at = (uint32_t)atoi(e); }
        if (at && wft_enabled()) {
            if (left && --left == 0) { wft_disarm("at"); at = 0; }
            else if (!left && frame() == at) { wft_arm(); left = g_wft_frames; g_wft_state = 99; note("write-fault trace armed at frame %u for %u frames", at, g_wft_frames); }
        }
    }
    const ULONG64 cyc = cycles_now();
    const ULONG64 dcyc = cyc - g_cyc_last;
    g_cyc_last = cyc;

    /* Until the test starts the real keyread thread samples the (scripted)
     * pads on vblanks, as in measure mode -- that is what navigates the menus
     * into the fight. From g_start on the thread is parked and this thread
     * ticks it once per logical frame, so input is a function of the frame. */
    if (g_start_auto && g_start == UINT32_MAX && df::mode_cur() == 4) {
        g_start = frame() + g_start_delay;
        set_script_base(g_start);
        note("game mode seen at frame %u: the test starts at %u (scripts count from there)", frame(), g_start);
    }
    if (frame() < g_start) {
        g_logical = frame();
        set_sim_frame(g_logical);
        if (g_stage >= 0 && rd32(0x1008F070) >= 4) {   /* stage confirmed: the game-mode loader copies 0x1008F088 at entry */
            wr32(0x1008F088, (uint32_t)g_stage);
            if (!g_stage_said) { g_stage_said = true; note("stage forced to %d from frame %u", g_stage, g_logical); }
        }
        /* T5_RB_SAMPLE=2: profile 30 normal frames (boundary to boundary) before the test starts, for comparison */
        if (g_sample == 2) {
            if (g_logical == g_start - 45) { g_normal_window = 30; sample_start(); icall_timing_start(); }
            else if (g_normal_window > 0 && --g_normal_window == 0) { sample_stop("normal"); icall_timing_stop("normal"); sample_reset(); }
        }
        if ((g_logical % 100) == 0) {
            const uint32_t scene = rd32(0x10532DF0);
            logline("F %u pre-start scene %08X vtable %08X pad %04X ri %u wi %u", g_logical, scene,
                    scene ? rd32(scene) : 0, script_input(0, g_logical).buttons, rd32(0x104CCE40), rd32(0x104CCE3C));
        }
        return;
    }
    if (!keyread_parked()) {
        g_logical = frame();
        set_sim_frame(g_logical);
        return;                           /* until the keyread thread is parked, nothing else */
    }
    { static bool once = false; if (!once) { once = true; note("keyread parked at frame %u: the main thread ticks it from here", frame()); } }
    if (g_logical < g_start) { g_logical = frame(); }

    uint32_t nre = 0;
    double commit_ms = 0;
    if (!state_ready()) { state_init(); note("state hash initialised at logical %u: %016llX", g_logical, (unsigned long long)state_hash()); }
    else {
        g_cap_cur = (g_capture_left > 0) ? &g_cap[g_cap_n++] : nullptr;
        if (g_cap_cur) { g_cap_cur->clear(); g_capture_left--; }
        nre = state_commit(g_logical, g_cap_cur ? capture_page : nullptr, &commit_ms);
        g_cap_cur = nullptr;
        g_commit_ms_total += commit_ms; g_commit_n++;
        if (commit_ms > g_commit_ms_max) g_commit_ms_max = commit_ms;
    }

    const uint32_t f = g_logical;
    if (wft_enabled()) {
        if (g_wft_state == 1 && --g_wft_left == 0) { wft_disarm("normal"); g_wft_state = 2; }
        else if (g_wft_state == 3) { wft_disarm("resim-cut"); g_wft_state = 4; }
        else if (g_wft_state == 5) { wft_disarm("diffpages-normal"); g_wft_state = 6; }
        if (g_wft_state == 0 && g_resim_left == 0 && f == g_start + 25) { wft_arm(); g_wft_state = 1; g_wft_left = g_wft_frames; }
        /* T5_RB_WFT=diff: trace the writers of the pages the first final-boundary diff found, over the next normal frame */
        if (g_wft_state == 4 && g_resim_left == 0 && !g_diff_pages.empty()) { wft_arm_pages(g_diff_pages.data(), g_diff_pages.size()); g_wft_state = 5; }
    }
    if (g_trace_on && g_trace_state == 1) { trace_stop("normal frame"); g_trace_state = 2; }
    if (g_trace_on && g_trace_state == 3) { trace_stop("resim frame"); g_trace_state = 4; }
    if (g_trace_on && g_trace_state == 0 && f == g_start + 30) { g_trace_state = 1; }
    if (g_resim_left == 0) {
        /* uninterrupted run: record */
        g_hist_hash[f % kHist] = state_hash(); g_hist_game[f % kHist] = state_game_hash(); g_hist_tag[f % kHist] = f + 1;
        if (f > g_start + 1) { g_cyc_normal += dcyc; g_cyc_normal_n++; }
        logline("F %u real %u dt %.2f cyc %.1fM dirty %u commit %.2f hash %016llX vb %llu last %llu clk %llu tick %u anim %u cnt %u round %u-%u over %u timer %u reset %u", f, frame(), dt_ms, dcyc / 1e6, nre, commit_ms,
                (unsigned long long)state_hash(), (unsigned long long)rd64(0x106D4D90), (unsigned long long)rd64(0x106D4DA0),
                (unsigned long long)rd64(kFrameClock), rd32(0x1008EB9C), rd32(0x100900D4), rd32(0x1006404C),
                vm_base[0x100900D1], vm_base[0x100909A1], vm_base[0x1008EBD5], rd32(0x1008F054), rd32(kRingResetFlag));
        if (g_have_snap && f == g_snap_frame + g_resim && g_rollbacks < g_rollbacks_max) {
            /* ROLLBACK: restore the boundary of P = g_snap_frame, re-simulate P..f-1 */
            for (size_t ri = 0; ri < kSaveN; ri++)
                for (uint32_t ea = kSave[ri].base; ea < kSave[ri].base + kSave[ri].len; ea += 0x1000) g_snap_page_hash[ea >> 12] = state_page_hash(ea);
            uint32_t rpages = 0; double rms = 0;
            const bool restored = state_rollback(g_snap_frame, &rpages, &rms);
            if (restored) cellAtrac_rb_rolled_back();
            g_have_snap = false;            /* one rollback per point */
            if (!restored) { g_rollback_fail++; note("ROLLBACK at %u -> %u: undo logs gone (oldest reachable %u)", f, g_snap_frame, state_oldest_frame()); g_logical = f + 1; set_sim_frame(f); keyread_tick(); return; }
            const bool ok = state_hash() == g_snap_hash;
            note("ROLLBACK at %u -> %u: %u pages restored in %.2f ms, hash %016llX %s", f, g_snap_frame, rpages, rms,
                 (unsigned long long)state_hash(), ok ? "== point" : "!= POINT (restore not faithful)");
            g_restore_ms_total += rms; g_restore_pages_total += rpages;
            if (!ok) { g_mismatches++; state_hash_full(); note("full rehash after an unfaithful restore: %016llX", (unsigned long long)state_hash()); }
            g_rollbacks++;
            g_diag_done = false; g_gdiag_done = false;
            g_resim_left = g_resim;
            g_resim_target = f;
            g_saved_minvb = rd64(kMinVblanks);
            wr32(kMinVblanks, 0); wr32(kMinVblanks + 4, 0);   /* no vblank pacing while re-simulating (u64) */
            set_bypass(true);
            if (g_skipsound) sound_skip(true);
            cut_set(g_resim > g_cut_tail);
            g_cut_hits0 = cut_hits();
            if (wft_enabled() && g_wft_state == 2 && g_resim > g_cut_tail) { wft_arm(); g_wft_state = 3; }
            QueryPerformanceCounter(&g_resim_t0);
            g_cyc_resim0 = cycles_now();
            /* re-run frame P now; the next boundary is logical P+1 */
            g_logical = g_snap_frame + 1;
            set_sim_frame(g_snap_frame);
            keyread_tick();
            if (g_trace_on && g_trace_state == 2) { g_trace_state = 3; trace_frame("resim frame"); }
            if (g_sample && g_rollbacks <= g_sample_n) { sample_start(); icall_timing_start(); }
            return;
        }
        if ((f - g_start) % g_save_every == 0 && f + g_resim <= g_start + 100000) {
            g_snap_frame = f; g_snap_hash = state_hash(); g_have_snap = true;
            g_cap_frame0 = f; g_cap_n = 0; g_cap_used = 0;
            g_capture_left = (int)std::min<uint32_t>(g_resim, kCapFrames);
            note("ROLLBACK POINT at %u: hash %016llX (commit %.2f ms, %u dirty pages; avg commit %.2f ms, max %.2f; stage %u, game type %u)", f, (unsigned long long)state_hash(),
                 commit_ms, nre, g_commit_n ? g_commit_ms_total / g_commit_n : 0, g_commit_ms_max, rd32(0x1008F088), rd32(0x1008EBAC));
        }
        g_logical = f + 1;
        set_sim_frame(f);
        keyread_tick();
        if (g_trace_on && g_trace_state == 1) trace_frame("normal frame");
        return;
    }

    /* re-simulating: boundary of logical frame f (frame f-1 was just re-run) */
    g_resim_left--;
    g_resim_frames++;
    if (g_resim_left <= g_cut_tail) cut_set(false);   /* the tail frames draw, as the live frame after a real rollback does */
    const bool known = g_hist_tag[f % kHist] == f + 1;
    const bool match = known && g_hist_hash[f % kHist] == state_hash();
    const uint64_t gh = state_game_hash();
    const bool gmatch = known && g_hist_game[f % kHist] == gh;
    const bool counted = g_resim_left < g_cut_tail || g_cut_tail == 0;   /* boundaries after a cut frame are expected to differ in render bookkeeping */
    if (!gmatch) {
        g_game_mismatches++;
        note("resim frame %u: GAMEPLAY hash %016llX, original %016llX -> MISMATCH", f, (unsigned long long)gh, (unsigned long long)(known ? g_hist_game[f % kHist] : 0));
        if (!g_gdiag_done) { g_gdiag_done = true; diff_gameplay(f); }
    }
    if (!match && counted) { g_mismatches++; if (!g_diag_done) { g_diag_done = true; diff_against_original(f, 12); } }
    if (!match && !counted) g_cut_diffs++;
    logline("R %u real %u dt %.2f cyc %.1fM dirty %u commit %.2f hash %016llX %s game %s vb %llu last %llu clk %llu tick %u anim %u cnt %u round %u-%u over %u timer %u reset %u", f, frame(), dt_ms, dcyc / 1e6, nre, commit_ms,
            (unsigned long long)state_hash(), !known ? "unknown" : match ? "MATCH" : "MISMATCH", gmatch ? "MATCH" : "MISMATCH",
            (unsigned long long)rd64(0x106D4D90), (unsigned long long)rd64(0x106D4DA0),
            (unsigned long long)rd64(kFrameClock), rd32(0x1008EB9C), rd32(0x100900D4), rd32(0x1006404C),
            vm_base[0x100900D1], vm_base[0x100909A1], vm_base[0x1008EBD5], rd32(0x1008F054), rd32(kRingResetFlag));
    if (!match && counted) note("resim frame %u: hash %016llX, original %016llX -> %s", f, (unsigned long long)state_hash(),
                     (unsigned long long)(known ? g_hist_hash[f % kHist] : 0), known ? "MISMATCH" : "unknown");
    if (g_resim_left == 0) {
        LARGE_INTEGER t1; QueryPerformanceCounter(&t1);
        const double ms = 1000.0 * (double)(t1.QuadPart - g_resim_t0.QuadPart) / (double)g_qpf.QuadPart;
        g_resim_ms_total += ms;
        if (g_sample && g_rollbacks <= g_sample_n) { sample_stop("resim"); icall_timing_stop("resim"); }
        cut_set(false);
        sound_skip(false);
        set_bypass(false);
        wr32(kMinVblanks, (uint32_t)(g_saved_minvb >> 32)); wr32(kMinVblanks + 4, (uint32_t)g_saved_minvb);
        const double rc = (double)(cycles_now() - g_cyc_resim0) / 1e6 / g_resim;
        const double nc = g_cyc_normal_n ? (double)g_cyc_normal / 1e6 / g_cyc_normal_n : 0;
        const SoundStats ss = sound_stats(false);
        note("RESIM done: %u frames in %.2f ms (%.2f ms/frame, %.1f Mcycles/frame CPU; a normal frame with draw: %.1f Mcycles); rollbacks %u (%u failed), GAMEPLAY-hash mismatches %u of %u resim boundaries; full-state mismatches at final boundaries %u (at cut-frame boundaries: %u); cut hits %llu; restore avg %.2f ms, %.0f pages; "
             "sounds so far: %u started live, %u kept from a first run, %u new in re-simulated frames, %u played on, %u ticks skipped; "
             "stops %u skipped / %u not applied, %u answers replayed, events %u skipped / %u new",
             g_resim, ms, ms / g_resim, rc, nc, g_rollbacks, g_rollback_fail, g_game_mismatches, g_resim_frames, g_mismatches, g_cut_diffs, (unsigned long long)(cut_hits() - g_cut_hits0),
             g_rollbacks ? g_restore_ms_total / g_rollbacks : 0, g_rollbacks ? (double)g_restore_pages_total / g_rollbacks : 0,
             ss.started_live, ss.deduped, ss.started_resim, ss.orphaned, ss.ticks_skipped, ss.stops_kept, ss.stops_suppressed, ss.queries_replayed, ss.events_kept, ss.events_new);
        /* continue the uninterrupted run from here: f == g_resim_target */
        g_logical = f + 1;
        set_sim_frame(f);
        keyread_tick();
        return;
    }
    g_logical = f + 1;
    set_sim_frame(f);
    keyread_tick();
}

} // namespace rb
