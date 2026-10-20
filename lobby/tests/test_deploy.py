"""Updating a running lobby (docs/DEPLOY_1.1.2.md, the 1.1.2 deploy rehearsal):

1. `admin drain --wait` also waits for a ranked set between two of its games (no match runs then, but a restart
   voids the set and the game already won)
2. going back to 1.1.1 after the upgrade, deleting accounts there, then 1.1.2 again: a new account that gets a deleted
   one's id does not inherit its friends or friend requests; the 1.1.1 server opens the upgraded database
3. `admin release X.Y.Z`: launchers of an older release are told to update (a notice they can show), newer ones not
"""
import contextlib
import io
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest

import util
from util import ServerThread, client, expect
from t5lobby.buildid import BuildInfo
from t5lobby.server import admin
from t5lobby.server.store import Store

SETS = {"set_next_seconds": 30.0}        # a long countdown between two games of a set


def run_admin(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            rc = admin.main(list(args))
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (print(e.code) or 1)
    return rc, out.getvalue()


# ============================================================================== 1. drain and ranked sets
class DrainSetTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "t5lobby.db")

    def test_drain_waits_for_a_ranked_set_between_its_games(self):
        s = ServerThread(db=self.db, admin_poll=0.2, status_port=-1, **SETS).start()
        clients = []
        try:
            a = client(s, "Alice", password="pw-Alice", register=True, auto_ready=True, sets=True)
            b = client(s, "Bob", password="pw-Bob", register=True, auto_ready=True, sets=True)
            clients += [a, b]
            a.ranked_match()
            b.ranked_match()
            ea, eb = expect(a, "match_start", 20), expect(b, "match_start", 20)
            w = ea["slot"]
            for c in (a, b):
                c.report_result(w, [3, 1] if w == 0 else [1, 3], match_id=ea["match"], source="game")
            ra = expect(a, "match_result")
            self.assertIn("next", ra["set"])                         # game 1 won; the countdown to game 2 runs
            url = f"http://127.0.0.1:{s.srv.status_http.port}/status"
            res, out = {}, io.StringIO()

            def drain():
                with contextlib.redirect_stdout(out):
                    res["code"] = admin.main(["--db", self.db, "--status-url", url, "drain", "--wait", "25"])
            th = threading.Thread(target=drain)
            th.start()
            self.assertTrue(s.wait_for(lambda: s.srv.draining, 5))
            time.sleep(2.5)
            self.assertEqual(s.call(lambda: s.srv.status()["matches"]["running"]), 0)    # no match runs ...
            self.assertTrue(th.is_alive())                           # ... but the set does: no "restart now"
            self.assertEqual(s.call(lambda: s.srv.store.open_set_count()), 1)
            a.leave_set()                                            # (leaving it loses it: the set is over)
            se = expect(b, "set_end", 10)
            self.assertEqual(se["status"], "forfeit")
            th.join(15)
            self.assertFalse(th.is_alive())
            self.assertEqual(res.get("code"), 0, out.getvalue())
            self.assertIn("1 ranked set(s) not finished", out.getvalue())
            self.assertIn("restart now", out.getvalue())
        finally:
            for c in clients:
                c.close()
            s.stop()

    def test_the_timeout_names_the_sets(self):
        s = ServerThread(db=self.db, admin_poll=0.2, status_port=-1).start()
        try:
            s.call(lambda: s.srv.store.save_set({
                "id": "sx", "created": time.time(), "ended": None, "ranked": True, "p1_name": "A", "p2_name": "B",
                "p1_account": None, "p2_account": None, "wins_needed": 2, "status": "playing", "winner": None,
                "score": [1, 0], "games": [], "rating": None, "reason": None, "blame": None}))
            s.call(lambda: s.srv.store.flush())
            url = f"http://127.0.0.1:{s.srv.status_http.port}/status"
            rc, out = run_admin("--db", self.db, "--status-url", url, "drain", "--wait", "3")
            self.assertEqual(rc, 1)
            self.assertIn("still 0 match(es) running, 1 ranked set(s) not finished", out)
        finally:
            s.stop()


