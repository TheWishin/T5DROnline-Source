"""End-to-end harness: a local lobby server, players driven through the launcher's own Online tab,
real (or stub) games, a network shaper between the two games.

What is real here and what stands in (docs/SMOKE.md "End-to-end online scenarios"):

  real   the lobby server (python -m t5lobby.server, its own process, its own database, local ports
         only), the Online tab (launcher/online.py -> t5lobby.tk_tab.OnlineTab) with its LobbyClient
         and MatchDriver, the launcher's game process code (launcher/core.py GameRun, Settings,
         game_state), the game (t5dr.exe, persistent mode as players get it), the problem report
         and the updater modules
  stub   the launcher window around the tab (E2EApp: the same start_game() as t5dr_launcher.pyw's
         App, nothing else), lobby/tools/stub_game.py instead of t5dr.exe for scenarios where the
         game does not matter (decline, timeouts, pair cap ...), a UDP proxy between the two games
         for latency, loss, jitter and cut links (Shaper; the lobby's own NAT step still runs and
         the games are then pointed at the proxy -- like a router between the two PCs)

The Tk root is withdrawn and every dialog the tab could open is replaced: nothing appears on the
desktop, nothing takes the focus, the clipboard is never touched. Games open minimized
(PS3_WINDOW_BACKGROUND=1), muted (PS3_AUDIO_MUTE=1), and run at below-normal priority (inherited
from this process). Only processes started here are ever stopped; a kill-on-close job ends them
if the runner dies. The lobby server binds 127.0.0.1 and a guard refuses any other server address.
"""
import ctypes
import datetime
import gc
import heapq
import json
import os
import random
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LOBBY = os.path.join(ROOT, "lobby")
LAUNCHER = os.path.join(ROOT, "launcher")
TOOLS = os.path.join(ROOT, "tools")
for _p in (TOOLS, LAUNCHER, LOBBY):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ["T5_PAD_NAV"] = "0"              # the tab never reads this PC's controllers
os.environ.setdefault("T5DR_NO_UPDATE_CHECK", "1")

import core                                  # noqa: E402  launcher/core.py
import build_game                            # noqa: E402


def _load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


procs = _load("smoke_procs", os.path.join(TOOLS, "smoke", "procs.py"))   # (tools/smoke on sys.path would shadow modules)
from t5lobby import proto                    # noqa: E402
from t5lobby.buildid import BuildInfo        # noqa: E402

IS_WIN = os.name == "nt"
BELOW_NORMAL = 0x00004000
PUBLIC_SERVERS = ("46.224.146.6",)
LOG_LOCK = threading.Lock()
T0 = time.time()


def log(msg):
    line = f"[{time.time() - T0:8.1f}s] {msg}"
    with LOG_LOCK:
        print(line, flush=True)
        if Run.current is not None and Run.current.logf is not None:
            Run.current.logf.write(line + "\n")
            Run.current.logf.flush()


def below_normal_priority():
    """This process and everything it starts (Windows children inherit BELOW_NORMAL) at below-normal."""
    if IS_WIN:
        k32 = ctypes.windll.kernel32
        k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL)


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def find_game_root(start=ROOT):
    """The tree that holds game/vfs and game/EBOOT.elf (this clone, or the main tree above build/)."""
    d = os.path.abspath(start)
    for _ in range(6):
        if os.path.isfile(os.path.join(d, "game", "EBOOT.elf")) and os.path.isdir(os.path.join(d, "game", "vfs")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def junction(link, target):
    if os.path.exists(link):
        return
    if IS_WIN:
        subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True,
                       creationflags=core.CREATE_NO_WINDOW)
    else:
        os.symlink(target, link)


def hardlink_or_copy(src, dst):
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


# ======================================================================================= lobby server
class LobbyServer:
    """python -m t5lobby.server on 127.0.0.1, its own database; restart() keeps ports and database."""

    def __init__(self, d, env=None):
        self.dir = d
        os.makedirs(d, exist_ok=True)
        self.db = os.path.join(d, "lobby.db")
        self.log_path = os.path.join(d, "server.log")
        self.tcp = free_port()
        self.udp = free_port(socket.SOCK_DGRAM)
        self.udp2 = free_port(socket.SOCK_DGRAM)
        self.env = dict(env or {})
        self.proc = None
        self.starts = 0

    @property
    def addr(self):
        return f"127.0.0.1:{self.tcp}"

    def start(self):
        env = dict(os.environ)
        env.update({"PYTHONPATH": LOBBY, "T5L_STATUS_PORT": "0", "T5L_LOG_LEVEL": "INFO", "T5L_SCRYPT_N": str(1 << 12),
                    "T5L_CONN_RATE": "50", "T5L_CONN_BURST": "200", "T5L_MAX_PER_IP": "64", "T5L_MIN_FPS": "0",
                    # both players of a scenario are on this PC (one address): let them play ranked against each
                    # other (lobby-hardening's alt rule); the scenario ranked_same_address keeps the rule on
                    "T5L_RANKED_SAME_IP": "1"})
        env.update({k: str(v) for k, v in self.env.items()})
        lf = open(self.log_path, "a", encoding="utf-8")
        lf.write(f"--- start {self.starts + 1} {datetime.datetime.now():%H:%M:%S} env "
                 + " ".join(f"{k}={v}" for k, v in sorted(self.env.items())) + "\n")
        lf.flush()
        self.proc = subprocess.Popen([sys.executable, "-m", "t5lobby.server", "--host", "127.0.0.1", "--port",
                                      str(self.tcp), "--udp-port", str(self.udp), "--udp-port2", str(self.udp2),
                                      "--db", self.db], cwd=LOBBY, env=env, stdout=lf, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, creationflags=core.CREATE_NO_WINDOW if IS_WIN else 0)
        lf.close()
        Run.current.own(self.proc)
        self.starts += 1
        t_end = time.time() + 15
        while time.time() < t_end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"lobby server exited with {self.proc.returncode} (see {self.log_path})")
            try:
                socket.create_connection(("127.0.0.1", self.tcp), 0.5).close()
                return self
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("lobby server did not start")

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                pass

    def restart(self, down_seconds=1.0):
        self.stop()
        time.sleep(down_seconds)
        self.start()

    def log_text(self):
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""


