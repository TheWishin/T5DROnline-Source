"""Casual matches by choice (1.1.5, server/casual.py; docs/ONLINE.md "Sides and stages by choice"): the side and
stage wishes of challenges, friends' casual invites and rooms (classic and community), Swap sides on a rematch, and
what stays as it was: Quick and Ranked (server sides -- a coin since 1.1.7, test_sides.py --, random stage), ranked
rooms, older launchers."""
import asyncio
import io
import os
import random
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
from unittest import mock

import util
from util import BUILD, ServerThread, client, expect
from t5lobby import fighters, proto
from t5lobby.client import LobbyClient
from t5lobby.proto import LobbyError
from t5lobby.server import casual

TABLE = fighters.table()


def drawn_stage(seed, old_stages=False):
    """The stage the server draws for a match without wishes (characters Random, as these test players have)."""
    return TABLE.resolve(fighters.RANDOM, fighters.RANDOM, fighters.RANDOM, seed, old_stages=old_stages)[2]


def coin_stage(seed, w1, w2):
    """The stage of two different wishes (P1's, P2's): the coin from the match's seed, a Random that wins drawn."""
    pick = (w1, w2)[random.Random((int(seed) ^ 0x5EED57A6) & 0xFFFFFFFF).randrange(2)]
    return drawn_stage(seed) if pick == fighters.RANDOM else pick


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        from t5lobby.server.ratelimit import KeyedBuckets
        self.s.call(lambda: setattr(self.s.srv, "registrations", KeyedBuckets(rate=100.0, burst=100)))
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name, side=None, stage=None, **kw):
        c = client(self.s, name, **kw)
        self.clients.append(c)
        if side is not None or stage is not None:
            c.set_casual_prefs(side, stage or fighters.RANDOM)
            pid = c.me["id"]
            want = (side, stage or fighters.RANDOM)
            self.assertTrue(self.s.wait_for(lambda: self._wish(pid) == want))
        return c

    def _wish(self, pid):
        p = self.s.srv.players.get(pid)
        return None if p is None else (getattr(p, "casual_side", None), getattr(p, "casual_stage", "random"))

    def challenge(self, a, b):
        """a challenges b, b accepts. -> (a's match_start, b's match_start, b's challenged event)."""
        cid = a.challenge(b.me["id"])
        ev = expect(b, "challenged")
        b.answer_challenge(cid, accept=True)
        expect(a, "match_found")
        expect(b, "match_found")
        return expect(a, "match_start", 20), expect(b, "match_start", 20), ev

    def finish(self, a, b, sa):
        a.report_result(0, [3, 1])
        b.report_result(0, [3, 1])
        expect(a, "match_result")
        expect(b, "match_result")
        return sa["match"]


class WishesTest(Base):
    def test_the_welcome_lists_the_stages(self):
        a = self.c("Alice")
        got = a.casual_stages()
        self.assertTrue(a.casual_ok())
        self.assertIn("s20", got)
        self.assertNotIn("t5s01", got)                  # T5L_OLD_STAGES off: only the stage select's
        self.assertEqual(got, TABLE.stage_pool())

    def test_tekken_5_stages_when_the_server_draws_them(self):
        self.s.srv.cfg.old_stages = True
        a = self.c("Alice")
        self.assertIn("t5s01", a.casual_stages())
        old = self.c("Bob", old_stages=False)           # (a launcher that does not know them is not offered them)
        self.assertNotIn("t5s01", old.casual_stages())
        with self.assertRaises(LobbyError):
            old._call({"t": "casual_prefs", "side": None, "stage": "t5s01"})

    def test_bad_wishes_are_refused(self):
        a = self.c("Alice")
        for side, stage in ((2, "random"), ("p1", "random"), (True, "random"), (None, "s99"), (0, "t5s01")):
            with self.assertRaises(LobbyError):
                a._call({"t": "casual_prefs", "side": side, "stage": stage})
        a._call({"t": "casual_prefs", "side": 1, "stage": "s33"})
        self.assertEqual(self.s.call(lambda: self._wish(a.me["id"])), (1, "s33"))

    def test_the_wishes_come_back_after_a_new_login(self):
        a = self.c("Alice", side=1, stage="s20")
        a.close()
        b = client(self.s, None)
        self.clients.append(b)
        b.casual_prefs = (1, "s20")                    # (what the launcher keeps)
        b.login_guest("Alice2")
        self.assertTrue(self.s.wait_for(lambda: self._wish(b.me["id"]) == (1, "s20")))


