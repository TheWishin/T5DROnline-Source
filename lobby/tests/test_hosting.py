"""Hosting and operations: admin tool, bans, backups, status endpoint, lobby deltas, the
pure-Python self-signed certificate (cross-checked with openssl when present) and certificate
reload, servers.json, "Host for friends", and UPnP / NAT-PMP port mapping against fake routers
on 127.0.0.1 (the real router is never contacted)."""
import contextlib
import http.server
import io
import json
import os
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

import util
from util import BUILD, ServerThread, client, expect
from t5lobby import portmap, proto, servers
from t5lobby.proto import LobbyError
from t5lobby.server import admin, backup, selfsigned
from t5lobby.server.store import SCHEMA, Store

LOBBY = os.path.dirname(util.HERE)


def run_admin(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            rc = admin.main(list(args))
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (print(e.code) or 1)
    return rc, out.getvalue()


def find_openssl():
    exe = shutil.which("openssl")
    if exe:
        return exe
    for p in (r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if os.path.exists(p):
            return p
    return None


def fetch(url):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5) as r:
        return r.status, r.read().decode()


class FileDbBase(unittest.TestCase):
    """A server on a database file (the admin tool works on the file)."""
    server_cfg = {}

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "t5lobby.db")
        cfg = dict(db=self.db, admin_poll=0.2, status_port=-1)
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        self.status = f"http://127.0.0.1:{self.s.srv.status_http.port}"
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def c(self, name=None, **kw):
        c = client(self.s, name, **kw)
        self.clients.append(c)
        return c

    def admin(self, *args):
        return run_admin("--db", self.db, "--status-url", self.status, *args)


