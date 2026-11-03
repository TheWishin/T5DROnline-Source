#!/usr/bin/env python3
"""Read-only rollback depth and corrected output report; never launches a game.

python tools/rollback_jitter_report.py RUN/host/lat.log --sound RUN/host/rb_sound.log

M/Q/P events are from PS3_LATENCY_LOG. Sound N lines come from T5_RB_SNDTRACE.
Output timestamps measure host submission, not photon or speaker latency.
"""
import argparse
import bisect
import collections
import json
import math
import re


def distribution(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "p50": None, "p95": None, "p99": None, "max": None}
    def rank(p):
        return values[max(0, math.ceil(p * len(values)) - 1)]
    return {"count": len(values), "p50": rank(.50), "p95": rank(.95),
            "p99": rank(.99), "max": values[-1]}


def analyze(latency_lines, sound_lines=()):
    frequency = 10_000_000
    events = []
    for line in latency_lines:
        if line.startswith("# qpc_frequency="):
            frequency = int(line.split("=", 1)[1])
            if frequency <= 0:
                raise ValueError("QPC frequency must be positive")
            continue
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("#"):
            continue
        try:
            events.append((int(parts[1]), parts[0], parts[2:]))
        except ValueError:
            continue
    events.sort(key=lambda event: event[0])
    presents = [t for t, kind, _ in events if kind == "P"]
    pending = {}
    depths, wall_ms, output_ms = [], [], []
    incomplete = malformed = 0
    for tick, kind, args in events:
        if kind not in ("M", "Q"):
            continue
        try:
            frame, first = int(args[0]), int(args[1])
            if first < 0 or frame <= first:
                raise ValueError("invalid rollback interval")
            key = (frame, first)
            if kind == "M":
                if key in pending:
                    incomplete += 1
                pending[key] = tick
            elif key in pending:
                # M is emitted AFTER restore; Q carries the full duration from
                # before restore. Q-M would undercount the expensive copy.
                duration = float(args[2])
                if not math.isfinite(duration) or duration < 0:
                    raise ValueError("invalid rollback duration")
                pending.pop(key)
                depths.append(frame - first)
                wall_ms.append(duration)
                index = bisect.bisect_left(presents, tick)
                if index < len(presents):
                    output_ms.append((presents[index] - tick) * 1000.0 / frequency)
        except (ValueError, IndexError):
            malformed += 1
    late = []
    sound_counts = collections.Counter()
    for line in sound_lines:
        match = re.match(r"^([GNDO]) (\d+) grp=", line)
        if not match:
            continue
        sound_counts[match[1]] += 1
        if match[1] == "N":
            lateness = re.search(r"\blate=(\d+)\b", line)
            if lateness:
                late.append(int(lateness[1]))
    return {
        "rollback_depth_frames": distribution(depths),
        "restore_and_resim_ms": distribution(wall_ms),
        "correction_done_to_next_present_ms": distribution(output_ms),
        "corrected_sound_late_frames": distribution(late),
        "sound_calls": dict(sound_counts),
        "incomplete_rollbacks": incomplete + len(pending),
        "malformed_rollback_events": malformed,
        "scope": "host output submission; no measured audio/video hardware latency",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("latency_log")
    parser.add_argument("--sound", help="rb_sound.log from the same process and run")
    args = parser.parse_args()
    with open(args.latency_log, encoding="utf-8", errors="replace") as source:
        latency = source.readlines()
    sound = []
    if args.sound:
        with open(args.sound, encoding="utf-8", errors="replace") as source:
            sound = source.readlines()
    print(json.dumps(analyze(latency, sound), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
