"""The intro movie and the title (ps3recomp patch 0053, tools/smoke wait_title).

1.1.2 smoke runs sometimes missed reach.title: the H.264 decoder never gave the
intro movie a picture, the movie stayed white and START did nothing. Patch 0053
makes the decoder ahead of time and lets a watchdog continue a movie whose
decoder stalls with blank pictures; wait_title presses START only once the
movie shows and until it has closed, and says which case it saw. No game
needed: wait_title runs against a log written by a fake game.
"""
import os
import sys
import tempfile
import threading
import unittest

from helpers import ROOT

SMOKE = os.path.join(ROOT, "tools", "smoke")
sys.path.insert(0, SMOKE)

try:
    import game  # noqa: E402  (frames.py needs Pillow)
    HAVE_GAME = True
except ImportError:
    HAVE_GAME = False

OPEN1 = "[cellVdec] Open(codec 1, profile 0x29, mem 0x46700000+0x100000) -> handle 0\n"
PIC1 = "[cellVdec] handle 0: picture #1 1280x720 (3 AUs in, 4.59 pictures/s delivered)\n"
CLOSE1 = "[cellVdec] Close(0): 61 AUs, 61 pictures decoded, 61 taken\n"
STALL = ("[cellVdec] handle 0: the H.264 decoder has not answered for 5000 ms (decoding) -- the rest of "
         "this movie has no pictures (its sound plays, START skips it); a new decoder is made for the next one\n")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(HAVE_GAME, "Pillow missing")
class WaitTitle(unittest.TestCase):
    def make(self, start, on_start=None):
        """A Game whose log starts as `start`; on_start(n, write) runs on the n-th START press."""
        d = tempfile.mkdtemp()
        g = game.Game(d, verbose=False)
        g.log_path = os.path.join(d, "game.log")
        g.t0 = __import__("time").perf_counter()
        g._ev = open(os.devnull, "w")
        g.check = lambda: None
        lock = threading.Lock()
        presses = []

        def write(s):
            with lock, open(g.log_path, "a") as f:
                f.write(s)

        def press(*btns, **kw):
            presses.append(btns)
            if on_start and btns == ("START",):
                on_start(len(presses), write)

        g.press = press
        g.wait = lambda s: __import__("time").sleep(min(s, 0.02))
        write(start)
        self.addCleanup(g._ev.close)
        return g, presses, write

    def test_skip_after_the_first_picture(self):
        g, presses, _ = self.make(OPEN1 + PIC1, lambda n, w: w(CLOSE1 + OPEN1))
        self.assertTrue(g.wait_title(timeout=5))
        self.assertEqual(len(presses), 1)
        self.assertIn("1 START press(es)", g.title_detail)
        self.assertIn("first picture", g.title_detail)

    def test_presses_until_the_movie_closes(self):
        g, presses, _ = self.make(OPEN1 + PIC1, lambda n, w: w(CLOSE1 + OPEN1) if n == 4 else None)
        self.assertTrue(g.wait_title(timeout=5))
        self.assertEqual(len(presses), 4)

    def test_no_press_before_the_movie_shows(self):
        def later(write):
            __import__("time").sleep(0.3)
            write(PIC1)
        g, presses, write = self.make(OPEN1, lambda n, w: w(CLOSE1 + OPEN1))
        threading.Thread(target=later, args=(write,), daemon=True).start()
        self.assertTrue(g.wait_title(timeout=5))
        self.assertEqual(len(presses), 1)

    def test_patch_0053_fallback_counts_as_shown(self):
        g, presses, _ = self.make(OPEN1 + STALL, lambda n, w: w(CLOSE1 + OPEN1))
        self.assertTrue(g.wait_title(timeout=5, picture_timeout=0.5))
        self.assertEqual(len(presses), 1)

    def test_decoder_without_picture_is_named(self):
        g, presses, _ = self.make(OPEN1)
        self.assertFalse(g.wait_title(timeout=5, picture_timeout=0.2, skip_timeout=0.3))
        self.assertIn("the decoder gave no picture", g.title_detail)
        self.assertGreaterEqual(len(presses), 1)

    def test_movie_that_ends_by_itself(self):
        g, presses, _ = self.make(OPEN1 + PIC1 + CLOSE1 + OPEN1)
        self.assertTrue(g.wait_title(timeout=5))
        self.assertEqual(presses, [])
        self.assertIn("the movie ended", g.title_detail)

    def test_build_without_movies(self):
        g, presses, _ = self.make("[cellDmux] Close(0x1)\n[cellDmux] Close(0x1)\n")
        self.assertTrue(g.wait_title(timeout=5))
        self.assertEqual(presses, [])


class Patch0053(unittest.TestCase):
    def test_series_has_it(self):
        names = sorted(os.listdir(os.path.join(ROOT, "patches", "ps3recomp")))
        self.assertIn("0053-movie-decoder-start.patch", names)

    def test_knobs_and_fallback(self):
        p = text("patches", "ps3recomp", "0053-movie-decoder-start.patch")
        for knob in ("PS3_VDEC_STALL_MS", "PS3_VDEC_THREADS", "PS3_VDEC_PREWARM",
                     "PS3_VDEC_TEST_STALL", "PS3_VDEC_TEST_NOPIC"):
            self.assertIn('"%s"' % knob, p, knob)
        self.assertIn("ms = e && *e ? atoi(e) : 5000;", p)            # stall limit 5 s
        self.assertIn("n = e && *e ? atoi(e) : 2;", p)                 # 2 decoding threads
        self.assertIn("if (id == CELL_SYSMODULE_VDEC) cellVdec_module_loaded();", p)
        self.assertIn("CoIncrementMTAUsage", p)                        # the MTA outlives the prewarm thread
        # the stalled worker is replaced, never reused
        self.assertIn("v->epoch++;", p)
        self.assertIn("if (!mf_leave(v, epoch)) return retire(v, mf, &c, &pl);", p)

    def test_smoke_knows_the_fallback_lines(self):
        p = text("patches", "ps3recomp", "0053-movie-decoder-start.patch")
        g = text("tools", "smoke", "game.py")
        self.assertIn("the H.264 decoder has not answered for", p)
        self.assertIn("no picture from the H.264 decoder", p)
        self.assertIn(r"the H\.264 decoder has not answered", g)
        self.assertIn(r"no picture from the H\.264 decoder", g)


if __name__ == "__main__":
    unittest.main()