# ======================================================================================= network shaper
class Proxy:
    """Stands between two games on this PC: A sends to `sb` (B's stand-in), the proxy forwards from
    `sa` to B; B sends to `sa`, the proxy forwards from `sb` to A. Each game sees the opponent's
    packets come from the address it was given. Delay, jitter, loss and a cut link come from the
    shaper's current settings (they may change while it runs)."""

    def __init__(self, shaper, a_port, b_port):
        self.shaper = shaper
        self.real = {"a": ("127.0.0.1", a_port), "b": ("127.0.0.1", b_port)}
        self.ip = shaper.ip                  # where the stand-ins live (127.0.0.2: "not this PC" for the firewall tests)
        self.sa = self._sock(self.ip)
        self.sb = self._sock(self.ip)
        self.ports = {a_port: self.sa.getsockname()[1], b_port: self.sb.getsockname()[1]}
        self.queue = []
        self.seq = 0
        self.stats = {"a2b": 0, "b2a": 0, "dropped": 0, "cut": 0}
        self.rnd = random.Random(a_port * 7919 + b_port)
        self.stop = False
        self.thread = threading.Thread(target=self._loop, daemon=True, name=f"proxy {a_port}<->{b_port}")
        self.thread.start()

    @staticmethod
    def _sock(ip="127.0.0.1"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((ip, 0))
        if IS_WIN:
            try:
                s.ioctl(socket.SIO_UDP_CONNRESET, False)
            except (OSError, AttributeError):
                pass
        s.setblocking(False)
        return s

    def stand_in(self, real_port):
        """The proxy port a game must send to in order to reach the game on `real_port`."""
        return self.ports[real_port]

    def _take(self, data, direction):
        sh = self.shaper
        if sh.cut:
            self.stats["cut"] += 1
            return
        if sh.loss and self.rnd.random() * 100.0 < sh.loss:
            self.stats["dropped"] += 1
            return
        one_way = sh.rtt / 2000.0
        if sh.jitter:
            one_way += self.rnd.uniform(-sh.jitter, sh.jitter) / 1000.0
        due = time.perf_counter() + max(0.0, one_way)
        if direction == "a2b":
            item = (due, self.seq, self.sa, data, self.real["b"])
        else:
            item = (due, self.seq, self.sb, data, self.real["a"])
        self.seq += 1
        heapq.heappush(self.queue, item)
        self.stats[direction] += 1

    def _loop(self):
        socks = [self.sa, self.sb]
        while not self.stop:
            now = time.perf_counter()
            while self.queue and self.queue[0][0] <= now:
                _due, _s, out, data, dst = heapq.heappop(self.queue)
                try:
                    out.sendto(data, dst)
                except OSError:
                    pass
            wait = min(0.002, max(0.0, self.queue[0][0] - now)) if self.queue else 0.002
            try:
                rd, _, _ = select.select(socks, [], [], wait)
            except OSError:
                break
            for s in rd:
                while True:
                    try:
                        data, _src = s.recvfrom(65535)
                    except (BlockingIOError, ConnectionResetError):
                        break
                    except OSError:
                        break
                    # A sends to sb (B's stand-in) -> a2b; B sends to sa -> b2a
                    self._take(data, "a2b" if s is self.sb else "b2a")

    def close(self):
        self.stop = True
        self.thread.join(2)
        for s in (self.sa, self.sb):
            try:
                s.close()
            except OSError:
                pass


_RELAY_TOOL = None


def relay_tool():
    """lobby/tools/relay_e2e.py as a module (its UdpDelay proxy, http_json); the sys.path entries it adds are
    taken back (lobby/tools first on the path would shadow modules of this runner)."""
    global _RELAY_TOOL
    if _RELAY_TOOL is None:
        saved, env = list(sys.path), os.environ.get("T5_PORTMAP")
        _RELAY_TOOL = _load("e2e_relay_tool", os.path.join(LOBBY, "tools", "relay_e2e.py"))
        sys.path[:] = saved
        if env is None:
            os.environ.pop("T5_PORTMAP", None)
        else:
            os.environ["T5_PORTMAP"] = env
    return _RELAY_TOOL


class RelayNodes:
    """Regional relay-only nodes for the scenario's lobby server (`python run.py relay`, docs/HOSTING.md "Adding a
    relay server"), each its own process with its own secret, and per player a UDP delay proxy to every relay --
    the lobby server's own one ("main") included -- like lobby/tools/relay_e2e.py: the client's relay_address()
    is pointed at the player's proxies, so each relay sees each player as its own endpoint and the round trips
    are the simulated ones. Default round trips (ms, player A / B): main 150/150, usw 20/140, usc 60/60 -- usc
    has the smallest sum and must be chosen."""

    RTT = {"main": (150, 150), "usw": (20, 140), "usc": (60, 60)}
    NAMES = {"usw": "Oregon (US West)", "usc": "Texas (US Central)"}

    def __init__(self, ctx, rtt=None):
        from t5lobby import relayctl
        self.ctx = ctx
        self.rtt = dict(rtt or self.RTT)
        self.dir = os.path.join(ctx.dir, "relays")
        os.makedirs(self.dir, exist_ok=True)
        self.nodes, self.procs, self.proxies = {}, {}, []
        relays = []
        for rid in [r for r in self.rtt if r != "main"]:
            sf = os.path.join(self.dir, f"relay-{rid}.secret")
            relayctl.write_secret(sf)
            self.nodes[rid] = {"udp": free_port(socket.SOCK_DGRAM), "status": free_port(), "secret": sf}
            relays.append({"id": rid, "name": self.NAMES.get(rid, rid), "host": "127.0.0.1",
                           "port": self.nodes[rid]["udp"], "secret_file": os.path.basename(sf)})
        self.json = os.path.join(self.dir, "relays.json")
        with open(self.json, "w", encoding="utf-8") as f:
            json.dump({"format": "t5dr-relays/1", "relays": relays}, f, indent=1)
        self.status_port = free_port()
        for rid in self.nodes:
            self.start(rid)

    def server_env(self):
        """For ctx.start_server: this relays.json, quick health checks, the status page (for the checks)."""
        return {"T5L_RELAYS": self.json, "T5L_RELAY_CHECK_SECONDS": 0.5, "T5L_RELAY_DEAD_SECONDS": 4,
                "T5L_STATUS_PORT": self.status_port}

    def start(self, rid):
        n = self.nodes[rid]
        lf = open(os.path.join(self.dir, f"{rid}.log"), "a", encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=LOBBY, T5L_LOG_LEVEL="INFO", T5_PORTMAP="0")
        env.pop("T5L_RELAYS", None)
        pr = subprocess.Popen([sys.executable, "run.py", "relay", "--secret-file", n["secret"], "--id", rid,
                               "--host", "127.0.0.1", "--udp-port", str(n["udp"]), "--status-port", str(n["status"]),
                               "--central", "127.0.0.1"], cwd=LOBBY, env=env, stdout=lf, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, creationflags=core.CREATE_NO_WINDOW if IS_WIN else 0)
        lf.close()
        Run.current.own(pr)
        self.procs[rid] = pr
        return pr

    def stop(self, rid):
        pr = self.procs.get(rid)
        if pr is not None and pr.poll() is None:
            pr.kill()
            try:
                pr.wait(10)
            except subprocess.TimeoutExpired:
                pass

    def routes(self, index):
        """Delay proxies for player `index` (0 = A, 1 = B): {relay id: proxy address}."""
        relay_e2e = relay_tool()
        targets = {"main": ("127.0.0.1", self.ctx.server.udp),
                   **{rid: ("127.0.0.1", n["udp"]) for rid, n in self.nodes.items()}}
        out = {}
        for rid, target in targets.items():
            px = relay_e2e.UdpDelay(target, self.rtt[rid][index], f"{rid}/{'AB'[index]}")
            px.start()
            self.proxies.append(px)
            out[rid] = tuple(px.addr)
        return out

    def central(self):
        """The lobby server's status page (relays: alive, sessions, kbit/s)."""
        return relay_tool().http_json(self.status_port)

    def node(self, rid):
        return relay_tool().http_json(self.nodes[rid]["status"])

    def alive(self):
        try:
            return {r["id"]: bool(r.get("alive")) for r in self.central().get("relays") or ()}
        except (OSError, ValueError):
            return {}

    def packets(self):
        """Packets each node relayed so far (None for a node that does not answer)."""
        out = {}
        for rid in self.nodes:
            try:
                out[rid] = self.node(rid)["relay"]["packets_total"]
            except (OSError, ValueError, KeyError, TypeError):
                out[rid] = None
        try:
            out["main"] = self.central()["relay"]["packets_total"]       # the lobby server's own relay
        except (OSError, ValueError, KeyError, TypeError):
            out["main"] = None
        return out

    def close(self):
        for px in self.proxies:
            try:
                px.close()
            except Exception:      # noqa: BLE001
                pass
        for rid in list(self.procs):
            self.stop(rid)


class Shaper:
    """The network between the two games. Off: the games talk directly. On: every new session is
    routed through a Proxy with the current rtt/jitter/loss; `cut` drops everything (a pulled cable).
    The lobby measured the direct path before the proxy was put in; the shaper hands the games what
    the lobby would have measured on the shaped path instead (T5_NET_RTT_MS, T5_NET_DELAY)."""

    def __init__(self):
        self.on = False
        self.rtt = 0.0
        self.jitter = 0.0
        self.loss = 0.0
        self.cut = False
        self.proxies = {}
        self.build_override = {}     # player name -> T5_NET_BUILD to hand that player's game (mismatch tests)
        # The proxy's own address: what the games see as the opponent's. 127.0.0.2 for the firewall cases --
        # T5_NET_TEST_INBOUND=block lets in nothing but 127.0.0.1 (the relay bridge), as if the opponent were on
        # another PC (every address of 127/8 is this PC; the games bind 127.0.0.1 and still reach it).
        self.ip = "127.0.0.1"

    def set(self, rtt=0.0, jitter=0.0, loss=0.0, on=True, ip="127.0.0.1"):
        self.on, self.rtt, self.jitter, self.loss, self.cut = on, float(rtt), float(jitter), float(loss), False
        if ip != self.ip:
            self.close()             # (the next session gets a proxy on the new address)
            self.ip = ip

    def describe(self):
        if not self.on:
            return "direct (no proxy)"
        return f"proxy rtt {self.rtt:g} ms, jitter +-{self.jitter:g} ms, loss {self.loss:g}%"

    def rewrite(self, player, env):
        if player.name in self.build_override:
            env["T5_NET_BUILD"] = self.build_override[player.name]
        if not self.on or env.get("T5_NET_PATH") == "relay" or not env.get("T5_NET_PEER"):
            return env
        try:
            port = int(env["T5_NET_PORT"])
            pport = int(env["T5_NET_PEER"].rsplit(":", 1)[1])
        except (KeyError, ValueError):
            return env
        key = (min(port, pport), max(port, pport))
        px = self.proxies.get(key)
        if px is None:
            px = self.proxies[key] = Proxy(self, key[0], key[1])
            log(f"shaper: proxy for ports {key[0]}<->{key[1]}: {self.describe()}")
        env["T5_NET_PEER"] = f"{px.ip}:{px.stand_in(pport)}"
        env["T5_NET_RTT_MS"] = f"{self.rtt:.1f}"
        env["T5_NET_DELAY"] = str(proto.suggest_delay(self.rtt, self.jitter))
        return env

    def stats(self, since=None):
        """Packets through the proxies (and dropped / cut), minus a former stats() result `since`."""
        out = {"a2b": 0, "b2a": 0, "dropped": 0, "cut": 0}
        for px in self.proxies.values():
            for k in out:
                out[k] += px.stats[k]
        if since:
            out = {k: v - since.get(k, 0) for k, v in out.items()}
        return out

    def close(self):
        for px in self.proxies.values():
            px.close()
        self.proxies.clear()


# ======================================================================================= games
class StubGameRun:
    """lobby/tools/stub_game.py with the GameRun interface (start/running/stop/proc/log_path/fps)."""

    def __init__(self, out, settings):
        self.out, self.settings = out, settings
        self.proc = self.log_path = self.fps = None
        self.last_lines = []
        self.started = None

    def start(self, extra_env=None, monitor_point=None):
        env = dict(os.environ)
        env.update(self.settings.env_overrides())
        env.update(extra_env or {})
        logs = os.path.join(self.out, "logs")
        os.makedirs(logs, exist_ok=True)
        self.log_path = os.path.join(logs, f"game-{datetime.datetime.now():%Y%m%d-%H%M%S}-{time.time_ns() % 10**6}.log")
        lf = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-u", os.path.join(LOBBY, "tools", "stub_game.py")], env=env,
                                     cwd=self.out, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     creationflags=core.CREATE_NO_WINDOW if IS_WIN else 0)
        lf.close()
        self.started = time.time()
        return self.proc.pid

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.running():
            core.kill_tree(self.proc.pid)


