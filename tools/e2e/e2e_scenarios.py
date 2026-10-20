"""The scenarios. Each one gets a fresh lobby server (own database, local ports), its own players and
games, and records checks (PASS/FAIL, warnings) and evidence lines.

    @scenario(name, group, game=True|False, suites=(...), desc="...")

game=False scenarios use no game or lobby/tools/stub_game.py (seconds per match); game=True ones play
real matches with t5dr.exe (about a minute each with one round).
"""
import getpass
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import zipfile

from e2e_flows import (accept, close_window, fight_started, found_both, fps_check, game_exit_code, kill_game, latest,
                   leave, log_has, login, match_row, parse_segment, profile, queue_match, rematch,
                   server_says, started_both, wait_fight, wait_results, STUB_MATCH_SECONDS)
import core                                  # launcher/core.py (on the path through e2e_harness)
from e2e_harness import Abort, Skip

SCENARIOS = []


class Scenario:
    def __init__(self, fn, name, group, game, suites, desc, needs):
        self.fn, self.name, self.group, self.game, self.suites, self.desc, self.needs = (fn, name, group, game, suites,
                                                                                         desc, needs)


def scenario(name, group, game=False, suites=("full",), desc="", needs=None):
    def deco(fn):
        SCENARIOS.append(Scenario(fn, name, group, game, tuple(suites) + ("full",) if "full" not in suites else
                                  tuple(suites), desc, needs))
        return fn
    return deco


# Server settings: real-game scenarios play one round (T5L_ROUNDS, --rounds), stub ones are instant.
def game_server(ctx, **extra):
    env = {"T5L_ROUNDS": ctx.run.rounds, "T5L_MIN_MATCH_SECONDS": 10, "T5L_RESULT_TIMEOUT": 40,
           "T5L_RECONNECT_GRACE": 30, "T5L_PAIR_COOLDOWN": 0}
    env.update(extra)
    return ctx.start_server(**env)


def stub_server(ctx, **extra):
    env = {"T5L_MIN_MATCH_SECONDS": 0, "T5L_RESULT_TIMEOUT": 10, "T5L_RECONNECT_GRACE": 10, "T5L_PAIR_COOLDOWN": 0}
    env.update(extra)
    return ctx.start_server(**env)


def features():
    """Optional features of the lobby in this tree (the scenarios for unmerged branches look here)."""
    try:
        from t5lobby.server import lobby as srv
        return set(srv.FEATURES)
    except Exception:          # noqa: BLE001
        return set()


def other_build(p):
    from t5lobby.buildid import BuildInfo
    b, _err = p.tab._build_info()
    return BuildInfo(b.elf_sha1, "e2e-other-build", "e2e-other")


# ============================================================================== 1. accounts and login
@scenario("accounts_login", "1 accounts", suites=("quick", "lobby"),
          desc="register, saved login after a launcher restart, log out (keep / forget), wrong password, guest, name rules")
def accounts_login(ctx):
    stub_server(ctx)
    pw = "alice-pass-1"
    a = ctx.player("E2E Alice", kind="stub", password=pw)
    login(ctx, a, "register")
    me = a.me or {}
    ctx.check("register: logged in with an account", me.get("guest") is False, f"me {me.get('name')} guest {me.get('guest')}")
    ctx.check("register: 8 recovery codes shown once", len(a.codes) == 1 and len(a.codes[0]) == 8, f"{len(a.codes)} window(s)")
    ctx.wait(lambda: a.action_on("ranked"), 5, "account: Ranked match button enabled")
    saved = a.tab._saved_session()
    cfg_text = open(a.tab.cfg_path, encoding="utf-8").read()
    ctx.check("remember me: a login token is saved, never the password",
              bool(saved and saved.get("token")) and pw not in cfg_text, f"saved {bool(saved)}")
    a.logout(forget=False)
    ctx.wait(lambda: a.tab.client is None, 10, "log out")
    ctx.check("log out (keep the saved login): token still saved", a.tab._saved_session() is not None)
    # the launcher starts again: a new Online tab on the same per-user folder logs in by itself
    a2 = ctx.player("E2E Alice", kind="stub", password=pw, tag="restart", user_dir=a.user_dir)
    a2.tab.try_saved_login()
    ctx.wait(lambda: a2.logged_in(), 15, "launcher restart: logged in with the saved login")
    ctx.check("status says it used the saved login", a2.saw_status("saved login"), a2.status_text())
    token = (a2.tab._saved_session() or {}).get("token")
    a2.logout(forget=True)
    ctx.wait(lambda: a2.tab.client is None, 10, "log out and forget")
    ctx.check("forget: the token is gone from online.json", a2.tab._saved_session() is None)
    ctx.sleep(1.0)
    # the forgotten token must be dead on the server too
    from t5lobby.client import LobbyClient
    from t5lobby import proto
    from t5lobby.proto import LobbyError
    b, _ = a2.tab._build_info()
    c = LobbyClient(ctx.server.addr, b)
    try:
        c.connect()
        try:
            c.login_session(token)
            ctx.check("forgotten token refused by the server", False, "it still logs in")
        except LobbyError as e:
            ctx.check("forgotten token refused by the server", e.code == proto.E_AUTH, f"{e.code}: {e.msg}")
    finally:
        c.close()
    # wrong password, then the right one
    a3 = ctx.player("E2E Alice", kind="stub", password=pw, tag="pw", user_dir=a.user_dir)
    t = time.time()
    a3.login("wrong-password-9")
    ctx.wait(lambda: a3.saw_status("wrong name or password", t), 10, "wrong password: refused with a clear message")
    ctx.check("wrong password: not logged in", not a3.logged_in())
    a3.login()
    ctx.wait(lambda: a3.logged_in(), 15, "right password: logged in")
    # a second account with the same name is refused
    x = ctx.player("e2e alice", kind="stub", password="other-pass-2", tag="dup")
    t = time.time()
    x.register()
    ctx.wait(lambda: x.saw_status("taken|online", t), 10, "register a taken name: refused")
    ctx.check("taken name: not logged in", not x.logged_in())
    # guests
    g = ctx.player("E2E Guest", kind="stub")
    login(ctx, g, "guest")
    ctx.check("guest: logged in as a guest", (g.me or {}).get("guest") is True)
    ctx.check("guest: Ranked match disabled, Quick match enabled", not g.action_on("ranked") and g.action_on("quick"))
    g2 = ctx.player("E2E ALICE", kind="stub", tag="guestname")
    t = time.time()
    g2.login_guest()
    ctx.wait(lambda: g2.saw_status("belongs to an account|online", t), 10, "guest with an account's name: refused")
    g3 = ctx.player("Admin", kind="stub")
    t = time.time()
    g3.login_guest()
    ctx.wait(lambda: g3.saw_status("reserved", t), 10, "reserved name (Admin): refused")
    ctx.note(f"accounts: {a.name} registered, saved-login restart, forget, wrong password, guest {g.name}")


@scenario("accounts_same_account", "1 accounts", suites=("quick", "lobby"),
          desc="the same account logged in on two PCs: idle and during a running match (stub games)")
def accounts_same_account(ctx):
    # (a lone report that favours its sender waits until T5L_MAX_MATCH_SECONDS after the start -- lobby-hardening;
    # 40 s here instead of 420 so the take-over's outcome comes within the scenario)
    stub_server(ctx, T5L_MAX_MATCH_SECONDS=40)
    pw = "dana-pass-1"
    d1 = ctx.player("E2E Dana", kind="stub", password=pw, tag="pc1")
    login(ctx, d1, "register")
    d2 = ctx.player("E2E Dana", kind="stub", password=pw, tag="pc2")
    t = time.time()
    login(ctx, d2, "account")
    ctx.wait(lambda: d1.events_of("kicked", t), 10, "PC 1 is told: logged in from another place")
    ctx.wait(lambda: d1.tab.client is None, 10, "PC 1's tab shows it is no longer connected")
    ctx.check("PC 1 status names the reason", d1.saw_status("another place", t), d1.status_text())
    ctx.sleep(4)
    ctx.check("PC 1 does not reconnect and fight for the session", d1.tab.client is None and not d1.events_of("reconnected"))
    ctx.check("PC 2 stays logged in", d2.logged_in())
    # during a match: the match moves to the new connection
    e = ctx.player("E2E Eve", kind="stub", env={"T5_STUB_SECONDS": 6})
    login(ctx, e, "guest")
    d2.app.settings["extra_env"] += "\nT5_STUB_SECONDS=6"
    mid = queue_match(ctx, d2, e, "quick")
    ctx.wait(lambda: d2.game_running(), 20, "PC 2's game runs")
    d3 = ctx.player("E2E Dana", kind="stub", password=pw, tag="pc3")
    t = time.time()
    login(ctx, d3, "account")
    ctx.wait(lambda: d2.events_of("kicked", t), 10, "PC 2 is told: logged in from another place")
    ctx.wait(lambda: any(ev.get("match") == mid and ev.get("resumed") for ev in d3.events_of("match_start", t)), 10,
             "PC 3 takes over the running match (match_start, resumed)")
    ctx.check("PC 3's lobby status is 'playing'", (d3.me or {}).get("status") == "playing", (d3.me or {}).get("status"))
    ok = ctx.wait(lambda: e.matches.get(mid, {}).get("status") and d3.matches.get(mid, {}).get("status"), 120,
                  "the match is settled on the opponent's and on PC 3's side")
    if ok:
        ctx.note(f"take-over mid-match: settled as {e.matches[mid].get('status')} ({e.matches[mid].get('reason')}), "
                 f"blame {e.matches[mid].get('blame')} -- PC 3 has no game, PC 2's game finished it but PC 2 was kicked")
    ctx.check("server process still runs", ctx.server.proc.poll() is None)


@scenario("server_restart", "1 accounts", suites=("quick", "lobby"),
          desc="lobby server restarts while players are in the lobby and while a match runs; log in again, play on")
def server_restart(ctx):
    stub_server(ctx)
    a = ctx.player("E2E Frank", kind="stub", password="frank-pass-1", env={"T5_STUB_SECONDS": 8})
    b = ctx.player("E2E Gina", kind="stub", env={"T5_STUB_SECONDS": 8})
    login(ctx, a, "register")
    login(ctx, b, "guest")
    t = time.time()
    ctx.server.restart(down_seconds=2.0)
    ctx.note("server restarted (idle lobby)")
    ctx.wait(lambda: a.events_of("reconnecting", t) and b.events_of("reconnecting", t), 15,
             "both clients notice and try to reconnect")
    ctx.wait(lambda: a.tab.client is None and b.tab.client is None, 90,
             "the restarted server forgot the sessions: both tabs show 'not connected'")
    ctx.check("status says the lobby connection was lost", a.saw_status("Lost the lobby connection", t), a.status_text())
    a.tab.do_login("session", session=(a.tab._saved_session() or {}).get("token"))
    ctx.wait(lambda: a.logged_in(), 15, "account: logged in again with the saved login after the restart")
    login(ctx, b, "guest")
    # a match while the server restarts
    mid = queue_match(ctx, a, b, "quick")
    ctx.wait(lambda: a.game_running() and b.game_running(), 20, "both stub games run")
    t = time.time()
    ctx.server.restart(down_seconds=2.0)
    ctx.note(f"server restarted during match {mid}")
    ctx.wait(lambda: a.tab.client is None and b.tab.client is None, 90, "both lose the lobby after the restart")
    a.tab.do_login("session", session=(a.tab._saved_session() or {}).get("token"))
    login(ctx, b, "guest")
    ctx.wait(lambda: a.logged_in() and b.logged_in(), 20, "both back in the lobby")
    ctx.sleep(10)   # the stub match goes on; its result has no match on the new server
    ctx.check("the tabs survived the lost match (still logged in)", a.logged_in() and b.logged_in())
    ctx.note(f"after the restart: {a.name} status {a.status_text()!r}; {b.name} status {b.status_text()!r}")
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 30, "Quick match available again on both")
    mid2 = queue_match(ctx, a, b, "quick")
    ok = ctx.wait(lambda: a.matches.get(mid2, {}).get("status") and b.matches.get(mid2, {}).get("status"),
                  150, "the next match after the restart gets a result")
    if ok:
        ctx.check("next match confirmed", a.matches[mid2]["status"] == "confirmed", a.matches[mid2].get("status"))


# ============================================================================== 2. quick match
@scenario("lobby_drop", "1 accounts", suites=("quick", "lobby"),
          desc="the lobby connection drops mid-match: back within the grace time the match carries on and counts; "
               "away for good it is a forfeit for the one who dropped")
def lobby_drop(ctx):
    stub_server(ctx, T5L_RECONNECT_GRACE=8, T5L_PLACEMENT=1)
    # (the old per-game protocol: this is about the lobby connection, not about sets -- bo3_* cover those)
    a = ctx.player("E2E Ida", kind="stub", password="ida-pass-1", env={"T5_STUB_SECONDS": 12}, sets=False)
    b = ctx.player("E2E Jan", kind="stub", password="jan-pass-1", env={"T5_STUB_SECONDS": 12}, sets=False)
    login(ctx, a, "register")
    login(ctx, b, "register")
    mid = queue_match(ctx, a, b, "ranked")
    ctx.wait(lambda: a.game_running() and b.game_running(), 20, "both games run")
    t = time.time()
    a.client._loop.call_soon_threadsafe(a.client._writer.transport.abort)      # the line drops (no FIN, no logout)
    ctx.wait(lambda: a.events_of("reconnected", t), 30, "the launcher resumes the session by itself")
    ctx.wait(lambda: any(ev.get("code") == "opponent_dropped" for ev in b.events_of("notice", t)), 10,
             "the opponent is told and waits", fail=False)
    wait_results(ctx, mid, (a, b), 120)
    ctx.check("back in time: the match counts (confirmed, rated)", a.matches[mid].get("status") == "confirmed" and
              a.matches[mid].get("rating"), f"{a.matches[mid].get('status')} {a.matches[mid].get('reason')}")
    for p in (a, b):
        leave(ctx, p)
    ctx.wait(lambda: a.action_on("ranked") and b.action_on("ranked"), 30, "both free again")
    # away for good: the dropped launcher does not come back (reconnect off), the grace time runs out
    mid2 = queue_match(ctx, a, b, "ranked")
    ctx.wait(lambda: a.game_running() and b.game_running(), 20, "both games run (match 2)")
    ctx.sleep(2)
    a.client.reconnect_window = 0
    a.client._loop.call_soon_threadsafe(a.client._writer.transport.abort)
    ok = ctx.wait(lambda: b.matches.get(mid2, {}).get("status"), 150, "the match is settled without the dropped player")
    if ok:
        mb = b.matches[mid2]
        ctx.check("away for good: forfeit for the dropped player (or the result the games reached)",
                  (mb.get("status") == "forfeit" and mb.get("reason") == "disconnect" and mb.get("blame") == "opponent")
                  or mb.get("status") in ("onesided", "confirmed"),
                  f"{mb.get('status')} {mb.get('reason')} blame {mb.get('blame')}")


@scenario("quick_match", "2 quick match", game=True, suites=("game",),
          desc="queue, blind found (ping only), accept/accept, the reveal, a real match, confirmed, Leave")
def quick_match(ctx):
    game_server(ctx)
    a = ctx.player("E2E Ann")
    b = ctx.player("E2E Ben")
    login(ctx, a)
    login(ctx, b)
    t = time.time()
    a.press("quick")
    ctx.sleep(0.3)
    b.press("quick")
    mid = found_both(ctx, a, b, t)
    ma = a.matches[mid]
    ctx.check("found: blind (no opponent name, no side)", ma.get("blind") and ma.get("opponent_at_found") is None,
              f"blind {ma.get('blind')}, opponent {ma.get('opponent_at_found')}")
    ctx.check("found: the ping estimate is shown", "ping" in a.tab.bar_text.get().lower() and "E2E Ben" not in a.tab.bar_text.get(),
              a.tab.bar_text.get())
    accept(ctx, a, mid)
    ctx.sleep(1.0)
    ctx.check("one accepted: still blind for both", "revealed" not in a.matches[mid] and "revealed" not in b.matches[mid])
    ctx.wait(lambda: b.saw_status("opponent accepted", t), 5, "the other player is told 'Your opponent accepted'", fail=False)
    accept(ctx, b, mid)
    ctx.wait(lambda: a.matches[mid].get("opponent") == "E2E Ben" and b.matches[mid].get("opponent") == "E2E Ann", 10,
             "both accepted: match_reveal names the opponent")
    started_both(ctx, a, b, mid)
    ctx.check("match line shows the opponent and the ping", "vs E2E Ben" in a.tab.match_var.get(), a.tab.match_var.get())
    wait_fight(ctx, mid, (a, b))
    wait_results(ctx, mid, (a, b))
    row = match_row(ctx, mid, (a, b), "confirmed", "quick match")
    fps_check(ctx, row, (a, b))
    ctx.check("casual: no rating change", a.matches[mid].get("rating") is None and not a.matches[mid].get("ranked"))
    ctx.wait(lambda: a.bar_button("Rematch") and a.bar_button("Leave") and a.bar_button("Block"), 10,
             "result bar: Rematch, Leave, Block")
    t = time.time()
    leave(ctx, a)
    ctx.wait(lambda: b.events_of("set_end", t) or b.events_of("rematch", t), 10, "the opponent is told the set ended")
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 15, "both can search again")


@scenario("quick_decline", "2 quick match", suites=("quick", "lobby"),
          desc="one side declines the found match: the other goes back into the queue and never learns the name")
def quick_decline(ctx):
    stub_server(ctx, T5L_READY_TIMEOUT=8)
    a = ctx.player("E2E Cleo", kind="stub")
    b = ctx.player("E2E Dirk", kind="stub")
    login(ctx, a)
    login(ctx, b)
    t = time.time()
    a.press("quick")
    ctx.sleep(0.3)
    b.press("quick")
    mid = found_both(ctx, a, b, t)
    accept(ctx, a, mid)
    ctx.wait(lambda: b.bar_button("Decline") is not None, 10, "Decline button")
    b.click("Decline")
    ctx.wait(lambda: a.matches[mid].get("cancel_reason") == "declined", 10, "the accepting player sees 'declined'")
    ctx.wait(lambda: (a.me or {}).get("status") == "queue", 10, "the accepting player is back in the queue")
    ctx.check("the decliner is idle", ctx.wait(lambda: (b.me or {}).get("status") == "idle", 10))
    ctx.check("the opponent's name was never sent", "revealed" not in a.matches[mid] and
              not any("E2E Dirk" in json.dumps(ev, default=str) for _t, ev in a.events if ev.get("match") == mid))
    ctx.check("no game was started", not a.games and not b.games)
    a.press("cancel")
    ctx.wait(lambda: (a.me or {}).get("status") == "idle", 10, "Stop searching")


