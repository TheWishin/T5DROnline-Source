"""Delayed launcher dialogs and update offers never activate over a running game. No real windows."""
import importlib.machinery
import importlib.util
import os
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "launcher"), os.path.join(ROOT, "lobby")]
import updater  # noqa: E402
from t5lobby import winfront  # noqa: E402


def load_launcher():
    loader = importlib.machinery.SourceFileLoader(
        "background_focus_launcher", os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Game:
    dialog_count = 1
    dialogs = ("The installed game data is corrupted. Ending game.",)

    def __init__(self, running=True):
        self.active = running

    def running(self):
        return self.active


class FatalDialogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = load_launcher()

    def setUp(self):
        self.callbacks = []
        self.game = Game()
        self.app = SimpleNamespace(
            game=self.game, _dialogs_seen=0, _dialog_text="", _dialog_box=False, readonly=False,
            status=SimpleNamespace(set=mock.Mock()),
            after=lambda delay, callback: self.callbacks.append((delay, callback)))
        raise_patch = mock.patch.object(winfront, "raise_window")
        self.raise_window = raise_patch.start()
        self.addCleanup(raise_patch.stop)
        error_patch = mock.patch.object(self.launcher.dialogs, "show_error")
        self.show_error = error_patch.start()
        self.addCleanup(error_patch.stop)
        log_patch = mock.patch.object(self.launcher.core, "log")
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def dispatch(self):
        delay, callback = self.callbacks.pop(0)
        callback()
        return delay

    def assert_quiet(self):
        self.raise_window.assert_not_called()
        self.show_error.assert_not_called()

    def test_fatal_message_waits_for_game_window_to_close(self):
        self.launcher.App._game_dialogs(self.app)
        self.assert_quiet()
        self.assertEqual(self.dispatch(), 0)
        self.assert_quiet()
        self.assertEqual(self.callbacks[0][0], 150)
        self.game.active = False
        self.dispatch()
        self.raise_window.assert_called_once_with(self.app)
        self.show_error.assert_called_once()
        self.assertEqual(self.callbacks, [])

    def test_delayed_message_does_not_interrupt_a_new_game(self):
        self.launcher.App._game_dialogs(self.app)
        self.game.active = False
        self.app.game = Game()
        self.dispatch()
        self.assert_quiet()
        self.app.game.active = False
        self.dispatch()
        self.raise_window.assert_called_once_with(self.app)
        self.show_error.assert_called_once()

    def test_nonfatal_message_only_updates_status(self):
        self.game.dialogs = ("Unable to save Play Data.",)
        self.launcher.App._game_dialogs(self.app)
        self.app.status.set.assert_called_once()
        self.assertEqual(self.callbacks, [])
        self.assert_quiet()


class UpdateOffer(unittest.TestCase):
    def test_delayed_offer_focus_rechecks_busy_state(self):
        game = Game()
        window = SimpleNamespace(lift=mock.Mock())
        button = SimpleNamespace(focus_set=mock.Mock())
        app = SimpleNamespace(game=game)
        up = SimpleNamespace(app=app, win=window, b_update=button)
        updater.Updater._focus_offer(up, window)
        window.lift.assert_not_called()
        button.focus_set.assert_not_called()
        game.active = False
        with mock.patch.object(updater, "processes_under", return_value=[]):
            updater.Updater._focus_offer(up, window)
        window.lift.assert_called_once()
        button.focus_set.assert_called_once()

    def test_closed_or_replaced_offer_never_gets_focus(self):
        window = SimpleNamespace(lift=mock.Mock())
        button = SimpleNamespace(focus_set=mock.Mock())
        up = SimpleNamespace(app=SimpleNamespace(), win=None, b_update=button)
        with mock.patch.object(updater, "busy_reason") as busy:
            updater.Updater._focus_offer(up, window)
        busy.assert_not_called()
        window.lift.assert_not_called()
        button.focus_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
