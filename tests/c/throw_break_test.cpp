/* The real endpoint mutation scope, with made-up command records and two
 * deterministic game models. No game assets, network, or lifted code. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdexcept>
#include <vector>
#include "../../src/netplay/throw_break.h"

using np::ThrowBreakRule;
using np::ThrowBreakWindowScope;
static unsigned checks = 0;
static void check(bool ok, const char* what)
{
    checks++;
    if (!ok) { printf("FAIL %s\n", what); exit(1); }
}
static void put(std::vector<uint8_t>& mem, uint32_t at, uint16_t n)
{
    ThrowBreakWindowScope::write(mem.data(), at, n);
}
static uint16_t get(const std::vector<uint8_t>& mem, uint32_t at)
{
    return ThrowBreakWindowScope::read(mem.data(), at);
}
static std::vector<uint8_t> commands(uint16_t start = 1, uint16_t end = 15)
{
    std::vector<uint8_t> mem(ThrowBreakRule::kMaxEntries * ThrowBreakRule::kEntryBytes, 0);
    put(mem, ThrowBreakRule::kStart, start); put(mem, ThrowBreakRule::kEnd, end);
    put(mem, ThrowBreakRule::kEntryBytes, ThrowBreakRule::kStop);
    return mem;
}
static bool accepts(const std::vector<uint8_t>& mem, int age, uint16_t button)
{
    /* A small model of the game's own timed input evaluator. The rule never
     * supplies buttons: the existing input condition must still pass. */
    return button == 1 && age >= get(mem, ThrowBreakRule::kStart) && age <= get(mem, ThrowBreakRule::kEnd);
}

static void endpoints()
{
    for (int delay = 0; delay <= ThrowBreakRule::kMaxDelay; delay++) {
        auto mem = commands(); const auto before = mem;
        for (int age = -1; age <= 64; age++) {
            {
                ThrowBreakWindowScope scope(mem.data(), 0, delay, true);
                check(get(mem, ThrowBreakRule::kStart) == 1, "start unchanged");
                check(get(mem, ThrowBreakRule::kEnd) == 15 + delay, "end extended exactly by delay");
                check(accepts(mem, age, 1) == (age >= 1 && age <= 15 + delay), "inclusive extended endpoint");
                check(!accepts(mem, age, 2), "wrong break button still fails");
                check(!accepts(mem, age, 0), "no press still fails");
            }
            check(mem == before, "every call restores bytes; no compounded extension");
        }
        {
            ThrowBreakWindowScope scope(mem.data(), 0, delay, true);
            check(accepts(mem, 15 + delay, 1), "offline last-frame press delivered after delay breaks");
            check(!accepts(mem, 16 + delay, 1), "one frame beyond compensated end fails");
            check(!accepts(mem, 0, 1), "window never opens early");
        }
    }
    check(ThrowBreakRule::end(0, 1, 15, -1) == 15, "negative delay unchanged");
    check(ThrowBreakRule::end(0, 1, 15, 999) == 45, "delay capped at negotiated maximum");
    check(ThrowBreakRule::end(0, 1, 32760, 30) == 32767, "endpoint saturates without signed wrap");
    check(ThrowBreakRule::end(0, 1, 65535, 30) == 65535, "invalid signed bound unchanged");
    check(ThrowBreakRule::end(0, 20, 15, 30) == 15, "reversed window unchanged");
    check(ThrowBreakRule::end(1, 1, 15, 30) == 15, "other input kind unchanged");
    check(ThrowBreakRule::paired_victim(-1, 1), "victim role qualifies");
    for (int16_t a : { (int16_t)-1, (int16_t)0, (int16_t)1 })
        for (int16_t b : { (int16_t)-1, (int16_t)0, (int16_t)1 })
            check(ThrowBreakRule::paired_victim(a, b) == (a < 0 && b > 0), "role gate is independent of local slot");
    puts("endpoints, early/wrong presses ok");
}

