"""The launcher's look: one dark ttk theme, its fonts and colours, and a few drawn pieces.

    from t5lobby import theme
    th = theme.apply(root)          # once per Tk interpreter (later calls return the same Theme)
    ttk.Button(card, text="Accept", style="Card.Accent.TButton")

Plain Tk 8.6, no image files and no game assets shipped: rounded buttons, cards, check boxes, icons are drawn
here (anti-aliased PNGs made in memory, kept in a cache folder between starts, Tk's own canvas for the rest). Rank
badges are the game's own rank plates once the launcher has read them from the player's unpacked game
(rank_art.py), else a text badge drawn here in the plate's colour. Fonts are
Windows' Segoe UI and Bahnschrift (Segoe UI when Bahnschrift is missing); in Korean and Japanese a Windows
font that has their glyphs (Malgun Gothic, Yu Gothic UI; i18n.FONTS) takes the place of both.

Styles (the prefix names what the widget sits on, so rounded corners blend into it):
    page (no prefix)  the window's background          e.g. "TButton", "Muted.TLabel", "H1.TLabel"
    Card.             a card (surface)                  "Card.TLabel", "Card.Accent.TButton", "Card.TEntry"
    Tile.             a tile inside a card (raised)     "Tile.TLabel", "Tile.Caps.TLabel"
    Err. / Note.      the error / notice banners        "Err.TLabel", "Note.TLabel"
Buttons: "TButton" (secondary), "Accent.TButton" (primary), "Hero.TButton" / "HeroAlt.TButton" (big),
"Ghost.TButton" (text only), "Small.TButton", "Danger.TButton". Frames: "Card.TFrame", "Tile.TFrame",
"Err.TFrame", "Note.TFrame". Labels: "", "Muted", "Faint", "H1", "H2", "H3", "Caps", "Big", "Huge",
"ok", "warn", "error", "Accent", "Mono", "Pill"/"PillAccent"/"PillOk"/"PillBad"/"PillGold". Notebooks: "TNotebook" (a
page's tabs), "Main.TNotebook" (the launcher's own tab row, a size larger); both draw a hairline under the tab row,
no box around the pages.

High DPI: fonts are in points (Tk scales them); every pixel size here goes through Theme.px(), which
follows Tk's scaling (the launcher makes the process DPI-aware before the first window).
"""
import base64
import ctypes
import hashlib
import marshal
import math
import os
import struct
import zlib
import weakref
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from . import i18n
from . import ranks
from .i18n import t
from .rank_art import ART

THEME = "t5dark"

C = {
    # a warm, soft charcoal (never black): the window, cards a step lighter, tiles and inputs another step
    "bg": "#18171c",          # the window
    "surface": "#222027",     # cards
    "raised": "#2c2a32",      # tiles, inputs, secondary buttons
    "hover": "#37353e",
    "pressed": "#1d1c21",
    "line": "#312f38",
    "line_hi": "#4a4752",
    "text": "#f4f1ec",
    "muted": "#bcb6ad",
    "faint": "#8a857e",
    "accent": "#e8472b",      # one accent: Tekken red-orange
    "accent_hi": "#ff6040",
    "accent_lo": "#c03a21",
    "accent_dim": "#4d2a24",  # (kept for callers; a disabled primary button is grey)
    "on_accent": "#ffffff",
    "sel": "#55291f",         # selected row
    "ok": "#52d98b",
    "warn": "#f6bd4a",
    "bad": "#ff6b6b",
    "gold": "#f7c95a",
    "info": "#66b2ff",
    "err_bg": "#341a1d",
    "err_line": "#76312f",
    "note_bg": "#30291a",
    "note_line": "#715b27",
    "ok_bg": "#17301f",
    "bad_bg": "#341a1d",
    "head_hi": "#3d211d",     # the header band's warm end (behind the mark)
}

# Rank tiers (ranks.RANKS index) -> badge colour, by group: the colours of the game's own rank plates.
TIER_GROUPS = [
    (0, 0, "#a18a5b"),        # Beginner (placement): stone
    (1, 9, "#c8372d"),        # 9th .. 1st kyu: red
    (10, 16, "#98a2ae"),      # 1st .. 7th dan: steel
    (17, 22, "#d5d9e0"),      # Shihan .. Champion: silver frame
    (23, 27, "#57b947"),      # Lone Wolf .. Legend: green
    (28, 31, "#2fa6d0"),      # Fujin .. Lord of War: blue
    (32, 36, "#f28a1c"),      # Dragon Lord .. Tekken Lord: fire
]
GUEST_COLOR = "#5d6676"
TIER_ABBR = {0: "B", 17: "SH", 18: "EX", 19: "WA", 20: "MA", 21: "VI", 22: "CH", 23: "LW", 24: "DS", 25: "BK",
             26: "SG", 27: "LG", 28: "FJ", 29: "RJ", 30: "DT", 31: "LoW", 32: "DL", 33: "TL", 34: "DK", 35: "KR",
             36: "KN"}

# what the result banners (Win. / Loss. / Even. styles) are drawn on: a canvas inside one takes this background
GROUNDS = {"Win.": C["ok_bg"], "Loss.": C["bad_bg"], "Even.": C["raised"], "Tile.": C["raised"], "Card.": C["surface"]}

PING_GOOD, PING_OK = 60, 120      # ms: green up to 60, yellow up to 120, red above
_PNG_CACHE = {}                    # (image key, size, scale) -> PNG data: a second window reuses the drawing
_DISK = {"loaded": None, "dirty": False}


def cache_dir():
    """Where the drawn images are kept between starts (drawing them takes ~0.7 s of the launcher's start):
    T5_UI_CACHE (a folder; "0" turns the cache off), else <T5_ONLINE_DIR>\\cache, else
    %LOCALAPPDATA%\\T5DROnline\\cache. Never the program folder."""
    d = os.environ.get("T5_UI_CACHE")
    if d is not None:
        return None if d.strip() in ("", "0", "off") else d
    base = os.environ.get("T5_ONLINE_DIR")
    if base:
        return os.path.join(base, "cache")
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "T5DROnline", "cache")


def _disk_file():
    d = cache_dir()
    if not d:
        return None
    try:
        with open(__file__, "rb") as f:             # a change to the drawing code makes a new file
            tag = hashlib.sha1(f.read()).hexdigest()[:12]
    except OSError:
        return None
    return os.path.join(d, f"theme-{tag}.bin")


def _disk_load():
    """The PNGs drawn by an earlier start (same theme code) into _PNG_CACHE; a bad file is ignored."""
    if _DISK["loaded"] is not None:
        return
    _DISK["loaded"] = path = _disk_file()
    if not path:
        return
    try:
        with open(path, "rb") as f:
            data = marshal.loads(f.read())
    except (OSError, ValueError, EOFError, TypeError):
        return
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, tuple) and len(k) == 4 and isinstance(v, str):
                _PNG_CACHE.setdefault(k, v)


def _disk_save():
    path = _DISK["loaded"]
    if not path or not _DISK["dirty"]:
        return
    _DISK["dirty"] = False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + f".{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            f.write(marshal.dumps({k: v for k, v in _PNG_CACHE.items()
                                   if all(isinstance(x, (str, int, float)) for x in k)}))
        os.replace(tmp, path)
        for name in os.listdir(os.path.dirname(path)):      # files of older theme code
            if name.startswith("theme-") and name.endswith(".bin") and name != os.path.basename(path):
                try:
                    os.remove(os.path.join(os.path.dirname(path), name))
                except OSError:
                    pass
    except OSError:
        pass


def tier_color(tier):
    if tier is None:
        return GUEST_COLOR
    for lo, hi, col in TIER_GROUPS:
        if lo <= tier <= hi:
            return col
    return GUEST_COLOR


def tier_abbr(tier):
    if tier is None:
        return "G"
    if 1 <= tier <= 9:
        return f"{10 - tier}K"
    if 10 <= tier <= 16:
        return f"{tier - 9}D"
    return TIER_ABBR.get(tier, "?")


def ping_quality(ms):
    """'good' | 'ok' | 'bad' | 'unknown'."""
    if ms is None:
        return "unknown"
    return "good" if ms <= PING_GOOD else "ok" if ms <= PING_OK else "bad"


def ping_color(ms):
    return {"good": C["ok"], "ok": C["warn"], "bad": C["bad"]}.get(ping_quality(ms), C["faint"])


def ping_bars(ms):
    """How many of 4 signal bars are lit."""
    if ms is None:
        return 0
    return 4 if ms <= 30 else 3 if ms <= PING_GOOD else 2 if ms <= PING_OK else 1


def ping_word(ms):
    return {"good": t("Good connection"), "ok": t("OK connection"), "bad": t("Laggy connection")}.get(
        ping_quality(ms), t("Ping not known yet"))


