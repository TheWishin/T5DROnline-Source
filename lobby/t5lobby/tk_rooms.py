"""The Online tab's rooms (docs/ONLINE.md "Rooms"): the Create room window (players, turns, who can join: anybody, a
password or an invite code, hidden from the list), joining a locked room (it asks for the password or the code; Join
room with no room selected asks for an invite code), and this player's room under the rooms list: who is in it, who
plays, who is next, Sit out / Back in line, the host's Room settings (lock, password, new invite code, hidden, remove
a player) and Copy invite code.

Copy invite code puts the code into the launcher's own field next to the button and selects it there -- nothing goes
to the system clipboard by itself (the player presses Ctrl+C when they want it); the field does not export its
selection either. The code is shown only after that press. A password is typed into a masked field, goes to the
server once and is never kept, logged or shown.

The tab (tk_tab.py) owns one RoomsUI and calls it from a few places: the rooms card (build), the lobby list (state
texts), its actions, its events and its poll.
"""
import time
import tkinter as tk
from tkinter import ttk

from . import proto
from .i18n import N_, t
from .theme import C

ROTATION_CHOICES = ((N_("Winner stays"), "winner"), (N_("Everyone in turn"), "queue"))
ACCESS_CHOICES = ((N_("Anybody"), None), (N_("Private (password)"), "password"), (N_("Private (invite code)"), "code"))
PW_RULE = N_("Room passwords are 4-64 characters, with no space at the start or end.")


def _pick(choices, shown):
    return next((v for label, v in choices if t(label) == shown), choices[0][1])


