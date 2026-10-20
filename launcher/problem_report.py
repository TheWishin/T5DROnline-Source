"""One-click problem report: ONE zip on the Desktop with the logs and settings that help to find a
problem, made safe to send.

Nothing here imports tkinter or the launcher, so it runs (and is tested) from a console:

    python launcher/problem_report.py --out <native folder> [--dest-dir DIR] [--note "what happened"]

What goes in (each part only when it exists):
  system.txt     Windows, processor, graphics card + driver + memory, RAM, screens (refresh rate, DPI),
                 the release version and build id, the settings in use, a few lines of the game log
  report.txt     what the player wrote in "What happened?"
  logs/          the newest game log(s) and the frame logs next to them
  build.log      when the build is the problem
  compile/       with a failed build.log: the compiler's whole output of each file that failed in the last
                 build (native\\build\\gamedll_obj\\*.log, tools/build_game_dll.py), the newest few
  launcher.log   the launcher's own log
  online/        the lobby/online files of the last match (result, status, fight line, control files)
  controls.ini   when there is one
  desync/        np_desync_*.bin / rb_desync_*.bin (game state numbers of a desync, binary)
  replay/        the newest replay (native/replays, docs/REPLAYS.md): both players' inputs and the game's
                 state checks of the last online session, so the match can be played again here; the
                 players' names are taken out of it first (replays.strip_names)
  contents.txt   what is in the zip, what was shortened, what was removed

Privacy -- applied to every text file before it goes into the zip (class Scrubber):
  * the Windows user name in a path (C:\\Users\\NAME\\ and C:/Users/NAME/) becomes <user>, and the
    user and PC name anywhere else too
  * IPv4/IPv6 addresses of the internet become <ip> (a port after it stays); 127.x, ::1, private
    (10.x, 172.16-31.x, 192.168.x), link-local and unique-local addresses are kept as they are
  * passwords, tokens, match keys, cookies and the like (by name, by URL, and the exact values
    found in launcher.json, online.json and the control files) become <removed>; so does any hex
    string of 32+ digits and anything shaped like a lobby recovery code (XXXX-XXXX-XXXX)
  * e-mail addresses become <email>; the Sony package file name <package>.pkg; the company name in
    "OneDrive - Company" becomes <org>
  * lobby player names -- this player's and every opponent's -- become <player>: where the files name
    them (the fight HUD line of the game log, T5_HUD_NAMES / PS3_NICKNAME, a fight line's names=,
    the nickname setting) and wherever else a name found there appears (status lines in launcher.log
    ...). The names come from online.json, launcher.json, the control files, the fight files, the game
    logs' HUD lines and launcher.log's status lines (Context.player_names)
The lobby session token (online.json) and launcher.json are never read into the zip. Binary desync
dumps hold game state numbers only and are copied as they are.

Size: the members add up to at most `cap` bytes (20 MB default). Small files come first, then the
newest game log, then older ones; a log that does not fit keeps its start and its end and loses the
middle, with a marker line saying how much.
"""
import argparse
import collections
import ctypes
import datetime
import getpass
import glob
import ipaddress
import json
import os
import platform
import re
import struct
import urllib.parse
import sys
import zipfile

try:
    import replays          # launcher/replays.py (the last replay goes in without the players' names)
except ImportError:          # a copy without it: no replay in the report
    replays = None

TOOL_VERSION = 1
DEFAULT_CAP = 20 * 1024 * 1024
HEAD_SHARE = 0.25            # of a shortened file: this much from the start, the rest from the end
MIN_USEFUL = 8 * 1024        # a file that would get less than this room is left out instead
MANIFEST_ROOM = 24 * 1024    # kept free for contents.txt

# placeholders
P_USER, P_IP, P_REMOVED, P_EMAIL, P_ORG, P_PACKAGE, P_PC, P_HEX, P_PLAYER = (
    "<user>", "<ip>", "<removed>", "<email>", "<org>", "<package>", "<pc>", "<hex>", "<player>")


# --------------------------------------------------------------------------- scrubbing

# A user folder name cannot hold these (nor the path separators); spaces are fine.
_SEG_BAD = r'\\/:*?"<>|\[\];=,+\r\n'
# C:\Users\NAME\..., C:/Users/NAME/..., D:\Users\NAME (a moved profile), \Users\NAME, /Users/NAME.
# NAME may hold spaces when something that ends a path name follows (a separator, a quote, the end of
# the line); otherwise it is the first word ("--home C:\Users\Max --pkg C:\x" keeps "--pkg").
_USER_PATH = re.compile(
    r"(?P<pre>(?:[A-Za-z]:[\\/]+|(?<![\w:.\-/\\]))Users[\\/]+)"
    r"(?:(?P<n1>[^" + _SEG_BAD + r"]+?)(?=[\\/\"<>|\r\n]|\Z)|(?P<n2>[^" + _SEG_BAD + r"\s]+))", re.I)
_SHARED_PROFILES = {"public", "default", "default user", "all users", P_USER}
# A user called like a word our logs are full of ("game" in "[game-dll]") is only replaced inside
# paths (C:\Users\game\...), not as a bare word: that would wreck every log line.
_LOG_WORDS = {"game", "games", "build", "native", "logs", "log", "online", "user", "users", "public", "default",
              "guest", "test", "tekken", "player", "windows", "system", "desktop", "documents", "downloads",
              "python", "launcher", "release", "runtime", "tools", "lobby", "server", "client", "match", "fight",
              "pad", "audio", "video", "input", "output", "pc", "ip", "org", "hex", "email", "boot", "scratch"}

_ONEDRIVE_ORG = re.compile(r"(OneDrive - )([^\\/:*?\"<>|\r\n]+?)(?=[\\/\"<>|\r\n]|\Z)", re.I)
_EMAIL = re.compile(r"(?<![\w.+\-])[\w.+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
_PACKAGE = re.compile(r"[A-Za-z0-9_\-]{40,}\.pkg", re.I)
_LONG_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{32,}(?![0-9A-Za-z])")
# A lobby account's recovery code (XXXX-XXXX-XXXX, lobby/t5lobby/server/store.py): name + code resets the password
_RC = "[A-HJKMNP-Z2-9]"
_RECOVERY_CODE = re.compile(r"(?<![A-Za-z0-9-])" + _RC + "{4}-" + _RC + "{4}-" + _RC + r"{4}(?![A-Za-z0-9-])", re.I)

_V4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w)(?!\.\d)")
# a run of hex digits, colons and dots that holds at least two colons (the start rule keeps this linear)
_V6 = re.compile(r"(?<![\w:.])(?=[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*:)[0-9A-Fa-f:.]{3,}")

# Names of things that hold a secret: password, token, secret, cookie, session id, api key, auth,
# and "...KEY" with an underscore or dash before it (T5_NET_KEY). A bare "key" is not one in a log
# (the game log has "key=0x6E754149" event queue ids); in a JSON file it is. The name has to start at
# the start of a word so that a long run of letters is scanned once.
_SECRET_WORDS = (r"(?:token|secret|passw(?:or)?d|passwd|pwd|passphrase|api[_\-]?key|apikey|auth(?:orization)?|"
                 r"credential|cookie|session[_\-]?id|[_\-]key|keyfile)")
