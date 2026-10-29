"""Stress of the real launcher (t5dr_launcher.App, real Tk main loop): many tab switches, lobby events from a local
lobby server, windows full of Tk objects opened and closed, worker threads allocating -- the cyclic garbage
collector then runs in those threads unless the launcher keeps it on the Tk thread (launcher/tkgc.py, 1.1.9:
players' launchers closed after a tab change or a match).

    python tests/launcher_gc_stress.py [--root DIR] [--seconds N] [--previous-window]

--root: the folder with launcher/ and lobby/t5lobby (default: this tree; give a release folder to test what players
get, with its bundled python/python.exe). --previous-window: an earlier launcher window of this process was closed
and left to the collector first (what the 1.1.7 release check's walk did: its interpreter was then freed by a
worker thread and Tcl aborted the process, "Tcl_AsyncDelete: async handler deleted by the wrong thread").

Prints one JSON line {"ok": ..., ...} at the end; exit code 0 = the launcher lived through it with every Tk object
freed on the Tk thread, 1 = it did not. A Tcl abort ends the process with no line at all (the test reads that).
Nothing is shown: the windows are withdrawn and fully transparent; the lobby server binds 127.0.0.1.
"""
import argparse
import asyncio
import collections
import importlib.machinery
import importlib.util
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import traceback

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ap.add_argument("--seconds", type=float, default=40.0)
ap.add_argument("--previous-window", action="store_true")
A = ap.parse_args()
ROOT = os.path.abspath(A.root)
sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(1, os.path.join(ROOT, "lobby"))
os.environ.update(T5_PAD_NAV="0", T5_NOTIFY="0", T5_FW_CHECK="0", T5_PORTMAP="0", T5DR_NO_UPDATE_CHECK="1",
                  T5_LANG="en", T5_NET_BIND="127.0.0.1", T5_DISCORD="0")
WORK = tempfile.mkdtemp(prefix="t5gcstress-")
os.environ["T5_ONLINE_DIR"] = os.path.join(WORK, "online")

import tkinter as tk  # noqa: E402
import tkinter.font as tkfont  # noqa: E402

MAIN = threading.main_thread()
OFF = collections.Counter()           # Tk objects freed on another thread: (kind, thread name) -> count
FREED = collections.Counter()


def _watch(cls, kind):
    orig = cls.__del__

    def __del__(self, _orig=orig, _kind=kind):
        FREED[_kind] += 1
        if threading.current_thread() is not MAIN:
            OFF[f"{_kind} in {threading.current_thread().name}"] += 1
        _orig(self)
    cls.__del__ = __del__


_watch(tk.Image, "picture")
_watch(tk.Variable, "variable")
_watch(tkfont.Font, "font")

from t5lobby import dialogs, proto  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.server import Config, LobbyServer  # noqa: E402

BUILD = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "0123456789abcdef", "test")
for n in ("ask_yes_no", "ask_yes_no_cancel", "show_info", "show_error", "ask_string"):
    setattr(dialogs, n, lambda *a, **k: False)


class Server:
    def __init__(self):
        self.cfg = Config(host="127.0.0.1", port=0, udp_port=0, udp_port2=-1, db=":memory:", scrypt_n=1 << 10,
                          log_level="ERROR", status_port=0, pair_cooldown=0.0, ranked_same_ip=True)
        self.loop = proto.new_event_loop()
        self.ready = threading.Event()
        threading.Thread(target=self._run, name="lobby-server", daemon=True).start()
        if not self.ready.wait(15):
            raise RuntimeError("the lobby server did not start")

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.srv = LobbyServer(self.cfg)
        self.loop.run_until_complete(self.srv.start())
        self.ready.set()
        self.loop.run_forever()

    @property
    def addr(self):
        return f"127.0.0.1:{self.srv.port}"


