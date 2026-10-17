"""Parse t5dr.exe's log into what the smoke checks need. No game, no Windows.

The game writes one line per event to stdout/stderr (the suite redirects both
to game.log). The lines that matter:

  [fps] 59.9 (frames 300..600 over 5.0s)        every 5 s while frames flip
  [audio-rate] 187.4 blocks/s (real time 187.5), silent 0.3%, dropped 0 frames/s, ...
                                                every 5 s with AUDIO_RATE=1
  [CRASH] ...                                   a fault the runtime caught
  [hle] unresolved NID 0x2BFFF084 ...           a firmware function nobody implements
  [frame-dump] <dir>\\frame_000060.ppm 1280x720 nonblack=921600
                                                LD_FRAME_DUMP's readback of the presented frame
  [WATCHDOG] ...                                the runtime's own stall sampler

LogScanner.feed(line, t, phase) takes one line plus the wall-clock time and
the scenario phase it arrived in (the suite tails the log while the game
runs); scan_text() parses a finished log with no timing.
"""
import re
from collections import namedtuple

Fps = namedtuple("Fps", "t value span phase")                 # span: seconds the value averages over
Audio = namedtuple("Audio", "t silent blocks dropped phase")
Crash = namedtuple("Crash", "t text phase")
Nid = namedtuple("Nid", "nid first_t first_phase count phases")
FrameDump = namedtuple("FrameDump", "t path width height nonblack phase")

RE_FPS = re.compile(r"^\[fps\] ([0-9.]+)(?: \(frames (\d+)\.\.(\d+) over ([0-9.]+)s\))?")
RE_AUDIO = re.compile(r"^\[audio-rate\] ([0-9.]+) blocks/s.*?silent ([0-9.]+)%(?:, dropped ([0-9.]+) frames/s)?")
RE_CRASH = re.compile(r"\[CRASH\]")
RE_NID = re.compile(r"\[hle\] unresolved NID (0x[0-9A-Fa-f]+)")
RE_DUMP = re.compile(r"^\[frame-dump\] (.+?\.ppm) (\d+)x(\d+) nonblack=(\d+)")
RE_WATCHDOG = re.compile(r"^\[WATCHDOG\] (\d+)s sample")
# Lines worth showing in the report when they appear (first occurrence each).
NOTABLE = [
    ("null-call", re.compile(r"^\[(null-call|null-write|null-read)\]|bctr to NULL")),
    ("opd", re.compile(r"guest_call: OPD .* not registered")),
    ("dialog", re.compile(r"^\[DIALOG\] ")),
    ("save-error", re.compile(r"^\[cellSaveData\] .*(error|fail)", re.I)),
    ("exception", re.compile(r"^\[(GUARD|EXC|abort)\]|unhandled exception|assertion", re.I)),
    ("out-of-memory", re.compile(r"0x80010004|out of memory|ENOMEM", re.I)),
]

FPS_SPAN = 5.0     # the runtime averages [fps] and [audio-rate] over 5 s


def norm_nid(s):
    return "0x" + s[2:].upper()


def shape(line):
    """A line with numbers and addresses blanked, to count repeats."""
    return re.sub(r"0x[0-9A-Fa-f]+|\d+", "N", line)[:120]


class LogScanner:
    def __init__(self):
        self.fps = []
        self.audio = []
        self.crashes = []
        self.nids = {}            # nid -> Nid (count/phases updated in place via _nid_update)
        self.frames = []
        self.watchdogs = 0
        self.notable = {}         # kind:shape -> [count, first_t, first_phase, first line]
        self.lines = 0

    def feed(self, line, t=None, phase=None):
        self.lines += 1
        line = line.rstrip("\r\n")
        m = RE_FPS.match(line)
        if m:
            span = float(m.group(4)) if m.group(4) else FPS_SPAN
            self.fps.append(Fps(t, float(m.group(1)), span, phase))
            return "fps"
        m = RE_AUDIO.match(line)
        if m:
            self.audio.append(Audio(t, float(m.group(2)), float(m.group(1)),
                                    float(m.group(3)) if m.group(3) else 0.0, phase))
            return "audio"
        m = RE_DUMP.match(line)
        if m:
            self.frames.append(FrameDump(t, m.group(1), int(m.group(2)), int(m.group(3)),
                                         int(m.group(4)), phase))
            return "frame"
        m = RE_NID.search(line)
        if m:
            nid = norm_nid(m.group(1))
            e = self.nids.get(nid)
            if e is None:
                self.nids[nid] = Nid(nid, t, phase, 1, [phase])
                return "nid-new"
            phases = e.phases if phase in e.phases else e.phases + [phase]
            self.nids[nid] = e._replace(count=e.count + 1, phases=phases)
            return "nid"
        if RE_CRASH.search(line):
            self.crashes.append(Crash(t, line.strip()[:400], phase))
            return "crash"
        if RE_WATCHDOG.match(line):
            self.watchdogs += 1
            return "watchdog"
        for kind, rx in NOTABLE:
            if rx.search(line):
                key = kind + ":" + shape(line)
                e = self.notable.get(key)
                if e is None:
                    self.notable[key] = [1, t, phase, line.strip()[:300]]
                    return "notable-new"
                e[0] += 1
                return "notable"
        return None

    def summary(self):
        return {
            "lines": self.lines,
            "fps": len(self.fps),
            "audio": len(self.audio),
            "crashes": len(self.crashes),
            "nids": sorted(self.nids),
            "frames": len(self.frames),
            "watchdogs": self.watchdogs,
        }


def scan_text(text):
    s = LogScanner()
    for line in text.splitlines():
        s.feed(line)
    return s


def fps_gaps(fps_times, start, end, first_grace=None):
    """Longest stretches without an [fps] line: [(from_t, to_t)] sorted by
    length, longest first. `fps_times` are the arrival times of the lines;
    the run's own start/end bound the search. Before the first line the game
    is still booting, so the search starts at the first line (or at
    start + first_grace if no line ever came)."""
    ts = sorted(t for t in fps_times if t is not None)
    if not ts:
        if first_grace is not None and end - start > first_grace:
            return [(start, end)]
        return []
    pts = ts + [end]
    gaps = [(a, b) for a, b in zip(pts, pts[1:]) if b > a]
    gaps.sort(key=lambda g: g[1] - g[0], reverse=True)
    return gaps
