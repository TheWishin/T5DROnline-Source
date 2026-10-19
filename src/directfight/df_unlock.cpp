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
 * T5_UNLOCK_ITEMS=1 (launcher Settings -> "Unlock all customization items")
 * makes every item in the item shop cost 0 Fight Money (detours of the two
 * price functions, below); the shop's own buy path then adds it to the save
 * like a bought item. Offline only: online games build no customization
 * (docs/DIRECTFIGHT.md "Unlocks", and the plan for costumes online there).
 *
 * T5_UNLOCK_TRACE=1 logs every distinct (caller, mask, game's answer, answer)
 * once, with the mode manager's mode, and the shop's item checks and prices
 * offline; =2 offline also installs the call tracer
 * (T5_RB_CALLTRACE=addr,..., rb_calls.log), which otherwise runs only with the
 * rollback loop.
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

namespace rb { void calltrace_install(); }   /* rb_detour.cpp: T5_RB_CALLTRACE (diagnostics) */

namespace unlock {
namespace {

constexpr uint32_t kFnCheck      = 0x002A732C;   /* (unlock byte & r3) != 0 */
constexpr uint32_t kFlagStages   = 0x10;         /* the Tekken 5 stages offered */
constexpr uint32_t kFlagJinpachi = 0x20;
constexpr uint32_t kUnlockByte   = 0x106849AA;   /* SYS-DATA +0x4A in the save image at 0x10684960 */
/* Tracing only (T5_UNLOCK_TRACE): answering "bought" here makes the shop show EQUIPPED and equip
 * nothing (its equip path searches the list itself), so the setting changes the prices instead.
 * The customization data of each side (VS custom data, 0x106C9934 + side * 0x1F4) starts with
 * the fighter's three costumes, 0x58 bytes each: +0x00 32 u16 parts bought (item id in the low
 * byte, in the order bought), +0x40 4 u16 the parts worn (HEAD, FACE, BODY up, BODY down; -1
 * none), +0x48 3 u32 bought colours (one bit per colour of COLOR1..3), +0x54 3 u8 the colours
 * worn. Checked by buying with Fight Money poked in (runs shop6/shop9). */
constexpr uint32_t kFnPartOwned  = 0x0029E754;   /* (side, costume, item id): a part bought */
constexpr uint32_t kFnColorOwned = 0x0029E7F4;   /* (side, costume, colour category, colour): a colour bought */
/* The price of an item, (character, costume, category, index) -> Fight Money: 0x152A18 picks one
 * of two by category and tail-calls it (the lifted code runs a tail call only after the function
 * returned, from its caller's trampoline), so the two are hooked: parts (HEAD..BODY down) from the per-character table *(0x10076724)[c] of
 * {item id, price}, colours (COLOR1..3). */
constexpr uint32_t kFnPricePart  = 0x00152918;   /* body of 0x1528F0 (the lifter split it after the prologue) */
constexpr uint32_t kFnPriceColor = 0x001522C8;

enum class Mode { Save, Fixed };
Mode g_mode = Mode::Save;
bool g_stages = false;
bool g_items = false;
bool g_trace = false;
bool g_installed = false;
rb::GuestFn o_check = nullptr;
rb::GuestFn o_part = nullptr;
rb::GuestFn o_color = nullptr;
rb::GuestFn o_price_part = nullptr;
rb::GuestFn o_price_color = nullptr;
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

/* The item shop asks these for the part or colour under its cursor: bought -> EQUIP,
 * else the price and BUY&EQUIP. */
void owned_note(const char* what, uint32_t side, uint32_t slot, uint32_t a, uint32_t b, uint32_t lr, uint32_t game, uint32_t r)
{
    std::lock_guard<std::mutex> lk(g_mu);
    if (g_seen.insert({ lr, (side << 4) | slot, (a << 8) | b, (game << 1) | r }).second)
        df::note("unlock: %s bought? side %u costume %u %u:%u from 0x%06X: game %u -> %u", what, side, slot, a, b, lr, game, r);
}

void h_part(ppu_context* ctx)
{
    const uint32_t side = (uint32_t)ctx->gpr[3], slot = (uint32_t)ctx->gpr[4], item = (uint32_t)ctx->gpr[5] & 0xFF;
    const uint32_t lr = (uint32_t)ctx->lr;
    o_part(ctx);
    const uint32_t game = (uint32_t)ctx->gpr[3];
    if (g_trace) owned_note("part", side, slot, 0, item, lr, game, game);
}

void h_color(ppu_context* ctx)
{
    const uint32_t side = (uint32_t)ctx->gpr[3], slot = (uint32_t)ctx->gpr[4], cat = (uint32_t)ctx->gpr[5], bit = (uint32_t)ctx->gpr[6] & 0xFF;
    const uint32_t lr = (uint32_t)ctx->lr;
    o_color(ctx);
    const uint32_t game = (uint32_t)ctx->gpr[3];
    if (g_trace) owned_note("colour", side, slot, cat, bit, lr, game, game);
}

/* The price the shop shows, checks against the Fight Money and takes: 0 with T5_UNLOCK_ITEMS. */
void price_hook(ppu_context* ctx, rb::GuestFn orig, const char* what)
{
    const uint32_t chr = (uint32_t)ctx->gpr[3], slot = (uint32_t)ctx->gpr[4], cat = (uint32_t)ctx->gpr[5], idx = (uint32_t)ctx->gpr[6];
    const uint32_t lr = (uint32_t)ctx->lr;
    orig(ctx);
    const uint32_t game = (uint32_t)ctx->gpr[3];
    const uint32_t r = g_items ? 0 : game;
    ctx->gpr[3] = r;
    if (g_trace) {
        std::lock_guard<std::mutex> lk(g_mu);
        if (g_seen.insert({ lr, 0x10000u | (chr << 8) | slot, (cat << 8) | idx, game }).second)
            df::note("unlock: %s price, character %u costume %u item %u:%u from 0x%06X: game %u -> %u", what, chr, slot, cat, idx, lr, game, r);
    }
}
void h_price_part(ppu_context* ctx) { price_hook(ctx, o_price_part, "part"); }
void h_price_color(ppu_context* ctx) { price_hook(ctx, o_price_color, "colour"); }

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
    g_items = env_on("T5_UNLOCK_ITEMS");
    g_trace = env_on("T5_UNLOCK_TRACE");
    g_mode = online && !save_online ? Mode::Fixed : Mode::Save;
    if (g_trace && g_mode == Mode::Save && getenv("T5_UNLOCK_TRACE")[0] == '2') rb::calltrace_install();   /* T5_RB_CALLTRACE too */
    if (g_mode == Mode::Save && !g_stages && !g_items && !g_trace) return;   /* nothing to change: no detour */
    if (g_mode == Mode::Fixed || g_stages || g_trace) {
        g_installed = rb::detour(kFnCheck, h_check, &o_check);
        if (!g_installed)
            df::note("unlock: 0x%06X not detourable -- unlocks as the save has them%s", kFnCheck,
                     g_mode == Mode::Fixed ? " (online: the two PCs may differ)" : "");
        else if (g_mode == Mode::Fixed)
            df::note("unlock: online game -- unlocks as on a fresh save (Tekken 5 stages and Jinpachi off), whatever the save%s",
                     g_stages || g_items ? " and the unlock settings" : "");
        else
            df::note("unlock: Tekken 5 stages %s", g_stages ? "unlocked (T5_UNLOCK_STAGES=1; the save is not changed)" : "as the save has them");
    }
    /* Items: offline only. Online the VS custom data stays the game's own (no customization in a direct fight). */
    if (g_mode == Mode::Save && (g_items || g_trace)) {
        const bool ok = rb::detour(kFnPricePart, h_price_part, &o_price_part) & rb::detour(kFnPriceColor, h_price_color, &o_price_color);
        if (g_trace) { rb::detour(kFnPartOwned, h_part, &o_part); rb::detour(kFnColorOwned, h_color, &o_color); }
        df::note("unlock: customization items %s", !ok ? "-- 0x152918/0x1522C8 not detourable, at their prices"
                 : g_items ? "free (T5_UNLOCK_ITEMS=1: every price 0; the Fight Money stays as it is)" : "at their prices");
    }
}

int t5_unlock_fixed(void) { return unlock::g_installed && unlock::g_mode == unlock::Mode::Fixed; }

} // extern "C"

namespace {
struct AutoInstall { AutoInstall() { t5_unlock_install(); } } g_auto;   /* the exe build: the lifted table is there at static init */
}
