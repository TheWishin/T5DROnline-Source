"""1.2.1: the VMX float ops four lanes at a time (ps3recomp patch 0114: runtime/ppu/ppu_vmx.h; docs/RENDER_PERF.md "VMX
float math four lanes at a time"). No game needed.

* The patch: vaddfp, vsubfp, vmaddfp and vnmsubfp get x86-64 vector forms; the scalar loops stay as *_scalar (the
  definition), PPU_VMX_SCALAR keeps them, non-x86 hosts call them.
* tests/c/vmx_vec_test.c, built against a ps3recomp tree with the patch (PS3RECOMP_DIR or deps/ps3recomp) for the
  x86-64 baseline (software FMA) and for x86-64-v3 (vfmadd), compares the vector forms with the scalar loops bit for
  bit: every special triple, millions of random and cancelling operands, VSCR[NJ] off and on, aliased destinations.
  Skipped without a tree or clang-cl; the v3 build only where this PC has AVX2 and FMA.
* Game state: the same bits as before by construction, so CODE_VERSION stays and old and new builds play each other.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0114-vmx-four-lanes.patch")


def find_tree():
    for c in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        if c and os.path.isfile(os.path.join(c, "runtime", "ppu", "ppu_vmx.h")):
            with open(os.path.join(c, "runtime", "ppu", "ppu_vmx.h"), encoding="utf-8", errors="replace") as f:
                if "PPU_VMX_VEC" in f.read():
                    return c
    return None


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0114 in this checkout")
        with open(PATCH, encoding="utf-8") as f:
            self.patch = f.read()

    def test_files(self):
        self.assertEqual(sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M))), ["runtime/ppu/ppu_vmx.h"])

    def test_scalar_forms_kept(self):
        for op in ("vmx_vaddfp", "vmx_vsubfp", "vmx_vmaddfp", "vmx_vnmsubfp"):
            self.assertIn(op + "_scalar", self.patch, op)
        self.assertIn("+#if defined(PPU_FP_X64) && !defined(PPU_VMX_SCALAR)", self.patch)

    def test_no_guest_memory(self):
        add = "\n".join(ln[1:] for ln in self.patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
        for word in ("vm_write", "vm_read", "ctx->", "getenv"):
            self.assertNotIn(word, add, word)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0114-vmx-four-lanes.patch"), names.index("0104-low-end.patch"))


class Bits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0114 (PS3RECOMP_DIR)")
        if os.name != "nt":
            raise unittest.SkipTest("Windows test (clang-cl, QueryPerformanceCounter)")
        cls.clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                                 if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not cls.clang:
            raise unittest.SkipTest("no clang-cl")

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name
        self.addCleanup(self._td.cleanup)

    def build(self, name, march=None):
        exe = os.path.join(self.tmp, name + ".exe")
        cmd = [self.clang, "/nologo", "/O2", "/W0", "/clang:-ffp-contract=off",
               "/I", os.path.join(self.tree, "runtime", "ppu"), os.path.join(ROOT, "tests", "c", "vmx_vec_test.c"),
               "/Fe:" + exe, "/Fo:" + os.path.join(self.tmp, name + ".obj")]
        if march:
            cmd.insert(5, "/clang:-mavx" if march == "avx" else "/clang:-march=" + march)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=self.tmp)
        if not os.path.isfile(exe):
            self.fail("vmx_vec_test did not build: " + (r.stdout + r.stderr)[-600:])
        return exe

    def check(self, exe):
        r = subprocess.run([exe, "check", "4000000"], capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:])
        self.assertRegex(r.stdout, r"\d+ cases .*differ 0")

    def test_baseline_same_bits(self):
        self.check(self.build("base"))

    def test_v3_same_bits(self):
        import ctypes
        k = ctypes.windll.kernel32
        if not (k.IsProcessorFeaturePresent(40)):          # PF_AVX2_INSTRUCTIONS_AVAILABLE
            self.skipTest("no AVX2 here")
        self.check(self.build("v3", "x86-64-v3"))

    def test_avx_without_fma_same_bits(self):
        import ctypes
        if not ctypes.windll.kernel32.IsProcessorFeaturePresent(39):  # PF_AVX_INSTRUCTIONS_AVAILABLE
            self.skipTest("no OS-enabled AVX here")
        self.check(self.build("avx", "avx"))


if __name__ == "__main__":
    unittest.main()