# ============================================================================ admin tool + bans
class AdminTest(FileDbBase):
    def test_users_ban_kick_unban(self):
        a = self.c("Alice", password="secret1", register=True)
        rc, out = self.admin("users")
        self.assertEqual(rc, 0)
        self.assertIn("Alice", out)
        rc, out = self.admin("ban", "Alice", "--hours", "2", "--reason", "rage quitting")
        self.assertEqual(rc, 0, out)
        ev = expect(a, ("kicked", "disconnected"), timeout=5)     # the server noticed within admin_poll
        self.assertIn(ev["t"], ("kicked", "disconnected"))
        with self.assertRaises(LobbyError) as e:
            self.c("Alice", password="secret1")
        self.assertEqual(e.exception.code, proto.E_NOT_ALLOWED)
        self.assertIn("rage quitting", e.exception.msg)
        rc, out = self.admin("bans")
        self.assertIn("Alice", out)
        self.admin("unban", "Alice")
        self.c("Alice", password="secret1")                      # works again

    def test_wrong_password_never_reveals_a_ban(self):
        self.c("Alice", password="secret1", register=True).close()
        self.admin("ban", "Alice")
        with self.assertRaises(LobbyError) as e:
            self.c("Alice", password="wrong-pw")
        self.assertEqual(e.exception.code, proto.E_AUTH)

    def test_reset_password_and_rating_delete(self):
        self.c("Bob", password="oldpass", register=True).close()
        os.environ["T5L_TEST_NEWPW"] = "newpass123"
        try:
            rc, out = self.admin("reset-password", "Bob", "--password-env", "T5L_TEST_NEWPW")
        finally:
            del os.environ["T5L_TEST_NEWPW"]
        self.assertEqual(rc, 0, out)
        with self.assertRaises(LobbyError):
            self.c("Bob", password="oldpass")
        self.c("Bob", password="newpass123").close()
        rc, out = self.admin("reset-password", "Bob")            # random one, printed once
        pw = out.split("new password: ")[1].split()[0]
        self.c("Bob", password=pw).close()
        st = Store(self.db)
        st.db.execute("UPDATE accounts SET rating = 1900 WHERE name = 'Bob'")
        st.close()
        self.admin("reset-rating", "Bob")
        self.assertEqual(Store(self.db).account("Bob")["rating"], 1500)
        rc, out = self.admin("delete-user", "Bob")
        self.assertNotEqual(rc, 0)                                # needs --yes
        self.admin("delete-user", "Bob", "--yes")
        self.assertIsNone(Store(self.db).account("Bob"))

    def test_ip_ban(self):
        self.c("Carol")
        rc, out = self.admin("ban-ip", "127.0.0.0/8", "--days", "1")
        self.assertEqual(rc, 0, out)
        time.sleep(0.6)
        with self.assertRaises(LobbyError):
            self.c("Dave")
        self.assertTrue(self.s.wait_for(lambda: not any(p.online for p in self.s.srv.players.values()), 5))
        self.admin("unban-ip", "127.0.0.1/8")                     # normalised to 127.0.0.0/8
        time.sleep(0.6)
        self.c("Dave")

    def test_purges(self):
        now = time.time()
        st = Store(self.db)
        st.save_match({"id": "mold", "created": now - 90 * 86400, "ranked": False, "p1_name": "g1",
                       "p2_name": "g2", "status": "confirmed"})
        st.save_match({"id": "mnew", "created": now, "ranked": False, "p1_name": "g1", "p2_name": "g2",
                       "status": "confirmed"})
        st.create_account("Ghost", "x")
        st.db.execute("UPDATE accounts SET created = ?, last_seen = ? WHERE name = 'Ghost'",
                      (now - 400 * 86400, now - 400 * 86400))
        st.close()
        rc, out = self.admin("purge-guests", "--days", "30")
        self.assertIn("deleted 1", out)
        rc, out = self.admin("purge-inactive", "--days", "365", "--yes")
        self.assertIn("deleted 1", out)
        rc, out = self.admin("matches")
        self.assertIn("mnew", out)
        self.assertNotIn("mold", out)

    def test_reserved_names(self):
        x = self.c()
        for name in ("Admin", "Moderator7", "T5Lobby"):
            with self.assertRaises(LobbyError) as e:
                x.login_guest(name)
            self.assertEqual(e.exception.code, proto.E_BAD_NAME)
        x.login_guest("Kazuya")

    def test_recovery_codes_and_logout_all(self):
        a = self.c()
        a.register("Rita", "ritapw12", remember=True)
        aid = Store(self.db).account("Rita")["id"]
        self.assertEqual(Store(self.db).session_count(aid), 1)
        rc, out = self.admin("logout-all", "Rita")
        self.assertIn("ended 1", out)
        self.assertEqual(Store(self.db).session_count(aid), 0)
        rc, out = self.admin("recovery-codes", "Rita")
        self.assertEqual(rc, 0, out)
        codes = [line.strip() for line in out.splitlines()[1:] if line.strip()]
        self.assertEqual(len(codes), 8)
        self.assertTrue(Store(self.db).use_recovery_code(aid, codes[0]))
        rc, out = self.admin("user", "Rita")
        self.assertIn("7 recovery codes left", out)

    def test_ban_ends_a_saved_login(self):
        a = self.c()
        a.register("Sam", "sampw123", remember=True)
        token = a.session
        a.close()
        self.admin("ban", "Sam", "--days", "1")
        b = self.c()
        with self.assertRaises(LobbyError):
            b.login_session(token)

    def test_missing_db_is_an_error_not_a_new_file(self):
        p = os.path.join(self.dir, "nope.db")
        rc, out = run_admin("--db", p, "users")
        self.assertNotEqual(rc, 0)
        self.assertFalse(os.path.exists(p))


class BlocklistTest(unittest.TestCase):
    def test_blocklist_file(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "names.txt")
        with open(p, "w") as f:
            f.write("# comment\nbadword\n")
        s = ServerThread(name_blocklist=p).start()
        try:
            x = client(s)
            with self.assertRaises(LobbyError):
                x.login_guest("Mr Bad-Word")       # punctuation and case do not help
            x.login_guest("Goodword")
            x.close()
        finally:
            s.stop()


