"""Synthetic runtime diagnostics for HD 4400 loss, without a game, GPU or network.

The old launcher only gave generic exit-12 advice and discarded the selected
adapter. The named diagnosis, retained evidence and Check my problem finding
below fail against that code. All runtime diagnostics here are synthetic.
"""
import os
import ast
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("launcher", "lobby", "tools"):
    sys.path.insert(0, os.path.join(ROOT, sub))

import core
import gpu_error
import problem_check
from t5lobby import i18n


def adapter(name="Intel(R) HD Graphics 4400"):
    return (f"[gpu] adapter: {name} (vendor 8086, 0 MB, feature level 11_0, "
            "resource binding tier 1, integrated)")


LOST = "[gpu] device lost at Present: hr=0x887A0005 reason=0x887A0006 (DXGI_ERROR_DEVICE_HUNG)"


class DeviceRemoved(unittest.TestCase):
    def setUp(self):
        language = i18n.language()
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, language)

    def test_exit12_names_only_the_selected_hd4400_and_offers_attempts(self):
        why = core.explain_exit(12, [adapter(), LOST])
        self.assertIn("Intel HD Graphics 4400", why)
        self.assertIn("PC maker", why)
        self.assertIn("Lowest (0.5x)", why)
        self.assertIn("another GPU", why)
        self.assertIn("may not fix", why)
        self.assertIn("Report a problem", why)
        for name in ("Intel(R) HD Graphics 4600", "Intel Arc A770", "NVIDIA GeForce RTX 3090"):
            with self.subTest(name=name):
                self.assertNotIn("4400", core.explain_exit(12, [adapter(name), LOST]))
        self.assertNotIn("4400", core.explain_exit(12, ["[DIALOG] Intel HD Graphics 4400"]))

    def test_model_alone_is_not_a_failure_and_exit13_keeps_its_meaning(self):
        self.assertIsNone(core.explain_exit(0, [adapter()]))
        self.assertIn("cannot run Direct3D 12", core.explain_exit(13, [adapter()]))
        self.assertNotIn("4400", core.explain_exit(5, [adapter()]))
        self.assertNotIn("4400", core.explain_exit(5, [adapter(), "[gpu] RSX_TEST_DEVICE_REMOVED: enabled"]))
        self.assertIn("4400", core.explain_exit(1, [adapter(), LOST]))

    def test_adapter_survives_the_bounded_log_tail(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            run = core.GameRun(folder, None)
            run.log_path = os.path.join(folder, "synthetic-diagnostic.txt")
            with open(run.log_path, "w", encoding="utf-8") as out:
                out.write("\n".join([adapter()] + ["[synthetic] startup"] * 300 + [LOST]) + "\n")
            run.proc = mock.Mock()
            run.proc.poll.return_value = 12
            lease = run._warmup_lease = object()
            with mock.patch.object(core.warmup, "resume_all") as resume:
                run._tail()
            resume.assert_called_once_with(lease)
            self.assertIsNone(run._warmup_lease)
        self.assertEqual(len(run.last_lines), 200)
        self.assertFalse(any(line.startswith("[gpu] adapter:") for line in run.last_lines))
        self.assertEqual(run.gpu_adapter, "Intel(R) HD Graphics 4400")
        self.assertIn("4400", core.explain_exit(12, run.last_lines, gpu_adapter=run.gpu_adapter))

    def test_new_start_clears_previous_run_evidence_before_launch(self):
        settings = mock.MagicMock(spec=core.Settings)
        settings.env_overrides.return_value = {}
        settings.__getitem__.side_effect = {"replays": False}.__getitem__
        run = core.GameRun(ROOT, settings)
        run.gpu_adapter = "Intel(R) HD Graphics 4400"
        run.last_lines = [adapter(), LOST]
        with mock.patch.object(core.run_game, "game_command", side_effect=ValueError("synthetic stop")) as command:
            with self.assertRaisesRegex(ValueError, "synthetic stop"):
                run.start()
        command.assert_called_once_with(ROOT, {"T5_REPLAY_DIR": None})
        self.assertIsNone(run.gpu_adapter)
        self.assertEqual(run.last_lines, [])

    def test_release_ships_the_new_launcher_dependency(self):
        # Inspect the manifest without importing or running the packager.
        with open(os.path.join(ROOT, "tools", "package_release.py"), encoding="utf-8") as source:
            tree = ast.parse(source.read())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "OUR_FILES"
                                  for target in node.targets))
        self.assertIn("launcher/gpu_error.py", ast.literal_eval(assignment.value))

    def test_check_my_problem_requires_same_log_adapter_and_loss(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            os.mkdir(os.path.join(folder, "logs"))
            path = os.path.join(folder, "logs", "game-synthetic.log")
            for lines, expected in (([adapter(), LOST], True), ([adapter()], False),
                                    ([adapter("Intel(R) HD Graphics 4600"), LOST], False),
                                    ([LOST], False)):
                with self.subTest(lines=lines):
                    with open(path, "w", encoding="utf-8") as out:
                        out.write("\n".join(lines))
                    found = problem_check.check_game_log(folder)
                    specific = [item for item in found if item.key == "intel_hd4400_device_lost"]
                    self.assertEqual(bool(specific), expected)
                    if specific:
                        self.assertIn("may not fix", specific[0].text()[2])

    def test_hd4400_names_and_only_runtime_fatal_diagnostics(self):
        self.assertTrue(gpu_error.is_hd4400("Intel(R) HD Graphics 4400"))
        self.assertTrue(gpu_error.is_hd4400("Intel HD 4400"))
        self.assertFalse(gpu_error.is_hd4400("Intel HD Graphics 44000"))
        self.assertTrue(gpu_error.device_lost("[gpu] FATAL (exit code 12): synthetic"))
        self.assertFalse(gpu_error.device_lost("[gpu] RSX_TEST_DEVICE_REMOVED: removing the device"))


if __name__ == "__main__":
    unittest.main()
