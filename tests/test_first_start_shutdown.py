"""Closing the real launcher during its first hint never saves dead Tk widgets."""
import unittest
from unittest import mock

import test_i18n as ti
import test_launcher_guard as guard


@unittest.skipIf(ti.tk is None, "no tkinter")
class HintShutdown(ti.Base):
    def test_close_during_modal_hint_saves_before_widgets_are_destroyed(self):
        mod, app = guard.Guard.app(self)
        app.settings.pop("controls_hint_shown", None)
        errors = []
        saves_at_dialog_close = []
        app.report_callback_exception = lambda *error: errors.append(error)

        def show(_title, _text, parent):
            dialog = ti.tk.Toplevel(parent)
            dialog.withdraw()
            parent.after(0, parent.on_close)
            parent.wait_window(dialog)
            saves_at_dialog_close.append(save.call_count)

        with mock.patch.object(mod.dialogs, "show_info", side_effect=show), \
                mock.patch.object(app, "save_settings", wraps=app.save_settings) as save:
            app._controls_first_start()
        self.assertEqual(errors, [])
        self.assertGreaterEqual(save.call_count, 1)
        self.assertEqual(save.call_count, saves_at_dialog_close[0])
        self.assertTrue(app.settings["controls_hint_shown"])
        with self.assertRaises(ti.tk.TclError):
            app.winfo_exists()

    def test_hint_callback_after_destroy_does_not_show_or_save(self):
        mod, app = guard.Guard.app(self)
        app.settings.pop("controls_hint_shown", None)
        app.destroy()
        with mock.patch.object(mod.dialogs, "show_info") as show, \
                mock.patch.object(app, "save_settings") as save:
            app._controls_first_start()
        show.assert_not_called()
        save.assert_not_called()
        self.assertNotIn("controls_hint_shown", app.settings)


if __name__ == "__main__":
    unittest.main()
