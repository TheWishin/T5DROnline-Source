"""The lobby client and a macOS game build (docs/MACOS_ONLINE_TEST.md).

A Mac build has the online modules only when built with tools/build_game.py --macos-online, which records
"online": true in <out>/build/t5dr_build.json; the Online tab and the command-line client refuse to start a
match with a build that has "online": false. The game binary is build/cmake/t5dr.exe on Windows and t5dr on
macOS, in the Online tab as in tools/run_game.py.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from helpers import ROOT, load_tool

LOBBY = os.path.join(ROOT, "lobby")
if LOBBY not in sys.path:
    sys.path.insert(0, LOBBY)

from t5lobby import cli, match_driver  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402


def make_out(d, stamp):
    os.makedirs(os.path.join(d, "game"))
    os.makedirs(os.path.join(d, "build", "cmake"))
    with open(os.path.join(d, "game", "EBOOT.elf"), "wb") as f:
        f.write(b"not a game, a test file")
    if stamp is not None:
        with open(os.path.join(d, "build", "t5dr_build.json"), "w") as f:
            json.dump(stamp, f)


class HasOnline(unittest.TestCase):
    def check(self, stamp):
        with tempfile.TemporaryDirectory() as d:
            make_out(d, stamp)
            return BuildInfo.has_online(d)

    def test_windows_and_old_stamps_have_online(self):
        self.assertTrue(self.check({"code_id": "x"}))          # Windows writes no key
        self.assertTrue(self.check(None))                      # no stamp: from_out_dir reports that instead

    def test_macos_stamp_decides(self):
        self.assertTrue(self.check({"code_id": "x", "online": True}))
        self.assertFalse(self.check({"code_id": "x", "online": False}))

    def test_cli_refuses_a_build_without_online(self):
        with tempfile.TemporaryDirectory() as d:
            make_out(d, {"code_id": "abc", "online": False})
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--server", "127.0.0.1:1", "--name", "x", "--build-out", d, "--quick"])
            self.assertEqual(rc, 1)
            self.assertIn("--macos-online", buf.getvalue())

    def test_european_build_has_no_online_and_says_why(self):
        # 1.1.9: build_game.py stamps the European program (NPEA00019) "online": false -- the online modules know
        # only the US program -- and the client names the version instead of the Mac test build
        with tempfile.TemporaryDirectory() as d:
            make_out(d, {"code_id": "abc", "title": "NPEA00019", "online": False})
            self.assertFalse(BuildInfo.has_online(d))
            self.assertEqual(BuildInfo.game_title(d), "NPEA00019")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--server", "127.0.0.1:1", "--name", "x", "--build-out", d, "--quick"])
            self.assertEqual(rc, 1)
            self.assertIn("NPEA00019, the European version: it plays offline only for now", buf.getvalue())
            self.assertIn("later update", buf.getvalue())
            self.assertNotIn("--macos-online", buf.getvalue())

    def test_game_title(self):
        with tempfile.TemporaryDirectory() as d:
            make_out(d, {"code_id": "abc", "title": "NPUB30009"})
            self.assertEqual(BuildInfo.game_title(d), "NPUB30009")
        with tempfile.TemporaryDirectory() as d:
            make_out(d, None)
            self.assertIsNone(BuildInfo.game_title(d))


class GameBinary(unittest.TestCase):
    def test_same_file_as_run_game(self):
        run_game = load_tool("run_game")
        with tempfile.TemporaryDirectory() as d:
            exe = run_game.game_command(d)[0][0]
            self.assertEqual(match_driver.game_files(d)[0], exe)
        self.assertEqual(match_driver.GAME_EXE, "t5dr.exe" if os.name == "nt" else "t5dr")


if __name__ == "__main__":
    unittest.main()
