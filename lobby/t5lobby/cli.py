"""Command-line lobby client: everything the launcher's Online tab does, for testing and for
playing without the launcher.

    python -m t5lobby.cli --server HOST[:PORT] --name NAME (--quick | --ranked | --room [NAME] |
                          --join ROOM | --challenge PLAYER | --wait | --list)
                          [--password-env VAR | --register-env VAR] [--build-out DIR]
                          [--game-port N] [-- COMMAND ARGS...]

Without a COMMAND it prints the game environment once the match is set up (cmd `set` lines).
With one (e.g. `-- python tools/run_game.py`) it runs it with that environment added, waits
for it to exit, reports the result from T5_NET_RESULT_FILE when the game wrote one (or the
--winner/--score given), and prints the lobby's verdict. Passwords are taken from an
environment variable, never from the command line (shell history, process lists).
"""
import argparse
import os
import subprocess
import sys
import tempfile

from . import proto
from .buildid import BuildInfo
from .client import LobbyClient
from .handover import read_result_file


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m t5lobby.cli", description=__doc__.split("\n\n")[0])
    ap.add_argument("--server", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--password-env", metavar="VAR", help="log in to an account; password in env VAR")
    ap.add_argument("--register-env", metavar="VAR", help="create an account; password in env VAR")
    ap.add_argument("--build-out", help="game build folder (<out>/game/EBOOT.elf, <out>/build/t5dr_build.json)")
    ap.add_argument("--elf-sha1", default="be80165b84e30b6334baa6d6331b9db4ffd5a6a4")
    ap.add_argument("--code-id", default="dev")
    ap.add_argument("--game-port", type=int, default=0)
    ap.add_argument("--tls-fingerprint", help="SHA-256 of the server's self-signed certificate (enables TLS)")
    ap.add_argument("--tls", action="store_true", help="TLS with a CA-signed server certificate")
    act = ap.add_mutually_exclusive_group(required=True)
    act.add_argument("--quick", action="store_true", help="quick match")
    act.add_argument("--ranked", action="store_true", help="ranked queue (accounts)")
    act.add_argument("--room", nargs="?", const="", metavar="NAME", help="open a room and wait")
    act.add_argument("--join", metavar="ROOM", help="join a room by id or name")
    act.add_argument("--challenge", metavar="PLAYER", help="challenge a player by name")
    act.add_argument("--wait", action="store_true", help="wait for (and accept) a challenge")
    act.add_argument("--list", action="store_true", help="print the lobby and exit")
    ap.add_argument("--winner", choices=("1", "2", "draw"), help="result to report if the game wrote none")
    ap.add_argument("--score", help="rounds, e.g. 3-1 (P1-P2)")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- command to run with the game environment")
    a = ap.parse_args(argv)

    build = BuildInfo.from_out_dir(a.build_out) if a.build_out else BuildInfo(a.elf_sha1, a.code_id)
    if a.build_out and not a.list and not BuildInfo.has_online(a.build_out):
        title = BuildInfo.game_title(a.build_out)
        if title and title != "NPUB30009":
            print(f"this game build is {title}, the European version: it plays offline only for now, online play "
                  "for it comes in a later update (docs/EU.md)")
        else:
            print("this game build has no online modules (a macOS build: tools/build_game.py --macos-online, "
                  "docs/MACOS_ONLINE_TEST.md)")
        return 1
    c = LobbyClient(a.server, build, auto_ready=True, game_port=a.game_port,
                    tls=a.tls, tls_fingerprint=a.tls_fingerprint, blind_ready=True)
    try:
        w = c.connect()
        print(f"connected to {w['server']} (build {build.build_id}){': ' + w['motd'] if w.get('motd') else ''}")
        if a.register_env:
            c.register(a.name, os.environ[a.register_env])
        elif a.password_env:
            c.login(a.name, os.environ[a.password_env])
        else:
            c.login_guest(a.name)
        print(f"logged in as {c.me['name']} ({'guest' if c.me['guest'] else 'rating %d' % c.me['rating']}), "
              f"server ping {c.server_rtt or 0:.0f} ms")
        c.refresh()
        snap = c.next_event(5, ("lobby_state",)) or {}
        if a.list:
            for p in snap.get("players", []):
                same = "" if p["build"] == build.build_id else "  [other build]"
                print(f"  {p['name']:<16} {p['status']:<8} {p['rating']:>5}  {p['rtt'] or '-':>6} ms{same}")
            for r in snap.get("rooms", []):
                print(f"  room {r['id']}  {r['name']!r} by {r['owner']['name']}  {r['status']}")
            return 0
        if a.quick:
            c.quick_match()
        elif a.ranked:
            c.ranked_match()
        elif a.room is not None:
            r = c.create_room(a.room or None)
            print(f"room {r['id']} open; waiting for an opponent")
        elif a.join:
            rid = next((r["id"] for r in snap.get("rooms", []) if a.join in (r["id"], r["name"])), a.join)
            c.join_room(rid)
        elif a.challenge:
            target = next((p for p in snap.get("players", []) if p["name"].lower() == a.challenge.lower()), None)
            if target is None:
                print(f"{a.challenge} is not online")
                return 1
            c.challenge(target["id"])
            print(f"challenged {target['name']}")
        else:
            print("waiting for a challenge")

        while True:
            ev = c.next_event(None)
            t = ev["t"]
            if t == "challenged" and a.wait:
                print(f"{ev['from']['name']} challenges you -- accepting")
                c.answer_challenge(ev["challenge"], True)
            elif t == "challenge_update" and ev["state"] in ("declined", "expired"):
                print(f"challenge {ev['state']}")
                return 1
            elif t == "match_found" and ev.get("blind"):
                ping = ev.get("ping") or {}
                print(f"opponent found -- ping about {ping['ms']} ms (through the server), accepting"
                      if ping.get("known") else "opponent found -- accepting")
            elif t == "match_reveal":
                print(f"opponent: {ev['opponent']['name']} ({ev['opponent']['rating']}) -- you are "
                      f"P{ev['slot'] + 1} ({ev['role']})")
            elif t == "match_found":
                print(f"opponent found: {ev['opponent']['name']} ({ev['opponent']['rating']}) -- you are "
                      f"P{ev['slot'] + 1} ({ev['role']})")
            elif t == "lag_check":
                print("lag check: " + ev["text"])
            elif t == "server_notice" and not ev.get("cleared"):
                print("server notice: " + ev["text"])
            elif t == "nat_status":
                print("  " + ev["text"])
            elif t == "match_cancel":
                print(f"match cancelled: {proto.scrub_addresses(str(ev['reason']))}")
                if not (a.quick or a.ranked or a.room is not None):
                    return 1
            elif t == "match_start":
                return play(c, ev["ticket"], a)
            elif t in ("disconnected", "kicked"):
                print(f"lobby connection lost: {proto.scrub_addresses(str(ev.get('reason')))}")
                return 1
            elif t in ("notice", "error"):
                print(f"[{ev.get('code')}] {proto.scrub_addresses(str(ev.get('msg')))}")
    except proto.LobbyError as e:
        print(f"lobby: {proto.scrub_addresses(str(e))}")       # (never an address in an error message)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        c.close()


def play(c, ticket, a):
    print(f"match {ticket.match_id}: {ticket.summary()}")
    rf = os.path.join(tempfile.gettempdir(), f"t5net-result-{ticket.match_id}.json")
    env = ticket.game_env(result_file=rf)
    cmd = [x for x in a.command if x != "--"]
    if not cmd:
        for k, v in env.items():
            print(f"set {k}={v}")
        try:
            input("Start the game with these settings; press Enter when the match is over... ")
        except EOFError:
            pass
    else:
        print("running: " + " ".join(cmd))
        rc = subprocess.call(cmd, env=dict(os.environ, **env))
        print(f"game exited with {rc}")
    res = read_result_file(rf)
    if res is None and a.winner:
        w = None if a.winner == "draw" else int(a.winner) - 1
        sc = [int(x) for x in a.score.split("-")] if a.score else None
        res = (w, sc)
    if res is None:
        print("no result to report (the game wrote none; use --winner/--score)")
        return 0
    c.report_result(res[0], res[1], match_id=ticket.match_id)
    ev = c.next_event(120, ("match_result",))
    if ev:
        chg = ev.get("rating") or {}
        print(f"result {ev['status']}: winner {'draw' if ev['winner'] is None else 'P%d' % (ev['winner'] + 1)}"
              f"{', rating %+.1f' % chg['delta'] if chg else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
