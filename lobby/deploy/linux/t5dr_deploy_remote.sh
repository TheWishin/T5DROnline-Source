#!/usr/bin/env bash
# The T5DR lobby update on the CENTRAL machine (t5lobby.service, with the T4 lobby t4lobby.service beside it sharing
# T5DR's account database), as root, from the unpacked NEW lobby folder:
#     sudo bash /opt/src/t5dr-lobby-X.Y.Z/lobby/deploy/linux/t5dr_deploy_remote.sh STEP [ARGS]
# (tools/deploy_lobby.sh on the PC uploads the folder and runs this; docs/DEPLOY_1.2.0.md explains every step.)
#
#   check            read only: machine, both services and their health, the running code (and the /opt/src folder it
#                    came from), the live database's schema and counts, what the new code expects, the chat filter list,
#                    T4's shared-accounts setting. Changes nothing.
#   precheck         a fresh backup (T5DR's own online backup), then on a COPY of it: the new code migrates it (schema,
#                    time, integrity), every earlier row is still there unchanged (lobby/tools/lobby_test_db.py), the T4
#                    lobby's shared-accounts check accepts the migrated copy, and the RUNNING (old) code still opens it
#                    (the code rollback keeps the database). The copies are removed. Players notice nothing.
#   notice MINUTES TEXT...
#                    the maintenance notice in both lobbies (T4: when installed).
#   deploy [--drain-wait S] [--no-t4-stop]
#                    check + precheck, backup (database, /etc/t5lobby, /etc/t4lobby, units and drop-ins, the running
#                    code), drain BOTH lobbies (default 900 s; nothing changes if they do not get quiet: the drains are
#                    taken back), a last backup, stop t4lobby, install.sh (code + restart; the env file, certificate and
#                    relay secrets stay), the new server migrates the database on its start, checks (health, schema,
#                    counts, log), start t4lobby, checks (health, "accounts shared with T5DR ... (schema N)").
#                    T5DR not healthy after the install -> the old code is put back by itself (database kept).
#                    --no-t4-stop: leave T4 running through the migration (proven safe; the default stops it anyway).
#   verify           the checks after a deploy, again (both lobbies, schema, counts, log lines). Changes nothing.
#   rollback [DIR]   drain, backup, the earlier code back (DIR = an /opt/src/<folder>/lobby to install.sh from; without
#                    DIR the code saved by the newest deploy), T4 restarted, checks. The database is KEPT as it is
#                    (an older server uses a newer schema as it is; never restore an old backup for a code rollback).
#
# Backups go to /root/t5dr-deploy-<folder>-<time>/ (root only). Nothing here touches the firewall, TLS, the relay nodes,
# the optional TCP 443 listener or `t5lobby-admin release` (only after the owner has published the release).
# T5D_ROOT=DIR: rehearsal in a staged layout (paths under DIR, install.sh --root, stub systemctl/journalctl on PATH:
# lobby/tools/deploy_rehearsal.py).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LOBBY="$(cd "$HERE/../.." && pwd)"                 # the NEW lobby folder
FOLDER="$(basename "$(dirname "$LOBBY")")"          # e.g. t5dr-lobby-1.2.0
R="${T5D_ROOT:-}"
STEP="${1:-}"; shift || true
TS="$(date -u +%Y%m%d-%H%M%S)"
BACKUP="$R/root/t5dr-deploy-$FOLDER-$TS"
T5DB="$R/var/lib/t5lobby/t5lobby.db"
T5CODE="$R/opt/t5lobby"
T4CODE="$R/opt/t4lobby"
T4ENV="$R/etc/t4lobby/t4lobby.env"
PY="${PYTHON:-python3}"
[ -n "$R" ] && export PATH="$R/usr/local/bin:$PATH"
die() { echo "t5dr_deploy: $*" >&2; exit 1; }
say() { printf '\n== %s\n' "$*"; }
ok() { echo "  ok: $*"; }

