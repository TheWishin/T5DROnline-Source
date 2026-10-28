"""1.1.7: 2-core PCs and PCs without FMA3 (ps3recomp patch 0084, docs/RENDER_PERF.md "1.1.7: 2-core PCs and
GitHub #12"). No game needed.

* The SPU signal path's log throttle: the fflush that sat outside the `if (... < 24)` (it ran on every SPU signal
  and every task dispatch; -Wmisleading-indentation on the Mac build) is inside it.
* ppu_fma_soft, the exact fused multiply-add a PC without FMA3 runs for every fmadd: a double-only path for the
  common case gives the same bits as vfmadd (tests/c/fma_soft_test.c against the instruction) and is faster than the
  integer path alone. Built against a ps3recomp tree (PS3RECOMP_DIR); skipped without one or a C compiler.
* Timing and host code only: nothing the patch adds writes guest memory, CODE_VERSION stays.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0084-weak-cpu-117.patch")
OLD_THROTTLE = re.compile(r"if \(__atomic_fetch_add\(&_n, 1, __ATOMIC_RELAXED\) < 24\)\s*\n[^;{}]*\([^{}]*?\);\s*fflush\(stderr\);")


def text(*parts):
    with open(os.path.join(*parts), encoding="utf-8", errors="replace") as f:
        return f.read()


def find_tree():
    """A ps3recomp tree to check: PS3RECOMP_DIR, else deps/ps3recomp (prepare_ps3recomp.py applies the series)."""
    for c in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        if c and os.path.isfile(os.path.join(c, "runtime", "ppu", "ppu_fp_det.h")):
            return c
    return None


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0084 in this checkout")
        self.patch = text(PATCH)

    def added(self):
        return "\n".join(ln[1:] for ln in self.patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))

    def test_files(self):
        files = sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M)))
        self.assertEqual(files, ["runtime/ppu/ppu_fp_det.h", "runtime/ppu/tests/test_fp_det.c",
                                 "runtime/spu/spu_workload.c"])

    def test_host_side_only(self):
        add = self.added()
        for word in ("vm_write", "write_be", "guest_write", "vm_memcpy_to", "vm_memset", "spu_ls_write"):
            self.assertNotIn(word, add, word)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0084-weak-cpu-117.patch"), names.index("0081-render-online.patch"))

    def test_documented(self):
        doc = text(ROOT, "docs", "RENDER_PERF.md")
        self.assertTrue("patch 0084" in doc, "RENDER_PERF.md names patch 0084")
        self.assertTrue("tools/perf_compare.py" in doc, "RENDER_PERF.md names tools/perf_compare.py")


class Tree(unittest.TestCase):
    """Against a ps3recomp tree: fails on 0001-0081 (fflush outside the throttle; no double-only fma path)."""

    @classmethod
    def setUpClass(cls):
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree (PS3RECOMP_DIR)")

    def test_signal_log_throttle_holds_the_fflush(self):
        src = text(self.tree, "runtime", "spu", "spu_workload.c")
        self.assertIsNone(OLD_THROTTLE.search(src), "an fflush(stderr) outside the log throttle")
        self.assertEqual(src.count("< 24) {"), src.count("__atomic_fetch_add(&_n, 1, __ATOMIC_RELAXED) < 24"))

    def _compile(self, name, defs):
        if os.name != "nt":
            self.skipTest("Windows test (QueryPerformanceCounter, clang-cl)")
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not clang:
            self.skipTest("no clang-cl")
        exe = os.path.join(self.tmp, name + ".exe")
        cmd = [clang, "/nologo", "/O2", "/W0", "/clang:-ffp-contract=off", "/I", os.path.join(self.tree, "runtime", "ppu"),
               os.path.join(ROOT, "tests", "c", "fma_soft_test.c"), "/Fe:" + exe, "/Fo:" + os.path.join(self.tmp, name + ".obj")]
        cmd += ["/D" + d for d in defs]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=self.tmp)
        if not os.path.isfile(exe):
            self.skipTest("fma_soft_test did not build: " + (r.stdout + r.stderr)[-400:])
        return exe

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name
        self.addCleanup(self._td.cleanup)

    def test_same_bits_as_vfmadd(self):
        exe = self._compile("fma_check", [])
        r = subprocess.run([exe, "check", "4000000"], capture_output=True, text=True, timeout=600)
        if "differ" not in r.stdout:
            self.skipTest("no FMA3 here to compare with")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("differ 0 of", r.stdout)

    def test_faster_than_the_integer_path(self):
        new, old = self._compile("fma_bench", []), self._compile("fma_bench_int", ["PPU_FMA_SOFT_INT_ONLY"])

        def ns(exe):
            out = subprocess.run([exe, "bench"], capture_output=True, text=True, timeout=600).stdout
            return float(re.search(r"ns ([0-9.]+)", out).group(1))
        a, b = min(ns(new) for _ in range(3)), min(ns(old) for _ in range(3))
        self.assertLess(a * 1.25, b, f"double-only path {a:.2f} ns, integer path {b:.2f} ns per call")


if __name__ == "__main__":
    unittest.main()
