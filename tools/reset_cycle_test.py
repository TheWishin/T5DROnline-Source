#!/usr/bin/env python3
"""One persistent game, many opponents, every way a session can end (docs/DIRECTFIGHT.md
"Persistent game": "After a session ends").

    python tools/reset_cycle_test.py --exe build/cmake/t5dr.exe --out build/rs/runs/c1 \
        [--cycles 10] [--ends stall,kill,quit,peer_idle,idle,no_peer,desync,normal] [--env T5_RB_MODE=off]

Game S (the survivor) is started once with T5_CTL_DIR and is never restarted: it is
the game under test. Game O (the opponent) is a persistent game too; it is started
again whenever a cycle killed it (a new opponent whose game has just started).

Every cycle is "match -> abnormal end -> next match", the way the launcher drives it
(an "idle", then a "fight" with a new session: new ports, key, seed, match id):

  1. the first match starts on both games; it ends at FIGHT START (the fight still
     loading), --fight-seconds later (in the fight) or at the select screen before
     FIGHT START (no game mode since the last title) -- in turn, cycle by cycle:
       stall      O's process is suspended (a frozen PC) until S gives the session up,
                  then killed
       kill       O's process is killed (a crash, a pulled cable)
       quit       O gets "quit" (its player closed the game: BYE)
       peer_idle  O gets "idle" (its launcher left the match: BYE, O stays open)
       idle       S gets "idle" (S's launcher left the match: the lobby voided it)
       no_peer    only S gets the "fight"; nobody answers (connect timeout)
       desync     O fights on another stage (the two states differ); after
                  --fight-seconds both get "idle" (the lobby voids the match)
       normal     the match is played to its end (KO or time) and confirmed;
                  then both get "idle" (no rematch: the launcher ends the session)
  2. S must come back to a fresh select screen ("neutral") by itself;
  3. the next match (a new session, O restarted if it died) is played to its end:
     both results name it, the same winner and gameplay hash, 0 mismatching frames.

Each cycle fails on: a bad guest call ("not registered"), a NULL call/read/write, a
fence queue overflow, a crash or the title's abort() (in either game), S stuck leaving a
fight or resetting, S not back at neutral, or the next match not confirmed. The FIFO walker's unmapped-JUMP/CALL
resyncs are counted and reported per cycle (main has them in ordinary fights too). Both players
mash buttons in fights (--mash, default on) so matches end in ~20-60 s.
Exit code 0 = every cycle passed. Windows open minimized; every game is killed at the end.
"""
import argparse
import ctypes
import json
import os
import random
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fight_flow_test import Game, mash_script, read_json, session_env  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = time.time()

BAD = [
    ("bad_guest_call", re.compile(r"guest_call: OPD .* not registered")),
    ("null_call", re.compile(r"\[null-call\]")),
    ("null_write", re.compile(r"\[null-write\]")),
    ("null_read", re.compile(r"\[null-read\]")),
    ("fence_overflow", re.compile(r"fence queue overflow")),
    ("crash", re.compile(r"\[CRASH\]")),
    ("abort", re.compile(r"abort\(\) is called")),   # the title's own abort() (rollback-crash: file manager, sound heap)
    ("leave_stuck", re.compile(r"leave: waiting in mode")),
    ("reset_stuck", re.compile(r"reset: waiting in mode")),
    ("stuck_exit", re.compile(r"STUCK:")),
]
# The FIFO walker's own recoveries: a JUMP/CALL to an unmapped IO address, then a
# resync. Main has them in ordinary fights too (an offline fight with no netplay:
# 1; build/dp's persistent runs: 1-8 per game log), so they are counted and
# reported separately; with a fence queue overflow or a bad guest call (the dry
# run's broken game) the cycle fails through BAD.
FIFO = [
    ("fifo_unmapped", re.compile(r"FIFO (JUMP|CALL) to unmapped")),
    ("fifo_resync", re.compile(r"FIFO resync")),
]


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


