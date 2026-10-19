"""Select stall after a fight (docs/DIRECTFIGHT.md "Select stall after a fight"): the harness's parts that
need no game (tools/select_stall_test.py) and the driver's guard around the game's async reader."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import select_stall_test as sst  # noqa: E402

# The stall as the old driver logged it (select_stall_test --fs-delay 150 --env T5_DF_READER_GUARD=0, shortened).
STALLED = """\
[df] frame 1579: boot state of 1 area(s), 94208 bytes, kept for later opponents (reader busy 1, queue 0x1009FF68 (1 request(s)), completion tokens 0)
[df] frame 8569: before the restore: reader busy 0, queue 0x00000000 (0 request(s)), completion tokens 0
[df] frame 8569: the match state areas are back as at boot (1646 bytes differed; reader busy 1, queue 0x1009FF68 (1 request(s)), completion tokens 0)
[df] frame 8569: start VS battle (func_0004E9DC(4, 3)) from the title mode
[df] frame 8569: state select
[df] frame 8689: waiting for the select screen (mode 6, select state 1, records 00/00; reader busy 1, queue 0x1009FF68 (5 request(s)), completion tokens 0)
[df] frame 8809: waiting for the select screen (mode 6, select state 1, records 00/00; reader busy 1, queue 0x1009FF68 (5 request(s)), completion tokens 0)
"""

# A cycle with the guard: the title waits for its loads, the copy leaves the reader out, the select goes on.
FIXED = """\
[df] frame 1580: waiting for the title's loads before start VS (reader busy 1, queue 0x1009FF68 (1 request(s)), completion tokens 0)
[df] frame 1623: the title's loads are done (reader busy 0, queue 0x00000000 (0 request(s)), completion tokens 0)
[df] frame 1623: boot state of 2 area(s), 91288 bytes, kept for later opponents (reader busy 0, queue 0x00000000 (0 request(s)), completion tokens 0)
[df] frame 1623: start VS battle (func_0004E9DC(4, 3)) from the title mode
[df] frame 1623: state select
[df] frame 1700: select done: P1 Kazuya with default (model 0x25), P2 Heihachi with default (model 0x23)
[df] frame 1700: state stage
[df] frame 1781: FIGHT START match 1 id s001: Kazuya vs Heihachi, stage 20 (field 0x14), rounds 1, game type 4
"""


class HarnessLogTest(unittest.TestCase):
    def test_a_clean_cycle(self):
        self.assertEqual(sst.bad_lines(FIXED), [])
        self.assertEqual(sst.RE_FIGHT.search(FIXED).group(2), "1")
        sv, st = sst.RE_STARTVS.search(FIXED), sst.RE_STAGE.search(FIXED)
        self.assertEqual(int(st.group(1)) - int(sv.group(1)), 77)
        self.assertEqual(sst.RE_WAITSEL.findall(FIXED), [])

    def test_the_stall_shows(self):
        self.assertIsNone(sst.RE_FIGHT.search(STALLED))
        self.assertEqual([w[2] for w in sst.RE_WAITSEL.findall(STALLED)], ["1", "1"])

    def test_progress_moves_on_a_slow_select(self):
        # a select still loading (new wait-line content or a new file open) is progress, the same lines again are not
        p0 = sst.progress(STALLED)
        self.assertEqual(sst.progress(STALLED), p0)
        self.assertNotEqual(sst.progress(STALLED + "[fs] open '/dev_hdd0/x' -> fd 3
"), p0)
        self.assertNotEqual(sst.progress(STALLED + "[df] frame 8929: waiting for the select screen (mode 6, select state 1, "
                                         "records 00/00; reader busy 1, queue 0x1009FFE0 (4 request(s)), completion tokens 0)
"), p0)
        self.assertEqual(sst.progress(STALLED + "[df] frame 8929: waiting for the select screen (mode 6, select state 1, "
                                      "records 00/00; reader busy 1, queue 0x1009FF68 (5 request(s)), completion tokens 0)
"), p0)
        self.assertNotEqual(sst.progress(FIXED), sst.progress(FIXED.split("[df] frame 1700")[0]))

    def test_faults_and_the_backstop(self):
        self.assertIn("stuck_exit", sst.bad_lines(
            "[df] frame 9000: STUCK: the select screen's loading for 10 s, the async reader waits for a read nobody does\n"))
        self.assertIn("crash", sst.bad_lines("[CRASH] access violation at 0x0\n"))
        # a slow reset is no fault here (--fs-delay): only one that never ends (no FIGHT START, STUCK)
        self.assertEqual(sst.bad_lines("[df] frame 6379: reset: waiting in mode 6\n"), [])


class DriverSourceTest(unittest.TestCase):
    """The boot-state copy must leave the reader's data out, and the title must wait for its loads."""

    def setUp(self):
        with open(os.path.join(ROOT, "src", "directfight", "df_fight.cpp"), encoding="utf-8-sig") as f:
            self.src = f.read()

    def const(self, name):
        m = re.search(name + r" = (0x[0-9A-Fa-f]+)u", self.src)
        self.assertIsNotNone(m, name)
        return int(m.group(1), 16)

    def test_the_reader_range_is_inside_the_copy_and_covers_the_reader(self):
        lo, hi = self.const("kReaderData"), self.const("kReaderDataEnd")
        self.assertEqual(lo, 0x1009FE20)            # thread id, then the service object 0x1009FE28
        self.assertEqual(hi, 0x100A0988)            # pool 0x1009FF68 + 64 * 0x28, config copy 0x100A0968 + 0x20
        self.assertEqual(self.const("kReader"), 0x1009FE28)
        self.assertEqual(self.const("kReaderPool"), 0x1009FF68)
        self.assertEqual(self.const("kReaderPoolEnd"), 0x1009FF68 + 64 * 0x28)
        self.assertIn('spec = "1008E000:17000"', self.src)   # the default copy, 0x1008E000..0x100A5000
        self.assertTrue(0x1008E000 < lo < hi < 0x100A5000)

    def test_areas_over_the_reader_are_split(self):
        self.assertRegex(self.src, r"g_reader_guard && a < kReaderDataEnd && end > kReaderData")
        self.assertIn("{ a, kReaderData - a, {} }", self.src)
        self.assertIn("{ kReaderDataEnd, end - kReaderDataEnd, {} }", self.src)
        self.assertIn("T5_DF_READER_GUARD", self.src)

    def test_title_waits_for_the_reader_before_copy_and_start_vs(self):
        title = re.search(r"case Ph::Title:(.*?)case Ph::Select:", self.src, re.S).group(1)
        wait = title.index("!reader_idle()")
        self.assertLess(wait, title.index("fresh_restore(f)"))
        self.assertLess(wait, title.index("fresh_take(f)"))
        self.assertLess(wait, title.index("gcall(kFnStartGame, 4, 3)"))

    def test_the_backstop_never_waits_on_a_slow_load(self):
        body = re.search(r"void select_load_check\(uint32_t f\)\s*\{(.*?)\n\}", self.src, re.S).group(1)
        # wedged: busy, no token and the reader thread parked on its request semaphore -- not merely "slow"
        self.assertIn("busy == 1 && tokens == 0 && sem_parked(rd32(kReader))", body)
        # nothing to load: the reader idle and every loader thread parked (a starved decoder is still working)
        self.assertIn("busy == 0 && q == 0 && sem_parked(rd32(kReader)) && sem_parked(rd32(kDecoderSemPtr))", body)
        self.assertIn("sem_parked(rd32(kAsyncSemPtr))", body)
        self.assertIn("TerminateProcess(GetCurrentProcess(), 6)", body)
        self.assertIn("f - g_sl_frame < limit * kStuckMinFps", body)
        self.assertRegex(self.src, r"void stuck_check\(uint32_t f\)\s*\{\s*select_load_check\(f\);")

    def test_a_crawling_game_is_not_stuck(self):
        # the stuck exits need the frames too: a PC starved to 1 fps is slow, not stuck
        self.assertRegex(self.src, r"constexpr uint32_t kStuckMinFps = \d+;")
        body = re.search(r"void stuck_check\(uint32_t f\)\s*\{(.*?)\n\}", self.src, re.S).group(1)
        self.assertIn("f - since_f < g_stuck_s * kStuckMinFps", body)


def split_areas(areas, guard=True, lo=0x1009FE20, hi=0x100A0988):
    """The driver's split (df_fight.cpp fight_init), for the table below."""
    out = []
    for a, n in areas:
        end = a + n
        if guard and a < hi and end > lo:
            if a < lo:
                out.append((a, lo - a))
            if end > hi:
                out.append((hi, end - hi))
        elif n:
            out.append((a, n))
    return out


class SplitTest(unittest.TestCase):
    def test_default_block(self):
        self.assertEqual(split_areas([(0x1008E000, 0x17000)]),
                         [(0x1008E000, 0x1009FE20 - 0x1008E000), (0x100A0988, 0x100A5000 - 0x100A0988)])
        self.assertEqual(sum(n for _, n in split_areas([(0x1008E000, 0x17000)])), 94208 - 0xB68)

    def test_hash_areas_untouched(self):
        hashed = [(0x1008E000, 0x4000), (0x10099600, 0x600), (0x100A3B00, 0x300)]
        self.assertEqual(split_areas(hashed), hashed)

    def test_old_way(self):
        self.assertEqual(split_areas([(0x1008E000, 0x17000)], guard=False), [(0x1008E000, 0x17000)])


if __name__ == "__main__":
    unittest.main()
