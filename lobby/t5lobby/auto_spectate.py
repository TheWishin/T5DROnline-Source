"""Idle watching policy; uses only existing, advertised Watch targets.

These flags are hints, never permission: the normal server watch handler checks
privacy, blocks, builds and all spectator limits again for every attempt.
"""
import math
import time

from . import ranks

IDLE_SECONDS = 15.0
ATTEMPT_SECONDS = 30.0
PAUSE_SECONDS = 120.0
TARGET_SECONDS = 120.0


def _strength(player):
    tier = ranks.index(player.get("tier"))
    if tier is None:
        tier = ranks.index(player.get("rank"))
    rating = player.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, (int, float)) or not math.isfinite(rating):
        rating = -1
    return (tier if tier is not None else -1, rating)


def _room_targets(room):
    if room.get("mode") == "tables":
        return [{"room": room["id"], "table": table["id"]}
                for table in room.get("tables") or () if table.get("id") is not None and table.get("watch")]
    return [{"room": room["id"]}]


def candidates(client):
    """Normal watch kwargs, ordered own room, friends, public rooms.

    Public rooms expose members and owner, not always the fighting pair. Sort
    by the strongest advertised member (owner as fallback), then a stable id.
    No guessed player addresses, requests for hidden rooms or new protocol.
    """
    me = getattr(client, "me", None) or {}
    mine = getattr(client, "my_room", None) or {}
    own_id = mine.get("id") if me.get("status") == "room" else None
    rows = []
    if own_id and mine.get("watch"):
        rows.extend(_room_targets(mine))
    friends = (getattr(client, "friend_list", None) or {}).get("friends") or ()
    friends = [f for f in friends if f.get("watch") and f.get("name")]
    for f in sorted(friends, key=lambda f: (-_strength(f)[0], -_strength(f)[1], f["name"].casefold())):
        rows.append({"name": f["name"]})
    players = {p.get("id"): p for p in getattr(client, "players", ()) or ()}
    rooms = []
    for room in getattr(client, "rooms", ()) or ():
        if not room.get("id") or room["id"] == own_id or not room.get("watch"):
            continue
        if room.get("private") or room.get("hidden") or room.get("lock") or me.get("id") in (room.get("members") or ()):
            continue
        known = [players[pid] for pid in room.get("members") or () if pid in players]
        owner = room.get("owner")
        if isinstance(owner, dict):
            known.append(owner)
        strength = max((_strength(p) for p in known), default=(-1, -1))
        rooms.append((strength, room))
    for _, room in sorted(rooms, key=lambda r: (-r[0][0], -r[0][1], r[1]["id"])):
        rows.extend(_room_targets(room))
    return rows


def idle(tab):
    """Fail closed while anything can need the player's game or attention."""
    c = getattr(tab, "client", None)
    if c is None or not getattr(c, "connected", True):
        return False
    has = getattr(c, "has_spectate", None)
    if not callable(has) or not has() or (getattr(c, "me", None) or {}).get("status") not in ("idle", "room"):
        return False
    if getattr(c, "match", None) is not None:
        return False
    for name in ("match", "challenge", "invite", "outgoing_invite", "ready_deadline", "set_bar", "rematch_bar"):
        if getattr(tab, name, None) is not None:
            return False
    if getattr(tab, "ready_sent", False) or getattr(tab, "set_locked", False) or getattr(tab, "bar_spec", None):
        return False
    chal = getattr(tab, "chal", None)
    if getattr(chal, "out", None) or getattr(chal, "incoming", None):
        return False
    if getattr(getattr(tab, "tours", None), "call", None) is not None:
        return False
    drv = getattr(tab, "driver", None)
    if getattr(drv, "ticket", None) is not None:
        return False
    running = getattr(drv, "game_running", None)
    if callable(running) and running():
        return False
    game = getattr(getattr(tab, "app", None), "game", None)
    if game is not None and game.running():
        return False
    room = getattr(c, "my_room", None) or {}
    uid = (c.me or {}).get("id")
    if uid in (room.get("playing") or ()) or uid in ((room.get("next") or {}).get("players") or ()):
        return False
    for table in room.get("tables") or ():
        if uid in ((table.get("next") or {}).get("players") or ()):
            return False
    return True


class Policy:
    def __init__(self):
        self._client = None
        self._idle_since = None
        self._next = 0.0
        self._target = None
        self._tried = {}

    def pause(self, now=None):
        """A user leaving must not immediately boot another spectator game."""
        now = time.monotonic() if now is None else now
        self._idle_since = now
        self._next = max(self._next, now + PAUSE_SECONDS)

    def attempted(self, now=None):
        """Rate limit successes and refusals alike; try another target next time."""
        now = time.monotonic() if now is None else now
        self._next = max(self._next, now + ATTEMPT_SECONDS)
        if self._target is not None:
            self._tried[self._target] = now + TARGET_SECONDS

    def due(self, tab, now=None):
        now = time.monotonic() if now is None else now
        c = getattr(tab, "client", None)
        if c is not self._client:
            self._client, self._idle_since = c, None
            self._tried.clear()
        settings = getattr(getattr(tab, "app", None), "settings", None) or {}
        if not settings.get("auto_spectate", False) or not idle(tab):
            self._idle_since = None
            return None
        if self._idle_since is None:
            self._idle_since = now
        if now - self._idle_since < IDLE_SECONDS or now < self._next:
            return None
        self._tried = {k: until for k, until in self._tried.items() if until > now}
        for target in candidates(c):
            key = tuple(sorted(target.items()))
            if key not in self._tried:
                self._target = key
                return target
        return None
