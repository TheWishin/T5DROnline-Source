"""Editing the game's controls.ini for the launcher's Controls screen (no Tk in here).

The runtime reads `controls.ini` (docs/controls.ini, patch 0009); lobby/t5lobby/padmap.py is the launcher's
port of its parser and binding rules. This module changes the file the way a careful person would by hand:

* `IniDoc` keeps every line as it is -- comments, blank lines, unknown keys, the spelling of the keys, the
  line endings -- and only touches the lines an edit is about. Text that is not changed comes out byte for byte.
* `ControlsEditor` sets, clears and resets Tekken buttons of one controller, applies a layout preset, sets a
  port's stick mode and SOCD, and pins a controller to a player port. After every edit the effective
  bindings are what padmap.py (= the game) computes from the new text, which is what the tests check.
* The same rules as the game's: an explicit `TARGET = SOURCE ...` line replaces what the target had and takes
  its sources away from whatever they did before; `TARGET =` (empty) unbinds; the preset comes from the most
  specific layer that names one; `[xinput]` / `[dinput]` < `[dinput.VVVV:PPPP]` < `[portN.xinput]` /
  `[portN.dinput]` (later layers win).

Where it writes: the file the game reads (padmap.find_controls_ini), else `<output>\\controls.ini`.
"""
import os
import re
import sys
import tempfile
from collections import namedtuple

_LOBBY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lobby")
if _LOBBY not in sys.path:
    sys.path.insert(0, _LOBBY)

from t5lobby import padmap  # noqa: E402
from t5lobby.padmap import DINPUT, XINPUT  # noqa: E402

try:    # the launcher's languages (lobby/t5lobby/i18n.py), when this copy has them
    from t5lobby.i18n import N_, t  # noqa: E402,F401
except ImportError:
    def N_(text):
        return text

    def t(text, **values):
        return text.format(**values) if values else text

WS = " \t\r\n\v\f"                     # what the game's trim() removes (C isspace), not Python's wider set
BOM = "\xef\xbb\xbf"                   # (the file is read as latin-1, byte for byte)
NOTE = "; written by the launcher (Settings > Controls); your other lines and comments are kept"
HEADER = (
    "; T5DR Online controls.ini -- started by the launcher (Settings > Controls).",
    "; Anything not listed here keeps its built-in default. Every setting and key name is",
    "; documented in docs\\controls.ini. You may edit this file; the launcher keeps your comments.",
)
# The runtime's tables (INI_MAX_KV / INI_MAX_SEC in pad_host_win32.c): lines past these are ignored silently.
MAX_KV, MAX_SECTIONS = 768, 96
MAX_SOURCES = 16                       # sources on one line (srcs[16] in bind_line)

SCOPE_KIND, SCOPE_MODEL, SCOPE_PORT = "kind", "model", "port"
SOCD_MODES = ("neutral", "up", "last", "off")      # parse_socd()
STICK_MODES = ("analog", "dpad")


# ---------------------------------------------------------------------- the file as lines

class Line:
    """One line. kind: blank | comment | section | kv | junk (junk: text the game ignores, e.g. a
    `key = value` before the first section). A kv line is kept as its parts, so changing the value keeps
    the key's spelling, the spacing and a trailing `; comment`."""
    __slots__ = ("kind", "text", "eol", "section", "name", "key", "val", "lead", "keyraw", "pre", "post")

    def __init__(self, kind, text, eol="\n", section=None):
        self.kind, self.text, self.eol, self.section = kind, text, eol, section
        self.name = self.key = self.val = ""
        self.lead = self.keyraw = self.pre = self.post = ""

    def rebuild(self):
        txt = f"{self.lead}{self.keyraw}={self.pre}{self.val}{self.post}"
        self.text = txt if self.post.strip() else txt.rstrip(WS)

    def set_val(self, val):
        if self.val == "" and val:          # `1 =` -> `1 = B1`
            self.pre = self.pre or " "
        self.val = val
        self.rebuild()


