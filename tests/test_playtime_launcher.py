"""The launcher's side of the time-played line: counted from the started game's process, stored next to
launcher.json, kept by an update, shipped in the release zip, a text in every catalog. Temporary folders only."""
import ast
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launcher"))
TEXT = "Playtime: {hours} h {minutes} min"


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("launcher_playtime_probe", str(ROOT / "launcher/t5dr_launcher.pyw"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Var:
    def __init__(self):
        self.value, self.sets = "", 0

    def get(self):
        return self.value

    def set(self, value):
        self.value, self.sets = value, self.sets + 1


class LauncherPlaytime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = load_launcher()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        L = self.launcher
        self.store = L.playtime.Store(os.path.join(self.tmp.name, "playtime.json"))
        self.app = types.SimpleNamespace(playtime_store=self.store, playtime_session=None, _playtime_read=(0.0, 0.0),
                                         PLAYTIME_GAME=L.App.PLAYTIME_GAME, playtime_var=Var())
        for name in ("_playtime_start", "playtime_seconds", "_playtime_show"):
            setattr(self.app, name, types.MethodType(getattr(L.App, name), self.app))

    def game(self, seconds, playback=False):
        proc = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(%s)" % seconds])
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        return types.SimpleNamespace(proc=proc, _playback=playback)

    def test_fresh_install_shows_zero_and_writes_nothing(self):
        self.app._playtime_show(force=True)
        self.assertEqual(self.app.playtime_var.get(), "Playtime: 0 h 0 min")
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_a_game_is_counted_until_it_ends(self):
        self.store.add("t5dr", 3600)
        game = self.game(1.0)
        self.app._playtime_start(game)
        session = self.app.playtime_session
        self.assertTrue(session.running())
        session.thread.join(20)
        seconds = self.app.playtime_seconds()
        self.assertIsNone(self.app.playtime_session)
        self.assertGreater(seconds, 3600.5)
        self.assertLess(seconds, 3610)
        self.assertEqual(self.store.sessions("t5dr"), 1)
        self.app._playtime_show()
        self.assertEqual(self.app.playtime_var.get(), "Playtime: 1 h 0 min")

    def test_killed_game(self):
        game = self.game(60)
        self.app._playtime_start(game)
        game.proc.kill()
        self.app.playtime_session.thread.join(20)
        self.assertLess(self.app.playtime_seconds(force=True), 10)

    def test_replay_playback_is_not_played(self):
        self.app._playtime_start(self.game(0.2, playback=True))
        self.assertIsNone(self.app.playtime_session)
        self.assertFalse(os.path.exists(self.store.path))

    def test_line_is_set_only_when_it_changes(self):
        self.store.add("t5dr", 125)
        for _ in range(5):
            self.app._playtime_show(force=True)
        self.assertEqual(self.app.playtime_var.get(), "Playtime: 0 h 2 min")
        self.assertEqual(self.app.playtime_var.sets, 1)

    def test_no_module_no_line(self):
        self.app.playtime_store = None
        self.app._playtime_show(force=True)
        self.app._playtime_start(self.game(0.1))
        self.assertEqual(self.app.playtime_var.get(), "")

    def test_file_is_next_to_the_settings(self):
        L = self.launcher
        os.environ.pop("T5DR_PLAYTIME_FILE", None)
        settings = L.core.Settings(os.path.join(self.tmp.name, "launcher.json"))
        self.assertEqual(L.playtime.default_path(settings.settings_dir, "T5DR_PLAYTIME_FILE"),
                         os.path.join(self.tmp.name, "playtime.json"))


class Shipping(unittest.TestCase):
    def test_update_keeps_the_file_and_swaps_the_program(self):
        import updater
        for name in ("playtime.json", "playtime.json.bak", "playtime.json.bad"):
            self.assertIn(name, updater.PROTECTED)
            self.assertNotIn(name, updater.PROGRAM_ITEMS)
        self.assertIn("launcher", updater.PROGRAM_ITEMS)          # playtime.py comes with the new launcher

    def test_release_zip_carries_the_module(self):
        tree = ast.parse((ROOT / "tools/package_release.py").read_text(encoding="utf-8"))
        listed = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        self.assertIn("launcher/playtime.py", listed)

    def test_every_catalog_has_the_text(self):
        sys.path.insert(0, str(ROOT / "lobby"))
        from t5lobby import i18n
        for lang in ("de", "es", "ko", "ja", "pt-BR", "fr"):
            with self.subTest(lang=lang):
                i18n.init(lang)
                text = i18n.t(TEXT, hours=12, minutes=5)
                self.assertNotEqual(text, "Playtime: 12 h 5 min")
                self.assertIn("12", text)
                self.assertIn("5", text)
        i18n.init("en")
        self.assertEqual(i18n.t(TEXT, hours=12, minutes=5), "Playtime: 12 h 5 min")

    def test_playtime_files_are_never_committed(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
        self.assertIn("playtime.json*", ignored)


if __name__ == "__main__":
    unittest.main()
