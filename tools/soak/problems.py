"""Scan a t5dr.exe log for the problems the offline soak watches (docs/SOAK.md).

    python tools/soak/problems.py game.log [--fps-min 59] [--json out.json]

Categories (each: count, first lines with their log line numbers):

  crash       [CRASH], unhandled exceptions, abort()
  nid         [hle] unresolved NID
  syscall     unimplemented lv2 syscalls
  guest       NULL calls/reads/writes, unregistered OPDs, unresolved indirect calls
  render      live-draw drop counters (fetch/degen/prim/alloc/pso/ring/surface), texture decode
              failures, white fallback binds, vertex-texture misses, queue-full packets
  shader      shader TODO / unsupported / compile failures
  decode      movie (cellVdec/Adec/Dmux/Pamf, Media Foundation) and music (cellAtrac) errors,
              ATRAC bad frames, inflate failures
  audio       [audio-rate]: blocks starved at the device, blocks the title had not written,
              blocks mixed without a device, dropped frames; device lost/waiting lines
  fifo        GCM ring recycles, flips the FIFO walker never reached, walker resyncs
  fps         [fps] windows below --fps-min (with the frame range)
  watchdog    the runtime's [WATCHDOG] thread samples
  other       anything else that says error/fail/warn (shape-deduplicated), for a human to read

scan(text) returns a dict; summary(d) a few lines of text.
"""
import argparse
import json
import re
import sys

RX = [
    ("crash", re.compile(r"\[CRASH\]|unhandled exception|abort\(\) is called|\[(GUARD|EXC|abort)\]", re.I)),
    ("nid", re.compile(r"\[hle\] unresolved NID")),
    ("syscall", re.compile(r"\[LV2\] unimplemented|unimplemented syscall|syscall \d+ .*not implemented", re.I)),
    ("guest", re.compile(r"^\[(null-call|null-write|null-read)\]|bctr to NULL|guest_call: OPD .* not registered|"
                         r"unresolved indirect call|garbage vcall")),
    ("shader", re.compile(r"\bTODO\b|shader.*(unsupported|unhandled|fail)|(unsupported|unhandled) (opcode|instruction)|"
                          r"D3DCompile.*fail|compile failed", re.I)),
    ("decode", re.compile(r"^\[(cellVdec|cellAdec|cellDmux|cellPamf|mf_h264|cellAtrac)\].*(error|fail|corrupt|invalid)|"
                          r"inflate failed", re.I)),
    ("audio", re.compile(r"\[cellAudio\] (audio device lost|audio device waiting|could not|new default audio device could not|sound glitches)|"
                         r"\[cellAudio\] port \d+ HAS DATA but never started")),
    ("fifo", re.compile(r"recycled the title's own ring|queued flip never reached|FIFO resync|walker circling|"
                        r"flip valve|unmapped IO|\[cellGcmSys\].*(stall|stuck)", re.I)),
    ("watchdog", re.compile(r"^\[WATCHDOG\] \S+ sample")),
]
RE_FPS = re.compile(r"^\[fps\] ([0-9.]+)(?: \(frames (\d+)\.\.(\d+) over ([0-9.]+)s\))?")
RE_AUDIO = re.compile(r"^\[audio-rate\] ([0-9.]+) blocks/s.*?silent ([0-9.]+)%, dropped ([0-9.]+) frames/s, device buf (\d+), "
                      r"queue min (\d+), starved (\d+), waited for (\d+) \(max ([0-9.]+) ms\), not written (\d+), no device (\d+)")
RE_LD = re.compile(r"^\[live-draw\] frame (\d+) packets\[seen=(\d+) queued=(\d+) movie=(\d+) qfull=(\d+)\] .*?"
                   r"drop\{fetch=(\d+) degen=(\d+) prim=(\d+) alloc=(\d+) pso=(\d+) ring=(\d+) surface=(\d+)\}.*?"
                   r"textures\[cached=\d+/\d+ full=(\d+) decodefail=(\d+).*?vtex\[.*?unsupported=(\d+) missingTXL=(\d+)\].*?"
                   r"binds\[white=(\d+)")
LD_KEYS = ("qfull", "drop_fetch", "drop_degen", "drop_prim", "drop_alloc", "drop_pso", "drop_ring", "drop_surface",
           "tex_full", "tex_decodefail", "vtex_unsupported", "vtex_missingTXL", "binds_white")
