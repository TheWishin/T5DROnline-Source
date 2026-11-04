"""Portable command/step/provenance/checkpoint policy for the local replay viewer."""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT


class ViewerModel(unittest.TestCase):
    def test_controller(self):
        scratch = os.path.join(ROOT, "build", "tests")
        os.makedirs(scratch, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="replay-viewer-", dir=scratch) as tmp:
            env = dict(os.environ, APPDATA=tmp, LOCALAPPDATA=tmp, OPENRECOMP_HOME=tmp)
            src = os.path.join(ROOT, "tests", "c", "replay_viewer_test.cpp")
            exe = os.path.join(tmp, "viewer.exe" if os.name == "nt" else "viewer")
            if os.name == "nt":
                from test_ps_hid import find_vcvars
                vcvars = find_vcvars()
                clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
                if not vcvars or not os.path.isfile(clang):
                    self.skipTest("no clang-cl / Visual Studio build tools")
                cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W4 '
                       f'"{src}" /Fe:"{exe}" /Fo:"{os.path.join(tmp, "viewer.obj")}"')
                result = subprocess.run(f'cmd /s /c "{cmd}"', cwd=tmp, env=env, capture_output=True,
                                        text=True, timeout=120)
            else:
                compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
                if not compiler:
                    self.skipTest("no C++ compiler")
                result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-pedantic", src, "-o", exe],
                                        cwd=tmp, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([exe], cwd=tmp, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"^PASS \d+ checks\s*$")


if __name__ == "__main__":
    unittest.main()
