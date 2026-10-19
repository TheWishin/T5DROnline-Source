"""MatchDriver without a server: the fight HUD identity it hands the game, the fight-file line,
and the persistent game's fallback to one process per opponent (fight-polish)."""
import json
import os
import shutil
import tempfile
import time
import unittest

import util  # noqa: F401  (sets sys.path)
from t5lobby import match_driver
from t5lobby.handover import MatchTicket
from t5lobby.match_driver import GameLog, MatchDriver, hud_values


class FakeClient:
    def __init__(self):
        self.calls = []

    def game_started(self, mid):
        self.calls.append(("game_started", mid))

    def leave_match(self, mid):
        self.calls.append(("leave_match", mid))


class FakeGame:
    """A game that never takes a control command (or a process-mode game)."""

    def __init__(self, env):
        self.env = env
        self.alive = True
        self.log_path = None
        self.proc = None

    def running(self):
        return self.alive

    def stop(self):
        self.alive = False


def ticket(mid="m1"):
    return MatchTicket(match_id=mid, role="host", slot=0, local_port=50000, peer=("127.0.0.1", 50001), path="lan",
                       rtt_ms=1.0, jitter_ms=0.0, delay=2, opponent={"name": "Bob"}, seed=7, key="k")


def start_event(mid="m1", players=None):
    return {"t": "match_start", "match": mid, "ticket": ticket(mid), "opponent": {"name": "Bob"},
            "fight": {"p1": "jin", "p2": "lili", "stage": "s20", "rounds": 3},
            "players": players if players is not None else
            [{"name": "Al Ice", "tier": 12, "guest": False}, {"name": "Bob", "tier": None, "guest": True}]}


class HudTest(unittest.TestCase):
    def test_hud_values(self):
        self.assertEqual(hud_values(start_event()), (["Al Ice", "Bob"], [12, 0]))
        self.assertIsNone(hud_values({"players": [{"name": "x"}]}))
        self.assertEqual(hud_values({"players": [{"name": "a" * 20, "tier": 99}, {"name": "b", "tier": 36}]}),
                         (["a" * 16, "b"], [0, 36]))

    def test_env_and_fight_line(self):
        d = tempfile.mkdtemp(prefix="drvhud")
        try:
            drv = MatchDriver(FakeClient(), FakeGame, d, mode="process")
            drv.fight_path = os.path.join(d, "fight.txt")
            drv.status_path = os.path.join(d, "status.json")
            ev = start_event()
            env = drv.match_env(ev, ev["ticket"])
            self.assertEqual(env["T5_HUD_NAMES"], "Al Ice|Bob")
            self.assertEqual(env["T5_HUD_RANKS"], "12,0")
            drv._write_fight_file("9,33,20,3", "m2", ev)
            with open(drv.fight_path) as f:
                line = f.read().strip()
            self.assertEqual(line, "9,33,20,3 names=Al%20Ice|Bob ranks=12|0 match=m2")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class MatchIdTest(unittest.TestCase):
    """A match id comes from the lobby server -- any server a player adds -- and goes into file names and the
    fight line. A server that sends a path must not make the launcher delete, write or move files elsewhere."""

    EVIL = ["..\\..\\..\\evil", "../../evil", "C:\\Windows\\x", "m1 pick=99 names=x", "m1\n", "",
            "x" * 41, "m1/../..", "con", "m:1"]

    def test_proto_refuses_them(self):
        from t5lobby import proto
        self.assertTrue(proto.valid_match_id("m752f00f03e2f"))
        for bad in self.EVIL[:-2] + [None, 7, ["m1"]]:
            if bad == "con":
                continue
            self.assertFalse(proto.valid_match_id(bad), bad)
        for bad in self.EVIL:
            safe = proto.file_safe(bad)
            self.assertRegex(safe, r"^[A-Za-z0-9_-]{1,40}$")

    def test_the_client_drops_a_message_with_such_an_id(self):
        import asyncio
        from t5lobby import proto
        from t5lobby.client import LobbyClient
        c = LobbyClient("127.0.0.1:1", util.BUILD)
        seen = []
        c._emit = seen.append
        loop = asyncio.new_event_loop()
        try:
            fut = loop.create_future()
            c._pending[5] = fut
            loop.run_until_complete(c._dispatch({"t": "match_found", "match": "..\\..\\evil", "re": 5}))
            loop.run_until_complete(c._dispatch({"t": "match_start", "match": "a b", "path": "lan"}))
            loop.run_until_complete(c._dispatch({"t": "notice", "match": "m1", "msg": "fine"}))
            self.assertIsInstance(fut.exception(), proto.LobbyError)
        finally:
            loop.close()
        self.assertEqual([e["t"] for e in seen], ["notice"])
        self.assertIsNone(c.match)

    def test_the_driver_keeps_its_files_in_its_folder(self):
        d = tempfile.mkdtemp(prefix="drvmid")
        outside = os.path.join(os.path.dirname(d), os.path.basename(d) + "-outside")
        os.makedirs(outside)
        victim = os.path.join(outside, "victim.json")
        with open(victim, "w") as f:
            f.write("{}")
        try:
            launched = []
            drv = MatchDriver(FakeClient(), lambda env: launched.append(FakeGame(env)) or launched[-1], d,
                              mode="process")
            rel = os.path.relpath(os.path.join(outside, "victim"), d)
            evil = os.sep.join(["x", "..", rel])         # result-x\..\..\<outside>\victim.json before the fix
            ev = start_event(evil)
            ev["ticket"] = ticket("m1")
            drv.on_event(ev)
            for path in (drv.result_path, drv.fight_path, drv.status_path):
                self.assertEqual(os.path.dirname(os.path.abspath(path)), os.path.abspath(d), path)
            self.assertTrue(os.path.exists(victim))
            self.assertNotIn("..", launched[0].env.get("T5_FIGHT_FILE", ""))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(outside, ignore_errors=True)


