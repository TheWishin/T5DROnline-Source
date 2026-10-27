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


COSTUME_BLOCK = 0x108          # src/directfight/costume_logic.h kBlock (format 3)


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
    hf = r.u32()
    out["rollback"] = bool(hf & 1)
    # format 4: bit 1 the select screen's generator mixes the match number (older: one seed per session),
    # bit 2 Jinpachi and the random cell were offered (T5_NET_UNLOCKS=open)
    out["select_mix"] = out["version"] >= 4 and bool(hf & 2)
    out["unlocks"] = "open" if out["version"] >= 4 and hf & 4 else "closed"
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
        m["costumes"] = None    # format 3: the custom costume blocks both sides fought in (2 x 0x108 bytes, hex)
        if out["version"] >= 3 and r.u32() & 1:
            m["costumes"] = [b[r.i:r.i + COSTUME_BLOCK].hex(), b[r.i + COSTUME_BLOCK:r.i + 2 * COSTUME_BLOCK].hex()]
            r.i += 2 * COSTUME_BLOCK
        # format 5: the match's rules (src/netplay/match_rules.h): bit 0 a training fight, bits 8-15 / 16-23 each
        # side's health in percent (0 = 100)
        rules = r.u32() if out["version"] >= 5 else 0
        m["training"] = bool(rules & 1)
        m["life"] = [((rules >> 8) & 0xFF) or 100, ((rules >> 16) & 0xFF) or 100]
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
    except (TypeError, ValueError, OverflowError, OSError):     # (Windows: OSError before 1970)
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
        self.ended = _local_time(m.get("ended"))

    @property
    def fighters(self):
        """'Jin vs Lili' with this player's fighter first"""
        mine, theirs = (self.p1, self.p2) if self.slot == 0 else (self.p2, self.p1)
        return f"{fighter_name(mine)} vs {fighter_name(theirs)}"

    def key(self):
        return (self.when.timestamp() if self.when else 0.0, self.index)


HISTORY_WINDOW = 15 * 60        # seconds between the lobby's time of a match and this PC's replay of it, at most


def for_history(entries, when, mine=None, theirs=None, opponent=None, score=None, window=HISTORY_WINDOW):
    """The replay Entry of a match from the lobby's match history (the Online tab's profile, 1.1.5), or None.

    when: the lobby's unix time of the match (its end; the server's clock, so a few minutes off this PC's are fine);
    mine / theirs: the fighters' ids (fighters.json "id", the replay's own numbers); opponent: the name (only
    compared when the replay kept names); score: [mine, theirs] (only prefers one of two close candidates). The
    replay ended (or started) closest to `when` wins."""
    best = None
    for e in entries:
        ref = e.ended or e.when
        if ref is None:
            continue
        try:
            dt = abs(ref.timestamp() - float(when))
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        if dt > window:
            continue
        mine_e, theirs_e = (e.p1, e.p2) if e.slot == 0 else (e.p2, e.p1)
        if mine is not None and theirs is not None and (mine_e, theirs_e) != (mine, theirs):
            continue
        if opponent and e.opponent and e.opponent.lower() != str(opponent).lower():
            continue
        off = 0 if (not score or tuple(score) == tuple(e.score)) else 1
        key = (off, dt)
        if best is None or key < best[0]:
            best = (key, e)
    return best[1] if best else None


def list_replays(folder):
    """Every match of every replay file in folder, newest first; files that cannot be read are skipped."""
    out = []
    for path in glob.glob(os.path.join(folder, "*" + EXT)):
        try:
            h = read_header(path)
            # a header line that is JSON but not what the game writes (a damaged or hand-made file: a side other
            # than 0/1, a match that is not an object, ...) skips this file, not the whole list
            rows = [Entry(path, h, k) for k in range(1, len(h["matches"]) + 1)]
            for e in rows:
                e.key()
        except (ReplayError, LookupError, TypeError, ValueError, AttributeError, OverflowError, OSError):
            continue
        out += rows
    out.sort(key=lambda e: e.key(), reverse=True)
    return out


def _by_age(folder):
    """The replay files in folder, newest first. A file that goes between the listing and its time (deleted by the
    Replays tab or another launcher pruning at the same moment) is left out: prune() runs while the launcher starts,
    and a FileNotFoundError there kept the launcher from opening."""
    out = []
    for p in glob.glob(os.path.join(folder, "*" + EXT)):
        try:
            out.append((os.path.getmtime(p), p))
        except OSError:
            continue
    out.sort(reverse=True)
    return [p for _t, p in out]


def newest(folder):
    """The newest replay file in folder, or None."""
    files = _by_age(folder)
    return files[0] if files else None


def prune(folder, keep=DEFAULT_KEEP):
    """Delete all but the newest `keep` replay files; returns how many went."""
    files = _by_age(folder)
    gone = 0
    for p in files[keep:]:
        try:
            os.remove(p)
            gone += 1
        except OSError:
            pass
    return gone


def playback_env(path, match=0, result_path=None, controls=True):
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
        if version >= 3:        # the costume blocks stay (no name in them)
            flags = struct.unpack_from("<I", b, r.i)[0]
            n = 4 + (2 * COSTUME_BLOCK if flags & 1 else 0)
            out += b[r.i:r.i + n]
            r.i += n
        if version >= 5:        # the match's rules word stays
            out += b[r.i:r.i + 4]
            r.i += 4
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
