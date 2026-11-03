"""Run updater.main --apply with real swaps and isolated process boundaries."""
import json
import unittest
from unittest import mock

import test_update_launch_failure as launch_fixture

updater = launch_fixture.updater


class UnconfirmedApply(unittest.TestCase):
    # Reuse the program-only fixture, without collecting its test methods again.
    setUp = launch_fixture.ApplyLaunch.setUp
    run_apply = launch_fixture.ApplyLaunch.run_apply

    def assert_recoverable(self, code, result, phase):
        self.assertNotEqual(code, 0)
        self.assertFalse(result["ok"])
        self.assertTrue(result["changed"])
        self.assertFalse(result["rolled_back"])
        self.assertEqual(result["phase"], phase)
        self.assertEqual(updater.local_version(self.install), "1.0.1")
        self.assertEqual(updater.local_version(self.backup), "1.0.0")
        self.assertIn("1.0.0", (self.backup / "launcher" / "t5dr_launcher.pyw").read_text())
        with mock.patch.object(updater, "wait_for_exit", return_value=True):
            self.assertFalse(updater.cleanup(str(self.stage), result))
        self.assertEqual(updater.local_version(self.backup), "1.0.0")

    def test_live_launcher_timeout_keeps_backup_and_reports_unconfirmed(self):
        wait_confirm = updater.wait_confirm

        def expired(proc, marker, timeout, watch_exit=True):
            return wait_confirm(proc, marker, 0, watch_exit=watch_exit)

        with mock.patch.object(updater, "wait_confirm", side_effect=expired), \
                mock.patch.object(updater, "undo", side_effect=AssertionError("live files must not move")):
            code, result, launch = self.run_apply(lambda *args, **kwargs: mock.Mock(poll=lambda: None))
        self.assertEqual(code, 8)
        self.assert_recoverable(code, result, "unconfirmed")
        self.assertEqual(launch.call_count, 1)
        self.assertIn("confirm", result["error"])

    def test_confirmation_exception_replaces_interim_success_without_restart(self):
        with mock.patch.object(updater, "wait_confirm", side_effect=RuntimeError("synthetic confirmation fault")), \
                mock.patch.object(updater, "undo", side_effect=AssertionError("live files must not move")):
            code, result, launch = self.run_apply(lambda *args, **kwargs: mock.Mock(poll=lambda: None))
        self.assertEqual(code, 7)
        self.assert_recoverable(code, result, "failed")
        self.assertEqual(launch.call_count, 1)
        self.assertIn("synthetic confirmation fault", result["error"])

    def test_post_swap_process_probe_exception_replaces_interim_success(self):
        processes = mock.Mock(side_effect=[[], RuntimeError("synthetic process probe fault")])
        code, result, launch = self.run_apply(AssertionError("unexpected launch"), processes)
        self.assertEqual(code, 7)
        self.assert_recoverable(code, result, "failed")
        launch.assert_not_called()
        self.assertIn("synthetic process probe fault", result["error"])

    def test_interim_result_write_exception_still_writes_failure(self):
        write_json = updater._write_json
        writes = []

        def fail_once(path, result):
            writes.append(dict(result))
            if len(writes) == 1:
                raise OSError("synthetic interim write fault")
            return write_json(path, result)

        path = self.stage / "plan.json"
        path.write_text(json.dumps(self.plan), encoding="utf-8")
        with mock.patch.object(updater, "processes_under", return_value=[]), \
                mock.patch.object(updater, "_spawn", side_effect=AssertionError("unexpected launch")) as launch, \
                mock.patch.object(updater, "_write_json", side_effect=fail_once):
            code = updater.main(["--apply", str(path)])
        self.assertEqual(code, 7)
        result = json.loads((self.stage / "result.json").read_text(encoding="utf-8"))
        self.assert_recoverable(code, result, "failed")
        launch.assert_not_called()
        self.assertIn("synthetic interim write fault", result["error"])


if __name__ == "__main__":
    unittest.main()
