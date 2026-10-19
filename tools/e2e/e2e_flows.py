"""What players do in the Online tab, as reusable steps, and what the evidence of a match is."""
import os
import re
import time

from e2e_harness import Abort, log

import fight_flow_test            # tools/: the FIFO stall patterns, the window close (Alt+F4)
import rollback_net_test          # tools/: the rollback summary line

MATCH_SECONDS = 330               # one real match, from match_start to both results
STUB_MATCH_SECONDS = 40

RE_PICK = re.compile(r"\[netplay\] rollback input delay for this match: (\d+) frame\(s\) \((.*)\)")
RE_AGREED = re.compile(r"\[netplay\] rollback agreed: input delay (\d+) -> (\d+)")
RE_CONNECTED = re.compile(r"\[netplay\] connected \((\w+), (P\d)\), delay (\d+)")
RE_SYNC = re.compile(r"sync check through frame (\d+): (\d+) mismatching")
RE_SPEED = re.compile(r"\[netplay\] speed: ([\d.]+) fps, this PC ([\d.]+) fps")
RE_FIGHT = re.compile(r"\[df\] frame (\d+): FIGHT START match (\d+) id (\S+): (.*?), stage (\d+)")
RE_LS_DELAY = re.compile(r"lockstep starts: frame \d+, delay (\d+)")
RE_LOST = re.compile(r"\[netplay\] .*(peer lost|cannot connect) \((\w+)\)")


def parse_segment(lines):
    """The numbers of one match from its part of the game log."""
    out = {"pick": None, "pick_why": None, "agreed": None, "mode": None, "connected": None, "rollbacks": 0,
           "resim": 0, "stalls": 0, "stall_ms": 0.0, "rb_windows": [], "sync": None, "desync_lines": 0,
           "crash": False, "fifo": {}, "fight_start": [], "speed": [], "lost": None, "build_mismatch": False,
           "ls_delay": None, "delay": None}
    for ln in lines:
        m = RE_PICK.search(ln)
        if m:
            out["pick"], out["pick_why"] = int(m.group(1)), m.group(2)
        m = RE_AGREED.search(ln)
        if m:
            out["agreed"] = int(m.group(2))
        if "[netplay] rollback mode starts" in ln or "rollback loop takes over" in ln:
            out["mode"] = "rollback"
        elif "[netplay] lockstep starts: frame" in ln:
            if out["mode"] is None:
                out["mode"] = "lockstep"
            m = RE_LS_DELAY.search(ln)
            if m:
                out["ls_delay"] = int(m.group(1))
        m = RE_CONNECTED.search(ln)
        if m:
            out["connected"] = (m.group(1), m.group(2), int(m.group(3)))
        m = rollback_net_test.RE_RBNET.search(ln)
        if m:
            g = m.groupdict()
            out["rollbacks"] += int(g["rb"])
            out["resim"] += int(g["resim"])
            out["stalls"] += int(g["stalls"])
            out["stall_ms"] += float(g["stall_ms"])
            if float(g["secs"]) > 0:
                out["rb_windows"].append(int(g["frames"]) / float(g["secs"]))
        m = RE_SYNC.search(ln)
        if m:
            out["sync"] = (int(m.group(1)), int(m.group(2)))
        if "DESYNC at frame" in ln:
            out["desync_lines"] += 1
        if "[CRASH]" in ln:
            out["crash"] = True
        for name, rx in fight_flow_test.FIFO_BAD:
            if rx.search(ln):
                out["fifo"][name] = out["fifo"].get(name, 0) + 1
        m = RE_FIGHT.search(ln)
        if m:
            out["fight_start"].append(m.group(0))
        m = RE_SPEED.search(ln)
        if m:
            out["speed"].append((float(m.group(1)), float(m.group(2))))
        m = RE_LOST.search(ln)
        if m:
            out["lost"] = m.group(2)
        if "build_mismatch" in ln or "different build" in ln:
            out["build_mismatch"] = True
    if out["mode"] is None and out["rb_windows"]:
        out["mode"] = "rollback"           # a rematch in the session: the rollback loop simply goes on
    elif out["mode"] is None and out["speed"]:
        out["mode"] = "lockstep"
    # the input delay this game ran with: the rollback pick (host) / the agreed change (joiner), else the
    # session's lockstep delay (no "agreed" line when the pick equals it)
    out["delay"] = out["agreed"] if out["agreed"] is not None else (
        out["pick"] if out["pick"] is not None else out["ls_delay"])
    return out


