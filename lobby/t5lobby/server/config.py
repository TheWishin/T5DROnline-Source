"""Server configuration. Everything comes from environment variables (no secrets in files
in the repo); Config(**overrides) is what the tests use."""
import os
from dataclasses import dataclass, field, fields

from ..proto import DEFAULT_PORT


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _list(v):
    return [x.strip().lower() for x in str(v).split(",") if x.strip()]


@dataclass
class Config:
    host: str = "0.0.0.0"           # T5L_HOST: bind address (TCP and UDP)
    port: int = DEFAULT_PORT        # T5L_PORT: TCP control port
    udp_port: int = DEFAULT_PORT    # T5L_UDP_PORT: UDP registration / ping / relay port
    udp_port2: int = DEFAULT_PORT + 1  # T5L_UDP_PORT2: NAT mapping probe; 0 = off
    db: str = "t5lobby.db"          # T5L_DB: SQLite file (":memory:" for tests)
    motd: str = ""                  # T5L_MOTD
    accounts: bool = True           # T5L_ACCOUNTS: allow registering / logging in with a password
    guests: bool = True             # T5L_GUESTS: allow guest logins
    guest_ranked: bool = False      # T5L_GUEST_RANKED: guests may use the ranked queue (rating lives for the session)
    builds: list = field(default_factory=list)   # T5L_BUILDS: allowed build ids (comma list); empty = any
    tls_cert: str = ""              # T5L_TLS_CERT / T5L_TLS_KEY: PEM files -> control channel over TLS
    tls_key: str = ""
    max_clients: int = 500          # T5L_MAX_CLIENTS
    max_per_ip: int = 8             # T5L_MAX_PER_IP: concurrent control connections per address
    relay: bool = True              # T5L_RELAY: offer the UDP relay when hole punching fails
    force_relay: bool = False       # T5L_FORCE_RELAY: skip hole punching (testing)
    relay_kbps: int = 512           # T5L_RELAY_KBPS: per-player relay bandwidth cap
    relay_pps: int = 400            # T5L_RELAY_PPS: per-player relay packet rate cap
    max_relays: int = 100           # T5L_MAX_RELAYS: concurrent relay sessions
    ready_timeout: float = 15.0     # T5L_READY_TIMEOUT: seconds to accept a found match
    blind_ready: bool = True        # T5L_BLIND_READY: queue matches show only the ping until both accepted (clients that ask)
    register_timeout: float = 6.0   # T5L_REGISTER_TIMEOUT: seconds for both game sockets to reach the server
    punch_timeout: float = 6.0      # T5L_PUNCH_TIMEOUT: seconds the clients try to punch through (1.0.0/1.1.0: 3)
    punch_ttl_open: float = 0.5     # T5L_PUNCH_TTL_OPEN: seconds of low-TTL punches that only open each side's own NAT
    predict_ports: int = 24         # T5L_PREDICT_PORTS: ports tried after a symmetric NAT's last one (0 = no prediction)
    relay_upgrade: bool = True      # T5L_RELAY_UPGRADE: two new clients on the relay move onto the direct path when it works
    relay_timeout: float = 6.0      # T5L_RELAY_TIMEOUT: seconds to set up the relay path
    result_timeout: float = 90.0    # T5L_RESULT_TIMEOUT: wait for the second result report
    match_timeout: float = 3 * 3600.0  # T5L_MATCH_TIMEOUT: a match without results is dropped after this
    accept_onesided: bool = True    # T5L_ACCEPT_ONESIDED: a lone report counts when the other player left the lobby
    login_timeout: float = 15.0     # T5L_LOGIN_TIMEOUT: hello + login must finish within this
    idle_timeout: float = 90.0      # T5L_IDLE_TIMEOUT: no message for this long -> disconnect
    resume_window: float = 600.0    # T5L_RESUME_WINDOW: seconds a dropped player's session can be resumed
    scrypt_n: int = 1 << 14         # T5L_SCRYPT_N: password hash cost
    log_level: str = "INFO"         # T5L_LOG_LEVEL
    # accounts (docs/RANKED.md "Accounts")
    session_days: float = 30.0      # T5L_SESSION_DAYS: a remembered login lasts this long unused
    recovery_codes: int = 8         # T5L_RECOVERY_CODES: one-time codes handed out at registration
    # ranked play and match integrity (docs/RANKED.md)
    placement: int = 5              # T5L_PLACEMENT: placement matches before the first rank
    placement_cap: int = 12         # T5L_PLACEMENT_CAP: highest tier placement gives (12 = 3rd Dan)
    hysteresis: float = 30.0        # T5L_HYSTERESIS: rating points below a tier before demotion
    shield: int = 3                 # T5L_SHIELD: matches after a promotion without demotion
    provisional_rd: float = 110.0   # T5L_PROVISIONAL_RD: above this RD a rank shows as provisional
    reconnect_grace: float = 60.0   # T5L_RECONNECT_GRACE: seconds a player who lost the lobby mid-match may return
    min_match_seconds: float = 30.0  # T5L_MIN_MATCH_SECONDS: shorter matches never count
    strike_limit: int = 3           # T5L_STRIKE_LIMIT: voids caused within 24 h before they count as losses
    pair_cap: int = 10              # T5L_PAIR_CAP: ranked matches per pair of accounts per 24 h that count
    rematch_window: float = 20.0    # T5L_REMATCH_WINDOW: seconds to agree on a rematch
    # ranked sets (docs/RANKED.md "Ranked sets"): first to this many games wins the set, rated once at its end;
    # 1 = every ranked game is rated on its own (the old way, and always with clients that do not announce "sets")
    ranked_set_wins: int = 2        # T5L_RANKED_SET_WINS
    set_next_seconds: float = 6.0   # T5L_SET_NEXT_SECONDS: countdown from a game's result to the set's next game
    set_replays: int = 2            # T5L_SET_REPLAYS: games without a winner (desync, draw, too short) played again
                                    # per set; one more and the set is void
    ranked_rooms: bool = True       # T5L_RANKED_ROOMS: rooms may be ranked (else only the ranked queue is)
    rounds: int = 3                 # T5L_ROUNDS: rounds to win a match (first to 3, like Tekken 6 online)
    ingame_pick: int = 30           # T5L_INGAME_PICK: seconds to pick the character on the game's own select screen
                                    # (when both players' launchers and games can; 0 = off: the launcher's character)
    ranked_input_delay: int = 2     # T5L_RANKED_INPUT_DELAY: rollback input delay of ranked matches, frames (fixed: the
                                    # players' own setting -- auto / 0 / 1 / 2 -- applies to other matches; -1 = theirs)
    # community tournaments (docs/TOURNAMENTS.md)
    tour_organizers: str = "any"    # T5L_TOUR_ORGANIZERS: who may create one: any (every account), none, or a comma list
                                    # of account names
    tour_admins: list = field(default_factory=list)   # T5L_TOUR_ADMINS: account names that may run every tournament
    tour_rated: bool = False        # T5L_TOUR_RATED: tournament sets change the rating (once per set, like a ranked set)
    tour_noshow: float = 300.0      # T5L_TOUR_NOSHOW: seconds to accept a called set; who has not is a no-show (out)
    tour_retries: int = 2           # T5L_TOUR_RETRIES: a set that ended without a result is called again this often
                                    # (its score kept), then it waits for the organizer
    tour_max_open: int = 20         # T5L_TOUR_MAX_OPEN: tournaments not finished yet, on the whole server
    tour_per_organizer: int = 2     # T5L_TOUR_PER_ORGANIZER: ... per organizer (T5L_TOUR_ADMINS have no limit)
    tour_max_days: float = 14.0     # T5L_TOUR_MAX_DAYS: a tournament starts at most this far ahead
    tour_keep_days: float = 7.0     # T5L_TOUR_KEEP_DAYS: finished tournaments stay in the list this long
    tour_tick: float = 0.5          # T5L_TOUR_TICK: seconds between looks at start times and no-shows
    tour_blamed_voids: int = 1      # T5L_TOUR_BLAMED_VOIDS: games of one set a player may end without a result by their
                                    # own doing (a crash) and still have the set called again; the next one loses it
    tour_get_rate: float = 2.0      # T5L_TOUR_GET_RATE / _BURST: tour_get requests per second per connection (a 64-player
    tour_get_burst: int = 10        # bracket is ~60 KB), after a burst of this many
    # matchmaking extras and the post-game lag check (docs/RANKED.md, Tekken 6 style options)
    strict_range: float = 150.0     # T5L_STRICT_RANGE: ranked "strict matchmaking" pairs within this many rating points
    # The queues pair players whose estimated ping (the best relay path: docs/RANKED.md "Matchmaking") fits a window
    # that starts at T5L_PING_START ms and grows by T5L_PING_WIDEN ms (quick: T5L_QUICK_PING_WIDEN) per second the
    # two have waited; after T5L_PING_ANY_SECONDS (quick: T5L_QUICK_PING_ANY_SECONDS) any ping goes (0 = never)
    ping_start: float = 80.0        # T5L_PING_START
    ping_widen: float = 10.0        # T5L_PING_WIDEN (ranked queue)
    ping_any_seconds: float = 60.0  # T5L_PING_ANY_SECONDS (ranked queue)
    quick_ping_widen: float = 20.0  # T5L_QUICK_PING_WIDEN
    quick_ping_any_seconds: float = 30.0  # T5L_QUICK_PING_ANY_SECONDS
    pair_cooldown: float = 30.0     # T5L_PAIR_COOLDOWN: seconds before two players who just finished a ranked game are queue-matched again
    max_blocks: int = 200           # T5L_MAX_BLOCKS: blocked players per account / guest session
    # friends and invites (docs/ONLINE.md "Friends and invites"): accounts only
    max_friends: int = 100          # T5L_MAX_FRIENDS: friends per account
    friend_requests_day: int = 20   # T5L_FRIEND_REQUESTS_DAY: friend requests an account may send per 24 h
    friend_pending: int = 30        # T5L_FRIEND_PENDING: requests waiting for an answer, per sender and per receiver
    friend_request_days: float = 14.0  # T5L_FRIEND_REQUEST_DAYS: an unanswered request runs out after this
    friend_retry_days: float = 7.0  # T5L_FRIEND_RETRY_DAYS: after a decline, the same request again only after this
    invite_seconds: float = 60.0    # T5L_INVITE_SECONDS: an invite to a match or a room waits this long for an answer
    lag_tolerance: float = 1.0      # T5L_LAG_TOLERANCE: extra frames of waiting before the lag check says "more than the ping explains"
    lag_wait: float = 6.0           # T5L_LAG_WAIT: seconds to wait for the second player's lag report
    # PC speed (docs/RANKED.md "Slow PCs"): lockstep plays at the slower PC's speed
    min_fps: float = 40.0           # T5L_MIN_FPS: a PC whose last match ran slower stays out of ranked (0 = off)
    warn_fps: float = 55.0          # T5L_WARN_FPS: below this both players are warned at match found (0 = off)
    # hosting and operations (docs/HOSTING.md)
    log_file: str = ""              # T5L_LOG_FILE: also log to this file, rotated (stderr is always used if open)
    log_max_mb: int = 10            # T5L_LOG_MAX_MB: rotate the log file at this size ...
    log_backups: int = 5            # T5L_LOG_BACKUPS: ... and keep this many old ones
    conn_rate: float = 0.5          # T5L_CONN_RATE: new connections per second per address ...
    conn_burst: int = 10            # T5L_CONN_BURST: ... after a burst of this many
    max_pending_kb: int = 1024      # T5L_MAX_PENDING_KB: unsent output per connection before it is dropped
    lobby_interval: float = 0.3     # T5L_LOBBY_INTERVAL: seconds between lobby list updates (at most)
    udp_ctl_pps: int = 5000         # T5L_UDP_CTL_PPS: server-addressed UDP packets per second, all senders
    name_blocklist: str = ""        # T5L_NAME_BLOCKLIST: file, one word per line; names containing one are refused
    status_host: str = "127.0.0.1"  # T5L_STATUS_HOST: HTTP status/health/metrics endpoint (keep it local) ...
    status_port: int = 7780         # T5L_STATUS_PORT: ... on this TCP port; 0 = off
    status_log_minutes: float = 15  # T5L_STATUS_LOG_MINUTES: a one-line status in the log this often; 0 = never
    backup_dir: str = ""            # T5L_BACKUP_DIR: online database backups go here; empty = no automatic backups
    backup_hours: float = 24        # T5L_BACKUP_HOURS: one backup this often ...
    backup_keep: int = 14           # T5L_BACKUP_KEEP: ... and keep the newest this many
    admin_poll: float = 5.0         # T5L_ADMIN_POLL: seconds between checks for bans made with the admin tool
    # abuse protection added for the public launch (docs/HOSTING.md, "Abuse protection")
    max_prelogin: int = 100         # T5L_MAX_PRELOGIN: connections that have not logged in yet, all addresses together
    tls_handshake_timeout: float = 10.0  # T5L_TLS_HANDSHAKE_TIMEOUT: seconds a new connection gets for its TLS handshake
    ipv6_prefix: int = 64           # T5L_IPV6_PREFIX: IPv6 addresses count per network of this size for the per-address limits
    heavy_rate: float = 1.0         # T5L_HEAVY_RATE: leaderboard / profile / history / full lobby list requests per second ...
    heavy_burst: int = 10           # T5L_HEAVY_BURST: ... per connection, after a burst of this many
    state_rate: float = 2.0         # T5L_STATE_RATE: requests that change what the lobby list shows (queue, rooms,
    state_burst: int = 20           # T5L_STATE_BURST:  character, ping, ...) per second per connection, after a burst
    chat_total_rate: float = 20.0   # T5L_CHAT_TOTAL_RATE: chat lines per second for the whole lobby (every line goes to everybody)
    pw_concurrency: int = 2         # T5L_PW_CONCURRENCY: password hashes computed at the same time (keep it below the
                                    # number of CPUs: the event loop must always find one free) ...
    pw_queue: int = 64              # T5L_PW_QUEUE: ... and waiting; more -> "server busy, try again"
    max_match_seconds: float = 420.0  # T5L_MAX_MATCH_SECONDS: the longest a real match takes; a lone result report does not
                                    # count against an opponent who is still online before this much time since the start
    dispute_limit: int = 3          # T5L_DISPUTE_LIMIT: disputed ranked results per account in 24 h; from then on that
                                    # account loses a disputed ranked match against an opponent below the limit (0 = off)
    ranked_same_ip: bool = False    # T5L_RANKED_SAME_IP: ranked matches between two players on one internet address count
    relay_max_bytes: int = 2048     # T5L_RELAY_MAX_BYTES: largest packet the relay forwards (netplay's own maximum)
    relay_max_seconds: float = 1200.0  # T5L_RELAY_MAX_SECONDS: a relay closes when its match has run this long (0 = never)
    max_relays_per_ip: int = 3      # T5L_MAX_RELAYS_PER_IP: relay sessions at once per internet address (0 = no limit)
    # regional relays (docs/HOSTING.md "Adding a relay server"): relay-only nodes in other regions, chosen per match
    relays: str = ""                # T5L_RELAYS: central server: relays.json -- a file, or the JSON itself; "" = none
    relay_secret_file: str = ""     # T5L_RELAY_SECRET_FILE: the secret shared with the relay nodes (central: for the
                                    # nodes without a "secret_file" of their own; a relay node: its secret)
    relay_check_seconds: float = 5.0   # T5L_RELAY_CHECK_SECONDS: central: health check of every relay node this often
    relay_dead_seconds: float = 20.0   # T5L_RELAY_DEAD_SECONDS: central: a node that has not answered this long is skipped
    relay_bind_seconds: float = 60.0   # T5L_RELAY_BIND_SECONDS: relay node: a session's bind tokens work this long
    relay_id: str = ""              # T5L_RELAY_ID: relay node: its id in the central's relays.json (other ids refused)
    relay_central: list = field(default_factory=list)  # T5L_RELAY_CENTRAL: relay node: the central server's addresses;
                                    # control datagrams from anywhere else are dropped (empty: any, the secret decides)

    @classmethod
    def from_env(cls, env=None, **overrides):
        env = os.environ if env is None else env
        kw = {}
        for f in fields(cls):
            key = "T5L_" + f.name.upper()
            if key not in env:
                continue
            raw = env[key]
            if f.type in (bool, "bool"):
                kw[f.name] = _bool(raw)
            elif f.type in (int, "int"):
                kw[f.name] = int(raw)
            elif f.type in (float, "float"):
                kw[f.name] = float(raw)
            elif f.type in (list, "list"):
                kw[f.name] = _list(raw)
            else:
                kw[f.name] = raw
        kw.update(overrides)
        return cls(**kw)
