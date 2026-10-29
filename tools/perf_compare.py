#!/usr/bin/env python3
"""Repeatable speed measurements of one game build, and a before/after table of two (1.1.7's gate).

    python tools/perf_compare.py run --game C:/T5DROnline/build/int115/x-final --out DIR [--parts ...]
        [--runs 2] [--lock C:/T5DROnline/build/int115/HEAVY.lock --lock-name NAME]
    python tools/perf_compare.py table DIR/results.json
    python tools/perf_compare.py compare BEFORE/results.json AFTER/results.json

--game is a built game's output folder (build/cmake/t5dr.exe [+ t5dr_game.dll], game/vfs). Every
measurement runs the real game; nothing is faked. Parts (--parts, comma list, default all):

  offline   direct fights (tools/fight_bench.py --polite: muted, below-normal priority, P1 attacking),
            Lili vs Asuka on stages 17 (Western Gate), 19 (Meteor Shower), 4 (City at Sunset, t5s05) and
            13 (Poolside, Tekken 5), at 720p Native with the launcher's defaults (stage blur off, shadows and
            effects on) and with the "Lowest" preset (Internal resolution Lowest, shadows and effects off),
            --runs times each, on all processors ("all") and on 2 cores / 4 threads by affinity ("2c":
            --two-core-mask, the game's own 2-core mode turns on by itself: PS3_TWO_CORE auto on <= 2
            physical cores) and, with --slow-core N, the same 2 cores with tools/slow_core.py taking N % of
            them ("2c-slow": an older 2-core CPU such as GitHub #12's i3-3240); --cpu-configs names other
            sets (all=,2c=0xF000,4c=0x5500,2c2t=0x5000: 4 and 2 cores without SMT, low-end PCs). Per run: fps, frame p99,
            frames over 20.9 ms (the [slow-frames] threshold), medians of the frame log's game part,
            translation and GPU wait (the [slow-frames] medians), the game thread's CPU per frame, GPU ms
            per frame from the [gpu-pass] lines (RSX_GPU_PASSES=1) and the D3D12 timestamps, every
            [slow-frames] line, and the CPU per frame of every thread.
  rollback  rollback pairs through the UDP proxy (tools/rollback_net_test.py --mode1/2 default --latlog,
            one whole match, Asuka vs Lili on stage 20, scripted attacks on both sides) at RTT 60/120/180/260
            ms with jitter and loss (60 +-5 1 %, 120 +-8 2 %, 180 +-10 3 %, 260 +-12 3 %; input delay by ping,
            the lobby's 3 above 150 ms and 4 above 250 ms), each side on 8 processors of its own: pictures
            shown twice or longer while fighting (display refreshes without a new frame, PS3_LATENCY_LOG),
            present-to-present p99, mismatching frames, fps, rollbacks and their cost, the display lock's
            lead (tick -> present: the screen part of input-to-screen, on top of the input delay).
  e2e       the e2e net suite with real games and a local lobby (tools/e2e/run.py): net_rollback (RTT 20-250, delays, loss, jitter, relay),
            net_relay_smooth on the direct path at the same four networks, and ranked_set (a ranked
            best-of-3 set). Per match: path, fps, rollbacks, stalls, mismatches, PASS/FAIL.

Each game run is one heavy step: with --lock the script takes the shared lock file before it and gives
it back after it (other agents' runs go in between: 35 s pass before it takes it again), looking every
30 s while someone else holds it. results.json keeps every number; `table` prints it, `compare` prints both builds side by side
with the change. The PC's other load is in every row ("load": processors busy besides the game) --
two builds are comparable when measured the same day under similar load; repeat a row when the load
differs a lot.
"""
import argparse
import csv
import json
import os
import re
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
STAGES = [(17, "Western Gate"), (19, "Meteor Shower"), (4, "City at Sunset"), (13, "Poolside")]
PRESETS = {
    "default": ["PS3_INTERNAL_RES=native", "PS3_STAGE_BLUR=0", "PS3_SHADOWS=1", "PS3_EFFECTS=1"],
    "lowest": ["PS3_INTERNAL_RES=lowest", "PS3_STAGE_BLUR=0", "PS3_SHADOWS=0", "PS3_EFFECTS=0"],
}
NETS = [(60, 5, 1), (120, 8, 2), (180, 10, 3), (260, 12, 3)]


