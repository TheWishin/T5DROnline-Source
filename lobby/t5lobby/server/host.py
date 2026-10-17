"""Host for friends: run a lobby server on this PC for a group of friends, nothing to set up.

    python -m t5lobby.server.host [--map-ports] [--port 7781] [--data DIR] [--no-tls] [--json]
    (release zip: "lobby\\deploy\\windows\\host-for-friends.cmd", or the launcher's Host button)

On the first start it makes a self-signed TLS certificate (pure Python, no openssl) in the data
folder; its fingerprint goes into the line you give your friends:

    203.0.113.7:7781#3f0c...e1     -> they paste it into the launcher's Server field

The data folder (default %LOCALAPPDATA%\\T5DR Online\\lobby-host, ~/.local/share/t5lobby-host)
keeps the database (accounts, ratings), the certificate, logs (rotated) and daily backups.

Your friends must reach the PC: forward TCP 7781 and UDP 7781-7782 on the router to it, or let
this program ask the router to do so with --map-ports (UPnP IGD or NAT-PMP; only then is the
router contacted). Mappings have a one-hour lease that is renewed while hosting and are removed
when you stop. Without a public IPv4 address (carrier-grade NAT, DS-Lite) hosting from home
cannot work -- use a small VPS instead (docs/HOSTING.md).

When you play on the hosting PC yourself, your matches against friends go through your own
server's relay. It runs on your PC, so it adds no detour.
"""
import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time

from .. import proto
from .config import Config
from .lobby import LobbyServer

log = logging.getLogger("t5lobby.host")


def default_data_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "T5DR Online", "lobby-host")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "t5lobby-host")


