"""Source contracts for cancellable live replay waits; no compiler or game needed.

These catch the former null-callback input/barrier waits and the select screen's
missing END/timeout path. Actual process shutdown and rendered output still need
the real-game phase matrix in docs/SPECTATE.md.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def body(source, declaration):
    """Extract a C++ function body with balanced braces for focused assertions."""
    start = source.index("{", source.index(declaration))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start + 1:end - 1]


class LiveExitContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "src/netplay/replay.cpp").read_text(encoding="utf-8-sig")

    def test_input_and_barrier_waits_use_registered_local_exit_poll(self):
        wait = body(self.src, "bool live_block(")
        self.assertIn("if (!quit) quit = p.quit_poll;", wait)
        self.assertLess(wait.index("if (quit && quit())"), wait.index("if (ok() || p.live_end)"))
        loop = wait[wait.index("for (;;) {"):]
        self.assertLess(loop.index("if (quit && quit())"), loop.index("live_poll(p)"))
        for signature in ("void play_inputs(", "uint32_t play_barrier("):
            with self.subTest(signature=signature):
                self.assertIn("live_block(p,", body(self.src, signature))

    def test_first_fight_wait_is_tracked_before_a_fight_line_is_requested(self):
        self.assertIn("p.waiting_fight = 1;", body(self.src, "bool live_load("))

    def test_missing_next_fight_tracks_its_number_and_clears_when_delivered(self):
        fight = body(self.src, "bool play_fight_line(")
        self.assertIn("p.waiting_fight = match > p.d.matches.size() ? match : 0;", fight)
        self.assertIn("p.finished", fight)
        self.assertLess(fight.index("return false;"), fight.index("p.waiting_fight = 0;"))

    def test_idle_end_polls_timeout_but_preserves_buffered_unplayed_fights(self):
        poll = body(self.src, "const char* play_poll_end(")
        self.assertIn("!p.waiting_fight", poll)
        self.assertIn("live_poll(p);", poll)
        self.assertIn("live_timeout(p);", poll)
        self.assertIn("!p.live_end || p.waiting_fight <= p.d.matches.size()", poll)
        self.assertIn("p.live_why.c_str()", poll)

    def test_idle_and_blocking_waits_share_the_same_timeout(self):
        self.assertIn("live_timeout(p);", body(self.src, "bool live_block("))
        self.assertIn("live_timeout(p);", body(self.src, "const char* play_poll_end("))
        timeout = body(self.src, "void live_timeout(")
        self.assertIn("p.timeout_s * 1000", timeout)
        self.assertIn("p.live_end = true;", timeout)

    def test_finish_closes_the_live_reader_after_final_poll(self):
        finish = body(self.src, "void play_finish(")
        self.assertIn("t5p_close(p.lh); p.lh = -1;", finish)
        self.assertLess(finish.index("live_poll(p)"), finish.index("t5p_close(p.lh)"))


if __name__ == "__main__":
    unittest.main()
