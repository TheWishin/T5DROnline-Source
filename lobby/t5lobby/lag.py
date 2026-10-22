"""The post-game lag check: "ping X ms should mean about Y frames behind, it was Z".

What it compares, with the numbers we really have (no game change is needed):

* Y, the frames behind the ping explains: the input delay the lobby chose for the measured ping
  (proto.suggest_delay: one-way latency + jitter + a frame of clock phase, in 59.94 Hz frames).
  The players feel exactly this much lag when the connection keeps its promise.
* Z, the frames behind it really was: Y plus the extra frames the games spent waiting for the
  other side's input. Each game's netplay log says how long it waited ("waited W s of T s" in the
  `speed:` line, 600 frames per line); the launcher turns that into milliseconds per frame and sends
  it as a lag report. Z uses the larger of the two sides.
* The cause of extra waiting: a PC whose own speed (without the waits) is below the warn speed
  makes the other PC wait for it. Waiting with both PCs fast is the network (jitter, loss).
* How long the games stood still: Z is an average per frame, so a match that froze ~9 ms per frame
  (92 s of 256 s, 40 fps on 60 fps PCs) still read "5.6 frames, what the ping explains" (1.1.4).
  A game that waited WAIT_SHARE of the match time or more (or ran well below its PC's own speed)
  makes the verdict "slow": "This match lagged: the games waited N s for each other's inputs."

Nothing here ends a match or changes a rating. The result is shown to both players; leaving the set
afterwards is their choice (docs/RANKED.md, "Post-game lag check").
"""
from .i18n import num, t
from .proto import FRAME_MS

MIN_FRAMES = 300        # a report over fewer frames says too little (the first speed line is at 600)
WAIT_SHARE = 0.05       # a game that stood still this share of the match time (or more): the match lagged ...
WAIT_MIN_S = 3.0        # ... when that is at least this many seconds (a short match's few stalls say little)
FPS_RATIO = 0.85        # ... the same for a game that ran below this share of its PC's own speed
WAIT_DIFFER = 1.25      # one game waited this many times as long as the other, and WAIT_DIFFER_S more:
WAIT_DIFFER_S = 2.0     # the server log names it


def clean_report(msg):
    """Validate one side's lag report (the client's `lag` message) -> dict or None."""
    try:
        frames = int(msg.get("frames"))
        waited = float(msg.get("waited_ms"))
    except (TypeError, ValueError):
        return None
    if not (MIN_FRAMES <= frames <= 10 ** 7) or not (0.0 <= waited <= 1e10):
        return None
    out = {"frames": frames, "waited_ms": round(waited, 1)}
    for key in ("pc_fps", "fps"):
        try:
            v = float(msg.get(key))
        except (TypeError, ValueError):
            v = None
        out[key] = round(v, 1) if v is not None and 0 < v < 1000 else None
    return out


def extra_frames(report):
    """Frames of waiting per frame played, in frames (0 = never waited)."""
    return (report["waited_ms"] / report["frames"]) / FRAME_MS


def match_seconds(report):
    """How long the match ran on that PC: its frames at the speed the game really ran (waits included),
    else its frames at 59.94 Hz plus the waits."""
    fps = report.get("fps")
    if fps:
        return report["frames"] / fps
    return report["frames"] * FRAME_MS / 1000.0 + report["waited_ms"] / 1000.0


def stood_still(report, wait_share=WAIT_SHARE):
    """Did this game wait for the other one much of the match (or run well below its PC's own speed)?"""
    if not report or wait_share <= 0:
        return False
    waited = report["waited_ms"] / 1000.0
    if waited < WAIT_MIN_S:
        return False
    if waited >= wait_share * match_seconds(report):
        return True
    fps, pc = report.get("fps"), report.get("pc_fps")
    return bool(fps and pc and fps < FPS_RATIO * pc)


def assess(delay, reports, warn_fps=55.0, tolerance=1.0, wait_share=WAIT_SHARE):
    """reports: [side 0 report or None, side 1 report or None] (clean_report results).
    -> {expected, observed, extra [per side or None], verdict ok|more_lag|slow|unknown, cause, slow [sides],
        waited_s [per side or None], share (the longer wait / its match time), waited_more (side or None),
        why (a line for the server log, None when ok)}.
    `cause` is network | pc | None (pc: `slow` names the sides whose own speed was below warn_fps).
    more_lag: the waits add more than `tolerance` frames per frame; slow: fewer, but a game stood still
    `wait_share` of the match time or more (stood_still; 0 = off)."""
    extra = [extra_frames(r) if r else None for r in reports]
    have = [e for e in extra if e is not None]
    slow = [i for i, r in enumerate(reports) if r and r.get("pc_fps") and warn_fps > 0 and r["pc_fps"] < warn_fps]
    waited = [round(r["waited_ms"] / 1000.0, 1) if r else None for r in reports]
    shares = [min(1.0, r["waited_ms"] / 1000.0 / max(match_seconds(r), 0.001)) for r in reports if r]
    out = {"expected": int(delay), "observed": None, "extra": [None if e is None else round(e, 2) for e in extra],
           "verdict": "unknown", "cause": None, "slow": slow, "waited_s": waited,
           "share": round(max(shares), 3) if shares else None, "waited_more": None, "why": None}
    if not have:
        return out
    if None not in waited:
        lo, hi = sorted(waited)
        if hi >= WAIT_DIFFER * lo and hi - lo >= WAIT_DIFFER_S:
            out["waited_more"] = waited.index(hi)
    worst = max(have)
    out["observed"] = round(delay + worst, 1)
    if worst > tolerance:
        out["verdict"] = "more_lag"
    elif any(stood_still(r, wait_share) for r in reports):
        out["verdict"] = "slow"
    else:
        out["verdict"] = "ok"
        return out
    out["cause"] = "pc" if slow else "network"
    out["why"] = why(out, reports)
    return out


