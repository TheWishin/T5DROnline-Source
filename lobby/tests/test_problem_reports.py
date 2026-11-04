"""Problem reports sent from the launcher (server/reports.py, t5lobby/report_upload.py): the upload over a report
connection, the server's checks (size, layout, zip bombs, hash, limits), the folder, the Discord webhook and the admin
commands."""
import contextlib
import hashlib
import http.server
import io
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest
import zipfile

from util import ServerThread
from t5lobby import report_upload as up
from t5lobby.server import admin, reports


def make_zip(path, files=None):
    files = files if files is not None else {"contents.txt": "T5DR Online problem report\n",
                                             "system.txt": "Windows 11\n", "logs/game-1.log": "x" * 5000}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return path


META = {"game": "T5DR Online", "version": "1.2.1", "build_id": "abc123", "os": "Windows 11 (26300)",
        "description": "the game froze @everyone after the KO", "contact": "Player#1234", "name": "Tester",
        "name_kind": "guest"}


class Hook(http.server.BaseHTTPRequestHandler):
    """A Discord webhook stand-in: records every POST; .reply = status codes to answer in turn."""
    posts = []
    reply = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Hook.posts.append((self.headers["Content-Type"], body))
        code = Hook.reply.pop(0) if Hook.reply else 204
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


@contextlib.contextmanager
def hook_server():
    Hook.posts, Hook.reply = [], []
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Hook)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/api/webhooks/1/x"
    finally:
        httpd.shutdown()
        httpd.server_close()


class Base(unittest.TestCase):
    cfg = {}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5rep-")
        self.dir = os.path.join(self.tmp, "reports")
        self.st = ServerThread(report_dir=self.dir, **self.cfg).start()
        self.port = self.st.srv.port

    def tearDown(self):
        self.st.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def send(self, path, meta=META, **kw):
        return up.upload("127.0.0.1", self.port, path, meta, tls="off", **kw)

    def stored(self):
        return reports.ReportFolder(self.dir).all()


