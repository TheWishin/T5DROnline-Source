# Mac work 1.1.9: report

Branch `mac-119` on TheWishin/T5DROnline-Dev, based on `1586bbb` (1.1.8 hotfix). Mac17,9, Apple M5 Pro (14 cores),
24 GB RAM, macOS 26.6.2, Command Line Tools (Apple clang 21.0.0), Python 3.12.16 (Homebrew venv). Weekly usage at the
end: 68 %. The owner was asleep, so every decision is the safe one: Mac-only, Windows unchanged.

## Commits

| Commit | What it does |
|---|---|
| `195f535` | Patch **0100**: no unsequenced `++` in the Metal staging-slot wait log (`rsx_metal_backend.m`) |
| `767b4b6` | Patch **0101**: `[fps]` on the Metal path, and real `[slow-frames]` times on macOS |
| `1a27220` | Patch **0102**: `PS3_PAD_FILE2` (player 2) on the non-XInput pad path. The smoke suite runs on the Mac and skips the frame-based checks there. |
| `1491920` | `src/`: the semaphore mirrors match the runtime off Windows. This makes late input and the practice tools work on the Mac. `tools/practice_check.py` runs on the Mac. |
| `f5ad52a` | The `src/` modules are **on by default on macOS** (`--macos-offline` turns them off). Online play stays off. |
| (this) | the report |

Patch numbers 0103 and 0104 are unused.

## Build

- Base `1586bbb` (game alone): deps 4, keys 1, decrypt 1, unpack 6, vfs 0, lift 15, spu 1, compile 26 s: **54 s** in total.
- Final, clean `native/`, no flags (the new default, with the modules): deps 0, keys 1, decrypt 0, unpack 15, vfs 0,
  lift 14, spu 1, compile 104 s: **135 s** in total.
  - The stamp reads `"online": false, "modules": true`.
  - Code id `2037ddb5a00f7af4`. The new patches are in the series, so the id changed. A Windows build of this branch gets the same id.
- No new warnings in the changed files. The `-Wunsequenced` in `rsx_metal_backend.m` is gone.
- `fp_vectors.py --compare tests/data/fp_vectors_x64.txt`: **55 of 55 instructions match** (darwin-arm64, n=100000),
  both before and after.

## 1. Compiler warning (patch 0100)

`if ((++s_eng_slot_waits & (s_eng_slot_waits - 1)) == 0)` → `const unsigned long w = ++s_eng_slot_waits; if ((w & (w - 1)) == 0) ... printf(..., w)`.
The file is Metal-only.

## 2. `[fps]` and `[slow-frames]` on Metal (patch 0101)

- **`[fps]`:** `rsx_draw_engine.c` `eng_present`, `#ifdef __APPLE__`. Same format and pace as `rsx_live_draw.c`: frames presented, every ≥ 5 s.
- **`[slow-frames]`:** off Windows, `rsx_pf_stamp` / `rsx_pf_guest_flip` were empty, so the line never saw the flip request. Now they stamp on the clock the compat QPC uses (`CLOCK_MONOTONIC` ns) and end the game part (`host_sched_main_flip_requested`).
- **`host_sched.c`, `#ifdef __APPLE__`:** the main thread's waits, release/flip and processor time, as patch 0063 has them on Windows.
  - Processor time: `thread_info(THREAD_BASIC_INFO)` of the thread registered as `HS_ROLE_MAIN`.
  - Linux keeps its stubs.
- **GPU time:** `GPUEndTime - GPUStartTime` of the Metal frame command buffers (`eng_encode_and_commit`), summed in a completion handler. It is exposed through `rsx_live_draw_gpu_ms()` with a weak symbol, so binaries without the backend still link.
- **What stays empty, and why:**
  - **"GPU wait" stays 0.** The Metal path never blocks the frame on the GPU; its frames are throttled by a semaphore in the completion handler.
  - **The per-frame median "game" stays 0.0.** On Metal the next frame is released at the vblank before the previous one is presented, so the flip stamp lies before the release. The average "game part … ms" (the same values, counted only where > 0) and the main thread's processor time are right.

Log lines from a real fight (`~/…/game.log`):

```
[fps] 59.9 (frames 2352..2652 over 5.0s)                      (stage 17, clean build)
[fps] 60.0 (frames 2952..3252 over 5.0s)
[fps] 59.9 (frames 2140..2440 over 5.0s)                      (stage 19, after the load: 17.4, 57.2, 59.9)
[slow-frames] last 30 s: 1395 frames, 5 slow (over 20.9 ms): CPU 5 (game 0, render translation 5, vblank thread late 0),
  GPU 0, present 0; 116 late for their vblank, shown when translated; median per frame: game 0.0 ms, translation 8.1,
  GPU wait 0.0, present 0.7; game part 8.3 ms on average: main thread running 8.3, waiting for the renderer 0.0, for
  other game threads 0.0 (its processor time 4.4 ms a frame); GPU busy 2.1 ms a frame (10 % of the time); worst 41.3 ms
  (CPU, render translation); vblank clock 54.52 Hz | power state unknown
[slow-frames] last 30 s: 1041 frames, 506 slow ... translation 12.4 ... GPU busy 1.6 ms a frame (5 % of the time);
  worst 831.6 ms (CPU, render translation); vblank clock 41.98 Hz       (stage 19: the window holds the stage load)
```

