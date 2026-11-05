"""The mixed-edition serializer must preserve unexpected and non-pointer state."""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars


class CrossHash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with clang-cl")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        if not vcvars or not os.path.isfile(clang):
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = os.path.join(cls.tmp.name, "cross_hash_test.exe")
        src = os.path.join(ROOT, "tests", "c", "cross_hash_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W3 "{src}" '
               f'/Fe:"{cls.exe}" /Fo:"{os.path.join(cls.tmp.name, "cross_hash_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=120)
        if r.returncode or not os.path.isfile(cls.exe):
            raise AssertionError("could not build cross_hash_test.cpp: " + (r.stdout + r.stderr)[-4000:])

    def test_fail_closed_serializer(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=30, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"PASS \d+ checks")


if __name__ == "__main__":
    unittest.main()
