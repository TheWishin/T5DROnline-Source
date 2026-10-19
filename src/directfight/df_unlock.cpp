/*
 * Unlocks without playing for them (docs/DIRECTFIGHT.md "Unlocks").
 *
 * T5DR keeps its unlocks in one byte of the system save (SYS-DATA offset 0x4A,
 * in memory at 0x106849AA, read through the save's setting object 0x106848B8):
 *
 *   0x01  the Tekken 5 stages earned   (the counter at SYS-DATA +0x4C passed 49)
 *   0x02  Jinpachi earned              (arcade cleared, or the counter passed 99)
 *   0x10  the Tekken 5 stages offered  (set by the title once it said so)
 *   0x20  Jinpachi offered             (likewise)
 *
 * Everything that offers them asks one function, 0x2A732C(mask) = (byte & mask)
 * != 0, with mask 0x10 or 0x20: the stage tables' availability callbacks
 * (0x613F8 for ids 0..13 and 15), the stage select's OLD/NEW switch (0x1151D0),
 * the random stage pickers (0x5C930), the select grid's Jinpachi and random
 * cells (0x112F04, 0x58F64) and the select mode's set-up (0x248768).
 *
 * T5_UNLOCK_STAGES=1 (launcher Settings -> "Unlock all stages") answers yes for
 * 0x10 through an entry detour of 0x2A732C. Nothing is written to guest memory:
 * the save keeps the player's own byte, and the setting turned off is the old
 * game again.
 *
 * Online the answer is fixed: in a game started for online play (T5_NET_MODE,
 * T5_CTL_DIR, T5_FIGHT, T5_FIGHT_FILE) every call answers as a fresh save does
 * (nothing unlocked), whatever the setting and the save. The two PCs then build
 * the same select grid (no Jinpachi or random cell), the same stage lists and
 * the same random stage picks; the stage of an online match is the lobby's and
 * is written by the direct-fight driver, which works for every stage id with
 * or without the unlock. T5_UNLOCK_ONLINE=save (tests only) lets the save and
 * the setting count online too, the old behaviour.
 *
 * T5_UNLOCK_TRACE=1 logs every distinct (caller, mask, game's answer, answer)
 * once, with the mode manager's mode.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mutex>
#include <set>
#include <tuple>

#include "sys_ppu_thread.h"
#include "../rollback/rb_detour.h"
#include "df.h"

namespace unlock {
namespace {

constexpr uint32_t kFnCheck      = 0x002A732C;   /* (unlock byte & r3) != 0 */
constexpr uint32_t kFlagStages   = 0x10;         /* the Tekken 5 stages offered */
constexpr uint32_t kFlagJinpachi = 0x20;
constexpr uint32_t kUnlockByte   = 0x106849AA;   /* SYS-DATA +0x4A in the save image at 0x10684960 */

enum class Mode { Save, Fixed };
Mode g_mode = Mode::Save;
bool g_stages = false;
bool g_trace = false;
bool g_installed = false;
rb::GuestFn o_check = nullptr;
std::mutex g_mu;
std::set<std::tuple<uint32_t, uint32_t, uint32_t, uint32_t>> g_seen;

bool env_on(const char* name)
{
    const char* e = getenv(name);
    return e && *e && *e != '0';
}

bool env_set(const char* name)
{
    const char* e = getenv(name);
    return e && *e;
}

void h_check(ppu_context* ctx)
{
    const uint32_t mask = (uint32_t)ctx->gpr[3];
    const uint32_t lr = (uint32_t)ctx->lr;
    o_check(ctx);
    const uint32_t game = (uint32_t)ctx->gpr[3];
    uint32_t r = game;
    if (g_mode == Mode::Fixed) r = 0;                       /* a fresh save: nothing unlocked */
    else if (g_stages && (mask & kFlagStages)) r = 1;
    ctx->gpr[3] = r;
    if (g_trace) {
        std::lock_guard<std::mutex> lk(g_mu);
        if (g_seen.insert({ lr, mask, game, r }).second)
            df::note("unlock: check(0x%02X) from 0x%06X: game %u -> %u (mode %d, byte 0x%02X)", mask, lr, game, r,
                     (int)df::mode_cur(), vm_base ? df::rd8(kUnlockByte) : 0);
    }
}

} // namespace
} // namespace unlock

extern "C" {

/* Main thread, before the select screens run: the exe build at static init,
 * the game-DLL build at the first frame boundary (t5_hooks.cpp on_frame_start). */
void t5_unlock_install(void)
{
    using namespace unlock;
    static bool done = false;
    if (done || !rb::detour_ready()) return;
    done = true;
    const bool online = env_set("T5_NET_MODE") || env_set("T5_CTL_DIR") || env_set("T5_FIGHT") || env_set("T5_FIGHT_FILE");
    const char* keep = getenv("T5_UNLOCK_ONLINE");
    const bool save_online = keep && !strcmp(keep, "save");
    g_stages = env_on("T5_UNLOCK_STAGES");
    g_trace = env_on("T5_UNLOCK_TRACE");
    g_mode = online && !save_online ? Mode::Fixed : Mode::Save;
    if (g_mode == Mode::Save && !g_stages && !g_trace) return;   /* nothing to change: no detour */
    g_installed = rb::detour(kFnCheck, h_check, &o_check);
    if (!g_installed) {
        df::note("unlock: 0x%06X not detourable -- unlocks as the save has them%s", kFnCheck,
                 g_mode == Mode::Fixed ? " (online: the two PCs may differ)" : "");
        return;
    }
    if (g_mode == Mode::Fixed)
        df::note("unlock: online game -- unlocks as on a fresh save (Tekken 5 stages and Jinpachi off), whatever the save%s",
                 g_stages ? " and T5_UNLOCK_STAGES" : "");
    else
        df::note("unlock: Tekken 5 stages %s", g_stages ? "unlocked (T5_UNLOCK_STAGES=1; the save is not changed)" : "as the save has them");
}

int t5_unlock_fixed(void) { return unlock::g_installed && unlock::g_mode == unlock::Mode::Fixed; }

} // extern "C"

namespace {
struct AutoInstall { AutoInstall() { t5_unlock_install(); } } g_auto;   /* the exe build: the lifted table is there at static init */
}
