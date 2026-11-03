"""Playback exit wiring that can be checked without a game or a C++ build.

These are source contracts, not evidence that a rendered frame is correct. The
real-game matrix must exercise SELECT/window close/END in each loading, fight,
select and between-match phase, then verify process exit and launcher ownership.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    """Take a C++ function body, including nested control-flow blocks."""
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    for pos in range(opening + 1, len(source)):
        depth += (source[pos] == "{") - (source[pos] == "}")
        if depth == 0:
            return source[opening + 1:pos]
    raise AssertionError("unclosed function: " + signature)


class ReplayExitContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hooks = (ROOT / "src/netplay/t5_hooks.cpp").read_text(encoding="utf-8-sig")

    def test_controls_run_before_lockstep_takeover_and_before_normal_wait(self):
        wait = function(self.hooks, "int64_t w_sem_wait(ppu_context* ctx)")
        poll = wait.index("replay_control_boundary();")
        # Before the first fight g_active is false and g_main_tid is unknown.
        guard = wait[wait.rfind("if (", 0, poll):poll]
        self.assertNotIn("g_active", guard)
        self.assertIn("g_main_tid != ~0ull ? g_main_tid : 1", guard)
        self.assertIn("!rb::net::bypass()", guard)
        self.assertLess(poll, wait.index("replay_frame_wait(ctx)"))
        boundary = function(self.hooks, "void replay_control_boundary()")
        self.assertIn("!g_active || g_idle", boundary)
        self.assertIn("replay_quit_poll()", boundary)
        self.assertIn("rp::play_poll_end()", boundary)

    def test_select_closes_even_when_diagnostic_keep_open_is_enabled(self):
        end = function(self.hooks, "void replay_end(const char* why, bool force)\n")
        self.assertIn("keep && !force", end)
        self.assertLess(end.index("const std::string reason = why"), end.index("rp::play_finish(why);"))
        self.assertIn("why = reason.c_str();", end)
        self.assertLess(end.index("rp::play_finish(why);", end.index("g_ending.exchange")),
                        end.index("t5p_exit_now(0)"))
        # Every explicit viewer SELECT exit must override T5_REPLAY_EXIT=0.
        calls = re.findall(r'replay_end\("ended by the viewer \(SELECT\)"([^;]+);', self.hooks)
        self.assertTrue(calls)
        self.assertTrue(all(re.fullmatch(r",\s*true\)", args) for args in calls), calls)

    def test_live_wait_cancellation_never_returns_to_missing_inputs(self):
        callback = function(self.hooks, "bool replay_wait_quit()\n")
        self.assertIn('replay_end("ended by the viewer (SELECT)", true)', callback)
        self.assertIn("return false;", callback)
        init = function(self.hooks, "void h_cellPadInit(ppu_context* ctx)")
        self.assertIn("rp::play_set_quit_poll(replay_wait_quit)", init)
        frame = function(self.hooks, "int64_t replay_frame_wait(ppu_context* ctx)")
        self.assertIn("rp::play_live_wait(g_frame, replay_wait_quit)", frame)

    def test_select_is_polled_during_loader_and_takeover_waits(self):
        for signature in ("bool ensure_keyread_parked(ppu_context* ctx)",
                          "double drain_wait(uint32_t f)", "void side_drain(uint32_t f)"):
            body = function(self.hooks, signature)
            self.assertIn("if (np::replaying()) replay_wait_quit();", body, signature)

    def test_window_close_does_not_race_main_thread_replay_verdict(self):
        closed = function(self.hooks, "void on_window_closed()")
        self.assertNotIn("rp::play_finish", closed)
        self.assertIn("g_replay_phase.load(std::memory_order_relaxed)", closed)
        self.assertIn("np::mode() != np::Mode::Local", closed)
        self.assertIn("t5p_exit_now(online ? 7u : 0u)", closed)

    def test_exit_phase_is_available_in_real_game_log(self):
        self.assertIn("replay exit: %s; frame %u, active %d, idle %d, paused %d, mode %u -> %u, live %d",
                      self.hooks)
        self.assertIn("replay window close: last boundary frame %u, active %d, idle %d, paused %d, mode %u -> %u, live %d",
                      self.hooks)


if __name__ == "__main__":
    unittest.main()
