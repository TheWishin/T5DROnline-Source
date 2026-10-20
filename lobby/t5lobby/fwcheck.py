"""Does Windows Firewall block the game (or the launcher)? A read-only look, for the Online tab's hint.

    st = fwcheck.check(exe=r"...\\native\\build\\cmake\\t5dr.exe")
    st.state      "off"      the firewall is off for this network (or not Windows)
                  "allowed"  an inbound allow rule for the program covers this network, and no block rule
                  "ask"      no rule yet: Windows will ask whether the program may use the network
                  "blocked"  a block rule for the program (someone clicked Cancel on Windows' question, or made
                             one), "Block all incoming connections" is on, or there is no rule and Windows does
                             not ask (notifications off): unsolicited packets are dropped
                  "unknown"  the rules could not be read
    st.blocked    the programs that are blocked: ["game"], ["launcher"], ["game", "launcher"] or []

Nothing is ever changed and nothing needs administrator rights. The rules come from the firewall's own store
in the registry, which every user may read: HKLM\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\
FirewallPolicy (FirewallRules and each profile's EnableFirewall / DoNotAllowExceptions / DisableNotifications),
with Group Policy's HKLM\\SOFTWARE\\Policies\\Microsoft\\WindowsFirewall on top. `netsh advfirewall firewall show
rule name=all verbose` reads the same rules but is no use here: on a PC with ~1,900 rules it ran for more than two
minutes and printed 1.9 MB, every label in the Windows language ("Aktion: Blockieren"). netsh is asked only which
profile the current network has (`netsh advfirewall show currentprofile`: its heading is compared with the headings
of `show privateprofile` / `publicprofile` / `domainprofile`, so the Windows language does not matter); when that
fails, every profile with the firewall on counts.

What a block means for online play (docs/NETPLAY.md "When Windows Firewall blocks the game"): Windows still lets
in the replies to the program's own packets, so a match still connects -- both sides send first -- but some
direct connections that need an unsolicited packet then fail and the match goes through a relay (more lag).
Third-party firewalls keep their own rules; the netplay results (tk_tab: udp_unreachable, a game that heard
nothing from its opponent) catch those.
"""
import os
import subprocess
import sys
import threading

PROFILES = ("domain", "private", "public")
_REG_PROFILE = {"domain": "DomainProfile", "private": "StandardProfile", "public": "PublicProfile"}
_POLICY_PROFILE = {"domain": "DomainProfile", "private": "PrivateProfile", "public": "PublicProfile"}
_RULE_PROFILE = {"domain": "domain", "private": "private", "public": "public"}
LOCAL_KEY = r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy"
POLICY_KEY = r"SOFTWARE\Policies\Microsoft\WindowsFirewall"
UDP = "17"
CREATE_NO_WINDOW = 0x08000000


class Status:
    __slots__ = ("state", "blocked", "programs", "profiles", "detail", "paths")

    def __init__(self, state, blocked=(), programs=None, profiles=None, detail="", paths=None):
        self.state = state
        self.paths = dict(paths or {})       # "game" / "launcher" -> the program's path that was checked
        self.blocked = list(blocked)
        self.programs = programs or {}       # "game" / "launcher" -> state of that program alone
        self.profiles = profiles             # the current network's profiles (None: not known, all counted)
        self.detail = detail

    def __repr__(self):
        return (f"fwcheck.Status({self.state!r}, blocked={self.blocked}, programs={self.programs}, "
                f"profiles={self.profiles}, detail={self.detail!r})")


