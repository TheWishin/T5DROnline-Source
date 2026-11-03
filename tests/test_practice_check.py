"""tools/practice_check.py --adv-compare (review optin-check-120 P2): every overlay result logged while the
experimental comparison runs needs its own comparison line with the same old value; one comparison line for many
results used to pass. No game needed: made-up training logs in the format training.cpp writes."""
import os
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import practice_check as pc  # noqa: E402

MAP = ["1 adv_compare mapping P1 status=mapping_conflict_position_x raw_move_word=0 anim=0 length=0 hitbox=0 char=0 "
       "indirect=00000000",
       "1 adv_compare mapping P2 status=mapping_conflict_position_x raw_move_word=0 anim=0 length=0 hitbox=0 char=0 "
       "indirect=00000000"]


def result(frame, player, adv):
    return f"{frame} result {player} startup 10 hit adv {adv:+d} total 30 active 10-12 | i10 {adv:+d}"


def move(frame, player, old):
    return (f"{frame} adv_compare move {player} active_poll=5 anchor=old-active-window old={old:+d} "
            f"old_status=available new=unavailable new_status=mapping_conflict_position_x sample_poll={frame} "
            f"raw_move_word=00000000 anim=0 length=1 hitbox=0 char=0")


class Coverage(unittest.TestCase):
    def test_complete_log_passes(self):
        log = MAP + [result(10, "P1", 3), move(10, "P1", 3), result(40, "P2", -7), move(40, "P2", -7)]
        self.assertEqual(pc.compare_coverage(log), ([], [], []))
        self.assertTrue(pc.check_adv_compare(log))

    def test_many_results_one_comparison_fails(self):
        log = MAP + [result(10, "P1", 3), move(10, "P1", 3), result(40, "P1", 9), result(70, "P2", 1)]
        missing, wrong, extra = pc.compare_coverage(log)
        self.assertEqual(len(missing), 2)
        self.assertFalse(pc.check_adv_compare(log))

    def test_other_old_value_fails(self):
        log = MAP + [result(10, "P1", 3), move(10, "P1", 4)]
        self.assertEqual(len(pc.compare_coverage(log)[1]), 1)
        self.assertFalse(pc.check_adv_compare(log))

    def test_comparison_without_result_and_wrong_player(self):
        log = MAP + [result(10, "P1", 3), move(10, "P2", 3)]
        missing, wrong, extra = pc.compare_coverage(log)
        self.assertEqual((len(missing), len(extra)), (1, 1))

    def test_results_while_the_comparison_is_off_need_none(self):
        log = [result(5, "P1", 1)] + MAP + [result(10, "P1", 3), move(10, "P1", 3),
                                            "20 adv_compare reset reason=phase", result(30, "P2", 2)]
        self.assertEqual(pc.compare_coverage(log), ([], [], []))


if __name__ == "__main__":
    unittest.main()
