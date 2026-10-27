"""The server's sides (1.1.7; server/casual.py "The server's sides", docs/RANKED.md "Sides"): who is P1 (= the netplay
host) and who is P2 in a match whose sides the server decides. Owner: "never the one with the lower ping is P1".

1. the queue (ranked and quick): a fair coin over many matches -- about half each, not tied to the server round
   trip, not to the queue order (1.1.6 and before: the lower server round trip was P1 every time)
2. a ranked set with the lower-ping player on P2: the games keep the set's sides, the winner's rating, record,
   history and profile are right whichever side the winner played
3. a ranked rematch (a new set) draws the sides again; a quick rematch keeps them; a ranked room's new set is
   drawn (not the room's member order), its next games keep it
4. the 1.1.6 launcher's client (git tag v1.1.6 -- its lobby/t5lobby is the release zip's, file for file) on this
   server: it plays the side the server names (role, slot, the game's T5_NET_MODE)
"""
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import unittest
from unittest import mock

import util
from util import BUILD, ServerThread, client, expect
from t5lobby.server import Config, LobbyServer, casual

SETS = {"set_next_seconds": 0.3}


# ============================================================================== 1. the queue (no network)
class _Conn:
    def __init__(self):
        self.build_id, self.release, self.ip = "b1", "", "127.0.0.1"
        self.caps = frozenset()

    def send(self, msg):
        pass


class QueueSidesTest(unittest.IsolatedAsyncioTestCase):
    N = 400            # matches per case: a fair coin lands within 0.40-0.60 with 4 standard deviations to spare

    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(**util.FAST))
        self.k = 0

    async def asyncTearDown(self):
        self.srv.store.close()

    def player(self, rtt, r=1500.0):
        from t5lobby.rating import Rating
        from t5lobby.server.lobby import Player
        self.k += 1
        p = Player(_Conn(), f"P{self.k}", guest=False)
        p.rating = Rating(r, 80)
        p.server_rtt = rtt
        self.srv.players[p.id] = p
        return p

    def pair(self, mode, rtt_first, rtt_second):
        """Two players queue (`first` a moment earlier) and get matched. -> (first, second, P1)."""
        now = time.monotonic()
        a, b = self.player(rtt_first), self.player(rtt_second)
        self.srv._enqueue(a, mode, now - 1.0)
        self.srv._enqueue(b, mode, now - 0.5)
        made = self.srv.match_queue(now)
        self.assertEqual(len(made), 1)
        m = a.match
        self.assertIs(m, b.match)
        self.assertEqual(m.queue_mode, mode)
        for p in (a, b):                     # (done with: the next pair has the queue to itself)
            p.match, p.status = None, "idle"
        self.srv.matches.pop(m.id, None)
        self.srv._cancel_timers(m)
        return a, b, m.players[0]

    def check_share(self, what, hits):
        share = hits / self.N
        self.assertTrue(0.40 <= share <= 0.60, f"{what}: {hits} of {self.N} ({share:.0%}); a coin gives about half")

    async def test_the_lower_ping_is_not_always_p1(self):
        for mode in ("ranked", "quick"):
            with self.subTest(mode=mode):
                low_first = low_second = first_p1 = 0
                for i in range(self.N):
                    # the lower round trip queues first in half the matches, second in the other half
                    if i % 2:
                        a, b, p1 = self.pair(mode, 5.0, 80.0)
                        low = a
                    else:
                        a, b, p1 = self.pair(mode, 80.0, 5.0)
                        low = b
                    if p1 is low:
                        if low is a:
                            low_first += 1
                        else:
                            low_second += 1
                    first_p1 += p1 is a
                self.check_share(f"{mode}: the lower server round trip as P1", low_first + low_second)
                self.check_share(f"{mode}: the one who queued first as P1", first_p1)
                # neither order of queueing makes the lower round trip P1 more often (each half: N / 2 matches)
                for what, hits in (("queued first", low_first), ("queued second", low_second)):
                    share = hits / (self.N / 2)
                    self.assertTrue(0.36 <= share <= 0.64, f"{mode}: lower round trip {what}: P1 in {share:.0%}")

    async def test_unknown_round_trips_too(self):
        # (1.1.6: a player without a measurement counted as 1e9 ms -- always P2 against anyone measured)
        hits = sum(self.pair("ranked", None, 30.0)[2].server_rtt is None for _ in range(self.N))
        self.check_share("ranked: the player without a server round trip as P1", hits)


