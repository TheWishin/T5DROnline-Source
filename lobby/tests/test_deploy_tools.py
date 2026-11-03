"""The central-server update tools (docs/DEPLOY_1.2.0.md "Central server: the update"):

- lobby/tools/lobby_test_db.py: digest/compare see every lost or changed row, allow added tables and columns
  (a migration), and the current Store's own migration of an older-looking database passes `compare`
- lobby/deploy/linux/t5dr_deploy_remote.sh: the steps it offers, the safety rules in its text (a code rollback
  keeps the database, the install runs under umask 022, T4 stopped for the migration and started after it, never
  `release`, the firewall or the TCP 443 listener), bash syntax
- tools/deploy_lobby.sh --dry-run: the archive, the copy, the checksum, the unpack and the remote step, nothing run

The whole sequence with real servers (staged machine, old + new code, T4 sharing the accounts, old and new
launchers): lobby/tools/deploy_rehearsal.py (minutes; not a unit test).
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import util  # noqa: F401  (path setup)
from test_hosting import git_bash
from t5lobby.server.store import SCHEMA_VERSION, Store, hash_password

LOBBY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(LOBBY)
TOOLS = os.path.join(LOBBY, "tools")
sys.path.insert(0, TOOLS)
import lobby_test_db  # noqa: E402

REMOTE = os.path.join(LOBBY, "deploy", "linux", "t5dr_deploy_remote.sh")
PC = os.path.join(REPO, "tools", "deploy_lobby.sh")


def posix(path):
    path = os.path.abspath(path).replace("\\", "/")
    return "/" + path[0].lower() + path[2:] if os.name == "nt" and path[1:2] == ":" else path


class DigestCompare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="deploytools-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = os.path.join(self.tmp, "t5.db")
        st = Store(self.db)
        for i in range(5):
            st.create_account(f"Dig{i}", hash_password("pw-dig", n=1 << 10))
        st.create_session(1)
        st.set_flag("release", "1.1.9")
        st.close()

    def digest(self, path):
        d = lobby_test_db.digest_db(path)
        for t in d["tables"].values():
            t.pop("_rows", None)
            t.pop("all_columns", None)
        out = os.path.join(self.tmp, "before.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(d, f)
        return out

    def compare(self, before, *extra):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lobby_test_db.main(["compare", before, self.db, *extra])
        return code, buf.getvalue()

    def test_unchanged_and_volatile_flags(self):
        before = self.digest(self.db)
        db = sqlite3.connect(self.db)
        db.execute("UPDATE kv SET value = '1.2.0' WHERE key = 'release'")      # (admin release: not data)
        db.execute("INSERT OR REPLACE INTO kv (key, value, updated) VALUES ('drain', NULL, 0)")
        db.commit()
        db.close()
        code, out = self.compare(before)
        self.assertEqual(code, 0, out)
        self.assertIn("data unchanged", out)

    def test_added_tables_and_columns_are_a_migration_not_a_loss(self):
        before = self.digest(self.db)
        db = sqlite3.connect(self.db)
        db.execute("ALTER TABLE accounts ADD COLUMN extra_120 TEXT NOT NULL DEFAULT ''")
        db.execute("CREATE TABLE new_120 (x INTEGER)")
        db.commit()
        db.close()
        code, out = self.compare(before)
        self.assertEqual(code, 0, out)
        self.assertIn("tables added: new_120", out)
        self.assertIn("columns added to accounts: extra_120", out)

    def test_changed_lost_or_dropped_data_is_found(self):
        for sql, words in (("UPDATE accounts SET rating = 1234 WHERE id = 2", "accounts: rows changed"),
                           ("DELETE FROM sessions", "sessions: rows changed"),
                           ("DROP TABLE blocks", "table blocks is gone"),
                           ("ALTER TABLE accounts DROP COLUMN ban_reason", "columns gone: ban_reason")):
            with self.subTest(sql=sql):
                self.setUp()
                before = self.digest(self.db)
                db = sqlite3.connect(self.db)
                db.execute(sql)
                db.commit()
                db.close()
                code, out = self.compare(before)
                self.assertEqual(code, 1, out)
                self.assertIn(words, out)
                self.assertIn("DATA CHANGED", out)

    def test_grow_allows_a_database_that_kept_running(self):
        before = self.digest(self.db)
        st = Store(self.db)
        st.create_account("Later", hash_password("pw-later", n=1 << 10))
        st.close()
        self.assertEqual(self.compare(before)[0], 1)
        self.assertEqual(self.compare(before, "--grow")[0], 0)

    def test_this_stores_migration_of_an_older_schema_keeps_every_row(self):
        """An older-looking database (no badge column, schema SCHEMA_VERSION - 1) migrated by this Store."""
        if SCHEMA_VERSION < 2:
            self.skipTest("no migration after schema 1")
        db = sqlite3.connect(self.db, isolation_level=None)
        db.execute("ALTER TABLE accounts DROP COLUMN badge")
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION - 1}")
        db.close()
        before = self.digest(self.db)
        st = Store(self.db)
        self.assertEqual(st.migrated, [SCHEMA_VERSION])
        st.close()
        code, out = self.compare(before)
        self.assertEqual(code, 0, out)
        self.assertIn("badge", out)


class RemoteScript(unittest.TestCase):
    def setUp(self):
        with open(REMOTE, encoding="utf-8") as f:
            self.text = f.read()

    def test_lf_and_steps(self):
        with open(REMOTE, "rb") as f:
            self.assertNotIn(b"\r\n", f.read())
        for step in ("check)", "precheck)", "notice)", "deploy)", "verify)", "rollback)"):
            self.assertIn("    " + step, self.text)

    @unittest.skipUnless(git_bash(), "needs bash")
    def test_bash_syntax_and_help(self):
        for path in (REMOTE, PC):
            r = subprocess.run([git_bash(), "-n", posix(path)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([git_bash(), posix(REMOTE)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("rollback [DIR]", r.stdout)

    def test_safety_rules(self):
        t = self.text
        code = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
        # the install never runs under the backups' umask 077 (code folders unreadable for the service user)
        install = code[code.index("run_install() {"):code.index("restore_code() {")]
        self.assertLess(install.index("umask 022"), install.index("install.sh"))
        # T4 stopped before the install, started after T5DR's checks
        deploy = code[code.index("do_deploy() {"):code.index("do_rollback() {")]
        self.assertLess(deploy.index("systemctl stop t4lobby"), deploy.index('run_install "$LOBBY"'))
        self.assertLess(deploy.index('verify_t5 "$started"'), deploy.index("start_t4 yes"))
        # precheck before anything changes; a failed new code puts the old one back (database kept)
        self.assertLess(deploy.index("do_precheck"), deploy.index("drain_both"))
        self.assertIn('restore_code "$BACKUP"', deploy)
        # a code rollback never restores a database backup
        self.assertNotIn("admin restore", code)
        self.assertNotIn(" restore ", code.replace("restore_code", ""))
        # nothing the owner decides separately is ever run (only named in messages)
        import re
        run = [l for l in code.splitlines() if "echo " not in l and "die " not in l]
        for pattern in (r"-admin\s+release\b", r"(^|[;&|]\s*)(ufw|nft|setcap)\b", r"tcp443\.conf",
                        r"T5L_TCP_FALLBACK_PORT=\d"):
            bad = [l for l in run if re.search(pattern, l.strip())]
            self.assertEqual(bad, [], f"{pattern} run by the deploy script")


@unittest.skipUnless(git_bash(), "needs bash")
class PcScriptDryRun(unittest.TestCase):
    def run_pc(self, *args, env=None):
        e = dict(os.environ, **(env or {}))
        return subprocess.run([git_bash(), posix(PC), "--dry-run", *args], capture_output=True, text=True, env=e,
                              cwd=REPO)

    def test_upload_and_steps(self):
        r = self.run_pc("1.2.0", "upload", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("core.autocrlf=false archive", out)
        self.assertIn("lobby_1.2.0.tgz", out)
        self.assertIn("root@46.224.146.6:/opt/src/lobby_1.2.0.tgz", out)
        self.assertIn("sha256sum -c", out)
        self.assertIn("StrictHostKeyChecking=yes", out)
        r = self.run_pc("1.2.0", "deploy", "--drain-wait", "900")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/opt/src/t5dr-lobby-1.2.0/lobby/deploy/linux/t5dr_deploy_remote.sh deploy --drain-wait 900",
                      r.stdout)
        r = self.run_pc("1.2.0", "notice", "15", "Server update at 21:00")
        self.assertIn("notice 15 Server\\ update\\ at\\ 21:00", r.stdout)

    def test_refusals(self):
        self.assertNotEqual(self.run_pc("1.2", "check").returncode, 0)
        self.assertNotEqual(self.run_pc("1.2.0", "release").returncode, 0)
        self.assertNotEqual(self.run_pc("1.2.0", "upload", "no-such-ref-xyz").returncode, 0)


if __name__ == "__main__":
    unittest.main()
