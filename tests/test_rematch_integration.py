"""Source integration guards for the host UI and agreed after-round skip.

These checks need no game, network, compiler, or dependency checkout. The
state-machine/rollback behavior itself is covered by the C++ rule tests; these
guards check that the live hooks and the authoritative fight path use them.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RematchIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fight = (ROOT / "src/directfight/df_fight.cpp").read_text(encoding="utf-8")
        cls.hooks = (ROOT / "src/netplay/t5_hooks.cpp").read_text(encoding="utf-8")

    def test_ui_sample_is_only_at_live_main_thread_boundary(self):
        start = self.hooks.index("void on_frame_start(ppu_context* ctx)")
        tick = self.hooks.index("df::ui_tick();", start)
        gate = self.hooks[start:tick]
        self.assertRegex(gate, r"if\s*\(!rb::net::bypass\(\)\s*&&\s*!np::replaying\(\)")
        self.assertIn("ctx->thread_id == (g_main_tid != ~0ull ? g_main_tid : 1)", gate)
        self.assertEqual(self.hooks.count("df::ui_tick();"), 1)
        self.assertLess(tick, self.hooks.index("if (g_idle)", start))

    def test_challenger_capture_only_filters_offline_practice(self):
        keyread = self.hooks[self.hooks.index("void keyread_tick()"):
                             self.hooks.index("/* Idle = parked", self.hooks.index("void keyread_tick()"))]
        self.assertIn("g_persistent && !np::enabled() && t5_df_offline_practice()", keyread)
        self.assertIn("if (g_offline || offline_practice)", keyread)
        first = keyread.index("if (offline_practice && df::ui_blocks_offline_pad())")
        practice = keyread.index("t5_practice_pads(&m0, &m1)")
        last = keyread.rindex("if (offline_practice && df::ui_blocks_offline_pad())")
        self.assertLess(first, practice)
        self.assertLess(practice, last)
        start = self.hooks.index("void on_frame_start(ppu_context* ctx)")
        take = self.hooks.index("if (g_persistent && !np::enabled() && t5_df_offline_practice())", start)
        branch = self.hooks[take:self.hooks.index("bool fresh_start", take)]
        self.assertIn("g_cur[0] = np::poll_now(0)", branch)
        self.assertIn("offline_frame(ctx)", branch)
        self.assertIn("g_idle = g_active.load()", branch)
        self.assertNotIn("np::begin_frame", branch)

    def test_rule_is_read_from_authoritative_fight_line(self):
        self.assertRegex(
            self.fight,
            r'_stricmp\(k.c_str\(\), "auto_skip_after_round"\) == 0\)\s*'
            r'f.rules.auto_skip_after_round = cur.substr\(eq \+ 1\) == "1";',
        )
        self.assertIn('line.find("auto_skip_after_round=") == std::string::npos', self.fight)

    def test_practice_setup_cannot_reuse_a_decided_match_or_wait_forever(self):
        # Reset treats a decided match as its win pose. Practice must revoke
        # that state before a command can race its select -> game transition.
        setup = self.fight.split("void begin_practice(uint32_t f)", 1)[1].split("\n}", 1)[0]
        phase = setup.index("set_phase(Ph::PracticeLoad")
        self.assertLess(setup.index("g_result_done = false"), phase)
        self.assertLess(setup.index("g_fresh = false"), phase)
        self.assertIn("Ph::PracticeLoad", self.fight.split("void select_load_check", 1)[1].split("void stuck_check", 1)[0])
        watchdog = self.fight.split("void stuck_check", 1)[1].split("\n}", 1)[0]
        self.assertIn("g_ph == Ph::PracticeLoad", watchdog)

    def test_every_fight_agrees_before_counters_holds_and_rule_latch(self):
        stage = self.fight[self.fight.index("case Ph::Stage:"):self.fight.index("case Ph::WaitGame:")]
        check = "np::verify_match_rules(g_session_matches + 1, g_cfg.rules.pack())"
        self.assertLess(stage.index(check), stage.index("press(p, B_CROSS, f)"))
        start = self.fight[self.fight.index("case Ph::WaitGame:"):self.fight.index("case Ph::Fight:")]
        agree = start.index(check)
        self.assertLess(agree, start.index("inject(p, false, 0)"))
        self.assertLess(agree, start.index("g_session_matches++"))
        latch = start.index("g_rules = g_cfg.rules;")
        self.assertLess(agree, latch)
        self.assertLess(latch, start.index("t5_replay_fight_start("))
        self.assertLess(latch, start.index("t5_netplay_start();"))

    def test_live_and_rollback_use_one_latched_skip_rule(self):
        start = self.hooks.index("void no_pause_rule(")
        end = self.hooks.index("void start_gate(", start)
        rule = self.hooks[start:end]
        self.assertIn("np::MatchRules::unpack(t5_df_rules())", rule)
        self.assertIn("g_np_rule.record(f, st, in, rules.auto_skip_after_round, rules.auto_skip_intro)", rule)
        self.assertIn("no_pause_rule(run, in, run >= f)", self.hooks)
        self.assertIn("no_pause_rule(f, in, true)", self.hooks)
        self.assertNotRegex(rule, r'getenv\(".*SKIP')
        self.assertIn("return df::g_rules.pack();", self.fight)


if __name__ == "__main__":
    unittest.main()
