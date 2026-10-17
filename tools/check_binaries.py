#!/usr/bin/env python3
"""Will the release's programs start on any Windows 10 (1909+) / 11 x64 PC?

    python tools/check_binaries.py --llvm DIR <release folder> [--host-map t5dr.map] [--json FILE]

Checks, with llvm-readobj / llvm-objdump from DIR\\bin:
  * imports: every DLL an .exe/.dll/.pyd imports is part of Windows 10, or ships beside it
    (the bundled Python's vcruntime140.dll, tcl86t.dll, ...). runtime\\t5dr.exe has the
    static C runtime (no VCRUNTIME140/MSVCP140) and loads mfplat.dll only on first use
    (Windows "N" editions have no Media Foundation).
  * runtime\\t5dr.exe's manifest: UTF-8 code page, long paths, per-monitor DPI awareness.
  * instruction sets (with --host-map, the linker map of that t5dr.exe): nothing beyond
    SSE4.1 outside the Microsoft C/C++ library, whose AVX/FMA/SSE4.2 paths run only after
    its own CPUID check. (`tzcnt` is clang's `rep bsf`, the same as `bsf` on older CPUs.)

package_release.py runs it on every release; docs/TROUBLESHOOTING.md "Windows versions and
other PCs" says what it means for players. Exit code 1 when something is wrong.
"""
import argparse
import bisect
import collections
import json
import os
import re
import subprocess
import sys

# DLLs every Windows 10 1909+ / 11 x64 has (lower case). api-ms-win-* sets are checked by prefix.
WINDOWS_DLLS = {
    "kernel32.dll", "user32.dll", "gdi32.dll", "advapi32.dll", "ole32.dll", "oleaut32.dll", "shell32.dll",
    "shlwapi.dll", "version.dll", "ntdll.dll", "ws2_32.dll", "winmm.dll", "bcrypt.dll", "crypt32.dll",
    "secur32.dll", "rpcrt4.dll", "iphlpapi.dll", "netapi32.dll", "userenv.dll", "propsys.dll", "imm32.dll",
    "comctl32.dll", "comdlg32.dll", "cabinet.dll", "msi.dll", "setupapi.dll", "cfgmgr32.dll", "dwmapi.dll",
    "uxtheme.dll", "shcore.dll", "avrt.dll", "dbghelp.dll", "psapi.dll", "wtsapi32.dll", "winhttp.dll",
    "ucrtbase.dll", "msvcrt.dll", "d3d12.dll", "dxgi.dll", "d3d11.dll", "d3dcompiler_47.dll", "dinput8.dll",
    "xinput1_4.dll", "hid.dll", "mmdevapi.dll", "dsound.dll", "opengl32.dll", "wintrust.dll",
}
# Windows DLLs that some editions lack (N/KN: Media Foundation): only allowed delay-loaded.
OPTIONAL_DLLS = {"mfplat.dll", "mf.dll", "mfreadwrite.dll", "evr.dll"}
# The Microsoft C/C++ library objects in a /MAP (CPUID-dispatched AVX/FMA/SSE4.2 code is fine there).
MS_CRT_LIBS = ("libucrt", "libvcruntime", "libcpmt", "libcmt", "libconcrt", "ucrt", "vcruntime", "msvcprt")
# Our own functions compiled for a newer instruction set and only called after a CPUID check
# (function -> the guard that dispatches to it).
DISPATCHED_FUNCS = {
    "ppu_fma_hw": "ppu_fp_cpu_fma() in runtime/ppu/ppu_fp_det.h (patch 0032)",
}

BMI = {"andn", "bextr", "blsi", "blsmsk", "blsr", "bzhi", "mulx", "pdep", "pext", "rorx", "sarx", "shlx", "shrx"}


