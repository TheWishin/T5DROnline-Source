"""Ask the home router to forward ports to this PC: PCP (RFC 6887), NAT-PMP (RFC 6886) or UPnP IGD,
stdlib only.

Two users:
  * "Host for friends" when the player asks for it (`--map-ports`, the launcher's "Open ports on my
    router" box): the lobby server's ports, a 1-hour lease renewed while hosting, removed when hosting
    stops, so a crash leaves nothing behind for longer than the lease -- except on routers that only take
    permanent UPnP mappings, which are deleted on a clean stop.
  * GamePortMapper: the game socket's port for one match (the launcher's "Open the game's port on my
    router" setting, LobbyClient(port_mapping=True)). A forwarded port is reachable from any address, so
    the opponent's punches get in even when the opponent's NAT changes ports for every destination. A
    10-minute lease renewed while the match runs; never a permanent mapping. `T5_PORTMAP=0` switches it
    off whatever the setting says (tests set it: nothing here may talk to the real router of the PC that
    runs them).

    m = PortMapper()                       # finds the gateway, the PC's LAN address
    if m.discover():                       # PCP, then NAT-PMP, then UPnP (SSDP); False = no luck
        m.add("TCP", 7781); m.add("UDP", 7781); m.add("UDP", 7782)
        print(m.external_ip())
        ...
        m.remove_all()

PortMapper(dry_run=True) talks to nobody: it logs what it would send. The tests run it against
fake routers on 127.0.0.1.

Safety: the UPnP description URL a device announces must be plain http on a private address --
the address the announcement came from -- and replies are size-capped, so a hostile device on the
LAN cannot make this fetch from elsewhere or feed it megabytes.
"""
import ipaddress
import logging
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import threading
import xml.etree.ElementTree as ET

log = logging.getLogger("t5lobby.portmap")

NATPMP_PORT = 5351
SSDP_ADDR = ("239.255.255.250", 1900)
IGD_SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
                "urn:schemas-upnp-org:service:WANPPPConnection:1")
MAX_REPLY = 64 * 1024
DESCRIPTION = "T5DR lobby"


class PortMapError(Exception):
    pass


