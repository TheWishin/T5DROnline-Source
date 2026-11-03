"""The Online tab's spectating (docs/SPECTATE.md): the Watch buttons (a friend in a match, a room's match), the
Spectating card in the tab's stage and the spectator's game; the players' "N watching" line.

The tab (tk_tab.py) owns one Spectating and calls it from a few places: building the friends and rooms lists
(watch buttons), building the stage card (the Spectating card), the poll, its events, its action states.
"""
import json
import os
import time
import tkinter as tk
from tkinter import ttk

from . import auto_spectate, spectate, theme
from .i18n import t
from .theme import C

def end_text(reason):
    """Why no more of the match comes (the server's spec_end reasons), for the Spectating card."""
    if reason == "over":
        return t("The live match is over.")
    if reason == "not_allowed":
        return t("The players turned spectators off.")
    if reason == "too_long":
        return t("This session is too long to watch from its start.")
    if reason == "your_match":
        return t("Your own match is starting.")
    if reason == "damaged":
        return t("The match data was damaged.")
    if reason == "left":
        return t("You stopped watching.")
    if reason == "bumped":
        return t("A friend of the players took your place: the match has as many spectators as it can take.")
    return t("The match data stopped coming.")      # stopped, unavailable, anything else


class Spectating:
    def __init__(self, tab):
        self.tab = tab
        self.w = None            # {stream, players, ranked, room, began, game, result, status, state, end, t0, delay}
        self.count = None        # spectators of this player's own match (the server's `spectators`)
        self.card = None
        self._sig = None
        self._prefs = None       # the (allow, ranked) last sent
        self._generation = 0
        self._pending = None     # one worker request; a late answer never owns a game
        self._pending_end = None
        self._auto = auto_spectate.Policy()
        self._before_ev = None

    # ------------------------------------------------------------------ settings
    def prefs(self):
        s = getattr(getattr(self.tab, "app", None), "settings", None) or {}
        try:
            return bool(s.get("spectators", True)), bool(s.get("spectators_ranked", False))
        except AttributeError:
            return True, False

    def client_kw(self):
        return {"spectate": True}

    def new_client(self, c):
        """A new LobbyClient (before it connects): the privacy setting goes with every login."""
        if self._pending is not None or self.w is not None:
            self._preempt("stopped")
            self.w = None
        self._prefs = self.prefs()
        c.set_spectate_prefs(*self._prefs)

    def _check_prefs(self):
        c = self.tab.client
        p = self.prefs()
        if c is not None and p != self._prefs and hasattr(c, "set_spectate_prefs"):
            self._prefs = p
            self.tab.call(c.set_spectate_prefs, *p)

    @property
    def active(self):
        return self.w is not None

    def ok(self):
        c = self.tab.client
        has = getattr(c, "has_spectate", None)
        return bool(c is not None and getattr(c, "me", None) and callable(has) and has())

    # ------------------------------------------------------------------ UI pieces
    def friend_button(self, row, px):
        """The friends list's Watch, at the left of the row below the list."""
        b = ttk.Button(row, text=t("Watch"), style="Card.Small.TButton", state="disabled", command=self.watch_friend)
        b.grid(row=0, column=0, sticky="nw", padx=(0, px(10)))
        return b

    def build_card(self, view, card):
        """The Spectating card (the stage card's "watch" stage)."""
        px = view.px
        f = view.body(card)
        f.columnconfigure(0, weight=1)
        head = view.body(f)
        head.grid(row=0, column=0, sticky="we")
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text=t("Spectating").upper(), style="Card.Caps.TLabel").grid(row=0, column=0, sticky="w")
        self.pill = ttk.Label(head, text=t("CASUAL"), style="Card.Pill.TLabel")
        self.pill.grid(row=0, column=1, sticky="w", padx=(px(8), 0))
        self.dot = tk.Canvas(head, width=px(10), height=px(10), bg=C["surface"], highlightthickness=0, takefocus=0)
        self.dot.grid(row=0, column=2, sticky="e", padx=(0, px(6)))
        self.state_label = ttk.Label(head, text="", style="Card.Bold.TLabel")
        self.state_label.grid(row=0, column=3, sticky="e")
        self.names = ttk.Label(f, text="", style="Card.H2.TLabel")
        self.names.grid(row=1, column=0, sticky="w", pady=(px(10), 0))
        self.detail = view.wrap(ttk.Label(f, text="", style="Card.Muted.TLabel", justify="left"), card, 40)
        self.detail.grid(row=2, column=0, sticky="w", pady=(px(4), 0))
        self.button = ttk.Button(f, text=t("Stop watching"), style="Card.TButton", command=self.stop)
        self.button.grid(row=3, column=0, sticky="w", pady=(px(12), 0))
        self.card = f
        self.view = view
        return f

    def update_card(self):
        w = self.w
        if w is None or self.card is None:
            return
        sig = (w["state"], w.get("end"), w.get("delay"), w.get("match"), w.get("spectators"))
        if sig == self._sig:
            return
        self._sig = sig
        names = [p.get("name", "?") for p in w.get("players") or ()] + ["?", "?"]
        self.names.configure(text=t("{p1} vs {p2}", p1=names[0], p2=names[1]))
        ranked = w.get("ranked")
        self.pill.configure(text=t("TOURNAMENT") if w.get("tournament") else t("RANKED") if ranked else t("CASUAL"),
                            style="Card.PillAccent.TLabel" if ranked or w.get("tournament") else "Card.Pill.TLabel")
        st = w["state"]
        if st == "waiting":
            text, col = t("Waiting for the match data..."), C["warn"]
        elif st == "starting":
            text, col = t("Starting the game..."), C["warn"]
        elif st == "playing":
            text, col = t("Watching"), C["ok"]
        else:
            text, col = t("Match over"), C["muted"]
        self.state_label.configure(text=text)
        self.dot.delete("all")
        d = self.view.px(10)
        self.dot.create_oval(1, 1, d - 1, d - 1, fill=col, outline="")
        lines = []
        if st == "playing" and isinstance(w.get("delay"), (int, float)) and w["delay"] >= 0:
            lines.append(t("About {seconds} s behind the live match.", seconds=f"{w['delay']:.0f}"))
        elif st in ("waiting", "starting"):
            lines.append(t("It plays from the start of the players' session, a few seconds behind."))
        if w.get("end"):
            lines.append(end_text(w["end"]))
        self.detail.configure(text="  ".join(lines))
        self.button.configure(text=t("Close") if st == "over" else t("Stop watching"))

    def set_actions(self, busy=None):
        """The Watch buttons' states (the tab's _set_actions / _set_friend_actions)."""
        tab = self.tab
        if busy is None:
            busy = tab.match is not None or (tab.driver is not None and tab.driver.ticket is not None) or \
                tab.set_bar is not None
        ok = self.ok() and not busy and self.w is None and self._pending is None
        fb = (getattr(tab, "friend_actions", None) or {}).get("watch")
        if fb is not None:
            f = tab._selected_friend() if ok else None
            try:
                fb.configure(state="normal" if f is not None and f.get("watch") else "disabled")
            except tk.TclError:
                pass
        tours = getattr(tab, "tours", None)
        tb = ((getattr(tours, "page", None) or {}).get("watch")) if tours is not None else None
        if tb is not None:                         # the Tournaments page (tk_tour.py): the selected set's game
            on = ok and bool(tours.watchable_set())
            try:
                tb.configure(state="normal" if on else "disabled")
            except tk.TclError:
                pass
        rb = (getattr(tab, "actions", None) or {}).get("watch_room")
        if rb is not None:
            r = self._selected_room() if ok else None
            me = (tab.client.me or {}).get("id") if tab.client else None
            if r is not None and r is getattr(tab.client, "my_room", None):
                on = bool(r.get("watch"))                # this player's own room: the server says (members only)
            else:
                on = r is not None and r.get("watch") and me not in (r.get("members") or ())
            try:
                rb.configure(state="normal" if on else "disabled")
            except tk.TclError:
                pass

    def _selected_room(self):
        """The room selected in the list -- or, with none selected, this player's own room (a hidden one is in no
        list; its members watch its match from there: docs/ONLINE.md "Rooms")."""
        tv = getattr(self.tab, "tv_rooms", None)
        sel = tv.selection() if tv is not None else ()
        mine = getattr(self.tab.client, "my_room", None)
        if mine is not None and (self.tab.client.me or {}).get("status") not in ("room", "match", "playing"):
            mine = None
        if not sel or (mine is not None and sel[0] == mine.get("id")):
            return mine
        for r in getattr(self.tab.client, "rooms", None) or ():
            if r.get("id") == sel[0]:
                return r
        return None

    # ------------------------------------------------------------------ watching
    def watch_friend(self):
        f = self.tab._selected_friend()
        if f is not None:
            self._watch(name=f["name"])

    def watch_room(self):
        r = self._selected_room()
        if r is not None:
            if r.get("mode") == "tables":
                self.tab.rooms_ui.tables(r)
            else:
                self._watch(room=r["id"])

    def watch_tour(self, tid, sid):
        """The Tournaments page's Watch: the game of bracket set `sid` being played (tk_tour.py)."""
        if tid and sid:
            self._watch(tournament=tid, set_id=sid)

    def _busy(self):
        """Recheck both Tk state and the client's already received match before every boot."""
        tab, c = self.tab, self.tab.client
        drv = tab.driver
        room = getattr(c, "my_room", None) or {}
        uid = (getattr(c, "me", None) or {}).get("id")
        return bool(c is None or getattr(c, "match", None) or
                    getattr(tab, "match", None) or (drv is not None and drv.ticket is not None) or
                    any(getattr(tab, k, None) is not None for k in
                        ("challenge", "invite", "outgoing_invite", "set_bar", "rematch_bar", "ready_deadline")) or
                    getattr(tab, "ready_sent", False) or
                    getattr(getattr(tab, "chal", None), "out", None) or
                    getattr(getattr(tab, "chal", None), "incoming", None) or
                    getattr(getattr(tab, "tours", None), "call", None) is not None or
                    uid in (room.get("playing") or ()) or
                    uid in ((room.get("next") or {}).get("players") or ()) or
                    any(uid in ((table.get("next") or {}).get("players") or ())
                        for table in room.get("tables") or ()) or
                    ((getattr(c, "me", None) or {}).get("status") in ("match", "playing")))

    def _cancel_client(self, c):
        if c is None:
            return
        cancel = getattr(c, "cancel_watch", None)
        if cancel is not None:
            cancel()             # synchronous generation barrier; cleanup is ordered on the client loop
        else:
            self.tab.call(c.unwatch)

    def _stop_owned_game(self, w):
        g = w.get("game") if w is not None else None
        drv = self.tab.driver
        # Never stop a process the match driver owns, even if stale UI state refers to it.
        if g is not None and (drv is None or g is not getattr(drv, "game", None)) and g.running():
            g.stop()

    def _watch(self, name=None, room=None, tournament=None, set_id=None, table=None, automatic=False):
        tab = self.tab
        if self.w is not None or self._pending is not None or not self.ok() or self._busy():
            return
        g = getattr(tab.app, "game", None)
        drv = tab.driver
        if (g is not None and g.running()) or (drv is not None and drv.game_running()):
            if not automatic:
                tab.status(t("Close the running game first (Stop game on the Play tab)."), error=True)
            return
        c = tab.client
        self._generation += 1
        generation = self._generation
        self._pending = (generation, c, automatic)
        self._pending_end = None

        def done(r):
            if self._pending != (generation, c, automatic):
                return
            self._pending = None
            if c is not tab.client:
                self._cancel_client(c)
                return
            if not r or self._busy() or not self.ok() or (automatic and
                    (not tab.app.settings.get("auto_spectate", False) or not auto_spectate.idle(tab))):
                self._cancel_client(c)
                return
            self.w = {"stream": r["stream"], "match": r.get("match"), "players": r.get("players"),
                      "ranked": r.get("ranked"), "room": r.get("room"), "began": r.get("began"),
                      "tournament": r.get("tournament"),
                      "spectators": r.get("spectators"), "state": "waiting", "game": None, "t0": time.monotonic(),
                      "end": None, "delay": None, "client": c, "automatic": automatic}
            current = getattr(c, "spec_watch", None) or {}
            if current.get("stream") != r["stream"]:
                ended = self._pending_end
                reason = ended[2] if ended and ended[:2] == (generation, r["stream"]) else "stopped"
                self.w["state"], self.w["end"] = "over", reason
                self._auto.pause()
                self._cancel_client(c)
                tab._set_actions()
                return                    # an END/privacy event can arrive before the worker callback
            names = [p.get("name", "?") for p in r.get("players") or ()] + ["?", "?"]
            tab.status(t("Watching {p1} vs {p2}.", p1=names[0], p2=names[1]))
            # the game starts now: it boots while the players' games load the fight, and waits for the data
            path = (getattr(tab.client, "spec_watch", None) or {}).get("path")
            if path and self.w["stream"] == (tab.client.spec_watch or {}).get("stream"):
                self._start_game(path)
            tab._set_actions()

        def failed():
            if self._pending == (generation, c, automatic):
                self._pending = None
                self._cancel_client(c)

        args = (name, room, tournament, set_id)
        if hasattr(c, "spec_generation"):
            args += (table, c.spec_generation)
        elif table is not None:
            args += (table,)
        tab.call(c.watch, *args, then=done, fail=failed)

    def _start_game(self, path):
        tab, w = self.tab, self.w
        if w is None or w.get("client") is not tab.client or self._busy():
            self._preempt("your_match")
            return
        drv = tab.driver
        g = getattr(tab.app, "game", None)
        if (g is not None and g.running()) or (drv is not None and drv.game_running()):
            self._preempt("stopped")
            return                       # start_game otherwise returns that unrelated process unchanged
        out = getattr(tab.app.settings, "out_dir", os.getcwd())
        d = os.path.join(out, "logs", "online")
        os.makedirs(d, exist_ok=True)
        w["result"] = os.path.join(d, "watch-verdict.json")
        w["status"] = os.path.join(d, "watch-status.json")
        for p in (w["result"], w["status"]):
            try:
                os.remove(p)
            except OSError:
                pass
        g = tab.app.start_game(spectate.watch_env(path, w["result"], w["status"]))
        if g is None:
            w["state"], w["end"] = "over", "stopped"
            self._cancel_client(w.get("client"))
            return
        w["game"] = g
        w["state"] = "starting"

    def stop(self):
        self._auto.pause()
        self._preempt("left")
        self.w = None
        self._sig = None
        self.tab._set_actions()

    def _preempt(self, reason):
        pending, w = self._pending, self.w
        self._generation += 1
        self._pending = None
        c = pending[1] if pending is not None else w.get("client") if w is not None else None
        self._cancel_client(c)
        self._stop_owned_game(w)
        if w is not None:
            w["state"], w["end"] = "over", reason

    def before_event(self, ev):
        """Called before MatchDriver sees an event: its own game must get the process first."""
        if self._before_ev is ev:
            return
        self._before_ev = ev
        kind = ev.get("t")
        if kind in ("match_found", "match_reveal", "match_start", "challenged", "invited", "tour_call",
                    "disconnected", "reconnecting", "kicked"):
            self._auto.pause()
            if self._pending is not None or self.w is not None:
                self._preempt("stopped" if kind in ("disconnected", "reconnecting", "kicked") else "your_match")

    # ------------------------------------------------------------------ the tab's poll and events
    def on_event(self, ev):
        self.before_event(ev)
        kind = ev.get("t")
        tab = self.tab
        if kind == "spectators":
            n = int(ev.get("count") or 0)
            if n != self.count:
                self.count = n
                if n:
                    tab.status(t("Spectators watching your match: {count}", count=n))
            return True
        w = self.w
        if kind == "spec_ready":
            if w is not None and ev.get("stream") == w["stream"] and w["game"] is None and w["state"] == "waiting":
                self._start_game(ev["path"])
            return True
        if kind == "spec_end":
            if w is None and self._pending is not None:
                self._pending_end = (self._pending[0], ev.get("stream"), ev.get("reason") or "over")
            if w is not None and ev.get("stream") == w["stream"]:
                self._auto.pause()
                w["end"] = ev.get("reason") or "over"
                if w["game"] is None:
                    w["state"] = "over"           # (the game never started: nothing to watch)
                elif w["end"] in ("your_match", "not_allowed", "bumped") or \
                        (w["state"] == "starting" and not ev.get("ready")):
                    # privacy and the player's own match: at once; a game still waiting for a first fight
                    # that never came has nothing to show (with a fight in the file it plays to its end)
                    self._stop_owned_game(w)
                    w["state"] = "over"
            return True
        if kind == "match_start":
            self.count = None
        return False

    def poll(self):
        self._check_prefs()
        w = self.w
        enabled = bool(self.tab.app.settings.get("auto_spectate", False))
        if self._pending is not None and self._pending[2] and not enabled:
            self._auto.pause()
            self._preempt("left")
        if self._busy() and (self._pending is not None or (w is not None and w["state"] != "over")):
            self._preempt("your_match")
            w = self.w
        if w is not None and w.get("automatic") and not enabled:
            self.stop()
            w = None
        if w is not None and w.get("automatic") and w["state"] == "over":
            self.w = w = None
        if w is None:
            if self._pending is None:
                target = self._auto.due(self.tab)
                if target:
                    self._auto.attempted()
                    self._watch(**target, automatic=True)
            return
        g = w.get("game")
        if g is not None and w["state"] in ("starting", "playing"):
            if not g.running():
                w["state"] = "over"
                if not w.get("end"):
                    try:
                        with open(w["result"], encoding="utf-8") as f:
                            v = json.load(f)
                        w["end"] = "over" if v.get("stream_end") or v.get("end") else "stopped"
                    except (OSError, ValueError):
                        w["end"] = "stopped"
                self._auto.pause()
                self._cancel_client(w.get("client"))
            elif time.monotonic() - w.get("t_status", 0) > 1.0:
                w["t_status"] = time.monotonic()
                try:
                    with open(w["status"], encoding="utf-8") as f:
                        st = json.load(f)
                    w["state"] = "playing"
                    w["delay"] = st.get("delay")
                except (OSError, ValueError):
                    pass
        self.update_card()