# ============================================================================== 2. back to 1.1.1 and up again
class RollbackTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "t5lobby.db")

    def friends_db(self):
        st = Store(self.db)
        for n in ("Ann", "Ben", "Cat", "Dot"):
            st.create_account(n, "pw-hash")
        ids = {n: st.account(n)["id"] for n in ("Ann", "Ben", "Cat", "Dot")}
        st.add_friendship(ids["Ann"], ids["Ben"])
        st.add_friendship(ids["Ann"], ids["Dot"])
        st.add_friend_request(ids["Ben"], ids["Dot"])
        st.add_friend_request(ids["Cat"], ids["Ann"])
        st.close()
        return ids

    def old_delete_and_register(self, old_store, gone, new_name):
        """What a server without friends tables does: delete accounts (delete-user / purge-inactive), then a new
        player registers -- SQLite gives it the highest deleted id again."""
        st = old_store.Store(self.db)
        for n in gone:
            self.assertTrue(st.delete_account(n))
        time.sleep(0.05)
        st.create_account(new_name, "pw-hash")
        aid = st.account(new_name)["id"]
        st.close()
        return aid

    def check(self, old_store):
        ids = self.friends_db()
        new_id = self.old_delete_and_register(old_store, ["Dot", "Cat"], "Eve")
        self.assertEqual(new_id, ids["Cat"])                          # a deleted account's id, given again
        with self.assertLogs("t5lobby.store", "WARNING"):
            st = Store(self.db)                                       # 1.1.2 again
        self.assertEqual(st.friend_ids(new_id), set())                # Eve has no friends ...
        self.assertEqual(st.friend_ids(ids["Ann"]), {ids["Ben"]})     # ... Ann keeps Ben
        self.assertEqual(st.outgoing_requests(new_id), [])            # nor Cat's request to Ann:
        self.assertEqual(st.incoming_requests(ids["Ann"]), [])        # Ann sees no request from "Eve"
        self.assertEqual(st.outgoing_requests(ids["Ben"]), [])        # Ben's request to Dot went with Dot
        self.assertEqual(st.friend_count(ids["Ann"]), 1)
        st.close()
        st = Store(self.db)                                           # nothing more to drop the next time
        self.assertEqual(st._drop_stale_friends(), 0)
        st.close()

    def test_a_reused_id_does_not_inherit_friends_simulated(self):
        """The old server's account deletion, as 1.1.1 does it (no friends tables known), without git."""
        class OldStore:
            class Store:
                def __init__(self, path):
                    self.db = sqlite3.connect(path, isolation_level=None)
                    self.db.row_factory = sqlite3.Row

                def delete_account(self, name):
                    n = self.db.execute("DELETE FROM accounts WHERE name = ?", (name,)).rowcount
                    for t in ("sessions", "recovery"):
                        self.db.execute(f"DELETE FROM {t} WHERE account_id NOT IN (SELECT id FROM accounts)")
                    return n == 1

                def create_account(self, name, pw_hash):
                    self.db.execute("INSERT INTO accounts (name, pw, created, rating, rd, vol) VALUES "
                                    "(?, ?, ?, 1500, 350, 0.06)", (name, pw_hash, time.time()))

                def account(self, name):
                    return self.db.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()

                def close(self):
                    self.db.close()
        self.check(OldStore)

    def test_a_reused_id_does_not_inherit_friends_with_the_v111_server(self):
        from test_friends import _old_tree
        _c, _s, old_store = _old_tree(self, "v1.1.1")
        self.check(old_store)

    def test_the_v111_server_opens_an_upgraded_database(self):
        from test_friends import _old_tree
        _c, _s, old_store = _old_tree(self, "v1.1.1")
        ids = self.friends_db()
        st = old_store.Store(self.db)
        self.assertEqual(st.account("Ann")["id"], ids["Ann"])
        st.close()
        st = Store(self.db)
        self.assertEqual(st.schema_version(), 1)
        self.assertEqual(st.friend_ids(ids["Ann"]), {ids["Ben"], ids["Dot"]})   # untouched by the old server
        st.close()