_NAME_CHARS = r"[A-Za-z0-9_.\-]*"
_SECRET_NAME = r"(?<![A-Za-z0-9_.\-])" + _NAME_CHARS + _SECRET_WORDS + _NAME_CHARS
_DQ = r'"(?:[^"\n\\]|\\.)*"'                    # "a double quoted value with \" escapes"
_SQ = r"'[^'\n]*'"
_SECRET_KV = re.compile(
    r"(?P<name>" + _SECRET_NAME + r")(?P<q>[\"']?)(?P<sep>[ \t]*[:=][ \t]*)"
    r"(?P<val>" + _DQ + "|" + _SQ + r"|(?:Bearer|Basic|Token)[ \t]+[^\s,;&\"']+|[^\s,;&\"'}\]]+)", re.I)
_SECRET_FLAG = re.compile(
    r"(?<![\w\-])(--?[A-Za-z0-9\-]*(?:token|secret|password|passwd|pwd|passphrase|api-?key)[A-Za-z0-9\-]*)"
    r"([ \t]+)(" + _DQ + r"|[^\s\-][^\s]*)", re.I)
_URL_USERINFO = re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+@")
_BEARER = re.compile(r"\b(Bearer|Basic)[ \t]+[A-Za-z0-9._~+/=\-]{8,}", re.I)
_SECRET_KEY_NAME = re.compile(_NAME_CHARS + _SECRET_WORDS + _NAME_CHARS + r"|key", re.I)   # a whole JSON key

_ENV_PREFIXES = ("PS3_", "T5_", "RSX_", "SPURS_", "ATRAC_", "LD_", "PAD_")

# Where the files name lobby players (direct fight's HUD line, the launcher's environment for the game,
# a fight line, the nickname setting). The value is replaced whatever the name is.
_NAME_KEYS = r"(?:T5_HUD_NAMES|PS3_NICKNAME|PS3_TITLE)"
_HUD_IDENTITY = re.compile(r"(HUD identity: P1 ')(.*?)(' rank -?\d+, P2 ')(.*?)(')")
_NAME_ENV = re.compile(r"(?<![A-Za-z0-9_])(" + _NAME_KEYS + r"=)([^\r\n,]*)")
_NAME_JSON = re.compile(r'("(?:' + _NAME_KEYS + r'|nickname)"\s*:\s*")((?:[^"\\\n]|\\.)*)(")', re.I)
_FIGHT_NAMES = re.compile(r"(?<![A-Za-z0-9_])(names=)(\S+)")
# Status lines the launcher logs that hold an opponent's name (launcher.log): harvested, then replaced everywhere
_STATUS_NAMES = (re.compile(r"(?:Playing|Rematch) against (.{2,16}?)(?: --|:| \()"),
                 re.compile(r"Opponent: (.{2,16}?) \("),
                 re.compile(r"(?:^|status: |notice: )(.{2,16}?) (?:lost the lobby connection|is back in the lobby)", re.M),
                 re.compile(r"(?:^|status: |notice: )(.{2,16}?)'s PC ran its last match", re.M),
                 re.compile(r"(?:Blocked|Unblocked|Block) (.{2,16}?)(?:\.|\?| --|$)", re.M),
                 re.compile(r"(?:^|status: )(.{2,16}?) wants a rematch", re.M))


def _is_public(ip):
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


class Scrubber:
    """Removes what must not leave the PC from text. `counts` says what was replaced.

    secrets      exact values to remove wherever they appear (tokens read from online.json ...)
    user_names   names of the Windows user (default: the one running this); replaced everywhere
    pc_names     name of this PC (default: COMPUTERNAME)
    player_names lobby names (this player's, the opponents'): replaced everywhere (3+ characters)
    keep         hex strings that may stay (the game program's SHA-1)
    """

    def __init__(self, secrets=(), user_names=None, pc_names=None, keep=(), player_names=()):
        self.counts = collections.Counter()
        self.secrets = sorted({s for s in secrets if isinstance(s, str) and len(s) >= 6}, key=len, reverse=True)
        self.keep = {k.lower() for k in keep}
        if user_names is None:
            try:
                login = getpass.getuser()
            except (ImportError, KeyError, OSError):
                login = ""
            user_names = {login, os.environ.get("USERNAME", ""),
                          os.path.basename(os.path.expanduser("~").rstrip("\\/"))}
        if pc_names is None:
            pc_names = {os.environ.get("COMPUTERNAME", "")}
        self._name_res = []
        for names, repl, key in ((user_names, P_USER, "user"), (pc_names, P_PC, "pc")):
            for n in sorted({n.strip() for n in names if n and len(n.strip()) >= 3}, key=len, reverse=True):
                if n.lower() in _SHARED_PROFILES or n.lower() in _LOG_WORDS:
                    continue
                self._name_res.append((re.compile(r"(?<![A-Za-z0-9_<])" + re.escape(n) + r"(?![A-Za-z0-9_>])", re.I),
                                       repl, key))
        # Lobby names anywhere in the text: 3 characters or more, and not a word the logs are full of (a
        # player called "Fight" keeps the logs readable; the places that name players are still cleaned).
        players = sorted({n.strip() for n in player_names if isinstance(n, str) and len(n.strip()) >= 3
                          and n.strip().lower() not in _LOG_WORDS and n.strip().lower() not in _SHARED_PROFILES},
                         key=len, reverse=True)
        self._player_re = re.compile(r"(?<![A-Za-z0-9_<])(?:" + "|".join(re.escape(n) for n in players)
                                     + r")(?![A-Za-z0-9_>])", re.I) if players else None

    # ---- parts
    def _secret_kv(self, m):
        val = m.group("val")
        self.counts["secret"] += 1
        quoted = val[:1] in "\"'"
        return m.group("name") + m.group("q") + m.group("sep") + (f"{val[0]}{P_REMOVED}{val[0]}" if quoted
                                                                   else P_REMOVED)

    def _flag(self, m):
        self.counts["secret"] += 1
        return m.group(1) + m.group(2) + P_REMOVED

    def _user(self, m):
        name = (m.group("n1") or m.group("n2") or "").strip()
        if name.lower() in _SHARED_PROFILES:
            return m.group(0)
        self.counts["user"] += 1
        return m.group("pre") + P_USER

    def _players(self, s):
        """Lobby player names: the places that name them, then the known names anywhere."""
        def hud(m):
            self.counts["player"] += 2
            return m.group(1) + P_PLAYER + m.group(3) + P_PLAYER + m.group(5)

        def value(m):
            v = m.group(2)
            if not v.strip() or v.startswith(P_PLAYER):
                return m.group(0)
            self.counts["player"] += 1
            return m.group(1) + P_PLAYER + (m.group(3) if m.re.groups >= 3 else "")
        s = _HUD_IDENTITY.sub(hud, s)
        s = _NAME_JSON.sub(value, s)
        s = _NAME_ENV.sub(value, s)
        s = _FIGHT_NAMES.sub(value, s)
        if self._player_re is not None:
            s = self._player_re.sub(lambda m: (self._count("player") or P_PLAYER), s)
        return s

    def _hex(self, m):
        if m.group(0).lower() in self.keep:
            return m.group(0)
        self.counts["secret"] += 1
        return P_HEX

    def _v4(self, m):
        t = m.group(0)
        try:
            ip = ipaddress.IPv4Address(t)
        except ValueError:
            return t
        if not _is_public(ip):
            return t
        self.counts["ip"] += 1
        return P_IP

    def _v6(self, m):
        s = m.group(0)
        if s.count(":") < 3 and not any(c.isdigit() for c in s):
            return s                                  # a C++ name like add::dec, not an address
        tail = ""
        while True:
            try:
                ip = ipaddress.IPv6Address(s)
                break
            except ValueError:
                if len(s) <= 3 or s[-1] not in ":.":
                    return m.group(0)
                s, tail = s[:-1], s[-1] + tail
        if not _is_public(ip):
            return m.group(0)
        self.counts["ip"] += 1
        return P_IP + tail

    def text(self, s):
        if not s:
            return s
        for v in self.secrets:                        # exact values first: they may sit inside anything
            if v in s:
                self.counts["secret"] += s.count(v)
                s = s.replace(v, P_REMOVED)
        s = _URL_USERINFO.sub(lambda m: (self._count("secret") or P_REMOVED + "@"), s)
        s = _BEARER.sub(lambda m: (self._count("secret") or m.group(1) + " " + P_REMOVED), s)
        s = _SECRET_KV.sub(self._secret_kv, s)
        s = _SECRET_FLAG.sub(self._flag, s)
        s = _LONG_HEX.sub(self._hex, s)
        s = _RECOVERY_CODE.sub(lambda m: (self._count("secret") or P_REMOVED), s)
        s = _USER_PATH.sub(self._user, s)
        s = _ONEDRIVE_ORG.sub(lambda m: (self._count("user") or m.group(1) + P_ORG), s)
        for rx, repl, key in self._name_res:
            s = rx.sub(lambda m, repl=repl, key=key: (self._count(key) or repl), s)
        s = self._players(s)
        s = _EMAIL.sub(lambda m: (self._count("email") or P_EMAIL), s)
        s = _PACKAGE.sub(lambda m: (self._count("user") or P_PACKAGE + ".pkg"), s)
        s = _V6.sub(self._v6, s)
        s = _V4.sub(self._v4, s)
        return s

    def _count(self, key):
        self.counts[key] += 1
        return None

    def clean(self, s):
        """True when a second pass would change nothing (the first one got everything)."""
        saved = collections.Counter(self.counts)
        again = self.text(s)
        self.counts = saved
        return again == s


