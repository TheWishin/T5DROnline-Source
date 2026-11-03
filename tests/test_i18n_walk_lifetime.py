"""The real layout walk releases its destroyed App even when its results are cached."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PROBE = r'''
import contextlib
import gc
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import weakref
import webbrowser
from unittest import mock

import tkinter as tk
try:
    display_probe = tk.Tk()
except tk.TclError as error:
    print("TK_UNAVAILABLE: " + str(error), flush=True)
    raise SystemExit(77)
display_probe.withdraw()
display_probe.destroy()
del display_probe
gc.collect()

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "tests"))
import i18n_layout as layout
import core
import updater
from t5lobby import dialogs, fighter_art, rank_art
from tkinter import filedialog, messagebox, simpledialog

launcher = layout.load_launcher()
owner = threading.get_ident()
released = []
refs = []
widgets = []
errors = []
threading.excepthook = lambda args: errors.append((args.exc_type.__name__, str(args.exc_value)))
launcher.App.report_callback_exception = lambda self, kind, value, tb: errors.append((kind.__name__, str(value)))
# Closing this App must leave callbacks belonging to other interpreters alone.
other = tk.Tcl()
other_value = tk.StringVar(other, value="before")
other_changes = []
other_value.trace_add("write", lambda *_: other_changes.append(other_value.get()))

class StopWalk(Exception):
    pass

def inspect_app(walk):
    app = walk.app
    assert app.theme is not None, "the regression requires the real theme"
    widgets.append(len(app.winfo_children()))
    assert walk.px.__self__.root is app, "the callback must own this real App"
    refs.extend((weakref.ref(app), weakref.ref(app.theme.apply(app))))
    weakref.finalize(app, lambda: released.append(threading.get_ident()))
    if sys.argv[2] == "stale":
        auxiliary = tk.StringVar(app, value="stale")
        def stale_info():
            raise tk.TclError("the auxiliary variable no longer exists")
        auxiliary.trace_info = stale_info
        app._lifetime_stale_variable = auxiliary
    if sys.argv[2] == "failure":
        raise StopWalk

def denied(*args, **kwargs):
    raise AssertionError("unexpected external action during the layout lifetime check")

with contextlib.ExitStack() as stack:
    for obj, name in ((socket, "socket"), (subprocess, "Popen"), (webbrowser, "open")):
        stack.enter_context(mock.patch.object(obj, name, denied))
    if hasattr(os, "startfile"):
        stack.enter_context(mock.patch.object(os, "startfile", denied))
    for module, names in (
        (messagebox, ("showinfo", "showwarning", "showerror", "askyesno", "askyesnocancel",
                      "askokcancel", "askretrycancel", "askquestion")),
        (filedialog, ("askopenfilename", "askopenfilenames", "asksaveasfilename", "askdirectory")),
        (simpledialog, ("askstring", "askinteger", "askfloat")),
        (dialogs, ("ask_yes_no", "ask_yes_no_cancel", "show_info", "show_error", "ask_string")),
    ):
        for name in names:
            stack.enter_context(mock.patch.object(module, name, denied))
    # These boundaries read game artwork or old updater results. App, widgets,
    # theme, Walk.run and its teardown are the actual implementations.
    # Plain functions avoid Mock call histories retaining App-bound callbacks.
    stack.enter_context(mock.patch.object(rank_art.ART, "prepare", lambda *a, **k: None))
    stack.enter_context(mock.patch.object(fighter_art.FACES, "prepare", lambda *a, **k: None))
    stack.enter_context(mock.patch.object(updater, "pending_results", return_value=[]))
    stack.enter_context(mock.patch.object(layout, "load_launcher", return_value=launcher))
    stack.enter_context(mock.patch.object(layout.Walk, "_launcher", inspect_app))
    stack.enter_context(mock.patch.object(layout.Walk, "_online", lambda self: None))
    stack.enter_context(mock.patch.object(layout.Walk, "_windows", lambda self, folder: None))
    walk = layout.Walk("en", 100)
    try:
        walk.run()
    except StopWalk:
        assert sys.argv[2] == "failure"
    else:
        assert sys.argv[2] in ("success", "stale")
    # Keep walk alive, as EveryLanguageRenderTests.english does between tests.
    gc.collect()
    assert widgets and widgets[0] > 0, "App widgets were not constructed"
    assert all(ref() is None for ref in refs), "completed Walk retains its destroyed App or theme"
    assert released == [owner], (released, owner)
    assert walk.app is None
    assert errors == [], errors
    other_value.set("after")
    assert other_changes == ["after"], other_changes
print("real Walk.run/App/Tk released on its owning thread", flush=True)
'''


class WalkLifetime(unittest.TestCase):
    def test_cached_successful_walk_releases_the_tk_root(self):
        self.run_probe("success")

    def test_failed_walk_releases_the_tk_root(self):
        self.run_probe("failure")

    def test_stale_variable_cannot_prevent_destroying_the_root(self):
        self.run_probe("stale")

    def run_probe(self, outcome):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest("no tkinter")
        scope = ROOT / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="walk_lifetime_", dir=scope) as folder:
            env = dict(os.environ, TMP=folder, TEMP=folder, TMPDIR=folder,
                       T5_ONLINE_DIR=str(Path(folder) / "online"), T5_PAD_NAV="0", T5_NOTIFY="0",
                       T5_FW_CHECK="0", T5_PORTMAP="0", T5DR_NO_UPDATE_CHECK="1", T5_DISCORD="0",
                       T5_LANG="en", T5_UI_CACHE="0")
            env.pop("T5DR_UPDATE_CONFIRM", None)
            result = subprocess.run([sys.executable, "-B", "-c", PROBE, str(ROOT), outcome],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode == 77 and result.stdout.startswith("TK_UNAVAILABLE: "):
            self.skipTest(result.stdout.strip())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("real Walk.run/App/Tk released on its owning thread", result.stdout)


if __name__ == "__main__":
    unittest.main()
