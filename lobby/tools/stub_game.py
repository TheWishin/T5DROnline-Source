#!/usr/bin/env python3
"""Stand-in for t5dr.exe when there is no netplay build: reads the same environment
the lobby hands the game and performs the netplay layer's handshake on it.

    T5_NET_MODE=host|join  T5_NET_PORT=<local port>  T5_NET_PEER=<ip:port>  T5_NET_DELAY=<frames>

Like src/netplay/netplay_core.cpp: both bind T5_NET_PORT; the joiner sends HELLO to
T5_NET_PEER every 100 ms; the host learns its peer from the first HELLO and answers;
the joiner adopts the host's delay. Then both exchange 60 "frames" of input packets at
60 Hz and print what they saw. Exit code 0 = connected and in sync.
"""
import os
import socket
import struct
import sys
import time

MAGIC = b"T5NP"
HELLO, INPUT = 1, 2


def main():
    mode = os.environ.get("T5_NET_MODE", "")
    port = int(os.environ.get("T5_NET_PORT", "0"))
    peer_s = os.environ.get("T5_NET_PEER", "")
    delay = int(os.environ.get("T5_NET_DELAY", "3"))
    timeout = float(os.environ.get("T5_NET_TIMEOUT", "20"))
    tag = f"[stub {mode}]"
    if mode not in ("host", "join"):
        print(f"{tag} T5_NET_MODE must be host or join", flush=True)
        return 2
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    if os.name == "nt":
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from t5lobby.proto import disable_udp_connreset
        disable_udp_connreset(s)
    s.settimeout(0.1)
    peer = None
    if peer_s:
        h, p = peer_s.rsplit(":", 1)
        peer = (h, int(p))
    print(f"{tag} bound UDP {port}, peer {peer_s or '(learn from first packet)'}, delay {delay}", flush=True)
    if mode == "host":
        peer = None                       # netplay's host ignores T5_NET_PEER and learns it

    t_end = time.time() + timeout
    connected = False
    last_hello = 0.0
    while time.time() < t_end and not connected:
        if mode == "join" and time.time() - last_hello >= 0.1:
            s.sendto(MAGIC + bytes([HELLO, 1, delay, 1]) + b"\0\0\0\0", peer)
            last_hello = time.time()
        try:
            data, src = s.recvfrom(2048)
        except socket.timeout:
            continue
        if data[:4] != MAGIC or data[4] != HELLO:
            continue
        if mode == "host":
            peer = src
            s.sendto(MAGIC + bytes([HELLO, 1, delay, 0]) + b"\0\0\0\0", peer)
            connected = True
        else:
            delay = data[6]
            connected = True
    if not connected:
        print(f"{tag} no peer within {timeout:.0f}s", flush=True)
        return 1
    print(f"{tag} connected to {peer[0]}:{peer[1]}, delay {delay}", flush=True)

    # 60 frames of lockstep-ish input exchange
    got = set()
    rtts = []
    for f in range(60):
        s.sendto(MAGIC + bytes([INPUT, 1, delay, 0]) + struct.pack("!Id", f, time.perf_counter()), peer)
        t_frame = time.perf_counter() + 1 / 60
        while time.perf_counter() < t_frame:
            try:
                data, _ = s.recvfrom(2048)
            except socket.timeout:
                break
            if data[:4] == MAGIC and data[4] == INPUT and len(data) >= 20:
                fr, t = struct.unpack_from("!Id", data, 8)
                if data[7] == 0:              # their input: echo it back as an ack
                    got.add(fr)
                    s.sendto(data[:7] + b"\1" + data[8:], peer)
                else:
                    rtts.append((time.perf_counter() - t) * 1000)
    # drain late packets
    s.settimeout(0.3)
    try:
        while True:
            data, _ = s.recvfrom(2048)
            if data[:4] == MAGIC and data[4] == INPUT and data[7] == 0:
                got.add(struct.unpack_from("!I", data, 8)[0])
    except socket.timeout:
        pass
    rtts.sort()
    med = rtts[len(rtts) // 2] if rtts else float("nan")
    print(f"{tag} frames from peer: {len(got)}/60, median RTT {med:.2f} ms", flush=True)
    return 0 if len(got) == 60 else 1


if __name__ == "__main__":
    sys.exit(main())
