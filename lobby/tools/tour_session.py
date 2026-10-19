#!/usr/bin/env python3
"""A whole tournament end to end on one PC (docs/TOURNAMENTS.md): a local lobby server (its own process and
database), N accounts, the first one organizes, everyone signs up, and each player's launcher glue
(t5lobby.match_driver.MatchDriver, as the Online tab runs it) accepts the calls and plays the sets with a game.

    python lobby/tools/tour_session.py --out <dir>                                  # 8 players, double, stub games
    python lobby/tools/tour_session.py --out <dir> --players 4 --format single --set-wins 3
    python lobby/tools/tour_session.py --out <dir> --players 2 --exe build/cmake/t5dr.exe

Stub games (lobby/tools/stub_game.py, persistent mode) pick each game's winner from the match's shared seed. With
the real game (--exe) the better seed of each set is the only player who presses anything (a bot writes attacks to
that game's T5_NET_PADFILE while the fight runs), so the bracket goes by seed; both games run minimized
(PS3_WINDOW_BACKGROUND=1), muted, below normal priority, without pads or keyboard, and every game started here is
killed at the end. Use few players with the real game: each one is a game instance on this PC.

Checks: the tournament finishes; every set was decided by its games (no walkover, no no-show, no organizer); every
game a lobby match confirmed from both games' result files; the standings and the champion. Prints the bracket
and the time from each call to the set's first FIGHT START. Exit code 0 = all of that.
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
sys.path.insert(0, HERE)

from t5lobby import tour_text  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.match_driver import MatchDriver  # noqa: E402
from t5lobby.proto import LobbyError  # noqa: E402
from set_session import GAME_ENV, ProcGame, free_port  # noqa: E402

T0 = time.time()
LOGF = None


def log(msg):
    line = f"[{time.time() - T0:7.1f}s] {msg}"
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + "\n")
        LOGF.flush()


def make_accounts(a, names):
    """The players' accounts, straight into the new database (the server lets one address register only a few)."""
    from t5lobby.server.store import Store, hash_password
    st = Store(os.path.join(a.out, "lobby.db"))
    for n in names:
        if st.account(n) is None:
            st.create_account(n, hash_password("password-" + n, n=1 << 12))
    st.close()


def start_server(a):
    tcp, udp, udp2 = free_port(), free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    env = dict(os.environ, T5L_DB=os.path.join(a.out, "lobby.db"), T5L_LOG_LEVEL="INFO", PYTHONPATH=LOBBY,
               T5L_SCRYPT_N=str(1 << 12), T5L_MIN_MATCH_SECONDS=str(a.min_seconds), T5L_RESULT_TIMEOUT="60",
               T5L_ROUNDS=str(a.rounds), T5L_SET_NEXT_SECONDS=str(a.next_seconds), T5L_STATUS_PORT="0",
               T5L_RECONNECT_GRACE="20", T5L_TOUR_NOSHOW="120", T5L_TOUR_TICK="0.2", T5L_MAX_PER_IP="80",
               T5L_CONN_BURST="100", T5L_RANKED_SAME_IP="1")
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


def self_exe(a):
    return bool(a.exe)


def close_windows(pid):
    """WM_CLOSE to every visible top-level window of process `pid` (Alt+F4 / the X button). -> how many."""
    if os.name != "nt":
        return 0
    import ctypes
    import ctypes.wintypes as wt
    u32 = ctypes.WinDLL("user32")
    found = []
    proto = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _lp):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            found.append(h)
        return True
    u32.EnumWindows(proto(cb), 0)
    for h in found:
        u32.PostMessageW(h, 0x0010, 0, 0)
    return len(found)


