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
  * wrong passwords / codes: per player, per internet address and per room (token buckets, T5L_ROOM_GUESSES then
    one per T5L_ROOM_GUESS_SECONDS), counted before the slow check and given back when it was right (parallel
    attempts on several connections cannot all pass while the first is hashed); the refusal says when to try again
    (`retry`, whole seconds, like a held-back invite);
  * passwords: 4-64 characters after Unicode NFC, any script, printable only (no control or format characters, no
    space at either end), at most 256 bytes of UTF-8;
  * setting a password costs a hash: counted like a password change (pw_ops, per player), and per address.

Older launchers (no "private_rooms" cap) never see a private room: the lobby list they get leaves them out; a join
by id is refused with a text they show ("update the launcher"); a friend's invite still brings them in (it is the
key). Community rooms work for them like any room: they see a ready check when it is their turn.

Messages (client -> server; docs/ONLINE.md "Protocol reference"):
    room_create {name, ranked, size, rotation, private: password|code, password, hidden}   -> room {room, code?}
    room_join   {room, password} | {room?, code}                                           -> room {room}
    room_lock   {lock: password|code|none, password, hidden}   (host)                      -> room {room, code?}
    room_kick   {player}                                       (host)                      -> room {room}
    room_line   {in: true|false}                               (community rooms)          -> room {room}