class ChallengeTest(Base):
    def test_no_wishes_the_challenger_is_p1(self):
        a, b = self.c("Alice"), self.c("Bob")
        sa, sb, ev = self.challenge(a, b)
        self.assertEqual((sa["role"], sb["role"]), ("host", "join"))
        self.assertEqual(ev["wish"], {"side": None, "stage": "random"})
        self.assertEqual(sa["fight"]["stage"], drawn_stage(sa["seed"]))     # the draw is exactly the old one
        self.assertEqual(sa["casual"], {"swap": True})

    def test_the_challenger_wants_p2(self):
        a, b = self.c("Alice", side=1), self.c("Bob")
        sa, sb, ev = self.challenge(a, b)
        self.assertEqual(ev["wish"]["side"], 1)        # Bob is told before he accepts
        self.assertEqual((sa["role"], sa["slot"], sb["role"], sb["slot"]), ("join", 1, "host", 0))
        self.assertEqual([p["name"] for p in sa["players"]], ["Bob", "Alice"])

    def test_the_challenged_player_wants_p1(self):
        a, b = self.c("Alice"), self.c("Bob", side=0)
        sa, sb, _ = self.challenge(a, b)
        self.assertEqual((sa["role"], sb["role"]), ("join", "host"))

    def test_both_get_their_wish(self):
        a, b = self.c("Alice", side=1), self.c("Bob", side=0)
        sa, sb, _ = self.challenge(a, b)
        self.assertEqual((sa["role"], sb["role"]), ("join", "host"))

    def test_the_same_side_is_a_coin_flip(self):
        for coin, roles in ((0, ("host", "join")), (1, ("join", "host"))):
            with self.subTest(coin=coin), mock.patch.object(casual, "_coin", return_value=coin):
                a, b = self.c(f"Alice{coin}", side=0), self.c(f"Bob{coin}", side=0)
                sa, sb, _ = self.challenge(a, b)
                self.assertEqual((sa["role"], sb["role"]), roles)

    def test_the_same_stage(self):
        a, b = self.c("Alice", stage="s33"), self.c("Bob", stage="s33")
        sa, sb, ev = self.challenge(a, b)
        self.assertEqual(ev["wish"]["stage"], "s33")
        self.assertEqual((sa["fight"]["stage"], sb["fight"]["stage"]), ("s33", "s33"))

    def test_one_stage_and_random(self):
        a, b = self.c("Alice", stage="s20"), self.c("Bob")
        sa, sb, _ = self.challenge(a, b)
        self.assertEqual(sa["fight"]["stage"], sb["fight"]["stage"])
        self.assertEqual(sa["fight"]["stage"], coin_stage(sa["seed"], "s20", fighters.RANDOM))

    def test_two_stages(self):
        a, b = self.c("Alice", stage="s20"), self.c("Bob", stage="s33")
        sa, sb, _ = self.challenge(a, b)
        self.assertIn(sa["fight"]["stage"], ("s20", "s33"))
        self.assertEqual(sa["fight"]["stage"], coin_stage(sa["seed"], "s20", "s33"))

    def test_a_tekken_5_stage_needs_both_launchers(self):
        self.s.srv.cfg.old_stages = True
        a, b = self.c("Alice", stage="t5s06"), self.c("Bob", stage="t5s06")
        sa, _, _ = self.challenge(a, b)
        self.assertEqual(sa["fight"]["stage"], "t5s06")
        c, d = self.c("Carol", stage="t5s06"), self.c("Dave", old_stages=False)
        sc, _, _ = self.challenge(c, d)
        self.assertNotIn(sc["fight"]["stage"], [x["key"] for x in TABLE.stages if x.get("t5")])

    def test_an_older_launcher(self):
        # a launcher before 1.1.5 sends no wishes: as before, and the new one's wishes still count
        a, b = self.c("Alice", side=1, stage="s33"), self.c("Bob")
        self.assertFalse(hasattr(self.s.call(lambda: self.s.srv.players[b.me["id"]]), "casual_side"))
        sb, sa, _ = self.challenge(b, a)
        self.assertEqual((sb["role"], sa["role"]), ("host", "join"))
        self.assertEqual(sa["fight"]["stage"], coin_stage(sa["seed"], fighters.RANDOM, "s33"))


