"""Replay folder selection and lossless moves, without a game or build."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core
import replays


class ReplayStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="replay-storage-", dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.settings = core.Settings(str(self.root / "launcher.json"))
        self.settings["out"] = str(self.root / "native")
        self.custom = self.root / "Replay folder 日本語 ä [2026]"
        self.custom.mkdir()

    def replay(self, folder, name="one", data=b"synthetic test bytes"):
        path = folder / (name + replays.EXT)
        path.write_bytes(data)
        return path

    def test_custom_setting_persists_and_is_used_for_recording(self):
        self.settings["replay_dir"] = str(self.custom)
        self.settings.save()
        saved = core.Settings(self.settings.path)
        self.assertEqual(saved["replay_dir"], str(self.custom))
        self.assertEqual(saved.replay_dir, str(self.custom))
        self.assertEqual(saved.env_overrides()["T5_REPLAY_DIR"], str(self.custom))
        self.assertEqual(list(self.custom.iterdir()), [])

    def test_default_folder_is_created(self):
        folder, warning = self.settings.replay_dir_status()
        self.assertEqual(folder, str(self.root / "native" / "replays"))
        self.assertEqual(warning, "")
        self.assertTrue(Path(folder).is_dir())

    def test_relative_choice_is_based_on_settings_file_not_working_directory(self):
        self.settings["replay_dir"] = self.custom.name
        with mock.patch.object(core.os, "getcwd", return_value=str(self.root / "elsewhere")):
            self.assertEqual(self.settings.replay_dir_status(), (str(self.custom), ""))

    def test_missing_selection_falls_back_without_replacing_preference(self):
        missing = self.custom / "unplugged"
        self.settings["replay_dir"] = str(missing)
        folder, warning = self.settings.replay_dir_status()
        self.assertEqual(folder, self.settings.default_replay_dir)
        self.assertIn(str(missing), warning)
        self.assertIn(folder, warning)
        self.assertFalse(missing.exists())
        self.assertEqual(self.settings["replay_dir"], str(missing))

    def test_readonly_folder_uses_real_write_probe_and_falls_back(self):
        self.settings["replay_dir"] = str(self.custom)
        mkstemp = core.tempfile.mkstemp

        def fail_custom(*args, **kwargs):
            if os.path.normcase(kwargs.get("dir", "")) == os.path.normcase(str(self.custom)):
                raise PermissionError("synthetic read-only folder")
            return mkstemp(*args, **kwargs)

        with mock.patch.object(core.tempfile, "mkstemp", side_effect=fail_custom):
            folder, warning = self.settings.replay_dir_status()
            self.assertEqual(folder, self.settings.default_replay_dir)
            self.assertIn(str(self.custom), warning)
            self.assertEqual(self.settings.env_overrides()["T5_REPLAY_DIR"], folder)
        self.assertEqual(list(self.custom.iterdir()), [])

    def test_unwritable_default_has_clear_message(self):
        with mock.patch.object(core.tempfile, "mkstemp", side_effect=PermissionError("denied")):
            folder, warning = self.settings.replay_dir_status()
            self.assertEqual(folder, self.settings.default_replay_dir)
            self.assertIn(folder, warning)
            self.assertIn("cannot be saved", warning)

    def test_file_and_invalid_paths_fall_back(self):
        file = self.root / "a file"
        file.write_text("fixture", encoding="utf-8")
        for value in (str(file), "bad\0path"):
            self.settings["replay_dir"] = value
            folder, warning = self.settings.replay_dir_status()
            self.assertEqual(folder, self.settings.default_replay_dir)
            self.assertTrue(warning)

    def test_corrupt_saved_setting_uses_default(self):
        for value in (None, True, 2, [], {}):
            with open(self.settings.path, "w", encoding="utf-8") as f:
                json.dump({"out": self.settings["out"], "replay_dir": value}, f)
            loaded = core.Settings(self.settings.path)
            self.assertEqual(loaded["replay_dir"], "")
            self.assertEqual(loaded.replay_dir, loaded.default_replay_dir)

    def test_extra_environment_cannot_split_folder_consumers(self):
        self.settings["replay_dir"] = str(self.custom)
        self.settings["extra_env"] = "T5_REPLAY_DIR=some other place"
        self.assertEqual(self.settings.env_overrides()["T5_REPLAY_DIR"], self.settings.replay_dir)
        self.settings["replays"] = False
        self.assertNotIn("T5_REPLAY_DIR", self.settings.env_overrides())

    def test_recovered_custom_folder_is_used_again(self):
        selected = self.custom / "temporarily missing"
        self.settings["replay_dir"] = str(selected)
        self.assertEqual(self.settings.replay_dir, self.settings.default_replay_dir)
        selected.mkdir()
        self.assertEqual(self.settings.replay_dir_status(), (str(selected), ""))

    def test_game_launch_clears_inherited_recording_and_extra_override_when_off(self):
        self.settings["replays"] = False
        self.settings["extra_env"] = "T5_REPLAY_DIR=other folder"
        self.assert_game_recording_folder(None)

    def test_game_launch_uses_chosen_folder_after_internal_extra_environment(self):
        self.settings["replay_dir"] = str(self.custom)
        self.settings["extra_env"] = "T5_REPLAY_DIR=other folder"
        self.assert_game_recording_folder(str(self.custom))

    def assert_game_recording_folder(self, expected):
        """Inspect command construction, aborting before any subprocess or game log is created."""
        class CapturedCommand(Exception):
            pass

        command = core.run_game.game_command
        captured = {}

        def capture(out, env):
            captured.update(command(out, env)[1])
            raise CapturedCommand

        game = core.GameRun(self.settings.out_dir, self.settings)
        with mock.patch.dict(os.environ, {"T5_REPLAY_DIR": "inherited folder"}), \
                mock.patch.object(core, "costume_env"), \
                mock.patch.object(core.run_game, "game_command", side_effect=capture), \
                mock.patch.object(core.subprocess, "Popen") as start:
            with self.assertRaises(CapturedCommand):
                game.start(extra_env={"T5_REPLAY_DIR": "internal stale override"})
            start.assert_not_called()
        if expected is None:
            self.assertNotIn("T5_REPLAY_DIR", captured)
        else:
            self.assertEqual(captured["T5_REPLAY_DIR"], expected)

    def test_move_preserves_bytes_and_times_and_unrelated_files(self):
        source = self.root / "old"
        source.mkdir()
        old = self.replay(source)
        os.utime(old, (1234567890, 1234567890))
        other = source / "notes.txt"
        other.write_text("keep", encoding="utf-8")
        self.assertEqual(replays.move_replays(str(source), str(self.custom)), (1, 0))
        moved = self.custom / old.name
        self.assertEqual(moved.read_bytes(), b"synthetic test bytes")
        self.assertEqual(int(moved.stat().st_mtime), 1234567890)
        self.assertFalse(old.exists())
        self.assertTrue(other.exists())

    def test_move_never_overwrites_collision(self):
        source = self.root / "old"
        source.mkdir()
        old = self.replay(source, data=b"original")
        existing = self.replay(self.custom, data=b"different")
        self.assertEqual(replays.move_replays(str(source), str(self.custom)), (0, 1))
        self.assertEqual(old.read_bytes(), b"original")
        self.assertEqual(existing.read_bytes(), b"different")

    def test_failed_copy_keeps_source_and_cleans_partial_destination(self):
        source = self.root / "old"
        source.mkdir()
        old = self.replay(source)

        def fail_copy(src, dst, *args, **kwargs):
            dst.write(b"partial")
            raise OSError("synthetic full disk")

        with mock.patch.object(replays.shutil, "copyfileobj", side_effect=fail_copy):
            self.assertEqual(replays.move_replays(str(source), str(self.custom)), (0, 1))
        self.assertEqual(old.read_bytes(), b"synthetic test bytes")
        self.assertEqual(list(self.custom.iterdir()), [])

    def test_changing_source_is_not_deleted(self):
        source = self.root / "old"
        source.mkdir()
        old = self.replay(source)
        copy = replays.shutil.copyfileobj

        def change_source(src, dst, *args, **kwargs):
            copy(src, dst, *args, **kwargs)
            with open(old, "ab") as f:
                f.write(b"new frames")

        with mock.patch.object(replays.shutil, "copyfileobj", side_effect=change_source):
            self.assertEqual(replays.move_replays(str(source), str(self.custom)), (0, 1))
        self.assertTrue(old.read_bytes().endswith(b"new frames"))
        self.assertEqual(list(self.custom.iterdir()), [])

    def test_delete_failure_preserves_verified_destination_and_source(self):
        source = self.root / "old"
        source.mkdir()
        old = self.replay(source)
        remove = replays.os.remove

        def fail_source(path, *args, **kwargs):
            if os.fspath(path) == str(old):
                raise PermissionError("synthetic source read-only")
            return remove(path, *args, **kwargs)

        with mock.patch.object(replays.os, "remove", side_effect=fail_source):
            self.assertEqual(replays.move_replays(str(source), str(self.custom)), (0, 1))
        self.assertEqual(old.read_bytes(), (self.custom / old.name).read_bytes())

    def test_same_folder_move_is_noop(self):
        old = self.replay(self.custom)
        self.assertEqual(replays.move_replays(str(self.custom), str(self.custom)), (0, 0))
        self.assertTrue(old.exists())

    def test_copy_with_wrong_bytes_keeps_source(self):
        source = self.root / "old"
        source.mkdir()
        old = self.replay(source)

        def corrupt_copy(src, dst, *args, **kwargs):
            dst.write(b"different bytes")

        with mock.patch.object(replays.shutil, "copyfileobj", side_effect=corrupt_copy):
            self.assertEqual(replays.move_replays(str(source), str(self.custom)), (0, 1))
        self.assertEqual(old.read_bytes(), b"synthetic test bytes")
        self.assertEqual(list(self.custom.iterdir()), [])

    def test_listing_and_newest_treat_brackets_as_literal_path(self):
        header = {"slot": 0, "matches": [{"p1": 1, "p2": 2, "complete": False}]}
        path = self.replay(self.custom, data=replays.MAGIC + json.dumps(header).encode("utf-8") + b"\n")
        self.assertEqual([e.path for e in replays.list_replays(str(self.custom))], [str(path)])
        self.assertEqual(replays.newest(str(self.custom)), str(path))

    def test_missing_move_source_is_reported_without_creating_it(self):
        source = self.root / "missing"
        with self.assertRaises(OSError):
            replays.move_replays(str(source), str(self.custom))
        self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
