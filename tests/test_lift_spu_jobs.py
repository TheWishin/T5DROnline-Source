"""tools/lift_spu_jobs.py without the game: the job fingerprint (ps3recomp's FNV-1a-64)
against the runtime's, the job table's invariants, guest reads from a synthetic ELF, the
include rewrite, the registration block, and a loud failure when the bytes at
the job addresses are not the expected ones."""
import importlib.util
import os
import re
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from helpers import PY, ROOT, TOOLS, fake_bytes, get, load_tool, put


def make_elf(segments):
    """Big-endian ELF64 with one PT_LOAD per (vaddr, data), plus one PT_NOTE."""
    phoff, phentsize = 0x40, 0x38
    phdrs = [(1, va, data) for va, data in segments] + [(4, 0, b"note")]
    off = phoff + phentsize * len(phdrs)
    out, body = bytearray(off), b""
    out[0:6] = b"\x7fELF\x02\x02"
    struct.pack_into(">Q", out, 0x20, phoff)
    struct.pack_into(">HH", out, 0x36, phentsize, len(phdrs))
    for i, (typ, va, data) in enumerate(phdrs):
        struct.pack_into(">IIQQQQQQ", out, phoff + i * phentsize, typ, 5, off + len(body), va, va,
                         len(data), len(data), 0x10)
        body += data
    return bytes(out) + body


PS3RECOMP = os.environ.get("PS3RECOMP_DIR") or os.path.join(ROOT, "deps", "ps3recomp")

# ps3recomp's FNV-1a-64 starts from 1469598103934665603, the standard offset
# basis 14695981039346656037 with its last digit dropped (the textbook value
# does not fit a signed 64-bit literal). It is not textbook FNV, but the
# runtime fingerprints job images with exactly this (runtime/spu/
# spu_workload.c), so tools/lift_spu_jobs.py must match the runtime, not the
# textbook: a "fix" here would silently unregister every lifted job.
RUNTIME_BASIS = 1469598103934665603
FNV_PRIME = 1099511628211


class Fnv(unittest.TestCase):
    def test_runtime_variant(self):
        fnv = load_tool("lift_spu_jobs").fnv1a64
        self.assertEqual(fnv(b""), RUNTIME_BASIS)
        self.assertEqual(fnv(b"a"), ((RUNTIME_BASIS ^ 0x61) * FNV_PRIME) & (2**64 - 1))
        h = RUNTIME_BASIS
        for x in b"foobar":
            h = ((h ^ x) * FNV_PRIME) % 2**64
        self.assertEqual(fnv(b"foobar"), h)
        self.assertLess(fnv(fake_bytes("x", 4096)), 1 << 64)

    @unittest.skipUnless(os.path.isfile(os.path.join(PS3RECOMP, "runtime", "spu", "spu_workload.c")),
                         "no ps3recomp checkout (set PS3RECOMP_DIR)")
    def test_matches_ps3recomp(self):
        """Same function as the runtime's spu_workload_fingerprint() and as
        ps3recomp's build_spu_workloads.py, which registers the sound core."""
        fnv = load_tool("lift_spu_jobs").fnv1a64
        src = get(os.path.join(PS3RECOMP, "runtime", "spu", "spu_workload.c")).decode("utf-8", "replace")
        body = src[src.index("spu_workload_fingerprint("):]
        body = body[:body.index("\n}")]
        basis = int(re.search(r"uint64_t h = (\d+)ULL", body).group(1))
        prime = int(re.search(r"h \*= (\d+)ULL", body).group(1))
        self.assertIn("h ^= p[i];", body)                 # xor, then multiply: FNV-1a
        self.assertEqual((basis, prime), (RUNTIME_BASIS, FNV_PRIME))

        spec = importlib.util.spec_from_file_location(
            "build_spu_workloads", os.path.join(PS3RECOMP, "tools", "build_spu_workloads.py"))
        bsw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bsw)
        for i in range(8):
            data = fake_bytes(f"image {i}", 16 * (i + 1) * 37)
            self.assertEqual(fnv(data), bsw.fnv1a64(data))


class JobTable(unittest.TestCase):
    def test_invariants(self):
        jobs = load_tool("lift_spu_jobs").JOBS
        names = [j[0] for j in jobs]
        ids = [j[5] for j in jobs]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(len({j[3] for j in jobs}), len(jobs), "fingerprints must differ")
        for name, ea, size, fp, code_end, image_id, targets, desc in jobs:
            self.assertEqual(size % 16, 0, f"{name}: sizeBinary<<4 is a multiple of 16")
            self.assertLessEqual(code_end, size, name)
            self.assertGreaterEqual(image_id, 32, f"{name}: ids below 32 belong to build_spu_workloads.py")
            self.assertLess(fp, 1 << 64)
            self.assertRegex(name, r"^[a-z0-9]+$")    # becomes a C identifier prefix
            for t in targets:
                self.assertLess(t, code_end, f"{name}: jump target 0x{t:X} past the code")
                self.assertEqual(t % 4, 0)
            self.assertTrue(desc)


