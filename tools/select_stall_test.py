#!/usr/bin/env python3
"""Title -> character select after a fight, many times in one persistent game (docs/DIRECTFIGHT.md
"Select stall after a fight").

    python tools/select_stall_test.py --exe build/cmake/t5dr.exe --out build/<you>/runs/s1 [--cycles 20]
        [--hog N] [--cpus N] [--fs-delay MS] [--env K=V ...] [--stall-seconds 60]

One game, started once with T5_CTL_DIR and no netplay (offline sessions). Every cycle is a "fight"
command for a new session -- what the launcher sends for a new opponent: the running fight (or its
loading) is left, the game goes back to the title (a fight ran since the last title visit), puts the
match state back as at boot, calls start VS and drives the new select screen into the next fight.
The next command comes 0.5-4 s after FIGHT START, so the old fight is left in its loading, its intros
or the fight itself, in turn.

Checked per cycle: FIGHT START of the new match within --stall-seconds of the command, no fault line
(NULL access, bad guest call, crash, stuck). A select screen that waits in its loading phase longer
than that is a stall: the game's reader and loader state is dumped through PS3_DEBUG and the run
ends with exit code 1.

Load (a PC in use, the conditions of the reports):
  --cpus N     the game and the hogs share N logical processors (affinity, inherited; --cpu-first K:
               from processor K on, for two runs side by side)
  --hog N      N busy-loop processes of our own at normal priority beside the game (which runs at
               below-normal priority, as every test game here)
  --fs-delay MS  PS3_TEST_FS_DELAY: every file open/read of the game waits MS ms (a slow disk)

The game runs muted, minimized-in-background and at below-normal priority; only processes this
script started are ever stopped.
"""
import argparse
import ctypes
import json
import os
import random
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = time.time()

# ("reset: waiting in mode" is not one here: with --fs-delay a leave or reset may take that long;
#  a reset that never ends shows as no FIGHT START, and after 60 s the game ends itself: STUCK)
BAD = [
    ("bad_guest_call", re.compile(r"guest_call: OPD .* not registered")),
    ("null_call", re.compile(r"\[null-call\]")),
    ("null_write", re.compile(r"\[null-write\]")),
    ("null_read", re.compile(r"\[null-read\]")),
    ("fence_overflow", re.compile(r"fence queue overflow")),
    ("crash", re.compile(r"\[CRASH\]")),
    ("abort", re.compile(r"abort\(\) is called")),
    ("stuck_exit", re.compile(r"STUCK:")),
    ("bad_fight_line", re.compile(r"no usable T5_FIGHT")),     # a harness error, not the game's
]
RE_FIGHT = re.compile(r"\[df\] frame (\d+): FIGHT START match (\d+)")
RE_STARTVS = re.compile(r"\[df\] frame (\d+): start VS battle \(func_0004E9DC\(4, 3\)\) from the title mode")
RE_STAGE = re.compile(r"\[df\] frame (\d+): state stage")
RE_WAITSEL = re.compile(r"\[df\] frame (\d+): waiting for the select screen \(mode (\d+), select state (\d+)")
RE_READER = re.compile(r"\[df\] frame (\d+): (boot state of .*|before the restore: .*|the match state areas are back .*|"
                       r"the async reader .*|.*reader.*)")
CHARS = ["kaz", "hei", "ask", "law", "jin", "xia", "pau", "bry", "nin", "lei", "ste", "hwo"]


def log(msg):
    print(f"[{time.time() - T0:8.1f}s] {msg}", flush=True)


def bad_lines(text):
    return [name for name, rx in BAD if rx.search(text)]


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    for _ in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:      # the game reads it with delete sharing; retry
            time.sleep(0.02)


def set_own_affinity(n, first=0):
    """n logical processors from `first` on for this process -- children (game, hogs) inherit it."""
    if not n or os.name != "nt":
        return
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    mask = ((1 << n) - 1) << first
    if not k32.SetProcessAffinityMask(ctypes.c_void_p(k32.GetCurrentProcess()), ctypes.c_size_t(mask)):
        log(f"could not set the affinity mask 0x{mask:X}")
    else:
        log(f"affinity: logical processors {first}..{first + n - 1} (game and hogs)")


