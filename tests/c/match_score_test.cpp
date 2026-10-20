/*
 * A decided match's score (src/netplay/match_score.h) on its own, for tests/test_match_score.py.
 *
 * The values are the game's, watched frame by frame in rollback pairs (first to 3, rematches): the
 * fighters' round counts at the frame the decided byte rises, the winner byte, the rounds to win.
 *   seen        3-2, 3-1, 0-3, 3-0 read as they are (1.1.2 made 3-2 and 3-1 into 3-0)
 *   draws       the decided byte 3, equal counts: no winner, whatever the winner byte says (0)
 *   fallback    counts that cannot be the match's (both 0, above the rounds to win, naming another
 *               verdict than the decided byte's): the decided byte with rounds-to-win : 0, `counted` false
 *   session     a persistent game's matches in a row, the way the hooks read them: the decided byte of
 *               the last match still up into the next fight with its counts, until the game mode's
 *               start clears both -- every match gets its own score, the stale one is never read
 * "PASS <n> checks" at the end, exit code 1 on the first failure.
 */
#include <stdio.h>
#include <stdlib.h>

#include "../../src/netplay/match_score.h"

static int g_checks = 0;
#define CHECK(c) do { g_checks++; if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)

static void expect(uint8_t w1, uint8_t w2, uint8_t decided, uint8_t win, uint8_t rounds, unsigned p1, unsigned p2,
                   int winner, bool counted)
{
    const np::MatchScore s = np::MatchScore::of(w1, w2, decided, win, rounds);
    if (s.p1 != p1 || s.p2 != p2 || s.winner() != winner || s.counted != counted)
        printf("of(%u, %u, decided %u, winner byte %u, rounds %u) = %u-%u winner %d counted %d; expected %u-%u winner %d "
               "counted %d\n", w1, w2, decided, win, rounds, s.p1, s.p2, s.winner(), s.counted, p1, p2, winner, counted);
    CHECK(s.p1 == p1 && s.p2 == p2 && s.winner() == winner && s.counted == counted);
}

int main()
{
    /* seen: the rollback pairs' matches (decided byte 1 = P1, 2 = P2; the winner byte with it) */
    expect(3, 2, 1, 0, 3, 3, 2, 0, true);
    expect(3, 1, 1, 0, 3, 3, 1, 0, true);
    expect(0, 3, 2, 1, 3, 0, 3, 1, true);
    expect(3, 0, 1, 0, 3, 3, 0, 0, true);
    expect(2, 3, 2, 1, 3, 2, 3, 1, true);
    expect(1, 0, 1, 0, 1, 1, 0, 0, true);        /* first to 1 */
    expect(5, 4, 1, 0, 5, 5, 4, 0, true);        /* first to 5 */
    printf("seen ok\n");

    /* draws: decided byte 3, the winner byte 0 (seen: a no-input pair, first to 1, ended 1-1 by time-out) --
     * no winner; 1.1.2 made it P1's 1-0 */
    expect(1, 1, 3, 0, 1, 1, 1, -1, true);
    expect(3, 3, 3, 0, 3, 3, 3, -1, true);
    expect(3, 2, 1, 0, 3, 3, 2, 0, true);        /* a drawn round at 2-1 counts for both: P1 at 3 wins */
    expect(0, 0, 3, 0, 3, 3, 3, -1, false);      /* a draw without counts: rounds-to-win each, no winner */
    printf("draws ok\n");

    /* fallback: the decided byte, rounds-to-win : 0, as before 1.1.3 */
    expect(0, 0, 2, 1, 3, 0, 3, 1, false);       /* no counts at all */
    expect(0, 0, 1, 0, 3, 3, 0, 0, false);
    expect(4, 1, 1, 0, 3, 3, 0, 0, false);       /* above the rounds to win */
    expect(0xFF, 0, 2, 1, 3, 0, 3, 1, false);
    expect(3, 1, 2, 1, 3, 0, 3, 1, false);       /* the counts name P1, the game P2 */
    expect(1, 3, 1, 0, 3, 3, 0, 0, false);
    expect(2, 2, 1, 0, 3, 3, 0, 0, false);       /* the counts a draw, the game P1 */
    expect(1, 0, 1, 0, 0, 1, 0, 0, true);        /* rounds to win 0 is 1 */
    /* a decided byte never seen (not 1/2/3): the winner byte is the game's verdict; neither: the counts */
    expect(3, 1, 7, 0, 3, 3, 1, 0, true);
    expect(3, 1, 7, 1, 3, 0, 3, 1, false);
    expect(3, 1, 7, 9, 3, 3, 1, 0, true);
    expect(0, 0, 7, 1, 3, 0, 3, 1, false);
    expect(0, 0, 7, 9, 3, 0, 0, -1, false);      /* nothing at all: no result (the hooks write none) */
    printf("fallback ok\n");

    /* a session: per match the round winners in turn; the hooks' reading (t5_hooks.cpp watch_match): a
     * result when the decided byte is up and none was written since it went down */
    struct Game { uint8_t c1 = 0, c2 = 0, decided = 0, winner = 0xFF, rounds = 3; } g;
    const char* matches[] = { "21211", "222", "1121", "21122", "111" };      /* round winners: 1 = P1, 2 = P2 */
    const unsigned want[][2] = { {3, 2}, {0, 3}, {3, 1}, {2, 3}, {3, 0} };
    bool done = true;            /* (session start: the last session's decided byte may still be up) */
    unsigned results = 0;
    for (int m = 0; m < 5; m++) {
        /* FIGHT START: ~230 frames with the last match's byte and counts still there */
        for (int f = 0; f < 230; f++) {
            if (!g.decided) done = false;
            if (g.decided && !done) { CHECK(!"a result from the last match's counts"); }
        }
        g.c1 = g.c2 = 0; g.decided = 0; g.winner = 0xFF;                  /* the game mode starts */
        if (!g.decided) done = false;
        for (const char* r = matches[m]; *r; r++) {
            CHECK(!g.decided);                                              /* (no round after the deciding one) */
            if (*r == '1') g.c1++; else g.c2++;
            if (g.c1 == g.rounds || g.c2 == g.rounds) { g.winner = g.c1 == g.rounds ? 0 : 1; g.decided = (uint8_t)(g.winner + 1); }
            if (g.decided && !done) {
                const np::MatchScore s = np::MatchScore::of(g.c1, g.c2, g.decided, g.winner, g.rounds);
                CHECK(s.counted && s.p1 == want[m][0] && s.p2 == want[m][1] && s.winner() == (int)g.winner);
                done = true;
                results++;
            }
        }
    }
    CHECK(results == 5);
    printf("session ok\n");
    printf("PASS %d checks\n", g_checks);
    return 0;
}
