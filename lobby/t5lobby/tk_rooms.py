"""The Online tab's rooms (docs/ONLINE.md "Rooms"): the Create room window (players, turns, who can join: anybody, a
password or an invite code, hidden from the list), joining a locked room (it asks for the password or the code; Join
room with no room selected asks for an invite code), and this player's room under the rooms list: who is in it, who
plays, who is next, Sit out / Back in line, the host's Room settings (lock, password, new invite code, hidden, remove
a player, turn away the networks that typed wrong passwords) and Copy invite code. The host of a password room sees
how many wrong passwords came in the last 10 minutes and from how many networks (the server never says who or where).

Copy invite code puts the code into the launcher's own field next to the button and selects it there -- nothing goes
to the system clipboard by itself (the player presses Ctrl+C when they want it); the field does not export its
selection either. The code is shown only after that press. A password is typed into a masked field, goes to the
server once and is never kept, logged or shown.

The tab (tk_tab.py) owns one RoomsUI and calls it from a few places: the rooms card (build), the lobby list (state
texts), its actions, its events and its poll.
"""
from functools import partial
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import proto
from .i18n import N_, t
from .theme import C

ROTATION_CHOICES = ((N_("Winner stays"), "winner"), (N_("Everyone in turn"), "queue"))
MODE_CHOICES = ((N_("One match, taking turns"), "line"), (N_("Several matches at once"), "tables"))
ACCESS_CHOICES = ((N_("Anybody"), None), (N_("Private (password)"), "password"), (N_("Private (invite code)"), "code"))
REMATCH_CHOICES = ((N_("Both players confirm"), "both_confirm"),
                   (N_("Start automatically unless declined"), "auto_unless_declined"))
PW_RULE = N_("Room passwords are 4-64 characters, with no space at the start or end.")


def _pick(choices, shown):
    return next((v for label, v in choices if t(label) == shown), choices[0][1])


