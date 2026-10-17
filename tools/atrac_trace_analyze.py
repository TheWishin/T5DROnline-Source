#!/usr/bin/env python3
"""Interleave an ATRAC_TRACE=1 game.log's stream adds with the rollback loop's
rollbacks and the decoder's errors: python atrac_trace_analyze.py GAME.LOG"""
import re, sys
log = sys.argv[1]
ev = []
for n, line in enumerate(open(log, errors="replace"), 1):
    m = re.search(r"AddStreamData handle=0x([0-9A-F]+) (\d+) bytes at \+0x([0-9A-F]+) \(file @0x([0-9A-F]+)\) have (\d+)/(\d+)", line)
    if m:
        ev.append((n, "add", int(m.group(2)), int(m.group(3), 16), int(m.group(4), 16), int(m.group(5)))); continue
    m = re.search(r"rbnet: frame (\d+): rollback to (\d+) \((\d+) frames\)", line)
    if m:
        ev.append((n, "rollback", int(m.group(1)), int(m.group(2)), int(m.group(3)), 0)); continue
    if "Invalid start bit" in line or "doesn't match channel" in line:
        ev.append((n, "decode-error", 0, 0, 0, 0)); continue
    if "decided before a rollback" in line:
        ev.append((n, "dropped-add", 0, 0, 0, 0)); continue
    if "SetData handle" in line:
        ev.append((n, "setdata", 0, 0, 0, 0)); continue
    if "abort() is called" in line:
        ev.append((n, "ABORT", 0, 0, 0, 0)); continue
print(f"{len(ev)} events")
# summary: adds whose file offset is not the previous add's offset + bytes (regressions / jumps)
prev_end = None
jumps = 0
first_err = next((i for i, e in enumerate(ev) if e[1] == "decode-error"), None)
for i, e in enumerate(ev):
    if e[1] == "add":
        n, _, nbytes, wr, fpos, have = e
        if prev_end is not None and fpos != prev_end:
            jumps += 1
            if jumps <= 15:
                print(f"line {n}: add {nbytes} B at ring +0x{wr:X} file @0x{fpos:X} (expected @0x{prev_end:X}, {'back' if fpos < prev_end else 'forward'} {abs(fpos-prev_end)}) have {have}")
        prev_end = fpos + nbytes
    elif e[1] == "setdata":
        prev_end = None
print(f"file-offset jumps between consecutive adds: {jumps}")
if first_err is not None:
    lo = max(0, first_err - 12)
    print("--- events before the first decode error ---")
    for e in ev[lo:first_err + 2]:
        n, kind = e[0], e[1]
        if kind == "add": print(f"line {n}: add {e[2]} B at +0x{e[3]:X} file @0x{e[4]:X} have {e[5]}")
        elif kind == "rollback": print(f"line {n}: ROLLBACK at {e[2]} -> {e[3]} ({e[4]} frames)")
        else: print(f"line {n}: {kind}")
# adds right after rollbacks: how many land at a different ring position than the previous add's end
print("--- first 10 rollbacks and the next add after each ---")
shown = 0
for i, e in enumerate(ev):
    if e[1] == "rollback" and shown < 10:
        nxt = next((x for x in ev[i + 1:i + 30] if x[1] == "add"), None)
        prv = next((x for x in reversed(ev[max(0, i - 30):i]) if x[1] == "add"), None)
        if nxt and prv:
            print(f"rollback line {e[0]} ({e[4]} frames): previous add @file 0x{prv[4]:X}+{prv[2]} ring +0x{prv[3]:X}; next add @file 0x{nxt[4]:X} ring +0x{nxt[3]:X} {'(file regressed)' if nxt[4] < prv[4] + prv[2] else ''}")
            shown += 1
