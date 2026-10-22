"""The Tekken 6 style lobby features (docs/RANKED.md, "Tekken 6 style options"):

1. the blind ready check: the ping first, the opponent's name after both accepted
2. blocking players (queues, rooms, challenges, rematches; mid-match counts as leaving)
3. strict matchmaking (+-150 rating points)
4. the 30 s same-opponent cooldown
5. the character lock of a ranked set
6. the post-game lag check, and leaving the set without a penalty
7. server notices from the admin tool
8. no IP address in any message a player reads
"""
import contextlib
import io
import json
import os
import re
import socket
import tempfile
import time
import types
import unittest

import util
from util import BUILD, ServerThread, client, expect
from t5lobby import lag as lagmod, proto
from t5lobby.client import LobbyClient
from t5lobby.match_driver import GameLog, MatchDriver
from t5lobby.proto import LobbyError
from t5lobby.rating import Rating
from t5lobby.server import Config, LobbyServer, admin
from t5lobby.server.lobby import Player

IPV4 = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name=None, **kw):
        c = client(self.s, name, **kw)
        self.clients.append(c)
        return c

    def acc(self, name, **kw):
        kw.setdefault("auto_ready", True)
        return self.c(name, password="pw-" + name, register=True, **kw)

    def ranked(self, a, b, ca=None, cb=None):
        a.ranked_match(ca)
        b.ranked_match(cb)
        return expect(a, "match_start"), expect(b, "match_start")

    def finish(self, a, b, ev, winner=None):
        w = ev["slot"] if winner is None else winner
        a.report_result(w, None)
        b.report_result(w, None)
        return expect(a, "match_result"), expect(b, "match_result")

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))

    def player(self, name):
        return self.s.call(lambda: self.s.srv.by_name.get(name.lower()))

    def even_ratings(self, *names):
        """Everybody back to 1500: a fresh queue only pairs ratings 100 points apart, and a first game moves them far."""
        for n in names:
            p = self.player(n)
            self.s.call(lambda p=p: setattr(p, "rating", Rating(1500, 80)))

    def set_rtt(self, name, ms):
        self.s.call(lambda: setattr(self.s.srv.by_name[name.lower()], "server_rtt", ms))


# ============================================================================== 1. blind ready check
class BlindReadyTest(Base):
    server_cfg = {"blind_ready": True, "ready_timeout": 8.0}

    def test_default_timeout_is_15_seconds(self):
        self.assertEqual(Config().ready_timeout, 15.0)
        self.assertEqual(Config.from_env({"T5L_READY_TIMEOUT": "9"}).ready_timeout, 9.0)
        self.assertTrue(Config().blind_ready)

    def test_ping_first_name_after_both_accepted(self):
        a = self.c("Alice", blind_ready=True)                      # accepts by hand
        b = self.c("Bob", blind_ready=True)
        self.set_rtt("Alice", 30.0)
        self.set_rtt("Bob", 45.0)
        a.quick_match()
        b.quick_match()
        fa, fb = expect(a, "match_found"), expect(b, "match_found")
        for ev in (fa, fb):
            self.assertTrue(ev["blind"])
            self.assertTrue(ev["ready_check"])
            self.assertIsNone(ev["opponent"])
            self.assertNotIn("role", ev)                           # the sides are hidden as well
            self.assertNotIn("slot", ev)
            self.assertEqual(ev["ready_timeout"], 8.0)
            # the ping the server can tell before the PCs are connected: both players' UDP round trips to it
            self.assertEqual(ev["ping"], {"ms": 75, "kind": "estimate", "known": True})
        self.assertNotIn("Bob", json.dumps(fa))
        self.assertNotIn("Alice", json.dumps(fb))
        a.ready()
        self.assertEqual(expect(b, "opponent_ready")["match"], fb["match"])
        self.assertIsNone(b.next_event(0.8, ("match_reveal",)))    # one player accepting reveals nothing
        b.ready()
        ra, rb = expect(a, "match_reveal"), expect(b, "match_reveal")
        self.assertEqual((ra["opponent"]["name"], rb["opponent"]["name"]), ("Bob", "Alice"))
        self.assertEqual({ra["role"], rb["role"]}, {"host", "join"})
        self.assertEqual({ra["slot"], rb["slot"]}, {0, 1})
        self.assertEqual(a.match["opponent"]["name"], "Bob")       # the client library kept it
        ea, eb = expect(a, "match_start"), expect(b, "match_start")
        self.assertEqual(ea["slot"], ra["slot"])                   # the sides revealed are the sides played
        self.assertEqual(eb["opponent"]["name"], "Alice")
        # ... and the ping measured between the two PCs comes with match_start, as it always did
        self.assertGreaterEqual(ea["rtt_ms"], 0.0)

    def test_old_clients_and_mixed_pairs_still_see_the_name(self):
        seen_b = []
        a = self.c("Alice", blind_ready=True)
        b = self.c("Bob", auto_ready=True, on_event=lambda ev: seen_b.append(ev["t"]))   # an older client: no blind_ready
        a.quick_match()
        b.quick_match()
        fa, fb = expect(a, "match_found"), expect(b, "match_found")
        self.assertTrue(fa["blind"])
        self.assertFalse(fb.get("blind"))
        self.assertEqual(fb["opponent"]["name"], "Alice")
        self.assertIn(fb["role"], ("host", "join"))
        self.assertEqual(fb["ping"]["ms"], fa["ping"]["ms"])       # both see the same number
        a.ready()
        self.assertEqual(expect(a, "match_reveal")["opponent"]["name"], "Bob")
        expect(a, "match_start")
        expect(b, "match_start")
        self.assertNotIn("match_reveal", seen_b)                   # nothing new for the old client

    def test_the_server_can_switch_it_off(self):
        self.s.call(lambda: setattr(self.s.srv.cfg, "blind_ready", False))
        a = self.c("Alice", blind_ready=True, auto_ready=True)
        b = self.c("Bob", blind_ready=True, auto_ready=True)
        a.quick_match()
        b.quick_match()
        fa = expect(a, "match_found")
        self.assertFalse(fa.get("blind"))
        self.assertEqual(fa["opponent"]["name"], "Bob")

    def test_decline_leaks_nothing_and_requeues_the_other(self):
        a = self.c("Alice", blind_ready=True)
        b = self.c("Bob", blind_ready=True)
        a.quick_match()
        b.quick_match()
        expect(a, "match_found")
        expect(b, "match_found")
        a.ready(accept=False)
        cb = expect(b, "match_cancel")
        self.assertEqual(cb["reason"], "declined")
        self.assertFalse(cb["you"])
        self.assertNotIn("Alice", json.dumps(cb))
        self.assertEqual(self.player("Bob").status, "queue")

    def test_not_answering_cancels_after_the_timeout(self):
        self.s.call(lambda: setattr(self.s.srv.cfg, "ready_timeout", 0.6))
        a = self.c("Alice", blind_ready=True, auto_ready=True)
        b = self.c("Bob", blind_ready=True)
        a.quick_match()
        b.quick_match()
        self.assertEqual(expect(b, "match_cancel")["reason"], "ready_timeout")
        self.assertEqual(self.player("Alice").status, "queue")

    def test_slow_pc_warning_does_not_name_the_opponent_yet(self):
        a = self.c("Alice", blind_ready=True)
        b = self.c("Bob", blind_ready=True)
        a.report_perf(30)
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.by_name["alice"].fps == 30.0))
        a.quick_match()
        b.quick_match()
        na, nb = expect(a, "notice"), expect(b, "notice")
        self.assertEqual(na["code"], nb["code"], "slow_pc")
        self.assertIn("your PC ran its last match at 30 fps", na["msg"])
        self.assertIn("your opponent's PC ran its last match at 30 fps", nb["msg"])
        self.assertNotIn("Alice", nb["msg"])

    def test_rooms_and_challenges_show_names_as_before(self):
        a = self.c("Alice", blind_ready=True)
        b = self.c("Bob", blind_ready=True)
        room = a.create_room("dojo")
        b.join_room(room["id"])
        fa = expect(a, "match_found")
        self.assertFalse(fa.get("blind"))                          # you chose the room: you know who is in it
        self.assertEqual(fa["opponent"]["name"], "Bob")
        self.assertEqual(fa["role"], "host")
        self.assertEqual(fa["ping"]["kind"], "estimate")           # (the ping is shown there as well)


