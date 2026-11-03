"""Static documentation regressions; no project imports or execution."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GuestPurgeDocumentation(unittest.TestCase):
    def test_admin_reference_discloses_guest_report_retention(self):
        document = (ROOT / "docs/HOSTING.md").read_text(encoding="utf-8")
        row = next(line for line in document.splitlines()
                   if line.startswith("| `purge-guests "))
        self.assertNotIn("Guests themselves are never stored", row)
        self.assertIn("guest-only matches", row)
        self.assertIn("Private reports, including guest names and selected message text", row)
        self.assertIn("retained separately", row)
        self.assertIn("[private-report retention policy](PRIVATE_CHAT.md)", row)


if __name__ == "__main__":
    unittest.main()
