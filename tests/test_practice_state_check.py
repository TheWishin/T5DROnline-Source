"""tools/practice_state_check.py without a game (practice-flake-018): which game type the title menu landed on (a lost
menu press used to give "no round start in the practice log"), when the frames run is over (it used to stop on the
wall clock, 90 frames short on a loaded PC), and that the start-watch lines the game writes since then do not count
as places or states. Made-up practice logs in the format practice.cpp writes."""
import os
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import practice_state_check as psc  # noqa: E402

START = ["0 start watch: game type 0 phase 0 runs 0 state 0 neutral 0",
         "0 start watch: game type 10 phase 1 runs 0 state 0 neutral 0",
         "0 start watch: game type 10 phase 7 runs 0 state 0 neutral 1",
         "0 start watch: held back 4000 0000 (phase 17 runs 0)",
         "0 start watch: game type 10 phase 17 runs 1 state 0 neutral 1",
         "0 the round's first state kept after 0 frame(s)",
         "0 start watch: game type 10 phase 17 runs 1 state 1 neutral 0",
         "0 round start: P1 1000.0 0.0 -1.571 dummy -1000.0 0.0 1.571",
         "0 practice start: round 17 phase 17 P1 y 0.0 hips 1129.9 move 80010080 class 00000000 act 1 right 0 "
         "dummy y 0.0 hips 1129.9 move 80010080 class 00000000 act 1 right 1"]


def reset(f, x1=1000.0, x2=-1000.0):
    return [f"{f} state restored: P1 1000.0 0.0 -1.571 dummy -1000.0 0.0 1.571",
            f"{f + 40} after reset: round 17 phase 17 P1 y 0.0 hips 1129.0 move 80010080 class 00000000 act 1 right 0 "
            f"dummy y 0.0 hips 1129.0 move 80010080 class 00000000 act 1 right 1",
            f"{f + 120} places: P1 {x1:.1f} 0.0 -1.571 dummy {x2:.1f} 0.0 1.571"]


class GameType(unittest.TestCase):
    def test_last_seen(self):
        self.assertEqual(psc.game_type(START), 10)
        self.assertEqual(psc.game_type(START[:1]), 0)

    def test_survival_is_seen(self):
        self.assertEqual(psc.game_type(["0 start watch: game type 9 phase 1 runs 0 state 0 neutral 0"]), 9)

    def test_older_game_unknown(self):
        self.assertIsNone(psc.game_type(["0 fight runs byte 1"]))


class FramesDone(unittest.TestCase):
    def test_last_hash_of_the_last_reset(self):
        lines = [f"5 hash {k} {f} 00ff" for k in range(3) for f in range(0, 31)]
        self.assertFalse(psc.frames_done(lines, 30, 3))
        lines += [f"9 hash 3 {f} 00ff" for f in range(0, 30)]
        self.assertFalse(psc.frames_done(lines, 30, 3))
        self.assertTrue(psc.frames_done(lines + ["9 hash 3 30 00ff"], 30, 3))

    def test_other_lines(self):
        self.assertFalse(psc.frames_done(["9 test 3 30 health 145 120", "9 start watch: game type 10 phase 17"], 30, 3))


class Resets(unittest.TestCase):
    def test_watch_lines_do_not_count(self):
        lines = START + [ln for f in range(100, 100 + 17 * 300, 300) for ln in reset(f)]
        ok, summary = psc.check_resets(lines)
        self.assertTrue(ok, summary)

    def test_a_kick_kept_in_the_state_fails(self):
        lines = START + [ln for f in range(100, 100 + 17 * 300, 300) for ln in reset(f, x1=640.9)]
        ok, summary = psc.check_resets(lines)
        self.assertFalse(ok)
        self.assertIn("17 bad", summary)


class ReadLines(unittest.TestCase):
    def test_missing_file(self):
        self.assertEqual(psc.read_lines(os.path.join(tempfile.gettempdir(), "no-such-practice-log.txt")), [])


if __name__ == "__main__":
    unittest.main()
