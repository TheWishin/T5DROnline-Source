"""Challenges and the lists around them (1.1.9, players' wishes; docs/ONLINE.md "Challenges").

* Your open challenges: under the player list, each with its input delay and a Cancel button; the player's row is
  in the accent colour. Sending, taking back, a no, the end after 30 s, and the automatic withdrawal all write a short line
  in the chat -- on both sides.
* Several challenges at once (a 1.1.9 server: up to five, to different players): the first one accepted starts the
  match and the server withdraws the others; both sides of each see it.
* The input delay of a casual challenge: the challenger picks Auto (from the ping; the box shows what Auto gives for
  the selected player) or 0 / 1 / 2 frames; the challenged player sees it on the card before accepting, and the match
  (and its rematches) use it on both PCs.
* The player list sorts by ping, rank, name or status (click the column's heading; the choice is kept in
  online.json); players you cannot play right now -- in a match, another version, no connection to the lobby
  server's UDP -- come below the others, under a line of their own.
* The leaderboard: ranked and casual wins and losses in their own columns (a 1.1.9 server's rows: ranked_wins,
  ranked_losses, casual_wins, casual_losses; an older server: the one Record column as before), every column
  sortable by its heading.
"""
import tkinter as tk
from tkinter import ttk

from .i18n import N_, t

DELAY_CHOICES = ("auto", "0", "1", "2")              # the Settings tab's choices (server: CHALLENGE_DELAYS)
PLAYER_SORTS = {"player": "name", "rank": "rank", "status": "status", "ping": "ping"}    # heading -> sort key
STATUS_ORDER = {"idle": 0, "queue": 1, "room": 2, "match": 3, "playing": 4}
AWAY = "sep:away"                                    # the line between the players you can and cannot play now
BOARD_SPLIT = ("ranked_wins", "ranked_losses", "casual_wins", "casual_losses")
BOARD_OLD_COLS = ("place", "player", "rank", "rating", "record", "main")
BOARD_NEW_COLS = ("place", "player", "rank", "rating", "rw", "rl", "cw", "cl", "main")
BOARD_COLS = ("place", "player", "rank", "rating", "record", "rw", "rl", "cw", "cl", "main")
BOARD_NUMERIC = {"place", "rating", "rw", "rl", "cw", "cl"}
END_TEXT_OUT = {"declined": N_("{name} declined your challenge."),
                "cancelled": N_("You took back your challenge to {name}."),
                "expired": N_("Your challenge to {name} was not answered in time."),
                "withdrawn": N_("Your challenge to {name} was withdrawn: a match started."),
                "accepted": N_("{name} accepted your challenge.")}
END_TEXT_IN = {"cancelled": N_("{name} took back the challenge."),
               "expired": N_("The challenge from {name} ran out."),
               "withdrawn": N_("The challenge from {name} was withdrawn: a match started.")}


def auto_delay(ms):
    """The input delay the games pick by themselves for a round trip of `ms` (docs/NETPLAY.md "Input delay": 1 frame up
    to 60 ms, 2 above; the lobby server's default T5L_PING_DELAYS: 3 above 150 ms, 4 above 250). None: not known."""
    if not isinstance(ms, (int, float)):
        return None
    if ms > 250:
        return 4
    if ms > 150:
        return 3
    return 1 if ms <= 60 else 2


def delay_text(d):
    """A challenge's `delay` ({"frames", "auto"}) as "2 (auto)" / "1"; '' when there is none."""
    if not isinstance(d, dict):
        return ""
    n = d.get("frames")
    if n is None:
        return t("auto") if d.get("auto") else ""
    return f"{n} ({t('auto')})" if d.get("auto") else str(n)


