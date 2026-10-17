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

Nothing here ends a match or changes a rating. The result is shown to both players; leaving the set
afterwards is their choice (docs/RANKED.md, "Post-game lag check").
"""
from .proto import FRAME_MS

MIN_FRAMES = 300        # a report over fewer frames says too little (the first speed line is at 600)


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


def assess(delay, reports, warn_fps=55.0, tolerance=1.0):
    """reports: [side 0 report or None, side 1 report or None] (clean_report results).
    -> {expected, observed, extra [per side or None], verdict ok|more_lag|unknown, cause, slow [sides]}.
    `cause` is network | pc | None (pc: `slow` names the sides whose own speed was below warn_fps)."""
    extra = [extra_frames(r) if r else None for r in reports]
    have = [e for e in extra if e is not None]
    slow = [i for i, r in enumerate(reports) if r and r.get("pc_fps") and warn_fps > 0 and r["pc_fps"] < warn_fps]
    out = {"expected": int(delay), "observed": None, "extra": [None if e is None else round(e, 2) for e in extra],
           "verdict": "unknown", "cause": None, "slow": slow}
    if not have:
        return out
    worst = max(have)
    out["observed"] = round(delay + worst, 1)
    if worst <= tolerance:
        out["verdict"] = "ok"
    else:
        out["verdict"] = "more_lag"
        out["cause"] = "pc" if slow else "network"
    return out


def describe(ping_ms, a, side, reports=None):
    """One plain sentence pair for the player on `side` (0/1): what the ping should mean and what
    it was. `a` is assess()'s result."""
    head = f"Ping {ping_ms:.0f} ms should mean about {a['expected']} frames behind."
    if a["verdict"] == "unknown":
        return head + " The games did not report how it went, so there is nothing to compare."
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