# ---------------------------------------------------------------------- colours
def _rgb(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(a, b, t):
    """a -> b by t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex([ra[i] + (rb[i] - ra[i]) * t for i in range(3)])


def luminance(c):
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(c):
    """Readable text colour on a fill."""
    return "#111318" if luminance(c) > 0.35 else "#ffffff"


# ---------------------------------------------------------------------- tiny rasteriser (PNG in memory)
def _png(w, h, rgba):
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))
    return base64.b64encode(png).decode("ascii")


def raster(w, h, layers, ss=4, bg=None, band=None):
    """RGBA bytes of `layers` painted in order: (inside(x, y) -> bool, "#rrggbb", convex). Edges are
    anti-aliased by 4x4 supersampling; a convex shape skips pixels whose four corners agree. With `bg`
    the picture starts from that colour (opaque), else from transparent. `band`: the shapes are
    rectangles with rounded corners no larger than `band` pixels -- only the corner zones and one
    middle row / column are worked out, the rest is copied (much faster)."""
    sub = [(i + 0.5) / ss for i in range(ss)]
    n = float(ss * ss)
    # a colour is "#rrggbb", or a list of (y, "#rrggbb") stops: a vertical gradient (flat before the first stop
    # and after the last -- keep the stops inside an image element's top and bottom border rows, which ttk never
    # tiles, and the gradient never repeats on a large widget)
    cols = [(_rgb(col) if isinstance(col, str) else [(float(y), _rgb(c)) for y, c in col], inside, convex,
             getattr(inside, "bbox", None)) for inside, col, convex in layers]
    graded = any(isinstance(c[0], list) for c in cols)
    b0 = _rgb(bg) if bg else None

    def at(stops, y):
        if y <= stops[0][0]:
            return stops[0][1]
        for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
            if y <= y1:
                t = (y - y0) / ((y1 - y0) or 1.0)
                return tuple(c0[i] + (c1[i] - c0[i]) * t for i in range(3))
        return stops[-1][1]

    def pixel(x, y):
        if b0:
            pr, pg, pb, pa = float(b0[0]), float(b0[1]), float(b0[2]), 1.0
        else:
            pr = pg = pb = pa = 0.0
        for col, inside, convex, bb in cols:
            cr, cg, cb = at(col, y + 0.5) if isinstance(col, list) else col
            if bb is not None and (x + 1 < bb[0] or x > bb[2] or y + 1 < bb[1] or y > bb[3]):
                continue
            if convex:
                k = inside(x, y) + inside(x + 1, y) + inside(x, y + 1) + inside(x + 1, y + 1)
                if k == 0:
                    continue
                cov = 1.0 if k == 4 else sum(inside(x + sx, y + sy) for sy in sub for sx in sub) / n
            else:
                cov = sum(inside(x + sx, y + sy) for sy in sub for sx in sub) / n
            if cov <= 0.0:
                continue
            q = 1.0 - cov
            pr, pg, pb, pa = cr * cov + pr * q, cg * cov + pg * q, cb * cov + pb * q, cov + pa * q
        if pa <= 0.0:
            return bytes(4)
        return bytes((int(pr / pa + 0.5), int(pg / pa + 0.5), int(pb / pa + 0.5), int(pa * 255 + 0.5)))

    if band is None or w < 2 * band + 3 or h < 2 * band + 3:
        out = bytearray()
        for y in range(h):
            for x in range(w):
                out += pixel(x, y)
        return out
    xs = list(range(band)) + [band] + list(range(w - band, w))

    def row(y):
        px_ = {x: pixel(x, y) for x in xs}
        left = b"".join(px_[x] for x in range(band))
        right = b"".join(px_[x] for x in range(w - band, w))
        return left + px_[band] * (w - 2 * band) + right
    if graded:
        return bytearray(b"".join(row(y) for y in range(h)))
    top = [row(y) for y in range(band)]
    mid = row(band)
    bot = [row(y) for y in range(h - band, h)]
    return bytearray(b"".join(top) + mid * (h - 2 * band) + b"".join(bot))


def rrect(x0, y0, x1, y1, r):
    """inside() of a rounded rectangle."""
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))

    def inside(x, y):
        if x < x0 or x > x1 or y < y0 or y > y1:
            return False
        cx = x0 + r if x < x0 + r else (x1 - r if x > x1 - r else x)
        cy = y0 + r if y < y0 + r else (y1 - r if y > y1 - r else y)
        dx, dy = x - cx, y - cy
        return dx * dx + dy * dy <= r * r
    return inside


def circle(cx, cy, r):
    def inside(x, y):
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    return inside


def polygon(pts):
    """inside() of a convex polygon (points in order)."""
    edges = list(zip(pts, pts[1:] + pts[:1]))
    sign = 1 if sum((b[0] - a[0]) * (b[1] + a[1]) for a, b in edges) < 0 else -1

    def inside(x, y):
        for (ax, ay), (bx, by) in edges:
            if sign * ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) < 0:
                return False
        return True
    return inside


def stroke(points, width):
    """inside() of a polyline drawn `width` wide (round joins)."""
    segs = list(zip(points, points[1:]))
    hw2 = (width / 2.0) ** 2
    hw = width / 2.0

    def inside(x, y):
        for (ax, ay), (bx, by) in segs:
            dx, dy = bx - ax, by - ay
            t = ((x - ax) * dx + (y - ay) * dy) / float(dx * dx + dy * dy or 1)
            t = 0.0 if t < 0 else 1.0 if t > 1 else t
            ex, ey = ax + t * dx - x, ay + t * dy - y
            if ex * ex + ey * ey <= hw2:
                return True
        return False
    inside.bbox = (min(p[0] for p in points) - hw, min(p[1] for p in points) - hw,
                   max(p[0] for p in points) + hw, max(p[1] for p in points) + hw)
    return inside


def ring(outer, inner):
    def inside(x, y):
        return outer(x, y) and not inner(x, y)
    return inside


# ---------------------------------------------------------------------- DPI
def enable_dpi_awareness():
    """System DPI awareness before the first window (Tk 8.6 then sizes fonts for the real DPI)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def scale_of(widget):
    """1.0 at 96 DPI, 1.5 at 144, 2.0 at 192 (from Tk's own scaling)."""
    try:
        return max(1.0, float(widget.tk.call("tk", "scaling")) / (96.0 / 72.0))
    except (tk.TclError, ValueError):
        return 1.0


# ---------------------------------------------------------------------- the theme
TEXT_FONTS = ["Inter", "Segoe UI"]                      # body text, in order of preference
DISPLAY_FONTS = ["Rajdhani SemiBold", "Barlow Condensed SemiBold", "Bahnschrift SemiBold Condensed",
                 "Bahnschrift SemiBold"]                  # titles, tabs, big buttons
DISPLAY_REGULAR = ["Rajdhani", "Barlow Condensed", "Bahnschrift Condensed", "Bahnschrift"]
CAPS_FONTS = ["Rajdhani SemiBold", "Barlow SemiBold", "Bahnschrift SemiBold"]   # small capitals: not condensed


def pick(families, wanted):
    """The first of `wanted` that is installed (or loaded by load_fonts), else None."""
    for name in wanted:
        if name in families:
            return name
    return None


FONT_DIRS = (os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),)
_LOADED_FONTS = []


def load_fonts(dirs=FONT_DIRS):
    """Freely licensed fonts shipped with the launcher (t5lobby/fonts/*.ttf|otf, each with its licence file) for
    this process only (Windows: AddFontResourceExW with FR_PRIVATE -- nothing is installed); before the first
    window. Without them (or elsewhere) the system fonts above are used. -> the files loaded."""
    if _LOADED_FONTS or os.name != "nt":
        return list(_LOADED_FONTS)
    try:
        add = ctypes.windll.gdi32.AddFontResourceExW
    except (AttributeError, OSError):
        return []
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for name in names:
            if name.lower().endswith((".ttf", ".otf")):
                path = os.path.join(d, name)
                try:
                    if add(ctypes.c_wchar_p(path), 0x10, 0):          # FR_PRIVATE
                        _LOADED_FONTS.append(path)
                except OSError:
                    pass
    return list(_LOADED_FONTS)


