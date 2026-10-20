"""Launcher Settings -> Unlocks (docs/DIRECTFIGHT.md "Unlocks"): "Unlock all stages" (T5_UNLOCK_STAGES) and
"Unlock all customization items" (T5_UNLOCK_ITEMS), off by default, offline only; a game started for online play
never gets them and keeps a save of its own (PS3_SAVEDATA_DIR, ps3recomp patch 0044), so both PCs start from the
same fresh save. The free items stay in the save, so the launcher backs the save folder up once first. No game."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core  # noqa: E402


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Settings(unittest.TestCase):
    def path(self, saved=None):
        d = tempfile.mkdtemp(prefix="t5dr-unlock")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "launcher.json")
        if saved is not None:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(saved, f)
        return p

    def test_off_by_default(self):
        s = core.Settings(self.path())
        self.assertFalse(s["unlock_stages"])
        self.assertFalse(s["unlock_items"])
        env = s.env_overrides()
        self.assertNotIn("T5_UNLOCK_STAGES", env)
        self.assertNotIn("T5_UNLOCK_ITEMS", env)
        # a launcher.json of an older version has neither key
        old = core.Settings(self.path({"display": "window1080"}))
        self.assertFalse(old["unlock_stages"] or old["unlock_items"])

    def test_on_goes_to_the_game_and_is_saved(self):
        p = self.path()
        s = core.Settings(p)
        s["unlock_stages"] = True
        s["unlock_items"] = True
        s.save()
        s2 = core.Settings(p)
        self.assertTrue(s2["unlock_stages"] and s2["unlock_items"])
        env = s2.env_overrides()
        self.assertEqual((env["T5_UNLOCK_STAGES"], env["T5_UNLOCK_ITEMS"]), ("1", "1"))
        s2["unlock_items"] = False
        self.assertNotIn("T5_UNLOCK_ITEMS", s2.env_overrides())


class GameStart(unittest.TestCase):
    """What GameRun.start hands the game: offline the settings, online neither of them and its own save folder."""

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="t5dr-unlock-out")
        self.addCleanup(shutil.rmtree, self.out, True)
        p = os.path.join(self.out, "launcher.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"unlock_stages": True, "unlock_items": True}, f)
        self.settings = core.Settings(p)

    def env_of_start(self, extra):
        seen = {}

        def fake_cmd(out, env):
            seen.update(env)
            raise FileNotFoundError("stop here")
        with mock.patch.object(core.run_game, "game_command", fake_cmd):
            with self.assertRaises(FileNotFoundError):
                core.GameRun(self.out, self.settings).start(dict(extra))
        return seen

    def test_offline_play_gets_the_unlocks_and_the_own_save(self):
        env = self.env_of_start({})
        self.assertEqual((env.get("T5_UNLOCK_STAGES"), env.get("T5_UNLOCK_ITEMS")), ("1", "1"))
        self.assertNotIn("PS3_SAVEDATA_DIR", env)

    def test_online_games_get_neither_and_a_save_of_their_own(self):
        for extra in ({"T5_CTL_DIR": "x"}, {"T5_NET_MODE": "host", "T5_FIGHT": "1,2,20,3"}, {"T5_FIGHT_FILE": "f"}):
            env = self.env_of_start(extra)
            self.assertNotIn("T5_UNLOCK_STAGES", env, extra)
            self.assertNotIn("T5_UNLOCK_ITEMS", env, extra)
            self.assertEqual(env["PS3_SAVEDATA_DIR"], core.online_saves_dir(self.out))
            self.assertNotEqual(os.path.normcase(env["PS3_SAVEDATA_DIR"]), os.path.normcase(core.saves_dir(self.out)))
        self.assertTrue(core.online_saves_dir(self.out).replace("\\", "/").endswith(
            "gamedata-online/dev_hdd0/home/00000001/savedata"))

    def test_a_long_game_folder_still_gets_the_online_save(self):
        # (security review 2) the runtime (0044) ignores a PS3_SAVEDATA_DIR of 960 bytes or more: an online game in a
        # deep folder used the player's offline save instead and went apart from a fresh one on every frame
        deep = os.path.join(self.out, *(["x" * 60] * 16))
        self.assertGreaterEqual(len(core.online_saves_dir(deep).encode("utf-8")), core.SAVEDATA_DIR_MAX)
        self.assertEqual(core.online_saves_env(deep), "./gamedata-online/dev_hdd0/home/00000001/savedata")
        self.assertEqual(core.online_saves_env(self.out), core.online_saves_dir(self.out))     # (the usual case)
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patches", "ps3recomp",
                               "0044-savedata-dir.patch"), encoding="utf-8") as f:
            patch = f.read()
        self.assertIn("s_save_root_buf[1024]", patch)              # (what SAVEDATA_DIR_MAX follows)
        self.assertIn("sizeof(s_save_root_buf) - 64", patch)

    def test_the_save_is_backed_up_once_before_free_items(self):
        sd = core.saves_dir(self.out)
        os.makedirs(os.path.join(sd, "NPUB30009-SYSNET"))
        with open(os.path.join(sd, "NPUB30009-SYSNET", "SYS-DATA"), "wb") as f:
            f.write(b"save")
        self.env_of_start({})
        root = os.path.join(self.out, "save-backups")
        backups = [d for d in os.listdir(root) if d.startswith("free-items-")]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(root, backups[0], "NPUB30009-SYSNET", "SYS-DATA"), "rb") as f:
            self.assertEqual(f.read(), b"save")
        self.env_of_start({})                                   # only once
        self.assertEqual(len([d for d in os.listdir(root) if d.startswith("free-items-")]), 1)
        self.env_of_start({"T5_CTL_DIR": "x"})                  # never for an online game

    def test_no_backup_without_saves_or_without_the_setting(self):
        self.assertIsNone(core.backup_saves_once(self.out, "free-items"))       # no save folder yet
        self.settings["unlock_items"] = False
        os.makedirs(os.path.join(core.saves_dir(self.out), "NPUB30009-SYSNET"))
        self.env_of_start({})
        self.assertFalse(os.path.isdir(os.path.join(self.out, "save-backups")))


class GameSide(unittest.TestCase):
    """The game's half (src/directfight/df_unlock.cpp, patch 0044) agrees with the launcher's."""

    def test_the_same_online_test(self):
        src = text("src", "directfight", "df_unlock.cpp")
        m = re.search(r"const bool online = (.*?);", src, re.S)
        self.assertTrue(m)
        names = set(re.findall(r'env_set\("([A-Z0-9_]+)"\)', m.group(1)))
        self.assertEqual(names, set(core.ONLINE_ENV))
        for name in core.UNLOCK_ENV:
            self.assertIn('"%s"' % name, src)

    def test_the_detours(self):
        src = text("src", "directfight", "df_unlock.cpp")
        for addr in ("0x002A732C", "0x00152918", "0x001522C8"):
            self.assertIn(addr, src)
        # online: every unlock check answers as a fresh save (0), and the item prices are left alone
        self.assertRegex(src, r"if \(g_mode == Mode::Fixed\) r = 0;")
        self.assertRegex(src, r"if \(g_mode == Mode::Save && \(g_items \|\| g_trace\)\)")

    def test_patch_0044(self):
        patch = text("patches", "ps3recomp", "0044-savedata-dir.patch")
        self.assertIn('getenv("PS3_SAVEDATA_DIR")', patch)
        self.assertIn("+#define s_save_root save_root()", patch)
        self.assertIn("PS3_SAVEDATA_DIR", text("launcher", "core.py"))


if __name__ == "__main__":
    unittest.main()
