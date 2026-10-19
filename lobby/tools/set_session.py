#!/usr/bin/env python3
"""Ranked sets end to end on one PC (docs/RANKED.md "Ranked sets"): a local lobby, two accounts, the ranked
queue, two games driven by the launcher's glue (t5lobby.match_driver.MatchDriver, as the Online tab does),
best-of-3 sets played to a plan.

    python lobby/tools/set_session.py --exe build/cmake/t5dr.exe --out <dir> --plan 2-0,2-1
    python lobby/tools/set_session.py --out <dir> --plan 2-0,2-1           # stub games (winners from the seed)

--plan: one entry per set, games won by the first account (A) - by the second (B): 2-0 = A wins games 1 and
2; 2-1 = A, B, A; 1-2 = A, B, B; 0-2 = B, B. With the real game the winner of each game is the only player
who presses anything (a live bot writes attacks to that game's T5_NET_PADFILE while the fight runs; the
other one stands still), so the plan decides the games. After the first set the driver accepts the rematch,
which is the next set (a new set, the same running games).

Checks: every set ends with the planned score and status confirmed; the rating changes once per set (each
game but the last has no rating change; the account's ranked games grow by one per set); the games of a
set continue in the running games (match_start continue) with the same characters and sides; history and
profile list the set with its games. Prints the time from each game's result to the next game's FIGHT START.

Real game: both instances minimized (PS3_WINDOW_BACKGROUND=1), muted (PS3_AUDIO_MUTE=1), below-normal
priority, no pads or keyboard; every game started here is killed at the end. The lobby runs on 127.0.0.1
with its own database in <out>. Exit code 0 = every set as planned.
"""
import argparse
import json
import os
import random
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
ROOT = os.path.dirname(LOBBY)
sys.path.insert(0, LOBBY)

from t5lobby import ranks, sets as setsmod  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.match_driver import MatchDriver  # noqa: E402

GAME_ENV = {"PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
            "PS3_AUDIO_MUTE": "1", "T5_NET_LOCALPAD": "0", "PAD_NO_KEYBOARD": "1"}
BELOW_NORMAL = 0x00004000
T0 = time.time()
LOGF = None


def log(msg):
    line = f"[{time.time() - T0:7.1f}s] {msg}"
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + "\n")
        LOGF.flush()


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(a):
    tcp, udp, udp2 = free_port(), free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    env = dict(os.environ, T5L_DB=os.path.join(a.out, "lobby.db"), T5L_LOG_LEVEL="INFO", PYTHONPATH=LOBBY,
               T5L_SCRYPT_N=str(1 << 12), T5L_MIN_MATCH_SECONDS=str(a.min_seconds), T5L_RESULT_TIMEOUT="60",
               T5L_ROUNDS=str(a.rounds), T5L_RANKED_SET_WINS="2", T5L_SET_NEXT_SECONDS=str(a.next_seconds),
               T5L_STATUS_PORT="0", T5L_RECONNECT_GRACE="20")
    lf = open(os.path.join(a.out, "server.log"), "w")
    p = subprocess.Popen([sys.executable, "-m", "t5lobby.server", "--host", "127.0.0.1", "--port", str(tcp),
                          "--udp-port", str(udp), "--udp-port2", str(udp2)], env=env, cwd=LOBBY,
                         stdout=lf, stderr=subprocess.STDOUT, text=True)
    t_end = time.time() + 10
    while time.time() < t_end:
        try:
            socket.create_connection(("127.0.0.1", tcp), 0.5).close()
            return p, f"127.0.0.1:{tcp}"
        except OSError:
            time.sleep(0.1)
    p.kill()
    sys.exit("lobby server did not start")


def plan_games(entry):
    """'2-1' -> ['A', 'B', 'A'] (who wins game 1, 2, 3)."""
    x, y = (int(v) for v in entry.split("-"))
    seq = {(2, 0): "AA", (2, 1): "ABA", (1, 2): "ABB", (0, 2): "BB"}.get((x, y))
    if seq is None:
        raise SystemExit(f"--plan: {entry!r} is not 2-0, 2-1, 1-2 or 0-2")
    return list(seq)


class ProcGame:
    def __init__(self, cmd, env, cwd, log_path, real):
        self.log_path = log_path
        si, flags = None, 0
        if real and os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7          # SW_SHOWMINNOACTIVE: minimized, never activated
            flags = BELOW_NORMAL
        with open(log_path, "w") as lf:
            self.proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, startupinfo=si, creationflags=flags)

    def running(self):
        return self.proc.poll() is None

    def stop(self):
        if self.running():
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)
            else:
                self.proc.kill()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                pass


