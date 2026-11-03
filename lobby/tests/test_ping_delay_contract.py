"""Deterministic legacy ping-delay coverage without starting a server or sockets.

Drive production match-start and client dispatch with measured jitter, then run
the existing end-to-end assertion body against those events. Network delivery,
registration and challenge scheduling remain covered by the server-backed test.
"""
import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

import util
import test_net_ping
from t5lobby.client import LobbyClient
from t5lobby.server import Config, LobbyServer


class PingDelayContract(unittest.TestCase):
    def check_delay(self, jitter, lockstep):
        # __new__ deliberately avoids server initialization. Only the match
        # start/message logic runs; storage, scheduling and stage lookup are fakes.
        srv = object.__new__(LobbyServer)
        srv.cfg = Config(ping_delays="-1:3", ingame_pick=0)
        for name in ("_cancel_timers", "_remember_pair", "_spec_match_started",
                     "_timer", "_save", "_count", "note", "_log_ping_delay"):
            setattr(srv, name, mock.Mock())
        srv.tours = SimpleNamespace(match_live=mock.Mock())
        srv.table = SimpleNamespace(resolve=lambda *args, **kw: ("first", "second", "arena"))
        srv._casual_stage = mock.Mock(return_value="arena")
        srv._casual_start_info = mock.Mock(return_value={})
        srv._can = mock.Mock(return_value=False)
        players = []
        for side in range(2):
            p = SimpleNamespace(send=mock.Mock(), brief=lambda side=side: {"name": str(side)})
            players.append(p)
        match = SimpleNamespace(
            id="m000000000001", players=players, fallback=False, state="punch",
            results=[{"rtt": 0.0, "jitter": jitter, "peer": ("127.0.0.1", 1)} for _ in players],
            ranked=False, challenge_delay8=False, casual_delay=None, set=None,
            tag=b"", picks=("first", "second"), relay_info=None, key=None,
            build_id="", compat_group="", continued=False, rematch_of=None,
            training=False, life=None,
        )
        srv._start_match(match, "direct")
        self.assertEqual(match.delay, lockstep)
        events = []

        async def receive_starts():
            for p in players:
                c = LobbyClient("127.0.0.1:1", util.BUILD, input_delay8=False)
                c.match = {"match": match.id, "state": "nat"}
                c._gs = SimpleNamespace(port=1, dup=None, confirmed=set(),
                                        _punch_to=mock.Mock(), close=mock.AsyncMock())
                await c._dispatch(p.send.call_args.args[0])
                events.append(c.events.get_nowait())

        # An accidental transport call fails immediately. The asyncio loop is
        # created before this guard because Windows loop construction uses sockets.
        loop = asyncio.new_event_loop()
        try:
            with mock.patch("socket.socket.__init__", side_effect=AssertionError("unexpected socket")):
                loop.run_until_complete(receive_starts())
        finally:
            loop.close()
        expected = min(3, lockstep)
        for ev in events:
            self.assertEqual(ev["input_delay"], expected)
            self.assertEqual(ev["ticket"].input_delay, expected)
            self.assertEqual(ev["ticket"].game_env()["T5_RB_NET_DELAY"], str(expected))

        # Keep the integration test's precise assertions under deterministic
        # delays, including a lockstep delay greater than the configured floor.
        case = test_net_ping.EndToEnd("test_input_delay_and_the_measured_ping_of_the_next_challenge")
        a, b = mock.Mock(), mock.Mock()
        a.me, b.me = {"id": "a"}, {"id": "b"}
        case.c = mock.Mock(side_effect=[a, b])
        case.s = SimpleNamespace(wait_for=mock.Mock(return_value=True), call=mock.Mock())
        replies = [{"ping": {"kind": "estimate"}}, *events, {},
                   {"ping": {"kind": "measured", "path": "direct", "ms": round(match.rtt)}}]
        with mock.patch.object(test_net_ping, "expect", side_effect=replies), \
                mock.patch.object(test_net_ping.time, "sleep"):
            case.test_input_delay_and_the_measured_ping_of_the_next_challenge()

    def test_lockstep_below_floor(self):
        self.check_delay(0.0, 2)

    def test_lockstep_at_floor(self):
        self.check_delay(16.0, 3)

    def test_lockstep_above_floor(self):
        self.check_delay(33.0, 4)

    def test_lockstep_at_ceiling(self):
        self.check_delay(200.0, 10)


if __name__ == "__main__":
    unittest.main()