def _parse(text, cur):
    """(Line, new current section) for one physical line, with the game's rules (ini_load)."""
    s = text.strip(WS)
    if not s:
        return Line("blank", text, section=cur), cur
    if s[0] in ";#":
        return Line("comment", text, section=cur), cur
    if s[0] == "[":
        e = s.find("]")
        if e < 0:                                # a header without ]: the keys under it belong to no section
            return Line("junk", text, section=None), None
        ln = Line("section", text)
        ln.name = s[1:e].strip(WS)
        return ln, ln.name
    eq = text.find("=")
    if eq < 0 or cur is None:
        return Line("junk", text, section=cur), cur
    ln = Line("kv", text, section=cur)
    ln.lead = text[:len(text) - len(text.lstrip(WS))]
    ln.keyraw = text[len(ln.lead):eq]
    ln.key = ln.keyraw.strip(WS)
    rest = text[eq + 1:]
    cut = None
    for i in range(1, len(rest)):                # an inline comment: whitespace, then ; or #
        if rest[i] in ";#" and rest[i - 1] in WS:
            cut = i
            break
    valpart, comment = (rest, "") if cut is None else (rest[:cut], rest[cut:])
    ln.val = valpart.strip(WS)
    if ln.val:
        ln.pre = valpart[:len(valpart) - len(valpart.lstrip(WS))]
        ln.post = valpart[len(ln.pre) + len(ln.val):] + comment
    else:
        ln.pre, ln.post = valpart, comment
    return ln, cur


class IniDoc:
    """A controls.ini as editable lines. `render()` of an untouched document is the original text."""

    def __init__(self, text=""):
        self.had_bom = text.startswith(BOM)
        if self.had_bom:
            text = text[len(BOM):]
        self.nl = "\r\n" if "\r\n" in text else ("\n" if "\n" in text else "\r\n")
        self.lines = []
        parts = text.split("\n")
        if parts and parts[-1] == "":
            parts.pop()
            last_has_eol = True
        else:
            last_has_eol = False
        cur = None
        for i, raw in enumerate(parts):
            eol = "\n"
            if raw.endswith("\r"):
                raw, eol = raw[:-1], "\r\n"
            if i == len(parts) - 1 and not last_has_eol:
                eol = ""
            ln, cur = _parse(raw, cur)
            ln.eol = eol
            self.lines.append(ln)

    def render(self):
        return "".join(l.text + l.eol for l in self.lines)

    def copy(self):
        return IniDoc(self.render())

    # ---------------------------------------------------------------- sections
    def find_section(self, name):
        """Index of the header of the FIRST section called `name` (the game ignores later ones), or None."""
        low = name.lower()
        for i, l in enumerate(self.lines):
            if l.kind == "section" and l.name.lower() == low:
                return i
        return None

    def section_end(self, h):
        for i in range(h + 1, len(self.lines)):
            if self.lines[i].kind == "section" or (self.lines[i].kind == "junk" and self.lines[i].section is None):
                return i
        return len(self.lines)

    def section_names(self):
        seen, out = set(), []
        for l in self.lines:
            if l.kind == "section" and l.name.lower() not in seen:
                seen.add(l.name.lower())
                out.append(l.name)
        return out

    def count_sections(self):
        return sum(1 for l in self.lines if l.kind == "section")

    def count_kv(self):
        return sum(1 for l in self.lines if l.kind == "kv")

    def kv_indices(self, name):
        h = self.find_section(name)
        if h is None:
            return []
        return [i for i in range(h + 1, self.section_end(h)) if self.lines[i].kind == "kv"]

    def get(self, name, key):
        """The value of `key` in the section (the last line wins, like the game), or None."""
        found = None
        for i in self.kv_indices(name):
            if self.lines[i].key.lower() == key.lower():
                found = self.lines[i].val
        return found

    def _eol_before_append(self):
        if self.lines and self.lines[-1].eol == "":
            self.lines[-1].eol = self.nl

    def ensure_section(self, name, note=True):
        """Index of the section's header; a missing section is added at the end of the file."""
        h = self.find_section(name)
        if h is not None:
            return h
        self._eol_before_append()
        if self.lines and self.lines[-1].kind != "blank":
            self.lines.append(Line("blank", "", self.nl))
        self.lines.append(Line("section", f"[{name}]", self.nl))
        self.lines[-1].name = name
        cur = len(self.lines) - 1
        if note:
            self.lines.append(Line("comment", NOTE, self.nl, section=name))
        return cur

    def _append_pos(self, h):
        """Where a new key=value line of this section goes: after its last key line, and after the comment
        lines that directly follow it (they describe that line); a section without keys: after the header and
        the comment block under it."""
        end = self.section_end(h)
        last = h
        for i in range(h + 1, end):
            if self.lines[i].kind == "kv":
                last = i
        pos = last + 1
        while pos < end and self.lines[pos].kind == "comment":
            pos += 1
        return pos

    def add_kv(self, name, key, val):
        h = self.ensure_section(name)
        pos = self._append_pos(h)
        ln = Line("kv", "", self.nl, section=self.lines[h].name)
        ln.key, ln.keyraw, ln.val = key, key + " ", val
        ln.pre = " " if val else ""
        ln.rebuild()
        if pos >= len(self.lines):
            self._eol_before_append()
        self.lines.insert(pos, ln)
        return pos

    def set_value(self, name, key, val):
        """`key = val` in the section: the game reads the last such line, so that one changes, earlier
        duplicates go, and a missing key is added."""
        idx = [i for i in self.kv_indices(name) if self.lines[i].key.lower() == key.lower()]
        if not idx:
            self.add_kv(name, key, val)
            return
        self.lines[idx[-1]].set_val(val)
        for i in reversed(idx[:-1]):
            del self.lines[i]

    def remove_lines(self, indices):
        for i in sorted(set(indices), reverse=True):
            del self.lines[i]

    def remove_key(self, name, key):
        idx = [i for i in self.kv_indices(name) if self.lines[i].key.lower() == key.lower()]
        self.remove_lines(idx)
        return len(idx)

    def prune_section(self, name):
        """Drop a section the launcher made once nothing but its own note is left in it."""
        h = self.find_section(name)
        if h is None:
            return False
        end = self.section_end(h)
        body = self.lines[h + 1:end]
        if any(l.kind == "kv" or l.kind == "junk" or (l.kind == "comment" and l.text != NOTE) for l in body):
            return False
        start = h
        if start > 0 and self.lines[start - 1].kind == "blank":
            start -= 1
        del self.lines[start:end]
        return True


