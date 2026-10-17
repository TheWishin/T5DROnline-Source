"""Admin tool for a lobby server: python -m t5lobby.server.admin COMMAND ...

It works on the server's SQLite database directly (safe while the server runs: SQLite locks, and
the server picks up bans within T5L_ADMIN_POLL seconds and kicks the player), and asks the running
server for live numbers over its local status endpoint (http://127.0.0.1:7780/status).

The database is --db, else $T5L_DB, else ./t5lobby.db -- the same rule the server uses, so run it
with the server's environment (systemd: `sudo -u t5lobby env $(cat /etc/t5lobby/t5lobby.env) ...`
or simply the wrapper `t5lobby-admin`; Docker: `docker compose exec lobby t5lobby-admin ...`).

    status [--json]                      players online, rooms, matches today, relay bandwidth
    health                               exit code 0 when the server answers (health checks)
    users [TEXT] [--banned] [--limit N]  accounts, most recently seen first
    user NAME                            one account and its last matches
    ban NAME [--days D | --hours H] [--reason TEXT]       (no duration: for good)
    unban NAME
    ban-ip ADDRESS|CIDR [--days D | --hours H] [--reason TEXT]   (guests have no account: ban the address)
    unban-ip ADDRESS|CIDR
    bans                                 banned accounts and addresses
    reset-password NAME [--password-env VAR]   new password from env VAR, else a random one is printed;
                                         ends the account's remembered logins
    recovery-codes NAME                  a new set of recovery codes (printed once; the old ones stop working)
    logout-all NAME                      end every remembered login of the account
    reset-rating NAME                    back to 1500 and unranked (placement again); the record stays
    delete-user NAME --yes
    purge-guests [--days 30]             delete records of guest-only matches older than this
    purge-inactive --days N [--include-played] --yes   delete accounts not seen for N days
    matches [--player NAME] [--limit N]
    backup [DIR] [--keep N]              online backup (default DIR: $T5L_BACKUP_DIR or ./backups)
    restore FILE [--yes] [--force]       put a backup back (stop the server first)
    notice TEXT... [--minutes N | --hours H]   a message for every connected player (e.g. "server restart in
                                         20 min"); the launcher shows it in its status bar. Default: 60 minutes
    notice --clear                       take the message down
    notices                              the latest messages and whether they are showing
    gen-cert [--dir DIR] [--name HOST] [--days N] [--force]   self-signed certificate + fingerprint
    fingerprint CERT                     SHA-256 fingerprint of a certificate (what clients pin)
    server-entry --name NAME --host HOST [--port N] (--cert CERT | --ca | --plain)
                                         the servers.json entry the launcher needs
"""
import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

from ..proto import DEFAULT_PORT, valid_name
from . import backup as bk
from .store import PERMANENT, Store, hash_password


def _fmt_t(t):
    if not t:
        return "-"
    if t >= PERMANENT:
        return "for good"
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(t)) + "Z"


def _db_path(a):
    return a.db or os.environ.get("T5L_DB") or "t5lobby.db"


def _open(a):
    path = _db_path(a)
    if path != ":memory:" and not os.path.isfile(path):
        sys.exit(f"no database at {path} (use --db or T5L_DB; the server creates it on first start)")
    return Store(path)


def _status_url(a, path="/status"):
    if a.status_url:
        base = a.status_url.rstrip("/")
        for suffix in ("/status", "/health", "/metrics"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        return base + path
    host = os.environ.get("T5L_STATUS_HOST", "127.0.0.1")
    if host in ("0.0.0.0", "", "::"):
        host = "127.0.0.1"
    port = os.environ.get("T5L_STATUS_PORT", "7780")
    return f"http://{host}:{port}{path}"


def _fetch(url, timeout=3.0):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))    # never through a proxy
    with opener.open(url, timeout=timeout) as r:
        return r.status, r.read(1 << 20).decode("utf-8")


def _duration(a):
    if getattr(a, "days", None):
        return time.time() + a.days * 86400.0
    if getattr(a, "hours", None):
        return time.time() + a.hours * 3600.0
    return PERMANENT


def _account(store, name):
    row = store.account(name)
    if row is None:
        sys.exit(f"no account named {name!r}")
    return row