# ---- process suspend / resume (a frozen PC) ------------------------------------------
_ntdll = ctypes.WinDLL("ntdll") if os.name == "nt" else None
_k32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None
PROCESS_SUSPEND_RESUME = 0x0800


def _suspend(pid, on):
    h = _k32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not h:
        return False
    try:
        return (_ntdll.NtSuspendProcess(h) if on else _ntdll.NtResumeProcess(h)) == 0
    finally:
        _k32.CloseHandle(h)


class Player(Game):
    """fight_flow_test's Game with a log offset (what this cycle added) and a mash script per session."""

    def __init__(self, a, idx, role):
        super().__init__(a, idx, role)
        self.log_pos = 0
        self.carry = ""   # the unread tail of the log of a game that was replaced (its abort, if it died)

    def _read_new(self):
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                f.seek(self.log_pos)
                t = f.read(64 << 20)
                self.log_pos = f.tell()
                return t
        except (OSError, AttributeError):
            return ""

    def log_since(self):
        """Text the game's logs got since the last call (at most 64 MB of the current one), including
        the end of the previous game's log when it was restarted in between."""
        t, self.carry = self.carry + self._read_new(), ""
        return t

    def boot(self):
        e = self.base_env()
        e["T5_CTL_DIR"] = self.ctl
        self.seq = 0
        for p in (os.path.join(self.ctl, "cmd.json"), os.path.join(self.ctl, "state.json"), self.status_path):
            try:
                os.remove(p)
            except OSError:
                pass
        self.carry += self._read_new()   # what the game being replaced wrote last
        self.start(e)
        self.log_pos = 0


def stutter(game, ms, on, lock, stop):
    """--stutter: a choppy opponent -- O's process is suspended for `ms` ms every 0.2-0.6 s while
    `on` is set (S predicts its input meanwhile and rolls back when it comes: rollbacks all through
    the match, the KO included)."""
    while not stop.is_set():
        time.sleep(random.uniform(0.2, 0.6))
        with lock:
            if not on.is_set() or not game.running():
                continue
            pid = game.proc.pid
            _suspend(pid, True)
            time.sleep(ms / 1000.0)
            _suspend(pid, False)


def log_guard(games, limit_mb, stop):
    """A game whose log runs away (a broken game spams NULL accesses: 12 GB in 7 minutes) is killed."""
    while not stop.is_set():
        for g in games:
            try:
                if g.running() and os.path.getsize(g.log_path) > limit_mb << 20:
                    log(f"game {g.idx}: log over {limit_mb} MB -- killed")
                    g.stop()
            except (OSError, AttributeError):
                pass
        stop.wait(2.0)


