"""Click-through of the 1.1.9 challenges with three real launcher processes (t5dr_launcher.App, real Tk main loop each)
against a local lobby server: several open challenges, Cancel, the first accept wins and withdraws the rest, the
challenger's input delay on both sides, the chat lines, the player list's sort (kept in online.json) and its
"Unavailable" line, the leaderboard's ranked / casual columns (a 1.1.9 server's fields, and the fallback for an older
server's rows).

    python tests/launcher_challenges_click.py [--root DIR]

--root: the folder with launcher/ and lobby/t5lobby (default: this tree; a release folder to test what players get --
run the script with that folder's python/python.exe). The players' windows are mapped (so the clicks have real
geometry: Treeview headings, rows, buttons get Enter / ButtonPress / ButtonRelease events at their own coordinates) but
sit far off the screen and are fully transparent; the lobby server binds 127.0.0.1; no game starts (the player's
start_game does nothing). Prints one line per check and a JSON line at the end; exit code 0 = every check passed.
"""
import argparse
import asyncio
import importlib.machinery
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--root", default=os.path.dirname(HERE))
ap.add_argument("--player")
ap.add_argument("--server")
ap.add_argument("--work")
A = ap.parse_args()
ROOT = os.path.abspath(A.root)


# ================================================================================================ a player (a launcher)
def player_main():
    sys.path.insert(0, os.path.join(ROOT, "launcher"))
    sys.path.insert(1, os.path.join(ROOT, "lobby"))
    os.environ.update(T5_PAD_NAV="0", T5_NOTIFY="0", T5_FW_CHECK="0", T5_PORTMAP="0", T5DR_NO_UPDATE_CHECK="1",
                      T5_LANG="en", T5_NET_BIND="127.0.0.1", T5_DISCORD="0")
    work = A.work
    os.environ["T5_ONLINE_DIR"] = os.path.join(work, "online")
    import tkinter as tk
    from t5lobby import dialogs
    from t5lobby.buildid import BuildInfo
    build = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "0123456789abcdef", "test")
    for n in ("ask_yes_no", "ask_yes_no_cancel", "show_info", "show_error", "ask_string"):
        setattr(dialogs, n, lambda *a, **k: False)
    spec = importlib.util.spec_from_loader("t5dr_launcher_click", importlib.machinery.SourceFileLoader(
        "t5dr_launcher_click", os.path.join(ROOT, "launcher", "t5dr_launcher.pyw")))
    L = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(L)
    real_settings = L.core.Settings
    L.core.Settings = lambda: real_settings(os.path.join(work, "launcher.json"))
    L.core.LAUNCHER_LOG = os.path.join(work, "launcher.log")
    L.App.refresh_prereqs = lambda app: None
    L.App.refresh_inputs = lambda app: None
    L.App.refresh_game_state = lambda app: app._show_game_state({"ok": True, "text": "Ready (test)."})
    app = L.App(offscreen=False)
    app.geometry("1100x900+-4000+50")                # (mapped, but far off every screen)
    try:
        app.attributes("-alpha", 0.0)
    except tk.TclError:
        pass
    tab = app.online
    tab._build_info = lambda: (build, None)
    tab.new_window = lambda parent: _hidden(parent)
    tab.bring_forward = lambda w: None
    app.start_game = lambda env=None: None           # (no game: only the lobby side is looked at)
    events = []
    orig_on_event = tab.on_event

    def on_event(ev, *a, **kw):
        events.append(dict(ev))
        return orig_on_event(ev, *a, **kw)
    tab.on_event = on_event
    tab.client_events = events

    def _hidden(parent):
        w = tk.Toplevel(parent)
        w.withdraw()
        return w

    def click(w, x=None, y=None, button=1):
        w.update_idletasks()
        x = w.winfo_width() // 2 if x is None else x
        y = w.winfo_height() // 2 if y is None else y
        w.event_generate("<Enter>", x=x, y=y)
        w.event_generate("<Motion>", x=x, y=y)
        w.event_generate(f"<ButtonPress-{button}>", x=x, y=y)
        w.event_generate(f"<ButtonRelease-{button}>", x=x, y=y)

    def click_row(tv, iid):
        tv.see(iid)
        tv.update_idletasks()
        x, y, w, h = tv.bbox(iid)
        click(tv, x + 40, y + h // 2)

    def heading_x(tv, col):
        x = 0
        cols = list(tv["displaycolumns"])
        if cols == ["#all"]:
            cols = list(tv["columns"])
        if str(tv.cget("show")).find("tree") >= 0:
            x += int(tv.column("#0", "width"))
        for c in cols:
            w = int(tv.column(c, "width"))
            if c == col:
                return x + w // 2
            x += w
        raise KeyError(col)

    def click_heading(tv, col):
        tv.update_idletasks()
        click(tv, heading_x(tv, col), 8)

    def chat():
        return tab.chat_log.get("1.0", "end")

    def rows(tv):
        return [(i, [str(v) for v in tv.item(i, "values")]) for i in tv.get_children()]

    def open_rows():
        out = []
        if tab.chal.rows is not None:
            for w in tab.chal.rows.winfo_children():
                if w.winfo_class() == "TLabel":
                    out.append(str(w.cget("text")))
        return out

    def cancel_buttons():
        return [w for w in tab.chal.rows.winfo_children() if w.winfo_class() == "TButton"]

    def bar_text():
        try:
            return str(tab.bar_msg.cget("text")) if hasattr(tab, "bar_msg") else ""
        except tk.TclError:
            return ""

    ns = dict(app=app, tab=tab, tk=tk, click=click, click_row=click_row, click_heading=click_heading, chat=chat,
              rows=rows, open_rows=open_rows, cancel_buttons=cancel_buttons, events=events, L=L, time=time,
              json=json, bar=lambda: tab_bar(tab), bar_button=lambda label: bar_button(tab, label))
    cmds = queue.Queue()

    def reader():
        for line in sys.stdin:
            line = line.strip()
            if line:
                cmds.put(json.loads(line))
        cmds.put({"id": -1, "code": "app.on_close()"})
    threading.Thread(target=reader, daemon=True).start()

    def pump():
        try:
            while True:
                c = cmds.get_nowait()
                try:
                    try:
                        val = eval(c["code"], ns)
                    except SyntaxError:
                        exec(c["code"], ns)
                        val = None
                    res = {"id": c["id"], "ok": True, "value": json.loads(json.dumps(val, default=repr))}
                except Exception:      # noqa: BLE001
                    res = {"id": c["id"], "ok": False, "value": traceback.format_exc()}
                print("@@" + json.dumps(res), flush=True)
        except queue.Empty:
            pass
        app.after(25, pump)
    app.after(25, pump)
    print("@@" + json.dumps({"id": 0, "ok": True, "value": "ready"}), flush=True)
    L.run_mainloop(app)
    os._exit(0)


def tab_bar(tab):
    """The card / bar under the tab's buttons (a challenge, a match found ...): its text and its button labels."""
    spec = list(getattr(tab, "bar_spec", None) or [])
    if not spec:
        return {"text": "", "buttons": []}
    return {"text": tab.bar_text.get(), "buttons": [str(b.cget("text")) for b, _label, _pad in spec]}


def bar_button(tab, label):
    return next(b for b, _l, _p in tab.bar_spec if str(b.cget("text")) == label)


if A.player:
    player_main()
    sys.exit(0)

# ================================================================================================ the orchestrator
sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(1, os.path.join(ROOT, "lobby"))
from t5lobby import proto  # noqa: E402
from t5lobby.server import Config, LobbyServer  # noqa: E402

WORK = tempfile.mkdtemp(prefix="t5click-")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"   [{detail}]"), flush=True)
    return ok


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


