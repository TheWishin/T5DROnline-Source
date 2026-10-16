#!/usr/bin/env python3
"""Run one game instance for a rollback experiment (src/rollback, docs/ROLLBACK.md).

    python tools/rollback_test.py --out NAME --seconds 90 [--exe build/cmake/t5dr.exe]
        [--env T5_RB_MODE=test --env T5_RB_START=3000 ...] [--shots t1,t2,...]

The run gets its own directory build/rollback-runs/NAME (cwd: gamedata/scratch
go there), game.log, rb_frames.log, and screenshots at the given times (seconds).
The window opens minimized (PS3_WINDOW_BACKGROUND=1); pads are scripted from
T5_RB_SCRIPT / T5_RB_SCRIPT2. The instance is killed when the time is up.
"""
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
EXE = ROOT + "/build/cmake/t5dr.exe"
VFS = ROOT + "/game/vfs"
RUNS = ROOT + "/build/rollback-runs"

# The menu path np found: title -> (DOWN, DOWN, CROSS) -> ... -> fight by ~3100.
# np packing: DIGITAL1 low byte (UP 10 RIGHT 20 DOWN 40 LEFT 80 START 8),
# DIGITAL2 high byte (TRIANGLE 1000 CIRCLE 2000 CROSS 4000 SQUARE 8000).
# With the intro movies playing (ps3recomp patch 0006) np's current timing:
# START at 1200 skips the movie, then DOWN DOWN CROSS on the main menu (VS
# BATTLE), CROSS x3 through character/stage select; fight from ~3300.
MENU = "@1200:4:0x8,1500:4:0x40,1540:4:0x40,1580:4:0x4000,1800:4:0x4000,2000:4:0x4000,2200:4:0x4000"


def fight_script(start=3300, end=9000, p1=True):
    ev = []
    f = start
    while f < end:
        if p1:
            ev.append(f"{f}:4:0x8000")      # SQUARE (LP)
            ev.append(f"{f + 20}:10:0x20")  # RIGHT
        else:
            ev.append(f"{f + 7}:4:0x1000")   # TRIANGLE (RP)
            ev.append(f"{f + 25}:10:0x80")   # LEFT
        f += 40
    return ",".join(ev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=90)
    ap.add_argument("--exe", default=EXE)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--shots", default="", help="comma-separated seconds at which to screenshot")
    ap.add_argument("--no-script", action="store_true")
    ap.add_argument("--icall-at", type=float, default=0, help="seconds: trace the main thread's indirect calls for 0.5 s")
    a = ap.parse_args()

    d = os.path.join(RUNS, a.out)
    os.makedirs(d, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "PS3_VFS_ROOT": VFS,
        "PS3_HDD0_ROOT": VFS + "/dev_hdd0",
        "PS3_TITLE": "T5DR rollback test",
        "PS3_GCM_TICKER_PUMP": "1",
        "RSX_LIVE_DRAW": "1",
        "PS3_VERBOSE": "0",
        "PS3_WINDOW_BACKGROUND": "1",
        "PAD_NO_KEYBOARD": "1",
        "PS3_VM_WRITE_WATCH": "1",
        "T5_RB_MODE": "measure",
        "T5_RB_LOG": os.path.join(d, "rb_frames.log"),
    })
    if not a.no_script:
        env["T5_RB_SCRIPT"] = MENU + "," + fight_script(p1=True)
        env["T5_RB_SCRIPT2"] = "@1810:4:0x4000,2010:4:0x4000,2210:4:0x4000," + fight_script(p1=False)
    gate = os.path.join(d, "icall.gate")
    if a.icall_at:
        env["PS3_ICALL_GATE"] = gate
        env["PS3_ICALL_TRACE"] = "1"
        if os.path.exists(gate):
            os.remove(gate)
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    log = open(os.path.join(d, "game.log"), "w")
    # private copy of the exe, so a rebuild during the run does not collide
    import shutil
    exe = os.path.join(d, "t5dr.exe")
    shutil.copyfile(a.exe, exe)
    p = subprocess.Popen([exe, VFS + "/PS3_GAME/USRDIR/EBOOT.elf"], env=env, cwd=d,
                         stdout=log, stderr=subprocess.STDOUT)
    print(f"started pid {p.pid} in {d}")
    shots = sorted(float(s) for s in a.shots.split(",") if s)
    t0 = time.time()
    try:
        while time.time() - t0 < a.seconds:
            if p.poll() is not None:
                print(f"exited early with {p.returncode}")
                break
            if shots and time.time() - t0 >= shots[0]:
                t = shots.pop(0)
                png = os.path.join(d, f"shot_{int(t)}s.png")
                subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ROOT + "/tools/screenshot.ps1",
                                "-Out", png, "-ProcessId", str(p.pid)], capture_output=True)
                print(f"shot {png}")
            if a.icall_at and time.time() - t0 >= a.icall_at:
                open(gate, "w").close()
                time.sleep(0.5)
                os.remove(gate)
                print("icall window done")
                a.icall_at = 0
            time.sleep(0.25)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        log.close()
    print("done")


if __name__ == "__main__":
    main()
