/*
 * "Always left" (a 1.1.8 test, always_left.h has the rule; docs/NETPLAY.md "Always left"):
 *
 *   T5_ALWAYS_LEFT=1   (launcher Settings "Always see me on the left") on; unset = off, nothing here runs.
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

bool t5_always_left_enabled()
{
    if (g_enabled < 0) g_enabled = al::parse_enabled(getenv("T5_ALWAYS_LEFT")) ? 1 : 0;   /* (also from a static constructor) */
    return g_enabled == 1;
}

extern "C" void t5_always_left_frame(void)
{
    if (!t5_always_left_enabled()) return;
    static bool said = false;
    if (!said) {
        said = true;
        np::note("always left: on -- as P2 this PC shows the fight mirrored (you on the left) and swaps your left and "
                 "right; the game and the other PC are unchanged (offline: Versus fights, the P2 side)");
    }
    al::Frame f;
    f.enabled = true;
    f.net = net_mode();
    f.replaying = np::replaying();
    f.local_slot = np::local_slot();
    f.phase = rd32(kPhase);
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
    static int trace = -1;
    if (trace < 0) { const char* t = getenv("T5_ALWAYS_LEFT_TRACE"); trace = t && *t == '1'; }
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
