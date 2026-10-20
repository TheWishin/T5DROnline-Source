"""The lobby server: control connections, players, rooms, queues, challenges and matches.

Single-threaded asyncio; all state lives on the event loop thread.

Match life cycle (states):
    ready      both players must accept (skipped for an accepted challenge or a rematch)
    nat        each client binds its game socket and registers it with the server over UDP
    punch      clients punch holes toward each other's candidate endpoints and measure RTT
               (clients with the "nat2" cap get a plan: a common start, a window, predicted ports)
    relay      punching failed (or both NATs are symmetric and unpredictable): both bind to the relay
    playing    match_start sent: the game runs; waiting for result reports
    done       results reconciled (or cancelled / void)

A rematch whose two games are still connected skips ready/nat/punch/relay and starts in
`playing` with the previous match's path. Ranked rules, result reconciliation and the
integrity rules (disconnects, disputes, desyncs, minimum length): docs/RANKED.md.

Around the matches (docs/RANKED.md, "Tekken 6 style options"):
    ready check   a queue match is "blind": both players see only the ping and accept or decline
                  within T5L_READY_TIMEOUT (15 s); names and sides come after both accepted
    set           the chain of games two players play in a row (the first match and its
                  rematches); a ranked set locks both characters for its games
    blocks        per account (guests: per session); a blocked pair is never matched again
    strict        ranked queue option: only opponents within +-T5L_STRICT_RANGE rating points
    cooldown      two players who just finished a ranked game are queue-matched again after 30 s
    lag check     after a match both games report how long they waited for each other; both
                  players get "ping X should mean Y frames behind, it was Z"
    notices       a message from the admin tool reaches every connected client

Friends (docs/ONLINE.md "Friends and invites", accounts only, clients with the "friends" cap): a request the other side
accepts, a list with who is online / in a match / offline (pushed as it changes), invites to a casual match or
to the inviter's room that one click accepts. A block ends a friendship.
"""
import asyncio
import ipaddress
import logging
import math
import os
import ssl
import sys
import time

from .. import __version__, fighters, lag as lagmod, proto, ranks, rating as glicko
from ..buildid import BuildInfo
from ..proto import LobbyError
from .config import Config
from .ratelimit import BanList, KeyedBuckets, TokenBucket
from .relays import MAIN as RELAY_MAIN, MAX_RELAYS, RelayPool
from .store import COUNTED, SET_COUNTED, Store, check_password, hash_password
from .udp import UdpService

log = logging.getLogger("t5lobby")

SERVER_NAME = "t5lobby/0.2"
# optional protocol features a client may announce in hello
CAPS = frozenset(("delta", "blind_ready", "notices", "sets", "ingame_pick", "nat2", "relays", "friends", "old_stages"))
QUEUE_MODES = ("quick", "ranked")
# What this server supports beyond protocol 1's base (the client checks before using them).
FEATURES = ["ranks", "sessions", "recovery", "passwd", "profile", "history", "chars", "integrity", "rematch",
            "blind_ready", "blocks", "strict", "set_lock", "lag_check", "notices", "ranked_sets", "ingame_pick",
            "nat2", "relays", "friends"]
REPORT_SOURCES = ("game", "manual", "quit", "crash", "disconnect")
DAY = 86400.0


def _checkpoint(path):
    """Fold the WAL file back into the database and truncate it (a worker thread: it waits for readers)."""
    import sqlite3
    try:
        c = sqlite3.connect(path, timeout=30)
        try:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            c.close()
    except sqlite3.Error as e:
        log.warning("WAL checkpoint: %s", e)


def _rid():
    return os.urandom(6).hex()


class Player:
    def __init__(self, conn, name, guest, account=None):
        self.id = "p" + _rid()
        self.conn = conn
        self.name = name
        self.guest = guest
        self.account_id = account["id"] if account else None
        self.build_id = conn.build_id
        self.release = conn.release
        self.ip = conn.ip
        self.status = "idle"            # idle | room | queue | match | playing
        self.room = None
        self.queue_mode = None
        self.queue_since = 0.0
        self.match = None
        self.server_rtt = None          # ms, reported by the client (UDP ping)
        self.relay_rtt = {}             # regional relay id -> ms, reported by a client with the "relays" cap
        self.fps = None                 # this PC's sustained game speed in its last match (client report)
        self.rtt_shown = None           # what the lobby list shows: only updated on a real change
        self.token = os.urandom(24).hex()   # session resume token
        self.dropped_at = None
        self.last_challenge = 0.0
        self.char = fighters.RANDOM     # character picked in the launcher (a fighters key)
        self.main = None                # most played character (accounts, from the history)
        self.rank = ranks.RankState()   # tier state (accounts: from the database)
        self.rules = ranks.RankRules()
        self.session = None             # "remember me" token this connection logged in with
        self.blocks = {}                # block key -> {name, guest, since}: players this one never meets again
        self.strict = False             # ranked queue: only opponents within T5L_STRICT_RANGE rating points
        self.set = None                 # the GameSet this player is in (games in a row with one opponent)
        self.friends = set()            # account ids of this account's friends (guests have none)
        self.last_invite = 0.0
        if account:
            self.rating = glicko.Rating(account["rating"], account["rd"], account["vol"])
            self.record = [account["wins"], account["losses"], account["draws"]]
        else:
            self.rating = glicko.Rating()
            self.record = [0, 0, 0]

    def rank_info(self):
        if self.guest:
            return {"tier": None, "rank": "Guest", "provisional": True, "placement": None}
        return ranks.describe(self.rank, self.rating.rd, self.rules)

    def public(self):
        d = {"id": self.id, "name": self.name, "guest": self.guest, "status": self.status,
             "rating": round(self.rating.r), "rd": round(self.rating.rd),
             "record": self.record, "room": self.room.id if self.room else None,
             "rtt": None if self.rtt_shown is None else round(self.rtt_shown, 1),
             "build": self.build_id, "release": self.release, "char": self.char, "main": self.main}
        d.update(self.rank_info())
        return d

    def brief(self):
        d = {"id": self.id, "name": self.name, "guest": self.guest,
             "rating": round(self.rating.r), "rd": round(self.rating.rd), "main": self.main, "fps": self.fps}
        d.update(self.rank_info())
        return d

    @property
    def online(self):
        return self.conn is not None

    def send(self, msg):
        if self.conn is not None:
            self.conn.send(msg)


class Room:
    def __init__(self, owner, name, ranked):
        self.id = "r" + _rid()
        self.name = name
        self.owner = owner
        self.members = [owner]
        self.ranked = ranked
        self.match = None
        self.set = None                 # the room's running set (rematches in the room keep it)
        self.build_id = owner.build_id

    def public(self):
        return {"id": self.id, "name": self.name, "owner": self.owner.brief(),
                "members": [p.id for p in self.members], "ranked": self.ranked,
                "build": self.build_id,
                "status": "playing" if self.match else ("full" if len(self.members) >= 2 else "open")}


class _ConnOf:
    """Stand-in connection for calling a handler on behalf of a player."""

    def __init__(self, player):
        self.player = player


class Challenge:
    def __init__(self, src, dst):
        self.id = "c" + _rid()
        self.src, self.dst = src, dst
        self.timer = None


class Invite:
    """A friend asked to play: a casual match ("casual") or the inviter's room ("room")."""

    def __init__(self, src, dst, kind, room=None):
        self.id = "i" + _rid()
        self.src, self.dst = src, dst
        self.kind = kind
        self.room = room
        self.timer = None


class GameSet:
    """The games two players play in a row: the first match (from the queue, a room or a
    challenge) and every rematch of it. A ranked set locks both players' characters: whatever they
    had picked when the set began is what they play in every game of it. The set ends when a player
    leaves it (declines the rematch, queues again, blocks, leaves the lobby), the rematch window runs
    out, or a game is cancelled.

    A **rated set** (`wins_needed` > 1: a ranked set between two clients that announced "sets",
    T5L_RANKED_SET_WINS, docs/RANKED.md "Ranked sets") is best of 2 * wins_needed - 1: its games are
    not rated one by one; the next game starts by itself after a countdown, and the rating changes once,
    when a player has won `wins_needed` games (or left the set). Otherwise (casual, or the old per-game
    rating) no game's rating changes when a set ends: each game was rated when it ended."""

    def __init__(self, a, b, ranked, wins_needed=0):
        self.id = "s" + _rid()
        self.players = [a, b]           # P1 and P2 of every game of a rated set (sides stay)
        self.locked = bool(ranked)
        self.ranked = bool(ranked)
        self.picks = {}                 # player id -> the character picked for the whole (locked) set
        self.costumes = {}              # player id -> its confirm button (1-4) when picked in the game (in-game select)
        self.matches = []
        self.games = 0                  # games started
        self.current = None             # the match being set up or played
        self.last = None                # the last finished match
        self.state = "active"
        self.created = time.time()
        # rated set
        self.wins_needed = wins_needed if ranked and wins_needed > 1 else 0
        self.wins = {a.id: 0, b.id: 0}  # games won, by player id
        self.number = 1                 # the set's game being played or next (a replay keeps the number)
        self.replays = 0                # games played again (no winner: desync, draw, too short)
        self.log = []                   # [{match, number, status, winner (0/1 = P1/P2 of the set), score, reason}]
        self.next_timer = None          # countdown to the next game
        self.next_due = 0.0             # (monotonic) when it ends
        self.next_keep = {}             # player id -> True: that player's game still runs, connected (set_next)
        self.fresh = False              # the next game needs a new connection (after a desync)
        self.grace = {}                 # player id -> timer: lost the lobby between two games
        self.outcome = None             # at the end: {status, winner, reason, blame (Players or None), changes}

    @property
    def rated(self):
        return self.wins_needed > 1

    def side(self, p):
        return 0 if self.players[0] is p else 1 if self.players[1] is p else None

    def other(self, p):
        return self.players[1 - self.side(p)]

    def score(self):
        """[games won by P1, by P2] (P1 / P2 of the set)."""
        return [self.wins[self.players[0].id], self.wins[self.players[1].id]]

    def info(self):
        d = {"id": self.id, "game": self.games, "locked": self.locked and self.state == "active",
             "ranked": self.ranked}
        if self.rated:
            # wins by side (P1, P2: the same in every game of the set); number: "game 2 of 3"
            d.update({"rated": True, "wins_needed": self.wins_needed, "best_of": 2 * self.wins_needed - 1,
                      "wins": self.score(), "number": self.number, "replays": self.replays,
                      "state": "active" if self.outcome is None else "ended"})
            if self.next_timer is not None:
                d["next"] = {"in": round(max(0.0, self.next_due - time.monotonic()), 1), "number": self.number,
                             "replay": bool(self.log) and self.log[-1]["winner"] is None}
            if self.outcome is not None:
                o = self.outcome
                d["result"] = {"status": o["status"], "reason": o["reason"],
                               "winner": None if o["winner"] is None else self.side(o["winner"]),
                               "blame": None if o["blame"] is None else self.side(o["blame"])}
        return d

    def view(self, p):
        """The set from `p`'s side, for set_end: {result win|loss|None, wins [you, opp], rating (p's change)}."""
        sd = self.side(p)
        sc = self.score()
        o = self.outcome or {}
        w = o.get("winner")
        return {"rated": True, "status": o.get("status"), "outcome_reason": o.get("reason"),
                "result": None if w is None else ("win" if w is p else "loss"),
                "wins": [sc[sd], sc[1 - sd]], "games": len(self.log), "best_of": 2 * self.wins_needed - 1,
                "blame": None if o.get("blame") is None else ("you" if o["blame"] is p else "opponent"),
                "rating": (o.get("changes") or {}).get(p.id)}


class Match:
    def __init__(self, host, join, ranked, origin, room=None):
        self.id = "m" + _rid()
        self.players = [host, join]          # slot 0 = host = P1, slot 1 = join = P2
        self.ranked = ranked
        self.origin = origin                 # queue | room | challenge
        self.room = room
        self.build_id = host.build_id
        self.state = "ready"
        self.created = time.time()
        self.ready = [False, False]
        self.tokens = [proto.new_token(), proto.new_token()]
        self.tag = os.urandom(proto.TAG_LEN)
        self.key = os.urandom(16).hex()      # T5_NET_KEY: authenticates the two games' packets (TCP only)
        self.public_ep = [None, None]        # game socket as the server's main UDP port sees it
        self.probe_ep = [None, None]         # ... and as the second port sees it
        self.nat_info = [None, None]         # client's nat_local message
        self.results = [None, None]          # nat_result (punch or relay phase)
        self.punch_retry = False             # the one second chance of a side that failed while the other made it
        self.nat_plan = None                 # what the punch phase was told (log, tests)
        self.upgraded = None                 # a relayed match that moved onto the direct path: its round trip
        self.relay = None
        self.path = None
        self.rtt = None
        self.jitter = None
        self.delay = None
        self.reports = [None, None]
        self.queue_since = [0.0, 0.0]
        self.queue_mode = None
        self.timers = {}
        self.final = None
        self.relay_stats = None
        self.relay_id = None                 # key of the relay session (a continued rematch keeps the old one)
        self.relay_node = None               # regional relay (relays.RelayNodeRef) the session is on; None = ours
        self.relay_info = None               # ... what the players were told about it (id, name, host, port)
        self.relay_choice = None             # the relays considered, best first: [(sum of both RTTs in ms, id)]
        self.relay_asking = False            # a failed regional relay setup: asking the node what it saw
        self.picks = [host.char, join.char]  # characters as picked (may be "random")
        self.chars = None                    # resolved at match start (the games' own picks replace them, below)
        self.pick = 0                        # seconds to pick on the game's select screen (0: the launchers' characters)
        self.stage = None
        self.started = None                  # time.time() of match_start
        self.rematch_of = None
        self.continued = False               # rematch inside the running games (no new connection)
        self.set = None                      # GameSet
        self.blind = [False, False]          # side -> got the blind ready check (no name, no side yet)
        self.lag = [None, None]              # side -> the game's lag report (docs/RANKED.md, lag check)
        self.lag_sent = False
        self.lag_verdict = None              # the lag check's verdict (a ranked set may be left for free after "more_lag")
        self.set_number = None               # its number in a rated set (1, 2, 3; a replay keeps it)
        self.lost_lobby = [False, False]     # side -> its lobby connection dropped while the match ran

    def side(self, player):
        return 0 if self.players[0] is player else 1 if self.players[1] is player else None

    def other(self, player):
        return self.players[1 - self.side(player)]


# =============================================================================== connection

class Conn:
    def __init__(self, srv, reader, writer):
        self.srv = srv
        self.reader, self.writer = reader, writer
        peer = writer.get_extra_info("peername") or ("?", 0)
        self.ip, self.port = peer[0], peer[1]
        self.akey = proto.address_key(self.ip, srv.cfg.ipv6_prefix)    # what the per-address limits count by
        self.out = asyncio.Queue(maxsize=512)
        self.pending = 0                # bytes queued but not yet handed to the socket
        self.player = None
        self.build_id = None
        self.release = ""
        self.caps = frozenset()         # optional protocol features the client announced
        self.need_full = True           # next lobby update: the whole list, not a delta
        self.helloed = False
        self.closed = False
        self.t_open = time.monotonic()
        self.bucket = TokenBucket(rate=20, burst=40)
        self.violations = TokenBucket(rate=0.2, burst=10)   # 10 strikes, one forgiven every 5 s
        # Requests that cost the server more than they cost the client: database queries over all
        # accounts (leaderboard, profiles, history, the whole lobby list), and changes that every other
        # player receives in the next lobby update (queue, rooms, character, ping).
        self.heavy = TokenBucket(srv.cfg.heavy_rate, srv.cfg.heavy_burst)
        self.state = TokenBucket(srv.cfg.state_rate, srv.cfg.state_burst)
        self.errors = 0

    def send(self, msg):
        if not self.closed:
            if msg.get("t") in ("error", "notice") and isinstance(msg.get("msg"), str):
                msg = dict(msg, msg=proto.scrub_addresses(msg["msg"]))     # never an IP address in a message
            self.send_raw(proto.encode(msg))

    def send_raw(self, data):
        """Queue encoded bytes. A client that stops reading is dropped before it costs much memory."""
        if self.closed:
            return
        if self.pending + len(data) > self.srv.cfg.max_pending_kb * 1024:
            self.drop(f"{self.pending} bytes unread")
            return
        try:
            self.out.put_nowait(data)
            self.pending += len(data)
        except asyncio.QueueFull:
            self.drop("output queue full")

    def drop(self, why):
        """A client that stopped reading: close at once, without its unread output. A graceful close
        waits until the peer has read everything -- for ever, if it never reads: the connection, its
        buffers and its slot (T5L_MAX_PER_IP, T5L_MAX_CLIENTS) used to stay taken until the peer went."""
        if self.closed and self.writer.transport.is_closing():
            return
        log.warning("%s: %s, dropping connection", self.ip, why)
        self.srv._count("dropped_slow_readers")
        self.closed = True
        try:
            self.out.put_nowait(None)
        except asyncio.QueueFull:
            pass
        try:
            self.writer.transport.abort()
        except Exception:      # noqa: BLE001 -- gone already
            pass

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.out.put_nowait(None)
            except asyncio.QueueFull:
                self.writer.close()

    async def writer_loop(self):
        try:
            while True:
                data = await self.out.get()
                if data is None:
                    break
                self.pending -= len(data)
                self.srv.counters["tcp_out_bytes"] += len(data)
                self.writer.write(data)
                await self.writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            self.closed = True
            try:
                self.writer.close()
            except Exception:
                pass

    async def run(self):
        wtask = asyncio.ensure_future(self.writer_loop())
        try:
            while not self.closed:
                if self.player is None:
                    timeout = self.srv.cfg.login_timeout - (time.monotonic() - self.t_open)
                    if timeout <= 0:
                        self.send({"t": "error", "code": proto.E_BAD_REQUEST, "msg": "login timeout"})
                        break
                else:
                    timeout = self.srv.cfg.idle_timeout
                try:
                    line = await asyncio.wait_for(self.reader.readuntil(b"\n"), timeout)
                except asyncio.TimeoutError:
                    self.send({"t": "error", "code": proto.E_BAD_REQUEST,
                               "msg": "login timeout" if self.player is None else "idle timeout"})
                    break
                except asyncio.LimitOverrunError:
                    self.send({"t": "error", "code": proto.E_BAD_REQUEST, "msg": "line too long"})
                    break
                except (asyncio.IncompleteReadError, ConnectionError, OSError):
                    break
                self.srv.counters["tcp_in_bytes"] += len(line)
                if not await self.srv.dispatch(self, line):
                    break
        finally:
            self.close()
            # The last messages (an error, "bye") get a few seconds to leave; a peer that reads nothing
            # does not hold the connection beyond that.
            done, _ = await asyncio.wait({wtask}, timeout=10.0)
            if not done:
                self.drop("unread output at close")
                wtask.cancel()
                await asyncio.gather(wtask, return_exceptions=True)
            self.srv.conn_closed(self)


# =============================================================================== server