class SessionLogTest(unittest.TestCase):
    def test_a_new_session_forgets_the_last_peer(self):
        g = GameLog(None)
        for ln in ("[netplay] connected (host, P1), delay 2, peer 1.2.3.4:5",
                   "[netplay] peer lost (peer_quit): the opponent left"):
            g.line(ln)
        self.assertEqual((g.connected, g.peer_lost, g.session_lost), (True, 1, 1))
        g.line("[netplay] session 2 set up (handshake running); the keyread thread stays parked")
        self.assertEqual((g.connected, g.peer_lost, g.session_lost, g.sessions), (False, 1, 0, 2))
        g.line("[netplay] connected (join, P2), delay 3, peer 5.6.7.8:9")
        self.assertTrue(g.connected)


class PersistentFallbackTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="drvctl")
        self.launched = []
        self.saved = match_driver.CTL_ACK_SECONDS, match_driver.CTL_ACK_BOOT_SECONDS
        match_driver.CTL_ACK_SECONDS = match_driver.CTL_ACK_BOOT_SECONDS = 0.2

    def tearDown(self):
        match_driver.CTL_ACK_SECONDS, match_driver.CTL_ACK_BOOT_SECONDS = self.saved
        shutil.rmtree(self.d, ignore_errors=True)

    def launch(self, env):
        g = FakeGame(env)
        self.launched.append(g)
        return g

    def test_a_game_that_does_not_answer_is_replaced_by_a_process(self):
        drv = MatchDriver(FakeClient(), self.launch, self.d, mode="persistent")
        drv.on_event(start_event("m1"))
        self.assertEqual(len(self.launched), 1)
        self.assertIn("T5_CTL_DIR", self.launched[0].env)
        self.assertNotIn("T5_NET_MODE", self.launched[0].env)
        with open(os.path.join(self.d, "ctl", "cmd.json")) as f:
            cmd = json.load(f)
        self.assertEqual((cmd["cmd"], cmd["match"], cmd["env"]["T5_NET_MODE"]), ("fight", "m1", "host"))
        self.assertEqual(cmd["env"]["T5_HUD_NAMES"], "Al Ice|Bob")
        time.sleep(0.3)
        drv.poll()
        self.assertEqual(drv.mode, "process")
        self.assertFalse(self.launched[0].alive)
        self.assertEqual(len(self.launched), 2)               # the same match, now as its own process
        self.assertEqual(self.launched[1].env["T5_NET_MODE"], "host")
        self.assertIn("T5_FIGHT", self.launched[1].env)

    def test_a_game_that_answers_stays(self):
        drv = MatchDriver(FakeClient(), self.launch, self.d, mode="persistent")
        drv.on_event(start_event("m1"))
        with open(os.path.join(self.d, "ctl", "state.json"), "w") as f:
            json.dump({"ctl": 1, "seq": 1, "state": "connecting"}, f)
        time.sleep(0.3)
        drv.poll()
        self.assertEqual((drv.mode, len(self.launched)), ("persistent", 1))
        # a new opponent: idle at match_found, then a fight command to the same game
        drv.on_event({"t": "match_found", "match": "m2"})
        drv.on_event(start_event("m2"))
        with open(os.path.join(self.d, "ctl", "cmd.json")) as f:
            cmd = json.load(f)
        self.assertEqual((cmd["cmd"], cmd["match"], cmd.get("rematch")), ("fight", "m2", False))
        self.assertEqual(len(self.launched), 1)


if __name__ == "__main__":
    unittest.main()