# ----------------------------------------------------------------------------- local network facts
def default_gateway():
    """IPv4 address of the default gateway, or None."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/net/route") as f:
                for line in f.readlines()[1:]:
                    p = line.split()
                    if len(p) > 2 and p[1] == "00000000" and int(p[3], 16) & 2:
                        return socket.inet_ntoa(struct.pack("<I", int(p[2], 16)))
        elif os.name == "nt":
            # route.exe writes the console (OEM) code page: umlauts on a German Windows are not
            # UTF-8 (PYTHONUTF8=1) and not always cp1252 either; only digits and dots are parsed.
            out = subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True, timeout=5,
                                 encoding="oem", errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            best = None
            for line in out.splitlines():
                p = line.split()
                if len(p) >= 5 and p[0] == "0.0.0.0" and p[1] == "0.0.0.0":
                    try:
                        ipaddress.IPv4Address(p[2])
                        metric = int(p[-1])
                    except ValueError:
                        continue
                    if best is None or metric < best[1]:
                        best = (p[2], metric)
            return best[0] if best else None
        else:
            out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"gateway:\s*([\d.]+)", out)
            return m.group(1) if m else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def local_ip_toward(addr):
    """The LAN address this PC uses to reach `addr` (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((addr, 9))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _private(ip):
    try:
        a = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_loopback


# ----------------------------------------------------------------------------- NAT-PMP
class NatPmp:
    name = "NAT-PMP"

    def __init__(self, gateway, port=NATPMP_PORT, timeout=0.25, tries=4):
        self.gateway, self.port, self.timeout, self.tries = gateway, port, timeout, tries

    def _ask(self, req, op):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            t = self.timeout
            for _ in range(self.tries):           # RFC 6886: 250 ms, doubling
                s.sendto(req, (self.gateway, self.port))
                s.settimeout(t)
                end = time.monotonic() + t
                while time.monotonic() < end:
                    try:
                        data, src = s.recvfrom(64)
                    except (socket.timeout, ConnectionError):
                        break
                    if src[0] != self.gateway or len(data) < 8 or data[0] != 0 or data[1] != 128 + op:
                        continue
                    result = struct.unpack_from("!H", data, 2)[0]
                    if result != 0:
                        raise PortMapError(f"NAT-PMP error {result}")
                    return data
                t *= 2
            return None
        finally:
            s.close()

    def probe(self):
        return self.external_ip() is not None

    def external_ip(self):
        r = self._ask(b"\x00\x00", 0)
        if r is None or len(r) < 12:
            return None
        return socket.inet_ntoa(r[8:12])

    def add(self, proto, ext_port, int_port, client_ip, lifetime):
        op = 1 if proto == "UDP" else 2
        r = self._ask(struct.pack("!BBHHHI", 0, op, 0, int_port, ext_port, lifetime), op)
        if r is None or len(r) < 16:
            raise PortMapError("no answer from the router (NAT-PMP)")
        _int, mapped, life = struct.unpack_from("!HHI", r, 8)
        return mapped, life

    def remove(self, proto, ext_port, int_port):
        op = 1 if proto == "UDP" else 2
        self._ask(struct.pack("!BBHHHI", 0, op, 0, int_port, 0, 0), op)


# ----------------------------------------------------------------------------- PCP
def _v6mapped(ip):
    return b"\x00" * 10 + b"\xff\xff" + socket.inet_aton(ip or "0.0.0.0")


class PcpUnsupported(PortMapError):
    """The gateway answered in NAT-PMP's format: it speaks NAT-PMP, not PCP."""


class Pcp:
    """PCP MAP requests (RFC 6887) to the gateway's port 5351 -- the successor of NAT-PMP on the same port;
    a NAT-PMP-only router answers a PCP request with its own "unsupported version" (version 0)."""
    name = "PCP"
    PROTO = {"UDP": 17, "TCP": 6}

    def __init__(self, gateway, client_ip, port=NATPMP_PORT, timeout=0.25, tries=2):
        self.gateway, self.client_ip, self.port, self.timeout, self.tries = gateway, client_ip, port, timeout, tries
        self.nonces = {}
        self.ext_ip = None

    def _ask(self, opcode, lifetime, payload=b""):
        req = struct.pack("!BBHI", 2, opcode, 0, lifetime) + _v6mapped(self.client_ip) + payload
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            t = self.timeout
            for _ in range(self.tries):
                s.sendto(req, (self.gateway, self.port))
                s.settimeout(t)
                end = time.monotonic() + t
                while time.monotonic() < end:
                    try:
                        data, src = s.recvfrom(1100)
                    except (socket.timeout, ConnectionError):
                        break
                    if src[0] != self.gateway or len(data) < 4:
                        continue
                    if data[0] == 0:
                        raise PcpUnsupported("the router speaks NAT-PMP, not PCP")
                    if data[0] != 2 or data[1] != 0x80 | opcode or len(data) < 24:
                        continue
                    if data[3] != 0:
                        raise PortMapError(f"PCP error {data[3]}")
                    return data
                t *= 2
            return None
        finally:
            s.close()

    def probe(self):
        return self._ask(0, 0) is not None              # ANNOUNCE

    def external_ip(self):
        return self.ext_ip

    def add(self, proto, ext_port, int_port, client_ip, lifetime):
        nonce = self.nonces.setdefault((proto, int_port), os.urandom(12))
        body = nonce + struct.pack("!B3xHH", self.PROTO[proto], int_port, ext_port) + _v6mapped("0.0.0.0")
        r = self._ask(1, lifetime, body)
        if r is None or len(r) < 60:
            raise PortMapError("no answer from the router (PCP)")
        life = struct.unpack_from("!I", r, 4)[0]
        if r[24:36] != nonce:
            raise PortMapError("PCP answer for another request")
        mapped = struct.unpack_from("!H", r, 42)[0]
        ip = r[44:60]
        if ip[:12] == b"\x00" * 10 + b"\xff\xff":
            self.ext_ip = socket.inet_ntoa(ip[12:])
        return mapped, life

    def remove(self, proto, ext_port, int_port):
        nonce = self.nonces.pop((proto, int_port), None)
        if nonce is None:
            return
        body = nonce + struct.pack("!B3xHH", self.PROTO[proto], int_port, ext_port) + _v6mapped("0.0.0.0")
        self._ask(1, 0, body)


# ----------------------------------------------------------------------------- UPnP IGD
def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))      # LAN only: never a proxy