static void scope_guards()
{
    auto mem = commands(); const auto original = mem;
    { ThrowBreakWindowScope scope(mem.data(), 0, 8, false); check(mem == original, "offline or legacy replay unchanged"); }
    try {
        ThrowBreakWindowScope scope(mem.data(), 0, 8, true);
        check(get(mem, ThrowBreakRule::kEnd) == 23, "scope active during evaluator");
        throw std::runtime_error("synthetic evaluator failure");
    } catch (const std::runtime_error&) {}
    check(mem == original, "exception restores endpoints");
    for (uint16_t kind : { (uint16_t)0x8005, (uint16_t)0x8006 }) {
        mem = commands(); put(mem, ThrowBreakRule::kEntryBytes, kind); const auto before = mem;
        { ThrowBreakWindowScope scope(mem.data(), 0, 8, true); check(mem == before, "indirect list fails closed without partial writes"); }
        check(mem == before, "indirect list restoration unchanged");
    }
    mem = commands(); put(mem, ThrowBreakRule::kEntryBytes, 0); const auto unterminated = mem;
    { ThrowBreakWindowScope scope(mem.data(), 0, 8, true); check(mem == unterminated, "unterminated list fails closed"); }
    mem = commands();
    put(mem, 0x18, 1); put(mem, 0x18 + 0x10, 2); put(mem, 0x18 + 0x12, 7);
    put(mem, 0x30, 0); put(mem, 0x30 + 0x10, 9); put(mem, 0x30 + 0x12, 12);
    put(mem, 0x48, ThrowBreakRule::kStop); const auto several = mem;
    {
        ThrowBreakWindowScope scope(mem.data(), 0, 3, true);
        check(get(mem, 0x12) == 18 && get(mem, 0x42) == 15, "alternate ordinary break entries extended");
        check(get(mem, 0x2A) == 7, "other command kind endpoint unchanged");
        check(get(mem, 0x40) == 9, "alternate command start unchanged");
    }
    check(mem == several, "all alternate endpoints restored");
    puts("scope restoration and guards ok");
}

struct Game {
    uint64_t hash = 1469598103934665603ull;
    unsigned breaks[2] = {}, throws[2] = {};
    uint16_t previous[2] = {};
    void mix(uint32_t n) { hash ^= n; hash *= 1099511628211ull; }
    void step(unsigned frame, const uint16_t input[2], int delay, std::vector<uint8_t>& mem)
    {
        const int age = (int)(frame % 64);
        for (unsigned p = 0; p < 2; p++) {
            const auto before = mem;
            bool broken = false;
            {
                ThrowBreakWindowScope scope(mem.data(), 0, delay, ThrowBreakRule::paired_victim(-1, 1));
                broken = input[p] != previous[p] && accepts(mem, age, input[p]);
            }
            check(mem == before, "frame leaves no mutable endpoint state");
            if (broken) breaks[p]++;
            if (age == 16 + delay) throws[p]++;
            previous[p] = input[p];
            mix(p); mix(input[p]); mix(broken); mix(breaks[p]); mix(throws[p]);
        }
    }
};

static void timelines()
{
    constexpr unsigned frames = 1200;
    uint16_t input[frames][2] = {};
    for (unsigned f = 0; f < frames; f++) {
        input[f][0] = f % 13 == 0 ? 1 : f % 17 == 0 ? 2 : 0;
        input[f][1] = f % 11 == 0 ? 1 : f % 19 == 0 ? 2 : 0;
    }
    for (int delay : { 0, 1, 3, 8, 30 }) {
        auto mem = commands();
        std::vector<Game> reference(frames + 1);
        for (unsigned f = 0; f < frames; f++) {
            reference[f + 1] = reference[f]; reference[f + 1].step(f, input[f], delay, mem);
        }
        /* Each PC first predicts the other player's input, then restores a
         * boundary and re-simulates confirmed inputs. Rollback spans vary and
         * deliberately cross throw windows, as do the larger replay batches. */
        for (unsigned local = 0; local < 2; local++) {
            Game pc;
            for (unsigned first = 0; first < frames;) {
                const unsigned count = 1 + first % 23;
                const unsigned last = first + count < frames ? first + count : frames;
                const Game snapshot = pc;
                for (unsigned f = first; f < last; f++) {
                    uint16_t predicted[2] = { input[f][0], input[f][1] };
                    predicted[local ^ 1] = pc.previous[local ^ 1];
                    pc.step(f, predicted, delay, mem);
                }
                pc = snapshot;
                for (unsigned f = first; f < last; f++) {
                    pc.step(f, input[f], delay, mem);
                    check(pc.hash == reference[f + 1].hash, "both PCs' confirmed re-simulations equal lockstep");
                }
                first = last;
            }
        }
        Game replay;
        for (unsigned f = 0; f < frames; f++) {
            replay.step(f, input[f], delay, mem);
            check(replay.hash == reference[f + 1].hash, "recorded delay and inputs reproduce lockstep hashes");
        }
        check(mem == commands(), "session leaves original command table intact");
    }
    puts("two PCs, lockstep, rollback and replay ok");
}

int main()
{
    endpoints(); scope_guards(); timelines();
    printf("PASS %u checks\n", checks);
    return 0;
}