def why(a, reports):
    """The server log's words for a lagged match: "network: the games waited 92 s / 95 s of 256 s (37 %) for each
    other's inputs" (+ "; P2's game waited more" when one waited clearly longer; pc: which PC was slow first)."""
    secs = " / ".join("-" if w is None else f"{w:.0f} s" for w in a["waited_s"])
    total = max(match_seconds(r) for r in reports if r)
    text = f"the games waited {secs} of {total:.0f} s ({(a['share'] or 0) * 100:.0f} %) for each other's inputs"
    if a["waited_more"] is not None:
        text += f"; P{a['waited_more'] + 1}'s game waited more"
    if a["cause"] == "pc":
        pcs = ", ".join(f"P{i + 1} {(reports[i] or {}).get('pc_fps') or 0:.0f} fps" for i in a["slow"])
        return f"pc: below full speed: {pcs}; {text}"
    return f"network: {text}"


def waited_most(a):
    """The longer of the two games' waits in seconds (the "N s" the players see), or None."""
    have = [w for w in (a.get("waited_s") or ()) if w is not None]
    return max(have) if have else None


def lagged(verdict):
    """Did the lag check find the match worse than its ping (more_lag; slow: the games stood still a lot)?"""
    return verdict in ("more_lag", "slow")


def describe(ping_ms, a, side, reports=None):
    """One plain sentence pair for the player on `side` (0/1): what the ping should mean and what
    it was. `a` is assess()'s result."""
    head = f"Ping {ping_ms:.0f} ms should mean about {a['expected']} frames behind."
    if a["verdict"] == "unknown":
        return head + " The games did not report how it went, so there is nothing to compare."
    if a["verdict"] == "slow":
        text = f"This match lagged: the games waited {waited_most(a):.0f} s for each other's inputs."
        if a["cause"] != "pc":
            return text + " A wired connection and no uploads during matches help."
    else:
        text = f"{head} It was {a['observed']:.1f}."
        if a["verdict"] == "ok":
            return text + " That is what the ping explains."
        text += " That is more than the ping explains."
    if a["cause"] == "pc":
        mine = side in a["slow"]
        theirs = (1 - side) in a["slow"]
        fps = lambda s: (reports[s] or {}).get("pc_fps") if reports else None   # noqa: E731
        if mine and theirs:
            return text + " Both PCs ran below full speed."
        if mine:
            f = fps(side)
            return text + f" Your PC was the slow one{f' ({f:.0f} fps)' if f else ''}."
        f = fps(1 - side)
        return text + f" Your opponent's PC was the slow one{f' ({f:.0f} fps)' if f else ''}."
    return text + " Both PCs kept up, so the connection stalled now and then (jitter or lost packets)."


def describe_event(ev):
    """The same sentences as describe(), from the numbers in a lag_check event, in the player's language.
    An event without them (an older server) shows the server's own English `text`."""
    try:
        ping = float(ev["ping_ms"])
        expected = int(ev["expected_frames"])
        verdict = ev["verdict"]
    except (KeyError, TypeError, ValueError):
        return str(ev.get("text", ""))
    cause = ev.get("cause")
    if verdict == "slow":
        try:
            secs = float(ev["waited_s"])
        except (KeyError, TypeError, ValueError):
            return str(ev.get("text", ""))
        text = t("This match lagged: the games waited {secs} s for each other's inputs.", secs=f"{secs:.0f}")
        if cause in ("both_pcs", "your_pc", "opponent_pc"):
            return text + " " + _pc_sentence(ev, cause)
        return text + " " + t("A wired connection and no uploads during matches help.")
    text = t("Ping {ping} ms should mean about {frames} frames behind.", ping=f"{ping:.0f}", frames=expected)
    if verdict == "unknown" or ev.get("observed_frames") is None:
        return text + " " + t("The games did not report how it went, so there is nothing to compare.")
    text += " " + t("It was {observed}.", observed=num(ev["observed_frames"], 1))
    if verdict == "ok":
        return text + " " + t("That is what the ping explains.")
    text += " " + t("That is more than the ping explains.")
    if cause in ("both_pcs", "your_pc", "opponent_pc"):
        return text + " " + _pc_sentence(ev, cause)
    return text + " " + t("Both PCs kept up, so the connection stalled now and then (jitter or lost packets).")


def _pc_sentence(ev, cause):
    if cause == "both_pcs":
        return t("Both PCs ran below full speed.")
    fps = (ev.get("yours" if cause == "your_pc" else "opponent") or {}).get("pc_fps")
    if cause == "your_pc":
        return (t("Your PC was the slow one ({fps} fps).", fps=f"{fps:.0f}") if fps
                else t("Your PC was the slow one."))
    return (t("Your opponent's PC was the slow one ({fps} fps).", fps=f"{fps:.0f}") if fps
            else t("Your opponent's PC was the slow one."))
