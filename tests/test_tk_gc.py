"""The launcher frees garbage -- Tk objects among it -- on the Tk thread only (launcher/tkgc.py, 1.1.9). Players'
launchers closed after a tab change or a match: Python's collector ran in whatever thread allocated (the lobby
client, a download, a picture reader) and freed closed windows' pictures, variables, fonts -- and a Tk interpreter
freed there aborts the process ("Tcl_AsyncDelete: async handler deleted by the wrong thread").

Real Tk, real main loops, each case in its own process (an abort must not take the test run with it):
  * tests/launcher_gc_stress.py: the real launcher under tab switches, lobby events from a local server, windows
    opened and closed, worker threads allocating. Old launcher: thousands of Tk objects freed in worker threads
    (the lobby client's among them). Now: none.
  * a closed Tk interpreter left to the collector while workers allocate: the old launcher's process aborts with
    Tcl_AsyncDelete; with tkgc it is freed on the Tk thread and the process lives.
"""
import gc
import json
import os
import subprocess
import sys
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LAUNCHER = os.path.join(ROOT, "launcher")
NOWIN = 0x08000000 if os.name == "nt" else 0        # CREATE_NO_WINDOW

try:
    import tkinter  # noqa: F401
except ImportError:      # pragma: no cover
    tkinter = None

INTERP = textwrap.dedent("""
    import gc, sys, threading, time, tkinter as tk
    sys.path.insert(0, sys.argv[1])
    use = sys.argv[2] == "tkgc"
    if use:
        import tkgc
    first = tk.Tk(); first.withdraw()
    if use:
        tkgc.install(first)                 # (what App.__init__ does)
    b = tk.Button(first); b.me = b          # a closed window whose objects point at each other
    first.destroy(); del first, b
    root = tk.Tk(); root.withdraw()
    if use:
        tkgc.install(root)
    stop = []
    def work():                             # a worker that allocates: the collector's counters overflow here
        while not stop:
            x = [[i] for i in range(300)]
            for a in x:
                a.append(a)
            time.sleep(0.001)
    threading.Thread(target=work, daemon=True).start()
    root.after(2500, lambda: (stop.append(1), root.destroy()))
    root.mainloop()
    print("alive", flush=True)
""")


@unittest.skipIf(tkinter is None, "no tkinter")
class TkGc(unittest.TestCase):
    def run_py(self, args, timeout):
        p = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=timeout,
                           creationflags=NOWIN, cwd=HERE)
        return p.returncode, p.stdout, p.stderr

    def test_a_closed_interpreter_is_freed_on_the_tk_thread(self):
        code, out, err = self.run_py(["-c", INTERP, LAUNCHER, "tkgc"], 60)
        self.assertEqual((code, out.strip()), (0, "alive"), err[-2000:])

    def test_without_tkgc_the_same_process_aborts(self):
        """The case above without tkgc: the worker frees the interpreter and Tcl aborts (the reason for tkgc; if
        this ever stops aborting, the case above proves nothing any more)."""
        code, out, err = self.run_py(["-c", INTERP, LAUNCHER, "plain"], 60)
        self.assertNotEqual(code, 0)
        self.assertIn("Tcl_AsyncDelete", err)

    def test_the_launcher_under_stress_frees_tk_objects_on_the_tk_thread_only(self):
        code, out, err = self.run_py([os.path.join(HERE, "launcher_gc_stress.py"), "--seconds", "20"], 240)
        lines = [x for x in out.splitlines() if x.startswith("{")]
        self.assertTrue(lines, f"the launcher died (exit {code}):\n{err[-3000:]}")
        res = json.loads(lines[-1])
        self.assertEqual(res["freed_off_tk_thread"], {})
        self.assertEqual((res["errors"], res["log_errors"]), ([], []))
        self.assertTrue(res["ok"], res)
        self.assertEqual(code, 0)
        self.assertGreater(res["freed"].get("picture", 0), 100)          # (the windows' pictures were freed)
        self.assertEqual(res["stats"]["logged in"], 1)
        self.assertEqual(res["stats"]["gc off while running"], 1)    # the launcher collects on its Tk thread ...
        self.assertTrue(res["gc_enabled"])                            # ... and gives it back when its window goes

    def test_collect_due_follows_the_thresholds(self):
        import gc
        sys.path.insert(0, LAUNCHER)
        try:
            import tkgc
        finally:
            sys.path.remove(LAUNCHER)
        was = gc.isenabled()
        gc.disable()
        try:
            gc.collect()
            self.assertIsNone(tkgc.collect_due())             # nothing due right after a full collection
            junk = [[] for _ in range(gc.get_threshold()[0] + 50)]
            self.assertEqual(tkgc.collect_due(), 0)            # the young generation
            del junk
        finally:
            if was:
                gc.enable()

@unittest.skipIf(tkinter is None, "no tkinter")
class Uninstall(unittest.TestCase):
    """CI 1.1.9: App.destroy gives the collection back to Python -- left off, every test after the first launcher
    window ran with no collector at all (the one-process CI run then failed in a different Tk test each time)."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "launcher"))
        import tkgc
        self.tkgc = tkgc
        self.addCleanup(gc.enable)

    def test_uninstall_turns_the_collector_back_on(self):
        root = tkinter.Tk()
        root.withdraw()
        self.tkgc.install(root)
        self.assertFalse(gc.isenabled())
        other = tkinter.Tk()
        other.withdraw()
        self.tkgc.uninstall(other)                  # not the root it runs on: nothing changes
        self.assertTrue(self.tkgc.installed_on(root))
        self.tkgc.uninstall(root)
        self.assertTrue(gc.isenabled())
        self.assertFalse(self.tkgc.installed_on(root))
        other.destroy()
        root.destroy()

    def test_the_launcher_window_uninstalls_on_destroy(self):
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            src = f.read()
        self.assertRegex(src, r"def destroy\(self\):\n\s+tkgc\.uninstall\(self\)")


if __name__ == "__main__":
    unittest.main()
