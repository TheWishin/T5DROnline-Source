"""The launcher's profile picture capture (launcher/profile_pic.py, docs/ONLINE.md "Profile picture").

A stand-in game (a small Python script speaking the real game's side of the contract: the [df] log lines, the
RSX_TEST_BB_SHOT request file, PPM pictures) takes the place of t5dr.exe. Covers: what the save says is customized;
the cache key follows only what a costume wears; the capture game's environment (offline direct fight, the save's
copy, a throw-away save folder, hidden and muted, nothing of netplay); the buttons tried until the customized
costume shows; pictures cached and taken again only after the customization changed; a fighter that is not
customized gets no picture; a game that never reaches the fight, ends early or is stopped; what a killed run left
behind does not block the next; the player's save is never written; the frame choice.
"""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "launcher"), os.path.join(ROOT, "lobby"), os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import profile_pic as pp  # noqa: E402
from t5lobby import picfmt  # noqa: E402

FAKE_GAME = textwrap.dedent('''
    import os, sys, time
    env = os.environ
    with open("fake_pid.txt", "w") as f:
        f.write(str(os.getpid()))
    with open("fake_env.txt", "a") as f:
        f.write(repr({k: v for k, v in env.items() if k.startswith(("T5_", "PS3_", "RSX_", "LD_"))}) + "\\n")
    mode = env.get("FAKE_MODE", "")
    fight = env["T5_FIGHT"]
    ids, buttons = fight.split(" ")[0].split(","), fight.split("buttons=")[1].split("|")
    fid, button = int(ids[0]), int(buttons[0])
    item = fid - 1                                   # (the game's item character index is not the fighter id)
    costume = 1 if button in (1, 2) else 2
    data = open(env["T5_COSTUME_SAVE"], "rb").read()
    blk = data[0x820 + item * 0x108:0x820 + (item + 1) * 0x108]
    def custom(k):
        c = blk[(k - 1) * 0x58:k * 0x58]
        return any(c[64 + 2 * i:66 + 2 * i] not in (b"\\xff\\xff", b"\\0\\0") for i in range(4)) or any(v != 255 for v in c[84:87])
    any_custom = any(custom(k) for k in (1, 2, 3))
    def say(s):
        print(s, flush=True)
    say("[boot] something else")
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        sys.exit(3)
    say("[df] frame 100: fighters: P1 X with Y (model 0x%X)" % costume)
    say("[df] frame 100: costumes written: P1 item char %d (fighter 0x10090040): %s, P2 item char 0 (fighter 0x1): "
        "nothing customized; blocks hash 00" % (item, "custom" if any_custom else "nothing customized"))
    if not any_custom:
        say("[df] frame 100: costumes worn: P1 default; P2 default")
    elif custom(costume) and mode != "refused":
        say("[df] frame 100: costumes worn: P1 costume %d (model 0x25): parts 03,-,0D,- colours 1,-,-; P2 default" % costume)
    else:
        say("[df] frame 100: costumes worn: P1 costume %d (model 0x24): nothing worn, customized: costume 2; P2 default" % costume)
    say("[df] frame 300: costumes: blocks hash 0000000000000000 after the loading")
    req = env["RSX_TEST_BB_SHOT"]
    w, h = 160, 90
    n = 0
    t_end = time.time() + 30
    while time.time() < t_end:
        if os.path.exists(req):
            out = open(req).read().strip()
            os.remove(req)
            n += 1
            px = bytearray()
            for y in range(h):
                for x in range(w):
                    if mode == "black" or (mode == "fade" and n == 2):
                        px += b"\\0\\0\\0"
                    else:
                        px += bytes(((x * 3 + n * 40 + button * 20) & 255, (y * 2 + data[0x820 + item * 0x108 + 0x58 + 64 + 1]) & 255, (x ^ y) & 255))
            with open(out, "wb") as f:
                f.write(b"P6\\n%d %d\\n255\\n" % (w, h) + bytes(px))
        time.sleep(0.01)
''')


