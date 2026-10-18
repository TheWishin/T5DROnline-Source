"""Ranked sets (docs/RANKED.md "Ranked sets"): a ranked set between two clients that know sets is best of 3
(first to T5L_RANKED_SET_WINS = 2 games); its games are not rated one by one, the next game starts by itself
after a countdown, and the rating changes once, at the end of the set.

1. 2-0 and 2-1 sets: one Glicko-2 update from the set's result, history and profile with the games
2. quitting in game 1, 2 or 3; leaving between two games; an early quit; a lobby drop between games
3. a desync is played again (at most 2 times per set), then the set is void
4. the pair cap and the cooldown count sets; queueing in the middle of a set is refused
5. an older client (no "sets"): every ranked game is rated on its own, with the rematch vote, as before
6. a server restart in the middle of a set: the set is void (nothing to undo: no game changed a rating)
7. ranked rooms; the launcher's glue (match driver + stub games) through a whole set
8. the Online tab: the set score, the countdown to the next game, Leave set, the set's result
9. the set's texts and the set score in the fight HUD
"""
import os
import sys
import tempfile
import time
import unittest

import util
from util import ServerThread, client, expect
from t5lobby import proto, rating as glicko, sets as setsmod
from t5lobby.match_driver import MatchDriver, hud_values
from t5lobby.proto import LobbyError
from t5lobby.rating import Rating

STUB = os.path.join(os.path.dirname(util.HERE), "tools", "stub_game.py")
SETS = {"set_next_seconds": 0.3}


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        cfg = dict(SETS)
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def acc(self, name, sets=True, **kw):
        kw.setdefault("auto_ready", True)
        c = client(self.s, name, password="pw-" + name, register=True, sets=sets, **kw)
        self.clients.append(c)
        return c

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))

    def player(self, name):
        return self.s.call(lambda: self.s.srv.by_name.get(name.lower()))

    def start(self, a, b, ca="jin", cb="paul"):
        a.ranked_match(ca)
        b.ranked_match(cb)
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)

    @staticmethod
    def score(w):
        return [3, 1] if w == 0 else [1, 3]

    def game(self, a, b, ev, winner, **kw):
        """Both report `winner` (0 = P1, 1 = P2) -> both match_results. (With a desync count the first report
        settles the game at once: the second one may come too late.)"""
        for c in (a, b):
            try:
                c.report_result(winner, self.score(winner) if winner is not None else None, match_id=ev["match"],
                                source="game", **kw)
            except LobbyError:
                if not kw.get("desync"):
                    raise
        return expect(a, "match_result"), expect(b, "match_result")

    def ids(self, *names):
        return [self.account(n)["id"] for n in names]

    def pair_ranked(self, x, y):
        ia, ib = self.ids(x, y)
        return self.s.call(lambda: self.s.srv.store.pair_ranked(ia, ib, 0))

    def next_game(self, a, b, keep=True):
        """Between two games: both launchers say whether their game still runs; the next game starts."""
        for c in (a, b):
            c.set_next(None, keep=keep)
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)


