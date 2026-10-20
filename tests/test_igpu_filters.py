"""The cheaper GPU paths of ps3recomp patch 0051 (docs/RENDER_PERF.md "GPU time on integrated
graphics"): the guest-size view of a scaled surface (patch 0043's box filter) and the present's
downscale (patch 0038) read pairs of texels with one bilinear tap between their centres. These
tests emulate exact bilinear sampling on random textures and check that every tap layout the
shaders use gives the same box average as the loop / the n x n taps it replaces; the in-game
check (RSX_FAST_SELFCHECK=1, both paths on the same frame) is in the doc. No game or GPU needed."""
import os
import random
import re
import unittest

from helpers import ROOT

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0051-igpu-perf.patch")


def bilinear(img, u, v):
    """Exact bilinear sample at texel-space position (u, v) (texel i spans [i, i+1), centre i+0.5)."""
    x, y = u - 0.5, v - 0.5
    x0, y0 = int(x // 1), int(y // 1)
    fx, fy = x - x0, y - y0
    h, w = len(img), len(img[0])

    def t(ix, iy):
        return img[min(max(iy, 0), h - 1)][min(max(ix, 0), w - 1)]
    return ((t(x0, y0) * (1 - fx) + t(x0 + 1, y0) * fx) * (1 - fy) +
            (t(x0, y0 + 1) * (1 - fx) + t(x0 + 1, y0 + 1) * fx) * fy)


def box(img, x0, y0, n):
    return sum(img[y][x] for y in range(y0, y0 + n) for x in range(x0, x0 + n)) / (n * n)


def loop_view(img, gx, gy, ratio):
    """Patch 0043's loop: area-weighted mean of the host texels under [g, g+1) * ratio."""
    h, w = len(img), len(img[0])
    lo_x, lo_y = gx * ratio, gy * ratio
    hi_x, hi_y = lo_x + ratio, lo_y + ratio
    acc = ws = 0.0
    y = int(lo_y // 1)
    while y <= min(int(-(-hi_y // 1)) - 1, h - 1):
        wy = min(hi_y, y + 1.0) - max(lo_y, float(y))
        x = int(lo_x // 1)
        while x <= min(int(-(-hi_x // 1)) - 1, w - 1):
            wx = min(hi_x, x + 1.0) - max(lo_x, float(x))
            acc += img[y][x] * wy * wx
            ws += wy * wx
            x += 1
        y += 1
    return acc / ws


class Filters(unittest.TestCase):
    def setUp(self):
        rnd = random.Random(51)
        self.img = [[rnd.randint(0, 255) / 255.0 for _ in range(48)] for _ in range(48)]

    def test_guest_view_pairs_equal_the_box(self):
        img = self.img
        for gy in range(0, 8):
            for gx in range(0, 8):
                # 2x: one tap at the 2x2 block's centre
                b = (2 * gx, 2 * gy)
                self.assertAlmostEqual(bilinear(img, b[0] + 1.0, b[1] + 1.0), box(img, b[0], b[1], 2), places=12)
                # 4x: four taps at the 2x2 quads' centres
                b = (4 * gx, 4 * gy)
                four = sum(bilinear(img, b[0] + dx, b[1] + dy) for dx in (1, 3) for dy in (1, 3)) * 0.25
                self.assertAlmostEqual(four, box(img, b[0], b[1], 4), places=12)
                # 3x: a pair (centre +1.0) and a single (centre +2.5) per axis, weighted 4:2:2:1
                b = (3 * gx, 3 * gy)
                pp = bilinear(img, b[0] + 1.0, b[1] + 1.0)
                sp = bilinear(img, b[0] + 2.5, b[1] + 1.0)
                ps = bilinear(img, b[0] + 1.0, b[1] + 2.5)
                ss = bilinear(img, b[0] + 2.5, b[1] + 2.5)
                self.assertAlmostEqual((pp * 4 + sp * 2 + ps * 2 + ss) / 9.0, box(img, b[0], b[1], 3), places=12)
                # and the loop gives the same box at these factors
                for r in (2, 3, 4):
                    self.assertAlmostEqual(loop_view(img, gx, gy, float(r)), box(img, r * gx, r * gy, r), places=12)

    def test_guest_view_one_and_a_half(self):
        """1.5x: always exactly 2 x 2 host texels, weights 1 / 0.5 -- what the unrolled path reads."""
        img = self.img
        for gy in range(0, 12):
            for gx in range(0, 12):
                lo_x, lo_y = gx * 1.5, gy * 1.5
                ax, ay = int(lo_x // 1), int(lo_y // 1)
                wx = [min(lo_x + 1.5, ax + 1.0) - max(lo_x, float(ax)), min(lo_x + 1.5, ax + 2.0) - max(lo_x, ax + 1.0)]
                wy = [min(lo_y + 1.5, ay + 1.0) - max(lo_y, float(ay)), min(lo_y + 1.5, ay + 2.0) - max(lo_y, ay + 1.0)]
                acc = sum(img[ay + j][ax + i] * wy[j] * wx[i] for j in (0, 1) for i in (0, 1))
                ws = sum(wy[j] * wx[i] for j in (0, 1) for i in (0, 1))
                self.assertAlmostEqual(ws, 2.25)
                self.assertAlmostEqual(acc / ws, loop_view(img, gx, gy, 1.5), places=12)

    def test_present_pairs_equal_the_n_by_n_taps(self):
        """The present at an integer ratio n: uv at the window pixel's centre; the old shader took
        n x n taps at the source texel centres, the new one pairs around the centre."""
        img = self.img
        for n in (2, 3, 4):
            for py in range(0, 40 // n):
                for px in range(0, 40 // n):
                    cx, cy = n * px + n / 2.0, n * py + n / 2.0        # texel-space centre of the footprint
                    old = sum(bilinear(img, cx - 0.5 * (n - 1) + i, cy - 0.5 * (n - 1) + j)
                              for j in range(n) for i in range(n)) / (n * n)

                    def s(dx, dy):
                        return bilinear(img, cx + dx, cy + dy)
                    if n == 2:
                        new = s(0, 0)
                    elif n == 4:
                        new = (s(-1, -1) + s(1, -1) + s(-1, 1) + s(1, 1)) * 0.25
                    else:
                        new = (s(-0.5, -0.5) * 4 + s(1, -0.5) * 2 + s(-0.5, 1) * 2 + s(1, 1)) / 9.0
                    self.assertAlmostEqual(new, old, places=12, msg=f"{n}x at {px},{py}")

    def test_the_patch_has_these_layouts_and_switches(self):
        with open(PATCH, encoding="utf-8") as f:
            p = f.read()
        for want in ("RSX_GPU_PASSES", "RSX_GVIEW_FAST", "RSX_PRESENT_FAST", "RSX_SMALL_TARGETS_NATIVE",
                     "RSX_FAST_SELFCHECK", "host_sched_laptop()", "(b + float2(2.5, 1.0)) * t",
                     "tap_step * float2(1.0, -0.5)", "g_ld_vendor == 0x1002u"):
            self.assertIn(want, p)
        # the per-pass report line the docs quote
        self.assertTrue(re.search(r'"\[gpu-pass\] %u frames, %\.3f ms GPU per frame', p))


if __name__ == "__main__":
    unittest.main()
