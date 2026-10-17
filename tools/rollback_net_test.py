#!/usr/bin/env python3
"""Two-instance rollback netplay test on one PC (src/rollback/rb_net.cpp).

    python tools/rollback_net_test.py --out NAME --seconds 150 [--rtt 100] [--loss 5]
        [--delay 2] [--maxpred 8] [--start 3400] [--exe build/cmake/t5dr.exe]

    python tools/rollback_net_test.py --out NAME --fight 26,33,20,2 \\
        --next 33,34,24,2 --next 33,34,24,2 --rtt 150 --jitter 5 --loss 3 --delay 1 \\
        --matches 3 --seconds 1500 [--audio] [--dump] [--mode1 off]

Starts a host and a joiner with scripted input. Without --fight: the menu path
to a Versus fight, both in netplay lockstep from boot and switching to the
rollback loop at lockstep frame --start. With --fight: both boot straight into
the match (direct fight, T5_FIGHT, T5_NET_START=external); every --next line
is the next match (written to each instance's T5_FIGHT_FILE, which direct
fight reads at character select after a match), so "--next A --next A" after
--fight is a second match plus a rematch. The attack scripts apply only
during fights (T5_NET_SCRIPT_FIGHT=1). The joiner talks to the host through a
UDP proxy on localhost that adds --rtt/2 ms of one-way delay (with +-jitter)
and drops --loss percent of the packets.

--mode1/--mode2 set T5_RB_MODE of the host/joiner (default net; "off" is the
lockstep fallback: a peer that does not offer rollback). --audio records each
instance's final mix (AUDIO_WAV, audio.f32: raw f32le stereo 48 kHz).
--matches N ends the run once both instances finished N matches.

Output: build/rollback-net-runs/NAME/{host,join}/game.log (the "[rbnet]"
summaries every 300 frames), frames.log, results.jsonl (every match result),
proxy.log, and summary.txt: per instance the sync check, decode errors, exit
code, hang, rollbacks, stalls, sounds, fps.
"""
import argparse
import json
import os
import random
import re
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


RE_RBNET = re.compile(r"rbnet: (?P<frames>\d+) frames in (?P<secs>[0-9.]+) s \([0-9.]+ fps\), (?P<rb>\d+) rollbacks \((?P<resim>\d+) frames re-simulated.*?\), "
                      r"[0-9.]+ ms per rollback.*?(?P<stalls>\d+) stalls \((?P<stall_ms>[0-9.]+) ms(?:, (?P<lock_ms>[0-9.]+) ms of them in lockstep windows)?\)"
                      r".*?(?P<sleeps>\d+) time-sync sleeps \((?P<sleep_ms>[0-9.]+) ms\), avg advantage (?P<adv>[-0-9.]+)")
RE_SOUND = re.compile(r"sounds: (\d+) started live, (\d+) kept from a first run, (\d+) new in re-simulated frames, (\d+) from mispredicted"
                      r"(?:.*?stops in re-simulated frames: (\d+) repeats skipped, (\d+) new not applied; (\d+) status answers replayed; "
                      r"music/bank events: (\d+) repeats skipped, (\d+) new)?")
RE_FT = re.compile(r"frame times \(displayed frames\) this window p50 ([0-9.]+) ms p99 ([0-9.]+) ms max ([0-9.]+) ms; whole run p50 ([0-9.]+) p99 ([0-9.]+)")
RE_SYNC = re.compile(r"sync check through frame (\d+): (\d+) mismatching")


