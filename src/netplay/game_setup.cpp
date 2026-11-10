/*
 * The player's own Controller Setup online (game_setup.h has the rule and why).
 *
 *   T5_PAD_SETUP_SAVE   the SYS-DATA whose Controller Setup this PC's player uses online; unset: the save the
 *                       launcher names for the costumes (T5_COSTUME_SAVE, the offline system save); "0": none
 *                       (the shoulder buttons do nothing online, as before)
 *
 * Read once per process, at the first live sample of a netplay session. Only this PC's exchanged sample
 * changes (netplay_core.cpp player_input): never a script, the peer's input, a re-simulated frame or a replay.
 */
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "ppu_recomp.h"     /* vm_base */
#include "netplay.h"
#include "game_setup.h"
#include "../platform/t5_addr.h"   /* T5A(): this program's address of a US address (EU Online) */

namespace np {
namespace {

const uint32_t kPhase = T5A(0x1008F070u);

inline uint32_t rd32(uint32_t a) { uint32_t v; memcpy(&v, vm_base + a, 4); return _byteswap_ulong(v); }

const char* fn_name(uint8_t fn)
{
    static const char* const k[gs::kFnMax + 1] = { "OFF", "LP", "RP", "LK", "RK", "LP+RP", "LK+RK", "LP+LK",
                                                   "RP+RK", "LP+RK", "RP+LK" };
    return fn <= gs::kFnMax ? k[fn] : "OFF";
}

struct Loaded { bool on = false; gs::Setup setup; };

Loaded load()
{
    Loaded l;
    const char* path = t5_env("T5_PAD_SETUP_SAVE");
    if (!path || !*path) path = t5_env("T5_COSTUME_SAVE");
    if (!path || !*path || !strcmp(path, "0")) {
        note("controller setup: no save named -- the game's default online (shoulder buttons OFF)");
        return l;
    }
    std::vector<uint8_t> d;
    if (FILE* fp = fopen(path, "rb")) {
        uint8_t buf[65536];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, fp)) > 0 && d.size() <= gs::kSaveSize) d.insert(d.end(), buf, buf + n);
        fclose(fp);
    }
    if (!gs::from_save(d.data(), d.size(), 0, l.setup)) {
        note("controller setup: %s -- the game's default online (shoulder buttons OFF)",
             d.empty() ? "the player's save cannot be read (none yet?)" : "not a SYS-DATA of this game");
        l.setup = gs::Setup();
        return l;
    }
    const uint8_t* f = l.setup.fn;
    if (l.setup.is_default()) {
        note("controller setup: the player's save has the game's default (shoulder buttons OFF)");
        return l;
    }
    l.on = true;
    note("controller setup: the player's own, from the offline save, applied to this PC's input in fights: "
         "L2 %s, R2 %s, L1 %s, R1 %s, triangle %s, circle %s, cross %s, square %s (T5_PAD_SETUP_SAVE=0: off)",
         fn_name(f[0]), fn_name(f[1]), fn_name(f[2]), fn_name(f[3]), fn_name(f[4]), fn_name(f[5]), fn_name(f[6]),
         fn_name(f[7]));
    return l;
}

}  // namespace

uint16_t game_setup_buttons(uint16_t buttons)
{
    static const Loaded l = load();
    const Mode m = mode();
    if (!gs::active(l.on, m == Mode::Host || m == Mode::Join, replaying(), rd32(kPhase))) return buttons;
    return gs::apply(l.setup, buttons);
}

}  // namespace np
