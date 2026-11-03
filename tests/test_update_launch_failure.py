"""Exercise the real updater --apply entry with program-only folders and fake spawning."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import updater  # noqa: E402


class ApplyLaunch(unittest.TestCase):
    def setUp(self):
        scope = Path(ROOT) / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="apply_launch_", dir=scope)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.install = root / "install"
        self.stage = root / "stage"
        self.new = self.stage / "new"
        self.backup = self.stage / "backup"
        for folder, version in ((self.install, "1.0.0"), (self.new, "1.0.1")):
            (folder / "launcher").mkdir(parents=True)
            (folder / "release.json").write_text(json.dumps({"version": version}), encoding="utf-8")
            (folder / "launcher" / "t5dr_launcher.pyw").write_text(
                f"# synthetic program {version}\n", encoding="utf-8")
        self.plan = dict(install=str(self.install), new=str(self.new), backup=str(self.backup),
                         **{"from": "1.0.0", "to": "1.0.1"}, wait_pid=0,
                         expect_python=False, launch=["synthetic-launcher"])

    def run_apply(self, spawn, processes=None):
        path = self.stage / "plan.json"
        path.write_text(json.dumps(self.plan), encoding="utf-8")
        with mock.patch.object(updater, "processes_under", processes or mock.Mock(return_value=[])), \
                mock.patch.object(updater, "_spawn", side_effect=spawn) as launch:
            code = updater.main(["--apply", str(path)])
        result = json.loads((self.stage / "result.json").read_text(encoding="utf-8"))
        return code, result, launch

    def assert_rolled_back(self, code, result):
        self.assertEqual(code, 6)
        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(result["phase"], "undone")
        self.assertEqual(updater.local_version(self.install), "1.0.0")
        self.assertIn("1.0.0", (self.install / "launcher" / "t5dr_launcher.pyw").read_text())
        self.assertEqual(updater.local_version(self.new), "1.0.1")
        self.assertEqual(list(self.backup.iterdir()), [])  # old program files were restored, not deleted

    def test_failed_spawn_restores_old_program_before_restarting_it(self):
        versions = []

        def spawn(*args, **kwargs):
            versions.append(updater.local_version(self.install))
            if len(versions) == 1:
                raise PermissionError("synthetic launch denied")
            return mock.Mock()

        code, result, _ = self.run_apply(spawn)
        self.assert_rolled_back(code, result)
        self.assertEqual(versions, ["1.0.1", "1.0.0"])
        self.assertIn("synthetic launch denied", (self.stage / "swap.log").read_text(encoding="utf-8"))

    def test_failed_restart_still_preserves_restored_old_program(self):
        code, result, launch = self.run_apply(OSError("synthetic launch denied"))
        self.assert_rolled_back(code, result)
        self.assertEqual(launch.call_count, 2)

    def test_confirmed_launcher_keeps_new_program_and_removes_backup(self):
        def spawn(*args, **kwargs):
            Path(kwargs["env"][updater.CONFIRM_ENV]).write_text("confirmed", encoding="utf-8")
            return mock.Mock()

        code, result, launch = self.run_apply(spawn)
        self.assertEqual((code, result["ok"], result["phase"]), (0, True, "done"))
        self.assertEqual(updater.local_version(self.install), "1.0.1")
        self.assertFalse(self.backup.exists())
        self.assertEqual(launch.call_count, 1)

    def test_early_exit_without_confirmation_still_rolls_back(self):
        code, result, launch = self.run_apply(lambda *a, **kw: mock.Mock(poll=lambda: 1))
        self.assert_rolled_back(code, result)
        self.assertEqual(launch.call_count, 2)

    def test_running_launcher_suppresses_spawn_without_new_failure(self):
        processes = mock.Mock(side_effect=[[], [(123, str(self.install / "python.exe"))]])
        code, result, launch = self.run_apply(AssertionError("unexpected launch"), processes)
        self.assertEqual((code, result["ok"], result["phase"]), (0, True, "done"))
        launch.assert_not_called()

    def test_missing_launcher_command_preserves_existing_no_spawn_behavior(self):
        self.plan.pop("launch")
        code, result, launch = self.run_apply(AssertionError("unexpected launch"))
        self.assertEqual((code, result["ok"], result["phase"]), (0, True, "done"))
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
