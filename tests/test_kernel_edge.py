"""Patch 0106 (Moonlit Wilderness' black line, docs/MOONLIT_WILDERNESS.md): a filter kernel that reads a render
target whose draws this frame left an undrawn margin reads it through the guest-size view with the margin filled
by the last drawn row / column. Game-free checks of the patch text and a numeric model of the view's clamp."""
import os
import re
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0106-kernel-edge.patch")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Patch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(PATCH):
            raise unittest.SkipTest("patch 0106 not in this tree")
        cls.patch = text("patches", "ps3recomp", "0106-kernel-edge.patch")
        cls.added = "\n".join(l[1:] for l in cls.patch.splitlines() if l.startswith("+") and not l.startswith("+++"))

    def test_one_file(self):
        self.assertEqual(re.findall(r"(?m)^diff --git a/(\S+)", self.patch), ["libs/video/rsx_live_draw.c"])

    def test_view_clamps_first(self):
        # the clamp comes before anything reads the position; inside the drawn part it is a no-op
        self.assertIn("pos.xy = min(floor(pos.xy), lim) + 0.5;", self.added)
        self.assertIn("float fast; float2 lim; };", self.added)
        self.assertIn("Num32BitValues = 7;", self.added)
        self.assertIn("SetGraphicsRoot32BitConstants(LDL, 1, 7, k, 0);", self.added)
        self.assertNotIn("SetGraphicsRoot32BitConstants(LDL, 1, 5, k, 0);",
                         "\n".join(l for l in self.patch.splitlines() if l.startswith(" ")))

    def test_only_kernels_with_blur_on(self):
        # the view is asked for only where 0043 asked (a filter kernel, stage blur on), now also at Native when
        # the draws left a margin; never below Native
        self.assertIn("g.surfaces[sampled].scale == 1.0f && ld_kernel_edge((u32)sampled)", self.added)
        self.assertIn("if (g_ld_stage_blur && (g.surfaces[sampled].scale > 1.0f ||", self.added)
        self.assertIn("(s->scale <= 1.0f && !(lim && s->scale == 1.0f))", self.added)

    def test_switch_and_cache(self):
        self.assertIn('getenv("RSX_KERNEL_EDGE")', self.added)
        self.assertIn("s->gv_lim == lim", self.added)          # a view made for another edge is made again
        self.assertIn("s->gv_lim = lim;", self.added)

    def test_extent_is_this_frames(self):
        self.assertIn("es->ext_frame != g_ld_frames + 1u", self.added)
        self.assertIn("s->ext_frame != g_ld_frames + 1u", self.added)

    def test_documented(self):
        doc = text("docs", "MOONLIT_WILDERNESS.md")
        for want in ("patch 0106", "RSX_KERNEL_EDGE=0", "Stage blur / glow On", "1536 x 1280"):
            self.assertIn(want, doc)
        self.assertIn("MOONLIT_WILDERNESS.md", text("docs", "RENDER_PERF.md"))


def view_texel(x, y, lim):
    """The view's texel position for output pixel (x, y), as the shader computes it."""
    return min(x, lim[0]), min(y, lim[1])


class ClampModel(unittest.TestCase):
    def test_inside_unchanged_margin_repeats_the_edge(self):
        lim = (1535, 1279)                       # Moonlit: drawn 1536 x 1280 of 2048 x 1440
        for x, y in ((0, 0), (1535, 1279), (700, 1279), (1535, 3)):
            self.assertEqual(view_texel(x, y, lim), (x, y))
        self.assertEqual(view_texel(1536, 1280, lim), (1535, 1279))
        self.assertEqual(view_texel(2047, 100, lim), (1535, 100))
        self.assertEqual(view_texel(10, 1439, lim), (10, 1279))

    def test_no_margin_no_clamp(self):
        # 65535 is sent when the draws reached the whole surface
        for x, y in ((0, 0), (2047, 1439)):
            self.assertEqual(view_texel(x, y, (65535, 65535)), (x, y))


if __name__ == "__main__":
    unittest.main()
