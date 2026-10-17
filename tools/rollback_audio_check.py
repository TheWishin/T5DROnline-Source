#!/usr/bin/env python3
"""Audible check of re-simulated frames (docs/ROLLBACK.md section 8).

    python tools/rollback_audio_check.py RUNDIR [RUNDIR ...]

Each RUNDIR holds audio.f32 (AUDIO_WAV: the final mix, raw f32le stereo
48 kHz) and rb_frames.log from a T5_RB_MODE=test run. Reports per run:
  - gaps: stretches of >= 20 ms where the mix is silent (|x| < 1e-4) after
    the first sound, as count and total seconds (a dropped or starved block);
  - onsets per minute: transients (a 10 ms RMS window rising by > 6 dB over
    the previous 50 ms and above -40 dBFS), the rate at which sound effects
    start -- duplicated effects from re-simulated frames show up as a higher
    rate in the run without the sound skip than in the reference run;
  - loudness: RMS in dBFS.
"""
import os
import sys
import numpy as np


def analyze(d):
    p = os.path.join(d, "audio.f32")
    if not os.path.exists(p):
        return None
    x = np.fromfile(p, dtype=np.float32)
    if x.size < 96000:
        return None
    x = x.reshape(-1, 2).mean(axis=1)
    sr = 48000
    secs = x.size / sr
    first = np.argmax(np.abs(x) > 1e-3)
    y = x[first:]
    # gaps
    silent = np.abs(y) < 1e-4
    win = int(0.02 * sr)
    gaps = 0
    gap_s = 0.0
    run = 0
    for i in range(0, silent.size - win, win):
        if silent[i:i + win].all():
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
    onsets = 0
    for i in range(5, n):
        prev = db[i - 5:i].max()
        if db[i] > -40 and db[i] - prev > 6:
            onsets += 1
    minutes = y.size / sr / 60
    loud = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
    return dict(seconds=secs, gaps=gaps, gap_s=gap_s, onsets=onsets, onsets_per_min=onsets / max(minutes, 1e-6), loud=loud)


def main():
    for d in sys.argv[1:]:
        r = analyze(d)
        if not r:
            print(f"{d}: no audio.f32")
            continue
        rb = 0
        lp = os.path.join(d, "game.log")
        if os.path.exists(lp):
            rb = sum(1 for l in open(lp, errors="replace") if "ROLLBACK at" in l)
        print(f"{d}: {r['seconds']:.0f} s, {rb} rollbacks, gaps {r['gaps']} ({r['gap_s']:.2f} s), onsets {r['onsets']} ({r['onsets_per_min']:.0f}/min), loudness {r['loud']:.1f} dBFS")


if __name__ == "__main__":
    main()
