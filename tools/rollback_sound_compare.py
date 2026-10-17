#!/usr/bin/env python3
"""Sound starts across rollbacks, from the play-call trace (T5_RB_SNDTRACE=1:
rb_sound.log of src/rollback/rb_sound.cpp; docs/ROLLBACK.md section 20).

    python tools/rollback_sound_compare.py RUN/host/rb_sound.log [REFERENCE/host/rb_sound.log]

Lines: G (a play call of a live frame: the sound starts), N (a play call of a
re-simulated frame no earlier run of that frame made: it starts now, late=
frames after its frame), D (a re-simulated frame's play call that an earlier
run of the frame made: not passed on, the sound keeps playing), O (a sound an
earlier run started that the re-simulation did not ask for: it plays on).

Per run: starts, doubled starts (the same sound started twice for one frame:
a G and an N with the same key -- 0 when deduplication works), late starts and
their lateness, sounds played on from mispredicted frames. With a reference
run (same scripts, no rollbacks): the sound effects (channel-less sounds;
voices are picked by a random draw the game takes from an unsynchronised
generator, so they are reported apart) the run started for each frame against
the reference's, frame by frame -- missing, extra, and started late.
"""
import collections
import re
import sys

RE = re.compile(r"^([GNDO]) (\d+) grp=(-?\d+) id=(-?\d+)(?: \(first run: -?\d+(?: at \d+)?\))? ch=(-?\d+) f=([0-9a-f]+)(?: pos=(\d))?.*?(?:late=(\d+))?$")


def parse(path):
    ev = []
    for line in open(path, errors="replace"):
        m = RE.match(line.strip())
        if not m:
            continue
        kind, f, grp, sid, ch, fl, pos, late = m.groups()
        ev.append((kind, int(f), int(grp), int(sid), int(ch), int(fl, 16), int(late or 0)))
    return ev


def key(grp, sid, ch, fl):
    return (grp, ch, fl, sid if ch < 0 else None)


def analyze(ev):
    starts = collections.defaultdict(list)    # frame -> keys started (G and N)
    late = []
    doubled = 0
    g_keys = collections.defaultdict(collections.Counter)
    orphans = collections.Counter()
    counts = collections.Counter(k for k, *_ in ev)
    for kind, f, grp, sid, ch, fl, lt in ev:
        k = key(grp, sid, ch, fl)
        if kind == "G":
            g_keys[f][k] += 1
            starts[f].append(k)
        elif kind == "N":
            if g_keys[f][k] > 0:
                doubled += 1
            starts[f].append(k)
            late.append(lt)
        elif kind == "O":
            orphans[(f, k)] += 1
    return dict(counts=counts, starts=starts, late=late, doubled=doubled, orphans=orphans)


def is_voice(k):
    return k[1] >= 0


def main():
    a = analyze(parse(sys.argv[1]))
    c = a["counts"]
    late = a["late"]
    print(f"{sys.argv[1]}: {c['G']} live starts, {c['N']} late starts (frames late: "
          f"{'min %d median %d max %d' % (min(late), sorted(late)[len(late) // 2], max(late)) if late else '-'}), "
          f"{c['D']} re-simulated starts kept from the first run, {c['O']} played on from mispredicted frames, "
          f"doubled starts {a['doubled']}")
    if len(sys.argv) < 3:
        return
    r = analyze(parse(sys.argv[2]))
    frames = sorted(set(a["starts"]) | set(r["starts"]))
    lo = max(min(a["starts"] or [0]), min(r["starts"] or [0]))
    hi = min(max(a["starts"] or [0]), max(r["starts"] or [0]))
    stats = {True: collections.Counter(), False: collections.Counter()}
    for f in frames:
        if f < lo or f > hi:
            continue
        got = collections.Counter(a["starts"].get(f, []))
        # sounds of this frame the run started only in a mispredicted run of it are not its timeline's
        for (of, k), n in a["orphans"].items():
            if of == f:
                got[k] -= n
        want = collections.Counter(r["starts"].get(f, []))
        for k in set(got) | set(want):
            v = is_voice(k)
            g, w = max(got[k], 0), want[k]
            stats[v]["matched"] += min(g, w)
            stats[v]["missing"] += max(w - g, 0)
            stats[v]["extra"] += max(g - w, 0)
            stats[v]["reference"] += w
    for v in (False, True):
        s = stats[v]
        print(f"  {'voices' if v else 'effects'} vs reference (frames {lo}-{hi}): {s['reference']} in the reference, "
              f"{s['matched']} started for the same frame, {s['missing']} missing, {s['extra']} extra")


if __name__ == "__main__":
    main()