# ============================================================================== 2. blocking
class BlockTest(Base):
    def both_wait(self, a, b, mode):
        (a.ranked_match if mode == "ranked" else a.quick_match)()
        (b.ranked_match if mode == "ranked" else b.quick_match)()
        self.assertIsNone(a.next_event(2.0, ("match_found",)))
        self.assertIsNone(b.next_event(0.1, ("match_found",)))
        a.cancel_queue()
        b.cancel_queue()

    def test_a_blocked_pair_is_never_matched_ranked_or_quick(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        r = a.block("Bob")
        self.assertEqual((r["name"], r["blocks"], r["left_match"]), ("Bob", 1, None))
        self.both_wait(a, b, "quick")
        self.both_wait(a, b, "ranked")
        # other players still match: Cleo gets one of the two, the other waits
        c = self.acc("Cleo")
        a.ranked_match()
        b.ranked_match()
        c.ranked_match()
        mf = expect(c, "match_found", 6)
        self.assertIn(mf["opponent"]["name"], ("Alice", "Bob"))

    def test_the_block_is_kept_on_the_account_and_can_be_lifted(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.block("Bob")
        self.assertEqual([r["name"] for r in a.blocks()], ["Bob"])
        self.assertEqual(b.blocks(), [])                           # the blocked player is not told
        aid = self.account("Alice")["id"]
        self.assertEqual(self.s.call(lambda: [r["blocked_name"] for r in self.s.srv.store.blocks_of(aid)]), ["Bob"])
        a.close()
        self.clients.remove(a)
        self.s.wait_for(lambda: "alice" not in self.s.srv.by_name)
        a2 = self.c("Alice", password="pw-Alice", auto_ready=True)       # a new session, the block is still there
        self.assertEqual([r["name"] for r in a2.blocks()], ["Bob"])
        self.both_wait(a2, b, "quick")
        a2.unblock("Bob")
        self.assertEqual(a2.blocks(), [])
        self.assertEqual(self.s.call(lambda: self.s.srv.store.blocks_of(aid)), [])
        a2.quick_match()
        b.quick_match()
        expect(a2, "match_found")
        with self.assertRaises(LobbyError) as e:
            a2.unblock("Bob")
        self.assertEqual(e.exception.code, proto.E_NOT_FOUND)

    def test_guests_block_for_the_session_only(self):
        g, a = self.c("Gus", auto_ready=True), self.acc("Alice")
        g.block("Alice")                                           # a guest blocks an account: kept in memory
        self.both_wait(a, g, "quick")
        count = lambda: self.s.call(lambda: self.s.srv.store.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0])  # noqa: E731
        self.assertEqual(count(), 0)                               # (nothing to store it on)
        g.close()
        self.clients.remove(g)
        self.s.wait_for(lambda: "gus" not in self.s.srv.by_name)
        g2 = self.c("Gus", auto_ready=True)                        # a new session starts with no blocks
        self.assertEqual(g2.blocks(), [])
        a.block("Gus")                                             # an account blocks a guest: by name, this session
        self.assertEqual(count(), 0)
        self.both_wait(a, g2, "quick")
        a.close()
        self.clients.remove(a)
        self.s.wait_for(lambda: "alice" not in self.s.srv.by_name)
        a2 = self.c("Alice", password="pw-Alice", auto_ready=True)
        self.assertEqual(a2.blocks(), [])                          # the guest block did not outlive the session

    def test_no_challenge_no_room_either_way(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.block("Bob")
        for src, dst in ((b, a), (a, b)):
            with self.assertRaises(LobbyError) as e:
                src.challenge(dst.me["id"])
            self.assertEqual(e.exception.code, proto.E_NOT_ALLOWED)
        room = a.create_room("dojo")
        with self.assertRaises(LobbyError) as e:
            b.join_room(room["id"])
        self.assertEqual(e.exception.code, proto.E_NOT_ALLOWED)
        self.assertEqual(self.player("Bob").status, "idle")

    def test_blocking_in_a_running_ranked_game_is_leaving_it(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        r = a.block("Bob")
        self.assertEqual(r["left_match"], ea["match"])
        ra, rb = expect(a, "match_result"), expect(b, "match_result")
        self.assertEqual((ra["status"], ra["reason"], ra["blame"]), ("forfeit", "quit", "you"))
        self.assertEqual((rb["status"], rb["blame"]), ("forfeit", "opponent"))
        self.assertLess(self.account("Alice")["rating"], 1500)     # a loss, exactly as for quitting
        self.assertGreater(self.account("Bob")["rating"], 1500)

    def test_blocking_right_after_a_game_withdraws_the_rematch(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        ra, rb = self.finish(a, b, ea)
        rating = self.account("Alice")["rating"]
        b.rematch(rb["match"], True, keep=True)
        self.assertEqual(expect(a, "rematch")["state"], "offered")
        a.block("Bob")
        self.assertEqual(expect(b, "rematch")["state"], "declined")
        se = expect(b, "set_end")
        self.assertEqual((se["reason"], se["by"]), ("left", "opponent"))      # (a block is not announced as one)
        with self.assertRaises(LobbyError):
            a.rematch(ra["match"], True)                           # the offer is gone
        self.assertEqual(self.account("Alice")["rating"], rating)  # blocking after the game changes no rating

    def test_blocking_before_the_game_starts_cancels_it(self):
        a, b = self.acc("Alice", auto_ready=False), self.acc("Bob", auto_ready=False)
        a.quick_match()
        b.quick_match()
        expect(a, "match_found")
        expect(b, "match_found")
        a.block("Bob")
        self.assertEqual(expect(b, "match_cancel")["reason"], "opponent_left")
        self.assertEqual(self.player("Alice").status, "idle")

    def test_rules(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        for name, code in (("Alice", proto.E_BAD_REQUEST), ("Nobody", proto.E_NOT_FOUND), ("x", proto.E_NOT_FOUND)):
            with self.assertRaises(LobbyError) as e:
                a.block(name)
            self.assertEqual(e.exception.code, code, name)
        b.close()
        self.clients.remove(b)
        self.s.wait_for(lambda: "bob" not in self.s.srv.by_name)
        self.assertEqual(a.block("Bob")["name"], "Bob")            # an account can be blocked while offline
        self.assertEqual(a.block("Bob")["blocks"], 1)              # twice is once
        self.s.call(lambda: setattr(self.s.srv.cfg, "max_blocks", 1))
        c = self.acc("Cleo")
        with self.assertRaises(LobbyError) as e:
            a.block("Cleo")
        self.assertEqual(e.exception.code, proto.E_NOT_ALLOWED)


class BlockEarlyQuitTest(Base):
    server_cfg = {"min_match_seconds": 30.0}

    def test_blocking_at_once_is_an_early_quit(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        a.block("Bob")
        ra = expect(a, "match_result")
        self.assertEqual((ra["status"], ra["reason"], ra["blame"]), ("void", "early_quit", "you"))
        self.assertEqual(self.account("Alice")["rating"], 1500.0)


# ============================================================================== 3./4. strict + cooldown (matchmaker)
class FakeConn:
    def __init__(self, build="b1"):
        self.build_id, self.release, self.ip = build, "", "127.0.0.1"
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


class MatchmakerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(**util.FAST))

    async def asyncTearDown(self):
        self.srv.store.close()

    def player(self, name, r, rtt=20.0, strict=False):
        p = Player(FakeConn(), name, guest=False)
        p.rating = Rating(r, 80)
        p.server_rtt = rtt
        p.strict = strict
        self.srv.players[p.id] = p
        return p

    def queue(self, *players, mode="ranked", waited=100.0):
        now = time.monotonic()
        for p in players:
            self.srv._enqueue(p, mode, now - waited)
        return now

    async def test_strict_pairs_only_within_150_points_however_long_it_takes(self):
        a = self.player("A", 1500, strict=True)
        b = self.player("B", 1651)                                  # 151 apart
        now = self.queue(a, b, waited=600.0)                        # (the normal window is 800 by now)
        self.assertEqual(self.srv.match_queue(now), [])
        self.assertEqual((a.status, b.status), ("queue", "queue"))
        c = self.player("C", 1650)                                  # exactly 150
        self.srv._enqueue(c, "ranked", now - 600.0)
        made = self.srv.match_queue(now)
        self.assertEqual({made[0][0].name, made[0][1].name}, {"A", "C"})
        self.assertEqual(b.status, "queue")

    async def test_strict_counts_for_the_other_player_too(self):
        a = self.player("A", 1500)
        b = self.player("B", 1700, strict=True)                    # the strict one is the higher rating
        now = self.queue(a, b, waited=600.0)
        self.assertEqual(self.srv.match_queue(now), [])
        b.strict = False
        self.assertEqual(len(self.srv.match_queue(now)), 1)         # off by default: the wide window applies

    async def test_the_range_is_a_setting(self):
        self.srv.cfg.strict_range = 300.0
        a = self.player("A", 1500, strict=True)
        b = self.player("B", 1790)
        now = self.queue(a, b, waited=600.0)
        self.assertEqual(len(self.srv.match_queue(now)), 1)

    async def test_strict_is_for_ranked_only(self):
        a = self.player("A", 1000, strict=True)
        b = self.player("B", 2000)
        now = self.queue(a, b, mode="quick")
        self.assertEqual(len(self.srv.match_queue(now)), 1)         # quick matches ignore ratings entirely

    async def test_cooldown_between_the_same_two(self):
        self.srv.cfg.pair_cooldown = 30.0
        a, b, c = self.player("A", 1500), self.player("B", 1500), self.player("C", 1520)
        now = self.queue(a, b, c)
        self.srv.pair_last[frozenset((self.srv._pair_id(a), self.srv._pair_id(b)))] = time.monotonic() - 5.0
        made = self.srv.match_queue(now)
        self.assertEqual(len(made), 1)
        self.assertNotEqual({made[0][0].name, made[0][1].name}, {"A", "B"})    # not these two, only 5 s after
        self.assertEqual(self.srv.match_queue(now), [])             # the third is left over with nobody new

    async def test_cooldown_ends_after_30_seconds_and_is_for_ranked_only(self):
        self.srv.cfg.pair_cooldown = 30.0
        a, b = self.player("A", 1500), self.player("B", 1500)
        now = self.queue(a, b)
        key = frozenset((self.srv._pair_id(a), self.srv._pair_id(b)))
        self.srv.pair_last[key] = time.monotonic() - 29.0
        self.assertEqual(self.srv.match_queue(now), [])
        self.srv.pair_last[key] = time.monotonic() - 31.0
        self.assertEqual(len(self.srv.match_queue(now)), 1)
        # a quick (casual) match is not held back
        c, d = self.player("C", 1500), self.player("D", 1500)
        now = self.queue(c, d, mode="quick")
        self.srv.pair_last[frozenset((self.srv._pair_id(c), self.srv._pair_id(d)))] = time.monotonic()
        self.assertEqual(len(self.srv.match_queue(now)), 1)


class StrictAndCooldownE2ETest(Base):
    server_cfg = {"pair_cooldown": 2.0}

    def test_strict_option_travels_with_the_queue_request(self):
        a = self.acc("Alice")
        self.assertEqual(a.welcome["strict_range"], 150.0)
        r = a.ranked_match(strict=True)
        self.assertTrue(r["strict"])
        self.assertTrue(self.player("Alice").strict)
        a.cancel_queue()
        self.assertFalse(a.ranked_match()["strict"])                # off unless asked for
        self.assertFalse(self.player("Alice").strict)

    def test_the_same_two_wait_before_the_queue_matches_them_again(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        self.finish(a, b, ea)
        self.even_ratings("Alice", "Bob")
        t0 = time.monotonic()
        a.ranked_match()
        b.ranked_match()
        self.assertIsNone(a.next_event(1.0, ("match_found",)))
        expect(a, "match_found", 6.0)
        self.assertGreaterEqual(time.monotonic() - t0, 1.2)         # (2 s from the end of the game)

    def test_casual_matches_and_rematches_are_not_held_back(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        ra, rb = self.finish(a, b, ea)
        a.rematch(ra["match"], True, keep=True)
        b.rematch(rb["match"], True, keep=True)
        self.assertTrue(expect(a, "match_start")["continue"])       # the rematch dialog is the players' own choice
        self.finish(a, b, ea)
        a.quick_match()
        b.quick_match()
        expect(a, "match_found", 3.0)

    def test_other_opponents_are_available_during_the_cooldown(self):
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Cleo")
        ea, eb = self.ranked(a, b)
        self.finish(a, b, ea)
        self.even_ratings("Alice", "Bob", "Cleo")
        a.ranked_match()
        c.ranked_match()
        self.assertEqual(expect(c, "match_found", 4.0)["opponent"]["name"], "Alice")


# ============================================================================== 5. character lock
class CharLockTest(Base):
    def chars(self, ev):
        f = ev["fight"]
        return (f["p1"], f["p2"]) if ev["slot"] == 0 else (f["p2"], f["p1"])        # (mine, theirs)

    def test_a_ranked_set_keeps_both_characters(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b, "jin", "paul")
        self.assertEqual(self.chars(ea), ("jin", "paul"))
        ra, rb = self.finish(a, b, ea)
        self.assertTrue(ra["set"]["locked"])
        with self.assertRaises(LobbyError) as e:
            a.set_char("kazuya")
        self.assertEqual(e.exception.code, proto.E_STATE)
        a.set_char("jin")                                           # the same character is no change
        # even if the pick on the server were changed behind the lock's back, the set decides
        alice = self.player("Alice")
        self.s.call(lambda: setattr(alice, "char", "kazuya"))
        a.rematch(ra["match"], True, keep=True)
        b.rematch(rb["match"], True, keep=True)
        s = expect(a, "match_start")
        self.assertEqual(self.chars(s), ("jin", "paul"))
        self.assertEqual((s["set"]["id"], s["set"]["game"], s["set"]["locked"]),
                         (ra["set"]["id"], 2, True))

    def test_the_lock_starts_when_the_match_is_found(self):
        a, b = self.acc("Alice", auto_ready=False), self.acc("Bob", auto_ready=False)
        a.ranked_match("jin")
        b.ranked_match("paul")
        mf = expect(a, "match_found")
        self.assertTrue(mf["set"]["locked"])
        with self.assertRaises(LobbyError) as e:
            a.set_char("law")
        self.assertEqual(e.exception.code, proto.E_STATE)
        b.ready(accept=False)                                       # the match falls through: the set was never played
        self.assertEqual(expect(a, "set_end")["reason"], "cancelled")
        a.set_char("law")

    def test_casual_sets_are_not_locked(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.quick_match("jin")
        b.quick_match("paul")
        ea, eb = expect(a, "match_start"), expect(b, "match_start")
        ra, rb = self.finish(a, b, ea)
        self.assertFalse(ra["set"]["locked"])
        a.set_char("kazuya")
        a.rematch(ra["match"], True, keep=True)
        b.rematch(rb["match"], True, keep=True)
        self.assertEqual(self.chars(expect(a, "match_start"))[0], "kazuya")

    def test_leaving_the_set_unlocks(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b, "jin", "paul")
        ra, rb = self.finish(a, b, ea)
        b.rematch(rb["match"], False)                               # declining the rematch ends the set
        se = expect(a, "set_end")
        self.assertEqual((se["reason"], se["by"]), ("declined", "opponent"))
        a.set_char("kazuya")
        b.set_char("law")

    def test_leaving_the_lobby_ends_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b, "jin", "paul")
        self.finish(a, b, ea)
        b.close()
        self.clients.remove(b)
        se = expect(a, "set_end")
        self.assertEqual((se["reason"], se["by"]), ("left", "opponent"))
        a.set_char("kazuya")

    def test_queueing_again_leaves_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b, "jin", "paul")
        self.finish(a, b, ea)
        a.ranked_match("kazuya")                                   # a new opponent wanted: a new set, a new pick
        self.assertEqual(expect(b, "rematch")["state"], "declined")
        self.assertEqual(expect(b, "set_end")["reason"], "left")
        self.assertEqual(self.player("Alice").char, "kazuya")

    def test_ranked_rooms_keep_the_set_across_rematches(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        room = a.create_room("dojo", ranked=True)
        a.set_char("jin")
        b.set_char("paul")
        b.join_room(room["id"])
        f1 = expect(a, "match_found")
        ea = expect(a, "match_start")
        expect(b, "match_start")
        self.finish(a, b, ea)
        with self.assertRaises(LobbyError):
            a.set_char("law")
        a.rematch()                                                 # the next game in the room
        f2 = expect(a, "match_found")
        self.assertEqual(f2["set"]["id"], f1["set"]["id"])
        s = expect(a, "match_start")
        self.assertEqual(self.chars(s), ("jin", "paul"))
        self.assertEqual(s["set"]["game"], 2)


class CharLockExpiryTest(Base):
    server_cfg = {"rematch_window": 1.0}

    def test_the_set_ends_when_the_rematch_window_runs_out(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b, "jin", "paul")
        self.finish(a, b, ea)
        se = expect(a, "set_end", 5.0)
        self.assertEqual((se["reason"], se["by"]), ("expired", None))
        a.set_char("law")


# ============================================================================== 6. lag check
class LagUnitTest(unittest.TestCase):
    def rep(self, ms_per_frame, pc_fps=60.0, frames=3000):
        return lagmod.clean_report({"frames": frames, "waited_ms": frames * ms_per_frame, "pc_fps": pc_fps})

    def test_as_expected(self):
        # (1.1.5: a few seconds of waiting in a match, as most matches have; 1.1.4's test waited 5 ms a frame)
        a = lagmod.assess(3, [self.rep(0.2), self.rep(0.9)])
        self.assertEqual((a["expected"], a["verdict"], a["cause"]), (3, "ok", None))
        self.assertAlmostEqual(a["observed"], 3 + 0.9 / proto.FRAME_MS, delta=0.06)
        self.assertIn("It was 3.1.", lagmod.describe(85.0, a, 0, [self.rep(0.2), self.rep(0.9)]))
        self.assertIn("Ping 85 ms should mean about 3 frames behind.", lagmod.describe(85.0, a, 0))

    def test_more_than_the_ping_explains(self):
        a = lagmod.assess(3, [self.rep(40.0), self.rep(40.0)])
        self.assertEqual((a["verdict"], a["cause"]), ("more_lag", "network"))
        self.assertAlmostEqual(a["observed"], 3 + 40.0 / proto.FRAME_MS, delta=0.06)
        self.assertIn("more than the ping explains", lagmod.describe(85.0, a, 0))
        self.assertIn("connection stalled", lagmod.describe(85.0, a, 0))

    def test_a_slow_pc_is_named_for_each_side(self):
        reports = [self.rep(0.5, pc_fps=41.0), self.rep(30.0, pc_fps=60.0)]
        a = lagmod.assess(3, reports, warn_fps=55.0)
        self.assertEqual((a["verdict"], a["cause"], a["slow"]), ("more_lag", "pc", [0]))
        self.assertIn("Your PC was the slow one (41 fps)", lagmod.describe(60.0, a, 0, reports))
        self.assertIn("Your opponent's PC was the slow one (41 fps)", lagmod.describe(60.0, a, 1, reports))

    def test_nothing_reported(self):
        a = lagmod.assess(3, [None, None])
        self.assertEqual((a["verdict"], a["observed"]), ("unknown", None))
        self.assertIn("nothing to compare", lagmod.describe(60.0, a, 0))

    # 1.1.5: the waits per frame looked fine while the games stood still much of the match
    def full(self, waited_s, fps=59.5, pc_fps=60.0, frames=10800):
        return lagmod.clean_report({"frames": frames, "waited_ms": waited_s * 1000.0, "pc_fps": pc_fps, "fps": fps})

    def test_a_third_of_the_match_waiting_is_flagged(self):
        # production 2026-10-21, gozmo vs joebudden, direct 97 ms, delay 5: 1.1.4 stored observed 5.6, "ok"
        reports = [self.full(92.0, 39.8, 60.2, 10192), self.full(94.8, 39.8, 60.2, 10192)]
        a = lagmod.assess(5, reports)
        self.assertEqual((a["verdict"], a["cause"], a["slow"]), ("slow", "network", []))
        self.assertEqual(a["observed"], 5.6)                         # (the frames behind still look like the ping)
        self.assertEqual(a["waited_s"], [92.0, 94.8])
        self.assertAlmostEqual(a["share"], 94.8 / (10192 / 39.8), delta=0.002)
        self.assertIsNone(a["waited_more"])                          # about the same on both PCs
        self.assertEqual(a["why"], "network: the games waited 92 s / 95 s of 256 s (37 %) for each other's inputs")
        self.assertEqual(lagmod.describe(97.0, a, 0, reports),
                         "This match lagged: the games waited 95 s for each other's inputs. "
                         "A wired connection and no uploads during matches help.")
        self.assertTrue(lagmod.lagged(a["verdict"]))

    def test_the_usual_waits_stay_ok(self):
        # 1.1.4 matches, ~3 minutes: direct median 0.5 s/min, p90 2.4 s/min; relay median 1.1 s/min
        for per_min in (0.5, 1.1, 2.4):
            a = lagmod.assess(4, [self.full(per_min * 3), self.full(per_min * 3 * 0.9)])
            self.assertEqual(a["verdict"], "ok", per_min)
            self.assertIsNone(a["why"])
        # the relay's p90 (4.7 s/min, 8 % of the match) is flagged; so are the relay rematches' worst (8.5 s in 3 min:
        # 4.7 %) only from T5L_LAG_WAIT_SHARE 0.04
        self.assertEqual(lagmod.assess(4, [self.full(14.1), self.full(13.0)])["verdict"], "slow")
        self.assertEqual(lagmod.assess(4, [self.full(8.5), self.full(8.0)])["verdict"], "ok")
        self.assertEqual(lagmod.assess(4, [self.full(8.5), self.full(8.0)], wait_share=0.04)["verdict"], "slow")
        self.assertEqual(lagmod.assess(4, [self.full(14.1), None], wait_share=0)["verdict"], "ok")      # 0 = off

    def test_a_short_match_needs_a_few_seconds_of_waiting(self):
        self.assertEqual(lagmod.assess(3, [self.full(2.5, frames=900), None])["verdict"], "ok")     # 15 s, 2.5 s
        self.assertEqual(lagmod.assess(3, [self.full(3.5, frames=900), None])["verdict"], "slow")

    def test_fps_well_below_the_pcs_own_speed(self):
        # no clear share of waiting reported, but the game ran at 48 fps on a 60 fps PC
        r = lagmod.clean_report({"frames": 10800, "waited_ms": 8000.0, "pc_fps": 60.0, "fps": 48.0})
        self.assertEqual(lagmod.assess(4, [r, None])["verdict"], "slow")

    def test_the_side_that_waited_more_is_named(self):
        reports = [self.full(4.0), self.full(20.0)]
        a = lagmod.assess(4, reports)
        self.assertEqual((a["verdict"], a["waited_more"]), ("slow", 1))
        self.assertTrue(a["why"].endswith("; P2's game waited more"), a["why"])

    def test_a_slow_pc_behind_long_waits(self):
        reports = [self.full(20.0, 40.0, 44.0), self.full(22.0)]
        a = lagmod.assess(4, reports, warn_fps=55.0)
        self.assertEqual((a["verdict"], a["cause"], a["slow"]), ("slow", "pc", [0]))
        self.assertTrue(a["why"].startswith("pc: below full speed: P1 44 fps; the games waited 20 s / 22 s"), a["why"])
        self.assertEqual(lagmod.describe(60.0, a, 0, reports),
                         "This match lagged: the games waited 22 s for each other's inputs. "
                         "Your PC was the slow one (44 fps).")

    def test_reports_are_validated(self):
        self.assertIsNone(lagmod.clean_report({"frames": 100, "waited_ms": 1}))          # too short to say anything
        self.assertIsNone(lagmod.clean_report({"frames": "x", "waited_ms": 1}))
        self.assertIsNone(lagmod.clean_report({"frames": 900, "waited_ms": -5}))
        r = lagmod.clean_report({"frames": 900, "waited_ms": 12, "pc_fps": 1e9})
        self.assertIsNone(r["pc_fps"])


class LagCheckTest(Base):
    server_cfg = {"lag_wait": 0.6}

    def played(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        ra, rb = self.finish(a, b, ea)
        return a, b, ea, ra

    def test_both_players_get_the_same_numbers(self):
        a, b, ea, ra = self.played()
        mid = ra["match"]
        a.report_lag(mid, 3000, 3000 * 0.17, 60.1, 59.9)
        self.assertIsNone(b.next_event(0.2, ("lag_check",)))        # one report: still waiting for the other
        b.report_lag(mid, 3000, 3000 * 0.34, 59.8, 59.5)
        la, lb = expect(a, "lag_check"), expect(b, "lag_check")
        for k in ("ping_ms", "expected_frames", "observed_frames", "verdict", "cause", "match", "path"):
            self.assertEqual(la[k], lb[k], k)
        self.assertEqual(la["expected_frames"], ea["delay"])        # "ping X should mean about Y frames behind"
        self.assertAlmostEqual(la["ping_ms"], ea["rtt_ms"], delta=0.06)
        self.assertEqual(la["verdict"], "ok")
        self.assertAlmostEqual(la["observed_frames"], ea["delay"] + 0.34 / proto.FRAME_MS, delta=0.06)
        self.assertEqual(la["yours"]["extra_frames"], lb["opponent"]["extra_frames"])      # the same numbers, turned round
        self.assertEqual(la["opponent"]["extra_frames"], lb["yours"]["extra_frames"])
        self.assertEqual(la["yours"]["pc_fps"], 60.1)
        self.assertIn("should mean about", la["text"])
        self.assertEqual(la["text"], lb["text"])
        self.assertTrue(la["can_leave"])
        row = self.s.call(lambda: self.s.srv.store.match_row(mid))
        self.assertEqual(json.loads(row["lag"])["assess"]["verdict"], "ok")      # kept with the match record

    def test_more_lag_than_the_ping_explains(self):
        a, b, ea, ra = self.played()
        a.report_lag(ra["match"], 3000, 3000 * 40.0, 60.0)
        b.report_lag(ra["match"], 3000, 3000 * 40.0, 60.0)
        la, lb = expect(a, "lag_check"), expect(b, "lag_check")
        self.assertEqual((la["verdict"], la["cause"]), ("more_lag", "network"))
        self.assertGreater(la["observed_frames"], la["expected_frames"] + 2)
        self.assertIn("more than the ping explains", lb["text"])

    def test_a_slow_pc_is_blamed_on_the_right_side(self):
        a, b, ea, ra = self.played()
        a.report_lag(ra["match"], 3000, 3000 * 0.5, 41.0)           # Alice's PC could not keep up ...
        b.report_lag(ra["match"], 3000, 3000 * 30.0, 60.0)          # ... so Bob's game kept waiting for it
        la, lb = expect(a, "lag_check"), expect(b, "lag_check")
        self.assertEqual((la["verdict"], la["cause"], lb["cause"]), ("more_lag", "your_pc", "opponent_pc"))
        self.assertIn("Your PC was the slow one", la["text"])
        self.assertIn("Your opponent's PC was the slow one", lb["text"])

    def test_one_report_is_enough_after_a_short_wait(self):
        a, b, ea, ra = self.played()
        b.report_lag(ra["match"], 3000, 3000 * 0.2, 60.0)
        la, lb = expect(a, "lag_check", 4.0), expect(b, "lag_check", 4.0)
        self.assertEqual(la["verdict"], "ok")
        self.assertIsNone(la["yours"]["extra_frames"])              # Alice's game said nothing
        self.assertIsNotNone(la["opponent"]["extra_frames"])

    def test_refused_reports(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        with self.assertRaises(LobbyError) as e:                     # the match is still running
            a._call({"t": "lag", "match": ea["match"], "frames": 3000, "waited_ms": 5})
        self.assertEqual(e.exception.code, proto.E_NOT_FOUND)
        ra, rb = self.finish(a, b, ea)
        with self.assertRaises(LobbyError) as e:
            a._call({"t": "lag", "match": ra["match"], "frames": 20, "waited_ms": 5})
        self.assertEqual(e.exception.code, proto.E_BAD_REQUEST)
        c = self.acc("Cleo")
        with self.assertRaises(LobbyError) as e:                     # not a player of that match
            c._call({"t": "lag", "match": ra["match"], "frames": 3000, "waited_ms": 5})
        self.assertEqual(e.exception.code, proto.E_NOT_FOUND)

    def test_nothing_ends_by_itself_and_leaving_costs_nothing(self):
        a, b, ea, ra = self.played()
        mid = ra["match"]
        a.report_lag(mid, 3000, 3000 * 40.0, 60.0)
        b.report_lag(mid, 3000, 3000 * 40.0, 60.0)
        self.assertEqual(expect(a, "lag_check")["verdict"], "more_lag")
        expect(b, "lag_check")
        self.assertIsNone(a.next_event(1.5, ("set_end",)))          # a bad check ends nothing
        self.assertEqual(self.player("Alice").set.state, "active")
        ratings = (self.account("Alice")["rating"], self.account("Bob")["rating"])
        aid = self.account("Alice")["id"]
        a.leave_set("lag")
        self.assertEqual(expect(b, "rematch")["state"], "declined")  # Bob's rematch bar goes away
        sa, sb = expect(a, "set_end"), expect(b, "set_end")
        self.assertEqual((sa["reason"], sa["by"], sb["reason"], sb["by"]), ("lag", "you", "lag", "opponent"))
        self.assertEqual((self.account("Alice")["rating"], self.account("Bob")["rating"]), ratings)   # no rating change
        self.assertEqual(self.s.call(lambda: self.s.srv.store.strikes(aid, 0)), 0)                    # no strike
        self.assertEqual(self.player("Alice").status, "idle")
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["lag_leaves"]), 1)
        with self.assertRaises(LobbyError):
            b.rematch(mid, True)                                     # the set is over

    def test_long_waits_are_flagged_and_leaving_costs_nothing(self):
        a, b, ea, ra = self.played()
        mid = ra["match"]
        a.report_lag(mid, 10192, 92000.0, 60.2, 39.8)              # production numbers (1.1.4 said "ok")
        b.report_lag(mid, 10192, 94800.0, 60.2, 39.8)
        la, lb = expect(a, "lag_check"), expect(b, "lag_check")
        self.assertEqual((la["verdict"], la["cause"], la["waited_s"]), ("slow", "network", 94.8))
        self.assertEqual((la["yours"]["waited_s"], la["opponent"]["waited_s"]), (92.0, 94.8))
        self.assertEqual((lb["yours"]["waited_s"], lb["opponent"]["waited_s"]), (94.8, 92.0))
        self.assertTrue(la["text"].startswith("This match lagged: the games waited 95 s for each other's inputs."))
        self.assertEqual(lagmod.describe_event(la), la["text"])
        row = self.s.call(lambda: self.s.srv.store.match_row(mid))
        stored = json.loads(row["lag"])["assess"]
        self.assertEqual((stored["verdict"], stored["cause"]), ("slow", "network"))
        p1p2 = "92 s / 95 s" if ea["slot"] == 0 else "95 s / 92 s"    # the log lists P1 first; a may be either side
        self.assertTrue(stored["why"].startswith("network: the games waited " + p1p2), stored["why"])
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["lag_slow"]), 1)
        a.leave_set("lag")                                            # a ranked set is left for free after it
        sa = expect(a, "set_end")
        self.assertEqual((sa["reason"], sa["by"]), ("lag", "you"))

    def test_a_114_launcher_gets_more_lag_for_long_waits(self):
        a, b, ea, ra = self.played()
        self.s.call(lambda: setattr(self.s.srv.by_name["bob"].conn, "caps",
                                    self.s.srv.by_name["bob"].conn.caps - {"lag_wait"}))
        a.report_lag(ra["match"], 10192, 92000.0, 60.2, 39.8)
        b.report_lag(ra["match"], 10192, 94800.0, 60.2, 39.8)
        la, lb = expect(a, "lag_check"), expect(b, "lag_check")
        self.assertEqual((la["verdict"], lb["verdict"]), ("slow", "more_lag"))     # its "Leave: too laggy" button
        self.assertIn("connection stalled", lagmod.describe_event(lb))

    def test_a_bad_check_does_not_stop_a_rematch(self):
        a, b, ea, ra = self.played()
        a.report_lag(ra["match"], 3000, 3000 * 40.0, 60.0)
        b.report_lag(ra["match"], 3000, 3000 * 40.0, 60.0)
        expect(a, "lag_check")
        a.rematch(ra["match"], True, keep=True)
        b.rematch(ra["match"], True, keep=True)
        self.assertTrue(expect(a, "match_start")["continue"])

    def test_leave_set_rules(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        with self.assertRaises(LobbyError) as e:
            a.leave_set()
        self.assertEqual(e.exception.code, proto.E_STATE)
        ea, eb = self.ranked(a, b)
        with self.assertRaises(LobbyError) as e:                     # a running match is left with leave_match
            a.leave_set()
        self.assertEqual(e.exception.code, proto.E_BUSY)


class DriverLagTest(unittest.TestCase):
    LINE = "[netplay] speed: {fps} fps, this PC {pc} fps without the waits for the peer (waited {w} s of {t} s)"

    def log(self, *rows):
        g = GameLog(None)
        for fps, pc, w, t in rows:
            g.line(self.LINE.format(fps=fps, pc=pc, w=w, t=t))
        return g

    def test_numbers_from_the_netplay_speed_lines(self):
        g = self.log((58.9, 61.2, 0.4, 10.2), (55.0, 60.0, 0.8, 10.9))
        st = g.lag_stats()
        self.assertAlmostEqual(st["frames"], 600 + 600, delta=3)
        self.assertAlmostEqual(st["waited_ms"], 1200.0, delta=0.5)
        self.assertEqual(st["pc_fps"], 61.2)
        self.assertEqual(g.local_fps, 60.0)                          # the old speed reading still works
        mark = g.mark()
        g.line(self.LINE.format(fps=50.0, pc=52.0, w=2.0, t=12.0))
        self.assertEqual(g.lag_stats(mark[3])["frames"], 600)        # only the lines after the mark
        self.assertIsNone(self.log().lag_stats())                    # no line: nothing to say
        self.assertIsNone(self.log((60.0, 60.0, 0.0, 1.0)).lag_stats())   # 60 frames: too few

    def test_driver_reports_when_the_lobby_settled_the_match(self):
        calls = []

        class Client:
            def report_lag(self, *a):
                calls.append(a)

        d = MatchDriver(Client(), lambda env: None, tempfile.mkdtemp(), mode="process")
        d.glog = self.log((59.0, 61.0, 1.0, 10.0), (58.0, 60.0, 3.0, 10.0))
        d.mark = (0, 0, 0, 1)                                        # the match started after the first line
        d.ticket = types.SimpleNamespace(match_id="m1")
        d.reported = True
        d._finished({"t": "match_result", "match": "m1"})
        self.assertEqual(len(calls), 1)
        mid, frames, waited_ms, pc_fps, fps = calls[0]
        self.assertEqual((mid, frames, pc_fps), ("m1", 580, 60.0))
        self.assertAlmostEqual(waited_ms, 3000.0, delta=0.5)
        d._finished({"t": "match_result", "match": "m2"})            # a match this driver was not playing
        self.assertEqual(len(calls), 1)


# ============================================================================== 7. server notices
class NoticeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t5lobby.db")
        self.s = ServerThread(db=self.db, admin_poll=0.2).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name):
        c = client(self.s, name)
        self.clients.append(c)
        return c

    def admin(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                rc = admin.main(["--db", self.db] + list(args))
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else (print(e.code) or 1)
        return rc, out.getvalue()

    def test_admin_notice_reaches_everyone_online_and_late_arrivals(self):
        a, b = self.c("Alice"), self.c("Bob")
        rc, out = self.admin("notice", "server", "restart", "in", "20", "min", "--minutes", "30")
        self.assertEqual(rc, 0)
        self.assertIn("server restart in 20 min", out)
        ea, eb = expect(a, "server_notice", 5), expect(b, "server_notice", 5)
        self.assertEqual(ea["text"], "server restart in 20 min")
        self.assertFalse(ea["cleared"])
        self.assertGreater(ea["expires"], time.time() + 25 * 60)
        self.assertEqual(a.active_notices(), ["server restart in 20 min"])
        late = self.c("Carol")                                       # logs in while it is showing
        self.assertEqual(expect(late, "server_notice", 5)["text"], "server restart in 20 min")
        rc, out = self.admin("notices")
        self.assertIn("showing", out)
        self.admin("notice", "--clear")
        self.assertTrue(expect(a, "server_notice", 5)["cleared"])
        self.assertEqual(a.active_notices(), [])
        self.assertIsNone(self.c("Dave").next_event(1.0, ("server_notice",)))      # nothing left to show

    def test_a_notice_ends_by_itself(self):
        a = self.c("Alice")
        self.admin("notice", "short one", "--minutes", "0.02")      # 1.2 s
        self.assertFalse(expect(a, "server_notice", 5)["cleared"])
        self.assertTrue(expect(a, "server_notice", 5)["cleared"])
        self.assertEqual(a.active_notices(), [])

    def test_older_clients_get_it_as_a_plain_notice(self):
        a = self.c("Alice")
        self.s.call(lambda: setattr(self.s.srv.by_name["alice"].conn, "caps", frozenset()))   # announced no "notices"
        self.admin("notice", "maintenance at noon")
        ev = expect(a, "notice", 5)
        self.assertEqual((ev["code"], ev["msg"]), ("server_notice", "maintenance at noon"))

    def test_admin_rules(self):
        rc, out = self.admin("notice")
        self.assertNotEqual(rc, 0)
        self.assertIn("what should the notice say", out)
        rc, out = self.admin("notice", "x" * 201)
        self.assertNotEqual(rc, 0)
        self.assertIn("too long", out)
        rc, out = self.admin("notices")
        self.assertIn("(no notices yet)", out)

    def test_it_is_counted_and_survives_in_the_status(self):
        a = self.c("Alice")
        self.admin("notice", "hello")
        expect(a, "server_notice", 5)
        st = self.s.call(lambda: self.s.srv.status())
        self.assertEqual(st["notices"], 1)
        self.assertEqual(st["counters"]["notices_sent"], 1)


# ============================================================================== 8. no addresses in messages
class ScrubTest(unittest.TestCase):
    def test_addresses_go_names_and_numbers_stay(self):
        s = proto.scrub_addresses
        self.assertEqual(s("cannot reach 203.0.113.7:7781 now"), "cannot reach (address hidden) now")
        self.assertEqual(s("Connect call failed ('127.0.0.1', 7781)"), "Connect call failed ('(address hidden)', 7781)")
        self.assertEqual(s("peer 2001:db8::1 gone, [2001:db8::2]:7781 too, fe80::1%eth0"),
                         "peer (address hidden) gone, (address hidden) too, (address hidden)")
        self.assertEqual(s("::ffff:192.0.2.1"), "::ffff:(address hidden)")
        for same in ("lobby.example.org:7781", "python 3.12.10 at 10:30:15", "frame 1,234 of 7,200",
                     "ping 85 ms, 3 frames", "version 1.2.3", ""):
            self.assertEqual(s(same), same)
        self.assertIsNone(s(None))

    def test_the_server_scrubs_notices_and_errors_before_sending(self):
        s = ServerThread().start()
        try:
            sock = socket.create_connection(("127.0.0.1", s.srv.port), timeout=5)
            f = sock.makefile("rwb")
            f.write(proto.encode({"t": "hello", "proto": proto.PROTO_VERSION, "build": BUILD.as_wire()}))
            f.write(proto.encode({"t": "login", "mode": "guest", "name": "Raw"}))
            f.flush()
            deadline = time.time() + 5
            while time.time() < deadline and "raw" not in s.srv.by_name:
                f.readline()
            msgs = ("peer 198.51.100.7:40000 and 2001:db8::7 unreachable", "cannot connect to 203.0.113.9")
            for text in msgs:
                s.call(lambda t=text: s.srv.by_name["raw"].send({"t": "notice", "code": "x", "msg": t}))
            f.write(proto.encode({"t": "203.0.113.9"}))             # "unknown message '203.0.113.9'": echoes what was sent
            f.flush()
            got = []
            deadline = time.time() + 5
            while len(got) < 3 and time.time() < deadline:
                m = json.loads(f.readline())
                if m["t"] in ("notice", "error"):
                    got.append(m)
            self.assertEqual(len(got), 3)
            for m in got:
                self.assertFalse(IPV4.search(m["msg"]) or "2001:db8" in m["msg"], m["msg"])
            self.assertIn("(address hidden)", got[0]["msg"])
            self.assertEqual(got[2]["t"], "error")                      # the error reply echoed the odd message type
            sock.close()
        finally:
            s.stop()

    def test_the_client_scrubs_what_it_shows(self):
        c = LobbyClient("127.0.0.1:1", BUILD)
        c._emit({"t": "notice", "code": "nat_error", "msg": "OSError: sendto ('203.0.113.7', 5) failed"})
        c._emit({"t": "nat_status", "match": "m", "phase": "punch", "text": "no answer from 198.51.100.4:61000"})
        c._emit({"t": "disconnected", "reason": "[Errno 10054] reset by 2001:db8::5"})
        c._emit({"t": "chat", "from": {}, "text": "my ip is 192.0.2.5"})       # chat is what players say: left alone
        evs = [c.events.get_nowait() for _ in range(4)]
        for ev in evs[:3]:
            self.assertNotRegex(json.dumps(ev), r"\d+\.\d+\.\d+\.\d+|2001:db8")
        self.assertIn("(address hidden)", evs[0]["msg"])
        self.assertIn("192.0.2.5", evs[3]["text"])

    def test_a_failed_connection_names_no_address(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()                                                # nothing listens there now
        c = LobbyClient(f"localhost:{port}", BUILD)
        try:
            with self.assertRaises(LobbyError) as e:
                c.connect(timeout=3)
        finally:
            c.close()
        self.assertEqual(e.exception.code, "connect_failed")
        text = str(e.exception)
        self.assertNotRegex(text, r"\d+\.\d+\.\d+\.\d+")
        self.assertNotIn("::1", text)
        self.assertIn(f"localhost:{port}", text)                     # what the player typed is still there

    def test_the_driver_scrubs_its_status_lines(self):
        d = MatchDriver(types.SimpleNamespace(), lambda env: None, tempfile.mkdtemp(), mode="process")
        d.status("could not reach 203.0.113.7:61000")
        from t5lobby.match_driver import _call_now

        def boom():
            raise OSError("connect to ('198.51.100.9', 61000) failed")
        _call_now(d.notes, boom)
        texts = [d.notes.get_nowait()["text"] for _ in range(2)]
        for t in texts:
            self.assertNotRegex(t, r"\d+\.\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
