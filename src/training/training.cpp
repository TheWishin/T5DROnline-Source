/*
 * T5DR training overlay (docs/TRAINING.md): input display and frame data,
 * drawn over the finished picture by the runtime's overlay layer (ps3recomp
 * patch 0045, libs/video/rsx_overlay.c).
 *
 * It only READS guest memory -- the fight blocks of the two fighters, once per
 * live frame, at the netplay hooks' frame boundary (t5_hooks.cpp
 * on_frame_start, never in a frame a rollback re-simulates) -- and never
 * writes it, calls into the game or changes its input. Online play is
 * therefore unaffected: the game state is the same with the overlay on or off
 * (checked with rollback and lockstep pairs, docs/TRAINING.md).
 *
 * Environment (the launcher sets the first three from Settings -> Training):
 *   T5_TRAINING          off (default) | inputs | frames (inputs and frame data)
 *   T5_TRAINING_ALL=1    also outside Practice (every offline fight)
 *   T5_TRAINING_ONLINE=1 also in online matches: this PC's own inputs only, no
 *                        frame data
 *   T5_TRAINING_LANG     de | en (default: the Windows display language)
 *   T5_TRAINING_ROWS     input rows per player (4..24, default 14)
 *   T5_TRAINING_LOG      file: one line per frame-data result and per new input
 *                        row (tests)
 *   T5_TRAINING_STATS=1  every 600 fight frames: the main thread's time in this
 *                        hook (mean / max microseconds)
 *   T5_TRAINING_TRACE    file: the fight block (0x1008E000, 16 KB) and the input
 *                        ring of every live frame (research)
 * F2 (while the game window has the focus) cycles off / inputs / inputs and
 * frame data for this session.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ppu_recomp.h"     /* ppu_context, vm_base */
#include "rsx_overlay.h"    /* ps3recomp patch 0045 */
#include "training_logic.h"

extern "C" int t5_netplay_enabled(void);       /* src/netplay/t5_hooks.cpp */
extern "C" int t5_netplay_local_slot(void);

