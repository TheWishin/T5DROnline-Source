#!/usr/bin/env python3
"""Sampling profiler for the game's host threads (Windows, no admin rights).

    python tools/thread_sampler.py --pid PID --exe PATH_TO_THAT_EXE
                                   [--threads spu,spurs] [--secs 10] [--hz 2000]
                                   [--top 40] [--json FILE]

Every 1/hz s it suspends each matching thread of the process for a moment,
reads its instruction pointer and resumes it (SuspendThread/GetThreadContext,
the poor man's profiler). Threads are picked by their description (the names
host_sched gives them: "spu" = the SPU sound core, "spurs-job" / "spurs-chain"
= the SPURS job workers and walker, "main", "ticker", ...; a comma list of
substrings, case-insensitive).

The samples are resolved with llvm-symbolizer against the exe's PDB, inlined
frames included, so an exe built with line tables (clang-cl /Z7
-gline-tables-only, lld-link /DEBUG) shows which inlined helper -- e.g. which
spu_helpers.h function inside a lifted SPU function -- the time went to. Per
thread it prints the innermost function, the outermost (the lifted function or
runtime routine that inlined it), and the hottest source lines. Samples outside
the exe are counted per module (ntdll/kernelbase = waiting or in the kernel).

Only reads the target: nothing is written into it. A thread is held suspended
for a few microseconds per sample; at 2000 Hz over a handful of threads that
costs the game well under 1 % of a processor.
"""
import argparse
import collections
import ctypes
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from ctypes import wintypes as W

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
TH32CS_SNAPTHREAD, TH32CS_SNAPMODULE, TH32CS_SNAPMODULE32 = 0x4, 0x8, 0x10
THREAD_SUSPEND_RESUME, THREAD_GET_CONTEXT, THREAD_QUERY_LIMITED_INFORMATION = 0x2, 0x8, 0x800
CONTEXT_AMD64, CONTEXT_CONTROL = 0x100000, 0x100001


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG),
                ("dwFlags", W.DWORD)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD),
                ("GlblcntUsage", W.DWORD), ("ProccntUsage", W.DWORD), ("modBaseAddr", ctypes.c_void_p),
                ("modBaseSize", W.DWORD), ("hModule", W.HMODULE), ("szModule", ctypes.c_wchar * 256),
                ("szExePath", ctypes.c_wchar * 260)]


k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
k32.Thread32First.argtypes = [W.HANDLE, ctypes.POINTER(THREADENTRY32)]
k32.Thread32Next.argtypes = [W.HANDLE, ctypes.POINTER(THREADENTRY32)]
k32.Module32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
k32.Module32NextW.argtypes = [W.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
k32.OpenThread.restype = W.HANDLE
k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.SuspendThread.argtypes = [W.HANDLE]
k32.SuspendThread.restype = W.DWORD
k32.ResumeThread.argtypes = [W.HANDLE]
k32.ResumeThread.restype = W.DWORD
k32.GetThreadContext.argtypes = [W.HANDLE, ctypes.c_void_p]
k32.GetThreadDescription.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
k32.LocalFree.argtypes = [ctypes.c_void_p]
k32.CloseHandle.argtypes = [W.HANDLE]
k32.QueryThreadCycleTime.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]


def threads_of(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def modules_of(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    me = MODULEENTRY32W()
    me.dwSize = ctypes.sizeof(me)
    out = []
    ok = k32.Module32FirstW(snap, ctypes.byref(me))
    while ok:
        out.append((me.modBaseAddr or 0, me.modBaseSize, me.szModule, me.szExePath))
        ok = k32.Module32NextW(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    return sorted(out)


def pid_of_exe(exe):
    """The first process whose image is exactly this file."""
    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
                    ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    k32.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(PE32)]
    k32.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(PE32)]
    k32.OpenProcess.restype = W.HANDLE
    k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, ctypes.c_wchar_p, ctypes.POINTER(W.DWORD)]
    want = os.path.normcase(os.path.abspath(exe))
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(pe)
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    found = 0
    while ok and not found:
        if pe.szExeFile.lower() == os.path.basename(want).lower():
            h = k32.OpenProcess(0x1000, False, pe.th32ProcessID)
            if h:
                buf = ctypes.create_unicode_buffer(1024)
                n = W.DWORD(1024)
                if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) and                         os.path.normcase(buf.value) == want:
                    found = pe.th32ProcessID
                k32.CloseHandle(h)
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return found


def pe_image_base(path):
    with open(path, "rb") as f:
        b = f.read(4096)
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    magic = struct.unpack_from("<H", b, pe + 24)[0]
    return struct.unpack_from("<Q", b, pe + 24 + 24)[0] if magic == 0x20B else struct.unpack_from("<I", b, pe + 24 + 28)[0]


