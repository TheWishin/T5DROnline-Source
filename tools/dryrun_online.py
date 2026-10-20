"""Online dry run of an UNPACKED, BUILT release: two guests on a lobby server, one quick match
(+ rematches) played by scripted/bot input in two real game instances.

It uses the install's own modules the way the launcher's Online tab does: servers.json (pinned
TLS fingerprint), BuildInfo.from_out_dir, LobbyClient, MatchDriver, run_game.game_command. Each
game gets its own working directory (two players share one PC); windows are minimized.

    <install>/python/python.exe tools/dryrun_online.py --install <install> --out DIR
        [--matches 2] [--seconds 900] [--bot live|script] [--env NAME=VALUE ...] [--check-only]
        [--mode auto|process|persistent] [--new-opponent]

--new-opponent: no rematches; after every result both players leave the set and queue again,
so every match is a new pairing (a new netplay session, as for a new opponent). With
--mode persistent (or auto with a game that understands T5_CTL_DIR) the games stay open
between them. Every match logs "Accept -> FIGHT" (the player's Accept to the game's
FIGHT START in its status file) for both players.

Guests only (DryRunA / DryRunB): it never creates accounts. The default server is the install's
lobby/servers.json default (the public one); --server 127.0.0.1:PORT uses a local one
(python lobby/run.py server). If other players with the same build are in the lobby it aborts
instead of risking a pairing with a stranger. Frames of each game are dumped with LD_FRAME_DUMP
(--shot-every). Written for the 0.1.0-preview release dry run (build/rd/REPORT.md).
"""
import argparse
import json
import os
import subprocess
import sys
import time


def _install_arg():
    for i, a in enumerate(sys.argv):
        if a == "--install" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith("--install="):
            return a.split("=", 1)[1]
    sys.exit("usage: dryrun_online.py --install <unpacked, built release folder> --out DIR [...]")


ROOT = os.path.abspath(_install_arg())
sys.path.insert(0, os.path.join(ROOT, "lobby"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "launcher"))

import core                                    # noqa: E402  (the launcher's module)
import run_game                                # noqa: E402
from t5lobby import proto, ranks, servers      # noqa: E402
from t5lobby.buildid import BuildInfo          # noqa: E402
from t5lobby.client import LobbyClient         # noqa: E402
from t5lobby.match_driver import MatchDriver   # noqa: E402

NATIVE = os.path.join(ROOT, "native")
T0 = time.time()
LOGF = None


def log(msg):
    line = f"[{time.time() - T0:7.1f}s] {msg}"
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + "\n")
        LOGF.flush()


class ProcGame:
    """Same contract as core.GameRun for the driver: running(), stop(), proc, log_path."""

    def __init__(self, cmd, env, cwd, log_path):
        self.log_path = log_path
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7        # SW_SHOWMINNOACTIVE
        with open(log_path, "w", encoding="utf-8", errors="replace") as lf:
            self.proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, startupinfo=si,
                                         creationflags=core.CREATE_NO_WINDOW)
        self.started = time.time()

    def running(self):
        return self.proc.poll() is None

    def stop(self):
        if self.running():
            core.kill_tree(self.proc.pid)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                pass


STOP = [60000]


def attack_script(path, role):
    """Both players press buttons and move at irregular gaps (the generator the repo's rollback/netplay
    tests use; they finish whole matches with it). Masks: UP 0x10 RIGHT 0x20 DOWN 0x40 LEFT 0x80
    SQUARE 0x8000 TRIANGLE 0x1000 CIRCLE 0x2000 CROSS 0x4000."""
    import random
    rnd = random.Random(11 if role == "host" else 22)
    ev, f = [], 120
    fwd = "0x20" if role == "host" else "0x80"
    while f < STOP[0]:
        btn = rnd.choice(["0x8000", "0x1000", "0x4000", "0x2000", fwd, fwd, "0x40", "0x10"])
        n = rnd.randint(2, 6)
        ev.append(f"{f} {n} {btn}")
        f += n + rnd.randint(2, 20)
    with open(path, "w") as fp:
        fp.write(chr(10).join(ev) + chr(10))
    return path


