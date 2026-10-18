"""English and German texts for the launcher and the Online tab.

    from t5lobby.i18n import t, N_

    label = t("Quick Match")                           # English text in, text in the player's language out
    line = t("Connecting to {server}...", server=name)   # values go in by name: German may reorder them
    STATUS = {"idle": N_("in lobby")}                  # N_ marks a text now ...
    shown = t(STATUS[key])                             # ... and t() translates it where it is shown

The English text is the key. t() returns it unchanged in English and for any text the German catalog
(i18n_de.py) does not have, so a missing translation shows English and never breaks a screen.
Rules for new texts:

* Always a string literal in t() / N_(), never an f-string and never a variable built from pieces
  (tests/test_i18n.py finds the texts in the source and checks the catalog against them).
* Placeholders are `{name}` with keyword values; the German text must carry the same names.
* One text, one meaning: a short word that means two things gets two English spellings.
* Do not name a local variable `t` or `N_` in a function that uses them.

The language is chosen once, at start (init()). Until then everything is English, so the lobby server,
the tools and every test that does not ask for German run in English. Texts that arrive from the lobby
server or from a build tool are English; translate_message() puts known ones into German (the list is
i18n_known.py) and leaves unknown ones as they are.
"""
import os
import re

CHOICES = ("auto", "de", "en")             # what the Settings box offers (launcher.json "language")
LANGUAGES = {"en": "English", "de": "Deutsch"}

_lang = "en"
_cat = {}              # English text -> text in the current language ({} while English)
_missing = set()       # texts asked for in a language that has no entry for them (tests, development)
_patterns = None       # [(regex, English template)] for translate_message()


def system_language():
    """'de' or 'en': the language of this PC's Windows (user interface language); anything but German -> 'en'.
    T5_LANG=de|en overrides it (development, tests)."""
    forced = os.environ.get("T5_LANG", "").strip().lower()
    if forced in LANGUAGES:
        return forced
    if os.name == "nt":
        try:
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if (langid & 0x3FF) == 0x07:          # LANG_GERMAN (de-DE, de-AT, de-CH, ...)
                return "de"
            return "en"
        except (AttributeError, OSError):
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v:
            return "de" if v.lower().startswith("de") else "en"
    return "en"


def resolve(choice):
    """'auto' | 'de' | 'en' (anything else counts as auto) -> 'de' | 'en'."""
    choice = str(choice or "auto").strip().lower()
    return choice if choice in LANGUAGES else system_language()


def init(choice="auto"):
    """Pick the language for this process (call once, before the first window is built). -> 'de' | 'en'."""
    return set_language(resolve(choice))


def set_language(lang):
    global _lang, _cat, _patterns
    lang = lang if lang in LANGUAGES else "en"
    _lang = lang
    _patterns = None
    _cat = {}
    if lang == "de":
        from . import i18n_de
        _cat = i18n_de.MESSAGES
    return _lang


def language():
    return _lang


def N_(text):
    """Marks a text for translation without translating it (module level tables, defaults)."""
    return text


def _has_words(text):
    return any(c.isalpha() for c in text)       # "", "0", "-" and "1 / 2" need no translation


def t(text, **values):
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
    """A number for reading: 2.3 in English, 2,3 in German (thousands separators are not used)."""
    s = f"{value:.{digits}f}"
    return s.replace(".", ",") if _lang == "de" else s


def stamp(ts):
    """Day and time of a unix time, short: '18 Oct 21:05' / '18.10. 21:05'."""
    import time
    lt = time.localtime(ts)
    if _lang == "de":
        return time.strftime("%d.%m. %H:%M", lt)
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{lt.tm_mday} {months[lt.tm_mon - 1]} {time.strftime('%H:%M', lt)}"


def clock(seconds):
    """m:ss for a number of seconds."""
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


# ---------------------------------------------------------------------------- texts from outside

_HOLE = re.compile(r"\{(\w+)\}")


def _compile_patterns():
    """Regexes for the known English message templates that carry {placeholders} (i18n_known.py)."""
    from . import i18n_known
    pats = []
    for tpl in i18n_known.templates():
        parts = _HOLE.split(tpl)            # text, name, text, name, ... text
        rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(parts))
        literal = sum(len(p) for p in parts[::2])
        pats.append((literal, re.compile(rx + r"\Z", re.S), tpl))
    pats.sort(key=lambda x: -x[0])         # the more specific template first
    return [(rx, tpl) for _n, rx, tpl in pats]


def translate_message(msg):
    """A text that came in English from the lobby server, the build tool or a library: the same text in
    the current language when it is a known one, else `msg` unchanged. Never raises."""
    global _patterns
    if _lang == "en" or not isinstance(msg, str) or not msg:
        return msg
    hit = _cat.get(msg)
    if hit is not None and not _HOLE.search(msg):
        return hit
    if _patterns is None:
        try:
            _patterns = _compile_patterns()
        except Exception:     # noqa: BLE001 -- no list: English
            _patterns = []
    for rx, tpl in _patterns:
        m = rx.match(msg)
        if m:
            german = _cat.get(tpl)
            if german is None:
                return msg
            vals = {k: _cat.get(v, v) for k, v in m.groupdict().items()}      # (status words: "idle", "queue", ...)
            try:
                return german.format(**vals)
            except (KeyError, IndexError, ValueError):
                return msg
    return msg