class E2EApp:
    """What the Online tab needs from the launcher (launcher/online.py's contract), with the same
    start_game() as t5dr_launcher.pyw's App: save the settings, check the build, reuse a running
    game, else core.GameRun(out, settings).start(env)."""

    def __init__(self, player):
        self.player = player
        self.settings = core.Settings(path=os.path.join(player.dir, "launcher.json"))
        self.game = None
        self.readonly = False
        self.statuses = []

    def game_state(self):
        return core.game_state(self.settings.out_dir)

    def start_game(self, env=None):
        self.settings.save()
        if not self.game_state().get("ok"):
            log(f"{self.player.name}: start_game refused: {self.game_state().get('text')}")
            return None
        if self.game and self.game.running():
            return self.game
        cls = StubGameRun if self.player.kind == "stub" else core.GameRun
        g = cls(self.settings.out_dir, self.settings)
        g.start(env)
        Run.current.own(g.proc)
        self.game = g
        self.player.games.append(g)
        log(f"{self.player.name}: game started, pid {g.proc.pid}, {os.path.relpath(g.log_path, Run.current.out)}; "
            "env " + " ".join(f"{k}={(env or {})[k]}" for k in sorted(env or {}) if k.startswith(("T5_CTL", "T5_NET_MODE",
                                                                                                   "T5_FIGHT"))))
        return g

    def set_status(self, text):
        self.statuses.append((time.time(), text))


