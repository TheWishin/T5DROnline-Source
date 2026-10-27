"""'Check my problem' (1.1.5): the known cases players ran into, found in this PC's logs and settings, each with
the fix in the player's language (problem_check_ui.py shows them).

    python launcher/problem_check.py --out <native folder>        what it finds, in English (diagnostics)

What it looks for (each only where the evidence is):
  package_version  the last BUILD GAME stopped at a package of another game version (v01.01: GitHub #20/#21;
                   build.log's "PARAM.SFO: ... version 01.01", or the program's content ID ...-0000000000000000)
  package_damaged  the last build found the package cut short or not decryptable, or the newest game log shows the
                   game's own "data is corrupted" message box
  unpack_memory    the last build ran out of memory while unpacking (MemoryError in build.log; GitHub #24)
  firewall         Windows Firewall blocks t5dr.exe (lobby/t5lobby/fwcheck.py, read-only)
  two_cores        the processor has 2 cores (i3-3240, i5-4210M: under ~20 frames per second in fights)
  gpu_tier1        the newest game log names a graphics card with resource binding tier 1 (old GT 730 and alike)
  wine             the launcher runs under Wine / Proton (ntdll's wine_get_version)

Nothing here changes anything, nothing is sent anywhere, and it imports no tkinter: the texts are English
templates marked N_() with their values; the window translates them.
"""
import argparse
import glob
import os
import re
import sys

try:
    import problem_report as report
except ImportError:      # pragma: no cover -- run from elsewhere
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import problem_report as report


def N_(text):
    return text


DOCS = "https://github.com/TheWishin/T5DROnline/blob/main/TROUBLESHOOTING.md"
SUPPORTED_VERSION = "01.00"
PKG_SIZE = "619,430,240"
RAP_NAME = "UP0700-NPUB30009_00-UPDATE0000010000.rap"
OTHER_PROGRAMS = {"UP0700-NPUB30009_00-0000000000000000": "01.01"}     # (tools/build_game.py OTHER_VERSIONS)

RE_SFO = re.compile(r"PARAM\.SFO: .*? / (\S+) / version (\S+)")
RE_VERSION_FAIL = re.compile(r"This (?:package|copy) is (?:a different )?version (\d\d\.\d\d)"
                             r"|\"[^\"]*\" version (\d\d\.\d\d)")
RE_PROGRAM_ID = re.compile(r"(UP0700-NPUB30009_00-\d{16})")
RE_PKG_SHORT = re.compile(r"the download is incomplete|Decrypting the game program failed", re.I)
RE_MEMORY = re.compile(r"\bMemoryError\b|Unable to allocate|out of memory", re.I)
RE_UNPACK_STEP = re.compile(r"pkg_extract|unpack", re.I)
RE_DIALOG = re.compile(r"^\[(?:DIALOG|cellMsgDialog)\].*?(corrupt|damaged|beschädigt)", re.I)
RE_GPU = re.compile(r"^\[gpu\] adapter: (.+?) \(vendor [0-9A-Fa-f]+, .*?resource binding tier (\d+)")
RE_WINE_LOG = re.compile(r"^\[wine\] (Wine [^\r\n]*?)(?: --|$)")


class Finding:
    """One known problem: `title` and `fix` are English templates (N_) filled with `values`; `found` says what
    was seen and where (a template too); `help` a section of TROUBLESHOOTING.md; `kind` 'problem' or 'hint'."""

    def __init__(self, key, title, fix, found="", values=None, help=None, kind="problem"):
        self.key, self.title, self.fix, self.found = key, title, fix, found
        self.values = dict(values or {})
        self.help = help
        self.kind = kind

    def text(self, translate=None):
        """(title, found, fix) filled in, through the translation function when given."""
        tr = translate or (lambda s, **v: s.format(**v) if v else s)
        return tuple(tr(s, **self.values) if s else "" for s in (self.title, self.found, self.fix))

    def __repr__(self):
        return f"Finding({self.key!r})"


def _read(path, limit=8 << 20):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def _newest(pattern):
    files = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    return max(files, key=lambda p: (os.path.getmtime(p), p)) if files else None