def make_save(custom=None):
    """A SYS-DATA with `custom`: {item char: {costume: (part, colour)}}."""
    data = bytearray(os.urandom(pp.SAVE_OFFSET)) + bytearray(pp.ITEM_CHARS * pp.BLOCK) + bytearray(os.urandom(64))
    for c in range(pp.ITEM_CHARS):
        for k in range(3):
            base = pp.SAVE_OFFSET + c * pp.BLOCK + k * pp.COSTUME
            data[base + 64:base + 72] = b"\xff" * 8
            data[base + 84:base + 87] = b"\xff" * 3
    for c, costumes in (custom or {}).items():
        for k, (part, colour) in costumes.items():
            base = pp.SAVE_OFFSET + c * pp.BLOCK + (k - 1) * pp.COSTUME
            if part is not None:
                data[base + 64:base + 66] = struct.pack(">H", part)
            if colour is not None:
                data[base + 84] = colour
    return bytes(data)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(self.out)
        self.fake = os.path.join(self.tmp.name, "fake_game.py")
        with open(self.fake, "w", encoding="utf-8") as f:
            f.write(FAKE_GAME)
        self.save = os.path.join(self.tmp.name, "player", "SYS-DATA")
        os.makedirs(os.path.dirname(self.save))
        self.mode = ""
        self.runs = 0

    def tearDown(self):
        self.tmp.cleanup()

    def write_save(self, custom):
        with open(self.save, "wb") as f:
            f.write(make_save(custom))

    def command(self, out, env_over):
        self.runs += 1
        env = dict(os.environ)
        for k in [k for k in env if k.startswith(("T5_", "PS3_", "RSX_", "LD_"))]:
            del env[k]
        for k, v in env_over.items():
            if v is not None:
                env[k] = str(v)
        env["FAKE_MODE"] = self.mode
        return [sys.executable, self.fake], env, out

    def refresh(self, fighter="kazuya", fid=15, **kw):
        kw.setdefault("boot_timeout", 20.0)
        kw.setdefault("shot_times", (0.05, 0.15, 0.25, 0.35))
        return pp.refresh(self.out, fighter, fid, 0, self.save, command=self.command, **kw)

    def envs(self):
        with open(os.path.join(self.out, "fake_env.txt"), encoding="utf-8") as f:
            return [eval(line) for line in f if line.strip()]     # noqa: S307 -- our own stand-in's output


class SaveTest(unittest.TestCase):
    def test_customized_and_key(self):
        data = make_save({14: {2: (3, 1)}, 31: {1: (None, 0), 3: (7, None)}})
        self.assertEqual(pp.customized(pp.block(data, 14)), [2])
        self.assertEqual(pp.customized(pp.block(data, 31)), [1, 3])
        self.assertEqual(pp.customized(pp.block(data, 0)), [])
        self.assertIsNone(pp.block(data, 36))
        self.assertIsNone(pp.block(data, -1))
        self.assertIsNone(pp.block(data[:pp.SAVE_OFFSET + 50], 0))
        # the key: only what the costume wears -- not the rest of the save, not other costumes or fighters
        key = pp.block_key(pp.block(data, 14), 2)
        other = bytearray(data)
        other[0:pp.SAVE_OFFSET] = os.urandom(pp.SAVE_OFFSET)                 # the rest of the save (options, records)
        other[pp.SAVE_OFFSET + 14 * pp.BLOCK + 10] ^= 0xFF                   # an item bought, costume 1
        other[pp.SAVE_OFFSET + 31 * pp.BLOCK + 70] ^= 0xFF                   # another fighter
        self.assertEqual(pp.block_key(pp.block(bytes(other), 14), 2), key)
        changed = make_save({14: {2: (4, 1)}})
        self.assertNotEqual(pp.block_key(pp.block(changed, 14), 2), key)
        self.assertNotIn(b"SYS-DATA", key.encode())
        self.assertEqual(len(key), 32)

    def test_a_part_of_zero_is_nothing_worn(self):
        data = make_save({5: {1: (0, None)}})
        self.assertEqual(pp.customized(pp.block(data, 5)), [])

    def test_game_env(self):
        env = pp.game_env("15,0,0,1 buttons=3|1", "profile-pics/work/SYS-DATA", "profile-pics/work")
        self.assertEqual(env["T5_FIGHT"], "15,0,0,1 buttons=3|1")
        self.assertEqual(env["PS3_SAVEDATA_DIR"], "./profile-pics/work/save")
        for k in ("T5_NET_MODE", "T5_CTL_DIR", "T5_FIGHT_FILE", "T5_REPLAY_DIR", "T5_REPLAY_LIVE", "T5_UNLOCK_ITEMS",
                  "T5_NET_RESULT_FILE"):
            self.assertIsNone(env[k], k)                         # (None: taken out of an inherited environment too)
        for k in ("PS3_WINDOW_HIDDEN", "PS3_WINDOW_BACKGROUND", "PS3_AUDIO_MUTE", "PS3_NO_DIALOGS"):
            self.assertEqual(env[k], "1")
        for v in env.values():                                   # nothing absolute: no path of this PC in the game's log
            self.assertFalse(isinstance(v, str) and (":" in v and "\\" in v), v)


