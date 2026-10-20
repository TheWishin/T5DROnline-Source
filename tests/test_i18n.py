"""The texts of the launcher and the Online tab in every language (lobby/t5lobby/i18n.py and its catalogs:
German i18n_de.py, Spanish i18n_es.py, Korean i18n_ko.py, Japanese i18n_ja.py, Brazilian Portuguese i18n_pt_br.py,
French i18n_fr.py).

* every text in the source (t("..."), N_("...")) has an entry in every catalog, and no entry is unused;
* every translation keeps the English text's {placeholders}; t() is called with values that fit;
* no function that translates also has a local variable called t or N_ (it would fail at run time);
* no literal English text goes to a widget, a status line or a dialog without t();
* the messages the lobby server, the lobby client, the build tool and the prerequisite check write in English are
  known to translate_message() (so a new server message without a German entry fails here);
* Auto picks the Windows language when the launcher has it, else English; the Settings box lists every language
  in its own name; Korean and Japanese get a font with their glyphs;
* the launcher and the Online tab render in every language at 100 %, 133 % and 150 % display scaling with
  withdrawn windows: no text missing from the catalog, no English left, nothing cut off (tests/i18n_layout.py);
* the lag sentences built from a lag_check event say what the server's own English sentences say.
"""
import ast
import gc
import importlib.machinery
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    sys.path.insert(0, os.path.join(ROOT, sub))
os.environ.setdefault("T5_PAD_NAV", "0")        # no controller thread in the Online tab
os.environ.setdefault("T5_FW_CHECK", "0")       # the Online tab's firewall hint never reads this PC's firewall

import core  # noqa: E402,F401  (imported now: it puts tools/ on the path, and other test modules import run late)
import i18n_extract as x   # noqa: E402
from t5lobby import i18n, i18n_de, i18n_known, lag   # noqa: E402

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog
    from t5lobby import dialogs
except ImportError:      # pragma: no cover
    tk = None

# Everything that could put a box in front of the person at this PC: the system's message boxes and file pickers,
# tkinter.simpledialog and the launcher's own dialogs (t5lobby/dialogs.py). A test that reaches one fails.
DIALOG_FUNCTIONS = [] if tk is None else [
    (messagebox, n) for n in ("showinfo", "showwarning", "showerror", "askyesno", "askyesnocancel", "askokcancel",
                              "askretrycancel", "askquestion")] + [
    (filedialog, n) for n in ("askopenfilename", "askopenfilenames", "asksaveasfilename", "askdirectory")] + [
    (simpledialog, n) for n in ("askstring", "askinteger", "askfloat")] + [
    (dialogs, n) for n in ("ask_yes_no", "ask_yes_no_cancel", "show_info", "show_error", "ask_string")]
REAL_DIALOGS = {n: getattr(dialogs, n) for _m, n in DIALOG_FUNCTIONS if _m is dialogs} if tk is not None else {}

# Server messages written for programmers (a client of this launcher never sends the request that causes them):
# they are not translated and show in English.
DEV_ONLY = {
    "login timeout", "idle timeout", "malformed message", "line too long", "hello first", "log in first",
    "unknown message X", "bad field: X", "mode is quick or ranked", "winner is 0 (P1), 1 (P2) or null (draw)",
    "score is [P1 rounds, P2 rounds]", "chars is [P1 fighter, P2 fighter]", "costumes is [P1 button, P2 button]",
    "fps is a number", "fps out of range",
    "unknown character X", "kind is casual or room",
    "mode is guest, account, register, session or resume",
}