class RoomsUI:
    def __init__(self, tab):
        self.tab = tab
        self.frame = None         # this player's room, under the rooms list (shown while in a room)
        self.text = None          # tk.StringVar: its summary
        self.code_var = None      # the invite code field (empty until Copy invite code)
        self.code_entry = None
        self.window = None        # Create room / Room settings (one at a time)
        self._shown = None        # (room id, code) the code field shows

    # ------------------------------------------------------------------ helpers
    @property
    def client(self):
        return self.tab.client

    def ok(self):
        c = self.client
        return c is not None and c.connected and c.private_rooms_ok()

    def mine(self):
        c = self.client
        return c.my_room if c is not None and c.me and c.me.get("status") in ("room", "match", "playing") else None

    def _host(self, r):
        me = (self.client.me or {}) if self.client else {}
        return r is not None and r.get("owner_id") == me.get("id")

    # ------------------------------------------------------------------ the rooms card
    def build(self, rc, px, view):
        """This player's room: a row under the rooms list (hidden while not in a room)."""
        tab = self.tab
        self.px = px
        f = view.body(rc)
        f.columnconfigure(0, weight=1)
        self.text = tk.StringVar(rc, value="")
        view.wrap(ttk.Label(f, textvariable=self.text, style="Card.Small.TLabel", justify="left"), rc, 30).grid(
            row=0, column=0, sticky="w")
        row = view.body(f)
        row.grid(row=1, column=0, sticky="w", pady=(px(6), 0))
        for key, label, cmd in (("room_line", t("Sit out"), self.toggle_line),
                                ("room_settings", t("Room settings..."), self.settings)):
            b = ttk.Button(row, text=label, style="Card.Small.TButton", state="disabled", command=cmd)
            b.pack(side="left", padx=(0, px(6)))
            tab.actions[key], tab.action_text[key] = b, label
        code = view.body(f)
        code.grid(row=2, column=0, sticky="w", pady=(px(6), 0))
        b = ttk.Button(code, text=t("Copy invite code"), style="Card.Small.TButton", state="disabled",
                       command=self.copy_code)
        b.pack(side="left", padx=(0, px(6)))
        tab.actions["room_code"], tab.action_text["room_code"] = b, t("Copy invite code")
        self.code_var = tk.StringVar(rc, value="")
        # (exportselection off: a selection here never becomes the system's selection; only Ctrl+C copies it)
        self.code_entry = ttk.Entry(code, textvariable=self.code_var, style="Card.TEntry", width=16, state="readonly",
                                    exportselection=False, font=view.th.fonts.get("code"))
        self.code_entry.pack(side="left")
        self.frame = f
        self.rc = rc
        return f

    def list_state(self, r):
        """The rooms list's state column for room r beyond its status: players / size, private."""
        parts = []
        if r.get("size", 2) != 2:
            parts.append(f"{len(r.get('members') or ())}/{r['size']}")
        if r.get("private"):
            parts.append(t("private"))
        return parts

    def set_actions(self, me, st, busy):
        """The room row's buttons (the tab's _set_actions decides when it calls)."""
        r = self.mine()
        acts = self.tab.actions
        on = {"room_line": bool(me and r and r.get("size", 2) > 2 and st == "room" and not busy),
              "room_settings": bool(me and r and self._host(r) and self.ok()),
              "room_code": bool(me and r and r.get("lock") == "code" and self.client.room_code)}
        if r is not None:
            away = me is not None and me.get("id") not in (r.get("line") or ())
            label = t("Back in line") if away else t("Sit out")
            self.tab.action_text["room_line"] = label
        return on if acts else {}

    # ------------------------------------------------------------------ this player's room
    def refresh(self):
        """Show / hide the room row and say what is going on in the room."""
        if self.frame is None:
            return
        r = self.mine()
        try:
            if r is None:
                if self.frame.winfo_manager():
                    self.frame.grid_remove()
                self.text.set("")
                self.code_var.set("")
                self._shown = None
                return
            if not self.frame.winfo_manager():
                self.frame.grid(row=2, column=0, sticky="we", pady=(self.px(8), 0))
        except tk.TclError:
            return
        if self._shown is not None and self._shown != (r.get("id"), self.client.room_code):
            self.code_var.set("")                     # (another room, or a new code: shown again on the next press)
            self._shown = None
        self.text.set(self.summary(r))

    def summary(self, r):
        players = {p.get("id"): p for p in r.get("players") or ()}
        name = lambda pid: (players.get(pid) or {}).get("name", "?")     # noqa: E731
        head = [t("Your room: {name}", name=r.get("name", "?")),
                t("{count}/{size} players", count=len(players), size=r.get("size", 2))]
        if r.get("lock") == "password":
            head.append(t("private (password)"))
        elif r.get("lock") == "code":
            head.append(t("private (invite code)"))
        if r.get("hidden"):
            head.append(t("hidden"))
        if r.get("size", 2) > 2:
            head.append(t(ROTATION_CHOICES[0][0]) if r.get("rotation") == "winner" else t(ROTATION_CHOICES[1][0]))
        lines = [" · ".join(head)]
        playing = r.get("playing") or []
        nxt = r.get("next") or {}
        if len(playing) == 2:
            lines.append(t("Playing: {p1} vs {p2}", p1=name(playing[0]), p2=name(playing[1])))
        elif nxt.get("players") and len(nxt["players"]) == 2:
            off = getattr(self.client, "clock_offset", None) or 0.0
            secs = max(0, int(round(float(nxt.get("at") or 0) - (time.time() + off))))
            lines.append(t("Next: {p1} vs {p2} in {seconds} s", p1=name(nxt["players"][0]), p2=name(nxt["players"][1]),
                           seconds=secs))
        if r.get("size", 2) > 2:
            names = []
            for pid in r.get("line") or ():
                n = name(pid)
                names.append(t("{name} (host)", name=n) if pid == r.get("owner_id") else n)
            for pid, p in players.items():
                if p.get("state") == "away":
                    names.append(t("{name} (sitting out)", name=p.get("name", "?")))
            lines.append(t("Line: {names}", names=", ".join(names)))
        return "\n".join(lines)

    def tick(self):
        """The tab's poll: the countdown to the room's next match."""
        r = self.mine()
        if r is not None and (r.get("next") or {}).get("players"):
            self.refresh()

    def on_event(self, ev):
        kind = ev.get("t")
        if kind in ("room", "lobby_state"):
            self.refresh()
        elif kind == "notice" and ev.get("code") == "room_kicked":
            self.close_window()
            self.refresh()

    # ------------------------------------------------------------------ actions
    def create(self):
        """Create room: the window when the server has private rooms, else a classic room at once (as before)."""
        tab = self.tab
        if not self.ok():
            tab.call(tab.client.create_room, None)
            return
        self.close_window()
        self.window = create_window(self)

    def join_selected(self):
        """Join room: the selected room (asking for its password or invite code when it is locked); with nothing
        selected, a room's invite code."""
        tab = self.tab
        sel = tab.tv_rooms.selection()
        if not sel:
            if not self.ok():
                tab.status(t("Select a room first."))
                return
            code = tab.ask_string(t("Invite code"), t("No room selected. Join a room with its invite code "
                                                      "(XXXX-XXXX-XXXX):"), parent=tab.parent)
            if code and code.strip():
                tab.call(tab.client.join_room, None, None, code.strip())
            return
        r = next((x for x in tab.client.rooms if x.get("id") == sel[0]), {})
        lock = r.get("lock") if r.get("private") else None
        if lock == "password":
            pw = tab.ask_string(t("Room password"), t("“{room}” is private. Its password:", room=r.get("name", "?")),
                                show="*", parent=tab.parent)
            if not pw:
                return
            if proto.clean_room_password(pw) is None:
                tab.status(t(PW_RULE), error=True)
                return
            tab.call(tab.client.join_room, sel[0], pw)
        elif lock == "code":
            code = tab.ask_string(t("Invite code"), t("The room's invite code (XXXX-XXXX-XXXX):"), parent=tab.parent)
            if code and code.strip():
                tab.call(tab.client.join_room, sel[0], None, code.strip())
        else:
            tab.call(tab.client.join_room, sel[0])

    def toggle_line(self):
        r = self.mine()
        me = (self.client.me or {}) if self.client else {}
        if r is None:
            return
        back = me.get("id") not in (r.get("line") or ())
        self.tab.call(self.client.room_line, back, then=lambda _r: self.tab.status(
            t("Back in line: you play when it is your turn.") if back else
            t("You sit out: your turns are skipped until you press Back in line.")))

    def copy_code(self):
        """The invite code into the launcher's own field, selected there -- never to the system clipboard."""
        code = self.client.room_code if self.client else None
        r = self.mine()
        if not code or r is None:
            return
        self.code_var.set(code)
        self._shown = (r.get("id"), code)
        try:
            self.code_entry.focus_set()
            self.code_entry.selection_range(0, "end")
            self.code_entry.icursor("end")
        except tk.TclError:
            pass
        self.tab.status(t("The invite code is in the field next to the button: select it and press Ctrl+C to copy "
                          "it."))

    def settings(self):
        r = self.mine()
        if r is None or not self._host(r):
            return
        self.close_window()
        self.window = settings_window(self, r)

    def kick(self, pid, name):
        tab = self.tab
        if not tab.ask_yes_no(t("Remove player"), t("Remove {name} from the room? They cannot come back into it.",
                                                     name=name), parent=tab.parent):
            return
        tab.call(tab.client.room_kick, pid, then=lambda _r: tab.status(t("Removed {name} from the room.", name=name)))

    def close_window(self):
        w, self.window = self.window, None
        if w is not None:
            try:
                w.destroy()
            except tk.TclError:
                pass