# ---------------------------------------------------------------------------- the build
def check_build(out_dir):
    """Findings from the last BUILD GAME (build.log), only when it did not end well."""
    log = os.path.join(out_dir, "build.log")
    if not os.path.isfile(log) or not report.last_build_failed(out_dir):
        return []
    text = _read(log)
    out = []
    ver = None
    for m in RE_SFO.finditer(text):
        ver = m.group(2)
    for m in RE_VERSION_FAIL.finditer(text):
        ver = m.group(1) or m.group(2) or ver
    for pid in RE_PROGRAM_ID.findall(text):
        if pid in OTHER_PROGRAMS:
            ver = OTHER_PROGRAMS[pid]
    if ver and ver != SUPPORTED_VERSION:
        out.append(Finding(
            "package_version", N_("Your game package is version {version}"),
            N_("The port works only with version {supported} of the game: TEKKEN 5 DARK RESURRECTION ONLINE, US PSN "
               "(NPUB30009), a .pkg of {size} bytes, with its license {rap}. Version {version} cannot be used, "
               "whatever the license. Choose the {supported} package on the Build tab and press BUILD GAME."),
            N_("build.log: the package says version {version}."),
            {"version": ver, "supported": SUPPORTED_VERSION, "size": PKG_SIZE, "rap": RAP_NAME},
            help="this-copy-is-a-different-version-of-the-game"))
        return out                     # (everything after it follows from the wrong version)
    tail = text[-200_000:]
    if RE_MEMORY.search(tail) and RE_UNPACK_STEP.search(tail):
        out.append(Finding(
            "unpack_memory", N_("Unpacking the game ran out of memory"),
            N_("Close other programs (browser, games, launchers) and press BUILD GAME again; since 1.1.5 the "
               "launcher unpacks the game in small pieces. If it fails again, check that Windows has a page file "
               "(System > About > Advanced system settings > Performance > Virtual memory: automatic)."),
            N_("build.log: the computer ran out of memory while the game data was unpacked."),
            help="the-build-is-slow-or-the-pc-is-unresponsive"))
    if RE_PKG_SHORT.search(tail):
        out.append(Finding(
            "package_damaged", N_("The game package looks damaged or incomplete"),
            N_("Download the package again (it must be {size} bytes), choose it on the Build tab, tick \"Redo every "
               "step\" and press BUILD GAME."),
            N_("build.log: the package could not be read to the end or not decrypted."),
            {"size": PKG_SIZE}, help="decrypting-the-game-program-failed"))
    return out


# ---------------------------------------------------------------------------- the game
def dialog_text(line):
    """The message of a game log's dialog line: '[DIALOG] text' or "[cellMsgDialog] Open2(..., msg='text')"."""
    m = re.search(r"msg='([^']*)", line)
    text = m.group(1) if m else re.sub(r"^\[[^\]]*\]\s*", "", line)
    return " ".join(text.replace("\n", " ").split())[:160]


def check_game_log(out_dir):
    """Findings from the newest game log: the game's own 'data is corrupted' box, an old graphics card."""
    path = _newest(os.path.join(out_dir, "logs", "game-*.log"))
    if not path:
        return []
    out = []
    gpu = None
    dialog = None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f):
                if n > 400_000:
                    break
                if gpu is None:
                    m = RE_GPU.match(line)
                    if m:
                        gpu = (m.group(1).strip(), int(m.group(2)))
                if (dialog is None or not dialog.startswith("[DIALOG]")) and RE_DIALOG.match(line):
                    dialog = line.strip()[:400]          # (the [DIALOG] line has the plain text: it wins)
    except OSError:
        return []
    if dialog:
        out.append(Finding(
            "package_damaged", N_("The game says its data is damaged"),
            N_("On the Build tab tick \"Redo every step\" and press BUILD GAME: it unpacks the game again. If the "
               "message comes back, download the package again (it must be {size} bytes)."),
            N_("Game log: the game showed the message \"{message}\"."),
            {"size": PKG_SIZE, "message": dialog_text(dialog)},
            help="the-game-starts-but"))
    if gpu and gpu[1] <= 1:
        out.append(Finding(
            "gpu_tier1", N_("Your graphics card is an older model"),
            N_("{gpu} is a Direct3D 12 card of the oldest kind (resource binding tier 1: GeForce cards with a Fermi "
               "chip, among them some GT 730 models, and older Intel graphics). The game's graphics take several "
               "times longer on it than on later cards, whatever the processor: fights can stay below 30 frames per "
               "second, and a lower Internal resolution helps only a little. Later cards (a GT 730 with a Kepler "
               "chip, GTX 750, Radeon HD 7000 and newer) run the game at full speed."),
            N_("Game log: {gpu}, resource binding tier {tier}."),
            {"gpu": gpu[0], "tier": gpu[1]}, help="low-frame-rate", kind="hint"))
    return out


