"""Private, reloadable server policy. This module never records submitted text.

Latin entries match complete words. A small, explicit set of native-script entries
may opt into substring matching for languages ordinarily written without spaces.
Policy data is trusted operator input, but bounded and validated before replacement.
"""
import json
import logging
import os
import re
import unicodedata
from itertools import groupby


log = logging.getLogger(__name__)
MAX_BYTES = 256 * 1024
MAX_TERMS = 256
MAX_TERM_LENGTH = 64

# Deliberately a small visual alphabet, not transliteration of arbitrary languages.
_LOOKALIKES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ԛ": "q", "һ": "h", "ӏ": "l",
    "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ι": "i", "κ": "k", "ν": "v",
    "τ": "t", "χ": "x", "ϲ": "c",
})
_SWAPS = {"a": "a4@", "b": "b8", "e": "e3", "g": "g69", "i": "i1!|",
          "l": "l1|", "o": "o0", "s": "s5$", "t": "t7+", "z": "z2"}
# Separators and substitutions do not overlap, keeping repetitions predictable.
# No letters/digits can be skipped. Three punctuation/space characters per gap is
# enough for light evasion. Fragments can cross ordinary word boundaries, so
# operators must review terms against innocent phrases as well as single words.
_GAP = r"(?:[^\w@!|+$]|_){0,3}"


def _normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold()).casefold()
    return "".join(c for c in text if unicodedata.category(c) not in ("Mn", "Mc", "Me", "Cf")).translate(_LOOKALIKES)


def _pattern(term, mode):
    term = _normalize(term)
    if not term or len(term) > MAX_TERM_LENGTH or not all(c.isalpha() for c in term):
        raise ValueError("chat filter terms must contain at most 64 normalized letters")
    runs = []
    for char, chars in groupby(term):
        count = len(list(chars))
        atom = "[" + re.escape(_SWAPS.get(char, char)) + "]"
        # Preserve natural doubles: the country Niger must not match the n-word.
        runs.append(atom + "(?:" + _GAP + atom + "){" + str(count - 1) + "," + str(MAX_TERM_LENGTH - 1) + "}")
    body = _GAP.join(runs)
    # Digits may be substitutions within a term or a numeric username suffix.
    # Only adjacent letters make it part of a larger innocent word.
    word_char = r"[^\W_\d]"
    return re.compile((r"(?<!" + word_char + ")" + body + r"(?!" + word_char + ")")
                      if mode == "word" else body)


def _read(path):
    with open(path, "rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("chat filter data is too large")
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("chat filter data needs version 1")
    entries = data.get("terms")
    if not isinstance(entries, list) or len(entries) > MAX_TERMS:
        raise ValueError("chat filter terms must be a bounded list")
    patterns = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("chat filter entries must be objects")
        term, mode = entry.get("term"), entry.get("match", "word")
        if not isinstance(term, str) or not 1 <= len(term) <= MAX_TERM_LENGTH:
            raise ValueError("chat filter term length is invalid")
        if mode not in ("word", "substring"):
            raise ValueError("chat filter matching mode is invalid")
        patterns.append(_pattern(term, mode))
    return tuple(patterns)


def _signature(path):
    st = os.stat(path)
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


class ChatFilter:
    """Reload on the next check after file metadata changes; retain last good data.

    Missing/malformed initial policy raises ValueError. A broken live replacement
    produces one metadata-only warning per file version and keeps the good list.
    Disabled filters neither read the file nor inspect text. Extra JSON metadata is
    ignored so the operator can keep language, category and review notes with terms.
    """

    def __init__(self, path, enabled=True):
        self.path = os.fspath(path)
        self.enabled = enabled
        self.last_error = None
        self._patterns = ()
        self._signature = None
        self._failed_signature = None
        if enabled:
            try:
                self._signature = _signature(self.path)
                self._patterns = _read(self.path)
            except (OSError, ValueError, UnicodeError, RecursionError) as exc:
                raise ValueError("Cannot load the chat filter. Check T5L_CHAT_FILTER_PATH.") from exc

    def reload(self, force=False):
        if not self.enabled:
            return False
        try:
            signature = _signature(self.path)
        except OSError:
            signature = ("unavailable",)
        if not force and signature in (self._signature, self._failed_signature):
            return False
        try:
            patterns = _read(self.path)
        except (OSError, ValueError, UnicodeError, RecursionError):
            if signature != self._failed_signature:
                log.warning("chat filter policy reload failed; keeping last valid policy")
            self._failed_signature = signature
            self.last_error = "cannot reload chat filter policy"
            return False
        self._patterns, self._signature = patterns, signature
        self._failed_signature = None
        self.last_error = None
        return True

    def blocked(self, text):
        if not self.enabled:
            return False
        self.reload()
        normalized = _normalize(text)
        # Keep regex runs bounded even on substring entries. Very long contiguous
        # repeats still match, while each candidate scans at most 64 copies/run.
        normalized = "".join(char * min(len(list(chars)), MAX_TERM_LENGTH)
                             for char, chars in groupby(normalized))
        return any(pattern.search(normalized) is not None for pattern in self._patterns)
