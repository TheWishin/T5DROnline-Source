"""1.1.5 ping before a match, matchmaking by measured ping, and the input delay of far matches (docs/ONLINE.md "Ping",
docs/RANKED.md "Matchmaking", docs/NETPLAY.md "Input delay").

Covers: the lobby list carries each player's round trips to the regional relays (only noticeable changes go out), so a
launcher estimates its ping to anybody the way the server does -- the best relay both measured, not the sum through
the central server (two players in North America read ~50 ms, not ~200); the measured ping and path of two players
who played is remembered (queues, the ready check, challenges and invites show it: "measured", path), expires, and
never tells a blind ready check that the hidden opponent is an old acquaintance; the path guess from two symmetric
NATs; above T5L_PING_DELAYS' thresholds both PCs get a higher rollback input delay in match_start (ranked too); the
launcher's list shows measured pings without "~"."""
import time
import types
import unittest

import util
from util import ServerThread, client, expect
from t5lobby.server.lobby import _ping_delay_floor
from test_region import Base


class RelayRttsInTheListTest(Base):
    async def test_the_list_carries_the_relay_round_trips(self):
        a = self.player("A", 150)
        conn = types.SimpleNamespace(player=a)
        await self.srv.h_relay_rtt(conn, {"rtts": {"usw": 25.4, "usc": 70.0, "nope": 5}})
        self.assertEqual(a.public()["relays"], {"usw": 25, "usc": 70})
        self.srv.dirty = False
        await self.srv.h_relay_rtt(conn, {"rtts": {"usw": 27.0, "usc": 71.0}})     # jitter: the list stays
        self.assertEqual(a.public()["relays"], {"usw": 25, "usc": 70})
        self.assertFalse(self.srv.dirty)
        await self.srv.h_relay_rtt(conn, {"rtts": {"usw": 60.0, "usc": 71.0}})     # moved: the list changes
        self.assertEqual(a.public()["relays"], {"usw": 60, "usc": 71})
        self.assertTrue(self.srv.dirty)
        await self.srv.h_relay_rtt(conn, {"rtts": {"usw": 60.0}})                  # usc no longer reached
        self.assertEqual(a.public()["relays"], {"usw": 60})

    async def test_an_older_client_has_no_relays_field(self):
        old = self.player("Old", 150, caps=())
        self.assertNotIn("relays", old.public())

    async def test_a_relay_taken_out_of_relays_json_leaves_the_list(self):
        a = self.player("A", 150)
        await self.srv.h_relay_rtt(types.SimpleNamespace(player=a), {"rtts": {"usw": 25, "usc": 70}})
        del self.srv.relays.nodes["usc"]
        self.srv._relays_changed()
        self.assertEqual(a.public()["relays"], {"usw": 25})


def fake_match(a, b, rtt, path, ranked=False, delay=None):
    from t5lobby import proto
    return types.SimpleNamespace(players=[a, b], rtt=rtt, path=path, ranked=ranked,
                                 delay=proto.suggest_delay(rtt) if delay is None else delay)


