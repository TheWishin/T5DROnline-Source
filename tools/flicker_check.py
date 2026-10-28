#!/usr/bin/env python3
"""Count black-flash frames in a real fight: one offline direct fight, every presented frame read back
without stopping the GPU (LD_FRAME_DUMP_ASYNC, ps3recomp patch 0082), and the frames whose 3D picture is
less than half as bright as both neighbours counted.

    python tools/flicker_check.py [--out GAME_OUT] [--stage 4] [--cpus 0xFF] [--secs 6] [--keep]
                                  [--dir DIR] [NAME=VALUE ...]

Made for 1.1.7's City at Sunset flicker (docs/RENDER_PERF.md "City at Sunset: one black frame at a time"):
stage 4 with Stage blur / glow Off and one vertex worker (below 24 logical processors; --cpus 0xFF gives the
game 8 of this PC's) showed 7-18 such frames in 6 s before the patch, 0 after. NAME=VALUE goes to the
game, e.g. RSX_VERTEX_KEEP_SKIPPED=0 (the code before the fix) or PS3_STAGE_BLUR=1. Both fighters are
scripted (walks, jumps, punches), so the camera moves. The pictures are game art: they go to a temporary
folder (or --dir) and are deleted unless --keep. Exit code: 0 no dark frame, 1 dark frames, 2 the run failed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import run_game  # noqa: E402


def script(offset, moves):
    """T5_DF_SCRIPT text: a 30-frame press every 40 frames from frame 1450 on (pad masks, hex)."""
    return ",".join(f"{1450 + k * 40 + offset}:30:{moves[k % len(moves)]}" for k in range(60))


def load_ppm(path):
    import numpy as np
    with open(path, "rb") as f:
        data = f.read()
    parts, i = [], 0
    while len(parts) < 4:
        while data[i:i + 1].isspace():
            i += 1
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        parts.append(data[i:j])
        i = j
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(data[i + 1:i + 1 + w * h * 3], dtype=np.uint8).reshape(h, w, 3)


def dark_frames(folder):
    """[(frame name, brightness)] of the frames whose middle (the 3D picture, not the HUD) is under 45 and
    less than half as bright as both neighbours: a frame that lost its 3D picture."""
    names = sorted(f for f in os.listdir(folder) if f.startswith("frame_") and f.endswith(".ppm") and "_s" not in f)
    m = []
    for n in names:
        img = load_ppm(os.path.join(folder, n))
        h, w = img.shape[:2]
        m.append(float(img[h * 200 // 720:h * 560 // 720:4, w * 100 // 1280:w * 1180 // 1280:4].mean()))
    bad = [(names[i], round(m[i], 1)) for i in range(1, len(m) - 1)
           if m[i] < 45 and m[i] < 0.5 * min(m[i - 1], m[i + 1])]
    return len(names), bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=ROOT, help="the build's output root (build_game.py --out)")
    ap.add_argument("--stage", default="4")
    ap.add_argument("--fighters", default="kaz,rav")
    ap.add_argument("--cpus", default="", help="0xMASK: the logical processors the game may use")
    ap.add_argument("--at", type=float, default=9.0, help="seconds after the fight state until the frames")
    ap.add_argument("--secs", type=float, default=6.0, help="seconds of frames")
    ap.add_argument("--dir", default="", help="where the frames and the game log go (default: a temp folder)")
    ap.add_argument("--keep", action="store_true", help="keep the frames")
    ap.add_argument("env", nargs="*")
    a = ap.parse_args()

    run = os.path.abspath(a.dir) if a.dir else tempfile.mkdtemp(prefix="t5dr-flicker-")
    frames = os.path.join(run, "frames")
    os.makedirs(frames, exist_ok=True)
    gate, status = os.path.join(run, "gate"), os.path.join(run, "status.json")
    for p in (gate, status):
        if os.path.exists(p):
            os.remove(p)
    with open(os.path.join(run, "p1.txt"), "w") as f:
        f.write(script(0, ["20", "10", "20", "4000", "80", "2000"]))
    with open(os.path.join(run, "p2.txt"), "w") as f:
        f.write(script(10, ["80", "8000", "20", "10", "80", "1000"]))
    extra = {
        "T5_FIGHT": f"{a.fighters},{a.stage},3", "T5_UNLOCK_STAGES": "1", "T5_DF_STATUS_FILE": status,
        "T5_DF_SCRIPT": os.path.join(run, "p1.txt"), "T5_DF_SCRIPT2": os.path.join(run, "p2.txt"),
        "PS3_STAGE_BLUR": "0",                 # the launcher's default since 1.1.4
        "LD_FRAME_DUMP": frames, "LD_FRAME_DUMP_EVERY": "1", "LD_FRAME_DUMP_GATE": gate,
        "LD_FRAME_DUMP_ASYNC": "1",
    }
    for kv in a.env:
        k, v = kv.split("=", 1)
        extra[k] = v
    cmd, env, cwd = run_game.game_command(os.path.abspath(a.out), extra)
    if not os.path.exists(cmd[0]):
        print(f"no game at {cmd[0]}")
        return 2
    if a.cpus and os.name == "nt":
        import ctypes
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        k32.SetProcessAffinityMask(k32.GetCurrentProcess(), int(a.cpus, 16))   # the game inherits it
    log = open(os.path.join(run, "game.log"), "w")
    p = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    t0, fight = time.time(), None
    try:
        while time.time() - t0 < 180 and fight is None:
            if p.poll() is not None:
                print("the game ended before the fight")
                return 2
            try:
                with open(status) as f:
                    if json.load(f).get("state") == "fight":
                        fight = time.time()
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        if fight is None:
            print("no fight within 180 s")
            return 2
        while time.time() - fight < a.at:
            time.sleep(0.05)
        open(gate, "w").close()
        while time.time() - fight < a.at + a.secs:
            time.sleep(0.05)
        os.remove(gate)
        time.sleep(1.5)                         # the writer thread finishes the last frames
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        log.close()
    n, bad = dark_frames(frames)
    print(f"stage {a.stage}: {n} frames, {len(bad)} dark (3D picture lost): {bad[:12]}")
    if not a.keep:
        shutil.rmtree(frames, ignore_errors=True)
    print(f"game log: {os.path.join(run, 'game.log')}")
    if n < 30:
        print("too few frames read back")
        return 2
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
