"""Matchmaking by region (docs/RANKED.md "Matchmaking" and "Found match", docs/ONLINE.md).

Covers: the ping estimate of a pair is the best relay path -- the smallest sum of both players' round trips to a
relay, this server's own included -- so two players near a regional relay see its ping, not the detour through
the central server; clients that measured no regional relay (1.1.0, 1.1.1 against a server without relays, a relay
that is down or that only one of them reached) get the central estimate as before; the queues pair by that
estimate inside a window that widens while both wait and is gone after T5L_PING_ANY_SECONDS (quick: sooner), so
nobody waits for ever; strict ranked and the blind ready check stay as they were (the estimate's relay is never
sent to a blind player). End to end: real clients behind UDP delay proxies (lobby/tools/relay_e2e.py).
"""
import time
import unittest

import util  # noqa: F401 -- sys.path, T5_PORTMAP=0
from util import expect
from t5lobby.rating import Rating
from t5lobby.server import Config, LobbyServer
from t5lobby.server.lobby import Player
from t5lobby.server.relays import RelayNodeRef
from test_relays import Regional


class FakeConn:
    def __init__(self, caps=("relays",), build="b1"):
        self.build_id, self.release, self.ip = build, "", "127.0.0.1"
        self.caps = frozenset(caps)
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(**util.FAST))
        for rid in ("usw", "usc"):
            n = RelayNodeRef(rid, rid.upper(), "192.0.2.1", 7781, b"x" * 32)
            n.ip, n.alive = "192.0.2.1", True
            self.srv.relays.nodes[rid] = n

    async def asyncTearDown(self):
        self.srv.store.close()

    def player(self, name, rtt=20.0, relays=None, caps=("relays",), r=1500):
        """relays: {relay id: ms} as the client reported it (relay_rtt); caps () = a 1.1.0 client."""
        p = Player(FakeConn(caps), name, guest=False)
        p.rating = Rating(r, 80)
        p.server_rtt = rtt
        p.relay_rtt = dict(relays or {})
        self.srv.players[p.id] = p
        return p

    def queue(self, *players, mode="quick", waited=0.0):
        now = time.monotonic()
        for p in players:
            self.srv._enqueue(p, mode, now - waited)
        return now

    @staticmethod
    def names(made):
        return [{a.name, b.name} for a, b, _m in made]


class EstimateTest(Base):
    async def test_two_players_near_a_regional_relay(self):
        a = self.player("A", 150, {"usw": 25, "usc": 70})
        b = self.player("B", 155, {"usw": 30, "usc": 60})
        self.assertEqual(self.srv._est_ping(a, b), (55, True, "usw"))     # not 305 through the central server

    async def test_the_central_server_when_it_is_better(self):
        a = self.player("A", 20, {"usw": 160})
        b = self.player("B", 25, {"usw": 150})
        self.assertEqual(self.srv._est_ping(a, b), (45, True, "main"))

    async def test_older_clients_get_the_central_estimate(self):
        a = self.player("A", 150, {"usw": 25})
        old = self.player("Old", 150, caps=())                            # 1.1.0: no "relays" cap, no relay_rtt
        self.assertEqual(self.srv._est_ping(a, old), (300, True, "main"))
        b = self.player("B", 150, {})                                     # 1.1.1 on a server it measured nothing for
        self.assertEqual(self.srv._est_ping(a, b), (300, True, "main"))
        c = self.player("C", 150, {"usc": 20})                            # each measured a different relay
        self.assertEqual(self.srv._est_ping(a, c), (300, True, "main"))

    async def test_a_relay_that_is_down_does_not_count(self):
        a = self.player("A", 150, {"usw": 25})
        b = self.player("B", 150, {"usw": 25})
        self.srv.relays.nodes["usw"].alive = False
        self.assertEqual(self.srv._est_ping(a, b), (300, True, "main"))
        self.srv.relays.nodes["usw"].alive = True
        self.srv.relays.nodes["usw"].enabled = False
        self.assertEqual(self.srv._est_ping(a, b)[2], "main")

    async def test_unknown_round_trips(self):
        a = self.player("A", None)
        b = self.player("B", 40)
        self.assertEqual(self.srv._est_ping(a, b), (90, False, "main"))   # 50 for the unknown side, as before
        a.relay_rtt, b.relay_rtt = {"usw": 70}, {"usw": 60}
        self.assertEqual(self.srv._est_ping(a, b), (130, True, "usw"))    # a measured relay path beats a guess

    async def test_match_found_shows_the_estimate_and_hides_the_relay(self):
        self.srv.cfg.blind_ready = True
        a = self.player("A", 150, {"usw": 25}, caps=("relays", "blind_ready"))
        b = self.player("B", 150, {"usw": 30}, caps=("relays", "blind_ready"))
        self.queue(a, b)
        self.assertEqual(len(self.srv.match_queue()), 1)
        for p in (a, b):
            found = [m for m in p.conn.sent if m["t"] == "match_found"][0]
            self.assertEqual(found["ping"], {"ms": 55, "kind": "estimate", "known": True})
            self.assertTrue(found["blind"])
            self.assertIsNone(found["opponent"])
            self.assertNotIn("usw", repr(found))          # which relay would hint where the hidden opponent lives
        ev = [e for e in self.srv.events if e[1] == "match_found"][-1][2]
        self.assertEqual((ev["ping"], ev["via"]), (55, "usw"))