class Theme:
    def __init__(self, root):
        self.root = root
        self.s = scale_of(root)
        self.images = {}            # every PhotoImage made here (Tk drops an image nobody holds)
        self.fonts = {}
        self._measure_fonts = {}
        self._element_names = None
        self.style = ttk.Style(root)
        load_fonts()
        self._fonts()
        _disk_load()
        self._build()
        _disk_save()

    def px(self, v):
        return int(round(v * self.s))

    @property
    def shadow(self):
        """How deep a card's shadow is (px): the bottom of its image element (tab_look's cards use the same)."""
        return max(2, self.px(3))

    def photo(self, key, w, h, layers, bg=None, band=None):
        """A PhotoImage drawn from `layers` (see raster); opaque on `bg` when given (fast to draw)."""
        img = self.images.get(key)
        if img is None:
            ck = (key, w, h, self.s)
            data = _PNG_CACHE.get(ck)
            if data is None:
                ss = 4 if self.s < 1.4 else 3          # (edges are already finer at high DPI)
                data = _PNG_CACHE[ck] = _png(w, h, raster(w, h, layers, ss=ss, bg=bg, band=band))
                _DISK["dirty"] = True
            img = tk.PhotoImage(master=self.root, data=data)
            self.images[key] = img
        return img

    # --- fonts
    def _fonts(self):
        try:
            fams = set(tkfont.families(self.root))
        except tk.TclError:
            fams = set()
        ui = pick(fams, TEXT_FONTS) or ("Segoe UI" if not fams else "TkDefaultFont")
        semi = pick(fams, [f + " Semibold" for f in TEXT_FONTS] + [f + " SemiBold" for f in TEXT_FONTS]) or ui
        # titles, tabs and big buttons: a condensed, sporty face (a shipped one when loaded, else Windows' own)
        disp = pick(fams, DISPLAY_FONTS) or semi
        disp_reg = pick(fams, DISPLAY_REGULAR) or ui
        caps = pick(fams, CAPS_FONTS) or semi
        mono = "Consolas" if "Consolas" in fams or not fams else "TkFixedFont"
        heavy = "normal"                  # the weight of semi / disp (they are semibold families already)
        cjk = i18n.ui_family(None, fams)  # Korean / Japanese: a font with their glyphs (i18n.FONTS)
        if cjk:
            ui = disp_reg = cjk
            semi = disp = caps = cjk + " Semibold" if cjk + " Semibold" in fams else cjk
            heavy = "normal" if semi != cjk else "bold"
        spec = {
            "body": (ui, 10, "normal"), "small": (ui, 9, "normal"), "bold": (semi, 10, heavy),
            "button": (semi, 10, heavy), "tab": (disp, 12, heavy), "maintab": (disp, 13, heavy),
            "h1": (disp, 22, heavy), "h2": (disp, 15, heavy), "h3": (disp, 13, heavy),
            "caps": (caps, 9, heavy), "hero": (disp, 16, heavy), "big": (disp, 28, heavy),
            "huge": (disp, 32, heavy), "num": (disp, 14, heavy), "mono": (mono, 10, "normal"),
            "code": (mono, 14, "normal"), "brand": (disp, 20, heavy),
        }
        existing = set(tkfont.names(self.root))
        for key, (fam, size, weight) in spec.items():
            name = "T5" + key.capitalize()
            if name in existing:
                f = tkfont.nametofont(name, root=self.root)
                f.configure(family=fam, size=size, weight=weight)
            else:
                f = tkfont.Font(root=self.root, name=name, family=fam, size=size, weight=weight)
            self.fonts[key] = f
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(name, root=self.root).configure(family=ui, size=10)
            except tk.TclError:
                pass

    def font(self, key):
        return self.fonts[key]

    def measure(self, family, size, text, weight="bold"):
        """Width of `text` in pixels (fonts made once per family / size)."""
        f = self._measure_fonts.get((family, size, weight))
        if f is None:
            f = self._measure_fonts[(family, size, weight)] = tkfont.Font(root=self.root, family=family, size=size,
                                                                          weight=weight)
        return f.measure(text)

    # --- images (opaque: every corner is blended into the colour it sits on, so Tk copies them as plain
    # bitmaps; partly transparent images are blended by Tk in software, tile by tile, which is very slow)
    def _rounded(self, key, w, h, r, fill, bg, line=None, line_w=1, ring_col=None, ring_w=2):
        layers = []
        if ring_col:
            layers.append((rrect(0, 0, w, h, r), ring_col, True))
            d = ring_w
            layers.append((rrect(d, d, w - d, h - d, r - d), fill, True))
        elif line:
            layers.append((rrect(0, 0, w, h, r), line, True))
            d = line_w
            layers.append((rrect(d, d, w - d, h - d, r - d), fill, True))
        elif fill:
            layers.append((rrect(0, 0, w, h, r), fill, True))
        return self.photo(key, w, h, layers, bg, band=int(r) + 3)

    def _panel(self, key, w, h, r, fill, bg, line=None, shadow=0):
        """A card / tile image: lighter at the top edge (fill and border fade into their colour within the
        corner rows), a soft shadow `shadow` px deep under it."""
        lit = max(1, r)
        layers = []
        if shadow:
            layers.append((rrect(0, shadow * 0.5, w, h, r + 1), mix(bg, "#000000", 0.22), True))
            layers.append((rrect(1, shadow, w - 1, h, r), mix(bg, "#000000", 0.38), True))
        hb = h - shadow
        if line:
            layers.append((rrect(0, 0, w, hb, r), [(0, mix(line, "#ffffff", 0.10)), (lit, line)], True))
            layers.append((rrect(1, 1, w - 1, hb - 1, r - 1), [(0, mix(fill, "#ffffff", 0.045)), (lit, fill)], True))
        else:
            layers.append((rrect(0, 0, w, hb, r), [(0, mix(fill, "#ffffff", 0.06)), (lit, fill)], True))
        return self.photo(key, w, h, layers, bg, band=int(r) + 3)

    def _ring_only(self, key, w, h, r, col, width, bg):
        d = width
        return self.photo(key, w, h, [(ring(rrect(0, 0, w, h, r), rrect(d, d, w - d, h - d, r - d)), col, False)],
                          bg, band=int(r) + 3)

    def _blank(self, key, w, h, bg=None):
        return self.photo(key, w, h, [], bg, band=2)

    def _element(self, name, *args, **kw):
        if name not in self._elements():
            self.style.element_create(name, "image", *args, **kw)
            self._element_names.add(name)

    # ttk draws the middle and the edges of an image element by tiling (one image copy per tile), so a 32 px
    # button image on a 200 px button, or a 72 px card image on a 1000 x 400 card, costs dozens to hundreds of
    # copies every time the window is redrawn (each resize step redrew the Online tab in ~0.8 s). The images are
    # drawn with a large middle instead (one or a few tiles); -width / -height keep each element's least size
    # what the small image gave.
    SLICE = {"frame": (320, 160), "button": (96, 30), "field": (240, 24), "pill": (64, 6), "tab": (160, 0)}

    def _sliced(self, kind, size):
        """(w, h) of a 9-slice image of least size `size` (a square) with the large middle of `kind`."""
        sw, sh = self.SLICE[kind]
        return size + self.px(sw), size + self.px(sh)

    # --- ttk
    def _build(self):
        st, px = self.style, self.px
        if THEME not in st.theme_names():
            st.theme_create(THEME, parent="clam")
        st.theme_use(THEME)
        if isinstance(self.root, (tk.Tk, tk.Toplevel)):
            self.root.configure(background=C["bg"])
        f = self.fonts
        st.configure(".", background=C["bg"], foreground=C["text"], font=f["body"], bordercolor=C["line"],
                     lightcolor=C["surface"], darkcolor=C["surface"], troughcolor=C["raised"],
                     fieldbackground=C["raised"], selectbackground=C["sel"], selectforeground=C["text"],
                     insertcolor=C["text"], focuscolor=C["accent"], arrowcolor=C["muted"],
                     disabledforeground=C["faint"])
        st.map(".", foreground=[("disabled", C["faint"])])

        # frames: cards on the page, tiles on cards, banners
        st.configure("TFrame", background=C["bg"])
        for name, fill, line, on, r, center, pad in (
                ("Card", C["surface"], C["line"], C["bg"], 12, 48, px(14)),
                ("Tile", C["raised"], None, C["surface"], 8, 32, (px(12), px(8))),
                ("Err", C["err_bg"], C["err_line"], C["bg"], 8, 32, (px(12), px(8))),
                ("Note", C["note_bg"], C["note_line"], C["bg"], 8, 32, (px(12), px(8))),
                ("Win", C["ok_bg"], mix(C["ok"], C["ok_bg"], 0.55), C["surface"], 8, 32, (px(12), px(8))),
                ("Loss", C["bad_bg"], mix(C["bad"], C["bad_bg"], 0.6), C["surface"], 8, 32, (px(12), px(8))),
                ("Even", C["raised"], C["line_hi"], C["surface"], 8, 32, (px(12), px(8)))):
            rr = px(r)
            size = 2 * rr + px(center)
            w, h = self._sliced("frame", size)
            # every frame is lit from above: its top edge and border a little lighter; a card on the page also
            # throws a soft shadow under itself
            sh = self.shadow if name == "Card" else 0
            img = self._panel("frame_" + name, w, h + sh, rr, fill, on, line, sh)
            self._element(f"{name}.bg", img, border=(rr + 1, rr + 1, rr + 1, rr + 1 + sh), sticky="nsew",
                          width=size, height=size + sh)
            st.layout(f"{name}.TFrame", [(f"{name}.bg", {"sticky": "nsew"})])
            st.configure(f"{name}.TFrame", background=on, padding=pad)
        # plain frames inside a card / tile / banner (rows of widgets)
        for name, bg in (("CardBody", C["surface"]), ("TileBody", C["raised"]), ("ErrBody", C["err_bg"]),
                         ("NoteBody", C["note_bg"]), ("WinBody", C["ok_bg"]), ("LossBody", C["bad_bg"]),
                         ("EvenBody", C["raised"])):
            st.configure(f"{name}.TFrame", background=bg)

        # labels: a role (font, colour) on each background
        containers = {"": C["bg"], "Card.": C["surface"], "Tile.": C["raised"], "Err.": C["err_bg"],
                      "Note.": C["note_bg"], "Win.": C["ok_bg"], "Loss.": C["bad_bg"], "Even.": C["raised"]}
        roles = {
            "": dict(font=f["body"], foreground=C["text"]),
            "Muted.": dict(font=f["body"], foreground=C["muted"]),
            "Small.": dict(font=f["small"], foreground=C["muted"]),
            "Faint.": dict(font=f["small"], foreground=C["faint"]),
            "Bold.": dict(font=f["bold"], foreground=C["text"]),
            "H1.": dict(font=f["h1"], foreground=C["text"]),
            "H2.": dict(font=f["h2"], foreground=C["text"]),
            "H3.": dict(font=f["h3"], foreground=C["text"]),
            "Caps.": dict(font=f["caps"], foreground=C["muted"]),
            "Big.": dict(font=f["big"], foreground=C["text"]),
            "Huge.": dict(font=f["huge"], foreground=C["text"]),
            "Num.": dict(font=f["num"], foreground=C["text"]),
            "Mono.": dict(font=f["mono"], foreground=C["text"]),
            "Accent.": dict(font=f["bold"], foreground=C["accent_hi"]),
            "Brand.": dict(font=f["brand"], foreground=C["text"]),           # the launcher's name in its header
            "BrandAccent.": dict(font=f["brand"], foreground=C["accent_hi"]),
            "ok.": dict(foreground=C["ok"]), "warn.": dict(foreground=C["warn"]),
            "error.": dict(foreground=C["bad"]), "gold.": dict(font=f["bold"], foreground=C["gold"]),
        }
        for pre, bg in containers.items():
            for role, opts in roles.items():
                st.configure(f"{pre}{role}TLabel", background=bg, **opts)
        # pills ([RANKED], [CASUAL] ...): rounded labels
        rp = px(9)
        psize = 2 * rp + 4                     # (small: the image is also the least size of a pill)
        for name, fill, fg in (("Pill", C["hover"], C["muted"]), ("PillAccent", C["accent"], C["on_accent"]),
                               ("PillOk", mix(C["ok"], C["surface"], 0.2), "#08130c"),
                               ("PillBad", mix(C["bad"], C["surface"], 0.15), "#1a0707"),
                               ("PillGold", C["gold"], "#1d1704"), ("PillWarn", C["warn"], "#1d1404")):
            for pre, bg in (("", C["bg"]), ("Card.", C["surface"]), ("Tile.", C["raised"]),
                            ("Win.", C["ok_bg"]), ("Loss.", C["bad_bg"]), ("Even.", C["raised"])):
                img = self._rounded(f"pill_{name}_{pre}", *self._sliced("pill", psize), rp, fill, bg)
                self._element(f"{pre}{name}.bg", img, border=rp + 1, padding=(rp + 1, max(1, px(1))), sticky="nsew",
                              width=psize, height=psize)
                st.layout(f"{pre}{name}.TLabel", [(f"{pre}{name}.bg", {"sticky": "nsew", "children": [
                    ("Label.padding", {"sticky": "nsew", "children": [("Label.label", {"sticky": "nsew"})]})]})])
                st.configure(f"{pre}{name}.TLabel", background=bg, foreground=fg, font=f["caps"],
                             padding=(px(9), px(2)), anchor="center")

        self._buttons()
        self._checks()
        self._fields()
        self._lists()
        self._notebook()
        st.configure("TSeparator", background=C["line"])
        st.configure("Card.TSeparator", background=C["line"])
        st.configure("TLabelframe", background=C["bg"], bordercolor=C["line"], lightcolor=C["bg"],
                     darkcolor=C["bg"], relief="solid", borderwidth=1)
        st.configure("TLabelframe.Label", background=C["bg"], foreground=C["muted"], font=f["h3"])
        st.configure("Horizontal.TProgressbar", troughcolor=C["raised"], background=C["accent"],
                     bordercolor=C["raised"], lightcolor=C["accent"], darkcolor=C["accent"], thickness=px(10))
        st.configure("Vertical.TProgressbar", troughcolor=C["raised"], background=C["accent"],
                     bordercolor=C["raised"], lightcolor=C["accent"], darkcolor=C["accent"])
        self._options()

    def _elements(self):
        if self._element_names is None:
            try:
                self._element_names = set(self.style.element_names())
            except tk.TclError:
                self._element_names = set()
        return self._element_names

    # backgrounds buttons sit on (their corners are blended into it): the page, cards, the error banner
    BUTTON_GROUNDS = (("", "bg"), ("Card.", "surface"), ("Err.", "err_bg"), ("Note.", "note_bg"))

    def _button_family(self, name, fill, hover, pressed, disabled, ring_col, line=None, glow=None):
        """Rounded button elements (one per background) with their states, and their layouts. The body sits
        `g` px inside its image: that margin holds the hover glow and, with the keyboard or a controller, a
        clear focus ring around the button; the body is lit from above (lighter top, darker bottom edge)."""
        st, px = self.style, self.px
        r = px(7)
        g = max(2, px(2))
        size = 2 * (r + g) + px(18)
        w, h = self._sliced("button", size)

        def body(col, edge=None):
            if col is None:
                return []
            stops = [(g, mix(col, "#ffffff", 0.10)), (g + r, col), (h - g - r, col), (h - g, mix(col, "#000000", 0.14))]
            out = []
            if edge:
                out.append((rrect(g, g, w - g, h - g, r), [(g, mix(edge, "#ffffff", 0.12)), (g + r, edge)], True))
                out.append((rrect(g + 1, g + 1, w - g - 1, h - g - 1, r - 1), stops, True))
            else:
                out.append((rrect(g, g, w - g, h - g, r), stops, True))
            return out

        def halo(col):
            return [(rrect(0, 0, w, h, r + g), col, True)] if col else []

        for pre, key in self.BUTTON_GROUNDS:
            bg = C[key]
            soft = mix(glow, bg, 0.5) if glow else None
            imgs = {
                "normal": body(fill, line),
                "hover": halo(soft) + body(hover, line),
                "pressed": body(pressed, line),
                # (disabled: an outline, so the button keeps its shape but plainly cannot be pressed)
                "disabled": body(disabled, C["line"]) if disabled is not None else [],
                "focus": halo(ring_col) + (body(fill, line) if fill is not None else
                                           [(rrect(g, g, w - g, h - g, r), bg, True)]),
                "focus_hover": halo(ring_col) + body(hover or C["hover"], line),
            }
            imgs = {k: self.photo(f"btn_{name}_{k}_{pre}", w, h, layers, bg, band=int(r + g) + 3)
                    for k, layers in imgs.items()}
            el = f"{pre}{name}.bg"
            self._element(el, imgs["normal"], ("disabled", imgs["disabled"]), ("pressed", imgs["pressed"]),
                          ("focus", "active", imgs["focus_hover"]), ("focus", imgs["focus"]),
                          ("active", imgs["hover"]), border=r + g + 1, padding=(r + 2, g + 1, r + 2, g + 1),
                          sticky="nsew", width=size, height=size)
            style = (pre + "TButton") if name == "Base" else f"{pre}{name}.TButton"
            st.layout(style, [(el, {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
            st.configure(style, background=bg, anchor="center", relief="flat")

    def _buttons(self):
        st, px, f = self.style, self.px, self.fonts
        self._button_family("Base", C["raised"], C["hover"], C["pressed"], mix(C["raised"], C["bg"], 0.5),
                            C["accent"], line=C["line_hi"], glow=C["line_hi"])
        # (a primary button that cannot be pressed now looks like any disabled button: grey, not a dim red)
        self._button_family("Accent", C["accent"], C["accent_hi"], C["accent_lo"], mix(C["raised"], C["bg"], 0.5),
                            "#ffffff", glow=C["accent_hi"])
        self._button_family("Ghost", None, C["hover"], C["pressed"], None, C["accent"])
        acc_dis = C["faint"]
        # (style suffix, layout family, font, padding, foreground, disabled / active foreground); the heights:
        # small 28, normal 34, hero 46 px at 100 % (the element adds only room for the focus ring)
        kinds = (("TButton", "Base", f["button"], (px(14), px(5)), C["text"], None),
                 ("Accent.TButton", "Accent", f["button"], (px(16), px(5)), C["on_accent"], acc_dis),
                 ("Hero.TButton", "Accent", f["hero"], (px(22), px(8)), C["on_accent"], acc_dis),
                 ("HeroAlt.TButton", "Base", f["hero"], (px(22), px(8)), C["text"], None),
                 ("Ghost.TButton", "Ghost", f["button"], (px(8), px(5)), C["muted"], "active"),
                 ("Link.TButton", "Ghost", f["body"], (px(6), px(3)), C["accent_hi"], "active"),
                 ("Small.TButton", "Base", f["small"], (px(10), px(3)), C["text"], None),
                 ("Danger.TButton", "Base", f["button"], (px(14), px(5)), C["bad"], None))
        for pre, key in self.BUTTON_GROUNDS:
            for suffix, fam, font, pad, fg, dis in kinds:
                style = pre + suffix
                base_style = (pre + "TButton") if fam == "Base" else f"{pre}{fam}.TButton"
                if style != base_style:
                    st.layout(style, st.layout(base_style))
                st.configure(style, font=font, padding=pad, foreground=fg, background=C[key], anchor="center")
                if dis == "active":
                    st.map(style, foreground=[("disabled", C["faint"]), ("active", C["text"])])
                else:
                    st.map(style, foreground=[("disabled", dis or C["faint"])])

    def _checks(self):
        st, px = self.style, self.px
        b = px(16)
        r = px(4)
        pad = px(1)
        w = b + 2 * pad
        gap = px(7)                       # between the box and its text (drawn into the image, on its right)
        chk = [(pad + b * 0.24, pad + b * 0.53), (pad + b * 0.43, pad + b * 0.72), (pad + b * 0.77, pad + b * 0.30)]
        sw = max(1.6, b * 0.14)
        box = rrect(pad, pad, pad + b, pad + b, r)
        lw = max(1, px(1))
        inner = rrect(pad + lw, pad + lw, pad + b - lw, pad + b - lw, r - lw)
        cx = cy = w / 2.0
        rr = b / 2.0
        for pre, bg in (("", C["bg"]), ("Card.", C["surface"]), ("Tile.", C["raised"])):
            def img(key, fill, line, check=None):
                layers = [(box, line, True), (inner, fill, True)]
                if check:
                    layers.append((stroke(chk, sw), check, False))
                return self.photo(key + pre, w + gap, w, layers, bg)

            def rimg(key, fill, line, dot=None):
                layers = [(circle(cx, cy, rr), line, True), (circle(cx, cy, rr - lw), fill, True)]
                if dot:
                    layers.append((circle(cx, cy, rr * 0.42), dot, True))
                return self.photo(key + pre, w + gap, w, layers, bg)
            self._element(f"{pre}Check.ind", img("chk_off", C["raised"], C["line_hi"]),
                          ("disabled", "selected", img("chk_on_d", C["accent_dim"], C["accent_dim"], C["muted"])),
                          ("disabled", img("chk_off_d", C["surface"], C["line"])),
                          ("selected", "active", img("chk_on_h", C["accent_hi"], C["accent_hi"], "#ffffff")),
                          ("selected", img("chk_on", C["accent"], C["accent"], "#ffffff")),
                          ("active", img("chk_off_h", C["hover"], C["muted"])), sticky="")
            self._element(f"{pre}Radio.ind", rimg("rad_off", C["raised"], C["line_hi"]),
                          ("disabled", "selected", rimg("rad_on_d", C["surface"], C["line"], C["faint"])),
                          ("disabled", rimg("rad_off_d", C["surface"], C["line"])),
                          ("selected", "active", rimg("rad_on_h", C["hover"], C["accent_hi"], C["accent_hi"])),
                          ("selected", rimg("rad_on", C["raised"], C["accent"], C["accent"])),
                          ("active", rimg("rad_off_h", C["hover"], C["muted"])), sticky="")
            for cls, ind in (("TCheckbutton", "Check.ind"), ("TRadiobutton", "Radio.ind")):
                part = "Checkbutton" if cls == "TCheckbutton" else "Radiobutton"
                st.layout(pre + cls, [(f"{part}.padding", {"sticky": "nswe", "children": [
                    (pre + ind, {"side": "left", "sticky": ""}),
                    (f"{part}.focus", {"side": "left", "sticky": "w", "children": [
                        (f"{part}.label", {"sticky": "nswe"})]})]})])
                st.configure(pre + cls, background=bg, foreground=C["text"], padding=(px(2), px(3)),
                             focuscolor=C["accent"], focusthickness=1, indicatormargin=0)
                st.map(pre + cls, foreground=[("disabled", C["faint"])], background=[("active", bg)])
        # a segmented choice: radiobuttons drawn as a tab strip on a raised track
        rs = px(7)
        ssize = 2 * rs + px(18)
        sw, sh = self._sliced("button", ssize)
        track = C["raised"]
        fw = max(2, px(2))
        self._element("Seg.bg", self._blank("seg_off", sw, sh, track),
                      ("selected", "focus", self._rounded("seg_on_f", sw, sh, rs, C["hover"], track,
                                                          ring_col=C["accent"], ring_w=fw)),
                      ("selected", self._rounded("seg_on", sw, sh, rs, C["hover"], track)),
                      ("focus", self._ring_only("seg_f", sw, sh, rs, C["accent"], fw, track)),
                      ("active", self._rounded("seg_h", sw, sh, rs, mix(C["raised"], C["hover"], 0.5), track)),
                      border=rs + 2, padding=(rs + 2, max(2, px(2))), sticky="nsew", width=ssize, height=ssize)
        st.layout("Seg.TRadiobutton", [("Seg.bg", {"sticky": "nsew", "children": [
            ("Radiobutton.padding", {"sticky": "nsew", "children": [("Radiobutton.label", {"sticky": "nsew"})]})]})])
        st.configure("Seg.TRadiobutton", background=track, foreground=C["muted"], font=self.fonts["button"],
                     padding=(px(12), px(5)), anchor="center")
        st.map("Seg.TRadiobutton", foreground=[("selected", C["text"]), ("active", C["text"])],
               background=[("active", track)])
        tsize = 2 * (rs + 1) + px(18)
        self._element("SegTrack.bg", self._rounded("seg_track", *self._sliced("field", tsize), rs + 1, track,
                                                   C["surface"]),
                      border=rs + 3, sticky="nsew", width=tsize, height=tsize)
        st.layout("SegTrack.TFrame", [("SegTrack.bg", {"sticky": "nsew"})])
        st.configure("SegTrack.TFrame", background=C["surface"], padding=px(3))

    def _fields(self):
        st, px = self.style, self.px
        r = px(6)
        size = 2 * r + px(18)
        lw = max(1, px(1))
        aw, ah = px(26), px(14)
        cw = px(5)
        mid = aw / 2.0 - px(2)
        chev = [(mid - cw, ah / 2.0 - cw / 2.0), (mid, ah / 2.0 + cw / 2.0), (mid + cw, ah / 2.0 - cw / 2.0)]
        sw = max(1.6, px(2))
        # the chevron sits on the field's fill (raised; surface when disabled)
        self._element("Chevron.arrow", self.photo("chev", aw, ah, [(stroke(chev, sw), C["muted"], False)], C["raised"]),
                      ("disabled", self.photo("chev_d", aw, ah, [(stroke(chev, sw), C["faint"], False)], C["surface"])),
                      ("active", self.photo("chev_h", aw, ah, [(stroke(chev, sw), C["text"], False)], C["raised"])),
                      ("pressed", self.photo("chev_p", aw, ah, [(stroke(chev, sw), C["text"], False)], C["raised"])),
                      sticky="")
        fw, fh = self._sliced("field", size)
        for pre, bg in (("", C["bg"]), ("Card.", C["surface"]), ("Tile.", C["raised"])):
            el = f"{pre}Field.bg"
            self._element(el, self._rounded("field" + pre, fw, fh, r, C["raised"], bg, line=C["line_hi"], line_w=lw),
                          ("disabled", self._rounded("field_d" + pre, fw, fh, r, C["surface"], bg, line=C["line"],
                                                     line_w=lw)),
                          ("focus", self._rounded("field_f" + pre, fw, fh, r, C["raised"], bg, line=C["accent"],
                                                  line_w=max(2, px(2)))),
                          ("active", self._rounded("field_h" + pre, fw, fh, r, C["raised"], bg, line=C["muted"],
                                                   line_w=lw)),
                          border=r + 2, padding=(r + 2, max(2, px(2)), r + 2, max(2, px(2))), sticky="nsew",
                          width=size, height=size)
            st.layout(pre + "TEntry", [(el, {"sticky": "nswe", "children": [
                ("Entry.padding", {"sticky": "nswe", "children": [("Entry.textarea", {"sticky": "nswe"})]})]})])
            st.configure(pre + "TEntry", background=bg, foreground=C["text"], fieldbackground=C["raised"],
                         insertcolor=C["text"], padding=(px(9), px(6)), selectbackground=C["sel"],
                         selectforeground=C["text"], insertwidth=max(1, px(1)))
            st.map(pre + "TEntry", foreground=[("disabled", C["faint"])], fieldbackground=[("disabled", C["surface"])])
            st.layout(pre + "TCombobox", [(el, {"sticky": "nswe", "children": [
                ("Chevron.arrow", {"side": "right", "sticky": "ns"}),
                ("Combobox.padding", {"sticky": "nswe", "children": [("Combobox.textarea", {"sticky": "nswe"})]})]})])
            st.configure(pre + "TCombobox", background=bg, foreground=C["text"], fieldbackground=C["raised"],
                         insertcolor=C["text"], padding=(px(9), px(6), px(2), px(6)), selectbackground=C["raised"],
                         selectforeground=C["text"], arrowsize=px(12))
            st.map(pre + "TCombobox", foreground=[("disabled", C["faint"])],
                   fieldbackground=[("readonly", C["raised"]), ("disabled", C["surface"])],
                   selectbackground=[("readonly", C["raised"]), ("!readonly", "focus", C["sel"])],
                   selectforeground=[("readonly", C["text"])])
        st.configure("ComboboxPopdownFrame", background=C["raised"], bordercolor=C["line_hi"], relief="solid",
                     borderwidth=1)

    def _lists(self):
        st, px, f = self.style, self.px, self.fonts
        st.configure("Treeview", background=C["surface"], fieldbackground=C["surface"], foreground=C["text"],
                     bordercolor=C["surface"], lightcolor=C["surface"], darkcolor=C["surface"],
                     rowheight=px(24), font=f["body"], borderwidth=0, padding=0, indent=px(4))
        st.configure("Lobby.Treeview", rowheight=px(28))
        st.map("Treeview", background=[("selected", "focus", C["sel"]), ("selected", mix(C["sel"], C["surface"], 0.35))],
               foreground=[("selected", C["text"]), ("disabled", C["faint"])])
        st.configure("Treeview.Heading", background=C["surface"], foreground=C["faint"], font=f["caps"],
                     relief="flat", borderwidth=0, bordercolor=C["line"], lightcolor=C["surface"],
                     darkcolor=C["line"], padding=(px(8), px(5)))
        st.map("Treeview.Heading", background=[("active", C["raised"])], foreground=[("active", C["muted"])])
        st.layout("Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.image", {"side": "left", "sticky": ""}),
            ("Treeitem.focus", {"side": "left", "sticky": "", "children": [("Treeitem.text", {"side": "left",
                                                                                             "sticky": ""})]})]})])
        st.configure("Treeview.Item", padding=(px(6), 0))
        # column headings: a hairline under them (lists sit on cards)
        lw = max(1, px(1))
        hw, hh = px(320), px(24)
        self._element("Heading.line", self.photo("tv_head", hw, hh, [(lambda x, y: y >= hh - lw, C["line"], True)],
                                                 C["surface"]),
                      ("active", self.photo("tv_head_h", hw, hh, [(lambda x, y: y >= hh - lw, C["line_hi"], True)],
                                            C["raised"])),
                      border=(0, 0, 0, lw), padding=(0, 0, 0, lw), sticky="nsew", width=px(8), height=lw + 1)
        st.layout("Treeview.Heading", [("Heading.line", {"sticky": "nswe", "children": [
            ("Treeheading.padding", {"sticky": "nswe", "children": [
                ("Treeheading.image", {"side": "right", "sticky": ""}),
                ("Treeheading.text", {"sticky": "we"})]})]})])
        # thin scroll bars without arrows
        for orient in ("Vertical", "Horizontal"):
            st.layout(f"{orient}.TScrollbar", [(f"{orient}.Scrollbar.trough", {"sticky": "nswe", "children": [
                (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
            st.configure(f"{orient}.TScrollbar", troughcolor=C["surface"], background=C["line"],
                         bordercolor=C["surface"], lightcolor=C["line"], darkcolor=C["line"],
                         arrowsize=px(10), gripcount=0, relief="flat", borderwidth=0)
            st.map(f"{orient}.TScrollbar", background=[("pressed", C["line_hi"]), ("active", C["line_hi"])],
                   lightcolor=[("active", C["line_hi"])], darkcolor=[("active", C["line_hi"])])

    def _notebook(self):
        st, px, f = self.style, self.px, self.fonts
        bar = max(2, px(3))
        w0, h = px(32), px(8) + bar
        w = self._sliced("tab", w0)[0]
        bg = C["bg"]
        self._element("Tab.line", self._blank("tab_n", w, h, bg),
                      ("selected", self.photo("tab_s", w, h, [(lambda x, y: y >= h - bar, C["accent"], True)], bg)),
                      ("active", self.photo("tab_h", w, h, [(lambda x, y: y >= h - max(1, px(1)), C["line_hi"], True)],
                                            bg)),
                      border=(px(3), px(3), px(3), bar), sticky="nsew", width=w0, height=h)
        st.layout("TNotebook.Tab", [("Tab.line", {"sticky": "nswe", "children": [
            ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
                ("Notebook.focus", {"side": "top", "sticky": "nswe", "children": [
                    ("Notebook.label", {"side": "top", "sticky": ""})]})]})]})])
        st.configure("TNotebook", background=C["bg"], borderwidth=0, bordercolor=C["line"], lightcolor=C["bg"],
                     darkcolor=C["bg"], tabmargins=(0, 0, 0, 0), tabposition="nw")
        st.configure("TNotebook.Tab", background=C["bg"], foreground=C["muted"], font=f["tab"],
                     padding=(px(14), px(5), px(14), px(6)), focuscolor=C["accent"], borderwidth=0)
        st.map("TNotebook.Tab", foreground=[("selected", C["text"]), ("active", C["text"])],
               background=[("selected", C["bg"])], expand=[("selected", (0, 0, 0, 0))])
        # no box around the pages: one hairline under the tab row, the selected tab's accent bar standing on it
        lw = max(1, px(1))
        cw = px(64)
        self._element("Line.client", self.photo("nb_client", cw, cw, [(lambda x, y: y < lw, C["line"], True)], bg),
                      border=(0, lw, 0, 0), padding=(0, lw, 0, 0), sticky="nsew")
        st.layout("TNotebook", [("Line.client", {"sticky": "nswe"})])
        # the launcher's own tab row (Build, Play offline, ... : Main.TNotebook) a size larger than a page's tabs
        st.layout("Main.TNotebook", [("Line.client", {"sticky": "nswe"})])
        st.configure("Main.TNotebook", background=C["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0), tabposition="nw")
        st.layout("Main.TNotebook.Tab", st.layout("TNotebook.Tab"))
        st.configure("Main.TNotebook.Tab", background=C["bg"], foreground=C["muted"], font=f["maintab"],
                     padding=(px(16), px(5), px(18), px(5)), focuscolor=C["accent"], borderwidth=0)
        st.map("Main.TNotebook.Tab", foreground=[("selected", C["text"]), ("active", C["text"])],
               background=[("selected", C["bg"])], expand=[("selected", (0, 0, 0, 0))])

    def _options(self):
        """Classic Tk widgets (Text, Listbox, the combobox drop-down, simple dialogs) in the same colours."""
        o = self.root.option_add
        pri = "widgetDefault"
        for cls in ("Text", "Listbox", "Entry"):
            o(f"*{cls}.background", C["raised"], pri)
            o(f"*{cls}.foreground", C["text"], pri)
            o(f"*{cls}.selectBackground", C["sel"], pri)
            o(f"*{cls}.selectForeground", C["text"], pri)
            o(f"*{cls}.insertBackground", C["text"], pri)
            o(f"*{cls}.relief", "flat", pri)
            o(f"*{cls}.borderWidth", 0, pri)
            o(f"*{cls}.highlightThickness", 1, pri)
            o(f"*{cls}.highlightBackground", C["line"], pri)
            o(f"*{cls}.highlightColor", C["accent"], pri)
        o("*TCombobox*Listbox.background", C["raised"], pri)
        o("*TCombobox*Listbox.foreground", C["text"], pri)
        o("*TCombobox*Listbox.selectBackground", C["sel"], pri)
        o("*TCombobox*Listbox.selectForeground", C["text"], pri)
        o("*TCombobox*Listbox.font", self.fonts["body"], pri)
        o("*TCombobox*Listbox.highlightThickness", 0, pri)
        for cls in ("Toplevel", "Frame", "Label", "Button", "Canvas", "Checkbutton", "Radiobutton", "Message"):
            o(f"*{cls}.background", C["bg"], pri)
        for cls in ("Label", "Button", "Checkbutton", "Radiobutton", "Message"):
            o(f"*{cls}.foreground", C["text"], pri)
        o("*Button.activeBackground", C["hover"], pri)
        o("*Button.activeForeground", C["text"], pri)
        o("*Button.relief", "flat", pri)
        o("*Canvas.highlightThickness", 0, pri)
        o("*Menu.background", C["raised"], pri)
        o("*Menu.foreground", C["text"], pri)
        o("*Menu.activeBackground", C["sel"], pri)
        o("*Menu.activeForeground", C["text"], pri)

    # --- drawn pieces (canvas images)
    def badge_image(self, tier, size):
        """A hexagon badge in the tier's colour (the abbreviation goes on top as canvas text)."""
        col = tier_color(tier)
        key = f"badge_{col}_{size}"
        if key in self.images:
            return self.images[key]
        w = size
        h = int(round(size * 1.12))
        cx = w / 2.0
        top, bot = 0.5, h - 0.5
        q = (bot - top) / 4.0
        outer = [(cx, top), (w - 0.5, top + q), (w - 0.5, bot - q), (cx, bot), (0.5, bot - q), (0.5, top + q)]
        d = max(1.5, size * 0.07)
        inner = [(cx, top + d), (w - 0.5 - d * 0.87, top + q + d * 0.5), (w - 0.5 - d * 0.87, bot - q - d * 0.5),
                 (cx, bot - d), (0.5 + d * 0.87, bot - q - d * 0.5), (0.5 + d * 0.87, top + q + d * 0.5)]
        inside = polygon(inner)
        layers = [(polygon(outer), mix(col, "#ffffff", 0.35), True), (inside, col, True),
                  (lambda x, y: y > h * 0.55 and inside(x, y), mix(col, "#000000", 0.22), True)]
        return self.photo(key, w, h, layers)

    def tier_icon(self, tier):
        """A small hexagon for list rows."""
        return self.badge_image(tier, self.px(14))

    def plate_image(self, col, w, h, bg=None):
        """The text badge's plate: a rounded bar in the tier colour with a lighter rim and a darker lower half
        (opaque on `bg`: fast to draw)."""
        key = f"plate_{col}_{w}_{h}_{bg}"
        if key in self.images:
            return self.images[key]
        r = h * 0.28
        d = max(1.5, h * 0.06)
        inner = rrect(d, d, w - d, h - d, r - d)
        layers = [(rrect(0, 0, w, h, r), mix(col, "#ffffff", 0.35), True), (inner, col, True),
                  (lambda x, y: y > h * 0.55 and inner(x, y), mix(col, "#000000", 0.18), True)]
        return self.photo(key, w, h, layers, bg)

    def list_plate(self):
        """Height of the plates in list rows (pixels)."""
        return self.px(22)

    def row_image(self, icon, tier):
        """A list row's picture: `icon` (ping bars, a friend's dot; may be None) and the game's rank plate next to
        it (none for a guest). Plain `icon` while the plates are not there."""
        h = self.list_plate()
        plate = ART.image(self.root, tier, h) if tier is not None else None
        if plate is None:
            return icon if icon is not None else self.empty_icon()
        key = ("row", str(icon) if icon is not None else "", tier, h)
        img = self.images.get(key)
        if img is None:
            gap = self.px(6)
            iw = icon.width() if icon is not None else 0
            slot = max(iw, self.px(20))
            w = slot + gap + plate.width() if icon is not None else plate.width()
            hh = max(h, icon.height() if icon is not None else 0)
            img = tk.PhotoImage(master=self.root, width=w, height=hh)
            img.blank()
            if icon is not None:
                img.tk.call(img, "copy", icon, "-to", (slot - iw) // 2, (hh - icon.height()) // 2)
            img.tk.call(img, "copy", plate, "-to", w - plate.width(), (hh - plate.height()) // 2)
            self.images[key] = img
        return img

    def ping_icon(self, ms):
        """Four signal bars (lit by ping, coloured by quality) for list rows."""
        n = ping_bars(ms)
        col = ping_color(ms)
        key = f"pingicon_{n}_{col}"
        if key in self.images:
            return self.images[key]
        px = self.px
        bw, gap = max(2, px(3)), max(1, px(2))
        w = 4 * bw + 3 * gap + 2
        h = px(14)
        layers = []
        for i in range(4):
            x0 = 1 + i * (bw + gap)
            bh = h * (0.35 + 0.65 * (i + 1) / 4.0)
            layers.append((rrect(x0, h - bh, x0 + bw, h, 0.8), col if i < n else C["line_hi"], True))
        return self.photo(key, w, h, layers)

    def presence_icon(self, status):
        """A friend's dot for list rows: green online, yellow in a match, a grey ring offline."""
        col = {"online": C["ok"], "in_match": C["warn"]}.get(status)
        key = f"presence_{status}_{col}"
        if key in self.images:
            return self.images[key]
        px = self.px
        w = h = px(14)
        r = w * 0.32
        if col:
            layers = [(circle(w / 2.0, h / 2.0, r), col, True)]
        else:
            layers = [(ring(circle(w / 2.0, h / 2.0, r), circle(w / 2.0, h / 2.0, r - max(1.4, px(2)))),
                       C["faint"], False)]
        return self.photo(key, w, h, layers)

    def lock_icon(self, col=None):
        col = col or C["muted"]
        key = f"lock_{col}"
        if key in self.images:
            return self.images[key]
        px = self.px
        w, h = px(14), px(16)
        lw = max(1.4, px(2))
        cx = w / 2.0
        shack_r = w * 0.30
        top = lw / 2 + 0.5
        body_top = h * 0.45
        outer = rrect(cx - shack_r - lw / 2, top - lw / 2, cx + shack_r + lw / 2, body_top + shack_r, shack_r + lw / 2)
        inner = rrect(cx - shack_r + lw / 2, top + lw / 2, cx + shack_r - lw / 2, body_top + shack_r,
                      shack_r - lw / 2)
        layers = [(lambda x, y: y < body_top + 1 and outer(x, y) and not inner(x, y), col, False),
                  (rrect(1, body_top, w - 1, h - 0.5, px(2)), col, True)]
        return self.photo(key, w, h, layers)

    def icon(self, name, col=None, size=18, bg=None):
        """One of the launcher's own line icons (drawn here, nothing from the game): "build" (a hammer), "play"
        (a play button), "settings" (a gear), "online" (a globe), "replays" (a film strip), in `col` on `bg`."""
        col, bg = col or C["muted"], bg or C["bg"]
        d = self.px(size)
        key = f"icon_{name}_{col}_{bg}_{d}"
        if key in self.images:
            return self.images[key]
        lw = max(1.6, d * 0.11)
        c = d / 2.0
        if name == "build":
            layers = [(stroke([(d * 0.2, d * 0.84), (d * 0.62, d * 0.42)], lw * 1.2), col, False),
                      (polygon([(d * 0.42, d * 0.3), (d * 0.66, d * 0.06), (d * 0.94, d * 0.34), (d * 0.7, d * 0.58)]),
                       col, True)]
        elif name == "play":
            layers = [(ring(circle(c, c, d * 0.46), circle(c, c, d * 0.46 - lw)), col, False),
                      (polygon([(d * 0.4, d * 0.3), (d * 0.72, c), (d * 0.4, d * 0.7)]), col, True)]
        elif name == "settings":
            teeth = []
            for i in range(8):
                a = i * math.pi / 4
                ca, sa = math.cos(a), math.sin(a)
                pts = [(c + ca * r0 - sa * t0, c + sa * r0 + ca * t0) for r0, t0 in
                       ((d * 0.3, -d * 0.08), (d * 0.48, -d * 0.07), (d * 0.48, d * 0.07), (d * 0.3, d * 0.08))]
                teeth.append((polygon(pts), col, True))
            layers = teeth + [(ring(circle(c, c, d * 0.36), circle(c, c, d * 0.15)), col, False)]
        elif name == "online":
            r0 = d * 0.45
            meridian = lambda x, y: ((x - c) / (r0 * 0.45)) ** 2 + ((y - c) / r0) ** 2   # noqa: E731
            layers = [(ring(circle(c, c, r0), circle(c, c, r0 - lw)), col, False),
                      (lambda x, y: abs(meridian(x, y) - 1.0) < lw / r0 * 1.6 and (x - c) ** 2 + (y - c) ** 2 <= r0 ** 2,
                       col, False),
                      (stroke([(d * 0.08, c), (d * 0.92, c)], lw * 0.9), col, False)]
        else:                                                    # replays: a film strip
            layers = [(ring(rrect(d * 0.06, d * 0.18, d * 0.94, d * 0.82, d * 0.1),
                            rrect(d * 0.06 + lw, d * 0.18 + lw, d * 0.94 - lw, d * 0.82 - lw, d * 0.05)), col, False),
                      (polygon([(d * 0.42, d * 0.36), (d * 0.64, c), (d * 0.42, d * 0.64)]), col, True)]
            for i in range(4):
                x0 = d * (0.18 + i * 0.19)
                layers.append((rrect(x0, d * 0.06, x0 + d * 0.09, d * 0.15, 1), col, True))
                layers.append((rrect(x0, d * 0.85, x0 + d * 0.09, d * 0.94, 1), col, True))
        return self.photo(key, d, d, layers, bg)

    def empty_icon(self, w=None, h=None):
        w = w or self.px(14)
        h = h or self.px(14)
        return self._blank(f"empty_{w}_{h}", w, h)


def apply(widget):
    """The theme for this widget's Tk interpreter (made once)."""
    root = widget._root() if hasattr(widget, "_root") else widget
    th = getattr(root, "_t5_theme", None)
    if th is None:
        th = Theme(root)
        root._t5_theme = th
        # dark title bars for the main window and every dialog (Windows 10 20H1+ / 11)
        root.bind("<Map>", lambda e: dark_title_bar(e.widget) if e.widget is root else None, add="+")
        root.bind_class("Toplevel", "<Map>", lambda e: dark_title_bar(e.widget), add="+")
    return th


def dark_title_bar(win):
    """Ask Windows for the dark caption of a top-level window (cosmetic; ignored where unsupported)."""
    if getattr(win, "_t5_dark_caption", False):
        return
    try:
        win._t5_dark_caption = True
        user32 = ctypes.windll.user32
        user32.GetParent.restype = ctypes.c_void_p
        user32.GetParent.argtypes = [ctypes.c_void_p]
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        on = ctypes.c_int(1)
        dwm = ctypes.windll.dwmapi
        for attr in (20, 19):            # DWMWA_USE_IMMERSIVE_DARK_MODE (20; 19 before Windows 10 20H1)
            if dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except (AttributeError, OSError, tk.TclError):
        pass


def get(widget):
    return apply(widget)


# ---------------------------------------------------------------------- canvas widgets
_BADGES = weakref.WeakSet()


def _art_changed():
    for b in list(_BADGES):
        try:
            b.redraw()
        except tk.TclError:
            pass


ART.listeners.append(_art_changed)


BADGE_SIZES = (22, 34, 36, 40)      # the badges' heights at 100 % (list rows: 22)


def plate_heights(th):
    """The plate heights in pixels this display needs (rank_art.Art.prepare makes them)."""
    return sorted({th.px(v) for v in BADGE_SIZES})


def plate_size(th, size):
    """(w, h) of a rank badge of `size` (its height at 100 %): the game's plates are twice as wide as high."""
    h = th.px(size)
    return 2 * h, h


class Badge(tk.Canvas):
    """A player's rank: the game's own rank plate when the launcher has it (rank_art.py), else a text badge in the
    plate's colour (the rank's name, or its short form when the name does not fit). Both take the same room
    (twice as wide as `size`), so a layout does not move when the plates arrive. A "?" marks a provisional rank."""

    def __init__(self, parent, size=44, bg=None, **kw):
        self.th = apply(parent)
        self.size = size
        self.w, self.h = plate_size(self.th, size)
        self.bgc = bg or C["surface"]
        super().__init__(parent, width=self.w, height=self.h, bg=self.bgc, highlightthickness=0, takefocus=0, **kw)
        self._key = None
        self._state = (None, False)
        _BADGES.add(self)
        self.set(None)

    def set(self, tier, provisional=False):
        self._state = (tier, bool(provisional))
        self.redraw()

    def redraw(self):
        tier, provisional = self._state
        img = ART.image(self, tier, self.h) if tier is not None else None
        key = (tier, provisional, img is not None)
        if key == self._key:
            return
        self._key = key
        self.delete("all")
        if img is not None:
            self.create_image(self.w / 2.0, self.h / 2.0, image=img, anchor="center")
        else:
            self._text_badge(tier)
        if provisional:
            r = self.h * 0.2
            x, y = self.w - r - 1, self.h - r - 1
            self.create_oval(x - r, y - r, x + r, y + r, fill=C["raised"], outline=C["line_hi"])
            self.create_text(x, y, text="?", fill=C["text"],
                             font=(self.th.fonts["caps"].actual("family"), max(6, int(self.size * 0.2)), "bold"))

    def _text_badge(self, tier):
        col = tier_color(tier)
        pad = max(2, int(self.h * 0.08))
        self.create_image(0, 0, image=self.th.plate_image(col, self.w, self.h, self.bgc), anchor="nw")
        fam = self.th.fonts["h3"].actual("family")
        avail = self.w - 2 * pad - self.h * 0.2
        name = t("Guest") if tier is None else ranks.name(tier)
        for txt in (name, tier_abbr(tier)):
            pt = max(7, int(round(self.size * (0.27 if len(txt) <= 3 else 0.22))))
            while pt > 6 and self.th.measure(fam, pt, txt) > avail:
                pt -= 1
            if self.th.measure(fam, pt, txt) <= avail:
                break
        self.create_text(self.w / 2.0, self.h / 2.0, text=txt, fill=text_on(col), font=(fam, pt, "bold"))


class PingBars(tk.Canvas):
    """Four signal bars, lit and coloured by the ping (green / yellow / red)."""

    def __init__(self, parent, height=18, bg=None, **kw):
        self.th = apply(parent)
        px = self.th.px
        self.bw, self.gap, self.h = px(5), px(3), px(height)
        super().__init__(parent, width=4 * self.bw + 3 * self.gap + 2, height=self.h + 2,
                         bg=bg or C["surface"], highlightthickness=0, takefocus=0, **kw)
        self._ms = -1
        self.set(None)

    def set(self, ms):
        if ms == self._ms:
            return
        self._ms = ms
        self.delete("all")
        n, col = ping_bars(ms), ping_color(ms)
        for i in range(4):
            x0 = 1 + i * (self.bw + self.gap)
            bh = self.h * (0.3 + 0.7 * (i + 1) / 4.0)
            self.create_rectangle(x0, self.h + 1 - bh, x0 + self.bw, self.h + 1,
                                  fill=col if i < n else C["line_hi"], outline="")


class CountdownRing(tk.Canvas):
    """A ring that empties as the seconds run out, the seconds in the middle."""

    def __init__(self, parent, size=84, width=7, bg=None, **kw):
        self.th = apply(parent)
        self.d = self.th.px(size)
        self.w = self.th.px(width)
        self.bgc = bg or C["surface"]
        super().__init__(parent, width=self.d, height=self.d, bg=self.bgc, highlightthickness=0, takefocus=0, **kw)
        m = self.w / 2.0 + 2
        self.box = (m, m, self.d - m, self.d - m)
        self.create_oval(*self.box, outline=C["line"], width=self.w)
        self.halo = self.create_arc(*self.box, start=90, extent=-359.9, style="arc",
                                    outline=mix(C["accent"], self.bgc, 0.55), width=self.w + 2)
        self.arc = self.create_arc(*self.box, start=90, extent=-359.9, style="arc", outline=C["accent"],
                                   width=self.w)
        fam = self.th.fonts["big"].actual("family")
        self.num = self.create_text(self.d / 2.0, self.d / 2.0 - self.th.px(4), text="", fill=C["text"],
                                    font=(fam, max(10, int(size * 0.28)), "normal"))
        self.unit = self.create_text(self.d / 2.0, self.d / 2.0 + self.th.px(size * 0.2), text=t("sec"),
                                     fill=C["faint"], font=(self.th.fonts["caps"].actual("family"), 8))

    def set(self, left, total):
        total = max(0.1, float(total or 15))
        left = max(0.0, min(total, float(left)))
        frac = left / total
        ext = -max(0.01, 359.99 * frac)
        col = C["accent"] if left > 5 else C["bad"]
        if left <= 0:
            self.itemconfigure(self.arc, state="hidden")
            self.itemconfigure(self.halo, state="hidden")
        else:
            self.itemconfigure(self.arc, extent=ext, outline=col, state="normal")
            self.itemconfigure(self.halo, extent=ext, outline=mix(col, self.bgc, 0.55), state="normal")
        self.itemconfigure(self.num, text=str(int(math.ceil(left))) if left > 0 else "0")


class Spinner(tk.Canvas):
    """A turning arc (searching, connecting). step() moves it; the owner runs the timer."""

    def __init__(self, parent, size=64, width=6, bg=None, **kw):
        self.th = apply(parent)
        self.d = self.th.px(size)
        w = self.th.px(width)
        self.bgc = bg or C["surface"]
        super().__init__(parent, width=self.d, height=self.d, bg=self.bgc, highlightthickness=0, takefocus=0, **kw)
        m = w / 2.0 + 2
        box = (m, m, self.d - m, self.d - m)
        self.create_oval(*box, outline=C["line"], width=w)
        self.halo = self.create_arc(*box, start=90, extent=100, style="arc",
                                    outline=mix(C["accent"], self.bgc, 0.55), width=w + 2)
        self.arc = self.create_arc(*box, start=90, extent=100, style="arc", outline=C["accent"], width=w)
        self.angle = 90.0

    def step(self, dt=0.033):
        self.angle = (self.angle - 300.0 * dt) % 360.0
        ext = 70 + 50 * (1 + math.sin(math.radians(self.angle * 2))) / 2
        for item in (self.halo, self.arc):
            self.itemconfigure(item, start=self.angle, extent=ext)


def list_look(tv):
    """Calmer, easier lists: every second row a shade lighter ("zebra") and the row under the mouse lit ("hover"),
    kept right after every insert / delete / move / re-tag. The selection still shows over both. Once per list."""
    if getattr(tv, "_t5_list_look", False):
        return
    tv._t5_list_look = True
    try:
        # (a Treeview's tags rank by when they were made: hover first, so it shows over a zebra row)
        tv.tag_configure("hover", background=mix(C["hover"], C["surface"], 0.35))
        tv.tag_configure("zebra", background=mix(C["surface"], C["raised"], 0.42))
    except tk.TclError:
        return
    st = {"gen": 0, "hover": None}

    def stripe(gen):
        if gen != st["gen"]:
            return                          # (a later change asked for its own pass)
        try:
            for i, iid in enumerate(tv.get_children()):
                tags = [x for x in tv.item(iid, "tags") if x not in ("zebra", "hover")]
                if i % 2:
                    tags.append("zebra")
                if iid == st["hover"]:
                    tags.append("hover")
                if tuple(tags) != tuple(tv.item(iid, "tags")):
                    _item(iid, tags=tags)
        except tk.TclError:
            pass

    def later():
        st["gen"] += 1
        try:
            tv.after_idle(stripe, st["gen"])
        except tk.TclError:
            pass

    def wrap(name):
        orig = getattr(tv, name)

        def call(*a, **k):
            out = orig(*a, **k)
            later()
            return out
        setattr(tv, name, call)
        return orig
    for name in ("insert", "delete", "move", "detach", "reattach"):
        wrap(name)
    _item = tv.item

    def item(iid, option=None, **kw):
        out = _item(iid, option, **kw)
        if "tags" in kw:
            later()
        return out
    tv.item = item

    def hover(row):
        if row != st["hover"]:
            st["hover"] = row or None
            later()
    tv.bind("<Motion>", lambda e: hover(tv.identify_row(e.y)), add="+")
    tv.bind("<Leave>", lambda _e: hover(None), add="+")
    later()


def draw_mark(cv, x, y, d, tags=()):
    """The launcher's mark (two slanted bars) on canvas `cv`, `d` px square, its top left at (x, y)."""
    w = d * 0.26
    for i, col in enumerate((C["accent"], mix(C["accent"], C["gold"], 0.45))):
        x0 = x + d * 0.18 + i * (w + d * 0.12)
        cv.create_polygon(x0 + d * 0.22, y + d * 0.1, x0 + d * 0.22 + w, y + d * 0.1, x0 + w, y + d * 0.9, x0,
                          y + d * 0.9, fill=col, outline="", tags=tags)


class Band(tk.Canvas):
    """A strip drawn by code for depth: a warm glow on the left fading into `base` (a soft horizontal gradient)
    with a few slanted slashes in the accent colour (Tekken's motif). It is redrawn when its width changes;
    text and widgets go on top (canvas items tagged other than "band", or packed children)."""

    def __init__(self, parent, height, base=None, glow=None, reach=760, **kw):
        th = apply(parent)
        self.th, self.base, self.glow, self.reach = th, base or C["bg"], glow or C["head_hi"], reach
        super().__init__(parent, height=th.px(height), bg=self.base, highlightthickness=0, takefocus=0, **kw)
        self._drawn = None
        self.bind("<Configure>", self._on_size, add="+")

    def _on_size(self, e):
        if self._drawn != (e.width, e.height):
            self._drawn = (e.width, e.height)
            self.paint(e.width, e.height)

    def shade(self, x):
        """The band's colour at x."""
        reach = self.th.px(self.reach)
        return mix(self.glow, self.base, min(1.0, max(0.0, x / float(reach))) ** 0.7)

    def paint(self, w, h):
        px = self.th.px
        self.delete("band")
        reach = px(self.reach)
        step = max(2, px(6))
        for x in range(0, min(w, reach) + step, step):
            self.create_rectangle(x, 0, x + step, h, fill=self.shade(x), outline="", tags="band")
        sw, gap = px(5), px(26)
        lean = h * 0.45
        for i, x in enumerate(range(px(150), int(reach * 0.75), gap)):
            fade = min(1.0, x / (reach * 0.75))
            col = mix(mix(C["accent"], self.shade(x), 0.78), self.shade(x), fade)
            self.create_polygon(x, h, x + sw, h, x + sw + lean, 0, x + lean, 0, fill=col, outline="", tags="band")
        self.create_line(0, h - 1, w, h - 1, fill=mix(C["line"], self.base, 0.4), tags="band")
        self.tag_lower("band")


class Portrait(tk.Canvas):
    """The player's main fighter in the Play online account card: a square picture (the fighter's head and
    shoulders from the player's own game, fighter_art.py, when the launcher has it; else a drawn placeholder: a
    silhouette on a warm gradient) over a bar with the fighter's name."""

    def __init__(self, parent, side=80, bg=None, **kw):
        th = apply(parent)
        self.th = th
        self.side, self.bar = th.px(side), th.px(22)
        self.w, self.h = self.side, self.side + self.bar
        super().__init__(parent, width=self.w, height=self.h, bg=bg or C["surface"], highlightthickness=0,
                         takefocus=0, **kw)
        self.key = self.photo = None
        self.set(None, "")

    def set(self, key, name, photo=None):
        """Fighter `key` (None: nobody / random) named `name`, its picture `photo` (a PhotoImage `side` px square)
        or None for the placeholder."""
        self.key, self.photo = key, photo
        self.delete("all")
        w, s, h, px = self.w, self.side, self.h, self.th.px
        if photo is not None:
            n = 10
            for i in range(n):                       # (behind the picture's transparent edges: a warm gradient)
                self.create_rectangle(0, s * i / n, w, s * (i + 1) / n + 1, outline="",
                                      fill=mix(mix(C["accent"], C["raised"], 0.7), C["raised"], i / (n - 1.0)))
            self.create_image(w // 2, s, image=photo, anchor="s")
        else:
            n = 14
            for i in range(n):
                self.create_rectangle(0, s * i / n, w, s * (i + 1) / n + 1, outline="",
                                      fill=mix(mix(C["accent"], C["raised"], 0.72), C["raised"], i / (n - 1.0)))
            sil = mix(C["raised"], "#000000", 0.35)
            cx = w / 2.0
            self.create_oval(cx - s * 0.18, s * 0.2, cx + s * 0.18, s * 0.56, fill=sil, outline="")
            self.create_polygon(cx - s * 0.44, s, cx - s * 0.36, s * 0.74, cx - s * 0.12, s * 0.62, cx + s * 0.12,
                                s * 0.62, cx + s * 0.36, s * 0.74, cx + s * 0.44, s, fill=sil, outline="", smooth=True)
            if not key:
                self.create_text(cx, s * 0.38, text="?", fill=mix(C["text"], C["raised"], 0.5),
                                 font=self.th.fonts["h1"])
        self.create_rectangle(0, s, w, h, fill=mix(C["bg"], C["surface"], 0.3), outline="")
        self.create_rectangle(0, s, px(3), h, fill=C["accent"], outline="")
        if name:
            f, text, room = self.th.fonts["caps"], name.upper(), w - px(12)
            while len(text) > 1 and f.measure(text) > room:
                text = text[:-2].rstrip() + "…"
            self.create_text(px(8), s + self.bar / 2.0, text=text, anchor="w", fill=C["text"], font=f)
        self.create_rectangle(0, 0, w - 1, h - 1, outline=C["line_hi"])


class Mark(tk.Canvas):
    """The launcher's own mark: two slanted bars (drawn, no logo)."""

    def __init__(self, parent, size=26, bg=None, **kw):
        th = apply(parent)
        d = th.px(size)
        super().__init__(parent, width=d, height=d, bg=bg or C["bg"], highlightthickness=0, takefocus=0, **kw)
        w = d * 0.26
        for i, col in enumerate((C["accent"], mix(C["accent"], C["gold"], 0.45))):
            x = d * 0.18 + i * (w + d * 0.12)
            self.create_polygon(x + d * 0.22, d * 0.1, x + d * 0.22 + w, d * 0.1, x + w, d * 0.9, x, d * 0.9,
                                fill=col, outline="")


# ---------------------------------------------------------------------- dialogs
def _center(win, parent):
    win.update_idletasks()
    try:
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - win.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - win.winfo_reqheight()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass


def _dialog(parent, title):
    th = apply(parent)
    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title)
    win.configure(bg=C["bg"])
    win.resizable(False, False)
    try:
        win.transient(parent.winfo_toplevel())
    except tk.TclError:
        pass
    body = ttk.Frame(win, style="Card.TFrame", padding=th.px(18))
    body.pack(fill="both", expand=True, padx=th.px(10), pady=th.px(10))
    return th, win, body


def _modal(win, parent, focus):
    _center(win, parent)
    win.deiconify()
    try:
        win.grab_set()
    except tk.TclError:
        pass
    focus.focus_set()
    win.wait_window()


def ask_string(title, prompt, show=None, initialvalue=None, parent=None, **_kw):
    """Themed stand-in for simpledialog.askstring (same arguments). Enter = OK, Escape = Cancel."""
    parent = parent or tk._default_root
    th, win, body = _dialog(parent, title)
    result = [None]
    ttk.Label(body, text=title, style="Card.H3.TLabel").pack(anchor="w")
    ttk.Label(body, text=prompt, style="Card.Muted.TLabel", wraplength=th.px(380), justify="left").pack(
        anchor="w", pady=(th.px(4), th.px(10)))
    var = tk.StringVar(win, value=initialvalue or "")
    e = ttk.Entry(body, textvariable=var, style="Card.TEntry", width=36, show=show or "")
    e.pack(fill="x")
    e.select_range(0, "end")
    row = ttk.Frame(body, style="CardBody.TFrame")
    row.pack(fill="x", pady=(th.px(14), 0))

    def ok(_e=None):
        result[0] = var.get()
        win.destroy()
    ttk.Button(row, text=t("Cancel"), style="Card.TButton", command=win.destroy).pack(side="right")
    ttk.Button(row, text=t("OK"), style="Card.Accent.TButton", command=ok).pack(side="right", padx=(0, th.px(8)))
    win.bind("<Return>", ok)
    win.bind("<Escape>", lambda _e: win.destroy())
    _modal(win, parent, e)
    return result[0]


def ask_yes_no(title, message, parent=None, **_kw):
    """Themed stand-in for messagebox.askyesno (same arguments). Enter = Yes, Escape = No."""
    parent = parent or tk._default_root
    th, win, body = _dialog(parent, title)
    result = [False]
    ttk.Label(body, text=title, style="Card.H3.TLabel").pack(anchor="w")
    ttk.Label(body, text=message, style="Card.TLabel", wraplength=th.px(400), justify="left").pack(
        anchor="w", pady=(th.px(6), th.px(4)))
    row = ttk.Frame(body, style="CardBody.TFrame")
    row.pack(fill="x", pady=(th.px(14), 0))

    def yes(_e=None):
        result[0] = True
        win.destroy()
    ttk.Button(row, text=t("No"), style="Card.TButton", command=win.destroy).pack(side="right")
    b = ttk.Button(row, text=t("Yes"), style="Card.Accent.TButton", command=yes)
    b.pack(side="right", padx=(0, th.px(8)))
    win.bind("<Return>", yes)
    win.bind("<Escape>", lambda _e: win.destroy())
    _modal(win, parent, b)
    return result[0]


def bind_return_on_buttons(widget):
    """Enter presses the focused button, like Space (keyboard players). Once per interpreter."""
    th = apply(widget)
    if getattr(th, "_return_bound", False):
        return
    th._return_bound = True
    root = th.root
    root.bind_class("TButton", "<Return>", lambda e: e.widget.invoke() if str(e.widget.cget("state")) != "disabled"
                    else None, add="+")
    root.bind_class("TButton", "<KP_Enter>", lambda e: e.widget.invoke() if str(e.widget.cget("state")) !=
                    "disabled" else None, add="+")