class EuropeanJobs(unittest.TestCase):
    """1.1.9: the European program (NPEA00019 v01.00) has its own job images; the table whose fingerprints all
    match the ELF is the one lifted."""

    def test_tables(self):
        m = load_tool("lift_spu_jobs")
        self.assertEqual([label for label, _ in m.JOBS_BY_PROGRAM], ["NPUB30009 v01.00", "NPEA00019 v01.00"])
        self.assertIs(m.JOBS_BY_PROGRAM[0][1], m.JOBS)
        for us, eu in zip(m.JOBS, m.JOBS_EU):
            self.assertEqual((us[0], us[2], us[5]), (eu[0], eu[2], eu[5]))     # name, size, image id
            self.assertNotEqual(us[1], eu[1])                                  # another place in the ELF
            self.assertLessEqual(eu[4], eu[2])
            for t in eu[6]:
                self.assertLess(t, eu[4])

    def test_pick_jobs_by_fingerprint(self):
        m = load_tool("lift_spu_jobs")
        a, b = fake_bytes("job a", 0x100), fake_bytes("job b", 0x80)
        segs = [(0x10000000, a + b)]
        one = [("x", 0x10000000, 0x100, m.fnv1a64(a), 0x100, 32, [], "x")]
        two = [("x", 0x10000100, 0x80, m.fnv1a64(b), 0x80, 32, [], "x")]
        with mock.patch.object(m, "JOBS_BY_PROGRAM", [("first", one), ("second", two)]):
            self.assertEqual(m.pick_jobs(segs), ("first", one))                  # the first table that matches
            self.assertEqual(m.pick_jobs([(0x10000000, bytes(0x180))]), (None, m.JOBS))   # none: the US table
        with mock.patch.object(m, "JOBS_BY_PROGRAM", [("first", one[:0] + [one[0][:1] + (0x10000000,) + one[0][2:]]),
                                                      ("second", two)]):
            self.assertEqual(m.pick_jobs([(0x10000000, b + a)])[0], None)        # wrong bytes at the first's EA
        with mock.patch.object(m, "JOBS_BY_PROGRAM", [("first", [("x", 0x10000000, 0x80, m.fnv1a64(b), 0x80, 32,
                                                                    [], "x")]), ("second", two)]):
            self.assertEqual(m.pick_jobs(segs)[0], "second")                     # only the second matches


class GuestReads(unittest.TestCase):
    def test_segments_and_reads(self):
        m = load_tool("lift_spu_jobs")
        a, b = fake_bytes("seg a", 0x300), fake_bytes("seg b", 0x80)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.elf")
            put(p, make_elf([(0x10000, a), (0x20000, b)]))
            segs = m.load_segments(p)
        self.assertEqual(segs, [(0x10000, a), (0x20000, b)])     # PT_NOTE skipped
        self.assertEqual(m.read_guest(segs, 0x10010, 0x20), a[0x10:0x30])
        self.assertEqual(m.read_guest(segs, 0x20000, 0x80), b)
        self.assertIsNone(m.read_guest(segs, 0x202F0, 0x20))       # crosses the end of a segment
        self.assertIsNone(m.read_guest(segs, 0x30000, 1))

    def test_rejects_little_endian_and_non_elf(self):
        m = load_tool("lift_spu_jobs")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.elf")
            put(p, b"\x7fELF\x02\x01" + bytes(58))
            with self.assertRaises(SystemExit):
                m.load_segments(p)
            put(p, b"SCE\0" + bytes(60))
            with self.assertRaises(SystemExit):
                m.load_segments(p)


class Output(unittest.TestCase):
    def test_debase_includes(self):
        m = load_tool("lift_spu_jobs")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "spu_recomp.c")
            put(p, '#include "../../runtime/spu/spu_helpers.h"\n#include "spu_recomp.h"\n'
                   '#include "../../../runtime/spu/spu_context.h"\n')
            m.debase_includes(p)
            self.assertEqual(get(p).decode(), '#include "spu_helpers.h"\n#include "spu_recomp.h"\n'
                                              '#include "spu_context.h"\n')

    def test_registration_block(self):
        m = load_tool("lift_spu_jobs")
        txt = m.registration("skin4x", "t5job_skin4x_", 0x1003DF80, 0x4480, 0x398E459063BA810A, 32, "desc")
        self.assertIn(m.REG_MARK, txt)
        self.assertIn("spu_begin_image(32); t5job_skin4x_spu_recomp_register();", txt)
        self.assertIn("spu_workload_register_img(0x398E459063BA810AULL, t5job_skin4x_spu_func_00000000, 32, "
                      '"skin4x");', txt)
        self.assertIn("static void t5job_skin4x_register_job(void)", txt)


class WrongGame(unittest.TestCase):
    def test_fingerprint_mismatch_fails_loudly(self):
        """Bytes at the job addresses that are not v01.00's must stop the
        script before anything is lifted or registered."""
        jobs = load_tool("lift_spu_jobs").JOBS
        lo = min(j[1] for j in jobs) & ~0xFFFF
        hi = max(j[1] + j[2] for j in jobs)
        with tempfile.TemporaryDirectory() as d:
            elf = os.path.join(d, "EBOOT.elf")
            put(elf, make_elf([(lo, fake_bytes("not the game", hi - lo))]))
            tools = os.path.join(d, "ps3recomp", "tools")
            os.makedirs(tools)
            for t in ("find_spu_functions.py", "spu_lifter.py"):
                put(os.path.join(tools, t), "raise SystemExit('must not be called')\n")
            spu = os.path.join(d, "spu")
            r = subprocess.run([PY, os.path.join(TOOLS, "lift_spu_jobs.py"), "--elf", elf, "--spu", spu,
                                "--ps3recomp", os.path.join(d, "ps3recomp")], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(f"{jobs[0][0]}: fingerprint", r.stderr)
            self.assertIn("not NPUB30009 v01.00", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(spu, "lifted")))

    def test_missing_ps3recomp_tools(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([PY, os.path.join(TOOLS, "lift_spu_jobs.py"), "--elf", "x", "--spu", d,
                                "--ps3recomp", os.path.join(d, "nowhere")], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("missing", r.stderr)


if __name__ == "__main__":
    unittest.main()