class RefreshTest(Case):
    def test_customized_costume_found_cached_and_retaken(self):
        self.write_save({14: {2: (3, 1)}})
        before = hashlib.sha256(open(self.save, "rb").read()).hexdigest()
        r = self.refresh()
        self.assertEqual((r["state"], r["ran"], [k for k, _ in r["pics"]]), ("ok", 2, [2]))   # button 1, then 3
        png = r["pics"][0][1]
        self.assertEqual(picfmt.clean(png), png)
        self.assertLessEqual(len(png), picfmt.MAX_BYTES)
        self.assertEqual(picfmt.decode(png)[:2], (picfmt.MAX_W, picfmt.MAX_H))
        envs = self.envs()
        self.assertEqual([e["T5_FIGHT"] for e in envs], ["15,0,0,1 buttons=1|1", "15,0,0,1 buttons=3|1"])
        for e in envs:
            self.assertFalse({"T5_NET_MODE", "T5_CTL_DIR", "T5_REPLAY_DIR", "T5_FIGHT_FILE"} & set(e))
            self.assertTrue(e["PS3_SAVEDATA_DIR"].startswith("./profile-pics/work/"))
            self.assertEqual(e["T5_COSTUME_SAVE"], "profile-pics/work/SYS-DATA")
        self.assertEqual(hashlib.sha256(open(self.save, "rb").read()).hexdigest(), before)   # the save: untouched
        self.assertFalse(os.path.exists(os.path.join(self.out, "profile-pics", "work")))     # nothing left behind
        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "profile-pics"))), ["index.json", "kazuya-2.png"])
        # again: from the cache, no game
        r2 = self.refresh()
        self.assertEqual((r2["state"], r2["ran"], r2["pics"]), ("ok", 0, [(2, png)]))
        self.assertEqual(self.runs, 2)
        # something else in the save changed (another fighter, the options): still no game
        self.write_save({14: {2: (3, 1)}, 20: {1: (9, None)}})
        self.assertEqual(self.refresh()["ran"], 0)
        # the costume changed: one game (the button is known now), a new picture
        self.write_save({14: {2: (5, 1)}})
        r3 = self.refresh()
        self.assertEqual((r3["state"], r3["ran"]), ("ok", 1))
        self.assertNotEqual(r3["pics"][0][1], png)
        self.assertEqual(self.envs()[-1]["T5_FIGHT"], "15,0,0,1 buttons=3|1")
        # the index holds no path and nothing of the save but the keys
        text = open(os.path.join(self.out, "profile-pics", "index.json"), encoding="utf-8").read()
        self.assertNotIn(self.tmp.name.replace("\\", "\\\\"), text)
        self.assertNotIn("SYS-DATA", text)

    def test_two_costumes(self):
        self.write_save({14: {1: (2, None), 2: (3, 1)}})
        r = self.refresh()
        self.assertEqual((r["state"], r["ran"], [k for k, _ in r["pics"]]), ("ok", 2, [1, 2]))
        self.assertNotEqual(r["pics"][0][1], r["pics"][1][1])

    def test_not_customized_no_picture(self):
        self.write_save({20: {1: (9, None)}})
        r = self.refresh()
        self.assertEqual((r["state"], r["pics"], r["ran"]), ("none", [], 1))       # one game to learn the fighter
        self.assertEqual(self.refresh()["ran"], 0)                                   # then the cache knows
        self.assertEqual(self.refresh()["state"], "none")
        # customized later: taken
        self.write_save({14: {1: (2, None)}})
        r = self.refresh()
        self.assertEqual((r["state"], [k for k, _ in r["pics"]]), ("ok", [1]))

    def test_costume_no_button_reaches(self):
        self.write_save({14: {3: (2, None)}})              # the stand-in's buttons give costumes 1 and 2 only
        r = self.refresh()
        self.assertEqual((r["state"], r["pics"]), ("ok", []))
        self.assertLessEqual(r["ran"], pp.MAX_RUNS)
        runs = self.runs
        self.assertEqual(self.refresh()["ran"], 0)         # remembered: never tried again for this customization
        self.assertEqual(self.runs, runs)

    def test_game_refuses_the_customization(self):
        self.mode = "refused"
        self.write_save({14: {1: (2, None)}})
        r = self.refresh()
        self.assertEqual((r["state"], r["pics"]), ("ok", []))
        self.assertEqual(self.refresh()["ran"], 0)

    def test_game_never_reaches_the_fight(self):
        self.mode = "hang"
        self.write_save({14: {1: (2, None)}})
        r = self.refresh(boot_timeout=1.0)
        self.assertEqual((r["state"], r["ran"]), ("failed", 1))
        self.assertIn("in time", r["error"])
        self.mode = "crash"
        r = self.refresh()
        self.assertEqual(r["state"], "failed")
        self.assertIn("ended early", r["error"])
        self.mode = "black"                                # pictures that show nothing
        r = self.refresh()
        self.assertEqual((r["state"], r["error"]), ("failed", "no usable picture"))
        self.mode = ""                                     # and then it works: nothing stale blocks it
        r = self.refresh()
        self.assertEqual(r["state"], "ok")

    def test_left_behind_by_a_killed_run(self):
        self.write_save({14: {1: (2, None)}})
        work = os.path.join(self.out, "profile-pics", "work")
        os.makedirs(os.path.join(work, "save"))
        for name, data in (("shot.req", b"profile-pics/work/old.ppm"), ("f0.ppm", b"P6 broken"), ("game.log", b"x"),
                           ("SYS-DATA", b"old")):
            with open(os.path.join(work, name), "wb") as f:
                f.write(data)
        with open(os.path.join(self.out, "profile-pics", "index.json"), "w") as f:
            f.write("{ cut short")
        with open(os.path.join(self.out, "profile-pics", "index.json.tmp"), "w") as f:
            f.write("{")
        r = self.refresh()
        self.assertEqual((r["state"], [k for k, _ in r["pics"]]), ("ok", [1]))
        # a picture file damaged on disk is taken again, never shown
        with open(pp.pic_path(self.out, "kazuya", 1), "wb") as f:
            f.write(b"\x89PNG broken")
        r = self.refresh()
        self.assertEqual((r["state"], r["ran"]), ("ok", 1))

    def test_stop(self):
        self.mode = "hang"
        self.write_save({14: {1: (2, None)}})
        stop = threading.Event()
        threading.Timer(0.5, stop.set).start()
        r = self.refresh(stop=stop, boot_timeout=30.0)
        self.assertEqual((r["state"], r["error"]), ("failed", "stopped"))

    def test_no_save_no_game(self):
        r = self.refresh()                                 # the save file does not exist
        self.assertEqual(r["state"], "failed")
        self.assertEqual(self.runs, 0)
        self.assertIn("save", r["error"])

    def test_game_not_built(self):
        self.write_save({14: {1: (2, None)}})
        r = pp.refresh(self.out, "kazuya", 15, 0, self.save,
                       command=lambda out, env: ([os.path.join(out, "nowhere", "t5dr.exe")], dict(os.environ), out))
        self.assertEqual((r["state"], r["error"]), ("failed", "the game is not built"))


