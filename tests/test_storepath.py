"""The lifted stores' reservation check (ps3recomp patch 0069, docs/RENDER_PERF.md "Lifted code: the guest store's
reservation check", branch store-path-114). No game needed.

* The lifted check reads the reserved-line bitmap through vm_coh_bm_k, a DLL-local view of its address that the
  runtime hands over once (ppu_game_set_coh) before the gates, and tests the line's 1 KB block byte; a block hit
  goes out of line to the runtime's exact check. PPU_NO_COH_LOCAL keeps the 1.1.4 check; PS3_COH_LOCAL=0 sends
  every lifted store out of line.
* The game DLL keeps its store window shut until it has the bitmap (a runtime that never hands it over).
* The proof tools ship with the patch (storepath_diff.py, test_ppu_storepath.py + test_storepath_race.c).
"""
import ast
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT

NAME = "0069-store-path.patch"
PATCH = os.path.join(ROOT, "patches", "ps3recomp", NAME)


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0069 in this checkout")
        self.patch = text("patches", "ps3recomp", NAME)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index(NAME), names.index("0066-lifter-regpromo.patch"))

    def test_files(self):
        files = set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M))
        self.assertEqual(files, {"tools/ppu_lifter.py", "runtime/ppu/ppu_loader.cpp", "runtime/spu/spu_coherency.c",
                                 "runtime/spu/spu_coherency.h", "tools/storepath_diff.py",
                                 "tools/test_ppu_storepath.py", "runtime/ppu/tests/test_storepath_race.c"})

    def test_block_byte_check_with_old_switch(self):
        self.assertIn("+#if defined(PPU_CONST_GATES) && !defined(PPU_NO_COH_LOCAL)", self.patch)
        self.assertIn("+    return __atomic_load_n(&vm_coh_bm_k[ea >> 10], __ATOMIC_RELAXED) != 0;", self.patch)
        # the 1.1.4 check is still there for PPU_NO_COH_LOCAL
        self.assertRegex(self.patch, r"\n[ +]    const unsigned char\* bm = __atomic_load_n\(&vm_coh_bitmap, __ATOMIC_ACQUIRE\);")

    def test_runtime_hands_the_bitmap_before_the_gates(self):
        i = self.patch.index('GetProcAddress(m, "ppu_game_set_coh")')
        j = self.patch.index('GetProcAddress(m, "ppu_game_set_gates")', i)
        self.assertLess(i, j)
        self.assertIn('getenv("PS3_COH_LOCAL")', self.patch)
        self.assertIn("+        if (!vm_coh_bm_k) vm_st_lim_k = 0u;", self.patch)

    def test_no_lifted_game_code(self):
        self.assertLess(len(re.findall(r"func_[0-9A-Fa-f]{8}", self.patch)), 100)


class GameDll(unittest.TestCase):
    def test_store_window_waits_for_the_bitmap(self):
        src = text("tools", "gamedll", "t5dr_game_dll.c")
        self.assertIn("__declspec(dllexport) void ppu_game_set_coh(const unsigned char* bm)", src)
        self.assertIn("vm_st_lim_k = vm_coh_bm_k ? st : 0;", src)


class OptimizedStores(unittest.TestCase):
    """Check the optimized code, where a lost re-check can silently break GETLLAR.

    This also guards the already-shipped 0069 win: no import slot, NULL test or
    per-line bit arithmetic in the DLL's common path. No game data is needed.
    """

    @classmethod
    def setUpClass(cls):
        cls.tree = next((p for p in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp"))
                         if p and os.path.isfile(os.path.join(p, "tools", "ppu_lifter.py"))), None)
        if not cls.tree:
            raise unittest.SkipTest("no prepared ps3recomp tree (PS3RECOMP_DIR)")
        cls.clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                                  if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not cls.clang or os.name != "nt":
            raise unittest.SkipTest("Windows clang-cl code-generation check")
        # Read only the two string constants; do not import/execute the lifter.
        with open(os.path.join(cls.tree, "tools", "ppu_lifter.py"), encoding="utf-8") as f:
            parsed = ast.parse(f.read())
        values = {}

        def value(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value
            if isinstance(node, ast.Name):
                return values[node.id]
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                return value(node.left) + value(node.right)
            raise ValueError("unexpected header constant expression")

        for node in parsed.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in ("FENCE_PREAMBLE", "HEADER_PREAMBLE"):
                    values[name] = value(node.value)
        cls.header = values["HEADER_PREAMBLE"]

    def test_two_atomic_block_reads_survive_optimization(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "ppu_recomp.h"), "w", encoding="utf-8") as f:
                f.write(self.header)
            src = os.path.join(tmp, "probe.c")
            with open(src, "w", encoding="utf-8") as f:
                f.write('#define PPU_CONST_GATES 1\n#define PPU_INLINE_STORES 1\n#include "ppu_recomp.h"\n')
                for width in (8, 16, 32, 64):
                    f.write(f"void probe{width}(uint32_t ea, uint{width}_t v) {{ vm_write{width}(ea, v); }}\n")
            ir_path = os.path.join(tmp, "probe.ll")
            r = subprocess.run([self.clang, "/nologo", "/O2", "/clang:-S", "/clang:-emit-llvm", src,
                                "/Fo:" + ir_path], capture_output=True, text=True, timeout=60, cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(ir_path, encoding="utf-8") as f:
                ir = f.read()
        self.assertRegex(ir, r"@vm_coh_bm_k = external .*constant ptr")
        self.assertNotIn("@vm_coh_bitmap", ir)
        self.assertNotIn("__imp_", ir)
        for width in (8, 16, 32, 64):
            body = re.search(rf"define [^\n]*@probe{width}\([^\n]*\).*?\n\}}", ir, re.S).group()
            reads = list(re.finditer(r"load atomic i8, ptr (%\w+) monotonic", body))
            self.assertEqual(len(reads), 2, body)
            self.assertEqual(reads[0].group(1), reads[1].group(1), body)
            store = re.search(rf"store atomic i{width} ", body)
            fence = body.index('fence syncscope("singlethread") seq_cst')
            self.assertLess(reads[0].start(), store.start(), body)
            self.assertLess(store.start(), fence, body)
            self.assertLess(fence, reads[1].start(), body)
            self.assertIn(f"@vm_write{width}(", body)
            self.assertIn("@vm_store_coh_notify(", body)


if __name__ == "__main__":
    unittest.main()
