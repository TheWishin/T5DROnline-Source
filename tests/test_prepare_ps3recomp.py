"""tools/prepare_ps3recomp.py against a throwaway "upstream": the series is
applied in name order on the pinned commit, and the first patch that does not
apply is named. Also: the real pin is the one build_game.py uses."""
import os
import subprocess
import tempfile
import unittest

from helpers import PY, TOOLS, load_tool, put

SCRIPT = os.path.join(TOOLS, "prepare_ps3recomp.py")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "core.autocrlf=false", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def diff(name, old, new):
    """A git-style patch turning file `name` from old into new (1-line files)."""
    return (f"diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n"
            f"@@ -1 +1 @@\n-{old}\n+{new}\n")


class Prepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.up = os.path.join(self.tmp.name, "upstream")
        os.makedirs(self.up)
        git(self.up, "init", "-q", "-b", "main")
        put(os.path.join(self.up, "a.c"), "int a = 1;\n")
        put(os.path.join(self.up, "b.c"), "int b = 1;\n")
        git(self.up, "add", ".")
        git(self.up, "commit", "-q", "-m", "pinned")
        self.pin = git(self.up, "rev-parse", "HEAD")
        put(os.path.join(self.up, "a.c"), "int a = 99;\n")     # upstream moved on after the pin
        git(self.up, "commit", "-q", "-am", "later")
        self.patches = os.path.join(self.tmp.name, "patches")
        os.makedirs(self.patches)

    def prepare(self, dest="tree"):
        r = subprocess.run([PY, SCRIPT, "--dest", os.path.join(self.tmp.name, dest), "--source", self.up,
                            "--branch", "main", "--commit", self.pin[:7], "--patches", self.patches],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_series_applies_in_name_order(self):
        # 0002 only applies after 0001 -- so name order is what makes it pass.
        put(os.path.join(self.patches, "0002-second.patch"), diff("a.c", "int a = 2;", "int a = 3;"))
        put(os.path.join(self.patches, "0001-first.patch"), diff("a.c", "int a = 1;", "int a = 2;"))
        put(os.path.join(self.patches, "0003-other.patch"), diff("b.c", "int b = 1;", "int b = 5;"))
        put(os.path.join(self.patches, "README.txt"), "not a patch\n")
        code, out = self.prepare()
        self.assertEqual(code, 0, out)
        tree = os.path.join(self.tmp.name, "tree")
        self.assertEqual(git(tree, "rev-parse", "HEAD"), self.pin)
        with open(os.path.join(tree, "a.c")) as f:
            self.assertEqual(f.read().strip(), "int a = 3;")
        self.assertLess(out.index("applied 0001"), out.index("applied 0002"))
        self.assertIn("3 patch(es) applied", out)

    def test_names_the_patch_that_does_not_apply(self):
        put(os.path.join(self.patches, "0001-first.patch"), diff("a.c", "int a = 1;", "int a = 2;"))
        put(os.path.join(self.patches, "0002-stale.patch"), diff("a.c", "int a = 1;", "int a = 7;"))
        put(os.path.join(self.patches, "0003-never.patch"), diff("b.c", "int b = 1;", "int b = 5;"))
        code, out = self.prepare()
        self.assertNotEqual(code, 0)
        self.assertIn(f"patch 0002-stale.patch does not apply on {self.pin[:7]} + 0001-first.patch", out)
        self.assertIn("a.c", out)                      # git's own reason follows
        self.assertNotIn("applied 0003", out)

    def test_refuses_existing_dest_and_unknown_commit(self):
        os.makedirs(os.path.join(self.tmp.name, "busy"))
        code, out = self.prepare("busy")
        self.assertNotEqual(code, 0)
        self.assertIn("--replace", out)
        self.pin = "0123456789abcdef0123456789abcdef01234567"
        put(os.path.join(self.patches, "0001-first.patch"), diff("a.c", "int a = 1;", "int a = 2;"))
        code, out = self.prepare()
        self.assertNotEqual(code, 0)
        self.assertIn("pinned commit 0123456", out)

    def test_pin_comes_from_build_game(self):
        bg, prep = load_tool("build_game"), load_tool("prepare_ps3recomp")
        self.assertEqual(prep.pin(), (bg.PS3RECOMP_URL, bg.PS3RECOMP_BRANCH, bg.PS3RECOMP_COMMIT))


if __name__ == "__main__":
    unittest.main()