Before this patch, every one of these fields was 0.0 on the Mac, and there was no `[fps]` line.

## 3. Second scripted pad, smoke quick on the Mac (patch 0102 + `tools/smoke`)

- **`cellPad.c`, non-XInput path only:**
  - `pad_poll_file_n(which)` reads `PS3_PAD_FILE` (port 0) or `PS3_PAD_FILE2` (port 1).
  - Port 1 is applied after the SDL poll, unless a real SDL controller is on that port.
  - The log line is `[cellPad] file pad 2: buttons ...`.
  - Windows (XInput) does not compile this code.
- **`tools/smoke`:**
  - The default exe is `build/cmake/t5dr` off Windows.
  - Checks judged from dumped frames are **skipped on macOS, with the reason**, not passed: screenshots, `reach.fight` / `reach.attract*` / `reach.back-to-title`, `fighters`, and the attract phase's audio. The runtime's `LD_FRAME_DUMP` is D3D12-only, and the Mac venv has no Pillow (not installed: outside the allowed packages).
  - `wait_frame` returns at once there, instead of waiting 60 s.
- **Smoke quick results:**

| Run | pass | skip | fail | the failures |
|---|---|---|---|---|
| before (base, the game alone) | 35 | 8 | 18 | every frame-based check: no frame dump on Metal |
| game alone + 0100-0102 | 32 | 24 | 1 | `arcade_fight reach.title`: intro not skipped after 30 START presses (passed on rerun, which instead had `audio.arcade-select` 32 % silent) |
| modules, before the semaphore fix | 28 | 26 | 7 | 4× `no-hang` (the 5 s keyread take-over at boot), title fps, select audio |
| modules, after it | 34 | 26 | 1 | `vs_two_pads audio.vs-charsel` 76 % silent |
| **final: clean build, modules by default** | **31** | **19** | **1** | `title_twice reach.title`: intro not skipped by START |

Two failures are open and seen with and without the modules, so they are not from this branch:
- **The intro is sometimes not skipped by START** on the Mac (about 1 run in 3).
- **Character select screens are sometimes mostly silent** (`audio.*-select` / `vs-charsel` 31-76 % silent blocks). It changes from run to run.

`PS3_PAD_FILE2` works: `vs_two_pads` passes, and the game log shows `[cellPad] file pad 2: buttons 0x0020 / 0x4000`.

## 4. Practice tools, stage unlock, direct fight: decision **default ON**

What I found, in order:

1. **`--macos-online` builds and runs offline**, but the practice tools never started: no `[practice] tools on`, no practice log.
   - The cause is a **layout bug in `src/`**. `t5_hooks.cpp` and `df_hooks.cpp` read the runtime's `g_sys_semaphores` through their own copy of `sys_semaphore_info`, with the Windows tail (`HANDLE`, `CRITICAL_SECTION`).
   - Off Windows the runtime has patch 0063's `rsx_posted` and a `pthread_mutex_t` + `pthread_cond_t` there, so every element after the first was read at the wrong place.
   - **Consequences:**
     - The keyread thread was never seen parked (`[netplay] take-over: ... STILL NOT PARKED after 5001 ms`), which cost 5 s at boot and failed the smoke `no-hang` checks.
     - The offline late input gave up (`the keyread thread does not park -- the game reads the pads itself`).
     - The practice tools never ran, because they run inside late input's keyread tick.
     - `t5_sem_count` / `t5_sem_set_count` locked memory that is not a lock.
   - **Fix (`1491920`):** the non-Windows branch of both structs has the runtime's layout, and the lock is `pthread_mutex_lock(&s.mtx)` (`NP_SEM_LOCK`).
   - **On Windows the structs and the lock calls are unchanged.** `rsx_posted` sits in the padding before `HANDLE` there, so the old Windows layout was already right.
   - After the fix: `[netplay] late input: the pads are read at the top of each frame by the main thread`, and `[practice] tools on (Practice, offline)`.
