"""The "Report a problem" button (launcher/report.py, report_ui.py): the zip a player sends.

Scrubbing (user names in paths, IP addresses, tokens and passwords), what goes into the zip, the size
cap, the system information, the launcher log, and the window itself (never shown: the Tk window is
withdrawn). No game, no network, no real user data: every name, address and token below is made up.
"""
import hashlib
import json
import os
import sys
import tempfile
import time
import types
import unittest
import zipfile
from unittest import mock

from helpers import ROOT, load_tool

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import core    # noqa: E402
import report  # noqa: E402

try:
    import tkinter as tk
    import report_ui
except ImportError:      # pragma: no cover
    tk = None

FAKE_USER = "Zoltan Quux"          # a name with a space, so a path regex that stops at spaces fails
FAKE_PC = "QUUX-DESKTOP"
PUBLIC_V4 = "93.184.216.34"
PUBLIC_V4_B = "8.8.8.8"
PUBLIC_V6 = "2606:4700:4700::1111"
# built at run time: no secret-shaped literal in the repository (tools/check_no_game_data.py)
FAKE_TOKEN = hashlib.sha256(b"t5dr fake session token").hexdigest()[:48]
FAKE_MATCH_KEY = hashlib.sha256(b"t5dr fake match key").hexdigest()[:32]
FAKE_PASSWORD = "correct-horse-" + hashlib.sha256(b"t5dr fake password").hexdigest()[:8]


def scrubber(**kw):
    kw.setdefault("user_names", [FAKE_USER])
    kw.setdefault("pc_names", [FAKE_PC])
    return report.Scrubber(**kw)


