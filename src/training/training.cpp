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
 *   T5_TRAINING_AB=<n>   cost measurement: in every other block of n fight frames
 *                        the hook does nothing and nothing is drawn; each switch
 *                        is logged with its QPC time (match it with PS3_FRAMELOG)
 *   T5_TRAINING_TRACE    file: the fight block (0x1008E000, 16 KB) and the input
 *                        ring of every live frame (research)
 *   T5_TRAINING_TRACE_RANGES  "addr:len[:every],..." (hex; every in frames): more
 *                        guest ranges for that trace, page by page (research)
 * F2 (while the game window has the focus) cycles off / inputs / inputs and
 * frame data for this session.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <intrin.h>      /* __rdtsc: T5_TRAINING_STATS */

#include "ppu_recomp.h"     /* ppu_context, vm_base */
#include "rsx_overlay.h"    /* ps3recomp patch 0045 */
#include "training_logic.h"

extern "C" int t5_netplay_enabled(void);       /* src/netplay/t5_hooks.cpp */
extern "C" int t5_netplay_local_slot(void);
extern "C" int t5_practice_on(void);                                   /* practice.cpp: the practice tools */
extern "C" int t5_practice_status(char* out, unsigned n, int de);      /* ... their status line ("" = none) */

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
    s.end_window = (w220 & 0xFF) == 1 && (w220 & 0x01000000u);
    s.new_move = (rd32(b + 0x20C) >> 24) & 1;
    s.active   = (rd32(b + 0x214) & 0x30000u) != 0;
    s.cls      = rd32(b + 0x15C);
    s.hp       = (int16_t)rd16(b + 0x6BC);
    const uint32_t mv = rd32(b + 0x168) >> 16;
    s.down     = (mv & 0xFF00) == 0x8000 && mv != 0x8001 && mv != 0x8000;
    return s;
}