def _fit_choices(box):
    """Keep translated choices readable in the closed combobox, including fallback fonts."""
    font = tkfont.Font(root=box, font=box.cget("font"))
    unit = max(1, font.measure("0"))
    longest = max((font.measure(str(value)) for value in box.cget("values")), default=0)
    # Tk's width is in zero-character units; leave one extra unit beside the text.
    box.configure(width=max(int(box.cget("width")), (longest + unit - 1) // unit + 1))


def _room_rules_supported(client, size=2, ranked=False, mode="line"):
    """Only the server's versioned classic casual rule can replace explicit rematch votes."""
    return bool(size == 2 and mode == "line" and not ranked
                and getattr(client, "ingame_rematch_ok", lambda: False)())


def _room_rule_values(client, size=2, ranked=False, policy="both_confirm", auto_skip_after_round=False, mode="line"):
    """Drop disabled/stale controls before making a request, including on older servers.

    Skipping is a room wish only: the server still needs each player's separate consent and both game caps.
    """
    if not _room_rules_supported(client, size, ranked, mode):
        return {}
    policies = [value for _label, value in REMATCH_CHOICES]
    rules = {"rematch_policy": policy if policy in policies else "both_confirm"}
    if getattr(client, "auto_skip_ok", lambda: False)():
        rules["auto_skip_after_round"] = bool(auto_skip_after_round)
    return rules


def _save_settings(tab, lock, password, hidden, rules, done):
    """Keep the existing lock operation and wait for each server acknowledgement before showing success."""
    client = tab.client
    room_id = (getattr(client, "my_room", None) or {}).get("id")

    def current():
        return (tab.client is client
                and (getattr(client, "my_room", None) or {}).get("id") == room_id)

    def saved(result):
        if current():
            done(result)

    def locked(result):
        if not current():
            return
        if rules:
            tab.call(client.room_rules, rules.get("rematch_policy"), rules.get("auto_skip_after_round"), then=saved)
        else:
            saved(result)
    tab.call(client.room_lock, lock, password, hidden, then=locked)


class RoomsUI:
    def __init__(self, tab):
        self.tab = tab
        self.frame = None         # this player's room, under the rooms list (shown while in a room)
        self.text = None          # tk.StringVar: its summary
        self.code_var = None      # the invite code field (empty until Copy invite code)
        self.code_entry = None
        self.window = None        # Create room / Room settings (one at a time)
        self._shown = None        # (room id, code) the code field shows
        self.members_frame = None
        self._members_shown = None

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
                                ("room_tables", t("Tables..."), self.tables),
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
        self.members_frame = view.body(f)
        self.members_frame.grid(row=3, column=0, sticky="we", pady=(px(6), 0))
        self.members_frame.columnconfigure(0, weight=1)
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
        if r.get("mode") == "tables":
            parts.append(t("Several matches at once"))
        if r.get("training"):
            parts.append(t("training"))
        elif not r.get("ranked") and r.get("first_to"):
            parts.append(t("FT{wins}", wins=r["first_to"]))
        return parts

    def set_actions(self, me, st, busy):
        """The room row's buttons (the tab's _set_actions decides when it calls)."""
        r = self.mine()
        acts = self.tab.actions
        on = {"room_line": bool(me and r and (r.get("size", 2) > 2 or r.get("mode") == "tables")
                               and st == "room" and not busy),
              "room_tables": bool(me and r and r.get("mode") == "tables"),
              "room_settings": bool(me and r and self._host(r) and self.ok()),
              "room_code": bool(me and r and r.get("lock") == "code" and self.client.room_code)}
        if r is not None:
            away = me is not None and me.get("id") not in (r.get("line") or ())
            label = t("Available to play") if away and r.get("mode") == "tables" else (
                t("Back in line") if away else t("Sit out"))
            self.tab.action_text["room_line"] = label
        if r is not None and r.get("training") and me is not None and st in ("match", "playing"):
            on["leave"] = True        # a training room: leave any time, its fight too (nothing is counted either way)
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
                self._refresh_members(None)
                return
            if not self.frame.winfo_manager():
                self.frame.grid(row=2, column=0, sticky="we", pady=(self.px(8), 0))
        except tk.TclError:
            return
        if self._shown is not None and self._shown != (r.get("id"), self.client.room_code):
            self.code_var.set("")                     # (another room, or a new code: shown again on the next press)
            self._shown = None
        self.text.set(self.summary(r))
        self._refresh_members(r)

    def _member_rows(self, room):
        """Request identities come from room data, never from rendered badge labels."""
        c = self.client
        if not room or not c:
            return []
        me = (c.me or {}).get("id")
        muted = getattr(c, "is_muted", lambda name: False)
        private = bool(getattr(c, "private_chat_ok", lambda: False)())
        return [(p["id"], p["name"], bool(muted(p["name"])), private)
                for p in room.get("players") or ()
                if p.get("id") and p.get("id") != me and isinstance(p.get("name"), str) and p["name"]]

    def _refresh_members(self, room):
        """Every other room member has a direct mute button, including during a match."""
        if self.members_frame is None:
            return
        rows = self._member_rows(room)
        signature = ((room or {}).get("id"), tuple(rows))
        if signature == self._members_shown:
            return
        self._members_shown = signature
        for widget in self.members_frame.winfo_children():
            widget.destroy()
        for index, (_pid, name, muted, private) in enumerate(rows):
            ttk.Label(self.members_frame, text=name, style="Card.Small.TLabel").grid(
                row=index, column=0, sticky="w", padx=(0, self.px(6)))
            ttk.Button(self.members_frame, text=t("Unmute") if muted else t("Mute"),
                       style="Card.Small.TButton", command=partial(self.toggle_mute, name)).grid(
                row=index, column=1, sticky="e", padx=(0, self.px(6)))
            ttk.Button(self.members_frame, text=t("Message player"), style="Card.Small.TButton",
                       state="normal" if private else "disabled",
                       command=partial(self.message_player, name)).grid(row=index, column=2, sticky="e")

    def toggle_mute(self, name):
        """A stale row cannot act on a player who left or a different room."""
        if any(row[1] == name for row in self._member_rows(self.mine())):
            self.tab.toggle_mute(name)

    def message_player(self, name):
        if any(row[1] == name and row[3] for row in self._member_rows(self.mine())):
            self.tab.private_chat.show(name)

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
        if r.get("training"):
            head.append(t("training: endless health, nothing counted"))
        elif not r.get("ranked") and r.get("first_to"):
            head.append(t("FT{wins}", wins=r["first_to"]))
        if (_room_rules_supported(self.client, r.get("size", 2), r.get("ranked", False), r.get("mode", "line"))
                and "rematch_policy" in r):
            policy = r.get("rematch_policy")
            head.append(t(next((label for label, value in REMATCH_CHOICES if value == policy),
                               REMATCH_CHOICES[0][0])))
        if r.get("mode") == "tables":
            head.append(t("Several matches at once"))
        elif r.get("size", 2) > 2:
            head.append(t(ROTATION_CHOICES[0][0]) if r.get("rotation") == "winner" else t(ROTATION_CHOICES[1][0]))
        lines = [" · ".join(head)]
        if r.get("mode") == "tables":
            for table in r.get("tables") or ():
                lines.append(self.table_summary(r, table))
            free = [name(p.get("id")) for p in self.free_players(r)]
            away = [name(p.get("id")) for p in players.values() if p.get("state") == "away"]
            lines.append(t("Available: {names}", names=", ".join(free)))
            if away:
                lines.append(t("Away: {names}", names=", ".join(away)))
        playing = r.get("playing") or []
        nxt = r.get("next") or {}
        if len(playing) == 2:
            lines.append(t("Playing: {p1} vs {p2}", p1=name(playing[0]), p2=name(playing[1])))
        elif nxt.get("players") and len(nxt["players"]) == 2:
            off = getattr(self.client, "clock_offset", None) or 0.0
            secs = max(0, int(round(float(nxt.get("at") or 0) - (time.time() + off))))
            lines.append(t("Next: {p1} vs {p2} in {seconds} s", p1=name(nxt["players"][0]), p2=name(nxt["players"][1]),
                           seconds=secs))
        st = r.get("set") or {}
        wins = st.get("wins")
        if st.get("casual") and isinstance(wins, list) and len(wins) == 2:
            lines.append(t("FT{wins}", wins=st.get("first_to") or st.get("wins_needed") or 1)
                         + " -- " + t("Set {mine}-{theirs}", mine=wins[0], theirs=wins[1]))
        g = r.get("guesses") if self._host(r) else None
        if isinstance(g, dict) and g.get("wrong"):
            lines.append(t("Wrong passwords in the last 10 minutes: {count} (networks: {networks})",
                           count=int(g.get("wrong") or 0), networks=int(g.get("networks") or 0)))
        if r.get("size", 2) > 2 and r.get("mode") != "tables":
            names = []
            for pid in r.get("line") or ():
                n = name(pid)
                names.append(t("{name} (host)", name=n) if pid == r.get("owner_id") else n)
            for pid, p in players.items():
                if p.get("state") == "away":
                    names.append(t("{name} (sitting out)", name=p.get("name", "?")))
            lines.append(t("Line: {names}", names=", ".join(names)))
        return "\n".join(lines)

    def free_players(self, r):
        """A display hint only: the server validates availability again when the host sets a pair."""
        seated = {pid for table in r.get("tables") or () for pid in table.get("players") or ()}
        available = set(r.get("line") or ())
        return [p for p in r.get("players") or () if p.get("id") in available and p.get("id") not in seated
                and p.get("state") != "away"]

    def pair_players(self, r):
        """The host may rearrange countdown reservations, but never a match or unfinished set."""
        busy = {pid for table in r.get("tables") or ()
                if table.get("match") or (table.get("set") or {}).get("state") == "active"
                for pid in table.get("players") or ()}
        available = set(r.get("line") or ())
        return [p for p in r.get("players") or () if p.get("id") in available and p.get("id") not in busy
                and p.get("state") != "away"]

    def table_summary(self, r, table):
        players = {p.get("id"): p for p in r.get("players") or ()}
        # Public rooms also name opponents from the lobby's ordinary player list.
        for p in getattr(self.client, "players", None) or ():
            players.setdefault(p.get("id"), p)
        pair = table.get("players") or (table.get("next") or {}).get("players") or ()
        names = t("{p1} vs {p2}", p1=(players.get(pair[0]) or {}).get("name", "?"),
                  p2=(players.get(pair[1]) or {}).get("name", "?")) if len(pair) == 2 else t("Empty table")
        text = t("Table {table}: {players}", table=table.get("id"), players=names)
        st = table.get("set") or {}
        wins = st.get("wins")
        if st.get("casual") and isinstance(wins, list) and len(wins) == 2:
            text += " -- " + t("FT{wins}", wins=st.get("first_to") or st.get("wins_needed") or 1)
            text += " -- " + t("Set {mine}-{theirs}", mine=wins[0], theirs=wins[1])
        nxt = table.get("next") or {}
        if nxt.get("at") is not None:
            off = getattr(self.client, "clock_offset", None) or 0.0
            seconds = max(0, int(round(float(nxt["at"]) - (time.time() + off))))
            text += " -- " + t("starts in {seconds} s", seconds=seconds)
        return text

    def tick(self):
        """The tab's poll: the countdown to the room's next match."""
        r = self.mine()
        if r is not None and ((r.get("next") or {}).get("players") or r.get("mode") == "tables"):
            self.refresh()
        if self.window is not None and hasattr(self.window, "refresh_tables"):
            self.window.refresh_tables()

    def on_event(self, ev):
        kind = ev.get("t")
        if kind in ("room", "lobby_state", "mutes"):
            self.refresh()
            if self.window is not None and hasattr(self.window, "refresh_tables"):
                self.window.refresh_tables()
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
        client = tab.client
        if client is None:
            return
        sel = tab.tv_rooms.selection()
        if not sel:
            if not self.ok():
                tab.status(t("Select a room first."))
                return
            code = tab.ask_string(t("Invite code"), t("No room selected. Join a room with its invite code "
                                                      "(XXXX-XXXX-XXXX):"), parent=tab.parent)
            if tab.client is client and code and code.strip():
                tab.call(client.join_room, None, None, code.strip())
            return
        r = next((x for x in client.rooms if x.get("id") == sel[0]), {})
        lock = r.get("lock") if r.get("private") else None
        if lock == "password":
            pw = tab.ask_string(t("Room password"), t("“{room}” is private. Its password:", room=r.get("name", "?")),
                                show="*", parent=tab.parent)
            if tab.client is not client or not pw:
                return
            if proto.clean_room_password(pw) is None:
                tab.status(t(PW_RULE), error=True)
                return
            tab.call(client.join_room, sel[0], pw)
        elif lock == "code":
            code = tab.ask_string(t("Invite code"), t("The room's invite code (XXXX-XXXX-XXXX):"), parent=tab.parent)
            if tab.client is client and code and code.strip():
                tab.call(client.join_room, sel[0], None, code.strip())
        else:
            tab.call(client.join_room, sel[0])

    def toggle_line(self):
        r = self.mine()
        me = (self.client.me or {}) if self.client else {}
        if r is None:
            return
        back = me.get("id") not in (r.get("line") or ())
        if r.get("mode") == "tables":
            self.tab.call(self.client.room_line, back, then=lambda _r: self.tab.status(
                t("You are available for a free table.") if back else
                t("You are away until you press Available to play.")))
            return
        self.tab.call(self.client.room_line, back, then=lambda _r: self.tab.status(
            t("Back in line: you play when it is your turn.") if back else
            t("You sit out: your turns are skipped until you press Back in line.")))

    def tables(self, r=None):
        r = self.mine() if r is None else r
        if r is None or r.get("mode") != "tables":
            return
        self.close_window()
        self.window = tables_window(self, r)

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

    def bar_guessers(self):
        """The host turns away the networks that typed wrong passwords into the room in the last 10 minutes."""
        tab = self.tab
        tab.call(tab.client.room_bar, then=lambda res: tab.status(
            t("Networks turned away: {count}. They cannot try passwords on this room any more.", count=res[1])))

    def kick(self, pid, name):
        tab = self.tab
        client = tab.client
        room_id = (getattr(client, "my_room", None) or {}).get("id")
        if not tab.ask_yes_no(t("Remove player"), t("Remove {name} from the room? They cannot come back into it.",
                                                     name=name), parent=tab.parent):
            return
        if tab.client is not client or (getattr(client, "my_room", None) or {}).get("id") != room_id:
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
    # Tables refresh from the tab's poll. Clear ownership before the native
    # close button destroys its widgets, so the next poll cannot redraw them.
    w.protocol("WM_DELETE_WINDOW", ui.close_window)
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
         "mode": tk.StringVar(w, value=t(MODE_CHOICES[0][0])),
         "rotation": tk.StringVar(w, value=t(ROTATION_CHOICES[0][0])),
         "access": tk.StringVar(w, value=t(ACCESS_CHOICES[0][0])), "password": tk.StringVar(w, value=""),
         "hidden": tk.IntVar(w, value=0), "training": tk.IntVar(w, value=0),
         "first_to": tk.StringVar(w, value=t("FT{wins}", wins=getattr(getattr(tab, "casual", None), "first_to", 1))),
         "rematch_policy": tk.StringVar(w, value=t(REMATCH_CHOICES[0][0])),
         "auto_skip_after_round": tk.IntVar(w, value=0)}
    rows = (("name", t("Room name (optional):"), None),
            ("size", t("Players:"), [str(n) for n in range(2, top + 1)]),
            ("mode", t("Room format:"), [t(x) for x, _v in MODE_CHOICES]),
            ("rotation", t("Turns (3 or more players):"), [t(x) for x, _v in ROTATION_CHOICES]),
            ("first_to", t("First to:"), [t("FT{wins}", wins=n) for n in proto.CASUAL_FIRST_TO]),
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
    # a training room (docs/ONLINE.md "Training rooms and the health handicap"): only when this launcher's game and
    # the server can play it
    train = ttk.Checkbutton(card, text=t("Training room: endless health, nothing counted"), variable=v["training"],
                            style="Card.TCheckbutton")
    train.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="w", pady=(px(4), 0))
    if not tab.client.training_ok():
        train.configure(state="disabled")
    widgets["training"] = train
    ttk.Label(card, text=t("Rematch rule:"), style="Card.Muted.TLabel").grid(
        row=len(rows) + 3, column=0, sticky="w", pady=px(3), padx=(0, px(10)))
    policy = ttk.Combobox(card, textvariable=v["rematch_policy"], values=[t(x) for x, _v in REMATCH_CHOICES],
                          state="readonly", style="Card.TCombobox", width=34)
    _fit_choices(policy)
    policy.grid(row=len(rows) + 3, column=1, sticky="we", pady=px(3))
    widgets["rematch_policy"] = policy
    skip = ttk.Checkbutton(card, text=t("Skip replays after rounds (both players must agree)"),
                           variable=v["auto_skip_after_round"], style="Card.TCheckbutton")
    skip.grid(row=len(rows) + 4, column=0, columnspan=2, sticky="w", pady=(px(4), 0))
    widgets["auto_skip_after_round"] = skip
    err = ttk.Label(card, text="", style="Card.error.TLabel", wraplength=px(360), justify="left")
    err.grid(row=len(rows) + 5, column=0, columnspan=2, sticky="w", pady=(px(6), 0))

    def sync(*_a):
        many = v["size"].get() not in ("", "2")
        lock = _pick(ACCESS_CHOICES, v["access"].get())
        try:
            tables = _pick(MODE_CHOICES, v["mode"].get()) == "tables"
            tables_ok = hasattr(tab.client, "room_tables_ok") and tab.client.room_tables_ok()
            if not tables_ok or v["training"].get():
                if tables:
                    v["mode"].set(t(MODE_CHOICES[0][0]))
                tables = False
            widgets["mode"].configure(state="readonly" if tables_ok and not v["training"].get() else "disabled")
            widgets["rotation"].configure(state="readonly" if many and not tables else "disabled")
            widgets["password"].configure(state="normal" if lock == "password" else "disabled")
            sets_on = hasattr(tab.client, "casual_sets_ok") and tab.client.casual_sets_ok()
            widgets["first_to"].configure(state="readonly" if sets_on and not v["training"].get() else "disabled")
            supported = _room_rules_supported(tab.client, 3 if many else 2, mode="tables" if tables else "line")
            policy.configure(state="readonly" if supported else "disabled")
            skip.configure(state="normal" if supported and getattr(tab.client, "auto_skip_ok", lambda: False)()
                           else "disabled")
        except tk.TclError:
            pass
    for key in ("size", "access", "training", "mode"):
        v[key].trace_add("write", sync)
    sync()

    def create():
        client = tab.client
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
        training = bool(v["training"].get()) and client.training_ok()
        labels = [t("FT{wins}", wins=n) for n in proto.CASUAL_FIRST_TO]
        chosen = v["first_to"].get()
        first_to = proto.CASUAL_FIRST_TO[labels.index(chosen)] if chosen in labels and not training else 1
        v["password"].set("")                          # (not kept in the window either)

        def done(_room):
            if tab.client is not client:
                return
            if ui.window is w:
                ui.close_window()
            tab.status(t("Room created. Press Copy invite code to see the code you can share.") if lock == "code"
                       else t("Room created."))
        mode = _pick(MODE_CHOICES, v["mode"].get())
        rules = _room_rule_values(client, size, False, _pick(REMATCH_CHOICES, v["rematch_policy"].get()),
                                  v["auto_skip_after_round"].get(), mode=mode)
        create_room = partial(client.create_room, first_to=first_to, mode=mode, **rules)
        tab.call(create_room, name, False, size, rotation, lock, pw, hidden, training, then=done)

    bar = tab.view.body(card)
    bar.grid(row=len(rows) + 6, column=0, columnspan=2, sticky="we", pady=(px(12), 0))
    ttk.Button(bar, text=t("Cancel"), style="Card.TButton", command=ui.close_window).pack(side="right")
    b = ttk.Button(bar, text=t("Create"), style="Card.Accent.TButton", command=create)
    b.pack(side="right", padx=(0, px(8)))
    w.create_button = b
    w.widgets, w.vars, w.err = widgets, v, err
    return w


def tables_window(ui, room):
    """Server-owned table state, with selectors for watching and the host's idle pairs."""
    tab = ui.tab
    client, room_id = tab.client, room.get("id")
    px = tab.view.px
    w, card = _window(ui, t("Room tables"))
    table_var, p1, p2 = (tk.StringVar(w, value="") for _ in range(3))
    summary = ttk.Label(card, text="", style="Card.Small.TLabel", justify="left", wraplength=px(440))
    summary.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, px(8)))
    boxes = {}
    for i, (key, label, var) in enumerate((("table", t("Table:"), table_var),
                                           ("p1", t("Player 1:"), p1), ("p2", t("Player 2:"), p2)), 2):
        ttk.Label(card, text=label, style="Card.Muted.TLabel").grid(row=i, column=0, sticky="w", pady=px(3))
        box = ttk.Combobox(card, textvariable=var, values=[], state="readonly", style="Card.TCombobox", width=28)
        box.grid(row=i, column=1, sticky="we", pady=px(3))
        boxes[key] = box
    err = ttk.Label(card, text="", style="Card.error.TLabel", wraplength=px(440), justify="left")
    err.grid(row=5, column=0, columnspan=2, sticky="w", pady=px(4))
    bar = tab.view.body(card)
    bar.grid(row=6, column=0, columnspan=2, sticky="we", pady=(px(8), 0))
    latest, choices = [room], {}

    def selected():
        return next((s for s in latest[0].get("tables") or () if str(s.get("id")) == table_var.get()), None)

    def pair():
        if tab.client is not client or (getattr(client, "my_room", None) or {}).get("id") != room_id:
            return
        table = selected()
        if table is None:
            err.configure(text=t("Select a table."))
            return
        ids = [choices.get(p1.get()), choices.get(p2.get())]
        if None in ids or ids[0] == ids[1]:
            err.configure(text=t("Select two different available players."))
            return
        def done(_r):
            if ui.window is w:
                ui.close_window()
        tab.call(client.room_pair, table["id"], ids, then=done)

    def watch():
        table = selected()
        if table is not None:
            rid, tid = latest[0]["id"], table["id"]
            ui.close_window()
            tab.spec._watch(room=rid, table=tid)

    b_pair = ttk.Button(bar, text=t("Set pair"), style="Card.TButton", command=pair)
    b_pair.pack(side="left")
    b_watch = ttk.Button(bar, text=t("Watch table"), style="Card.TButton", command=watch)
    b_watch.pack(side="left", padx=(px(8), 0))
    ttk.Button(bar, text=t("Close"), style="Card.TButton", command=ui.close_window).pack(side="right")

    def sync(*_a):
        table = selected()
        idle = table is not None and not table.get("match") and (table.get("set") or {}).get("state") != "active"
        b_pair.configure(state="normal" if ui._host(latest[0]) and idle and len(choices) >= 2 else "disabled")
        spec = getattr(tab, "spec", None)
        busy = getattr(tab, "match", None) is not None or getattr(tab, "set_bar", None) is not None
        drv = getattr(tab, "driver", None)
        busy = busy or (drv is not None and drv.ticket is not None)
        can_watch = spec is not None and spec.ok() and spec.w is None and not busy
        b_watch.configure(state="normal" if table and table.get("watch") and can_watch else "disabled")

    def refresh():
        mine = getattr(ui.client, "my_room", None)
        fresh = mine if mine and mine.get("id") == room.get("id") else next(
            (r for r in getattr(ui.client, "rooms", None) or () if r.get("id") == room.get("id")), None)
        if fresh is None:
            ui.close_window()
            return
        latest[0] = fresh
        summary.configure(text="\n".join(ui.table_summary(fresh, s) for s in fresh.get("tables") or ()))
        values = [str(s["id"]) for s in fresh.get("tables") or ()]
        boxes["table"].configure(values=values)
        if table_var.get() not in values:
            table_var.set(values[0] if values else "")
        choices.clear()
        choices.update((p.get("name", "?"), p["id"]) for p in ui.pair_players(fresh))
        for key, var in (("p1", p1), ("p2", p2)):
            boxes[key].configure(values=list(choices), state="readonly" if ui._host(fresh) else "disabled")
            if var.get() not in choices:
                var.set("")
        sync()

    table_var.trace_add("write", sync)
    w.refresh_tables = refresh
    w.table_var, w.player_vars, w.pair_button, w.watch_button = table_var, (p1, p2), b_pair, b_watch
    w.err = err
    refresh()
    return w


