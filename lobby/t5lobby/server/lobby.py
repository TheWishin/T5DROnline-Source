"""The lobby server: control connections, players, rooms, queues, challenges and matches.

Single-threaded asyncio; all state lives on the event loop thread.

Match life cycle (states):
    ready      both players must accept (skipped for an accepted challenge or a rematch)
    nat        each client binds its game socket and registers it with the server over UDP
    punch      clients punch holes toward each other's candidate endpoints and measure RTT
    relay      punching failed (or both NATs are symmetric): both bind to the relay
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
"""
import asyncio
import ipaddress
import logging
import os
import ssl
import time

from .. import __version__, fighters, lag as lagmod, proto, ranks, rating as glicko
from ..buildid import BuildInfo
from ..proto import LobbyError
from .config import Config
from .ratelimit import BanList, KeyedBuckets, TokenBucket
from .store import COUNTED, SET_COUNTED, Store, check_password, hash_password
from .udp import UdpService

log = logging.getLogger("t5lobby")

SERVER_NAME = "t5lobby/0.2"
CAPS = frozenset(("delta", "blind_ready", "notices", "sets"))   # optional protocol features a client may announce in hello
QUEUE_MODES = ("quick", "ranked")
# What this server supports beyond protocol 1's base (the client checks before using them).
FEATURES = ["ranks", "sessions", "recovery", "passwd", "profile", "history", "chars", "integrity", "rematch",
            "blind_ready", "blocks", "strict", "set_lock", "lag_check", "notices", "ranked_sets"]
REPORT_SOURCES = ("game", "manual", "quit", "crash", "disconnect")
DAY = 86400.0


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
        self.picks = [host.char, join.char]  # characters as picked (may be "random")
        self.chars = None                    # resolved at match start
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
            log.warning("%s: %d bytes unread, dropping connection", self.ip, self.pending)
            self.close()
            return
        try:
            self.out.put_nowait(data)
            self.pending += len(data)
        except asyncio.QueueFull:
            log.warning("%s: output queue full, dropping connection", self.ip)
            self.close()

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
            await asyncio.gather(wtask, return_exceptions=True)
            self.srv.conn_closed(self)


# =============================================================================== server