def describe(h):
    p = ctypes.c_wchar_p()
    if k32.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value is not None:
        s = p.value
        k32.LocalFree(p)
        return s
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, default=0, help="the game's process id (default: the process running --exe)")
    ap.add_argument("--exe", required=True, help="the exe the process runs (its PDB beside it)")
    ap.add_argument("--threads", default="spu,spurs", help="comma list of thread-name substrings")
    ap.add_argument("--secs", type=float, default=10.0)
    ap.add_argument("--hz", type=float, default=2000.0)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--json", default="")
    ap.add_argument("--symbolizer", default=shutil.which("llvm-symbolizer") or r"C:\Program Files\LLVM\bin\llvm-symbolizer.exe")
    a = ap.parse_args()

    if not a.pid:
        a.pid = pid_of_exe(a.exe)
        if not a.pid:
            sys.exit("no process runs %s" % a.exe)
    want = [w.strip().lower() for w in a.threads.split(",") if w.strip()]
    targets = []
    for tid in threads_of(a.pid):
        h = k32.OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_LIMITED_INFORMATION, False, tid)
        if not h:
            continue
        name = describe(h)
        if any(w in name.lower() for w in want):
            targets.append((tid, name or "?", h))
        else:
            k32.CloseHandle(h)
    if not targets:
        sys.exit("no thread matches %r" % a.threads)
    mods = modules_of(a.pid)
    exe_l = os.path.basename(a.exe).lower()
    exe_mod = [m for m in mods if m[2].lower() == exe_l]
    if not exe_mod:
        sys.exit("module %s not loaded in %d" % (exe_l, a.pid))
    exe_base, exe_size = exe_mod[0][0], exe_mod[0][1]
    pref = pe_image_base(a.exe)

    buf = ctypes.create_string_buffer(1232 + 16)
    addr = ctypes.addressof(buf)
    ctx = addr + ((16 - addr % 16) % 16)
    samples = collections.defaultdict(collections.Counter)     # name -> Counter(rip)
    cyc0 = {}
    for tid, name, h in targets:
        c = ctypes.c_ulonglong()
        k32.QueryThreadCycleTime(h, ctypes.byref(c))
        cyc0[tid] = c.value
    period = 1.0 / a.hz
    t_end = time.perf_counter() + a.secs
    nxt = time.perf_counter()
    n = 0
    while True:
        now = time.perf_counter()
        if now >= t_end:
            break
        if now < nxt:
            # busy-ish wait at this rate: time.sleep's ~1 ms granularity is too coarse
            if nxt - now > 0.0015:
                time.sleep(nxt - now - 0.001)
            continue
        nxt += period
        for tid, name, h in targets:
            if k32.SuspendThread(h) == 0xFFFFFFFF:
                continue
            ctypes.memmove(ctx + 0x30, struct.pack("<I", CONTEXT_CONTROL), 4)
            if k32.GetThreadContext(h, ctx):
                rip = struct.unpack("<Q", ctypes.string_at(ctx + 0xF8, 8))[0]
                samples[name + "#" + str(tid)][rip] += 1
            k32.ResumeThread(h)
        n += 1
    cyc = {}
    for tid, name, h in targets:
        c = ctypes.c_ulonglong()
        k32.QueryThreadCycleTime(h, ctypes.byref(c))
        cyc[tid] = c.value - cyc0[tid]
        k32.CloseHandle(h)

    # symbolize every exe address once
    addrs = sorted({r for cnt in samples.values() for r in cnt if exe_base <= r < exe_base + exe_size})
    sym = {}
    if addrs:
        inp = "\n".join("0x%x" % (r - exe_base + pref) for r in addrs) + "\n"
        p = subprocess.run([a.symbolizer, "--obj=" + a.exe, "--inlining",
                            "--output-style=LLVM"], input=inp, capture_output=True, text=True)
        blocks = p.stdout.strip("\n").split("\n\n")
        for r, blk in zip(addrs, blocks):
            lines = blk.strip("\n").split("\n")
            frames = [(lines[i], lines[i + 1] if i + 1 < len(lines) else "") for i in range(0, len(lines), 2)]
            sym[r] = frames            # innermost first: (function, file:line:col)

    def modname(r):
        for base, size, nm, _ in mods:
            if base <= r < base + size:
                return nm
        return "?"

    report = {}
    print("samples per thread at %.0f Hz for %.1f s (%d rounds)" % (a.hz, a.secs, n))
    for key in sorted(samples, key=lambda k: -sum(samples[k].values())):
        cnt = samples[key]
        tot = sum(cnt.values())
        tid = int(key.rsplit("#", 1)[1])
        inner, outer, line = collections.Counter(), collections.Counter(), collections.Counter()
        for r, c in cnt.items():
            if r in sym and sym[r]:
                fr = sym[r]
                inner[fr[0][0]] += c
                outer[fr[-1][0]] += c
                fl = fr[0][1]
                fl = re.sub(r"^.*[\\/]", "", fl)
                line[fr[0][0] + " @ " + fl.rsplit(":", 1)[0]] += c
            else:
                m = "[" + modname(r) + "]"
                inner[m] += c
                outer[m] += c
                line[m] += c
        print("\n== %s: %d samples, %.1f M cycles of CPU in the window ==" % (key, tot, cyc.get(tid, 0) / 1e6))
        for title, ctr in (("innermost function", inner), ("outermost function", outer), ("source line", line)):
            print("  -- %s" % title)
            for k, c in ctr.most_common(a.top):
                print("    %6.2f%%  %6d  %s" % (100.0 * c / tot, c, k))
        report[key] = {"samples": tot, "cycles": cyc.get(tid, 0), "inner": inner.most_common(200),
                       "outer": outer.most_common(200), "line": line.most_common(400),
                       "raw_rva": {"%x" % (r - exe_base): c for r, c in cnt.items() if exe_base <= r < exe_base + exe_size}}
    if a.json:
        with open(a.json, "w") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
