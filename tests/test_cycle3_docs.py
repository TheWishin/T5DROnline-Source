"""Static documentation regression; no project imports or execution."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NetplayLimitDocumentation(unittest.TestCase):
    def test_limits_agree_with_direct_fight_no_pause_policy(self):
        document = (ROOT / "docs/NETPLAY.md").read_text(encoding="utf-8")
        limits = document.split("## Limits and next steps", 1)[1]
        normalized = re.sub(r"\s+", " ", limits)
        self.assertNotIn("Pausing (START) in an online fight is not blocked", normalized)
        self.assertIn("START cannot pause a direct-fight online match", normalized)
        self.assertIn("[No pause online](#no-pause-online-branch-online-no-pause-112)", limits)
        self.assertIn("synchronized skip exceptions", normalized)


if __name__ == "__main__":
    unittest.main()
