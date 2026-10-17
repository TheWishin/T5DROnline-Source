#!/usr/bin/env python3
"""Check what the audio device got in a game run (ps3recomp patch 0026).

The runtime writes two raw f32le stereo 48 kHz files, one block (256 frames)
per mixer block and in step with each other:

    AUDIO_WAV=audio_mix.f32            the final mix, every block
    PS3_AUDIO_DEVICE_WAV=audio_dev.f32 the same block where an output device
                                       took it, silence where there was none

Run the game with both (relative names land in the game's working directory),
optionally with the test hooks PS3_AUDIO_FAKE_NODEVICE=<s> and
PS3_AUDIO_FAKE_LOSS=t1,t2,..., then:

    python tools/audio_device_check.py <dir with game.log and the two files>
        [--first-sound-after S] [--max-gap S] [--losses N]

It reads the `[cellAudio] audio device opened/lost/waiting ... [t=..]` lines of
game.log and, per stretch with a device and per stretch without, counts the
mix blocks that carry sound and how many reached the device. Checks:

  - no sound reaches the device while no device is open;
  - with a device open, (nearly) every loud block reaches it, and the block is
    the mix block of the same index (so the music stays in step with the game);
  - after a loss, or a "default audio device changed" line, a device is open
    again within --max-gap seconds (default 1.0);
  - --first-sound-after S: the first device opens no earlier than S seconds
    (and within 2.5 s after it: the retry period is 2 s);
  - --losses N / --changes N: exactly N losses / default-device changes were
    logged.

Also prints the fps lines and [audio-rate] summary of the log. Exit 0 = all
checks passed.
"""
import argparse
import array
import os
import re
import statistics
import sys

BLOCK = 256               # frames per block
RATE = 48000
FLOATS = BLOCK * 2
EV = re.compile(r"\[cellAudio\] (?:audio device (opened|lost|waiting)\b|(default audio device changed), switching)"
                r"(.*?)\[t=([0-9.]+)s\]")
FPS = re.compile(r"\[fps\] ([0-9.]+)")
AREATE = re.compile(r"\[audio-rate\] ([0-9.]+) blocks/s.*?silent ([0-9.]+)%.*?dropped ([0-9.]+) frames/s"
                    r".*?(?:no device (\d+))?\s*$")


def read_blocks(path):
    with open(path, "rb") as f:
        data = f.read()
    n = len(data) // (FLOATS * 4)
    return data, n