def isa_class(mnemonic, ops):
    """The instruction-set extension above SSE4.1 an instruction needs, or None."""
    m = mnemonic
    if "zmm" in ops or re.search(r"%k[0-7]\b", ops):
        return "avx512"
    if m.startswith(("vfmadd", "vfmsub", "vfnmadd", "vfnmsub")):
        return "fma"
    if "ymm" in ops or m in ("vzeroupper", "vzeroall") or (m.startswith("v") and "xmm" in ops):
        return "avx"
    if m in BMI or m.rstrip("lqw") in BMI:
        return "bmi"
    if m.startswith("lzcnt"):
        return "lzcnt"
    if m.startswith("movbe"):
        return "movbe"
    if m.startswith("popcnt"):
        return "popcnt"
    if m.startswith(("pcmpestr", "pcmpistr", "crc32", "pcmpgtq")):
        return "sse4.2"
    if m.startswith(("aes", "pclmul", "sha1", "sha256")):
        return "aes/sha"
    if m.startswith(("adcx", "adox", "rdrand", "rdseed")):
        return "adx/rdrand"
    return None          # tzcnt (rep bsf) and everything up to SSE4.1


def read_map(path):
    """[(address, symbol, object)] sorted, from an lld-link/link.exe /MAP file."""
    pat = re.compile(r"^\s*[0-9a-f]{4}:[0-9a-f]{8}\s+(\S+)\s+([0-9a-f]{16})\s+(.*)$")
    syms = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            m = pat.match(line)
            if m:
                syms.append((int(m.group(2), 16), m.group(1), m.group(3).strip()))
    syms.sort()
    return syms


def isa_findings(disassembly, syms):
    """{object/function: Counter(class)} for instructions beyond SSE4.1 outside the MS CRT."""
    addrs = [s[0] for s in syms]
    ins = re.compile(r"^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$")
    bad = collections.defaultdict(collections.Counter)
    for line in disassembly.splitlines():
        m = ins.match(line)
        if not m:
            continue
        cls = isa_class(m.group(2), m.group(3))
        if not cls:
            continue
        i = bisect.bisect_right(addrs, int(m.group(1), 16)) - 1
        obj = syms[i][2] if i >= 0 else "?"
        if obj.split(":")[0].lower().startswith(MS_CRT_LIBS):
            continue
        if i >= 0 and syms[i][1] in DISPATCHED_FUNCS:
            continue
        bad[f"{syms[i][1] if i >= 0 else '?'} [{obj}]"][cls] += 1
    return bad


