"""The Build, Play offline and Settings tabs in the Online tab's look (1.1.5): rounded cards on the dark page, the
section name in small capitals inside the card's top-left corner -- the same cards, fields, check boxes and buttons
as lobby/t5lobby/theme.py draws for the Online tab.

    tab_look.apply(app)      once, after the tabs are built (t5dr_launcher.App._layout); nothing without the theme

It changes the look only, never what a tab holds or does: the tabs keep building their widgets as before (a
labelled frame per section). Here each labelled frame of the Build and Settings tabs becomes a card -- its title
moves inside, in the Online tab's section style (its text unchanged) -- and every ttk widget in it gets the card's variant of its style
("Muted.TLabel" -> "Card.Muted.TLabel", a wrapping check box "W440.TCheckbutton" -> "W440.Card.TCheckbutton", ...),
which also holds for a style the launcher sets later (the build steps, the package check's colours): those
widgets' configure() translates it. The Play offline and Replays tabs' content becomes one card each.
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ttk classes that keep their style in a card (they draw their own ground: lists, bars, scroll bars)
KEEP = frozenset(("Treeview", "TScrollbar", "TProgressbar", "TNotebook", "TPanedwindow", "TSizegrip"))
TK_GROUND = frozenset(("Label", "Frame", "Message", "Checkbutton", "Radiobutton", "Canvas"))
MARGIN = 14             # px at 100 %: from the tab row's line and the window's sides to the cards (every tab)


class Look:
    def __init__(self, app, theme):
        self.app = app
        self.theme = theme
        self.th = theme.apply(app)
        self.st = self.th.style
        self.C = theme.C
        self.px = self.th.px
        self.made = {}
        self.cards = []
        st = self.st
        px = self.px
        # A labelled frame drawn as the Online tab's card: theme.py's card image as the frame's border element (a
        # labelframe lays its content inside the element called "...border"), and its own title inside the card,
        # top left: the label's margins pull the border up under it (negative bottom margin) instead of the label
        # sitting on the border line.
        self.inset = px(12) + 1                   # the card image's corner (theme.py: radius 12, border radius + 1)
        self.side = 0                             # (the content as far in as before: no tab gets wider)
        # (the titles keep their case, so a heading font rather than the small capitals of the Online tab's sections)
        self.caps_h = tkfont.Font(font=self.th.fonts["h3"]).metrics("linespace")
        img = self.th.images.get("frame_Card")
        if img is not None and "CardLF.border" not in st.element_names():
            size = 2 * px(12) + px(48)
            st.element_create("CardLF.border", "image", img, border=self.inset, sticky="nsew", width=size,
                              height=size)
        if "CardLF.border" in st.element_names():
            st.layout("Card.TLabelframe", [("CardLF.border", {"sticky": "nsew"})])
        top = px(12)
        st.configure("Card.TLabelframe", background=self.C["bg"], borderwidth=0, labeloutside=False,
                     labelmargins=(self.inset + self.side, top, 0, -(top + self.caps_h)))
        st.configure("Card.TLabelframe.Label", background=self.C["surface"], foreground=self.C["text"],
                     font=self.th.fonts["h3"])
        for name in ("Step", "StepRun", "StepDone", "StepFail"):      # (the launcher's own label styles)
            self.card_style(f"{name}.TLabel", "TLabel")

    # ------------------------------------------------------------------ styles
    def _defined(self, name):
        try:
            return bool(self.st.configure(name))
        except tk.TclError:
            return False

    def card_style(self, old, cls):
        """The card variant of ttk style `old` of a widget of class `cls` ('' = the class's own style)."""
        old = str(old or cls)
        if old in self.made:
            return self.made[old]
        if cls in KEEP or old.startswith(("Card.", "CardBody.", "Tile.")) or ".Card." in old or ".CardBody." in old:
            new = old
        elif old == "TFrame":
            new = "CardBody.TFrame"
        elif old == "TLabelframe":
            new = "Card.TLabelframe"
        elif self._defined("Card." + old):
            new = "Card." + old                               # the theme draws it: Card.TButton, Card.Muted.TLabel ...
        else:
            # a style of the launcher's own ("W440.TCheckbutton", "Step.TLabel"): the same options on the card's
            # variant of its class ("W440.Card.TCheckbutton" falls back to "Card.TCheckbutton", not to "TCheckbutton")
            head, _, base = old.rpartition(".")
            ground = "CardBody" if base == "TFrame" else "Card"      # (a frame in a card is plain, not a card again)
            new = f"{head}.{ground}.{base}" if head else f"{ground}.{base}"
            try:
                opts = {k: v for k, v in (self.st.configure(old) or {}).items() if k != "background"}
                if base in ("TLabel", "TFrame") or not self._defined("Card." + base):
                    opts["background"] = self.C["surface"]
                if opts:
                    self.st.configure(new, **opts)
                m = self.st.map(old)
                if m:
                    self.st.map(new, **{k: v for k, v in m.items() if k != "background"})
            except tk.TclError:
                new = old
        self.made[old] = new
        return new

    # ------------------------------------------------------------------ widgets
    def _hook(self, w, cls):
        """A style the launcher sets on `w` later is translated too (pkg_lbl ok/warn, the build steps ...)."""
        orig = w.configure

        def configure(cnf=None, **kw):
            if isinstance(cnf, dict) and "style" in cnf:
                cnf = dict(cnf, style=self.card_style(cnf["style"], cls))
            if "style" in kw:
                kw["style"] = self.card_style(kw["style"], cls)
            return orig(cnf, **kw)
        w.configure = w.config = configure

    def restyle(self, parent):
        """Every widget below `parent` (which is a card now) on the card's ground."""
        for w in parent.winfo_children():
            cls = w.winfo_class()
            if isinstance(w, ttk.Widget):
                if cls in KEEP:
                    continue
                try:
                    new = self.card_style(w.cget("style"), cls)
                    if new != str(w.cget("style") or cls):
                        w.configure(style=new)
                except tk.TclError:
                    pass
                self._hook(w, cls)
            elif cls in TK_GROUND:
                try:
                    w.configure(background=self.C["surface"])
                    if cls in ("Checkbutton", "Radiobutton"):
                        w.configure(activebackground=self.C["surface"], selectcolor=self.C["raised"])
                except tk.TclError:
                    pass
            if cls == "TLabelframe":
                self.card_labelframe(w)
            else:
                self.restyle(w)

    def card_labelframe(self, lf):
        """A labelled frame -> a card with its title inside, top left (the Online tab's section heading)."""
        try:
            title = str(lf.cget("text") or "").strip()
            # (the content's place inside the card: the card image's corners plus a little; under the title)
            edge = self.inset + self.side
            top = self.px(12) + self.caps_h + self.px(8) if title else edge
            # (the title stays as it is written -- tests and tools find the boxes by it; the heading style does the rest)
            lf.configure(text=title, style="Card.TLabelframe", padding=(edge, top, edge, self.inset))
        except tk.TclError:
            return
        self.cards.append(lf)
        self.restyle(lf)

    def card_frame(self, f, pad=18):
        """A plain frame (the Play offline tab's content) -> one card."""
        try:
            f.configure(style="Card.TFrame", padding=self.px(pad))
        except tk.TclError:
            return
        self.cards.append(f)
        self.restyle(f)


def labelframes(w):
    """The outermost labelled frames below w."""
    out = []
    for c in w.winfo_children():
        if c.winfo_class() == "TLabelframe":
            out.append(c)
        else:
            out += labelframes(c)
    return out


def apply(app, keys=("build", "settings", "play", "replays")):
    """Give the launcher's Build, Settings, Play offline and Replays tabs the Online tab's cards. -> the Look, or None
    without the dark theme (lobby/ missing: the plain look stays)."""
    theme = getattr(app, "theme", None)
    tabs = getattr(app, "tabs", None) or {}
    if theme is None or not tabs:
        return None
    look = Look(app, theme)
    px = look.px
    m = MARGIN
    for key in keys:
        tab = tabs.get(key)
        if tab is None:
            continue
        if key in ("play", "replays"):            # (one frame holds the whole tab: one card)
            kids = [c for c in tab.winfo_children() if c.winfo_class() == "TFrame"]
            if kids:
                look.card_frame(kids[0])
                if kids[0].winfo_manager() == "pack":
                    kids[0].pack_configure(padx=px(m), pady=(px(m), px(8)))
                    if key == "play":              # (nothing in it grows: the card as tall as what it holds)
                        kids[0].pack_configure(fill="x", expand=False)
            continue
        # every tab's cards the same distance from the window's edges as the Online tab's (tk_views.OnlineView)
        if key == "build":                         # (its cards keep their own 8 px apart)
            tab.configure(padding=(px(m - 8), px(m - 8), px(m - 8), 0))
        elif key == "settings":
            inner = getattr(getattr(app, "settings_scroll", None), "inner", None)
            box = [c for c in inner.winfo_children() if c.winfo_class() == "TFrame"][:1] if inner else []
            if box:
                box[0].configure(padding=(px(m), px(m), px(m), px(m)))
        for lf in labelframes(tab):
            look.card_labelframe(lf)
    app.tab_look = look
    return look
