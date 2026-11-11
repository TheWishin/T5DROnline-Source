# A build for processors without SSE4.1 (2026-11-11)

Probe on branch `sse2-probe-018` (main `db9711a5`); made shippable on branch `t5-oldhw-019` (from
`release-123-final` `b43edf2c`, ps3recomp patch renumbered 0123 -> **0126**). Question: can T5DR run on a 2006-2007
processor (Core 2 Duo "Conroe", Athlon 64 X2, later Phenom II / Athlon II: SSE2/SSE3 only), and how fast.

Short answer: **the build exists, runs and computes the same game; the processors it is for are far too slow for
60 fps.** The release can carry it so that such a PC starts at all (section "Shipping it" at the end).

## What used newer instructions (inventory)

Compile flags:

| where | flag | what it allows |
|---|---|---|
| ps3recomp `CMakeLists.txt` (2 places) | `-msse4.1` for the runtime and for every C file a port compiles against it (the lifted SPU code) | SSE3, SSSE3, SSE4.1 anywhere the compiler likes |
| `CMakeLists.txt` `T5DR_LIFTED_ARCH`, `tools/build_game_dll.py --march` | `auto` = `-march=x86-64-v3` (AVX2, FMA, BMI1/2, LZCNT, MOVBE), else `-mavx`, else nothing | the lifted PPU and SPU code |
| `tools/build_game_dll.py` | `-msse4.1` for the lifted SPU C | as the runtime |
| `CMakeLists.txt` | `/clang:-mcx16` (runtime and `src/`) | CMPXCHG16B: every Core 2 has it, Windows 8.1+ needs it |

Source (ps3recomp at the pin + patches 0001..0122, and `src/`): 16 lines in 2 files use an intrinsic above SSE2.
`runtime/spu/spu_helpers.h` 12 (`pshufb` 6 times, `pblendvb` 3, `pcmpeqq` 4, `pabsd`, `ptest`), behind
`__SSE4_1__` with a scalar fallback; `runtime/ppu/ppu_fp_det.h` 4 (`roundss`), with an exact SSE2 form beside it since
patch 0032. `ppu_fp_det.h` / `ppu_vmx.h` choose FMA and AVX forms by `__FMA__` / `__AVX__` (10 + 13 lines), all with
software forms that give the same bits (patches 0032, 0104, 0114, 0121). `src/`: none (only CPUID checks).
POPCNT: none in the source. Leading-zero counts are `__builtin_clz*` (bsr): no LZCNT required.

What the compiler made of it, counted in the linked `t5dr.exe` with the new `tools/isa_audit.py` (disassembly +
linker map, per function):

| instructions above SSE2 | normal build (v3 lifted code) | SSE2 baseline build |
|---|---|---|
| SSE3 | 159 in 34 functions | 0 |
| SSSE3 | 181 in 61 functions | 0 of ours (2 in the C++ library) |
| SSE4.1 | 3,324 in 188 functions | 0 of ours (4 in the C++ library) |
| SSE4.2 | 3 (C++ library) | 3 (C++ library) |
| POPCNT | 0 | 0 |
| LZCNT / BMI / MOVBE | 195 / 3,216 / 989 | 0 of ours (2 LZCNT in the C++ library) |
| AVX, AVX2, FMA (VEX) | 464,863 in 5,427 functions | 8 of ours, in `ppu_fma_hw` (below); 83 in the C++ library |

"C++ library" = Microsoft's `__std_*` vector algorithms (find, search, minmax), which pick their SSE4.2/AVX2 body by
CPUID at run time and never run it on a processor without it. So a plain "drop the flag" audit of the normal build's
SSE4.1 use would have been misleading: only 12 source lines ask for it, but the compiler used it in 188 runtime
functions (movie conversion, PNG, the D3D12 backend, pad code, ...).

## The baseline build

- **ps3recomp patch 0126** (`patches/ps3recomp/0126-sse2-baseline.patch`): `PS3RECOMP_X86_BASELINE=ON` drops
  `-msse4.1`; `spu_helpers.h` gets SSE2 forms of everything its SSE4.1 path used. Byte shifts and rotates of the
  128-bit register as two 64-bit halves (no `pshufb`); `shufb` as whole 32-bit moves when the control is word-wise
  (what `cwd`/`cdd` controls and float shuffles are), else 16 table reads; generate-controls and select masks with
  and/andnot; the float path's `pabsd`, `pcmpeqq`, `ptest` written with SSE2 compares.
