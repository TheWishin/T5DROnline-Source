"""Texts for ranked sets (docs/RANKED.md "Ranked sets"): a ranked set is best of 3, the first player to win
2 games wins it, and the rating changes once, at its end.

No UI here: the Online tab (and any other front end) shows these strings in one label.

    status_text(set_info, slot)   "Set 1-0 -- game 2 of 3", "Set 1-0 -- game 2 of 3 starts in 5 s"
                                  (`set` of match_found / match_start / match_result; slot = this player's
                                  side, 0 = P1); "" for anything that is not a rated set
    result_text(set_end)          "You won the set 2-1; rating 1532 (+32) -- PROMOTED to 1st Dan!"
                                  (the set_end event of a rated set); "" otherwise
"""
import math

# Why a set (or its last game) ended without a result, for the player.
REASON_TEXT = {"desync": "the two games went out of sync", "too_short": "a game was too short to count",
               "no_result": "a fight ended without a winner", "draw": "too many games without a winner",
               "disputed": "the reports disagreed", "crash": "a game crashed",
               "connection": "the connection between the games failed", "no_report": "a player did not report",
               "both_left": "both players left", "timeout": "no result in time", "lag": "left after the lag check",
               "server_restart": "the lobby server restarted", "early_quit": "a player left right away",
               "cancelled": "the next game could not start", "left": "a player left before a game counted",
               "disconnect": "a player lost the lobby connection", "declined": "a player left"}


def status_text(info, slot=0):
    """Where the set stands, from this player's side: 'Set 1-0 -- game 2 of 3' (+ ' starts in N s' during the
    countdown between two games). '' when `info` is not a rated set (casual, or every game rated on its own)."""
    if not info or not info.get("rated"):
        return ""
    w = info.get("wins") or [0, 0]
    mine, theirs = (w[0], w[1]) if slot == 0 else (w[1], w[0])
    text = f"Set {mine}-{theirs}"
    if info.get("state") == "ended":
        return text
    nxt = info.get("next")
    number = (nxt or {}).get("number") or info.get("number") or 1
    text += f" -- game {number} of {info.get('best_of', 3)}"
    if nxt:
        if nxt.get("replay"):
            text += " again (no winner)"
        text += f" starts in {max(0, math.ceil(float(nxt.get('in') or 0)))} s"
    return text


def rank_change_text(r):
    """'; rating 1532 (+32) -- PROMOTED to 1st Dan!' for a rating change (match_result / set_end `rating`)."""
    if not r:
        return ""
    text = f"; rating {r['after']['r']:.0f} ({r['delta']:+.0f})"
    after = r.get("rank_after") or {}
    if r.get("event") == "promoted":
        text += f" -- PROMOTED to {after.get('rank')}!"
    elif r.get("event") == "demoted":
        text += f" -- demoted to {after.get('rank')}"
    elif r.get("event") == "placed":
        text += f" -- placed at {after.get('rank')}"
    elif after.get("placement"):
        text += f" -- placement {after['placement'][0]}/{after['placement'][1]}"
    return text


def result_text(ev):
    """The end of a rated set (a set_end event): who won, the score, the one rating change."""
    if not ev or not ev.get("rated"):
        return ""
    res = ev.get("result")
    if ev.get("status") not in ("confirmed", "forfeit") or res not in ("win", "loss"):
        why = REASON_TEXT.get(ev.get("outcome_reason") or ev.get("reason") or "")
        return "The set does not count" + (f" ({why})" if why else "") + "; no rating change"
    verb = "won" if res == "win" else "lost"
    if ev.get("status") == "forfeit":
        who = ev.get("blame") or ev.get("by")
        text = f"You {verb} the set ({'you left it' if who == 'you' else 'your opponent left it'})"
    else:
        w = ev.get("wins") or [0, 0]
        text = f"You {verb} the set {w[0]}-{w[1]}"
    return text + rank_change_text(ev.get("rating"))