# ============================================================================== 1. 2-0 and 2-1
class SetResultTest(Base):
    def test_two_nil_is_rated_once(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        s = ea["set"]
        self.assertTrue(s["rated"])
        self.assertEqual((s["wins_needed"], s["best_of"], s["number"], s["wins"]), (2, 3, 1, [0, 0]))
        w = ea["slot"]                                       # Alice wins both games
        ra, rb = self.game(a, b, ea, w)
        self.assertEqual(ra["status"], "confirmed")
        self.assertIsNone(ra["rating"])                      # no rating change after a game of the set
        self.assertEqual(ra["rematch_window"], 0)            # no rematch vote: the set goes on by itself
        self.assertEqual(ra["set"]["wins"][w], 1)
        self.assertEqual(ra["set"]["number"], 2)
        self.assertIn("next", ra["set"])
        self.assertEqual(self.account("Alice")["rating"], 1500)
        self.assertEqual(self.account("Alice")["ranked_games"], 0)
        with self.assertRaises(LobbyError):
            a.rematch(ra["match"], True, keep=True)          # nothing to vote on
        ea2, eb2 = self.next_game(a, b)
        self.assertTrue(ea2["continue"])                     # inside the running games
        self.assertEqual((ea2["set"]["id"], ea2["set"]["number"]), (s["id"], 2))
        self.assertEqual(ea2["slot"], ea["slot"])            # the same sides
        self.assertEqual(ea2["fight"]["p1"], ea["fight"]["p1"])        # the same (locked) characters
        ra2, rb2 = self.game(a, b, ea2, w)
        self.assertIsNotNone(ra2["rating"])                  # the deciding game carries the set's rating change
        self.assertEqual(ra2["set"]["state"], "ended")
        self.assertEqual(ra2["set"]["result"]["winner"], w)
        self.assertGreater(ra2["rematch_window"], 0)         # after the set: a rematch is a new set
        se = expect(a, "set_end")
        self.assertEqual((se["reason"], se["status"], se["result"], se["wins"]), ("decided", "confirmed", "win", [2, 0]))
        sb = expect(b, "set_end")
        self.assertEqual((sb["result"], sb["wins"]), ("loss", [0, 2]))
        # ONE update from the set's result: what one won game between two new players gives
        want, _ = glicko.match(Rating(), Rating(), 1.0)
        self.assertAlmostEqual(self.account("Alice")["rating"], want.r, places=3)
        self.assertAlmostEqual(se["rating"]["after"]["r"], round(want.r, 1), places=1)
        acc = self.account("Alice")
        self.assertEqual((acc["ranked_games"], acc["wins"], acc["losses"], acc["games"]), (1, 1, 0, 1))
        self.assertEqual(self.account("Bob")["losses"], 1)
        self.assertEqual(self.player("Alice").record[:2], [1, 0])
        # history: both games with the set; the deciding one carries the set's change
        hist = a.history("Alice")
        self.assertEqual(len(hist), 2)
        self.assertEqual([h["set"]["game"] for h in hist], [2, 1])
        self.assertEqual({h["set"]["result"] for h in hist}, {"win"})
        self.assertEqual(hist[0]["set"]["score"], [2, 0])
        self.assertGreater(hist[0]["delta"], 0)
        self.assertIsNone(hist[1]["delta"])
        prof = b.profile("Bob")
        self.assertEqual(len(prof["sets"]), 1)
        st = prof["sets"][0]
        self.assertEqual((st["result"], st["score"], st["opponent"], len(st["games"])), ("loss", [0, 2], "Alice", 2))
        self.assertEqual([g["result"] for g in st["games"]], ["loss", "loss"])
        self.assertEqual(st["games"][0]["you_char"], "paul")
        self.assertLess(st["delta"], 0)
        self.assertEqual(self.pair_ranked("Alice", "Bob"), 1)
        # the characters unlock with the end of the set
        a.set_char("law")

    def test_two_one(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        w = ea["slot"]
        numbers = []
        for i, winner in enumerate((w, 1 - w, w)):
            if i:
                ea, _ = self.next_game(a, b)
            numbers.append(ea["set"]["number"])
            ra, _ = self.game(a, b, ea, winner)
        self.assertEqual(numbers, [1, 2, 3])
        self.assertEqual(ra["set"]["state"], "ended")
        se = expect(a, "set_end")
        self.assertEqual((se["result"], se["wins"], se["games"]), ("win", [2, 1], 3))
        acc = self.account("Alice")
        self.assertEqual((acc["ranked_games"], acc["wins"], acc["losses"]), (1, 1, 0))
        row = self.s.call(lambda: self.s.srv.store.set_row(se["set"]))
        self.assertEqual((row["status"], len(row["games"])), ("confirmed", 3))
        self.assertEqual(row["score"][w], 2)

    def test_next_game_over_a_new_connection(self):
        """A launcher whose game is gone (or does not say) gets the next game over a new connection."""
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, 0)
        a.set_next(None, keep=True)
        b.set_next(None, keep=False)
        s = expect(a, "match_start", 20.0)
        self.assertFalse(s["continue"])
        self.assertIsNotNone(s["ticket"])
        self.assertEqual(s["set"]["number"], 2)

    def test_without_set_next_the_next_game_starts_anyway(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, 1)
        s = expect(a, "match_start", 20.0)                  # nobody answered: the countdown starts it all the same
        self.assertEqual((s["set"]["number"], s["continue"]), (2, False))


# ============================================================================== 2. leaving
class SetLeaveTest(Base):
    def test_quit_in_game_1(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        b.leave_match(eb["match"])                            # Bob closes his game in game 1
        ra = expect(a, "match_result")
        self.assertEqual((ra["status"], ra["reason"], ra["winner"]), ("forfeit", "quit", ea["slot"]))
        self.assertGreater(ra["rating"]["delta"], 0)          # the set is lost: rated at once
        se = expect(b, "set_end")
        self.assertEqual((se["status"], se["result"], se["blame"]), ("forfeit", "loss", "you"))
        self.assertEqual(self.account("Bob")["losses"], 1)

    def quit_in(self, n):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        w = ea["slot"]
        winners = [w, 1 - w][:n - 1]
        for i, winner in enumerate(winners):
            self.game(a, b, ea, winner)
            ea, eb = self.next_game(a, b)
        self.assertEqual(ea["set"]["number"], n)
        a.leave_match(ea["match"])                            # Alice quits game n
        rb = expect(b, "match_result")
        self.assertEqual((rb["status"], rb["winner"]), ("forfeit", eb["slot"]))
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["result"]), ("forfeit", "loss"))
        self.assertLess(se["rating"]["delta"], 0)
        acc = self.account("Alice")
        self.assertEqual((acc["ranked_games"], acc["losses"]), (1, 1))

    def test_quit_in_game_2(self):
        self.quit_in(2)

    def test_quit_in_game_3(self):
        self.quit_in(3)

    def test_leaving_between_games_loses_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        self.game(a, b, ea, ea["slot"])                       # Alice leads 1-0 ...
        a.leave_set()                                         # ... and leaves: still a loss
        se = expect(a, "set_end")
        self.assertEqual((se["reason"], se["status"], se["result"], se["wins"]), ("left", "forfeit", "loss", [1, 0]))
        sb = expect(b, "set_end")
        self.assertEqual((sb["by"], sb["result"]), ("opponent", "win"))
        self.assertGreater(sb["rating"]["delta"], 0)

    def test_queueing_or_a_room_in_the_middle_of_a_set_is_refused(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, 0)
        for fn in (lambda: a.ranked_match("jin"), lambda: a.quick_match(), lambda: a.create_room("x")):
            with self.assertRaises(LobbyError) as e:
                fn()
            self.assertEqual(e.exception.code, proto.E_BUSY)
        with self.assertRaises(LobbyError):
            a.set_char("law")                                 # still locked
        expect(a, "match_start", 20.0)                        # and the set goes on

    def test_logging_out_between_games_loses_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        a.logout()
        self.clients.remove(a)
        sb = expect(b, "set_end")
        self.assertEqual((sb["reason"], sb["result"]), ("left", "win"))

    def test_leaving_before_any_game_counted_is_no_loss(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"], desync=5)             # a desync: no game has counted
        b.leave_set()
        sb = expect(b, "set_end")
        self.assertEqual((sb["status"], sb["result"], sb["rating"]), ("void", None, None))
        self.assertEqual(self.account("Bob")["rating"], 1500)

    def test_lobby_drop_between_games(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        # Bob's connection breaks right after the game; his launcher reconnects: the set goes on
        b._loop.call_soon_threadsafe(b._writer.transport.abort)
        expect(b, "reconnecting")
        expect(b, "reconnected", timeout=15)
        s = expect(a, "match_start", 20.0)
        self.assertEqual(s["set"]["number"], 2)

    def test_lobby_drop_between_games_for_good_loses_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        b.reconnect_window = 0
        b._loop.call_soon_threadsafe(b._writer.transport.abort)
        n = expect(a, "notice")
        self.assertEqual(n["code"], "opponent_dropped")
        se = expect(a, "set_end", 10)                         # grace (2 s in tests) runs out
        self.assertEqual((se["reason"], se["status"], se["result"]), ("disconnect", "forfeit", "win"))


class SetEarlyQuitTest(Base):
    server_cfg = {"min_match_seconds": 1.0}

    def test_early_quit_in_game_1_is_void_with_a_strike(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        b.leave_match(eb["match"])                            # at once: within the minimum match length
        ra = expect(a, "match_result")
        self.assertEqual((ra["status"], ra["reason"], ra["blame"]), ("void", "early_quit", "opponent"))
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["rating"]), ("void", None))
        self.assertEqual(self.account("Alice")["rating"], 1500)
        bob = self.account("Bob")
        self.assertEqual(self.s.call(lambda: self.s.srv.store.strikes(bob["id"], 0)), 1)

    def test_early_quit_in_a_later_game_is_leaving_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        time.sleep(1.1)
        self.game(a, b, ea, eb["slot"])                       # Bob leads 1-0 ...
        ea, eb = self.next_game(a, b)
        a.leave_match(ea["match"])                            # ... and Alice quits game 2 at once
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["result"], se["outcome_reason"]), ("forfeit", "loss", "early_quit"))


