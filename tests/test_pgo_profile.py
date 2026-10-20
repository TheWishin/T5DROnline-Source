"""The lifted code's PGO profile (tools/gamedll/t5dr_lifted.proftext): tools/profile_check.py accepts
only function names, hashes and counts; the repository and release guards exempt that one path only
when the check passes; build_game_dll.py splits it into a PPU and an SPU profile. Every profile here
is made up on the spot (invented addresses and counts)."""
import os
import subprocess
import tempfile
import unittest

from helpers import PY, ROOT, TOOLS, load_tool

pc = load_tool("profile_check")
bgd = load_tool("build_game_dll")
GUARD = os.path.join(TOOLS, "check_no_game_data.py")
PROFDATA = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "LLVM", "bin", "llvm-profdata.exe")


def record(name, counts, h=12345):
    return "%s\n# Func Hash:\n%d\n# Num Counters:\n%d\n# Counter Values:\n%s\n" % (
        name, h, len(counts), "\n".join(str(c) for c in counts))


def profile(n_ppu=3, extra=""):
    recs = [record("?func_%08X@@YAXPEAUppu_context@@@Z" % (0x10200 + 4 * i), [i + 1, 0, 7]) for i in range(n_ppu)]
    recs += [record("bnuscore_spu_func_0000B1E8", [99, 1]),
             record("t5job_skin1x_spu_func_00000040", [5]),
             record("t5job_skin1x_spu_recomp_register", [1]),
             record("t5dr_spu_register_all", [1]),
             record("ppu_recomp_003.cpp:?vm_read32_inl@@YAI_K@Z", [10, 9, 1]),
             record("spu_recomp.c:spu__nf_be", [300]),
             record("spu_recomp.c:spu__nf_be", [7], h=999)]       # same helper name, other hash
    return ("\n".join(recs) + extra).encode()


class ProfileCheck(unittest.TestCase):
    def test_accepts_names_hashes_counts(self):
        self.assertEqual(pc.check(profile()), [])
        self.assertEqual(pc.check(b":fe\n" + profile()), [])
        self.assertEqual(pc.check(b"# IR level Instrumentation Flag\n:ir\n" + profile()), [])
        self.assertEqual(pc.check(profile().replace(b"\n", b"\r\n")), [])

    def test_rejects_anything_else(self):
        cases = {
            "unknown name": profile() + record("main", [1]).encode(),
            "name with a path": profile() + record(r"C:\Users\x\ppu_recomp_001.cpp:f", [1]).encode(),
            "free text": profile() + b"\nthis is not a record\n",
            "value profile": profile().rstrip(b"\n") + b"\n# Num Value Kinds:\n1\n",
            "bitmap": profile().rstrip(b"\n") + b"\n# Num Bitmap Bytes:\n$1\n",
            "counter not a number": record("?func_00010200@@YAXPEAUppu_context@@@Z", [1]).replace("1\n", "0x41\n").encode(),
            "missing counters": b"?func_00010200@@YAXPEAUppu_context@@@Z\n# Func Hash:\n1\n# Num Counters:\n3\n"
                                b"# Counter Values:\n1\n",
            "binary": b"\x00\x01ELF" + profile(),
            "not ascii": profile() + "\n\u00e4\n".encode(),
            "twice": profile() + record("bnuscore_spu_func_0000B1E8", [1]).encode(),
            "empty": b"",
        }
        for what, data in cases.items():
            with self.subTest(what):
                self.assertNotEqual(pc.check(data), [], what)

    def test_size_limit(self):
        self.assertTrue(pc.check(b"x" * (pc.MAX_BYTES + 1)))

    def test_shipped_profile_passes(self):
        path = os.path.join(ROOT, *pc.PROFILE_PATH.split("/"))
        if not os.path.exists(path):
            self.skipTest("no shipped profile in this checkout")
        with open(path, "rb") as f:
            self.assertEqual(pc.check(f.read()), [])


def git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "-c", "core.autocrlf=false", *args], check=True, capture_output=True)