# ============================================================================ status endpoint
class StatusTest(FileDbBase):
    def test_health_status_metrics(self):
        a = self.c("Alice", auto_ready=True)
        b = self.c("Bob", auto_ready=True)
        a.quick_match()
        b.quick_match()
        expect(a, "match_start")
        expect(b, "match_start")
        code, body = fetch(self.status + "/health")
        self.assertEqual((code, body), (200, "ok\n"))
        st = json.loads(fetch(self.status + "/status")[1])
        self.assertEqual(st["players"]["online"], 2)
        self.assertEqual(st["players"]["playing"], 2)
        self.assertEqual(st["matches"]["running"], 1)
        self.assertEqual(st["counters"]["matches_lan"] + st["counters"]["matches_direct"], 1)
        self.assertEqual(st["db"]["matches_24h"], 1)
        self.assertNotIn("Alice", json.dumps(st))                 # no names, no addresses
        self.assertIsNotNone(st["process"]["rss_mb"])
        metrics = fetch(self.status + "/metrics")[1]
        self.assertIn("t5lobby_players_online 2", metrics)
        self.assertIn("t5lobby_matches_found_total 1", metrics)
        rc, out = self.admin("status")
        self.assertEqual(rc, 0, out)
        self.assertIn("2 online", out)
        self.assertEqual(self.admin("health", "-q")[0], 0)

    def test_health_fails_when_down(self):
        rc, _ = run_admin("--status-url", "http://127.0.0.1:9/", "health", "-q", "--timeout", "1")
        self.assertEqual(rc, 1)

    def test_status_endpoint_ignores_garbage(self):
        s = socket.create_connection(("127.0.0.1", self.s.srv.status_http.port))
        s.sendall(b"POST /status HTTP/1.0\r\n\r\n")
        self.assertIn(b"405", s.recv(1000))
        s.close()


# ============================================================================ backup / restore
class BackupTest(FileDbBase):
    server_cfg = {}

    def test_backup_while_running_and_restore(self):
        self.c("Alice", password="secret1", register=True)
        bdir = os.path.join(self.dir, "b")
        rc, out = self.admin("backup", bdir)
        self.assertEqual(rc, 0, out)
        files = backup.list_backups(bdir)
        self.assertEqual(len(files), 1)
        self.assertEqual(backup.verify(files[0])["accounts"], 1)
        self.c("Bob", password="secret2", register=True)          # changes after the backup
        rc, out = self.admin("restore", files[0], "--yes")
        self.assertNotEqual(rc, 0)                                 # refused: the server runs
        self.assertIn("running", out)
        for c in self.clients:
            c.close()
        self.clients = []
        self.s.stop()
        try:
            rc, out = self.admin("restore", files[0], "--yes")
            self.assertEqual(rc, 0, out)
            st = Store(self.db)
            self.assertIsNotNone(st.account("Alice"))
            self.assertIsNone(st.account("Bob"))                   # back to the backup
            st.close()
            safety = [f for f in os.listdir(self.dir) if f.startswith("pre-restore-")]
            self.assertEqual(len(safety), 1)                       # the replaced database was kept
        finally:
            self.s = ServerThread(db=self.db, status_port=0).start()

    def test_keep_and_scheduled_backup(self):
        bdir = os.path.join(self.dir, "auto")
        for _ in range(4):
            backup.backup_db(self.db, bdir, keep=3)
        self.assertEqual(len(backup.list_backups(bdir)), 3)
        self.s.stop()
        self.s = ServerThread(db=self.db, backup_dir=os.path.join(self.dir, "sched"), backup_hours=0.0001,
                              status_port=0).start()
        self.assertTrue(self.s.wait_for(lambda: len(backup.list_backups(os.path.join(self.dir, "sched"))) >= 1,
                                        timeout=12))

    def test_restore_refuses_garbage(self):
        bad = os.path.join(self.dir, "bad.db")
        with open(bad, "wb") as f:
            f.write(b"not sqlite" * 100)
        rc, out = self.admin("restore", bad, "--yes", "--force")
        self.assertNotEqual(rc, 0)


class MigrationTest(unittest.TestCase):
    def test_old_database_is_upgraded(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "old.db")
        conn = sqlite3.connect(p)
        conn.executescript(SCHEMA)          # the schema as shipped before bans existed
        conn.execute("INSERT INTO accounts (name, pw, created, rating, rd, vol) VALUES ('Old', 'x', 1, 1500, 350, 0.06)")
        conn.commit()
        conn.close()
        st = Store(p)
        cols = {r["name"] for r in st.db.execute("PRAGMA table_info(accounts)")}
        self.assertTrue({"banned_until", "ban_reason", "tier"} <= cols)
        self.assertIsNone(st.ban_state(st.account("Old")))
        st.ban_account("Old", time.time() + 60, "test")
        self.assertIsNotNone(st.ban_state(st.account("Old")))
        st.close()
        Store(p).close()                    # idempotent


