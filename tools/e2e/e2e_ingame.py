"""Scenarios: the rematch question in the game (1.2.0, docs/REMATCH_1.2.0.md). After a casual match both games show
"Rematch?" over their picture with a 10-second countdown and the opponent's choice; each player answers with the
controller in the game (Cross = rematch, Circle = no), never in the launcher. Here the answers are presses of the
player's pad file (PS3_PAD_FILE, port 1 -- the game reads it like a controller); the launcher's own Rematch buttons are
never clicked. Imported by e2e_scenarios (the registry).

Checks: the game logs "in-game question shown" and the driver says the game shows it (ingame_ui_ready); the vote comes
from the game (ingame_vote); the launcher window is not brought forward while the question is up, and is once it is
over without a rematch; a rematch both accepted continues in the running session; every match confirmed with the same
hash and 0 mismatching frames (match_row); run.py --replays plays every recorded session back.
"""
import os
import random
import re
import threading
import time

from e2e_flows import (accept, create_room, found_both, leave, login, match_row, queue_match, started_both,
                       wait_fight, wait_results)
from e2e_harness import Abort, _PickPad

QUESTION_SECONDS = 10.0


def _instrument(players):
    """Count the times a launcher brings its window forward (the harness keeps the windows withdrawn)."""
    for p in players:
        p.forward = []
        p.tab.bring_forward = (lambda *_a, _p=p, **_k: _p.forward.append(time.time()))


def _note_times(p, kind, mid=None, since=0.0):
    return [ts for ts, n in p.notes if n.get("kind") == kind and ts >= since and (mid is None or n.get("match") == mid)]


def _votes(p, mid):
    return [n.get("accept") for _ts, n in p.notes if n.get("kind") == "ingame_vote" and n.get("match") == mid]


def _shown_in_game_log(p, mid):
    g = p.game()
    if g is None or not getattr(g, "log_path", None):
        return False
    try:
        with open(g.log_path, "rb") as f:
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    return f"in-game question shown: rematch for match {mid}" in text


def _answered_in_game_log(p, mid):
    g = p.game()
    try:
        with open(g.log_path, "rb") as f:
            text = f.read().decode("utf-8", "replace")
    except (OSError, AttributeError, TypeError):
        return []
    return re.findall(r"in-game question answered: (\w+) \(match " + re.escape(mid) + r"\)", text)


def question(ctx, players, mid, timeout=40):
    """Both games show the question for `mid`: returns the time each driver saw it shown."""
    ok = ctx.wait(lambda: all(_note_times(p, "ingame_ui_ready", mid) for p in players), timeout,
                  f"{mid}: the rematch question is shown in both games")
    if not ok:
        for p in players:
            d = p.tab.driver
            ctx.note(f"{p.name}: notes {[n.get('kind') for _t, n in p.notes[-12:]]}, "
                     f"ui {getattr(getattr(d, 'ui', None), 'document', None)}")
        raise Abort("no in-game question")
    for p in players:
        ctx.check(f"{mid}: {p.name}'s game logged the question", _shown_in_game_log(p, mid))
        doc = p.tab.driver.ui.snapshot()
        ctx.check(f"{mid}: {p.name}: question with Cross/Circle, a {QUESTION_SECONDS:.0f} s countdown and the "
                  f"opponent's state", doc["allowed"] == ["accept", "decline"] and 8000 <= doc["countdown_ms"] <= 10000
                  and doc["total_ms"] == 10000 and doc["opp_state"] in ("deciding", "accept") and doc["opponent"],
                  {k: doc.get(k) for k in ("allowed", "countdown_ms", "total_ms", "opponent", "opp_state",
                                           "key_confirm", "key_cancel")})
    return [min(_note_times(p, "ingame_ui_ready", mid)) for p in players]


LOCK_SECONDS = 1.0      # (the game ignores the buttons for the question's first 0.7 s: ui_logic.h kInputLockMs)


def press(p, button, hold=0.12, gap=0.2, shown=None):
    """A press on the player's controller (the pad file the game reads as port 1); with `shown` (when the question
    came up) not before the question takes buttons -- a person reads it first."""
    if shown is not None:
        time.sleep(max(0.0, shown + LOCK_SECONDS - time.time()))
    _PickPad(p).press(button, hold, gap)


def no_forward_until(ctx, players, since, label):
    for p in players:
        ctx.check(f"{label}: {p.name}'s launcher stayed behind the game", not [t for t in p.forward if t >= since],
                  f"brought forward at {[round(t - since, 1) for t in p.forward if t >= since]} s")


