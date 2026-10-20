/*
 * The score of a decided match ("score" in T5_NET_RESULT_FILE, docs/NETPLAY.md "Match result") --
 * read by the netplay hooks (t5_hooks.cpp) and the direct-fight driver (df_fight.cpp) the same way;
 * tests/c/match_score_test.cpp checks it on its own.
 *
 * Rounds won: the u8 at +0xA1 of each fighter's block (P1 0x10090030, P2 0x10090900, 0x8D0 apart;
 * +0xA2 is an i16 with the fighter's last round: 1 won, -1 lost). The game counts a round there on
 * its KO frame -- for the last round the same frame the decided byte 0x1008EBD5 rises -- and clears
 * both counts when the next match's game mode starts (the frame the decided byte goes back to 0).
 * Found with guest memory dumps at every round's replay of a rollback pair (8 rounds in 2 matches,
 * 3-2 and 0-3) and the words watched frame by frame through more matches.
 *
 * Before 1.1.3 the score came from the battle config's bytes +0x2E/+0x2F (0x1008EBDA/DB), taken for
 * the rounds won in a menu-driven VS match. In direct fights they stay 0, so the score was made up
 * from the winner byte as rounds-to-win : 0 (a 3-2 or 3-1 read 3-0), and when one of them was not 0
 * (mashing rollback pairs, first to 3: 0-1 and 1-0) that was the score: "[0, 1]" for a match P2 won
 * with three rounds. The lobby decides on the score when the other player's report is a lost
 * connection (only a full score -- the winner at the rounds to win -- stands, docs/RANKED.md
 * "Results"); history and result cards show it.
 *
 * The decided byte says how the match ended: 1 P1 won, 2 P2 won, 3 a draw (a time-out with equal health
 * or a double KO in the deciding round: both fighters count that round -- a no-input pair, first to 1,
 * ended 1-1 with 3 there). The winner byte 0x1008EBD6 is 0 in a draw: 1.1.2 reported every drawn
 * match as P1's win (the score made up as rounds-to-win : 0 from it).
 *
 * of() uses the counts when they can be the match's -- not both 0, none above the rounds to win, their
 * winner the decided byte's -- and falls back to the decided byte (or, for a value never seen there,
 * the winner byte) with rounds-to-win : 0 (a draw: rounds-to-win each) otherwise; `counted` is false
 * then (the hooks log it).
 */
#pragma once
#include <stdint.h>

namespace np {

struct MatchScore {
    static constexpr uint32_t kRoundWinsP1 = 0x100900D1;   /* u8: P1's fighter block 0x10090030 + 0xA1 */
    static constexpr uint32_t kRoundWinsP2 = 0x100909A1;   /* u8: P2's fighter block 0x10090900 + 0xA1 */

    unsigned p1 = 0, p2 = 0;
    bool counted = false;        /* the fighters' round counts (false: made up from the decided byte) */

    /* At a boundary where the decided byte is set. wins1/wins2: the fighters' counts; decided: the decided
     * byte 0x1008EBD5; winner_idx: the winner byte 0x1008EBD6 (0 = P1, 1 = P2); rounds_to_win: the battle
     * config's 0x1008EBD4. */
    static MatchScore of(uint8_t wins1, uint8_t wins2, uint8_t decided, uint8_t winner_idx, uint8_t rounds_to_win)
    {
        MatchScore s;
        const unsigned r = rounds_to_win ? rounds_to_win : 1;
        /* the game's own verdict: 0 = P1, 1 = P2, -1 = a draw, -2 = not known */
        const int game = decided == 1 ? 0 : decided == 2 ? 1 : decided == 3 ? -1 : winner_idx <= 1 ? (int)winner_idx : -2;
        const int counts = wins1 > wins2 ? 0 : wins2 > wins1 ? 1 : -1;
        const bool sane = (wins1 || wins2) && wins1 <= r && wins2 <= r;
        if (sane && (game == -2 || counts == game)) {
            s.p1 = wins1; s.p2 = wins2; s.counted = true;
        } else if (game == 0) {
            s.p1 = r;
        } else if (game == 1) {
            s.p2 = r;
        } else if (game == -1) {
            s.p1 = s.p2 = r;
        }
        return s;
    }

    /* 0 = P1, 1 = P2, -1 = none (a draw, or nothing decided) */
    int winner() const { return p1 > p2 ? 0 : p2 > p1 ? 1 : -1; }
};

} // namespace np