class QueueTest(Base):
    async def test_quick_pairs_neighbours_at_once(self):
        a = self.player("A", 150, {"usw": 25})
        b = self.player("B", 150, {"usw": 30})            # 55 through Oregon
        now = self.queue(a, b)
        self.assertEqual(self.names(self.srv.match_queue(now)), [{"A", "B"}])

    async def test_quick_prefers_the_nearer_opponent(self):
        ca = self.player("CA", 150, {"usw": 25})
        eu = self.player("EU", 20, {"usw": 160})          # 170 through Nuremberg
        ca2 = self.player("CA2", 150, {"usw": 30})        # 55 through Oregon
        now = self.queue(ca, eu, ca2, waited=40.0)        # (both windows wide open: still the nearest first)
        self.assertEqual(self.names(self.srv.match_queue(now)), [{"CA", "CA2"}])
        self.assertEqual(eu.status, "queue")

    async def test_quick_window_widens_and_then_anyone_goes(self):
        a = self.player("A", 150, caps=())                # two old clients, 300 through Nuremberg
        b = self.player("B", 150, caps=())
        now = self.queue(a, b)
        self.assertEqual(self.srv.match_queue(now), [])                   # 80 ms at first
        self.assertEqual(self.srv.match_queue(now + 10.0), [])            # 80 + 20/s: 280
        self.assertEqual(self.names(self.srv.match_queue(now + 11.0)), [{"A", "B"}])   # 300
        c = self.player("C", 450, caps=())
        d = self.player("D", 450, caps=())                # 900: never inside the window
        now = self.queue(c, d)
        self.assertEqual(self.srv.match_queue(now + 29.0), [])
        self.assertEqual(self.names(self.srv.match_queue(now + 30.0)), [{"C", "D"}])   # nobody waits for ever

    async def test_ranked_neighbours_at_once_and_far_pairs_after_a_minute(self):
        a = self.player("A", 150, {"usw": 25})
        b = self.player("B", 150, {"usw": 30}, r=1550)
        now = self.queue(a, b, mode="ranked")
        self.assertEqual(self.names(self.srv.match_queue(now)), [{"A", "B"}])      # 55, not 300
        c = self.player("C", 400, caps=())
        d = self.player("D", 400, caps=())                # 800: never paired before (the window stopped at 400 ms)
        now = self.queue(c, d, mode="ranked")
        self.assertEqual(self.srv.match_queue(now + 59.0), [])            # 80 + 10/s: 670
        self.assertEqual(self.names(self.srv.match_queue(now + 60.0)), [{"C", "D"}])

    async def test_ranked_takes_the_nearer_of_two_equal_ratings(self):
        a = self.player("A", 150, {"usw": 25})
        far = self.player("Far", 20, {"usw": 200}, r=1500)     # 170 through Nuremberg
        near = self.player("Near", 150, {"usw": 35}, r=1520)  # 60 through Oregon
        now = self.queue(a, far, near, mode="ranked", waited=30.0)
        self.assertEqual(self.names(self.srv.match_queue(now)), [{"A", "Near"}])

    async def test_strict_still_holds_after_the_ping_window_is_gone(self):
        a = self.player("A", 150, {"usw": 25})
        b = self.player("B", 150, {"usw": 30}, r=1700)
        a.strict = True
        now = self.queue(a, b, mode="ranked", waited=600.0)
        self.assertEqual(self.srv.match_queue(now), [])

    async def test_the_window_is_a_setting(self):
        self.srv.cfg.ping_start = 400.0
        a = self.player("A", 150, caps=())
        b = self.player("B", 150, caps=())
        now = self.queue(a, b)
        self.assertEqual(len(self.srv.match_queue(now)), 1)
        self.srv.cfg.ping_start, self.srv.cfg.quick_ping_any_seconds = 80.0, 0.0     # 0: no "any ping" at all
        self.assertEqual(self.srv._ping_limit(10000.0, "quick"), 80.0 + 20.0 * 10000.0)


    async def test_a_window_that_starts_at_zero(self):
        """review-112: T5L_PING_START=0 (a window of 0 ms at first) and a ranked pair whose estimate is 0 (both on the
        server's LAN): ping / limit was 0 / 0 -- ZeroDivisionError out of match_queue on every tick, nobody paired."""
        self.srv.cfg.ping_start = 0.0
        a = self.player("A", 0.0, caps=())
        b = self.player("B", 0.0, caps=(), r=1520)
        now = self.queue(a, b, mode="ranked")
        self.assertEqual(self.names(self.srv.match_queue(now)), [{"A", "B"}])

