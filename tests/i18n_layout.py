"""Cut-off check for the launcher in every language, at 100 % and 150 % display scaling, with withdrawn windows.

    python tests/i18n_layout.py [es ko ...] [--scale 100|150]   # list what is cut off, compared with English

tests/test_i18n.py runs the same walk for every language. Nothing is put on the screen: Tk computes no geometry for
the children of a withdrawn window, so everything is judged from requested sizes and measured texts --

* a text wider than the widget that shows it: fixed-width labels and buttons, Treeview headings and cells,
  Combobox choices, canvas texts;
* the window: the natural width of the launcher's tabs (and of the Controls, report and update windows)
  against the window's width.

English is the yardstick: a language is checked for what is cut off where English is not (or clearly more
than English), so the few places that are already tight in English are not counted against a translation.
"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import time
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher", "tests"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("T5_PAD_NAV", "0")        # no controller thread in the Online tab

import tkinter as tk  # noqa: E402
import tkinter.font as tkfont  # noqa: E402
from tkinter import ttk  # noqa: E402

from t5lobby import i18n  # noqa: E402

LANGS = tuple(i18n.LANGUAGES)
SCALES = (100, 150)
SCREEN_H = 1080                      # the launcher's size is checked as on a 1920 x 1080 screen


# ---------------------------------------------------------------------------- the checker
def _font(w, suffix=""):
    try:
        f = w.cget("font")
    except tk.TclError:
        f = ""
    if not f:
        try:
            st = ttk.Style(w)
            style = (w.cget("style") or w.winfo_class()) + suffix
            f = st.lookup(style, "font") or st.lookup(w.winfo_class() + suffix, "font") or "TkDefaultFont"
        except tk.TclError:
            f = "TkDefaultFont"
    try:
        return tkfont.Font(root=w, font=f)
    except tk.TclError:
        return tkfont.nametofont("TkDefaultFont", root=w)


def _text(w):
    text = str(w.cget("text"))
    try:
        var = str(w.cget("textvariable"))
        if var:
            text = str(w.getvar(var))
    except tk.TclError:
        pass
    return text


def problems(root, slack=2):
    """[(kind, widget path, column, needed px, available px, text)] for texts wider than their widget."""
    out = []

    def walk(w):
        cls = w.winfo_class()
        managed = bool(w.winfo_manager())
        if managed and cls in ("TLabel", "Label", "TButton", "Button", "TCheckbutton", "Checkbutton",
                               "TRadiobutton", "Radiobutton"):
            try:
                text = _text(w)
                width = int(str(w.cget("width") or 0) or 0)
                wrap = str(w.cget("wraplength") or 0)
            except (tk.TclError, ValueError):
                text, width, wrap = "", 0, "0"
            if text and width > 0 and wrap in ("", "0"):     # a fixed width: the text must fit it
                need = max(_font(w).measure(line) for line in text.split("\n"))
                if need > w.winfo_reqwidth() + slack:
                    out.append(("fixed", str(w), "", need, w.winfo_reqwidth(), text))
        elif managed and cls == "Treeview":
            head, body = _font(w, ".Heading"), _font(w)
            show = str(w.cget("show"))
            for c in ("#0",) + tuple(w["columns"]):
                if c == "#0" and "tree" not in show:
                    continue
                width = int(w.column(c, "width"))
                h = str(w.heading(c)["text"])
                if h and head.measure(h) + 12 > width + slack:
                    out.append(("heading", str(w), c, head.measure(h) + 12, width, h))
                for iid in w.get_children():
                    v = str(w.item(iid, "text") if c == "#0" else w.set(iid, c))
                    need = body.measure(v) + 8 + (20 if c == "#0" else 0)
                    if v and need > width + slack:
                        out.append(("cell", str(w), c, need, width, v))
        elif managed and cls == "TCombobox":
            f = _font(w)
            values = [str(v) for v in w.cget("values")]
            if values:
                longest = max(values, key=f.measure)
                need = f.measure(longest) + 26
                if need > w.winfo_reqwidth() + slack:
                    out.append(("combo", str(w), "", need, w.winfo_reqwidth(), longest))
        elif managed and cls == "Canvas":
            try:
                cw, ch = int(float(w.cget("width"))), int(float(w.cget("height")))
            except (tk.TclError, ValueError):
                cw = ch = 0
            for item in w.find_all():
                if w.type(item) == "text" and w.itemcget(item, "text") and w.itemcget(item, "state") != "hidden":
                    bb = w.bbox(item)
                    if bb and cw and ch and (bb[0] < -slack or bb[2] > cw + slack):
                        out.append(("canvas", str(w), str(item), bb[2] - bb[0], cw, w.itemcget(item, "text")))
        for c in w.winfo_children():
            if c.winfo_class() != "Toplevel":
                walk(c)
    walk(root)
    return out


# ---------------------------------------------------------------------------- the launcher, state by state
def load_launcher():
    loader = importlib.machinery.SourceFileLoader("t5dr_launcher_layout", os.path.join(ROOT, "launcher",
                                                                                      "t5dr_launcher.pyw"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def cancel_timers(root):
    try:
        for after_id in root.tk.splitlist(root.tk.call("after", "info")):
            try:
                root.tk.call("after", "cancel", after_id)
            except tk.TclError:
                pass
    except tk.TclError:
        pass


def all_texts(root):
    """Every text a widget shows: labels, buttons, headings, rows, tab names, combobox choices."""
    out = []

    def walk(w):
        try:
            v = w.cget("text")
            if v:
                out.append(str(v))
        except tk.TclError:
            pass
        try:
            var = w.cget("textvariable")
            if var:
                out.append(str(w.getvar(str(var))))
        except tk.TclError:
            pass
        cls = w.winfo_class()
        if cls == "Treeview":
            for c in ("#0",) + tuple(w["columns"]):
                out.append(str(w.heading(c)["text"]))
            for iid in w.get_children():
                out.append(str(w.item(iid, "text")))
                out.extend(str(v) for v in w.item(iid, "values"))
        elif cls == "TNotebook":
            out.extend(str(w.tab(i, "text")) for i in range(len(w.tabs())))
        elif cls == "TCombobox":
            out.extend(str(v) for v in w.cget("values"))
        for c in w.winfo_children():
            walk(c)
    walk(root)
    return [x.strip() for x in out if x and x.strip()]


class Client:
    """Enough of a lobby client for the Online tab to show every card, the leaderboard and a profile."""
    connected = True
    tls = False
    server_rtt = 20.0
    session = None

    class build:
        build_id = "b1"

    def __init__(self):
        self.me = {"id": "p1", "name": "Me", "guest": False, "rating": 1500, "record": [3, 2, 0], "status": "idle",
                   "main": "jin", "tier": 31, "rank": "Lord of War", "provisional": False}
        self.events = __import__("queue").Queue()

    friend_list = {
        "max": 100,
        "friends": [
            {"name": "Rival_Long_Name", "status": "online", "activity": "queue", "rank": "Lord of War", "tier": 31},
            {"name": "Bob", "status": "in_match", "rank": "2nd Dan", "tier": 11, "invite": "update"},
            {"name": "Old", "status": "online", "activity": "idle", "invite": "version", "rank": "1st Dan", "tier": 10},
            {"name": "Zed", "status": "offline", "last_seen": 1792350300, "rank": "Beginner", "tier": 0}],
        "incoming": [{"name": "NewFriend_123"}],
        "outgoing": [{"name": "Somebody_Else"}]}

    def active_notices(self):
        return []

    def has_friends(self):
        return True

    def close(self):
        pass

    def leaderboard(self, n):
        return [{"place": i + 1, "name": nm, "online": i % 2 == 0, "rank": rk, "provisional": i == 2,
                 "rating": 1500 + 37 * i, "wins": 12 + i, "losses": 7, "main": "jin", "tier": tier}
                for i, (nm, rk, tier) in enumerate((("Rival_Long_Name", "Lord of War", 31), ("Bob", "2nd Dan", 11),
                                                    ("Ccc", "Beginner", 0)))]

    def profile(self, name, n):
        return {"name": "Me", "account": True, "rank": "Lord of War", "tier": 31, "rating": 1612, "rd": 61,
                "provisional": False, "place": 3, "record": [30, 12, 1], "ranked_games": 43,
                "peak_rank": "Lord of War", "chars": [{"char": "jin", "wins": 20, "games": 30}],
                "voids_24h": 1, "self": True, "recovery_codes_left": 7,
                "history": [{"time": 1792350300, "result": r, "opponent": "Rival_Long_Name", "you_char": "devil_jin",
                             "opp_char": "lee", "score": [2, 1], "delta": 12.0, "ranked": True, "status": st,
                             "reason": rs, "set": None}
                            for r, st, rs in (("won", "confirmed", None), ("lost", "forfeit", "quit"),
                                              ("draw", "void", "desync"), ("lost", "disputed", "disputed"))]}


PLAYERS = [
    {"id": "p1", "name": "Me", "guest": False, "rating": 1500, "record": [3, 2, 0], "status": "idle", "build": "b1",
     "rtt": 10.0, "rank": "Lord of War", "tier": 31, "provisional": False, "main": "devil_jin"},
    {"id": "p2", "name": "Rival_Long_Name", "guest": True, "record": [10, 11, 0], "status": "playing", "build": "b1",
     "rtt": None},
    {"id": "p3", "name": "Bob", "guest": False, "rating": 1612, "record": [30, 12, 1], "status": "match",
     "build": "b1", "rtt": 140.0, "rank": "2nd Dan", "tier": 11, "provisional": True, "main": "lee"},
    {"id": "p4", "name": "Q", "guest": False, "rating": 1612, "record": [0, 0, 0], "status": "queue", "build": "b1",
     "rtt": 40.0, "rank": "Beginner", "tier": 0, "provisional": True, "main": "random"},
    {"id": "p5", "name": "Old", "guest": True, "record": [1, 0, 0], "status": "playing", "build": "other", "rtt": 80.0}]
ROOMS = [{"id": "r1", "name": "Room of Rival", "owner": {"name": "Rival_Long_Name"}, "status": "open", "build": "b1",
          "ranked": True},
         {"id": "r2", "name": "R2", "owner": {"name": "Bob"}, "status": "full", "build": "b1", "ranked": False}]
RIVAL = {"name": "Rival_Long_Name", "guest": False, "rating": 1520, "rank": "Lord of War", "provisional": False,
         "tier": 31}


class Walk:
    """The launcher built (withdrawn) in one language at one display scale, taken through its screens. For each
    screen: what is cut off (problems), the natural width against the window's, texts the catalog lacks and
    English texts left on screen."""

    def __init__(self, lang, scale):
        self.lang, self.scale = lang, scale
        self.cut = {}            # (screen, kind, widget, column) -> (needed, available, text)
        self.english = {}        # screen -> [English texts on screen]
        self.screens = []
        self.missing = []
        self.shown = []          # windows that were on screen (must stay empty)

    def run(self):
        d = tempfile.mkdtemp(prefix="t5i18n-")
        env = mock.patch.dict(os.environ, {"T5_ONLINE_DIR": os.path.join(d, "user"), "T5_PAD_NAV": "0"})
        env.start()
        mod = load_launcher()
        import core
        log = mock.patch.object(core, "LAUNCHER_LOG", os.path.join(d, "launcher.log"))
        log.start()
        st = core.Settings(os.path.join(d, "launcher.json"))
        st["language"], st["out"] = self.lang, os.path.join(d, "native")
        style = mod.App._style

        def scaled_style(app):           # the display scaling, before the theme measures anything
            app.tk.call("tk", "scaling", 96.0 / 72.0 * self.scale / 100.0)
            style(app)
        patches = [mock.patch.object(mod.App, "_style", scaled_style)] + [
            mock.patch.object(mod.App, n, lambda app: None)
            for n in ("refresh_prereqs", "refresh_inputs", "refresh_game_state")]
        for p in patches:
            p.start()
        app = None
        try:
            app = mod.App(offscreen=False, settings=st)
            app.withdraw()
            cancel_timers(app)
            self.app, self.px = app, app.theme.apply(app).px if app.theme else int
            app.geometry(f"{self.px(1080)}x{min(self.px(840), SCREEN_H - 80)}")
            i18n.clear_missing()
            self._launcher()
            self._online()
            self._windows(d)
            self.missing = i18n.missing()
        finally:
            for p in reversed(patches):
                p.stop()
            if app is not None:
                self._close(app)
            log.stop()
            env.stop()
            i18n.set_language("en")
        return self

    def _close(self, app):
        try:
            self.shown += [str(w) for w in [app] + list(app.winfo_children())
                           if w.winfo_class() in ("Tk", "Toplevel") and w.winfo_ismapped()]
            cancel_timers(app)
            app.online.client = None
            app.online.on_close()
            app.destroy()
        except tk.TclError:
            pass

    def screen(self, name, top=None):
        app = self.app
        app.update()
        view = getattr(getattr(app, "online", None), "view", None)
        for lab, _cont, _margin in getattr(view, "_wraps", ()):
            try:                     # (on screen they follow their card's width; withdrawn, the card has none)
                lab.configure(wraplength=view.px(300))
            except tk.TclError:
                pass
        top = top or app
        top.update_idletasks()
        self.screens.append(name)
        for kind, w, col, need, have, text in problems(top):
            self.cut[(name, kind, w, col)] = (need, have, text)
        if top is app:
            self.cut[(name, "width", "", "")] = (app.nb.winfo_reqwidth(), app.winfo_width() - 24, "")
        cat = i18n.catalog(self.lang)
        self.english[name] = sorted({x for x in all_texts(top) if x in cat and cat[x] != x})

    def _launcher(self):
        app = self.app
        for key in app.tab_keys:
            app.nb.select(app.tabs[key])
            self.screen("tab " + key)
        app._show_prereqs([
            {"id": "python", "name": "Python 3.10+", "ok": True, "detail": "3.12.10 at C:\\Py\\python.exe",
             "needed_for": "", "install": None},
            {"id": "msvc", "name": "C++ build tools (MSVC x64)", "ok": False, "detail": "not found",
             "needed_for": "", "install": "Microsoft.VisualStudio.2022.BuildTools"}])
        app.nb.select(app.tabs["build"])
        self.screen("build tools")

    def _online(self):
        app = self.app
        app.nb.select(app.tabs["online"])
        tab = app.online
        self.screen("online login")
        tab.client = Client()
        tab.call = lambda fn, *a, then=None, fail=None: then(fn(*a)) if then else fn(*a)
        tab._set_account_view(True)
        tab.on_event({"t": "lobby_state", "players": PLAYERS, "rooms": ROOMS, "queue": {"ranked": 3, "quick": 1}})
        self.screen("online lobby")
        tab.client.me["status"] = "queue"
        tab.cfg["last_search"] = "ranked"
        tab.strict_var.set(1)
        tab.view.refresh()
        self.screen("online searching")
        tab.client.me["status"] = "idle"
        tab.on_event({"t": "match_found", "match": "m1", "ranked": True, "blind": True, "opponent": None,
                      "ping": {"known": True, "ms": 42.0}, "ready_timeout": 15, "ready_check": True})
        self.screen("online found")
        tab.on_event({"t": "match_reveal", "opponent": RIVAL})
        self.screen("online ready")
        tab.on_event({"t": "challenged", "challenge": "c1", "from": RIVAL})
        self.screen("online challenged")
        tab.hide_bar()
        tab.on_event({"t": "match_start", "ranked": True, "opponent": RIVAL, "rtt_ms": 41.6, "path": "relay",
                      "delay": 2, "fight": {"p1": "devil_jin", "p2": "random"}})
        tab.driver = type("D", (), {"ticket": object(), "game_running": lambda self: True, "session_ticket": None,
                                    "close": lambda self: None, "poll": lambda self: []})()
        tab.view.refresh()
        self.screen("online in match")
        tab.driver = None
        tab.on_event({"t": "match_result", "status": "confirmed", "winner": None, "score": [2, 1], "ranked": True,
                      "rating": {"after": {"r": 1612.3}, "delta": 12.0, "event": "promoted",
                                 "rank_after": {"rank": "Lord of War", "tier": 31}}})
        tab.on_event({"t": "lag_check", "ping_ms": 37.4, "expected_frames": 2, "observed_frames": 4.2,
                      "verdict": "more_lag", "cause": "network", "can_leave": True, "text": "x"})
        tab.view.refresh()
        self.screen("online result")
        tab.rematch_bar = (i18n.t("Result confirmed"), "Rival_Long_Name")
        tab._show_rematch_bar()
        self.screen("online rematch buttons")
        tab.on_driver({"kind": "ask_result", "opponent": "Rival_Long_Name"})
        self.screen("online how did it end")
        tab.hide_bar()
        tab.nb.select(1)
        tab.load_leaderboard()
        self.screen("online leaderboard")
        tab.show_profile("Me")
        self.screen("online profile")
        tab.nb.select(tab.friends_page)
        tab.on_event({"t": "friends"})
        self.screen("online friends")
        tab.on_event({"t": "invited", "invite": "i1", "kind": "room", "from": RIVAL, "room": {"name": "Room of Rival"}})
        self.screen("online friend's invite")
        tab.hide_bar()

    def _windows(self, d):
        """The Controls window (fake controllers), the problem report and the update offer: windows of their own,
        never shown."""
        app = self.app
        import test_controls_ui as tc
        dlg = tc.cu.ControlsDialog(app, tc.FakeSettings(d), sources=[tc.FakePad()], foreground=lambda: True,
                                   clock=tc.Clock(), thread=False, ask=lambda *a: True, game_running=lambda: False)
        dlg.top.withdraw()
        self.screen("controls window", dlg.top)
        self.cut[("controls window", "width", "", "")] = (dlg.top.winfo_reqwidth(), self.px(1040), "")
        dlg.editor.saved_text = dlg.editor.doc.render()
        dlg.close()
        from test_problem_report import fake_context
        import problem_report_ui as report_ui
        ctx = fake_context(d, build_exit=0)
        rd = report_ui.ReportDialog(app, lambda: ctx, os.path.join(d, "Desktop"), reveal=lambda p: None,
                                    issues_url="https://example.org/issues", log=lambda m: None, visible=False)
        self.screen("report window", rd.top)
        rd.close()
        import updater
        up = updater.Updater(app)
        cancel_timers(app)
        up.release = {"version": "9.9.9", "zip": {"size": 92_300_000}, "page": "https://github.com/x/y",
                      "notes": "- something", "published": "2026-10-20", "code_id": None}
        with mock.patch.object(updater, "busy_reason", return_value="The game is running. Close it first, then update."):
            up.offer()
        up.win.withdraw()
        self.screen("update window", up.win)
        up.win.destroy()


def compare(walk, english):
    """What `walk` has cut off that the English walk at the same scale has not (or clearly less)."""
    out = []
    for key, (need, have, text) in sorted(walk.cut.items()):
        screen, kind, w, col = key
        base = english.cut.get(key)
        if kind == "width":
            if need > max(have, base[0] if base else 0) + 4:
                out.append(f"{screen}: {need} px wide, the window has {have} (English {base[0] if base else '?'})")
        elif base is None or need > base[0] + 6:
            out.append(f"{screen}: {kind} {need} > {have} px {w[-40:]} {col} {text[:60]!r}")
    return sorted(set(out))


def main(argv):
    langs = [a for a in argv if a in LANGS] or [x for x in LANGS if x != "en"]
    scales = [int(argv[argv.index("--scale") + 1])] if "--scale" in argv else SCALES
    bad = 0
    for scale in scales:
        english = Walk("en", scale).run()
        for lang in langs:
            t0 = time.time()
            w = Walk(lang, scale).run()
            lines = compare(w, english) + [f"missing text: {m!r}" for m in w.missing] + [
                f"{s}: English left: {e}" for s, e in w.english.items() if e] + [f"on screen: {s}" for s in w.shown]
            print(f"{lang} {scale} %: {len(lines)} problems ({time.time() - t0:.1f} s)")
            for x in lines:
                print("   ", x)
            bad += len(lines)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
