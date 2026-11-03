"""Offline persistence and administrator CLI regressions; never start a lobby or sockets."""
import contextlib
import io
import os
import tempfile
import time
import unittest
from unittest import mock

import util  # noqa: F401 -- adds the lobby import path only
from t5lobby.server import admin
from t5lobby.server.store import PERMANENT, Store


class PersonalMuteStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "lobby.db")
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.alice = self.store.create_account("Alice", "unused")["id"]
        self.bob = self.store.create_account("Bob", "unused")["id"]

    def test_mute_persists_but_does_not_block_or_end_friendship(self):
        self.store.add_friendship(self.alice, self.bob)
        self.assertTrue(self.store.add_mute(self.alice, self.bob, "bogus wire name"))
        self.assertFalse(self.store.add_mute(self.alice, self.bob, "Bob"))
        other = Store(self.path)
        self.addCleanup(other.close)
        self.assertTrue(other.is_muted_by(self.alice, self.bob))
        self.assertEqual(other.mutes_of(self.alice)[0]["muted_name"], "Bob")
        self.assertFalse(other.is_blocked_by(self.alice, self.bob))
        self.assertEqual(other.friend_ids(self.alice), {self.bob})
        self.store.add_block(self.alice, self.bob, "Bob")
        self.assertTrue(other.remove_mute(self.alice, self.bob))
        self.assertTrue(other.is_blocked_by(self.alice, self.bob))
        self.assertEqual(other.friend_ids(self.alice), {self.bob})

    def test_guest_names_persist_case_insensitively_separate_from_accounts(self):
        self.assertTrue(self.store.add_mute(self.alice, None, "Guest Bob"))
        self.assertFalse(self.store.add_mute(self.alice, None, "GUEST BOB"))
        self.assertTrue(self.store.is_muted_by(self.alice, None, "guest bob"))
        self.assertFalse(self.store.is_muted_by(self.alice, self.bob))
        other = Store(self.path)
        self.addCleanup(other.close)
        self.assertEqual(other.mutes_of(self.alice)[0]["muted_id"], None)
        self.assertTrue(other.remove_mute(self.alice, None, "GUEST BOB"))
        self.assertEqual(other.mutes_of(self.alice), [])

    def test_deleted_target_and_owner_leave_no_inherited_mutes(self):
        self.store.add_mute(self.alice, self.bob, "Bob")
        self.store.add_mute(self.alice, None, "Guest Bob")
        self.store.delete_account("Bob")
        self.assertEqual([r["muted_name"] for r in self.store.mutes_of(self.alice)], ["Guest Bob"])
        self.store.delete_account("Alice")
        new_alice = self.store.create_account("Alice", "unused")["id"]
        self.assertEqual(self.store.mutes_of(new_alice), [])
        self.assertEqual(self.store._x("SELECT COUNT(*) FROM personal_mutes").fetchone()[0], 0)

    def test_rollback_reused_account_ids_cannot_inherit_mutes(self):
        self.store.add_mute(self.alice, self.bob, "Bob")
        self.store._x("UPDATE accounts SET created = ? WHERE id = ?", (time.time() + 10, self.bob))
        other = Store(self.path)
        self.addCleanup(other.close)
        self.assertEqual(other.mutes_of(self.alice), [])

    def test_unknown_owners_targets_and_self_are_not_persisted(self):
        self.assertFalse(self.store.add_mute(self.alice + 100, self.bob, "Bob"))
        self.assertFalse(self.store.add_mute(self.alice, self.bob + 100, "Missing"))
        self.assertFalse(self.store.add_mute(self.alice, self.alice, "Alice"))
        for target, name in ((None, ""), (True, "Bob"), (-1, "Bob")):
            with self.assertRaises(ValueError):
                self.store.add_mute(self.alice, target, name)
        self.assertEqual(self.store.mutes_of(self.alice), [])


class AdminMuteCommandTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.alice = self.store.create_account("Alice", "unused")["id"]

    def command(self, argv):
        output = io.StringIO()
        with mock.patch.object(admin, "_open", return_value=self.store), \
                mock.patch.object(self.store, "close"), contextlib.redirect_stdout(output):
            self.assertEqual(admin.main(argv), 0)
        return output.getvalue()

    def test_timed_mute_deadline_and_unmute_are_live_database_state(self):
        with mock.patch.object(admin.time, "time", return_value=1000):
            out = self.command(["mute", "ALICE", "--hours", "2"])
        self.assertIn("all channels", out)
        self.assertEqual(self.store.chat_moderation(self.alice)["muted_until"], 8200)
        self.command(["unmute", "alice"])
        self.assertIsNone(self.store.chat_moderation(self.alice)["muted_until"])
        self.command(["mute", "Alice"])
        self.assertEqual(self.store.chat_moderation(self.alice)["muted_until"], PERMANENT)

    def test_invalid_durations_never_mutate_the_account(self):
        for duration in ("0", "-1", "nan", "inf", "-inf"):
            with self.subTest(duration=duration), self.assertRaises(SystemExit):
                self.command(["mute", "Alice", "--hours=" + duration])
        self.assertIsNone(self.store.chat_moderation(self.alice)["muted_until"])

    def test_filter_counts_include_private_without_storing_message_text(self):
        self.assertTrue(self.store.record_chat_filter(self.alice, "private"))
        self.assertEqual(self.store.chat_moderation(self.alice)["blocked_count"], 1)
        self.assertEqual(self.store.private_reports(), [])


if __name__ == "__main__":
    unittest.main()
