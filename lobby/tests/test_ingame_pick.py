"""The in-game character select (docs/RANKED.md "Character select in the game"): the server offers
it in match_start (fight.pick) when both players' clients can, the launcher puts pick=N on the
game's fight line, the fighters the game fought with come back with the result (chars) -- into the
history, and as the lock of a ranked set (its later games skip the select screen)."""
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

import util
from util import ServerThread, client, expect
from t5lobby import proto
from t5lobby.match_driver import MatchDriver, game_supports_pick
from t5lobby.proto import LobbyError
from t5lobby.server import Config

STUB = os.path.join(os.path.dirname(util.HERE), "tools", "stub_game.py")


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def acc(self, name, pick=True, **kw):
        c = client(self.s, name, password="pw-" + name, register=True, auto_ready=True, ingame_pick=pick, **kw)
        self.clients.append(c)
        return c

    def ranked(self, a, b, ca="jin", cb="paul"):
        a.ranked_match(ca)
        b.ranked_match(cb)
        return expect(a, "match_start"), expect(b, "match_start")

    @staticmethod
    def mine(ev, fight=None):
        f = fight or ev["fight"]
        return (f["p1"], f["p2"]) if ev["slot"] == 0 else (f["p2"], f["p1"])        # (mine, theirs)

    def report(self, a, b, ea, chars_a, chars_b, winner=0):
        """Both report P1's win as the game would, with the fighters the game fought (P1, P2)."""
        a.report_result(winner, [1, 0], ea["match"], source="game", chars=chars_a)
        b.report_result(winner, [1, 0], ea["match"], source="game", chars=chars_b)
        return expect(a, "match_result"), expect(b, "match_result")