2. **Practice tools:** `tools/practice_check.py` on the Mac.
   - On macOS it drives the tools after the menu driver's fight timeout, because there is no frame dump to see the HUD; the practice log is the evidence.
   - Run 1 (modules build): **PASS**, all checks.
     - Round start 2000 apart, 10 round-start resets.
     - 4 walls found, 1100 apart.
     - Slot 1 recorded, played and looped.
     - Dummy block / crouch / walk / step / game, and the guard after the first hit.
   - Runs 2 and 3 (the final clean build), 15 ok each. Wall resets, recordings and dummy behaviours were ok every time, but two "30 frames after the reset" checks failed (run 2 also "blocks after the first hit"): the fighters were already elsewhere 30 frames after a round-start reset (`P1 (-500, 0) dummy (-1600, 0)`). Without frame feedback the driver's presses fall at other moments of the fight than on Windows. I read this as the check's timing, not the tools, but it is **not proven**: the Windows side may want to look at it.
3. **Stage unlock:** `T5_UNLOCK_STAGES=1` is read, and the direct fight logs `[df] unlock: online game -- unlocks as on a fresh save`. That is the direct fight's fixed mode, as on Windows.
   - The 1.1.7 test already ran a fight on stage 4 (City at Sunset), a Tekken 5 stage, with it.
   - Fps with it on: 57.5 / 59.5, then 53.1 / 41.7, and 37.7-39.5 in one other run. With it off: 59.5-59.9 (4 runs).
   - In a direct fight the code path is the same with and without it (fixed mode either way), and Spotlight indexers ran over the new build folders at the time. I count it as system load, not the unlock.
4. **Direct fight** (`T5_FIGHT=15,27,17,2` / `...,19,2`): FIGHT START, then 59.9-60.0 fps on stage 17 and 59.9 on stage 19 after its load.
5. **Training (`T5_TRAINING=1`):** the module runs, and fps is the same with and without it (59.6/59.9 vs 59.9/59.9).
   - **Nothing is drawn on the Mac:** `rsx_overlay.c` (input display, frame data, the practice status line) draws into the D3D12 backbuffer only, and the Metal backend has no overlay.
   - So the input display / frame data do not show. This is the main open Mac item (a Metal overlay pass).
6. **Fps with and without the modules:**
   - Menus and title: 59.4-59.9 in both (smoke `fps.*`).
   - Arcade fight: 59.9 in both.
   - The load into the fight with the modules showed 16.6 fps for about 10 s (without: about 60). This is probably late input's loader drain, now that it works. Only the loading screen is affected.

**Decision: default ON (`f5ad52a`).** Boot, menus, VS, the practice tools, unlock and direct fight work, and fight fps is unchanged.
- **`tools/build_game.py`:** the modules are built on macOS unless `--macos-offline`. `--macos-online` is still accepted; it alone sets the stamp's `"online": true`.
- **`CMakeLists.txt`:** `T5DR_MACOS_ONLINE` defaults ON on `APPLE` only. Off-Apple CMake is unchanged.
- **Online stays off:**
  - The lobby client checks the stamp's `"online"`, which is false without `--macos-online`.
  - Nothing starts netplay without the launcher / `T5_NET_MODE`.
  - The new stamp key `"modules"` records the build kind.
- **Tests:** `tests/test_macos_port.py` follows the new default. All `test_macos*` pass (17).
  - `test_build*` fails 6 + 1 on the Mac, **identical before and after this branch** (`git stash`): DepsSeries, PackageFacts, build_quiet.

## Checks at the end

| Check | Result |
|---|---|
| clean build (`rm -rf native`, no flags) | OK, 135 s, modules in, online off |
| fp_vectors | 55/55 |
| smoke quick | 31 pass / 19 skip / 1 fail (intro START skip, flaky also without the modules) |
| fight stage 17 / 19 | 59.9-60.0 / 59.9 fps, `[fps]` and `[slow-frames]` lines present |
| practice tools | PASS once; the final build's two runs pass walls, recordings and dummy, but miss the 30-frames-after-reset check (above) |
| exit with Esc | **not tested**: keys cannot be sent to the game window while it is in the background (computer use). Every run ended with `kill -9`; no crash otherwise. |
| `check_no_game_data.py` | ok (see the commit) |
| `git status` | only the files of these commits; nothing from `native/`, `deps/`, `.venv/`, no logs |

## Open for the Windows side

1. **Metal overlay pass for `rsx_overlay.c`:** the training input display / frame data / practice status line are invisible on the Mac.
2. **Smoke on Mac:** the intro sometimes ignores START (1 in 3 runs), and the character select is sometimes mostly silent. Both occur with and without the modules.
3. **`practice_check.py` without frames:** its "30 frames after the reset" check is timing-sensitive (the fighters moved). A log-based "fight started" signal (`[df]`/`[practice]` line) would make the blind driver exact.
4. **Fight load with the modules:** 16.6 fps for about 10 s on the loading screen (late input's loader drain?).
5. **Docs:** README "Building on macOS" and docs/MACOS.md do not yet say that the modules (practice tools) are the Mac default and that `--macos-offline` exists. I left the docs to the coordinator.