# ---------------------------------------------------------------------- the buttons of the screen

Slot = namedtuple("Slot", "key label group mask")

SLOT_GROUPS = (
    ("attack", N_("Attack buttons")),
    ("macro", N_("Several buttons with one press (macros)")),
    ("menu", N_("Start, Select and the other buttons")),
    ("dir", N_("Directions")),
)


def _slots():
    rows = [
        ("1", N_("1 (Left Punch)"), "attack"), ("2", N_("2 (Right Punch)"), "attack"),
        ("3", N_("3 (Left Kick)"), "attack"), ("4", N_("4 (Right Kick)"), "attack"),
    ]
    rows += [(k, k, "macro") for k in (
        "1+2", "3+4", "1+3", "2+4", "1+4", "2+3", "1+2+3", "1+2+4", "1+3+4", "2+3+4", "1+2+3+4")]
    rows += [("START", N_("Start / pause"), "menu"), ("SELECT", N_("Select"), "menu"),
             ("L1", "L1", "menu"), ("R1", "R1", "menu"), ("L2", "L2", "menu"), ("R2", "R2", "menu"),
             ("L3", "L3", "menu"), ("R3", "R3", "menu"),
             ("UP", N_("Up"), "dir"), ("DOWN", N_("Down"), "dir"), ("LEFT", N_("Left"), "dir"),
             ("RIGHT", N_("Right"), "dir")]
    return tuple(Slot(k, lab, grp, padmap.target_mask(k)) for k, lab, grp in rows)


SLOTS = _slots()
SLOT_BY_KEY = {s.key: s for s in SLOTS}
SLOT_BY_MASK = {s.mask: s for s in SLOTS}
assert all(s.mask for s in SLOTS) and len(SLOT_BY_MASK) == len(SLOTS)
ATTACK_KEYS = tuple(s.key for s in SLOTS if s.group == "attack")
GUIDED_BUTTONS = ("1", "2", "3", "4", "1+2", "3+4", "1+3", "2+4", "1+2+3+4", "START", "SELECT")
GUIDED_DIRECTIONS = ("UP", "DOWN", "LEFT", "RIGHT")


def mask_text(mask):
    """A button mask as controls.ini would name it: 1 2 3 4 for the face buttons, + between several."""
    names = {padmap.PS3_BIT["SQUARE"]: "1", padmap.PS3_BIT["TRIANGLE"]: "2", padmap.PS3_BIT["CROSS"]: "3",
             padmap.PS3_BIT["CIRCLE"]: "4"}
    face = [names[b] for b in sorted(names, key=lambda b: names[b]) if mask & b]
    rest = [n for n, b in padmap.PS3_BIT.items() if mask & b and b not in names]
    order = ["START", "SELECT", "L1", "R1", "L2", "R2", "L3", "R3", "UP", "DOWN", "LEFT", "RIGHT"]
    rest.sort(key=lambda n: order.index(n) if n in order else 99)
    return "+".join(face + rest) or "-"


# ---------------------------------------------------------------------- layout presets