class Player:
    def __init__(self, a, addr, build, idx, name):
        self.a, self.idx, self.name = a, idx, name
        self.dir = os.path.abspath(os.path.join(a.out, f"p{idx + 1}"))
        os.makedirs(self.dir, exist_ok=True)
        self.client = LobbyClient(addr, build, auto_ready=True, sets=True, tournaments=True)
        self.client.connect()
        self.client.login(name, "password-" + name)          # (the accounts: make_accounts, before the server)
        self.games = []
        self.events = []
        self.padfile = os.path.join(self.dir, "pad.txt")
        open(self.padfile, "w").close()
        self.rnd = random.Random(11 + idx)
        self.attacking = False
        self.role = None
        self.seed = None
        self.opp_seed = None
        self.called_at = {}            # set id -> time of its call
        self.call_to_fight = []        # seconds from a call to the set's first FIGHT START
        self.waiting_fight = None
        self.quit_armed = None         # (match id, fight base) when this player quits the running game (--quit)
        self.quit_fight_t = None
        self.quits = []                # match ids this player quit
        self.driver = MatchDriver(self.client, self.launch, self.dir, mode="persistent", ask_manual=False,
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
            full["PS3_TITLE"] = f"T5DR tournament session: {self.name}"
            full["T5_NET_PADFILE"] = self.padfile
            cmd = [os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")]
        else:
            full.setdefault("T5_STUB_SECONDS", str(a.stub_seconds))
            cmd = [sys.executable, os.path.join(HERE, "stub_game.py")]
        g = ProcGame(cmd, full, self.dir, logp, real=bool(a.exe))
        self.games.append(g)
        log(f"{self.name}: game {n} started (pid {g.proc.pid})")
        return g

    def status(self):
        try:
            with open(self.driver.status_path) as f:
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
            if t == "tour_call":
                sid = ev["set"]["id"]
                if not ev["accepted"][0]:
                    self.called_at.setdefault(sid, time.time())
                    log(f"{self.name}: called: {tour_text.round_label(ev['set'])} ({sid}) vs "
                        f"{ev['opponent'].get('name')}, best of {ev['best_of']}"
                        + (f", goes on at {ev['score'][0]}-{ev['score'][1]}" if any(ev["score"]) else ""))
                    try:
                        self.client.tour_accept(ev["tournament"]["id"], sid)
                    except LobbyError as e:
                        log(f"{self.name}: accept: {e.msg}")
            elif t == "match_start":
                s = ev.get("set") or {}
                ts = s.get("tournament") or {}
                self.role = "host" if ev["slot"] == 0 else "join"
                # the better seed attacks; the seeds come with the bracket (asked now if the loop has not yet)
                if not any(x.get("seed") for x in self.a.entrants) and getattr(self.a, "tid", None):
                    try:
                        self.a.entrants = self.client.tour_get(self.a.tid)["entrants"]
                    except LobbyError:
                        pass
                seeds = {x["name"]: x["seed"] for x in self.a.entrants}
                mine = seeds.get(self.name) or 99
                opp = seeds.get((ev.get("opponent") or {}).get("name")) or 99
                self.attacking = mine < opp
                sid = ts.get("set")
                base = int((self.status() or {}).get("match") or 0) if self.driver.game_running() else 0
                if sid in self.called_at:
                    self.waiting_fight = (sid, self.called_at.pop(sid), base)
                # --quit SET:GAME: the player who loses that game (the worse seed, who stands still) quits it mid-fight
                if self.a.quit == (sid, int(s.get("number") or 1)) and not self.attacking:
                    self.quit_armed = (ev["match"], base)
                    self.quit_fight_t = None
                log(f"{self.name}: game {s.get('number')} of set {sid} vs {(ev.get('opponent') or {}).get('name')} "
                    f"P{ev['slot'] + 1}" + (" -- attacks" if self.a.exe and self.attacking else "")
                    + (" -- will quit it" if self.quit_armed else ""))
            elif t == "match_result":
                s = ev.get("set") or {}
                self.attacking = False
                log(f"{self.name}: game result {ev['status']}{' (' + ev['reason'] + ')' if ev.get('reason') else ''}"
                    f", set {s.get('wins')}")
            elif t == "tour_notice":
                log(f"{self.name}: {tour_text.notice_text(ev)}")
            elif t in ("notice", "match_cancel", "tour_call_end"):
                log(f"{self.name}: {t}: {ev.get('msg') or ev.get('reason')}")
        for n in self.driver.poll():
            if n["kind"] == "status":
                log(f"{self.name}: [driver] {n['text']}")
        w = self.waiting_fight
        st = self.status() or {}
        if w and st.get("state") == "fight" and int(st.get("match") or 0) > w[2]:
            self.call_to_fight.append(round(time.time() - w[1], 1))
            self.waiting_fight = None
        q = self.quit_armed
        if q and st.get("state") == "fight" and int(st.get("match") or 0) > q[1]:
            if self.quit_fight_t is None:
                self.quit_fight_t = time.time()
            elif time.time() - self.quit_fight_t >= self.a.quit_after:
                self.quit_armed = None
                if self.a.exe:
                    # the real player's way: Alt+F4 / the X button -> the game ends its session as a quit (BYE to
                    # the opponent, result "quit", exit code 7) and the driver reports it
                    n = close_windows(self.driver.game.proc.pid) if self.driver.game is not None else 0
                    log(f"{self.name}: closes the game window in the fight of {q[0]} ({n} window(s))")
                    if n:
                        self.quits.append(q[0])
                else:
                    log(f"{self.name}: leaves the match {q[0]} in the fight")
                    try:
                        self.client.leave_match(q[0])
                        self.quits.append(q[0])
                    except LobbyError as e:
                        log(f"{self.name}: leave: {e.msg}")

    def bot(self):
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
        btn = self.rnd.choice([0x8000, 0x1000, 0x4000, 0x2000, 0x8000 | 0x4000, 0x40 | 0x4000, fwd | 0x1000, fwd])
        try:
            with open(self.padfile, "w") as fp:
                fp.write(f"{btn:#x} {self.rnd.randint(3, 6)}")
        except OSError:
            pass

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
    ap.add_argument("--players", type=int, default=8)
    ap.add_argument("--format", choices=["single", "double"], default="double")
    ap.add_argument("--set-wins", type=int, choices=[2, 3], default=2)
    ap.add_argument("--rounds", type=int, default=3, help="rounds to win a game (the server's T5L_ROUNDS)")
    ap.add_argument("--min-seconds", type=float, default=0.0, help="server: minimum game length")
    ap.add_argument("--next-seconds", type=float, default=3.0, help="server: countdown to a set's next game")
    ap.add_argument("--stub-seconds", type=float, default=1.0, help="stub games: one game's length")
    ap.add_argument("--seconds", type=float, default=3600.0, help="give up after this long")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for every game (every match too)")
    ap.add_argument("--quit", help="SET:GAME, e.g. W1-2:2: the loser of that game quits it mid-fight (closes the game "
                                   "window; stub games: leaves the match) -- the set must go to the other player")
    ap.add_argument("--quit-after", type=float, default=4.0, help="seconds into that fight")
    a = ap.parse_args()
    if a.quit:
        sid, _c, num = a.quit.partition(":")
        a.quit = (sid, int(num or 1))
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    LOGF = open(os.path.join(a.out, "harness.log"), "a", encoding="utf-8")
    log(f"=== tournament session: {a.players} players, {a.format} elimination, first to {a.set_wins}, "
        f"{'real game ' + a.exe if a.exe else 'stub games'}")
    build = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "tour-session", "demo")
    names = [f"Player{i + 1:02d}" for i in range(a.players)]
    make_accounts(a, names)
    server, addr = start_server(a)
    log(f"lobby server on {addr}")
    players = []
    ok = True
    try:
        for i in range(a.players):
            players.append(Player(a, addr, build, i, names[i]))
        org = players[0].client
        t = org.tour_create("Session Cup", fmt=a.format, set_wins=a.set_wins, start=time.time() + 2,
                            max_players=max(8, 1 << (max(1, a.players - 1)).bit_length()))
        for p in players:
            p.client.tour_join(t["id"])
        tid = a.tid = t["id"]
        a.entrants = []
        state, t_end, last = "signup", time.time() + a.seconds, 0.0
        while time.time() < t_end:
            for p in players:
                p.pump()
                p.bot()
            if time.time() - last >= 1.0:
                last = time.time()
                full = org.tour_get(tid)
                a.entrants = full["entrants"]
                if full["state"] != state:
                    state = full["state"]
                    log(f"tournament: {state}")
                if state in ("finished", "cancelled"):
                    break
            time.sleep(0.1)
        for _ in range(10):
            for p in players:
                p.pump()
            time.sleep(0.2)
        full = org.tour_get(tid)
        b = full.get("bracket") or {}
        info = {"format": b.get("format"), "rounds": b.get("rounds"), "losers_rounds": b.get("losers_rounds")}
        log("--- bracket")
        for s in b.get("sets") or ():
            log("  " + tour_text.set_line(s, info) + f"  [{s['id']}, {len(s.get('games') or [])} games]")
        played = [s for s in b.get("sets") or () if s["state"] == "done" and s["reason"] not in ("bye", "empty",
                                                                                                 "skipped")]
        quit_set = a.quit[0] if a.quit else None
        not_by_games = [s["id"] for s in played if s["reason"] is not None and s["id"] != quit_set]
        ok &= full["state"] == "finished" and not not_by_games
        log("standings: " + ", ".join(f"{r['place']}. {r['name']}" for r in full.get("standings") or ()))
        log(f"champion: {full.get('champion')}; sets played: {len(played)}; not decided by the games: {not_by_games}")
        rows = []
        try:
            import sqlite3
            db = sqlite3.connect(os.path.join(a.out, "lobby.db"))
            rows = db.execute("SELECT id, status, reason, reports FROM matches WHERE set_id IS NOT NULL "
                              "ORDER BY started").fetchall()
            db.close()
        except Exception as e:      # noqa: BLE001 -- the check below says it
            log(f"database: {e}")
        quitted = {m for p in players for m in p.quits}
        by_status, bad = {}, []
        for mid, st, why, rep in rows:
            by_status[st] = by_status.get(st, 0) + 1
            reps = [r for r in json.loads(rep or "[]") if r]
            if mid in quitted:
                srcs = sorted(r["source"] for r in reps)
                good = st == "forfeit" and "quit" in srcs
                log(f"  game {mid}: {st} ({why}), reports {srcs} -- the planned quit {'OK' if good else 'NOT AS PLANNED'}")
            else:
                hashes = {r.get("hash") for r in reps}
                # (the stub game writes no state hash: equal hashes are checked with the real game)
                good = (st == "confirmed" and len(reps) == 2 and all(r["source"] == "game" for r in reps)
                        and len(hashes) == 1 and (None not in hashes or not self_exe(a))
                        and not any(r.get("desync") for r in reps))
                log(f"  game {mid}: {st}{' (' + why + ')' if why else ''}, from {[r['source'] for r in reps]}, "
                    f"hashes {'equal ' + str(next(iter(hashes))) if len(hashes) == 1 else hashes}, "
                    f"desync {[r.get('desync') for r in reps]}{'' if good else '  <-- NOT OK'}")
            if not good:
                bad.append(mid)
        log(f"games: {len(rows)} {by_status}; not as expected: {bad}")
        ok &= bool(rows) and not bad
        if a.quit:
            bs = next((s for s in b.get("sets") or () if s["id"] == quit_set), None)
            quitter = next((p.name for p in players if p.quits), None)
            if bs is None or quitter is None or bs.get("winner") is None:
                log(f"the planned quit in {quit_set} did not happen")
                ok = False
            else:
                winner_name = bs["p"][bs["winner"]]
                good = bs["reason"] == "forfeit" and winner_name not in (None, quitter)
                ok &= good
                log(f"set {quit_set}: {quitter} quit game {a.quit[1]} -> {bs['reason']}, the set to {winner_name} "
                    f"(games before: {bs.get('score')}) -> {'OK' if good else 'NOT AS PLANNED'}")
        times = [x for p in players for x in p.call_to_fight]
        if times:
            log(f"call -> first FIGHT START of the set: median {sorted(times)[len(times) // 2]} s, max {max(times)} s "
                f"({len(times)} sets x players)")
        log("TOURNAMENT OK" if ok else "SOMETHING DIFFERED")
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