def play(ctx, a, b, mid, label):
    if not wait_fight(ctx, mid, (a, b), timeout=150):
        raise Abort(f"{label}: no fight")
    wait_results(ctx, mid, (a, b))
    return match_row(ctx, mid, (a, b), "confirmed", label)


def rematch_both(ctx, a, b, mid, label, delay_b=1.0):
    """Both press Cross in the game (B `delay_b` seconds later): the rematch continues in the running session."""
    shown = question(ctx, (a, b), mid)
    since = time.time()
    press(a, "CROSS", shown=shown[0])
    ctx.wait(lambda: b.tab.driver.ui.snapshot().get("opp_state") == "accept", 5,
             f"{label}: {b.name}'s game shows that {a.name} wants a rematch")
    left = max(0.0, shown[1] + delay_b - time.time())
    ctx.sleep(left)
    press(b, "CROSS")
    mid2 = found_both(ctx, a, b, since, timeout=20)
    if not started_both(ctx, a, b, mid2, 30):
        raise Abort(f"{label}: the rematch did not start")
    for p in (a, b):
        ctx.check(f"{label}: {p.name} voted in the game (one yes)", _votes(p, mid) == [True], _votes(p, mid))
        ctx.check(f"{label}: {p.name}'s game logged its answer", _answered_in_game_log(p, mid) == ["accept"],
                  _answered_in_game_log(p, mid))
    ctx.check(f"{label}: continues in the running session", a.matches[mid2].get("cont") and b.matches[mid2].get("cont"),
              f"{a.matches[mid2].get('cont')} / {b.matches[mid2].get('cont')}")
    ctx.wait(lambda: all(p.tab.driver.ui.snapshot()["kind"] == "hidden" for p in (a, b)), 5,
             f"{label}: the question is gone in both games")
    no_forward_until(ctx, (a, b), shown[0] - 2, label)
    return mid2


def back_to_lobby(ctx, a, b, label, since):
    """No rematch: after its last words the question is gone and each launcher comes forward (the lobby, as today)."""
    ctx.wait(lambda: all(p.tab.driver.ui.snapshot()["kind"] == "hidden" for p in (a, b)), 10,
             f"{label}: the question is gone in both games")
    ctx.wait(lambda: all([t for t in p.forward if t >= since] for p in (a, b)), 10,
             f"{label}: both launchers come forward")
    ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 30, f"{label}: both free to search again")
    ctx.check(f"{label}: no new match", not a.events_of("match_found", since) and not b.events_of("match_found", since))


def _setup(ctx, na, nb, **server):
    from e2e_scenarios import game_server
    game_server(ctx, **server)
    a = ctx.player(na)
    b = ctx.player(nb)
    login(ctx, a)
    login(ctx, b)
    _instrument((a, b))
    for p in (a, b):
        ctx.check(f"{p.name}: the client offers the in-game question (the game build can show it)",
                  "ingame_rematch_v1" in (p.client.welcome or {}).get("caps", []),
                  (p.client.welcome or {}).get("caps"))
    return a, b


# ------------------------------------------------------------------------------------------------ scenarios
def ingame_rematch_flow(ctx):
    """accept/accept (rematch in the session), then accept/decline (back to the lobby)."""
    a, b = _setup(ctx, "E2E IgA", "E2E IgB")
    mid = queue_match(ctx, a, b, "quick")
    play(ctx, a, b, mid, "match 1")
    mid = rematch_both(ctx, a, b, mid, "in-game rematch 1 (both Cross)")
    play(ctx, a, b, mid, "rematch 1")
    shown = question(ctx, (a, b), mid)
    since = time.time()
    press(a, "CROSS", shown=shown[0])
    ctx.wait(lambda: b.tab.driver.ui.snapshot().get("opp_state") == "accept", 5, "B sees A's yes")
    press(b, "CIRCLE", shown=shown[1])
    ctx.wait(lambda: a.tab.driver.ui.snapshot().get("opp_state") == "decline", 5,
             "A's game shows that B does not want a rematch")
    ctx.check("B's game says no rematch", "lobby" in b.tab.driver.ui.snapshot().get("status", "").lower(),
              b.tab.driver.ui.snapshot().get("status"))
    ctx.check("votes: A yes, B no (from the games)", _votes(a, mid) == [True] and _votes(b, mid) == [False],
              f"{_votes(a, mid)} / {_votes(b, mid)}")
    back_to_lobby(ctx, a, b, "accept/decline", since)


