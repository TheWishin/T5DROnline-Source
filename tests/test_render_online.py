"""Renderer side of online play and the resource binding tier-1 path (ps3recomp patch 0081, docs/RENDER_PERF.md
"Online pictures and old graphics cards (1.1.5, patch 0081)"). No game needed: the patch's switches and what it may
touch.

* A draw the renderer cannot make (no topology for its primitive type) is named with where the FIFO walker found
  it and the ring words around it, and stamped in the latency log ('Z'), so it can be lined up with rollbacks.
* The tier-1 path (on by default with resource binding tier 1, RSX_TIER1_PATH=1/0 forces it) changes only host
  binding work: texture units the fragment program does not sample are not bound, a draw that differs from the one
  before it only in such units keeps that draw's table, and the main descriptor heaps are set once per command
  list. Tier 2/3 behaviour is the same as before (the switch is off there).
* RSX_FX_COUNT=1 (diagnostics, off by default) stamps the effect draws of every present in the latency log ('H').
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

    def test_tables_kept_only_for_unsampled_units(self):
        add = self.added()
        self.assertIn("if (fp_reads != 0xFFFFu) {", add)   # tier-1 path only
        # a sampled unit must match exactly; an unsampled one may differ (texture: a guest texture or white only,
        # and only while no texture descriptor was written since)
        self.assertIn("srv_same &= slots[u] == prev.srv[u];", add)
        self.assertIn("srv_same &= ps == SRV_WHITE || (ps >= SRV_TEXTURE_BASE && ps < SRV_VTEX_BASE);", add)
        self.assertIn("int srv_same = prev.gen == g_ld_srv_gen, smp_same = 1;", add)
        self.assertIn("tables kept", add)

    def test_effect_counts_off_by_default(self):
        add = self.added()
        self.assertIn('getenv("RSX_FX_COUNT")', add)
        self.assertIn("lat_log('H'", add)   # 'Y' is patch 0080's skipped tick
        self.assertNotIn("lat_log('Y'", add)

    def test_no_pacing_change(self):
        # the vblank / flip-completion experiments of this branch are not in the patch (docs/RENDER_PERF.md)
        add = self.added()
        for word in ("PS3_VBLANK_PER_FRAME", "PS3_FLIP_DONE_NEEDS_FLIP", "GCM_PENDING_SET", "cellGcm_skip_ticks"):
            self.assertNotIn(word, add, word)

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
        self.assertIn(" binding %.0f draws, tables set %.0f", add)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0081-render-online.patch"), names.index("0079-graphics-settings.patch"))


if __name__ == "__main__":
    unittest.main()
