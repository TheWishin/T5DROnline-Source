#!/usr/bin/env python3
"""Play replay files back through the game and check them against the live match (docs/REPLAYS.md).

    python tools/replay_play.py --exe build/cmake/t5dr.exe --out build/rp/play  <file or folder> ...
        [--match K] [--speed 0|1|2] [--timeout 900] [--parallel N] [--env NAME=VALUE]

Each file is played by its own game (netplay's local mode fed by the file, T5_NET_MODE=replay):
the recorded inputs frame by frame, the recorded sync points, seeds and counters, the loop the
session ran (rollback or lockstep). The game compares every recorded state hash (one every
T5_REPLAY_HASH_EVERY frames, 60 by default) and every match's result (winner, score, the deciding
frame's hash) with the live ones and writes its verdict (T5_REPLAY_RESULT); this tool prints a
table and a summary. --match K plays the session up to match K (0, the default: every match);
--speed 0 (the default) runs as fast as the PC can, 1 at normal speed.

Games run minimized, muted, at below-normal priority, with the pad ignored (T5_REPLAY_CONTROLS=0);
each one is killed when its time is up. Exit code 0 = every replay identical to its live match.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "launcher"))
import replays  # noqa: E402


def files_of(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith(replays.EXT))
        else:
            out.append(p)
    return out


def play(a, path, idx):
    d = os.path.abspath(os.path.join(a.out, f"p{idx:02d}_" + os.path.splitext(os.path.basename(path))[0]))
    os.makedirs(d, exist_ok=True)
    res = os.path.join(d, "verdict.json")
    for fn in ("verdict.json", "verdict.json.tmp"):
        try:
            os.remove(os.path.join(d, fn))
        except OSError:
            pass
    vfs = os.path.abspath(a.vfs)
    env = dict(os.environ)
    env.update({
        "PS3_VFS_ROOT": vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
        "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
        "PS3_AUDIO_MUTE": "1", "PAD_NO_KEYBOARD": "1", "T5_NET_LOG": os.path.join(d, "frames.log"),
    })
    env.update(replays.playback_env(path, a.match, res, a.speed, controls=False))
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    log = open(os.path.join(d, "game.log"), "w")
    t0 = time.time()
    p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")], cwd=d, env=env,
                         stdout=log, stderr=subprocess.STDOUT, creationflags=0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
    try:
        while p.poll() is None and time.time() - t0 < a.timeout:
            time.sleep(1.0)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(10)
        log.close()
    v = replays.read_result(res) or {"error": "no verdict (exit code %s after %.0f s)" % (p.returncode, time.time() - t0)}
    v["seconds"] = round(time.time() - t0, 1)
    v["dir"] = d
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="replay files or folders")
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--match", type=int, default=0, help="play up to this match of each session (0: all)")
    ap.add_argument("--speed", type=int, default=0, help="0 as fast as possible, 1 normal, 2 double")
    ap.add_argument("--timeout", type=float, default=900, help="seconds per replay")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for every game")
    ap.add_argument("--parallel", type=int, default=1, help="games at a time")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows, ok = [], 0
    files = files_of(a.files)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as pool:
        verdicts = list(pool.map(lambda job: play(a, job[1], job[0]), enumerate(files, 1)))
    for i, (f, v) in enumerate(zip(files, verdicts), 1):
        h = replays.read_header(f)
        same = bool(v.get("identical"))
        ok += same
        for m in v.get("matches", []):
            rec = h["matches"][m["n"] - 1]
            rows.append((os.path.basename(f), m["n"], h.get("mode"), rec.get("stage"),
                         f"{replays.fighter_name(rec.get('p1'))} vs {replays.fighter_name(rec.get('p2'))}",
                         m.get("recorded_winner"), m.get("winner"), m.get("recorded_hash"), m.get("hash"), m.get("same")))
        print(f"[{i}] {os.path.basename(f)}: {h.get('mode')}, {len(h['matches'])} match(es) -- "
              f"{'IDENTICAL' if same else 'NOT identical'}: {v.get('hashes_compared', 0)} hashes compared, "
              f"{v.get('hash_mismatches', '?')} different, sync points {v.get('sync_points', '?')}/{v.get('sync_points_recorded', '?')}, "
              f"{v.get('seconds')} s{(' -- ' + v['error']) if v.get('error') else ''}", flush=True)
        with open(os.path.join(a.out, "verdicts.jsonl"), "a", encoding="utf-8") as fo:
            fo.write(json.dumps(dict(v, file=f)) + "\n")
    print()
    print("| replay | match | mode | stage | fighters | winner live / replay | final hash live | final hash replay | same |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %s | %s | %s / %s | %s | %s | %s |" % r)
    total = len(files)
    print(f"\n{ok} of {total} replays identical to the live match (every recorded hash and result)")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
