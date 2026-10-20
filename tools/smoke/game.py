"""Drive one t5dr.exe for a smoke test: start it, script both pads, tail the
log, sample memory, collect frames, stop it. Grown out of the QA agent's
build/qa/drive.py; this copy lives in the repo and is what tools/smoke/run.py
uses.

    g = Game(test_dir, exe=..., root=...)
    g.start()
    g.wait_title()              # boot, skip the intro movie, wait for the title menu
    g.phase("vs-select", "menu")
    g.press("DOWN"); g.press("CROSS")
    g.shot("charsel", expect="content")
    g.stop()                    # -> result dict for checks.evaluate()

Screenshots come from the runtime's own frame dump (LD_FRAME_DUMP): it reads
back the presented surface every N flips, so nothing on the desktop changes --
the window stays minimized (PS3_WINDOW_BACKGROUND=1) and focus is never taken.
Every dumped frame is reduced to a small JPEG plus statistics (frames.py); a
shot() saves the next frame that shows what it expects (content, the fight
HUD) at full size under its name, skipping fades for a few seconds.

Waits raise Abort when the game exits or stops presenting for `abort_hang`
seconds, so a broken build fails a test in seconds instead of minutes.
"""
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(ROOT, "tools"))

import frames as framelib  # noqa: E402
import logscan  # noqa: E402
import procs  # noqa: E402
from run_game import game_command  # noqa: E402  (the one place that knows how the game starts)

BUTTONS = {"UP", "DOWN", "LEFT", "RIGHT", "CROSS", "CIRCLE", "SQUARE", "TRIANGLE",
           "L1", "R1", "L2", "R2", "L3", "R3", "START", "SELECT"}


def find_game_root(start=ROOT):
    """The tree that holds game/vfs: this checkout, or -- for a git worktree
    under build/ -- the first parent that has one."""
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, "game", "vfs")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return os.path.abspath(start)
        d = up


class Abort(Exception):
    """The game died or hung; the scenario cannot go on."""


def _sleep(s):
    end = time.perf_counter() + s
    while True:
        r = end - time.perf_counter()
        if r <= 0:
            return
        time.sleep(min(r, 0.01) if r < 0.03 else r - 0.02)