@scenario("quick_timeout", "2 quick match", suites=("quick", "lobby"),
          desc="nobody / only one side accepts within the ready time")
def quick_timeout(ctx):
    stub_server(ctx, T5L_READY_TIMEOUT=6)
    a = ctx.player("E2E Hugo", kind="stub")
    b = ctx.player("E2E Iris", kind="stub")
    login(ctx, a)
    login(ctx, b)
    t = time.time()
    a.press("quick")
    ctx.sleep(0.3)
    b.press("quick")
    mid = found_both(ctx, a, b, t)
    accept(ctx, a, mid)
    ctx.wait(lambda: a.matches[mid].get("cancel_reason") == "ready_timeout", 15, "one accepted: cancelled after 6 s")
    ctx.wait(lambda: (a.me or {}).get("status") == "queue", 10, "the one who accepted keeps searching")
    ctx.wait(lambda: (b.me or {}).get("status") == "idle", 10, "the silent one is out of the queue")
    ctx.check("bar gone, status says nobody accepted in time", b.saw_status("in time", t), b.status_text())
    # the silent one queues again; this time nobody accepts
    t = time.time()
    b.press("quick")
    mid2 = found_both(ctx, a, b, t)
    ctx.wait(lambda: a.matches[mid2].get("cancel_reason") == "ready_timeout", 15, "nobody accepted: cancelled")
    ctx.wait(lambda: (a.me or {}).get("status") == "idle" and (b.me or {}).get("status") == "idle", 10,
             "nobody accepted: both out of the queue")


# ============================================================================== 3. ranked
# Ranked is a best-of-3 set since ranked-sets (docs/RANKED.md "Ranked sets"): the next game starts by itself after
# a countdown (no rematch vote), the characters stay locked, the rating changes once at the end of the set, and
# leaving mid-set loses it. The real-game set scenarios use planned winners: the planned winner's player presses
# attacks live while the fight runs, the other one stands still (ctx.plan, bot players; lobby/tools/set_session.py).
SET_NEXT = 6.0


def _set_of(p, mid):
    return (p.matches.get(mid) or {}).get("set") or {}


def _set_game(ctx, a, b, mid, label, timeout=240):
    """Play one game of a ranked set to its result; no game of a set changes a rating on its own."""
    wait_fight(ctx, mid, (a, b), timeout=150)
    wait_results(ctx, mid, (a, b), timeout)
    return match_row(ctx, mid, (a, b), "confirmed", label)


def _rated_once(ctx, a, b, mids, ends, label):
    """No game but the deciding one carries a rating change; the deciding game's change is the set's (set_end)."""
    for p, e in zip((a, b), ends):
        early = [(p.matches.get(m) or {}).get("rating") for m in mids[:-1]]
        ctx.check(f"{label}: {p.name}: no rating change after the games before the last", all(r is None for r in early),
                  early)
        last = ((p.matches.get(mids[-1]) or {}).get("rating") or {}).get("delta")
        whole = (e.get("rating") or {}).get("delta")
        ctx.check(f"{label}: {p.name}: the one change comes with the deciding game and is the set's",
                  last is not None and whole is not None and abs(last - whole) < 0.01, f"game {last}, set {whole}")


def _next_set_game(ctx, a, b, mid, label):
    """Between two games: a countdown and "Leave set", no rematch vote; the next game starts by itself."""
    t_res = max(p.matches[mid].get("result") or 0 for p in (a, b))
    ctx.wait(lambda: a.bar_button("Leave set") is not None and b.bar_button("Leave set") is not None, 10,
             f"{label}: the set bar counts down and offers Leave set")
    ctx.check(f"{label}: no rematch vote between two games of a set",
              a.bar_button("Rematch") is None and b.bar_button("Rematch") is None, [a.bar_labels(), b.bar_labels()])
    ctx.check(f"{label}: the countdown is shown", "starts in" in a.tab.bar_text.get() or "s" in a.tab.bar_text.get(),
              a.tab.bar_text.get())
    since = t_res - 0.5
    ok = ctx.wait(lambda: latest(a, "match_start", since) and latest(b, "match_start", since), 40,
                  f"{label}: the next game starts by itself")
    if not ok:
        raise Abort("the set's next game did not start")
    nxt = latest(a, "match_start", since)["match"]
    dt = a.matches[nxt]["started"] - t_res
    ctx.check(f"{label}: started {dt:.1f} s after the result (countdown {SET_NEXT:g} s)", SET_NEXT - 1.0 <= dt <= SET_NEXT + 12,
              f"{dt:.1f} s")
    ctx.check(f"{label}: continues in the running games", a.matches[nxt].get("cont"), a.matches[nxt].get("cont"))
    if not ((a.matches[mid].get("fight") or {}).get("pick") and getattr(ctx, "manual_pick", False)):
        # (game 1 picked in the game by the scenario: the lock is what it picked, not the lobby's fallback --
        # cs_ranked_lock checks that from both games' logs)
        ctx.check(f"{label}: the same characters and sides", _picks(a, b, nxt) == _picks(a, b, mid),
                  f"{_picks(a, b, mid)} -> {_picks(a, b, nxt)}")
    return nxt


def _play_set(ctx, a, b, mid, plan, label):
    """Play a ranked set to its end following plan ("AA", "ABA", ...). Returns (set_end of a, of b, game ids)."""
    t0 = min(p.matches.get(mid, {}).get("started") or time.time() for p in (a, b))   # (not before this set began: the last set's set_end can be a moment old)
    mids = [mid]
    for k in range(3):
        _set_game(ctx, a, b, mid, f"{label} game {k + 1}")
        s = _set_of(a, mid)
        ctx.note(f"{label} game {k + 1}: set {s.get('wins')} state {s.get('state')}")
        if a.events_of("set_end", t0) or s.get("state") == "ended" or not s.get("next"):
            break
        mid = _next_set_game(ctx, a, b, mid, f"{label} game {k + 2}")
        mids.append(mid)
    ctx.wait(lambda: a.events_of("set_end", t0) and b.events_of("set_end", t0), 20, f"{label}: the set ends")
    ea, eb = (latest(p, "set_end", t0) or {} for p in (a, b))
    _rated_once(ctx, a, b, mids, (ea, eb), label)
    want = [plan.count("A"), plan.count("B")]
    ctx.check(f"{label}: set decided as planned ({want[0]}-{want[1]}) after {len(plan)} games",
              ea.get("wins") == want and ea.get("games") == len(plan) and ea.get("result") == ("win" if want[0] > want[1]
                                                                                              else "loss"),
              f"{a.name}: {ea.get('result')} {ea.get('wins')} in {ea.get('games')} game(s), status {ea.get('status')}")
    for p, e in ((a, ea), (b, eb)):
        r = e.get("rating") or {}
        ctx.check(f"{label}: {p.name}'s rating changed once, at the end of the set",
                  e.get("rated") and r.get("delta") not in (None, 0), f"{r.get('before', {}).get('r')} -> "
                  f"{r.get('after', {}).get('r')} ({r.get('delta')}), rank {(r.get('rank_after') or {}).get('rank')} "
                  f"{r.get('event') or ''}")
    return ea, eb, mids


@scenario("ranked_set", "3 ranked", game=True, suites=("game",),
          desc="ranked best-of-3 set (2-1): game 1, the next games after a 6 s countdown (no vote), characters locked, "
               "one rating change at the end; Rematch = a new set (2-0); pair cooldown; leaving mid-set loses the set")
def ranked_set(ctx):
    game_server(ctx, T5L_PLACEMENT=1, T5L_PAIR_COOLDOWN=25)
    a = ctx.player("E2E Rin", password="rin-pass-1", char="jin", bot=True)
    b = ctx.player("E2E Kai", password="kai-pass-1", char="lili", bot=True)
    login(ctx, a, "register")
    login(ctx, b, "register")
    a.set_char("jin")
    b.set_char("lili")
    ctx.plan = (a, b, ["ABA", "AA", "A"])
    ctx.sleep(1)
    mid = queue_match(ctx, a, b, "ranked")
    s = _set_of(a, mid)
    ctx.check("a ranked queue match is a rated best-of-3 set, characters locked",
              s.get("rated") and s.get("best_of") == 3 and s.get("locked"), s)
    ctx.check("set 1 fighters are the picks", _picks(a, b, mid) == {"E2E Rin": "jin", "E2E Kai": "lili"}, _picks(a, b, mid))
    ctx.wait(lambda: str(a.tab.char_cb.cget("state")) == "disabled", 10, "character box greyed out in the set")
    t = time.time()
    a.call(a.client.set_char, "king")
    ctx.wait(lambda: a.saw_status("locked", t), 10, "changing the character mid-set is refused by the server")
    ea, _eb, mids = _play_set(ctx, a, b, mid, "ABA", "set 1")
    prof = profile(ctx, a) or {}
    ctx.check("profile: one ranked set counted (not three games)", prof.get("ranked_games") == 1,
              f"ranked_games {prof.get('ranked_games')}, record {prof.get('record')}, rank {prof.get('rank')}")
    # Rematch after a set = a new set
    t = time.time()
    ctx.wait(lambda: a.bar_button("Rematch") is not None and b.bar_button("Rematch") is not None, 20,
             "after the set: Rematch (a new set)")
    mid2 = rematch(ctx, a, b)
    ctx.check("the rematch is a new set", _set_of(a, mid2).get("id") != _set_of(a, mids[0]).get("id"),
              f"{_set_of(a, mids[0]).get('id')} -> {_set_of(a, mid2).get('id')}")
    _play_set(ctx, a, b, mid2, "AA", "set 2 (rematch)")
    prof = profile(ctx, a) or {}
    ctx.check("profile: two ranked sets", prof.get("ranked_games") == 2, f"ranked_games {prof.get('ranked_games')}")
    t_last = time.time()
    leave(ctx, a)
    ctx.wait(lambda: str(a.tab.char_cb.cget("state")) == "readonly", 15, "character unlocked after the set")
    a.set_char("king")
    ctx.wait(lambda: a.action_on("ranked") and b.action_on("ranked"), 15, "Ranked match available again")
    t = time.time()
    a.press("ranked")
    ctx.sleep(0.3)
    b.press("ranked")
    mid3 = found_both(ctx, a, b, t, timeout=60)
    ctx.check("pair cooldown: matched again only after 25 s", time.time() - t_last >= 23, f"{time.time() - t_last:.1f} s")
    accept(ctx, a, mid3)
    accept(ctx, b, mid3)
    started_both(ctx, a, b, mid3)
    ctx.check("set 3: the new character", _picks(a, b, mid3).get("E2E Rin") == "king", _picks(a, b, mid3))
    _set_game(ctx, a, b, mid3, "set 3 game 1")
    # leaving between two games loses the set
    ctx.wait(lambda: b.bar_button("Leave set") is not None, 10, "set 3: Leave set offered between the games")
    t = time.time()
    b.answer_yes_no = True
    b.click("Leave set")
    ctx.wait(lambda: a.events_of("set_end", t) and b.events_of("set_end", t), 20, "set 3: Leave set ends the set")
    eb = latest(b, "set_end", t) or {}
    ctx.check("leaving mid-set loses the set (rating changes once)", eb.get("result") == "loss" and eb.get("status") == "forfeit"
              and (eb.get("rating") or {}).get("delta", 0) < 0, f"{eb.get('result')} {eb.get('status')} {eb.get('wins')}")
    ctx.check("no next game after leaving", not latest(a, "match_start", t), "")
    prof = profile(ctx, a) or {}
    ctx.note(f"after three sets: {a.name} {prof.get('rank')} {prof.get('rating')}, record {prof.get('record')}, "
             f"sets {len(prof.get('sets') or [])}")


def _picks(a, b, mid):
    """{player name: fighter key} of a started match (P1 = host = slot 0)."""
    m = a.matches.get(mid, {})
    f = m.get("fight") or {}
    if m.get("slot") is None:
        return {}
    mine, theirs = (f.get("p1"), f.get("p2")) if m["slot"] == 0 else (f.get("p2"), f.get("p1"))
    return {a.name: mine, b.name: theirs}


@scenario("ranked_per_game", "3 ranked", game=True, suites=("game",),
          desc='the old protocol ("sets": false in online.json, a 1.0.0 launcher): every ranked game rated, a rematch '
               "vote between games, characters locked")
def ranked_per_game(ctx):
    game_server(ctx, T5L_PLACEMENT=1)
    a = ctx.player("E2E Old1", password="old1-pass-1", char="paul", sets=False)
    b = ctx.player("E2E Old2", password="old2-pass-1", char="nina", sets=False)
    login(ctx, a, "register")
    login(ctx, b, "register")
    a.set_char("paul")
    b.set_char("nina")
    mid = queue_match(ctx, a, b, "ranked")
    ctx.check("not a rated set (old protocol)", not _set_of(a, mid).get("rated"), _set_of(a, mid))
    rating = {}
    for k in range(2):
        wait_fight(ctx, mid, (a, b))
        wait_results(ctx, mid, (a, b))
        match_row(ctx, mid, (a, b), "confirmed", f"ranked game {k + 1} (per game)")
        for p in (a, b):
            r = p.matches[mid].get("rating") or {}
            before = (r.get("before") or {}).get("r")
            ctx.check(f"game {k + 1}: {p.name}'s rating moved after this game", r.get("delta") not in (None, 0) and
                      (p.name not in rating or abs(before - rating[p.name]) < 1.0), f"{before} -> {(r.get('after') or {}).get('r')}")
            rating[p.name] = (r.get("after") or {}).get("r")
        if k == 0:
            ctx.check("a rematch vote, not a countdown", ctx.wait(lambda: a.bar_button("Rematch") is not None, 15) and
                      a.bar_button("Leave set") is None, a.bar_labels())
            mid = rematch(ctx, a, b)
            ctx.check("rematch: same characters (locked)", _picks(a, b, mid) == {"E2E Old1": "paul", "E2E Old2": "nina"},
                      _picks(a, b, mid))


@scenario("ranked_pair_cap", "3 ranked", suites=("quick", "lobby"),
          desc="anti win-trading cap (old protocol, per game): the 3rd ranked game of a pair within 24 h (cap 2) is "
               "casual, both told")
def ranked_pair_cap(ctx):
    stub_server(ctx, T5L_PAIR_CAP=2, T5L_PLACEMENT=1)
    a = ctx.player("E2E Jon", kind="stub", password="jon-pass-1", sets=False)
    b = ctx.player("E2E Liv", kind="stub", password="liv-pass-1", sets=False)
    login(ctx, a, "register")
    login(ctx, b, "register")
    mid = queue_match(ctx, a, b, "ranked")
    t = time.time()
    for k in range(3):
        wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
        m = a.matches[mid]
        if k < 2:
            ctx.check(f"game {k + 1}: ranked, rating moved", m.get("ranked") and m.get("rating"), f"ranked {m.get('ranked')}")
            t = time.time()
            mid = rematch(ctx, a, b)
        else:
            ctx.check("game 3: played as casual (pair cap)", not m.get("ranked") and not m.get("rating"),
                      f"ranked {m.get('ranked')}")
            ctx.check("both were told why", any(ev.get("code") == "pair_cap" for ev in a.events_of("notice", t)) and
                      any(ev.get("code") == "pair_cap" for ev in b.events_of("notice", t)))


@scenario("ranked_quit_mid_set", "3 ranked", game=True, suites=("game",),
          desc="ranked set: game 1 won by A, in game 2 B closes the game window (Alt+F4) -> B loses the set at once "
               "(forfeit), the rating changes once")
def ranked_quit_mid_set(ctx):
    game_server(ctx, T5L_PLACEMENT=1)
    a = ctx.player("E2E Max", password="max-pass-1", char="paul", bot=True)
    b = ctx.player("E2E Noa", password="noa-pass-1", char="nina", bot=True)
    login(ctx, a, "register")
    login(ctx, b, "register")
    a.set_char("paul")
    b.set_char("nina")
    ctx.plan = (a, b, ["AB"])
    t0 = time.time()
    mid = queue_match(ctx, a, b, "ranked")
    _set_game(ctx, a, b, mid, "game 1")
    mid = _next_set_game(ctx, a, b, mid, "game 2")
    wait_fight(ctx, mid, (a, b))
    ctx.sleep(10)
    n = close_window(b)
    ctx.note(f"game 2: WM_CLOSE to {b.name}'s game window ({n} window(s)), Alt+F4")
    ctx.wait(lambda: not b.game_running(), 20, "the closed game ends itself")
    ctx.check("closed game: exit code 7 (quit)", game_exit_code(b) == 7, f"exit code {game_exit_code(b)}")
    ctx.wait(lambda: a.events_of("set_end", t0) and b.events_of("set_end", t0), 60, "the set ends at once")
    eb, ea = latest(b, "set_end", t0) or {}, latest(a, "set_end", t0) or {}
    ctx.check("the quitter lost the set (forfeit), whatever the score", eb.get("result") == "loss" and
              ea.get("result") == "win" and eb.get("status") == "forfeit",
              f"{b.name}: {eb.get('result')} {eb.get('status')} {eb.get('wins')}; {a.name}: {ea.get('result')}")
    for p, e, sign in ((a, ea, 1), (b, eb, -1)):
        d = (e.get("rating") or {}).get("delta")
        ctx.check(f"{p.name}: one rating change for the set", d is not None and d * sign > 0, d)
    ctx.check("game 2 itself is a forfeit with the quitter blamed", b.matches.get(mid, {}).get("blame") == "you",
              f"{b.matches.get(mid, {}).get('status')} {b.matches.get(mid, {}).get('reason')} blame {b.matches.get(mid, {}).get('blame')}")
    hist = [h for m_, h in b.tab.driver.history if m_ == mid]
    ctx.check("the quitter's launcher reported 'quit' without asking", hist and hist[-1].get("source") == "quit" and
              not any(n_.get("kind") == "ask_result" for _t, n_ in b.notes), hist)


@scenario("ranked_room", "3 ranked", game=True, suites=("game",),
          desc="a ranked room plays best-of-3 sets: create, join, ready, a 2-0 set, rated once")