def put(path, data, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = mode or ("wb" if isinstance(data, bytes) else "w")
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8", "newline": ""})) as f:
        f.write(data)
    return path


class UserNames(unittest.TestCase):
    def test_backslash_and_forward_slash_paths(self):
        sc = scrubber()
        self.assertEqual(sc.text(r"C:\Users\Zoltan Quux\Desktop\T5DR\native\game.log"),
                         r"C:\Users\<user>\Desktop\T5DR\native\game.log")
        self.assertEqual(sc.text("C:/Users/Zoltan Quux/Desktop/T5DR/native"), "C:/Users/<user>/Desktop/T5DR/native")
        self.assertEqual(sc.counts["user"], 2)

    def test_other_users_and_other_drives(self):
        sc = scrubber()
        self.assertEqual(sc.text(r"D:\Users\anna.b\AppData\Local\Temp"), r"D:\Users\<user>\AppData\Local\Temp")
        self.assertEqual(sc.text(r"file:///C:/Users/eve/x.txt"), "file:///C:/Users/<user>/x.txt")
        self.assertEqual(sc.text(r"C:\Users\Ünal Çelik\x"), r"C:\Users\<user>\x")
        self.assertEqual(sc.text(r"C:\Users\O'Brien\x"), r"C:\Users\<user>\x")

    def test_json_escaped_paths(self):
        sc = scrubber()
        self.assertEqual(sc.text('{"f": "C:\\\\Users\\\\Max\\\\Desktop\\\\a.json"}'),
                         '{"f": "C:\\\\Users\\\\<user>\\\\Desktop\\\\a.json"}')

    def test_a_name_with_spaces_at_the_end_of_a_quoted_path_or_a_line(self):
        sc = scrubber()
        self.assertEqual(sc.text('opened "C:\\Users\\John Smith" ok'), 'opened "C:\\Users\\<user>" ok')
        self.assertEqual(sc.text("saved to C:\\Users\\John Smith\nnext line"), "saved to C:\\Users\\<user>\nnext line")

    def test_a_name_followed_by_more_arguments_keeps_them(self):
        sc = scrubber()
        self.assertEqual(sc.text(r"--home C:\Users\Max --pkg C:\Users\Max\Downloads\a.pkg"),
                         r"--home C:\Users\<user> --pkg C:\Users\<user>\Downloads\a.pkg")

    def test_shared_profiles_and_url_paths_stay(self):
        sc = scrubber()
        for t in (r"C:\Users\Public\Documents", r"C:\Users\Default\NTUSER.DAT", "https://example.com/users/12/Users/x"):
            self.assertEqual(sc.text(t), t)
        self.assertEqual(sc.counts["user"], 0)

    def test_the_user_and_pc_name_anywhere(self):
        sc = scrubber()
        self.assertEqual(sc.text("hello zoltan quux, welcome to QUUX-DESKTOP; Zoltan Quuxx stays"),
                         "hello <user>, welcome to <pc>; Zoltan Quuxx stays")

    def test_onedrive_company_name(self):
        sc = scrubber()
        self.assertEqual(sc.text(r"C:\Users\x\OneDrive - Contoso GmbH\Desktop\a"), r"C:\Users\<user>\OneDrive - <org>\Desktop\a")

    def test_the_package_file_name_and_emails(self):
        sc = scrubber()
        name = "A2" + "x" * 90
        self.assertEqual(sc.text(f"--pkg C:\\dl\\{name}.pkg"), "--pkg C:\\dl\\<package>.pkg")
        self.assertEqual(sc.text("mail me@example.org, not user@host"), "mail <email>, not user@host")

    def test_this_pcs_own_names_are_found_by_default(self):
        sc = report.Scrubber()
        home = os.path.expanduser("~")
        name = os.path.basename(home)
        if len(name) >= 3 and name.lower() not in ("user", "public", "default"):
            self.assertNotIn(name, sc.text(f"C:\\Users\\{name}\\x and {name} and {home}"))


class Addresses(unittest.TestCase):
    def test_public_ipv4_with_and_without_port(self):
        sc = scrubber()
        self.assertEqual(sc.text(f"joining {PUBLIC_V4}:59986, then {PUBLIC_V4_B}."), "joining <ip>:59986, then <ip>.")
        self.assertEqual(sc.counts["ip"], 2)

    def test_local_addresses_are_kept(self):
        sc = scrubber()
        keep = ("127.0.0.1", "127.0.0.1:7781", "10.0.0.5", "172.16.5.4", "172.31.255.1", "192.168.1.20",
                "192.168.178.1:50000", "169.254.10.2", "0.0.0.0", "255.255.255.255")
        for ip in keep:
            self.assertEqual(sc.text(f"peer {ip} ok"), f"peer {ip} ok", ip)
        self.assertEqual(sc.text("outside 172.32.0.1 and 11.0.0.1"), "outside <ip> and <ip>")
        self.assertEqual(sc.counts["ip"], 2)

    def test_public_ipv6_in_all_forms(self):
        sc = scrubber()
        self.assertEqual(sc.text(f"peer {PUBLIC_V6} up"), "peer <ip> up")
        self.assertEqual(sc.text(f"peer [{PUBLIC_V6}]:443 up"), "peer [<ip>]:443 up")
        self.assertEqual(sc.text("peer 2606:4700:4700:0:0:0:0:1111."), "peer <ip>.")
        self.assertEqual(sc.text("mapped ::ffff:8.8.8.8 done"), "mapped <ip> done")

    def test_local_ipv6_is_kept(self):
        sc = scrubber()
        for ip in ("::1", "fe80::1", "fe80::1ff:fe23:4567:890a", "fd12:3456:789a::1", "::ffff:192.168.1.1"):
            self.assertEqual(sc.text(f"at {ip} ok"), f"at {ip} ok", ip)

    def test_versions_clock_times_and_names_are_not_addresses(self):
        sc = scrubber()
        for t in ("Windows 10.0.26300.9711", "driver 32.0.16.1742", "python 3.12.10", "1.2.3.4.5", "v9.9.9.9",
                  "time 19:26:37 and 12:34:56.789", "std::vector add::dec Foo::Bar a::b", "x 1.2.3.400 and 01.02.03.04",
                  "key=0x6E754149 id 12:34", "sha 1234:5678"):
            self.assertEqual(sc.text(t), t, t)

    def test_the_lobby_style_endpoint_line_of_a_real_log(self):
        sc = scrubber()
        self.assertEqual(sc.text(f"[netplay] connected (join, P2), delay 3, peer {PUBLIC_V4}:59986, packets authenticated"),
                         "[netplay] connected (join, P2), delay 3, peer <ip>:59986, packets authenticated")


class Secrets(unittest.TestCase):
    def test_names_that_hold_a_secret(self):
        sc = scrubber()
        for text, want in (
                (f"T5_NET_KEY={FAKE_MATCH_KEY} rest", "T5_NET_KEY=<removed> rest"),
                (f'{{"T5_NET_KEY": "{FAKE_MATCH_KEY}", "x": 1}}', '{"T5_NET_KEY": "<removed>", "x": 1}'),
                (f"password={FAKE_PASSWORD}", "password=<removed>"),
                (f"--password {FAKE_PASSWORD} --out C:\\x", "--password <removed> --out C:\\x"),
                (f"token: {FAKE_TOKEN}", "token: <removed>"),
                (f"session_token = '{FAKE_TOKEN}'", "session_token = '<removed>'"),
                (f"https://bob:{FAKE_PASSWORD}@example.org/x?token=abc&a=1", "https://<removed>@example.org/x?token=<removed>&a=1"),
                ("Authorization: Bearer abcdefghij1234567890", "Authorization: <removed>"),
                ("API_KEY=abc123", "API_KEY=<removed>")):
            self.assertEqual(sc.text(text), want)

    def test_log_words_that_only_look_like_it_stay(self):
        sc = scrubber()
        for t in ("[evt] queue_create -> id=2 key=0x6E754149 size=4",
                  "[netplay] main loop frame 1100: keyread wakes stopped (keyread in a tick; tokens 0, waiters 0)",
                  "handshake from boot on: authenticated (match key), connect timeout 60 s",
                  "reader tokens given back 0"):
            self.assertEqual(sc.text(t), t)

    def test_exact_values_are_removed_wherever_they_are(self):
        sc = scrubber(secrets=[FAKE_TOKEN, "x"])           # a value shorter than 6 characters is ignored
        self.assertEqual(sc.text(f"resume {FAKE_TOKEN}!"), "resume <removed>!")
        self.assertEqual(sc.text("x marks"), "x marks")

    def test_long_hex_strings_but_not_the_game_programs_sha1(self):
        sha1 = hashlib.sha1(b"the game program").hexdigest()
        sc = scrubber(keep=[sha1])
        self.assertEqual(sc.text(f"sha {sha1} and {FAKE_TOKEN}"), f"sha {sha1} and <hex>")
        self.assertEqual(sc.text("hash f566b09a296fb30d build acd750b2014ae803"), "hash f566b09a296fb30d build acd750b2014ae803")

    def test_a_second_pass_changes_nothing(self):
        sc = scrubber(secrets=[FAKE_TOKEN])
        text = (f"C:\\Users\\Zoltan Quux\\a peer {PUBLIC_V4}:1 T5_NET_KEY={FAKE_MATCH_KEY} {PUBLIC_V6} "
                f"--password {FAKE_PASSWORD} me@example.org {FAKE_TOKEN}")
        out = sc.text(text)
        self.assertTrue(sc.clean(out))
        self.assertEqual(sc.text(out), out)
        for bad in (FAKE_USER, PUBLIC_V4, FAKE_MATCH_KEY, PUBLIC_V6, FAKE_PASSWORD, "example.org", FAKE_TOKEN):
            self.assertNotIn(bad, out)

    def test_secrets_are_read_from_json_by_key_name(self):
        doc = {"server": "x", "sessions": {"host:7781": {"name": "n", "token": FAKE_TOKEN}},
               "password": FAKE_PASSWORD, "nested": [{"api_key": "abcdef123456"}], "T5_NET_KEY": FAKE_MATCH_KEY,
               "plain": "visible-value", "key": "bare-key-value"}
        found = report.harvest_secrets(doc)
        self.assertEqual(found, {FAKE_TOKEN, FAKE_PASSWORD, "abcdef123456", FAKE_MATCH_KEY, "bare-key-value"})


class Reading(unittest.TestCase):
    def test_a_big_file_keeps_its_start_and_its_end(self):
        with tempfile.TemporaryDirectory() as d:
            lines = [f"line {i:06d} ........................................\n" for i in range(20000)]
            p = put(os.path.join(d, "big.log"), "".join(lines))
            data, removed = report.read_capped(p, 100_000)
        text = data.decode()
        self.assertLessEqual(len(data), 100_000)
        self.assertGreater(removed, 800_000)
        self.assertTrue(text.startswith("line 000000"))
        self.assertTrue(text.rstrip().endswith("line 019999 ........................................"))
        self.assertIn(f"{removed:,} bytes removed", text)
        for ln in text.splitlines():                                  # cut at line ends: no broken line
            self.assertTrue(not ln or ln.startswith("line ") or ln.startswith("[... T5DR report"), ln)

    def test_a_small_file_is_whole(self):
        with tempfile.TemporaryDirectory() as d:
            p = put(os.path.join(d, "s.log"), "a\nb\n")
            self.assertEqual(report.read_capped(p, 1000), (b"a\nb\n", 0))
            self.assertEqual(report.read_capped(os.path.join(d, "missing"), 1000), (b"", 0))


def fake_native(d, user=FAKE_USER, logs=3, build_exit=None):
    """A native\\ folder as a played release leaves it, with made-up names, addresses and tokens."""
    out = os.path.join(d, "native")
    home = f"C:\\Users\\{user}\\Desktop\\T5DR"
    for i in range(logs):
        body = [f"[boot] VFS root: {home}\\native\\game\\vfs\n", f"[gpu] adapter: Fake GPU 9000 (vendor 10DE, 8192 MB)\n",
                f"[netplay] joining {PUBLIC_V4}:5{i}000\n", f"[netplay] mode join marker-{i}\n"]
        p = put(os.path.join(out, "logs", f"game-20261018-1{i}0000.log"), "".join(body) * 40)
        t = time.time() - (logs - i) * 100
        os.utime(p, (t, t))
    put(os.path.join(out, "logs", "online", "ctl", "cmd.json"), json.dumps(
        {"match": "m1", "env": {"T5_NET_PEER": f"{PUBLIC_V4_B}:9017", "T5_NET_KEY": FAKE_MATCH_KEY,
                                "T5_NET_RESULT_FILE": home + "\\native\\logs\\online\\result-m1.json"}}))
    put(os.path.join(out, "logs", "online", "ctl", "state.json"), '{"ctl": 1, "state": "neutral"}')
    put(os.path.join(out, "logs", "online", "result-m1.json"), '{"match": "m1", "winner": 1}')
    put(os.path.join(out, "logs", "online", "status-m1.json"), '{"state": "over", "match": 2}')
    older = put(os.path.join(out, "logs", "online", "result-m0.json"), '{"match": "m0", "winner": 0}')
    os.utime(older, (time.time() - 3600, time.time() - 3600))            # the match before
    put(os.path.join(out, "logs", "online", "results", "m1.json"), '{"match": "m1"}')
    put(os.path.join(out, "rb_frames.log"), f"# rbnet frames\n# {home}\n")
    put(os.path.join(out, "controls.ini"), "[general]\nbackground = 1\n")
    put(os.path.join(out, "np_desync_f000123.bin"), bytes(range(256)) * 40)
    put(os.path.join(out, "rb_desync_f000200.bin"), b"\x00\x01\x02" * 100)
    put(os.path.join(out, "build", "t5dr_build.json"), json.dumps(
        {"code_id": "aab9cb523c06a67b", "elf_sha1": "be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "built": "2026-10-18T19:28:00",
         "compiler": f"clang-cl from {home}\\toolchain"}))
    if build_exit is not None:
        put(os.path.join(out, "build.log"), f"# T5DR Online build log\n# {home}\\python\\python.exe build_game.py\nERROR: x\n"
            f"# exit code {build_exit}\n")
    return out


def fake_context(d, **kw):
    out = kw.pop("out", None) or fake_native(d, build_exit=kw.pop("build_exit", 0))
    root = os.path.join(d, "release")
    online_dir = os.path.join(d, "appdata", "T5DROnline")
    put(os.path.join(online_dir, "online.json"), json.dumps(
        {"server": "play.example.org:7781", "name": "Zed", "remember": True,
         "sessions": {"play.example.org:7781": {"name": "Zed", "token": FAKE_TOKEN, "saved": 1}}}))
    put(os.path.join(root, "launcher.json"), json.dumps(
        {"pkg": "C:\\Users\\Zoltan Quux\\Downloads\\a.pkg", "display": "window1080", "password": FAKE_PASSWORD,
         "extra_env": "PS3_PAD_LOG=1"}))
    put(os.path.join(root, "launcher.log"), f"2026-10-18 20:00:00 launcher 1.0.0 started, output C:\\Users\\{FAKE_USER}\\x\n"
        f"2026-10-18 20:00:01 status: login {FAKE_TOKEN}\n")
    put(os.path.join(root, "launcher.log.1"), "2026-10-17 10:00:00 older run\n")
    args = dict(root=root, launcher_log=os.path.join(root, "launcher.log"), online_dir=online_dir,
                release={"version": "1.2.3", "name": "T5DR Online", "commit": hashlib.sha1(b"c").hexdigest()},
                build_info={"build_id": "0123456789abcdef", "code_id": "aab9cb523c06a67b", "net": 3,
                            "elf_sha1": "be80165b84e30b6334baa6d6331b9db4ffd5a6a4"},
                settings_lines=["Window and resolution: Window, 1920 x 1080 [window1080]",
                                "Online input delay (netcode): 2", "Extra settings: ", "    PS3_PAD_LOG=1"],
                online_info=f"Server: play.example.org:7781\nLast match: id m1, ping 25 ms, peer {PUBLIC_V4}\n",
                user_names=[FAKE_USER], pc_names=[FAKE_PC])
    args.update(kw)
    return report.Context(out, **args)


class Whole(unittest.TestCase):
    def build(self, **kw):
        self.d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.d, True)
        self.ctx = fake_context(self.d, **kw.pop("ctx", {}))
        self.dest = os.path.join(self.d, "Desktop")
        self.res = report.build(self.ctx, self.dest, **kw)
        self.z = zipfile.ZipFile(self.res.path)
        self.addCleanup(self.z.close)
        return self.res

    def names(self):
        return sorted(self.z.namelist())

    def text(self, name):
        return self.z.read(name).decode("utf-8")

    def test_one_zip_with_the_expected_files(self):
        self.build(note="The match froze after round 2.")
        self.assertRegex(os.path.basename(self.res.path), r"^T5DR-report-\d{8}-\d{6}\.zip$")
        self.assertEqual(os.listdir(self.dest), [os.path.basename(self.res.path)])      # one file, no .part left
        self.assertIsNone(self.z.testzip())
        n = self.names()
        for want in ("contents.txt", "system.txt", "report.txt", "launcher.log", "launcher.log.1", "controls.ini",
                     "logs/rb_frames.log", "online/ctl/cmd.json", "online/ctl/state.json", "online/result-m1.json",
                     "online/status-m1.json", "online/results/m1.json", "online/lobby-summary.txt",
                     "desync/np_desync_f000123.bin", "desync/rb_desync_f000200.bin"):
            self.assertIn(want, n)
        self.assertNotIn("online/result-m0.json", n)                  # an older match's file
        self.assertEqual(self.text("report.txt"), "The match froze after round 2.")
        self.assertNotIn("build.log", n)                              # the last build went fine

    def test_the_newest_two_game_logs_only(self):
        self.build()
        logs = [n for n in self.names() if n.startswith("logs/game-")]
        self.assertEqual(logs, ["logs/game-20261018-110000.log", "logs/game-20261018-120000.log"])
        self.assertIn("marker-2", self.text("logs/game-20261018-120000.log"))

    def test_build_log_when_the_build_is_the_problem(self):
        self.build(ctx={"build_exit": 2})
        self.assertIn("build.log", self.names())
        self.assertNotIn("FAKE", self.text("build.log"))
        self.assertIn("exit code 2", self.text("build.log"))
        self.build(ctx={"build_exit": 0}, enabled={"build": True})            # the player ticked it anyway
        self.assertIn("build.log", self.names())
        self.build(ctx={"build_exit": 2}, enabled={"build": False})           # ... or unticked it
        self.assertNotIn("build.log", self.names())

    def test_nothing_private_is_in_any_text_file(self):
        self.build(note=f"my ip is {PUBLIC_V4_B} and my name is {FAKE_USER}; password={FAKE_PASSWORD}")
        for name in self.z.namelist():
            if name.startswith("desync/"):
                continue
            t = self.text(name)
            for bad in (FAKE_USER, FAKE_PC, PUBLIC_V4, PUBLIC_V4_B, FAKE_TOKEN, FAKE_MATCH_KEY, FAKE_PASSWORD):
                self.assertNotIn(bad, t, f"{bad!r} in {name}")
            self.assertNotRegex(t, r"(?i)Users[\\/]+(?!<user>|Public|Default)\w")
        # ... but the useful parts are still there
        self.assertIn(r"C:\Users\<user>\Desktop\T5DR\native\game\vfs", self.text("logs/game-20261018-120000.log"))
        self.assertIn("<ip>:", self.text("logs/game-20261018-120000.log"))
        self.assertIn('"T5_NET_KEY": "<removed>"', self.text("online/ctl/cmd.json"))
        self.assertIn("<ip>:9017", self.text("online/ctl/cmd.json"))

    def test_settings_files_never_go_in(self):
        self.build()
        for name in self.names():
            self.assertNotIn("online.json", name)
            self.assertNotIn("launcher.json", name)
        # the token sits only in online.json and in the launcher log here: the log copy is cleaned by value
        self.assertIn("status: login <removed>", self.text("launcher.log"))

    def test_binary_dumps_are_copied_as_they_are(self):
        self.build()
        self.assertEqual(self.z.read("desync/np_desync_f000123.bin"), bytes(range(256)) * 40)
        self.assertEqual(self.z.read("desync/rb_desync_f000200.bin"), b"\x00\x01\x02" * 100)

    def test_system_text(self):
        self.build()
        t = self.text("system.txt")
        for want in ("Release: 1.2.3 (T5DR Online)", "Build id: 0123456789abcdef", "Code id: aab9cb523c06a67b",
                     "Game program SHA-1: be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "Windows:", "Processor:", "Memory:",
                     "Graphics:", "== Settings in use ==", "Window, 1920 x 1080", "Online input delay (netcode): 2",
                     "PS3_PAD_LOG=1", "[gpu] adapter: Fake GPU 9000", "Source commit: " + hashlib.sha1(b"c").hexdigest()):
            self.assertIn(want, t)

    def test_contents_lists_everything_and_what_was_removed(self):
        self.build()
        t = self.text("contents.txt")
        self.assertIn("logs/game-20261018-120000.log", t)
        self.assertRegex(t, r"\d+ internet IP addresses -> <ip>")
        self.assertRegex(t, r"\d+ passwords, tokens, match keys")
        self.assertIn("Build log (the last build went fine): not included", t)
        self.assertGreater(self.res.counts["user"], 5)
        self.assertGreater(self.res.counts["ip"], 5)
        self.assertGreaterEqual(self.res.counts["secret"], 2)

    def test_a_second_report_in_the_same_second_gets_its_own_name(self):
        self.build()
        again = report.build(self.ctx, self.dest, now=__import__("datetime").datetime.fromtimestamp(
            os.path.getmtime(self.res.path)))
        self.assertNotEqual(again.path, self.res.path)
        self.assertEqual(len(os.listdir(self.dest)), 2)

    def test_an_empty_folder_still_makes_a_report(self):
        with tempfile.TemporaryDirectory() as d:
            res = report.build(report.Context(os.path.join(d, "native"), user_names=[FAKE_USER], pc_names=[FAKE_PC]),
                               os.path.join(d, "out"))
            with zipfile.ZipFile(res.path) as z:
                self.assertEqual(sorted(z.namelist()), ["contents.txt", "system.txt"])


