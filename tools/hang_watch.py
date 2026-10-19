"""Watch the games of a fight_flow_test / reset_cycle_test run: when a game's log stops growing
for --quiet seconds, ask its PS3_DEBUG console (dbg.cmd in its run dir) for "threads", once per
stall, and keep the answer (dbg.cmd.out) under a numbered name.

    python tools/hang_watch.py RUNDIR [--quiet 40]     (games started with PS3_DEBUG=dbg.cmd)
"""
import glob
import os
import shutil
import sys
import time

run = sys.argv[1]
quiet = float(sys.argv[sys.argv.index("--quiet") + 1]) if "--quiet" in sys.argv else 40.0
asked = {}
n = 0
while True:
    for d in sorted(glob.glob(os.path.join(run, "run*"))):
        logs = sorted(glob.glob(os.path.join(d, "game*.log")), key=os.path.getmtime)
        if not logs:
            continue
        log = logs[-1]
        age = time.time() - os.path.getmtime(log)
        key = (log, int(os.path.getmtime(log)))
        if age > quiet and key not in asked:
            asked[key] = True
            n += 1
            cmd = os.path.join(d, "dbg.cmd")
            # threads, then the draw side's request managers (geometry 0x10742880:
            # +8 busy count, +0x50 semaphore; draw 0x1074BE80: +0x48 list, +0x98 counter)
            for c in ("threads", "mem 10742880 96", "mem 1074BEC0 128"):
                with open(cmd, "w") as f:
                    f.write(c + "\n")
                for _ in range(50):
                    time.sleep(0.2)
                    if os.path.getsize(cmd) == 0:
                        break
                time.sleep(2)
            print(f"{time.strftime('%H:%M:%S')} {log}: quiet {age:.0f} s -- asked for threads and manager memory", flush=True)
            time.sleep(3)
            out = cmd + ".out"
            if os.path.exists(out):
                shutil.copy(out, os.path.join(d, f"threads_{n}.txt"))
                print(f"  saved {os.path.join(d, f'threads_{n}.txt')} ({os.path.getsize(out)} bytes)", flush=True)
            else:
                print("  no answer", flush=True)
    if os.path.exists(os.path.join(run, "report.json")) and any(
            "ALL OK" in l or "FAILED:" in l for l in open(run + ".log", errors="replace")):
        break
    time.sleep(5)
