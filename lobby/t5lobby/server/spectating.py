"""Spectators of live matches (docs/SPECTATE.md): the lobby server's side.

One player's launcher (the streamer) uploads the session's live stream -- the replay's data as the
game writes it, one zlib stream -- while somebody watches; the server keeps it from the session's
start and sends it to every spectator from there. The players' games only write a file; nothing
here can make them wait.

Who may watch a match that is being played:
    friends     a friend of either player (accounts)
    rooms       anybody in the lobby, for a room's match (a room is public)
    tournaments the tournaments branch decides (_spec_tournament_may_watch, a hook)
and only if both players allow it (spec_prefs: "allow spectators", default on in the launcher;
"also in ranked matches", default off), neither player has blocked the viewer, and the match has
fewer than T5L_MAX_SPECTATORS of them. Clients without the "spectate" cap never send spec_prefs,
so a match with an older launcher on either side cannot be watched, and they never get any of
these messages.

Messages (client -> server):
    spec_prefs {allow, ranked}             a player's privacy setting (sent after login and on change)
    watch {name} | {room}                  watch the match a friend plays / a room's match -> watching
    unwatch {}                             stop watching
    spec_data {stream, off, data, eof}     the streamer's next piece (base64), in order
    spec_fail {stream, why}                the streamer cannot send this stream
server -> client:
    watching {stream, match, players, ranked, began, spectators}     (the reply to watch)
    spec_want {stream, match, from}        streamer: send from this offset (the server has what is before it)
    spec_stop {stream}                     streamer: nobody watches any more (keep the place)
    spec_data {stream, off, data}          spectator: the next piece
    spec_end {stream, reason}              spectator: no more (over | stopped | not_allowed | too_long | left | ...)
    spectators {match, count}              players: how many watch them
"""
import asyncio
import base64
import logging
import time

from .. import proto
from ..proto import LobbyError
from .ratelimit import TokenBucket

log = logging.getLogger("t5lobby")

SEND_PIECE = 16384          # compressed bytes per spec_data to a spectator
PENDING_LIMIT = 192 * 1024  # a spectator's unsent output above this: wait before sending it more
MAX_UPLOAD_PIECE = 5120     # compressed bytes in one spec_data from the streamer (base64 under the 8 KB line limit)


class Stream:
    """The live stream of one netplay session (its first match's id), shared by its spectators."""

    def __init__(self, sid, match, streamer, rate_kb, began):
        self.id = sid
        self.match = match                 # the session's current Match (a rematch in the running games moves it)
        self.streamer = streamer           # the Player whose launcher uploads it
        self.buf = bytearray()             # the compressed stream from the session's start
        self.eof = False                   # the streamer sent its last piece
        self.viewers = {}                  # Player -> offset sent to it
        self.wanted = False                # the streamer was asked to send (spec_want; spec_stop clears it)
        self.began = began                 # unix time the session's first match started
        self.t_data = time.monotonic()     # the last piece (or the stream's creation)
        self.bucket = TokenBucket(rate_kb * 1024, max(64, rate_kb * 16) * 1024)
        self.pump_at = None                # a later pump is scheduled (a spectator's output was full)
        self.ended = None


