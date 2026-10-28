/*
 * Unit test of "Always left" in the game layer (src/netplay/always_left.h; docs/NETPLAY.md "Always left"):
 * when this PC shows the fight mirrored, and what the player's left/right become.
 *
 *   always_left_test   prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * Built by tests/test_always_left.py with clang-cl.
 */
#include <stdio.h>

#include "../../src/netplay/always_left.h"

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); \
        }                                                                       \
    } while (0)

int main()
{
    /* left <-> right, nothing else */
    CHECK(al::swap_lr(0x0080) == 0x0020, "LEFT -> RIGHT");
    CHECK(al::swap_lr(0x0020) == 0x0080, "RIGHT -> LEFT");
    CHECK(al::swap_lr(0x00A0) == 0x00A0, "both stay both");
    CHECK(al::swap_lr(0x0010 | 0x0040) == (0x0010 | 0x0040), "UP and DOWN stay");
    CHECK(al::swap_lr(0x4000 | 0x0080 | 0x0010) == (0x4000 | 0x0020 | 0x0010), "CROSS + UP-LEFT -> CROSS + UP-RIGHT");
    for (unsigned b = 0; b < 0x10000; b++) {
        const uint16_t s = al::swap_lr((uint16_t)b);
        if (al::swap_lr(s) != (uint16_t)b || (s & ~0x00A0) != (b & ~0x00A0u)) {
            CHECK(false, "swap_lr(0x%04X) = 0x%04X", b, s);
            break;
        }
    }
    g_checks++;
    CHECK(al::mirror_axis(0) == 255 && al::mirror_axis(255) == 0, "full left <-> full right");
    CHECK(al::mirror_axis(128) == 127 && al::mirror_axis(127) == 128, "the centre stays in the centre");
    CHECK(al::mirror_axis(40) == 215, "a part tilt mirrors");

    /* when */
    al::Frame f;
    f.enabled = true; f.net = al::Net::Join; f.local_slot = 1; f.phase = 17; f.game_type = 4;
    CHECK(al::active(f), "online P2 in a fight");
    f.local_slot = 0;
    CHECK(!al::active(f), "online P1: normal");
    f.local_slot = 1; f.net = al::Net::Host;
    CHECK(al::active(f), "the host as P2 (a side chosen in the lobby)");
    f.enabled = false;
    CHECK(!al::active(f), "the option off: never");
    f.enabled = true; f.phase = 6;
    CHECK(!al::active(f), "not in a fight (character select): normal");
    f.phase = 17; f.replaying = true;
    CHECK(!al::active(f), "a replay being watched: as recorded");
    f.replaying = false; f.game_type = 2;
    CHECK(!al::active(f), "the attract demo: never");
    f.net = al::Net::Off; f.game_type = 4;
    CHECK(al::active(f), "offline Versus: the P2 side's view");
    f.game_type = 0;
    CHECK(!al::active(f), "offline Arcade: normal");
    f.game_type = 10;
    CHECK(!al::active(f), "offline Practice: normal");
    f.net = al::Net::Local; f.game_type = 4;
    CHECK(al::active(f), "two players at one PC (netplay local mode), Versus: as offline");

    CHECK(al::parse_enabled("1") && al::parse_enabled("on") && al::parse_enabled("TRUE") && al::parse_enabled("yes"),
          "1/on/true/yes");
    CHECK(!al::parse_enabled(nullptr) && !al::parse_enabled("") && !al::parse_enabled("0") &&
          !al::parse_enabled("off") && !al::parse_enabled("10"), "unset/empty/0/off/10");

    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks\n", g_checks);
    return 0;
}
