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
    ready_timeout: float = 20.0     # T5L_READY_TIMEOUT: seconds to accept a found match
    register_timeout: float = 6.0   # T5L_REGISTER_TIMEOUT: seconds for both game sockets to reach the server
    punch_timeout: float = 3.0      # T5L_PUNCH_TIMEOUT: seconds the clients try to punch through
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
    ranked_rooms: bool = True       # T5L_RANKED_ROOMS: rooms may be ranked (else only the ranked queue is)

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
