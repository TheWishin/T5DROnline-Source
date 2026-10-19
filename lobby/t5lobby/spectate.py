"""Spectating live matches (docs/SPECTATE.md): the live stream a player's game writes, sent through
the lobby to the spectators' games.

The game of one player (the "streamer") appends the session to a file while it is played
(T5_REPLAY_LIVE: the replay's data as records, src/netplay/replay.cpp "the live stream"). Its
launcher reads that file, compresses it into one zlib stream and uploads the pieces to the lobby
server (Uploader) -- only while somebody watches, never faster than a set rate; the game never
waits for any of it. The server keeps the compressed stream of the session from its start and
sends it to each spectator from the beginning (a late viewer starts at the session's start: the
game state of a rematch depends on the matches before it, and a playback cannot run faster than
the game shows pictures). The spectator's launcher unpacks it into a file of whole records
(Receiver) and starts its game on that file: a replay that is still growing.

Stdlib only; used by the client library, the launcher and tools/spectate_test.py.
"""
import base64
import os
import struct
import zlib

MAGIC = b"T5LIVE 1\n"
EXT = ".t5live"

R_SESSION, R_INPUTS, R_HASH, R_BARRIER, R_MATCH, R_LAST, R_END = 1, 2, 3, 4, 5, 6, 7
MAX_RECORD = 1 << 24
MAX_RAW = 64 << 20          # a spectator never unpacks more than this (a stream is a few KB a minute)
CHUNK = 4096                # compressed bytes per upload message (base64 ~5.5 KB: under the 8 KB line limit)


class LiveError(Exception):
    pass


def _u32(b, i):
    return struct.unpack_from("<I", b, i)[0]


def _str(b, i):
    n = struct.unpack_from("<H", b, i)[0]
    if i + 2 + n > len(b):
        raise LiveError("string past the record")
    return b[i + 2:i + 2 + n].decode("utf-8", "replace"), i + 2 + n


def parse_match(b):
    """A MATCH record's payload -> dict (the fields the launcher shows)."""
    if len(b) < 4 + 24 + 48 + 8 + 4:
        raise LiveError("short match record")
    idx = _u32(b, 0)
    start, end, frames, _hf, desync, flags = struct.unpack_from("<6I", b, 4)
    v = struct.unpack_from("<12i", b, 28)
    names = []
    i = 28 + 48 + 8
    for _ in range(2):
        s, i = _str(b, i)
        names.append(s)
    return {"index": idx, "start": start, "end": end, "frames": frames, "desync": desync,
            "have_result": bool(flags & 1), "complete": bool(flags & 4),
            "p1": v[0], "p2": v[1], "stage": v[6], "rounds": v[7], "pick": v[8],
            "winner": None if v[9] < 0 else v[9], "score": [v[10], v[11]], "names": names}


class LiveParser:
    """Whole records of a live stream, fed in pieces of any size. feed() returns the bytes that
    complete whole records (the magic included at the start): what a spectator's file gets, so an
    END record can always be added after them."""

    def __init__(self):
        self.buf = bytearray()
        self.started = False
        self.session = None
        self.matches = []
        self.last = 0
        self.frames = 0
        self.ended = False
        self.end_why = None
        self.bad = None
        self.records = 0

    @property
    def ready(self):
        """The session and its first match are in: a spectator's game can start."""
        return self.session is not None and bool(self.matches) and self.bad is None

    def feed(self, data):
        if self.bad is not None:
            return b""
        self.buf += data
        out = bytearray()
        i = 0
        if not self.started:
            if len(self.buf) < len(MAGIC):
                return b""
            if bytes(self.buf[:len(MAGIC)]) != MAGIC:
                self.bad = "not a live stream"
                return b""
            self.started = True
            out += MAGIC
            i = len(MAGIC)
        while len(self.buf) - i >= 5:
            t = self.buf[i]
            n = _u32(self.buf, i + 1)
            if n > MAX_RECORD:
                self.bad = "a record too long"
                break
            if len(self.buf) - i - 5 < n:
                break
            payload = bytes(self.buf[i + 5:i + 5 + n])
            try:
                self._record(t, payload)
            except (LiveError, struct.error) as e:
                self.bad = f"record {t}: {e}"
                break
            out += self.buf[i:i + 5 + n]
            i += 5 + n
            self.records += 1
        del self.buf[:i]
        return bytes(out)

    def _record(self, t, b):
        if t == R_SESSION:
            if len(b) < 32:
                raise LiveError("short session record")
            ver, flags, slot, delay, rb_delay, seed, mseed, every = struct.unpack_from("<8I", b, 0)
            build, i = _str(b, 32)
            created, _ = _str(b, i)
            self.session = {"version": ver, "rollback": bool(flags & 1), "slot": slot, "delay": delay,
                            "hash_every": every, "build": build, "created": created}
        elif t == R_INPUTS:
            first, cnt = struct.unpack_from("<2I", b, 0)
            if first != self.frames or len(b) != 8 + 12 * cnt:
                raise LiveError("inputs out of order")
            self.frames = first + cnt
        elif t == R_MATCH:
            m = parse_match(b)
            k = m["index"]
            if k > len(self.matches):
                raise LiveError("match out of order")
            if k == len(self.matches):
                self.matches.append(m)
            else:
                self.matches[k] = m
        elif t == R_LAST:
            self.last = max(self.last, _u32(b, 0))
        elif t == R_END:
            self.ended = True
            self.end_why = _str(b, 0)[0] if len(b) >= 2 else ""