class SizeCap(unittest.TestCase):
    def logs(self, d, sizes):
        out = os.path.join(d, "native")
        for i, size in enumerate(sizes):
            lines, n = [], 0
            j = 0
            while n < size:
                ln = f"[log{i}] line {j:07d} user C:\\Users\\{FAKE_USER}\\x peer {PUBLIC_V4}:{j % 60000} ...........\n"
                lines.append(ln)
                n += len(ln)
                j += 1
            p = put(os.path.join(out, "logs", f"game-20261018-1{i}0000.log"), "".join(lines))
            t = time.time() - (len(sizes) - i) * 100
            os.utime(p, (t, t))
        return out

    def test_a_huge_log_is_cut_in_the_middle(self):
        cap = 400_000
        with tempfile.TemporaryDirectory() as d:
            out = self.logs(d, [3_000_000])
            res = report.build(report.Context(out, user_names=[FAKE_USER], pc_names=[FAKE_PC]),
                               os.path.join(d, "o"), cap=cap)
            self.assertLessEqual(res.total, cap)
            self.assertLessEqual(res.zip_size, cap)
            with zipfile.ZipFile(res.path) as z:
                t = z.read("logs/game-20261018-100000.log").decode()
                self.assertTrue(t.startswith("[log0] line 0000000"))                        # the start (boot lines)
                self.assertRegex(t.rstrip().splitlines()[-1], r"^\[log0\] line \d{7} ")     # the end (the crash)
                self.assertRegex(t, r"\[\.\.\. T5DR report: [\d,]+ bytes removed here")
                self.assertIn("shortened", z.read("contents.txt").decode())
                self.assertNotIn(FAKE_USER, t)
        m = {x["name"]: x for x in res.members}["logs/game-20261018-100000.log"]
        self.assertGreater(m["removed"], 2_000_000)

    def test_the_newest_log_comes_first_and_gets_more(self):
        cap = 600_000
        with tempfile.TemporaryDirectory() as d:
            out = self.logs(d, [2_000_000, 2_000_000])
            res = report.build(report.Context(out, user_names=[FAKE_USER], pc_names=[FAKE_PC]),
                               os.path.join(d, "o"), cap=cap)
        sizes = {m["name"]: m["size"] for m in res.members}
        new, old = sizes["logs/game-20261018-110000.log"], sizes["logs/game-20261018-100000.log"]
        self.assertGreater(new, old)
        self.assertGreater(old, 20_000)
        self.assertLessEqual(res.total, cap)
        self.assertLessEqual(res.zip_size, cap)

    def test_small_files_are_never_squeezed_out_by_big_logs(self):
        cap = 500_000
        with tempfile.TemporaryDirectory() as d:
            out = self.logs(d, [4_000_000, 4_000_000])
            put(os.path.join(out, "build.log"), "# exit code 3\n" + "x" * 30_000)
            put(os.path.join(out, "controls.ini"), "[general]\n")
            put(os.path.join(out, "np_desync_f000001.bin"), os.urandom(60_000))
            res = report.build(report.Context(out, user_names=[FAKE_USER], pc_names=[FAKE_PC]),
                               os.path.join(d, "o"), cap=cap)
        names = {m["name"] for m in res.members}
        for want in ("system.txt", "build.log", "controls.ini", "desync/np_desync_f000001.bin",
                     "logs/game-20261018-110000.log", "logs/game-20261018-100000.log"):
            self.assertIn(want, names)
        self.assertLessEqual(res.total, cap)
        self.assertLessEqual(res.zip_size, cap)

    def test_a_placeholder_longer_than_the_name_cannot_break_the_cap(self):
        cap = 200_000
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "native")
            # "C:\Users\ab\" is replaced by "C:\Users\<user>\": every line grows by 4 characters
            put(os.path.join(out, "logs", "game-20261018-100000.log"), "C:\\Users\\ab\\x\n" * 40_000)
            res = report.build(report.Context(out, user_names=["ab"], pc_names=[]), os.path.join(d, "o"), cap=cap)
        self.assertLessEqual(res.total, cap)

    def test_a_short_user_name_does_not_cut_a_small_file(self):
        """"al" becomes "<user>": the clean text is longer than the file. That must not cut it."""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "native")
            put(os.path.join(out, "build.log"), "# exit code 1\n" + "C:\\Users\\al\\x\n" * 500)
            put(os.path.join(out, "controls.ini"), "[general]\n# C:\\Users\\al\\x\n")
            res = report.build(report.Context(out, user_names=["al"], pc_names=[]), os.path.join(d, "o"))
            with zipfile.ZipFile(res.path) as z:
                t = z.read("build.log").decode()
                self.assertNotIn("bytes removed", t)
                self.assertEqual(t.count("C:\\Users\\<user>\\x"), 500)
                self.assertEqual(z.read("controls.ini").decode(), "[general]\n# C:\\Users\\<user>\\x\n")
                self.assertNotIn("bytes removed", z.read("system.txt").decode())

    def test_the_default_cap_is_20_mb(self):
        self.assertEqual(report.DEFAULT_CAP, 20 * 1024 * 1024)