class Player:
    def __init__(self, name, server, again=False):
        self.name = name
        self.dir = os.path.join(WORK, name)           # (again: the same folders, a launcher that starts anew)
        if not again:
            os.makedirs(self.dir)
        self.proc = subprocess.Popen(
            [sys.executable, "-u", os.path.abspath(__file__), "--root", ROOT, "--player", name, "--server", server,
             "--work", self.dir], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(
                 os.path.join(self.dir, "stderr.txt"), "w"), text=True, encoding="utf-8")
        self.out = queue.Queue()
        self.n = 0
        threading.Thread(target=self._read, daemon=True).start()
        self.wait_reply(0, 60)

    def _read(self):
        for line in self.proc.stdout:
            if line.startswith("@@"):
                self.out.put(json.loads(line[2:]))

    def wait_reply(self, n, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            try:
                r = self.out.get(timeout=0.2)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"{self.name}'s launcher died (exit {self.proc.returncode})")
                continue
            if r["id"] == n:
                return r
        raise TimeoutError(f"{self.name}: no answer")

    def run(self, code, timeout=30):
        self.n += 1
        self.proc.stdin.write(json.dumps({"id": self.n, "code": code}) + "\n")
        self.proc.stdin.flush()
        r = self.wait_reply(self.n, timeout)
        if not r["ok"]:
            raise RuntimeError(f"{self.name}: {code}\n{r['value']}")
        return r["value"]

    def until(self, code, timeout=15, what=""):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            last = self.run(code)
            if last:
                return last
            time.sleep(0.15)
        raise TimeoutError(f"{self.name}: {what or code} (last {last!r})")

    def close(self):
        try:
            self.proc.stdin.write(json.dumps({"id": 999, "code": "app.on_close()"}) + "\n")
            self.proc.stdin.flush()
            self.proc.wait(10)
        except Exception:      # noqa: BLE001
            self.proc.kill()