class Game:
    def __init__(self, test_dir, exe=None, root=None, env=None, dump_every=30,
                 abort_hang=20.0, boot_timeout=60.0, cwd=None, seed_gamedata=None, keep_gamedata=False, verbose=True):
        self.dir = os.path.abspath(test_dir)
        self.cwd = os.path.abspath(cwd) if cwd else os.path.join(self.dir, "cwd")
        self.frames_dir = os.path.join(self.dir, "frames")
        self.dump_dir = os.path.join(self.dir, "dump")
        self.log_path = os.path.join(self.dir, "game.log")
        self.pad_path = os.path.join(self.dir, "pad1.txt")
        self.pad2_path = os.path.join(self.dir, "pad2.txt")
        self.root = root or find_game_root()
        self.exe = exe
        self.extra_env = dict(env or {})
        self.dump_every = dump_every
        self.abort_hang = abort_hang
        self.boot_timeout = boot_timeout
        self.seed_gamedata = seed_gamedata
        self.keep_gamedata = keep_gamedata
        self.verbose = verbose
        self.name = os.path.basename(self.dir)

        self.proc = None
        self.t0 = None
        self.phase_name = "start"
        self.phases = []                # [name, kind, t_start, t_end]
        self.events = []                # (t, phase, kind, detail)
        self.scan = logscan.LogScanner()
        self.mem = []                   # (t, phase, ws_mb, private_mb)
        self.frames = []                # frame records (dicts), in dump order
        self.shots = {}                 # name -> {"file", "frame", "expect", "phase", "t"}
        self.contention = {"games": 0, "builds": 0, "names": []}
        self.hangs = []                 # [t_from, t_to or None, phase]
        self.expects = []               # scenario milestones (expect())
        self.last_fps_t = None
        self.exit_code = None
        self.aborted = None
        self.start_error = None
        self._stop = threading.Event()
        self._log_pos = 0
        self._lock = threading.Lock()
        self._fq = queue.Queue()
        self._shot_req = []             # pending shot() requests (dicts)
        self._threads = []
        self._prev_thumb = None

    # ------------------------------------------------------------ lifecycle
    def command(self):
        env = {
            "PS3_WINDOW_BACKGROUND": "1",
            "PS3_PAD_FILE": self.pad_path.replace("\\", "/"),
            "PS3_PAD_FILE2": self.pad2_path.replace("\\", "/"),
            "AUDIO_RATE": "1",
        }
        if self.dump_every:
            env["LD_FRAME_DUMP"] = self.dump_dir
            env["LD_FRAME_DUMP_EVERY"] = str(self.dump_every)
        env.update(self.extra_env)
        argv, full_env, _cwd = game_command(self.root, env)
        if self.exe:
            argv[0] = os.path.abspath(self.exe)
        return argv, full_env, self.cwd

    def prepare_dirs(self):
        os.makedirs(self.dir, exist_ok=True)
        for d in (self.frames_dir, self.dump_dir):
            os.makedirs(d, exist_ok=True)
        os.makedirs(self.cwd, exist_ok=True)
        gd = os.path.join(self.cwd, "gamedata")
        if not self.keep_gamedata and os.path.isdir(gd):
            shutil.rmtree(gd)
        if self.seed_gamedata and not os.path.isdir(gd):
            shutil.copytree(self.seed_gamedata, gd)
        for p in (self.pad_path, self.pad2_path):
            with open(p, "w"):
                pass

    def start(self):
        self.prepare_dirs()
        argv, env, cwd = self.command()
        self.argv = argv
        self.logf = open(self.log_path, "wb")
        self.t0 = time.perf_counter()
        self._log_pos = 0
        self._ev = open(os.path.join(self.dir, "events.tsv"), "w", buffering=1, encoding="utf-8")
        self.phases.append([self.phase_name, "boot", 0.0, None])
        try:
            if not os.path.isfile(argv[0]):
                raise OSError(f"no such file: {argv[0]}")
            self.proc = subprocess.Popen(argv, env=env, cwd=cwd, stdout=self.logf,
                                         stderr=subprocess.STDOUT)
            # If this Python dies without stop(), Windows kills the game with it.
            self._job = procs.kill_on_close_job(self.proc.pid)
        except OSError as e:
            self.start_error = f"could not start {argv[0]}: {e}"
            self.event("start-error", str(e))
            self.logf.close()
            self._ev.close()
            raise Abort(self.start_error)
        self.event("start", f"pid={self.proc.pid} exe={argv[0]}")
        for fn in (self._tail, self._sampler, self._framer):
            th = threading.Thread(target=fn, daemon=True)
            th.start()
            self._threads.append(th)
        return self

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def now(self):
        return time.perf_counter() - self.t0 if self.t0 else 0.0

    def stop(self):
        """Kill the game (and only what it spawned), finish frame processing."""
        if self.proc is None:
            return self.result()
        self.event("stop", f"alive={self.alive()}")
        self.end_phase()
        procs.kill_tree(self.proc)
        if getattr(self, "_job", None):
            self._job.close()
        self.exit_code = self.proc.returncode
        time.sleep(0.3)
        self._read_new()
        self._stop.set()
        for th in self._threads:
            th.join(15)
        self._drain_frames()
        self.logf.close()
        self._ev.close()
        try:
            shutil.rmtree(self.dump_dir)
        except OSError:
            pass
        return self.result()

    # ------------------------------------------------------------ timeline
    def event(self, kind, detail=""):
        t = self.now()
        with self._lock:
            self.events.append((round(t, 2), self.phase_name, kind, detail))
            try:
                self._ev.write(f"{t:.2f}\t{self.phase_name}\t{kind}\t{detail}\n")
            except (ValueError, AttributeError):
                pass
        if self.verbose and kind not in ("fps", "audio", "frame"):
            print(f"  [{self.name} {t:6.1f}s {self.phase_name}] {kind} {detail}"[:240], flush=True)

    def phase(self, name, kind):
        """Start a scenario phase. `kind` picks the thresholds (checks.KINDS):
        boot, title, menu, load, fight, attract, idle."""
        self.end_phase()
        self.phase_name = name
        self.phases.append([name, kind, self.now(), None])
        self.event("phase", f"{name} ({kind})")

    def end_phase(self):
        if self.phases and self.phases[-1][3] is None:
            self.phases[-1][3] = self.now()

    # ------------------------------------------------------------ log tail
    def _read_new(self):
        try:
            with open(self.log_path, "rb") as f:
                f.seek(self._log_pos)
                data = f.read()
        except OSError:
            return
        nl = data.rfind(b"\n")
        if nl < 0:
            return
        data = data[:nl + 1]
        self._log_pos += len(data)
        t = self.now()
        for raw in data.splitlines():
            line = raw.decode("utf-8", "replace")
            kind = self.scan.feed(line, t, self.phase_name)
            if kind == "fps":
                if self.hangs and self.hangs[-1][1] is None:
                    self.hangs[-1][1] = t
                    self.event("hang-end", f"frames resumed after {t - self.hangs[-1][0]:.1f}s")
                self.last_fps_t = t
                self.event("fps", line.strip())
            elif kind == "audio":
                self.event("audio", f"silent {self.scan.audio[-1].silent}%")
            elif kind == "frame":
                self._fq.put(self.scan.frames[-1])
            elif kind == "crash":
                self.event("CRASH", line.strip()[:300])
            elif kind == "nid-new":
                self.event("nid", line.strip()[:200])
            elif kind == "notable-new":
                self.event("notable", line.strip()[:300])

    def _tail(self):
        hang_gap = 12.0
        while not self._stop.is_set():
            self._read_new()
            t = self.now()
            if self.last_fps_t is not None and t - self.last_fps_t > hang_gap and \
                    (not self.hangs or self.hangs[-1][1] is not None):
                self.hangs.append([self.last_fps_t, None, self.phase_name])
                self.event("HANG", f"no [fps] line since {self.last_fps_t:.1f}s")
            if self.proc.poll() is not None:
                self._read_new()
                self.exit_code = self.proc.returncode
                self.event("EXIT", f"code={self.proc.returncode}")
                return
            time.sleep(0.2)

    def _sampler(self):
        n = 0
        ours = {self.proc.pid}
        while not self._stop.is_set() and self.alive():
            m = procs.memory(self.proc.pid)
            if m:
                self.mem.append((round(self.now(), 1), self.phase_name, round(m[0], 1), round(m[1], 1)))
            if n % 8 == 0:
                c = procs.contention(procs.list_processes(), ours)
                for k in ("games", "builds"):
                    self.contention[k] = max(self.contention[k], c[k])
                self.contention["names"] = sorted(set(self.contention["names"]) | set(c["names"]))
            n += 1
            self._stop.wait(2.0)

    # ------------------------------------------------------------ frames
    def _framer(self):
        while not (self._stop.is_set() and self._fq.empty()):
            try:
                fd = self._fq.get(timeout=0.3)
            except queue.Empty:
                continue
            self._process_frame(fd)

    def _drain_frames(self):
        while True:
            try:
                fd = self._fq.get_nowait()
            except queue.Empty:
                break
            self._process_frame(fd)

    def _process_frame(self, fd):
        path = fd.path
        if not os.path.isabs(path):
            path = os.path.join(self.cwd, path)
        im = None
        for _ in range(20):
            try:
                im = framelib.load(path)
                break
            except Exception:
                time.sleep(0.05)
        if im is None:
            return
        base = os.path.splitext(os.path.basename(path))[0]
        rec, self._prev_thumb = framelib.stats(im, self._prev_thumb)
        rec.update(t=round(fd.t, 2), phase=fd.phase, nonblack=fd.nonblack,
                   file=os.path.join("frames", base + ".jpg"))
        try:
            rec["fight"] = framelib.fight_check(im)
        except Exception as e:                       # analysis must never stop a run
            rec["fight"] = {"error": str(e)}
        framelib.save_thumb(im, os.path.join(self.dir, rec["file"]))
        with self._lock:
            self.frames.append(rec)
            for req in self._shot_req:
                if req["done"] or fd.t < req["t"]:
                    continue
                # Wait out fades: a 'content' shot takes the first frame with
                # content, a 'fight' shot the first with the HUD -- until the
                # deadline, then whatever came last.
                want = req["expect"]
                good = (want == "any" or
                        (want == "content" and framelib.classify(rec) == "content") or
                        (want == "fight" and rec["fight"].get("is_fight")))
                if good or time.perf_counter() >= req["deadline"]:
                    im.save(os.path.join(self.dir, req["name"] + ".png"))
                    req["result"] = {"file": req["name"] + ".png", "frame": rec, "expect": want,
                                     "phase": req["phase"], "t": rec["t"], "fight": rec["fight"]}
                    req["done"] = True
                    req["event"].set()
                else:
                    req["last"] = rec
        try:
            os.remove(path)
        except OSError:
            pass

    def shot(self, name, expect="content", settle=6.0, timeout=10.0):
        """Save a presented frame as <name>.png and record what it should
        show: 'content' (not black/white/flat), 'fight' (the fight HUD), 'any'
        (evidence only). Frames that do not show it yet (a fade) are skipped
        for up to `settle` seconds."""
        req = {"name": name, "t": self.now(), "expect": expect, "phase": self.phase_name,
               "deadline": time.perf_counter() + settle, "event": threading.Event(),
               "done": False, "result": None, "last": None}
        with self._lock:
            self._shot_req.append(req)
        end = time.perf_counter() + max(timeout, settle + 4.0)
        while not req["event"].is_set() and time.perf_counter() < end:
            if not self.alive():
                break
            req["event"].wait(0.1)
        with self._lock:
            self._shot_req.remove(req)
            res = req["result"]
        if res is None:
            res = {"file": None, "frame": req["last"], "expect": expect, "phase": self.phase_name,
                   "t": round(self.now(), 2)}
        self.shots[name] = res
        self.event("shot", f"{name}: " + (framelib.describe(res["frame"]) if res["frame"] else "no frame"))
        return res

    # ------------------------------------------------------------ waiting
    def check(self):
        """Raise Abort if the game is gone or has stopped presenting."""
        if not self.alive():
            self._read_new()
            if self.aborted is None:
                self.aborted = f"game exited (code {self.proc.returncode}) in phase {self.phase_name}"
                self.event("abort", self.aborted)
            raise Abort(self.aborted)
        if self.abort_hang and self.last_fps_t is not None and self.now() - self.last_fps_t > self.abort_hang:
            if self.aborted is None:
                self.aborted = f"no frames for {self.now() - self.last_fps_t:.0f}s in phase {self.phase_name}"
                self.event("abort", self.aborted)
            raise Abort(self.aborted)
        if self.last_fps_t is None and self.now() > self.boot_timeout:
            if self.aborted is None:
                self.aborted = f"no frame presented within {self.boot_timeout:.0f}s of start"
                self.event("abort", self.aborted)
            raise Abort(self.aborted)

    def expect(self, name, ok, detail="", evidence=None):
        """Record a scenario milestone ("reached the title", "fight started");
        it becomes the check reach.<name>."""
        self.expects.append({"name": name, "ok": bool(ok), "detail": detail, "evidence": evidence,
                             "t": round(self.now(), 1), "phase": self.phase_name})
        self.event("expect", f"{name}: {'ok' if ok else 'FAILED'} {detail}")
        return ok

    def latest_frame(self):
        with self._lock:
            return self.frames[-1] if self.frames else None

    def frames_since(self, t):
        with self._lock:
            return [f for f in self.frames if f["t"] >= t]

    def wait_frame(self, pred, timeout=30.0, need=1):
        """Wait for `need` consecutive dumped frames (presented after this
        call) for which pred(record) is true. Returns the last or None."""
        t0 = self.now()
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            run = 0
            for f in self.frames_since(t0):
                run = run + 1 if pred(f) else 0
                if run >= need:
                    return f
            self.wait(0.2)
        return None

    def until_fight(self, timeout=60.0, taps=(("CROSS", 1),), every=1.0, need=2):
        """Tap `taps` ((button, pad) pairs) every `every` seconds until `need`
        dumped frames in a row show the fight HUD. Gets through character
        select confirmations, stage select, VS splash and intros. Returns the
        time the fight started, or None."""
        t_start = self.now()
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            fr = self.frames_since(t_start)
            run = 0
            for f in fr:
                run = run + 1 if f.get("fight", {}).get("is_fight") else 0
                if run >= need:
                    return f["t"]
            for btn, pad in taps:
                self.press(btn, pad=pad, gap=60)
            self.wait(max(0.0, every - 0.16 * len(taps)))
        return None

    def wait(self, s):
        end = time.perf_counter() + s
        while True:
            self.check()
            r = end - time.perf_counter()
            if r <= 0:
                return
            _sleep(min(r, 0.1))

    def log_bytes(self):
        with open(self.log_path, "rb") as f:
            return f.read()

    def wait_log(self, pattern, timeout=30.0, count=1):
        """Wait until regex `pattern` matched `count` times in this run's log."""
        rx = re.compile(pattern.encode() if isinstance(pattern, str) else pattern)
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            if len(rx.findall(self.log_bytes())) >= count:
                return True
            self.wait(0.25)
        return False

    # The intro movie, as the log shows it: the decoder opens, gives its first
    # picture (or patch 0053 says it gave none and the movie goes on black),
    # START skips it (the decoder closes), the title background movie opens a
    # second decoder.
    MOVIE_OPEN = b"[cellVdec] Open("
    MOVIE_PICTURE = re.compile(rb"\[cellVdec\] handle \d+: picture #1 |no picture from the H\.264 decoder|"
                               rb"the H\.264 decoder has not answered")
    MOVIE_CLOSE = b"[cellVdec] Close("

    def wait_title(self, timeout=90.0, picture_timeout=12.0, skip_timeout=30.0):
        """Boot -> title menu. With movie support (patch 0006) the intro
        movie opens cellVdec; START skips it and the title background movie
        opens a second decoder. Builds without movies skip them: the PAMF
        reader opens and closes twice right before the title fades in.

        START is pressed only once the movie shows (its first picture, or
        patch 0053's word that it plays without pictures) -- the game ignores
        it before -- and then until the movie has closed, for up to
        skip_timeout s. The 'title' event says what happened, so a failure
        tells a decoder that gave no picture (the old 1.1.x hang, fixed by
        0053) from presses that did not skip."""
        end = time.perf_counter() + timeout
        ok = False
        detail = "timeout before the intro movie"
        while time.perf_counter() < end:
            self.check()
            txt = self.log_bytes()
            if txt.count(self.MOVIE_OPEN) >= 1:
                ok, detail = self._skip_intro(txt.find(self.MOVIE_OPEN), picture_timeout, skip_timeout)
                break
            if txt.count(b"[cellDmux] Close") >= 2 and self.MOVIE_OPEN not in txt:
                ok, detail = True, "no movies in this build"
                break
            _sleep(0.25)
        self.wait(3.0)
        self.title_detail = detail
        self.event("title", ("reached: " if ok else "NOT reached: ") + detail)
        return ok

    def _skip_intro(self, open_at, picture_timeout, skip_timeout):
        t_open = self.now()
        t_pic = None
        while self.now() - t_open < picture_timeout:
            if self.MOVIE_PICTURE.search(self.log_bytes(), open_at):
                t_pic = self.now()
                break
            self.wait(0.2)
        if t_pic is None:
            self.event("movie", f"intro movie: no picture {picture_timeout:.0f}s after the decoder opened "
                                "(decoder stalled) -- pressing START anyway")
        presses = 0
        t_first = self.now()
        while self.now() - t_first < skip_timeout:
            txt = self.log_bytes()
            closed = txt.find(self.MOVIE_CLOSE, open_at) >= 0
            if txt.count(self.MOVIE_OPEN) >= 2:
                how = f"{presses} START press(es)" if presses else "the movie ended"
                pic = f"first picture {t_pic - t_open:.1f}s after open" if t_pic is not None else "no picture"
                return True, f"intro skipped ({pic}, {how}, title movie {self.now() - t_open:.1f}s after open)"
            if not closed:
                self.press("START", gap=900)
                presses += 1
            else:
                self.wait(0.3)          # closed: the title movie opens next
        closed = self.log_bytes().find(self.MOVIE_CLOSE, open_at) >= 0
        return False, (f"intro movie {'closed but no title movie' if closed else 'not skipped'} after "
                       f"{presses} START press(es) in {skip_timeout:.0f}s; "
                       + ("first picture %.1fs after open" % (t_pic - t_open) if t_pic is not None
                          else "the decoder gave no picture"))

    # ------------------------------------------------------------ input
    def _write_pad(self, text, path):
        tmp = path + ".tmp"
        for _ in range(100):
            try:
                with open(tmp, "w") as f:
                    f.write(text)
                os.replace(tmp, path)
                return
            except PermissionError:
                time.sleep(0.002)
        raise RuntimeError("could not write pad file " + path)

    def hold(self, *btns, pad=1, **axes):
        for b in btns:
            if b not in BUTTONS:
                raise ValueError(f"unknown button {b}")
        parts = list(btns) + [f"{k.upper()}={v}" for k, v in axes.items()]
        self._write_pad(" ".join(parts), self.pad_path if pad == 1 else self.pad2_path)

    def release(self, pad=1):
        self._write_pad("", self.pad_path if pad == 1 else self.pad2_path)

    def press(self, *btns, ms=100, gap=250, pad=1, **axes):
        """Tap: hold `btns` for `ms`, release, wait `gap` ms."""
        self.hold(*btns, pad=pad, **axes)
        _sleep(ms / 1000)
        self.release(pad=pad)
        self.wait(gap / 1000)

    def press2(self, *btns, ms=100, gap=250):
        self.press(*btns, ms=ms, gap=gap, pad=2)

    def seq(self, *steps, ms=100, gap=300, pad=1):
        """seq("DOWN", "DOWN", 1.0, "CROSS"): taps in order; a number waits."""
        for s in steps:
            if isinstance(s, (int, float)):
                self.wait(s)
                continue
            if isinstance(s, str):
                s = (s,)
            self.press(*s, ms=ms, gap=gap, pad=pad)

    # ------------------------------------------------------------ result
    def result(self):
        s = self.scan
        return {
            "name": self.name,
            "dir": self.dir,
            "argv": getattr(self, "argv", None),
            "duration": round(self.now(), 1),
            "exit_code": self.exit_code,
            "start_error": self.start_error,
            "aborted": self.aborted,
            "phases": [list(p) for p in self.phases],
            "fps": [list(f) for f in s.fps],
            "audio": [list(a) for a in s.audio],
            "crashes": [list(c) for c in s.crashes],
            "nids": {k: {"first_t": v.first_t, "first_phase": v.first_phase, "count": v.count,
                         "phases": v.phases} for k, v in s.nids.items()},
            "notable": [{"kind": k.split(":", 1)[0], "count": v[0], "t": v[1], "phase": v[2], "line": v[3]}
                        for k, v in s.notable.items()],
            "hangs": [list(h) for h in self.hangs],
            "mem": [list(m) for m in self.mem],
            "frames": list(self.frames),
            "shots": dict(self.shots),
            "contention": dict(self.contention),
            "events": [list(e) for e in self.events if e[2] not in ("fps", "audio")],
            "expects": list(self.expects),
        }
