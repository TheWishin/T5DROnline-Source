"""Replay folder changes without Tk windows, a game, or existing player files."""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core
import replays_ui


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("replay_folder_launcher", os.path.join(
        ROOT, "launcher", "t5dr_launcher.pyw"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ReplayFolderUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = load_launcher()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.settings = core.Settings(os.path.join(self.temp.name, "launcher.json"))
        self.settings["out"] = os.path.join(self.temp.name, "native")
        self.settings.save = mock.Mock()
        self.var = mock.Mock()
        self.var.get.return_value = ""
        self.app = types.SimpleNamespace(
            readonly=False, settings=self.settings, game=None, replay_dir_var=self.var,
            replay_dir_hint=mock.Mock(), replays=types.SimpleNamespace(refresh=mock.Mock()))
        for name in ("_apply_replay_folder", "_replay_folder_status"):
            setattr(self.app, name, types.MethodType(getattr(self.launcher.App, name), self.app))

    def test_switch_leaves_replays_when_player_declines_move(self):
        source = self.settings.replay_dir
        os.makedirs(source, exist_ok=True)
        original = os.path.join(source, "old.t5replay")
        with open(original, "wb") as f:
            f.write(b"synthetic fixture")
        destination = os.path.join(self.temp.name, "日本語 replay folder")
        os.mkdir(destination)
        self.var.get.return_value = destination
        with mock.patch.object(self.launcher.dialogs, "ask_yes_no", return_value=False), \
                mock.patch.object(self.launcher.replays, "move_replays") as move:
            self.app._apply_replay_folder()
        move.assert_not_called()
        self.assertTrue(os.path.isfile(original))
        self.assertEqual(self.settings["replay_dir"], destination)
        self.settings.save.assert_called_once()
        self.app.replays.refresh.assert_called_once()

    def test_move_requires_explicit_yes_and_reports_retained_files(self):
        source = self.settings.replay_dir
        os.makedirs(source, exist_ok=True)
        with open(os.path.join(source, "old.t5replay"), "wb") as f:
            f.write(b"synthetic fixture")
        destination = os.path.join(self.temp.name, "destination")
        os.mkdir(destination)
        self.var.get.return_value = destination
        with mock.patch.object(self.launcher.dialogs, "ask_yes_no", return_value=True), \
                mock.patch.object(self.launcher.replays, "move_replays", return_value=(2, 1)) as move, \
                mock.patch.object(self.launcher.dialogs, "show_info") as info:
            self.app._apply_replay_folder()
        move.assert_called_once_with(source, destination)
        self.assertIn("2", info.call_args.args[1])
        self.assertIn(source, info.call_args.args[1])

    def test_missing_folder_uses_default_and_shows_warning(self):
        missing = os.path.join(self.temp.name, "missing")
        self.var.get.return_value = missing
        with mock.patch.object(self.launcher.dialogs, "show_info") as info, \
                mock.patch.object(self.launcher.dialogs, "ask_yes_no") as ask:
            self.app._apply_replay_folder()
        self.assertEqual(self.settings.replay_dir, self.settings.default_replay_dir)
        self.assertIn(missing, info.call_args.args[1])
        ask.assert_not_called()

    def test_running_game_blocks_folder_change(self):
        self.app.game = types.SimpleNamespace(running=lambda: True)
        self.var.get.return_value = os.path.join(self.temp.name, "different")
        with mock.patch.object(self.launcher.dialogs, "show_info") as info:
            self.app._apply_replay_folder()
        self.assertEqual(self.settings["replay_dir"], "")
        self.settings.save.assert_not_called()
        info.assert_called_once()


class ReplayFolderCacheTests(unittest.TestCase):
    def test_refresh_displays_fallback_warning_and_lists_effective_folder(self):
        settings = types.SimpleNamespace(replay_dir_status=lambda: ("fallback", "folder unavailable"))
        tab = replays_ui.ReplaysTab.__new__(replays_ui.ReplaysTab)
        tab.app = types.SimpleNamespace(settings=settings)
        tab.tv, tab.count_var, tab.folder_warning = mock.Mock(), mock.Mock(), mock.Mock()
        tab.tv.get_children.return_value = []
        tab._buttons = mock.Mock()
        with mock.patch.object(replays_ui.os.path, "isdir", return_value=True), \
                mock.patch.object(replays_ui.replays, "list_replays", return_value=[]) as listing:
            tab.refresh()
        listing.assert_called_once_with("fallback")
        tab.folder_warning.set.assert_called_once_with("folder unavailable")
        self.assertEqual(tab._listed_folder, "fallback")

    def test_open_unavailable_default_shows_warning_without_making_folder(self):
        settings = types.SimpleNamespace(replay_dir_status=lambda: ("fallback", "folder unavailable"))
        tab = replays_ui.ReplaysTab.__new__(replays_ui.ReplaysTab)
        tab.app = types.SimpleNamespace(settings=settings)
        tab.folder_warning = mock.Mock()
        with mock.patch.object(replays_ui.os.path, "isdir", return_value=False), \
                mock.patch.object(replays_ui.os, "makedirs") as mkdir, \
                mock.patch.object(replays_ui.core, "open_path") as opening:
            tab.open_folder()
        mkdir.assert_not_called()
        opening.assert_not_called()
        tab.folder_warning.set.assert_called_once_with("folder unavailable")

    def test_history_cache_refreshes_immediately_when_folder_changes(self):
        settings = types.SimpleNamespace(replay_dir="first")
        tab = replays_ui.ReplaysTab.__new__(replays_ui.ReplaysTab)
        tab.app = types.SimpleNamespace(settings=settings)
        with mock.patch.object(replays_ui.time, "time", return_value=100), \
                mock.patch.object(replays_ui.os.path, "isdir", return_value=True), \
                mock.patch.object(replays_ui.replays, "list_replays", side_effect=[["old"], ["new"]]):
            self.assertEqual(tab.entries_now(), ["old"])
            settings.replay_dir = "second"
            self.assertEqual(tab.entries_now(), ["new"])


if __name__ == "__main__":
    unittest.main()