# ============================================================================== 3. desync: played again
class SetReplayTest(Base):
    def test_a_desynced_game_is_played_again(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        ra, _ = self.game(a, b, ea, ea["slot"], desync=12)
        self.assertEqual((ra["status"], ra["reason"]), ("void", "desync"))
        self.assertEqual((ra["set"]["number"], ra["set"]["replays"], ra["set"]["wins"]), (1, 1, [0, 0]))
        self.assertTrue(ra["set"]["next"]["replay"])
        ea2, _ = self.next_game(a, b, keep=True)
        self.assertFalse(ea2["continue"])                     # after a desync: a new connection (the games reset)
        self.assertEqual(ea2["set"]["number"], 1)
        self.game(a, b, ea2, ea2["slot"])
        ea3, _ = self.next_game(a, b)
        self.assertTrue(ea3["continue"])
        self.game(a, b, ea3, ea3["slot"])
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["result"], se["games"]), ("confirmed", "win", 3))
        self.assertEqual(self.account("Alice")["ranked_games"], 1)

    def test_void_after_two_replays(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])                       # 1-0, then three desyncs
        for i in range(3):
            ea, _ = self.next_game(a, b)
            self.assertEqual(ea["set"]["number"], 2)
            ra, _ = self.game(a, b, ea, ea["slot"], desync=3)
        self.assertEqual(ra["set"]["state"], "ended")
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["outcome_reason"], se["rating"]), ("void", "desync", None))
        self.assertEqual(self.account("Alice")["rating"], 1500)
        self.assertEqual(self.account("Alice")["ranked_games"], 0)

    def test_a_crash_voids_the_set_and_blames_the_crasher(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        ea, eb = self.next_game(a, b)
        b.report_result(None, None, match_id=eb["match"], source="crash")
        a.report_result(None, None, match_id=ea["match"], source="disconnect", reason="peer_timeout")
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["outcome_reason"], se["blame"]), ("void", "crash", "opponent"))
        self.assertEqual(self.account("Alice")["rating"], 1500)


