"""Run the updater's real Tk entry and worker queue, without downloads or swaps.

Each case has its own bounded process so a native Tk abort is reported as a
failure. Synthetic folders contain program markers only; preparation, network
and process boundaries are replaced. This is GUI lifecycle coverage, not an
end-to-end update or proof of the cause of a previous suite abort.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UNAVAILABLE = "UPDATE_GUI_UNAVAILABLE "
PROBE = r'''
import faulthandler
import gc
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import traceback
from types import SimpleNamespace
from unittest import mock

faulthandler.enable()
faulthandler.dump_traceback_later(15)
root, work, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
try:
    import tkinter as tk
except ImportError:
    print("UPDATE_GUI_UNAVAILABLE ImportError", flush=True)
    raise SystemExit(77)
try:
    app = tk.Tk()
except tk.TclError:
    # Only native Tk initialization can skip, before production updater code.
    print("UPDATE_GUI_UNAVAILABLE TclError", flush=True)
    raise SystemExit(77)
app.withdraw()
sys.path.insert(0, str(root / "launcher"))
import updater

install = work / "install"
(install / "python").mkdir(parents=True)
(install / "release.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
(install / "python" / "pythonw.exe").write_text("synthetic program marker", encoding="utf-8")
stage = work / "stage"
stage.mkdir()
release = {"version": "1.0.1", "zip": {"size": 1}, "notes": "Synthetic release", "page": ""}
events, errors, worker_threads = [], [], []
owner = threading.get_ident()

def background(name):
    assert threading.get_ident() != owner, name + " ran on the Tk thread"
    worker_threads.append(threading.current_thread())
    events.append(name)

def checked(*args, **kwargs):
    background("check")
    return release, None

def prepared(rel, folder, progress, cancel):
    background("prepare")
    assert rel == release and Path(folder) == install
    progress("download", 1, 1)
    if mode == "failure":
        raise updater.UpdateError("Synthetic preparation refused")
    return {"sroot": str(stage)}

def swapped(staged, old, new, **kwargs):
    assert threading.get_ident() == owner
    assert staged == {"sroot": str(stage)}
    assert (old, new) == ("1.0.0", "1.0.1")
    events.append("swap")

def denied(*args, **kwargs):
    raise AssertionError("unexpected external boundary")

app.settings = SimpleNamespace(out_dir=str(work / "output"))
app.readonly = False
app.statuses = []
app.set_status = app.statuses.append
app.report_callback_exception = lambda typ, value, tb: errors.append(
    "".join(traceback.format_exception(typ, value, tb)))
app.on_close = lambda: (events.append("close"), app.quit())
up = None
timed_out = []

def deadline():
    timed_out.append(True)
    app.quit()

def poll():
    if errors:
        app.quit()
        return
    if up.win is not None and "click" not in events:
        assert threading.get_ident() == owner
        assert up.release == release
        events.append("offer")
        events.append("click")
        up.b_update.invoke()
    if mode == "failure" and up.win is not None and up.err.get():
        assert up.err.get() == "Synthetic preparation refused", up.err.get()
        assert str(up.b_update.cget("state")) == "normal"
        assert "swap" not in events and "close" not in events
        events.append("refused")
        up.close_window()
        assert up.win is None
        app.quit()
        return
    app.after(10, poll)

old_hook = threading.excepthook
threading.excepthook = lambda args: errors.append(
    "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
os.environ[updater.NO_CHECK_ENV] = "1"
os.environ.pop(updater.CONFIRM_ENV, None)
try:
    with mock.patch.object(updater, "check_latest", side_effect=checked), \
            mock.patch.object(updater, "prepare_update", side_effect=prepared), \
            mock.patch.object(updater, "start_swap", side_effect=swapped), \
            mock.patch.object(updater, "processes_under", return_value=[]), \
            mock.patch.object(updater, "open_url", side_effect=denied), \
            mock.patch.object(socket, "socket", side_effect=denied), \
            mock.patch.object(subprocess, "Popen", side_effect=denied):
        up = updater.Updater(app, root=str(install))
        up.check(manual=True)
        app.after(10, poll)
        app.after(8000, deadline)
        app.mainloop()
        for thread in worker_threads:
            thread.join(2)
            assert not thread.is_alive(), "updater worker did not finish"
        assert not errors, errors
        assert not timed_out, events
        expected = ["check", "offer", "click", "prepare"]
        expected += ["refused"] if mode == "failure" else ["swap", "close"]
        assert events == expected, events
finally:
    threading.excepthook = old_hook
    for job in app.tk.splitlist(app.tk.call("after", "info")):
        app.after_cancel(job)
    if up is not None:
        up.close_window()
    app.destroy()
    up = app = None
    gc.collect()
    faulthandler.cancel_dump_traceback_later()
print("real updater Tk check/offer/button/worker/close: " + mode, flush=True)
'''


class UpdateGuiLifecycle(unittest.TestCase):
    def run_probe(self, mode):
        scope = ROOT / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="update_gui_", dir=scope) as work:
            result = subprocess.run(
                [sys.executable, "-B", "-c", PROBE, str(ROOT), work, mode],
                cwd=ROOT, capture_output=True, text=True, timeout=25,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
        unavailable = result.stdout.strip()
        if result.returncode == 77 and unavailable in (
                UNAVAILABLE + "ImportError", UNAVAILABLE + "TclError"):
            self.skipTest("native Tk initialization unavailable: " + unavailable[len(UNAVAILABLE):])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("real updater Tk check/offer/button/worker/close: " + mode, result.stdout)
        self.assertEqual(result.stderr, "", result.stderr)

    def test_update_button_reaches_swap_and_closes_through_real_tk(self):
        self.run_probe("success")

    def test_preparation_failure_keeps_real_tk_window_responsive(self):
        self.run_probe("failure")


if __name__ == "__main__":
    unittest.main()
