"""Rooms (docs/ONLINE.md "Rooms" and "Private rooms"): the lobby server's side.

A room is where players meet by choice. Its owner (the host) creates it, others join, its matches start by
themselves.

Classic room (size 2 -- what every launcher before 1.1.3 creates, and still the default): two members; their
match starts when the second one joins (with a ready check, or without one right after a friend accepted an invite
into it); after it the two rematch in their running games, or one of them presses Ready again (`rematch` without a
match id) for a new match. Unchanged since 1.0.

Community room (size 3..T5L_ROOM_MAX_SIZE, created by a launcher with the "private_rooms" cap): up to that many
members who take turns. The room keeps a line (the turn order); the first two in it play, with a ready check. When
their match is over the line moves on by the room's rule --
    winner   winner stays: the loser goes to the back of the line, the next one plays the winner (no winner -- a
             void, a draw -- both go to the back)
    queue    everyone in turn: whoever wins, the player who was at the table longer goes to the back and the other
             plays the next one in line -- everyone plays two in a row (with three players everyone meets everyone)
-- and the next match starts by itself after T5L_ROOM_NEXT_SECONDS (nobody votes for a rematch; with only two in
the line it is the same two again). Whoever declines the ready check or lets it run out sits out (leaves the line,
stays in the room, is told so) until they press Back in line (`room_line`); a member can also sit out on purpose.
Community rooms are casual: who plays whom is the room's business, which is what ranked keeps out.

Casual first-to sets (1.2.0, caps "sets" and "casual_sets"): the host picks first_to 1, 2, 3, 5 or 10.
One complete set occupies one turn at the table; the line stays put between its games. Winner stays uses
the set winner; everyone in turn moves the longer-seated player after the set. An unfinished set has no
set winner, so winner stays moves both players back. Older players play single-game turns instead.

Simultaneous tables (1.2.0, cap "room_tables", mode "tables"): a casual room has size // 2 stable table
numbers. Each free pair gets its own normal match and first-to set; a set keeps that table between games.
After the whole set both players return behind the waiting members. The host can rearrange idle countdown
pairs (`room_pair`); playing matches and active sets cannot move. `room_line` still means available / away.
A member watching must sit out to keep watching when a match is offered. Failed table setup puts its pair
away until they explicitly return, so a full relay cannot cause automatic connection retry loops. The room
size, global relay limits and spectator budgets stay unchanged. Launchers without the new cap get a clear
update refusal on join (also by invite), rather than receiving an ambiguous single-table room view.

Private room: locked with a password or with an invite code the server makes (XXXX-XXXX-XXXX); also casual. It
shows in the room list as locked (name, host, players, "private") or, hidden, not at all. Joining needs the password
or the code -- or a friend's invite into the room (`invite` kind room): the invite is the key, no secret is sent to
anybody. The host can change or remove the lock, hide the room, make a new code and remove players (`room_kick`;
they cannot come back into that room). Only members can watch a private room's match.

Security (security-review patterns of lobby.py):
  * the password is kept only as a salted scrypt hash (store.hash_password, worker thread, the T5L_PW_CONCURRENCY
    gate), in memory; checked with a constant-time compare (store.check_password); an invite code only as its HMAC
    under a key made when the server starts (the index that finds a room by its code); neither is ever logged, sent
    to anybody, put in the lobby list, the status JSON, an event or an error message;
  * wrong passwords / codes: per player and per internet address (IPv6: the /64, and the /56 and /48 around it with
    2x and 4x the budget, so the 256 /64s of a /56 are not 256 budgets), token buckets (T5L_ROOM_GUESSES then one
    per T5L_ROOM_GUESS_SECONDS), counted before the slow check and given back when it was right (parallel attempts
    on several connections cannot all pass while the first is hashed); the refusal says when to try again (`retry`,
    whole seconds, like a held-back invite);
  * the room's own budget (hardening 1.1.4): a guess at a room is paid first out of a small lane of the guesser's
    network (an IPv4 address, an IPv6 /48: T5L_ROOM_LANE_GUESSES, then one per T5L_ROOM_LANE_SECONDS), only then out
    of the room's shared budget (4x T5L_ROOM_GUESSES, then 3 per T5L_ROOM_GUESS_SECONDS). Guessers from many
    addresses can use up the shared budget, never another network's lane: a member who types the right password
    gets in while the room is being guessed at (before, the empty shared budget refused everybody: "try again in
    N s"). Brute force stays bounded per room: the shared budget plus a few guesses per network and hour;
  * the host sees the wrong passwords of the last 10 minutes (how many, from how many networks; never who or from
    where) and can turn those networks away from the room (`room_bar`): their guesses are refused before they cost
    anything, so the shared budget fills up again;
  * passwords: 4-64 characters after Unicode NFC, any script, printable only (no control or format characters, no
    space at either end), at most 256 bytes of UTF-8;
  * setting a password costs a hash: counted like a password change (pw_ops, per player), and per address.

Older launchers (no "private_rooms" cap) never see a private room: the lobby list they get leaves them out; a join
by id is refused with a text they show ("update the launcher"); a friend's invite still brings them in (it is the
key). Community rooms work for them like any room: they see a ready check when it is their turn.

Messages (client -> server; docs/ONLINE.md "Protocol reference"):
    room_create {name, ranked, size, rotation, first_to, mode, private: password|code, password, hidden} -> room {room, code?}
    room_join   {room, password} | {room?, code}                                           -> room {room}
    room_lock   {lock: password|code|none, password, hidden}   (host)                      -> room {room, code?}
    room_kick   {player}                                       (host)                      -> room {room}
    room_bar    {}                                             (host, password lock)      -> room {room}, barred
    room_line   {in: true|false}                               (community rooms)          -> room {room}
    room_pair   {table, players: [player, player]}               (host, idle table)          -> room {room}
server -> client: room {room} (a member's view: line, who plays, the next match; the host's also has `guesses`, the
wrong passwords of the last 10 minutes), notice room_kicked / room_away.
"""
import asyncio
import collections
import hashlib
import hmac
import logging
import os
import time