# ============================================================================ lobby deltas
class DeltaTest(unittest.TestCase):
    def setUp(self):
        self.s = ServerThread(max_per_ip=64, conn_burst=64).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name):
        c = client(self.s, name)
        self.clients.append(c)
        return c

    def test_merged_view_matches_server(self):
        a = self.c("Alice")
        others = [self.c(f"Pal{i}") for i in range(5)]
        others[0].create_room("one")
        others[1].close()
        others[2].create_room("two")
        others[2].leave_room()
        others[3].chat("hi")
        time.sleep(1.5)            # only broadcasts (a full list at login, then deltas) reach `a`
        want = self.s.call(lambda: sorted(p["name"] for p in self.s.srv._snapshot(full=True)["players"]))
        got = sorted(p["name"] for p in a.players)
        self.assertEqual(got, want)
        self.assertEqual([r["name"] for r in a.rooms], ["one"])
        self.assertEqual(self.s.call(lambda: self.s.srv.conns and min(
            "delta" in c.caps for c in self.s.srv.conns)), True)

    def test_legacy_client_gets_whole_lists(self):
        raw = socket.create_connection(("127.0.0.1", self.s.srv.port))
        f = raw.makefile("rwb")
        for m in ({"t": "hello", "proto": 1, "build": BUILD.as_wire()}, {"t": "login", "mode": "guest", "name": "Old"}):
            f.write(proto.encode(m))
        f.flush()
        self.c("Newer").create_room("r")
        types = set()
        raw.settimeout(3)
        t_end = time.time() + 3
        while time.time() < t_end and "lobby_state" not in types:
            types.add(json.loads(f.readline())["t"])
        self.assertIn("lobby_state", types)
        self.assertNotIn("lobby_delta", types)
        raw.close()

    def test_delta_is_small(self):
        a = self.c("Alice")
        for i in range(30):
            self.c(f"Q{i:02d}")
        time.sleep(1.0)
        before = self.s.call(lambda: self.s.srv.counters["tcp_out_bytes"])
        self.clients[5].create_room("x")                          # one player's status changes
        time.sleep(1.0)
        sent = self.s.call(lambda: self.s.srv.counters["tcp_out_bytes"]) - before
        full = len(self.s.call(lambda: proto.encode(self.s.srv._snapshot(full=True))))
        self.assertLess(sent, full * 31 / 5)                      # whole lists to everybody would be 31x full
        self.assertEqual(len(a.players), 31)


# ============================================================================ certificates
class CertTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        t0 = time.monotonic()
        cls.cert, cls.key, cls.fp = selfsigned.write_pair(cls.dir, "lobby.example.org", days=30)
        cls.gen_s = time.monotonic() - t0

    def test_fast_enough(self):
        self.assertLess(self.gen_s, 30)

    def test_python_loads_it(self):
        import ssl
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(self.cert, self.key)                 # raises if key and certificate disagree
        self.assertEqual(len(self.fp), 64)

    @unittest.skipIf(find_openssl() is None, "openssl not found")
    def test_openssl_agrees(self):
        ossl = find_openssl()
        txt = subprocess.run([ossl, "x509", "-in", self.cert, "-noout", "-text"], capture_output=True, text=True,
                             check=True).stdout
        self.assertIn("sha256WithRSAEncryption", txt)
        self.assertIn("Public-Key: (2048 bit)", txt)
        self.assertIn("DNS:lobby.example.org", txt)
        self.assertIn("CA:TRUE", txt)
        ver = subprocess.run([ossl, "verify", "-check_ss_sig", "-CAfile", self.cert, self.cert], capture_output=True,
                             text=True)
        self.assertIn("OK", ver.stdout, ver.stderr)               # the self-signature checks out
        chk = subprocess.run([ossl, "rsa", "-in", self.key, "-check", "-noout"], capture_output=True, text=True)
        self.assertIn("RSA key ok", chk.stdout + chk.stderr)
        fp = subprocess.run([ossl, "x509", "-in", self.cert, "-noout", "-fingerprint", "-sha256"],
                            capture_output=True, text=True, check=True).stdout
        self.assertIn(selfsigned.pretty(self.fp), fp)

    def test_tls_with_it_and_reload(self):
        d = tempfile.mkdtemp()
        cert, key, fp1 = selfsigned.write_pair(d, "t5lobby")
        s = ServerThread(tls_cert=cert, tls_key=key).start()
        try:
            c = client(s, "Alice", tls_fingerprint=fp1)
            c.close()
            # a renewed certificate is picked up without a restart
            d2 = tempfile.mkdtemp()
            cert2, key2, fp2 = selfsigned.write_pair(d2, "t5lobby")
            time.sleep(0.05)
            shutil.copy(key2, key)
            shutil.copy(cert2, cert)
            self.assertTrue(s.call(lambda: s.srv.reload_tls(force=True)))
            c = client(s, "Bob", tls_fingerprint=fp2)
            c.close()
            with self.assertRaises(LobbyError) as e:
                client(s, "Carol", tls_fingerprint=fp1)
            self.assertEqual(e.exception.code, "tls_mismatch")
            # a broken pair is refused, the working certificate stays
            with open(cert, "w") as f:
                f.write("garbage")
            self.assertFalse(s.call(lambda: s.srv.reload_tls(force=True)))
            client(s, "Dave", tls_fingerprint=fp2).close()
        finally:
            s.stop()

    def test_admin_gen_cert_and_fingerprint(self):
        d = tempfile.mkdtemp()
        rc, out = run_admin("gen-cert", "--dir", d)
        self.assertEqual(rc, 0, out)
        rc, out2 = run_admin("gen-cert", "--dir", d)
        self.assertNotEqual(rc, 0)                                # never overwrites silently
        rc, fp = run_admin("fingerprint", os.path.join(d, "cert.pem"), "--plain")
        self.assertIn(selfsigned.pretty(fp.strip()), out)
        rc, entry = run_admin("server-entry", "--name", "Friends", "--host", "198.51.100.4",
                              "--cert", os.path.join(d, "cert.pem"))
        e = servers.ServerEntry.from_json(json.loads(entry))
        self.assertEqual((e.tls, e.fingerprint), ("pin", fp.strip()))


