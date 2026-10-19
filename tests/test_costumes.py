"""Custom costumes online (docs/DIRECTFIGHT.md "Custom costumes online").

* tests/c/costume_test.cpp, built against src/directfight/costume_logic.h alone (clang-cl, AddressSanitizer when
  the LLVM install has it), must print PASS: the save's blocks, the wire table (round trip, every malformed one
  refused whole), the check both PCs make on a block before the game gets it.
* The netplay side (PKT_COSTUME: pieces, acknowledgements, the hash check, a hostile opponent) is in
  tests/c/netplay_fuzz.cpp (tests/test_netplay_fuzz.py).
* The driver writes the blocks at FIGHT START, before t5_netplay_start(), and the stage confirm waits for the
  opponent's table; the launcher names the player's own save for online games only.

Windows only; skipped without a C++ compiler.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT
from test_netplay_fuzz import LLVM, asan_runtime_dir
from test_ps_hid import find_vcvars

if os.path.join(ROOT, "launcher") not in sys.path:
    sys.path.append(os.path.join(ROOT, "launcher"))


class CostumeLogic(unittest.TestCase):
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
        cls.asan = asan_runtime_dir(clang)
        exe = os.path.join(cls.tmp.name, "costume_test.exe")
        src = os.path.join(ROOT, "tests", "c", "costume_test.cpp")
        flags = "/fsanitize=address /Zi" if cls.asan else ""
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O1 /W3 {flags} "{src}" '
               f'/Fe:"{exe}" /Fo:"{os.path.join(cls.tmp.name, "costume_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/costume_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_logic(self):
        env = dict(os.environ)
        if self.asan:
            env["PATH"] = self.asan + os.pathsep + env.get("PATH", "")
            env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1"
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=300, cwd=self.tmp.name, env=env)
        out = r.stdout[-3000:] + r.stderr[-3000:]
        self.assertEqual(r.returncode, 0, out)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", out)
        self.assertNotIn("AddressSanitizer", r.stderr)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8-sig") as f:
        return f.read()


class DriverAndProtocol(unittest.TestCase):
    """Where the pieces sit (the order matters for determinism)."""

    def test_written_at_fight_start_before_the_lockstep(self):
        src = read("src/directfight/df_fight.cpp")
        m = re.search(r"pick_fight_start\(f\);\s*costume_apply\(f, session_netplay\(\)\);(.*?)t5_netplay_start\(\)",
                      src, re.S)
        self.assertIsNotNone(m, "costume_apply must follow pick_fight_start and come before t5_netplay_start()")

    def test_stage_confirm_waits_for_the_table(self):
        src = read("src/directfight/df_fight.cpp")
        stage = src[src.index("case Ph::Stage:"):src.index("case Ph::WaitGame:")]
        self.assertLess(stage.index("costume_ready("), stage.index("press(p, B_CROSS, f)"))

    def test_protocol_version_and_bounds(self):
        src = read("src/netplay/netplay_core.cpp")
        self.assertRegex(src, r"constexpr uint8_t\s+kVersion\s*=\s*4;")
        self.assertIn("PKT_COSTUME = 7", src)
        hdr = read("src/directfight/costume_logic.h")
        self.assertIn("kWireMax    = kWireHead + kChars * (1 + kBlock)", hdr)
        cmax = int(re.search(r"kCostumeMax\s*=\s*(\d+)", src).group(1))
        chunk = int(re.search(r"kCostumeChunk\s*=\s*(\d+)", src).group(1))
        self.assertGreaterEqual(cmax, 8 + 35 * (1 + 0x108))
        self.assertLessEqual((cmax + chunk - 1) // chunk, 16, "ack_mask has 16 bits")


class Launcher(unittest.TestCase):
    def test_online_games_name_the_players_save(self):
        import core
        out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out, True)
        env = {"T5_CTL_DIR": "x"}
        core.costume_env(out, env)
        self.assertEqual(env["T5_COSTUME_SAVE"], os.path.join(out, "gamedata", "dev_hdd0", "home", "00000001",
                                                              "savedata", "NPUB30009-SYSNET", "SYS-DATA"))
        env = {"T5_NET_MODE": "host", "T5_COSTUME_SAVE": "0"}
        core.costume_env(out, env)
        self.assertEqual(env["T5_COSTUME_SAVE"], "0", "the player's own choice (extra environment) is kept")
        env = {}
        core.costume_env(out, env)
        self.assertNotIn("T5_COSTUME_SAVE", env, "offline games use their own save as always")

if __name__ == "__main__":
    unittest.main()
