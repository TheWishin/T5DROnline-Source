"""Source-only checks for rest/runtime coexistence; no compiler or game required.

Native policy and numeric harnesses remain the behavioral checks for maintainers.
These guards catch dropped hooks when this draft is combined with the existing
rematch, replay-path and VRR drafts.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


class RestRuntimeIntegration(unittest.TestCase):
    def test_jitter_policy_keeps_replay_rule_and_pacing_dependencies(self):
        core = source("src/netplay/netplay_core.cpp")
        for header in ("rollback_delay.h", "replay_paths.h", "match_rule_agreement.h"):
            self.assertIn(f'#include "{header}"', core)
        for hook in ('path_env("T5_REPLAY_FILE")', "MatchRuleAgreement match_rules;",
                     "cellGcm_vrr_external_hold();", "bool verify_match_rules("):
            self.assertIn(hook, core)
        decide = core.split("void decide_rb_delay_locked()", 1)[1].split("void send_reject(", 1)[0]
        explicit, automatic = decide.split("    } else {", 1)
        self.assertNotIn("jitter_delay", explicit)
        self.assertIn("s.rb_adaptive_delay && s.mode == Mode::Host", automatic)
        self.assertLess(automatic.index("detail::jitter_delay("), automatic.index("if (pick > s.delay)"))
        self.assertLess(automatic.index("if (pick > s.delay)"), automatic.index("s.rb_decided = pick;"))
        self.assertIn("if (s.rb_decided >= 0", explicit)

    def test_extended_screen_side_keeps_live_only_sampling_and_replay_exclusion(self):
        side = source("src/netplay/always_left.cpp")
        self.assertIn('al::parse_side(t5_env("T5_SCREEN_SIDE"), t5_env("T5_ALWAYS_LEFT"))', side)
        self.assertIn("f.replaying = np::replaying();", side)
        self.assertIn("f.online_game = online_game();", side)
        self.assertIn("port != g_mirrored_port.load", side)
        core = source("src/netplay/netplay_core.cpp")
        sampling = core.split("PadInput sample_local(uint32_t f)", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("always_left_input", sampling)

    def test_default_off_simd_and_hidden_warmup_follow_vrr_patch(self):
        directory = ROOT / "patches" / "ps3recomp"
        tail = sorted(path.name for path in directory.glob("010*.patch"))[:6]   # (0106+ may follow)
        self.assertEqual(tail, ["0100-macos-metal-slot-wait-warning.patch",
                                "0101-macos-fps-slow-frames.patch", "0102-macos-pad-file2.patch",
                                "0103-vrr-pacing.patch", "0104-low-end.patch", "0105-warmup-hidden.patch",
                                "0106-kernel-edge.patch", "0107-picture-format.patch",
                                "0109-picture-copy-scissor.patch"])
        low = source("patches/ps3recomp/0104-low-end.patch")
        self.assertIn("#define PPU_VMX_SOFT2 0", low)
        hidden = source("patches/ps3recomp/0105-warmup-hidden.patch")
        self.assertIn('background && !getenv("PS3_WINDOW_HIDDEN")', hidden)


if __name__ == "__main__":
    unittest.main()