# ============================================================================== 2.-3. with a real server
class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        cfg = dict(SETS)
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        from t5lobby.server.ratelimit import KeyedBuckets
        self.s.call(lambda: setattr(self.s.srv, "registrations", KeyedBuckets(rate=100.0, burst=100)))
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def acc(self, name, rtt=None, sets=True, **kw):
        kw.setdefault("auto_ready", True)
        c = client(self.s, name, password="pw-" + name, register=True, sets=sets, **kw)
        self.clients.append(c)
        if rtt is not None:
            self.rtt(c, rtt)
        return c

    def rtt(self, c, ms):
        """What the launcher's UDP measurement would have reported (udp_rtt)."""
        pid = c.me["id"]
        self.s.call(lambda: setattr(self.s.srv.players[pid], "server_rtt", float(ms)))

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))

    def game(self, a, b, ev, winner):
        for c in (a, b):
            c.report_result(winner, [3, 1] if winner == 0 else [1, 3], match_id=ev["match"], source="game")
        return expect(a, "match_result"), expect(b, "match_result")

    def next_game(self, a, b, keep=True):
        for c in (a, b):
            c.set_next(None, keep=keep)
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)

    def ranked(self, a, b, coin):
        """a (lower ping) and b queue for ranked with the side coin fixed. -> (a's match_start, b's)."""
        with mock.patch.object(casual, "_side_coin", create=True, return_value=coin):
            a.ranked_match("jin")
            b.ranked_match("paul")
            return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)


class RankedSetSidesTest(Base):
    def test_the_coin_decides_not_the_ping(self):
        roles = set()
        for coin in (0, 1):
            with self.subTest(coin=coin):
                a, b = self.acc(f"Low{coin}", rtt=5), self.acc(f"High{coin}", rtt=80)
                ea, eb = self.ranked(a, b, coin)
                self.assertEqual({ea["slot"], eb["slot"]}, {0, 1})
                self.assertEqual(ea["role"], "host" if ea["slot"] == 0 else "join")
                roles.add(ea["role"])
                a.leave_match(ea["match"])
                expect(a, "match_result")
                expect(b, "match_result")
                for c in (a, b):
                    c.close()
                    self.clients.remove(c)
        # 1.1.6: the lower round trip (5 ms against 80) was the host both times
        self.assertEqual(roles, {"host", "join"}, "the side coin decides P1, whatever the server round trips")

    def test_lower_ping_on_p2_wins_the_set(self):
        a, b = self.acc("Alice", rtt=5), self.acc("Bob", rtt=80)       # Alice: the lower server round trip
        ea, eb = self.ranked(a, b, 1)        # (the coin's 1 swaps the queue's order: Alice queued first)
        self.assertEqual((ea["slot"], ea["role"], eb["slot"], eb["role"]), (1, "join", 0, "host"),
                         "Alice (5 ms) must be able to get P2")
        self.assertEqual(ea["ticket"].game_env()["T5_NET_MODE"], "join")
        self.assertEqual(eb["ticket"].game_env()["T5_NET_MODE"], "host")
        sid = ea["set"]["id"]
        # game 1: P2 (Alice) wins; game 2 keeps the sides (inside the running games), P2 wins again
        ra, _ = self.game(a, b, ea, 1)
        self.assertEqual(ra["set"]["wins"], [0, 1])                 # [P1, P2]
        with mock.patch.object(casual, "_side_coin", create=True, return_value=1):     # (no coin between two games)
            ea2, eb2 = self.next_game(a, b)
        self.assertEqual((ea2["set"]["id"], ea2["slot"], eb2["slot"]), (sid, 1, 0))
        self.assertTrue(ea2["continue"])
        ra2, rb2 = self.game(a, b, ea2, 1)
        self.assertEqual(ra2["set"]["state"], "ended")
        self.assertEqual(ra2["set"]["result"]["winner"], 1)        # the set's P2 = Alice
        sa, sb = expect(a, "set_end"), expect(b, "set_end")
        self.assertEqual((sa["result"], sa["wins"]), ("win", [2, 0]))      # from Alice's side: [you, opponent]
        self.assertEqual((sb["result"], sb["wins"]), ("loss", [0, 2]))
        self.assertGreater(sa["rating"]["delta"], 0)
        self.assertLess(sb["rating"]["delta"], 0)
        acc_a, acc_b = self.account("Alice"), self.account("Bob")
        self.assertGreater(acc_a["rating"], 1500)
        self.assertLess(acc_b["rating"], 1500)
        self.assertEqual((acc_a["ranked_games"], acc_a["wins"], acc_a["losses"]), (1, 1, 0))
        self.assertEqual((acc_b["ranked_games"], acc_b["wins"], acc_b["losses"]), (1, 0, 1))
        # the database: P1 / P2 names as played, the winner by side; history and profile from each player's side
        row = self.s.call(lambda: self.s.srv.store.set_row(sid))
        self.assertEqual((row["p1_name"], row["p2_name"], row["winner"], row["score"]), ("Bob", "Alice", 1, [0, 2]))
        hist = a.history("Alice")
        self.assertEqual([h["result"] for h in hist], ["win", "win"])
        self.assertEqual(hist[0]["score"], [3, 1])                  # rounds: [you, opponent]
        self.assertEqual((hist[0]["opponent"], hist[0]["you_char"], hist[0]["opp_char"]), ("Bob", "jin", "paul"))
        self.assertGreater(hist[0]["delta"], 0)
        self.assertEqual(hist[0]["set"]["score"], [2, 0])
        prof = b.profile("Bob")
        st = prof["sets"][0]
        self.assertEqual((st["result"], st["score"], st["opponent"]), ("loss", [0, 2], "Alice"))
        self.assertEqual(b.history("Bob")[0]["result"], "loss")
        board = {r["name"]: r for r in a.leaderboard()}
        self.assertEqual(board["Alice"]["wins"], 1)