RE_ATRAC_BAD = re.compile(r"\[cellAtrac\] DeleteDecoder .*?(\d+) bad frames")
RE_TICK = re.compile(r"^\[spu-tick\] tid 0x[0-9A-F]+: (\d+) answers, mean ([0-9.]+) ms, .*?over 5\.33 ms: (\d+)"
                     r"(?:; on the CPU ([0-9.]+) M cycles)?")
RE_OTHER = re.compile(r"\b(error|failed|failure|fail|warning|warn|timeout|timed out|overrun|underrun|lost)\b", re.I)
# Lines with those words that are routine on a healthy run (each explained in docs/SOAK.md).
OTHER_OK = re.compile(
    r"^\[cellNetCtl\] GetState\(\) -> error NOT_INITIALIZED|"       # offline model: the title shows its own message
    r"^\[cellGame\]|^\[sc-caller\]|^\[WAIT\]|^\[evt\]|^\[fs\]|"
    r"^\[cellSaveData\] (funcStat|dispatching)|"
    r"^\[hle-trace\]|^\[tex-refresh\]|^\[surfsz\]|"
    r"sys_ppu_thread_set_priority.*ESRCH|"                          # lv2 does not treat -1 as self (GAPS.md #17)
    r"^\[pacing\]|^\[sched\]|^\[gpu\]|^\[display\]|^\[pad\]|^\[pso-prewarm\] \d+ pipeline\(s\) created ahead, 0 failed")


def shape(line):
    return re.sub(r"0x[0-9A-Fa-f]+|\d+(\.\d+)?", "N", line)[:140]


