"""Real updater startup/report/apply paths with program-only files and fake processes."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import updater  # noqa: E402


class CleanupSafety(unittest.TestCase):
    def setUp(self):
        scope = Path(ROOT) / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="cleanup_safety_", dir=scope)
        self.addCleanup(self.tmp.cleanup)
        self.install = Path(self.tmp.name) / "install"
        self.install.mkdir()
        self.stage = Path(updater.stage_roots(self.install)[0])
        self.stage.mkdir()
        self.backup = self.stage / "backup"
        self.jobs = []
        jobs = self.jobs

        class DeferredThread:
            def __init__(self, target, args=(), **kwargs):
                self.target, self.args = target, args

            def start(self):
                jobs.append((self.target, self.args))

        patch = mock.patch.object(updater.threading, "Thread", DeferredThread)
        patch.start()
        self.addCleanup(patch.stop)

    def report(self):
        app = SimpleNamespace(
            after=lambda *args: None,
            settings=SimpleNamespace(out_dir=None),
            game_state=lambda: {"needs_rebuild": False},
            set_status=lambda text: None,
        )
        with mock.patch.object(updater, "take_confirm_marker", return_value=None):
            ui = updater.Updater(app, root=str(self.install))
        ui.report_last_update()
        self.assertEqual(len(self.jobs), 1)

    def result(self, **values):
        result = dict(ok=True, changed=True, rolled_back=False, pid=123,
                      phase="swapped", **{"from": "1.0.0", "to": "1.0.1"})
        result.update(values)
        (self.stage / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return result

    def old_program(self):
        old = self.backup / "launcher" / "old.py"
        old.parent.mkdir(parents=True)
        old.write_text("# synthetic old program\n", encoding="utf-8")
        return old

    def run_cleanup(self, wait):
        target, args = self.jobs.pop()
        self.assertIs(target, updater.cleanup)
        with mock.patch.object(updater, "wait_for_exit", side_effect=wait):
            return target(*args)

    def test_startup_report_keeps_backup_while_swap_process_is_alive(self):
        old = self.old_program()
        self.result()
        self.report()
        self.assertFalse(self.run_cleanup(lambda *args: False))
        self.assertTrue(old.is_file())
        self.assertTrue((self.stage / "result.json").is_file())

    def test_startup_report_keeps_backup_if_swap_exited_with_only_interim_result(self):
        old = self.old_program()
        self.result()
        self.report()
        self.assertFalse(self.run_cleanup(lambda *args: True))
        self.assertTrue(old.is_file())

    def make_plan(self):
        new = self.stage / "new"
        for folder, version in ((self.install, "1.0.0"), (new, "1.0.1")):
            (folder / "launcher").mkdir(parents=True)
            (folder / "launcher" / "t5dr_launcher.pyw").write_text(
                "# synthetic program " + version + "\n", encoding="utf-8")
            (folder / "release.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        plan = dict(install=str(self.install), new=str(new), backup=str(self.backup),
                    **{"from": "1.0.0", "to": "1.0.1"}, wait_pid=0,
                    expect_python=False, launch=["synthetic-launcher"])
        path = self.stage / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path

    def test_apply_failed_rollback_keeps_backup_despite_earlier_success_report(self):
        plan = self.make_plan()
        move = updater.move_with_retry

        def deny_restoring_launcher(src, dst, *args, **kwargs):
            if Path(src) == self.backup / "launcher":
                raise PermissionError("synthetic restore denied")
            return move(src, dst, *args, **kwargs)

        def spawn(*args, **kwargs):
            if not self.jobs:
                self.report()
            return SimpleNamespace(poll=lambda: 1)

        with mock.patch.object(updater, "_spawn", side_effect=spawn), \
                mock.patch.object(updater, "processes_under", return_value=[]), \
                mock.patch.object(updater, "move_with_retry", side_effect=deny_restoring_launcher):
            code = updater.main(["--apply", str(plan)])
        self.assertEqual(code, 6)
        final = json.loads((self.stage / "result.json").read_text(encoding="utf-8"))
        self.assertFalse(final["ok"])
        self.assertFalse(final["rolled_back"])
        self.assertEqual(self.jobs[0][1][1]["phase"], "swapped")
        old = self.backup / "launcher" / "t5dr_launcher.pyw"
        self.assertIn("1.0.0", old.read_text(encoding="utf-8"))
        self.assertFalse(self.run_cleanup(lambda *args: True))
        self.assertIn("1.0.0", old.read_text(encoding="utf-8"))

    def test_apply_confirmed_launcher_allows_report_cleanup(self):
        plan = self.make_plan()

        def spawn(*args, **kwargs):
            self.report()
            Path(kwargs["env"][updater.CONFIRM_ENV]).write_text("confirmed", encoding="utf-8")
            return SimpleNamespace(poll=lambda: None)

        with mock.patch.object(updater, "_spawn", side_effect=spawn), \
                mock.patch.object(updater, "processes_under", return_value=[]):
            code = updater.main(["--apply", str(plan)])
        self.assertEqual(code, 0)
        self.assertEqual(self.jobs[0][1][1]["phase"], "swapped")
        self.assertTrue(self.run_cleanup(lambda *args: True))
        self.assertFalse(self.stage.exists())
        self.assertEqual(updater.local_version(self.install), "1.0.1")

    def test_report_keeps_backup_when_final_result_cannot_be_read(self):
        for final in (None, "{"):
            with self.subTest(final=final):
                old = self.old_program()
                self.result()
                self.report()

                def process_exited(*args):
                    path = self.stage / "result.json"
                    if final is None:
                        path.unlink()
                    else:
                        path.write_text(final, encoding="utf-8")
                    return True

                self.assertFalse(self.run_cleanup(process_exited))
                self.assertTrue(old.is_file())
                old.unlink()
                old.parent.rmdir()
                self.backup.rmdir()

    def prepare_failure(self):
        release = {"zip": {"size": 1}, "sums": {"url": "synthetic-sums"}}
        with mock.patch.object(updater, "download", side_effect=updater.UpdateError("synthetic download disabled")) as download:
            with self.assertRaises(updater.UpdateError):
                updater.prepare_update(release, root=str(self.install), need_python=False)
        return download

    def test_prepare_retry_keeps_unrestored_backup_and_uses_other_stage(self):
        old = self.old_program()
        self.result(ok=False, phase="undone")
        download = self.prepare_failure()
        self.assertTrue(old.is_file())
        destination = Path(download.call_args.args[1])
        self.assertEqual(destination.parents[1], Path(updater.stage_roots(self.install)[1]))

    def test_prepare_retry_keeps_both_backups_when_both_stages_are_occupied(self):
        old = self.old_program()
        other = Path(updater.stage_roots(self.install)[1]) / "backup" / "launcher" / "old.py"
        other.parent.mkdir(parents=True)
        other.write_text("# synthetic old program\n", encoding="utf-8")
        download = self.prepare_failure()
        download.assert_not_called()
        self.assertTrue(old.is_file())
        self.assertTrue(other.is_file())

    def test_prepare_retry_reuses_stage_after_old_files_have_been_restored(self):
        self.backup.mkdir()
        self.result(ok=False, rolled_back=True, phase="undone")
        download = self.prepare_failure()
        destination = Path(download.call_args.args[1])
        self.assertEqual(destination.parents[1], self.stage)
        self.assertFalse(self.stage.exists())


if __name__ == "__main__":
    unittest.main()