- **Why not just the scalar fallback that was already there:** it is not the same game. The sound core runs with
  `SPU_NEAR_FLOAT` (round to nearest), and the old fallback of a build without SSE4.1 was the exact SPU path (round
  toward zero): other bits in every float result (`tests/test_sse2_baseline.py` shows it).
- **Switches:** CMake `T5DR_X86_BASELINE=ON` (runtime + lifted SPU code without `-msse4.1`, lifted PPU code
  `-march` none, `cpu_check.cpp` no longer stops without SSE4.1); `tools/build_game.py` reads `T5DR_X86_BASELINE=1`;
  `tools/build_game_dll.py --simd sse2` for the player-side DLL. Default everywhere: as before.
- Not done (it would be the release work): a second prebuilt runtime in the zip (`t5dr-sse2.exe`, as Tekken 4 ships
  its SSE2 twin), the launcher choosing it, the "processor too old" texts, a PGO profile check for the baseline.

## Same results

Three levels, all on this PC (its processor has every instruction, so "runs on an old processor" is shown by
what is in the file, not by an old processor):

- **No instruction above SSE2 in our code:** the table above (`tools/isa_audit.py --fail-on ...` exits 0 for the
  baseline `t5dr.exe`). One function is above SSE2 by design: `ppu_fma_hw` (one `vfmadd`, two copies in the
  program), which `ppu_fp_det.h` calls only when CPUID reports FMA (patch 0032); the audit lists it as guarded.
- **The helpers, bit for bit:** `tests/test_sse2_baseline.py` builds `tests/c/spu_sse2_cross_test.c` with and without
  `-msse4.1` in the three float modes the game uses (exact, `SPU_NEAR_FLOAT` = the sound core, `SPU_FAST_FLOAT` = the
  skinning jobs): the same digest for each of 33 operations over 400,000 operand sets (special values,
  cancellations, every shift count, word-wise and near-word-wise controls), the integer forms also equal to the
  scalar loops, and the baseline object free of newer instructions. ps3recomp's own suites built without the flag
  (`tests/run_ps3recomp_tests.py`, six new entries): `shufb` 200,000 cases, byte permutes / generate controls / fsm
  3,900,544 checks, the float path against the scalar definition 8,000,000 cases, `SPU_NEAR_FLOAT` with the same
  checksum as the SSE4.1 build (`FA551799C56DF954`), `SPU_FAST_FLOAT` 4,624,268: all pass, as do the 14 old ones.
- **The game, frame by frame:** `tools/cross_build_test.py`, the normal build hosting, the SSE2 baseline joining as a
  PC without FMA would (`PS3_FP_SOFT_FMA=1`, `PS3_CRT_FMA3=0`), RTT 50 / jitter 5 / loss 3 %, two matches per mode:
  rollback 8,997 frames, lockstep 9,020 frames, **0 different**, the same result hashes on both sides. Old and new
  players would meet in sync; `CODE_VERSION` does not need to move.

Not done: a start on a real processor without SSE4.1; other stages and modes than the scripted fights; the
player-side DLL layout (`tools/build_game_dll.py --simd sse2` is wired but was not built or run here: only the
developer build, one `t5dr.exe`).

## Speed on this PC

Development PC (Ryzen 9 7950X, RTX 3090, Windows 11), the game limited to 4 cores / 8 threads (mask `0xFF00`),
below-normal priority, muted, alone on the PC's heavy-run slots (1.7-3.5 processors of other load stayed).
`tools/fight_bench.py`, direct fight Lili vs Asuka, stage 20, the 60 s from second 24 on. Three developer builds of
the same lift: **normal** (lifted code x86-64-v3, runtime SSE4.1: what this PC's players get), **SSE4.1 + baseline
lifted code** (what a 2008-2010 processor without AVX gets today), **SSE2 baseline** (this probe).

| build (runs) | fps | frame time median / p99 | game thread CPU per frame, median / p99 | sound core | skinning jobs | all threads per frame |
|---|---|---|---|---|---|---|
| normal (3) | 58.9-60.0 | 16.67 / 19.1-20.2 ms | 2.64-2.74 / 3.3-4.1 ms | 3.4 ms | 1.6 ms | 14.0-14.5 ms |
| SSE4.1 + baseline lifted code (3) | 60.0 | 16.67 / 19.2-19.6 | 3.05 / 3.7-3.8 | 3.5 | 1.6 | 14.8-15.5 |
| **SSE2 baseline** (2) | 59.8-60.0 | 16.67 / 19.4 | 3.11-3.19 / 3.8-4.2 | 4.7-4.8 | 2.9-3.1 | **17.9-18.7** |
| SSE2 baseline before the word-wise `shufb` (2) | 60.0 | 16.65 / 18.9-19.0 | 3.42-3.47 / 4.4-5.0 | 8.1 | 4.5 | 23.2-24.2 |

On 2 cores without SMT (mask `0x5000`, one run each): SSE4.1 + baseline lifted 13.2 ms of processor time per frame,
game thread 3.5 / 4.7 ms; SSE2 baseline 16.4 ms, game thread 4.3 / 5.9 ms; both 60 fps (p99 18.7-18.8 ms).

**Slowdown factor of the SSE2 baseline: 1.28 in processor time per frame against the normal build (18.3 / 14.3 ms),
1.21 against the SSE4.1 build with the same lifted code; game thread 1.18 and 1.03; sound core 1.4; skinning 1.8-1.9.**
The frame time itself does not move on this PC: every build holds 60 with the same median and p99, because a frame
needs a quarter of the time there is. Translation (1.5 ms) and GPU time are the same in all builds.
The cost sits in the SPU code: without `pshufb` every byte permute is a table walk. More of it can be won back the
way the word-wise `shufb` won 6 ms (other fixed patterns); not done here.

## What it means for an old processor

The owner's yardstick: a 2006 dual core is about 10 times slower per core than this PC. Not measured (no such
processor here); the only cross-check is a player's i5-2500 log (2011, 4 cores): its game thread needs 7-12 ms where
this PC needs 2.7-3.5, so about 3 times slower, and it reaches 55-60 fps.