def scrub_text(s, **kw):
    """One-shot scrub with a fresh Scrubber (tests, small uses)."""
    return Scrubber(**kw).text(s)


def harvest_secrets(obj, found=None, hint=False):
    """Every string value in a parsed JSON document whose key looks like a secret (token, password,
    secret, key ...): these exact values are then removed from every file, whatever they sit next to."""
    found = set() if found is None else found
    if isinstance(obj, dict):
        for k, v in obj.items():
            secret_key = bool(_SECRET_KEY_NAME.fullmatch(str(k)))
            if secret_key and isinstance(v, str):
                found.add(v)
            else:
                harvest_secrets(v, found, secret_key)
    elif isinstance(obj, list):
        for v in obj:
            harvest_secrets(v, found, hint)
    elif isinstance(obj, str) and hint:
        found.add(obj)
    return found


def read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- reading files with a cap

def read_capped(path, limit):
    """(bytes, removed) -- the file, or when it is bigger than `limit`: its start and its end with
    a marker line between (cut at line ends). `removed` is the number of bytes left out."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size <= limit:
                return f.read(), 0
            return cut_middle(f, size, limit)
    except OSError:
        return b"", 0


def cut_middle(f, size, limit):
    marker_room = 200
    keep = max(limit - marker_room, 0)
    head_n = int(keep * HEAD_SHARE)
    tail_n = keep - head_n
    f.seek(0)
    head = f.read(head_n)
    cut = head.rfind(b"\n")
    if cut >= 0:
        head = head[:cut + 1]
    f.seek(max(size - tail_n, len(head)))
    tail = f.read()
    nl = tail.find(b"\n")
    if 0 <= nl < len(tail) - 1 and size - tail_n > len(head):
        tail = tail[nl + 1:]
    removed = size - len(head) - len(tail)
    marker = (f"\n[... T5DR report: {removed:,} bytes removed here to keep the report small; "
              f"the start and the end of the file are kept ...]\n").encode()
    return head + marker + tail, removed


# --------------------------------------------------------------------------- system information

def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def _reg(path, name, root=None):
    wr = _winreg()
    if wr is None:
        return None
    try:
        with wr.OpenKey(root if root is not None else wr.HKEY_LOCAL_MACHINE, path) as k:
            return wr.QueryValueEx(k, name)[0]
    except OSError:
        return None


def windows_version():
    if os.name != "nt":
        return platform.platform()
    cv = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    name = _reg(cv, "ProductName") or "Windows"
    build = str(_reg(cv, "CurrentBuild") or sys.getwindowsversion().build)
    if build.isdigit() and int(build) >= 22000 and name.startswith("Windows 10"):
        name = "Windows 11" + name[len("Windows 10"):]       # the registry still says Windows 10
    disp = _reg(cv, "DisplayVersion") or _reg(cv, "ReleaseId") or ""
    ubr = _reg(cv, "UBR")
    edition = _reg(cv, "EditionID") or ""
    arch = platform.machine() or "?"
    text = f"{name} {disp}".strip() + f" (build {build}" + (f".{ubr}" if ubr is not None else "") + f"), {arch}"
    if edition.endswith("N"):
        text += f", edition {edition} (\"N\": Media Foundation is an optional feature)"
    return text


def _physical_cores():
    if os.name != "nt":
        return None
    try:
        k = ctypes.windll.kernel32
        n = ctypes.c_ulong(0)
        k.GetLogicalProcessorInformationEx(0, None, ctypes.byref(n))
        if not n.value:
            return None
        buf = ctypes.create_string_buffer(n.value)
        if not k.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(n)):
            return None
        off = cores = 0
        while off + 8 <= n.value:
            rel, size = struct.unpack_from("<II", buf, off)
            if size == 0:
                break
            cores += rel == 0
            off += size
        return cores or None
    except (OSError, AttributeError, struct.error):
        return None


def cpu_info():
    name = " ".join(str(_reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
                        or platform.processor() or "?").split())
    logical = os.cpu_count()
    cores = _physical_cores()
    feats = []
    if os.name == "nt":
        try:
            k = ctypes.windll.kernel32
            feats = [n for n, i in (("SSE4.1", 37), ("AVX", 39), ("AVX2", 40), ("AVX-512", 41))
                     if k.IsProcessorFeaturePresent(i)]
        except (OSError, AttributeError):
            pass
    return (f"{name}; {cores if cores else '?'} cores, {logical} logical processors"
            + (f"; {', '.join(feats)}" if feats else ""))


def memory_info():
    if os.name != "nt":
        return "?"

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return f"{m.ullTotalPhys / 2**30:.1f} GB total, {m.ullAvailPhys / 2**30:.1f} GB free"
    except (OSError, AttributeError):
        return "?"


def gpu_info():
    """[(name, driver version, driver date, VRAM bytes or None)] from the display adapter class key."""
    wr = _winreg()
    out = []
    if wr is None:
        return out
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    for i in range(32):
        p = base + "\\%04d" % i
        desc = _reg(p, "DriverDesc")
        if not desc:
            continue
        mem = _reg(p, "HardwareInformation.qwMemorySize")
        if isinstance(mem, bytes):
            mem = int.from_bytes(mem[:8], "little")
        if not mem:
            m32 = _reg(p, "HardwareInformation.MemorySize")
            mem = int.from_bytes(m32[:4], "little") if isinstance(m32, bytes) else m32
        out.append((str(desc), str(_reg(p, "DriverVersion") or "?"), str(_reg(p, "DriverDate") or "?"),
                    mem if isinstance(mem, int) and mem > 0 else None))
    return out


def display_info():
    """[dict(device, width, height, hz, dpi, primary)] for every screen that is part of the desktop."""
    if os.name != "nt":
        return []
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class DEVMODEW(ctypes.Structure):
        _fields_ = [("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", ctypes.c_ushort),
                    ("dmDriverVersion", ctypes.c_ushort), ("dmSize", ctypes.c_ushort),
                    ("dmDriverExtra", ctypes.c_ushort), ("dmFields", ctypes.c_ulong),
                    ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                    ("dmDisplayOrientation", ctypes.c_ulong), ("dmDisplayFixedOutput", ctypes.c_ulong),
                    ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
                    ("dmFormName", ctypes.c_wchar * 32), ("dmLogPixels", ctypes.c_ushort),
                    ("dmBitsPerPel", ctypes.c_ulong), ("dmPelsWidth", ctypes.c_ulong),
                    ("dmPelsHeight", ctypes.c_ulong), ("dmDisplayFlags", ctypes.c_ulong),
                    ("dmDisplayFrequency", ctypes.c_ulong), ("dmICMMethod", ctypes.c_ulong),
                    ("dmICMIntent", ctypes.c_ulong), ("dmMediaType", ctypes.c_ulong),
                    ("dmDitherType", ctypes.c_ulong), ("dmReserved1", ctypes.c_ulong),
                    ("dmReserved2", ctypes.c_ulong), ("dmPanningWidth", ctypes.c_ulong),
                    ("dmPanningHeight", ctypes.c_ulong)]

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("DeviceName", ctypes.c_wchar * 32),
                    ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", ctypes.c_ulong),
                    ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong), ("szDevice", ctypes.c_wchar * 32)]

    dpi_by_device = {}
    try:
        MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                             ctypes.POINTER(RECT), wintypes.LPARAM)
        shcore = ctypes.windll.shcore

        def on_monitor(hmon, _dc, _rc, _lp):
            mi = MONITORINFOEXW()
            mi.cbSize = ctypes.sizeof(mi)
            dx, dy = ctypes.c_uint(0), ctypes.c_uint(0)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)) and \
                    shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0:
                dpi_by_device[mi.szDevice] = dx.value
            return 1
        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(on_monitor), 0)
    except (OSError, AttributeError):
        pass

    out = []
    i = 0
    while i < 16:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(dd)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        i += 1
        if not dd.StateFlags & 0x1:                  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
            continue
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(dm)
        if user32.EnumDisplaySettingsW(dd.DeviceName, -1, ctypes.byref(dm)):    # ENUM_CURRENT_SETTINGS
            out.append(dict(device=dd.DeviceName, width=dm.dmPelsWidth, height=dm.dmPelsHeight,
                            hz=dm.dmDisplayFrequency, dpi=dpi_by_device.get(dd.DeviceName),
                            primary=bool(dd.StateFlags & 0x4)))
    return out


def system_dpi():
    try:
        return int(ctypes.windll.user32.GetDpiForSystem())
    except (OSError, AttributeError):
        return None


def display_adapters():
    """{device name: adapter name} for every screen in the desktop (which graphics chip drives it: on a
    laptop with two GPUs the screen hangs off the integrated one)."""
    if os.name != "nt":
        return {}

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("DeviceName", ctypes.c_wchar * 32),
                    ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", ctypes.c_ulong),
                    ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]
    out = {}
    try:
        for i in range(16):
            dd = DISPLAY_DEVICEW()
            dd.cb = ctypes.sizeof(dd)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.StateFlags & 0x1:
                out[dd.DeviceName] = dd.DeviceString
    except (OSError, AttributeError):
        pass
    return out


# Windows' built-in power plans and the Windows 10/11 "power mode" slider (overlay schemes).
POWER_PLANS = {"381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced",
               "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "High performance",
               "a1841308-3541-4fab-bc81-f71556f20b4a": "Power saver",
               "e9a42b02-d5df-448d-aa00-03f14749eb61": "Ultimate Performance"}
POWER_MODES = {"00000000-0000-0000-0000-000000000000": "Balanced",
               "961cc777-2547-4f9d-8174-7d86181b8a7a": "Best power efficiency",
               "3af9b8d9-7c97-431d-ad78-34a8bfea439f": "Better performance",
               "ded574b5-45a0-4f42-8737-46345c09c238": "Best performance"}


def power_plan_info():
    """'Power plan: <name> (<guid>); power mode on AC / battery: ...' from the registry."""
    key = r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes"
    guid = str(_reg(key, "ActivePowerScheme") or "").lower()
    if not guid:
        return "?"
    name = POWER_PLANS.get(guid)
    if not name:
        fn = _reg(key + "\\" + guid, "FriendlyName")
        name = str(fn).rsplit(",", 1)[-1] if fn else "custom plan"
    text = f"{name} ({guid})"
    modes = []
    for label, val in (("on AC", "ActiveOverlayAcPowerScheme"), ("on battery", "ActiveOverlayDcPowerScheme")):
        g = str(_reg(key, val) or "").lower()
        if g:
            modes.append(f"{label} {POWER_MODES.get(g, g)}")
    if modes:
        text += "; power mode " + ", ".join(modes)
    return text


def power_source_info():
    """AC or battery, the charge, battery saver; 'desktop' when there is no battery."""
    if os.name != "nt":
        return "?"

    class SPS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    s = SPS()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return "?"
    except (OSError, AttributeError):
        return "?"
    if s.BatteryFlag in (128, 255):
        return "no battery (a desktop PC)" + (", on AC power" if s.ACLineStatus == 1 else "")
    src = {0: "on battery", 1: "on AC power"}.get(s.ACLineStatus, "power source unknown")
    pct = f", battery {s.BatteryLifePercent} %" if s.BatteryLifePercent <= 100 else ""
    return src + pct + (", battery saver on" if s.SystemStatusFlag & 1 else "")


def processor_clock_info():
    """The processor's clock limit against its maximum (CallNtPowerInformation): a limit below the
    maximum means the processor is held back right now -- heat, or the power plan."""
    if os.name != "nt":
        return "?"

    class PPI(ctypes.Structure):
        _fields_ = [("Number", ctypes.c_ulong), ("MaxMhz", ctypes.c_ulong), ("CurrentMhz", ctypes.c_ulong),
                    ("MhzLimit", ctypes.c_ulong), ("MaxIdleState", ctypes.c_ulong), ("CurrentIdleState", ctypes.c_ulong)]
    n = os.cpu_count() or 1
    arr = (PPI * n)()
    try:
        if ctypes.windll.powrprof.CallNtPowerInformation(11, None, 0, ctypes.byref(arr), ctypes.sizeof(arr)) != 0:
            return "?"
    except (OSError, AttributeError):
        return "?"
    mx = max(p.MaxMhz for p in arr)
    lim = min((p.MhzLimit for p in arr if p.MhzLimit), default=mx)
    if not mx:
        return "?"
    text = f"clock limit {lim} of {mx} MHz"
    if lim * 100 < mx * 97:
        text += " (held back right now: heat or the power plan)"
    return text


def thermal_info(sample_s=0.25):
    """Temperatures of the ACPI thermal zones and the processor's performance limit, from Windows'
    performance counters (no administrator rights needed; many laptops report a zone, many desktops
    none). '' when Windows has none."""
    if os.name != "nt":
        return ""
    try:
        pdh = ctypes.windll.pdh
    except OSError:
        return ""
    q = ctypes.c_void_p()
    if pdh.PdhOpenQueryW(None, None, ctypes.byref(q)) != 0:
        return ""
    parts = []
    try:
        counters = {}
        for name, path in (("temp", r"\Thermal Zone Information(*)\Temperature"),
                           ("limit", r"\Processor Information(_Total)\% Performance Limit"),
                           ("perf", r"\Processor Information(_Total)\% Processor Performance")):
            h = ctypes.c_void_p()
            if pdh.PdhAddEnglishCounterW(q, ctypes.c_wchar_p(path), None, ctypes.byref(h)) == 0:
                counters[name] = h
        if not counters:
            return ""
        pdh.PdhCollectQueryData(q)
        import time as _time
        _time.sleep(sample_s)
        pdh.PdhCollectQueryData(q)

        class FMT(ctypes.Structure):
            _fields_ = [("CStatus", ctypes.c_ulong), ("pad", ctypes.c_ulong), ("doubleValue", ctypes.c_double)]

        class ITEM(ctypes.Structure):
            _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", FMT)]
        if "temp" in counters:
            size, count = ctypes.c_ulong(0), ctypes.c_ulong(0)
            pdh.PdhGetFormattedCounterArrayW(counters["temp"], 0x200, ctypes.byref(size), ctypes.byref(count), None)
            if size.value:
                buf = ctypes.create_string_buffer(size.value)
                if pdh.PdhGetFormattedCounterArrayW(counters["temp"], 0x200, ctypes.byref(size), ctypes.byref(count),
                                                    buf) == 0:
                    items = ctypes.cast(buf, ctypes.POINTER(ITEM))
                    temps = []
                    for i in range(count.value):
                        k = items[i].FmtValue.doubleValue
                        if items[i].FmtValue.CStatus in (0, 1) and 200 < k < 400:      # Kelvin
                            temps.append(f"{k - 273.15:.0f} C")
                    if temps:
                        parts.append("thermal zones " + ", ".join(temps[:6]))
        for name, label in (("perf", "processor performance %.0f %% of nominal"),
                            ("limit", "performance limit %.0f %%")):
            if name in counters:
                v = FMT()
                if pdh.PdhGetFormattedCounterValue(counters[name], 0x200, None, ctypes.byref(v)) == 0 and \
                        v.CStatus in (0, 1):
                    parts.append(label % v.doubleValue)
    except (OSError, AttributeError, ValueError):
        pass
    finally:
        pdh.PdhCloseQuery(q)
    return ", ".join(parts)


def _gb(n):
    return f"{n / 2**30:.0f} GB" if n >= 2**30 else f"{n / 2**20:.0f} MB"


GAME_LOG_FACTS = re.compile(r"^\[(?:gpu|display|pacing|cpu|sched|game-dll|netplay|power)\] "
                            r"(?:adapter|res_scale|window on|display|stage blur|FATAL|CPU budget|built for|mode |lobby match|"
                            r"power saving|on AC|on battery|power source)")
# Lines that sum up how the game ran (patch 0047: slow frames with their reason, the display lock's
# late frames); the last few of each kind go into system.txt.
GAME_LOG_RUN = re.compile(r"^\[(?:slow-frames|pacing\] display lock:|cellAudio\] sound glitches)")


def facts_from_log(path, limit=12):
    """The few start-up lines of a game log that say what the game found on this PC."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f):
                if n > 4000 or len(out) >= limit:
                    break
                if GAME_LOG_FACTS.match(line):
                    out.append(line.rstrip()[:200])
    except OSError:
        pass
    return out


