#!/usr/bin/env python3
"""Check the practice tools in the game (docs/TRAINING.md "Practice tools").

    python tools/practice_check.py [--exe build/cmake/t5dr.exe] [--root DIR] [--out DIR] [--keep]

Starts the game through the smoke harness's menu driver (tools/smoke: title -> PRACTICE -> the cursor's
fighters -> the fight) with the practice tools on (T5_PRACTICE=1, T5_PRACTICE_LOG) and drives P1's pad file:
SELECT+3 after walking away, the four wall resets (each followed by SELECT+3), the dummy's behaviours, a
recording played once and in a loop, and SELECT+3 right after a launcher. The practice log must show

    the fighters 2000 apart at the round start; every reset still in place 30 frames later;
    a wall found for every wall reset, the other fighter 1100 in front of it, facing each other;
    the slot recorded, played and looped; the dummy's behaviours cycled;
    a reset pressed while the dummy is in the air (after df+2) waits until both stand, then holds.

The game runs muted and minimised; nothing of it is kept unless --keep. Exit 0 = PASS.

    python tools/practice_check.py --adv-compare [...]

The same run with the experimental advantage comparison on (T5_TRAINING_ADV_COMPARE=1, T5_TRAINING_LOG;
docs/TRAINING.md "Experimental animation-frame advantage comparison"): besides the checks above, the training
log must hold the old overlay results, the comparison's mapping lines for both players, and for every old
result a comparison line that fails closed (new=unavailable new_status=mapping_conflict_position_x) -- never a
second number from the conflicting mapping.
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
from game import FRAMES, Game, find_game_root  # noqa: E402
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
    sel(g)                                              # back to the start, then a launcher and SELECT+3 while
    g.wait(1)                                           # the dummy is in the air: the reset waits until both stand
    g.hold("RIGHT")
    g.wait(1.4)
    g.release()
    g.wait(0.2)
    g.hold("DOWN", "RIGHT")
    g.wait(0.08)
    g.hold("DOWN", "RIGHT", "TRIANGLE")                 # df+2: a launcher for most of the cast
    g.wait(0.12)
    g.release()
    g.wait(0.35)
    sel(g)
    g.wait(3)
    g.shot("after-launcher-reset", expect="any", settle=0.5)


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
    later = [i for i, p in enumerate(places) if p[1] == "30 frames later:" or p[1] == "after the turn, back to:"]
    good(len(resets) >= 5, f"{len(resets)} round-start resets (want 5)")
    # the places are checked while the dummy stands (later on it walks, sidesteps, plays a recording)
    first_mode = next((int(ln.split()[0]) for ln in log_lines if re.match(r"^\d+ dummy \w+$", ln)), 1 << 30)
    for i in [r for r in resets if int(places[r][0]) < first_mode]:
        after = next((j for j in later if j > i), None)
        if s and after is not None:
            a = xyz(places[after])
            good(abs(a[0] - s[0]) < 60 and abs(a[1] - s[1]) < 60 and abs(a[3] - s[3]) < 60 and abs(a[4] - s[4]) < 60,
                 f"30 frames after the reset at frame {places[i][0]}: P1 ({a[0]:.0f}, {a[1]:.0f}) "
                 f"dummy ({a[3]:.0f}, {a[4]:.0f})")
    # the reset after the launcher: it waited until both stood, then both at the start, still there 30 frames later
    # (the last waiting reset: the crouching / blocking dummy earlier on waits a few frames too)
    waits = [i for i, ln in enumerate(log_lines) if " reset waits until both stand:" in ln]
    wait_at = waits[-1] if waits else None
    if wait_at is None:
        good(False, "a reset pressed with the dummy in the air waited for both to stand (no 'reset waits' line: did "
                    "the launcher hit?)")
    else:
        rest = log_lines[wait_at:]
        done = next((ln for ln in rest if re.match(r"^\d+ reset after waiting \d+ frames", ln)), "")
        good(done and "anyway" not in done, f"the waiting reset came once both stood: {done.split(' ', 1)[-1] if done else 'never'}")
        later_p = [m.groups() for m in (PLACE.match(ln) for ln in rest) if m]
        r_i = next((i for i, p in enumerate(later_p) if p[1] == "reset round start:"), None)
        a_p = next((p for p in later_p[r_i:] if p[1] == "30 frames later:"), None) if r_i is not None else None
        if s and a_p:
            a = xyz(a_p)
            good(abs(a[0] - s[0]) < 60 and abs(a[1] - s[1]) < 60 and abs(a[3] - s[3]) < 60 and abs(a[4] - s[4]) < 60,
                 f"30 frames after the waiting reset: P1 ({a[0]:.0f}, {a[1]:.0f}) dummy ({a[3]:.0f}, {a[4]:.0f})")
        else:
            good(False, "no places 30 frames after the waiting reset")
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


RE_RESULT = re.compile(r"^(\d+) result (P[12]) startup \S+ \S+ adv ([+-]\d+) ")
RE_MOVE = re.compile(r"^(\d+) adv_compare move (P[12]) .*? old=([+-]\d+) ")


def compare_coverage(lines):
    """(results without their comparison line, pairs whose old value is not the result's adv, comparison lines
    without a result) -- review optin-check-120 P2: one comparison line used to be enough for any number of
    results. The training writes both lines for one result in the same frame (training.cpp log_result +
    shadow_log_old), but only while the comparison runs: from an 'adv_compare mapping' line (it starts) to an
    'adv_compare reset' line (it stops); results outside that need none."""
    active = False
    pending = []                 # (frame, player, adv, line) of results waiting for their comparison line
    missing, wrong, extra = [], [], []
    for ln in lines:
        if " adv_compare mapping " in ln:
            active = True
            continue
        if " adv_compare reset " in ln:
            active = False
            missing += [p[3] for p in pending]
            pending = []
            continue
        m = RE_RESULT.match(ln)
        if m and " adv_compare " not in ln:
            if active:
                pending.append((m.group(1), m.group(2), int(m.group(3)), ln))
            continue
        m = RE_MOVE.match(ln)
        if m:
            k = next((i for i, p in enumerate(pending) if p[0] == m.group(1) and p[1] == m.group(2)), None)
            if k is None:
                extra.append(ln)
                continue
            frame, player, adv, res = pending.pop(k)
            if int(m.group(3)) != adv:
                wrong.append(f"{res.strip()}  <->  {ln.strip()}")
    missing += [p[3] for p in pending]
    return missing, wrong, extra


def check_adv_compare(lines):
    """The training log of an --adv-compare run (docs/TRAINING.md): observation only, fails closed."""
    ok = True

    def good(cond, what):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    adv = [ln for ln in lines if " adv_compare " in ln]
    old = [ln for ln in lines if " adv_compare " not in ln and re.search(r"^\d+ result P[12] startup ", ln)]
    mapping = [ln for ln in adv if " adv_compare mapping " in ln]
    moves = [ln for ln in adv if " adv_compare move " in ln]
    print(f"{len(lines)} training log lines, {len(adv)} adv_compare lines ({len(mapping)} mapping, {len(moves)} move)")
    good(old, f"the overlay's own results are logged ({len(old)})")
    good({"P1", "P2"} <= {ln.split()[3] for ln in mapping}, "a mapping line for both players")
    good(moves, "comparison lines for the overlay's results")
    missing, wrong, extra = compare_coverage(lines)
    good(not missing and not wrong and not extra,
         f"every overlay result while the comparison runs has its comparison line with the same old value "
         f"(missing {len(missing)}, other value {len(wrong)}, without a result {len(extra)})")
    for ln in (missing[:2] + wrong[:2] + extra[:2]):
        print("    ! " + ln[:220])
    good(all("new=unavailable" in ln and "new_status=mapping_conflict_position_x" in ln for ln in moves),
         "every comparison fails closed (new=unavailable, mapping_conflict_position_x)")
    good(not [ln for ln in adv if " new=candidate" in ln], "no second number from the conflicting mapping")
    for ln in (mapping[:2] + moves[:3]):
        print("    " + ln[:220])
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=None, help="t5dr.exe (default: <root>/build/cmake/t5dr.exe)")
    ap.add_argument("--root", default=None, help="the build's output root with game/vfs (build_game.py --out)")
    ap.add_argument("--out", default="", help="working directory (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="keep the working directory")
    ap.add_argument("--adv-compare", action="store_true",
                    help="also the experimental advantage comparison (T5_TRAINING_ADV_COMPARE=1): fails closed")
    a = ap.parse_args()
    root = os.path.abspath(a.root) if a.root else find_game_root()
    exe = os.path.abspath(a.exe) if a.exe else os.path.join(root, "build", "cmake",
                                                            "t5dr.exe" if os.name == "nt" else "t5dr")
    out = os.path.abspath(a.out) if a.out else tempfile.mkdtemp(prefix="practice_check_")
    log = os.path.join(out, "practice.log")
    env = {"T5_PRACTICE": "1", "T5_PRACTICE_LOG": log, "T5_TRAINING": "frames", "PS3_AUDIO_MUTE": "1"}
    tlog = os.path.join(out, "training.log")
    if a.adv_compare:
        env.update(T5_TRAINING_ADV_COMPARE="1", T5_TRAINING_LOG=tlog)
    g = Game(out, exe=exe, root=root, env=env)   # frame dumps: the menu driver finds the fight HUD in them
    ok = False
    try:
        g.start()
        if sc.to_title(g):
            g.phase("practice-select", "menu")
            sc.pick_mode(g, sc.PRACTICE, wait=3.0)
            # macOS has no frame dump to see the fight HUD in: the menu driver has confirmed through to the
            # fight by its timeout, so drive anyway -- the practice log below is the evidence either way
            if sc.start_fight(g, skip=False) or not FRAMES:
                drive(g)
    finally:
        g.stop()
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            ok = check(f.read().splitlines())
    else:
        print("no practice log: the game did not reach the fight, or T5_PRACTICE did not take")
    if a.adv_compare:
        if os.path.exists(tlog):
            with open(tlog, encoding="utf-8", errors="replace") as f:
                ok = check_adv_compare(f.read().splitlines()) and ok
        else:
            print("no training log: T5_TRAINING_LOG did not take")
            ok = False
    if not a.keep and not a.out:
        shutil.rmtree(out, ignore_errors=True)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
