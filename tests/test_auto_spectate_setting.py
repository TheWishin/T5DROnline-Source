"""Auto-spectate is an explicit, persisted opt-in, independent of spectator privacy."""
import ast
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "launcher") not in sys.path:
    sys.path.append(os.path.join(ROOT, "launcher"))
import core


class AutoSpectateSettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "launcher.json")

    def test_new_and_old_settings_leave_auto_spectate_off(self):
        self.assertIs(core.Settings(self.path)["auto_spectate"], False)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"spectators": True, "spectators_ranked": True}, f)
        self.assertIs(core.Settings(self.path)["auto_spectate"], False)

    def test_explicit_choice_survives_saving_without_changing_privacy(self):
        settings = core.Settings(self.path)
        settings["spectators"], settings["spectators_ranked"] = False, True
        for enabled in (True, False):
            settings["auto_spectate"] = enabled
            settings.save()
            loaded = core.Settings(self.path)
            self.assertIs(loaded["auto_spectate"], enabled)
            self.assertIs(loaded["spectators"], False)
            self.assertIs(loaded["spectators_ranked"], True)

    def test_non_boolean_saved_values_do_not_enable_auto_boot(self):
        for malformed in ("false", "true", 1, None, [], {}):
            with self.subTest(value=malformed):
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump({"auto_spectate": malformed}, f)
                self.assertIs(core.Settings(self.path)["auto_spectate"], False)

    def test_settings_ui_offers_the_translated_opt_in_and_saves_it(self):
        # Check the UI wiring without constructing a window or starting the launcher.
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        text_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name) and n.func.id == "t"]
        self.assertTrue(any(n.args and isinstance(n.args[0], ast.Constant)
                            and n.args[0].value == "Automatically watch matches while idle" for n in text_calls))
        saves = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "save_settings"]
        self.assertEqual(len(saves), 1)
        self.assertTrue(any(isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store)
                            and isinstance(n.slice, ast.Constant) and n.slice.value == "auto_spectate"
                            for n in ast.walk(saves[0])))


class PlaybackProcessStopTests(unittest.TestCase):
    def game(self):
        game = core.GameRun("unused", {})
        game._playback = True
        game.proc = mock.Mock()
        return game

    def test_playback_stop_kills_only_captured_process_and_bounds_exit_wait(self):
        game = self.game()
        game.proc.poll.side_effect = [None, 0]
        with mock.patch.object(core, "kill_tree") as tree:
            self.assertTrue(game.stop())
        tree.assert_not_called()
        game.proc.kill.assert_called_once_with()
        game.proc.wait.assert_called_once_with(timeout=0.25)

    def test_unconfirmed_exit_keeps_process_running_for_ownership_guard(self):
        game = self.game()
        game.proc.poll.return_value = None
        game.proc.wait.side_effect = core.subprocess.TimeoutExpired("game", 0.25)
        with mock.patch.object(core, "kill_tree") as tree:
            self.assertFalse(game.stop())
        tree.assert_not_called()
        self.assertTrue(game.running())

    def test_process_exit_racing_kill_is_safe(self):
        game = self.game()
        game.proc.poll.side_effect = [None, 0]
        game.proc.kill.side_effect = OSError("already exited")
        self.assertTrue(game.stop())
        game.proc.wait.assert_not_called()

    def test_kill_failure_keeps_process_running_without_raising_to_ui(self):
        game = self.game()
        game.proc.poll.return_value = None
        game.proc.kill.side_effect = OSError("access denied")
        self.assertFalse(game.stop())
        self.assertTrue(game.running())

    def test_stopping_an_exited_playback_does_not_kill_again(self):
        game = self.game()
        game.proc.poll.return_value = 0
        self.assertTrue(game.stop())
        game.proc.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
