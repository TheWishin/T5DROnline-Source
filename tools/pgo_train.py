#!/usr/bin/env python3
"""Train the profile for the lifted code's profile-guided optimisation (developer PC only).

    python tools/build_game_dll.py ... --pgo-gen --out <bin>/t5dr_game.dll     (instrumented DLL)
    python tools/pgo_train.py --bin <bin> --vfs game/vfs --out build/pgo-train [--fights ...] [--secs 75]
    -> <out>/t5dr_lifted.profdata (merged), checked by tools/check_profile.py

Each fight boots the game in direct-fight mode (T5_FIGHT, docs/DIRECTFIGHT.md): title, select, the
fight's loading and then --secs seconds of fighting, both players' pads scripted with seeded random
presses (moves, blocks, throws, knock-downs, round ends). Then the DLL writes its counters
(tools/gamedll/pgo_train.c: T5_PGO_TRIGGER) and the game is stopped. The raw profiles of all fights
are merged with llvm-profdata. At most --parallel games run at once, muted, in the background, at
below-normal priority.

What the profile holds: per lifted function (named func_<guest address>, plus the inline helpers of
the generated code and ps3recomp's headers) a structural hash and execution counts; indirect-call
value profiling is off (--pgo-gen compiles with it off), so nothing else. tools/check_profile.py
checks exactly that before the file may ship.
"""
import argparse
import glob
import json
import os
import random
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# fighters and stages that cover different move sets, stage effects (soft focus 24/26/28/34, glow 20) and the
# heaviest stage for the CPU: 30, the pool at night with its crowd of 3D bystanders (players' worst case)
DEFAULT_FIGHTS = ["lil,ask,20,3", "kaz,jin,24,3", "pau,kin,33,3", "xia,bry,34,3", "hwo,ste,26,3", "dvj,yos,28,3",
                  "cha,rav,30,3"]

BUTTONS = ["SQUARE", "TRIANGLE", "CROSS", "CIRCLE", "SQUARE TRIANGLE", "CROSS CIRCLE", "SQUARE CROSS",
           "TRIANGLE CIRCLE"]
DIRS = ["", "", "RIGHT", "LEFT", "DOWN", "UP", "DOWN RIGHT", "DOWN LEFT", "UP RIGHT"]


def pad_script(seed, secs):
    """[(t, held)] random presses for one player: a direction (held or tapped), buttons, pauses."""
    rnd = random.Random(seed)
    t, out = 0.0, []
    while t < secs:
        d = rnd.choice(DIRS)
        b = rnd.choice(BUTTONS) if rnd.random() < 0.7 else ""
        out.append((t, (d + " " + b).strip()))
        t += rnd.choice([0.05, 0.1, 0.15, 0.25])
        out.append((t, d if rnd.random() < 0.3 else ""))
        t += rnd.choice([0.05, 0.1, 0.2, 0.4])
    return out


def write_pad(path, s):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(s)
    for _ in range(200):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.002)


