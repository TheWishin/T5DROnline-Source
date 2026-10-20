"""A decided match's score (docs/NETPLAY.md "Match result", src/netplay/match_score.h).

* tests/c/match_score_test.cpp is the reading on its own: the fighters' round counts as the game left them in
  rollback pairs (3-2, 3-1, 0-3), draws (1.1.2 made them P1's wins), the fallback to the decided byte, a
  persistent game's matches in a row.
  Built with clang-cl; skipped without a C++ compiler.
* The source checks: the netplay hooks and the direct-fight driver take the score from np::MatchScore -- never
  again from the battle config's bytes 0x1008EBDA/DB, which are not the rounds won in a direct fight (1.1.2:
  a 3-2 reported as 3-0, a 3-0 as 0-1)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars

LLVM = r"C:\Program Files\LLVM"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class Reading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with clang-cl")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (os.path.join(LLVM, "bin", "clang-cl.exe")
                                             if os.path.isfile(os.path.join(LLVM, "bin", "clang-cl.exe")) else None)
        if not vcvars or not clang:
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "match_score_test.exe")
        src = os.path.join(ROOT, "tests", "c", "match_score_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W3 "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "match_score_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=900)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/match_score_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_reading(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        out = r.stdout[-3000:] + r.stderr[-2000:]
        self.assertEqual(r.returncode, 0, out)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", out)
        for part in ("seen ok", "draws ok", "fallback ok", "session ok"):
            self.assertIn(part, r.stdout)


class Source(unittest.TestCase):
    def test_both_readers_use_the_fighters_counts(self):
        hdr = read("src/netplay/match_score.h")
        self.assertIn("kRoundWinsP1 = 0x100900D1", hdr)
        self.assertIn("kRoundWinsP2 = 0x100909A1", hdr)
        for rel in ("src/netplay/t5_hooks.cpp", "src/directfight/df_fight.cpp"):
            src = read(rel)
            code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.S)
            self.assertIn("np::MatchScore::of(rd8(kWinsP1), rd8(kWinsP2), rd8(kMatchOver), rd8(kWinnerIdx), rd8(kRoundsToWin))", code, rel)
            self.assertRegex(code, r"kWinsP1\s*=\s*np::MatchScore::kRoundWinsP1", rel)
            self.assertNotRegex(code, r"0x1008EBD[AB]", rel)        # the battle config's +0x2E/+0x2F: not the score

    def test_a_partial_score_is_never_the_last_matchs(self):
        """A session that ends mid-match writes the rounds won so far -- not the last match's counts, which stay
        until this match's game mode clears them (with the decided byte)."""
        src = read("src/netplay/t5_hooks.cpp")
        body = src[src.index("void write_end_result("):]
        body = body[:body.index("\n}\n")]
        self.assertIn("const bool stale = rd8(kMatchOver) != 0;", body)
        self.assertIn("stale ? 0 : rd8(kWinsP1), stale ? 0 : rd8(kWinsP2)", body)


if __name__ == "__main__":
    unittest.main()
