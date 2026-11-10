"""Win records in the match (1.2.3, server/records.py): match_start's `records` (both players' wins and losses for
the game's PLAYER DATA bar) -- which record, guests, the cap, the players' "Show win records" choice -- and what the
match driver hands the game (T5_HUD_RECORDS, records= on the fight line)."""
import os
import shutil
import tempfile
import time
import types
import unittest

import util
from util import ServerThread, client, expect
from t5lobby import match_driver
from t5lobby.match_driver import MatchDriver, hud_records
from t5lobby.proto import LobbyError
from t5lobby.server import records

from test_driver_persistent import FakeClient, FakeGame, start_event

PW = "secret123"


def counted(n, p1, p2, a1, a2, winner, ranked):
    now = time.time()
    return {"id": f"m{n:012d}", "created": now - 600, "ended": now - 300, "ranked": ranked, "p1_name": p1,
            "p2_name": p2, "p1_account": a1, "p2_account": a2, "status": "confirmed", "winner": winner}


class RecordOfTest(unittest.TestCase):
    def test_kinds(self):
        st = {"ranked": {"games": 5, "wins": 3, "losses": 1, "draws": 1},
              "casual": {"games": 4, "wins": 1, "losses": 3, "draws": 0}}
        self.assertEqual(records.record_of(st, records.KIND_RANKED), [3, 1])
        self.assertEqual(records.record_of(st, records.KIND_ALL), [4, 4])     # draws left out (the bar has none)
        self.assertEqual(records.record_of({}, records.KIND_ALL), [0, 0])


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.s = ServerThread().start()
        from t5lobby.server.ratelimit import KeyedBuckets
        self.s.call(lambda: setattr(self.s.srv, "registrations", KeyedBuckets(rate=100.0, burst=100)))
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name, account=True, **kw):
        kw.setdefault("hud_records", True)
        c = client(self.s, name, password=PW if account else None, register=account, **kw) if account \
            else client(self.s, name, **kw)
        self.clients.append(c)
        return c

    def aid(self, c):
        return self.s.call(lambda: self.s.srv.players[c.me["id"]].account_id)

    def history(self, a, b):
        """Alice: ranked 2-1, casual 1-0 (+ a draw); Bob the other side of those."""
        aa, ab = self.aid(a), self.aid(b)

        def fill():
            st = self.s.srv.store
            st.save_match(counted(1, "Alice", "Bob", aa, ab, 0, True))
            st.save_match(counted(2, "Alice", "Bob", aa, ab, 0, True))
            st.save_match(counted(3, "Bob", "Alice", ab, aa, 0, True))
            st.save_match(counted(4, "Alice", "Bob", aa, ab, 0, False))
            st.save_match(counted(5, "Alice", "Bob", aa, ab, None, False))
            st.save_match(dict(counted(6, "Alice", "Bob", aa, ab, 1, False), status="void"))   # not counted
        self.s.call(fill)

    def challenge(self, a, b):
        cid = a.challenge(b.me["id"])
        expect(b, "challenged")
        b.answer_challenge(cid, accept=True)
        expect(a, "match_found")
        expect(b, "match_found")
        return expect(a, "match_start", 20), expect(b, "match_start", 20)

    def test_casual_match_shows_all_matches(self):
        a, b = self.c("Alice"), self.c("Bob")
        self.assertTrue(a.records_ok())
        self.history(a, b)
        sa, sb = self.challenge(a, b)
        want = {"kind": "all", "sides": [[3, 1], [1, 3]]}           # P1 = the challenger
        self.assertEqual(sa["records"], want)
        self.assertEqual(sb["records"], want)                       # the same list on both PCs
        self.assertEqual(match_driver.hud_records(sa), "3-1|1-3")

    def test_ranked_match_shows_the_ranked_record(self):
        a, b = self.c("Alice"), self.c("Bob")
        self.history(a, b)

        def rec():
            ps = [self.s.srv.players[a.me["id"]], self.s.srv.players[b.me["id"]]]
            return self.s.srv._records(types.SimpleNamespace(id="mx", players=ps, ranked=True))
        self.assertEqual(self.s.call(rec), {"kind": "ranked", "sides": [[2, 1], [1, 2]]})

    def test_guest_has_no_record(self):
        a, g = self.c("Alice"), self.c("Guesty", account=False)
        sa, sg = self.challenge(a, g)
        self.assertEqual(sa["records"], {"kind": "all", "sides": [[0, 0], None]})
        self.assertEqual(sg["records"], sa["records"])
        self.assertEqual(match_driver.hud_records(sg), "0-0|")

    def test_old_client_gets_nothing_and_nobody_does(self):
        a, b = self.c("Alice"), self.c("Bob", hud_records=False)
        self.assertFalse(b.records_ok())
        sa, sb = self.challenge(a, b)
        self.assertNotIn("records", sa)                             # (one game would write nothing: both none)
        self.assertNotIn("records", sb)

    def test_a_player_who_turns_it_off_hides_both(self):
        a, b = self.c("Alice"), self.c("Bob")
        b.set_record_prefs(False)
        pid = b.me["id"]
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.players[pid].record_show is False))
        sa, sb = self.challenge(a, b)
        self.assertNotIn("records", sa)
        self.assertNotIn("records", sb)

    def test_the_choice_comes_back_after_a_new_login(self):
        a = self.c("Alice")
        a.set_record_prefs(False)
        pid = a.me["id"]
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.players[pid].record_show is False))
        a.close()
        c = client(self.s, None, hud_records=True)
        self.clients.append(c)
        c.set_record_prefs(False)                                   # (kept before the login, sent after it)
        c.login("Alice", PW)
        pid = c.me["id"]
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.players[pid].record_show is False))

    def test_bad_requests(self):
        a = self.c("Alice")
        with self.assertRaises(LobbyError):
            a._call({"t": "record_prefs", "show": "yes"})
        b = self.c("Bob", hud_records=False)
        with self.assertRaises(LobbyError):
            b._call({"t": "record_prefs", "show": True})            # (no cap: not this client's message)

    def test_old_server(self):
        from t5lobby.server import lobby as lobby_mod
        orig = lobby_mod.FEATURES
        lobby_mod.FEATURES = [f for f in orig if f != records.FEATURE]
        try:
            a = self.c("Alice")
            self.assertFalse(a.records_ok())
            a.set_record_prefs(False)                               # nothing sent
            time.sleep(0.2)
            self.assertTrue(self.s.call(lambda: self.s.srv.players[a.me["id"]].record_show))
        finally:
            lobby_mod.FEATURES = orig