# ======================================================================================= players
class _PickPad:
    """What pick_flow_test.Picker needs from a game: its log and its pad file (PS3_PAD_FILE)."""

    def __init__(self, p):
        self.p = p
        self.pad_path = os.path.join(p.dir, "pad.txt")
        self.active = True               # a picker of an earlier match must not press into this one

    @property
    def log_path(self):
        g = self.p.game()
        return g.log_path if g is not None else None

    def log_since(self, pos):
        try:
            with open(self.log_path, "rb") as f:
                f.seek(pos)
                return f.read().decode("utf-8", "replace")
        except (OSError, TypeError):
            return ""

    def pad(self, text):
        if not self.active and text:
            return
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


class Player:
    """One person at one PC: the launcher's Online tab (a frame in the shared withdrawn root), its
    settings and output folder, and the games it started."""

    def __init__(self, ctx, name, kind="real", password=None, char=None, input_delay="auto", env=None,
                 mash_gap=20, game_mode=None, user_dir=None, tag="", sets=None, bot=False, lobby=None):
        """bot=True: no scripted presses; the player attacks live (T5_NET_PADFILE) only while ctx.plan says
        this player wins the game being fought, else stands still -- planned results (ranked sets 2-0, 2-1).
        sets=False: online.json "sets": false (the old protocol: every ranked game rated, rematch votes)."""
        import tkinter as tk
        from tkinter import ttk
        self.ctx, self.name, self.kind, self.password = ctx, name, kind, password
        self.dir = os.path.join(ctx.dir, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + (f"-{tag}" if tag else ""))
        self.out = os.path.join(self.dir, "native")
        os.makedirs(self.dir, exist_ok=True)
        ctx.run.prepare_out(self.out)
        self.games = []
        self.events = []          # (time, event)
        self.notes = []           # (time, driver note)
        self.statuses = []        # (time, status text)
        self.matches = {}         # match id -> what this player saw of it
        self.app = E2EApp(self)
        # Windows Firewall blocking this player's game / launcher, emulated (T5_NET_TEST_INBOUND, set_firewall())
        self.fw_game = None
        self.fw_launcher = None
        self.mash_gap = mash_gap
        self.extra_env = dict(env or {})
        st = self.app.settings
        st["out"] = self.out
        st["nickname"] = name
        st["background"] = True
        st["input_delay"] = input_delay
        # T5_NET_BIND: every local test game binds loopback only (no firewall question, nothing reachable from
        # the network; a game without the switch ignores it)
        lines = ["PS3_AUDIO_MUTE=1", "PAD_NO_KEYBOARD=1", "T5_NET_LOCALPAD=0", "T5_NET_DESYNC_DUMP=1", "T5_NET_BIND=127.0.0.1",
                 f"RSX_SHADER_CACHE_DIR={ctx.run.shader_cache}", f"PS3_TITLE=T5DR e2e {name}"]
        if kind == "real":
            # the in-game select (ingame-select): this player's pad file, the cursor cell in the log
            lines += [f"PS3_PAD_FILE={os.path.join(self.dir, 'pad.txt')}", "T5_DF_TRACE=1"]
            open(os.path.join(self.dir, "pad.txt"), "a").close()
        self.pickers = []
        self.bot = bool(bot) and kind == "real"
        self.attacking = False
        self.padfile = os.path.join(self.dir, "pad.txt")
        self.rnd = random.Random(sum(map(ord, name)) + ctx.run.seed)
        if self.bot:
            open(self.padfile, "w").close()
            lines.append(f"T5_NET_PADFILE={self.padfile}")
        elif kind == "real":
            import fight_flow_test
            mash = fight_flow_test.mash_script(os.path.join(self.dir, "mash.txt"),
                                               1000 + sum(map(ord, name)) + ctx.run.seed, gap=mash_gap)
            lines.append(f"T5_NET_SCRIPT={mash}")
        else:
            lines += ["T5_STUB_SECONDS=2", "T5_STUB_IDLE_EXIT=900"]
        if kind == "real" and ctx.run.netcode == "lockstep" and "T5_RB_MODE" not in (env or {}):
            lines.append("T5_RB_MODE=off")             # run.py --netcode lockstep: the delay-based lockstep everywhere
        for k, v in (env or {}).items():
            lines.append(f"{k}={v}")
        st["extra_env"] = "\n".join(lines)
        st.save()
        self.frame = ttk.Frame(ctx.run.tk_root())
        self.user_dir = user_dir or os.path.join(self.dir, "user")
        os.environ["T5_ONLINE_DIR"] = self.user_dir      # read once, by the tab's constructor
        if lobby:
            # an older release's Online tab with its own client and match driver (git tag `lobby`, e.g. v1.1.0)
            import importlib
            OnlineTab = importlib.import_module(ctx.run.old_lobby(lobby) + ".tk_tab").OnlineTab
        else:
            from t5lobby.tk_tab import OnlineTab
        self.lobby = lobby
        self._sets = sets
        self.tab = OnlineTab(self.frame, self.app)
        if kind == "stub":
            game_mode = game_mode or "persistent"       # stub_game.py speaks the control channel too
            if not os.path.isfile(os.path.join(self.out, "build", "cmake", "t5dr.exe")):
                # no game build at all (a lobby-only run): the stub stands in for every part of it
                b = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", ctx.run.code_id, "e2e-stub")
                self.app.game_state = lambda: {"ok": True, "text": "stub game"}
                self.tab._build_info = lambda: (b, None)
        self._instrument(char, game_mode)
        self.tk = tk

    # ------------------------------------------------------------------ instrumentation
    def _instrument(self, char, game_mode):
        tab = self.tab
        me = self
        tab.ask_yes_no = lambda *a, **k: me.answer_yes_no
        tab.ask_string = lambda *a, **k: me.password
        self.answer_yes_no = False
        self.codes = []
        tab.show_codes = lambda codes, *a, **kw: me.codes.append(list(codes))
        tab._blocks_window = lambda rows, *a, **kw: me.notes.append((time.time(), {"kind": "blocks_window", "rows": rows}))
        tab.pad_visible = lambda: False
        if hasattr(tab, "bring_forward"):
            tab.bring_forward = lambda *a, **kw: None     # the (withdrawn) launcher window never goes to the front
        tab.server_var.set(self.ctx.server.addr if self.ctx.server else "127.0.0.1:1")
        tab.name_var.set(self.name)
        if char:
            self.set_char(char, send=False)
        if game_mode:
            tab.cfg["game_mode"] = game_mode
        if self._sets is not None:
            tab.cfg["sets"] = bool(self._sets)          # online.json "sets" (read when the tab makes its client)
        orig_new_client = tab._new_client

        def new_client(server, build):
            host = server.split("#")[0].replace("tls://", "").rsplit(":", 1)[0]
            if host != "127.0.0.1" or any(p in server for p in PUBLIC_SERVERS):
                raise RuntimeError(f"e2e guard: refusing to connect to {server!r} (local test servers only)")
            c = orig_new_client(server, build)
            me.client_made(c)
            return c
        tab._new_client = new_client
        orig_event = tab.on_event

        def on_event(ev, *a, **kw):
            me._record(ev)
            orig_event(ev, *a, **kw)
        tab.on_event = on_event
        orig_driver = tab.on_driver

        def on_driver(n, *a, **kw):
            me.notes.append((time.time(), n))
            if n.get("kind") == "game_state":
                me._game_state(n)
            orig_driver(n, *a, **kw)
        tab.on_driver = on_driver
        orig_status = tab.status

        def status(text, *a, **kw):              # (the new tab: status(text, error=False))
            me.statuses.append((time.time(), str(text)))
            orig_status(text, *a, **kw)
        tab.status = status
        orig_make = tab._make_driver

        def make_driver():
            orig_make()
            d = tab.driver
            orig_env = d.match_env

            def match_env(ev, ticket):
                env = orig_env(ev, ticket)
                if me.kind == "real" and not me.bot and not ev.get("continue") and \
                        "T5_NET_SCRIPT" not in (me.extra_env or {}):
                    # every session its own presses (a session reads T5_NET_SCRIPT when it starts; the same
                    # file every time would play the same match over and over)
                    import fight_flow_test
                    seed = (1000 + sum(map(ord, me.name)) + me.ctx.run.seed) * 7919 + sum(map(ord, ev.get("match", "")))
                    env["T5_NET_SCRIPT"] = fight_flow_test.mash_script(
                        os.path.join(me.dir, f"mash-{ev.get('match')}.txt"), seed, gap=me.mash_gap)
                if me.fw_game:
                    env["T5_NET_TEST_INBOUND"] = me.fw_game      # (a session without it: the firewall is off again)
                return me.ctx.shaper.rewrite(me, env)
            d.match_env = match_env
        tab._make_driver = make_driver

    def set_firewall(self, game=None, launcher=None):
        """Windows Firewall blocking this player's game and/or launcher, emulated from the next match on:
        "stateful" (only replies get in: Windows for a blocked program) / "block" (nothing but 127.0.0.1) / None."""
        self.fw_game, self.fw_launcher = game, launcher
        if self.tab.client is not None and hasattr(self.tab.client, "test_inbound"):
            self.tab.client.test_inbound = launcher or ""

    def client_made(self, c):
        if hasattr(c, "test_inbound"):
            c.test_inbound = self.fw_launcher or ""
        if self.ctx.block_direct.get(self.name):
            c.block_direct = True
        routes = self.ctx.relay_routes.get(self.name)
        if routes and hasattr(c, "relay_address"):
            orig = c.relay_address

            def relay_address(relay, _orig=orig, _routes=routes):
                r = _routes.get((relay or {}).get("id"))
                return r if r is not None else _orig(relay)
            c.relay_address = relay_address        # the relays through this player's delay proxies
        if self.name in self.ctx.no_nat2 and hasattr(c, "nat2"):
            c.nat2 = False           # a 1.1.0-style client: no planned punch, no relay bridge

    def _record(self, ev):
        now = time.time()
        self.events.append((now, ev))
        t = ev.get("t")
        mid = ev.get("match")
        if t in ("match_found", "match_reveal", "match_start", "match_result", "match_cancel", "rematch", "lag_check"):
            m = self.matches.setdefault(mid, {"id": mid}) if mid else None
            if m is None:
                return
            if t == "match_found":
                m.update(found=now, origin=ev.get("origin"), ranked=ev.get("ranked"), blind=bool(ev.get("blind")),
                         opponent_at_found=(ev.get("opponent") or {}).get("name"), ping=ev.get("ping"),
                         keep=ev.get("keep"), set=ev.get("set"), ready_check=ev.get("ready_check"))
            elif t == "match_reveal":
                m.update(revealed=now, opponent=(ev.get("opponent") or {}).get("name"), slot=ev.get("slot"))
            elif t == "match_start":
                g = self.app.game
                mark = None
                if g is not None and g.log_path:
                    try:
                        mark = (g.log_path, os.path.getsize(g.log_path))
                    except OSError:
                        mark = (g.log_path, 0)
                self.attacking = self._plan_attacks(ev)
                m["set_start"] = ev.get("set")
                # (match_result's `set` already points at the next game)
                m.update(started=now, path=ev.get("path"), rtt=ev.get("rtt_ms"), delay=ev.get("delay"),
                         input_delay=ev.get("input_delay"), fight=ev.get("fight"), cont=bool(ev.get("continue")),
                         role=ev.get("role"), slot=ev.get("slot"), ranked=ev.get("ranked"),
                         opponent=(ev.get("opponent") or {}).get("name"), log_mark=mark, set=ev.get("set"))
                self._auto_pick(ev, mark)
            elif t == "match_result":
                self.attacking = False
                m.update(result=now, status=ev.get("status"), reason=ev.get("reason"), winner=ev.get("winner"),
                         score=ev.get("score"), rating=ev.get("rating"), blame=ev.get("blame"), set=ev.get("set"),
                         rematch_window=ev.get("rematch_window"), you=ev.get("you"))
            elif t == "match_cancel":
                m.update(cancelled=now, cancel_reason=ev.get("reason"))
            elif t == "lag_check":
                m.update(lag=ev)

    def _plan_attacks(self, ev):
        """ctx.plan = (A, B, ["ABA", "AA", ...]): per set (counted by this player's set_end events) the winner
        of each game; True when this player is that game's winner."""
        plan = getattr(self.ctx, "plan", None)
        if not plan or not self.bot:
            return False
        pa, pb, seqs = plan
        if self is not pa and self is not pb:
            return False
        k = len(self.events_of("set_end"))
        seq = seqs[min(k, len(seqs) - 1)]
        n = int((ev.get("set") or {}).get("number") or 1)
        who = seq[min(n, len(seq)) - 1]
        return (who == "A" and self is pa) or (who == "B" and self is pb)

    def _auto_pick(self, ev, mark):
        """In-game select (fight.pick): pick this player's launcher character on the game's own select screen,
        the way a player confirms the fighter the launcher shows (tools/pick_flow_test.Picker presses through
        PS3_PAD_FILE, closed loop on the cursor cell T5_DF_TRACE logs). ctx.manual_pick: the scenario picks."""
        f = ev.get("fight") or {}
        if self.kind != "real" or not f.get("pick") or getattr(self.ctx, "manual_pick", False):
            return
        try:
            import pick_flow_test
        except ImportError:
            return
        key = f.get("p1") if ev.get("slot") == 0 else f.get("p2")
        fi = self.tab.table.fighter(key) or {}
        if fi.get("id") is None:
            return
        for _m, _k, _pk, old in self.pickers:
            old.active = False               # (a match that never reached its fight left its picker waiting)
        g = _PickPad(self)
        pk = pick_flow_test.Picker(g, f"{fi['id']}:lp", mark[1] if mark else 0, time.time() + 150)
        pk.start()
        self.pickers.append((ev.get("match"), key, pk, g))
        log(f"{self.name}: picks {fi.get('name')} on the select screen (match {ev.get('match')})")

    def bot_tick(self):
        """The planned winner presses attacks while its game is in the fight; the other one stands still."""
        if not self.bot or not self.attacking or not self.game_running():
            return
        d = self.tab.driver
        st = (d.df_status or {}) if d is not None else {}
        if st.get("state") != "fight":
            return
        try:
            if os.path.getsize(self.padfile):
                return
        except OSError:
            return
        mid = getattr(getattr(d, "ticket", None), "match_id", None)
        slot = (self.matches.get(mid) or {}).get("slot") or 0
        fwd = 0x20 if slot == 0 else 0x80
        down = 0x40
        btn = self.rnd.choice([0x8000, 0x1000, 0x4000, 0x2000, 0x8000 | 0x4000, 0x1000 | 0x2000,
                               down | 0x4000, down | 0x2000, fwd | 0x1000, fwd, fwd])
        try:
            with open(self.padfile, "w") as fp:
                fp.write(f"{btn:#x} {self.rnd.randint(3, 6)}")
        except OSError:
            pass

    def _game_state(self, n):
        if n.get("state") == "fight":
            d = self.tab.driver
            t = d.ticket if d is not None else None
            mid = getattr(t, "match_id", None)
            if mid and mid in self.matches and "fight_at" not in self.matches[mid]:
                self.matches[mid]["fight_at"] = time.time()

    # ------------------------------------------------------------------ what the player does
    def login_guest(self):
        self.tab.pw_var.set("")
        self.tab.b_guest.invoke()

    def register(self):
        self.tab.pw_var.set(self.password)
        self.tab.b_register.invoke()

    def login(self, password=None):
        self.tab.pw_var.set(password if password is not None else self.password)
        self.tab.b_login.invoke()

    def logout(self, forget=False):
        self.answer_yes_no = forget
        self.tab.b_logout.invoke()

    @property
    def client(self):
        return self.tab.client

    @property
    def me(self):
        c = self.tab.client
        return c.me if c is not None else None

    def logged_in(self):
        c = self.tab.client
        return c is not None and c.connected and c.me is not None

    def action_on(self, key):
        return str(self.tab.actions[key].cget("state")) == "normal"

    def press(self, key):
        """A button of the play row: ranked, quick, cancel, room, join, leave, challenge."""
        b = self.tab.actions[key]
        if str(b.cget("state")) != "normal":
            # a person waits for the button: the client may know the new lobby state a moment before the tab shows it
            self.ctx.wait(lambda: str(b.cget("state")) == "normal", 5)
        if str(b.cget("state")) != "normal":
            raise RuntimeError(f"{self.name}: button {key!r} is disabled")
        b.invoke()

    def bar_labels(self):
        return [spec[1] for spec in self.tab.bar_spec]

    def bar_button(self, prefix):
        """A button of the tab's bar by its English label (or its start); in another language the
        translated label (t5lobby.i18n) counts too."""
        wanted = {prefix}
        try:
            from t5lobby import i18n
            wanted.add(i18n.t(prefix))
        except ImportError:
            pass
        for b, label, _pad in self.tab.bar_spec:
            if any(label == w or label.startswith(w) for w in wanted):
                return b
        return None

    def click(self, prefix):
        b = self.bar_button(prefix)
        if b is None:
            raise RuntimeError(f"{self.name}: no bar button {prefix!r} (bar: {self.bar_labels()})")
        b.invoke()

    def set_char(self, key_or_name, send=True):
        from t5lobby import fighters
        table = self.tab.table
        name = table.fighter_name(key_or_name) if key_or_name != fighters.RANDOM else "Random"
        self.tab.char_var.set(name)
        if send:
            self.tab.on_char()

    def call(self, fn, *args):
        """A lobby request the way the tab makes them (worker thread, error to the status line)."""
        box = {}
        self.tab.call(fn, *args, then=lambda r: box.setdefault("ok", r), fail=lambda: box.setdefault("err", True))
        return box

    def status_text(self):
        return self.tab.status_var.get()

    def saw_status(self, pattern, since=0.0):
        rx = re.compile(pattern, re.I)
        return any(rx.search(t) for ts, t in self.statuses if ts >= since)

    def events_of(self, t, since=0.0):
        return [e for ts, e in self.events if e.get("t") == t and ts >= since]

    def results(self):
        return [e for _ts, e in self.events if e.get("t") == "match_result"]

    def game_running(self):
        g = self.app.game
        return g is not None and g.running()

    def game(self):
        return self.app.game

    def result_file(self, mid):
        """The game's own result file for a match, as the driver archived it (results/<id>.json), or one the
        driver moved aside (unreported-*/stale-*: the lobby had settled the match first)."""
        d = os.path.join(self.out, "logs", "online", "results")
        r = read_json(os.path.join(d, f"{mid}.json"))
        if r is not None:
            return r
        try:
            names = sorted(os.listdir(d))
        except OSError:
            return None
        for n in names:
            r = read_json(os.path.join(d, n))
            if isinstance(r, dict) and r.get("match") == mid:
                return dict(r, moved_aside=n)
        return None

    def log_segment(self, mid, end_mark=None):
        """Game log lines from this match's start to the end of the file (or end_mark)."""
        m = self.matches.get(mid) or {}
        mark = m.get("log_mark")
        g = self.app.game
        path, pos = mark if mark else ((g.log_path, 0) if g is not None and g.log_path else (None, 0))
        if not path:
            return []
        try:
            with open(path, "rb") as f:
                f.seek(pos)
                data = f.read()
        except OSError:
            return []
        return data.decode("utf-8", "replace").splitlines()

    def close(self):
        if self.kind == "real":
            self.ctx.run.real_logs += [g.log_path for g in self.games if g.log_path]
        try:
            self.tab.on_close()
        except Exception as e:      # noqa: BLE001
            log(f"{self.name}: on_close: {e}")
        for g in self.games:
            try:
                g.stop()
            except Exception:       # noqa: BLE001
                pass
        try:
            self.frame.destroy()
        except Exception:           # noqa: BLE001
            pass