def parse_rule(text):
    """'v2.10|Action=Block|Active=TRUE|Dir=In|Protocol=17|Profile=Public|App=C:\\x\\t5dr.exe|Name=t5dr|' ->
    {"action": "block", "active": True, "dir": "in", "protocol": "17", "profiles": {"public"}, "app": ...,
    "scoped": False}. Profiles empty = every profile; protocol None = any. scoped: only some ports or remote
    addresses (an allow rule like that does not count as "the program is allowed")."""
    r = {"action": None, "active": False, "dir": None, "protocol": None, "profiles": set(), "app": None,
         "scoped": False}
    for part in str(text or "").split("|"):
        k, eq, v = part.partition("=")
        if not eq:
            continue
        k = k.strip().lower()
        v = v.strip()
        if k == "action":
            r["action"] = v.lower()
        elif k == "active":
            r["active"] = v.upper() == "TRUE"
        elif k == "dir":
            r["dir"] = v.lower()
        elif k == "protocol":
            r["protocol"] = v
        elif k == "profile":
            p = _RULE_PROFILE.get(v.lower())
            if p:
                r["profiles"].add(p)
        elif k == "app":
            r["app"] = v
        elif k in ("lport", "rport", "ra4", "ra6", "la4", "la6", "lport2_10", "rport2_10", "ra42", "ra62"):
            r["scoped"] = True
    return r


def norm_path(p):
    try:
        return os.path.normcase(os.path.normpath(os.path.expandvars(str(p))))
    except (TypeError, ValueError):
        return ""


def evaluate(rules, programs, enabled, current=None, block_all=None, notify_off=None):
    """The decision, from data (tests feed it directly).

    rules: rule strings (FirewallRules values). programs: {"game": path, "launcher": path}. enabled: {profile: bool}
    (firewall on). current: the current network's profiles, or None (every profile counts). block_all /
    notify_off: {profile: bool} (DoNotAllowExceptions / DisableNotifications). -> Status."""
    block_all = block_all or {}
    notify_off = notify_off or {}
    profiles = [p for p in (current or PROFILES) if p in PROFILES]
    live = [p for p in profiles if enabled.get(p)]
    if not live:
        return Status("off", profiles=current, detail="the firewall is off for " + ",".join(profiles or ["?"]))
    parsed = [parse_rule(r) for r in rules]
    per = {}
    blocked = []
    for name, path in programs.items():
        want = norm_path(path)
        if not want:
            continue
        mine = [r for r in parsed if r["active"] and r["dir"] == "in" and r["app"] and norm_path(r["app"]) == want
                and r["protocol"] in (None, UDP)]
        state = "allowed"
        for p in live:
            here = [r for r in mine if not r["profiles"] or p in r["profiles"]]
            if block_all.get(p) or any(r["action"] == "block" for r in here):
                state = "blocked"
                break
            if not any(r["action"] == "allow" and not r["scoped"] for r in here):
                state = "blocked" if notify_off.get(p) else ("ask" if state == "allowed" else state)
                if state == "blocked":
                    break
        per[name] = state
        if state == "blocked":
            blocked.append(name)
    if blocked:
        overall = "blocked"
    elif any(s == "ask" for s in per.values()):
        overall = "ask"
    else:
        overall = "allowed"
    return Status(overall, blocked, per, current, "firewall on for " + ",".join(live), paths=programs)


# ------------------------------------------------------------------ reading this PC (Windows only)
def _reg_values(root, path):
    import winreg
    out = {}
    try:
        k = winreg.OpenKey(root, path)
    except OSError:
        return None
    try:
        i = 0
        while True:
            try:
                name, value, _typ = winreg.EnumValue(k, i)
            except OSError:
                break
            out[name] = value
            i += 1
    finally:
        winreg.CloseKey(k)
    return out


def read_registry():
    """-> (rules, enabled, block_all, notify_off) from the local store with Group Policy on top, or None."""
    import winreg
    hk = winreg.HKEY_LOCAL_MACHINE
    local_rules = _reg_values(hk, LOCAL_KEY + r"\FirewallRules")
    if local_rules is None:
        return None
    rules = [v for v in local_rules.values() if isinstance(v, str)]
    rules += [v for v in (_reg_values(hk, POLICY_KEY + r"\FirewallRules") or {}).values() if isinstance(v, str)]
    enabled, block_all, notify_off = {}, {}, {}
    for p in PROFILES:
        loc = _reg_values(hk, LOCAL_KEY + "\\" + _REG_PROFILE[p]) or {}
        pol = _reg_values(hk, POLICY_KEY + "\\" + _POLICY_PROFILE[p]) or {}

        def val(name, default):
            v = pol.get(name, loc.get(name, default))
            return bool(v) if isinstance(v, int) else default
        enabled[p] = val("EnableFirewall", True)          # (Windows' default: on)
        block_all[p] = val("DoNotAllowExceptions", False)
        notify_off[p] = val("DisableNotifications", False)
    return rules, enabled, block_all, notify_off