class UploadTest(Base):
    cfg = dict(report_per_address_day=50, report_per_name_day=50)

    def test_guest_without_login_sends_a_report(self):
        z = make_zip(os.path.join(self.tmp, "r.zip"))
        seen = []
        r = self.send(z, progress=lambda a, b: seen.append((a, b)))
        self.assertRegex(r["id"], r"^[A-Z0-9]{6}$")
        self.assertFalse(r["webhook"])
        rows = self.stored()
        self.assertEqual(len(rows), 1)
        meta, zpath = rows[0]
        with open(z, "rb") as f, open(zpath, "rb") as g:
            self.assertEqual(f.read(), g.read())
        self.assertEqual(meta["id"], r["id"])
        self.assertEqual(meta["version"], "1.2.1")
        self.assertEqual(meta["name"], "Tester")
        self.assertEqual(meta["name_kind"], "guest, as the launcher says")
        self.assertEqual(meta["files"], 3)
        self.assertIn(["logs/game-1.log", 5000], meta["members"])
        self.assertNotIn("ip", meta)
        self.assertEqual(seen[-1][0], os.path.getsize(z))
        self.assertTrue(os.path.basename(os.path.dirname(zpath))[:2] == "20")      # <dir>/<YYYY-MM-DD>/<id>.zip

    def test_server_says_it_takes_reports(self):
        self.assertEqual(up.server_takes_reports("127.0.0.1", self.port, tls="off"), 15360 * 1024)

    def test_report_connection_cannot_log_in(self):
        s = socket.create_connection(("127.0.0.1", self.port), 5)
        f = s.makefile("rb")
        s.sendall(b'{"t":"hello","proto":1,"purpose":"report","caps":["problem_reports"],"rid":1}\n'
                  b'{"t":"login","mode":"guest","name":"Sneaky","rid":2}\n')
        replies = [json.loads(f.readline()) for _ in range(2)]
        s.close()
        self.assertEqual(replies[0]["t"], "welcome")
        self.assertEqual(replies[1]["t"], "error")
        self.assertIn("cannot log in", replies[1]["msg"])

    def test_too_big_is_refused_before_sending(self):
        z = make_zip(os.path.join(self.tmp, "big.zip"),
                     {"contents.txt": "x", "desync/np_desync_1.bin": os.urandom(16 * 1024 * 1024)})
        with self.assertRaises(up.ReportError) as cm:
            self.send(z)
        self.assertEqual(cm.exception.code, "report_size")
        self.assertEqual(self.stored(), [])

    def test_layouts_that_are_refused(self):
        cases = {"no contents": {"system.txt": "x"},
                 "a path out": {"contents.txt": "x", "../evil.txt": "x"},
                 "absolute": {"contents.txt": "x", "/etc/passwd.txt": "x"},
                 "an exe": {"contents.txt": "x", "run.exe": "MZ"},
                 "a folder entry": {"contents.txt": "x", "logs/": ""}}
        for why, files in cases.items():
            with self.subTest(why):
                z = make_zip(os.path.join(self.tmp, "bad.zip"), files)
                with self.assertRaises(up.ReportError) as cm:
                    self.send(z)
                self.assertEqual(cm.exception.code, "report_bad")
        not_zip = os.path.join(self.tmp, "nz.zip")
        with open(not_zip, "wb") as f:
            f.write(b"PK" + os.urandom(500))
        with self.assertRaises(up.ReportError) as cm:
            self.send(not_zip)
        self.assertEqual(cm.exception.code, "report_bad")
        self.assertEqual(self.stored(), [])

    def test_damaged_upload_is_refused(self):
        z = make_zip(os.path.join(self.tmp, "r.zip"))
        with open(z, "rb") as f:
            data = f.read()
        s = socket.create_connection(("127.0.0.1", self.port), 5)
        fr = s.makefile("rb")
        s.sendall(b'{"t":"hello","proto":1,"purpose":"report","caps":["problem_reports"],"rid":1}\n')
        fr.readline()
        s.sendall(json.dumps({"t": "report_begin", "rid": 2, "size": len(data),
                              "sha256": hashlib.sha256(b"other").hexdigest()}).encode() + b"\n")
        go = json.loads(fr.readline())
        s.sendall(json.dumps({"t": "report_data", "id": go["id"], "rid": 3}).encode() + b"\n" + data)
        done = json.loads(fr.readline())
        s.close()
        self.assertEqual(done["code"], "report_bad")
        self.assertEqual(self.stored(), [])

    def test_upload_that_breaks_off_stores_nothing_and_the_server_goes_on(self):
        z = make_zip(os.path.join(self.tmp, "r.zip"))
        with open(z, "rb") as f:
            data = f.read()
        s = socket.create_connection(("127.0.0.1", self.port), 5)
        fr = s.makefile("rb")
        s.sendall(b'{"t":"hello","proto":1,"purpose":"report","caps":["problem_reports"],"rid":1}\n')
        fr.readline()
        s.sendall(json.dumps({"t": "report_begin", "rid": 2, "size": len(data),
                              "sha256": hashlib.sha256(data).hexdigest()}).encode() + b"\n")
        go = json.loads(fr.readline())
        self.assertEqual(go["t"], "report_go", go)
        s.sendall(json.dumps({"t": "report_data", "id": go["id"], "rid": 3}).encode() + b"\n" + data[:100])
        s.shutdown(socket.SHUT_WR)          # (a FIN: a close with data unread on Windows is a reset, the line lost)
        s.settimeout(10)
        while s.recv(4096):
            pass
        s.close()
        self.assertTrue(self.st.wait_for(lambda: self.st.srv.counters.get("reports_broken", 0) == 1))
        self.assertEqual(self.stored(), [])
        self.send(make_zip(os.path.join(self.tmp, "r2.zip")))
        self.assertEqual(len(self.stored()), 1)

    def test_a_line_alone_cannot_carry_a_report(self):
        """The 8 KB line limit holds for everything but the counted bytes after report_data."""
        s = socket.create_connection(("127.0.0.1", self.port), 5)
        fr = s.makefile("rb")
        s.sendall(b'{"t":"hello","proto":1,"purpose":"report","caps":["problem_reports"],"rid":1}\n')
        fr.readline()
        s.sendall(b'{"t":"report_data","id":"AAAAAA","rid":2}\n')
        reply = json.loads(fr.readline())
        s.close()
        self.assertEqual(reply["code"], "bad_state")


