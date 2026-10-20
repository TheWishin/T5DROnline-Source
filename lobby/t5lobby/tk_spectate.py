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

from . import spectate, theme
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
    return t("The match data stopped coming.")      # stopped, unavailable, anything else


class Spectating:
    def __init__(self, tab):
        self.tab = tab
        self.w = None            # {stream, players, ranked, room, began, game, result, status, state, end, t0, delay}
        self.count = None        # spectators of this player's own match (the server's `spectators`)
        self.card = None
        self._sig = None
        self._prefs = None       # the (allow, ranked) last sent

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
        self.pill.configure(text=t("RANKED") if ranked else t("CASUAL"),
                            style="Card.PillAccent.TLabel" if ranked else "Card.Pill.TLabel")
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
        ok = self.ok() and not busy and self.w is None
        fb = (getattr(tab, "friend_actions", None) or {}).get("watch")
        if fb is not None:
            f = tab._selected_friend() if ok else None
            try:
                fb.configure(state="normal" if f is not None and f.get("watch") else "disabled")
            except tk.TclError:
                pass
        rb = (getattr(tab, "actions", None) or {}).get("watch_room")
        if rb is not None:
            r = self._selected_room() if ok else None
            me = (tab.client.me or {}).get("id") if tab.client else None
            on = r is not None and r.get("watch") and me not in (r.get("members") or ())
            try:
                rb.configure(state="normal" if on else "disabled")
            except tk.TclError:
                pass

    def _selected_room(self):
        tv = getattr(self.tab, "tv_rooms", None)
        sel = tv.selection() if tv is not None else ()
        if not sel:
            return None
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
            self._watch(room=r["id"])

    def _watch(self, name=None, room=None):
        tab = self.tab
        if self.w is not None or not self.ok():
            return
        g = getattr(tab.app, "game", None)
        drv = tab.driver
        if g is not None and g.running() and (drv is None or g is not drv.game):
            tab.status(t("Close the running game first (Stop game on the Play tab)."), error=True)
            return

        def done(r):
            self.w = {"stream": r["stream"], "match": r.get("match"), "players": r.get("players"),
                      "ranked": r.get("ranked"), "room": r.get("room"), "began": r.get("began"),
                      "spectators": r.get("spectators"), "state": "waiting", "game": None, "t0": time.monotonic(),
                      "end": None, "delay": None}
            names = [p.get("name", "?") for p in r.get("players") or ()] + ["?", "?"]
            tab.status(t("Watching {p1} vs {p2}.", p1=names[0], p2=names[1]))
            # the game starts now: it boots while the players' games load the fight, and waits for the data
            path = (getattr(tab.client, "spec_watch", None) or {}).get("path")
            if path and self.w["stream"] == (tab.client.spec_watch or {}).get("stream"):
                self._start_game(path)
            tab._set_actions()
        tab.call(tab.client.watch, name, room, then=done)

    def _start_game(self, path):
        tab, w = self.tab, self.w
        drv = tab.driver
        if drv is not None and drv.ticket is None and drv.game_running():
            drv.stop_game()                  # the idle online game (persistent mode): it starts again for a match
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
            return
        w["game"] = g
        w["state"] = "starting"

    def stop(self):
        w = self.w
        if w is None:
            return
        if w["state"] != "over":
            g = w.get("game")
            if g is not None and g.running():
                g.stop()
            c = self.tab.client
            if c is not None:
                self.tab.call(c.unwatch)
        self.w = None
        self._sig = None
        self.tab._set_actions()

    # ------------------------------------------------------------------ the tab's poll and events
    def on_event(self, ev):
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
            if w is not None and ev.get("stream") == w["stream"]:
                w["end"] = ev.get("reason") or "over"
                if w["game"] is None:
                    w["state"] = "over"           # (the game never started: nothing to watch)
                elif w["end"] in ("your_match", "not_allowed") or (w["state"] == "starting" and not ev.get("ready")):
                    # privacy and the player's own match: at once; a game still waiting for a first fight
                    # that never came has nothing to show (with a fight in the file it plays to its end)
                    if w["game"].running():
                        w["game"].stop()
                    w["state"] = "over"
            return True
        if kind in ("match_found", "disconnected") and w is not None and w["state"] != "over":
            g = w.get("game")
            if g is not None and g.running():
                g.stop()
            w["state"], w["end"] = "over", "your_match" if kind == "match_found" else "stopped"
        if kind == "match_start":
            self.count = None
        return False

    def poll(self):
        self._check_prefs()
        w = self.w
        if w is None:
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
                c = self.tab.client
                if c is not None and getattr(c, "spec_watch", None) is not None:
                    self.tab.call(c.unwatch)
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