class Selection(unittest.TestCase):
    def test_online_files_of_the_last_match_only(self):
        with tempfile.TemporaryDirectory() as d:
            out = fake_native(d)
            names = [os.path.relpath(p, out).replace("\\", "/") for p in report.online_files(out)]
        self.assertIn("logs/online/ctl/cmd.json", names)
        self.assertIn("logs/online/ctl/state.json", names)
        self.assertIn("logs/online/result-m1.json", names)
        self.assertIn("logs/online/status-m1.json", names)
        self.assertIn("logs/online/results/m1.json", names)
        self.assertNotIn("logs/online/result-m0.json", names)

    def test_last_build_failed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(report.last_build_failed(d))                              # no build.log
            for text, want in (("# exit code 0\n", False), ("# exit code 2\n", True), ("# exit code -1\n", True),
                               ("[compile]\nstill running\n", True)):
                put(os.path.join(d, "build.log"), text)
                self.assertEqual(report.last_build_failed(d), want, text)

    def test_discover_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = fake_context(d, build_exit=4)
            g = {x.key: x for x in report.discover(ctx, "")}
            self.assertTrue(g["build"].default_on)
            self.assertFalse(g["system"].can_untick)
            self.assertNotIn("note", g)
            self.assertIn("note", {x.key: x for x in report.discover(ctx, "hello")})
            self.assertIn("desync", g)
            self.assertTrue(all(i.kind == "binary" for i in g["desync"].items))

    def test_summary_lines(self):
        with tempfile.TemporaryDirectory() as d:
            lines = report.describe(report.discover(fake_context(d), ""))
        self.assertTrue(any(l.startswith("Launcher log: 2 files") for l in lines), lines)
        self.assertTrue(any("Game logs" in l or "Game log" in l for l in lines), lines)