server -> client: room {room} (a member's view: line, who plays, the next match), notice room_kicked / room_away.
"""
import asyncio
import hashlib
import hmac
import logging
import os
import time

from .. import proto
from ..proto import (CODE_ALPHABET, CODE_LEN, LobbyError, clean_room_password,  # noqa: F401 -- (tests use them here)
                     new_room_code as new_code, normalize_room_code as normalize_code)
from .ratelimit import KeyedBuckets
from .store import COUNTED, check_password, hash_password

log = logging.getLogger("t5lobby")

ROTATIONS = ("winner", "queue")
LOCKS = ("password", "code")
SOON = 1.0                     # seconds before a room's first match once two are in its line


def _rid():
    return os.urandom(6).hex()


class Room:
    def __init__(self, owner, name, ranked, size=2, rotation="winner"):
        self.id = "r" + _rid()
        self.name = name
        self.owner = owner
        self.members = [owner]          # everyone in the room, in the order they came
        self.line = [owner]             # community rooms: the turn order (a member sitting out is not in it)
        self.size = size                # most members at once (2 = a classic room)
        self.rotation = rotation        # community rooms: winner (winner stays) | queue (everyone in turn)
        self.ranked = ranked
        self.match = None
        self.set = None                 # the room's running set (rematches in the room keep it)
        self.build_id = owner.build_id
        self.watch = False              # its match can be watched (spectating.py, set before each lobby list)
        self.lock = None                # None | "password" | "code"
        self.secret = None              # lock "password": its salted scrypt hash -- memory only, never sent or logged
        self.code_key = None            # lock "code": the code's HMAC (the server's index key), never the code
        self.hidden = False             # not in the lobby list at all
        self.kicked = {}                # block key -> name: removed by the host, not let back in
        self.next_timer = None          # community rooms: the countdown to the next match
        self.next_at = None             # ... when it ends (unix time, for the members' view)
        self.sent = {}                  # member id -> the last view pushed to it

    @property
    def community(self):
        return self.size > 2

    @property
    def private(self):
        """Locked or hidden: only its members may watch its match."""
        return self.lock is not None or self.hidden

    def status(self):
        return "playing" if self.match else ("full" if len(self.members) >= self.size else "open")

    def public(self):
        """The lobby list's entry. Nothing about a lock but that there is one (and which kind, so a launcher asks for
        a password or a code); never a password, a hash or a code."""
        d = {"id": self.id, "name": self.name, "owner": self.owner.brief(),
             "members": [p.id for p in self.members], "ranked": self.ranked,
             "build": self.build_id, "status": self.status(),
             "watch": self.watch and not self.private}
        if self.size != 2:
            d.update(size=self.size, rotation=self.rotation)
        if self.lock is not None:
            d.update(private=True, lock=self.lock)
        return d


class RoomsMixin:
    """Methods of LobbyServer (lobby.py): self.rooms, self.cfg, self.players ..."""

    def _rooms_init(self):
        self.room_codes = {}                     # HMAC of an invite code -> Room
        self._room_code_key = os.urandom(32)     # made at start, never stored: the codes die with the process
        g = max(1, self.cfg.room_guesses)
        per = max(1.0, self.cfg.room_guess_seconds)
        self.room_guess = KeyedBuckets(rate=1.0 / per, burst=g)               # per player (account / guest name)
        self.room_guess_addr = KeyedBuckets(rate=2.0 / per, burst=2 * g)      # per internet address
        self.room_guess_room = KeyedBuckets(rate=3.0 / per, burst=4 * g)      # per room, everybody together
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

    def _guess_keys(self, p, conn, r=None):
        keys = [(self.room_guess, "p:" + self._block_key(p)), (self.room_guess_addr, "ip:" + conn.akey)]
        if r is not None:
            keys.append((self.room_guess_room, r.id))
        return keys

    def _guess_refused(self, keys):
        wait = max(b.wait(k) for b, k in keys)
        if wait > 0:
            sec = max(1, int(wait + 0.999))
            raise LobbyError(proto.E_RATE, f"too many wrong room passwords; try again in {sec} s", retry=sec)

    def _guess_wrong(self, p, r, what):
        self._count("room_wrong_guesses")
        # (who and which room -- never what was typed)
        log.info("room %s: wrong %s from %s", r.id if r is not None else "?", what, p.name)

    async def _room_check_password(self, r, p, conn, pw):
        """Let p into locked room r with its password, or raise. Constant-time compare (store.check_password); wrong
        guesses limited per player, address and room."""
        keys = self._guess_keys(p, conn, r)
        self._guess_refused(keys)
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
            self._guess_wrong(p, r, "password")
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
        if ranked and not self.cfg.ranked_rooms:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked matches come from the ranked queue on this server")
        if ranked and p.guest and not self.cfg.guest_ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked needs an account")
        if ranked:
            self._check_speed(p)
        self._abandon_set(p)
        secret = await self._room_hash(p, pw) if pw is not None else None
        if p.status != "idle" or conn.closed:     # (it changed while the password was hashed)
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        name = proto.clean_text(msg.get("name") or f"{p.name}'s room", 32)
        r = Room(p, name, ranked, size, rotation)
        r.hidden = hidden
        code = None
        if lock == "password":
            r.lock, r.secret = "password", secret
        elif lock == "code":
            code = self._room_new_code(r)
        self.rooms[r.id] = r
        p.room, p.status = r, "room"
        self.dirty = True
        if size > 2 or lock or hidden:
            log.info("room %s: %s made a %s room for %d%s%s", r.id, p.name, rotation if size > 2 else "two-player",
                     size, f", locked ({lock})" if lock else "", ", hidden" if hidden else "")
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
        if p.status != "idle":
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        if p in r.members:
            raise LobbyError(proto.E_STATE, "you are in that room")
        if len(r.members) >= r.size:
            raise LobbyError(proto.E_FULL, "room is full")
        if r.build_id != p.build_id:
            raise LobbyError(proto.E_VERSION, "that player runs a different build of the game")
        if r.ranked and p.guest and not self.cfg.guest_ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked needs an account")
        if r.ranked:
            self._check_speed(p)
        if self._block_key(p) in r.kicked:
            raise LobbyError(proto.E_NOT_ALLOWED, "the room's host removed you from this room")
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
        if p.match is not None:
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
            self._room_schedule(r)
        self.dirty = True

    # ------------------------------------------------------------------ matches in a room
    def _room_start(self, r, invited=False):
        """Classic room: its two members' match, with a ready check -- except right after a friend accepted an invite
        to the room (origin "invite": both have said yes already). Community room: the first two free players of its
        line (always with a ready check)."""
        if r.id not in self.rooms or r.match is not None or self.draining:
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
        r.match = self.create_match(a, b, ranked=r.ranked and not r.community,
                                    origin="invite" if invited else "room", room=r, game_set=gs)
        if r.match.state == "cancelled":
            r.match = None

    def _room_next_pair(self, r):
        free = []
        for q in r.line:
            if not q.online or q.match is not None or q.status != "room" or q.room is not r:
                continue
            try:
                self._set_free(q)                # (a tournament set called for them, a ranked set: not now)
            except LobbyError:
                continue
            free.append(q)
            if len(free) == 2:
                return free
        return None

    def _room_schedule(self, r, delay=None):
        """Community rooms: count down to the next match when nothing runs and two are free in the line."""
        if not r.community or r.id not in self.rooms:
            return
        if r.match is not None or self.draining or self._room_next_pair(r) is None:
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
        if reason in ("declined", "ready_timeout"):
            out = [by] if by is not None else [q for q in m.players]
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
        self._room_schedule(r)

    def _room_match_over(self, r, m, status, winner):
        """A room's match has a result (_finish). Community rooms: the line moves by the room's rule, then the next
        match after T5L_ROOM_NEXT_SECONDS."""
        if r is None or not r.community or r.id not in self.rooms:
            return
        if r.rotation == "winner":
            # winner stays; the loser to the back (no winner: both, P1 first)
            stay = m.players[winner] if status in COUNTED and winner is not None else None
        else:
            # everyone in turn: the one who was at the table longer (P1: first in line) goes to the back, the other
            # stays for one more match -- every member plays two in a row, against both neighbours in the line,
            # whoever wins (with three, everyone meets everyone)
            stay = m.players[1]
        for q in m.players:
            if q is not stay and q in r.line:
                r.line.remove(q)
                r.line.append(q)
        if stay is not None and stay in r.line:
            r.line.remove(stay)
            r.line.insert(0, stay)
        # the two played their game: no rematch vote in a community room (the room picks the next match; h_rematch
        # refuses one) -- the match stays in `recent` for the post-game lag check
        gs = m.set
        if gs is not None and gs.state == "active" and gs.current is None and not gs.rated:
            self._end_set(gs, "expired")
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
        m = r.match
        if m is not None and p in m.players and m.state not in ("playing", "done"):
            self.cancel_match(m, "opponent_left", by=p)
        if r.set is not None and r.set.state == "active" and r.set.current is None and p in r.set.players:
            self._decline_recent(r.set, p)
            self._end_set(r.set, "left", by=p)
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
        playing = list(r.match.players) if r.match is not None else []
        d.update({"size": r.size, "rotation": r.rotation, "lock": r.lock, "hidden": r.hidden,
                  "owner_id": r.owner.id,
                  "players": [dict(q.brief(), state="playing" if q in playing else
                                   ("line" if q in r.line else "away")) for q in r.members],
                  "line": [q.id for q in r.line], "playing": [q.id for q in playing],
                  "next": None, "watch": False})
        if r.next_at is not None:
            pair = self._room_next_pair(r)
            d["next"] = {"at": round(r.next_at, 1), "players": [q.id for q in pair] if pair else []}
        if r.match is not None and viewer not in playing and self._can(viewer, "spectate"):
            d["watch"] = self._spec_refusal(viewer, r.match) is None
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
