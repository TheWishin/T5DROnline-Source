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


def candidates(client, own_room=True):
    """Normal watch kwargs, ordered own room, friends, public rooms.

    own_room False: the room's table watching (TablePolicy) looks after this player's own room.

    Public rooms expose members and owner, not always the fighting pair. Sort
    by the strongest advertised member (owner as fallback), then a stable id.
    No guessed player addresses, requests for hidden rooms or new protocol.
    """
    me = getattr(client, "me", None) or {}
    mine = getattr(client, "my_room", None) or {}
    own_id = mine.get("id") if me.get("status") == "room" else None
    rows = []
    if own_room and own_id and mine.get("watch"):
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
    if getattr(getattr(tab, "app", None), "build", None) is not None:
        return False                    # BUILD GAME runs: no game of any kind
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
        for target in candidates(c, own_room=not table_setting(tab)):
            key = tuple(sorted(target.items()))
            if key not in self._tried:
                self._target = key
                return target
        return None


# ---------------------------------------------------------------------- the room's table (1.2.0, on by default)
# A member of a community room who waits for a turn watches the match at the room's table (one match taking
# turns), or at "their" table in a room with several matches at once: the table they last played at or picked to
# watch, else the lowest-numbered table with a match on. Settings key "auto_watch_table" (launcher Settings and the
# room row's "Automatically watch"; docs/SPECTATE.md "Automatically watch your room's table"). It reacts at once
# (no idle wait): the spectator game should boot while the players' games still load. The server checks every
# watch as it checks a click on Watch (privacy, private rooms: members only, blocks, limits).
TABLE_SETTING = "auto_watch_table"
TABLE_RETRY_SECONDS = 5.0       # the same table after a refusal or a failed request
TABLE_GAP_SECONDS = 1.0         # between any two automatic requests
TABLE_END_GRACE = 20.0          # a watched match whose stream ended plays to its end (KO, result) before the
                                # table's next match takes its place; its game closes by itself at the stream's end


def table_setting(tab):
    settings = getattr(getattr(tab, "app", None), "settings", None) or {}
    try:
        return settings.get(TABLE_SETTING, True) is not False
    except AttributeError:
        return True


def community(room):
    return bool(room) and (room.get("mode") == "tables" or (room.get("size") or 2) > 2)


def table_room(client):
    """The community room this player sits in, waiting or playing (else None)."""
    me = getattr(client, "me", None) or {}
    room = getattr(client, "my_room", None)
    if me.get("status") != "room" or not community(room) or me.get("id") not in (room.get("members") or ()):
        return None
    return room


def member_room(client):
    """The community room this player is a member of, whatever their status: waiting, at the ready check, in a
    match or playing (table_room() is the room only while they wait in it). The client keeps my_room through a
    room match and clears it when the player is back to idle / queue."""
    me = getattr(client, "me", None) or {}
    room = getattr(client, "my_room", None)
    if me.get("status") in ("idle", "queue") or not community(room) or me.get("id") not in (room.get("members") or ()):
        return None
    return room


def _seat_key(room, table=None):
    """Who sits at the table now: a new pair (the next turn) is a new key, a set's games keep it (the pair in
    either order: a side swap in a casual set is the same turn)."""
    pair = table.get("players") if table is not None else room.get("playing")
    return (room.get("id"), table.get("id") if table is not None else None, tuple(sorted(pair or (), key=str)))


def _seat_keys(room):
    """The seat key of every table in the room now."""
    if room.get("mode") != "tables":
        return {_seat_key(room)}
    return {_seat_key(room, tb) for tb in room.get("tables") or () if isinstance(tb.get("id"), int)}


def table_targets(room, prefer=None):
    """[(watch kwargs, seat key)] for this room's table(s), best first; [] while nothing can be watched there.

    prefer: the table id this player calls theirs. While that table counts down to its next pair the list is
    empty: its next match comes in seconds, watching another table until then would only boot a game for nothing.
    """
    if room.get("mode") != "tables":
        return [({"room": room["id"]}, _seat_key(room))] if room.get("watch") else []
    tables = [tb for tb in room.get("tables") or () if isinstance(tb.get("id"), int)]
    mine = next((tb for tb in tables if tb["id"] == prefer), None)
    if mine is not None and not mine.get("watch") and (mine.get("next") or {}).get("at") is not None:
        return []
    order = sorted(tables, key=lambda tb: (tb is not mine, tb["id"]))
    return [({"room": room["id"], "table": tb["id"]}, _seat_key(room, tb)) for tb in order if tb.get("watch")]


def own_game(tab):
    """The player's own game is open (a match driver's game, e.g. a persistent game kept for the next match, or an
    offline game)."""
    drv = getattr(tab, "driver", None)
    running = getattr(drv, "game_running", None)
    if callable(running) and running():
        return True
    game = getattr(getattr(tab, "app", None), "game", None)
    return game is not None and game.running()