# ============================================================================ servers.json
class ServersTest(unittest.TestCase):
    def test_shipped_file_is_a_placeholder(self):
        entries, problems = servers.load()
        self.assertEqual(problems, [])
        self.assertEqual(entries, [])            # empty host: ignored until the owner fills it in
        with open(servers.shipped_path()) as f:
            self.assertEqual(json.load(f)["format"], servers.FORMAT)

    def test_merge_and_resolve(self):
        d = tempfile.mkdtemp()
        shipped = os.path.join(d, "shipped.json")
        with open(shipped, "w") as f:
            json.dump({"format": servers.FORMAT, "servers": [
                {"name": "Public", "host": "lobby.example.org", "tls": "ca", "default": True},
                {"name": "Broken", "host": "bad host!", "port": 7781},
                {"name": "Pinned", "host": "203.0.113.9", "port": 7790, "fingerprint": "AB:" * 31 + "AB"}]}, f)
        servers.save_user_entry(d, servers.ServerEntry("Friends", "198.51.100.7", 7781, "pin", "cd" * 32))
        entries, problems = servers.load(d, shipped)
        self.assertEqual([e.name for e in entries], ["Public", "Pinned", "Friends"])
        self.assertEqual(len(problems), 1)                         # the broken one, reported
        self.assertEqual(servers.default_entry(entries).name, "Public")
        kw = servers.resolve("Public", entries).client_kwargs()
        self.assertEqual(kw, {"server": "lobby.example.org:7781", "tls": True, "tls_fingerprint": None})
        pinned = servers.resolve("Pinned", entries)
        self.assertEqual((pinned.tls, pinned.fingerprint), ("pin", "ab" * 32))

    def test_typed_addresses(self):
        e = servers.parse_address("1.2.3.4")
        self.assertEqual((e.address, e.tls), ("1.2.3.4:7781", "off"))
        e = servers.parse_address("lobby.example.org:7000#" + "EF" * 32)
        self.assertEqual((e.address, e.tls, e.fingerprint), ("lobby.example.org:7000", "pin", "ef" * 32))
        self.assertEqual(servers.parse_address(e.share_string()).fingerprint, e.fingerprint)
        e = servers.parse_address("tls://lobby.example.org")
        self.assertEqual((e.address, e.tls), ("lobby.example.org:7781", "ca"))
        for bad in ("host:99999", "a b:1", "x:1#1234"):
            with self.assertRaises(ValueError):
                servers.parse_address(bad)


