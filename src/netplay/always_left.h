/*
 * "Always left" (1.1.9, casual matches; launcher "Always see me on the left", T5_ALWAYS_LEFT=1): the player the
 * game made P2 sees the fight as P1 sees it -- themselves on the left. Only this PC's picture and this PC's
 * controller change: the renderer mirrors the 3D picture and swaps the HUD's halves (ps3recomp patch 0086,
 * rsx_always_left.h), and this player's left and right are swapped before the input reaches the game or the
 * other PC, so "towards the opponent" stays the direction the player sees the opponent in. The game simulates
 * exactly what it did before; the other PC sees the normal picture. docs/NETPLAY.md "Always left".
 *
 * When (active()):
 *   - the option is on (this session's T5_ALWAYS_LEFT: a persistent game gets it with every match), and
 *   - a fight runs (the fight phase 17, round intros and the win pose included; not the attract demo), and
 *   - online (host or join, live): this PC plays P2 (local_slot 1) in a CASUAL match (the session's
 *     T5_NET_CASUAL=1, from the lobby's match_start: a challenge, a friend's invite, a room that is not ranked,
 *     their rematches). Ranked, the Quick queue and tournament sets never: there the sides stay the server's
 *     coin and the picture stays as it is (the owner's rule for 1.1.9);
 *     offline: a Versus fight (two players at one PC: the screen follows the P2 side -- for trying it alone
 *     with a second pad); the other offline modes stay as they are -- and never in a game started for online
 *     play (online_game), whatever its netplay state. A replay being watched: as recorded, not mirrored.
 *
 * The pure part (no runtime calls); tests/c/always_left_test.cpp checks it.
 */
#pragma once
#include <stdint.h>

namespace al {

/* CELL_PAD_CTRL_LEFT / _RIGHT in DIGITAL1, the low byte of netplay's 16-bit button word */
constexpr uint16_t kLeft = 0x0080, kRight = 0x0020;

constexpr uint32_t kPhaseFight = 17;   /* 0x1008F070: the fight runs (round intros included) */
constexpr uint32_t kGtDemo = 2, kGtVersus = 4;   /* 0x1008EBAC, the battle config's game type */

/* LEFT <-> RIGHT; every other button stays. */
inline uint16_t swap_lr(uint16_t b)
{
    const uint16_t l = (uint16_t)(b & kLeft), r = (uint16_t)(b & kRight);
    b = (uint16_t)(b & ~(kLeft | kRight));
    if (l) b |= kRight;
    if (r) b |= kLeft;
    return b;
}

/* A stick axis mirrored: 0 (full left) <-> 255 (full right), the centre (128) to 127 -- inside every dead
 * zone, as the pad layer's own rounding is. */
inline uint8_t mirror_axis(uint8_t v) { return (uint8_t)(255u - v); }

enum class Net { Off, Local, Host, Join };

struct Frame {
    bool     enabled = false;      /* T5_ALWAYS_LEFT=1 (this session's value) */
    bool     casual = false;       /* online: T5_NET_CASUAL=1, a casual match (this session's value) */
    bool     online_game = false;  /* the game was started for online play (T5_CTL_DIR, T5_NET_MODE host/join) */
    Net      net = Net::Off;
    bool     replaying = false;    /* a replay being watched */
    int      local_slot = 0;       /* online: 0 = P1, 1 = P2 */
    uint32_t phase = 0;            /* 0x1008F070 */
    uint32_t game_type = 0;        /* 0x1008EBAC */
};

inline bool active(const Frame& f)
{
    if (!f.enabled || f.replaying) return false;
    if (f.phase != kPhaseFight || f.game_type == kGtDemo) return false;
    if (f.net == Net::Host || f.net == Net::Join) return f.local_slot == 1 && f.casual;
    if (f.online_game) return false;
    return f.game_type == kGtVersus;
}

/* T5_ALWAYS_LEFT: "1" (or "on", "true", "yes") = on; anything else, or unset, = off. */
inline bool parse_enabled(const char* v)
{
    if (!v) return false;
    auto eq = [](const char* a, const char* b) {
        for (; *a && *b; a++, b++) {
            char c = *a;
            if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
            if (c != *b) return false;
        }
        return *a == 0 && *b == 0;
    };
    return eq(v, "1") || eq(v, "on") || eq(v, "true") || eq(v, "yes");
}

}  // namespace al
