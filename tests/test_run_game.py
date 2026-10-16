"""tools/run_game.py without a build: the command, environment and working
directory it hands the game (game_command(), which the launcher uses too)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

from helpers import load_tool


class GameCommand(unittest.TestCase):
    def test_defaults(self):
        rg = load_tool("run_game")
        with tempfile.TemporaryDirectory() as out, mock.patch.dict(os.environ, {}, clear=False):
            for k in rg.DEFAULT_ENV:
                os.environ.pop(k, None)
            argv, env, cwd = rg.game_command(out)
        vfs = os.path.join(out, "game", "vfs")
        self.assertEqual(argv, [os.path.join(out, "build", "cmake", "t5dr.exe"),
                                os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")])
        self.assertEqual(cwd, out)                       # saves and shader cache land under the output root
        self.assertEqual(env["PS3_VFS_ROOT"], vfs.replace("\\", "/"))
        self.assertEqual(env["PS3_HDD0_ROOT"], env["PS3_VFS_ROOT"] + "/dev_hdd0")
        self.assertNotIn("\\", env["PS3_HDD0_ROOT"])
        for k, v in {"PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0"}.items():
            self.assertEqual(env[k], v, k)

    def test_overrides(self):
        rg = load_tool("run_game")
        with mock.patch.dict(os.environ, {"RSX_LIVE_DRAW": "0", "PS3_TITLE": "x"}, clear=False):
            _, env, _ = rg.game_command(extra_env={"PS3_VERBOSE": 1, "PS3_TITLE": None, "PS3_PAD_FILE": "a=b"})
        self.assertEqual(env["RSX_LIVE_DRAW"], "0")      # the caller's environment beats a default
        self.assertEqual(env["PS3_VERBOSE"], "1")        # extra_env beats both, stringified
        self.assertNotIn("PS3_TITLE", env)               # None removes a variable
        self.assertEqual(env["PS3_PAD_FILE"], "a=b")


class Main(unittest.TestCase):
    def test_runs_and_passes_the_exit_code(self):
        rg = load_tool("run_game")
        seen = {}

        def fake_run(cmd, env=None, cwd=None, stdout=None, stderr=None):
            seen.update(cmd=cmd, env=env, cwd=cwd)
            return mock.Mock(returncode=7)
        with tempfile.TemporaryDirectory() as out:
            exe = os.path.join(out, "build", "cmake", "t5dr.exe")
            os.makedirs(os.path.dirname(exe))
            open(exe, "w").close()
            with mock.patch.object(rg.subprocess, "run", fake_run), \
                 mock.patch.object(sys, "argv", ["run_game.py", "--out", out, "PS3_VERBOSE=1", "PS3_PAD_FILE=a=b"]):
                with self.assertRaises(SystemExit) as cm:
                    rg.main()
        self.assertEqual(cm.exception.code, 7)
        self.assertEqual(seen["cmd"][0], exe)
        self.assertEqual(seen["cwd"], out)
        self.assertEqual(seen["env"]["PS3_VERBOSE"], "1")
        self.assertEqual(seen["env"]["PS3_PAD_FILE"], "a=b")    # split on the first '=' only

    def test_not_built(self):
        rg = load_tool("run_game")
        with tempfile.TemporaryDirectory() as out, mock.patch.object(sys, "argv", ["run_game.py", "--out", out]):
            with self.assertRaises(SystemExit) as cm:
                rg.main()
        self.assertIn("build_game.py", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main()