# ----------------------------------------------------------------------------- commands
def cmd_status(a):
    try:
        code, body = _fetch(_status_url(a))
        st = json.loads(body)
    except (OSError, ValueError) as e:
        print(f"server not reachable at {_status_url(a)} ({e}); database only:")
        path = _db_path(a)
        if os.path.isfile(path):
            print(json.dumps(Store(path).stats(), indent=1))
        return 1
    if a.json:
        print(json.dumps(st, indent=1))
        return 0
    p, r, db = st["players"], st["relay"], st.get("db", {})
    up = st["uptime_s"]
    print(f"{st['server']}  up {up // 86400}d {up % 86400 // 3600}h {up % 3600 // 60}m")
    print(f"players   {p['online']} online ({p['guests']} guests, {p['accounts']} accounts), "
          f"{p['playing']} playing, {p['in_queue']} searching")
    print(f"rooms     {st['rooms']}   queues {st['queue']}")
    print(f"matches   {st['matches']['running']} running {st['matches']['by_state'] or ''}; "
          f"last 24 h: {db.get('matches_24h', '?')} {db.get('matches_24h_by_path', '')}")
    print(f"relay     {r['sessions']}/{r['max']} sessions, {r['kbit_s']:.0f} kbit/s now, "
          f"{r['bytes_total'] / 1e6:.1f} MB since start{'  (relay only)' if r['force_relay'] else ''}")
    print(f"accounts  {db.get('accounts', '?')} ({db.get('accounts_seen_24h', '?')} seen in 24 h), "
          f"banned {db.get('accounts_banned', 0)}, address bans {db.get('ip_bans', 0)}")
    tls = st.get("tls")
    if tls:
        print(f"tls       {tls.get('subject', '')} expires {tls.get('not_after', '?')} "
              f"({tls.get('days_left', '?')} days)")
    else:
        print("tls       off")
    pr = st.get("process", {})
    c = st["counters"]
    print(f"process   cpu {pr.get('cpu_s')} s, rss {pr.get('rss_mb')} MB, python {pr.get('python')}; "
          f"traffic {c['tcp_out_bytes'] / 1e6:.1f} MB out / {c['tcp_in_bytes'] / 1e6:.1f} MB in (control)")
    return 0


def cmd_health(a):
    try:
        code, body = _fetch(_status_url(a, "/health"), timeout=a.timeout)
    except (OSError, ValueError) as e:
        if not a.quiet:
            print(f"unhealthy: {e}")
        return 1
    ok = code == 200 and body.strip() == "ok"
    if not a.quiet:
        print("ok" if ok else f"unhealthy: {code} {body[:80]}")
    return 0 if ok else 1


def cmd_users(a):
    st = _open(a)
    rows = st.list_accounts(a.text, a.limit, a.banned)
    print(f"{'name':<17}{'rating':>7}{'rd':>5}{'W-L-D':>11}  {'last seen':<18}{'created':<18}banned")
    for r in rows:
        ban = st.ban_state(r)
        print(f"{r['name']:<17}{r['rating']:>7.0f}{r['rd']:>5.0f}{'%d-%d-%d' % (r['wins'], r['losses'], r['draws']):>11}"
              f"  {_fmt_t(r['last_seen']):<18}{_fmt_t(r['created']):<18}{_fmt_t(ban[0]) if ban else ''}")
    print(f"({len(rows)} shown)")
    return 0


def cmd_user(a):
    st = _open(a)
    r = _account(st, a.name)
    ban = st.ban_state(r)
    print(f"name      {r['name']} (id {r['id']})")
    print(f"created   {_fmt_t(r['created'])}   last seen {_fmt_t(r['last_seen'])}   "
          f"password changed {_fmt_t(r['pw_changed'])}")
    print(f"rating    {r['rating']:.1f}  rd {r['rd']:.1f}  vol {r['vol']:.4f}  games {r['games']} "
          f"({r['wins']}-{r['losses']}-{r['draws']}), ranked {r['ranked_games']}, tier {r['tier']} "
          f"(peak {r['tier_peak']})")
    print(f"logins    {st.session_count(r['id'])} remembered, {st.recovery_left(r['id'])} recovery codes left")
    print(f"banned    {_fmt_t(ban[0]) + ' ' + ban[1] if ban else 'no'}")
    _print_matches(st.recent_matches(10, r["name"]))
    return 0


