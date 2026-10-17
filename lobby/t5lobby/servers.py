"""The launcher's list of lobby servers: servers.json.

Two files are read and merged (entries with the same name: the later file wins):

  1. lobby/servers.json in the release -- the servers the project publishes;
  2. servers.json next to the player's launcher.json -- servers the player added (friends).

Format ("format" is checked so that a future, incompatible layout is not misread):

    {
      "format": "t5dr-servers/1",
      "servers": [
        {
          "name": "T5DR Online (EU)",         shown in the launcher; unique
          "host": "lobby.example.org",       DNS name or IPv4 address; "" = placeholder, ignored
          "port": 7781,                      TCP control port (default 7781)
          "tls": "ca",                       "ca": certificate from a CA (Let's Encrypt), hostname checked
                                             "pin": self-signed, pinned by "fingerprint"
                                             "off": plain TCP (guests only, or a LAN)
          "fingerprint": "",                 SHA-256 of the certificate (hex, colons allowed), for "pin"
          "udp_ports": [7781, 7782],         informational (the server announces its UDP ports itself)
          "region": "EU", "note": "...",     informational
          "default": true                    preselected in the launcher
        }
      ]
    }

A server can also be typed in directly (and shared as one line):

    host[:port]                 plain TCP
    host[:port]#FINGERPRINT     TLS, self-signed certificate pinned by its SHA-256 (64 hex digits)
    tls://host[:port]           TLS with a CA-signed certificate
"""
import json
import os
import re
from dataclasses import dataclass, field

from .proto import DEFAULT_PORT, parse_hostport

FORMAT = "t5dr-servers/1"
TLS_MODES = ("off", "ca", "pin")
_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-\.]{0,251}[A-Za-z0-9])?$")
_FP_RE = re.compile(r"^[0-9a-f]{64}$")


def shipped_path():
    """lobby/servers.json next to the t5lobby package."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "servers.json")


def clean_fingerprint(fp):
    return (fp or "").replace(":", "").replace(" ", "").strip().lower()


@dataclass
class ServerEntry:
    name: str
    host: str
    port: int = DEFAULT_PORT
    tls: str = "off"
    fingerprint: str = ""
    region: str = ""
    note: str = ""
    default: bool = False
    udp_ports: list = field(default_factory=list)

    def __post_init__(self):
        self.fingerprint = clean_fingerprint(self.fingerprint)
        if self.tls == "pin" and not _FP_RE.match(self.fingerprint):
            raise ValueError(f"{self.name}: \"tls\": \"pin\" needs a 64-digit SHA-256 fingerprint")
        if self.tls not in TLS_MODES:
            raise ValueError(f"{self.name}: tls is one of {', '.join(TLS_MODES)}")
        if not (isinstance(self.port, int) and 0 < self.port < 65536):
            raise ValueError(f"{self.name}: bad port {self.port!r}")
        if not _HOST_RE.match(self.host or ""):
            raise ValueError(f"{self.name}: bad host {self.host!r}")

    @property
    def address(self):
        return f"{self.host}:{self.port}"

    def client_kwargs(self):
        """Keyword arguments for LobbyClient(...)."""
        return {"server": self.address, "tls": self.tls == "ca",
                "tls_fingerprint": self.fingerprint if self.tls == "pin" else None}

    def share_string(self):
        """One line a player can paste into the launcher's server field."""
        if self.tls == "pin":
            return f"{self.address}#{self.fingerprint}"
        if self.tls == "ca":
            return f"tls://{self.address}"
        return self.address

    def to_json(self):
        d = {"name": self.name, "host": self.host, "port": self.port, "tls": self.tls}
        if self.tls == "pin":
            d["fingerprint"] = self.fingerprint
        for k in ("region", "note"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.udp_ports:
            d["udp_ports"] = self.udp_ports
        if self.default:
            d["default"] = True
        return d

    @classmethod
    def from_json(cls, d):
        if not isinstance(d, dict):
            raise ValueError("server entries are objects")
        fp = clean_fingerprint(d.get("fingerprint"))
        tls = d.get("tls") or ("pin" if fp else "off")
        udp = d.get("udp_ports") or []
        return cls(name=str(d.get("name") or d.get("host") or "?")[:64], host=str(d.get("host", "")).strip(),
                   port=int(d.get("port", DEFAULT_PORT)), tls=str(tls), fingerprint=fp,
                   region=str(d.get("region", ""))[:32], note=str(d.get("note", ""))[:200],
                   default=bool(d.get("default", False)),
                   udp_ports=[int(x) for x in udp][:4] if isinstance(udp, list) else [])


def parse_address(text, name=None):
    """A typed-in server: 'host[:port]', 'host[:port]#fingerprint' or 'tls://host[:port]'."""
    text = text.strip()
    tls, fp = "off", ""
    if text.lower().startswith("tls://"):
        tls, text = "ca", text[6:]
    if "#" in text:
        text, fp = text.split("#", 1)
        tls = "pin"
    host, port = parse_hostport(text)
    return ServerEntry(name or text, host, port, tls, fp)


def load_file(path):
    """-> (entries, problems). Placeholders (empty host) are skipped silently."""
    entries, problems = [], []
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return entries, problems
    except (OSError, ValueError) as e:
        return entries, [f"{path}: {e}"]
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        return entries, [f"{path}: not a {FORMAT} file"]
    for d in doc.get("servers", [])[:100]:
        if isinstance(d, dict) and not str(d.get("host", "")).strip():
            continue
        try:
            entries.append(ServerEntry.from_json(d))
        except (ValueError, TypeError) as e:
            problems.append(f"{path}: {e}")
    return entries, problems


def load(user_dir=None, shipped=None):
    """The merged list: shipped servers, then the player's own. -> (entries, problems)."""
    merged, problems = {}, []
    paths = [shipped or shipped_path()]
    if user_dir:
        paths.append(os.path.join(user_dir, "servers.json"))
    for p in paths:
        es, pr = load_file(p)
        problems += pr
        for e in es:
            merged[e.name] = e
    return list(merged.values()), problems


def resolve(text, entries):
    """What the player picked or typed -> ServerEntry (a listed name, or an address)."""
    text = (text or "").strip()
    for e in entries:
        if text == e.name:
            return e
    return parse_address(text)


def default_entry(entries):
    for e in entries:
        if e.default:
            return e
    return entries[0] if entries else None


def save_user_entry(user_dir, entry):
    """Add or replace an entry in the player's own servers.json."""
    path = os.path.join(user_dir, "servers.json")
    doc = {"format": FORMAT, "servers": []}
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        if isinstance(old, dict) and old.get("format") == FORMAT:
            doc = old
    except (OSError, ValueError):
        pass
    doc["servers"] = [d for d in doc.get("servers", []) if not (isinstance(d, dict) and d.get("name") == entry.name)]
    doc["servers"].append(entry.to_json())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp, path)
    return path
