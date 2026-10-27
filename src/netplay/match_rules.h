/*
 * Match rules that change what the game simulates online (docs/NETPLAY.md "Online training and the health
 * handicap"): a training fight (endless health, no round timer, hold SELECT to give up) and each player's health
 * handicap (life %). The rule on its own, without the game: t5_hooks.cpp feeds it what the fighter blocks show at a
 * frame's boundary and writes back what it says; tests/c/match_rules_test.cpp feeds it made-up timelines (two PCs,
 * rollbacks, replays) and checks that both PCs always end up with the same game state.
 *
 * Where the rules come from: the direct-fight line (`train=1`, `life=<P1>|<P2>`), which the lobby gives both
 * launchers in match_start and a replay keeps per match (format 5). Both PCs (and every replay or spectator of the
 * match) read the same line, the driver latches the rules at FIGHT START (before t5_netplay_start()), and they
 * stay fixed for the whole fight.
 *
 * The health handicap is the game's own: the battle config holds each side's life percent (0x1008EBF4 P1,
 * 0x1008EBF8 P2, u32, 100 after the select screen's handicap bar), which the game mode's set-up turns into the
 * fighters' maximum health (fighter block +0x6C0, 16.16 fixed point: 145.0 at 100 %, 72.5 at 50 %) and their
 * health at every round start (+0x6BC). The driver writes both words at the game mode's first frame, before that
 * set-up runs (docs/DIRECTFIGHT.md "How the game is driven"), the same values on both PCs; the HUD's health bars
 * show the shorter maximum as an empty part (build/int115 probes p2, p5).
 *
 * The training rule, per frame f, with the game state at f's boundary (live, re-simulated and played-back frames
 * alike, after the inputs are final for that run):
 *   - only while the round is fought (round state 5, the match not decided);
 *   - the round timer (0x1008F054, frames) is held at 60 s: no time-out;
 *   - a fighter's health refills to its maximum once it has taken no damage for kRefillFrames frames (one second
 *     after the last hit of a combo, whether the fighter stands, blocks or lies on the ground); a stream of hits
 *     keeps it down, as in a real fight;
 *   - a player who holds SELECT for kGiveUpFrames frames gives up: their health goes to 0 and the game KOs them
 *     in the next frame (probe p6), which ends the training fight (1 round) like any match: both games go back to
 *     the select screen, the lobby records nothing.
 * The counters behind the last two (health and frames without damage, frames SELECT held) live here, one entry per
 * frame (frame
 * number mod kHist, tagged with the frame), each computed from its predecessor's entry -- the same scheme as the
 * no-pause rule (no_pause.h): a re-simulated boundary is computed again from the restored state and the frame's
 * final inputs, and the boundaries before a rollback's first wrong frame ran with the right inputs, so the entry a
 * boundary reads is the final one. A sync point (scene barrier) renumbers frames differently on the two PCs (the
 * side that got there first skips frame numbers), so the history is cleared at every sync point and at frame 0 of
 * a session, on both PCs alike. The rule never looks at which PC runs it or which slot is local, and it treats both
 * slots alike.
 */
#pragma once
#include <stdint.h>
#include <string.h>

#include "netplay.h"

namespace np {

struct MatchRules {
    static constexpr int kLifeMin = 10, kLifeMax = 100;
    bool training = false;
    int life[2] = { 100, 100 };

