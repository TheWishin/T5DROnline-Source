#!/usr/bin/env python3
"""Tap latch test (ps3recomp patch 0025): a short tap between two reads of the
pad must reach the game exactly once -- held in one read, released in the next.

    python tools/tap_latch_test.py --exe build/cmake/t5dr.exe --out build/taptest/off1
    python tools/tap_latch_test.py --exe ... --out ... --pair                  # netplay host + joiner
    python tools/tap_latch_test.py --exe ... --out ... --pair --rollback       # the rollback loop
    python tools/tap_latch_test.py --exe ... --out ... --env PAD_TAP_LATCH=0   # reference: taps get lost
    python tools/tap_latch_test.py --out <earlier run> [--pair] --analyze      # analysis only
    python tools/tap_latch_test.py --exe ... --out ... --hid dualsense,bt-ext   # through a DualSense's reports

Boots straight into a fight (T5_FIGHT), waits until it has settled (--after,
12 s), then writes taps of 2-5 ms (random length and phase against the
frame), 50-90 ms apart, over SQUARE TRIANGLE CROSS CIRCLE DOWN into
PS3_PAD_FILE (port 1). Windows open minimized; physical pads and the keyboard
are ignored.

  offline: every packet the title reads through cellPadGetData, with its time,
           comes from PS3_PAD_READ_LOG. Each tap must show up as exactly one
           press of its button in the reads that follow it, held for exactly
           one read unless a second read fell inside the tap itself. Taps with
           no read inside them ("between two reads") are the ones a read-time
           sample alone loses. A tap while the game is not reading at all
           (reads > 50 ms apart: loading) is listed but not counted -- several
           taps then share one read.
  --pair:  host and joiner on 127.0.0.1, each tapping its own player. The
           same check on netplay's local sample (cellPad_sample_local, "L"
           lines of PS3_PAD_READ_LOG); every press it delivered must be in a
           lockstep frame (frames.log), one frame long; both frame logs must
           agree and the sync checks must say 0 mismatching frames.
  --rollback: rollback loop at input delay 0 (frames re-simulate); the local
           checks as above, sync from the rollback hash exchange.

  --hid MODEL,MODE: the taps come as input reports of a DualShock 4 / DualSense
           (ps3recomp patch 0042: PS3_PAD_HID_FAKE feeds the runtime's own HID
           reader from a file; MODEL ds4|dualsense|edge, MODE usb|bt-simple|
           bt-ext, or bt-steam: simple reports, half way through the extended
           ones, as when Steam starts during the game; see
           tools/ps_hid_reports.py), on port 1 through the "ps"
           layout like a real pad -- XInput, DirectInput and the keyboard off.
           Every second tap is a press and its release in one write: two
           reports between two samples, which only the reader's tap memory can
           deliver (a sub-millisecond tap).

Also prints fps in the fight and the pad sampler's rate and CPU ([pad-tap]).
Exit code 0 = every tap delivered exactly once (and in sync with --pair).
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time

# Both games of a local pair talk over 127.0.0.1: bind there, not on every interface (no Windows Firewall
# prompt for each build folder's t5dr.exe; docs/NETPLAY.md "Bind address"). An explicit T5_NET_BIND wins.
os.environ.setdefault("T5_NET_BIND", "127.0.0.1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUTTONS = {"SQUARE": 0x8000, "TRIANGLE": 0x1000, "CROSS": 0x4000, "CIRCLE": 0x2000, "DOWN": 0x0040}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ps_hid_reports as phr  # noqa: E402
HID_PIDS = {"ds4": "09CC", "dualsense": "0CE6", "edge": "0DF2"}


class HidWriter:
    """Writes the taps as input reports of a PlayStation pad into the PS3_PAD_HID_FAKE file."""

    def __init__(self, model, mode, switch_at=None):
        """mode bt-steam: Bluetooth simple reports, then from report `switch_at` on the extended ones -- the
        pad switched over by Steam while the game runs."""
        self.model, self.mode, self.n, self.switch_at = model, mode, 0, switch_at

    def report(self, name):
        self.n += 1
        s = phr.PadState(buttons=() if name in (None, "DOWN") else (name.lower(),),
                         hat=4 if name == "DOWN" else None)
        mode = self.mode
        if mode == "bt-steam":
            mode = "bt-ext" if self.switch_at is not None and self.n >= self.switch_at else "bt-simple"
        return phr.padded(self.model, mode, phr.report(self.model, mode, s, counter=self.n)).hex() + "\n"

    def write(self, path, name, kind, new=False):
        """Append the reports (the file is the pad's report queue, PS3_PAD_HID_FAKE); new: start the file.
        kind: press, release, or tap (press and release, two reports in one write)."""
        text = (self.report(name) if kind == "press" else self.report(None) if kind == "release"
                else self.report(name) + self.report(None))
        with open(path, "w" if new else "a") as f:
            f.write(text)


FPS_RE = re.compile(r"\[fps\] ([0-9.]+) \(frames (\d+)\.\.(\d+)")


def now_ns():
    return time.perf_counter_ns()


def wait_until(t_ns):
    """Sleep until perf_counter_ns() >= t_ns; the last 2 ms busy-waiting."""
    while True:
        left = t_ns - now_ns()
        if left <= 0:
            return
        if left > 2_500_000:
            time.sleep((left - 2_000_000) / 1e9)


def write_file(path, text):
    # In place (truncate + write): a reader that opens the file in between sees
    # it empty = nothing held, which is the state before a press or after a
    # release anyway. (os.replace would race the game's 1 ms reads.)
    with open(path, "w") as f:
        f.write(text)


def status(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def schedule(n, seed, t0_ns):
    """n taps: (start_ns, length_ns, button), 50-90 ms apart."""
    rnd = random.Random(seed)
    names = list(BUTTONS)
    out, t = [], t0_ns + rnd.randint(0, 40) * 1_000_000
    for i in range(n):
        length = rnd.randint(2000, 5000) * 1000          # 2-5 ms
        out.append((t, length, names[i % len(names)]))
        t += length + rnd.randint(50, 90) * 1_000_000
    return out


def run_taps(plans, hid=None):
    """plans: [(pad_path, taps)] -> {pad_path: [(button, t0, t1, t2, t3)]}: press
    write begun / done, release write begun / done (perf_counter_ns). One thread
    plays every instance's taps in time order, so each tap is timed exactly.
    hid: a HidWriter -- reports instead of button names; every second tap is
    pressed and released in one write (t2 = t3 = t1)."""
    ev = []
    for path, taps in plans:
        for i, (t, length, b) in enumerate(taps):
            instant = hid is not None and i % 2 == 1
            ev.append((t, 0, path, b, instant))
            if not instant:
                ev.append((t + length, 1, path, b, False))
    ev.sort()
    done = {path: [] for path, _ in plans}
    press = {}
    for t, kind, path, b, instant in ev:
        wait_until(t)
        if kind == 0:
            a = now_ns()
            if hid and instant:
                hid.write(path, b, "tap")
                e = now_ns()
                done[path].append((b, a, e, e, e))
                continue
            if hid:
                hid.write(path, b, "press")
            else:
                write_file(path, f"{b} T={a}")
            press[path] = (a, now_ns())
        else:
            a = now_ns()
            if hid:
                hid.write(path, b, "release")
            else:
                write_file(path, "")
            done[path].append((b,) + press[path] + (a, now_ns()))
    return done


def runs_of(seq, bit):
    """seq: [(t, mask)] -> [(t_first, length)] for each press of `bit`."""
    out, start, n = [], None, 0
    for r in seq:
        t, m = r[0], r[1]
        if m & bit:
            if not n:
                start = t
            n += 1
        elif n:
            out.append((start, n))
            n = 0
    if n:
        out.append((start, n))
    return out


def file_presses(log):
    """Taps the pad layer saw in the file (its 'file pad' lines)."""
    seen, prev = {b: 0 for b in BUTTONS}, 0
    for m in re.finditer(r"\[cellPad\] file pad: buttons 0x([0-9A-F]{4})", log):
        v = int(m.group(1), 16)
        for name, bit in BUTTONS.items():
            if v & bit and not prev & bit:
                seen[name] += 1
        prev = v
    return seen


def stats_lines(log):
    fps = [float(m.group(1)) for m in FPS_RE.finditer(log)]
    out = []
    if fps:
        tail = fps[-12:]
        out.append(f"fps (last {len(tail)} x 5 s): min {min(tail):.1f} median {sorted(tail)[len(tail) // 2]:.1f}"
                   f"  all: {' '.join(f'{x:.1f}' for x in fps)}")
    out += [l for l in log.splitlines() if l.startswith("[pad-tap]")][-2:]
    out += [l for l in log.splitlines() if l.startswith("[pad-lat] port 1:")][-1:]
    return out


def load_reads(path, who):
    """PS3_PAD_READ_LOG lines of port 1 from reader `who` (G title, L netplay local)."""
    out = []
    if os.path.exists(path):
        for line in open(path, errors="replace"):
            f = line.split()
            if len(f) == 5 and f[1] == "1" and f[4] == who:
                out.append((int(f[0]), int(f[2], 16), int(f[3], 16)))
    return out


def analyze_reads(tag, what, taps, reads, log, stall_ms=50):
    """taps: [(button, t0, t1, t2, t3)]; reads: [(t, mask, tapped)] port 1, in time order.
    A tap whose surrounding reads are more than `stall_ms` apart came while the
    game was not reading (loading, a stall): several taps then share one read,
    so it is reported but not held to "exactly once"."""
    import bisect
    ok = True
    lens = [(t2 - t1) / 1e6 for (_, _, t1, t2, _) in taps]
    between = stalled = 0
    per = {b: {"written": 0, "got": 0, "once": 0, "between": 0, "between_got": 0} for b in BUTTONS}
    problems = []
    times = [r[0] for r in reads]
    for i, (b, t0, t1, t2, t3) in enumerate(taps):
        bit = BUTTONS[b]
        lo_in, hi_in = bisect.bisect_left(times, t0), bisect.bisect_right(times, t3)
        before = times[lo_in - 1] if lo_in > 0 else None
        after = times[hi_in] if hi_in < len(times) else None
        if before is None or after is None or after - before > stall_ms * 1_000_000:
            stalled += 1
            continue
        p = per[b]
        p["written"] += 1
        inside = hi_in - lo_in                  # reads while the file showed the tap
        is_between = inside == 0
        nxt = taps[i + 1][1] if i + 1 < len(taps) else t3 + 60_000_000
        lo, hi = lo_in, bisect.bisect_left(times, nxt)
        r = runs_of(reads[lo:hi], bit)
        if is_between:
            between += 1
            p["between"] += 1
        if len(r) == 1:
            p["got"] += 1
            if is_between:
                p["between_got"] += 1
            if r[0][1] == 1 or r[0][1] <= inside:
                p["once"] += 1
            else:
                problems.append(f"{b} tap {i}: held {r[0][1]} reads ({inside} read(s) inside the tap)")
        else:
            near = reads[max(0, lo - 2):hi + 1]
            problems.append(f"{b} tap {i} ({(t1 - t0) / 1e6:.2f}+{(t2 - t1) / 1e6:.2f} ms): {len(r)} presses in the reads after it;"
                            f" reads around (ms from the tap: buttons/tap): "
                            + " ".join(f"{(x[0] - t1) / 1e6:+.1f}:{x[1]:04X}/{x[2]:04X}" for x in near))
    print(f"== {tag}: {len(taps)} taps written, {min(lens):.1f}-{max(lens):.1f} ms long (avg {sum(lens) / len(lens):.1f});"
          f" {len(reads)} {what} of port 1; {between} taps fell between two of them"
          + (f"; {stalled} came while the game was not reading (reads > {stall_ms} ms apart), not counted" if stalled else ""))
    seen = file_presses(log)
    for b, p in per.items():
        good = p["got"] == p["written"] and p["once"] == p["written"]
        ok &= good
        print(f"   {b:8s} written {p['written']:3d}  pad layer saw {seen[b]:3d}  reads got {p['got']:3d} press(es),"
              f" {p['once']} for exactly one read; between reads {p['between']:3d}, of those delivered {p['between_got']:3d}"
              + ("" if good else "   <-- MISMATCH"))
    for s in problems[:10]:
        print("   ! " + s)
    print(f"   {sum(1 for r in reads if r[2])} {what} carried a tap the latch held (PS3_PAD_READ_LOG 'tap' column)")
    if stalled * 2 > len(taps):
        print("   ! most taps came during a stall: start later (--after)")
        ok = False
    return ok


def launch_and_tap(a, out, base, roles, vfs):
    """Start the instance(s), wait for the fight, play the taps; -> (procs, done)."""
    procs = []
    for i, role in enumerate(roles):
        d = os.path.join(out, role)
        os.makedirs(d, exist_ok=True)
        env = dict(base)
        pad = os.path.join(d, "pad.txt")
        write_file(pad, "")
        if a.hid:
            # port 1 = the fake pad's reports; no other device is read
            model, mode = a.hid
            pad = os.path.join(d, "hid.txt")
            HidWriter(model, mode).write(pad, None, "release", new=True)
            ini = os.path.join(d, "controls.ini")
            write_file(ini, "[general]\nxinput = 0\ndinput = 0\nhid = 1\nkeyboard = 0\n"
                            f"[port1]\ndevice = dinput:054C:{HID_PIDS[model]}\n")
            env["PS3_CONTROLS"] = ini
            env["PS3_PAD_HID_FAKE"] = f"{model},{'usb' if mode == 'usb' else 'bt'},{pad}"
            env.pop("PS3_PAD_FILE", None)
        else:
            env["PS3_PAD_FILE"] = pad
        env["PS3_PAD_READ_LOG"] = os.path.join(d, "reads.log")
        env["T5_DF_STATUS_FILE"] = os.path.join(d, "status.json")
        for f in ("status.json", "reads.log", "frames.log"):
            if os.path.exists(os.path.join(d, f)):
                os.remove(os.path.join(d, f))
        if a.pair and a.rollback:
            env.update({"T5_RB_MODE": "net", "PS3_VM_WRITE_WATCH": "1", "T5_RB_NET_START": "0", "T5_NET_DELAY": "0"})
        if a.pair:
            env.update({"T5_NET_MODE": role, "T5_NET_START": "external", "T5_NET_LOCALPAD": "1",
                        "T5_NET_LOG": os.path.join(d, "frames.log"), "T5_NET_TIMEOUT": "60"})
            if role == "host":
                env["T5_NET_PORT"] = str(a.port)
            else:
                env["T5_NET_PORT"] = "0"
                env["T5_NET_PEER"] = f"127.0.0.1:{a.port}"
        log = open(os.path.join(d, "game.log"), "w")
        p = subprocess.Popen([os.path.abspath(a.exe), vfs + "/PS3_GAME/USRDIR/EBOOT.elf"],
                             cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
        procs.append({"p": p, "dir": d, "pad": pad, "log": log, "status": env["T5_DF_STATUS_FILE"]})
        print(f"started {role} pid {p.pid} in {d}", flush=True)
        if a.pair and i == 0:
            time.sleep(1.0)

    try:
        t_end = time.time() + a.timeout
        while time.time() < t_end:
            if any(x["p"].poll() is not None for x in procs):
                raise SystemExit("an instance exited before the fight")
            if all(status(x["status"]).get("state") == "fight" for x in procs):
                break
            time.sleep(0.25)
        else:
            raise SystemExit("no fight within the timeout")
        print(f"fight running; first tap in {a.after:.0f} s", flush=True)
        time.sleep(a.after)
        t0 = now_ns() + 50_000_000
        plans = [(x["pad"], schedule(a.taps, a.seed * 100 + k, t0)) for k, x in enumerate(procs)]
        done = run_taps(plans, HidWriter(*a.hid, switch_at=a.taps + 1) if a.hid else None)
        with open(os.path.join(out, "taps.json"), "w") as f:
            json.dump({x["pad"]: done[x["pad"]] for x in procs}, f)
        time.sleep(3.0 + a.hold)      # the frame log is flushed every 60 frames
    finally:
        for x in procs:
            if x["p"].poll() is None:
                x["p"].kill()
        for x in procs:
            try:
                x["p"].wait(10)
            except Exception:
                pass
            x["log"].close()
    return procs, done


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--pair", action="store_true", help="netplay host + joiner on 127.0.0.1")
    ap.add_argument("--rollback", action="store_true",
                    help="with --pair: the rollback loop (T5_RB_MODE=net, input delay 0 so remote input is predicted and"
                         " frames are re-simulated); sync from the rollback hash exchange ('desync mismatches')")
    ap.add_argument("--taps", type=int, default=60, help="taps per instance")
    ap.add_argument("--fight", default="lil,ask,20,3", help="T5_FIGHT")
    ap.add_argument("--after", type=float, default=12.0, help="seconds into the fight before the first tap")
    ap.add_argument("--hold", type=float, default=0.0, help="keep running this long after the taps (fps check)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--port", type=int, default=7400)
    ap.add_argument("--timeout", type=float, default=150, help="seconds to wait for the fight")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for every instance")
    ap.add_argument("--analyze", action="store_true", help="only analyze an earlier run in --out")
    ap.add_argument("--hid", metavar="MODEL,MODE",
                    help="taps as reports of a PlayStation pad through the runtime's HID reader (patch 0042):"
                         " MODEL ds4|dualsense|edge, MODE usb|bt-simple|bt-ext|bt-steam (simple reports, then"
                         " half way the extended ones, as when Steam starts while the game runs)")
    a = ap.parse_args()
    if a.hid:
        model, _, mode = a.hid.partition(",")
        if model not in HID_PIDS or mode not in ("usb", "bt-simple", "bt-ext", "bt-steam"):
            ap.error("--hid MODEL,MODE: MODEL ds4|dualsense|edge, MODE usb|bt-simple|bt-ext|bt-steam")
        if a.pair:
            ap.error("--hid is for one instance")
        a.hid = (model, mode)

    vfs = os.path.abspath(a.vfs).replace("\\", "/")
    out = os.path.abspath(a.out)
    base = dict(os.environ)
    base.update({
        "PS3_VFS_ROOT": vfs, "PS3_HDD0_ROOT": vfs + "/dev_hdd0", "PS3_GCM_TICKER_PUMP": "1",
        "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1", "PAD_NO_KEYBOARD": "1",
        "PS3_PAD_LATENCY": "1", "PS3_FIXED_TIME": "1760000000", "T5_FIGHT": a.fight,
    })
    for kv in a.env:
        k, v = kv.split("=", 1)
        base[k] = v
    roles = ["host", "join"] if a.pair else ["offline"]
    if a.analyze:
        with open(os.path.join(out, "taps.json")) as f:
            done = json.load(f)
        procs = [{"dir": os.path.join(out, r), "pad": os.path.join(out, r, "hid.txt" if a.hid else "pad.txt")}
                 for r in roles]
        done = {x["pad"]: next(v for k, v in done.items() if os.path.normcase(k) == os.path.normcase(x["pad"]))
                for x in procs}
    else:
        procs, done = launch_and_tap(a, out, base, roles, vfs)

    ok = True
    if not a.pair:
        x = procs[0]
        log = open(os.path.join(x["dir"], "game.log"), errors="replace").read()
        reads = load_reads(os.path.join(x["dir"], "reads.log"), "G")
        ok = analyze_reads("offline, cellPadGetData", "title reads", done[x["pad"]], reads, log)
        for s in stats_lines(log):
            print("   " + s)
    else:
        sync = []
        frames_all = []
        for k, x in enumerate(procs):
            log = open(os.path.join(x["dir"], "game.log"), errors="replace").read()
            frames = {}
            fl = os.path.join(x["dir"], "frames.log")
            if os.path.exists(fl):
                for line in open(fl, errors="replace"):
                    f = line.split()
                    if len(f) >= 5 and f[1] == "I":
                        frames[int(f[0])] = (f[2], f[3], f[4])
            frames_all.append(frames)
            # host = player 1 = first input column, joiner = player 2 = second
            seq = [(fr, int(frames[fr][k][:4], 16)) for fr in sorted(frames)]
            taps = done[x["pad"]]
            lens = [(t2 - t1) / 1e6 for (_, _, t1, t2, _) in taps]
            print(f"== {roles[k]} (player {k + 1}): {len(taps)} taps written, {min(lens):.1f}-{max(lens):.1f} ms long;"
                  f" local input of {len(seq)} lockstep frames")
            lreads = load_reads(os.path.join(x["dir"], "reads.log"), "L")
            ok &= analyze_reads(f"{roles[k]}, cellPad_sample_local", "netplay local reads", taps, lreads, log)
            # every press a local read delivered must be in a lockstep frame's input
            print("   lockstep frames (frames.log) vs the local reads:")
            for b, bit in BUTTONS.items():
                r = runs_of(seq, bit)
                rl = runs_of(lreads, bit)
                once = sum(1 for (_, l) in r if l == 1)
                good = len(r) == len(rl)
                ok &= good
                print(f"   {b:8s} presses in local reads {len(rl):3d}  in lockstep frames {len(r):3d}, {once} of them one frame long"
                      + ("" if good else "   <-- MISMATCH"))
            if a.rollback:
                # rollback: the frame log holds the inputs used live (the peer's possibly predicted);
                # sync comes from the exchanged final hashes
                s = [l.strip() for l in log.splitlines() if "rbnet:" in l and "desync mismatches" in l]
                if s:
                    print("   " + s[-1][:400])
                sync.append(s[-1] if s else "")
            else:
                s = [l.strip() for l in log.splitlines() if "sync check through frame" in l or "DESYNC" in l]
                if s:
                    print("   " + s[-1])
                sync.append(s[-1] if s else "")
            for s in stats_lines(log):
                print("   " + s)
        h, j = frames_all
        common = sorted(set(h) & set(j))
        if a.rollback:
            # the peer's column is what was used live, maybe a prediction: shown, not judged
            diff = [f for f in common if h[f][0] != j[f][0] or h[f][1] != j[f][1]]
            ok &= all(re.search(r"desync mismatches 0\b", s) for s in sync)
        else:
            diff = [f for f in common if h[f] != j[f]]
            ok &= all(" 0 mismatching" in s for s in sync)
        print(f"== frame logs host vs joiner: {len(common)} common frames, {len(diff)} differ"
              + (" (inputs; live rollback frames may show a predicted input)" if a.rollback else " (inputs or state hash)")
              + (f", first {diff[:5]}" if diff else ""))
        if not a.rollback:
            ok &= not diff
        ok &= len(common) > 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
