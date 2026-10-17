#!/usr/bin/env python3
"""Two-instance rollback netplay test on one PC (src/rollback/rb_net.cpp).

    python tools/rollback_net_test.py --out NAME --seconds 150 [--rtt 100] [--loss 5]
        [--delay 2] [--maxpred 8] [--start 3400] [--exe build/cmake/t5dr.exe]

Starts a host and a joiner with scripted input (the menu path to a Versus
fight, then attacks on both sides), both in netplay lockstep from boot
(T5_NET_MODE) and switching to the rollback loop at lockstep frame --start
(T5_RB_MODE=net, T5_RB_NET_START). The joiner talks to the host through a
UDP proxy on localhost that adds --rtt/2 ms of one-way delay (with +-jitter)
and drops --loss percent of the packets, so the rollback frequency and depth
at a given latency can be measured without a second PC.

Output: build/rollback-net-runs/NAME/{host,join}/game.log (the "[rbnet]"
summaries every 300 frames: fps, rollbacks, depth histogram, stalls,
mismatches) and proxy.log.
"""
import argparse
import os
import random
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
EXE = ROOT + "/build/cmake/t5dr.exe"
VFS = os.environ.get("PS3_VFS_ROOT", ROOT + "/game/vfs")
RUNS = ROOT + "/build/rollback-net-runs"

# np packing: DIGITAL1 low byte (UP 10 RIGHT 20 DOWN 40 LEFT 80 START 8),
# DIGITAL2 high byte (TRIANGLE 1000 CIRCLE 2000 CROSS 4000 SQUARE 8000).
MENU1 = "1200:4:0x8,1500:4:0x40,1540:4:0x40,1580:4:0x4000,1800:4:0x4000,2000:4:0x4000,2200:4:0x4000"
MENU2 = "1810:4:0x4000,2010:4:0x4000,2210:4:0x4000"


def fight_script(start, end, p1, seed):
    """Varied attacks and movement: presses of 2-6 frames at irregular gaps, so
    the remote input changes often (every change the peer did not see in time
    is a misprediction)."""
    rnd = random.Random(seed)
    ev = []
    f = start
    while f < end:
        if p1:
            btn = rnd.choice(["0x8000", "0x1000", "0x4000", "0x2000", "0x20", "0x40", "0x10"])
        else:
            btn = rnd.choice(["0x8000", "0x1000", "0x4000", "0x2000", "0x80", "0x40", "0x10"])
        n = rnd.randint(2, 6)
        ev.append(f"{f}:{n}:{btn}")
        f += n + rnd.randint(2, 20)
    return ",".join(ev)