# ---------------------------------------------------------------------------------- lobby steps
def login(ctx, p, how="guest", timeout=20):
    """Log in through the tab's buttons: guest | register | account."""
    {"guest": p.login_guest, "register": p.register, "account": p.login}[how]()
    ok = ctx.wait(lambda: p.logged_in(), timeout, f"{p.name}: logged in ({how})")
    if ok:
        ctx.wait(lambda: p.action_on("quick"), 10, fail=False)
    return ok


def latest(p, t, since):
    ev = p.events_of(t, since)
    return ev[-1] if ev else None


def found_both(ctx, a, b, since, timeout=30):
    ok = ctx.wait(lambda: latest(a, "match_found", since) and latest(b, "match_found", since), timeout,
                  f"match found for {a.name} and {b.name}")
    if not ok:
        raise Abort("no match found")
    fa, fb = latest(a, "match_found", since), latest(b, "match_found", since)
    ctx.require("both found the same match", fa["match"] == fb["match"], f"{fa['match']} / {fb['match']}")
    return fa["match"]


def accept(ctx, p, mid, timeout=15):
    ctx.wait(lambda: p.bar_button("Accept") is not None, timeout, f"{p.name}: Accept button for {mid}")
    p.click("Accept")


def started_both(ctx, a, b, mid, timeout=40):
    return ctx.wait(lambda: a.matches.get(mid, {}).get("started") and b.matches.get(mid, {}).get("started"), timeout,
                    f"match {mid} started on both PCs")


def queue_match(ctx, a, b, mode="quick", accept_both=True, timeout=40):
    """Both press Quick/Ranked match, both accept: returns the match id once both got match_start."""
    since = time.time()
    a.press(mode)
    ctx.sleep(0.3)
    b.press(mode)
    mid = found_both(ctx, a, b, since, timeout)
    if accept_both:
        accept(ctx, a, mid)
        ctx.sleep(0.4)
        accept(ctx, b, mid)
        if not started_both(ctx, a, b, mid):
            raise Abort("match did not start")
    return mid


def wait_results(ctx, mid, players, timeout=MATCH_SECONDS):
    ok = ctx.wait(lambda: all(p.matches.get(mid, {}).get("status") for p in players), timeout,
                  f"result of {mid} on both PCs")
    if not ok:
        for p in players:
            ctx.note(f"{p.name}: match {mid}: {strip(p.matches.get(mid))}; status line {p.status_text()!r}")
    return ok


def rematch(ctx, a, b, timeout=40):
    """Both click Rematch after a result: returns the next match id (it must start on both)."""
    since = time.time()
    ctx.wait(lambda: a.bar_button("Rematch") is not None, 20, f"{a.name}: Rematch button")
    a.click("Rematch")
    ctx.wait(lambda: b.bar_button("Rematch") is not None, 20, f"{b.name}: Rematch button")
    b.click("Rematch")
    mid = found_both(ctx, a, b, since, timeout)
    if not started_both(ctx, a, b, mid, timeout):
        raise Abort("rematch did not start")
    return mid


def leave(ctx, p):
    """Leave after a result (the rematch bar's Leave, or No thanks on an offer)."""
    wanted = {"Leave", _tr("Leave"), "No thanks", _tr("No thanks")}      # not "Leave: too laggy", not "Leave set"
    for b, text, _pad in p.tab.bar_spec:
        if text in wanted:
            b.invoke()
            return True
    return False


def _tr(text):
    try:
        from t5lobby import i18n
        return i18n.t(text)
    except ImportError:
        return text


def strip(m):
    if not m:
        return m
    return {k: v for k, v in m.items() if k not in ("log_mark", "you", "lag", "set")}