def python_sample(node):
    """A string with a literal text of an AST node (str, f-string, a + b); every {expression} becomes 'X'. None if
    the node is something else (a variable, a conditional)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "X" for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = python_sample(node.left), python_sample(node.right)
        return a + b if a is not None and b is not None else None
    return None


def calls_in(path, names, arg_index, keyword=None):
    """[(line, sample)] for the argument `arg_index` (or dict key `keyword`) of calls to functions in `names`."""
    out = []
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f_ = n.func
            name = f_.id if isinstance(f_, ast.Name) else f_.attr if isinstance(f_, ast.Attribute) else None
            if name in names and len(n.args) > arg_index:
                out.append((n.lineno, python_sample(n.args[arg_index]), ast.unparse(n.args[arg_index])))
        if keyword and isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == keyword:
                    out.append((n.lineno, python_sample(v), ast.unparse(v)))
    return out


class Base(unittest.TestCase):
    """The launcher's modules put lobby/ in front of sys.path when they are loaded (lobby/run.py then hides
    tools/smoke/run.py from another test module): each test gives the path back as it found it."""

    def setUp(self):
        saved = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved))
        # Last of all (cleanups run in reverse): what a test's windows left behind is freed here, on the main
        # thread. Left to the garbage collector it can be freed on any thread that happens to trigger a collection --
        # a subprocess pipe reader of a later test -- and Tcl aborts the interpreter ("Tcl_AsyncDelete: async handler
        # deleted by the wrong thread"; seen in test_lift_spu_jobs once the launcher had its Replays tab).
        import gc
        self.addCleanup(gc.collect)
        # Nothing a test does may reach the person at this PC: no box, no file picker, and the launcher's log is a
        # temporary file, not launcher.log in the program folder.
        self.log_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.log_dir, True)
        self.launcher_log = os.path.join(self.log_dir, "launcher.log")
        patches = [mock.patch.object(core, "LAUNCHER_LOG", self.launcher_log)]
        for module, name in DIALOG_FUNCTIONS:
            def refuse(*_a, _n=f"{module.__name__}.{name}", **_k):
                raise AssertionError(f"{_n} was called: a test must not open a dialog")
            patches.append(mock.patch.object(module, name, refuse))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def launcher_log_text(self):
        try:
            with open(self.launcher_log, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""


class German(Base):
    """Context: the texts in German for the test, English again afterwards."""

    def setUp(self):
        super().setUp()
        i18n.set_language("de")
        i18n.clear_missing()

    def tearDown(self):
        i18n.set_language("en")


class CatalogTests(Base):
    @classmethod
    def setUpClass(cls):
        cls.r = x.check()

    def test_every_text_has_a_german_entry(self):
        self.assertEqual(self.r["missing"], [], "texts without a German entry: python tools/i18n_extract.py --skeleton")

    def test_every_entry_is_used(self):
        self.assertEqual(self.r["unused"], [], "catalog entries no t() / N_() call uses")

    def test_placeholders_match(self):
        self.assertEqual(self.r["mismatched"], [], "the German text must have the English text's {placeholders}")

    def test_texts_are_literals_and_values_fit(self):
        self.assertEqual(self.r["problems"], [])

    def test_no_function_hides_t(self):
        self.assertEqual(self.r["shadowed"], [])

    def test_no_forgotten_text(self):
        self.assertEqual(x.unwrapped(), [], "English text for a widget / status / dialog that skips t()")

    def test_german_formats_with_its_placeholders(self):
        for en, de in i18n_de.MESSAGES.items():
            values = {name: "X" for name in x.HOLE.findall(en)}
            try:
                de.format(**values)
            except (KeyError, IndexError, ValueError) as e:
                self.fail(f"{en[:50]!r}: the German text does not format: {e!r}")

    def test_sentences_are_translated(self):
        # a catalog still holding the English text of a sentence is an entry nobody translated
        same = [en for en, de in i18n_de.MESSAGES.items()
                if en == de and len(re.findall(r"[A-Za-z]{3,}", en)) >= 4 and "{" not in en[:1]]
        self.assertEqual(same, [])

    def test_no_trailing_or_doubled_space_added(self):
        for en, de in i18n_de.MESSAGES.items():
            self.assertEqual(en.endswith(" "), de.endswith(" "), en)
            self.assertEqual(en.startswith(" "), de.startswith(" "), en)
            self.assertEqual(en.count("\n"), de.count("\n"), en)

    def test_every_language_has_every_text(self):
        for lang in x.LANGS:
            with self.subTest(lang=lang):
                r = x.check(lang=lang)
                self.assertEqual(r["missing"], [], f"texts without a {lang} entry: python tools/i18n_extract.py "
                                                   f"--skeleton --lang {lang}")
                self.assertEqual(r["unused"], [], f"{lang} entries no t() / N_() call uses")
                self.assertEqual(r["mismatched"], [], f"{lang}: the translation must have the English {{placeholders}}")

    def test_every_catalog_has_the_keys_of_the_german_one(self):
        self.assertEqual(set(x.LANGS), set(i18n.CATALOGS), "tools/i18n_extract.py LANGS must name every catalog")
        for lang in x.LANGS:
            with self.subTest(lang=lang):
                self.assertEqual(list(i18n.catalog(lang)), list(i18n_de.MESSAGES), "same keys, same order")

    def test_every_translation_formats_and_keeps_its_shape(self):
        for lang in x.LANGS:
            for en, tr in i18n.catalog(lang).items():
                with self.subTest(lang=lang, text=en[:40]):
                    self.assertTrue(tr.strip(), "empty translation")
                    tr.format(**{name: "X" for name in x.HOLE.findall(en)})
                    self.assertEqual(en.endswith(" "), tr.endswith(" "))
                    self.assertEqual(en.startswith(" "), tr.startswith(" "))
                    self.assertEqual(en.count("\n"), tr.count("\n"))

    def test_every_language_translates_its_sentences(self):
        # a catalog still holding the English text of a sentence is an entry nobody translated
        for lang in x.LANGS:
            same = [en for en, tr in i18n.catalog(lang).items()
                    if en == tr and len(re.findall(r"[A-Za-z]{3,}", en)) >= 4 and "{" not in en[:1]]
            self.assertEqual(same, [], lang)

    def test_scripts_fit_the_language(self):
        hangul, kana = re.compile(r"[가-힯]"), re.compile(r"[぀-ヿ]")
        latin_only = re.compile(r"[ᄀ-ᇿ　-鿿가-힯]")
        for lang in x.LANGS:
            for en, tr in i18n.catalog(lang).items():
                if lang == "ko":
                    self.assertIsNone(kana.search(tr), tr)
                elif lang == "ja":
                    self.assertIsNone(hangul.search(tr), tr)
                else:
                    self.assertIsNone(latin_only.search(tr), (lang, tr))

    def test_the_game_and_community_terms_stay(self):
        # Quick Match, Ranked, BUILD GAME and Rematch are what players call them, in every language
        for lang in x.LANGS:
            cat = i18n.catalog(lang)
            self.assertEqual(cat["Quick match"], "Quick Match", lang)
            self.assertEqual(cat["BUILD GAME"], "BUILD GAME", lang)
            self.assertEqual(cat["Rematch"], "Rematch", lang)
            self.assertIn("Ranked", cat["Ranked match"], lang)
            self.assertIn("BUILD GAME", cat["Press BUILD GAME. It takes a few minutes; the game data stays in this "
                                            "folder."], lang)

    def test_the_dynamic_lookups_are_few(self):
        # t(variable): the variable must hold a text marked with N_(); keep the list short and known
        files = {os.path.basename(s.split(":")[0].replace("\\", "/")) for s in x.dynamic_sites()}
        self.assertLessEqual(files, {"t5dr_launcher.pyw", "tk_tab.py", "match_driver.py", "handover.py",
                                     "problem_report_ui.py", "controls_ui.py",
                                     "tk_views.py"})


class EngineTests(German):
    def test_default_language_is_english(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("Quick match"), "Quick match")
        self.assertEqual(i18n.t("Hello {name}", name="x"), "Hello x")

    def test_german(self):
        self.assertEqual(i18n.t("Quick match"), "Quick Match")
        self.assertEqual(i18n.t("Log in"), "Anmelden")
        self.assertEqual(i18n.t("Connecting to {server}...", server="s:1"), "Verbinde mit s:1...")

    def test_unknown_text_is_english_and_remembered(self):
        self.assertEqual(i18n.t("A text nobody translated {n}", n=3), "A text nobody translated 3")
        self.assertIn("A text nobody translated {n}", i18n.missing())

    def test_a_value_can_be_called_text(self):
        self.assertEqual(i18n.t("Lag check: {text}", text="abc"), "Lag-Check: abc")

    def test_texts_without_words_need_no_entry(self):
        self.assertEqual(i18n.t("0"), "0")
        self.assertEqual(i18n.t(""), "")
        self.assertEqual(i18n.missing(), [])

    def test_a_broken_translation_shows_english(self):
        saved = dict(i18n._cat)
        try:
            i18n._cat["Hello {name}"] = "Hallo {nam}"
            self.assertEqual(i18n.t("Hello {name}", name="Bob"), "Hello Bob")
        finally:
            i18n._cat.clear()
            i18n._cat.update(saved)

    def test_choices(self):
        os.environ["T5_LANG"] = "de"
        try:
            self.assertEqual(i18n.resolve("auto"), "de")
            self.assertEqual(i18n.resolve("en"), "en")
            self.assertEqual(i18n.resolve("de"), "de")
            self.assertEqual(i18n.resolve("nonsense"), "de")        # unknown counts as auto
            self.assertEqual(i18n.resolve(None), "de")
            os.environ["T5_LANG"] = "en"
            self.assertEqual(i18n.resolve("auto"), "en")
            self.assertEqual(i18n.resolve("de"), "de")
        finally:
            os.environ.pop("T5_LANG", None)

    def test_init_sets_the_language(self):
        self.assertEqual(i18n.init("en"), "en")
        self.assertEqual(i18n.language(), "en")
        self.assertEqual(i18n.init("de"), "de")
        self.assertEqual(i18n.language(), "de")

    def test_numbers_and_dates(self):
        self.assertEqual(i18n.num(2.34, 1), "2,3")
        ts = time.mktime((2026, 10, 18, 21, 5, 0, 0, 0, -1))
        self.assertEqual(i18n.stamp(ts), "18.10. 21:05")
        i18n.set_language("en")
        self.assertEqual(i18n.num(2.34, 1), "2.3")
        self.assertEqual(i18n.stamp(ts), "18 Oct 21:05")
        for lang, number, date in (("es", "2.3", "18/10 21:05"), ("pt-BR", "2,3", "18/10 21:05"),
                                   ("fr", "2,3", "18/10 21:05"), ("ko", "2.3", "10월 18일 21:05"),
                                   ("ja", "2.3", "10月18日 21:05")):
            i18n.set_language(lang)
            self.assertEqual((i18n.num(2.34, 1), i18n.stamp(ts)), (number, date), lang)

    def test_the_languages_in_their_own_names(self):
        self.assertEqual(list(i18n.LANGUAGES.values()),
                         ["English", "Deutsch", "Español", "한국어", "日本語", "Português (Brasil)", "Français"])
        self.assertEqual(i18n.CHOICES, ("auto", "en", "de", "es", "ko", "ja", "pt-BR", "fr"))
        labels = [label for key, label in core.LANGUAGE_CHOICES]
        self.assertEqual(labels[1:], list(i18n.LANGUAGES.values()))
        for key, label in core.LANGUAGE_CHOICES[1:]:
            self.assertNotIn(label, i18n_de.MESSAGES, "a language's own name is not translated")

    def test_codes_in_any_spelling(self):
        for given, lang in (("pt-BR", "pt-BR"), ("pt-br", "pt-BR"), ("PT_BR", "pt-BR"), ("pt", "pt-BR"),
                            ("pt_PT.UTF-8", "pt-BR"), ("es-MX", "es"), ("es_AR", "es"), ("fr-CA", "fr"), ("ko_KR", "ko"),
                            ("ja-JP", "ja"), ("de-AT", "de"), ("EN", "en"), ("zh-CN", None), ("", None), (None, None)):
            self.assertEqual(i18n.canonical(given), lang, given)
        with mock.patch.dict(os.environ, {"T5_LANG": "en"}):
            for lang in i18n.LANGUAGES:
                self.assertEqual(i18n.resolve(lang), lang)
                self.assertEqual(i18n.resolve(lang.lower()), lang)
            self.assertEqual(i18n.resolve("auto"), "en")
            self.assertEqual(i18n.resolve("klingon"), "en")        # unknown counts as auto
        with mock.patch.dict(os.environ, {"T5_LANG": "pt-br"}):
            self.assertEqual(i18n.resolve("auto"), "pt-BR")

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_auto_follows_the_windows_ui_language(self):
        import ctypes
        cases = {0x0407: "de", 0x0807: "de", 0x0C0A: "es", 0x080A: "es", 0x2C0A: "es", 0x0412: "ko", 0x0411: "ja",
                 0x0416: "pt-BR", 0x0816: "pt-BR", 0x040C: "fr", 0x0C0C: "fr", 0x0409: "en", 0x0809: "en",
                 0x0410: "en", 0x0804: "en", 0x0419: "en"}
        env = {k: v for k, v in os.environ.items() if k != "T5_LANG"}
        with mock.patch.dict(os.environ, env, clear=True):
            for langid, lang in cases.items():
                with mock.patch.object(ctypes.windll.kernel32, "GetUserDefaultUILanguage", return_value=langid):
                    self.assertEqual(i18n.system_language(), lang, hex(langid))
                    self.assertEqual(i18n.resolve("auto"), lang)

    def test_every_language_switches_on(self):
        for lang in i18n.LANGUAGES:
            self.assertEqual(i18n.set_language(lang), lang)
            self.assertEqual(i18n.language(), lang)
            if lang != "en":
                self.assertNotEqual(i18n.t("Log in"), "Log in", lang)
                self.assertEqual(i18n.t("Connecting to {server}...", server="s:1").count("s:1"), 1)
        i18n.set_language("en")
        self.assertEqual(i18n.t("Log in"), "Log in")

    def test_korean_and_japanese_get_their_fonts(self):
        installed = {"Segoe UI", "Malgun Gothic", "Yu Gothic UI", "Meiryo", "Bahnschrift"}
        self.assertEqual(i18n.font_of("ko", installed), "Malgun Gothic")
        self.assertEqual(i18n.font_of("ja", installed), "Yu Gothic UI")
        self.assertEqual(i18n.font_of("ja", {"Meiryo"}), "Meiryo")
        self.assertIsNone(i18n.font_of("ja", {"Segoe UI"}))          # (none installed: Tk's own fallback)
        for lang in ("en", "de", "es", "pt-BR", "fr", "auto"):
            self.assertIsNone(i18n.font_of(lang, installed), lang)
        i18n.set_language("ko")
        self.assertEqual(i18n.ui_family("Segoe UI", installed), "Malgun Gothic")
        i18n.set_language("es")
        self.assertEqual(i18n.ui_family("Segoe UI", installed), "Segoe UI")


class MessageCoverageTests(German):
    """Messages written in English elsewhere must be known (or listed as for programmers)."""

    def covered(self, sample):
        return i18n.translate_message(sample) != sample

    def check_all(self, found):
        missing = []
        for where, sample, source in found:
            if sample is None:
                continue
            if sample in DEV_ONLY or any(sample.startswith(d) for d in DEV_ONLY if d.endswith("X")):
                continue
            if not self.covered(sample):
                missing.append(f"{where}: {source[:110]}")
        self.assertEqual(missing, [], "known messages are listed in lobby/t5lobby/i18n_known.py")

    def test_server_messages(self):
        path = os.path.join(ROOT, "lobby", "t5lobby", "server", "lobby.py")
        found = [(f"lobby.py:{ln}", s, src) for ln, s, src in calls_in(path, {"LobbyError"}, 1)]
        found += [(f"lobby.py:{ln}", s, src) for ln, s, src in calls_in(path, {"kick"}, 1)]
        found += [(f"lobby.py:{ln}", s, src) for ln, s, src in calls_in(path, set(), 0, keyword="msg")]
        found = [f for f in found if not (f[1] is None)]
        self.assertGreater(len(found), 80)
        # (the "msg" of a reply that repeats a LobbyError's own msg is a variable: skipped above)
        self.check_all([(w, s, src) for w, s, src in found if s and "banned" not in s])

    def test_the_ban_messages(self):
        for text in ("this account is banned for good", "this account is banned for good: cheating",
                     "this account is banned until 2026-10-20 12:00 UTC",
                     "this account is banned until 2026-10-20 12:00 UTC: spam"):
            self.assertTrue(self.covered(text), text)
        self.assertEqual(i18n.translate_message("this account is banned until 2026-10-20 12:00 UTC: spam"),
                         "Dieses Konto ist bis 2026-10-20 12:00 UTC gesperrt: spam")

    def test_client_messages(self):
        path = os.path.join(ROOT, "lobby", "t5lobby", "client.py")
        found = [(f"client.py:{ln}", s, src) for ln, s, src in calls_in(path, {"LobbyError"}, 1)]
        found += [(f"client.py:{ln}", s, src) for ln, s, src in calls_in(path, set(), 0, keyword="msg")]
        self.assertGreater(len(found), 5)
        samples = [(w, s, src) for w, s, src in found if s and not s.startswith("X")]
        self.check_all(samples)
        for reason in ("connection closed", "message too long", "closed"):      # the reasons a connection ended
            self.assertTrue(self.covered(reason), reason)

    def test_build_tool_messages(self):
        path = os.path.join(ROOT, "tools", "build_game.py")
        found = [(f"build_game.py:{ln}", s, src) for ln, s, src in calls_in(path, {"fail"}, 0)]
        self.assertGreater(len(found), 15)
        self.check_all(found)
        # the lines main() prints after "ERROR: "
        for sample in ("step 'lift' failed: a tool exited with code 3 -- the lines above say why.", "cancelled",
                       "step 'unpack' could not read or write a file: No space left (D:\\x). The folder path is too "
                       "long for Windows: move the folder to a short path such as C:\\Games\\T5DR.",
                       "step 'unpack' could not read or write a file: No space left (D:\\x). Is the disk full, or "
                       "does another program (antivirus, OneDrive) hold the file?"):
            self.assertTrue(self.covered(sample), sample)
        src = open(path, encoding="utf-8").read()
        for hint in ("The folder path is too long for Windows: move the folder to a short path such as",
                     "Is the disk full, or does another program (antivirus, OneDrive) hold the file?"):
            self.assertIn(hint, src)

    def test_prerequisite_list(self):
        path = os.path.join(ROOT, "tools", "prereqs.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        check = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "check")
        names, details = [], []
        for n in ast.walk(check):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "add" and len(n.args) > 3:
                names.append(python_sample(n.args[1]))
                keys = {id(k) for d in ast.walk(n.args[3]) if isinstance(d, ast.Dict) for k in d.keys}
                for c in ast.walk(n.args[3]):
                    s = python_sample(c) if isinstance(c, (ast.Constant, ast.JoinedStr)) and id(c) not in keys else None
                    if s and re.search(r"[A-Za-z]{3,}", s) and s == s.strip():
                        details.append(s)
        self.assertEqual(len(names), 9)
        for s in names + details:
            self.assertTrue(self.covered(s) or s in i18n_de.MESSAGES or s in ("CMake", "Ninja"), s)
        self.assertEqual(i18n.translate_message("missing CMake and Ninja"), "fehlt: CMake and Ninja")
        self.assertEqual(i18n.translate_message("3.12.10 at C:\\Python\\python.exe"), "3.12.10 in C:\\Python\\python.exe")

    def test_updater_messages(self):
        path = os.path.join(ROOT, "launcher", "updater.py")
        found = [(f"updater.py:{ln}", s, src) for ln, s, src in calls_in(path, {"UpdateError", "SwapFailed", "Cancelled"}, 0)]
        found += [(f"updater.py:{ln}", s, src) for ln, s, src in calls_in(path, {"finish"}, 1)]
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for fn in ast.walk(tree):          # the sentences these functions return: busy_reason, check_latest, member checks
            if isinstance(fn, ast.FunctionDef) and fn.name in ("busy_reason", "check_latest", "_member_problem"):
                for r in ast.walk(fn):
                    if isinstance(r, ast.Return) and r.value is not None:
                        parts = r.value.elts if isinstance(r.value, ast.Tuple) else [r.value]
                        for part in parts:
                            found.append((f"updater.py:{r.lineno}", python_sample(part), ast.unparse(part)))
        self.assertGreater(len([f for f in found if f[1]]), 40)
        # (a sentence built from a joined list, a conditional or a variable has no sample: checked below)
        not_sentences = ("dev", "True", "False")
        self.check_all([(w, s_, src) for w, s_, src in found
                        if s_ and s_ not in not_sentences and not s_.startswith(("T5DR-Online-launcher", "X"))])
        for sample in ("Other programs from this folder are still running (python.exe, t5dr.exe): another launcher "
                       "window, the game or a lobby server. Close them, then update.",
                       "could not replace the program files: the new release contains native (the player's files)",
                       "The download contains an unexpected path (a/b: outside the folder top). Nothing was changed.",
                       "GitHub asks to wait with update checks until 21:45."):
            self.assertTrue(self.covered(sample), sample)
        self.assertEqual(
            i18n.translate_message("could not replace the program files: the new release contains native (the "
                                   "player's files)"),
            "die Programmdateien konnten nicht ersetzt werden: das neue Release enthält native (Dateien des Spielers)")

    def test_report_parts(self):
        path = os.path.join(ROOT, "launcher", "problem_report.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        titles = [python_sample(n.args[1]) for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Group"]
        self.assertGreaterEqual(len(titles), 8)
        for title in ("System information and the settings you use", "What happened (what you wrote)", "Launcher log",
                      "Game log (the newest one)", "Game log (the newest 3)", "Build log",
                      "Build log (the last build went fine)", "Online: the files of the last match",
                      "controls.ini (your button settings)", "Desync dumps (game state numbers, binary)"):
            self.assertTrue(self.covered(title), title)
        for t_ in titles:
            if t_ and "Game log" not in t_ and "Build log" not in t_:
                self.assertTrue(self.covered(t_), t_)
        reasons = {n.elts[1].value for n in ast.walk(tree) if isinstance(n, ast.Tuple) and len(n.elts) == 2
                   and isinstance(n.elts[1], ast.Constant) and isinstance(n.elts[1].value, str)
                   and n.elts[1].value in ("could not be read", "no room left in the size limit",
                                           "could not be cleaned of private data")}
        self.assertEqual(len(reasons), 3)
        for r in reasons:
            self.assertTrue(self.covered(r), r)

    def test_translations_of_known_kinds(self):
        tm = i18n.translate_message
        self.assertEqual(tm("wrong name or password"), "Name oder Passwort falsch")
        self.assertEqual(tm("you are queue"), "Das geht gerade nicht (Status: in der Suche)")
        self.assertEqual(tm("Bob lost the lobby connection; waiting 20 s for them to return"),
                         "Bob hat die Verbindung zur Lobby verloren; warte 20 s auf die Rückkehr")
        self.assertEqual(
            tm("your PC ran its last match at 41 fps; your opponent's PC ran its last match at 38 fps -- this match "
               "runs at the slower PC's speed"),
            "dein PC hat sein letztes Match mit 41 fps gespielt; der PC deines Gegners hat sein letztes Match mit "
            "38 fps gespielt -- dieses Match läuft mit der Geschwindigkeit des langsameren PCs")
        self.assertEqual(tm("Bob's PC ran its last match at 41 fps"), "der PC von Bob hat sein letztes Match mit 41 fps "
                                                                      "gespielt")

    def test_unknown_messages_stay_english(self):
        for text in ("a message from a newer server", "[WinError 10054] connection reset by peer", "", None, 5):
            self.assertEqual(i18n.translate_message(text), text)

    def test_names_inside_messages_are_not_translated(self):
        # a player called "Draw" or "idle" is still called that
        self.assertEqual(i18n.translate_message("Draw is back in the lobby"), "Draw ist zurück in der Lobby")
        self.assertEqual(i18n.translate_message("idle lost the lobby connection; waiting 5 s for them to return"),
                         "idle hat die Verbindung zur Lobby verloren; warte 5 s auf die Rückkehr")

    def test_english_stays_english(self):
        i18n.set_language("en")
        self.assertEqual(i18n.translate_message("wrong name or password"), "wrong name or password")

    def test_lobby_error_text(self):
        from t5lobby.proto import LobbyError
        from t5lobby.tk_tab import lobby_error_text
        self.assertEqual(lobby_error_text(LobbyError("auth_failed", "wrong name or password")),
                         "Lobby: Name oder Passwort falsch")
        self.assertEqual(lobby_error_text(LobbyError("x", "something new")), "Lobby: something new")
        self.assertEqual(lobby_error_text(LobbyError("timeout")), "Lobby: timeout")
        i18n.set_language("en")
        self.assertEqual(lobby_error_text(LobbyError("auth_failed", "wrong name or password")),
                         "Lobby: wrong name or password")


class EveryLanguageMessageTests(Base):
    """Server texts, lag sentences and error tips in each language."""

    def tearDown(self):
        i18n.set_language("en")

    def test_known_messages(self):
        for lang in x.LANGS:
            i18n.set_language(lang)
            tm = i18n.translate_message
            with self.subTest(lang=lang):
                self.assertNotEqual(tm("wrong name or password"), "wrong name or password")
                queue = tm("you are queue")
                self.assertIn(i18n.t("queue"), queue)
                self.assertNotIn("queue", queue)
                ban = tm("this account is banned until 2026-10-20 12:00 UTC: spam")
                self.assertIn("2026-10-20 12:00 UTC", ban)
                self.assertIn("spam", ban)
                self.assertNotIn("banned", ban)
                self.assertIn("Draw", tm("Draw is back in the lobby"))       # a name stays a name
                fps = tm("your PC ran its last match at 41 fps; your opponent's PC ran its last match at 38 fps -- "
                         "this match runs at the slower PC's speed")
                self.assertIn("41", fps)
                self.assertIn("38", fps)
                self.assertNotIn("slower", fps)
                self.assertEqual(tm("a message from a newer server"), "a message from a newer server")

    def test_lag_sentences(self):
        for lang in x.LANGS:
            i18n.set_language(lang)
            i18n.clear_missing()
            for delay, reports in LagTextTests.CASES:
                for side in (0, 1):
                    _a, ev = LagTextTests.event(None, delay, reports, side)
                    text = lag.describe_event(ev)
                    self.assertNotEqual(text, ev["text"], lang)
                    self.assertIn("37", text, lang)
            self.assertEqual(i18n.missing(), [], lang)

    def test_error_tips(self):
        """Each ERROR_HELP entry gives its tip in every language: for every catalog text that holds the entry's
        English words, the translated message gets the tip the English message gets."""
        from t5lobby import tk_views
        keys = list(i18n_de.MESSAGES)
        for words, _tip in tk_views.ERROR_HELP:
            hits = [k for k in keys if any(w in k.lower() for w in words)]
            self.assertTrue(hits, words)
            for key in hits:
                values = {name: "X" for name in x.HOLE.findall(key)}
                i18n.set_language("en")
                en = tk_views.friendly_error("Lobby: " + key.format(**values))
                tip_en = next(tip for w, tip in tk_views.ERROR_HELP if tip in en) if any(
                    tip in en for w, tip in tk_views.ERROR_HELP) else None
                for lang in x.LANGS:
                    i18n.set_language(lang)
                    msg = i18n.t("Lobby: {message}", message=i18n.t(key, **values) if values else i18n.t(key))
                    shown = tk_views.friendly_error(msg)
                    if tip_en:
                        self.assertIn(i18n.t(tip_en), shown, (lang, key[:50]))

    def test_dialog_buttons(self):
        from t5lobby import dialogs as dlg
        for lang in x.LANGS:
            i18n.set_language(lang)
            names = [i18n.t(n) for n in ("Yes", "No", "Cancel")]
            self.assertEqual(len(set(names)), 3, lang)
            self.assertNotIn("Yes", names, lang)
            self.assertTrue(callable(dlg.ask_yes_no))


class LagTextTests(German):
    CASES = (
        (2, [None, None]),
        (2, [{"frames": 600, "waited_ms": 10.0, "pc_fps": 60.0, "fps": 60.0},
             {"frames": 600, "waited_ms": 5.0, "pc_fps": 60.0, "fps": 60.0}]),
        (2, [{"frames": 600, "waited_ms": 90000.0, "pc_fps": 60.0, "fps": 60.0},
             {"frames": 600, "waited_ms": 80000.0, "pc_fps": 61.0, "fps": 60.0}]),
        (2, [{"frames": 600, "waited_ms": 90000.0, "pc_fps": 40.0, "fps": 40.0},
             {"frames": 600, "waited_ms": 80000.0, "pc_fps": 60.0, "fps": 60.0}]),
        (2, [{"frames": 600, "waited_ms": 90000.0, "pc_fps": 40.0, "fps": 40.0},
             {"frames": 600, "waited_ms": 80000.0, "pc_fps": 41.0, "fps": 40.0}]),
        (3, [{"frames": 600, "waited_ms": 90000.0, "pc_fps": None, "fps": None},
             {"frames": 600, "waited_ms": 80000.0, "pc_fps": 41.0, "fps": 40.0}]),
    )

    def event(self, delay, reports, side, ping=37.4):
        a = lag.assess(delay, reports)
        cause = a["cause"]
        if cause == "pc":
            slow = a["slow"]
            cause = "both_pcs" if len(slow) == 2 else "your_pc" if side in slow else "opponent_pc"
        return a, {"t": "lag_check", "ping_ms": round(ping, 1), "expected_frames": a["expected"],
                   "observed_frames": a["observed"], "verdict": a["verdict"], "cause": cause,
                   "yours": {"extra_frames": a["extra"][side], "pc_fps": (reports[side] or {}).get("pc_fps")},
                   "opponent": {"extra_frames": a["extra"][1 - side], "pc_fps": (reports[1 - side] or {}).get("pc_fps")},
                   "text": lag.describe(ping, a, side, reports)}

    def test_english_matches_the_servers_sentences(self):
        i18n.set_language("en")
        seen = set()
        for delay, reports in self.CASES:
            for side in (0, 1):
                a, ev = self.event(delay, reports, side)
                seen.add((a["verdict"], ev["cause"]))
                self.assertEqual(lag.describe_event(ev), ev["text"])
        self.assertGreaterEqual(len(seen), 5, seen)        # unknown, ok, more lag for each cause

    def test_german_is_complete_and_differs(self):
        for delay, reports in self.CASES:
            for side in (0, 1):
                _a, ev = self.event(delay, reports, side)
                de = lag.describe_event(ev)
                self.assertNotEqual(de, ev["text"])
                self.assertTrue(de.startswith("Bei 37 ms Ping sind etwa"), de)
        self.assertEqual(i18n.missing(), [])

    def test_an_event_without_numbers_shows_the_servers_text(self):
        self.assertEqual(lag.describe_event({"text": "Ping 12 ms ..."}), "Ping 12 ms ...")
        self.assertEqual(lag.describe_event({}), "")


class SettingsTests(Base):
    def test_language_setting_is_saved(self):
        import core
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "launcher.json")
            st = core.Settings(path)
            self.assertEqual(st["language"], "auto")
            st["language"] = "de"
            st.save()
            self.assertEqual(core.Settings(path)["language"], "de")

    def test_apply_language(self):
        import core
        try:
            self.assertEqual(core.apply_language({"language": "de"}), "de")
            self.assertEqual(i18n.language(), "de")
            self.assertEqual(core.apply_language({"language": "en"}), "en")
            self.assertEqual(i18n.language(), "en")
            os.environ["T5_LANG"] = "de"
            self.assertEqual(core.apply_language({"language": "auto"}), "de")
        finally:
            os.environ.pop("T5_LANG", None)
            i18n.set_language("en")

    def test_core_texts(self):
        import core
        with tempfile.TemporaryDirectory() as d:
            en = core.game_state(d)["text"]
            i18n.set_language("de")
            try:
                de = core.game_state(d)["text"]
                self.assertNotEqual(en, de)
                self.assertTrue(de.startswith("Das Spiel ist noch nicht gebaut"), de)
                self.assertIn("kein PS3-Paket", core.describe_pkg(os.path.join(d, "x.pkg"))[2] + "kein PS3-Paket")
                self.assertEqual(core.describe_pkg("")[2], "Kein Paket gewählt.")
                self.assertIn("Absturz", core.explain_exit(-1, ["[CRASH] x"]))
                self.assertEqual(i18n.missing(), [])
            finally:
                i18n.set_language("en")


def load_launcher():
    loader = importlib.machinery.SourceFileLoader("t5dr_launcher_under_test",
                                                   os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def assert_nothing_shown(test, root):
    """No window of this Tk application is on screen (a test window is withdrawn; a dialog or window it opens too)."""
    shown = []

    def walk(w):
        if w.winfo_class() in ("Tk", "Toplevel") and w.winfo_ismapped():
            shown.append(str(w))
        for c in w.winfo_children():
            walk(c)
    try:
        walk(root)
    except tk.TclError:
        return
    test.assertEqual(shown, [], "a window was on screen during a test")


def cancel_timers(root):
    """Drop the pending after() callbacks of a window (the launcher schedules checks for later)."""
    try:
        for after_id in root.tk.splitlist(root.tk.call("after", "info")):
            try:
                root.tk.call("after", "cancel", after_id)      # (Tcl's cancel: each widget deletes its own commands)
            except tk.TclError:
                pass
    except tk.TclError:
        pass


def all_texts(root):
    """Every text a widget shows right now: labels, buttons, headings, rows, tab names, entries' variables."""
    out = []

    def walk(w):
        for opt in ("text",):
            try:
                v = w.cget(opt)
                if v:
                    out.append(str(v))
            except tk.TclError:
                pass
        try:
            var = w.cget("textvariable")
            if var:
                out.append(str(w.getvar(str(var))))
        except tk.TclError:
            pass
        cls = w.winfo_class()
        if cls == "Treeview":
            for c in ("#0",) + tuple(w["columns"]):
                out.append(str(w.heading(c)["text"]))
            for iid in w.get_children():
                out.append(str(w.item(iid, "text")))
                out.extend(str(v) for v in w.item(iid, "values"))
        elif cls == "TNotebook":
            for i in range(len(w.tabs())):
                out.append(str(w.tab(i, "text")))
        elif cls == "TCombobox":
            out.extend(str(v) for v in w.cget("values"))
        for c in w.winfo_children():
            walk(c)
    walk(root)
    return [t.strip() for t in out if t and t.strip()]