def bad_lines(text, table=None):
    found = {}
    for name, rx in (table or BAD):
        n = len(rx.findall(text))
        if n:
            found[name] = n
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--stutter", type=int, default=0,
                    help="suspend O for this many ms every 0.2-0.6 s during the matches (rollbacks near the KO)")
    ap.add_argument("--start-cycle", type=int, default=1,
                    help="begin the schedule (end, point, fighters, stage) at this cycle, e.g. to replay a failed one")
    ap.add_argument("--ends", default="stall,kill,quit,peer_idle,idle,no_peer,desync,normal")
    ap.add_argument("--points", default="loading,fight,select", help="where the first match ends, in turn")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--delay", type=int, default=2)
    ap.add_argument("--chars", default="kaz,hei,lil,dra,asu,law")
    ap.add_argument("--stages", default="20,33,25,31,27")
    ap.add_argument("--timeout", type=int, default=10, help="T5_NET_TIMEOUT of every session (the lobby passes 20)")
    ap.add_argument("--fight-seconds", type=float, default=12.0, help="even cycles: seconds after FIGHT START the end comes")
    ap.add_argument("--no-mash", action="store_true")
    ap.add_argument("--port", type=int, default=7600)
    ap.add_argument("--match-seconds", type=float, default=300)
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for both games")
    ap.add_argument("--env1", action="append", default=[], help="NAME=VALUE for S only")
    ap.add_argument("--env2", action="append", default=[], help="NAME=VALUE for O only")
    ap.add_argument("--below-normal", action="store_true", help="start the games at below-normal CPU priority (the PC is in use)")
    ap.add_argument("--mute", action="store_true", help="PS3_AUDIO_MUTE=1 for both games (the mix is zeroed; the PC is in use)")
    a = ap.parse_args()
    a.mash = not a.no_mash
    a.exe2 = None
    if a.mute:
        a.env = a.env + ["PS3_AUDIO_MUTE=1"]
    if not os.path.isfile(os.path.join(a.vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")):
        print(f"no game at {a.vfs} (--vfs <game/vfs of a built tree>)")
        return 2
    os.makedirs(a.out, exist_ok=True)
    ends = [e.strip() for e in a.ends.split(",") if e.strip()]
    points = [p.strip() for p in a.points.split(",") if p.strip()]

    S, O = Player(a, 1, "host"), Player(a, 2, "join")
    for g in (S, O):
        for p in (g.status_path, g.result_path):
            try:
                os.remove(p)
            except OSError:
                pass
    report = {"exe": os.path.abspath(a.exe), "env": a.env, "cycles": []}
    state = {"k": 2 * (a.start_cycle - 1)}   # two sessions per cycle

    def new_session(o_stage=None, o_too=True):
        """'idle' + 'fight' with a new session for S (and O), as the launcher does for a new opponent."""
        state["k"] += 1
        k = state["k"]
        mid = f"c{k:03d}"
        chars = a.chars.split(",")
        stages = [int(s) for s in a.stages.split(",")]
        line = f"{chars[(2 * k) % len(chars)]},{chars[(2 * k + 1) % len(chars)]},{stages[k % len(stages)]},{a.rounds}"
        port = a.port + 4 * (k % 200)
        base = {}
        for g in (S, O) if o_too else (S,):
            env = session_env(a, k, mid, g, port)
            env["T5_NET_TIMEOUT"] = str(a.timeout)
            env["T5_NET_CONNECT_TIMEOUT"] = str(max(15, 2 * a.timeout))
            if a.mash:
                env["T5_NET_SCRIPT"] = mash_script(os.path.join(g.dir, f"mash{k}.txt"), 1000 * k + g.idx)
            gl = line
            if g is O and o_stage is not None:
                p = line.split(",")
                p[2] = str(o_stage)
                gl = ",".join(p)
            env["T5_FIGHT"] = gl
            for p in (g.result_path,):
                try:
                    os.replace(p, os.path.join(g.dir, f"result-before-{mid}.json"))
                except OSError:
                    pass
            st = g.status()
            base[g.idx] = int(st.get("match") or 0) if g.running() else 0
            if not g.running():
                g.boot()
                base[g.idx] = 0
            else:
                g.send("idle")
                time.sleep(random.uniform(0.2, 0.6))
            g.send("fight", match=mid, env=env)
        return mid, line, base, time.time()

    def wait_fight(mid, base, games, seconds=150):
        t_end = time.time() + seconds
        seen = {}
        while time.time() < t_end:
            for g in games:
                st = g.status()
                if g.idx not in seen and st.get("state") in ("fight", "over") and int(st.get("match") or 0) > base[g.idx]:
                    seen[g.idx] = time.time()
            if len(seen) == len(games):
                return True
            if not all(g.running() for g in games):
                return False
            time.sleep(0.2)
        return False

    def wait_neutral(g, seconds=90):
        """S back at a fresh select screen with no session (ctl state idle/error)."""
        t0 = time.time()
        while time.time() - t0 < seconds:
            if not g.running():
                return None, "died"
            st, cs = g.status(), g.ctl_state()
            if st.get("state") == "neutral" and cs.get("state") in ("idle", "error"):
                return time.time() - t0, cs.get("error")
            time.sleep(0.2)
        return None, f"stuck: status {g.status().get('state')}, ctl {g.ctl_state()}"

    def play_match(mid, base, t_cmd):
        """Both games play match `mid` to its end; returns (ok, details)."""
        res = {}
        t_fight = {}
        t_end = time.time() + a.match_seconds
        stutter_set(True)
        while time.time() < t_end:
            for g in (S, O):
                st = g.status()
                if g.idx not in t_fight and st.get("state") == "fight" and int(st.get("match") or 0) > base[g.idx]:
                    t_fight[g.idx] = round(time.time() - t_cmd, 1)
                r = read_json(g.result_path)
                if r and r.get("match") == mid and g.idx not in res:
                    res[g.idx] = r
            if len(res) == 2 or not (S.running() and O.running()):
                break
            time.sleep(0.25)
        stutter_set(False)
        r1, r2 = res.get(1), res.get(2)
        ok = (r1 is not None and r2 is not None and r1.get("winner") is not None and r1.get("winner") == r2.get("winner")
              and r1.get("hash") == r2.get("hash") and r1.get("desync") == 0 and r2.get("desync") == 0)
        return ok, {"to_fight_s": t_fight, "results": res}

    ok_all = True
    stop = threading.Event()
    threading.Thread(target=log_guard, args=((S, O), 300, stop), daemon=True).start()
    st_on, st_lock = threading.Event(), threading.Lock()
    if a.stutter:
        threading.Thread(target=stutter, args=(O, a.stutter, st_on, st_lock, stop), daemon=True).start()

    def stutter_set(on):
        with st_lock:
            (st_on.set if on else st_on.clear)()
    try:
        for c in range(a.start_cycle, a.start_cycle + a.cycles):
            end = ends[(c - 1) % len(ends)]
            point = "fight" if end == "desync" else points[(c - 1) % len(points)]
            cyc = {"cycle": c, "end": end, "point": point}
            log(f"=== cycle {c}: end '{end}' at {point}")
            # ---- 1. the match that ends abnormally
            if end == "no_peer":
                mid, line, base, t_cmd = new_session(o_too=False)
                if O.running():
                    O.send("idle")               # O is somewhere else (another match)
                cyc["first"] = {"match": mid, "line": line}
            else:
                # desync: O fights on another stage than S (the lobby's two lines disagree)
                mid, line, base, t_cmd = new_session(o_stage=17 if end == "desync" else None)
                cyc["first"] = {"match": mid, "line": line}
            if end != "no_peer" and point == "select" and end != "normal":
                # the session ends at the select screen, before FIGHT START (no game mode since the title)
                t_lim = time.time() + 60
                while time.time() < t_lim and not all(g.status().get("state") == "select" for g in (S, O)):
                    time.sleep(0.1)
                cyc["first"]["select_reached"] = all(g.status().get("state") == "select" for g in (S, O))
                time.sleep(0.5)
            elif end != "no_peer":
                reached = wait_fight(mid, base, (S, O))
                cyc["first"]["fight_reached"] = reached
                if not reached:
                    log(f"cycle {c}: the first match did not reach FIGHT START on both games")
                if point == "fight" and end != "normal":
                    time.sleep(a.fight_seconds)
                elif end != "normal":
                    time.sleep(0.3)
            t_end0 = time.time()
            if end == "stall":
                _suspend(O.proc.pid, True)
                log(f"cycle {c}: O (pid {O.proc.pid}) suspended")
                t_lim = time.time() + 3 * a.timeout + 30
                while time.time() < t_lim and S.ctl_state().get("state") not in ("error", "idle"):
                    time.sleep(0.2)
                O.stop()
            elif end == "kill":
                O.stop()
            elif end == "quit":
                O.send("quit")
                t_lim = time.time() + 10
                while O.running() and time.time() < t_lim:
                    time.sleep(0.1)
                O.stop()
            elif end == "peer_idle":
                O.send("idle")
            elif end == "idle":
                S.send("idle")
            elif end == "desync":
                S.send("idle")
                O.send("idle")
            elif end == "normal":
                ok, det = play_match(mid, base, t_cmd)
                cyc["first"].update(det, ok=ok)
                log(f"cycle {c}: normal match {'confirmed' if ok else 'NOT confirmed'}: "
                    f"{[(i, r.get('winner'), r.get('desync'), r.get('reason')) for i, r in det['results'].items()]}")
                # no rematch: the launcher ends the session with "idle" (the game keeps it for a rematch until then)
                S.send("idle")
                O.send("idle")
            took, why = wait_neutral(S)
            cyc["back_to_neutral_s"] = round(took, 1) if took is not None else None
            cyc["s_error"] = why
            r = read_json(S.result_path)
            cyc["first"]["s_result"] = r if r and r.get("match") == mid else None
            log(f"cycle {c}: S back at neutral after {took if took is None else round(took, 1)} s "
                f"(session end: {why}; S result {cyc['first']['s_result'] and cyc['first']['s_result'].get('reason')})")
            if O.running() and end in ("idle", "desync", "peer_idle", "normal"):
                wait_neutral(O, 60)
            # ---- 2. the next match: a new session, played to its end
            mid2, line2, base2, t_cmd2 = new_session()
            ok2, det2 = play_match(mid2, base2, t_cmd2)
            cyc["next"] = dict(det2, match=mid2, line=line2, ok=ok2)
            log(f"cycle {c}: next match {mid2} {'CONFIRMED' if ok2 else 'NOT confirmed'}: to FIGHT {det2['to_fight_s']}, "
                f"{[(i, r.get('winner'), r.get('desync'), r.get('hash')) for i, r in det2['results'].items()]}")
            # ---- 3. the logs
            text_s, text_o = S.log_since(), O.log_since()
            bad_s, bad_o = bad_lines(text_s), bad_lines(text_o)
            cyc["bad_s"], cyc["bad_o"] = bad_s, bad_o
            cyc["fifo_s"], cyc["fifo_o"] = bad_lines(text_s, FIFO), bad_lines(text_o, FIFO)
            # a crash or abort of O fails the cycle too (O rolls back as well; rollback-crash found
            # the sound heap abort on O, which the old check called "clean")
            o_dead = {k: v for k, v in bad_o.items() if k in ("crash", "abort")}
            cyc["ok"] = ok2 and took is not None and not bad_s and not o_dead and S.running()
            ok_all &= cyc["ok"]
            report["cycles"].append(cyc)
            log(f"cycle {c}: {'PASS' if cyc['ok'] else 'FAIL'} (S log: {bad_s or 'clean'}; O log: {bad_o or 'clean'}; "
                f"FIFO walker resyncs S {cyc['fifo_s'] or 0}, O {cyc['fifo_o'] or 0})")
            with open(os.path.join(a.out, "report.json"), "w") as f:
                json.dump(report, f, indent=1)
            if not S.running():
                log("S died: stopping")
                break
            if not cyc["ok"] and not ok2 and took is None:
                break
    finally:
        stop.set()
        for g in (S, O):
            try:
                if g.proc:
                    _suspend(g.proc.pid, False)
            except Exception:
                pass
            g.stop()
        report["ok"] = ok_all and len(report["cycles"]) == a.cycles
        report["s_starts"] = S.starts
        with open(os.path.join(a.out, "report.json"), "w") as f:
            json.dump(report, f, indent=1)
        n = sum(1 for c in report["cycles"] if c["ok"])
        log(f"{'ALL PASS' if report['ok'] else 'FAILED'}: {n}/{a.cycles} cycles in one S process "
            f"(S started {S.starts}x); report {os.path.join(a.out, 'report.json')}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
