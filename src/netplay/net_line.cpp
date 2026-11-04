/*
 * The connection line (docs/NETPLAY.md "Connection line"): one line at the bottom of the picture during an online
 * session -- ping, input delay, rollbacks per second and the deepest one, direct or relayed, this PC's speed. Off
 * by default; T5_NET_LINE=1 (launcher Settings -> Online, "Show the connection line in online matches") turns it on,
 * F3 switches it in the game. Drawn with the runtime's overlay into its status layer (ps3recomp patch 0113: layer
 * 2, drawn over the training display and the rematch panel), from the main thread's live boundary. It only reads
 * the netplay core's and the rollback loop's numbers: nothing of the game's state, input or timing changes.
 */
#include "../platform/t5_win.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <string>

#include "netplay.h"
#include "../rollback/rb_net.h"
#include "rsx_overlay.h"    /* ps3recomp patches 0045 (overlay), 0089 (layers), 0113 (status layer) */

namespace {

constexpr unsigned kLayer = 2;            /* the status layer (patch 0113) */
constexpr unsigned kEvery = 15;           /* frames between two updates (4 a second) */
constexpr float kPx = 2.0f;               /* font pixel: 12 x 16 canvas units per character */

struct LineState {
    bool inited = false;
    bool on = false;            /* T5_NET_LINE, then F3 */
    bool key_down = false;
    bool shown = false;
    unsigned frames = 0;        /* live boundaries since the last update */
    unsigned logged = 0;        /* updates since the last log line */
    LARGE_INTEGER qf{}, t_last{};
    bool t_ok = false;
    uint32_t rb_last = 0;
    uint32_t deepest_window = 0;
    std::string last_text;
} g;

#if defined(_WIN32)
bool focused()
{
    HWND fg = GetForegroundWindow();
    DWORD pid = 0;
    if (fg) GetWindowThreadProcessId(fg, &pid);
    return pid == GetCurrentProcessId();
}
bool f3_down() { return (GetAsyncKeyState(VK_F3) & 0x8000) != 0 && focused(); }
#else
bool f3_down() { return false; }   /* (the Mac build: T5_NET_LINE alone) */
#endif

uint32_t ping_colour(int ms)
{
    if (ms < 0) return RSX_OVL_RGBA(170, 170, 170, 255);
    if (ms <= 80) return RSX_OVL_RGBA(110, 220, 110, 255);
    if (ms <= 150) return RSX_OVL_RGBA(255, 214, 72, 255);
    return RSX_OVL_RGBA(255, 110, 110, 255);
}

void hide()
{
    if (g.shown) rsx_overlay_clear_layer(kLayer);
    g.shown = false;
    g.last_text.clear();
}

void publish(const np::LineInfo& li, double fps, double rb_per_s, uint32_t deepest)
{
    char ping[32], delay[48], rb[48], path[24], speed[24];
    if (li.rtt_ms >= 0) snprintf(ping, sizeof ping, "Ping %d ms", li.rtt_ms);
    else snprintf(ping, sizeof ping, "Ping ?");
    if (li.rollback) {
        if (li.feel_extra > 0) snprintf(delay, sizeof delay, "Delay %d (+%d)", li.delay, li.feel_extra);
        else snprintf(delay, sizeof delay, "Delay %d", li.delay);
        snprintf(rb, sizeof rb, "Rollbacks %.1f/s  max %u", rb_per_s, deepest);
    } else {
        snprintf(delay, sizeof delay, "Delay %d", li.delay);
        snprintf(rb, sizeof rb, "Lockstep");
    }
    snprintf(path, sizeof path, "%s", li.path[0] ? li.path : "-");
    snprintf(speed, sizeof speed, "%.0f fps", fps);
    if (!li.connected) snprintf(rb, sizeof rb, "Waiting for the opponent");
    const std::string text = std::string(ping) + "  |  " + delay + "  |  " + rb + "  |  " + path + "  |  " + speed;
    if (g.shown && text == g.last_text) return;
    g.last_text = text;
    /* the ping in its colour, the rest white, on a dark band at the bottom of the picture */
    const std::string rest = std::string("  |  ") + delay + "  |  " + rb + "  |  " + path + "  |  " + speed;
    const float wp = rsx_overlay_text_width(ping, kPx), wr = rsx_overlay_text_width(rest.c_str(), kPx);
    const float w = wp + wr + 24.0f, x0 = 640.0f - w / 2.0f, y = 690.0f;
    rsx_overlay_begin_layer(kLayer);
    rsx_overlay_rect(x0, y - 5.0f, w, 26.0f, RSX_OVL_RGBA(0, 0, 0, 160));
    rsx_overlay_text(x0 + 12.0f, y, kPx, ping_colour(li.rtt_ms), RSX_OVL_SHADOW, ping);
    rsx_overlay_text(x0 + 12.0f + wp, y, kPx, RSX_OVL_RGBA(235, 235, 235, 255), RSX_OVL_SHADOW, rest.c_str());
    rsx_overlay_end();
    g.shown = true;
    if (g.logged++ % 40 == 0) np::note("connection line: %s", text.c_str());   /* every ~10 s */
}

} // namespace

/* t5_hooks.cpp on_frame_start: every live boundary of the main thread (never a re-simulated one). */
void t5_net_line_frame()
{
    if (!g.inited) {
        g.inited = true;
        const std::string on = np::path_environment("T5_NET_LINE");
        g.on = !on.empty() && on[0] == '1';
        QueryPerformanceFrequency(&g.qf);
        if (g.on) rsx_overlay_prepare();
    }
    if (!np::enabled() || np::replaying()) { hide(); return; }
    const bool down = f3_down();
    if (down && !g.key_down) {
        g.on = !g.on;
        if (g.on) rsx_overlay_prepare();
        np::note("connection line %s (F3)", g.on ? "on" : "off");
        if (!g.on) hide();
        g.frames = kEvery;   /* update at once */
    }
    g.key_down = down;
    if (!g.on) return;
    if (++g.frames < kEvery) return;
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    const double s = g.t_ok ? (double)(now.QuadPart - g.t_last.QuadPart) / (double)g.qf.QuadPart : 0.0;
    const unsigned frames = g.frames;
    g.frames = 0;
    g.t_last = now;
    if (!g.t_ok) { g.t_ok = true; return; }
    if (s <= 0) return;
    const np::LineInfo li = np::line_info();
    if (!li.active) { hide(); return; }
    uint32_t total = 0, deepest = 0;
    double rb_per_s = 0;
    if (rb::net::line_stats(&total, &deepest)) {
        rb_per_s = total >= g.rb_last ? (double)(total - g.rb_last) / s : 0.0;
        g.rb_last = total;
    } else {
        g.rb_last = 0;
    }
    /* the deepest rollback of the last ~2 s stays on the line (a single deep one is otherwise gone in 0.25 s) */
    static uint32_t hold[8] = {};
    static unsigned k = 0;
    hold[k++ % 8] = deepest;
    uint32_t shown_deepest = 0;
    for (uint32_t d : hold) if (d > shown_deepest) shown_deepest = d;
    publish(li, (double)frames / s, rb_per_s, shown_deepest);
}
