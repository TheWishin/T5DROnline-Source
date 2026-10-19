"""Replays: the files the game writes for every online session, read for the launcher's Replays tab,
the problem report and the tools (docs/REPLAYS.md).

Nothing here imports tkinter or the launcher, so it runs (and is tested) from a console:

    python launcher/replays.py <native folder>\\replays          (list them)

A file (written by src/netplay/replay.cpp):

    line 1   "T5REPLAY 1"
    line 2   one line of JSON: build id, date, rollback or lockstep, this PC's side (slot), the matches
             (fighters, costumes, stage, rounds, winner, score, hash, names when kept)
    rest     a zlib stream with what the game plays back: inputs of both players for every frame,
             the sync points (seeds, frame counters), state hashes every N frames

One file is one netplay session (one opponent, the first match and every rematch); the list has one row
per match. Watching match k of a session plays the matches before it too (fast): a rematch starts from
what the match before it left.
"""
import datetime
import glob
import json
import os
import struct
import zlib

MAGIC = b"T5REPLAY 1\n"
EXT = ".t5replay"
DEFAULT_KEEP = 200              # newest files kept in native/replays (older ones are deleted at launcher start)

NAMES = ["Paul", "Law", "Lei", "King", "Yoshimitsu", "Nina", "Hwoarang", "Xiaoyu", "Christie", "Jin", "Julia", "Kuma",
         "Panda", "Bryan", "Heihachi", "Kazuya", "Lee", "Steve", "Marduk", "Mokujin", "Eddy", "Jack-5", "Roger Jr.",
         "Anna", "Wang", "Ganryu", "Asuka", "Bruce", "Baek", "Devil Jin", "Raven", "Feng", "Armor King", "Lili",
         "Dragunov", "Jinpachi"]


class ReplayError(Exception):
    pass


def fighter_name(cid):
    try:
        return NAMES[int(cid)]
    except (TypeError, ValueError, IndexError):
        return "?"


def read_header(path):
    """The JSON line of a replay file (dict). ReplayError when it is not one."""
    try:
        with open(path, "rb") as f:
            head = f.read(len(MAGIC))
            if head != MAGIC:
                raise ReplayError("not a T5DR replay")
            line = f.readline(1 << 20)
    except OSError as e:
        raise ReplayError(str(e)) from e
    try:
        h = json.loads(line.decode("utf-8", errors="replace"))
    except ValueError as e:
        raise ReplayError("damaged header") from e
    if not isinstance(h, dict) or not isinstance(h.get("matches"), list):
        raise ReplayError("damaged header")
    return h


def split(path):
    """(header bytes incl. the two lines, zlib payload bytes)"""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(MAGIC):
        raise ReplayError("not a T5DR replay")
    nl = data.find(b"\n", len(MAGIC))
    if nl < 0:
        raise ReplayError("no data after the header")
    return data[:nl + 1], data[nl + 1:]


class _R:
    def __init__(self, b):
        self.b, self.i = b, 0

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.i)[0]
        self.i += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.i)[0]
        self.i += 4
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.b, self.i)[0]
        self.i += 8
        return v

    def s(self):
        n = struct.unpack_from("<H", self.b, self.i)[0]
        self.i += 2
        v = self.b[self.i:self.i + n].decode("utf-8", errors="replace")
        self.i += n
        return v