def end_record(why):
    w = why.encode("utf-8", "replace")[:200]
    payload = struct.pack("<H", len(w)) + w
    return struct.pack("<BI", R_END, len(payload)) + payload


def watch_env(path, result_path=None, status_path=None, controls=True, buffer_frames=None):
    """The game's environment to watch the live stream in `path` (a growing file)."""
    env = {"T5_NET_MODE": "replay", "T5_REPLAY_FILE": os.path.abspath(path), "T5_NET_START": "external"}
    if result_path:
        env["T5_REPLAY_RESULT"] = os.path.abspath(result_path)
    if status_path:
        env["T5_REPLAY_STATUS"] = os.path.abspath(status_path)
    if not controls:
        env["T5_REPLAY_CONTROLS"] = "0"
    if buffer_frames is not None:
        env["T5_REPLAY_LIVE_BUFFER"] = str(int(buffer_frames))
    return env


def live_path(folder, match_id):
    """Where a player's game writes the live stream of the session that begins with `match_id`."""
    from .proto import file_safe
    return os.path.join(folder, "live-" + file_safe(match_id) + EXT)


class Uploader:
    """The streamer's side: the game's live file, read as it grows, compressed into one zlib stream
    whose pieces go to the server in order (offset = compressed bytes before the piece)."""

    def __init__(self, path):
        self.path = path
        self.pos = 0                 # raw bytes of the file read
        self.z = zlib.compressobj(6)
        self.out = bytearray()       # compressed, not yet sent
        self.sent = 0                # compressed bytes handed out
        self.parser = LiveParser()
        self.finished = False        # the END record is read and compressed

    def _read(self, limit):
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read(limit)
        except OSError:
            return b""
        self.pos += len(data)
        return data

    def take(self, max_bytes):
        """Up to max_bytes of the compressed stream: [(offset, bytes), ...] in pieces of CHUNK."""
        if not self.finished and len(self.out) < max_bytes:
            data = self._read(max(65536, max_bytes * 8))
            if data:
                self.parser.feed(data)
                self.out += self.z.compress(data)
                if self.parser.ended and not self.parser.buf:
                    self.out += self.z.flush(zlib.Z_FINISH)
                    self.finished = True
                else:
                    self.out += self.z.flush(zlib.Z_SYNC_FLUSH)
        pieces = []
        while self.out and max_bytes > 0:
            n = min(CHUNK, max_bytes, len(self.out))
            pieces.append((self.sent, bytes(self.out[:n])))
            del self.out[:n]
            self.sent += n
            max_bytes -= n
        return pieces

    @property
    def done(self):
        return self.finished and not self.out


class Receiver:
    """The spectator's side: the compressed pieces in order -> a file of whole records."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "wb")
        self.z = zlib.decompressobj()
        self.expect = 0
        self.raw = 0
        self.parser = LiveParser()
        self.closed = False

    def add(self, offset, data):
        """One piece; False if it does not follow the last one (or the stream is broken)."""
        if self.closed or offset != self.expect:
            return False
        try:
            raw = self.z.decompress(data, MAX_RAW - self.raw + 1)
        except zlib.error:
            self.parser.bad = "damaged data"
            return False
        self.expect += len(data)
        self.raw += len(raw)
        if self.raw > MAX_RAW or self.z.unconsumed_tail:
            self.parser.bad = "too much data"
            return False
        whole = self.parser.feed(raw)
        if whole:
            self.f.write(whole)
            self.f.flush()
        return self.parser.bad is None

    def add_b64(self, offset, text):
        try:
            data = base64.b64decode(text, validate=True)
        except (ValueError, TypeError):
            return False
        return self.add(offset, data)

    def close(self, why=None):
        """Done: an END record for the game if the stream had none (it stopped early)."""
        if self.closed:
            return
        self.closed = True
        try:
            if not self.parser.ended and self.parser.started:
                self.f.write(end_record(why or "the stream stopped"))
            self.f.close()
        except OSError:
            pass