class SystemInfo(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows registry")
    def test_windows_11_is_named_right_although_the_registry_says_10(self):
        fake = {"ProductName": "Windows 10 Pro", "CurrentBuild": "26100", "DisplayVersion": "24H2", "UBR": 4770,
                "EditionID": "Professional"}
        with mock.patch.object(report, "_reg", lambda path, name, root=None: fake.get(name)):
            self.assertEqual(report.windows_version(), "Windows 11 Pro 24H2 (build 26100.4770), " + (report.platform.machine() or "?"))
            fake["CurrentBuild"], fake["EditionID"] = "19045", "ProfessionalN"
            self.assertIn("Windows 10 Pro 24H2 (build 19045.4770)", report.windows_version())
            self.assertIn('edition ProfessionalN ("N"', report.windows_version())

    @unittest.skipUnless(os.name == "nt", "Windows APIs")
    def test_real_values_on_this_pc(self):
        self.assertRegex(report.windows_version(), r"^Windows \d+")
        self.assertRegex(report.cpu_info(), r"\d+ logical processors")
        self.assertRegex(report.memory_info(), r"[\d.]+ GB total, [\d.]+ GB free")
        for name, ver, date, mem in report.gpu_info():
            self.assertTrue(name and ver)
        for d in report.display_info():
            self.assertGreater(d["width"], 0)
            self.assertGreater(d["hz"], 0)

    def test_settings_lines_show_the_choices_and_no_paths_or_secrets(self):
        st = {"pkg": "C:\\Users\\Zoltan Quux\\a.pkg", "rap": "C:\\x\\b.rap", "display": "window1080", "render_scale": "0.75",
              "input_delay": "2", "mute": True, "extra_env": "PS3_PAD_LOG=2\n# c\n", "nickname": "Zed", "password": FAKE_PASSWORD}
        labels = {"display": dict(core.DISPLAY_MODES), "render_scale": core.RENDER_SCALES, "input_delay": core.INPUT_DELAYS}
        lines = report.settings_lines(st, labels, {"T5_RB_NET_DELAY": "2"}, r"C:\x\native")
        text = "\n".join(lines)
        self.assertIn("Window, 1920 x 1080 [window1080]", text)
        self.assertIn("Lower [0.75]", text)
        self.assertIn("Online input delay (netcode): 2 [2]", text)
        self.assertIn("Mute sound: yes", text)
        self.assertIn("    PS3_PAD_LOG=2", text)
        self.assertIn("T5_RB_NET_DELAY=2", text)
        self.assertNotIn("Zoltan", text)
        self.assertNotIn(FAKE_PASSWORD, text)
        self.assertNotIn("Zed", text)

    def test_build_info_from_a_built_folder(self):
        with tempfile.TemporaryDirectory() as d:
            out = fake_native(d)
            put(os.path.join(out, "game", "EBOOT.elf"), b"not the real program")
            info = report.build_info_for(out, {"version": "9.9.9"}, ROOT)
        self.assertEqual(info["code_id"], "aab9cb523c06a67b")
        self.assertRegex(info.get("build_id", ""), r"^[0-9a-f]{16}$")
        self.assertEqual(info["net"], 3)


class LauncherLog(unittest.TestCase):
    def test_lines_are_added_with_a_time(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "launcher.log")
            core.log("first", p)
            core.log("two\nlines", p)
            lines = open(p, encoding="utf-8").read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d first$")
        self.assertTrue(lines[1].endswith("two | lines"))

    def test_it_moves_aside_when_big_and_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "launcher.log")
            put(p, "x" * (core.LAUNCHER_LOG_MAX + 10))
            core.log("after", p)
            self.assertTrue(os.path.exists(p + ".1"))
            self.assertEqual(len(open(p, encoding="utf-8").read().splitlines()), 1)
            core.log("into nowhere", os.path.join(d, "no", "such", "dir", "x.log"))      # must not raise

    def test_the_report_tool_and_window_ship_in_the_release(self):
        package = load_tool("package_release")
        for f in ("launcher/report.py", "launcher/report_ui.py"):
            self.assertIn(f, package.OUR_FILES)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, *f.split("/"))))
        smoke = load_tool("smoke_release")
        self.assertIn("launcher/report.py", smoke.REQUIRED)


