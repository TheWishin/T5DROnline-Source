#!/usr/bin/env python3
"""Two players on one PC, paired through the lobby, then handed to the game.

    python lobby/tools/two_players.py                       # stub game (no build needed)
    python lobby/tools/two_players.py --exe <t5dr.exe with netplay> [--seconds 60] [--relay]

1. starts a lobby server on localhost (or uses --server),
2. logs in two guests, queues both for a quick match (auto-accepting the ready check),
3. waits until hole punching (or the relay with --relay) has connected them,
4. prints the exact environment each game instance gets, then
5. starts two game instances with it -- t5dr.exe (needs the netplay branch's
   src/netplay) or, without --exe, tools/stub_game.py, which performs the same
   handshake as the netplay layer -- and
6. reports the result file of each game from both sides and prints
   the lobby's verdict.

Game windows open minimized (PS3_WINDOW_BACKGROUND=1). Input: P1 = XInput pad 0,
P2 = XInput pad 1, keyboard = whichever game window has the focus; --no-input
turns all of it off (scripted runs). Every instance is killed after --seconds.
"""
import argparse
import os
import re
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
ROOT = os.path.dirname(LOBBY)
sys.path.insert(0, LOBBY)

from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.handover import read_result_file  # noqa: E402

GAME_ENV = {"PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1"}


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(relay):
    tcp, udp, udp2 = free_port(), free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_DGRAM)
    env = dict(os.environ, T5L_DB=":memory:", T5L_LOG_LEVEL="INFO", PYTHONPATH=LOBBY,
               T5L_FORCE_RELAY="1" if relay else "0",
               T5L_MIN_MATCH_SECONDS="0")      # the stub's "match" lasts a second
    p = subprocess.Popen([sys.executable, "-m", "t5lobby.server", "--host", "127.0.0.1", "--port", str(tcp),
                          "--udp-port", str(udp), "--udp-port2", str(udp2)], env=env, cwd=LOBBY,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    line = p.stdout.readline()
    if "t5lobby:" not in line:
        p.kill()
        sys.exit("lobby server did not start: " + line)
    return p, f"127.0.0.1:{tcp}"


def build_info(a):
    if a.build_out:
        return BuildInfo.from_out_dir(a.build_out)
    return BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "two-players-demo", "demo")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", help="t5dr.exe built with the netplay layer; without it a stub game runs")
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"), help="the game's VFS root")
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "two_players"), help="working dirs and logs")
    ap.add_argument("--seconds", type=float, default=60.0, help="kill the games after this long")
    ap.add_argument("--server", help="use this lobby server instead of starting one")
    ap.add_argument("--relay", action="store_true", help="force the relay path (local server only)")
    ap.add_argument("--build-out", help="take the build id from this build (<out>/game, <out>/build)")
    ap.add_argument("--no-input", action="store_true", help="no pads, no keyboard (scripted runs)")
    ap.add_argument("--env", action="append", default=[], help="extra NAME=VALUE for both games")
    a = ap.parse_args()

    if a.exe and not os.path.exists(os.path.join(a.vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")):
        sys.exit(f"no game under --vfs {a.vfs} (expected PS3_GAME/USRDIR/EBOOT.elf)")
    server_proc = None
    clients = []
    try:
        if a.server:
            addr = a.server
        else:
            server_proc, addr = start_server(a.relay)
            print(f"lobby server on {addr}{' (relay forced)' if a.relay else ''}")
        procs = play(a, addr, clients)
    finally:
        for c in clients:
            c.close()
        if server_proc is not None:
            server_proc.terminate()
            try:
                out = server_proc.communicate(timeout=5)[0]
                print("\n--- lobby server log\n" + "\n".join("   " + ln for ln in out.splitlines()[-12:]))
            except subprocess.TimeoutExpired:
                server_proc.kill()
    if a.exe:
        return 0
    return 0 if procs and all(p.returncode == 0 for p in procs) else 1




def play(a, addr, clients):
    """Pair two guests, start both games, report the result. -> the game processes."""
    procs, logs = [], []
    try:
        build = build_info(a)
        for name in ("Kazuya", "Jin"):
            c = LobbyClient(addr, build, auto_ready=True)
            c.connect()
            c.login_guest(name)
            clients.append(c)
        for c in clients:
            c.quick_match()
        tickets = {}
        for c in clients:
            while True:
                ev = c.next_event(25)
                if ev is None:
                    sys.exit("no match within 25 s")
                if ev["t"] == "nat_status":
                    print(f"  {c.me['name']}: {ev['text']}")
                elif ev["t"] == "match_cancel":
                    sys.exit(f"match cancelled: {ev['reason']}")
                elif ev["t"] == "match_start":
                    tickets[c] = ev["ticket"]
                    break
        order = sorted(clients, key=lambda c: tickets[c].slot)
        for c in order:
            t = tickets[c]
            print(f"\n{c.me['name']} (P{t.slot + 1}, {t.role}): {t.summary()}")
            for k, v in t.game_env().items():
                print(f"    {k}={v}")

        os.makedirs(a.out, exist_ok=True)
        extra = dict(kv.split("=", 1) for kv in a.env)
        for c in order:
            t = tickets[c]
            d = os.path.abspath(os.path.join(a.out, f"p{t.slot + 1}"))
            os.makedirs(d, exist_ok=True)
            env = dict(os.environ)
            env.update(t.game_env(result_file=os.path.join(d, "result.json")))
            if a.exe:
                vfs = os.path.abspath(a.vfs)
                env.update(GAME_ENV)
                env["PS3_VFS_ROOT"] = vfs.replace("\\", "/")
                env["PS3_HDD0_ROOT"] = os.path.join(vfs, "dev_hdd0").replace("\\", "/")
                env["PS3_TITLE"] = f"T5DR two players: P{t.slot + 1}"
                env["T5_NET_LOG"] = os.path.join(d, "frames.log")
                if a.no_input:
                    # no local devices at all (netplay reads port 1 through the runtime's controls)
                    env["T5_NET_LOCALPAD"] = "0"
                    env["PAD_NO_KEYBOARD"] = "1"
                cmd = [os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")]
                si = None
                if os.name == "nt":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 7          # SW_SHOWMINNOACTIVE
            else:
                cmd = [sys.executable, os.path.join(HERE, "stub_game.py")]
                si = None
            env.update(extra)
            log = os.path.join(d, "game.log")
            with open(log, "w") as lf:
                procs.append(subprocess.Popen(cmd, cwd=d, env=env, stdout=lf, stderr=subprocess.STDOUT,
                                              stdin=subprocess.DEVNULL, startupinfo=si))
            logs.append(log)
            print(f"started P{t.slot + 1} pid {procs[-1].pid}, log {log}")

        t_end = time.time() + (a.seconds if a.exe else 30)
        while time.time() < t_end and any(p.poll() is None for p in procs):
            time.sleep(0.5)
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
        for p in procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                pass

    pat = re.compile(r"\[(netplay|stub \w+)\]")
    for log in logs:
        print(f"\n--- {log}")
        with open(log, errors="replace") as f:
            lines = [ln.rstrip() for ln in f if pat.search(ln)]
        for ln in lines[:12] + (["    ..."] + lines[-4:] if len(lines) > 16 else lines[12:]):
            print("   " + ln)

    # Result reporting: each side reports what its game wrote to T5_NET_RESULT_FILE (the stub and
    # t5dr.exe with netplay both write it at the end of a match).
    reported = 0
    for c in clients:
        res = read_result_file(os.path.join(a.out, f"p{tickets[c].slot + 1}", "result.json"))
        if res is None and not a.exe and all(p.returncode == 0 for p in procs):
            res = (0, [3, 1])
        if res is not None:
            c.report_result(*res)
            reported += 1
    if reported:
        ev = clients[0].next_event(10, ("match_result",))
        w = (ev or {}).get("winner")
        print(f"\nlobby verdict: {ev['status'] if ev else 'none'}, winner {'P%d' % (w + 1) if w is not None else '-'}")
    else:
        print("\nno result reported (the game wrote no T5_NET_RESULT_FILE)")
    return procs


if __name__ == "__main__":
    sys.exit(main())
