"""Local database-only moderation admin regressions; no server or game required."""
import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import util
from t5lobby.server import admin
from t5lobby.server.store import PERMANENT, Store


class ChatFilterAdminTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "lobby.db")
        st = Store(self.db)
        self.alice = st.create_account("Alice", "unused-password-hash")["id"]
        self.legacy = st.create_account("LegacyHate", "unchanged-password-hash")["id"]
        st.close()

    def run_admin(self, *args):
        output = io.StringIO()
        # Database-only commands must never query even the local status endpoint.
        with patch.object(admin, "_fetch", side_effect=AssertionError("unexpected network access")), \
                contextlib.redirect_stdout(output):
            try:
                rc = admin.main(["--db", self.db, *args])
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
                if not isinstance(e.code, int):
                    print(e.code)
        return rc, output.getvalue()

    def moderation(self):
        st = Store(self.db)
        try:
            return st.chat_moderation(self.alice)
        finally:
            st.close()

    def test_counts_are_visible_without_message_text_or_automatic_ban(self):
        st = Store(self.db)
        st.record_chat_filter(self.alice, "chat")
        st.record_chat_filter(self.alice, "room")
        st.close()
        rc, output = self.run_admin("chat-counts")
        self.assertEqual(rc, 0, output)
        self.assertIn("Alice", output)
        self.assertRegex(output, r"Alice\s+2\s+-")
        self.assertNotIn("LegacyHate", output)
        self.assertIn("no automatic ban", output)
        st = Store(self.db)
        try:
            self.assertIsNone(st.ban_state(st.account("Alice")))
        finally:
            st.close()

    def test_mute_duration_and_unmute_leave_account_usable_and_count_intact(self):
        st = Store(self.db)
        st.record_chat_filter(self.alice, "chat")
        st.close()
        start = time.time()
        rc, output = self.run_admin("mute", "alice", "--hours", "2")
        self.assertEqual(rc, 0, output)
        m = self.moderation()
        self.assertGreaterEqual(m["muted_until"], start + 7200)
        self.assertLess(m["muted_until"], time.time() + 7201)
        self.assertEqual(m["blocked_count"], 1)
        rc, output = self.run_admin("unmute", "ALICE")
        self.assertEqual(rc, 0, output)
        self.assertFalse(self.moderation()["muted_until"])
        self.assertEqual(self.moderation()["blocked_count"], 1)
        st = Store(self.db)
        try:
            self.assertIsNone(st.ban_state(st.account("Alice")))
            self.assertEqual(st.account("Alice")["pw"], "unused-password-hash")
        finally:
            st.close()

    def test_permanent_mute_is_visible_even_without_blocked_attempts(self):
        rc, output = self.run_admin("mute", "Alice")
        self.assertEqual(rc, 0, output)
        self.assertEqual(self.moderation()["muted_until"], PERMANENT)
        rc, output = self.run_admin("chat-counts", "--limit", "1")
        self.assertEqual(rc, 0, output)
        self.assertIn("Alice", output)
        self.assertIn("for good", output)

    def test_invalid_durations_and_unknown_accounts_do_not_set_mutes(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value):
                rc, _output = self.run_admin("mute", "Alice", "--hours", value)
                self.assertNotEqual(rc, 0)
                self.assertFalse(self.moderation()["muted_until"])
        for command in ("mute", "unmute"):
            rc, output = self.run_admin(command, "Nobody")
            self.assertNotEqual(rc, 0)
            self.assertIn("no account", output)
        rc, _output = self.run_admin("chat-counts", "--limit", "0")
        self.assertNotEqual(rc, 0)

    def test_flagged_names_reports_every_matching_existing_name_without_changes(self):
        terms = os.path.join(self.temp.name, "terms.json")
        with open(terms, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "terms": [{"term": "legacyhate", "languages": ["en"]}]}, f)
        st = Store(self.db)
        before = dict(st.account("LegacyHate"))
        st.close()
        # Explicit review remains available while the server filter is switched off.
        with patch.dict(os.environ, {"T5L_CHAT_FILTER_PATH": terms, "T5L_CHAT_FILTER": "0"}):
            rc, output = self.run_admin("flagged-names")
        self.assertEqual(rc, 0, output)
        self.assertIn(f"LegacyHate (id {self.legacy})", output)
        self.assertNotIn("Alice", output)
        self.assertIn("1 flagged", output)
        st = Store(self.db)
        try:
            self.assertEqual(dict(st.account("LegacyHate")), before)
            self.assertEqual(st.chat_moderation(self.legacy)["blocked_count"], 0)
        finally:
            st.close()

    def test_flagged_names_accepts_explicit_term_path_and_rejects_missing_list(self):
        terms = os.path.join(self.temp.name, "terms.json")
        with open(terms, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "terms": [{"term": "alice", "languages": ["en"]}]}, f)
        rc, output = self.run_admin("flagged-names", "--terms", terms)
        self.assertEqual(rc, 0, output)
        self.assertIn("Alice", output)
        self.assertNotIn("LegacyHate", output)
        rc, output = self.run_admin("flagged-names", "--terms", terms + ".missing")
        self.assertNotEqual(rc, 0)
        self.assertIn("cannot load hate-term list", output)


if __name__ == "__main__":
    unittest.main()