def delay_for(rtt):
    """The lobby's input-delay floor (docs/ROLLBACK.md 34): 3 above 150 ms, 4 above 250; else by ping."""
    return 4 if rtt > 250 else 3 if rtt > 150 else 0


# ------------------------------------------------------------------ the shared lock (one heavy step at a time)
class Lock:
    def __init__(self, path, name):
        self.path, self.name = path, name
        self.given = 0.0

    GAP = 35.0      # after giving the lock back: others poll every 30 s, so wait that long before the next take

    def __enter__(self):
        return self

    def take(self, what):
        if not self.path:
            return
        if time.time() - self.given < self.GAP:
            time.sleep(self.GAP - (time.time() - self.given))
        while True:
            try:
                cur = open(self.path, encoding="utf-8", errors="replace").read().strip()
            except OSError:
                cur = ""
            if not cur or cur.split()[0] == self.name:
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write(f"{self.name} {time.strftime('%H:%M')} {what}\n")
                return
            print(f"  lock held: {cur!r}; waiting", flush=True)
            time.sleep(30)

    def give(self):
        if not self.path:
            return
        try:
            cur = open(self.path, encoding="utf-8", errors="replace").read().strip()
            if cur.split() and cur.split()[0] == self.name:
                os.remove(self.path)
                self.given = time.time()
        except OSError:
            pass

    def __exit__(self, *a):
        self.give()


def busy_processors(secs=3.0):
    """Processors busy right now (all programs), from GetSystemTimes over secs."""
    if os.name != "nt":
        return float("nan")
    import ctypes
    from ctypes import wintypes as W
    k = ctypes.windll.kernel32

    def t():
        i, kk, u = W.FILETIME(), W.FILETIME(), W.FILETIME()
        k.GetSystemTimes(ctypes.byref(i), ctypes.byref(kk), ctypes.byref(u))
        f = lambda x: (x.dwHighDateTime << 32 | x.dwLowDateTime) / 1e7  # noqa: E731
        return f(i), f(kk) + f(u)
    a, t0 = t(), time.time()
    time.sleep(secs)
    b = t()
    return ((b[1] - a[1]) - (b[0] - a[0])) / (time.time() - t0)


def med(xs):
    return statistics.median(xs) if xs else float("nan")


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


# ------------------------------------------------------------------ offline fights
RE_GPU_PASS = re.compile(r"\[gpu-pass\] (\d+) frames, ([0-9.]+) ms GPU per frame.*?binding (\d+) draws")


def offline_extra(d, js):
    """Numbers fight_bench does not print: the frame log's medians in the window, frames over 20.9 ms, the
    [gpu-pass] lines of the fight (those with more than 300 draws a frame: not menus or loading)."""
    out = {}
    try:
        with open(os.path.join(d, "frames.csv")) as f:
            f.readline()
            rows = list(csv.DictReader(f))
    except OSError:
        rows = []
    lo, hi = js.get("window_qpc", [0, 0])
    w = [r for r in rows if lo <= float(r["qpc"]) <= hi]

    def col(k):
        xs = []
        for r in w:
            try:
                xs.append(float(r[k]) / 1000.0)
            except (KeyError, TypeError, ValueError):
                pass
        return xs
    dts = [x for x in col("dt_us") if x > 0]
    out["over_20_9"] = sum(1 for x in dts if x > 20.85)
    out["over_20_9_pct"] = 100.0 * out["over_20_9"] / len(dts) if dts else float("nan")
    # the game part (release -> flip request) comes from the game thread log (fight_bench: game_thread.part_p50)
    out["game_med"] = (js.get("game_thread") or {}).get("part_p50", float("nan"))
    out["xlat_med"] = med(col("xlat_us"))
    out["gpuwait_med"] = med(col("flush_wait_us"))
    out["gpu_med"] = med([x for x in col("gpu_us") if x > 0])
    gp = []
    try:
        for ln in open(os.path.join(d, "game.log"), errors="replace"):
            m = RE_GPU_PASS.search(ln)
            if m and int(m.group(3)) > 300:
                gp.append(float(m.group(2)))
    except OSError:
        pass
    out["gpu_pass_ms"] = med(gp)
    out["gpu_pass_lines"] = len(gp)
    return out