class LimitTest(Base):
    cfg = dict(report_per_address_day=2, report_total_mb=0)

    def test_per_address_limit(self):
        z = make_zip(os.path.join(self.tmp, "r.zip"))
        self.send(z)
        self.send(z, meta=dict(META, name="Other"))
        with self.assertRaises(up.ReportError) as cm:
            self.send(z, meta=dict(META, name="Third"))
        self.assertEqual(cm.exception.code, "rate_limited")
        self.assertGreater(cm.exception.retry, 0)
        self.assertEqual(len(self.stored()), 2)


class NameLimitTest(Base):
    cfg = dict(report_per_name_day=1)

    def test_per_name_limit(self):
        z = make_zip(os.path.join(self.tmp, "r.zip"))
        self.send(z)
        with self.assertRaises(up.ReportError) as cm:
            self.send(z, meta=dict(META, name="tester"))          # (the same name: case and punctuation do not count)
        self.assertEqual(cm.exception.code, "rate_limited")


class OffTest(unittest.TestCase):
    def test_an_older_or_switched_off_server(self):
        st = ServerThread(reports=False).start()
        try:
            self.assertEqual(up.server_takes_reports("127.0.0.1", st.srv.port, tls="off"), 0)
            with tempfile.TemporaryDirectory() as d:
                z = make_zip(os.path.join(d, "r.zip"))
                with self.assertRaises(up.ReportError) as cm:
                    up.upload("127.0.0.1", st.srv.port, z, META, tls="off")
            self.assertEqual(cm.exception.code, "unsupported")
        finally:
            st.stop()

    def test_in_memory_database_without_a_folder_is_off(self):
        st = ServerThread().start()          # (tests: db ":memory:", no T5L_REPORT_DIR)
        try:
            self.assertFalse(st.srv.reports_on())
        finally:
            st.stop()


