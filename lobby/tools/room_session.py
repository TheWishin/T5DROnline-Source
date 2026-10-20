#!/usr/bin/env python3
"""A private community room end to end on one PC (docs/ONLINE.md "Rooms"): a local lobby server (its own process and
database), N players (default 3), the first creates a room for N locked with a password (or an invite code), the
others join with it -- one tries a wrong password first and is refused -- and the players take turns, each through
the launcher's glue (t5lobby.match_driver.MatchDriver, as the Online tab runs it) with a stub game in persistent mode
(lobby/tools/stub_game.py: a game's winner comes from the match's shared seed).

    python lobby/tools/room_session.py --out <dir>                                    # 3 players, winner stays
    python lobby/tools/room_session.py --out <dir> --players 4 --rotation queue --lock code --games 8

Checks: the wrong password is refused and nobody gets in without it; every room match is confirmed from both stub
games' result files; the matches follow the room's rule in order (winner stays: the loser goes to the back of the
line; queue: the player who was at the table longer goes to the back) starting from the line in join order; every player plays; no rematch vote is
offered (the room starts the next match by itself); the password never shows up in the server's log or the database.
Exit code 0 = all of that.
"""
import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time

# Every game of the session talks over 127.0.0.1 (no Windows Firewall prompt; docs/NETPLAY.md "Bind address").
os.environ.setdefault("T5_NET_BIND", "127.0.0.1")

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
sys.path.insert(0, LOBBY)
sys.path.insert(0, HERE)

from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.match_driver import MatchDriver  # noqa: E402
from t5lobby.proto import LobbyError  # noqa: E402
from set_session import ProcGame, free_port  # noqa: E402

PASSWORD = "Kuma Panda Night"
T0 = time.time()
LOGF = None


def log(msg):
    line = f"[{time.time() - T0:7.1f}s] {msg}"
    print(line, flush=True)
    if LOGF:
        LOGF.write(line + "\n")
        LOGF.flush()


def start_server(a):
    tcp, udp, udp2 = free_port(), free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    env = dict(os.environ, T5L_DB=os.path.join(a.out, "lobby.db"), T5L_LOG_LEVEL="INFO", PYTHONPATH=LOBBY,
               T5L_SCRYPT_N=str(1 << 12), T5L_MIN_MATCH_SECONDS="0", T5L_RESULT_TIMEOUT="60", T5L_ROUNDS="1",
               T5L_ROOM_NEXT_SECONDS=str(a.next_seconds), T5L_STATUS_PORT="0", T5L_RECONNECT_GRACE="20",
               T5L_MAX_PER_IP="80", T5L_CONN_BURST="100")
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


class Player:
    def __init__(self, a, addr, build, idx, name):
        self.a, self.idx, self.name = a, idx, name
        self.dir = os.path.abspath(os.path.join(a.out, f"p{idx + 1}"))
        os.makedirs(self.dir, exist_ok=True)
        self.client = LobbyClient(addr, build, auto_ready=True, sets=True)
        self.client.connect()
        self.client.login_guest(name)
        self.games = []
        self.results = []              # match_result events
        self.offers = 0                # results that offered a rematch vote (never in a community room)
        self.driver = MatchDriver(self.client, self.launch, self.dir, mode="persistent", ask_manual=False)

    def launch(self, env):
        n = len(self.games) + 1
        full = dict(os.environ)
        full.update(env)
        full.setdefault("T5_STUB_SECONDS", str(self.a.stub_seconds))
        g = ProcGame([sys.executable, os.path.join(HERE, "stub_game.py")], full, self.dir,
                     os.path.join(self.dir, f"game{n}.log"), real=False)
        self.games.append(g)
        log(f"{self.name}: game {n} started (pid {g.proc.pid})")
        return g

    def pump(self):
        while True:
            ev = self.client.next_event(0)
            if ev is None:
                break
            self.driver.on_event(ev)
            t = ev["t"]
            if t == "match_start":
                log(f"{self.name}: match {ev['match']} vs {(ev.get('opponent') or {}).get('name')} P{ev['slot'] + 1}")
            elif t == "match_result":
                self.results.append(ev)
                if ev.get("rematch_window"):
                    self.offers += 1
                log(f"{self.name}: result {ev['status']}, winner P{(ev.get('winner') or 0) + 1}")
            elif t in ("notice", "match_cancel"):
                log(f"{self.name}: {t}: {ev.get('msg') or ev.get('reason')}")
        for n in self.driver.poll():
            if n["kind"] == "status":
                log(f"{self.name}: [driver] {n['text']}")

    def close(self):
        try:
            self.driver.close()
        finally:
            for g in self.games:
                g.stop()
            self.client.close()