def cache_env(a):
    """One shader cache for every game of the run (the player's is warmed after BUILD GAME): a run's own
    working directory would start every fight cold (PSO compiles in the measured window)."""
    return [f"RSX_SHADER_CACHE_DIR={os.path.join(a.out, 'shader_cache')}"]


def warm_up(a, lock, results):
    """One unmeasured fight per stage and preset (and the rollback pairs' pair on stage 20) before anything is
    measured, so the measured fights meet a warm shader cache."""
    exe = os.path.join(a.game, "build", "cmake", "t5dr.exe")
    vfs = os.path.join(a.game, "game", "vfs")
    fights = [(f"lil,ask,{s},3", p) for s, _ in STAGES for p in PRESETS] + [("26,33,20,2", "default")]
    for fight, preset in fights:
        key = f"warm/{fight}/{preset}"
        if key in results:
            continue
        d = os.path.join(a.out, "warm", fight.replace(",", "-") + "-" + preset)
        os.makedirs(d, exist_ok=True)
        cmd = [PY, os.path.join(ROOT, "tools", "fight_bench.py"), "--exe", exe, "--vfs", vfs, "--fight", fight,
               "--skip", "4", "--secs", "20", "--polite", "--out", d] + PRESETS[preset] + cache_env(a) + a.env
        print(f"[warm] {fight} {preset}", flush=True)
        lock.take(f"perf_compare shader warm-up {fight}")
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=400)
        finally:
            lock.give()
        results[key] = {"kind": "warm"}
        save(a, results)


