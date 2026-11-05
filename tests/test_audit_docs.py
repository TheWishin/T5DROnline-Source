"""Read-only deployment and renderer-limit documentation contracts; no game imports."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AuditDocumentation(unittest.TestCase):
    def test_combined_deployment_covers_default_enabled_private_reports(self):
        config = (ROOT / "lobby/t5lobby/server/config.py").read_text(encoding="utf-8")
        self.assertRegex(config, r"private_chat:\s*bool\s*=\s*True")
        store = (ROOT / "lobby/t5lobby/server/store.py").read_text(encoding="utf-8")
        schema = re.search(r'SCHEMA = """(.*?)"""', store, re.S).group(1)
        self.assertIn("CREATE TABLE IF NOT EXISTS private_reports", schema)
        deploy = (ROOT / "docs/DEPLOY_1.2.0.md").read_text(encoding="utf-8")
        for text in ("Combined database and private-chat rollout", "`private_reports` table",
                     "`T5L_PRIVATE_CHAT=false`", "`T5L_PRIVATE_REPORT_DAYS`",
                     "`T5L_MAX_PRIVATE_REPORTS`", "Code rollback does not erase retained"):
            with self.subTest(contract=text):
                self.assertIn(text, deploy)

    def test_online_social_docs_link_integrated_private_chat(self):
        online = (ROOT / "docs/ONLINE.md").read_text(encoding="utf-8")
        self.assertNotIn("Private chat remains deferred to an owner decision", online)
        self.assertIn("[PRIVATE_CHAT.md](PRIVATE_CHAT.md)", online)
        self.assertIn("ordinary private transcripts are not stored", online)

    def test_current_replay_format_and_legacy_policy_are_documented(self):
        native = (ROOT / "src/netplay/replay.cpp").read_text(encoding="utf-8")
        self.assertRegex(native, r"kVersion\s*=\s*9\b")
        replay = (ROOT / "docs/REPLAYS.md").read_text(encoding="utf-8")
        for text in ("**Format 7 (1.2.0 integrated).**", "guarded SESSION 3",
                     "historical input policy", "**Format 6 (earlier 1.2.0 draft).**"):
            with self.subTest(contract=text):
                self.assertIn(text, replay)
        rematch = (ROOT / "docs/REMATCH_1.2.0.md").read_text(encoding="utf-8")
        self.assertIn("replay format 7 and guarded live SESSION 3", rematch)
        self.assertNotIn("Skip-off recordings keep replay format 5", rematch)

    def test_screen_side_summary_states_the_renderer_rule(self):
        source = (ROOT / "docs/SCREEN_SIDE_120.md").read_text(encoding="utf-8")
        for text in ("actual texture reads and evaluated", "larger than six vertices across the middle are",
                     "from this frame's draws only", "Issue #31",
                     "ALWAYS_LEFT_FIX.md", "**0 mismatches**"):
            with self.subTest(contract=text):
                self.assertIn(text, source)


if __name__ == "__main__":
    unittest.main()