class Player:
    def __init__(self, a, entry, build, idx, name, char):
        self.a, self.idx, self.name, self.char = a, idx, name, char
        self.dir = os.path.abspath(os.path.join(a.out, f"p{idx}"))
        os.makedirs(self.dir, exist_ok=True)
        kw = entry.client_kwargs()
        self.client = LobbyClient(kw["server"], build, tls=kw["tls"], tls_fingerprint=kw["tls_fingerprint"],
                                  blind_ready=True)
        t = time.time()
        w = self.client.connect()
        log(f"{name}: connected to {w.get('server')} in {time.time() - t:.2f}s, motd={w.get('motd')!r}")
        t = time.time()
        self.client.login_guest(name)
        me = self.client.me
        log(f"{name}: guest login {time.time() - t:.2f}s -> {me.get('name')!r} guest={me.get('guest')} "
            f"server ping {self.client.server_rtt or 0:.0f} ms")
        import random
        self.rnd = random.Random(1000 + idx)
        self.games = []
        self.events = []
        game_files = [os.path.join(NATIVE, "build", "cmake", "t5dr.exe"), os.path.join(NATIVE, "build", "cmake", "t5dr_game.dll")]
        self.driver = MatchDriver(self.client, self.launch, self.dir, mode=a.mode, ask_manual=False,
                                  auto_rematch=0 if a.new_opponent else a.matches - 1, game_files=game_files,
                                  extra_env=dict(kv.split("=", 1) for kv in a.env))
        log(f"{name}: match driver mode {self.driver.mode}")
        self.t_accept = None          # when Accept was pressed for the match being set up
        self.fight_base = 0           # the status' match number before it
        self.timings = []             # Accept -> FIGHT per match

    def launch(self, env):
        n = len(self.games) + 1
        role = env.get("T5_NET_MODE") or ("persistent" if env.get("T5_CTL_DIR") else None)
        over = {"PS3_NICKNAME": self.name, "PS3_WINDOW_BACKGROUND": "1", "T5_NET_LOCALPAD": "0",
                "PAD_NO_KEYBOARD": "1"}
        over.update(env)
        over.update(dict(kv.split("=", 1) for kv in self.a.env))
        if role in ("host", "join", "persistent"):
            if self.a.bot == "script" and role != "persistent":
                over["T5_NET_SCRIPT"] = attack_script(os.path.join(self.dir, f"script{n}.txt"), role)
            else:       # live bot: presses only while the game is in the fight (see Player.bot)
                self.padfile = os.path.join(self.dir, f"pad{n}.txt")
                open(self.padfile, "w").close()
                over["T5_NET_PADFILE"] = self.padfile
                self.role = role
        over["T5_NET_LOG"] = os.path.join(self.dir, f"frames{n}.log")
        sd = os.path.join(self.dir, f"shots{n}")
        os.makedirs(sd, exist_ok=True)
        over["LD_FRAME_DUMP"] = sd                 # the game's own frame dump (no screen capture)
        over["LD_FRAME_DUMP_EVERY"] = str(self.a.shot_every)
        cmd, genv, _cwd = run_game.game_command(NATIVE, over)
        logp = os.path.join(self.dir, f"game{n}.log")
        # two players share this PC: each game gets its own working dir (./scratch, ./gamedata)
        g = ProcGame(cmd, genv, self.dir, logp)
        self.games.append(g)
        log(f"{self.name}: game {n} started pid {g.proc.pid} ({role}); env "
            + " ".join(f"{k}={env[k]}" for k in sorted(env) if k.startswith(("T5_FIGHT", "T5_NET_MODE",
                                                                              "T5_NET_DELAY", "T5_NET_PATH"))))
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
                opp = ev.get("opponent")
                log(f"{self.name}: match_found blind={ev.get('blind')} ping={ev.get('ping')} "
                    f"opp={opp and opp.get('name')} ranked={ev.get('ranked')} origin={ev.get('origin')}")
                if ev.get("ready_check") is not False:
                    time.sleep(0.5)                       # a person reads the ping, then clicks Accept
                    self.client.ready(True)
                    log(f"{self.name}: pressed Accept")
                self.t_accept = time.time()
                self.fight_base = int((self.status() or {}).get("match") or 0) if self.driver.game_running() else 0
            elif t == "match_reveal":
                log(f"{self.name}: match_reveal opp={ev['opponent']['name']} slot P{ev['slot'] + 1} {ev['role']}")
            elif t == "match_start":
                f = ev.get("fight") or {}
                log(f"{self.name}: match_start {ev['match']} path={ev['path']} delay={ev['delay']} "
                    f"{f.get('p1')} vs {f.get('p2')} stage {f.get('stage')} rounds {f.get('rounds')}"
                    f"{' (continued)' if ev.get('continue') else ''}")
            elif t == "match_result":
                log(f"{self.name}: match_result status={ev['status']} reason={ev.get('reason')} "
                    f"winner={ev['winner']} score={ev['score']} rematch_window={ev.get('rematch_window')} "
                    f"rating={ev.get('rating')}")
                if self.a.new_opponent and len(self.results()) < self.a.matches:   # (this result is in the list already)
                    # a new pairing for the next match: out of the set, back into the queue
                    try:
                        self.client.leave_set("next")
                    except Exception as e:
                        log(f"{self.name}: leave_set: {e}")
                    self.requeue_at = time.time() + 1.0
            elif t == "nat_status":
                log(f"{self.name}: nat: {ev['text']}")
            elif t in ("notice", "match_cancel", "rematch", "server_notice", "lag_check", "error", "disconnected",
                       "kicked"):
                log(f"{self.name}: {t}: {json.dumps({k: v for k, v in ev.items() if k != 't'}, default=str)[:300]}")
        for n in self.driver.poll():
            if n["kind"] == "status":
                log(f"{self.name}: [driver] {n['text']}")
            else:
                log(f"{self.name}: [driver:{n['kind']}] {json.dumps({k: v for k, v in n.items() if k not in ('t', 'kind')}, default=str)[:200]}")

    def check_timing(self):
        """Accept -> FIGHT START of this match (the status file's match counter moves past the base);
        with --new-opponent, the queue again after a result."""
        t = getattr(self, "requeue_at", None)
        if t and time.time() >= t:
            self.requeue_at = None
            self.client.quick_match()
            log(f"{self.name}: queued again (new opponent)")
        if self.t_accept is None:
            return
        s = self.status() or {}
        if s.get("state") == "fight" and int(s.get("match") or 0) > self.fight_base:
            dt = time.time() - self.t_accept
            self.timings.append(round(dt, 1))
            log(f"{self.name}: Accept -> FIGHT {dt:.1f} s (match #{s.get('match')}, driver mode {self.driver.mode})")
            self.t_accept = None

    def bot(self):
        """Press random buttons like a person would, but only while the game is in a fight."""
        import random
        pf = getattr(self, "padfile", None)
        if not pf or self.a.bot != "live":
            return
        tk = self.driver.ticket
        role = getattr(tk, "role", None) or getattr(self, "role", None)
        if role == self.a.idle:
            return
        s = self.status()
        if not s or s.get("state") != "fight" or not self.driver.game_running():
            return
        try:
            if os.path.getsize(pf) != 0:
                return
        except OSError:
            return
        rnd = self.rnd
        fwd = "0x20" if role == "host" else "0x80"
        btn = rnd.choice(["0x8000", "0x1000", "0x4000", "0x2000", fwd, fwd, "0x40", "0x10"])
        try:
            with open(pf, "w") as fp:
                fp.write(f"{btn} {rnd.randint(2, 6)}")
        except OSError:
            pass

    def results(self):
        return [e for e in self.events if e["t"] == "match_result"]

    def status(self):
        p = self.driver.status_path
        if p and os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None
        return None

    def close(self):
        try:
            self.driver.close()
        except Exception as e:
            log(f"{self.name}: driver.close: {e}")
        for g in self.games:
            g.stop()
        try:
            self.client.close()
        except Exception:
            pass


