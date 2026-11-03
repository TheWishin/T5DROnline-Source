"""Quit-only loader polls must not consume the viewer's START pause edge.

Source contracts only: actual controller timing and playback still need a game.
"""
from pathlib import Path
import unittest

from test_replay_exit_contract import function


ROOT = Path(__file__).resolve().parents[1]


class ReplayPausePollTest(unittest.TestCase):
    def test_quit_poll_leaves_start_history_for_frame_control(self):
        source = (ROOT / "src/netplay/t5_hooks.cpp").read_text(encoding="utf-8-sig")
        quit_poll = function(source, "bool replay_quit_poll()")
        # drain_wait polls even on frames with no loader wait. A START held
        # from that poll until the next frame must still be a fresh pause edge.
        self.assertNotIn("g_rp.prev", quit_poll)
        self.assertIn("replay_pad() & kPadSelect", quit_poll)
        self.assertIn("g_rp.quit = true", quit_poll)
        frame = function(source, "int64_t replay_frame_wait(ppu_context* ctx)")
        self.assertIn("b & ~r.prev", frame)
        self.assertIn("r.prev = b;", frame)
        self.assertIn("press & kPadStart", frame)


if __name__ == "__main__":
    unittest.main()