def summarize(d, who, rc, hung):
    p = os.path.join(d, who, "game.log")
    lines = open(p, errors="replace").read().splitlines() if os.path.exists(p) else []
    tot = dict(frames=0, secs=0.0, rollbacks=0, resim=0, stalls=0, stall_ms=0.0, lock_ms=0.0, sleeps=0, sleep_ms=0.0)
    snd = [0] * 9
    adv = []
    sync = None
    ft = None
    ftmax = 0.0
    for l in lines:
        m = RE_FT.search(l)
        if m:
            ft = (float(m.group(4)), float(m.group(5)))
            ftmax = max(ftmax, float(m.group(3)))
        m = RE_RBNET.search(l)
        if m:
            g = m.groupdict()
            tot["frames"] += int(g["frames"]); tot["secs"] += float(g["secs"]); tot["rollbacks"] += int(g["rb"])
            tot["resim"] += int(g["resim"]); tot["stalls"] += int(g["stalls"]); tot["stall_ms"] += float(g["stall_ms"])
            tot["lock_ms"] += float(g["lock_ms"] or 0)
            tot["sleeps"] += int(g["sleeps"]); tot["sleep_ms"] += float(g["sleep_ms"]); adv.append(float(g["adv"]))
        m = RE_SOUND.search(l)
        if m:
            for i in range(9):
                snd[i] += int(m.group(i + 1) or 0)
        m = RE_SYNC.search(l)
        if m:
            sync = (int(m.group(1)), int(m.group(2)))
    dec = sum(1 for l in lines if "Invalid start bit" in l or "doesn't match channel configuration" in l)
    aborted = [l for l in lines if "sys_process_exit(code=1)" in l or "FATAL" in l or "[CRASH]" in l]
    starts = [l for l in lines if "FIGHT START" in l]
    overs = [l for l in lines if "MATCH OVER" in l]
    phases = sum(1 for l in lines if "fight phase" in l)
    fps = tot["frames"] / tot["secs"] if tot["secs"] else 0
    out = [f"{who}: exit {rc}{' HUNG' if hung else ''}, sync {('through frame %d: %d mismatching' % sync) if sync else 'none'}, "
           f"decode errors {dec}, aborts {len(aborted)}, matches started {len(starts)}, over {len(overs)}, phase changes {phases}",
           f"  rollback loop: {tot['frames']} frames in {tot['secs']:.0f} s ({fps:.1f} fps), {tot['rollbacks']} rollbacks, "
           f"{tot['resim']} frames re-simulated, {tot['stalls']} stalls ({tot['stall_ms']:.0f} ms, {tot['lock_ms']:.0f} ms in lockstep windows), {tot['sleeps']} time-sync sleeps "
           f"({tot['sleep_ms']:.0f} ms), advantage per window min {min(adv) if adv else 0:.2f} max {max(adv) if adv else 0:.2f}"
           + (f", displayed frame time p50 {ft[0]:.1f} ms p99 {ft[1]:.1f} ms max {ftmax:.1f} ms" if ft else ""),
           f"  sounds: {snd[0]} started live, {snd[1]} kept from a first run, {snd[2]} new in re-simulated frames, {snd[3]} played on; "
           f"stops {snd[4]} repeats skipped, {snd[5]} new not applied; {snd[6]} answers replayed; events {snd[7]} repeats skipped, {snd[8]} new"]
    for l in starts + overs:
        out.append("  " + l.strip())
    for l in aborted[:3]:
        out.append("  ABORT: " + l.strip())
    return out


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
    ap.add_argument("--fight", default="", help="direct fight p1,p2,stage[,rounds] on both sides (T5_FIGHT, T5_NET_START=external): the fight is lockstep frame 0")
    ap.add_argument("--next", action="append", default=[], help="the next match's T5_FIGHT line (repeatable): match 2, 3, ...")
    ap.add_argument("--matches", type=int, default=0, help="stop once both instances finished this many matches")
    ap.add_argument("--mode1", default="net", help="T5_RB_MODE of the host (net, off = lockstep only, default = unset)")
    ap.add_argument("--mode2", default="net", help="T5_RB_MODE of the joiner")
    ap.add_argument("--audio", action="store_true", help="record each instance's mix to audio.f32 (AUDIO_WAV)")
    ap.add_argument("--dump", action="store_true", help="T5_NET_DESYNC_DUMP=1")
    ap.add_argument("--hang", type=float, default=60, help="seconds without progress that count as a hang")
    ap.add_argument("--seed1", type=int, default=11)
    ap.add_argument("--seed2", type=int, default=22)
    ap.add_argument("--vfs", default=VFS)
    ap.add_argument("--runs", default=RUNS)
    a = ap.parse_args()
    vfs = a.vfs

    d = os.path.join(a.runs, a.out)
    os.makedirs(d, exist_ok=True)
    exe = os.path.join(d, "t5dr.exe")
    shutil.copyfile(a.exe, exe)
    game_dll = os.path.join(os.path.dirname(a.exe), "t5dr_game.dll")   # the release layout (T5DR_GAME_DLL=ON)
    if os.path.exists(game_dll):
        shutil.copyfile(game_dll, os.path.join(d, "t5dr_game.dll"))
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
        "T5_RB_NET_START": f"frame:{a.start}", "T5_RB_NET_MAXPRED": str(a.maxpred), "T5_RB_NET_LOG": "1",
    })
    if a.fight:
        base.update({"T5_FIGHT": a.fight, "T5_NET_START": "external", "T5_RB_NET_START": "0", "T5_NET_SCRIPT_FIGHT": "1"})
    if a.dump:
        base["T5_NET_DESYNC_DUMP"] = "1"
    for kv in a.env:
        k, v = kv.split("=", 1)
        base[k] = v
    procs = []
    files = {}
    for who in ("host", "join"):
        wd = os.path.join(d, who)
        os.makedirs(wd, exist_ok=True)
        env = dict(base)
        mode = a.mode1 if who == "host" else a.mode2
        if mode == "default":
            env.pop("T5_RB_MODE", None)   # what a player gets: no T5_RB_MODE at all
            env.pop("PS3_VM_WRITE_WATCH", None)   # ... and no write-watch switch (the rollback hooks turn it on)
        else:
            env["T5_RB_MODE"] = mode
        env["T5_NET_LOG"] = os.path.join(wd, "frames.log")
        env["T5_RB_LOG"] = os.path.join(wd, "rb_frames.log")
        env["T5_DF_STATUS_FILE"] = os.path.join(wd, "status.json")
        env["T5_NET_RESULT_FILE"] = os.path.join(wd, "result.json")
        if a.audio:
            env["AUDIO_WAV"] = os.path.join(wd, "audio.f32")
            env["AUDIO_RATE"] = "1"
        fight_file = os.path.join(wd, "next_fight.txt")
        for stale in (fight_file, fight_file + ".done", os.path.join(wd, "result.json"), os.path.join(wd, "status.json")):
            if os.path.exists(stale):
                os.remove(stale)
        if a.next:
            env["T5_FIGHT_FILE"] = fight_file
        files[who] = dict(log_pos=0, marks=[], audio=env.get("AUDIO_WAV"),
                          fight=fight_file, status=env["T5_DF_STATUS_FILE"], result=env["T5_NET_RESULT_FILE"], next=list(a.next),
                          last_result="", results=[], frames=os.path.join(wd, "frames.log"), last_size=-1, last_change=time.time())
        # the script goes through a file: inline it would exceed the environment's size limit
        # (np's inline form parses nothing then: "0 scripted press(es)")
        if who == "host":
            script = fight_script(120, 200000, True, a.seed1) if a.fight else MENU1 + "," + fight_script(3300, 12000, True, a.seed1)
            env.update({"T5_NET_MODE": "host", "T5_NET_PORT": str(host_port)})
        else:
            script = fight_script(120, 200000, False, a.seed2) if a.fight else MENU2 + "," + fight_script(3300, 12000, False, a.seed2)
            env.update({"T5_NET_MODE": "join", "T5_NET_PORT": "0",
                        "T5_NET_PEER": f"127.0.0.1:{host_port if a.no_proxy else proxy_port}"})
        sp = os.path.join(wd, "script.txt")
        with open(sp, "w") as fp:
            fp.write("\n".join(e.replace(":", " ") for e in script.split(",")) + "\n")
        env["T5_NET_SCRIPT"] = sp
        for kv in (a.env1 if who == "host" else a.env2):
            k, v = kv.split("=", 1)
            env[k] = v
        glog = open(os.path.join(wd, "game.log"), "w")
        p = subprocess.Popen([exe, vfs + "/PS3_GAME/USRDIR/EBOOT.elf"], env=env, cwd=wd, stdout=glog, stderr=subprocess.STDOUT)
        procs.append((who, p, glog))
        print(f"{who}: pid {p.pid} in {wd}", flush=True)
        time.sleep(1.5)

    def feed_fight_file(f):
        """Hand the next match to direct fight: the file is written while none is pending."""
        if not f["next"] or os.path.exists(f["fight"]):
            return
        if os.path.exists(f["fight"] + ".done") or not f.get("written"):
            if os.path.exists(f["fight"] + ".done"):
                os.remove(f["fight"] + ".done")
            tmp = f["fight"] + ".tmp"
            with open(tmp, "w") as fp:
                fp.write(f["next"].pop(0) + "\n")
            os.replace(tmp, f["fight"])
            f["written"] = True

    def matches_over(f):
        try:
            st = json.load(open(f["status"]))
        except (OSError, ValueError):
            return 0
        m = int(st.get("match", 0))
        return m - 1 if st.get("state") == "fight" else m

    def mark_audio(who, f):
        """Where FIGHT START / MATCH OVER fell in the audio recording (seconds of
        audio.f32), for tools/rollback_audio_check.py --match."""
        if not f["audio"]:
            return
        lp = os.path.join(d, who, "game.log")
        try:
            with open(lp, "rb") as fp:
                fp.seek(f["log_pos"])
                chunk = fp.read()
        except OSError:
            return
        nl = chunk.rfind(bytes([10]))
        if nl < 0:
            return
        f["log_pos"] += nl + 1
        for line in chunk[:nl].decode(errors="replace").splitlines():
            if "FIGHT START" in line or "MATCH OVER" in line:
                try:
                    secs = os.path.getsize(f["audio"]) / 8.0 / 48000.0
                except OSError:
                    secs = 0.0
                f["marks"].append({"event": "start" if "FIGHT START" in line else "over", "audio_s": round(secs, 2), "line": line.strip()})
                with open(os.path.join(d, who, "marks.json"), "w") as fp:
                    json.dump(f["marks"], fp, indent=1)

    hung = {"host": False, "join": False}
    t0 = time.time()
    try:
        while time.time() - t0 < a.seconds:
            if any(p.poll() is not None for _, p, _ in procs):
                print("an instance exited early", flush=True)
                break
            done = True
            for who, p, _ in procs:
                f = files[who]
                feed_fight_file(f)
                mark_audio(who, f)
                try:
                    r = open(f["result"]).read()
                except OSError:
                    r = ""
                if r and r != f["last_result"]:
                    f["last_result"] = r
                    f["results"].append(r.strip())
                    with open(os.path.join(d, who, "results.jsonl"), "a") as fp:
                        fp.write(r.strip() + "\n")
                try:
                    sz = os.path.getsize(f["frames"])
                except OSError:
                    sz = -1
                if sz != f["last_size"]:
                    f["last_size"] = sz
                    f["last_change"] = time.time()
                elif time.time() - f["last_change"] > a.hang and time.time() - t0 > 120:
                    hung[who] = True
                if a.matches and (matches_over(f) < a.matches or len(f["results"]) < a.matches):
                    done = False
                if a.matches and matches_over(f) >= a.matches and not f.get("over_t"):
                    f["over_t"] = time.time()
            if any(hung.values()):
                print("an instance made no progress for %.0f s: hang" % a.hang, flush=True)
                break
            if a.matches and done:
                time.sleep(2)
                break
            if a.matches and all(files[w].get("over_t") and time.time() - files[w]["over_t"] > 45 for w in ("host", "join")):
                print("the last match's result did not arrive within 45 s", flush=True)
                break
            time.sleep(0.1 if a.audio else 0.5)
    finally:
        rcs = {}
        for who, p, glog in procs:
            if p.poll() is None:
                p.kill()
                p.wait()
                rcs[who] = "killed"
            else:
                rcs[who] = p.returncode
            glog.close()
        if proxy:
            proxy.stop = True
            log.write(f"proxy: {proxy.stats}\n")
        log.close()
    out = [f"run {a.out}: rtt {a.rtt} jitter {a.jitter} loss {a.loss} delay {a.delay} maxpred {a.maxpred}, {time.time() - t0:.0f} s, modes {a.mode1}/{a.mode2}"]
    for who, _, _ in procs:
        out += summarize(d, who, rcs[who], hung[who])
        for r in files[who]["results"]:
            out.append("  result: " + r)
    if proxy:
        out.append(f"proxy: {proxy.stats}")
    open(os.path.join(d, "summary.txt"), "w").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
