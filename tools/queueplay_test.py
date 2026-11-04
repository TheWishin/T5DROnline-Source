#!/usr/bin/env python3
"""Local proof: a game after minutes of Practice meets a freshly booted game.

Run once with --mode rollback, once with --mode lockstep. Acquire a coordination
heavy slot before invoking this tool; it runs one pair, then each replay in turn.
Requires a newly built queueplay runtime, and the owner's local --vfs. Never uses
a lobby or an account. Outputs report.json, game logs, results and replay verdicts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fight_flow_test import Game, read_json, session_env, write_atomic  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SYNC = re.compile(r"sync check through frame (\d+): (\d+) mismatching")
BAD = re.compile(r"\[CRASH\]|\[null-(?:call|read|write)\]|guest_call: OPD .* not registered|"
                 r"fence queue overflow|abort\(\) is called|queued flip never reached by the FIFO walker|drain stalled")


def isolated_env(directory):
    return {name: str(Path(directory, name.lower()).resolve())
            for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA")}


def owner_config_hash():
    path = Path(os.environ.get("LOCALAPPDATA", ""), "OpenRecomp", "config.json")
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def assess_pair(results, logs, mode):
    """Fail closed on missing comparisons, unconfirmed results or mode fallback."""
    errors, checks = [], []
    for index, (result, log) in enumerate(zip(results, logs), 1):
        sync = [(int(frame), int(bad)) for frame, bad in SYNC.findall(log)]
        checks.append(sync)
        if not sync or any(bad for _, bad in sync):
            errors.append(f"game {index}: missing sync checks or mismatching frames")
        if not result or result.get("winner") not in (0, 1) or not result.get("hash") or result.get("desync"):
            errors.append(f"game {index}: missing/invalid result or desync")
        rollback = "rollback loop takes over" in log
        if rollback != (mode == "rollback"):
            errors.append(f"game {index}: requested {mode} loop was not used")
        if mode == "rollback" and not re.search(r"rollback \d+ -> \d+ done", log):
            errors.append(f"game {index}: no completed rollback was observed")
        if BAD.search(log):
            errors.append(f"game {index}: fatal runtime or FIFO error")
    if len(results) != 2 or len(logs) != 2:
        errors.append("two game results and logs are required")
    elif all(results) and (results[0].get("winner"), results[0].get("hash")) != (
            results[1].get("winner"), results[1].get("hash")):
        errors.append("different winners or final hashes")
    return errors, checks


class Player(Game):
    def base_env(self):
        env = super().base_env()
        # A developer shell must not silently add a peer, replay or boot mode.
        for key in list(env):
            if key.startswith(("T5_NET_", "T5_REPLAY_", "T5_FIGHT", "T5_CTL_")):
                del env[key]
        env.update(isolated_env(self.dir))
        env.update(PS3_AUDIO_MUTE="1", PS3_WINDOW_BACKGROUND="1", PAD_NO_HOST="1",
                   T5_CTL_DIR=self.ctl, T5_NET_BIND="127.0.0.1", T5_NET_LOCALPAD="1", T5_PRACTICE="1",
                   T5_PRACTICE_LOG=os.path.join(self.dir, "practice.log"),
                   PS3_SAVEDATA_DIR=os.path.join(self.dir, "savedata-online"),
                   PS3_PAD_FILE=os.path.join(self.dir, "pad.txt"), T5_ONLINE_FAST_BOOT="0",
                   T5_REPLAY_HASH_EVERY="1",
                   T5_RB_MODE="off" if self.a.mode == "lockstep" else "net")
        # Install this script only in the online session command below.
        # Offline Practice samples the changing physical-pad file instead.
        from fight_flow_test import mash_script
        self.online_script = mash_script(os.path.join(self.dir, "mash.txt"), 100 + self.idx, moves=True)
        if self.a.mode == "rollback":
            env["T5_RB_NET_FORCE"] = "120:4"
            env["T5_RB_NET_LOG"] = "1"
        if getattr(self, "ui_channel", None) is not None:
            env.update(self.ui_channel.environment())
        return env


def wait_for(games, predicate, timeout, description):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        if not all(game.running() for game in games):
            raise RuntimeError(f"game exited waiting for {description}")
        time.sleep(0.25)
    raise RuntimeError(f"timeout waiting for {description}")


def ui_events(channel):
    events = []
    while True:
        try:
            events.append(channel.events.get_nowait())
        except queue.Empty:
            return events


def challenger_probe(host, channel, evidence):
    """Real rendered local channel and pad input; no lobby or match authority."""
    evidence.update(ok=False, offers=[])
    pad = os.path.join(host.dir, "pad.txt")

    def settle(seconds):
        deadline = time.monotonic() + seconds
        wait_for([host], lambda: time.monotonic() >= deadline, seconds + 1, "UI probe delay")

    def no_events(description):
        events = ui_events(channel)
        if events:
            raise RuntimeError(f"{description}: unexpected UI events {events}")

    def offer(name):
        no_events("before new challenger")
        if not channel.offer(name, "challenger", ["accept", "decline"], 15,
                             {"title": "NEW CHALLENGER", "body": "Local queueplay proof",
                              "confirm": "Accept", "cancel": "Decline"}, countdown=15):
            raise RuntimeError("local challenger offer refused")
        row = {"case": name, "offered_revision": channel.revision,
               "countdown_ms": channel.snapshot()["countdown_ms"], "total_ms": channel.snapshot()["total_ms"]}
        evidence["offers"].append(row)
        wait_for([host], lambda: channel.shown, 5, "rendered challenger revision")
        row["rendered_revision"] = channel.ready_revision
        return row

    def take_action(expected, row):
        received = []

        def got_event():
            received.extend(ui_events(channel))
            return bool(received)

        wait_for([host], got_event, 5, f"pad {expected}")
        if len(received) != 1 or received[0][0] != "action":
            raise RuntimeError(f"expected one {expected} action; received {received}")
        value = received[0][1]
        if value.get("action") != expected or value.get("match") != row["case"]:
            raise RuntimeError(f"wrong challenger action: {value}")
        row["action"] = value
        channel.complete(value["seq"], True)
        ack_revision = channel.revision
        wait_for([host], lambda: channel.healthy and channel.ready_revision >= ack_revision,
                 5, "rendered action acknowledgment")
        row.update(ack_seq=channel.snapshot()["ack_seq"], ack_status=channel.snapshot()["ack_status"],
                   ack_rendered_revision=channel.ready_revision)
        settle(0.75)
        no_events("held button after acknowledgment must not repeat")
        channel.hide()
        hidden_revision = channel.revision
        write_atomic(pad, "")
        wait_for([host], lambda: channel.healthy and channel.ready_revision >= hidden_revision,
                 5, "hidden challenger revision")
        settle(0.5)
        no_events("after hidden challenger")

    # Cross is already held when the prompt arrives. It must remain unanswered
    # even after the initial input lock, until released and freshly pressed.
    write_atomic(pad, "CROSS")
    settle(0.5)
    row = offer("probe-held-accept")
    settle(1.0)
    no_events("Cross held before the challenger must not accept")
    row["held_cross_ignored"] = True
    write_atomic(pad, "")
    settle(0.75)
    write_atomic(pad, "CROSS")
    take_action("accept", row)

    row = offer("probe-decline")
    settle(0.75)
    write_atomic(pad, "CIRCLE")
    take_action("decline", row)

    started = time.monotonic()
    row = offer("probe-expire")
    expired = []

    def got_expiry():
        expired.extend(ui_events(channel))
        return bool(expired)

    wait_for([host], got_expiry, 18, "15 second challenger expiry")
    row["expiry_seconds"] = round(time.monotonic() - started, 3)
    row["events"] = expired
    if expired != [("expired", None)] or row["expiry_seconds"] < 14.5:
        raise RuntimeError(f"challenger did not expire once after 15 seconds: {row}")
    hidden_revision = channel.revision
    wait_for([host], lambda: channel.healthy and channel.ready_revision >= hidden_revision,
             5, "rendered expired challenger removal")
    settle(0.5)
    no_events("after challenger expiry")
    evidence["ok"] = True


def run(a):
    os.makedirs(a.out, exist_ok=False)  # stale results must never pass a new run
    before = owner_config_hash()
    report = {"mode": a.mode, "practice_seconds_requested": a.practice_seconds,
              "exe_sha256": hashlib.sha256(Path(a.exe).read_bytes()).hexdigest(), "ok": False}
    games = [Player(a, 1, "host"), Player(a, 2, "join")]
    channel = None
    try:
        host, fresh = games
        if a.challenger_probe:
            sys.path.insert(0, str(ROOT / "lobby"))
            from t5lobby.ingame_ui import IngameUI
            channel = IngameUI(os.path.join(host.dir, "ui"), "queueplay-proof-ui", worker=True)
            host.ui_channel = channel
        host.send("practice", env={"T5_FIGHT": a.practice_fight})
        host.start(host.base_env())
        wait_for([host], lambda: host.ctl_state().get("state") == "practice", a.boot_seconds, "loaded Practice")
        report["practice_state"] = host.ctl_state()
        if "type=10 phase=17" not in Path(host.log_path).read_text(encoding="utf-8", errors="replace"):
            raise RuntimeError("loaded native Practice evidence (type=10 phase=17) is missing")
        started = time.monotonic()
        print(f"Practice loaded; exercising it for {a.practice_seconds:g} s", flush=True)
        inputs = ("RIGHT", "RIGHT SQUARE", "TRIANGLE", "LEFT", "DOWN RIGHT TRIANGLE", "CROSS", "",
                  "SELECT CROSS", "")
        tick = 0
        while time.monotonic() - started < a.practice_seconds:
            if not host.running() or host.ctl_state().get("state") != "practice":
                raise RuntimeError("Practice ended during the soak")
            write_atomic(os.path.join(host.dir, "pad.txt"), inputs[tick % len(inputs)])
            tick += 1
            time.sleep(max(0, min(1.0, a.practice_seconds - (time.monotonic() - started))))
        write_atomic(os.path.join(host.dir, "pad.txt"), "")
        report["practice_seconds_actual"] = round(time.monotonic() - started, 3)
        report["practice_input_changes"] = tick
        practice_path = Path(host.dir, "practice.log")
        practice_log = practice_path.read_text(encoding="utf-8", errors="replace") if practice_path.exists() else ""
        report["practice_resets_observed"] = practice_log.count("reset round start:")
        if a.practice_seconds >= 10 and not report["practice_resets_observed"]:
            raise RuntimeError("no Practice reset observed: pad input did not reach the Practice tools")
        report["persistent_pid"] = host.proc.pid
        if channel is not None:
            challenger_probe(host, channel, report.setdefault("challenger_probe", {}))
        # Boot the new opponent only after the soak. It waits at neutral select;
        # neither game's peer timeout is running while this new process boots.
        fresh.start(fresh.base_env())
        wait_for(games, lambda: fresh.ctl_state().get("state") == "idle", a.boot_seconds, "fresh opponent")
        report["fresh_pid"] = fresh.proc.pid
        report["fresh_state"] = fresh.ctl_state()
        for game in games:
            env = session_env(a, 1, "queueplay-proof", game, a.port)
            env.update(T5_FIGHT=a.fight, T5_NET_BIND="127.0.0.1",
                       T5_NET_SCRIPT=game.online_script, T5_NET_LOCALPAD="0",
                       T5_REPLAY_DIR=os.path.join(game.dir, "replays"), T5_REPLAY_HASH_EVERY="1")
            game.send("fight", match="queueplay-proof", env=env)
        wait_for(games, lambda: all((read_json(g.result_path) or {}).get("match") == "queueplay-proof" for g in games),
                 a.match_seconds, "both match results")
        report["results"] = [read_json(g.result_path) for g in games]
        report["persistent_pid_unchanged"] = host.proc.pid == report["persistent_pid"]
        for game in games:
            game.send("idle")
        wait_for(games, lambda: all(g.ctl_state().get("state") == "idle" for g in games),
                 a.boot_seconds, "session teardown and replay flush")
        time.sleep(1)
        logs = [Path(g.log_path).read_text(encoding="utf-8", errors="replace") for g in games]
        errors, report["sync_checks"] = assess_pair(report["results"], logs, a.mode)
        report["errors"] = errors
        if errors:
            raise RuntimeError("; ".join(errors))
        for game in games:
            game.stop()
        if channel is not None:
            channel.close()
        replay_files = [str(p) for g in games for p in Path(g.dir, "replays").glob("*.t5replay")]
        if len(replay_files) != 2:
            raise RuntimeError(f"expected two recorded replays, found {len(replay_files)}")
        replay_out = os.path.join(a.out, "playback")
        command = [sys.executable, str(ROOT / "tools" / "replay_play.py"), "--exe", a.exe,
                   "--vfs", a.vfs, "--out", replay_out, "--parallel", "1", "--timeout", str(a.match_seconds)]
        for key, value in isolated_env(os.path.join(replay_out, "sandbox")).items():
            command += ["--env", f"{key}={value}"]
        command += ["--env", "T5_NET_BIND=127.0.0.1", "--env", "PS3_SAVEDATA_DIR=savedata-online"] + replay_files
        playback_env = {key: value for key, value in os.environ.items()
                        if not key.startswith(("T5_", "PS3_", "RSX_"))}
        playback_env.update(isolated_env(os.path.join(replay_out, "sandbox")))
        with open(os.path.join(a.out, "replay.log"), "w", encoding="utf-8") as log:
            replay = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False, env=playback_env)
        verdict_path = Path(replay_out, "verdicts.jsonl")
        verdicts = [json.loads(line) for line in verdict_path.read_text(encoding="utf-8").splitlines()] if verdict_path.exists() else []
        report["replay_verdicts"] = verdicts
        if replay.returncode or len(verdicts) != 2 or not all(v.get("identical") for v in verdicts):
            raise RuntimeError("both replays must play back identical; see replay.log")
        report["ok"] = True
    except (OSError, RuntimeError, ValueError) as error:
        report["error"] = str(error)
    finally:
        for game in games:
            game.stop()
        if channel is not None:
            channel.close()
        report["owner_config_unchanged"] = before == owner_config_hash()
        if not report["owner_config_unchanged"]:
            report["ok"] = False
            report["error"] = "owner OpenRecomp config hash changed"
        Path(a.out, "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{'PASS' if report['ok'] else 'FAIL'}: {Path(a.out, 'report.json')}", flush=True)
    return 0 if report["ok"] else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--vfs", required=True)
    ap.add_argument("--out", required=True, help="new run directory (must not already exist)")
    ap.add_argument("--mode", choices=("rollback", "lockstep"), required=True)
    ap.add_argument("--challenger-probe", action="store_true",
                    help="before the session, verify rendered local challenger pad accept/decline and 15s expiry")
    ap.add_argument("--practice-seconds", type=float, default=180)
    ap.add_argument("--practice-fight", default="9,33,20,3")
    ap.add_argument("--fight", default="15,14,27,1")
    ap.add_argument("--port", type=int, default=27400)
    ap.add_argument("--boot-seconds", type=float, default=90)
    ap.add_argument("--match-seconds", type=float, default=420)
    a = ap.parse_args()
    if a.practice_seconds <= 0:
        ap.error("--practice-seconds must be positive (use at least 180 for release proof)")
    a.out, a.exe, a.vfs = map(os.path.abspath, (a.out, a.exe, a.vfs))
    if not Path(a.exe).is_file() or not Path(a.vfs, "PS3_GAME", "USRDIR", "EBOOT.elf").is_file():
        ap.error("--exe and --vfs must name an existing new runtime and local game VFS")
    # Fields consumed by the shared pair harness.
    a.exe2, a.env, a.env1, a.env2 = None, [], [], []
    a.mash, a.below_normal, a.delay, a.rounds = False, True, 2, 1
    a.gamedata1 = a.gamedata2 = a.cpus1 = a.cpus2 = ""
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
