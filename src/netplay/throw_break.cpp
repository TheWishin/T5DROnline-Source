/* The online throw-break rule's connection to the game's command evaluator.
 * RAM layout and causal probes: docs/THROW_BREAK.md. This is our own wrapper;
 * no lifted implementation or per-character move table is included.
 */
#include "../platform/t5_win.h"
#include "../platform/t5_game.h"
#include <stdio.h>
#include <stdlib.h>
#include "ppu_recomp.h"
#include "../rollback/rb_detour.h"
#include "netplay.h"
#include "replay_paths.h"
#include "throw_break.h"

extern "C" uint8_t* vm_base;

namespace {
constexpr uint32_t kEvaluate = 0x000EF7BC;
constexpr uint32_t kFighter[2] = { 0x10090040, 0x10090910 };
constexpr uint32_t kRole = 0x148;
constexpr uint32_t kGuestLimit = 0x80000000;
rb::GuestFn original = nullptr;
bool installed = false;
bool attempted = false;
int frame_delay = 0;
thread_local bool evaluating = false;

uint32_t read32(uint32_t a)
{
    return (uint32_t)vm_base[a] << 24 | (uint32_t)vm_base[a + 1] << 16 |
           (uint32_t)vm_base[a + 2] << 8 | vm_base[a + 3];
}
struct EvaluationGuard {
    EvaluationGuard() { evaluating = true; }
    ~EvaluationGuard() { evaluating = false; }
};

void log_window(const np::ThrowBreakWindowScope& scope, uint32_t age, uint32_t fighter, uint32_t list)
{
    static bool read = false;
    static FILE* file = nullptr;
    static uint32_t lines = 0;
    if (!read) {
        read = true;
        const std::string path = np::path_environment("T5_THROW_BREAK_LOG");
        if (!path.empty()) file = replay_paths::open(path.c_str(), "w");
    }
    if (!file || lines >= 4096) return;
    for (uint32_t i = 0; i < scope.count && lines < 4096; i++, lines++) {
        const auto& saved = scope.saved[i];
        fprintf(file, "age=%u fighter=%08X list=%08X end_addr=%08X end=%u->%u delay=%d\n",
                age, fighter, list, saved.address, saved.end,
                np::ThrowBreakWindowScope::read(vm_base, saved.address), frame_delay);
    }
    if (scope.count) fflush(file);
}

void evaluate(ppu_context* ctx)
{
    const uint32_t list = (uint32_t)ctx->gpr[3];
    const uint32_t fighter = (uint32_t)ctx->gpr[5], opponent = (uint32_t)ctx->gpr[6];
    const bool pair = (fighter == kFighter[0] && opponent == kFighter[1]) ||
                      (fighter == kFighter[1] && opponent == kFighter[0]);
    bool eligible = frame_delay > 0 && !evaluating && pair &&
        list >= 0x10000 && list <= kGuestLimit - np::ThrowBreakRule::kMaxEntries * np::ThrowBreakRule::kEntryBytes &&
        np::ThrowBreakRule::paired_victim((int16_t)np::ThrowBreakWindowScope::read(vm_base, fighter + kRole),
                                          (int16_t)np::ThrowBreakWindowScope::read(vm_base, opponent + kRole));
    if (eligible) {
        const uint32_t move = read32(fighter + 0xC4);
        eligible = move >= 0x10000 && move <= kGuestLimit - 0x18 && read32(move + 0x14) == list;
    }
    if (!eligible) { original(ctx); return; }
    /* EF790's short prologue tail-calls EF7BC. Hook its complete body so all
     * nested guest calls finish before the scope restores the command bytes. */
    EvaluationGuard guard;
    {
        np::ThrowBreakWindowScope window(vm_base, list, frame_delay, true);
        log_window(window, (uint32_t)ctx->gpr[4], fighter, list);
        original(ctx);
    }
}
} // namespace

extern "C" void t5_throw_break_install(void)
{
    if (attempted || !rb::detour_ready()) return;
    attempted = true;
    if (!t5game::hooks_ok("online throw breaks")) return;
    installed = rb::detour(kEvaluate, evaluate, &original);
    np::note("throw breaks: timed input-command endpoint rule %s (evaluator 0x%08X)",
             installed ? "installed" : "UNAVAILABLE", kEvaluate);
}

extern "C" int t5_throw_break_ready(void) { return installed ? 1 : 0; }

/* Called before every simulated frame, including every re-simulation. The caller
 * supplies an agreed delay, never a local setting or an estimated network RTT. */
extern "C" void t5_throw_break_frame(bool enabled, int delay)
{
    frame_delay = enabled ? np::ThrowBreakRule::delay(delay) : 0;
    if (enabled && !installed) {
        np::note("FATAL: online throw-break evaluator could not be installed; refusing incompatible simulation");
        abort();
    }
}
