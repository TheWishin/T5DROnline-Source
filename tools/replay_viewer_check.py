#!/usr/bin/env python3
"""Exercise replay viewer IPC using one local, isolated game process.

The caller MUST acquire a HEAVY slot before running this tool and release it
afterwards. This tool does not acquire a slot. It never connects to a lobby or
logs in. Supply --hdd0 as an existing PRIVATE COPY beneath --out; game assets
under --vfs are read, while saves, logs and temporary files stay under --out.

Example (paths abbreviated; prepare the private dev_hdd0 copy first):
  python tools/replay_viewer_check.py --exe build/game/t5dr.exe --vfs game/vfs \
    --hdd0 build/probe/dev_hdd0 --out build/probe --file sample.t5replay \
    --match 2 --scenario controls --build-id <recording-build-id>

Scenarios test pause, three single steps, backward/forward seek, and at least
60 simulated frames at each speed (0.25, 0.5, 1, 2, 4). These are FUNCTIONAL
checks, not performance measurements. The controls scenario then plays to the
end and requires an identical verdict. Take-control scenarios additionally run
60 frames with local P1/P2, return to recorded input and check permanent
unverified provenance before quitting. --timeout bounds the whole run;
--command-timeout bounds each individual wait. Result: result.json plus
commands.jsonl, statuses.jsonl, events.jsonl, game.log and verdict.json.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "launcher"))
import replay_library  # noqa: E402
import replays  # noqa: E402


class ProbeError(RuntimeError):
    pass


def config_hash(env):
    """Read only: detect an accidental change to the owner's real config."""
    folder = env.get("LOCALAPPDATA")
    if not folder:
        return None
    path = Path(folder) / "OpenRecomp" / "config.json"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def validate_status(data):
    if not isinstance(data, dict):
        raise ProbeError("status must be a JSON object")
    for key in ("frame", "start", "end"):
        if type(data.get(key)) is not int or not 0 <= data[key] <= 0xFFFFFFFF:
            raise ProbeError("invalid status field: " + key)
    if data["start"] > data["end"]:
        raise ProbeError("invalid status bounds")
    for key in ("paused", "verified", "seeking"):
        if type(data.get(key)) is not bool:
            raise ProbeError("invalid status field: " + key)
    if data.get("control") not in (0, 1, 2) or isinstance(data.get("control"), bool):
        raise ProbeError("invalid status control")
    speed = data.get("speed")
    if type(speed) not in (int, float) or not math.isfinite(speed) or speed not in (0.25, 0.5, 1, 2, 4):
        raise ProbeError("invalid status speed")
    provenance = data.get("unverified_from")
    if provenance is not None and (type(provenance) is not int or not 0 <= provenance <= 0xFFFFFFFF):
        raise ProbeError("invalid unverified provenance")
    return data


def seekable(status):
    """New runtimes report checkpoint readiness; older probes use round marks."""
    if "seekable" in status:
        return status["seekable"] is True and not status["seeking"]
    marks = status.get("rounds")
    return isinstance(marks, list) and bool(marks) and status["frame"] >= max(status["start"], marks[0]) and not status["seeking"]


def verify_verdict(verdict, scenario, provenance=None):
    if not isinstance(verdict, dict) or verdict.get("error"):
        raise ProbeError("missing or erroneous replay verdict")
    if scenario == "controls":
        if verdict.get("identical") is not True:
            raise ProbeError("controls changed playback: verdict is not identical")
        if verdict.get("unverified_from") is not None:
            raise ProbeError("controls unexpectedly tainted playback")
    elif (verdict.get("identical") is not False or verdict.get("verified") is not False
          or verdict.get("unverified_from") != provenance):
        raise ProbeError("take-control verdict lost its unverified provenance")


def game_env(args, inherited):
    out = args.out.resolve()
    hdd0 = args.hdd0.resolve()
    if not hdd0.is_dir() or not hdd0.is_relative_to(out):
        raise ProbeError("--hdd0 must be an existing private copy beneath --out")
    if hdd0 == (args.vfs.resolve() / "dev_hdd0").resolve():
        raise ProbeError("--hdd0 must not be the source VFS dev_hdd0")
    # Inherited automation, output paths, peers and controller files must not
    # escape isolation or alter the replay. Preserve ordinary system DLL paths.
    env = {k: v for k, v in inherited.items()
           if not k.upper().startswith(("T5_", "PS3_", "RSX_", "PAD_", "OPENRECOMP_"))}
    for key in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        path = out / "isolation" / key.lower()
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    (out / "savedata").mkdir(exist_ok=True)
    (out / "pad.txt").write_text("", encoding="ascii")
    env.update(replays.playback_env(str(args.file.resolve()), args.match, str(out / "verdict.json"), controls=False))
    env.update({
        "PS3_VFS_ROOT": args.vfs.resolve().as_posix(), "PS3_HDD0_ROOT": hdd0.as_posix(),
        "PS3_SAVEDATA_DIR": str(out / "savedata"), "PS3_AUDIO_MUTE": "1", "PS3_WINDOW_BACKGROUND": "1",
        "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PAD_NO_KEYBOARD": "1",
        "PS3_VM_WRITE_WATCH": "1",
        "PS3_PAD_FILE": str(out / "pad.txt"), "T5_NET_BIND": "127.0.0.1", "T5_NET_LOG": str(out / "frames.log"),
        "T5_REPLAY_COMMAND": str(out / "command.txt"), "T5_REPLAY_STATUS": str(out / "status.json"),
        "T5_REPLAY_CAPSULES": "1", "T5_REPLAY_EXIT": "0",
    })
    if args.build_id:
        env["T5_NET_BUILD"] = args.build_id
    return env