def _print_matches(rows):
    for m in rows:
        sc = json.loads(m["score"]) if m["score"] else None
        print(f"  {_fmt_t(m['created'])}  {m['id']}  {m['p1_name']} vs {m['p2_name']}  {m['status']:<9} "
              f"winner {'-' if m['winner'] is None else 'P%d' % (m['winner'] + 1)} {sc or ''} "
              f"{m['path'] or ''} {'%.0f ms' % m['rtt_ms'] if m['rtt_ms'] else ''}{' ranked' if m['ranked'] else ''}")


def cmd_ban(a):
    st = _open(a)
    r = _account(st, a.name)
    until = _duration(a)
    st.ban_account(r["name"], until, a.reason or "")
    st.revoke_sessions(r["id"])           # remembered logins end too
    print(f"banned {r['name']} {_fmt_t(until) if until < PERMANENT else 'for good'}"
          f"{': ' + a.reason if a.reason else ''} (kicked within a few seconds if online)")
    return 0


def cmd_unban(a):
    st = _open(a)
    print("unbanned" if st.unban_account(_account(st, a.name)["name"]) else "not found")
    return 0


def _norm_net(text):
    import ipaddress
    try:
        return str(ipaddress.ip_network(text, strict=False))
    except ValueError:
        sys.exit(f"not an address or network: {text!r}")


def cmd_ban_ip(a):
    st = _open(a)
    net = _norm_net(a.net)
    until = _duration(a)
    st.ban_ip(net, until, a.reason or "")
    print(f"banned {net} {_fmt_t(until)}{': ' + a.reason if a.reason else ''}")
    return 0


def cmd_unban_ip(a):
    st = _open(a)
    print("unbanned" if st.unban_ip(_norm_net(a.net)) else "no such ban")
    return 0


def cmd_bans(a):
    st = _open(a)
    for r in st.list_accounts(None, 1000, banned_only=True):
        print(f"account  {r['name']:<17} until {_fmt_t(r['banned_until']):<18} {r['ban_reason'] or ''}")
    for b in st.ip_bans():
        print(f"address  {b['net']:<17} until {_fmt_t(b['until']):<18} {b['reason'] or ''}")
    return 0


def cmd_reset_password(a):
    st = _open(a)
    r = _account(st, a.name)
    if a.password_env:
        pw = os.environ.get(a.password_env, "")
        if not 6 <= len(pw) <= 128:
            sys.exit(f"${a.password_env} must hold 6-128 characters")
        shown = None
    else:
        pw = shown = secrets.token_urlsafe(9)
    n = int(os.environ.get("T5L_SCRYPT_N", 1 << 14))
    st.set_password(r["id"], hash_password(pw, n))
    st.revoke_sessions(r["id"])
    print(f"password of {r['name']} reset" + (f"; new password: {shown}  (tell the player privately; they "
                                              "change it in the launcher)" if shown else "")
          + "; remembered logins ended")
    return 0


def cmd_recovery_codes(a):
    st = _open(a)
    r = _account(st, a.name)
    codes = st.issue_recovery_codes(r["id"])
    print(f"new recovery codes for {r['name']} (the old ones no longer work; give them to the player privately):")
    for c in codes:
        print("   ", c)
    return 0


def cmd_logout_all(a):
    st = _open(a)
    r = _account(st, a.name)
    n = st.session_count(r["id"])
    st.revoke_sessions(r["id"])
    print(f"ended {n} remembered login(s) of {r['name']}")
    return 0


def cmd_reset_rating(a):
    st = _open(a)
    st.reset_rating(_account(st, a.name)["name"])
    print("rating reset to 1500 / RD 350 and unranked (placement again); takes effect at the player's next login")
    return 0


def cmd_delete_user(a):
    if not a.yes:
        sys.exit("deleting an account cannot be undone; add --yes")
    st = _open(a)
    print("deleted" if st.delete_account(_account(st, a.name)["name"]) else "not found")
    return 0


def cmd_purge_guests(a):
    st = _open(a)
    n = st.purge_guest_matches(a.days)
    print(f"deleted {n} guest-only match record(s) older than {a.days} days "
          "(guests themselves are never stored; ban an address with ban-ip)")
    return 0


def cmd_purge_inactive(a):
    if not a.yes:
        sys.exit("this deletes accounts; add --yes")
    st = _open(a)
    n = st.purge_inactive_accounts(a.days, a.include_played)
    print(f"deleted {n} account(s) not seen for {a.days} days"
          + ("" if a.include_played else " that never finished a game"))
    return 0