def ranked_room(ctx):
    game_server(ctx, T5L_PLACEMENT=1)
    a = ctx.player("E2E Ola", password="ola-pass-1", char="asuka", bot=True)
    b = ctx.player("E2E Pim", password="pim-pass-1", char="law", bot=True)
    login(ctx, a, "register")
    login(ctx, b, "register")
    a.set_char("asuka")
    b.set_char("law")
    ctx.plan = (a, b, ["BB"])
    box = a.call(a.client.create_room, "E2E ranked room", True)
    ctx.wait(lambda: box, 10, "ranked room created")
    rid = (box.get("ok") or {}).get("id")
    ctx.check("the room is ranked", (box.get("ok") or {}).get("ranked") is True, box.get("ok"))
    ctx.wait(lambda: b.tab.tv_rooms.exists(rid), 10, "the room shows in the other player's list")
    t = time.time()
    b.tab.tv_rooms.selection_set(rid)
    b.press("join")
    mid = found_both(ctx, a, b, t)
    ctx.check("room match: ranked, a rated set, not blind", a.matches[mid].get("ranked") and
              _set_of(a, mid).get("rated") and not a.matches[mid].get("blind"), _set_of(a, mid))
    accept(ctx, a, mid)
    accept(ctx, b, mid)
    started_both(ctx, a, b, mid)
    _play_set(ctx, a, b, mid, "BB", "room set")


# ============================================================================== 4. rooms
@scenario("room_flow", "4 rooms", game=True, suites=("game",),
          desc="room: create, join, ready, match, Rematch, then Ready again (a new session), match, Rematch "
               "(the 1.0.0 hang), leave the room, the host leaves")
def room_flow(ctx):
    game_server(ctx)
    a = ctx.player("E2E Quinn", char="bryan")
    b = ctx.player("E2E Rosa", char="xiaoyu")
    login(ctx, a)
    login(ctx, b)
    a.set_char("bryan")
    b.set_char("xiaoyu")
    a.press("room")
    ctx.wait(lambda: (a.me or {}).get("status") == "room", 10, "Create room")
    ctx.wait(lambda: len(b.tab.tv_rooms.get_children()) == 1, 10, "the room is listed for the other player")
    rid = b.tab.tv_rooms.get_children()[0]
    t = time.time()
    b.tab.tv_rooms.selection_set(rid)
    b.press("join")
    mid = found_both(ctx, a, b, t)
    ctx.check("room match: ready check, opponent named", a.matches[mid].get("ready_check") and
              a.matches[mid].get("opponent_at_found") == "E2E Rosa")
    accept(ctx, a, mid)
    accept(ctx, b, mid)
    started_both(ctx, a, b, mid)
    labels = ["room match 1", "rematch (same session)", "Ready again (new session)", "rematch after Ready again"]
    for k, label in enumerate(labels):
        if k > 0:
            if k == 2:
                # "Ready again": no rematch; the room starts its next match (a new netplay session)
                leave(ctx, a)
                ctx.wait(lambda: (a.me or {}).get("status") == "room" and (b.me or {}).get("status") == "room", 15,
                         "after declining the rematch both are still in the room")
                t = time.time()
                a.call(a.client.rematch)
                mid = found_both(ctx, a, b, t)
                accept(ctx, a, mid)
                accept(ctx, b, mid)
                started_both(ctx, a, b, mid)
                ctx.check("Ready again: a new session (not continued)", not a.matches[mid].get("cont"))
            else:
                mid = rematch(ctx, a, b)
                ctx.check(f"{label}: continues in the running session", a.matches[mid].get("cont"))
        wait_fight(ctx, mid, (a, b), timeout=120)
        wait_results(ctx, mid, (a, b))
        row = match_row(ctx, mid, (a, b), "confirmed", label)
        fps_check(ctx, row, (a, b))
    leave(ctx, b)
    ctx.wait(lambda: a.action_on("leave") or (a.me or {}).get("status") == "room", 15, "both back in the room")
    b.press("leave") if b.action_on("leave") else None
    ctx.wait(lambda: (b.me or {}).get("status") == "idle", 10, "Leave room")
    ctx.wait(lambda: any(r for r in a.client.rooms if (r.get("owner") or {}).get("name") == "E2E Quinn"), 10,
             "the room stays with its host")
    a.press("leave")
    ctx.wait(lambda: not a.client.rooms, 10, "the host leaves the empty room: it is gone")


@scenario("room_leave", "4 rooms", suites=("quick", "lobby"),
          desc="rooms: the host leaves (ownership moves), the last one leaves (room gone), Leave room is off "
               "during the ready check, a declined room match keeps both in the room")
def room_leave(ctx):
    stub_server(ctx)
    a = ctx.player("E2E Sam", kind="stub")
    b = ctx.player("E2E Tia", kind="stub")
    login(ctx, a)
    login(ctx, b)
    a.press("room")
    ctx.wait(lambda: len(b.tab.tv_rooms.get_children()) == 1, 10, "room listed")
    rid = b.tab.tv_rooms.get_children()[0]
    t = time.time()
    b.tab.tv_rooms.selection_set(rid)
    b.press("join")
    mid = found_both(ctx, a, b, t)
    ctx.wait(lambda: b.bar_button("Decline") is not None, 10, "ready check bar")
    ctx.check("Leave room is disabled during the ready check", not b.action_on("leave") and not a.action_on("leave"))
    b.click("Decline")
    ctx.wait(lambda: a.matches[mid].get("cancel_reason") == "declined", 10, "declined room match cancelled")
    ctx.wait(lambda: (a.me or {}).get("status") == "room" and (b.me or {}).get("status") == "room", 10,
             "both stay in the room after a decline")
    # play one stub match, then the host leaves
    t = time.time()
    a.call(a.client.rematch)
    mid = found_both(ctx, a, b, t)
    accept(ctx, a, mid)
    accept(ctx, b, mid)
    wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
    ctx.check("room stub match confirmed", a.matches[mid].get("status") == "confirmed", a.matches[mid].get("status"))
    leave(ctx, a)
    ctx.wait(lambda: a.action_on("leave"), 10, "host can leave the room")
    a.press("leave")
    ctx.wait(lambda: (a.me or {}).get("status") == "idle", 10, "host left")
    ctx.wait(lambda: any((r.get("owner") or {}).get("name") == "E2E Tia" for r in b.client.rooms), 10,
             "ownership moved to the one who stayed")
    b.press("leave")
    ctx.wait(lambda: not a.client.rooms and not b.client.rooms, 10, "last one left: the room is gone")


# ============================================================================== 5. rematch
@scenario("rematch_decline", "5 rematch", suites=("quick", "lobby"), desc="one side wants a rematch, the other leaves")
def rematch_decline(ctx):
    stub_server(ctx)
    a = ctx.player("E2E Uma", kind="stub")
    b = ctx.player("E2E Vic", kind="stub")
    login(ctx, a)
    login(ctx, b)
    mid = queue_match(ctx, a, b, "quick")
    wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
    t = time.time()
    a.click("Rematch")
    ctx.wait(lambda: b.bar_button("Rematch") is not None and "wants a rematch" in b.tab.bar_text.get(), 10,
             "the other player sees the offer")
    leave(ctx, b)
    ctx.wait(lambda: any(ev.get("state") == "declined" for ev in a.events_of("rematch", t)), 10, "the offer is declined")
    ctx.wait(lambda: a.bar_button("Rematch") is None, 5, "the rematch bar is gone")
    ctx.wait(lambda: a.events_of("set_end", t), 10, "the set ended")
    ctx.check("no second match started", len(a.events_of("match_start")) == 1)
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 10, "both free to search again")


@scenario("rematch_timeout", "5 rematch", suites=("quick", "lobby"), desc="the rematch window runs out")
def rematch_timeout(ctx):
    stub_server(ctx, T5L_REMATCH_WINDOW=6)
    a = ctx.player("E2E Wes", kind="stub")
    b = ctx.player("E2E Xen", kind="stub")
    login(ctx, a)
    login(ctx, b)
    mid = queue_match(ctx, a, b, "quick")
    wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
    t = time.time()
    a.click("Rematch")
    ctx.wait(lambda: any(ev.get("reason") == "expired" for ev in a.events_of("set_end", t)), 15,
             "after the 6 s window: set ends (expired)")
    ctx.check("no rematch started", len(a.events_of("match_start")) == 1)
    t = time.time()
    box = b.call(b.client.rematch, mid, True, False)
    ctx.wait(lambda: box, 10)
    ctx.check("a late Rematch is refused (the match is over)", "err" in box or b.saw_status("over", t), b.status_text())


@scenario("rematch_late_answer", "5 rematch", game=True, suites=("game",),
          desc="one player clicks Rematch at once, the other only after the lag check came in (8 s): the first one's "
               "bar must not offer Rematch again meanwhile, and the rematch starts")
def rematch_late_answer(ctx):
    game_server(ctx)
    a = ctx.player("E2E Gil")
    b = ctx.player("E2E Hana")
    login(ctx, a)
    login(ctx, b)
    mid = queue_match(ctx, a, b, "quick")
    wait_fight(ctx, mid, (a, b))
    wait_results(ctx, mid, (a, b))
    match_row(ctx, mid, (a, b), "confirmed", "match 1")
    ctx.wait(lambda: a.bar_button("Rematch") is not None, 15, f"{a.name}: Rematch button")
    t = time.time()
    a.click("Rematch")
    seen = []

    def watch():
        if a.bar_button("Rematch") is not None:
            seen.append(round(time.time() - t, 1))
        return False
    ctx.wait(watch, 8)
    lag = a.matches[mid].get("lag")
    ctx.note(f"lag check: {(lag or {}).get('text')}")
    ctx.check("after Rematch was clicked the bar does not offer Rematch again (it waits for the opponent)",
              not seen, f"the Rematch button was back {len(seen)} poll(s), first {seen[0] if seen else '-'} s after the "
              f"click (lag check {'arrived' if lag else 'not seen'})")
    ctx.wait(lambda: b.bar_button("Rematch") is not None, 10, f"{b.name}: Rematch button")
    t2 = time.time()
    b.click("Rematch")
    mid2 = found_both(ctx, a, b, t2)
    started_both(ctx, a, b, mid2)
    wait_fight(ctx, mid2, (a, b))
    wait_results(ctx, mid2, (a, b))
    match_row(ctx, mid2, (a, b), "confirmed", "the late-answered rematch")


@scenario("rematch_chain", "5 rematch", game=True, suites=("game",),
          desc="rematch after rematch: 1 match + 5 rematches in the running games")
def rematch_chain(ctx):
    game_server(ctx)
    a = ctx.player("E2E Yara", char="steve")
    b = ctx.player("E2E Zed", char="hwoarang")
    login(ctx, a)
    login(ctx, b)
    a.set_char("steve")
    b.set_char("hwoarang")
    mid = queue_match(ctx, a, b, "quick")
    pids = None
    for k in range(6):
        if k:
            mid = rematch(ctx, a, b)
            ctx.check(f"rematch {k}: same game processes, same session", a.matches[mid].get("cont") and
                      [g.proc.pid for g in (a.game(), b.game())] == pids)
        wait_fight(ctx, mid, (a, b), timeout=120)
        if pids is None:
            pids = [g.proc.pid for g in (a.game(), b.game())]
        wait_results(ctx, mid, (a, b))
        row = match_row(ctx, mid, (a, b), "confirmed", "first match" if not k else f"rematch {k}")
        fps_check(ctx, row, (a, b))


# ============================================================================== 6. netcode
NET_ROLLBACK = [
    # label, rtt, jitter, loss, input delay setting (both), relay, expected rollback input delay
    ("rollback RTT 20, delay Auto", 20, 0, 0, "auto", False, 1),
    ("rollback RTT 80, delay Auto", 80, 0, 0, "auto", False, 2),
    ("rollback RTT 150, delay Auto", 150, 0, 0, "auto", False, 2),
    ("rollback RTT 250, delay Auto", 250, 0, 0, "auto", False, 2),
    ("rollback RTT 80, delay 0", 80, 0, 0, "0", False, 0),
    ("rollback RTT 80, delay 1", 80, 0, 0, "1", False, 1),
    ("rollback RTT 80, delay 2", 80, 0, 0, "2", False, 2),
    ("rollback RTT 80, 2% loss", 80, 0, 2, "auto", False, 2),
    ("rollback RTT 80, 10% loss", 80, 0, 10, "auto", False, 2),
    ("rollback RTT 80, jitter +-20 ms", 80, 20, 0, "auto", False, 2),
    ("rollback relay path", 0, 0, 0, "auto", True, 1),
]
NET_LOCKSTEP = [
    ("lockstep RTT 20", 20, 0, 0, "auto", False, None),
    ("lockstep RTT 150", 150, 0, 0, "auto", False, None),
    ("lockstep RTT 80, 10% loss, jitter +-15 ms", 80, 15, 10, "auto", False, None),
    ("lockstep relay path", 0, 0, 0, "auto", True, None),
]


def net_case(ctx, a, b, label, rtt, jitter, loss, delay, relay, expect, mode="rollback"):
    from t5lobby import proto
    ctx.shaper.set(rtt, jitter, loss, on=not relay)
    stats0 = ctx.shaper.stats()
    for p in (a, b):
        p.app.settings["input_delay"] = delay
        p.tab.driver.input_delay = delay
        p.client.block_direct = relay
    mid = queue_match(ctx, a, b, "quick")
    path = a.matches[mid].get("path")
    ctx.check(f"{label}: path", path == "relay" if relay else path in ("lan", "direct"), path)
    if not wait_fight(ctx, mid, (a, b), timeout=150):
        raise Abort("no fight")
    wait_results(ctx, mid, (a, b))
    row = match_row(ctx, mid, (a, b), "confirmed", label)
    fps_check(ctx, row, (a, b), floor=45.0)
    host, join = (a, b) if a.matches[mid].get("slot") == 0 else (b, a)
    rh, rj = row[host.name], row[join.name]
    ctx.check(f"{label}: netcode {mode} on both", rh["mode"] == mode and rj["mode"] == mode, f"{rh['mode']}/{rj['mode']}")
    if mode == "rollback" and expect is not None:
        ctx.check(f"{label}: rollback input delay {expect}", rh["pick"] == expect and rj["delay"] == expect,
                  f"host picked {rh['pick']} ({rh['pick_why']}), joiner runs {rj['delay']}")
    if mode == "lockstep":
        want = proto.suggest_delay(rtt, jitter) if not relay else None
        got = [(r or {}).get("connected") for r in (parse_segment(host.log_segment(mid)), parse_segment(join.log_segment(mid)))]
        ctx.note(f"{label}: lockstep delay host/joiner {got}, lobby-style delay for the shaped path {want}")
    ctx.note(f"{label}: proxy {ctx.shaper.stats(stats0)}")
    for p in (a, b):
        leave(ctx, p)
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 30, f"{label}: free for the next pairing")
    ctx.sleep(1.0)
    return row


@scenario("net_rollback", "6 netcode", game=True, suites=("game", "net"),
          desc="rollback: RTT 20/80/150/250 ms, input delay Auto/0/1/2, 2% and 10% loss, jitter, the relay path")
def net_rollback(ctx):
    if ctx.run.netcode == "lockstep":
        raise Skip("the rollback cases (this run is --netcode lockstep; net_lockstep covers it)")
    game_server(ctx)
    a = ctx.player("E2E Net1")
    b = ctx.player("E2E Net2")
    login(ctx, a)
    login(ctx, b)
    cases = NET_ROLLBACK if not ctx.run.short else NET_ROLLBACK[:2] + NET_ROLLBACK[-1:]
    for c in cases:
        try:
            net_case(ctx, a, b, *c)
        except Abort as e:
            ctx.check(f"{c[0]}: completed", False, str(e))
            for p in (a, b):
                leave(ctx, p)
            ctx.sleep(5)


@scenario("net_lockstep", "6 netcode", game=True, suites=("game", "net"),
          desc="lockstep (both T5_RB_MODE=off): RTT 20/150, loss with jitter, the relay path")
def net_lockstep(ctx):
    game_server(ctx)
    a = ctx.player("E2E Lock1", env={"T5_RB_MODE": "off"})
    b = ctx.player("E2E Lock2", env={"T5_RB_MODE": "off"})
    login(ctx, a)
    login(ctx, b)
    for c in (NET_LOCKSTEP if not ctx.run.short else NET_LOCKSTEP[:1]):
        try:
            net_case(ctx, a, b, *c, mode="lockstep")
        except Abort as e:
            ctx.check(f"{c[0]}: completed", False, str(e))
            for p in (a, b):
                leave(ctx, p)
            ctx.sleep(5)


@scenario("net_internal_res", "6 netcode", game=True, suites=("game", "net"),
          desc="different internal resolutions on the two PCs (4K against Lowest, the launcher's setting): a match and "
               "a rematch stay in sync")
def net_internal_res(ctx):
    import core
    if "internal_res" not in core.DEFAULTS:
        raise Skip("this launcher has no 'Internal resolution' setting (internal-res is not merged)")
    game_server(ctx)
    a = ctx.player("E2E Res4K", char="lili")
    b = ctx.player("E2E ResLow", char="dragunov")
    a.app.settings["internal_res"] = "4k"
    b.app.settings["internal_res"] = "lowest"
    login(ctx, a)
    login(ctx, b)
    a.set_char("lili")
    b.set_char("dragunov")
    mid = queue_match(ctx, a, b, "quick")
    for label, (p, want) in (("4K side", (a, "4k")), ("Lowest side", (b, "lowest"))):
        ctx.wait(lambda p=p: p.game() is not None and p.game().log_path, 20)
        ok = ctx.wait(lambda p=p, want=want: log_line(p, r"\[display\] internal resolution " + want), 60,
                      f"{label}: the game runs at internal resolution {want}")
        if ok:
            ctx.note(f"{label}: {log_line(p, r'\[display\] internal resolution')}")
    row = _play(ctx, a, b, mid, "match 1 (4K vs Lowest)")
    fps_check(ctx, row, (a, b))
    mid = rematch(ctx, a, b)
    row = _play(ctx, a, b, mid, "rematch (4K vs Lowest)")
    fps_check(ctx, row, (a, b))