Spec = namedtuple("Spec", "preset macros lines port")      # port: {"stick": .., "socd": ..}
Recipe = namedtuple("Recipe", "id titles summary specs")

_NONE = ()


def _spec(preset, macros=None, lines=_NONE, port=None):
    return Spec(preset, macros, tuple(lines), dict(port or {}))


# Every preset name here exists in the runtime (tests/test_controls_ui.py checks them against patch 0009).
RECIPES = (
    Recipe("default",
           {XINPUT: N_("Xbox pad, default"), DINPUT: N_("PlayStation pad, default")},
           {XINPUT: N_("X Y A B are 1 2 3 4; bumpers and triggers are L1 R1 L2 R2."),
            DINPUT: N_("Square Triangle Cross Circle are 1 2 3 4 (DualShock 4, DualSense and most "
                       "PS3/PS4-mode sticks).")},
           {XINPUT: _spec("standard"), DINPUT: _spec("ps")}),
    Recipe("switch", {DINPUT: N_("Switch pad, default")},
           {DINPUT: N_("Y X B A are 1 2 3 4 (Switch Pro controller, sticks in Switch mode).")},
           {DINPUT: _spec("switch")}),
    Recipe("xbox_hid", {DINPUT: N_("Xbox-style pad (generic)")},
           {DINPUT: N_("A B X Y buttons and LB RB, for Xbox-like pads that Windows does not give to XInput.")},
           {DINPUT: _spec("xbox")}),
    Recipe("vewlix",
           {XINPUT: N_("8-button stick (Vewlix layout)"),
            DINPUT: N_("8-button stick (Vewlix layout)")},
           {XINPUT: N_("Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: X Y RB LB over A B RT LT."),
            DINPUT: N_("Top row 1 2 [1+2] [1+3], bottom row 3 4 [3+4] [2+4]: B1 B4 B6 B5 over B2 B3 B8 B7.")},
           {XINPUT: _spec("standard", "tekken"), DINPUT: _spec("ps", "tekken")}),
    Recipe("astro",
           {XINPUT: N_("6-button stick (Noir / Sega Astro)"),
            DINPUT: N_("6-button stick (Noir / Sega Astro)")},
           {XINPUT: N_("Top row 1 2 [1+2], bottom row 3 4 [3+4]: X Y RB over A B RT. LB and LT stay L1 and L2."),
            DINPUT: N_("Top row 1 2 [1+2], bottom row 3 4 [3+4]: B1 B4 B6 over B2 B3 B8. B5 and B7 stay "
                       "L1 and L2.")},
           {XINPUT: _spec("standard", lines=("1+2=RB", "3+4=RT")),
            DINPUT: _spec("ps", lines=("1+2=B6", "3+4=B8"))}),
    Recipe("hitbox",
           {XINPUT: N_("Hitbox"), DINPUT: N_("Hitbox")},
           {XINPUT: N_("The 8-button layout above. Directions come from the d-pad or the left stick, which is read "
                       "as 8-way d-pad presses; left+right (up+down) at once cancel."),
            DINPUT: N_("The 8-button layout above. Directions come from the hat or the left stick, which is read "
                       "as 8-way d-pad presses; left+right (up+down) at once cancel.")},
           {XINPUT: _spec("standard", "tekken", port={"stick": "dpad", "socd": "neutral"}),
            DINPUT: _spec("ps", "tekken", port={"stick": "dpad", "socd": "neutral"})}),
)
RECIPE_BY_ID = {r.id: r for r in RECIPES}


def recipes_for(kind):
    return [r for r in RECIPES if kind in r.specs]


def recipe_title(recipe, kind):
    return recipe.titles.get(kind) or next(iter(recipe.titles.values()))


def recipe_text(kind, spec):
    """The lines the preset stands for, as a one-section controls.ini (to compute what it binds)."""
    out = [f"[{kind}]", f"preset = {spec.preset}"]
    if spec.macros:
        out.append(f"macros = {spec.macros}")
    out += list(spec.lines)
    return "\n".join(out) + "\n"


def recipe_pairs(kind, spec):
    """{(source, mask)} the preset binds on a device of this kind."""
    tab = padmap.Controls(recipe_text(kind, spec)).table(kind, -1, 0, 0)
    return frozenset((s, m) for s, m in tab.binds)


# ---------------------------------------------------------------------- sources, for people

