"""Clip recording is a persisted opt-in, gated by the final power-saving setting.

No game, encoders, devices or network are started by these tests.
"""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launcher"))
import core


class ClipSettings(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "build/clips-launcher-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "launcher.json"

    def settings(self, **values):
        # Avoid the replay folder's write probe: it is unrelated to clip configuration.
        self.path.write_text(json.dumps(dict(replays=False, **values)), encoding="utf-8")
        return core.Settings(str(self.path))

    def test_new_settings_and_invalid_values_are_off(self):
        self.assertIs(core.Settings(str(self.path))["clips"], False)
        for bad in (None, "true", "false", 1, [], {}):
            with self.subTest(value=bad):
                self.assertIs(self.settings(clips=bad)["clips"], False)

    def test_choice_is_persisted(self):
        for enabled in (True, False):
            settings = self.settings(clips=enabled)
            settings.save()
            self.assertIs(core.Settings(str(self.path))["clips"], enabled)

    def test_enabled_with_power_saving_off_reaches_the_game(self):
        settings = self.settings(clips=True, power_saving="off")
        env = settings.env_overrides()
        self.assertEqual(env["PS3_CLIPS"], "1")
        self.assertEqual(env["PS3_CLIPS_SECONDS"], "30")
        with mock.patch.dict(os.environ, {"PS3_CLIPS": "0"}):
            _cmd, game_env, _cwd = core.run_game.game_command(self.tmp.name, env)
        self.assertEqual(game_env["PS3_CLIPS"], "1")

    def test_power_saving_on_suppresses_recording(self):
        self.assertEqual(self.settings(clips=True, power_saving="on").env_overrides()["PS3_CLIPS"], "0")

    def test_auto_uses_actual_power_policy(self):
        for saving in (True, False):
            with self.subTest(saving=saving), mock.patch.object(core, "power_saving_auto", return_value=(saving, "")):
                self.assertEqual(self.settings(clips=True).env_overrides()["PS3_CLIPS"], "0" if saving else "1")

    def test_final_power_override_is_respected(self):
        for laptop, expected in (("1", "0"), ("0", "1")):
            self.assertEqual(self.settings(clips=True, power_saving="off", extra_env=f"PS3_LAPTOP={laptop}")
                             .env_overrides()["PS3_CLIPS"], expected)

    def test_disabled_setting_clears_inherited_or_extra_enable(self):
        with mock.patch.object(core, "power_saving_auto", side_effect=AssertionError("unneeded power probe")), \
                mock.patch.dict(os.environ, {"PS3_CLIPS": "1"}):
            env = self.settings(extra_env="PS3_CLIPS=1\nPS3_CLIPS_SECONDS=300").env_overrides()
        self.assertEqual(env["PS3_CLIPS"], "0")
        self.assertEqual(env["PS3_CLIPS_SECONDS"], "30")

    def test_catalogs_include_controls_and_privacy(self):
        ui = ast.parse((ROOT / "launcher/t5dr_launcher.pyw").read_text(encoding="utf-8"))
        keys = {n.args[0].value for n in ast.walk(ui) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "t" and n.args
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)}
        clip_keys = {"Video clips", "Keep the last 30 seconds"}
        clip_keys.update(key for key in keys if key.startswith("Ctrl+F10 or hold SELECT"))
        self.assertEqual(len(clip_keys), 3)
        self.assertTrue(clip_keys.issubset(keys))
        for lang in ("de", "es", "fr", "ja", "ko", "pt_br"):
            tree = ast.parse((ROOT / f"lobby/t5lobby/i18n_{lang}.py").read_text(encoding="utf-8"))
            node = next(n for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "MESSAGES" for t in n.targets))
            catalog = ast.literal_eval(node.value)
            for key in clip_keys:
                with self.subTest(lang=lang, key=key):
                    self.assertTrue(catalog[key].strip())
                    self.assertNotEqual(key, catalog[key])


if __name__ == "__main__":
    unittest.main()