class LobbyServer:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config.from_env()
        self.store = Store(self.cfg.db)
        self.udp = UdpService(self, self.cfg)
        self.conns = set()
        self.players = {}          # id -> Player (online or resumable)
        self.by_name = {}          # lower name -> Player
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
            "set_replays"), 0)
        self._last_lobby = None    # the last lobby list sent: deltas are computed against it
        self.ip_bans = []          # [(ip_network, until)] from the database (the admin tool writes them)
        self.name_block = self._load_blocklist(self.cfg.name_blocklist)
        self.sslctx = None
        self._tls_mtime = None
        self.status_http = None
        self._last_backup = 0.0
        self._last_status_log = time.monotonic()
        self._relay_samples = []   # (monotonic, bytes relayed so far) for the relay bandwidth

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
        n = self.store.void_open_sets("server_restart")
        if n:
            # A running ranked set lives in this process only: one the last server left open is void (its games
            # changed no rating, so nothing is undone). docs/RANKED.md "Ranked sets", server restart.
            log.info("%d ranked set(s) left open by the last server run: void (server_restart)", n)
        self.reload_bans()
        self.notices_by_id = {n["id"]: n for n in self.store.active_notices()}
        self.tcp = await asyncio.start_server(self._accept, self.cfg.host, self.cfg.port, ssl=sslctx,
                                              limit=proto.MAX_LINE + 2)
        self.port = self.tcp.sockets[0].getsockname()[1]
        await self.udp.start(loop)
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

    async def _accept(self, reader, writer):
        conn = Conn(self, reader, writer)
        ip = conn.ip
        if self.ip_banned(ip):
            self.counters["refused_connections"] += 1
            writer.write(proto.encode({"t": "error", "code": proto.E_NOT_ALLOWED, "msg": "banned from this server"}))
            writer.close()
            return
        if self.bans.banned(ip) or not self.ip_connects.take(ip):
            self.counters["refused_connections"] += 1
            writer.write(proto.encode({"t": "error", "code": proto.E_RATE, "msg": "too many connections"}))
            writer.close()
            return
        if len(self.conns) >= self.cfg.max_clients or self.ip_conns.get(ip, 0) >= self.cfg.max_per_ip:
            self.counters["refused_connections"] += 1
            writer.write(proto.encode({"t": "error", "code": proto.E_FULL, "msg": "server full"}))
            writer.close()
            return
        self.counters["connections"] += 1
        self.conns.add(conn)
        self.ip_conns[ip] = self.ip_conns.get(ip, 0) + 1
        await conn.run()

    def conn_closed(self, conn):
        if conn not in self.conns:
            return
        self.conns.discard(conn)
        n = self.ip_conns.get(conn.ip, 1) - 1
        if n <= 0:
            self.ip_conns.pop(conn.ip, None)
        else:
            self.ip_conns[conn.ip] = n
        p = conn.player
        if p is not None and p.conn is conn:
            self.player_dropped(p)

    # ------------------------------------------------------------------ dispatch
    PRE_LOGIN = ("hello", "login", "ping", "logout", "recover")

    async def dispatch(self, conn, line):
        """Handle one line; False closes the connection."""
        if not conn.bucket.take():
            if not conn.violations.take():
                self.bans.ban(conn.ip, 60)
                conn.send({"t": "error", "code": proto.E_RATE, "msg": "flooding: disconnected"})
                return False
            conn.send({"t": "error", "code": proto.E_RATE, "msg": "slow down"})
            return True
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
            reply = await fn(conn, msg)
        except LobbyError as e:
            conn.send({"t": "error", "code": e.code, "msg": e.msg, "re": rid})
            if e.code in (proto.E_PROTO, proto.E_VERSION) and t == "hello":
                return False
            return True
        except (KeyError, TypeError, ValueError) as e:
            conn.errors += 1
            conn.send({"t": "error", "code": proto.E_BAD_REQUEST, "msg": f"bad field: {e}", "re": rid})
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
        conn.release = str(build.get("release", ""))[:32]
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
                "set_wins": self.cfg.ranked_set_wins if "sets" in conn.caps else 1}

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
            key_ip = "ip:" + conn.ip
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
            elif mode in ("account", "register"):
                if not self.cfg.accounts:
                    raise LobbyError(proto.E_NOT_ALLOWED, "this server has no accounts")
                pw = msg.get("password", "")
                self._check_pw_rules(pw)
                key_ip, key_name = "ip:" + conn.ip, "name:" + name.lower()
                if not (self.login_fail.peek_ok(key_ip) and self.login_fail.peek_ok(key_name)):
                    raise LobbyError(proto.E_RATE, "too many failed logins; wait a few minutes")
                if mode == "register":
                    if self.by_name.get(name.lower()) is not None:
                        raise LobbyError(proto.E_NAME_TAKEN, "someone with that name is online")
                    if not self.registrations.take(conn.ip):
                        raise LobbyError(proto.E_RATE, "too many new accounts from this address")
                    pw_hash = await asyncio.to_thread(hash_password, pw, self.cfg.scrypt_n)
                    account = self.store.create_account(name, pw_hash)
                    if account is None:
                        raise LobbyError(proto.E_NAME_TAKEN, "that name is taken")
                    codes = self.store.issue_recovery_codes(account["id"], self.cfg.recovery_codes)
                    self.counters["accounts_created"] += 1
                    log.info("account %r created from %s", name, conn.ip)
                else:
                    account = self.store.account(name)
                    ok = account is not None and await asyncio.to_thread(check_password, pw, account["pw"])
                    if not ok:
                        self.login_fail.take(key_ip)
                        self.login_fail.take(key_name)
                        self.counters["login_failures"] += 1
                        raise LobbyError(proto.E_AUTH, "wrong name or password")
                    self._refuse_banned(account)
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
        conn.player = p
        self.players[p.id] = p
        self.by_name[name.lower()] = p
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
        row = self.store.account_by_id(p.account_id)
        if not await asyncio.to_thread(check_password, str(msg.get("old", "")), row["pw"]):
            self.login_fail.take(key)
            raise LobbyError(proto.E_AUTH, "the current password is wrong")
        self.store.set_password(p.account_id, await asyncio.to_thread(hash_password, new, self.cfg.scrypt_n))
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
        key_ip, key_name = "ip:" + conn.ip, "name:" + name.lower()
        if not (self.login_fail.peek_ok(key_ip) and self.login_fail.peek_ok(key_name)):
            raise LobbyError(proto.E_RATE, "too many failed attempts; wait a few minutes")
        account = self.store.account(name) if proto.valid_name(name) else None
        if account is None or not self.store.use_recovery_code(account["id"], str(msg.get("code", ""))):
            self.login_fail.take(key_ip)
            self.login_fail.take(key_name)
            raise LobbyError(proto.E_AUTH, "wrong name or recovery code (each code works once)")
        self.store.set_password(account["id"], await asyncio.to_thread(hash_password, new, self.cfg.scrypt_n))
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
        row = self.store.account_by_id(p.account_id)
        if not await asyncio.to_thread(check_password, str(msg.get("password", "")), row["pw"]):
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
        rows = self.store.leaderboard(max(1, min(100, int(msg.get("limit", 20)))), max(0, int(msg.get("offset", 0))))
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
        if not self.chat_rate.take(conn.player.id):
            raise LobbyError(proto.E_RATE, "chat: slow down")
        text = "".join(ch for ch in text[:200] if ch.isprintable())
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
        m = p.match
        if m is not None and m.state not in ("playing", "done"):
            self.cancel_match(m, "opponent_left", by=p)
        elif m is not None and m.state == "playing":
            # Lost the lobby mid-match: the launcher reconnects on its own. Not back within the
            # grace period -> the match is lost (docs/RANKED.md, disconnects).
            side = m.side(p)
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
        self.sessions.pop(p.token, None)
        self._leave_queue(p)
        self._leave_room(p)
        if p.set is not None and p.set.state == "active" and p.set.current is None:
            self._decline_recent(p.set, p)
            self._end_set(p.set, "left", by=p)

    # ------------------------------------------------------------------ queues
    async def h_queue(self, conn, msg):
        p = conn.player
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
             "member_since": row["created"], "last_seen": row["last_seen"],
             "chars": self.store.char_usage(aid), "main": self.store.main_char(aid),
             "voids_24h": self.store.strikes(aid, time.time() - DAY),
             "history": self.store.history(aid, max(0, min(50, n_history))),
             "sets": self.store.set_history(aid, max(0, min(20, n_history)))}
        d.update(ranks.describe(rank, rt.rd, self.rules))
        if online is not None:
            d["status"] = online.status
        d["self"] = me is not None and me.account_id == aid
        if d["self"]:
            d["recovery_codes_left"] = self.store.recovery_left(aid)
        return d

    async def h_history(self, conn, msg):
        name = str(msg.get("name") or conn.player.name)
        row = self.store.account(name) if proto.valid_name(name) else None
        if row is None:
            raise LobbyError(proto.E_NOT_FOUND, "history is kept for accounts only")
        limit = max(1, min(100, int(msg.get("limit", 20))))
        return {"t": "history", "name": row["name"],
                "rows": self.store.history(row["id"], limit, max(0, int(msg.get("offset", 0))))}

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

    @staticmethod
    def _est_ping(a, b):
        """Ping between two players as the server can tell before they are connected: each one's
        UDP round trip to the server, added (the relay path; a direct path is usually shorter).
        The real peer-to-peer ping is measured after both accepted (nat.py, `rtt_ms` in match_start)."""
        ra = a.server_rtt if a.server_rtt is not None else 50.0
        rb = b.server_rtt if b.server_rtt is not None else 50.0
        return ra + rb

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
                    ping = self._est_ping(a, b)
                    if mode == "ranked":
                        if self._cooling(a, b, time.monotonic()):
                            continue                     # just played each other: not again within T5L_PAIR_COOLDOWN
                        wb = now - b.queue_since
                        window = min(self._rating_window(wa), self._rating_window(wb))
                        limit = min(self._ping_limit(wa), self._ping_limit(wb))
                        dr = abs(a.rating.r - b.rating.r)
                        if dr > window or ping > limit:
                            continue
                        if (a.strict or b.strict) and dr > self.cfg.strict_range:
                            continue                     # strict matchmaking: +-T5L_STRICT_RANGE rating points, however long it takes
                        score = dr / window + ping / limit
                    else:
                        score = ping
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

    @staticmethod
    def _ping_limit(waited):
        return min(400.0, 80.0 + 10.0 * waited)

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
        name = str(msg.get("name") or f"{p.name}'s room")[:32]
        name = "".join(ch for ch in name if ch.isprintable())
        r = Room(p, name, ranked)
        self.rooms[r.id] = r
        p.room, p.status = r, "room"
        self.dirty = True
        return {"t": "room", "room": r.public()}

    async def h_room_join(self, conn, msg):
        p = conn.player
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

    def _room_start(self, r):
        if r.id not in self.rooms or len(r.members) != 2 or r.match is not None:
            return
        if any(not q.online or q.match is not None for q in r.members):
            return
        gs = r.set if r.set is not None and r.set.state == "active" and \
            {id(q) for q in r.set.players} == {id(q) for q in r.members} else None
        r.match = self.create_match(r.members[0], r.members[1], ranked=r.ranked, origin="room", room=r,
                                    game_set=gs)

    def _leave_room(self, p):
        r = p.room
        if r is None:
            return
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
        if not msg.get("accept"):
            self._end_challenge(c, "declined")
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
        self._end_challenge(c, "cancelled")

    def _end_challenge(self, c, state):
        if self.challenges.pop(c.id, None) is None:
            return
        if c.timer:
            c.timer.cancel()
        for q in (c.src, c.dst):
            q.send({"t": "challenge_update", "challenge": c.id, "state": state})

    # ------------------------------------------------------------------ matches: setup
    def create_match(self, host, join, ranked, origin, room=None, rematch_of=None, keep=False, game_set=None):
        note = None
        going_on = game_set or (rematch_of.set if rematch_of is not None else None)
        if going_on is not None and going_on.rated and going_on.state == "active" and                 {id(x) for x in going_on.players} == {id(host), id(join)}:
            pass                     # the next game of a rated set: the set was ranked (and capped) when it began
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
        self._join_set(m, rematch_of, game_set)
        skip_ready = origin in ("challenge", "rematch", "set")
        est = self._est_ping(host, join)
        ping = {"ms": round(est), "kind": "estimate", "known": host.server_rtt is not None and join.server_rtt is not None}
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
                p.send({"t": "notice", "code": "pair_cap", "match": m.id, "msg": note})
        self._speed_notice(m)
        self.dirty = True
        self.counters["matches_found"] += 1
        self.note("match_found", match=m.id, origin=origin)
        log.info("match %s: %s vs %s (%s%s)", m.id, host.name, join.name, origin, ", ranked" if ranked else "")
        if keep:
            # Both games still run and are connected: same path, same ports, no NAT work.
            m.ready = [True, True]
            m.results = rematch_of.results
            m.continued = True
            if rematch_of.relay is not None:
                m.relay, m.relay_id = rematch_of.relay, rematch_of.relay_id
                rematch_of.relay = None
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
            m.relay_stats = self.udp.close_relay(m.relay_id or m.id)
            m.relay = None

    def _close_kept_relay(self, m):
        if m.relay is not None:
            m.relay_stats = self.udp.close_relay(m.relay_id or m.id)
            m.relay = None

    # ------------------------------------------------------------------ matches: NAT traversal
    def _start_nat(self, m):
        self._cancel_timers(m)
        m.state = "nat"
        for side, p in enumerate(m.players):
            self.tokens[m.tokens[side]] = (m, side)
            p.send({"t": "nat_begin", "match": m.id, "token": m.tokens[side].hex(), "tag": m.tag.hex(),
                    "side": side, "udp_port": self.udp.port, "udp_port2": self.udp.port2})
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
        m.nat_info[side] = {"addrs": addrs, "nat": str(msg.get("nat", "unknown"))[:16],
                            "port": int(msg.get("port", 0))}
        self._maybe_punch(m)

    def _maybe_punch(self, m):
        if m.state != "nat" or None in m.public_ep or None in m.nat_info:
            return
        nats = [i["nat"] for i in m.nat_info]
        if self.cfg.force_relay or nats == ["symmetric", "symmetric"]:
            self._start_relay(m, "forced" if self.cfg.force_relay else "both NATs symmetric")
            return
        m.state = "punch"
        same_ip = m.public_ep[0][0] == m.public_ep[1][0]
        for side, p in enumerate(m.players):
            o = 1 - side
            cands = [{"ip": m.public_ep[o][0], "port": m.public_ep[o][1], "kind": "public"}]
            if same_ip:
                # Same public address: the two PCs share a router (or are one PC). Hairpinning through
                # the router often fails, so offer the peer's own interface addresses first.
                for ip, port in m.nat_info[o]["addrs"]:
                    if [ip, port] != list(m.public_ep[o]):
                        cands.insert(0, {"ip": ip, "port": port, "kind": "local"})
            p.send({"t": "nat_punch", "match": m.id, "candidates": cands, "timeout": self.cfg.punch_timeout})
        self._timer(m, "punch", self.cfg.punch_timeout + 3.0, self._punch_timeout, m)
        self.dirty = True

    def _punch_timeout(self, m):
        if m.state == "punch":
            self._start_relay(m, "punch timeout")

    def _start_relay(self, m, why):
        self._cancel_timers(m)
        if not self.cfg.relay:
            self.cancel_match(m, "no_connection")
            return
        m.results = [None, None]
        m.relay = self.udp.open_relay(m.id, m.tokens)
        m.relay_id = m.id
        if m.relay is None:
            self.cancel_match(m, "relay_full")
            return
        m.state = "relay"
        log.info("match %s: relay (%s)", m.id, why)
        for side, p in enumerate(m.players):
            p.send({"t": "nat_relay", "match": m.id, "udp_port": self.udp.port, "reason": why})
        self._timer(m, "relay", self.cfg.relay_timeout, self._relay_timeout, m)

    def _relay_timeout(self, m):
        if m.state == "relay":
            self.cancel_match(m, "no_connection")

    def udp_relay_bound(self, match_id, side, addr):
        self.note("relay_bound", match=match_id, side=side)

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
            res["kind"] = str(msg.get("kind", ""))[:16]
            peer = msg.get("peer")
            res["peer"] = [str(peer[0]), int(peer[1])] if peer else None
        m.results[side] = res
        if m.state == "punch":
            if not ok:
                self._start_relay(m, "punch failed")
            elif all(r and r["ok"] for r in m.results):
                kinds = {r["kind"] for r in m.results}
                self._start_match(m, "lan" if kinds == {"local"} else "direct")
        elif m.state == "relay":
            if not ok:
                self.cancel_match(m, "no_connection")
            elif all(r and r["ok"] for r in m.results):
                self._start_match(m, "relay")

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
        m.chars = list(self.table.resolve(m.picks[0], m.picks[1], fighters.RANDOM, seed)[:2])
        m.stage = self.table.resolve(m.picks[0], m.picks[1], fighters.RANDOM, seed)[2]
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
                "relay_port": self.udp.port if m.path == "relay" else None,
                "rtt_ms": round(m.rtt, 2), "jitter_ms": round(m.jitter, 2), "delay": m.delay,
                # rollback input delay: fixed for ranked (T5_RB_NET_DELAY on both PCs), else each player's setting
                "input_delay": self.cfg.ranked_input_delay if m.ranked and self.cfg.ranked_input_delay >= 0 else None,
                "rounds": self.cfg.rounds, "ranked": m.ranked, "build": m.build_id,
                "opponent": m.players[1 - side].brief(), "seed": int.from_bytes(m.tag[:4], "big"),
                "key": m.key,                          # T5_NET_KEY (the tag above travels in UDP punches)
                "fight": {"p1": m.chars[0], "p2": m.chars[1], "stage": m.stage, "rounds": self.cfg.rounds},
                "start_time": int(m.started),          # PS3_FIXED_TIME: the same game clock on both PCs
                "players": [q.brief() for q in m.players],
                "continue": m.continued, "rematch_of": m.rematch_of,
                "min_seconds": self.cfg.min_match_seconds,
                "set": m.set.info() if m.set is not None else None})

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
        rep = {"winner": winner, "score": score, "source": source, "desync": desync, "hash": h, "frames": frames,
               "reason": str(msg.get("reason", ""))[:32], "at": time.time()}
        if m.reports[side] is not None and m.reports[side]["source"] != "quit":
            return {"t": "result_ack", "match": m.id}        # first report stands
        m.reports[side] = rep
        if desync:
            # The games went apart: whatever either screen showed, it was not the same match.
            self._finish(m, "void", None, None, reason="desync")
        elif all(m.reports):
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
        else:
            # The opponent's game will notice too (their netplay times out); settle without waiting.
            self._settle_quit(m, side)

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
        if a.get("desync") or b.get("desync"):
            self._finish(m, "void", None, None, reason="desync")
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
        # disconnect + disconnect, or disconnect + result: the connection between the two PCs failed.
        self._finish(m, "void", None, None, reason="connection")

    def _dispute(self, m):
        """Both reported a result and the winners differ. The netplay layer's state hash decides when
        both sent one: equal hashes = the two games ended in the same state, so one report was changed
        by hand -- the one read from the game wins; different hashes = desync."""
        a, b = m.reports
        log.warning("match %s: results disagree: %s vs %s", m.id, a, b)
        if a.get("hash") and b.get("hash"):
            if a["hash"] != b["hash"]:
                self._finish(m, "void", None, None, reason="desync")
                return
            src = [r["source"] for r in (a, b)]
            if src.count("game") == 1:
                good = m.reports[src.index("game")]
                self._finish(m, "resolved", good["winner"], good["score"], reason="disputed")
                return
        self._finish(m, "disputed", None, None, reason="disputed")

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

    def _grace_expired(self, m, side):
        """`side` lost the lobby mid-match and did not come back in time: the match is lost
        (unless the opponent already said that player won)."""
        m.timers.pop(f"grace{side}", None)
        if m.state != "playing" or m.players[side].online:
            return
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
            if culprit is not None and reason in ("early_quit", "disconnect") and any(gs.wins.values()):
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
        elif by is not None and reason in ("left", "declined", "disconnect") and any(gs.wins.values()):
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
        if m is not None and self.recent.pop(m.id, None) is not None:
            for q in gs.players:
                if q is not by:
                    q.send({"t": "rematch", "match": m.id, "state": "declined", "from": by.brief()})

    def _abandon_set(self, p, requester=None):
        """`p` starts something new (queue, room, challenge): the old set is over. Not in the middle of a
        ranked set: that has to be left on purpose (leave_set), and leaving it is losing it."""
        gs = p.set
        if gs is not None and gs.rated and gs.state == "active":
            a, b = gs.wins[p.id], gs.wins[gs.other(p).id]
            raise LobbyError(proto.E_BUSY, f"you are in a ranked set ({a}-{b}); leave it first (that counts as a loss)"
                             if requester is None else "that player is in a ranked set")
        if gs is not None and gs.state == "active" and gs.current is None:
            self._decline_recent(gs, p)
            self._end_set(gs, "left", by=p)

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
            self.ip_connects.prune()
            self.login_fail.prune()
            self.pair_last = {k: t for k, t in self.pair_last.items() if now - t < self.cfg.pair_cooldown}
            self._relay_samples.append((now, self.udp.stats["relayed_bytes"]))
            del self._relay_samples[:-13]          # one minute of 5 s samples
            try:
                self.reload_tls()
                self._maybe_backup()
                self._maybe_log_status()
            except Exception:
                log.exception("housekeeping")

    async def _tick_admin(self):
        """Bans made with the admin tool (python -m t5lobby.server.admin) take effect within seconds:
        banned accounts and addresses are kicked."""
        while True:
            await asyncio.sleep(self.cfg.admin_poll)
            try:
                self.poll_notices()
                self.reload_bans()
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
            "rooms": len(self.rooms),
            "queue": {m: len(q) for m, q in self.queues.items()},
            "matches": {"running": sum(by_state.values()), "by_state": by_state},
            "relay": {"sessions": len(self.udp.relays), "max": self.cfg.max_relays,
                      "kbit_s": round(self.relay_kbit_s(), 1),
                      "bytes_total": self.udp.stats["relayed_bytes"], "packets_total": self.udp.stats["relayed"],
                      "dropped_total": self.udp.stats["dropped"], "force_relay": self.cfg.force_relay},
            "counters": dict(self.counters),
            "db": db,
            "tls": cert_info(self.cfg.tls_cert) if self.sslctx else None,
            "notices": len(self.notices_by_id),
            "config": {"accounts": self.cfg.accounts, "guests": self.cfg.guests,
                       "max_clients": self.cfg.max_clients, "pinned_builds": len(self.cfg.builds)},
            "process": process_info(),
        }
