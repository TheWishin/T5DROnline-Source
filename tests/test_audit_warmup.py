"""Warm-up build identity regressions; stat results are entirely synthetic."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from helpers import load_tool


_path = list(sys.path)
worker = load_tool("shader_warmup")
sys.path[:] = _path


class WarmupBuildIdentity(unittest.TestCase):
    host = os.path.join("fake", "build", "cmake", "t5dr.exe")
    dll = os.path.join("fake", "build", "cmake", "t5dr_game.dll")

    def stamp(self, host_time=1_000_000_001, dll_time=2_000_000_001, dll_size=20):
        def stat(path):
            if path == self.host:
                return SimpleNamespace(st_size=10, st_mtime=1.0, st_mtime_ns=host_time)
            self.assertEqual(path, self.dll)
            if dll_time is None:
                raise FileNotFoundError(path)
            return SimpleNamespace(st_size=dll_size, st_mtime=2.0, st_mtime_ns=dll_time)
        with mock.patch.object(worker.os, "stat", side_effect=stat):
            return worker.exe_stamp(self.host)

    def test_dll_only_rebuild_invalidates_progress_with_unchanged_host(self):
        original = self.stamp()
        self.assertNotEqual(original, self.stamp(dll_time=2_000_000_002))
        self.assertNotEqual(original, self.stamp(dll_size=21))

    def test_subsecond_host_rebuild_invalidates_progress(self):
        self.assertNotEqual(self.stamp(), self.stamp(host_time=1_000_000_002))

    def test_unchanged_build_keeps_identity_and_monolithic_build_is_supported(self):
        self.assertEqual(self.stamp(), self.stamp())
        self.assertIsNone(self.stamp(dll_time=None)["game_dll"])
        self.assertNotEqual(self.stamp(), self.stamp(dll_time=None))

    def test_legacy_host_only_marker_is_invalidated(self):
        self.assertNotEqual(self.stamp(), {"size": 10, "mtime": 1})


if __name__ == "__main__":
    unittest.main()
