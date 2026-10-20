"""Discord Rich Presence (t5lobby/discord_rpc.py): the frames on Discord's local IPC pipe, against a fake Discord
-- a named pipe with a test-only name (a Unix socket elsewhere), never the real discord-ipc-N pipes, so a Discord
running on this PC is not touched. Handshake, SET_ACTIVITY and taking it down, the rate limit, PING, Discord not
running (silent), starting later, quitting and coming back, a refused application id, the configuration, and the
texts in English and German."""
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
import uuid

import util  # noqa: F401  (sys.path)

from t5lobby import discord_rpc, i18n
from t5lobby.discord_rpc import DiscordPresence, activity_for

APP = "123456789012345678"


class FakeDiscord:
    """The Discord client's side of the IPC pipe, for tests. Answers the handshake with READY (or an ERROR when
    `refuse`), SET_ACTIVITY with the activity, PING with PONG; records everything. kick() drops the client
    (Discord quit); stop() ends it. Every wait inside has a timeout."""

    def __init__(self, user="Tester", refuse=False):
        self.user = user
        self.refuse = refuse
        tag = f"t5dr-test-discord-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        if os.name == "nt":
            self.path = "\\\\.\\pipe\\" + tag
        else:
            self._dir = tempfile.mkdtemp()
            self.path = os.path.join(self._dir, tag)
        self.frames = []            # (op, payload) from the client
        self.activities = []        # each SET_ACTIVITY's activity (None = taken down)
        self.connections = 0
        self.pongs = []
        self._stop = threading.Event()
        self._kick = threading.Event()
        self._ping = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        if not self._ready.wait(5):
            raise RuntimeError("fake Discord did not start")
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(5)

    def kick(self):
        self._kick.set()

    def send_ping(self):
        self._ping.set()

    def wait(self, pred, timeout=10.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if pred():
                return True
            time.sleep(0.01)
        raise AssertionError(f"fake Discord: not as expected; frames {self.frames}")

    # --- the server loop
    def _run(self):
        if os.name == "nt":
            self._run_pipe()
        else:
            self._run_unix()

    def _serve(self, recv, send, available):
        """One connection: frames until the client closes, kick() or stop()."""
        self.connections += 1
        while not self._stop.is_set():
            if self._kick.is_set():
                self._kick.clear()
                return
            if self._ping.is_set():
                self._ping.clear()
                send(discord_rpc.encode(discord_rpc.OP_PING, {"n": 1}))
            if not available():
                time.sleep(0.01)
                continue
            op, n = struct.unpack("<II", recv(8))
            data = json.loads(recv(n).decode("utf-8")) if n else {}
            self.frames.append((op, data))
            if op == discord_rpc.OP_HANDSHAKE:
                if self.refuse:
                    send(discord_rpc.encode(discord_rpc.OP_FRAME, {"cmd": "DISPATCH", "evt": "ERROR",
                                                                   "data": {"code": 4000, "message": "Invalid Client ID"}}))
                    send(discord_rpc.encode(discord_rpc.OP_CLOSE, {"code": 4000, "message": "Invalid Client ID"}))
                    return
                send(discord_rpc.encode(discord_rpc.OP_FRAME, {"cmd": "DISPATCH", "evt": "READY",
                                                               "data": {"v": 1, "user": {"username": self.user}}}))
            elif op == discord_rpc.OP_FRAME and data.get("cmd") == "SET_ACTIVITY":
                act = (data.get("args") or {}).get("activity")
                self.activities.append(act)
                send(discord_rpc.encode(discord_rpc.OP_FRAME, {"cmd": "SET_ACTIVITY", "data": act, "evt": None,
                                                               "nonce": data.get("nonce")}))
            elif op == discord_rpc.OP_PONG:
                self.pongs.append(data)
            elif op == discord_rpc.OP_CLOSE:
                return

    def _run_pipe(self):
        import _winapi
        while not self._stop.is_set():
            h = _winapi.CreateNamedPipe(self.path, _winapi.PIPE_ACCESS_DUPLEX | _winapi.FILE_FLAG_OVERLAPPED,
                                        _winapi.PIPE_WAIT, _winapi.PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0,
                                        _winapi.NULL)
            self._ready.set()
            try:
                ov = _winapi.ConnectNamedPipe(h, overlapped=True)
                while not self._stop.is_set():
                    if _winapi.WaitForSingleObject(ov.event, 50) == _winapi.WAIT_OBJECT_0:
                        break
                else:
                    ov.cancel()
                    try:
                        ov.GetOverlappedResult(True)
                    except OSError:
                        pass
                    return
                ov.GetOverlappedResult(True)
                buf = bytearray()
                pending = []              # the one overlapped read in flight (kept until it completes: no lost bytes)

                def pump(wait_ms):
                    if not pending:
                        rov, _err = _winapi.ReadFile(h, 65536, overlapped=True)
                        pending.append(rov)
                    if _winapi.WaitForSingleObject(pending[0].event, wait_ms) != _winapi.WAIT_OBJECT_0:
                        return False
                    rov = pending.pop()
                    rov.GetOverlappedResult(True)          # (BrokenPipeError: the client is gone)
                    buf.extend(rov.getbuffer())
                    return True

                def recv(n, timeout=5.0):
                    t_end = time.monotonic() + timeout
                    while len(buf) < n:
                        if self._stop.is_set() or time.monotonic() > t_end:
                            raise TimeoutError
                        pump(50)
                    out = bytes(buf[:n])
                    del buf[:n]
                    return out

                def send(data):
                    wov, _err = _winapi.WriteFile(h, data, overlapped=True)
                    if _winapi.WaitForSingleObject(wov.event, 5000) != _winapi.WAIT_OBJECT_0:
                        wov.cancel()
                        raise TimeoutError
                    wov.GetOverlappedResult(True)

                def available():
                    return bool(buf) or pump(20)
                try:
                    self._serve(recv, send, available)
                except (OSError, TimeoutError, ValueError):
                    pass
                for rov in pending:
                    rov.cancel()
                    try:
                        rov.GetOverlappedResult(True)
                    except OSError:
                        pass
            finally:
                _winapi.CloseHandle(h)

    def _run_unix(self):
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.path)
        srv.listen(4)
        srv.settimeout(0.05)
        self._ready.set()
        try:
            while not self._stop.is_set():
                try:
                    c, _a = srv.accept()
                except socket.timeout:
                    continue
                c.settimeout(5.0)
                import select

                def recv(n, c=c):
                    out = b""
                    while len(out) < n:
                        chunk = c.recv(n - len(out))
                        if not chunk:
                            raise OSError("closed")
                        out += chunk
                    return out
                try:
                    self._serve(recv, c.sendall, lambda c=c: bool(select.select([c], [], [], 0.02)[0]))
                except (OSError, TimeoutError, ValueError):
                    pass
                c.close()
        finally:
            srv.close()


