"""1.2.1: the Old PC settings (launcher/core.py OLD_PC_PRESET, apply_old_pc; docs/WEAK_PC.md "Old PCs"). No game needed.

* An old PC = a processor with 2 cores or fewer, or a graphics card with D3D12 resource binding tier 1 as the newest
  game log names it ("[gpu] adapter: ... resource binding tier 1").
* On such a PC, while the graphics settings are as the launcher ships them, the launcher puts the Old PC settings in
  once (Internal resolution Lowest, stage blur, shadows and effects off) and says so; a PC whose settings were
  changed, or after Default, never gets them by itself again; a PC that is not old stays undecided (a later game log
  may name an old card).
* Settings -> Graphics has an "Old PC" button; every text is in every catalog.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core  # noqa: E402

GT730 = ("[gpu] adapter: NVIDIA GeForce GT 730 (vendor 10DE, 4031 MB, feature level 11_0, resource binding tier 1, "
         "heap tier 1, dedicated) -- the high-performance GPU\n")
KEPLER = GT730.replace("tier 1, heap", "tier 2, heap")


class OldPc(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="t5dr-oldpc")
        self.addCleanup(shutil.rmtree, self.d, True)

    def settings(self, saved=None):
        p = os.path.join(self.d, "launcher.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dict({"settings_version": 1}, **(saved or {})), f)
        return core.Settings(p)

    def log(self, text):
        os.makedirs(os.path.join(self.d, "logs"), exist_ok=True)
        p = os.path.join(self.d, "logs", "game-20261104-120000.log")
        with open(p, "w", encoding="utf-8") as f:
            f.write("[sched] processors: 4 logical, 2 cores\n" + text)
        return p

    def test_reasons(self):
        self.assertEqual(core.old_pc_reasons(self.d, cores=4, gpu=False), [])
        self.assertEqual([r[0] for r in core.old_pc_reasons(self.d, cores=2, gpu=False)],
                         ["a processor with {cores} cores"])
        self.assertEqual(core.old_pc_reasons(self.d, cores=4, gpu=("GT 730", 1))[0][1], {"name": "GT 730"})
        self.assertEqual(core.old_pc_reasons(self.d, cores=8, gpu=("GT 730", 2)), [])     # Kepler: tier 2 is fine

    def test_tier_from_the_game_log(self):
        self.assertIsNone(core.last_gpu_tier(self.d))
        p = self.log(GT730)
        self.assertEqual(core.last_gpu_tier(self.d), ("NVIDIA GeForce GT 730", 1))
        self.assertEqual(core.last_gpu_tier(None, logs=[p]), ("NVIDIA GeForce GT 730", 1))
        self.log(KEPLER)
        self.assertEqual(core.last_gpu_tier(self.d)[1], 2)

    def test_applied_once_on_an_old_pc(self):
        s = self.settings()
        self.assertEqual(s["old_pc"], "auto")
        reasons = core.apply_old_pc(s, reasons=[("a processor with {cores} cores", {"cores": 2})])
        self.assertTrue(reasons)
        self.assertEqual(core.preset_in_use(s), "old_pc")
        self.assertEqual(s["old_pc"], "done")
        env = s.env_overrides()
        self.assertEqual((env["PS3_INTERNAL_RES"], env["PS3_STAGE_BLUR"], env["PS3_SHADOWS"], env["PS3_EFFECTS"]),
                         ("lowest", "0", "0", "0"))
        text = core.old_pc_text(reasons)
        self.assertIn("2 cores", text)
        self.assertIn("Default", text)
        # Default by hand: the normal look, and it never comes back by itself
        core.apply_preset(s, core.DEFAULT_PRESET)
        self.assertIsNone(core.apply_old_pc(s, reasons=reasons))
        self.assertEqual(core.preset_in_use(s), "default")

    def test_not_over_the_players_choice(self):
        s = self.settings({"internal_res": "1080p", "internal_res_set": True})
        self.assertIsNone(core.apply_old_pc(s, reasons=[("x", {})]))
        self.assertEqual(s["internal_res"], "1080p")
        self.assertEqual(s["old_pc"], "done")
        s = self.settings({"shadows": "off"})
        self.assertIsNone(core.apply_old_pc(s, reasons=[("x", {})]))
        self.assertEqual(s["effects"], "on")

    def test_not_old_stays_undecided(self):
        s = self.settings()
        self.assertIsNone(core.apply_old_pc(s, reasons=[]))
        self.assertEqual(s["old_pc"], "auto")           # the next game's log may name a tier-1 card
        self.log(GT730)
        reasons = core.old_pc_reasons(self.d, cores=8)
        self.assertTrue(core.apply_old_pc(s, reasons=reasons))
        self.assertIn("GT 730", core.old_pc_text(reasons))

    def test_launcher_wiring(self):
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("core.OLD_PC_PRESET", src)
        self.assertIn("core.apply_old_pc(self.settings)", src)
        self.assertIn("self._old_pc_check(show=False)", src)     # after a game too: the log names the card

    def test_every_catalog_has_the_texts(self):
        import importlib.util
        texts = ["a processor with {cores} cores", "an old graphics card ({name}: resource binding tier 1)", "Old PC",
                 "This PC looks like an old PC ({why}), so the launcher chose the Old PC settings: Internal resolution "
                 "Lowest, no stage blur, no shadows and no effects. Settings -> Graphics -> Default puts the normal "
                 "look back."]
        for lang in ("de", "es", "ko", "ja", "pt_br", "fr"):
            spec = importlib.util.spec_from_file_location(f"i18n_{lang}_oldpc",
                                                          os.path.join(ROOT, "lobby", "t5lobby", f"i18n_{lang}.py"))
            cat = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cat)
            for x in texts:
                self.assertTrue(cat.MESSAGES.get(x), (lang, x))


if __name__ == "__main__":
    unittest.main()
