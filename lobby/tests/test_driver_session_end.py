"""Public driver events must only keep a netplay session that is still alive.

These tests use the real MatchDriver and its log reader with inert game/client
handles. They do not start a game, socket or server.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t5lobby.handover import MatchTicket
from t5lobby.match_driver import MatchDriver


class SessionEndTest(unittest.TestCase):
    class Client:
        def __init__(self):
            self.keeps = []
            self.starts = []

        def game_started(self, mid):
            self.starts.append(mid)

        def set_next(self, mid, keep):
            self.keeps.append((mid, keep))

    class Game:
        def __init__(self, log_path):
            self.log_path = log_path
            self.proc = None
            self.alive = True

        def running(self):
            return self.alive

        def stop(self):
            self.alive = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="session_end_", dir=os.path.dirname(__file__))
        self.addCleanup(self.tmp.cleanup)
        self.log_path = os.path.join(self.tmp.name, "game.log")
        with open(self.log_path, "w", encoding="utf-8"):
            pass
        self.client = self.Client()
        self.launches = []

        def launch(env):
            game = self.Game(self.log_path)
            self.launches.append(game)
            return game

        self.driver = MatchDriver(self.client, launch, self.tmp.name, mode="process", ingame_rematch=False)
        self.addCleanup(self.driver.close)
        self.start("m1")
        self.say("[netplay] session 1 set up (handshake running); the keyread thread stays parked",
                 "[netplay] connected (host, P1), delay 2, peer 127.0.0.1:50001")

    def say(self, *lines):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in lines))

    def start(self, mid):
        ticket = MatchTicket(mid, "host", 0, 50000, ("127.0.0.1", 50001), "lan", 1.0, 0.0, 2,
                             opponent={"name": "Peer"})
        self.driver.on_event({"t": "match_start", "match": mid, "ticket": ticket,
                              "opponent": {"name": "Peer"}})

    def finish(self, mid):
        self.driver.on_event({"t": "match_result", "match": mid,
                              "set": {"rated": True, "next": {"in": 3}}})

    def test_ended_session_is_not_kept_for_the_next_set_game(self):
        self.say("[netplay] session 1 ends (idle): 120 packets in, 120 out, 0 mismatching frame(s)")
        self.finish("m1")
        self.assertEqual(self.client.keeps, [("m1", False)])

    def test_new_session_can_be_kept_after_the_previous_session_ended(self):
        self.say("[netplay] session 1 ends (idle): 120 packets in, 120 out, 0 mismatching frame(s)")
        self.finish("m1")
        self.assertEqual(self.client.keeps, [("m1", False)])
        self.start("m2")
        self.say("[netplay] session 2 set up (handshake running); the keyread thread stays parked",
                 "[netplay] connected (host, P1), delay 2, peer 127.0.0.1:50001")
        self.finish("m2")
        self.assertEqual(self.client.keeps[-1], ("m2", True))

    def test_live_session_continues_in_the_running_game(self):
        self.finish("m1")
        self.assertEqual(self.client.keeps, [("m1", True)])
        self.driver.on_event({"t": "match_start", "match": "m2", "continue": True,
                              "opponent": {"name": "Peer"}})
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(self.client.starts, ["m1", "m2"])
        self.finish("m2")
        self.assertEqual(self.client.keeps[-1], ("m2", True))


if __name__ == "__main__":
    unittest.main()