class Game:
    def __init__(self, a):
        self.a = a
        self.dir = os.path.abspath(os.path.join(a.out, "run1"))
        os.makedirs(self.dir, exist_ok=True)
        self.ctl = os.path.join(self.dir, "ctl")
        os.makedirs(self.ctl, exist_ok=True)
        self.status_path = os.path.join(self.dir, "status.json")
        self.result_path = os.path.join(self.dir, "result.json")
        self.pad_path = os.path.join(self.dir, "pad.txt")
        self.dbg = os.path.join(self.dir, "dbg.cmd")
        open(self.pad_path, "w").close()
        open(self.dbg, "w").close()
        self.seq = 0
        self.proc = None
        self.starts = 0
        self.log_path = None

    def env(self):
        vfs = os.path.abspath(self.a.vfs)
        env = dict(os.environ)
        env.update({
            "PS3_VFS_ROOT": vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
            "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
            "PS3_AUDIO_MUTE": "1", "PAD_NO_KEYBOARD": "1", "T5_NET_LOCALPAD": "0", "PS3_PAD_FILE": self.pad_path,
            "T5_DF_STATUS_FILE": self.status_path, "T5_CTL_DIR": self.ctl, "PS3_DEBUG": self.dbg,
        })
        if self.a.fs_delay:
            env["PS3_TEST_FS_DELAY"] = str(self.a.fs_delay)
        for kv in self.a.env:
            k, v = kv.split("=", 1)
            env[k] = v
        return env

    def start(self):
        self.starts += 1
        self.log_path = os.path.join(self.dir, f"game{self.starts}.log")
        lf = open(self.log_path, "w")
        vfs = os.path.abspath(self.a.vfs)
        self.proc = subprocess.Popen([os.path.abspath(self.a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                                     cwd=self.dir, env=self.env(), stdout=lf, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        log(f"game started, pid {self.proc.pid}, log {self.log_path}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                pass

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def send(self, cmd, **kw):
        self.seq += 1
        write_atomic(os.path.join(self.ctl, "cmd.json"), json.dumps(dict(kw, seq=self.seq, cmd=cmd, time=time.time())))

    def log_size(self):
        try:
            return os.path.getsize(self.log_path)
        except (OSError, TypeError):
            return 0

    def log_since(self, pos):
        try:
            with open(self.log_path, "rb") as f:
                f.seek(pos)
                return f.read().decode("utf-8", "replace")
        except (OSError, TypeError):
            return ""

    def debug(self, *cmds):
        """Ask the running game (PS3_DEBUG console); the answers go to dbg.cmd.out."""
        for c in cmds:
            with open(self.dbg, "w") as f:
                f.write(c + "\n")
            t = time.time()
            while time.time() - t < 10:
                time.sleep(0.2)
                try:
                    if os.path.getsize(self.dbg) == 0:
                        break
                except OSError:
                    break
            time.sleep(0.5)


def fight_env(g, k):
    return {"T5_NET_ROUNDS": "1", "T5_NET_RESULT_FILE": g.result_path, "T5_DF_STATUS_FILE": g.status_path,
            "T5_HUD_NAMES": "Stall One|Stall Two", "T5_HUD_RANKS": f"{k % 37},{(k * 7) % 37}"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--cycles", type=int, default=20)
    ap.add_argument("--stall-seconds", type=float, default=60.0,
                    help="a new match not at FIGHT START this long after its command = a stall")
    ap.add_argument("--wait", default="0.5:4", help="seconds after FIGHT START before the next command (min:max)")
    ap.add_argument("--hog", type=int, default=0, help="busy-loop processes of our own beside the game")
    ap.add_argument("--cpus", type=int, default=0, help="game and hogs on N logical processors (from --cpu-first on)")
    ap.add_argument("--cpu-first", type=int, default=0, help="the first of the --cpus processors (two runs side by side)")
    ap.add_argument("--fs-delay", type=int, default=0, help="PS3_TEST_FS_DELAY ms per file open/read")
    ap.add_argument("--keep-going", action="store_true", help="after a stall: restart the game and go on")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rnd = random.Random(a.seed)
    lo, hi = (float(x) for x in a.wait.split(":"))
    set_own_affinity(a.cpus, a.cpu_first)
    hogs = []
    for _ in range(a.hog):
        hogs.append(subprocess.Popen([sys.executable, "-c", "while True: pass"]))
    if hogs:
        log(f"{len(hogs)} hog process(es) at normal priority")
    g = Game(a)
    report = {"cycles": [], "stalls": 0, "bad": [], "args": vars(a)}
    rc = 0
    try:
        for i in range(a.cycles):
            k = i + 1
            mid = f"s{k:03d}"
            line = f"{CHARS[(2 * i) % len(CHARS)]},{CHARS[(2 * i + 1) % len(CHARS)]},{20 + i % 12},1"
            pos = g.log_size() if g.running() else 0
            env = dict(fight_env(g, k), T5_FIGHT=line)
            t0 = time.time()
            if not g.running():
                g.seq = 0      # a new game: its commands count from 1 again
                g.send("fight", match=mid, env=env)
                g.start()
                pos = 0
            else:
                g.send("fight", match=mid, env=env)
            c = {"k": k, "match": mid, "line": line}
            fight = None
            while time.time() - t0 < a.stall_seconds and g.running():
                text = g.log_since(pos)
                if bad_lines(text):
                    break
                m = RE_FIGHT.search(text)
                if m:
                    fight = m
                    break
                time.sleep(0.2)
            text = g.log_since(pos)
            c["seconds"] = round(time.time() - t0, 1)
            sv, st = RE_STARTVS.search(text), RE_STAGE.search(text)
            c["select_frames"] = int(st.group(1)) - int(sv.group(1)) if sv and st else None
            c["select_waits"] = len(RE_WAITSEL.findall(text))
            c["reader"] = [m.group(0) for m in RE_READER.finditer(text)
                           if "boot state of" in m.group(0) or "before the restore" in m.group(0)]
            c["bad"] = bad_lines(text)
            c["ok"] = bool(fight) and not c["bad"]
            report["cycles"].append(c)
            log(f"cycle {k} ({line}): {'OK' if c['ok'] else 'FAILED'} -- to FIGHT {c['seconds']} s, select set-up "
                f"{c['select_frames']} frames, {c['select_waits']} wait line(s)"
                + (f", BAD {c['bad']}" if c["bad"] else "") + ("" if g.running() else ", the game is gone"))
            for r in c["reader"]:
                log(f"    {r}")
            if not c["ok"]:
                rc = 1
                if not fight and g.running():
                    report["stalls"] += 1
                    log("    stall: dumping the reader, its request pool and the threads (dbg.cmd.out)")
                    g.debug("stat", "threads", "mem 1009FE20 80", "mem 1009FF68 2560", "mem 1008F060 32", "hle")
                    waits = RE_WAITSEL.findall(g.log_since(pos))
                    if waits:
                        log(f"    last select wait line: frame {waits[-1][0]}, mode {waits[-1][1]}, select state {waits[-1][2]}")
                if not a.keep_going:
                    break
                g.stop()
                continue
            time.sleep(rnd.uniform(lo, hi))
    finally:
        g.stop()
        for h in hogs:
            h.kill()
        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
    n_ok = sum(1 for c in report["cycles"] if c["ok"])
    frames = [c["select_frames"] for c in report["cycles"] if c["select_frames"] is not None]
    log(f"{'ALL OK' if rc == 0 else 'FAILED'}: {n_ok} of {len(report['cycles'])} cycles, {report['stalls']} stall(s); select "
        f"set-up frames min {min(frames) if frames else '-'} max {max(frames) if frames else '-'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
