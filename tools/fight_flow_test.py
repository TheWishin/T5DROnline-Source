#!/usr/bin/env python3
"""Two games on this PC, many matches in a row, the way the launcher drives them.

    python tools/fight_flow_test.py --exe build/cmake/t5dr.exe --out build/ff/runs/r1 \
        [--flow rematch|persistent] [--matches 4] [--mash] [--rounds 1] [--fresh-at N] [--seconds 1500]

--flow rematch (process mode): one host + one joiner started with T5_FIGHT (direct
fight, T5_NET_START=external); every next match is a line in each game's
T5_FIGHT_FILE, written at slightly different times on the two sides (two launchers).

--flow persistent (T5_CTL_DIR): both games are started once without netplay and get
every match as a control command (docs/DIRECTFIGHT.md "Persistent game"): "idle",
then "fight" with a NEW session each time (new UDP ports, seed, key, match id), as
for a new opponent. --rematch-every K makes every K-th match a rematch in the
running session instead. --fresh-at N restarts the joiner's game before match N (a
new opponent whose game has just started meets a game that has played already).

--mash: both players press face buttons and directions at random the whole time
(T5_NET_SCRIPT: fights, KOs, win poses, select screens). --rematch-wait 20 gives
the next command only 20 s after the results (people clicking Rematch late): the
games wait at a live select screen meanwhile, which is where mashing used to start
the game's own next VS battle.

Checks, per match: both games reach FIGHT START of that match, both write its
result file (same winner and state hash, 0 mismatching frames). Prints the time
from the command (fight file / control command) to FIGHT START on both sides.
Windows open minimized, host devices are ignored, every game is killed at the end.
Exit code 0 = every match fought and confirmed on both sides.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def mash_script(path, seed, frames=400000):
    """Face buttons and directions, 1-4 frames each, a few frames apart (no START: that pauses a fight)."""
    rnd = random.Random(seed)
    buttons = [0x4000, 0x2000, 0x8000, 0x1000, 0x4000 | 0x2000, 0x8000 | 0x1000, 0x10, 0x20, 0x40, 0x80, 0x20, 0x80]
    out, f = [], 30
    while f < frames:
        n = rnd.randint(1, 4)
        out.append(f"{f} {n} {rnd.choice(buttons):#x}")
        f += n + rnd.randint(1, 6)
    with open(path, "w") as fp:
        fp.write("\n".join(out) + "\n")
    return path


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


class Game:
    def __init__(self, a, idx, role):
        self.a, self.idx, self.role = a, idx, role
        self.dir = os.path.abspath(os.path.join(a.out, f"run{idx}"))
        os.makedirs(self.dir, exist_ok=True)
        self.status_path = os.path.join(self.dir, "status.json")
        self.result_path = os.path.join(self.dir, "result.json")
        self.fight_path = os.path.join(self.dir, "fight.txt")
        self.ctl = os.path.join(self.dir, "ctl")
        self.seq = 0
        self.proc = None
        self.starts = 0

    def base_env(self):
        vfs = os.path.abspath(self.a.vfs)
        env = dict(os.environ)
        env.update({
            "PS3_VFS_ROOT": vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
            "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
            "PAD_NO_KEYBOARD": "1", "T5_NET_LOCALPAD": "0", "T5_NET_LOG": os.path.join(self.dir, f"frames{self.starts}.log"),
            "T5_DF_STATUS_FILE": self.status_path, "T5_NET_TIMEOUT": "20",
        })
        if self.a.mash:
            env["T5_NET_SCRIPT"] = mash_script(os.path.join(self.dir, "mash.txt"), 100 + self.idx)
        for kv in self.a.env:
            k, v = kv.split("=", 1)
            env[k] = v
        return env

    def start(self, env):
        self.starts += 1
        env["T5_NET_LOG"] = os.path.join(self.dir, f"frames{self.starts}.log")
        self.log_path = os.path.join(self.dir, f"game{self.starts}.log")
        lf = open(self.log_path, "w")
        vfs = os.path.abspath(self.a.vfs)
        self.proc = subprocess.Popen([os.path.abspath(self.a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                                     cwd=self.dir, env=env, stdout=lf, stderr=subprocess.STDOUT)
        log(f"game {self.idx} ({self.role}) started, pid {self.proc.pid}, log {self.log_path}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                pass

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def status(self):
        return read_json(self.status_path) or {}

    def send(self, cmd, **kw):
        self.seq += 1
        os.makedirs(self.ctl, exist_ok=True)
        d = dict(kw, seq=self.seq, cmd=cmd, time=time.time())
        write_atomic(os.path.join(self.ctl, "cmd.json"), json.dumps(d))

    def ctl_state(self):
        return read_json(os.path.join(self.ctl, "state.json")) or {}


def session_env(a, k, match, game, port0):
    """T5_NET_* for a match of session k as the lobby would hand it out (new ports/seed/key per session)."""
    seed = 1000 + 7919 * k
    env = {
        "T5_NET_MODE": game.role, "T5_NET_DELAY": str(a.delay), "T5_NET_TIMEOUT": "20", "T5_NET_MATCH": match,
        "T5_NET_ROUNDS": str(a.rounds), "T5_NET_PATH": "lan", "T5_NET_RTT_MS": "1", "T5_NET_SEED": str(seed),
        "T5_NET_BUILD": "fight-flow-test", "T5_NET_KEY": f"key-{k}-{seed}", "T5_NET_RESULT_FILE": game.result_path,
        "T5_NET_START": "external", "T5_DF_STATUS_FILE": game.status_path,
        "T5_HUD_NAMES": "Tester One|Tester Two", "T5_HUD_RANKS": f"{(k * 3) % 37},{(k * 5) % 37}",
    }
    if game.role == "host":
        env["T5_NET_PORT"] = str(port0)
        env["T5_NET_PEER"] = f"127.0.0.1:{port0 + 1}"
    else:
        env["T5_NET_PORT"] = str(port0 + 1)
        env["T5_NET_PEER"] = f"127.0.0.1:{port0}"
    return env


def fight_line(a, k):
    chars = a.chars.split(",")
    p1, p2 = chars[(2 * k) % len(chars)], chars[(2 * k + 1) % len(chars)]
    stages = [int(s) for s in a.stages.split(",")]
    return f"{p1},{p2},{stages[k % len(stages)]},{a.rounds}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--flow", choices=["rematch", "persistent"], default="rematch")
    ap.add_argument("--matches", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--delay", type=int, default=2)
    ap.add_argument("--chars", default="kaz,hei,lil,dra")
    ap.add_argument("--stages", default="20,33,25,31")
    ap.add_argument("--mash", action="store_true")
    ap.add_argument("--rematch-every", type=int, default=0, help="persistent: every K-th match is a rematch in the session")
    ap.add_argument("--fresh-at", type=int, default=0, help="persistent: restart the joiner's game before this match")
    ap.add_argument("--rematch-wait", type=float, default=1.0,
                    help="seconds between a match's results and the next command (players clicking Rematch late: 20)")
    ap.add_argument("--port", type=int, default=7400)
    ap.add_argument("--seconds", type=float, default=1800)
    ap.add_argument("--match-seconds", type=float, default=420, help="give up on a match after this long")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for both games")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    games = [Game(a, 1, "host"), Game(a, 2, "join")]
    for g in games:
        for p in (g.status_path, g.result_path, g.fight_path, g.fight_path + ".done", os.path.join(g.ctl, "cmd.json"),
                  os.path.join(g.ctl, "state.json")):
            try:
                os.remove(p)
            except OSError:
                pass
    report = {"flow": a.flow, "mash": a.mash, "matches": []}
    ok_all = True
    try:
        port = a.port
        sess_k = 1
        fixed_time = str(int(time.time()))
        for k in range(1, a.matches + 1):
            mid = f"t{k:02d}"
            line = fight_line(a, k)
            rematch = a.flow == "rematch" and k > 1 or (a.rematch_every and k > 1 and (k - 1) % a.rematch_every == 0)
            if a.flow == "persistent" and not rematch:
                port = a.port + 4 * k
                sess_k = k
            base = {}
            for g in games:
                try:
                    os.replace(g.result_path, os.path.join(g.dir, f"result-before-{mid}.json"))
                except OSError:
                    pass
            t_cmd = {}
            for i, g in enumerate(games):
                env = session_env(a, sess_k, mid, g, port)
                st = g.status()
                base[g.idx] = int(st.get("match") or 0)
                if a.flow == "rematch":
                    if k == 1:
                        e = g.base_env()
                        e.update(env)
                        e.update({"T5_FIGHT": line, "T5_FIGHT_FILE": g.fight_path, "PS3_FIXED_TIME": fixed_time})
                        g.start(e)
                    else:
                        time.sleep(random.uniform(0.2, 1.5))       # two launchers never write at the same moment
                        write_atomic(g.fight_path, f"{line} match={mid}\n")
                else:
                    if a.fresh_at == k and g.role == "join" and g.running():
                        log(f"match {k}: restarting game {g.idx} (a new opponent's fresh game)")
                        g.stop()
                    if not g.running():
                        e = g.base_env()
                        e["T5_CTL_DIR"] = g.ctl
                        g.seq = 0
                        for p in (os.path.join(g.ctl, "cmd.json"), os.path.join(g.ctl, "state.json")):
                            try:
                                os.remove(p)
                            except OSError:
                                pass
                        base[g.idx] = 0
                        env2 = dict(env, T5_FIGHT=line)
                        g.send("fight", match=mid, env=env2)
                        g.start(e)
                    else:
                        if not rematch:
                            g.send("idle")
                            time.sleep(random.uniform(0.3, 1.0))   # the lobby's ready check and NAT punch
                        g.send("fight", match=mid, env=dict(env, T5_FIGHT=line), rematch=bool(rematch))
                t_cmd[g.idx] = time.time()
            log(f"match {k} ({mid}): {line}{' (rematch)' if rematch else ''}, ports {port}/{port + 1}")
            m = {"k": k, "match": mid, "line": line, "rematch": bool(rematch)}
            t_fight, results = {}, {}
            t_end = time.time() + a.match_seconds
            while time.time() < t_end and time.time() - T0 < a.seconds:
                for g in games:
                    st = g.status()
                    if g.idx not in t_fight and st.get("state") == "fight" and int(st.get("match") or 0) > base[g.idx]:
                        t_fight[g.idx] = time.time()
                        log(f"match {k}: game {g.idx} FIGHT after {t_fight[g.idx] - t_cmd[g.idx]:.1f} s")
                    r = read_json(g.result_path)
                    if r and r.get("match") == mid and g.idx not in results:
                        results[g.idx] = r
                        log(f"match {k}: game {g.idx} result {json.dumps(r)}")
                if len(results) == 2 or not all(g.running() for g in games):
                    break
                time.sleep(0.25)
            m["to_fight_s"] = {g.idx: round(t_fight[g.idx] - t_cmd[g.idx], 1) if g.idx in t_fight else None for g in games}
            m["results"] = results
            r1, r2 = results.get(1), results.get(2)
            ok = (r1 is not None and r2 is not None and r1.get("winner") == r2.get("winner") and r1.get("winner") is not None
                  and r1.get("hash") == r2.get("hash") and not r1.get("desync") and not r2.get("desync"))
            m["ok"] = ok
            ok_all &= ok
            report["matches"].append(m)
            log(f"match {k}: {'OK' if ok else 'FAILED'} -- to FIGHT {m['to_fight_s']}, winners "
                f"{[r and r.get('winner') for r in (r1, r2)]}, desync {[r and r.get('desync') for r in (r1, r2)]}")
            if not ok or not all(g.running() for g in games):
                ok_all = False
                break
            # the launcher waits for the lobby's verdict and the players' rematch clicks
            time.sleep(a.rematch_wait)
        time.sleep(2.0)
    finally:
        for g in games:
            g.stop()
        for g in games:
            sync = []
            for fn in sorted(f for f in os.listdir(g.dir) if f.startswith("game") and f.endswith(".log")):
                with open(os.path.join(g.dir, fn), encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        mm = re.search(r"sync check through frame (\d+): (\d+) mismatching", ln)
                        if mm:
                            sync.append((fn, int(mm.group(1)), int(mm.group(2))))
            report[f"sync{g.idx}"] = sync[-3:]
            log(f"game {g.idx}: last sync checks {sync[-3:]}")
        report["ok"] = ok_all
        with open(os.path.join(a.out, "report.json"), "w") as f:
            json.dump(report, f, indent=1)
        log(f"{'ALL OK' if ok_all else 'FAILED'}: {sum(1 for m in report['matches'] if m['ok'])}/{a.matches} matches; "
            f"report {os.path.join(a.out, 'report.json')}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