class ChallengesUI:
    def __init__(self, tab):
        self.tab = tab
        self.out = {}          # challenge id -> {"pid", "name", "delay"}: this player's open challenges
        self.incoming = {}     # challenge id -> the challenger's name (for the chat line when it ends)
        self.ended = {}        # challenge id -> its end state, when that came before the reply to the challenge
        cfg = tab.cfg
        self.delay = cfg.get("challenge_delay") if cfg.get("challenge_delay") in DELAY_CHOICES else "auto"
        s = cfg.get("players_sort")
        self.sort = (s[0], bool(s[1])) if isinstance(s, list) and len(s) == 2 and s[0] in PLAYER_SORTS.values() \
            else ("ping", False)
        b = cfg.get("board_sort")
        self.board_sort = (b[0], bool(b[1])) if isinstance(b, list) and len(b) == 2 and b[0] in BOARD_COLS \
            else ("place", False)
        self.delay_var = tk.StringVar(value="")
        self.delay_cb = None
        self.box = None         # the open challenges under the player list
        self.rows = None
        self._auto_for = None   # the auto value the box shows (for the selected player)

    @property
    def client(self):
        return self.tab.client

    def multi_ok(self):
        c = self.client
        return c is not None and hasattr(c, "multi_challenge_ok") and c.multi_challenge_ok()

    # ------------------------------------------------------------------ widgets (tk_views' lobby page)
    def build_tools(self, tools, px):
        """The input delay box left of Challenge (hidden on a server that does not take it)."""
        self.delay_cb = ttk.Combobox(tools, textvariable=self.delay_var, state="readonly", width=15,
                                     style="Card.TCombobox")
        self.delay_cb.bind("<<ComboboxSelected>>", lambda _e: self._delay_chosen())
        self.delay_cb.pack(side="left", padx=(0, px(6)))
        self._px = px
        self._fill_delay()
        return self.delay_cb

    def build_open(self, parent, row, px):
        """Your open challenges (under the player list): a line each with Cancel; hidden while there are none."""
        self.box = ttk.Frame(parent, style="CardBody.TFrame")
        self.box.grid(row=row, column=0, sticky="we", pady=(px(6), 0))
        self.box.columnconfigure(0, weight=1)
        ttk.Label(self.box, text=t("Your open challenges").upper(), style="Card.Caps.TLabel").grid(
            row=0, column=0, sticky="w")
        self.rows = ttk.Frame(self.box, style="CardBody.TFrame")
        self.rows.grid(row=1, column=0, sticky="we")
        self.rows.columnconfigure(0, weight=1)
        self.box.grid_remove()
        return self.box

    def _choice_labels(self):
        auto = self._auto_for
        first = t("Delay: auto") + (f" ({auto})" if auto is not None else "")
        return [first] + [t("Delay: {frames}", frames=n) for n in DELAY_CHOICES[1:]]

    def _fill_delay(self):
        if self.delay_cb is None:
            return
        labels = self._choice_labels()
        self.delay_cb.configure(values=labels)
        self.delay_var.set(labels[DELAY_CHOICES.index(self.delay)])

    def _delay_chosen(self):
        labels = list(self.delay_cb.cget("values"))
        v = self.delay_var.get()
        self.delay = DELAY_CHOICES[labels.index(v)] if v in labels else "auto"
        self.tab.cfg["challenge_delay"] = self.delay
        self.tab._save_cfg()

    def selection_changed(self):
        """A player was selected: the box's Auto shows what auto gives with them."""
        sel = self.tab.tv_players.selection()
        if sel and sel[0] == AWAY:
            self.tab.tv_players.selection_remove(AWAY)
            return
        ms = None
        if sel:
            ms = (getattr(self.tab, "_list_rtt", {}) or {}).get(sel[0], (None, False))[0]
        auto = auto_delay(ms)
        if auto != self._auto_for:
            self._auto_for = auto
            self._fill_delay()

    def refresh(self):
        """After a login / logout and every change of the tab's buttons: the delay box only where it counts."""
        if self.delay_cb is None:
            return
        on = self.multi_ok()
        if on and not self.delay_cb.winfo_manager():
            self.delay_cb.pack(side="left", padx=(0, self._px(6)), before=self.tab.actions["challenge"])
        elif not on and self.delay_cb.winfo_manager():
            self.delay_cb.pack_forget()
        self.delay_cb.configure(state="readonly" if str(self.tab.actions["challenge"].cget("state")) == "normal"
                                else "disabled")

    def _show_open(self):
        if self.rows is None:
            return
        for w in self.rows.winfo_children():
            w.destroy()
        px = self._px
        for i, (cid, c) in enumerate(self.out.items()):
            text = c["name"]
            d = delay_text(c.get("delay"))
            if d:
                text += "  --  " + t("input delay {delay}", delay=d)
            ttk.Label(self.rows, text=text, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=(px(3), 0))
            ttk.Button(self.rows, text=t("Cancel"), style="Card.Small.TButton",
                       command=lambda cid=cid: self.cancel(cid)).grid(row=i, column=1, sticky="e", pady=(px(3), 0))
        if self.out:
            self.box.grid()
        else:
            self.box.grid_remove()

    # ------------------------------------------------------------------ challenges
    def send(self):
        tab = self.tab
        sel = tab.tv_players.selection()
        me = (tab.client.me or {}) if tab.client else {}
        if not sel or sel[0] == AWAY or sel[0] == me.get("id"):
            tab.status(t("Select an opponent in the list first."))
            return
        pid = sel[0]
        if any(c["pid"] == pid for c in self.out.values()):
            tab.status(t("You challenged that player already: your open challenges are under the list."))
            return
        name = self._name_of(pid)
        delay = None if self.delay == "auto" or not self.multi_ok() else int(self.delay)
        tab.call(tab.client.send_challenge, pid, delay, then=lambda r: self._sent(r, pid, name))

    def _name_of(self, pid):
        for p in (getattr(self.tab, "_last_lobby", None) or {}).get("players", []):
            if p.get("id") == pid:
                return p.get("name") or "?"
        return "?"

    def _sent(self, r, pid, name):
        cid = r.get("challenge") if isinstance(r, dict) else r
        name = ((r.get("to") or {}).get("name") if isinstance(r, dict) else None) or name
        delay = r.get("delay") if isinstance(r, dict) else None
        d = delay_text(delay)
        self.tab.chat_line(t("You challenged {name}.", name=name) + (" " + t("Input delay: {delay}.", delay=d)
                                                                      if d else ""))
        self.tab.status(t("Challenge sent."))
        state = self.ended.pop(cid, None)
        if state is not None:                 # (answered before the reply was read)
            self._ended_out(state, name)
            return
        self.out[cid] = {"pid": pid, "name": name, "delay": delay}
        self._show_open()
        self.tab.relist()

    def cancel(self, cid):
        if cid in self.out and self.client is not None:
            self.tab.call(self.client.cancel_challenge, cid)

    def _ended_out(self, state, name):
        text = END_TEXT_OUT.get(state)
        if text:
            self.tab.chat_line(t(text, name=name))

    def on_event(self, ev):
        """Every lobby event, before the tab handles it."""
        kind = ev.get("t")
        if kind == "challenged":
            name = (ev.get("from") or {}).get("name") or "?"
            self.incoming[ev.get("challenge")] = name
            d = delay_text(ev.get("delay"))
            self.tab.chat_line(t("{name} challenges you.", name=name)
                               + (" " + t("Input delay: {delay}.", delay=d) if d else ""))
        elif kind == "challenge_update":
            cid, state = ev.get("challenge"), ev.get("state")
            if cid in self.out:
                c = self.out.pop(cid)
                self._ended_out(state, c["name"])
                self._show_open()
                self.tab.relist()
            elif cid in self.incoming:
                name = self.incoming.pop(cid)
                text = END_TEXT_IN.get(state)
                if text:
                    self.tab.chat_line(t(text, name=name))
            else:
                self.ended[cid] = state
                if len(self.ended) > 64:
                    self.ended.pop(next(iter(self.ended)))

    def reset(self):
        """Logged out / disconnected: nothing is open any more."""
        self.out.clear()
        self.incoming.clear()
        self.ended.clear()
        self._show_open()

    def challenged_ids(self):
        return {c["pid"] for c in self.out.values()}

    def card_line(self, ev):
        """The challenge card's line about the input delay (the challenged player, before the answer); '' if none."""
        d = ev.get("delay") if isinstance(ev, dict) else None
        if not isinstance(d, dict) or d.get("frames") is None:
            return ""
        if d.get("auto"):
            return t("Input delay {frames} (auto, from the ping)", frames=d["frames"])
        return t("Input delay {frames} (chosen by the challenger)", frames=d["frames"])

    # ------------------------------------------------------------------ the player list
    def order_players(self, entries, me_id):
        """entries: [(iid, values, image, tags, player, ms)] -> the list's rows: you first, then the players you can
        play now in the chosen order, then a line and the others (in the same order)."""
        key, desc = self.sort

        def k(e):
            p, ms = e[4], e[5]
            if key == "ping":
                return (ms is None, ms if ms is not None else 0.0)
            if key == "rank":
                return (bool(p.get("guest")), -(p.get("rating") or 0))
            if key == "status":
                return (STATUS_ORDER.get(p.get("status"), 9), str(p.get("name", "")).casefold())
            return (str(p.get("name", "")).casefold(),)
        mine = [e for e in entries if e[0] == me_id]
        rest = [e for e in entries if e[0] != me_id]
        rest.sort(key=k, reverse=desc)
        now = [e for e in rest if "away" not in e[3]]
        later = [e for e in rest if "away" in e[3]]
        rows = [e[:4] for e in mine + now]
        if later:
            n = len(entries[0][1]) if entries else 7
            rows.append((AWAY, (t("Unavailable"),) + ("",) * (n - 1), None, ("sep",)))
            rows += [e[:4] for e in later]
        return rows

    @staticmethod
    def playable(p, me, mine_build):
        """Can this player be played right now (challenge, invite, their room)? Not: in a match, another version,
        nothing known of their connection to the lobby server (no UDP: unreachable)."""
        if me and p.get("id") == me.get("id"):
            return True
        if p.get("build") != mine_build:
            return False
        if p.get("status") in ("match", "playing"):
            return False
        return not (p.get("rtt") is None and not p.get("relays"))

    def bind_player_sort(self, tv):
        for col, key in PLAYER_SORTS.items():
            tv.heading(col, command=lambda key=key: self._sort_players(key))
        self._mark(tv, {v: k for k, v in PLAYER_SORTS.items()}[self.sort[0]], self.sort[1])

    def _sort_players(self, key):
        desc = (not self.sort[1]) if self.sort[0] == key else (key == "rank")
        self.sort = (key, desc)
        self.tab.cfg["players_sort"] = [key, desc]
        self.tab._save_cfg()
        self._mark(self.tab.tv_players, {v: k for k, v in PLAYER_SORTS.items()}[key], desc)
        self.tab.relist()

    def _mark(self, tv, col, desc):
        """The sorted column's heading gets an arrow; the others none."""
        from .tk_views import HEADINGS
        for c in tv["columns"]:
            text = t(HEADINGS.get(c, c)).upper()
            tv.heading(c, text=text + ((" ▼" if desc else " ▲") if c == col else ""))

    # ------------------------------------------------------------------ the leaderboard
    def bind_board_sort(self, tv):
        for col in BOARD_COLS:
            if col != "record":
                tv.heading(col, command=lambda col=col: self._sort_board(col))
        self._mark(tv, self.board_sort[0], self.board_sort[1])

    def _sort_board(self, col):
        desc = (not self.board_sort[1]) if self.board_sort[0] == col else col in BOARD_NUMERIC - {"place"}
        self.board_sort = (col, desc)
        self.tab.cfg["board_sort"] = [col, desc]
        self.tab._save_cfg()
        self._mark(self.tab.tv_board, col, desc)
        rows = getattr(self.tab, "_last_board", None)
        if rows is not None:
            self.tab._show_board(rows)

    def board_rows(self, rows):
        """The leaderboard's rows in the chosen order, and the columns to show: the split ones when the server sends
        them (BOARD_SPLIT), else the old Record column."""
        split = bool(rows) and all(all(isinstance(r.get(k), int) for k in BOARD_SPLIT) for r in rows)
        col, desc = self.board_sort
        field = {"place": "place", "player": "name", "rating": "rating", "rank": "rating", "rw": "ranked_wins",
                 "rl": "ranked_losses", "cw": "casual_wins", "cl": "casual_losses", "main": "main"}.get(col, "place")
        if not split and field.startswith(("ranked_", "casual_")):
            field = "place"

        def k(r):
            v = r.get(field)
            if isinstance(v, (int, float)):
                return (0, v, r.get("place", 0))
            return (0 if v else 1, str(v or "").casefold(), r.get("place", 0))
        return sorted(rows, key=k, reverse=desc), (BOARD_NEW_COLS if split else BOARD_OLD_COLS)