def run_lines_from_log(path, keep=4, limit=64 * 1024 * 1024):
    """The last `keep` lines of each kind GAME_LOG_RUN matches (slow frames, display lock, sound)."""
    last = collections.OrderedDict()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            read = 0
            for line in f:
                read += len(line)
                if read > limit:
                    break
                m = GAME_LOG_RUN.match(line)
                if m:
                    q = last.setdefault(m.group(0), collections.deque(maxlen=keep))
                    q.append(line.rstrip()[:600])
    except OSError:
        pass
    return [ln for q in last.values() for ln in q]


def system_text(ctx, now=None, game_log=None):
    """The text of system.txt (not yet scrubbed)."""
    now = now or datetime.datetime.now()
    rel = ctx.release or {}
    bi = ctx.build_info or {}
    L = ["T5DR Online problem report -- system information",
         f"Made: {now:%Y-%m-%d %H:%M:%S} (this PC's time), report tool {TOOL_VERSION}", ""]
    L += ["== Program ==",
          f"Release: {rel.get('version', '?')} ({rel.get('name', '?')})",
          f"Build id: {bi.get('build_id') or '?'}   (players only meet with the same build id)",
          f"Code id: {bi.get('code_id') or rel.get('code_id') or '?'}   Netplay protocol: {bi.get('net', '?')}",
          f"Game program SHA-1: {bi.get('elf_sha1') or '?'}",
          f"Built here: {bi.get('built') or '?'}   Compiler: {rel.get('llvm', '?')}   "
          f"Prebuilt runtime: {rel.get('prebuilt_host', '?')}",
          f"Source commit: {rel.get('commit') or '?'}   ps3recomp: {rel.get('ps3recomp', '?')}",
          f"Launcher Python: {platform.python_version()} ({platform.architecture()[0]})", ""]
    L += ["== This PC ==", f"Windows: {windows_version()}", f"Processor: {cpu_info()}", f"Memory: {memory_info()}"]
    gpus = gpu_info()
    for g in gpus or [("?", "?", "?", None)]:
        L.append(f"Graphics: {g[0]}, driver {g[1]} ({g[2]})" + (f", {_gb(g[3])} video memory" if g[3] else ""))
    sd = system_dpi()
    adapters = display_adapters()
    for d in display_info() or []:
        scale = f", DPI {d['dpi']} ({round(d['dpi'] * 100 / 96)} %)" if d["dpi"] else (
            f", system DPI {sd} ({round(sd * 100 / 96)} %)" if sd else "")
        on = adapters.get(d["device"])
        L.append(f"Screen {d['device'].lstrip(chr(92) + '.')}: {d['width']} x {d['height']} at {d['hz']} Hz{scale}"
                 + (" (main screen)" if d["primary"] else "") + (f", driven by {on}" if on else ""))
    L.append("")
    # Laptops: "the game gets slower after a while" is mostly heat or the power plan (docs/TROUBLESHOOTING.md
    # "Game speeds up or slows down on a laptop"). Read now, after the game: the game log's [power] and
    # [slow-frames] lines below say how it was while playing.
    L += ["== Power and heat (now) ==",
          f"Power: {power_source_info()}",
          f"Power plan: {power_plan_info()}",
          f"Processor: {processor_clock_info()}"]
    th = thermal_info()
    L.append(f"Sensors: {th}" if th else "Sensors: (Windows reports no temperature here)")
    L.append("")
    L += ["== Settings in use ==", *(ctx.settings_lines or ["(none)"]), ""]
    env = sorted((k, v) for k, v in os.environ.items() if k.upper().startswith(_ENV_PREFIXES))
    L.append("== Environment variables the game would see from Windows ==")
    L += [f"{k}={v}" for k, v in env] or ["(none)"]
    if game_log:
        facts = facts_from_log(game_log)
        if facts:
            L += ["", f"== From {os.path.basename(game_log)} ==", *facts]
        run = run_lines_from_log(game_log)
        if run:
            L += ["", f"== How the game ran ({os.path.basename(game_log)}) ==", *run]
    return "\n".join(L) + "\n"