With the 2-core figures above times 10: 164 ms of processor work per frame on 2 cores = **at best 12 fps**, and the
sound core alone needs 49 ms for every 16.7 ms of sound, so it cannot keep up at all (the game waits for it every
audio tick: slow motion with broken sound). Times 5 (an optimistic Core 2 Duo E8000 or Phenom II): about 24 fps and
the sound core still over its budget.

Read the other way: for 60 fps the SSE2 build needs 4 cores at about 45-50 % of this PC's core speed, or 2 cores at
about 55-60 % (16.4 ms of work per frame, the game thread's 6-7 ms p99 chain, the sound core's own core). **No
processor without SSE4.1 is that fast.** The fastest ones (Phenom II X4/X6, 2009-2010, about a third of this PC per
core: estimate) would land around 35-45 fps; a Core 2 Quad Q6600 around 20-25; a 2006 Core 2 Duo at 10-15 with
unusable sound. The realistic class for 60 fps stays what the README says: 4 cores from 2011 on (Sandy Bridge),
which have SSE4.1 and AVX anyway. The SSE2 build widens "starts at all", not "playable".

## What stays in the way besides the processor (not measured here)

- **Graphics card:** the renderer is Direct3D 12 (feature level 11_0). No card of 2006-2008 has a D3D12 driver
  (GeForce 7/8/9, Radeon X1000/HD 2000-4000, every Intel GMA). The oldest that do: GeForce GTX 400/500 (2010, the
  slow "resource binding tier 1" path a player's GT 730 showed: 6-7x our translation and GPU time), Radeon HD 7000
  (2012), Intel HD 4400+ (2013). A 2006 PC needs a newer card.
- **Windows:** D3D12 means Windows 10. Core 2 runs Windows 10; Windows 11 24H2 needs SSE4.2 and POPCNT and does not
  start on any processor this build is for. The first Athlon 64 lacks CMPXCHG16B (no 64-bit Windows 8.1+ at all).
- **Memory:** 4 GB (0.8 GB working set for the game); BUILD GAME runs one compiler at a time there.
- **BUILD GAME:** the bundled clang-cl and Python are plain x86-64 programs (not checked instruction by instruction).
  The compile took 8-10 minutes on a 2-core stand-in at 57 % of this PC's core speed (branch toaster-018, docs/TOASTER.md); a 2006 dual
  core would need most of an hour.

## Shipping it (branch t5-oldhw-019)

- **Release zip:** `tools/package_release.py --prebuilt-host` builds the runtime twice from the same staged tree: the
  normal `runtime/t5dr.exe` exactly as before, and `runtime/sse2/t5dr.exe` + `t5dr.lib` with `-DT5DR_X86_BASELINE=ON`
  (checked with `tools/isa_audit.py --fail-on sse3,...,avx,aes`: nothing above SSE2 outside the C library's CPUID
  dispatch and the guarded `ppu_fma_hw`). Same file name in a subfolder on purpose: the game DLL imports from
  `t5dr.exe` by name. Signing (`code_signing.signable_files`) and the updater (whole `runtime` folder) pick it up as
  they are; `check_binaries.py` checks its imports and manifest, `smoke_release.py` wants it in the zip. The code ID
  and crossplay group hash it too.
- **BUILD GAME picks it:** `tools/build_game.py` `runtime_for_this_pc()` -> `choose_runtime()`: Windows'
  `IsProcessorFeaturePresent(PF_SSE4_1)` yes = normal (no further question, so a normal PC never starts anything
  extra); otherwise CPUID through the bundled clang (`-march=native`, `clang_has_sse41`), because Windows 10 before
  2004 answers "no" for feature 37 on every processor; no SSE3 at all = SSE2; unknown = normal (it then stops with
  its clear "too old" message, as before). `T5DR_RUNTIME=sse2|sse41` forces one (tests, a misread processor). On the
  SSE2 path `compile_game_dll` copies `runtime/sse2/t5dr.exe` to `build/cmake/t5dr.exe`, links against its
  `t5dr.lib` and runs `build_game_dll.py --simd sse2` (lifted SPU code without `-msse4.1`, lifted PPU code for the
  x86-64 baseline); the stamp `t5dr_build.json` gets `"runtime": "sse2"` (`"sse41"` on the normal path).
- **Launcher:** the Play tab asks for BUILD GAME when the stamp's runtime is not the one this PC needs (a folder built
  on another PC); the game log starts with `[launcher] runtime: normal (SSE4.1)` or `... SSE2 build ...`, and the SSE2
  runtime itself writes `[cpu] runtime: SSE2 build ...` (the problem report keeps both); a `[cpu] FATAL` from the
  normal runtime now says "press BUILD GAME again" when the release has the SSE2 one. **Check my problem** shows a
  hint with the expected speed instead of "too old" (`old_cpu`, kind hint) when `runtime/sse2` is there; its SSE4.1
  answer also asks CPUID when Windows says no.
