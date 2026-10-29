"""tools/flicker_check.py: the dark-frame count over a folder of frames, and the pad scripts it gives the game.
The game run itself is the real test (docs/RENDER_PERF.md "City at Sunset: one black frame at a time")."""
import os
import tempfile
import unittest

from helpers import load_tool

try:
    import numpy as np
except ImportError:            # the dark-frame count needs numpy (a CI runner may not have it)
    np = None

fc = load_tool("flicker_check")


def ppm(path, w, h, rgb_rows):
    """A P6 file whose rows are filled by rgb_rows(y) -> (r, g, b)."""
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        for y in range(h):
            f.write(bytes(rgb_rows(y)) * w)


@unittest.skipIf(np is None, "numpy not installed")
class DarkFrames(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def write(self, n, dark=(), w=128, h=72):
        for i in range(n):
            name = os.path.join(self.d, "frame_%06d_flip%06d.ppm" % (1000 + i, 1000 + i))
            if i in dark:   # the HUD stays at the top and bottom, the middle (the 3D picture) is black
                ppm(name, w, h, lambda y: (200, 200, 200) if y < h // 8 or y > h * 7 // 8 else (0, 0, 0))
            else:
                ppm(name, w, h, lambda y: (150, 120, 90))

    def test_counts_a_frame_that_lost_its_picture(self):
        self.write(10, dark={4, 7})
        n, bad = fc.dark_frames(self.d)
        self.assertEqual(n, 10)
        self.assertEqual([b[0][6:12] for b in bad], ["001004", "001007"])

    def test_steady_frames_and_surface_dumps_are_not_counted(self):
        self.write(6)
        ppm(os.path.join(self.d, "frame_001003_s017F0000.ppm"), 32, 18, lambda y: (0, 0, 0))   # a render target
        n, bad = fc.dark_frames(self.d)
        self.assertEqual((n, bad), (6, []))

    def test_a_dark_scene_that_stays_dark_is_no_flash(self):
        self.write(6, dark={1, 2, 3, 4})   # a fade: no frame is darker than both neighbours by half
        n, bad = fc.dark_frames(self.d)
        self.assertEqual(bad, [])


class Script(unittest.TestCase):
    def test_presses_every_40_frames_from_1450(self):
        s = fc.script(10, ["20", "10"]).split(",")
        self.assertEqual(len(s), 60)
        self.assertEqual(s[:3], ["1460:30:20", "1500:30:10", "1540:30:20"])


if __name__ == "__main__":
    unittest.main()
