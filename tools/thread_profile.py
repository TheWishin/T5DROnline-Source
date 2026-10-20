#!/usr/bin/env python3
"""Sampling profiler for one thread of a running game (no admin, no ETW).

    python tools/thread_profile.py --pid PID [--thread ticker] [--secs 10]
                                   [--rate 2000] [--map build/cmake/t5dr.map]
                                   [--top 40] [--json FILE]

Suspends the named thread of the game (default: `ticker`, which walks the RSX
command stream and records the D3D12 command lists) about --rate times a
second, reads its instruction pointer and the top of its stack, resumes it,
and maps the addresses to functions with the linker map that sits next to
the executable (lld-link /MAP lists static functions too), and system DLL
addresses to their nearest export. Samples taken while the thread waits in
the kernel (right after the `syscall` of NtWait*, NtDelayExecution,
NtWaitForAlertByThreadId ...) are left out, so the table is where the
thread's CPU time went.

Self time is per function (inlined code counts for the function it was
inlined into). Samples in a DLL (D3D12, the display driver, the C runtime)
are charged to the DLL and, for the inclusive table, to the functions of the
executable found on the stack: return addresses that follow a call
instruction, nearest first -- a heuristic (a stale return address left on
the stack can show up), good enough to see which of our functions spend the
time in the driver.

Run it next to tools/fight_bench.py (--pid of the game it started).
"""
import argparse
import bisect
import collections
import ctypes
import json
import os
import re
import sys
import time
from ctypes import wintypes as W

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi")
ntdll = ctypes.WinDLL("ntdll")

k32.OpenThread.restype = W.HANDLE
k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenProcess.restype = W.HANDLE
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.SuspendThread.argtypes = [W.HANDLE]
k32.ResumeThread.argtypes = [W.HANDLE]
k32.GetThreadContext.argtypes = [W.HANDLE, ctypes.c_void_p]
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.CloseHandle.argtypes = [W.HANDLE]
k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.GetThreadDescription.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
k32.LocalFree.argtypes = [ctypes.c_void_p]
k32.QueryThreadCycleTime.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]
psapi.EnumProcessModules.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)]
psapi.GetModuleBaseNameW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
psapi.GetModuleInformation.argtypes = [W.HANDLE, W.HMODULE, ctypes.c_void_p, W.DWORD]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG),
                ("dwFlags", W.DWORD)]


class MODINFO(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("size", W.DWORD), ("entry", ctypes.c_void_p)]


# x64 CONTEXT: 1232 bytes, 16-byte aligned; ContextFlags at 0x30, Rsp 0x98, Rip 0xF8
CTX_SIZE = 1232
CONTEXT_CONTROL = 0x100001


