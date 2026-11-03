"""Offline moderation metadata: additive upgrades, durable counts and manual mutes.

These tests do not start a lobby, connect sockets or need game data.
"""
import os
import sqlite3
import tempfile
import time
import unittest

import util  # noqa: F401  (sets sys.path)
from t5lobby.server.store import PERMANENT, SCHEMA, Store


class ChatModerationStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "lobby.db")
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.store.create_account("Alice", "unused-hash")
        self.aid = self.store.account("Alice")["id"]

    def test_counts_persist_without_automatic_bans_or_mutes(self):
        self.assertEqual(self.store.chat_moderation(self.aid), {"blocked_count": 0, "muted_until": None})
        for context in ("chat", "room", "name"):
            self.assertTrue(self.store.record_chat_filter(self.aid, context))
        reopened = Store(self.path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.chat_moderation(self.aid), {"blocked_count": 3, "muted_until": None})
        self.assertIsNone(reopened.ban_state(reopened.account("Alice")))
        self.assertEqual(reopened.list_chat_moderation(), [
            {"id": self.aid, "name": "Alice", "blocked_count": 3, "muted_until": None}])

    def test_admin_mute_is_visible_to_an_already_open_store(self):
        admin = Store(self.path)
        self.addCleanup(admin.close)
        self.assertTrue(admin.mute_account("ALICE", PERMANENT))
        self.assertEqual(self.store.chat_moderation(self.aid)["muted_until"], PERMANENT)
        self.assertEqual(self.store.list_chat_moderation()[0]["blocked_count"], 0)
        self.assertTrue(admin.unmute_account("alice"))
        self.assertIsNone(self.store.chat_moderation(self.aid)["muted_until"])
        self.assertEqual(self.store.list_chat_moderation(), [])
        self.assertTrue(admin.mute_account("Alice", time.time() - 1))
        self.assertEqual(self.store.list_chat_moderation(), [])  # expired mutes are not active
        self.assertFalse(admin.mute_account("Missing", PERMANENT))
        self.assertFalse(admin.unmute_account("Missing"))

    def test_missing_accounts_and_contexts_cannot_create_metadata(self):
        self.assertFalse(self.store.record_chat_filter(None, "chat"))
        self.assertFalse(self.store.record_chat_filter(self.aid + 100, "chat"))
        with self.assertRaises(ValueError):
            self.store.record_chat_filter(self.aid, "arbitrary message content")
        self.assertEqual(self.store.chat_moderation(None), {"blocked_count": 0, "muted_until": None})
        self.assertEqual(self.store.list_chat_moderation(), [])

    def test_deleted_account_does_not_leave_counts_or_mutes(self):
        self.store.record_chat_filter(self.aid, "chat")
        self.store.mute_account("Alice", PERMANENT)
        self.assertTrue(self.store.delete_account("Alice"))
        self.store.create_account("Alice", "unused-hash")
        new_id = self.store.account("Alice")["id"]
        self.assertEqual(self.store.chat_moderation(new_id), {"blocked_count": 0, "muted_until": None})
        self.assertEqual(self.store.list_chat_moderation(), [])

    def test_moderation_listing_is_limited_and_count_ordered(self):
        self.store.create_account("Bob", "unused-hash")
        bob = self.store.account("Bob")["id"]
        self.store.record_chat_filter(self.aid, "room")
        self.store.record_chat_filter(bob, "chat")
        self.store.record_chat_filter(bob, "chat")
        self.assertEqual([r["name"] for r in self.store.list_chat_moderation(limit=1)], ["Bob"])


class ChatModerationUpgradeTest(unittest.TestCase):
    def test_original_schema_gains_zeroed_columns_and_keeps_existing_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "old.db")
            old = sqlite3.connect(path)
            old.executescript(SCHEMA)
            old.execute("INSERT INTO accounts (name, pw, created, rating, rd, vol) "
                        "VALUES ('ExistingName', 'unused', 1, 1500, 350, 0.06)")
            old.commit()
            old.close()
            current = Store(path)
            try:
                row = current.account("ExistingName")
                self.assertEqual(row["name"], "ExistingName")
                self.assertEqual(current.chat_moderation(row["id"]),
                                 {"blocked_count": 0, "muted_until": None})
                current.record_chat_filter(row["id"], "chat")
            finally:
                current.close()
            reopened = Store(path)
            try:
                self.assertEqual(reopened.chat_moderation(row["id"])["blocked_count"], 1)
                self.assertEqual(reopened.account("ExistingName")["name"], "ExistingName")
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
