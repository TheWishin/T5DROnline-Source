"""The lifted code's floating point gives the same bits on every build and host
(tools/fp_vectors.py; docs/MACOS.md "Determinism across operating systems and
CPUs"; docs/NETPLAY.md "Same game state on every CPU").

On x86-64 Windows: the baseline build, the x86-64-v3 build (FMA3 instructions)
and the baseline build running the software fma (as on a CPU without FMA3) all
match tests/data/fp_vectors_x64.txt. On any other host (a Mac) the same
comparison runs and names the instructions that differ from x86-64 -- the list
the macOS port has to bring to zero before a Mac may play a PC online.

Needs a ps3recomp checkout (PS3RECOMP_DIR or deps/ps3recomp) and a compiler:
clang-cl in the MSVC environment on Windows (found through vswhere when the
environment is not set up), clang++ elsewhere. Skipped without them.
"""
import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT, PY

TOOL = os.path.join(ROOT, "tools", "fp_vectors.py")
REF = os.path.join(ROOT, "tests", "data", "fp_vectors_x64.txt")


def find_ps3recomp():
    for c in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        if c and os.path.isfile(os.path.join(c, "tools", "ppu_lifter.py")) and \
                os.path.isfile(os.path.join(c, "runtime", "ppu", "ppu_fp_det.h")):
            return c
    return None


def find_vcvars():
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = os.path.join(pf86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if os.path.isfile(vswhere):
        r = subprocess.run([vswhere, "-latest", "-products", "*", "-property", "installationPath"],
                           capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            p = os.path.join(line.strip(), "VC", "Auxiliary", "Build", "vcvars64.bat")
            if os.path.isfile(p):
                return p
    return None


def is_x64():
    return platform.machine().lower() in ("amd64", "x86_64")


def has_avx2():
    if os.name == "nt":
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))   # PF_AVX2_INSTRUCTIONS_AVAILABLE
    try:
        with open("/proc/cpuinfo") as f:
            return " avx2 " in f.read()
    except OSError:
        r = subprocess.run(["sysctl", "-n", "machdep.cpu.leaf7_features"], capture_output=True, text=True)
        return "AVX2" in r.stdout


class FpVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp checkout (set PS3RECOMP_DIR)")
        cls.prefix = []
        if os.name == "nt":
            if not (shutil.which("clang-cl") or os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe")):
                raise unittest.SkipTest("no clang-cl")
            if not os.environ.get("INCLUDE"):
                vcvars = find_vcvars()
                if not vcvars:
                    raise unittest.SkipTest("no MSVC environment (vcvars64.bat)")
                cls.vcvars = vcvars
        elif not (shutil.which("clang++") or shutil.which("c++")):
            raise unittest.SkipTest("no C++ compiler")
        cls.work = tempfile.mkdtemp(prefix="fpv_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "work", ""), ignore_errors=True)

    def run_tool(self, *args):
        argv = [PY, TOOL, "--ps3recomp", self.tree, "--out", self.work, "--compare", REF, *args]
        if os.name == "nt" and getattr(self, "vcvars", None):
            cmd = '"%s" >nul 2>&1 && %s' % (self.vcvars, subprocess.list2cmdline(argv))
            r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, errors="replace", timeout=900)
        else:
            r = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=900)
        return r

    def test_reference_is_complete(self):
        with open(REF, encoding="utf-8") as f:
            lines = [l for l in f if l.strip() and not l.startswith("#")]
        self.assertGreaterEqual(len(lines), 50)

    def test_baseline_build_matches_reference(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_fma3_build_matches_reference(self):
        if not is_x64() or not has_avx2():
            self.skipTest("x86-64-v3 needs an x86-64 CPU with AVX2")
        r = self.run_tool("--march", "x86-64-v3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_software_fma_matches_reference(self):
        if not is_x64():
            self.skipTest("the software fma path is the x86-64 baseline build's")
        r = self.run_tool("--soft-fma")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
