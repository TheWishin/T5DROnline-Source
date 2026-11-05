"""Cross-program private RNG streams use proven caller identity, preserving US seeds."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars


class RandSites(unittest.TestCase):
    def test_native_caller_identity_and_seed_regression(self):
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        vcvars = find_vcvars() if os.name == "nt" else None
        if not vcvars or not os.path.isfile(clang):
            self.skipTest("requires clang-cl and Visual Studio build tools")
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "rand_site_test.exe"
            obj = pathlib.Path(tmp) / "rand_site_test.obj"
            source = pathlib.Path(ROOT) / "tests/c/rand_site_test.cpp"
            command = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 '
                       f'"{source}" /Fe:"{exe}" /Fo:"{obj}"')
            result = subprocess.run(f'cmd /s /c "{command}"', capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"PASS \d+ checks")


if __name__ == "__main__":
    unittest.main()
