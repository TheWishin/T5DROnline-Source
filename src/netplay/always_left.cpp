/*
 * "Always left" (1.1.9, casual matches; always_left.h has the rule; docs/NETPLAY.md "Always left"):
 *
 *   T5_ALWAYS_LEFT=1   (launcher "Always see me on the left", Settings and the Online tab) on; unset = off.
 *   T5_NET_CASUAL=1    (the launcher, from the lobby's match_start) this online match is casual: only then
 *                      is an online P2 shown mirrored. Both are the SESSION's values (t5_env): a persistent
 *                      game gets them again with every match, so a ranked match after a casual one is never
 *                      mirrored, and the option changed in the launcher counts from the next match on.
 *
 * t5_always_left_frame() runs at the top of each frame (t5_hooks.cpp on_frame_start, main thread, never in a
 * re-simulated frame): it reads the fight phase and the game type (guest memory, read only) and tells the
 * renderer (ps3recomp patch 0086) whether to show this frame mirrored. While it does:
 *   - online: this player's sample has left and right swapped (always_left_input, netplay_core.cpp
 *     sample_local) -- before it is exchanged, so both PCs simulate the same, swapped input;
 *   - offline (a Versus fight): port 2's data has left and right swapped as the game reads it
 *     (t5_always_left_pad_fix, from the late-input pad hook or the direct fight's; T5_LATE_INPUT=0 without a
 *     direct fight has no such hook and stays unswapped).
 *
 *   T5_ALWAYS_LEFT_TRACE=1   (tests) every 20 fight frames: both fighters' places on the floor and their
 *                            distance, on stderr ("[always-left] trace ...")
 */
#include "../platform/t5_win.h"

#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

#include "ppu_recomp.h"     /* ppu_context, vm_base */
#include "netplay.h"
#include "always_left.h"

extern "C" void rsx_live_draw_set_always_left(int on);   /* ps3recomp patch 0086 (libs/video/rsx_live_draw.c) */
extern "C" int32_t cellPadGetData(uint32_t port, void* data_guest);   /* ps3recomp libs/input/cellPad.c */

namespace {

constexpr uint32_t kPhase = 0x1008F070u, kGameType = 0x1008EBACu;

std::atomic<bool> g_active{ false };
int g_enabled = -1;

/* The session's values (t5_env: a persistent game's match overlay, else the process environment), read again
 * whenever the fight phase changes -- a new match always passes through the select screen -- not every frame. */
struct Session { bool enabled = false, casual = false; };
Session read_session()
{
    Session s;
    s.enabled = al::parse_enabled(t5_env("T5_ALWAYS_LEFT"));
    const char* c = t5_env("T5_NET_CASUAL");
    s.casual = c && c[0] == '1' && c[1] == 0;
    return s;
}

/* Started for online play (the lobby's persistent game, or one netplay session): never the offline rule. */
bool online_game()
{
    static int v = -1;
    if (v < 0) {
        const char* ctl = getenv("T5_CTL_DIR");
        const char* m = getenv("T5_NET_MODE");
        v = (ctl && *ctl) || (m && (!_stricmp(m, "host") || !_stricmp(m, "join"))) ? 1 : 0;
    }
    return v == 1;
}

inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }
inline uint16_t rd16(uint32_t a) { uint16_t v; memcpy(&v, vm_base + a, 2); return _byteswap_ushort(v); }
inline void wr16(uint32_t a, uint16_t x) { x = _byteswap_ushort(x); memcpy(vm_base + a, &x, 2); }
inline float rdf(uint32_t a) { const uint32_t u = rd32(a); float f; memcpy(&f, &u, 4); return f; }
constexpr uint32_t kFighter[2] = { 0x10090030u, 0x10090900u };   /* +0x10 x, +0x18 z (training_logic.h) */

al::Net net_mode()
{
    switch (np::mode()) {
    case np::Mode::Host: return al::Net::Host;
    case np::Mode::Join: return al::Net::Join;
    case np::Mode::Local: return al::Net::Local;
    default: return al::Net::Off;
    }
}

}  // namespace

/* The process's value (the offline pad hook is registered by it, from a static constructor). */
bool t5_always_left_enabled()
{
    if (g_enabled < 0) g_enabled = al::parse_enabled(getenv("T5_ALWAYS_LEFT")) ? 1 : 0;
    return g_enabled == 1;
}

