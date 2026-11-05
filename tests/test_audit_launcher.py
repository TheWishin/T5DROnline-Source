"""Game-free launcher audit regressions; filesystem and writes are in-memory fakes."""
import ast
import json
import importlib.util
import os
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def settings_save(namespace):
    tree = ast.parse((ROOT / "launcher/core.py").read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings")
    node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "save")
    code = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(code, "launcher/core.py", "exec"), namespace)
    return namespace["save"]


class MemoryFile:
    def __init__(self, files, name):
        self.files = files
        self.name = name
        files[name] = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def write(self, text):
        self.files[self.name] += text
        return len(text)

    def flush(self):
        pass

    def fileno(self):
        return 42


class SettingsSaveAudit(unittest.TestCase):
    def setUp(self):
        self.original = '{"screen_side": "left", "replay_dir": "keep", "nickname": "player"}'
        self.files = {"launcher.json": self.original}
        self.os = SimpleNamespace(path=os.path, fsync=mock.Mock(), remove=self.remove,
                                  replace=mock.Mock(side_effect=self.replace))
        self.tempfile = SimpleNamespace(NamedTemporaryFile=mock.Mock(
            side_effect=lambda **_kwargs: MemoryFile(self.files, "settings.tmp")))
        self.namespace = {"SCREEN_SIDES": {"dealt": "", "left": "", "right": ""},
                          "json": json, "os": self.os, "tempfile": self.tempfile,
                          "open": lambda path, *_args, **_kwargs: MemoryFile(self.files, path)}
        self.save = settings_save(self.namespace)

        class Settings(dict):
            path = "launcher.json"

        self.settings = Settings(screen_side="right", replay_dir="keep", nickname="player")

    def remove(self, path):
        self.files.pop(path, None)

    def replace(self, source, destination):
        self.files[destination] = self.files.pop(source)

    def test_disk_full_during_serialization_keeps_previous_settings(self):
        def partial_dump(_data, stream, **_kwargs):
            stream.write('{"screen_side":')
            raise OSError("disk full")

        self.namespace["json"] = SimpleNamespace(dump=partial_dump)
        self.save(self.settings)
        self.assertEqual(self.files["launcher.json"], self.original)
        self.assertNotIn("settings.tmp", self.files)

    def test_failed_sync_keeps_previous_settings(self):
        self.os.fsync.side_effect = OSError("sync failed")
        self.save(self.settings)
        self.assertEqual(self.files["launcher.json"], self.original)
        self.assertNotIn("settings.tmp", self.files)
        self.os.replace.assert_not_called()

    def test_failed_replace_keeps_previous_settings(self):
        self.os.replace.side_effect = OSError("file locked")
        self.save(self.settings)
        self.assertEqual(self.files["launcher.json"], self.original)
        self.assertNotIn("settings.tmp", self.files)

    def test_success_preserves_preferences_and_replaces_after_sync(self):
        order = []
        self.os.fsync.side_effect = lambda _fd: order.append("sync")

        def replace(source, destination):
            order.append("replace")
            self.replace(source, destination)

        self.os.replace.side_effect = replace
        self.save(self.settings)
        saved = json.loads(self.files["launcher.json"])
        self.assertEqual(saved["replay_dir"], "keep")
        self.assertEqual(saved["nickname"], "player")
        self.assertEqual(saved["screen_side"], "right")
        self.assertIs(saved["always_left"], False)
        self.assertEqual(order, ["sync", "replace"])
        self.assertNotIn("settings.tmp", self.files)
        options = self.tempfile.NamedTemporaryFile.call_args.kwargs
        self.assertEqual(options["dir"], os.path.dirname(os.path.abspath(self.settings.path)))
        self.assertIs(options["delete"], False)


class ReplayFormatAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("audit_replays", ROOT / "launcher/replays.py")
        cls.replays = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.replays)

    def replay_bytes(self, version):
        # One synthetic frame and match, held only in memory; no recording is written.
        payload = bytearray(b"T5RP")
        payload += struct.pack("<IIIIiIIII", version, 1, 0, 2, 1, 7, 7, 1, 60)
        if version >= 2:
            payload += struct.pack("<I", 0)
        payload += struct.pack("<I6I", 1, 0, 0, 0, 0, 0, 0)
        payload += struct.pack("<12i", 9, 33, 0, 0, 1, 2, 20, 3, 0, -1, 0, 0)
        payload += struct.pack("<Q", 0)
        for name in (b"test-a", b"test-b"):
            payload += struct.pack("<H", len(name)) + name
        if version >= 3:
            payload += struct.pack("<I", 0)
        if version >= 5:
            payload += struct.pack("<I", 2)  # Automatic skips in 6+, independent from the format7 reset guard.
        payload += struct.pack("<II", 0, 0)  # No barriers or hashes.
        payload += bytes([9] + [0] * 11)    # P1 START+SELECT; neutral axes and P2.
        header = self.replays.MAGIC + b'{"matches":[{"names":["test-a","test-b"]}]}\n'
        return header, zlib.compress(payload)

    def decode(self, parts):
        with mock.patch.object(self.replays, "split", return_value=parts):
            return self.replays.read_payload("unused")

    def test_format_seven_decodes_reset_policy_and_preserves_inputs(self):
        decoded = self.decode(self.replay_bytes(7))
        self.assertEqual(decoded["version"], 7)
        self.assertIs(decoded["soft_reset_guard"], True)
        self.assertEqual(decoded["inputs"][0], [(9, 128, 128, 128, 128)])
        self.assertTrue(decoded["matches"][0]["auto_skip_after_round"])

    def test_legacy_replays_keep_legacy_reset_policy(self):
        for version in range(1, 7):
            with self.subTest(version=version):
                decoded = self.decode(self.replay_bytes(version))
                self.assertIs(decoded["soft_reset_guard"], False)
                self.assertEqual(decoded["inputs"][0][0][0], 9)

    def test_unknown_format_ten_is_rejected(self):
        with self.assertRaises(self.replays.ReplayError):
            self.decode(self.replay_bytes(10))
        with mock.patch.object(self.replays, "split", return_value=self.replay_bytes(10)):
            with self.assertRaises(self.replays.ReplayError):
                self.replays.strip_names("unused")

    def test_scrubbing_preserves_format_seven_policy_rules_and_inputs(self):
        original = self.replay_bytes(7)
        with mock.patch.object(self.replays, "split", return_value=original):
            scrubbed = self.replays.strip_names("unused")
        end = scrubbed.index(b"\n", len(self.replays.MAGIC)) + 1
        clean = self.decode((scrubbed[:end], scrubbed[end:]))
        decoded = self.decode(original)
        self.assertEqual(clean["version"], decoded["version"])
        self.assertEqual(clean["soft_reset_guard"], decoded["soft_reset_guard"])
        self.assertEqual(clean["inputs"], decoded["inputs"])
        self.assertEqual(clean["matches"][0]["auto_skip_after_round"],
                         decoded["matches"][0]["auto_skip_after_round"])
        self.assertEqual(clean["matches"][0]["names"], ["", ""])

if __name__ == "__main__":
    unittest.main()