def ingame_rematch_timing(ctx):
    """A yes at 9.x s still starts the rematch; then nobody answers: the countdown runs out."""
    a, b = _setup(ctx, "E2E IgC", "E2E IgD")
    mid = queue_match(ctx, a, b, "quick")
    play(ctx, a, b, mid, "match 1")
    t_press = 9.2
    mid = rematch_both(ctx, a, b, mid, f"B answers after {t_press} s", delay_b=t_press)
    play(ctx, a, b, mid, "rematch (late yes)")
    shown = question(ctx, (a, b), mid)
    ctx.sleep(QUESTION_SECONDS - 1)
    for p in (a, b):
        ctx.check(f"timeout: {p.name}'s countdown still runs after {QUESTION_SECONDS - 1:.0f} s",
                  p.tab.driver.ui.snapshot()["countdown_ms"] > 0, p.tab.driver.ui.snapshot()["countdown_ms"])
    ctx.wait(lambda: all("time" in p.tab.driver.ui.snapshot().get("status", "").lower()
                         or p.tab.driver.ui.snapshot()["kind"] == "hidden" for p in (a, b)), 6,
             "timeout: both games say the time is up")
    back_to_lobby(ctx, a, b, "timeout", shown[0])
    ctx.check("timeout: nobody voted", not _votes(a, mid) and not _votes(b, mid))
    ctx.check("timeout: the lobby let the rematch run out",
              any(e.get("state") == "expired" for e in a.events_of("rematch", shown[0]))
              or any(e.get("reason") == "expired" for e in a.events_of("set_end", shown[0])),
              [e.get("state") for e in a.events_of("rematch", shown[0])])


class _Masher:
    """Both players mash random buttons (attacks, directions, Cross/Circle, START) on their pad files."""

    def __init__(self, players, seed):
        self.players, self.rnd, self.stop = players, random.Random(seed), threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        choices = ["SQUARE", "TRIANGLE", "CROSS", "CIRCLE", "LEFT", "RIGHT", "UP", "DOWN", "SQUARE TRIANGLE",
                   "CROSS CIRCLE", "LEFT SQUARE", "START", "R1", ""]
        pads = [_PickPad(p) for p in self.players]
        while not self.stop.is_set():
            for pad in pads:
                pad.pad(self.rnd.choice(choices))
            time.sleep(self.rnd.uniform(0.03, 0.09))
        for pad in pads:
            pad.pad("")

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.stop.set()
        self.thread.join(2)


def ingame_rematch_mash(ctx):
    """Both mash buttons from the KO through the question: whatever they hit, both PCs agree (a rematch on both or
    on neither), each sends at most one yes and one no, and the match after it is in sync."""
    a, b = _setup(ctx, "E2E IgE", "E2E IgF")
    mid = queue_match(ctx, a, b, "quick")
    for k in range(3):
        if not wait_fight(ctx, mid, (a, b), timeout=150):
            raise Abort("no fight")
        ctx.wait(lambda: all((p.matches.get(mid) or {}).get("over") or p.tab.driver.game_state in ("over", "neutral")
                             for p in (a, b)), 150, fail=False)
        since = time.time()
        with _Masher((a, b), seed=ctx.run.seed * 31 + k):
            wait_results(ctx, mid, (a, b))
            match_row(ctx, mid, (a, b), "confirmed", f"mash {k + 1}")
            question(ctx, (a, b), mid)
            ctx.wait(lambda: a.events_of("match_found", since) or b.events_of("match_found", since)
                     or all(p.tab.driver.ui.snapshot()["kind"] == "hidden" for p in (a, b)), QUESTION_SECONDS + 8,
                     fail=False)
        for p in (a, b):
            v = _votes(p, mid)
            ctx.check(f"mash {k + 1}: {p.name}: at most one yes and one no", v.count(True) <= 1 and v.count(False) <= 1, v)
        # the wait above ends when EITHER launcher has the rematch's match_found; the other one's comes a moment
        # later over its own connection (gate 1.2.0: [True, False] read at once while both games went on into the
        # rematch) -- give it a few seconds before comparing
        if any(p.events_of("match_found", since) for p in (a, b)):
            ctx.wait(lambda: all(p.events_of("match_found", since) for p in (a, b)), 5, fail=False)
        found = [bool(p.events_of("match_found", since)) for p in (a, b)]
        ctx.check(f"mash {k + 1}: both PCs agree (rematch on both or on neither)", found[0] == found[1], found)
        if not all(found):
            ctx.note(f"mash {k + 1}: no rematch (votes {_votes(a, mid)} / {_votes(b, mid)})")
            ctx.wait(lambda: a.action_on("quick") and b.action_on("quick"), 30, "both free to search again")
            ctx.sleep(1.0)
            mid = queue_match(ctx, a, b, "quick")
            continue
        mid2 = found_both(ctx, a, b, since)
        started_both(ctx, a, b, mid2)
        ctx.note(f"mash {k + 1}: rematch {mid2} (votes {_votes(a, mid)} / {_votes(b, mid)})")
        mid = mid2
    if not wait_fight(ctx, mid, (a, b), timeout=150):
        raise Abort("no fight")
    wait_results(ctx, mid, (a, b))
    match_row(ctx, mid, (a, b), "confirmed", "after the mashing")


