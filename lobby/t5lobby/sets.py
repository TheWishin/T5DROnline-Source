"""Texts for ranked sets (docs/RANKED.md "Ranked sets"): a ranked set is best of 3, the first player to win
2 games wins it, and the rating changes once, at its end.

No UI here: the Online tab (and any other front end) shows these strings in one label. Every text goes
through t5lobby.i18n (German in i18n_de.py).

    status_text(set_info, slot)   "Set 1-0 -- game 2 of 3", "Set 1-0 -- game 2 of 3 -- starts in 5 s"
                                  (`set` of match_found / match_start / match_result; slot = this player's
                                  side, 0 = P1); "" for anything that is not a rated set
    result_text(set_end)          "You won the set 2-1; rating 1532 (+32) -- PROMOTED to 1st Dan!"
                                  (the set_end event of a rated set); "" otherwise
    history_text(row_set)         " -- set game 2, set won 2-1" for a history row's `set`; "" otherwise
                                  (" -- set game 1, set lost 1-0 (you did not come back within 90 s)")
    leave_text(reason, by)        "your opponent left the set": who ended a set by leaving it, and how
"""
import math

from .i18n import t

# Why a set (or its last game) ended without a result, for the player. (Functions, not N_() marks: every text
# is a literal t() call where it is translated.)
REASON_TEXT = {
    "desync": lambda: t("the two games went out of sync"),
    "too_short": lambda: t("a game was too short to count"),
    "no_result": lambda: t("a fight ended without a winner"),
    "draw": lambda: t("too many games without a winner"),
    "disputed": lambda: t("the reports disagreed"),
    "crash": lambda: t("a game crashed"),
    "connection": lambda: t("the connection between the games failed"),
    "no_report": lambda: t("a player did not report"),
    "both_left": lambda: t("both players left"),
    "timeout": lambda: t("no result in time"),
    "lag": lambda: t("left after the lag check"),
    "server_restart": lambda: t("the lobby server restarted"),
    "early_quit": lambda: t("a player left right away"),
    "cancelled": lambda: t("the next game could not start"),
    "left": lambda: t("a player left before a game counted"),
    "disconnect": lambda: t("a player lost the lobby connection"),
    "declined": lambda: t("a player left"),
    "no_return": lambda: t("a player did not come back in time"),
}
SET_RESULT = {"win": lambda: t("set won"), "loss": lambda: t("set lost")}
AWAY_SECONDS = 90      # the server's T5L_SET_AWAY_SECONDS (set_end says it; older history rows: the default)


def leave_text(reason, by, seconds=None):
    """Who ended a ranked set by leaving it, and how (1.1.9): 'your opponent left the set' (the Leave set button),
    'you did not come back within 90 s' (a crash, a closed launcher, a lost connection, not back in time),
    'your opponent quit a game' ... -- `reason` and `by` (you | opponent) of set_end or of a history row's set;
    '' when the set did not end that way."""
    if by not in ("you", "opponent"):
        return ""
    you = by == "you"
    if reason in ("left", "declined"):
        return t("you left the set") if you else t("your opponent left the set")
    if reason == "no_return":
        n = int(round(float(seconds or AWAY_SECONDS)))
        return (t("you did not come back within {seconds} s", seconds=n) if you
                else t("your opponent did not come back within {seconds} s", seconds=n))
    if reason in ("quit", "early_quit", "early_quit_repeat"):
        return t("you quit a game") if you else t("your opponent quit a game")
    if reason in ("disconnect", "connection"):
        return t("you lost the connection") if you else t("your opponent lost the connection")
    if reason == "no_connection":
        return t("your side could not connect") if you else t("your opponent's side could not connect")
    return ""


def status_text(info, slot=0):
    """Where the set stands, from this player's side: 'Set 1-0 -- game 2 of 3' (+ ' -- starts in N s' during
    the countdown between two games). '' when `info` is not a rated set (casual, or every game rated on its
    own)."""
    if not info or not info.get("rated"):
        return ""
    w = info.get("wins") or [0, 0]
    mine, theirs = (w[0], w[1]) if slot == 0 else (w[1], w[0])
    text = t("Set {mine}-{theirs}", mine=mine, theirs=theirs)
    if info.get("state") == "ended":
        return text
    nxt = info.get("next")
    number = (nxt or {}).get("number") or info.get("number") or 1
    best = info.get("best_of", 3)
    if nxt and nxt.get("replay"):
        text += " -- " + t("game {number} of {best} again (no winner)", number=number, best=best)
    else:
        text += " -- " + t("game {number} of {best}", number=number, best=best)
    if nxt:
        text += " -- " + t("starts in {seconds} s", seconds=max(0, math.ceil(float(nxt.get("in") or 0))))
    return text


def rank_change_text(r):
    """'; rating 1532 (+32) -- PROMOTED to 1st Dan!' for a rating change (match_result / set_end `rating`)."""
    if not r:
        return ""
    text = "; " + t("rating {rating} ({delta})", rating=f"{r['after']['r']:.0f}", delta=f"{r['delta']:+.0f}")
    after = r.get("rank_after") or {}
    if r.get("event") == "promoted":
        text += " -- " + t("PROMOTED to {rank}!", rank=after.get("rank"))
    elif r.get("event") == "demoted":
        text += " -- " + t("demoted to {rank}", rank=after.get("rank"))
    elif r.get("event") == "placed":
        text += " -- " + t("placed at {rank}", rank=after.get("rank"))
    elif after.get("placement"):
        text += " -- " + t("placement {done}/{total}", done=after["placement"][0], total=after["placement"][1])
    return text


def result_text(ev):
    """The end of a rated set (a set_end event): who won, the score, the one rating change."""
    if not ev or not ev.get("rated"):
        return ""
    res = ev.get("result")
    if ev.get("status") not in ("confirmed", "forfeit") or res not in ("win", "loss"):
        why = REASON_TEXT.get(ev.get("outcome_reason") or ev.get("reason") or "")
        if why:
            return t("The set does not count ({why}); no rating change", why=why())
        return t("The set does not count; no rating change")
    w = ev.get("wins") or [0, 0]
    if ev.get("status") == "forfeit":
        who = ev.get("blame") or ev.get("by")
        you_left = who == "you"
        why = ev.get("outcome_reason") or ev.get("reason")
        how = leave_text(why, who, ev.get("away_seconds")) if why not in ("left", "declined") else ""
        if how:
            text = t("You won the set ({how})", how=how) if res == "win" else t("You lost the set ({how})", how=how)
        elif res == "win":
            text = t("You won the set (your opponent left it)") if not you_left else t("You won the set")
        else:
            text = t("You lost the set (you left it)") if you_left else t("You lost the set")
    elif res == "win":
        text = t("You won the set {mine}-{theirs}", mine=w[0], theirs=w[1])
    else:
        text = t("You lost the set {mine}-{theirs}", mine=w[0], theirs=w[1])
    return text + rank_change_text(ev.get("rating"))


def history_text(sv):
    """For a history row of a set's game (`set` {game, result, score [you, opp]}): ' -- set game 2, set won 2-1'."""
    if not sv:
        return ""
    text = " -- " + t("set game {number}", number=sv.get("game"))
    sc = sv.get("score")
    if sv.get("result") in SET_RESULT and sc:
        text += ", " + SET_RESULT[sv["result"]]() + f" {sc[0]}-{sc[1]}"
    how = leave_text(sv.get("reason"), sv.get("by"), sv.get("away_seconds")) if sv.get("status") == "forfeit" else ""
    if how:
        text += " (" + how + ")"          # 1.1.9: who left the set, and how
    return text