class RematchSidesTest(Base):
    def _set(self, a, b, ea):
        """Win the set 2-0 for P1."""
        self.game(a, b, ea, 0)
        ea2, _ = self.next_game(a, b)
        ra, _ = self.game(a, b, ea2, 0)
        expect(a, "set_end")
        expect(b, "set_end")
        return ra["match"]

    def test_a_ranked_rematch_draws_the_sides_again(self):
        a, b = self.acc("Alice", rtt=5), self.acc("Bob", rtt=80)
        ea, _ = self.ranked(a, b, 0)
        mid = self._set(a, b, ea)
        slot = ea["slot"]
        for coin, swapped in ((1, True), (0, False)):
            with self.subTest(coin=coin):
                with mock.patch.object(casual, "_side_coin", create=True, return_value=coin):
                    a.rematch(mid, True, keep=True)
                    b.rematch(mid, True, keep=True)
                    fa = expect(a, "match_found")
                    sa, _ = expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)
                want = 1 - slot if swapped else slot
                self.assertEqual(sa["slot"], want)
                self.assertNotEqual(sa["set"]["id"], ea["set"]["id"])          # a new set
                # other sides: a new netplay session (a game keeps its slot); the same: inside the running games
                self.assertEqual(fa["keep"], not swapped)
                self.assertEqual(bool(sa.get("continue")), not swapped)
                slot, ea = want, sa
                mid = self._set(a, b, sa)

    def test_a_quick_rematch_keeps_the_sides(self):
        a, b = self.acc("Alice", rtt=5), self.acc("Bob", rtt=80)
        a.quick_match("jin")
        b.quick_match("paul")
        sa, _ = expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)
        ra, _ = self.game(a, b, sa, 0)
        with mock.patch.object(casual, "_side_coin", create=True, return_value=1):
            a.rematch(sa["match"], True)
            b.rematch(sa["match"], True)
            sa2, _ = expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)
        self.assertEqual(sa2["slot"], sa["slot"])

    def test_a_ranked_room_draws_each_new_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        with mock.patch.object(casual, "_side_coin", create=True, return_value=1):
            room = a.create_room("dojo", ranked=True)
            b.join_room(room["id"])
            ea, eb = expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)
            # 1.1.6: the room's first member (its creator) was P1 in every ranked room match
            self.assertEqual((ea["role"], eb["role"]), ("join", "host"))
            self.game(a, b, ea, 0)
            ea2, eb2 = self.next_game(a, b)                    # the set's next game: its sides, no coin
            self.assertEqual((ea2["slot"], eb2["slot"], ea2["set"]["id"]), (1, 0, ea["set"]["id"]))
            self.game(a, b, ea2, 0)
            expect(a, "set_end")
        with mock.patch.object(casual, "_side_coin", create=True, return_value=0):
            a.rematch()                                        # the room's next set
            ea3 = expect(a, "match_start", 20.0)
        self.assertNotEqual(ea3["set"]["id"], ea["set"]["id"])
        self.assertEqual(ea3["slot"], 0)