class Probe:
    def __init__(self, args, process, events, commands, statuses):
        self.args, self.process, self.events = args, process, events
        self.commands, self.statuses = commands, statuses
        self.command_path, self.status_path = args.out / "command.txt", args.out / "status.json"
        self.started = time.monotonic()
        self.deadline = self.started + args.timeout
        self.last = None
        self._last_stamp = None
        self.speed_checks = []

    def event(self, kind, **values):
        row = {"seconds": round(time.monotonic() - self.started, 3), "kind": kind, **values}
        self.events.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.events.flush()
        stream = self.commands if kind == "command" else self.statuses if kind == "status" else None
        if stream is not None:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()

    def status(self):
        try:
            stamp = self.status_path.stat().st_mtime_ns
            with self.status_path.open(encoding="utf-8") as f:
                raw = f.read(65537)
            if len(raw) > 65536:
                raise ProbeError("status exceeds 64 KiB")
            data = validate_status(json.loads(raw))
        except (FileNotFoundError, PermissionError, json.JSONDecodeError):
            return None
        self.last = data
        if stamp != self._last_stamp:
            self._last_stamp = stamp
            self.event("status", status=data)
        return data

    def wait(self, label, predicate, consumed=False):
        end = min(self.deadline, time.monotonic() + self.args.command_timeout)
        self.event("wait", label=label)
        while time.monotonic() < end:
            status = self.status()
            if status is not None:
                if status.get("error"):
                    raise ProbeError(label + ": " + str(status["error"]))
                if (not consumed or not self.command_path.exists()) and predicate(status):
                    self.event("check", label=label, status=status)
                    return status
            if self.process.poll() is not None:
                raise ProbeError(label + ": game exited early with code " + str(self.process.returncode))
            time.sleep(0.05)
        raise ProbeError(label + ": timeout; last status=" + json.dumps(self.last))

    def command(self, command, label, predicate):
        self.wait("command slot", lambda _s: True, consumed=True)
        self.event("command", command=command, label=label)
        replay_library.atomic_text(str(self.command_path), command + "\n")
        return self.wait(label, predicate, consumed=True)

    def pause(self, label="pause"):
        return self.command("pause", label, lambda s: s["paused"] and not s["seeking"])

    def seek(self, frame, label):
        return self.command("seek " + str(frame), label,
                            lambda s: s["paused"] and not s["seeking"] and s["frame"] == frame)

    def quit(self):
        self.wait("quit command slot", lambda _s: True, consumed=True)
        self.event("command", command="quit", label="clean quit")
        replay_library.atomic_text(str(self.command_path), "quit\n")
        end = min(self.deadline, time.monotonic() + self.args.command_timeout)
        while self.process.poll() is None and time.monotonic() < end:
            self.status()
            time.sleep(0.05)
        if self.process.poll() is None:
            raise ProbeError("clean quit timed out")
        if self.process.returncode != 0:
            raise ProbeError("game exit code " + str(self.process.returncode))
        self.event("check", label="clean quit", exit_code=0)