def _read_capped(resp):
    data = resp.read(MAX_REPLY + 1)
    if len(data) > MAX_REPLY:
        raise PortMapError("reply too large")
    return data


def _local(tag):
    return tag.rsplit("}", 1)[-1]


class Upnp:
    name = "UPnP"

    def __init__(self, control_url, service, timeout=3.0):
        self.control_url, self.service, self.timeout = control_url, service, timeout

    @classmethod
    def discover(cls, timeout=2.0, ssdp_addr=SSDP_ADDR, bind_ip=""):
        """SSDP M-SEARCH, then the first gateway whose description lists a WAN*Connection service."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            if bind_ip:
                s.bind((bind_ip, 0))
            for st in ("urn:schemas-upnp-org:device:InternetGatewayDevice:1",
                       "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
                       "urn:schemas-upnp-org:service:WANIPConnection:1"):
                msg = ("M-SEARCH * HTTP/1.1\r\n"
                       f"HOST: {ssdp_addr[0]}:{ssdp_addr[1]}\r\n"
                       'MAN: "ssdp:discover"\r\nMX: 2\r\n'
                       f"ST: {st}\r\n\r\n")
                s.sendto(msg.encode("ascii"), ssdp_addr)
            seen = set()
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                s.settimeout(max(0.05, end - time.monotonic()))
                try:
                    data, src = s.recvfrom(4096)
                except (socket.timeout, ConnectionError):
                    break
                m = re.search(rb"(?im)^location:\s*(\S+)\s*$", data)
                if not m:
                    continue
                loc = m.group(1).decode("ascii", "replace")
                if loc in seen:
                    continue
                seen.add(loc)
                try:
                    dev = cls.from_location(loc, src[0])
                except (PortMapError, OSError, ET.ParseError, ValueError) as e:
                    log.debug("UPnP device at %s: %s", loc, e)
                    continue
                if dev:
                    return dev
            return None
        finally:
            s.close()

    @classmethod
    def from_location(cls, location, announced_by):
        u = urllib.parse.urlsplit(location)
        if u.scheme != "http" or u.hostname != announced_by or not _private(u.hostname):
            raise PortMapError(f"ignoring description URL {location!r} announced by {announced_by}")
        with _opener().open(location, timeout=3.0) as r:
            root = ET.fromstring(_read_capped(r))
        base = location
        for el in root.iter():
            if _local(el.tag) == "URLBase" and el.text:
                base = el.text.strip()
        for svc in root.iter():
            if _local(svc.tag) != "service":
                continue
            fields = {_local(c.tag): (c.text or "").strip() for c in svc}
            if fields.get("serviceType") in IGD_SERVICES and fields.get("controlURL"):
                ctrl = urllib.parse.urljoin(base, fields["controlURL"])
                cu = urllib.parse.urlsplit(ctrl)
                if cu.scheme != "http" or cu.hostname != announced_by:
                    raise PortMapError(f"control URL {ctrl!r} points elsewhere")
                return cls(ctrl, fields["serviceType"])
        return None

    def _soap(self, action, args):
        body = "".join(f"<{k}>{v}</{k}>" for k, v in args)
        env = ('<?xml version="1.0"?>\r\n<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
               's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
               f'<u:{action} xmlns:u="{self.service}">{body}</u:{action}></s:Body></s:Envelope>')
        req = urllib.request.Request(self.control_url, data=env.encode("utf-8"), method="POST", headers={
            "Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{self.service}#{action}"'})
        try:
            with _opener().open(req, timeout=self.timeout) as r:
                root = ET.fromstring(_read_capped(r))
        except urllib.error.HTTPError as e:
            try:
                root = ET.fromstring(e.read(MAX_REPLY))
            except ET.ParseError:
                raise PortMapError(f"{action}: HTTP {e.code}") from None
            code = next((el.text for el in root.iter() if _local(el.tag) == "errorCode"), None)
            desc = next((el.text for el in root.iter() if _local(el.tag) == "errorDescription"), "")
            raise PortMapError(f"{action}: UPnP error {code} {desc}".strip()) from None
        return {_local(el.tag): (el.text or "") for el in root.iter()}

    def probe(self):
        return True

    def external_ip(self):
        try:
            ip = self._soap("GetExternalIPAddress", []).get("NewExternalIPAddress") or None
            ipaddress.IPv4Address(ip)
            return ip
        except (PortMapError, OSError, ValueError, TypeError):
            return None

    def add(self, proto, ext_port, int_port, client_ip, lifetime):
        args = [("NewRemoteHost", ""), ("NewExternalPort", ext_port), ("NewProtocol", proto),
                ("NewInternalPort", int_port), ("NewInternalClient", client_ip), ("NewEnabled", 1),
                ("NewPortMappingDescription", DESCRIPTION), ("NewLeaseDuration", lifetime)]
        try:
            self._soap("AddPortMapping", args)
        except PortMapError as e:
            if "725" not in str(e) or lifetime == 0:        # 725 OnlyPermanentLeasesSupported
                raise
            args[-1] = ("NewLeaseDuration", 0)
            self._soap("AddPortMapping", args)
            lifetime = 0
        return ext_port, lifetime

    def remove(self, proto, ext_port, int_port):
        self._soap("DeletePortMapping", [("NewRemoteHost", ""), ("NewExternalPort", ext_port),
                                         ("NewProtocol", proto)])


# ----------------------------------------------------------------------------- the front end
class PortMapper:
    def __init__(self, gateway=None, local_ip=None, dry_run=False, natpmp_port=NATPMP_PORT, ssdp_addr=SSDP_ADDR,
                 lifetime=3600, pcp=True):
        self.gateway = gateway
        self.local_ip = local_ip
        self.dry_run = dry_run
        self.natpmp_port = natpmp_port
        self.ssdp_addr = ssdp_addr
        self.lifetime = lifetime
        self.pcp = pcp
        self.backend = None
        self.mappings = {}         # (proto, ext_port) -> (int_port, lifetime, time made)

    def discover(self):
        if self.gateway is None and not self.dry_run:
            self.gateway = default_gateway()
        if self.local_ip is None:
            self.local_ip = local_ip_toward(self.gateway or "192.168.0.1") if not self.dry_run else "192.168.x.y"
        if self.dry_run:
            log.info("[dry run] would ask %s:%d (PCP, NAT-PMP), then multicast an SSDP search to %s:%d (UPnP)",
                     self.gateway or "<default gateway>", self.natpmp_port, *self.ssdp_addr)
            return False
        if self.gateway and not _private(self.gateway):
            log.warning("gateway %s is not a private address; not trying PCP / NAT-PMP", self.gateway)
        elif self.gateway:
            if self.pcp:
                pcp = Pcp(self.gateway, self.local_ip, self.natpmp_port)
                try:
                    if pcp.probe():
                        self.backend = pcp
                except PcpUnsupported:
                    pass
                except (PortMapError, OSError) as e:
                    log.info("PCP: %s", e)
            pmp = NatPmp(self.gateway, self.natpmp_port)
            try:
                if self.backend is None and pmp.probe():
                    self.backend = pmp
            except (PortMapError, OSError) as e:
                log.info("NAT-PMP: %s", e)
        if self.backend is None:
            try:
                self.backend = Upnp.discover(ssdp_addr=self.ssdp_addr,
                                             bind_ip=self.local_ip if self.local_ip and self.local_ip != "127.0.0.1" else "")
            except OSError as e:
                log.info("UPnP: %s", e)
        if self.backend:
            log.info("router port mapping via %s", self.backend.name)
        return self.backend is not None

    def external_ip(self):
        return self.backend.external_ip() if self.backend else None

    def add(self, proto, port, int_port=None):
        int_port = int_port or port
        if self.dry_run:
            log.info("[dry run] would map %s %d -> %s:%d for %d s", proto, port, self.local_ip, int_port, self.lifetime)
            return port
        if not self.backend:
            raise PortMapError("no router to talk to")
        mapped, life = self.backend.add(proto, port, int_port, self.local_ip, self.lifetime)
        self.mappings[(proto, mapped)] = (int_port, life, time.monotonic())
        log.info("router: %s %d -> %s:%d (%s)", proto, mapped, self.local_ip, int_port,
                 f"{life} s" if life else "permanent until removed")
        return mapped

    def renew(self):
        """Refresh mappings past half their lease. Call every few minutes while hosting."""
        now = time.monotonic()
        for (proto, ext), (int_port, life, made) in list(self.mappings.items()):
            if life and now - made > life / 2:
                try:
                    self.add(proto, ext, int_port)
                except (PortMapError, OSError) as e:
                    log.warning("renewing %s %d failed: %s", proto, ext, e)

    def remove_all(self):
        for (proto, ext), (int_port, _l, _m) in list(self.mappings.items()):
            try:
                self.backend.remove(proto, ext, int_port)
                log.info("router: removed %s %d", proto, ext)
            except (PortMapError, OSError) as e:
                log.warning("removing %s %d failed: %s", proto, ext, e)
            self.mappings.pop((proto, ext), None)


# ----------------------------------------------------------------------------- the game socket's port
def portmap_allowed():
    """False when T5_PORTMAP=0 (tests, or a player who wants the router left alone)."""
    return os.environ.get("T5_PORTMAP", "1").strip().lower() not in ("0", "off", "no", "false")


class GamePortMapper:
    """Forwards the game socket's port on the home router for the current match.

    start() looks for the router once, on a thread of its own (PCP / NAT-PMP answer in milliseconds, a
    UPnP search takes up to ~2 s; a player has logged in long before the first match). map(port) asks for
    external port = internal port: on most routers the forward then also carries the socket's outgoing
    packets, so the endpoint the lobby server sees *is* the forwarded one and even an opponent with an old
    launcher reaches it. The lease is 10 minutes, renew() keeps it while the match runs, unmap() ends it.
    A router that only takes permanent UPnP mappings is not used (a crash would leave the forward behind).
    backend_factory: callable -> an object with add/remove/external_ip (tests and the NAT simulator)."""

    def __init__(self, backend_factory=None, lifetime=600):
        self.backend_factory = backend_factory
        self.lifetime = lifetime
        self.backend = None
        self.local_ip = None
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.current = None           # (proto, ext_port, int_port, made, life)
        self.thread = None

    def start(self):
        if self.thread is not None:
            return self
        if self.backend_factory is None and not portmap_allowed():
            self.done.set()
            return self
        self.thread = threading.Thread(target=self._discover, name="t5lobby-portmap", daemon=True)
        self.thread.start()
        return self

    def _discover(self):
        try:
            if self.backend_factory is not None:
                self.backend = self.backend_factory()
                self.local_ip = "0.0.0.0"
            else:
                m = PortMapper(lifetime=self.lifetime)
                if m.discover():
                    self.backend, self.local_ip = m.backend, m.local_ip
        except Exception as e:      # noqa: BLE001 -- no router to talk to is the normal case
            log.info("router port mapping unavailable: %s", e)
        finally:
            self.done.set()

    def ready(self):
        return self.done.is_set() and self.backend is not None

    def map(self, port):
        """Forward UDP `port` -> this PC. -> (external ip or None, external port), or None."""
        if not self.ready():
            return None
        with self.lock:
            self._unmap_locked()
            try:
                ext, life = self.backend.add("UDP", port, port, self.local_ip, self.lifetime)
                if not life:                # permanent only: not for a game socket
                    self.backend.remove("UDP", ext, port)
                    return None
                self.current = ("UDP", ext, port, time.monotonic(), life)
                ip = None
                try:
                    ip = self.backend.external_ip()
                except (PortMapError, OSError):
                    pass
                log.info("router: game port UDP %d -> %s:%d for %d s", ext, self.local_ip, port, life)
                return ip, ext
            except (PortMapError, OSError, ValueError) as e:
                log.info("router: no forward for the game port %d: %s", port, e)
                return None

    def renew(self):
        with self.lock:
            if self.current is None:
                return
            proto_, ext, port, made, life = self.current
            if time.monotonic() - made < life / 2:
                return
            try:
                ext2, life2 = self.backend.add(proto_, ext, port, self.local_ip, self.lifetime)
                self.current = (proto_, ext2, port, time.monotonic(), life2 or life)
            except (PortMapError, OSError, ValueError) as e:
                log.info("router: renewing the game port failed: %s", e)

    def _unmap_locked(self):
        if self.current is None:
            return
        proto_, ext, port, _m, _l = self.current
        self.current = None
        try:
            self.backend.remove(proto_, ext, port)
        except (PortMapError, OSError, ValueError) as e:
            log.info("router: removing the game port failed: %s", e)

    def unmap(self):
        with self.lock:
            self._unmap_locked()
