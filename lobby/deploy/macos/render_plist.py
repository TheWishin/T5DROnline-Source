"""Fill in the LaunchAgent template for the lobby host (used by install.sh; any Python 3.8+).

    python3 render_plist.py --template org.t5dronline.lobby-host.plist --python /path/to/python3 \
        --app "$HOME/Library/Application Support/T5DR Online/lobby-app" \
        --data "$HOME/Library/Application Support/T5DR Online/lobby-host" \
        [--no-caffeinate] [--arg --map-ports ...] --out ~/Library/LaunchAgents/org.t5dronline.lobby-host.plist

The template is a real property list with @PYTHON@, @APP@ and @DATA@ in its strings. They are
replaced inside the parsed list (so a path with a space, & or < needs no escaping), the result is
written with plistlib and read back once, and any placeholder left over is an error.
"""
import argparse
import plistlib
import re
import sys

PLACEHOLDER_RE = re.compile(r"@[A-Z][A-Z_]+@")      # any @NAME@ left after filling in is a mistake
CAFFEINATE = ["/usr/bin/caffeinate", "-s"]


def _subst(value, mapping):
    if isinstance(value, str):
        for key, val in mapping.items():
            value = value.replace(key, val)
        return value
    if isinstance(value, list):
        return [_subst(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, mapping) for k, v in value.items()}
    return value


def _leftovers(value):
    if isinstance(value, str):
        return PLACEHOLDER_RE.findall(value)
    if isinstance(value, list):
        return [x for v in value for x in _leftovers(v)]
    if isinstance(value, dict):
        return [x for v in value.values() for x in _leftovers(v)]
    return []


def render(template_bytes, python, app, data, caffeinate=True, extra_args=()):
    """Template bytes -> the finished property list (bytes, XML format)."""
    plist = plistlib.loads(template_bytes)
    plist = _subst(plist, {"@PYTHON@": python, "@APP@": app, "@DATA@": data})
    args = list(plist["ProgramArguments"])
    if not caffeinate and args[:2] == CAFFEINATE:
        args = args[2:]
    plist["ProgramArguments"] = args + [str(a) for a in extra_args]
    left = _leftovers(plist)
    if left:
        raise ValueError(f"placeholders left in the template: {sorted(set(left))}")
    out = plistlib.dumps(plist, fmt=plistlib.FMT_XML)
    plistlib.loads(out)         # round trip: what we write is a valid property list
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--template", required=True)
    ap.add_argument("--python", required=True, help="absolute path of the Python 3.10+ that runs the host")
    ap.add_argument("--app", required=True, help="folder with the copied lobby code (contains run.py)")
    ap.add_argument("--data", required=True, help="data folder (database, certificate, logs, backups)")
    ap.add_argument("--no-caffeinate", action="store_true", help="do not wrap the job in caffeinate -s")
    ap.add_argument("--arg", action="append", default=[], help="extra argument for `run.py host` (repeatable)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.template, "rb") as f:
        text = render(f.read(), a.python, a.app, a.data, not a.no_caffeinate, a.arg)
    with open(a.out, "wb") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