# ============================================================================== 4. pair cap, cooldown
class SetPairCapTest(Base):
    server_cfg = {"pair_cap": 1}

    def test_the_cap_counts_sets(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, 0)
        a.set_next(None, keep=True)
        b.set_next(None, keep=True)
        mf = expect(a, "match_found")
        self.assertTrue(mf["ranked"])                         # game 2 of the set: still ranked
        ea = expect(a, "match_start")
        self.game(a, b, ea, 0)
        expect(a, "set_end")
        a.ranked_match()                                      # one set = the cap of 1
        b.ranked_match()
        mf = expect(a, "match_found", 20.0)
        self.assertFalse(mf["ranked"])
        self.assertEqual(expect(a, "notice")["code"], "pair_cap")
        self.assertFalse(mf["set"].get("rated", False))


class SetCooldownTest(Base):
    server_cfg = {"pair_cooldown": 30.0}

    def test_the_same_two_wait_after_a_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, 0)
        ea, _ = self.next_game(a, b)                          # (the cooldown does not hold the set's own games)
        self.game(a, b, ea, 0)
        expect(a, "set_end")
        a.ranked_match()
        b.ranked_match()
        self.assertIsNone(a.next_event(2.0, ("match_found",)))


# ============================================================================== 5. older clients
class SetFallbackTest(Base):
    def test_an_older_client_gets_every_game_rated(self):
        a, b = self.acc("Alice"), self.acc("Bob", sets=False)        # Bob's launcher predates sets
        ea, _ = self.start(a, b)
        self.assertFalse(ea["set"].get("rated", False))
        ra, rb = self.game(a, b, ea, ea["slot"])
        self.assertIsNotNone(ra["rating"])                    # rated at once, as before
        self.assertGreater(ra["rematch_window"], 0)           # with the rematch vote
        self.assertNotIn("next", ra["set"])
        self.assertEqual(self.account("Alice")["ranked_games"], 1)
        a.rematch(ra["match"], True, keep=True)
        b.rematch(rb["match"], True, keep=True)
        ea = expect(a, "match_start")
        ra, _ = self.game(a, b, ea, ea["slot"])
        self.assertIsNotNone(ra["rating"])
        self.assertEqual(self.account("Alice")["ranked_games"], 2)
        self.assertEqual(self.pair_ranked("Alice", "Bob"), 2)

    def test_both_old_clients(self):
        a, b = self.acc("Alice", sets=False), self.acc("Bob", sets=False)
        self.assertEqual(a.welcome["set_wins"], 1)
        ea, _ = self.start(a, b)
        ra, _ = self.game(a, b, ea, 0)
        self.assertIsNotNone(ra["rating"])

    def test_the_server_can_switch_sets_off(self):
        self.s.call(lambda: setattr(self.s.srv.cfg, "ranked_set_wins", 1))
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        ra, _ = self.game(a, b, ea, 0)
        self.assertIsNotNone(ra["rating"])