# ======================================================================================= the run
class Skip(Exception):
    pass


class Abort(Exception):
    pass


class Run:
    current = None

    def __init__(self, out, exe, game_root, seed=1, rounds=1, short=False, netcode="rollback"):
        self.out = os.path.abspath(out)
        os.makedirs(self.out, exist_ok=True)
        self.exe = exe
        self.game_root = game_root
        self.seed = seed
        self.rounds = rounds
        self.short = short
        self.netcode = netcode
        self.logf = open(os.path.join(self.out, "run.log"), "a", encoding="utf-8")
        self.owned = []              # Popen objects started here
        self.jobs = []
        self.bin = os.path.join(self.out, "bin")
        self.shader_cache = os.path.join(os.path.dirname(self.out), "shader_cache")
        os.makedirs(self.shader_cache, exist_ok=True)
        self.code_id = build_game.code_id()
        self.root = None
        self.real_logs = []          # real game logs of this run (the problem report scenario reuses one)
        Run.current = self

    def old_lobby(self, ref):
        """lobby/t5lobby of the git tag `ref` (git archive into the run folder), imported as its own package
        (t5lobby uses relative imports only: lobby/tools/natsim.load_pkg). -> the package's module name."""
        name = "t5lobby_" + re.sub(r"[^A-Za-z0-9]", "", ref)
        if name in sys.modules:
            return name
        import io
        import tarfile
        r = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", ref, "lobby/t5lobby"], capture_output=True,
                           timeout=60)
        if r.returncode != 0:
            raise Skip(f"git archive {ref}: {r.stderr.decode(errors='replace').strip()}")
        base = os.path.join(self.out, f"_lobby_{re.sub(r'[^A-Za-z0-9.]', '', ref)}")
        tarfile.open(fileobj=io.BytesIO(r.stdout)).extractall(base, filter="data")
        import importlib.util
        pkg_dir = os.path.join(base, "lobby", "t5lobby")
        spec = importlib.util.spec_from_file_location(name, os.path.join(pkg_dir, "__init__.py"),
                                                      submodule_search_locations=[pkg_dir])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod             # (as lobby/tools/natsim.load_pkg)
        spec.loader.exec_module(mod)
        try:        # its own dialog module: answered like this tree's (tk_root)
            import importlib
            dialogs = importlib.import_module(name + ".dialogs")
            for n, v in (("ask_yes_no", False), ("ask_yes_no_cancel", None), ("show_info", None),
                         ("show_error", None), ("ask_string", None)):
                if hasattr(dialogs, n):
                    setattr(dialogs, n, lambda *a, _n=n, _v=v, **kw: (log(f"dialog stubbed: {name}.{_n} {a[:2]}"), _v)[1])
        except ImportError:
            pass
        log(f"lobby package {ref} loaded as {name} (from {base})")
        return name

    def tk_root(self):
        """The one Tk root of the run: withdrawn and fully transparent. Every Toplevel is withdrawn and
        transparent the moment it is made, every message box and file dialog is answered here (and
        recorded), the clipboard is an in-memory list. An error in a Tk callback goes to launcher.log
        as "error in the launcher", exactly like t5dr_launcher.pyw's App.report_callback_exception."""
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog
        if self.root is not None:
            return self.root
        self.dialogs = []
        run = self

        def answered(kind, value):
            def f(*a, **kw):
                run.dialogs.append((time.time(), kind, a[:2], {k: v for k, v in kw.items() if k in ("title", "message")}))
                log(f"dialog stubbed: {kind} {a[:2]}")
                return value
            return f
        for n in ("showinfo", "showwarning", "showerror"):
            setattr(messagebox, n, answered(n, "ok"))
        for n, v in (("askyesno", False), ("askokcancel", False), ("askretrycancel", False), ("askquestion", "no"),
                     ("askyesnocancel", None)):
            setattr(messagebox, n, answered(n, v))
        for n in ("asksaveasfilename", "askopenfilename", "askdirectory"):
            setattr(filedialog, n, answered(n, ""))
        filedialog.askopenfilenames = answered("askopenfilenames", ())
        for n in ("askstring", "askinteger", "askfloat"):
            setattr(simpledialog, n, answered(n, None))
        try:        # the launcher's own boxes (buttons in the chosen language; they block in a nested loop)
            from t5lobby import dialogs
            for n, v in (("ask_yes_no", False), ("ask_yes_no_cancel", None), ("show_info", None),
                         ("show_error", None), ("ask_string", None)):
                setattr(dialogs, n, answered("dialogs." + n, v))
        except ImportError:
            pass
        orig_top = tk.Toplevel.__init__

        def top_init(w, *a, **kw):
            orig_top(w, *a, **kw)
            try:
                w.withdraw()
                w.attributes("-alpha", 0.0)
            except tk.TclError:
                pass
            w.deiconify = lambda: None        # nothing may map it later
            w.wm_deiconify = lambda: None
        tk.Toplevel.__init__ = top_init
        self.root = tk.Tk()
        self.root.withdraw()
        try:
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.root.deiconify = lambda: None
        clip = []                 # never the real clipboard
        self.root.clipboard_clear = lambda **kw: clip.clear()
        self.root.clipboard_append = lambda text, **kw: clip.append(text)
        self.root.clipboard_get = lambda **kw: "".join(clip)

        def report_callback_exception(exc, val, tb):
            import traceback
            core.log("error in the launcher:\n" + "".join(traceback.format_exception(exc, val, tb)))
            log("error in the launcher: " + "".join(traceback.format_exception(exc, val, tb)))
        self.root.report_callback_exception = report_callback_exception
        return self.root

    def own(self, popen):
        if popen is None:
            return
        self.owned.append(popen)
        j = procs.kill_on_close_job(popen.pid)
        if j is not None:
            self.jobs.append(j)

    def ours(self):
        return {p.pid for p in self.owned}

    def contention(self):
        return procs.contention(procs.list_processes(), self.ours())

    def stage_bin(self):
        """t5dr.exe (+ t5dr_game.dll) copied once into <out>/bin; every player's native\\build\\cmake
        hard-links them (the source build is only ever read)."""
        os.makedirs(self.bin, exist_ok=True)
        if self.exe and os.path.isfile(self.exe):
            for name in ("t5dr.exe", "t5dr_game.dll"):
                src = os.path.join(os.path.dirname(os.path.abspath(self.exe)), name)
                dst = os.path.join(self.bin, name)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copyfile(src, dst)

    def prepare_out(self, out):
        """A player's output folder as the launcher's build leaves it: build/cmake/t5dr.exe,
        build/t5dr_build.json (code id), game/EBOOT.elf, game/vfs (a junction to the real one)."""
        cm = os.path.join(out, "build", "cmake")
        os.makedirs(cm, exist_ok=True)
        os.makedirs(os.path.join(out, "game"), exist_ok=True)
        for name in ("t5dr.exe", "t5dr_game.dll"):
            src = os.path.join(self.bin, name)
            if os.path.isfile(src):
                hardlink_or_copy(src, os.path.join(cm, name))
        stamp = os.path.join(out, "build", "t5dr_build.json")
        if not os.path.exists(stamp):
            with open(stamp, "w") as f:
                json.dump({"code_id": self.code_id, "built": datetime.datetime.now().isoformat(timespec="seconds"),
                           "note": "e2e: the exe is a copy of " + str(self.exe)}, f)
        if self.game_root:
            hardlink_or_copy(os.path.join(self.game_root, "game", "EBOOT.elf"), os.path.join(out, "game", "EBOOT.elf"))
            junction(os.path.join(out, "game", "vfs"), os.path.join(self.game_root, "game", "vfs"))

    def close(self):
        for p in self.owned:
            if p.poll() is None:
                try:
                    procs.kill_tree(p)
                except Exception:     # noqa: BLE001
                    pass
        for j in self.jobs:
            j.close()
        self.jobs = []
        if self.root is not None:
            try:
                self.root.destroy()
            except Exception:         # noqa: BLE001
                pass
            self.root = None
        gc.collect()