def cmd_matches(a):
    _print_matches(_open(a).recent_matches(a.limit, a.player))
    return 0


def cmd_backup(a):
    db = _db_path(a)
    dest = a.dir or os.environ.get("T5L_BACKUP_DIR") or os.path.join(os.path.dirname(os.path.abspath(db)), "backups")
    path = bk.backup_db(db, dest, a.keep)
    info = bk.verify(path)
    print(f"{path}  ({os.path.getsize(path) / 1e3:.0f} kB, {info['accounts']} accounts, {info['matches']} matches)")
    return 0


def cmd_restore(a):
    db = _db_path(a)
    try:
        info = bk.verify(a.file)
    except Exception as e:     # noqa: BLE001
        sys.exit(f"{a.file}: not a usable backup ({e})")
    running = cmd_health(argparse.Namespace(status_url=a.status_url, timeout=1.0, quiet=True)) == 0
    if running and not a.force:
        sys.exit("the server is running: stop it first (it keeps ratings in memory and would write them "
                 "back), or add --force")
    if not a.yes:
        sys.exit(f"this replaces {db} with {a.file} ({info['accounts']} accounts, {info['matches']} matches); "
                 "the current database is saved first. Add --yes")
    safety, _ = bk.restore_db(a.file, db)
    print(f"restored {a.file} -> {db}" + (f"; the previous database was saved as {safety}" if safety else ""))
    return 0


NOTICE_MAX = 200


def cmd_notice(a):
    st = _open(a)
    if a.clear:
        n = st.clear_notices()
        print(f"cleared {n} notice(s); connected players see it go within a few seconds")
        return 0
    text = "".join(ch for ch in " ".join(a.text) if ch.isprintable()).strip()
    if not text:
        sys.exit("what should the notice say?  notice \"server restart in 20 min\"  (or: notice --clear)")
    if len(text) > NOTICE_MAX:
        sys.exit(f"too long: {len(text)} characters, at most {NOTICE_MAX}")
    seconds = a.hours * 3600.0 if a.hours else (a.minutes or 60.0) * 60.0
    until = time.time() + seconds
    nid = st.add_notice(text, until)
    print(f"notice #{nid} sent to everyone online within a few seconds (and to players who log in), "
          f"showing until {_fmt_t(until)} or `notice --clear`:\n  {text}")
    return 0


def cmd_notices(a):
    st = _open(a)
    now = time.time()
    rows = st.recent_notices(a.limit)
    for r in rows:
        state = "cleared" if r["cleared"] else ("showing" if r["expires"] > now else "ended")
        print(f"#{r['id']:<4}{state:<9}{_fmt_t(r['created'])}  until {_fmt_t(r['expires'])}  {r['text']}")
    if not rows:
        print("(no notices yet)")
    return 0


def cmd_gen_cert(a):
    from . import selfsigned
    t0 = time.monotonic()
    try:
        cert, key, fp = selfsigned.write_pair(a.dir, a.name, a.days, a.force)
    except FileExistsError as e:
        sys.exit(str(e))
    print(f"certificate {cert}\nkey         {key}  (keep it private)\n"
          f"valid       {a.days} days   ({time.monotonic() - t0:.1f} s to make)")
    print(f"fingerprint {selfsigned.pretty(fp)}")
    print("\nServer: T5L_TLS_CERT=%s T5L_TLS_KEY=%s" % (cert, key))
    print("Players: put the fingerprint in the server's servers.json entry (\"tls\": \"pin\"), or type "
          f"HOST:PORT#{fp} as the server address.")
    return 0


def cmd_fingerprint(a):
    from . import selfsigned
    fp = selfsigned.fingerprint(a.cert)
    print(selfsigned.pretty(fp) if not a.plain else fp)
    return 0


