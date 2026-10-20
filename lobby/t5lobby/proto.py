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
    """A request the server refused, or a connection problem. .code is machine readable; .extra holds the
    error's machine-readable fields beyond code and msg (the server sends them in the error message), e.g.
    retry: whole seconds until the same request may go again (an invite held back after a no)."""

    def __init__(self, code, msg="", **extra):
        super().__init__(f"{code}: {msg}" if msg else code)
        self.code = code
        self.msg = msg
        self.extra = extra


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
    # "replace": a lone surrogate (valid JSON as "\ud800", not encodable as UTF-8) must never make a message
    # unsendable -- one in a client's build "release" used to stop the lobby list for everybody.
    return (json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8", "replace")


def clean_text(value, limit):
    """A client-supplied string the server keeps or passes on: printable characters only (no
    control, format -- e.g. right-to-left override -- or surrogate code points), at most `limit`
    characters, and at most two combining marks in a row (no "Zalgo" text towering over the chat)."""
    import unicodedata
    out = []
    marks = 0
    for ch in str(value)[:limit * 4]:
        if not ch.isprintable():
            continue
        if unicodedata.combining(ch):
            marks += 1
            if marks > 2:
                continue
        else:
            marks = 0
        out.append(ch)
        if len(out) >= limit:
            break
    return "".join(out)


def decode(line):
    """bytes (one line) -> dict; raises ValueError on anything that is not a JSON object with a string "t"."""
    try:
        obj = json.loads(line.decode("utf-8"))
    except RecursionError:          # [[[[...]]]] nested deeper than the parser's stack
        raise ValueError("nested too deeply") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("t"), str):
        raise ValueError("not a message")
    return obj


# ---------------------------------------------------------------------------- addresses in messages
# Messages the players read (errors, notices, status lines) must never carry an IP address: the
# opponent's address is private, and a connection error is the most likely place for one to leak
# (an OSError names the address it failed to reach). scrub_addresses() is applied where a message
# leaves the server (Conn.send) and where the client library and the launcher show text.
_IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w)(?::\d{1,5})?")
_IPV6_RE = re.compile(r"\[?(?<![\w:])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?:%\w+)?\]?(?::\d{1,5})?(?![\w:])")
HIDDEN_ADDRESS = "(address hidden)"


def scrub_addresses(text):
    """Replace IPv4 and IPv6 addresses (with or without a port) in `text` by HIDDEN_ADDRESS.
    Host names stay. Anything that does not parse as an address (a clock time, a version number
    such as 3.12.10) is left alone."""
    import ipaddress
    if not isinstance(text, str) or (":" not in text and "." not in text):
        return text

    def v4(m):
        t = m.group(0)
        try:
            ipaddress.IPv4Address(t.rsplit(":", 1)[0] if ":" in t else t)
        except ValueError:
            return t
        return HIDDEN_ADDRESS

    def v6(m):
        t = m.group(0)
        inner = t[1:].split("]", 1)[0] if t.startswith("[") else t
        try:
            ipaddress.IPv6Address(inner.split("%", 1)[0])
        except ValueError:
            return t
        return HIDDEN_ADDRESS

    return _IPV6_RE.sub(v6, _IPV4_RE.sub(v4, text))


NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.\[\]\(\)!\? ]{2,16}$")

# A match id as servers make them ("m" + 12 hex digits). The launcher puts it into file names (result,
# fight and status files, the handover socket file) and into the game's fight line, so a server -- any
# server a player adds -- must not be able to send one with a path, a dot or a space in it (1.1.2).
MATCH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def valid_match_id(value):
    return isinstance(value, str) and MATCH_ID_RE.fullmatch(value) is not None


