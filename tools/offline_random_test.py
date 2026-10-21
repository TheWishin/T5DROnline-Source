#!/usr/bin/env python3
"""Offline random draws from start to start (docs/DIRECTFIGHT.md "Unlocks", "Random offline").

    python tools/offline_random_test.py --exe build/cmake/t5dr.exe --out build/<you>/runs/off1 \\
        [--boots 2] [--p1 random|mokujin|jinpachi] [--p2 mokujin] [--env T5_OFFLINE_SEED=123]

Boots the game offline (no netplay, no direct fight) `--boots` times, each time: title -> VS ->
both players move their cursor in the top row of the select grid (closed loop on the cells the game
logs with T5_SELECT_TRACE=1) to the asked cell and confirm, the stage, the fight's loading; then the
game is stopped. T5_UNLOCK_JINPACHI=1 is set (the random and Jinpachi's cells are on the grid). Logged
per boot: the models the select records got (the random cell's draw), the fighter words at the fight
(Mokujin's copy: "plays") and the seed line. Prints one line per boot and whether they all differ /
all repeat; --expect differ|same makes it the exit code (0 = as expected).

The games run minimized, muted, below-normal priority (run it under a priority wrapper as well).
"""
import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "smoke"))
import game as smoke_game  # noqa: E402
import scenarios as sc  # noqa: E402

TOP = {"random": 24, "mokujin": 27, "jinpachi": 35}   # the open grid's top row (df_fight.cpp)


def cells(txt, p):
    return [int(m.group(1)) for m in re.finditer(rf"select trace \d+: P{p} cell (\d+) state 03", txt)]


def drive(g, p, target, timeout=40.0):
    """Move player p's cursor to `target` (a top-row cell), closed loop."""
    press = g.press if p == 1 else g.press2
    end = time.time() + timeout
    seen = []
    while time.time() < end:
        txt = g.log_bytes().decode("utf-8", "replace")
        c = cells(txt, p)
        cur = c[-1] if c else None
        if cur is None:
            g.wait(0.3)
            continue
        if not seen or seen[-1] != cur:
            seen.append(cur)
        if cur == target:
            return True, seen
        press("UP" if cur < 24 else "RIGHT", gap=350)
    return False, seen


def one_boot(a, k):
    d = os.path.join(a.out, f"boot{k}")
    env = {"T5_UNLOCK_JINPACHI": "1", "T5_SELECT_TRACE": "1", "PS3_AUDIO_MUTE": "1"}
    for kv in a.env:
        key, _, v = kv.partition("=")
        env[key] = v
    g = smoke_game.Game(d, exe=a.exe, env=env, dump_every=30)
    g.start()
    try:
        # (below normal: the whole tree)
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-Process -Id {g.proc.pid}).PriorityClass = 'BelowNormal'"], capture_output=True)
        if not sc.to_title(g):
            return {"boot": k, "error": "no title"}
        sc.pick_mode(g, sc.VS, wait=3.0)
        ok1, s1 = drive(g, 1, TOP[a.p1])
        g.press("CROSS", gap=1200)
        ok2, s2 = drive(g, 2, TOP[a.p2])
        g.press2("CROSS", gap=1200)
        for _ in range(3):                       # the handicap bars, the stage
            g.press("CROSS", gap=900)
            g.press2("CROSS", gap=900)
        g.wait_log(r"P2 fighter word 0x000[1-9A-F]", timeout=60)
        g.wait(3)
    finally:
        g.stop()
    txt = open(os.path.join(d, "game.log"), encoding="utf-8", errors="replace").read()
    models = {p: re.findall(rf"P{p} cell \d+ state 09 model 0x([0-9A-F]+)", txt) for p in (1, 2)}
    words = {p: re.findall(rf"P{p} fighter word 0x([0-9A-F]+)", txt) for p in (1, 2)}
    seed = re.search(r"offline: the scene's random generator (?:seeded with (0x[0-9A-F]+)|starts as the game sets it)", txt)
    return {"boot": k, "nav": (ok1, s1, ok2, s2), "m1": models[1][-1:] or ["?"], "m2": models[2][-1:] or ["?"],
            "w1": words[1][-1:] or ["?"], "w2": words[2][-1:] or ["?"],
            "seed": (seed.group(1) or "game's own") if seed else "none logged"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--boots", type=int, default=2)
    ap.add_argument("--p1", default="random", choices=sorted(TOP))
    ap.add_argument("--p2", default="mokujin", choices=sorted(TOP))
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--expect", choices=("differ", "same", ""), default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    res = [one_boot(a, k) for k in range(1, a.boots + 1)]
    for r in res:
        print(f"boot {r['boot']}: seed {r.get('seed')}, P1 model {r.get('m1')}, P2 model {r.get('m2')}, "
              f"P1 word {r.get('w1')}, P2 word {r.get('w2')}  {r.get('error', '')}  nav {r.get('nav')}", flush=True)
    keys = [(tuple(r.get("m1", [])), tuple(r.get("m2", [])), tuple(r.get("w1", [])), tuple(r.get("w2", []))) for r in res]
    same = len(set(keys)) == 1
    print("ALL THE SAME" if same else "DIFFERENT", flush=True)
    if a.expect:
        sys.exit(0 if (same if a.expect == "same" else not same) else 1)


if __name__ == "__main__":
    main()