@unittest.skipIf(tk is None, "no tkinter")
class RenderTests(Base):
    """The launcher window, built for real (not shown), in each language."""

    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp()
        self.old_env = os.environ.get("T5_ONLINE_DIR")
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "user")      # (the Online tab's settings: not the real ones)
        self.mod = load_launcher()
        import core
        self.core = core

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("T5_ONLINE_DIR", None)
        else:
            os.environ["T5_ONLINE_DIR"] = self.old_env
        i18n.set_language("en")

    def launcher(self, language):
        st = self.core.Settings(os.path.join(self.dir, "launcher.json"))
        st["language"] = language
        st["out"] = os.path.join(self.dir, "native")
        try:
            app = self.mod.App(offscreen=False, settings=st)
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        app.withdraw()
        cancel_timers(app)            # nothing may run later: not the check of the tools, not the game state thread
        # Cleanups run last-in first-out: after the window is closed and the cleanup holding it is
        # dropped, its reference cycles are collected here, on the main thread. Collected later by
        # another thread (a subprocess reader of the next module), the last reference to the Tcl
        # interpreter aborts the process ("Tcl_AsyncDelete: async handler deleted by the wrong
        # thread", seen during test_lift_spu_jobs). test_online_ui_walk does the same.
        self.addCleanup(gc.collect)
        self.addCleanup(lambda: self.close_launcher(app))
        i18n.clear_missing()
        return app

    def close_launcher(self, app):
        try:
            assert_nothing_shown(self, app)
            cancel_timers(app)
            app.online.on_close()
            app.destroy()
        except tk.TclError:
            pass                                  # (already closed by the test)

    def test_english(self):
        app = self.launcher("en")
        app.update()
        texts = all_texts(app)
        self.assertEqual(app.language, "en")
        for expect in ("Build", "Play offline", "Settings", "Play online", "BUILD GAME", "PLAY OFFLINE",
                       "Online tab", "Quick match", "Ranked match", "Log in", "Language"):
            self.assertTrue(any(expect in t for t in texts), expect)
        self.assertNotIn("Bauen", " ".join(texts))

    def test_german(self):
        app = self.launcher("de")
        app.update()
        texts = all_texts(app)
        self.assertEqual(app.language, "de")
        self.assertEqual(i18n.missing(), [], "texts shown in German that the catalog does not have")
        keys = set(i18n_de.MESSAGES)
        english_left = sorted({t for t in texts if t in keys and i18n_de.MESSAGES[t] != t})
        self.assertEqual(english_left, [], "English texts still on screen")
        for expect in ("Bauen", "Offline spielen", "Einstellungen", "Online spielen", "BUILD GAME", "OFFLINE SPIELEN",
                       "Online-Reiter", "Quick Match", "Ranked-Match", "Anmelden", "Als Gast spielen", "Sprache",
                       "Rangliste"):
            self.assertTrue(any(expect in t for t in texts), expect)
        # most of the screen changed
        i18n.set_language("en")
        en_app = self.launcher("en")
        en_app.update()
        en = all_texts(en_app)
        changed = sum(1 for a, b in zip(en, texts) if a != b)
        self.assertGreater(changed, len(en) // 2)

    def test_auto_follows_windows(self):
        os.environ["T5_LANG"] = "de"
        try:
            app = self.launcher("auto")
            self.assertEqual(app.language, "de")
        finally:
            os.environ.pop("T5_LANG", None)

    def test_switching_the_language_with_every_tab_selected(self):
        """The language applies at the next start. Walk through that: start in each language, select every tab (both
        directions), change the language box while each tab is up, close the window one way or the other. Whatever
        goes wrong inside a Tk callback is written to launcher.log as 'error in the launcher'."""
        for turn, language in enumerate(("en", "de", "en", "de", "auto")):
            with mock.patch.dict(os.environ, {"T5_LANG": "de"}):
                app = self.launcher(language)
                app.refresh_game_state = lambda: None          # (it starts a thread that talks to Tk from outside)
                app.update()
                for key in app.tab_keys + app.tab_keys[::-1]:
                    app.nb.select(app.tabs[key])
                    app.update()
                    self.assertEqual(app._selected_tab(), key)
                app.nb.select(app.tabs["settings"])
                for other in ("de", "en", "auto", language):
                    app.language_var.set(other)
                    app.language_changed()
                    app.update()
                    for key in app.tab_keys:
                        app.nb.select(app.tabs[key])
                        app.update()
                self.assertEqual(i18n.missing(), [])
                if turn % 2:
                    app.on_close()                              # the close button
                else:
                    app.destroy()                               # what --screenshots and the tests do
                self.assertNotIn("error in the launcher", self.launcher_log_text())
        self.assertNotIn("Traceback", self.launcher_log_text())

    def test_a_notebook_with_no_tab_selected_is_not_an_error(self):
        """Taking the tabs away (what destroying the window does) makes Tk send <<NotebookTabChanged>> with nothing
        selected; the handler used to fail with 'Invalid slave specification' and write 'error in the launcher'."""
        app = self.launcher("de")
        app.update()
        app.nb.select(app.tabs["online"])
        app.update()
        app.online.nb.select(2)                                 # the Online tab's own tabs: Profile
        app.update()
        for notebook in (app.online.nb, app.nb):
            for tab in notebook.tabs():
                notebook.forget(tab)
            app.update()
        self.assertIsNone(app._selected_tab())
        app._on_tab()                                           # (a direct call must not raise either)
        app.online._on_subtab()
        self.assertNotIn("error in the launcher", self.launcher_log_text())
        self.assertNotIn("Traceback", self.launcher_log_text())

    def test_tab_names_are_found_by_position(self):
        app = self.launcher("de")
        app.update()
        app.nb.select(3)                     # "Online": the handler used to compare the (English) label
        app.update()
        self.assertEqual(app.tab_keys[app.nb.index(app.nb.select())], "online")

    def test_changing_the_language_asks_for_a_restart(self):
        app = self.launcher("en")
        app.update()
        self.assertEqual(app.lang_note.get(), "")
        app.language_var.set("de")
        app.language_changed()
        self.assertIn("starts again", app.lang_note.get())
        self.assertEqual(self.core.Settings(os.path.join(self.dir, "launcher.json"))["language"], "de")
        app.language_var.set("en")
        app.language_changed()
        self.assertEqual(app.lang_note.get(), "")

    def test_vsync_box_in_german(self):
        app = self.launcher("de")
        app.update()
        texts = all_texts(app)
        for expect in ("VSync", "An (flüssig, Standard)", "Aus (geringste Verzögerung, Bild kann reißen)",
                       "Das Spiel läuft immer mit 60 fps, wie auf der PS3."):
            self.assertIn(expect, texts)
        self.assertNotIn("On (smooth, default)", texts)
        self.assertEqual(i18n.missing(), [])

    def test_vsync_choice_is_saved_and_shown_again(self):
        app = self.launcher("en")
        app.update()
        texts = all_texts(app)
        for expect in ("VSync", "On (smooth, default)", "Off (lowest latency, may tear)",
                       "The game always runs at 60 fps, like on the PS3."):
            self.assertIn(expect, texts)
        self.assertEqual(app.vsync_var.get(), "on")
        self.assertNotIn("PS3_VSYNC", app.settings.env_overrides())
        app.vsync_var.set("off")
        app.save_settings()                       # what the radio button's command does
        saved = self.core.Settings(os.path.join(self.dir, "launcher.json"))
        self.assertEqual(saved["vsync"], "off")
        self.assertEqual(saved.env_overrides()["PS3_VSYNC"], "0")
        again = self.launcher("en")               # a new launcher shows the saved choice
        self.assertEqual(again.vsync_var.get(), "off")

    def test_dynamic_launcher_texts_in_german(self):
        app = self.launcher("de")
        app.update()
        app._show_game_state(self.core.game_state(app.settings.out_dir))
        self.assertTrue(app.state_var.get().startswith("⚠ Das Spiel ist noch nicht gebaut"), app.state_var.get())
        app._show_prereqs([
            {"id": "python", "name": "Python 3.10+", "ok": True, "detail": "3.12.10 at C:\\Py\\python.exe",
             "needed_for": "", "install": None},
            {"id": "msvc", "name": "C++ build tools (MSVC x64)", "ok": False, "detail": "not found",
             "needed_for": "", "install": "Microsoft.VisualStudio.2022.BuildTools"}])
        self.assertEqual(app.tools_sum.get(), "✖ Es fehlt: C++-Build-Tools (MSVC x64)")
        self.assertEqual(app.status.get(), "1 Build-Tool(s) fehlen -- klicke auf „Fehlendes installieren…“.")
        rows = [app.tools_tv.item(i, "values") for i in app.tools_tv.get_children()]
        self.assertEqual(rows[1], ("✖ fehlt", "nicht gefunden"))
        self.assertEqual(rows[0][1], "3.12.10 in C:\\Py\\python.exe")
        app.step_state["lift"] = "running"
        app.cur_step, app.step_t0, app.sub = "lift", time.time() - 75, 0.5
        quiet = []                         # the build's quiet hint (core.lift_quiet_hint), none at first
        app.build = type("B", (), {"events": __import__("queue").Queue(),
                                   "quiet_hint": lambda _self: quiet[-1] if quiet else None})()
        app._drain_build()
        self.assertTrue(app.detail.get().startswith("Schritt 6 von 8: Code übersetzen  —  1:15"), app.detail.get())
        self.assertNotIn("\n", app.detail.get())
        quiet.append(self.core.lift_quiet_hint("lift", 200))
        app._drain_build()
        first, second = app.detail.get().split("\n")
        self.assertTrue(first.startswith("Schritt 6 von 8: Code übersetzen"), first)
        self.assertTrue(second.startswith("Der Schritt „Code übersetzen“ hat seit 3 Minuten nichts ausgegeben."), second)
        app.build.events.put(("error", "Choose your license file (.rap) first."))
        app._drain_build()
        self.assertEqual(app.error.get(), "Wähle zuerst deine Lizenzdatei (.rap).")
        app.build = None
        self.assertEqual(i18n.missing(), [])


@unittest.skipIf(tk is None, "no tkinter")
class EveryLanguageRenderTests(Base):
    """The launcher, the Online tab's screens, the Controls, report and update windows, built (withdrawn) in each
    language at 100 %, 133 % and 150 % display scaling (tests/i18n_layout.py): no text missing from the catalog, no
    English left on screen, nothing cut off (English included), no window on screen."""
    english = {}

    @classmethod
    def baseline(cls, scale):
        import i18n_layout
        if scale not in cls.english:
            cls.english[scale] = i18n_layout.Walk("en", scale).run()
        return cls.english[scale]

    def check_language(self, lang):
        import i18n_layout
        for scale in i18n_layout.SCALES:
            try:
                base = self.baseline(scale)
                walk = i18n_layout.Walk(lang, scale).run()
            except tk.TclError as e:
                self.skipTest(f"no display: {e}")
            with self.subTest(scale=scale):
                self.assertEqual(walk.shown, [], "a window was on screen")
                self.assertEqual(walk.missing, [], "texts shown that the catalog does not have")
                self.assertEqual({s: e for s, e in walk.english.items() if e}, {}, "English texts still on screen")
                self.assertGreaterEqual(len(walk.screens), 20)
                self.assertEqual(i18n_layout.compare(walk, base), [],
                                 f"cut off in {lang} at {scale} % (python tests/i18n_layout.py {lang})")

    def test_english_cuts_nothing_off(self):
        import i18n_layout
        for scale in i18n_layout.SCALES:
            with self.subTest(scale=scale):
                self.assertEqual(i18n_layout.compare(self.baseline(scale)), [],
                                 f"cut off in English at {scale} % (python tests/i18n_layout.py en)")

    def test_english_shows_no_window(self):
        base = self.baseline(100)
        self.assertEqual(base.shown, [])
        self.assertEqual(base.missing, [])

    def test_the_language_box(self):
        import i18n_layout
        walk = i18n_layout.Walk("es", 100)
        names = []

        def look(w=walk):
            from tkinter import ttk
            texts = i18n_layout.all_texts(w.app.tabs["settings"])
            names.extend(n for n in i18n.LANGUAGES.values() if n in texts)
            names.append("Auto (idioma de Windows)" in texts)
            for key in ("ko", "ja"):
                family = i18n.font_of(key)
                if family:
                    style = f"Lang{key}.TRadiobutton"
                    names.append(family in str(ttk.Style(w.app).lookup(style, "font")))
        with mock.patch.object(i18n_layout.Walk, "_online", lambda self: look()), \
                mock.patch.object(i18n_layout.Walk, "_windows", lambda self, d: None):
            walk.run()
        self.assertEqual(names[:7], list(i18n.LANGUAGES.values()))
        self.assertTrue(all(names[7:]), names)


for _lang in tuple(i18n.LANGUAGES)[1:]:
    setattr(EveryLanguageRenderTests, "test_" + _lang.lower().replace("-", "_"),
            lambda self, _l=_lang: self.check_language(_l))


class FakeClient:
    """Enough of LobbyClient for the tab to show events."""
    connected = True
    tls = False
    server_rtt = 20.0
    session = None

    class build:
        build_id = "b1"

    def __init__(self):
        self.me = {"id": "p1", "name": "Me", "guest": False, "rating": 1500, "record": [3, 2, 0], "status": "idle",
                   "main": "jin", "tier": 5, "rank": "2nd Dan", "provisional": False}
        self.events = __import__("queue").Queue()

    def active_notices(self):
        return []

    def close(self):
        pass


@unittest.skipIf(tk is None, "no tkinter")
class OnlineTabGermanTests(German):
    """Events and answers of the lobby, shown by the Online tab in German."""

    def setUp(self):
        German.setUp(self)
        self.dir = tempfile.mkdtemp()
        self.old_env = os.environ.get("T5_ONLINE_DIR")
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "user")
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        from t5lobby.tk_tab import OnlineTab

        class Settings(dict):
            path = os.path.join(self.dir, "launcher.json")
            out_dir = self.dir

        class App:
            settings = Settings(nickname="Me")
            game = None
            statuses = []

            def game_state(self):
                return {"ok": True}

            def set_status(self, text):
                self.statuses.append(text)
        self.app = App()
        self.tab = OnlineTab(self.root, self.app)
        self.tab.client = FakeClient()
        i18n.clear_missing()

    def tearDown(self):
        try:
            assert_nothing_shown(self, self.root)
            self.tab.client = None
            self.tab.on_close()
            self.root.destroy()
        finally:
            if self.old_env is None:
                os.environ.pop("T5_ONLINE_DIR", None)
            else:
                os.environ["T5_ONLINE_DIR"] = self.old_env
            German.tearDown(self)

    def status(self):
        return self.tab.status_var.get()

    def test_lists(self):
        self.tab.on_event({"t": "lobby_state", "players": [
            {"id": "p1", "name": "Me", "guest": False, "rating": 1500, "record": [3, 2, 0], "status": "idle",
             "build": "b1", "rtt": 10.0, "rank": "2nd Dan", "provisional": False, "main": "jin"},
            {"id": "p2", "name": "Gu", "guest": True, "record": [0, 1, 0], "status": "playing", "build": "other",
             "rtt": None}],
            "rooms": [{"id": "r1", "name": "R", "owner": {"name": "Me"}, "status": "open", "build": "b1",
                       "ranked": True}], "queue": {"ranked": 1, "quick": 2}})
        rows = [self.tab.tv_players.item(i, "values") for i in self.tab.tv_players.get_children()]
        self.assertEqual(rows[0][0], "Me  (du)")
        self.assertEqual(rows[0][5], "in der Lobby")
        self.assertEqual(rows[1][1], "Gast")
        self.assertEqual(rows[1][5], "andere Version")
        room = self.tab.tv_rooms.item("r1", "values")
        self.assertEqual(room[2], "offen ranked")
        self.assertIn("2nd Dan", " ".join(str(v) for v in rows[0]))
        self.assertIn("Server-Ping 20 ms", self.tab.me_var.get())
        self.assertEqual(i18n.missing(), [])

    def test_profile_selection_finds_the_name_in_german(self):
        self.tab.on_event({"t": "lobby_state", "players": [
            {"id": "p1", "name": "Me", "guest": False, "rating": 1500, "record": [3, 2, 0], "status": "idle",
             "build": "b1", "rtt": 10.0, "rank": "2nd Dan", "provisional": False}], "rooms": []})
        names = []
        self.tab.show_profile = names.append
        self.tab.tv_players.selection_set("p1")
        self.tab._profile_of_selected()
        self.assertEqual(names, ["Me"])

    def test_match_flow(self):
        t = self.tab
        t.on_event({"t": "match_found", "match": "m1", "ranked": True, "blind": True, "opponent": None,
                    "ping": {"known": True, "ms": 42.0}, "ready_timeout": 15, "ready_check": True})
        self.assertIn("Gegner gefunden -- RANKED -- Ping etwa 42 ms", t.bar_text.get())
        self.assertRegex(t.bar_text.get(), r"innerhalb von \d+ s annehmen\?")
        t.on_event({"t": "match_reveal", "opponent": {"name": "Rival", "guest": False, "rating": 1520,
                                                       "rank": "3rd Dan", "provisional": False}})
        self.assertEqual(t.bar_text.get(), "Gegner: Rival (3rd Dan, 1520) -- RANKED -- verbinde...")
        t.on_event({"t": "match_start", "ranked": True, "opponent": {"name": "Rival"}, "rtt_ms": 41.6,
                    "path": "relay", "delay": 2, "fight": {"p1": "jin", "p2": "random"}})
        self.assertEqual(t.match_var.get(), "Ranked-Match gegen Rival -- Jin vs Zufall -- Ping 42 ms (über das Relay des "
                                           "Lobby-Servers), Input-Delay 2 Frames (33 ms)")
        t.on_event({"t": "match_found", "match": "m2", "ranked": False, "origin": "rematch", "ready_check": False,
                    "opponent": {"name": "Rival", "guest": True}, "blind": False})
        self.assertEqual(t.bar_text.get(), "Gegner: Rival (Gast, Gast) -- Rematch -- verbinde...")
        for reason, expect in (("declined", "Match abgelehnt."), ("ready_timeout", "Niemand hat rechtzeitig angenommen."),
                               ("relay_full", "Das Relay des Lobby-Servers ist voll; versuche es gleich noch einmal."),
                               ("brand_new", "Match abgebrochen (brand_new).")):
            t.on_event({"t": "match_cancel", "reason": reason})
            self.assertEqual(self.status(), expect)
        self.assertEqual(i18n.missing(), [])

    def test_results(self):
        t = self.tab
        for status, reason, expect in (
                ("confirmed", None, "Ergebnis bestätigt."),
                ("void", "desync", "Kein Ergebnis (die Spiele liefen nicht mehr synchron)."),
                ("forfeit", "quit", "Match durch Aufgabe entschieden (ein Spieler ist gegangen)."),
                ("disputed", "disputed", "Du und dein Gegner habt verschiedene Ergebnisse gemeldet -- zählt nicht "
                                          "(die Meldungen passten nicht zusammen).")):
            t.on_event({"t": "match_result", "status": status, "reason": reason, "winner": None})
            self.assertEqual(self.status(), expect)
        t.on_event({"t": "match_result", "status": "confirmed", "winner": None,
                    "rating": {"after": {"r": 1612.3}, "delta": 12.0, "event": "promoted",
                               "rank_after": {"rank": "Lone Wolf"}}})
        self.assertEqual(self.status(), "Ergebnis bestätigt; Wertung 1612 (+12) -- AUFGESTIEGEN zu Lone Wolf!.")
        t.on_event({"t": "match_result", "status": "confirmed", "winner": None,
                    "rating": {"after": {"r": 1500.0}, "delta": 0.0, "rank_after": {"placement": [1, 5]}}})
        self.assertIn("Platzierung 1/5", self.status())
        self.assertEqual(i18n.missing(), [])

    def test_notices_and_connection(self):
        t = self.tab
        t.on_event({"t": "notice", "msg": "your opponent reported the result; please report yours"})
        self.assertEqual(self.status(), "Dein Gegner hat das Ergebnis gemeldet; melde bitte auch deins")
        t.on_event({"t": "notice", "msg": "an admin wrote this"})
        self.assertEqual(self.status(), "an admin wrote this")
        t.on_event({"t": "kicked", "reason": "logged in from another place"})
        self.assertEqual(self.status(), "Aus der Lobby entfernt: an einem anderen Ort angemeldet")
        t.on_event({"t": "nat_status", "text": "Measuring the connection..."})
        t.on_event({"t": "reconnecting", "reason": "x"})
        self.assertIn("verbinde neu", self.status())
        t.on_event({"t": "challenge_update", "challenge": "c", "state": "declined"})
        self.assertEqual(self.status(), "Herausforderung abgelehnt.")
        t.on_event({"t": "disconnected", "reason": "connection closed"})
        self.assertEqual(self.status(), "Verbindung zur Lobby verloren: Verbindung geschlossen")
        self.assertEqual(t.me_var.get(), "Nicht verbunden.")
        self.assertEqual(i18n.missing(), [])

    def test_lag_check_and_set(self):
        t = self.tab
        t.on_event({"t": "lag_check", "ping_ms": 37.4, "expected_frames": 2, "observed_frames": None,
                    "verdict": "unknown", "cause": None, "text": "Ping 37 ms ..."})
        self.assertTrue(t.match_var.get().startswith("Lag-Check: Bei 37 ms Ping sind etwa 2 Frames"), t.match_var.get())
        t.on_event({"t": "set_end", "reason": "lag", "by": "opponent"})
        self.assertEqual(self.status(), "Dein Gegner ist nach dem Lag-Check gegangen. Für keinen von euch gibt es eine "
                                       "Strafe.")
        t.rematch_bar = ("Ergebnis", "Rival")
        t._show_rematch_bar()
        labels = [str(b.cget("text")) for b in t.bar_buttons.winfo_children()]
        self.assertEqual(labels, ["Rematch mit Rival", "Nächstes Spiel", "Verlassen", "Rival blockieren"])
        self.assertEqual(i18n.missing(), [])

    def test_driver_notes(self):
        t = self.tab
        t.on_driver({"kind": "ask_result", "opponent": "Rival"})
        self.assertEqual(t.bar_text.get(), "Das Spiel wurde geschlossen. Wie ist das Match gegen Rival ausgegangen?")
        labels = [str(b.cget("text")) for b in t.bar_buttons.winfo_children()]
        self.assertEqual(labels, ["Ich habe gewonnen", "Ich habe verloren", "Unentschieden", "Ich habe aufgegeben"])
        t.on_driver({"kind": "rematch_offer", "opponent": "Rival"})
        self.assertEqual(t.bar_text.get(), "Rival will ein Rematch")
        self.assertEqual(i18n.missing(), [])

    def test_buttons_and_headings_are_german(self):
        texts = all_texts(self.root)
        for expect in ("Online spielen", "Anmelden", "Konto erstellen", "Als Gast spielen", "Ranked-Match",
                       "Quick Match", "Suche beenden", "Raum erstellen", "Herausfordern", "Rangliste", "Profil",
                       "SPIELER", "BILANZ", "FÜR FREUNDE HOSTEN", "Controller hier benutzen"):
            self.assertIn(expect, texts)
        self.assertEqual(i18n.missing(), [])
        keys = set(i18n_de.MESSAGES)
        self.assertEqual(sorted({t for t in texts if t in keys and i18n_de.MESSAGES[t] != t}), [])

    def shown(self):
        """The texts on screen now, and the English ones among them (a text of the catalog, not translated)."""
        self.root.update()
        texts = all_texts(self.root)
        keys = set(i18n_de.MESSAGES)
        english = sorted({t for t in texts if t in keys and i18n_de.MESSAGES[t] != t})
        return texts, english

    def test_every_screen_of_the_view(self):
        """The cards of the Online tab (tk_views.py), one after the other: no English left, no text missing."""
        t = self.tab
        t._set_account_view(True)
        t.on_event({"t": "lobby_state", "players": [], "rooms": [], "queue": {"ranked": 3, "quick": 1}})
        texts, english = self.shown()
        for expect in ("Gast", "Gewertet: nah an deinem Rang, gute Verbindung", "SPIELER ONLINE", "RÄUME"):
            self.assertTrue(any(expect in x for x in texts), expect)
        self.assertEqual(english, [])
        t.client.me["status"] = "queue"
        t.cfg["last_search"] = "ranked"
        t.strict_var.set(1)
        t.view.refresh()
        texts, english = self.shown()
        self.assertTrue(any(x.startswith("Ähnlicher Rang und gute Verbindung, streng") for x in texts), texts)
        self.assertIn("3 in der Ranked-Suche  ·  1 bei Quick Match", texts)
        self.assertEqual(english, [])
        t.client.me["status"] = "idle"
        t.on_event({"t": "match_found", "match": "m1", "ranked": True, "blind": True, "opponent": None,
                    "ping": {"known": True, "ms": 42.0}, "ready_timeout": 15, "ready_check": True})
        texts, english = self.shown()
        for expect in ("GEGNER GEFUNDEN", "Gegner verborgen", "Gute Verbindung",
                       "Name und Seite werden gezeigt, sobald ihr beide annehmt.", "(geschätzt, bevor ihr verbunden seid)"):
            self.assertTrue(any(expect in x for x in texts), expect)
        self.assertEqual(english, [])
        t.ready_sent = True
        t.view._bar_sig = None
        t.view.refresh()
        texts, english = self.shown()
        self.assertIn("Angenommen. Warte auf deinen Gegner...", texts)
        t.on_event({"t": "match_reveal", "opponent": {"name": "Rival", "guest": False, "rating": 1520,
                                                       "rank": "3rd Dan", "provisional": False, "tier": 5}})
        texts, english = self.shown()
        self.assertIn("MATCH BEREIT", texts)
        self.assertIn("Verbinde die beiden Spiele...", texts)
        self.assertEqual(english, [])
        t.on_event({"t": "challenged", "challenge": "c1", "from": {"name": "Rival", "guest": False, "rating": 1500,
                                                                    "rank": "2nd Dan", "provisional": False}})
        texts, english = self.shown()
        self.assertIn("will gegen dich spielen. Nimm an, um das Match zu starten.", texts)
        self.assertIn("Annehmen", texts)
        self.assertEqual(english, [])
        t.hide_bar()
        t.on_event({"t": "match_start", "ranked": True, "opponent": {"name": "Rival", "guest": False, "rating": 1520,
                                                                      "rank": "3rd Dan", "tier": 5},
                    "rtt_ms": 41.6, "path": "relay", "delay": 2, "fight": {"p1": "jin", "p2": "random"}})
        t.driver = type("D", (), {"ticket": object(), "game_running": lambda self: True, "session_ticket": None,
                                  "close": lambda self: None, "poll": lambda self: []})()
        t.view.refresh()
        texts, english = self.shown()
        for expect in ("IM MATCH", "gegen Rival", "2 Frames  (33 ms)", "Relay (Lobby-Server)", "Dein Spiel läuft",
                       "INPUT-DELAY", "VERBINDUNG"):
            self.assertTrue(any(expect in x for x in texts), (expect, texts[-40:]))
        self.assertEqual(english, [])
        t.driver = None
        t.on_event({"t": "match_result", "status": "confirmed", "winner": None, "score": [2, 1], "ranked": True,
                    "rating": {"after": {"r": 1612.3}, "delta": 12.0, "event": "promoted",
                               "rank_after": {"rank": "Lone Wolf", "tier": 8}}})
        t.on_event({"t": "lag_check", "ping_ms": 37.4, "expected_frames": 2, "observed_frames": 4.2,
                    "verdict": "more_lag", "cause": "network", "can_leave": True, "text": "x"})
        t.view.refresh()
        texts, english = self.shown()
        for expect in ("UNENTSCHIEDEN", "Ranked-Match", "AUFGESTIEGEN", "Wertung 1612", "LAG-CHECK",
                       "RUNDEN  (P1 – P2)", "Nächstes Spiel", "Zurück zur Lobby"):
            self.assertTrue(any(expect in x for x in texts), (expect, texts[-40:]))
        self.assertEqual(english, [])
        self.assertEqual(i18n.missing(), [])

    def test_friends_page_and_invites(self):
        """The Friends page, a friend's invite in the bar and the friends' messages: German, nothing missing."""
        t = self.tab
        c = t.client
        c.has_friends = lambda: True
        c.rooms = []
        base = {"rank": "3rd Dan", "tier": 12, "provisional": False, "rating": 1600, "guest": False}
        c.friend_list = {"friends": [
            dict(base, name="Rival", status="online", activity="queue", invite="ok"),
            dict(base, name="Busy", status="in_match", activity="playing", invite="busy"),
            dict(base, name="Gone", status="offline", activity=None, invite="offline", last_seen=1792000000.0),
            dict(base, name="Old", status="online", activity="idle", invite="update")],
            "incoming": [{"name": "Neu", "time": 1.0}], "outgoing": [{"name": "Frage", "time": 2.0}], "max": 100,
            "requests_left": 20}
        t._set_account_view(True)
        t.on_event({"t": "friends"})
        t.nb.select(3)
        texts, english = self.shown()
        for expect in ("FREUNDE", "Zum Match einladen", "In den Raum einladen", "Entfernen", "FREUND HINZUFÜGEN",
                       "Anfrage senden", "ANFRAGEN", "möchte dein Freund sein", "wartet auf Antwort",
                       i18n.t("searching"), "im Match", "Freunde (1)", "3 online · 4 von 100",
                       "älterer Launcher: keine Einladungen"):
            self.assertIn(expect, texts)
        self.assertTrue(any(x.startswith("offline, zuletzt gesehen ") for x in texts), texts)
        self.assertEqual(english, [])
        t.on_event({"t": "invited", "invite": "i1", "kind": "room", "room": {"name": "Dojo"},
                    "from": dict(base, name="Rival")})
        texts, english = self.shown()
        self.assertEqual(t.bar_text.get(), "Rival (3rd Dan) lädt dich in den Raum „Dojo“ ein")
        for expect in ("EINLADUNG VON EINEM FREUND", "Annehmen", "Ablehnen",
                       "lädt dich in den Raum „Dojo“ ein. Nimm an, um beizutreten; das Match startet sofort."):
            self.assertIn(expect, texts)
        self.assertEqual(english, [])
        t.on_event({"t": "invite_update", "invite": "i1", "state": "expired", "name": "Rival"})
        self.assertEqual(self.status(), "Die Einladung von Rival ist abgelaufen.")
        t.on_event({"t": "invited", "invite": "i2", "kind": "casual", "from": dict(base, name="Rival")})
        self.assertEqual(t.bar_text.get(), "Rival (3rd Dan) lädt dich zu einem Casual-Match ein")
        t.on_event({"t": "friend_request", "name": "Neu"})
        self.assertEqual(self.status(), "Neu möchte dein Freund sein: siehe den Reiter Freunde.")
        t.on_event({"t": "friend_update", "name": "Frage", "state": "accepted"})
        self.assertEqual(self.status(), "Frage hat deine Freundschaftsanfrage angenommen.")
        t.outgoing_invite = {"invite": "i3", "name": "Rival"}
        t.on_event({"t": "invite_update", "invite": "i3", "state": "declined", "name": "Rival"})
        self.assertEqual(self.status(), "Rival hat deine Einladung abgelehnt.")
        c.me["guest"] = True
        t._fill_friends()
        self.assertTrue(t.friends_note_var.get().startswith("Freunde brauchen ein Konto"))
        self.assertEqual(i18n.translate_message("you can send 20 friend requests a day; try again tomorrow"),
                         "Du kannst 20 Freundschaftsanfragen am Tag senden; versuche es morgen wieder")
        self.assertEqual(i18n.missing(), [])

    def test_errors_get_a_tip_in_german(self):
        from t5lobby import tk_views
        self.assertEqual(tk_views.friendly_error("Lobby: Name oder Passwort falsch"),
                         "Name oder Passwort falsch. Prüfe die Schreibweise, oder nutze „Passwort vergessen...“.")
        self.assertEqual(tk_views.friendly_error("Lobby-Fehler: Ranked braucht ein Konto"),
                         "Ranked braucht ein Konto. Erstelle ein (kostenloses) Konto, um Ranked zu spielen.")
        self.assertEqual(tk_views.friendly_error("Lobby: something new"), "Something new")
        i18n.set_language("en")
        self.assertEqual(tk_views.friendly_error("Lobby: wrong name or password"),
                         "Wrong name or password. Check the spelling, or use \"Forgot password...\".")

    def test_every_error_tip_matches_its_german_words(self):
        """ERROR_HELP looks for words in the message: the English ones in the server's text, the German ones in
        its translation. Each pair has to belong to the same known message."""
        from t5lobby import tk_views
        english = [k for k in i18n_de.MESSAGES]
        for words, _tip in tk_views.ERROR_HELP:
            en_words, de_words = [words[0]], list(words[1:])
            hits = [k for k in english if en_words[0] in k.lower()]
            self.assertTrue(hits, f"no text has {en_words[0]!r}")
            for k in hits:
                de = i18n_de.MESSAGES[k].lower()
                self.assertTrue(any(w in de for w in de_words),
                                f"{en_words[0]!r} is in {k[:60]!r} but none of {de_words} is in {de[:70]!r}")


