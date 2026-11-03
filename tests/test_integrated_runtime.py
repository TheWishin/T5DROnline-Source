"""Source guards for runtime overlaps in the 1.2.0 integration; never compile or run a game.

These catch dropped imports and initialization when independent draft hunks
touch the same functions. They do not prove native compilation or peer parity.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


class IntegratedRuntimeTest(unittest.TestCase):
    def test_cover_runs_before_training_gate_and_diagnostics_keep_running(self):
        training = source("src/training/training.cpp")
        frame = training.split('extern "C" void t5_training_frame(ppu_context* ctx)', 1)[1]
        self.assertLess(frame.index("t5_boot_cover_publish();"), frame.index("if (g_boot_cover_shown) return;"))
        self.assertLess(frame.index("if (g_boot_cover_shown) return;"), frame.index("if (!g_init) init();"))
        gate = frame.split("if (g_cfg.mode == kOff", 1)[1].split("return;", 1)[0]
        self.assertIn("!g_cfg.diagnostic", gate)
        self.assertIn("const bool diagnose = g_cfg.diagnostic && !online;", training)

    def test_rule_agreement_unicode_paths_and_pacing_keep_their_dependencies(self):
        core = source("src/netplay/netplay_core.cpp")
        self.assertIn('#include "match_rule_agreement.h"', core)
        self.assertIn("MatchRuleAgreement match_rules;", core)
        self.assertIn('#include "replay_paths.h"', core)
        self.assertIn('path_env("T5_REPLAY_FILE")', core)
        self.assertIn('extern "C" void cellGcm_vrr_external_hold(void);', core)
        self.assertIn("cellGcm_vrr_external_hold();", core)

    def test_unicode_recording_initializes_rules_before_publishing_live_session(self):
        replay = source("src/netplay/replay.cpp")
        begin = replay.split("void rec_session_begin(", 1)[1].split("void rec_session_end(", 1)[0]
        # Use the shared Unicode-aware accessor so per-session overlays and
        # explicit unsets keep authority over the process environment.
        for key in ("T5_REPLAY_DIR", "T5_REPLAY_LIVE"):
            with self.subTest(path=key):
                accessor = f'np::path_environment("{key}")'
                self.assertIn(accessor, begin)
                self.assertLess(begin.index(accessor), begin.index("r.cur = st;"))
                self.assertNotIn(f'replay_paths::env("{key}")', begin)
        self.assertIn("if (dir) replay_paths::make_directory(dir);", begin)
        # Every new recording versions reset filtering, independent of the skip hint.
        self.assertIn("return kVersion;", replay.split("uint32_t rules_version(", 1)[1]
                      .split("std::vector<uint8_t> to_binary", 1)[0])
        hint = begin.index('const char* skip_format = t5_env("T5_AUTO_SKIP_AFTER_ROUND");')
        self.assertLess(hint, begin.index("r.cur = st;"))
        self.assertLess(begin.index("st->d.slot = slot;"), begin.index("r.cur = st;"))
        self.assertLess(begin.index("st->d.build = build ? build : \"\";"), begin.index("r.cur = st;"))
        self.assertNotIn("CreateDirectoryA(", replay)

    def test_boot_cover_keeps_match_rule_agreement_before_fight_start(self):
        fight = source("src/directfight/df_fight.cpp")
        self.assertIn('extern "C" void t5_boot_cover_publish(void);', fight)
        self.assertIn("std::atomic<int> g_boot_cover", fight)
        self.assertIn("struct CoverAtFrameEnd", fight)
        start = fight.split("case Ph::WaitGame:", 1)[1].split("case Ph::Fight:", 1)[0]
        agreement = start.index("np::verify_match_rules(g_session_matches + 1, g_cfg.rules.pack())")
        self.assertLess(agreement, start.index("g_rules = g_cfg.rules;"))
        self.assertLess(agreement, start.index("t5_netplay_start();"))


if __name__ == "__main__":
    unittest.main()
