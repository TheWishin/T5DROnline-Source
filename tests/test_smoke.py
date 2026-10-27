"""tools/smoke without the game: log parsing, checks, known issues, the
report, process selection, frame heuristics (on synthetic images), and the
runner's error path. The suite itself needs the game; see docs/SMOKE.md."""
import contextlib
import io
import json
import os
import random
import sys
import tempfile
import unittest

from helpers import ROOT

SMOKE = os.path.join(ROOT, "tools", "smoke")
sys.path.insert(0, SMOKE)

import checks  # noqa: E402
import logscan  # noqa: E402
import procs  # noqa: E402
import report  # noqa: E402

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


SAMPLE_LOG = """\
[boot] VFS root: C:/T5DROnline/game/vfs
[hle] unresolved NID 0x224e1610 (cellHttp)
[fps] 59.8 (frames 1..300 over 5.0s)
[audio-rate] 187.4 blocks/s (real time 187.5), silent 0.3%, dropped 0 frames/s, device buf 2400, queue min 3, starved 0, waited for 0 (max 0.0 ms), not written 0
[frame-dump] C:\\x\\dump\\frame_000060.ppm 1280x720 nonblack=921600
[hle] unresolved NID 0x224E1610 (cellHttp)
[DIALOG] Unable to load Play Data.
[DIALOG] Unable to load Play Data.
[fps] 41.2
[CRASH] access violation at 0x0000000000001234
[WATCHDOG] 8s sample; last HLE call = 0x00000000 ()
"""


class LogScan(unittest.TestCase):
    def test_lines(self):
        s = logscan.scan_text(SAMPLE_LOG)
        self.assertEqual([(f.value, f.span) for f in s.fps], [(59.8, 5.0), (41.2, 5.0)])
        self.assertEqual(len(s.audio), 1)
        self.assertEqual((s.audio[0].silent, s.audio[0].blocks, s.audio[0].dropped), (0.3, 187.4, 0.0))
        self.assertEqual(list(s.nids), ["0x224E1610"])           # case-normalised, counted once
        self.assertEqual(s.nids["0x224E1610"].count, 2)
        self.assertEqual(len(s.crashes), 1)
        self.assertEqual(s.frames[0].nonblack, 921600)
        self.assertTrue(s.frames[0].path.endswith("frame_000060.ppm"))
        self.assertEqual(s.watchdogs, 1)
        dialog = [v for k, v in s.notable.items() if k.startswith("dialog:")]
        self.assertEqual(dialog[0][0], 2)                         # repeats counted, first line kept

    def test_feed_keeps_time_and_phase(self):
        s = logscan.LogScanner()
        self.assertEqual(s.feed("[fps] 60.0 (frames 1..301 over 5.0s)\n", 12.5, "title"), "fps")
        self.assertEqual(s.feed("[hle] unresolved NID 0x71714CDC", 13.0, "menu"), "nid-new")
        self.assertEqual(s.feed("[hle] unresolved NID 0x71714CDC", 14.0, "fight"), "nid")
        self.assertEqual(s.fps[0].t, 12.5)
        self.assertEqual(s.fps[0].phase, "title")
        self.assertEqual(s.nids["0x71714CDC"].phases, ["menu", "fight"])
        self.assertIsNone(s.feed("[cellPad] file pad: buttons 0x0000", 15.0, "fight"))

    def test_gaps(self):
        self.assertEqual(logscan.fps_gaps([5, 10, 30], 0, 32)[0], (10, 30))
        self.assertEqual(logscan.fps_gaps([], 0, 100, first_grace=60), [(0, 100)])
        self.assertEqual(logscan.fps_gaps([], 0, 30, first_grace=60), [])


def make_run(**over):
    """A healthy 60-s run: boot, 20 s title, 30 s fight."""
    fps = [[t, 60.0, 5.0, "x"] for t in range(5, 31, 5)] + [[t, 40.0, 5.0, "fight"] for t in range(35, 61, 5)]
    audio = [[t, 0.5, 187.0, 0.0, "x"] for t in range(5, 61, 5)]
    frames = []
    for i, t in enumerate(range(10, 60)):
        fight = t >= 31
        frames.append({"t": float(t), "file": f"frames/frame_{i:06d}.jpg", "mean": 80.0, "std": 40.0,
                       "black": 0.05, "white": 0.0, "diff_prev": 5.0 if i else None,
                       "fight": {"is_fight": fight, "hud": 1.0 if fight else 0.0, "spikes": 0.01}})
    run = {
        "name": "t", "dir": "x", "duration": 61.0, "exit_code": None, "start_error": None, "aborted": None,
        "phases": [["start", "boot", 0.0, 10.0], ["title", "title", 10.0, 30.0], ["fight", "fight", 30.0, None]],
        "fps": fps, "audio": audio, "crashes": [], "nids": {"0x224E1610": {"first_phase": "start", "count": 1}},
        "mem": [[t, "x", 800.0, 1000.0 + t] for t in range(0, 61, 2)],
        "frames": frames, "shots": {}, "contention": {"games": 0, "builds": 0, "names": []},
        "expects": [{"name": "title", "ok": True, "detail": "ok"}],
    }
    run.update(over)
    return run