class WebhookTest(Base):
    def setUp(self):
        self._hook = hook_server()
        self.url = self._hook.__enter__()
        self.cfg = dict(report_webhook=self.url)
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self._hook.__exit__(None, None, None)

    def test_posted_with_the_zip(self):
        z = make_zip(os.path.join(self.tmp, "r.zip"))
        r = self.send(z)
        self.assertTrue(r["webhook"])
        self.assertTrue(self.st.wait_for(lambda: self.st.srv.counters.get("reports_posted", 0) == 1))
        ctype, body = Hook.posts[0]
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        with open(z, "rb") as f:
            self.assertIn(f.read(), body)
        self.assertIn(f'filename="{r["id"]}.zip"'.encode(), body)
        payload = json.loads(body.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        text = payload["content"]
        for want in (f"#{r['id']}", "T5DR Online 1.2.1", "abc123", "Windows 11", "Tester", "Player#1234",
                     "the game froze"):
            self.assertIn(want, text)
        self.assertLessEqual(len(text), 2000)
        self.assertTrue(self.st.wait_for(lambda: self.stored()[0][0]["webhook"] == "posted with the zip"))

    def test_too_big_for_discord_goes_without_the_file(self):
        Hook.reply = [413, 204]
        z = make_zip(os.path.join(self.tmp, "r.zip"))
        r = self.send(z)
        self.assertTrue(self.st.wait_for(lambda: self.st.srv.counters.get("reports_posted", 0) == 1))
        self.assertEqual(len(Hook.posts), 2)
        self.assertNotIn(b"application/zip", Hook.posts[1][1])
        self.assertIn(f"reports get {r['id']}".encode(), Hook.posts[1][1])
        self.assertTrue(self.st.wait_for(lambda: self.stored()[0][0]["webhook"] == "posted without the zip"))

    def test_webhook_down_keeps_the_report(self):
        Hook.reply = [500]
        self.send(make_zip(os.path.join(self.tmp, "r.zip")))
        self.assertTrue(self.st.wait_for(lambda: self.st.srv.counters.get("reports_post_failed", 0) == 1))
        self.assertEqual(self.stored()[0][0]["webhook"], "failed: HTTP 500")


class CheckZipTest(unittest.TestCase):
    def _zip(self, files):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            for n, d in files.items():
                z.writestr(n, d)
        return b.getvalue()

    def test_real_report_names(self):
        names = ["contents.txt", "system.txt", "report.txt", "launcher.log", "launcher.log.1", "build.log",
                 "controls.ini", "logs/game-20261104-101010.log", "logs/x_frames.log", "compile/ppu_recomp_007.log",
                 "online/lobby-summary.txt", "online/ctl/cmd.json", "replay/s-1.t5replay", "desync/np_desync_1.bin"]
        got = reports.check_zip(self._zip({n: "x" for n in names}))
        self.assertEqual([n for n, _s in got], names)

    def test_member_that_lies_about_its_size(self):
        data = bytearray(self._zip({"contents.txt": "x", "a.log": "A" * 100000}))
        cd = data.rfind(b"PK\x01\x02")                      # the last central directory entry (a.log)
        data[cd + 24:cd + 28] = (1000).to_bytes(4, "little")   # says 1000 bytes unpacked
        with self.assertRaises(ValueError):
            reports.check_zip(bytes(data))

    def test_ratio_and_totals(self):
        bomb = self._zip({"contents.txt": "x", "a.log": b"\0" * (33 << 20)})
        with self.assertRaises(ValueError):
            reports.check_zip(bomb)
        with self.assertRaises(ValueError):
            reports.check_zip(self._zip({f"f{i}.log": "x" for i in range(201)} | {"contents.txt": "x"}))


class FolderAndAdminTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5rep-")
        self.f = reports.ReportFolder(os.path.join(self.tmp, "reports"))
        self.zip = make_zip(os.path.join(self.tmp, "r.zip"))
        with open(self.zip, "rb") as fh:
            self.data = fh.read()
        self.env = {"T5L_REPORT_DIR": os.path.join(self.tmp, "reports"), "T5L_DB": os.path.join(self.tmp, "x.db")}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _store(self, rid, age_days=0.0):
        return self.f.store(rid, self.data, dict(META, id=rid, time=time.time() - age_days * 86400, size=len(self.data),
                                                 files=3, members=[["contents.txt", 27]]),
                            now=time.time() - age_days * 86400)

    def test_prune_oldest_first(self):
        self._store("AAAAAA", 200)
        self._store("BBBBBB", 3)
        self._store("CCCCCC", 1)
        self._store("DDDDDD", 0)
        gone = self.f.prune(total_bytes=2 * len(self.data), keep_days=120)
        self.assertEqual(gone, ["AAAAAA", "BBBBBB"])                # past 120 days, then the oldest over the cap
        self.assertEqual([m["id"] for m, _z in self.f.all()], ["CCCCCC", "DDDDDD"])

    def _admin(self, *args):
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(out):
            code = admin.main(list(args))
        return code, out.getvalue()

    def test_admin_commands(self):
        self._store("K7QF2M")
        code, out = self._admin("reports")
        self.assertEqual(code, 0)
        self.assertIn("#K7QF2M", out)
        self.assertIn("Tester", out)
        code, out = self._admin("reports", "show", "k7qf2m")
        self.assertIn("the game froze", out)
        self.assertIn("contents.txt", out)
        dest = os.path.join(self.tmp, "got")
        code, out = self._admin("reports", "get", "K7QF2M", "--out", dest)
        with open(os.path.join(dest, "report-K7QF2M.zip"), "rb") as fh:
            self.assertEqual(fh.read(), self.data)
        code, out = self._admin("reports", "delete", "#K7QF2M")
        self.assertEqual(self.f.all(), [])
        with self.assertRaises(SystemExit):
            self._admin("reports", "show", "../../etc")

    def test_admin_send_again(self):
        self._store("K7QF2M")
        with hook_server() as url:
            self.env["T5L_REPORT_WEBHOOK"] = url
            code, out = self._admin("reports", "send", "K7QF2M")
        self.assertEqual(code, 0)
        self.assertIn("posted with the zip", out)
        self.assertEqual(self.f.find("K7QF2M")[0]["webhook"], "posted with the zip")

    def test_webhook_text_never_too_long(self):
        t = reports.webhook_text(dict(META, id="X", description="d" * 3000), False)
        self.assertLessEqual(len(t), 2000)
        self.assertIn("too big to attach", t)

    def test_only_https_or_this_machine(self):
        self.assertTrue(reports.webhook_url_ok("https://discord.com/api/webhooks/1/abc"))
        self.assertTrue(reports.webhook_url_ok("http://127.0.0.1:9/x"))
        self.assertFalse(reports.webhook_url_ok("http://example.com/x"))
        self.assertFalse(reports.webhook_url_ok("file:///etc/passwd"))


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
