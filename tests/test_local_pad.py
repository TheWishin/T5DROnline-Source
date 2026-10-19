"""Which of this PC's controllers is the online player (src/netplay/local_pad.h, local_pad.cpp; docs/NETPLAY.md
"Which controller plays online"): tests/c/local_pad_test.cpp includes the code with fake ports and must print
PASS -- once for the follower, the controls.ini rules and the glue, once more in a process of its own for a
pinned player 1 (the pin is read once per process, as the runtime reads controls.ini once).
Windows only; skipped without clang-cl and the Visual Studio build tools."""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars

LLVM = r"C:\Program Files\LLVM"


class LocalPadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("the netplay layer is Windows only")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (os.path.join(LLVM, "bin", "clang-cl.exe")
                                             if os.path.isfile(os.path.join(LLVM, "bin", "clang-cl.exe")) else None)
        if not vcvars or not clang:
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "local_pad_test.exe")
        src = os.path.join(ROOT, "tests", "c", "local_pad_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O1 /W3 /D_CRT_SECURE_NO_WARNINGS "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "local_pad_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/local_pad_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def run_exe(self, *args):
        env = dict(os.environ)
        env.pop("PS3_CONTROLS", None)
        env.pop("T5_NET_PADPORT", None)
        return subprocess.run([self.exe, *args], capture_output=True, text=True, timeout=120, cwd=self.tmp.name,
                              env=env)

    def test_follower_ini_rules_and_glue(self):
        r = self.run_exe("all", self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", r.stdout[-3000:])

    def test_a_pinned_player_1_reads_port_1_only(self):
        r = self.run_exe("pinned", self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", r.stdout[-3000:])
        self.assertIn("port 1 only ([port1] device in controls.ini)", r.stdout)


class SourcesTest(unittest.TestCase):
    """Every reader of this PC's player goes through local_pad.cpp: nothing reads port 1 by itself any more."""

    def test_no_direct_port_1_reads(self):
        for rel in (("src", "netplay", "netplay_core.cpp"), ("src", "netplay", "t5_hooks.cpp"),
                    ("src", "directfight", "df_pick.cpp")):
            with open(os.path.join(ROOT, *rel), encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn("cellPad_sample_local(0", text, "/".join(rel))
        with open(os.path.join(ROOT, "src", "netplay", "netplay_core.cpp"), encoding="utf-8") as f:
            core = f.read()
        self.assertIn("if (s.localpad) player_input(&in);", core)
        # local mode: P2 is still port 2
        self.assertIn("if (s.localpad) device_input(1, &theirs);", core)


if __name__ == "__main__":
    unittest.main()
