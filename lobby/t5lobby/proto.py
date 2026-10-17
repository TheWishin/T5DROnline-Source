"""Wire format shared by the lobby server and its clients.

Two channels (details and the full message list: docs/ONLINE.md):

* Control: TCP (optionally TLS), one JSON object per line, UTF-8, "\\n"
  terminated, at most MAX_LINE bytes from a client. Every object has "t"
  (the message type). A client request may carry "rid" (an integer); the
  server's reply to it carries the same value as "re".

* UDP: small binary packets starting with UDP_MAGIC. Some go to the server
  (ping, endpoint registration, NAT probe, relay bind); the others go
  peer to peer (punch, peer ping) and are what the relay forwards. The game's
  own netplay packets start with b"T5NP" and are never parsed here.
"""
import json
import os
import re
import socket
import struct

PROTO_VERSION = 1          # lobby protocol (control + UDP); bumped on incompatible changes
DEFAULT_PORT = 7781        # TCP control and UDP (same number)
MAX_LINE = 8192            # longest control line a client may send
MAX_LINE_FROM_SERVER = 1 << 20

# ---------------------------------------------------------------------------- errors

class LobbyError(Exception):
    """A request the server refused, or a connection problem. .code is machine readable."""

    def __init__(self, code, msg=""):
        super().__init__(f"{code}: {msg}" if msg else code)
        self.code = code
        self.msg = msg


# Error codes the server sends ({"t":"error","code":...}).
E_BAD_REQUEST = "bad_request"
E_PROTO = "proto_mismatch"
E_VERSION = "version_mismatch"
E_AUTH = "auth_failed"
E_NAME_TAKEN = "name_taken"
E_BAD_NAME = "bad_name"
E_NOT_ALLOWED = "not_allowed"
E_NOT_FOUND = "not_found"
E_BUSY = "busy"
E_RATE = "rate_limited"
E_FULL = "server_full"
E_STATE = "bad_state"
E_INSECURE = "insecure"     # client side: no password over a plain connection to a public server

# ---------------------------------------------------------------------------- control channel

def encode(msg):
    return (json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def decode(line):
    """bytes (one line) -> dict; raises ValueError on anything that is not a JSON object with a string "t"."""
    try:
        obj = json.loads(line.decode("utf-8"))
    except RecursionError:          # [[[[...]]]] nested deeper than the parser's stack
        raise ValueError("nested too deeply") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("t"), str):
        raise ValueError("not a message")
    return obj


NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.\[\]\(\)!\? ]{2,16}$")


def valid_name(name):
    """Display/account names: 2-16 printable ASCII characters from a safe set, no leading/trailing space."""
    return isinstance(name, str) and bool(NAME_RE.match(name)) and name == name.strip() and "  " not in name


# Names nobody may use (compared without case, spaces and punctuation): they would pass for the
# server, its staff, the game's own placeholders or the game's publisher.
RESERVED_NAMES = frozenset((
    "admin", "administrator", "moderator", "mod", "staff", "support", "server", "system", "lobby", "t5lobby",
    "root", "owner", "official", "guest", "unknown", "anonymous", "player", "player1", "player2", "p1", "p2",
    "host", "join", "nobody", "null", "none", "undefined", "you", "me", "cpu", "com", "namco", "bandai",
    "bandainamco", "namcobandai", "sony", "playstation", "psn", "tekken", "t5dr", "t5dronline",
))
RESERVED_PREFIXES = ("admin", "moderator", "official", "t5lobby")