def fast(p):
    p.MIN_INTERVAL = 0.05
    p.RETRY = 0.2
    p.LOST_RETRY = 0.2
    return p


class PresenceTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeDiscord().start()
        self.addCleanup(self.fake.stop)
        self.p = None

    def tearDown(self):
        if self.p is not None:
            self.p.close(3)

    def presence(self, **kw):
        self.p = fast(DiscordPresence(APP, paths=[self.fake.path], **kw)).start()
        return self.p

    def test_shows_updates_and_takes_it_down(self):
        p = self.presence()
        lobby = activity_for("lobby", start=1000)
        p.update(lobby)
        self.fake.wait(lambda: self.fake.activities == [lobby])
        hs = self.fake.frames[0]
        self.assertEqual(hs, (discord_rpc.OP_HANDSHAKE, {"v": 1, "client_id": APP}))
        set_frame = self.fake.frames[1][1]
        self.assertEqual(set_frame["args"]["pid"], os.getpid())
        self.assertTrue(set_frame["nonce"])
        self.assertTrue(p.connected)
        self.assertEqual(p.user, "Tester")
        match = activity_for("match", ranked=True, fighters=("Jin", "Kazuya"), set_score=(1, 0), start=1005)
        p.update(match)
        self.fake.wait(lambda: self.fake.activities[-1] == match)
        self.assertEqual(match["details"], "In match: Jin vs Kazuya (Ranked, Set 1-0)")
        self.assertEqual(match["timestamps"], {"start": 1005})
        p.update(None)                                              # nothing to show (logged out)
        self.fake.wait(lambda: self.fake.activities[-1] is None)
        p.update(lobby)
        self.fake.wait(lambda: self.fake.activities[-1] == lobby)
        p.close(3)
        self.fake.wait(lambda: self.fake.activities[-1] is None)    # taken down at the end ...
        self.fake.wait(lambda: self.fake.frames[-1][0] == discord_rpc.OP_CLOSE)   # ... and a proper goodbye
        self.assertFalse(p._thread.is_alive())

    def test_at_most_one_update_per_interval(self):
        p = self.presence()
        p.MIN_INTERVAL = 3.0        # long enough that a burst on a busy PC still falls inside one interval
        p.update(activity_for("lobby", start=1))
        self.fake.wait(lambda: len(self.fake.activities) == 1)
        for i in range(10):                                         # a burst of changes
            p.update(activity_for("search", mode="ranked" if i % 2 else "quick", start=2 + i))
            time.sleep(0.02)
        time.sleep(0.2)
        self.assertEqual(len(self.fake.activities), 1)              # held back ...
        last = activity_for("search", mode="ranked", start=11)
        self.fake.wait(lambda: self.fake.activities[-1] == last, 6)  # ... then only the newest one
        self.assertEqual(len(self.fake.activities), 2)

    def test_ping_gets_a_pong(self):
        p = self.presence()
        p.update(activity_for("lobby"))
        self.fake.wait(lambda: self.fake.activities)
        self.fake.send_ping()
        self.fake.wait(lambda: self.fake.pongs == [{"n": 1}])

    def test_discord_quits_and_comes_back(self):
        p = self.presence()
        lobby = activity_for("lobby", start=5)
        p.update(lobby)
        self.fake.wait(lambda: self.fake.activities == [lobby])
        self.fake.kick()                                            # Discord quits (or restarts)
        self.fake.wait(lambda: self.fake.connections == 2, 10)      # back by itself ...
        self.fake.wait(lambda: self.fake.activities == [lobby, lobby])   # ... and shows the state again
        self.assertTrue(p.connected)

    def test_a_refused_application_id(self):
        self.fake.refuse = True
        log = []
        p = self.presence(log=log.append)
        p.update(activity_for("lobby"))
        self.fake.wait(lambda: self.fake.connections >= 2, 10)       # tries again now and then, quietly
        self.assertFalse(p.connected)
        self.assertEqual(self.fake.activities, [])
        self.assertEqual(len(log), 1)
        self.assertIn("Invalid Client ID", p.last_error)