from .. import proto
from ..compatibility import compatible
from ..proto import (CODE_ALPHABET, CODE_LEN, LobbyError, clean_room_password,  # noqa: F401 -- (tests use them here)
                     new_room_code as new_code, normalize_room_code as normalize_code)
from .ratelimit import KeyedBuckets
from .store import COUNTED, check_password, hash_password

log = logging.getLogger("t5lobby")

ROTATIONS = ("winner", "queue")
LOCKS = ("password", "code")
SOON = 1.0                     # seconds before a room's first match once two are in its line
GUESS_WINDOW = 600.0           # seconds of wrong passwords the host sees (and turns away with room_bar)
GUESS_MEMORY = 2000            # wrong passwords a room remembers (the oldest go first)
BARRED_MAX = 4096              # networks one room turns away at most


def _rid():
    return os.urandom(6).hex()


class RoomTable:
    """One pair's seat in a room; connections, results and sets are ordinary matches."""
    def __init__(self, room, number):
        self.room = room
        self.id = number
        self.pair = []
        self.match = None
        self.set = None
        self.next_timer = None
        self.next_at = None
        self.watch = False

    def active(self):
        return self.match is not None or (self.set is not None and self.set.state == "active")

    def players(self):
        """Match sides also order the set's score; reservations keep the host's order."""
        if self.match is not None:
            return self.match.players
        if self.set is not None and self.set.state == "active":
            return self.set.players
        return self.pair


