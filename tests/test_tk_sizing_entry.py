"""Native offline room/profile widgets, including their font-sizing paths.

Each child owns its Tk interpreter and runs the production window constructors
and button callbacks. Transport is an in-memory recorder; no server is started.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import os
from pathlib import Path
import sys
import gc
from types import SimpleNamespace
from unittest import mock

root, route, scale = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
sys.path.insert(0, str(root / "lobby"))
try:
    import tkinter as tk
    from tkinter import font as tkfont, ttk
except ImportError:
    print("TK_UNAVAILABLE")
    raise SystemExit(77)
try:
    app = tk.Tk()
except tk.TclError as error:
    if "no display" in str(error).lower() or "couldn't connect to display" in str(error).lower():
        print("TK_NO_DISPLAY")
        raise SystemExit(77)
    raise
app.withdraw()
app.tk.call("tk", "scaling", scale / 100 * 96 / 72)
from t5lobby import i18n, theme, tk_ranked_chars, tk_rooms, tk_views

i18n.set_language("pt-BR" if route == "rooms" else "de")
errors, requests = [], []
app.report_callback_exception = lambda typ, value, tb: errors.append((typ.__name__, str(value)))

def denied(*args, **kwargs):
    raise AssertionError("external action in native sizing test")

def exercise():
    try:
        view = tk_views.OnlineView.__new__(tk_views.OnlineView)
        view.th = theme.apply(app)
        view.px, view._empty = view.th.px, {}
        room = {"id": "fixture-room", "size": 2, "players": [], "status": "waiting",
                "rematch_policy": "both_confirm", "lock": None}
        def record(name):
            def request(*args, **kwargs):
                requests.append((name, args, kwargs))
                return room
            return request
        client = SimpleNamespace(
            welcome={}, me={"id": "fixture-host", "status": "room"}, my_room=room,
            training_ok=lambda: False, room_tables_ok=lambda: True,
            casual_sets_ok=lambda: True, ingame_rematch_ok=lambda: True, auto_skip_ok=lambda: True,
            create_room=record("create"), room_lock=record("lock"), room_rules=record("rules"))
        def call(function, *args, then=None):
            result = function(*args)
            if then:
                then(result)
        tab = SimpleNamespace(parent=app, view=view, client=client, new_window=tk.Toplevel,
                              call=call, status=lambda text: None,
                              table=SimpleNamespace(fighter_name=str.title))
        view.tab = tab
        if route == "rooms":
            ui = tk_rooms.RoomsUI(tab)
            for constructor in (lambda: tk_rooms.create_window(ui),
                                lambda: tk_rooms.settings_window(ui, room)):
                ui.window = window = constructor()
                window.withdraw()
                app.update_idletasks()
                box = window.widgets["rematch_policy"]
                font = tkfont.Font(root=box, font=box.cget("font"))
                needed = max(font.measure(value) for value in box.cget("values"))
                # The closed entry's character allocation must fit every choice;
                # its arrow and border are additional native requested width.
                assert int(box.cget("width")) * font.measure("0") >= needed, (needed, box.cget("width"))
                assert box.winfo_reqwidth() >= needed, (needed, box.winfo_reqwidth())
                window.vars["rematch_policy"].set(i18n.t(tk_rooms.REMATCH_CHOICES[1][0]))
                if hasattr(window, "create_button"):
                    window.create_button.invoke()
                    assert requests[-1][0] == "create", requests
                    assert requests[-1][2]["rematch_policy"] == "auto_unless_declined", requests
                else:
                    window.save_button.invoke()
                    assert requests[-1] == ("rules", ("auto_unless_declined", None), {}), requests
                ui.close_window()
        else:
            card = view.card(app)
            card.pack(fill="both", expand=True)
            ranked = tk_ranked_chars.RankedCharacters(view, card)
            ranked.shown({"ranked_chars": [{"char": "fixture", "games": 3, "wins": 1,
                                           "losses": 1, "draws": 1, "win_rate": 33.33}]})
            app.update_idletasks()
            tv = ranked.tv
            style = ttk.Style(tv)
            heading = str(tv.cget("style") or "Treeview") + ".Heading"
            font = tkfont.Font(root=tv, font=style.lookup(heading, "font") or "TkHeadingFont")
            padding = [tv.winfo_pixels(value) for value in
                       tv.tk.splitlist(style.lookup(heading, "padding") or "0")]
            horizontal_padding = padding[0] + padding[2] if len(padding) >= 3 else 2 * padding[0]
            requirements = [(column, font.measure(tv.heading(column, "text"))
                             + max(horizontal_padding, view.px(12))) for column in tk_ranked_chars.COLUMNS]
            for option in ("width", "minwidth"):
                for column, needed in requirements:
                    assert tv.column(column, option) >= needed, (column, option, needed, tv.column(column))
            assert tv.item("ranked:fixture", "values")[-1] == "33,33 %"
            ranked.shown({})
            assert not ranked.frame.winfo_manager()
            assert not tv.get_children()
    except BaseException:
        import traceback
        errors.append(traceback.format_exc())
    finally:
        app.destroy()

with mock.patch("socket.socket", side_effect=denied), mock.patch("subprocess.Popen", side_effect=denied):
    app.after(0, exercise)
    app.mainloop()
gc.collect()
assert not errors, errors
print("native sizing entry passed: %s %s" % (route, scale))
'''


class NativeSizingEntry(unittest.TestCase):
    def run_route(self, route):
        scope = ROOT / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        for scale in (100, 150):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory(prefix="native_sizing_", dir=scope) as folder:
                env = dict(os.environ, TEMP=folder, TMP=folder, TMPDIR=folder,
                           T5_UI_CACHE="0", T5_NOTIFY="0", T5_PAD_NAV="0", T5_FW_CHECK="0",
                           PYTHONIOENCODING="utf-8")
                result = subprocess.run([sys.executable, "-B", "-X", "faulthandler", "-c", PROBE,
                                         str(ROOT), route, str(scale)],
                                        cwd=ROOT, env=env, capture_output=True, text=True,
                                        encoding="utf-8", timeout=30)
            output = result.stdout + result.stderr
            if result.returncode == 77 and ("TK_UNAVAILABLE" in output or "TK_NO_DISPLAY" in output):
                self.skipTest(output.strip())
            self.assertEqual(result.returncode, 0, output)
            self.assertEqual(result.stderr, "", result.stderr)
            self.assertIn(f"native sizing entry passed: {route} {scale}", result.stdout)

    def test_real_room_create_and_settings_choices_and_buttons(self):
        self.run_route("rooms")

    def test_real_ranked_headings_profile_and_old_server(self):
        self.run_route("ranked")


if __name__ == "__main__":
    unittest.main()
