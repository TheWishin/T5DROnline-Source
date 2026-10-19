"""Select restarts (docs/DIRECTFIGHT.md "Select restarts"): the harness's parts that need no game
(tools/pick_flow_test.py --aborts / --abort-plan / --offline) and the driver's restart path."""
import os
import re
import sys
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pick_flow_test as pft  # noqa: E402

# What the 4th in-place restart printed (build/selrestart run r1, shortened).
BROKEN = """\
[df] frame 1445: select screen restart (func_0004E9DC(4, 3) at the select screen; no fight since the title)
[null-write] guest wrote32 0x0 to 0x00000008 (NULL+0x8) by guest-fn=0x002B1F40 -- DROPPED
[GSTACK:nw] chain: func_002B1808+0x84 func_002B1900+0x2C func_002B29A0+0x354 func_002ADAB8+0x2A4
[null-write] further stores into the null page are dropped without a word
[ppu] guest_call: OPD 0x004635A8 -> code 0x00000000 not registered (opd: 00000000 00000000 00000000 00000000)
"""

# A restart through the mode manager, as the fixed driver logs it.
FIXED = """\
[df] frame 1545: control command 6: idle (0 variable(s))
[df] frame 1545: state reset
[df] frame 1545: select screen restart (start VS at the select screen, select mode 0x1062F600 ended and built again by the mode manager; no fight since the title)
[df] frame 1597: select screen restarted (3 in this game)
[df] frame 1597: state neutral
[cellSaveData] dispatching funcStat OPD=0x00458688 (cb=0x24E0000 get=0x24E0020 set=0x24E06D0, isNew=1, userdata=0x00000000)
"""


class AbortPlanTest(unittest.TestCase):
    def test_aborts_before_match_1(self):
        self.assertEqual(pft.abort_plan(50, ""), {0: 50})

    def test_plan_and_aborts_add_up(self):
        self.assertEqual(pft.abort_plan(5, "0:3, 2:10,2:1,4:0"), {0: 8, 2: 11})

    def test_nothing(self):
        self.assertEqual(pft.abort_plan(0, ""), {})
        self.assertEqual(pft.abort_plan(0, None), {})

    def test_bad_items(self):
        with self.assertRaises(ValueError):
            pft.abort_plan(0, "1:-2")
        with self.assertRaises(ValueError):
            pft.abort_plan(0, "x")


class LogCheckTest(unittest.TestCase):
    def test_the_old_corruption_is_caught(self):
        self.assertEqual(pft.bad_lines(BROKEN), ["bad_guest_call", "null_write"])

    def test_a_restart_through_the_manager_is_clean(self):
        self.assertEqual(pft.bad_lines(FIXED), [])
        self.assertEqual(len(pft.RE_RESTARTED.findall(FIXED)), 1)
        self.assertEqual(len(pft.RE_RESTARTED.findall(BROKEN)), 0)   # "restart" alone is the request, not the result

    def test_stuck_and_crash_lines(self):
        self.assertIn("reset_stuck", pft.bad_lines("[df] frame 9000: reset: waiting in mode 6\n"))
        self.assertIn("crash", pft.bad_lines("[CRASH] access violation at 0x0\n"))


class SessionEnvTest(unittest.TestCase):
    def game(self, role):
        return SimpleNamespace(role=role, result_path="r.json", status_path="s.json")

    def test_offline_session_has_no_netplay(self):
        a = SimpleNamespace(offline=True, rounds=1, delay=2)
        env = pft.session_env(a, 1001, "a001", self.game("host"), 9000)
        self.assertNotIn("T5_NET_MODE", env)
        self.assertNotIn("T5_NET_PORT", env)
        self.assertEqual(env["T5_NET_RESULT_FILE"], "r.json")

    def test_pair_sessions_get_their_own_ports_and_keys(self):
        a = SimpleNamespace(offline=False, rounds=1, delay=2)
        h = pft.session_env(a, 1001, "a001", self.game("host"), 9600)
        j = pft.session_env(a, 1001, "a001", self.game("join"), 9600)
        self.assertEqual((h["T5_NET_MODE"], j["T5_NET_MODE"]), ("host", "join"))
        self.assertEqual(h["T5_NET_PEER"], f"127.0.0.1:{j['T5_NET_PORT']}")
        self.assertEqual(h["T5_NET_KEY"], j["T5_NET_KEY"])
        self.assertNotEqual(h["T5_NET_KEY"], pft.session_env(a, 1002, "a002", self.game("host"), 9604)["T5_NET_KEY"])


class DriverSourceTest(unittest.TestCase):
    """The restart must stay a mode change (the in-place restart left the old select scene running)."""

    def setUp(self):
        with open(os.path.join(ROOT, "src", "directfight", "df_fight.cpp"), encoding="utf-8-sig") as f:
            self.src = f.read()

    def test_restart_goes_through_the_mode_manager(self):
        m = re.search(r"void select_restart\(uint32_t f\)\s*\{(.*?)\n\}", self.src, re.S)
        self.assertIsNotNone(m, "select_restart() not found")
        body = m.group(1)
        self.assertIn("gcall(kFnStartGame, 4, 3)", body)
        self.assertIn("wr32(mgr + kMgrNext, kModeSelect)", body)
        self.assertIn("wr32(mgr + kMgrParam, 0)", body)

    def test_reset_uses_it(self):
        self.assertRegex(self.src, r"g_restart_frame = f;\s*select_restart\(f\);")
        self.assertIn("T5_DF_SELECT_RESTART", self.src)


if __name__ == "__main__":
    unittest.main()
