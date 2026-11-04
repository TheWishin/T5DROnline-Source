"""'Send to the developer' in the report window (launcher/problem_report_ui.py, report_send.py): one click sends the
cleaned zip; an older server hides the button; a failure keeps Save. Then the whole way on this PC: the window's Send
-> a lobby server on 127.0.0.1 (lobby/t5lobby/server/reports.py) -> the stored zip and a webhook post with it.
No game, no internet: the server is local, the webhook a local stand-in."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import problem_report as report  # noqa: E402
import report_send  # noqa: E402
from test_problem_report import FAKE_TOKEN, FAKE_USER, PUBLIC_V4, fake_context  # noqa: E402

try:
    import tkinter as tk
    import problem_report_ui as report_ui
except ImportError:      # pragma: no cover
    tk = None


class FakeSender:
    def __init__(self, takes=15 << 20, fail=None):
        self.takes, self.fail, self.sent = takes, fail, []

    def probe(self):
        return self.takes

    def send(self, path, note="", contact="", progress=None):
        with zipfile.ZipFile(path) as z:
            self.sent.append(dict(names=z.namelist(), report=z.read("report.txt").decode() if "report.txt" in
                                  z.namelist() else "", size=os.path.getsize(path), note=note, contact=contact,
                                  all=b"".join(z.read(n) for n in z.namelist())))
        if progress:
            progress(os.path.getsize(path), os.path.getsize(path))
        if self.fail:
            raise self.fail
        return {"id": "K7QF2M", "webhook": True}


@unittest.skipIf(tk is None, "no tkinter")
class SendWindow(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.ctx = fake_context(self.d, build_exit=0)
        self.revealed, self.logged = [], []

    def tearDown(self):
        self.root.destroy()
        self.root = None
        __import__("gc").collect()

    def dialog(self, sender):
        return report_ui.ReportDialog(self.root, lambda: self.ctx, os.path.join(self.d, "Desktop"),
                                      reveal=self.revealed.append, log=self.logged.append, visible=False,
                                      discord_url="https://discord.gg/x", sender=sender)

    def pump(self, cond, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.root.update()
            if cond():
                return True
            time.sleep(0.02)
        self.fail("timed out")

    def texts(self, dlg):
        out = []

        def walk(w):
            for c in w.winfo_children():
                if not c.winfo_manager():
                    continue                    # (not shown)
                try:
                    out.append(str(c.cget("text")))
                except tk.TclError:
                    pass
                walk(c)
        walk(dlg.body)
        return " ".join(out)

    def test_one_click_sends_the_cleaned_zip(self):
        s = FakeSender()
        dlg = self.dialog(s)
        self.assertIn("Sends your logs to the developer", self.texts(dlg))
        self.assertEqual(str(dlg.send_btn.cget("default")), "active")
        dlg.note.insert("1.0", f"froze after the KO, my ip {PUBLIC_V4}")
        dlg.contact.insert(0, "Zed#1")
        dlg.send()
        self.pump(lambda: dlg.sent is not None or dlg.send_error is not None)
        self.assertIsNone(dlg.send_error)
        sent = s.sent[0]
        self.assertEqual(sent["report"], "froze after the KO, my ip <ip>")     # the zip has the cleaned note
        self.assertEqual(sent["contact"], "Zed#1")
        self.assertIn("contents.txt", sent["names"])
        self.assertLessEqual(sent["size"], report.SEND_TARGET)
        for secret in (FAKE_TOKEN, FAKE_USER, PUBLIC_V4):
            self.assertNotIn(secret.encode(), sent["all"])
        self.assertIn("Sent, thanks (report #K7QF2M)", self.texts(dlg))
        self.assertEqual(self.revealed, [])                         # nothing saved, no folder opened
        self.assertFalse(os.path.exists(os.path.join(self.d, "Desktop")))
        self.assertTrue(any("report sent: #K7QF2M" in m for m in self.logged))
        dlg.close()

    def test_enter_sends(self):
        s = FakeSender()
        dlg = self.dialog(s)
        dlg._enter(__import__("types").SimpleNamespace(widget=dlg.top))     # (Return anywhere but in the note)
        self.pump(lambda: dlg.sent is not None)
        self.assertEqual(len(s.sent), 1)
        dlg.close()

    def test_an_older_server_hides_send(self):
        dlg = self.dialog(FakeSender(takes=0))
        self.pump(lambda: not dlg.send_btn.winfo_manager())
        self.assertIn("cannot take reports yet", self.texts(dlg))
        self.assertEqual(str(dlg.save_btn.cget("text")), "Save report on the Desktop")
        dlg.save()
        self.pump(lambda: dlg.result is not None)
        self.assertTrue(os.path.isfile(dlg.result.path))
        dlg.close()

    def test_a_failed_send_keeps_save(self):
        from t5lobby.report_upload import ReportError
        dlg = self.dialog(FakeSender(fail=ReportError("connect_failed", "cannot reach the server")))
        dlg.send()
        self.pump(lambda: dlg.send_error is not None)
        self.assertIn("could not be reached", dlg.status_var.get())
        self.assertEqual(str(dlg.save_btn.cget("state")), "normal")
        self.assertEqual(str(dlg.send_btn.cget("state")), "normal")
        dlg.close()

    def test_without_a_sender_it_is_the_old_window(self):
        dlg = self.dialog(None)
        self.assertFalse(dlg.send_btn.winfo_manager())
        self.assertNotIn("Sends your logs", self.texts(dlg))
        self.assertEqual(str(dlg.save_btn.cget("text")), "Save report on the Desktop")
        dlg.close()


class SmallerForSending(unittest.TestCase):
    def test_a_big_report_is_made_smaller(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        ctx = fake_context(d)
        import random
        rnd = random.Random(5)
        logs = os.path.join(ctx.out_dir, "logs")
        os.makedirs(logs, exist_ok=True)
        for i in range(2):          # hard to pack: random words
            with open(os.path.join(logs, f"game-2026110{i}-101010.log"), "w", encoding="utf-8") as f:
                for _ in range(40000):
                    f.write(" ".join("%x" % rnd.getrandbits(40) for _ in range(8)) + "\n")
        full = report.build(ctx, os.path.join(d, "a"))
        target = full.zip_size // 3
        res = report.build_for_send(ctx, os.path.join(d, "b"), target=target)
        self.assertLessEqual(res.zip_size, target)
        self.assertEqual(len(os.listdir(os.path.join(d, "b"))), 1)        # the bigger tries are gone
        with zipfile.ZipFile(res.path) as z:
            self.assertIn("system.txt", z.namelist())
            self.assertTrue(any(n.startswith("logs/game-") for n in z.namelist()))


class TheWholeWay(unittest.TestCase):
    """Window -> report_send -> report_upload -> a lobby server on 127.0.0.1 -> stored + posted to the webhook."""

    def test_end_to_end(self):
        if tk is None:
            self.skipTest("no tkinter")
        lobby_tests = os.path.join(ROOT, "lobby", "tests")
        if lobby_tests not in sys.path:
            sys.path.insert(0, lobby_tests)
        from util import ServerThread                             # lobby/tests/util.py
        from test_problem_reports import Hook, hook_server        # lobby/tests/test_problem_reports.py
        from t5lobby.server import reports
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with hook_server() as url:
            st = ServerThread(report_dir=os.path.join(d, "srv"), report_webhook=url).start()
            try:
                with mock.patch.dict(os.environ, {"T5_REPORT_SERVER": f"127.0.0.1:{st.srv.port}"}):
                    sender = report_send.make_sender(release={"version": "1.2.3"},
                                                     build_info=lambda: {"build_id": "0123456789abcdef"},
                                                     name="Zed", name_kind="account", language="de")
                try:
                    root = tk.Tk()
                except tk.TclError as e:
                    self.skipTest(f"no display: {e}")
                root.withdraw()
                try:
                    ctx = fake_context(d)
                    dlg = report_ui.ReportDialog(root, lambda: ctx, os.path.join(d, "Desktop"), visible=False,
                                                 sender=sender)
                    dlg.note.insert("1.0", "black screen after the intro")
                    dlg.send()
                    end = time.monotonic() + 30
                    while dlg.sent is None and dlg.send_error is None and time.monotonic() < end:
                        root.update()
                        time.sleep(0.02)
                    self.assertIsNone(dlg.send_error)
                    rid = dlg.sent["id"]
                    dlg.close()
                finally:
                    root.destroy()
                self.assertTrue(st.wait_for(lambda: st.srv.counters.get("reports_posted", 0) == 1))
            finally:
                st.stop()
        rows = reports.ReportFolder(os.path.join(d, "srv")).all()
        self.assertEqual(len(rows), 1)
        meta, zpath = rows[0]
        self.assertEqual(meta["id"], rid)
        self.assertEqual((meta["game"], meta["version"], meta["build_id"]), ("T5DR Online", "1.2.3", "0123456789abcdef"))
        self.assertEqual(meta["name"], "Zed")
        self.assertEqual(meta["description"], "black screen after the intro")
        self.assertEqual(meta["webhook"], "posted with the zip")
        with zipfile.ZipFile(zpath) as z:
            self.assertEqual(z.read("report.txt").decode(), "black screen after the intro")
        body = Hook.posts[0][1]
        with open(zpath, "rb") as f:
            self.assertIn(f.read(), body)
        content = json.loads(body.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0])["content"]
        self.assertIn(f"#{rid}", content)
        self.assertIn("Zed (account, as the launcher says)", content)


if __name__ == "__main__":
    unittest.main()
