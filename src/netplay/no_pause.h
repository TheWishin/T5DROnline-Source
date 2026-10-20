/*
 * No pause online (docs/NETPLAY.md "No pause online") and the skips by both players' START
 * (docs/NETPLAY.md "Skipping intros and replays online") -- the rule on its own, without the game:
 * t5_hooks.cpp feeds it what the game state shows at a frame's boundary, tests/c/no_pause_test.cpp
 * feeds it made-up timelines (two PCs, rollbacks, replays) and checks that both PCs always give the
 * game the same inputs.
 *
 * START opens the game's pause menu in a VS fight. Online it is an input like any other, so either
 * player's START paused the fight in both games. The rule: in a direct-fight session START is taken
 * out of BOTH players' inputs of every frame, except where START does not pause but skips:
 *   - the skip parts: the fighters' intros before round 1 (round states 1 and 2), and after a round
 *     that did not decide the match its KO slow motion, replay and the way to the next round (8, 9,
 *     0xC). Each player's START counts from the frame it is seen in that frame's inputs until the
 *     part ends (the presses need not overlap; holding counts once). While only one player has
 *     pressed, START is taken out of both inputs as everywhere else. From the frame both have, the
 *     rule itself presses START for both players: 3 frames, then again every 20 frames until the
 *     part is over -- the game skips the P1 intro, the P2 intro, the replay and the way to the next
 *     round one press each (offline any press of the player whose intro runs, of either player in
 *     the replay). The players' own START does not reach the game there either.
 *   - the post-match window -- from kDelay frames after the match was decided in this fight until
 *     the game asks for the select screen -- where START skips the last KO replay and the win pose
 *     (the direct-fight driver presses it in lockstep, the rollback loop's post-match rule sends it;
 *     both from 40 frames after the decision). START is kept there as it comes.
 *
 * What the rule does to frame f is a function of
 *   - the game state at the boundaries up to f's (record()), which is the same on both PCs while
 *     they are in sync, and
 *   - the inputs of the frames up to f (record()), which are the same on both PCs for every frame
 *     that counts (lockstep: exchanged before the frame runs; rollback: the confirmed inputs the
 *     final re-simulation runs with; replay: the file).
 * It never looks at which PC runs it, which slot is local or where an input came from, and it treats
 * both slots alike: apply(swap(in)) == swap(apply(in)), and the presses are kept per slot the same
 * way. So both games give the game the same inputs and stay equal, and a modified client that sends
 * START anyway pauses nothing and skips nothing on its own.
 *
 * record() keeps one entry per boundary (frame number mod kHist, tagged with the frame), so a
 * re-simulated boundary is recorded again from the restored state and the frame's (now confirmed)
 * inputs: an entry always comes from the latest run of its frame. A rollback to first_wrong re-runs
 * every boundary from first_wrong on, and the boundaries before it ran on correct inputs, so the
 * entry a boundary reads (its predecessor's) is the final one. reset() at every frame 0 (a new
 * session renumbers the frames).
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
    static constexpr uint32_t kReplay = 9;          /* round state: the replay after a round's KO */
    /* The skip parts by round state (bit n = state n; probes in build/skip114, docs/NETPLAY.md):
     * 1 the P1 fighter's intro, 2 the P2 fighter's intro (before round 1); 8 the KO's slow motion
     * (START does nothing there, a press counts), 9 the replay, 0xC the way to the next round. START
     * does nothing in READY/FIGHT (4) and pauses the fight (5). */
    static constexpr uint32_t kIntroRounds = (1u << 1) | (1u << 2);
    static constexpr uint32_t kAfterRounds = (1u << 8) | (1u << kReplay) | (1u << 0xC);
    static constexpr uint32_t kPressFrames = 3, kPressEvery = 20;   /* the rule's own presses once both have */
    enum Part : uint8_t { kNone = 0, kIntro = 1, kAfter = 2 };

    /* What the game shows at a frame's boundary. */
    struct State {
        bool     game_mode;   /* the mode manager runs the game mode (4) */
        uint32_t phase;       /* fight phase word 0x1008F070 (17 = the fight, rounds and their KOs) */
        bool     decided;     /* 0x1008EBD5: the match is decided (stays set into the next fight's start) */
        uint32_t mode_next;   /* the mode the manager was asked for (6 = the select screen) */
        uint32_t round;       /* round state u32 0x1009322C: 1, 2 the fighters' intros before round 1, 4 READY/FIGHT,
                               * 5 fighting, 6 the KO frame, 8 KO slow motion, 9 the replay, 0xC on to the next round */
    };

    /* What START does in a frame (record()'s answer, apply()'s argument). */
    enum Verdict : uint8_t {
        kCut   = 0,   /* taken out of both inputs */
        kKeep  = 1,   /* kept as it comes (the post-match window) */
        kPress = 2,   /* both players have pressed in this skip part: START in both inputs (the rule's press) */
    };

    uint32_t tag[kHist];      /* boundary f recorded: f + 1 */
    bool     fought[kHist];   /* boundary f: game mode, phase 17, match not decided */
    uint32_t since[kHist];    /* boundary f: the frame the match was decided at in this fight, 0 = not */
    uint8_t  part[kHist];     /* boundary f: the skip part it is in (Part) */
    uint8_t  pressed[kHist];  /* boundary f: who has pressed START in this part, frame f's inputs included
                               * (bit 0 = P1, bit 1 = P2) */
    uint32_t both[kHist];     /* boundary f: the frame both had pressed at, + 1 (0 = not yet) */

    NoPauseRule() { reset(); }
    void reset()
    {
        memset(tag, 0, sizeof tag); memset(fought, 0, sizeof fought); memset(since, 0, sizeof since);
        memset(part, 0, sizeof part); memset(pressed, 0, sizeof pressed); memset(both, 0, sizeof both);
    }

    /* The skip part a boundary's round state belongs to (the match not yet decided in this fight;
     * t5_hooks.cpp asks it at the live boundary as well: this PC's START goes out only there). */
    static Part part_of(const State& st)
    {
        if (!st.game_mode || st.phase != 17 || st.round >= 32 || st.mode_next == kModeSelect) return kNone;
        if ((kIntroRounds >> st.round) & 1) return kIntro;
        if ((kAfterRounds >> st.round) & 1) return kAfter;
        return kNone;
    }
    static unsigned start_bits(const PadInput in[2])
    {
        return ((in[0].buttons & kStart) ? 1u : 0u) | ((in[1].buttons & kStart) ? 2u : 0u);
    }

    /* Records frame f's boundary and frame f's inputs (as exchanged, before apply()); the answer says
     * what START does in frame f. The post-match window opens only where the decided byte rises after
     * a boundary that was fought -- not on the last match's byte, which is still set when a rematch's
     * fight begins; the round's own skip parts end where the match is decided. */
    Verdict record(uint32_t f, const State& st, const PadInput in[2])
    {
        const bool fight = st.game_mode && st.phase == 17;
        const bool dec = fight && st.decided;
        const bool prev_ok = f > 0 && tag[(f - 1) % kHist] == f;
        const uint32_t p = (f - 1) % kHist;
        uint32_t s = 0;
        if (dec && prev_ok) s = since[p] ? since[p] : fought[p] ? f : 0;
        const bool window = s != 0 && f - s >= kDelay && st.mode_next != kModeSelect;
        const Part pt = s ? kNone : part_of(st);
        uint8_t pr = 0;
        uint32_t b = 0;
        if (pt != kNone) {
            const bool same = prev_ok && part[p] == pt;
            pr = (uint8_t)((same ? pressed[p] : 0) | start_bits(in));
            b = same && both[p] ? both[p] : pr == 3 ? f + 1 : 0;
        }
        const uint32_t i = f % kHist;
        tag[i] = f + 1;
        fought[i] = fight && !dec;
        since[i] = s;
        part[i] = (uint8_t)pt;
        pressed[i] = pr;
        both[i] = b;
        if (window) return kKeep;
        return b && (f + 1 - b) % kPressEvery < kPressFrames ? kPress : kCut;
    }

    /* Who has pressed START in the skip part at boundary f (bit 0 = P1, bit 1 = P2; 0 when f is not in
     * one or was not recorded), and the part. */
    unsigned pressed_at(uint32_t f) const { const uint32_t i = f % kHist; return tag[i] == f + 1 ? pressed[i] : 0; }
    Part part_at(uint32_t f) const { const uint32_t i = f % kHist; return tag[i] == f + 1 ? (Part)part[i] : kNone; }

    /* START in both players' inputs as the verdict says. Returns which players' START was taken out
     * (bit 0 = P1, bit 1 = P2). */
    static unsigned apply(Verdict v, PadInput in[2])
    {
        if (v == kKeep) return 0;
        const unsigned had = start_bits(in);
        for (int p = 0; p < 2; p++)
            in[p].buttons = (uint16_t)(v == kPress ? in[p].buttons | kStart : in[p].buttons & ~kStart);
        return v == kPress ? 0 : had;
    }
};

} // namespace np
