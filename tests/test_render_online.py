"""Renderer side of online play and the resource binding tier-1 path (ps3recomp patch 0081, docs/RENDER_PERF.md
"Online pictures and old graphics cards (1.1.5, patch 0081)"). No game needed: the patch's switches and what it may
touch.

* A draw the renderer cannot make (no topology for its primitive type) is named with where the FIFO walker found
  it and the ring words around it, and stamped in the latency log ('Z'), so it can be lined up with rollbacks.
* The tier-1 path (on by default with resource binding tier 1, RSX_TIER1_PATH=1/0 forces it) changes only host
  binding work: texture units the fragment program does not sample are not bound, and the main descriptor heaps
  are set once per command list. Tier 2/3 behaviour is the same as before (the switch is off there).
* Nothing it adds writes guest memory or the command stream: the two players of a match may differ.
"""
import os
import re
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0081-render-online.patch")


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0081 in this checkout")
        with open(PATCH, encoding="utf-8") as f:
            self.patch = f.read()

    def added(self):
        return "\n".join(ln[1:] for ln in self.patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))

    def test_vblank_per_frame(self):
        add = self.added()
        self.assertIn("void cellGcm_set_vblank_pace(u32 interval_ea)", add)
        self.assertIn('getenv("PS3_VBLANK_PER_FRAME")', add)
        # on with a title word, the switch wins either way
        self.assertIn("vpf = e && *e ? *e != '0' : s_vpf_interval_ea != 0;", add)
        # the title's interval, clamped to 1..4; a vblank beyond it within 100 ms of the frame's flip request is held
        self.assertIn("if (iv < 1u) iv = 1u; else if (iv > 4u) iv = 4u;", add)
        self.assertIn("if (vpf_n >= iv && now - vpf_t < 100) {", add)
        self.assertIn("InterlockedExchange(&s_vpf_owed, 1);", add)
        # ... and passed on at the next flip request (pacing kept): the request marks it pending, the pump delivers it
        self.assertIn("if (s_vpf_owed) GCM_PENDING_SET(1);", add)
        self.assertIn("if (InterlockedExchange(&s_vpf_owed, 0)) p |= 1;", add)

    def test_the_game_names_its_interval(self):
        with open(os.path.join(ROOT, "src", "perf", "t5_vblank.cpp"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("constexpr uint32_t kFlipInterval = 0x106D4D9Cu;", src)
        self.assertIn("cellGcm_set_vblank_pace(kFlipInterval);", src)

    def test_only_the_renderer(self):
        files = sorted(set(re.findall(r"^diff --git a/(\S+) ", self.patch, re.M)))
        self.assertEqual(files, ["libs/video/cellGcmSys.c", "libs/video/rsx_live_draw.c"])

    def test_tier1_switch(self):
        add = self.added()
        self.assertIn('getenv("RSX_TIER1_PATH")', add)
        # default: on only with resource binding tier 1
        self.assertIn("g_ld_t1 = e && *e ? *e != '0' : g_ld_bind_tier == 1;", add)
        self.assertIn("[gpu] tier-1 binding path:", add)
        # off: every unit is bound (0xFFFF) and every heap call is made, as before
        self.assertIn("const u32 fp_reads = ld_tier1_path() ? g_ld_current_pso.fp_tex_mask : 0xFFFFu;", add)
        self.assertIn("if (g_ld_heaps_main && ld_tier1_path()) return;", add)

    def test_heaps_forgotten_with_the_list_and_the_present(self):
        add = self.added()
        self.assertEqual(add.count("g_ld_heaps_main = 0;"), 3)   # two list resets, the present's own heap
        self.assertNotIn("SetDescriptorHeaps(LDL, 2, heaps)", add)

    def test_dropped_draw_notes(self):
        add = self.added()
        self.assertIn('getenv("RSX_PRIM_NOTES")', add)
        self.assertIn("lat_log('Z'", add)
        self.assertIn("ring at 0x%X:", add)

    def test_host_side_only(self):
        add = self.added()
        for word in ("vm_write", "guest_write", "write_be", "wr32(", "rsx_dsp_set", "g.rsx.regs[", "g.rsx.constants["):
            self.assertNotIn(word, add, word)

    def test_binding_work_in_the_gpu_pass_line(self):
        add = self.added()
        self.assertIn(" | binding per frame: %.0f draws, tables set %.0f", add)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0081-render-online.patch"), names.index("0079-graphics-settings.patch"))


if __name__ == "__main__":
    unittest.main()