class Player:
    def __init__(self, a, addr, build, idx, name, char):
        self.a, self.idx, self.name, self.char = a, idx, name, char
        self.tag = "AB"[idx]
        self.dir = os.path.abspath(os.path.join(a.out, f"p{idx + 1}"))
        os.makedirs(self.dir, exist_ok=True)
        self.client = LobbyClient(addr, build, auto_ready=True, sets=True)
        self.client.connect()
        self.client.register(name, "password-" + name)
        self.games = []
        self.events = []
        self.padfile = os.path.join(self.dir, "pad.txt")
        open(self.padfile, "w").close()
        self.rnd = random.Random(7 + idx)
        self.attacking = False
        self.role = None
        self.sets_done = 0
        self.t_result = None           # when the last game's result came (set going on)
        self.fight_base = 0
        self.next_times = []           # result -> next game's FIGHT START, seconds
        self.driver = MatchDriver(self.client, self.launch, self.dir, mode="persistent" if a.exe else a.mode,
                                  ask_manual=False, auto_rematch=len(a.plans) - 1,
                                  extra_env=dict(kv.split("=", 1) for kv in a.env))

    def launch(self, env):
        a = self.a
        n = len(self.games) + 1
        full = dict(os.environ)
        full.update(env)
        logp = os.path.join(self.dir, f"game{n}.log")
        if a.exe:
            vfs = os.path.abspath(a.vfs)
            full.update(GAME_ENV)
            full["PS3_VFS_ROOT"] = vfs.replace("\\", "/")
            full["PS3_HDD0_ROOT"] = os.path.join(vfs, "dev_hdd0").replace("\\", "/")
            full["PS3_TITLE"] = f"T5DR set session: {self.name}"
            full["T5_NET_LOG"] = os.path.join(self.dir, f"frames{n}.log")
            full["T5_NET_PADFILE"] = self.padfile
            cmd = [os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")]
        else:
            full.setdefault("T5_STUB_SECONDS", "2")
            full.setdefault("T5_STUB_MATCHES", "9")
            full.setdefault("T5_STUB_GAP", "1")
            full.setdefault("T5_STUB_LINGER", "30")
            cmd = [sys.executable, os.path.join(HERE, "stub_game.py")]
        g = ProcGame(cmd, full, self.dir, logp, real=bool(a.exe))
        self.games.append(g)
        log(f"{self.name}: game {n} started (pid {g.proc.pid}) "
            + " ".join(f"{k}={env[k]}" for k in sorted(env) if k.startswith(("T5_FIGHT", "T5_HUD", "T5_CTL"))))
        return g

    def status(self):
        p = self.driver.status_path
        try:
            with open(p) as f:
                return json.load(f)
        except (OSError, ValueError, TypeError):
            return None

    def pump(self):
        while True:
            ev = self.client.next_event(0)
            if ev is None:
                break
            self.events.append(ev)
            self.driver.on_event(ev)
            t = ev["t"]
            if t == "match_found":
                log(f"{self.name}: match_found {ev['match']} origin {ev['origin']} ranked {ev['ranked']} "
                    f"set {json.dumps(ev.get('set'))}")
            elif t == "match_start":
                s = ev.get("set") or {}
                f = ev.get("fight") or {}
                self.role = "host" if ev["slot"] == 0 else "join"
                plan = self.a.plans[min(self.sets_done, len(self.a.plans) - 1)]
                n = int(s.get("number") or 1)
                self.attacking = plan[min(n, len(plan)) - 1] == self.tag
                self.fight_base = int((self.status() or {}).get("match") or 0) if self.driver.game_running() else 0
                log(f"{self.name}: match_start {ev['match']} {f.get('p1')} vs {f.get('p2')} stage {f.get('stage')} "
                    f"P{ev['slot'] + 1} continue={ev.get('continue')} -- {setsmod.status_text(s, ev['slot'])}"
                    f" -- {'attacks' if self.attacking else 'stands still'}")
            elif t == "match_result":
                s = ev.get("set") or {}
                r = ev.get("rating") or {}
                log(f"{self.name}: match_result {ev['status']}{' (' + ev['reason'] + ')' if ev.get('reason') else ''} "
                    f"winner P{(ev['winner'] or 0) + 1 if ev['winner'] is not None else '-'} score {ev['score']} -- "
                    f"{setsmod.status_text(s, (self.driver.session_ticket.slot if self.driver.session_ticket else 0))}"
                    + (f" -- rating {r['before']['r']:.0f} -> {r['after']['r']:.0f}" if r else " -- no rating change"))
                self.attacking = False
                self.t_result = time.time() if s.get("next") else None
                self.fight_base = max(self.fight_base, int((self.status() or {}).get("match") or 0))
            elif t == "set_end":
                self.sets_done += 1
                log(f"{self.name}: set_end {ev.get('reason')}: {setsmod.result_text(ev)}")
            elif t in ("notice", "match_cancel", "rematch", "error"):
                log(f"{self.name}: {t}: {ev.get('msg') or ev.get('reason') or ev.get('state')}")
        for n in self.driver.poll():
            if n["kind"] == "status":
                log(f"{self.name}: [driver] {n['text']}")
        st = self.status() or {}
        if self.t_result and st.get("state") == "fight" and int(st.get("match") or 0) > self.fight_base:
            dt = time.time() - self.t_result
            self.next_times.append(round(dt, 1))
            log(f"{self.name}: result -> next game's FIGHT START {dt:.1f} s")
            self.t_result = None

    def bot(self):
        """The planned winner attacks while the fight runs; the other player stands still."""
        if not self.a.exe or not self.attacking or not self.driver.game_running():
            return
        st = self.status() or {}
        if st.get("state") != "fight":
            return
        try:
            if os.path.getsize(self.padfile):
                return
        except OSError:
            return
        fwd = 0x20 if self.role == "host" else 0x80
        down = 0x40
        btn = self.rnd.choice([0x8000, 0x1000, 0x4000, 0x2000, 0x8000 | 0x4000, 0x1000 | 0x2000,
                               down | 0x4000, down | 0x2000, fwd | 0x1000, fwd, fwd])
        try:
            with open(self.padfile, "w") as fp:
                fp.write(f"{btn:#x} {self.rnd.randint(3, 6)}")
        except OSError:
            pass

    def set_ends(self):
        return [e for e in self.events if e["t"] == "set_end"]

    def close(self):
        try:
            self.driver.close()
        finally:
            for g in self.games:
                g.stop()
            self.client.close()


def main():
    global LOGF
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", help="t5dr.exe (direct fight + persistent game); without it the stub game runs")
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", default="2-0,2-1", help="sets to play, games won by A - by B (2-0, 2-1, 1-2, 0-2)")
    ap.add_argument("--rounds", type=int, default=3, help="rounds to win a game (the server's T5L_ROUNDS)")
    ap.add_argument("--min-seconds", type=float, default=20.0, help="server: minimum game length")
    ap.add_argument("--next-seconds", type=float, default=6.0, help="server: countdown to the set's next game")
    ap.add_argument("--mode", choices=["process", "persistent"], default="persistent", help="stub games only")
    ap.add_argument("--seconds", type=float, default=1800.0, help="give up after this long")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for both games (every match too)")
    ap.add_argument("--names", default="SetAlpha,SetBravo")
    ap.add_argument("--chars", default="kazuya,heihachi")
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    a.plans = [plan_games(p.strip()) for p in a.plan.split(",") if p.strip()]
    LOGF = open(os.path.join(a.out, "harness.log"), "a", encoding="utf-8")
    log(f"=== set session: plan {a.plan}, rounds {a.rounds}, {'real game ' + a.exe if a.exe else 'stub games'}")
    build = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "set-session", "demo")
    names, chars = a.names.split(","), a.chars.split(",")
    server, addr = start_server(a)
    log(f"lobby server on {addr}")
    players = []
    ok = True
    try:
        for i in (0, 1):
            players.append(Player(a, addr, build, i, names[i], chars[i]))
        for p in players:
            p.client.set_char(p.char)
            p.client.ranked_match()
        t_end = time.time() + a.seconds
        while time.time() < t_end:
            for p in players:
                p.pump()
                p.bot()
            if all(len(p.set_ends()) >= len(a.plans) for p in players):
                break
            time.sleep(0.1)
        for _ in range(5):
            for p in players:
                p.pump()
            time.sleep(0.2)
        log("--- results")
        A = players[0]
        ends = A.set_ends()
        for k, plan in enumerate(a.plans):
            want = [plan.count("A"), plan.count("B")]
            se = ends[k] if k < len(ends) else None
            got = se and se.get("wins")
            # (the stub game picks its winners from the seed: there only a decided best-of-3 is checked)
            good = se is not None and se.get("status") == "confirmed" and (
                got == want if a.exe else max(got) == 2 and min(got) < 2)
            ok &= good
            log(f"set {k + 1}: planned {want[0]}-{want[1]}, got {got} {se and se.get('status')} "
                f"-> {'OK' if good else 'NOT AS PLANNED'}")
        results = [e for e in A.events if e["t"] == "match_result"]
        rated = [r["rating"] is not None for r in results]
        log(f"rating changes per game (A): {rated}")
        starts = [e for e in A.events if e["t"] == "match_start"]
        log("continue per game (A): " + str([s.get("continue") for s in starts]))
        for p in players:
            prof = p.client.profile()
            log(f"{prof['name']}: {ranks.label(prof)}, rating {prof['rating']} +/- {prof['rd']}, record {prof['record']}, "
                f"ranked sets {prof['ranked_games']}")
            ok &= prof["ranked_games"] == len(a.plans)
            for s in prof.get("sets", []):
                log(f"    set vs {s['opponent']}: {s['result']} {s['score']} {s['status']}, delta {s['delta']}, games "
                    + ", ".join(f"{g['result']} {g['score']}" for g in s["games"]))
            log(f"{p.name}: result -> next FIGHT START (s): {p.next_times}; reported {p.driver.history}")
        log("ALL SETS AS PLANNED" if ok else "SOMETHING DIFFERED")
        return 0 if ok else 1
    finally:
        for p in players:
            p.close()
        server.terminate()
        try:
            server.wait(5)
        except subprocess.TimeoutExpired:
            server.kill()
        log("closed")


if __name__ == "__main__":
    sys.exit(main())
