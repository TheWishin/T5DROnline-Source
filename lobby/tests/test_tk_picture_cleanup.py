"""Character-picture timer ownership with fake widgets; no Tk window, game or sockets."""
import unittest
from types import SimpleNamespace
from unittest import mock

import util  # noqa: F401 -- repository import path only
from t5lobby import fighter_art, tk_charsel


class Var:
    def __init__(self):
        self.traces = {}

    def get(self):
        return "Jin"

    def trace_add(self, kind, callback):
        self.traces["trace1"] = (kind, callback)
        return "trace1"

    def trace_remove(self, kind, token):
        assert self.traces[token][0] == kind
        del self.traces[token]


class Button:
    def __init__(self, *_args, **_kwargs):
        self.timers = {}
        self.bindings = {}
        self.next_timer = 0
        self.inline = False
        self.after_hook = None

    def configure(self, **_kwargs):
        pass

    def bind(self, sequence, callback, **_kwargs):
        self.bindings[sequence] = callback

    def after(self, _delay, callback):
        self.next_timer += 1
        timer = "after" + str(self.next_timer)
        self.timers[timer] = callback
        if self.after_hook:
            self.after_hook()
        if self.inline:
            self.fire(timer)
        return timer

    def after_cancel(self, timer):
        self.timers.pop(timer, None)

    def fire(self, timer):
        self.timers.pop(timer)()

    def destroy(self):
        callback = self.bindings.get("<Destroy>")
        if callback:
            callback(SimpleNamespace(widget=self))


class PictureCleanupTest(unittest.TestCase):
    def setUp(self):
        self.listeners = []
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(fighter_art.FACES, "listeners", self.listeners).start()
        mock.patch.object(tk_charsel.ttk, "Button", Button).start()
        mock.patch.object(tk_charsel.CharSelect, "_styles").start()
        self.var = Var()
        self.tab = SimpleNamespace(char_var=self.var)
        view = SimpleNamespace(tab=self.tab, px=lambda value: value)
        self.sel = tk_charsel.CharSelect(view, object())
        self.button = self.sel.button

    def test_button_destroy_cancels_delayed_picture_request(self):
        self.assertEqual(len(self.button.timers), 1)
        self.button.destroy()
        # Tk deletes a destroyed widget's registered commands, but leaves its
        # pending after events unless the owner cancels them first.
        self.assertEqual(self.button.timers, {})

    def test_button_destroy_releases_picture_listener_and_variable_trace(self):
        self.assertEqual(self.listeners, [self.sel._pictures_ready])
        self.assertEqual(len(self.var.traces), 1)
        self.button.destroy()
        self.assertEqual(self.listeners, [])
        self.assertEqual(self.var.traces, {})
        self.button.destroy()  # cleanup remains safe if requested again

    def test_other_widget_destroy_does_not_cancel_picture_request(self):
        self.sel._destroy(SimpleNamespace(widget=object()))
        self.assertEqual(len(self.button.timers), 1)
        self.assertEqual(self.listeners, [self.sel._pictures_ready])

    def test_fired_timer_is_released_and_still_prepares_pictures(self):
        with mock.patch.object(fighter_art.FACES, "has", return_value=True) as has:
            self.button.fire(next(iter(self.button.timers)))
        has.assert_called_once_with(self.sel.pic_size)
        self.assertEqual(self.sel._after_ids, set())
        self.assertEqual(self.button.timers, {})

    def test_worker_completion_timer_is_cancelled_with_button(self):
        ready = mock.Mock()
        with mock.patch.object(self.sel, "out_dir", return_value="unused-output"), \
                mock.patch.object(fighter_art.FACES, "set_folder"), \
                mock.patch.object(fighter_art.FACES, "has", return_value=False), \
                mock.patch.object(fighter_art.FACES, "prepare") as prepare:
            self.sel.prepare_pictures()
        schedule = prepare.call_args.kwargs["after"]
        schedule(0, ready)
        self.assertEqual(len(self.button.timers), 2)
        self.button.destroy()
        self.assertEqual(self.button.timers, {})
        self.assertIsNone(schedule(0, ready))
        ready.assert_not_called()

    def test_completion_can_fire_before_worker_receives_timer_id(self):
        self.button.inline = True
        ready = mock.Mock()
        self.sel._after(0, ready)
        ready.assert_called_once_with()
        # Only the original delayed picture request remains registered.
        self.assertEqual(len(self.sel._after_ids), 1)
        self.assertEqual(len(self.button.timers), 1)

    def test_destruction_during_timer_registration_cancels_new_timer(self):
        self.button.after_hook = self.button.destroy
        self.sel._after(0, mock.Mock())
        self.assertEqual(self.sel._after_ids, set())
        self.assertEqual(self.button.timers, {})


if __name__ == "__main__":
    unittest.main()
