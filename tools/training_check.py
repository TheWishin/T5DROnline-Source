#!/usr/bin/env python3
"""Check the training overlay's frame data in the game (docs/TRAINING.md).

    python tools/training_check.py [--exe build/cmake/t5dr.exe] [--out DIR] [--vfs DIR] [--keep]

One game in local lockstep (T5_NET_MODE=local: both players on this PC, input
scripted frame by frame with T5_NET_SCRIPT / T5_NET_SCRIPT2) with the overlay
on (T5_TRAINING=frames, T5_TRAINING_LOG): Jin vs Jin, stage 20. After the round
starts, eight exchanges: P1's jab on block and on hit (P2 walks into it), P2's
jab on block and on hit, each once with the attacker and once with the
defender pressing the jab again on every second frame right after (so each
fighter's next jab starts at the first frame it can act: the game's own answer
to "who is plus"), and a whiff. The overlay's log must show

    P1/P2 startup 10 block +3, hit +9, whiff 25 frames

which is what the frame-exact mash test measured (docs/TRAINING.md "How the
frame data is measured"). Wrong offsets in the fight block or a broken tracker
give other numbers. The game runs muted, minimised, at below-normal priority;
nothing of it is kept unless --keep. Exit 0 = PASS.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# Both games of a local pair talk over 127.0.0.1: bind there, not on every interface (no Windows Firewall
# prompt for each build folder's t5dr.exe; docs/NETPLAY.md "Bind address"). An explicit T5_NET_BIND wins.
os.environ.setdefault("T5_NET_BIND", "127.0.0.1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from run_game import game_command  # noqa: E402

SQ, RIGHT, LEFT = 0x8000, 0x20, 0x80
ROUND_FRAME = 762      # lockstep frame the round starts at (Jin vs Jin, stage 20, deterministic)
SPACING = 170


def plan():
    """[(attacker, kind, masher)], the two scripts and the last lockstep frame"""
    s = {1: [], 2: []}
    out = []

    def press(p, f, n, m):
        s[p].append(f"{f}:{n}:{m:#x}")
    cases = [(a, kind, masher) for a in (1, 2) for kind in ("block", "hit") for masher in ("attacker", "defender")]
    for k, (att, kind, masher) in enumerate(cases):
        b = ROUND_FRAME + 60 + SPACING * k
        dfd = 3 - att
        press(att, b - 40, 18, RIGHT if att == 1 else LEFT)          # walk in
        press(att, b, 1, SQ)                                          # the jab
        if kind == "hit":
            press(dfd, b - 12, 22, LEFT if dfd == 2 else RIGHT)       # the defender walks into it
        who = att if masher == "attacker" else dfd
        for f in range(b + 12, b + 70, 2):
            press(who, f, 1, SQ)
        out.append((att, kind, masher))
    b = ROUND_FRAME + 60 + SPACING * len(cases)
    press(1, b - 60, 30, LEFT)                                        # walk away
    press(1, b, 1, SQ)                                                # a jab into the air
    out.append((1, "whiff", None))
    return out, ",".join(s[1]), ",".join(s[2]), b + 120


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.environ.get("PS3_VFS_ROOT", os.path.join(ROOT, "game", "vfs")))
    ap.add_argument("--out", default="", help="working directory (default: a temporary one)")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--keep", action="store_true", help="keep the working directory")
    a = ap.parse_args()

    cases, s1, s2, last = plan()
    out = os.path.abspath(a.out) if a.out else tempfile.mkdtemp(prefix="training_check_")
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "training.log")
    env = {"PS3_VFS_ROOT": a.vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(a.vfs, "dev_hdd0").replace("\\", "/"),
           "PS3_WINDOW_BACKGROUND": "1", "PS3_AUDIO_MUTE": "1",
           "T5_NET_MODE": "local", "T5_NET_START": "external", "T5_NET_LOCALPAD": "0", "T5_RB_MODE": "off",
           "T5_FIGHT": "jin,jin,20,3", "T5_NET_SCRIPT": "@" + s1, "T5_NET_SCRIPT2": "@" + s2,
           "T5_NET_LOG": os.path.join(out, "frames.log"),
           "T5_TRAINING": "frames", "T5_TRAINING_ALL": "1", "T5_TRAINING_LOG": log}
    argv, full_env, _ = game_command(ROOT, env)
    argv[0] = os.path.abspath(a.exe)
    argv[1] = os.path.join(a.vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")
    flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    t0 = time.time()
    with open(os.path.join(out, "game.log"), "w") as gl:
        p = subprocess.Popen(argv, env=full_env, cwd=out, stdout=gl, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            frames = os.path.join(out, "frames.log")
            while p.poll() is None and time.time() - t0 < a.timeout:
                time.sleep(1)
                try:
                    with open(frames, "rb") as f:
                        f.seek(max(0, os.path.getsize(frames) - 400))
                        tail = [ln for ln in f.read().decode(errors="replace").splitlines() if ln[:1].isdigit()]
                    if tail and int(tail[-1].split()[0]) >= last:
                        break
                except (OSError, ValueError):
                    pass
        finally:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=20)
    results = []
    if os.path.exists(log):
        for line in open(log):
            m = re.match(r"\d+ result P(\d) startup (\d+) (\w+) adv ([+-]\d+) total (\d+)", line)
            if m:
                results.append((int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))))
    want = {"block": 3, "hit": 9}
    ok = True
    print(f"{len(results)} results in {time.time() - t0:.0f} s ({out})")
    for r in results:
        print(f"    P{r[0]} i{r[1]} {r[2]} {r[3]:+d}" + (f" {r[4]}F" if r[2] == "whiff" else ""))
    # every result of a kind must carry that kind's numbers (a masher's own jab adds more of the same)
    for att in (1, 2):
        for kind in ("block", "hit"):
            got = [r for r in results if r[0] == att and r[2] == kind]
            good = len(got) >= 2 and all(r[1] == 10 and r[3] == want[kind] for r in got)
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} P{att} jab on {kind}: {len(got)} result(s), want i10 {want[kind]:+d}")
    wh = [r for r in results if r[2] == "whiff"]
    good = any(r[0] == 1 for r in wh) and all(r[1] == 10 and r[4] == 25 for r in wh)
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} whiffs: {len(wh)} result(s), want i10 25F")
    if not a.keep and not a.out:
        shutil.rmtree(out, ignore_errors=True)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
