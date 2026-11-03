"""The stub's real persistent entry, with networking and disk writes denied.

These tests exercise control dispatch, not UDP delivery or the real game.
"""
import importlib.util
import io
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch


STUB = Path(__file__).resolve().parents[1] / "tools" / "stub_game.py"


class PersistentEntryTest(unittest.TestCase):
    def run_commands(self, commands, *, play_result="ok", connect_result=True):
        spec = importlib.util.spec_from_file_location("stub_persistent_entry", STUB)
        stub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stub)
        events = []

        class Session:
            def __init__(self, env, game_no):
                self.env = env
                self.game_no = game_no
                self.match_id = env.get("T5_NET_MATCH")
                self.last = None
                self.mismatches = 0
                self.desync = env.get("T5_STUB_DESYNC") == "1" or str(game_no) in stub._list(
                    env.get("T5_STUB_DESYNC_AT"))
                events.append(("new", game_no))

            def open(self):
                events.append(("open", self.game_no))

            def connect(self):
                events.append(("connect", self.game_no))
                return connect_result

            def play(self, n, env):
                events.append(("play", self.game_no, self.match_id, n,
                               env.get("T5_NET_RESULT_FILE"), self.desync))
                return play_result

            def exchange(self, frames):
                events.append(("exchange", frames))
                return "ok"

            def close(self):
                events.append(("close", self.game_no))

        commands = iter(commands)
        with patch.object(stub, "Session", Session), \
                patch.object(stub, "replace"), \
                patch.object(stub.json, "load", side_effect=lambda f: next(commands)), \
                patch("builtins.open", side_effect=lambda *a, **k: io.StringIO()), \
                patch.object(stub.socket, "socket", side_effect=AssertionError("unexpected socket")), \
                patch.dict(os.environ, {"T5_CTL_DIR": "synthetic-control"}, clear=True), \
                patch.object(stub.time, "sleep"), patch.object(stub, "log"):
            rc = stub.main()
        return rc, events

    @staticmethod
    def fight(seq, mid, *, rematch=False, **env):
        return {"seq": seq, "cmd": "fight", "match": mid, "rematch": rematch,
                "env": dict(T5_NET_MATCH=mid, T5_NET_RESULT_FILE=mid + ".json", **env)}

    def test_rematch_keeps_the_session_and_updates_the_match(self):
        rc, events = self.run_commands([
            self.fight(1, "m1"),
            self.fight(2, "m2", rematch=True, T5_STUB_DESYNC_AT="2"),
            {"seq": 3, "cmd": "quit"},
        ])
        self.assertEqual(rc, 0)
        self.assertEqual([e for e in events if e[0] == "open"], [("open", 1)])
        self.assertEqual([e for e in events if e[0] == "connect"], [("connect", 1)])
        self.assertEqual([e for e in events if e[0] == "play"], [
            ("play", 1, "m1", 1, "m1.json", False),
            ("play", 2, "m2", 2, "m2.json", True),
        ])
        self.assertEqual(events[-1], ("close", 2))

    def test_idle_closes_before_a_fresh_session(self):
        _, events = self.run_commands([
            self.fight(1, "m1"), {"seq": 2, "cmd": "idle"},
            self.fight(3, "m2"), {"seq": 4, "cmd": "quit"},
        ])
        self.assertEqual([e for e in events if e[0] in ("new", "close")], [
            ("new", 1), ("close", 1), ("new", 2), ("close", 2),
        ])

    def test_waiting_for_a_command_services_the_existing_peer(self):
        _, events = self.run_commands([
            self.fight(1, "m1"), {"seq": 1, "cmd": "fight"},
            {"seq": 2, "cmd": "quit"},
        ])
        self.assertTrue(any(e[0] == "exchange" for e in events), events)

    def test_a_new_opponent_replaces_the_session_without_idle(self):
        _, events = self.run_commands([
            self.fight(1, "m1"), self.fight(2, "m2"), {"seq": 3, "cmd": "quit"},
        ])
        self.assertEqual([e for e in events if e[0] in ("new", "close")], [
            ("new", 1), ("close", 1), ("new", 2), ("close", 2),
        ])

    def test_failed_handshake_closes_the_socket(self):
        rc, events = self.run_commands([
            self.fight(1, "m1"), {"seq": 2, "cmd": "quit"},
        ], connect_result=False)
        self.assertEqual(rc, 0)
        self.assertFalse(any(e[0] == "play" for e in events))
        self.assertEqual(events[-1], ("close", 1))

    def test_failure_and_early_exit_close_the_socket(self):
        for result, expected in (("lost", 0), ("close", 7), ("crash", 3)):
            with self.subTest(result=result):
                rc, events = self.run_commands([
                    self.fight(1, "m1"), {"seq": 2, "cmd": "quit"},
                ], play_result=result)
                self.assertEqual(rc, expected)
                self.assertEqual([e for e in events if e[0] == "close"], [("close", 1)])


class SessionTimeoutTest(unittest.TestCase):
    """Real packet exchange under a fake clock/socket; no UDP socket is opened."""

    def exchange_short_calls(self, healthy):
        spec = importlib.util.spec_from_file_location("stub_session_timeout", STUB)
        stub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stub)

        class Clock:
            now = 0.0

            def time(self):
                return self.now

        clock = Clock()

        class Socket:
            def sendto(self, data, peer):
                pass

            def recvfrom(self, size):
                clock.now += 0.02 if healthy else 0.05
                if not healthy:
                    raise stub.socket.timeout()
                data = stub.MAGIC + bytes([stub.INPUT, 1, 3, 0]) + struct.pack("!II", 1, session.hash(1))
                return data, session.peer

        with patch.object(stub.time, "time", clock.time), \
                patch.object(stub.time, "perf_counter", clock.time), \
                patch.object(stub.socket, "socket", side_effect=AssertionError("unexpected socket")), \
                patch.object(stub, "log"):
            session = stub.Session({"T5_NET_MODE": "host", "T5_NET_TIMEOUT": "1"})
            session.frame = 1
            session.peer = ("synthetic-peer", 1)
            session.sock = Socket()
            results = []
            for _ in range(100):
                results.append(session.exchange(3))
                if results[-1] != "ok":
                    break
        return results, clock.now

    def test_a_vanished_peer_times_out_across_short_exchanges(self):
        results, elapsed = self.exchange_short_calls(healthy=False)
        self.assertEqual(results[-1], "lost", results)
        self.assertLess(elapsed, 1.2)

    def test_input_keeps_the_session_alive_across_short_exchanges(self):
        results, elapsed = self.exchange_short_calls(healthy=True)
        self.assertEqual(results, ["ok"] * 100)
        self.assertGreater(elapsed, 5)


if __name__ == "__main__":
    unittest.main()
