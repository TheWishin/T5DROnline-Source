"""The Online tab's character select (1.1.5): a fighting-game select grid instead of a plain drop-down list.

The play card shows the chosen fighter on a button; it opens the grid over the Online tab: Random and every fighter
a player can pick (fighters.json, in the game's order), the chosen one lit in the accent colour, the player's main
(the fighter of most of their counted matches, from the lobby) marked with a star. Keyboard: the arrow keys move,
Enter or Space picks, Esc closes (Tab / Shift+Tab walk the tiles too); a controller as on the rest of the Online tab:
Cross / A picks the tile that has the focus, Circle / B closes. A ranked set's lock greys the button and closes the
grid (as it greyed the old list).

Names only: the game's select-screen portraits are not in a form this launcher reads (the online lobby's layout,
which rank_art.py reads for the rank plates, holds flags and plates, not faces), and nothing of the game is shipped.

`tab.char_cb` is the button's stand-in for the old list (state "readonly" = open to choose, "disabled" = locked):
tests, the e2e runner and the tab's own code keep using it as before; `tab.char_var` still holds the fighter's name.
"""
import tkinter as tk
from tkinter import ttk

from . import fighters
from .i18n import t

COLUMNS = 6
STAR = "★"


class _Chip:
    """The old Combobox's interface on the fighter button: configure(state="readonly" | "disabled"), cget("state")."""

    def __init__(self, sel, button):
        self.sel = sel
        self.button = button

    def configure(self, cnf=None, **kw):
        state = kw.pop("state", None)
        if state is not None:
            self.sel.set_locked(state == "disabled")
        if kw or cnf:
            return self.button.configure(cnf, **kw)
        return None

    config = configure

    def cget(self, key):
        if key == "state":
            return "disabled" if self.sel.locked else "readonly"
        return self.button.cget(key)

    def __getattr__(self, name):          # grid, winfo_*, bind ... go to the button
        return getattr(self.button, name)


