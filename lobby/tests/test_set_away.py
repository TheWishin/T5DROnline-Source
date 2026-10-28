"""Leaving a ranked set, judged smartly (1.1.9, owner 2026-10-28; server/lobby.py "away from a ranked set",
docs/RANKED.md "Ranked sets"), the set's sides, and the leaderboard's ranked / casual split.

The case that started it: a player won game 1 of a ranked set 3-0, his launcher left the set between two games and
he logged in again 5 s later -- the set was scored as his forfeit (-40, demoted). Now:

1. the Leave set button counts at once: the leaver loses the set, the remaining player wins it and gets the points;
   the history says who left
2. the launcher closed (logout) or crashed (connection gone) between two games, back within the away window
   (T5L_SET_AWAY_SECONDS, 90 s; short here): the set goes on with the same score, sides and characters; the
   remaining player is told the time left; the returning player's rating is the one it had
3. the same in the next game before its fight began (the launcher's game is gone, the launcher closes): that game
   is played again over a new connection; repeated without end it is leaving the set
4. not back in time: the leaver loses the set, the remaining player wins it ("did not come back within N s"); a later
   login reads the new rating from the database
5. both gone: the set is void, no rating change
6. a ranked room's set waits for its player too
7. sides: the coin once per ranked set (also a launcher without sets: its ranked rematches inside the set keep the
   sides); quick matches keep their coin per match
8. leaderboard rows: ranked_wins, ranked_losses, casual_wins, casual_losses (the old fields stay)
"""
import time
import unittest
from unittest import mock

from util import ServerThread, client, expect
from t5lobby import sets as setsmod
from t5lobby.server import casual