def log_line(p, pattern):
    """The first line of p's current game log matching `pattern`, or None."""
    import re as _re
    g = p.game()
    if g is None or not g.log_path:
        return None
    rx = _re.compile(pattern, _re.I)
    try:
        with open(g.log_path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                if rx.search(ln):
                    return ln.strip()
    except OSError:
        pass
    return None


@scenario("net_mixed_fallback", "6 netcode", game=True, suites=("game", "net"),
          desc="one game without rollback (T5_RB_MODE=off): both fall back to lockstep, in sync")
def net_mixed_fallback(ctx):
    if ctx.run.netcode == "lockstep":
        raise Skip("needs one rollback game (this run is --netcode lockstep)")
    game_server(ctx)
    a = ctx.player("E2E Mix1")
    b = ctx.player("E2E Mix2", env={"T5_RB_MODE": "off"})
    login(ctx, a)
    login(ctx, b)
    net_case(ctx, a, b, "mixed: one side lockstep only, RTT 40", 40, 0, 0, "auto", False, None, mode="lockstep")


# ------------------------------------------------------------------ relay -> direct while the match runs (1.1.1)
def _relay_bridge():
    """nat.RelayBridge in this tree (nat-robust, 1.1.1), or None."""
    try:
        from t5lobby.nat import RelayBridge
        return RelayBridge
    except ImportError:
        return None


def _upgrades(p, mid, path="direct"):
    return [ts for ts, e in p.events if e.get("t") == "nat_upgrade" and e.get("match") == mid and e.get("path") == path]


def relay_upgrade_case(ctx, a, b, label, expect=True, real=True):
    """The punch phase fails (both launchers ignore the opponent's direct packets: block_direct), so the match
    starts on the lobby server's relay; then the direct path is opened again. Between two 1.1.1 launchers the
    relay bridge finds it in its first burst (the match's start + 35 s, the same server time on both) and both
    move the game's packets onto it while the match runs; the games keep talking to 127.0.0.1 and must not
    notice. expect=False: one side is a 1.1.0-style client (no nat2), so no bridge and the match stays on the
    relay to its end."""
    rb = _relay_bridge()
    ctx.shaper.set(0, 0, 0, on=False)
    for p in (a, b):
        p.client.block_direct = True
    since = time.time()
    mid = queue_match(ctx, a, b, "quick")
    started = max(a.matches[mid]["started"], b.matches[mid]["started"])
    for p in (a, b):
        p.client.block_direct = False                 # (the next match punches normally)
    paths = [p.matches[mid].get("path") for p in (a, b)]
    ctx.check(f"{label}: the match starts on the relay", paths == ["relay", "relay"], paths)
    bridges = [p.client._bridge for p in (a, b)]
    if expect:
        ctx.check(f"{label}: a relay bridge in both launchers", all(bridges), [type(x).__name__ for x in bridges])
        if not all(bridges):
            raise Abort("no relay bridge")
        peers = [tuple(getattr(getattr(p.tab.driver, "ticket", None), "peer", ()) or ()) for p in (a, b)]
        ctx.check(f"{label}: both games talk to their own launcher (127.0.0.1:<bridge port>)",
                  all(len(pr) == 2 and pr[0] == "127.0.0.1" and int(pr[1]) == br.port for pr, br in zip(peers, bridges)),
                  f"game peers {peers}, bridge ports {[br.port for br in bridges]}")
        for br in bridges:
            br.gs.block_direct = False                # the direct path opens: only the punch phase was blocked
        ctx.note(f"{label}: punch phase blocked -> relay; direct path opened {time.time() - started:.1f} s after "
                 f"match_start; first burst due at +{rb.FIRST_BURST:.0f} s")
    else:
        ctx.check(f"{label}: no relay bridge (a 1.1.0 client on one side)", not any(bridges),
                  [type(x).__name__ for x in bridges])
    if real and not wait_fight(ctx, mid, (a, b), timeout=150):
        raise Abort("no fight")
    up = None
    if expect:
        deadline = started + rb.FIRST_BURST + rb.BURST + 15.0
        ok = ctx.wait(lambda: _upgrades(a, mid) and _upgrades(b, mid), max(5.0, deadline - time.time()),
                      f"{label}: both launchers moved the match onto the direct path (nat_upgrade)")
        if ok:
            up = [_upgrades(p, mid)[0] for p in (a, b)]
            ctx.note(f"{label}: switched {up[0] - started:.1f} s / {up[1] - started:.1f} s after match_start")
            s0 = [dict(br.stats) for br in bridges]
            ctx.sleep(5.0)
            s1 = [dict(br.stats) for br in bridges]
            for p, br, x0, x1 in zip((a, b), bridges, s0, s1):
                d_in, r_in = x1["direct_in"] - x0["direct_in"], x1["relay_in"] - x0["relay_in"]
                ctx.check(f"{label}: {p.name}: the opponent's packets now come straight from its PC",
                          br.path == "direct" and d_in >= 20 and r_in <= d_in // 10,
                          f"in the 5 s after the switch: {d_in} direct, {r_in} through the relay, "
                          f"{x1['from_game'] - x0['from_game']} sent by this game; bridge path {br.path}")
            ctx.check(f"{label}: the Online tab says so on both PCs",
                      a.saw_status("Direct connection found", since) and b.saw_status("Direct connection found", since),
                      f"{a.status_text()!r} / {b.status_text()!r}")
            ctx.check(f"{label}: the lobby server logged both switches",
                      server_says(ctx, rf"match {mid}: side 0 left the relay for the direct path") and
                      server_says(ctx, rf"match {mid}: side 1 left the relay for the direct path"))
    wait_results(ctx, mid, (a, b))
    t_res = min(p.matches[mid].get("result") or 1e18 for p in (a, b))
    if expect and up:
        if real:
            fight = max(p.matches[mid].get("fight_at") or 0 for p in (a, b))
            ctx.check(f"{label}: the switch came while the fight ran", fight < min(up) and max(up) < t_res,
                      f"FIGHT START +{fight - started:.1f} s, switch +{min(up) - started:.1f}/{max(up) - started:.1f} s,"
                      f" result +{t_res - started:.1f} s")
        else:
            ctx.check(f"{label}: the switch came while the match ran", max(up) < t_res,
                      f"switch +{max(up) - started:.1f} s, result +{t_res - started:.1f} s")
        back = [ts for p in (a, b) for ts in _upgrades(p, mid, "relay") if ts < t_res]
        ctx.check(f"{label}: on the direct path to the end (no fall back to the relay)", not back,
                  f"{len(back)} switches back")
        ctx.note(f"{label}: bridge counters {[dict(br.stats) for br in bridges]}")
    elif not expect:
        ctx.check(f"{label}: no switch: the match stays on the relay", not _upgrades(a, mid) and not _upgrades(b, mid))
    if real:
        row = match_row(ctx, mid, (a, b), "confirmed", label)
        fps_check(ctx, row, (a, b))
        mode = ctx.run.netcode
        ctx.check(f"{label}: netcode {mode} on both", row[a.name]["mode"] == mode and row[b.name]["mode"] == mode,
                  f"{row[a.name]['mode']}/{row[b.name]['mode']}")
        for p in (a, b):
            ctx.check(f"{label}: {p.name}'s game kept one peer address (it never had to follow one)",
                      not log_has(p, r"the peer's address changed", mid))
    else:
        st = [p.matches[mid].get("status") for p in (a, b)]
        ctx.check(f"{label}: lobby result confirmed", st == ["confirmed", "confirmed"], st)
        rf = [p.result_file(mid) or {} for p in (a, b)]
        ctx.check(f"{label}: both stub games: same winner, 0 mismatching frames",
                  rf[0].get("winner") == rf[1].get("winner") and not rf[0].get("desync") and not rf[1].get("desync"),
                  f"winner {rf[0].get('winner')}/{rf[1].get('winner')}, desync {rf[0].get('desync')}/{rf[1].get('desync')}")
        for p in (a, b):
            ctx.check(f"{label}: {p.name}'s stub game never lost its peer",
                      not log_has(p, r"no input from the peer|peer lost|DESYNC", mid))
    for p in (a, b):
        leave(ctx, p)
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 30, f"{label}: free for the next pairing")
    ctx.sleep(1.0)
    return mid


@scenario("net_relay_upgrade", "6 netcode", game=True, suites=("game", "net"),
          desc="1.1.1 relay bridge: the punch fails, the match starts on the relay, the direct path opens; both "
               "launchers move the fight onto it at the match's start + 35 s, the games stay in sync")
def net_relay_upgrade(ctx):
    if _relay_bridge() is None:
        raise Skip("no relay bridge in this tree (nat-robust, 1.1.1)")
    game_server(ctx, T5L_ROUNDS=max(2, ctx.run.rounds))     # a fight still running 35-40 s after match_start
    a = ctx.player("E2E Up1")
    b = ctx.player("E2E Up2")
    login(ctx, a)
    login(ctx, b)
    relay_upgrade_case(ctx, a, b, "relay -> direct")


@scenario("relay_upgrade_stub", "6 netcode", suites=("lobby", "net"),
          desc="1.1.1 relay bridge with stub games: relay -> direct during a ~65 s match; against a 1.1.0-style "
               "client (no nat2) no bridge and the match stays on the relay")
def relay_upgrade_stub(ctx):
    if _relay_bridge() is None:
        raise Skip("no relay bridge in this tree (nat-robust, 1.1.1)")
    stub_server(ctx)
    # T5_STUB_SECONDS counts frames (60 a second), but a stub frame waits for the peer's packet: ~17 frames a
    # second, so 18 "seconds" are about 65 s -- the first burst (+35 s) falls into the match
    a = ctx.player("E2E Ups1", kind="stub", env={"T5_STUB_SECONDS": 18})
    b = ctx.player("E2E Ups2", kind="stub", env={"T5_STUB_SECONDS": 18})
    login(ctx, a)
    login(ctx, b)
    relay_upgrade_case(ctx, a, b, "stub: relay -> direct", real=False)
    c = ctx.player("E2E Old110", kind="stub", env={"T5_STUB_SECONDS": 18})
    ctx.no_nat2.add(c.name)
    login(ctx, c)
    ctx.check("the 1.1.0-style client logged in without nat2", c.client is not None and not c.client.nat2)
    relay_upgrade_case(ctx, c, b, "stub: 1.1.0 client on the relay", expect=False, real=False)


# ------------------------------------------------------------------ regional relays (1.1.1)
def _regional_world(ctx, real, rtt=None):
    """Lobby server with two regional relay nodes (RelayNodes: usw, usc) behind simulated round trips."""
    from e2e_harness import RelayNodes
    try:
        import t5lobby.relayctl  # noqa: F401
    except ImportError:
        raise Skip("no regional relays in this tree (regional-relays, 1.1.1)")
    ctx.relays = RelayNodes(ctx, rtt)
    (game_server if real else stub_server)(ctx, **ctx.relays.server_env())
    if not ctx.wait(lambda: all(ctx.relays.alive().get(r) for r in ctx.relays.nodes), 25,
                    f"relay nodes {sorted(ctx.relays.nodes)} up at the lobby server"):
        raise Abort("relay nodes not up")
    ctx.note(f"relays: {ctx.relays.json}; simulated round trips (ms, A/B) {ctx.relays.rtt}")


def _routed(ctx, p, index):
    ctx.relay_routes[p.name] = ctx.relays.routes(index)


def _start_ev(p, mid):
    for _ts, e in p.events:
        if e.get("t") == "match_start" and e.get("match") == mid:
            return e
    return {}


def regional_case(ctx, a, b, label, expect, expect_rtt, real=True):
    """The punch fails (block_direct, kept on: the relay bridge's bursts fail too, the match stays relayed), so the
    lobby needs a relay: the regional one with the smallest sum of both players' measured round trips (expect:
    its id; "main" = the lobby server's own relay, e.g. against a 1.1.0 client)."""
    names = ctx.relays.NAMES
    for p in (a, b):
        p.client.block_direct = True
    rtts = {p.name: dict(getattr(p.client, "relay_rtts", None) or {}) for p in (a, b)}
    ctx.note(f"{label}: measured relay round trips {rtts}")
    before = ctx.relays.packets()
    since = time.time()
    mid = queue_match(ctx, a, b, "quick")
    evs = [_start_ev(p, mid) for p in (a, b)]
    chosen = [(e.get("relay") or {}).get("id") or ("main" if e.get("path") == "relay" else e.get("path")) for e in evs]
    ctx.check(f"{label}: relayed through {expect} on both PCs", chosen == [expect, expect] and
              all(e.get("path") == "relay" for e in evs), f"{chosen}, paths {[e.get('path') for e in evs]}")
    rtt = evs[0].get("rtt_ms")
    ctx.check(f"{label}: the lobby's round trip of the path ~{expect_rtt} ms",
              rtt is not None and expect_rtt * 0.8 - 5 < rtt < expect_rtt * 1.35 + 15, f"{rtt} ms")
    want = (f"using the relay server {names[expect]}" if expect in names else "using the lobby server's relay")
    ctx.check(f"{label}: the Online tab names the relay", a.saw_status(re.escape(want), since) or
              (b.saw_status(re.escape(want), since)), f"wanted '{want}': {a.status_text()!r} / {b.status_text()!r}")
    if real:
        if not wait_fight(ctx, mid, (a, b), timeout=150):
            raise Abort("no fight")
    wait_results(ctx, mid, (a, b))
    after = ctx.relays.packets()
    moved = {k: (after[k] - before[k]) if after.get(k) is not None and before.get(k) is not None else None
             for k in after}
    others = {k: v for k, v in moved.items() if k != expect}
    # (a few packets elsewhere are the 1.1.1 client's round-trip pings to the other relays, not the games')
    ctx.check(f"{label}: {expect} carried the match alone",
              (moved.get(expect) or 0) >= 100 and all((v or 0) <= max(20, (moved.get(expect) or 0) // 50)
                                                      for v in others.values()),
              f"packets relayed during the match: {moved}")
    ups = [e for p in (a, b) for e in p.events_of("nat_upgrade", since) if e.get("match") == mid]
    ctx.check(f"{label}: stayed on the relay (no direct path: blocked)", not ups, f"{len(ups)} switches")
    if real:
        row = match_row(ctx, mid, (a, b), "confirmed", label)
        fps_check(ctx, row, (a, b))
        mode = ctx.run.netcode
        ctx.check(f"{label}: netcode {mode} on both", row[a.name]["mode"] == mode and row[b.name]["mode"] == mode,
                  f"{row[a.name]['mode']}/{row[b.name]['mode']}")
        if mode == "rollback":
            host, join = (a, b) if a.matches[mid].get("slot") == 0 else (b, a)
            ctx.note(f"{label}: rollback input delay host {row[host.name]['pick']} ({row[host.name]['pick_why']}), "
                     f"joiner {row[join.name]['delay']}")
    else:
        st = [p.matches[mid].get("status") for p in (a, b)]
        ctx.check(f"{label}: lobby result confirmed", st == ["confirmed", "confirmed"], st)
        rf = [p.result_file(mid) or {} for p in (a, b)]
        ctx.check(f"{label}: both stub games: same winner, 0 mismatching frames",
                  rf[0].get("winner") == rf[1].get("winner") and not rf[0].get("desync") and not rf[1].get("desync"),
                  f"winner {rf[0].get('winner')}/{rf[1].get('winner')}, desync {rf[0].get('desync')}/{rf[1].get('desync')}")
    for p in (a, b):
        p.client.block_direct = False
        leave(ctx, p)
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 30, f"{label}: free for the next pairing")
    ctx.sleep(1.0)
    return mid


def _relay_dead(ctx, rid):
    t0 = time.time()
    ctx.relays.stop(rid)
    ctx.wait(lambda: ctx.relays.alive().get(rid) is False, 30, f"the lobby server marks {rid} down (node stopped)")
    ctx.note(f"{rid} stopped: marked down after {time.time() - t0:.1f} s")


@scenario("relay_regional", "6 netcode", game=True, suites=("game", "net"),
          desc="regional relays (1.1.1): the punch fails, the lobby picks the relay node with the smallest RTT sum "
               "(usc 60+60 over usw 20+140 and its own 150+150), real games play through it in sync; usc stopped: "
               "the next match takes usw")
def relay_regional(ctx):
    _regional_world(ctx, real=True)
    a = ctx.player("E2E Reg1")
    b = ctx.player("E2E Reg2")
    _routed(ctx, a, 0)
    _routed(ctx, b, 1)
    login(ctx, a)
    login(ctx, b)
    ctx.wait(lambda: all(len(p.client.relay_rtts or {}) >= 2 for p in (a, b)), 20, "both measured both relays")
    regional_case(ctx, a, b, "regional relay usc", "usc", 120)
    _relay_dead(ctx, "usc")
    regional_case(ctx, a, b, "usc down: usw", "usw", 160)


@scenario("relay_old_client", "6 netcode", game=True, suites=("game", "net"),
          desc="the real 1.1.0 Online tab, client and match driver (git tag v1.1.0) against 1.1.1, the same game "
               "build, regional relays up: the 1.1.0 side cannot use them, the match takes the lobby's own relay")
def relay_old_client(ctx):
    _regional_world(ctx, real=True)
    a = ctx.player("E2E New111")
    b = ctx.player("E2E Old110", lobby="v1.1.0")
    _routed(ctx, a, 0)
    login(ctx, a)
    login(ctx, b)
    ctx.check("the 1.1.0 player runs the 1.1.0 lobby code", type(b.client).__module__.startswith("t5lobby_v110"),
              type(b.client).__module__)
    ctx.wait(lambda: len(a.client.relay_rtts or {}) >= 2, 20, "the 1.1.1 player measured both relays")
    regional_case(ctx, a, b, "1.1.0 + 1.1.1: the lobby's own relay", "main", 150)


@scenario("relay_regional_stub", "6 netcode", suites=("lobby", "net"),
          desc="regional relays with stub games: usc by RTT sum, usw once usc is down, the lobby's own relay "
               "against the real 1.1.0 lobby code (git tag v1.1.0)")
def relay_regional_stub(ctx):
    _regional_world(ctx, real=False)
    a = ctx.player("E2E RegS1", kind="stub", env={"T5_STUB_SECONDS": 4})
    b = ctx.player("E2E RegS2", kind="stub", env={"T5_STUB_SECONDS": 4})
    _routed(ctx, a, 0)
    _routed(ctx, b, 1)
    login(ctx, a)
    login(ctx, b)
    ctx.wait(lambda: all(len(p.client.relay_rtts or {}) >= 2 for p in (a, b)), 20, "both measured both relays")
    regional_case(ctx, a, b, "stub: regional relay usc", "usc", 120, real=False)
    c = ctx.player("E2E OldS110", kind="stub", env={"T5_STUB_SECONDS": 4}, lobby="v1.1.0")
    login(ctx, c)
    ctx.check("the 1.1.0 player runs the 1.1.0 lobby code", type(c.client).__module__.startswith("t5lobby_v110"),
              type(c.client).__module__)
    regional_case(ctx, a, c, "stub: 1.1.0 + 1.1.1: the lobby's own relay", "main", 150, real=False)
    _relay_dead(ctx, "usc")
    regional_case(ctx, a, b, "stub: usc down: usw", "usw", 160, real=False)


