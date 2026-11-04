/* Online throw-break timing, independently testable without the game.
 *
 * The fighter's current move points to timed input-command records. A record's
 * inclusive window is [start, end]. Only its end becomes end + the agreed input
 * delay; the game's input/command evaluator still decides whether a press breaks.
 * No input is synthesized, no animation clock is changed, and start is preserved.
 *
 * The scope below temporarily changes eligible endpoints while that evaluator
 * runs and restores the original bytes before it returns. It has no frame history:
 * rollback runs it again on restored state, and replay uses the recorded delay.
 * See docs/THROW_BREAK.md for the RAM evidence and required game-level checks.
 */
#pragma once
#include <stdint.h>

namespace np {

struct ThrowBreakRule {
    static constexpr int kMaxDelay = 30;
    static constexpr uint16_t kMaxEnd = 0x7FFF;
    static constexpr uint16_t kInput = 0, kStop = 0x8000;
    static constexpr uint32_t kEntryBytes = 0x18, kStart = 0x10, kEnd = 0x12;
    static constexpr uint32_t kMaxEntries = 128;

    static int delay(int n) { return n < 0 ? 0 : n > kMaxDelay ? kMaxDelay : n; }
    static bool paired_victim(int16_t role, int16_t opponent_role)
    {
        return role < 0 && opponent_role > 0;
    }
    static uint16_t end(uint16_t kind, uint16_t start, uint16_t original, int frames)
    {
        if (kind != kInput || start > original || original > kMaxEnd) return original;
        const uint32_t n = (uint32_t)original + (uint32_t)delay(frames);
        return (uint16_t)(n > kMaxEnd ? kMaxEnd : n);
    }
};

/* Big-endian guest data, not host-endian pointers. Bounded scanning fails closed
 * on an absent terminator or an indirect/special command list. Other ordinary
 * command kinds retain their endpoints. No game data or move IDs live here. */
struct ThrowBreakWindowScope {
    struct Saved { uint32_t address; uint16_t end; } saved[ThrowBreakRule::kMaxEntries];
    uint8_t* memory;
    uint32_t count = 0;

    static uint16_t read(const uint8_t* memory, uint32_t a)
    {
        return (uint16_t)((uint16_t)memory[a] << 8 | memory[a + 1]);
    }
    static void write(uint8_t* memory, uint32_t a, uint16_t n)
    {
        memory[a] = (uint8_t)(n >> 8); memory[a + 1] = (uint8_t)n;
    }
    ThrowBreakWindowScope(uint8_t* mem, uint32_t list, int frames, bool eligible)
        : memory(mem)
    {
        if (!eligible || !ThrowBreakRule::delay(frames)) return;
        bool terminated = false;
        for (uint32_t i = 0; i < ThrowBreakRule::kMaxEntries; i++) {
            const uint32_t a = list + i * ThrowBreakRule::kEntryBytes;
            const uint16_t kind = read(memory, a);
            if (kind == ThrowBreakRule::kStop) { terminated = true; break; }
            if (kind & 0x8000) { count = 0; return; }
            const uint16_t start = read(memory, a + ThrowBreakRule::kStart);
            const uint16_t original = read(memory, a + ThrowBreakRule::kEnd);
            if (ThrowBreakRule::end(kind, start, original, frames) != original)
                saved[count++] = { a + ThrowBreakRule::kEnd, original };
        }
        if (!terminated) { count = 0; return; }
        for (uint32_t i = 0; i < count; i++)
            write(memory, saved[i].address,
                  ThrowBreakRule::end(ThrowBreakRule::kInput, 0, saved[i].end, frames));
    }
    ~ThrowBreakWindowScope()
    {
        for (uint32_t i = count; i > 0; i--) write(memory, saved[i - 1].address, saved[i - 1].end);
    }
    ThrowBreakWindowScope(const ThrowBreakWindowScope&) = delete;
    ThrowBreakWindowScope& operator=(const ThrowBreakWindowScope&) = delete;
};

} // namespace np
