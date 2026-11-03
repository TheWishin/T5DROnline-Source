"""Run the launcher's real main, App and Tk loop with offline startup boundaries.

The child owns real widgets and executes the normal startup timers. Game files,
personal-folder discovery, prerequisite probes and external processes stay outside
this smoke test; this is launcher startup evidence, not game/build acceptance.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RESULT = "LAUNCHER_MAIN_RESULT "
PROBE = r'''
import gc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from unittest import mock

root, work = map(Path, sys.argv[1:3])
os.environ.update(T5_ONLINE_DIR=str(work / "online"), T5_PAD_NAV="0", T5_NOTIFY="0",
                  T5_FW_CHECK="0", T5_PORTMAP="0", T5DR_NO_UPDATE_CHECK="1",
                  T5_DISCORD="0", T5_LANG="en")
os.environ.pop("T5DR_UPDATE_CONFIRM", None)
sys.path[:0] = [str(root / "launcher"), str(root / "lobby")]

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog
except ImportError:
    print('LAUNCHER_MAIN_RESULT {"unavailable": "ImportError"}')
    raise SystemExit(77)
try:
    check = tk.Tk()
except tk.TclError:
    # Only genuine Tk availability is a skip. Importing the launcher and running
    # its entry point below must succeed once a native root can be made.
    print('LAUNCHER_MAIN_RESULT {"unavailable": "TclError"}')
    raise SystemExit(77)
check.withdraw()
check.destroy()
del check
gc.collect()                         # free the probe root on its owning thread

import core
import updater
from t5lobby import dialogs, fighter_art, rank_art

settings = core.Settings(str(work / "launcher.json"))
settings.update(out=str(work / "output"), replay_dir=str(work / "replays"),
                language="en", controls_hint_shown=True)
core.LAUNCHER_LOG = str(work / "launcher.log")
seen = {"constructed": 0, "loop": 0, "closed": 0, "callbacks": [], "threads": [], "prereqs": 0}
apps = []

def forbidden(*args, **kwargs):
    raise AssertionError("launcher startup attempted an external action")

def prereqs():
    seen["prereqs"] += 1
    return []

def callback_error(self, exc, value, tb):
    seen["callbacks"].append(exc.__name__ + ": " + str(value))

with mock.patch.object(socket, "socket", side_effect=forbidden), \
        mock.patch.object(subprocess, "Popen", side_effect=forbidden), \
        mock.patch.object(webbrowser, "open", side_effect=forbidden), \
        mock.patch.object(core, "Settings", return_value=settings), \
        mock.patch.object(core, "find_candidates", return_value=(None, None)), \
        mock.patch.object(core, "peek_needs_keys", return_value=False), \
        mock.patch.object(core.prereqs, "check", side_effect=prereqs), \
        mock.patch.object(core.prereqs, "release_missing", return_value=False), \
        mock.patch.object(core, "game_state", return_value={"ok": False, "text": "Not built."}), \
        mock.patch.object(rank_art.ART, "prepare"), \
        mock.patch.object(fighter_art.FACES, "prepare"), \
        mock.patch.object(tk.Tk, "report_callback_exception", callback_error):
    patches = []
    for module, names in ((messagebox, ("showinfo", "showwarning", "showerror", "askyesno",
                                       "askyesnocancel", "askokcancel", "askretrycancel", "askquestion")),
                          (filedialog, ("askopenfilename", "askopenfilenames", "asksaveasfilename", "askdirectory")),
                          (simpledialog, ("askstring", "askinteger", "askfloat")),
                          (dialogs, ("show_info", "show_error", "ask_yes_no", "ask_yes_no_cancel", "ask_string"))):
        for name in names:
            patch = mock.patch.object(module, name, side_effect=forbidden)
            patch.start()
            patches.append(patch)
    if hasattr(os, "startfile"):
        patch = mock.patch.object(os, "startfile", side_effect=forbidden)
        patch.start()
        patches.append(patch)
    try:
        path = root / "launcher" / "t5dr_launcher.pyw"
        loader = importlib.machinery.SourceFileLoader("launcher_main_smoke", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)          # complete production module, no AST extraction
        original_init = launcher.App.__init__
        original_loop = launcher.run_mainloop
        original_thread_errors = launcher.log_thread_errors

        def thread_errors():
            original_thread_errors()
            production_hook = threading.excepthook

            def record(args):
                seen["threads"].append(args.exc_type.__name__ + ": " + str(args.exc_value))
                production_hook(args)
            threading.excepthook = record

        def finish(app):
            ready = (getattr(app, "_searched", False) and hasattr(app, "prereq_items")
                     and getattr(app, "_game_state", None) == {"ok": False, "text": "Not built."})
            if not ready and time.monotonic() < app._smoke_deadline:
                app.after(50, lambda: finish(app))
                return
            assert threading.current_thread() is threading.main_thread()
            assert launcher.tkgc.installed_on(app)
            assert app.nb.winfo_exists() and app.online.parent.winfo_exists()
            assert app.settings is settings and not app.readonly
            try:
                assert ready and seen["prereqs"] == 1, seen
            finally:
                app.on_close()                # production online shutdown and App.destroy
                seen["closed"] += 1

        def initialize(app, *args, **kwargs):
            original_init(app, *args, **kwargs)
            seen["constructed"] += 1
            apps.append(app)
            app.withdraw()
            app._smoke_deadline = time.monotonic() + 12
            app.after(2200, lambda: finish(app))

        def loop(app):
            seen["loop"] += 1
            return original_loop(app)         # real Tk event loop and startup timers

        def attach(app, header=None):
            return updater.Updater(app, header, root=str(work / "install"))

        saved_hook = threading.excepthook
        try:
            with mock.patch.object(launcher.App, "__init__", initialize), \
                    mock.patch.object(launcher, "run_mainloop", side_effect=loop), \
                    mock.patch.object(launcher, "log_thread_errors", side_effect=thread_errors), \
                    mock.patch.object(updater, "attach", side_effect=attach), \
                    mock.patch.object(sys, "argv", [str(path)]):
                launcher.main()
        finally:
            threading.excepthook = saved_hook
        assert seen["constructed"] == seen["loop"] == seen["closed"] == 1, seen
        assert not seen["callbacks"], seen
        assert not seen["threads"], seen
        assert gc.isenabled() and launcher.tkgc._state["root"] is None
        assert all(app.online._closed for app in apps)
        text = (work / "launcher.log").read_text(encoding="utf-8")
        assert "error in the launcher" not in text and "could not start" not in text, text
        assert (work / "launcher.json").is_file()
        apps.clear()
        gc.collect()                         # release all widget cycles before child shutdown
        print("LAUNCHER_MAIN_RESULT " + json.dumps(seen))
    finally:
        for patch in reversed(patches):
            patch.stop()
'''


class LauncherMain(unittest.TestCase):
    def test_real_main_constructs_app_runs_startup_timers_and_closes(self):
        scope = ROOT / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="launcher_main_", dir=scope) as work:
            result = subprocess.run(
                [sys.executable, "-B", "-X", "faulthandler", "-c", PROBE, str(ROOT), work],
                cwd=work, capture_output=True, text=True, timeout=20,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
        lines = [line[len(RESULT):] for line in result.stdout.splitlines() if line.startswith(RESULT)]
        if result.returncode == 77 and lines and "unavailable" in json.loads(lines[-1]):
            self.skipTest("native Tk initialization unavailable: " + json.loads(lines[-1])["unavailable"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        self.assertEqual(len(lines), 1, result.stdout + result.stderr)
        observed = json.loads(lines[0])
        self.assertEqual((observed["constructed"], observed["loop"], observed["closed"]), (1, 1, 1))
        self.assertEqual(observed["callbacks"], [])
        self.assertEqual(observed["threads"], [])


if __name__ == "__main__":
    unittest.main()