# ---------------------------------------------------------------------------- windows
def _window(ui, title):
    tab = ui.tab
    view = tab.view
    w = tab.new_window(tab.parent)
    w.title(title)
    try:
        w.configure(bg=C["bg"])
    except tk.TclError:
        pass
    card = view.card(w, pad=18)
    card.pack(fill="both", expand=True, padx=view.px(10), pady=view.px(10))
    card.columnconfigure(1, weight=1)
    ttk.Label(card, text=title, style="Card.H2.TLabel").grid(row=0, column=0, columnspan=2, sticky="w",
                                                            pady=(0, view.px(10)))
    return w, card


def create_window(ui):
    tab = ui.tab
    px = tab.view.px
    w, card = _window(ui, t("Create a room"))
    limits = (tab.client.welcome or {}).get("room_limits") or {}
    top = max(2, min(16, int(limits.get("max_size") or 8)))
    v = {"name": tk.StringVar(w, value=""), "size": tk.StringVar(w, value="2"),
         "rotation": tk.StringVar(w, value=t(ROTATION_CHOICES[0][0])),
         "access": tk.StringVar(w, value=t(ACCESS_CHOICES[0][0])), "password": tk.StringVar(w, value=""),
         "hidden": tk.IntVar(w, value=0)}
    rows = (("name", t("Room name (optional):"), None),
            ("size", t("Players:"), [str(n) for n in range(2, top + 1)]),
            ("rotation", t("Turns (3 or more players):"), [t(x) for x, _v in ROTATION_CHOICES]),
            ("access", t("Who can join:"), [t(x) for x, _v in ACCESS_CHOICES]),
            ("password", t("Password (4-64 characters):"), None))
    widgets = {}
    for i, (key, label, values) in enumerate(rows):
        ttk.Label(card, text=label, style="Card.Muted.TLabel").grid(row=i + 1, column=0, sticky="w", pady=px(3),
                                                                   padx=(0, px(10)))
        if values is None:
            e = ttk.Entry(card, textvariable=v[key], style="Card.TEntry", width=28,
                          show="*" if key == "password" else "")
        else:
            e = ttk.Combobox(card, textvariable=v[key], values=values, state="readonly", style="Card.TCombobox",
                             width=26)
        e.grid(row=i + 1, column=1, sticky="we", pady=px(3))
        widgets[key] = e
    hide = ttk.Checkbutton(card, text=t("Hide the room from the room list"), variable=v["hidden"],
                           style="Card.TCheckbutton")
    hide.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(px(6), 0))
    widgets["hidden"] = hide
    err = ttk.Label(card, text="", style="Card.error.TLabel", wraplength=px(360), justify="left")
    err.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="w", pady=(px(6), 0))

    def sync(*_a):
        many = v["size"].get() not in ("", "2")
        lock = _pick(ACCESS_CHOICES, v["access"].get())
        try:
            widgets["rotation"].configure(state="readonly" if many else "disabled")
            widgets["password"].configure(state="normal" if lock == "password" else "disabled")
        except tk.TclError:
            pass
    for key in ("size", "access"):
        v[key].trace_add("write", sync)
    sync()

    def create():
        lock = _pick(ACCESS_CHOICES, v["access"].get())
        pw = v["password"].get() if lock == "password" else None
        if lock == "password" and proto.clean_room_password(pw) is None:
            err.configure(text=t(PW_RULE))
            return
        try:
            size = int(v["size"].get() or 2)
        except ValueError:
            size = 2
        rotation = _pick(ROTATION_CHOICES, v["rotation"].get())
        name = v["name"].get().strip() or None
        hidden = bool(v["hidden"].get())
        v["password"].set("")                          # (not kept in the window either)

        def done(_room):
            ui.close_window()
            tab.status(t("Room created. Press Copy invite code to see the code you can share.") if lock == "code"
                       else t("Room created."))
        tab.call(tab.client.create_room, name, False, size, rotation, lock, pw, hidden, then=done)

    bar = tab.view.body(card)
    bar.grid(row=len(rows) + 3, column=0, columnspan=2, sticky="we", pady=(px(12), 0))
    ttk.Button(bar, text=t("Cancel"), style="Card.TButton", command=ui.close_window).pack(side="right")
    b = ttk.Button(bar, text=t("Create"), style="Card.Accent.TButton", command=create)
    b.pack(side="right", padx=(0, px(8)))
    w.create_button = b
    w.widgets, w.vars, w.err = widgets, v, err
    return w