class DriverTest(unittest.TestCase):
    def test_hud_records(self):
        self.assertIsNone(hud_records({}))
        self.assertIsNone(hud_records({"records": {"sides": [[1, 2]]}}))
        self.assertIsNone(hud_records({"records": {"sides": [[1, -2], [0, 0]]}}))
        self.assertIsNone(hud_records({"records": {"sides": [[True, 2], [0, 0]]}}))
        self.assertIsNone(hud_records({"records": {"sides": ["3-1", [0, 0]]}}))
        self.assertEqual(hud_records({"records": {"sides": [None, [7, 0]]}}), "|7-0")
        self.assertEqual(hud_records({"records": {"sides": [[2000000, 5], None]}}), "999999-5|")

    def test_env_and_fight_line(self):
        d = tempfile.mkdtemp(prefix="drvrec")
        try:
            drv = MatchDriver(FakeClient(), FakeGame, d, mode="process")
            drv.fight_path = os.path.join(d, "fight.txt")
            drv.status_path = os.path.join(d, "status.json")
            ev = start_event()
            self.assertNotIn("T5_HUD_RECORDS", drv.match_env(ev, ev["ticket"]))
            ev["records"] = {"kind": "all", "sides": [[37, 21], None]}
            env = drv.match_env(ev, ev["ticket"])
            self.assertEqual(env["T5_HUD_RECORDS"], "37-21|")
            drv._write_fight_file("9,33,20,3", "m2", ev)
            with open(drv.fight_path) as f:
                line = f.read().strip()
            self.assertEqual(line, "9,33,20,3 names=Al%20Ice|Bob ranks=12|0 records=37-21| match=m2")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_marker(self):
        d = tempfile.mkdtemp(prefix="drvrecm")
        try:
            exe = os.path.join(d, "t5dr.exe")
            with open(exe, "wb") as f:
                f.write(b"\0" * 100 + b"T5_HUD_RANKS\0")
            self.assertFalse(match_driver.game_supports_records([exe]))
            with open(exe, "ab") as f:
                f.write(b"T5_HUD_RECORDS\0")
            self.assertTrue(match_driver.game_supports_records([exe]))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
