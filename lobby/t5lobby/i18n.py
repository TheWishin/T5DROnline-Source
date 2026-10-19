"""The texts of the launcher and the Online tab in the player's language.

    from t5lobby.i18n import t, N_

    label = t("Quick Match")                           # English text in, text in the player's language out
    line = t("Connecting to {server}...", server=name)   # values go in by name: a language may reorder them
    STATUS = {"idle": N_("in lobby")}                  # N_ marks a text now ...
    shown = t(STATUS[key])                             # ... and t() translates it where it is shown

The English text is the key. Each other language has a catalog with the same keys: German (i18n_de.py),
Spanish (i18n_es.py), Korean (i18n_ko.py), Japanese (i18n_ja.py), Brazilian Portuguese (i18n_pt_br.py) and
French (i18n_fr.py). t() returns the English text unchanged in English and for any text the catalog does not
have, so a missing translation shows English and never breaks a screen. Rules for new texts:

* Always a string literal in t() / N_(), never an f-string and never a variable built from pieces
  (tests/test_i18n.py finds the texts in the source and checks every catalog against them).
* Placeholders are `{name}` with keyword values; every translation must carry the same names.
* One text, one meaning: a short word that means two things gets two English spellings.
* Do not name a local variable `t` or `N_` in a function that uses them.
* A new text needs an entry in every catalog: python tools/i18n_extract.py --skeleton.

The language is chosen once, at start (init()). Until then everything is English, so the lobby server,
the tools and every test that does not ask for another language run in English. Texts that arrive from the
lobby server or from a build tool are English; translate_message() puts known ones into the player's language
(the list is i18n_known.py) and leaves unknown ones as they are.
"""
import importlib
import os
import re

# The languages, in the order the Settings box lists them, each in its own name (launcher.json "language").
LANGUAGES = {"en": "English", "de": "Deutsch", "es": "Español", "ko": "한국어", "ja": "日本語",
             "pt-BR": "Português (Brasil)", "fr": "Français"}
CHOICES = ("auto",) + tuple(LANGUAGES)
CATALOGS = {"de": "i18n_de", "es": "i18n_es", "ko": "i18n_ko", "ja": "i18n_ja", "pt-BR": "i18n_pt_br",
            "fr": "i18n_fr"}
# Windows primary language ids (the low 10 bits of a LANGID) -> our language. Every Portuguese Windows gets
# Brazilian Portuguese, every Spanish / French / German one its language, whatever the country.
WINDOWS_LANGIDS = {0x07: "de", 0x0A: "es", 0x12: "ko", 0x11: "ja", 0x16: "pt-BR", 0x0C: "fr"}
DECIMAL_COMMA = ("de", "pt-BR", "fr")       # 2,3 instead of 2.3 (Spanish keeps the point, as the RAE suggests)

# Segoe UI and Bahnschrift have no Hangul, kana or kanji. Tk on Windows then draws those characters with the
# first installed font it finds that has them (for Japanese often a Chinese one, so kanji get Chinese shapes),
# with Segoe UI's line height. Korean and Japanese get a Windows font of their own instead (the first one that
# is installed; Malgun Gothic and Yu Gothic UI come with Windows 8.1 and later).
FONTS = {"ko": ("Malgun Gothic",), "ja": ("Yu Gothic UI", "Meiryo UI", "Meiryo", "MS UI Gothic")}

_lang = "en"
_cat = {}              # English text -> text in the current language ({} while English)
_missing = set()       # texts asked for in a language that has no entry for them (tests, development)
_patterns = None       # [(regex, English template)] for translate_message()
_exact = frozenset()   # the known messages without placeholders (i18n_known.py)
_fonts = {}            # language -> the installed family of FONTS (or None), looked up once


def canonical(code):
    """'pt-br', 'PT_BR', 'pt' -> 'pt-BR'; 'de-AT' -> 'de'; anything unknown -> None."""
    code = str(code or "").strip().replace("_", "-").lower()
    for lang in LANGUAGES:
        if code == lang.lower():
            return lang
    base = code.split("-")[0].split(".")[0]
    if base == "pt":
        return "pt-BR"
    return base if base in LANGUAGES else None


def system_language():
    """The language of this PC's Windows (user interface language) when the launcher has it, else 'en'.
    T5_LANG=<code> overrides it (development, tests)."""
    forced = canonical(os.environ.get("T5_LANG", ""))
    if forced:
        return forced
    if os.name == "nt":
        try:
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return WINDOWS_LANGIDS.get(langid & 0x3FF, "en")
        except (AttributeError, OSError):
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v:
            return canonical(v) or "en"
    return "en"


def resolve(choice):
    """'auto' or a language code (case does not matter; anything unknown counts as auto) -> a language code."""
    return canonical(choice) or system_language()


def init(choice="auto"):
    """Pick the language for this process (call once, before the first window is built). -> the language code."""
    return set_language(resolve(choice))


def set_language(lang):
    global _lang, _cat, _patterns
    lang = canonical(lang) or "en"
    _lang = lang
    _patterns = None
    _cat = {}
    if lang in CATALOGS:
        _cat = importlib.import_module("." + CATALOGS[lang], __package__).MESSAGES
    return _lang


