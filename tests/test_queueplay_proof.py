"""The queueplay proof must reject absent evidence and mode fallbacks."""
import sys
import unittest

from helpers import TOOLS

sys.path.insert(0, TOOLS)
from queueplay_test import assess_pair  # noqa: E402


class ProofEvidence(unittest.TestCase):
    def setUp(self):
        self.result = {"winner": 0, "hash": "1234", "desync": 0}
        self.lockstep = "sync check through frame 1199: 0 mismatching frame(s) -- in sync\n"
        self.rollback = (self.lockstep + "rbnet: rollback loop takes over at frame 1\n"
                         "rbnet: rollback 120 -> 116 done in 1.0 ms (4 frames re-simulated)\n")

    def check(self, logs, mode="lockstep", results=None):
        return assess_pair(results or [self.result, self.result], logs, mode)[0]

    def test_actual_compared_pair_passes(self):
        self.assertEqual(self.check([self.lockstep] * 2), [])
        self.assertEqual(self.check([self.rollback] * 2, "rollback"), [])

    def test_absent_frame_comparisons_fail(self):
        self.assertTrue(self.check(["", ""]))

    def test_earlier_mismatches_fail_even_if_last_check_is_clean(self):
        self.assertTrue(self.check(["sync check through frame 599: 1 mismatching\n" + self.lockstep,
                                    self.lockstep]))

    def test_rollback_fallback_fails(self):
        self.assertTrue(self.check([self.lockstep] * 2, "rollback"))
        self.assertTrue(self.check([self.rollback] * 2))

    def test_rollback_negotiation_without_resimulation_fails(self):
        log = self.lockstep + "rollback loop takes over"
        self.assertTrue(self.check([log] * 2, "rollback"))

    def test_result_disagreement_and_unconfirmed_result_fail(self):
        self.assertTrue(self.check([self.lockstep] * 2, results=[self.result, dict(self.result, hash="5678")]))
        self.assertTrue(self.check([self.lockstep] * 2, results=[self.result, {"reason": "peer_quit"}]))

    def test_fatal_errors_and_missing_game_fail(self):
        self.assertTrue(self.check([self.lockstep + "[null-call]", self.lockstep]))
        self.assertTrue(assess_pair([self.result], [self.lockstep], "lockstep")[0])


if __name__ == "__main__":
    unittest.main()