def describe_source(kind, src):
    """A source name as the screen shows it. The file keeps the raw name; this is for reading."""
    if kind == XINPUT:
        names = {"DUP": "D-pad up", "DDOWN": "D-pad down", "DLEFT": "D-pad left", "DRIGHT": "D-pad right",
                 "LUP": "left stick up", "LDOWN": "left stick down", "LLEFT": "left stick left",
                 "LRIGHT": "left stick right", "RUP": "right stick up", "RDOWN": "right stick down",
                 "RLEFT": "right stick left", "RRIGHT": "right stick right", "BACK": "Back",
                 "LS": "left stick click", "RS": "right stick click"}
        return names.get(src, src)
    m = re.fullmatch(r"HAT(\d?)_(UP|DOWN|LEFT|RIGHT)", src)
    if m:
        return f"hat{m.group(1)} {m.group(2).lower()}"
    m = re.fullmatch(r"([A-Z0-9]+)([+-])", src)
    if m:
        return f"axis {m.group(1)}{m.group(2)}"
    return src


# ---------------------------------------------------------------------- the editor

DeviceRef = namedtuple("DeviceRef", "kind port vid pid")


class FileChanged(Exception):
    """controls.ini was changed on disk after the screen loaded it."""


def split_sources(val):
    return [tok for tok in re.split(r"[ ,\t]+", val.strip()) if tok]


def _is_managed_key(key):
    k = key.strip().upper()
    return k in ("PRESET", "MACROS") or k in padmap.AXIS_TARGETS or padmap.target_mask(key) != 0


def _is_target_key(key):
    return key.strip().upper() not in ("PRESET", "MACROS") and key.strip().upper() not in padmap.AXIS_TARGETS \
        and padmap.target_mask(key) != 0


def controls_path(out_dir, env=None):
    """The file the game reads, found the way it finds it; a file that is not there yet goes where the
    README says: `<output>\\controls.ini` (PS3_CONTROLS, from Settings or the environment, wins)."""
    merged = dict(os.environ)
    merged.update(env or {})
    forced = merged.get("PS3_CONTROLS")
    if forced:
        return forced
    return padmap.find_controls_ini(out_dir, env) or os.path.join(out_dir, "controls.ini")


