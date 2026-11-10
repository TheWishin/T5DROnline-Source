/*
 * The player's own Controller Setup online (docs/NETPLAY.md "The game's Controller Setup online").
 *
 * The game's OPTIONS > CONTROLLER SETUP (L2 R2 L1 R1 as LP, RP, LK, RK or a two-button shortcut; the four face
 * buttons) lives in the system save. An online game plays on a save of its own that both PCs start fresh
 * ("One save for online"): there every shoulder button is OFF, so a player's shortcuts did nothing online.
 * The setup cannot simply be loaded: the game applies P1's setup to P1's pad inside the simulation, and both
 * PCs must simulate the same.
 *
 * So it is applied where controls.ini is: to this PC's own sample, before it is exchanged. The player's setup
 * (P1's record of the offline save) turns the held buttons into the face buttons that mean the same under the
 * default setup both online games have. The other PC, replays and spectators see ordinary face buttons.
 *
 * SYS-DATA (0x218C0 bytes): P1's record at +0x11, P2's at +0x19, eight bytes each in the order
 * L2 R2 L1 R1 TRIANGLE CIRCLE CROSS SQUARE (the pad's own bit order), each a function:
 *   0 OFF  1 LP  2 RP  3 LK  4 RK  5 LP+RP  6 LK+RK  7 LP+LK  8 RP+RK  9 LP+RK  10 RP+LK
 * (read off the game's own setup screen for saves holding each value; above 10 the screen shows nothing: OFF
 * here). A fresh save: 0 0 0 0 2 4 3 1.
 *
 * The pure part (no runtime calls); tests/c/game_setup_test.cpp checks it.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace gs {

constexpr size_t kSaveSize = 0x218C0;        /* SYS-DATA's size */
constexpr size_t kOffP1 = 0x11, kOffP2 = 0x19;
constexpr int    kButtons = 8;
constexpr uint8_t kFnMax = 10;

/* netplay's 16-bit button word: DIGITAL1 low, DIGITAL2 high */
constexpr uint16_t kL2 = 0x0100, kR2 = 0x0200, kL1 = 0x0400, kR1 = 0x0800,
                   kTriangle = 0x1000, kCircle = 0x2000, kCross = 0x4000, kSquare = 0x8000;
constexpr uint16_t kFace = kTriangle | kCircle | kCross | kSquare;
constexpr uint16_t kBit[kButtons] = { kL2, kR2, kL1, kR1, kTriangle, kCircle, kCross, kSquare };

/* A function as the face buttons of the default setup: LP square, RP triangle, LK cross, RK circle. */
constexpr uint16_t kLP = kSquare, kRP = kTriangle, kLK = kCross, kRK = kCircle;
inline uint16_t fn_buttons(uint8_t fn)
{
    static const uint16_t k[kFnMax + 1] = {
        0, kLP, kRP, kLK, kRK,
        (uint16_t)(kLP | kRP), (uint16_t)(kLK | kRK), (uint16_t)(kLP | kLK), (uint16_t)(kRP | kRK),
        (uint16_t)(kLP | kRK), (uint16_t)(kRP | kLK),
    };
    return fn <= kFnMax ? k[fn] : 0;
}

struct Setup {
    uint8_t fn[kButtons] = { 0, 0, 0, 0, 2, 4, 3, 1 };   /* a fresh save's */

    /* Nothing to do: every shoulder OFF and the face buttons as they are. */
    bool is_default() const
    {
        for (int i = 0; i < kButtons; i++)
            if (fn_buttons(fn[i]) != (i < 4 ? 0 : kBit[i])) return false;
        return true;
    }
};

/* One player's record (side 0 = P1) of a SYS-DATA. False: not a SYS-DATA of this game (`s` stays default). */
inline bool from_save(const uint8_t* d, size_t n, int side, Setup& s)
{
    if (!d || n != kSaveSize || (side != 0 && side != 1)) return false;
    const uint8_t* r = d + (side ? kOffP2 : kOffP1);
    for (int i = 0; i < kButtons; i++) s.fn[i] = r[i];
    return true;
}

/* The buttons to send for the held ones: the face buttons become what the held shoulder and face buttons mean
 * in the player's setup; everything else (directions, START, SELECT, L3, R3 and the shoulder bits themselves,
 * which are OFF in the game that simulates them) stays. */
inline uint16_t apply(const Setup& s, uint16_t buttons)
{
    uint16_t face = 0;
    for (int i = 0; i < kButtons; i++)
        if (buttons & kBit[i]) face |= fn_buttons(s.fn[i]);
    return (uint16_t)((buttons & ~kFace) | face);
}

constexpr uint32_t kPhaseFight = 17;   /* 0x1008F070: the fight runs (round intros and the win pose included) */

/* Only an online match (host or join: the game then plays on the fresh online save; two players at one PC
 * and offline games apply the setup of the save they loaded themselves), only a fight (the game's menus read
 * the pad's own buttons whatever the setup says), never a replay. */
inline bool active(bool loaded, bool online, bool replaying, uint32_t phase)
{
    return loaded && online && !replaying && phase == kPhaseFight;
}

}  // namespace gs