def catalog(lang):
    """The catalog of a language (English text -> translation; {} for English)."""
    lang = canonical(lang) or "en"
    return importlib.import_module("." + CATALOGS[lang], __package__).MESSAGES if lang in CATALOGS else {}


def font_of(lang, families=None):
    """The installed font of FONTS for `lang` (Korean, Japanese), or None (a language Segoe UI covers, or none of
    them installed). `families`: the installed ones; else Tk is asked (which needs a Tk window)."""
    names = FONTS.get(canonical(lang) or "")
    if not names:
        return None
    if families is not None:
        return next((n for n in names if n in families), None)
    if lang not in _fonts:
        try:
            import tkinter.font as tkfont
            installed = set(tkfont.families())
        except Exception:     # noqa: BLE001 -- no Tk window yet: Tk's own fallback
            return None
        _fonts[lang] = next((n for n in names if n in installed), None)
    return _fonts[lang]


def ui_family(default="Segoe UI", families=None):
    """The font family for texts in the current language: `default` for the languages Segoe UI covers, the
    installed font of FONTS for Korean and Japanese (`default` when none of them is installed)."""
    return font_of(_lang, families) or default


def language():
    return _lang


def N_(text):
    """Marks a text for translation without translating it (module level tables, defaults)."""
    return text


def _has_words(text):
    return any(c.isalpha() for c in text)       # "", "0", "-" and "1 / 2" need no translation


def t(text, /, **values):
    """The text in the current language, with {name} placeholders filled from the keyword values."""
    out = text
    if _lang != "en" and _has_words(text):
        hit = _cat.get(text)
        if hit is None:
            _missing.add(text)
        else:
            out = hit
    if values:
        try:
            return out.format(**values)
        except (KeyError, IndexError, ValueError, AttributeError):
            return text.format(**values)       # a broken translation must not break a screen
    return out


def missing():
    """Texts that t() could not find in the current language since the last clear_missing()."""
    return sorted(_missing)


def clear_missing():
    _missing.clear()


# ---------------------------------------------------------------------------- numbers and dates

def num(value, digits=0):
    """A number for reading: 2.3 in English, 2,3 in German, Portuguese and French (no thousands separators)."""
    s = f"{value:.{digits}f}"
    return s.replace(".", ",") if _lang in DECIMAL_COMMA else s


def stamp(ts):
    """Day and time of a unix time, short: '18 Oct 21:05', '18.10. 21:05', '18/10 21:05', '10월 18일 21:05',
    '10月18日 21:05'."""
    import time
    lt = time.localtime(ts)
    hm = time.strftime("%H:%M", lt)
    if _lang == "de":
        return f"{lt.tm_mday:02d}.{lt.tm_mon:02d}. {hm}"
    if _lang in ("es", "pt-BR", "fr"):
        return f"{lt.tm_mday:02d}/{lt.tm_mon:02d} {hm}"
    if _lang == "ko":
        return f"{lt.tm_mon}월 {lt.tm_mday}일 {hm}"
    if _lang == "ja":
        return f"{lt.tm_mon}月{lt.tm_mday}日 {hm}"
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{lt.tm_mday:02d} {months[lt.tm_mon - 1]} {hm}"


# ---------------------------------------------------------------------------- texts from outside

_HOLE = re.compile(r"\{(\w+)\}")


def _compile_patterns():
    """Regexes for the known English message templates that carry {placeholders} (i18n_known.py)."""
    global _exact
    from . import i18n_known
    _exact = frozenset(i18n_known.exact())
    pats = []
    for tpl in i18n_known.templates():
        parts = _HOLE.split(tpl)            # text, name, text, name, ... text
        rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(parts))
        literal = sum(len(p) for p in parts[::2])
        pats.append((literal, re.compile(rx + r"\Z", re.S), tpl))
    pats.sort(key=lambda x: -x[0])         # the more specific template first
    return [(rx, tpl) for _n, rx, tpl in pats]


def _param(name, value):
    """A value inside a known message: player states ("idle", "queue") and the pieces of a joined list are
    translated, everything else (names, numbers, paths, texts an admin wrote) stays as it came."""
    if name == "status":
        return _cat.get(value, value)
    if name == "parts":
        return "; ".join(translate_message(x) for x in value.split("; "))
    if name in ("why", "error"):          # a reason that is itself one of the known messages
        return translate_message(value)
    return value


def translate_message(msg):
    """A text that came in English from the lobby server, the build tool or a library: the same text in
    the current language when it is a known one, else `msg` unchanged. Never raises."""
    global _patterns
    if _lang == "en" or not isinstance(msg, str) or not msg:
        return msg
    if _patterns is None:
        try:
            _patterns = _compile_patterns()
        except Exception:     # noqa: BLE001 -- no list: English
            _patterns = []
    if msg in _exact:
        return _cat.get(msg, msg)
    for rx, tpl in _patterns:
        m = rx.match(msg)
        if m:
            translated = _cat.get(tpl)
            if translated is None:
                return msg
            vals = {k: _param(k, v) for k, v in m.groupdict().items()}
            try:
                return translated.format(**vals)
            except (KeyError, IndexError, ValueError):
                return msg
    return msg