class NoDiscordTest(unittest.TestCase):
    def test_nothing_happens_without_discord(self):
        missing = "\\\\.\\pipe\\t5dr-test-nobody-" + uuid.uuid4().hex if os.name == "nt" else \
            os.path.join(tempfile.mkdtemp(), "nobody")
        log = []
        p = fast(DiscordPresence(APP, paths=[missing], log=log.append)).start()
        p.update(activity_for("lobby"))
        t_end = time.monotonic() + 5
        while p.attempts < 3 and time.monotonic() < t_end:
            time.sleep(0.05)
        self.assertGreaterEqual(p.attempts, 3)
        self.assertFalse(p.connected)
        self.assertEqual(p.sent, 0)
        self.assertEqual(len(log), 1)                               # one line, not one per try
        t0 = time.monotonic()
        p.close(3)
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertFalse(p._thread.is_alive())

    def test_discord_starts_later(self):
        fake = FakeDiscord()
        p = fast(DiscordPresence(APP, paths=[fake.path])).start()
        try:
            lobby = activity_for("lobby", start=7)
            p.update(lobby)
            time.sleep(0.4)
            self.assertFalse(p.connected)
            fake.start()
            fake.wait(lambda: fake.activities == [lobby], 10)
        finally:
            p.close(3)
            fake.stop()

    def test_no_application_id_no_thread(self):
        for bad in ("", None, "abc", "12345"):
            p = DiscordPresence(bad, paths=["unused"]).start()
            self.assertIsNone(p._thread)
            p.update(activity_for("lobby"))
            p.close()

    def test_default_pipes(self):
        paths = discord_rpc.default_paths()
        if os.name == "nt":
            self.assertEqual(paths[0], r"\\.\pipe\discord-ipc-0")
            self.assertEqual(len(paths), 10)
        else:
            self.assertTrue(all(os.path.basename(p).startswith("discord-ipc-") for p in paths))


class TextAndConfigTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_the_texts(self):
        self.assertEqual(activity_for("lobby")["details"], "In lobby")
        self.assertEqual(activity_for("search", mode="ranked")["details"], "Searching ranked")
        self.assertEqual(activity_for("search", mode="quick")["details"], "Searching quick match")
        self.assertEqual(activity_for("match", ranked=False, fighters=("Lili", "Asuka"))["details"],
                         "In match: Lili vs Asuka (Casual)")
        self.assertEqual(activity_for("match", ranked=True, fighters=("Jin", None))["details"], "In match (Ranked)")
        self.assertIsNone(activity_for(None))
        a = activity_for("lobby", start=12.7, large_image="logo", large_text="T5DR Online")
        self.assertEqual(a["timestamps"], {"start": 12})
        self.assertEqual(a["assets"], {"large_image": "logo", "large_text": "T5DR Online"})
        self.assertNotIn("assets", activity_for("lobby"))
        i18n.set_language("de")
        i18n.clear_missing()
        self.assertEqual(activity_for("match", ranked=True, fighters=("Jin", "Kazuya"), set_score=(1, 0))["details"],
                         "Im Match: Jin vs Kazuya (Ranked-Set 1-0)")
        self.assertEqual(activity_for("search", mode="ranked")["details"], "Sucht ein Ranked-Match")
        self.assertEqual(activity_for("lobby")["details"], "In der Lobby")
        self.assertEqual(i18n.missing(), [])

    def test_the_application_id(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "discord.json")
        self.assertIsNone(discord_rpc.load_config(env={}, path=path)["application_id"])     # no file
        with open(path, "w") as f:
            json.dump({"application_id": "111111111111111111", "large_image": "logo"}, f)
        cfg = discord_rpc.load_config(env={}, path=path)
        self.assertEqual((cfg["application_id"], cfg["large_image"]), ("111111111111111111", "logo"))
        cfg = discord_rpc.load_config({"discord_app_id": "222222222222222222"}, env={}, path=path)
        self.assertEqual(cfg["application_id"], "222222222222222222")                      # the player's own
        cfg = discord_rpc.load_config({"discord_app_id": "not a number"}, env={"T5_DISCORD_APP_ID": "333333333333333333"},
                                      path=path)
        self.assertEqual(cfg["application_id"], "333333333333333333")                      # the environment wins
        self.assertIsNone(discord_rpc.valid_app_id("12 34"))
        # what the release ships: no id until the owner made the Discord application (docs/ONLINE.md)
        shipped = discord_rpc.load_config(env={})
        self.assertIn("application_id", shipped)


if __name__ == "__main__":
    unittest.main()