class PairMemoryTest(Base):
    async def test_a_pair_that_played_gets_its_measured_ping(self):
        a = self.player("A", 150, {"usw": 160})
        b = self.player("B", 150, {"usw": 150})           # 300 through Nuremberg, 310 through Oregon
        self.assertEqual(self.srv._est_ping(a, b), (300, True, "main"))
        self.srv._remember_pair(fake_match(a, b, 35.0, "direct"))     # neighbours far from every server
        self.assertEqual(self.srv._est_ping(b, a), (35.0, True, "measured"))
        self.assertEqual(self.srv._ping_info(a, b), {"ms": 35, "kind": "measured", "known": True, "path": "direct"})
        other = self.player("C", 150, {"usw": 150})
        self.assertEqual(self.srv._est_ping(a, other)[2], "main")      # only that pair

    async def test_it_expires(self):
        a, b = self.player("A", 150), self.player("B", 150)
        self.srv._remember_pair(fake_match(a, b, 35.0, "direct"))
        self.srv.cfg.pair_ping_days = -1.0
        self.assertIsNone(self.srv._pair_measured(a, b))
        self.assertEqual(self.srv.pair_net, {})

    async def test_bad_measurements_are_not_kept_and_the_memory_is_bounded(self):
        a, b = self.player("A", 150), self.player("B", 150)
        self.srv._remember_pair(fake_match(a, b, None, "direct", delay=2))
        self.srv._remember_pair(fake_match(a, b, 30.0, None))
        self.srv._remember_pair(fake_match(a, a, 30.0, "direct"))
        self.assertEqual(self.srv.pair_net, {})
        self.srv.PAIR_NET_MAX = 3
        players = [self.player(f"P{i}", 50) for i in range(5)]
        for q in players:
            self.srv._remember_pair(fake_match(a, q, 40.0, "relay"))
        self.assertEqual(len(self.srv.pair_net), 3)
        self.assertIsNone(self.srv._pair_measured(a, players[0]))      # the oldest went first
        self.assertEqual(self.srv._pair_measured(a, players[4]), (40.0, "relay"))

    async def test_the_queue_pairs_them_at_once(self):
        a = self.player("A", 150, caps=())
        b = self.player("B", 150, caps=())                # 300: outside the first window
        now = self.queue(a, b)
        self.assertEqual(self.srv.match_queue(now), [])
        self.srv._remember_pair(fake_match(a, b, 30.0, "direct"))
        self.assertEqual(self.names(self.srv.match_queue(now)), [{"A", "B"}])

    async def test_quick_prefers_the_measured_neighbour(self):
        a = self.player("A", 100, caps=())
        far = self.player("Far", 20, caps=())             # 120 through the server
        near = self.player("Near", 150, caps=())          # 250 through the server, 30 measured
        self.srv._remember_pair(fake_match(a, near, 30.0, "direct"))
        now = self.queue(a, far, near, waited=40.0)
        self.assertEqual(self.names(self.srv.match_queue(now)), [{"A", "Near"}])

    async def test_a_blind_ready_check_does_not_tell_who_it_is(self):
        self.srv.cfg.blind_ready = True
        a = self.player("A", 150, caps=("relays", "blind_ready"))
        b = self.player("B", 150, caps=("relays", "blind_ready"))
        self.srv._remember_pair(fake_match(a, b, 42.0, "direct"))
        self.queue(a, b)
        self.assertEqual(len(self.srv.match_queue()), 1)
        for p in (a, b):
            found = [m for m in p.conn.sent if m["t"] == "match_found"][0]
            self.assertTrue(found["blind"])
            self.assertEqual(found["ping"], {"ms": 42, "kind": "estimate", "known": True, "path": "direct"})

    async def test_not_blind_it_says_measured(self):
        a = self.player("A", 150, caps=("relays",))
        b = self.player("B", 150, caps=("relays",))
        self.srv._remember_pair(fake_match(a, b, 42.0, "relay"))
        self.queue(a, b)
        self.assertEqual(len(self.srv.match_queue()), 1)
        found = [m for m in a.conn.sent if m["t"] == "match_found"][0]
        self.assertEqual(found["ping"], {"ms": 42, "kind": "measured", "known": True, "path": "relay"})


class PathGuessTest(Base):
    async def test_two_unpredictable_symmetric_nats_go_through_a_relay(self):
        a, b = self.player("A"), self.player("B")
        self.assertIsNone(self.srv._guess_path(a, b))                  # nothing known: the direct path is tried
        a.nat_seen, b.nat_seen = (True, False), (True, False)
        self.assertEqual(self.srv._guess_path(a, b), "relay")
        a.nat_seen = (True, True)                                      # one predictable: still the relay (_maybe_punch)
        self.assertEqual(self.srv._guess_path(a, b), "relay")
        b.nat_seen = (True, True)                                      # both predictable: the punch walks the ports
        self.assertIsNone(self.srv._guess_path(a, b))
        a.nat_seen, b.nat_seen = (False, False), (True, False)
        self.assertIsNone(self.srv._guess_path(a, b))
        self.assertNotIn("path", self.srv._ping_info(a, b))

    async def test_the_last_match_wins_and_force_relay_is_always_the_relay(self):
        a, b = self.player("A"), self.player("B")
        a.nat_seen = b.nat_seen = (True, False)
        self.srv._remember_pair(fake_match(a, b, 60.0, "direct"))     # (their relay bridges found the direct path)
        self.assertEqual(self.srv._guess_path(a, b), "direct")
        self.srv.cfg.force_relay = True
        self.assertEqual(self.srv._guess_path(a, b), "relay")

    async def test_the_nat_phase_notes_what_it_saw(self):
        a, b = self.player("A"), self.player("B")
        m = types.SimpleNamespace(players=[a, b])
        self.srv._note_nat(m, [(True, 4), (False, None)], [[5000, 5001], []])
        self.assertEqual((a.nat_seen, b.nat_seen), ((True, True), (False, False)))