def load_launcher():
    path = os.path.join(ROOT, "launcher", "t5dr_launcher.pyw")
    spec = importlib.util.spec_from_loader("t5dr_launcher_stress", importlib.machinery.SourceFileLoader(
        "t5dr_launcher_stress", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = load_launcher()
real_settings = L.core.Settings
L.core.Settings = lambda: real_settings(os.path.join(WORK, "launcher.json"))
L.core.LAUNCHER_LOG = os.path.join(WORK, "launcher.log")
L.App.refresh_prereqs = lambda app: None            # (no build tools, no Downloads folder of this PC)
L.App.refresh_inputs = lambda app: None
L.App.refresh_game_state = lambda app: app._show_game_state({"ok": True, "text": "Ready (test)."})


def hide(app):
    app.withdraw()
    try:
        app.attributes("-alpha", 0.0)
    except tk.TclError:
        pass


def new_app():
    app = L.App(offscreen=False)
    hide(app)
    app.online._build_info = lambda: (BUILD, None)
    app.online.new_window = lambda parent: _hidden(parent)
    app.online.bring_forward = lambda w: None
    return app


def _hidden(parent):
    w = tk.Toplevel(parent)
    w.withdraw()
    return w


if A.previous_window:
    # an earlier window of this process, closed: its widgets point at each other, so only the collector frees them
    # (closed the way the release check's walk closed its windows, tests/i18n_layout.py _close: pending timers
    # cancelled -- a pending one would keep the window alive through Tcl)
    first = new_app()
    first.update()
    for after_id in first.tk.splitlist(first.tk.call("after", "info")):
        try:
            first.tk.call("after", "cancel", after_id)
        except tk.TclError:
            pass
    first.online.client = None
    first.online.on_close()
    first.destroy()
    del first

srv = Server()
app = new_app()
tab = app.online
tab.server_var.set(srv.addr)
tab.name_var.set("Stress")
stop = threading.Event()
stats = collections.Counter()
errors = []


def bots():
    """Lobby events: players come and go, change fighters, open and leave rooms."""
    cs = []
    try:
        for i in range(5):
            c = LobbyClient(srv.addr, BUILD, relay_bridge=False)
            c.connect()
            c.login_guest(f"Bot{i}")
            cs.append(c)
        chars = ["jin", "kazuya", "nina", "law", "king", "paul"]
        while not stop.is_set():
            c = random.choice(cs)
            r = random.random()
            try:
                if r < 0.4:
                    c.set_char(random.choice(chars))
                elif r < 0.7:
                    c.create_room(f"room {random.randint(1, 99)}")
                else:
                    c.leave_room()
                stats["lobby events"] += 1
            except Exception:      # noqa: BLE001 -- (a refused request is an event too)
                stats["refused"] += 1
            while c.next_event(0) is not None:
                pass
            time.sleep(0.03)
    except Exception:      # noqa: BLE001
        errors.append("bots: " + traceback.format_exc())
    finally:
        for c in cs:
            try:
                c.close()
            except Exception:      # noqa: BLE001
                pass


def allocator(n):
    """A worker thread that allocates (the lobby client parsing messages, a download, a picture reader): the
    automatic collector runs in whichever thread allocates when its counters overflow."""
    while not stop.is_set():
        x = [[i] for i in range(400)]
        for a in x:
            a.append(a)                # cyclic garbage of its own
        del x
        stats[f"alloc{n}"] += 1
        time.sleep(0.001)


KEYS = [k for k in ("build", "play", "settings", "online", "replays") if k in app.tabs]
PAGES = ("lobby_page", "board_page", "stats_page", "prof_page", "friends_page", "tours_page")


def flip():
    if stop.is_set():
        return
    try:
        app.nb.select(app.tabs[random.choice(KEYS)])
        if getattr(tab, "nb", None) is not None and random.random() < 0.6:
            app.nb.select(app.tabs["online"])
            tab.nb.select(getattr(tab, random.choice(PAGES)))
        stats["tab switches"] += 1
    except Exception:      # noqa: BLE001
        errors.append("flip: " + traceback.format_exc())
    app.after(12, flip)


def churn():
    """What a match leaves behind: windows with pictures, variables and fonts, closed again (the result card, the
    match-found bar, a profile window). Left to the collector: the widgets point at each other."""
    if stop.is_set():
        return
    try:
        from t5lobby import theme
        for _ in range(4):
            w = tab.new_window(app)
            holder = type("Card", (), {})()
            holder.me = holder
            holder.win = w
            holder.pics = [tk.PhotoImage(master=w, width=8, height=8) for _ in range(3)]
            holder.vars = [tk.StringVar(w, value="x"), tk.IntVar(w, 1), tk.BooleanVar(w, True)]
            holder.font = tkfont.Font(root=w, family="Segoe UI", size=9)
            holder.badge = theme.Badge(w, size=22)
            holder.portrait = theme.Portrait(w)
            w.destroy()
            stats["windows"] += 1
    except Exception:      # noqa: BLE001
        errors.append("churn: " + traceback.format_exc())
    app.after(40, churn)


def start():
    app.nb.select(app.tabs["online"])
    tab.do_login("guest")
    threading.Thread(target=bots, name="bots", daemon=True).start()
    for n in range(3):
        threading.Thread(target=allocator, args=(n,), name=f"worker{n}", daemon=True).start()
    app.after(300, flip)
    app.after(300, churn)


def end():
    stop.set()
    stats["players listed"] = len(tab.tv_players.get_children()) if hasattr(tab, "tv_players") else -1
    stats["logged in"] = int(bool(tab.client is not None and tab.client.me))
    stats["gc off while running"] = int(not __import__("gc").isenabled())   # tkgc: collected on the Tk thread
    app.after(600, app.on_close)


app.after(300, start)
app.after(int(A.seconds * 1000), end)
t0 = time.time()
L.run_mainloop(app)
alive = time.time() - t0
import gc  # noqa: E402
gc.collect()                         # (the last windows: freed here, on the Tk thread)
try:
    with open(L.core.LAUNCHER_LOG, encoding="utf-8") as f:
        log_errors = [x for x in f.read().split("\n") if x.startswith("error in the launcher")]
except OSError:
    log_errors = []
ok = not OFF and not errors and not log_errors and stats["tab switches"] > 50 and stats["windows"] > 20
print(json.dumps({"ok": ok, "seconds": round(alive, 1), "freed_off_tk_thread": dict(OFF), "freed": dict(FREED),
                  "stats": dict(stats), "errors": errors[:3], "log_errors": log_errors[:3],
                  "gc_enabled": gc.isenabled(), "python": sys.version.split()[0]}), flush=True)
shutil.rmtree(WORK, True)
os._exit(0 if ok else 1)           # (daemon threads: no waiting for them)
