"""The game's netplay packet parser (src/netplay/netplay_core.cpp) against strangers and a hostile
opponent: tests/c/netplay_fuzz.cpp includes the parser, feeds it crafted and random packets in one
process (no socket, no network) and checks the security properties listed at its top. Built with
clang-cl and AddressSanitizer when the LLVM install has the ASan runtime, else without it.
Windows only (the parser uses Winsock types); skipped without a C++ compiler."""
import glob
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars

LLVM = r"C:\Program Files\LLVM"


def asan_runtime_dir(clang):
    base = os.path.join(os.path.dirname(os.path.dirname(clang)), "lib", "clang")
    for d in sorted(glob.glob(os.path.join(base, "*", "lib", "windows")), reverse=True):
        if os.path.isfile(os.path.join(d, "clang_rt.asan_dynamic-x86_64.dll")):
            return d
    return None


class NetplayParserFuzz(unittest.TestCase):
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
        cls.asan = asan_runtime_dir(clang)
        exe = os.path.join(cls.tmp.name, "netplay_fuzz.exe")
        src = os.path.join(ROOT, "tests", "c", "netplay_fuzz.cpp")
        inc = os.path.join(ROOT, "src", "netplay")
        flags = "/fsanitize=address /Zi" if cls.asan else ""
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O1 /W0 {flags} /I "{inc}" "{src}" '
               f'/Fe:"{exe}" /Fo:"{os.path.join(cls.tmp.name, "netplay_fuzz.obj")}" /link ws2_32.lib')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=900)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/netplay_fuzz.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def run_harness(self, iterations):
        env = dict(os.environ)
        if self.asan:
            env["PATH"] = self.asan + os.pathsep + env.get("PATH", "")
            env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1"
        return subprocess.run([self.exe, str(iterations)], capture_output=True, text=True, timeout=600,
                              cwd=self.tmp.name, env=env)

    def test_security_checks_and_fuzz(self):
        r = self.run_harness(200000)
        out = r.stdout[-3000:] + r.stderr[-3000:]
        self.assertEqual(r.returncode, 0, out)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", out)
        self.assertNotIn("AddressSanitizer", r.stderr)


if __name__ == "__main__":
    unittest.main()