def _relay_tool_run(ctx, real):
    """lobby/tools/relay_e2e.py as it is (its own central lobby, two relay nodes, delay proxies, the 1.1.0 client
    from the git tag), in a process of this run (stopped with it)."""
    tool = os.path.join(harness_root(), "lobby", "tools", "relay_e2e.py")
    if not os.path.isfile(tool):
        raise Skip("no lobby/tools/relay_e2e.py in this tree (regional-relays, 1.1.1)")
    cmd = [sys.executable, tool, "--scenarios", "best,dead,old"]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if real:
        cmd += ["--exe", ctx.run.exe, "--vfs", os.path.join(ctx.run.game_root, "game", "vfs")]
        if ctx.run.netcode == "lockstep":
            env["T5_RB_MODE"] = "off"
    logf = os.path.join(ctx.dir, "relay_e2e.log")
    with open(logf, "w", encoding="utf-8") as lf:
        pr = subprocess.Popen(cmd, cwd=harness_root(), env=env, stdout=lf, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, creationflags=0x08000000 if os.name == "nt" else 0)
        ctx.run.own(pr)
        t_end = time.time() + (900 if real else 300)
        while pr.poll() is None and time.time() < t_end:
            ctx.sleep(1.0)
        if pr.poll() is None:
            pr.kill()
    text = open(logf, encoding="utf-8", errors="replace").read()
    ctx.check("relay_e2e.py finished in time", pr.returncode is not None and time.time() < t_end, f"exit {pr.returncode}")
    for name in ("best", "dead", "old"):
        m = re.search(rf"== {name}\n(.*?)\n   (PASS|FAIL)([^\n]*)", text, re.S)
        ctx.check(f"relay_e2e {name}", bool(m) and m.group(2) == "PASS",
                  (m.group(2) + m.group(3)) if m else "no result line")
        if m:
            for ln in m.group(1).splitlines():
                if ln.strip().startswith(("match ", "packets", "lobby verdict", "usc stopped", "P1 game", "P2 game")):
                    ctx.note(f"relay_e2e {name}: {ln.strip()[:240]}")
    ctx.check("relay_e2e.py: RELAY E2E OK, exit 0", "RELAY E2E OK" in text and pr.returncode == 0,
              text.strip().splitlines()[-1] if text.strip() else "no output")


def harness_root():
    import e2e_harness
    return e2e_harness.ROOT


@scenario("relay_e2e_tool", "6 netcode", suites=("lobby", "net"),
          desc="lobby/tools/relay_e2e.py with stub games: best (usc), dead (usw), old (1.1.0 client: the lobby's relay)")
def relay_e2e_tool(ctx):
    _relay_tool_run(ctx, real=False)


@scenario("relay_e2e_tool_game", "6 netcode", game=True, suites=("game", "net"),
          desc="lobby/tools/relay_e2e.py --exe: the same three cases with real games (no launcher; idle fighters)")
def relay_e2e_tool_game(ctx):
    _relay_tool_run(ctx, real=True)


# ------------------------------------------------------------------ VSync off in one game (1.1.1)
@scenario("net_vsync_off", "6 netcode", game=True, suites=("game", "net"),
          desc="launcher Settings VSync off (PS3_VSYNC=0) in one game of the match: both still 60 fps, in sync, "
               "a new session and two rematches")
def net_vsync_off(ctx):
    if "vsync" not in core.DEFAULTS:
        raise Skip("no VSync setting in this launcher (vsync-toggle, 1.1.1)")
    game_server(ctx)
    a = ctx.player("E2E VsOff")
    b = ctx.player("E2E VsOn")
    a.app.settings["vsync"] = "off"
    a.app.settings.save()
    login(ctx, a)
    login(ctx, b)
    mid = queue_match(ctx, a, b, "quick")
    rx = re.compile(r"\[display\] res_scale=\S+ vsync=(\d)")
    for k in range(3):
        if k:
            mid = rematch(ctx, a, b)
        if not wait_fight(ctx, mid, (a, b), timeout=150):
            raise Abort("no fight")
        if k == 0:
            got = {}
            for p in (a, b):
                ms = [m.group(1) for ln in log_lines(p) for m in [rx.search(ln)] if m]
                got[p.name] = ms[-1] if ms else None
            ctx.check("the game of the player with VSync off runs vsync=0, the other vsync=1",
                      got == {a.name: "0", b.name: "1"}, got)
        wait_results(ctx, mid, (a, b))
        label = "VSync off/on" + (f", rematch {k}" if k else "")
        row = match_row(ctx, mid, (a, b), "confirmed", label)
        fps_check(ctx, row, (a, b))
        fa = row[a.name]["result_file"].get("fps")
        ctx.check(f"{label}: VSync off does not make the game faster than 60", fa is None or fa <= 61.0, f"fps {fa}")


def log_lines(p):
    out = []
    for g in p.games:
        try:
            with open(g.log_path, encoding="utf-8", errors="replace") as f:
                out += f.read().splitlines()
        except (OSError, TypeError):
            pass
    return out


# ============================================================================== 7. failures
def _two(ctx, n1, n2, **kw):
    game_server(ctx, **kw)
    a = ctx.player(n1)
    b = ctx.player(n2)
    login(ctx, a)
    login(ctx, b)
    return a, b


def _next_match_ok(ctx, a, b, label):
    for p in (a, b):
        leave(ctx, p)
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 60, f"{label}: both can search again")
    mid = queue_match(ctx, a, b, "quick")
    wait_fight(ctx, mid, (a, b), timeout=180)
    wait_results(ctx, mid, (a, b))
    match_row(ctx, mid, (a, b), "confirmed", label)
    return mid


@scenario("fail_close_window", "7 failures", game=True, suites=("game",),
          desc="Alt+F4 / closing the window mid-match = quit = forfeit; the next match starts a fresh game")
def fail_close_window(ctx):
    a, b = _two(ctx, "E2E Fay", "E2E Gus")
    mid = queue_match(ctx, a, b, "quick")
    wait_fight(ctx, mid, (a, b))
    ctx.sleep(12)
    n = close_window(b)
    ctx.note(f"WM_CLOSE to {b.name}'s game ({n} window(s))")
    ctx.wait(lambda: not b.game_running(), 20, "the closed game ends itself")
    ctx.check("exit code 7", game_exit_code(b) == 7, game_exit_code(b))
    wait_results(ctx, mid, (a, b), 90)
    mb = b.matches.get(mid, {})
    ctx.check("lobby: forfeit (quit), the closer blamed and lost", mb.get("status") == "forfeit" and mb.get("reason") == "quit"
              and mb.get("blame") == "you" and mb.get("winner") == 1 - (mb.get("slot") or 0),
              f"{mb.get('status')} {mb.get('reason')} blame {mb.get('blame')} winner {mb.get('winner')} slot {mb.get('slot')}")
    ctx.check("quit reported without asking the player", not any(n_.get("kind") == "ask_result" for _t, n_ in b.notes))
    rf_b, rf_a = b.result_file(mid) or {}, a.result_file(mid) or {}
    ctx.check("result files: quit / peer_quit", rf_b.get("reason") == "quit" and rf_a.get("reason") == "peer_quit",
              f"{rf_b.get('reason')} / {rf_a.get('reason')}")
    games_before = len(b.games)
    _next_match_ok(ctx, a, b, "next match after the quit")
    ctx.check("the closer's launcher started a fresh game; the other kept its game",
              len(b.games) == games_before + 1 and len(a.games) == 1, f"{len(b.games)} / {len(a.games)}")


@scenario("fail_kill", "7 failures", game=True, suites=("game",),
          desc="a game killed mid-match counts as a crash (void, blamed); the next match works")
def fail_kill(ctx):
    a, b = _two(ctx, "E2E Hal", "E2E Ivy")
    mid = queue_match(ctx, a, b, "quick")
    wait_fight(ctx, mid, (a, b))
    ctx.sleep(12)
    ctx.check("game killed", kill_game(b))
    wait_results(ctx, mid, (a, b), 90)
    hist = [h for m_, h in b.tab.driver.history if m_ == mid]
    ctx.check("the killed side reports a crash", hist and hist[-1].get("source") == "crash", hist)
    mb = b.matches.get(mid, {})
    ctx.check("lobby: void (crash), the crashed side blamed", mb.get("status") == "void" and mb.get("reason") == "crash"
              and mb.get("blame") == "you", f"{mb.get('status')} {mb.get('reason')} blame {mb.get('blame')}")
    ha = [h for m_, h in a.tab.driver.history if m_ == mid]
    ctx.note(f"the survivor reported {ha[-1] if ha else None}")
    ctx.check("the player is told", b.saw_status("stopped unexpectedly"), b.status_text())
    _next_match_ok(ctx, a, b, "next match after the crash")


@scenario("fail_net_cut", "7 failures", game=True, suites=("game",),
          desc="the network between the games is cut mid-match: both report a disconnect, void, no blame")
def fail_net_cut(ctx):
    a, b = _two(ctx, "E2E Jo", "E2E Kim")
    ctx.shaper.set(10, 0, 0)
    mid = queue_match(ctx, a, b, "quick")
    wait_fight(ctx, mid, (a, b))
    ctx.sleep(10)
    t = time.time()
    ctx.shaper.cut = True
    ctx.note("link cut (all packets dropped both ways)")
    wait_results(ctx, mid, (a, b), 120)
    ctx.note(f"results after {time.time() - t:.0f} s")
    ha = [h for m_, h in a.tab.driver.history if m_ == mid]
    hb = [h for m_, h in b.tab.driver.history if m_ == mid]
    ctx.check("both report a disconnect", ha and hb and ha[-1].get("source") == "disconnect" and
              hb[-1].get("source") == "disconnect", f"{ha[-1] if ha else None} / {hb[-1] if hb else None}")
    ma = a.matches.get(mid, {})
    ctx.check("lobby: void (connection), nobody blamed", ma.get("status") == "void" and ma.get("reason") == "connection"
              and ma.get("blame") is None, f"{ma.get('status')} {ma.get('reason')} blame {ma.get('blame')}")
    ctx.shaper.cut = False
    _next_match_ok(ctx, a, b, "next match after the cut")


@scenario("fail_restart_between", "7 failures", game=True, suites=("game",),
          desc="one player closes the game between matches; Rematch then starts it fresh (fresh vs played game), "
               "then a rematch in that session")
def fail_restart_between(ctx):
    a, b = _two(ctx, "E2E Lea", "E2E Moe")
    mid = queue_match(ctx, a, b, "quick")
    wait_fight(ctx, mid, (a, b))
    wait_results(ctx, mid, (a, b))
    match_row(ctx, mid, (a, b), "confirmed", "match 1")
    status1 = b.matches[mid].get("status")
    n = close_window(b)
    ctx.note(f"{b.name} closes the game at the result screen ({n} window(s))")
    ctx.wait(lambda: not b.game_running(), 20, "the game closed")
    ctx.note(f"exit code {game_exit_code(b)}")
    ctx.sleep(1)
    hist = [h for m_, h in b.tab.driver.history if m_ == mid]
    ctx.check("nothing more reported for the finished match", len(hist) == 1, hist)
    mid2 = rematch(ctx, a, b)
    ctx.check("rematch with a new connection (the game is gone)", not a.matches[mid2].get("cont"))
    wait_fight(ctx, mid2, (a, b), timeout=180)
    wait_results(ctx, mid2, (a, b))
    match_row(ctx, mid2, (a, b), "confirmed", "match 2: fresh game vs played game")
    ctx.check("the closer runs a new game, the other the same one", len(b.games) == 2 and len(a.games) == 1)
    mid3 = rematch(ctx, a, b)
    wait_fight(ctx, mid3, (a, b))
    wait_results(ctx, mid3, (a, b))
    match_row(ctx, mid3, (a, b), "confirmed", "match 3: rematch in that session")
    ctx.check("match 1 stays confirmed", status1 == "confirmed")


@scenario("version_lobby", "7 failures", suites=("quick", "lobby"),
          desc="another build in the lobby: marked, never paired by the queue, room join and challenge refused; "
               "a server pinned to one build and an old lobby protocol are refused at the door")
def version_lobby(ctx):
    stub_server(ctx)
    a = ctx.player("E2E Ned", kind="stub")
    login(ctx, a)
    c = ctx.player("E2E Old", kind="stub")
    ob = other_build(c)
    c.tab._build_info = lambda: (ob, None)
    login(ctx, c)
    ctx.wait(lambda: any("other version" in str(c.tab.tv_players.item(i, "values")) for i in c.tab.tv_players.get_children()),
             10, "the lobby list marks the other build")
    a.press("room")
    ctx.wait(lambda: len(c.tab.tv_rooms.get_children()) == 1, 10, "room listed")
    ctx.check("the room list marks the other build", "other version" in str(c.tab.tv_rooms.item(
        c.tab.tv_rooms.get_children()[0], "values")))
    t = time.time()
    c.tab.tv_rooms.selection_set(c.tab.tv_rooms.get_children()[0])
    c.press("join")
    ctx.wait(lambda: c.saw_status("different build", t), 10, "joining a room of another build is refused")
    a.press("leave")
    ctx.wait(lambda: a.action_on("quick"), 10)
    t = time.time()
    a.press("quick")
    c.press("quick")
    ctx.check("queue never pairs different builds", not ctx.wait(lambda: latest(c, "match_found", t), 8, fail=False))
    a.press("cancel")
    c.press("cancel")
    ctx.sleep(1)
    c.tab.tv_players.selection_set(a.client.me["id"])
    t = time.time()
    c.press("challenge")
    ctx.wait(lambda: c.saw_status("different build", t), 10, "challenging another build is refused")
    # a server that accepts one build only (T5L_BUILDS), and a launcher with an older lobby protocol
    from t5lobby import proto
    from t5lobby.client import LobbyClient
    from t5lobby.proto import LobbyError
    mine, _ = a.tab._build_info()
    for p in (a, c):
        p.logout()
    ctx.wait(lambda: a.tab.client is None and c.tab.client is None, 10, "both log out")
    ctx.server.env["T5L_BUILDS"] = mine.build_id
    ctx.server.restart()
    t = time.time()
    c.tab.do_login("guest")
    ctx.wait(lambda: c.saw_status("not accepted by this server", t), 15,
             "a server pinned to one build refuses another at the door, with a sentence to update")
    ctx.check("... and the other build is not logged in", not c.logged_in())
    old = proto.PROTO_VERSION
    cl = LobbyClient(ctx.server.addr, mine)
    try:
        proto.PROTO_VERSION = old - 1 if old > 1 else old + 1
        try:
            cl.connect()
            ctx.check("an older lobby protocol is refused", False, "connected")
        except LobbyError as e:
            ctx.check("an older lobby protocol is refused", e.code == proto.E_PROTO and "update" in e.msg, f"{e.code}: {e.msg}")
    finally:
        proto.PROTO_VERSION = old
        cl.close()


@scenario("fail_version", "7 failures", game=True, suites=("game",),
          desc="two games told different build ids refuse each other: no fight, a disconnect for both, void; "
               "the next match with equal builds plays")
def fail_version(ctx):
    a, b = _two(ctx, "E2E Ned", "E2E Ora")
    # the games themselves: one told another build id
    ctx.shaper.build_override[b.name] = "e2e-tampered-build"
    mid = queue_match(ctx, a, b, "quick")
    wait_results(ctx, mid, (a, b), 150)
    ma = a.matches.get(mid, {})
    segs = [parse_segment(p.log_segment(mid)) for p in (a, b)]
    ctx.check("the games refused each other (build mismatch), no fight", all(s["build_mismatch"] for s in segs[:1]) and
              not any(fight_started(p, mid) for p in (a, b)),
              f"logs {[s['build_mismatch'] for s in segs]}, lost {[s['lost'] for s in segs]}")
    ctx.check("lobby: void, nobody rated", ma.get("status") == "void", f"{ma.get('status')} {ma.get('reason')}")
    hist = [h for p in (a, b) for m_, h in p.tab.driver.history if m_ == mid]
    ctx.note(f"reports: {hist}")
    ctx.shaper.build_override.clear()
    _next_match_ok(ctx, a, b, "next match with equal builds")


# ============================================================================== 8. launcher extras
@scenario("report_problem", "8 launcher", suites=("quick", "lobby"),
          desc="Report a problem after a match: one zip in our own folder, no user/PC/lobby names, IPs, tokens or keys")
def report_problem(ctx):
    import problem_report as report
    import problem_report_ui as report_ui
    import core
    stub_server(ctx)
    a = ctx.player("E2E Pia", kind="stub", password="pia-pass-1")
    b = ctx.player("E2E Rex", kind="stub")
    login(ctx, a, "register")
    login(ctx, b)
    mid = queue_match(ctx, a, b, "quick")
    wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
    # a real game log from this run when there is one (names, HUD lines, netplay lines), plus the lines an
    # internet match leaves (a public address, a match key)
    logs = os.path.join(a.out, "logs")
    real = [p for p in ctx.run.real_logs if os.path.isfile(p)]
    pub = "81.2.69.142"
    synth = os.path.join(logs, "game-29991231-235959.log")
    with open(synth, "w", encoding="utf-8") as f:
        if real:
            with open(real[-1], encoding="utf-8", errors="replace") as src:
                f.write(src.read()[-400000:])
        f.write(f"[netplay] calling {pub}:61234 while waiting (lobby punch / relay path)\n"
                f"[netplay] lobby match {mid} (path direct, measured rtt 31 ms)\n"
                f"[df] frame 1061: HUD identity: P1 'E2E Pia' rank 0, P2 'E2E Rex' rank 0\n"
                f"T5_NET_KEY=0123456789abcdef0123456789abcdef\n")
    root = os.path.join(ctx.dir, "install")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "launcher.json"), "w") as f:
        json.dump(dict(a.app.settings), f)
    llog = os.path.join(root, "launcher.log")
    with open(llog, "w") as f:
        f.write(f"2026-10-18 23:00:00 status: Connecting to {pub}:7781...\n")
    desk = os.path.join(ctx.dir, "Desktop")
    os.makedirs(desk, exist_ok=True)
    s = a.app.settings
    labels = {"display": dict(core.DISPLAY_MODES), "input_delay": core.INPUT_DELAYS}      # as t5dr_launcher.pyw
    if hasattr(core, "INTERNAL_RES_LABELS"):
        labels["internal_res"] = core.INTERNAL_RES_LABELS
    elif hasattr(core, "RENDER_SCALES"):
        labels["render_scale"] = core.RENDER_SCALES
    lines = report.settings_lines(s, labels, s.env_overrides(), s.out_dir)
    online_info = a.tab.report_info()

    def make_context():
        return report.Context(s.out_dir, root=root, launcher_log=llog, settings_lines=lines,
                              release={"version": "e2e"}, build_info=lambda: report.build_info_for(s.out_dir, {}, root),
                              online_dir=a.tab.user_dir, online_info=online_info)
    dlg = report_ui.ReportDialog(ctx.run.root, make_context, desk, reveal=None, visible=False)
    dlg.save()
    ctx.wait(lambda: dlg.result is not None or dlg.error is not None, 60, "the report zip is made")
    dlg.close()
    res = dlg.result
    if res is None:
        raise Abort(f"report failed: {dlg.error}")
    ctx.check("one zip, in the folder it was told (not the real Desktop)", os.path.dirname(res.path) == desk and
              res.path.endswith(".zip"), res.path)
    names = [m["name"] for m in res.members]
    ctx.note(f"zip {os.path.basename(res.path)} {res.zip_size} bytes: {names}; removed {dict(res.counts)}")
    ctx.check("zip has the system info, game log and the online files", "system.txt" in names and
              any(n.startswith("logs/") for n in names) and any(n.startswith("online/") for n in names), names)
    token = (a.tab._saved_session() or {}).get("token") or ""
    keys = set(re.findall(r'"T5_NET_KEY": "([^"]+)"', open(os.path.join(a.out, "logs", "online", "ctl", "cmd.json")).read())
               if os.path.exists(os.path.join(a.out, "logs", "online", "ctl", "cmd.json")) else [])
    user = getpass.getuser()
    pc = os.environ.get("COMPUTERNAME", "")
    leaks = {}
    with zipfile.ZipFile(res.path) as z:
        for n in z.namelist():
            data = z.read(n)
            text = data.decode("utf-8", "replace")
            for label, needle in (("windows user", user), ("pc name", pc), ("public ip", pub), ("login token", token),
                                  ("match key", "0123456789abcdef0123456789abcdef"),
                                  *(("match key", k) for k in keys),
                                  ("own lobby name", "E2E Pia"), ("opponent's lobby name", "E2E Rex")):
                if needle and len(needle) >= 3 and re.search(r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])",
                                                             text, re.I):
                    leaks.setdefault(label, []).append(n)
    for label in ("windows user", "pc name", "public ip", "login token", "match key"):
        ctx.check(f"zip: no {label}", label not in leaks, leaks.get(label))
    ctx.check("zip: no lobby player names (own or opponent)", "own lobby name" not in leaks and
              "opponent's lobby name" not in leaks, {k: v for k, v in leaks.items() if "name" in k})