AWAY = 6.0          # the away window in these tests (90 s on a real server)


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        cfg = {"set_next_seconds": 0.3, "set_away_seconds": AWAY}
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        from t5lobby.server.ratelimit import KeyedBuckets
        self.s.call(lambda: setattr(self.s.srv, "registrations", KeyedBuckets(rate=100.0, burst=100)))
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            try:
                c.close()
            except Exception:       # noqa: BLE001
                pass
        self.s.stop()

    def acc(self, name, sets=True, **kw):
        kw.setdefault("auto_ready", True)
        c = client(self.s, name, password="pw-" + name, register=True, sets=sets, **kw)
        self.clients.append(c)
        return c

    def again(self, name, sets=True):
        """The player starts the launcher again and logs in (password; a new connection, a new client)."""
        c = client(self.s, name, password="pw-" + name, sets=sets, auto_ready=True)
        self.clients.append(c)
        return c

    def crash(self, c):
        """The launcher dies: the connection breaks, nothing reconnects."""
        c.reconnect_window = 0
        c._loop.call_soon_threadsafe(c._writer.transport.abort)
        self.clients.remove(c)

    def close_launcher(self, c):
        """The launcher's window is closed: it logs out (client.close)."""
        c.close()
        self.clients.remove(c)

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))

    def player(self, name):
        return self.s.call(lambda: self.s.srv.by_name.get(name.lower()))

    def start(self, a, b, coin=0):
        with mock.patch.object(casual, "_side_coin", return_value=coin):
            a.ranked_match("jin")
            b.ranked_match("paul")
            return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)

    def game(self, a, b, ev, winner):
        for c in (a, b):
            c.report_result(winner, [3, 0] if winner == 0 else [0, 3], match_id=ev["match"], source="game")
        return expect(a, "match_result"), expect(b, "match_result")

    def next_game(self, a, b, keep=True):
        for c in (a, b):
            c.set_next(None, keep=keep)
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)

    @staticmethod
    def notice(c, code, timeout=10.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            ev = c.next_event(max(0.0, t_end - time.monotonic()), ("notice",))
            if ev is not None and ev.get("code") == code:
                return ev
        raise AssertionError(f"no notice {code!r}")

    def history_set(self, c, name):
        """The newest history row's set view, and its text as the profile's history shows it."""
        h = c.history(name)[0]
        return h["set"], setsmod.history_text(h["set"])


# ============================================================================== 1. Leave set: at once
class DeliberateLeaveTest(Base):
    def test_leave_set_loses_at_once_and_the_other_gets_the_points(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        self.game(a, b, ea, ea["slot"])                       # Alice 1-0 ...
        a.leave_set()                                         # ... and presses Leave set
        sa, sb = expect(a, "set_end"), expect(b, "set_end")
        self.assertEqual((sa["status"], sa["result"], sa["blame"]), ("forfeit", "loss", "you"))
        self.assertEqual((sb["status"], sb["result"], sb["blame"]), ("forfeit", "win", "opponent"))
        self.assertGreater(sb["rating"]["delta"], 0)          # the remaining player gets the points
        self.assertLess(sa["rating"]["delta"], 0)
        self.assertEqual(setsmod.result_text(sb).split(";")[0], "You won the set (your opponent left it)")
        self.assertGreater(self.account("Bob")["rating"], 1500)
        self.assertEqual((self.account("Bob")["wins"], self.account("Alice")["losses"]), (1, 1))
        # the history says who left, and how
        sv, text = self.history_set(b, "Bob")
        self.assertEqual((sv["reason"], sv["by"], sv["result"]), ("left", "opponent", "win"))
        self.assertIn("set won 0-1 (your opponent left the set)", text)
        sv, text = self.history_set(a, "Alice")
        self.assertIn("set lost 1-0 (you left the set)", text)


# ============================================================================== 2. away between two games, back
class AwayAndBackTest(Base):
    def _back(self, how):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b, coin=1)                     # (the coin: Alice P2)
        slot, sid = ea["slot"], ea["set"]["id"]
        self.game(a, b, ea, slot)                             # Alice wins game 1 3-0
        how(a)                                                # ... and her launcher closes / crashes
        n = self.notice(b, "opponent_dropped")
        self.assertEqual((n["set"], n["left"]), (sid, AWAY))
        self.assertIn("Alice is reconnecting -- 6 s left", n["msg"])
        time.sleep(1.0)
        self.assertEqual(self.s.call(lambda: self.s.srv.store.set_row(sid)["status"]), "playing")
        with mock.patch.object(casual, "_side_coin", return_value=0):     # (no coin inside the set)
            a2 = self.again("Alice")                          # back within the window (a new launcher, a new login)
            self.assertEqual(a2.me["rating"], 1500)           # nothing was rated: the rating it had
            r = self.notice(a2, "set_resumed")
            self.assertEqual((r["set"], r["info"]["wins"][slot], r["slot"]), (sid, 1, slot))
            self.assertIn("you are back in the ranked set (1-0)", r["msg"])
            self.assertIn("Alice is back; the set goes on", self.notice(b, "opponent_back")["msg"])
            ea2, eb2 = expect(a2, "match_start", 20.0), expect(b, "match_start", 20.0)
        self.assertEqual((ea2["set"]["id"], ea2["set"]["number"], ea2["slot"]), (sid, 2, slot))   # the same sides
        self.assertEqual(ea2["set"]["wins"][slot], 1)                                           # the same score
        self.assertEqual(ea2["fight"][("p1", "p2")[slot]], ea["fight"][("p1", "p2")[slot]])      # the same characters
        ra, _ = self.game(a2, b, ea2, slot)                   # 2-0 Alice
        se = expect(a2, "set_end")
        self.assertEqual((se["status"], se["result"], se["wins"]), ("confirmed", "win", [2, 0]))
        rating = self.account("Alice")["rating"]
        self.assertGreater(rating, 1500)
        self.assertAlmostEqual(self.player("Alice").rating.r, rating, places=3)     # memory = database
        self.assertEqual(self.account("Alice")["ranked_games"], 1)

    def test_launcher_closed_between_games_and_back(self):
        self._back(self.close_launcher)                       # 1.1.8: a loss at once (the 2026-10-28 set)

    def test_launcher_crashed_between_games_and_back(self):
        self._back(self.crash)

    def test_the_time_left_is_told_again(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        with mock.patch.object(type(self.s.srv), "AWAY_MARKS", (4, 2)):
            self.crash(a)
            self.notice(b, "opponent_dropped")
            lefts = [self.notice(b, "opponent_away")["left"] for _ in range(2)]
        self.assertEqual(lefts, [4, 2])
        self.assertEqual(expect(b, "set_end", 10)["outcome_reason"], "no_return")


# ============================================================================== 3. the next game, before its fight
class BeforeTheFightTest(Base):
    def test_launcher_closed_when_the_next_game_started(self):
        """The real case: game 2 already started (inside the running games) when the launcher closed -- it used to
        quit that game, which lost the set."""
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        slot, sid = ea["slot"], ea["set"]["id"]
        self.game(a, b, ea, slot)
        ea2, eb2 = self.next_game(a, b)
        self.assertTrue(ea2["continue"])
        self.close_launcher(a)                                # logout: leave_match of game 2, then gone
        rb = expect(b, "match_result")
        self.assertEqual((rb["status"], rb["reason"], rb["blame"], rb["rating"]), ("void", "set_restart", None, None))
        self.assertEqual(rb["set"]["wins"][slot], 1)          # 1-0 stays
        self.notice(b, "opponent_dropped")
        a2 = self.again("Alice")
        self.notice(a2, "set_resumed")
        ea3, eb3 = expect(a2, "match_start", 20.0), expect(b, "match_start", 20.0)
        self.assertEqual((ea3["set"]["id"], ea3["set"]["number"], ea3["slot"]), (sid, 2, slot))
        self.assertFalse(ea3["continue"])                     # a new connection: Alice's game is new
        self.game(a2, b, ea3, slot)
        se = expect(b, "set_end")
        self.assertEqual((se["status"], se["result"], se["games"]), ("confirmed", "loss", 2))
        alice = self.account("Alice")
        self.assertEqual(self.s.call(lambda: self.s.srv.store.strikes(alice["id"], 0)), 0)    # no strike either

    def test_game_gone_with_the_launcher_still_here(self):
        """The launcher is online but its game is not running when the next game continues in it (it says
        leave_match): that game starts again over a new connection, the set goes on."""
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        slot = ea["slot"]
        self.game(a, b, ea, slot)
        ea2, _ = self.next_game(a, b)
        a.leave_match(ea2["match"])
        ra = expect(a, "match_result")
        self.assertEqual((ra["status"], ra["reason"]), ("void", "set_restart"))
        ea3, _ = self.next_game(a, b, keep=False)
        self.assertEqual((ea3["set"]["number"], ea3["slot"], ea3["continue"]), (2, slot, False))

    def test_a_crash_report_before_the_fight(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        ea2, eb2 = self.next_game(a, b)
        b.report_result(None, None, match_id=eb2["match"], source="crash")
        rb = expect(b, "match_result")
        self.assertEqual((rb["status"], rb["reason"]), ("void", "set_restart"))     # 1.1.8: the whole set void
        ea3, _ = self.next_game(a, b, keep=False)
        self.assertEqual(ea3["set"]["number"], 2)

    def test_without_end_it_is_leaving_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, 1 - ea["slot"])                   # Bob 1-0
        n = self.s.srv.SET_RESTARTS
        for i in range(n):
            ea2, _ = self.next_game(a, b)
            a.leave_match(ea2["match"])
            self.assertEqual(expect(a, "match_result")["reason"], "set_restart")
        ea2, _ = self.next_game(a, b)
        a.leave_match(ea2["match"])                           # one more: the old rules (an early quit: leaving)
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["result"]), ("forfeit", "loss"))

    def test_connection_lost_before_the_fight_and_not_back(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        ea2, _ = self.next_game(a, b)
        self.crash(a)                                         # the lobby connection breaks, the game 2 is "playing"
        n = self.notice(b, "opponent_dropped")
        self.assertEqual(n["left"], AWAY)                     # the set's window, not T5L_RECONNECT_GRACE (2 s here)
        rb = expect(b, "match_result", AWAY + 5)
        self.assertEqual((rb["status"], rb["reason"]), ("void", "no_return"))
        se = expect(b, "set_end")
        self.assertEqual((se["status"], se["result"], se["outcome_reason"]), ("forfeit", "win", "no_return"))
        self.assertGreater(se["rating"]["delta"], 0)


# ============================================================================== 4. not back; 5. both gone
class NotBackTest(Base):
    def test_not_back_in_time_loses_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])                       # Alice leads 1-0 ...
        self.crash(a)                                         # ... crashes, and does not come back
        se = expect(b, "set_end", AWAY + 5)
        self.assertEqual((se["status"], se["result"], se["outcome_reason"], se["blame"]),
                         ("forfeit", "win", "no_return", "opponent"))
        self.assertGreater(se["rating"]["delta"], 0)
        self.assertEqual(setsmod.result_text(se).split(";")[0],
                         "You won the set (your opponent did not come back within 6 s)")
        sv, text = self.history_set(b, "Bob")
        self.assertIn("(your opponent did not come back within 90 s)", text)   # (a history row: the 90 s default)
        rating = self.account("Alice")["rating"]
        self.assertLess(rating, 1500)
        a2 = self.again("Alice")                              # later: the database's rating, no set
        self.assertEqual(a2.me["rating"], round(rating))
        self.assertIsNone(self.player("Alice").set)
        sv, text = self.history_set(a2, "Alice")
        self.assertEqual((sv["reason"], sv["by"], sv["result"]), ("no_return", "you", "loss"))
        self.assertIn("set lost 1-0 (you did not come back within 90 s)", text)

    def test_both_gone_is_void(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        self.game(a, b, ea, ea["slot"])
        sid = ea["set"]["id"]
        self.crash(a)
        self.close_launcher(b)
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.store.set_row(sid)["status"] != "playing", AWAY + 5))
        row = self.s.call(lambda: self.s.srv.store.set_row(sid))
        self.assertEqual((row["status"], row["reason"], row["rating"]), ("void", "both_left", None))
        for n in ("Alice", "Bob"):
            acc = self.account(n)
            self.assertEqual((acc["rating"], acc["ranked_games"]), (1500, 0))