class AccountIdTest(unittest.TestCase):
    """A deleted account's id is never given to a new account (everything is stored by account id: history, pair
    counts, friends, blocks, tournament entries, a tournament's organizer)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "t5lobby.db")

    def test_the_newest_accounts_id_is_not_given_again(self):
        st = Store(self.db)
        for n in ("Ann", "Ben", "Cat"):
            st.create_account(n, "pw-hash")
        cat = st.account("Cat")["id"]
        self.assertTrue(st.delete_account("Cat"))
        self.assertEqual(st.create_account("Dot", "pw-hash")["id"], cat + 1)
        st.close()
        st = Store(self.db)                                           # (kept in the database: also after a restart)
        self.assertTrue(st.delete_account("Dot"))
        self.assertEqual(st.create_account("Eve", "pw-hash")["id"], cat + 2)
        st.close()

    def test_purge_inactive_too(self):
        st = Store(self.db)
        for n in ("Ann", "Ben"):
            st.create_account(n, "pw-hash")
        ben = st.account("Ben")["id"]
        st.db.execute("UPDATE accounts SET created = 1, last_seen = NULL WHERE name = 'Ben'")
        self.assertEqual(st.purge_inactive_accounts(30), 1)
        self.assertEqual(st.create_account("Cid", "pw-hash")["id"], ben + 1)
        st.close()

    def test_without_deletions_ids_are_as_before(self):
        st = Store(self.db)
        ids = [st.create_account(n, "pw-hash")["id"] for n in ("Ann", "Ben", "Cat")]
        self.assertEqual(ids, [1, 2, 3])
        self.assertIsNone(st.create_account("ann", "pw-hash"))         # (the name rule is unchanged)
        st.close()

    def test_a_deleted_organizers_tournament_is_not_run_by_a_newcomer(self):
        from t5lobby.server import tournaments
        st = Store(self.db)
        org = st.create_account("Org", "pw-hash")["id"]
        tournaments.migrate(st.db)
        st.db.execute("INSERT INTO tournaments (id, name, organizer_id, organizer_name, format, set_wins, max_players, "
                      "start_time, seeding, state, created, seed) VALUES ('t1', 'Cup', ?, 'Org', 'single', 2, 8, ?, "
                      "'random', 'signup', ?, 1)", (org, time.time() + 600, time.time()))
        st.delete_account("Org")
        new = st.create_account("Newcomer", "pw-hash")["id"]
        self.assertNotEqual(new, org)
        st.close()


# ============================================================================== 3. "update your launcher"
def build(release):
    return BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "code-" + release, release)


class ReleaseNoticeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, "t5lobby.db")
        self.s = ServerThread(db=self.db, admin_poll=0.2).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name, release):
        c = client(self.s, name, build=build(release))
        self.clients.append(c)
        return c

    def updates(self, c, timeout=1.0):
        out = []
        while True:
            ev = c.next_event(timeout, ("server_notice", "notice"))
            if ev is None:
                return out
            out.append(ev)
            timeout = 0.2

    def test_older_launchers_are_told_newer_ones_not(self):
        old, new, dev, older = self.c("Old", "1.1.1"), self.c("New", "1.1.2"), self.c("Dev", "dev"), self.c("Ancient", "1.0.0")
        self.assertEqual(self.updates(old, 0.5), [])                  # nothing before the owner says so
        rc, out = run_admin("--db", self.db, "release", "1.1.2")
        self.assertEqual(rc, 0, out)
        ev = expect(old, "server_notice", 5)
        self.assertEqual((ev["id"], ev["cleared"], ev["expires"]), (-1, False, 0))
        self.assertIn("T5DR Online 1.1.2 is out", ev["text"])
        self.assertIn("your 1.1.1", ev["text"])
        self.assertLessEqual(len(ev["text"]), 200)
        self.assertEqual(old.active_notices(), [ev["text"]])
        self.assertIn("1.1.2 is out", expect(older, "server_notice", 5)["text"])
        self.assertEqual(self.updates(new), [])
        self.assertEqual(self.updates(dev), [])
        late = self.c("Late", "1.1.1")                                # at login too
        self.assertIn("1.1.2 is out", expect(late, "server_notice", 5)["text"])
        # with an admin notice beside it: the launcher sorts its notices by id (the update notice is -1)
        run_admin("--db", self.db, "notice", "maintenance at noon")
        expect(old, "server_notice", 5)
        self.assertEqual(old.active_notices()[1], "maintenance at noon")
        run_admin("--db", self.db, "release", "--clear")
        ev = expect(old, "server_notice", 5)
        self.assertEqual((ev["id"], ev["cleared"]), (-1, True))
        self.assertEqual(old.active_notices(), ["maintenance at noon"])

    def test_a_launcher_without_server_notices_gets_a_plain_notice(self):
        old = self.c("Old", "1.1.1")
        self.s.call(lambda: setattr(self.s.srv.by_name["old"].conn, "caps", frozenset()))
        run_admin("--db", self.db, "release", "1.1.2")
        ev = expect(old, "notice", 5)
        self.assertEqual(ev["code"], "update")
        self.assertIn("1.1.2 is out", ev["msg"])
        run_admin("--db", self.db, "release", "--clear")
        self.assertEqual(self.updates(old), [])                       # (nothing to take down)

    def test_it_survives_a_restart_and_is_refused_for_a_non_release(self):
        rc, out = run_admin("--db", self.db, "release", "dev")
        self.assertNotEqual(rc, 0)
        self.assertIn("not a release number", out)
        run_admin("--db", self.db, "release", "v1.1.2")
        rc, out = run_admin("--db", self.db, "release")
        self.assertIn("newest release: 1.1.2", out)
        self.s.stop()
        self.s = ServerThread(db=self.db, admin_poll=0.2).start()
        old = self.c("Old", "1.1.1")
        self.assertIn("1.1.2 is out", expect(old, "server_notice", 5)["text"])

    def test_release_numbers(self):
        key = __import__("t5lobby.server.lobby", fromlist=["LobbyServer"]).LobbyServer.release_key
        self.assertLess(key("1.1.1"), key("1.1.2"))
        self.assertLess(key("1.1.9"), key("1.1.10"))
        self.assertEqual(key("v1.1.2-rc1"), key("1.1.2"))
        self.assertEqual(key("1.1"), key("1.1.0"))
        for bad in ("dev", "", None, "1.a", "1.2.3.4.5", "test-other"):
            self.assertIsNone(key(bad))


if __name__ == "__main__":
    unittest.main()
