"""Static documentation regression; no project imports or execution."""
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ChatFilterReviewDocumentation(unittest.TestCase):
    def test_opening_does_not_claim_the_starter_list_is_already_reviewed(self):
        data = json.loads((ROOT / "lobby/t5lobby/server/data/chat_filter_terms.json")
                          .read_text(encoding="utf-8"))
        self.assertIn("review required before deployment", data["review"]["status"])
        document = (ROOT / "docs/CHAT_FILTER.md").read_text(encoding="utf-8")
        opening = re.sub(r"\s+", " ", document.split("## Coverage and existing names", 1)[0])
        self.assertNotIn("maintainer-reviewed", opening)
        self.assertIn("starter list requires maintainer and native-speaker review before deployment", opening)


if __name__ == "__main__":
    unittest.main()