def by_id(cs):
    return {c["id"]: c for c in cs}


class Checks(unittest.TestCase):
    known = {"0x224E1610"}

    def test_healthy_run_passes(self):
        cs = by_id(checks.evaluate(make_run(), known_nids=self.known))
        bad = {k: c for k, c in cs.items() if c["status"] not in ("pass", "info", "skip")}
        self.assertEqual(bad, {})
        self.assertEqual(cs["fps.title"]["value"], 60.0)
        self.assertEqual(cs["fps.fight"]["status"], "info")       # fights are reported, not judged
        self.assertEqual(cs["fighters"]["status"], "pass")
        self.assertEqual(cs["reach.title"]["status"], "pass")

    def test_crash_and_early_exit(self):
        cs = by_id(checks.evaluate(make_run(crashes=[[20.0, "[CRASH] access violation", "title"]])))
        self.assertEqual(cs["no-crash"]["status"], "fail")
        self.assertIn("access violation", cs["no-crash"]["detail"])
        cs = by_id(checks.evaluate(make_run(aborted="game exited (code 3) in phase title")))
        self.assertEqual(cs["no-crash"]["status"], "fail")

    def test_hang(self):
        run = make_run()
        run["fps"] = [f for f in run["fps"] if not 12 < f[0] < 30]      # 15 s without a frame
        c = by_id(checks.evaluate(run))["no-hang"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("from 10s", c["detail"])
        c = by_id(checks.evaluate(make_run(fps=[])))["no-hang"]
        self.assertEqual(c["status"], "fail")
        late = make_run(fps=[[70.0, 60.0, 5.0, "x"]], duration=75.0)
        self.assertIn("first [fps] line only at 70s", by_id(checks.evaluate(late))["no-hang"]["detail"])

    def test_slow_kill_is_no_hang(self):
        # the harness stopped the game 1 s after the last [fps] line and the kill took 24 s
        run = make_run()
        last = max(f[0] for f in run["fps"])
        run["duration"] = last + 25.0
        run["events"] = list(run.get("events", [])) + [[last + 1.0, "title", "stop", "alive=True"]]
        self.assertEqual(by_id(checks.evaluate(run))["no-hang"]["status"], "pass")
        run["events"] = []                                   # no stop event: the old end
        self.assertEqual(by_id(checks.evaluate(run))["no-hang"]["status"], "fail")

    def test_menu_fps_threshold_and_contention(self):
        run = make_run()
        for f in run["fps"]:
            if f[0] <= 30:
                f[1] = 50.0
        self.assertEqual(by_id(checks.evaluate(run))["fps.title"]["status"], "fail")
        run["contention"] = {"games": 2, "builds": 0, "names": ["t5dr.exe"]}
        c = by_id(checks.evaluate(run))["fps.title"]
        self.assertEqual(c["status"], "warn")
        self.assertIn("2 other t5dr.exe", c["detail"])
        self.assertEqual(by_id(checks.evaluate(run, strict=True))["fps.title"]["status"], "fail")
        self.assertEqual(by_id(checks.evaluate(run, thresholds={"fps_min.title": 45}))["fps.title"]["status"], "pass")

    def test_fps_window_must_fit_the_phase(self):
        run = make_run(phases=[["start", "boot", 0.0, 10.0], ["title", "title", 10.0, 13.0],
                               ["fight", "fight", 13.0, None]])
        self.assertEqual(by_id(checks.evaluate(run))["fps.title"]["status"], "skip")

    def test_audio(self):
        run = make_run()
        for a in run["audio"]:
            if a[0] > 35:
                a[1] = 40.0
        c = by_id(checks.evaluate(run))["audio.fight"]
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["value"], 40.0)
        self.assertEqual(by_id(checks.evaluate(make_run(audio=[])))["audio.fight"]["status"], "skip")

    def test_new_nid(self):
        run = make_run(nids={"0x224E1610": {"first_phase": "start", "count": 1},
                             "0xDEADBEEF": {"first_phase": "fight", "count": 3}})
        c = by_id(checks.evaluate(run, known_nids=self.known))["nids"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("0xDEADBEEF", c["detail"])
        self.assertNotIn("0x224E1610", c["detail"])

    def test_memory(self):
        run = make_run(mem=[[t, "x", 800.0, 1000.0 + (500 if t > 40 else 0)] for t in range(0, 61, 2)])
        c = by_id(checks.evaluate(run))["memory"]
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["value"], 500.0)
        # a long run whose second half keeps growing
        long_run = make_run(duration=600.0, mem=[[t, "x", 800.0, 1000.0 + t * 0.5] for t in range(0, 601, 10)])
        long_run["phases"][-1][3] = 600.0
        c = by_id(checks.evaluate(long_run, thresholds={"mem_growth_mb": 1000}))["memory"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("MB/min", c["detail"])
        # an idle run starts its only phase at boot: the baseline waits for boot to settle
        idle = make_run(duration=600.0, phases=[["idle", "idle", 0.0, 600.0]],
                        fps=[[t, 60.0, 5.0, "idle"] for t in range(5, 600, 5)],
                        mem=[[t, "idle", 800.0, min(1000.0, 50.0 * t)] for t in range(0, 601, 10)])
        c = by_id(checks.evaluate(idle))["memory"]
        self.assertEqual(c["status"], "pass", c["detail"])

    def test_white_and_frozen_screens(self):
        run = make_run()
        for f in run["frames"]:
            if f["t"] >= 31:
                f.update(white=1.0, std=0.0, mean=255.0, diff_prev=0.0)
        cs = by_id(checks.evaluate(run))
        self.assertEqual(cs["picture.fight"]["status"], "fail")
        self.assertIn("white", cs["picture.fight"]["detail"])
        self.assertEqual(cs["frozen.fight"]["status"], "fail")
        self.assertEqual(cs["picture.title"]["status"], "pass")

    def test_fighters(self):
        run = make_run()
        for f in run["frames"]:
            f["fight"]["spikes"] = 0.2
        c = by_id(checks.evaluate(run))["fighters"]
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["value"], 0.2)
        run = make_run()
        for f in run["frames"]:
            f["fight"]["is_fight"] = False
        self.assertIn("no frame with the fight HUD", by_id(checks.evaluate(run))["fighters"]["detail"])

    def test_shots_and_expects(self):
        good = {"mean": 80, "std": 40, "black": 0, "white": 0}
        run = make_run(shots={
            "a": {"expect": "content", "frame": good, "file": "a.png"},
            "b": {"expect": "content", "frame": dict(good, black=1.0), "file": "b.png"},
            "c": {"expect": "fight", "frame": good, "fight": {"is_fight": False, "hud": 0.1}, "file": "c.png"},
            "d": {"expect": "any", "frame": None},
            "e": {"expect": "content", "frame": None},
        }, expects=[{"name": "fight", "ok": False, "detail": "no HUD"}])
        cs = by_id(checks.evaluate(run))
        self.assertEqual(cs["shot.a"]["status"], "pass")
        self.assertEqual(cs["shot.b"]["status"], "fail")
        self.assertEqual(cs["shot.c"]["status"], "fail")
        self.assertNotIn("shot.d", cs)
        self.assertEqual(cs["shot.e"]["status"], "fail")
        self.assertEqual(cs["reach.fight"]["status"], "fail")
        self.assertEqual(cs["shot.a"]["evidence"], "a.png")

    def test_guest_faults(self):
        run = make_run(notable=[{"kind": "null-call", "count": 4, "t": 50.0, "phase": "fight",
                                 "line": "[null-call] guest called a NULL function pointer"},
                                {"kind": "dialog", "count": 1, "t": 1.0, "phase": "start", "line": "[DIALOG] x"}])
        c = by_id(checks.evaluate(run))["guest-faults"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("4 line(s); first at 50s in fight", c["detail"])
        self.assertEqual(by_id(checks.evaluate(make_run()))["guest-faults"]["status"], "pass")

    def test_start_error(self):
        cs = checks.evaluate(make_run(start_error="no such file: t5dr.exe"))
        self.assertEqual([c["id"] for c in cs], ["start"])


class KnownIssues(unittest.TestCase):
    KNOWN = [{"issue": "QA-1", "test": "title_twice", "check": "*title3*"},
             {"issue": "QA-1", "test": "title_twice", "check": "no-hang", "detail": "title3"},
             {"issue": "QA-9", "test": "*", "check": "nids", "expect": "maybe"}]

    def test_marking(self):
        cs = [checks.check("picture.title3", "fail"), checks.check("shot.title3-10s", "pass"),
              checks.check("picture.title2", "fail"), checks.check("no-hang", "fail", "no frames from 9s (title1)"),
              checks.check("nids", "pass")]
        checks.apply_known("title_twice", cs, self.KNOWN)
        self.assertEqual([c["status"] for c in cs], ["known-fail", "pass", "fail", "fail", "pass"])
        self.assertEqual(cs[0]["issue"], "QA-1")
        self.assertNotIn("issue", cs[3])                          # detail regex did not match: a real hang
        cs = [checks.check("no-hang", "fail", "no frames for 16s from 121s (title3)")]
        checks.apply_known("title_twice", cs, self.KNOWN)
        self.assertEqual(cs[0]["status"], "known-fail")
        cs = [checks.check("picture.title3", "fail")]
        checks.apply_known("other_test", cs, self.KNOWN)
        self.assertEqual(cs[0]["status"], "fail")
        cs = [checks.check("fps.title3", "warn", "unreliable: 3 other t5dr.exe")]
        checks.apply_known("title_twice", cs, self.KNOWN)      # a WARN is no evidence: stays WARN
        self.assertEqual([c["status"] for c in cs], ["warn", "xpass"])

    def test_xpass_once_per_issue(self):
        cs = [checks.check("picture.title3", "pass"), checks.check("no-hang", "pass")]
        checks.apply_known("title_twice", cs, self.KNOWN)
        self.assertEqual([c["id"] for c in cs if c["status"] == "xpass"], ["known.QA-1"])
        cs = [checks.check("nids", "pass")]
        checks.apply_known("anything", cs, self.KNOWN)            # QA-9 is expect=maybe: no xpass
        self.assertEqual([c["status"] for c in cs], ["pass"])

    def test_status_order(self):
        self.assertEqual(checks.test_status([checks.check("a", "pass"), checks.check("b", "known-fail")]), "known-fail")
        self.assertEqual(checks.test_status([checks.check("a", "warn"), checks.check("b", "fail")]), "fail")
        self.assertEqual(checks.test_status([checks.check("a", "info"), checks.check("b", "skip")]), "pass")

    def test_shipped_file(self):
        with open(os.path.join(SMOKE, "known_issues.json"), encoding="utf-8") as f:
            known = json.load(f)
        import scenarios
        for k in known["failures"]:
            self.assertRegex(k["issue"], r"^[A-Z]+-\d+$")
            self.assertIn(k["test"], scenarios.TESTS, k)          # no stale test names
            self.assertTrue(k.get("note"), k)
        for nid in known["nids"]:
            self.assertRegex(nid, r"^0x[0-9A-F]{8}$")


class Report(unittest.TestCase):
    def sample(self):
        return [
            {"name": "boot_menu", "duration": 50, "checks": [checks.check("no-crash", "pass", "ok"),
                                                              checks.check("fps.title", "warn", "median 45 | low")]},
            {"name": "title_twice", "duration": 90, "checks": [
                dict(checks.check("picture.title3", "known-fail", "white", evidence="frames/f.jpg"), issue="QA-1")]},
        ]

    def test_exit_codes(self):
        t = self.sample()
        self.assertEqual(report.exit_code(t), 0)                  # warn and known-fail do not fail the suite
        t[0]["checks"].append(checks.check("no-hang", "fail", "x"))
        self.assertEqual(report.exit_code(t), 1)
        t[1]["error"] = "no such file"
        self.assertEqual(report.exit_code(t), 2)

    def test_markdown_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            md = report.write(d, {"suite": "quick", "exe": "t5dr.exe", "duration": 140}, self.sample())
            self.assertTrue(md.startswith("# Smoke suite: PASS"))
            self.assertIn("**KNOWN** (QA-1) `title_twice` `picture.title3`", md)
            self.assertIn("[f.jpg](title_twice/frames/f.jpg)", md)
            self.assertIn("median 45 \\| low", md)                # table cells escaped
            with open(os.path.join(d, "report.json"), encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(doc["exit_code"], 0)
            self.assertEqual(doc["counts"], {"pass": 1, "warn": 1, "known-fail": 1})


class Procs(unittest.TestCase):
    P = procs.Proc

    def test_descendants(self):
        ps = [self.P(1, 0, "python.exe"), self.P(2, 1, "t5dr.exe"), self.P(3, 2, "ffmpeg.exe"),
              self.P(4, 9, "t5dr.exe"), self.P(5, 2, "conhost.exe")]
        self.assertEqual(sorted(p.pid for p in procs.descendants(ps, 1)), [2, 3, 5])
        self.assertEqual(sorted(p.pid for p in procs.descendants(ps, 2)), [3, 5])
        # pid 5 claims parent 2 but is older than it: a reused PID, not ours
        created = {1: 10, 2: 20, 3: 30, 5: 5}
        self.assertEqual(sorted(p.pid for p in procs.descendants(ps, 2, created)), [3])
        self.assertEqual(procs.descendants([self.P(7, 7, "x")], 7), [])     # self-parented

    def test_contention(self):
        ps = [self.P(2, 1, "t5dr.exe"), self.P(4, 9, "t5dr.exe"), self.P(6, 9, "clang-cl.exe"),
              self.P(8, 9, "notepad.exe")]
        c = procs.contention(ps, ours={2})
        self.assertEqual((c["games"], c["builds"]), (1, 1))
        self.assertEqual(c["names"], ["clang-cl.exe", "t5dr.exe"])

    @unittest.skipUnless(sys.platform == "win32", "Windows process APIs")
    def test_live_list_has_us(self):
        me = os.getpid()
        self.assertIn(me, {p.pid for p in procs.list_processes()})
        self.assertIsNotNone(procs.memory(me))


@unittest.skipUnless(HAVE_PIL, "Pillow not installed")
class Frames(unittest.TestCase):
    def setUp(self):
        import frames
        from PIL import Image, ImageDraw
        self.f, self.Image, self.Draw = frames, Image, ImageDraw
        rnd = random.Random(5)
        # a "stage": coarse random texture everywhere (every 16x16 block varies)
        self.noise = Image.frombytes("L", (320, 180), bytes(rnd.randrange(30, 220) for _ in range(320 * 180)))

    def textured(self):
        return self.noise.resize((1280, 720), self.Image.NEAREST).convert("RGB")

    def with_hud(self, im, damage=0):
        d = self.Draw.Draw(im)
        for x0, x1 in ((70, 575), (712, 1220)):
            for y, col in ((58, (24, 166, 140)), (62, (74, 243, 198)), (66, (0, 121, 99)), (70, (5, 179, 156))):
                d.line([(x0, y), (x1, y)], fill=col, width=4)
            if damage:
                for y, col in ((62, (84, 6, 4)), (70, (66, 0, 0))):
                    d.line([(x0, y), (x0 + damage, y)], fill=col, width=4)
            d.line([(x0, 74), (x1, 74)], fill=(7, 7, 7), width=3)
        return im

    def spikes(self, im):
        d = self.Draw.Draw(im)
        for i, (a, b) in enumerate((((640, 420), (0, 680)), ((640, 420), (180, 680)), ((600, 400), (1280, 600)),
                                    ((640, 430), (1100, 680)))):
            shade = 200 + 10 * i
            d.polygon([a, b, (b[0] + 260, b[1] - 120)], fill=(shade, shade - 30, shade - 20))
        return im

    def test_classify(self):
        f = self.f
        black = f.stats(self.Image.new("RGB", (1280, 720)))[0]
        white = f.stats(self.Image.new("RGB", (1280, 720), (255, 255, 255)))[0]
        flat = f.stats(self.Image.new("RGB", (1280, 720), (90, 20, 20)))[0]
        content, thumb = f.stats(self.textured())
        self.assertEqual([f.classify(r) for r in (black, white, flat, content, None)],
                         ["black", "white", "flat", "content", "missing"])
        same = f.stats(self.textured(), thumb)[0]
        self.assertEqual(same["diff_prev"], 0.0)
        self.assertTrue(f.frozen([0.0, 0.1, 0.0]))
        self.assertFalse(f.frozen([0.0, 4.0]))
        self.assertFalse(f.frozen([None]))

    def test_hud(self):
        f = self.f
        self.assertGreaterEqual(f.hud_score(self.with_hud(self.textured())), 0.99)
        self.assertGreaterEqual(f.hud_score(self.with_hud(self.textured(), damage=300)), 0.99)
        self.assertLess(f.hud_score(self.textured()), 0.2)
        self.assertLess(f.hud_score(self.Image.new("RGB", (1280, 720))), 0.01)     # black is not a damaged bar
        small = self.with_hud(self.textured()).resize((640, 360))                    # scaled back up first
        self.assertGreaterEqual(f.hud_score(small), 0.8)

    def test_spikes(self):
        f = self.f
        good = f.fight_check(self.with_hud(self.textured()))
        bad = f.fight_check(self.spikes(self.with_hud(self.textured())))
        self.assertTrue(good["is_fight"] and bad["is_fight"])
        self.assertLess(good["spikes"], 0.01)
        self.assertGreater(bad["spikes"], f.SPIKE_LIMIT)
        self.assertEqual(f.fighters_verdict([0.01, 0.02, 0.5]), (True, 0.02, 0.5))       # one odd frame is not enough
        self.assertEqual(f.fighters_verdict([0.2, 0.3, 0.01])[0], False)
        self.assertEqual(f.fighters_verdict([]), (None, None, None))

    def test_dark_smooth_areas_do_not_count(self):
        f = self.f
        im = self.with_hud(self.textured())
        self.Draw.Draw(im).rectangle([0, 300, 1280, 700], fill=(10, 10, 12))         # a dark night floor
        self.assertLess(f.spike_score(im), 0.01)


def smoke_run():
    """tools/smoke/run.py by its path: a plain "import run" took lobby/run.py whenever an earlier test (the launcher's
    Replays tab tests) left lobby/ ahead of tools/smoke on sys.path."""
    import importlib.util
    mod = sys.modules.get("t5dr_smoke_run")
    if mod is None:
        spec = importlib.util.spec_from_file_location("t5dr_smoke_run", os.path.join(SMOKE, "run.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["t5dr_smoke_run"] = mod
        spec.loader.exec_module(mod)
    return mod


class Runner(unittest.TestCase):
    def test_list_and_missing_exe(self):
        run = smoke_run()
        import scenarios
        quick = {t["name"] for t in scenarios.tests_for("quick")}
        self.assertEqual(quick, {"boot_menu", "arcade_fight", "vs_two_pads", "practice", "title_twice"})
        self.assertTrue({"ghost", "survival_loop", "options", "gallery_offline", "save_reload",
                         "idle_attract"} <= {t["name"] for t in scenarios.tests_for("full")})
        self.assertLessEqual(sum(t["budget"] for t in scenarios.tests_for("quick")), 6 * 60)
        self.assertLessEqual(sum(t["budget"] for t in scenarios.tests_for("full")), 25 * 60)
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            code = run.main(["--exe", os.path.join(d, "missing.exe"), "--only", "boot_menu", "--out", d,
                             "--shader-cache", "", "--quiet"])
            self.assertEqual(code, 2)
            with open(os.path.join(d, "report.md"), encoding="utf-8") as f:
                md = f.read()
            self.assertIn("# Smoke suite: ERROR", md)
            self.assertIn("missing.exe", md)

    def test_game_command(self):
        from game import Game
        with tempfile.TemporaryDirectory() as d:
            g = Game(os.path.join(d, "t"), exe=os.path.join(d, "my.exe"), root=d, env={"X_TEST": "1"})
            argv, env, cwd = g.command()
        self.assertEqual(argv[0], os.path.join(d, "my.exe"))
        self.assertTrue(argv[1].endswith("EBOOT.elf"))
        self.assertEqual(cwd, os.path.join(d, "t", "cwd"))
        for k in ("PS3_WINDOW_BACKGROUND", "PS3_PAD_FILE", "PS3_PAD_FILE2", "AUDIO_RATE", "LD_FRAME_DUMP"):
            self.assertIn(k, env)
        if sys.platform != "darwin":                                 # run_game.py's defaults come along
            self.assertEqual(env["RSX_LIVE_DRAW"], "1")
        self.assertEqual(env["X_TEST"], "1")
        self.assertNotIn("\\", env["PS3_PAD_FILE"])

    def test_bad_threshold(self):
        run = smoke_run()
        with self.assertRaises(SystemExit):
            run.parse_set(["fps_min.nope=3"])
        self.assertEqual(run.parse_set(["fps_min.menu=50"]), {"fps_min.menu": 50.0})


if __name__ == "__main__":
    unittest.main()