# ---------------------------------------------------------------------------- this PC
def wine_version():
    """'Wine 9.0 ...' when this program runs under Wine or Proton, else None."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        fn = ctypes.WinDLL("ntdll").wine_get_version
    except (OSError, AttributeError):
        return None
    try:
        fn.restype = ctypes.c_char_p
        return "Wine " + (fn() or b"?").decode("ascii", "replace")
    except (OSError, ValueError):
        return "Wine"


def system_facts():
    """What check_pc needs from this PC: physical cores, logical processors, Wine."""
    try:
        cores = report._physical_cores()
    except Exception:       # noqa: BLE001 -- a fact we cannot read is a fact we do not use
        cores = None
    return {"cores": cores, "logical": os.cpu_count(), "wine": wine_version()}


def check_pc(facts, out_dir=None):
    out = []
    cores = facts.get("cores")
    if cores and cores <= 2:
        out.append(Finding(
            "two_cores", N_("Your processor has {cores} cores"),
            N_("The game is made for 4 cores; on {cores} it can stay below 60 frames per second in fights (an "
               "i3-3240 reached about 20). Close other programs while you play, keep Windows' power plan on "
               "Balanced or High performance, and see \"Low frame rate\" in the help."),
            N_("This PC: {cores} cores, {logical} logical processors."),
            {"cores": cores, "logical": facts.get("logical") or "?"}, help="low-frame-rate", kind="hint"))
    wine = facts.get("wine")
    if not wine and out_dir:
        path = _newest(os.path.join(out_dir, "logs", "game-*.log"))
        for line in (_read(path, 64 << 10).splitlines()[:50] if path else ()):
            m = RE_WINE_LOG.match(line)
            if m:
                wine = m.group(1)
                break
    if wine:
        out.append(Finding(
            "wine", N_("The launcher runs under Wine or Proton"),
            N_("That works, with a few known differences: since 1.1.5 the launcher sets the safe graphics defaults "
               "for Wine by itself. A dark blue or black game window (sound playing) means the Proton build does "
               "not suit the game: try another one (Proton Experimental, proton-cachyos-slr). See \"Linux and "
               "Steam Deck\" in the help."),
            N_("This PC: {wine}."), {"wine": wine}, help="linux-and-steam-deck-wine-proton", kind="hint"))
    return out


def check_firewall(out_dir, fw=None):
    """Windows Firewall blocks the game (fwcheck, read-only). fw: fwcheck.check (tests hand in their own)."""
    exe = os.path.join(out_dir, "build", "cmake", "t5dr.exe")
    if fw is None:
        try:
            sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lobby"))
            from t5lobby import fwcheck
            fw = fwcheck.check
        except ImportError:
            return []
    try:
        st = fw(exe)
    except Exception:       # noqa: BLE001 -- the check never stops the others
        return []
    if getattr(st, "state", None) != "blocked" or "game" not in (getattr(st, "blocked", None) or ()):
        return []
    return [Finding(
        "firewall", N_("Windows Firewall blocks the game"),
        N_("Online matches then often go through a relay (more lag) or do not connect. Open Windows Security > "
           "Firewall & network protection > Allow an app through firewall, and allow t5dr.exe (in {folder}) for "
           "private and public networks; or remove the block rule for it there."),
        N_("Windows Firewall: a block rule or \"Block all incoming connections\" for t5dr.exe."),
        {"folder": os.path.dirname(exe)}, help="the-firewall-blocks-the-game")]


def check(out_dir, facts=None, fw=None):
    """Every finding, problems first."""
    out = []
    out += check_build(out_dir)
    out += check_game_log(out_dir)
    out += check_firewall(out_dir, fw)
    out += check_pc(facts if facts is not None else system_facts(), out_dir)
    seen = set()
    uniq = []
    for f in out:
        if f.key in seen:
            continue
        seen.add(f.key)
        uniq.append(f)
    uniq.sort(key=lambda f: f.kind != "problem")
    return uniq


def help_url(f):
    return f"{DOCS}#{f.help}" if f and f.help else DOCS


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the native folder (build.log, logs)")
    a = ap.parse_args(argv)
    found = check(os.path.abspath(a.out))
    for f in found:
        title, seen, fix = f.text()
        print(f"[{f.kind}] {title}\n  {seen}\n  {fix}\n  {help_url(f)}")
    if not found:
        print("No known problem found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