def select_player(p, name):
    """Click the named player's row in the player list; the list's own selection must follow."""
    p.run(f"click_row(tab.tv_players, next(i for i, v in rows(tab.tv_players) if v[0].startswith({name!r})))")
    return p.run("[tab.tv_players.item(i, 'values')[0] for i in tab.tv_players.selection()]")


def scenario():
    srv = Server()
    names = ("Alice", "Bob", "Cleo", "Dan")
    pl = {n: Player(n, srv.addr) for n in names}
    A_, B_, C_, D_ = (pl[n] for n in names)
    try:
        for p in pl.values():
            p.run(f"tab.server_var.set({srv.addr!r}); tab.name_var.set({p.name!r}); "
                  f"app.nb.select(app.tabs['online'])")
            p.run("tab.do_login('guest')")
        for p in pl.values():
            p.until("bool(tab.client and tab.client.me) and len(tab.tv_players.get_children()) >= 4", 30,
                    "logged in, 4 players listed")
        check("four launchers are in the lobby, all see four players", True)
        feat = A_.run("tab.client.multi_challenge_ok()")
        check("the local server announces challenges2", feat is True, feat)
        check("the delay box is shown on a 1.1.9 server", A_.run("bool(tab.chal.delay_cb.winfo_manager())"))

        # ---- Alice challenges Bob (delay 2) and Cleo (auto)
        sel = select_player(A_, "Bob")
        check("a click on Bob's row selects Bob", sel and sel[0].startswith("Bob"), sel)
        labels = A_.run("list(tab.chal.delay_cb.cget('values'))")
        check("the delay box offers auto / 0 / 1 / 2", len(labels) == 4 and labels[0].startswith("Delay: auto"),
              labels)
        A_.run("tab.chal.delay_var.set(tab.chal.delay_cb.cget('values')[3]); "
               "tab.chal.delay_cb.event_generate('<<ComboboxSelected>>')")
        check("choosing 'Delay: 2' is remembered in online.json",
              A_.run("tab.cfg.get('challenge_delay')") == "2", A_.run("tab.cfg.get('challenge_delay')"))
        A_.run("click(tab.actions['challenge'])")
        A_.until("len(open_rows()) == 1", 15, "Bob's challenge listed")
        check("Alice's open challenges list Bob with 'input delay 2'",
              A_.run("open_rows()")[0].startswith("Bob") and "2" in A_.run("open_rows()")[0], A_.run("open_rows()"))
        B_.until("any(e.get('t') == 'challenged' for e in events)", 15, "Bob is challenged")
        bb = B_.run("bar()")
        check("Bob's card shows Alice's choice: input delay 2 chosen by the challenger",
              "Input delay 2 (chosen by the challenger)" in bb["text"] and "Accept" in bb["buttons"], bb)
        check("Alice's chat says what she sent, with the delay",
              "You challenged Bob. Input delay: 2." in A_.run("chat()"), A_.run("chat()"))
        check("Bob's chat has the challenge with the delay", "Alice challenges you. Input delay: 2." in B_.run("chat()"),
              B_.run("chat()"))
        time.sleep(0.9)                                  # (the server wants 0.7 s between two challenges)
        select_player(A_, "Cleo")
        A_.run("tab.chal.delay_var.set(tab.chal.delay_cb.cget('values')[0]); "
               "tab.chal.delay_cb.event_generate('<<ComboboxSelected>>')")
        A_.run("click(tab.actions['challenge'])")
        A_.until("len(open_rows()) == 2", 15, "Cleo's challenge listed too")
        C_.until("any(e.get('t') == 'challenged' for e in events)", 15, "Cleo is challenged")
        cb = C_.run("bar()")
        check("Cleo's card shows an auto delay (from the ping)",
              "(auto, from the ping)" in cb["text"] and "Input delay" in cb["text"], cb)
        check("Alice has two open challenges, two Cancel buttons, 'challenged' rows in accent colour",
              A_.run("len(cancel_buttons())") == 2 and A_.run("sum('challenged' in tab.tv_players.item(i, 'tags') "
                                                              "for i in tab.tv_players.get_children())") == 2)

        # ---- a second challenge to Bob is refused client-side
        select_player(A_, "Bob")
        A_.run("click(tab.actions['challenge'])")
        check("a second challenge to the same player is not sent",
              A_.run("len(open_rows())") == 2 and "already" in A_.run("tab.status_var.get()"),
              A_.run("tab.status_var.get()"))

        # ---- Alice cancels Cleo's (the row of Cleo)
        idx = A_.run("[i for i, t in enumerate(open_rows()) if t.startswith('Cleo')][0]")
        A_.run(f"click(cancel_buttons()[{idx}])")
        A_.until("len(open_rows()) == 1", 15, "the cancelled challenge is gone")
        check("only Bob's challenge is left after Cancel", A_.run("open_rows()")[0].startswith("Bob"))
        C_.until("not bar()['buttons'] or 'Accept' not in bar()['buttons']", 15, "Cleo's card goes away")
        check("Cleo's card is gone", "Accept" not in C_.run("bar()")["buttons"])
        check("both chats say it was taken back",
              "You took back your challenge to Cleo." in A_.run("chat()")
              and "Alice took back the challenge." in C_.run("chat()"), (A_.run("chat()"), C_.run("chat()")))

        # ---- Alice challenges Dan; Bob accepts: first accept wins, Dan's is withdrawn on both sides
        time.sleep(0.9)
        select_player(A_, "Dan")
        A_.run("click(tab.actions['challenge'])")
        A_.until("len(open_rows()) == 2", 15, "two open again")
        D_.until("'Accept' in bar()['buttons']", 15, "Dan's second card")
        B_.until("'Accept' in bar()['buttons']", 15, "Bob's card still there")
        B_.run("click(bar_button('Accept'))")
        B_.until("any(e.get('t') == 'match_start' for e in events)", 30, "Bob gets match_start")
        A_.until("any(e.get('t') == 'match_start' for e in events)", 30, "Alice gets match_start")
        ms_a = A_.run("[e for e in events if e.get('t') == 'match_start'][-1]")
        ms_b = B_.run("[e for e in events if e.get('t') == 'match_start'][-1]")
        check("the match starts on both sides with the challenger's delay 2",
              ms_a.get("delay") == 2 and ms_b.get("delay") == 2, (ms_a.get("delay"), ms_b.get("delay")))
        A_.until("len(open_rows()) == 0", 15, "Alice's list empty")
        check("Alice's open challenges are all gone once a match started", A_.run("open_rows()") == [])
        D_.until("'Accept' not in bar()['buttons']", 15, "Dan's card gone")
        check("Dan's card is gone", "Accept" not in D_.run("bar()")["buttons"])
        check("Dan's chat: the challenge from Alice was withdrawn",
              "The challenge from Alice was withdrawn: a match started." in D_.run("chat()"), D_.run("chat()"))
        check("Alice's chat: her challenge to Dan was withdrawn",
              "Your challenge to Dan was withdrawn: a match started." in A_.run("chat()"), A_.run("chat()"))
        check("Alice's chat: Bob accepted", "Bob accepted your challenge." in A_.run("chat()"), A_.run("chat()"))
        check("Dan is still free (idle) after the withdrawal",
              D_.run("tab.client.me.get('status')") in ("idle", None), D_.run("tab.client.me.get('status')"))
    finally:
        pass
    return srv, pl