class Run:
    def __init__(self, a, k, fight):
        self.fight = fight
        self.dir = os.path.join(os.path.abspath(a.out), "f%02d_%s" % (k, fight.replace(",", "_")))
        os.makedirs(self.dir, exist_ok=True)
        for f in glob.glob(os.path.join(self.dir, "*")):
            if os.path.isfile(f):
                os.remove(f)
        vfs = os.path.abspath(a.vfs)
        self.trig = os.path.join(self.dir, "trig")
        self.status = os.path.join(self.dir, "status.json")
        self.pads = [os.path.join(self.dir, "pad1.txt"), os.path.join(self.dir, "pad2.txt")]
        for p in self.pads:
            open(p, "w").close()
        env = dict(os.environ)
        env.update({
            "PS3_VFS_ROOT": vfs.replace("\\", "/"),
            "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
            "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0",
            "PS3_WINDOW_BACKGROUND": "1", "PAD_NO_KEYBOARD": "1", "PS3_AUDIO_MUTE": "1",
            "T5_FIGHT": fight, "T5_DF_STATUS_FILE": self.status,
            "PS3_PAD_FILE": self.pads[0], "PS3_PAD_FILE2": self.pads[1],
            "T5_PGO_TRIGGER": self.trig, "LLVM_PROFILE_FILE": os.path.join(self.dir, "fight.profraw"),
        })
        self.log = open(os.path.join(self.dir, "game.log"), "w")
        flags = 0x4000 if os.name == "nt" else 0          # BELOW_NORMAL_PRIORITY_CLASS
        self.p = subprocess.Popen([os.path.join(os.path.abspath(a.bin), "t5dr.exe"),
                                   os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                                  env=env, cwd=self.dir, stdout=self.log, stderr=subprocess.STDOUT,
                                  creationflags=flags)
        self.t0 = time.time()
        self.fight_t = None
        self.secs = a.secs
        self.scripts = [pad_script(1000 + 2 * k, a.secs + 30), pad_script(1001 + 2 * k, a.secs + 30)]
        self.state = "boot"
        self.result = None

    def step(self):
        now = time.time()
        if self.p.poll() is not None and self.state != "done":
            self.state, self.result = "done", "game ended early (exit %s)" % self.p.returncode
            return
        if self.state == "boot":
            if now - self.t0 > 240:
                self.finish("no fight after 240 s")
                return
            try:
                with open(self.status) as f:
                    if json.load(f).get("state") == "fight":
                        self.fight_t, self.state = now, "fight"
            except (OSError, ValueError):
                pass
        elif self.state == "fight":
            rel = now - self.fight_t
            for i in (0, 1):
                s = self.scripts[i]
                while s and s[0][0] <= rel:
                    write_pad(self.pads[i], s.pop(0)[1])
            if rel >= self.secs:
                for p in self.pads:
                    write_pad(p, "")
                open(self.trig + ".write", "w").close()
                self.state, self.write_t = "writing", now
        elif self.state == "writing":
            if os.path.exists(self.trig + ".write.ok"):
                self.finish(None)
            elif now - self.write_t > 60:
                self.finish("the DLL did not write its profile within 60 s")

    def finish(self, err):
        if self.p.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.p.pid)], capture_output=True)
            try:
                self.p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
        self.log.close()
        self.state, self.result = "done", err


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bin", required=True, help="folder with t5dr.exe and the --pgo-gen t5dr_game.dll")
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--fights", nargs="+", default=DEFAULT_FIGHTS, help="T5_FIGHT lines (p1,p2,stage,rounds)")
    ap.add_argument("--secs", type=float, default=75.0, help="seconds of fighting per run")
    ap.add_argument("--parallel", type=int, default=2, help="games at once (at most 3)")
    ap.add_argument("--profdata", default="", help="llvm-profdata.exe (default: next to clang-cl)")
    a = ap.parse_args()
    a.parallel = max(1, min(3, a.parallel))
    os.makedirs(a.out, exist_ok=True)

    pending = list(enumerate(a.fights))
    running, done = [], []
    while pending or running:
        while pending and len(running) < a.parallel:
            k, fight = pending.pop(0)
            running.append(Run(a, k, fight))
            print("start %s" % fight, flush=True)
            time.sleep(2)
        for r in list(running):
            r.step()
            if r.state == "done":
                running.remove(r)
                done.append(r)
                print("%s: %s" % (r.fight, r.result or "profile written"), flush=True)
        time.sleep(0.01)
    bad = [r for r in done if r.result]
    raws = sorted(glob.glob(os.path.join(os.path.abspath(a.out), "f*", "fight.profraw")))
    if bad or len(raws) != len(a.fights):
        sys.exit("training failed: %d of %d fights, %d raw profiles" % (len(done) - len(bad), len(a.fights), len(raws)))
    pd = a.profdata
    if not pd:
        for d in (os.path.join(ROOT, "toolchain", "llvm", "bin"),
                  os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "LLVM", "bin")):
            if os.path.exists(os.path.join(d, "llvm-profdata.exe")):
                pd = os.path.join(d, "llvm-profdata.exe")
                break
    if not pd:
        sys.exit("llvm-profdata.exe not found (--profdata)")
    out = os.path.join(os.path.abspath(a.out), "t5dr_lifted.profdata")
    # --binary-ids are not kept (no build ids in a COFF DLL anyway); sparse: functions never run are left out
    subprocess.run([pd, "merge", "--sparse", "-o", out] + raws, check=True)
    print("wrote %s (%d bytes) from %d fights" % (out, os.path.getsize(out), len(raws)))


if __name__ == "__main__":
    main()
