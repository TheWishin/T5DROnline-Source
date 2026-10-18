#!/usr/bin/env python3
"""One game, the same scripted match twice: does anything but the inputs decide the fight?

    python tools/rb_equiv_test.py --exe build/cmake/t5dr.exe --out build/eq/r1 --fight kaz,hei,29,1 \
        [--force 9:4] [--test-env NAME=VALUE ...] [--full] [--dump]

Both runs are the direct-fight match in netplay's local mode (T5_NET_MODE=local: no peer, both
players scripted -- the --moves mash of tools/fight_flow_test.py, motion inputs included -- and the
rollback loop running as online), with the same seed and fixed clock. The reference run has nothing
else; the test run adds --force (T5_RB_NET_FORCE=every:depth, a rollback of `depth` frames every
`every` fight frames, re-simulated with the same inputs) and/or --test-env (anything a second PC may
differ in: T5_TEST_HITCH, PS3_CPUS, PS3_TEST_FS_DELAY, RSX_TEST_DISPLAY_HZ, ...). Each run's
frames.log has the final gameplay hash of every frame ("f F <hash>"); a deterministic game gives the
same hash on every frame in both runs. Prints the first differing frame and how many differ.

--full hashes without the cosmetic skip list (T5_RB_HASH_FULL=1, both runs): camera and secondary
motion count too, so a run shows when they part. --dump writes the final gameplay bytes of the
frames around the first difference (a third and fourth run, T5_RB_DUMP_AT) and diffs them per word
(tools/rb_desync_diff.py). --cpus N runs a game on N logical processors (affinity + PS3_CPUS).

Games run minimized, muted, at below-normal priority, host devices ignored; each is killed at the end.
Exit code 0 = no differing frame.
"""
import argparse
import ctypes
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fight_flow_test as fft          # noqa: E402  (mash_script, suspend_process, cpu_mask)


