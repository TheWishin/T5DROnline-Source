"""Search options, area and language in the Online tab (docs/ONLINE.md "Search options, areas and languages").

The options live in online.json (the tab's cfg): max_ping (None / 60 / 100 / 150), no_wifi, steady; the area the
player says they are in ("auto" = the nearest relay's, the server decides) and the language they speak ("" = the
launcher's language). The server learns Wi-Fi / area / language once per login (client.netinfo, sent after the
login) and again when the player changes them here; the options go with every Quick / Ranked search. A server
without "mm_filters" gets none of it (the button says the server has no search options).
"""
import tkinter as tk
from tkinter import ttk

from . import i18n, netinfo
from .i18n import t
from .theme import C

AREA_CODES = ("na", "sa", "eu", "af", "as", "oc")


def area_labels():
    """code -> the area in the launcher's language"""
    return {"na": t("North America"), "sa": t("South America"), "eu": t("Europe"), "af": t("Africa"),
            "as": t("Asia"), "oc": t("Oceania")}
AREA_SHORT = {"na": "NA", "sa": "SA", "eu": "EU", "af": "AF", "as": "AS", "oc": "OC"}


def options(cfg):
    """The search options for client.quick_match / ranked_match."""
    mp = cfg.get("max_ping")
    return {"max_ping": mp if mp in (60, 100, 150) else None, "no_wifi": bool(cfg.get("no_wifi")),
            "steady": bool(cfg.get("steady"))}


def launcher_lang():
    return i18n.language() or "en"


def netinfo_msg(cfg, wifi=None):
    """What the client sends after its login: {wifi, area, lang}."""
    area = cfg.get("area") if cfg.get("area") in AREA_CODES else "auto"
    lang = cfg.get("lang") if cfg.get("lang") in netinfo.LANG_NAMES else launcher_lang()
    return {"wifi": wifi if isinstance(wifi, bool) else None, "area": area, "lang": lang}


def summary(cfg):
    """The options that are on, for the line under the search buttons ("" = none)."""
    o = options(cfg)
    parts = []
    if o["max_ping"]:
        parts.append(t("ping up to {ms} ms", ms=o["max_ping"]))
    if o["no_wifi"]:
        parts.append(t("no Wi-Fi"))
    if o["steady"]:
        parts.append(t("steady 60 fps"))
    return ", ".join(parts)


def where_text(p):
    """A lobby list row's area and language ("EU de"), or "" (an older server, or not known)."""
    parts = [AREA_SHORT.get(p.get("area"), "")] if p.get("area") else []
    if p.get("lang"):
        parts.append(str(p["lang"]))
    return " ".join(x for x in parts if x)