SETTING_KEYS = ("display", "internal_res", "vsync", "stage_blur", "power_saving", "input_delay", "mute", "background",
                "low_priority", "unlock_stages", "unlock_items")


def settings_lines(settings, labels=None, env_overrides=None, out_dir=None):
    """The 'settings in use' lines of system.txt from the launcher's settings (a dict). `labels`:
    {key: {value: text}} for display, internal_res, vsync, stage_blur and input_delay. File paths of the .pkg/.rap are
    not listed (only whether they are set); a password could not be in here: only these keys are read."""
    labels = labels or {}
    st = settings or {}

    def lab(key):
        v = st.get(key)
        t = (labels.get(key) or {}).get(v)
        return f"{t} [{v}]" if t else str(v)
    yesno = lambda v: "yes" if v else "no"      # noqa: E731
    L = [f"Window and resolution: {lab('display')}",
         f"Internal resolution: {lab('internal_res')}",
         f"VSync: {lab('vsync')}",
         f"Stage blur / glow: {lab('stage_blur')}",
         f"Power saving (laptops, handhelds): {lab('power_saving')}",
         f"Online input delay (netcode): {lab('input_delay')}",
         f"Mute sound: {yesno(st.get('mute'))}",
         f"Start minimized without focus: {yesno(st.get('background'))}",
         f"Build at low priority: {yesno(st.get('low_priority'))}",
         f"Unlock all stages (offline): {yesno(st.get('unlock_stages'))}",
         f"Unlock all customization items (offline): {yesno(st.get('unlock_items'))}",
         f"Player name set: {yesno((st.get('nickname') or '').strip())}",
         f"Package and license chosen: {yesno(st.get('pkg') and st.get('rap'))}"]
    if out_dir:
        L.append(f"Output folder: {out_dir}")
    extra = [ln.strip() for ln in str(st.get("extra_env") or "").splitlines() if ln.strip()]
    L.append("Extra settings: " + ("" if extra else "(none)"))
    L += [f"    {ln}" for ln in extra]
    if env_overrides:
        L.append("Environment the launcher gives the game: " + ", ".join(f"{k}={v}" for k, v in sorted(env_overrides.items())))
    return L


