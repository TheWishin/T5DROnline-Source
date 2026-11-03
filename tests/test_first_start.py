"""First-start controls hint lifecycle; no GUI, game, build or controller."""
import json
import os
import sys
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import first_start  # noqa: E402


class ControlsHintTests(unittest.TestCase):
    def test_new_or_old_settings_show_once_across_restarts(self):
        for initial in ({}, {"controls_hint_shown": False}, {"controls_hint_shown": "true"}):
            with self.subTest(initial=initial):
                settings = dict(initial)
                shown, saved = [], []
                save = lambda: saved.append(json.dumps(settings))
                self.assertTrue(first_start.show_controls_hint(settings, shown.append, save))
                self.assertEqual(len(shown), 1)
                self.assertIn("Controller Setup", shown[0])
                self.assertIs(settings["controls_hint_shown"], True)
                reloaded = json.loads(saved[0])
                self.assertFalse(first_start.show_controls_hint(reloaded, shown.append, save))
                self.assertEqual(len(shown), 1)
                self.assertEqual(len(saved), 1)

    def test_readonly_does_not_show_or_consume(self):
        settings = {}
        show, save = mock.Mock(), mock.Mock()
        self.assertFalse(first_start.show_controls_hint(settings, show, save, readonly=True))
        self.assertEqual(settings, {})
        show.assert_not_called()
        save.assert_not_called()

    def test_dialog_failure_leaves_pending_and_does_not_save(self):
        settings = {}
        save = mock.Mock()
        with self.assertRaises(RuntimeError):
            first_start.show_controls_hint(settings, mock.Mock(side_effect=RuntimeError("dialog")), save)
        self.assertEqual(settings, {})
        save.assert_not_called()

    def test_save_failure_allows_retry(self):
        settings = {"controls_hint_shown": False}
        show = mock.Mock()
        with self.assertRaises(OSError):
            first_start.show_controls_hint(settings, show, mock.Mock(side_effect=OSError("read only")))
        self.assertIs(settings["controls_hint_shown"], False)
        self.assertTrue(first_start.show_controls_hint(settings, show, lambda: None))
        self.assertEqual(show.call_count, 2)

    def test_modal_reentry_does_not_repeat(self):
        settings = {}
        calls = []

        def show(text):
            calls.append(text)
            self.assertFalse(first_start.show_controls_hint(settings, show, lambda: None))

        self.assertTrue(first_start.show_controls_hint(settings, show, lambda: None))
        self.assertEqual(len(calls), 1)

    def test_text_translated_when_shown(self):
        show = mock.Mock()
        with mock.patch.object(first_start, "t", return_value="translated hint") as translate:
            first_start.show_controls_hint({}, show, lambda: None)
        translate.assert_called_once_with(first_start.CONTROLS_HINT)
        show.assert_called_once_with("translated hint")


if __name__ == "__main__":
    unittest.main()
