"""The end-to-end runner's game-independent parts (tools/e2e): the network shaper between two games,
the log parser, the scenario list and the report. The scenarios themselves need the game and run on
the owner's PC (python tools/e2e/run.py)."""
import json
import os
import socket
import sys
import tempfile
import time
import unittest

from helpers import ROOT

sys.path.append(os.path.join(ROOT, "tools", "e2e"))      # (appended: tools/e2e/run.py must not shadow tools/smoke/run.py)
import e2e_flows as flows      # noqa: E402
import e2e_harness as harness    # noqa: E402
import e2e_scenarios as scenarios  # noqa: E402


def udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    s.settimeout(2.0)
    return s


class ShaperTest(unittest.TestCase):
    def setUp(self):
        self.a, self.b = udp(), udp()
        self.pa, self.pb = self.a.getsockname()[1], self.b.getsockname()[1]
        self.sh = harness.Shaper()
        self.addCleanup(self.sh.close)
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)

    def route(self):
        """Both games' environment as the lobby hands it out, rewritten by the shaper."""
        p = type("P", (), {"name": "A"})()
        q = type("P", (), {"name": "B"})()
        ea = self.sh.rewrite(p, {"T5_NET_PORT": str(self.pa), "T5_NET_PEER": f"127.0.0.1:{self.pb}", "T5_NET_PATH": "lan"})
        eb = self.sh.rewrite(q, {"T5_NET_PORT": str(self.pb), "T5_NET_PEER": f"127.0.0.1:{self.pa}", "T5_NET_PATH": "lan"})
        to_b = ("127.0.0.1", int(ea["T5_NET_PEER"].rsplit(":", 1)[1]))
        to_a = ("127.0.0.1", int(eb["T5_NET_PEER"].rsplit(":", 1)[1]))
        return ea, eb, to_a, to_b

    def test_off_leaves_the_environment_alone(self):
        env = {"T5_NET_PORT": "1", "T5_NET_PEER": "127.0.0.1:2", "T5_NET_PATH": "lan", "T5_NET_DELAY": "2"}
        self.assertEqual(self.sh.rewrite(type("P", (), {"name": "A"})(), dict(env)), env)

    def test_packets_go_through_the_proxy_both_ways_from_the_address_each_game_was_given(self):
        self.sh.set(rtt=40)
        ea, eb, to_a, to_b = self.route()
        self.assertNotEqual(ea["T5_NET_PEER"], f"127.0.0.1:{self.pb}")
        self.assertEqual(ea["T5_NET_RTT_MS"], "40.0")
        self.assertEqual(ea["T5_NET_DELAY"], "3")                  # suggest_delay(40): what the lobby would say
        t = time.perf_counter()
        self.a.sendto(b"hello b", to_b)
        data, src = self.b.recvfrom(100)
        dt = time.perf_counter() - t
        self.assertEqual(data, b"hello b")
        self.assertEqual(src, to_a)                                 # B sees it come from the address B sends to
        self.assertGreaterEqual(dt, 0.018)                          # one way = rtt / 2
        self.b.sendto(b"hello a", src)
        data, src = self.a.recvfrom(100)
        self.assertEqual((data, src), (b"hello a", to_b))

    def test_loss_and_cut(self):
        self.sh.set(rtt=0, loss=100)
        _ea, _eb, _to_a, to_b = self.route()
        self.a.sendto(b"x", to_b)
        self.b.settimeout(0.3)
        with self.assertRaises(socket.timeout):
            self.b.recvfrom(10)
        self.sh.loss = 0
        self.sh.cut = True
        self.a.sendto(b"y", to_b)
        with self.assertRaises(socket.timeout):
            self.b.recvfrom(10)
        st = self.sh.stats()
        self.assertEqual((st["dropped"], st["cut"]), (1, 1))
        self.sh.cut = False
        self.a.sendto(b"z", to_b)
        self.assertEqual(self.b.recvfrom(10)[0], b"z")

    def test_relay_path_and_build_override(self):
        self.sh.set(rtt=80)
        self.sh.build_override["A"] = "other"
        env = self.sh.rewrite(type("P", (), {"name": "A"})(), {"T5_NET_PORT": "1", "T5_NET_PEER": "127.0.0.1:9",
                                                               "T5_NET_PATH": "relay", "T5_NET_BUILD": "b"})
        self.assertEqual(env["T5_NET_PEER"], "127.0.0.1:9")         # the relay is the server: no proxy
        self.assertEqual(env["T5_NET_BUILD"], "other")


