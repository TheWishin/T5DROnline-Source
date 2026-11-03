"""Game-free host menu tests. Maintainer runs this; no game or server is used."""
import os
import shutil
import subprocess
import tempfile
import unittest
from helpers import ROOT


class RematchUI(unittest.TestCase):
    def test_fake_pad_clock_protocol(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        vcvars = None
        if os.name == "nt":
            from test_ps_hid import find_vcvars
            vcvars = find_vcvars()
            compiler = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
            if not vcvars or not os.path.isfile(compiler):
                self.skipTest("requires clang-cl and Visual Studio build tools")
        elif not compiler:
            self.skipTest("requires a C++17 compiler")
        with tempfile.TemporaryDirectory() as directory:
            executable = os.path.join(directory, "rematch_ui_test" + (".exe" if os.name == "nt" else ""))
            source = os.path.join(ROOT, "tests", "c", "rematch_ui_test.cpp")
            command = [compiler, "-std=c++17", "-O1", source, "-o", executable]
            if vcvars:
                obj = os.path.join(directory, "rematch_ui_test.obj")
                command = (f'"{vcvars}" >nul 2>&1 && "{compiler}" /nologo /std:c++17 /EHsc /O1 '
                           f'"{source}" /Fe:"{executable}" /Fo:"{obj}"')
                command = f'cmd /s /c "{command}"'
            build = subprocess.run(command,
                                   capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([executable], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"PASS \d+ checks")


if __name__ == "__main__":
    unittest.main()