def expected_pairs(rows, line, rotation):
    """The pairs the room's rule gives, from the line in join order and each match's result (rooms.py)."""
    line = list(line)
    out = []
    for p1, p2, winner, status in rows:
        out.append((line[0], line[1]))
        players = (p1, p2)
        if rotation == "winner":
            stay = players[winner] if status == "confirmed" and winner is not None else None
        else:
            stay = p2                                  # (everyone in turn: P1 leaves the table, P2 plays on)
        for q in players:
            if q != stay and q in line:
                line.remove(q)
                line.append(q)
        if stay is not None:
            line.remove(stay)
            line.insert(0, stay)
    return out


def main():
    global LOGF
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--players", type=int, default=3)
    ap.add_argument("--games", type=int, default=6, help="room matches to play")
    ap.add_argument("--rotation", choices=["winner", "queue"], default="winner")
    ap.add_argument("--lock", choices=["password", "code"], default="password")
    ap.add_argument("--next-seconds", type=float, default=2.0, help="server: pause between a room's matches")
    ap.add_argument("--stub-seconds", type=float, default=1.0, help="stub games: one game's length")
    ap.add_argument("--seconds", type=float, default=600.0, help="give up after this long")
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    LOGF = open(os.path.join(a.out, "harness.log"), "a", encoding="utf-8")
    log(f"=== room session: {a.players} players, a private room ({a.lock}), {a.rotation} rotation, {a.games} matches")
    build = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "room-session", "demo")
    names = [f"Roomie{i + 1}" for i in range(a.players)]
    server, addr = start_server(a)
    log(f"lobby server on {addr}")
    players = []
    ok = True
    try:
        for i, n in enumerate(names):
            players.append(Player(a, addr, build, i, n))
        host = players[0].client
        room = host.create_room("Session room", size=a.players, rotation=a.rotation, private=a.lock,
                                password=PASSWORD if a.lock == "password" else None)
        code = host.room_code
        log(f"room {room['id']}: {room['size']} players, {room['rotation']}, locked ({room['lock']})")
        # the door: no key, a wrong key -> refused
        intruder = players[1].client
        for wrong in (None, "not the password"):
            try:
                if a.lock == "password":
                    intruder.join_room(room["id"], password=wrong)
                else:
                    intruder.join_room(code="ABCD-EFGH-JKMN" if wrong else None, room_id=room["id"])
                log("a join without the right key got in  <-- NOT OK")
                ok = False
            except LobbyError as e:
                log(f"{intruder.me['name']}: join with {'no' if wrong is None else 'a wrong'} key refused: {e.code} "
                    f"({e.msg})")
        for p in players[1:]:
            if a.lock == "password":
                p.client.join_room(room["id"], password=PASSWORD)
            else:
                p.client.join_room(code=code)
            log(f"{p.name} joined")
        t_end = time.time() + a.seconds
        while time.time() < t_end:
            for p in players:
                p.pump()
            if len({ev["match"] for p in players for ev in p.results}) >= a.games:
                break
            time.sleep(0.1)
        for _ in range(10):
            for p in players:
                p.pump()
            time.sleep(0.2)
        db = sqlite3.connect(os.path.join(a.out, "lobby.db"))
        rows = db.execute("SELECT id, p1_name, p2_name, winner, status, origin, reports FROM matches "
                          "WHERE origin = 'room' AND ended IS NOT NULL ORDER BY started").fetchall()[:a.games]
        db.close()
        played = [(p1, p2, w, st) for _mid, p1, p2, w, st, _o, _r in rows]
        log(f"--- {len(rows)} room match(es)")
        bad = []
        for mid, p1, p2, w, st, _o, rep in rows:
            reps = [r for r in json.loads(rep or "[]") if r]
            good = st == "confirmed" and len(reps) == 2 and all(r["source"] == "game" for r in reps)
            log(f"  {mid}: {p1} vs {p2}: {st}, winner {(p1, p2)[w] if w is not None else '-'}, reports "
                f"{[r['source'] for r in reps]}{'' if good else '  <-- NOT OK'}")
            if not good:
                bad.append(mid)
        want = expected_pairs(played, names, a.rotation)
        got = [(p1, p2) for p1, p2, _w, _s in played]
        log(f"pairs: {got}")
        log(f"the room's rule ({a.rotation}): {want} -> {'OK' if got == want else 'DIFFERENT'}")
        everyone = {n for pair in got for n in pair}
        log(f"players who played: {sorted(everyone)}")
        offers = sum(p.offers for p in players)
        log(f"rematch votes offered: {offers}")
        secret_seen = False
        for fn in ("server.log", "lobby.db", "harness.log"):
            try:
                with open(os.path.join(a.out, fn), "rb") as f:
                    data = f.read()
            except OSError:
                continue
            for secret in ([PASSWORD] if a.lock == "password" else [code or "-"]):
                if secret.encode("utf-8") in data or secret.replace("-", "").encode() in data:
                    log(f"the room's secret is in {fn}  <-- NOT OK")
                    secret_seen = True
        ok &= (len(rows) >= a.games and not bad and got[:len(want)] == want and everyone == set(names)
               and offers == 0 and not secret_seen)
        log("ROOM SESSION OK" if ok else "SOMETHING DIFFERED")
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