class ControlsEditor:
    def __init__(self, text="", path=None, on_disk=None):
        self.path = path
        self.doc = IniDoc(text)
        self.saved_text = self.doc.render()
        self.disk_bytes = on_disk              # the bytes read from the file, None: no such file
        self.notes = []                         # what the last edit did besides the obvious (for the status line)
        self.backed_up = False
        self._ver = 0
        self._ctl = None

    # ---------------------------------------------------------------- load / save
    @classmethod
    def load(cls, path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            return cls("", path, None)
        return cls(raw.decode("latin-1"), path, raw)

    @property
    def exists(self):
        return self.disk_bytes is not None

    @property
    def dirty(self):
        return self.doc.render() != self.saved_text

    def validate(self):
        """Problems that would make the game ignore part of the file silently."""
        out = []
        if self.doc.count_kv() >= MAX_KV:
            out.append(t("The file has {n} settings; the game reads at most {max}.", n=self.doc.count_kv(),
                         max=MAX_KV - 1))
        if self.doc.count_sections() >= MAX_SECTIONS:
            out.append(t("The file has {n} sections; the game reads at most {max}.", n=self.doc.count_sections(),
                         max=MAX_SECTIONS - 1))
        return out

    def save(self, path=None, force=False):
        """Write the file (atomically; the file as it was goes to controls.ini.bak once per session)."""
        path = path or self.path
        if not path:
            raise ValueError("no path")
        problems = self.validate()
        if problems:
            raise ValueError(" ".join(problems))
        if os.path.exists(path):
            with open(path, "rb") as f:
                now = f.read()
            if self.disk_bytes is not None and now != self.disk_bytes and not force:
                raise FileChanged(path)
            if self.disk_bytes is None and now and not force:
                raise FileChanged(path)
        else:
            now = None
        text = self.doc.render()
        data = text.encode("latin-1", "replace")
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        if now is not None and now != data and (not self.backed_up or now != self.disk_bytes):
            try:
                with open(path + ".bak", "wb") as f:
                    f.write(now)
                self.backed_up = True
            except OSError:
                pass
        fd, tmp = tempfile.mkstemp(prefix="controls-", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        self.path = path
        self.disk_bytes = data
        self.saved_text = text
        return path

    def revert(self):
        self.doc = IniDoc(self.saved_text)
        self.notes = []
        self._touch()

    def reload(self):
        """Read the file again (it changed on disk); unsaved edits are lost."""
        if self.path:
            fresh = ControlsEditor.load(self.path)
            self.doc, self.saved_text, self.disk_bytes = fresh.doc, fresh.saved_text, fresh.disk_bytes
            self.notes = []
            self._touch()

    # ---------------------------------------------------------------- reading
    def _touch(self):
        self._ver += 1
        self._ctl = None

    def controls(self):
        """The game's view of the text as it is now (padmap.Controls); the same object until the next edit."""
        if self._ctl is None:
            self._ctl = padmap.Controls(self.doc.render(), self.path)
        return self._ctl

    def table(self, dev):
        return self.controls().table(dev.kind, dev.port, dev.vid, dev.pid)

    def sources(self, dev, key):
        """Sources that are exactly this button (a Tekken name or macro) on this controller, in binding order."""
        return list(self.table(dev).sources_exactly(padmap.target_mask(key)))

    def layers(self, dev):
        """[(scope, section name)] from the least to the most specific; the later ones win."""
        out = [(SCOPE_KIND, dev.kind)]
        if dev.kind == DINPUT and dev.vid:
            out.append((SCOPE_MODEL, f"dinput.{dev.vid:04X}:{dev.pid:04X}"))
        if dev.port >= 0:
            out.append((SCOPE_PORT, f"port{dev.port + 1}.{dev.kind}"))
        return out

    def section_for(self, dev, scope):
        for sc, name in self.layers(dev):
            if sc == scope:
                return name
        raise KeyError(scope)

    def scopes(self, dev):
        return [sc for sc, _ in self.layers(dev)]

    def has_content(self, section, preset_counts=True):
        for i in self.doc.kv_indices(section):
            k = self.doc.lines[i].key
            if k.strip().upper() == "PRESET" and not preset_counts:
                continue
            if _is_managed_key(k):
                return True
        return False

    def default_scope(self, dev):
        """Where an edit goes unless the person says otherwise: into the most specific section that already
        holds buttons of this controller; else this model (DirectInput) / all pads of the kind (XInput)."""
        layers = self.layers(dev)
        for sc, name in reversed(layers):
            if self.has_content(name, preset_counts=(sc != SCOPE_KIND)):
                return sc
        return SCOPE_MODEL if any(sc == SCOPE_MODEL for sc, _ in layers) else SCOPE_KIND

    def own_masks(self, dev, scope):
        """Masks of the buttons that have a line of their own in this scope's section."""
        return {m for _i, m in self._target_lines(self.section_for(dev, scope))}

    def more_specific(self, dev, scope):
        names = [n for _sc, n in self.layers(dev)]
        return names[names.index(self.section_for(dev, scope)) + 1:]

    def preset_name(self, dev):
        """The preset the game uses for this controller (the most specific layer that names one, else the default)."""
        for _sc, name in reversed(self.layers(dev)):
            v = self.doc.get(name, "preset")
            if v:
                return v.lower()
        return padmap.default_preset(dev.kind, dev.vid)

    def macros_on(self, dev):
        return "tekken macros" in self.table(dev).desc

    def detect_recipe(self, dev):
        """The id of the preset the controller's bindings equal right now, or None (own layout)."""
        have = frozenset((s, m) for s, m in self.table(dev).binds)
        same = [r for r in recipes_for(dev.kind) if recipe_pairs(dev.kind, r.specs[dev.kind]) == have]
        for r in same:                  # a preset that also sets the port's options counts when they are set
            port = r.specs[dev.kind].port
            if port and dev.port >= 0 and port.get("stick") == self.stick_of(dev.port) \
                    and port.get("socd") == self.socd_of(dev.port):
                return r.id
        for r in same:
            if not r.specs[dev.kind].port:
                return r.id
        return None

    def socd_of(self, port):
        c = self.controls()
        v = (c._get(f"port{port + 1}", "socd") or c._get("general", "socd") or "neutral").lower()
        return v if v in SOCD_MODES else ("off" if v == "0" else "neutral")

    def stick_of(self, port):
        v = (self.controls()._get(f"port{port + 1}", "stick") or "analog").lower()
        return v if v in STICK_MODES else "analog"

    def pinned(self, port):
        return (self.doc.get(f"port{port + 1}", "device") or "auto").strip()

    # ---------------------------------------------------------------- editing helpers
    def _prepare(self):
        """Before the first change to an empty file: the header comment."""
        if not any(l.kind != "blank" for l in self.doc.lines):
            self.doc.lines = [Line("comment", h, self.doc.nl) for h in HEADER]
        self.notes = []

    def _target_lines(self, section):
        out = []
        for i in self.doc.kv_indices(section):
            k = self.doc.lines[i].key
            if _is_target_key(k):
                out.append((i, padmap.target_mask(k)))
        return out

    def _strip_sources(self, section, srcs, kind, keep_mask):
        """Take these sources off the other button lines of the section (an explicit binding means 'this
        button now does that', not 'also'). A line left without sources stays as `TARGET =`."""
        changed = 0
        for i, mask in self._target_lines(section):
            if mask == keep_mask:
                continue
            ln = self.doc.lines[i]
            toks = split_sources(ln.val)
            kept = [tok for tok in toks if padmap.canon_source(kind, tok) not in srcs]
            if len(kept) != len(toks):
                ln.set_val(" ".join(kept))
                changed += 1
        return changed

    def _drop_target(self, section, mask):
        idx = [i for i, m in self._target_lines(section) if m == mask]
        self.doc.remove_lines(idx)
        return len(idx)

    def _managed_indices(self, section):
        return [i for i in self.doc.kv_indices(section) if _is_managed_key(self.doc.lines[i].key)]

    def _override_note(self, names, what):
        if names:
            self.notes.append(t("Changed lines of {sections} that would have overridden this ({what}).",
                                sections=", ".join(f"[{n}]" for n in names), what=what))

    # ---------------------------------------------------------------- edits
    def pairs(self, dev):
        """The controller's bindings as the game computes them: [(source, mask)] in binding order."""
        return [(s, m) for s, m in self.table(dev).binds]

    def _write_line(self, kind, section, mask, key, srcs):
        """The one line of this section for the button `mask`: `key = srcs` (changed in place when there is
        one, else added). The sources are taken off the section's other button lines."""
        self.doc.ensure_section(section)
        self._strip_sources(section, set(srcs), kind, mask)
        idx = [i for i, m in self._target_lines(section) if m == mask]
        val = " ".join(srcs)
        if idx:
            self.doc.lines[idx[0]].set_val(val)
            self.doc.remove_lines(idx[1:])
        else:
            self.doc.add_kv(section, key, val)

    def _reconcile(self, dev, scope, expected):
        """An edit means exactly one thing: this button gets these sources, they leave whatever had them, and
        nothing else changes. Taking a line out of the file can give a button its old source back (a line
        that took it from the preset). If the game's result differs from the meant one, the buttons that
        differ get a line that says what they had -- in the section being edited, and if a more specific
        section of the file still wins, in that one."""
        layers = [n for _sc, n in self.layers(dev)]
        first = layers.index(self.section_for(dev, scope))
        for step in range(len(layers) - first + 1):
            self._touch()
            actual = self.pairs(dev)
            if set(actual) == set(expected):
                return True
            sec = layers[min(first + step, len(layers) - 1)]
            for mask in sorted({m for _s, m in set(actual) ^ set(expected)}):
                self._write_line(dev.kind, sec, mask, mask_text(mask), [s for s, m in expected if m == mask])
        self._touch()
        ok = set(self.pairs(dev)) == set(expected)
        if not ok:
            self.notes.append(t("Lines of your file in other sections still change some buttons."))
        return ok

    def bind(self, dev, scope, key, sources, add=False):
        """Make `sources` the buttons for Tekken button / macro `key` on this controller. A source that did
        something else loses that. Returns the sources now bound (as the game sees them)."""
        mask = padmap.target_mask(key)
        if not mask:
            raise ValueError(f"unknown button {key!r}")
        srcs = list(self.sources(dev, key)) if add else []
        for s in sources:
            c = padmap.canon_source(dev.kind, s)
            if c is None:
                raise ValueError(f"unknown {dev.kind} input {s!r}")
            if c not in srcs:
                srcs.append(c)
        srcs = srcs[:MAX_SOURCES]
        self._prepare()
        sec = self.section_for(dev, scope)
        expected = [(s, m) for s, m in self.pairs(dev) if s not in srcs and m != mask] + [(s, mask) for s in srcs]
        self._write_line(dev.kind, sec, mask, key, srcs)
        over = []
        for other in self.more_specific(dev, scope):
            n = self._drop_target(other, mask) + self._strip_sources(other, set(srcs), dev.kind, mask)
            if n:
                over.append(other)
                self.doc.prune_section(other)
        self._override_note(over, key)
        self._reconcile(dev, scope, expected)
        return self.sources(dev, key)

    def clear(self, dev, scope, key):
        """No button for `key` on this controller (also where the preset had one)."""
        mask = padmap.target_mask(key)
        if not mask:
            raise ValueError(f"unknown button {key!r}")
        self._prepare()
        sec = self.section_for(dev, scope)
        expected = [(s, m) for s, m in self.pairs(dev) if m != mask]
        self._drop_target(sec, mask)
        over = []
        for other in self.more_specific(dev, scope):
            if self._drop_target(other, mask):
                over.append(other)
                self.doc.prune_section(other)
        self._override_note(over, key)
        self._touch()
        if self.sources(dev, key):                  # the preset or a shared section has one: say "none"
            self.doc.add_kv(sec, key, "")
        self._reconcile(dev, scope, expected)
        if not self.doc.kv_indices(sec):
            self.doc.prune_section(sec)
        return self.sources(dev, key)

    def apply_recipe(self, dev, scope, recipe_id):
        """The controller gets this preset's layout: the section keeps only what the preset says (its own
        button lines go; comments and keys that are not about buttons stay). Port options of the preset are
        set on the controller's port."""
        self._prepare()
        r = RECIPE_BY_ID[recipe_id]
        spec = r.specs[dev.kind]
        sec = self.section_for(dev, scope)
        self.doc.ensure_section(sec)
        self.doc.remove_lines(self._managed_indices(sec))
        self.doc.set_value(sec, "preset", spec.preset)
        if spec.macros:
            self.doc.set_value(sec, "macros", spec.macros)
        for line in spec.lines:
            k, _, v = line.partition("=")
            self.doc.add_kv(sec, k, v)
        over = []
        for other in self.more_specific(dev, scope):
            if self._managed_indices(other):
                self.doc.remove_lines(self._managed_indices(other))
                self.doc.prune_section(other)
                over.append(other)
        if not spec.macros and dev.port >= 0 and self.doc.get(f"port{dev.port + 1}", "macros"):
            self.doc.remove_key(f"port{dev.port + 1}", "macros")
        self._override_note(over, recipe_title(r, dev.kind))
        if dev.port >= 0:
            for k, v in spec.port.items():
                self.doc.set_value(f"port{dev.port + 1}", k, v)
        self._touch()
        want = recipe_pairs(dev.kind, spec)
        have = frozenset((s, m) for s, m in self.table(dev).binds)
        if want != have:
            others = [n for _sc, n in self.layers(dev) if n != sec and self._managed_indices(n)]
            self.notes.append(t("Other lines in your file ({sections}) still change this layout.",
                                sections=", ".join(f"[{n}]" for n in others) or "controls.ini"))
        return have == want

    def reset(self, dev, shared=False):
        """Back to the defaults for this controller: its model and port sections lose their button lines and
        preset (`shared`: the section of all pads of the kind too), and its port goes back to the default
        stick mode and SOCD. Comments, `[general]` and device pins stay."""
        self._prepare()
        names = [n for sc, n in self.layers(dev) if sc != SCOPE_KIND or shared]
        removed = 0
        for n in names:
            removed += len(self._managed_indices(n))
            self.doc.remove_lines(self._managed_indices(n))
            self.doc.prune_section(n)
        if dev.port >= 0:
            port = f"port{dev.port + 1}"
            general = (self.doc.get("general", "socd") or "neutral").lower()
            default = {"stick": "analog", "socd": "neutral" if general in ("", "neutral") else general}
            for k in ("stick", "socd", "macros"):
                v = (self.doc.get(port, k) or "").lower()
                if v and v != default.get(k):           # (a line that says what the default says can stay)
                    removed += self.doc.remove_key(port, k)
        self._touch()
        self.notes.append(t("{n} lines removed.", n=removed))
        return removed

    def set_port_option(self, port, key, value):
        """`[portN] stick = analog|dpad` / `socd = neutral|up|last|off`."""
        key = key.lower()
        if (key, value) not in [("stick", v) for v in STICK_MODES] + [("socd", v) for v in SOCD_MODES]:
            raise ValueError(f"{key} = {value}")
        self._prepare()
        self.doc.set_value(f"port{port + 1}", key, value)
        self._touch()

    def assign_port(self, spec, port):
        """Pin the controller `spec` (e.g. dinput:0F0D:00EE, xinput:0) to player `port` (0-based); None: automatic
        again. Another port pinned to the same controller goes back to auto."""
        self._prepare()
        for p in range(padmap.MAX_PORTS):
            sec = f"port{p + 1}"
            cur = (self.doc.get(sec, "device") or "").strip()
            if p == port:
                self.doc.set_value(sec, "device", spec)
            elif cur.lower() == spec.lower():
                self.doc.set_value(sec, "device", "auto")
        self._touch()