@unittest.skipIf(tk is None, "no tkinter")
class ReportAndUpdateTests(German):
    """The problem report window and the update offer (windows of launcher/problem_report_ui.py, updater.py)."""

    def setUp(self):
        German.setUp(self)
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.root.readonly = True
        self.dir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.dir, True)

    def tearDown(self):
        try:
            assert_nothing_shown(self, self.root)
            cancel_timers(self.root)
            self.root.destroy()
        finally:
            German.tearDown(self)

    def pump(self, cond, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.root.update()
            if cond():
                return True
            time.sleep(0.02)
        self.fail("timed out")

    def test_the_report_window(self):
        from test_problem_report import fake_context
        import problem_report_ui as report_ui
        ctx = fake_context(self.dir, build_exit=0)
        dlg = report_ui.ReportDialog(self.root, lambda: ctx, os.path.join(self.dir, "Desktop"), reveal=lambda p: None,
                                     issues_url="https://example.org/issues", log=lambda m: None, visible=False)
        texts = all_texts(dlg.top)
        self.assertEqual(dlg.top.title(), "Problem melden")
        for expect in ("Problem melden", "Was ist passiert? (freiwillig)", "Was in die Zip-Datei kommt",
                       "Bericht auf dem Desktop speichern", "Abbrechen"):
            self.assertIn(expect, texts)
        self.assertTrue(any(t.startswith("Launcher-Log  (") for t in texts), texts)
        self.assertTrue(any(t.startswith("Spiel-Log (das neueste)  (") or t.startswith("Spiel-Log (die neuesten ")
                            for t in texts), texts)
        self.assertTrue(any(t.startswith("Etwa ") and "gepackt" in t for t in texts), texts)
        self.assertTrue(any(t.startswith("Bevor die Zip-Datei entsteht") for t in texts))
        dlg.save()
        self.pump(lambda: dlg.result is not None or dlg.error)
        self.assertIsNone(dlg.error)
        texts = all_texts(dlg.top)
        for expect in ("Bericht gespeichert", "Ordner öffnen", "Schließen"):
            self.assertIn(expect, texts)
        self.assertTrue(any(t.startswith("Schicke diese Zip-Datei") and t.endswith("https://example.org/issues.")
                            for t in texts), texts)
        box = [w for w in dlg.top.winfo_children()[0].winfo_children() if w.winfo_class() == "Text"][0]
        self.assertIn("Aus den Textdateien entfernt:", box.get("1.0", "end"))
        self.assertEqual(i18n.missing(), [])
        dlg.close()

    def test_a_report_that_failed(self):
        from test_problem_report import fake_context
        import problem_report_ui as report_ui
        ctx = fake_context(self.dir, build_exit=0)
        dest = os.path.join(self.dir, "file")
        with open(dest, "w") as f:
            f.write("a file, not a folder")
        dlg = report_ui.ReportDialog(self.root, lambda: ctx, dest, visible=False)
        dlg.save()
        self.pump(lambda: dlg.error is not None)
        self.assertTrue(dlg.status_var.get().startswith("Der Bericht konnte nicht erstellt werden:"))
        dlg.close()

    def test_the_sizes(self):
        import problem_report_ui as report_ui
        self.assertEqual(report_ui.human(5), "5 Bytes")
        self.assertEqual(report_ui.human(2048), "2 KB")
        self.assertEqual(report_ui.human(3 * (1 << 20) + (1 << 19)), "3,5 MB")
        i18n.set_language("en")
        self.assertEqual(report_ui.human(3 * (1 << 20) + (1 << 19)), "3.5 MB")

    def test_the_update_offer(self):
        from unittest import mock
        import updater
        up = updater.Updater(self.root)
        cancel_timers(self.root)
        up.release = {"version": "9.9.9", "zip": {"size": 92_300_000}, "page": "https://github.com/x/y",
                      "notes": "- something", "published": "2026-10-20", "code_id": None}
        with mock.patch.object(updater, "busy_reason", return_value="The game is running. Close it first, then update."):
            up.offer()
        up.win.withdraw()                                  # (never on screen)
        texts = all_texts(up.win)
        self.assertEqual(up.win.title(), "Update verfügbar")
        for expect in ("T5DR Online 9.9.9 ist da", "Jetzt aktualisieren", "Später", "Release-Seite"):
            self.assertIn(expect, texts)
        self.assertTrue(any(t.startswith("Du hast ") and "Download: 92,3 MB, veröffentlicht 2026-10-20. Der Launcher lädt es"
                            in t for t in texts), texts)
        self.assertIn("Das Spiel läuft. Schließe es zuerst, dann aktualisiere.", texts)
        self.assertIn("Ändert dieses Update den Spielcode, bittet dich der Reiter Spielen, das Spiel einmal zu bauen "
                      "(etwa 2 Minuten).", texts)
        up._failed("Not enough free disk space: the update needs about 300 MB next to the folder, 12 MB are free.")
        self.assertEqual(up.err.get(), "Nicht genug freier Speicherplatz: Das Update braucht etwa 300 MB neben dem "
                                       "Ordner, frei sind 12 MB.")
        up._progress("download", 5_000_000, 92_300_000)
        self.assertEqual(up.msg.get(), "Lade herunter… 5,0 MB von 92,3 MB")
        self.assertEqual(i18n.missing(), [])
        up.win.destroy()

    def test_update_answers_in_boxes(self):
        from unittest import mock
        import updater
        up = updater.Updater(self.root)
        cancel_timers(self.root)
        with mock.patch.object(updater, "_box") as box:
            up._checked(None, "No connection to GitHub. Check the internet connection and try again.", True)
            up._checked({"version": up.local, "zip": {}}, None, True)
        self.assertEqual(box.call_args_list[0].args[:3], (
            "show_info", "Updates", "Die Suche nach Updates hat nicht geklappt.\n\nKeine Verbindung zu GitHub. Prüfe "
                                    "die Internetverbindung und versuche es noch einmal."))
        self.assertEqual(box.call_args_list[1].args[2], "Du hast die neueste Version (%s)." % up.local)
        self.assertEqual(i18n.missing(), [])


@unittest.skipIf(tk is None, "no tkinter")
class DialogTests(German):
    """t5lobby/dialogs.py: boxes with buttons in the chosen language. The window is withdrawn (never on screen) and
    the test presses the button, which is what wait_window waits for."""

    def setUp(self):
        German.setUp(self)
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.shown = []
        test = self

        class QuietToplevel(tk.Toplevel):
            press = None
            typed = None

            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                self.withdraw()

            def wait_window(self, window=None):
                texts = all_texts(self)
                test.shown.append(texts)
                entry = [w for w in self.winfo_children()[0].winfo_children() if w.winfo_class() == "TEntry"]
                if entry and QuietToplevel.typed is not None:
                    entry[0].delete(0, "end")
                    entry[0].insert(0, QuietToplevel.typed)
                for b in self.winfo_children()[1].winfo_children():
                    if str(b.cget("text")) == QuietToplevel.press:
                        b.invoke()
                        return
                test.fail(f"no button {QuietToplevel.press!r} in {texts}")
        self.Quiet = QuietToplevel
        patch = mock.patch.object(dialogs.tk, "Toplevel", QuietToplevel)
        patch.start()
        self.addCleanup(patch.stop)

    def test_buttons_follow_the_language(self):
        self.Quiet.press = "Ja"
        self.assertTrue(REAL_DIALOGS["ask_yes_no"]("Titel", "Frage?", parent=self.root))
        self.assertIn("Nein", self.shown[-1])
        self.Quiet.press = "Nein"
        self.assertFalse(REAL_DIALOGS["ask_yes_no"]("Titel", "Frage?", parent=self.root))
        i18n.set_language("en")
        self.Quiet.press = "Yes"
        self.assertTrue(REAL_DIALOGS["ask_yes_no"]("Title", "Question?", parent=self.root))
        self.assertIn("No", self.shown[-1])

    def test_yes_no_cancel(self):
        for label, expect in (("Ja", True), ("Nein", False), ("Abbrechen", None)):
            self.Quiet.press = label
            self.assertIs(REAL_DIALOGS["ask_yes_no_cancel"]("T", "Speichern?", parent=self.root), expect)

    def test_info_and_error_have_one_button(self):
        self.Quiet.press = "OK"
        REAL_DIALOGS["show_info"]("T", "Hallo", parent=self.root)
        REAL_DIALOGS["show_error"]("T", "Fehler", parent=self.root)
        self.assertIn("OK", self.shown[-1])
        self.assertNotIn("Abbrechen", self.shown[-1])

    def test_ask_string(self):
        self.Quiet.press, self.Quiet.typed = "OK", "geheim"
        self.assertEqual(REAL_DIALOGS["ask_string"]("T", "Passwort:", parent=self.root, show="*"), "geheim")
        self.assertIn("Abbrechen", self.shown[-1])
        self.Quiet.press = "Abbrechen"
        self.assertIsNone(REAL_DIALOGS["ask_string"]("T", "Passwort:", parent=self.root))
        self.Quiet.press, self.Quiet.typed = "OK", None
        self.assertEqual(REAL_DIALOGS["ask_string"]("T", "Name:", parent=self.root, initialvalue="Bob"), "Bob")
        self.assertEqual(i18n.missing(), [])

    def test_the_tests_cannot_open_dialogs(self):
        with self.assertRaises(AssertionError):
            dialogs.ask_yes_no("T", "Q")
        with self.assertRaises(AssertionError):
            messagebox.showinfo("T", "Q")
        with self.assertRaises(AssertionError):
            filedialog.askopenfilename()


class DriverTextTests(German):
    def test_reasons_and_states(self):
        from t5lobby import match_driver
        for key, text in match_driver.REASON_TEXT.items():
            self.assertNotEqual(i18n.t(text), text, key)
        for key, text in match_driver.MatchDriver.STATE_TEXT.items():
            self.assertTrue(i18n.t(text), key)
        self.assertEqual(i18n.missing(), [])

    def test_ticket_summary(self):
        from t5lobby.handover import MatchTicket
        ticket = MatchTicket(match_id="m", role="host", slot=0, local_port=1, peer=("1.2.3.4", 5), path="relay",
                             rtt_ms=40.2, jitter_ms=1.0, delay=2, rounds=3, ranked=False,
                             opponent={"name": "Rival"}, build="b", seed=1)
        self.assertEqual(ticket.summary(), "Rival -- über den Lobby-Server, Ping 40 ms, Input-Delay 2")

    def test_rank_label(self):
        from t5lobby import ranks
        self.assertEqual(ranks.label({"rank": "Beginner", "placement": [2, 5]}), "Beginner (Platzierung 2/5)")


if __name__ == "__main__":
    unittest.main()