class LogTest(unittest.TestCase):
    LINES = [
        "[netplay] connected (host, P1), delay 2, peer 127.0.0.1:7821, packets authenticated",
        "[df] frame 1062: FIGHT START match 1 id t05: Lili vs Dragunov, stage 33 (field 0x21), rounds 1, game type 4",
        "[netplay] rollback input delay for this match: 1 frame(s) (auto: round trip 0 ms (13 samples) -> 1)",
        "[netplay] lockstep starts: frame 0, delay 2",
        "[netplay] rollback agreed: input delay 2 -> 1 (this match's)",
        "[rb] rbnet: rollback loop takes over at frame 1 (delay 1, max prediction 8 frames, peer inputs known for < 9)",
        "[rb] rbnet: 300 frames in 5.0 s (60.0 fps), 3 rollbacks (4 frames re-simulated, max depth 2, depth histogram "
        "1:2 2:1), 7.84 ms per rollback (max 10.94; restore 1.04 ms of it), 2 stalls (29.0 ms, 0.0 ms of them in "
        "lockstep windows), 90 frames ran on predicted input, 10 time-sync sleeps (286 ms), avg advantage 0.34 frames, x",
        "[netplay] sync check through frame 599: 0 mismatching frame(s) -- in sync",
        "[netplay] speed: 43.5 fps, this PC 48.7 fps without the waits for the peer (waited 1.5 s of 13.8 s)",
        "[cellGcmSys] queued flip never reached by the FIFO walker (get stuck at 0x000F882C)",
    ]

    def test_parse_segment(self):
        s = flows.parse_segment(self.LINES)
        self.assertEqual((s["pick"], s["agreed"], s["mode"]), (1, 1, "rollback"))
        self.assertEqual(s["connected"], ("host", "P1", 2))
        self.assertEqual((s["rollbacks"], s["stalls"], s["rb_windows"]), (3, 2, [60.0]))
        self.assertEqual(s["sync"], (599, 0))
        self.assertEqual(s["fifo"], {"fifo_stall": 1})
        self.assertEqual(len(s["fight_start"]), 1)
        self.assertEqual(s["speed"], [(43.5, 48.7)])

    def test_lockstep_only(self):
        s = flows.parse_segment(["[netplay] lockstep starts: frame 0, delay 3", "[netplay] DESYNC at frame 9: x"])
        self.assertEqual((s["mode"], s["desync_lines"]), ("lockstep", 1))


class ScenarioListTest(unittest.TestCase):
    def test_names_suites_and_groups(self):
        names = [s.name for s in scenarios.SCENARIOS]
        self.assertEqual(len(names), len(set(names)))
        for s in scenarios.SCENARIOS:
            self.assertIn("full", s.suites, s.name)
            self.assertTrue(s.desc and s.group, s.name)
            if "quick" in s.suites:
                self.assertFalse(s.game, f"{s.name}: the quick suite needs no game")
        groups = {s.group.split(" ")[0] for s in scenarios.SCENARIOS}
        # (12: spectating and the 1.1.2 scenarios, 13: the 1.1.3 integration, 14: private and community rooms,
        # 15: the 1.2.0 opt-in features)
        self.assertEqual(groups, {str(i) for i in range(1, 16)})

    def test_unmerged_features_skip(self):
        feats = scenarios.features()
        for s in scenarios.SCENARIOS:
            if s.needs == "ingame_pick" and "ingame_pick" not in feats:
                with self.assertRaises(harness.Skip):
                    scenarios._need_ingame_pick()
            if s.needs == "bo3" and not ({"ranked_sets", "bo3", "set_bo3", "best_of"} & feats):
                with self.assertRaises(harness.Skip):
                    scenarios._need_bo3()