class LobbyServer:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config.from_env()
        self.store = Store(self.cfg.db)
        self.udp = UdpService(self, self.cfg)
        self.relays = RelayPool(self.cfg, on_change=self._relays_changed)   # regional relay nodes (T5L_RELAYS)
        self._bg = set()           # background tasks that must not be garbage collected
        self.conns = set()
        self.players = {}          # id -> Player (online or resumable)
        self.by_name = {}          # lower name -> Player
        self.by_account = {}       # account id -> Player (online or resumable)
        self.invites = {}          # invite id -> Invite (friends)
        self.retry_after = {}      # (kind, asker, asked) -> monotonic time a new invite / challenge may go again
        self.friend_req_addr = KeyedBuckets(rate=max(1, self.cfg.friend_requests_address) / DAY,
                                            burst=max(1, self.cfg.friend_requests_address))   # per internet address
        self._presence = {}        # account id -> (status, activity, name, build, cap): what the friends were last told
        self.sessions = {}         # resume token -> Player
        self.rooms = {}
        self.challenges = {}
        self.matches = {}
        self.tokens = {}           # udp token -> (Match, side)
        self.queues = {m: [] for m in QUEUE_MODES}
        self.ip_conns = {}
        self.ip_connects = KeyedBuckets(rate=self.cfg.conn_rate, burst=self.cfg.conn_burst)  # new connections per IP
        self.login_fail = KeyedBuckets(rate=1 / 60.0, burst=5)  # failed password logins per IP and per name
        self.registrations = KeyedBuckets(rate=1 / 600.0, burst=3)  # new accounts per IP
        # password changes and new recovery codes per account, right or wrong: each costs one or two scrypt
        # runs, and a logged-in account with its own password could otherwise keep the hashing busy for everyone
        self.pw_ops = KeyedBuckets(rate=1 / 20.0, burst=3)
        self.chat_rate = KeyedBuckets(rate=1.0, burst=5)          # chat lines per player
        self.bans = BanList()
        self.dirty = True
        self.tcp = None
        self.tasks = []
        self.started = time.time()
        self.events = []           # (time, kind, data) -- recent events for tests / diagnostics
        self.recent = {}           # match id -> finished Match, kept rematch_window seconds for a rematch
        self.pair_last = {}        # frozenset of two player keys -> monotonic time their last ranked game ended
        self.notices_by_id = {}    # active server notices (admin tool): id -> row
        self.table = fighters.table()
        self.rules = ranks.RankRules(placement=self.cfg.placement, placement_cap=self.cfg.placement_cap,
                                     hysteresis=self.cfg.hysteresis, shield=self.cfg.shield,
                                     provisional_rd=self.cfg.provisional_rd)
        self.counters = dict.fromkeys((
            "tcp_in_bytes", "tcp_out_bytes", "connections", "refused_connections", "logins_guest",
            "logins_account", "accounts_created", "login_failures", "kicked", "matches_found",
            "matches_cancelled", "matches_direct", "matches_lan", "matches_relay", "results_confirmed",
            "results_disputed", "results_onesided", "results_void", "chat_lines", "blocks_made", "lag_checks",
            "lag_more", "lag_leaves", "notices_sent", "sets_confirmed", "sets_forfeit", "sets_void",
            "set_replays", "punch_retries", "punch_predicted", "relay_upgrades", "relay_regional",
            "relay_fallbacks", "friend_requests", "friendships_made", "friendships_ended", "invites_sent",
            "invites_accepted"), 0)
        self._last_lobby = None    # the last lobby list sent: deltas are computed against it
        self.ip_bans = []          # [(ip_network, until)] from the database (the admin tool writes them)
        self.name_block = self._load_blocklist(self.cfg.name_blocklist)
        self.sslctx = None
        self._tls_mtime = None
        self.status_http = None
        self._last_backup = 0.0
        self._last_status_log = time.monotonic()
        self._relay_samples = []   # (monotonic, bytes relayed so far) for the relay bandwidth
        self.by_skel = {}          # proto.name_skeleton -> Player online: no look-alike names at the same time
        self.chat_total = TokenBucket(self.cfg.chat_total_rate, self.cfg.chat_total_rate * 2)
        self.pw_sem = asyncio.Semaphore(max(1, self.cfg.pw_concurrency))   # scrypt: CPU and 16 MB each
        self.pw_waiting = 0
        self.good_logins = {}      # lower name -> {address key: time}: where the account logged in fine
        self.handshakes = 0        # TLS handshakes in progress
        self.draining = False      # `admin drain`: no new matches, the running ones finish, then restart
        self._last_db_upkeep = time.monotonic()

    # ------------------------------------------------------------------ lifecycle
    async def start(self):
        loop = asyncio.get_running_loop()
        sslctx = None
        if self.cfg.tls_cert:
            sslctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            sslctx.minimum_version = ssl.TLSVersion.TLSv1_2
            sslctx.load_cert_chain(self.cfg.tls_cert, self.cfg.tls_key or None)
            self._tls_mtime = self._tls_files_mtime()
        elif self.cfg.accounts and self.cfg.host not in ("127.0.0.1", "localhost", "::1"):
            log.warning("no TLS certificate (T5L_TLS_CERT): account passwords cross the network readable; "
                        "see docs/HOSTING.md")
        self.sslctx = sslctx
        n = self.store.void_interrupted()
        if n:
            log.warning("%d match(es) were running when the server stopped: void (no rating change, no blame)", n)
        n = self.store.void_open_sets("server_restart")
        if n:
            # A running ranked set lives in this process only: one the last server left open is void (its games
            # changed no rating, so nothing is undone). docs/RANKED.md "Ranked sets", server restart.
            log.info("%d ranked set(s) left open by the last server run: void (server_restart)", n)
        self.store.set_flag("drain", None)              # a restart ends a drain (admin.py drain)
        self.store.defer_commits(loop.call_soon)
        self.reload_bans()
        self.notices_by_id = {n["id"]: n for n in self.store.active_notices()}
        # TLS: on Python 3.11+ the handshake starts only after the address checks in _accept (bans, rate,
        # per-address and pre-login caps), with its own timeout. Before, every connection got a 60 s
        # handshake that no limit counted: a slowloris could hold any number of sockets that way.
        self._late_tls = sslctx is not None and sys.version_info >= (3, 11)
        self.tcp = await asyncio.start_server(
            self._accept, self.cfg.host, self.cfg.port, limit=proto.MAX_LINE + 2,
            **({} if sslctx is None or self._late_tls
               else {"ssl": sslctx, "ssl_handshake_timeout": self.cfg.tls_handshake_timeout}))
        self.port = self.tcp.sockets[0].getsockname()[1]
        await self.udp.start(loop)
        await self.relays.start()
        if self.cfg.status_port:
            from .status import StatusHttp
            self.status_http = StatusHttp(self)
            try:
                await self.status_http.start(self.cfg.status_host, max(0, self.cfg.status_port))
            except OSError as e:
                log.warning("status endpoint %s:%s unavailable (%s)", self.cfg.status_host, self.cfg.status_port, e)
                self.status_http = None
        if self.cfg.backup_dir and self.cfg.db != ":memory:":
            from .backup import newest_backup_time
            self._last_backup = newest_backup_time(self.cfg.backup_dir)
        self.tasks = [asyncio.ensure_future(self._tick_lobby()), asyncio.ensure_future(self._tick_queue()),
                      asyncio.ensure_future(self._tick_housekeeping()), asyncio.ensure_future(self._tick_admin())]
        log.info("listening: TCP %s:%d%s, UDP %d%s%s", self.cfg.host, self.port, " (TLS)" if sslctx else "",
                 self.udp.port, f" + probe {self.udp.port2}" if self.udp.port2 else "",
                 f", status http://{self.cfg.status_host}:{self.status_http.port}/" if self.status_http else "")

    async def stop(self):
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.tcp:
            self.tcp.close()
        for c in list(self.conns):
            c.close()
        if self.tcp:
            try:
                await asyncio.wait_for(self.tcp.wait_closed(), 2)
            except asyncio.TimeoutError:
                pass
        if self.status_http:
            await self.status_http.stop()
        await self.relays.stop()
        for t in list(self._bg):
            t.cancel()
        self.udp.close()
        self.store.close()

    # ------------------------------------------------------------------ operations: TLS, bans, names
    def _tls_files_mtime(self):
        try:
            return tuple(os.stat(f).st_mtime_ns for f in (self.cfg.tls_cert, self.cfg.tls_key) if f)
        except OSError:
            return None

    def reload_tls(self, force=False):
        """Load a renewed certificate (certbot, or a replaced self-signed one) for new connections.
        Called when the files change (checked every few seconds) and on SIGHUP. A broken pair is
        refused and the old certificate stays in use."""
        if self.sslctx is None:
            return False
        mt = self._tls_files_mtime()
        if mt is None or (mt == self._tls_mtime and not force):
            return False
        try:
            self.sslctx.load_cert_chain(self.cfg.tls_cert, self.cfg.tls_key or None)
        except (OSError, ssl.SSLError, ValueError) as e:
            log.error("TLS certificate reload failed, keeping the old one: %s", e)
            self._tls_mtime = mt            # do not retry every few seconds; the next change will
            return False
        self._tls_mtime = mt
        log.info("TLS certificate reloaded from %s", self.cfg.tls_cert)
        return True

    def reload_bans(self):
        """Address bans from the database (written by the admin tool)."""
        nets = []
        for row in self.store.ip_bans():
            try:
                nets.append((ipaddress.ip_network(row["net"], strict=False), row["until"]))
            except ValueError:
                continue
        self.ip_bans = nets

    def ip_banned(self, ip):
        if not self.ip_bans:
            return False
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return False
        now = time.time()
        return any(until > now and a.version == net.version and a in net for net, until in self.ip_bans)

    @staticmethod
    def _load_blocklist(path):
        """Extra words refused anywhere in new names (T5L_NAME_BLOCKLIST), on top of the reserved
        names in proto.reserved_name."""
        words = set()
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    words |= {w.strip().lower() for w in f if w.strip() and not w.startswith("#")}
            except OSError as e:
                log.warning("name blocklist %s: %s", path, e)
        return words

    def name_blocked(self, name):
        flat = proto.name_key(name)
        return any(w and proto.name_key(w) in flat for w in self.name_block)

    def _refuse_banned(self, account):
        """Bans come from the admin tool; checked after the password (or saved login) is proven,
        so a ban never tells a stranger that an account exists."""
        ban = self.store.ban_state(self.store.account_by_id(account["id"]) or account)
        if ban:
            until, reason = ban
            when = "for good" if until >= 3e10 else "until " + time.strftime("%Y-%m-%d %H:%M UTC",
                                                                             time.gmtime(until))
            raise LobbyError(proto.E_NOT_ALLOWED, f"this account is banned {when}" + (f": {reason}" if reason else ""))

    def _count(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1

    def kick(self, p, reason):
        if p.conn is not None:
            p.send({"t": "kicked", "reason": reason})
            c = p.conn
            c.player = None
            c.close()
            self.counters["kicked"] += 1
            self.player_dropped(p, final=True)

    def note(self, kind, **data):
        self.events.append((time.time(), kind, data))
        if len(self.events) > 1000:
            del self.events[:500]

    def akey(self, ip):
        return proto.address_key(ip, self.cfg.ipv6_prefix)

    def _refuse(self, writer, code, msg, tell=False):
        """Close a connection we do not take. Over TLS (late handshake) only a "server full" is worth
        a handshake to say so -- and only a few at a time; bans and rate limits just close."""
        self.counters["refused_connections"] += 1
        if not self._late_tls:
            writer.write(proto.encode({"t": "error", "code": code, "msg": msg}))
            writer.close()
            return
        if not tell or self.handshakes >= 16:
            writer.close()
            return

        async def say():
            self.handshakes += 1
            try:
                await writer.start_tls(self.sslctx, ssl_handshake_timeout=5.0)
                writer.write(proto.encode({"t": "error", "code": code, "msg": msg}))
                await asyncio.wait_for(writer.drain(), 5.0)
            except (OSError, ssl.SSLError, asyncio.TimeoutError, ConnectionError, ValueError):
                pass
            finally:
                self.handshakes -= 1
                writer.close()
        asyncio.ensure_future(say())

    async def _accept(self, reader, writer):
        conn = Conn(self, reader, writer)
        ip, key = conn.ip, conn.akey
        if self.ip_banned(ip):
            self._refuse(writer, proto.E_NOT_ALLOWED, "banned from this server")
            return
        if self.bans.banned(key) or not self.ip_connects.take(key):
            self._refuse(writer, proto.E_RATE, "too many connections")
            return
        if len(self.conns) >= self.cfg.max_clients or self.ip_conns.get(key, 0) >= self.cfg.max_per_ip:
            self._refuse(writer, proto.E_FULL, "server full", tell=True)
            return
        if self.cfg.max_prelogin > 0 and \
                sum(1 for c in self.conns if c.player is None) >= self.cfg.max_prelogin:
            # Connections that have not logged in yet (and TLS handshakes) cost memory and file
            # descriptors without being anybody: a flood of them must not crowd out real players.
            self._refuse(writer, proto.E_FULL, "server busy, try again in a moment", tell=True)
            return
        self.counters["connections"] += 1
        self.conns.add(conn)
        self.ip_conns[key] = self.ip_conns.get(key, 0) + 1
        if self._late_tls:
            self.handshakes += 1
            try:
                await writer.start_tls(self.sslctx, ssl_handshake_timeout=self.cfg.tls_handshake_timeout)
            except (OSError, ssl.SSLError, asyncio.TimeoutError, ConnectionError, ValueError):
                self.counters["tls_failed"] = self.counters.get("tls_failed", 0) + 1
                conn.closed = True
                try:
                    writer.close()
                except Exception:      # noqa: BLE001 -- the socket is gone either way
                    pass
                self.conn_closed(conn)
                return
            finally:
                self.handshakes -= 1
        await conn.run()

    def conn_closed(self, conn):
        if conn not in self.conns:
            return
        self.conns.discard(conn)
        n = self.ip_conns.get(conn.akey, 1) - 1
        if n <= 0:
            self.ip_conns.pop(conn.akey, None)
        else:
            self.ip_conns[conn.akey] = n
        p = conn.player
        if p is not None and p.conn is conn:
            self.player_dropped(p)

    # ------------------------------------------------------------------ dispatch
    PRE_LOGIN = ("hello", "login", "ping", "logout", "recover")
    HEAVY = frozenset(("leaderboard", "profile", "history", "lobby", "friends"))
    STATE = frozenset(("queue", "unqueue", "room_create", "room_join", "room_leave", "set_char", "udp_rtt", "perf",
                       "relay_rtt",
                       "challenge", "challenge_cancel", "block", "unblock", "leave_set",
                       "friend_add", "friend_answer", "friend_cancel", "friend_remove", "invite", "invite_answer",
                       "invite_cancel"))

    async def dispatch(self, conn, line):
        """Handle one line; False closes the connection."""
        if not conn.bucket.take():
            if not conn.violations.take():
                self.bans.ban(conn.akey, 60)
                conn.send({"t": "error", "code": proto.E_RATE, "msg": "flooding: disconnected"})
                return False
            conn.send({"t": "error", "code": proto.E_RATE, "msg": "slow down"})
            return True
        try:
            return await self._dispatch(conn, line)
        except Exception as e:      # noqa: BLE001 -- a request we did not foresee must not end the connection task
            conn.errors += 1
            self._count("handler_errors")
            if self.counters["handler_errors"] <= 20 or self.counters["handler_errors"] % 1000 == 0:
                log.warning("%s: request failed (%s: %s)", conn.player.name if conn.player else conn.ip,
                            type(e).__name__, str(e)[:200])
            conn.send({"t": "error", "code": proto.E_BAD_REQUEST, "msg": "bad request"})
            return conn.errors < 5

    async def _dispatch(self, conn, line):
        try:
            msg = proto.decode(line)
        except ValueError:
            conn.errors += 1
            conn.send({"t": "error", "code": proto.E_BAD_REQUEST, "msg": "malformed message"})
            return conn.errors < 5
        t = msg["t"]
        rid = msg.get("rid")
        fn = getattr(self, "h_" + t, None) if t.isidentifier() else None
        try:
            if fn is None:
                raise LobbyError(proto.E_BAD_REQUEST, f"unknown message {t!r}")
            if t not in self.PRE_LOGIN and conn.player is None:
                raise LobbyError(proto.E_STATE, "log in first")
            if (t in self.HEAVY and not conn.heavy.take()) or (t in self.STATE and not conn.state.take()):
                raise LobbyError(proto.E_RATE, "slow down")
            reply = await fn(conn, msg)
        except LobbyError as e:
            conn.send({"t": "error", "code": e.code, "msg": e.msg, "re": rid})
            if e.code in (proto.E_PROTO, proto.E_VERSION) and t == "hello":
                return False
            return True
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError, IndexError) as e:
            conn.errors += 1
            conn.send({"t": "error", "code": proto.E_BAD_REQUEST, "msg": "bad field: " + proto.clean_text(e, 120),
                       "re": rid})
            return conn.errors < 5
        if reply is False:
            return False
        if reply is not None:
            if rid is not None:
                reply["re"] = rid
            conn.send(reply)
        elif rid is not None:
            conn.send({"t": "ok", "re": rid})
        return True

    # ------------------------------------------------------------------ hello / login
    async def h_hello(self, conn, msg):
        if conn.player is not None:
            raise LobbyError(proto.E_STATE, "already logged in")
        if int(msg.get("proto", 0)) != proto.PROTO_VERSION:
            raise LobbyError(proto.E_PROTO, f"this server speaks lobby protocol {proto.PROTO_VERSION}; "
                                            "update the launcher")
        build = msg.get("build") or {}
        bid = BuildInfo.wire_id(build)
        if self.cfg.builds and bid not in self.cfg.builds:
            raise LobbyError(proto.E_VERSION, f"build {bid} is not accepted by this server; update the "
                                              "launcher and rebuild the game")
        conn.build_id = bid
        conn.release = proto.clean_text(build.get("release", ""), 32)     # (shown to everybody in the lobby list)
        caps = msg.get("caps")
        conn.caps = CAPS.intersection(str(c) for c in caps[:16]) if isinstance(caps, list) else frozenset()
        conn.helloed = True
        return {"t": "welcome", "server": SERVER_NAME, "proto": proto.PROTO_VERSION,
                "udp_port": self.udp.port, "udp_port2": self.udp.port2, "build": bid,
                "accounts": self.cfg.accounts, "guests": self.cfg.guests, "motd": self.cfg.motd,
                "ip": conn.ip, "time": time.time(), "features": FEATURES,
                "tls": conn.writer.get_extra_info("ssl_object") is not None,
                "ranked_guests": self.cfg.guest_ranked, "placement": self.cfg.placement,
                "caps": sorted(conn.caps), "relay_only": self.cfg.force_relay,
                "strict_range": self.cfg.strict_range, "pair_cooldown": self.cfg.pair_cooldown,
                "set_wins": self.cfg.ranked_set_wins if "sets" in conn.caps else 1,
                # regional relays: the client measures its UDP round trip to each and reports it (relay_rtt)
                **({"relays": self.relays.public_list()} if "relays" in conn.caps else {}),
                # friends: the limits, for the launcher's texts
                **({"friend_limits": {"max": self.cfg.max_friends, "per_day": self.cfg.friend_requests_day,
                                      "invite_seconds": self.cfg.invite_seconds}}
                   if "friends" in conn.caps else {})}

    async def h_login(self, conn, msg):
        if not conn.helloed:
            raise LobbyError(proto.E_STATE, "hello first")
        if conn.player is not None:
            raise LobbyError(proto.E_STATE, "already logged in")
        mode = msg.get("mode", "guest")
        if mode == "resume":
            return self._resume(conn, str(msg.get("token", "")))
        remember = bool(msg.get("remember"))
        account = None
        codes = None
        session = None
        if mode == "session":
            # A remembered login: the launcher kept the token from an earlier password login.
            if not self.cfg.accounts:
                raise LobbyError(proto.E_NOT_ALLOWED, "this server has no accounts")
            key_ip = "ip:" + conn.akey
            if not self.login_fail.peek_ok(key_ip):
                raise LobbyError(proto.E_RATE, "too many failed logins; wait a few minutes")
            session = str(msg.get("session", ""))
            account = self.store.session_account(session, self.cfg.session_days)
            if account is None:
                self.login_fail.take(key_ip)
                self.counters["login_failures"] += 1
                raise LobbyError(proto.E_AUTH, "the saved login has expired; log in with your password")
            self._refuse_banned(account)
            name = account["name"]
            self._good_login(name, conn.akey)
        else:
            name = msg.get("name", "")
            if not proto.valid_name(name):
                raise LobbyError(proto.E_BAD_NAME, "names are 2-16 letters, digits, spaces or _-.[]()!?")
            if mode in ("guest", "register") and proto.reserved_name(name):
                raise LobbyError(proto.E_BAD_NAME, "that name is reserved")
            if mode in ("guest", "register") and self.name_blocked(name):
                raise LobbyError(proto.E_BAD_NAME, "that name is not allowed here")
            if mode == "guest":
                if not self.cfg.guests:
                    raise LobbyError(proto.E_NOT_ALLOWED, "this server has no guest logins")
                if self.store.account(name) is not None:
                    raise LobbyError(proto.E_NAME_TAKEN, "that name belongs to an account")
                self._check_lookalike(name)
            elif mode in ("account", "register"):
                if not self.cfg.accounts:
                    raise LobbyError(proto.E_NOT_ALLOWED, "this server has no accounts")
                pw = msg.get("password", "")
                self._check_pw_rules(pw)
                key_ip, key_name = "ip:" + conn.akey, "name:" + name.lower()
                # The name's lockout (5 failures, then one a minute, from all addresses together) stops a
                # spread-out guessing attack -- and would lock the owner out with it: an address this
                # account logged in from before is not held back by it, only by its own address limit.
                known = conn.akey in self.good_logins.get(name.lower(), ())
                if not (self.login_fail.peek_ok(key_ip) and (known or self.login_fail.peek_ok(key_name))):
                    raise LobbyError(proto.E_RATE, "too many failed logins; wait a few minutes")
                if mode == "register":
                    if self.by_name.get(name.lower()) is not None:
                        raise LobbyError(proto.E_NAME_TAKEN, "someone with that name is online")
                    self._check_lookalike(name)
                    if not self.registrations.take(conn.akey):
                        raise LobbyError(proto.E_RATE, "too many new accounts from this address")
                    pw_hash = await self._pw(hash_password, pw, self.cfg.scrypt_n)
                    account = self.store.create_account(name, pw_hash)
                    if account is None:
                        raise LobbyError(proto.E_NAME_TAKEN, "that name is taken")
                    codes = self.store.issue_recovery_codes(account["id"], self.cfg.recovery_codes)
                    self.counters["accounts_created"] += 1
                    log.info("account %r created from %s", name, conn.ip)
                else:
                    # Count the attempt before the (slow) check, give it back when it was right: parallel
                    # attempts on several connections cannot all pass the limit while the first is hashed.
                    self.login_fail.take(key_ip)
                    if not known:
                        self.login_fail.take(key_name)
                    account = self.store.account(name)
                    try:
                        ok = account is not None and await self._pw(check_password, pw, account["pw"])
                    except LobbyError:          # "server busy": not an attempt at all
                        self.login_fail.give(key_ip)
                        if not known:
                            self.login_fail.give(key_name)
                        raise
                    if not ok:
                        self.counters["login_failures"] += 1
                        raise LobbyError(proto.E_AUTH, "wrong name or password")
                    self.login_fail.give(key_ip)
                    if not known:
                        self.login_fail.give(key_name)
                    self._refuse_banned(account)
                    self._good_login(name, conn.akey)
                name = account["name"]
                if remember:
                    session = self.store.create_session(account["id"], self.cfg.session_days)
            else:
                raise LobbyError(proto.E_BAD_REQUEST, "mode is guest, account, register, session or resume")
        if conn.closed:
            return False
        old = self.by_name.get(name.lower())
        if old is not None:
            if account is not None and old.account_id == account["id"]:
                # The same account logging in again: the new connection wins. A match in progress
                # stays with the player (the new connection takes it over, like a resume).
                m = old.match
                if old.conn is not None:
                    old.send({"t": "kicked", "reason": "logged in from another place"})
                    old.conn.player = None
                    old.conn.close()
                if (m is not None and m.state == "playing") or self._between_set_games(old):
                    # (between two games of a ranked set the set moves with the player too)
                    return self._take_over(conn, old, session)
                self.player_dropped(old, final=True)
            else:
                raise LobbyError(proto.E_NAME_TAKEN, "someone with that name is online")
        p = Player(conn, name, account is None, account)
        p.rules = self.rules
        p.session = session
        if account is not None:
            p.rating = self.store.rating(account["id"])
            p.rank = self.store.rank_state(account["id"])
            p.main = self.store.main_char(account["id"])
            self.store.touch(account["id"])
            for b in self.store.blocks_of(account["id"]):
                p.blocks[f"a:{b['blocked_id']}"] = {"name": b["blocked_name"], "guest": False, "since": b["created"]}
            p.friends = self.store.friend_ids(account["id"])
            self.by_account[account["id"]] = p
        conn.player = p
        self.players[p.id] = p
        self.by_name[name.lower()] = p
        self.by_skel[proto.name_skeleton(name)] = p
        self.sessions[p.token] = p
        self.dirty = True
        self.counters["logins_guest" if p.guest else "logins_account"] += 1
        log.info("login %s %r (%s) from %s build %s", p.id, name, "guest" if p.guest else mode,
                 conn.ip, p.build_id)
        self.note("login", player=p.id, name=name)
        reply = {"t": "login_ok", "you": p.public(), "token": p.token}
        if session and mode != "session":
            reply["session"] = session
        if codes:
            reply["recovery_codes"] = codes
        asyncio.get_running_loop().call_soon(self._send_active_notices, p)
        asyncio.get_running_loop().call_soon(self._send_friends, p)
        return reply

    def _take_over(self, conn, p, session):
        """An account logged in again while its match runs: the new connection becomes the player."""
        if p.build_id != conn.build_id:
            raise LobbyError(proto.E_VERSION, "finish your running match with the same game build first")
        if session:
            p.session = session
        p.conn = None
        reply = self._resume(conn, p.token)
        if session:
            reply["session"] = session
        return reply

    async def _pw(self, fn, *args):
        """Hash or check a password on a worker thread. scrypt costs ~16 MB and tens of ms of CPU each:
        at most T5L_PW_CONCURRENCY at once, T5L_PW_QUEUE waiting, the rest are told to come back --
        a login flood from many addresses cannot pile up work (and memory) without bound."""
        if self.pw_waiting >= self.cfg.pw_queue:
            self._count("pw_busy")
            raise LobbyError(proto.E_RATE, "the server is busy; try again in a few seconds")
        self.pw_waiting += 1
        try:
            async with self.pw_sem:
                return await asyncio.to_thread(fn, *args)
        finally:
            self.pw_waiting -= 1

    def _good_login(self, name, akey):
        d = self.good_logins.setdefault(name.lower(), {})
        d[akey] = time.monotonic()
        if len(d) > 8:
            del d[min(d, key=d.get)]

    def _check_lookalike(self, name):
        """A new name (guest or account) must not pass for an account or a player online: same
        proto.name_skeleton, different name (W1shin next to Wishin, Wish.in, WIshin ...)."""
        other = self.store.similar_account(name)
        if other is not None:
            raise LobbyError(proto.E_NAME_TAKEN, f"that name looks too much like the account {other}")
        p = self.by_skel.get(proto.name_skeleton(name))
        if p is not None and p.name.lower() != name.lower():
            raise LobbyError(proto.E_NAME_TAKEN, f"that name looks too much like {p.name}, who is online")

    @staticmethod
    def _check_pw_rules(pw):
        if not isinstance(pw, str) or not 6 <= len(pw) <= 128:
            raise LobbyError(proto.E_AUTH, "passwords are 6-128 characters")

    async def h_passwd(self, conn, msg):
        """Change the password: old + new. Every remembered login of the account ends; with
        `remember` this connection gets a fresh one."""
        p = conn.player
        if p.account_id is None:
            raise LobbyError(proto.E_NOT_ALLOWED, "guests have no password")
        new = msg.get("new", "")
        self._check_pw_rules(new)
        key = "name:" + p.name.lower()
        if not self.login_fail.peek_ok(key):
            raise LobbyError(proto.E_RATE, "too many failed attempts; wait a few minutes")
        if not self.pw_ops.take(f"a:{p.account_id}"):
            raise LobbyError(proto.E_RATE, "too many password changes; wait a minute")
        row = self.store.account_by_id(p.account_id)
        if not await self._pw(check_password, str(msg.get("old", "")), row["pw"]):
            self.login_fail.take(key)
            raise LobbyError(proto.E_AUTH, "the current password is wrong")
        self.store.set_password(p.account_id, await self._pw(hash_password, new, self.cfg.scrypt_n))
        self.store.revoke_sessions(p.account_id)
        p.session = None
        reply = {"t": "passwd_ok"}
        if msg.get("remember"):
            p.session = reply["session"] = self.store.create_session(p.account_id, self.cfg.session_days)
        log.info("password changed for %r", p.name)
        return reply

    async def h_recover(self, conn, msg):
        """Forgotten password: name + one of the recovery codes shown at registration + a new
        password. Works without logging in; every remembered login of the account ends."""
        if not conn.helloed:
            raise LobbyError(proto.E_STATE, "hello first")
        name = str(msg.get("name", ""))
        new = msg.get("password", "")
        self._check_pw_rules(new)
        key_ip, key_name = "ip:" + conn.akey, "name:" + name.lower()
        if not (self.login_fail.peek_ok(key_ip) and self.login_fail.peek_ok(key_name)):
            raise LobbyError(proto.E_RATE, "too many failed attempts; wait a few minutes")
        account = self.store.account(name) if proto.valid_name(name) else None
        if account is None or not self.store.use_recovery_code(account["id"], str(msg.get("code", ""))):
            self.login_fail.take(key_ip)
            self.login_fail.take(key_name)
            raise LobbyError(proto.E_AUTH, "wrong name or recovery code (each code works once)")
        self.store.set_password(account["id"], await self._pw(hash_password, new, self.cfg.scrypt_n))
        self.store.revoke_sessions(account["id"])
        log.info("password of %r reset with a recovery code from %s", account["name"], conn.ip)
        return {"t": "recovered", "name": account["name"], "codes_left": self.store.recovery_left(account["id"])}

    async def h_recovery_codes(self, conn, msg):
        """A new set of recovery codes (the old ones stop working); needs the password."""
        p = conn.player
        if p.account_id is None:
            raise LobbyError(proto.E_NOT_ALLOWED, "guests have no account")
        key = "name:" + p.name.lower()
        if not self.login_fail.peek_ok(key):
            raise LobbyError(proto.E_RATE, "too many failed attempts; wait a few minutes")
        if not self.pw_ops.take(f"a:{p.account_id}"):
            raise LobbyError(proto.E_RATE, "too many requests for new codes; wait a minute")
        row = self.store.account_by_id(p.account_id)
        if not await self._pw(check_password, str(msg.get("password", "")), row["pw"]):
            self.login_fail.take(key)
            raise LobbyError(proto.E_AUTH, "wrong password")
        return {"t": "recovery_codes",
                "codes": self.store.issue_recovery_codes(p.account_id, self.cfg.recovery_codes)}

    def _resume(self, conn, token):
        p = self.sessions.get(token)
        if p is None or p.conn is not None or p.build_id != conn.build_id:
            raise LobbyError(proto.E_AUTH, "session expired; log in again")
        p.conn = conn
        p.ip = conn.ip
        p.dropped_at = None
        conn.player = p
        self.dirty = True
        log.info("resume %s %r", p.id, p.name)
        reply = {"t": "login_ok", "you": p.public(), "token": p.token, "resumed": True}
        asyncio.get_running_loop().call_soon(self._send_active_notices, p)
        asyncio.get_running_loop().call_soon(self._send_friends, p)
        m = p.match
        if m is not None and m.state == "playing":
            side = m.side(p)
            h = m.timers.pop(f"grace{side}", None)
            if h:
                h.cancel()
                m.players[1 - side].send({"t": "notice", "code": "opponent_back", "match": m.id,
                                          "msg": f"{p.name} is back in the lobby"})
            asyncio.get_running_loop().call_soon(self._send_match_start, m, side)
        elif self._between_set_games(p):
            self._set_back(p.set, p)
        return reply

    async def h_logout(self, conn, msg):
        if conn.player is not None:
            p = conn.player
            if msg.get("forget") and p.account_id is not None:
                tok = msg.get("session") or p.session
                row = self.store.session_account(tok, self.cfg.session_days) if tok else None
                if row is not None and row["id"] == p.account_id:
                    self.store.revoke_session(tok)
                p.session = None
            conn.player = None
            m = p.match
            if m is not None and m.state == "playing":
                # Logging out (or closing the launcher) mid-match is leaving it.
                await self.h_leave_match(_ConnOf(p), {"match": m.id})
            self.player_dropped(p, final=True)
        conn.send({"t": "bye", "re": msg.get("rid")})
        return False

    async def h_ping(self, conn, msg):
        return {"t": "pong", "time": time.time()}

    async def h_udp_rtt(self, conn, msg):
        ms = float(msg["ms"])
        if 0 <= ms < 10000:
            p = conn.player
            p.server_rtt = ms                 # matchmaking uses the exact value
            shown = p.rtt_shown
            if shown is None or abs(ms - shown) > max(5.0, 0.2 * shown):
                p.rtt_shown = ms              # the lobby list only when it changed noticeably
                self.dirty = True

    async def h_relay_rtt(self, conn, msg):
        """The client's UDP round trips (ms) to the regional relays the server listed: {"rtts": {id: ms}}. A relay
        it could not reach is left out (and is then never chosen for its matches)."""
        rtts = msg["rtts"]
        if not isinstance(rtts, dict):
            raise TypeError("rtts is {relay id: ms}")          # (-> "bad field", for programmers)
        out = {}
        for rid, ms in list(rtts.items())[:MAX_RELAYS]:
            if rid in self.relays.nodes and isinstance(ms, (int, float)) and 0 <= ms < 10000:
                out[rid] = float(ms)
        conn.player.relay_rtt = out

    def _relays_changed(self):
        """relays.json changed: clients that know the regional relays get the new list (and measure it again)."""
        lst = self.relays.public_list()
        for c in list(self.conns):
            if c.player is not None and "relays" in c.caps:
                c.send({"t": "relays", "relays": lst})
        for p in self.players.values():
            p.relay_rtt = {k: v for k, v in p.relay_rtt.items() if k in self.relays.nodes}

    def _spawn(self, coro):
        t = asyncio.ensure_future(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)
        return t

    async def h_perf(self, conn, msg):
        """The client's measure of its PC: sustained frames per second of its last match."""
        try:
            fps = float(msg.get("fps"))
        except (TypeError, ValueError):
            raise LobbyError(proto.E_BAD_REQUEST, "fps is a number")
        if not 0 < fps < 1000:
            raise LobbyError(proto.E_BAD_REQUEST, "fps out of range")
        conn.player.fps = round(fps, 1)
        self.dirty = True

    def _check_speed(self, p):
        """Ranked needs a PC that keeps up: lockstep runs at the slower PC's speed, so one slow PC
        makes the match crawl for both (QA: 15 fps on one side -> both at 15)."""
        if self.cfg.min_fps > 0 and p.fps is not None and p.fps < self.cfg.min_fps:
            raise LobbyError(proto.E_NOT_ALLOWED,
                             f"this PC ran its last match at {p.fps:.0f} fps; ranked needs at least "
                             f"{self.cfg.min_fps:.0f} (both games run at the slower PC's speed). Close other "
                             f"programs or lower the resolution scale, then play a casual match to measure again")

    def _speed_notice(self, m):
        """Before the match: tell both players when a PC is slow (the match runs at its speed)."""
        if self.cfg.warn_fps <= 0:
            return
        slow = [q for q in m.players if q.fps is not None and q.fps < self.cfg.warn_fps]
        if not slow:
            return
        for side, p in enumerate(m.players):
            # (while the ready check is blind the opponent has no name yet)
            other = "your opponent's PC" if m.blind[side] else None
            parts = [("your PC" if q is p else (other or f"{q.name}'s PC")) + f" ran its last match at {q.fps:.0f} fps"
                     for q in slow]
            p.send({"t": "notice", "code": "slow_pc", "match": m.id,
                    "msg": "; ".join(parts) + " -- this match runs at the slower PC's speed"})

    async def h_lobby(self, conn, msg):
        conn.need_full = True       # the next broadcast is whole again: deltas follow the broadcasts
        return self._snapshot(full="delta" in conn.caps)

    async def h_leaderboard(self, conn, msg):
        key = (max(1, min(100, int(msg.get("limit", 20)))), max(0, min(100000, int(msg.get("offset", 0)))))
        # The same page asked again within a few seconds comes from memory: the query sorts every
        # ranked account and looks up each row's main character (many players open the tab at once).
        cache = self.__dict__.setdefault("_lb_cache", {})
        hit = cache.get(key)
        if hit is None or time.monotonic() - hit[0] > 5.0 or hit[2] != self.store.writes:
            if len(cache) > 64:
                cache.clear()
            hit = cache[key] = (time.monotonic(), self.store.leaderboard(*key), self.store.writes)
        rows = [dict(r) for r in hit[1]]
        for r in rows:
            r["rank"] = ranks.name(r["tier"])
            r["provisional"] = r["tier"] == ranks.BEGINNER or r["rd"] > self.rules.provisional_rd
            r["rating"], r["rd"] = round(r["rating"]), round(r["rd"])
            r["online"] = r["name"].lower() in self.by_name
        return {"t": "leaderboard", "rows": rows}

    async def h_chat(self, conn, msg):
        text = str(msg["text"]).strip()
        if not text:
            return None
        if not self.chat_rate.take(conn.player.id) or not self.chat_rate.take("addr:" + conn.akey, 0.5):
            raise LobbyError(proto.E_RATE, "chat: slow down")
        if not self.chat_total.take():
            # Every line goes to every player: the lobby as a whole gets T5L_CHAT_TOTAL_RATE lines a second.
            raise LobbyError(proto.E_RATE, "the chat is busy; try again in a moment")
        text = proto.clean_text(text, 200)
        if not text:
            return None
        p = conn.player
        self.counters["chat_lines"] += 1
        data = proto.encode({"t": "chat", "from": p.brief(), "text": text, "time": time.time()})
        for q in self.players.values():
            if q.conn is not None:
                q.conn.send_raw(data)

    # ------------------------------------------------------------------ player removal
    def player_dropped(self, p, final=False):
        """Connection gone (or logout). Keep the player resumable while a match needs them."""
        p.conn = None
        p.dropped_at = time.monotonic()
        self._leave_queue(p)
        self._leave_room(p)
        for c in [c for c in self.challenges.values() if p in (c.src, c.dst)]:
            self._end_challenge(c, "cancelled")
        for inv in [i for i in self.invites.values() if p in (i.src, i.dst)]:
            self._end_invite(inv, "cancelled")
        m = p.match
        if m is not None and m.state not in ("playing", "done"):
            self.cancel_match(m, "opponent_left", by=p)
        elif m is not None and m.state == "playing":
            # Lost the lobby mid-match: the launcher reconnects on its own. Not back within the
            # grace period -> the match is lost (docs/RANKED.md, disconnects).
            side = m.side(p)
            m.lost_lobby[side] = True
            self._timer(m, f"grace{side}", self.cfg.reconnect_grace, self._grace_expired, m, side)
            m.players[1 - side].send({"t": "notice", "code": "opponent_dropped", "match": m.id,
                                      "grace": self.cfg.reconnect_grace,
                                      "msg": f"{p.name} lost the lobby connection; waiting "
                                             f"{self.cfg.reconnect_grace:.0f} s for them to return"})
        if not final and self._between_set_games(p):
            # Between two games of a ranked set: the launcher reconnects on its own, like mid-match. Not back
            # within the grace period -> the set is lost (docs/RANKED.md "Ranked sets").
            self._set_dropped(p.set, p)
        elif final or p.match is None:
            self._forget(p)
        self.dirty = True
        self.note("drop", player=p.id)

    def _forget(self, p):
        self.players.pop(p.id, None)
        if self.by_name.get(p.name.lower()) is p:
            del self.by_name[p.name.lower()]
        if self.by_skel.get(proto.name_skeleton(p.name)) is p:
            del self.by_skel[proto.name_skeleton(p.name)]
        if p.account_id is not None and self.by_account.get(p.account_id) is p:
            del self.by_account[p.account_id]
        self.sessions.pop(p.token, None)
        self._leave_queue(p)
        self._leave_room(p)
        if p.set is not None and p.set.state == "active" and p.set.current is None:
            self._decline_recent(p.set, p)
            self._end_set(p.set, "left", by=p)

    # ------------------------------------------------------------------ queues
    async def h_queue(self, conn, msg):
        p = conn.player
        self._refuse_draining()
        mode = msg.get("mode", "quick")
        if mode not in QUEUE_MODES:
            raise LobbyError(proto.E_BAD_REQUEST, "mode is quick or ranked")
        if mode == "ranked" and p.guest and not self.cfg.guest_ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked needs an account")
        if mode == "ranked":
            self._check_speed(p)
        if p.status not in ("idle", "queue"):
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        self._abandon_set(p)                     # looking for a new opponent leaves the old set (and unlocks the character)
        if "char" in msg:
            self._set_char(p, msg["char"])
        p.strict = bool(msg.get("strict")) and mode == "ranked"
        self._leave_queue(p)
        self._enqueue(p, mode, time.monotonic())
        return {"t": "queued", "mode": mode, "strict": p.strict}

    DRAIN_TEXT = "the server restarts for an update in a moment; running matches finish first. Try again in a minute"

    def _refuse_draining(self):
        if self.draining:
            raise LobbyError(proto.E_NOT_ALLOWED, self.DRAIN_TEXT)

    def set_draining(self, on):
        """`admin drain`: before a restart, take no new matches (queues, rooms, challenges, rematches)
        and let the running ones finish; `admin drain --wait` returns when none is left. A restart
        clears it."""
        if on == self.draining:
            return
        self.draining = on
        log.warning("drain %s: %d match(es) running", "on" if on else "off", len(self.matches))
        if on:
            for p in list(self.players.values()):
                self._leave_queue(p)
                p.send({"t": "notice", "code": "server_restart", "msg": self.DRAIN_TEXT})
        self.dirty = True

    def _set_char(self, p, char):
        char = str(char or fighters.RANDOM)
        if not self.table.valid_fighter(char):
            raise LobbyError(proto.E_BAD_REQUEST, f"unknown character {char!r}")
        gs = p.set
        if gs is not None and gs.state == "active" and gs.locked and char != gs.picks.get(p.id, p.char):
            raise LobbyError(proto.E_STATE, "your character is locked until this ranked set ends")
        if p.char != char:
            p.char = char
            self.dirty = True

    async def h_set_char(self, conn, msg):
        """The character the player will fight with (a fighters key or "random")."""
        self._set_char(conn.player, msg.get("char"))

    # ------------------------------------------------------------------ profiles, history, leaderboard
    async def h_profile(self, conn, msg):
        name = str(msg.get("name") or conn.player.name)
        return {"t": "profile", "profile": self._profile(name, int(msg.get("history", 10)), conn.player)}

    def _profile(self, name, n_history=10, me=None):
        online = self.by_name.get(name.lower())
        row = self.store.account(name) if proto.valid_name(name) else None
        if row is None:
            if online is None:
                raise LobbyError(proto.E_NOT_FOUND, "no such player")
            d = online.public()
            d.update({"account": False, "history": [], "chars": [], "online": online.online})
            return d
        aid = row["id"]
        rt = self.store.rating(aid)
        rank = self.store.rank_state(aid)
        d = {"name": row["name"], "guest": False, "account": True, "online": bool(online and online.online),
             "rating": round(rt.r), "rd": round(rt.rd), "record": [row["wins"], row["losses"], row["draws"]],
             "ranked_games": row["ranked_games"], "games": row["games"],
             "peak": rank.peak, "peak_rank": ranks.name(rank.peak), "place": self.store.place(aid),
             "member_since": row["created"],
             "chars": self.store.char_usage(aid), "main": self.store.main_char(aid),
             "voids_24h": self.store.strikes(aid, time.time() - DAY),
             "history": self.store.history(aid, max(0, min(50, n_history))),
             "sets": self.store.set_history(aid, max(0, min(20, n_history)))}
        d.update(ranks.describe(rank, rt.rd, self.rules))
        if online is not None:
            d["status"] = online.status
        d["self"] = me is not None and me.account_id == aid
        if d["self"] or (me is not None and aid in me.friends):
            # When an account was last online is for its friends (their list says "last seen") and itself: since
            # 1.1.2 the Friends page makes that a friends-only thing, so a profile no longer tells it to everyone.
            d["last_seen"] = row["last_seen"]
        if d["self"]:
            d["recovery_codes_left"] = self.store.recovery_left(aid)
        elif me is not None and me.account_id is not None and me.conn is not None and "friends" in me.conn.caps:
            d["friend"] = self._friend_relation(me, aid)     # friends | asked | asks | None (the Add friend button)
        return d

    async def h_history(self, conn, msg):
        name = str(msg.get("name") or conn.player.name)
        row = self.store.account(name) if proto.valid_name(name) else None
        if row is None:
            raise LobbyError(proto.E_NOT_FOUND, "history is kept for accounts only")
        limit = max(1, min(100, int(msg.get("limit", 20))))
        return {"t": "history", "name": row["name"],
                "rows": self.store.history(row["id"], limit, max(0, min(100000, int(msg.get("offset", 0)))))}

    async def h_unqueue(self, conn, msg):
        self._leave_queue(conn.player)

    def _enqueue(self, p, mode, since):
        p.status, p.queue_mode, p.queue_since = "queue", mode, since
        q = self.queues[mode]
        q.append(p)
        q.sort(key=lambda x: x.queue_since)
        self.dirty = True

    def _leave_queue(self, p):
        if p.queue_mode:
            q = self.queues[p.queue_mode]
            if p in q:
                q.remove(p)
            p.queue_mode = None
            if p.status == "queue":
                p.status = "idle"
            self.dirty = True

    def _est_ping(self, a, b):
        """Ping between two players as the server can tell before they are connected -> (ms, known, via).

        The worst the pair can get: the relay path through the best relay, the sum of both players' UDP round
        trips to it -- this server (`udp_rtt`) or a regional relay both of them measured (`relay_rtt`, clients
        with the "relays" cap that is up), whichever sum is smaller (via: "main" or the relay's id). A direct
        path is usually shorter. Two Californians whose round trips to Nuremberg are 150 ms each but 25 ms to
        a relay in Oregon: about 50 ms, not 300. A pair with a 1.1.0 / 1.1.1 client measured no regional relay:
        the sum through this server, as before. An unknown round trip to this server counts as 50 ms and makes
        the estimate `known: false` -- unless a measured regional relay gives one. The real peer-to-peer ping
        is measured after both accepted (nat.py, `rtt_ms` in match_start)."""
        ra = a.server_rtt if a.server_rtt is not None else 50.0
        rb = b.server_rtt if b.server_rtt is not None else 50.0
        est, known, via = ra + rb, a.server_rtt is not None and b.server_rtt is not None, RELAY_MAIN
        regional = self._pair_relays(a, b, own=False)
        if regional and (regional[0][0] < est or not known):
            est, known, via = regional[0][0], True, regional[0][1].id
        return est, known, via

    @staticmethod
    def _pair_id(p):
        return p.account_id if p.account_id is not None else p.id

    def _cooling(self, a, b, now):
        """Did these two finish a ranked game less than T5L_PAIR_COOLDOWN seconds ago?"""
        t = self.pair_last.get(frozenset((self._pair_id(a), self._pair_id(b))))
        return t is not None and now - t < self.cfg.pair_cooldown

    def match_queue(self, now=None):
        """One matchmaking pass over both queues. Returns the matches made."""
        now = time.monotonic() if now is None else now
        made = []
        if self.draining:
            return made
        for mode in QUEUE_MODES:
            q = self.queues[mode]
            taken = set()
            for i, a in enumerate(q):
                if a in taken:
                    continue
                wa = now - a.queue_since
                best, best_score = None, None
                for b in q[i + 1:]:
                    if b in taken or b.build_id != a.build_id or self._is_blocked(a, b):
                        continue
                    ping = self._est_ping(a, b)[0]
                    wb = now - b.queue_since
                    # region first: the estimated ping must fit the window of both, which grows while they wait
                    limit = min(self._ping_limit(wa, mode), self._ping_limit(wb, mode))
                    if ping > limit:
                        continue
                    if mode == "ranked":
                        if not self.cfg.ranked_same_ip and self._same_address(a, b):
                            continue                     # one household / one PC: never a ranked pair (alt farming)
                        if self._cooling(a, b, time.monotonic()):
                            continue                     # just played each other: not again within T5L_PAIR_COOLDOWN
                        window = min(self._rating_window(wa), self._rating_window(wb))
                        dr = abs(a.rating.r - b.rating.r)
                        if dr > window:
                            continue
                        if (a.strict or b.strict) and dr > self.cfg.strict_range:
                            continue                     # strict matchmaking: +-T5L_STRICT_RANGE rating points, however long it takes
                        score = dr / window + (ping / limit if limit < math.inf else ping / 1000.0)
                    else:
                        score = ping                     # quick: the closest one within the window
                    if best_score is None or score < best_score:
                        best, best_score = b, score
                if best is not None:
                    taken.update((a, best))
                    made.append((a, best, mode))
        for a, b, mode in made:
            # Host: the one with the lower server RTT (more likely the better-connected PC).
            ra = a.server_rtt if a.server_rtt is not None else 1e9
            rb = b.server_rtt if b.server_rtt is not None else 1e9
            host, join = (a, b) if ra <= rb else (b, a)
            since = [host.queue_since, join.queue_since]
            self._leave_queue(a)
            self._leave_queue(b)
            m = self.create_match(host, join, ranked=(mode == "ranked"), origin="queue")
            m.queue_since = since
            m.queue_mode = mode
        return made

    @staticmethod
    def _rating_window(waited):
        return min(800.0, 100.0 + 25.0 * waited)

    def _ping_limit(self, waited, mode="ranked"):
        """The highest estimated ping a queue pair may have after `waited` seconds (docs/RANKED.md "Matchmaking"):
        T5L_PING_START ms at first, growing while the player waits, and any ping at all once it has waited
        T5L_PING_ANY_SECONDS (quick: faster and sooner) -- nobody waits for ever because nobody is near."""
        c = self.cfg
        widen, any_s = (c.ping_widen, c.ping_any_seconds) if mode == "ranked" else \
            (c.quick_ping_widen, c.quick_ping_any_seconds)
        if any_s > 0 and waited >= any_s:
            return math.inf
        return c.ping_start + widen * max(0.0, waited)

    async def _tick_queue(self):
        while True:
            await asyncio.sleep(0.5)
            try:
                self.match_queue()
            except Exception:
                log.exception("matchmaker")

    # ------------------------------------------------------------------ rooms
    async def h_room_create(self, conn, msg):
        p = conn.player
        self._refuse_draining()
        if p.status != "idle":
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        ranked = bool(msg.get("ranked", False))
        if ranked and not self.cfg.ranked_rooms:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked matches come from the ranked queue on this server")
        if ranked and p.guest and not self.cfg.guest_ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked needs an account")
        if ranked:
            self._check_speed(p)
        self._abandon_set(p)
        name = proto.clean_text(msg.get("name") or f"{p.name}'s room", 32)
        r = Room(p, name, ranked)
        self.rooms[r.id] = r
        p.room, p.status = r, "room"
        self.dirty = True
        return {"t": "room", "room": r.public()}

    async def h_room_join(self, conn, msg):
        p = conn.player
        self._refuse_draining()
        r = self.rooms.get(msg.get("room"))
        if r is None:
            raise LobbyError(proto.E_NOT_FOUND, "no such room")
        if p.status != "idle":
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        if len(r.members) >= 2:
            raise LobbyError(proto.E_FULL, "room is full")
        if r.build_id != p.build_id:
            raise LobbyError(proto.E_VERSION, "that player runs a different build of the game")
        if r.ranked and p.guest and not self.cfg.guest_ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "ranked needs an account")
        if r.ranked:
            self._check_speed(p)
        if any(self._is_blocked(p, q) for q in r.members):
            raise LobbyError(proto.E_NOT_ALLOWED, "you cannot join this room")
        self._abandon_set(p)
        r.members.append(p)
        p.room, p.status = r, "room"
        self.dirty = True
        reply = {"t": "room", "room": r.public()}
        asyncio.get_running_loop().call_soon(self._room_start, r)
        return reply

    async def h_room_leave(self, conn, msg):
        p = conn.player
        if p.room is None:
            raise LobbyError(proto.E_STATE, "not in a room")
        if p.match is not None:
            raise LobbyError(proto.E_BUSY, "finish the match first")
        self._leave_room(p)

    async def h_rematch(self, conn, msg):
        """Rooms: start the next match in the room (with a ready check). After any other match:
        `match` = the finished match's id, `accept` (default true), `keep` = true when this
        player's game is still running and connected to the opponent's (then the rematch skips
        the connection setup and continues inside the running games)."""
        p = conn.player
        if msg.get("accept", True):
            self._refuse_draining()
        if msg.get("match") is None:
            r = p.room
            if r is None or len(r.members) != 2 or r.match is not None:
                raise LobbyError(proto.E_STATE, "no opponent in the room")
            if r.set is not None and r.set.rated and r.set.state == "active":
                raise LobbyError(proto.E_STATE, "the ranked set goes on by itself")
            self._room_start(r)
            return None
        prev = self.recent.get(msg.get("match"))
        if prev is None or prev.side(p) is None:
            raise LobbyError(proto.E_NOT_FOUND, "that match is over; find a new opponent")
        side = prev.side(p)
        other = prev.players[1 - side]
        gs = prev.set
        if gs is not None and gs.rated and gs.state == "active":
            # A ranked set goes on by itself (no vote); declining is leaving it.
            if msg.get("accept", True) or gs.current is not None:
                raise LobbyError(proto.E_STATE, "the ranked set goes on by itself")
            self._end_set(gs, "left", by=p)
            return None
        if not msg.get("accept", True):
            self.recent.pop(prev.id, None)
            other.send({"t": "rematch", "match": prev.id, "state": "declined", "from": p.brief()})
            if prev.set is not None and prev.set.last is prev:
                self._end_set(prev.set, "declined", by=p)
            return None
        if p.status not in ("idle", "room") or p.match is not None:
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        if self._is_blocked(p, other):
            self.recent.pop(prev.id, None)
            raise LobbyError(proto.E_BUSY, "your opponent is no longer available")
        prev.rematch = getattr(prev, "rematch", [None, None])
        prev.rematch[side] = {"keep": bool(msg.get("keep"))}
        if prev.rematch[1 - side] is None:
            other.send({"t": "rematch", "match": prev.id, "state": "offered", "from": p.brief(),
                        "timeout": self.cfg.rematch_window})
            return {"t": "rematch", "match": prev.id, "state": "waiting"}
        if not other.online or other.match is not None or other.status not in ("idle", "room"):
            self.recent.pop(prev.id, None)
            raise LobbyError(proto.E_BUSY, "your opponent is no longer available")
        self.recent.pop(prev.id, None)
        keep = all(r["keep"] for r in prev.rematch) and prev.path is not None
        m = self.create_match(prev.players[0], prev.players[1], ranked=prev.ranked, origin="rematch",
                              room=prev.room, rematch_of=prev, keep=keep)
        return {"t": "rematch", "match": prev.id, "state": "accepted", "next": m.id}

    def _room_start(self, r, invited=False):
        """Two players in the room: their match, with a ready check -- except right after a friend accepted an
        invite to the room (origin "invite": both have said yes already)."""
        if r.id not in self.rooms or len(r.members) != 2 or r.match is not None or self.draining:
            return
        if any(not q.online or q.match is not None for q in r.members):
            return
        gs = r.set if r.set is not None and r.set.state == "active" and \
            {id(q) for q in r.set.players} == {id(q) for q in r.members} else None
        r.match = self.create_match(r.members[0], r.members[1], ranked=r.ranked,
                                    origin="invite" if invited else "room", room=r, game_set=gs)

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
        if r.match is not None and r.match.state not in ("playing", "done"):
            self.cancel_match(r.match, "opponent_left", by=p)
        if r.set is not None and r.set.state == "active" and r.set.current is None:
            self._decline_recent(r.set, p)
            self._end_set(r.set, "left", by=p)
        if not r.members:
            self.rooms.pop(r.id, None)
        elif r.owner is p:
            r.owner = r.members[0]
            for q in r.members:
                q.send({"t": "room", "room": r.public()})
        else:
            for q in r.members:
                q.send({"t": "room", "room": r.public()})
        self.dirty = True

    # ------------------------------------------------------------------ challenges
    async def h_challenge(self, conn, msg):
        p = conn.player
        self._refuse_draining()
        q = self.players.get(msg.get("player"))
        if q is None or not q.online or q is p:
            raise LobbyError(proto.E_NOT_FOUND, "no such player")
        if q.build_id != p.build_id:
            raise LobbyError(proto.E_VERSION, "that player runs a different build of the game")
        if p.status not in ("idle", "queue") or q.status not in ("idle", "queue"):
            raise LobbyError(proto.E_BUSY, "busy")
        if self._is_blocked(p, q):
            raise LobbyError(proto.E_NOT_ALLOWED, "that player is not available")
        now = time.monotonic()
        if now - p.last_challenge < 2.0 or any(c.src is p for c in self.challenges.values()):
            raise LobbyError(proto.E_RATE, "one challenge at a time")
        if sum(1 for c in self.challenges.values() if c.dst is q) >= 3:
            raise LobbyError(proto.E_BUSY, "that player has challenges pending")
        wait = self._retry_left(("challenge", self._block_key(p), self._block_key(q)))
        if wait:
            raise LobbyError(proto.E_RATE, f"your last challenge to that player ended a moment ago; try again in {wait} s")
        p.last_challenge = now
        c = Challenge(p, q)
        self.challenges[c.id] = c
        c.timer = asyncio.get_running_loop().call_later(30.0, self._end_challenge, c, "expired")
        q.send({"t": "challenged", "challenge": c.id, "from": p.brief()})
        return {"t": "challenge", "challenge": c.id}

    async def h_challenge_reply(self, conn, msg):
        p = conn.player
        c = self.challenges.get(msg.get("challenge"))
        if c is None or c.dst is not p:
            raise LobbyError(proto.E_NOT_FOUND, "no such challenge")
        if not msg.get("accept") or self.draining:
            if not self.draining:
                self._retry_later(("challenge", self._block_key(c.src), self._block_key(p)))
            self._end_challenge(c, "declined")
            self._refuse_draining()
            return None
        src = c.src
        self._end_challenge(c, "accepted")
        if not src.online or src.status not in ("idle", "queue") or p.status not in ("idle", "queue"):
            raise LobbyError(proto.E_BUSY, "challenge no longer possible")
        if self._is_blocked(src, p):
            raise LobbyError(proto.E_NOT_ALLOWED, "that player is not available")
        self._abandon_set(src, requester=p)
        self._abandon_set(p)
        self._leave_queue(src)
        self._leave_queue(p)
        self.create_match(src, p, ranked=False, origin="challenge")

    async def h_challenge_cancel(self, conn, msg):
        c = self.challenges.get(msg.get("challenge"))
        if c is None or c.src is not conn.player:
            raise LobbyError(proto.E_NOT_FOUND, "no such challenge")
        self._retry_later(("challenge", self._block_key(c.src), self._block_key(c.dst)))
        self._end_challenge(c, "cancelled")

    def _end_challenge(self, c, state):
        if self.challenges.pop(c.id, None) is None:
            return
        if c.timer:
            c.timer.cancel()
        for q in (c.src, c.dst):
            q.send({"t": "challenge_update", "challenge": c.id, "state": state})

    # ------------------------------------------------------------------ matches: setup
    def _same_address(self, a, b):
        return self.akey(a.ip) == self.akey(b.ip)

    def create_match(self, host, join, ranked, origin, room=None, rematch_of=None, keep=False, game_set=None):
        note, note_code = None, "pair_cap"
        going_on = game_set or (rematch_of.set if rematch_of is not None else None)
        if going_on is not None and going_on.rated and going_on.state == "active" and (
                {id(x) for x in going_on.players} == {id(host), id(join)}):
            pass                     # the next game of a rated set: the set was ranked (and capped) when it began
        elif ranked and not self.cfg.ranked_same_ip and self._same_address(host, join):
            # Two accounts on one internet address: alts of one player feeding each other wins, as far as
            # the server can tell (T5L_RANKED_SAME_IP=1 allows it, e.g. for a LAN event).
            ranked = False
            note_code = "same_address"
            note = "you two play from the same internet address; ranked matches between you do not count"
        elif ranked and host.account_id is not None and join.account_id is not None and self.cfg.pair_cap > 0:
            n = self.store.pair_ranked(host.account_id, join.account_id, time.time() - DAY)
            if n >= self.cfg.pair_cap:
                # Anti win-trading: the same two accounts only move each other's rating so often a day.
                ranked = False
                note = (f"you two played {n} ranked matches in the last 24 hours; this one is unranked "
                        f"(limit {self.cfg.pair_cap})")
        m = Match(host, join, ranked, origin, room)
        m.rematch_of = rematch_of.id if rematch_of is not None else None
        self.matches[m.id] = m
        for inv in [i for i in self.invites.values() if i.src in (host, join) or i.dst in (host, join)]:
            self._end_invite(inv, "cancelled")          # (playing someone else now)
        self._join_set(m, rematch_of, game_set)
        skip_ready = origin in ("challenge", "rematch", "set", "invite")
        est, known, via = self._est_ping(host, join)
        # (`via` stays on this server: which relay the estimate went through would hint where a blind opponent lives)
        ping = {"ms": round(est), "kind": "estimate", "known": known}
        for side, p in enumerate(m.players):
            p.match = m
            p.status = "match"
            # A queue match between strangers is blind: ping and rules first, names and sides after both accepted.
            m.blind[side] = (origin == "queue" and not skip_ready and self.cfg.blind_ready
                             and "blind_ready" in getattr(p.conn, "caps", ()))
            found = {"t": "match_found", "match": m.id, "ranked": ranked, "origin": origin,
                     "you": p.brief(), "ready_check": not skip_ready, "ready_timeout": self.cfg.ready_timeout,
                     "rematch_of": m.rematch_of, "keep": keep, "ping": ping, "set": m.set.info()}
            if m.blind[side]:
                found.update(blind=True, opponent=None)
            else:
                found.update(role="host" if side == 0 else "join", slot=side,
                             opponent=m.players[1 - side].brief())
            p.send(found)
            if note:
                p.send({"t": "notice", "code": note_code, "match": m.id, "msg": note})
        self._speed_notice(m)
        self.dirty = True
        self.counters["matches_found"] += 1
        self.note("match_found", match=m.id, origin=origin, ping=round(est), via=via)
        log.info("match %s: %s vs %s (%s%s)", m.id, host.name, join.name, origin, ", ranked" if ranked else "")
        if keep:
            # Both games still run and are connected: same path, same ports, no NAT work.
            m.ready = [True, True]
            m.results = rematch_of.results
            m.continued = True
            if rematch_of.relay is not None:
                m.relay, m.relay_id = rematch_of.relay, rematch_of.relay_id
                m.relay_node, m.relay_info = rematch_of.relay_node, rematch_of.relay_info
                rematch_of.relay = None
                if m.relay_node is not None:
                    self.relays.renew(m.relay, self._relay_lease())    # the node's time limit starts again
            self._start_match(m, rematch_of.path)
        elif skip_ready:
            m.ready = [True, True]
            self._start_nat(m)
        else:
            self._timer(m, "ready", self.cfg.ready_timeout, self._ready_timeout, m)
        return m

    def _join_set(self, m, rematch_of, game_set):
        """Put the match into its set: a rematch (or the next game in a room) continues the set it
        belongs to, anything else starts one. A ranked set fixes both characters at its first game."""
        host, join = m.players
        gs = game_set
        if gs is None and rematch_of is not None:
            gs = rematch_of.set
        if gs is None or gs.state != "active" or {id(x) for x in gs.players} != {id(host), id(join)}:
            # A ranked set between two clients that know sets is best of 3 (T5L_RANKED_SET_WINS), rated once;
            # with an older client every game is rated on its own, as before.
            sets_ok = all("sets" in getattr(q.conn, "caps", ()) for q in (host, join))
            gs = GameSet(host, join, m.ranked, self.cfg.ranked_set_wins if sets_ok else 0)
        if gs.locked:
            for q in (host, join):
                gs.picks.setdefault(q.id, q.char)
            m.picks = [gs.picks[host.id], gs.picks[join.id]]
        gs.matches.append(m)
        if gs.rated:
            m.set_number = gs.number
        gs.current = m
        m.set = gs
        host.set = join.set = gs
        if m.room is not None:
            m.room.set = gs

    def _timer(self, m, name, delay, fn, *args):
        old = m.timers.pop(name, None)
        if old:
            old.cancel()
        m.timers[name] = asyncio.get_running_loop().call_later(delay, fn, *args)

    def _cancel_timers(self, m):
        for h in m.timers.values():
            h.cancel()
        m.timers.clear()

    def _get_match(self, p, msg, states=None):
        m = p.match
        if m is None or m.id != msg.get("match"):
            raise LobbyError(proto.E_NOT_FOUND, "no such match")
        if states and m.state not in states:
            raise LobbyError(proto.E_STATE, f"match is {m.state}")
        return m

    async def h_ready(self, conn, msg):
        p = conn.player
        m = self._get_match(p, msg, ("ready",))
        if not msg.get("accept", True):
            self.cancel_match(m, "declined", by=p)
            return None
        m.ready[m.side(p)] = True
        m.players[1 - m.side(p)].send({"t": "opponent_ready", "match": m.id})
        if all(m.ready):
            self._reveal(m)
            self._start_nat(m)

    def _reveal(self, m):
        """Both accepted: the blind players now learn who they play and on which side."""
        for side, p in enumerate(m.players):
            if m.blind[side]:
                p.send({"t": "match_reveal", "match": m.id, "role": "host" if side == 0 else "join", "slot": side,
                        "opponent": m.players[1 - side].brief(), "you": p.brief()})

    def _ready_timeout(self, m):
        if m.state == "ready":
            slow = [p for i, p in enumerate(m.players) if not m.ready[i]]
            self.cancel_match(m, "ready_timeout", by=slow[0] if len(slow) == 1 else None)

    def cancel_match(self, m, reason, by=None):
        """Abort a match that has not started. Players who did nothing wrong go back where they were."""
        if m.state in ("done", "cancelled"):
            return
        culprit = self._setup_culprit(m, reason, by) if m.set is not None and m.set.rated else None
        m.state = "cancelled"
        self._cancel_timers(m)
        self._release(m)
        for side, p in enumerate(m.players):
            if p.match is m:
                p.match = None
                p.status = "idle"
            p.send({"t": "match_cancel", "match": m.id, "reason": reason,
                    "you": by is p})
            if p.room is not None and p.room is m.room:
                p.status = "room"
            elif (m.origin == "queue" and m.queue_mode and by is not None and p is not by and p.online
                  and p.status == "idle"):
                self._enqueue(p, m.queue_mode, m.queue_since[side])   # keeps its place in the queue
        if m.room is not None:
            m.room.match = None
        self.matches.pop(m.id, None)
        gs = m.set
        if gs is not None:
            if gs.current is m:
                gs.current = None
            if gs.state == "active":
                if gs.rated and by is not None and reason in ("opponent_left", "declined"):
                    if by.online:
                        self._end_set(gs, "left", by=by)     # the next game of a ranked set: leaving it
                    # else: `by` lost the lobby while the game was set up -- player_dropped gives the set its
                    # grace period (or ends it for a logout)
                elif culprit is not None:
                    # The next game's connection could not be set up, and the server's evidence names the
                    # side that failed: like leaving the set (a loss once a game has counted). Before, any
                    # failed setup voided the set -- a player behind could block UDP, or not answer the
                    # relay, and walk away from a lost set with no loss.
                    self._count("set_setup_failures")
                    log.info("match %s: %s's side failed the connection setup (%s)", m.id, culprit.name, reason)
                    if culprit.online:
                        self._end_set(gs, "no_connection", by=culprit)
                    # (offline: player_dropped's grace decides, as for leaving)
                else:
                    self._end_set(gs, "cancelled")
        self.counters["matches_cancelled"] += 1
        self.note("match_cancel", match=m.id, reason=reason)
        log.info("match %s cancelled: %s", m.id, reason)
        self.dirty = True

    def _release(self, m, keep_relay=False):
        for tok in m.tokens:
            self.tokens.pop(tok, None)
        if m.relay is not None:
            if keep_relay:
                # The two games still talk through it (menus, result screen); a rematch inside the
                # running games takes it over, otherwise it closes after the rematch window.
                asyncio.get_running_loop().call_later(self.cfg.rematch_window + 5.0, self._close_kept_relay, m)
                return
            self._close_relay(m)

    def _close_kept_relay(self, m):
        if m.relay is not None:
            self._close_relay(m)

    def _close_relay(self, m):
        """Close the match's relay session: ours at once, a regional node's over its control channel."""
        s, m.relay = m.relay, None
        if s is None:
            return
        if getattr(s, "remote", False):
            self.relays.close(s)
            m.relay_stats = s.stats()
        else:
            m.relay_stats = self.udp.close_relay(m.relay_id or m.id)

    # ------------------------------------------------------------------ matches: NAT traversal
    def _start_nat(self, m):
        self._cancel_timers(m)
        m.state = "nat"
        for side, p in enumerate(m.players):
            self.tokens[m.tokens[side]] = (m, side)
            p.send({"t": "nat_begin", "match": m.id, "token": m.tokens[side].hex(), "tag": m.tag.hex(),
                    "side": side, "udp_port": self.udp.port, "udp_port2": self.udp.port2, "nat2": True})
        self._timer(m, "nat", self.cfg.register_timeout, self._nat_timeout, m)
        self.dirty = True

    def _nat_timeout(self, m):
        if m.state != "nat":
            return
        missing = [p for i, p in enumerate(m.players) if m.public_ep[i] is None]
        if missing:
            if len(missing) == 1:
                missing[0].send({"t": "notice", "code": "udp_blocked",
                                 "msg": "your PC's UDP packets did not reach the lobby server; check the firewall"})
            self.cancel_match(m, "udp_unreachable", by=missing[0] if len(missing) == 1 else None)
        else:   # UDP fine, but a client never sent nat_local (crashed or too old)
            silent = [p for i, p in enumerate(m.players) if m.nat_info[i] is None]
            self.cancel_match(m, "no_connection", by=silent[0] if len(silent) == 1 else None)

    def udp_register(self, token, addr, probe):
        """Called by the UDP service for REGISTER / PROBE packets. True -> acknowledge."""
        hit = self.tokens.get(token)
        if hit is None:
            return False
        m, side = hit
        if m.state not in ("nat", "punch", "relay"):
            return False
        if probe:
            m.probe_ep[side] = addr
        else:
            m.public_ep[side] = addr
            self._maybe_punch(m)
        return True

    async def h_nat_local(self, conn, msg):
        p = conn.player
        m = self._get_match(p, msg, ("nat", "punch", "relay"))
        side = m.side(p)
        addrs = []
        loopback_ok = m.public_ep[side] is not None and m.public_ep[side][0].startswith("127.")
        for a in list(msg.get("addrs", []))[:8]:
            ip, port = str(a[0]), int(a[1])
            try:
                ipa = ipaddress.IPv4Address(ip)
            except ValueError:
                continue
            # Only private interface addresses: the peer will send punches there, and a client must
            # not be able to aim them at arbitrary hosts on the internet.
            if 0 < port < 65536 and ipa.is_private and not ipa.is_link_local and (loopback_ok or not ipa.is_loopback):
                addrs.append([ip, port])
        mapped = None
        mp = msg.get("mapped")
        if isinstance(mp, list) and len(mp) == 2:
            try:
                mapped = [str(ipaddress.IPv4Address(str(mp[0]))), int(mp[1])]
            except (ValueError, TypeError):
                mapped = None
            if mapped and not 0 < mapped[1] < 65536:
                mapped = None
        m.nat_info[side] = {"addrs": addrs, "nat": proto.clean_text(msg.get("nat", "unknown"), 16),
                            "port": int(msg.get("port", 0)), "mapped": mapped}
        self._maybe_punch(m)

    # How the punch phase is planned (docs/NETPLAY.md "Getting a direct connection"):
    #  * the NAT type from what the server itself saw: the same socket's endpoint at the main and at the
    #    probe port -- different ports = the NAT maps every destination anew ("symmetric"), and the step
    #    between them says whether its next ports can be guessed (a small step: they count up);
    #  * candidates: the peer's public endpoint (not for a symmetric peer: it only leads to the server), its
    #    router forward (UPnP / NAT-PMP / PCP, only on its own public address), its LAN addresses when both
    #    share a public address, and for a predictable symmetric peer the next ports it will use;
    #  * a "nat2" client gets a plan: start in N ms (both start together: the server's message takes the
    #    two players different times to arrive), punch for punch_timeout seconds, walk the predicted ports;
    #  * an older client gets the same candidates (at most 8 predicted ones) and the window as `timeout`.
    def _nat_view(self, m, side):
        """-> (symmetric, step): step = probe port - main port when both were seen from one address."""
        pub, prb = m.public_ep[side], m.probe_ep[side]
        if pub is not None and prb is not None and prb[0] == pub[0]:
            return prb[1] != pub[1], prb[1] - pub[1]
        return m.nat_info[side]["nat"] == "symmetric", None

    def _predicted(self, m, side):
        """The ports a symmetric NAT will most likely give its next mappings, in the order it gives them."""
        sym, step = self._nat_view(m, side)
        n = self.cfg.predict_ports
        if not sym or not step or abs(step) > 16 or n <= 0:
            return []
        d = 1 if step > 0 else -1
        last = m.probe_ep[side][1]
        return [p for p in (last + d * k for k in range(1, n + 1)) if 1024 <= p <= 65535]

    def _maybe_punch(self, m):
        if m.state != "nat" or None in m.public_ep or None in m.nat_info:
            return
        views = [self._nat_view(m, i) for i in (0, 1)]
        preds = [self._predicted(m, i) for i in (0, 1)]
        new = ["nat2" in getattr(p.conn, "caps", ()) for p in m.players]
        both_sym = views[0][0] and views[1][0]
        if self.cfg.force_relay or (both_sym and not (preds[0] and preds[1])):
            self._start_relay(m, "forced" if self.cfg.force_relay else "both NATs symmetric")
            return
        m.state = "punch"
        m.results = [None, None]
        same_ip = m.public_ep[0][0] == m.public_ep[1][0]
        window = self.cfg.punch_timeout
        # Both start together: the message reaches each player about half its round trip after it leaves.
        one_way = [min(400.0, max(5.0, (getattr(p, "server_rtt", None) or 150.0) / 2.0)) for p in m.players]
        go = max(one_way) + 60.0
        t_go = time.time() + go / 1000.0          # (server clock; a client that synced its clock starts then)
        plan_log = []
        for side, p in enumerate(m.players):
            o = 1 - side
            o_ip, o_port = m.public_ep[o]
            o_sym = views[o][0]
            cands = []
            if same_ip:
                # Same public address: the two PCs share a router (or are one PC). Hairpinning through
                # the router often fails, so offer the peer's own interface addresses first.
                for ip, port in m.nat_info[o]["addrs"]:
                    if [ip, port] != list(m.public_ep[o]):
                        cands.append({"ip": ip, "port": port, "kind": "local"})
            mp = m.nat_info[o].get("mapped")
            if mp and mp[0] == o_ip and mp[1] != o_port:
                cands.append({"ip": o_ip, "port": mp[1], "kind": "mapped"})
            msg = {"t": "nat_punch", "match": m.id, "candidates": cands, "timeout": window}
            if new[side]:
                scan = []
                if o_sym:
                    # the peer's next ports in the order its NAT hands them out, its server endpoint last
                    # (a symmetric pair walks both ranges in step: the n-th new mapping on each side meets)
                    scan = [{"ip": o_ip, "ports": preds[o] + [o_port]}]
                else:
                    cands.append({"ip": o_ip, "port": o_port, "kind": "public"})
                # The first half second's punches only open this side's own NAT (low TTL), so the peer's
                # router never sees a punch from here before its own went out. Two new clients start at
                # the same server time; against an older client, which starts the moment its message
                # arrives, a new one starts the moment its own arrives too (its low-TTL half second then
                # covers an older client that gets its message a little later).
                msg["plan"] = {"start_in": round(go - one_way[side]) if all(new) else 0,
                               "window": window, "interval": 0.05, "slow_start": 0.0 if all(new) else 0.6,
                               "ttl_open": self.cfg.punch_ttl_open, "scan": scan}
                if all(new):
                    msg["plan"]["start_at"] = round(t_go, 3)
                    # each says when it starts (nat_punching -> nat_peer_punching): the low-TTL opening lasts
                    # until the other one has started too, however late its message came
                    msg["plan"]["wait_peer"] = True
            else:
                # (in order: an older client punches its list front to back, so against a symmetric peer the
                # predicted ports come first -- the order that peer's NAT hands its ports out)
                pred = [{"ip": o_ip, "port": port, "kind": "public"} for port in preds[o][:8]]
                public = [{"ip": o_ip, "port": o_port, "kind": "public"}]
                cands.extend(pred + public if o_sym else public + pred)
            plan_log.append({"sym": views[side][0], "step": views[side][1], "pred": len(preds[o]) if o_sym else 0,
                             "mapped": bool(mp), "nat2": new[side]})
            p.send(msg)
        if any(preds):
            self._count("punch_predicted")
        m.nat_plan = plan_log
        self.note("nat_plan", match=m.id, plan=plan_log)
        log.info("match %s: punch %s", m.id, plan_log)
        self._timer(m, "punch", go / 1000.0 + window + 3.0, self._punch_timeout, m)
        self.dirty = True

    def _punch_timeout(self, m):
        if m.state == "punch":
            self._start_relay(m, "punch timeout")

    # Which relay (docs/ONLINE.md "Regional relays"): this server's own, or a relay-only node in another region
    # (T5L_RELAYS). The path through a relay is player A -> relay -> player B, so its round trip is the sum of
    # both players' round trips to that relay: each client with the "relays" cap measures its UDP round trip to
    # every node the server listed and reports it (relay_rtt); its round trip to this server is the one it
    # reports anyway (udp_rtt). The relay with the smallest sum wins (a tie: ours); a node that is down, or
    # that a player could not reach, is not considered, and an older client gets ours, as before. When the
    # chosen node refuses the session (full) or does not answer, the next one is tried, down to ours.
    def _relay_options(self, m):
        """-> [(sum of both players' round trips in ms, RelayNodeRef or None for ours)], best first."""
        return self._pair_relays(*m.players, own=self.cfg.relay)

    def _pair_relays(self, a, b, own=True):
        """The relays two players could be relayed through, best first: [(sum of both round trips in ms, RelayNodeRef
        or None for this server's own)]. Regional ones only when both clients measured them (the "relays" cap) and
        the node is up. The relay choice (_relay_options) and the ping estimate (_est_ping) use it."""
        opts = []
        if own:
            # (an unknown round trip to us counts as far, so that a measured regional relay can win)
            opts.append((sum(p.server_rtt if p.server_rtt is not None else 500.0 for p in (a, b)), 0, None))
        if all("relays" in getattr(p.conn, "caps", ()) for p in (a, b)):
            for n in self.relays.usable():
                ms = [p.relay_rtt.get(n.id) for p in (a, b)]
                if None not in ms:
                    opts.append((sum(ms), 1, n))
        opts.sort(key=lambda o: (o[0], o[1]))
        return [(score, n) for score, _k, n in opts]

    def _relay_lease(self):
        """How long a regional node keeps a session before the lease must be renewed: the match time limit with
        some room for the setup (the node never gives more than its own T5L_RELAY_MAX_SECONDS at a time)."""
        return self.cfg.relay_max_seconds + 120.0 if self.cfg.relay_max_seconds > 0 else self.cfg.match_timeout

    def _start_relay(self, m, why):
        self._cancel_timers(m)
        m.results = [None, None]
        opts = self._relay_options(m)
        if not opts:
            self.cancel_match(m, "no_connection")
            return
        if self._relay_crowded(m):
            log.info("match %s: no relay (address limit)", m.id)
            self.cancel_match(m, "relay_full")
            return
        m.state = "relay"
        m.relay_choice = [(round(score), n.id if n is not None else RELAY_MAIN) for score, n in opts]
        if opts[0][1] is None:
            if self._open_own_relay(m):
                self._relay_ready(m, why)             # (the usual case, and the only one without T5L_RELAYS)
                return
            opts = opts[1:]
            if not opts:
                self.cancel_match(m, "relay_full")
                return
        self._spawn(self._open_relay(m, opts, why))

    def _open_own_relay(self, m):
        m.relay = self.udp.open_relay(m.id, m.tokens)
        m.relay_id = m.id
        m.relay_node = m.relay_info = None
        return m.relay is not None

    async def _open_relay(self, m, opts, why):
        """Try the relays in order; the first that opens a session carries the match."""
        for _score, node in opts:
            if m.state != "relay" or m.relay is not None:
                return
            if node is None:
                if self._open_own_relay(m):
                    self._relay_ready(m, why)
                    return
                continue
            sid = os.urandom(8).hex()
            rr, err = await self.relays.open(node, sid, [proto.new_token(), proto.new_token()], self._relay_lease())
            if m.state != "relay" or m.relay is not None:      # cancelled (a player left) while we asked
                if rr is not None:
                    self.relays.close(rr)
                return
            if rr is None:
                self._count("relay_fallbacks")
                log.warning("match %s: relay %s refused the session (%s); trying the next", m.id, node.id, err)
                continue
            m.relay, m.relay_id, m.relay_node = rr, sid, node
            m.relay_info = node.public()
            self._relay_ready(m, why)
            return
        if m.state == "relay" and m.relay is None:
            self.cancel_match(m, "relay_full")

    def _relay_ready(self, m, why):
        node = m.relay_node
        log.info("match %s: relay %s (%s; sum of round trips: %s)", m.id, node.id if node else RELAY_MAIN, why,
                 ", ".join(f"{rid} {ms} ms" for ms, rid in m.relay_choice or ()))
        self.note("relay_choice", match=m.id, relay=node.id if node else RELAY_MAIN, options=m.relay_choice)
        if node is not None:
            self._count("relay_regional")
        # Two nat2 clients keep the game socket and look for the direct path while the match runs (RelayBridge).
        bridge = self.cfg.relay_upgrade and all("nat2" in getattr(p.conn, "caps", ()) for p in m.players)
        for side, p in enumerate(m.players):
            msg = {"t": "nat_relay", "match": m.id, "udp_port": self.udp.port, "reason": why, "bridge": bridge}
            if node is not None:
                # (only clients with the "relays" cap get here: both measured the node)
                msg.update(relay=m.relay_info, relay_token=m.relay.tokens[side].hex())
            p.send(msg)
        self._timer(m, "relay", self.cfg.relay_timeout, self._relay_timeout, m)

    def _fail_relay(self, m):
        """The relay path did not come up: the match is cancelled (no_connection). In a ranked set the side to
        blame comes from what the relay saw (_setup_culprit); a regional node is asked for that first."""
        s = m.relay
        if m.relay_asking:
            return
        if getattr(s, "remote", False) and m.set is not None and m.set.rated:
            m.relay_asking = True

            async def ask():
                await self.relays.info(s)
                m.relay_asking = False
                if m.state == "relay":
                    self.cancel_match(m, "no_connection")
            self._spawn(ask())
            return
        self.cancel_match(m, "no_connection")

    def _relay_crowded(self, m):
        """T5L_MAX_RELAYS_PER_IP: relay sessions per internet address. Two accounts can always force the
        relay (both claim a symmetric NAT); without a limit a few addresses could hold every relay slot
        for hours as a free tunnel."""
        cap = self.cfg.max_relays_per_ip
        if cap <= 0 or m.rematch_of is not None:
            # (the next game with the same opponent had a relay a minute ago: never refuse it -- a full
            # address would otherwise end a set, and one could fill one's own address to void a set)
            return False
        mine = {self.akey(p.ip) for p in m.players}
        n = {k: 0 for k in mine}
        for o in self.matches.values():
            if o is m or o.relay is None:
                continue
            for k in {self.akey(p.ip) for p in o.players} & mine:
                n[k] += 1
        for o in self.recent.values():          # finished matches whose games still talk through their relay
            if o.relay is not None:
                for k in {self.akey(p.ip) for p in o.players} & mine:
                    n[k] += 1
        return any(v >= cap for v in n.values())

    def _setup_culprit(self, m, reason, by):
        """Whose side made a game's connection setup fail, by the server's own evidence -- None when it
        cannot be told (both sides, a full server, two NATs that cannot punch with the relay off ...).

        Registration: _nat_timeout names the one side whose game socket never reached the server over UDP
        (`udp_unreachable`) or whose launcher never sent its addresses (`no_connection`). Relay: the server
        relays the peer pings it measures with, so it sees which side never bound to the relay, which side
        got the other's pings and never answered one, and which side sent nothing at all."""
        if by is not None and reason in ("udp_unreachable", "no_connection"):
            return by
        s = m.relay if m.state == "relay" else None
        if s is None or reason != "no_connection":
            return None
        bound = [s.ep[i] is not None for i in (0, 1)]
        if bound.count(False) == 1:
            return m.players[bound.index(False)]
        if not all(bound):
            return None
        mute = [s.pings[1 - i] > 0 and s.pongs[i] == 0 for i in (0, 1)]
        if mute.count(True) == 1:
            return m.players[mute.index(True)]
        silent = [s.pkts[i] + s.dropped[i] == 0 for i in (0, 1)]
        if silent.count(True) == 1:
            return m.players[silent.index(True)]
        return None

    def _relay_timeout(self, m):
        if m.state == "relay":
            self._fail_relay(m)

    @staticmethod
    def _peer(peer):
        """The peer endpoint a client measured: an IPv4 address and a port, or None (it goes back to
        that client in match_start, and nothing else is believed)."""
        try:
            ip, port = str(peer[0]), int(peer[1])
            ipaddress.IPv4Address(ip)
        except (TypeError, ValueError, IndexError, KeyError):
            return None
        return [ip, port] if 0 < port < 65536 else None

    def udp_relay_bound(self, match_id, side, addr):
        self.note("relay_bound", match=match_id, side=side)

    async def h_nat_punching(self, conn, msg):
        """A nat2 client has started its planned punch: tell the other one (its low-TTL opening may end)."""
        p = conn.player
        m = p.match if p is not None else None
        if m is None or m.id != msg.get("match") or m.state != "punch":
            return None
        m.players[1 - m.side(p)].send({"t": "nat_peer_punching", "match": m.id})
        return None

    async def h_nat_upgrade(self, conn, msg):
        """A relayed match moved onto the direct path (or back): the clients' RelayBridges found it while the
        games played. For the log and the counters only -- the relay session stays as the way back."""
        p = conn.player
        m = p.match if p is not None else None
        if m is None or m.id != msg.get("match") or m.path != "relay":
            return None
        path = "direct" if msg.get("path") == "direct" else "relay"
        if path == "direct":
            try:
                rtt = max(0.0, min(5000.0, float(msg.get("rtt_ms", 0) or 0)))
            except (TypeError, ValueError):
                rtt = 0.0
            if m.upgraded is None:
                self._count("relay_upgrades")
            m.upgraded = rtt
        if path == "direct":
            log.info("match %s: side %d left the relay for the direct path (%.0f ms)", m.id, m.side(p), m.upgraded)
        else:
            log.info("match %s: side %d went back to the relay", m.id, m.side(p))
        self.note("nat_upgrade", match=m.id, side=m.side(p), path=path)
        return None

    async def h_nat_result(self, conn, msg):
        p = conn.player
        m = self._get_match(p, msg, ("punch", "relay"))
        if msg.get("phase", m.state) != m.state:
            return None      # a late answer from the punch phase after the relay was chosen
        side = m.side(p)
        ok = bool(msg.get("ok"))
        res = {"ok": ok}
        if ok:
            res["rtt"] = max(0.0, min(5000.0, float(msg.get("rtt_ms", 0))))
            res["jitter"] = max(0.0, min(5000.0, float(msg.get("jitter_ms", 0))))
            res["kind"] = proto.clean_text(msg.get("kind", ""), 16)
            res["peer"] = self._peer(msg.get("peer"))
        m.results[side] = res
        if m.state == "punch":
            if all(r and r["ok"] for r in m.results):
                kinds = {r["kind"] for r in m.results}
                self._start_match(m, "lan" if kinds == {"local"} else "direct")
            elif None in m.results:
                pass   # the other side is still punching (or measuring): its result or the deadline decides
            elif m.results[1 - side]["ok"] != ok and not m.punch_retry:
                # One side got through, the other did not (it stopped before the first side's punches
                # arrived, or missed the answers): the path works one way at least. The failed side punches
                # once more -- the addresses it heard from are on its list now.
                m.punch_retry = True
                failed = side if not ok else 1 - side
                m.results[failed] = None
                self._count("punch_retries")
                q = m.players[failed]
                again = {"t": "nat_punch", "match": m.id, "candidates": [], "timeout": 2.5, "retry": True}
                if "nat2" in getattr(q.conn, "caps", ()):
                    again["plan"] = {"start_in": 0, "window": 2.5, "interval": 0.03, "slow_start": 0.0, "scan": []}
                q.send(again)
                self._timer(m, "punch", 2.5 + 3.0, self._punch_timeout, m)
            else:
                self._start_relay(m, "punch failed")
        elif m.state == "relay":
            if all(r and r["ok"] for r in m.results):
                self._start_match(m, "relay")
            elif all(r is not None for r in m.results):
                self._fail_relay(m)
            # else: one side reported (a failure, or success) and the other has not yet: its report or the
            # relay timeout decides -- by then the relay has seen what each side sent (_setup_culprit)

    # ------------------------------------------------------------------ matches: play and results
    def _start_match(self, m, path):
        self._cancel_timers(m)
        m.state = "playing"
        m.path = path
        m.rtt = max(r["rtt"] for r in m.results)
        m.jitter = max(r["jitter"] for r in m.results)
        m.delay = proto.suggest_delay(m.rtt, m.jitter)
        m.started = time.time()
        if m.set is not None:
            m.set.games += 1
        seed = int.from_bytes(m.tag[:4], "big")
        m.pick = self._pick_seconds(m)
        m.chars = list(self.table.resolve(m.picks[0], m.picks[1], fighters.RANDOM, seed)[:2])
        m.stage = self.table.resolve(m.picks[0], m.picks[1], fighters.RANDOM, seed, old_stages=self._old_stages(m))[2]
        for side, p in enumerate(m.players):
            p.status = "playing"
            self._send_match_start(m, side)
        self._timer(m, "match", self.cfg.match_timeout, self._match_timeout, m)
        self._save(m, "playing")
        if m.set is not None and m.set.rated:
            self._save_set(m.set)
        self.dirty = True
        self._count("matches_" + path)
        self.note("match_start", match=m.id, path=path, rtt=m.rtt, delay=m.delay)
        log.info("match %s starts: %s, rtt %.1f ms, delay %d, %s vs %s on %s", m.id, path, m.rtt, m.delay,
                 m.chars[0], m.chars[1], m.stage)

    def _send_match_start(self, m, side):
        p = m.players[side]
        r = m.results[side] or {}
        p.send({"t": "match_start", "match": m.id, "role": "host" if side == 0 else "join", "slot": side,
                "path": m.path, "peer": r.get("peer") if m.path != "relay" else None,
                "relay_port": (m.relay_info["port"] if m.relay_info else self.udp.port) if m.path == "relay" else None,
                # a regional relay: where it is (only clients with the "relays" cap get one)
                **({"relay": m.relay_info} if m.path == "relay" and m.relay_info else {}),
                "rtt_ms": round(m.rtt, 2), "jitter_ms": round(m.jitter, 2), "delay": m.delay,
                # rollback input delay: fixed for ranked (T5_RB_NET_DELAY on both PCs), else each player's setting
                "input_delay": self.cfg.ranked_input_delay if m.ranked and self.cfg.ranked_input_delay >= 0 else None,
                "rounds": self.cfg.rounds, "ranked": m.ranked, "build": m.build_id,
                "opponent": m.players[1 - side].brief(), "seed": int.from_bytes(m.tag[:4], "big"),
                "key": m.key,                          # T5_NET_KEY (the tag above travels in UDP punches)
                "fight": dict({"p1": m.chars[0], "p2": m.chars[1], "stage": m.stage, "rounds": self.cfg.rounds},
                              **({"pick": m.pick} if m.pick else {}), **self._locked_costumes(m)),
                "start_time": int(m.started),          # PS3_FIXED_TIME: the same game clock on both PCs
                "players": [q.brief() for q in m.players],
                "continue": m.continued, "rematch_of": m.rematch_of,
                "min_seconds": self.cfg.min_match_seconds,
                "set": m.set.info() if m.set is not None else None})

    def _old_stages(self, m):
        """May this match's stage be a Tekken 5 one? The server's choice (T5L_OLD_STAGES), and only when both clients
        know those stage keys (cap "old_stages"; an older launcher could not start the fight)."""
        return bool(self.cfg.old_stages) and all("old_stages" in getattr(p.conn, "caps", ()) for p in m.players)

    def _pick_seconds(self, m):
        """In-game select (docs/RANKED.md "Character select in the game"): both players pick on their
        game's own select screen, the characters in `fight` are the fallback. Only when both clients
        can (caps), and in a locked (ranked) set only in the game that fixes its characters."""
        if self.cfg.ingame_pick <= 0:
            return 0
        if not all("ingame_pick" in getattr(p.conn, "caps", ()) for p in m.players):
            return 0
        if not self._picks_in_game(m):
            return 0
        return int(self.cfg.ingame_pick)

    @staticmethod
    def _locked_costumes(m):
        """A locked set's later game after an in-game pick: {"buttons": [P1, P2]}, the costumes (confirm
        buttons) its picking game fought with, so a new connection or a restarted game keeps them too."""
        gs = m.set
        if m.pick or gs is None or not gs.locked or not gs.costumes:
            return {}
        b = [gs.costumes.get(p.id, 0) for p in m.players]
        return {"buttons": b} if any(b) else {}

    @staticmethod
    def _picks_in_game(m):
        """Does this game pick its characters on the select screen? Casual games (no lock) always: a
        rematch goes back to the select screen. A rated set (best of 3) only in game 1 -- a replay of
        game 1 (desync, draw) too, nothing counted yet; games 2 and 3 start by themselves with game 1's
        fighters and costumes. An older per-game ranked set (a client without "sets") in its first game."""
        gs = m.set
        if gs is None or not gs.locked:
            return True
        if gs.rated:
            return m.set_number == 1
        return bool(gs.matches) and gs.matches[0] is m

    def _picked(self, m):
        """The characters the games fought with (in-game select): what both reports say, or the one
        report that says it; None when they disagree or nobody said."""
        if not m.pick:
            return None
        got = [r["chars"] for r in m.reports if r and r.get("chars")]
        if not got or (len(got) == 2 and got[0] != got[1]):
            return None
        return list(got[0])

    @staticmethod
    def _picked_costumes(m):
        """The confirm buttons (costumes) both reports agree on for an in-game pick, or None."""
        got = [r.get("costumes") for r in m.reports if r and r.get("chars")]
        if not got or any(c is None for c in got) or (len(got) == 2 and got[0] != got[1]):
            return None
        return list(got[0])

    async def h_game_started(self, conn, msg):
        self._get_match(conn.player, msg, ("playing",))

    # A result report (`result`):
    #   winner  0 | 1 | null        P1 / P2 / draw (null also when there is no result: quit, crash, disconnect)
    #   score   [p1, p2] rounds     optional
    #   source  game | manual | quit | crash | disconnect
    #           game: read from the game's result file; manual: the player answered; quit: this player
    #           left the match; crash: this player's game died; disconnect: this player's game lost the
    #           opponent (netplay timeout)
    #   desync  frames on which the two games' state hashes differed (netplay's detector), optional
    #   hash    hex state hash at the end of the match (netplay), optional
    #   frames  frames played, optional
    async def h_result(self, conn, msg):
        p = conn.player
        m = self._get_match(p, msg, ("playing",))
        side = m.side(p)
        winner = msg.get("winner")
        if winner not in (0, 1, None):
            raise LobbyError(proto.E_BAD_REQUEST, "winner is 0 (P1), 1 (P2) or null (draw)")
        score = msg.get("score")
        if score is not None:
            if (not isinstance(score, list) or len(score) != 2
                    or not all(isinstance(x, int) and 0 <= x <= 9 for x in score)):
                raise LobbyError(proto.E_BAD_REQUEST, "score is [P1 rounds, P2 rounds]")
        source = msg.get("source") or ("manual" if score is None else "game")
        if source not in REPORT_SOURCES:
            raise LobbyError(proto.E_BAD_REQUEST, "source is " + ", ".join(REPORT_SOURCES))
        if source == "quit":
            winner = 1 - side
        desync = msg.get("desync")
        desync = max(0, min(10 ** 9, int(desync))) if desync is not None else None
        h = msg.get("hash")
        h = str(h)[:32].lower() if h else None
        frames = msg.get("frames")
        frames = max(0, min(10 ** 9, int(frames))) if frames is not None else None
        chars = msg.get("chars")
        if chars is not None:
            # the fighters the game fought with (in-game select): keys, or the game's ids
            ok = isinstance(chars, list) and len(chars) == 2
            keys = []
            for c in chars if ok else ():
                f = self.table.fighter(c) if isinstance(c, str) else (
                    self.table.fighter_by_id(c) if isinstance(c, int) and not isinstance(c, bool) else None)
                if f is None or f.get("boss"):
                    ok = False
                    break
                keys.append(f["key"])
            if not ok:
                raise LobbyError(proto.E_BAD_REQUEST, "chars is [P1 fighter, P2 fighter]")
            chars = keys
        costumes = msg.get("costumes")
        if costumes is not None:
            # their confirm buttons (1-4 = LP, RP, LK, RK; 0 = the default): the costumes a ranked set keeps
            if not (isinstance(costumes, list) and len(costumes) == 2 and all(
                    isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 4 for x in costumes)):
                raise LobbyError(proto.E_BAD_REQUEST, "costumes is [P1 button, P2 button]")
        rep = {"winner": winner, "score": score, "source": source, "desync": desync, "hash": h, "frames": frames,
               "reason": proto.clean_text(msg.get("reason", ""), 32), "at": time.time()}
        if chars is not None:
            rep["chars"] = chars
            if costumes is not None:
                rep["costumes"] = list(costumes)
        if m.reports[side] is not None and m.reports[side]["source"] != "quit":
            return {"t": "result_ack", "match": m.id}        # first report stands
        m.reports[side] = rep
        # A desync report waits for the other side's report like any other (it used to void the match at
        # once): both games compare the same state hashes, so a real desync is reported by both, and one
        # side alone claiming it -- even mid-match -- must not wipe out a match it was losing (_desync_verdict).
        if all(m.reports):
            self._reconcile(m)
        elif "result" not in m.timers:
            self._timer(m, "result", self.cfg.result_timeout, self._result_timeout, m)
            m.players[1 - side].send({"t": "notice", "code": "result_pending", "match": m.id,
                                      "msg": "your opponent reported the result; please report yours"})
        return {"t": "result_ack", "match": m.id}

    async def h_leave_match(self, conn, msg):
        """Quit a match. Before it started: cancel. While playing: this player's report becomes
        `quit` (a loss, or no result at all before the minimum match length)."""
        p = conn.player
        m = self._get_match(p, msg)
        if m.state != "playing":
            self.cancel_match(m, "opponent_left", by=p)
            return None
        side = m.side(p)
        if m.reports[side] is None or m.reports[side]["source"] not in ("game", "manual"):
            m.reports[side] = {"winner": 1 - side, "score": None, "source": "quit", "desync": None, "hash": None,
                               "frames": None, "reason": "quit", "at": time.time()}
        if all(m.reports):
            self._reconcile(m)
        elif m.reports[side]["source"] == "quit":
            # The opponent's game will notice too (their netplay times out); settle without waiting.
            self._settle_quit(m, side)
        # else: this player had already reported the result and leaves now (logs out, blocks the
        # opponent ...): the report stands and the result timer or the opponent's report decides.
        # It used to settle as a quit: a winner who closed the launcher while the opponent kept quiet
        # lost the match.

    def _duration(self, m, rep=None):
        """Seconds from match start to the report (server clock; reports cannot fake it)."""
        end = rep["at"] if rep else time.time()
        return max(0.0, end - (m.started or end))

    @staticmethod
    def _kind(rep):
        s = rep["source"]
        return "result" if s in ("game", "manual") else s

    def _reconcile(self, m):
        """Both players reported: decide (docs/RANKED.md, "Results")."""
        a, b = m.reports
        if self._desync_verdict(m):
            return
        ka, kb = self._kind(a), self._kind(b)
        if ka == kb == "result":
            if a["winner"] is None and b["winner"] is None and a["source"] == b["source"] == "game" and \
                    not any(sum(r["score"] or [0]) for r in (a, b)):
                # Both games say the fight ended without a single round won (left without a winner).
                self._finish(m, "void", None, None, reason="no_result")
                return
            if a["winner"] == b["winner"]:
                score = a["score"] if a["score"] == b["score"] or b["score"] is None else (
                    b["score"] if a["score"] is None else None)
                if self._duration(m, max((a, b), key=lambda r: r["at"])) < self.cfg.min_match_seconds:
                    self._finish(m, "void", None, None, reason="too_short")
                else:
                    self._finish(m, "confirmed", a["winner"], score,
                                 reason=None if score is not None or a["score"] is None else "score_mismatch")
                return
            self._dispute(m)
            return
        for side, k in enumerate((ka, kb)):
            if k == "quit":
                self._settle_quit(m, side)
                return
        for side, k in enumerate((ka, kb)):
            o = m.reports[1 - side]
            if k == "crash":
                if self._kind(o) == "result":
                    # The other game saw the match to its end: that result stands.
                    self._finish(m, "onesided", o["winner"], o["score"], reason="crash")
                else:
                    self._void_blame(m, side, "crash")
                return
        for side, k in enumerate((ka, kb)):
            o = m.reports[1 - side]
            if k == "disconnect" and self._complete(o):
                # The other game played the match to its end (a full score, read from the game): the
                # connection failed after the deciding round -- or this report is a loser's way out.
                # Either way that result stands (it used to be a void: a free one for the loser).
                if self._duration(m, o) < self.cfg.min_match_seconds:
                    self._finish(m, "void", None, None, reason="too_short")
                else:
                    self._finish(m, "onesided", o["winner"], o["score"], reason="disconnect")
                return
        # disconnect + disconnect, or disconnect + an unfinished result: the connection between the two
        # PCs failed. When only one player's lobby connection dropped during the match too, it was that
        # player's connection: a void with blame (a strike), like a crash.
        lost = [i for i in (0, 1) if m.lost_lobby[i]]
        if len(lost) == 1:
            self._void_blame(m, lost[0], "connection")
        else:
            self._finish(m, "void", None, None, reason="connection")

    def _complete(self, rep):
        """A result read from the game with a winner who reached the rounds to win."""
        sc = rep.get("score") if rep is not None else None
        return (rep is not None and rep["source"] == "game" and rep["winner"] in (0, 1) and isinstance(sc, list)
                and len(sc) == 2 and sc[rep["winner"]] >= self.cfg.rounds and not rep.get("desync"))

    def _desync_verdict(self, m):
        """Desync reports (docs/RANKED.md, "Desync claims"). -> True when this decided the match.
        Both games compare the same state hashes, so a real desync is in both reports. A claim the
        other game contradicts -- its report, read from the game, counts 0 mismatching frames -- is not
        taken on trust: equal final state hashes mean both games ended in the same state (the claim
        changes nothing); otherwise the match is void and the claimant blamed (a strike: from
        T5L_STRIKE_LIMIT in 24 h on, a lone claim loses the match, like repeated crashes). A claim
        nobody contradicts (the other report is manual, a crash, ...) voids the match as before."""
        claims = [bool(r.get("desync")) and r["source"] != "quit" for r in m.reports]
        if not any(claims):
            return False
        if all(claims):
            self._finish(m, "void", None, None, reason="desync")
            return True
        c = claims.index(True)
        rc, ro = m.reports[c], m.reports[1 - c]
        if ro["source"] == "game" and ro.get("desync") == 0:
            if rc.get("hash") and rc["hash"] == ro.get("hash"):
                rc["desync_claimed"], rc["desync"] = rc["desync"], 0      # same end state: decide on the results
                return False
            log.warning("match %s: only %s reports a desync; the other game counted none", m.id, m.players[c].name)
            self._void_blame(m, c, "desync_claim")
            return True
        self._finish(m, "void", None, None, reason="desync")
        return True

    def _dispute(self, m):
        """Both reported a result and the winners differ. The netplay layer's state hash decides when
        both sent one: equal hashes = the two games ended in the same state, so one report was changed
        by hand -- the one read from the game wins; different hashes = desync."""
        a, b = m.reports
        log.warning("match %s: results disagree: %s vs %s", m.id, a, b)
        reason = "disputed"
        if a.get("hash") and b.get("hash"):
            if a["hash"] != b["hash"]:
                if a.get("desync") != 0 and b.get("desync") != 0:
                    self._finish(m, "void", None, None, reason="desync")    # no detector counts: as before
                    return
                # Different end states although a game's own detector counted 0 mismatching frames all
                # match long (a real desync shows there): one report is not what its game said.
                # Disputed, not "desync" -- a made-up hash must not turn a forged result into a void
                # nobody is accountable for.
                reason = "hash_mismatch"
            else:
                src = [r["source"] for r in (a, b)]
                if src.count("game") == 1:
                    good = m.reports[src.index("game")]
                    self._finish(m, "resolved", good["winner"], good["score"], reason="disputed")
                    return
        side = self._repeat_disputer(m)
        if side is not None:
            # This account disputed T5L_DISPUTE_LIMIT ranked results in 24 h, its opponent fewer: the
            # pattern decides what one match's evidence cannot.
            self._finish(m, "forfeit", 1 - side, None, reason="dispute_repeat", blame=side)
            return
        self._finish(m, "disputed", None, None, reason=reason)

    def _repeat_disputer(self, m):
        if not m.ranked or self.cfg.dispute_limit <= 0 or any(p.account_id is None for p in m.players):
            return None
        since = time.time() - DAY
        over = [self.store.disputes(p.account_id, since) >= self.cfg.dispute_limit for p in m.players]
        return over.index(True) if over.count(True) == 1 else None

    def _settle_quit(self, m, side):
        """`side` quit the match: a loss -- unless it was too early to be a match at all."""
        rep = m.reports[side]
        o = m.reports[1 - side]
        if o is not None and self._kind(o) == "result" and o["winner"] == side:
            self._finish(m, "onesided", side, o["score"], reason="quit")     # the opponent says the quitter won
            return
        if self._duration(m, rep) < self.cfg.min_match_seconds:
            self._void_blame(m, side, "early_quit")
            return
        score = o["score"] if o is not None and self._kind(o) == "result" else None
        self._finish(m, "forfeit", 1 - side, score, reason="quit", blame=side)

    def _void_blame(self, m, side, reason):
        """No result, caused by `side` (crash, early quit, silence). Counts as a loss once that account
        has caused T5L_STRIKE_LIMIT such voids within 24 hours."""
        p = m.players[side]
        if m.ranked and p.account_id is not None and self.cfg.strike_limit > 0:
            if self.store.strikes(p.account_id, time.time() - DAY) >= self.cfg.strike_limit:
                self._finish(m, "forfeit", 1 - side, None, reason=reason + "_repeat", blame=side)
                return
        self._finish(m, "void", None, None, reason=reason, blame=side)

    def _result_timeout(self, m):
        """Only one player reported within T5L_RESULT_TIMEOUT."""
        if m.state != "playing":
            return
        have = [i for i in (0, 1) if m.reports[i] is not None]
        if len(have) != 1:
            self._finish(m, "void", None, None, reason="no_report")
            return
        r = have[0]
        silent = 1 - r
        rep = m.reports[r]
        k = self._kind(rep)
        if not m.players[silent].online and f"grace{silent}" in m.timers:
            return      # the silent player is reconnecting; the grace timer settles it
        if self._wait_for_silent(m, r):
            return
        if rep.get("desync") and k != "quit":
            self._finish(m, "void", None, None, reason="desync")     # a lone desync report: void, as before
            return
        if k == "quit":
            self._settle_quit(m, r)
        elif k == "result":
            if rep["winner"] == silent or (self.cfg.accept_onesided and not m.players[silent].online):
                # a report against the reporter's own interest, or the opponent left the lobby
                self._finish(m, "onesided", rep["winner"], rep["score"], reason="no_report")
            else:
                self._void_blame(m, silent, "no_report")
        elif k == "crash":
            self._void_blame(m, r, "crash")
        else:                    # disconnect, and the opponent is silent although online
            self._void_blame(m, silent, "no_report")

    def _wait_for_silent(self, m, r):
        """One report is in, the other player is online and silent. That player may still be fighting:
        a report can come early (a modified launcher sending a win, a desync or a lost connection in the
        first minute), and nobody may be blamed -- or, after T5L_STRIKE_LIMIT strikes, lose -- for not
        reporting a match that is still running. So wait until T5L_MAX_MATCH_SECONDS after the start
        (no real match takes longer); a report against the reporter's own interest needs no wait.
        -> True when the decision was put off."""
        silent = 1 - r
        rep = m.reports[r]
        k = self._kind(rep)
        if self.cfg.max_match_seconds <= 0 or not m.players[silent].online or k in ("quit", "crash"):
            return False
        if k == "result" and rep["winner"] == silent and not rep.get("desync"):
            return False
        left = (m.started or 0.0) + self.cfg.max_match_seconds - time.time()
        if left <= 0:
            return False
        self._timer(m, "result", left, self._result_timeout, m)
        m.players[silent].send({"t": "notice", "code": "result_pending", "match": m.id,
                                "msg": "your opponent reported the result; please report yours"})
        return True

    def _grace_expired(self, m, side):
        """`side` lost the lobby mid-match and did not come back in time: the match is lost
        (unless the opponent already said that player won)."""
        m.timers.pop(f"grace{side}", None)
        if m.state != "playing" or m.players[side].online:
            return
        mine = m.reports[side]
        if mine is not None and self._kind(mine) == "result":
            return      # this player reported the result before leaving: the result timer decides, not the absence
        o = m.reports[1 - side]
        if o is not None and self._kind(o) == "result" and o["winner"] == side:
            self._finish(m, "onesided", side, o["score"], reason="disconnect")
            return
        if not m.players[1 - side].online:
            self._finish(m, "void", None, None, reason="both_left")
            return
        if self._duration(m) < self.cfg.min_match_seconds:
            self._void_blame(m, side, "disconnect")
            return
        score = o["score"] if o is not None and self._kind(o) == "result" else None
        self._finish(m, "forfeit", 1 - side, score, reason="disconnect", blame=side)

    def _match_timeout(self, m):
        if m.state == "playing":
            self._finish(m, "void", None, None, reason="timeout")

    def _finish(self, m, status, winner, score, reason=None, blame=None):
        self._cancel_timers(m)
        m.state = "done"
        picked = self._picked(m)
        if picked:
            # In-game select: the history counts what was fought; the game of a locked (ranked) set whose
            # characters were picked in the game (_picks_in_game: a rated set's game 1) fixes them for the
            # rest of the set.
            if picked != m.chars:
                log.info("match %s: picked in the game %s vs %s (launchers: %s vs %s)", m.id, picked[0], picked[1],
                         *(m.chars or ["?", "?"]))
            m.chars = picked
            if m.set is not None and m.set.locked and m.set.state == "active":
                costumes = self._picked_costumes(m) or [0, 0]
                for p, c, b in zip(m.players, picked, costumes):
                    m.set.picks[p.id] = c
                    m.set.costumes[p.id] = b
        # A game of a rated set changes no rating and no record by itself: the set does, once, at its end.
        gs = m.set if m.set is not None and m.set.rated and m.set.state == "active" else None
        counts = status in COUNTED
        changes = None
        if counts and gs is None:
            outcome = ["draw", "draw"] if winner is None else \
                ["win" if winner == 0 else "loss", "win" if winner == 1 else "loss"]
            if m.ranked:
                s0 = 0.5 if winner is None else (1.0 if winner == 0 else 0.0)
                p0, p1 = m.players
                n0, n1 = glicko.match(p0.rating, p1.rating, s0)
                changes = []
                for p, new in ((p0, n0), (p1, n1)):
                    before_rank = p.rank_info()
                    rank_state, event = ranks.after_match(p.rank, new.r, self.rules)
                    ch = {"before": p.rating.as_dict(), "after": new.as_dict(),
                          "delta": round(new.r - p.rating.r, 1), "rank_before": before_rank, "event": event}
                    p.rating = new
                    if not p.guest:
                        p.rank = rank_state
                    ch["rank_after"] = p.rank_info()
                    changes.append(ch)
                for i, p in enumerate(m.players):
                    if p.account_id is not None:
                        self.store.set_rating(p.account_id, p.rating, outcome[i], p.rank)
            else:
                for i, p in enumerate(m.players):
                    if p.account_id is not None:
                        self.store.add_unranked_game(p.account_id, outcome[i])
            for i, p in enumerate(m.players):
                p.record[{"win": 0, "loss": 1, "draw": 2}[outcome[i]]] += 1
        m.final = {"status": status, "winner": winner, "score": score, "reason": reason, "blame": blame}
        self._release(m, keep_relay=m.path == "relay")
        self.matches.pop(m.id, None)
        self._save(m, status, winner, score, changes, reason, blame)
        if counts:
            for p in m.players:
                if p.account_id is not None:
                    p.main = self.store.main_char(p.account_id)
        # Keep it for a rematch offer for a little while.
        m.rematch = [None, None]
        self.recent[m.id] = m
        if m.ranked and m.started:
            self.pair_last[frozenset(self._pair_id(q) for q in m.players)] = time.monotonic()
        if m.set is not None:
            if m.set.current is m:
                m.set.current = None
            m.set.last = m
        asyncio.get_running_loop().call_later(self.cfg.rematch_window, self._expire_recent, m)
        if gs is not None:
            # the set decides what comes next: its next game after a countdown, or its end (and the rating)
            self._set_game_over(gs, m, status, winner, score, reason, blame)
            ch = gs.outcome and gs.outcome["changes"]
            if ch:
                changes = [ch[q.id] for q in m.players]
        set_going = gs is not None and gs.outcome is None
        for side, p in enumerate(m.players):
            if p.match is m:
                p.match = None
                p.status = "room" if p.room is not None else "idle"
            p.send({"t": "match_result", "match": m.id, "status": status, "winner": winner, "score": score,
                    "reason": reason, "blame": None if blame is None else ("you" if blame == side else "opponent"),
                    "ranked": m.ranked, "rating": changes[side] if changes else None, "you": p.public(),
                    "fight": {"p1": m.chars[0], "p2": m.chars[1], "stage": m.stage} if m.chars else None,
                    "set": m.set.info() if m.set is not None else None,
                    "rematch_window": self.cfg.rematch_window if p.online and m.players[1 - side].online
                    and not set_going else 0})
            if not p.online and p.match is None:
                if set_going and self._between_set_games(p):
                    self._set_dropped(gs, p)           # lost the lobby during the game: the set waits a while
                else:
                    self._forget(p)
        if gs is not None and gs.outcome is not None:
            self._announce_set_end(gs, "decided")
        if m.room is not None:
            m.room.match = None
        self._count("results_" + status)
        self.note("match_result", match=m.id, status=status, winner=winner, reason=reason)
        log.info("match %s %s%s: winner %s score %s", m.id, status, f" ({reason})" if reason else "", winner, score)
        self.dirty = True

    def _save(self, m, status, winner=None, score=None, changes=None, reason=None, blame=None):
        try:
            self.store.save_match({
                "id": m.id, "created": m.created, "ended": time.time() if status != "playing" else None,
                "ranked": m.ranked, "p1_name": m.players[0].name, "p2_name": m.players[1].name,
                "p1_account": m.players[0].account_id, "p2_account": m.players[1].account_id,
                "build": m.build_id, "path": m.path, "rtt_ms": m.rtt, "delay": m.delay, "status": status,
                "winner": winner, "score": score, "reports": m.reports, "rating": changes,
                "origin": m.origin, "started": m.started,
                "set_id": m.set.id if m.set is not None and m.set.rated else None, "set_game": m.set_number,
                "duration": round(time.time() - m.started, 1) if m.started and status != "playing" else None,
                "p1_char": m.chars[0] if m.chars else None, "p2_char": m.chars[1] if m.chars else None,
                "stage": m.stage, "reason": reason, "blame": blame})
        except Exception:
            log.exception("saving match %s", m.id)

    # ------------------------------------------------------------------ blocking players
    # A block lives with the blocker: on an account it is stored (blocks table) and follows the
    # account; a guest keeps it for the session only. The blocked side is an account (by id) or, for
    # a guest, a name -- a guest has nothing else to go by, so that block ends with the blocker's
    # session. Blocked pairs are never matched (queues, rooms, challenges, rematches), either way
    # round. Blocking never tells the other player.
    @staticmethod
    def _block_key(p):
        return f"a:{p.account_id}" if p.account_id is not None else "g:" + p.name.lower()

    def _is_blocked(self, a, b):
        """Has either of the two blocked the other?"""
        return self._block_key(b) in a.blocks or self._block_key(a) in b.blocks

    async def h_block(self, conn, msg):
        """Block a player by `name` (an account, or someone online) or by lobby `player` id. A
        running match with that player ends like a quit (docs/RANKED.md); a rematch offer, a
        challenge, a shared room and the set are dropped."""
        p = conn.player
        name = str(msg.get("name") or "").strip()
        target = self.players.get(msg.get("player")) if msg.get("player") else None
        if target is None and name:
            target = self.by_name.get(name.lower())
        if target is not None:
            if target is p:
                raise LobbyError(proto.E_BAD_REQUEST, "you cannot block yourself")
            key, shown, aid, guest = self._block_key(target), target.name, target.account_id, target.guest
        else:
            row = self.store.account(name) if proto.valid_name(name) else None
            if row is None:
                raise LobbyError(proto.E_NOT_FOUND, "no such player")
            if row["id"] == p.account_id:
                raise LobbyError(proto.E_BAD_REQUEST, "you cannot block yourself")
            key, shown, aid, guest = f"a:{row['id']}", row["name"], row["id"], False
        if key not in p.blocks and len(p.blocks) >= self.cfg.max_blocks:
            raise LobbyError(proto.E_NOT_ALLOWED, f"the block list is full ({self.cfg.max_blocks})")
        if key not in p.blocks:
            p.blocks[key] = {"name": shown, "guest": guest, "since": time.time()}
            if p.account_id is not None and aid is not None:
                self.store.add_block(p.account_id, aid, shown)
            self._count("blocks_made")
            log.info("%s blocked %s", p.name, shown)
        left = await self._after_block(p, key)
        if p.account_id is not None and aid is not None:
            self._unfriend(p.account_id, aid, why="block")    # a block ends a friendship (and its requests)
        return {"t": "blocked", "name": shown, "blocks": len(p.blocks), "left_match": left}

    async def _after_block(self, p, key):
        """What a block changes right now. -> the id of the match it ended, or None."""
        left = None
        m = p.match
        if m is not None and m.state != "done" and self._block_key(m.other(p)) == key:
            left = m.id
            if m.state == "playing":
                await self.h_leave_match(_ConnOf(p), {"match": m.id})       # like quitting: a forfeit (docs/RANKED.md)
            else:
                self.cancel_match(m, "opponent_left", by=p)
        for c in [c for c in self.challenges.values()
                  if p in (c.src, c.dst) and self._block_key(c.dst if c.src is p else c.src) == key]:
            self._end_challenge(c, "cancelled")
        gs = p.set
        if gs is not None and gs.state == "active" and gs.current is None and \
                any(self._block_key(q) == key for q in gs.players if q is not p):
            self._decline_recent(gs, p)
            self._end_set(gs, "left", by=p)
        r = p.room
        if r is not None and p.match is None and any(self._block_key(q) == key for q in r.members if q is not p):
            self._leave_room(p)
        return left

    async def h_unblock(self, conn, msg):
        p = conn.player
        name = str(msg.get("name") or "").strip().lower()
        key = next((k for k, b in p.blocks.items() if b["name"].lower() == name), None)
        if key is None:
            raise LobbyError(proto.E_NOT_FOUND, "that player is not on your block list")
        p.blocks.pop(key)
        if p.account_id is not None and key.startswith("a:"):
            self.store.remove_block(p.account_id, int(key[2:]))
        return {"t": "unblocked", "name": name, "blocks": len(p.blocks)}

    async def h_blocks(self, conn, msg):
        rows = [{"name": b["name"], "guest": b["guest"], "since": b["since"]}
                for b in sorted(conn.player.blocks.values(), key=lambda b: b["since"])]
        return {"t": "blocks", "rows": rows}

    # ------------------------------------------------------------------ friends (docs/ONLINE.md "Friends and invites")
    # Accounts only. A request waits for the other side to accept it and runs out after T5L_FRIEND_REQUEST_DAYS.
    # Limits: T5L_FRIEND_REQUESTS_DAY requests per account per 24 h, T5L_FRIEND_PENDING waiting at once (sent by
    # one account, and to one account), T5L_MAX_FRIENDS friends, a declined request again only after
    # T5L_FRIEND_RETRY_DAYS. A block ends a friendship and the requests between the two; a request to someone who
    # blocked you is never shown to them (it looks like one nobody answers). The list and its changes go only to
    # clients with the "friends" cap -- an older launcher gets none of these messages -- and who is online / in a
    # match / offline is pushed with the lobby broadcasts (friend_status).
    @staticmethod
    def _can(p, cap):
        return p is not None and p.conn is not None and not p.conn.closed and cap in p.conn.caps

    @staticmethod
    def _need_account(p):
        if p.account_id is None:
            raise LobbyError(proto.E_NOT_ALLOWED, "guests cannot have friends; create an account (free)")

    def _account_named(self, name):
        row = self.store.account(name) if proto.valid_name(name) else None
        if row is None:
            raise LobbyError(proto.E_NOT_FOUND, "there is no account with that name")
        return row

    def _request_since(self):
        """Requests made before this (unix time) have run out."""
        return time.time() - self.cfg.friend_request_days * DAY

    @staticmethod
    def _presence_of(q):
        """(status, activity) of a player as friends see it: online | in_match | offline, and the lobby status."""
        if q is None or not q.online:
            return "offline", None
        return ("in_match" if q.status in ("match", "playing") else "online"), q.status

    def _invitable(self, viewer, q):
        """Can `viewer` invite friend `q` now? ok | busy | offline | update (an older launcher) | version."""
        if q is None or not q.online:
            return "offline"
        if not self._can(q, "friends"):
            return "update"
        if q.build_id != viewer.build_id:
            return "version"
        if q.status not in ("idle", "queue"):
            return "busy"
        return "ok"

    def _friend_entry(self, viewer, row):
        """One friend in a `friends` list, as `viewer` sees it."""
        q = self.by_account.get(row["id"])
        status, activity = self._presence_of(q)
        d = {"name": row["name"], "status": status, "activity": activity, "since": row["since"],
             "last_seen": row["last_seen"], "invite": self._invitable(viewer, q)}
        if q is not None:
            d["rating"] = round(q.rating.r)
            d.update(q.rank_info())
        else:
            d["rating"] = round(row["rating"])
            d.update(ranks.describe(ranks.RankState(row["tier"], row["ranked_games"], row["tier_since"],
                                                    row["tier_peak"], row["tier_floor"]), row["rd"], self.rules))
        return d

    def _friends_msg(self, p):
        aid = p.account_id
        since = self._request_since()
        sent = self.store.requests_sent_since(aid, time.time() - DAY)
        return {"t": "friends", "friends": [self._friend_entry(p, r) for r in self.store.friends_of(aid)],
                "incoming": [{"name": r["name"], "time": r["time"]} for r in self.store.incoming_requests(aid, since)],
                "outgoing": [{"name": r["name"], "time": r["time"]} for r in self.store.outgoing_requests(aid, since)],
                "max": self.cfg.max_friends, "requests_left": max(0, self.cfg.friend_requests_day - sent)}

    def _send_friends(self, p):
        """The whole list to `p`: after login and whenever it changed (other than who is online)."""
        if p is None or p.account_id is None or not self._can(p, "friends"):
            return
        p.send(self._friends_msg(p))

    def _send_friends_soon(self, *aids):
        for aid in aids:
            asyncio.get_running_loop().call_soon(self._send_friends, self.by_account.get(aid))

    async def h_friends(self, conn, msg):
        """The friends list: {friends [{name, status, activity, invite, rank ...}], incoming, outgoing, max,
        requests_left}."""
        self._need_account(conn.player)
        return self._friends_msg(conn.player)

    async def h_friend_add(self, conn, msg):
        """Ask the account `name` to be friends. -> friend_added {name, state: pending | friends} (friends at
        once when they had asked this player already)."""
        p = conn.player
        self._need_account(p)
        row = self._account_named(str(msg.get("name") or "").strip())
        tid, name = row["id"], row["name"]
        if tid == p.account_id:
            raise LobbyError(proto.E_BAD_REQUEST, "you cannot add yourself")
        if tid in p.friends:
            return {"t": "friend_added", "name": name, "state": "friends"}
        if f"a:{tid}" in p.blocks:
            raise LobbyError(proto.E_NOT_ALLOWED, "you blocked that player; unblock them first")
        since = self._request_since()
        hidden = self.store.is_blocked_by(tid, p.account_id)        # they blocked this player: never shown to them
        if not hidden and self.store.pending_request(tid, p.account_id, since) is not None:
            self._befriend(p.account_id, tid)                       # they asked first: this is the answer
            return {"t": "friend_added", "name": name, "state": "friends"}
        if self.store.pending_request(p.account_id, tid, since) is not None:
            return {"t": "friend_added", "name": name, "state": "pending"}     # (asked already: not counted again)
        if len(p.friends) >= self.cfg.max_friends:
            raise LobbyError(proto.E_NOT_ALLOWED, f"your friends list is full ({self.cfg.max_friends})")
        now = time.time()
        if self.store.requests_sent_since(p.account_id, now - DAY) >= self.cfg.friend_requests_day:
            raise LobbyError(proto.E_RATE, f"you can send {self.cfg.friend_requests_day} friend requests a day; "
                                           "try again tomorrow")
        if len(self.store.outgoing_requests(p.account_id, since)) >= self.cfg.friend_pending:
            raise LobbyError(proto.E_NOT_ALLOWED, f"{self.cfg.friend_pending} of your friend requests are waiting "
                                                  "for an answer; cancel some first")
        declined = self.store.last_declined(p.account_id, tid)
        if declined is not None and now - declined < self.cfg.friend_retry_days * DAY:
            days = max(1, int(-(-(declined + self.cfg.friend_retry_days * DAY - now) // DAY)))
            raise LobbyError(proto.E_NOT_ALLOWED, f"{name} declined your last request; you can ask again in "
                                                  f"{days} day(s)")
        if not hidden and len(self.store.incoming_requests(tid, since)) >= self.cfg.friend_pending:
            raise LobbyError(proto.E_BUSY, "that player has too many friend requests waiting")
        if self.cfg.friend_requests_address > 0 and not self.friend_req_addr.take(conn.akey):
            # (the per-account limits times as many accounts as one address makes: T5L_FRIEND_REQUESTS_ADDRESS a day
            # from one internet address, all its accounts together)
            raise LobbyError(proto.E_RATE, "too many friend requests from this internet address today; try again "
                                           "tomorrow")
        # Asked again within a day of taking a request back: it waits in their list as before, but it does not pop up
        # again -- "add, take back, add ..." put "X wants to be your friend" on their screen 20 times a day.
        quiet = self.store.cancelled_request_since(p.account_id, tid, now - DAY)
        self.store.add_friend_request(p.account_id, tid, now)
        self._count("friend_requests")
        log.info("%s asked %s to be friends%s", p.name, name, " (not shown: blocked)" if hidden else
                 " (again today: not announced)" if quiet else "")
        q = self.by_account.get(tid)
        if not hidden and not quiet and self._can(q, "friends"):
            q.send({"t": "friend_request", "name": p.name, "time": now})
        self._send_friends_soon(p.account_id, *(() if hidden else (tid,)))
        return {"t": "friend_added", "name": name, "state": "pending"}

    def _befriend(self, a, b):
        """Accounts a (who said yes) and b become friends; both lists change, b hears that a accepted."""
        if self.store.friend_count(a) >= self.cfg.max_friends:
            raise LobbyError(proto.E_NOT_ALLOWED, f"your friends list is full ({self.cfg.max_friends})")
        if self.store.friend_count(b) >= self.cfg.max_friends:
            raise LobbyError(proto.E_NOT_ALLOWED, "that player's friends list is full")
        self.store.add_friendship(a, b)
        for x, y in ((a, b), (b, a)):
            q = self.by_account.get(x)
            if q is not None:
                q.friends.add(y)
        self._count("friendships_made")
        row_a = self.store.account_by_id(a)
        qb = self.by_account.get(b)
        if row_a is not None and self._can(qb, "friends"):
            qb.send({"t": "friend_update", "name": row_a["name"], "state": "accepted"})
        log.info("friends: %s and %s", row_a["name"] if row_a else a, qb.name if qb else b)
        self._send_friends_soon(a, b)

    def _unfriend(self, a, b, why):
        """Accounts a and b are no longer friends (a removed b, or blocked b): invites between them end, and for a
        block the requests between them too. -> True when they were friends."""
        was = self.store.remove_friendship(a, b)
        if why == "block":
            self.store.answer_requests(a, b, "cancelled")
            self.store.answer_requests(b, a, "cancelled")
        for x, y in ((a, b), (b, a)):
            q = self.by_account.get(x)
            if q is not None:
                q.friends.discard(y)
        for inv in [i for i in self.invites.values() if {i.src.account_id, i.dst.account_id} == {a, b}]:
            self._end_invite(inv, "cancelled")
        if was:
            self._count("friendships_ended")
            log.info("friends no more (%s): accounts %s and %s", why, a, b)
        self._send_friends_soon(a, b)
        return was

    async def h_friend_answer(self, conn, msg):
        """Accept (`accept`: true) or decline the friend request of `name`."""
        p = conn.player
        self._need_account(p)
        row = self._account_named(str(msg.get("name") or "").strip())
        if self.store.is_blocked_by(p.account_id, row["id"]) or \
                self.store.pending_request(row["id"], p.account_id, self._request_since()) is None:
            raise LobbyError(proto.E_NOT_FOUND, "no friend request from that player")
        if msg.get("accept"):
            self._befriend(p.account_id, row["id"])
            return None
        self.store.answer_requests(row["id"], p.account_id, "declined")
        q = self.by_account.get(row["id"])
        if self._can(q, "friends"):
            q.send({"t": "friend_update", "name": p.name, "state": "declined"})
        self._send_friends_soon(p.account_id, row["id"])
        return None

    async def h_friend_cancel(self, conn, msg):
        """Take back this player's own request to `name`."""
        p = conn.player
        self._need_account(p)
        row = self._account_named(str(msg.get("name") or "").strip())
        if not self.store.answer_requests(p.account_id, row["id"], "cancelled"):
            raise LobbyError(proto.E_NOT_FOUND, "no friend request to that player")
        self._send_friends_soon(p.account_id, row["id"])

    async def h_friend_remove(self, conn, msg):
        """End the friendship with `name` (the other side's list changes; nobody is told more)."""
        p = conn.player
        self._need_account(p)
        row = self._account_named(str(msg.get("name") or "").strip())
        if not self._unfriend(p.account_id, row["id"], why="remove"):
            raise LobbyError(proto.E_NOT_FOUND, "that player is not on your friends list")

    def _friend_relation(self, me, aid):
        """What account `aid` is to `me` on a profile: friends | asked (me -> them) | asks (them -> me) | None."""
        if me is None or me.account_id is None or aid == me.account_id:
            return None
        if aid in me.friends:
            return "friends"
        since = self._request_since()
        if self.store.pending_request(me.account_id, aid, since) is not None:
            return "asked"
        if not self.store.is_blocked_by(me.account_id, aid) and \
                self.store.pending_request(aid, me.account_id, since) is not None:
            return "asks"
        return None

    def _push_presence(self):
        """Who is online, in a match or offline: what changed since the last lobby broadcast goes to each friend
        who is online with the "friends" cap (friend_status {name, status, activity, invite})."""
        now = {}
        for q in self.players.values():
            if q.account_id is not None and q.online:
                st, act = self._presence_of(q)
                now[q.account_id] = (st, act, q.name, q.build_id, self._can(q, "friends"))
        old = self._presence
        changed = [aid for aid, v in now.items() if old.get(aid) != v] + [aid for aid in old if aid not in now]
        self._presence = now
        if not changed:
            return
        watchers = [w for w in self.players.values() if w.friends and self._can(w, "friends")]
        for aid in changed:
            v = now.get(aid)
            q = self.by_account.get(aid) if v else None
            st, act, name = (v[0], v[1], v[2]) if v else ("offline", None, old[aid][2])
            for w in watchers:
                if aid in w.friends:
                    w.send({"t": "friend_status", "name": name, "status": st, "activity": act,
                            "invite": self._invitable(w, q)})

    # ------------------------------------------------------------------ invites (friends)
    async def h_invite(self, conn, msg):
        """Invite a friend who is online: `kind` casual (a casual match; it starts when the friend accepts, no
        ready check) or room (this player's room: the friend joins it and the match starts). The friend gets
        `invited`; the invite waits T5L_INVITE_SECONDS. -> invite_sent {invite, name, kind, expires}."""
        p = conn.player
        self._refuse_draining()
        self._need_account(p)
        kind = msg.get("kind", "casual")
        if kind not in ("casual", "room"):
            raise LobbyError(proto.E_BAD_REQUEST, "kind is casual or room")
        q = self.by_name.get(str(msg.get("name") or "").strip().lower())
        if q is None or q.account_id is None or q.account_id not in p.friends or not q.online:
            raise LobbyError(proto.E_NOT_FOUND, "that friend is not online")
        if not self._can(q, "friends"):
            raise LobbyError(proto.E_NOT_ALLOWED, "that friend's launcher is too old for invites (it needs 1.1.2 or "
                                                  "newer)")
        if q.build_id != p.build_id:
            raise LobbyError(proto.E_VERSION, "that player runs a different build of the game")
        if self._is_blocked(p, q):
            raise LobbyError(proto.E_NOT_ALLOWED, "that player is not available")
        room = None
        if kind == "room":
            room = p.room
            if room is None:
                raise LobbyError(proto.E_STATE, "create a room first, then invite")
            if len(room.members) >= 2 or room.match is not None:
                raise LobbyError(proto.E_FULL, "room is full")
        elif p.status not in ("idle", "queue"):
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        self._set_free(p)
        if q.status not in ("idle", "queue"):
            raise LobbyError(proto.E_BUSY, "that friend is busy right now")
        self._set_free(q, requester=p)
        now = time.monotonic()
        if any(i.src is p for i in self.invites.values()):
            raise LobbyError(proto.E_RATE, "one invite at a time")
        wait = self._retry_left(("invite", p.account_id, q.account_id))
        if wait:
            raise LobbyError(proto.E_RATE, f"your last invite to that friend ended a moment ago; try again in {wait} s")
        if now - p.last_invite < 2.0:           # the last one ended already: only too soon (any friend)
            raise LobbyError(proto.E_RATE, "wait a moment before inviting again")
        if sum(1 for i in self.invites.values() if i.dst is q) >= 3:
            raise LobbyError(proto.E_BUSY, "that player has invites pending")
        p.last_invite = now
        inv = Invite(p, q, kind, room)
        self.invites[inv.id] = inv
        inv.timer = asyncio.get_running_loop().call_later(self.cfg.invite_seconds, self._end_invite, inv, "expired")
        ev = {"t": "invited", "invite": inv.id, "from": p.brief(), "kind": kind, "expires": self.cfg.invite_seconds}
        if room is not None:
            ev["room"] = {"id": room.id, "name": room.name, "ranked": room.ranked}
        q.send(ev)
        self._count("invites_sent")
        log.info("%s invited %s (%s)", p.name, q.name, kind)
        return {"t": "invite_sent", "invite": inv.id, "name": q.name, "kind": kind, "expires": self.cfg.invite_seconds}

    async def h_invite_answer(self, conn, msg):
        """One click: `accept` true starts the casual match (no ready check) or joins the inviter's room (its match
        starts at once -- a ranked room's with the ready check, which says it is ranked); false declines."""
        p = conn.player
        inv = self.invites.get(msg.get("invite"))
        if inv is None or inv.dst is not p:
            raise LobbyError(proto.E_NOT_FOUND, "that invite is over")
        if not msg.get("accept") or self.draining:
            if not self.draining:
                self._retry_later(("invite", inv.src.account_id, p.account_id))     # (no invite spam after a no)
            self._end_invite(inv, "declined")
            self._refuse_draining()
            return None
        src, r = inv.src, inv.room
        gone = (not src.online or src.account_id not in p.friends or self._is_blocked(src, p)
                or src.build_id != p.build_id)
        if inv.kind == "casual":
            gone = gone or src.status not in ("idle", "queue") or src.match is not None
        else:
            gone = gone or r.id not in self.rooms or src not in r.members or len(r.members) >= 2 or r.match is not None
        if gone:
            self._end_invite(inv, "cancelled")
            raise LobbyError(proto.E_BUSY, "the invite is no longer possible")
        if p.status not in ("idle", "queue"):
            raise LobbyError(proto.E_BUSY, f"you are {p.status}")
        if inv.kind == "casual":
            self._abandon_set(src, requester=p)
            self._abandon_set(p)
            self._end_invite(inv, "accepted")
            self._leave_queue(src)
            self._leave_queue(p)
            self._count("invites_accepted")
            self.create_match(src, p, ranked=False, origin="invite")
            return None
        if r.ranked:
            self._check_speed(p)
        self._abandon_set(p)
        self._end_invite(inv, "accepted")
        self._leave_queue(p)
        r.members.append(p)
        p.room, p.status = r, "room"
        self.dirty = True
        self._count("invites_accepted")
        # A ranked room keeps its ready check: the invite only named the room (its name is the owner's free text),
        # and a ranked room's match is rated -- with ranked sets a best of 3 that is lost by leaving it. The ready
        # check says "ranked" and needs a second yes (security review 2).
        asyncio.get_running_loop().call_soon(self._room_start, r, not r.ranked)
        return {"t": "room", "room": r.public()}

    async def h_invite_cancel(self, conn, msg):
        inv = self.invites.get(msg.get("invite"))
        if inv is None or inv.src is not conn.player:
            raise LobbyError(proto.E_NOT_FOUND, "that invite is over")
        self._retry_later(("invite", inv.src.account_id, inv.dst.account_id))     # (no invite / cancel popup loop)
        self._end_invite(inv, "cancelled")

    # A no (or the asker's own cancel) holds back the next invite / challenge between the same two for
    # T5L_INVITE_RETRY_SECONDS: before, a friend (an invite) or anybody (a challenge) could put the question up on the
    # other's screen every 2 s -- with a controller's A as its answer. Keyed by account id (guests: name), so logging
    # in again does not reset it.
    def _retry_later(self, key):
        if self.cfg.invite_retry_seconds <= 0:
            return
        now = time.monotonic()
        if len(self.retry_after) > 4096:
            self.retry_after = {k: v for k, v in self.retry_after.items() if v > now}
        self.retry_after[key] = now + self.cfg.invite_retry_seconds

    def _retry_left(self, key):
        """Whole seconds until the same two may ask again (0: now)."""
        left = self.retry_after.get(key, 0.0) - time.monotonic()
        return math.ceil(left) if left > 0 else 0

    def _end_invite(self, inv, state):
        """accepted | declined | cancelled | expired: both sides are told (invite_update)."""
        if self.invites.pop(inv.id, None) is None:
            return
        if inv.timer is not None:
            inv.timer.cancel()
        for q, other in ((inv.src, inv.dst), (inv.dst, inv.src)):
            if self._can(q, "friends"):
                q.send({"t": "invite_update", "invite": inv.id, "state": state, "name": other.name,
                        "kind": inv.kind})

    # ------------------------------------------------------------------ sets
    def _end_set(self, gs, reason, by=None):
        """A set is over: characters unlock, both players are told. Ratings are not touched -- except for
        a rated set left before it was decided: leaving it is losing it (_set_abort)."""
        if gs.state == "ended":
            return
        if gs.rated and gs.outcome is None:
            self._set_abort(gs, reason, by)
        else:
            self._close_set(gs)
        self._announce_set_end(gs, reason, by)

    def _close_set(self, gs):
        gs.state = "ended"
        if gs.next_timer is not None:
            gs.next_timer.cancel()
            gs.next_timer = None
        for h in gs.grace.values():
            h.cancel()
        gs.grace.clear()
        for q in gs.players:
            if q.set is gs:
                q.set = None

    def _announce_set_end(self, gs, reason, by=None):
        for q in gs.players:
            msg = {"t": "set_end", "set": gs.id, "reason": reason,
                   "by": None if by is None else ("you" if q is by else "opponent")}
            if gs.rated:
                msg.update(gs.view(q))
            q.send(msg)
        self.note("set_end", set=gs.id, reason=reason)
        if gs.rated:
            for q in gs.players:            # a player who lost the lobby waited for the set only
                if not q.online and q.match is None:
                    self._forget(q)

    # ------------------------------------------------------------------ ranked sets (best of 3, rated once)
    # docs/RANKED.md "Ranked sets". A rated set (GameSet.rated) is a ranked set between two clients that
    # announced "sets": first to T5L_RANKED_SET_WINS games. After each game the next one starts by itself
    # (T5L_SET_NEXT_SECONDS countdown, no vote; the same characters, the same sides); the rating changes once,
    # when the set is decided. Leaving or quitting it is losing it (once a game has counted); a crash or a
    # broken connection follows the integrity rules (void, blame); a game without a winner (desync, draw, too
    # short) is played again, at most T5L_SET_REPLAYS times per set, then the set is void.
    SET_REPLAY = ("desync", "too_short", "no_result")
    # A later game of a rated set voided with one of these blames is that player leaving the set (a loss):
    # quitting or vanishing at its start, a desync claim the other game contradicts, no report while
    # online, the only lobby connection that dropped. A crash stays a void (the game has rare real ones).
    SET_LEAVE_REASONS = ("early_quit", "disconnect", "desync_claim", "no_report", "connection")

    def _between_set_games(self, p):
        gs = p.set
        return gs is not None and gs.rated and gs.state == "active" and gs.current is None and p.match is None

    def _set_game_over(self, gs, m, status, winner, score, reason, blame):
        """One game of a rated set ended (`_finish`): count it, then the next game or the end of the set."""
        same = m.players[0] is gs.players[0]                 # (always: the games keep the set's sides)
        win_side = None if winner is None else (winner if same else 1 - winner)
        gs.log.append({"match": m.id, "number": gs.number, "status": status,
                       "winner": win_side if status in COUNTED else None,
                       "score": score if same or not score else score[::-1], "reason": reason})
        if status == "forfeit":
            loser = m.players[blame] if blame is not None else m.players[1 - winner]
            self._set_conclude(gs, "forfeit", winner=gs.other(loser), reason=reason, blame=loser)
        elif status in COUNTED and winner is not None:
            w = m.players[winner]
            gs.wins[w.id] += 1
            if gs.wins[w.id] >= gs.wins_needed:
                self._set_conclude(gs, "confirmed", winner=w)
            else:
                gs.number += 1
                self._set_schedule_next(gs)
        elif (status in COUNTED and winner is None) or (status == "void" and reason in self.SET_REPLAY):
            # no winner: the same game again (a desync: over a new connection, the games reset first)
            if gs.replays >= self.cfg.set_replays:
                self._set_conclude(gs, "void", reason=reason or "draw")
                return
            gs.replays += 1
            self._count("set_replays")
            gs.fresh = gs.fresh or reason == "desync"
            self._set_schedule_next(gs)
        else:
            culprit = m.players[blame] if blame is not None else None
            if culprit is not None and reason in self.SET_LEAVE_REASONS and any(gs.wins.values()):
                # quitting (or vanishing) right at the start of a later game is still leaving the set
                self._set_conclude(gs, "forfeit", winner=gs.other(culprit), reason=reason, blame=culprit)
            else:
                # crash, broken connection, dispute, no reports: the integrity rules, for the whole set
                self._set_conclude(gs, "void", reason=reason or status, blame=culprit)

    def _set_abort(self, gs, reason, by):
        """A rated set ends between two games (or its next game could not start): leaving it -- declining,
        leave_set, logging out, blocking, not coming back to the lobby -- loses it once a game has counted;
        a lag check that found more lag than the ping explains lets a player out for free (h_leave_set)."""
        if reason == "lag" and by is not None:
            self._set_conclude(gs, "void", reason="lag")
        elif by is not None and reason in ("left", "declined", "disconnect", "no_connection") and any(gs.wins.values()):
            self._set_conclude(gs, "forfeit", winner=gs.other(by), reason=reason, blame=by)
        else:
            self._set_conclude(gs, "void", reason=reason)

    def _set_conclude(self, gs, status, winner=None, reason=None, blame=None):
        """The end of a rated set: status confirmed | forfeit (decided, rated: ONE Glicko-2 update per player,
        from the set's result) or void (no rating change). Unlocks the characters; announcing is the caller's."""
        if gs.outcome is not None:
            return
        changes = None
        if status in SET_COUNTED and winner is not None:
            a, b = gs.players
            na, nb = glicko.match(a.rating, b.rating, 1.0 if winner is a else 0.0)
            changes = {}
            for p, new in ((a, na), (b, nb)):
                before_rank = p.rank_info()
                rank_state, event = ranks.after_match(p.rank, new.r, self.rules)
                ch = {"before": p.rating.as_dict(), "after": new.as_dict(), "delta": round(new.r - p.rating.r, 1),
                      "rank_before": before_rank, "event": event}
                p.rating = new
                if not p.guest:
                    p.rank = rank_state
                ch["rank_after"] = p.rank_info()
                changes[p.id] = ch
                won = p is winner
                p.record[0 if won else 1] += 1
                if p.account_id is not None:
                    self.store.set_rating(p.account_id, p.rating, "win" if won else "loss", p.rank)
                    p.main = self.store.main_char(p.account_id)
            self.pair_last[frozenset(self._pair_id(q) for q in gs.players)] = time.monotonic()
        gs.outcome = {"status": status, "winner": winner, "reason": reason, "blame": blame, "changes": changes}
        self._close_set(gs)
        if gs.games > 0:
            self._save_set(gs)
        self._count("sets_" + status)
        self.note("set_result", set=gs.id, status=status, reason=reason,
                  winner=None if winner is None else winner.id, score=gs.score())
        log.info("set %s %s%s: %s %d-%d %s", gs.id, status, f" ({reason})" if reason else "", gs.players[0].name,
                 *gs.score(), gs.players[1].name)
        self.dirty = True

    def _save_set(self, gs):
        a, b = gs.players
        o = gs.outcome or {}
        ch = o.get("changes")
        try:
            self.store.save_set({
                "id": gs.id, "created": gs.created, "ended": time.time() if o else None, "ranked": gs.ranked,
                "p1_name": a.name, "p2_name": b.name, "p1_account": a.account_id, "p2_account": b.account_id,
                "wins_needed": gs.wins_needed, "status": o.get("status", "playing"),
                "winner": None if o.get("winner") is None else gs.side(o["winner"]),
                "score": gs.score(), "games": gs.log, "rating": [ch[a.id], ch[b.id]] if ch else None,
                "reason": o.get("reason"), "blame": None if o.get("blame") is None else gs.side(o["blame"])})
        except Exception:
            log.exception("saving set %s", gs.id)

    def _set_schedule_next(self, gs):
        """The countdown to the set's next game (no vote: it starts by itself)."""
        gs.next_keep = {}
        self._save_set(gs)                              # (the score so far, should the server stop now)
        if gs.next_timer is not None:
            gs.next_timer.cancel()
        gs.next_due = time.monotonic() + self.cfg.set_next_seconds
        gs.next_timer = asyncio.get_running_loop().call_later(self.cfg.set_next_seconds, self._set_next, gs)

    def _set_next(self, gs):
        """The countdown is over: the set's next game, in the running games when both said their game still
        runs connected (set_next keep), else over a new connection. Waits while a player is away from the
        lobby (their grace timer decides)."""
        gs.next_timer = None
        if gs.state != "active" or gs.current is not None:
            return
        a, b = gs.players
        if not (a.online and b.online):
            return
        if a.match is not None or b.match is not None:
            self._end_set(gs, "cancelled")           # (cannot happen: the lobby refuses anything else meanwhile)
            return
        prev = gs.last
        keep = (not gs.fresh and prev is not None and prev.path is not None
                and all(gs.next_keep.get(q.id) for q in (a, b)))
        gs.fresh = False
        room = prev.room if prev is not None and prev.room is not None and prev.room.id in self.rooms else None
        m = self.create_match(a, b, ranked=True, origin="set", room=room, rematch_of=prev, keep=keep, game_set=gs)
        if room is not None and m.state != "cancelled":
            room.match = m

    def _set_dropped(self, gs, p):
        """`p` lost the lobby between two games of a rated set: like mid-match, T5L_RECONNECT_GRACE to return."""
        if p.id in gs.grace:
            return
        gs.grace[p.id] = asyncio.get_running_loop().call_later(self.cfg.reconnect_grace, self._set_grace_expired,
                                                               gs, p)
        gs.other(p).send({"t": "notice", "code": "opponent_dropped", "set": gs.id, "grace": self.cfg.reconnect_grace,
                          "msg": f"{p.name} lost the lobby connection; waiting "
                                 f"{self.cfg.reconnect_grace:.0f} s for them to return"})

    def _set_grace_expired(self, gs, p):
        gs.grace.pop(p.id, None)
        if gs.state != "active" or p.online or gs.current is not None:
            return
        if not gs.other(p).online:
            self._end_set(gs, "both_left")
        else:
            self._end_set(gs, "disconnect", by=p)

    def _set_back(self, gs, p):
        """`p` is back in the lobby (resumed) between two games: the set goes on."""
        h = gs.grace.pop(p.id, None)
        if h is not None:
            h.cancel()
            gs.other(p).send({"t": "notice", "code": "opponent_back", "set": gs.id,
                              "msg": f"{p.name} is back in the lobby"})
        if gs.next_timer is None and gs.current is None:
            asyncio.get_running_loop().call_soon(self._set_next, gs)

    async def h_set_next(self, conn, msg):
        """Between two games of a ranked set: `keep` = this player's game still runs, connected to the
        opponent's (the next game then continues in the running games). Optional: without it the next game
        starts all the same, over a new connection."""
        p = conn.player
        gs = p.set
        if gs is None or not gs.rated or gs.state != "active":
            raise LobbyError(proto.E_STATE, "you are not in a ranked set")
        if gs.current is not None:
            return {"t": "set_next", "set": gs.id, "state": "started", "next": gs.current.id}
        gs.next_keep[p.id] = bool(msg.get("keep"))
        if gs.next_timer is None:
            asyncio.get_running_loop().call_soon(self._set_next, gs)      # (the countdown is over already)
        return {"t": "set_next", "set": gs.id, "state": "waiting",
                "in": round(max(0.0, gs.next_due - time.monotonic()), 1)}

    def _decline_recent(self, gs, by):
        """`by` leaves the set: the last game's rematch offer is withdrawn and the other player told."""
        m = gs.last
        if m is not None and self.recent.pop(m.id, None) is not None and not (gs.rated and gs.outcome is None):
            # (in the middle of a ranked set nothing was offered: set_end tells the other player)
            for q in gs.players:
                if q is not by:
                    q.send({"t": "rematch", "match": m.id, "state": "declined", "from": by.brief()})

    def _abandon_set(self, p, requester=None):
        """`p` starts something new (queue, room, challenge): the old set is over. Not in the middle of a
        ranked set: that has to be left on purpose (leave_set), and leaving it is losing it."""
        self._set_free(p, requester)
        gs = p.set
        if gs is not None and gs.state == "active" and gs.current is None:
            self._decline_recent(gs, p)
            self._end_set(gs, "left", by=p)

    @staticmethod
    def _set_free(p, requester=None):
        """Refuse something new while `p` is in the middle of a ranked set (that has to be left on purpose)."""
        gs = p.set
        if gs is not None and gs.rated and gs.state == "active":
            a, b = gs.wins[p.id], gs.wins[gs.other(p).id]
            raise LobbyError(proto.E_BUSY, f"you are in a ranked set ({a}-{b}); leave it first (that counts as a loss)"
                             if requester is None else "that player is in a ranked set")

    def _expire_recent(self, m):
        self.recent.pop(m.id, None)
        gs = m.set
        if gs is not None and gs.state == "active" and gs.last is m and gs.current is None and not gs.rated:
            self._end_set(gs, "expired")         # (a ranked set waits for its next game, not for a rematch)

    async def h_leave_set(self, conn, msg):
        """Leave the set between two games, without a penalty: no forfeit, no strike, no rating change
        (a game already played keeps its result). `reason: "lag"` says it was the post-game lag check;
        the opponent is told that."""
        p = conn.player
        gs = p.set
        if gs is None or gs.state != "active":
            raise LobbyError(proto.E_STATE, "you are not in a set")
        if gs.current is not None:
            raise LobbyError(proto.E_BUSY, "finish or leave the running match first")
        reason = "lag" if msg.get("reason") == "lag" else "left"
        if reason == "lag" and gs.rated and getattr(gs.last, "lag_verdict", None) != "more_lag":
            reason = "left"     # a ranked set is left for free only after a lag check that found more lag
        self._decline_recent(gs, p)
        self._end_set(gs, reason, by=p)
        if reason == "lag":
            self._count("lag_leaves")
        log.info("%s left set %s (%s)", p.name, gs.id, reason)

    # ------------------------------------------------------------------ post-game lag check
    async def h_lag(self, conn, msg):
        """The game's lag report for a finished match: frames played, ms spent waiting for the other
        side, this PC's own speed. When both reports are in (or T5L_LAG_WAIT seconds after the first)
        both players get `lag_check` (lag.py: ping X should mean Y frames behind, it was Z)."""
        p = conn.player
        mid = msg.get("match")
        m = p.match if p.match is not None and p.match.id == mid else self.recent.get(mid)
        if m is None or m.side(p) is None or m.state != "done":
            raise LobbyError(proto.E_NOT_FOUND, "no such finished match")
        rep = lagmod.clean_report(msg)
        if rep is None:
            raise LobbyError(proto.E_BAD_REQUEST, "lag report: frames (at least %d) and waited_ms are numbers"
                             % lagmod.MIN_FRAMES)
        side = m.side(p)
        if m.lag[side] is not None or m.lag_sent:
            return None
        m.lag[side] = rep
        if all(m.lag):
            self._lag_flush(m)
        elif "lag" not in m.timers:
            self._timer(m, "lag", self.cfg.lag_wait, self._lag_flush, m)

    def _lag_flush(self, m):
        if m.lag_sent:
            return
        m.lag_sent = True
        h = m.timers.pop("lag", None)
        if h:
            h.cancel()
        delay = m.delay if m.delay is not None else 0
        a = lagmod.assess(delay, m.lag, self.cfg.warn_fps, self.cfg.lag_tolerance)
        m.lag_verdict = a["verdict"]
        ping = m.rtt or 0.0
        try:
            self.store.set_match_lag(m.id, {"ping_ms": round(ping, 1), "jitter_ms": round(m.jitter or 0.0, 1),
                                            "path": m.path, "assess": a, "reports": m.lag})
        except Exception:
            log.exception("saving the lag check of %s", m.id)
        self._count("lag_checks")
        if a["verdict"] == "more_lag":
            self._count("lag_more")
        for side, p in enumerate(m.players):
            cause = a["cause"]
            if cause == "pc":
                slow = a["slow"]
                cause = "both_pcs" if len(slow) == 2 else "your_pc" if side in slow else "opponent_pc"
            mine, theirs = m.lag[side], m.lag[1 - side]
            p.send({"t": "lag_check", "match": m.id, "ping_ms": round(ping, 1), "path": m.path,
                    "expected_frames": a["expected"], "observed_frames": a["observed"],
                    "verdict": a["verdict"], "cause": cause,
                    "yours": {"extra_frames": a["extra"][side], "pc_fps": (mine or {}).get("pc_fps")},
                    "opponent": {"extra_frames": a["extra"][1 - side], "pc_fps": (theirs or {}).get("pc_fps")},
                    "text": lagmod.describe(ping, a, side, m.lag), "ranked": m.ranked,
                    "set": m.set.info() if m.set is not None else None,
                    "can_leave": m.set is not None and m.set.state == "active"})
        log.info("match %s lag check: ping %.0f ms, expected %s, observed %s (%s)", m.id, ping, a["expected"],
                 a["observed"], a["verdict"])

    # ------------------------------------------------------------------ server notices (admin tool)
    def _notice_msg(self, n, conn, cleared=False):
        if "notices" in conn.caps:
            return {"t": "server_notice", "id": n["id"], "text": n["text"], "expires": n["expires"],
                    "cleared": cleared}
        if cleared:
            return None
        return {"t": "notice", "code": "server_notice", "msg": n["text"]}      # older clients show it as a notice

    def _send_active_notices(self, p):
        if p.conn is None or p.conn.closed:
            return
        for n in self.notices_by_id.values():
            msg = self._notice_msg(n, p.conn)
            if msg:
                p.conn.send(msg)

    def poll_notices(self):
        """A notice made with `admin notice` is picked up within T5L_ADMIN_POLL seconds and sent to
        every connected client; one that was cleared or has run out is taken down the same way."""
        active = {n["id"]: n for n in self.store.active_notices()}
        changes = [(n, False) for i, n in active.items() if i not in self.notices_by_id]
        changes += [(n, True) for i, n in self.notices_by_id.items() if i not in active]
        self.notices_by_id = active
        for n, cleared in changes:
            for p in self.players.values():
                if p.conn is not None and not p.conn.closed:
                    msg = self._notice_msg(n, p.conn, cleared)
                    if msg:
                        p.conn.send(msg)
            if not cleared:
                self._count("notices_sent")
                log.info("server notice %d: %s", n["id"], n["text"])

    # ------------------------------------------------------------------ lobby broadcast
    # A client that announced caps ["delta"] gets the whole list once (after login, or after asking
    # with "lobby"), then only what changed since the previous broadcast:
    #     {"t":"lobby_delta", "players":[changed or new], "gone":[ids], "rooms":[changed or new],
    #      "rooms_gone":[ids], "queue":{...}}          (fields only when something changed)
    # The client library merges them and hands the UI a complete lobby_state as before. Whole lists
    # for everybody cost O(players^2): 46 Mbit/s at 100 players (lobby/tools/load_test.py).
    LEGACY_PLAYERS, LEGACY_ROOMS = 300, 100

    def _snapshot(self, full=False):
        players = [p.public() for p in self.players.values() if p.online]
        rooms = [r.public() for r in self.rooms.values()]
        if not full:
            players, rooms = players[:self.LEGACY_PLAYERS], rooms[:self.LEGACY_ROOMS]
        return {"t": "lobby_state", "players": players, "rooms": rooms,
                "queue": {m: len(q) for m, q in self.queues.items()}}

    def _broadcast_lobby(self):
        players = {p.id: p.public() for p in self.players.values() if p.online}
        rooms = {r.id: r.public() for r in self.rooms.values()}
        queue = {m: len(q) for m, q in self.queues.items()}
        last = self._last_lobby
        self._last_lobby = {"players": players, "rooms": rooms, "queue": queue}
        delta_data = full_data = legacy_data = None
        if last is not None:
            delta = {"t": "lobby_delta"}
            changed = [v for k, v in players.items() if last["players"].get(k) != v]
            gone = [k for k in last["players"] if k not in players]
            rchanged = [v for k, v in rooms.items() if last["rooms"].get(k) != v]
            rgone = [k for k in last["rooms"] if k not in rooms]
            for key, val in (("players", changed), ("gone", gone), ("rooms", rchanged), ("rooms_gone", rgone)):
                if val:
                    delta[key] = val
            if queue != last["queue"]:
                delta["queue"] = queue
            if len(delta) > 1:
                delta_data = proto.encode(delta)
        for p in self.players.values():
            c = p.conn
            if c is None or c.closed:
                continue
            if "delta" in c.caps:
                if c.need_full or last is None:
                    if full_data is None:
                        full_data = proto.encode({"t": "lobby_state", "players": list(players.values()),
                                                  "rooms": list(rooms.values()), "queue": queue})
                    c.need_full = False
                    c.send_raw(full_data)
                elif delta_data is not None:
                    c.send_raw(delta_data)
            else:
                if legacy_data is None:
                    legacy_data = proto.encode({"t": "lobby_state",
                                                "players": list(players.values())[:self.LEGACY_PLAYERS],
                                                "rooms": list(rooms.values())[:self.LEGACY_ROOMS], "queue": queue})
                c.send_raw(legacy_data)

    async def _tick_lobby(self):
        while True:
            await asyncio.sleep(self.cfg.lobby_interval)
            if not self.dirty:
                continue
            self.dirty = False
            try:
                self._broadcast_lobby()
            except Exception:
                log.exception("lobby broadcast")
            try:
                self._push_presence()
            except Exception:
                log.exception("friends' presence")

    async def _tick_housekeeping(self):
        while True:
            await asyncio.sleep(5.0)
            now = time.monotonic()
            for p in list(self.players.values()):
                if p.conn is None and p.dropped_at and now - p.dropped_at > self.cfg.resume_window:
                    if p.match is not None and p.match.state == "playing":
                        continue   # the result timer settles it
                    self._forget(p)
            for mid in self.udp.expire_idle():
                m = self.matches.get(mid)
                if m is None or m.state != "playing":
                    self.udp.close_relay(mid)
            self._expire_long_relays()
            self.ip_connects.prune()
            self.login_fail.prune()
            self.registrations.prune()
            self.pw_ops.prune()
            self.chat_rate.prune()
            self.bans.prune()
            self.udp.ctl_buckets.prune()
            day = time.monotonic() - 30 * DAY
            for k in [k for k, d in self.good_logins.items() if max(d.values()) < day]:
                del self.good_logins[k]
            self.pair_last = {k: t for k, t in self.pair_last.items() if now - t < self.cfg.pair_cooldown}
            self._relay_samples.append((now, self.udp.stats["relayed_bytes"]))
            del self._relay_samples[:-13]          # one minute of 5 s samples
            try:
                self.reload_tls()
                self._maybe_backup()
                self._maybe_log_status()
                self._db_upkeep()
            except Exception:
                log.exception("housekeeping")

    def _expire_long_relays(self):
        """T5L_RELAY_MAX_SECONDS: no match takes 20 minutes; a relay whose match has run that long is a
        tunnel, not a game (the match then ends like any lost connection)."""
        if self.cfg.relay_max_seconds <= 0:
            return
        now = time.time()
        for m in list(self.matches.values()):
            if m.relay is not None and m.state == "playing" and m.started and now - m.started > self.cfg.relay_max_seconds:
                log.warning("match %s: relay closed after %.0f s", m.id, now - m.started)
                self._count("relays_expired")
                self._close_relay(m)

    def _db_upkeep(self):
        """Hourly: expired remembered logins go, and the WAL file is folded back into the database."""
        if time.monotonic() - self._last_db_upkeep < 3600:
            return
        self._last_db_upkeep = time.monotonic()
        self.store.prune_sessions()
        self.store.expire_friend_requests(time.time() - self.cfg.friend_request_days * DAY)
        self.store.flush()
        if self.cfg.db != ":memory:":
            asyncio.ensure_future(asyncio.to_thread(_checkpoint, self.cfg.db))     # (it may wait for a backup)

    async def _tick_admin(self):
        """Bans made with the admin tool (python -m t5lobby.server.admin) take effect within seconds:
        banned accounts and addresses are kicked."""
        while True:
            await asyncio.sleep(self.cfg.admin_poll)
            try:
                self.poll_notices()
                self.reload_bans()
                self.set_draining(bool(self.store.get_flag("drain")))
                banned = self.store.banned_account_ids()
                for p in list(self.players.values()):
                    if p.conn is None:
                        continue
                    if (p.account_id is not None and p.account_id in banned) or self.ip_banned(p.conn.ip):
                        log.info("kicking %r (%s): banned", p.name, p.conn.ip)
                        self.kick(p, "banned from this server")
                for c in [c for c in self.conns if c.player is None and self.ip_banned(c.ip)]:
                    c.close()
            except Exception:
                log.exception("admin poll")

    def _maybe_backup(self):
        if not self.cfg.backup_dir or self.cfg.db == ":memory:" or self.cfg.backup_hours <= 0:
            return
        if time.time() - self._last_backup < self.cfg.backup_hours * 3600:
            return
        self._last_backup = time.time()
        from .backup import backup_db

        async def run():
            try:
                self.store.flush()
                path = await asyncio.to_thread(backup_db, self.cfg.db, self.cfg.backup_dir, self.cfg.backup_keep)
                log.info("database backed up to %s", path)
            except Exception as e:     # noqa: BLE001 -- logged; the next attempt is in backup_hours
                log.error("database backup failed: %s", e)
        asyncio.ensure_future(run())

    def _maybe_log_status(self):
        every = self.cfg.status_log_minutes * 60
        if every <= 0 or time.monotonic() - self._last_status_log < every:
            return
        self._last_status_log = time.monotonic()
        st = self.status()
        log.info("status: %d online (%d guests), %d rooms, %d queued, %d matches running, %d relayed, "
                 "relay %.0f kbit/s, %s matches in 24 h", st["players"]["online"], st["players"]["guests"],
                 st["rooms"], sum(st["queue"].values()), st["matches"]["running"], st["relay"]["sessions"],
                 st["relay"]["kbit_s"], st["db"].get("matches_24h", "?"))
        for r in st["relays"]:
            log.info("status: relay %s %s, %s sessions, %s kbit/s, last answer %s s ago", r["id"],
                     "up" if r["alive"] else "DOWN", r["sessions"], r["kbit_s"], r["last_seen_s"])

    def relay_kbit_s(self):
        """Relay throughput (bytes forwarded, both directions together) over the last minute."""
        s = self._relay_samples
        if len(s) < 2 or s[-1][0] <= s[0][0]:
            return 0.0
        return 8 * (s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0]) / 1000.0

    def status(self):
        """Everything the status endpoint and the admin tool show. No names, no addresses."""
        from .status import cert_info, process_info
        online = [p for p in self.players.values() if p.online]
        by_state = {}
        for m in self.matches.values():
            by_state[m.state] = by_state.get(m.state, 0) + 1
        try:
            db = self.store.stats()
        except Exception as e:     # noqa: BLE001
            db = {"error": str(e)}
        return {
            "server": SERVER_NAME, "proto": proto.PROTO_VERSION, "time": round(time.time()),
            "uptime_s": round(time.time() - self.started),
            "players": {"online": len(online), "guests": sum(1 for p in online if p.guest),
                        "accounts": sum(1 for p in online if not p.guest),
                        "playing": sum(1 for p in online if p.status == "playing"),
                        "in_queue": sum(1 for p in online if p.status == "queue"),
                        "resumable": len(self.players) - len(online)},
            "connections": len(self.conns),
            "connections_prelogin": sum(1 for c in self.conns if c.player is None),
            "tls_handshakes": self.handshakes, "password_checks_waiting": self.pw_waiting,
            "draining": self.draining,
            "rooms": len(self.rooms),
            "queue": {m: len(q) for m, q in self.queues.items()},
            "matches": {"running": sum(by_state.values()), "by_state": by_state},
            "relay": {"sessions": len(self.udp.relays), "max": self.cfg.max_relays,
                      "kbit_s": round(self.relay_kbit_s(), 1),
                      "bytes_total": self.udp.stats["relayed_bytes"], "packets_total": self.udp.stats["relayed"],
                      "dropped_total": self.udp.stats["dropped"], "force_relay": self.cfg.force_relay},
            # regional relay nodes (T5L_RELAYS): up or down, sessions, kbit/s, last answer
            "relays": self.relays.status(), "relays_error": self.relays.error,
            "counters": dict(self.counters),
            "db": db,
            "tls": cert_info(self.cfg.tls_cert) if self.sslctx else None,
            "notices": len(self.notices_by_id),
            "config": {"accounts": self.cfg.accounts, "guests": self.cfg.guests,
                       "max_clients": self.cfg.max_clients, "pinned_builds": len(self.cfg.builds)},
            "process": process_info(),
        }