namespace {

using namespace training;

/* ---- guest memory, read only (NPUB30009 v01.00) -------------------------- */
constexpr uint32_t kPhase    = 0x1008F070;   /* fight phase: 17 = the fight runs (round intros included) */
constexpr uint32_t kGameType = 0x1008EBAC;   /* battle config +0: 0 arcade, 1 ghost, 2 demo, 4 VS, 9 survival, 10 practice */
constexpr uint32_t kFighter[2] = { 0x10090030, 0x10090900 };
constexpr uint32_t kGtPractice = 10, kGtDemo = 2;

inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline uint16_t rd16(uint32_t a) { uint16_t v; memcpy(&v, vm_base + a, 2); return _byteswap_ushort(v); }
inline uint8_t  rd8(uint32_t a)  { return vm_base[a]; }

Sample read_fighter(uint32_t b)
{
    Sample s;
    const uint32_t w220 = rd32(b + 0x220), w21c = rd32(b + 0x21C);
    s.input    = rd16(b + 0x6D6);
    s.right    = rd8(b + 0x1D2) != 0;
    s.can_act  = (w220 & 0xFF) == 1 && ((w220 & 0x01000000u) || (w21c & 1));
    s.new_move = (rd32(b + 0x20C) >> 24) & 1;
    s.active   = (rd32(b + 0x214) & 0x30000u) != 0;
    s.cls      = rd32(b + 0x15C);
    s.hp       = (int16_t)rd16(b + 0x6BC);
    return s;
}

/* ---- settings ---------------------------------------------------------------- */
enum Mode { kOff = 0, kInputs = 1, kFrames = 2 };
struct Config {
    int  mode = kOff;
    bool all = false, online = false, de = false;
    int  rows = 14;
    bool stats = false;
    bool online_game = false;   /* started for online play (T5_NET_MODE / T5_CTL_DIR): online rules all the time */
    bool local_net = false;     /* T5_NET_MODE=local: both players on this PC (tests): offline rules */
    FILE* log = nullptr;
    FILE* trace = nullptr;
} g_cfg;
bool g_init = false;

int parse_mode(const char* e)
{
    if (!e || !*e) return kOff;
    if (!_stricmp(e, "frames") || !_stricmp(e, "framedata") || !_stricmp(e, "all") || !strcmp(e, "2")) return kFrames;
    if (!_stricmp(e, "inputs") || !_stricmp(e, "input") || !strcmp(e, "1") || !_stricmp(e, "on")) return kInputs;
    return kOff;
}

void init()
{
    g_init = true;
    g_cfg.mode = parse_mode(getenv("T5_TRAINING"));
    const char* a = getenv("T5_TRAINING_ALL");
    const char* o = getenv("T5_TRAINING_ONLINE");
    g_cfg.all = a && *a == '1';
    g_cfg.online = o && *o == '1';
    const char* l = getenv("T5_TRAINING_LANG");
    if (l && *l) g_cfg.de = !_strnicmp(l, "de", 2);
    else g_cfg.de = PRIMARYLANGID(GetUserDefaultUILanguage()) == LANG_GERMAN;
    if (const char* r = getenv("T5_TRAINING_ROWS")) {
        const int n = atoi(r);
        if (n >= 4 && n <= 24) g_cfg.rows = n;
    }
    if (const char* f = getenv("T5_TRAINING_LOG"); f && *f) g_cfg.log = fopen(f, "w");
    { const char* st = getenv("T5_TRAINING_STATS"); g_cfg.stats = st && *st == '1'; }
    { const char* nm = getenv("T5_NET_MODE"); const char* ctl = getenv("T5_CTL_DIR");
      g_cfg.local_net = nm && !_stricmp(nm, "local");
      g_cfg.online_game = (nm && *nm && !g_cfg.local_net) || (ctl && *ctl); }
    if (const char* f = getenv("T5_TRAINING_TRACE"); f && *f) g_cfg.trace = fopen(f, "wb");
    if (g_cfg.mode != kOff) {
        rsx_overlay_prepare();
        fprintf(stderr, "[training] overlay: %s, %s%s (F2 switches it)\n",
                g_cfg.mode == kFrames ? "inputs and frame data" : "inputs",
                g_cfg.all ? "every offline fight" : "Practice",
                g_cfg.online ? ", online: own inputs" : "");
    }
}

/* ---- state ------------------------------------------------------------------- */
History<24> g_hist[2];
Tracker g_track;
Result g_results[3];
int g_nresults = 0;
uint64_t g_live = 0;            /* live frames in the current fight */
bool g_shown = false;           /* a list is published */
bool g_in_fight = false;
int g_f2_mode = -1;             /* F2's choice for this session (-1: the setting) */
bool g_f2_down = false;

const char* tr(const char* en, const char* de) { return g_cfg.de ? de : en; }

bool window_focused()
{
    HWND fg = GetForegroundWindow();
    DWORD pid = 0;
    if (fg) GetWindowThreadProcessId(fg, &pid);
    return pid == GetCurrentProcessId();
}

void poll_hotkey()
{
    const bool down = (GetAsyncKeyState(VK_F2) & 0x8000) != 0 && window_focused();
    if (down && !g_f2_down) {
        const int cur = g_f2_mode >= 0 ? g_f2_mode : g_cfg.mode;
        g_f2_mode = (cur + 1) % 3;
        if (g_f2_mode != kOff) rsx_overlay_prepare();
        fprintf(stderr, "[training] F2: %s\n", g_f2_mode == kOff ? "off" : g_f2_mode == kInputs ? "inputs" : "inputs and frame data");
    }
    g_f2_down = down;
}

/* ---- drawing ----------------------------------------------------------------- */
constexpr float kPx = 2.0f;                 /* font pixel: 12 x 16 canvas units per character */
constexpr float kRowH = 18.0f;
constexpr uint32_t kWhite = RSX_OVL_RGBA(240, 240, 240, 255), kGrey = RSX_OVL_RGBA(150, 150, 150, 255),
                   kYellow = RSX_OVL_RGBA(255, 214, 72, 255), kGreen = RSX_OVL_RGBA(96, 232, 96, 255),
                   kRed = RSX_OVL_RGBA(255, 96, 96, 255), kPanel = RSX_OVL_RGBA(0, 0, 0, 150);

void draw_history(int p, float x, float y)
{
    const History<24>& h = g_hist[p];
    const int rows = h.count < g_cfg.rows ? h.count : g_cfg.rows;
    const float w = 156.0f;
    const uint32_t accent = p == 0 ? RSX_OVL_RGBA(230, 60, 60, 255) : RSX_OVL_RGBA(70, 130, 255, 255);
    rsx_overlay_rect(x, y - 4, w, kRowH * (float)g_cfg.rows + 8, kPanel);
    rsx_overlay_rect(p == 0 ? x : x + w - 3, y - 4, 3, kRowH * (float)g_cfg.rows + 8, accent);
    for (int i = 0; i < rows; i++) {
        const HistoryRow& r = h.rows[i];
        const float ry = y + kRowH * (float)i;
        char num[8], btn[12], dir[2] = { (char)r.n.dir, 0 };
        if (r.frames > 999) snprintf(num, sizeof num, "999");
        else snprintf(num, sizeof num, "%u", r.frames);
        buttons_text(r.n.buttons, btn, sizeof btn);
        const uint32_t a = i == 0 ? 255u : (uint32_t)(255 - i * 8);
        const uint32_t fade = 0xFFFFFF00u;
        rsx_overlay_text(x + 48, ry, kPx, (kGrey & fade) | a, RSX_OVL_RIGHT | RSX_OVL_SHADOW, num);
        if (r.n.dir != 5 || !r.n.buttons)
            rsx_overlay_text(x + 60, ry, kPx, ((r.n.dir == 5 ? kGrey : kYellow) & fade) | a, RSX_OVL_SHADOW, dir);
        if (r.n.buttons)
            rsx_overlay_text(x + (r.n.dir == 5 ? 60 : 78), ry, kPx, (kWhite & fade) | a, RSX_OVL_SHADOW, btn);
    }
}

void result_line(const Result& r, char* lead, size_t nl, char* tail, size_t nt, uint32_t* tail_col)
{
    const char* who = r.attacker ? "P2" : "P1";
    char su[16] = "";
    if (r.startup > 0) snprintf(su, sizeof su, "  i%d", r.startup);
    switch (r.kind) {
    case Kind::Whiff:
        snprintf(lead, nl, "%s%s  %s", who, su, tr("WHIFF", "DANEBEN"));
        snprintf(tail, nt, "%dF", r.total);
        *tail_col = kGrey;
        return;
    case Kind::Down:
        snprintf(lead, nl, "%s%s  %s", who, su, tr("KNOCKDOWN", "AM BODEN"));
        tail[0] = 0;
        *tail_col = kWhite;
        return;
    default: break;
    }
    const char* k = r.kind == Kind::Hit ? tr("HIT", "TREFFER") : r.kind == Kind::Counter ? tr("COUNTER HIT", "KONTER")
                                                                                        : tr("BLOCK", "GEBLOCKT");
    snprintf(lead, nl, "%s%s  %s", who, su, k);
    snprintf(tail, nt, "%+d", r.adv);
    *tail_col = r.adv > 0 ? kGreen : r.adv < 0 ? kRed : kWhite;
}

void draw_results(float cx, float y)
{
    if (!g_nresults) return;
    const float w = 460.0f;
    rsx_overlay_rect(cx - w / 2, y - 4, w, kRowH * (float)g_nresults + 8, kPanel);
    for (int i = 0; i < g_nresults; i++) {
        char lead[64], tail[16];
        uint32_t col;
        result_line(g_results[i], lead, sizeof lead, tail, sizeof tail, &col);
        const uint32_t a = i == 0 ? 255u : 150u;
        const float lw = rsx_overlay_text_width(lead, kPx), tw = rsx_overlay_text_width(tail, kPx);
        const float x0 = cx - (lw + (tail[0] ? 12.0f + tw : 0.0f)) / 2;
        const float ry = y + kRowH * (float)i;
        rsx_overlay_text(x0, ry, kPx, (kWhite & 0xFFFFFF00u) | a, RSX_OVL_SHADOW, lead);
        if (tail[0]) rsx_overlay_text(x0 + lw + 12.0f, ry, kPx, (col & 0xFFFFFF00u) | a, RSX_OVL_SHADOW, tail);
    }
}

void publish(int mode, bool show_p1, bool show_p2, bool frames)
{
    rsx_overlay_begin();
    if (show_p1) draw_history(0, 16.0f, 190.0f);
    if (show_p2) draw_history(1, 1280.0f - 16.0f - 156.0f, 190.0f);
    if (frames && mode == kFrames) draw_results(640.0f, 176.0f);
    rsx_overlay_end();
    g_shown = true;
}

void hide()
{
    if (g_shown) rsx_overlay_clear();
    g_shown = false;
}

void log_result(const Result& r)
{
    if (!g_cfg.log) return;
    static const char* kinds[] = { "block", "hit", "counter", "whiff", "down" };
    fprintf(g_cfg.log, "%llu result P%d startup %d %s adv %+d total %d\n", (unsigned long long)g_live, r.attacker + 1,
            r.startup, kinds[(int)r.kind], r.adv, r.total);
    fflush(g_cfg.log);
}

void trace_frame()
{
    static uint32_t n = 0;
    struct { uint32_t magic, n; } h = { 0x54524331u, n++ };
    fwrite(&h, sizeof h, 1, g_cfg.trace);
    fwrite(vm_base + 0x1008E000u, 1, 0x4000, g_cfg.trace);
    fwrite(vm_base + 0x104CCDF0u, 1, 0x60, g_cfg.trace);
    fwrite(vm_base + 0x10099F00u, 1, 0x200, g_cfg.trace);
    fwrite(vm_base + 0x106D4D88u, 1, 8, g_cfg.trace);
    fflush(g_cfg.trace);
}

} // namespace

