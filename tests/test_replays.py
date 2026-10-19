"""Replays (docs/REPLAYS.md): the file the game writes for every online session and the launcher's side of it.

* launcher/replays.py reads the header line (the Replays list), decodes the binary part (tools, tests),
  lists one row per match, builds the playback environment and takes the players' names out for a problem
  report (strip_names) -- checked on files written by Python here and on files written by the game's own
  code.
* tests/c/replay_test.cpp is src/netplay/replay.cpp + replay_zlib.cpp on their own: it records a made-up
  session through the calls the netplay hooks make and plays files back the way the game does, so the two
  readers (C++ and Python) and the two writers (the game's and strip_names') are checked against each other:
  the same inputs on every frame, the same matches, sync points and names.
* The playback's frame numbering at a sync point that this game reaches later than the recording did
  (a fresh game loads a fight slower than one that has played).
* The problem report takes the newest replay without names; the launcher's settings give the game
  T5_REPLAY_DIR / T5_REPLAY_NAMES.

The C++ part needs a Windows C++ compiler and a ps3recomp tree (stb's zlib code, libs/codec); it is skipped
without them.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import replays  # noqa: E402

NEUTRAL = (0, 128, 128, 128, 128)


def fnv_digest(frames):
    """FNV-1a over every input as the C++ harness digests it (buttons, then the four axes as one word)."""
    h = 1469598103934665603
    for pair in frames:
        for (b, lx, ly, rx, ry) in pair:
            for v in (b, lx | ly << 8 | rx << 16 | ry << 24):
                for i in range(4):
                    h ^= (v >> (8 * i)) & 0xFF
                    h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def make_file(path, inputs, matches, bars=(), hashes=(), rollback=True, slot=0, names=("A", "B"),
              build="b1", created="2026-10-19T12:00:00Z"):
    """A replay file written by Python (the same layout as replay.cpp's)."""
    n = len(inputs[0])
    b = bytearray(b"T5RP")
    b += struct.pack("<IIIIiIIII", 1, 1 if rollback else 0, slot, 2, 1, 7, 7, n, 60)
    b += struct.pack("<I", len(matches))
    for m in matches:
        b += struct.pack("<6I", m["start"], m["end"], m["end"] - m["start"], m["end"], 0,
                         (1 | 2 | 4) if m.get("winner") is not None else 0)
        b += struct.pack("<12i", m["p1"], m["p2"], 0, 0, 1, 2, m["stage"], 2, 0,
                         -1 if m.get("winner") is None else m["winner"], *m.get("score", (0, 0)))
        b += struct.pack("<Q", 0x1234)
        for nm in names:
            e = nm.encode()
            b += struct.pack("<H", len(e)) + e
    b += struct.pack("<I", len(bars))
    for x in bars:
        b += struct.pack("<5IQ3I", x["kind"], x["f"], x["nf"], x["seed"], 1, x["f"], 1, 2, 3)
    b += struct.pack("<I", len(hashes))
    for f, h in hashes:
        b += struct.pack("<IQ", f, h)
    for p in (0, 1):
        for c in range(6):
            prev = NEUTRAL[0] & 0xFF if c == 0 else 0 if c == 1 else 128
            for f in range(n):
                v = inputs[p][f]
                cur = (v[0] & 0xFF, v[0] >> 8, v[1], v[2], v[3], v[4])[c]
                b.append(cur ^ prev)
                prev = cur
    header = {"format": 1, "build": build, "created": created, "mode": "rollback" if rollback else "lockstep",
              "slot": slot, "frames": n, "matches": []}
    for k, m in enumerate(matches, 1):
        header["matches"].append({"n": k, "start": m["start"], "end": m["end"], "p1": m["p1"], "p2": m["p2"],
                                  "stage": m["stage"], "winner": m.get("winner"), "score": list(m.get("score", (0, 0))),
                                  "complete": m.get("winner") is not None, "started": m.get("started", created),
                                  "names": list(names)})
    with open(path, "wb") as f:
        f.write(replays.MAGIC + json.dumps(header).encode() + b"\n" + zlib.compress(bytes(b)))
    return header


def sample_inputs(n, seed=7):
    import random
    rnd = random.Random(seed)
    out = [[], []]
    cur = [list(NEUTRAL), list(NEUTRAL)]
    for _ in range(n):
        for p in (0, 1):
            if rnd.random() < 0.2:
                cur[p][0] = rnd.randrange(1 << 16)
            if rnd.random() < 0.1:
                cur[p][1], cur[p][2] = rnd.randrange(256), rnd.randrange(256)
            out[p].append(tuple(cur[p]))
    return out


class PythonSideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5dr-replay")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_payload_round_trip(self):
        ins = sample_inputs(500)
        p = os.path.join(self.tmp, "a" + replays.EXT)
        make_file(p, ins, [{"start": 0, "end": 300, "p1": 9, "p2": 33, "stage": 27, "winner": 1, "score": (0, 2)}],
                  bars=[{"kind": 2, "f": 190, "nf": 195, "seed": 99}], hashes=[(0, 5), (60, 6)])
        d = replays.read_payload(p)
        self.assertEqual(d["frames"], 500)
        self.assertEqual(d["inputs"][0], ins[0])
        self.assertEqual(d["inputs"][1], ins[1])
        self.assertEqual(d["sync_points"][0]["nf"], 195)
        self.assertEqual(d["hashes"], [(0, "%016x" % 5), (60, "%016x" % 6)])
        self.assertEqual(d["matches"][0]["names"], ["A", "B"])

    def test_list_one_row_per_match_from_this_players_side(self):
        ins = sample_inputs(100)
        make_file(os.path.join(self.tmp, "s1" + replays.EXT), ins,
                  [{"start": 0, "end": 40, "p1": 9, "p2": 33, "stage": 20, "winner": 1, "score": (1, 2),
                    "started": "2026-10-19T12:00:00Z"},
                   {"start": 50, "end": 90, "p1": 9, "p2": 33, "stage": 20, "winner": None,
                    "started": "2026-10-19T12:05:00Z"}], slot=1, names=("Host", "Me"))
        make_file(os.path.join(self.tmp, "s2" + replays.EXT), ins,
                  [{"start": 0, "end": 40, "p1": 0, "p2": 1, "stage": 27, "winner": 0, "score": (3, 1),
                    "started": "2026-10-19T13:00:00Z"}], slot=0, names=("Me", "Other"))
        with open(os.path.join(self.tmp, "junk" + replays.EXT), "wb") as f:
            f.write(b"not a replay")
        rows = replays.list_replays(self.tmp)
        self.assertEqual(len(rows), 3)
        newest = rows[0]
        self.assertEqual((newest.fighters, newest.won, newest.score, newest.opponent), ("Paul vs Law", True, (3, 1), "Other"))
        rematch, first = rows[1], rows[2]
        self.assertTrue(rematch.rematch)
        self.assertFalse(rematch.complete)
        self.assertEqual((first.fighters, first.won, first.score, first.opponent), ("Lili vs Jin", True, (2, 1), "Host"))
        self.assertEqual(replays.newest(self.tmp) is not None, True)

    def test_playback_env(self):
        p = os.path.join(self.tmp, "a" + replays.EXT)
        make_file(p, sample_inputs(10), [{"start": 0, "end": 5, "p1": 1, "p2": 2, "stage": 20, "winner": 0}])
        env = replays.playback_env(p, 2, os.path.join(self.tmp, "v.json"), speed=0, controls=False)
        self.assertEqual(env["T5_NET_MODE"], "replay")
        self.assertEqual(env["T5_REPLAY_MATCH"], "2")
        self.assertEqual(env["T5_REPLAY_SPEED"], "0")
        self.assertEqual(env["T5_REPLAY_CONTROLS"], "0")
        self.assertNotIn("T5_RB_MODE", env)               # the file decides rollback or lockstep, not the launcher
        bad = os.path.join(self.tmp, "bad" + replays.EXT)
        with open(bad, "wb") as f:
            f.write(b"T5REPLAY 1\n{nope\n")
        with self.assertRaises(replays.ReplayError):
            replays.playback_env(bad)

    def test_strip_names(self):
        p = os.path.join(self.tmp, "a" + replays.EXT)
        ins = sample_inputs(64)
        make_file(p, ins, [{"start": 0, "end": 5, "p1": 1, "p2": 2, "stage": 20, "winner": 0}], names=("Secret Sam", "Zoe"))
        data = replays.strip_names(p)
        self.assertNotIn(b"Secret Sam", data)
        self.assertNotIn(b"Zoe", zlib.decompress(data.split(b"\n", 2)[2]))
        q = os.path.join(self.tmp, "b" + replays.EXT)
        with open(q, "wb") as f:
            f.write(data)
        d = replays.read_payload(q)
        self.assertEqual(d["inputs"][0], ins[0])
        self.assertEqual(d["matches"][0]["names"], ["", ""])
        self.assertEqual(replays.read_header(q)["matches"][0]["names"], ["<player>", "<player>"])

    def test_prune_keeps_the_newest(self):
        for i in range(5):
            p = os.path.join(self.tmp, f"r{i}" + replays.EXT)
            make_file(p, sample_inputs(4), [{"start": 0, "end": 2, "p1": 1, "p2": 2, "stage": 20, "winner": 0}])
            os.utime(p, (1000 + i, 1000 + i))
        self.assertEqual(replays.prune(self.tmp, keep=2), 3)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["r3" + replays.EXT, "r4" + replays.EXT])


class LauncherSideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5dr-replay")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_settings_record_by_default(self):
        import core
        p = os.path.join(self.tmp, "launcher.json")
        s = core.Settings(p)
        env = s.env_overrides()
        self.assertEqual(env["T5_REPLAY_DIR"], os.path.join(s.out_dir, "replays"))
        self.assertNotIn("T5_REPLAY_NAMES", env)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"replay_names": False}, f)
        self.assertEqual(core.Settings(p).env_overrides()["T5_REPLAY_NAMES"], "0")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"replays": False}, f)
        self.assertNotIn("T5_REPLAY_DIR", core.Settings(p).env_overrides())

    def test_problem_report_has_the_newest_replay_without_names(self):
        import problem_report as pr
        out = os.path.join(self.tmp, "native")
        os.makedirs(os.path.join(out, "replays"))
        old = os.path.join(out, "replays", "old" + replays.EXT)
        new = os.path.join(out, "replays", "new" + replays.EXT)
        for p, t in ((old, 1000), (new, 2000)):
            make_file(p, sample_inputs(32), [{"start": 0, "end": 5, "p1": 1, "p2": 2, "stage": 20, "winner": 0}],
                      names=("Nick Name", "Rival Person"))
            os.utime(p, (t, t))
        ctx = pr.Context(out, root=self.tmp, launcher_log=None)
        groups = pr.discover(ctx)
        g = [x for x in groups if x.key == "replay"]
        self.assertEqual(len(g), 1)
        self.assertEqual([i.arcname for i in g[0].items], ["replay/new" + replays.EXT])
        res = pr.build(ctx, self.tmp, groups=groups)
        with zipfile.ZipFile(res.path) as z:
            data = z.read("replay/new" + replays.EXT)
        self.assertNotIn(b"Nick Name", data)
        self.assertNotIn(b"Rival Person", zlib.decompress(data.split(b"\n", 2)[2]))
        q = os.path.join(self.tmp, "back" + replays.EXT)
        with open(q, "wb") as f:
            f.write(data)
        self.assertEqual(replays.read_payload(q)["frames"], 32)


