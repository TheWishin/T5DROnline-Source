"""Ask the home router to forward ports to this PC: NAT-PMP (RFC 6886) or UPnP IGD, stdlib only.

Used ONLY by "Host for friends" when the player asks for it (`--map-ports`, the launcher's
"Open ports on my router" box). Nothing here runs otherwise. A mapping is made with a lease
(1 hour, renewed while hosting) and removed when hosting stops, so a crash leaves nothing behind
for longer than the lease -- except on routers that only take permanent UPnP mappings, which are
deleted on a clean stop.

    m = PortMapper()                       # finds the gateway, the PC's LAN address
    if m.discover():                       # NAT-PMP first, then UPnP (SSDP); False = no luck
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
            out = subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True, timeout=5,
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
                 lifetime=3600):
        self.gateway = gateway
        self.local_ip = local_ip
        self.dry_run = dry_run
        self.natpmp_port = natpmp_port
        self.ssdp_addr = ssdp_addr
        self.lifetime = lifetime
        self.backend = None
        self.mappings = {}         # (proto, ext_port) -> (int_port, lifetime, time made)

    def discover(self):
        if self.gateway is None and not self.dry_run:
            self.gateway = default_gateway()
        if self.local_ip is None:
            self.local_ip = local_ip_toward(self.gateway or "192.168.0.1") if not self.dry_run else "192.168.x.y"
        if self.dry_run:
            log.info("[dry run] would ask %s:%d (NAT-PMP), then multicast an SSDP search to %s:%d (UPnP)",
                     self.gateway or "<default gateway>", self.natpmp_port, *self.ssdp_addr)
            return False
        if self.gateway and not _private(self.gateway):
            log.warning("gateway %s is not a private address; not trying NAT-PMP", self.gateway)
        elif self.gateway:
            pmp = NatPmp(self.gateway, self.natpmp_port)
            try:
                if pmp.probe():
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