def loud(block_bytes):
    a = array.array("f")
    a.frombytes(block_bytes)
    return max(a) > 1e-4 or min(a) < -1e-4


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="the run's directory: game.log, and audio_mix.f32 + audio_dev.f32 there or in its cwd/ "
                                "(a smoke test directory, or a netplay_test.py run1/)")
    ap.add_argument("--log", default="game.log")
    ap.add_argument("--mix", default="audio_mix.f32")
    ap.add_argument("--dev", default="audio_dev.f32")
    ap.add_argument("--first-sound-after", type=float, default=None)
    ap.add_argument("--max-gap", type=float, default=1.0)
    ap.add_argument("--losses", type=int, default=None)
    ap.add_argument("--changes", type=int, default=None, help="expected number of default-device changes")
    a = ap.parse_args(argv)

    d = a.dir
    log = os.path.join(d, a.log)
    mix_p = os.path.join(d, a.mix) if os.path.isfile(os.path.join(d, a.mix)) else os.path.join(d, "cwd", a.mix)
    dev_p = os.path.join(d, a.dev) if os.path.isfile(os.path.join(d, a.dev)) else os.path.join(d, "cwd", a.dev)
    if not os.path.isfile(log):
        sys.exit(f"no {a.log} in {d}")
    for p in (mix_p, dev_p):
        if not os.path.isfile(p):
            sys.exit(f"missing {p} (run the game with AUDIO_WAV=audio_mix.f32 PS3_AUDIO_DEVICE_WAV=audio_dev.f32)")

    with open(log, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    events = [(float(m.group(4)), m.group(1) or "changed", m.group(3).strip()) for m in EV.finditer(text)]
    print("device events:")
    for t, kind, rest in events:
        print(f"  t={t:7.2f} s  {kind:8s} {rest[:110]}")

    # Intervals with a device: [opened, next lost) (or the end of the files).
    mix, n_mix = read_blocks(mix_p)
    dev, n_dev = read_blocks(dev_p)
    n = min(n_mix, n_dev)
    t_end = n * BLOCK / RATE
    spans, t_open = [], None
    for t, kind, _ in events:
        if kind == "opened":
            if t_open is None:
                t_open = t
        elif kind == "lost" and t_open is not None:
            spans.append((t_open, t))
            t_open = None
    if t_open is not None:
        spans.append((t_open, t_end))

    def has_device(i):
        t = i * BLOCK / RATE
        for a0, b0 in spans:
            if a0 <= t < b0:
                return True
        return False

    inside = dict(loud=0, got=0, wrong=0)
    outside = dict(loud=0, got=0, wrong=0)
    first_dev_sound = None
    # a device that opened/lost a few ms off the block grid: ignore blocks within 60 ms of a span edge
    edge = 0.06
    def near_edge(i):
        t = i * BLOCK / RATE
        return any(abs(t - e) < edge for s in spans for e in s)
    mix_loud_total = 0
    for i in range(n):
        mb = mix[i * FLOATS * 4:(i + 1) * FLOATS * 4]
        db = dev[i * FLOATS * 4:(i + 1) * FLOATS * 4]
        if not loud(mb):
            if loud(db):
                (inside if has_device(i) else outside)["wrong"] += 1
            continue
        mix_loud_total += 1
        got = db == mb
        wrong = (not got) and loud(db)
        if got and first_dev_sound is None:
            first_dev_sound = i * BLOCK / RATE
        if near_edge(i):
            continue
        tgt = inside if has_device(i) else outside
        tgt["loud"] += 1
        tgt["got"] += 1 if got else 0
        tgt["wrong"] += 1 if wrong else 0

    print(f"\nmix: {n} blocks ({t_end:.1f} s), {mix_loud_total} carry sound")
    print(f"with a device open:  {inside['loud']:6d} loud blocks, {inside['got']:6d} reached the device, "
          f"{inside['wrong']} differing")
    print(f"no device open:      {outside['loud']:6d} loud blocks, {outside['got']:6d} reached the device, "
          f"{outside['wrong']} differing")
    if first_dev_sound is not None:
        print(f"first sound at the device: t={first_dev_sound:.2f} s")

    fails = []
    def check(ok, msg):
        print(("ok    " if ok else "FAIL  ") + msg)
        if not ok:
            fails.append(msg)

    print()
    check(outside["got"] == 0, f"nothing reaches the device while none is open ({outside['got']} blocks did)")
    check(inside["wrong"] == 0 and outside["wrong"] == 0,
          "every block the device got is the mix block of the same index (music stays in step)")
    if inside["loud"]:
        frac = inside["got"] / inside["loud"]
        check(frac >= 0.97, f"with a device open {100 * frac:.1f}% of the loud blocks reach it (>= 97%)")
    elif any(k == "opened" for _, k, _ in events):
        check(False, "a device was open but no loud block was mixed during that time")
    opens = [t for t, k, _ in events if k == "opened"]
    losts = [t for t, k, _ in events if k == "lost"]
    if a.first_sound_after is not None:
        if opens:
            check(opens[0] >= a.first_sound_after - 0.05 and opens[0] <= a.first_sound_after + 2.5,
                  f"first device opened at t={opens[0]:.2f} s (fake window {a.first_sound_after:.1f} s + up to one 2 s retry)")
        else:
            check(False, "no device was ever opened")
    prev, what = None, ""
    for t, kind, _ in events:
        if kind in ("lost", "changed"):
            prev, what = t, "loss" if kind == "lost" else "default change"
        elif kind == "opened" and prev is not None:
            gap = t - prev
            check(gap <= a.max_gap, f"{what} at t={prev:.2f} s: device open again after {gap:.2f} s (<= {a.max_gap:.1f} s)")
            prev = None
    if prev is not None:
        check(False, f"{what} at t={prev:.2f} s was never followed by an open device")
    if a.losses is not None:
        check(len(losts) == a.losses, f"{len(losts)} loss(es) logged, expected {a.losses}")
    if a.changes is not None:
        n_chg = sum(1 for _, k, _ in events if k == "changed")
        check(n_chg == a.changes, f"{n_chg} default-device change(s) logged, expected {a.changes}")

    fps = [float(m.group(1)) for m in FPS.finditer(text)]
    if len(fps) > 2:
        w = fps[2:]
        print(f"\n[fps] {len(fps)} windows: median {statistics.median(w):.1f}, min {min(w):.1f}, max {max(w):.1f}")
    rates = []
    for line in text.splitlines():
        m = AREATE.match(line)
        if m:
            rates.append((float(m.group(1)), float(m.group(2)), float(m.group(3)), int(m.group(4) or 0)))
    if rates:
        print(f"[audio-rate] {len(rates)} windows: blocks/s median {statistics.median(r[0] for r in rates):.1f} "
              f"(min {min(r[0] for r in rates):.1f}), silent median {statistics.median(r[1] for r in rates):.1f}%, "
              f"no-device blocks total {sum(r[3] for r in rates)}")
    print("\n" + ("all checks passed" if not fails else f"{len(fails)} check(s) FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
