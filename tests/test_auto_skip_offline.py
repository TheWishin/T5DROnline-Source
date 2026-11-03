"""Offline auto-skip (1.2.0; launcher Settings "Round endings", T5_AUTO_SKIP_OFFLINE=1; the rule:
src/netplay/no_pause.h OfflineSkip, its model test in tests/c/no_pause_test.cpp "offline skips ok").

* the launcher: off by default, the setting sends T5_AUTO_SKIP_OFFLINE=1, an online game never gets it;
* the game's side (source checks): the rule runs in keyread_tick's offline branch only, presses START (0x0800 in the
  game's port mask) on both ports, and reads the switch from the environment once;
* the texts are in every catalog."""
import os
import re
import sys
import unittest
from unittest import mock

from helpers import ROOT

for sub in ("launcher", "lobby"):
    if os.path.join(ROOT, sub) not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, sub))

import core  # noqa: E402


def read(*rel):
    with open(os.path.join(ROOT, *rel), encoding="utf-8") as f:
        return f.read()


class LauncherSide(unittest.TestCase):
    def settings(self, **kw):
        s = core.Settings.__new__(core.Settings)
        dict.__init__(s, dict(core.DEFAULTS, **kw))
        s.path = os.path.join(ROOT, "build", "nonexistent", "launcher.json")
        return s

    def test_off_by_default(self):
        self.assertIs(core.DEFAULTS["auto_skip_offline"], False)
        self.assertNotIn("T5_AUTO_SKIP_OFFLINE", self.settings().env_overrides())

    def test_the_setting_sends_the_switch(self):
        self.assertEqual(self.settings(auto_skip_offline=True).env_overrides().get("T5_AUTO_SKIP_OFFLINE"), "1")

    def test_an_online_game_never_gets_it(self):
        self.assertIn("T5_AUTO_SKIP_OFFLINE", core.OFFLINE_ONLY_ENV)
        src = read("launcher", "core.py")
        m = re.search(r"if is_online_env\(env_over\):\n(.*?)\n        elif", src, re.S)
        self.assertTrue(m)
        self.assertIn("UNLOCK_ENV + OFFLINE_ONLY_ENV", m.group(1))

    def test_the_settings_page(self):
        src = read("launcher", "t5dr_launcher.pyw")
        self.assertIn('self.auto_skip_var = tk.BooleanVar(value=bool(self.settings.get("auto_skip_offline", False)))', src)
        self.assertIn('self.settings["auto_skip_offline"] = bool(self.auto_skip_var.get())', src)


class GameSide(unittest.TestCase):
    def test_offline_branch_only(self):
        src = read("src", "netplay", "t5_hooks.cpp")
        m = re.search(r"void keyread_tick\(\)\n\{(.*?)\n\}", src, re.S)
        self.assertTrue(m)
        body = m.group(1)
        branch = re.search(r"if \(g_offline\) \{(.*?)\n    \}", body, re.S)
        self.assertTrue(branch)
        self.assertIn("offline_auto_skip(m0, m1);", branch.group(1))
        self.assertEqual(body.count("offline_auto_skip("), 1)

    def test_presses_start_on_both_ports(self):
        src = read("src", "netplay", "t5_hooks.cpp")
        m = re.search(r"void offline_auto_skip\(uint16_t& m0, uint16_t& m1\)\n\{(.*?)\n\}", src, re.S)
        self.assertTrue(m)
        body = m.group(1)
        self.assertIn("kMaskStart = 0x0800", body)
        self.assertIn("m0 = (uint16_t)(m0 | kMaskStart);", body)
        self.assertIn("m1 = (uint16_t)(m1 | kMaskStart);", body)
        self.assertIn('getenv("T5_AUTO_SKIP_OFFLINE")', body)
        self.assertIn("g_off_skip.press(st)", body)

    def test_no_start_beside_select_and_only_on_the_known_player(self):
        # review wishes-120 P2 x2: a held SELECT gets no START (soft reset); the one-player modes' port is the one
        # whose presses a fighter reads (+0x6D6), never "any input on a port"
        src = read("src", "netplay", "t5_hooks.cpp")
        body = re.search(r"void offline_auto_skip\(uint16_t& m0, uint16_t& m1\)\n\{(.*?)\n\}", src, re.S).group(1)
        sel = body.index("np::OfflineSkip::select_held(m0, m1)")
        self.assertLess(sel, body.index("m0 = (uint16_t)(m0 | kMaskStart);"))
        self.assertIn("np::OfflineSkip::ports(gt, g_off_owner.known(0), g_off_owner.known(1))", body)
        self.assertIn("g_off_owner.feed(m0, m1, rd16(kFighter0 + 0x6D6), rd16(kFighter0 + kFighterStride + 0x6D6))",
                      body)
        self.assertNotIn("g_off_used", src)
        rule = read("src", "netplay", "no_pause.h")
        self.assertIn("kMaskSelect = 0x0100", rule)
        self.assertIn("kSelect = 0x0100", read("src", "training", "training_logic.h"))

    def test_start_bit_is_the_games(self):
        self.assertIn("kStart = 0x0800", read("src", "training", "training_logic.h"))


class Texts(unittest.TestCase):
    TEXTS = ("Round endings", "Skip replays and round endings automatically (offline)",
             'Online the skip counts only when both players tick "Auto-skip replays and round endings" in the '
             'Online tab (casual matches; never ranked).')

    def test_every_language(self):
        from t5lobby import i18n
        for lang in ("de", "es", "fr", "ja", "ko", "pt-BR"):
            cat = i18n.catalog(lang)
            online = cat.get("Auto-skip replays and round endings (both players agree)")
            for text in self.TEXTS:
                self.assertNotEqual(cat.get(text, text), text, (lang, text))
            self.assertIn(online, cat[self.TEXTS[2]], lang)      # names the online checkbox as it is shown there


if __name__ == "__main__":
    unittest.main()