class OfferTest(Base):
    def test_default_is_30_seconds(self):
        self.assertEqual(Config().ingame_pick, 30)
        self.assertEqual(Config.from_env({"T5L_INGAME_PICK": "0"}).ingame_pick, 0)

    def test_offered_when_both_can(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.assertIn("ingame_pick", a.welcome["features"])
        self.assertIn("ingame_pick", a.welcome["caps"])
        ea, eb = self.ranked(a, b)
        self.assertEqual((ea["fight"]["pick"], eb["fight"]["pick"]), (30, 30))
        self.assertEqual(self.mine(ea), ("jin", "paul"))                   # the launchers' picks: the fallback

    def test_not_when_one_cannot(self):
        a, b = self.acc("Alice"), self.acc("Bob", pick=False)
        ea, eb = self.ranked(a, b)
        self.assertNotIn("pick", ea["fight"])
        self.assertNotIn("pick", eb["fight"])


class OffTest(Base):
    server_cfg = {"ingame_pick": 0}

    def test_the_server_can_switch_it_off(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.ranked(a, b)
        self.assertNotIn("pick", ea["fight"])


class PickedTest(Base):
    def test_ranked_set_locks_what_was_picked_in_the_game(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        # the game's picks: Alice Kazuya, Bob Lili (in P1/P2 order of this match)
        picked = ["kazuya", "lili"] if ea["slot"] == 0 else ["lili", "kazuya"]
        ra, rb = self.report(a, b, ea, picked, picked)
        self.assertEqual(ra["status"], "confirmed")
        self.assertEqual(self.mine(ea, ra["fight"]), ("kazuya", "lili"))   # the history has the real fighters
        self.assertTrue(ra["set"]["locked"])
        a.rematch(ra["match"], True, keep=True)
        b.rematch(rb["match"], True, keep=True)
        s = expect(a, "match_start")
        self.assertNotIn("pick", s["fight"])                                # the second game skips the select screen
        self.assertEqual(self.mine(s), ("kazuya", "lili"))
        self.assertEqual((s["set"]["game"], s["set"]["locked"]), (2, True))
        hist = a.profile("Alice", 5)["history"]
        self.assertEqual((hist[0]["you_char"], hist[0]["opp_char"]), ("kazuya", "lili"))

    def test_ids_are_taken_too_and_disagreement_keeps_the_launchers(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        ra, rb = self.report(a, b, ea, [15, 33], [9, 33])                  # the two games saw different fighters
        self.assertEqual(self.mine(ea, ra["fight"]), ("jin", "paul"))
        a.rematch(ra["match"], True, keep=True)
        b.rematch(rb["match"], True, keep=True)
        s = expect(a, "match_start")
        self.assertEqual(self.mine(s), ("jin", "paul"))                    # the lock: what the launchers had

    def test_one_report_is_enough(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        a.report_result(0, [1, 0], ea["match"], source="game", chars=[15, 12])   # Kazuya vs Panda (Kuma's cell)
        b.report_result(0, [1, 0], ea["match"], source="game")
        ra = expect(a, "match_result")
        self.assertEqual((ra["fight"]["p1"], ra["fight"]["p2"]), ("kazuya", "panda"))

    def test_casual_rematches_pick_again(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.quick_match("jin")
        b.quick_match("paul")
        ea, eb = expect(a, "match_start"), expect(b, "match_start")
        self.assertEqual(ea["fight"]["pick"], 30)
        ra, rb = self.report(a, b, ea, ["kazuya", "lili"], ["kazuya", "lili"])
        self.assertFalse(ra["set"]["locked"])
        a.rematch(ra["match"], True, keep=True)
        b.rematch(rb["match"], True, keep=True)
        self.assertEqual(expect(a, "match_start")["fight"]["pick"], 30)

    def test_jinpachi_in_a_casual_match_only(self):
        """1.1.4: casual matches offer Jinpachi on the select grid (T5_NET_UNLOCKS=open), so his result counts
        (cap boss_chars) and the history shows him; ranked refuses him (test_bad_chars_are_refused)."""
        a, b = self.acc("Alice"), self.acc("Bob")
        self.assertIn("boss_chars", a.welcome.get("caps") or ())
        a.quick_match("jin")
        b.quick_match("paul")
        ea, eb = expect(a, "match_start"), expect(b, "match_start")
        self.assertFalse(ea["ranked"])
        ra, rb = self.report(a, b, ea, [35, "jin"], [35, "jin"])
        self.assertEqual((ra["fight"]["p1"], ra["fight"]["p2"]), ("jinpachi", "jin"))
        hist = a.profile("Alice", 5)["history"]
        self.assertIn("jinpachi", (hist[0]["you_char"], hist[0]["opp_char"]))

    def test_bad_chars_are_refused(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        for bad in (["jin"], ["jinpachi", "jin"], [35, 1], ["nobody", "jin"], [True, 1], "jin,law"):
            with self.assertRaises(LobbyError) as e:
                a.report_result(0, [1, 0], ea["match"], source="game", chars=bad)
            self.assertEqual(e.exception.code, proto.E_BAD_REQUEST)


class RatedSetPickTest(Base):
    """A ranked set of best of 3 (both clients know "sets"): only game 1 is picked in the game; games 2 and 3
    start by themselves with game 1's fighters and costumes, also over a new connection."""
    server_cfg = {"set_next_seconds": 0.3}

    def acc(self, name, pick=True, **kw):
        return super().acc(name, pick, sets=True, **kw)

    def play(self, a, b, ev, winner, chars=None, costumes=None, desync=None):
        for c in (a, b):
            try:
                c.report_result(winner, [3, 1] if winner == 0 else [1, 3], ev["match"], source="game", chars=chars,
                                costumes=costumes, desync=desync)
            except LobbyError:
                if not desync:
                    raise
        return expect(a, "match_result"), expect(b, "match_result")

    def next_game(self, a, b, keep=True):
        for c in (a, b):
            c.set_next(None, keep=keep)
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)

    def test_game_1_picked_games_2_and_3_locked_with_costumes(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        self.assertEqual((ea["set"]["rated"], ea["set"]["number"], ea["fight"]["pick"]), (True, 1, 30))
        picked = ["kazuya", "lili"] if ea["slot"] == 0 else ["lili", "kazuya"]       # P1/P2 of this set
        costumes = [2, 4] if ea["slot"] == 0 else [4, 2]                           # Alice RP, Bob RK
        ra, _ = self.play(a, b, ea, 0, picked, costumes)
        self.assertEqual(ra["set"]["number"], 2)
        e2, _ = self.next_game(a, b)
        self.assertNotIn("pick", e2["fight"])                                      # game 2: no select screen
        self.assertEqual(self.mine(e2), ("kazuya", "lili"))
        self.assertEqual(e2["fight"]["buttons"], costumes)                          # and the same costumes
        self.play(a, b, e2, 1)                                                     # 1-1 (no chars: no pick)
        e3, _ = self.next_game(a, b, keep=False)                                    # game 3 over a new connection
        self.assertEqual((e3["set"]["number"], e3["continue"]), (3, False))
        self.assertNotIn("pick", e3["fight"])
        self.assertEqual(self.mine(e3), ("kazuya", "lili"))
        self.assertEqual(e3["fight"]["buttons"], costumes)
        self.play(a, b, e3, 0)
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["games"]), ("confirmed", 3))
        hist = a.profile("Alice", 5)["history"]
        self.assertEqual({(h["you_char"], h["opp_char"]) for h in hist}, {("kazuya", "lili")})

    def test_a_replayed_game_1_is_picked_again(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.ranked(a, b)
        ra, _ = self.play(a, b, ea, 0, ["kazuya", "lili"], [1, 3], desync=9)       # game 1 desynced: void
        self.assertEqual((ra["status"], ra["set"]["number"]), ("void", 1))
        e1, _ = self.next_game(a, b)
        self.assertEqual((e1["set"]["number"], e1["fight"]["pick"]), (1, 30))      # nothing counted: pick again
        self.assertNotIn("buttons", e1["fight"])
        self.play(a, b, e1, 0, ["steve", "asuka"], [0, 0])
        e2, _ = self.next_game(a, b)
        self.assertNotIn("pick", e2["fight"])
        self.assertEqual((e2["fight"]["p1"], e2["fight"]["p2"]), ("steve", "asuka"))
        self.assertNotIn("buttons", e2["fight"])                                    # default costumes: nothing to say

    def test_bad_costumes_are_refused(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.ranked(a, b)
        for bad in ([1], [5, 1], [-1, 0], [True, 1], "1,2"):
            with self.assertRaises(LobbyError) as e:
                a.report_result(0, [1, 0], ea["match"], source="game", chars=["jin", "paul"], costumes=bad)
            self.assertEqual(e.exception.code, proto.E_BAD_REQUEST)


class DriverUnitTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="drvpick")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_fight_line_and_reported_chars(self):
        calls = []

        class Client:
            def report_result(self, *a, **kw):
                calls.append((a, kw))

            def game_started(self, mid):
                pass

        drv = MatchDriver(Client(), lambda env: None, self.d, mode="process")
        ev = {"fight": {"p1": "jin", "p2": "lili", "stage": "s20", "rounds": 3, "pick": 30}}
        self.assertEqual(drv.fight_line(ev), "9,33,20,3 pick=30")
        self.assertEqual(drv.fight_line({"fight": dict(ev["fight"], pick=0)}), "9,33,20,3")
        drv.match_ev = ev
        drv.ticket = types.SimpleNamespace(match_id="m1")
        drv.fight_chars = [15, 12]                                         # the status file at FIGHT START
        drv.fight_buttons = [2, 3]
        drv._report("m1", 0, [1, 0], "game", desync=0)
        self.assertEqual(calls[-1][1]["chars"], ["kazuya", "panda"])
        self.assertEqual(calls[-1][1]["costumes"], [2, 3])
        # a locked set's later game: the costumes on the fight line
        self.assertEqual(drv.fight_line({"fight": dict(ev["fight"], pick=0, buttons=[2, 3])}), "9,33,20,3 buttons=2|3")
        self.assertEqual(drv.fight_line({"fight": dict(ev["fight"], pick=0, buttons=[0, 0])}), "9,33,20,3")
        drv.match_ev = {"fight": dict(ev["fight"], pick=0)}                # no in-game select: nothing to say
        drv._report("m1", 0, [1, 0], "game", desync=0)
        self.assertNotIn("chars", calls[-1][1])

    def test_build_marker(self):
        exe = os.path.join(self.d, "t5dr.exe")
        with open(exe, "wb") as f:
            f.write(b"\0" * 100 + b"T5_DF_PICK" + b"\0" * 100)
        self.assertTrue(game_supports_pick([exe, os.path.join(self.d, "missing.dll")]))
        with open(exe, "wb") as f:
            f.write(b"T5_CTL_DIR")
        self.assertFalse(game_supports_pick([exe]))


class StubSetTest(Base):
    """A ranked set through the launcher's glue and the stub game in persistent mode: the first game
    picked in the game, the rematch locked to those fighters with no select screen."""

    def launch_stub(self, d, extra):
        import subprocess

        class G:
            def __init__(self, env):
                self.log_path = os.path.join(d, f"game-{time.monotonic_ns()}.log")
                full = dict(os.environ, **extra)
                full.update(env)
                with open(self.log_path, "w") as lf:
                    self.proc = subprocess.Popen([sys.executable, STUB], env=full, stdout=lf, stderr=lf)

            def running(self):
                return self.proc.poll() is None

            def stop(self):
                if self.running():
                    self.proc.kill()
                    self.proc.wait(5)
        return G

    def test_ranked_set_through_the_driver(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        stub = {"T5_STUB_SECONDS": "1", "T5_STUB_PICKS": "15,33"}         # the "game" picked Kazuya vs Lili
        drivers, dirs = [], []
        for c in (a, b):
            d = tempfile.mkdtemp(prefix="drvset")
            dirs.append(d)
            drivers.append(MatchDriver(c, self.launch_stub(d, stub), d, mode="persistent", ask_manual=False,
                                       auto_rematch=1))
        starts, results = {0: [], 1: []}, {0: [], 1: []}
        a.ranked_match("jin")
        b.ranked_match("paul")
        t_end = time.monotonic() + 40
        try:
            while time.monotonic() < t_end and min(len(results[0]), len(results[1])) < 2:
                for i, (c, drv) in enumerate(zip((a, b), drivers)):
                    while True:
                        ev = c.next_event(0)
                        if ev is None:
                            break
                        drv.on_event(ev)
                        if ev["t"] == "match_start":
                            starts[i].append(ev)
                        if ev["t"] == "match_result":
                            results[i].append(ev)
                    drv.poll()
                time.sleep(0.05)
        finally:
            for drv in drivers:
                drv.close()
            for d in dirs:
                shutil.rmtree(d, ignore_errors=True)
        self.assertEqual([r["status"] for r in results[0]], ["confirmed", "confirmed"])
        self.assertEqual(starts[0][0]["fight"]["pick"], 30)
        self.assertEqual((results[0][0]["fight"]["p1"], results[0][0]["fight"]["p2"]), ("kazuya", "lili"))
        self.assertNotIn("pick", starts[0][1]["fight"])                    # game 2: locked, no select screen

        def alices(game, ev):    # Alice's fighter in that game, whichever side (a ranked rematch draws the sides again)
            return ev["fight"]["p1" if starts[0][game]["slot"] == 0 else "p2"]
        self.assertEqual(alices(1, starts[0][1]), alices(0, results[0][0]))
        self.assertEqual(drivers[0].history[0][1].get("chars"), ["kazuya", "lili"])


try:
    from test_tk_tab import TkBase
except Exception:        # pragma: no cover  (no tkinter)
    TkBase = None


@unittest.skipIf(TkBase is None, "no tkinter")
class TabPickTest(TkBase if TkBase is not None else unittest.TestCase):
    """The Online tab with a game build that can pick in the game: the cap, pick=N on the fight
    line, the match line, and the fighters once the fight starts."""

    def test_the_tab_offers_and_shows_the_in_game_pick(self):
        tab = self.tab
        cm = os.path.join(self.dir, "build", "cmake")
        os.makedirs(cm, exist_ok=True)
        with open(os.path.join(cm, "t5dr.exe"), "wb") as f:      # a game build with the in-game select
            f.write(b"MZ" + b"\0" * 64 + b"T5_DF_PICK" + b"\0" * 64)
        tab.server_var.set(self.s.addr)
        tab.name_var.set("TabUser")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.assertTrue(tab.client.ingame_pick)
        self.assertIn("pick your fighter in the game", tab.hint_var.get())
        self.other = client(self.s, "Rival", auto_ready=True, ingame_pick=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.actions["quick"].invoke()
        self.other.quick_match("paul")
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        self.assertIn(" pick=30", self.app.games[0].env["T5_FIGHT"])
        self.assertIn("pick your fighter in the game (30 s)", tab.match_var.get())
        # the game says the fight started with what was picked (Kazuya vs Lili)
        drv = tab.driver
        import json
        with open(drv.status_path, "w") as f:
            json.dump({"state": "fight", "match": 1, "p1": 15, "p2": 33}, f)
        self.pump(lambda: "Kazuya vs Lili" in tab.match_var.get())


if __name__ == "__main__":
    unittest.main()
