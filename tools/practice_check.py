#!/usr/bin/env python3
"""Check the practice tools in the game (docs/TRAINING.md "Practice tools").

    python tools/practice_check.py [--exe build/cmake/t5dr.exe] [--root DIR] [--out DIR] [--keep]

Starts the game through the smoke harness's menu driver (tools/smoke: title -> PRACTICE -> the cursor's
fighters -> the fight) with the practice tools on (T5_PRACTICE=1, T5_PRACTICE_LOG) and drives P1's pad file:
SELECT+3 after walking away, the four wall resets (each followed by SELECT+3), the dummy's behaviours, and a
recording played once and in a loop. The practice log must show

    the fighters 2000 apart at the round start; every reset still in place 30 frames later;
    a wall found for every wall reset, the other fighter 1100 in front of it, facing each other;
    the slot recorded, played and looped; the dummy's behaviours cycled.

The game runs muted and minimised; nothing of it is kept unless --keep. Exit 0 = PASS.
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
GAP = 1100.0


def sel(g, *dirs, btn="CROSS"):
    """SELECT held, then the direction(s), then the button; let go in reverse order"""
    g.hold("SELECT")
    g.wait(0.1)
    if dirs:
        g.hold("SELECT", *dirs)
        g.wait(0.1)
    if btn:
        g.hold("SELECT", *dirs, btn)
        g.wait(0.15)
        g.hold("SELECT", *dirs)
        g.wait(0.1)
    g.hold("SELECT")
    g.wait(0.1)
    g.release()
    g.wait(0.3)


def drive(g):
    g.wait(2)
    g.hold("LEFT")
    g.wait(2)
    g.release()
    g.wait(0.5)
    sel(g)                                              # round start
    g.wait(1)
    for dirs in (("RIGHT",), ("LEFT",), ("DOWN", "RIGHT"), ("DOWN", "LEFT")):
        sel(g, *dirs)                                   # a wall reset
        g.wait(1)
        g.shot("wall-" + "".join(d[0] for d in dirs).lower(), expect="any", settle=1.0)
        sel(g)                                          # back to the round start
        g.wait(1)
    for _ in range(5):                                  # the dummy's behaviours, once round
        sel(g, "RIGHT", btn=None)
        g.hold("RIGHT")                                 # walk in and jab: the first jab hits, then
        g.wait(0.4)                                     # the blocking dummy guards
        g.release()
        for _ in range(3):
            g.press("SQUARE", gap=300)
        g.wait(1.5)
        sel(g)
    sel(g, btn="SQUARE")                                # record slot 1: P1's pad plays the dummy
    g.hold("RIGHT")
    g.wait(1)
    g.release()
    g.press("SQUARE", gap=300)
    sel(g, btn="SQUARE")
    sel(g, btn="TRIANGLE")                              # play once
    g.wait(3)
    sel(g, btn="CIRCLE")                                # loop, then stop
    g.wait(4)
    sel(g, btn="CIRCLE")
    g.wait(1)


def check(log_lines):
    ok = True
    places = [m.groups() for m in (PLACE.match(ln) for ln in log_lines) if m]
    print(f"{len(log_lines)} log lines, {len(places)} with places")

    def good(cond, what):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")

    def xyz(p):
        return [float(v) for v in p[2:]]
    start = [p for p in places if p[1] == "round start:"]
    good(start and abs(math.hypot(xyz(start[0])[0] - xyz(start[0])[3], xyz(start[0])[1] - xyz(start[0])[4]) - 2000) < 50,
         "round start: the fighters 2000 apart" + (f" ({xyz(start[0])})" if start else ""))
    s = xyz(start[0]) if start else None
    resets = [i for i, p in enumerate(places) if p[1] == "reset round start:"]
    later = [i for i, p in enumerate(places) if p[1] == "30 frames later:"]
    good(len(resets) >= 5, f"{len(resets)} round-start resets (want 5)")
    for i in resets:
        after = next((j for j in later if j > i), None)
        if s and after is not None:
            a = xyz(places[after])
            good(abs(a[0] - s[0]) < 60 and abs(a[1] - s[1]) < 60 and abs(a[3] - s[3]) < 60 and abs(a[4] - s[4]) < 60,
                 f"30 frames after the reset at frame {places[i][0]}: P1 ({a[0]:.0f}, {a[1]:.0f}) "
                 f"dummy ({a[3]:.0f}, {a[4]:.0f})")
    walls = [p for p in places if p[1] == "wall:"]
    nowall = [p for p in places if p[1].startswith("no wall")]
    good(len(walls) == 4 and not nowall, f"{len(walls)} walls found, {len(nowall)} without a wall (want 4 / 0)")
    for w in walls:
        v = xyz(w)
        d = math.hypot(v[0] - v[3], v[1] - v[4])
        good(abs(d - GAP) < 5, f"at the wall: {d:.0f} apart (want {GAP:.0f})")
    good(any(" record slot 1" in ln for ln in log_lines) and any(" play slot 1" in ln for ln in log_lines)
         and any(" loop slot 1" in ln for ln in log_lines), "slot 1 recorded, played and looped")
    modes = [ln.split()[2] for ln in log_lines if re.match(r"^\d+ dummy \w+$", ln)]
    good(modes[:5] == ["block", "crouch", "walk", "step", "game"], f"dummy behaviours cycled: {modes}")
    sets = [int(m.group(1)) for m in (re.match(r"^\d+ training dummy setting (\d+)", ln) for ln in log_lines) if m]
    good(4 in sets, "blocks after the first hit: the game's guard against all attacks (setting 4) after the hit")
    good(10 in sets, "crouch / walk / step / recordings: CONTROLLER (setting 10)")
    good(any("(the player's)" in ln for ln in log_lines), "the player's own TRAINING DUMMY back afterwards")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=None, help="t5dr.exe (default: <root>/build/cmake/t5dr.exe)")
    ap.add_argument("--root", default=None, help="the build's output root with game/vfs (build_game.py --out)")
    ap.add_argument("--out", default="", help="working directory (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="keep the working directory")
    a = ap.parse_args()
    root = os.path.abspath(a.root) if a.root else find_game_root()
    exe = os.path.abspath(a.exe) if a.exe else os.path.join(root, "build", "cmake", "t5dr.exe")
    out = os.path.abspath(a.out) if a.out else tempfile.mkdtemp(prefix="practice_check_")
    log = os.path.join(out, "practice.log")
    env = {"T5_PRACTICE": "1", "T5_PRACTICE_LOG": log, "T5_TRAINING": "frames", "PS3_AUDIO_MUTE": "1"}
    g = Game(out, exe=exe, root=root, env=env)   # frame dumps: the menu driver finds the fight HUD in them
    ok = False
    try:
        g.start()
        if sc.to_title(g):
            g.phase("practice-select", "menu")
            sc.pick_mode(g, sc.PRACTICE, wait=3.0)
            if sc.start_fight(g, skip=False):
                drive(g)
    finally:
        g.stop()
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            ok = check(f.read().splitlines())
    else:
        print("no practice log: the game did not reach the fight, or T5_PRACTICE did not take")
    if not a.keep and not a.out:
        shutil.rmtree(out, ignore_errors=True)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
