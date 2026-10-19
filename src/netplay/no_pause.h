/*
 * No pause online (docs/NETPLAY.md "No pause online") -- the rule on its own, without the game:
 * t5_hooks.cpp feeds it what the game state shows at a frame's boundary, tests/c/no_pause_test.cpp
 * feeds it made-up timelines (two PCs, rollbacks, replays) and checks that both PCs always give the
 * game the same inputs.
 *
 * START opens the game's pause menu in a VS fight. Online it is an input like any other, so either
 * player's START paused the fight in both games. The rule: in a direct-fight session START is taken
 * out of BOTH players' inputs of every frame, except in the post-match window -- from kDelay frames
 * after the match was decided in this fight until the game asks for the select screen -- where START
 * skips the KO replay and the win pose (the direct-fight driver presses it in lockstep, the rollback
 * loop's post-match rule sends it; both from 40 frames after the decision).
 *
 * What the rule does to frame f is a function of
 *   - the game state at the boundaries up to f's (record()), which is the same on both PCs while
 *     they are in sync, and
 *   - frame f's two inputs (apply()), which are the same on both PCs for every frame that counts
 *     (lockstep: exchanged before the frame runs; rollback: the confirmed inputs the final
 *     re-simulation runs with; replay: the file).
 * It never looks at which PC runs it, which slot is local or where an input came from, and it treats
 * both slots alike: apply(swap(in)) == swap(apply(in)). So both games give the game the same inputs
 * and stay equal, and a modified client that sends START anyway pauses nothing.
 *
 * record() keeps one entry per boundary (frame number mod kHist, tagged with the frame), so a
 * re-simulated boundary is recorded again from the restored state: an entry always comes from the
 * latest run of its frame. A rollback to first_wrong re-runs every boundary from first_wrong on, and
 * the boundaries before it ran on correct inputs, so the entry a boundary reads (its predecessor's)
 * is the final one. reset() at every frame 0 (a new session renumbers the frames).
 */
#pragma once
#include <stdint.h>
#include <string.h>

#include "netplay.h"

namespace np {

struct NoPauseRule {
    static constexpr uint16_t kStart = 0x0008;      /* START in PadInput::buttons (DIGITAL1 low byte) */
    static constexpr uint32_t kDelay = 40;          /* frames after the decision: the skip's first press */
    static constexpr uint32_t kHist = 4096;
    static constexpr uint32_t kModeSelect = 6;      /* the mode manager's select mode */

    /* What the game shows at a frame's boundary. */
    struct State {
        bool     game_mode;   /* the mode manager runs the game mode (4) */
        uint32_t phase;       /* fight phase word 0x1008F070 (17 = the fight, rounds and their KOs) */
        bool     decided;     /* 0x1008EBD5: the match is decided (stays set into the next fight's start) */
        uint32_t mode_next;   /* the mode the manager was asked for (6 = the select screen) */
    };

    uint32_t tag[kHist];      /* boundary f recorded: f + 1 */
    bool     fought[kHist];   /* boundary f: game mode, phase 17, match not decided */
    uint32_t since[kHist];    /* boundary f: the frame the match was decided at in this fight, 0 = not */

    NoPauseRule() { reset(); }
    void reset() { memset(tag, 0, sizeof tag); memset(fought, 0, sizeof fought); memset(since, 0, sizeof since); }

    /* Records frame f's boundary; true = START may reach the game in frame f (the post-match window).
     * The window opens only where the decided byte rises after a boundary that was fought -- not on
     * the last match's byte, which is still set when a rematch's fight begins. */
    bool record(uint32_t f, const State& st)
    {
        const bool fight = st.game_mode && st.phase == 17;
        const bool dec = fight && st.decided;
        uint32_t s = 0;
        if (dec && f > 0 && tag[(f - 1) % kHist] == f) {
            const uint32_t p = (f - 1) % kHist;
            s = since[p] ? since[p] : fought[p] ? f : 0;
        }
        const uint32_t i = f % kHist;
        tag[i] = f + 1;
        fought[i] = fight && !dec;
        since[i] = s;
        return s != 0 && f - s >= kDelay && st.mode_next != kModeSelect;
    }

    /* START out of both players' inputs unless allowed. Returns which players' START was taken out
     * (bit 0 = P1, bit 1 = P2). */
    static unsigned apply(bool allowed, PadInput in[2])
    {
        if (allowed) return 0;
        unsigned cut = 0;
        for (int p = 0; p < 2; p++)
            if (in[p].buttons & kStart) { in[p].buttons = (uint16_t)(in[p].buttons & ~kStart); cut |= 1u << p; }
        return cut;
    }
};

} // namespace np
