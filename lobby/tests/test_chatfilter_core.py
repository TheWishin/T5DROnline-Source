"""Pure policy regressions; no game, sockets, client packages or submitted-text logs."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import util  # noqa: F401 (sets sys.path)
from t5lobby.server.chatfilter import ChatFilter
from t5lobby.i18n import LANGUAGES


class ChatFilterTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "policy.json"
        self.write("nigger")

    def write(self, *terms):
        self.path.write_text(json.dumps({"version": 1, "terms": [
            {"term": term} if isinstance(term, str) else term for term in terms
        ]}), encoding="utf-8")
        # Atomic replacement must be recognized even on coarse timestamp filesystems.
        replacement = self.path.with_suffix(".new")
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)

    def test_normalization_and_light_evasion(self):
        policy = ChatFilter(self.path)
        for text in ("NIGGER", "níggér", "n1gg3r", "n!gg3r", "nіggеr", "ｎｉｇｇｅｒ", "𝐍𝐈𝐆𝐆𝐄𝐑",
                     "n i g g e r", "n.i.g.g.e.r", "n_ig_ger", "n---i---g---g---e---r",
                     "nnniiggggeeerrr", "ni\u200bgger", "you nigger!", "(nigger)", "nigger_name",
                     "nigger123", "123nigger", "nig ger", "n" * 1000 + "igger"):
            with self.subTest(text=text):
                self.assertTrue(policy.blocked(text))

    def test_whole_words_and_natural_double_letters_avoid_false_positives(self):
        policy = ChatFilter(self.path)
        innocent = ("Niger", "Nigeria", "Nigerian", "snigger", "sniggering", "trigger", "bigger",
                    "Scunthorpe", "classical", "assassin", "cucumber", "therapist", "Dickinson",
                    "cocktail", "grape", "analyst", "night game", "nice game", "Japanese", "Korean",
                    "abcNIGGERxyz", "neighbour")
        for text in innocent:
            with self.subTest(text=text):
                self.assertFalse(policy.blocked(text))

    def test_configured_substring_mode_for_unspaced_native_text(self):
        self.write({"term": "チョン公", "match": "substring"},
                   {"term": "짱깨", "match": "substring"})
        policy = ChatFilter(self.path)
        self.assertTrue(policy.blocked("あのチョン公は"))
        self.assertTrue(policy.blocked("짱깨가"))
        self.assertFalse(policy.blocked("チョンと触れる"))
        self.assertFalse(policy.blocked("짱구와 한국어"))

    def test_reload_and_invalid_replacement_keep_the_last_good_policy(self):
        policy = ChatFilter(self.path)
        self.write("bougnoule")
        self.assertFalse(policy.blocked("nigger"))
        self.assertTrue(policy.blocked("bougnoule"))
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertLogs("t5lobby.server.chatfilter", level="WARNING") as captured:
            self.assertTrue(policy.blocked("bougnoule"))
            self.assertTrue(policy.blocked("bougnoule"))
        self.assertEqual(len(captured.output), 1)
        self.assertNotIn("bougnoule", captured.output[0])
        self.assertIsNotNone(policy.last_error)
        self.path.unlink()
        with self.assertLogs("t5lobby.server.chatfilter", level="WARNING"):
            self.assertTrue(policy.blocked("bougnoule"))
        self.write("nigger")
        self.assertTrue(policy.blocked("nigger"))
        self.assertIsNone(policy.last_error)
        self.write("ﬀ" * 64)     # raw length valid; normalized length exceeds the bound
        with self.assertLogs("t5lobby.server.chatfilter", level="WARNING"):
            self.assertTrue(policy.blocked("nigger"))

    def test_bad_initial_policy_fails_and_disabled_filter_never_reads(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "Check T5L_CHAT_FILTER_PATH"):
            ChatFilter(self.path)
        self.assertFalse(ChatFilter(self.path, enabled=False).blocked("nigger"))

    def test_invalid_schema_and_bounds(self):
        for data in ({"version": True, "terms": []}, {"version": 1, "terms": ["nigger"]},
                     {"version": 1, "terms": [{"term": "a" * 65}]},
                     {"version": 1, "terms": [{"term": "ﬀ" * 64}]},
                     {"version": 1, "terms": [{"term": "a", "match": "regex"}]},
                     {"version": 1, "terms": [{"term": "a.*"}]},
                     {"version": 1, "terms": [{"term": "a"}] * 257}):
            self.path.write_text(json.dumps(data), encoding="utf-8")
            with self.subTest(data=data), self.assertRaises(ValueError):
                ChatFilter(self.path)

    def test_shipped_data_matches_each_entry_and_has_no_general_swear_words(self):
        path = Path(__file__).parents[1] / "t5lobby" / "server" / "data" / "chat_filter_terms.json"
        policy = ChatFilter(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual({lang for entry in data["terms"] for lang in entry["languages"]}, set(LANGUAGES))
        for entry in data["terms"]:
            with self.subTest(term=entry["term"]):
                self.assertTrue(policy.blocked(entry["term"]))
        for text in ("damn", "shit", "fuck", "Niger", "Nigeria", "sniggering", "Scunthorpe",
                     "cocktail", "classical", "night game", "you pin him", "you pins", "sudamericano",
                     "日本語", "한국어"):
            with self.subTest(innocent=text):
                self.assertFalse(policy.blocked(text))


if __name__ == "__main__":
    unittest.main()
