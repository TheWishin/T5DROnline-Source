/*
 * Unit test of the player's own Controller Setup online (src/netplay/game_setup.h; docs/NETPLAY.md "The game's
 * Controller Setup online"): the save's records, what each held button becomes, and when.
 *
 *   game_setup_test   prints "PASS <n> checks" (exit 0) or the failures (exit 1)
 *
 * Built by tests/test_game_setup.py with clang-cl.
 */
#include <stdio.h>
#include <string.h>
#include <vector>

#include "../../src/netplay/game_setup.h"

static int g_checks, g_fails;
#define CHECK(cond, ...)                                                        \
    do {                                                                        \
        g_checks++;                                                             \
        if (!(cond)) {                                                          \
            g_fails++;                                                          \
            printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); \
        }                                                                       \
    } while (0)

using namespace gs;

/* An independent model: the functions a setup gives the held buttons, as a set of LP RP LK RK. */
static unsigned fn_set(unsigned fn)
{
    enum { LP = 1, RP = 2, LK = 4, RK = 8 };
    switch (fn) {
    case 1: return LP; case 2: return RP; case 3: return LK; case 4: return RK;
    case 5: return LP | RP; case 6: return LK | RK; case 7: return LP | LK; case 8: return RP | RK;
    case 9: return LP | RK; case 10: return RP | LK;
    default: return 0;
    }
}
static unsigned functions(const Setup& s, unsigned buttons)
{
    static const unsigned bit[8] = { 0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000, 0x4000, 0x8000 };
    unsigned f = 0;
    for (int i = 0; i < 8; i++) if (buttons & bit[i]) f |= fn_set(s.fn[i]);
    return f;
}

int main()
{
    const Setup def;
    CHECK(def.is_default(), "a fresh save's setup is the default");
    for (unsigned b = 0; b < 0x10000; b++)
        if (apply(def, (uint16_t)b) != (uint16_t)b) { CHECK(false, "default setup changes 0x%04X", b); break; }
    g_checks++;

    /* the report: L1 R1 L2 R2 as shortcuts, which the fresh online save has OFF */
    Setup s;
    s.fn[0] = 5;  /* L2 = LP+RP */
    s.fn[1] = 6;  /* R2 = LK+RK */
    s.fn[2] = 9;  /* L1 = LP+RK */
    s.fn[3] = 2;  /* R1 = RP */
    CHECK(!s.is_default(), "a setup with shortcuts is not the default");
    CHECK(apply(s, kL2) == (kL2 | kSquare | kTriangle), "L2 -> square + triangle (got 0x%04X)", apply(s, kL2));
    CHECK(apply(s, kR2) == (kR2 | kCross | kCircle), "R2 -> cross + circle");
    CHECK(apply(s, kL1) == (kL1 | kSquare | kCircle), "L1 -> square + circle");
    CHECK(apply(s, kR1) == (kR1 | kTriangle), "R1 -> triangle");
    CHECK(apply(s, 0) == 0, "nothing held, nothing sent");
    CHECK(apply(s, 0x00F9) == 0x00F9, "directions, START and SELECT stay");
    CHECK(apply(s, 0x0006) == 0x0006, "L3 and R3 stay");
    CHECK(apply(s, kCross | 0x0040) == (kCross | 0x0040), "an unchanged face button stays");
    CHECK(apply(s, kL2 | kCross) == (kL2 | kSquare | kTriangle | kCross), "shortcut + face button");

    /* face buttons changed: the old meaning is gone, not added to */
    Setup f;
    f.fn[4] = 1; f.fn[7] = 2;      /* triangle = LP, square = RP */
    CHECK(!f.is_default(), "swapped face buttons are not the default");
    CHECK(apply(f, kTriangle) == kSquare, "triangle as LP -> square");
    CHECK(apply(f, kSquare) == kTriangle, "square as RP -> triangle");
    CHECK(apply(f, kTriangle | kSquare) == (kTriangle | kSquare), "both -> both");
    f.fn[5] = 0;                   /* circle off */
    CHECK(apply(f, kCircle) == 0, "a face button that is OFF sends nothing");
    f.fn[6] = 200;                 /* not a function: the game's screen shows nothing */
    CHECK(apply(f, kCross) == 0, "an unknown function is OFF");
    CHECK(fn_buttons(11) == 0 && fn_buttons(255) == 0, "functions above 10 are OFF");

    /* random setups, every held combination of the eight buttons: under the default setup the sent buttons
     * mean exactly what the held ones mean under the player's, and nothing but the face buttons changes */
    unsigned long long cases = 0;
    bool ok = true;
    for (unsigned seed = 0; seed < 4000 && ok; seed++) {
        Setup r;
        unsigned x = seed * 2654435761u + 12345u;
        for (int i = 0; i < 8; i++) { x = x * 1664525u + 1013904223u; r.fn[i] = (uint8_t)((x >> 24) % 12); }
        for (unsigned h = 0; h < 256 && ok; h++) {
            const unsigned held = h << 8 | (seed & 0xFF);
            const uint16_t sent = apply(r, (uint16_t)held);
            cases++;
            if (functions(def, sent) != functions(r, held) || ((sent ^ held) & ~kFace)) {
                CHECK(false, "seed %u held 0x%04X sent 0x%04X", seed, held, sent);
                ok = false;
            }
        }
    }
    g_checks++;

    /* the save */
    std::vector<uint8_t> d(kSaveSize, 0);
    const uint8_t p1[8] = { 2, 10, 1, 9, 2, 4, 3, 1 }, p2[8] = { 0, 0, 0, 0, 2, 4, 3, 1 };
    memcpy(&d[0x11], p1, 8);
    memcpy(&d[0x19], p2, 8);
    Setup a, b;
    CHECK(from_save(d.data(), d.size(), 0, a) && !memcmp(a.fn, p1, 8), "P1's record at +0x11");
    CHECK(from_save(d.data(), d.size(), 1, b) && !memcmp(b.fn, p2, 8) && b.is_default(), "P2's record at +0x19");
    CHECK(apply(a, kR2) == (kR2 | kTriangle | kCross), "R2 = RP+LK from the save");
    Setup c;
    CHECK(!from_save(d.data(), d.size() - 1, 0, c) && c.is_default(), "a file of another size is no save");
    CHECK(!from_save(nullptr, 0, 0, c) && c.is_default(), "no file is no save");
    CHECK(!from_save(d.data(), d.size(), 2, c), "there are two players");

    /* when */
    CHECK(active(true, true, false, kPhaseFight), "an online fight");
    CHECK(!active(false, true, false, kPhaseFight), "not without a setup");
    CHECK(!active(true, false, false, kPhaseFight), "not offline or with two players at one PC");
    CHECK(!active(true, true, true, kPhaseFight), "not in a replay");
    CHECK(!active(true, true, false, 16) && !active(true, true, false, 0), "not outside a fight");

    if (g_fails) { printf("FAILED %d of %d checks\n", g_fails, g_checks); return 1; }
    printf("PASS %d checks (%llu random cases)\n", g_checks, cases);
    return 0;
}