class SearchOptions:
    """The "Search options..." window of the Online tab."""

    def __init__(self, tab):
        self.tab = tab
        self.window = None
        self.wifi = None            # this PC's adapter kind, read once per login (netinfo.on_wifi)

    def refresh_wifi(self):
        self.wifi = netinfo.on_wifi()
        return self.wifi

    def client_netinfo(self):
        return netinfo_msg(self.tab.cfg, self.wifi)

    def supported(self):
        c = self.tab.client
        return c is None or c.has_feature("mm_filters")

    def open(self):
        tab = self.tab
        if self.window is not None:
            try:
                self.window.lift()
                return self.window
            except tk.TclError:
                self.window = None
        view, cfg = tab.view, tab.cfg
        px = view.px
        w = tab.new_window(tab.parent)
        w.title(t("Search options"))
        w.configure(bg=C["bg"])
        self.window = w
        w.bind("<Destroy>", lambda e: setattr(self, "window", None) if e.widget is w else None)
        card = view.card(w, pad=16)
        card.pack(fill="both", expand=True, padx=px(10), pady=px(10))
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text=t("Search options"), style="Card.H2.TLabel").grid(row=0, column=0, columnspan=2,
                                                                                sticky="w")
        ttk.Label(card, wraplength=px(420), justify="left", style="Card.Muted.TLabel", text=t(
            "For Quick match and Ranked match. Your opponent's options count too. The more you choose, the longer "
            "the search can take.")).grid(row=1, column=0, columnspan=2, sticky="w", pady=(px(4), px(10)))
        ttk.Label(card, text=t("Highest ping"), style="Card.TLabel").grid(row=2, column=0, sticky="w")
        ping_var = tk.StringVar(value=str(cfg.get("max_ping") or "any"))
        row = view.body(card)
        row.grid(row=2, column=1, sticky="w", padx=(px(10), 0))
        for value, label in (("any", t("Any")), ("60", "60 ms"), ("100", "100 ms"), ("150", "150 ms")):
            ttk.Radiobutton(row, text=label, value=value, variable=ping_var, style="Card.TRadiobutton").pack(
                side="left", padx=(0, px(10)))
        wifi_var = tk.BooleanVar(value=bool(cfg.get("no_wifi")))
        steady_var = tk.BooleanVar(value=bool(cfg.get("steady")))
        ttk.Checkbutton(card, text=t("No opponents on Wi-Fi"), variable=wifi_var, style="Card.TCheckbutton").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
        ttk.Checkbutton(card, text=t("Only opponents whose PC keeps 60 fps"), variable=steady_var,
                        style="Card.TCheckbutton").grid(row=4, column=0, columnspan=2, sticky="w", pady=(px(4), 0))
        ttk.Label(card, wraplength=px(420), justify="left", style="Card.Faint.TLabel", text=t(
            "Wi-Fi and speed come from your opponent's launcher (its last match); a launcher that does not say is "
            "not left out.")).grid(row=5, column=0, columnspan=2, sticky="w", pady=(px(2), px(10)))
        # where you are and the language you speak: shown next to your name in the lobby and on your rooms
        ttk.Label(card, text=t("Your area"), style="Card.TLabel").grid(row=6, column=0, sticky="w")
        areas = [("auto", t("Auto (the nearest server)"))] + list(area_labels().items())
        area_var = tk.StringVar(value=dict(areas).get(cfg.get("area") or "auto", areas[0][1]))
        ttk.Combobox(card, textvariable=area_var, values=[v for _k, v in areas], state="readonly", width=28).grid(
            row=6, column=1, sticky="w", padx=(px(10), 0), pady=(0, px(4)))
        ttk.Label(card, text=t("Language you speak"), style="Card.TLabel").grid(row=7, column=0, sticky="w")
        langs = [("", t("The launcher's language"))] + list(netinfo.LANGS)
        lang_var = tk.StringVar(value=dict(langs).get(cfg.get("lang") or "", langs[0][1]))
        ttk.Combobox(card, textvariable=lang_var, values=[v for _k, v in langs], state="readonly", width=28).grid(
            row=7, column=1, sticky="w", padx=(px(10), 0))
        note = ttk.Label(card, wraplength=px(420), justify="left", style="Card.Faint.TLabel", text="" if
                         self.supported() else t("This server has no search options yet: they count once it has."))
        note.grid(row=8, column=0, columnspan=2, sticky="w", pady=(px(8), 0))
        bar = view.body(card)
        bar.grid(row=9, column=0, columnspan=2, sticky="we", pady=(px(12), 0))

        def save():
            mp = ping_var.get()
            cfg["max_ping"] = int(mp) if mp in ("60", "100", "150") else None
            cfg["no_wifi"] = bool(wifi_var.get())
            cfg["steady"] = bool(steady_var.get())
            cfg["area"] = next((k for k, v in areas if v == area_var.get()), "auto")
            cfg["lang"] = next((k for k, v in langs if v == lang_var.get()), "")
            tab._save_cfg()
            self.send()
            tab.search_options_changed()
            w.destroy()

        ttk.Button(bar, text=t("Cancel"), style="Card.TButton", command=w.destroy).pack(side="right")
        ttk.Button(bar, text=t("Save"), style="Card.Accent.TButton", command=save).pack(side="right",
                                                                                       padx=(0, px(8)))
        return w

    def send(self):
        """Area / language / Wi-Fi to the server now (a change in the window)."""
        c = self.tab.client
        if c is not None and c.me and c.has_feature("mm_filters"):
            self.tab.call(c.send_netinfo, **self.client_netinfo())
