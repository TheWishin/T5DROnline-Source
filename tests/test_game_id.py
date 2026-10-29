"""1.1.9: which game program the runtime runs (src/platform/t5_game.h, docs/EU.md).

* tests/c/game_id_test.cpp: the US program, the European v01.00 and "Online" programs, others and unreadable files
  told apart by their ELF header; started with an ELF as argv[1] (as the runtime is), the modules that know the US
  program's addresses stay off for a European one. Built with clang-cl; skipped without a C++ compiler.
* The source checks: every module that installs hooks at US addresses asks t5game::hooks_ok() first."""
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


class Identify(unittest.TestCase):
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
        exe = os.path.join(cls.tmp.name, "game_id_test.exe")
        src = os.path.join(ROOT, "tests", "c", "game_id_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W3 /D_CRT_SECURE_NO_WARNINGS '
               f'"{src}" /Fe:"{exe}" /Fo:"{os.path.join(cls.tmp.name, "game_id_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=900)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/game_id_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_identify(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$")

    def test_started_with_the_european_program(self):
        subprocess.run([self.exe], capture_output=True, timeout=120, cwd=self.tmp.name)   # writes the stand-ins
        r = subprocess.run([self.exe, "eu.elf"], capture_output=True, text=True, timeout=60, cwd=self.tmp.name)
        self.assertIn("game 2 NPEA00019 v01.00 (EU) hooks off", r.stdout)
        self.assertIn("[t5] test module: off -- this game is NPEA00019 v01.00 (EU)", r.stderr)
        r = subprocess.run([self.exe, "us.elf"], capture_output=True, text=True, timeout=60, cwd=self.tmp.name)
        self.assertIn("game 1 NPUB30009 v01.00 (US) hooks on", r.stdout)
        self.assertEqual(r.stderr, "")


class Source(unittest.TestCase):
    def test_every_registration_asks_first(self):
        for rel, before in (("src/netplay/t5_hooks.cpp", "ps3_hle_register_ctx(NID_cellPadInit"),
                            ("src/directfight/df_hooks.cpp", "ctl_init();"),
                            ("src/rollback/rb_hooks.cpp", 't5p_setenv_os("PS3_VM_WRITE_WATCH"'),
                            ("src/perf/t5_perf.cpp", "ps3_hle_register_ctx(")):
            src = read(rel)
            reg = src[src.index("struct Register {"):]
            reg = reg[:reg.index("} g_register;")]
            code = re.sub(r"/\*.*?\*/|//[^\n]*", "", reg, flags=re.S)
            self.assertIn("t5game::hooks_ok(", code, rel)
            self.assertLess(code.index("t5game::hooks_ok("), code.index(before), rel)
            self.assertIn('#include "../platform/t5_game.h"', src, rel)


if __name__ == "__main__":
    unittest.main()