def sorting(srv, pl):
    """Sorting the player list by each heading; kept in online.json and restored by a new launcher."""
    D = pl["Cleo"]
    # a player of another version (a bot with another build id) cannot be played: listed below the line
    from t5lobby.buildid import BuildInfo
    from t5lobby.client import LobbyClient
    eve = LobbyClient(srv.addr, BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "ffffffffffffffff", "other"),
                      relay_bridge=False)
    eve.connect()
    eve.login_guest("Eve")
    srv.eve = eve
    D.until("any(v[0] == 'Unavailable' for i, v in rows(tab.tv_players))", 15, "the separator is listed")
    r = D.run("[v[0].split(' ')[0] for i, v in rows(tab.tv_players)]")
    check("a player of another version is listed below the 'Unavailable' line",
          r[-2:] == ["Unavailable", "Eve"], r)
    D.run("click_row(tab.tv_players, 'sep:away')")
    check("a click on the line selects nothing", D.run("list(tab.tv_players.selection())") == [],
          D.run("list(tab.tv_players.selection())"))
    for col, key in (("player", "name"), ("rank", "rank"), ("status", "status"), ("ping", "ping")):
        before = D.run("tab.chal.sort")
        D.run(f"click_heading(tab.tv_players, {col!r})")
        after = D.run("tab.chal.sort")
        check(f"clicking the {col} heading sorts by {key}", after[0] == key and after != before, after)
    D.run("click_heading(tab.tv_players, 'ping')")
    check("a second click on the same heading reverses it",
          D.run("tab.chal.sort") == ["ping", True], D.run("tab.chal.sort"))
    D.run("click_heading(tab.tv_players, 'player')")
    names = D.run("[v[0].split(' ')[0] for i, v in rows(tab.tv_players) if v[0] != 'Unavailable'][:4]")
    check("sorted by name: you first, the others in name order above the line",
          names == ["Cleo", "Alice", "Bob", "Dan", "Eve"][:1] + sorted(["Alice", "Bob", "Dan"]), names)
    head = D.run("str(tab.tv_players.heading('player', 'text'))")
    check("the sorted heading carries an arrow", "▲" in head or "▼" in head, head)
    cfg = D.run("json.load(open(__import__('os').path.join(__import__('os').environ['T5_ONLINE_DIR'], "
                "'online.json')))")
    check("the choice is stored in online.json", cfg.get("players_sort") == ["name", False], cfg.get("players_sort"))
    D.close()
    # a new launcher for Cleo: same folder, the order comes back
    return Player("Cleo", srv.addr, again=True)


