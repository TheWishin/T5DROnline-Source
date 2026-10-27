"""The Online tab's character select (1.1.5): a fighting-game select grid instead of a plain drop-down list.

The play card shows the chosen fighter on a button; it opens the grid over the Online tab: Random first, then every
fighter a player can pick (fighters.json) in the alphabetical order of the names shown, each with its picture, the
chosen one lit in the accent colour, the player's main (the fighter of most of their counted matches, from the lobby)
marked with a star. Keyboard: the arrow keys move,
Enter or Space picks, Esc closes (Tab / Shift+Tab walk the tiles too); a controller as on the rest of the Online tab:
Cross / A picks the tile that has the focus, Circle / B closes. A ranked set's lock greys the button and closes the
grid (as it greyed the old list).

Pictures: the head and shoulders of the game's own select-screen render of each fighter, read from the player's
built game into <output folder>\\cache\\fighters (fighter_art.py; never shipped) -- on the first use after BUILD GAME,
in a thread, the grid fills them in when they are there. Without them (no build yet, a failed read) the tiles show
the names alone.

`tab.char_cb` is the button's stand-in for the old list (state "readonly" = open to choose, "disabled" = locked):
tests, the e2e runner and the tab's own code keep using it as before; `tab.char_var` still holds the fighter's name.
"""
import tkinter as tk
from tkinter import ttk

from . import fighter_art, fighters
from .i18n import t

COLUMNS = 6                 # names only
COLUMNS_PICTURES = 9        # with the pictures (36 tiles: 4 rows)
PICTURE = 64                # the pictures' size at 100 % display scaling
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
        self.columns = COLUMNS
        self.button = ttk.Button(parent, style="Card.TButton", command=self.toggle, cursor="hand2")
        self.chip = _Chip(self, self.button)
        tab.char_var.trace_add("write", lambda *_a: self._label())
        self._label()
        self._styles()
        self.pic_size = self.px(PICTURE)
        self.blank = None                  # the Random tile's empty picture (the tiles' text lines up)
        fighter_art.FACES.listeners.append(self._pictures_ready)
        try:
            self.button.after(2500, self.prepare_pictures)      # (the first use after BUILD GAME reads them)
        except tk.TclError:
            pass

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
        """[(key, name)]: Random first, then every fighter a player can pick, by the name shown (A to Z)."""
        picks = sorted(((f["key"], f["name"]) for f in self.tab.table.selectable()), key=lambda c: c[1].casefold())
        return [(fighters.RANDOM, t("Random"))] + picks

    # ------------------------------------------------------------------ pictures (fighter_art.py)
    def _styles(self):
        """Tile styles: the card buttons with the small font and less padding, so a picture and a name fit."""
        st = ttk.Style(self.button)
        th = self.view.th if hasattr(self.view, "th") else None
        font = th.fonts["small"] if th is not None and "small" in getattr(th, "fonts", {}) else None
        for base in ("Card.TButton", "Card.Accent.TButton"):
            opts = {"padding": (self.px(4), self.px(4))}
            if font is not None:
                opts["font"] = font
            st.configure("Fighter." + base, **opts)

    def out_dir(self):
        return getattr(getattr(getattr(self.tab, "app", None), "settings", None), "out_dir", None)

    def prepare_pictures(self):
        """Read the pictures from the built game once (a thread); the grid fills them in when they are there."""
        faces, out = fighter_art.FACES, self.out_dir()
        if out:
            faces.set_folder(fighter_art.folder_for(out))
        if faces.has(self.pic_size) or not out:
            return
        try:
            from .tk_tab import _launcher_log
            faces.prepare([self.pic_size], out_dir=out, after=self.button.after, log=_launcher_log)
        except (tk.TclError, RuntimeError):
            pass

    def _pictures_ready(self):
        try:
            alive = self.button.winfo_exists()
        except tk.TclError:
            alive = False
        if not alive:
            fighter_art.FACES.listeners[:] = [f for f in fighter_art.FACES.listeners if f != self._pictures_ready]
            return
        if self.is_open():
            self.open()                    # (again, with the pictures)

    def random_picture(self, faces):
        """The Random tile's picture: four fighters' pictures at half size, a new four each time the grid opens."""
        import random
        half = self.pic_size // 2
        if len(faces) < 4 or half < 2:
            return None
        try:
            img = tk.PhotoImage(master=self.button, width=half * 2, height=half * 2)
            for k, face in enumerate(random.sample(faces, 4)):
                small = face.subsample(max(1, face.width() // half))
                img.tk.call(img, "copy", small, "-to", (k % 2) * half, (k // 2) * half)
        except tk.TclError:
            return None
        self._random_img = img             # (kept: Tk drops an image nobody holds)
        return img

    def picture(self, key):
        """The PhotoImage of fighter `key`, None without the pictures."""
        faces = fighter_art.FACES
        if not faces.has(self.pic_size):
            return None
        f = self.tab.table._f.get(key) if hasattr(self.tab.table, "_f") else None
        gid = f.get("id") if isinstance(f, dict) else None
        return faces.image(self.button, gid, self.pic_size) if isinstance(gid, int) else None

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
        if not fighter_art.FACES.has(self.pic_size):
            self.prepare_pictures()        # (the first use: the grid gets them when they are read)
        choices = self.choices()
        pics = {key: self.picture(key) for key, _n in choices}
        with_pics = any(pics.values())
        self.columns = cols = COLUMNS_PICTURES if with_pics else COLUMNS
        if with_pics:
            pics[fighters.RANDOM] = self.random_picture([p for p in pics.values() if p is not None])
            if self.blank is None:
                self.blank = tk.PhotoImage(master=self.button, width=self.pic_size, height=self.pic_size)
        for c in range(cols):
            grid.columnconfigure(c, weight=1, uniform="fighters")
        current = self.tab._char_key()
        self.tiles = []
        for i, (key, name) in enumerate(choices):
            style = "Card.Accent.TButton" if key == current else "Card.TButton"
            text = f"{name} {STAR}" if key == main and key != fighters.RANDOM else name
            b = ttk.Button(grid, text=text, style=style, command=lambda k=key, n=name: self.pick(k, n))
            if with_pics:                  # the picture above the name (a missing one: the name alone, lined up)
                b.configure(image=pics[key] or self.blank, compound="top", style="Fighter." + style)
            b.grid(row=i // cols, column=i % cols, sticky="nsew", padx=px(3), pady=px(3),
                   ipady=0 if with_pics else px(5))
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
            cols = self.columns
            j = i + dr * cols
            if j >= n:                           # down from the last row's gap: the last tile
                j = n - 1 if i // cols < (n - 1) // cols else i
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