def main():
    global LOGF
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", required=True, help="unpacked and built release folder")
    ap.add_argument("--server", help="HOST:PORT[#FINGERPRINT] instead of the install's default server")
    ap.add_argument("--out", required=True)
    ap.add_argument("--matches", type=int, default=2)
    ap.add_argument("--seconds", type=float, default=900)
    ap.add_argument("--names", default="DryRunA,DryRunB")
    ap.add_argument("--chars", default="kazuya,heihachi")
    ap.add_argument("--shot-every", type=int, default=1500, help="frame dump every N flips")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for both games")
    ap.add_argument("--script-stop", type=int, default=60000, help="last lockstep frame with scripted presses")
    ap.add_argument("--bot", choices=["live", "script"], default="live")
    ap.add_argument("--idle", choices=["host", "join"], help="live bot: this role (host = P1, join = P2) never presses")
    ap.add_argument("--check-only", action="store_true", help="connect, list the lobby, leave")
    ap.add_argument("--mode", choices=["auto", "process", "persistent"], default="auto",
                    help="the match driver's game mode (auto: persistent when the game understands T5_CTL_DIR)")
    ap.add_argument("--new-opponent", action="store_true",
                    help="no rematches: every match a new pairing (leave the set, queue again)")
    a = ap.parse_args()
    STOP[0] = a.script_stop
    os.makedirs(a.out, exist_ok=True)
    LOGF = open(os.path.join(a.out, "harness.log"), "a", encoding="utf-8")
    log(f"=== online dry run, install {ROOT}")

    entries, problems = servers.load(None)          # lobby/servers.json of the install
    log(f"servers.json: {[(e.name, e.address, e.tls) for e in entries]} problems={problems}")
    entry = servers.resolve(a.server, entries) if a.server else servers.default_entry(entries)
    host = (entry.address if entry else "").rsplit(":", 1)[0].strip("[]").lower()
    if host == "localhost" or host.startswith("127."):
        # A lobby on this PC: both players and their games stay on 127.0.0.1 (the lobby client's game socket
        # and the game bind there -- no Windows Firewall prompt; docs/NETPLAY.md "Bind address"). Through a
        # real server the games bind every interface, as for players.
        os.environ.setdefault("T5_NET_BIND", "127.0.0.1")
        log(f"local lobby: T5_NET_BIND={os.environ['T5_NET_BIND']}")
    st = core.game_state(NATIVE)
    log(f"game_state: ok={st.get('ok')} {st.get('text')}")
    if not st.get("ok"):
        sys.exit(1)
    build = BuildInfo.from_out_dir(NATIVE, core.release_info().get("version", "dev"))
    log(f"build id {build.build_id} (release {build.release}, code {build.code_id})")
    names, chars = a.names.split(","), a.chars.split(",")
    players = []
    try:
        for i in (1, 2):
            players.append(Player(a, entry, build, i, names[i - 1], chars[i - 1]))
        snap = None
        players[0].client.refresh()
        snap = players[0].client.next_event(5, ("lobby_state",)) or {}
        log("lobby: " + ", ".join(f"{p['name']}({p['status']},{p['build']==build.build_id and 'same build' or 'other build'})"
                                 for p in snap.get("players", [])) + f" | queues={snap.get('queues')} rooms={len(snap.get('rooms', []))}")
        others = [p for p in snap.get("players", []) if p["name"] not in names and p["build"] == build.build_id]
        if others:
            log(f"ABORT: other players with my build are in the lobby: {[p['name'] for p in others]}")
            return 2
        if a.check_only:
            return 0
        for p in players:
            p.client.set_char(p.char)
            p.client.quick_match()
            log(f"{p.name}: quick match requested ({p.char})")
        t_end = time.time() + a.seconds
        last_status = {}
        while time.time() < t_end:
            for p in players:
                p.pump()
                p.check_timing()
                p.bot()
                s = p.status()
                key = (s or {}).get("state"), (s or {}).get("match")
                if s and last_status.get(p.idx) != key:
                    last_status[p.idx] = key
                    log(f"{p.name}: game state {s.get('state')} match#{s.get('match')} frame {s.get('frame')} "
                        f"winner {s.get('last_winner')} score {s.get('last_score')}")
            done = [len(p.results()) for p in players]
            if min(done) >= a.matches:
                log(f"all {a.matches} match result(s) in")
                break
            if any(p.games and not p.driver.game_running() and not p.results() for p in players) and \
                    time.time() - T0 > 60 and all(not p.driver.game_running() for p in players):
                log("both games are gone without a result")
                break
            time.sleep(0.2)
        for _ in range(10):
            for p in players:
                p.pump()
            time.sleep(0.3)
        for p in players:
            alive = [(g.proc.pid, g.running()) for g in p.games]
            log(f"{p.name}: game processes {alive}; reported {p.driver.history}")
            log(f"{p.name}: Accept -> FIGHT per match (s): {p.timings}")
        # profile / history as the server sees it
        for p in players:
            try:
                prof = p.client.profile()
                log(f"{p.name}: profile {json.dumps(prof, default=str)[:400]}")
            except Exception as e:
                log(f"{p.name}: profile: {e}")
        # leave the games open for a moment: do they stay up after the last result?
        time.sleep(5)
        for p in players:
            log(f"{p.name}: game still running after last result: {p.driver.game_running()}; status {p.status()}")
        return 0 if all(len(p.results()) >= 1 for p in players) else 1
    finally:
        for p in players:
            p.close()
        log("closed")


if __name__ == "__main__":
    sys.exit(main())
