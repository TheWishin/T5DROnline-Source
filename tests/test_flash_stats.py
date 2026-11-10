"""tools/flash_stats.py: the dark-frame count over the game's flash-check file (ps3recomp patch 0124), the two
pictures of a frame kept apart, the rollbacks next to a dark frame; and the patch has the pieces the tool
and docs/RENDER_PERF.md name. The game run itself is the real test."""
import contextlib
import io
import os
import tempfile
import unittest

from helpers import ROOT, load_tool

fs = load_tool("flash_stats")
PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0124-flash-check.patch")


def stats(path, n, dark=(), window_dark=(), skip=()):
    with open(path, "w") as f:
        for i in range(n):
            if i in skip:
                continue
            qpc = 1000000000 + i * 166833
            f.write("frame_%06d_flip%06d.ppm,%d,%.2f,90.00,0.0100\n" % (500 + i, 400 + i, qpc, 3.0 if i in dark else 120.0))
            f.write("frame_%06d_flip%06d_bb.ppm,%d,%.2f,90.00,0.0100\n"
                    % (500 + i, 400 + i, qpc + 50, 2.0 if i in window_dark else 118.0))


class FlashStats(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.csv = os.path.join(self.d, "flash.csv")

    def run_tool(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = fs.main(["flash_stats.py", *args])
        return rc, out.getvalue()

    def test_clean_run(self):
        stats(self.csv, 60)
        rc, text = self.run_tool(self.csv)
        self.assertEqual(rc, 0)
        self.assertIn("game  : 60 pictures (0 not read back)", text)
        self.assertIn("window: 60 pictures", text)
        self.assertIn(": 0 dark", text)

    def test_the_two_pictures_are_counted_apart(self):
        stats(self.csv, 60, dark={10, 30}, window_dark={10, 30, 44})
        kinds = fs.read_stats(self.csv)
        self.assertEqual([r[0] for r in fs.classify(kinds["game"])[0]], [510, 530])
        self.assertEqual([r[0] for r in fs.classify(kinds["window"])[0]], [510, 530, 544])
        rc, _ = self.run_tool(self.csv)
        self.assertEqual(rc, 1)

    def test_a_dark_stretch_is_no_flash(self):
        stats(self.csv, 60, dark=set(range(20, 40)))     # a fade or a dark scene: its neighbours are dark too
        self.assertEqual(fs.classify(fs.read_stats(self.csv)["game"])[0], [])

    def test_missing_pictures_are_reported(self):
        stats(self.csv, 60, skip={7, 8})
        self.assertEqual(fs.classify(fs.read_stats(self.csv)["game"])[2], 2)

    def test_rollbacks_next_to_a_dark_frame(self):
        stats(self.csv, 60, dark={10})
        lat = os.path.join(self.d, "lat.log")
        t = 1000000000 + 10 * 166833
        with open(lat, "w") as f:
            f.write("# qpc_frequency=10000000\n")
            f.write("M %d 910 905 0.45\nQ %d 910 905 21.30 9.80\nP %d 410 510 510 0\nM %d 930 928 0.40\n"
                    % (t - 30000, t - 10000, t, t + 500000))
        rc, text = self.run_tool(self.csv, lat)
        self.assertEqual(rc, 1)
        self.assertIn("2 rollbacks", text)
        self.assertIn("M-3.0ms(910 905 0.45)", text)
        self.assertIn("Q-1.0ms(910 905 21.30 9.80)", text)
        self.assertIn("M+50.0ms(930 928 0.40)", text)

    def test_junk_lines_and_an_empty_file(self):
        with open(self.csv, "w") as f:
            f.write("not a line\nframe_x,1,2,3,4\nframe_000001_flip000001.ppm,abc,1,2,3\n")
        rc, _ = self.run_tool(self.csv)
        self.assertEqual(rc, 2)


class Patch(unittest.TestCase):
    def test_the_patch_has_the_switches(self):
        with open(PATCH, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for word in ("RSX_FLASH_CHECK", "LD_FRAME_DUMP_STATS", "LD_FRAME_DUMP_ASYNC_BB", "[flash-check] DARK",
                     "flash.csv", "_bb.ppm"):
            self.assertIn(word, text)

    def test_its_number_is_its_own(self):
        names = [n for n in os.listdir(os.path.dirname(PATCH)) if n.endswith(".patch")]
        self.assertEqual(len({n[:4] for n in names}), len(names), "two patches with one number")

if __name__ == "__main__":
    unittest.main()
