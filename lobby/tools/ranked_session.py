#!/usr/bin/env python3
"""Two ranked players on one PC, end to end, through the same glue the launcher uses
(t5lobby.match_driver.MatchDriver):

    lobby server -> register/log in two accounts -> pick characters -> ranked queue ->
    ready check -> NAT punch (or relay) -> both games start with T5_NET_* / T5_FIGHT / T5_HUD_* ->
    the games write their result files -> both launchers report -> the lobby reconciles,
    updates Glicko-2 and the rank tiers -> rematches inside the running games -> profile,
    match history and leaderboard.

    python lobby/tools/ranked_session.py                         # stub games, 3 matches (1 + 2 rematches)
    python lobby/tools/ranked_session.py --matches 2 --fail-p2 crash
    python lobby/tools/ranked_session.py --persistent            # stub games in persistent (T5_CTL_DIR) mode
    python lobby/tools/ranked_session.py --exe <t5dr.exe> --seconds 420 \\
        --env-host T5_NET_SCRIPT=@... --env-join T5_NET_SCRIPT=@...   # the real game, scripted input

With --exe both instances open minimized (PS3_WINDOW_BACKGROUND=1), no pads or keyboard
unless --input; every game started here is killed at the end.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
ROOT = os.path.dirname(LOBBY)
sys.path.insert(0, LOBBY)

from t5lobby import ranks  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.match_driver import MatchDriver  # noqa: E402

GAME_ENV = {"PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1"}


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(a, db):
    tcp, udp, udp2 = free_port(), free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    env = dict(os.environ, T5L_DB=db, T5L_LOG_LEVEL="INFO", PYTHONPATH=LOBBY,
               T5L_FORCE_RELAY="1" if a.relay else "0", T5L_SCRYPT_N=str(1 << 12),
               T5L_PLACEMENT=str(a.placement), T5L_MIN_MATCH_SECONDS=str(a.min_seconds),
               T5L_RESULT_TIMEOUT=str(a.result_timeout), T5L_RECONNECT_GRACE="10", T5L_ROUNDS=str(a.rounds))
    log = open(os.path.join(a.out, "server.log"), "w")
    p = subprocess.Popen([sys.executable, "-m", "t5lobby.server", "--host", "127.0.0.1", "--port", str(tcp),
                          "--udp-port", str(udp), "--udp-port2", str(udp2)], env=env, cwd=LOBBY,
                         stdout=log, stderr=subprocess.STDOUT, text=True)
    t_end = time.time() + 10
    while time.time() < t_end:
        try:
            socket.create_connection(("127.0.0.1", tcp), 0.5).close()
            return p, f"127.0.0.1:{tcp}"
        except OSError:
            time.sleep(0.1)
    p.kill()
    sys.exit("lobby server did not start")


class ProcGame:
    """What the launcher's GameRun offers the driver: running(), stop(), proc, log_path."""

    def __init__(self, cmd, env, cwd, log_path, minimized):
        self.log_path = log_path
        si = None
        if minimized and os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7      # SW_SHOWMINNOACTIVE
        with open(log_path, "w") as lf:
            self.proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, startupinfo=si)

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
        self.dir = os.path.abspath(os.path.join(a.out, f"p{idx}"))
        os.makedirs(self.dir, exist_ok=True)
        self.client = LobbyClient(addr, build, auto_ready=True)
        self.client.connect()
        try:
            self.client.login(name, "password-" + name)
        except Exception:
            self.client.register(name, "password-" + name)
        self.games = []
        extra = dict(kv.split("=", 1) for kv in a.env + (a.env1 if idx == 1 else a.env2))
        mode = "persistent" if a.persistent else "process"
        self.driver = MatchDriver(self.client, self.launch, self.dir, mode=mode, extra_env=extra,
                                  ask_manual=False, auto_rematch=a.matches - 1)
        self.events = []

    def launch(self, env):
        a = self.a
        n = len(self.games) + 1
        full = dict(os.environ)
        full.update(env)
        # Scripted input belongs to the game's player slot (P1 = host drives the menus), and
        # the lobby decides who hosts.
        role = env.get("T5_NET_MODE")
        if role in ("host", "join"):
            full.update(dict(kv.split("=", 1) for kv in (a.env_host if role == "host" else a.env_join)))
        log = os.path.join(self.dir, f"game{n}.log")
        if a.exe and a.attacks and "T5_NET_SCRIPT" not in full and role in ("host", "join"):
            ev, f = [], 120
            while f < 60000:      # P1: square + right, P2: triangle + left (like the direct-fight tests)
                if role == "host":
                    ev += [f"{f} 4 0x8000", f"{f + 20} 10 0x20"]
                else:
                    ev += [f"{f + 7} 4 0x1000", f"{f + 25} 10 0x80"]
                f += 40
            sp = os.path.join(self.dir, f"attacks{n}.txt")
            with open(sp, "w") as fp:
                fp.write("\n".join(ev) + "\n")
            full["T5_NET_SCRIPT"] = sp
        if a.exe:
            vfs = os.path.abspath(a.vfs)
            full.update(GAME_ENV)
            full["PS3_VFS_ROOT"] = vfs.replace("\\", "/")
            full["PS3_HDD0_ROOT"] = os.path.join(vfs, "dev_hdd0").replace("\\", "/")
            full["PS3_TITLE"] = f"T5DR ranked session: {self.name}"
            full["T5_NET_LOG"] = os.path.join(self.dir, f"frames{n}.log")
            if not a.input:
                full.update({"T5_NET_LOCALPAD": "0", "PAD_NO_KEYBOARD": "1"})
            cmd = [os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")]
        else:
            if self.idx == 2 and a.fail_p2 and n == 1:
                full["T5_STUB_FAIL"] = a.fail_p2
            full.setdefault("T5_STUB_SECONDS", str(a.stub_seconds))
            full.setdefault("T5_STUB_MATCHES", str(a.matches))
            full.setdefault("T5_STUB_GAP", "3")
            full.setdefault("T5_STUB_LINGER", "30")
            cmd = [sys.executable, os.path.join(HERE, "stub_game.py")]
        g = ProcGame(cmd, full, self.dir, log, minimized=bool(a.exe))
        self.games.append(g)
        print(f"  [{self.name}] game {n} started (pid {g.proc.pid}): "
              + " ".join(f"{k}={env[k]}" for k in sorted(env) if k.startswith(("T5_FIGHT", "T5_HUD", "T5_NET_MODE",
                                                                                "T5_NET_DELAY", "T5_CTL"))),
              flush=True)
        return g

    def pump(self):
        while True:
            ev = self.client.next_event(0)
            if ev is None:
                break
            self.events.append(ev)
            self.driver.on_event(ev)
            t = ev["t"]
            if t == "match_found":
                print(f"  [{self.name}] match found: {ev['opponent']['name']} ({ranks.label(ev['opponent'])}), "
                      f"{'ranked' if ev['ranked'] else 'unranked'}, origin {ev['origin']}", flush=True)
            elif t == "match_start":
                f = ev.get("fight") or {}
                print(f"  [{self.name}] match_start {ev['match']}: path {ev['path']}, delay {ev['delay']}, "
                      f"{f.get('p1')} vs {f.get('p2')} on {f.get('stage')}{' (continued)' if ev.get('continue') else ''}",
                      flush=True)
            elif t == "match_result":
                r = ev.get("rating") or {}
                print(f"  [{self.name}] result {ev['status']}{' (' + ev['reason'] + ')' if ev.get('reason') else ''}: "
                      f"winner {ev['winner']} score {ev['score']}"
                      + (f", rating {r['before']['r']:.0f} -> {r['after']['r']:.0f}, rank "
                         f"{ranks.label(r['rank_before'])} -> {ranks.label(r['rank_after'])}"
                         f"{' [' + r['event'] + ']' if r.get('event') else ''}" if r else ""), flush=True)
            elif t in ("notice", "match_cancel", "rematch"):
                print(f"  [{self.name}] {t}: {ev.get('msg') or ev.get('reason') or ev.get('state')}", flush=True)
        for n in self.driver.poll():
            if n["kind"] == "status":
                print(f"  [{self.name}] {n['text']}", flush=True)

    def results(self):
        return [e for e in self.events if e["t"] == "match_result"]

    def close(self):
        self.driver.close()
        for g in self.games:
            g.stop()
        self.client.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", help="t5dr.exe with netplay; without it the stub game runs")
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "ranked_session"))
    ap.add_argument("--server", help="use this lobby server (accounts must not exist or have the tool's passwords)")
    ap.add_argument("--db", help="server database (default: <out>/lobby.db, kept between runs)")
    ap.add_argument("--matches", type=int, default=3, help="matches to play (the first + rematches)")
    ap.add_argument("--seconds", type=float, default=180.0, help="give up after this long")
    ap.add_argument("--stub-seconds", type=float, default=35.0, help="stub: length of one match")
    ap.add_argument("--min-seconds", type=float, default=30.0, help="server: minimum match length")
    ap.add_argument("--placement", type=int, default=2, help="server: placement matches")
    ap.add_argument("--rounds", type=int, default=3, help="server: rounds to win (T5_FIGHT)")
    ap.add_argument("--attacks", action="store_true",
                    help="real game: both players attack (T5_NET_SCRIPT from lockstep frame 0 = fight start)")
    ap.add_argument("--result-timeout", type=float, default=30.0)
    ap.add_argument("--relay", action="store_true", help="force the relay path (local server only)")
    ap.add_argument("--persistent", action="store_true", help="persistent game (control channel) mode")
    ap.add_argument("--fail-p2", choices=["crash", "quit", "vanish"], help="stub: P2's first game fails mid-match")
    ap.add_argument("--names", default="Kazuya,Heihachi")
    ap.add_argument("--chars", default="kazuya,heihachi")
    ap.add_argument("--input", action="store_true", help="real game: allow pads/keyboard")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for both games")
    ap.add_argument("--env1", action="append", default=[], help="NAME=VALUE for player 1's game")
    ap.add_argument("--env2", action="append", default=[], help="NAME=VALUE for player 2's game")
    ap.add_argument("--env-host", action="append", default=[], help="NAME=VALUE for the hosting game (P1)")
    ap.add_argument("--env-join", action="append", default=[], help="NAME=VALUE for the joining game (P2)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    build = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "ranked-session", "demo")
    names, chars = a.names.split(","), a.chars.split(",")
    server = None
    players = []
    try:
        if a.server:
            addr = a.server
        else:
            server, addr = start_server(a, a.db or os.path.join(os.path.abspath(a.out), "lobby.db"))
            print(f"lobby server on {addr}")
        for i in (1, 2):
            players.append(Player(a, addr, build, i, names[i - 1], chars[i - 1]))
            me = players[-1].client.me
            print(f"{me['name']}: {ranks.label(me)}, rating {me['rating']} +/- {me['rd']}")
        for p in players:
            p.client.set_char(p.char)
            p.client.ranked_match()
        t_end = time.time() + a.seconds
        while time.time() < t_end:
            for p in players:
                p.pump()
            done = [len(p.results()) for p in players]
            if min(done) >= a.matches:
                break
            if all(p.results() and not p.results()[-1].get("rematch_window") for p in players) and \
                    all(not p.driver.game_running() for p in players):
                break
            time.sleep(0.1)
        for p in players:
            p.pump()
        print("\n--- after the session")
        for p in players:
            prof = p.client.profile()
            print(f"{prof['name']}: {ranks.label(prof)} (peak {prof['peak_rank']}), rating {prof['rating']} +/- "
                  f"{prof['rd']}, record {prof['record']}, main {prof['main']}, place {prof['place']}")
            for h in prof["history"]:
                print(f"    {h['result']:>4} vs {h['opponent']:<10} {h['you_char']} vs {h['opp_char']} "
                      f"on {h['stage']}, score {h['score']}, {h['status']}"
                      f"{' (' + h['reason'] + ')' if h['reason'] else ''}, delta {h['delta']}")
        print("leaderboard:", json.dumps([(r["place"], r["name"], r["rank"], r["rating"]) for r in
                                          players[0].client.leaderboard()]))
        for p in players:
            print(f"{p.name} reported: {p.driver.history}")
        return 0 if all(len(p.results()) >= 1 for p in players) else 1
    finally:
        for p in players:
            p.close()
        if server is not None:
            server.terminate()
            try:
                server.wait(5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    sys.exit(main())
