"""Database backups that are safe while the server runs (SQLite's online backup API).

A backup is a complete, checked SQLite file named t5lobby-YYYYmmdd-HHMMSS.db. The server makes one
every T5L_BACKUP_HOURS into T5L_BACKUP_DIR (keeping T5L_BACKUP_KEEP); the admin tool makes one on
demand (`backup`) and restores one (`restore`). Backups on the same disk do not survive losing the
machine: copy the folder elsewhere now and then (docs/HOSTING.md)."""
import glob
import os
import sqlite3
import time

PREFIX = "t5lobby-"


def _check(conn):
    ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        raise ValueError(f"integrity check failed: {ok}")
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if not {"accounts", "matches"} <= names:
        raise ValueError("not a t5lobby database (no accounts/matches tables)")


def backup_db(db_path, dest_dir, keep=14, prefix=PREFIX):
    """Copy the live database into dest_dir; returns the new file's path. Keeps the newest `keep`
    backups with this prefix (None = keep all)."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(db_path)
    os.makedirs(dest_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    final = os.path.join(dest_dir, f"{prefix}{stamp}.db")
    n = 1
    while os.path.exists(final):
        n += 1
        final = os.path.join(dest_dir, f"{prefix}{stamp}-{n}.db")
    tmp = final + ".part"
    src = sqlite3.connect(db_path, timeout=30)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst, pages=256, sleep=0.005)     # in steps: the server keeps writing meanwhile
            dst.execute("PRAGMA journal_mode=DELETE")    # one self-contained file
            _check(dst)
        finally:
            dst.close()
    finally:
        src.close()
    os.replace(tmp, final)
    if os.name != "nt":
        os.chmod(final, 0o600)            # password hashes inside
    if keep:
        for old in list_backups(dest_dir, prefix)[:-keep]:
            try:
                os.remove(old)
            except OSError:
                pass
    return final


def list_backups(dest_dir, prefix=PREFIX):
    """Backups in dest_dir, oldest first."""
    return sorted(p for p in glob.glob(os.path.join(dest_dir, prefix + "*.db")))


def newest_backup_time(dest_dir, prefix=PREFIX):
    files = list_backups(dest_dir, prefix)
    return os.path.getmtime(files[-1]) if files else 0.0


def verify(path):
    """Raise if `path` is not an intact t5lobby database."""
    conn = sqlite3.connect(f"file:{_uri_path(path)}?mode=ro", uri=True)
    try:
        _check(conn)
        return {"accounts": conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
                "matches": conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]}
    finally:
        conn.close()


def restore_db(backup_path, db_path, safety_dir=None):
    """Replace the database's content with a backup, through SQLite (so a running server's open
    connection stays valid). First saves the current database as pre-restore-*.db in safety_dir
    (default: next to it). Stop the server first anyway: it keeps players' ratings in memory.
    Returns (safety copy's path or None when there was no database yet, row counts of the backup)."""
    info = verify(backup_path)
    safety = None
    if os.path.isfile(db_path):
        safety = backup_db(db_path, safety_dir or os.path.dirname(os.path.abspath(db_path)), keep=None,
                           prefix="pre-restore-")
    src = sqlite3.connect(f"file:{_uri_path(backup_path)}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(db_path, timeout=30)
        try:
            src.backup(dst)
            _check(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return safety, info


def _uri_path(path):
    from urllib.request import pathname2url
    return pathname2url(os.path.abspath(path))