@unittest.skipUnless(os.name == "nt", "the kill-on-close job is Windows")
class LauncherGoneTest(Case):
    @staticmethod
    def alive(pid):
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True,
                             creationflags=0x08000000).stdout or b""
        return f'"{pid}"'.encode() in out

    def test_a_killed_launcher_leaves_no_hidden_game(self):
        self.write_save({14: {1: (2, None)}})
        driver = os.path.join(self.tmp.name, "driver.py")
        with open(driver, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(f"""
                import os, sys
                sys.path[:0] = {[os.path.join(ROOT, "launcher"), os.path.join(ROOT, "lobby"), os.path.join(ROOT, "tools")]!r}
                import profile_pic as pp
                def command(out, env_over):
                    env = dict(os.environ, FAKE_MODE="hang")
                    env.update({{k: str(v) for k, v in env_over.items() if v is not None}})
                    return [sys.executable, {self.fake!r}], env, out
                pp.run_game_once({self.out!r}, 15, 0, 1, {self.save!r}, command=command, boot_timeout=120)
            """))
        launcher = subprocess.Popen([sys.executable, driver], creationflags=0x08000000)
        try:
            pid_file = os.path.join(self.out, "fake_pid.txt")
            t_end = time.monotonic() + 30
            while not os.path.exists(pid_file) and time.monotonic() < t_end:
                time.sleep(0.1)
            time.sleep(0.3)
            with open(pid_file) as f:
                game = int(f.read())
            self.assertTrue(self.alive(game))
            launcher.kill()                                # the launcher dies without a goodbye
            launcher.wait(10)
            t_end = time.monotonic() + 15
            while self.alive(game) and time.monotonic() < t_end:
                time.sleep(0.2)
            self.assertFalse(self.alive(game), "the capture game outlived its launcher")
        finally:
            if launcher.poll() is None:
                launcher.kill()
        # and the next start is not held up by what that run left in the work folder
        r = self.refresh()
        self.assertEqual(r["state"], "ok")