def threads_of(pid):
    out = []
    snap = k32.CreateToolhelp32Snapshot(0x4, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def thread_name(tid):
    h = k32.OpenThread(0x0800, False, tid)       # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    name = ctypes.c_wchar_p()
    nm = ""
    if k32.GetThreadDescription(h, ctypes.byref(name)) >= 0 and name.value is not None:
        nm = name.value
        k32.LocalFree(ctypes.cast(name, ctypes.c_void_p))
    k32.CloseHandle(h)
    return nm


def modules(hp):
    out = []
    arr = (W.HMODULE * 1024)()
    need = W.DWORD()
    if psapi.EnumProcessModules(hp, arr, ctypes.sizeof(arr), ctypes.byref(need)):
        for i in range(min(1024, need.value // ctypes.sizeof(W.HMODULE))):
            nm = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(hp, W.HMODULE(arr[i]), nm, 260)
            mi = MODINFO()
            if psapi.GetModuleInformation(hp, W.HMODULE(arr[i]), ctypes.byref(mi), ctypes.sizeof(mi)):
                out.append((mi.base or 0, mi.size, nm.value))
    out.sort()
    return out


def load_map(path):
    """[(rva, name)] sorted, from an lld-link /MAP file (publics and statics)."""
    syms = []
    pref = 0x140000000
    rx = re.compile(r"^\s*0001:[0-9a-f]+\s+(\S+)\s+([0-9a-f]{16})\s")
    with open(path, errors="replace") as f:
        for ln in f:
            if "Preferred load address is" in ln:
                pref = int(ln.split()[-1], 16)
            m = rx.match(ln)
            if m:
                syms.append((int(m.group(2), 16) - pref, m.group(1)))
    syms.sort()
    return syms


def read(hp, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(hp, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return b""
    return buf.raw[:got.value]


def exports(hp, base):
    """[(rva, name)] sorted: the module's exported functions (for names inside system DLLs)."""
    hdr = read(hp, base, 0x400)
    if len(hdr) < 0x40 or hdr[:2] != b"MZ":
        return []
    pe = int.from_bytes(hdr[0x3C:0x40], "little")
    hdr = read(hp, base + pe, 0x108)
    if len(hdr) < 0x108 or hdr[:4] != b"PE\0\0":
        return []
    rva = int.from_bytes(hdr[24 + 112:24 + 116], "little")
    if not rva:
        return []
    d = read(hp, base + rva, 40)
    if len(d) < 40:
        return []
    n_names = int.from_bytes(d[0x18:0x1C], "little")
    a_funcs = int.from_bytes(d[0x1C:0x20], "little")
    a_names = int.from_bytes(d[0x20:0x24], "little")
    a_ords = int.from_bytes(d[0x24:0x28], "little")
    names = read(hp, base + a_names, 4 * n_names)
    ords = read(hp, base + a_ords, 2 * n_names)
    out = []
    for i in range(n_names):
        nrva = int.from_bytes(names[4 * i:4 * i + 4], "little")
        o = int.from_bytes(ords[2 * i:2 * i + 2], "little")
        f = int.from_bytes(read(hp, base + a_funcs + 4 * o, 4), "little")
        nm = read(hp, base + nrva, 96).split(b"\0")[0].decode("ascii", "replace")
        out.append((f, nm))
    out.sort()
    return out


# syscalls a thread waits in: samples there are idle time, not CPU time
WAITS = ("NtWait", "ZwWait", "NtDelayExecution", "ZwDelayExecution", "NtWaitForAlertByThreadId",
         "NtRemoveIoCompletion", "NtSignalAndWait", "NtUserMsgWaitForMultipleObjectsEx",
         "NtUserWaitMessage", "NtGdiDdDDIWaitForSynchronizationObject", "NtYieldExecution")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--thread", default="ticker", help="thread name (GetThreadDescription)")
    ap.add_argument("--secs", type=float, default=10.0)
    ap.add_argument("--rate", type=float, default=2000.0, help="samples a second (busy-waits between them)")
    ap.add_argument("--map", default="", help="linker map (default: <exe>.map next to the game)")
    ap.add_argument("--stack", type=int, default=2048, help="stack bytes scanned for callers")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--json", default="")
    ap.add_argument("--raw", default="", help="also write every busy sample: leaf, then callers; executable "
                    "addresses as RVAs (hex), for line-level symbolizing with a PDB (llvm-symbolizer)")
    a = ap.parse_args()

    hp = k32.OpenProcess(0x0410, False, a.pid)     # QUERY_INFORMATION | VM_READ
    if not hp:
        sys.exit("cannot open process %d" % a.pid)
    mods = modules(hp)
    exe = None
    for base, size, nm in mods:
        if nm.lower().endswith(".exe"):
            exe = (base, size, nm)
    if not exe:
        sys.exit("no exe module")
    if not a.map:
        buf = ctypes.create_unicode_buffer(1024)
        psapi.GetModuleFileNameExW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
        psapi.GetModuleFileNameExW(hp, None, buf, 1024)
        a.map = os.path.splitext(buf.value)[0] + ".map"
    syms = load_map(a.map)
    rvas = [s[0] for s in syms]
    ebase, esize = exe[0], exe[1]
    # the executable's code, for the call-site check of return addresses
    code = read(hp, ebase, esize)
    mbases = [m[0] for m in mods]

    exp_cache = {}
    sys_dlls = ("ntdll.dll", "win32u.dll", "kernelbase.dll", "kernel32.dll", "ucrtbase.dll",
                "vcruntime140.dll", "d3d12core.dll", "d3d12.dll", "dxgi.dll", "user32.dll")

    def sym(addr):
        if ebase <= addr < ebase + esize:
            i = bisect.bisect_right(rvas, addr - ebase) - 1
            return syms[i][1] if i >= 0 else "?"
        i = bisect.bisect_right(mbases, addr) - 1
        if i >= 0 and addr < mods[i][0] + mods[i][1]:
            base, _, nm = mods[i]
            if nm.lower() in sys_dlls:
                ex = exp_cache.get(base)
                if ex is None:
                    ex = exp_cache[base] = (exports(hp, base),)
                ex = ex[0]
                j = bisect.bisect_right([e[0] for e in ex], addr - base) - 1 if ex else -1
                if j >= 0:
                    return "[%s]%s" % (nm, ex[j][1])
            return "[%s]" % nm
        return "[?]"

    insys_cache = {}

    def in_syscall(addr):
        """the thread sits right after a `syscall` instruction (in the kernel)"""
        v = insys_cache.get(addr)
        if v is None:
            b = read(hp, addr - 2, 2)
            v = insys_cache[addr] = (b == b"\x0f\x05")
        return v

    def is_ret(addr):
        """addr is in the exe and follows a call instruction"""
        o = addr - ebase
        if o < 8 or o >= len(code):
            return False
        b = code[o - 7:o]
        if b[2] == 0xE8:                              # call rel32
            return True
        if b[1] == 0xFF and (b[2] >> 3) & 7 == 2:     # call [rip+d32] / [r+d32] (6 bytes)
            return True
        if b[4] == 0xFF and (b[5] >> 3) & 7 == 2 and (b[5] >> 6) == 1:   # call [r+d8]
            return True
        if b[5] == 0xFF and (b[6] >> 3) & 7 == 2 and (b[6] >> 6) == 3:   # call r
            return True
        if b[4] == 0xFF and (b[5] >> 3) & 7 == 2 and (b[5] >> 6) == 0:   # call [r] with sib/rex
            return True
        return False

    tid = None
    for t in threads_of(a.pid):
        if thread_name(t) == a.thread:
            tid = t
            break
    if tid is None:
        sys.exit("no thread named %r" % a.thread)
    ht = k32.OpenThread(0x0002 | 0x0008 | 0x0040 | 0x0200, False, tid)
    if not ht:
        sys.exit("cannot open thread %d" % tid)
    raw = ctypes.create_string_buffer(CTX_SIZE + 16)
    off = (16 - ctypes.addressof(raw) % 16) % 16
    ctxp = ctypes.addressof(raw) + off

    self_c = collections.Counter()
    incl_c = collections.Counter()
    edge_c = collections.Counter()        # (caller, callee-or-dll)
    n_busy = n_idle = 0
    raw_out = open(a.raw, "w") if a.raw else None
    period = 1.0 / a.rate
    t_end = time.perf_counter() + a.secs
    nxt = time.perf_counter()
    stk = ctypes.create_string_buffer(a.stack)
    got = ctypes.c_size_t()
    while True:
        now = time.perf_counter()
        if now >= t_end:
            break
        if now < nxt:
            continue
        nxt += period
        if k32.SuspendThread(ht) == 0xFFFFFFFF:
            break
        ctypes.c_uint32.from_address(ctxp + 0x30).value = CONTEXT_CONTROL | 0x2   # + INTEGER
        okc = k32.GetThreadContext(ht, ctypes.c_void_p(ctxp))
        rip = ctypes.c_uint64.from_address(ctxp + 0xF8).value
        rsp = ctypes.c_uint64.from_address(ctxp + 0x98).value
        oks = okc and k32.ReadProcessMemory(hp, ctypes.c_void_p(rsp), stk, a.stack, ctypes.byref(got))
        k32.ResumeThread(ht)
        if not okc:
            continue
        leaf = sym(rip)
        if in_syscall(rip) and leaf.split("]")[-1].startswith(WAITS):
            n_idle += 1
            continue
        n_busy += 1
        self_c[leaf] += 1
        chain = [leaf]
        rchain = ["%x" % (rip - ebase) if ebase <= rip < ebase + esize else leaf.replace(" ", "_")]
        if oks:
            data = stk.raw[:got.value]
            for i in range(0, len(data) - 7, 8):
                v = int.from_bytes(data[i:i + 8], "little")
                if ebase <= v < ebase + esize and is_ret(v):
                    f = sym(v)
                    if len(rchain) < 16:
                        rchain.append("%x" % (v - ebase))
                    if f != chain[-1]:
                        chain.append(f)
                    if len(chain) >= 12:
                        break
        if raw_out:
            raw_out.write(" ".join(rchain) + "\n")
        for f in set(chain):
            incl_c[f] += 1
        if len(chain) > 1:
            edge_c[(chain[1], chain[0])] += 1
    k32.CloseHandle(ht)
    k32.CloseHandle(hp)
    if raw_out:
        raw_out.close()

    tot = max(1, n_busy)
    print("thread %s (tid %d): %d busy samples, %d idle, %.0f s at %.0f/s" % (
        a.thread, tid, n_busy, n_idle, a.secs, a.rate))
    print("\nself time (top %d):" % a.top)
    for f, n in self_c.most_common(a.top):
        print("  %5.1f%%  %s" % (100.0 * n / tot, f))
    print("\ninclusive (heuristic stack scan, top %d):" % a.top)
    for f, n in incl_c.most_common(a.top):
        print("  %5.1f%%  %s" % (100.0 * n / tot, f))
    print("\ncaller -> callee (top %d):" % a.top)
    for (c, f), n in edge_c.most_common(a.top):
        print("  %5.1f%%  %s -> %s" % (100.0 * n / tot, c, f))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"busy": n_busy, "idle": n_idle, "self": self_c.most_common(),
                       "incl": incl_c.most_common(),
                       "edges": [[c, f, n] for (c, f), n in edge_c.most_common()]}, fh, indent=1)


if __name__ == "__main__":
    main()
