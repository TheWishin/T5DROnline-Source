#!/bin/bash
# Host a T5DR lobby on a Mac at home: starts at login, restarts if it stops, keeps the Mac awake.
# User level (a launchd LaunchAgent): no sudo, nothing outside your home folder is touched.
# NOT TESTED ON A REAL MAC -- see docs/HOSTING.md, "macOS: host on a Mac at home".
#
#   lobby/deploy/macos/install.sh [options] [-- extra arguments for `run.py host`]
#
# Options
#   --python PATH     the Python 3.10+ to run the server with (default: python.org's, Homebrew's,
#                     or python3 from PATH -- never the old /usr/bin/python3 that comes with macOS)
#   --data DIR        data folder (default: the host's own default, see docs/HOSTING.md)
#   --no-caffeinate   do not wrap the server in `caffeinate -s` (the Mac may then go to sleep)
#   --no-start        install the job but do not start it now (it starts at the next login)
#   --dry-run         print what would be done, change nothing
# Example: install.sh -- --map-ports --guests-only
#
# What it does: copies the lobby code to ~/Library/Application Support/T5DR Online/lobby-app (so the
# job does not depend on the checkout, and macOS does not ask for access to Documents or Desktop),
# writes ~/Library/LaunchAgents/org.t5dronline.lobby-host.plist from the template next to this
# script (render_plist.py) and loads it. Run it again to update the code or change options.
# Remove it with uninstall.sh. The data folder (database, certificate, backups) is never deleted.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/../.." && pwd)"                       # the lobby/ folder of the checkout
LABEL=org.t5dronline.lobby-host
TEMPLATE="$HERE/$LABEL.plist"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP="$HOME/Library/Application Support/T5DR Online/lobby-app"
PY="" DATA="" CAFFEINATE=1 START=1 DRY=0
EXTRA=()

die() { echo "install.sh: $*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }
run() {   # run a command, or show it in a dry run
    if [ "$DRY" = 1 ]; then printf '+'; printf ' %q' "$@"; printf '\n'; else "$@"; fi
}

while [ $# -gt 0 ]; do
    case "$1" in
        --python) PY="${2:?--python needs a path}"; shift ;;
        --data) DATA="${2:?--data needs a folder}"; shift ;;
        --no-caffeinate) CAFFEINATE=0 ;;
        --no-start) START=0 ;;
        --dry-run) DRY=1 ;;
        -h|--help) sed -n '2,/^set -eu/p' "$0" | sed '$d'; exit 0 ;;
        --) shift; while [ $# -gt 0 ]; do EXTRA+=("$1"); shift; done; break ;;
        *) die "unknown option $1 (see --help)" ;;
    esac
    shift
done

# ---------------------------------------------------------------------------- checks
step "checks"
if [ "$(uname -s)" != Darwin ]; then
    [ "$DRY" = 1 ] || die "this installer is for macOS (launchd). On Linux use deploy/linux/install.sh."
    echo "(not macOS: a dry run only prints the steps)"
fi
[ -f "$SRC/t5lobby/server/lobby.py" ] || die "run me from the repository (no $SRC/t5lobby/server)"
[ -f "$TEMPLATE" ] || die "missing $TEMPLATE"

py_ok() {   # Python 3.10+ with the modules the server needs (scrypt: accounts)
    "$1" - >/dev/null 2>&1 <<'PYEOF'
import sys
assert sys.version_info >= (3, 10)
import asyncio, sqlite3, ssl, hashlib, plistlib
hashlib.scrypt(b"x", salt=b"y", n=16, r=8, p=1)
PYEOF
}
if [ -z "$PY" ]; then
    # python.org's installer first, then Homebrew, then whatever python3 is on the PATH.
    # /usr/bin/python3 is skipped: it is old, and without the developer tools it opens an install dialog.
    CANDIDATES=("${PYTHON:-}" /Library/Frameworks/Python.framework/Versions/Current/bin/python3)
    for c in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do CANDIDATES+=("$c"); done
    CANDIDATES+=(/usr/local/bin/python3 /opt/homebrew/bin/python3)
    p="$(command -v python3 2>/dev/null || true)"
    if [ -n "$p" ] && [ "$p" != /usr/bin/python3 ]; then CANDIDATES+=("$p"); fi
    for c in "${CANDIDATES[@]}"; do
        if [ -n "$c" ] && [ -x "$c" ] && py_ok "$c"; then PY="$c"; break; fi
    done
    [ -n "$PY" ] || die "no Python 3.10 or newer found. Install it from https://www.python.org/downloads/ (the python3 that comes with macOS is too old), or pass --python PATH."