def scan(text, fps_min=59.0, keep=8):
    out = {c: {"count": 0, "first": []} for c, _ in RX}
    out["other"] = {"count": 0, "first": [], "shapes": {}}
    fps, low = [], []
    audio = {"windows": 0, "starved": 0, "not_written": 0, "no_device": 0, "dropped_windows": 0,
             "silent_max": 0.0, "silent": [], "queue_min_min": None, "waited": 0, "wait_max_ms": 0.0}
    ld_first, ld_last = None, None
    atrac_bad = 0
    tick = {"windows": 0, "answers": 0, "over": 0, "wall_ms": [], "mcyc": []}
    for no, line in enumerate(text.splitlines(), 1):
        line = line.rstrip("\r")
        m = RE_FPS.match(line)
        if m:
            v = float(m.group(1))
            fr = (int(m.group(2)), int(m.group(3))) if m.group(2) else None
            fps.append((no, v, fr))
            if v < fps_min:
                low.append({"line": no, "fps": v, "frames": fr})
            continue
        m = RE_AUDIO.match(line)
        if m:
            audio["windows"] += 1
            silent = float(m.group(2))
            audio["silent"].append(silent)
            audio["silent_max"] = max(audio["silent_max"], silent)
            if float(m.group(3)) > 0:
                audio["dropped_windows"] += 1
            qmin = int(m.group(5))
            audio["queue_min_min"] = qmin if audio["queue_min_min"] is None else min(audio["queue_min_min"], qmin)
            audio["starved"] += int(m.group(6))
            audio["waited"] += int(m.group(7))
            audio["wait_max_ms"] = max(audio["wait_max_ms"], float(m.group(8)))
            audio["not_written"] += int(m.group(9))
            audio["no_device"] += int(m.group(10))
            if int(m.group(6)) or int(m.group(9)):
                a = out["audio"]
                a["count"] += 1
                if len(a["first"]) < keep:
                    a["first"].append(f"{no}: {line[:220]}")
            continue
        m = RE_LD.match(line)
        if m:
            vals = dict(zip(LD_KEYS, (int(x) for x in m.groups()[4:])))
            vals["frame"] = int(m.group(1))
            if ld_first is None:
                ld_first = vals
            if ld_last and any(vals[k] > ld_last[k] for k in LD_KEYS):
                r = out.setdefault("render", {"count": 0, "first": []})
                r["count"] += 1
                if len(r["first"]) < keep:
                    grew = {k: vals[k] - ld_last[k] for k in LD_KEYS if vals[k] > ld_last[k]}
                    r["first"].append(f"{no}: frame {vals['frame']}: +{grew}")
            ld_last = vals
            continue
        if line.startswith("[live-draw] frame") or line.startswith("[WATCHDOG]  "):
            continue
        m = RE_TICK.match(line)
        if m:
            tick["windows"] += 1
            tick["answers"] += int(m.group(1))
            tick["over"] += int(m.group(3))
            tick["wall_ms"].append(float(m.group(2)))
            if m.group(4):
                tick["mcyc"].append(float(m.group(4)))
            continue
        m = RE_ATRAC_BAD.search(line)
        if m:
            atrac_bad += int(m.group(1))
        hit = False
        for cat, rx in RX:
            if rx.search(line):
                d = out[cat]
                d["count"] += 1
                if len(d["first"]) < keep:
                    d["first"].append(f"{no}: {line[:240]}")
                hit = True
                break
        if hit:
            continue
        if RE_OTHER.search(line) and not OTHER_OK.search(line):
            o = out["other"]
            o["count"] += 1
            s = shape(line)
            if s not in o["shapes"]:
                o["shapes"][s] = [0, no, line[:240]]
            o["shapes"][s][0] += 1
    out.setdefault("render", {"count": 0, "first": []})
    out["render"]["live_draw_totals"] = ld_last
    out["fps"] = {"windows": len(fps), "below": len(low), "fps_min": fps_min, "low": low[:200],
                  "min": min((v for _, v, _ in fps), default=None),
                  "median": sorted(v for _, v, _ in fps)[len(fps) // 2] if fps else None}
    out["audio_rate"] = audio
    out["atrac_bad_frames"] = atrac_bad
    out["spu_tick"] = {"windows": tick["windows"], "answers": tick["answers"], "over_5_33ms": tick["over"],
                       "wall_ms_median": sorted(tick["wall_ms"])[len(tick["wall_ms"]) // 2] if tick["wall_ms"] else None,
                       "mcycles_median": sorted(tick["mcyc"])[len(tick["mcyc"]) // 2] if tick["mcyc"] else None}
    out["other"]["shapes"] = {k: v for k, v in sorted(out["other"]["shapes"].items(), key=lambda kv: kv[1][1])}
    return out


def summary(d):
    lines = []
    for cat in ("crash", "nid", "syscall", "guest", "render", "shader", "decode", "audio", "fifo", "watchdog"):
        c = d.get(cat, {})
        lines.append(f"{cat:9s} {c.get('count', 0)}" + (f"   e.g. {c['first'][0][:160]}" if c.get("first") else ""))
    f = d["fps"]
    lines.append(f"fps       {f['windows']} windows, median {f['median']}, min {f['min']}, {f['below']} below {f['fps_min']}")
    a = d["audio_rate"]
    lines.append(f"audio     {a['windows']} windows: starved {a['starved']}, not written {a['not_written']}, "
                 f"no device {a['no_device']}, dropped in {a['dropped_windows']} windows, silent max {a['silent_max']}%, "
                 f"waited {a['waited']} (max {a['wait_max_ms']} ms), queue min {a['queue_min_min']}")
    lines.append(f"atrac     {d['atrac_bad_frames']} bad frames")
    t = d.get("spu_tick") or {}
    if t.get("windows"):
        lines.append(f"spu-tick  {t['answers']} answers in {t['windows']} windows, {t['over_5_33ms']} over 5.33 ms, "
                     f"median wall {t['wall_ms_median']} ms, median {t['mcycles_median']} M cycles on the CPU")
    t = d["render"].get("live_draw_totals") or {}
    if t:
        lines.append("live-draw totals: " + ", ".join(f"{k}={t[k]}" for k in LD_KEYS) + f" (frame {t['frame']})")
    o = d["other"]
    lines.append(f"other     {o['count']} lines, {len(o['shapes'])} shapes")
    for s, (n, no, line) in list(o["shapes"].items())[:25]:
        lines.append(f"   {n:5d}x  {no}: {line[:170]}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--fps-min", type=float, default=59.0)
    ap.add_argument("--json")
    a = ap.parse_args()
    with open(a.log, encoding="utf-8", errors="replace") as f:
        d = scan(f.read(), a.fps_min)
    print(summary(d))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)


if __name__ == "__main__":
    sys.exit(main())