class Host:
    def __init__(self, a):
        self.a = a
        self.data = os.path.abspath(a.data or default_data_dir())
        self.json = a.json
        self.mapper = None
        self.mapped = []
        self.public_ip = None
        self.lan_ip = None
        self.fp = None

    # ----------------------------------------------------------------- output
    def say(self, text):
        if not self.json and sys.stdout is not None:
            print(text, flush=True)
        else:
            log.info("%s", text.strip())

    def event(self, kind, **data):
        if self.json and sys.stdout is not None:
            print(json.dumps(dict(event=kind, **data)), flush=True)

    # ----------------------------------------------------------------- setup
    def certificate(self):
        from . import selfsigned
        d = os.path.join(self.data, "tls")
        cert, key = os.path.join(d, "cert.pem"), os.path.join(d, "key.pem")
        if not (os.path.isfile(cert) and os.path.isfile(key)):
            self.say("Making this server's TLS certificate (once; a few seconds)...")
            cert, key, _ = selfsigned.write_pair(d, "t5lobby-host")
        self.fp = selfsigned.fingerprint(cert)
        return cert, key

    def map_ports(self, ports):
        from ..portmap import PortMapError, PortMapper
        self.mapper = PortMapper(dry_run=self.a.map_dry_run)
        self.say("Asking the router to forward the ports (UPnP / NAT-PMP)...")
        try:
            if not self.mapper.discover():
                if self.a.map_dry_run:
                    for proto_, port in ports:
                        self.mapper.add(proto_, port)    # only logs what it would ask for
                    self.say("  (dry run: nothing was sent to the router)")
                else:
                    self.say("  The router did not answer (UPnP / NAT-PMP off?). Forward the ports by hand.")
                return
            for proto_, port in ports:
                try:
                    self.mapper.add(proto_, port)
                    self.mapped.append(f"{proto_} {port}")
                except (PortMapError, OSError) as e:
                    self.say(f"  {proto_} {port}: {e}")
            self.public_ip = self.mapper.external_ip()
        except (PortMapError, OSError) as e:
            self.say(f"  port mapping failed: {e}")

    def share_info(self, port):
        from ..portmap import default_gateway, local_ip_toward
        self.lan_ip = local_ip_toward(default_gateway() or "192.168.0.1") or "127.0.0.1"
        suffix = f":{port}" + (f"#{self.fp}" if self.fp else "")
        info = {"port": port, "fingerprint": self.fp, "lan_ip": self.lan_ip, "public_ip": self.public_ip,
                "mapped": self.mapped, "local": f"127.0.0.1{suffix}", "lan": f"{self.lan_ip}{suffix}",
                "internet": f"{self.public_ip}{suffix}" if self.public_ip else None, "data": self.data}
        with open(os.path.join(self.data, "host.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=1)
        return info

    # ----------------------------------------------------------------- run
    def run(self):
        os.makedirs(self.data, exist_ok=True)
        cert = key = ""
        if not self.a.no_tls:
            cert, key = self.certificate()
        cfg = Config.from_env(
            host="0.0.0.0", port=self.a.port, udp_port=self.a.port,
            udp_port2=self.a.udp_port2 if self.a.udp_port2 is not None else (self.a.port + 1 if self.a.port else 0),
            db=os.path.join(self.data, "t5lobby.db"), tls_cert=cert, tls_key=key,
            log_file=os.path.join(self.data, "logs", "t5lobby.log"),
            backup_dir=os.path.join(self.data, "backups"), backup_keep=7,
            status_port=self.a.status_port, motd=self.a.motd or "",
            guests=True, accounts=not self.a.guests_only)
        from .__main__ import setup_logging
        setup_logging(cfg)
        loop = proto.new_event_loop()
        asyncio.set_event_loop(loop)
        srv = LobbyServer(cfg)
        stop = asyncio.Event()
        try:
            loop.run_until_complete(srv.start())
        except OSError as e:
            self.say(f"Cannot start the server: {e}\n(Is another lobby server already running on port "
                     f"{self.a.port}? Close it, or use --port.)")
            self.event("error", message=str(e))
            return 2
        ports = [("TCP", srv.port), ("UDP", srv.udp.port)] + ([("UDP", srv.udp.port2)] if srv.udp.port2 else [])
        if self.a.map_ports or self.a.map_dry_run:
            self.map_ports(ports)
        info = self.share_info(srv.port)
        self.event("ready", **info)
        self.say(self.banner(info, ports))

        def renew():
            if self.mapper and self.mapper.backend:
                self.mapper.renew()

        async def main():
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except (NotImplementedError, RuntimeError):
                    pass
            if self.a.stdin_control:
                threading.Thread(target=self._watch_stdin, args=(loop, stop), daemon=True).start()
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), 300)
                except asyncio.TimeoutError:
                    await loop.run_in_executor(None, renew)
            await srv.stop()

        try:
            loop.run_until_complete(main())
        except KeyboardInterrupt:
            loop.run_until_complete(srv.stop())
        finally:
            loop.close()
            if self.mapper and self.mapper.backend:
                self.say("Removing the router's port forwarding...")
                self.mapper.remove_all()
            self.event("stopped")
            self.say("Lobby server stopped.")
        return 0

    @staticmethod
    def _watch_stdin(loop, stop):
        """Launcher mode: 'stop' on stdin, or stdin closing (the launcher went away), stops hosting."""
        try:
            for line in sys.stdin:
                if line.strip().lower() in ("stop", "quit", "exit"):
                    break
        except (OSError, ValueError):
            pass
        loop.call_soon_threadsafe(stop.set)

    def banner(self, info, ports):
        ports_s = ", ".join(f"{p} {n}" for p, n in ports)
        lines = ["", "=" * 72, "  T5DR lobby server is running on this PC.", ""]
        if info["internet"]:
            lines += ["  Give your friends this line (they paste it as the launcher's Server):", "",
                      f"      {info['internet']}", ""]
        else:
            lines += ["  Give your friends this line, with YOUR PUBLIC IP ADDRESS in front",
                      "  (your router's status page shows it; it is not the 192.168... one):", "",
                      f"      <public-ip>:{info['port']}" + (f"#{self.fp}" if self.fp else ""), ""]
        lines += [f"  Friends on your own network:  {info['lan']}",
                  f"  You, on this PC:              {info['local']}", ""]
        if self.mapped:
            lines.append(f"  Router forwarding: {', '.join(self.mapped)} (removed when you stop)")
        else:
            lines.append(f"  Router: forward {ports_s} to {info['lan_ip']} (or start with --map-ports).")
        lines.append("  Windows asks whether Python may accept connections: allow it (private networks).")
        if self.fp:
            from .selfsigned import pretty
            lines.append(f"  Certificate fingerprint: {pretty(self.fp)}")
        lines += [f"  Data, logs, backups: {self.data}", "  Stop: Ctrl+C (or close this window).", "=" * 72, ""]
        return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m t5lobby.server.host", description="Host a lobby for friends")
    ap.add_argument("--data", help="data folder (database, certificate, logs, backups)")
    ap.add_argument("--port", type=int, default=proto.DEFAULT_PORT, help="TCP and UDP port (default 7781)")
    ap.add_argument("--udp-port2", type=int, help="NAT probe port (default port + 1; 0 = off)")
    ap.add_argument("--status-port", type=int, default=7780, help="local status page port (0 = off)")
    ap.add_argument("--map-ports", action="store_true", help="ask the router to forward the ports (UPnP/NAT-PMP)")
    ap.add_argument("--map-dry-run", action="store_true", help="show what --map-ports would do; contact nobody")
    ap.add_argument("--no-tls", action="store_true", help="plain TCP (then use guest logins only)")
    ap.add_argument("--guests-only", action="store_true", help="no accounts on this server")
    ap.add_argument("--motd", help="message shown to players after login")
    ap.add_argument("--json", action="store_true", help="machine-readable events on stdout (the launcher)")
    ap.add_argument("--stdin-control", action="store_true", help="stop on 'stop' or end of stdin (the launcher)")
    a = ap.parse_args(argv)
    if a.no_tls and not a.guests_only:
        a.guests_only = True      # never let passwords cross the internet in clear from a home host
    return Host(a).run()


if __name__ == "__main__":
    sys.exit(main())