class Room:
    def __init__(self, owner, name, ranked, size=2, rotation="winner", first_to=1, mode="line"):
        self.id = "r" + _rid()
        self.name = name
        self.owner = owner
        self.members = [owner]          # everyone in the room, in the order they came
        self.line = [owner]             # community rooms: the turn order (a member sitting out is not in it)
        self.size = size                # most members at once (2 = a classic room)
        self.rotation = rotation        # community rooms: winner (winner stays) | queue (everyone in turn)
        self.ranked = ranked
        self.first_to = first_to        # casual set target; effective target is 1 against an older launcher
        self.match = None
        self.set = None                 # the room's running set (rematches in the room keep it)
        self.build_id = owner.build_id
        self.compat_group = getattr(owner, "compat_group", "")
        self.watch = False              # its match can be watched (spectating.py, set before each lobby list)
        self.lock = None                # None | "password" | "code"
        self.secret = None              # lock "password": its salted scrypt hash -- memory only, never sent or logged
        self.code_key = None            # lock "code": the code's HMAC (the server's index key), never the code
        self.hidden = False             # not in the lobby list at all
        self.kicked = {}                # block key -> name: removed by the host, not let back in
        self.wrong = collections.deque(maxlen=GUESS_MEMORY)   # (monotonic time, network) of each wrong password
        self.barred = set()             # networks the host turned away (room_bar): no more guesses at this room
        self.next_timer = None          # community rooms: the countdown to the next match
        self.next_at = None             # ... when it ends (unix time, for the members' view)
        self.sent = {}                  # member id -> the last view pushed to it
        self.training = False           # a training room: endless health, no result (matchrules.py)
        self.rematch_policy = "both_confirm"
        self.auto_skip_after_round = False
        self.mode = mode                # line (the existing single table) | tables (independent pairs)
        self.tables = [RoomTable(self, n + 1) for n in range(size // 2)] if mode == "tables" else []

    @property
    def community(self):
        return self.size > 2 or self.mode == "tables"

    @property
    def private(self):
        """Locked or hidden: only its members may watch its match."""
        return self.lock is not None or self.hidden

    def status(self):
        return "playing" if self.match or self._casual_set_active() or any(t.active() for t in self.tables) else (
            "full" if len(self.members) >= self.size else "open")

    def _casual_set_active(self):
        return self.set is not None and getattr(self.set, "casual", False) and self.set.state == "active"

    def public(self):
        """The lobby list's entry. Nothing about a lock but that there is one (and which kind, so a launcher asks for
        a password or a code); never a password, a hash or a code."""
        d = {"id": self.id, "name": self.name, "owner": self.owner.brief(),
             "members": [p.id for p in self.members], "ranked": self.ranked,
             "build": self.build_id, "compat_group": self.compat_group if all(
                 getattr(p, "compat_group", "") == self.compat_group for p in self.members) else "",
             "status": self.status(),
             "watch": self.watch and not self.private}
        if self.size != 2:
            d.update(size=self.size, rotation=self.rotation)
        if self.mode == "tables":
            d.update(mode="tables", tables=[{
                "id": table.id, "players": [q.id for q in table.players()],
                "match": table.match.id if table.match is not None else None,
                "watch": table.watch and not self.private} for table in self.tables])
        if self.lock is not None:
            d.update(private=True, lock=self.lock)
        if self.training:
            d["training"] = True        # (older launchers ignore it; they cannot join: _room_training_check)
        elif not self.ranked:
            d["first_to"] = self.first_to
        return d


class RoomsMixin:
    """Methods of LobbyServer (lobby.py): self.rooms, self.cfg, self.players ..."""

    def _rooms_init(self):
        self.room_codes = {}                     # HMAC of an invite code -> Room
        self._room_code_key = os.urandom(32)     # made at start, never stored: the codes die with the process
        g = max(1, self.cfg.room_guesses)
        per = max(1.0, self.cfg.room_guess_seconds)
        self.room_guess = KeyedBuckets(rate=1.0 / per, burst=g)               # per player (account / guest name)
        self.room_guess_addr = KeyedBuckets(rate=2.0 / per, burst=2 * g)      # per internet address (IPv6: /64)
        self.room_guess_n56 = KeyedBuckets(rate=4.0 / per, burst=4 * g)       # IPv6: per /56 (256 /64s)
        self.room_guess_n48 = KeyedBuckets(rate=8.0 / per, burst=8 * g)       # IPv6: per /48 (65,536 /64s)
        self.room_guess_room = KeyedBuckets(rate=3.0 / per, burst=4 * g)      # per room, shared by every network
        # per room and guessing network (IPv4 address / IPv6 /48), spent before the shared budget: guessers from
        # elsewhere can never use up the tries of a member's network
        self.room_guess_lane = KeyedBuckets(rate=1.0 / max(1.0, self.cfg.room_lane_seconds),
                                            burst=max(1, self.cfg.room_lane_guesses))
        # new room passwords hashed per internet address (a guest's own budget starts again with every new name)
        self.room_pw_addr = KeyedBuckets(rate=1.0 / 6.0, burst=10)

    # ------------------------------------------------------------------ helpers
    def _can_private(self, p_or_conn):
        caps = getattr(p_or_conn, "caps", None)
        if caps is None:
            conn = getattr(p_or_conn, "conn", None)
            caps = getattr(conn, "caps", ()) if conn is not None else ()
        return "private_rooms" in caps

    def _need_private_cap(self, conn):
        if "private_rooms" not in conn.caps:
            raise LobbyError(proto.E_NOT_ALLOWED, "private rooms need a newer launcher; update it")

    @staticmethod
    def _room_tables_check(r, p_or_conn):
        caps = getattr(p_or_conn, "caps", None)
        if caps is None:
            caps = getattr(getattr(p_or_conn, "conn", None), "caps", ())
        if r.mode == "tables" and "room_tables" not in caps:
            raise LobbyError(proto.E_NOT_ALLOWED, "simultaneous room tables need a newer launcher; update it")

    @staticmethod
    def _room_table(r, number):
        number = proto.room_table(number, len(r.tables))
        return r.tables[number - 1]

    def _room_owner(self, p):
        r = p.room
        if r is None or r.id not in self.rooms:
            raise LobbyError(proto.E_STATE, "not in a room")
        if r.owner is not p:
            raise LobbyError(proto.E_NOT_ALLOWED, "only the room's host can do that")
        return r

    def _code_hash(self, norm):
        return hmac.new(self._room_code_key, norm.encode("ascii"), hashlib.sha256).digest()

    def _room_unlock(self, r):
        if r.code_key is not None and self.room_codes.get(r.code_key) is r:
            del self.room_codes[r.code_key]
        r.lock = r.secret = r.code_key = None

    def _room_new_code(self, r):
        """A fresh invite code for r (the old one stops working). -> the code, for the host's reply only."""
        self._room_unlock(r)
        while True:
            code = new_code()
            key = self._code_hash(normalize_code(code))
            if key not in self.room_codes:
                break
        self.room_codes[key] = r
        r.lock, r.code_key = "code", key
        return code

    async def _room_hash(self, p, pw):
        """Hash a new room password (scrypt on a worker thread); counted like a password change."""
        akey = getattr(p.conn, "akey", None)
        if not self.pw_ops.take("room:" + self._block_key(p)) or (akey and not self.room_pw_addr.take(akey)):
            raise LobbyError(proto.E_RATE, "too many password changes; wait a minute")
        return await self._pw(hash_password, pw, self.cfg.scrypt_n)

    @staticmethod
    def _conn_ip(conn):
        return getattr(conn, "ip", None) or conn.akey

    def _guess_net(self, conn):
        """The network a guess comes from, for a room's lanes, the host's count and room_bar: an IPv4 address, an
        IPv6 /48 (proto.address_net)."""
        return proto.address_net(self._conn_ip(conn))

    def _guess_keys(self, p, conn):
        """The guesser's own budgets: the player, the address and (IPv6) the /56 and /48 around it."""
        keys = [(self.room_guess, "p:" + self._block_key(p)), (self.room_guess_addr, "ip:" + conn.akey)]
        ip = self._conn_ip(conn)
        for b, prefix in ((self.room_guess_n56, 56), (self.room_guess_n48, 48)):
            k = proto.address_key(ip, prefix)
            if k != conn.akey:                   # (IPv4: the address is the only level)
                keys.append((b, f"n{prefix}:{k}"))
        return keys

    def _guess_refused(self, keys):
        self._guess_wait(max(b.wait(k) for b, k in keys))

    @staticmethod
    def _guess_wait(wait):
        if wait > 0:
            sec = max(1, int(wait + 0.999))
            raise LobbyError(proto.E_RATE, f"too many wrong room passwords; try again in {sec} s", retry=sec)

    def _guess_room_key(self, r, net):
        """Which of the room's budgets this guess spends: the guessing network's own lane while it has tries, else the
        room's shared one; refused (with the wait) when neither has. Guessers elsewhere can empty the shared budget,
        never this network's lane -- so a member's first tries are always checked."""
        if net in r.barred:
            raise LobbyError(proto.E_NOT_ALLOWED, "the room's host turned away password guesses from your network; "
                                                  "ask the host for an invite")
        lane = (self.room_guess_lane, f"{r.id}|{net}")
        shared = (self.room_guess_room, r.id)
        for b, k in (lane, shared):
            if b.peek_ok(k):
                return b, k
        self._guess_wait(min(lane[0].wait(lane[1]), shared[0].wait(shared[1])))

    def _guess_wrong(self, p, r, what, net=None):
        self._count("room_wrong_guesses")
        if r is not None and net is not None:
            r.wrong.append((time.monotonic(), net))
            self.dirty = True                    # (the host's view shows the count)
        # (who and which room -- never what was typed, never the address)
        log.info("room %s: wrong %s from %s", r.id if r is not None else "?", what, p.name)

    def _room_guesses(self, r):
        """The host's view of the wrong passwords: how many in the last GUESS_WINDOW seconds and from how many
        networks (those not turned away), how many networks are turned away, whether the shared budget is used up."""
        cut = time.monotonic() - GUESS_WINDOW
        while r.wrong and r.wrong[0][0] < cut:
            r.wrong.popleft()
        recent = [n for _t, n in r.wrong if n not in r.barred]
        return {"wrong": len(recent), "networks": len(set(recent)), "barred": len(r.barred),
                "busy": not self.room_guess_room.peek_ok(r.id)}

    async def _room_check_password(self, r, p, conn, pw):
        """Let p into locked room r with its password, or raise. Constant-time compare (store.check_password); wrong
        guesses limited per player and address (the guesser's own budgets) and per room (the network's lane, then
        the room's shared budget)."""
        own = self._guess_keys(p, conn)
        self._guess_refused(own)
        net = self._guess_net(conn)
        keys = own + [self._guess_room_key(r, net)]
        for b, k in keys:                        # counted before the slow check, given back when it was right
            b.take(k)
        pw = clean_room_password(pw)
        secret = r.secret
        ok = False
        if pw is not None and secret is not None:
            try:
                ok = await self._pw(check_password, pw, secret)
            except LobbyError:                   # "server busy": not an attempt at all
                for b, k in keys:
                    b.give(k)
                raise
        if ok and r.secret is not secret:        # the host changed it meanwhile
            for b, k in keys:
                b.give(k)
            raise LobbyError(proto.E_STATE, "the room's password changed; try again")
        if not ok:
            self._guess_wrong(p, r, "password", net)
            raise LobbyError(proto.E_AUTH, "wrong room password")
        for b, k in keys:
            b.give(k)

    def _room_by_code(self, p, conn, code):
        """The room invite code `code` opens, or raise (a wrong code counts like a wrong password)."""
        keys = self._guess_keys(p, conn)
        self._guess_refused(keys)
        norm = normalize_code(code)
        key = self._code_hash(norm) if norm else None
        r = self.room_codes.get(key) if key is not None else None
        if r is None or r.id not in self.rooms or r.code_key is None or not hmac.compare_digest(r.code_key, key):
            for b, k in keys:
                b.take(k)
            self._guess_wrong(p, None, "invite code")
            raise LobbyError(proto.E_AUTH, "no room has that invite code")
        return r

    # ------------------------------------------------------------------ requests
    async def h_room_create(self, conn, msg):
        p = conn.player
        self._refuse_draining()
        if p.status != "idle":
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        ranked = bool(msg.get("ranked", False))
        mode = proto.room_mode(msg.get("mode", "line"))
        if mode == "tables" and not {"room_tables", "private_rooms"}.issubset(conn.caps):
            raise LobbyError(proto.E_NOT_ALLOWED, "simultaneous room tables need a newer launcher; update it")
        size, rotation, lock, hidden, pw = 2, "winner", None, False, None
        if "private_rooms" in conn.caps:          # (an older launcher's room is a classic, open one, as before)
            size = msg.get("size", 2)
            if isinstance(size, bool) or not isinstance(size, int) or not 2 <= size <= self.cfg.room_max_size:
                raise LobbyError(proto.E_BAD_REQUEST, f"rooms hold 2 to {self.cfg.room_max_size} players")
            rotation = msg.get("rotation") or "winner"
            if rotation not in ROTATIONS:
                raise LobbyError(proto.E_BAD_REQUEST, "rotation is winner or queue")
            lock = msg.get("private") or None
            if lock not in (None,) + LOCKS:
                raise LobbyError(proto.E_BAD_REQUEST, "private is password or code")
            hidden = bool(msg.get("hidden"))
            if lock == "password":
                pw = clean_room_password(msg.get("password"))
                if pw is None:
                    raise LobbyError(proto.E_BAD_REQUEST, "room passwords are 4-64 characters, no space at either end")
            if ranked and (size > 2 or lock or hidden):
                raise LobbyError(proto.E_NOT_ALLOWED, "private and community rooms are casual (unranked)")
        training = self._room_training_opt(conn, msg, ranked)      # (matchrules.py)
        rematch_policy, auto_skip = self._rematch_room_options(conn, msg, ranked, size, mode)
        if mode == "tables" and (ranked or training):
            raise LobbyError(proto.E_NOT_ALLOWED, "simultaneous room tables are casual and cannot be training rooms")
        first_to = proto.casual_first_to(msg.get("first_to", 1))
        if ranked or training or not {"sets", "casual_sets"}.issubset(conn.caps):
            first_to = 1
        if ranked and not self.cfg.ranked_rooms:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked matches come from the ranked queue on this server")
        if ranked and p.guest and not self.cfg.guest_ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked needs an account")
        if ranked:
            self._check_speed(p)
        # Check both submitted and published text: truncation must not hide a term,
        # and removing control characters can join its letters.
        raw_name = str(msg.get("name") or f"{p.name}'s room")
        name = proto.clean_text(raw_name, 32)
        self._check_filtered_text(raw_name, "room", p)
        if name != raw_name:
            self._check_filtered_text(name, "room", p)
        self._abandon_set(p)
        secret = await self._room_hash(p, pw) if pw is not None else None
        if p.status != "idle" or conn.closed:     # (it changed while the password was hashed)
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        if pw is not None:  # The policy may have reloaded while the hash was awaited.
            self._check_filtered_text(raw_name, "room", p)
            if name != raw_name:
                self._check_filtered_text(name, "room", p)
        r = Room(p, name, ranked, size, rotation, first_to, mode)
        r.hidden = hidden
        r.training = training
        r.rematch_policy, r.auto_skip_after_round = rematch_policy, auto_skip
        code = None
        if lock == "password":
            r.lock, r.secret = "password", secret
        elif lock == "code":
            code = self._room_new_code(r)
        self.rooms[r.id] = r
        p.room, p.status = r, "room"
        self.dirty = True
        if size > 2 or lock or hidden or training:
            log.info("room %s: %s made a %s%s room for %d%s%s", r.id, p.name, "training " if training else "",
                     rotation if size > 2 else "two-player", size, f", locked ({lock})" if lock else "",
                     ", hidden" if hidden else "")
        reply = {"t": "room", "room": self._room_view(r, p)}
        if code is not None:
            reply["code"] = code                 # (to the host only; the server keeps its HMAC)
        return reply

    async def h_room_join(self, conn, msg):
        p = conn.player
        self._refuse_draining()
        by_code = msg.get("code") is not None and "private_rooms" in conn.caps
        if by_code:
            r = self._room_by_code(p, conn, msg.get("code"))
            if msg.get("room") is not None and msg.get("room") != r.id:
                self._guess_wrong(p, r, "invite code")
                raise LobbyError(proto.E_AUTH, "no room has that invite code")
        else:
            r = self.rooms.get(msg.get("room"))
            if r is None or (r.hidden and p not in r.members):
                raise LobbyError(proto.E_NOT_FOUND, "no such room")
            if r.lock is not None and "private_rooms" not in conn.caps:
                raise LobbyError(proto.E_NOT_ALLOWED, "private rooms need a newer launcher; update it")
        self._room_may_join(r, p)
        if r.lock == "password" and not by_code:
            await self._room_check_password(r, p, conn, msg.get("password"))
            if r.id not in self.rooms or conn.closed:
                raise LobbyError(proto.E_NOT_FOUND, "no such room")
            self._room_may_join(r, p)            # (again: the room or the player may have changed meanwhile)
        elif r.lock == "code" and not by_code:
            raise LobbyError(proto.E_AUTH, "no room has that invite code")
        self._abandon_set(p)
        self._room_add(r, p)
        return {"t": "room", "room": self._room_view(r, p)}

    def _room_may_join(self, r, p):
        self._room_tables_check(r, p)
        if p.status != "idle":
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        if p in r.members:
            raise LobbyError(proto.E_STATE, "you are in that room")
        if len(r.members) >= r.size:
            raise LobbyError(proto.E_FULL, "room is full")
        if not compatible(r, p) or any(not compatible(q, p) for q in r.members):
            raise LobbyError(proto.E_VERSION, "that player runs a different build of the game")
        if r.ranked and p.guest and not self.cfg.guest_ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked needs an account")
        if r.ranked:
            self._check_speed(p)
        if self._block_key(p) in r.kicked:
            raise LobbyError(proto.E_NOT_ALLOWED, "the room's host removed you from this room")
        self._room_training_check(r, p)
        if any(self._is_blocked(p, q) for q in r.members):
            raise LobbyError(proto.E_NOT_ALLOWED, "you cannot join this room")

    def _room_add(self, r, p, invited=False):
        """p comes into r (joined, or accepted an invite): the match starts when there is a pair."""
        r.members.append(p)
        r.line.append(p)
        p.room, p.status = r, "room"
        self.dirty = True
        if r.community:
            self._room_schedule(r, SOON)
        else:
            asyncio.get_running_loop().call_soon(self._room_start, r, invited)

    async def h_room_leave(self, conn, msg):
        p = conn.player
        if p.room is None:
            raise LobbyError(proto.E_STATE, "not in a room")
        if p.match is not None and not self._training_leave(p):     # (a training room: any time, matchrules.py)
            raise LobbyError(proto.E_BUSY, "finish the match first")
        self._leave_room(p)

    async def h_room_lock(self, conn, msg):
        """The host locks, unlocks or hides the room: lock password (with `password`) | code (a new invite code, the
        old one stops working) | none (open); `hidden` true/false. Members stay; spectators who are not members are
        sent away when the room becomes private."""
        p = conn.player
        self._need_private_cap(conn)
        r = self._room_owner(p)
        if r.ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "private and community rooms are casual (unranked)")
        lock = msg.get("lock")                   # (absent: only `hidden` changes)
        if lock is not None and lock not in LOCKS + ("none",):
            raise LobbyError(proto.E_BAD_REQUEST, "lock is password, code or none")
        code = None
        if lock == "password":
            pw = clean_room_password(msg.get("password"))
            if pw is None:
                raise LobbyError(proto.E_BAD_REQUEST, "room passwords are 4-64 characters, no space at either end")
            secret = await self._room_hash(p, pw)
            if p.room is not r or r.owner is not p or r.id not in self.rooms:
                raise LobbyError(proto.E_STATE, "not in a room")
            self._room_unlock(r)
            r.lock, r.secret = "password", secret
        elif lock == "code":                      # (a new code every time: the old one stops working)
            code = self._room_new_code(r)
        elif lock == "none":
            self._room_unlock(r)
        if "hidden" in msg:
            r.hidden = bool(msg.get("hidden"))
        log.info("room %s: %s set the lock to %s%s", r.id, p.name, r.lock or "none", ", hidden" if r.hidden else "")
        self._room_spec_check(r)
        self.dirty = True
        reply = {"t": "room", "room": self._room_view(r, p)}
        if code is not None:
            reply["code"] = code
        return reply

    async def h_room_kick(self, conn, msg):
        """The host removes a member (`player`: its id). Not while they play the room's running match. They cannot
        come back into this room (a password, a code or an invite)."""
        p = conn.player
        self._need_private_cap(conn)
        r = self._room_owner(p)
        q = self.players.get(msg.get("player"))
        if q is None or q not in r.members:
            raise LobbyError(proto.E_NOT_FOUND, "that player is not in your room")
        if q is p:
            raise LobbyError(proto.E_BAD_REQUEST, "you cannot remove yourself; leave the room instead")
        m = q.match
        if m is not None and m.state == "playing":
            raise LobbyError(proto.E_BUSY, "you can remove that player after their match")
        if m is not None and m.state not in ("done", "cancelled"):
            self.cancel_match(m, "opponent_left", by=q)
        r.kicked[self._block_key(q)] = q.name
        self._leave_room(q)
        q.send({"t": "notice", "code": "room_kicked", "room": r.id, "msg": "the room's host removed you from this room"})
        self._count("room_kicks")
        log.info("room %s: %s removed %s", r.id, p.name, q.name)
        return {"t": "room", "room": self._room_view(r, p)}

    async def h_room_bar(self, conn, msg):
        """The host turns away every network that typed a wrong password into this room in the last 10 minutes: their
        guesses at this room are refused from now on, before they cost the room's budget anything (members already
        in the room stay; a friend's invite still brings anybody in). The host never learns who or where they are."""
        p = conn.player
        self._need_private_cap(conn)
        r = self._room_owner(p)
        if r.lock != "password":
            raise LobbyError(proto.E_STATE, "only a room with a password counts wrong guesses")
        cut = time.monotonic() - GUESS_WINDOW
        new = {n for t, n in r.wrong if t >= cut} - r.barred
        new = set(sorted(new)[:max(0, BARRED_MAX - len(r.barred))])
        r.barred |= new
        self._count("room_bars")
        log.info("room %s: %s turned away %d network(s) (%d in all)", r.id, p.name, len(new), len(r.barred))
        self.dirty = True
        return {"t": "room", "room": self._room_view(r, p), "barred": len(new)}

    async def h_room_line(self, conn, msg):
        """Community rooms: `in` false = sit out (stay in the room, skip your turns), true = back in line."""
        p = conn.player
        r = p.room
        if r is None or r.id not in self.rooms:
            raise LobbyError(proto.E_STATE, "not in a room")
        if not r.community:
            raise LobbyError(proto.E_STATE, "only rooms for 3 or more players take turns")
        self._room_line(r, p, bool(msg.get("in", True)))
        return {"t": "room", "room": self._room_view(r, p)}

    def _room_line(self, r, p, back):
        if back:
            if p not in r.line:
                r.line.append(p)
            self._room_schedule(r, SOON)
        else:
            if p.match is not None and p.match.room is r:
                raise LobbyError(proto.E_BUSY, "finish the match first")
            if p in r.line:
                r.line.remove(p)
            if r.mode == "tables":
                for table in r.tables:
                    if p not in table.pair:
                        continue
                    if table.set is not None and table.set.state == "active":
                        self._end_set(table.set, "left", by=p)
                    self._room_table_release(table)
            if r._casual_set_active() and p in r.set.players:
                self._end_set(r.set, "left", by=p)       # sitting out between games gives up this table turn
            self._room_schedule(r)
        self.dirty = True

    async def h_room_pair(self, conn, msg):
        """The host sets an idle table's next pair; an active match or set never moves."""
        r = self._room_owner(conn.player)
        self._room_tables_check(r, conn)
        if r.mode != "tables":
            raise LobbyError(proto.E_STATE, "this room does not have simultaneous tables")
        table = self._room_table(r, msg.get("table"))
        ids = msg.get("players")
        if not isinstance(ids, list) or len(ids) != 2 or not all(isinstance(i, str) for i in ids) or ids[0] == ids[1]:
            raise LobbyError(proto.E_BAD_REQUEST, "choose two different players for the table")
        pair = [next((q for q in r.members if q.id == i), None) for i in ids]
        if table.active() or any(q is None or not self._room_table_free(r, q) for q in pair):
            raise LobbyError(proto.E_BUSY, "choose available players and an idle table")
        if self._is_blocked(*pair):
            raise LobbyError(proto.E_NOT_ALLOWED, "you cannot pair these players")
        # Reservations are not matches yet: a host may rearrange them atomically.
        for other in r.tables:
            if other is table or any(q in other.pair for q in pair):
                if other.active():
                    raise LobbyError(proto.E_BUSY, "choose available players and an idle table")
        for other in r.tables:
            if other is table or any(q in other.pair for q in pair):
                self._room_table_release(other)
        table.pair = pair
        self._room_table_schedule(table, SOON)
        self._room_schedule(r, SOON)
        return {"t": "room", "room": self._room_view(r, conn.player)}

    # ------------------------------------------------------------------ matches in a room
    def _room_table_free(self, r, q):
        """Available for a new set, independently of a countdown reservation."""
        if q not in r.line or not q.online or q.match is not None or q.status != "room" or q.room is not r:
            return False
        if any(t.active() and q in t.pair for t in r.tables):
            return False
        try:
            self._set_free(q)
        except LobbyError:
            return False
        return True

    def _room_table_release(self, table):
        if table.next_timer is not None:
            table.next_timer.cancel()
        table.next_timer, table.next_at = None, None
        table.pair = []
        if table.set is not None and table.set.state != "active":
            table.set = None
        self.dirty = True

    def _room_table_schedule(self, table, delay):
        if table.next_timer is not None:
            return
        table.next_at = time.time() + delay
        table.next_timer = asyncio.get_running_loop().call_later(delay, self._room_table_next, table)
        self.dirty = True

    def _room_tables_schedule(self, r, delay=None):
        if r.id not in self.rooms or self.draining:
            return
        delay = self.cfg.room_next_seconds if delay is None else delay
        # Discard only reservations that became invalid; running sets own their seats.
        for table in r.tables:
            if not table.active() and table.pair and not all(self._room_table_free(r, q) for q in table.pair):
                self._room_table_release(table)
        reserved = [q for table in r.tables for q in table.pair]
        free = [q for q in r.line if q not in reserved and self._room_table_free(r, q)]
        for table in r.tables:
            if table.active() or table.pair:
                continue
            pair = next(([a, b] for i, a in enumerate(free) for b in free[i + 1:]
                         if not self._is_blocked(a, b)), None)
            if pair is None:
                break
            table.pair = pair
            free = [q for q in free if q not in pair]
            self._room_table_schedule(table, delay)

    def _room_table_next(self, table):
        table.next_timer, table.next_at = None, None
        r = table.room
        self.dirty = True
        if r.id not in self.rooms or self.draining:
            self._room_table_release(table)
            return
        if table.active():
            return
        pair = table.pair
        if len(pair) != 2 or not all(self._room_table_free(r, q) for q in pair) or self._is_blocked(*pair):
            self._room_table_release(table)
            self._room_schedule(r)
            return
        a, b = pair
        table.match = self.create_match(*self._casual_sides(a, b), ranked=False, origin="room", room=r,
                                       first_to=r.first_to, table=table)
        table.match.line_order = (a, b)
        if table.match.state == "cancelled":
            table.match = None

    def _room_table_over(self, r, table, players):
        """A whole table turn ends: both players return behind the waiting members."""
        self._room_table_release(table)
        for q in players:
            if q in r.line:
                r.line.remove(q)
                r.line.append(q)
        self._room_schedule(r)

    def _room_start(self, r, invited=False):
        """Classic room: its two members' match, with a ready check -- except right after a friend accepted an invite
        to the room (origin "invite": both have said yes already). Community room: the first two free players of its
        line (always with a ready check)."""
        if r.mode == "tables":
            self._room_schedule(r, SOON)
            return
        if r.id not in self.rooms or r.match is not None or r._casual_set_active() or self.draining:
            return
        if r.community:
            pair = self._room_next_pair(r)
            if pair is None:
                return
            a, b = pair
            invited = False
        else:
            if len(r.members) != 2:
                return
            a, b = r.members
        if any(not q.online or q.match is not None for q in (a, b)):
            return
        gs = r.set if r.set is not None and r.set.state == "active" and \
            {id(q) for q in r.set.players} == {id(a), id(b)} else None
        ranked = r.ranked and not r.community
        if not ranked:
            sides = self._casual_sides(a, b)
        elif gs is not None:
            sides = tuple(gs.players)            # the next game of the room's set: its sides stay
        else:
            sides = self._drawn_sides(a, b, "ranked room")     # a new ranked set: a coin, not the members' order
        r.match = self.create_match(*sides, ranked=ranked,
                                    origin="invite" if invited else "room", room=r, game_set=gs,
                                    first_to=r.first_to)
        r.match.line_order = (a, b)              # (the line's order, whatever sides the players asked for: casual.py)
        if r.match.state == "cancelled":
            r.match = None

    def _room_next_pair(self, r):
        """The first two free players of the line who have not blocked one another (a block made in the room makes
        the blocker leave it; this only keeps a pair that got in some other way apart -- security review 3)."""
        free = []
        for q in r.line:
            if not q.online or q.match is not None or q.status != "room" or q.room is not r:
                continue
            try:
                self._set_free(q)                # (a tournament set called for them, a ranked set: not now)
            except LobbyError:
                continue
            free.append(q)
        for i, a in enumerate(free):
            for b in free[i + 1:]:
                if not self._is_blocked(a, b):
                    return [a, b]
        return None

    def _room_schedule(self, r, delay=None):
        """Community rooms: count down to the next match when nothing runs and two are free in the line."""
        if r.mode == "tables":
            self._room_tables_schedule(r, delay)
            return
        if not r.community or r.id not in self.rooms:
            return
        if r.match is not None or r._casual_set_active() or self.draining or self._room_next_pair(r) is None:
            if r.next_timer is not None and r.match is None:
                r.next_timer.cancel()
                r.next_timer, r.next_at = None, None
            self.dirty = True
            return
        if r.next_timer is not None:
            if delay is None or r.next_at is None or r.next_at - time.time() <= delay:
                return
            r.next_timer.cancel()                # (sooner: the room was waiting for a second player)
        delay = self.cfg.room_next_seconds if delay is None else delay
        r.next_at = time.time() + delay
        r.next_timer = asyncio.get_running_loop().call_later(delay, self._room_next, r)
        self.dirty = True

    def _room_next(self, r):
        r.next_timer, r.next_at = None, None
        self.dirty = True
        self._room_start(r)
        if r.match is None:
            self._room_schedule(r)

    def _room_match_cancelled(self, r, m, reason, by):
        """A room's match was cancelled before it started (cancel_match). Community rooms: who declined or let the
        ready check run out sits out; a failed connection puts both at the back of the line; then the next match."""
        if not r.community or r.id not in self.rooms:
            return
        table = getattr(m, "table", None)
        if m.set is not None and getattr(m.set, "casual", False):
            m.set._room_turn_done = True        # cancellation already has the line rule below
        if reason in ("declined", "ready_timeout") or (table is not None and reason not in ("opponent_left",)):
            # A failed table setup waits for an explicit return, rather than repeatedly
            # spending relay capacity or retrying a broken UDP route every countdown.
            out = [by] if reason in ("declined", "ready_timeout") and by is not None else list(m.players)
            for q in out:
                if q in r.line and q in r.members:
                    r.line.remove(q)
                    q.send({"t": "notice", "code": "room_away", "room": r.id,
                            "msg": "you sit out in the room; press Back in line to play again"})
        elif reason not in ("opponent_left",):
            for q in m.players:
                if q in r.line:
                    r.line.remove(q)
                    r.line.append(q)
        if table is not None:
            self._room_table_release(table)
        self._room_schedule(r)

    def _room_match_over(self, r, m, status, winner):
        """A room's match has a result (_finish). Community rooms: the line moves by the room's rule, then the next
        match after T5L_ROOM_NEXT_SECONDS."""
        if r is None or not r.community or r.id not in self.rooms:
            return
        gs = m.set
        if gs is not None and getattr(gs, "casual", False):
            if gs.state == "active":
                return                          # one complete set occupies one turn at the table
            outcome = gs.outcome or {}
            self._room_set_over(r, gs, outcome.get("status", "void"), outcome.get("winner"))
            return
        table = getattr(m, "table", None)
        if table is not None:
            if gs is not None and gs.state == "active" and gs.current is None and not gs.rated:
                self._end_set(gs, "expired")
            self._room_table_over(r, table, m.players)
            return
        order = getattr(m, "line_order", None) or m.players     # (P1 / P2 may be the other way round: casual.py)
        self._room_turn_over(r, m.players, order, status,
                             m.players[winner] if winner is not None else None)
        # Legacy casual games have an open-ended rematch group, not an automatic set.
        if gs is not None and gs.state == "active" and gs.current is None and not gs.rated:
            self._end_set(gs, "expired")

    def _room_set_over(self, r, gs, status, winner):
        """A casual set is one table turn, including an unfinished set left between games.

        Called by the deciding game's result, or by _end_set when there is no current game.
        The marker prevents a cancellation and its set-ending callback from moving the line twice.
        """
        if r is None or not r.community or r.id not in self.rooms or getattr(gs, "_room_turn_done", False):
            return
        gs._room_turn_done = True
        table = getattr(gs, "table", None)
        if table is not None:
            self._room_table_over(r, table, gs.players)
            return
        first = gs.matches[0] if gs.matches else None
        order = getattr(first, "line_order", None) or gs.players
        self._room_turn_over(r, gs.players, order, status, winner)

    def _room_turn_over(self, r, players, order, status, winner):
        """Move the line once after a single legacy game or a complete/abandoned casual set."""
        if r.rotation == "winner":
            # winner stays; the loser to the back (no winner: both, the first in line first)
            stay = winner if status in COUNTED and winner in players else None
        else:
            # everyone in turn: the one who was at the table longer (first in line) goes to the back, the other
            # stays for one more match -- every member plays two in a row, against both neighbours in the line,
            # whoever wins (with three, everyone meets everyone)
            stay = order[1]
        for q in order:
            if q is not stay and q in r.line:
                r.line.remove(q)
                r.line.append(q)
        if stay is not None and stay in r.line:
            r.line.remove(stay)
            r.line.insert(0, stay)
        self._room_schedule(r)

    # ------------------------------------------------------------------ leaving
    def _leave_room(self, p):
        r = p.room
        if r is None:
            return
        for inv in [i for i in self.invites.values() if i.room is r and i.src is p]:
            self._end_invite(inv, "cancelled")           # (an invite to a room its owner left)
        p.room = None
        if p.status == "room":
            p.status = "idle"
        if p in r.members:
            r.members.remove(p)
        if p in r.line:
            r.line.remove(p)
        r.sent.pop(p.id, None)
        for seat in r.tables if r.mode == "tables" else [r]:
            m = seat.match
            if m is not None and p in m.players and m.state not in ("playing", "done"):
                self.cancel_match(m, "opponent_left", by=p)
            gs = seat.set
            if gs is not None and gs.state == "active" and gs.current is None and p in gs.players and not (
                    gs.rated and not p.online):       # (ranked set's away window decides, 1.1.9)
                self._decline_recent(gs, p)
                self._end_set(gs, "left", by=p)
            if seat is not r and p in seat.pair and not seat.active():
                self._room_table_release(seat)
        if r.private and p.watching is not None and getattr(p.watching.match, "room", None) is r:
            self._spec_unwatch(p, "not_allowed")
        if not r.members:
            self._room_close(r)
        else:
            if r.owner is p:
                r.owner = r.members[0]
                if r.private or r.community:
                    log.info("room %s: %s is the host now", r.id, r.owner.name)
            self._room_schedule(r)
        self.dirty = True

    def _room_close(self, r):
        self.rooms.pop(r.id, None)
        self._room_unlock(r)
        if r.next_timer is not None:
            r.next_timer.cancel()
            r.next_timer, r.next_at = None, None
        for table in r.tables:
            self._room_table_release(table)

    # ------------------------------------------------------------------ spectating (spectating.py asks)
    def _room_spec_check(self, r):
        """r became private (or lost a member): spectators of its match who are not members stop watching."""
        if not r.private:
            return
        for st in list(self.streams.values()):
            if getattr(st.match, "room", None) is not r:
                continue
            for v in list(st.viewers):
                if v not in r.members:
                    self._spec_unwatch(v, "not_allowed")

    # ------------------------------------------------------------------ what members see
    def _room_view(self, r, viewer):
        """The room as a member sees it (the `room` message): the list entry plus the line, who plays, the next
        match, its rules. Never a password, a hash or a code."""
        d = r.public()
        if not r.community and not r.ranked and self._rematch_enabled() and self._rematch_capable(viewer):
            d.update(rematch_policy=r.rematch_policy, auto_skip_after_round=r.auto_skip_after_round)
        elif (not r.community and not r.ranked and self._skip_enabled()
              and "auto_skip_after_round_v1" in getattr(getattr(viewer, "conn", None), "caps", ())):
            d.update(auto_skip_after_round=r.auto_skip_after_round)     # (the round skip without the in-game rematch)
        playing = list(r.match.players) if r.match is not None else []
        if not playing and r._casual_set_active():
            playing = list(r.set.players)       # the table remains theirs during the between-game countdown
        if r.mode == "tables":
            playing = [q for table in r.tables if table.active() for q in table.players()]
        d.update({"size": r.size, "rotation": r.rotation, "lock": r.lock, "hidden": r.hidden,
                  "owner_id": r.owner.id,
                  "players": [dict(q.brief(), state="playing" if q in playing else
                                   ("line" if q in r.line else "away")) for q in r.members],
                  "line": [q.id for q in r.line], "playing": [q.id for q in playing],
                  "next": None, "watch": False})
        if r.set is not None and getattr(r.set, "casual", False):
            d["set"] = r.set.info()
        if viewer is r.owner and r.lock == "password":
            d["guesses"] = self._room_guesses(r)         # (the host only: counts, never who or from where)
        if r.mode == "tables":
            d["tables"] = [self._room_table_view(r, table, viewer) for table in r.tables]
            d["watch"] = any(table["watch"] for table in d["tables"])
            return d
        if r.next_at is not None:
            pair = self._room_next_pair(r)
            d["next"] = {"at": round(r.next_at, 1), "players": [q.id for q in pair] if pair else []}
        m = self._spec_room_match(r)                 # (between a match and its rematch: while its stream is alive)
        if m is not None and viewer not in m.players and self._can(viewer, "spectate"):
            d["watch"] = self._spec_refusal(viewer, m) is None
        return d

    def _room_table_view(self, r, table, viewer):
        d = {"id": table.id, "players": [q.id for q in table.players()],
             "match": table.match.id if table.match is not None else None,
             "set": table.set.info() if table.set is not None else None,
             "next": None, "watch": False}
        if table.next_at is not None:
            d["next"] = {"at": round(table.next_at, 1), "players": d["players"]}
        m = self._spec_room_match(r, table)
        if m is not None and viewer not in m.players and self._can(viewer, "spectate"):
            d["watch"] = self._spec_refusal(viewer, m) is None
        return d

    def _room_push(self):
        """Every member gets its room's view when it changed (from the lobby broadcast tick)."""
        for r in list(self.rooms.values()):
            for q in list(r.members):
                if q.conn is None or q.conn.closed:
                    continue
                v = self._room_view(r, q)
                if r.sent.get(q.id) != v:
                    r.sent[q.id] = v
                    q.send({"t": "room", "room": v})

    # ------------------------------------------------------------------ the lobby list
    def _room_lists(self):
        """The rooms of the lobby list: (for launchers with the "private_rooms" cap, for older ones). A hidden room
        is in neither; a locked one only in the first."""
        new = {r.id: r.public() for r in self.rooms.values() if not r.hidden}
        old = {k: v for k, v in new.items() if not v.get("private")}
        return new, old
