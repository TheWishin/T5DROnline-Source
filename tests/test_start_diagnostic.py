"""Exercise the actual local START filter with fake mapped pad samples.

No game data or patched runtime is needed. The C++ harness checks suppression,
forwarding, other buttons/axes and bounded diagnostic output. It fails against
the old pad_into implementation because hardware START was suppressed silently.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars


class StartDiagnosticTest(unittest.TestCase):
    def test_mapped_start_reports_the_gate_without_changing_inputs(self):
        if os.name != "nt":
            self.skipTest("built with clang-cl and Visual Studio build tools")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        if not vcvars or not os.path.isfile(clang):
            self.skipTest("no clang-cl / Visual Studio build tools")
        with open(os.path.join(ROOT, "src", "netplay", "netplay_core.cpp"), encoding="utf-8") as f:
            core = f.read()
        start = core.index("std::atomic<bool> g_no_start")
        end = core.index("/* This PC's devices", start)
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "pad_into_under_test.h"), "w", encoding="utf-8") as f:
                f.write(core[start:end])
            exe = os.path.join(tmp, "start_diagnostic_test.exe")
            src = os.path.join(ROOT, "tests", "c", "start_diagnostic_test.cpp")
            cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O1 /W3 '
                   f'/I "{tmp}" "{src}" /Fe:"{exe}" /Fo:"{os.path.join(tmp, "test.obj")}"')
            built = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
            self.assertTrue(os.path.isfile(exe), (built.stdout + built.stderr)[-3000:])
            result = subprocess.run([exe], capture_output=True, text=True, timeout=60, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS mapped START diagnostics and unchanged inputs", result.stdout)


if __name__ == "__main__":
    unittest.main()