else
    py_ok "$PY" || die "$PY is not Python 3.10 or newer (or lacks asyncio, sqlite3, ssl or scrypt)"
fi
echo "python: $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"

if [ -z "$DATA" ]; then
    DATA="$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); from t5lobby.server.host import default_data_dir; print(default_data_dir())' "$SRC")"
fi
echo "code:   $APP"
echo "data:   $DATA"
echo "job:    $PLIST"
if [ "$CAFFEINATE" = 1 ]; then echo "awake:  caffeinate -s (while hosting, on mains power)"; else echo "awake:  not kept awake (--no-caffeinate)"; fi

# ---------------------------------------------------------------------------- stop an older job
UIDN="$(id -u)"
unload() {
    if [ "$DRY" = 1 ]; then echo "+ launchctl bootout gui/$UIDN/$LABEL   (if loaded)"; return 0; fi
    launchctl bootout "gui/$UIDN/$LABEL" >/dev/null 2>&1 || launchctl unload "$PLIST" >/dev/null 2>&1 || true
}
step "stopping an older copy (if any)"
unload

# ---------------------------------------------------------------------------- code
step "copying the lobby code"
run rm -rf "$APP/t5lobby"
run mkdir -p "$APP/t5lobby/server" "$APP/t5lobby/data"
for f in "$SRC"/t5lobby/*.py; do run cp "$f" "$APP/t5lobby/"; done
for f in "$SRC"/t5lobby/server/*.py; do run cp "$f" "$APP/t5lobby/server/"; done
for f in "$SRC"/t5lobby/data/*.json; do run cp "$f" "$APP/t5lobby/data/"; done
run cp "$SRC/run.py" "$SRC/servers.json" "$APP/"
if [ "$DRY" = 0 ]; then
    "$PY" -c "import sys; sys.path.insert(0, sys.argv[1]); from t5lobby.server import Config, LobbyServer; LobbyServer(Config(db=':memory:')).store.close(); print('code ok')" "$APP" \
        || die "the copied code does not start"
fi
run mkdir -p "$DATA/logs" "$HOME/Library/LaunchAgents"

# ---------------------------------------------------------------------------- job
step "writing the job"
RENDER=("$PY" "$HERE/render_plist.py" --template "$TEMPLATE" --python "$PY" --app "$APP" --data "$DATA" --out "$PLIST")
if [ "$CAFFEINATE" = 0 ]; then RENDER+=(--no-caffeinate); fi
for a in ${EXTRA[@]+"${EXTRA[@]}"}; do RENDER+=("--arg=$a"); done
run "${RENDER[@]}"
run chmod 644 "$PLIST"
if [ "$DRY" = 0 ] && command -v plutil >/dev/null 2>&1; then plutil -lint "$PLIST"; fi

# ---------------------------------------------------------------------------- start
if [ "$START" = 1 ]; then
    step "starting"
    if [ "$DRY" = 1 ]; then
        echo "+ launchctl enable gui/$UIDN/$LABEL"
        echo "+ launchctl bootstrap gui/$UIDN $PLIST   (else: launchctl load -w $PLIST)"
    else
        STAMP="$(mktemp)"
        sleep 1                                      # host.json must be newer than this file
        launchctl enable "gui/$UIDN/$LABEL" >/dev/null 2>&1 || true
        launchctl bootstrap "gui/$UIDN" "$PLIST" >/dev/null 2>&1 || launchctl load -w "$PLIST" \
            || die "launchctl could not load the job (is a user logged in at the Mac's screen?)"
        FRESH=0
        printf 'waiting for the server'
        for _ in $(seq 1 40); do
            if [ "$DATA/host.json" -nt "$STAMP" ]; then FRESH=1; break; fi
            printf '.'; sleep 1
        done
        echo
        rm -f "$STAMP"
        if [ "$FRESH" = 1 ]; then
            "$PY" - "$DATA/host.json" <<'PYEOF' || true
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
print("Friends on your own network:  %s" % d.get("lan"))
print("Friends on the internet:      %s" % (d.get("internet") or "<your public IP>:%s#%s" % (d.get("port"), d.get("fingerprint"))))
print("Certificate fingerprint:      %s" % d.get("fingerprint"))
PYEOF
        else
            echo "The server has not reported in 40 seconds."
        fi
        echo "Log: $DATA/logs/launchd.log"
        echo "If it did not start, read the log and look at: launchctl print gui/$UIDN/$LABEL"
    fi
fi

step "done"
echo "Next: forward TCP 7781 and UDP 7781-7782 on your router to this Mac (docs/HOSTING.md),"
echo "and click Allow if macOS asks whether Python may accept incoming connections."
echo "Remove: lobby/deploy/macos/uninstall.sh"
