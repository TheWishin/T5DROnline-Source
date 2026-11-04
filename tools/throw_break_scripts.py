#!/usr/bin/env python3
"""Write reproducible Jin/Jin throw-break probes (no game data).

Offline: T5_RB_START=auto,T5_RB_START_DELAY=0,T5_RB_MODE=test,
T5_RB_SAVE_EVERY=100000,T5_FIGHT=jin,jin,20,3. The defender script has
one correctly timed Square press; use an empty script for the thrown control.
Online: T5_FIGHT=jin,jin,20,1,T5_NET_DELAY=N,T5_RB_NET_DELAY=N.
The defender responds 13 frames after the delayed contact, so its delivered
press is beyond the original endpoint for N>=3. Attacks after the probe finish
the round. Both scripts use the netplay parser's decimal/0x-prefixed syntax.
"""
import argparse
from pathlib import Path


def scripts(delay, offline=False, attacker=1):
    forward = 0x20 if attacker == 1 else 0x80
    if offline:
        attack = [(1600, 60, forward), (1680, 1, 0xC000)]
        defend = [(1698, 1, 0x8000)]
    else:
        attack = [(800, 28, forward), (840, 1, 0xC000)]
        defend = [(866 + delay, 1, 0x8000)]
        for frame in range(1050, 9000, 50):
            attack += [(frame, 6, forward), (frame + 10, 4, 0x4040 | forward),
                       (frame + 30, 4, 0x9000)]
    return (attack, defend) if attacker == 1 else (defend, attack)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--delay", type=int, choices=range(31), default=3)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--attacker", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for player, events in enumerate(scripts(args.delay, args.offline, args.attacker), 1):
        (out / f"p{player}.txt").write_text(
            "".join(f"{frame} {length} {mask:#x}\n" for frame, length, mask in events), encoding="ascii")
    (out / "neutral.txt").write_text("", encoding="ascii")


if __name__ == "__main__":
    main()
