# Continuous integration

`.github/workflows/ci.yml` runs on `windows-latest`. It uses **no game data**:
no package, no license, no keys, no lifted code. So it cannot boot the game. It
catches the breakage that can be caught without it.

## When it runs (the repository is private)

A private repository has a monthly budget of runner minutes (about 2,000 on the
free plan) and a Windows minute counts double, so the work is in two tiers:

| Job | push | pull request | by hand | Mondays 04:23 UTC (default branch) | cost |
|---|---|---|---|---|---|
| `checks` -- guard + patch series + Python tool tests | yes | no (the push already ran it) | yes | yes | ~2 min |
| `lobby` -- `lobby/tests` | no | yes | yes | yes | ~5 min (real-time windows, not CPU: 4.5 min pinned to 4 CPUs) |
| `runtime` -- patched ps3recomp build + native tests | no | yes | yes | yes | ~3 min warm, ~8 cold |

So a push to a branch gets the cheap job, and a pull request's head commit gets
all three. Concurrency: one run per ref, a newer push cancels the older one
(`concurrency: ci-<ref>`, `cancel-in-progress`). Run the long jobs on any branch
with "Run workflow" (`workflow_dispatch`); `runtime` needs no game data and can
be started from there at any time. The release workflow is separate
([RELEASING.md](RELEASING.md)).

## What runs

Three jobs run in parallel.

### `checks` -- game-data guard + Python tests (about 5-10 min, limit 30)

| Step | Catches |
|---|---|
| `tools/check_no_game_data.py` | anything game-derived in the tracked files |
| `... --history <range>` | the same in every commit of the push or PR (a file added and deleted again is still public) |
| `py_compile` on every tracked `.py`/`.pyw` | syntax errors in tools/, tests/, launcher/, lobby/ |
| `tools/prepare_ps3recomp.py` | a patch that no longer applies (named) |
| `python tests/ci_unittest.py -v` (= `unittest discover -s tests -v`) | broken tools (below); every failed test becomes an annotation |