def file_safe(value):
    """`value` for a file name: letters, digits, '_' and '-' only (anything else becomes '_')."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:40] or "_"


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


def name_skeleton(name):
    """What a name looks like: names with the same skeleton pass for each other on screen, so a new
    name may not share one with an account or a player online ("Wishin", "Wish-in", "W1shin",
    "WIshin" and "Wishln" are one name here). Lower case, letters and digits only, with the
    look-alikes folded: capital I, 1 and i -> l, 0 -> o, rn -> m, vv -> w."""
    s = str(name).replace("I", "l").lower().translate(_LOOKALIKE)
    return re.sub(r"[^a-z0-9]", "", s).replace("rn", "m").replace("vv", "w")


_LOOKALIKE = str.maketrans({"0": "o", "1": "l", "i": "l"})
_LEET = str.maketrans({"3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g"})


def _staff_key(name):
    return name_skeleton(name).translate(_LEET)


_RESERVED_KEYS = frozenset(_staff_key(n) for n in RESERVED_NAMES)
_RESERVED_PREFIX_KEYS = tuple(_staff_key(p) for p in RESERVED_PREFIXES)


def reserved_name(name):
    """Reserved without regard to case, punctuation, look-alike letters or digits standing for
    letters ("Adm1n", "M0derat0r", "5ystem" and "0fficial_x" are refused like "admin")."""
    k = name_key(name)
    if not k or k in RESERVED_NAMES or any(k.startswith(p) for p in RESERVED_PREFIXES):
        return True
    sk = _staff_key(name)
    return sk in _RESERVED_KEYS or any(sk.startswith(p) for p in _RESERVED_PREFIX_KEYS)


def address_key(ip, v6_prefix=64):
    """What the per-address limits count by: the address itself for IPv4 (and IPv4-mapped IPv6),
    the /64 network for IPv6 -- one subscriber usually gets a whole /64, so a limit per single IPv6
    address would not limit anything."""
    import ipaddress
    try:
        a = ipaddress.ip_address(str(ip).split("%", 1)[0])
    except ValueError:
        return str(ip)
    if a.version == 6:
        if a.ipv4_mapped is not None:
            return str(a.ipv4_mapped)
        return str(ipaddress.ip_network(f"{a}/{v6_prefix}", strict=False))
    return str(a)


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


# ---------------------------------------------------------------------------- private rooms
# docs/ONLINE.md "Rooms". The rules a room password follows and the invite codes' alphabet, shared by the server
# (server/rooms.py) and the launcher (it checks a password before sending it).
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"     # no 0/O, 1/I/L: read off a screen, typed back (~59 bits)
CODE_LEN = 12
ROOM_PW_MIN, ROOM_PW_MAX, ROOM_PW_MAX_BYTES = 4, 64, 256


def clean_room_password(pw):
    """The room password as it is hashed (Unicode NFC: any script, the same however it was typed), or None when it
    cannot be one: 4-64 characters, printable only (no control or format characters), no space at either end, at
    most 256 bytes of UTF-8. Never says what it was."""
    import unicodedata
    if not isinstance(pw, str) or len(pw) > ROOM_PW_MAX * 4:
        return None
    pw = unicodedata.normalize("NFC", pw)
    if not ROOM_PW_MIN <= len(pw) <= ROOM_PW_MAX or len(pw.encode("utf-8", "replace")) > ROOM_PW_MAX_BYTES:
        return None
    if pw != pw.strip() or not all(ch.isprintable() for ch in pw):
        return None
    return pw


def normalize_room_code(code):
    """'k7qf-m2px 9tzr' -> 'K7QFM2PX9TZR'; None when it cannot be an invite code."""
    if not isinstance(code, str) or len(code) > 64:
        return None
    s = "".join(ch for ch in code.upper() if ch.isalnum())
    return s if len(s) == CODE_LEN and all(ch in CODE_ALPHABET for ch in s) else None


def new_room_code():
    """A fresh invite code, XXXX-XXXX-XXXX."""
    import secrets
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
    return "-".join(raw[i:i + 4] for i in range(0, CODE_LEN, 4))


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

PEER_TYPES = frozenset((U_PUNCH, U_PPING, U_PPONG))   # what the relay carries besides the game's T5NP packets

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