class ChallengeAndInvitePingTest(Base):
    async def test_a_challenge_carries_the_ping(self):
        from t5lobby.server.lobby import _ConnOf
        a = self.player("A", 150, {"usw": 25})
        b = self.player("B", 150, {"usw": 30})
        r = await self.srv.h_challenge(_ConnOf(a), {"player": b.id})
        ev = [m for m in b.conn.sent if m["t"] == "challenged"][0]
        self.assertEqual(ev["ping"], {"ms": 55, "kind": "estimate", "known": True})
        self.assertEqual(r["ping"], ev["ping"])
        for c in list(self.srv.challenges.values()):
            c.timer.cancel()


class InputDelayTest(Base):
    def test_the_setting(self):
        self.assertIsNone(_ping_delay_floor("150:3,250:4", 150.0))
        self.assertEqual(_ping_delay_floor("150:3,250:4", 151.0), 3)
        self.assertEqual(_ping_delay_floor("250:4,150:3", 300.0), 4)
        self.assertIsNone(_ping_delay_floor("", 300.0))
        self.assertEqual(_ping_delay_floor("x,150:3,200:y,100:99", 300.0), 3)    # bad parts are left out
        self.assertIsNone(_ping_delay_floor("150:3", None))

    async def test_casual_and_ranked(self):
        a, b = self.player("A"), self.player("B")
        d = self.srv._input_delay
        self.assertIsNone(d(fake_match(a, b, 80.0, "direct")))           # each player's own setting, as before
        self.assertEqual(d(fake_match(a, b, 160.0, "relay")), 3)
        self.assertEqual(d(fake_match(a, b, 260.0, "relay")), 4)
        self.assertEqual(d(fake_match(a, b, 80.0, "direct", ranked=True)), 2)   # T5L_RANKED_INPUT_DELAY
        self.assertEqual(d(fake_match(a, b, 160.0, "relay", ranked=True)), 3)
        self.srv.cfg.ranked_input_delay = 5
        self.assertEqual(d(fake_match(a, b, 160.0, "relay", ranked=True)), 5)   # (never lower than ranked's own)
        self.assertEqual(d(fake_match(a, b, 260.0, "relay", delay=3)), 3)       # never above the lockstep delay
        self.srv.cfg.ping_delays = ""
        self.assertIsNone(d(fake_match(a, b, 400.0, "relay")))


