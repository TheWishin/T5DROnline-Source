#!/usr/bin/env python3
"""Spectators of a live match on this PC: games that play a session's live stream while it grows
(docs/SPECTATE.md).

    python tools/spectate_test.py --exe build/cmake/t5dr.exe --out build/sp/watch --live LIVE_FILE \
        [--late 60] [--spectators 2] [--chunk 0.5] [--timeout 1800]

LIVE_FILE is the stream a player's game writes (T5_REPLAY_LIVE, e.g. a pair run of
tools/fight_flow_test.py with --env1 T5_REPLAY_LIVE=...). Each spectator gets its own copy of
it, fed the way the launcher feeds one from the lobby: every --chunk seconds whatever is new,
cut at arbitrary bytes. Spectator 1 starts as soon as the stream has its session and first
match; every further one --late seconds after the one before it (a viewer who joins late: it
gets everything from the session's start at once and plays from there). Each spectator's game
compares every recorded hash and result with its own and writes its verdict (T5_REPLAY_RESULT);
the tool prints them side by side, with each spectator's delay behind the live game.

Games run minimized, muted, at below-normal priority, with the pad ignored. Exit code 0 = every
spectator saw the whole session identical to the live game.
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
from t5lobby import spectate  # noqa: E402


def feed(src, dst, chunk_s, stop):
    """Copy what src got since the last pass to dst, every chunk_s seconds, until src has its END
    record and everything is copied (or stop is set)."""
    pos = 0
    parser = spectate.LiveParser()
    with open(dst, "wb") as out:
        while not stop.is_set():
            try:
                with open(src, "rb") as f:
                    f.seek(pos)
                    data = f.read()
            except OSError:
                data = b""
            if data:
                out.write(data)
                out.flush()
                pos += len(data)
                parser.feed(data)
            if parser.ended:
                return
            stop.wait(chunk_s)


def run_spectator(a, k, ready_at, results):
    d = os.path.abspath(os.path.join(a.out, f"spectator{k}"))
    os.makedirs(d, exist_ok=True)
    start = ready_at + (k - 1) * a.late
    while time.time() < start:
        time.sleep(0.2)
    copy = os.path.join(d, "live.t5live")
    stop = threading.Event()
    th = threading.Thread(target=feed, args=(a.live, copy, a.chunk, stop), daemon=True)
    th.start()
    # the launcher starts the game once its copy has the session and the first match
    t0 = time.time()
    while time.time() - t0 < 60:
        p = spectate.LiveParser()
        try:
            with open(copy, "rb") as f:
                p.feed(f.read())
        except OSError:
            pass
        if p.ready:
            break
        time.sleep(0.2)
    res = os.path.join(d, "verdict.json")
    for fn in ("verdict.json", "verdict.json.tmp", "status.json"):
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
    env.update(spectate.watch_env(copy, result_path=res, status_path=os.path.join(d, "status.json"), controls=False))
    for kv in a.env:
        key, v = kv.split("=", 1)
        env[key] = v
    log = open(os.path.join(d, "game.log"), "w")
    t_start = time.time()
    proc = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")], cwd=d, env=env,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
    try:
        while proc.poll() is None and time.time() - t_start < a.timeout:
            time.sleep(1.0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(10)
        stop.set()
        log.close()
    v = None
    try:
        with open(res, encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        v = {"error": "no verdict (exit code %s after %.0f s)" % (proc.returncode, time.time() - t_start)}
    v["joined_s"] = round(t_start - ready_at, 1)
    v["seconds"] = round(time.time() - t_start, 1)
    v["dir"] = d
    results[k] = v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", required=True, help="the live stream a player's game writes (T5_REPLAY_LIVE)")
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--spectators", type=int, default=2)
    ap.add_argument("--late", type=float, default=60.0, help="seconds between one spectator's start and the next one's")
    ap.add_argument("--chunk", type=float, default=0.5, help="seconds between two pieces of the copy")
    ap.add_argument("--wait", type=float, default=900, help="seconds to wait for the stream's session and first match")
    ap.add_argument("--timeout", type=float, default=1800, help="seconds per spectator game")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for every spectator's game")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    while True:
        p = spectate.LiveParser()
        try:
            with open(a.live, "rb") as f:
                p.feed(f.read())
        except OSError:
            pass
        if p.ready:
            break
        if time.time() - t0 > a.wait:
            print("the live stream never got its session and first match", flush=True)
            return 2
        time.sleep(0.5)
    ready_at = time.time()
    print(f"live stream ready after {ready_at - t0:.0f} s: {a.live}", flush=True)
    results = {}
    ths = [threading.Thread(target=run_spectator, args=(a, k, ready_at, results)) for k in range(1, a.spectators + 1)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    ok = 0
    finals = {}
    for k in sorted(results):
        v = results[k]
        same = bool(v.get("identical"))
        ok += same
        hashes = [m.get("hash") for m in v.get("matches", [])]
        finals[k] = hashes
        print(f"spectator {k}: joined {v.get('joined_s')} s after the stream was ready -- "
              f"{'IDENTICAL' if same else 'NOT identical'}: {v.get('hashes_compared', 0)} hashes compared, "
              f"{v.get('hash_mismatches', '?')} different, {v.get('uncompared', '?')} uncompared, sync points "
              f"{v.get('sync_points', '?')}/{v.get('sync_points_recorded', '?')}, matches {len(hashes)}, "
              f"delay avg {v.get('delay_avg', '?')} s max {v.get('delay_max', '?')} s, {v.get('stalls', '?')} waits "
              f"({v.get('stall_seconds', '?')} s), end: {v.get('end')} / {v.get('stream_end')}"
              f"{(' -- ' + v['error']) if v.get('error') else ''}", flush=True)
        for m in v.get("matches", []):
            print(f"    match {m['n']}: winner {m.get('winner')} (live {m.get('recorded_winner')}), hash {m.get('hash')} "
                  f"(live {m.get('recorded_hash')}), same {m.get('same')}", flush=True)
        with open(os.path.join(a.out, "verdicts.jsonl"), "a", encoding="utf-8") as fo:
            fo.write(json.dumps(dict(v, spectator=k)) + "\n")
    same_hashes = len(set(json.dumps(h) for h in finals.values())) == 1 and all(finals.values())
    print(f"\n{ok} of {len(results)} spectators identical to the live game; final hashes the same for all: {same_hashes}")
    return 0 if ok == len(results) and same_hashes else 1


if __name__ == "__main__":
    sys.exit(main())
