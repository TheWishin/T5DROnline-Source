#!/usr/bin/env python3
"""Read a PS3_HOST_PROF stack profile (PS3_HOST_PROF_DEPTH=N) with the build's map file.

    python tools/host_prof.py PROFILE --map build/cmake/t5dr.map [--top 30] [--tid N]
                              [--json FILE] [--focus NAME]

The runtime's sampler (boot_main.cpp, PS3_HOST_PROF=<file>) writes one line per
sample with the sampled thread's whole host stack. Start the game with

    PS3_HOST_PROF=prof.txt PS3_HOST_PROF_WHO=main PS3_HOST_PROF_DEPTH=48
    PS3_HOST_PROF_AT=30,60

to sample only the guest's main thread (the one that runs the frame) from 30 s
to 60 s after start. This script prints, as a share of all samples:

- self time per function (the leaf frame): lifted functions are func_XXXXXXXX
  (the guest address), runtime functions by their name;
- inclusive time per function (in the stack anywhere, counted once a sample);
- the samples by kind: lifted code, the runtime's helpers by group (guest
  memory, indirect calls, HLE calls, lv2 syscalls, waits in the kernel, ...),
  netplay/rollback (src/), and other modules;
- with --focus NAME: what the samples that have NAME in their stack were doing
  at their leaf (self time inside NAME's subtree).

Groups are decided from the leaf up: a sample is "waiting" when its leaf is in
ntdll/kernel32/kernelbase under a wait call, "HLE: <name>" when the innermost
runtime entry on the stack is an HLE handler, and so on (see CATS).
"""
import argparse
import bisect
import collections
import json
import re
import sys

IMAGE_BASE = 0x140000000


def load_map(path):
    """[(rva, name, obj)] sorted, from an lld-link /MAP file."""
    syms = []
    pat = re.compile(r"^\s*([0-9a-fA-F]{4}):([0-9a-fA-F]{8})\s+(\S+)\s+([0-9a-fA-F]{16})\s+(.*)$")
    for line in open(path, errors="replace"):
        m = pat.match(line)
        if not m:
            continue
        sec = int(m.group(1), 16)
        if sec != 1:        # .text only
            continue
        va = int(m.group(4), 16)
        if va < IMAGE_BASE:
            continue
        syms.append((va - IMAGE_BASE, demangle(m.group(3)), m.group(5).strip()))
    syms.sort()
    return syms


def demangle(n):
    # ?func_00165BD0@@YAXPEAUppu_context@@@Z -> func_00165BD0; ?name@ns@@... -> ns::name
    if n.startswith("?"):
        body = n[1:]
        if body.startswith("?"):
            return n
        parts = body.split("@@")[0].split("@")
        parts = [p for p in parts if p]
        if parts:
            return "::".join(reversed(parts))
    return n


def pe_exports(path):
    """{rva: name} of a DLL's exports (read from the file; system DLLs are the same image)."""
    import struct
    try:
        d = open(path, "rb").read()
    except OSError:
        return {}
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    opt = pe + 24
    exp_rva = struct.unpack_from("<I", d, opt + 112)[0]
    secs = []
    for i in range(nsec):
        o = opt + optsz + 40 * i
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, max(vsz, rsz), raw))

    def off(rva):
        for va, sz, raw in secs:
            if va <= rva < va + sz:
                return raw + rva - va
        return None
    eo = off(exp_rva)
    if eo is None:
        return {}
    nfun, nnames, af, an, ao = struct.unpack_from("<IIIII", d, eo + 20)
    out = {}
    for i in range(nnames):
        nrva = struct.unpack_from("<I", d, off(an) + 4 * i)[0]
        ordn = struct.unpack_from("<H", d, off(ao) + 2 * i)[0]
        frva = struct.unpack_from("<I", d, off(af) + 4 * ordn)[0]
        no = off(nrva)
        name = d[no:d.index(0, no)].decode("ascii", "replace")
        out.setdefault(frva, name)
    return out