def name_key(name):
    """Lower case, letters and digits only: 'Ad.Min' and 'admin' are the same name here."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def reserved_name(name):
    k = name_key(name)
    return k in RESERVED_NAMES or any(k.startswith(p) for p in RESERVED_PREFIXES) or not k


def parse_hostport(spec, default_port=DEFAULT_PORT):
    """'host', 'host:port', '[v6]:port' -> (host, port)."""
    spec = spec.strip()
    if spec.startswith("["):
        host, _, rest = spec[1:].partition("]")
        return host, int(rest[1:]) if rest.startswith(":") else default_port
    if spec.count(":") == 1:
        host, port = spec.split(":")
        return host, int(port)
    return spec, default_port


# ---------------------------------------------------------------------------- UDP

UDP_MAGIC = b"T5LB"
UDP_VER = 1
GAME_MAGIC = b"T5NP"       # the netplay layer's packets (src/netplay), relayed untouched

# server-addressed
U_SPING = 1        # client -> server ping; answered with U_SPONG (same size)
U_SPONG = 2
U_REGISTER = 3     # "this is my game socket" (token) -> U_REG_ACK with the endpoint the server saw
U_REG_ACK = 4
U_PROBE = 5        # same, to the second UDP port: tells endpoint-dependent (symmetric) NAT mapping apart
U_PROBE_ACK = 6
U_RELAY_BIND = 7   # latch this endpoint into the match's relay session -> U_RELAY_ACK
U_RELAY_ACK = 8
SERVER_TYPES = frozenset((U_SPING, U_REGISTER, U_PROBE, U_RELAY_BIND))

# peer to peer (also what the relay forwards)
U_PUNCH = 16       # hole punching; flag F_HEARD = "I have received your punches"
U_PPING = 17       # peer RTT measurement
U_PPONG = 18

F_HEARD = 1

HDR = struct.Struct("!4sBB")                    # magic, type, version            (6)
PING = struct.Struct("!4sBBId")                 # + seq, sender time            (18)
TOKEN_PKT = struct.Struct("!4sBB16s10x")        # + 16-byte token, padding      (32)
TOKEN_ACK = struct.Struct("!4sBB16s4sH4x")      # + token, seen ip, seen port   (32)
PUNCH = struct.Struct("!4sBB8sBBI")             # + match tag, side, flags, seq (20)
PPING = struct.Struct("!4sBB8sBId")             # + match tag, side, seq, time  (27)

TOKEN_LEN = 16
TAG_LEN = 8


def udp_type(data):
    """Type byte of a lobby UDP packet, or None for anything else (e.g. game traffic)."""
    if len(data) >= HDR.size and data[:4] == UDP_MAGIC and data[5] == UDP_VER:
        return data[4]
    return None


def pk_ping(kind, seq, t):
    return PING.pack(UDP_MAGIC, kind, UDP_VER, seq & 0xFFFFFFFF, t)


def pk_token(kind, token):
    return TOKEN_PKT.pack(UDP_MAGIC, kind, UDP_VER, token)


def pk_token_ack(kind, token, addr):
    return TOKEN_ACK.pack(UDP_MAGIC, kind, UDP_VER, token, socket.inet_aton(addr[0]), addr[1])


def un_token_ack(data):
    _m, kind, _v, token, ip, port = TOKEN_ACK.unpack_from(data)
    return kind, token, (socket.inet_ntoa(ip), port)


def pk_punch(tag, side, flags, seq):
    return PUNCH.pack(UDP_MAGIC, U_PUNCH, UDP_VER, tag, side, flags, seq & 0xFFFFFFFF)


def pk_pping(kind, tag, side, seq, t):
    return PPING.pack(UDP_MAGIC, kind, UDP_VER, tag, side, seq & 0xFFFFFFFF, t)


def new_token():
    return os.urandom(TOKEN_LEN)


# ---------------------------------------------------------------------------- Windows UDP quirk

def disable_udp_connreset(sock):
    """Windows reports an ICMP port-unreachable as WSAECONNRESET on the NEXT recvfrom of a UDP
    socket, and asyncio's proactor stops reading after that. Punching sends to ports that are
    not open yet, so switch the behaviour off (SIO_UDP_CONNRESET = FALSE). No-op elsewhere."""
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        ws2 = ctypes.WinDLL("ws2_32")
        ws2.WSAIoctl.argtypes = [ctypes.c_size_t, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                 ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                 ctypes.c_void_p, ctypes.c_void_p]
        for code in (0x9800000C, 0x9800000F):      # SIO_UDP_CONNRESET, SIO_UDP_NETRESET
            flag = wintypes.BOOL(False)
            ret = wintypes.DWORD(0)
            ws2.WSAIoctl(sock.fileno(), code, ctypes.byref(flag), ctypes.sizeof(flag), None, 0,
                         ctypes.byref(ret), None, None)
    except (OSError, AttributeError):
        pass


def new_event_loop():
    """The event loop both sides use. On Windows the selector loop: its UDP transport keeps
    reading after socket errors (the proactor's stops), and nothing here needs pipes."""
    import asyncio
    if os.name == "nt":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


# ---------------------------------------------------------------------------- session parameters

FRAME_MS = 1000.0 / 59.94


def suggest_delay(rtt_ms, jitter_ms=0.0, lo=2, hi=10):
    """Input delay (frames) for delay-based lockstep at 59.94 fps.

    The input sampled at frame f is used at frame f + d on both PCs, so it has to cross the
    network in d frames: one-way latency (rtt/2) plus jitter plus up to one frame of phase
    difference between the two PCs' frame clocks plus a little processing slack."""
    import math
    one_way = max(0.0, rtt_ms) / 2.0 + max(0.0, jitter_ms) + 2.0
    return max(lo, min(hi, math.ceil(one_way / FRAME_MS) + 1))
