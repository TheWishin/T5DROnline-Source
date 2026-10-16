# Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request, on
`windows-latest`. It uses **no game data**: no package, no license, no keys, no
lifted code. So it cannot boot the game. It catches the breakage that can be
caught without it.

## What runs

Two jobs run in parallel.

### `checks` -- game-data guard + Python tests (about 2 min)

| Step | Catches |
|---|---|
| `tools/check_no_game_data.py` | anything game-derived in the tracked files |
| `... --history <range>` | the same in every commit of the push or PR (a file added and deleted again is still public) |
| `python -m py_compile tools/*.py tests/*.py` | syntax errors |
| `tools/prepare_ps3recomp.py` | a patch that no longer applies (named) |
| `python -m unittest discover -s tests` | broken tools (below) |

Python tests in `tests/` (stdlib `unittest`, plus `pycryptodome` for unself):

- `test_unself.py` -- `rap_to_rif_key` against an independent reference and a
  fixed vector; a full decrypt of a **synthetic NPDRM SELF** built in the test
  with fake keys (compressed + plain segments, section headers); a wrong
  license is refused.
- `test_make_keys.py` -- `make_keys.py --source` on a fake key vault in
  RPCS3's layout; output read back by `unself.load_keys`.
- `test_build_game.py` -- pins, argument parsing, step order, the `deps`
  step's commands (patches in name order), steps that must refuse to run
  without `--pkg`/`--rap`, the SHA-1 version pin.
- `test_lift_spu_jobs.py` -- the job fingerprint against the runtime's own
  (see the FNV note below), the job table, guest reads from a synthetic ELF,
  the include rewrite, the registration block, a loud failure on the wrong
  game version.
- `test_run_game.py` -- the environment handed to the game.
- `test_check_no_game_data.py` -- the guard catches each kind of game file
  and passes ordinary sources.
- `test_prepare_ps3recomp.py` -- name order, and the failing patch is named.

All fake keys are derived from hashes at run time. No key-shaped value is in
the repository (the guard would flag it).

### `runtime` -- patched ps3recomp (estimate: 5-8 min cold, 3-4 min with a warm compile cache)

(The same steps take about 70 s on the owner's PC at `-j 8`.)

1. `tools/prepare_ps3recomp.py --dest deps/ps3recomp`: clones
   NoahBPeterson/ps3recomp at the commit `tools/build_game.py` pins and applies
   `patches/ps3recomp/*.patch` in name order. The first patch that does not
   apply fails the job with its name and git's reason.
2. MSVC environment (`ilammy/msvc-dev-cmd`), the runner's
   `C:/Program Files/LLVM/bin/clang-cl.exe`, Ninja. `sccache` caches compiles
   in the Actions cache (optional; the build runs without it if setup fails).
3. **Smoke title instead of a lift.** ps3recomp's `tools/make_smoke_elf.py`
   writes a `ppu_recomp.h` for its hand-written "smoke title".
   `tests/smoke_t5dr.cmake` (passed as `CMAKE_PROJECT_t5dr_INCLUDE`) adds that
   title's C file to `t5dr`. So **our `CMakeLists.txt` configures as for the
   game**.
4. Build `ps3recomp_runtime`: every runtime file, including every file a patch
   changes.
5. Link `t5dr`: the patched boot scaffold (`ppu_loader.cpp`, `boot_main.cpp`,
   ...), the generated HLE NID table, the link against the runtime.
6. `PS3RECOMP_BUILD_TESTS=ON`: `sync_stress` and the condition-variable
   tests (ctest). `fiber_switch` is left out: it does not link on Windows at
   the pin, with or without our patches.
7. `tests/run_ps3recomp_tests.py`: ps3recomp's self-contained native tests,
   compiled straight from source with clang-cl and run. `spu_float` is
   `test_spu_float_neon.c` (patch 0003's SSE4.1 SPU float ops, bit-exact
   against the scalar reference); `spu_mfc_slots` and `spu_lockline_peer`
   link `spu_workload.c` and `spurs_job.c` (patch 0002); plus shufb, SPU
   helpers, numeric semantics, lock-line coherence, RSX texture layout and
   primitives. A test that prints "nothing to compare" fails.
   `tests/shim/pthread.h` gives the POSIX-only ones the four pthread calls
   they use.
8. *Informational* (`continue-on-error`): boot the smoke title in `t5dr` for
   up to 60 s and require three FIFO flips and `sys_process_exit`. This needs
   a D3D12 device on the runner. The smoke title's guest-thread checks
   (`sys_ppu_thread_create` returns 0) fail on Windows without our patches
   too -- the pin plus only 0001's two Windows build fixes fails them the same
   way -- so they are not required.

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
    python -m unittest discover -s tests -v
    python tools/prepare_ps3recomp.py --dest build/<you>/patchcheck --source deps/ps3recomp --replace
    python build/<you>/patchcheck/tools/make_smoke_elf.py --out build/<you>/smoke/smoke.elf --header build/<you>/smoke/ppu_recomp.h
    cmake -S . -B build/<you>/ci-cmake -G Ninja -DCMAKE_BUILD_TYPE=Release ^
          -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl ^
          -DPS3RECOMP_DIR=<abs>/build/<you>/patchcheck -DRECOMP_DIR=<abs>/build/<you>/smoke ^
          -DCMAKE_PROJECT_t5dr_INCLUDE=<abs>/tests/smoke_t5dr.cmake -DPS3RECOMP_BUILD_TESTS=ON
    cmake --build build/<you>/ci-cmake --target ps3recomp_runtime t5dr -j 8
    python tests/run_ps3recomp_tests.py --ps3recomp build/<you>/patchcheck --out build/<you>/native-tests

If other builds share the machine, check `Get-Process clang-cl` first and keep
`-j` low.

## What CI cannot check

Anything that needs the game: decrypting the real EBOOT, lifting it, the SPU
lift, booting, rendering, audio, frame rate, netplay. Those still need a run
on a PC with the player's package.

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