- **Normal players unchanged:** patch 0126 leaves the SSE4.1 side of `spu_helpers.h` token for token as before (the
  three SSE4.1 wrappers are macros; `tests/test_sse2_runtime.py` `NormalBuildUnchanged` preprocesses the header with
  and without 0126 under every flag set the lifted SPU code gets: identical), and `build_game_dll.py` gets no new
  option on the normal path (`CompileStep.test_normal_is_unchanged`).

## Intel HD 2000-4000: why both games stop, and what a fallback would take (research only)

Nothing in our code blocks these chips by name (`launcher/gpu_support.py` only warns before BUILD GAME). T5DR asks
every hardware adapter for a Direct3D 12 device at feature level 11_0 (`rsx_live_draw.c` `ld_create_device`); with
no device the game ends with exit code 13 ("needs a graphics card with Direct3D 12"). Tekken 4 needs OpenGL 4.3 with
buffer storage and texture barrier and ends with exit code 4. The block is the driver, not a check of ours:

| Intel graphics | Generation | Direct3D 12 driver | Best Windows API the driver has | OpenGL (Windows) | T5DR | Tekken 4 | What a fallback would take |
|---|---|---|---|---|---|---|---|
| HD 2000 / 3000 | Gen6, Sandy Bridge (2011) | never | Direct3D 11 at feature level 10_1 (no compute shaders) | 3.1 | stops, exit 13 | stops, exit 4 | Neither planned path reaches it: a GL 3.3 backend (T5: 44-60 agent-days, `T5_GL_PLAN.md`; T4: 3-4 agent-days, `GL33_PLAN.md`) needs 3.3; a D3D11 backend at 10_1 is not costed (the owner ruled out DX11). Estimated 4-7 fps even then. Practical answer: a used GT 730 (Kepler) / GT 1030 / RX 550 card |
| HD 2500 / 4000 | Gen7, Ivy Bridge (2012) | never | Direct3D 11 at feature level 11_0 | 4.0 | stops, exit 13 | stops, exit 4 | T4: the GL 3.3 path (3-4 agent-days + a real HD 4000 PC). T5DR: a GL 3.3 backend (44-60 agent-days) or a D3D11 FL 11_0 backend (not costed, ruled out). Estimate 11-25 fps in fights |
| HD 4200-5000, Iris 5100/5200 | Gen7.5, Haswell (2013) | yes (feature level 11_1, resource binding tier 1), but Intel switched it **off** from driver 15.40.44.5107 (2021, a security fix); 15.40.42.5063 and older still have it | -- | 4.3 (4600) | starts only with the old driver; device losses seen on HD 4400 | "probably" (GL 4.3) | Nothing to build: say "older Intel driver needed, untested" honestly; the README now says so |