class ClientPingTest(unittest.TestCase):
    """The launcher's side: the Ping column and the ping of a challenge from an older server."""

    def setUp(self):
        from t5lobby.client import LobbyClient
        self.c = LobbyClient("127.0.0.1:1", util.BUILD)
        self.c.me = {"id": "pme", "name": "Me"}
        self.c.server_rtt = 100.0
        self.c.relay_rtts = {"usw": 20.0, "usc": 70.0}

    def test_the_best_relay_both_measured(self):
        """The player's report: two friends in North America read ~200 ms (both round trips to Nuremberg)."""
        friend = {"id": "p1", "name": "Friend", "guest": False, "rtt": 100.0, "relays": {"usw": 30, "usc": 60}}
        self.assertEqual(self.c.ping_to(friend), (50.0, False))
        far = {"id": "p2", "name": "Far", "guest": False, "rtt": 10.0, "relays": {"usw": 160}}
        self.assertEqual(self.c.ping_to(far), (110.0, False))                  # the central server is better here
        old = {"id": "p3", "name": "Old", "guest": True, "rtt": 100.0}         # a 1.1.4 server: no relays in the list
        self.assertEqual(self.c.ping_to(old), (200.0, False))
        self.assertEqual(self.c.ping_to({"id": "pme", "name": "Me", "rtt": 1.0}), (None, False))
        self.assertEqual(self.c.ping_to({"id": "p4", "name": "New", "rtt": None}), (None, False))
        self.c.relay_rtts = {}                                                 # an older launcher's view: as before
        self.assertEqual(self.c.ping_to(friend), (200.0, False))

    def test_a_measured_ping_wins_and_has_no_tilde(self):
        from t5lobby.tk_tab import _ping_cell
        friend = {"id": "p1", "name": "Friend", "guest": False, "rtt": 100.0, "relays": {"usw": 30}}
        self.c._remember_peer_ping({"t": "match_start", "opponent": {"id": "p1", "name": "friend", "guest": False},
                                    "rtt_ms": 41.6, "path": "direct"})
        self.assertEqual(self.c.ping_to(friend), (41.6, True))
        self.assertEqual(self.c.ping_to(dict(friend, id="p9")), (41.6, True))   # (logged in again: a new id)
        self.assertEqual(self.c.ping_to(dict(friend, guest=True)), (50.0, False))  # a guest of that name is not them
        self.assertEqual((_ping_cell(41.6, True), _ping_cell(50.0), _ping_cell(None)), ("42 ms", "~50 ms", ""))
        for bad in ({"opponent": {"name": "x"}, "rtt_ms": None}, {"opponent": {"name": "x"}, "rtt_ms": True},
                    {"opponent": None, "rtt_ms": 5}, {"opponent": {"name": "x"}, "rtt_ms": -1}):
            self.c._remember_peer_ping(bad)
        self.assertEqual(list(self.c.peer_pings), [("friend", False)])

    def test_the_ping_of_a_challenge(self):
        server_ping = {"ms": 55, "kind": "estimate", "known": True, "path": "relay"}
        self.assertIs(self.c.ping_info({"t": "challenged", "from": {"id": "p1"}, "ping": server_ping}), server_ping)
        # an older server sends none: the launcher's own estimate from the lobby list
        self.c._pmap = {"p1": {"id": "p1", "name": "Friend", "guest": False, "rtt": 100.0, "relays": {"usw": 30}}}
        self.assertEqual(self.c.ping_info({"t": "challenged", "from": {"id": "p1", "name": "Friend"}}),
                         {"ms": 50, "kind": "estimate", "known": True})
        self.assertIsNone(self.c.ping_info({"t": "challenged", "from": {"id": "p2", "name": "Nobody"}}))
        self.assertIsNone(self.c.ping_info({"t": "match_found", "opponent": None}, "opponent"))
        # 1.1.7: a server ping it does not know (a round trip not measured yet) gives way to the launcher's own
        unknown = {"ms": 100, "kind": "estimate", "known": False, "path": "relay"}
        self.assertEqual(self.c.ping_info({"t": "challenged", "from": {"id": "p1", "name": "Friend"}, "ping": unknown}),
                         {"ms": 50, "kind": "estimate", "known": True, "path": "relay"})
        self.assertIs(self.c.ping_info({"t": "challenged", "from": {"id": "p2", "name": "Nobody"}, "ping": unknown}),
                      unknown)                                                 # nothing better here: the server's
        self.assertIs(self.c.ping_info({"t": "match_found", "opponent": None, "ping": unknown}, "opponent"), unknown)

    def test_the_bar_text(self):
        from t5lobby.tk_views import ping_text
        self.assertEqual(ping_text({"ms": 55, "kind": "estimate", "known": True}),
                         "ping about 55 ms (estimated; measured directly once you both accept)")
        self.assertEqual(ping_text({"ms": 42, "kind": "measured", "known": True, "path": "relay"}),
                         "ping 42 ms (measured in your last match together), probably through a relay server")
        self.assertEqual(ping_text({"ms": 90, "known": False}), "ping not known yet")
        self.assertEqual(ping_text(None), "ping not known yet")


# ============================================================================== end to end
class EndToEnd(unittest.TestCase):
    def setUp(self):
        # "-1:3": every round trip is above -1 ms -- this PC's matches stand in for far ones
        self.s = ServerThread(ping_delays="-1:3").start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name):
        c = client(self.s, name)
        self.clients.append(c)
        return c

    def test_input_delay_and_the_measured_ping_of_the_next_challenge(self):
        a, b = self.c("Alice"), self.c("Bob")
        cid = a.challenge(b.me["id"])
        ev = expect(b, "challenged")
        self.assertEqual(ev["ping"]["kind"], "estimate")
        b.answer_challenge(cid, accept=True)
        sa, sb = expect(a, "match_start", 15), expect(b, "match_start", 15)
        # both PCs: T5_RB_NET_DELAY -- 3, but never above the lockstep delay of a match on this PC (2)
        self.assertEqual((sa["input_delay"], sb["input_delay"]), (sa["delay"], sa["delay"]))
        self.assertEqual(sa["ticket"].input_delay, 2)
        self.assertEqual(sa["ticket"].game_env()["T5_RB_NET_DELAY"], "2")
        a.report_result(0, [3, 1])
        b.report_result(0, [3, 1])
        expect(a, "match_result")
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.by_name["alice"].status == "idle"
                                        and self.s.srv.by_name["bob"].status == "idle"))
        self.s.call(lambda: self.s.srv.retry_after.clear())
        time.sleep(2.1)                                                       # one challenge per 2 s
        a.challenge(b.me["id"])
        ev = expect(b, "challenged")
        self.assertEqual(ev["ping"]["kind"], "measured")
        self.assertIn(ev["ping"].get("path"), ("lan", "direct"))
        self.assertEqual(ev["ping"]["ms"], round(sa["rtt_ms"]))


if __name__ == "__main__":
    unittest.main()