class Proxy(threading.Thread):
    """UDP proxy: joiner -> proxy:port_in -> host:port_host, replies back. Each
    datagram is delayed by rtt/2 (+-jitter) ms, dropped with probability loss."""

    def __init__(self, port_in, host_port, rtt_ms, jitter_ms, loss_pct, log):
        super().__init__(daemon=True)
        self.sock_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_in.bind(("127.0.0.1", port_in))
        self.sock_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_out.bind(("127.0.0.1", 0))
        self.host = ("127.0.0.1", host_port)
        self.joiner = None
        self.one_way = rtt_ms / 2000.0
        self.jitter = jitter_ms / 1000.0
        self.loss = loss_pct / 100.0
        self.log = log
        self.rnd = random.Random(1)
        self.stats = {"j2h": 0, "h2j": 0, "dropped": 0}
        self.queue = []          # (due, sock, data, addr)
        self.lock = threading.Lock()
        self.stop = False

    def delayed_send(self, sock, data, addr):
        if self.loss and self.rnd.random() < self.loss:
            self.stats["dropped"] += 1
            return
        due = time.perf_counter() + self.one_way + (self.rnd.uniform(-self.jitter, self.jitter) if self.jitter else 0)
        with self.lock:
            self.queue.append((due, sock, data, addr))

    def pump(self):
        while not self.stop:
            now = time.perf_counter()
            ready = []
            with self.lock:
                keep = []
                for item in self.queue:
                    (ready if item[0] <= now else keep).append(item)
                self.queue = keep
            ready.sort(key=lambda x: x[0])
            for _, sock, data, addr in ready:
                try:
                    sock.sendto(data, addr)
                except OSError:
                    pass
            time.sleep(0.0005)

    def rx(self, sock, direction):
        sock.settimeout(0.2)
        while not self.stop:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if direction == "j2h":
                self.joiner = addr
                self.stats["j2h"] += 1
                self.delayed_send(self.sock_out, data, self.host)
            else:
                self.stats["h2j"] += 1
                if self.joiner:
                    self.delayed_send(self.sock_in, data, self.joiner)

    def run(self):
        threading.Thread(target=self.rx, args=(self.sock_in, "j2h"), daemon=True).start()
        threading.Thread(target=self.rx, args=(self.sock_out, "h2j"), daemon=True).start()
        self.pump()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=150)
    ap.add_argument("--exe", default=EXE)
    ap.add_argument("--rtt", type=float, default=0, help="round-trip time added by the proxy, ms")
    ap.add_argument("--jitter", type=float, default=0, help="+- one-way jitter, ms")
    ap.add_argument("--loss", type=float, default=0, help="packet loss, percent")
    ap.add_argument("--delay", type=int, default=2, help="input delay, frames")
    ap.add_argument("--maxpred", type=int, default=8)
    ap.add_argument("--start", type=int, default=3400, help="lockstep frame at which the rollback loop takes over")
    ap.add_argument("--env", action="append", default=[], help="extra NAME=VALUE for both instances")
    ap.add_argument("--env1", action="append", default=[], help="extra NAME=VALUE for the host only")
    ap.add_argument("--env2", action="append", default=[], help="extra NAME=VALUE for the joiner only")
    ap.add_argument("--port", type=int, default=7300)
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument("--vfs", default=VFS)
    ap.add_argument("--runs", default=RUNS)
    a = ap.parse_args()
    vfs = a.vfs

    d = os.path.join(a.runs, a.out)
    os.makedirs(d, exist_ok=True)
    exe = os.path.join(d, "t5dr.exe")
    shutil.copyfile(a.exe, exe)
    host_port, proxy_port = a.port, a.port + 1
    proxy = None
    log = open(os.path.join(d, "proxy.log"), "w")
    if not a.no_proxy:
        proxy = Proxy(proxy_port, host_port, a.rtt, a.jitter, a.loss, log)
        proxy.start()
    base = dict(os.environ)
    base.update({
        "PS3_VFS_ROOT": vfs, "PS3_HDD0_ROOT": vfs + "/dev_hdd0", "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1",
        "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1", "PAD_NO_KEYBOARD": "1", "PS3_VM_WRITE_WATCH": "1",
        "T5_NET_LOCALPAD": "0", "T5_NET_DELAY": str(a.delay), "T5_NET_TIMEOUT": "60",
        "T5_RB_MODE": "net", "T5_RB_NET_START": f"frame:{a.start}", "T5_RB_NET_MAXPRED": str(a.maxpred), "T5_RB_NET_LOG": "1",
    })
    for kv in a.env:
        k, v = kv.split("=", 1)
        base[k] = v
    procs = []
    for who in ("host", "join"):
        wd = os.path.join(d, who)
        os.makedirs(wd, exist_ok=True)
        env = dict(base)
        env["T5_NET_LOG"] = os.path.join(wd, "frames.log")
        env["T5_RB_LOG"] = os.path.join(wd, "rb_frames.log")
        if who == "host":
            env.update({"T5_NET_MODE": "host", "T5_NET_PORT": str(host_port),
                        "T5_NET_SCRIPT": "@" + MENU1 + "," + fight_script(3300, 12000, True, 11)})
        else:
            env.update({"T5_NET_MODE": "join", "T5_NET_PORT": "0",
                        "T5_NET_PEER": f"127.0.0.1:{host_port if a.no_proxy else proxy_port}",
                        "T5_NET_SCRIPT": "@" + MENU2 + "," + fight_script(3300, 12000, False, 22)})
        for kv in (a.env1 if who == "host" else a.env2):
            k, v = kv.split("=", 1)
            env[k] = v
        glog = open(os.path.join(wd, "game.log"), "w")
        p = subprocess.Popen([exe, vfs + "/PS3_GAME/USRDIR/EBOOT.elf"], env=env, cwd=wd, stdout=glog, stderr=subprocess.STDOUT)
        procs.append((p, glog))
        print(f"{who}: pid {p.pid} in {wd}")
        time.sleep(1.5)
    t0 = time.time()
    try:
        while time.time() - t0 < a.seconds:
            if any(p.poll() is not None for p, _ in procs):
                print("an instance exited early")
                break
            time.sleep(0.5)
    finally:
        for p, glog in procs:
            if p.poll() is None:
                p.kill()
                p.wait()
            glog.close()
        if proxy:
            proxy.stop = True
            log.write(f"proxy: {proxy.stats}\n")
        log.close()
    # summary: the last [rbnet] line of each instance
    for who in ("host", "join"):
        lines = [l.strip() for l in open(os.path.join(d, who, "game.log"), errors="replace") if "rbnet:" in l and "frames in" in l]
        print(f"== {who}: {len(lines)} summaries")
        for l in lines[-3:]:
            print("  " + l)
        sync = [l.strip() for l in open(os.path.join(d, who, "game.log"), errors="replace") if "sync check" in l or "DESYNC" in l]
        for l in sync[-2:]:
            print("  " + l)
    if proxy:
        print("proxy:", proxy.stats)


if __name__ == "__main__":
    main()