class FrameTest(unittest.TestCase):
    @staticmethod
    def frame(seed, flat=False):
        w, h = 160, 90
        px = bytearray()
        for y in range(h):
            for x in range(w):
                px += b"\x10\x10\x10" if flat else bytes(((x * 5 + seed) & 255, (y * 3) & 255, (x ^ y ^ seed) & 255))
        return w, h, bytes(px)

    def test_choice(self):
        a, b, c, d = (self.frame(s) for s in (1, 2, 3, 4))
        flat = self.frame(0, flat=True)
        port = lambda f: picfmt.portrait(*f)     # noqa: E731
        self.assertEqual(pp.choose_frame([a, b, c, d]), port(b))            # the second (2.5 s) is liked best
        self.assertEqual(pp.choose_frame([a, flat, c, d]), port(c))         # ... unless it shows nothing
        self.assertEqual(pp.choose_frame([a, None, None, d]), port(a))
        self.assertEqual(pp.choose_frame([None, None, None, d]), port(d))
        self.assertIsNone(pp.choose_frame([flat, flat, None, flat]))
        self.assertIsNone(pp.choose_frame([None] * 4))
        self.assertIsNone(pp.choose_frame([]))
        self.assertIsNone(pp.make_png([flat]))
        self.assertEqual(picfmt.decode(pp.make_png([a]))[:2], (picfmt.MAX_W, picfmt.MAX_H))


if __name__ == "__main__":
    unittest.main()
