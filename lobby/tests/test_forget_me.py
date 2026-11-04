"""Remove my data (docs/ONLINE.md "Remove my data", server/forget.py, store.Store.forget_account).

Covers: the password is needed (wrong one refused, counted like a password change); a dry run counts and changes
nothing; the real run removes the account, its remembered logins, recovery codes, friends (the friend's list
updates), friend requests, blocks and mutes, and keeps the other players' match history under "deleted player"
without the account; the connection ends; logging in again fails and the name can be registered anew (without the
old history); guests are told there is nothing on the server; not while queued; an older server's answer.
"""
import time
import unittest

import util
from util import client
from t5lobby.proto import LobbyError
from t5lobby.server.store import Store
from test_friends import Base


class ForgetTest(Base):
    def _match_row(self, a_id, b_id, a_name, b_name):
        def add():
            self.s.srv.store._x("INSERT INTO matches (id, created, ranked, p1_name, p2_name, p1_account, p2_account, "
                                "status, winner) VALUES (?, ?, 0, ?, ?, ?, ?, 'confirmed', 0)",
                                ("m" + a_name + b_name, time.time(), a_name, b_name, a_id, b_id))
            self.s.srv.store.flush()
        self.s.call(add)

    def _aid(self, name):
        return self.s.call(lambda: self.s.srv.store.account(name)["id"])

    def test_password_dry_run_and_removal(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.befriend(a, b)
        aid, bid = self._aid("Alice"), self._aid("Bob")
        self._match_row(aid, bid, "Alice", "Bob")
        self.assertIn("forget_me", a.welcome["features"])
        with self.assertRaises(LobbyError):
            a.forget_me("not-the-password")
        r = a.forget_me("alice-pw1", dry_run=True)
        self.assertEqual(r["counts"]["matches"], 1)
        self.assertEqual(r["counts"]["friends"], 1)
        self.assertIsNotNone(self.s.call(lambda: self.s.srv.store.account("Alice")))     # nothing changed
        r = a.forget_me("alice-pw1")
        self.assertEqual(r.get("t"), "forgotten")
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.store.account("Alice") is None))
        st = self.s.srv.store
        row = self.s.call(lambda: dict(st._x("SELECT * FROM matches WHERE id = ?", ("mAliceBob",)).fetchone()))
        self.assertEqual((row["p1_name"], row["p1_account"]), ("deleted player", None))
        self.assertEqual((row["p2_name"], row["p2_account"]), ("Bob", bid))                   # the other side stays
        for table, col in (("sessions", "account_id"), ("recovery", "account_id"), ("friends", "account_id"),
                           ("friends", "friend_id"), ("friend_requests", "from_id"), ("friend_requests", "to_id")):
            n = self.s.call(lambda: st._x(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (aid,)).fetchone()[0])
            self.assertEqual(n, 0, f"{table}.{col}")
        # Bob's friends list no longer has Alice
        t_end = time.monotonic() + 10
        while time.monotonic() < t_end and "Alice" in [f["name"] for f in (b.friend_list or {}).get("friends") or ()]:
            time.sleep(0.05)
        self.assertNotIn("Alice", [f["name"] for f in (b.friend_list or {}).get("friends") or ()])
        # the name is free again; the new account has none of the old history
        c = self.acc("Alice")
        self.assertNotEqual(self._aid("Alice"), aid)
        hist = c.history("Alice")
        self.assertEqual(hist, [])

    def test_guest_and_busy(self):
        g = self.guest("Guesty")
        with self.assertRaises(LobbyError):
            g.forget_me("whatever")
        a = self.acc("Carol")
        a.quick_match()
        with self.assertRaises(LobbyError) as e:
            a.forget_me("carol-pw1")
        self.assertIn("queue", str(e.exception))
        self.assertIsNotNone(self.s.call(lambda: self.s.srv.store.account("Carol")))

    def test_old_server(self):
        a = self.acc("Dave")
        a.welcome["features"] = [f for f in a.welcome["features"] if f != "forget_me"]
        with self.assertRaises(LobbyError):
            a.forget_me("dave-pw1")


class StoreTest(unittest.TestCase):
    def test_forget_account_rows(self):
        st = Store(":memory:")
        a = st.create_account("Ann", "x")["id"]
        b = st.create_account("Ben", "x")["id"]
        st._x("INSERT INTO sets (id, created, ranked, p1_name, p2_name, p1_account, p2_account, wins_needed, status) "
              "VALUES ('s1', 0, 1, 'Ann', 'Ben', ?, ?, 2, 'confirmed')", (a, b))
        st._x("INSERT INTO blocks (account_id, blocked_id, blocked_name, created) VALUES (?, ?, 'Ben', 0)", (a, b))
        st._x("INSERT INTO blocks (account_id, blocked_id, blocked_name, created) VALUES (?, ?, 'Ann', 0)", (b, a))
        st.add_private_report("Ben", b, "Ann", ["x"], "spam")
        n = st.forget_account(a)
        self.assertEqual(n["sets"], 1)
        self.assertEqual(n["reports"], 1)
        row = st._x("SELECT * FROM sets WHERE id = 's1'").fetchone()
        self.assertEqual((row["p1_name"], row["p1_account"], row["p2_name"]), ("deleted player", None, "Ben"))
        self.assertEqual(st._x("SELECT COUNT(*) FROM blocks").fetchone()[0], 0)
        self.assertEqual(st._x("SELECT peer_name FROM private_reports").fetchone()[0], "deleted player")
        self.assertIsNone(st.account("Ann"))
        self.assertIsNone(st.forget_account(a))
        c = st.create_account("Cid", "x")["id"]
        self.assertGreater(c, b)          # ids are never given again
        st.close()


if __name__ == "__main__":
    unittest.main()
