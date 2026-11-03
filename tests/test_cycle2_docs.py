"""Static documentation regression; no client imports or network activity."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PrivateChatRateLimitDocumentation(unittest.TestCase):
    def test_describes_short_circuit_before_recipient_and_text_checks(self):
        document = (ROOT / "docs/PRIVATE_CHAT.md").read_text(encoding="utf-8")
        self.assertIn("sender, address and global budgets are checked in that", document)
        self.assertIn("order, stopping at the first exhausted budget", document)
        self.assertIn("Attempts refused later by recipient,", document)
        self.assertIn("mute or text checks have already consumed all three budgets", document)


if __name__ == "__main__":
    unittest.main()
