#!/usr/bin/env python3
"""Find the texts the launcher and the Online tab translate, and check them against the German catalog.

    python tools/i18n_extract.py               # report: missing entries, unused entries, problems
    python tools/i18n_extract.py --skeleton    # the missing entries as lines to paste into i18n_de.py
    python tools/i18n_extract.py --keys        # every text in the source, one per line

A text is the first argument of t("...") or N_("...") (lobby/t5lobby/i18n.py). tests/test_i18n.py runs the
same checks, so a new string without a German entry fails the tests. Exit code 1 on any problem.
"""
import ast
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOBBY = os.path.join(ROOT, "lobby")
WRAP = ("t", "N_")                    # the names that translate / mark a text

# Python files whose texts are translated (the lobby server and the tools stay English).
SOURCE_GLOBS = ["launcher/*.py", "launcher/*.pyw", "lobby/t5lobby/*.py"]
NOT_SOURCES = ("i18n_de.py", "i18n_known.py")      # the catalog itself; i18n_known.py is read for its N_() marks too

HOLE = re.compile(r"\{(\w+)(?:![rsa])?(?::[^{}]*)?\}")
PCT = re.compile(r"%[a-zA-Z]")


def source_files(root=ROOT):
    out = []
    for g in SOURCE_GLOBS:
        out += glob.glob(os.path.join(root, g))
    return sorted(p for p in out if os.path.basename(p) not in ("i18n_de.py",))


def placeholders(text):
    """Names of the {placeholders} and the %-codes (strftime) of a text, as a sorted list (duplicates kept)."""
    return sorted(HOLE.findall(text)) + sorted(PCT.findall(text))


class Site:
    __slots__ = ("path", "line", "key", "kwargs", "kind")

    def __init__(self, path, line, key, kwargs, kind):
        self.path, self.line, self.key, self.kwargs, self.kind = path, line, key, kwargs, kind

    def where(self):
        return f"{os.path.relpath(self.path, ROOT)}:{self.line}"


def _parse(path):
    with open(path, encoding="utf-8") as f:
        return ast.parse(f.read(), path)


def _callee(node):
    f = node.func
    return f.id if isinstance(f, ast.Name) else None


def scan(paths=None):
    """-> (sites, problems). sites: Site(kind='t'|'N_') for every literal text; problems: strings."""
    sites, problems = [], []
    for path in paths or source_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _callee(node) not in WRAP:
                continue
            name = _callee(node)
            where = f"{os.path.relpath(path, ROOT)}:{node.lineno}"
            if not node.args:
                problems.append(f"{where}: {name}() without a text")
                continue
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                kws = None if any(k.arg is None for k in node.keywords) else sorted(k.arg for k in node.keywords)
                sites.append(Site(path, node.lineno, a.value, kws, name))
            elif isinstance(a, ast.JoinedStr):
                problems.append(f"{where}: {name}() with an f-string; use {{placeholders}} and keyword values")
            elif isinstance(a, ast.BinOp) and name == "t":
                problems.append(f"{where}: t() with a text built from pieces; write one literal (adjacent "
                                "string literals are fine)")
            # a variable (t(text)): fine, it holds a text marked with N_() somewhere
    return sites, problems


def dynamic_sites(paths=None):
    """Where t() gets something that is not a literal (a name, an attribute, a subscript)."""
    out = []
    for path in paths or source_files():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Call) and _callee(node) == "t" and node.args \
                    and not isinstance(node.args[0], (ast.Constant, ast.JoinedStr, ast.BinOp)):
                out.append(f"{os.path.relpath(path, ROOT)}:{node.lineno}")
    return out


def shadowed(paths=None):
    """Functions that call t() / N_() and also assign a local of that name: the call would fail at run time."""
    out = []
    for path in paths or source_files():
        tree = _parse(path)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            uses, locals_ = set(), set()
            args = fn.args
            for a in args.args + args.kwonlyargs + args.posonlyargs + ([args.vararg] if args.vararg else []) \
                    + ([args.kwarg] if args.kwarg else []):
                locals_.add(a.arg)
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and _callee(n) in WRAP:
                    uses.add(_callee(n))
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    locals_.add(n.id)
                if isinstance(n, ast.arg):
                    locals_.add(n.arg)
            for name in sorted(uses & locals_):
                out.append(f"{os.path.relpath(path, ROOT)}:{fn.lineno}: '{name}' is a local name in a function that "
                           "calls the translation function of the same name")
    return out


# ---------------------------------------------------------------------------- texts not wrapped

