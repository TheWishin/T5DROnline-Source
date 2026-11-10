# Preflight 1.2.3 (local, 2026-11-10/11)

Candidate: branch release-123-all at 566d8d89. Nothing was pushed, tagged, drafted, uploaded or deployed.
Run on the developer PC with the worktree's own venv (CPython 3.12.10), steps run one by one (not the
whole `tools/release_preflight.py`, so its steps 1-3, 6 and 7 are not part of this record).

| Step | Result |
|---|---|
| 1. `tests/ci_unittest.py -v --timeout 2400 test_layout_lobby_entry`, alone, normal priority | OK, 11 tests, 1273.6 s (21 min 14 s wall, 00:11-00:32). Another game and some Python jobs of other sessions were running on the PC. |
| 2. LLVM | `tools/fetch_llvm.py --dest build/rd/llvm`: SHA-256 OK, LLVM 23.1.3, 82 s |
| 3. ps3recomp | local clone at f17bcd3 as source, 95 patches applied, 32 s |
| 4. Player zip (`package_release.py --release --version 1.2.3`, inside vcvars64, MSVC 14.44.35207) | OK, 111 s. Binary check: 95 imports checked; scan of folder and zip: 2218 files, 275.6 MB, no game files, no lifted code, no keys (key-bytes scan run with the local keys file) |
| 5. `smoke_release.py` with the GUI checks, bare PATH | 14/14 checks passed, 37 s |

Zip: `D:\t4-night\w018\rel123all\build\preflight\123\dist\T5DR-Online-1.2.3.zip` (98,239,904 bytes)

SHA-256: `1b0b1b9041a99f7dfdebc1756f6329f737390f8fe6a809e8170577e4f77e7e6e`

GUI checks: the desktop had no input for over an hour. The checks use no window titles: the launcher is
rendered offscreen (5 tab images, exit 0 after 14 s) and `T5DR Online.exe` is started with a package chosen
(starter exit 0, launcher process still alive after 15 s, then closed by the check).

Not done here: preflight step 6 (all unit tests) and step 7 (changelog/README release lines) as one run, CI,
the update drills, the signing step. The zip is not code-signed (smoke: "no signing service set up").

Two first attempts at step 4 failed through a wrong relative LLVM path in the local helper script (not a
repository problem); the third run, with absolute paths, is the one recorded.