def board(srv):
    """The leaderboard with a 1.1.9 server's rows and with an old server's rows."""
    store = srv.srv.store
    real = store.leaderboard
    rows = [{"id": f"x{i}", "name": nm, "rating": 1700.0 - 50 * i, "rd": 60.0, "games": 40 - i, "ranked_games": 30 - i,
             "wins": 20 - i, "losses": 15, "draws": 0, "tier": 20 - i, "tier_peak": 21 - i, "place": i + 1}
            for i, nm in enumerate(("Zed", "Yan", "Xia"))]
    split = {"Zed": (12, 3, 8, 2), "Yan": (5, 9, 30, 1), "Xia": (7, 7, 1, 10)}

    def new(limit=20, offset=0):
        out = []
        for r in rows:
            r = dict(r)
            r["ranked_wins"], r["ranked_losses"], r["casual_wins"], r["casual_losses"] = split[r["name"]]
            r["main"] = "jin"
            out.append(r)
        return out

    def old(limit=20, offset=0):
        return [dict(r, main="jin") for r in rows]
    return real, new, old, store


def board_check(srv, p):
    real, new, old, store = board(srv)
    srv.srv._lb_cache = {}
    store.leaderboard = new
    p.run("app.nb.select(app.tabs['online']); tab.nb.select(tab.board_page); tab.load_leaderboard()")
    p.until("len(tab.tv_board.get_children()) == 3", 15, "leaderboard rows (1.1.9 server)")
    cols = p.run("list(tab.tv_board['displaycolumns'])")
    check("1.1.9 server rows: the ranked / casual columns are shown, the Record column is not",
          cols == ["place", "player", "rank", "rating", "rw", "rl", "cw", "cl", "main"], cols)
    vals = p.run("[list(tab.tv_board.item(i, 'values')) for i in tab.tv_board.get_children()]")
    check("... with the server's numbers (Zed 12 / 3 ranked, 8 / 2 casual)",
          str(vals[0][1]).split()[0] == "Zed" and [str(x) for x in vals[0][5:9]] == ["12", "3", "8", "2"],
          vals[0])
    heads = p.run("[tab.tv_board.heading(c, 'text') for c in tab.tv_board['displaycolumns']]")
    check("... and their headings are sortable (arrow on the sorted one)", any("▲" in h for h in heads), heads)
    p.run("click_heading(tab.tv_board, 'cw')")
    order = p.run("[tab.tv_board.item(i, 'values')[1].split()[0] for i in tab.tv_board.get_children()]")
    check("a click on 'Casual W' sorts by casual wins, most first (Yan 30, Zed 8, Xia 1)",
          order == ["Yan", "Zed", "Xia"], order)
    p.run("click_heading(tab.tv_board, 'cw')")
    order = p.run("[tab.tv_board.item(i, 'values')[1].split()[0] for i in tab.tv_board.get_children()]")
    check("a second click reverses it", order == ["Xia", "Zed", "Yan"], order)
    store.leaderboard = old
    srv.srv._lb_cache = {}
    time.sleep(0.1)
    p.run("tab.load_leaderboard()")
    p.until("list(tab.tv_board['displaycolumns']) == ['place', 'player', 'rank', 'rating', 'record', 'main']", 15,
            "old rows: the Record column is back")
    check("old server rows (no split fields): the Record column as before", True)
    order = p.run("[tab.tv_board.item(i, 'values')[1].split()[0] for i in tab.tv_board.get_children()]")
    check("... still listed (sort on a missing field falls back to the place)", order == ["Zed", "Yan", "Xia"], order)
    store.leaderboard = real