extern "C" void t5_always_left_frame(void)
{
    static int trace = -1;
    if (trace < 0) { const char* t = getenv("T5_ALWAYS_LEFT_TRACE"); trace = t && *t == '1'; }
    /* one guest read per frame; the session's values only when the phase changes */
    static uint32_t last_phase = ~0u;
    static Session sess;
    const uint32_t phase = rd32(kPhase);
    if (phase != last_phase) {
        last_phase = phase;
        const Session was = sess;
        sess = read_session();
        if (sess.enabled != was.enabled || (sess.enabled && sess.casual != was.casual))
            np::note("always left: %s", !sess.enabled ? "off"
                     : online_game() ? (sess.casual ? "on -- this casual match: as P2 this PC shows the fight mirrored "
                                                      "(you on the left) and swaps your left and right; the game and "
                                                      "the other PC are unchanged"
                                                    : "on, but not in this match (ranked, Quick or a tournament set: "
                                                      "only casual matches)")
                     : "on -- offline Versus fights show the P2 side mirrored");
    }
    if (!sess.enabled && !g_active.load(std::memory_order_relaxed) && !trace) return;
    al::Frame f;
    f.enabled = sess.enabled;
    f.casual = sess.casual;
    f.online_game = online_game();
    f.net = net_mode();
    f.replaying = np::replaying();
    f.local_slot = np::local_slot();
    f.phase = phase;
    f.game_type = rd32(kGameType);
    const bool a = al::active(f);
    if (a != g_active.load(std::memory_order_relaxed)) {
        g_active.store(a, std::memory_order_relaxed);
        rsx_live_draw_set_always_left(a ? 1 : 0);
        np::note("always left: %s (%s, game type %u)", a ? "the fight is shown mirrored, left/right swapped"
                                                          : "normal picture",
                 f.net == al::Net::Off || f.net == al::Net::Local ? "offline" : f.local_slot == 1 ? "P2" : "P1",
                 f.game_type);
    }
    static uint32_t n = 0;
    if (trace && f.phase == al::kPhaseFight && n++ % 20 == 0) {
        const float x1 = rdf(kFighter[0] + 0x10), z1 = rdf(kFighter[0] + 0x18);
        const float x2 = rdf(kFighter[1] + 0x10), z2 = rdf(kFighter[1] + 0x18);
        fprintf(stderr, "[always-left] trace %u mirrored=%d P1 %.0f %.0f P2 %.0f %.0f dist %.0f\n", n - 1, a ? 1 : 0,
                x1, z1, x2, z2, sqrtf((x2 - x1) * (x2 - x1) + (z2 - z1) * (z2 - z1)));
    }
}

namespace np {

PadInput always_left_input(PadInput in)
{
    if (!g_active.load(std::memory_order_relaxed)) return in;
    in.buttons = al::swap_lr(in.buttons);
    in.lx = al::mirror_axis(in.lx);
    in.rx = al::mirror_axis(in.rx);
    return in;
}

}  // namespace np

/* Offline: port 2's data as the game is about to read it (s32 len, u16 button[], big-endian), mirrored while
 * the Versus fight is: [2] DIGITAL1 (LEFT 0x80, RIGHT 0x20), [4] right stick X, [6] left stick X, and in
 * press mode [8] / [9] the RIGHT / LEFT pressure. Called by both offline pad hooks: the one below (late
 * input) and the direct fight's (df_hooks.cpp, its scripts and devices). */
extern "C" void t5_always_left_pad_fix(uint32_t port, uint32_t ea)
{
    if (port != 1 || !ea || !g_active.load(std::memory_order_relaxed)) return;
    const int32_t len = (int32_t)rd32(ea);
    if (len < 8) return;
    const uint32_t b = ea + 4;
    wr16(b + 2 * 2, al::swap_lr(rd16(b + 2 * 2)));
    wr16(b + 4 * 2, (uint16_t)al::mirror_axis((uint8_t)rd16(b + 4 * 2)));
    wr16(b + 6 * 2, (uint16_t)al::mirror_axis((uint8_t)rd16(b + 6 * 2)));
    if (len >= 20) {   /* press mode (CELL_PAD_LEN_CHANGE_PRESS_ON) */
        const uint16_t pr = rd16(b + 8 * 2), pl = rd16(b + 9 * 2);
        wr16(b + 8 * 2, pl);
        wr16(b + 9 * 2, pr);
    }
}

/* The direct fight reads the pads itself offline when it is configured or scripted (df_hooks.cpp Register:
 * T5_FIGHT, T5_FIGHT_FILE, T5_DF_SCRIPT, T5_DF_SCRIPT2) and calls t5_always_left_pad_fix there; the first
 * registration of a NID wins, so the late-input hook below stays out of its way. */
bool t5_always_left_df_pads()
{
    for (const char* k : { "T5_FIGHT", "T5_FIGHT_FILE", "T5_DF_SCRIPT", "T5_DF_SCRIPT2" }) {
        const char* v = getenv(k);
        if (v && *v) return true;
    }
    return false;
}

/* Offline, late input (t5_hooks.cpp registers it when T5_ALWAYS_LEFT is on and the direct fight does not read
 * the pads): the game's own pad read, then t5_always_left_pad_fix. */
extern "C" void t5_always_left_pad_read(ppu_context* ctx)
{
    const uint32_t port = (uint32_t)ctx->gpr[3], ea = (uint32_t)ctx->gpr[4];
    const int32_t r = cellPadGetData(port, (void*)(uintptr_t)ea);
    ctx->gpr[3] = (uint64_t)(int64_t)r;
    if (r == 0) t5_always_left_pad_fix(port, ea);
}