def run_offline(a, lock, results):
    exe = os.path.join(a.game, "build", "cmake", "t5dr.exe")
    vfs = os.path.join(a.game, "game", "vfs")
    cfgs = [("all", "")] + [("2c", a.two_core_mask)]
    if a.cpu_configs:     # NAME=MASK,... instead (an empty mask = every processor)
        cfgs = [tuple(c.split("=", 1)) if "=" in c else (c, "") for c in a.cpu_configs.split(",") if c]
    if a.slow_core:
        cfgs.append(("2c-slow", a.two_core_mask))
    stages = [s for s in STAGES if not a.stages or str(s[0]) in a.stages.split(",")]
    for k in range(a.runs):
        for cpu, mask in cfgs:
            for stage, sname in stages:
                for preset in PRESETS:
                    key = f"offline/{cpu}/{stage}/{preset}/{k + 1}"
                    if key in results and not a.redo:
                        continue
                    d = os.path.join(a.out, "offline", f"{cpu}-s{stage}-{preset}-{k + 1}")
                    os.makedirs(d, exist_ok=True)
                    js = os.path.join(d, "bench.json")
                    cmd = [PY, os.path.join(ROOT, "tools", "fight_bench.py"), "--exe", exe, "--vfs", vfs,
                           "--fight", f"lil,ask,{stage},3", "--skip", str(a.skip), "--secs", str(a.secs),
                           "--polite", "--out", d, "--json", js]
                    if mask:
                        cmd += ["--cpus", mask]
                    cmd += PRESETS[preset] + ["RSX_GPU_PASSES=1"] + cache_env(a) + a.env
                    print(f"[offline] {key}: {sname}, {preset}, {cpu}", flush=True)
                    lock.take(f"perf_compare offline {key}")
                    slow = None
                    try:
                        load = busy_processors()
                        if cpu == "2c-slow":
                            slow = subprocess.Popen([PY, os.path.join(ROOT, "tools", "slow_core.py"), "--cpus", mask,
                                                     "--busy", str(a.slow_core), "--secs", str(a.secs + 200)],
                                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                    finally:
                        if slow is not None:
                            slow.kill()
                            slow.wait()
                        lock.give()
                    open(os.path.join(d, "bench.txt"), "w").write(r.stdout + r.stderr)
                    try:
                        res = json.load(open(js))
                    except (OSError, ValueError):
                        print(f"  failed: {(r.stdout + r.stderr)[-400:]}", flush=True)
                        results[key] = {"error": (r.stdout + r.stderr)[-400:]}
                        save(a, results)
                        continue
                    row = {"kind": "offline", "cpu": cpu, "stage": stage, "preset": preset, "run": k + 1,
                           "load_before": load, "fps": res.get("fps"), "p99": res.get("p99"),
                           "frames": res.get("frames"), "other_load": res.get("other_load"),
                           "game_cpu_procs": res.get("game_cpu"), "cpu_ms_per_frame": res.get("cpu_ms_per_frame"),
                           "switches_per_s": res.get("switches_per_s"),
                           "game_thread_cpu": (res.get("game_thread") or {}).get("cpu_p50"),
                           "game_thread_cpu_mean": (res.get("game_thread") or {}).get("cpu_mean"),
                           "game_part_p50": (res.get("game_thread") or {}).get("part_p50"),
                           "game_part_p99": (res.get("game_thread") or {}).get("part_p99"),
                           "slow_frames": res.get("slow_frames", []),
                           "threads": {n: v["ms_per_frame"] for n, v in (res.get("threads") or {}).items()
                                       if v["ms_per_frame"] >= 0.05}}
                    row.update(offline_extra(d, res))
                    results[key] = row
                    save(a, results)
                    print(f"  fps {row['fps']:.2f}, p99 {row['p99']:.1f} ms, over 20.9 ms {row['over_20_9']}, "
                          f"game {row['game_med']:.2f} / xlat {row['xlat_med']:.2f} / GPU wait {row['gpuwait_med']:.2f} ms, "
                          f"GPU {row['gpu_pass_ms']:.2f} ms, other load {row['other_load']:.1f}", flush=True)


# ------------------------------------------------------------------ rollback pairs
RE_LEAD = re.compile(r"display lock: lead ([0-9.]+) ms")


def run_rollback(a, lock, results):
    exe = os.path.join(a.game, "build", "cmake", "t5dr.exe")
    vfs = os.path.join(a.game, "game", "vfs").replace("\\", "/")
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import rollback_net_test as rnt
    for k in range(a.runs):
        for rtt, jit, loss in NETS:
            key = f"rollback/{rtt}/{k + 1}"
            if key in results and not a.redo:
                continue
            name = f"rb-{rtt}-{k + 1}"
            runs = os.path.join(a.out, "rollback")
            cmd = [PY, os.path.join(ROOT, "tools", "rollback_net_test.py"), "--out", name, "--runs", runs,
                   "--exe", exe, "--vfs", vfs, "--fight", "26,33,20,2", "--delay", "6", "--mode1", "default",
                   "--mode2", "default", "--matches", "1", "--seconds", "400", "--latlog", "--polite",
                   "--cpus1", a.rb_cpus1, "--cpus2", a.rb_cpus2, "--rtt", str(rtt), "--jitter", str(jit),
                   "--loss", str(loss), "--port", str(7300 + 10 * k)]
            if delay_for(rtt):
                cmd += ["--env", f"T5_RB_NET_DELAY={delay_for(rtt)}"]
            for e in cache_env(a) + a.env:
                cmd += ["--env", e]
            print(f"[rollback] {key}: RTT {rtt} +-{jit} ms, {loss} % loss", flush=True)
            lock.take(f"perf_compare rollback {key}")
            try:
                load = busy_processors()
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            finally:
                lock.give()
            d = os.path.join(runs, name)
            open(os.path.join(d, "perf_compare.txt"), "w").write(r.stdout + r.stderr)
            row = {"kind": "rollback", "rtt": rtt, "jitter": jit, "loss": loss, "run": k + 1, "load_before": load}
            for who in ("host", "join"):
                s = {}
                glog = os.path.join(d, who, "game.log")
                lines = open(glog, errors="replace").read().splitlines() if os.path.exists(glog) else []
                txt = "\n".join(rnt.summarize(d, who, 0, False))
                m = re.search(r"sync through frame (\d+): (\d+) mismatching", txt)
                s["sync_frames"], s["mismatch"] = (int(m.group(1)), int(m.group(2))) if m else (None, None)
                m = re.search(r"\(([0-9.]+) fps, 300-frame windows median ([0-9.]+)\), (\d+) rollbacks", txt)
                if m:
                    s["fps"], s["rollbacks"] = float(m.group(2)), int(m.group(3))
                m = re.search(r"(\d+) stalls", txt)
                s["stalls"] = int(m.group(1)) if m else None
                leads = [float(x.group(1)) for x in map(RE_LEAD.search, lines) if x]
                s["lead_ms"] = med(leads[1:] if len(leads) > 1 else leads)
                ls = rnt.latlog_stats(os.path.join(d, who, "lat.log")) or {}
                hist = {int(g): n for g, n in (ls.get("refreshes_per_frame") or {}).items()}
                s["presents"] = ls.get("presents")
                s["shown_twice"] = sum(n for g, n in hist.items() if g >= 2)
                s["extra_refreshes"] = sum(n * (g - 1) for g, n in hist.items() if g >= 2)
                s["p99"] = ls.get("p99")
                s["over_20ms"] = ls.get("over_20ms")
                res = [json.loads(x) for x in open(os.path.join(d, who, "results.jsonl"))] \
                    if os.path.exists(os.path.join(d, who, "results.jsonl")) else []
                s["hash"] = res[-1].get("hash") if res else None
                s["delay"] = str(delay_for(rtt) or "by ping")
                row[who] = s
            results[key] = row
            save(a, results)
            h, j = row["host"], row["join"]
            print(f"  shown twice host/join {h['shown_twice']}/{j['shown_twice']}, mismatching {h['mismatch']}/{j['mismatch']}, "
                  f"fps {h.get('fps')}/{j.get('fps')}, lead {h['lead_ms']:.1f}/{j['lead_ms']:.1f} ms, hash {h['hash']}/{j['hash']}",
                  flush=True)


# ------------------------------------------------------------------ e2e
RE_CONF = re.compile(r"\] (.+?): confirmed  path (\S+).*?E2E [^:]+: to FIGHT.*?mode (\w+), input delay (\d+), (\d+) rollbacks, "
                     r"(\d+) stalls.*?hash (\w+); E2E [^:]+: to FIGHT.*?mode (\w+), input delay (\d+), (\d+) rollbacks, "
                     r"(\d+) stalls.*?hash (\w+); fps ([0-9.]+)/([0-9.]+)")


def run_e2e(a, lock, results):
    exe = os.path.join(a.game, "build", "cmake", "t5dr.exe")
    smooth = ",".join(f"{r}/{j}/{l}" for r, j, l in NETS)
    jobs = [("net_rollback", [], {}),
            ("net_relay_smooth", [], {"E2E_SMOOTH_CASES": smooth, "E2E_SMOOTH_PATHS": "direct"}),
            ("ranked_set", [], {})]
    for name, extra, env in jobs:
        key = f"e2e/{name}"
        if key in results and not a.redo:
            continue
        d = os.path.join(a.out, "e2e", name)
        cmd = [PY, os.path.join(ROOT, "tools", "e2e", "run.py"), "--only", name, "--exe", exe, "--out", d] + extra
        print(f"[e2e] {name}", flush=True)
        lock.take(f"perf_compare e2e {name}")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=dict(os.environ, **env))
        finally:
            lock.give()
        row = {"kind": "e2e", "name": name, "status": None, "checks": 0, "failed": [], "matches": []}
        try:
            rep = json.load(open(os.path.join(d, "report.json")))
            sc = rep["results"][0]
            row["status"] = sc["status"]
            row["checks"] = len(sc.get("checks", []))
            row["failed"] = [c["name"] + ": " + str(c.get("detail")) for c in sc.get("checks", [])
                             if not c["ok"] and c.get("level") == "fail"]
        except (OSError, ValueError, KeyError, IndexError):
            row["status"] = "NO REPORT"
        try:
            for ln in open(os.path.join(d, "run.log"), errors="replace"):
                m = RE_CONF.search(ln)
                if m:
                    g = m.groups()
                    row["matches"].append({"label": g[0], "path": g[1], "mode": g[2], "rollbacks": [int(g[4]), int(g[9])],
                                           "stalls": [int(g[5]), int(g[10])], "same_hash": g[6] == g[11],
                                           "fps": [float(g[12]), float(g[13])]})
                if "0 mismatching frames" in ln or "mismatching frames --" in ln:
                    m2 = re.search(r"desync (\S+)/(\S+)", ln)
                    if m2 and row["matches"]:
                        row["matches"][-1]["desync"] = [m2.group(1), m2.group(2)]
        except OSError:
            pass
        try:
            row["smooth"] = json.load(open(os.path.join(d, name, "smooth.json")))
        except (OSError, ValueError):
            pass
        results[key] = row
        save(a, results)
        print(f"  {row['status']}: {row['checks']} checks, {len(row['failed'])} failed, {len(row['matches'])} matches", flush=True)


