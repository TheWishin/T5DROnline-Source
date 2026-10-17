#!/usr/bin/env python3
"""Two different builds of the game in one netplay pair: do they compute the same state?

    python tools/cross_build_test.py --build HOSTDIR --out NAME          (builds both DLLs itself)
    python tools/cross_build_test.py --exe1 A/t5dr.exe --exe2 B/t5dr.exe --out NAME
        [--modes rollback,lockstep] [--fight 26,33,20,2] [--next 33,34,24,2 ...]
        [--rtt 50] [--jitter 5] [--loss 3] [--audit] [--control] [--env1 K=V] [--env2 K=V]

Every player compiles the lifted game code on their own PC (tools/build_game_dll.py):
-march=x86-64-v3 when the PC has AVX2, else the x86-64 baseline. Online play needs
both PCs to compute bit-identical game state from the same inputs. This test runs
the host with one build (--exe1, its t5dr_game.dll beside it) and the joiner with
the other (--exe2) through tools/rollback_net_test.py -- direct fight, scripted
attacks, a latency/loss proxy -- once per mode:

    rollback   what players get (T5_RB_MODE unset: rollback, input delay 2)
    lockstep   the fallback (T5_RB_MODE=off on both)

and compares, frame by frame, the state hashes the two games logged: in rollback
the final hash of every frame (frames.log "f F <hash>", written when every input
before it is confirmed -- what the peers compare), in lockstep the hash of every
frame ("f I <p1> <p2> <hash>"). It FAILS on any differing frame, on a mismatch the
built-in desync check reported, on result files that disagree (winner, score,
hash), on a crash or hang, and when too few frames were compared. With --audit it
also runs tools/fp_audit.py --strict on both game DLLs (no rcp/rsqrt estimates, no
x87, no C runtime math). With --control it then runs the host's build on both
sides with the same matches: a desync that this pair shows too is a rollback or
timing problem of the port, not a difference between the builds (the report
says so; the exit code still follows the mixed pair).

--build HOSTDIR does the building: HOSTDIR holds a runtime built with
-DT5DR_GAME_DLL=ON (t5dr.exe + t5dr.lib, as a release ships it); the tool compiles
the lift (--recomp, --spu, --deps; the developer tree's defaults) twice with
tools/build_game_dll.py, --march x86-64-v3 (--march1) for the host and --march none
(--march2) for the joiner, into build/cross-build-runs/bin/<march>/ (objects kept
there, so a rerun only recompiles what changed), adds --audit, and runs the
baseline joiner as a PC without FMA3 runs it: PS3_FP_SOFT_FMA=1 (the software fma
although this CPU has FMA3) and PS3_CRT_FMA3=0 (the C runtime's non-FMA3 paths);
--hw-fma keeps the instructions. By hand (same lift, same runtime):
    python tools/build_game_dll.py ... --march x86-64-v3 --out X/v3/t5dr_game.dll
    python tools/build_game_dll.py ... --march none      --out X/base/t5dr_game.dll
(copy t5dr.exe next to each). docs/NETPLAY.md, "Same game state on every CPU".

Output: build/cross-build-runs/NAME/<mode>/ (the rollback_net_test run) and
NAME/report.txt. Exit code 0 = in sync, 1 = not.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
RUNS = os.path.join(ROOT, "build", "cross-build-runs")


def read_hashes(frames_log, kind):
    """{frame: hash} -- kind "F": final hashes (rollback), "I": lockstep frame lines.
    A frame logged twice (a re-run after a sync point) keeps its last hash."""
    out = {}
    if not os.path.exists(frames_log):
        return out
    with open(frames_log, errors="replace") as f:
        for line in f:
            p = line.split()
            if len(p) < 3 or p[0].startswith("#") or not p[0].isdigit() or p[1] != kind:
                continue
            h = p[2] if kind == "F" else (p[4] if len(p) > 4 else None)
            if h:
                out[int(p[0])] = h
    return out


def read_sessions(frames_logs, kind):
    """A persistent game logs every netplay session into one file, each from frame 0:
    one {frame: hash} per session, split at the "lockstep starts: frame 0" lines."""
    sessions = []
    for path in frames_logs:
        if not os.path.exists(path):
            continue
        with open(path, errors="replace") as f:
            for line in f:
                if "lockstep starts: frame 0" in line:
                    sessions.append({})
                    continue
                p = line.split()
                if len(p) < 3 or not p[0].isdigit() or p[1] != kind or not sessions:
                    continue
                h = p[2] if kind == "F" else (p[4] if len(p) > 4 else None)
                if h:
                    sessions[-1][int(p[0])] = h
    return sessions


def check_flow(d, mode, min_frames):
    """Compare the two games of a tools/fight_flow_test.py run (persistent game), session by session."""
    lines, ok = [], True
    kind = "F" if mode == "rollback" else "I"
    logs = {}
    for who, run in (("host", "run1"), ("join", "run2")):
        rd = os.path.join(d, run)
        fl = sorted((f for f in os.listdir(rd) if re.match(r"frames\d+\.log$", f)) if os.path.isdir(rd) else [],
                    key=lambda f: int(re.findall(r"\d+", f)[0]))
        logs[who] = read_sessions([os.path.join(rd, f) for f in fl], kind)
        gl = [os.path.join(rd, f) for f in (os.listdir(rd) if os.path.isdir(rd) else []) if re.match(r"game\d+\.log$", f)]
        m = [x for g in gl for x in grep(g, r"fp: game code -march=(\S+), main thread MXCSR (0x[0-9A-Fa-f]+)")]
        lines.append(f"  {who}: -march={m[0].group(1) if m else '?'} (MXCSR {m[0].group(2) if m else '?'}), "
                     f"{len(logs[who])} netplay session(s)")
    total = 0
    for i in range(max(len(logs["host"]), len(logs["join"]))):
        a = logs["host"][i] if i < len(logs["host"]) else {}
        b = logs["join"][i] if i < len(logs["join"]) else {}
        common = sorted(set(a) & set(b))
        diff = [f for f in common if a[f] != b[f]]
        total += len(common)
        lines.append(f"  session {i + 1}: {len(common)} frames on both sides, {len(diff)} differ"
                     + (f"; first at frame {diff[0]}" if diff else ""))
        ok &= not diff
    if total < min_frames:
        lines.append(f"  FAIL: fewer than {min_frames} frames compared")
        ok = False
    rep = None
    try:
        rep = json.load(open(os.path.join(d, "report.json")))
    except (OSError, ValueError):
        pass
    if not rep:
        lines.append("  FAIL: no report.json from tools/fight_flow_test.py")
        ok = False
    else:
        for m in rep.get("matches", []):
            r = m.get("results", {})
            r1, r2 = r.get("1") or r.get(1) or {}, r.get("2") or r.get(2) or {}
            lines.append(f"  match {m['k']} {m['line']}{' (rematch)' if m.get('rematch') else ''}: "
                         f"{'confirmed' if m.get('ok') else 'NOT confirmed'} -- winner {r1.get('winner')}/{r2.get('winner')}, "
                         f"hash {r1.get('hash')}/{r2.get('hash')}, desync {r1.get('desync')}/{r2.get('desync')}")
        ok &= bool(rep.get("ok"))
    lines.insert(0, f"{mode} (persistent game, tools/fight_flow_test.py):")
    lines.append(f"  -> {'IN SYNC' if ok else 'NOT IN SYNC'}")
    return ok, lines


def grep(path, pattern):
    if not os.path.exists(path):
        return []
    rx = re.compile(pattern)
    with open(path, errors="replace") as f:
        return [m for m in (rx.search(l) for l in f) if m]


def results(path):
    res = []
    if os.path.exists(path):
        for line in open(path, errors="replace"):
            try:
                res.append(json.loads(line))
            except ValueError:
                pass
    return res


def check_run(d, mode, min_frames):
    """Compare the two instances of one rollback_net_test run; returns (ok, lines)."""
    lines, ok = [], True
    kind = "F" if mode == "rollback" else "I"
    h1 = read_hashes(os.path.join(d, "host", "frames.log"), kind)
    h2 = read_hashes(os.path.join(d, "join", "frames.log"), kind)
    common = sorted(set(h1) & set(h2))
    diff = [f for f in common if h1[f] != h2[f]]
    arch = {}
    for who in ("host", "join"):
        m = grep(os.path.join(d, who, "game.log"), r"fp: game code -march=(\S+), main thread MXCSR (0x[0-9A-Fa-f]+)")
        arch[who] = (m[0].group(1), m[0].group(2)) if m else ("?", "?")
    lines.append(f"{mode}: host -march={arch['host'][0]} (MXCSR {arch['host'][1]}), "
                 f"joiner -march={arch['join'][0]} (MXCSR {arch['join'][1]})")
    if arch["host"][0] == arch["join"][0] and arch["host"][0] not in ("?", "unknown"):
        lines.append("  note: both instances ran the same target -- this pair compares nothing across targets")
    lines.append(f"  {'final' if kind == 'F' else 'lockstep'} state hashes: {len(common)} frames on both sides "
                 f"(host {len(h1)}, joiner {len(h2)}), {len(diff)} differ"
                 + (f"; first at frame {diff[0]}: {h1[diff[0]]} vs {h2[diff[0]]}" if diff else ""))
    if diff:
        ok = False
    if len(common) < min_frames:
        lines.append(f"  FAIL: fewer than {min_frames} frames compared")
        ok = False
    for who in ("host", "join"):
        sync = grep(os.path.join(d, who, "game.log"), r"sync check through frame (\d+): (\d+) mismatching")
        desync = grep(os.path.join(d, who, "game.log"), r"DESYNC at frame (\d+)")
        started = grep(os.path.join(d, who, "game.log"), r"lockstep starts: frame 0|rollback mode starts")
        rolled = grep(os.path.join(d, who, "game.log"), r"rollback loop takes over|rollback mode starts")
        ran = "nothing" if not started else "the rollback loop" if rolled else "the lockstep"
        last = sync[-1] if sync else None
        lines.append(f"  {who}: built-in sync check " + (f"through frame {last.group(1)}: {last.group(2)} mismatching"
                                                        if last else "none")
                     + (f", {len(desync)} DESYNC line(s)" if desync else "") + f"; ran {ran}")
        if not last or int(last.group(2)) or desync:
            ok = False
        if ran != ("the rollback loop" if mode == "rollback" else "the lockstep"):
            lines.append(f"  FAIL: {who} did not run the {mode} loop")
            ok = False
    r1, r2 = results(os.path.join(d, "host", "results.jsonl")), results(os.path.join(d, "join", "results.jsonl"))
    for i in range(max(len(r1), len(r2))):
        a = r1[i] if i < len(r1) else {}
        b = r2[i] if i < len(r2) else {}
        same = all(a.get(k) == b.get(k) for k in ("winner", "score", "hash", "frames")) and a.get("desync") == 0 == b.get("desync")
        lines.append(f"  match {i + 1}: host {a.get('winner')}/{a.get('score')}/{a.get('hash')}/desync {a.get('desync')}, "
                     f"joiner {b.get('winner')}/{b.get('score')}/{b.get('hash')}/desync {b.get('desync')}"
                     + ("" if same else "  <- DIFFER"))
        ok &= same
    if not r1:
        lines.append("  FAIL: no match result")
        ok = False
    summ = os.path.join(d, "summary.txt")
    if os.path.exists(summ):
        txt = open(summ, errors="replace").read()
        if "HUNG" in txt or "ABORT" in txt:
            lines.append("  FAIL: an instance hung or aborted (summary.txt)")
            ok = False
    lines.append(f"  -> {'IN SYNC' if ok else 'NOT IN SYNC'}")
    return ok, lines


def build_pair(a):
    """--build: t5dr_game.dll for --march1 and --march2 from one lift, each next to a copy
    of the runtime; returns the two t5dr.exe paths."""
    import shutil
    host_exe, host_lib = os.path.join(a.build, "t5dr.exe"), os.path.join(a.build, "t5dr.lib")
    if not (os.path.exists(host_exe) and os.path.exists(host_lib)):
        sys.exit(f"--build: {a.build} needs t5dr.exe and t5dr.lib of a -DT5DR_GAME_DLL=ON build")
    exes = []
    for march in (a.march1, a.march2):
        d = os.path.join(a.runs, "bin", march)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(host_exe, os.path.join(d, "t5dr.exe"))
        cmd = [PY, os.path.join(ROOT, "tools", "build_game_dll.py"), "--recomp", a.recomp, "--spu", a.spu,
               "--deps", a.deps, "--host-lib", host_lib, "--out", os.path.join(d, "t5dr_game.dll"),
               "--obj", os.path.join(d, "obj"), "--march", march, "--jobs", str(a.jobs)]
        print(f"[build] {' '.join(cmd)}", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        last = (r.stdout.strip().splitlines() or ["?"])[-1]
        print(f"[build] {march}: {last}", flush=True)
        if r.returncode:
            print(r.stdout[-3000:] + r.stderr[-3000:])
            sys.exit(f"--build: the {march} game DLL did not build")
        exes.append(os.path.join(d, "t5dr.exe"))
    return exes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe1", help="host build: t5dr.exe (t5dr_game.dll beside it)")
    ap.add_argument("--exe2", help="joiner build")
    ap.add_argument("--build", metavar="HOSTDIR",
                    help="build both game DLLs first: HOSTDIR has t5dr.exe + t5dr.lib of a -DT5DR_GAME_DLL=ON runtime")
    ap.add_argument("--march1", default="x86-64-v3", help="--build: the host's target (default x86-64-v3)")
    ap.add_argument("--march2", default="none", help="--build: the joiner's target (default none, the baseline)")
    ap.add_argument("--hw-fma", action="store_true",
                    help="--build: let a baseline joiner use this CPU's FMA3 instructions (default: the software fma "
                         "and the C runtime's non-FMA3 paths, as on a CPU without FMA3)")
    ap.add_argument("--recomp", default=os.path.join(ROOT, "build", "recomp"), help="--build: the lifted PPU code")
    ap.add_argument("--spu", default=os.path.join(ROOT, "build", "spu"), help="--build: the lifted SPU images")
    ap.add_argument("--deps", default=os.path.join(ROOT, "deps", "ps3recomp"),
                    help="--build: the patched ps3recomp the runtime was built from (headers)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="--build: compile jobs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--modes", default="rollback,lockstep")
    ap.add_argument("--fight", default="26,33,20,2", help="first match: p1,p2,stage,rounds (Asuka vs Lili, stage 20)")
    ap.add_argument("--next", action="append", default=None,
                    help="further matches (default: Lili vs Dragunov, stage 24; 'none': only the first)")
    ap.add_argument("--rtt", type=float, default=50)
    ap.add_argument("--jitter", type=float, default=5)
    ap.add_argument("--loss", type=float, default=3)
    ap.add_argument("--seconds", type=float, default=0, help="time limit per mode (default: 330 s per match)")
    ap.add_argument("--port", type=int, default=7400)
    ap.add_argument("--min-frames", type=int, default=3000, help="fail when fewer frames could be compared")
    ap.add_argument("--audit", action="store_true", help="also tools/fp_audit.py --strict on both game DLLs")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--env1", action="append", default=[])
    ap.add_argument("--env2", action="append", default=[])
    ap.add_argument("--runs", default=RUNS)
    ap.add_argument("--recheck", action="store_true", help="only compare the runs already in --out (no new run)")
    ap.add_argument("--flow", choices=["process", "persistent"], default="process",
                    help="process: a game process per pair, matches through T5_FIGHT/T5_FIGHT_FILE "
                         "(tools/rollback_net_test.py, with the latency proxy); persistent: games that stay open, every "
                         "match a control command with a new session (T5_CTL_DIR, tools/fight_flow_test.py --mash)")
    ap.add_argument("--matches", type=int, default=3, help="--flow persistent: matches (new sessions) per mode")
    ap.add_argument("--control", action="store_true",
                    help="also run the host's build on both sides (same matches): tells a cross-build difference "
                         "from a rollback/timing desync the same build has too")
    ap.add_argument("--vfs", default=os.environ.get("PS3_VFS_ROOT", os.path.join(ROOT, "game", "vfs")),
                    help="the game's vfs folder (default: PS3_VFS_ROOT, else game/vfs)")
    a = ap.parse_args()
    if not os.path.exists(os.path.join(a.vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")):
        sys.exit(f"no game in {a.vfs} (--vfs)")
    if a.build:
        a.exe1, a.exe2 = build_pair(a)
        a.audit = True
        if "none" in (a.march1, a.march2) and not a.hw_fma:
            soft = ["PS3_FP_SOFT_FMA=1", "PS3_CRT_FMA3=0"]
            if a.march2 == "none":
                a.env2 = soft + a.env2
            elif a.march1 == "none":
                a.env1 = soft + a.env1
    elif not (a.exe1 and a.exe2):
        sys.exit("give --exe1 and --exe2, or --build HOSTDIR")
    nxt = [n for n in (a.next if a.next is not None else ["33,34,24,2"]) if n != "none"]   # --next none: one match
    matches = 1 + len(nxt)
    base = os.path.join(a.runs, a.out)
    os.makedirs(base, exist_ok=True)
    report, ok_all = [f"cross-build test {a.out}: host {a.exe1}, joiner {a.exe2}, rtt {a.rtt} jitter {a.jitter} "
                      f"loss {a.loss}, matches {a.fight} then {' '.join(nxt) or '-'}"], True
    if a.audit:
        for exe in (a.exe1, a.exe2):
            dll = os.path.join(os.path.dirname(os.path.abspath(exe)), "t5dr_game.dll")
            if not os.path.exists(dll):
                continue
            r = subprocess.run([PY, os.path.join(ROOT, "tools", "fp_audit.py"), "--strict", dll], capture_output=True, text=True)
            report += r.stdout.strip().splitlines()
            ok_all &= r.returncode == 0
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]

    def run_pair(exe1, exe2, env1, env2, prefix, port):
        ok_pair, out = True, []
        for i, mode in enumerate(modes):
            if a.flow == "persistent":
                d = os.path.join(base, prefix + mode)
                cmd = [PY, os.path.join(ROOT, "tools", "fight_flow_test.py"), "--flow", "persistent", "--exe", exe1,
                       "--exe2", exe2, "--out", d, "--matches", str(a.matches), "--rounds", "2", "--mash",
                       "--port", str(port + 20 * i), "--vfs", a.vfs, "--seconds", str(a.seconds or 400 * a.matches + 120)]
                if mode == "lockstep":
                    cmd += ["--env", "T5_RB_MODE=off"]
                for flag, vals in (("--env", a.env), ("--env1", env1), ("--env2", env2)):
                    for kv in vals:
                        cmd += [flag, kv]
                t0 = time.time()
                if not a.recheck:
                    print(f"[{prefix}{mode}] {' '.join(cmd)}", flush=True)
                    subprocess.run(cmd, stdout=open(os.path.join(base, f"{prefix}{mode}.out"), "w"), stderr=subprocess.STDOUT)
                ok, lines = check_flow(d, mode, a.min_frames)
                lines[0] = prefix + lines[0]
                lines.insert(1, f"  ({time.time() - t0:.0f} s, run directory {d})")
                out += lines
                ok_pair &= ok
                print("\n".join(lines), flush=True)
                continue
            rb_mode = {"rollback": "default", "lockstep": "off"}[mode]
            cmd = [PY, os.path.join(ROOT, "tools", "rollback_net_test.py"), "--out", prefix + mode, "--runs", base,
                   "--exe", exe1, "--exe2", exe2, "--fight", a.fight, "--matches", str(matches),
                   "--seconds", str(a.seconds or 330 * matches + 60), "--rtt", str(a.rtt), "--jitter", str(a.jitter),
                   "--loss", str(a.loss), "--delay", "3", "--mode1", rb_mode, "--mode2", rb_mode,
                   "--port", str(port + 10 * i), "--vfs", a.vfs.replace(os.sep, "/")]
            for n in nxt:
                cmd += ["--next", n]
            for flag, vals in (("--env", a.env), ("--env1", env1), ("--env2", env2)):
                for kv in vals:
                    cmd += [flag, kv]
            t0 = time.time()
            if not a.recheck:
                print(f"[{prefix}{mode}] {' '.join(cmd)}", flush=True)
                subprocess.run(cmd, stdout=open(os.path.join(base, f"{prefix}{mode}.out"), "w"), stderr=subprocess.STDOUT)
            ok, lines = check_run(os.path.join(base, prefix + mode), mode, a.min_frames)
            lines[0] = prefix + lines[0]
            lines.insert(1, f"  ({time.time() - t0:.0f} s, run directory {os.path.join(base, prefix + mode)})")
            out += lines
            ok_pair &= ok
            print("\n".join(lines), flush=True)
        return ok_pair, out

    ok_mixed, lines = run_pair(a.exe1, a.exe2, a.env1, a.env2, "", a.port)
    report += lines
    ok_all &= ok_mixed
    if a.control:
        # the same build on both sides, same matches: a desync here is a rollback or timing
        # problem of the game port, not a difference between the builds
        ok_ctl, lines = run_pair(a.exe1, a.exe1, a.env1, a.env1, "control_", a.port + 50)
        report += lines
        report.append(f"control pair (host build on both sides): {'in sync' if ok_ctl else 'NOT in sync'}"
                      + ("" if ok_ctl or ok_mixed else " -- the same build desyncs too: not a cross-build difference"))
    report.append("PASS: the two builds stayed in sync" if ok_all else "FAIL: the two builds did not stay in sync")
    open(os.path.join(base, "report.txt"), "w").write("\n".join(report) + "\n")
    print(report[-1])
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
