"""The lifted stores' reservation check (ps3recomp patch 0069, docs/RENDER_PERF.md "Lifted code: the guest store's
reservation check", branch store-path-114). No game needed.

* The lifted check reads the reserved-line bitmap through vm_coh_bm_k, a DLL-local view of its address that the
  runtime hands over once (ppu_game_set_coh) before the gates, and tests the line's 1 KB block byte; a block hit
  goes out of line to the runtime's exact check. PPU_NO_COH_LOCAL keeps the 1.1.4 check; PS3_COH_LOCAL=0 sends
  every lifted store out of line.
* The game DLL keeps its store window shut until it has the bitmap (a runtime that never hands it over).
* The proof tools ship with the patch (storepath_diff.py, test_ppu_storepath.py + test_storepath_race.c).
"""
import os
import re
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


if __name__ == "__main__":
    unittest.main()