class SpectateMixin:
    """Methods of LobbyServer (lobby.py): self.streams, self.cfg, self.players ..."""

    # ------------------------------------------------------------------ who may watch
    def _spec_tournament_may_watch(self, viewer, m):
        """Hook for the tournaments branch: may `viewer` watch tournament match `m` (players of the
        tournament, its organizer, anybody for a public one)? The rest of the rules (both players allow
        it, blocks, the limit) still apply. Nothing here knows tournaments yet."""
        return False

    @staticmethod
    def _spec_allowed_by(q, m):
        return bool(q.spec_allow) and (not m.ranked or bool(q.spec_ranked))

    def _spec_streamer_for(self, m):
        """The player whose launcher sends the stream: P1's if online with the cap, else P2's."""
        for q in m.players:
            if self._can(q, "spectate"):
                return q
        return None

    def _spec_watchable(self, m):
        """Can anybody watch match m at all now (both players allow it, a streamer, room left)?"""
        if m is None or m.state != "playing" or not all(self._spec_allowed_by(q, m) for q in m.players):
            return False
        if self._spec_streamer_for(m) is None:
            return False
        st = self.streams.get(m.stream_id)
        return st is None or (st.ended is None and len(st.viewers) < self.cfg.max_spectators)

    def _spec_refusal(self, viewer, m):
        """None if `viewer` may watch m now, else a LobbyError to raise."""
        if not self._can(viewer, "spectate"):
            return LobbyError(proto.E_NOT_ALLOWED, "this launcher cannot watch matches; update it")
        if m is None or m.state != "playing":
            return LobbyError(proto.E_STATE, "that match is not being played right now")
        if viewer in m.players:
            return LobbyError(proto.E_STATE, "you are playing in that match")
        if viewer.match is not None and viewer.match.state not in ("done", "cancelled"):
            return LobbyError(proto.E_BUSY, "you are in a match yourself")
        if viewer.build_id != m.build_id:      # (another build plays the stream differently)
            return LobbyError(proto.E_VERSION, "that player runs a different build of the game")
        may = (m.room is not None
               or (viewer.account_id is not None and any(q.account_id in viewer.friends for q in m.players))
               or self._spec_tournament_may_watch(viewer, m))
        if not may:
            return LobbyError(proto.E_NOT_ALLOWED, "only friends of a player can watch this match")
        if any(self._is_blocked(viewer, q) for q in m.players) or \
                not all(self._spec_allowed_by(q, m) for q in m.players):
            return LobbyError(proto.E_NOT_ALLOWED, "the players do not allow spectators")
        if self._spec_streamer_for(m) is None:
            return LobbyError(proto.E_STATE, "neither player can send the match right now")
        st = self.streams.get(m.stream_id)
        if st is not None and st.ended is not None:
            return LobbyError(proto.E_STATE, "this match cannot be watched any more")
        if st is not None and viewer not in st.viewers and len(st.viewers) >= self.cfg.max_spectators:
            return LobbyError(proto.E_FULL, f"this match has {self.cfg.max_spectators} spectators already")
        if st is None and len(self.streams) >= self.cfg.max_streams:
            return LobbyError(proto.E_FULL, "the server cannot show more matches right now")
        return None

    def _spec_watch_flag(self, viewer, q):
        """The friends list's "watch" for friend q as `viewer` sees it."""
        m = q.match if q is not None else None
        return bool(m is not None and self._can(viewer, "spectate") and self._spec_refusal(viewer, m) is None)

    def _spec_refresh_rooms(self):
        """Room.public's "watch": a room's match anybody may watch (before each lobby list)."""
        for r in self.rooms.values():
            r.watch = self._spec_watchable(r.match)

    # ------------------------------------------------------------------ requests
    async def h_spec_prefs(self, conn, msg):
        p = conn.player
        if "spectate" not in conn.caps:
            raise LobbyError(proto.E_BAD_REQUEST, "bad request")
        allow, ranked = bool(msg.get("allow")), bool(msg.get("ranked"))
        changed = (allow, ranked) != (p.spec_allow, p.spec_ranked)
        p.spec_allow, p.spec_ranked = allow, ranked
        if changed:
            m = p.match
            st = self.streams.get(m.stream_id) if m is not None else None
            if st is not None and not self._spec_allowed_by(p, m):
                self._spec_end(st, "not_allowed", flush=False)     # privacy: at once, not after the buffer
            self.dirty = True
        return None

    def _spec_target(self, viewer, msg):
        if msg.get("room") is not None:
            r = self.rooms.get(str(msg["room"]))
            if r is None:
                raise LobbyError(proto.E_NOT_FOUND, "no such room")
            return r.match
        name = str(msg.get("name") or "")
        q = self.by_name.get(name.lower())
        if q is None or not q.online:
            raise LobbyError(proto.E_NOT_FOUND, "no such player")
        return q.match

    async def h_watch(self, conn, msg):
        p = conn.player
        m = self._spec_target(p, msg)
        why = self._spec_refusal(p, m)
        if why is not None:
            raise why
        if p.watching is not None:
            self._spec_unwatch(p, "switched")
        st = self.streams.get(m.stream_id)
        if st is None:
            first = self.matches.get(m.stream_id) or self.recent.get(m.stream_id) or m
            st = self.streams[m.stream_id] = Stream(m.stream_id, m, self._spec_streamer_for(m),
                                                    self.cfg.spectate_rate_kb, first.started or time.time())
            self._count("spectate_streams")
            log.info("stream %s (match %s): %s's launcher sends it", st.id, m.id, st.streamer.name)
        st.viewers[p] = 0
        p.watching = st
        self._count("spectate_viewers")
        self.note("watch", stream=st.id, viewer=p.id)
        log.info("%s watches stream %s (%d spectator(s))", p.name, st.id, len(st.viewers))
        if not st.wanted and not st.eof:
            self._spec_want(st)
        self._spec_count(st)
        asyncio.get_running_loop().call_soon(self._spec_pump, st)
        return {"t": "watching", "stream": st.id, "match": m.id, "players": [q.brief() for q in m.players],
                "ranked": m.ranked, "room": m.room.name if m.room is not None else None, "began": st.began,
                "spectators": len(st.viewers)}

    async def h_unwatch(self, conn, msg):
        if conn.player.watching is not None:
            self._spec_unwatch(conn.player, "left")
        return None

    async def h_spec_data(self, conn, msg):
        p = conn.player
        st = self.streams.get(str(msg.get("stream")))
        if st is None or st.streamer is not p or st.ended is not None:
            return None                    # (a piece for a stream that ended meanwhile: dropped)
        # (no error answers: the streamer's launcher sends these on its own; a broken stream just ends)
        off = int(msg.get("off", -1))
        try:
            data = base64.b64decode(str(msg.get("data", "")), validate=True)
        except ValueError:
            data = None
        if data is None or off != len(st.buf) or len(data) > MAX_UPLOAD_PIECE:
            self._count("spectate_bad_pieces")
            log.info("stream %s: a piece out of order or too big (%s at %s, have %d)", st.id,
                     None if data is None else len(data), off, len(st.buf))
            self._spec_end(st, "stopped", flush=True)
            return None
        if not st.bucket.take(len(data)):
            self._count("spectate_rate_ends")
            self._spec_end(st, "stopped", flush=True)
            return None
        if len(st.buf) + len(data) > self.cfg.spectate_buffer_kb * 1024:
            self._spec_end(st, "too_long", flush=True)
            return None
        st.buf += data
        st.t_data = time.monotonic()
        if msg.get("eof"):
            st.eof = True
        self._spec_pump(st)
        return None

    async def h_spec_fail(self, conn, msg):
        st = self.streams.get(str(msg.get("stream")))
        if st is not None and st.streamer is conn.player:
            log.info("stream %s: the streamer cannot send it (%s)", st.id, proto.clean_text(msg.get("why", ""), 80))
            self._spec_end(st, "unavailable", flush=True)
        return None

    # ------------------------------------------------------------------ the stream's life
    def _spec_want(self, st):
        st.wanted = True
        st.streamer.send({"t": "spec_want", "stream": st.id, "match": st.match.id, "from": len(st.buf)})

    def _spec_count(self, st):
        n = len(st.viewers)
        for q in st.match.players:
            if self._can(q, "spectate"):
                q.send({"t": "spectators", "match": st.match.id, "count": n})

    def _spec_pump(self, st):
        """Send each spectator what it has not got yet, as far as its connection keeps up."""
        st.pump_at = None
        if st.id not in self.streams:
            return
        behind = False
        for v, off in list(st.viewers.items()):
            c = v.conn
            if c is None or c.closed:
                continue
            while off < len(st.buf) and c.pending < PENDING_LIMIT:
                piece = bytes(st.buf[off:off + SEND_PIECE])
                c.send({"t": "spec_data", "stream": st.id, "off": off, "data": base64.b64encode(piece).decode("ascii")})
                off += len(piece)
                self.counters["spectate_bytes"] = self.counters.get("spectate_bytes", 0) + len(piece)
            st.viewers[v] = off
            if off < len(st.buf):
                behind = True
            elif st.eof or st.ended is not None:
                # everything there is: this spectator is done
                v.send({"t": "spec_end", "stream": st.id, "reason": st.ended or "over"})
                del st.viewers[v]
                if v.watching is st:
                    v.watching = None
        if behind and st.pump_at is None:
            st.pump_at = asyncio.get_running_loop().call_later(0.25, self._spec_pump, st)
        if not st.viewers and (st.eof or st.ended is not None):
            self._spec_drop(st)

    def _spec_end(self, st, reason, flush):
        """No more data for this stream. flush: the spectators still get what the server has; else they stop now."""
        if st.ended is None:
            st.ended = reason
            log.info("stream %s ends: %s (%d bytes, %d spectator(s))", st.id, reason, len(st.buf), len(st.viewers))
        if st.wanted and not st.eof:
            st.streamer.send({"t": "spec_stop", "stream": st.id})
            st.wanted = False
        if not flush:
            for v in list(st.viewers):
                v.send({"t": "spec_end", "stream": st.id, "reason": reason})
                if v.watching is st:
                    v.watching = None
            st.viewers.clear()
        self._spec_pump(st)
        self._spec_count(st)

    def _spec_drop(self, st):
        if st.pump_at is not None:
            st.pump_at.cancel()
            st.pump_at = None
        if self.streams.get(st.id) is st:
            del self.streams[st.id]
        if st.ended is None:
            st.ended = "over"

    def _spec_unwatch(self, p, why):
        st = p.watching
        p.watching = None
        if st is None:
            return
        st.viewers.pop(p, None)
        log.info("%s stops watching stream %s (%s)", p.name, st.id, why)
        if why not in ("left", "switched"):
            p.send({"t": "spec_end", "stream": st.id, "reason": why})
        if not st.viewers:
            if st.eof or st.ended is not None:
                self._spec_drop(st)
            elif st.wanted:
                st.streamer.send({"t": "spec_stop", "stream": st.id})   # nobody watches: the upload pauses
                st.wanted = False
        self._spec_count(st)

    # ------------------------------------------------------------------ hooks from lobby.py
    def _spec_match_started(self, m):
        """A match starts playing: a rematch in the running games carries its session's stream on."""
        st = self.streams.get(m.stream_id)
        if st is not None and st.ended is None:
            st.match = m
            if not self._spec_allowed_by(m.players[0], m) or not self._spec_allowed_by(m.players[1], m):
                self._spec_end(st, "not_allowed", flush=False)
            else:
                self._spec_count(st)

    def _spec_player_gone(self, p):
        """p's connection is gone (or p logged out): it watches nothing any more. A streamer that
        comes back is asked again (_spec_player_back); one that does not, ends in _spec_tick."""
        if p.watching is not None:
            self._spec_unwatch(p, "left")

    def _spec_player_back(self, p):
        for st in self.streams.values():
            if st.streamer is p and st.ended is None and not st.eof and st.viewers:
                self._spec_want(st)

    def _spec_new_match(self, p):
        """p got a match of its own: it stops watching (its launcher closes the spectator's game)."""
        if p.watching is not None:
            self._spec_unwatch(p, "your_match")

    def _spec_tick(self):
        """Housekeeping: streams whose data stopped coming."""
        now = time.monotonic()
        for st in list(self.streams.values()):
            idle = now - st.t_data
            m = st.match
            set_over = m.state != "playing" and (m.set is None or m.set.state != "active")
            if st.ended is None and not st.eof and idle > 10 and set_over:
                # the set is over (no rematch in these games any more): the session's stream is complete; a
                # persistent game keeps its netplay session open until the next one, so no END would come
                self._spec_end(st, "over", flush=True)
            elif st.ended is None and not st.eof and idle > self.cfg.spectate_idle:
                m = st.match
                gone = m.state != "playing" or st.streamer.conn is None
                if gone or idle > 4 * self.cfg.spectate_idle:
                    self._spec_end(st, "stopped", flush=True)
            elif (st.eof or st.ended is not None) and not st.viewers:
                self._spec_drop(st)
            elif st.viewers:
                self._spec_pump(st)

    def spectate_status(self):
        return {"streams": len(self.streams), "spectators": sum(len(s.viewers) for s in self.streams.values()),
                "buffered_kb": round(sum(len(s.buf) for s in self.streams.values()) / 1024.0, 1)}