def settings_window(ui, r):
    """The host's window: who can join (a new password, a new invite code, open), hidden, remove a player."""
    tab = ui.tab
    px = tab.view.px
    w, card = _window(ui, t("Room settings"))
    shown = {None: ACCESS_CHOICES[0][0], "password": ACCESS_CHOICES[1][0], "code": ACCESS_CHOICES[2][0]}
    v = {"access": tk.StringVar(w, value=t(shown.get(r.get("lock"), ACCESS_CHOICES[0][0]))),
         "password": tk.StringVar(w, value=""), "hidden": tk.IntVar(w, value=1 if r.get("hidden") else 0)}
    ttk.Label(card, text=t("Who can join:"), style="Card.Muted.TLabel").grid(row=1, column=0, sticky="w", pady=px(3),
                                                                            padx=(0, px(10)))
    access = ttk.Combobox(card, textvariable=v["access"], values=[t(x) for x, _v in ACCESS_CHOICES], state="readonly",
                          style="Card.TCombobox", width=26)
    access.grid(row=1, column=1, sticky="we", pady=px(3))
    ttk.Label(card, text=t("Password (4-64 characters):"), style="Card.Muted.TLabel").grid(
        row=2, column=0, sticky="w", pady=px(3), padx=(0, px(10)))
    pw = ttk.Entry(card, textvariable=v["password"], style="Card.TEntry", width=28, show="*")
    pw.grid(row=2, column=1, sticky="we", pady=px(3))
    hide = ttk.Checkbutton(card, text=t("Hide the room from the room list"), variable=v["hidden"],
                           style="Card.TCheckbutton")
    hide.grid(row=3, column=0, columnspan=2, sticky="w", pady=(px(6), 0))
    err = ttk.Label(card, text="", style="Card.error.TLabel", wraplength=px(360), justify="left")
    err.grid(row=4, column=0, columnspan=2, sticky="w", pady=(px(4), 0))

    def sync(*_a):
        try:
            pw.configure(state="normal" if _pick(ACCESS_CHOICES, v["access"].get()) == "password" else "disabled")
        except tk.TclError:
            pass
    v["access"].trace_add("write", sync)
    sync()

    def save(new_code=False):
        want = _pick(ACCESS_CHOICES, v["access"].get())
        hidden = bool(v["hidden"].get())
        cur = (tab.client.my_room or {}).get("lock")
        lock, p = None, None                          # (None: the lock stays as it is)
        if new_code:
            lock = "code"
        elif want is None:
            lock = "none" if cur is not None else None
        elif want == "password":
            p = v["password"].get()
            if p or cur != "password":                # (nothing typed: keep the old password)
                if proto.clean_room_password(p) is None:
                    err.configure(text=t(PW_RULE))
                    return
                lock = "password"
            else:
                p = None
        elif want == "code" and cur != "code":        # (a code room keeps the code its players have)
            lock = "code"
        v["password"].set("")

        def done(_r):
            err.configure(text="")
            tab.status(t("Room settings saved."))
        tab.call(tab.client.room_lock, lock, p, hidden, then=done)

    bar = tab.view.body(card)
    bar.grid(row=5, column=0, columnspan=2, sticky="we", pady=(px(10), 0))
    b_save = ttk.Button(bar, text=t("Save"), style="Card.Accent.TButton", command=save)
    b_save.pack(side="left")
    b_code = ttk.Button(bar, text=t("New invite code"), style="Card.TButton", command=lambda: save(True))
    b_code.pack(side="left", padx=(px(8), 0))

    me = (tab.client.me or {}).get("id")
    others = [p for p in r.get("players") or () if p.get("id") != me]
    ttk.Label(card, text=t("Players in the room:"), style="Card.Muted.TLabel").grid(
        row=6, column=0, columnspan=2, sticky="w", pady=(px(14), px(4)))
    lb = tk.Listbox(card, height=max(3, min(8, len(others))), width=30, activestyle="none", exportselection=False)
    for p in others:
        lb.insert("end", p.get("name", "?"))
    lb.grid(row=7, column=0, columnspan=2, sticky="we")

    def kick():
        sel = lb.curselection()
        if sel:
            p = others[sel[0]]
            ui.kick(p.get("id"), p.get("name", "?"))
    b_kick = ttk.Button(card, text=t("Remove player"), style="Card.TButton", command=kick)
    b_kick.grid(row=8, column=0, sticky="w", pady=(px(8), 0))
    ttk.Button(card, text=t("Close"), style="Card.TButton", command=ui.close_window).grid(
        row=8, column=1, sticky="e", pady=(px(8), 0))
    w.vars, w.err, w.players, w.save_button, w.code_button, w.kick_button = v, err, lb, b_save, b_code, b_kick
    return w