def build_info_for(out_dir, release=None, root=None):
    """dict(build_id, code_id, elf_sha1, net, built) of the build in out_dir; fields stay empty when
    it is not built. Uses the lobby's BuildInfo so the id matches the one the lobby shows."""
    info = {}
    stamp = read_json(os.path.join(out_dir, "build", "t5dr_build.json")) or {}
    info["code_id"] = stamp.get("code_id")
    info["elf_sha1"] = stamp.get("elf_sha1")
    info["built"] = stamp.get("built")
    try:
        lobby = os.path.join(root or os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lobby")
        if lobby not in sys.path:
            sys.path.insert(0, lobby)
        from t5lobby.buildid import BuildInfo
        b = BuildInfo.from_out_dir(out_dir, (release or {}).get("version", "dev"))
        info.update(build_id=b.build_id, code_id=b.code_id, elf_sha1=b.elf_sha1, net=b.net)
    except Exception:       # noqa: BLE001 -- not built, or the lobby files are missing: the report goes on
        pass
    return info


# --------------------------------------------------------------------------- what goes in

class Item:
    """One thing that may go into the zip: a file on disk, or text made here (a string, or a function
    that makes it when the zip is written)."""

    def __init__(self, arcname, path=None, text=None, kind="text", limit=None, note="", size=None):
        self.arcname = arcname
        self.path = path
        self.text = text
        self.kind = kind                       # "text" (scrubbed), "binary" (copied) or "replay" (copied without names)
        self.limit = limit                     # most bytes this item may take (None: the budget decides)
        self.note = note
        if size is not None:
            self.size = size                   # an estimate, for the list in the window
            return
        try:
            self.size = len(text.encode("utf-8")) if text is not None else os.path.getsize(path)
        except OSError:
            self.size = 0


class Group:
    def __init__(self, key, title, items, default_on=True, can_untick=True):
        self.key, self.title, self.items = key, title, items
        self.default_on, self.can_untick = default_on, can_untick

    @property
    def size(self):
        return sum(i.size for i in self.items)


class Context:
    """Where everything is. `out_dir` is the folder the build and the game write to (native\\)."""

    def __init__(self, out_dir, root=None, launcher_log=None, settings_lines=(), release=None, build_info=None,
                 online_dir=None, online_info=None, build_problem=None, extra_secrets=(), user_names=None,
                 pc_names=None, game_logs=2, player_names=()):
        self.out_dir = os.path.abspath(out_dir)
        self.root = root
        self.launcher_log = launcher_log
        self.settings_lines = list(settings_lines)
        self.release = release or {}
        self._build_info = build_info or {}       # a dict, or a function that makes it (hashing the game program takes a moment)
        self.online_dir = online_dir              # per-user folder with online.json (read for secrets only)
        self.online_info = online_info            # text the Online tab adds (lobby, last result)
        self.build_problem = build_problem
        self.extra_secrets = list(extra_secrets)
        self.user_names = user_names
        self.pc_names = pc_names
        self.game_logs = game_logs
        self.extra_player_names = list(player_names)

    @property
    def build_info(self):
        if callable(self._build_info):
            self._build_info = self._build_info() or {}
        return self._build_info

    def secrets(self):
        """Exact secret values to keep out of every file: from the settings files and the control files."""
        found = set(self.extra_secrets)
        files = [os.path.join(self.root, "launcher.json") if self.root else None,
                 os.path.join(self.online_dir, "online.json") if self.online_dir else None,
                 os.path.join(self.out_dir, "logs", "online", "ctl", "cmd.json")]
        for p in files:
            if p and os.path.isfile(p):
                harvest_secrets(read_json(p), found)
        return found

    def player_names(self):
        """Lobby names this report must not contain: this player's and the opponents' -- from the
        settings files, the control channel, the fight files, the game logs' HUD lines and the status
        lines in launcher.log. The opponents never agreed to be in somebody else's report."""
        found = set(self.extra_player_names)

        def add(v):
            for n in str(v or "").split("|"):
                n = urllib.parse.unquote(n).strip()
                if 2 <= len(n) <= 32 and n != P_PLAYER:
                    found.add(n)
        st = read_json(os.path.join(self.root, "launcher.json")) if self.root else None
        if isinstance(st, dict):
            add(st.get("nickname"))
        on = read_json(os.path.join(self.online_dir, "online.json")) if self.online_dir else None
        if isinstance(on, dict):
            add(on.get("name"))
            for sess in (on.get("sessions") or {}).values():
                if isinstance(sess, dict):
                    add(sess.get("name"))
        d = os.path.join(self.out_dir, "logs", "online")
        cmd = read_json(os.path.join(d, "ctl", "cmd.json"))
        if isinstance(cmd, dict) and isinstance(cmd.get("env"), dict):
            add(cmd["env"].get("T5_HUD_NAMES"))
            add(cmd["env"].get("PS3_NICKNAME"))
        for p in glob.glob(os.path.join(d, "fight-*.txt*")) + glob.glob(os.path.join(d, "*", "fight-*.txt*")):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    m = _FIGHT_NAMES.search(f.read(4096))
                if m:
                    add(m.group(2))
            except OSError:
                pass
        for p in _newest(os.path.join(self.out_dir, "logs", "game-*.log"), 10):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        if "HUD" not in ln:
                            continue
                        m = _HUD_IDENTITY.search(ln)
                        if m:
                            add(m.group(2))
                            add(m.group(4))
                        m = re.search(r"T5_HUD_NAMES=([^\r\n,]*)|\[netplay\] HUD: (.*?) ranks", ln)
                        if m:
                            add(m.group(1) or m.group(2))
            except OSError:
                pass
        for p in (self.launcher_log, (self.launcher_log or "") + ".1"):
            if p and os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        text = f.read(4 << 20)
                except OSError:
                    continue
                for rx in _STATUS_NAMES:
                    for m in rx.finditer(text):
                        add(m.group(1))
                for m in _NAME_ENV.finditer(text):
                    add(m.group(2))
        return found


def _newest(pattern, n=None):
    files = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    files.sort(key=lambda p: (os.path.getmtime(p), p), reverse=True)
    return files[:n] if n else files


def last_build_failed(out_dir):
    """True when build.log ends without 'exit code 0' (failed, cancelled or still unfinished)."""
    try:
        with open(os.path.join(out_dir, "build.log"), "rb") as f:
            f.seek(0, 2)
            f.seek(max(f.tell() - 400, 0))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    m = re.findall(r"# exit code (-?\d+)", tail)
    return not (m and m[-1] == "0")


COMPILE_LOGS = 4                 # at most this many compiler outputs (one per failed file)


def compile_logs(out_dir, n=COMPILE_LOGS):
    """The compiler's whole output of each file that failed in the last build (tools/build_game_dll.py writes
    native\\build\\gamedll_obj\\<file>.log and removes them when it starts), newest first. A log older than
    the start of the last build (build.log's first line) belongs to an earlier one and stays out."""
    logs = _newest(os.path.join(out_dir, "build", "gamedll_obj", "*.log"))
    try:
        with open(os.path.join(out_dir, "build.log"), encoding="utf-8", errors="replace") as f:
            m = re.search(r"build log, (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", f.readline())
        start = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp() if m else None
    except (OSError, ValueError):
        start = None
    if start is not None:
        logs = [p for p in logs if os.path.getmtime(p) >= start - 5]
    return logs[:n]


def online_files(out_dir):
    """The files of the last online match: the newest match id's result/status/fight files, the
    reported results, the control channel's two files."""
    d = os.path.join(out_dir, "logs", "online")
    files = []
    top = [p for p in _newest(os.path.join(d, "*")) if re.match(r"(?:result|status|fight)-", os.path.basename(p))]
    if top:
        m = re.match(r"(?:result|status|fight)-(.+?)(?:\.|$)", os.path.basename(top[0]))
        mid = m.group(1) if m else None
        files += [p for p in top if mid and f"-{mid}." in os.path.basename(p)] or top[:3]
    files += _newest(os.path.join(d, "results", "*"), 3)
    files += [p for p in (os.path.join(d, "ctl", "cmd.json"), os.path.join(d, "ctl", "state.json"))
              if os.path.isfile(p)]
    return files


def discover(ctx, note="", now=None):
    """The groups the zip can hold, in the order they are filled. Looks at the disk, reads nothing big."""
    out = ctx.out_dir
    groups = []
    newest = _newest(os.path.join(out, "logs", "game-*.log"), 1)
    sysitem = Item("system.txt", text=lambda: system_text(ctx, now, newest[0] if newest else None), limit=1 << 20,
                   size=4 * 1024)
    groups.append(Group("system", "System information and the settings you use", [sysitem], True, False))
    if note.strip():
        groups.append(Group("note", "What happened (what you wrote)", [Item("report.txt", text=note.strip())],
                            True, False))
    ll = [p for p in (ctx.launcher_log, (ctx.launcher_log or "") + ".1") if p and os.path.isfile(p)]
    if ll:
        groups.append(Group("launcher", "Launcher log", [Item(os.path.basename(p), p, limit=1 << 20) for p in ll]))
    games = _newest(os.path.join(out, "logs", "game-*.log"), ctx.game_logs)
    frames = [p for p in sorted(glob.glob(os.path.join(out, "*_frames.log"))) if os.path.isfile(p)]
    items = [Item("logs/" + os.path.basename(p), p, note="newest first") for p in games]
    items += [Item("logs/" + os.path.basename(p), p, limit=2 << 20) for p in frames]
    if items:
        groups.append(Group("game", "Game log (the newest " + ("one" if len(games) == 1 else str(len(games))) + ")",
                            items))
    bl = os.path.join(out, "build.log")
    if os.path.isfile(bl):
        failed = ctx.build_problem if ctx.build_problem is not None else last_build_failed(out)
        items = [Item("build.log", bl, limit=4 << 20)]
        if failed:          # the compiler's own words: build.log shows only an excerpt of them
            items += [Item("compile/" + os.path.basename(p), p, limit=512 << 10) for p in compile_logs(out)]
        groups.append(Group("build", "Build log" + ("" if failed else " (the last build went fine)"),
                            items, default_on=bool(failed)))
    on = online_files(out)
    oitems = [Item("online/" + p[len(os.path.join(out, "logs", "online")) + 1:].replace("\\", "/"), p, limit=64 << 10)
              for p in on]
    if ctx.online_info:
        oitems.append(Item("online/lobby-summary.txt", text=ctx.online_info, limit=64 << 10))
    if oitems:
        groups.append(Group("online", "Online: the files of the last match", oitems))
    ctl = _controls_ini(ctx)
    if ctl:
        groups.append(Group("controls", "controls.ini (your button settings)", [Item("controls.ini", ctl, limit=256 << 10)]))
    rep = _newest(os.path.join(out, "replays", "*.t5replay"), 1)
    if rep and replays is not None:
        groups.append(Group("replay", "The last replay (the inputs of the last online session, without names)",
                            [Item("replay/" + os.path.basename(rep[0]), rep[0], kind="replay", limit=4 << 20)]))
    dumps = _newest(os.path.join(out, "np_desync_*.bin"), 8) + _newest(os.path.join(out, "rb_desync_*.bin"), 8)
    if dumps:
        groups.append(Group("desync", "Desync dumps (game state numbers, binary)",
                            [Item("desync/" + os.path.basename(p), p, kind="binary", limit=1 << 20) for p in dumps]))
    return groups


def _controls_ini(ctx):
    env = os.environ.get("PS3_CONTROLS")
    cands = [env] if env else []
    cands += [os.path.join(ctx.out_dir, "build", "cmake", "controls.ini"), os.path.join(ctx.out_dir, "controls.ini")]
    return next((p for p in cands if p and os.path.isfile(p)), None)


def describe(groups, cap=DEFAULT_CAP):
    """Lines for the 'what is inside' summary: group title, file count, size."""
    lines = []
    for g in groups:
        n = len([i for i in g.items])
        lines.append(f"{g.title}: {n} file{'s' if n != 1 else ''}, {human(g.size)}")
    total = sum(g.size for g in groups if g.default_on)
    if total > cap:
        lines.append(f"Too big for {human(cap)}: the biggest logs are shortened in the middle.")
    return lines


def human(n):
    if n < 1024:
        return f"{n} bytes"
    if n < 1 << 20:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1 << 20):.1f} MB"