def read_payload(path):
    """Everything the game plays back, decoded (dict): flags, matches, sync points, hashes and the
    inputs as two lists of (buttons, lx, ly, rx, ry) per frame. For tools and tests."""
    _, z = split(path)
    try:
        b = zlib.decompress(z)
    except zlib.error as e:
        raise ReplayError("damaged data") from e
    if b[:4] != b"T5RP":
        raise ReplayError("not a replay payload")
    r = _R(b)
    r.i = 4
    out = {"version": r.u32()}
    out["rollback"] = bool(r.u32() & 1)
    out["slot"], out["delay"], out["rb_delay"] = r.u32(), r.u32(), r.i32()
    out["seed"], out["match_seed"], frames, out["hash_every"] = r.u32(), r.u32(), r.u32(), r.u32()
    if out["version"] >= 2:
        out["last_frame"] = r.u32()
    else:                       # format 1 (development files): the inputs reach the input delay past the last frame
        dl = out["rb_delay"] if out["rollback"] and out["rb_delay"] >= 0 else out["delay"]
        out["last_frame"] = max(0, frames - dl - 1)
    out["frames"] = frames
    ms = []
    for _ in range(r.u32()):
        m = {"start": r.u32(), "end": r.u32(), "frames": r.u32(), "hash_frame": r.u32(), "desync": r.u32()}
        fl = r.u32()
        m.update(have_result=bool(fl & 1), have_hash=bool(fl & 2), complete=bool(fl & 4))
        for k in ("p1", "p2", "b1", "b2", "m1", "m2", "stage", "rounds", "pick", "winner", "s1", "s2"):
            m[k] = r.i32()
        m["hash"] = "%016x" % r.u64()
        m["names"] = [r.s(), r.s()]
        ms.append(m)
    out["matches"] = ms
    bars = []
    for _ in range(r.u32()):
        x = {"kind": r.u32(), "f": r.u32(), "nf": r.u32(), "seed": r.u32(), "state": bool(r.u32() & 1)}
        x["clock"] = r.u64()
        x["c"] = [r.u32(), r.u32(), r.u32()]
        bars.append(x)
    for m in ms:                # never before a recorded match's end (format 1's estimate; a file written at the
        if m["have_result"] and out["last_frame"] < m["end"] < frames:   # very frame of a result)
            out["last_frame"] = m["end"]
    out["sync_points"] = bars
    out["hashes"] = [(r.u32(), "%016x" % r.u64()) for _ in range(r.u32())]
    cols = []
    for _c in range(12):
        prev = (0, 0, 128, 128, 128, 128)[_c % 6]
        col = bytearray(frames)
        for f in range(frames):
            prev ^= b[r.i + f]
            col[f] = prev
        r.i += frames
        cols.append(col)
    out["inputs"] = [[(cols[p * 6][f] | (cols[p * 6 + 1][f] << 8), cols[p * 6 + 2][f], cols[p * 6 + 3][f],
                       cols[p * 6 + 4][f], cols[p * 6 + 5][f]) for f in range(frames)] for p in (0, 1)]
    return out


def _local_time(iso):
    """'2026-10-19T13:04:12Z' -> a local datetime (None when unreadable)"""
    try:
        dt = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone()
    except (TypeError, ValueError):
        return None


class Entry:
    """One row of the Replays list: one match of a recorded session."""

    def __init__(self, path, header, index):
        self.path = path
        self.header = header
        self.index = index                      # 1-based match number in the session
        m = header["matches"][index - 1]
        self.match = m
        self.slot = int(header.get("slot") or 0)
        self.when = _local_time(m.get("started") or header.get("created"))
        self.p1, self.p2 = m.get("p1"), m.get("p2")
        self.mode = header.get("mode", "?")
        self.build = header.get("build", "")
        names = m.get("names") or []
        self.me = names[self.slot] if len(names) == 2 else ""
        self.opponent = names[1 - self.slot] if len(names) == 2 else ""
        self.complete = bool(m.get("complete"))
        w = m.get("winner")
        self.won = None if w is None else (w == self.slot)
        sc = m.get("score") or [0, 0]
        self.score = (sc[self.slot], sc[1 - self.slot]) if len(sc) == 2 else (0, 0)
        self.rematch = index > 1

    @property
    def fighters(self):
        """'Jin vs Lili' with this player's fighter first"""
        mine, theirs = (self.p1, self.p2) if self.slot == 0 else (self.p2, self.p1)
        return f"{fighter_name(mine)} vs {fighter_name(theirs)}"

    def key(self):
        return (self.when.timestamp() if self.when else 0.0, self.index)


def list_replays(folder):
    """Every match of every replay file in folder, newest first; files that cannot be read are skipped."""
    out = []
    for path in glob.glob(os.path.join(folder, "*" + EXT)):
        try:
            h = read_header(path)
        except ReplayError:
            continue
        for k in range(1, len(h["matches"]) + 1):
            out.append(Entry(path, h, k))
    out.sort(key=lambda e: e.key(), reverse=True)
    return out