    static int clamp_life(int v) { return v < kLifeMin ? kLifeMin : v > kLifeMax ? kLifeMax : v; }
    bool any() const { return training || life[0] != 100 || life[1] != 100; }
    /* bit 0 training, bits 8-15 P1's life %, bits 16-23 P2's (a replay's per-match word); 0 = no rules (a match
     * as before 1.1.5, and what older replay files read as) */
    uint32_t pack() const
    {
        if (!any()) return 0;
        return (training ? 1u : 0u) | (uint32_t)clamp_life(life[0]) << 8 | (uint32_t)clamp_life(life[1]) << 16;
    }
    static MatchRules unpack(uint32_t w)
    {
        MatchRules r;
        r.training = (w & 1) != 0;
        const int a = (int)(w >> 8 & 0xFF), b = (int)(w >> 16 & 0xFF);
        r.life[0] = a ? clamp_life(a) : 100;
        r.life[1] = b ? clamp_life(b) : 100;
        return r;
    }
    bool operator==(const MatchRules& o) const
    {
        return training == o.training && life[0] == o.life[0] && life[1] == o.life[1];
    }
    bool operator!=(const MatchRules& o) const { return !(*this == o); }
};

struct TrainingRule {
    static constexpr uint32_t kHist = 4096;
    static constexpr uint16_t kSelect = 0x0001;      /* SELECT in PadInput::buttons (DIGITAL1 low byte) */
    static constexpr uint32_t kGiveUpFrames = 60;    /* SELECT held this long: that player gives up */
    static constexpr uint32_t kRefillFrames = 60;    /* no damage this long: health back to the maximum */
    static constexpr uint32_t kRoundTimer = 60 * 60; /* the round timer held at 60 s (frames) */

    struct Fighter {
        int32_t hp = 0, max = 0;   /* 16.16 fixed point, as in the fighter block */
    };
    struct State {
        bool fighting = false;     /* round state 5, the match not decided */
        Fighter f[2];
    };
    struct Action {
        bool set_hp[2] = { false, false };
        int32_t hp[2] = { 0, 0 };
        bool hold_timer = false;
        bool gave_up[2] = { false, false };     /* (for the log: this frame's give-up) */
        bool refilled[2] = { false, false };
    };

    uint32_t tag[kHist];               /* frame + 1 of the entry (0 = empty) */
    uint16_t held[2][kHist];           /* frames SELECT has been held up to and including this frame */
    uint16_t quiet[2][kHist];          /* frames without damage (health not lower than at the boundary before) */
    int32_t  hp[2][kHist];             /* the fighter's health after this boundary (the rule's own write included) */

    TrainingRule() { reset(); }
    void reset()
    {
        memset(tag, 0, sizeof tag); memset(held, 0, sizeof held); memset(quiet, 0, sizeof quiet); memset(hp, 0, sizeof hp);
    }

    Action step(uint32_t f, const State& s, const PadInput in[2])
    {
        Action a;
        const uint32_t i = f % kHist, j = (f + kHist - 1) % kHist;
        const bool prev = f > 0 && tag[j] == f;   /* the entry of frame f - 1 (tag = frame + 1) */
        tag[i] = f + 1;
        for (int p = 0; p < 2; p++) {
            hp[p][i] = s.f[p].hp;
            if (!s.fighting) { held[p][i] = quiet[p][i] = 0; continue; }
            const uint16_t h0 = prev ? held[p][j] : 0, q0 = prev ? quiet[p][j] : 0;
            held[p][i] = (in[p].buttons & kSelect) ? (uint16_t)(h0 < 0xFFFF ? h0 + 1 : h0) : 0;
            const bool hurt = prev && s.f[p].hp < hp[p][j];
            quiet[p][i] = hurt ? 0 : (uint16_t)(q0 < 0xFFFF ? q0 + 1 : q0);
        }
        if (!s.fighting) return a;
        a.hold_timer = true;
        for (int p = 0; p < 2; p++) {
            if (held[p][i] >= kGiveUpFrames) {
                if (s.f[p].hp != 0) { a.set_hp[p] = true; a.hp[p] = 0; a.gave_up[p] = held[p][i] == kGiveUpFrames; }
            } else if (quiet[p][i] >= kRefillFrames && s.f[p].max > 0 && s.f[p].hp < s.f[p].max) {
                a.set_hp[p] = true;
                a.hp[p] = s.f[p].max;
                a.refilled[p] = true;
            }
            if (a.set_hp[p]) hp[p][i] = a.hp[p];   /* (a hit in the same frame then still counts as damage) */
        }
        return a;
    }
};

} // namespace np