def ingame_rematch_room(ctx):
    """A classic room's match: the question in the game; both Cross = the rematch in the room."""
    from e2e_scenarios import game_server
    game_server(ctx)
    a = ctx.player("E2E IgG")
    b = ctx.player("E2E IgH")
    login(ctx, a)
    login(ctx, b)
    _instrument((a, b))
    create_room(a)
    ctx.wait(lambda: (a.me or {}).get("status") == "room", 10, "Create room")
    ctx.wait(lambda: len(b.tab.tv_rooms.get_children()) == 1, 10, "the room is listed for the other player")
    t = time.time()
    b.tab.tv_rooms.selection_set(b.tab.tv_rooms.get_children()[0])
    b.press("join")
    mid = found_both(ctx, a, b, t)
    accept(ctx, a, mid)
    accept(ctx, b, mid)
    started_both(ctx, a, b, mid)
    play(ctx, a, b, mid, "room match")
    mid = rematch_both(ctx, a, b, mid, "room: in-game rematch")
    ctx.check("room: the rematch is the room's match", (a.me or {}).get("status") in ("room", "playing"),
              (a.me or {}).get("status"))
    play(ctx, a, b, mid, "room rematch")
    shown = question(ctx, (a, b), mid)
    since = time.time()
    press(b, "CIRCLE", shown=shown[1])
    ctx.wait(lambda: all(p.tab.driver.ui.snapshot()["kind"] == "hidden" for p in (a, b)), 10, "room: question gone")
    ctx.wait(lambda: (a.me or {}).get("status") == "room" and (b.me or {}).get("status") == "room", 15,
             "room: after the no both are still in the room")
    ctx.wait(lambda: all([t for t in p.forward if t >= since] for p in (a, b)), 10, "room: both launchers come forward")


def ingame_rematch_relay(ctx):
    """A match on the relay (no direct path): the in-game rematch is a new connection that tries the direct path
    again, fails again and plays on the relay."""
    a, b = _setup(ctx, "E2E IgI", "E2E IgJ")
    for p in (a, b):
        p.client.block_direct = True
    try:
        mid = queue_match(ctx, a, b, "quick")
        ctx.check("relay match: relay from the start", a.matches[mid].get("path") == "relay", a.matches[mid].get("path"))
        play(ctx, a, b, mid, "relay match")
        mid = _relay_rematch_in_game(ctx, a, b, mid)
        play(ctx, a, b, mid, "relay rematch")
    finally:
        for p in (a, b):
            p.client.block_direct = False
            leave(ctx, p)


def _relay_rematch_in_game(ctx, a, b, mid):
    shown = question(ctx, (a, b), mid)
    since = time.time()
    press(a, "CROSS", shown=shown[0])
    ctx.sleep(0.8)
    press(b, "CROSS", shown=shown[1])
    mid2 = found_both(ctx, a, b, since, timeout=20)
    if not started_both(ctx, a, b, mid2, 60):
        raise Abort("relay: the rematch did not start")
    m = a.matches.get(mid2, {})
    ctx.check("relay: the rematch is a new connection (the direct path tried again)", not m.get("keep"),
              f"keep {m.get('keep')}, continue {m.get('cont')}")
    ctx.check("relay: the rematch plays on the relay again", m.get("path") == "relay", m.get("path"))
    for p in (a, b):
        ctx.check(f"relay: {p.name} voted in the game", _votes(p, mid) == [True], _votes(p, mid))
    no_forward_until(ctx, (a, b), since - 2, "relay")
    return mid2