class Ctx:
    """One scenario: its folder, its lobby server, its players, the shaper, its checks and evidence."""

    def __init__(self, run, name, d, game=False):
        self.run, self.name, self.dir = run, name, d
        os.makedirs(d, exist_ok=True)
        self.server = None
        self.players = []
        self.shaper = Shaper()
        self.block_direct = {}
        self.no_nat2 = set()        # player names whose client behaves like 1.1.0 (no "nat2" cap)
        self.relays = None          # RelayNodes (regional relay scenarios)
        self.relay_routes = {}      # player name -> {relay id: delay proxy address}
        self.checks = []            # (name, ok, detail, level)
        self.evidence = []
        self.t0 = time.time()
        self.game = game
        self.matches = []           # match evidence rows
        self.plan = None            # (A, B, ["ABA", ...]): planned game winners per ranked set (bot players)
        # the launcher's own log for this scenario (core.log writes "error in the launcher" lines here)
        self.launcher_log = os.path.join(d, "launcher.log")
        core.LAUNCHER_LOG = self.launcher_log

    # ------------------------------------------------------------------ setup
    def start_server(self, **env):
        self.server = LobbyServer(os.path.join(self.dir, "server"), env).start()
        log(f"[{self.name}] lobby server {self.server.addr} " + " ".join(f"{k}={v}" for k, v in sorted(env.items())))
        for p in self.players:
            p.tab.server_var.set(self.server.addr)
        return self.server

    def player(self, name, **kw):
        if self.game and kw.get("kind", "real") == "real" and not self.run.exe:
            raise Skip("no game build (--exe)")
        p = Player(self, name, **kw)
        self.players.append(p)
        return p

    # ------------------------------------------------------------------ pumping
    def pump(self, seconds=0.05):
        root = self.run.root
        t_end = time.monotonic() + seconds
        while True:
            try:
                root.update()
            except Exception as e:     # noqa: BLE001 -- a Tk error must not stop the run
                log(f"tk: {e}")
            for p in self.players:
                p.bot_tick()
            if time.monotonic() >= t_end:
                return
            time.sleep(0.02)

    def wait(self, cond, timeout, what=None, fail=True):
        """Pump until cond() is true. On timeout: a failed check `what` (unless fail=False)."""
        t0 = time.monotonic()
        t_end = t0 + timeout
        while time.monotonic() < t_end:
            self.pump(0.05)
            try:
                if cond():
                    if what:
                        self.check(what, True, f"after {time.monotonic() - t0:.1f} s")
                    return True
            except Exception as e:     # noqa: BLE001
                log(f"[{self.name}] wait condition raised {e!r}")
        if what and fail:
            self.check(what, False, f"not within {timeout:.0f} s")
        return False

    def sleep(self, seconds):
        self.pump(seconds)

    # ------------------------------------------------------------------ checks
    def check(self, name, ok, detail="", level="fail"):
        """level fail: a failed check fails the scenario; warn: reported, does not fail it."""
        ok = bool(ok)
        self.checks.append((name, ok, str(detail), level))
        log(f"[{self.name}] {'ok  ' if ok else ('WARN' if level == 'warn' else 'FAIL')} {name}"
            + (f" -- {detail}" if detail else ""))
        return ok

    def require(self, name, ok, detail=""):
        if not self.check(name, ok, detail):
            raise Abort(name)

    def note(self, text):
        self.evidence.append(str(text))
        log(f"[{self.name}] {text}")

    def failed(self):
        return any(not ok and lvl == "fail" for _n, ok, _d, lvl in self.checks)

    def launcher_errors(self):
        try:
            with open(self.launcher_log, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return []
        return [b.strip()[:600] for b in re.split(r"(?=^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d )", text, flags=re.M)
                if "error in the launcher" in b]

    def close(self):
        for p in self.players:
            p.close()
        self.pump(0.3)
        errs = self.launcher_errors()
        self.check("launcher.log: no 'error in the launcher' line", not errs, " || ".join(errs)[:2000])
        dlg = [d for d in getattr(self.run, "dialogs", []) if d[0] >= self.t0]
        if dlg:
            self.note(f"dialogs the code tried to show (answered by the runner): {[(k, a) for _t, k, a, _kw in dlg]}")
        self.shaper.close()
        if self.relays is not None:
            self.relays.close()
        if self.server is not None:
            self.server.stop()
        gc.collect()