# ============================================================================== 6. a ranked room's set
class RoomSetTest(Base):
    def test_a_ranked_room_set_waits_too(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        room = a.create_room("dojo", ranked=True)
        b.join_room(room["id"])
        ea, eb = expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)
        self.game(a, b, ea, eb["slot"])                       # Bob 1-0
        self.crash(b)                                         # 1.1.8: leaving the room ended the set at once
        self.notice(a, "opponent_dropped")
        b2 = self.again("Bob")
        eb2, ea2 = expect(b2, "match_start", 20.0), expect(a, "match_start", 20.0)
        self.assertEqual((eb2["set"]["id"], eb2["set"]["number"], eb2["slot"]), (eb["set"]["id"], 2, eb["slot"]))


# ============================================================================== 7. sides
class SidesTest(Base):
    def test_a_launcher_without_sets_keeps_the_sides_inside_the_set(self):
        """Each ranked game is rated on its own, the next one is a rematch vote -- the coin only at the set's first
        game (1.1.7: again for every rematch)."""
        a, b = self.acc("Alice", sets=False), self.acc("Bob", sets=False)
        ea, _ = self.start(a, b, coin=0)
        self.assertFalse(ea["set"].get("rated", False))
        slot, sid = ea["slot"], ea["set"]["id"]
        for i in range(3):
            ra, _ = self.game(a, b, ea, i % 2)
            with mock.patch.object(casual, "_side_coin", return_value=1):     # a coin would swap them
                a.rematch(ra["match"], True)
                b.rematch(ra["match"], True)
                ea = expect(a, "match_start", 20.0)
                expect(b, "match_start", 20.0)
            self.assertEqual((ea["set"]["id"], ea["slot"]), (sid, slot))

    def test_quick_matches_keep_their_coin(self):
        slots = []
        for coin in (0, 1):
            a, b = self.acc(f"Q{coin}a"), self.acc(f"Q{coin}b")
            with mock.patch.object(casual, "_side_coin", return_value=coin):
                a.quick_match("jin")
                b.quick_match("paul")
                slots.append(expect(a, "match_start", 20.0)["slot"])
                expect(b, "match_start", 20.0)
        self.assertEqual(sorted(slots), [0, 1])               # the coin decides each quick match


