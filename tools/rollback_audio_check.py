#!/usr/bin/env python3
"""Audible check of rollbacks (docs/ROLLBACK.md sections 8 and 20).

    python tools/rollback_audio_check.py RUNDIR|audio.f32 [...] [--ref RUNDIR|audio.f32]

Each argument is a run directory holding audio.f32 (AUDIO_WAV: the final
mix, raw f32le stereo 48 kHz) or the file itself. Reports per recording:
  - onsets: transients (a 10 ms RMS window rising by > 6 dB over the loudest
    of the previous 50 ms and above -40 dBFS) -- the rate at which sounds
    start. A rollback that starts its frames' sounds again adds onsets; one
    that drops them removes some. Record with ATRAC_MUTE=1 (music decoded but
    silent) so the onsets are the sound effects and voices alone;
  - re-triggers: onsets within 30-120 ms of the previous one -- a doubled or
    restarted hit shows up here first;
  - gaps: stretches of >= 20 ms where the mix is silent (|x| < 1e-4) after
    the first sound (a starved stream or a dropped block: the music hiccup);
  - loudness: RMS in dBFS.
With --ref, the differences to the reference recording (same scripts, no
rollbacks), per minute of audio so recordings of different length compare.
--match N cuts each recording to match N (FIGHT START .. MATCH OVER + 2 s,
from the marks.json tools/rollback_net_test.py --audio writes); the same match
holds the same sounds however long it took, so then the counts are compared
directly. For a count of the sound effects alone record with ATRAC_MUTE=1
(no music) and T5_RB_SND_NOVOICE=1 (no fighter voices: they are a random
draw that differs from run to run).
"""
import os
import sys
import numpy as np


MATCH = 0


def load(p):
    d = p if os.path.isdir(p) else os.path.dirname(p)
    if os.path.isdir(p):
        p = os.path.join(p, "audio.f32")
    if not os.path.exists(p):
        return None, p
    x = np.fromfile(p, dtype=np.float32)
    if x.size < 96000:
        return None, p
    x = x.reshape(-1, 2).mean(axis=1)
    if MATCH:
        import json
        marks = json.load(open(os.path.join(d, "marks.json")))
        starts = [m["audio_s"] for m in marks if m["event"] == "start"]
        overs = [m["audio_s"] for m in marks if m["event"] == "over"]
        if len(starts) < MATCH or len(overs) < MATCH:
            return None, p + f" (no match {MATCH} in marks.json)"
        a, b = starts[MATCH - 1], overs[MATCH - 1] + 2.0
        x = x[int(a * 48000):int(b * 48000)]
        p += f" [match {MATCH}: {a:.1f}-{b:.1f} s]"
    return x, p


def analyze(x):
    sr = 48000
    secs = x.size / sr
    first = int(np.argmax(np.abs(x) > 1e-3))
    y = x[first:]
    # gaps
    win = int(0.02 * sr)
    n = y.size // win
    silent = (np.abs(y[: n * win]).reshape(n, win).max(axis=1) < 1e-4)
    gaps, gap_s, run = 0, 0.0, 0
    for s in silent:
        if s:
            run += 1
        else:
            if run:
                gaps += 1
                gap_s += run * 0.02
            run = 0
    # onsets
    w = int(0.01 * sr)
    n = y.size // w
    rms = np.sqrt(np.mean(y[: n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    on = []
    for i in range(5, n):
        if db[i] > -40 and db[i] - db[i - 5:i].max() > 6:
            on.append(i)
    on = np.array(on)
    d = np.diff(on) if on.size > 1 else np.array([])
    retrig = int(np.sum((d >= 3) & (d <= 12)))
    minutes = y.size / sr / 60
    loud = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
    return dict(seconds=secs, minutes=minutes, gaps=gaps, gap_s=gap_s, onsets=int(on.size), retrig=retrig, loud=loud)


def fmt(r):
    return (f"{r['seconds']:.0f} s, onsets {r['onsets']} ({r['onsets'] / max(r['minutes'], 1e-6):.1f}/min), "
            f"re-triggers {r['retrig']} ({r['retrig'] / max(r['minutes'], 1e-6):.1f}/min), "
            f"gaps {r['gaps']} ({r['gap_s']:.2f} s), loudness {r['loud']:.1f} dBFS")


def main():
    global MATCH
    args = sys.argv[1:]
    if "--match" in args:
        i = args.index("--match")
        MATCH = int(args[i + 1])
        del args[i:i + 2]
    ref = None
    if "--ref" in args:
        i = args.index("--ref")
        ref = args[i + 1]
        del args[i:i + 2]
    rr = None
    if ref:
        x, p = load(ref)
        if x is None:
            print(f"{p}: no audio")
        else:
            rr = analyze(x)
            print(f"reference {p}: {fmt(rr)}")
    for a in args:
        x, p = load(a)
        if x is None:
            print(f"{p}: no audio")
            continue
        r = analyze(x)
        line = f"{p}: {fmt(r)}"
        if rr and MATCH:
            # the same match (same game frames): its sounds are the same set however
            # long it took on the wall clock, so the counts compare directly
            line += (f"; vs reference: onsets {r['onsets'] - rr['onsets']:+d} ({100.0 * (r['onsets'] - rr['onsets']) / max(rr['onsets'], 1):+.1f} %), "
                     f"re-triggers {r['retrig'] - rr['retrig']:+d}, gaps {r['gaps'] - rr['gaps']:+d}")
        elif rr:
            on = r["onsets"] / r["minutes"] - rr["onsets"] / rr["minutes"]
            rt = r["retrig"] / r["minutes"] - rr["retrig"] / rr["minutes"]
            line += (f"; vs reference: onsets {100 * on / max(rr['onsets'] / rr['minutes'], 1e-6):+.1f} %/min, "
                     f"re-triggers {rt:+.1f}/min, gaps {r['gaps'] - rr['gaps']:+d}")
        print(line)


if __name__ == "__main__":
    main()