class Guards(unittest.TestCase):
    """check_no_game_data.py and package_release.classify take the profile at its path only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q")

    def add(self, rel, data):
        p = os.path.join(self.repo, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        git(self.repo, "add", "-f", rel)

    def guard(self):
        e = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
        r = subprocess.run([PY, GUARD, "--repo", self.repo], capture_output=True, text=True, env=e)
        return r.returncode, r.stdout + r.stderr

    def test_profile_path_accepted(self):
        big = profile(n_ppu=200) * 1          # 200 lifted names: over the generic limit of 50
        self.add(pc.PROFILE_PATH, big)
        code, out = self.guard()
        self.assertEqual(code, 0, out)

    def test_same_content_elsewhere_refused(self):
        self.add("tools/gamedll/other.proftext", profile(n_ppu=200))
        code, out = self.guard()
        self.assertEqual(code, 1, out)
        self.assertIn("lifted function names", out)

    def test_bad_profile_at_the_path_refused(self):
        self.add(pc.PROFILE_PATH, profile() + b"\nsome other text\n")
        code, out = self.guard()
        self.assertEqual(code, 1, out)
        self.assertIn("PGO profile", out)

    def test_release_scan(self):
        pr = load_tool("package_release")
        good = profile(n_ppu=200)
        self.assertEqual(pr.classify("T5DR-Online-1.1.3/" + pc.PROFILE_PATH, good), [])
        self.assertEqual(pr.classify(pc.PROFILE_PATH, good), [])
        self.assertTrue(any("lifted game code" in w for w in pr.classify("T5DR-Online-1.1.3/tools/x.proftext", good)))
        self.assertTrue(any("lifted game code" in w for w in pr.classify("a/b/" + pc.PROFILE_PATH, good)))
        self.assertTrue(any("PGO profile" in w for w in pr.classify(pc.PROFILE_PATH, good + b"\nfree text\n")))


class Split(unittest.TestCase):
    def test_spu_records(self):
        for n in ("bnuscore_spu_func_0000B1E8", "t5job_skin4x_spu_recomp_register", "t5dr_spu_register_all",
                  "spu_recomp.c:spu__nf_be", "spu_dispatch_mt.c:x", "spu_workloads.c:y", "t5dr_game_dll.c:z"):
            self.assertTrue(bgd.is_spu_record(n), n)
        for n in ("?func_00010200@@YAXPEAUppu_context@@@Z", "ppu_recomp_003.cpp:?vm_read32_inl@@YAI_K@Z"):
            self.assertFalse(bgd.is_spu_record(n), n)

    @unittest.skipUnless(os.path.exists(PROFDATA), "needs LLVM's llvm-profdata.exe")
    def test_prepare_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "t5dr_lifted.proftext")
            with open(src, "wb") as f:
                f.write(profile())
            out = bgd.prepare_profiles(src, d, os.path.dirname(PROFDATA))
            self.assertEqual(sorted(out), ["ppu", "spu"])
            names = {}
            for kind, p in out.items():
                r = subprocess.run([PROFDATA, "show", "--all-functions", p], capture_output=True, text=True)
                names[kind] = [ln.strip().rstrip(":") for ln in r.stdout.splitlines() if ln.startswith("  ") and
                               ln.rstrip().endswith(":") and not ln.startswith("    ")]
            self.assertEqual(len(names["ppu"]), 4, names)     # 3 lifted functions + the PPU helper
            self.assertTrue(all("ppu_context" in n or n.startswith("ppu_recomp_") for n in names["ppu"]), names)
            self.assertIn("bnuscore_spu_func_0000B1E8", names["spu"])
            # an unusable profile is skipped, never half used
            with open(src, "ab") as f:
                f.write(b"\nfree text\n")
            self.assertEqual(bgd.prepare_profiles(src, d, os.path.dirname(PROFDATA)), {})
            # no llvm-profdata: build without the profile
            empty = os.path.join(d, "nollvm")
            os.makedirs(empty)
            self.assertEqual(bgd.prepare_profiles(src, d, empty), {})


if __name__ == "__main__":
    unittest.main()
