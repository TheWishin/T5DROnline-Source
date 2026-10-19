"""The control channel between the central lobby server and its relay-only nodes (docs/HOSTING.md,
"Adding a relay server"; protocol: docs/ONLINE.md "Regional relays").

A relay node runs only the lobby's UDP relay, in another region, with no accounts and no database. The
central lobby talks to it with small UDP datagrams on the node's relay port, each authenticated with
HMAC-SHA256 under a secret the two share (a file on both machines, never in the repository):

    "T5RC" | version u8 | kind u8 (1 = request, 2 = reply) | JSON (UTF-8) | HMAC-SHA256 (32 bytes)

The MAC covers everything before it. Requests carry `op`, a fresh random `id`, the central's clock `ts`
and the node's `node` id; a node takes a request only with a valid MAC, a `ts` within CLOCK_SKEW seconds
of its own clock, an `id` it has not seen and (when it was given one) its own id -- a recorded request
cannot be played back later or at another node. A reply carries `re` = the request's id and is
authenticated the same way; the central server only takes a reply to a request it has open, from the
address it sent that request to.

Requests (central -> node):
    status                       -> sessions, max, kbit/s, totals, the node's clock and uptime
    open  {sid, tokens [2], lease}   a relay session for one match: the two players' 16-byte bind tokens
                                 (short-lived: a side must bind within T5L_RELAY_BIND_SECONDS), the time
                                 the session may live (renewed for a rematch inside the running games)
    renew {sid, lease}
    info  {sid}                  what the session saw: bound sides, packets, peer pings and pongs
    close {sid}                  -> its final numbers

The players never see this channel: they bind to the node with the bind token the central server gave
them over its TLS control connection (RELAY_BIND, exactly as with the central relay), and the node then
forwards their game packets with the central relay's limits.

The MAC makes the channel authentic, not secret: the bind tokens in an `open` request would cross the
internet readable, and anybody on the path between the two servers could bind before (or after) the
player and take the session. So a node of 1.1.2 or newer says `"caps": ["etokens"]` in its status answer,
and the central server then sends the tokens sealed (`etokens`: XOR with HMAC-SHA256(secret,
"T5RC-tokens|" + request id) -- a fresh id per datagram, so no keystream is used twice). An older node gets
them as before (`tokens`), and the central server logs once that it should be updated.

A node also refuses requests stamped before it started (RESTART_MARGIN): the ids it has seen are kept in
memory only, so without this a request recorded just before a node restart could be played back after it.
"""
import hashlib
import hmac
import json
import os
import secrets as _secrets
import time

MAGIC = b"T5RC"
VERSION = 1
REQUEST = 1
REPLY = 2
MAC_LEN = 32
HDR_LEN = 6
MAX_PACKET = 1400          # stays below a typical path MTU: no fragments
CLOCK_SKEW = 120.0         # seconds a request's timestamp may differ from the node's clock
MIN_SECRET = 32            # characters in a secret file (secret_hex() writes 64)
OPS = ("status", "open", "renew", "info", "close")
NODE_CAPS = ("etokens",)   # what a node of this version understands (its status answer lists them)
RESTART_MARGIN = 5.0       # seconds: a node takes no request stamped earlier than its start minus this
_TOKENS_LABEL = b"T5RC-tokens|"


def pack(secret, kind, obj):
    """-> one authenticated datagram (bytes)."""
    body = json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    head = MAGIC + bytes((VERSION, kind))
    data = head + body
    return data + hmac.new(secret, data, hashlib.sha256).digest()


def unpack(secret, data):
    """-> (kind, dict) of a datagram whose MAC is right, else None. Never raises on bad input."""
    if len(data) < HDR_LEN + MAC_LEN + 2 or len(data) > MAX_PACKET or data[:4] != MAGIC or data[4] != VERSION:
        return None
    body, mac = data[:-MAC_LEN], data[-MAC_LEN:]
    if not hmac.compare_digest(hmac.new(secret, body, hashlib.sha256).digest(), mac):
        return None
    try:
        obj = json.loads(body[HDR_LEN:].decode("ascii"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(obj, dict):
        return None
    return data[5], obj


def is_control(data):
    return data[:4] == MAGIC


def _token_keystream(secret, rid, n):
    out = b""
    i = 0
    while len(out) < n:
        out += hmac.new(secret, _TOKENS_LABEL + str(rid).encode("ascii") + bytes((i,)), hashlib.sha256).digest()
        i += 1
    return out[:n]


def seal_tokens(secret, rid, tokens):
    """Bind tokens (bytes each) for the request `rid` -> the hex string of `etokens`."""
    raw = b"".join(tokens)
    return bytes(a ^ b for a, b in zip(raw, _token_keystream(secret, rid, len(raw)))).hex()


def open_tokens(secret, rid, sealed_hex, n=2, size=16):
    """`etokens` of the request `rid` -> [n tokens of `size` bytes]. Raises ValueError."""
    raw = bytes.fromhex(str(sealed_hex))
    if len(raw) != n * size:
        raise ValueError("etokens")
    plain = bytes(a ^ b for a, b in zip(raw, _token_keystream(secret, rid, len(raw))))
    return [plain[i * size:(i + 1) * size] for i in range(n)]


def request(op, node_id, **fields):
    """A request dict with a fresh id and the current time."""
    msg = {"op": op, "id": _secrets.token_hex(8), "ts": round(time.time(), 3), "node": node_id}
    msg.update(fields)
    return msg


def secret_hex():
    """A new secret: 64 hex digits (256 bits)."""
    return _secrets.token_hex(32)


def load_secret(path):
    """The secret in a file (one line; surrounding space ignored) -> bytes. Raises ValueError when the file
    is missing, unreadable or too short."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError as e:
        raise ValueError(f"relay secret file {path}: {e.strerror or e}") from None
    if len(text) < MIN_SECRET or any(c.isspace() for c in text):
        raise ValueError(f"relay secret file {path}: needs one line of at least {MIN_SECRET} characters "
                         "(make one with: python run.py relay --gen-secret FILE)")
    return text.encode("utf-8")


def write_secret(path, force=False):
    """Create a secret file (mode 0600 where the OS has modes). -> the secret's text. An existing file is kept
    unless force (both machines must hold the same secret)."""
    if os.path.exists(path) and not force:
        return load_secret(path).decode("utf-8")
    text = secret_hex()
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return text


class SeenIds:
    """Request ids a node has taken, kept for twice the clock window (a replay inside the window is refused)."""

    def __init__(self, keep=2 * CLOCK_SKEW, limit=20000):
        self.keep = keep
        self.limit = limit
        self.ids = {}

    def add(self, rid, now=None):
        """True when `rid` is new (and remembers it)."""
        now = time.monotonic() if now is None else now
        if rid in self.ids:
            return False
        if len(self.ids) >= self.limit:
            self.prune(now)
            if len(self.ids) >= self.limit:      # (a flood of valid requests cannot happen without the secret)
                return False
        self.ids[rid] = now + self.keep
        return True

    def prune(self, now=None):
        now = time.monotonic() if now is None else now
        self.ids = {k: t for k, t in self.ids.items() if t > now}
