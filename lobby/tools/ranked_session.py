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
    python lobby/tools/ranked_session.py --exe <t5dr.exe> --persistent --attacks --ingame-pick \\
        --pick1 jin:rp --pick2 lil:lk                                # picked on the game's select screen

--ingame-pick: both clients announce the in-game select (docs/RANKED.md "Character select in the
game"); with the real game, --pick1/--pick2 give each player's picks per pick round (comma-separated,
the last one repeats; tools/pick_flow_test.py's scenarios: <char>:<lp|rp|lk|rk>, random, timeout,
late<s>:<char>:<button>), pressed through the game's PS3_PAD_FILE.

Ranked sets (docs/RANKED.md "Ranked sets"): both clients announce them (as the launcher does; --no-bo3:
not), so a ranked pairing is best of 3 -- only game 1 is picked in the game, games 2 and 3 start by
themselves after the countdown with game 1's fighters and costumes. --plan 1,2,1: who wins each game (that
player's game attacks through T5_NET_PADFILE while the fight runs, the other stands still; "-" = both
still), the last entry repeats -- e.g. a 2-1 set.

With --exe both instances open minimized (PS3_WINDOW_BACKGROUND=1), muted (PS3_AUDIO_MUTE=1), at
below-normal priority, no pads or keyboard unless --input; every game started here is killed at the end.
The local lobby lets two accounts on 127.0.0.1 play ranked (T5L_RANKED_SAME_IP=1) and has no PC-speed or
pair-cooldown limits. <out>/events.json: every lobby event and report per player (tools/pick_report.py).
"""
import argparse
import json
import os
import random
import re
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
ROOT = os.path.dirname(LOBBY)
sys.path.insert(0, LOBBY)

from t5lobby import ranks  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.match_driver import MatchDriver  # noqa: E402

GAME_ENV = {"PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
            "PS3_AUDIO_MUTE": "1"}
BELOW_NORMAL = 0x00004000


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
               T5L_RESULT_TIMEOUT=str(a.result_timeout), T5L_RECONNECT_GRACE="10", T5L_ROUNDS=str(a.rounds),
               # two accounts on one PC: ranked between them counts here (lobby hardening refuses it by default),
               # no PC-speed gate (two games and other work share this PC), no pause before the next pairing,
               # no status port (another local lobby may hold 7780)
               T5L_RANKED_SAME_IP="1", T5L_MIN_FPS="0", T5L_WARN_FPS="0", T5L_PAIR_COOLDOWN="0", T5L_STATUS_PORT="0",
               T5L_SET_NEXT_SECONDS=str(a.set_next))
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
                                         stdin=subprocess.DEVNULL, startupinfo=si,
                                         creationflags=BELOW_NORMAL if minimized and os.name == "nt" else 0)

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
        self.client = LobbyClient(addr, build, auto_ready=True, ingame_pick=a.ingame_pick, sets=not a.no_bo3)
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
        self.padfile = os.path.join(self.dir, "netpad.txt")      # --plan: this player's attacks (T5_NET_PADFILE)
        open(self.padfile, "w").close()
        self.attacking = False
        self.role = None
        self.games_started = 0
        self.rnd = random.Random(11 + idx)

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
        if a.exe and a.attacks and not a.plan and "T5_NET_SCRIPT" not in full and role in ("host", "join"):
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
            if a.plan:
                full["T5_NET_PADFILE"] = self.padfile
            if not a.input:
                full.update({"T5_NET_LOCALPAD": "0", "PAD_NO_KEYBOARD": "1"})
            if a.ingame_pick and not a.input:
                # the picks on the select screen: this player's pad file, pressed by a PickPlayer
                full["PS3_PAD_FILE"] = os.path.join(self.dir, f"pad{n}.txt")
                full["T5_DF_TRACE"] = "1"
                open(full["PS3_PAD_FILE"], "w").close()
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
        if a.exe and full.get("PS3_PAD_FILE"):
            specs = (a.pick1 if self.idx == 1 else a.pick2).split(",")
            PickPlayer(g, full["PS3_PAD_FILE"], specs, self.name).start()
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
                s = ev.get("set") or {}
                self.role = "host" if ev["slot"] == 0 else "join"
                plan = self.a.plan.split(",") if self.a.plan else []
                self.attacking = bool(plan) and plan[min(self.games_started, len(plan) - 1)].strip() == str(self.idx)
                self.games_started += 1
                print(f"  [{self.name}] match_start {ev['match']}: path {ev['path']}, delay {ev['delay']}, "
                      f"{f.get('p1')} vs {f.get('p2')} on {f.get('stage')}{' (continued)' if ev.get('continue') else ''}"
                      + (f", pick {f['pick']} s" if f.get("pick") else "")
                      + (f", buttons {f['buttons']}" if f.get("buttons") else "")
                      + (f", set game {s.get('number')} of best {s.get('best_of')} {s.get('wins')}" if s.get("rated") else "")
                      + (", attacks" if self.attacking else ", stands still" if plan else ""), flush=True)
            elif t == "match_result":
                r = ev.get("rating") or {}
                print(f"  [{self.name}] result {ev['status']}{' (' + ev['reason'] + ')' if ev.get('reason') else ''}: "
                      f"winner {ev['winner']} score {ev['score']}"
                      + (f", rating {r['before']['r']:.0f} -> {r['after']['r']:.0f}, rank "
                         f"{ranks.label(r['rank_before'])} -> {ranks.label(r['rank_after'])}"
                         f"{' [' + r['event'] + ']' if r.get('event') else ''}" if r else ""), flush=True)
            elif t == "set_end":
                print(f"  [{self.name}] set_end {ev.get('status')}: {ev.get('result')} {ev.get('wins')} in {ev.get('games')} "
                      f"games{' (' + str(ev.get('outcome_reason')) + ')' if ev.get('outcome_reason') else ''}", flush=True)
            elif t in ("notice", "match_cancel", "rematch"):
                print(f"  [{self.name}] {t}: {ev.get('msg') or ev.get('reason') or ev.get('state')}", flush=True)
        for n in self.driver.poll():
            if n["kind"] == "status":
                print(f"  [{self.name}] {n['text']}", flush=True)

    def results(self):
        return [e for e in self.events if e["t"] == "match_result"]

    def set_ends(self):
        return [e for e in self.events if e["t"] == "set_end"]

    def rated(self):
        """The pairing being played is a rated set (best of 3)."""
        starts = [e for e in self.events if e["t"] == "match_start"]
        return bool(starts) and bool((starts[-1].get("set") or {}).get("rated"))

    def bot(self):
        """--plan: the planned winner attacks while the fight runs; the other player stands still."""
        if not self.a.exe or not self.a.plan or not self.attacking or not self.driver.game_running():
            return
        try:
            with open(self.driver.status_path) as f:
                st = json.load(f)
        except (OSError, ValueError, TypeError):
            return
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

    def close(self):
        self.driver.close()
        for g in self.games:
            g.stop()
        self.client.close()


class PickPlayer(threading.Thread):
    """Plays this player's in-game picks: every time the game's select screen comes up for a pick
    (its log says so), the next scenario through tools/pick_flow_test.py's Picker."""

    def __init__(self, game, pad_path, specs, name):
        super().__init__(daemon=True)
        self.g, self.pad_path, self.specs, self.name = game, pad_path, specs, name

    # what pick_flow_test.Picker needs of a game
    def log_since(self, pos):
        try:
            with open(self.g.log_path, "rb") as f:
                f.seek(pos)
                return f.read().decode("utf-8", "replace")
        except OSError:
            return ""

    def pad(self, text):
        for _ in range(100):
            try:
                with open(self.pad_path, "w") as f:
                    f.write(text)
                return
            except PermissionError:
                time.sleep(0.002)

    def press(self, buttons, hold=0.08, gap=0.17):
        self.pad(buttons)
        time.sleep(hold)
        self.pad("")
        time.sleep(gap)

    def run(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from pick_flow_test import Picker
        pos, k = 0, 0
        while self.g.running():
            text = self.log_since(pos)
            m = re.search(r"in-game select: player \d picks on the select screen", text)
            if not m:
                time.sleep(0.2)
                continue
            start = pos + len(text[:m.start()].encode("utf-8"))
            spec = self.specs[min(k, len(self.specs) - 1)]
            k += 1
            print(f"  [{self.name}] select screen: pick {spec}", flush=True)
            pk = Picker(self, spec, start, time.time() + 120)
            pk.run()
            if pk.note:
                print(f"  [{self.name}] pick: {pk.note}", flush=True)
            pos = start + 1


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
    ap.add_argument("--ingame-pick", action="store_true", help="both clients offer the in-game select")
    ap.add_argument("--queue", choices=["ranked", "quick", "room"], default="ranked",
                    help="how the two find each other: the ranked or quick queue, or a lobby room (rematches in it)")
    ap.add_argument("--room-ranked", action="store_true", help="--queue room: a ranked room")
    ap.add_argument("--sets", type=int, default=1, help="pairings in a row (--matches each); after a set both "
                                                       "queue again: the next opponent, a new netplay session")
    ap.add_argument("--fresh-p2", action="store_true", help="--sets: player 2's game is closed before every new "
                                                            "pairing (a fresh game against a persistent one)")
    ap.add_argument("--pick1", default="timeout", help="real game, --ingame-pick: player 1's picks")
    ap.add_argument("--pick2", default="timeout", help="real game, --ingame-pick: player 2's picks")
    ap.add_argument("--no-bo3", action="store_true", help="the clients do not announce ranked sets (per-game rating)")
    ap.add_argument("--set-next", type=float, default=6.0, help="server: seconds to a ranked set's next game")
    ap.add_argument("--plan", default="", help="real game: the winner per game, 1 or 2 (- = nobody attacks), "
                                               "comma-separated, the last repeats (T5_NET_PADFILE bot)")
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
        if a.queue == "room":
            # a lobby room: the first player opens it, the second joins (two members: a ready check)
            room = players[0].client.create_room("ranked_session", ranked=a.room_ranked)
            players[1].client.join_room(room["id"])
        else:
            for p in players:
                (p.client.quick_match if a.queue == "quick" else p.client.ranked_match)()
        t_end = time.time() + a.seconds
        total = a.matches * a.sets
        set_no = 1
        while time.time() < t_end:
            for p in players:
                p.pump()
                p.bot()
            done = [len(p.results()) for p in players]
            rated = any(p.rated() for p in players)
            if rated:
                # a rated set ends by itself (2 wins): the pairing is over when both saw set_end
                pairing_over = min(len(p.set_ends()) for p in players) >= set_no
            else:
                pairing_over = min(done) >= a.matches * set_no
            if pairing_over and set_no >= a.sets:
                break
            if not rated and min(done) >= total:
                break
            if pairing_over:
                # the set is over: both leave it and meet again as a new pairing (a new netplay
                # session in the running games, as for the next opponent); --fresh-p2: player 2's
                # game is closed first, so a fresh game meets a persistent one
                set_no += 1
                for p in players:
                    last = p.results()[-1]["match"]
                    if rated:
                        continue                # the rated set has ended: nothing to leave
                    try:
                        p.client.rematch(last, False)
                    except Exception as e:      # noqa: BLE001 -- the set may have ended already
                        print(f"  [{p.name}] leave the set: {e}", flush=True)
                if a.fresh_p2:
                    print(f"  [{players[1].name}] closing the game: a fresh one meets the next opponent", flush=True)
                    players[1].driver.stop_game()
                time.sleep(2.0)
                for p in players:
                    p.driver.auto_rematch = a.matches - 1
                    p.driver.rematch_sent.clear()
                    (p.client.quick_match if a.queue == "quick" else p.client.ranked_match)()
                print(f"--- set {set_no}: a new pairing", flush=True)
                continue
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
        with open(os.path.join(a.out, "events.json"), "w") as f:
            json.dump({p.name: {"idx": p.idx, "events": p.events, "reported": p.driver.history,
                                "games": [g.log_path for g in p.games]} for p in players}, f, indent=1, default=str)
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
