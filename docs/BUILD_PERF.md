# Build settings for the game's CPU per frame (branch `cpu-build-opt`)

The weak-PC study (docs/WEAK_PC.md, branch `weakpc-fps`) found that players
at 40-50 fps are held back by one processor core's speed: the game part of a
fight frame is 5-6 ms on this PC's fast cores, 8-10 ms on slower or shared
ones, plus 2.2-3.8 ms of translation. This branch makes the game's own CPU
work per frame cheaper with **build settings only** -- nothing in the game's
code or behaviour changes.

**What ships:** BUILD GAME compiles the lifted code (the part every player
compiles from their own game, `t5dr_game.dll`) with a **profile** of where a
fight spends its time: clang's profile-guided optimisation (PGO), the profile
`tools/gamedll/t5dr_lifted.proftext` split into four parts. The game's main
thread needs **~3 % less CPU per frame on the 1.1.2 runtime and ~6 % less on
a runtime with patch 0061** (where the lifted code is ~83 % of the main
thread's busy time); BUILD GAME's compile got ~15 % faster and the DLL 17 %
smaller. Players with different builds stay in sync. Everything else tried
gave nothing measurable (table below).

## How it was measured

Two tools, both on the release path (prebuilt runtime `t5dr.exe` + the
player's `t5dr_game.dll` built by `tools/build_game_dll.py`), x86-64-v3,
two cores / four threads per game, below-normal priority, muted:

- **Re-simulation benchmark** (the main number): the rollback test mode
  (`T5_RB_MODE=test`, docs/ROLLBACK.md) restores a fight state every 60 frames
  and re-runs 30 frames back to back from it with scripted input, draws
  included, no vblank wait. Every build re-runs exactly the same frames, so the
  main thread's CPU cycles per re-simulated frame ("RESIM done ... Mcycles/frame")
  compare like for like, rollback by rollback (~35 per 75 s run). Builds run at
  the same time on the least loaded cores (picked per rep), rotated over the
  core groups rep by rep; the result is the median ratio per rep and its
  geometric mean over 6 reps.
- **Live fight** (`tools/fight_bench.py`, weakpc-fps version): Lili vs Asuka,
  stage 20, P1 attacking, window fight start +24..42 s; fps and frame times
  from the presents, game part and translation per frame from the latency
  probe (`PS3_LATENCY_LOG`: B -> F, F -> X), CPU per frame of each thread.

This PC was shared with other agents the whole time: 10-25 of its 32 logical
processors busy, among them busy loops pinned to single processors. A live
fight swings by +-20 % from run to run under that; the re-simulation ratios
stay within a few percent, which is why they carry the decisions.

## What was tried

Re-simulation benchmark, main-thread CPU per re-simulated frame, ratio to the
plain build (lower is better; per-rep medians, geometric mean of 6 reps):

| setting | 1.1.2 runtime | runtime with 0059 + 0061 + `-mcx16` | verdict |
|---|---|---|---|
| **PGO, front-end instrumentation, profile in four parts** | **0.972** (0.957-0.991) | **0.941** (0.904-0.987) | **shipped** |
| the same + ThinLTO across the 15 lifted chunks | -- | 0.951 (0.922-0.976) | no extra gain; the link becomes one 40-60 s step |
| PGO in two parts (PPU / all SPU) | 0.973 | -- | the skinning jobs got slower (below) |
| PGO in two parts + ThinLTO | 0.963 | -- | |
| PGO in four parts + `-hot-cold-split` | 0.974 | -- | no extra gain |
| PGO in two parts, cold call sites inlined as usual (`-inline-cold-callsite-threshold=325`) | 0.980 | -- | no gain |
| PGO, IR instrumentation (`-fprofile-generate`) | 0.998 | -- | no gain; its function hashes follow the IR after early inlining, so a profile made on an AVX2 build would not fit a baseline one |
| ThinLTO alone | 1.009 | -- | no gain |
| `-O3` instead of `-O2` | 0.996 | -- | no gain |

Not benchmarked, decided from the code:

- **`-march`.** Players' DLLs are x86-64-v3 when the CPU has AVX2, else the
  x86-64 baseline (unchanged). An x86-64-v2 (+`-mmovbe`) level for CPUs
  without AVX2 would change nothing: the instruction mix of a lifted chunk
  is within 0.3 % of the baseline build's, and v3's within 0.7 %. Guest loads
  are relaxed atomics (single-copy atomicity, patch 0013) and LLVM never folds
  those into `movbe` -- the old "v3 is 25-30 % faster" came from before that.
  Nothing requires AVX2.
- **`/GS-`** (stack cookies). The DLL build had it already; with `/GS` a lifted
  chunk gets 0 cookies anyway (the PPU registers live in the context, not in
  local arrays). The CMake build now passes `/GS-` for the lifted code too.
- **Function order, hot/cold splitting.** With a profile, clang already puts
  never-run functions into `.text$unlikely` and lld-link orders the rest by the
  profile's call graph (`.llvm.call-graph-profile`, on by default); block-level
  splitting (`-hot-cold-split`) added nothing (table).

**Why the profile is split.** LLVM sorts counts into hot and cold against the
whole profile it is given. The SPU sound core's inner loops run ~10^11 times
in a training run; next to them most PPU code fell under the "cold" cutoff and
was compiled for size, and the guest-memory helpers were no longer inlined:
4,385 out-of-line calls to `vm_read32_inl` in one chunk where the plain build
has none (`-Rpass-missed=inline`: "too costly to inline (cost=75,
threshold=45)"), 3 % of all main-thread samples in such calls, and the game's
draw-request thread 4-8 % slower than without a profile. The same happened to
the skinning jobs next to the sound core. Now each part is compiled against its
own profile: the lifted PPU code, the SPU sound core, the SPU skinning jobs,
the rest (`build_game_dll.prepare_profiles`). The four SPU images' sources are
all called `spu_recomp.c`, so each is compiled under its own name
(`-main-file-name <image>_spu_recomp.c`) to keep their helpers apart.

## Results

LIVE_TABLE

## Determinism

A profile changes which code the compiler emits (inlining, block order, size
or speed per block), never what it computes: `-ffp-contract=off` stays, no
fast-math or reassociation flag is involved, and the FP helpers of patch 0032
are unchanged. Proof with `tools/cross_build_test.py` (RTT 50 +-5 ms, 3 % loss,
three matches each: Asuka vs Lili stage 20, Lili vs Dragunov stage 24, Jin vs
Kazuya stage 26):

PAIR_TABLE

`tools/fp_audit.py --strict` on the DLLs: no estimate instructions, no x87, no
MXCSR writes, no C runtime math. (`tools/fp_vectors.py` is not on main; the
flags touch no FP code path.)

## The profile file

`tools/gamedll/t5dr_lifted.proftext`: 1.35 MB of text (183 KB in the zip),
7,540 records, each a function name, a structural hash of its source (which
kinds of statement it has, in order -- not what they do) and how often each of
its regions ran:

    ?func_00010200@@YAXPEAUppu_context@@@Z
    # Func Hash:
    854407558796376
    # Num Counters:
    5
    # Counter Values:
    6
    0
    ...

Names are lifted PPU functions (`?func_<guest address>@@...`), lifted SPU
functions (`<image>_spu_func_<address>`), the SPU images' register functions,
and the generated code's helpers (`ppu_recomp_003.cpp:?vm_read32_inl@@...`,
`bnuscore_spu_recomp.c:spu__nf_be`). No code, no data, no paths; value
profiling (indirect-call targets, copy sizes) is off when training.
`tools/profile_check.py` checks exactly this grammar. `tools/check_no_game_data.py`
and the release scan (`package_release.classify`) accept the file at that one
path only when the check passes -- their generic checks would refuse it (over
1 MiB, thousands of lifted names).

clang reads only LLVM's binary profile format, so the build converts the text
with `llvm-profdata.exe` (6.4 MB, from the same LLVM 23.1.3 as clang-cl, now in
`toolchain/llvm/bin`, 2.7 MB zipped; one more unsigned LLVM binary in the zip
for the VirusTotal check). Without it, or when the check refuses the file, the
build goes on without the profile -- the same game, a little slower. The
profile is part of the code ID (`build_game.py`, `CODE_VERSION` 4), so a new
one asks players to build again.

**Build time and size** (the lifted code, 23 files, 4 jobs, same PC and load):
plain 136 s (520 s summed over the files), with the profile 113 s (441 s) --
cold code is compiled for size, so BUILD GAME's compile gets ~15 % *faster*;
on a 4-thread PC with half this PC's per-core speed roughly 3.7 instead of 4.3
minutes. `t5dr_game.dll` 45.7 -> 38.0 MB (11.2 -> 8.7 million instructions).

## Training a new profile

The profile fits the lifted code it was trained on (names and hashes must
match). Patches that only change the runtime (0059, 0061 ...) do not touch it.
A change to the lifter's output or to the headers the lifted code includes
leaves the changed functions without profile -- still correct, just not
optimised -- so retrain then:

    python tools/build_game_dll.py --recomp build/recomp --spu build/spu --deps deps/ps3recomp \
        --host-lib <runtime>/t5dr.lib --out <bin>/t5dr_game.dll --pgo-gen        # instrumented, dev PC only
    python tools/pgo_train.py --bin <bin> --vfs game/vfs --out build/pgo-train     # 6 fights, ~8 min
    llvm-profdata merge --text -o tools/gamedll/t5dr_lifted.proftext build/pgo-train/t5dr_lifted.profdata
    python tools/profile_check.py

`--pgo-gen` links LLVM's profile runtime into the DLL (with the Windows SDK's
`ucrt.lib` / `kernel32.lib`); `tools/gamedll/pgo_train.c` supplies the few C
runtime pieces the DLL has no start-up for and writes the counters when
`pgo_train.py` asks (`T5_PGO_TRIGGER`). `pgo_train.py` plays six direct fights
(different fighters; stages 20, 24, 26, 28, 33, 34 for the stage effects),
75 s each with both pads mashing, three games at a time. The instrumented game
runs at ~15 fps; counts are per game frame, so that does not matter.
`build_game_dll.py --copt/--ldopt/--lto/--profile` stay for experiments; the
CMake build (`build_game.py --full-compile`) takes the four parts as
`T5DR_PGO`, `T5DR_PGO_SND`, `T5DR_PGO_SKIN`, `T5DR_PGO_SPU`.

## What is left

The compiler cannot do much more for this code. Every guest store is a relaxed
atomic store followed by a compiler barrier and a reservation check (patch
0013: single-copy atomicity, SPU lock lines), so the PPU registers in the
context are reloaded after every store, and loads never become `movbe`. That
is where the next real saving is -- a code change (for example plain accesses
where no SPU can hold a reservation), not a build setting.
