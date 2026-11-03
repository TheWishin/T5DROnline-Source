"""1.2.0 challenge delays: in-memory server methods and fake connections, no sockets or game.

The server must send equal values to both games, preserve explicit 8 even on a LAN, keep rematches,
and leave ranked and old clients on their existing policy.
"""
import math
import tempfile
import types
import unittest
from unittest import mock

import util
from test_region import Base
from t5lobby import proto
from t5lobby.handover import MatchTicket
from t5lobby.match_driver import MatchDriver
from t5lobby.server.lobby import CAPS, FEATURES, Challenge, Match, _challenge_auto_delay


class Delay8(Base):
    def pair(self, caps=("input_delay8",)):
        a, b = self.player("A", caps=caps), self.player("B", caps=caps)
        for p in (a, b):
            p.conn.player = p
            p.conn.closed = False
        return a, b

    async def asyncTearDown(self):
        for c in self.srv.challenges.values():
            c.timer.cancel()
        await super().asyncTearDown()

    def start(self, m, rtt=300, path="direct"):
        m.results = [dict(ok=True, rtt=rtt, jitter=0, peer=["127.0.0.1", 7000])] * 2
        # Replace only bookkeeping and external work. Real _start_match and _send_match_start
        # construct the two messages; no server is started, no socket opened, no game launched.
        with mock.patch.multiple(self.srv, _remember_pair=mock.Mock(), _spec_match_started=mock.Mock(),
                                 _timer=mock.Mock(), _save=mock.Mock(), _save_set=mock.Mock(),
                                 note=mock.Mock()), mock.patch.object(self.srv.tours, "match_live"):
            self.srv._start_match(m, path)
        return [next(msg for msg in reversed(p.conn.sent) if msg["t"] == "match_start") for p in m.players]

    async def test_cap_and_feature_are_advertised(self):
        self.assertIn("input_delay8", CAPS)
        self.assertIn("input_delay8", FEATURES)
        a, b = self.pair()
        self.assertTrue(a.public()["input_delay8"])
        b.conn.caps = frozenset()
        self.assertNotIn("input_delay8", b.public())

    async def test_auto_boundaries_and_preview_agree(self):
        a, b = self.pair()
        c = Challenge(a, b)
        for ms, n in ((0, 1), (60, 1), (60.1, 2), (100, 2), (100.1, 3), (150, 3), (150.1, 4),
                      (200, 4), (200.1, 5), (250, 5), (250.1, 6), (300, 6), (300.1, 7),
                      (350, 7), (350.1, 8), (5000, 8)):
            with self.subTest(ms=ms):
                self.assertEqual(_challenge_auto_delay(ms), n)
                self.assertEqual(self.srv._challenge_delay(c, {"known": True, "ms": ms}),
                                 {"frames": n, "auto": True})
        self.assertEqual(self.srv._challenge_delay(c, {"known": False, "ms": 300}),
                         {"frames": None, "auto": True})
        for bad in (None, True, "300", -1, math.nan, math.inf):
            self.assertIsNone(_challenge_auto_delay(bad))

    async def test_accept_every_numeric_choice_and_keep_eight_on_a_lan(self):
        a, b = self.pair()
        for n in range(9):
            a.last_challenge = 0
            reply = await self.srv.h_challenge(a.conn, {"player": b.id, "delay": n})
            self.assertEqual(reply["delay"], {"frames": n, "auto": False})
            self.srv._end_challenge(self.srv.challenges[reply["challenge"]], "cancelled")
        self.srv.retry_after.clear()
        a.last_challenge = 0
        reply = await self.srv.h_challenge(a.conn, {"player": b.id, "delay": 8})
        with mock.patch.object(self.srv, "_start_nat"):
            await self.srv.h_challenge_reply(b.conn, {"challenge": reply["challenge"], "accept": True})
        m = a.match
        self.assertEqual(m.casual_delay, 8)
        self.assertTrue(m.challenge_delay8)
        msgs = self.start(m, rtt=1)
        self.assertEqual([(q["delay"], q["input_delay"]) for q in msgs], [(8, 8), (8, 8)])
        ticket = MatchTicket(m.id, "host", 0, 7000, ("127.0.0.1", 7001), "direct", 1, 0,
                             msgs[0]["delay"], input_delay=msgs[0]["input_delay"])
        self.assertEqual(ticket.game_env()["T5_NET_DELAY"], "8")
        self.assertEqual(ticket.game_env()["T5_RB_NET_DELAY"], "8")

    async def test_new_auto_uses_measured_ping_on_both_pcs_and_ignores_personal_setting(self):
        a, b = self.pair()
        reply = await self.srv.h_challenge(a.conn, {"player": b.id, "delay": "auto"})
        with mock.patch.object(self.srv, "_start_nat"):
            await self.srv.h_challenge_reply(b.conn, {"challenge": reply["challenge"], "accept": True})
        m = a.match
        msgs = self.start(m)
        self.assertEqual([q["input_delay"] for q in msgs], [6, 6])
        with tempfile.TemporaryDirectory(dir=util.HERE) as tmp:
            drv = MatchDriver(types.SimpleNamespace(), lambda env: None, tmp, mode="process", input_delay="0")
            drv.extra_env["T5_RB_NET_DELAY"] = "0"
            for q in msgs:
                ticket = MatchTicket(q["match"], q["role"], q["slot"], 7000, ("127.0.0.1", 7001),
                                     q["path"], q["rtt_ms"], q["jitter_ms"], q["delay"], input_delay=q["input_delay"])
                env = drv.match_env({}, ticket)
                self.assertEqual(env["T5_RB_NET_DELAY"], "6")
                self.assertGreaterEqual(int(env["T5_NET_DELAY"]), 6)

    async def test_auto_relay_fallback_uses_its_measurement_on_both_pcs(self):
        a, b = self.pair()
        m = Match(a, b, False, "challenge")
        m.challenge_delay8 = True
        self.assertEqual([q["input_delay"] for q in self.start(m)], [6, 6])
        m.fallback, m.state = True, "relay"
        msgs = self.start(m, rtt=400, path="relay")
        self.assertEqual([(q["delay"], q["input_delay"]) for q in msgs], [(10, 8), (10, 8)])

    async def test_legacy_peer_in_either_slot_rejects_new_manual_values(self):
        a, b = self.pair()
        for old in (a, b):
            old.conn.caps = frozenset()
            for n in range(3, 9):
                with self.assertRaises(proto.LobbyError) as err:
                    await self.srv.h_challenge(a.conn, {"player": b.id, "delay": n})
                self.assertEqual(err.exception.code, proto.E_NOT_ALLOWED)
            c = Challenge(a, b)
            self.assertEqual(self.srv._challenge_delay(c, {"known": True, "ms": 300}),
                             {"frames": 4, "auto": True})
            old.conn.caps = frozenset(("input_delay8",))

    async def test_invalid_values_do_not_create_a_challenge(self):
        a, b = self.pair()
        for bad in (-1, 9, 30, True, False, 8.0, "8", [], {}):
            with self.subTest(delay=bad), self.assertRaises(proto.LobbyError) as err:
                await self.srv.h_challenge(a.conn, {"player": b.id, "delay": bad})
            self.assertEqual(err.exception.code, proto.E_BAD_REQUEST)
        self.assertFalse(self.srv.challenges)

    async def test_ranked_quick_and_legacy_auto_keep_server_policy(self):
        a, b = self.pair()
        for ranked, extended, explicit, want in ((True, True, 8, 4), (False, False, None, 4)):
            m = Match(a, b, ranked, "queue")
            m.challenge_delay8, m.casual_delay = extended, explicit
            msgs = self.start(m)
            self.assertEqual([q["input_delay"] for q in msgs], [want, want])
        self.srv.cfg.ranked_input_delay = 7
        m = Match(a, b, True, "queue")
        m.challenge_delay8, m.casual_delay = True, 0
        self.assertEqual([q["input_delay"] for q in self.start(m)], [7, 7])

    async def test_first_to_set_successor_keeps_explicit_eight_for_both_players(self):
        a, b = self.pair(caps=("input_delay8", "sets", "casual_sets"))
        reply = await self.srv.h_challenge(a.conn, {"player": b.id, "delay": 8, "first_to": 3})
        self.assertEqual(reply["first_to"], 3)
        with mock.patch.object(self.srv, "_start_nat"):
            await self.srv.h_challenge_reply(b.conn, {"challenge": reply["challenge"], "accept": True})
        previous = a.match
        gs = previous.set
        self.assertEqual(gs.first_to, 3)
        self.assertEqual([message["input_delay"] for message in self.start(previous)], [8, 8])
        # Isolate the next-game transition; result accounting has its own set tests.
        gs.current, gs.last = None, previous
        a.match = b.match = None
        with mock.patch.object(self.srv, "_start_nat"):
            self.srv._set_next(gs)
        following = a.match
        self.assertIs(following.set, gs)
        self.assertTrue(following.challenge_delay8)
        self.assertEqual(following.casual_delay, 8)
        self.assertEqual([message["input_delay"] for message in self.start(following)], [8, 8])

    async def test_rematches_keep_the_challenge_policy_in_fresh_and_running_sessions(self):
        a, b = self.pair()
        for chosen in (None, 0, 8):
            prev = Match(a, b, False, "challenge")
            prev.casual_delay, prev.challenge_delay8 = chosen, True
            self.start(prev)
            for keep in (False, True):
                with mock.patch.object(self.srv, "_start_nat"), mock.patch.object(self.srv, "_start_match"):
                    m = self.srv.create_match(a, b, ranked=False, origin="rematch", rematch_of=prev, keep=keep)
                self.assertTrue(m.challenge_delay8)
                self.assertEqual(m.casual_delay, chosen)
                self.assertEqual([q["input_delay"] for q in self.start(m)],
                                 [6 if chosen is None else chosen] * 2)


if __name__ == "__main__":
    unittest.main()