# ------------------------------------------------------------------ output
def save(a, results):
    path = os.path.join(a.out, "results.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(results, f, indent=1)
    os.replace(tmp, path)


def f1(x, n=1):
    try:
        return f"{float(x):.{n}f}" if x == x else "-"
    except (TypeError, ValueError):
        return "-"


def summarize_rows(results):
    """{(section, label): {metric: value}} averaged over the runs, for the table and compare."""
    out = {}
    groups = {}
    for key, r in results.items():
        if not isinstance(r, dict) or r.get("error"):
            continue
        if r.get("kind") == "offline":
            groups.setdefault(("offline", f"{r['cpu']:<7} stage {r['stage']:>2} {r['preset']}"), []).append(r)
        elif r.get("kind") == "rollback":
            groups.setdefault(("rollback", f"RTT {r['rtt']} +-{r['jitter']} {r['loss']}%"), []).append(r)
        elif r.get("kind") == "e2e":
            groups.setdefault(("e2e", r["name"]), []).append(r)
    for (sec, label), rs in sorted(groups.items()):
        m = {}
        if sec == "offline":
            for k in ("fps", "p99", "over_20_9", "game_med", "xlat_med", "gpuwait_med", "gpu_pass_ms", "gpu_med",
                      "game_thread_cpu", "cpu_ms_per_frame", "other_load"):
                vals = [r.get(k) for r in rs if isinstance(r.get(k), (int, float)) and r.get(k) == r.get(k)]
                m[k] = statistics.mean(vals) if vals else float("nan")
            m["runs"] = ", ".join(f1(r.get("fps"), 1) for r in rs)
        elif sec == "rollback":
            def both(k):
                vals = [r[w].get(k) for r in rs for w in ("host", "join")
                        if isinstance(r[w].get(k), (int, float)) and r[w].get(k) == r[w].get(k)]
                return statistics.mean(vals) if vals else float("nan")
            for k in ("shown_twice", "extra_refreshes", "p99", "fps", "lead_ms", "rollbacks", "stalls"):
                m[k] = both(k)
            m["mismatch"] = sum((r[w].get("mismatch") or 0) for r in rs for w in ("host", "join"))
            m["synced"] = all(r[w].get("mismatch") == 0 for r in rs for w in ("host", "join"))
            m["same_hash"] = all(r["host"].get("hash") and r["host"].get("hash") == r["join"].get("hash") for r in rs)
            m["delay"] = "/".join(sorted({str(r["host"].get("delay")) for r in rs}))
        else:
            r = rs[-1]
            m["status"] = r["status"]
            m["failed"] = len(r["failed"])
            fps = [x for mm in r["matches"] for x in mm["fps"]]
            m["fps_min"] = min(fps) if fps else float("nan")
            m["fps_mean"] = statistics.mean(fps) if fps else float("nan")
            m["matches"] = len(r["matches"])
            m["same_hash"] = all(mm["same_hash"] for mm in r["matches"])
            sm = r.get("smooth") or []
            if sm:
                m["smooth"] = "; ".join(
                    f"{c['case'][0]:g}ms rb/s {f1(c['host']['rb_per_s'])}/{f1(c['join']['rb_per_s'])} "
                    f"p99 {f1(c['host']['p99_med'])}/{f1(c['join']['p99_med'])} desync {c['host']['desync']}/{c['join']['desync']}"
                    for c in sm)
        out[(sec, label)] = m
    return out


OFF_COLS = [("fps", 1), ("p99", 1), ("over_20_9", 0), ("game_med", 2), ("xlat_med", 2), ("gpuwait_med", 2),
            ("gpu_pass_ms", 2), ("game_thread_cpu", 2), ("cpu_ms_per_frame", 1), ("other_load", 1)]
RB_COLS = [("shown_twice", 1), ("extra_refreshes", 1), ("p99", 1), ("fps", 1), ("lead_ms", 1), ("rollbacks", 0),
           ("mismatch", 0)]


def table(results):
    s = summarize_rows(results)
    print("## Offline fights (Lili vs Asuka; means over the runs; game/xlat/gpuwait = medians of the frame log, "
          "gpu_pass = [gpu-pass] GPU ms a frame)")
    print("| config | " + " | ".join(c for c, _ in OFF_COLS) + " | fps of each run |")
    print("|---" * (len(OFF_COLS) + 2) + "|")
    for (sec, label), m in s.items():
        if sec == "offline":
            print(f"| {label} | " + " | ".join(f1(m[c], n) for c, n in OFF_COLS) + f" | {m['runs']} |")
    print("\n## Rollback pairs (per side and match, means over host+join and runs)")
    print("| network | delay | " + " | ".join(c for c, _ in RB_COLS) + " | same hash |")
    print("|---" * (len(RB_COLS) + 3) + "|")
    for (sec, label), m in s.items():
        if sec == "rollback":
            print(f"| {label} | {m['delay']} | " + " | ".join(f1(m[c], n) for c, n in RB_COLS) + f" | {m['same_hash']} |")
    print("\n## e2e")
    for (sec, label), m in s.items():
        if sec == "e2e":
            print(f"- {label}: {m['status']} ({m['failed']} failed checks), {m['matches']} matches, fps min "
                  f"{f1(m['fps_min'])} mean {f1(m['fps_mean'])}, same hash {m['same_hash']}"
                  + (f"\n  {m['smooth']}" if m.get("smooth") else ""))


def compare(before, after):
    sb, sa = summarize_rows(before), summarize_rows(after)
    keys = [k for k in sb if k in sa]

    def cell(b, a_, n, higher_better):
        try:
            b, a_ = float(b), float(a_)
        except (TypeError, ValueError):
            return f"{b} -> {a_}"
        if b != b or a_ != a_:
            return f"{f1(b, n)} -> {f1(a_, n)}"
        d = a_ - b
        pctd = f" ({100.0 * d / b:+.1f} %)" if b else ""
        return f"{f1(b, n)} -> {f1(a_, n)}{pctd}"
    print("## Offline fights: before -> after (means over the runs)")
    cols = [("fps", 1), ("p99", 1), ("over_20_9", 0), ("game_med", 2), ("xlat_med", 2), ("gpuwait_med", 2),
            ("gpu_pass_ms", 2), ("game_thread_cpu", 2), ("other_load", 1)]
    print("| config | " + " | ".join(c for c, _ in cols) + " |")
    print("|---" * (len(cols) + 1) + "|")
    for k in keys:
        if k[0] == "offline":
            print(f"| {k[1]} | " + " | ".join(cell(sb[k][c], sa[k][c], n, c == "fps") for c, n in cols) + " |")
    print("\n## Rollback pairs: before -> after (per side and match)")
    print("| network | " + " | ".join(c for c, _ in RB_COLS) + " | same hash |")
    print("|---" * (len(RB_COLS) + 2) + "|")
    for k in keys:
        if k[0] == "rollback":
            print(f"| {k[1]} | " + " | ".join(cell(sb[k][c], sa[k][c], n, False) for c, n in RB_COLS)
                  + f" | {sb[k]['same_hash']} -> {sa[k]['same_hash']} |")
    print("\n## e2e: before -> after")
    for k in keys:
        if k[0] == "e2e":
            b, a_ = sb[k], sa[k]
            print(f"- {k[1]}: {b['status']} -> {a_['status']}; failed checks {b['failed']} -> {a_['failed']}; "
                  f"fps min {f1(b['fps_min'])} -> {f1(a_['fps_min'])}, mean {f1(b['fps_mean'])} -> {f1(a_['fps_mean'])}; "
                  f"same hash {b['same_hash']} -> {a_['same_hash']}")
    bad = [k for k in keys if k[0] == "rollback" and not sa[k]["synced"]] + \
          [k for k in keys if k[0] == "e2e" and sa[k]["status"] != "PASS"]
    print("\nverdict: " + ("NOT OK: " + ", ".join(k[1] for k in bad) if bad else
                           "every rollback pair in sync and every e2e scenario PASS in the after build"))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--game", required=True, help="a built game's output folder (build/cmake/t5dr.exe, game/vfs)")
    r.add_argument("--out", required=True)
    r.add_argument("--parts", default="offline,rollback,e2e")
    r.add_argument("--runs", type=int, default=2)
    r.add_argument("--stages", default="", help="only these stage ids (comma list)")
    r.add_argument("--two-core-mask", default="0xF000", help="2 cores / 4 threads (default LP 12-15)")
    r.add_argument("--cpu-configs", default="",
                   help="offline processor sets NAME=MASK,... (default all=,2c=--two-core-mask); e.g. "
                        "all=,2c=0xF000,4c=0x5500,2c2t=0x5000: 4 cores without SMT, 2 cores without SMT")
    r.add_argument("--slow-core", type=int, default=0, help="also 2c-slow: slow_core.py --busy N on those cores")
    r.add_argument("--skip", type=float, default=8.0)
    r.add_argument("--secs", type=float, default=50.0)
    r.add_argument("--rb-cpus1", default="0xFF0000")
    r.add_argument("--rb-cpus2", default="0xFF000000")
    r.add_argument("--lock", default="", help="the shared lock file (taken per game run)")
    r.add_argument("--lock-name", default="perf")
    r.add_argument("--lock-gap", type=float, default=35.0, help="seconds between giving the lock back and taking it again")
    r.add_argument("--redo", action="store_true", help="measure again what results.json already has")
    r.add_argument("--env", action="append", default=[], help="extra NAME=VALUE for every game")
    t = sub.add_parser("table")
    t.add_argument("results")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    a = ap.parse_args()
    if a.cmd == "table":
        table(json.load(open(a.results)))
        return 0
    if a.cmd == "compare":
        return compare(json.load(open(a.before)), json.load(open(a.after)))
    a.game = os.path.abspath(a.game)
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "results.json")
    results = json.load(open(path)) if os.path.exists(path) else {}
    lock = Lock(a.lock, a.lock_name)
    lock.GAP = a.lock_gap
    parts = a.parts.split(",")
    with lock:
        if "offline" in parts or "rollback" in parts:
            warm_up(a, lock, results)
        if "offline" in parts:
            run_offline(a, lock, results)
        if "rollback" in parts:
            run_rollback(a, lock, results)
        if "e2e" in parts:
            run_e2e(a, lock, results)
    table(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
