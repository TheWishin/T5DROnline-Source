"""The real screenshot scheduler must exercise every current/future notebook tab."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class ScreenshotTabs(unittest.TestCase):
    def test_scheduler_renders_manifest_for_every_notebook_tab(self):
        loader = importlib.machinery.SourceFileLoader('launcher_screenshot_probe', str(ROOT / 'launcher/t5dr_launcher.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)
        pending, selected, captured = [], [], []

        class App:
            tab_keys = ['build', 'play', 'settings', 'online', 'replays', 'future']
            nb = mock.Mock()
            destroyed = False
            def after(self, ms, callback):
                if ms < 30 * 60 * 1000:
                    pending.append(callback)
            def destroy(self):
                self.destroyed = True

        app = App()
        app.nb.select.side_effect = selected.append
        with tempfile.TemporaryDirectory() as folder:
            def capture(_app, path):
                captured.append(Path(path).stem)
                Path(path).write_bytes(b'\x89PNG\r\n\x1a\n')
            with mock.patch.object(launcher, 'capture_window', side_effect=capture):
                launcher.screenshots(app, folder)
                while pending:
                    pending.pop(0)()
            self.assertTrue(app.destroyed)
            self.assertEqual(selected, list(range(len(app.tab_keys))))
            self.assertEqual(captured, ['launcher_' + key for key in app.tab_keys])
            self.assertEqual(json.loads((Path(folder) / 'tabs.json').read_text(encoding='utf-8'))['tabs'], app.tab_keys)
