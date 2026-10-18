"""tools/soak: the log problem scanner and the title-menu frame check (no game needed)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "soak"))

import problems  # noqa: E402

LOG = """\
[sched] CPU budget: 6 logical processors, 6 cores (affinity mask; PS3_CPUS); sub-ms sleeps: timer
[pso-prewarm] 306 pipeline(s) created ahead, 0 failed
[fps] 59.4 (frames 1..298 over 5.0s)
[fps] 49.8 (frames 1197..1447 over 5.0s)
[audio-rate] 187.6 blocks/s (real time 187.5), silent 2.0%, dropped 0 frames/s, device buf 2400, queue min 415, starved 1, waited for 300 (max 4.5 ms), not written 12, no device 0
[live-draw] frame 32 packets[seen=0 queued=0 movie=0 qfull=0] groups[seen=0 exec=0 empty=0 drop{fetch=0 degen=0 prim=0 alloc=0 pso=0 ring=0 surface=0}] clears[guest=57 badsurf=0 implicitZ=0] textures[cached=0/1024 full=0 decodefail=0 depthSRV=0 rejectZ=0] vtex[cached=0 enabled=0 binds=0 uploads=0 refresh=0 unsupported=0 missingTXL=0] divider=0 balance[p=ok g=ok] binds[white=0 real=0 surf=0] (cumulative)
[live-draw] frame 64 packets[seen=9 queued=9 movie=0 qfull=0] groups[seen=9 exec=9 empty=0 drop{fetch=2 degen=0 prim=0 alloc=0 pso=0 ring=0 surface=0}] clears[guest=60 badsurf=0 implicitZ=0] textures[cached=2/1024 full=0 decodefail=1 depthSRV=0 rejectZ=0] vtex[cached=0 enabled=0 binds=0 uploads=0 refresh=0 unsupported=0 missingTXL=0] divider=0 balance[p=ok g=ok] binds[white=0 real=9 surf=0] (cumulative)
[cellGcmSys] recycled the title's own ring (ctx=0x0F800000 begin=0x40100000 end=0x40500000) -- its callback does not
[cellGcmSys] queued flip never reached by the FIFO walker (get=0x001C3C34 put=0x002A59D4 cur=0x403A5B10 io 0x002A5B10) -- completing it
[hle] unresolved NID 0x2BFFF084 (cellFoo)
[CRASH] access violation at 0x0
[WATCHDOG] 8s sample; last HLE call = 0x00000000 ()
[cellAudio] sound glitches: 41 audio block(s) not written by the game in time, 0 device underrun(s) in 1 window(s) of 5 s (937 blocks in the last one) [t=12.0s]
[spu-tick] tid 0x2000: 937 answers, mean 3.10 ms, p95 3.75, p99 4.50, max 6.20, over 5.33 ms: 2; on the CPU 14.30 M cycles per answer
[cellAtrac] DeleteDecoder handle=0x1: 57272 bytes streamed in, 3 bad frames, read from its archive
[mf_h264] decode failed: 0x8000FFFF
something else failed here
"""


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.d = problems.scan(LOG, fps_min=59.0)

    def test_categories(self):
        d = self.d
        self.assertEqual(d["crash"]["count"], 1)
        self.assertEqual(d["nid"]["count"], 1)
        self.assertEqual(d["fifo"]["count"], 2)
        self.assertEqual(d["watchdog"]["count"], 1)
        self.assertEqual(d["decode"]["count"], 1)
        # the [audio-rate] window with holes and the glitch line
        self.assertEqual(d["audio"]["count"], 2)

    def test_numbers(self):
        d = self.d
        self.assertEqual(d["fps"]["windows"], 2)
        self.assertEqual(d["fps"]["below"], 1)
        self.assertEqual(d["audio_rate"]["not_written"], 12)
        self.assertEqual(d["audio_rate"]["starved"], 1)
        self.assertEqual(d["atrac_bad_frames"], 3)
        self.assertEqual(d["spu_tick"]["answers"], 937)
        self.assertEqual(d["spu_tick"]["over_5_33ms"], 2)
        self.assertAlmostEqual(d["spu_tick"]["mcycles_median"], 14.30)
        self.assertEqual(d["render"]["count"], 1)            # drop/decodefail counters grew once
        self.assertEqual(d["render"]["live_draw_totals"]["drop_fetch"], 2)

    def test_other_lines(self):
        shapes = self.d["other"]["shapes"]
        self.assertEqual(len(shapes), 1)                       # the prewarm OK line is routine
        self.assertIn("something else failed", list(shapes.values())[0][2])

    def test_summary_runs(self):
        s = problems.summary(self.d)
        self.assertIn("spu-tick", s)
        self.assertIn("fifo", s)


class MenuCheckTest(unittest.TestCase):
    def test_menu_and_press_start(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not installed")
        if sys.platform != "win32":
            self.skipTest("soakgame drives Windows processes")
        from soakgame import title_menu_check
        im = Image.new("RGB", (1280, 720))
        d = ImageDraw.Draw(im)
        for y, c in ((515, (200, 30, 20)), (547, (90, 20, 10)), (579, (90, 20, 10)), (611, (90, 20, 10))):
            d.rectangle((500, y, 780, y + 14), fill=c)
        r = title_menu_check(im)
        self.assertTrue(r["menu"])
        self.assertEqual(r["hi"], 0)
        self.assertFalse(r["press_start"])
        im2 = Image.new("RGB", (1280, 720))
        ImageDraw.Draw(im2).rectangle((420, 538, 860, 556), fill=(140, 22, 4))
        r2 = title_menu_check(im2)
        self.assertFalse(r2["menu"])
        self.assertTrue(r2["press_start"])


if __name__ == "__main__":
    unittest.main()
