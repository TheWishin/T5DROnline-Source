"""Game-free integration contracts for the three remaining 1.2.0 drafts.

Only reads source and parses Python AST. No imports of build/game/server tools,
subprocesses, sockets, temporary data or native compilation.
"""
import ast
from fnmatch import fnmatchcase
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def assignment(path, name):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
    return next(node.value for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name
                        for target in node.targets))


class RemainingIntegration(unittest.TestCase):
    def test_packaging_keeps_prior_features_and_all_new_launcher_modules(self):
        files = ast.literal_eval(assignment("tools/package_release.py", "OUR_FILES"))
        for name in ("launcher/warmup.py", "launcher/first_start.py", "launcher/gpu_support.py",
                     "launcher/gpu_error.py", "launcher/replays.py", "launcher/replays_ui.py"):
            with self.subTest(path=name):
                self.assertIn(name, files)
                self.assertTrue((ROOT / name).is_file())
        self.assertEqual(len(files), len(set(files)), "duplicate packaged paths")
        globs = ast.literal_eval(assignment("tools/package_release.py", "OUR_GLOBS"))
        for name in ("lobby/t5lobby/private_chat.py", "lobby/t5lobby/tk_private_chat.py",
                     "lobby/t5lobby/server/private_chat.py", "lobby/t5lobby/compatibility.py"):
            self.assertTrue(any(fnmatchcase(name, pattern) for pattern in globs), name)
            self.assertTrue((ROOT / name).is_file())

    def test_build_identity_separates_previous_integrated_source(self):
        version = ast.literal_eval(assignment("tools/build_game.py", "CODE_VERSION"))
        self.assertGreater(version, 9)

    def test_waiting_diagnostics_keep_rest_delay_and_prior_runtime_hooks(self):
        source = (ROOT / "src/netplay/netplay_core.cpp").read_text(encoding="utf-8")
        for contract in ('#include "rollback_delay.h"', "detail::jitter_delay(",
                         "g_start_noted.fetch_or(", "const uint16_t mapped = b;",
                         "MatchRuleAgreement match_rules;", 'path_env("T5_REPLAY_FILE")',
                         "cellGcm_vrr_external_hold();"):
            with self.subTest(contract=contract):
                self.assertIn(contract, source)


if __name__ == "__main__":
    unittest.main()
