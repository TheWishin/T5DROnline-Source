"""The Online tab's casual choices (1.1.5; docs/ONLINE.md "Sides and stages by choice"; the server: server/casual.py).

Two choices in the play card, right of Strict -- the side (any, P1, P2) and the stage (Random or one of the
server's) -- count in challenges, friends' casual invites and rooms (not ranked ones). They are kept in online.json
and go to the server after every login and when the player changes them (client.set_casual_prefs). A challenger's
or a friend's wishes come with their question; the match card says which side and stage this player got; a casual
rematch offers Rematch: swap sides (Triangle / Y on a pad). The row is hidden on a server without casual choices.

1.2.0: under the row's choices, Screen side shares the launcher's dealt/left/right setting with Settings. It counts
in these casual matches only (T5_NET_CASUAL; never ranked, Quick or a tournament set). MatchDriver passes it to
every match. The legacy always_left bool remains synchronized for older callers.
"""
import tkinter as tk
from tkinter import ttk

from . import fighters, proto
from .i18n import N_, t

SIDES = ((None, N_("Any side")), (0, N_("P1 (left)")), (1, N_("P2 (right)")))
SCREEN_SIDES = {"dealt": N_("As dealt"), "left": N_("Always left"), "right": N_("Always right")}


class CasualUI:
    def __init__(self, tab):
        self.tab = tab
        side = tab.cfg.get("casual_side")
        self.side = side if side in (0, 1) else None
        self.stage = str(tab.cfg.get("casual_stage") or fighters.RANDOM)
        target = tab.cfg.get("casual_first_to", 1)
        self.first_to = target if type(target) is int and target in proto.CASUAL_FIRST_TO else 1
        self.side_var = tk.StringVar(value="")
        self.stage_var = tk.StringVar(value="")
        self.set_var = tk.StringVar(value="")
        self.set_row = self.set_cb = None
        self.row = None              # the choices in the play card (tk_views), shown while the server has them
        self.side_cb = self.stage_cb = None
        self.left_check = None       # legacy alias for the left screen-side radio
        self.skip_check = None
        self.skip_var = tk.BooleanVar(value=bool(tab.cfg.get("auto_skip_after_round", False)))
        self.left_var = None
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
        line = ttk.Frame(row, style="CardBody.TFrame")      # caption, side, stage; the checkbox on a line below
        line.pack(side="top", anchor="w")
        self.caption = ttk.Label(line, text=t("Challenges, invites, rooms:"), style="Card.Small.TLabel")
        self.caption.pack(side="left", padx=(0, px(6)))
        self.side_cb = ttk.Combobox(line, textvariable=self.side_var, values=[t(x[1]) for x in SIDES],
                                    state="readonly", width=11, style="Card.TCombobox")
        self.side_cb.pack(side="left")
        self.side_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_change())
        self.stage_cb = ttk.Combobox(line, textvariable=self.stage_var, state="readonly", width=17,
                                     style="Card.TCombobox")
        self.stage_cb.pack(side="left", padx=(px(6), 0))
        self.stage_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_change())
        self.set_row = ttk.Frame(row, style="CardBody.TFrame")
        self.set_row.pack(side="top", anchor="w", pady=(px(4), 0))
        ttk.Label(self.set_row, text=t("Casual sets:"), style="Card.Small.TLabel").pack(side="left", padx=(0, px(6)))
        self.set_cb = ttk.Combobox(self.set_row, textvariable=self.set_var, state="readonly", width=7,
                                  values=[t("FT{wins}", wins=n) for n in proto.CASUAL_FIRST_TO],
                                  style="Card.TCombobox")
        self.set_cb.pack(side="left")
        self.set_cb.bind("<<ComboboxSelected>>", lambda _e: self.on_set_change())
        ttk.Label(self.set_row, text=t("Older launchers play single games."), style="Card.Small.TLabel").pack(
            side="left", padx=(px(6), 0))
        # Share the Settings tab's language-independent token.
        app = getattr(self.tab, "app", None)
        self.left_var = getattr(app, "screen_side_var", None)
        if not isinstance(self.left_var, tk.StringVar):
            settings = getattr(app, "settings", None) or {}
            side = settings.get("screen_side", "left" if settings.get("always_left") else "dealt")
            self.left_var = tk.StringVar(value=side if side in SCREEN_SIDES else "dealt")
        screen_row = ttk.Frame(row, style="CardBody.TFrame")
        screen_row.pack(side="top", anchor="w", pady=(px(4), 0))
        ttk.Label(screen_row, text=t("Screen side"), style="Card.Small.TLabel").pack(side="left", padx=(0, px(6)))
        self.screen_checks = []
        for side, label in SCREEN_SIDES.items():
            check = ttk.Radiobutton(screen_row, text=t(label), variable=self.left_var, value=side,
                                    command=self.on_left, style="Card.TRadiobutton")
            check.pack(side="left", padx=(0, px(6)))
            self.screen_checks.append(check)
        self.left_check = self.screen_checks[1]  # legacy tests/callers: the left choice
        self.skip_check = ttk.Checkbutton(row, text=t("Auto-skip replays and round endings (both players agree)"),
                                          variable=self.skip_var, command=self.on_skip,
                                          style="Card.TCheckbutton")
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
        self.set_var.set(t("FT{wins}", wins=self.first_to))

    def refresh(self):
        """After a login or a logout: the server's stages, and the row shown only where the choices count."""
        on = self.ok()
        skip_ok = on and bool(getattr(self.client, "auto_skip_ok", lambda: False)())
        if self.skip_check is not None:
            if skip_ok:
                self.skip_check.pack(side="top", anchor="w")
            else:
                self.skip_check.pack_forget()
        sets_on = bool(on and hasattr(self.client, "casual_sets_ok") and self.client.casual_sets_ok())
        stages = self.client.casual_stages() if on else self.stages
        if (on, tuple(stages), sets_on) == self._shown:
            return                   # (called with every change of the tab's buttons)
        self._shown = (on, tuple(stages), sets_on)
        self.stages = list(stages)
        self._fill()
        if self.set_row is not None:
            if sets_on:
                self.set_row.pack(side="top", anchor="w")
            else:
                self.set_row.pack_forget()
        if self.row is not None:
            if on:
                self.row.grid()
                place = getattr(getattr(self.tab, "view", None), "place_casual_row", None)
                if place is not None:
                    place()                  # (beside "Strict" or below it: whichever fits)
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

    def on_left(self):
        """Save screen side at once; the next casual match reads it, including an explicit reset to dealt."""
        app = getattr(self.tab, "app", None)
        settings = getattr(app, "settings", None)
        if settings is None:
            return
        if getattr(app, "screen_side_var", None) is self.left_var and hasattr(app, "save_settings"):
            app.save_settings()
            return
        side = self.left_var.get() if self.left_var.get() in SCREEN_SIDES else "dealt"
        settings["screen_side"] = side
        settings["always_left"] = side == "left"  # legacy readers
        if hasattr(settings, "save"):
            settings.save()

    def on_set_change(self):
        labels = [t("FT{wins}", wins=n) for n in proto.CASUAL_FIRST_TO]
        shown = self.set_var.get()
        self.first_to = proto.CASUAL_FIRST_TO[labels.index(shown)] if shown in labels else 1
        self.tab.cfg["casual_first_to"] = self.first_to
        self.tab._save_cfg()
        if self.client is not None:
            self.client.casual_first_to = self.first_to

    def on_skip(self):
        self.tab.cfg["auto_skip_after_round"] = bool(self.skip_var.get())
        self.tab._save_cfg()
        c = self.client
        if c is not None and hasattr(c, "set_auto_skip_after_round"):
            c.set_auto_skip_after_round(self.skip_var.get())

    def new_client(self, c):
        """A new LobbyClient (before it connects): the wishes go with every login."""
        if hasattr(c, "set_casual_prefs"):
            c.set_casual_prefs(self.side, self.stage)
        c.casual_first_to = self.first_to
        if hasattr(c, "set_auto_skip_after_round"):
            c.set_auto_skip_after_round(self.skip_var.get())

    # ------------------------------------------------------------------ texts
    def wish_text(self, wish):
        """' -- wants to be P1 on Scrapyard' for a challenger's or a friend's wishes ('' when they leave both open)."""
        text = self.wish_line(wish)
        return " -- " + text if text else ""

    def wish_line(self, wish):
        """'wants to be P1 on Scrapyard' (the challenge / invite card's line, 1.1.7); '' when they leave both open."""
        wish = wish if isinstance(wish, dict) else {}
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
        return text

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