def ingame_rematch_off(ctx):
    """T5_INGAME_REMATCH=0 on one launcher (as with an older launcher): no question in either game, the launcher's
    Rematch buttons work as before."""
    from e2e_scenarios import game_server
    import os
    game_server(ctx)
    a = ctx.player("E2E IgK")
    b = ctx.player("E2E IgL")
    login(ctx, a)
    old = os.environ.get("T5_INGAME_REMATCH")
    os.environ["T5_INGAME_REMATCH"] = "0"         # (read when the launcher logs in and makes its match driver)
    try:
        login(ctx, b)
    finally:
        if old is None:
            os.environ.pop("T5_INGAME_REMATCH", None)
        else:
            os.environ["T5_INGAME_REMATCH"] = old
    ctx.check("the switched-off launcher does not offer the in-game question",
              "ingame_rematch_v1" not in (b.client.welcome or {}).get("caps", []), (b.client.welcome or {}).get("caps"))
    mid = queue_match(ctx, a, b, "quick")
    play(ctx, a, b, mid, "match 1")
    from e2e_flows import rematch as launcher_rematch
    ctx.check("no question offered by the lobby", not a.matches[mid].get("rematch_ui")
              and not any(e.get("rematch_ui") for e in a.events_of("match_result")))
    mid = launcher_rematch(ctx, a, b)
    play(ctx, a, b, mid, "launcher rematch")
    ctx.check("no game showed a question", not _note_times(a, "ingame_ui_ready") and not _note_times(b, "ingame_ui_ready"))


def _shoot(ctx, p, path, timeout=3.0):
    """RSX_TEST_BB_SHOT: the next present writes the backbuffer (what the window shows, overlay included) as PPM."""
    req = os.path.join(p.dir, "shot.req")
    with open(req, "w") as f:
        f.write(path)
    t_end = time.time() + timeout
    while os.path.exists(req) and time.time() < t_end:
        ctx.pump(0.05)
    ok = os.path.isfile(path)
    if ok:
        try:
            from PIL import Image
            png = os.path.splitext(path)[0] + ".png"
            Image.open(path).save(png)
            os.remove(path)
            path = png
        except Exception:          # noqa: BLE001 -- the PPM stays
            pass
    return path if ok else None


def ingame_rematch_pictures(ctx):
    """Pictures of the question (build/ only, never committed): A at Internal resolution Lowest in a 1280x720
    window, B at 4K in a 1920x1080 window; every launcher language once, then the opponent's yes."""
    from e2e_scenarios import game_server
    from t5lobby import i18n
    game_server(ctx)
    pa = ctx.player("E2E PicA", env={"PS3_INTERNAL_RES": "0.5", "RSX_TEST_CLIENT_SIZE": "1280x720"})
    pb = ctx.player("E2E PicB", env={"PS3_INTERNAL_RES": "2160", "RSX_TEST_CLIENT_SIZE": "1920x1080"})
    for p in (pa, pb):
        st = p.app.settings
        st["extra_env"] = st["extra_env"] + "\nRSX_TEST_BB_SHOT=" + os.path.join(p.dir, "shot.req")
        st.save()
    login(ctx, pa)
    login(ctx, pb)
    _instrument((pa, pb))
    mid = queue_match(ctx, pa, pb, "quick")
    play(ctx, pa, pb, mid, "match")
    shown = question(ctx, (pa, pb), mid)
    ev = {p.name: [e for e in p.events_of("match_result") if e.get("match") == mid][-1] for p in (pa, pb)}
    prev = i18n.language()
    shots = []
    try:
        for lang in ("ja", "ko", "fr", "de", "es", "pt-BR", "en"):
            i18n.set_language(lang)
            for p in (pa, pb):
                p.tab._offer_ingame_ui(ev[p.name])
            ctx.pump(0.35)
            for p in (pa, pb):
                got = _shoot(ctx, p, os.path.join(p.dir, f"question_{lang}.ppm"))
                ctx.check(f"picture {lang} of {p.name}'s question", got is not None, got)
                shots.append(got)
    finally:
        i18n.set_language(prev)
    press(pa, "CROSS", shown=shown[0])
    ctx.wait(lambda: pb.tab.driver.ui.snapshot().get("opp_state") == "accept", 5, "B sees A's yes")
    ctx.pump(0.3)
    for p, name in ((pa, "after_my_yes"), (pb, "opponent_yes")):
        shots.append(_shoot(ctx, p, os.path.join(p.dir, f"question_{name}.ppm")))
    ctx.note(f"pictures: {[s for s in shots if s]}")