# ============================================================================== 4. the 1.1.6 launcher
LOBBY = os.path.dirname(util.HERE)
OLD_REF = os.environ.get("T5L_SIDES_OLD_REF", "v1.1.6")      # the release before random sides
_TMP = []


def _old_client(test, ref):
    git = shutil.which("git")
    if not git:
        test.skipTest("no git")
    r = subprocess.run([git, "-C", os.path.dirname(LOBBY), "archive", "--format=tar", ref, "lobby/t5lobby"],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        test.skipTest(f"no {ref} in this checkout")
    tmp = tempfile.mkdtemp(prefix="t5sides-old-")
    _TMP.append(tmp)
    tarfile.open(fileobj=io.BytesIO(r.stdout)).extractall(tmp, filter="data")
    import importlib
    import sys
    sys.path.insert(0, os.path.join(LOBBY, "tools"))
    import natsim
    name = "t5lobby_sidesold_" + "".join(ch for ch in ref if ch.isalnum())
    natsim.load_pkg(name, os.path.join(tmp, "lobby", "t5lobby"))
    return importlib.import_module(name + ".client")


def tearDownModule():
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


class OldLauncherTest(Base):
    def test_the_1_1_6_launcher_plays_the_side_it_is_given(self):
        oldc = _old_client(self, OLD_REF)
        olds = []
        for name, rtt in (("Near", 5), ("Far", 80)):
            c = oldc.LobbyClient(self.s.addr, BUILD, relay_bridge=False, sets=True, auto_ready=True)
            c.connect()
            c.register(name, "pw-" + name)
            self.clients.append(c)
            self.rtt(c, rtt)
            olds.append(c)
        near, far = olds
        ea, eb = self.ranked(near, far, 1)   # (1 swaps the queue's order: Near queued first)
        # the lower round trip on P2, and the 1.1.6 client starts its game as the joiner (P2)
        self.assertEqual((ea["role"], ea["slot"], eb["role"], eb["slot"]), ("join", 1, "host", 0))
        self.assertEqual((ea["ticket"].role, ea["ticket"].slot), ("join", 1))
        self.assertEqual(ea["ticket"].game_env()["T5_NET_MODE"], "join")
        self.assertEqual(eb["ticket"].game_env()["T5_NET_MODE"], "host")
        self.assertTrue(ea["set"]["rated"])
        # its set score and result from its own side (sets.status_text with its slot)
        self.game(near, far, ea, 1)
        ea2, _ = self.next_game(near, far)
        self.assertEqual(ea2["slot"], 1)
        ra, _ = self.game(near, far, ea2, 1)
        sa = expect(near, "set_end")
        self.assertEqual((sa["result"], sa["wins"]), ("win", [2, 0]))
        oldsets = __import__(type(near).__module__.rsplit(".", 1)[0] + ".sets", fromlist=["status_text"])
        self.assertTrue(oldsets.status_text(ra["set"], ea2["slot"]).startswith("Set 2-0"),
                        oldsets.status_text(ra["set"], ea2["slot"]))
        self.assertGreater(self.account("Near")["rating"], 1500)


if __name__ == "__main__":
    unittest.main()