def settings_window(ui, r):
    """The host's window: who can join (a new password, a new invite code, open), hidden, remove a player."""
    tab = ui.tab
    client, room_id = tab.client, r.get("id")
    px = tab.view.px
    w, card = _window(ui, t("Room settings"))
    shown = {None: ACCESS_CHOICES[0][0], "password": ACCESS_CHOICES[1][0], "code": ACCESS_CHOICES[2][0]}
    v = {"access": tk.StringVar(w, value=t(shown.get(r.get("lock"), ACCESS_CHOICES[0][0]))),
         "password": tk.StringVar(w, value=""), "hidden": tk.IntVar(w, value=1 if r.get("hidden") else 0),
         "rematch_policy": tk.StringVar(w, value=t(next((label for label, value in REMATCH_CHOICES
                                                          if value == r.get("rematch_policy")),
                                                         REMATCH_CHOICES[0][0]))),
         "auto_skip_after_round": tk.IntVar(w, value=1 if r.get("auto_skip_after_round") else 0)}
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
    can_rules = (_room_rules_supported(tab.client, r.get("size", 2), r.get("ranked", False), r.get("mode", "line"))
                 and (tab.client.me or {}).get("status") == "room" and r.get("status") != "playing")
    ttk.Label(card, text=t("Rematch rule:"), style="Card.Muted.TLabel").grid(
        row=4, column=0, sticky="w", pady=px(3), padx=(0, px(10)))
    policy = ttk.Combobox(card, textvariable=v["rematch_policy"], values=[t(x) for x, _v in REMATCH_CHOICES],
                          state="readonly" if can_rules else "disabled", style="Card.TCombobox", width=34)
    _fit_choices(policy)
    policy.grid(row=4, column=1, sticky="we", pady=px(3))
    skip = ttk.Checkbutton(card, text=t("Skip replays after rounds (both players must agree)"),
                           variable=v["auto_skip_after_round"], style="Card.TCheckbutton")
    skip.grid(row=5, column=0, columnspan=2, sticky="w", pady=(px(4), 0))
    if not can_rules or not getattr(tab.client, "auto_skip_ok", lambda: False)():
        skip.configure(state="disabled")
    err = ttk.Label(card, text="", style="Card.error.TLabel", wraplength=px(360), justify="left")
    err.grid(row=6, column=0, columnspan=2, sticky="w", pady=(px(4), 0))

    def sync(*_a):
        try:
            pw.configure(state="normal" if _pick(ACCESS_CHOICES, v["access"].get()) == "password" else "disabled")
        except tk.TclError:
            pass
    v["access"].trace_add("write", sync)
    sync()

    def save(new_code=False):
        # The open controls still belong to their original room and session.
        if tab.client is not client or (getattr(client, "my_room", None) or {}).get("id") != room_id:
            return
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
            if ui.window is w:
                err.configure(text="")
            tab.status(t("Room settings saved."))
        current = tab.client.my_room or {}
        editable = can_rules and (tab.client.me or {}).get("status") == "room" and current.get("status") != "playing"
        wanted = _room_rule_values(tab.client, current.get("size", 2), current.get("ranked", False),
                                   _pick(REMATCH_CHOICES, v["rematch_policy"].get()),
                                   v["auto_skip_after_round"].get(), mode=current.get("mode", "line")) if editable else {}
        rules = {key: value for key, value in wanted.items() if value != current.get(key, False if key ==
                 "auto_skip_after_round" else "both_confirm")}
        _save_settings(tab, lock, p, hidden, rules, done)

    bar = tab.view.body(card)
    bar.grid(row=7, column=0, columnspan=2, sticky="we", pady=(px(10), 0))
    b_save = ttk.Button(bar, text=t("Save"), style="Card.Accent.TButton", command=save)
    b_save.pack(side="left")
    b_code = ttk.Button(bar, text=t("New invite code"), style="Card.TButton", command=lambda: save(True))
    b_code.pack(side="left", padx=(px(8), 0))

    me = (tab.client.me or {}).get("id")
    others = [p for p in r.get("players") or () if p.get("id") != me]
    ttk.Label(card, text=t("Players in the room:"), style="Card.Muted.TLabel").grid(
        row=8, column=0, columnspan=2, sticky="w", pady=(px(14), px(4)))
    lb = tk.Listbox(card, height=max(3, min(8, len(others))), width=30, activestyle="none", exportselection=False)
    for p in others:
        lb.insert("end", p.get("name", "?"))
    lb.grid(row=9, column=0, columnspan=2, sticky="we")

    def kick():
        if tab.client is not client or (getattr(client, "my_room", None) or {}).get("id") != room_id:
            return
        sel = lb.curselection()
        if sel:
            p = others[sel[0]]
            ui.kick(p.get("id"), p.get("name", "?"))
    b_kick = ttk.Button(card, text=t("Remove player"), style="Card.TButton", command=kick)
    b_kick.grid(row=10, column=0, sticky="w", pady=(px(8), 0))
    ttk.Button(card, text=t("Close"), style="Card.TButton", command=ui.close_window).grid(
        row=10, column=1, sticky="e", pady=(px(8), 0))
    g = r.get("guesses")
    b_bar = None
    if isinstance(g, dict):                       # (a password room on a server that counts wrong guesses)
        def bar_guessers():
            if tab.client is not client or (getattr(client, "my_room", None) or {}).get("id") != room_id:
                return
            ui.bar_guessers()

        ttk.Label(card, text=t("Wrong passwords in the last 10 minutes: {count} (networks: {networks})",
                               count=int(g.get("wrong") or 0), networks=int(g.get("networks") or 0)),
                  style="Card.Muted.TLabel", wraplength=px(360), justify="left").grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(px(14), px(4)))
        b_bar = ttk.Button(card, text=t("Turn away the guessers"), style="Card.TButton", command=bar_guessers,
                           state="normal" if g.get("wrong") else "disabled")
        b_bar.grid(row=12, column=0, sticky="w")
    w.vars, w.err, w.players, w.save_button, w.code_button, w.kick_button = v, err, lb, b_save, b_code, b_kick
    w.bar_button = b_bar
    w.widgets = {"rematch_policy": policy, "auto_skip_after_round": skip}
    return w