# paths handed to Python (staging under Git Bash with Windows' Python: Windows paths)
pp() { if [ -n "$R" ] && command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
as_svc() { if [ -z "$R" ]; then runuser -u t5lobby -- "$@"; else "$@"; fi; }
active() { systemctl is-active --quiet "$1" 2>/dev/null; }
have_t4() { [ -f "$R/etc/systemd/system/t4lobby.service" ] || [ -d "$T4CODE/t4lobby" ]; }
t4_shared() { grep -qs '^T5L_SHARED_ACCOUNTS_DB=' "$T4ENV"; }
pid_of() { systemctl show -p MainPID --value "$1" 2>/dev/null || echo 0; }
wait_health() {   # $1 = admin tool, $2 = seconds
    local i
    for ((i = 0; i < $2; i++)); do "$1" health -q >/dev/null 2>&1 && return 0; sleep 1; done
    return 1
}
journal_since() { journalctl -u "$1" --since "$2" --no-pager 2>/dev/null || true; }

new_schema() {   # the schema version the NEW code migrates to
    "$PY" -c "import sys; sys.path.insert(0, sys.argv[1]); from t5lobby.server.store import SCHEMA_VERSION; print(SCHEMA_VERSION)" "$(pp "$LOBBY")"
}
db_facts() {     # $1 = database: "schema N accounts N matches N sets N friends N" (read only, as the service user)
    as_svc "$PY" -c "
import sqlite3, sys
db = sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)
one = lambda q: db.execute(q).fetchone()[0]
tables = {r[0] for r in db.execute(\"SELECT name FROM sqlite_master WHERE type = 'table'\")}
n = lambda t: one(f'SELECT COUNT(*) FROM {t}') if t in tables else 0
print('schema', one('PRAGMA user_version'), 'accounts', n('accounts'), 'matches', n('matches'), 'sets', n('sets'),
      'friends', n('friends'), 'sessions', n('sessions'))
db.close()" "$(pp "$1")"
}
fact() { echo "$1" | awk -v k="$2" '{for (i = 1; i < NF; i++) if ($i == k) print $(i + 1)}'; }
running_src() {  # the /opt/src/*/lobby folder whose server code is the installed one
    local d f same
    for d in "$R"/opt/src/*/lobby; do
        [ -f "$d/t5lobby/server/lobby.py" ] || continue
        same=1
        for f in "$T5CODE"/t5lobby/*.py "$T5CODE"/t5lobby/server/*.py; do
            cmp -s "$f" "$d/t5lobby/${f#"$T5CODE"/t5lobby/}" || { same=0; break; }
        done
        [ "$same" = 1 ] && { echo "$d"; return 0; }
    done
    return 0
}
newest_backup() { ls -t "$R"/var/lib/t5lobby/backups/t5lobby-*.db 2>/dev/null | head -1 || true; }

# ------------------------------------------------------------------------------------------------ check
do_check() {
    say "check (read only)"
    [ "$(id -u)" = 0 ] || [ -n "$R" ] || die "run as root (sudo)"
    [ -f "$LOBBY/t5lobby/server/lobby.py" ] || die "this folder is not the T5DR lobby ($LOBBY)"
    [ -f "$LOBBY/tools/lobby_test_db.py" ] || die "$LOBBY/tools/lobby_test_db.py is missing (the archive needs lobby/tools)"
    echo "new code: $LOBBY (expects database schema $(new_schema))"
    "$PY" -c "import sys; assert sys.version_info >= (3, 10); print('python', sys.version.split()[0])"
    [ -z "$R" ] && echo "machine:  $(uname -srm)  $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")" \
                && echo "disk:     $(df -h /var/lib 2>/dev/null | awk 'NR==2 {print $4 " free on /var/lib"}')"
    active t5lobby || die "t5lobby.service is not running: this script updates a running lobby"
    t5lobby-admin health -q && ok "T5DR: t5lobby runs (pid $(pid_of t5lobby)), health ok" || die "T5DR health FAILED: fix that first"
    [ -f "$T5DB" ] || die "no T5DR database at $T5DB"
    local facts; facts="$(db_facts "$T5DB")"
    echo "  live database: $facts"
    local src; src="$(running_src)"
    if [ -n "$src" ]; then ok "running code = $src (rollback: rollback $src)"
    else echo "  note: no /opt/src folder matches the running code; the deploy saves the code itself (rollback without DIR)"; fi
    if have_t4; then
        if active t4lobby; then
            t4lobby-admin health -q && ok "T4: t4lobby runs (pid $(pid_of t4lobby)), health ok" || echo "  WARNING: T4 health failed"
        else echo "  T4: installed, not running (the deploy leaves it stopped)"; fi
        if t4_shared; then
            ok "T4 shares T5DR's accounts ($(sed -n 's/^T5L_SHARED_ACCOUNTS_DB=//p' "$T4ENV" | tail -1))"
        else echo "  T4: accounts of its own (not shared)"; fi
    else echo "  T4: not installed here"; fi
    # the chat filter's term list: shipped with the code (server/data), or the env file's own path
    local cf_path cf_on
    cf_on="$(sed -n 's/^T5L_CHAT_FILTER=//p' "$R/etc/t5lobby/t5lobby.env" 2>/dev/null | tail -1)"
    cf_path="$(sed -n 's/^T5L_CHAT_FILTER_PATH=//p' "$R/etc/t5lobby/t5lobby.env" 2>/dev/null | tail -1)"
    if [ "${cf_on:-1}" = 0 ]; then echo "  chat filter: off in the env file (T5L_CHAT_FILTER=0)"
    else
        [ -n "$cf_path" ] || cf_path="$LOBBY/t5lobby/server/data/chat_filter_terms.json"
        [ -n "$R" ] && [ "${cf_path#/etc/}" != "$cf_path" ] && cf_path="$R$cf_path"
        "$PY" -c "
import json, sys; sys.path.insert(0, sys.argv[1])
from t5lobby.server.chatfilter import ChatFilter
ChatFilter(sys.argv[2])
print('  ok: chat filter list', sys.argv[2], '-', len(json.load(open(sys.argv[2], encoding='utf-8-sig'))['terms']), 'terms')" \
            "$(pp "$LOBBY")" "$(pp "$cf_path")" || die "the chat filter list does not load: the new server would refuse to start (T5L_CHAT_FILTER_PATH / T5L_CHAT_FILTER=0)"
    fi
    local fb; fb="$(sed -n 's/^T5L_TCP_FALLBACK_PORT=//p' "$R/etc/t5lobby/t5lobby.env" 2>/dev/null | tail -1)"
    echo "  TCP fallback listener: ${fb:-0 (off)}  (opt-in, separate step: DEPLOY_1.2.0.md 'TCP 443 fallback')"
    echo "check done"
}

# ------------------------------------------------------------------------------------------------ precheck
do_precheck() {
    say "precheck: the new code on a copy of a fresh backup (players notice nothing)"
    umask 077
    mkdir -p "$BACKUP"
    t5lobby-admin backup | tee "$BACKUP/precheck-backup.txt"
    local src; src="$(newest_backup)"
    [ -n "$src" ] || die "no backup file in /var/lib/t5lobby/backups"
    local copy="$BACKUP/precheck.db"
    cp "$src" "$copy"
    "$PY" "$(pp "$LOBBY/tools/lobby_test_db.py")" digest "$(pp "$copy")" > "$BACKUP/precheck-before.json"
    # (the copy is root's and lives in /root: no service user, no environment from the env file -> no network)
    if ! "$PY" - "$(pp "$LOBBY")" "$(pp "$copy")" > "$BACKUP/precheck-migrate.txt" 2>&1 <<'EOF'; then
import sys, time
sys.path.insert(0, sys.argv[1])
from t5lobby.server import Config, LobbyServer
from t5lobby.server.store import SCHEMA_VERSION
t = time.monotonic()
s = LobbyServer(Config(db=sys.argv[2], status_port=0))
dt = time.monotonic() - t
one = lambda q: s.store.db.execute(q).fetchone()[0]
print(f"new code on the copy: schema {s.store.schema_version()} (code {SCHEMA_VERSION}), migrated now {s.store.migrated},"
      f" tournaments {s.tours.migrated}, accounts {one('SELECT COUNT(*) FROM accounts')},"
      f" matches {one('SELECT COUNT(*) FROM matches')}, integrity {one('PRAGMA integrity_check')}, start {dt:.2f} s")
ok = s.store.schema_version() == SCHEMA_VERSION and one("PRAGMA integrity_check") == "ok"
s.store.close()
sys.exit(0 if ok else 1)
EOF
        cat "$BACKUP/precheck-migrate.txt"
        die "the new code did not migrate the copy cleanly (see above); nothing was changed"
    fi
    grep -E "^new code on the copy|WARNING|ERROR" "$BACKUP/precheck-migrate.txt" | sed 's/^/  /' || true
    if ! "$PY" "$(pp "$LOBBY/tools/lobby_test_db.py")" compare "$(pp "$BACKUP/precheck-before.json")" "$(pp "$copy")" \
            > "$BACKUP/precheck-compare.txt"; then
        cat "$BACKUP/precheck-compare.txt"
        die "rows changed by the migration (see above); nothing was changed"
    fi
    sed 's/^/  /' "$BACKUP/precheck-compare.txt"
    if have_t4 && [ -d "$T4CODE/t4lobby" ]; then
        "$PY" -c "
import sys; sys.path.insert(0, sys.argv[1])
from t4lobby.server.shared_accounts import SharedAccounts, SharedAccountsError
try:
    s = SharedAccounts(sys.argv[2])
except SharedAccountsError as e:
    sys.exit(f'T4 REFUSES the migrated database: {e}')
n = s.db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
print(f'  ok: the installed T4 lobby accepts the migrated database (schema {s.schema}, {n} accounts)')
s.close()" "$(pp "$T4CODE")" "$(pp "$copy")" || die "T4 would not start on the migrated database; nothing was changed"
    fi
    "$PY" - "$(pp "$T5CODE")" "$(pp "$copy")" <<'EOF' || die "the running (old) code cannot open the migrated database: no code rollback possible; stop"
import logging, sys
logging.disable(logging.WARNING)
sys.path.insert(0, sys.argv[1])
from t5lobby.server import Config, LobbyServer
s = LobbyServer(Config(db=sys.argv[2], status_port=0))
n = s.store.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
print(f"  ok: the running (old) code opens the migrated copy too (schema {s.store.schema_version()}, {n} accounts): "
      "a code rollback keeps the database")
s.store.close()
EOF
    rm -f "$copy" "$copy-wal" "$copy-shm"
    echo "precheck done ($BACKUP)"
}

# ------------------------------------------------------------------------------------------------ backup
do_backup() {
    say "backup -> $BACKUP"
    umask 077
    mkdir -p "$BACKUP"
    t5lobby-admin backup | tee "$BACKUP/t5lobby-backup.txt"
    local b; b="$(newest_backup)"
    [ -n "$b" ] && cp -p "$b" "$BACKUP/" && echo "copied $(basename "$b")"
    tar -C "$R/etc" -czf "$BACKUP/etc-t5lobby.tgz" t5lobby && echo "saved /etc/t5lobby (settings, certificate, relay secrets)"
    tar -C "$R/opt" -czf "$BACKUP/opt-t5lobby.tgz" t5lobby && echo "saved /opt/t5lobby (the running code: rollback)"
    tar -C "$R/etc/systemd/system" -czf "$BACKUP/units.tgz" $(cd "$R/etc/systemd/system" && ls -d t5lobby.service* t4lobby.service* 2>/dev/null) \
        && echo "saved the t5lobby/t4lobby units and drop-ins"
    [ -f "$R/usr/local/bin/t5lobby-admin" ] && cp -p "$R/usr/local/bin/t5lobby-admin" "$BACKUP/"
    if have_t4; then
        [ -d "$R/etc/t4lobby" ] && tar -C "$R/etc" -czf "$BACKUP/etc-t4lobby.tgz" t4lobby && echo "saved /etc/t4lobby"
        active t4lobby && { t4lobby-admin backup | tee "$BACKUP/t4lobby-backup.txt" || true; }
    fi
    { echo "time $TS"; echo "folder $FOLDER"; echo "t5lobby pid $(pid_of t5lobby)"; echo "t4lobby active $(active t4lobby && echo yes || echo no)"
      echo "running src $(running_src)"; echo "db $(db_facts "$T5DB")"; } > "$BACKUP/baseline.txt"
    cat "$BACKUP/baseline.txt"
}

# ------------------------------------------------------------------------------------------------ verify
verify_t5() {   # $1 = time of the start (journal), $2 = baseline facts ("" = none)
    wait_health t5lobby-admin 30 || return 1
    ok "T5DR health ok (pid $(pid_of t5lobby))"
    local want facts; want="$(new_schema)"; facts="$(db_facts "$T5DB")"
    echo "  database: $facts"
    [ "$(fact "$facts" schema)" -ge "$want" ] || { echo "  FAIL: schema $(fact "$facts" schema), the new code wants $want"; return 1; }
    ok "schema $(fact "$facts" schema)"
    if [ -n "$2" ]; then
        local k
        for k in accounts matches sets friends; do
            [ "$(fact "$facts" $k)" -ge "$(fact "$2" $k)" ] || { echo "  FAIL: $k $(fact "$2" $k) -> $(fact "$facts" $k)"; return 1; }
        done
        ok "accounts, matches, sets, friends: as many as before or more"
    fi
    if [ -n "$1" ]; then
        local log; log="$(journal_since t5lobby "$1")"
        echo "$log" | grep -E "database upgraded to schema|listening:|Traceback|ERROR" | sed 's/^/  log: /' || true
        echo "$log" | grep -q "Traceback" && { echo "  FAIL: a Traceback in the T5DR log"; return 1; }
    fi
    return 0
}
verify_t4() {   # $1 = time of the start (journal)
    have_t4 || { echo "  T4: not installed"; return 0; }
    active t4lobby || { echo "  FAIL: t4lobby is not running"; return 1; }
    wait_health t4lobby-admin 30 || { echo "  FAIL: T4 health"; return 1; }
    ok "T4 health ok (pid $(pid_of t4lobby))"
    if t4_shared && [ -n "$1" ]; then
        local line; line="$(journal_since t4lobby "$1" | grep 'accounts shared with T5DR' | tail -1 || true)"
        [ -n "$line" ] || { echo "  FAIL: T4 did not log 'accounts shared with T5DR' since $1"; return 1; }
        ok "T4: ${line##*t4lobby.shared_accounts: }"
        local want; want="$(fact "$(db_facts "$T5DB")" schema)"
        case "$line" in *"(schema $want)") ok "T4 runs on T5DR's schema $want" ;;
            *) echo "  FAIL: T4 reports another schema than the database's $want"; return 1 ;; esac
    fi
    return 0
}
do_verify() {
    say "verify"
    local since; since="$(date '+%Y-%m-%d %H:%M:%S' -d '-30 min' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')"
    verify_t5 "$since" "" || die "T5DR checks failed"
    verify_t4 "$since" || die "T4 checks failed"
    echo "verify done"
}

# ------------------------------------------------------------------------------------------------ drain
drain_both() {   # $1 = seconds; on failure both drains are taken back
    local wait="$1" t4pid=""
    say "drain: no new matches, waiting up to $wait s for running matches and ranked sets"
    if have_t4 && active t4lobby; then
        t4lobby-admin drain --wait "$wait" > "$BACKUP/t4-drain.txt" 2>&1 & t4pid=$!
    fi
    if ! t5lobby-admin drain --wait "$wait"; then
        t5lobby-admin drain --off || true
        if [ -n "$t4pid" ]; then kill "$t4pid" 2>/dev/null || true; t4lobby-admin drain --off || true; fi
        die "T5DR did not get quiet within $wait s: drains taken back, nothing installed (try again later)"
    fi
    if [ -n "$t4pid" ]; then
        if ! wait "$t4pid"; then
            cat "$BACKUP/t4-drain.txt"
            t5lobby-admin drain --off || true; t4lobby-admin drain --off || true
            die "T4 did not get quiet within $wait s: drains taken back, nothing installed"
        fi
        sed 's/^/  T4: /' "$BACKUP/t4-drain.txt"
    fi
}

run_install() {  # $1 = lobby folder to install from
    umask 022        # (the backups' umask 077 would leave new code folders unreadable for the service user)
    if [ -n "$R" ]; then
        PYTHON="$PY" bash "$1/deploy/linux/install.sh" --root "$R" --self-signed > "$BACKUP/install-$(basename "$(dirname "$1")").txt"
        systemctl restart t5lobby
    else
        bash "$1/deploy/linux/install.sh" --self-signed --firewall none | tee "$BACKUP/install-$(basename "$(dirname "$1")").txt"
    fi
}
restore_code() { # the code saved in $1 (a deploy's backup folder) back, restart
    umask 022
    rm -rf "$T5CODE/t5lobby"
    tar -C "$R/opt" -xzf "$1/opt-t5lobby.tgz"
    [ -f "$1/t5lobby-admin" ] && cp -p "$1/t5lobby-admin" "$R/usr/local/bin/t5lobby-admin"
    tar -C "$R/etc/systemd/system" -xzf "$1/units.tgz" t5lobby.service 2>/dev/null || true
    systemctl daemon-reload
    systemctl restart t5lobby
}
start_t4() {     # $1 = was it running before
    [ "$1" = yes ] || { echo "  T4 was not running before: left stopped"; return 0; }
    systemctl start t4lobby
}

# ------------------------------------------------------------------------------------------------ deploy
do_deploy() {
    local wait=900 stop_t4=1
    while [ $# -gt 0 ]; do
        case "$1" in --drain-wait) wait="${2:?}"; shift ;; --no-t4-stop) stop_t4=0 ;; *) die "deploy: unknown option $1" ;; esac
        shift
    done
    do_check
    do_precheck
    do_backup
    local base t4was; base="$(sed -n 's/^db //p' "$BACKUP/baseline.txt")"
    t4was="$(sed -n 's/^t4lobby active //p' "$BACKUP/baseline.txt")"
    drain_both "$wait"
    say "last backup (the database exactly as the install finds it)"
    t5lobby-admin backup | tee -a "$BACKUP/t5lobby-backup.txt"
    cp -p "$(newest_backup)" "$BACKUP/"
    if [ "$t4was" = yes ] && [ "$stop_t4" = 1 ]; then
        say "stop t4lobby for the migration (T4 players reconnect in a moment)"
        systemctl stop t4lobby
    fi
    say "install $FOLDER (install.sh; the server migrates the database on its start)"
    local started; started="$(date '+%Y-%m-%d %H:%M:%S')"
    if ! run_install "$LOBBY" || ! verify_t5 "$started" "$base"; then
        say "T5DR did not come up healthy on the new code: putting the old code back (database kept)"
        journal_since t5lobby "$started" | tail -30
        restore_code "$BACKUP"
        wait_health t5lobby-admin 30 && echo "  T5DR: old code running again, health ok" || echo "  T5DR: STILL NOT HEALTHY -- journalctl -u t5lobby"
        [ "$t4was" = yes ] && { active t4lobby || systemctl start t4lobby; }
        die "deploy failed and was rolled back; backups in $BACKUP"
    fi
    say "T4"
    local t4start; t4start="$(date '+%Y-%m-%d %H:%M:%S')"
    if [ "$t4was" = yes ]; then
        if [ "$stop_t4" = 1 ]; then start_t4 yes; else systemctl restart t4lobby; fi
    fi
    verify_t4 "$t4start" || die "T5DR runs the new code, but T4 failed its checks: journalctl -u t4lobby; T4's own rollback: docs/DEPLOY_T4_BETA.md (T5DR stays as it is)"
    say "done: $FOLDER runs; backups in $BACKUP"
    echo "Next: a real login with a launcher; after the owner has PUBLISHED the release: t5lobby-admin release X.Y.Z"
    echo "The maintenance notice ends by itself (or: t5lobby-admin notice --clear; t4lobby-admin notice --clear)."
}

# ------------------------------------------------------------------------------------------------ rollback
do_rollback() {
    local dir="${1:-}" from
    if [ -n "$dir" ]; then
        dir="${dir%/}"; [ "$(basename "$dir")" = lobby ] || dir="$dir/lobby"
        [ -f "$dir/deploy/linux/install.sh" ] && [ -f "$dir/t5lobby/server/lobby.py" ] || die "$dir is not a T5DR lobby folder"
        from="$dir"
    else
        from="$(ls -dt "$R"/root/t5dr-deploy-*/ 2>/dev/null | while read -r d; do [ -f "$d/opt-t5lobby.tgz" ] && [ -f "$d/install-$FOLDER.txt" ] && { echo "${d%/}"; break; }; done || true)"
        [ -n "$from" ] || die "no deploy backup with saved code under /root/t5dr-deploy-*: give the old /opt/src/<folder>/lobby"
    fi
    do_backup
    local t4was; t4was="$(sed -n 's/^t4lobby active //p' "$BACKUP/baseline.txt")"
    drain_both 900
    t5lobby-admin backup | tee -a "$BACKUP/t5lobby-backup.txt"
    [ "$t4was" = yes ] && systemctl stop t4lobby
    say "rollback: the code from $from (the database stays as it is)"
    local started; started="$(date '+%Y-%m-%d %H:%M:%S')"
    if [ -n "$dir" ]; then run_install "$from"; else restore_code "$from"; fi
    wait_health t5lobby-admin 30 || die "T5DR not healthy after the rollback: journalctl -u t5lobby"
    ok "T5DR health ok on the earlier code; database: $(db_facts "$T5DB")"
    journal_since t5lobby "$started" | grep -E "newer than this server|listening:" | sed 's/^/  log: /' || true
    local t4start; t4start="$(date '+%Y-%m-%d %H:%M:%S')"
    start_t4 "$t4was"
    verify_t4 "$t4start" || die "T4 failed its checks after the rollback"
    echo "rollback done; backups in $BACKUP"
}

do_notice() {
    local minutes="${1:?notice MINUTES TEXT}"; shift
    [ $# -gt 0 ] || die "notice MINUTES TEXT"
    t5lobby-admin notice "$*" --minutes "$minutes"
    if have_t4 && active t4lobby; then t4lobby-admin notice "$*" --minutes "$minutes"; fi
}

case "$STEP" in
    check) do_check ;;
    precheck) do_check; do_precheck ;;
    notice) do_notice "$@" ;;
    deploy) do_deploy "$@" ;;
    verify) do_verify ;;
    rollback) do_rollback "${1:-}" ;;
    *) sed -n '2,32p' "$0"; exit 2 ;;
esac