# ============================================================================== end to end
class FoundPingEndToEnd(Regional):
    """Real clients: two players in "California" -- 150 ms to the central server, 25 to a relay in "Oregon"."""
    rtt = {"main": (150, 150), "usw": (25, 25), "usc": (90, 90)}
    server_cfg = {"force_relay": True, "blind_ready": True}

    def test_the_estimate_is_the_regional_path_and_the_match_goes_there(self):
        a = self.player("Alice", 0, blind_ready=True)
        b = self.player("Bob", 1, blind_ready=True)
        for c in (a, b):
            self.measured(c, ["usw", "usc"])
        t0 = time.monotonic()
        a.quick_match()
        b.quick_match()
        fa, fb = expect(a, "match_found", 10), expect(b, "match_found", 10)
        self.assertLess(time.monotonic() - t0, 3.0)                      # paired at once: neighbours
        for ev in (fa, fb):
            self.assertTrue(ev["ping"]["known"])
            self.assertTrue(40 <= ev["ping"]["ms"] <= 110, ev["ping"])   # ~50 through Oregon, not ~300
            self.assertIsNone(ev["opponent"])
        ea = expect(a, "match_start", 30)
        self.assertEqual(ea["relay"]["id"], "usw")

    def test_an_older_client_gets_the_central_estimate(self):
        a = self.player("Alice", 0)
        b = self.player("Bob", 1, relays=False)                           # a launcher before regional relays
        self.measured(a, ["usw"])
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.by_name["bob"].server_rtt is not None, 10))
        self.s.call(lambda: setattr(self.s.cfg, "quick_ping_any_seconds", 1.0))   # (not 30 s of waiting here)
        a.quick_match()
        b.quick_match()
        fb = expect(b, "match_found", 15)
        self.assertGreater(fb["ping"]["ms"], 250)                         # through the central server, as before
        self.assertTrue(fb["ping"]["known"])


if __name__ == "__main__":
    unittest.main()