class _Resp:
    def __init__(self, body=b"", headers=None):
        self.body = io.BytesIO(body)
        self.headers = headers or {}

    def read(self, n=-1):
        return self.body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass


@scenario("update_check", "8 launcher", suites=("quick", "lobby"),
          desc="the update check and download against mocked GitHub answers (no network): offer, cache, 304, "
               "rate limit, draft, 404, foreign host, checksum, stage and swap keeping native/")
def update_check(ctx):
    import updater as up
    inst = os.path.join(ctx.dir, "T5DR-Online-1.0.0")
    os.makedirs(os.path.join(inst, "launcher"), exist_ok=True)
    os.makedirs(os.path.join(inst, "native", "gamedata"), exist_ok=True)
    with open(os.path.join(inst, "release.json"), "w") as f:
        json.dump({"version": "1.0.0"}, f)
    with open(os.path.join(inst, "launcher", "t5dr_launcher.pyw"), "w") as f:
        f.write("# old launcher\n")
    with open(os.path.join(inst, "native", "gamedata", "save.bin"), "wb") as f:
        f.write(b"player save")
    with open(os.path.join(inst, "launcher.json"), "w") as f:
        json.dump({"nickname": "keep me"}, f)
    # the new release zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("T5DR-Online-1.0.1/release.json", json.dumps({"version": "1.0.1"}))
        z.writestr("T5DR-Online-1.0.1/launcher/t5dr_launcher.pyw", "# new launcher\n")
    zbytes = buf.getvalue()
    sha = hashlib.sha256(zbytes).hexdigest()
    base = "https://github.com/TheWishin/T5DROnline/releases/download/v1.0.1/"

    def release_json(**over):
        d = {"tag_name": "v1.0.1", "name": "T5DR Online 1.0.1", "draft": False, "prerelease": False,
             "html_url": "https://github.com/TheWishin/T5DROnline/releases/tag/v1.0.1", "published_at": "2026-10-19T00:00:00Z",
             "body": "## Fixes\n- rematch\n\n---\n| Code ID | `0123456789abcdef` |",
             "assets": [{"name": "T5DR-Online-1.0.1.zip", "browser_download_url": base + "T5DR-Online-1.0.1.zip",
                         "size": len(zbytes), "state": "uploaded", "digest": f"sha256:{sha}"},
                        {"name": "SHA256SUMS", "browser_download_url": base + "SHA256SUMS", "size": 100, "state": "uploaded"}]}
        d.update(over)
        return json.dumps(d).encode()

    calls = []
    plan = {"api": ("ok", release_json()), "zip": zbytes, "sums": f"{sha}  T5DR-Online-1.0.1.zip\n".encode()}

    def opener(url, headers=None, kind="download", timeout=None):
        calls.append((url, dict(headers or {})))
        if not up.url_allowed(url, kind):
            raise up.UpdateError("refused " + url)
        if kind == "api":
            what, body = plan["api"]
            if what == "ok":
                return _Resp(body, {"ETag": '"e2e-etag"'})
            raise urllib.error.HTTPError(url, what, "mock", body or {}, None)
        if url.endswith("SHA256SUMS"):
            return _Resp(plan["sums"])
        return _Resp(plan["zip"], {"Content-Length": str(len(plan["zip"]))})
    cache = os.path.join(inst, up.CACHE_FILE)
    now = time.time()
    rel, prob = up.check_latest(cache, opener=opener, now=now)
    ctx.check("published newer release offered", rel and rel["version"] == "1.0.1" and up.is_newer(rel["version"],
              up.local_version(inst)) and prob is None, f"{rel and rel['version']} {prob}")
    ctx.check("release notes summary and code id read", rel and "rematch" in rel["notes"] and rel["code_id"] == "0123456789abcdef")
    n = len(calls)
    rel2, _ = up.check_latest(cache, opener=opener, now=now + 60)
    ctx.check("within the hour: cached, no request", len(calls) == n and rel2 and rel2["version"] == "1.0.1")
    plan["api"] = (304, None)
    rel3, prob3 = up.check_latest(cache, force=True, opener=opener, now=now + 120)
    ctx.check("forced check: conditional request (ETag), 304 keeps the release",
              calls[-1][1].get("If-None-Match") == '"e2e-etag"' and rel3 and rel3["version"] == "1.0.1", prob3)
    plan["api"] = (403, {"X-RateLimit-Reset": str(int(now + 1800))})
    rel4, prob4 = up.check_latest(cache, force=True, opener=opener, now=now + 180)
    ctx.check("rate limit: a sentence, no offer", rel4 is None and prob4 and "limit" in prob4.lower(), prob4)
    n = len(calls)
    _rel5, prob5 = up.check_latest(cache, force=True, opener=opener, now=now + 240)
    ctx.check("rate limit remembered until GitHub's reset (no request)", len(calls) == n and prob5 and "wait" in prob5, prob5)
    os.remove(cache)
    plan["api"] = ("ok", release_json(draft=True))
    rel6, prob6 = up.check_latest(cache, force=True, opener=opener, now=now)
    ctx.check("a draft is never offered", rel6 is None and prob6, prob6)
    plan["api"] = (404, None)
    rel7, prob7 = up.check_latest(cache, force=True, opener=opener, now=now)
    ctx.check("no published release (404): nothing offered, no error", rel7 is None and prob7 is None, prob7)
    bad = json.loads(release_json())
    bad["assets"][0]["browser_download_url"] = "https://evil.example.com/T5DR-Online-1.0.1.zip"
    plan["api"] = ("ok", json.dumps(bad).encode())
    rel8, prob8 = up.check_latest(cache, force=True, opener=opener, now=now)
    ctx.check("an asset on another host is refused", rel8 is None and prob8 and "not on this project" in prob8, prob8)
    # download, verify, stage
    rel = up.parse_release(json.loads(release_json()))
    plan["zip"] = zbytes[:-1] + bytes([zbytes[-1] ^ 1])
    try:
        up.prepare_update(rel, root=inst, opener=opener, need_python=False)
        ctx.check("a damaged download is refused", False, "it was staged")
    except up.UpdateError as e:
        ctx.check("a damaged download is refused, nothing changed", "SHA-256" in str(e) or "damaged" in str(e) or
                  "not a readable zip" in str(e), str(e))
    ctx.check("old version still installed", up.local_version(inst) == "1.0.0")
    plan["zip"] = zbytes
    staged = up.prepare_update(rel, root=inst, opener=opener, need_python=False)
    ctx.check("the verified release is staged next to the install", os.path.isfile(os.path.join(staged["new"], "release.json")),
              staged)
    try:
        up.swap(inst, staged["new"], os.path.join(staged["sroot"], "backup"), "1.0.1", expect_python=False)
        ctx.check("swap: the new version is installed", up.local_version(inst) == "1.0.1")
        ctx.check("swap: native\\ and launcher.json kept", open(os.path.join(inst, "native", "gamedata", "save.bin"), "rb").read()
                  == b"player save" and json.load(open(os.path.join(inst, "launcher.json")))["nickname"] == "keep me")
    except Exception as e:      # noqa: BLE001
        ctx.check("swap", False, repr(e))


@scenario("i18n_de", "8 launcher", suites=("quick", "lobby"),
          desc="the Online tab in German: register, guest, quick match, accept, result, rematch offer and Leave, the "
               "problem report -- no launcher error, every text the tab shows has a German entry")
def i18n_de(ctx):
    try:
        from t5lobby import i18n
    except ImportError:
        raise Skip("this launcher has no translations (i18n is not merged)")
    prev = i18n.language()
    i18n.set_language("de")
    i18n.clear_missing()
    try:
        stub_server(ctx)
        a = ctx.player("E2E Uwe", kind="stub", password="uwe-pass-1")
        b = ctx.player("E2E Vera", kind="stub")
        ctx.check("the tab is built in German", a.tab.b_guest.cget("text") == i18n.t("Play as guest") != "Play as guest",
                  a.tab.b_guest.cget("text"))
        login(ctx, a, "register")
        login(ctx, b, "guest")
        t = time.time()
        a.press("quick")
        ctx.sleep(0.3)
        b.press("quick")
        mid = found_both(ctx, a, b, t)
        ctx.check("the ready bar is German", a.bar_button("Accept") is not None and
                  a.bar_button("Accept").cget("text").startswith(i18n.t("Accept")), a.bar_labels())
        accept(ctx, a, mid)
        accept(ctx, b, mid)
        started_both(ctx, a, b, mid)
        wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
        ctx.check("the result is confirmed", a.matches[mid].get("status") == "confirmed", a.matches[mid].get("status"))
        ctx.note(f"status lines: {a.status_text()!r} / {b.status_text()!r}")
        t = time.time()
        ctx.wait(lambda: a.bar_button("Rematch") is not None, 15, "German result bar with Rematch")
        a.click("Rematch")
        ctx.wait(lambda: b.bar_button("No thanks") is not None or b.bar_button("Leave") is not None, 15,
                 "the offer reaches the other player")
        leave(ctx, b)
        ctx.wait(lambda: any(ev.get("state") == "declined" for ev in a.events_of("rematch", t)), 10, "declined")
        a.logout(forget=False)
        ctx.wait(lambda: a.tab.client is None, 10, "log out")
        miss = [m for m in i18n.missing() if not m.startswith("E2E")]
        ctx.check("every text shown has a German entry", not miss, miss[:30])
    finally:
        i18n.set_language(prev)


@scenario("settings_persist", "8 launcher", suites=("quick", "lobby"),
          desc="launcher settings and Online tab settings survive a restart; the speed of the last match is kept")
def settings_persist(ctx):
    import core
    stub_server(ctx)
    path = os.path.join(ctx.dir, "launcher.json")
    s = core.Settings(path)
    keys = [k for k in ("display", "internal_res", "render_scale", "input_delay", "mute", "nickname", "extra_env",
                        "language") if k in core.DEFAULTS]
    s.update(display="borderless", input_delay="2", mute=True, nickname="E2E Sue", extra_env="FOO_E2E=1")
    if "internal_res" in core.DEFAULTS:
        s["internal_res"] = "1440p"
    else:
        s["render_scale"] = "0.75"
    if "language" in core.DEFAULTS:
        s["language"] = "de"
    s.save()
    s2 = core.Settings(path)
    ctx.check("launcher.json: every setting back after a restart", all(s2[k] == s[k] for k in keys),
              {k: s2[k] for k in keys if k != "extra_env"})
    env = s2.env_overrides()
    if "internal_res" in core.DEFAULTS:
        res_ok = env.get("PS3_INTERNAL_RES") == "1440p"
    else:
        res_ok = env.get("PS3_RENDER_SCALE") == "0.75"
    ctx.check("settings reach the game: input delay, internal resolution, nickname, extra lines",
              env.get("T5_RB_NET_DELAY") == "2" and res_ok and env.get("FOO_E2E") == "1"
              and env.get("PS3_NICKNAME") == "E2E Sue", env)
    a = ctx.player("E2E Sue", kind="stub", input_delay="1")
    b = ctx.player("E2E Tom", kind="stub")
    a.tab.strict_var.set(1)
    a.set_char("feng", send=False)
    login(ctx, a)
    login(ctx, b)
    ctx.check("the player's input delay reaches the match driver", a.tab.driver.input_delay == "1", a.tab.driver.input_delay)
    mid = queue_match(ctx, a, b, "quick")
    wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
    ctx.wait(lambda: a.tab.cfg.get("last_fps"), 10, "the last match's speed is kept")
    a.tab._save_cfg()
    a2 = ctx.player("E2E Sue", kind="stub", tag="restart", user_dir=a.user_dir)
    cfg = a2.tab.cfg
    ctx.check("online.json: server, name, character, strict, last speed back after a restart",
              cfg.get("server") == ctx.server.addr and cfg.get("name") == "E2E Sue" and cfg.get("char") == "feng"
              and cfg.get("strict") is True and cfg.get("last_fps"),
              {k: cfg.get(k) for k in ("server", "name", "char", "strict", "last_fps")})
    ctx.check("the tab shows them", a2.tab.char_var.get() == "Feng" and a2.tab.strict_var.get() == 1)


# ============================================================================== 11. opponents and characters (owner, 1.0.0)
def _play(ctx, a, b, mid, label, timeout=180):
    """Wait for this match's fight and both results, then check it like every match (fighters, sync)."""
    ok = wait_fight(ctx, mid, (a, b), timeout=timeout)
    wait_results(ctx, mid, (a, b))
    row = match_row(ctx, mid, (a, b), "confirmed", label)
    if not ok:
        for p in (a, b):
            st = p.tab.driver.df_status if p.tab.driver else None
            ctx.note(f"{label}: {p.name}'s game status {st}")
    return row


def _new_pairing(ctx, a, b, label):
    for p in ctx.players:
        leave(ctx, p)
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 60, f"{label}: both free to search")
    ctx.sleep(1)
    return queue_match(ctx, a, b, "quick")


@scenario("opponent_switch", "11 opponents and characters", game=True, suites=("game",),
          desc="A and B play a match and a rematch; A (played game) meets C (fresh game); C meets B (both played "
               "other opponents); B restarts its game and meets A again, then a rematch")
def opponent_switch(ctx, rtt=None):
    game_server(ctx)
    if rtt:
        ctx.shaper.set(rtt, rtt / 6.0, 0.5)
    a = ctx.player("E2E Ava", char="kazuya")
    b = ctx.player("E2E Bo", char="lili")
    c = ctx.player("E2E Cy", char="steve")
    for p, ch in ((a, "kazuya"), (b, "lili"), (c, "steve")):
        login(ctx, p)
        p.set_char(ch)
    mid = queue_match(ctx, a, b, "quick")
    _play(ctx, a, b, mid, "A-B match 1 (both fresh)")
    mid = rematch(ctx, a, b)
    _play(ctx, a, b, mid, "A-B rematch")
    pid_a = a.game().proc.pid
    mid = _new_pairing(ctx, a, c, "A-C")
    ctx.check("A keeps its game, C starts its first", a.game().proc.pid == pid_a and len(c.games) == 1)
    _play(ctx, a, c, mid, "A (played 2 matches) vs C (fresh game)")
    mid = _new_pairing(ctx, c, b, "C-B")
    _play(ctx, c, b, mid, "C vs B (both played other opponents)")
    for p in (c, b):
        leave(ctx, p)
    n = close_window(b)
    ctx.note(f"{b.name} closes its game between matches ({n} window(s))")
    ctx.wait(lambda: not b.game_running(), 20, "B's game closed")
    mid = _new_pairing(ctx, b, a, "B-A")
    ctx.check("B starts a fresh game, A keeps its own", len(b.games) == 2 and a.game().proc.pid == pid_a)
    _play(ctx, b, a, mid, "B (restarted, fresh) vs A (played 4 matches)")
    mid = rematch(ctx, b, a)
    _play(ctx, b, a, mid, "B-A rematch after the switch")


@scenario("rematch_char_change", "11 opponents and characters", game=True, suites=("game",),
          desc="casual rematch with a character change: P1 changes, P2 changes, both change -- each rematch starts on "
               "both PCs with the new fighters and stays in sync")
def rematch_char_change(ctx, rtt=None):
    game_server(ctx)
    if rtt:
        ctx.shaper.set(rtt, rtt / 6.0, 0.5)
    a = ctx.player("E2E Cat", char="paul")
    b = ctx.player("E2E Dov", char="nina")
    login(ctx, a)
    login(ctx, b)
    a.set_char("paul")
    b.set_char("nina")
    mid = queue_match(ctx, a, b, "quick")
    _play(ctx, a, b, mid, "match 1")
    p1, p2 = (a, b) if a.matches[mid].get("slot") == 0 else (b, a)
    for label, change in (("P1 changes (rematch)", {p1: "king"}), ("P2 changes (rematch)", {p2: "asuka"}),
                          ("both change (rematch)", {p1: "steve", p2: "hwoarang"}),
                          ("nobody changes (rematch)", {})):
        t = time.time()
        for p, key in change.items():
            ctx.wait(lambda p=p: str(p.tab.char_cb.cget("state")) == "readonly", 10, f"{p.name}: character box open")
            p.set_char(key)
        ctx.sleep(1.5)
        ctx.check(f"{label}: no character change refused", not any(p.saw_status("locked|Lobby:", t) for p in (a, b)),
                  [p.status_text() for p in (a, b)])
        want = {p: change.get(p) for p in (p1, p2)}
        mid = rematch(ctx, a, b)
        f = a.matches[mid].get("fight") or {}
        ctx.check(f"{label}: continues in the running session", a.matches[mid].get("cont"))
        ctx.check(f"{label}: the lobby sends the new fighters", (want[p1] is None or f.get("p1") == want[p1]) and
                  (want[p2] is None or f.get("p2") == want[p2]), f"fight {f.get('p1')} vs {f.get('p2')}, wanted "
                  f"{want[p1] or 'same'} vs {want[p2] or 'same'}")
        _play(ctx, a, b, mid, label)