/* ---- settings ---------------------------------------------------------------- */
enum Mode { kOff = 0, kInputs = 1, kFrames = 2 };
struct Config {
    int  mode = kOff;
    bool all = false, online = false, de = false;
    int  rows = 14;
    bool stats = false;
    int  ab = 0;                /* T5_TRAINING_AB=<frames>: cost measurement, on and off in turns */
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

void parse_trace_ranges(const char* p);   /* T5_TRAINING_TRACE_RANGES, below */

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
    if (const char* ab = getenv("T5_TRAINING_AB")) g_cfg.ab = atoi(ab) > 0 ? atoi(ab) : 0;
    { const char* nm = getenv("T5_NET_MODE"); const char* ctl = getenv("T5_CTL_DIR");
      g_cfg.local_net = nm && !_stricmp(nm, "local");
      g_cfg.online_game = (nm && *nm && !g_cfg.local_net) || (ctl && *ctl); }
    if (const char* f = getenv("T5_TRAINING_TRACE"); f && *f) {
        g_cfg.trace = fopen(f, "wb");
        parse_trace_ranges(getenv("T5_TRAINING_TRACE_RANGES"));
    }
    if (g_cfg.mode != kOff || t5_practice_on()) rsx_overlay_prepare();
    if (g_cfg.mode != kOff) {
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

void draw_status(const char* st)
{
    const float w = rsx_overlay_text_width(st, kPx) + 24.0f, y = 176.0f + kRowH * 3 + 14.0f;
    rsx_overlay_rect(640.0f - w / 2, y - 4, w, kRowH + 8, kPanel);
    rsx_overlay_text(640.0f, y, kPx, kYellow, RSX_OVL_CENTER | RSX_OVL_SHADOW, st);
}

/* mode kOff: only the practice status line */
void publish(int mode, bool show_p1, bool show_p2, bool frames, const char* status = "")
{
    if (!g_shown && g_cfg.log) {
        fprintf(g_cfg.log, "%llu show game type %u%s%s%s\n", (unsigned long long)g_live, rd32(kGameType),
                show_p1 ? " P1" : "", show_p2 ? " P2" : "", frames && mode == kFrames ? " frames" : "");
        fflush(g_cfg.log);
    }
    rsx_overlay_begin();
    if (mode != kOff) {
        if (show_p1) draw_history(0, 16.0f, 190.0f);
        if (show_p2) draw_history(1, 1280.0f - 16.0f - 156.0f, 190.0f);
        if (frames && mode == kFrames) draw_results(640.0f, 176.0f);
    }
    if (status[0]) draw_status(status);
    rsx_overlay_end();
    g_shown = true;
}

void hide()
{
    if (g_shown) {
        rsx_overlay_clear();
        if (g_cfg.log) { fprintf(g_cfg.log, "%llu hide phase %u\n", (unsigned long long)g_live, rd32(kPhase)); fflush(g_cfg.log); }
    }
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

/* T5_TRAINING_TRACE_RANGES="addr:len[:every],..." (hex addresses and lengths,
 * every in frames, default 1): more guest ranges for the research trace, each
 * appended to the frames it is due in (n % every == 0), in the order given */
struct TraceRange { uint32_t base, len, every; };
TraceRange g_trace_extra[8];
int g_trace_nextra = 0;

void parse_trace_ranges(const char* p)
{
    while (p && *p && g_trace_nextra < 8) {
        char* e;
        const uint32_t a = (uint32_t)strtoul(p, &e, 16);
        if (e == p || *e != ':') break;
        p = e + 1;
        const uint32_t l = (uint32_t)strtoul(p, &e, 16);
        if (e == p) break;
        p = e;
        uint32_t every = 1;
        if (*p == ':') { every = (uint32_t)strtoul(p + 1, &e, 10); p = e; if (!every) every = 1; }
        if (a >= 0x10000000u && l && l <= 0x01000000u && a + l <= 0x20000000u) g_trace_extra[g_trace_nextra++] = { a, l, every };
        while (*p == ',' || *p == ' ') p++;
    }
}

/* a range page by page: pages the game has not committed (yet) go in as zeros */
void trace_range(uint32_t base, uint32_t len)
{
    static const uint8_t zero[4096] = {};
    for (uint32_t off = 0; off < len;) {
        const uint32_t a = base + off, n = (len - off) < (4096 - (a & 4095)) ? (len - off) : (4096 - (a & 4095));
        MEMORY_BASIC_INFORMATION mi;
        const bool ok = VirtualQuery(vm_base + a, &mi, sizeof mi) && mi.State == MEM_COMMIT &&
                        !(mi.Protect & (PAGE_NOACCESS | PAGE_GUARD));
        fwrite(ok ? (const void*)(vm_base + a) : (const void*)zero, 1, n, g_cfg.trace);
        off += n;
    }
}

void trace_frame()
{
    static uint32_t n = 0;
    const uint32_t k = n;
    struct { uint32_t magic, n; } h = { 0x54524331u, n++ };
    fwrite(&h, sizeof h, 1, g_cfg.trace);
    fwrite(vm_base + 0x1008E000u, 1, 0x4000, g_cfg.trace);
    fwrite(vm_base + 0x104CCDF0u, 1, 0x60, g_cfg.trace);
    fwrite(vm_base + 0x10099F00u, 1, 0x200, g_cfg.trace);
    fwrite(vm_base + 0x106D4D88u, 1, 8, g_cfg.trace);
    for (int i = 0; i < g_trace_nextra; i++) {
        const TraceRange& r = g_trace_extra[i];
        if (k % r.every == 0) trace_range(r.base, r.len);
    }
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
    if (g_cfg.mode == kOff && g_f2_mode < 0 && !g_cfg.trace && !t5_practice_on()) return;
    /* T5_TRAINING_STATS: wall time and this thread's own CPU time (cycles, so a
     * busy PC preempting the thread does not count) */
    LARGE_INTEGER t0, t1;
    ULONG64 c0 = 0, c1 = 0;
    if (g_cfg.stats) { QueryPerformanceCounter(&t0); QueryThreadCycleTime(GetCurrentThread(), &c0); }
    const bool in_fight = frame_body();
    if (g_cfg.stats && in_fight) {
        static LARGE_INTEGER fq;
        static double sum = 0, mx = 0, csum = 0, cmx = 0, cyc_per_us = 0;
        static unsigned n = 0;
        QueryThreadCycleTime(GetCurrentThread(), &c1);
        QueryPerformanceCounter(&t1);
        if (!fq.QuadPart) {
            QueryPerformanceFrequency(&fq);
            LARGE_INTEGER a, b;   /* the cycle counter's rate, once */
            QueryPerformanceCounter(&a);
            const unsigned long long r0 = __rdtsc();
            do QueryPerformanceCounter(&b); while (b.QuadPart - a.QuadPart < fq.QuadPart / 50);
            cyc_per_us = (double)(__rdtsc() - r0) / (1e6 * (double)(b.QuadPart - a.QuadPart) / (double)fq.QuadPart);
        }
        const double us = 1e6 * (double)(t1.QuadPart - t0.QuadPart) / (double)fq.QuadPart;
        const double cus = cyc_per_us > 0 ? (double)(c1 - c0) / cyc_per_us : 0;
        sum += us; if (us > mx) mx = us;
        csum += cus; if (cus > cmx) cmx = cus;
        if (++n == 600) {
            fprintf(stderr, "[training] 600 fight frames: hook CPU %.1f us mean, %.1f us max (wall %.1f / %.1f us)\n",
                    csum / 600.0, cmx, sum / 600.0, mx);
            n = 0; sum = 0; mx = 0; csum = 0; cmx = 0;
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
    if (g_cfg.ab) {
        /* cost measurement (docs/TRAINING.md "Cost"): the whole hook and the drawing are off in every
         * other block of ab fight frames; the switches go to stderr with the QPC time, to be matched
         * with the frame log (PS3_FRAMELOG) */
        const bool off = ((g_live - 1) / (uint64_t)g_cfg.ab) & 1;
        if ((g_live - 1) % (uint64_t)g_cfg.ab == 0) {
            LARGE_INTEGER q;
            QueryPerformanceCounter(&q);
            fprintf(stderr, "[training] ab %s qpc %lld\n", off ? "off" : "on", (long long)q.QuadPart);
        }
        if (off) { hide(); return true; }
    }

    Sample s[2] = { read_fighter(kFighter[0]), read_fighter(kFighter[1]) };
    /* the history and the tracker always run in a fight, so F2 shows a full list;
     * online only this PC's own player is followed at all */
    const int me = online ? t5_netplay_local_slot() : -1;
    for (int p = 0; p < 2; p++) {
        if (online && p != me) continue;
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
        p1 = me == 0;
        p2 = me == 1;
        frames = false;
    } else if (gt != kGtPractice && !g_cfg.all) {
        show = false;
    }
    /* the practice tools' status line (practice.cpp; offline Practice only) */
    char status[96] = "";
    if (!online && gt == kGtPractice) t5_practice_status(status, sizeof status, g_cfg.de ? 1 : 0);
    if (show || status[0]) publish(show ? mode : kOff, p1, p2, frames, status);
    else hide();
    return true;
}