class ModSym:
    def __init__(self):
        self.cache = {}

    def name(self, mod, offset):
        if mod not in self.cache:
            import os
            ex = pe_exports(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", mod))
            ks = sorted(ex)
            self.cache[mod] = (ks, [ex[k] for k in ks])
        ks, ns = self.cache[mod]
        i = bisect.bisect_right(ks, offset) - 1
        return "%s!%s" % (mod, ns[i] if i >= 0 else "?")


class Sym:
    def __init__(self, syms):
        self.syms = syms
        self.addrs = [s[0] for s in syms]

    def name(self, rva):
        i = bisect.bisect_right(self.addrs, rva) - 1
        if i < 0:
            return "?", ""
        return self.syms[i][1], self.syms[i][2]


# runtime groups by symbol (first match on the name, checked leaf -> root over runtime frames)
GROUPS = [
    ("guest memory (out-of-line vm_read/vm_write)", re.compile(r"^(vm_read|vm_write|ppu_stwcx|ppu_stdcx|vm_store_coh|ppu_resv)")),
    ("indirect calls (ps3_indirect_call)", re.compile(r"^(ps3_indirect_call|ppu_lookup|icall_hist)")),
    ("lv2 syscalls", re.compile(r"^(lv2_syscall|sys_|lv2_)")),
    ("HLE calls", re.compile(r"^(ps3_hle_call|cell|_cell|sce|ppu_hle)")),
    ("fp environment check", re.compile(r"^ppu_fp_")),
    ("timebase", re.compile(r"^ppu_timebase")),
]


def classify_frame(name, obj):
    if name.startswith("func_"):
        return "lifted"
    o = obj.lower()
    if "ppu_recomp_" in o:
        return "lifted"
    if any(k in o for k in ("rb_", "netplay", "t5_hooks", "replay", "local_pad", "df_", "training", "t5_perf")):
        return "src"
    return "runtime"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile")
    ap.add_argument("--map", required=True)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--tid", type=int, default=0, help="only this host thread id")
    ap.add_argument("--json", default="")
    ap.add_argument("--focus", default="", help="leaf profile of the samples with this function in their stack")
    ap.add_argument("--busy", action="store_true",
                    help="leave out samples blocked in a wait (leaf ntdll!NtWaitFor*/NtDelayExecution/...): "
                         "shares of the thread's busy time")
    ap.add_argument("--callers", action="store_true",
                    help="with --focus: leaf as module!export and the first frame in the game's module (symbol+offset)")
    a = ap.parse_args()

    sym = Sym(load_map(a.map))
    msym = ModSym()
    mods = {}
    samples = []
    for line in open(a.profile):
        if line.startswith("M "):
            _, k, nm = line.split(None, 2)
            mods[int(k)] = nm.strip()
        elif line.startswith("S "):
            f = line.split()
            tid, n = int(f[1]), int(f[2])
            if a.tid and tid != a.tid:
                continue
            frames = []
            for t in f[3:3 + n]:
                if t.startswith("M"):
                    k, off = t[1:].split("+")
                    frames.append(("mod", mods.get(int(k), "?"), int(off, 16)))
                else:
                    r = int(t, 16)
                    nm, obj = sym.name(r)
                    frames.append(("sym", nm, obj, r))
            samples.append(frames)
    if a.busy:
        def blocked(fr):
            x = fr[0]
            if x[0] != "mod":
                return False
            nm = msym.name(x[1], x[2])
            return any(w in nm for w in ("NtWaitFor", "NtDelayExecution", "NtRemoveIoCompletion",
                                         "NtWaitForMultipleObjects", "ZwWaitFor", "NtSignalAndWaitForSingleObject"))
        nall = len(samples)
        samples = [fr for fr in samples if not blocked(fr)]
        print("busy samples: %d of %d (%.1f%%)" % (len(samples), nall, 100.0 * len(samples) / max(1, nall)))
    N = len(samples)
    if not N:
        sys.exit("no samples")
    self_c = collections.Counter()
    incl_c = collections.Counter()
    kind_c = collections.Counter()
    focus_c = collections.Counter()
    focus_n = 0
    for fr in samples:
        leaf = fr[0]
        self_c[leaf[1] if leaf[0] == "sym" else "[%s]" % leaf[1]] += 1
        seen = set()
        for x in fr:
            nm = x[1] if x[0] == "sym" else "[%s]" % x[1]
            if nm not in seen:
                seen.add(nm)
                incl_c[nm] += 1
        # kind: walk from the leaf; foreign modules first, then the first module frame decides
        kind = None
        foreign = None
        for x in fr:
            if x[0] == "mod":
                if foreign is None:
                    foreign = x[1]
                continue
            nm, obj = x[1], x[2]
            c = classify_frame(nm, obj)
            if c == "lifted":
                kind = "in the kernel/system (%s) from lifted code" % foreign if foreign else "lifted code (self)"
                break
            if c == "src":
                kind = "netplay/rollback (src/)" + (" in %s" % foreign if foreign else "")
                break
            g = None
            for gname, pat in GROUPS:
                if pat.match(nm):
                    g = gname
                    break
            if g:
                kind = g + (" -> waiting/system (%s)" % foreign if foreign else "")
                break
        if kind is None:
            # only runtime frames without a group: name the innermost runtime frame's function
            for x in fr:
                if x[0] == "sym":
                    kind = "runtime: %s%s" % (x[1], " -> %s" % foreign if foreign else "")
                    break
            else:
                kind = "only system frames (%s)" % foreign
        kind_c[kind] += 1
        if a.focus:
            names = [x[1] for x in fr if x[0] == "sym"]
            if any(a.focus in nm for nm in names):
                focus_n += 1
                if a.callers:
                    lf = leaf[1] if leaf[0] == "sym" else msym.name(leaf[1], leaf[2])
                    own = next((x for x in fr if x[0] == "sym"), None)
                    if own:
                        base = sym.addrs[bisect.bisect_right(sym.addrs, own[3]) - 1]
                        lf += "  <-  %s+0x%X" % (own[1], own[3] - base)
                    focus_c[lf] += 1
                else:
                    focus_c[leaf[1] if leaf[0] == "sym" else "[%s]" % leaf[1]] += 1

    def pr(title, c, n):
        print("\n%s (%d samples)" % (title, N))
        for nm, k in c.most_common(n):
            print("  %6.2f%%  %6d  %s" % (100.0 * k / N, k, nm))

    print("samples: %d" % N)
    pr("by kind", kind_c, 40)
    pr("self (leaf function)", self_c, a.top)
    pr("inclusive", incl_c, a.top * 2)
    lifted_self = [(nm, k) for nm, k in self_c.most_common() if nm.startswith("func_")]
    print("\nlifted functions, self (top %d)" % a.top)
    for nm, k in lifted_self[:a.top]:
        print("  %6.2f%%  %6d  %s" % (100.0 * k / N, k, nm))
    if a.focus:
        print("\nfocus %s: %d samples (%.2f%%), leaves:" % (a.focus, focus_n, 100.0 * focus_n / N))
        for nm, k in focus_c.most_common(a.top):
            print("  %6.2f%%  %6d  %s" % (100.0 * k / N, k, nm))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"samples": N, "kind": kind_c.most_common(), "self": self_c.most_common(200),
                       "inclusive": incl_c.most_common(400)}, f, indent=1)


if __name__ == "__main__":
    main()