class ReplaysTabTest(unittest.TestCase):
    """The launcher's Replays tab, built for real (not shown): the rows, Watch (the game's environment and the
    verdict it shows afterwards), Delete, in English and German."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_i18n as ti
        if ti.tk is None:
            self.skipTest("no tkinter")
        self.ti = ti
        self.base = ti.Base("setUp")
        self.base.setUp()                       # no dialogs, launcher.log in a temporary folder, sys.path restored
        self.addCleanup(self.base.doCleanups)
        self.dir = tempfile.mkdtemp(prefix="t5dr-replaytab")
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "user")
        self.addCleanup(os.environ.pop, "T5_ONLINE_DIR", None)
        self.native = os.path.join(self.dir, "native")
        os.makedirs(os.path.join(self.native, "replays"))
        self.file = os.path.join(self.native, "replays", "T5R-test" + replays.EXT)
        make_file(self.file, sample_inputs(50),
                  [{"start": 0, "end": 20, "p1": 9, "p2": 33, "stage": 27, "winner": 0, "score": (2, 1),
                    "started": "2026-10-19T12:00:00Z"},
                   {"start": 25, "end": 45, "p1": 9, "p2": 33, "stage": 27, "winner": 1, "score": (0, 2),
                    "started": "2026-10-19T12:04:00Z"}], slot=0, names=("Me", "Rival"))

    def launcher(self, language):
        import core
        from t5lobby import i18n
        st = core.Settings(os.path.join(self.dir, "launcher.json"))
        st["language"] = language
        st["out"] = self.native
        mod = self.ti.load_launcher()
        try:
            app = mod.App(offscreen=False, settings=st)
        except self.ti.tk.TclError as e:
            self.skipTest(f"no display: {e}")
        app.withdraw()
        self.ti.cancel_timers(app)
        app.refresh_game_state = lambda: None

        def close():
            self.ti.cancel_timers(app)
            app.online.on_close()
            app.destroy()
            i18n.set_language("en")
        self.addCleanup(close)
        return app

    def test_rows_watch_and_verdict(self):
        app = self.launcher("en")
        app.nb.select(app.tabs["replays"])
        app.update()
        tab = app.replays
        rows = [tab.tv.item(i, "values") for i in tab.tv.get_children()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(list(rows[0][1:]), ["Jin vs Lili", "lost 0-2", "Rival", "Rollback  ·  rematch"])
        self.assertEqual(list(rows[1][1:]), ["Jin vs Lili", "won 2-1", "Rival", "Rollback"])
        started = {}

        class FakeGame:
            def running(self):
                return False

            def stop(self):
                pass

        def start_game(env=None):
            started.update(env)
            with open(env["T5_REPLAY_RESULT"], "w", encoding="utf-8") as f:
                json.dump({"identical": True, "hashes_compared": 69, "matches": []}, f)
            return FakeGame()
        app.start_game = start_game
        app.game_state = lambda: {"ok": True}
        tab.tv.selection_set("0")
        app.update()
        tab.watch()
        self.assertEqual(started["T5_NET_MODE"], "replay")
        self.assertEqual(started["T5_REPLAY_MATCH"], "2")
        self.assertEqual(os.path.normcase(started["T5_REPLAY_FILE"]), os.path.normcase(os.path.abspath(self.file)))
        tab._poll()
        self.assertIn("identical to the live match (69 checks", tab.verdict.get())
        self.assertIsNone(tab.watching)

    def test_german(self):
        from t5lobby import i18n
        app = self.launcher("de")
        app.nb.select(app.tabs["replays"])
        app.update()
        texts = self.ti.all_texts(app.tabs["replays"])
        self.assertIn("ANSEHEN", texts)
        self.assertTrue(any("gewonnen 2-1" in str(v) for i in app.replays.tv.get_children()
                            for v in app.replays.tv.item(i, "values")))
        self.assertEqual(i18n.missing(), [])


def find_stb():
    cands = [os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")]
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--git-common-dir"], capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            common = os.path.normpath(os.path.join(ROOT, r.stdout.strip()))
            cands.append(os.path.join(os.path.dirname(common), "deps", "ps3recomp"))
    except (OSError, subprocess.SubprocessError):
        pass
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "libs", "codec", "stb_image_write.h")):
            return os.path.join(c, "libs", "codec")
    return None


class GameCodeTest(unittest.TestCase):
    """src/netplay/replay.cpp itself (tests/c/replay_test.cpp)."""

    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("Windows only")
        stb = find_stb()
        if not stb:
            raise unittest.SkipTest("no ps3recomp tree (libs/codec/stb_image_write.h)")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_ps_hid import find_vcvars
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not clang:
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        cls.tmp = tempfile.mkdtemp(prefix="t5dr-replayc")
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        exe = os.path.join(cls.tmp, "replay_test.exe")
        srcs = [os.path.join(ROOT, "tests", "c", "replay_test.cpp"), os.path.join(ROOT, "src", "netplay", "replay.cpp"),
                os.path.join(ROOT, "src", "netplay", "replay_zlib.cpp")]
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /O1 /EHsc /std:c++17 /W0 /D_CRT_SECURE_NO_WARNINGS '
               f'/I "{stb}" ' + " ".join(f'"{s}"' for s in srcs) + f' /Fe:"{exe}" /Fo:"{cls.tmp}\\\\"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600, cwd=cls.tmp)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/replay_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def run_exe(self, *args):
        r = subprocess.run([self.exe, *args], capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout

    def lines(self, out, tag):
        return [ln[len(tag) + 1:] for ln in out.splitlines() if ln.startswith(tag + " ")]

    def test_game_writes_what_python_reads_and_back(self):
        d = tempfile.mkdtemp(dir=self.tmp)
        code, out = self.run_exe("write", d, "3000", "0x5eed")
        self.assertEqual(code, 0, out)
        path = self.lines(out, "FILE")[0]
        digest = int(self.lines(out, "DIGEST")[0], 16)
        p = replays.read_payload(path)
        self.assertEqual(p["frames"], 3000)
        self.assertEqual(fnv_digest(zip(p["inputs"][0], p["inputs"][1])), digest)
        self.assertTrue(p["rollback"])
        self.assertEqual((p["slot"], p["delay"], p["rb_delay"], p["seed"]), (1, 2, 1, 0x1234ABCD))
        self.assertEqual([b["kind"] for b in p["sync_points"]], [2, 4, 5])
        self.assertEqual(p["hash_every"], 30)
        self.assertEqual(len(p["hashes"]), 100)
        h = replays.read_header(path)
        m1, m2 = h["matches"]
        self.assertEqual((m1["p1"], m1["p2"], m1["b1"], m1["b2"], m1["stage"], m1["rounds"], m1["pick"]), (9, 33, 2, 4, 27, 2, 30))
        self.assertEqual((m1["winner"], m1["score"], m1["hash"], m1["complete"]), (1, [0, 2], "0123456789abcdef", True))
        self.assertEqual((m2["winner"], m2["score"], m2["desync"], m2["start"]), (0, [2, 1], 3, 1500))
        self.assertEqual(m1["names"], ["Alpha One", "B\u00e9ta"])
        self.assertEqual(h["build"], "test-build-id")
        # the game reads it back: every frame's inputs, the lines, the sync points
        code, out = self.run_exe("read", path)
        self.assertEqual(code, 0, out)
        frames = list(zip(p["inputs"][0], p["inputs"][1]))
        self.assertEqual(int(self.lines(out, "DIGESTPLUS")[0], 16), fnv_digest(frames))
        self.assertEqual(self.lines(out, "LINE"), ["1 9,33,27,2 buttons=2|4 pick=30 names=Alpha%20One|B%C3%A9ta",
                                                   "2 9,33,27,2 buttons=2|1 names=Alpha%20One|B%C3%A9ta"])
        self.assertEqual(len(self.lines(out, "BARRIER")), 3)
        # and a copy without names (problem report) still plays, with no names in its lines
        stripped = os.path.join(d, "stripped" + replays.EXT)
        with open(stripped, "wb") as f:
            f.write(replays.strip_names(path))
        code, out = self.run_exe("read", stripped)
        self.assertEqual(code, 0, out)
        self.assertEqual(int(self.lines(out, "DIGESTPLUS")[0], 16), fnv_digest(frames))
        self.assertEqual(self.lines(out, "LINE")[0], "1 9,33,27,2 buttons=2|4 pick=30")

    def test_game_reads_a_python_file(self):
        ins = sample_inputs(777, seed=3)
        path = os.path.join(self.tmp, "py" + replays.EXT)
        make_file(path, ins, [{"start": 0, "end": 700, "p1": 17, "p2": 6, "stage": 27, "winner": 0, "score": (2, 0)}],
                  bars=[{"kind": 2, "f": 195, "nf": 195, "seed": 5}], slot=1)
        code, out = self.run_exe("read", path)
        self.assertEqual(code, 0, out)
        self.assertIn("SLOT 1 DELAY 2 ROLLBACK 1", out)
        self.assertEqual(int(self.lines(out, "DIGESTPLUS")[0], 16),
                         fnv_digest(list(zip(ins[0], ins[1]))))

    def test_damaged_files_are_refused_with_a_reason(self):
        good = os.path.join(self.tmp, "g" + replays.EXT)
        make_file(good, sample_inputs(50), [{"start": 0, "end": 40, "p1": 1, "p2": 2, "stage": 20, "winner": 0}])
        with open(good, "rb") as f:
            data = f.read()
        cases = {"not a T5DR replay": b"hello", "no data after the header": replays.MAGIC + b"{}",
                 "the data is damaged": data[:-40] + b"x" * 40}
        for why, blob in cases.items():
            p = os.path.join(self.tmp, "bad" + replays.EXT)
            with open(p, "wb") as f:
                f.write(blob)
            code, out = self.run_exe("read", p)
            self.assertEqual(code, 2, out)
            self.assertIn("ERROR " + why, out)
        code, out = self.run_exe("read", os.path.join(self.tmp, "missing" + replays.EXT))
        self.assertIn("ERROR the file cannot be opened", out)

    def test_a_slower_load_renumbers_the_frames(self):
        """A sync point this game reaches later than the recording continues at its own frame; the recorded
        frames are then found that many frames on (and an earlier arrival jumps to the recorded frame)."""
        path = os.path.join(self.tmp, "map" + replays.EXT)
        make_file(path, sample_inputs(400), [{"start": 0, "end": 300, "p1": 1, "p2": 2, "stage": 20, "winner": 0}],
                  bars=[{"kind": 2, "f": 190, "nf": 195, "seed": 5}, {"kind": 1, "f": 300, "nf": 300, "seed": 6}])
        code, out = self.run_exe("map", path, "0:199", "1:304")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.lines(out, "MAP"), ["0 199 199", "1 304 304"])     # 4 frames later: renumbered, then in step
        code, out = self.run_exe("map", path, "0:180", "1:300")
        self.assertEqual(self.lines(out, "MAP"), ["0 180 195", "1 300 300"])     # earlier: on to the recorded frame


if __name__ == "__main__":
    unittest.main()
