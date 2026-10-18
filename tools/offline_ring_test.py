"""Offline fight on a few CPUs (rematch-fix, patch 0035): does the GCM ring's drain-thread recycle fire (old build) or not (0035)?

    python tools/offline_ring_test.py EXE OUTDIR [seconds] [cpus]

One game, direct fight (T5_FIGHT), no netplay, muted (PS3_AUDIO_MUTE=1, the mix still goes to
AUDIO_WAV), minimized, below-normal priority, affinity to the first `cpus` logical processors and
PS3_CPUS=cpus. Prints the FIFO lines, fps and an audio summary of the fight (silent 10 ms blocks)."""
import ctypes
import os
import re
import struct
import subprocess
import sys
import time

exe, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 110
cpus = int(sys.argv[4]) if len(sys.argv) > 4 else 6
os.makedirs(out, exist_ok=True)
vfs = os.environ.get("T5_VFS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "game", "vfs")).replace("\\", "/")
wav = os.path.join(out, "mix.f32")
env = dict(os.environ)
env.update({"PS3_VFS_ROOT": vfs, "PS3_HDD0_ROOT": vfs + "/dev_hdd0", "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1",
            "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1", "PAD_NO_KEYBOARD": "1", "PS3_AUDIO_MUTE": "1",
            "AUDIO_WAV": wav, "PS3_CPUS": str(cpus), "T5_FIGHT": "kaz,hei,20,3",
            "T5_DF_STATUS_FILE": os.path.join(out, "status.json"), "T5_DF_WATCH": "40500000"})
for p in (wav,):
    try:
        os.remove(p)
    except OSError:
        pass
log = open(os.path.join(out, "game.log"), "w")
BELOW_NORMAL = 0x00004000
proc = subprocess.Popen([exe, vfs + "/PS3_GAME/USRDIR/EBOOT.elf"], cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=BELOW_NORMAL)
k32 = ctypes.WinDLL("kernel32")
h = k32.OpenProcess(0x0200 | 0x0400, False, proc.pid)      # PROCESS_SET_INFORMATION | QUERY
k32.SetProcessAffinityMask(h, ctypes.c_size_t((1 << cpus) - 1))
k32.CloseHandle(h)
t0 = time.time()
t_fight = None
while time.time() - t0 < secs and proc.poll() is None:
    time.sleep(1)
    if t_fight is None:
        try:
            if '"fight"' in open(os.path.join(out, "status.json")).read():
                t_fight = time.time() - t0
        except OSError:
            pass
proc.kill()
proc.wait(10)
log.close()
text = open(os.path.join(out, "game.log"), errors="replace").read()
print(f"{os.path.basename(out)}: fight from {t_fight and round(t_fight, 1)} s of {secs:.0f} s")
for name, rx in (("recycled", r"recycled the title's own ring"), ("flip_stall", r"queued flip never reached"),
                 ("resync", r"FIFO resync|FIFO walker circling"), ("unmapped", r"unmapped IO"), ("heap header 0x40500000 overwritten", r"\[0x40500000\] 0x405000C0 -> ")):
    print(f"  {name}: {len(re.findall(rx, text))}")
fps = [float(m) for m in re.findall(r"^\[fps\] ([\d.]+)", text, re.M)]
print(f"  fps lines: {fps}")
try:
    data = open(wav, "rb").read()
    n = len(data) // 8                       # f32 stereo frames
    blk = 480                                # 10 ms at 48 kHz
    silent = loud = 0
    # the fight's part of the capture: from t_fight on (the mix starts at boot, 48000 frames a second)
    start = int((t_fight or 0) * 48000) if t_fight else 0
    for b in range(start // blk, n // blk):
        s = struct.unpack_from(f"<{blk * 2}f", data, b * blk * 8)
        if max(abs(x) for x in s) < 1e-6:
            silent += 1
        else:
            loud += 1
    print(f"  audio (fight part): {loud + silent} blocks of 10 ms, {silent} silent ({100.0 * silent / max(1, loud + silent):.2f} %)")
except OSError as e:
    print(f"  audio: no capture ({e})")