def newest(folder):
    """The newest replay file in folder, or None."""
    files = glob.glob(os.path.join(folder, "*" + EXT))
    return max(files, key=os.path.getmtime) if files else None


def prune(folder, keep=DEFAULT_KEEP):
    """Delete all but the newest `keep` replay files; returns how many went."""
    files = sorted(glob.glob(os.path.join(folder, "*" + EXT)), key=os.path.getmtime, reverse=True)
    gone = 0
    for p in files[keep:]:
        try:
            os.remove(p)
            gone += 1
        except OSError:
            pass
    return gone


def playback_env(path, match=0, result_path=None, speed=None, controls=True):
    """The game's environment for watching match `match` (1-based; 0 = the whole session) of a replay:
    netplay's local mode fed by the file, the loop it was recorded with, direct fight."""
    read_header(path)            # (a file that is not a replay raises ReplayError here, not in the game)
    env = {
        "T5_NET_MODE": "replay",
        "T5_REPLAY_FILE": os.path.abspath(path),
        "T5_REPLAY_MATCH": str(int(match or 0)),
        "T5_NET_START": "external",
    }
    # (rollback or lockstep: the game takes it from the file; T5_RB_MODE does not apply to a replay)
    if result_path:
        env["T5_REPLAY_RESULT"] = os.path.abspath(result_path)
    if speed is not None:
        env["T5_REPLAY_SPEED"] = str(int(speed))
    if not controls:
        env["T5_REPLAY_CONTROLS"] = "0"
    return env


def read_result(path):
    """The game's verdict after a playback (T5_REPLAY_RESULT), or None."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def scrub_header(header_bytes, placeholder="<player>"):
    """A replay's two header lines with every player name replaced (problem reports: names never leave the
    PC). The binary part has no names in the JSON sense but keeps the HUD names: report copies use
    strip_names() instead, which rewrites the whole file."""
    lines = header_bytes.split(b"\n", 2)
    try:
        h = json.loads(lines[1].decode("utf-8"))
    except (IndexError, ValueError):
        return header_bytes
    for m in h.get("matches", []):
        if m.get("names"):
            m["names"] = [placeholder if n else "" for n in m["names"]]
    return MAGIC + json.dumps(h).encode("utf-8") + b"\n"


def strip_names(path, placeholder="<player>"):
    """The bytes of a copy of the replay without any player name: the JSON's names become `placeholder`,
    the HUD names in the binary part are emptied (the playback then shows the game's "Unknown")."""
    head, z = split(path)
    try:
        b = bytearray(zlib.decompress(z))
    except zlib.error as e:
        raise ReplayError("damaged data") from e
    # walk to the names in the match table and drop them
    r = _R(bytes(b))
    version = struct.unpack_from("<I", b, 4)[0]
    # magic, version, flags/slot/delay/rb_delay/seed/match seed, frames, hash every (, last frame)
    r.i = 4 + 4 + 4 * 6 + 4 * 2 + (4 if version >= 2 else 0)
    nm = r.u32()
    out = bytearray(b[:r.i])
    for _ in range(nm):
        fixed = 6 * 4 + 12 * 4 + 8
        out += b[r.i:r.i + fixed]
        r.i += fixed
        for _n in range(2):
            ln = struct.unpack_from("<H", b, r.i)[0]
            r.i += 2 + ln
            out += b"\0\0"
    out += b[r.i:]
    if r.i > len(b):
        raise ReplayError("damaged data")
    return scrub_header(head, placeholder) + zlib.compress(bytes(out), 9)


def main():
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    for e in list_replays(folder):
        res = "-" if not e.complete else ("won" if e.won else "lost") + " %d-%d" % e.score
        print(f"{e.when:%Y-%m-%d %H:%M}" if e.when else "?", e.fighters, res, e.opponent or "?", e.mode,
              os.path.basename(e.path), f"match {e.index}")


if __name__ == "__main__":
    main()