# --------------------------------------------------------------------------- making the zip

class Result:
    def __init__(self):
        self.path = None
        self.members = []          # dicts: name, size (in the zip), original, removed, note
        self.skipped = []          # (name, why)
        self.counts = collections.Counter()
        self.zip_size = 0
        self.cap = DEFAULT_CAP

    @property
    def total(self):
        return sum(m["size"] for m in self.members)


def default_zip_name(now=None):
    return f"T5DR-report-{(now or datetime.datetime.now()):%Y%m%d-%H%M%S}.zip"


def unique_path(path):
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base}-{n}{ext}"
        n += 1
    return path


def fit_bytes(raw, limit):
    """raw, or its start and end with a marker in between when it is longer than `limit`."""
    if len(raw) <= limit:
        return raw, 0
    import io
    return cut_middle(io.BytesIO(raw), len(raw), limit)


def build(ctx, dest_dir, note="", enabled=None, cap=DEFAULT_CAP, now=None, groups=None):
    """Write the report zip into dest_dir and return a Result.

    enabled   {group key: bool}: the dialog's check marks (a group not named keeps its default)
    groups    the result of discover(), when the caller has it already
    """
    now = now or datetime.datetime.now()
    groups = groups if groups is not None else discover(ctx, note, now)
    on = [g for g in groups if not g.can_untick or (enabled or {}).get(g.key, g.default_on)]
    sc = Scrubber(secrets=ctx.secrets(), user_names=ctx.user_names, pc_names=ctx.pc_names,
                  keep=[ctx.build_info.get("elf_sha1") or "", ctx.release.get("commit") or ""],
                  player_names=ctx.player_names())
    res = Result()
    res.cap = cap
    members = []                                         # (arcname, bytes, original size, removed, note)
    state = {"left": cap - MANIFEST_ROOM}

    def put_text(arcname, data, original, removed, room, note="", reserve=0):
        """Scrub `data` (bytes of a text file) and add it. `room` is what the file was read for. A
        placeholder can be longer than the name it replaced ("al" -> "<user>"), so the clean text may be
        longer than `room`, as long as the budget (minus `reserve`, kept for the game logs) allows it.
        False: left out."""
        limit = max(state["left"] - reserve, room)
        out = sc.text(data.decode("utf-8", "replace"))
        if not sc.clean(out):                            # the first pass exposed something more
            out = sc.text(out)
            if not sc.clean(out):
                res.skipped.append((arcname, "could not be cleaned of private data"))
                return False
        raw, extra = fit_bytes(out.encode("utf-8"), limit)   # a placeholder can be longer than what it replaced
        members.append((arcname, raw, original, removed + extra, note))
        state["left"] -= len(raw)
        return True

    def room_for(size, limit, reserve):
        """Bytes a thing of `size` may take now, or 0 when it is not worth a file."""
        want = min(size, limit or size)
        room = min(want, state["left"] - reserve)
        return room if room >= min(want, MIN_USEFUL) and room > 0 else 0

    reserve = min(cap // 3, 6 << 20)                     # the game logs keep at least this much
    logs = []
    for g in on:
        for it in g.items:
            if it.arcname.startswith("logs/game-"):
                logs.append(it)
                continue
            if it.text is not None:                      # text made here
                data = (it.text() if callable(it.text) else it.text).encode("utf-8")
                room = room_for(len(data), it.limit, reserve)
                if room <= 0:
                    res.skipped.append((it.arcname, "no room left in the size limit"))
                    continue
                put_text(it.arcname, data[:room], len(data), max(len(data) - room, 0), room, it.note, reserve)
                continue
            room = room_for(it.size, it.limit, reserve)
            if room <= 0:
                res.skipped.append((it.arcname, "no room left in the size limit"))
                continue
            if it.kind in ("binary", "replay"):
                try:
                    if it.kind == "replay":       # the players' names never leave the PC
                        data = replays.strip_names(it.path, P_PLAYER)
                    else:
                        with open(it.path, "rb") as f:
                            data = f.read()
                except (OSError, ValueError, replays.ReplayError if replays else OSError):
                    res.skipped.append((it.arcname, "could not be read"))
                    continue
                if len(data) > room:
                    res.skipped.append((it.arcname, "no room left in the size limit"))
                    continue
                members.append((it.arcname, data, len(data), 0, it.note))
                state["left"] -= len(data)
            else:
                data, removed = read_capped(it.path, room)
                if not data and it.size:
                    res.skipped.append((it.arcname, "could not be read"))
                    continue
                put_text(it.arcname, data, it.size, removed, room, it.note, reserve)

    # game logs, newest first: the newest takes most of what is left, older ones the rest
    for idx, it in enumerate(logs):
        share = state["left"] if idx == len(logs) - 1 else int(state["left"] * 0.7)
        room = min(it.size, share)
        if room < min(it.size, MIN_USEFUL):
            res.skipped.append((it.arcname, "no room left in the size limit"))
            continue
        data, removed = read_capped(it.path, room)
        if not data and it.size:
            res.skipped.append((it.arcname, "could not be read"))
            continue
        put_text(it.arcname, data, it.size, removed, room, it.note)

    res.counts = sc.counts
    res.members = [dict(name=n, size=len(b), original=o, removed=r, note=nt) for n, b, o, r, nt in members]
    manifest = contents_text(res, now, [g for g in groups if g not in on]).encode("utf-8")
    os.makedirs(dest_dir, exist_ok=True)
    path = unique_path(os.path.join(dest_dir, default_zip_name(now)))
    tmp = path + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr(_zinfo("contents.txt", now), manifest)
            for name, data, *_ in members:
                z.writestr(_zinfo(name, now), data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    res.members.insert(0, dict(name="contents.txt", size=len(manifest), original=len(manifest), removed=0, note=""))
    res.path = path
    res.zip_size = os.path.getsize(path)
    return res


def _zinfo(name, now):
    zi = zipfile.ZipInfo(name, date_time=now.timetuple()[:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    return zi


def contents_text(res, now, left_out):
    L = [f"T5DR Online problem report, {now:%Y-%m-%d %H:%M:%S}",
         "", "This zip was made on the player's PC by the launcher's 'Report a problem' button. Nothing was",
         "uploaded. Before the files went in, private data was removed from every text file:",
         f"  {res.counts['user']} Windows user or PC names -> {P_USER} / {P_PC}",
         f"  {res.counts['ip']} internet IP addresses -> {P_IP} (local network addresses stay)",
         f"  {res.counts['secret']} passwords, tokens, match keys or long hex strings -> {P_REMOVED} / {P_HEX}",
         f"  {res.counts['email']} e-mail addresses -> {P_EMAIL}",
         f"  {res.counts['player']} lobby player names (yours and your opponents') -> {P_PLAYER}",
         "The desync dumps (desync/*.bin) are binary game state numbers and are copied as they are.",
         "The replay (replay/*.t5replay) holds both players' inputs and state checks; the names are taken out.",
         "", "Files:"]
    for m in res.members:
        L.append(f"  {m['name']}  {human(m['size'])}"
                 + (f"  (shortened: {m['removed']:,} bytes removed from the middle)" if m["removed"] else ""))
    for name, why in res.skipped:
        L.append(f"  {name}  LEFT OUT: {why}")
    for g in left_out:
        L.append(f"  {g.title}: not included")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- command line

def main(argv=None):
    ap = argparse.ArgumentParser(description="Make a T5DR problem report zip (the launcher's 'Report a problem').")
    ap.add_argument("--out", required=True, help="the build's output folder (native)")
    ap.add_argument("--root", help="the release folder (launcher.json, release.json)")
    ap.add_argument("--dest-dir", default=os.path.join(os.path.expanduser("~"), "Desktop"))
    ap.add_argument("--note", default="")
    ap.add_argument("--cap-mb", type=float, default=DEFAULT_CAP / (1 << 20))
    ap.add_argument("--with-build-log", action="store_true")
    a = ap.parse_args(argv)
    root = a.root or os.path.dirname(a.out.rstrip("\\/"))
    rel = read_json(os.path.join(root, "release.json")) or {}
    st = read_json(os.path.join(root, "launcher.json")) or {}
    ctx = Context(a.out, root=root, launcher_log=os.path.join(root, "launcher.log"), release=rel,
                  settings_lines=settings_lines(st if isinstance(st, dict) else {}, out_dir=os.path.abspath(a.out)),
                  build_info=build_info_for(os.path.abspath(a.out), rel, root))
    res = build(ctx, a.dest_dir, a.note, {"build": True} if a.with_build_log else None, int(a.cap_mb * (1 << 20)))
    print(res.path, human(res.zip_size))
    for m in res.members:
        print(f"  {m['name']}  {human(m['size'])}" + (f"  shortened ({m['removed']:,} bytes)" if m["removed"] else ""))
    for n, why in res.skipped:
        print(f"  {n}  left out: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
