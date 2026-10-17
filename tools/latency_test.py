#!/usr/bin/env python3
"""Input latency, end to end: from the pad state change to the presented frame.

    python tools/latency_test.py [--exe build/cmake/t5dr.exe] [--out DIR]
                                 [--presses 40] [--fight lil,ask,20,3] [--cpus N]
                                 [--frames] [--analyze-only] [NAME=VALUE ...]

Boots straight into a fight (direct fight, docs/DIRECTFIGHT.md) with the window
minimised and P2 idle, and taps P1's jab (SQUARE, Tekken's 1 = left punch) at a
random moment every ~1.2 s. The runtime's latency probe (PS3_LATENCY_LOG,
ps3recomp patch 0034, runtime/platform/lat_log.h) stamps every step on the
QueryPerformanceCounter clock, which Python's perf_counter_ns() also reads:

    press      the script writes the pad file (PS3_PAD_FILE)
    E          the pad layer's 1 ms sampler saw the button go down
    R          a read handed the title the new buttons (keyread's cellPadGetData,
               or netplay's local sample)
    F          the title asked for a flip: its frame is simulated and drawn;
               with the watched words (P1's pad block and the move word below)
    X          the FIFO walker reached that flip: the frame is translated
    P          Present() returned for that flip
    C          the display's vblank clock (DWM): last vblank, period

Per press: the consuming frame is the first flip whose pad block holds the
button; the reacting frame is the first flip whose move word (P1's current
move, KMOVE below) changed after the press. The breakdown:

    sample     press -> E           (the 1 ms sampler)
    read       E -> consuming frame start (K: the flip completion that released
               the frame that read it)
    game       consuming frame -> reacting frame (the game's own frames)
    sim        reacting frame start -> its flip request (F)
    xlat       F -> X (translation)
    queue      X -> P (wait for the present + the present call)
    display    P -> the display vblank that shows it (next vblank in the DWM
               clock after P + the GPU copy; +1 refresh when the window is
               composed by DWM rather than flipped independently -- a
               minimised test window cannot show which, see docs/RENDER_PERF.md)

--frames also dumps the presented frames around 6 presses (LD_FRAME_DUMP with a
gate file) as PNG next to the log, to check by eye that the reacting frame is
the first one where the jab shows.

--analyze-only DIR re-reads an earlier run.
"""
import argparse
import ctypes
import json
import os
import random
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WIN = os.name == "nt"

PAD_BLOCK = 0x10099F24      # the two pad state blocks (P1 first), 0x70 bytes
PHASE = 0x1008F070          # fight phase word: 17 = fighting
CONSUME = 0x1008F01C        # P1's button hold counter in the fight (1, 2, 3 ... while held): the
                            # first frame whose fight logic saw the press (--discover, runs disc1)
KMOVE = 0x10090064          # 0x80000000 for one frame when the move starts: the jab's first frame
SQUARE_BIT = 0x8000         # cellPad digital2 SQUARE in the R line's mask (button[3] << 8 | button[2])