class CommandLine(unittest.TestCase):
    def test_main_makes_a_zip(self):
        with tempfile.TemporaryDirectory() as d:
            out = fake_native(d)
            with mock.patch("sys.stdout"):
                code = report.main(["--out", out, "--dest-dir", os.path.join(d, "o"), "--note", "hi"])
            self.assertEqual(code, 0)
            z = [f for f in os.listdir(os.path.join(d, "o")) if f.endswith(".zip")]
            self.assertEqual(len(z), 1)
            with zipfile.ZipFile(os.path.join(d, "o", z[0])) as zf:
                self.assertEqual(zf.read("report.txt"), b"hi")


@unittest.skipIf(tk is None, "no tkinter")
class Window(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.d, True)
        self.ctx = fake_context(self.d, build_exit=0)
        self.revealed, self.logged = [], []

    def tearDown(self):
        self.root.destroy()
        self.root = None
        __import__("gc").collect()

    def dialog(self):
        return report_ui.ReportDialog(self.root, lambda: self.ctx, os.path.join(self.d, "Desktop"),
                                      reveal=self.revealed.append, issues_url="https://example.org/issues",
                                      log=self.logged.append, visible=False)

    def pump(self, cond, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.root.update()
            if cond():
                return True
            time.sleep(0.02)
        self.fail("timed out")

    def test_the_window_lists_what_goes_in_and_saves_one_zip(self):
        dlg = self.dialog()
        self.assertFalse(dlg.top.winfo_viewable())                       # never shown while testing
        self.assertEqual(set(dlg.vars), {"system", "launcher", "game", "build", "online", "controls", "desync"})
        self.assertTrue(dlg.vars["system"].get())
        self.assertFalse(dlg.vars["build"].get())                        # the last build went fine
        dlg.note.insert("1.0", f"froze, my ip {PUBLIC_V4}")
        dlg.vars["controls"].set(False)
        dlg.save()
        self.pump(lambda: dlg.result is not None or dlg.error)
        self.assertIsNone(dlg.error)
        res = dlg.result
        self.assertTrue(os.path.isfile(res.path))
        self.assertEqual(os.path.dirname(res.path), os.path.join(self.d, "Desktop"))
        with zipfile.ZipFile(res.path) as z:
            self.assertNotIn("controls.ini", z.namelist())
            self.assertEqual(z.read("report.txt").decode(), "froze, my ip <ip>")
            self.assertNotIn("build.log", z.namelist())
        self.assertEqual(self.revealed, [res.path])                      # the folder was opened once, afterwards
        self.assertTrue(any("report saved" in m for m in self.logged))
        dlg.open_folder()
        self.assertEqual(len(self.revealed), 2)
        dlg.close()

    def test_a_failure_is_shown_and_the_button_comes_back(self):
        dlg = self.dialog()
        dlg.dest_dir = os.path.join(self.d, "file")
        put(dlg.dest_dir, "i am a file, not a folder")
        dlg.save()
        self.pump(lambda: dlg.error is not None)
        self.assertIn("could not be made", dlg.status_var.get())
        self.assertEqual(str(dlg.save_btn.cget("state")), "normal")
        self.assertEqual(self.revealed, [])
        dlg.close()

    def test_the_online_tabs_button_asks_the_launcher(self):
        from t5lobby.tk_tab import OnlineTab
        calls = []
        tab = types.SimpleNamespace(app=types.SimpleNamespace(report_problem=lambda: calls.append(1)))
        OnlineTab.do_report(tab)
        self.assertEqual(calls, [1])
        OnlineTab.do_report(types.SimpleNamespace(app=object()))          # a launcher without it: nothing happens

    def test_the_online_tabs_report_text_has_no_names_addresses_or_keys(self):
        from t5lobby.tk_tab import OnlineTab
        ticket = types.SimpleNamespace(match_id="m9", role="join", slot=1, path="direct", rtt_ms=31.0, jitter_ms=2.0,
                                       delay=2, rounds=3, ranked=False, input_delay=None, build="0123456789abcdef",
                                       peer=(PUBLIC_V4, 5000), key=FAKE_MATCH_KEY, opponent={"name": "Rival"})
        driver = types.SimpleNamespace(mode="persistent", ctl_failures=1, last_fps=59.9, session_ticket=ticket,
                                       history=[("m9", {"source": "game", "token": FAKE_TOKEN})])
        client = types.SimpleNamespace(me={"guest": True, "name": "Zed"}, tls=True, server_rtt=40.0)
        tab = types.SimpleNamespace(client=client, driver=driver, cfg={"game_mode": "auto"},
                                    last_result={"match": "m9", "status": "confirmed", "winner": 1, "score": [0, 3],
                                                 "rating": {"r": 1500}, "you": {"name": "Zed", "token": FAKE_TOKEN}},
                                    _server_key=lambda: "play.example.org:7781")
        text = OnlineTab.report_info(tab)
        for want in ("Server: play.example.org:7781", "Logged in: as a guest", "Match driver mode: persistent",
                     "id m9, join slot 1, path direct, ping 31 ms", "'status': 'confirmed'"):
            self.assertIn(want, text)
        for bad in (PUBLIC_V4, FAKE_MATCH_KEY, FAKE_TOKEN, "Rival", "Zed", "1500"):
            self.assertNotIn(bad, text)


if __name__ == "__main__":
    unittest.main()