class CharSelect:
    def __init__(self, view, parent):
        self.view = view
        self.tab = tab = view.tab
        self.px = view.px
        self.locked = False
        self.panel = None
        self.tiles = []                    # [(key, name, button)]
        self.cursor = 0                    # the tile with the keyboard focus (the controller's Cross picks it)
        self.button = ttk.Button(parent, style="Card.TButton", command=self.toggle, cursor="hand2")
        self.chip = _Chip(self, self.button)
        tab.char_var.trace_add("write", lambda *_a: self._label())
        self._label()

    # ------------------------------------------------------------------ the button
    def _label(self):
        name = self.tab.char_var.get() or t("Random")
        try:
            self.button.configure(text=f"{name}  ▾")
        except tk.TclError:
            pass

    def set_locked(self, locked):
        self.locked = bool(locked)
        try:
            self.button.configure(state="disabled" if self.locked else "normal",
                                  cursor="arrow" if self.locked else "hand2")
        except tk.TclError:
            pass
        if self.locked:
            self.close()

    # ------------------------------------------------------------------ the grid
    def choices(self):
        """[(key, name)]: Random first, then every fighter a player can pick, in the game's order."""
        return [(fighters.RANDOM, t("Random"))] + [(f["key"], f["name"]) for f in self.tab.table.selectable()]

    def main_key(self):
        me = getattr(getattr(self.tab, "client", None), "me", None)
        return me.get("main") if isinstance(me, dict) else None

    def is_open(self):
        try:
            return self.panel is not None and bool(self.panel.winfo_manager())
        except tk.TclError:
            return False

    def toggle(self):
        if self.is_open():
            self.close()
        else:
            self.open()

    def open(self):
        if self.locked:
            return
        px = self.px
        box = self.view.box
        self.close(refocus=False)
        p = self.panel = ttk.Frame(box, style="Card.TFrame", padding=px(16))
        p.columnconfigure(0, weight=1)
        head = self.view.body(p)
        head.grid(row=0, column=0, sticky="we", pady=(0, px(10)))
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text=t("Choose your fighter").upper(), style="Card.Caps.TLabel").grid(row=0, column=0,
                                                                                            sticky="w")
        main = self.main_key()
        hint = t("{star} your main: {character}", star=STAR, character=self.tab.table.fighter_name(main)) \
            if main else ""
        ttk.Label(head, text=hint, style="Card.Faint.TLabel").grid(row=0, column=1, sticky="w", padx=(px(12), 0))
        ttk.Button(head, text=t("Close"), style="Card.Small.TButton", command=self.close).grid(row=0, column=2,
                                                                                          sticky="e")
        grid = self.view.body(p)
        grid.grid(row=1, column=0, sticky="nsew")
        for c in range(COLUMNS):
            grid.columnconfigure(c, weight=1, uniform="fighters")
        current = self.tab._char_key()
        self.tiles = []
        for i, (key, name) in enumerate(self.choices()):
            style = "Card.Accent.TButton" if key == current else "Card.TButton"
            text = f"{name} {STAR}" if key == main and key != fighters.RANDOM else name
            b = ttk.Button(grid, text=text, style=style, command=lambda k=key, n=name: self.pick(k, n))
            b.grid(row=i // COLUMNS, column=i % COLUMNS, sticky="nsew", padx=px(3), pady=px(3), ipady=px(5))
            for seq, dr, dc in (("<Left>", 0, -1), ("<Right>", 0, 1), ("<Up>", -1, 0), ("<Down>", 1, 0)):
                b.bind(seq, lambda _e, j=i, r=dr, c=dc: self._move(j, r, c))
            b.bind("<Home>", lambda _e: self._focus(0))
            b.bind("<End>", lambda _e: self._focus(len(self.tiles) - 1))
            b.bind("<Escape>", self._escape)
            b.bind("<FocusIn>", lambda _e, j=i: setattr(self, "cursor", j), add="+")
            self.tiles.append((key, name, b))
        ttk.Label(p, style="Card.Faint.TLabel", text=t(
            "Arrow keys move, Enter picks, Esc closes. With a controller: Cross / A picks, Circle / B closes.")).grid(
            row=2, column=0, sticky="w", pady=(px(10), 0))
        p.place(in_=box, relx=0.5, y=px(64), anchor="n", relwidth=0.94)
        p.lift()
        self._focus(next((i for i, (k, _n, _b) in enumerate(self.tiles) if k == current), 0))
        self.tab._pad_relabel()

    def _focus(self, i):
        if self.tiles:
            i = max(0, min(len(self.tiles) - 1, i))
            self.cursor = i
            try:
                self.tiles[i][2].focus_set()
            except tk.TclError:
                pass
        return "break"

    def _move(self, i, dr, dc):
        n = len(self.tiles)
        if dc:
            j = i + dc
        else:
            j = i + dr * COLUMNS
            if j >= n:                           # down from the last row's gap: the last tile
                j = n - 1 if i // COLUMNS < (n - 1) // COLUMNS else i
        if 0 <= j < n:
            self._focus(j)
        return "break"

    def _escape(self, _e=None):
        if self.is_open():
            self.close()
            return "break"
        return None

    def focused(self):
        """(key, name) of the tile with the focus, None while the grid is closed."""
        if not self.tiles:
            return None
        k, n, _b = self.tiles[max(0, min(len(self.tiles) - 1, self.cursor))]
        return k, n

    def pick(self, key, name):
        self.tab.char_var.set(name)
        self.close()
        self.tab.on_char()

    def pad_plan(self):
        """While the grid is open the controller picks and closes here (tk_tab._pad_plan)."""
        def cross():
            f = self.focused()
            if f:
                self.pick(*f)
        return {"cross": (None, cross), "circle": (None, self.close)}

    def close(self, refocus=True):
        p, self.panel = self.panel, None
        self.tiles = []
        if p is not None:
            try:
                p.destroy()
            except tk.TclError:
                pass
            if refocus:
                try:
                    self.button.focus_set()
                except tk.TclError:
                    pass
            try:
                self.tab._pad_relabel()
            except (AttributeError, tk.TclError):
                pass


def build(view, parent):
    """The fighter button in the play card (tk_views._build_play) -> the CharSelect; tab.char_cb is its chip."""
    sel = CharSelect(view, parent)
    view.tab.charsel = sel
    view.tab.char_cb = sel.chip
    return sel