# ============================================================================ host for friends
class HostTest(unittest.TestCase):
    def test_host_mode_end_to_end(self):
        d = tempfile.mkdtemp()
        err = open(os.path.join(tempfile.mkdtemp(), "stderr.txt"), "w+")
        self.addCleanup(err.close)
        proc = subprocess.Popen([sys.executable, os.path.join(LOBBY, "run.py"), "host", "--data", d, "--port", "0",
                                 "--status-port", "0", "--json", "--stdin-control", "--map-dry-run"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)
        try:
            ready = None
            for line in proc.stdout:
                ev = json.loads(line)
                if ev["event"] == "ready":
                    ready = ev
                    break
            err.seek(0)
            self.assertIsNotNone(ready, err.read())
            self.assertEqual(ready["mapped"], [])                  # dry run: no mapping
            entry = servers.parse_address(ready["local"])
            self.assertEqual(entry.tls, "pin")
            c = util.LobbyClient(**dict(entry.client_kwargs(), build=BUILD))
            c.connect()
            me = c.login_guest("HostedGuest")
            self.assertEqual(me["name"], "HostedGuest")
            c.close()
            proc.stdin.write("stop\n")
            proc.stdin.flush()
            rest = [json.loads(x)["event"] for x in proc.stdout if x.startswith("{")]
            self.assertIn("stopped", rest)
            self.assertEqual(proc.wait(15), 0)
            for f in ("t5lobby.db", "host.json", os.path.join("tls", "cert.pem"), os.path.join("logs", "t5lobby.log")):
                self.assertTrue(os.path.exists(os.path.join(d, f)), f)
            with open(os.path.join(d, "logs", "t5lobby.log"), encoding="utf-8") as f:
                log = f.read()
            self.assertIn("[dry run]", log)
            self.assertIn("HostedGuest", log)
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_run_py_usage(self):
        r = subprocess.run([sys.executable, os.path.join(LOBBY, "run.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("run.py host", r.stdout)


# ============================================================================ port mapping (fakes)
class FakeNatPmp(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.maps = {}
        self.running = True

    def run(self):
        self.sock.settimeout(0.2)
        while self.running:
            try:
                data, src = self.sock.recvfrom(64)
            except (socket.timeout, OSError):
                continue
            if data[:2] == b"\x00\x00":
                self.sock.sendto(struct.pack("!BBHI4s", 0, 128, 0, 1, socket.inet_aton("203.0.113.50")), src)
            elif len(data) == 12 and data[1] in (1, 2):
                _v, op, _r, ip, ep, life = struct.unpack("!BBHHHI", data)
                key = ("UDP" if op == 1 else "TCP", ip)
                if life:
                    self.maps[key] = (ep, life)
                else:
                    self.maps.pop(key, None)
                self.sock.sendto(struct.pack("!BBHIHHI", 0, 128 + op, 0, 1, ip, ep, life), src)

    def stop(self):
        self.running = False
        self.sock.close()


class FakeIgd:
    """An SSDP responder and an IGD (description + SOAP control) on 127.0.0.1."""
    def __init__(self, location_host="127.0.0.1", permanent_only=False):
        outer = self
        self.calls = []
        self.permanent_only = permanent_only

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = (f'<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>'
                        f'<deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType><deviceList>'
                        f'<device><deviceList><device><serviceList><service>'
                        f'<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>'
                        f'<controlURL>/ctl/IPConn</controlURL></service></serviceList></device></deviceList>'
                        f'</device></deviceList></device></root>').encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                n = int(self.headers["Content-Length"])
                body = self.rfile.read(n).decode()
                action = self.headers["SOAPAction"].strip('"').split("#")[1]
                outer.calls.append((action, body))
                if action == "AddPortMapping" and outer.permanent_only and "<NewLeaseDuration>0<" not in body:
                    fault = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault>'
                             '<detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>725</errorCode>'
                             '<errorDescription>OnlyPermanentLeasesSupported</errorDescription></UPnPError>'
                             '</detail></s:Fault></s:Body></s:Envelope>').encode()
                    self.send_response(500)
                    self.send_header("Content-Length", str(len(fault)))
                    self.end_headers()
                    self.wfile.write(fault)
                    return
                extra = "<NewExternalIPAddress>203.0.113.77</NewExternalIPAddress>" \
                    if action == "GetExternalIPAddress" else ""
                out = (f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                       f'<u:{action}Response xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">{extra}'
                       f'</u:{action}Response></s:Body></s:Envelope>').encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.ssdp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ssdp.bind(("127.0.0.1", 0))
        self.ssdp_port = self.ssdp.getsockname()[1]
        self.location = f"http://{location_host}:{self.http.server_address[1]}/desc.xml"
        self.running = True
        threading.Thread(target=self._ssdp, daemon=True).start()

    def _ssdp(self):
        self.ssdp.settimeout(0.2)
        while self.running:
            try:
                data, src = self.ssdp.recvfrom(2048)
            except (socket.timeout, OSError):
                continue
            if data.startswith(b"M-SEARCH"):
                self.ssdp.sendto(f"HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=120\r\nLOCATION: {self.location}\r\n"
                                 f"ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n".encode(), src)

    def stop(self):
        self.running = False
        self.http.shutdown()
        self.ssdp.close()


class PortMapTest(unittest.TestCase):
    def test_natpmp(self):
        f = FakeNatPmp()
        f.start()
        try:
            m = portmap.PortMapper(gateway="127.0.0.1", local_ip="127.0.0.1", natpmp_port=f.port)
            self.assertTrue(m.discover())
            self.assertEqual(m.backend.name, "NAT-PMP")
            self.assertEqual(m.external_ip(), "203.0.113.50")
            m.add("TCP", 7781)
            m.add("UDP", 7781)
            m.add("UDP", 7782)
            self.assertEqual(set(f.maps), {("TCP", 7781), ("UDP", 7781), ("UDP", 7782)})
            self.assertEqual(f.maps[("UDP", 7782)], (7782, 3600))
            m.mappings[("TCP", 7781)] = (7781, 3600, time.monotonic() - 3000)     # past half the lease
            m.renew()
            m.remove_all()
            self.assertEqual(f.maps, {})
        finally:
            f.stop()

    def test_upnp(self):
        igd = FakeIgd()
        try:
            dev = portmap.Upnp.discover(timeout=2.0, ssdp_addr=("127.0.0.1", igd.ssdp_port))
            self.assertIsNotNone(dev)
            m = portmap.PortMapper(gateway="127.0.0.1", local_ip="192.168.1.20")
            m.backend = dev
            self.assertEqual(m.external_ip(), "203.0.113.77")
            m.add("UDP", 7781)
            add = [b for a, b in igd.calls if a == "AddPortMapping"][0]
            for frag in ("<NewExternalPort>7781<", "<NewProtocol>UDP<", "<NewInternalClient>192.168.1.20<",
                         "<NewLeaseDuration>3600<"):
                self.assertIn(frag, add)
            m.remove_all()
            self.assertEqual([a for a, _ in igd.calls][-1], "DeletePortMapping")
        finally:
            igd.stop()

    def test_upnp_permanent_only_router(self):
        igd = FakeIgd(permanent_only=True)
        try:
            dev = portmap.Upnp.discover(timeout=2.0, ssdp_addr=("127.0.0.1", igd.ssdp_port))
            m = portmap.PortMapper(local_ip="192.168.1.20")
            m.backend = dev
            m.add("TCP", 7781)
            self.assertEqual(m.mappings[("TCP", 7781)][1], 0)      # permanent: removed on stop
            m.remove_all()
            self.assertEqual([a for a, _ in igd.calls].count("DeletePortMapping"), 1)
        finally:
            igd.stop()

    def test_upnp_ignores_foreign_description_url(self):
        igd = FakeIgd(location_host="10.9.8.7")       # announced by 127.0.0.1, points elsewhere
        try:
            self.assertIsNone(portmap.Upnp.discover(timeout=1.0, ssdp_addr=("127.0.0.1", igd.ssdp_port)))
            self.assertEqual(igd.calls, [])
        finally:
            igd.stop()

    def test_dry_run_sends_nothing(self):
        real = socket.socket

        def no_network(*a, **k):
            raise AssertionError("dry run must not open sockets")
        socket.socket = no_network
        try:
            m = portmap.PortMapper(dry_run=True)
            self.assertFalse(m.discover())
            self.assertEqual(m.add("TCP", 7781), 7781)
            self.assertEqual(m.mappings, {})
        finally:
            socket.socket = real


if __name__ == "__main__":
    unittest.main()
