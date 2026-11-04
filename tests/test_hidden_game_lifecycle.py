"""Launcher hidden-game policy without starting a renderer or native windows."""
import os
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core


class HiddenGameLifecycle(unittest.TestCase):
    def test_missing_ownership_helper_fails_before_starting_an_unowned_game(self):
        game = core.GameRun("unused", {})
        with mock.patch.object(core, "process_owner", None), \
                mock.patch.object(core.subprocess, "Popen") as spawn:
            with self.assertRaises(FileNotFoundError):
                game.start()
        spawn.assert_not_called()

    def test_all_game_modes_use_owned_spawn_and_enforce_hidden_audio_policy(self):
        for extra in ({}, {"T5_CTL_DIR": "control", "PS3_WINDOW_BACKGROUND": "1"},
                      {"T5_NET_MODE": "replay"}, {"T5_PRACTICE": "1"}):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as out:
                settings = core.Settings(os.path.join(out, "launcher.json"))
                settings["extra_env"] = "PS3_AUDIO_MUTE_HIDDEN=0"
                settings["replays"] = False
                game = core.GameRun(out, settings)
                proc = mock.Mock(pid=1234)
                command = [sys.executable, "fake-game"]
                env = {}

                def game_command(_out, overrides):
                    env.update(overrides)
                    return command, env, out

                with mock.patch.object(core.run_game, "game_command", side_effect=game_command), \
                        mock.patch.object(core.run_game, "under_wine", return_value=None), \
                        mock.patch.object(core.warmup, "pause_all", return_value="hold"), \
                        mock.patch.object(core.process_owner, "popen", return_value=proc) as spawn, \
                        mock.patch.object(core.threading, "Thread"):
                    self.assertEqual(game.start(extra), 1234)
                self.assertEqual(env["PS3_AUDIO_MUTE_HIDDEN"], "1")
                self.assertNotIn("PS3_AUDIO_MUTE", env)
                spawn.assert_called_once()
                self.assertEqual(spawn.call_args.args[0], command)
                self.assertEqual(game._warmup_lease, "hold")

    def test_tail_releases_job_and_warmup_only_after_confirmed_exit(self):
        for running in (True, False):
            with self.subTest(running=running):
                game = core.GameRun("unused", {})
                game.proc = object()
                game._warmup_lease = "hold"
                with mock.patch.object(game, "running", return_value=running), \
                        mock.patch.object(game, "_read_tail"), \
                        mock.patch.object(core.process_owner, "release") as release, \
                        mock.patch.object(core.warmup, "resume_all") as resume:
                    game._tail()
                if running:
                    release.assert_not_called()
                    resume.assert_not_called()
                else:
                    release.assert_called_once_with(game.proc)
                    resume.assert_called_once_with("hold")

    def test_owned_game_stop_closes_job_with_a_bounded_wait(self):
        game = core.GameRun("unused", {})
        game.proc = mock.Mock(_t5_job=object())
        game.proc.poll.side_effect = [None, 0]
        with mock.patch.object(core, "IS_WIN", True), \
                mock.patch.object(core.process_owner, "release") as release, \
                mock.patch.object(core, "kill_tree") as tree:
            self.assertTrue(game.stop())
        release.assert_called_once_with(game.proc)
        game.proc.wait.assert_called_once_with(timeout=game.PLAYBACK_STOP_WAIT)
        tree.assert_not_called()


if __name__ == "__main__":
    unittest.main()
