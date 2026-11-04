"""Ownership barriers use fake processes and jobs; no executable is launched."""
import os
import sys
import threading
import unittest
from unittest import mock

from helpers import ROOT

sys.path.append(os.path.join(ROOT, "lobby"))
from t5lobby import process_owner as owner


class Ownership(unittest.TestCase):
    def setUp(self):
        self.proc = mock.Mock()
        self.job = mock.Mock()
        self.events = []
        self.job.assign.side_effect = lambda proc: self.events.append("assign")
        self.spawn = self.enterContext(mock.patch.object(owner.subprocess, "Popen", side_effect=self._spawn))
        self.enterContext(mock.patch.object(owner, "_Job", return_value=self.job))
        self.resume = self.enterContext(mock.patch.object(owner, "_resume", side_effect=lambda p: self.events.append("resume")))
        self.enterContext(mock.patch.object(owner.sys, "platform", "win32"))
        self.enterContext(mock.patch.object(owner, "_jobs", set()))

    def _spawn(self, *args, **kwargs):
        self.events.append("spawn")
        self.assertEqual(kwargs["creationflags"], 0x4000 | owner.CREATE_SUSPENDED)
        return self.proc

    def test_child_cannot_run_before_ownership_and_release_is_idempotent(self):
        proc = owner.popen(["game"], creationflags=0x4000)
        self.assertEqual(self.events, ["spawn", "assign", "resume"])
        self.assertIn(self.job, owner._jobs)
        owner.release(proc)
        owner.release(proc)
        self.job.close.assert_called_once()

    def test_assignment_failure_kills_suspended_child_and_closes_job(self):
        self.job.assign.side_effect = OSError("assignment denied")
        with self.assertRaisesRegex(OSError, "assignment denied"):
            owner.popen(["game"], creationflags=0x4000)
        self.resume.assert_not_called()
        self.proc.kill.assert_called_once()
        self.proc.wait.assert_called_once_with(timeout=5)
        self.job.close.assert_called_once()

    def test_resume_failure_closes_job_even_if_process_wait_fails(self):
        self.resume.side_effect = OSError("resume failed")
        self.proc.wait.side_effect = owner.subprocess.TimeoutExpired("game", 5)
        with self.assertRaisesRegex(OSError, "resume failed"):
            owner.popen(["game"], creationflags=0x4000)
        self.job.close.assert_called_once()

    def test_spawn_failure_closes_unused_job(self):
        self.spawn.side_effect = OSError("no game")
        with self.assertRaisesRegex(OSError, "no game"):
            owner.popen(["game"], creationflags=0x4000)
        self.job.close.assert_called_once()


class ConcurrentRelease(unittest.TestCase):
    def test_stop_and_tail_close_a_handle_only_once(self):
        # Hold the first CloseHandle open while the other thread starts closing.
        # A second unsynchronized call would reach the kernel during this wait.
        job = owner._Job.__new__(owner._Job)
        job.handle = 123
        first_close = threading.Event()
        second_attempt = threading.Event()
        errors = []

        class AnnouncedLock:
            def __init__(self):
                self.lock = threading.Lock()

            def __enter__(self):
                if first_close.is_set():
                    second_attempt.set()
                self.lock.acquire()

            def __exit__(self, *args):
                self.lock.release()

        job._close_lock = AnnouncedLock()

        def close_handle(handle):
            if first_close.is_set():
                second_attempt.set()
            else:
                first_close.set()
                if not second_attempt.wait(timeout=2):
                    raise AssertionError("Second close never started")
            return True

        job.kernel = mock.Mock()
        job.kernel.CloseHandle.side_effect = close_handle

        def release():
            try:
                job.close()
            except BaseException as exc:
                errors.append(exc)

        one = threading.Thread(target=release)
        two = threading.Thread(target=release)
        one.start()
        self.assertTrue(first_close.wait(timeout=2))
        two.start()
        one.join(timeout=2)
        two.join(timeout=2)
        self.assertFalse(one.is_alive() or two.is_alive())
        self.assertEqual(errors, [])
        job.kernel.CloseHandle.assert_called_once_with(123)
        self.assertIsNone(job.handle)



if __name__ == "__main__":
    unittest.main()
