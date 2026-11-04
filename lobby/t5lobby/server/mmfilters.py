"""Search options and where players are (docs/ONLINE.md "Search options, areas and languages"): the lobby server's side.

Feature "mm_filters" (the server announces it; a launcher without it never sends any of this, and an older server
ignores the fields):

  netinfo {wifi, area, lang}   what the launcher knows of its PC: wifi true / false / null (the network adapter of the
                               default route; null = not known), the player's area ("auto" or one of AREAS) and the
                               language they speak (the launcher's language unless the player picked another)
  queue {..., max_ping, no_wifi, steady}
                               max_ping: 60 | 100 | 150 (ms, the estimate _est_ping makes; absent / null = any),
                               no_wifi: only opponents not known to play over Wi-Fi, steady: only opponents whose PC
                               kept at least T5L_STEADY_FPS in its last match (unknown counts as steady: a first match,
                               an older launcher). The options of BOTH players must accept the pair; the usual ping
                               window (T5L_PING_START, widening) applies on top.

Area: the player's choice, or "auto" = the area of the relay (the central's T5L_AREA, a regional relay's "area" in
relays.json) with the smallest round trip, when that is at most AREA_RTT_MS -- else not known. The lobby list's player
rows and rooms carry "area" and "lang" (older launchers ignore them). Wi-Fi is never shown to anybody: it is only used
by the no_wifi option.
"""
import re

from .. import proto
from ..proto import LobbyError

AREAS = ("na", "sa", "eu", "af", "as", "oc")     # North / South America, Europe, Africa, Asia, Oceania
AREA_RTT_MS = 100.0                              # auto: the nearest relay must be at most this far
MAX_PINGS = (60, 100, 150)
_LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")


def clean_area(value, allow_auto=True):
    v = str(value or "").strip().lower()
    if allow_auto and v in ("", "auto"):
        return "auto"
    return v if v in AREAS else None


def clean_lang(value):
    """'de', 'pt-BR', 'ko' ... (BCP 47 language + optional region, as the launcher's catalogs); '' = not given."""
    v = str(value or "").strip()
    if not v:
        return ""
    if "-" in v:
        a, _, b = v.partition("-")
        v = a.lower() + "-" + b.upper()
    else:
        v = v.lower()
    return v if _LANG_RE.match(v) else None


class MatchFiltersMixin:
    """Methods of LobbyServer (lobby.py)."""

    # ------------------------------------------------------------------ area / language / Wi-Fi
    def _auto_area(self, p):
        best = None
        main_area = clean_area(self.cfg.area, allow_auto=False)
        if p.server_rtt is not None and main_area:
            best = (p.server_rtt, main_area)
        for rid, ms in (p.relay_rtt or {}).items():
            node = self.relays.nodes.get(rid)
            area = getattr(node, "area", "") if node is not None else ""
            if area and (best is None or ms < best[0]):
                best = (ms, area)
        return best[1] if best is not None and best[0] <= AREA_RTT_MS else ""

    def _update_area(self, p):
        """The area the lobby list shows: the player's choice, else the nearest relay's."""
        choice = getattr(p, "area_choice", "auto")
        area = choice if choice in AREAS else self._auto_area(p)
        if area != getattr(p, "area", ""):
            p.area = area
            self.dirty = True

    async def h_netinfo(self, conn, msg):
        p = conn.player
        wifi = msg.get("wifi")
        p.wifi = wifi if isinstance(wifi, bool) else None
        if "area" in msg:
            area = clean_area(msg.get("area"))
            if area is None:
                raise LobbyError(proto.E_BAD_REQUEST, "area is auto or one of " + ", ".join(AREAS))
            p.area_choice = area
        if "lang" in msg:
            lang = clean_lang(msg.get("lang"))
            if lang is None:
                raise LobbyError(proto.E_BAD_REQUEST, "lang is a language code such as en, de or pt-BR")
            if lang != p.lang:
                p.lang = lang
                self.dirty = True
        self._update_area(p)
        return {"t": "netinfo", "area": p.area, "lang": p.lang}

    # ------------------------------------------------------------------ search options
    @staticmethod
    def _read_filters(msg):
        """queue's options -> {max_ping, no_wifi, steady} (bad values: refused, not ignored)."""
        mp = msg.get("max_ping")
        if mp is not None and (isinstance(mp, bool) or mp not in MAX_PINGS):
            raise LobbyError(proto.E_BAD_REQUEST, "max_ping is one of " + ", ".join(map(str, MAX_PINGS)) + " or null")
        return {"max_ping": mp, "no_wifi": bool(msg.get("no_wifi")), "steady": bool(msg.get("steady"))}

    def _steady(self, p):
        return p.fps is None or self.cfg.steady_fps <= 0 or p.fps >= self.cfg.steady_fps

    def _accepts(self, a, b, ping):
        """Do a's search options accept b as the opponent at an estimated ping?"""
        f = getattr(a, "filters", None) or {}
        if f.get("max_ping") is not None and ping > f["max_ping"]:
            return False
        if f.get("no_wifi") and getattr(b, "wifi", None) is True:
            return False
        if f.get("steady") and not self._steady(b):
            return False
        return True

    def _filters_ok(self, a, b, ping):
        return self._accepts(a, b, ping) and self._accepts(b, a, ping)

    @staticmethod
    def _filters_text(f):
        """For the queued reply and the log: the options that are on."""
        parts = []
        if f.get("max_ping") is not None:
            parts.append(f"ping <= {f['max_ping']} ms")
        if f.get("no_wifi"):
            parts.append("no Wi-Fi")
        if f.get("steady"):
            parts.append("steady 60 fps")
        return ", ".join(parts)

    # ------------------------------------------------------------------ rooms
    def _room_tags(self, conn, msg, owner):
        """A new room's area and language: the host's choice in room_create (mm_filters launchers), else the host's own."""
        area = clean_area(msg.get("area"), allow_auto=True) if "area" in msg else "auto"
        if area is None:
            raise LobbyError(proto.E_BAD_REQUEST, "area is auto or one of " + ", ".join(AREAS))
        lang = clean_lang(msg.get("lang")) if "lang" in msg else getattr(owner, "lang", "")
        if lang is None:
            raise LobbyError(proto.E_BAD_REQUEST, "lang is a language code such as en, de or pt-BR")
        return (area if area != "auto" else getattr(owner, "area", "")), lang
