#!/usr/bin/env python3
"""Check the practice reset in the game (docs/TRAINING.md "The reset is the round's first state").

    python tools/practice_state_check.py [--exe build/cmake/t5dr.exe] [--root DIR] [--out DIR] [--keep]
                                         [--only resets|frames] [--frames N] [--passes K] [--places]

Two offline Practice runs through the smoke harness's menu driver (title -> PRACTICE -> the cursor's fighters):

resets   P1's pad file walks away, sidesteps to both sides, throws the dummy (1+3 and 2+4: the fighters change
         sides), walks around it, launches it -- and presses SELECT+3 after each, the launcher's while the dummy
         is in the air; then ten more resets in a row, each after a walk-in and a throw, sidesteps and a jab, or a
         launcher. After EVERY reset the practice log must show both fighters at the round's first places (to a
         unit), on their first sides (the game's own side flag of each fighter), facing each other and standing,
         two seconds later too.

frames   T5_PRACTICE_STATE_TEST=N:K: the game plays a scripted P1 (walks in, steps, sidesteps, attacks, throws, a
         launcher) for N frames from the kept state, puts the state back and plays the same pad again, K times,
         and logs the gameplay hash (rb_state.cpp state_game_hash: pads, input ring, frame clock, random
         generators, round state, both fighters) of every frame. Every frame after a reset must have the hash the
         same frame had the first time: a reset plays the same frames as the fresh round.

--places runs "resets" with the reset that only moves the places (T5_PRACTICE_STATE=0, the reset before 1.2.3)
and prints what it does; it is expected to fail the checks (sides flipped, a fighter off its place, turned away).

The game runs muted and minimised; nothing of it is kept unless --keep / --out. Exit 0 = PASS.
"""
import argparse
import math
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from game import Game, find_game_root  # noqa: E402
import scenarios as sc  # noqa: E402

PLACE = re.compile(r"^(\d+) (.+?) P1 (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) dummy (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)$")
STATE = re.compile(r"^(\d+) (.+?): round \d+ phase \d+ P1 y (\S+) hips \S+ move (\w+) class \w+ act (\d) right (\d) "
                   r"dummy y (\S+) hips \S+ move (\w+) class \w+ act (\d) right (\d)")
HASH = re.compile(r"^\d+ hash (\d+) (\d+) (\w+)$")
HEALTH = re.compile(r"^\d+ test (\d+) (\d+) health (-?\d+) (-?\d+)$")


def sel(g, btn="CROSS"):
    g.hold("SELECT")
    g.wait(0.1)
    g.hold("SELECT", btn)
    g.wait(0.15)
    g.hold("SELECT")
    g.wait(0.1)
    g.release()
    g.wait(0.3)


def tap(g, *btns, ms=80, gap=0.25):
    g.hold(*btns)
    g.wait(ms / 1000)
    g.release()
    g.wait(gap)


def walk_in(g, s):
    g.hold("RIGHT")
    g.wait(s)
    g.release()
    g.wait(0.2)


def launcher(g):
    g.hold("DOWN", "RIGHT")
    g.wait(0.08)
    g.hold("DOWN", "RIGHT", "TRIANGLE")
    g.wait(0.12)
    g.release()


def drive_resets(g):
    g.wait(2)
    g.hold("LEFT")                                      # walk away
    g.wait(2)
    g.release()
    g.wait(0.4)
    sel(g)
    g.wait(3)
    for _ in range(5):                                  # sidesteps into the background
        tap(g, "UP", ms=60, gap=0.45)
    sel(g)
    g.wait(3)
    for _ in range(5):                                  # ... into the foreground, then in
        tap(g, "DOWN", ms=60, gap=0.45)
    walk_in(g, 1.0)
    sel(g)
    g.wait(3)
    walk_in(g, 1.6)                                     # a throw, the reset at once
    tap(g, "TRIANGLE", "CIRCLE", ms=100, gap=0.6)
    sel(g)
    g.wait(5)
    walk_in(g, 1.6)                                     # the other throw, the reset once it is over
    tap(g, "SQUARE", "CROSS", ms=100, gap=3.5)
    sel(g)
    g.wait(4)
    walk_in(g, 1.2)                                     # around the dummy
    tap(g, "UP", ms=50, gap=0.08)
    g.hold("UP")
    g.wait(2.5)
    g.release()
    g.wait(0.2)
    sel(g)
    g.wait(3)
    walk_in(g, 1.4)                                     # a launcher, the reset while the dummy is in the air
    launcher(g)
    g.wait(0.35)
    sel(g)
    g.wait(5)
    for i in range(10):                                 # ten in a row
        walk_in(g, 1.3)
        if i % 3 == 0:
            tap(g, "TRIANGLE", "CIRCLE", ms=100, gap=0.3)
        elif i % 3 == 1:
            for _ in range(3):
                tap(g, "UP", ms=60, gap=0.3)
            tap(g, "SQUARE", ms=60, gap=0.1)
        else:
            launcher(g)
            g.wait(0.2)
        sel(g)
        g.wait(4.5)