@scenario("rematch_char_change_edge", "11 opponents and characters", game=True, suites=("game",),
          desc="rematches that move the cursor from Bruce or Kuma (the select grid's right edge) to the top row and "
               "back, on both sides (the owner's 'rematch with a character change' hang, fixed by rollback-crash)")
def rematch_char_change_edge(ctx, rtt=None):
    game_server(ctx)
    if rtt:
        ctx.shaper.set(rtt, rtt / 6.0, 0.5)
    a = ctx.player("E2E Edge1", char="bruce")
    b = ctx.player("E2E Edge2", char="kuma")
    login(ctx, a)
    login(ctx, b)
    a.set_char("bruce")
    b.set_char("kuma")
    mid = queue_match(ctx, a, b, "quick")
    _play(ctx, a, b, mid, "match 1 (Bruce vs Kuma)")
    for label, change in (("Bruce -> Raven (top row)", {a: "raven"}),
                          ("Kuma -> Feng (top row)", {b: "feng"}),
                          ("back to Kuma and Bruce", {a: "kuma", b: "bruce"}),
                          ("Kuma -> Eddy, Bruce -> Devil Jin (both to the top row)", {a: "eddy", b: "devil_jin"}),
                          ("top row -> Bruce and Kuma", {a: "bruce", b: "kuma"}),
                          ("Bruce -> Wang, Kuma -> Armor King (top row, the far ends)", {a: "wang", b: "armor_king"})):
        t = time.time()
        for p, key in change.items():
            ctx.wait(lambda p=p: str(p.tab.char_cb.cget("state")) == "readonly", 10, f"{p.name}: character box open")
            p.set_char(key)
        ctx.sleep(1.5)
        ctx.check(f"{label}: no character change refused", not any(p.saw_status("locked|Lobby:", t) for p in (a, b)),
                  [p.status_text() for p in (a, b)])
        mid = rematch(ctx, a, b)
        f = a.matches[mid].get("fight") or {}
        picks = _picks(a, b, mid)
        ctx.check(f"{label}: continues in the running session", a.matches[mid].get("cont"))
        ctx.check(f"{label}: the lobby sends the new fighters", all(picks.get(p.name) == key for p, key in change.items()),
                  f"fight {f.get('p1')} vs {f.get('p2')}, picks {picks}")
        _play(ctx, a, b, mid, label)


@scenario("ranked_same_address", "3 ranked", suites=("quick", "lobby"),
          desc="lobby-hardening: two accounts on one internet address never play ranked against each other -- the queue "
               "does not pair them and a ranked room's match is played unranked, both told (T5L_RANKED_SAME_IP=0)")
def ranked_same_address(ctx):
    stub_server(ctx, T5L_RANKED_SAME_IP=0)
    a = ctx.player("E2E Alt1", kind="stub", password="alt1-pass-1")
    b = ctx.player("E2E Alt2", kind="stub", password="alt2-pass-1")
    login(ctx, a, "register")
    login(ctx, b, "register")
    t = time.time()
    a.press("ranked")
    ctx.sleep(0.3)
    b.press("ranked")
    ctx.check("the ranked queue never pairs two accounts on one address",
              not ctx.wait(lambda: latest(a, "match_found", t), 10, fail=False))
    a.press("cancel")
    b.press("cancel")
    ctx.wait(lambda: a.action_on("ranked") and b.action_on("ranked"), 10)
    box = a.call(a.client.create_room, "E2E same address", True)
    ctx.wait(lambda: box, 10, "ranked room created")
    rid = (box.get("ok") or {}).get("id")
    ctx.wait(lambda: b.tab.tv_rooms.exists(rid), 10, "room listed")
    t = time.time()
    b.tab.tv_rooms.selection_set(rid)
    b.press("join")
    mid = found_both(ctx, a, b, t)
    ctx.check("the ranked room's match is played unranked", not a.matches[mid].get("ranked"), a.matches[mid].get("ranked"))
    ctx.check("both are told why", any(ev.get("code") == "same_address" for ev in a.events_of("notice", t)) and
              any(ev.get("code") == "same_address" for ev in b.events_of("notice", t)))


@scenario("opponent_switch_rtt", "11 opponents and characters", game=True, suites=("game",),
          desc="opponent_switch over an internet-like link: RTT 30 ms, jitter +-5 ms, 0.5% loss (the owner's 1.0.0 "
               "game had RTT 26 ms)")
def opponent_switch_rtt(ctx):
    opponent_switch(ctx, rtt=30)


@scenario("rematch_char_change_rtt", "11 opponents and characters", game=True, suites=("game",),
          desc="rematch_char_change over RTT 30 ms, jitter +-5 ms, 0.5% loss")
def rematch_char_change_rtt(ctx):
    rematch_char_change(ctx, rtt=30)


# ============================================================================== 9. character select (ingame-select)
def _need_ingame_pick():
    """The in-game select (branch ingame-select): the lobby offers it ('ingame_pick') and the test helpers that
    press the picks closed-loop on the cursor cell (tools/pick_flow_test.py) are in this tree."""
    if "ingame_pick" not in features() or not os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "pick_flow_test.py")):
        raise Skip("in-game character select is not on this branch yet (no 'ingame_pick' in the lobby's features, "
                   "no tools/pick_flow_test.py; branch ingame-select)")
    import pick_flow_test
    return pick_flow_test


class _PadGame:
    """What pick_flow_test.Picker needs from a game: its log and its pad file (PS3_PAD_FILE)."""

    def __init__(self, p):
        self.p = p
        self.pad_path = os.path.join(p.dir, "pad.txt")

    @property
    def log_path(self):
        g = self.p.game()
        return g.log_path if g is not None else None

    def log_since(self, pos):
        try:
            with open(self.log_path, "rb") as f:
                f.seek(pos)
                return f.read().decode("utf-8", "replace")
        except (OSError, TypeError):
            return ""

    def pad(self, text):
        for _ in range(100):
            try:
                with open(self.pad_path, "w") as f:
                    f.write(text)
                return
            except PermissionError:
                time.sleep(0.002)

    def press(self, buttons, hold=0.08, gap=0.17):
        self.pad(buttons)
        time.sleep(hold)
        self.pad("")
        time.sleep(gap)


def _cs_player(ctx, name, **kw):
    import re as _re
    d = os.path.join(ctx.dir, _re.sub(r"[^A-Za-z0-9_.-]", "_", name))
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "pad.txt"), "w").close()
    env = {"PS3_PAD_FILE": os.path.join(d, "pad.txt"), "T5_DF_TRACE": "1", "T5_NET_SCRIPT_FIGHT": "1"}
    env.update(kw.pop("env", {}))
    return ctx.player(name, env=env, **kw)


def _cs_match(ctx, pf, a, b, specs, label, mode="quick", again=False, expect_pick=True, prev=None):
    """One match picked on the select screen: specs = {player name: pick_flow_test scenario}
    (<char>:<lp|rp|lk|rk>, random, timeout). Checks both games fought the same fighters, what was
    asked for, no PICK MISMATCH, and the usual result evidence. Returns (match id, fighters line)."""
    if prev is not None:
        mid = _next_set_game(ctx, a, b, prev, label)          # a ranked set's next game comes by itself
    else:
        mid = rematch(ctx, a, b) if again else queue_match(ctx, a, b, mode)
    fight = a.matches[mid].get("fight") or {}
    ctx.check(f"{label}: the lobby {'offers' if expect_pick else 'does not offer'} the in-game select",
              bool(fight.get("pick")) == expect_pick, f"fight.pick {fight.get('pick')}")
    pickers = []
    for p in (a, b):
        mark = p.matches[mid].get("log_mark")
        if expect_pick:
            pk = pf.Picker(_PadGame(p), specs[p.name], mark[1] if mark else 0, time.time() + 150)
            pk.start()
            pickers.append((p, pk))
    wait_fight(ctx, mid, (a, b), timeout=200)
    for p, pk in pickers:
        pk.join(5)
        if pk.note:
            ctx.check(f"{label}: {p.name}'s pick pressed", False, pk.note)
    wait_results(ctx, mid, (a, b))
    match_row(ctx, mid, (a, b), "confirmed", label)
    lines = {}
    for p in (a, b):
        seg = "\n".join(p.log_segment(mid))
        m = pf.RE_PICKS.search(seg)
        lines[p.name] = m.groups() if m else None
        ctx.check(f"{label}: {p.name}: no PICK MISMATCH", "PICK MISMATCH" not in seg)
    ctx.check(f"{label}: both games fought the same fighters (character, costume, model)",
              lines[a.name] is not None and lines[a.name] == lines[b.name], lines)
    got = lines[a.name]
    if got and expect_pick:
        for p in (a, b):
            slot = p.matches[mid].get("slot")
            line_char = fight.get("p1") if slot == 0 else fight.get("p2")
            want = pf.expected(specs[p.name], line_char)
            have = (got[0], got[1]) if slot == 0 else (got[3], got[4])
            if want is not None:
                ctx.check(f"{label}: {p.name} (P{slot + 1}) got {want[0]} with {want[1]}", have == want, f"got {have}")
    return mid, got


def _cs_two(ctx, n1, n2, ranked=False, pick=30, **srv):
    pf = _need_ingame_pick()
    ctx.manual_pick = True                       # these scenarios press their own picks
    game_server(ctx, T5L_INGAME_PICK=pick, T5L_PLACEMENT=1, **srv)
    a = _cs_player(ctx, n1, password=f"{n1.split()[-1].lower()}-pass-1" if ranked else None, char="king")
    b = _cs_player(ctx, n2, password=f"{n2.split()[-1].lower()}-pass-1" if ranked else None, char="lili")
    login(ctx, a, "register" if ranked else "guest")
    login(ctx, b, "register" if ranked else "guest")
    a.set_char("king")
    b.set_char("lili")
    return pf, a, b


@scenario("cs_pick", "9 character select", game=True, suites=("game",), needs="ingame_pick",
          desc="both pick on the game's own select screen (Jin / Asuka); the picks are exchanged and fought")
def cs_pick(ctx):
    pf, a, b = _cs_two(ctx, "E2E Pick1", "E2E Pick2")
    _cs_match(ctx, pf, a, b, {a.name: "jin:lk", b.name: "asuka:lp"}, "pick")


@scenario("cs_costume", "9 character select", game=True, suites=("game",), needs="ingame_pick",
          desc="the costume is the confirm button: Xiaoyu with RK, Lili with RP, the same model on both PCs")
def cs_costume(ctx):
    pf, a, b = _cs_two(ctx, "E2E Cos1", "E2E Cos2")
    _cs_match(ctx, pf, a, b, {a.name: "xiaoyu:rk", b.name: "lili:rp"}, "costume")


@scenario("cs_mirror", "9 character select", game=True, suites=("game",), needs="ingame_pick",
          desc="a mirror match picked in the game (both Steve with Square): both PCs give the second costume to the "
               "same side and stay in sync; then both Jin with different buttons")
def cs_mirror(ctx):
    pf, a, b = _cs_two(ctx, "E2E Mir1", "E2E Mir2")
    _cs_match(ctx, pf, a, b, {a.name: "steve:lp", b.name: "steve:lp"}, "mirror, same button")
    _cs_match(ctx, pf, a, b, {a.name: "jin:lk", b.name: "jin:rp"}, "mirror, different buttons", again=True)


@scenario("cs_random", "9 character select", game=True, suites=("game",), needs="ingame_pick",
          desc="Random (Select) on the select screen: drawn on that PC, the same fighter on both PCs")
def cs_random(ctx):
    pf, a, b = _cs_two(ctx, "E2E Rnd1", "E2E Rnd2")
    _cs_match(ctx, pf, a, b, {a.name: "random", b.name: "random"}, "random")


@scenario("cs_timeout", "9 character select", game=True, suites=("game",), needs="ingame_pick",
          desc="one player picks nothing: after the pick time (10 s here, 30 s by default) the launcher's character")
def cs_timeout(ctx):
    pf, a, b = _cs_two(ctx, "E2E Late1", "E2E Late2", pick=10)
    _cs_match(ctx, pf, a, b, {a.name: "timeout", b.name: "paul:rp"}, "timeout")


@scenario("cs_rematch_select", "9 character select", game=True, suites=("game",), needs="ingame_pick",
          desc="a rematch goes back to the select screen; a new pick is fought, twice")
def cs_rematch_select(ctx):
    pf, a, b = _cs_two(ctx, "E2E Rem1", "E2E Rem2")
    _mid, f1 = _cs_match(ctx, pf, a, b, {a.name: "jin:lk", b.name: "law:lp"}, "match 1")
    _mid, f2 = _cs_match(ctx, pf, a, b, {a.name: "nina:rp", b.name: "steve:lk"}, "rematch 1", again=True)
    _mid, f3 = _cs_match(ctx, pf, a, b, {a.name: "random", b.name: "timeout"}, "rematch 2", again=True)
    ctx.check("each rematch fought its new picks", f1 != f2 and f2 != f3, [f1, f2, f3])


@scenario("cs_ranked_lock", "9 character select", game=True, suites=("game",), needs="ingame_pick",
          desc="ranked set: game 1 picked in the game; the rematches skip the select screen and keep those fighters")
def cs_ranked_lock(ctx):
    pf, a, b = _cs_two(ctx, "E2E Lock1", "E2E Lock2", ranked=True)
    mid, f1 = _cs_match(ctx, pf, a, b, {a.name: "bryan:lk", b.name: "julia:rp"}, "ranked game 1", mode="ranked")
    _mid, f2 = _cs_match(ctx, pf, a, b, {}, "ranked game 2 (locked)", again=True, expect_pick=False,
                         prev=mid if _set_of(a, mid).get("rated") else None)
    ctx.check("game 2 kept game 1's fighters (the lock)", f1 is not None and f1 == f2, [f1, f2])
    prof = profile(ctx, a) or {}
    ctx.check("the history records the fighters the game fought with",
              any(h.get("you_char") in ("bryan", "julia") for h in prof.get("history", [])), prof.get("history"))


# ============================================================================== 10. ranked sets (best of 3)
# The set rules with the stub game (seconds per game): planned winners (T5_STUB_WINNERS, by side: 0 = P1),
# a window closed in game k (T5_STUB_FAIL=close, T5_STUB_FAIL_AT=k), desyncs (T5_STUB_DESYNC_AT).
def _need_bo3():
    if "ranked_sets" not in features():
        raise Skip("best-of-3 ranked sets are not on this branch yet (branch ranked-sets)")


def _bo3_pair(ctx, n1, n2, env1=None, env2=None, sets=(None, None), **srv):
    _need_bo3()
    stub_server(ctx, T5L_PLACEMENT=1, **srv)
    a = ctx.player(n1, kind="stub", password=f"{n1.split()[-1].lower()}-pass-1", env=env1, sets=sets[0])
    b = ctx.player(n2, kind="stub", password=f"{n2.split()[-1].lower()}-pass-1", env=env2, sets=sets[1])
    login(ctx, a, "register")
    login(ctx, b, "register")
    return a, b


def _stub_set(ctx, a, b, mid, label, games_max=6, timeout=150):
    """Follow a stub set until set_end: every game's result (no rating on its own), the next game started by itself.
    Returns (set_end of a, set_end of b, [(match id, status, set number, continued)])."""
    t0 = min(p.matches.get(mid, {}).get("started") or time.time() for p in (a, b))   # (not before this set began: the last set's set_end can be a moment old)
    seen = []
    for _ in range(games_max):
        wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
        m = a.matches.get(mid, {})
        seen.append((mid, m.get("status"), (m.get("set_start") or {}).get("number"), m.get("cont")))
        if ctx.wait(lambda: a.events_of("set_end", t0), 2.0):
            break
        since = max(p.matches[mid].get("result") or 0 for p in (a, b)) - 0.5
        if not ctx.wait(lambda: latest(a, "match_start", since) and latest(b, "match_start", since), 30):
            break
        mid = latest(a, "match_start", since)["match"]
    ctx.wait(lambda: a.events_of("set_end", t0) and b.events_of("set_end", t0), timeout, f"{label}: the set ends")
    ctx.note(f"{label}: games {seen}")
    ea, eb = latest(a, "set_end", t0) or {}, latest(b, "set_end", t0) or {}
    if ea.get("rated") and (ea.get("rating") or {}).get("delta"):
        _rated_once(ctx, a, b, [x[0] for x in seen], (ea, eb), label)
    return ea, eb, seen


def _rating_once(ctx, a, b, ea, eb, label):
    for p, e in ((a, ea), (b, eb)):
        d = (e.get("rating") or {}).get("delta")
        ctx.check(f"{label}: {p.name}'s rating changed once, at the end", e.get("rated") and d not in (None, 0), d)


@scenario("bo3_2_0", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="ranked set won 2-0: two games, the second by itself after the countdown, the set ends, rated once")
def bo3_2_0(ctx):
    w = {"T5_STUB_WINNERS": "0,0,0"}
    a, b = _bo3_pair(ctx, "E2E Ann0", "E2E Bea0", w, w)
    mid = queue_match(ctx, a, b, "ranked")
    ea, eb, seen = _stub_set(ctx, a, b, mid, "2-0 set")
    p1 = a if a.matches[mid].get("slot") == 0 else b
    e1 = ea if p1 is a else eb
    ctx.check("2-0 for P1 in two games, status confirmed", e1.get("wins") == [2, 0] and e1.get("games") == 2 and
              e1.get("result") == "win" and e1.get("status") == "confirmed", e1)
    ctx.check("game 2 continued in the running games", len(seen) == 2 and seen[1][3] and seen[1][2] == 2, seen)
    _rating_once(ctx, a, b, ea, eb, "2-0 set")
    prof = profile(ctx, a) or {}
    ctx.check("profile: one ranked set, its two games in the history", prof.get("ranked_games") == 1 and
              len([h for h in prof.get("history", []) if h.get("set")]) == 2, f"ranked_games {prof.get('ranked_games')}, "
              f"history {len(prof.get('history', []))}, sets {len(prof.get('sets') or [])}")


@scenario("bo3_2_1", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="ranked set won 2-1: P1, P2, P1 -- three games, rated once")
def bo3_2_1(ctx):
    w = {"T5_STUB_WINNERS": "0,1,0"}
    a, b = _bo3_pair(ctx, "E2E Ann1", "E2E Bea1", w, w)
    mid = queue_match(ctx, a, b, "ranked")
    ea, eb, seen = _stub_set(ctx, a, b, mid, "2-1 set")
    p1 = a if a.matches[mid].get("slot") == 0 else b
    e1 = ea if p1 is a else eb
    ctx.check("2-1 for P1 in three games", e1.get("wins") == [2, 1] and e1.get("games") == 3 and e1.get("result") == "win",
              e1)
    _rating_once(ctx, a, b, ea, eb, "2-1 set")


