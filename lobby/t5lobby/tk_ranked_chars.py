"""The profile's ranked fighter records (1.2.0), supplied by the lobby server.

This view only formats the server's rows. The server counts games and computes win rates; rating and rank
remain on the account. Older servers omit ranked_chars, so their profile has no extra section.
"""
from tkinter import font as tkfont, ttk

from . import i18n, tklist
from .i18n import t

COLUMNS = ("fighter", "games", "wins", "losses", "draws", "winrate")
WIDTHS = (180, 80, 80, 80, 80, 110)


def rows_for(profile, fighter_name):
    """Format every server row in server order; do not derive stats from the limited profile history."""
    return [("ranked:" + row["char"],
             (fighter_name(row["char"]), *(i18n.num(row[key]) for key in ("games", "wins", "losses", "draws")),
              i18n.num(row["win_rate"], 2) + " %"), None, ())
            for row in profile.get("ranked_chars") or ()]


class RankedCharacters:
    def __init__(self, view, card):
        self.view = view
        self.frame = view.body(card)
        self.frame.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(view.px(8), 0))
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)
        ttk.Label(self.frame, text=t("Ranked by character").upper(), style="Card.Caps.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, view.px(4)))
        frame, self.tv = view.tree(self.frame, COLUMNS, WIDTHS, height=4, image_col=False, select="none",
                                   empty=t("No ranked games played."))
        frame.grid(row=1, column=0, sticky="nsew")
        style = ttk.Style(self.tv)
        heading_style = str(self.tv.cget("style") or "Treeview") + ".Heading"
        heading_font = tkfont.Font(root=self.tv, font=style.lookup(heading_style, "font") or "TkHeadingFont")
        padding = [self.tv.winfo_pixels(value) for value in
                   self.tv.tk.splitlist(style.lookup(heading_style, "padding") or "0")]
        horizontal_padding = padding[0] + padding[2] if len(padding) >= 3 else 2 * padding[0]
        for column in COLUMNS:
            # Translated headings can exceed the default numeric-column widths.
            needed = heading_font.measure(self.tv.heading(column, "text")) + max(horizontal_padding, view.px(12))
            self.tv.column(column, width=max(self.tv.column(column, "width"), needed),
                           minwidth=max(self.tv.column(column, "minwidth"), needed))
        for column in COLUMNS[1:]:
            self.tv.column(column, anchor="e")
            self.tv.heading(column, anchor="e")
        self.frame.grid_remove()

    def shown(self, profile):
        rows = rows_for(profile, self.view.tab.table.fighter_name)
        tklist.sync(self.tv, rows)
        self.view.show_empty(self.tv, not rows)
        if "ranked_chars" in profile:
            self.frame.grid()
        else:
            self.frame.grid_remove()