Sources: Intel's 2021 notice as reported by [Tom's Hardware](https://www.tomshardware.com/news/intel-disables-directx-12-on-haswell)
and [TechSpot](https://www.techspot.com/news/92098-intel-disabling-support-support-directx-12-4th-gen.html); the
GL/D3D levels per generation and the agent-day figures from `T5_GL_PLAN.md`, `GL33_PLAN.md` and `COMPATIBILITY.md`
(other branches). No Intel HD PC was used here. WARP (Windows' software Direct3D 12, `RSX_ADAPTER=warp`) is not a
fallback for these PCs: it draws on the same processor the game needs, which on a Sandy/Ivy Bridge 2-4 core is
already the limit.

### Measured on branch t5-oldhw-019 (development PC, 2026-11-11)

- **Normal runtime unchanged:** the prebuilt runtime (`-DT5DR_GAME_DLL=ON`, static C runtime, as `package_release.py`
  builds it) from `release-123-final` `b43edf2c` + patches 0001-0125 and from this branch + 0126, same paths, same
  clang-cl 23.1.3: `t5dr.exe` 4,268,032 bytes both, **byte-identical** once the link time stamp is zeroed; `t5dr.lib`
  identical (also to the SSE2 runtime's: the game DLL links the same imports either way).
- **SSE2 runtime:** 4,252,672 bytes; `tools/isa_audit.py --fail-on sse3,ssse3,sse4.1,sse4.2,popcnt,lzcnt,bmi,movbe,avx,aes`
  exit 0 (every such instruction sits in the static C runtime's CPUID-dispatched objects; `tzcnt` = `rep bsf` in 4 of
  ours, harmless). The SSE2 game DLL (`--simd sse2`): no SSE3..SSE4.2/BMI/LZCNT/POPCNT/MOVBE, 8 VEX instructions =
  the CPUID-guarded hardware fma `ppu_fma_hw` (as in the probe; this DLL has no map to attribute them).
- **Cost of shipping it:** zip +1.74 MB (the two files at the release's deflate level 9; the 1.2.3 player zip was
  98.2 MB), unpacked +4.26 MB; release build +23 s (one more runtime build, -j 8 on this PC: 23-24 s each). The
  player's BUILD GAME on an SSE2 PC: same steps, the DLL compile took 40 s vs 41 s normal here (10 jobs); the SSE2 DLL is
  38.3 MB vs 37.1 MB. A normal PC asks Windows once and starts nothing extra.
- **BUILD GAME on a stand-in processor:** `T5DR_TEST_CPU_MODEL=core2` (LLVM's Core 2 "Merom", no SSE4.1) in the
  release-like tree -> "runtime: SSE2 (runtime\sse2, ...) -- this processor has no SSE4.1 (CPUID)", `build/cmake/t5dr.exe`
  = `runtime/sse2/t5dr.exe`, `--simd sse2`, PPU code `-march=none`, stamp `"runtime": "sse2"`, 0 PGO warnings.
- **Boot to a fight with that build** (fight_bench, Lili vs Asuka, stage 20, 30 s window, below-normal, muted, ~4.6
  processors of other load): `[cpu] runtime: SSE2 build ...` in the log, FIGHT START at frame 1074, 59.93 fps, frame
  p99 18.7 ms, game thread median 3.30 ms (all 32 processors, so the worker threads spin: the 27.5 ms of all
  threads per frame are not comparable with the 4-core figures above; no speed claim from this run).
- **Cross pair, as players would meet** (`tools/cross_build_test.py`, from the release-like tree): host = normal
  runtime + normal DLL (x86-64-v3), joiner = SSE2 runtime + SSE2 DLL (`-march=none`, without FMA3:
  `PS3_FP_SOFT_FMA=1 PS3_CRT_FMA3=0`), RTT 50 / jitter 5 / loss 3 %, two matches per mode: rollback 9,036 frames,
  lockstep 9,021 frames, **0 different**, the same result hashes on both sides (rollback a6df8692.. / 7b5919ce..,
  lockstep 2153f75c.. / b98364dc..); the joiner's log starts with `[cpu] runtime: SSE2 build ...`.

Not done: a start on a real processor without SSE4.1 (none here); a full `package_release.py --release` run (the zip
figure above is the two files compressed alone); the six SSE2 ps3recomp suites (`tests/run_ps3recomp_tests.py`)
were not run again after the SSE4.1 wrappers became macros (the SSE4.1 side is token-identical to before 0126, the
SSE2 side unchanged from the probe, where they passed). `tests/test_sse2_baseline.py` including `Bits` (33 operations,
400,000 operand sets, SSE4.1 vs SSE2 builds) passed again on this branch's tree.