def check_resets(lines, want_state=True, want=17):
    """-> (ok, summary)"""
    ok = True

    def good(cond, what):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")

    places, states = [], []
    for ln in lines:
        m = PLACE.match(ln)
        if m:
            places.append((int(m[1]), m[2], [float(x) for x in m.groups()[2:]]))
            continue
        m = STATE.match(ln)
        if m:
            states.append((int(m[1]), m[2], m[4], int(m[6]), m[8], int(m[10]), float(m[3]), float(m[7])))
    start = next((p for p in places if p[1] == "round start:"), None)
    st0 = next((s for s in states if s[1] == "practice start"), None)
    if not start or not st0:
        good(False, "no round start in the practice log")
        return False, "no round start"
    sx = start[2]
    print(f"  round start: P1 ({sx[0]:.0f}, {sx[1]:.0f}) facing {sx[2]:.2f}, dummy ({sx[3]:.0f}, {sx[4]:.0f}) facing "
          f"{sx[5]:.2f}; side flags P1 {st0[3]} dummy {st0[5]}")
    kept = any(" the round's first state kept" in ln for ln in lines)
    good(kept == want_state, "the round's first state " + ("kept" if kept else "not kept"))
    resets = [p for p in places if p[1] == ("state restored:" if kept else "reset round start:")]
    good(len(resets) >= want, f"{len(resets)} resets (want {want})")
    good(not any("did not come back" in ln for ln in lines) or not kept, "every reset put the state back")

    def off(v):
        return math.hypot(v[0] - sx[0], v[1] - sx[1]), math.hypot(v[3] - sx[3], v[4] - sx[4])

    def face_err(v):
        out = []
        for me, ot in ((0, 3), (3, 0)):
            want_a = math.atan2(v[ot] - v[me], v[ot + 1] - v[me + 1])
            out.append(abs((v[me + 2] - want_a + math.pi) % (2 * math.pi) - math.pi))
        return max(out)
    bad = flips = worst_off = 0
    worst_face = 0.0
    for i, r in enumerate(resets):
        f = r[0]
        before = [p for p in places if p[0] <= f and p[1] not in (r[1], "30 frames later:")]
        b = off(before[-1][2]) if before else (0, 0)
        later = [p for p in places if f + 100 <= p[0] <= f + 150 and p[1] == "places:"]
        sts = [s for s in states if f + 30 <= s[0] <= f + 125 and s[1] == "after reset"]
        v = later[-1][2] if later else r[2]
        o = off(v)
        fe = face_err(v)
        sides = (sts[-1][3], sts[-1][5]) if sts else None
        stand = bool(sts) and sts[-1][2].startswith("8001") and sts[-1][4].startswith("8001")
        flipped = sides is not None and sides != (st0[3], st0[5])
        this_bad = max(o) > 1.0 or fe > 0.05 or flipped or not stand or not sts
        bad += this_bad
        flips += flipped
        worst_off = max(worst_off, *o)
        worst_face = max(worst_face, fe)
        print(f"  {'ok  ' if not this_bad else 'BAD '} reset {i + 1:2d} at frame {f}: before it P1 {b[0]:.0f} / dummy {b[1]:.0f} "
              f"from their first places; 2 s after it {o[0]:.0f} / {o[1]:.0f}, facing off by {fe:.2f}, sides "
              f"{'as at the start' if not flipped else 'FLIPPED'}{'' if stand else ', not both standing'}")
    summary = (f"{len(resets)} resets, {bad} bad, {flips} with the sides flipped, worst place {worst_off:.0f} units off, "
               f"worst facing {worst_face:.2f} rad off")
    good(bad == 0, summary)
    return ok, summary


