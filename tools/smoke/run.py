#!/usr/bin/env python3
"""Regression smoke suite: boot the game, drive it through its modes with
both pads scripted, and check that nothing broke. See docs/SMOKE.md.

    python tools/smoke/run.py [--exe build/cmake/t5dr.exe] [--suite quick|full] [--out DIR]
                              [--only TEST,...] [--list] [--set KEY=VALUE ...] [--strict]

  quick  (~6 min)  boot/menu, Arcade fight, VS with two pads, Practice,
                   title twice (QA issue 1)
  full   (~25 min) quick + Ghost, Survival loop, Options, Gallery offline,
                   save -> reboot -> load, 10 min idle/attract

Every test starts its own t5dr.exe (tools/run_game.py's environment plus
PS3_WINDOW_BACKGROUND=1, AUDIO_RATE=1, LD_FRAME_DUMP, scripted pads) in its
own working directory with an empty gamedata, and stops only that process.
Writes <out>/report.md and <out>/report.json; exit code 0 = nothing
unexpected failed, 1 = a regression, 2 = the suite could not run a test.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import checks  # noqa: E402
import procs  # noqa: E402
import report  # noqa: E402
import scenarios  # noqa: E402
from game import ROOT, Abort, Game, find_game_root  # noqa: E402

KNOWN = os.path.join(HERE, "known_issues.json")


def load_known(path=KNOWN):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Ctx:
    """What a scenario gets: boot() starts a game for this test."""

    def __init__(self, test_dir, opts):
        self.dir = test_dir
        self.opts = opts
        self.games = []

    def boot(self, label=None, keep_gamedata=False, env=None):
        d = os.path.join(self.dir, label) if label else self.dir
        e = {"RSX_SHADER_CACHE_DIR": self.opts.shader_cache} if self.opts.shader_cache else {}
        e.update(env or {})
        g = Game(d, exe=self.opts.exe, root=self.opts.root, env=e, dump_every=self.opts.dump_every,
                 cwd=os.path.join(self.dir, "cwd"), keep_gamedata=keep_gamedata, verbose=not self.opts.quiet)
        g.label = label
        self.games.append(g)
        g.start()
        return g

    def stop(self, g):
        if not getattr(g, "_stopped", False):
            g._stopped = True
            g.result_cache = g.stop() if g.proc is not None else g.result()
        return g.result_cache

    def stop_all(self):
        return [(g.label, self.stop(g)) for g in self.games]


def file_info(path):
    try:
        st = os.stat(path)
    except OSError:
        return {}
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"exe_size": st.st_size, "exe_sha1": h.hexdigest()[:12],
            "exe_mtime": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")}


def git_rev():
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return None


def run_test(t, opts, known):
    test_dir = os.path.join(opts.out, t["name"])
    ctx = Ctx(test_dir, opts)
    t0 = time.perf_counter()
    error = None
    print(f"== {t['name']}: {t['desc']}", flush=True)
    try:
        t["fn"](ctx)
    except Abort as e:
        print(f"   aborted: {e}", flush=True)
    except Exception:
        error = traceback.format_exc(limit=4).strip().splitlines()[-1]
        traceback.print_exc()
    finally:
        runs = ctx.stop_all()
    all_checks = []
    for label, run in runs:
        if run.get("start_error"):
            error = error or run["start_error"]
        cs = checks.evaluate(run, known_nids=checks.known_nid_set(known), thresholds=opts.thresholds,
                             strict=opts.strict)
        for c in cs:
            if label and len(runs) > 1:
                c["id"] = f"{label}.{c['id']}"
                if c.get("evidence"):
                    c["evidence"] = f"{label}/{c['evidence']}"
        all_checks += cs
        with open(os.path.join(run["dir"], "run.json"), "w", encoding="utf-8") as f:
            json.dump(run, f, indent=1, default=str)
    checks.apply_known(t["name"], all_checks, known.get("failures", []))
    res = {"name": t["name"], "desc": t["desc"], "duration": round(time.perf_counter() - t0, 1),
           "checks": all_checks, "error": error,
           "contention": [r.get("contention") for _, r in runs]}
    st = "ERROR" if error else checks.test_status(all_checks).upper()
    bad = [c for c in all_checks if c["status"] in ("fail", "warn", "known-fail", "xpass")]
    print(f"   {st} in {res['duration']:.0f}s" + "".join(
        f"\n     {c['status']:10s} {c['id']}: {c['detail'][:150]}" + (f" [{c['issue']}]" if c.get("issue") else "")
        for c in bad), flush=True)
    return res


def parse_set(items):
    out = {}
    for kv in items or []:
        k, v = kv.split("=", 1)
        if k not in checks.DEFAULTS:
            sys.exit(f"--set: unknown threshold {k!r} (known: {', '.join(sorted(checks.DEFAULTS))})")
        out[k] = float(v)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", help="t5dr.exe to test (default: <root>/build/cmake/t5dr.exe)")
    ap.add_argument("--root", help="tree with game/vfs (default: this checkout or the first parent that has one)")
    ap.add_argument("--suite", choices=("quick", "full"), default="quick")
    ap.add_argument("--only", help="comma-separated test names (any suite)")
    ap.add_argument("--out", help="report directory (default: <root>/build/smoke/<time>-<suite>)")
    ap.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a threshold (see checks.DEFAULTS)")
    ap.add_argument("--strict", action="store_true", help="fps/audio failures fail even when other games or compilers run")
    ap.add_argument("--dump-every", type=int, default=60, help="frame dump interval in flips (default 60: about one per second)")
    ap.add_argument("--shader-cache", help="RSX_SHADER_CACHE_DIR for all tests (default: <root>/build/smoke/shader_cache)")
    ap.add_argument("--known", default=KNOWN, help="known issues file")
    ap.add_argument("--list", action="store_true", help="list the tests and exit")
    ap.add_argument("--quiet", action="store_true", help="no per-event lines")
    opts = ap.parse_args(argv)

    if opts.list:
        for t in scenarios.TESTS.values():
            print(f"{t['name']:16s} {','.join(t['suites']):11s} ~{t['budget']:4d}s  {t['desc']}")
        return 0

    opts.root = os.path.abspath(opts.root) if opts.root else find_game_root()
    opts.exe = os.path.abspath(opts.exe or os.path.join(opts.root, "build", "cmake", "t5dr.exe"))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    opts.out = os.path.abspath(opts.out or os.path.join(opts.root, "build", "smoke", f"{stamp}-{opts.suite}"))
    if opts.shader_cache is None:
        opts.shader_cache = os.path.join(opts.root, "build", "smoke", "shader_cache")
    if opts.shader_cache:
        os.makedirs(opts.shader_cache, exist_ok=True)
    opts.thresholds = parse_set(opts.set)
    known = load_known(opts.known)

    if opts.only:
        names = [n.strip() for n in opts.only.split(",") if n.strip()]
        unknown = [n for n in names if n not in scenarios.TESTS]
        if unknown:
            sys.exit(f"unknown test(s): {', '.join(unknown)} (--list shows them)")
        todo = [scenarios.TESTS[n] for n in names]
    else:
        todo = scenarios.tests_for(opts.suite)

    os.makedirs(opts.out, exist_ok=True)
    meta = {"suite": opts.only and f"only {opts.only}" or opts.suite, "exe": opts.exe, "root": opts.root,
            "out": opts.out, "started": stamp, "repo_rev": git_rev(), "thresholds": dict(checks.DEFAULTS, **opts.thresholds),
            "strict": opts.strict, "cpus": procs.cpu_count()}
    meta.update(file_info(opts.exe))
    c0 = procs.contention(procs.list_processes(), set())
    print(f"smoke {meta['suite']}: {len(todo)} test(s), exe {opts.exe} ({meta.get('exe_mtime', 'missing')}), "
          f"out {opts.out}", flush=True)
    if c0["games"] or c0["builds"]:
        print(f"note: {c0['games']} other t5dr.exe and {c0['builds']} compiler process(es) running -- "
              "fps/audio may be low (reported as WARN)", flush=True)

    t_start = time.perf_counter()
    results = []
    for t in todo:
        results.append(run_test(t, opts, known))
        meta["duration"] = time.perf_counter() - t_start
        load = [c for r in results for c in r.get("contention") or [] if c]
        if load:
            meta["contention"] = (f"up to {max(c['games'] for c in load)} other t5dr.exe, "
                                  f"{max(c['builds'] for c in load)} compiler processes")
        report.write(opts.out, meta, results)     # after every test: a partial report survives a crash

    md = report.write(opts.out, meta, results)
    code = report.exit_code(results)
    print()
    print(md.split("## All checks")[0].rstrip())
    print(f"\nreport: {os.path.join(opts.out, 'report.md')}  (exit {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