def qpc_freq():
    if IS_WIN:
        f = ctypes.c_longlong()
        ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(f))
        return f.value
    return 10_000_000


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def busy_cpus():
    """(idle, total) seconds of all processors so far (GetSystemTimes)"""
    if not IS_WIN:
        return (0.0, 0.0)
    from ctypes import wintypes as W
    i, k, u = W.FILETIME(), W.FILETIME(), W.FILETIME()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    ft = lambda t: (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7
    return ft(i), ft(k) + ft(u)


def proc_cpu(pid):
    if not IS_WIN:
        return 0.0
    from ctypes import wintypes as W
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return 0.0
    c, e, k, u = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
    ctypes.windll.kernel32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
    ctypes.windll.kernel32.CloseHandle(h)
    ft = lambda t: (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7
    return ft(k) + ft(u)


def parse_log(path):
    ev = {k: [] for k in "EKRFXPDCVBN"}
    freq = 10_000_000
    watch = []
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("# qpc_frequency="):
                freq = int(line.split("=")[1])
                continue
            if line.startswith("# watch"):
                for w in line.split()[2:]:
                    a, l = w.split(":")
                    watch.append((int(a, 16), int(l, 16)))
                continue
            p = line.split()
            if len(p) < 2 or p[0] not in ev:
                continue
            try:
                ev[p[0]].append([int(p[1])] + p[2:])
            except ValueError:
                pass
    return freq, watch, ev


def word_at(watch, words, ea):
    """value of the guest word at ea among an F line's watched words"""
    i = 0
    for a, l in watch:
        if a <= ea < a + l:
            return int(words[i + (ea - a) // 4], 16)
        i += l // 4
    return None


def analyze(out, move_ea=None, move_off=None, quiet=False):
    freq, watch, ev = parse_log(os.path.join(out, "lat.log"))
    with open(os.path.join(out, "presses.json")) as f:
        meta = json.load(f)
    ms = 1000.0 / freq
    to_q = lambda ns: ns * freq // 1_000_000_000
    presses = [to_q(p) for p in meta["presses"]]
    if move_ea is None:
        move_ea = meta.get("move_ea")
    F = [(e[0], int(e[1]), e[2:]) for e in ev["F"]]
    Xl = sorted((e[0], int(e[1])) for e in ev["X"])
    Xq = [x[0] for x in Xl]
    P = {}
    for e in ev["P"]:
        P.setdefault(int(e[1]), e[0])
    K = [(e[0], int(e[2])) for e in ev["K"]]          # (qpc, walked seq at release)
    C = [(e[0], int(e[1]), int(e[2])) for e in ev["C"]]
    E = [(e[0], int(e[2], 16)) for e in ev["E"] if e[1] == "0"]
    R = [(e[0], int(e[2], 16)) for e in ev["R"] if e[1] == "0" and e[3] in ("G", "L")]
    import bisect
    Fq = [x[0] for x in F]
    Kq = [k[0] for k in K]

    def first_after(lst, t, pred=lambda x: True):
        i = bisect.bisect_left([x[0] for x in lst], t)
        for x in lst[i:]:
            if pred(x):
                return x
        return None

    def consumed(words):
        v = word_at(watch, words, CONSUME)
        return v is not None and v != 0

    rows = []
    for t in presses:
        e = first_after(E, t - freq // 1000, lambda x: x[1] & SQUARE_BIT)
        r = first_after(R, t - freq // 1000, lambda x: x[1] & SQUARE_BIT)
        if not e or not r or e[0] - t > freq // 10:
            continue
        i = bisect.bisect_left(Fq, t)
        if i == 0 or i >= len(F):
            continue
        ph = word_at(watch, F[i - 1][2], PHASE)
        if ph != 17 or consumed(F[i - 1][2]):
            continue
        base = word_at(watch, F[i - 1][2], move_ea) if move_ea else None
        cons = react = None
        for j in range(i, min(i + 30, len(F))):
            fq, seq, words = F[j]
            if cons is None and consumed(words):
                cons = j
            if react is None and move_ea is not None and word_at(watch, words, move_ea) != base:
                react = j
            if cons is not None and react is not None:
                break
        if react is None or cons is None:
            continue
        fq, _, _ = F[react]
        # the walker numbers flips itself (a request that never reached it at
        # boot shifts the two counts): the reacting frame's flip is the first
        # one the walker reached after the request
        k = bisect.bisect_right(Xq, fq)
        if k >= len(Xl):
            continue
        x, seq = Xl[k]
        p = P.get(seq)
        if p is None:
            continue
        # the frame start of the consuming / reacting frame: the flip completion
        # (K) just before its flip request, i.e. the release of that frame
        def start_of(j):
            k = bisect.bisect_right(Kq, F[j][0]) - 1
            return Kq[k] if k >= 0 else None
        cs, rs = start_of(cons), start_of(react)
        c = None
        k = bisect.bisect_right([cc[0] for cc in C], p) - 1
        if k >= 0:
            c = C[k]
        disp = None
        if c:
            vb, per = c[1], c[2]
            gpu = freq // 2000              # the present copy (~0.5 ms) must land before the vblank
            n = -(-(p + gpu - vb) // per)     # DWM may stamp the coming vblank: n can be <= 0
            disp = vb + n * per
        rows.append(dict(press=t, E=e[0], R=r[0], cons_start=cs, cons_seq=F[cons][1], react_start=rs,
                         react_seq=seq, frames_game=react - cons, F=fq, X=x, P=p, disp=disp))
    if not rows:
        print("no usable presses (phase 17 with a reaction) in", out)
        return None
    parts = [("sample", lambda r: r["E"] - r["press"]),
             ("read+wait", lambda r: r["cons_start"] - r["E"] if r["cons_start"] else 0),
             ("game frames", lambda r: r["react_start"] - r["cons_start"]),
             ("sim", lambda r: r["F"] - r["react_start"]),
             ("translation", lambda r: r["X"] - r["F"]),
             ("present queue", lambda r: r["P"] - r["X"]),
             ("to display vblank", lambda r: (r["disp"] - r["P"]) if r["disp"] else 0),
             ("TOTAL press->display", lambda r: (r["disp"] or r["P"]) - r["press"])]
    res = {"n": len(rows), "parts": {}}
    lines = ["%-22s %8s %8s %8s %8s" % ("part (ms)", "median", "mean", "p10", "p90")]
    for name, fn in parts:
        v = [fn(r) * ms for r in rows]
        res["parts"][name] = dict(median=statistics.median(v), mean=statistics.mean(v), p10=pct(v, 10), p90=pct(v, 90))
        lines.append("%-22s %8.2f %8.2f %8.2f %8.2f" % (name, statistics.median(v), statistics.mean(v), pct(v, 10), pct(v, 90)))
    gf = [r["frames_game"] for r in rows]
    lines.append("game frames from the consuming frame to the reaction: %s" %
                 ", ".join("%d x%d" % (k, gf.count(k)) for k in sorted(set(gf))))
    res["game_frames"] = {str(k): gf.count(k) for k in sorted(set(gf))}
    if C:
        per = statistics.median([c[2] for c in C]) * ms
        res["display_period_ms"] = per
        lines.append("display refresh %.3f ms (%.3f Hz, DWM clock)" % (per, 1000.0 / per))
    lines.append("presses used: %d of %d" % (len(rows), len(presses)))
    txt = "\n".join(lines)
    if not quiet:
        print(txt)
    with open(os.path.join(out, "latency.txt"), "w") as f:
        f.write(txt + "\n")
    with open(os.path.join(out, "latency.json"), "w") as f:
        json.dump(dict(res, rows=rows), f, indent=1)
    return res


def discover(out):
    """Which words of the fight block change a few frames after each jab and
    not in between: candidates for the move word (PS3_LATENCY_DUMP)."""
    import struct
    freq, watch, ev = parse_log(os.path.join(out, "lat.log"))
    with open(os.path.join(out, "presses.json")) as f:
        meta = json.load(f)
    dump = open(os.path.join(out, "lat.log.dump"), "rb").read()
    base, ln = meta["dump"]
    rec = 12 + ln
    frames = []
    for o in range(0, len(dump) - rec + 1, rec):
        seq, q = struct.unpack_from("<Iq", dump, o)
        frames.append((q, dump[o + 12:o + 12 + ln]))
    to_q = lambda ns: ns * freq // 1_000_000_000
    presses = [to_q(p) for p in meta["presses"]]
    import bisect
    fq = [f[0] for f in frames]
    nw = ln // 4
    score = [0] * nw
    lag = [[] for _ in range(nw)]
    idle_changes = [0] * nw
    used = 0
    for t in presses:
        i = bisect.bisect_left(fq, t)
        if i < 30 or i + 30 > len(frames):
            continue
        used += 1
        pre = frames[i - 1][1]
        for w in range(nw):
            a = pre[w * 4:w * 4 + 4]
            for j in range(i, i + 12):
                if frames[j][1][w * 4:w * 4 + 4] != a:
                    score[w] += 1
                    lag[w].append(j - i)
                    break
            # changes in the 20 frames before the press (idle): a move word stays put
            for j in range(i - 20, i - 1):
                if frames[j][1][w * 4:w * 4 + 4] != frames[j + 1][1][w * 4:w * 4 + 4]:
                    idle_changes[w] += 1
    cands = [(score[w], -idle_changes[w], w) for w in range(nw) if score[w] >= used * 0.9 and idle_changes[w] == 0]
    cands.sort(reverse=True)
    print("presses used %d; words that change after every press and never in the idle frames before:" % used)
    for s, ic, w in cands[:40]:
        print("  %08X  changed after %d presses, lag %s" % (base + w * 4, s, sorted(set(lag[w]))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.environ.get("PS3_VFS_ROOT", os.path.join(ROOT, "game", "vfs")))
    ap.add_argument("--cpus", default="")
    ap.add_argument("--fight", default="lil,ask,20,3")
    ap.add_argument("--presses", type=int, default=40)
    ap.add_argument("--interval", type=float, default=1.2)
    ap.add_argument("--hold", type=float, default=0.10)
    ap.add_argument("--settle", type=float, default=14.0, help="s after fight start before the first press")
    ap.add_argument("--move-ea", default="", help="hex address of P1's move word (default: the known one)")
    ap.add_argument("--discover", action="store_true", help="dump the fight block per flip and list move-word candidates")
    ap.add_argument("--frames", action="store_true", help="dump presented frames around 6 presses")
    ap.add_argument("--out", default="")
    ap.add_argument("--analyze-only", default="")
    ap.add_argument("env", nargs="*")
    a = ap.parse_args()
    move_ea = int(a.move_ea, 16) if a.move_ea else KMOVE_DEFAULT
    if a.analyze_only:
        if a.discover:
            discover(a.analyze_only)
        else:
            analyze(a.analyze_only, move_ea if a.move_ea else None)
        return

    out = os.path.abspath(a.out or os.path.join(ROOT, "build", "latency", time.strftime("%Y%m%d-%H%M%S")))
    os.makedirs(out, exist_ok=True)
    vfs = os.path.abspath(a.vfs)
    env = dict(os.environ)
    watch = "%X:70,%X:4,%X:4,%X:4" % (PAD_BLOCK, PHASE, CONSUME, move_ea)
    env.update({
        "PS3_VFS_ROOT": vfs.replace("\\", "/"),
        "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
        "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0",
        "PS3_WINDOW_BACKGROUND": "1", "PAD_NO_KEYBOARD": "1",
        "T5_FIGHT": a.fight,
        "T5_DF_STATUS_FILE": os.path.join(out, "status.json"),
        "PS3_PAD_FILE": os.path.join(out, "pad.txt"),
        "PS3_LATENCY_LOG": os.path.join(out, "lat.log"),
        "PS3_LATENCY_WATCH": watch,
    })
    meta = {"exe": os.path.abspath(a.exe), "fight": a.fight, "cpus": a.cpus, "presses": [],
            "move_ea": move_ea, "env": a.env}
    if a.discover:
        env["PS3_LATENCY_DUMP"] = "1008E000:4000"
        meta["dump"] = [0x1008E000, 0x4000]
    gate = os.path.join(out, "dump.gate")
    if a.frames:
        os.makedirs(os.path.join(out, "frames"), exist_ok=True)
        env["LD_FRAME_DUMP"] = os.path.join(out, "frames")
        env["LD_FRAME_DUMP_EVERY"] = "1"
        env["LD_FRAME_DUMP_GATE"] = gate
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    open(env["PS3_PAD_FILE"], "w").close()
    mask = None
    if a.cpus:
        mask = int(a.cpus, 16) if a.cpus.lower().startswith("0x") else (1 << int(a.cpus)) - 1
    k32 = ctypes.WinDLL("kernel32") if IS_WIN else None
    me = old = None
    if mask and IS_WIN:
        me = k32.GetCurrentProcess()
        pm, sm = ctypes.c_size_t(), ctypes.c_size_t()
        k32.GetProcessAffinityMask(ctypes.c_void_p(me), ctypes.byref(pm), ctypes.byref(sm))
        old = pm.value
        k32.SetProcessAffinityMask(ctypes.c_void_p(me), ctypes.c_size_t(mask))
    log = open(os.path.join(out, "game.log"), "w")
    try:
        p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                             env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT)
    finally:
        if old:
            k32.SetProcessAffinityMask(ctypes.c_void_p(me), ctypes.c_size_t(old))

    def setpad(s):
        tmp = env["PS3_PAD_FILE"] + ".tmp"
        with open(tmp, "w") as f:
            f.write(s)
        for _ in range(200):
            try:
                os.replace(tmp, env["PS3_PAD_FILE"])
                return time.perf_counter_ns()
            except PermissionError:
                time.sleep(0.002)
        return time.perf_counter_ns()

    t0 = time.time()
    rng = random.Random(1234)
    try:
        fight_t = None
        while p.poll() is None and fight_t is None:
            if time.time() - t0 > 150:
                sys.exit("no fight after 150 s (see %s)" % os.path.join(out, "game.log"))
            try:
                with open(env["T5_DF_STATUS_FILE"]) as f:
                    if json.load(f).get("state") == "fight":
                        fight_t = time.time()
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        time.sleep(a.settle)
        dump_presses = set(range(2, a.presses, max(1, a.presses // 6))) if a.frames else set()
        w0, st0, pc0 = time.time(), busy_cpus(), proc_cpu(p.pid)
        for i in range(a.presses):
            if p.poll() is not None:
                break
            time.sleep(a.interval * 0.5 + rng.random() * a.interval * 0.5)
            if i in dump_presses:
                open(gate, "w").close()
                time.sleep(0.05)
            meta["presses"].append(setpad("SQUARE"))
            time.sleep(a.hold)
            setpad("")
            if i in dump_presses:
                time.sleep(0.25)
                os.remove(gate)
        w1, st1, pc1 = time.time(), busy_cpus(), proc_cpu(p.pid)
        busy = ((st1[1] - st0[1]) - (st1[0] - st0[0])) / max(1e-6, w1 - w0)
        meta["load"] = {"busy_cpus_all": round(busy, 2), "game_cpus": round((pc1 - pc0) / max(1e-6, w1 - w0), 2),
                        "other_cpus": round(busy - (pc1 - pc0) / max(1e-6, w1 - w0), 2)}
        print("load during the presses: %(busy_cpus_all).1f processors busy, the game %(game_cpus).1f, others %(other_cpus).1f" % meta["load"])
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
            p.wait()
        log.close()
        with open(os.path.join(out, "presses.json"), "w") as f:
            json.dump(meta, f)
    if a.discover:
        discover(out)
        return
    if a.frames:
        try:
            from PIL import Image
            d = os.path.join(out, "frames")
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".ppm"):
                    Image.open(os.path.join(d, fn)).save(os.path.join(d, fn[:-4] + ".png"))
                    os.remove(os.path.join(d, fn))
        except ImportError:
            pass
    analyze(out)


KMOVE_DEFAULT = KMOVE

if __name__ == "__main__":
    main()
