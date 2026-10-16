#!/usr/bin/env python3
"""Start the built game: python tools/run_game.py [--log FILE] [extra env NAME=VALUE ...]

Sets up the runtime's file system mapping (see build_game.py step_vfs) and
starts build/cmake/t5dr.exe from the repository root.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "build", "cmake", "t5dr.exe")
VFS = os.path.join(ROOT, "game", "vfs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="write the game's output to this file")
    ap.add_argument("env", nargs="*", help="extra environment, NAME=VALUE")
    a = ap.parse_args()

    env = dict(os.environ)
    env["PS3_VFS_ROOT"] = VFS.replace("\\", "/")
    env["PS3_HDD0_ROOT"] = os.path.join(VFS, "dev_hdd0").replace("\\", "/")
    env.setdefault("PS3_TITLE", "Tekken 5: Dark Resurrection Online")
    env.setdefault("PS3_GCM_TICKER_PUMP", "1")   # GCM handlers on the ticker thread (see patches)
    env.setdefault("RSX_LIVE_DRAW", "1")         # the NV4097 -> D3D12 draw engine; the default backend shows black
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v

    if not os.path.exists(EXE):
        sys.exit("t5dr.exe not built yet -- run tools/build_game.py")
    out = open(a.log, "w") if a.log else None
    cmd = [EXE, os.path.join(VFS, "PS3_GAME", "USRDIR", "EBOOT.elf")]
    sys.exit(subprocess.run(cmd, env=env, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT if out else None).returncode)


if __name__ == "__main__":
    main()