Python tests in `tests/` (stdlib `unittest`, plus `pycryptodome` for unself
and Pillow for the smoke suite's frame checks):

- `test_unself.py` -- `rap_to_rif_key` against an independent reference and a
  fixed vector; a full decrypt of a **synthetic NPDRM SELF** built in the test
  with fake keys (compressed + plain segments, section headers); a wrong
  license is refused.
- `test_make_keys.py` -- `make_keys.py --source` on a fake key vault in
  RPCS3's layout (every name in `make_keys.NAMED`, package keys included);
  output read back by `unself.load_keys`.
- `test_build_game.py` -- pins, the output layout (`--out`, defaults inside
  ignored folders), the code ID, argument parsing and step order, one
  `ERROR:` line and exit 2 on a build error, the `deps` step's commands
  (patches in name order), its vendored-copy check, and with real git a
  developer's checkout prepared again when the patch series changed, `.rap`/`.pkg`
  validation, `PARAM.SFO` parsing, another title or another version refused.
- `test_lift_spu_jobs.py` -- the job fingerprint against the runtime's own
  (see the FNV note below), the job table, guest reads from a synthetic ELF,
  the include rewrite, the registration block, a loud failure on the wrong
  game version.
- `test_run_game.py` -- `game_command()`: paths, environment, overrides.
- `test_check_no_game_data.py` -- the guard catches each kind of game file
  and passes ordinary sources.
- `test_prepare_ps3recomp.py` -- name order, and the failing patch is named.
- `test_padmap_sync.py` -- the launcher's copy of the game's controller presets
  (`lobby/t5lobby/padmap.py`) equals the tables in patch 0009, and no later patch
  edits them.
- `test_smoke.py` -- the game-independent half of `tools/smoke/` (see
  docs/SMOKE.md): log parsing, every check on synthetic runs (crash, hang,
  fps/audio thresholds and the under-load WARN, NIDs, memory, white/frozen
  screens, fighters), known-issue marking, the report and exit codes,
  process selection by parent PID, the HUD/spike heuristics on synthetic
  frames, the runner's missing-exe path.

All fake keys are derived from hashes at run time. No key-shaped value is in
the repository (the guard would flag it).

`lobby/tests/test_tk_tab.py` used to abort the interpreter ("Tcl_AsyncDelete:
async handler deleted by the wrong thread": a worker thread dropped the last
reference to the Online tab). Fixed on branch `ranked`: the tab's worker
threads hold only a queue and the client call, never the tab or a Tk object,
so every lobby module is required again.

### `lobby` -- the lobby's own suite

`lobby/tests`, one process per module through the same wrapper, so a module that
kills the interpreter cannot hide the others: server, NAT/relay, Glicko-2, TLS
pinning, ranked play and match integrity, hosting, the launcher's Online tab, the
match driver with the stub game. It starts real servers and clients and waits on
real time windows, which is why it is not in the per-push tier.

### `runtime` -- patched ps3recomp (estimate: 7-11 min cold, 4-5 min with a warm compile cache)

(The same steps take under 2 min on the owner's PC at `-j 8`.)

1. `tools/prepare_ps3recomp.py --dest deps/ps3recomp`: clones
   NoahBPeterson/ps3recomp at the commit `tools/build_game.py` pins and applies
   `patches/ps3recomp/*.patch` in name order. The first patch that does not
   apply fails the job with its name and git's reason. New patches are picked
   up automatically.
2. MSVC environment (`ilammy/msvc-dev-cmd`), the runner's
   `C:/Program Files/LLVM/bin/clang-cl.exe`, Ninja. `sccache` caches compiles
   in the Actions cache (optional; the build runs without it if setup fails).
3. **Release host**: configure exactly like `package_release.py
   --prebuilt-host` (`T5DR_GAME_DLL=ON`, static CRT). It needs no lift.
   Build `ps3recomp_runtime` (every runtime file, including every file a
   patch changes), then `t5dr.exe` + `t5dr.lib` (the patched boot scaffold,
   the HLE NID table, the exports for `t5dr_game.dll`, the link).
4. `PS3RECOMP_BUILD_TESTS=ON`: `sync_stress` and the condition-variable
   tests (ctest). `fiber_switch` is left out: it does not link on Windows at
   the pin, with or without our patches. Patch 0083 gives the two programs
   stand-ins for the hooks our patches call from the sync sources and that
   live in files they do not link (`host_sched_main_wait_begin/end` from 0063,
   `cellSpurs_queue_wait_help/done`, `ppu_fp_thread_init`); before it they did
   not link (the Monday run was red from 0063 on). It touches only
   `tests/sync_stress`, so it changes nothing that is built for players --
   but, like every patch, the code ID (`patch_digest`).
5. `tests/run_ps3recomp_tests.py`: ps3recomp's self-contained native tests,
   compiled straight from source with clang-cl and run. `spu_float` is
   `test_spu_float_neon.c` (patch 0003's SSE4.1 SPU float ops, bit-exact
   against the scalar reference); `spu_mfc_slots` and `spu_lockline_peer`
   link `spu_workload.c` and `spurs_job.c` (patch 0002); plus shufb, SPU
   helpers, numeric semantics, lock-line coherence, RSX texture layout and
   primitives; `spu_int_sse` and `spu_near_float_sse` check patch 0064's x86
   byte permutes and SPU_NEAR_FLOAT ops bit for bit against the code they
   replaced. A test that prints "nothing to compare" fails.
   `tests/shim/pthread.h` gives the POSIX-only ones the four pthread calls
   they use. **`spu_mfc_slots` is our adapted copy of the upstream test**
   (`tests/c/test_spu_mfc_slots_ci.c`, header lists every change): upstream
   starts one spinning worker per MFC slot (128 at the pin) behind a barrier with
   a 10 s deadline, which a 4-vCPU runner cannot meet, so the step used to fail
   after 367 s. The copy runs 2 workers per CPU (8 on the runner; at least 8, at
   most one per slot, `T5_MFC_WORKERS=n` to override, 128 = upstream), yields in
   the barrier, claims the same 4096 contexts, and checks the same things; it
   takes about a second. It was checked against `mfc_for()` with the claim lock
   removed: that fails with 8, 16, 64 and 128 workers pinned to 4 CPUs. Time
   limits: 300 s for each of the two SPU tests (a normal run is under 10 s).
6. **In-exe build** (`T5DR_GAME_DLL=OFF`, what `build_game.py`'s full compile
   does). There is no game lift, so ps3recomp's `tools/make_smoke_elf.py`
   writes a `ppu_recomp.h` for its hand-written "smoke title" and
   `tests/smoke_t5dr.cmake` (passed as `CMAKE_PROJECT_t5dr_INCLUDE`) adds that
   title's C file to `t5dr`. Our `CMakeLists.txt` configures as for the game.
7. The launcher stub `T5DR Online.exe`, compiled as `package_release.py` does.
8. *Informational* (`continue-on-error`): boot the smoke title in the in-exe
   `t5dr` for up to 60 s and require three FIFO flips and `sys_process_exit`.
   This needs a D3D12 device on the runner. The smoke title's guest-thread
   checks (`sys_ppu_thread_create` returns 0) fail on Windows without our
   patches too -- the pin plus only 0001's two Windows build fixes fails them
   the same way -- so they are not required.

## Reading a red run without logs

The job logs need a login, the annotations do not. `tests/ci_unittest.py` and
`tests/run_ps3recomp_tests.py` write what you need to read as `::error`
annotations: each failed unit test (id and the end of its traceback) and a
summary line naming all of them; for a failed native test its FAIL/assert lines,
exit code, time and last output lines; plus one `::notice` with the runner's
CPUs/memory and the timings. GitHub keeps 10 error annotations per step, so
the tools mute the `::error::` lines they print on purpose while tests drive
them into error paths (`[muted] ::error::...` in the log); without that the
real failure was pushed out of the list. From a shell, no token needed:

    curl -s https://api.github.com/repos/TheWishin/T5DROnline/actions/runs?branch=<branch>
    curl -s https://api.github.com/repos/TheWishin/T5DROnline/actions/runs/<run>/jobs
    curl -s https://api.github.com/repos/TheWishin/T5DROnline/check-runs/<job id>/annotations

Things that only go wrong on the runner, found this way: the workspace is on
`D:` and the temp folder on `C:` (`os.path.relpath` raises `ValueError` between
drives: `tools/release_notes.py`); 4 CPUs (a test that needs a CPU per
thread); an English Windows (no localized output to decode). To try a unit test
the way the runner sees it, set `TEMP`/`TMP` to a folder on another drive and
`GITHUB_ACTIONS=true CI=1`.

## The game-data guard

Run it before you commit:

    python tools/check_no_game_data.py                       # staged + tracked files
    python tools/check_no_game_data.py --keys keys/ps3.keys  # also: the real key bytes (local only)
    python tools/check_no_game_data.py --history HEAD        # every commit

It fails on:

- **paths**: `.pkg .rap .rif .edat .sdat .self .sprx .prx .elf .sfo .pfd .trp
  .at3 .pam .pamf .keys .bin`, `EBOOT.BIN`, `PARAM.SFO`, `ICON0.PNG`/`PIC*.PNG`,
  `T55DATA*`, lifted output (`ppu_recomp*`, `spu_recomp.c/.h`,
  `spu_workloads.c`), anything under `keys/ game/ build/ deps/ _ref/ USRDIR/
  dev_hdd0/ PS3_GAME/ gamedata/ scratch/`;
- **size** over 1 MiB;
- **magic**: ELF, SCE (SELF/SPRX), PKG, NPD (EDAT/SDAT), PSF, PAMF, RIFF, TRP;
- **binary**: anything that is not UTF-8 text;
- **content**: the lifters' "generated" headers, 50+ lifted function names
  (`func_XXXXXXXX`), a `GIT binary patch`, hex runs of 512+ digits, base64 runs
  of 2048+ characters, and a **key name** (`RAP_KEY`, `NP_KLIC_KEY`,
  `NPDRM_xxxx_ERK`, ...) next to a 32+ digit hex value or a 16+ byte list.

The CI copy has no keys. It looks for key *names* with long values instead.
`--keys` (local) searches for each key's bytes as raw bytes, hex text or a C
byte list, and prints only the key's name, never its value.

A file we made that trips a rule (a synthetic fixture, say) goes in `ALLOW`
in the script, with the reason next to it.

## Run it locally

From a shell with the MSVC environment (`vcvars64.bat`) and LLVM on `PATH`:

    python tools/check_no_game_data.py --keys keys/ps3.keys
    python tests/ci_unittest.py -v
    cd lobby/tests && for %m in (test_*.py) do python ../../tests/ci_unittest.py -v %~nm
    cd ../..
    python tools/prepare_ps3recomp.py --dest build/<you>/patchcheck --source deps/ps3recomp --replace

    rem release host (no lift needed)
    cmake -S . -B build/<you>/ci-host -G Ninja -DCMAKE_BUILD_TYPE=Release ^
          -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl ^
          -DPS3RECOMP_DIR=<abs>/build/<you>/patchcheck -DT5DR_GAME_DLL=ON ^
          -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded -DPS3RECOMP_BUILD_TESTS=ON
    cmake --build build/<you>/ci-host --target ps3recomp_runtime t5dr sync_stress test_cond_semantics -j 8
    ctest --test-dir build/<you>/ci-host/ps3recomp -E fiber_switch
    python tests/run_ps3recomp_tests.py --ps3recomp build/<you>/patchcheck --out build/<you>/native-tests

    rem in-exe build against the smoke title
    python build/<you>/patchcheck/tools/make_smoke_elf.py --out build/<you>/smoke/smoke.elf --header build/<you>/smoke/ppu_recomp.h
    cmake -S . -B build/<you>/ci-smoke -G Ninja -DCMAKE_BUILD_TYPE=Release ^
          -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl ^
          -DPS3RECOMP_DIR=<abs>/build/<you>/patchcheck -DRECOMP_DIR=<abs>/build/<you>/smoke ^
          -DCMAKE_PROJECT_t5dr_INCLUDE=<abs>/tests/smoke_t5dr.cmake
    cmake --build build/<you>/ci-smoke --target t5dr -j 8

If other builds share the machine, check `Get-Process clang-cl` first and keep
`-j` low.

## What CI cannot check

Anything that needs the game: decrypting the real EBOOT, lifting it, the SPU
lift, compiling the lift into `t5dr_game.dll` (`tools/build_game_dll.py`),
booting, rendering, audio, frame rate, netplay. Those still need a run on a
PC with the player's package. `tools/package_release.py` (which has its own
no-game-data checks) is not run by this workflow; only the pieces it builds
(the release host, the stub) are. The release workflow
(`.github/workflows/release.yml`, [RELEASING.md](RELEASING.md)) runs it in
full, on version tags and on pushes that change the release tooling.

Also not run: `test_spu_lifted_start.c` (POSIX-only; with shims it links on
Windows but crashes the same way on the unpatched pin), and
`test_gcm_user_command.c` / `test_audio_ring.c` (POSIX-only, and upstream CI
does not run them either). These would cover patches 0001/0002/0007 more
directly on a Linux runner.

## Notes

- **The pin lives in one place**: `tools/build_game.py` (`PS3RECOMP_URL`,
  `PS3RECOMP_BRANCH`, `PS3RECOMP_COMMIT`). `prepare_ps3recomp.py` and the
  tests read it from there.
- **FNV**: ps3recomp's FNV-1a-64 starts from `1469598103934665603`, the
  textbook offset basis (`14695981039346656037`) with the last digit
  dropped. It is used consistently by the runtime and the build tools, so
  `lift_spu_jobs.py` must keep it. A test pins this.
- A new patch: add it as `patches/ps3recomp/NNNN-topic.patch` and run
  `prepare_ps3recomp.py` on a fresh directory before committing.