LETTERS = re.compile(r"[A-Za-zÀ-ɏ]{3,}")
KW_SINKS = {"text", "title", "message", "label", "placeholder"}
CALL_SINKS = {"status", "set_status", "chat_line", "show_bar", "showinfo", "showerror", "showwarning", "askyesno",
              "askstring", "ask_string", "ask_yes_no", "showmessage", "tell"}
# Constants that are not words for a player (file names, technical names, keys of a table).
TECHNICAL = {"Segoe UI", "Consolas", "launcher.json", "online.json"}


def _texty(node):
    """True when `node` is (or builds from) a string literal with words in it, outside t() / N_()."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and bool(LETTERS.search(node.value)) and node.value not in TECHNICAL
    if isinstance(node, ast.JoinedStr):
        return any(_texty(v) for v in node.values if isinstance(v, ast.Constant))
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return _texty(node.left) or _texty(node.right)
    if isinstance(node, ast.IfExp):
        return _texty(node.body) or _texty(node.orelse)
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_texty(e) for e in node.elts)
    if isinstance(node, ast.Call) and _callee(node) in WRAP:
        return False
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("join", "format"):
        return _texty(node.func.value) or any(_texty(a) for a in node.args)
    return False


def unwrapped(paths=None, skip=()):
    """Places that hand a literal English text to something a player reads without t(): widget text= / title=
    arguments, status lines, dialogs, bars. A heuristic for catching forgotten texts, not a proof."""
    out = []
    for path in paths or source_files():
        if os.path.basename(path) in skip:
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            rel = f"{os.path.relpath(path, ROOT)}:{node.lineno}"
            for k in node.keywords:
                if k.arg in KW_SINKS and _texty(k.value):
                    out.append(f"{rel}: {k.arg}= {ast.unparse(k.value)[:70]}")
            fn = node.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
            if fname in CALL_SINKS:
                for a in node.args:
                    if _texty(a):
                        out.append(f"{rel}: {fname}({ast.unparse(a)[:70]})")
            if fname == "set" and isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Attribute | ast.Name):
                base = fn.value.attr if isinstance(fn.value, ast.Attribute) else fn.value.id
                if re.search(r"(_var|^var|status|_info|_sum|detail|error)$", base) and node.args and _texty(node.args[0]):
                    out.append(f"{rel}: {base}.set({ast.unparse(node.args[0])[:70]})")
    return out


# ---------------------------------------------------------------------------- the catalog

def catalog():
    sys.path.insert(0, LOBBY)
    try:
        from t5lobby import i18n_de
        return dict(i18n_de.MESSAGES)
    finally:
        sys.path.remove(LOBBY)


def check(cat=None, paths=None):
    """-> dict(keys, missing, unused, mismatched, problems, shadowed). Everything empty = clean."""
    cat = catalog() if cat is None else cat
    sites, problems = scan(paths)
    keys = {}
    for s in sites:
        keys.setdefault(s.key, []).append(s)
    for key, ss in keys.items():
        ph = placeholders(key)
        for s in ss:
            if s.kwargs is not None and s.kind == "t":
                want = sorted(set(HOLE.findall(key)))
                if sorted(set(s.kwargs)) != want:
                    problems.append(f"{s.where()}: values {s.kwargs} do not fit the placeholders {want} of "
                                    f"{key[:60]!r}")
            elif s.kwargs is None and s.kind == "t":
                pass
        del ph
    missing = sorted(k for k in keys if k not in cat)
    unused = sorted(k for k in cat if k not in keys)
    mismatched = sorted(k for k in cat if k in keys and placeholders(k) != placeholders(cat[k]))
    return dict(keys=keys, missing=missing, unused=unused, mismatched=mismatched, problems=problems,
                shadowed=shadowed(paths))


def main(argv=None):
    ap_keys = "--keys" in (argv or sys.argv)
    skeleton = "--skeleton" in (argv or sys.argv)
    r = check()
    if ap_keys:
        for k in sorted(r["keys"]):
            print(k)
        return 0
    if skeleton:
        for k in r["missing"]:
            print(f"    {k!r}: {k!r},")
        return 1 if r["missing"] else 0
    bad = False
    for title, items in (("Missing German entries", r["missing"]), ("Catalog entries nothing uses", r["unused"]),
                         ("Placeholders differ", r["mismatched"]), ("Problems", r["problems"]),
                         ("Local names that hide t / N_", r["shadowed"]),
                         ("Possibly forgotten texts (heuristic)", unwrapped())):
        if items:
            bad = bad or title != "Possibly forgotten texts (heuristic)"
            print(f"{title} ({len(items)}):")
            for i in items:
                print("   ", i if isinstance(i, str) else repr(i))
    print(f"{len(r['keys'])} texts in the source")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
