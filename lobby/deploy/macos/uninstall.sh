#!/bin/bash
# Stop the T5DR lobby host job and remove it (the LaunchAgent and the copied code).
# The data folder (database, certificate, logs, backups) is kept: delete it by hand if you want to.
# NOT TESTED ON A REAL MAC -- see docs/HOSTING.md, "macOS: host on a Mac at home".
#
#   lobby/deploy/macos/uninstall.sh [--dry-run]
set -eu

LABEL=org.t5dronline.lobby-host
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP="$HOME/Library/Application Support/T5DR Online/lobby-app"
DRY=0
case "${1:-}" in
    "") ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "usage: uninstall.sh [--dry-run]" >&2; exit 2 ;;
esac
UIDN="$(id -u)"

if [ "$DRY" = 1 ]; then
    echo "+ launchctl bootout gui/$UIDN/$LABEL   (else: launchctl unload $PLIST)"
    echo "+ rm -f $PLIST"
    echo "+ rm -rf $APP"
else
    launchctl bootout "gui/$UIDN/$LABEL" >/dev/null 2>&1 || launchctl unload "$PLIST" >/dev/null 2>&1 || true
    rm -f "$PLIST"
    rm -rf "$APP"
fi
echo "Removed the job and the copied code."
echo "Kept the data folder (database, certificate, logs, backups): $HOME/Library/Application Support/T5DR Online/lobby-host"
echo "(or ~/.local/share/t5lobby-host if an older run made it). Delete it by hand if you no longer need it."
