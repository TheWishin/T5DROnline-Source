"""The Online tab's casual choices (1.1.5; docs/ONLINE.md "Sides and stages by choice"; the server: server/casual.py).

Two choices in the play card, right of Strict -- the side (any, P1, P2) and the stage (Random or one of the
server's) -- count in challenges, friends' casual invites and rooms (not ranked ones). They are kept in online.json
and go to the server after every login and when the player changes them (client.set_casual_prefs). A challenger's
or a friend's wishes come with their question; the match card says which side and stage this player got; a casual
rematch offers Rematch: swap sides (Triangle / Y on a pad). The row is hidden on a server without casual choices.
"""
import tkinter as tk
from tkinter import ttk

from . import fighters
from .i18n import N_, t

SIDES = ((None, N_("Any side")), (0, N_("P1 (left)")), (1, N_("P2 (right)")))


class CasualUI:
    def __init__(self, tab):
        self.tab = tab
        side = tab.cfg.get("casual_side")
        self.side = side if side in (0, 1) else None
        self.stage = str(tab.cfg.get("casual_stage") or fighters.RANDOM)
        self.side_var = tk.StringVar(value="")
        self.stage_var = tk.StringVar(value="")
        self.row = None              # the choices in the play card (tk_views), shown while the server has them
        self.side_cb = self.stage_cb = None
        self.stages = []             # the stage keys the combobox lists after Random
        self._shown = None           # (shown, stages) the row was last set up for
        self.last_casual = False     # the last match had the players' choices: its rematch can swap sides
        self.offers = {}             # match id -> the opponent's rematch offer asked for the sides swapped

    @property
    def client(self):
        return self.tab.client

    def ok(self):
        c = self.client
        return c is not None and c.me is not None and hasattr(c, "casual_ok") and c.casual_ok()

    # ------------------------------------------------------------------ the choices
    def build(self, parent, px):
        """The row right of Strict (tk_views): caption, side, stage. Gridded by the view, hidden until a login
        on a server that has casual choices."""
        row = ttk.Frame(parent, style="CardBody.TFrame")
        ttk.Label(row, text=t("Challenges, invites, rooms:"), style="Card.Small.TLabel").pack(side="left",
                                                                                               padx=(0, px(6)))
        self.side_cb = ttk.Combobox(row, textvariable=self.side_var, values=[t(x[1]) for x in SIDES],
                                    state="readonly", width=11, style="Card.TCombobox")
        self.side_cb.pack(side="left")
        self.side_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_change())
        self.stage_cb = ttk.Combobox(row, textvariable=self.stage_var, state="readonly", width=17,
                                     style="Card.TCombobox")
        self.stage_cb.pack(side="left", padx=(px(6), 0))
        self.stage_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_change())
        self.row = row
        self._fill()
        return row

    def _fill(self):
        """The choices as this player left them, in the player's language."""
        if self.side_cb is None:
            return
        names = [t("Random stage")] + [self.tab.table.stage_name(k) for k in self.stages]
        self.stage_cb.configure(values=names)
        self.side_var.set(t(dict(SIDES)[self.side]))
        self.stage_var.set(names[1 + self.stages.index(self.stage)] if self.stage in self.stages else names[0])

    def refresh(self):
        """After a login or a logout: the server's stages, and the row shown only where the choices count."""
        on = self.ok()
        stages = self.client.casual_stages() if on else self.stages
        if (on, tuple(stages)) == self._shown:
            return                   # (called with every change of the tab's buttons)
        self._shown = (on, tuple(stages))
        self.stages = list(stages)
        self._fill()
        if self.row is not None:
            if on:
                self.row.grid()
            else:
                self.row.grid_remove()

    def on_change(self):
        side = next((k for k, label in SIDES if t(label) == self.side_var.get()), None)
        names = list(self.stage_cb.cget("values")) if self.stage_cb is not None else []
        i = names.index(self.stage_var.get()) if self.stage_var.get() in names else 0
        stage = self.stages[i - 1] if i > 0 and i - 1 < len(self.stages) else fighters.RANDOM
        self.side, self.stage = side, stage
        self.tab.cfg["casual_side"], self.tab.cfg["casual_stage"] = side, stage
        self.tab._save_cfg()
        if self.ok():
            self.tab.call(self.client.set_casual_prefs, side, stage)

    def new_client(self, c):
        """A new LobbyClient (before it connects): the wishes go with every login."""
        if hasattr(c, "set_casual_prefs"):
            c.set_casual_prefs(self.side, self.stage)

    # ------------------------------------------------------------------ texts
    def wish_text(self, wish):
        """' -- wants to be P1 on Scrapyard' for a challenger's or a friend's wishes ('' when they leave both open)."""
        wish = wish or {}
        side, stage = wish.get("side"), wish.get("stage") or fighters.RANDOM
        name = self.tab.table.stage_name(stage) if stage != fighters.RANDOM else None
        if side in (0, 1) and name:
            text = t("wants to be P{n} on {stage}", n=side + 1, stage=name)
        elif side in (0, 1):
            text = t("wants to be P{n}", n=side + 1)
        elif name:
            text = t("wants to play on {stage}", stage=name)
        else:
            return ""
        return " -- " + text

    def head_suffix(self, ev):
        """For the match card's head ("Casual match vs X"): the side and the stage, when the players' choices
        counted in this match; also says in the status line when a coin flip went against this player's wish."""
        self.last_casual = bool(ev.get("casual"))
        if not self.last_casual:
            return ""
        slot = ev.get("slot") or 0
        stage = (ev.get("fight") or {}).get("stage")
        if self.side in (0, 1) and self.side != slot and not ev.get("rematch_of"):    # (a rematch keeps or swaps)
            self.tab.status(t("You both wanted P{n}: a coin flip made you P{m}.", n=self.side + 1, m=slot + 1))
        elif self.stage != fighters.RANDOM and stage and stage != self.stage:
            self.tab.status(t("Your opponent wanted another stage: a coin flip chose {stage}.",
                              stage=self.tab.table.stage_name(stage)))
        return " (" + t("P{n} on {stage}", n=slot + 1, stage=self.tab.table.stage_name(stage)) + ")"

    # ------------------------------------------------------------------ events, rematches
    def after_event(self, ev):
        """Every lobby event, after the tab handled it."""
        kind = ev.get("t")
        tab = self.tab
        if kind == "challenged" and tab.challenge == ev.get("challenge"):
            tab.bar_text.set(tab.bar_text.get() + self.wish_text(ev.get("wish")))
        elif kind == "invited" and ev.get("kind") == "casual" and tab.invite is ev:
            tab.bar_text.set(tab.bar_text.get() + self.wish_text(ev.get("wish")))
        elif kind == "rematch" and ev.get("state") == "offered":
            self.offers[ev.get("match")] = bool(ev.get("swap"))

    def rematch_buttons(self):
        """For the rematch question after a casual match by choice: Rematch: swap sides (Triangle)."""
        if not (self.last_casual and self.ok()):
            return []
        return [(t("Rematch: swap sides"), lambda: self.tab._rematch(True, swap=True), "triangle")]

    def offer(self, n):
        """The opponent's rematch offer (driver note): (text after "X wants a rematch", extra buttons)."""
        if self.offers.pop(n.get("match"), False):
            return " -- " + t("with the sides swapped"), []
        return "", self.rematch_buttons()
