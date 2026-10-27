"""One-click update, end to end against a local fake release (1.1.5): the launcher's own Updater -- the check, the
offer, "Update now", download, size + SHA-256 (+ signature) check, staging, the detached swap step as a real
process, the new launcher's confirmation, the report and the clean-up -- on a fake installed release in a
temporary folder. Nothing goes to the network: FakeGitHub (test_updater.py) answers every request and refuses any
URL outside the allow-list, so no download can come from GitHub's real releases or land outside the test folder.

What must hold: the player's files (native\\: the built game, saves, controls.ini, replays, logs; launcher.json)
are byte for byte the same afterwards; nothing is replaced unless the download is the published file."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import updater  # noqa: E402
import release_sig  # noqa: E402
from test_updater import FakeGitHub, make_zip, release, tree, write  # noqa: E402

try:
    import tkinter as tk
except ImportError:      # pragma: no cover
    tk = None

PLAYER_FILES = {
    "native/build/t5dr_build.json": json.dumps({"code_id": "aaaaaaaaaaaaaaaa"}),
    "native/build/cmake/t5dr.exe": b"MZ the player's built game",
    "native/build/cmake/t5dr_game.dll": b"MZ lifted game code, built on this PC",
    "native/gamedata/dev_hdd0/home/00000001/savedata/BLUS-SAVE/DATA.BIN": b"my save",
    "native/controls.ini": "[keys]\nup = W\n",
    "native/replays/T5R-20261026-2100.t5replay": b"T5REPLAY 1\n{}\n",
    "native/logs/game-20261026-210000.log": "log\n",
    "launcher.json": json.dumps({"nickname": "Wishin", "internal_res": "1080p", "language": "de"}),
    "launcher.log": "old launcher log\n",
}
PROGRAM_FILES = {
    "release.json": json.dumps({"version": "1.1.4"}),
    "T5DR Online.exe": b"MZ old stub",
    "launcher/t5dr_launcher.pyw": "# old launcher\n",
    "launcher/updater.py": "# old updater\n",
    "python/pythonw.exe": b"MZ old python",
    "python/Lib/os.py": "# old\n",
    "tools/build_game.py": "# old\n",
    "runtime/t5dr.exe": b"MZ old runtime",
    "docs/TROUBLESHOOTING.md": "old\n",
    "README.txt": "old\n",
}
CONFIRM = "import os; open(os.environ['T5DR_UPDATE_CONFIRM'], 'w').write(str(os.getpid()))"


class Settings:
    def __init__(self, out_dir):
        self.out_dir = out_dir


@unittest.skipIf(tk is None, "no tkinter")
class OneClickUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5dr_e2e_update_")
        self.install = os.path.join(self.tmp, "T5DR-Online-1.1.4")
        for rel, data in {**PROGRAM_FILES, **PLAYER_FILES}.items():
            write(os.path.join(self.install, rel), data)
        self.player_before = {k: v for k, v in tree(self.install).items() if k in PLAYER_FILES}
        self.assertEqual(len(self.player_before), len(PLAYER_FILES))
        try:
            self.app = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.app.withdraw()
        self.app.settings = Settings(os.path.join(self.install, "native"))
        self.app.readonly = False
        self.closed = []
        self.app.on_close = lambda: self.closed.append(time.time())
        # a release signed with a key of this test only (the shipped key list is empty until the owner adds his)
        self.seed = bytes(range(32))
        self.key = release_sig.public_key(self.seed).hex()
        p = mock.patch.object(updater, "RELEASE_PUBLIC_KEYS", (self.key,))
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(updater, "processes_under", lambda dirs, exclude=(): [])    # (this test process)
        p.start()
        self.addCleanup(p.stop)
        os.environ[updater.NO_CHECK_ENV] = "1"          # no check of its own at start: the test asks
        self.addCleanup(os.environ.pop, updater.NO_CHECK_ENV, None)

    def tearDown(self):
        try:
            for job in self.app.tk.splitlist(self.app.tk.call("after", "info")):
                self.app.after_cancel(job)                 # (the updater's pump and its start-up timers)
            self.app.destroy()
        except tk.TclError:
            pass
        for _ in range(100):                           # (the stand-in launcher may still be ending)
            shutil.rmtree(self.tmp, ignore_errors=True)
            if not os.path.exists(self.tmp):
                break
            time.sleep(0.1)

    def github(self, version="1.1.5", zip_bytes=None, **kw):
        z = make_zip(version) if zip_bytes is None else zip_bytes
        data, files = release(version, z, sig=self.seed, **kw)
        return FakeGitHub(files, api=data)

    def pump(self, cond, timeout=60.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            self.app.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    def offer(self, gh):
        up = updater.Updater(self.app, root=self.install)
        self.assertEqual(up.local, "1.1.4")
        with mock.patch.object(updater, "open_url", gh):
            up.check(manual=True)
            self.assertTrue(self.pump(lambda: up.win is not None), "no offer")
        return up

    def test_one_click_keeps_the_players_files(self):
        gh = self.github()
        up = self.offer(gh)
        self.assertEqual(up.release["version"], "1.1.5")
        real_start = updater.start_swap
        spawned = []

        def start_swap(staged, version_from, version_to, out_dir=None, root=None, **kw):
            # the real step as a real process; the 'launcher' it starts afterwards is a stand-in that confirms,
            # and it does not wait for this test process to end (wait_pid 0)
            p = real_start(staged, version_from, version_to, out_dir=out_dir, root=root, wait_pid=0,
                           python=sys.executable, launch=[sys.executable, "-c", CONFIRM])
            spawned.append((p, staged))
            return p
        with mock.patch.object(updater, "open_url", gh), mock.patch.object(updater, "start_swap", start_swap):
            up.b_update.invoke()                                                 # the one click
            self.assertTrue(self.pump(lambda: spawned and self.closed), up.err.get() or up.msg.get())
        urls = [u for u, _h in gh.calls]
        self.assertTrue(urls[0].startswith("https://api.github.com/repos/"))
        self.assertTrue(all(u.startswith(("https://api.github.com/", "https://github.com/TheWishin/T5DROnline/"))
                            for u in urls), urls)
        self.assertIn("SHA256SUMS.sig", " ".join(urls))                         # the signature was fetched
        proc, staged = spawned[0]
        rc = proc.wait(90)
        with open(os.path.join(staged["sroot"], "swap.log"), encoding="utf-8") as f:
            self.assertEqual(rc, 0, f.read())
        with open(os.path.join(staged["sroot"], "result.json"), encoding="utf-8") as f:
            res = json.load(f)
        self.assertTrue(res["ok"])
        self.assertEqual(res["phase"], "done")
        after = tree(self.install)
        self.assertEqual({k: after.get(k) for k in PLAYER_FILES}, self.player_before)
        self.assertEqual(updater.local_version(self.install), "1.1.5")
        self.assertEqual(after["launcher/t5dr_launcher.pyw"], b"# new launcher\n")
        self.assertIn("lobby/t5lobby/client.py", after)                          # a folder the new release adds
        self.assertFalse(os.path.exists(os.path.join(staged["sroot"], "backup")))
        self.assertFalse(os.path.exists(os.path.join(staged["sroot"], "download", "T5DR-Online-1.1.5.zip")))
        # the new launcher reports it at its next start and removes the staging folder
        up2 = updater.Updater(self.app, root=self.install)
        self.assertEqual(up2.local, "1.1.5")
        up2.report_last_update()
        self.assertTrue(self.pump(lambda: not os.path.exists(staged["sroot"]), 20))
        logs = os.listdir(os.path.join(self.install, "native", "logs"))
        self.assertTrue(any(f.startswith("update-") for f in logs), logs)

    def check_refused(self, gh, words):
        up = self.offer(gh)
        before = tree(self.install)                     # (after the check: it caches its answer, update-check.json)
        with mock.patch.object(updater, "open_url", gh), \
                mock.patch.object(updater, "start_swap", side_effect=AssertionError("must not swap")):
            up.b_update.invoke()
            self.assertTrue(self.pump(lambda: up.err.get()), "no error shown")
        self.assertIn(words, up.err.get())
        self.assertEqual(tree(self.install), before)                             # nothing replaced
        self.assertEqual(self.closed, [])                                        # the launcher stays open
        for d in updater.stage_roots(self.install):
            self.assertFalse(os.path.exists(d), d)
        up.close_window()

    def test_a_different_file_is_refused(self):
        z = make_zip("1.1.5")
        data, files = release("1.1.5", z, sig=self.seed)
        url = next(u for u in files if u.endswith(".zip"))
        files[url] = make_zip("1.1.5", extra={"T5DR-Online-1.1.5/launcher/evil.py": "x"})    # same name, other bytes
        data["assets"][1]["size"] = len(files[url])
        self.check_refused(FakeGitHub(files, api=data), "SHA-256")

    def test_a_short_download_is_refused(self):
        z = make_zip("1.1.5")
        data, files = release("1.1.5", z, sig=self.seed)
        url = next(u for u in files if u.endswith(".zip"))
        files[url] = z[: len(z) // 2]                                            # cut off on the way
        self.check_refused(FakeGitHub(files, api=data), "stopped early")

    def test_an_unsigned_release_is_refused(self):
        z = make_zip("1.1.5")
        data, files = release("1.1.5", z)                                         # no SHA256SUMS.sig
        self.check_refused(FakeGitHub(files, api=data), "not signed")


if __name__ == "__main__":
    unittest.main()