/* One live frame boundary on the main thread (t5_hooks.cpp on_frame_start, not
 * called in re-simulated frames): the frame that just ran is complete. */
static bool frame_body();

extern "C" void t5_training_frame(ppu_context* ctx)
{
    (void)ctx;
    if (!g_init) init();
    if (g_cfg.trace) trace_frame();
    if (g_cfg.mode == kOff && g_f2_mode < 0 && !g_cfg.trace) return;
    LARGE_INTEGER t0, t1;
    if (g_cfg.stats) QueryPerformanceCounter(&t0);
    const bool in_fight = frame_body();
    if (g_cfg.stats && in_fight) {
        static LARGE_INTEGER fq;
        static double sum = 0, mx = 0;
        static unsigned n = 0;
        QueryPerformanceCounter(&t1);
        if (!fq.QuadPart) QueryPerformanceFrequency(&fq);
        const double us = 1e6 * (double)(t1.QuadPart - t0.QuadPart) / (double)fq.QuadPart;
        sum += us; if (us > mx) mx = us;
        if (++n == 600) {
            fprintf(stderr, "[training] 600 fight frames: hook %.1f us mean, %.1f us max\n", sum / 600.0, mx);
            n = 0; sum = 0; mx = 0;
        }
    }
}

/* true in a fight */
static bool frame_body()
{
    poll_hotkey();
    const int mode = g_f2_mode >= 0 ? g_f2_mode : g_cfg.mode;

    const uint32_t phase = rd32(kPhase), gt = rd32(kGameType);
    const bool online = !g_cfg.local_net && (g_cfg.online_game || t5_netplay_enabled() != 0);
    const bool fight = phase == 17 && gt != kGtDemo;
    if (!fight) {
        if (g_in_fight) {
            g_track.reset();
            g_hist[0].clear(); g_hist[1].clear();
            g_nresults = 0;
            g_in_fight = false;
        }
        hide();
        return false;
    }
    if (!g_in_fight) { g_in_fight = true; g_live = 0; }
    g_live++;

    Sample s[2] = { read_fighter(kFighter[0]), read_fighter(kFighter[1]) };
    /* the history and the tracker always run in a fight, so F2 shows a full list */
    for (int p = 0; p < 2; p++) {
        const Notation n = notation(s[p].input, s[p].right);
        g_hist[p].push(n);
        if (g_cfg.log && g_hist[p].rows[0].frames == 1) {   /* a new row */
            char b[12];
            buttons_text(n.buttons, b, sizeof b);
            fprintf(g_cfg.log, "%llu input P%d %d%s%s\n", (unsigned long long)g_live, p + 1, n.dir, b[0] ? "+" : "", b);
        }
    }
    if (!online && g_track.frame(s)) {
        const Result& r = g_track.last();
        memmove(&g_results[1], &g_results[0], sizeof(Result) * 2);
        g_results[0] = r;
        if (g_nresults < 3) g_nresults++;
        log_result(r);
    }

    bool show = mode != kOff;
    bool p1 = true, p2 = true, frames = true;
    if (online) {
        show = show && g_cfg.online;
        const int me = t5_netplay_local_slot();
        p1 = me == 0;
        p2 = me == 1;
        frames = false;
    } else if (gt != kGtPractice && !g_cfg.all) {
        show = false;
    }
    if (show) publish(mode, p1, p2, frames);
    else hide();
    return true;
}
