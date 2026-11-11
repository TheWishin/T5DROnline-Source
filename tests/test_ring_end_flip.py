"""A frame that ends in the last 4 KB of the command ring (ps3recomp patch 0125, docs/RENDER_PERF.md "A frame that
ends at the ring's end"): its user command and its flip stay in the FIFO (the ring is wrapped there) instead of
being made at call time, which lost one picture and one tick. No game needed: the patch's rules are checked in
its text, and tools/frame_skips.py against game-thread logs written here."""
import os
import sys
import tempfile
import unittest

from helpers import ROOT

if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.append(os.path.join(ROOT, "tools"))
import frame_skips  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0125-ring-end-flip.patch")


def patch_lines(sign):
    with open(PATCH, encoding="utf-8") as f:
        return "\n".join(ln[1:] for ln in f.read().splitlines() if ln.startswith(sign) and not ln.startswith(sign * 3))


class Patch(unittest.TestCase):
    def test_one_file(self):
        with open(PATCH, encoding="utf-8") as f:
            files = [ln for ln in f.read().splitlines() if ln.startswith("diff --git")]
        self.assertEqual(files, ["diff --git a/libs/video/cellGcmSys.c b/libs/video/cellGcmSys.c"])

    def test_after_every_other_patch(self):
        names = sorted(n for n in os.listdir(os.path.dirname(PATCH)) if n.endswith(".patch"))
        later = names[names.index("0125-ring-end-flip.patch") + 1:]
        # a later patch (0127: the tier-1 mask check) may follow, but none of them touches cellGcmSys.c
        for n in later:
            with open(os.path.join(os.path.dirname(PATCH), n), encoding="utf-8") as f:
                self.assertNotIn("diff --git a/libs/video/cellGcmSys.c", f.read(), n)

    def test_the_flip_wraps_by_the_same_rule_as_every_lap(self):
        p = patch_lines("+")
        # refused as before unless: switched on, `current` inside the ring, and the walker past the ring's head
        self.assertIn("if (!gcm_ring_end_cfg() || cur < begin || cur > end || io_begin == 0xFFFFFFFFu ||\n"
                      "            s_fifo_getoff < io_begin + GCM_RECYCLE_MARGIN) {", p)
        # fewer than 8 bytes: the JUMP at `current`, the marker at the ring's start
        self.assertIn("vm_write32(cur, 0x20000000u | io_begin);", p)
        self.assertIn("vm_write32(begin, GCM_FLIP_MARKER | bufferId);", p)
        self.assertIn("vm_write32(ctx + 8, begin + 4);", p)

    def test_the_user_command_leaves_room_for_the_flip(self):
        p = patch_lines("+")
        # 16 bytes: the command (8), then the flip's marker and its JUMP
        self.assertIn("if (cur + 16 <= end && !gcm_ring_end_wrap_first()) near_end = 1;", p)
        # only the ring the walker reads, and only with the walker past the head
        self.assertIn("cur <= end && c == s_gcm_context_ea &&", p)
        self.assertIn("else if (cur >= begin && io_begin != 0xFFFFFFFFu && s_fifo_getoff >= io_begin + GCM_RECYCLE_MARGIN) {", p)
        # `put` moves back to the ring's start after a wrap (it only ever moved forward before)
        self.assertIn("if (io != 0xFFFFFFFFu && (wrapped || io > vm_read32(GCM_CONTROL_GUEST_ADDR))) {", p)

    def test_old_way_and_notes(self):
        p = patch_lines("+")
        self.assertIn('getenv("PS3_GCM_RING_END"); cfg = !(e && *e == \'0\');', p)
        self.assertIn("ring wrapped there, the flip stays in the FIFO", p)
        self.assertIn("flip made at call time, outside the FIFO (one picture is lost)", p)
        # the default slack is the runtime's own; the test switches are off unless set
        self.assertIn(": GCM_RECYCLE_SLACK; }", p)
        self.assertIn('getenv("PS3_GCM_TEST_RING_WRAP"); v = e && *e == \'1\';', p)

    def test_nothing_else_removed(self):
        gone = [ln.strip() for ln in patch_lines("-").splitlines() if ln.strip()]
        self.assertEqual(len(gone), 4, gone)
        for ln in gone:
            self.assertTrue("GCM_RECYCLE_SLACK" in ln or "const u32 end" in ln or
                            "io > vm_read32(GCM_CONTROL_GUEST_ADDR)" in ln, ln)


def write_log(path, frames):
    """frames: (interval_ms, cpu_ms) per flip request; QPC 10 MHz, TSC 4 GHz."""
    q, c = 1000000, 5000000000
    with open(path, "w") as f:
        f.write("# qpc_frequency=10000000 tsc_frequency=4000000000\n")
        f.write("1 %d 0 %d 77\n" % (q, c))
        for i, (iv, cpu) in enumerate(frames):
            q += int(iv * 10000)
            c += int(cpu * 4000000)
            f.write("%d %d %d %d 77\n" % (i + 2, q, q - 25000, c))


class Tool(unittest.TestCase):
    def run_tool(self, frames, extra=()):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "gt.log")
            write_log(p, frames)
            qf, tf, rows = frame_skips.read(p)
            fr = frame_skips.frames(qf, tf, rows)
            return frame_skips.skips(fr)

    def test_steady(self):
        med, sk = self.run_tool([(16.68, 2.5)] * 600)
        self.assertAlmostEqual(med, 2.5, places=2)
        self.assertEqual(sk, [])

    def test_two_frames_for_one_picture(self):
        fr = [(16.68, 2.5)] * 300 + [(54.0, 5.2)] + [(16.68, 2.5)] * 300
        med, sk = self.run_tool(fr)
        self.assertEqual(len(sk), 1)
        seq, iv, cpu, k = sk[0]
        self.assertEqual(seq, 302)
        self.assertAlmostEqual(iv, 54.0, places=1)
        self.assertGreaterEqual(k, 1.6)

    def test_a_late_frame_is_not_a_lost_picture(self):
        fr = [(16.68, 2.5)] * 300 + [(33.4, 2.7)] + [(16.68, 2.5)] * 300
        med, sk = self.run_tool(fr)
        self.assertEqual(len(sk), 1)
        self.assertLess(sk[0][3], 1.6)


if __name__ == "__main__":
    unittest.main()
