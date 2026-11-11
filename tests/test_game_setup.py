"""The player's own Controller Setup online (docs/NETPLAY.md "The game's Controller Setup online"). No game needed.

Player report on 1.2.2: "doesn't read my in-game config or macros for L and R 1,2,3 during quick match". The
game's OPTIONS > CONTROLLER SETUP lives in the system save; an online game plays on a fresh save of its own
(launcher/core.py PS3_SAVEDATA_DIR), where L1 R1 L2 R2 are OFF -- the player's shortcuts did nothing online.

* tests/c/game_setup_test.cpp (src/netplay/game_setup.h): the save's records, what the held buttons become
  (checked against an independent model for random setups), and when (an online fight only).
* The wiring: applied to this PC's own device sample before it is exchanged (never to scripts, the peer's input
  or the in-game select), and the launcher names the offline save for every game it starts for online play.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT
from test_always_left import build, compiler, text

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core  # noqa: E402


class Logic(unittest.TestCase):
    def test_c_unit_test_passes(self):
        vcvars, clang = compiler()
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "game_setup_test.exe")
            build(vcvars, clang, os.path.join(ROOT, "tests", "c", "game_setup_test.cpp"), exe, "/std:c++17 /EHsc")
            r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks")


class Wiring(unittest.TestCase):
    def test_applied_to_this_players_device_sample(self):
        src = text("src", "netplay", "netplay_core.cpp").replace("\r\n", "\n")
        m = re.search(r"void player_input\(PadInput\* in\)\n\{(.*?)\n\}", src, re.S)
        self.assertTrue(m)
        body = m.group(1)
        self.assertIn("in->buttons = game_setup_buttons(in->buttons);", body)
        self.assertLess(body.index("pad_into(d, in);"), body.index("game_setup_buttons"))
        # the only caller: the second local player's devices, scripts and the menu inject are left alone
        self.assertEqual(src.count("game_setup_buttons("), 1)
        m = re.search(r"PadInput sample_local\(uint32_t f\)\n\{(.*?)\n\}", src, re.S)
        self.assertLess(m.group(1).index("g_local_inject_on"), m.group(1).index("player_input(&in)"))

    def test_online_fights_only_and_never_a_replay(self):
        src = text("src", "netplay", "game_setup.cpp").replace("\r\n", "\n")
        self.assertIn("gs::active(l.on, m == Mode::Host || m == Mode::Join, replaying(), rd32(kPhase))", src)
        self.assertIn('t5_env("T5_PAD_SETUP_SAVE")', src)
        self.assertIn('t5_env("T5_COSTUME_SAVE")', src)
        # reads the save and the fight phase, writes nothing into the game
        self.assertNotRegex(src, r"\bwr(8|16|32)\(|vm_write|memcpy\(vm_base")

    def test_the_select_screen_and_replay_controls_read_the_pad_itself(self):
        src = text("src", "netplay", "local_pad.cpp")
        self.assertNotIn("game_setup", src)

    def test_launcher_names_the_offline_save_for_every_online_game(self):
        out = os.path.join("X:", os.sep, "t5")
        want = os.path.join(core.saves_dir(out), "NPUB30009-SYSNET", "SYS-DATA")
        for env in ({"T5_CTL_DIR": "ctl"}, {"T5_CTL_DIR": "ctl", "T5_QUEUEPLAY": "1"}, {"T5_NET_MODE": "host"},
                    {"T5_NET_MODE": "join"}):
            e = dict(env)
            core.costume_env(out, e)
            self.assertEqual(e.get("T5_COSTUME_SAVE"), want, env)
        e = {}
        core.costume_env(out, e)            # an offline game: its own save, read by the game itself
        self.assertNotIn("T5_COSTUME_SAVE", e)
        # the save an online game plays on is another one (there the shoulder buttons are OFF)
        self.assertNotEqual(os.path.normcase(core.online_saves_dir(out)), os.path.normcase(core.saves_dir(out)))


if __name__ == "__main__":
    unittest.main()