class QueueTest(Base):
    def test_quick_and_ranked_keep_the_server_s_choice(self):
        for mode in ("quick", "ranked"):
            with self.subTest(mode=mode):
                a = self.c(f"Alice{mode}", side=1, stage="s33", auto_ready=True, password="alice-pw1", register=True)
                b = self.c(f"Bob{mode}", side=1, stage="s33", auto_ready=True, password="bob-pw1", register=True)
                self.s.call(lambda: setattr(self.s.srv.players[a.me["id"]], "server_rtt", 5.0))
                self.s.call(lambda: setattr(self.s.srv.players[b.me["id"]], "server_rtt", 50.0))
                with mock.patch.object(casual, "_side_coin", return_value=0):
                    (a.quick_match if mode == "quick" else a.ranked_match)()
                    (b.quick_match if mode == "quick" else b.ranked_match)()
                    sa, sb = expect(a, "match_start", 20), expect(b, "match_start", 20)
                # the server's coin (test_sides.py; 0: the queue's order), not Alice's P2 wish
                self.assertEqual((sa["role"], sb["role"]), ("host", "join"))
                self.assertEqual(sa["fight"]["stage"], drawn_stage(sa["seed"]))
                self.assertNotIn("casual", sa)
                mid = self.finish(a, b, sa)
                # Swap sides is a casual choice: a quick rematch keeps the sides
                if mode == "quick":
                    a.rematch(mid, True, swap=True)
                    off = expect(b, "rematch")
                    self.assertNotIn("swap", off)
                    b.rematch(mid, True)
                    sa2, sb2 = expect(a, "match_start", 20), expect(b, "match_start", 20)
                    self.assertEqual((sa2["role"], sb2["role"]), ("host", "join"))
                    self.finish(a, b, sa2)
                for c in (a, b):
                    c.close()


class RematchTest(Base):
    def test_swap_sides(self):
        a, b = self.c("Alice", stage="s20"), self.c("Bob", stage="s20")
        sa, sb, _ = self.challenge(a, b)
        self.assertEqual(sa["role"], "host")
        mid = self.finish(a, b, sa)
        a.rematch(mid, True, keep=True, swap=True)
        off = expect(b, "rematch")
        self.assertEqual((off["state"], off.get("swap")), ("offered", True))
        b.rematch(mid, True, keep=True)
        fa, fb = expect(a, "match_found"), expect(b, "match_found")
        self.assertFalse(fa["keep"])                   # a new netplay session: the games keep their slot per session
        self.assertEqual((fa["role"], fb["role"]), ("join", "host"))
        sa2, sb2 = expect(a, "match_start", 20), expect(b, "match_start", 20)
        self.assertEqual((sa2["role"], sb2["role"], sa2["continue"]), ("join", "host", False))
        self.assertEqual(sa2["fight"]["stage"], "s20")
        self.assertEqual(sa2["casual"], {"swap": True})
        mid2 = self.finish(a, b, sa2)
        # no swap: the sides stay, and the games go on (keep)
        a.rematch(mid2, True, keep=True)
        self.assertNotIn("swap", expect(b, "rematch"))
        b.rematch(mid2, True, keep=True)
        fa = expect(a, "match_found")
        self.assertTrue(fa["keep"])
        self.assertEqual(fa["role"], "join")
        mid3 = self.finish(a, b, expect(a, "match_start", 20))
        # the one who accepts may ask for it too
        a.rematch(mid3, True, keep=True)
        expect(b, "rematch")
        b.rematch(mid3, True, keep=True, swap=True)
        self.assertEqual(expect(a, "match_found")["role"], "host")


