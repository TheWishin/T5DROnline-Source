"""The mixed hash must guard every byte of the differently laid-out CRT prefix."""
import os
import shutil
import subprocess
import tempfile
import unittest
from helpers import ROOT
from test_ps_hid import find_vcvars
class FirstBlock(unittest.TestCase):
    def test_native_prefix_guard(self):
        if os.name != "nt": self.skipTest("clang-cl native fixture")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        if not vcvars or not os.path.isfile(clang): self.skipTest("no native compiler")
        with tempfile.TemporaryDirectory() as directory:
            exe = os.path.join(directory, "first_block_hash_test.exe")
            obj = os.path.join(directory, "first_block_hash_test.obj")
            src = os.path.join(ROOT, "tests", "c", "first_block_hash_test.cpp")
            cmd = f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 "{src}" /Fe:"{exe}" /Fo:"{obj}"'
            result = subprocess.run(f'cmd /s /c "{cmd}"', cwd=directory, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([exe], cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS immutable prefix", result.stdout)
