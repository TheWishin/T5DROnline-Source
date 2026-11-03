/* Screen-side policy: no game/runtime, no guest memory. Build separately as C++17. */
#include <assert.h>
#include <initializer_list>
#include "../../src/netplay/always_left.h"

int main()
{
    using al::Side;
    assert(al::parse_side(nullptr, "1") == Side::Left);
    assert(al::parse_side(nullptr, "0") == Side::Dealt);
    assert(al::parse_side("dealt", "1") == Side::Dealt);
    assert(al::parse_side("", "1") == Side::Dealt);
    assert(al::parse_side("invalid", "1") == Side::Dealt);
    assert(al::parse_side("RIGHT", "1") == Side::Right);
    assert(al::parse_side("left", nullptr) == Side::Left);
    assert(al::mirrored_port(Side::Left) == 1);
    assert(al::mirrored_port(Side::Right) == 0);

    al::Frame f;
    f.enabled = true; f.casual = true; f.online_game = true;
    f.phase = al::kPhaseFight; f.game_type = al::kGtVersus;
    for (al::Net net : {al::Net::Host, al::Net::Join}) {
        f.net = net;
        for (Side side : {Side::Dealt, Side::Left, Side::Right}) {
            f.side = side;
            for (int slot = 0; slot < 2; ++slot) {
                f.local_slot = slot;
                const bool expected = side == Side::Left ? slot == 1 : side == Side::Right && slot == 0;
                assert(al::active(f) == expected);
                f.casual = false;
                assert(!al::active(f)); // Ranked, Quick and tournament sessions never mirror.
                f.casual = true;
                f.replaying = true;
                assert(!al::active(f));
                f.replaying = false;
                f.phase = 6;
                assert(!al::active(f));
                f.phase = al::kPhaseFight;
                f.game_type = al::kGtDemo;
                assert(!al::active(f));
                f.game_type = al::kGtVersus;
            }
        }
    }
    f.side = Side::Right; f.net = al::Net::Off;
    assert(!al::active(f)); // A persistent online game between matches never takes the offline preview rule.
    f.online_game = false;
    assert(al::active(f)); // Offline Versus preview uses P1 for Always right.
    f.enabled = false;
    assert(!al::active(f));
    for (unsigned b = 0; b < 65536; ++b)
        assert(al::swap_lr(al::swap_lr((uint16_t)b)) == b);
    for (unsigned x = 0; x < 256; ++x)
        assert(al::mirror_axis(al::mirror_axis((uint8_t)x)) == x);
}
