"""Wine / Proton (Linux, Steam Deck), 1.1.5: tools/run_game.py finds Wine through ntdll's wine_get_version and gives
the game RSX_VERTEX_THREADS=0 and PS3_LWM_FAST=0 there (a value of the player's own wins); the game log's first line
and launcher.log name the Wine version, the Proton build (the tool folder's name, never its path) and what the game
got. No Wine needed: a stand-in ntdll."""
import ctypes
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import run_game  # noqa: E402


class Fn:
    def __init__(self, ret=None, host=None):
        self.ret, self.host = ret, host

    def __call__(self, *args):
        if self.host:                                   # wine_get_host_version(&sysname, &release)
            args[0]._obj.value, args[1]._obj.value = self.host
        return self.ret


class FakeNtdll:
    """Wine's ntdll: wine_get_version and friends. Without them it is Windows' ntdll."""

    def __init__(self, version=b"10.0", build=b"wine-10.0 (Staging)", host=(b"Linux", b"6.17.1-cachyos")):
        if version is not None:
            self.wine_get_version = Fn(version)
            self.wine_get_build_id = Fn(build)
            self.wine_get_host_version = Fn(host=host)


GE = "/home/somebody/.steam/root/compatibilitytools.d/GE-Proton10-11:/home/somebody/.steam/steamapps/common/SLR"


class Detect(unittest.TestCase):
    def test_wine(self):
        with mock.patch.dict(os.environ, {"STEAM_COMPAT_TOOL_PATHS": GE}):
            info = run_game.wine_info(FakeNtdll())
        self.assertEqual(info, {"version": "10.0", "build": "wine-10.0 (Staging)", "host": "Linux 6.17.1-cachyos",
                                "proton": "GE-Proton10-11"})
        note = run_game.wine_note(info, {"RSX_VERTEX_THREADS": "0", "PS3_LWM_FAST": "1"})
        self.assertEqual(note, "[wine] Wine 10.0 (wine-10.0 (Staging)) Proton: GE-Proton10-11 on Linux 6.17.1-cachyos "
                               "-- RSX_VERTEX_THREADS=0, PS3_LWM_FAST=1 (your own setting)")
        self.assertNotIn("somebody", note)                     # the Linux user name stays out of the logs
        self.assertIn("defaults for the game: RSX_VERTEX_THREADS=0, PS3_LWM_FAST=0", run_game.wine_note(info))

    def test_not_wine(self):
        self.assertIsNone(run_game.wine_info(FakeNtdll(version=None)))
        if os.name == "nt":                                    # this PC: real Windows
            self.assertIsNone(run_game.wine_info())

    def test_plain_wine_without_steam(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STEAM_COMPAT_TOOL_PATHS", None)
            info = run_game.wine_info(FakeNtdll(build=b"wine-9.0", host=(None, None)))
        self.assertEqual((info["proton"], info["host"]), ("", ""))
        self.assertTrue(run_game.wine_note(info).startswith("[wine] Wine 10.0 (wine-9.0) -- defaults"))


class Defaults(unittest.TestCase):
    def env(self, wine, extra=None, outer=None):
        with mock.patch.object(run_game, "under_wine", lambda: {"version": "10.0"} if wine else None), \
                mock.patch.dict(os.environ, outer or {}):
            for k in run_game.WINE_ENV:
                if k not in (outer or {}):
                    os.environ.pop(k, None)
            return run_game.game_command(ROOT, extra)[1]

    def test_defaults_under_wine_only(self):
        e = self.env(True)
        self.assertEqual((e["RSX_VERTEX_THREADS"], e["PS3_LWM_FAST"]), ("0", "0"))
        e = self.env(False)
        self.assertNotIn("RSX_VERTEX_THREADS", e)
        self.assertNotIn("PS3_LWM_FAST", e)

    def test_own_settings_win(self):
        e = self.env(True, extra={"RSX_VERTEX_THREADS": "2"}, outer={"PS3_LWM_FAST": "1"})
        self.assertEqual((e["RSX_VERTEX_THREADS"], e["PS3_LWM_FAST"]), ("2", "1"))
        e = self.env(True, extra={"RSX_VERTEX_THREADS": None})          # removed on purpose: stays removed
        self.assertNotIn("RSX_VERTEX_THREADS", e)


class GameLog(unittest.TestCase):
    def test_first_line_of_the_game_log(self):
        import core

        class Settings(dict):
            def env_overrides(self):
                return {}
        with tempfile.TemporaryDirectory() as d:
            g = core.GameRun(d, Settings(display="window"))
            info = {"version": "10.0", "build": "", "host": "Linux 6.17", "proton": "proton-cachyos-slr"}
            cmd = ([sys.executable, "-c", "print('[fps] 60.0 (game)')"], dict(os.environ, RSX_VERTEX_THREADS="0",
                                                                          PS3_LWM_FAST="0"), d)
            logged = []
            with mock.patch.object(core.run_game, "under_wine", lambda: info), \
                    mock.patch.object(core.run_game, "game_command", lambda out, env: cmd), \
                    mock.patch.object(core, "log", logged.append):
                g.start()
                g.proc.wait(30)
                end = time.monotonic() + 10
                while g.fps is None and time.monotonic() < end:
                    time.sleep(0.05)
            with open(g.log_path, encoding="utf-8") as f:
                lines = f.read().splitlines()
            time.sleep(0.3)                                    # (the tail thread lets go of the log)
        self.assertEqual(lines[0], "[wine] Wine 10.0 Proton: proton-cachyos-slr on Linux 6.17 -- "
                                   "RSX_VERTEX_THREADS=0, PS3_LWM_FAST=0")
        self.assertEqual(lines[1], "[fps] 60.0 (game)")          # the game's own output follows it
        self.assertIn(lines[0], logged)


if __name__ == "__main__":
    unittest.main()