def exercise(probe, scenario):
    ready = probe.wait("checkpoint ready", seekable)
    anchor = ready["start"]
    probe.wait("120 frames after checkpoint start", lambda s: seekable(s) and s["frame"] >= anchor + 120)
    paused = probe.pause()
    for number in range(1, 4):
        target = paused["frame"] + 1
        paused = probe.command("step", "single step " + str(number),
                               lambda s, target=target: s["paused"] and not s["seeking"] and s["frame"] == target)
    backward = paused["frame"] - 60
    if backward < paused["start"]:
        raise ProbeError("fixture lacks 60 frames before paused position")
    paused = probe.seek(backward, "seek backward exactly 60 frames")
    forward = paused["frame"] + 90
    if forward > paused["end"]:
        raise ProbeError("fixture lacks 90 frames for forward seek")
    paused = probe.seek(forward, "seek forward exactly 90 frames")
    for speed in (0.25, 0.5, 1, 2, 4):
        if paused["frame"] + 60 > paused["end"]:
            raise ProbeError("fixture ended before all speed checks")
        paused = probe.command("speed " + str(speed), "set speed " + str(speed),
                               lambda s, speed=speed: s["paused"] and s["speed"] == speed)
        start = paused["frame"]
        probe.command("resume", "resume speed " + str(speed), lambda s: not s["paused"])
        advanced = probe.wait("60 frames at speed " + str(speed),
                              lambda s, start=start, speed=speed: s["frame"] >= start + 60 and s["speed"] == speed)
        paused = probe.pause("pause after speed " + str(speed))
        probe.speed_checks.append({"speed": speed, "from": start, "to": advanced["frame"], "functional_only": True})
    provenance = None
    if scenario == "controls":
        probe.command("speed 4", "finish playback at 4x", lambda s: s["paused"] and s["speed"] == 4)
        probe.command("resume", "resume to recorded end", lambda s: not s["paused"])
        probe.wait("recorded end parked", lambda s: s["paused"] and s["frame"] >= s["end"] and not s["seeking"])
    else:
        side = 1 if scenario == "take-p1" else 2
        provenance = paused["frame"]
        if provenance + 60 > paused["end"]:
            raise ProbeError("fixture lacks 60 frames after taking control")
        probe.command("control " + str(side), "take local P" + str(side),
                      lambda s: s["control"] == side and not s["verified"] and s.get("unverified_from") == provenance)
        probe.command("resume", "resume with local input", lambda s: not s["paused"])
        probe.wait("60 local-input frames", lambda s: s["frame"] >= provenance + 60 and s["control"] == side and not s["verified"])
        probe.pause("pause local-input branch")
        probe.command("control 0", "recorded input remains unverified",
                      lambda s: s["control"] == 0 and not s["verified"] and s.get("unverified_from") == provenance)
    probe.quit()
    return provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key in ("exe", "vfs", "hdd0", "out", "file"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--match", type=int, required=True, help="one-based completed match")
    parser.add_argument("--scenario", choices=("controls", "take-p1", "take-p2"), required=True)
    parser.add_argument("--build-id", default="", help="same build ID used to record start capsules")
    parser.add_argument("--timeout", type=float, default=900, help="whole-run timeout in seconds")
    parser.add_argument("--command-timeout", type=float, default=120, help="maximum seconds for each wait")
    args = parser.parse_args(argv)
    if args.match < 1 or not math.isfinite(args.timeout) or args.timeout <= 0 or not math.isfinite(args.command_timeout) or args.command_timeout <= 0:
        parser.error("--match and both timeouts must be positive")
    args.out = args.out.resolve()
    inherited = dict(os.environ)
    before = config_hash(inherited)
    process = None
    result = {"scenario": args.scenario, "match": args.match, "ok": False, "functional_only": True}
    fresh_output = True
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        for filename in ("result.json", "events.jsonl", "commands.jsonl", "statuses.jsonl", "game.log", "verdict.json", "command.txt", "status.json"):
            if (args.out / filename).exists():
                fresh_output = False
                raise ProbeError("use a fresh --out directory; output already exists: " + filename)
        header = replays.read_header(str(args.file))
        matches = header["matches"]
        if args.match > len(matches) or not matches[args.match - 1].get("complete"):
            raise ProbeError("--match must name a completed recorded match")
        elf = args.vfs.resolve() / "PS3_GAME" / "USRDIR" / "EBOOT.elf"
        if not args.exe.is_file() or not elf.is_file():
            raise ProbeError("game executable or VFS EBOOT.elf is missing")
        env = game_env(args, inherited)
        with (args.out / "events.jsonl").open("w", encoding="utf-8") as events, \
                (args.out / "commands.jsonl").open("w", encoding="utf-8") as commands, \
                (args.out / "statuses.jsonl").open("w", encoding="utf-8") as statuses, \
                (args.out / "game.log").open("w", encoding="utf-8") as log:
            flags = 0x00004000 if os.name == "nt" else 0
            process = subprocess.Popen([str(args.exe.resolve()), str(elf)], cwd=args.out, env=env,
                                       stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            probe = Probe(args, process, events, commands, statuses)
            probe.event("start", pid=process.pid, scenario=args.scenario, functional_only=True)
            try:
                provenance = exercise(probe, args.scenario)
                verdict = replays.read_result(str(args.out / "verdict.json"))
                result.update(verdict=verdict, unverified_from=provenance, speed_checks=probe.speed_checks)
                verify_verdict(verdict, args.scenario, provenance)
                result["ok"] = True
            except Exception as error:
                result["error"] = str(error)
                probe.event("failure", error=str(error), last_status=probe.last)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                    result["forced_termination"] = True
                result.update(exit_code=process.returncode, seconds=round(time.monotonic() - probe.started, 3), last_status=probe.last)
    except (OSError, ValueError, replays.ReplayError, ProbeError) as error:
        result["error"] = str(error)
    finally:
        result["owner_config_unchanged"] = before == config_hash(inherited)
        if not result["owner_config_unchanged"]:
            result.update(ok=False, error="owner OpenRecomp configuration changed")
        if fresh_output:
            replay_library.atomic_text(str(args.out / "result.json"), json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": result["ok"], "scenario": args.scenario, "result": str(args.out / "result.json") if fresh_output else None,
                      "error": result.get("error")}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