def run(a, name, extra, dump=None):
    d = os.path.abspath(os.path.join(a.out, name))
    os.makedirs(d, exist_ok=True)
    for fn in os.listdir(d):
        if fn.startswith(("rb_frame_f", "frames", "result")):
            os.remove(os.path.join(d, fn))
    vfs = os.path.abspath(a.vfs)
    env = dict(os.environ)
    env.update({
        "PS3_VFS_ROOT": vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
        "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
        "PS3_AUDIO_MUTE": "1", "PAD_NO_KEYBOARD": "1", "T5_NET_LOCALPAD": "0",
        "T5_NET_MODE": "local", "T5_NET_START": "external", "T5_FIGHT": a.fight, "T5_NET_SEED": str(a.seed),
        "PS3_FIXED_TIME": str(a.clock), "T5_NET_LOG": os.path.join(d, "frames.log"),
        "T5_NET_RESULT_FILE": os.path.join(d, "result.json"), "T5_NET_SCRIPT_FIGHT": "1",
        "T5_NET_SCRIPT": fft.mash_script(os.path.join(a.out, "p1.txt"), 101, gap=a.gap, moves=not a.no_moves),
        "T5_NET_SCRIPT2": fft.mash_script(os.path.join(a.out, "p2.txt"), 102, gap=a.gap, moves=not a.no_moves),
    })
    if a.full:
        env["T5_RB_HASH_FULL"] = "1"
    if dump:
        env["T5_RB_DUMP_AT"] = f"{dump[0]}:{dump[1]}"
    for kv in a.env + extra:
        k, v = kv.split("=", 1)
        env[k] = v
    cpus = a.cpus if "TEST" in name.upper() else ""
    mask = fft.cpu_mask(cpus)
    flags = 0x00004000 | (0x00000004 if mask else 0)
    if mask:
        env["PS3_CPUS"] = str(bin(mask).count("1"))
    log = open(os.path.join(d, "game.log"), "w")
    t0 = time.time()
    p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")], cwd=d, env=env,
                         stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    if mask:
        fft._k32.SetProcessAffinityMask(ctypes.c_void_p(int(p._handle)), ctypes.c_size_t(mask))
        fft.suspend_process(p.pid, False)
    print(f"[{name}] pid {p.pid}{' ' + ' '.join(extra) if extra else ''}{f' cpus {cpus}' if mask else ''}", flush=True)
    res = os.path.join(d, "result.json")
    try:
        while time.time() - t0 < a.seconds and p.poll() is None:
            if os.path.exists(res):
                time.sleep(3.0)          # the frames after the deciding one are in the log too
                break
            time.sleep(1.0)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(10)
    hashes = {}
    try:
        with open(os.path.join(d, "frames.log"), encoding="utf-8", errors="replace") as f:
            for ln in f:
                m = re.match(r"(\d+) F ([0-9a-f]{16})", ln)
                if m:
                    hashes[int(m.group(1))] = m.group(2)
    except OSError:
        pass
    forced = 0
    with open(os.path.join(d, "game.log"), encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = re.search(r"forced rollbacks (\d+)", ln)
            if m:
                forced = max(forced, int(m.group(1)))
    result = open(res).read().strip() if os.path.exists(res) else None
    print(f"[{name}] {len(hashes)} final hashes, {forced} forced rollbacks (last report), {time.time() - t0:.0f} s, result {result}",
          flush=True)
    return hashes, d


def compare(h1, h2):
    common = sorted(set(h1) & set(h2))
    diff = [f for f in common if h1[f] != h2[f]]
    return common, diff


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(os.path.dirname(HERE), "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(os.path.dirname(HERE), "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--fight", default="kaz,hei,29,1", help="T5_FIGHT line (p1,p2,stage,rounds)")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--clock", type=int, default=1792300000, help="PS3_FIXED_TIME of both runs")
    ap.add_argument("--gap", type=int, default=12, help="mash: at most this many frames between inputs")
    ap.add_argument("--no-moves", action="store_true", help="plain mash, no motion inputs")
    ap.add_argument("--force", default="", help="test run: T5_RB_NET_FORCE=every:depth")
    ap.add_argument("--test-env", action="append", default=[], help="NAME=VALUE for the test run only")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for both runs")
    ap.add_argument("--cpus", default="", help="test run: N logical processors or 0xMASK")
    ap.add_argument("--full", action="store_true", help="hash without the cosmetic skip list (T5_RB_HASH_FULL=1)")
    ap.add_argument("--dump", action="store_true", help="run both again with dumps around the first difference")
    ap.add_argument("--ref", default="", help="reuse this earlier reference run directory (its frames.log)")
    ap.add_argument("--seconds", type=float, default=400)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    test_extra = list(a.test_env) + ([f"T5_RB_NET_FORCE={a.force}"] if a.force else [])
    if a.ref:
        h_ref = {}
        with open(os.path.join(a.ref, "frames.log"), encoding="utf-8", errors="replace") as f:
            for ln in f:
                m = re.match(r"(\d+) F ([0-9a-f]{16})", ln)
                if m:
                    h_ref[int(m.group(1))] = m.group(2)
        print(f"[ref] {len(h_ref)} final hashes from {a.ref}")
    else:
        h_ref, _ = run(a, "ref", [])
    h_test, _ = run(a, "test", test_extra)
    common, diff = compare(h_ref, h_test)
    ok = len(common) > 300 and not diff
    first = diff[0] if diff else None
    runs = []
    if diff:
        r, cur = [], [diff[0], diff[0]]
        for f in diff[1:]:
            if f == cur[1] + 1:
                cur[1] = f
            else:
                r.append(tuple(cur))
                cur = [f, f]
        r.append(tuple(cur))
        runs = r
    print(f"compared {len(common)} frames: {len(diff)} differ" + (f", first {first}; runs {runs[:12]}" if diff else ""))
    if diff and a.dump:
        rng = (max(0, first - 3), first + 12)
        _, d1 = run(a, "ref_dump", [], dump=rng)
        _, d2 = run(a, "test_dump", test_extra, dump=rng)
        subprocess.call([sys.executable, os.path.join(HERE, "rb_desync_diff.py"), d1, d2])
    print("EQUAL" if ok else ("DIFFERENT" if diff else "TOO FEW FRAMES"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