def _netsh_headings(what, timeout):
    """The profile headings `netsh advfirewall show <what>` prints (raw bytes, in whatever language)."""
    out = subprocess.run(["netsh", "advfirewall", "show", what], capture_output=True, timeout=timeout,
                         creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL).stdout
    lines = [ln.strip() for ln in out.splitlines()]
    return [lines[i] for i in range(len(lines) - 1) if lines[i] and lines[i + 1].startswith(b"-----")]


def current_profiles(timeout=8.0):
    """The current network's profiles (["public"], ["private", "domain"] ...), or None when netsh does not say."""
    import concurrent.futures
    names = [p + "profile" for p in PROFILES] + ["currentprofile"]
    try:
        with concurrent.futures.ThreadPoolExecutor(len(names)) as ex:      # (each netsh takes about a second)
            got = dict(zip(names, ex.map(lambda w: _netsh_headings(w, timeout), names)))
    except (OSError, subprocess.SubprocessError):
        return None
    cur = got["currentprofile"]
    found = [p for p in PROFILES if got[p + "profile"] and got[p + "profile"][0] in cur]
    return found or None


def own_program():
    """The program this launcher runs as (pythonw.exe, or the launcher's own .exe): what a firewall rule names."""
    if os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(32768)
            n = ctypes.windll.kernel32.GetModuleFileNameW(None, buf, len(buf))
            if n:
                return buf.value
        except (OSError, AttributeError, ValueError):
            pass
    return sys.executable


def check(exe, launcher=None, profiles="auto"):
    """The firewall's view of the game `exe` (the exact t5dr.exe the launcher starts) and of the launcher. Blocks
    (netsh may take a few seconds): run it on a worker thread. Never raises."""
    if os.name != "nt":
        return Status("off", detail="not Windows")
    try:
        got = read_registry()
    except Exception as e:      # noqa: BLE001 -- a hint must never stop the launcher
        return Status("unknown", detail=f"registry: {type(e).__name__}: {e}")
    if got is None:
        return Status("unknown", detail="the firewall rules could not be read")
    rules, enabled, block_all, notify_off = got
    if not any(enabled.values()):
        return Status("off", detail="the firewall is off for every profile")
    cur = current_profiles() if profiles == "auto" else profiles
    progs = {"game": exe}
    if launcher is None:
        launcher = own_program()
    if launcher:
        progs["launcher"] = launcher
    return evaluate(rules, progs, enabled, cur, block_all, notify_off)


class Checker:
    """check() once in the background; `result` is None until it is done. `then(status)` runs on the worker
    thread (a Tk front end hands it to its own thread)."""

    def __init__(self, exe, then=None, **kw):
        self.result = None
        self._then = then
        self._thread = threading.Thread(target=self._run, args=(exe, kw), daemon=True, name="fwcheck")
        self._thread.start()

    def _run(self, exe, kw):
        try:
            self.result = check(exe, **kw)
        except Exception as e:  # noqa: BLE001
            self.result = Status("unknown", detail=f"{type(e).__name__}: {e}")
        if self._then is not None:
            try:
                self._then(self.result)
            except Exception:   # noqa: BLE001
                pass


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Read-only: does Windows Firewall block the game / the launcher?")
    ap.add_argument("exe", help="the game's t5dr.exe (the path the launcher starts)")
    ap.add_argument("--launcher", default=None, help="the launcher's program (default: this Python)")
    a = ap.parse_args(argv)
    print(check(a.exe, launcher=a.launcher or sys.executable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