def imports(readobj, path):
    """({dll: [functions]}, {delay-loaded dll: [functions]}) of a PE file."""
    out = subprocess.run([readobj, "--coff-imports", path], capture_output=True, text=True,
                         errors="replace").stdout
    normal, delay = collections.defaultdict(list), collections.defaultdict(list)
    cur = None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Import {"):
            cur = (normal, None)
        elif s.startswith("DelayImport {"):
            cur = (delay, None)
        elif s.startswith("Name:") and cur and cur[1] is None:
            cur = (cur[0], s.split(":", 1)[1].strip().lower())
            cur[0].setdefault(cur[1], [])
        elif s.startswith("Symbol:") and cur and cur[1]:
            cur[0][cur[1]].append(s.split(":", 1)[1].strip().split(" ")[0])
        elif s == "}":
            cur = None
    return dict(normal), dict(delay)


def import_problems(rel, normal, delay, shipped):
    """Plain sentences for imports that a clean Windows 10/11 cannot satisfy."""
    bad = []
    for dll in normal:
        if dll in WINDOWS_DLLS or dll.startswith(("api-ms-win-", "ext-ms-win-")) or dll in shipped:
            continue
        if dll in OPTIONAL_DLLS:
            bad.append(f"{rel}: {dll} is not on every Windows (N editions) -- load it delayed")
        elif dll.startswith(("vcruntime", "msvcp", "concrt")):
            bad.append(f"{rel}: needs the Visual C++ redistributable ({dll}) -- link the static C runtime")
        else:
            bad.append(f"{rel}: imports {dll}, which is neither part of Windows nor shipped beside it")
    for dll in delay:
        if not (dll in WINDOWS_DLLS or dll in OPTIONAL_DLLS or dll in shipped):
            bad.append(f"{rel}: delay-loads {dll}, which is neither part of Windows nor shipped")
    return bad


def manifest_of(path):
    """The RT_MANIFEST resource #1 of a PE file as text ('' when it has none). Windows only."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes as w
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.LoadLibraryExW.restype = w.HMODULE
    k.FindResourceW.restype = ctypes.c_void_p
    k.FindResourceW.argtypes = [w.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
    k.LoadResource.restype = ctypes.c_void_p
    k.LoadResource.argtypes = [w.HMODULE, ctypes.c_void_p]
    k.LockResource.restype = ctypes.c_void_p
    k.LockResource.argtypes = [ctypes.c_void_p]
    k.SizeofResource.argtypes = [w.HMODULE, ctypes.c_void_p]
    k.FreeLibrary.argtypes = [w.HMODULE]
    h = k.LoadLibraryExW(path, None, 0x2 | 0x20)       # LOAD_LIBRARY_AS_DATAFILE | _AS_IMAGE_RESOURCE
    if not h:
        return ""
    try:
        r = k.FindResourceW(h, ctypes.c_void_p(1), ctypes.c_void_p(24))
        if not r:
            return ""
        return ctypes.string_at(k.LockResource(k.LoadResource(h, r)), k.SizeofResource(h, r)).decode("utf-8", "replace")
    finally:
        k.FreeLibrary(h)


MANIFEST_NEEDS = {
    "UTF-8 code page (any characters in folder and user names)": ">UTF-8</activeCodePage>",
    "long paths": ">true</longPathAware>",
    "per-monitor DPI awareness": "PerMonitorV2",
}


def check_release(folder, llvm_bin, host_map=None, log=print):
    """[problem sentences], {details} for an unpacked release folder."""
    readobj = os.path.join(llvm_bin, "llvm-readobj.exe")
    objdump = os.path.join(llvm_bin, "llvm-objdump.exe")
    problems, details = [], {"imports": {}}
    if not os.path.exists(readobj):
        return [f"no llvm-readobj.exe in {llvm_bin}"], details
    py_dir = os.path.join(folder, "python")
    py_shipped = set()
    for d in (py_dir, os.path.join(py_dir, "DLLs")):
        if os.path.isdir(d):
            py_shipped |= {n.lower() for n in os.listdir(d) if n.lower().endswith(".dll")}
    for dp, dns, fns in os.walk(folder):
        dns[:] = [d for d in dns if d not in ("native", "__pycache__")]
        for fn in fns:
            if not fn.lower().endswith((".exe", ".dll", ".pyd")):
                continue
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, folder)
            normal, delay = imports(readobj, path)
            shipped = {n.lower() for n in os.listdir(dp) if n.lower().endswith(".dll")}
            if rel.lower().startswith("python" + os.sep):
                shipped |= py_shipped
            details["imports"][rel] = {"imports": sorted(normal), "delay": sorted(delay)}
            problems += import_problems(rel, normal, delay, shipped)
    host = os.path.join(folder, "runtime", "t5dr.exe")
    if os.path.exists(host):
        normal, delay = imports(readobj, host)
        if "mfplat.dll" in normal:
            problems.append(r"runtime\t5dr.exe imports mfplat.dll directly: it would not start on Windows N")
        man = manifest_of(host)
        if man is not None:
            for what, needle in MANIFEST_NEEDS.items():
                if needle not in man:
                    problems.append(rf"runtime\t5dr.exe's manifest lacks {what}")
        if host_map and os.path.exists(objdump):
            dis = subprocess.run([objdump, "-d", "--no-show-raw-insn", host], capture_output=True, text=True,
                                 errors="replace").stdout
            bad = isa_findings(dis, read_map(host_map))
            details["isa"] = {k: dict(v) for k, v in bad.items()}
            for where, c in sorted(bad.items()):
                problems.append(rf"runtime\t5dr.exe: {dict(c)} outside the C library, in {where} -- "
                                "it would crash on a CPU without these instructions")
            log(f"  instruction sets: {'nothing beyond SSE4.1 outside the C library' if not bad else len(bad)}")
    log(f"  imports: {len(details['imports'])} programs and libraries checked")
    return problems, details


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="unpacked release folder")
    ap.add_argument("--llvm", required=True, help="LLVM folder (bin/llvm-readobj.exe, bin/llvm-objdump.exe)")
    ap.add_argument("--host-map", help="the linker map of runtime/t5dr.exe (for the instruction-set check)")
    ap.add_argument("--json", help="write every import list and finding here")
    a = ap.parse_args()
    problems, details = check_release(a.folder, os.path.join(a.llvm, "bin"), a.host_map)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(details, f, indent=1)
    for p in problems:
        print("PROBLEM:", p)
    print("binaries OK" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
