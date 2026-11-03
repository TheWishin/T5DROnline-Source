"""Ranked per-character profiles (1.2.0), without sockets, a game or a running server."""
import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import util
from t5lobby import fighters, proto, ranks
from t5lobby.compatibility import BuildGroups
from t5lobby.server.config import Config
from t5lobby.server.lobby import CAPS, FEATURES, LobbyServer
from t5lobby.server.store import SCHEMA_VERSION, Store


def match(st, n, a, b, c1="jin", c2="law", winner=0, ranked=True, status="confirmed", **kw):
    m = {"id": f"m{n:012d}", "created": 1_800_000_000.0 + n, "ended": 1_800_000_060.0 + n,
         "ranked": ranked, "p1_name": "Alice", "p2_name": "Bob", "p1_account": a, "p2_account": b,
         "p1_char": c1, "p2_char": c2, "winner": winner, "status": status}
    m.update(kw)
    st.save_match(m)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.st = Store(":memory:")
        self.addCleanup(self.st.close)
        self.a = self.st.create_account("Alice", "x")["id"]
        self.b = self.st.create_account("Bob", "x")["id"]

    def test_ranked_only_all_outcomes_and_counted_statuses(self):
        for n, (status, winner) in enumerate((("confirmed", 0), ("onesided", 1),
                                                ("forfeit", 0), ("resolved", None)), 1):
            match(self.st, n, self.a, self.b, winner=winner, status=status)
        for n, status in enumerate(("void", "playing", "disputed", "pending"), 10):
            match(self.st, n, self.a, self.b, status=status)
        match(self.st, 20, self.a, self.b, ranked=False)
        match(self.st, 21, self.a, self.b, c1=None)
        match(self.st, 22, self.a, self.b, c1="")
        self.assertEqual(self.st.ranked_chars(self.a), [
            {"char": "jin", "games": 4, "wins": 2, "losses": 1, "draws": 1, "win_rate": 50.0}])
        self.assertEqual(self.st.ranked_chars(99999), [])

    def test_mirror_counts_only_each_accounts_own_side(self):
        match(self.st, 1, self.a, self.b, c2="jin", winner=0)
        a, b = self.st.ranked_chars(self.a)[0], self.st.ranked_chars(self.b)[0]
        self.assertEqual((a["games"], a["wins"], a["losses"]), (1, 1, 0))
        self.assertEqual((b["games"], b["wins"], b["losses"]), (1, 0, 1))
        match(self.st, 2, self.b, self.a, c1="jin", c2="jin", winner=None)
        for aid in (self.a, self.b):
            row = self.st.ranked_chars(aid)[0]
            self.assertEqual((row["games"], row["draws"]), (2, 1))

    def test_all_fighters_deterministic_order_and_win_rate_rounding(self):
        chars = ("asuka", "bryan", "feng", "hwoarang", "jin", "law", "lili")
        for n, ch in enumerate(reversed(chars), 1):
            match(self.st, n, self.a, self.b, c1=ch)
        # P2's reported fighter belongs to the account on P2; 1/3 = 33.33% (draws included).
        match(self.st, 20, self.b, self.a, c2="jin", winner=0)
        match(self.st, 21, self.b, self.a, c2="jin", winner=None)
        rows = self.st.ranked_chars(self.a)
        self.assertEqual(len(rows), 7)
        self.assertEqual([r["char"] for r in rows], ["jin", *[c for c in chars if c != "jin"]])
        self.assertEqual(rows[0], {"char": "jin", "games": 3, "wins": 1, "losses": 1, "draws": 1,
                                   "win_rate": 33.33})

    def test_ties_use_wins_then_character_even_for_draw_only_fighters(self):
        match(self.st, 1, self.a, self.b, c1="yoshimitsu", winner=0)
        match(self.st, 2, self.a, self.b, c1="asuka", winner=None)
        match(self.st, 3, self.a, self.b, c1="bryan", winner=1)
        self.assertEqual([r["char"] for r in self.st.ranked_chars(self.a)], ["yoshimitsu", "asuka", "bryan"])

    def test_sets_count_games_like_leaderboard_and_do_not_change_account_rank(self):
        self.st.db.execute("UPDATE accounts SET ranked_games = 1 WHERE id = ?", (self.a,))
        before = dict(self.st.account_by_id(self.a))
        for n, winner in enumerate((0, 1, 0), 1):
            match(self.st, n, self.a, self.b, winner=winner, set_id="s123", set_game=n)
        # A voided replay belongs to the set's history but is not a counted game.
        match(self.st, 4, self.a, self.b, status="void", set_id="s123", set_game=2)
        row = self.st.ranked_chars(self.a)[0]
        self.assertEqual((row["games"], row["wins"], row["losses"]), (3, 2, 1))
        self.assertEqual({k: row[k] for k in ("games", "wins", "losses", "draws")},
                         self.st.match_stats(self.a)["ranked"])
        board = self.st.leaderboard()[0]
        self.assertEqual((board["ranked_games"], board["ranked_wins"], board["ranked_losses"]), (1, 2, 1))
        self.assertEqual(dict(self.st.account_by_id(self.a)), before)

    def test_old_stored_history_counts_after_reopen_without_schema_change(self):
        with tempfile.TemporaryDirectory(dir=util.HERE) as folder:
            path = os.path.join(folder, "history.db")
            st = Store(path)
            a = st.create_account("Alice", "x")["id"]
            b = st.create_account("Bob", "x")["id"]
            # The existing schema already stores these fields; insert an old row directly,
            # without calling any new statistics helper or making an aggregate table.
            st.db.execute("INSERT INTO matches (id, created, ranked, p1_account, p2_account, "
                          "p1_char, p2_char, status, winner) VALUES ('old', 1, 1, ?, ?, 'jin', 'law', "
                          "'confirmed', 0)", (a, b))
            schema = list(st.db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name"))
            schema = [tuple(r) for r in schema]
            version = st.db.execute("PRAGMA user_version").fetchone()[0]
            st.close()
            st = Store(path)
            try:
                self.assertEqual(st.ranked_chars(a), [{"char": "jin", "games": 1, "wins": 1, "losses": 0,
                                                       "draws": 0, "win_rate": 100.0}])
                self.assertEqual(st.db.execute("PRAGMA user_version").fetchone()[0], version)
                self.assertEqual(version, SCHEMA_VERSION)
                self.assertEqual([tuple(r) for r in st.db.execute(
                    "SELECT type, name, sql FROM sqlite_master ORDER BY type, name")], schema)
            finally:
                st.close()


class ProfileTest(unittest.TestCase):
    def setUp(self):
        # Use the actual handler and store without constructing networking services.
        self.srv = LobbyServer.__new__(LobbyServer)
        self.srv.store = Store(":memory:")
        self.addCleanup(self.srv.store.close)
        self.srv.by_name = {}
        self.srv.rules = ranks.RankRules()
        self.a = self.srv.store.create_account("Alice", "x")["id"]
        self.b = self.srv.store.create_account("Bob", "x")["id"]
        self.me = SimpleNamespace(name="Viewer", account_id=None, friends=set())

    def profile(self, name, caps):
        conn = SimpleNamespace(player=self.me, caps=frozenset(caps))
        return asyncio.run(self.srv.h_profile(conn, {"name": name, "history": 0}))["profile"]

    def test_field_is_cap_gated_and_history_limit_does_not_limit_fighters(self):
        self.assertIn("ranked_chars", CAPS)
        self.assertIn("ranked_chars", FEATURES)
        match(self.srv.store, 1, self.a, self.b)
        with patch.object(self.srv.store, "ranked_chars", wraps=self.srv.store.ranked_chars) as query:
            old = self.profile("Alice", [])
            self.assertNotIn("ranked_chars", old)
            query.assert_not_called()
            new = self.profile("Alice", ["ranked_chars"])
            query.assert_called_once_with(self.a)
        self.assertEqual(new.pop("ranked_chars"), [{"char": "jin", "games": 1, "wins": 1, "losses": 0,
                                                    "draws": 0, "win_rate": 100.0}])
        self.assertEqual(new, old)
        self.assertEqual(new["history"], [])

    def test_empty_account_and_guest(self):
        self.assertEqual(self.profile("Alice", ["ranked_chars"])["ranked_chars"], [])
        self.srv.by_name["guest7"] = SimpleNamespace(public=lambda: {"name": "Guest7", "guest": True},
                                                     online=True)
        self.assertNotIn("ranked_chars", self.profile("Guest7", []))
        self.assertEqual(self.profile("Guest7", ["ranked_chars"])["ranked_chars"], [])

    def test_hello_negotiates_cap_without_opening_a_socket(self):
        self.srv.cfg = Config()
        # __new__ bypasses the server constructor, including its compatibility policy.
        self.srv.build_groups = BuildGroups(self.srv.cfg.compat_groups)
        self.srv.table = fighters.table()
        self.srv.udp = SimpleNamespace(port=0, port2=0)
        self.srv.latest_release = ""
        self.srv.release_cache = SimpleNamespace(public=lambda _: None)
        conn = SimpleNamespace(player=None, ip="127.0.0.1",
                               writer=SimpleNamespace(get_extra_info=lambda key: None))
        welcome = asyncio.run(self.srv.h_hello(conn, {
            "proto": proto.PROTO_VERSION, "build": util.BUILD.as_wire(), "caps": ["ranked_chars", "unknown"]}))
        self.assertEqual(welcome["caps"], ["ranked_chars"])
        self.assertIn("ranked_chars", welcome["features"])
        self.assertEqual(conn.caps, frozenset(("ranked_chars",)))
        self.assertEqual(conn.compat_group, "")
        self.assertEqual(welcome["compat_group"], "")


if __name__ == "__main__":
    unittest.main()