def cmd_server_entry(a):
    from ..servers import ServerEntry
    if a.cert:
        from . import selfsigned
        e = ServerEntry(a.name, a.host, a.port, "pin", selfsigned.fingerprint(a.cert))
    else:
        e = ServerEntry(a.name, a.host, a.port, "ca" if a.ca else "off", "")
    e.region, e.note = a.region or "", a.note or ""
    print(json.dumps(e.to_json(), indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m t5lobby.server.admin",
                                 description="T5DR lobby server administration",
                                 epilog="Details: docs/HOSTING.md")
    ap.add_argument("--db", help="database file (default $T5L_DB or ./t5lobby.db)")
    ap.add_argument("--status-url", help="status endpoint (default http://127.0.0.1:$T5L_STATUS_PORT/status)")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        return p

    def duration(p):
        g = p.add_mutually_exclusive_group()
        g.add_argument("--days", type=float)
        g.add_argument("--hours", type=float)
        p.add_argument("--reason")

    add("status", cmd_status, "live numbers from the running server").add_argument("--json", action="store_true")
    p = add("health", cmd_health, "exit 0 when the server answers")
    p.add_argument("--timeout", type=float, default=3.0)
    p.add_argument("-q", "--quiet", action="store_true")
    p = add("users", cmd_users, "list accounts")
    p.add_argument("text", nargs="?")
    p.add_argument("--banned", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    add("user", cmd_user, "show one account").add_argument("name")
    p = add("ban", cmd_ban, "ban an account")
    p.add_argument("name")
    duration(p)
    add("unban", cmd_unban, "lift an account ban").add_argument("name")
    p = add("ban-ip", cmd_ban_ip, "ban an address or network")
    p.add_argument("net")
    duration(p)
    add("unban-ip", cmd_unban_ip, "lift an address ban").add_argument("net")
    add("bans", cmd_bans, "list bans")
    p = add("reset-password", cmd_reset_password, "set a new password")
    p.add_argument("name")
    p.add_argument("--password-env", metavar="VAR", help="take the new password from this environment variable")
    add("recovery-codes", cmd_recovery_codes, "issue new recovery codes").add_argument("name")
    add("logout-all", cmd_logout_all, "end every remembered login").add_argument("name")
    add("reset-rating", cmd_reset_rating, "back to 1500 and unranked").add_argument("name")
    p = add("delete-user", cmd_delete_user, "delete an account")
    p.add_argument("name")
    p.add_argument("--yes", action="store_true")
    add("purge-guests", cmd_purge_guests, "delete old guest-only match records").add_argument(
        "--days", type=float, default=30)
    p = add("purge-inactive", cmd_purge_inactive, "delete accounts not seen for a long time")
    p.add_argument("--days", type=float, required=True)
    p.add_argument("--include-played", action="store_true")
    p.add_argument("--yes", action="store_true")
    p = add("matches", cmd_matches, "recent matches")
    p.add_argument("--player")
    p.add_argument("--limit", type=int, default=20)
    p = add("backup", cmd_backup, "back up the database now")
    p.add_argument("dir", nargs="?")
    p.add_argument("--keep", type=int, default=0, help="keep only the newest N backups (0 = all)")
    p = add("restore", cmd_restore, "restore a backup")
    p.add_argument("file")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force", action="store_true", help="even while the server runs")
    p = add("notice", cmd_notice, "show a message to every connected player")
    p.add_argument("text", nargs="*", help="the message (200 characters at most)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--minutes", type=float, help="how long it shows (default 60)")
    g.add_argument("--hours", type=float)
    g.add_argument("--clear", action="store_true", help="take the showing notice(s) down")
    p = add("notices", cmd_notices, "the latest notices")
    p.add_argument("--limit", type=int, default=10)
    p = add("gen-cert", cmd_gen_cert, "make a self-signed TLS certificate")
    p.add_argument("--dir", default=".")
    p.add_argument("--name", default="t5lobby", help="host name or address to put in it (informational)")
    p.add_argument("--days", type=int, default=3650)
    p.add_argument("--force", action="store_true", help="replace an existing one (players must re-pin)")
    p = add("fingerprint", cmd_fingerprint, "SHA-256 fingerprint of a certificate")
    p.add_argument("cert")
    p.add_argument("--plain", action="store_true", help="lowercase hex without colons")
    p = add("server-entry", cmd_server_entry, "print a servers.json entry")
    p.add_argument("--name", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--cert", help="self-signed certificate to pin")
    g.add_argument("--ca", action="store_true", help="certificate from a CA (Let's Encrypt)")
    g.add_argument("--plain", action="store_true", help="no TLS")
    p.add_argument("--region")
    p.add_argument("--note")
    a = ap.parse_args(argv)
    if getattr(a, "name", None) and a.cmd in ("ban", "unban", "user", "reset-password", "reset-rating",
                                               "delete-user", "recovery-codes", "logout-all") \
            and not valid_name(a.name):
        sys.exit(f"{a.name!r} is not a valid player name")
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