class RoomTest(Base):
    def test_classic_room(self):
        a, b = self.c("Alice", side=1, stage="s33"), self.c("Bob", stage="s33")
        room = a.create_room("dojo")
        b.join_room(room["id"])
        fa, fb = expect(a, "match_found"), expect(b, "match_found")
        self.assertEqual((fa["role"], fb["role"]), ("join", "host"))      # the owner asked for P2
        a.ready()
        b.ready()
        sa = expect(a, "match_start", 20)
        self.assertEqual(sa["fight"]["stage"], "s33")
        self.assertEqual(sa["casual"], {"swap": True})

    def test_a_ranked_room_keeps_the_server_s_choice(self):
        a = self.c("Alice", password="alice-pw1", register=True, side=1, stage="s33", auto_ready=True)
        b = self.c("Bob", password="bob-pw1", register=True, side=1, stage="s33", auto_ready=True)
        with mock.patch.object(casual, "_side_coin", return_value=0):
            room = a.create_room("ranked dojo", ranked=True)
            b.join_room(room["id"])
            sa, sb = expect(a, "match_start", 20), expect(b, "match_start", 20)
        self.assertTrue(sa["ranked"])
        self.assertEqual((sa["role"], sb["role"]), ("host", "join"))       # the server's coin, not the wishes
        self.assertEqual(sa["fight"]["stage"], drawn_stage(sa["seed"]))
        self.assertNotIn("casual", sa)

    def test_community_room_turns_follow_the_line(self):
        # everyone in turn: the first in line goes to the back after the match, also when the wishes made the
        # second in line P1
        self.s.srv.cfg.room_next_seconds = 0.2
        a = self.c("Alice", auto_ready=True)
        b = self.c("Bob", side=0, auto_ready=True)
        c = self.c("Carol", auto_ready=True)
        room = a.create_room("club", size=3, rotation="queue")
        b.join_room(room["id"])
        sa, sb = expect(a, "match_start", 20), expect(b, "match_start", 20)
        self.assertEqual((sa["role"], sb["role"]), ("join", "host"))      # Bob asked for P1
        c.join_room(room["id"])
        rid = room["id"]
        self.finish(a, b, sa)
        line = self.s.call(lambda: [q.name for q in self.s.srv.rooms[rid].line])
        self.assertEqual(line, ["Bob", "Carol", "Alice"])
        sb2, sc2 = expect(b, "match_start", 20), expect(c, "match_start", 20)
        self.assertEqual((sb2["role"], sc2["role"]), ("host", "join"))


class InviteTest(Base):
    def test_casual_invite(self):
        a = self.c("Alice", password="alice-pw1", register=True, stage="s20")
        b = self.c("Bob", password="bob-pw1", register=True, side=0, stage="s20")
        a.add_friend("Bob")
        expect(b, "friend_request")
        b.answer_friend("Alice", True)
        deadline = time.monotonic() + 10
        while "Bob" not in [f["name"] for f in (a.friend_list or {}).get("friends") or ()]:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        r = a.invite("Bob", "casual")
        ev = expect(b, "invited")
        self.assertEqual(ev["wish"], {"side": None, "stage": "s20"})
        b.answer_invite(r["invite"], True)
        sa, sb = expect(a, "match_start", 20), expect(b, "match_start", 20)
        self.assertEqual((sa["role"], sb["role"]), ("join", "host"))
        self.assertEqual(sa["fight"]["stage"], "s20")


# ============================================================================== older launchers and servers
LOBBY = os.path.dirname(util.HERE)
OLD_REF = os.environ.get("T5L_CASUAL_OLD_REF", "v1.1.4")      # the release before casual choices
_OLD = {}
_TMP = []


