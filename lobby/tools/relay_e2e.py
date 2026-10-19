#!/usr/bin/env python3
"""Regional relays end to end on this PC: a central lobby, two relay-only nodes, simulated round trips.

    python lobby/tools/relay_e2e.py [--scenarios best,dead,old] [--exe t5dr.exe --vfs game/vfs] [-v]

Every server is its own process, started the way a host starts it: the central lobby (`run.py server`,
T5L_FORCE_RELAY=1 so that every match needs a relay, T5L_RELAYS = a relays.json with two nodes) and two
nodes (`run.py relay --secret-file ...`). Two players log in with the real client library. Between each
player and each relay -- the central server's own one included -- sits a UDP delay proxy (one per pair, one
upstream socket per player socket, so a relay sees each player as its own endpoint, as through a home
router). The round trips (ms):

                 player A   player B   sum
    main (ours)     150        150     300      the central server, far from both (Nuremberg from California)
    usw              20        140     160      close to A only
    usc              60         60     120      in between: the smallest sum, so it must be chosen

Scenarios:
    best   both players are new: the match must go through usc, play through it (stub games, or t5dr.exe with
           --exe) and end with a confirmed result; the measured round trip of the path must be ~120 ms and
           usc's own counters must show the games' packets
    dead   usc is killed first: the central server must mark it down within T5L_RELAY_DEAD_SECONDS and the next
           match must take usw (160 ms), the next best
    old    player B is the newest release tag's client (git archive; 1.1.0): it cannot use a regional relay,
           so the match must take the central server's own relay and still play through

Exit code 0 when every scenario passed. Writes nothing outside a temporary folder (--keep keeps it).
"""
import argparse
import heapq
import io
import json
import os
import selectors
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
ROOT = os.path.dirname(LOBBY)
sys.path.insert(0, LOBBY)
sys.path.insert(0, HERE)
os.environ["T5_PORTMAP"] = "0"         # never ask this PC's router for anything

from t5lobby import proto, relayctl  # noqa: E402
from t5lobby.buildid import BuildInfo  # noqa: E402
from t5lobby.client import LobbyClient  # noqa: E402
from t5lobby.handover import read_result_file  # noqa: E402

BUILD = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "0123456789abcdef", "relay-e2e")
RTT = {"main": (150, 150), "usw": (20, 140), "usc": (60, 60)}
NAMES = {"usw": "Oregon (US West)", "usc": "Texas (US Central)"}


# ============================================================================ the simulated network
class UdpDelay(threading.Thread):
    """A UDP proxy that adds `rtt_ms / 2` each way: players send to `addr`, the proxy sends on to `target` from
    an upstream socket of each player's own (the target sees one endpoint per player socket) and back."""

    def __init__(self, target, rtt_ms, name=""):
        super().__init__(daemon=True, name=f"udp-delay {name}")
        self.target = tuple(target)
        self.one_way = rtt_ms / 2000.0
        self.sel = selectors.DefaultSelector()
        self.front = self._sock()
        self.sel.register(self.front, selectors.EVENT_READ, None)
        self.up = {}                    # player address -> upstream socket
        self.heap = []
        self.seq = 0
        self.stop_flag = False
        self.stats = {"up": 0, "down": 0}

    @staticmethod
    def _sock():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        proto.disable_udp_connreset(s)
        s.setblocking(False)
        return s

    @property
    def addr(self):
        return self.front.getsockname()

    def _later(self, sock, data, dst):
        self.seq += 1
        heapq.heappush(self.heap, (time.perf_counter() + self.one_way, self.seq, sock, data, dst))

    def run(self):
        while not self.stop_flag:
            timeout = 0.02 if not self.heap else max(0.0, min(0.02, self.heap[0][0] - time.perf_counter()))
            for key, _ev in self.sel.select(timeout):
                sock = key.fileobj
                while True:
                    try:
                        data, src = sock.recvfrom(4096)
                    except (BlockingIOError, InterruptedError):
                        break
                    except OSError:
                        break
                    if sock is self.front:
                        up = self.up.get(src)
                        if up is None:
                            up = self.up[src] = self._sock()
                            self.sel.register(up, selectors.EVENT_READ, src)
                        self.stats["up"] += 1
                        self._later(up, data, self.target)
                    else:
                        self.stats["down"] += 1
                        self._later(self.front, data, key.data)
            now = time.perf_counter()
            while self.heap and self.heap[0][0] <= now:
                _t, _s, sock, data, dst = heapq.heappop(self.heap)
                try:
                    sock.sendto(data, dst)
                except OSError:
                    pass

    def close(self):
        self.stop_flag = True
        self.join(2)
        for s in [self.front, *self.up.values()]:
            s.close()


