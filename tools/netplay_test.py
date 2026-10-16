#!/usr/bin/env python3
"""Run one or two game instances for netplay testing on this PC.

    python tools/netplay_test.py --exe build/np/cmake/t5dr.exe --out build/np/runs/t1 \
        --seconds 120 --pair [--delay 3] [--env NAME=VALUE ...] [--env1 ...] [--env2 ...]

--pair starts a host (P1, UDP 7000) and a joiner (P2) on 127.0.0.1; without it a
single instance runs in T5_NET_MODE=local. Each instance gets its own working
directory (the runtime writes ./gamedata and ./scratch there), a log, the
netplay frame log (frames.log) and, with --shots N, a .ppm of the presented
frame every N flips (converted to .png when Pillow is installed). Windows open
minimized (PS3_WINDOW_BACKGROUND=1) and host pads/keyboard are ignored, so a
test neither disturbs nor is disturbed by the person at the PC; input comes
from T5_NET_SCRIPT / T5_NET_PADFILE (padfile.txt in each instance directory).
All instances are killed when the time is up.
"""
import argparse
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def to_png(d):
    try:
        from PIL import Image
    except ImportError:
        return
    for p in sorted(glob.glob(os.path.join(d, "*.ppm"))):
        try:
            Image.open(p).save(p[:-4] + ".png")
            os.remove(p)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=90)
    ap.add_argument("--pair", action="store_true")
    ap.add_argument("--delay", type=int, default=3)
    ap.add_argument("--port", type=int, default=7000)
    ap.add_argument("--shots", type=int, default=0, help="dump the screen every N flips")
    ap.add_argument("--off", action="store_true", help="netplay off (reference run); PAD_FILE=padfile.txt drives port 0")
    ap.add_argument("--keep-ppm", action="store_true", help="leave screen dumps as .ppm")
    ap.add_argument("--stagger", type=float, default=0.0, help="seconds between starting host and joiner")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--env1", action="append", default=[])
    ap.add_argument("--env2", action="append", default=[])
    a = ap.parse_args()

    vfs = os.path.abspath(a.vfs)
    base = dict(os.environ)
    base.update({
        "PS3_VFS_ROOT": vfs.replace("\\", "/"),
        "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
        "PS3_TITLE": "Tekken 5 DR netplay test",
        "PS3_GCM_TICKER_PUMP": "1",
        "RSX_LIVE_DRAW": "1",
        "PS3_VERBOSE": "0",
        "PS3_WINDOW_BACKGROUND": "1",
        "PAD_NO_KEYBOARD": "1",
        "T5_NET_XINPUT": "-1",
        "T5_NET_KEYBOARD": "0",
        "T5_NET_DELAY": str(a.delay),
    })
    for kv in a.env:
        k, v = kv.split("=", 1)
        base[k] = v

    roles = [("host", a.env1), ("join", a.env2)] if a.pair else [("local", a.env1)]
    procs = []
    for i, (role, extra) in enumerate(roles, 1):
        d = os.path.abspath(os.path.join(a.out, f"run{i}"))
        os.makedirs(d, exist_ok=True)
        env = dict(base)
        env["T5_NET_MODE"] = "" if a.off else role
        if a.off:
            env["PAD_FILE"] = os.path.join(d, "padfile.txt")
        env["T5_NET_LOG"] = os.path.join(d, "frames.log")
        env["T5_NET_PADFILE"] = os.path.join(d, "padfile.txt")
        open(env["T5_NET_PADFILE"], "w").close()
        if role == "local":
            env["T5_NET_PADFILE2"] = os.path.join(d, "padfile2.txt")
            open(env["T5_NET_PADFILE2"], "w").close()
        if role == "host":
            env["T5_NET_PORT"] = str(a.port)
        if role == "join":
            env["T5_NET_PEER"] = f"127.0.0.1:{a.port}"
        if a.shots:
            sd = os.path.join(d, "shots")
            os.makedirs(sd, exist_ok=True)
            env["LD_FRAME_DUMP"] = sd
            env["LD_FRAME_DUMP_EVERY"] = str(a.shots)
        for kv in extra:
            k, v = kv.split("=", 1)
            env[k] = v
        log = open(os.path.join(d, "game.log"), "w")
        p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                             cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
        procs.append((p, d))
        print(f"started {role} pid {p.pid} in {d}", flush=True)
        if a.stagger and i == 1:
            time.sleep(a.stagger)

    t_end = time.time() + a.seconds
    try:
        while time.time() < t_end and any(p.poll() is None for p, _ in procs):
            time.sleep(0.5)
    finally:
        for p, _ in procs:
            if p.poll() is None:
                p.kill()
        for p, _ in procs:
            try:
                p.wait(10)
            except Exception:
                pass
    for p, d in procs:
        print(f"{d}: exit {p.returncode}")
        if a.shots and not a.keep_ppm:
            to_png(os.path.join(d, "shots"))


if __name__ == "__main__":
    sys.exit(main())