# ---------------------------------------------------------------------------------- evidence
def match_row(ctx, mid, players, expect="confirmed", label="", same_result=True, sync=True):
    """Check one finished real-game match and add its evidence row:
    both saw `expect` from the lobby; with same_result, both games wrote a result for this match with
    the same winner and state hash and 0 mismatching frames; the logs show no crash and no FIFO stall."""
    a, b = players
    ma, mb = a.matches.get(mid, {}), b.matches.get(mid, {})
    row = {"match": mid, "label": label, "status": ma.get("status"), "reason": ma.get("reason"),
           "path": ma.get("path"), "rtt_lobby": ma.get("rtt"), "cont": ma.get("cont"), "ranked": ma.get("ranked"),
           "fight": ma.get("fight"), "shaper": ctx.shaper.describe()}
    ctx.check(f"{label or mid}: lobby result {expect}", ma.get("status") == expect and mb.get("status") == expect,
              f"{a.name}: {ma.get('status')} ({ma.get('reason')}), {b.name}: {mb.get('status')} ({mb.get('reason')})")
    for p, m in ((a, ma), (b, mb)):
        seg = parse_segment(p.log_segment(mid))
        rf = p.result_file(mid) or {}
        tf = (m.get("fight_at") - m.get("started")) if m.get("fight_at") and m.get("started") else None
        row[p.name] = {"result_file": rf, "to_fight_s": round(tf, 1) if tf else None, "pick": seg["pick"],
                       "agreed": seg["agreed"], "delay": seg["delay"], "mode": seg["mode"], "rollbacks": seg["rollbacks"],
                       "stalls": seg["stalls"], "sync": seg["sync"], "fps_windows": _med(seg["rb_windows"]),
                       "speed": seg["speed"][-1] if seg["speed"] else None, "fifo": seg["fifo"],
                       "crash": seg["crash"], "lost": seg["lost"], "pick_why": seg["pick_why"]}
        ctx.check(f"{label or mid}: {p.name}'s game: no crash, no FIFO stall",
                  not seg["crash"] and not seg["fifo"].get("fifo_stall") and not seg["fifo"].get("drain_stalled"),
                  f"crash {seg['crash']}, fifo {seg['fifo']}")
        fought = fighters_of(seg, mid)
        row[p.name]["fought"] = fought
        want = lobby_fighters(p, ma.get("fight"))
        if want and fought:
            ctx.check(f"{label or mid}: {p.name}'s game fought the fighters the lobby sent", same_fighters(fought, want),
                      f"game {fought[0]} vs {fought[1]}, lobby {want[0]} vs {want[1]}")
        elif want:
            ctx.check(f"{label or mid}: {p.name}'s game reached FIGHT START of this match", False,
                      "no FIGHT START line with this match id")
    if same_result:
        ra, rb = row[a.name]["result_file"], row[b.name]["result_file"]
        ctx.check(f"{label or mid}: both games wrote this match's result", ra.get("match") == mid and rb.get("match") == mid,
                  f"{ra.get('match')} / {rb.get('match')}")
        ctx.check(f"{label or mid}: same winner and state hash on both PCs",
                  ra.get("winner") == rb.get("winner") and ra.get("hash") and ra.get("hash") == rb.get("hash"),
                  f"winner {ra.get('winner')}/{rb.get('winner')}, hash {ra.get('hash')}/{rb.get('hash')}, "
                  f"score {ra.get('score')}/{rb.get('score')}")
        if sync:
            ctx.check(f"{label or mid}: 0 mismatching frames", not ra.get("desync") and not rb.get("desync"),
                      f"desync {ra.get('desync')}/{rb.get('desync')}")
        if ma.get("winner") is not None:
            ctx.check(f"{label or mid}: lobby winner = game winner", ma.get("winner") == ra.get("winner"),
                      f"lobby {ma.get('winner')}, game {ra.get('winner')}")
    ctx.matches.append(row)
    fa, fb = (row[p.name]["result_file"].get("fps") for p in players)
    ctx.note(f"{label or mid}: {row['status']} {row['reason'] or ''} path {row['path']} "
             f"({ctx.shaper.describe()}), {'rematch in session' if row['cont'] else 'new session'}; "
             f"{a.name}: {_brief(row[a.name])}; {b.name}: {_brief(row[b.name])}; fps {fa}/{fb}")
    return row


