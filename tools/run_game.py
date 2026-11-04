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


# A Wine builtin DLL carries this text right after its DOS header (winebuild writes it; Wine's loader reads it).
WINE_BUILTIN = b"Wine builtin DLL"
# The two DLLs the game's picture depends on under Wine (docs/LINUX_STEAM_DECK.md): Direct3D 12 (Proton: vkd3d-proton,
# a DLL of its own; plain Wine: Wine's own vkd3d, which lacks much of what the game uses) and the HLSL compiler the
# game compiles every shader with (Wine's own, from vkd3d-shader, unless Microsoft's was installed with
# winetricks/protontricks d3dcompiler_47). GitHub #26's dark blue window = the game's Direct3D 12 renderer did not start.
WINE_DLLS = ("d3d12.dll", "d3dcompiler_47.dll")


def dll_origin(name, k32=None):
    """Where this Wine prefix takes `name` from: "wine" (Wine's own builtin), "native" (a DLL of its own:
    vkd3d-proton's d3d12, Microsoft's compiler), "" (not there). Mapped without running any of it
    (DONT_RESOLVE_DLL_REFERENCES) and freed again. Only asked under Wine. `k32`: kernel32 (tests)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = k32 or ctypes.WinDLL("kernel32")
        load, free = k32.LoadLibraryExW, k32.FreeLibrary
        load.restype = ctypes.c_void_p
        load.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
        free.argtypes = [ctypes.c_void_p]
        h = load(name, None, 0x00000001)
        if not h:
            return ""
        try:
            return "wine" if ctypes.string_at(h + 0x40, len(WINE_BUILTIN)) == WINE_BUILTIN else "native"
        finally:
            free(h)
    except (AttributeError, OSError, ValueError):
        return ""


def wine_info(nt=None, k32=None):
    """{"version", "build", "host", "proton", "dlls"} when this process runs under Wine (Proton is Wine; ntdll
    exports wine_get_version only there), else None. "proton": the name of Steam's compatibility tool folder
    (GE-Proton10-11, proton-cachyos-slr, ...), never the path (it holds the Linux user name). "dlls": {name:
    dll_origin} for WINE_DLLS (the launcher shares the game's prefix and DLL overrides, so it sees what the game
    will load). `nt`: ntdll, `k32`: kernel32 (tests; a stand-in ntdll without k32 asks no DLLs)."""
    if nt is None and os.name != "nt":
        return None
    probe = nt is None or k32 is not None
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
    if probe:
        info["dlls"] = {n: dll_origin(n, k32) for n in WINE_DLLS}
    return info


def dll_note(dlls):
    """'d3d12: vkd3d-proton, d3dcompiler_47: Wine's own' for the [wine] line ('' without dlls)."""
    words = {"d3d12.dll": {"native": "vkd3d-proton (native)", "wine": "Wine's own (vkd3d)", "": "missing"},
             "d3dcompiler_47.dll": {"native": "Microsoft's (native)", "wine": "Wine's own", "": "missing"}}
    return ", ".join(f"{n[:-4]}: {words[n].get(dlls[n], dlls[n])}" for n in WINE_DLLS if n in (dlls or {}))


def wine_home(env=None):
    """The Linux home folder as a Windows path ("Z:\\home\\deck") when this process runs under Wine, else None.
    Wine puts WINEHOMEDIR ("\\??\\Z:\\home\\deck") into every process's environment. Under Proton the prefix's own
    Desktop/Downloads (C:\\users\\steamuser\\...) are folders deep inside steamapps/compatdata that no player finds:
    the real ones are under this home."""
    v = (os.environ if env is None else env).get("WINEHOMEDIR", "")
    if v.startswith("\\??\\"):
        v = v[4:]
    return v if v and os.path.isdir(v) else None


XDG_DEFAULTS = {"DESKTOP": "Desktop", "DOWNLOAD": "Downloads", "DOCUMENTS": "Documents"}


def wine_user_dirs(home):
    """{"DESKTOP": path, "DOWNLOAD": path, "DOCUMENTS": path} under the Linux `home` (a Windows path): the
    folders ~/.config/user-dirs.dirs names (localized ones such as ~/Schreibtisch, as Wine maps them), else
    ~/Desktop, ~/Downloads, ~/Documents. Only folders that exist."""
    named = {}
    try:
        with open(os.path.join(home, ".config", "user-dirs.dirs"), encoding="utf-8", errors="replace") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                key = key.strip()
                if key.startswith("XDG_") and key.endswith("_DIR") and key[4:-4] in XDG_DEFAULTS:
                    value = value.strip().strip('"')
                    if value.startswith("$HOME/"):
                        named[key[4:-4]] = os.path.join(home, *value[6:].split("/"))
    except OSError:
        pass
    out = {}
    for key, default in XDG_DEFAULTS.items():
        for p in (named.get(key), os.path.join(home, default)):
            if p and os.path.isdir(p):
                out[key] = p
                break
    return out


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
    dlls = dll_note(info.get("dlls"))
    return "[wine] " + " ".join(p for p in parts if p) + f" -- {used}" + (f" -- {dlls}" if dlls else "")


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
        if os.name == "nt":
            # Windows ignores the case of names: drop every spelling of k first (a lower-case extra name next to
            # the inherited upper-case one would reach the game twice, and None must remove both)
            for old in [o for o in env if o.upper() == k.upper()]:
                del env[old]
            k = k.upper()
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