# ============================================================================== 8. leaderboard
class LeaderboardTest(Base):
    def test_ranked_and_casual_wins_and_losses(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.start(a, b)
        w = ea["slot"]
        self.game(a, b, ea, w)                                # Alice wins a ranked set 2-0 ...
        ea2, _ = self.next_game(a, b)
        self.game(a, b, ea2, w)
        expect(a, "set_end")
        a.quick_match("jin")                                  # ... and loses a quick match
        b.quick_match("paul")
        eq = expect(a, "match_start", 20.0)
        expect(b, "match_start", 20.0)
        self.game(a, b, eq, 1 - eq["slot"])
        rows = {r["name"]: r for r in a.leaderboard()}
        al, bo = rows["Alice"], rows["Bob"]
        self.assertEqual([al[k] for k in ("ranked_wins", "ranked_losses", "casual_wins", "casual_losses")],
                         [2, 0, 0, 1])
        self.assertEqual([bo[k] for k in ("ranked_wins", "ranked_losses", "casual_wins", "casual_losses")],
                         [0, 2, 1, 0])
        for k in ("wins", "losses", "draws", "rating", "rd", "games", "ranked_games", "place", "rank", "main"):
            self.assertIn(k, al)                              # the old fields stay (older launchers)
        self.assertEqual((al["wins"], al["losses"]), (1, 1))  # (the record: the set once, the quick match)
        # the same as the profile's split
        st = a.profile("Alice")["stats"]
        self.assertEqual((st["ranked"]["wins"], st["casual"]["losses"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