def turn(tab):
    """A match, a question or a call of this player's own is under way (idle() without the game checks)."""
    c = tab.client
    if getattr(c, "match", None) is not None:
        return True
    for name in ("match", "challenge", "invite", "outgoing_invite", "ready_deadline", "set_bar", "rematch_bar"):
        if getattr(tab, name, None) is not None:
            return True
    if getattr(tab, "ready_sent", False) or getattr(tab, "set_locked", False) or getattr(tab, "bar_spec", None):
        return True
    chal = getattr(tab, "chal", None)
    if getattr(chal, "out", None) or getattr(chal, "incoming", None):
        return True
    if getattr(getattr(tab, "tours", None), "call", None) is not None:
        return True
    if getattr(getattr(tab, "driver", None), "ticket", None) is not None:
        return True
    room = getattr(c, "my_room", None) or {}
    uid = (getattr(c, "me", None) or {}).get("id")
    if uid in (room.get("playing") or ()) or uid in ((room.get("next") or {}).get("players") or ()):
        return True
    for tb in room.get("tables") or ():
        if uid in ((tb.get("next") or {}).get("players") or ()):
            return True
        if uid in (tb.get("players") or ()) and (tb.get("match") or (tb.get("set") or {}).get("state") == "active"):
            return True
    return False


def table_blocker(tab, spectator_running=False):
    """None when this player may watch their room's table now, else why not:
    off | room (not in a community room, or no spectating) | turn (their turn, or a match / question / call of their
    own) | build (BUILD GAME runs) | game (their own game is open: a persistent game waiting for their next match).
    spectator_running: the game that is open is this tab's own spectator (switching to the table's next match)."""
    if not table_setting(tab):
        return "off"
    c = getattr(tab, "client", None)
    if c is None or not getattr(c, "connected", True):
        return "room"
    has = getattr(c, "has_spectate", None)
    if not callable(has) or not has() or table_room(c) is None:
        return "room"
    if turn(tab):
        return "turn"
    if getattr(getattr(tab, "app", None), "build", None) is not None:
        return "build"
    if not spectator_running and own_game(tab):
        return "game"
    return None


class TablePolicy:
    """Which table to watch next, and when to ask again."""

    def __init__(self):
        self._client = None
        self._room = None
        self.prefer = None          # the table id this player calls theirs (rooms with several matches at once)
        self._retry = {}            # seat key -> monotonic time it may be asked for again
        self._skip = set()          # seat keys the player stopped watching (Stop watching): not again this turn
        self._next = 0.0

    def _track(self, tab):
        # membership, not "waiting": a match of this player's own in the room (status match / playing) keeps the
        # room, its preferred table and its skips (review autowatch-120 P2: the match cleared prefer, and after it
        # the player watched table 1 instead of the table they had played at); whether they may watch now is
        # table_blocker's question
        c = getattr(tab, "client", None)
        room = member_room(c) if c is not None else None
        rid = room.get("id") if room else None
        if c is not self._client or rid != self._room:
            self._client, self._room = c, rid
            self.prefer = None
            self._retry.clear()
            self._skip.clear()
        if room is None:
            return None
        # a Stop watching holds for that turn only: once its table shows another pair the skip is gone, so the
        # same two meeting again later (A-B, A-C, A-B) are watched again (review autowatch-120 P2)
        self._skip &= _seat_keys(room)
        uid = (c.me or {}).get("id")
        for tb in room.get("tables") or ():
            if uid in (tb.get("players") or ()) and isinstance(tb.get("id"), int):
                self.prefer = tb["id"]          # the table this player plays at is theirs
        return room

    def picked(self, room_id, table_id):
        """The player watched a table by hand (Room tables -> Watch table): it is theirs from now on."""
        if room_id is not None and room_id == self._room and isinstance(table_id, int):
            self.prefer = table_id

    def due(self, tab, now=None, spectator_running=False, current=None):
        """(watch kwargs, seat key) to ask for now, or None. current: the seat key being watched (not asked again)."""
        now = time.monotonic() if now is None else now
        room = self._track(tab)
        if room is None or now < self._next or table_blocker(tab, spectator_running) is not None:
            return None
        self._retry = {k: until for k, until in self._retry.items() if until > now}
        for kw, key in table_targets(room, self.prefer):
            if key != current and key not in self._skip and key not in self._retry:
                return kw, key
        return None

    def attempted(self, target, now=None):
        now = time.monotonic() if now is None else now
        kw, key = target
        self._next = now + TABLE_GAP_SECONDS
        if kw.get("table") is not None:
            self.prefer = kw["table"]
        self._retry[key] = now + TABLE_RETRY_SECONDS

    def stopped(self, key):
        """Stop watching on an automatic watch: not this table turn again (the next pair is a new key)."""
        if key is not None:
            self._skip.add(key)