# ============================================================================== 6. server restart
class SetRestartTest(unittest.TestCase):
    def test_a_set_open_at_a_restart_is_void(self):
        d = tempfile.mkdtemp(prefix="sets")
        db = os.path.join(d, "lobby.db")
        s = ServerThread(db=db, **SETS).start()
        a = client(s, "Alice", password="pw-alice", register=True, sets=True, auto_ready=True)
        b = client(s, "Bob", password="pw-bob", register=True, sets=True, auto_ready=True)
        try:
            a.ranked_match("jin")
            b.ranked_match("paul")
            ea = expect(a, "match_start", 20)
            for c in (a, b):
                c.report_result(0, [3, 0], match_id=ea["match"], source="game")
            ra = expect(a, "match_result")
            sid = ra["set"]["id"]
            ea2 = expect(a, "match_start", 20)                # game 2 is being played when the server stops
            m2 = ea2["match"]
        finally:
            a.reconnect_window = b.reconnect_window = 0
            s.stop()                                          # (before the launchers log out: that would be a quit)
            a.close()
            b.close()
        s = ServerThread(db=db, **SETS).start()               # the same database, a new server process
        try:
            row = s.call(lambda: s.srv.store.set_row(sid))
            self.assertEqual((row["status"], row["reason"], row["rating"]), ("void", "server_restart", None))
            self.assertEqual(row["score"], [1, 0])
            g2 = s.call(lambda: s.srv.store.match_row(m2))
            self.assertEqual((g2["status"], g2["reason"]), ("void", "server_restart"))
            g1 = s.call(lambda: s.srv.store.match_row(ea["match"]))
            self.assertEqual((g1["status"], g1["set_id"]), ("confirmed", sid))
            acc = s.call(lambda: dict(s.srv.store.account("Alice")))
            self.assertEqual((acc["rating"], acc["ranked_games"]), (1500, 0))   # nothing was rated, nothing undone
            bob = s.call(lambda: dict(s.srv.store.account("Bob")))
            self.assertEqual(s.call(lambda: s.srv.store.pair_ranked(acc["id"], bob["id"], 0)), 0)
            c = client(s, "Alice", password="pw-alice", sets=True)
            try:
                prof = c.profile("Alice")
                self.assertEqual((prof["sets"][0]["status"], prof["sets"][0]["reason"]), ("void", "server_restart"))
            finally:
                c.close()
        finally:
            s.stop()