def check_frames(lines, frames, passes):
    ok = True

    def good(cond, what):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")

    seq, health = {}, {}
    for ln in lines:
        m = HASH.match(ln)
        if m:
            seq.setdefault(int(m[1]), {})[int(m[2])] = m[3]
            continue
        m = HEALTH.match(ln)
        if m:
            health.setdefault(int(m[1]), []).append((int(m[3]), int(m[4])))
    base = seq.get(0, {})
    good(len(base) == frames + 1, f"the fresh round: {len(base)} frames with a hash (want {frames + 1})")
    good(len(set(base.values())) > frames * 0.9, f"{len(set(base.values()))} different hashes among them")
    h0 = health.get(0, [])
    good(h0 and min(h[1] for h in h0) < h0[0][1], "the scripted P1 hit the dummy (its health "
         + (f"{h0[0][1]} -> {min(h[1] for h in h0)})" if h0 else "unknown)"))
    total = differ = 0
    for k in range(1, passes + 1):
        got = seq.get(k, {})
        d = [f for f in sorted(base) if f in got and got[f] != base[f]]
        total += len(got)
        differ += len(d)
        good(len(got) == frames + 1 and not d, f"after reset {k}: {len(got)} frames, {len(d)} differ from the fresh round"
             + (f" (first at frame {d[0]})" if d else ""))
    summary = f"{passes} resets, {total} frames compared with the fresh round's, {differ} different"
    good(total and not differ, summary)
    return ok, summary


def run(out, exe, root, env, drive):
    log = os.path.join(out, "practice.log")
    env = dict({"T5_PRACTICE": "1", "T5_PRACTICE_LOG": log, "T5_PRACTICE_DIR": "-", "T5_TRAINING": "frames",
                "PS3_AUDIO_MUTE": "1"}, **env)
    g = Game(out, exe=exe, root=root, env=env)
    try:
        g.start()
        if sc.to_title(g):
            g.phase("practice-select", "menu")
            sc.pick_mode(g, sc.PRACTICE, wait=3.0)
            if sc.start_fight(g, skip=False):
                g.release()
                drive(g)
    finally:
        g.stop()
    if not os.path.exists(log):
        print("no practice log: the game did not reach the fight, or T5_PRACTICE did not take")
        return None
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=None, help="t5dr.exe (default: <root>/build/cmake/t5dr.exe)")
    ap.add_argument("--root", default=None, help="the build's output root with game/vfs (build_game.py --out)")
    ap.add_argument("--out", default="", help="working directory (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="keep the working directory")
    ap.add_argument("--only", choices=("resets", "frames"), help="one of the two runs")
    ap.add_argument("--frames", type=int, default=1800, help="frames: frames played from the state (default 1800)")
    ap.add_argument("--passes", type=int, default=3, help="frames: resets (default 3)")
    ap.add_argument("--places", action="store_true", help="resets with T5_PRACTICE_STATE=0 (the reset before 1.2.3)")
    a = ap.parse_args()
    root = os.path.abspath(a.root) if a.root else find_game_root()
    exe = os.path.abspath(a.exe) if a.exe else os.path.join(root, "build", "cmake",
                                                            "t5dr.exe" if os.name == "nt" else "t5dr")
    out = os.path.abspath(a.out) if a.out else tempfile.mkdtemp(prefix="practice_state_check_")
    ok = True
    results = []
    if a.only != "frames":
        print("resets" + (" (T5_PRACTICE_STATE=0: the places only)" if a.places else ""))
        lines = run(os.path.join(out, "resets"), exe, root, {"T5_PRACTICE_STATE": "0"} if a.places else {}, drive_resets)
        r = check_resets(lines, want_state=not a.places) if lines is not None else (False, "no log")
        ok &= r[0]
        results.append("resets: " + r[1])
    if a.only != "resets" and not a.places:
        print("frames")
        lines = run(os.path.join(out, "frames"), exe, root, {"T5_PRACTICE_STATE_TEST": f"{a.frames}:{a.passes}"},
                    lambda g: g.wait(a.frames * (a.passes + 1) / 60 + 8))
        r = check_frames(lines, a.frames, a.passes) if lines is not None else (False, "no log")
        ok &= r[0]
        results.append("frames: " + r[1])
    for r in results:
        print(r)
    if not a.keep and not a.out:
        shutil.rmtree(out, ignore_errors=True)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
