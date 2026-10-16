#!/usr/bin/env python3
"""Start the built game: python tools/run_game.py [--out DIR] [--log FILE] [extra env NAME=VALUE ...]

Sets up the runtime's file system mapping (see build_game.py step_vfs) and
starts <out>/build/cmake/t5dr.exe with <out> as the working directory (the
runtime keeps saves in ./gamedata and its shader cache in ./scratch there).
The launcher uses game_command() directly.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Defaults every player wants; the launcher's settings and NAME=VALUE arguments
# override them.
DEFAULT_ENV = {
    "PS3_TITLE": "Tekken 5: Dark Resurrection Online",
    "PS3_GCM_TICKER_PUMP": "1",   # GCM handlers on the ticker thread (see patches)
    "RSX_LIVE_DRAW": "1",         # the NV4097 -> D3D12 draw engine; the default backend shows black
    "PS3_VERBOSE": "0",           # per-wait logging costs whole frames and starves the sound core
}


def game_command(out=ROOT, extra_env=None):
    """(argv, env, cwd) to start the game built under `out`."""
    vfs = os.path.join(out, "game", "vfs")
    exe = os.path.join(out, "build", "cmake", "t5dr.exe")
    env = dict(os.environ)
    env["PS3_VFS_ROOT"] = vfs.replace("\\", "/")
    env["PS3_HDD0_ROOT"] = os.path.join(vfs, "dev_hdd0").replace("\\", "/")
    for k, v in DEFAULT_ENV.items():
        env.setdefault(k, v)
    for k, v in (extra_env or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)
    return [exe, os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")], env, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=ROOT, help="the build's output root (build_game.py --out)")
    ap.add_argument("--log", help="write the game's output to this file")
    ap.add_argument("env", nargs="*", help="extra environment, NAME=VALUE")
    a = ap.parse_args()

    cmd, env, cwd = game_command(os.path.abspath(a.out), dict(kv.split("=", 1) for kv in a.env))
    if not os.path.exists(cmd[0]):
        sys.exit("t5dr.exe not built yet -- run tools/build_game.py")
    out = open(a.log, "w") if a.log else None
    sys.exit(subprocess.run(cmd, env=env, cwd=cwd, stdout=out, stderr=subprocess.STDOUT if out else None).returncode)


if __name__ == "__main__":
    main()