# ============================================================================== 7. rooms, the match driver
class SetRoomTest(Base):
    def test_a_ranked_room_plays_sets(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        room = a.create_room("dojo", ranked=True)
        b.join_room(room["id"])
        f1 = expect(a, "match_found")
        self.assertTrue(f1["set"]["rated"])
        ea = expect(a, "match_start")
        expect(b, "match_start")
        self.game(a, b, ea, 0)
        with self.assertRaises(LobbyError):
            a.rematch()                                       # no "Ready again" inside a set
        ea, _ = self.next_game(a, b)
        self.assertEqual(ea["set"]["id"], f1["set"]["id"])
        self.game(a, b, ea, 0)
        expect(a, "set_end")
        a.rematch()                                           # the room's next game: a new set
        f2 = expect(a, "match_found")
        self.assertNotEqual(f2["set"]["id"], f1["set"]["id"])
        self.assertEqual(f2["set"]["wins"], [0, 0])

    def test_leaving_the_room_between_games_loses_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        room = a.create_room("dojo", ranked=True)
        b.join_room(room["id"])
        ea = expect(a, "match_start")
        expect(b, "match_start")
        self.game(a, b, ea, 0)
        b.leave_room()
        se = expect(b, "set_end")
        self.assertEqual((se["reason"], se["status"], se["result"]), ("left", "forfeit", "loss"))


class SetDriverTest(Base):
    """The launcher's glue with the stub game through a whole set: set_next with keep, the next games in
    the running game, one rating change."""

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

    def run_set(self, mode, stub):
        a, b = self.acc("Alice"), self.acc("Bob")
        drivers = []
        for c, n in ((a, "a"), (b, "b")):
            d = tempfile.mkdtemp(prefix=f"set{n}")
            drivers.append(MatchDriver(c, self.launch_stub(d, stub), d, mode=mode, ask_manual=False))
        a.ranked_match("lili")
        b.ranked_match("asuka")
        results, ends = {0: [], 1: []}, {0: [], 1: []}
        starts = []
        t_end = time.monotonic() + 60
        try:
            while time.monotonic() < t_end and not (ends[0] and ends[1]):
                for i, (c, drv) in enumerate(zip((a, b), drivers)):
                    while True:
                        ev = c.next_event(0)
                        if ev is None:
                            break
                        drv.on_event(ev)
                        if ev["t"] == "match_result":
                            results[i].append(ev)
                        elif ev["t"] == "set_end":
                            ends[i].append(ev)
                        elif ev["t"] == "match_start" and i == 0:
                            starts.append(ev)
                    drv.poll()
                time.sleep(0.05)
        finally:
            for drv in drivers:
                drv.close()
        return results, ends, starts, drivers

    def check(self, results, ends, starts):
        self.assertTrue(ends[0], "the set did not end")
        se = ends[0][0]
        self.assertEqual(se["status"], "confirmed", (se, [(r["status"], r["reason"]) for r in results[0]]))
        self.assertIn(se["wins"], ([2, 0], [2, 1], [0, 2], [1, 2]))
        self.assertEqual(len(results[0]), sum(se["wins"]))
        self.assertEqual([r["rating"] is not None for r in results[0]],
                         [False] * (len(results[0]) - 1) + [True])
        self.assertTrue(all(s["continue"] for s in starts[1:]), "the set's games went on in the running game")
        self.assertEqual(self.account("Alice")["ranked_games"], 1)

    def test_persistent_mode(self):
        results, ends, starts, drivers = self.run_set("persistent", {"T5_STUB_SECONDS": "1"})
        self.check(results, ends, starts)

    def test_process_mode(self):
        stub = {"T5_STUB_SECONDS": "1", "T5_STUB_MATCHES": "3", "T5_STUB_GAP": "1", "T5_STUB_LINGER": "10"}
        results, ends, starts, drivers = self.run_set("process", stub)
        self.check(results, ends, starts)
        self.assertEqual(len(drivers[0].history), len(results[0]))


class SetDriverSessionTest(unittest.TestCase):
    """A set's next game over a new connection in a persistent game (after a desync): the other game goes
    idle first, and this game logs the end of the LAST session ("peer lost (peer_quit)") only after the
    driver handed it the new match. That line is not the new match's (e2e run e3: the replay was reported as
    a disconnect, then voided as no_report with the innocent opponent blamed)."""

    class Client:
        def __init__(self):
            self.reports = []

        def game_started(self, mid):
            pass

        def report_result(self, winner, score=None, match_id=None, **kw):
            self.reports.append((match_id, kw.get("source"), kw.get("reason")))

    class Game:
        def __init__(self, env, log_path):
            self.env, self.log_path, self.proc = env, log_path, None

        def running(self):
            return True

        def stop(self):
            pass

    def test_the_last_sessions_end_is_not_the_new_match(self):
        from test_driver_persistent import start_event
        d = tempfile.mkdtemp(prefix="drvset")
        logp = os.path.join(d, "game.log")
        open(logp, "w").close()
        cl = self.Client()
        drv = MatchDriver(cl, lambda env: self.Game(env, logp), d, mode="persistent")

        def say(*lines):
            with open(logp, "a") as f:
                f.write("".join(ln + "\n" for ln in lines))

        def ack(seq):
            with open(os.path.join(d, "ctl", "state.json"), "w") as f:
                f.write('{"ctl": 1, "seq": %d, "state": "fight"}' % seq)

        drv.on_event(start_event("m1"))
        ack(1)
        say("[netplay] session 1 set up (handshake running)", "[netplay] connected (host, P1), delay 2")
        drv.poll()
        drv.on_event({"t": "match_result", "match": "m1", "status": "void", "reason": "desync", "set": {}})
        drv.on_event({"t": "match_found", "match": "m2", "keep": False})        # idle: a new connection
        drv.on_event(start_event("m2"))
        ack(3)
        say("[netplay] peer lost (peer_quit): the opponent left (its game was closed)")   # session 1's end
        t_end = time.monotonic() + 4.0
        while time.monotonic() < t_end:
            drv.poll()
            time.sleep(0.1)
        self.assertEqual(cl.reports, [])
        say("[netplay] session 2 set up (handshake running)", "[netplay] connected (host, P1), delay 2")
        for _ in range(10):
            drv.poll()
            time.sleep(0.05)
        self.assertEqual(cl.reports, [])
        say("[netplay] peer lost (peer_timeout): no packets")                   # now the new match's opponent is gone
        t_end = time.monotonic() + 5.0
        while time.monotonic() < t_end and not cl.reports:
            drv.poll()
            time.sleep(0.1)
        self.assertEqual(cl.reports, [("m2", "disconnect", "peer_timeout")])


# ============================================================================== 8. the Online tab
try:
    import tkinter as tk
    import test_tk_tab as tkt
except ImportError:      # pragma: no cover
    tk = None


@unittest.skipIf(tk is None, "no tkinter")
class TkSetTest(tkt.TkBase if tk is not None else unittest.TestCase):
    server_cfg = {"set_next_seconds": 1.5}
    login_account = tkt.TkT6Test.login_account if tk is not None else None

    def game(self, n, won=True):
        """Game n of the set in the tab's (fake) game: it closes, the tab answers, Rival reports the same."""
        tab = self.tab
        self.pump(lambda: len(self.app.games) == n)
        g = self.app.games[n - 1]
        slot = 0 if g.env["T5_NET_MODE"] == "host" else 1
        self.pump(lambda: f"game {n} of 3" in tab.set_var.get())
        g.done = True
        self.pump(lambda: self.bar_button("I won") is not None)
        self.bar_button("I won" if won else "I lost").invoke()
        self.other.report_result(slot if won else 1 - slot, None)

    def start(self):
        tab = self.tab
        self.login_account()
        self.other = client(self.s, "Rival", password="rival-pw1", register=True, auto_ready=True, sets=True)
        tab.actions["ranked"].invoke()
        self.other.ranked_match()
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.bar_button("Accept").invoke()

    def test_the_set_score_the_countdown_and_the_result(self):
        tab = self.tab
        self.start()
        self.game(1)
        self.pump(lambda: self.bar_button("Leave set (counts as a loss)") is not None)
        self.assertIn("Set 1-0 -- game 2 of 3 -- starts in", tab.bar_text.get())        # no rematch vote
        self.assertIsNone(self.bar_button("Rematch Rival"))
        self.assertEqual(str(tab.actions["ranked"].cget("state")), "disabled")       # the set goes on by itself
        self.assertEqual(str(tab.char_cb.cget("state")), "disabled")
        self.game(2)                                                                  # it started by itself
        self.pump(lambda: "You won the set 2-0" in tab.status_var.get())
        self.assertIn("rating", tab.status_var.get())
        self.assertEqual(tab.set_var.get(), "Set 2-0")
        self.pump(lambda: self.bar_button("Rematch Rival") is not None)              # a rematch = a new set
        self.assertEqual(str(tab.char_cb.cget("state")), "readonly")

    def test_leave_set_button(self):
        tab = self.tab
        self.start()
        self.game(1)
        self.pump(lambda: self.bar_button("Leave set (counts as a loss)") is not None)
        tab.ask_yes_no = lambda *a, **k: True
        self.bar_button("Leave set (counts as a loss)").invoke()
        self.pump(lambda: "You lost the set (you left it)" in tab.status_var.get())
        self.assertEqual(expect(self.other, "set_end")["result"], "win")


# ============================================================================== 9. texts, HUD
class SetTextTest(unittest.TestCase):
    def info(self, **kw):
        d = {"id": "s1", "rated": True, "wins_needed": 2, "best_of": 3, "wins": [1, 0], "number": 2, "replays": 0,
             "state": "active"}
        d.update(kw)
        return d

    def test_status_text(self):
        self.assertEqual(setsmod.status_text(self.info(), slot=0), "Set 1-0 -- game 2 of 3")
        self.assertEqual(setsmod.status_text(self.info(), slot=1), "Set 0-1 -- game 2 of 3")
        self.assertEqual(setsmod.status_text(self.info(next={"in": 4.2, "number": 2, "replay": False}), slot=0),
                         "Set 1-0 -- game 2 of 3 -- starts in 5 s")
        self.assertEqual(setsmod.status_text(self.info(wins=[0, 0], number=1, replays=1,
                                                       next={"in": 3, "number": 1, "replay": True}), slot=0),
                         "Set 0-0 -- game 1 of 3 again (no winner) -- starts in 3 s")
        self.assertEqual(setsmod.status_text({"id": "s", "game": 2, "locked": True, "ranked": True}, slot=0), "")
        self.assertEqual(setsmod.status_text(None, slot=0), "")

    def test_result_text(self):
        ev = {"rated": True, "status": "confirmed", "result": "win", "wins": [2, 1],
              "rating": {"after": {"r": 1662.3}, "delta": 162.3, "event": None,
                         "rank_after": {"rank": "Beginner", "placement": [1, 5]}}}
        self.assertEqual(setsmod.result_text(ev), "You won the set 2-1; rating 1662 (+162) -- placement 1/5")
        ev = {"rated": True, "status": "forfeit", "result": "loss", "wins": [1, 0], "by": "you", "reason": "left",
              "rating": {"after": {"r": 1480}, "delta": -20, "event": "demoted",
                         "rank_after": {"rank": "1st Kyu"}}}
        self.assertEqual(setsmod.result_text(ev),
                         "You lost the set (you left it); rating 1480 (-20) -- demoted to 1st Kyu")
        ev = {"rated": True, "status": "void", "result": None, "wins": [1, 1], "outcome_reason": "desync"}
        self.assertEqual(setsmod.result_text(ev), "The set does not count (the two games went out of sync); "
                                                  "no rating change")

    def test_german(self):
        from t5lobby import i18n
        i18n.set_language("de")
        i18n.clear_missing()
        try:
            self.assertEqual(setsmod.status_text(self.info(next={"in": 4.2, "number": 2, "replay": False}), slot=0),
                             "Set 1-0 -- Spiel 2 von 3 -- startet in 5 s")
            ev = {"rated": True, "status": "confirmed", "result": "win", "wins": [2, 1],
                  "rating": {"after": {"r": 1532}, "delta": 32, "event": None, "rank_after": {"rank": "1st Dan"}}}
            self.assertTrue(setsmod.result_text(ev).startswith("Du hast das Set 2-1 gewonnen"))
            void = {"rated": True, "status": "void", "result": None, "outcome_reason": "server_restart"}
            self.assertEqual(setsmod.result_text(void),
                             "Das Set zählt nicht (der Lobby-Server wurde neu gestartet); keine Wertungsänderung")
            self.assertEqual(setsmod.history_text({"game": 2, "result": "win", "score": [2, 1]}),
                             " -- Set-Spiel 2, Set gewonnen 2-1")
            self.assertEqual(i18n.missing(), [])
        finally:
            i18n.set_language("en")

    def test_hud_names_show_the_set_score(self):
        ev = {"players": [{"name": "Alice", "tier": 11}, {"name": "Bartholomew_Long", "tier": 3}],
              "set": self.info(wins=[1, 0], number=2)}
        self.assertEqual(hud_values(ev), (["Alice [1]", "Bartholomew_ [0]"], [11, 3]))
        ev["set"] = self.info(wins=[0, 0], number=1)
        self.assertEqual(hud_values(ev)[0], ["Alice", "Bartholomew_Long"])        # game 1: the plain names
        ev["set"] = {"id": "s", "game": 2, "locked": True, "ranked": True}         # not a rated set
        self.assertEqual(hud_values(ev)[0], ["Alice", "Bartholomew_Long"])


if __name__ == "__main__":
    unittest.main()
