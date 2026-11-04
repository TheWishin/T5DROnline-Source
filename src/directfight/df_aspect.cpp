/* True 4:3 and the 16:9 camera -- a RESEARCH switch, off unless T5_ASPECT_CAMERA=16:9
 * (docs/PICTURE_FORMAT.md "True 4:3 online: what is in the way").
 *
 * Told it has a 4:3 TV (PS3_VIDEO_ASPECT=4:3, ps3recomp patch 0107) the game lays its HUD out for 4:3 and
 * gives the fight camera a 4:3 aspect: the camera set-up 0x816D4 stores 4/3 (0x46985C) instead of 16/9
 * (0x469860) at +0x1E4 of the camera object *(0x46984C). The camera then frames the fight for the narrower
 * view and the fighters' screen x (+0x6C8, func_0028AB40) follow it. Those screen x decide the side flags
 * (+0x1C2/+0x1C3, func_000808D8: which fighter is on the left, i.e. which way up/down sidesteps), so a 4:3
 * PC and a 16:9 PC play different fights: a lockstep pair, one side 4:3, had the side flags apart at frame
 * 1,783 and every fighter word after it (runs ard3; the camera words alone from frame 224).
 *
 * With T5_ASPECT_CAMERA=16:9 this file puts the 16:9 aspect back right after 0x816D4 (and forces the
 * set-mode 0x80F10 to 16:9) and asks the renderer to show the middle 4:3 of the 16:9 3D picture under the
 * game's 4:3 HUD (rsx_live_draw_set_3d_crop): the picture is right, and the fight stays the same as on a 16:9
 * PC for its first ~1,500 frames (runs ard4: frame 224 -> 1,762) -- then the camera drifts apart by a few
 * millionths again (another reader of the 4:3 mode: not found yet) and the side flags follow at frame
 * ~3,100. So it is NOT safe online; the launcher never sends PS3_VIDEO_ASPECT to an online game.
 */
#include "../platform/t5_win.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sys_ppu_thread.h"
#include "../rollback/rb_detour.h"
#include "df.h"
#include "../platform/t5_addr.h"   /* T5A(): this program's address of a US address (EU Online) */

#if defined(_WIN32)
extern "C" void rsx_live_draw_set_3d_crop(float k);   /* ps3recomp patch 0107, rsx_live_draw.c */
#endif

namespace {

const uint32_t kFnCameraSetup = T5A(0x000816D4);   /* writes the camera's aspect (+0x1E4) from the display's wide flag */
const uint32_t kFnSetMode = T5A(0x00080F10);      /* set-mode(r3 = 0/2 -> 4:3, else 16:9): camera aspect, the 4:3 / 16:9 camera constants, the draw library's mode (0x15C5FC) */
const uint32_t kCameraPtr = T5A(0x0046984C);       /* TOC 0x470540 - 0x6CF4: the camera object */
constexpr uint32_t kCameraAspect = 0x1E4;

rb::GuestFn o_setup = nullptr, o_mode = nullptr;
unsigned g_mode_fixed = 0;
bool g_on = false;
unsigned g_fixed = 0, g_odd = 0;
constexpr uint32_t kBits16x9 = 0x3FE38E39u;   /* 16/9 as a float: what 0x469860 holds */
constexpr uint32_t kBits4x3 = 0x3FAAAAABu;    /* 4/3: 0x46985C */

bool env_set(const char* n) { const char* e = getenv(n); return e && *e; }

void keep_16x9()
{
    const uint32_t cam = df::rd32(kCameraPtr);
    if (!cam || cam >= 0x20000000u) return;
    const uint32_t now = df::rd32(cam + kCameraAspect);
    if (now == kBits4x3) {
        df::wr32(cam + kCameraAspect, kBits16x9);
        if (g_fixed++ < 3) df::note("aspect: camera set-up -> 16:9 framing kept (T5_ASPECT_CAMERA=16:9; HUD 4:3)");
    } else if (now != kBits16x9 && g_odd++ < 3) {
        df::note("aspect: camera aspect 0x%08X is neither 4/3 nor 16/9 -- left as it is", now);
    }
}

void h_setup(ppu_context* ctx) { o_setup(ctx); keep_16x9(); }
void h_mode(ppu_context* ctx)
{
    const uint64_t m = ctx->gpr[3];
    if ((uint32_t)m == 0 || (uint32_t)m == 2) {
        ctx->gpr[3] = 1;
        if (g_mode_fixed++ < 3) df::note("aspect: set-mode(%u) -> 1 (16:9 camera)", (unsigned)m);
    }
    o_mode(ctx);
}

} // namespace

extern "C" {

/* 1 when the 3D picture is drawn with the 16:9 camera while the game shows 4:3 (rsx_live_draw.c asks) */
int t5_aspect_3d_crop(void) { return g_on ? 1 : 0; }

/* Main thread, before any scene: the exe build at static init, the game-DLL build at the first frame
 * boundary (t5_hooks.cpp), like t5_unlock_install. */
void t5_aspect_install(void)
{
    static bool done = false;
    if (done || !rb::detour_ready()) return;
    done = true;
    const char* a = getenv("PS3_VIDEO_ASPECT");
    if (!(a && (!strcmp(a, "4:3") || !strcmp(a, "4_3") || !strcmp(a, "43")))) return;
    const char* c = getenv("T5_ASPECT_CAMERA");
    const bool online = env_set("T5_NET_MODE") || env_set("T5_CTL_DIR") || env_set("T5_FIGHT") || env_set("T5_FIGHT_FILE");
    const bool keep16 = c && !strcmp(c, "16:9");   /* research switch only (see the head of this file) */
    (void)online;
    if (!keep16) { df::note("aspect: True 4:3 with the game's own 4:3 camera%s", online ? " -- a game started for online play: the other PC must be on True 4:3 too, mixed settings do not stay in sync" : ""); return; }
    g_on = rb::detour(kFnCameraSetup, h_setup, &o_setup);
    if (g_on && !rb::detour(kFnSetMode, h_mode, &o_mode))
        df::note("aspect: 0x80F10 not detourable -- its camera set-ups keep the game's 4:3");
#if defined(_WIN32)
    if (g_on) rsx_live_draw_set_3d_crop(4.0f / 3.0f);   /* (16/9) / (4/3): the middle 4:3 of the 16:9 picture */
#endif
    df::note("aspect: T5_ASPECT_CAMERA=16:9 (research) -- the camera keeps the 16:9 framing, the 3D picture is its "
             "middle 4:3; not safe for mixed online play: %s", g_on ? "on" : "0x816D4 not detourable, the game's own camera");
}

} // extern "C"

namespace { struct AutoInstall { AutoInstall() { t5_aspect_install(); } } g_auto; }
