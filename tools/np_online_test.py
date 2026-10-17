#!/usr/bin/env python3
"""Launch one or two T5DR instances for the NP-online work and drive them with
PS3_PAD_FILE scripts.

    python drive.py --out runs/x --seconds 60 [--two] [--script1 FILE] [--script2 FILE]
                    [--env K=V ...] [--env1 K=V ...] [--env2 K=V ...] [--shots t,t,t]

A script is a list of "<when> <buttons...>" lines: when that moment comes the
pad file is rewritten with those held buttons (none = release everything).
<when> is either seconds since launch (12.5) or a game frame number (f1500):
the runtime prints "[fps] N (frames A..B over T s)" every 5 s and the driver
extrapolates the current frame from the last such line, so a frame-based
script survives a slow boot (other builds hogging the CPU) that a wall-clock
one does not. Lines starting with "wait" pause the script until the regex
that follows appears in the instance's game.log; later frame/second values
are then relative to that moment.
    f1500 DOWN
    f1512
    wait \\[sceNpMatching\\] in room
    3 CROSS
Screenshots are taken at the --shots times (seconds) into <run>/shot_<t>.png.
"""
import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PS = os.environ.get("T5DR_PS_DIR", os.path.join(os.path.dirname(HERE), "build", "ps"))  # build/<agent> dir with cmake/t5dr.exe
ROOT = os.path.dirname(HERE)
EXE = os.path.join(PS, "cmake", "t5dr.exe")
VFS = os.path.join(ROOT, "game", "vfs")
SHOT = os.path.join(ROOT, "tools", "screenshot.ps1")
FPS_RE = re.compile(r"\[fps\] ([0-9.]+) \(frames (\d+)\.\.(\d+) over")


def parse_script(path):
    ev = []
    if not path:
        return ev
    for line in open(path):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if parts[0] == "wait":
            ev.append(("wait", re.compile(parts[1] if len(parts) > 1 else "$^"), ""))
        elif parts[0] == "shot":
            # "shot <seconds> <name>": screenshot of this instance at that (relative) time
            t, name = parts[1].split(None, 1)
            ev.append(("shot", float(t), name.strip()))
        elif parts[0].startswith("f"):
            ev.append(("frame", int(parts[0][1:]), parts[1] if len(parts) > 1 else ""))
        else:
            ev.append(("sec", float(parts[0]), parts[1] if len(parts) > 1 else ""))
    return ev


def screenshot(pid, out):
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", SHOT, "-Out", out,
                    "-ProcessId", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=60)


class Instance:
    def __init__(self, i, d, p, pad, events):
        self.i, self.dir, self.p, self.pad, self.events = i, d, p, pad, events
        self.log_path = os.path.join(d, "game.log")
        self.log_pos = 0
        self.fps, self.frame_at, self.t_at = 0.0, 0, time.time()
        self.t0 = time.time()           # reference for seconds/frames
        self.frame0 = 0
        self.waiting = None
        self.tail = ""

    def est_frame(self, now):
        return self.frame_at + (now - self.t_at) * self.fps

    def poll_log(self):
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.log_pos)
                chunk = f.read()
                self.log_pos = f.tell()
        except OSError:
            return
        if not chunk:
            return
        for m in FPS_RE.finditer(chunk):
            self.fps, self.frame_at, self.t_at = float(m.group(1)), int(m.group(3)), time.time()
        self.tail = (self.tail + chunk)[-200000:]
        if self.waiting is not None and self.waiting.search(chunk):
            print(f"run{self.i}: wait satisfied ({self.waiting.pattern})", flush=True)
            self.waiting = None
            self.t0 = time.time()
            self.frame0 = self.est_frame(self.t0)
            self.tail = ""

    def step(self, now):
        self.poll_log()
        fired = False   # one pad event per step, so a press and its release never land in the same poll
        while self.events and self.waiting is None and not fired:
            kind, when, btn = self.events[0]
            if kind == "wait":
                self.events.pop(0)
                if when.search(self.tail):
                    self.t0 = time.time(); self.frame0 = self.est_frame(self.t0); self.tail = ""
                else:
                    self.waiting = when
                continue
            if kind in ("sec", "shot") and now - self.t0 < when:
                break
            if kind == "frame" and self.est_frame(now) - self.frame0 < when:
                break
            self.events.pop(0)
            fired = True
            if kind == "shot":
                if self.p.poll() is None:
                    screenshot(self.p.pid, os.path.join(self.dir, f"{btn}.png"))
                    print(f"run{self.i}: t={now - self.t0:.1f}s shot {btn}", flush=True)
                continue
            with open(self.pad, "w") as f:
                f.write(btn + "\n")
            if btn:
                print(f"run{self.i}: t={now - self.t0:.1f}s f~{int(self.est_frame(now) - self.frame0)} press {btn}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--two", action="store_true")
    ap.add_argument("--exe", default=EXE)
    ap.add_argument("--script1")
    ap.add_argument("--script2")
    ap.add_argument("--shots", default="")
    ap.add_argument("--stagger", type=float, default=0.0)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--env1", action="append", default=[])
    ap.add_argument("--env2", action="append", default=[])
    a = ap.parse_args()

    base = dict(os.environ)
    base.update({
        "PS3_VFS_ROOT": VFS.replace("\\", "/"),
        "PS3_HDD0_ROOT": os.path.join(VFS, "dev_hdd0").replace("\\", "/"),
        "PS3_GCM_TICKER_PUMP": "1",
        "RSX_LIVE_DRAW": "1",
        "PS3_VERBOSE": "0",
        "PS3_WINDOW_BACKGROUND": "1",
    })
    for kv in a.env:
        k, v = kv.split("=", 1)
        base[k] = v

    insts = [(1, a.script1, a.env1)]
    if a.two:
        insts.append((2, a.script2, a.env2))
    procs = []
    t0 = time.time()
    for i, script, extra in insts:
        d = os.path.abspath(os.path.join(a.out, f"run{i}"))
        os.makedirs(d, exist_ok=True)
        env = dict(base)
        pad = os.path.join(d, "pad.txt")
        open(pad, "w").close()
        env["PS3_PAD_FILE"] = pad
        for kv in extra:
            k, v = kv.split("=", 1)
            env[k] = v
        log = open(os.path.join(d, "game.log"), "w")
        p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(VFS, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                             cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
        procs.append(Instance(i, d, p, pad, parse_script(script)))
        print(f"started run{i} pid {p.pid} in {d}", flush=True)
        if a.stagger and i == 1:
            time.sleep(a.stagger)

    shots = [float(x) for x in a.shots.split(",") if x]
    t_end = t0 + a.seconds
    try:
        while time.time() < t_end and any(x.p.poll() is None for x in procs):
            now = time.time()
            for x in procs:
                x.step(now)
            while shots and now - t0 >= shots[0]:
                t = shots.pop(0)
                for x in procs:
                    if x.p.poll() is None:
                        screenshot(x.p.pid, os.path.join(x.dir, f"shot_{int(t)}.png"))
            time.sleep(0.05)
    finally:
        for x in procs:
            if x.p.poll() is None:
                x.p.kill()
        for x in procs:
            try:
                x.p.wait(10)
            except Exception:
                pass
    for x in procs:
        print(f"{x.dir}: exit {x.p.returncode}")


if __name__ == "__main__":
    sys.exit(main())
