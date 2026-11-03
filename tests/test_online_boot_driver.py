"""Online boot-cover contracts that need no executable or game data.

These source checks fail before the presentation cover exists. They guard the
thread boundary and the title/sync invariants; rendering and pair determinism
still require the owner's real-build smoke tests.
"""
import os
import re
import unittest

from helpers import ROOT


class OnlineBootDriverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "src", "directfight", "df_fight.cpp"),
                  encoding="utf-8-sig") as src:
            cls.src = src.read()

    def body(self, signature):
        match = re.search(re.escape(signature) + r"\s*\{(.*?)\n\}", self.src, re.S)
        self.assertIsNotNone(match, signature)
        return match.group(1)

    def test_off_by_default_explicit_switch_only(self):
        # owner decision 1.2.0: no Connecting cover by default, online starts included (the game's own logos,
        # movie, title and loading pictures as in 1.1.9); T5_ONLINE_FAST_BOOT=1 turns it on for testers
        init = self.body("void fight_init()")
        self.assertIn('getenv("T5_ONLINE_FAST_BOOT")', init)
        self.assertIn("g_boot_cover_enabled = sw && *sw == '1';", init)
        self.assertNotIn(": online;", init)
        self.assertLess(init.index("g_boot_cover.store"), init.index("t5_boot_cover_publish()"))

    def test_renderer_query_is_host_only(self):
        query = re.search(r'extern "C" int t5_df_boot_cover\(void\) \{([^}]+)\}', self.src)
        self.assertIsNotNone(query)
        self.assertIn("g_boot_cover.load(std::memory_order_relaxed)", query.group(1))
        for forbidden in ("rd32", "mode_cur", "mode_manager", "g_ph"):
            self.assertNotIn(forbidden, query.group(1))

    def test_cover_waits_for_input_ready_select_or_loaded_fight(self):
        update = self.body("void boot_cover_update()")
        self.assertIn("mode_next() == kModeNone", update)
        self.assertIn("(g_ph == Ph::Pick || g_ph == Ph::PickWait) && g_pick.live", update)
        self.assertIn("mode_cur() == kModeSelect && rd32(kSelectState) == 3", update)
        self.assertIn("(g_ph == Ph::Fight || g_ph == Ph::Over)", update)
        self.assertIn("mode_cur() == kModeGame", update)
        self.assertIn("fight && (g_boot_fight_ready || rd32(kSelectState) >= 17)", update)
        self.assertIn("if (!fight) g_boot_fight_ready = false", update)
        # First ready boundary stays covered; a lost readiness resets the latch.
        self.assertIn("const bool reveal = ready && g_boot_ready_last", update)
        self.assertIn("g_boot_ready_last = ready", update)
        self.assertIn("g_boot_cover_enabled && !reveal", update)

    def test_cover_changes_no_guest_state_or_input(self):
        update = re.sub(r"/\*.*?\*/", "", self.body("void boot_cover_update()"), flags=re.S)
        for forbidden in ("wr8(", "wr16(", "wr32(", "gcall(", "inject(", "press(", "t5_netplay_start("):
            self.assertNotIn(forbidden, update)
        frame = self.body("void fight_on_frame(uint32_t f)")
        self.assertIn("~CoverAtFrameEnd() { boot_cover_update(); }", frame)

    def test_required_title_and_sync_sequence_is_retained(self):
        title = re.search(r"case Ph::Title:(.*?)case Ph::Select:", self.src, re.S).group(1)
        self.assertIn("mode_next() != kModeNone", title)
        self.assertIn("f >= g_title_seen + 30", title)
        for check in ("autosave_running()", "!reader_idle()", "fresh_restore(f)", "fresh_take(f)"):
            self.assertLess(title.index(check), title.index("gcall(kFnStartGame, 4, 3)"))
        wait = re.search(r"case Ph::WaitGame:(.*?)case Ph::Fight:", self.src, re.S).group(1)
        self.assertIn("rd32(kSelectState) < 7", wait)
        self.assertLess(wait.index("rd32(kSelectState) < 7"), wait.index("t5_netplay_start()"))


if __name__ == "__main__":
    unittest.main()
