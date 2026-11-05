#include "mixed_timing.h"
#include "netplay.h"
#include "../platform/t5_game.h"
#include "../platform/t5_live_immediates.h"
#include <stdio.h>
#include <stdlib.h>
extern "C" uint8_t* vm_base;
namespace np { namespace mixed_timing {
void update()
{
    if (t5game::game() != t5game::Game::EU_ONLINE) return;
    static bool active = false;
    const bool wanted = np::enabled() && np::cross_program();
    if (wanted == active) return;
    if (wanted && !t5game::has_live_immediates(kManifest)) {
        np::note("FATAL: this EU game DLL lacks the exact mixed-timing manifest; rebuild it with the current tools");
        abort();
    }
    if (!transition(vm_base, active, wanted)) {
        np::note("FATAL: EU timing instruction or voice-duration record differs from the reviewed image; refusing a partial timing change");
        abort();
    }
    active = wanted;
    np::note("EU timing: %s (%zu reviewed live immediates, %zu voice durations)", active ? "mixed-program US deadlines" : "original same-program deadlines", sizeof kSites / sizeof kSites[0], sizeof kDurationRecords / sizeof kDurationRecords[0]);
}
} }
