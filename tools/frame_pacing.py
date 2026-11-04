#!/usr/bin/env python3
"""Analyze host submission and observed DXGI display pacing separately.

    python tools/frame_pacing.py frames.csv --window-json result.json --json pacing.json
    python tools/frame_pacing.py frames.csv --latency latency.log --display-hz 59.94

FRAMELOG dt_us is a host timestamp interval, not display time. Display metrics
use successful DXGI frame-statistics observations only. SyncQPCTime anchors
SyncRefreshCount, so the displayed timestamp is SyncQPCTime plus
(PresentRefreshCount - SyncRefreshCount) * display period. --display-hz must
describe the physical display, not RSX_TEST_DISPLAY_HZ (which simulates waits).
Without it a stable period is inferred from independent DXGI sync anchors.

Repeated observations are deduplicated. If PresentCount jumps, the intervening
frames might have been dropped OR merely not observed; neither their frame times
nor a dropped-frame count can be recovered. Such gaps invalidate a complete-run
display claim. A minimized/occluded window normally has no display evidence.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics


def percentile(values, percent):
    """Linear interpolation between adjacent order statistics (NumPy default)."""
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def summary(intervals_ms):
    """Rates use only the actually observed intervals, never the requested span."""
    duration = sum(intervals_ms) / 1000
    return {
        "intervals": len(intervals_ms), "observed_seconds": duration,
        "fps": len(intervals_ms) / duration if duration else None,
        "p50_ms": percentile(intervals_ms, 50),
        "p95_ms": percentile(intervals_ms, 95),
        "p99_ms": percentile(intervals_ms, 99),
        "p99_9_ms": percentile(intervals_ms, 99.9),
        "max_ms": max(intervals_ms) if intervals_ms else None,
        "inside_15_7_17_7_percent": (100 * sum(15.7 <= x <= 17.7 for x in intervals_ms)
                                     / len(intervals_ms) if intervals_ms else None),
        "over_ms": {str(limit): {
            "count": sum(x > limit for x in intervals_ms),
            "per_minute": (60 * sum(x > limit for x in intervals_ms) / duration
                           if duration else None)} for limit in (20, 25, 33)},
    }


def _complete_lines(path):
    data = Path(path).read_bytes()
    end = data.rfind(b"\n") + 1
    return data[:end].decode("utf-8", errors="replace").splitlines(), len(data) - end


def read_frames(path):
    lines, partial_bytes = _complete_lines(path)
    if not lines or not lines[0].startswith("# qpc_frequency="):
        raise ValueError("frame log lacks qpc_frequency header")
    frequency = int(lines[0].split("=", 1)[1])
    rows, malformed = [], 0
    for row in csv.DictReader(lines[1:]):
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("incomplete CSV row")
            if not math.isfinite(float(row["qpc"])):
                raise ValueError("non-finite QPC")
            rows.append(row)
        except (TypeError, KeyError, ValueError):
            malformed += 1
    return frequency, rows, {"partial_tail_bytes": partial_bytes, "malformed_rows": malformed}


def _number(row, key, default=0):
    try:
        value = float(row.get(key, default))
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def frame_statistics(rows):
    has_status = bool(rows and "present_status" in rows[0])
    has_issued_count = bool(rows and "last_present_count" in rows[0])
    successful_counts = {int(_number(r, "last_present_count")) for r in rows
                         if r.get("present_status") == "ok"}
    return [{"observed_qpc": int(r["qpc"]),
             "pc": int(_number(r, "dxgi_present_count")),
             "present_refresh": int(_number(r, "dxgi_present_refresh")),
             "sync_refresh": int(_number(r, "dxgi_sync_refresh")),
             "sync_qpc": int(_number(r, "dxgi_sync_qpc"))} for r in rows
            if r.get("present_status", "ok") == "ok"
            and (not (has_status and has_issued_count)
                 or int(_number(r, "dxgi_present_count")) in successful_counts)]


def read_latency(path):
    """D qpc pc present_refresh sync_refresh sync_qpc (not legacy four-field D)."""
    lines, partial_bytes = _complete_lines(path)
    frequency, samples, malformed, dropped, visibility_verified = None, [], 0, 0, False
    successful_presents = {}
    for line in lines:
        if line.startswith("# qpc_frequency="):
            frequency = int(line.split("=", 1)[1].split()[0])
        if line.startswith("# trace_dropped="):
            dropped = max(dropped, int(line.split("=", 1)[1].split()[0]))
        if line.startswith("#") and "display_statistics=successful_nonoccluded_present_only" in line.split():
            visibility_verified = True
        fields = line.split()
        if len(fields) >= 6 and fields[0] == "P":
            try:
                if int(fields[5], 0) == 0:
                    pc, stamp = int(fields[4]), int(fields[1])
                    successful_presents[pc] = min(stamp, successful_presents.get(pc, stamp))
            except ValueError:
                pass
        if not fields or fields[0] != "D":
            continue
        try:
            if len(fields) != 6:
                raise ValueError("unsupported D event layout")
            values = list(map(int, fields[1:]))
            samples.append(dict(zip(("observed_qpc", "pc", "present_refresh",
                                     "sync_refresh", "sync_qpc"), values)))
        except ValueError:
            malformed += 1
    # GetFrameStatistics may still refer to a previous occluded Present just
    # after restoration. Match the reported ID to an earlier successful call.
    if visibility_verified:
        samples = [s for s in samples if s["pc"] in successful_presents
                   and successful_presents[s["pc"]] <= s["observed_qpc"]]
    return frequency, samples, {"partial_tail_bytes": partial_bytes,
                                "malformed_D_events": malformed, "trace_dropped": dropped,
                                "display_visibility_verified": visibility_verified}


def counter_delta(current, previous):
    """Signed difference of 32-bit DXGI counters, including ordinary wraparound."""
    return ((current - previous + (1 << 31)) % (1 << 32)) - (1 << 31)


def infer_period(samples, frequency):
    periods, previous = [], None
    for sample in samples:
        if not sample["sync_qpc"]:
            continue
        if previous:
            refreshes = counter_delta(sample["sync_refresh"], previous["sync_refresh"])
            ticks = sample["sync_qpc"] - previous["sync_qpc"]
            if refreshes > 0 and ticks > 0:
                periods.append(ticks / refreshes)
        previous = sample
    if len(periods) < 3:
        return None, {"independent_anchor_pairs": len(periods), "reason": "need three sync-anchor pairs"}
    median = statistics.median(periods)
    spread = max(abs(x / median - 1) for x in periods)
    if not frequency / 1000 < median < frequency / 20 or spread > .002:
        return None, {"independent_anchor_pairs": len(periods), "relative_max_deviation": spread,
                      "reason": "unstable or implausible physical refresh period"}
    return median, {"independent_anchor_pairs": len(periods), "relative_max_deviation": spread}


def display_pacing(samples, frequency, lo, hi, display_hz=None, windows=None):
    samples = sorted((s for s in samples if s["pc"] > 0 and s["sync_qpc"] > 0),
                     key=lambda s: s["observed_qpc"])
    period, calibration = infer_period(samples, frequency)
    if display_hz is not None:
        if not math.isfinite(display_hz) or display_hz <= 0:
            raise ValueError("display Hz must be finite and positive")
        period = frequency / display_hz
        calibration = {"source": "explicit physical display Hz", "hz": display_hz}
    else:
        calibration["source"] = "DXGI sync-anchor differences"
    result = {"available": False, "complete": False, "calibration": calibration,
              "statistics_observations": len(samples), "skipped_present_count": None,
              "skipped_presents_per_minute": None,
              "skipped_present_scope": "Zero only when contiguous valid DXGI PresentCount IDs cover every requested span; otherwise unknown.",
              "note": "PresentCount gaps cannot distinguish skipped submitted presents from unobserved statistics. Repeated refreshes hold the previous frame."}
    if not samples or period is None:
        result["reason"] = "no valid DXGI display observations" if not samples else "physical display period unknown"
        return result
    points, conflicts, duplicates, resets = [], 0, 0, 0
    previous = None
    for sample in samples:
        point = dict(sample)
        point["display_qpc"] = sample["sync_qpc"] + counter_delta(
            sample["present_refresh"], sample["sync_refresh"]) * period
        if previous:
            change = counter_delta(point["pc"], previous["pc"])
            if change == 0:
                duplicates += 1
                if point["present_refresh"] != previous["present_refresh"]:
                    conflicts += 1
                continue
            if change < 0 or point["display_qpc"] < previous["display_qpc"]:
                resets += 1
                point["reset"] = True
        points.append(point)
        previous = point
    intervals, refresh_histogram, repeats, gaps, gap_ids, invalid = [], {}, 0, 0, 0, 0
    for left, right in zip(points, points[1:]):
        a, b = left["display_qpc"], right["display_qpc"]
        # Count unknown/corrupt observations intersecting the window even when
        # they straddle its boundary. Only wholly contained valid intervals
        # contribute percentiles and held-refresh counts.
        if not any(a < end and b > start for start, end in (windows or [(lo, hi)])):
            continue
        pc_delta = counter_delta(right["pc"], left["pc"])
        refresh_delta = counter_delta(right["present_refresh"], left["present_refresh"])
        if right.get("reset") or pc_delta <= 0 or refresh_delta <= 0 or b <= a:
            invalid += 1
            continue
        if pc_delta != 1:
            gaps += 1
            gap_ids += pc_delta - 1
            continue
        if not any(start <= a < b <= end for start, end in (windows or [(lo, hi)])):
            continue
        intervals.append((b - a) * 1000 / frequency)
        refresh_histogram[str(refresh_delta)] = refresh_histogram.get(str(refresh_delta), 0) + 1
        repeats += refresh_delta - 1
    hz = frequency / period
    bounds_covered = bool(points and all(points[0]["display_qpc"] <= start
                                         and points[-1]["display_qpc"] >= end
                                         for start, end in (windows or [(lo, hi)])))
    observed_seconds = sum(intervals) / 1000
    result.update({"available": bool(intervals), "complete": bool(intervals) and bounds_covered
                   and not (gaps or invalid or conflicts or resets),
                   "display_hz": hz, "metrics": summary(intervals), "bounds_covered": bounds_covered,
                   "unique_observed_presents": len(points), "duplicate_observations": duplicates,
                   "conflicting_observations": conflicts, "counter_resets": resets,
                   "unobserved_present_id_gaps": gap_ids, "gap_intervals_excluded": gaps,
                   "invalid_intervals_excluded": invalid, "refreshes_per_frame": refresh_histogram,
                   "repeated_refreshes": repeats,
                   "repeated_refreshes_per_minute": 60 * repeats / observed_seconds if observed_seconds else None,
                   "judder_extra_refreshes": repeats if 59 <= hz <= 61 else None,
                   "refresh_note": ("Extra refreshes hold the previous frame."
                                    if 59 <= hz <= 61 else
                                    "Native repeated refreshes include the expected 2/3-refresh cadence of 60 fps on 144 Hz; not all are judder.")})
    result["skipped_present_count"] = 0 if result["complete"] else None
    result["skipped_presents_per_minute"] = 0.0 if result["complete"] else None
    return result


def latency_fight_windows(path):
    """Live N boundaries delimit fights; resimulation boundaries cannot open a span."""
    lines, _ = _complete_lines(path)
    windows, current = [], None
    for line in lines:
        fields = line.split()
        if len(fields) < 6 or fields[0] != "N":
            continue
        try:
            stamp, _frame, resim, _early, fighting = map(int, fields[1:6])
        except ValueError:
            continue
        if resim:
            continue
        if fighting == 1:
            if current is None:
                current = [stamp, stamp]
            current[1] = stamp
        elif fighting == 0 and current is not None:
            windows.append(current)
            current = None
    if current is not None:
        windows.append(current)
    return [window for window in windows if window[1] > window[0]]


def analyze_latency(path, lo=None, hi=None, display_hz=None, fights_only=False):
    frequency, samples, parse = read_latency(path)
    if not frequency or frequency <= 0:
        raise ValueError("latency log lacks a positive QPC clock frequency")
    lines, _ = _complete_lines(path)
    presents = []
    for line in lines:
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "P":
            try:
                presents.append(int(fields[1]))
            except ValueError:
                pass
    if len(presents) < 2:
        raise ValueError("latency log needs at least two complete P events")
    lo = min(presents) if lo is None else lo
    hi = max(presents) if hi is None else hi
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        raise ValueError("window end must be after start")
    windows = [(max(a, lo), min(b, hi)) for a, b in latency_fight_windows(path)] if fights_only else [(lo, hi)]
    windows = [(a, b) for a, b in windows if b > a]
    if not windows:
        raise ValueError("no live fighting spans in latency log")
    intervals = [(b - a) * 1000 / frequency for a, b in zip(presents, presents[1:])
                 if any(start <= a < b <= end for start, end in windows)]
    display = display_pacing(samples, frequency, lo, hi, display_hz, windows)
    if parse["trace_dropped"] or parse["malformed_D_events"]:
        display["complete"] = False
        display["trace_loss"] = True
    if not parse["display_visibility_verified"]:
        display["complete"] = False
        display["visibility_note"] = "Legacy D events may include occluded presents; display visibility unverified."
    if not display["complete"]:
        display["skipped_present_count"] = None
        display["skipped_presents_per_minute"] = None
    return {"latency_log": str(Path(path)), "qpc_frequency": frequency,
            "window_qpc": [lo, hi], "fight_windows_qpc": windows,
            "requested_seconds": sum(b - a for a, b in windows) / frequency,
            "parsing": parse,
            "present_return_intervals": {"display_evidence": False, "metrics": summary(intervals)},
            "display": display}


def analyze(path, lo=None, hi=None, display_hz=None, latency=None):
    frequency, rows, parse = read_frames(path)
    if frequency <= 0 or not rows:
        raise ValueError("frame log must contain a positive clock frequency and complete rows")
    timestamps = [int(r["qpc"]) for r in rows]
    lo = min(timestamps) if lo is None else lo
    hi = max(timestamps) if hi is None else hi
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        raise ValueError("window end must be after start")
    samples = frame_statistics(rows)
    if latency:
        lf, extra, latency_parse = read_latency(latency)
        if lf != frequency:
            raise ValueError("frame and latency QPC frequencies must match")
        # A legacy D log can include occluded presents. CSV status is the stronger
        # evidence; only use D records belonging to a confirmed successful call.
        if "present_status" in rows[0]:
            successful_counts = {int(_number(r, "last_present_count")) for r in rows
                                 if r.get("present_status") == "ok"}
            extra = [s for s in extra if s["pc"] in successful_counts]
        samples.extend(extra)
        parse["latency"] = latency_parse
    selected = [r for r in rows if lo <= int(r["qpc"]) <= hi]
    # dt_us includes submission/copy/wait work before actual Present entry.
    host_dts = [_number(r, "dt_us") / 1000 for r in selected
                if _number(r, "dt_us") > 0 and int(r["qpc"]) - _number(r, "dt_us") * frequency / 1e6 >= lo]
    actual_present = [_number(r, "present_interval_us") / 1000 for r in selected
                      if r.get("present_status") == "ok" and _number(r, "present_interval_valid") == 1
                      and _number(r, "present_interval_us") > 0
                      and _number(r, "present_entry_qpc") <= hi
                      and _number(r, "present_entry_qpc") - _number(r, "present_interval_us") * frequency / 1e6 >= lo]
    statuses = {}
    for r in selected:
        status = r.get("present_status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    display = display_pacing(samples, frequency, lo, hi, display_hz)
    if "present_status" not in rows[0]:
        display["complete"] = False
        display["visibility_note"] = "Legacy CSV lacks Present status; display visibility unverified."
    trace_dropped = max((_number(r, "trace_dropped") for r in selected), default=0)
    if (trace_dropped or parse["malformed_rows"] or
            (latency and (latency_parse["trace_dropped"] or latency_parse["malformed_D_events"]))):
        display["complete"] = False
        display["trace_loss"] = True
    if not display["complete"]:
        display["skipped_present_count"] = None
        display["skipped_presents_per_minute"] = None
    intentional_skips = (int(sum(_number(r, "intentional_skip_ticks") for r in selected))
                         if "intentional_skip_ticks" in rows[0] else None)
    return {"frame_log": str(Path(path)), "qpc_frequency": frequency, "window_qpc": [lo, hi],
            "requested_seconds": (hi - lo) / frequency, "parsing": parse,
            "csv_coverage": {"first_qpc": min(timestamps), "last_qpc": max(timestamps),
                             "bounds_covered": min(timestamps) <= lo and max(timestamps) >= hi},
            "present_status_counts": statuses,
            "host_pacer_diagnostics": {
                "display_evidence": False, "intentional_skip_ticks": intentional_skips,
                "intentional_skip_ticks_per_minute": (intentional_skips * 60 * frequency / (hi - lo)
                                                       if intentional_skips is not None else None),
                "note": "Host scheduling slots intentionally skipped; not physical vblank repeats or skipped submitted presents."},
            "host_frame_intervals": {"display_evidence": False, "metrics": summary(host_dts)},
            "successful_present_entry_intervals": {"display_evidence": False, "metrics": summary(actual_present)},
            "display": display}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("frames", type=Path, nargs="?")
    parser.add_argument("--latency", type=Path)
    parser.add_argument("--display-hz", type=float, help="actual physical display refresh, never the wait test hook")
    parser.add_argument("--window-json", type=Path, help="fight_bench result.json supplying window_qpc")
    parser.add_argument("--fights-only", action="store_true", help="latency-only: live fighting N-event spans")
    parser.add_argument("--start-qpc", type=float)
    parser.add_argument("--end-qpc", type=float)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if not args.frames and not args.latency:
        parser.error("give frames.csv or --latency latency.log")
    if args.fights_only and args.frames:
        parser.error("--fights-only requires latency-only analysis (omit frames.csv)")
    lo, hi = args.start_qpc, args.end_qpc
    if args.window_json:
        bounds = json.loads(args.window_json.read_text())["window_qpc"]
        lo = bounds[0] if lo is None else lo
        hi = bounds[1] if hi is None else hi
    try:
        result = (analyze(args.frames, lo, hi, args.display_hz, args.latency) if args.frames else
                  analyze_latency(args.latency, lo, hi, args.display_hz, args.fights_only))
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    encoded = json.dumps(result, indent=2, allow_nan=False)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(encoded + "\n")
    print(encoded)


if __name__ == "__main__":
    main()