def routed(base):
    """A LobbyClient class (of this tree or an older one) whose relays go through the player's delay proxies."""
    class Routed(base):
        routes = {}

        def relay_address(self, relay):
            r = self.routes.get(relay.get("id"))
            return r if r is not None else base.relay_address(self, relay)
    return Routed


# ============================================================================ processes
def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def http_json(port, path="/status", timeout=2.0):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class Proc:
    def __init__(self, name, cmd, env, log_dir):
        self.name = name
        self.log = os.path.join(log_dir, f"{name}.log")
        self.lf = open(self.log, "w", encoding="utf-8")
        self.p = subprocess.Popen(cmd, cwd=LOBBY, env=env, stdout=self.lf, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL)

    def stop(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(5)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait(5)
        self.lf.close()

    def tail(self, n=15):
        try:
            with open(self.log, encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()[-n:]
        except OSError:
            return []


class World:
    """Central lobby + relay nodes + delay proxies, all on 127.0.0.1."""

    def __init__(self, tmp, verbose=False, dead_seconds=4.0):
        self.tmp = tmp
        self.verbose = verbose
        self.procs = {}
        self.proxies = []
        self.nodes = {}             # id -> {"udp": port, "status": port}
        env = dict(os.environ, PYTHONPATH=LOBBY, PYTHONDONTWRITEBYTECODE="1", T5_PORTMAP="0")
        env.pop("T5L_RELAYS", None)
        self.env = env
        relays = []
        for rid in ("usw", "usc"):
            sf = os.path.join(tmp, f"relay-{rid}.secret")
            relayctl.write_secret(sf)
            udp, st = free_port(socket.SOCK_DGRAM), free_port()
            self.nodes[rid] = {"udp": udp, "status": st, "secret": sf}
            self.procs[rid] = Proc(rid, [sys.executable, "run.py", "relay", "--secret-file", sf, "--id", rid,
                                         "--host", "127.0.0.1", "--udp-port", str(udp), "--status-port", str(st),
                                         "--central", "127.0.0.1"],
                                   dict(env, T5L_LOG_LEVEL="DEBUG" if verbose else "INFO"), tmp)
            relays.append({"id": rid, "name": NAMES[rid], "host": "127.0.0.1", "port": udp,
                           "secret_file": os.path.basename(sf)})
        rj = os.path.join(tmp, "relays.json")
        with open(rj, "w", encoding="utf-8") as f:
            json.dump({"format": "t5dr-relays/1", "relays": relays}, f, indent=1)
        self.tcp, self.udp, udp2, self.status = (free_port(), free_port(socket.SOCK_DGRAM),
                                                 free_port(socket.SOCK_DGRAM), free_port())
        self.procs["central"] = Proc("central", [
            sys.executable, "run.py", "server", "--host", "127.0.0.1", "--port", str(self.tcp),
            "--udp-port", str(self.udp), "--udp-port2", str(udp2)],
            dict(env, T5L_DB=":memory:", T5L_FORCE_RELAY="1", T5L_MIN_MATCH_SECONDS="0", T5L_RELAYS=rj,
                 T5L_RELAY_CHECK_SECONDS="0.5", T5L_RELAY_DEAD_SECONDS=str(dead_seconds),
                 T5L_STATUS_PORT=str(self.status), T5L_LOG_LEVEL="INFO", T5L_RANKED_SAME_IP="1",
                 T5L_BLIND_READY="0", T5L_PAIR_COOLDOWN="0"), tmp)
        self.addr = f"127.0.0.1:{self.tcp}"

    def targets(self):
        return {"main": ("127.0.0.1", self.udp), **{rid: ("127.0.0.1", n["udp"]) for rid, n in self.nodes.items()}}

    def routes_for(self, player):
        """Delay proxies for player 0 (A) or 1 (B): {relay id: proxy address}."""
        out = {}
        for rid, target in self.targets().items():
            px = UdpDelay(target, RTT[rid][player], f"{rid}/{'AB'[player]}")
            px.start()
            self.proxies.append(px)
            out[rid] = px.addr
        return out

    def central_status(self):
        return http_json(self.status)

    def node_status(self, rid):
        return http_json(self.nodes[rid]["status"])

    def wait(self, pred, timeout, what):
        t_end = time.monotonic() + timeout
        last = None
        while time.monotonic() < t_end:
            try:
                if pred():
                    return
            except (OSError, ValueError, KeyError) as e:
                last = e
            time.sleep(0.2)
        raise AssertionError(f"timeout: {what}" + (f" ({last})" if last else ""))

    def up(self, ids):
        def ok():
            st = {r["id"]: r for r in self.central_status()["relays"]}
            return all(st.get(i, {}).get("alive") for i in ids)
        self.wait(ok, 20, f"relays {ids} up at the central server")

    def stop(self):
        for px in self.proxies:
            px.close()
        for p in self.procs.values():
            p.stop()


# ============================================================================ one match
def play_match(world, clients, a, out_dir, expect_relay, expect_rtt):
    for c in clients:
        c.quick_match()
    starts = {}
    t_end = time.monotonic() + 40
    for c in clients:
        while c not in starts:
            ev = c.next_event(max(0.1, t_end - time.monotonic()))
            if ev is None:
                raise AssertionError("no match_start within 40 s")
            if ev["t"] == "nat_status" and a.verbose:
                print(f"    {c.me['name']}: {ev['text']}")
            elif ev["t"] == "match_cancel":
                raise AssertionError(f"match cancelled: {ev.get('reason')}")
            elif ev["t"] == "match_start":
                starts[c] = ev
    evs = list(starts.values())
    chosen = [(ev.get("relay") or {}).get("id", "main") for ev in evs]
    rtt = evs[0]["rtt_ms"]
    print(f"  match {evs[0]['match']}: relay {chosen}, path {evs[0]['path']}, measured round trip "
          f"{rtt:.0f} ms (expected ~{expect_rtt})")
    for c in clients:
        if getattr(c, "relay_rtts", None):
            print(f"    {c.me['name']} measured {c.relay_rtts} (+ main {c.server_rtt:.0f})")
    if chosen != [expect_relay, expect_relay]:
        raise AssertionError(f"relay {chosen}, expected {expect_relay}")
    if not expect_rtt * 0.8 - 5 < rtt < expect_rtt * 1.35 + 15:
        raise AssertionError(f"round trip {rtt:.0f} ms through {expect_relay}, expected ~{expect_rtt}")
    # ---- the games
    procs, dirs = [], []
    order = sorted(clients, key=lambda c: starts[c]["slot"])
    for c in order:
        tk = starts[c]["ticket"]
        d = os.path.join(out_dir, f"p{tk.slot + 1}")
        os.makedirs(d, exist_ok=True)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.update(tk.game_env(result_file=os.path.join(d, "result.json")))
        if a.exe:
            vfs = os.path.abspath(a.vfs)
            env.update(PS3_GCM_TICKER_PUMP="1", RSX_LIVE_DRAW="1", PS3_VERBOSE="0", PS3_WINDOW_BACKGROUND="1",
                       PS3_AUDIO_MUTE="1", T5_NET_LOCALPAD="0", PAD_NO_KEYBOARD="1",
                       PS3_VFS_ROOT=vfs.replace("\\", "/"),
                       PS3_HDD0_ROOT=os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
                       T5_FIGHT="0,1,0,1", PS3_TITLE=f"relay e2e P{tk.slot + 1}")
            cmd = [os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")]
        else:
            env.update(T5_STUB_SECONDS=str(a.seconds))
            cmd = [sys.executable, os.path.join(HERE, "stub_game.py")]
        lf = open(os.path.join(d, "game.log"), "w", encoding="utf-8")
        procs.append((subprocess.Popen(cmd, cwd=d, env=env, stdout=lf, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL), lf))
        dirs.append(d)
    t_end = time.monotonic() + (a.game_seconds if a.exe else 30 + a.seconds)
    while time.monotonic() < t_end and any(p.poll() is None for p, _lf in procs):
        time.sleep(0.25)
    for p, lf in procs:
        if p.poll() is None:
            p.kill()
        p.wait(10)
        lf.close()
    logs = []
    for d in dirs:
        with open(os.path.join(d, "game.log"), encoding="utf-8", errors="replace") as f:
            logs.append(f.read())
    for i, text in enumerate(logs):
        lines = [ln for ln in text.splitlines() if "connected" in ln or "mismatch" in ln or "over" in ln
                 or "peer lost" in ln]
        print(f"    P{i + 1} game: " + " | ".join(ln.strip()[:90] for ln in lines[:4]))
    if not all("connected" in text for text in logs):
        raise AssertionError("the games did not connect through the relay")
    # ---- results
    for c in order:
        res = read_result_file(os.path.join(dirs[order.index(c)], "result.json"))
        if res is None:
            raise AssertionError(f"no result file from {c.me['name']}'s game")
        c.report_result(*res)
    ev = order[0].next_event(15, ("match_result",))
    if ev is None:
        raise AssertionError("no match_result")
    print(f"    lobby verdict: {ev['status']}, score {ev.get('score')}")
    if ev["status"] != "confirmed":
        raise AssertionError(f"result {ev['status']}")
    for c in order[1:]:
        c.next_event(5, ("match_result",))
    return evs[0]


def login(world, cls, name, player, extra=None):
    c = cls(world.addr, BUILD, auto_ready=True, **(extra or {}))
    c.routes = world.routes_for(player)
    c.connect()
    c.login_guest(name)
    return c


def wait_rtts(c, ids, timeout=15):
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        if all(i in (c.relay_rtts or {}) for i in ids):
            return
        time.sleep(0.1)
    raise AssertionError(f"{c.me['name']} did not measure {ids}: {c.relay_rtts}")


# ============================================================================ scenarios
def scenario_best(world, a, tmp):
    world.up(["usw", "usc"])
    A = login(world, routed(LobbyClient), "Alice", 0)
    B = login(world, routed(LobbyClient), "Bob", 1)
    try:
        for c in (A, B):
            wait_rtts(c, ["usw", "usc"])
        before = {rid: world.node_status(rid)["relay"]["packets_total"] for rid in world.nodes}
        play_match(world, [A, B], a, os.path.join(tmp, "best"), "usc", 120)
        after = {rid: world.node_status(rid)["relay"]["packets_total"] for rid in world.nodes}
        moved = {rid: after[rid] - before[rid] for rid in after}
        print(f"    packets relayed by the nodes during the match: {moved}")
        if moved["usc"] < 100 or moved["usw"] != 0:
            raise AssertionError(f"usc should carry the match alone: {moved}")
        st = {r["id"]: r for r in world.central_status()["relays"]}
        print(f"    admin view: " + "; ".join(f"{r['id']} {'up' if r['alive'] else 'DOWN'}, {r['sessions']} sessions, "
                                             f"{r['kbit_s']} kbit/s, last seen {r['last_seen_s']} s ago"
                                             for r in st.values()))
    finally:
        A.close()
        B.close()


def scenario_dead(world, a, tmp):
    world.up(["usw", "usc"])
    # Both players measured usc (the best) while it ran; then it goes away.
    A = login(world, routed(LobbyClient), "Carol", 0)
    B = login(world, routed(LobbyClient), "Dave", 1)
    try:
        for c in (A, B):
            wait_rtts(c, ["usw", "usc"])
        t0 = time.monotonic()
        world.procs["usc"].stop()
        world.wait(lambda: not {r["id"]: r for r in world.central_status()["relays"]}["usc"]["alive"], 30,
                   "the central server marks usc down")
        print(f"  usc stopped: marked down after {time.monotonic() - t0:.1f} s")
        play_match(world, [A, B], a, os.path.join(tmp, "dead"), "usw", 160)
    finally:
        A.close()
        B.close()


def old_client_class(tmp, ref):
    """LobbyClient of the git tag `ref` (lobby/t5lobby), imported under another package name."""
    r = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", ref, "lobby/t5lobby"], capture_output=True,
                       timeout=60)
    if r.returncode != 0:
        raise AssertionError(f"git archive {ref}: {r.stderr.decode(errors='replace').strip()}")
    base = os.path.join(tmp, "old")
    tarfile.open(fileobj=io.BytesIO(r.stdout)).extractall(base, filter="data")
    import natsim
    natsim.load_pkg("t5lobby_old", os.path.join(base, "lobby", "t5lobby"))
    import importlib
    old = importlib.import_module("t5lobby_old.client").LobbyClient
    # (the old client has no relay_address: it always uses the lobby server's own address -- route that too)
    return old


def scenario_old(world, a, tmp):
    ids = [i for i in ("usw", "usc") if world.procs[i].p.poll() is None]
    world.up(ids)
    Old = old_client_class(tmp, a.old_ref)
    A = login(world, routed(LobbyClient), "Erin", 0)
    B = Old(world.addr, BUILD, auto_ready=True)
    B.connect()
    B.login_guest("Frank")
    try:
        wait_rtts(A, ids)
        # (the old client talks to the central server's relay without a delay proxy: 150 + ~0)
        play_match(world, [A, B], a, os.path.join(tmp, "old"), "main", 150)
    finally:
        A.close()
        B.close()


SCENARIOS = {"best": scenario_best, "dead": scenario_dead, "old": scenario_old}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenarios", default="best,dead,old")
    ap.add_argument("--seconds", type=float, default=3.0, help="length of a stub game's match")
    ap.add_argument("--exe", help="t5dr.exe: real games instead of the stub")
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--game-seconds", type=float, default=150.0, help="real games: give them this long")
    ap.add_argument("--old-ref", default="v1.1.0", help="git tag of the old client (scenario old)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary folder (logs)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    names = [s.strip() for s in a.scenarios.split(",") if s.strip()]
    tmp = tempfile.mkdtemp(prefix="relay-e2e-")
    world = World(tmp, a.verbose)
    failed = []
    try:
        for name in names:
            print(f"== {name}")
            t0 = time.monotonic()
            try:
                SCENARIOS[name](world, a, tmp)
                print(f"   PASS ({time.monotonic() - t0:.1f} s)")
            except AssertionError as e:
                failed.append(name)
                print(f"   FAIL: {e}")
    finally:
        world.stop()
        if failed or a.verbose:
            for p in world.procs.values():
                print(f"--- {p.name} log (end)")
                for ln in p.tail():
                    print("   " + ln)
        if a.keep:
            print(f"logs in {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print("RELAY E2E " + ("OK" if not failed else "FAILED: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
