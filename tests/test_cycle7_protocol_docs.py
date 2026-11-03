"""Static documentation regression; no project imports or execution."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NetplayRollbackStatusDocumentation(unittest.TestCase):
    def test_limits_do_not_describe_existing_rollback_as_future_work(self):
        document = (ROOT / "docs/NETPLAY.md").read_text(encoding="utf-8")
        limits = re.sub(r"\s+", " ", document.split("## Limits and next steps", 1)[1])
        self.assertNotIn("Next step is **rollback**", limits)
        self.assertNotIn("That needs a fast save/load", limits)
        self.assertIn("Rollback is already the direct-fight online default", limits)
        self.assertIn("when both peers offer it", limits)
        self.assertIn("[Rollback](ROLLBACK.md)", limits)


if __name__ == "__main__":
    unittest.main()