def _old_tree(test, ref):
    """(client, server) modules of the git revision `ref`, imported once per process under another name."""
    if ref in _OLD:
        return _OLD[ref]
    git = shutil.which("git")
    if not git:
        test.skipTest("no git")
    r = subprocess.run([git, "-C", os.path.dirname(LOBBY), "archive", "--format=tar", ref, "lobby/t5lobby"],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        test.skipTest(f"no {ref} in this checkout")
    tmp = tempfile.mkdtemp(prefix="t5casual-old-")
    _TMP.append(tmp)
    tarfile.open(fileobj=io.BytesIO(r.stdout)).extractall(tmp, filter="data")
    import importlib
    import sys
    sys.path.insert(0, os.path.join(LOBBY, "tools"))
    import natsim
    name = "t5lobby_casualold_" + "".join(ch for ch in ref if ch.isalnum())
    natsim.load_pkg(name, os.path.join(tmp, "lobby", "t5lobby"))
    _OLD[ref] = (importlib.import_module(name + ".client"), importlib.import_module(name + ".server"))
    return _OLD[ref]


def tearDownModule():
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


class OldClientTest(Base):
    def test_a_release_launcher(self):
        oldc, _srv = _old_tree(self, OLD_REF)
        old = oldc.LobbyClient(self.s.addr, BUILD, relay_bridge=False)
        old.connect()
        old.login_guest("Old")
        self.clients.append(old)
        self.assertFalse(hasattr(old, "set_casual_prefs"))      # (it never sends a wish)
        a = self.c("Alice", side=1, stage="s33")
        # the new launcher challenges: the 1.1.4 one gets the challenge (the wish is a field it ignores), its side
        # and the stage in match_found / match_start as always
        sa, so, ev = self.challenge(a, old)
        self.assertEqual((sa["role"], so["role"]), ("join", "host"))
        self.assertEqual(so["ticket"].role, "host")
        self.assertEqual(sa["fight"]["stage"], coin_stage(sa["seed"], fighters.RANDOM, "s33"))
        mid = self.finish(a, old, sa)
        # Swap sides: the old launcher sees an ordinary rematch offer, says yes with its game still connected; the
        # rematch comes over a new session with the sides the other way round
        a.rematch(mid, True, keep=True, swap=True)
        self.assertEqual(expect(old, "rematch")["state"], "offered")
        old.rematch(mid, True, keep=True)
        fo = expect(old, "match_found")
        self.assertEqual((fo["role"], fo["keep"]), ("join", False))
        sa2, so2 = expect(a, "match_start", 20), expect(old, "match_start", 20)
        self.assertEqual((sa2["role"], so2["ticket"].role), ("host", "join"))
        self.finish(a, old, sa2)
        # the old launcher challenges a new one: as before (no wishes on its side)
        b = self.c("Bob")
        sb_old, sb, _ = self.challenge(old, b)
        self.assertEqual((sb_old["role"], sb["role"]), ("host", "join"))
        self.assertEqual(sb["fight"]["stage"], drawn_stage(sb["seed"]))


class OldServerTest(unittest.TestCase):
    def test_new_launchers_on_a_release_server(self):
        _oldc, olds = _old_tree(self, OLD_REF)
        loop = proto.new_event_loop()
        srv = olds.LobbyServer(olds.Config(**util.FAST))
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(srv.start())
            ready.set()
            loop.run_forever()
        th = threading.Thread(target=run, daemon=True)
        th.start()
        clients = []
        try:
            self.assertTrue(ready.wait(10))
            for name in ("Alice", "Bob"):
                c = LobbyClient(f"127.0.0.1:{srv.port}", BUILD, relay_bridge=False)
                c.connect()
                c.login_guest(name)
                clients.append(c)
                self.assertFalse(c.casual_ok())          # the launcher hides its choices
                self.assertEqual(c.casual_stages(), [])
                c.set_casual_prefs(1, "s33")              # (nothing is sent)
            a, b = clients
            cid = a.challenge(b.me["id"])
            expect(b, "challenged")
            b.answer_challenge(cid, accept=True)
            sa, sb = expect(a, "match_start", 30), expect(b, "match_start", 30)
            self.assertEqual((sa["role"], sb["role"]), ("host", "join"))
            self.assertNotIn("casual", sa)
            for c in clients:
                c.report_result(0, [3, 1])
            expect(a, "match_result")
            a.rematch(sa["match"], True, keep=True, swap=True)     # an older server takes it as a rematch
            expect(b, "rematch")
            b.rematch(sa["match"], True, keep=True)
            self.assertEqual(expect(a, "match_found")["role"], "host")
        finally:
            for c in clients:
                c.close()
            asyncio.run_coroutine_threadsafe(srv.stop(), loop).result(10)
            loop.call_soon_threadsafe(loop.stop)
            th.join(10)
            loop.close()


if __name__ == "__main__":
    unittest.main()
