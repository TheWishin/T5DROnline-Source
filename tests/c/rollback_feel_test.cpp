/* Online feel policy (src/netplay/rollback_feel.h): pure checks, no game, sockets or guest memory. */
#include "../../src/netplay/rollback_feel.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <limits>

using namespace np::feel;

static int checks = 0;
#define CHECK(x) do { assert(x); ++checks; } while (0)

int main()
{
    /* capacity: (15 ms - live - restore) / resim, 0..15, unknown without a re-simulated frame time */
    CHECK(capacity(5.0, 0.6, 1.86) == 5);          /* this dev PC in a fight: 9.4 / 1.86 */
    CHECK(capacity(12.0, 1.0, 4.0) == 0);          /* a weak PC: 2 ms left, a resim frame costs 4 */
    CHECK(capacity(14.0, 2.0, 1.0) == 0);          /* nothing left */
    CHECK(capacity(1.0, 0.1, 0.1) == 15);          /* capped */
    CHECK(capacity(5.0, 0.6, 0.0) == kCapUnknown);
    CHECK(capacity(std::numeric_limits<double>::quiet_NaN(), 0.6, 1.0) == kCapUnknown);
    CHECK(capacity(-1.0, 0.6, 1.0) == kCapUnknown);

    /* in flight: ceil(rtt / 33.37 ms) + 1 */
    CHECK(in_flight(0) == 1);
    CHECK(in_flight(30) == 2);
    CHECK(in_flight(150) == 6);
    CHECK(in_flight(186) == 7);
    CHECK(in_flight(-1) == -1);
    CHECK(expected_depth(150, 2) == 4);
    CHECK(expected_depth(0, 1) == 0);
    CHECK(expected_depth(30, 5) == 0);

    /* combine */
    CHECK(combine(kSmooth, kSmooth) == kSmooth);
    CHECK(combine(kResponsive, kResponsive) == kResponsive);
    CHECK(combine(kResponsive, kSmooth) == kBalanced);
    CHECK(combine(kSmooth, kUnknown) == kSmooth);   /* an older peer sends nothing: this player's choice */
    CHECK(combine(kUnknown, kUnknown) == kBalanced);
    CHECK(parse("smooth") == kSmooth && parse("Responsive") == kResponsive && parse("") == kBalanced &&
          parse(nullptr) == kBalanced && parse("x") == kBalanced);
    CHECK(slower(5, kCapUnknown) == 5 && slower(kCapUnknown, kCapUnknown) == kCapUnknown && slower(2, 7) == 2);

    /* decide: responsive never adds */
    CHECK(decide(2, 150, 6, kResponsive, 0).delay == 2);
    /* balanced: both PCs keep up -> the base pick */
    CHECK(decide(2, 150, 6, kBalanced, 5).delay == 2);
    /* balanced: the slower PC cannot hide depth 4 -> one frame, never more */
    { const Pick p = decide(2, 150, 6, kBalanced, 3); CHECK(p.delay == 3 && p.extra == 1 && p.depth == 3); }
    CHECK(decide(2, 150, 6, kBalanced, 0).delay == 3);
    /* balanced without any measurement: the base pick (an old peer and a fresh install) */
    CHECK(decide(2, 150, 6, kBalanced, kCapUnknown).delay == 2);
    /* never above the session's lockstep delay */
    CHECK(decide(2, 150, 2, kBalanced, 0).delay == 2);
    CHECK(decide(1, 30, 3, kBalanced, 0).delay == 2);   /* a weak PC on a near connection */
    /* no round trip: the base pick */
    CHECK(decide(2, -1, 6, kSmooth, 0).delay == 2);
    /* smooth: at most two frames predicted, at most two more than the base */
    CHECK(decide(2, 150, 8, kSmooth, kCapUnknown).delay == 4);   /* 6 in flight - 2 */
    CHECK(decide(1, 30, 8, kSmooth, kCapUnknown).delay == 1);    /* 2 in flight: nothing to add */
    CHECK(decide(2, 300, 8, kSmooth, kCapUnknown).delay == 4);   /* 10 in flight - 2 = 8, capped at base + 2 */
    /* smooth + the capacity frame */
    { const Pick p = decide(2, 300, 8, kSmooth, 2); CHECK(p.delay == 5 && p.extra == 3); }
    CHECK(decide(2, 300, 4, kSmooth, 2).delay == 4);              /* ceiling */
    /* never below the base */
    CHECK(decide(3, 30, 2, kBalanced, 0).delay == 3);
    /* one frame by measured cost: only with both PCs measured, only Responsive / Balanced, only where the slower
     * PC re-simulates the 99th-percentile depth of one frame of delay (ceil(rtt / 33.4) + 1 <= cap, at most 6) */
    CHECK(p99_depth_one_frame(60) == 3 && p99_depth_one_frame(100) == 4 && p99_depth_one_frame(120) == 5 &&
          p99_depth_one_frame(150) == 6 && p99_depth_one_frame(-1) == -1);   /* as measured */
    CHECK(decide(2, 100, 6, kBalanced, 4, true).delay == 1);      /* p99 depth 4 <= capacity 4 */
    { const Pick p = decide(2, 100, 6, kBalanced, 4, true); CHECK(p.extra == -1 && p.depth == 3); }
    CHECK(decide(2, 101, 6, kBalanced, 4, true).delay == 2);      /* p99 depth 5 > 4: the 1.2.0 pick */
    CHECK(decide(2, 100, 6, kBalanced, 3, true).delay == 2);      /* this dev PC at 100 ms: measured not to hold */
    CHECK(decide(2, 66, 6, kBalanced, 3, true).delay == 1);       /* ... and where it does */
    CHECK(decide(2, 100, 6, kBalanced, 4, false).delay == 2);     /* one PC not measured: as before */
    CHECK(decide(2, 100, 6, kBalanced, 4).delay == 2);            /* the old call: as before */
    CHECK(decide(2, 100, 6, kBalanced, kCapUnknown, true).delay == 2);
    CHECK(decide(2, 150, 6, kBalanced, 6, true).delay == 1);      /* p99 depth 6, the deepest the rule plans with */
    CHECK(decide(2, 150, 6, kBalanced, 5, true).delay == 2);
    CHECK(decide(2, 150, 6, kBalanced, 3, true).delay == 3);      /* and the slower PC's frame, as before */
    CHECK(decide(2, 170, 6, kBalanced, 15, true).delay == 2);     /* p99 depth 7: never planned, whatever the capacity */
    CHECK(decide(2, 100, 6, kResponsive, 4, true).delay == 1);
    CHECK(decide(2, 100, 6, kResponsive, 2, true).delay == 2);    /* responsive still never adds */
    CHECK(decide(2, 100, 6, kSmooth, 9, true).delay == 2);        /* smooth: in flight 4 - 2, untouched */
    CHECK(decide(1, 50, 6, kBalanced, 2, true).delay == 1);       /* base 1 stays 1 */
    CHECK(decide(1, 50, 6, kBalanced, 1, true).delay == 2);       /* ... and its capacity frame as before */
    CHECK(decide(2, 100, 0, kBalanced, 4, true).delay == 1);      /* the caller clamps to the lockstep delay */
    CHECK(decide(2, -1, 6, kBalanced, 9, true).delay == 2);       /* no round trip */
    CHECK(one_frame_up_to_ms(kCapUnknown) < 0 && one_frame_up_to_ms(0) == 0 && one_frame_up_to_ms(1) == 0);
    CHECK(std::fabs(one_frame_up_to_ms(3) - 66.7) < 0.1 && std::fabs(one_frame_up_to_ms(9) - 166.8) < 0.1);
    /* the table agrees with decide() at every ping and capacity */
    for (int cap = 0; cap <= 15; cap++)
        for (int rtt = 61; rtt <= 400; rtt++) {
            const bool one = decide(2, rtt, 8, kBalanced, (uint8_t)cap, true).delay == 1;
            CHECK(one == (rtt <= one_frame_up_to_ms((uint8_t)cap) + 1e-6));
        }
    printf("PASS %d checks\n", checks);
    return 0;
}
