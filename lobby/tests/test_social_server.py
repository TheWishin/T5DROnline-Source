"""1.2.0 badges/mentions: handlers, SQLite and fake connections only; no listener or game.

Run with PYTHONPATH=lobby: python -m unittest discover -s lobby/tests -p test_social_server.py
"""
import contextlib
import io
import os
import sqlite3
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto
from t5lobby.server import admin, store as store_mod
from t5lobby.server.lobby import Conn, LobbyServer, Player, _chat_mentions
from t5lobby.server.ratelimit import KeyedBuckets, TokenBucket
from t5lobby.server.store import Store


class FakeConn:
    send = Conn.send

    def __init__(self, caps=()):
        self.caps = frozenset(caps)
        self.build_id, self.release = "test", "1.2.0"
        self.ip, self.akey = "127.0.0.1", str(id(self))
        self.closed, self.need_full, self.errors = False, True, 0
        self.messages = []

    def send_raw(self, data):
        self.messages.append(proto.decode(data))


class SocialServerTest(unittest.TestCase):
    def setUp(self):
        # Accidental network use in these tests must fail before a socket is opened.
        self.socket_patch = mock.patch("socket.socket", side_effect=AssertionError("no sockets in unit tests"))
        self.socket_patch.start()
        self.addCleanup(self.socket_patch.stop)
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.srv = object.__new__(LobbyServer)
        self.srv.store = self.store
        self.srv.players, self.srv.queues = {}, {"quick": [], "ranked": []}
        self.srv._last_lobby = None
        self.srv._spec_refresh_rooms = lambda: None
        self.srv._room_lists = lambda: ({}, {})
        self.srv._can_private = lambda c: "private_rooms" in c.caps
        self.srv.chat_rate = KeyedBuckets(rate=0, burst=5)
        self.srv.chat_total = TokenBucket(rate=0, burst=1000)
        self.srv.counters = {"chat_lines": 0}
        self.srv.dirty = False

    def player(self, name, caps=("badges", "mentions", "delta"), account=None, guest=True):
        c = FakeConn(caps)
        p = Player(c, name, guest, account)
        c.player = p
        self.srv.players[p.id] = p
        return p

    def account(self, name="Case Tester", badge=""):
        row = self.store.create_account(name, "not-a-real-password-hash")
        self.store.set_badge(row["id"], badge)
        return self.store.account(name)

    def say(self, p, text, **extra):
        # A fresh coroutine loop, without socket-based asyncio event-loop setup.
        coro = self.srv.h_chat(p.conn, dict(extra, text=text))
        try:
            coro.send(None)
        except StopIteration as result:
            return result.value
        self.fail("h_chat unexpectedly waited for I/O")

    def test_schema_one_upgrade_keeps_accounts_and_runs_once(self):
        with mock.patch.object(store_mod, "MIGRATIONS", store_mod.MIGRATIONS[:1]):
            old = Store(":memory:")
        self.addCleanup(old.close)
        row = old.create_account("Before Upgrade", "unchanged-hash")
        self.assertNotIn("badge", row.keys())
        self.assertEqual(old._migrate(), [2])
        self.assertEqual(old.schema_version(), 2)
        row = old.account("Before Upgrade")
        self.assertEqual((row["pw"], row["badge"]), ("unchanged-hash", ""))
        old.set_badge(row["id"], "dev")
        self.assertEqual(old._migrate(), [])
        self.assertEqual(old.account("Before Upgrade")["badge"], "dev")
        with self.assertRaises(sqlite3.IntegrityError):
            old.db.execute("UPDATE accounts SET badge = 'admin'")
        with self.assertRaises(ValueError):
            old.set_badge(row["id"], "admin")

    def test_admin_command_grants_and_clears_case_insensitively(self):
        row = self.account()
        with mock.patch.object(admin, "_open", return_value=self.store), \
                mock.patch.object(self.store, "close"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(admin.main(["badge", "case tester", "dev"]), 0)
            self.assertEqual(self.store.account_by_id(row["id"])["badge"], "dev")
            self.assertEqual(admin.main(["badge", "CASE TESTER", "--clear"]), 0)
            self.assertEqual(self.store.account_by_id(row["id"])["badge"], "")
            for args in (["badge", "Case Tester"], ["badge", "Case Tester", "dev", "--clear"],
                         ["badge", "Missing", "dev"]):
                with self.assertRaises(SystemExit):
                    admin.main(args)

    def test_badge_is_stored_account_metadata_and_admin_poll_refreshes_it(self):
        row = self.account(badge="dev")
        p = self.player(row["name"], account=row, guest=False)
        guest = self.player("Guest Name", account=row)  # even a mismatched constructor cannot badge a guest
        self.assertEqual((p.public()["badge"], p.brief()["badge"], guest.badge), ("dev", "dev", ""))
        self.assertFalse(hasattr(self.srv, "h_badge"))
        self.srv.tours = SimpleNamespace(handler=lambda _t: None)
        coro = self.srv._dispatch(p.conn, proto.encode({"t": "badge", "badge": "dev", "rid": 1}))
        with self.assertRaises(StopIteration):
            coro.send(None)
        self.assertEqual(p.conn.messages[-1]["code"], proto.E_BAD_REQUEST)
        self.store.set_badge(row["id"], "")
        self.srv.poll_badges()
        self.assertEqual(p.badge, "")
        self.assertTrue(self.srv.dirty)
        self.store.set_badge(row["id"], "dev")
        self.srv.poll_badges()
        self.assertEqual((p.badge, guest.badge), ("dev", ""))
        # An account logging in again receives the stored metadata, independent of its old Player.
        fresh = self.player(row["name"], account=self.store.account_by_id(row["id"]), guest=False)
        self.assertEqual(fresh.badge, "dev")

    def test_roster_full_delta_nested_room_and_direct_reply_are_cap_gated(self):
        row = self.account(badge="dev")
        owner = self.player(row["name"], account=row, guest=False)
        legacy = self.player("Legacy", caps=())
        delta_old = self.player("Delta Old", caps=("delta",))
        rooms = {"room": {"id": "room", "owner": owner.brief()}}
        self.srv._room_lists = lambda: (rooms, rooms)
        for p in (owner, legacy, delta_old):
            snap = self.srv._snapshot(full=True, conn=p.conn)
            expected = "badges" in p.conn.caps
            self.assertEqual("badge" in snap["players"][0], expected)
            self.assertEqual("badge" in snap["rooms"][0]["owner"], expected)
            p.conn.send({"t": "login_ok", "you": owner.public()})
            self.assertEqual("badge" in p.conn.messages[-1]["you"], expected)
        self.srv._broadcast_lobby()
        self.assertEqual(owner.conn.messages[-1]["players"][0]["badge"], "dev")
        for p in (legacy, delta_old):
            self.assertNotIn("badge", p.conn.messages[-1]["players"][0])
            self.assertNotIn("badge", p.conn.messages[-1]["rooms"][0]["owner"])
        owner.badge = ""
        self.srv._broadcast_lobby()
        self.assertEqual(owner.conn.messages[-1]["t"], "lobby_delta")
        self.assertEqual(owner.conn.messages[-1]["players"][0]["badge"], "")
        self.assertNotIn("badge", delta_old.conn.messages[-1]["players"][0])

    def test_mentions_use_online_names_case_insensitively_longest_first(self):
        short = self.player("Rival")
        long = self.player("Rival Main")
        punct = self.player("[Ace] (UK)!")
        offline = self.player("Offline")
        offline.conn = None
        text = "@rival main, @RIVAL. @[ace] (uk)! @Rival @Offline @Nobody"
        self.assertEqual(_chat_mentions(text, self.srv.players.values()), [long.id, short.id, punct.id])
        for text in ("mail@Rival", "@@Rival", "@Rival_more", "@Rival.more", "é@Rival", "@Rivalé", "@Rival-Extra"):
            with self.subTest(text=text):
                self.assertEqual(_chat_mentions(text, self.srv.players.values()), [])
        offline.conn = FakeConn()
        self.assertEqual(_chat_mentions("@Offline", self.srv.players.values()), [offline.id])

    def test_chat_ignores_forged_identity_and_targets_and_preserves_legacy_shape(self):
        row = self.account(badge="dev")
        sender = self.player(row["name"], account=row, guest=False)
        target = self.player("Rival")
        legacy = self.player("Older", caps=())
        only_mentions = self.player("Pings Only", caps=("mentions",))
        only_badges = self.player("Badges Only", caps=("badges",))
        self.say(sender, "hi @\x00Rival", badge="admin", mentions=[legacy.id],
                 **{"from": {"name": "Fake", "badge": "admin"}})
        msg = target.conn.messages[-1]
        self.assertEqual(msg["text"], "hi @Rival")
        self.assertEqual(msg["mentions"], [target.id])
        self.assertEqual((msg["from"]["name"], msg["from"]["badge"]), (sender.name, "dev"))
        old = legacy.conn.messages[-1]
        self.assertEqual(set(old), {"t", "from", "text", "time"})
        self.assertNotIn("badge", old["from"])
        self.assertEqual(only_mentions.conn.messages[-1]["mentions"], [target.id])
        self.assertNotIn("badge", only_mentions.conn.messages[-1]["from"])
        self.assertNotIn("mentions", only_badges.conn.messages[-1])
        self.assertEqual(only_badges.conn.messages[-1]["from"]["badge"], "dev")
        # Typing @name from an older sender can still ping a newer recipient.
        self.say(legacy, "@Rival", badge="dev")
        self.assertEqual(target.conn.messages[-1]["mentions"], [target.id])
        self.assertEqual(target.conn.messages[-1]["from"]["badge"], "")

    def test_mentions_share_chat_player_address_and_global_limits(self):
        sender, target = self.player("Sender"), self.player("Rival")
        for _ in range(5):
            self.say(sender, "@Rival")
        before = len(target.conn.messages)
        with self.assertRaises(proto.LobbyError) as caught:
            self.say(sender, "@Rival")
        self.assertEqual(caught.exception.code, proto.E_RATE)
        self.assertEqual(len(target.conn.messages), before)
        # A different player on an address with no chat budget cannot bypass it with a ping.
        other = self.player("Other Sender")
        self.srv.chat_rate.b["addr:" + other.conn.akey] = TokenBucket(rate=0, burst=0)
        with self.assertRaises(proto.LobbyError):
            self.say(other, "@Rival")
        other.conn.akey = "fresh-address"
        self.srv.chat_total = TokenBucket(rate=0, burst=0)
        with self.assertRaises(proto.LobbyError):
            self.say(other, "@Rival")
        self.assertEqual(len(target.conn.messages), before)

    def test_chat_truncation_and_offline_names_cannot_create_pings(self):
        sender, target = self.player("Sender"), self.player("Rival")
        self.say(sender, "x" * 200 + " @Rival", mentions=[target.id])
        self.assertEqual(target.conn.messages[-1]["mentions"], [])
        target.conn = None
        self.say(sender, "@Rival", mentions=[target.id])
        self.assertEqual(sender.conn.messages[-1]["mentions"], [])


if __name__ == "__main__":
    unittest.main()
