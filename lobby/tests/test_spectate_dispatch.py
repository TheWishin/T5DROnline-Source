"""Spectator/match dispatch ordering, without Tk, processes, or a server."""
import ast
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "t5lobby" / "tk_tab.py"


def method(name, **globals_):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OnlineTab")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = dict(globals_, queue=queue, tk=SimpleNamespace(TclError=RuntimeError))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


class DispatchTests(unittest.TestCase):
    def test_teardown_cancels_spectating_before_driver_or_client_close(self):
        source = SOURCE.read_text(encoding="utf-8-sig")
        close = source.split("def on_close(self):", 1)[1].split("\n    def ", 1)[0]
        self.assertLess(close.index("self.spec.stop()"), close.index("self.driver.close()"))
        self.assertLess(close.index("self.spec.stop()"), close.index("self.client.close()"))
        logout = source.split("def do_logout(self):", 1)[1].split("\n    def ", 1)[0]
        self.assertLess(logout.index("self.spec.stop()"), logout.index("c, self.client = self.client, None"))

    def test_completed_ready_check_does_not_keep_lobby_busy(self):
        source = SOURCE.read_text(encoding="utf-8-sig")
        # Each exit from the ready question must clear its accepted flag, which
        # the idle policy checks independently of the deadline.
        for event in ("match_reveal", "match_cancel", "match_start"):
            branch = source.split('elif kind == "' + event + '":', 1)[1].split("elif kind", 1)[0]
            self.assertIn("self.ready_sent = False", branch, event)
        reset = source.split("def _reset_lobby_view(self):", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("self.ready_sent = False", reset)

    def test_preempt_before_driver_and_completed_watch_callback(self):
        seen = []
        events, results = queue.Queue(), queue.Queue()
        events.put({"t": "match_start"})
        results.put((1, True, {}))
        noop = lambda *a, **kw: None
        box = SimpleNamespace(winfo_exists=lambda: True)
        tab = SimpleNamespace(
            _closed=False, _after=None, _poll=noop,
            parent=SimpleNamespace(winfo_exists=lambda: True, after=noop),
            view=SimpleNamespace(box=box, tick=noop), ui_q=queue.Queue(),
            client=SimpleNamespace(events=events, my_room=None), results_q=results,
            room_watch=SimpleNamespace(reset=noop),
            _callbacks={1: (lambda r: seen.append("watch_callback"), None)},
            driver=SimpleNamespace(on_event=lambda ev: seen.append("driver"), poll=lambda: []),
            spec=SimpleNamespace(before_event=lambda ev: seen.append("preempt"), poll=noop),
            on_event=lambda ev: seen.append("tab"), casual=SimpleNamespace(after_event=noop),
            fw_q=queue.Queue(), _fw_result=noop,
            tours=SimpleNamespace(tick=noop), rooms_ui=SimpleNamespace(tick=noop),
            _set_actions=noop,
        )
        for name in ("_tick_ready", "_tick_set", "_invite_wait_tick", "_relogin_tick",
                     "_presence_tick", "_show_notice", "_pad_tick"):
            setattr(tab, name, noop)
        method("_poll")(tab)
        self.assertEqual(seen, ["preempt", "driver", "tab", "watch_callback"])

    def test_match_launch_never_adopts_a_spectator_that_did_not_stop(self):
        starts = []
        clock = iter((0, 6))
        game = SimpleNamespace(running=lambda: True, stop=lambda: None)
        tab = SimpleNamespace(app=SimpleNamespace(game=game, start_game=lambda env: starts.append(env)),
                              driver=None, status=lambda *a: None)
        launch = method("_launch", time=SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda n: None),
                        t=lambda s: s)
        self.assertIsNone(launch(tab, {"T5_NET_MODE": "host"}))
        self.assertEqual(starts, [])


if __name__ == "__main__":
    unittest.main()