class AlwaysLeftStepTest(unittest.TestCase):
    """net_always_left judges where A went in the first ~10 s of holding RIGHT, not its first step: in the 1.2.0 gate
    an unmirrored P2 (Eddy, Christie) was first traced at its intro place and then set to the round start a few
    hundred units nearer the opponent by the automatic intro skip -- the old first-step rule read that jump as
    'towards' (and before that, the script's back + Square lunged forward). Trace rows (n, P1 x, P1 z, P2 x, P2 z)
    as the game logged them (gate_int_al5, Kazuya vs Eddy, every second row)."""
    QUICK_P2 = [(7840, 0, 0, 1, 0), (7860, -819, 0, 819, 0), (7900, -819, 0, 819, 0), (8020, -819, 0, 375, 0),
                (8080, -819, 0, 375, 0), (8100, -819, 0, 1735, 0), (8220, -819, 0, 3184, 0), (8340, -819, 0, 2796, 0),
                (8400, -819, 0, 3637, 0), (8460, -819, 0, 2823, 0), (8520, -819, 0, 3655, 0)]
    CASUAL_P2_MIRRORED = [(500, 0, 0, 0, 0), (520, 1000, 0, -1000, 0), (680, 1000, 0, -992, 0),
                          (720, 1550, -6, -751, 98), (760, 1750, -10, 66, 129)]

    def test_where_a_went(self):
        self.assertEqual(scenarios.al_first_step(self.QUICK_P2, 1), -1)              # away (after the intro jump)
        self.assertEqual(scenarios.al_first_step(self.CASUAL_P2_MIRRORED, 1), 1)     # towards
        # the jump alone would have read 'towards' (the old first-step rule)
        self.assertEqual(scenarios.al_first_step(self.QUICK_P2[:5], 1), 1)
        # a P2 whose RIGHT walked it towards P1 unmirrored (left/right swapped by mistake) is told apart
        wrong = [(0, 0, -1000, 0, 1000), (20, 0, -1000, 0, 860)]
        self.assertEqual(scenarios.al_first_step(wrong, 1), 1)
        self.assertEqual(scenarios.al_first_step([(0, 0, 0, 0, 0)], 1), 0)
        self.assertEqual(scenarios.al_first_step([(0, 1000, 0, -1000, 0), (20, 1000, 0, -1040, 0)], 1), 0)  # < 100


class OptinScenarioReviewTest(unittest.TestCase):
    """Review optin-check-120: the private-chat privacy check reads SQLite's WAL too; the VRR scenarios give the
    proxy 2 % (it takes percent); the adaptive (rollback) scenario skips a --netcode lockstep run."""

    def test_privacy_check_sees_a_line_still_in_the_wal(self):
        import shutil
        import sqlite3
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        db = os.path.join(d, "t5lobby.db")
        c = sqlite3.connect(db)
        self.addCleanup(c.close)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA wal_autocheckpoint=0")
        c.execute("CREATE TABLE lines (text TEXT)")
        c.commit()
        c.execute("INSERT INTO lines VALUES ('pm two'), ('pm one')")
        c.commit()
        with open(db, "rb") as f:
            self.assertNotIn(b"pm one", f.read())          # the old check (main file only) saw nothing
        raw, rows = scenarios._db_privacy_texts(db)
        self.assertIn(b"pm one", raw)
        self.assertIn("pm one", rows)
        self.assertIn("pm two", rows)

    def test_vrr_loss_is_percent(self):
        self.assertEqual(scenarios.VRR_LOSS_PCT, 2.0)
        import inspect
        src = inspect.getsource(scenarios._net_vrr_120)
        self.assertIn("VRR_LOSS_PCT", src)
        self.assertNotIn("15, 0.02,", src)

    def test_adaptive_scenario_skips_lockstep_runs(self):
        ctx = type("Ctx", (), {"run": type("Run", (), {"netcode": "lockstep"})()})()
        with self.assertRaises(harness.Skip):
            scenarios.net_vrr_adaptive_120.__wrapped__(ctx) if hasattr(scenarios.net_vrr_adaptive_120, "__wrapped__") \
                else scenarios.net_vrr_adaptive_120(ctx)


class ReportTest(unittest.TestCase):
    def test_report_lists_every_scenario_with_its_counts(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("e2e_run", os.path.join(ROOT, "tools", "e2e", "run.py"))
        e2e_run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(e2e_run)
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        run = type("R", (), {"out": d, "exe": None, "rounds": 1})()
        a = type("A", (), {"suite": "quick", "only": "", "repeat": 2})()
        res = []
        for attempt, st in ((1, "PASS"), (2, "FAIL")):
            res.append({"name": "quick_decline", "attempt": attempt, "group": "2 quick match", "game": False,
                        "desc": "decline", "status": st, "error": None, "seconds": 3.0, "dir": "quick_decline",
                        "checks": [{"name": "c", "ok": st == "PASS", "detail": "d", "level": "fail"}],
                        "evidence": ["e"], "matches": [], "contention": {"games": 0, "builds": 0}})
        tot = e2e_run.write_report(run, res, a, time.time())
        self.assertEqual(tot, {"PASS": 1, "FAIL": 1, "SKIP": 0})
        with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("| quick_decline | 2 quick match | 2 | 1 | 1 | 0 |", md)
        self.assertIn("## Failures first", md)
        with open(os.path.join(d, "report.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["totals"]["FAIL"], 1)


if __name__ == "__main__":
    unittest.main()
