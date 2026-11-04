"""Background warm-up lifecycle and checkpoints, with no game/process launches."""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from helpers import ROOT

for directory in ("launcher", "tools", "lobby"):
    path = os.path.join(ROOT, directory)
    if path not in sys.path:
        sys.path.append(path)
import warmup
from t5lobby import process_owner
_path = list(sys.path)
import shader_warmup as worker
sys.path[:] = _path


class Process:
    pid = 12345
    returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -9


class Control:
    def __init__(self, path):
        pass

    def send(self, command, **values):
        pass


class Background(unittest.TestCase):
    def test_process_confirmation_is_inconclusive_off_windows(self):
        with mock.patch.object(warmup.sys, "platform", "linux"), \
                mock.patch.object(warmup.ctypes, "WinDLL", create=True,
                                  side_effect=AssertionError("Windows API called off Windows")):
            self.assertFalse(warmup._process_exited(23456))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = self.tmp.name

    def test_start_is_hidden_low_priority_and_bounded_without_waiting(self):
        controller = warmup.BackgroundWarmup(self.out)
        proc = Process()
        with mock.patch.object(warmup.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", return_value=proc) as spawn, \
                mock.patch.object(proc, "wait", side_effect=AssertionError("start waited")):
            self.assertTrue(controller.start())
            self.assertFalse(controller.start())
        cmd = spawn.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--fights") + 1], "6")
        self.assertEqual(cmd[cmd.index("--minutes") + 1], "3")
        self.assertIn("--background", cmd)
        self.assertEqual(spawn.call_args.kwargs["creationflags"],
                         warmup.CREATE_NO_WINDOW | warmup.BELOW_NORMAL_PRIORITY_CLASS)
        self.assertEqual(spawn.call_args.kwargs["stdout"], warmup.subprocess.DEVNULL)

    def test_pause_stops_worker_before_return_and_resume_restarts(self):
        controller = warmup.BackgroundWarmup(self.out)
        with mock.patch.object(warmup.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", side_effect=[Process(), Process()]) as spawn:
            controller.start()
            first = controller.proc
            token = controller.pause()
            self.assertIsNotNone(first.poll())
            self.assertTrue(os.path.isfile(os.path.join(self.out, warmup.PAUSE_FILE)))
            self.assertFalse(controller.start())
            controller.resume(token)
            self.assertEqual(spawn.call_count, 2)
            self.assertFalse(os.path.exists(os.path.join(self.out, warmup.PAUSE_FILE)))

    def test_close_allows_a_later_build_but_does_not_resume_on_its_own(self):
        controller = warmup.BackgroundWarmup(self.out)
        with mock.patch.object(warmup.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", side_effect=[Process(), Process()]) as spawn:
            controller.start()
            token = controller.pause()
            controller.close()
            self.assertFalse(controller.resume(token))
            self.assertEqual(spawn.call_count, 1)
            self.assertTrue(controller.start())

    def test_pause_failure_blocks_game_start(self):
        controller = warmup.BackgroundWarmup(self.out)
        controller.proc = Process()
        with mock.patch.object(controller.proc, "wait", side_effect=warmup.subprocess.TimeoutExpired("worker", 1)), \
                mock.patch.object(warmup.subprocess, "run", side_effect=OSError("taskkill unavailable")):
            with self.assertRaises(OSError):
                controller.pause()
        self.assertTrue(controller.paused)

    def test_old_game_tail_cannot_resume_during_a_new_game(self):
        controller = warmup.BackgroundWarmup(self.out)
        with mock.patch.object(warmup.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", side_effect=[Process(), Process()]) as spawn:
            controller.start()
            first = controller.pause()
            second = controller.pause()
            self.assertFalse(controller.resume(first))
            self.assertEqual(spawn.call_count, 1)
            self.assertTrue(controller.resume(second))
            self.assertEqual(spawn.call_count, 2)
            self.assertFalse(controller.resume(first))  # Repeated/stale release cannot affect a later game.

    def test_dead_worker_with_unconfirmed_child_blocks_real_game(self):
        controller = warmup.BackgroundWarmup(self.out)
        child_file = os.path.join(self.out, warmup.CHILD_FILE)
        os.makedirs(os.path.dirname(child_file), exist_ok=True)
        with open(child_file, "w", encoding="ascii") as f:
            json.dump({"state": "starting"}, f)
        with self.assertRaises(OSError):
            controller.pause()
        self.assertTrue(controller.paused)

    def test_fallback_recovers_after_confirming_child_exit(self):
        controller = warmup.BackgroundWarmup(self.out)
        controller.proc = Process()
        child_file = os.path.join(self.out, warmup.CHILD_FILE)
        os.makedirs(os.path.dirname(child_file), exist_ok=True)
        with open(child_file, "w", encoding="ascii") as f:
            json.dump({"pid": 23456}, f)

        def wait(timeout=None):
            if controller.proc.returncode is None:
                controller.proc.returncode = 0
                raise warmup.subprocess.TimeoutExpired("worker", 1)
            return 0

        with mock.patch.object(controller.proc, "wait", side_effect=wait), \
                mock.patch.object(warmup.subprocess, "run") as kill_tree, \
                mock.patch.object(warmup, "_process_exited", return_value=True) as exited:
            token = controller.pause()
        self.assertIsNotNone(token)
        self.assertFalse(os.path.exists(child_file))
        exited.assert_called_once_with(23456)
        self.assertIn(str(Process.pid), kill_tree.call_args.args[0])
        self.assertNotIn("23456", kill_tree.call_args.args[0])  # Recorded child PIDs are never killed directly.

    def test_live_or_unknown_child_is_not_recovered(self):
        controller = warmup.BackgroundWarmup(self.out)
        child_file = os.path.join(self.out, warmup.CHILD_FILE)
        os.makedirs(os.path.dirname(child_file), exist_ok=True)
        with open(child_file, "w", encoding="ascii") as f:
            json.dump({"pid": 23456}, f)
        with mock.patch.object(warmup, "_process_exited", return_value=False), self.assertRaises(OSError):
            controller.pause()
        self.assertTrue(os.path.exists(child_file))

    def test_output_change_cannot_bypass_a_real_game_hold_or_close(self):
        other_out = os.path.join(self.out, "other")
        os.makedirs(other_out)
        with mock.patch.dict(warmup._controllers, {}, clear=True), \
                mock.patch.dict(warmup._global_holds, {}, clear=True), \
                mock.patch.object(warmup.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", side_effect=[Process(), Process(), Process()]) as spawn:
            self.assertTrue(warmup.start(self.out))
            first = warmup.pause_all()
            self.assertFalse(warmup.start(other_out))
            second = warmup.pause_all()
            warmup.resume_all(first)
            self.assertEqual(spawn.call_count, 1)  # An older game tail cannot release the newer global hold.
            warmup.resume_all(second)
            self.assertEqual(spawn.call_count, 3)
            old_proc = warmup.controller(self.out).proc
            new_proc = warmup.controller(other_out).proc
            warmup.close_all()
            self.assertIsNotNone(old_proc.poll())
            self.assertIsNotNone(new_proc.poll())
            self.assertFalse(warmup.controller(self.out).enabled)
            self.assertFalse(warmup.controller(other_out).enabled)

    def test_current_output_is_checked_before_any_build_in_a_new_session(self):
        child_file = os.path.join(self.out, warmup.CHILD_FILE)
        os.makedirs(os.path.dirname(child_file), exist_ok=True)
        with open(child_file, "w", encoding="ascii") as f:
            json.dump({"pid": 23456}, f)
        with mock.patch.dict(warmup._controllers, {}, clear=True), \
                mock.patch.dict(warmup._global_holds, {}, clear=True), \
                mock.patch.object(warmup, "_process_exited", return_value=False) as exited:
            with self.assertRaises(OSError):
                warmup.pause_all(self.out)
            self.assertEqual(len(warmup._controllers), 1)
            with self.assertRaises(OSError):
                warmup.close_all(self.out)
            self.assertEqual(exited.call_count, 2)
            self.assertTrue(os.path.exists(child_file))

    def test_worker_resumes_only_fully_completed_fights(self):
        args = SimpleNamespace(env=[], force=False, fights=6, fight_seconds=3,
                               minutes=3, background=True)
        calls = []

        def first_play(ctl, status, proc, lines, *values, **options):
            calls.append(lines)
            options["progress"](1)
            raise worker.Paused()

        def second_play(ctl, status, proc, lines, *values, **options):
            calls.append(lines)
            options["progress"](len(lines))
            return len(lines)

        with mock.patch.object(worker.run_game, "game_command", return_value=(["host", "program"], {}, self.out)), \
                mock.patch.object(worker.os.path, "isfile", return_value=True), \
                mock.patch.object(worker, "exe_stamp", return_value={"size": 1, "mtime": 2}), \
                mock.patch.object(worker.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", side_effect=[Process(), Process()]), \
                mock.patch("t5lobby.match_driver.Control", Control), \
                mock.patch.object(worker, "play", side_effect=lambda *a, **kw:
                                  (first_play if not calls else second_play)(*a, **kw)):
            self.assertEqual(worker.warmup(args, self.out), 0)
            self.assertEqual(worker.warmup(args, self.out), 0)
        self.assertEqual(len(calls[0]), 6)
        self.assertEqual(calls[1], calls[0][1:])
        with open(os.path.join(self.out, worker.CACHE, worker.BACKGROUND_MARKER), encoding="utf-8") as f:
            marker = json.load(f)
        self.assertEqual(marker["completed"], 6)
        self.assertTrue(marker["complete"])

    def test_play_pause_precedes_the_next_fight(self):
        pause = os.path.join(self.out, "pause")
        with open(pause, "w", encoding="ascii") as f:
            f.write("pause")
        ctl = mock.Mock()
        with self.assertRaises(worker.Paused):
            worker.play(ctl, "status", Process(), worker.fight_lines(6), 3, 9999999999,
                        "pad", pause=pause)
        ctl.send.assert_not_called()

    def test_budget_expires_during_active_fight(self):
        # First iteration reaches FIGHT START; its first input wait crosses the deadline.
        ctl = mock.Mock()
        with mock.patch.object(worker, "read_json", return_value={"state": "fight", "match": 1}), \
                mock.patch.object(worker, "set_pad"), \
                mock.patch.object(worker.time, "time", side_effect=[0, 0, 0, 0, 0, 0, 2]), \
                self.assertRaises(worker.BudgetExpired):
            worker.play(ctl, "status", Process(), worker.fight_lines(1), 3, 1, "pad")

    def test_skip_and_launcher_deadline_stop_the_owned_worker(self):
        controller = warmup.BackgroundWarmup(self.out)
        proc = Process()
        timer = mock.Mock()
        with mock.patch.object(warmup.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", return_value=proc), \
                mock.patch.object(warmup.threading, "Timer", return_value=timer), \
                mock.patch.object(process_owner, "release") as release:
            self.assertTrue(controller.start())
            self.assertTrue(controller.skip())
            self.assertTrue(os.path.exists(os.path.join(self.out, worker.SKIP_FILE)))
            self.assertFalse(controller.enabled)
            controller._expire(proc)
        self.assertIsNotNone(proc.poll())
        release.assert_called_once_with(proc)

    def test_hung_owned_worker_is_stopped_by_job_without_pid_kill(self):
        controller = warmup.BackgroundWarmup(self.out)
        proc = Process()
        proc._t5_job = object()
        controller.proc = proc

        def wait(timeout=None):
            if proc.poll() is None:
                raise warmup.subprocess.TimeoutExpired("worker", timeout)
            return proc.returncode

        with mock.patch.object(proc, "wait", side_effect=wait), \
                mock.patch.object(process_owner, "release", side_effect=lambda p: p.kill()) as release, \
                mock.patch.object(warmup.subprocess, "run") as pid_kill:
            controller._expire(proc)
        self.assertIsNotNone(proc.poll())
        pid_kill.assert_not_called()
        self.assertGreaterEqual(release.call_count, 1)
        newer = Process()
        controller.proc = newer
        controller._expire(proc)  # A cancelled old timer cannot stop a newer queue.
        self.assertIsNone(newer.poll())

    def test_worker_is_always_hidden_muted_and_cleaned_up_on_every_outcome(self):
        for outcome in ("success", "skip", "timeout", "error"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as out:
                proc = Process()
                args = SimpleNamespace(env=["PS3_AUDIO_MUTE=0", "PS3_WINDOW_BACKGROUND=0", "PS3_WINDOW_HIDDEN=0"],
                                       force=True, fights=1, fight_seconds=3, minutes=3, background=True)

                def play(*values, **options):
                    if outcome == "skip":
                        raise worker.Skipped(0)
                    if outcome == "timeout":
                        raise worker.BudgetExpired()
                    if outcome == "error":
                        raise ValueError("test failure")
                    return 1

                with mock.patch.object(worker.run_game, "game_command", return_value=(["host", "program"], {}, out)), \
                        mock.patch.object(worker.os.path, "isfile", return_value=True), \
                        mock.patch.object(worker, "exe_stamp", return_value={"size": 1}), \
                        mock.patch.object(worker.sys, "platform", "win32"), \
                        mock.patch.object(process_owner, "popen", return_value=proc) as spawn, \
                        mock.patch.object(process_owner, "release") as release, \
                        mock.patch("t5lobby.match_driver.Control", Control), \
                        mock.patch.object(worker, "play", side_effect=play):
                    if outcome == "error":
                        with self.assertRaisesRegex(ValueError, "test failure"):
                            worker.warmup(args, out)
                    else:
                        self.assertEqual(worker.warmup(args, out), 0)
                self.assertIsNotNone(proc.poll())
                release.assert_called_once_with(proc)
                env = spawn.call_args.kwargs["env"]
                for name in ("PS3_AUDIO_MUTE", "PS3_WINDOW_BACKGROUND", "PS3_WINDOW_HIDDEN"):
                    self.assertEqual(env[name], "1")
                self.assertEqual(spawn.call_args.kwargs["creationflags"], worker.subprocess.BELOW_NORMAL_PRIORITY_CLASS)
                self.assertFalse(os.path.exists(os.path.join(out, worker.CHILD_FILE)))

    def test_hidden_queue_uses_the_opt_in_runtime_patch(self):
        patch = os.path.join(ROOT, "patches", "ps3recomp", "0105-warmup-hidden.patch")
        with open(patch, encoding="utf-8") as f:
            text = f.read()
        self.assertIn('if (background && !getenv("PS3_WINDOW_HIDDEN"))', text)
        self.assertIn('ShowWindow(s_state.hwnd, SW_SHOWMINNOACTIVE)', text)

    def test_failed_owned_spawn_cannot_leave_an_unknown_child_marker(self):
        args = SimpleNamespace(env=[], force=True, fights=1, fight_seconds=3,
                               minutes=3, background=True)
        child_file = os.path.join(self.out, worker.CHILD_FILE)

        def fail_spawn(*values, **options):
            self.assertFalse(os.path.exists(child_file))
            raise OSError("job assignment failed")

        with mock.patch.object(worker.run_game, "game_command", return_value=(["host", "program"], {}, self.out)), \
                mock.patch.object(worker.os.path, "isfile", return_value=True), \
                mock.patch.object(worker, "exe_stamp", return_value={"size": 1}), \
                mock.patch.object(worker.sys, "platform", "win32"), \
                mock.patch.object(process_owner, "popen", side_effect=fail_spawn), \
                mock.patch("t5lobby.match_driver.Control", Control):
            with self.assertRaisesRegex(OSError, "job assignment failed"):
                worker.warmup(args, self.out)
        self.assertFalse(os.path.exists(child_file))
        self.assertTrue(warmup._recover_child(self.out))


if __name__ == "__main__":
    unittest.main()