def fighters_of(seg, mid):
    """(P1 name, P2 name) from this match's FIGHT START line in a game log segment, or None."""
    for ln in seg["fight_start"]:
        m = RE_FIGHT.search(ln)
        if m and m.group(3).rstrip(":") == mid:
            names = m.group(4).split(" vs ")
            if len(names) == 2:
                return names[0].strip(), names[1].strip()
    return None


def lobby_fighters(p, fight):
    if not fight or not fight.get("p1") or not fight.get("p2"):
        return None
    t = p.tab.table
    return t.fighter_name(fight["p1"]), t.fighter_name(fight["p2"])


def _norm(n):
    return re.sub(r"[^a-z0-9]", "", str(n).lower())


def same_fighters(game, lobby):
    """The game's short names ("Law", "Xiaoyu") against the lobby's ("Marshall Law", "Ling Xiaoyu")."""
    return all(_norm(g) and (_norm(g) in _norm(w) or _norm(w) in _norm(g)) for g, w in zip(game, lobby))


def _med(v):
    return round(sorted(v)[len(v) // 2], 1) if v else None


def _brief(r):
    rf = r["result_file"]
    return (f"to FIGHT {r['to_fight_s']} s, mode {r['mode']}, input delay {r['delay']}"
            f", {r['rollbacks']} rollbacks, {r['stalls']} stalls, winner {rf.get('winner')} score {rf.get('score')} "
            f"frames {rf.get('frames')} hash {rf.get('hash')}" + (f", reason {rf.get('reason')}" if rf.get("reason") else ""))


def fps_check(ctx, row, players, floor=45.0):
    """fps of both games in a match: below `floor` fails on a quiet PC, only warns next to other games."""
    busy = ctx.run.contention()
    for p in players:
        fps = row[p.name]["result_file"].get("fps")
        if fps is None:
            continue
        loaded = busy["games"] > 0 or busy["builds"] >= 4
        ctx.check(f"{row['label'] or row['match']}: {p.name} fps {fps}", fps >= floor,
                  f"floor {floor}" + (f"; {busy['games']} other games and {busy['builds']} compilers running" if loaded
                                      else ""), level="warn" if loaded else "fail")


def close_window(p):
    """Alt+F4 / the X button: WM_CLOSE to the game's window."""
    g = p.game()
    return fight_flow_test.close_windows(g.proc.pid) if g is not None and g.proc is not None else 0


def kill_game(p):
    """The game dies (TerminateProcess, like a crash or the task manager): exit code 1."""
    g = p.game()
    if g is not None and g.proc is not None and g.proc.poll() is None:
        g.proc.kill()
        return True
    return False


def fight_started(p, mid):
    return bool(p.matches.get(mid, {}).get("fight_at"))


def wait_fight(ctx, mid, players, timeout=150):
    return ctx.wait(lambda: all(fight_started(p, mid) for p in players), timeout, f"{mid}: FIGHT START on both PCs")


def log_has(p, pattern, mid=None):
    rx = re.compile(pattern)
    lines = p.log_segment(mid) if mid else _whole(p)
    return any(rx.search(ln) for ln in lines)


def _whole(p):
    out = []
    for g in p.games:
        try:
            with open(g.log_path, encoding="utf-8", errors="replace") as f:
                out += f.read().splitlines()
        except (OSError, TypeError):
            pass
    return out


def profile(ctx, p, name=None):
    box = p.call(p.client.profile, name, 20)
    ctx.wait(lambda: box, 15, f"{p.name}: profile {name or 'self'}")
    return box.get("ok")


def server_says(ctx, pattern):
    return re.search(pattern, ctx.server.log_text()) is not None


def game_exit_code(p, idx=-1, timeout=15.0):
    g = p.games[idx] if p.games else None
    if g is None:
        return None
    t_end = time.time() + timeout
    while g.proc.poll() is None and time.time() < t_end:
        time.sleep(0.1)
    return g.proc.poll()


__all__ = [n for n in dir() if not n.startswith("_")] + ["log", "os"]
