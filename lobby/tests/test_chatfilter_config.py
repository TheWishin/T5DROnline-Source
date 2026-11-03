"""Filter configuration and deployment contracts; no server or game is needed."""
import ast
import fnmatch
import os
from pathlib import Path
import unittest

import util  # noqa: F401 (sets sys.path)
from t5lobby.server.config import Config


ROOT = Path(__file__).resolve().parents[2]


class ChatFilterConfigTest(unittest.TestCase):
    def test_default_is_enabled_and_points_at_server_data(self):
        cfg = Config.from_env({})
        self.assertTrue(cfg.chat_filter)
        self.assertTrue(os.path.isabs(cfg.chat_filter_path))
        self.assertEqual(Path(cfg.chat_filter_path),
                         ROOT / "lobby/t5lobby/server/data/chat_filter_terms.json")
        self.assertTrue(Path(cfg.chat_filter_path).is_file())

    def test_environment_can_disable_filter_and_select_operator_file(self):
        cfg = Config.from_env({"T5L_CHAT_FILTER": "0",
                               "T5L_CHAT_FILTER_PATH": "/managed/chat_filter_terms.json"})
        self.assertFalse(cfg.chat_filter)
        self.assertEqual(cfg.chat_filter_path, "/managed/chat_filter_terms.json")
        for enabled in ("1", "true", "yes", "on"):
            with self.subTest(enabled=enabled):
                self.assertTrue(Config.from_env({"T5L_CHAT_FILTER": enabled}).chat_filter)

    def test_explicit_override_wins_over_environment(self):
        cfg = Config.from_env({"T5L_CHAT_FILTER": "0", "T5L_CHAT_FILTER_PATH": "env.json"},
                              chat_filter=True, chat_filter_path="override.json")
        self.assertTrue(cfg.chat_filter)
        self.assertEqual(cfg.chat_filter_path, "override.json")

    def test_native_installers_copy_server_data(self):
        for platform, destination, command in (("linux", "CODE", "install -m 0644"),
                                                ("macos", "APP", "cp")):
            with self.subTest(platform=platform):
                script = (ROOT / "lobby/deploy" / platform / "install.sh").read_text(encoding="utf-8")
                self.assertIn('"$' + destination + '/t5lobby/server/data"', script)
                self.assertIn('for f in "$SRC"/t5lobby/server/data/*.json; do run ' + command
                              + ' "$f" "$' + destination + '/t5lobby/server/data/"; done', script)

    def test_server_list_is_excluded_from_player_release_inputs(self):
        # Inspect literal inputs only: importing/running the release tool could inspect git or build.
        tree = ast.parse((ROOT / "tools/package_release.py").read_text(encoding="utf-8"))
        inputs = {}
        for statement in tree.body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id in ("OUR_FILES", "OUR_OPTIONAL_FILES", "OUR_GLOBS"):
                        inputs[target.id] = ast.literal_eval(statement.value)
        self.assertEqual(set(inputs), {"OUR_FILES", "OUR_OPTIONAL_FILES", "OUR_GLOBS"})
        term_path = "lobby/t5lobby/server/data/chat_filter_terms.json"
        self.assertNotIn(term_path, inputs["OUR_FILES"] + inputs["OUR_OPTIONAL_FILES"])
        for pattern in inputs["OUR_GLOBS"]:
            # pathlib glob patterns match segments, so a single '*' never crosses '/'.
            if len(pattern.split("/")) == len(term_path.split("/")):
                self.assertFalse(all(fnmatch.fnmatchcase(part, glob_part)
                                     for part, glob_part in zip(term_path.split("/"), pattern.split("/"))),
                                 pattern)


if __name__ == "__main__":
    unittest.main()
