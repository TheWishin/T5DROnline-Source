"""tools/hp_bar_check.py's measurement on drawn bars (no game pictures): the dark and orange runs of each bar,
a drain that stalls and steps back counted as reversals, and the frame-for-frame comparison after alignment."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import hp_bar_check as h  # noqa: E402

try:
    import numpy as np
except ImportError:            # the tool needs numpy too
    np = None

DARK, ORANGE, TEAL = (84, 6, 4), (250, 160, 30), (74, 243, 189)


def frame(p1, p2):
    """A 1280x720 picture with both bars: (empty px, orange px) from each bar's outer end, teal for the rest."""
    img = np.zeros((720, 1280, 3), np.uint8)
    for k, (e, o) in (("P1", p1), ("P2", p2)):
        a, b = h.BARS[k]
        a, b = a + 4, b - 4
        cols = list(range(a, b)) if k == "P1" else list(range(b - 1, a - 1, -1))
        for i, x in enumerate(cols):
            img[58:68, x] = DARK if i < e else ORANGE if i < e + o else TEAL
    return img


@unittest.skipIf(np is None, "numpy not installed")
class HpBarCheckTest(unittest.TestCase):
    def test_runs(self):
        r = h.bar_runs(frame((100, 50), (0, 0)))
        self.assertEqual(r["P1"], (100, 50))
        self.assertEqual(r["P2"], (0, 0))
        self.assertEqual(h.bar_runs(frame((0, 0), (30, 77)))["P2"], (30, 77))

    def test_drain_stepping_back_is_a_reversal(self):
        smooth = [h.bar_runs(frame((100 + 3 * i, 30 - 3 * i), (0, 0))) for i in range(10)]
        self.assertEqual(h.reversals(smooth), 0)
        stutter = list(smooth)
        stutter[5] = stutter[3]                 # a rollback put the drain back two steps
        self.assertEqual(h.reversals(stutter), 1)
        diff, n = h.compare(stutter, smooth)
        self.assertEqual((diff, n), (1, 10))

    def test_alignment(self):
        seq = [h.bar_runs(frame((100 + 3 * i, 30 - 3 * i), (i, 0))) for i in range(10)]
        self.assertEqual(h.compare(seq[2:], seq), (0, 8))

    def test_refill_is_not_a_reversal(self):
        seq = [h.bar_runs(frame((300, 0), (0, 0))), h.bar_runs(frame((0, 0), (0, 0)))]
        self.assertEqual(h.reversals(seq), 0)


if __name__ == "__main__":
    unittest.main()
