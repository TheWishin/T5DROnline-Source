"""tools/run_game.py without a build: the environment it hands the game."""
import os
import sys
import tempfile
import unittest
from unittest import mock

from helpers import load_tool


class RunGame(unittest.TestCase):
    def launch(self, argv, environ=None):
        rg = load_tool("run_game")
        seen = {}

        def fake_run(cmd, env=None, cwd=None, stdout=None, stderr=None):
            seen.update(cmd=cmd, env=env, cwd=cwd)
            return mock.Mock(returncode=7)
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "t5dr.exe")
            open(exe, "w").close()
            with mock.patch.object(rg, "EXE", exe), mock.patch.object(rg.subprocess, "run", fake_run), \
                 mock.patch.object(sys, "argv", ["run_game.py"] + argv), \
                 mock.patch.dict(os.environ, environ or {}, clear=False):
                with self.assertRaises(SystemExit) as cm:
                    rg.main()
        self.assertEqual(cm.exception.code, 7)          # the game's exit code is passed through
        return rg, seen

    def test_defaults(self):
        rg, seen = self.launch([])
        env = seen["env"]
        self.assertEqual(env["PS3_VFS_ROOT"], rg.VFS.replace("\\", "/"))
        self.assertEqual(env["PS3_HDD0_ROOT"], env["PS3_VFS_ROOT"] + "/dev_hdd0")
        self.assertNotIn("\\", env["PS3_HDD0_ROOT"])
        for k, v in {"PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0"}.items():
            self.assertEqual(env[k], v, k)
        self.assertTrue(seen["cmd"][1].endswith(os.path.join("PS3_GAME", "USRDIR", "EBOOT.elf")))
        self.assertEqual(seen["cwd"], rg.ROOT)

    def test_overrides(self):
        _, seen = self.launch(["PS3_VERBOSE=1", "PS3_PAD_FILE=a=b"], {"RSX_LIVE_DRAW": "0"})
        env = seen["env"]
        self.assertEqual(env["PS3_VERBOSE"], "1")            # argument beats the default
        self.assertEqual(env["PS3_PAD_FILE"], "a=b")         # split on the first '=' only
        self.assertEqual(env["RSX_LIVE_DRAW"], "0")          # caller's environment beats the default

    def test_not_built(self):
        rg = load_tool("run_game")
        with mock.patch.object(rg, "EXE", os.path.join(tempfile.gettempdir(), "no-such-t5dr.exe")), \
             mock.patch.object(sys, "argv", ["run_game.py"]):
            with self.assertRaises(SystemExit) as cm:
                rg.main()
        self.assertIn("build_game.py", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main()