def main():
    srv, pl = scenario()
    try:
        d2 = sorting(srv, pl)
        pl["Cleo"] = d2
        d2.run("tab.server_var.set(%r); tab.name_var.set('Cleo'); app.nb.select(app.tabs['online'])" % srv.addr)
        d2.run("tab.do_login('guest')")
        d2.until("bool(tab.client and tab.client.me) and len(tab.tv_players.get_children()) >= 4", 30, "Cleo again")
        check("a new launcher starts with the same sort (name)", d2.run("tab.chal.sort") == ["name", False],
              d2.run("tab.chal.sort"))
        h = d2.run("str(tab.tv_players.heading('player', 'text'))")
        check("... and the arrow on the heading", "▲" in h, h)
        board_check(srv, d2)
        errs = []
        for p in pl.values():
            p.run("1")
            log = os.path.join(p.dir, "launcher.log")
            if os.path.exists(log):
                errs += [x for x in open(log, encoding="utf-8", errors="replace").read().split("\n")
                         if x.startswith("error in the launcher")]
        check("no 'error in the launcher' in any launcher's log", not errs, errs[:2])
    except Exception:      # noqa: BLE001
        traceback.print_exc()
        check("the click-through ran to its end", False, "exception")
    finally:
        for p in pl.values():
            p.close()
    ok = all(r[1] for r in RESULTS)
    print(json.dumps({"ok": ok, "checks": len(RESULTS), "failed": [r[0] for r in RESULTS if not r[1]],
                      "python": sys.version.split()[0]}), flush=True)
    shutil.rmtree(WORK, True)
    os._exit(0 if ok else 1)


if __name__ == "__main__":
    main()
