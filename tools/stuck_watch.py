"""Watch S of a reset_cycle_test run: a 'fight' command not followed by any df state change
for --quiet s -> ask S's PS3_DEBUG console for threads (and the select / file manager words), once per command.

    python tools/stuck_watch.py RUNDIR [--quiet 60]     (games started with --env PS3_DEBUG=dbg.cmd)
"""
import os, re, sys, time
run = sys.argv[1]
quiet = float(sys.argv[sys.argv.index("--quiet") + 1]) if "--quiet" in sys.argv else 60.0
d = os.path.join(run, "run1")
done = set()
n = 0
while True:
    log = os.path.join(d, "game1.log")
    if os.path.exists(log):
        lines = open(log, errors="replace").read().splitlines()
        last_cmd = None
        for i, l in enumerate(lines):
            if re.search(r"\[df\] frame \d+: control command \d+: fight", l):
                last_cmd = (i, l)
        if last_cmd and last_cmd[1] not in done:
            later = [l for l in lines[last_cmd[0] + 1:] if re.search(r"\[df\] frame \d+: (state|session|the select)", l)]
            age = time.time() - os.path.getmtime(os.path.join(d, "status.json")) if os.path.exists(os.path.join(d, "status.json")) else 0
            if not later and age > quiet:
                done.add(last_cmd[1]); n += 1
                cmd = os.path.join(d, "dbg.cmd")
                for c in ("threads", "mem 1008F070 16", "mem 10093F58 240", "mem 10751A00 96", "hle", "stat"):
                    with open(cmd, "w") as f:
                        f.write(c + "\n")
                    for _ in range(50):
                        time.sleep(0.2)
                        if os.path.getsize(cmd) == 0:
                            break
                    time.sleep(2)
                print(time.strftime("%H:%M:%S"), "stuck after", last_cmd[1], "-- dumped", flush=True)
    if os.path.exists(run + ".log") and any(("ALL" in l and "cycle" in l) or "FAILED" in l or "passed" in l for l in open(run + ".log", errors="replace")):
        break
    time.sleep(5)
