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

# Under Wine / Proton (Linux, Steam Deck): the asynchronous vertex workers flashed stages black and bent their
# geometry, and the fast lwmutex garbled the characters' skinning (a player narrowed it to these two on GE-Proton
# 11-11 with an RX 9060 XT, 1.1.4). Only defaults: a value of the player's own (the extra settings, the environment)
# wins. Neither changes what the game computes, only how the work is spread over threads.
WINE_ENV = {
    "RSX_VERTEX_THREADS": "0",    # vertex fetch on the walker itself, no worker threads
    "PS3_LWM_FAST": "0",          # lwmutexes through the kernel-call path
}


def _ntdll():
    import ctypes
    return ctypes.WinDLL("ntdll")


def wine_info(nt=None):
    """{"version", "build", "host", "proton"} when this process runs under Wine (Proton is Wine; ntdll exports
    wine_get_version only there), else None. "proton": the name of Steam's compatibility tool folder
    (GE-Proton10-11, proton-cachyos-slr, ...), never the path (it holds the Linux user name). `nt`: ntdll (tests)."""
    if nt is None and os.name != "nt":
        return None
    try:
        import ctypes
        nt = nt or _ntdll()
        get = nt.wine_get_version
        get.restype = ctypes.c_char_p
        info = {"version": (get() or b"?").decode("ascii", "replace")}
    except (AttributeError, OSError, ValueError):
        return None
    try:
        build = nt.wine_get_build_id
        build.restype = ctypes.c_char_p
        info["build"] = (build() or b"").decode("ascii", "replace")
    except (AttributeError, OSError, ValueError):
        info["build"] = ""
    try:
        host = nt.wine_get_host_version
        sysname, release = ctypes.c_char_p(), ctypes.c_char_p()
        host.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p)]
        host(ctypes.byref(sysname), ctypes.byref(release))
        info["host"] = " ".join(v.decode("ascii", "replace") for v in (sysname.value, release.value) if v)
    except (AttributeError, OSError, ValueError):
        info["host"] = ""
    tools = [t for t in os.environ.get("STEAM_COMPAT_TOOL_PATHS", "").replace("\\", "/").split(":") if t.strip()]
    names = [os.path.basename(t.rstrip("/")) for t in tools]
    info["proton"] = next((n for n in names if "proton" in n.lower()), names[0] if names else "")
    return info


_WINE = []


def under_wine():
    """wine_info(), asked once per process."""
    if not _WINE:
        _WINE.append(wine_info())
    return _WINE[0]


def wine_note(info, env=None):
    """One log line about Wine and the two defaults: what the game got in `env` (and which of them the player's
    own settings replaced), or without `env` the defaults alone."""
    parts = [f"Wine {info['version']}"]
    build = info.get("build") or ""
    if build and build not in (info["version"], "wine-" + info["version"]):
        parts.append(f"({build})")
    if info.get("proton"):
        parts.append(f"Proton: {info['proton']}")
    if info.get("host"):
        parts.append(f"on {info['host']}")
    if env is None:
        used = "defaults for the game: " + ", ".join(f"{k}={v}" for k, v in WINE_ENV.items())
    else:
        used = ", ".join(f"{k}={env.get(k, '(unset)')}" + ("" if env.get(k) == v else " (your own setting)")
                         for k, v in WINE_ENV.items())
    return "[wine] " + " ".join(p for p in parts if p) + f" -- {used}"


def game_command(out=ROOT, extra_env=None):
    """(argv, env, cwd) to start the game built under `out`."""
    vfs = os.path.join(out, "game", "vfs")
    exe = os.path.join(out, "build", "cmake", "t5dr.exe" if os.name == "nt" else "t5dr")
    env = dict(os.environ)
    env["PS3_VFS_ROOT"] = vfs.replace("\\", "/")
    env["PS3_HDD0_ROOT"] = os.path.join(vfs, "dev_hdd0").replace("\\", "/")
    for k, v in DEFAULT_ENV.items():
        if k == "RSX_LIVE_DRAW" and sys.platform == "darwin":
            continue    # D3D12 only; macOS draws through the Metal backend
        env.setdefault(k, v)
    if under_wine():
        for k, v in WINE_ENV.items():
            if k not in (extra_env or {}):
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
        sys.exit(f"{os.path.basename(cmd[0])} not built yet -- run tools/build_game.py")
    out = open(a.log, "w") if a.log else None
    sys.exit(subprocess.run(cmd, env=env, cwd=cwd, stdout=out, stderr=subprocess.STDOUT if out else None).returncode)


if __name__ == "__main__":
    main()