def _bo3_quit(ctx, k):
    w = {"T5_STUB_WINNERS": "0,1,0"}
    a, b = _bo3_pair(ctx, f"E2E Qa{k}", f"E2E Qb{k}", w, dict(w, T5_STUB_FAIL="close", T5_STUB_FAIL_AT=str(k)))
    mid = queue_match(ctx, a, b, "ranked")
    ea, eb, seen = _stub_set(ctx, a, b, mid, f"quit in game {k}")
    ctx.check(f"a quit in game {k}: the quitter loses the set at once (forfeit), whatever the score",
              eb.get("result") == "loss" and ea.get("result") == "win" and eb.get("status") == "forfeit",
              f"{b.name}: {eb.get('result')} {eb.get('status')} {eb.get('wins')}")
    ctx.check(f"the set ended in game {k}", len(seen) == k, seen)
    hist = [h for _m, h in b.tab.driver.history]
    ctx.check("the quitter's launcher reported 'quit'", hist and hist[-1].get("source") == "quit", hist[-1:] if hist else hist)
    _rating_once(ctx, a, b, ea, eb, f"quit in game {k}")


@scenario("bo3_quit_g1", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="the window closed in game 1 of a ranked set: the set is lost at once")
def bo3_quit_g1(ctx):
    _bo3_quit(ctx, 1)


@scenario("bo3_quit_g2", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="the window closed in game 2 of a ranked set (1-0): the set is lost at once")
def bo3_quit_g2(ctx):
    _bo3_quit(ctx, 2)


@scenario("bo3_quit_g3", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="the window closed in game 3 of a ranked set (1-1): the set is lost at once")
def bo3_quit_g3(ctx):
    _bo3_quit(ctx, 3)


@scenario("bo3_leave_set", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="Leave set between two games (after game 1 counted) loses the set; queueing mid-set is refused")
def bo3_leave_set(ctx):
    w = {"T5_STUB_WINNERS": "0,1,0"}
    a, b = _bo3_pair(ctx, "E2E Lea1", "E2E Lea2", w, w, T5L_SET_NEXT_SECONDS=12)
    t0 = time.time()
    mid = queue_match(ctx, a, b, "ranked")
    wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
    ctx.wait(lambda: b.bar_button("Leave set") is not None, 10, "Leave set offered during the countdown")
    box = b.call(b.client.ranked_match)
    ctx.wait(lambda: box, 10)
    ctx.check("queueing between two games of a set is refused", "err" in box or b.saw_status("set", t0), b.status_text())
    t = time.time()
    b.answer_yes_no = True
    b.click("Leave set")
    ctx.wait(lambda: a.events_of("set_end", t) and b.events_of("set_end", t), 15, "Leave set ends the set")
    eb, ea = latest(b, "set_end", t) or {}, latest(a, "set_end", t) or {}
    ctx.check("leaving after a counted game loses the set", eb.get("result") == "loss" and ea.get("result") == "win"
              and eb.get("status") == "forfeit", f"{eb.get('result')} {eb.get('status')} {eb.get('wins')}")
    ctx.check("no next game starts", not ctx.wait(lambda: latest(a, "match_start", t), 14, fail=False))
    _rating_once(ctx, a, b, ea, eb, "left set")


@scenario("bo3_desync_replay", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="a desynced game is played again (same number, a new connection); three desyncs void the set")
def bo3_desync_replay(ctx):
    w = {"T5_STUB_WINNERS": "0,0,0,0"}
    a, b = _bo3_pair(ctx, "E2E Dsa", "E2E Dsb", w, dict(w, T5_STUB_DESYNC_AT="1"))
    mid = queue_match(ctx, a, b, "ranked")
    ea, eb, seen = _stub_set(ctx, a, b, mid, "one desync")
    ctx.check("game 1 voided as a desync, replayed as game 1 over a new connection, then 2-0",
              len(seen) == 3 and seen[0][1] == "void" and seen[1][2] == 1 and not seen[1][3] and seen[2][2] == 2, seen)
    ctx.check("the set is decided and rated", ea.get("rated") and ea.get("status") == "confirmed" and
              (ea.get("rating") or {}).get("delta"), ea)
    # every game desyncs: after the third, the set is void
    for p in (a, b):
        leave(ctx, p)
    ctx.wait(lambda: a.action_on("ranked") and b.action_on("ranked"), 30, "free for the next set")
    b.app.settings["extra_env"] += "\nT5_STUB_DESYNC=1"
    if b.game_running():
        b.game().stop()                    # the next game of B starts with the new setting
    ctx.wait(lambda: not b.game_running(), 10)
    ctx.server.env["T5L_PAIR_COOLDOWN"] = 0
    mid = queue_match(ctx, a, b, "ranked")
    ea, eb, seen = _stub_set(ctx, a, b, mid, "three desyncs", games_max=5)
    ctx.check("three desyncs in one set: the set is void, no rating change",
              ea.get("status") == "void" and not (ea.get("rating") or {}).get("delta"),
              f"{ea.get('status')} {ea.get('outcome_reason')} games {seen}")


@scenario("bo3_rating_once", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="the rating changes only once per set: the profile's rating stays after games 1 and 2 and moves at the end")
def bo3_rating_once(ctx):
    w = {"T5_STUB_WINNERS": "0,1,0", "T5_STUB_SECONDS": "6"}
    a, b = _bo3_pair(ctx, "E2E Ro1", "E2E Ro2", w, w)
    r0 = (profile(ctx, a) or {}).get("rating")
    mid = queue_match(ctx, a, b, "ranked")
    t0 = time.time()
    seen = []
    for _ in range(3):
        wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
        if a.events_of("set_end", t0):
            break
        seen.append((profile(ctx, a) or {}).get("rating"))
        since = a.matches[mid]["result"] - 0.5
        if not ctx.wait(lambda: latest(a, "match_start", since), 30):
            break
        mid = latest(a, "match_start", since)["match"]
    ctx.wait(lambda: a.events_of("set_end", t0), 30, "the set ends")
    r1 = (profile(ctx, a) or {}).get("rating")
    ctx.check("the profile rating did not move during the set", all(r == r0 for r in seen), f"{r0} -> {seen}")
    ctx.check("... and moved once at its end", r1 != r0, f"{r0} -> {r1}")


@scenario("bo3_ranked_room", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="a ranked room plays a best-of-3 set (2-0 for P2)")
def bo3_ranked_room(ctx):
    w = {"T5_STUB_WINNERS": "1,1"}
    a, b = _bo3_pair(ctx, "E2E Rr1", "E2E Rr2", w, w)
    box = a.call(a.client.create_room, "E2E ranked set room", True)
    ctx.wait(lambda: box, 10, "ranked room created")
    rid = (box.get("ok") or {}).get("id")
    ctx.wait(lambda: b.tab.tv_rooms.exists(rid), 10, "room listed")
    t = time.time()
    b.tab.tv_rooms.selection_set(rid)
    b.press("join")
    mid = found_both(ctx, a, b, t)
    accept(ctx, a, mid)
    accept(ctx, b, mid)
    ea, eb, seen = _stub_set(ctx, a, b, mid, "room set")
    p2 = a if a.matches[mid].get("slot") == 1 else b
    e2 = ea if p2 is a else eb
    ctx.check("2-0 for P2, rated", e2.get("result") == "win" and e2.get("wins") == [2, 0] and e2.get("rated"), e2)
    _rating_once(ctx, a, b, ea, eb, "room set")


@scenario("bo3_old_client", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc='an old (1.0.0-protocol, "sets": false) client: its ranked matches are rated per game, with a rematch vote')
def bo3_old_client(ctx):
    a, b = _bo3_pair(ctx, "E2E New", "E2E Legacy", None, None, sets=(None, False))
    mid = queue_match(ctx, a, b, "ranked")
    ctx.check("no rated set with an old client", not _set_of(a, mid).get("rated"), _set_of(a, mid))
    wait_results(ctx, mid, (a, b), STUB_MATCH_SECONDS)
    ctx.check("the game is rated on its own", all((p.matches[mid].get("rating") or {}).get("delta") for p in (a, b)),
              [p.matches[mid].get("rating") for p in (a, b)])
    ctx.wait(lambda: a.bar_button("Rematch") is not None and b.bar_button("Rematch") is not None, 15,
             "a rematch vote (no countdown)")
    mid2 = rematch(ctx, a, b)
    wait_results(ctx, mid2, (a, b), STUB_MATCH_SECONDS)
    ctx.check("the rematch is rated on its own too", all((p.matches[mid2].get("rating") or {}).get("delta") for p in (a, b)))


@scenario("bo3_pair_cap", "10 ranked sets (bo3)", suites=("quick", "lobby"), needs="bo3",
          desc="the anti win-trading cap counts sets: with cap 1, the rematch after a set is casual and both are told")
def bo3_pair_cap(ctx):
    w = {"T5_STUB_WINNERS": "0,0"}
    a, b = _bo3_pair(ctx, "E2E Cap1", "E2E Cap2", w, w, T5L_PAIR_CAP=1)
    mid = queue_match(ctx, a, b, "ranked")
    _stub_set(ctx, a, b, mid, "set 1")
    t = time.time()
    ctx.wait(lambda: a.bar_button("Rematch") is not None and b.bar_button("Rematch") is not None, 15, "Rematch after the set")
    mid2 = rematch(ctx, a, b)
    ctx.check("the next set is casual (pair cap)", not a.matches[mid2].get("ranked") and not _set_of(a, mid2).get("rated"),
              _set_of(a, mid2))
    ctx.check("both were told why", any(ev.get("code") == "pair_cap" for ev in a.events_of("notice", t)) and
              any(ev.get("code") == "pair_cap" for ev in b.events_of("notice", t)))


# ============================================================================== 12. spectating (docs/SPECTATE.md)
def _frame_times(p):
    """The last whole-run frame-time line of p's games (rb_net.cpp report), its recording cost lines and its live
    stream's end line."""
    from e2e_flows import _whole
    ft, cost, live = None, [], []
    rx = re.compile(r"frame times, whole run p50 ([\d.]+) p95 ([\d.]+) p99 ([\d.]+) ms; while fighting \((\d+) frames\) "
                    r"p50 ([\d.]+) p95 ([\d.]+) p99 ([\d.]+) ms")
    for ln in _whole(p):
        m = rx.search(ln)
        if m:
            ft = {"p50": float(m.group(1)), "p95": float(m.group(2)), "p99": float(m.group(3)),
                  "fight_frames": int(m.group(4)), "fight_p50": float(m.group(5)), "fight_p95": float(m.group(6)),
                  "fight_p99": float(m.group(7))}
        m = re.search(r"recording cost the frame ([\d.]+) us on average, ([\d.]+) us at most", ln)
        if m:
            cost.append((float(m.group(1)), float(m.group(2))))
        if "live stream" in ln and "ended" in ln:
            live.append(ln.split("] ", 1)[-1].strip())
    return ft, cost, live


def _verdict(p):
    from e2e_harness import read_json
    return read_json(os.path.join(p.out, "logs", "online", "watch-verdict.json"))


def _friend_watch(p, name):
    return any(f["name"] == name and f.get("watch") for f in (p.client.friend_list or {}).get("friends") or ())


def _spectate_case(ctx, watched):
    """A room match and a rematch in the running games (rollback), Ava (P1, the room's host) vs Bo. watched: Vi
    (Ava's friend) watches from the start through the Friends page, Wu (a guest) joins 60 s later through the
    Rooms list -- 4 games. Not watched: the same two players, the same mashing, no spectators and no live
    stream at all (launchers without the cap) -- the frame times to compare. (At most 4 games at once.)"""
    if "spectate" not in features():
        raise Skip("this tree has no spectating")
    game_server(ctx)
    a = ctx.player("E2E Ava", char="steve", password="ava-pw-1")
    b = ctx.player("E2E Bo", char="hwoarang")
    v = w = None
    if watched:
        v = ctx.player("E2E Vi", password="vi-pw-1")
        w = ctx.player("E2E Wu")
    else:
        for p in (a, b):
            p.tab.spec.client_kw = lambda: {"spectate": False}      # like an older launcher: no live stream at all
    login(ctx, a, "register")
    login(ctx, b)
    if watched:
        login(ctx, v, "register")
        login(ctx, w)
    a.set_char("steve")
    b.set_char("hwoarang")
    if watched:
        a.call(a.client.add_friend, "E2E Vi")
        ctx.wait(lambda: any(r["name"] == "E2E Ava" for r in (v.client.friend_list or {}).get("incoming") or ()), 15,
                 "Vi gets Ava's friend request")
        v.call(v.client.answer_friend, "E2E Ava", True)
        ctx.wait(lambda: any(f["name"] == "E2E Ava" for f in (v.client.friend_list or {}).get("friends") or ()), 15,
                 "Vi and Ava are friends")
    a.press("room")
    ctx.wait(lambda: (a.me or {}).get("status") == "room", 10, "Ava creates a room")
    ctx.wait(lambda: len(b.tab.tv_rooms.get_children()) == 1, 10, "the room is listed")
    rid = b.tab.tv_rooms.get_children()[0]
    t = time.time()
    b.tab.tv_rooms.selection_set(rid)
    b.press("join")
    mid = found_both(ctx, a, b, t)
    accept(ctx, a, mid)
    accept(ctx, b, mid)
    started_both(ctx, a, b, mid)
    sa = latest(a, "match_start", t) or {}
    if not watched:
        ctx.check("no stream id (no live stream)", "stream" not in sa, sa.get("stream"))
    else:
        ctx.check("the match has a stream id", sa.get("stream") == mid, sa.get("stream"))
        # Vi watches from the start: Friends -> Ava -> Watch
        ctx.wait(lambda: _friend_watch(v, "E2E Ava"), 30, "Vi's friends list: Ava can be watched")
        v.tab._fill_friends()
        v.tab.tv_friends.selection_set("f:E2E Ava")
        v.tab._set_friend_actions()
        ctx.require("Vi's Watch button is on", str(v.tab.friend_actions["watch"].cget("state")) == "normal")
        v.tab.friend_actions["watch"].invoke()
        t_v = time.time()
        ctx.wait(lambda: v.tab.spec.w is not None, 15, "Vi watches (the Spectating card)")
        ctx.wait(lambda: (v.tab.spec.w or {}).get("game") is not None, 30, "Vi's game starts at once (it waits for the data)")
        ctx.wait(lambda: a.events_of("spectators", t_v), 15, "Ava is told somebody watches")
    wait_fight(ctx, mid, (a, b), timeout=180)
    if watched:
        ctx.wait(lambda: (v.tab.spec.w or {}).get("state") == "playing", 120, "Vi's game plays the match")
        # Wu joins late: Rooms -> Ava's room -> Watch
        ctx.sleep(max(0.0, 60.0 - (time.time() - t_v)))
        ctx.wait(lambda: any(r.get("watch") for r in w.client.rooms), 10, "the room's match can be watched")
        w.tab.tv_rooms.selection_set(rid)
        w.tab.spec.set_actions()
        ctx.require("Wu's Watch button is on", str(w.tab.actions["watch_room"].cget("state")) == "normal")
        w.tab.actions["watch_room"].invoke()
        ctx.note(f"Wu joins {time.time() - t_v:.0f} s after Vi")
        ctx.wait(lambda: (w.tab.spec.w or {}).get("game") is not None, 30, "Wu's game starts (from the session's start)")
    wait_results(ctx, mid, (a, b))
    mid2 = rematch(ctx, a, b)                  # (at once: the rematch window runs)
    ctx.check("the rematch continues the session", a.matches[mid2].get("cont"))
    rows = [match_row(ctx, mid, (a, b), "confirmed", "match 1")]
    wait_fight(ctx, mid2, (a, b), timeout=120)
    wait_results(ctx, mid2, (a, b))
    rows.append(match_row(ctx, mid2, (a, b), "confirmed", "rematch"))
    leave(ctx, a)                               # the set ends: the players' session (and its stream) ends
    if watched:
        ctx.wait(lambda: all((p.tab.spec.w or {}).get("state") == "over" for p in (v, w)), 900,
                 "both spectators' games end at the end of the stream")
        for p, label in ((v, "Vi (from the start)"), (w, "Wu (60 s late)")):
            vd = _verdict(p) or {}
            ms = vd.get("matches") or []
            ctx.check(f"{label}: identical to the live game", vd.get("identical") is True,
                      f"{vd.get('hashes_compared')} hashes compared, {vd.get('hash_mismatches')} different, "
                      f"{vd.get('uncompared')} uncompared, sync points {vd.get('sync_points')}/"
                      f"{vd.get('sync_points_recorded')}, setup problems {vd.get('setup_problems')}")
            ctx.check(f"{label}: both matches played, the same results", len(ms) == 2 and all(m.get("same") for m in ms),
                      [(m.get("winner"), m.get("hash"), m.get("same")) for m in ms])
            ctx.note(f"{label}: delay avg {vd.get('delay_avg')} s, max {vd.get('delay_max')} s; {vd.get('stalls')} waits "
                     f"({vd.get('stall_seconds')} s); {vd.get('received_bytes')} bytes for {vd.get('received_frames')} "
                     f"frames; end {vd.get('end')!r} / {vd.get('stream_end')!r}")
        fv, fw = _verdict(v) or {}, _verdict(w) or {}
        ctx.check("both spectators saw the same final hashes", bool(fv.get("matches")) and
                  [m.get("hash") for m in fv.get("matches") or []] == [m.get("hash") for m in fw.get("matches") or []],
                  [m.get("hash") for m in fv.get("matches") or []])
        ctx.check("Vi watched a few seconds behind", isinstance(fv.get("delay_avg"), (int, float)) and
                  0 < fv["delay_avg"] < 12, fv.get("delay_avg"))
    for p in (a, b):
        ft, cost, live = _frame_times(p)
        ctx.note(f"{p.name}: frame times {ft}; recording cost (avg us, max us) {cost[-3:]}; live {live[-1:]}")
    for r in rows:
        ctx.note(f"{r['label']}: " + ", ".join(f"{n}: fps {r[n]['result_file'].get('fps')}, desync "
                                                f"{r[n]['result_file'].get('desync')}" for n in r
                                                if isinstance(r[n], dict) and "result_file" in r[n]))


@scenario("spectate_live", "12 spectating", game=True, suites=("game",),
          desc="a room match and a rematch in the running games (rollback); a friend watches from the start "
               "(Friends: Watch), a guest joins 60 s late (Rooms: Watch); both spectators' games play the "
               "session with every recorded hash and result the same, a few seconds behind")
def spectate_live(ctx):
    _spectate_case(ctx, True)


@scenario("spectate_baseline", "12 spectating", game=True, suites=("game",),
          desc="the same two players and the same match without spectators or live stream: the frame times to "
               "compare with spectate_live")
def spectate_baseline(ctx):
    _spectate_case(ctx, False)
