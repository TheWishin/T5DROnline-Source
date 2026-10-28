#!/usr/bin/env python3
"""Hit effects at a low frame rate (GitHub #12: the EWGF's lightning) -- a test in the real game.

    python tools/effects_test.py [--exe build/cmake/t5dr.exe] [--vfs game/vfs] [--out DIR]
                                 [--slow-gpu 16000000,256 | --slow-gpu 0] [--n 6] [--min 40] [NAME=VALUE ...]

Boots a direct fight (Kazuya vs Heihachi, stage 20, docs/DIRECTFIGHT.md), Kazuya does a scripted Electric Wind
God Fist (f, n, d, d/f+2 with the 2 on the d/f frame) every 150 frames into a Heihachi who walks forward, and
counts per picture the effect draws the game submitted (RSX_FX_COUNT=1: the latency log's `H` lines). An effect
"frame" is a picture with 40 or more effect draws above the count before the press. By default the graphics
card is slowed to about 30 fps (RSX_TEST_SLOW_GPU, the GT 730 of GitHub #12 on an RTX 3090; a slower card needs
a smaller number) -- the case where the hit effects used to end after 3-13 frames instead of 60-70 (ps3recomp
patch 0085: the FIFO walker now waits for the game's semaphore ACQUIRE, as the RSX does). PASS when every EWGF
from the third on (the first two can fall into the fight's start) shows the effect for at least --min frames.
GCM_SEMA_ACQUIRE=0 shows the old behaviour.

Exit code 0 PASS, 1 FAIL, 2 the run did not give an answer (no fight, too fast for the test, ...).
"""
import argparse, csv, json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, D, TRI, LEFT = 0x20, 0x40, 0x1000, 0x80   # pad bits: right (forward for P1), down, triangle (2 = right punch), left


def script(n, start, gap, walk=40):
    """P1's per-frame script (frame:hold:buttons) and the frames of each 2 press."""
    p1, plan = [], []
    for k in range(n):
        a = start + k * gap
        p1 += [(a - walk - 15, walk, R), (a, 2, R), (a + 4, 1, D), (a + 5, 3, R | D), (a + 5, 2, TRI)]
        plan.append(a + 5)
    return "@" + ",".join("%d:%d:%x" % e for e in p1), plan


def effect_frames(lat, presses):
    """Per press: pictures whose effect draw count is 40+ above the count 3 pictures before the press. The flip
    numbers of the H lines are matched to the fight's frames by the shift that makes frames 8-13 after every press
    the busiest (as the lightning is there)."""
    fx = {}
    for ln in open(lat, errors="replace"):
        f = ln.split()
        if ln.startswith("H ") and len(f) >= 4:
            fx[int(f[2])] = int(f[3])
    if not fx:
        return None
    best = max(range(-60, 61), key=lambda dl: sum(fx.get(p + dl + i, 0) - fx.get(p + dl - 3, 0)
                                                 for p in presses for i in range(8, 14)))
    out = []
    for p in presses:
        b = p + best
        base = fx.get(b - 3, 0)
        out.append(sum(1 for i in range(120) if fx.get(b + i, 0) - base >= 40))
    return out


def fps_of(frames_csv, a, b):
    try:
        rows = list(csv.DictReader(open(frames_csv).readlines()[1:]))
        dt = sorted(int(r["dt_us"]) for r in rows[a:b] if r["dt_us"].isdigit() and int(r["dt_us"]) > 0)
        return 1e6 / dt[len(dt) // 2] if dt else None
    except (OSError, KeyError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.environ.get("PS3_VFS_ROOT", os.path.join(ROOT, "game", "vfs")))
    ap.add_argument("--out", default="")
    ap.add_argument("--slow-gpu", default="16000000,256", help="RSX_TEST_SLOW_GPU (0: the card as it is)")
    ap.add_argument("--n", type=int, default=6, help="EWGFs (from fight frame 1700, every 150 frames)")
    ap.add_argument("--min", type=int, default=40, help="effect pictures each EWGF must show")
    ap.add_argument("--max-fps", type=float, default=40.0, help="with --slow-gpu: a faster run gives no answer")
    ap.add_argument("env", nargs="*", help="extra NAME=VALUE for the game")
    a = ap.parse_args()

    out = os.path.abspath(a.out or os.path.join(ROOT, "build", "effects-test", time.strftime("%Y%m%d-%H%M%S")))
    os.makedirs(out, exist_ok=True)
    start, gap = 1700, 150
    p1, presses = script(a.n, start, gap)
    vfs = os.path.abspath(a.vfs)
    env = dict(os.environ)
    env.update({
        "PS3_VFS_ROOT": vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
        "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
        "PAD_NO_KEYBOARD": "1", "PS3_AUDIO_MUTE": "1", "T5_FIGHT": "kaz,hei,20,3",
        "T5_DF_LOG": os.path.join(out, "df_frames.log"), "PS3_FRAMELOG": os.path.join(out, "frames.csv"),
        "T5_DF_SCRIPT": p1, "T5_DF_SCRIPT2": "@0:99999:%x" % LEFT,   # P2 walks forward (towards P1): every EWGF hits
        "RSX_FX_COUNT": "1", "PS3_LATENCY_LOG": os.path.join(out, "lat.log"),
    })
    if a.slow_gpu and a.slow_gpu != "0":
        env["RSX_TEST_SLOW_GPU"] = a.slow_gpu
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    stop = start + a.n * gap + 60
    with open(os.path.join(out, "game.log"), "w") as log:
        p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")], env=env,
                             cwd=out, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        t0, last = time.time(), 0
        try:
            while p.poll() is None and time.time() - t0 < 600 and last < stop:
                time.sleep(1.0)
                try:
                    for ln in open(env["T5_DF_LOG"]):
                        if ln.startswith("F "):
                            last = int(ln.split()[1])
                except (OSError, ValueError, IndexError):
                    pass
        finally:
            if p.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                else:
                    p.kill()
                p.wait()
    if last < stop:
        print("NO ANSWER: the fight reached frame %d of %d (%s)" % (last, stop, os.path.join(out, "game.log")))
        return 2
    fr = effect_frames(os.path.join(out, "lat.log"), presses)
    fps = fps_of(os.path.join(out, "frames.csv"), 1500, 2400)
    print("fps %s, effect pictures per EWGF %s" % ("%.1f" % fps if fps else "?", fr))
    json.dump({"fps": fps, "effect_frames": fr, "presses": presses },
              open(os.path.join(out, "result.json"), "w"), indent=1)
    if not fr:
        print("NO ANSWER: no H lines (RSX_FX_COUNT needs ps3recomp patch 0081)")
        return 2
    if "RSX_TEST_SLOW_GPU" in env and fps and fps > a.max_fps:
        print("NO ANSWER: %.1f fps -- the slowed card is still too fast for this test (a larger --slow-gpu)" % fps)
        return 2
    ok = all(n >= a.min for n in fr[2:])
    print("%s: every EWGF from the third on shows its effect for %d+ pictures" % ("PASS" if ok else "FAIL", a.min)
          if ok else "FAIL: EWGFs 3-%d show their effect for %s pictures (at least %d expected)" % (len(fr), fr[2:], a.min))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
