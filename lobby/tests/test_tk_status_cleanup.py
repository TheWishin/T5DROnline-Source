"""Online view timer lifetimes, with fake widgets and no Tcl interpreter or sockets."""
import types
import unittest
from unittest import mock

import util  # noqa: F401 -- makes the local lobby package importable
from t5lobby import tk_views


class TimerBox:
    def __init__(self):
        self.pending = {}
        self.bindings = {}
        self.serial = 0

    def after(self, _delay, callback):
        self.serial += 1
        ident = f"after#{self.serial}"
        self.pending[ident] = callback
        return ident

    def after_idle(self, callback):
        return self.after("idle", callback)

    def after_cancel(self, ident):
        del self.pending[ident]

    def bind(self, event, callback, add=None):
        self.bindings.setdefault(event, []).append(callback)

    def pack(self, **_kw):
        pass

    def columnconfigure(self, *_a, **_kw):
        pass

    def rowconfigure(self, *_a, **_kw):
        pass


class StatusTimerCleanupTest(unittest.TestCase):
    def view(self):
        view = object.__new__(tk_views.OnlineView)
        view.tab = mock.Mock()
        view.px = lambda n: n
        view.th = mock.Mock()
        view.th.fonts = {"h3": mock.Mock()}
        view.err_var = mock.Mock()
        view._closed = False
        view._anim_id = None
        view._wrap_after = None
        view._status_after = None
        view.box = TimerBox()
        view.card = mock.Mock(side_effect=lambda *_a: mock.Mock())
        view.wrap = lambda label, *_a: label
        return view

    def build_footer(self, view):
        with mock.patch.multiple(tk_views.ttk, Frame=mock.Mock(), Label=mock.Mock(),
                                 Button=mock.Mock(), Checkbutton=mock.Mock()), \
                mock.patch.object(tk_views.tk, "Canvas", mock.Mock()):
            view._build_footer(view.box)

    def test_close_cancels_real_footer_idle_before_widget_destruction(self):
        view = self.view()
        self.build_footer(view)
        self.assertEqual(len(view.box.pending), 1)
        view.close()
        self.assertEqual(view.box.pending, {})
        self.assertIsNone(view._status_after)
        view.close()  # repeated owner/parent teardown remains safe

    def test_finished_status_idle_is_no_longer_pending_at_close(self):
        view = self.view()
        self.build_footer(view)
        ident, callback = next(iter(view.box.pending.items()))
        del view.box.pending[ident]
        view._place_footer = mock.Mock()
        callback()
        self.assertIsNone(view._status_after)
        view._place_footer.assert_called_once_with()
        view.close()

    def test_box_destruction_cancels_status_wrap_and_animation(self):
        view = self.view()
        box = view.box
        view._build_login = mock.Mock()
        view._build_lobby = mock.Mock()
        view._build_footer = mock.Mock()
        with mock.patch.object(tk_views.ttk, "Frame", return_value=box):
            view._build()
        self.assertIn("<Destroy>", box.bindings)
        on_destroy, = box.bindings["<Destroy>"]
        view._status_after = box.after_idle(view._place_status)
        view._wrap_after = box.after(60, view._apply_wraps)
        view._anim_id = box.after(33, view._anim)
        on_destroy(types.SimpleNamespace(widget=object()))
        self.assertEqual(len(box.pending), 3)
        on_destroy(types.SimpleNamespace(widget=box))
        self.assertEqual(box.pending, {})
        self.assertTrue(view._closed)

    def test_close_prevents_late_event_scheduling_and_callbacks(self):
        view = self.view()
        view._anim_needed = mock.Mock(return_value=True)
        view._place_footer = mock.Mock()
        view.close()
        view._on_resize()
        view._ensure_anim()
        view._place_status()
        view._anim()
        self.assertEqual(view.box.pending, {})
        view._anim_needed.assert_not_called()
        view._place_footer.assert_not_called()


if __name__ == "__main__":
    unittest.main()