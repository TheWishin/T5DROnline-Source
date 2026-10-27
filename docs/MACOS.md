# macOS port: inventory, plan and groundwork

## Status 1.1.5 (2026-10-27)

- **Offline play on Apple silicon works**: n0madic's port (ps3recomp patches
  0071-0073: Metal renderer fixes, SDL2 audio and pads, VideoToolbox movies,
  the guest main thread on a 256 MB pthread; `tools/build_game.py` builds on a
  Mac). The owner played it on an M5 Pro / macOS 26.
- **Online play is prepared, and off by default** (branch `macos-online-115`):
  `src/` (netplay, rollback, direct fight, training, perf) builds on macOS
  through the platform layer described below, but only in a build made with
  `tools/build_game.py --macos-online` (CMake `T5DR_MACOS_ONLINE`, default
  OFF). The lobby client refuses to start a match with a Mac build that lacks
  it. A Mac offers rollback only with `T5_MACOS_ROLLBACK=1`, so the first
  Mac-vs-PC matches run in lockstep. **Nothing of it has run on a Mac yet**:
  docs/MACOS_ONLINE_TEST.md is the owner's step list; online on a Mac stays a
  test build until a Mac-vs-PC match ends with 0 mismatching frames.
- Done since the study below (ps3recomp patch 0078 and `src/`):
  - the square-root NaN: the **Mac now produces the PC's bits** (default NaN
    with the sign set) instead of both moving to the PS3's -- so nothing a PC
    computes changes and no CODE_VERSION bump is needed. An empty asm keeps
    clang from folding the choice back into a plain `fsqrt` (it did, at -O2);
    `tests/test_macos_port.py` checks the arm64 code for it;
  - the FPCR check on arm64 (`ppu_fp_env_check`, `ppu_fp_thread_init`: FPCR 0,
    restored and logged when something changed it);
  - `-ffp-contract=off` for all of t5dr on a Mac (the runtime library and the
    lifted code had it already);
  - entry detours without code patching: the lifter's `--hook-slots` (every
    function on `src/rollback/hook_slots.txt` calls the hook in its slot, if
    any, before its body `func_X__orig`); `rb::detour` stores into the slot.
    One difference to a patched entry: a slot also catches calls the compiler
    inlined, which a patched entry on Windows would miss. The detours the
    lockstep uses (the TLS random generator 0x3AFC3C, the scene and sound
    tasks, the unlock check) have no caller in their own translation unit, so
    nothing can have been inlined there; some rollback-only targets (sound
    library calls, the draw cut's 0x0A25A8 / 0x35D894, the sound heap's
    malloc) and diagnostics do -- worth a look if a rollback pair differs;
  - the write watch's kernel writes: `ppu_fs.cpp`/`sys_fs.c` read files into
    guest memory through a host buffer off Windows (a `read(2)` into a
    protected page fails with EFAULT instead of faulting);
  - netplay's local input on the SDL2 backend (`cellPad_sample_local` returned
    "no device" off Windows: a Mac player's input never left the machine);
  - BSD sockets, monotonic clocks, POSIX files and thread names in `src/`;
    the loader-drain semaphore peeks are acquire loads off Windows.
- Still open: the write watch's cost on a Mac (16 KB pages, a signal per first
  write), rollback Mac vs PC, the renderer gaps and packaging below.

What follows is the study of 2026-10-19; its "Recommended order" and "What
the owner needs" still hold.

---

Status 2026-10-19, branch `macos-port`. **No Mac was used.** Everything below
that says "verified" was verified on the Windows development PC; everything
else is a plan or a prediction and says so.

## In short (for the owner)

- The game can come to the Mac. The hardest part is the picture: the Windows
  renderer (D3D12 "live draw") holds most of our render fixes, and the Mac
  renderer (Metal, from ps3recomp) has none of them yet.
- Online play Mac against PC is possible, but only if both compute exactly the
  same numbers. On Apple Silicon three floating-point instructions are expected
  to give a different "not a number" bit pattern than on a PC (details below).
  That is a small fix in the lifter, but every player must get it in the same
  release.
- Build the Mac version for Apple Silicon (M1 and newer). Intel Macs are old
  and Apple drops them; an Intel build is only useful as a test tool.
- Rough size: 70-100 agent-days, 8 to 12 weeks with two agents, once a Mac is
  available (table below).
- What the owner must provide: a Mac with Apple Silicon that an agent can use,
  and a decision about the Apple Developer Program (99 USD a year) for signing.
  Without it the game still runs, but every player has to allow it by hand in
  System Settings. Nobody creates that account except the owner.

## What this branch already does (verifiable on Windows)

| change | what | how it was checked |
|---|---|---|
| `src/platform/t5_win.h` | every file in `src/` includes this instead of `<windows.h>`. On Windows it *is* `<windows.h>`; on macOS/Linux it is ps3recomp's POSIX shim for the Win32 subset the runtime already uses (`runtime/platform/win32_compat.h`: QPC, Sleep, events, threads, critical sections, SRW locks, VirtualAlloc/Protect/Query, vectored exception handlers; `msvc_compat.h`; `win32_backtrace.h`) | `tests/test_macos_port.py`: no host header outside `src/platform`; every Win32-style call outside a Windows-only block exists in the shim or in `t5_plat.h` (lint fails on a reintroduced `GetWriteWatch`, checked) |
| `src/platform/t5_plat.h` | the rest of the host, one function per job: write watch (`t5p_write_watch*`), code patching for the rollback detours (`t5p_code_*`, `t5p_exec_alloc_near`, `t5p_icache_flush`), file replace / stamp / shared read, process exit, OS environment, module of an address, cycle counters, FP control word, `T5P_SEP`, `T5P_CTX_PC` | Windows: static inline wrappers around the exact calls made before. Object-code comparison of all 23 `src/` objects before/after: **3,503 of 3,522 functions identical instruction for instruction**; the 19 others are the edited call sites (register choice, one log string) |
| `src/platform/t5_plat_posix.c` | the POSIX half: write watch by page protection (below), `rename`, `stat`, `dladdr`, `dlopen(RTLD_NOLOAD)`, `clock_gettime`, `mprotect`, `sys_icache_invalidate`, FPCR/MXCSR | `clang -fsyntax-only -Wall -Wextra -Werror` for `arm64-apple-macos12`, `x86_64-apple-macos12`, `x86_64-linux-gnu` against `tests/posix_sysroot` (declaration-only headers written for this; they keep the macOS/glibc differences that matter, e.g. `st_mtimespec` vs `st_mtim` -- a test proves a wrong one is caught). **Not run on a Mac.** |
| `src/platform/t5_sock.h` | UDP for the netplay transport: Winsock / BSD sockets (`netplay_core.cpp`) | same syntax check; Windows object code identical except the edited sites |
| `CMakeLists.txt` | `-ffp-contract=off` and `-march` passed in the right spelling for clang-cl and for clang; off Windows: shim include path, `_GNU_SOURCE`, `t5_plat_posix.c` | Windows: `build.ninja` flags/defines/includes identical before and after |
| Windows-only diagnostics | the stack sampler (`rb_sample.cpp`: SEH, `RtlVirtualUnwind`) and the write-fault tracer (`rb_wft.cpp`: x86 trap flag, 4 KB page protection) compile to stubs elsewhere | lint + Windows objects identical |
| `tools/fp_vectors.py` + `tests/data/fp_vectors_x64.txt` | lifts one real instruction word of each of 55 PPU scalar-FP and VMX-float instructions with `ppu_lifter.py`, runs 100,000 operand sets each (NaN payloads, signalling NaNs, denormals, conversion edges, random bits), prints a digest per instruction | x86-64 Windows: baseline, x86-64-v3 (FMA3) and software-fma builds all match the reference, 55/55 (`tests/test_fp_vectors.py`). On a Mac it names every instruction that differs from a PC. |

Regression proof for Windows (2026-10-19, this branch's `t5dr.exe`): tests/
pass, smoke quick PASS, rollback pair in sync (numbers in "Evidence" at the end).

## Inventory: every Windows-only dependency

Effort = agent-days with a Mac available, including tests. "ps3recomp has" =
what the pinned runtime (f17bcd3 + our patch series) already carries for
macOS/POSIX.

| area | Windows today | ps3recomp has for macOS / POSIX | Mac work | effort |
|---|---|---|---|---|
| **Renderer** | `rsx_live_draw.c` (13,100 lines, D3D12; our patches 0005/0010/0023/0027/0034/0035/0038 added ~3,460 of them; 138 env knobs). Off Windows the file is a no-op stub. | `rsx_metal_backend.m` (3,900 lines) driven by `rsx_draw_engine.c` (2,200 lines, a platform-neutral port of live draw's orchestration *before* our patches); guest shaders NV40 -> HLSL -> SPIR-V (glslang) -> MSL (spirv-cross) at run time. Upstream's v0.12 notes credit a Yakuza port running on macOS with it; upstream's own platform table still says macOS does not run a game. | port our live-draw fixes into the engine + Metal backend (table "Renderer" below), pacing via `CAMetalDisplayLink`, shader/pipeline cache, frame dumps for the smoke suite | **20-30** |
| **Window, DPI, fullscreen** | Win32 window in `rsx_null_backend.c` (patch 0021: background/minimized start, Alt+Enter/F11 borderless, exclusive, letterbox, close = exit 7), per-monitor DPI manifest | `NSWindow` + `CAMetalLayer` in the Metal backend, keyboard via `NSEvent`; it calls `activateIgnoringOtherApps` (steals focus) and `dispatch_sync`s window work to the main queue | AppKit must own the **main thread**: the guest main thread moves to a pthread (see Threads); `PS3_WINDOW_BACKGROUND` = miniaturized, no activation; native fullscreen (Spaces) or borderless; Retina: `contentsScale` = `backingScaleFactor`; close = exit 7 | 3-4 |
| **Pads** | `pad_host_win32.c` (2,540 lines): controls.ini, bindings, presets, macros, SOCD, 1 ms sampler + tap latch, `PS3_PAD_FILE` scripts, XInput, DirectInput 8, DS4/DualSense HID reports (patch 0042), keyboard, hot-plug, Steam Input rules; works unfocused | `cellPad.c` SDL2 GameController path (4 pads, no controls.ini, no tap latch); the netplay API `cellPad_sample_local` returns "no device" off Windows | split the file: ~60 % is host-neutral (ini, bindings, latch, scripts, the DS4/DualSense report parser) -> `pad_host_common.c`; new `pad_host_mac.c`: GameController.framework (Xbox, PlayStation, Switch pads; `shouldMonitorBackgroundEvents` for unfocused input), IOHIDManager for arcade sticks/hitboxes and raw DS4/DualSense reports, keyboard from the window; `cellPad.c` gates on "has pad_host" instead of `_WIN32` | 6-8 |
| **Audio** | WASAPI in `cellAudio.c` (patches 0003/0026/0029/0041): own device thread, retry every 2 s, default-device change, format conversion, 50 ms buffer, mixer on its own QPC clock (187.5 blocks/s with or without a device), `PS3_AUDIO_MUTE`, health line | SDL2 audio path with a simpler mixer loop (none of the above) | CoreAudio (AudioUnit HAL output) behind the same device-thread design; device change via `kAudioHardwarePropertyDefaultOutputDevice` listener; the mixer clock stays independent (netplay/rollback must not see the device) | 3-4 |
| **Movies** | Media Foundation H.264 (`mf_h264.cpp`, patch 0006; delay-loaded) | stub: "unavailable", movies are skipped | VideoToolbox `VTDecompressionSession` (Annex B -> AVCC); or ship without intro movies first | 2-3 (optional) |
| **Threads, priorities, affinity** | `host_sched.c` (patch 0015/0027): roles -> priorities, MMCSS, CPU sets, power throttling, `PS3_CPUS`, waitable-timer sleeps, sub-ms spin budget | `host_sched.c` is a no-op off Windows; threads are pthreads through the shim | QoS classes (`QOS_CLASS_USER_INTERACTIVE` for main/ticker/audio/sound core keeps them on P-cores), `THREAD_TIME_CONSTRAINT_POLICY` for audio; no affinity on Apple Silicon (ignored) -- `PS3_CPUS` from `hw.perflevel0.logicalcpu`; 256 MB guest main-thread stack: macOS caps the main thread's stack (8 MB default, hard limit ~64 MB), so the guest main runs on a pthread with a 256 MB stack | 2-3 |
| **Timers, waitable objects** | QPC, `timeBeginPeriod(1)`, events/semaphores/waitable timers, `WaitForMultipleObjects` | all in `win32_compat.c` (pthread/condvar based; upstream builds and tests it on arm64 macOS, `tests/sync_stress` is its memory-model net) | timing check only: `nanosleep`/`mach_wait_until` are already fine-grained; vblank ticker accuracy measured on the Mac | 1 |
| **Guest memory** | 4 GB `VirtualAlloc` reservation, vectored handler commits 64 KB on first touch, `MEM_WRITE_WATCH` when rollback is on (`boot_main.cpp`) | `calloc(0xE0000000)` (3.5 GB, not page aligned on glibc, no watch) | `mmap(4 GB, MAP_ANON\|MAP_PRIVATE\|MAP_NORESERVE)`: lazily zero-filled like the Windows commit-on-touch, host-page aligned (the write watch needs it) | 1 |
| **Rollback write watch** | `GetWriteWatch`/`ResetWriteWatch` (kernel dirty bits, 4 KB) | nothing | `t5p_write_watch` in `t5_plat_posix.c` (written, not run): read-only pages, fault -> mark + unprotect, reset = protect + clear; race-safe ordering documented in the file. Apple Silicon pages are 16 KB: a dirty 16 KB page is reported as four 4 KB pages. Kernel writes (`read(2)`/`recv(2)` into guest memory) do not fault, they fail with `EFAULT`: the runtime's file and socket HLE must call `t5p_write_watch_touch` on the destination first (`sys_fs.c:475`, `cellFs.c:499`, `ppu_fs.cpp:815`, `sysNet.c:467,485`, `cellSaveData.c:733`; libc `fread` of a large block goes straight to `read(2)`) | 3-4 |
| **Rollback entry detours** | `rb_detour.cpp` rewrites the first bytes of lifted x86-64 functions (sound play/stop detours of phase 10, the direct-call cut of patch 0034, call tracer) | -- | arm64: different encoding, and a notarized app may not write its own code pages. Replace with **hook slots the lifter emits**: for the listed guest addresses `func_X` starts with `if (ppu_hook[N]) return ppu_hook[N](ctx);` -- no code patching on any platform; `detour()` keeps its signature. Until then `detour()` refuses on arm64 (this branch) | 3-4 |
| **Exceptions, crash reports** | vectored handlers, `SetUnhandledExceptionFilter`, stack-overflow report, `RtlCaptureStackBackTrace` | shim maps vectored handlers onto `sigaction` (SA_ONSTACK, but no alternate stack is created), `backtrace(3)` | `sigaltstack` per thread for stack-overflow reports; crash line format kept for `tools/hang_watch.py` | 1-2 |
| **getenv cache + session overlay** | `boot_main.cpp` replaces the CRT's `__imp_getenv` import slot (a PE linker trick) | none (plain `getenv`) | define `getenv` in the executable (the static runtime binds to it); the game module resolves against the host (`-bundle_loader`) | 1 |
| **Game module (player builds the lifted code)** | `t5dr_game.dll` built on the player's PC with bundled clang-cl + lld-link, no Visual Studio (patch 0020, `tools/build_game_dll.py`, `t5dr_host.def`) | -- | `t5dr_game.dylib` with bundled clang + `ld64.lld` (ad-hoc signs arm64 output), linked against the host with `-bundle_loader`; the signed host needs the `disable-library-validation` entitlement to load a locally built, unsigned library; no Apple SDK may be redistributed, so the dylib links no system library (a small text `.tbd` stub of what it imports) | 3-5 |
| **File paths** | VFS under `game/vfs`, saves `./gamedata`, logs/scratch in the cwd, UTF-8 code page manifest (patch 0031), `\\` in two `src/` paths (fixed here: `T5P_SEP`) | POSIX paths in `ppu_fs.cpp`/`sys_fs.c` | a signed `.app` is read-only: game data, saves, logs, shader cache, the built dylib go to `~/Library/Application Support/T5DR Online/`; the game's cwd is set there | 1-2 |
| **Network** | Winsock (`netplay_core.cpp` via `t5_sock.h` now; runtime `sysNet.c` has POSIX branches) | BSD sockets | the macOS firewall asks once per signed app ("accept incoming connections"); UPnP/NAT-PMP is Python in the launcher (portable) | 1 |
| **CPU check** | `cpu_check.cpp` (SSE4.1, MessageBox) and `gpu_preference.c` (Optimus exports) -- Windows-only by CMake | -- | not needed on arm64; an x86-64 macOS build would need the same SSE4.1 check | 0 |
| **Launcher** | Tk (portable) plus: `ctypes.windll` (DPI awareness, window placement, `user32`), `winreg` (problem report), `os.startfile`, `CREATE_NO_WINDOW`, `pythonw.exe`, the stub `T5DR Online.exe`, the updater's zip swap; `lobby/t5lobby/padnav.py` reads XInput/WinMM through ctypes | -- | `.app` bundle with an embedded Python (python-build-standalone has Tk) and a tiny launcher binary; `open` for files; system info from `sysctl`; DPI is automatic; the updater replaces the whole signed `.app` (writing into a signed bundle breaks its signature); pad navigation: ask the game binary (`t5dr --pad-probe`) or PyObjC GameController | 6-8 |
| **Build, release, CI** | `build_game.py`/`build_game_dll.py` (clang-cl, vcvars), `package_release.py` (zip), `release.yml`, `release_preflight.py`, VirusTotal step | upstream CI builds the runtime on macOS arm64 | macOS paths in the build tools, `.dmg`/zip with the `.app`, `codesign --options runtime` + `notarytool` + `stapler` (needs the developer account), a macOS CI job (GitHub's macOS runners cost 10x minutes in a private repository) | 4-6 |
| **Test tools** | `tools/smoke` (job objects, `screenshot.ps1`, Windows process APIs), `rollback_net_test.py`, `cross_build_test.py`, `hang_watch.py` | -- | process control by process group, frame dumps instead of screenshots (already the smoke suite's main source), a **Mac vs PC pair** runner (two machines on a LAN, the existing UDP proxy in between) | 3-4 |
| **Determinism** | patch 0032 (x86-64 only: MXCSR pinning, `ppu_fp_det.h`), `tools/cross_build_test.py` | the non-x86 branch of `ppu_fp_det.h` | the sqrt NaN fix (one release for all players), FPCR check, `volatile` audit, `fp_vectors` and Mac-vs-PC pair runs (section below) | 6-10 |
| **Diagnostics** | `PS3_DEBUG` console (tlhelp32), host sampler, hang watchdog, `PS3_HOST_PROF` | some through the shim (`Thread32First`, `SuspendThread`, `GetThreadContext` over Mach) | port when needed | later |

Total: **~70-100 agent-days**, about 8-12 weeks of calendar time with two
agents (the phases below overlap), most of it the renderer, input and
packaging.

### Renderer: what live draw has that the Metal path lacks

| feature (Windows, patch) | Metal backend + draw engine today |
|---|---|
| guest VP/FP decompiled to HLSL, PSO cache, PSO prewarm (0023) | HLSL -> SPIR-V -> MSL per program at run time, no prewarm, no on-disk cache (first-use stutter) |
| skinned-normal and shadow fixes: depth-compare sampling with 2x2 PCF, depth clamp (0010) | depth targets exist; no compare sampler / PCF / clamp path |
| internal resolution 0.5x..4K, per-surface factor, scissor fix (0038; `PS3_RES_SCALE`, `PS3_RENDER_SCALE` aliases) | guest size only |
| flips queued in the command stream, shown at vblank; present at translate; display lock to the monitor's vblank with adaptive lead (0005, 0034) | present when the engine flips; no pacing, no vblank lock |
| async vertex fetch (`RSX_VERTEX_THREADS`), program memos, texture pool (0023) | vertices fetched on the CPU as 16 float4 attributes per vertex (256 B), synchronous |
| tearing / no-vsync modes, frame latency, `PS3_PRESENT_FILTER`, letterbox, Alt+Enter/F11 | windowed, fixed |
| `LD_FRAME_DUMP` (the smoke suite's screenshots), `LD_DRAW_DUMP_TEX`, method reports | headless readback of the centre pixel only |
| weak-PC tuning (0027), FIFO ring end fix (0035, in cellGcmSys -- shared, already applies) | -- |

Approach: keep `rsx_draw_engine.c` as the shared orchestration (it is what
upstream maintains), port each live-draw fix into it in the order of the table
(each one is visible on a frame dump), and make the Metal backend's per-draw
CPU vertex fetch a GPU-side fetch before measuring frame times. Target: same
frame dumps as Windows for the 18 stages and the menus (`tools/smoke`'s
frame comparison).

## Determinism across operating systems and CPUs

Online play needs bit-identical guest state on both machines; the desync
detector hashes 25 KB of state every frame and voids a ranked match on a
mismatch.

### What patch 0032 already gives, and why it carries over

Patch 0032 ("same state on every CPU") removed every source of x86-64
variation from the lifted code: no C-runtime math (`ppu_fp_det.h`: `sqrtsd`,
`cvtsd2si`, an exact software fma that matches `vfmadd`), MXCSR pinned to
`0x1F80` on every guest thread and re-checked after every HLE call,
`-ffp-contract=off`, no `rcpps`/`rsqrtps`/x87. The lifter itself goes further
than x86 needs: PPC NaN rules are implemented in software for `fadd` ...
`fdiv` and the fused family (`ppu_fp_bin`, `ppu_fmadd_core`: propagated NaNs
quieted in PPC operand order, the PPC default NaN `0x7FF8000000000000` for
invalid operations), `frsp` truncates NaN payloads explicitly, `fctiw`/`fctid`
saturate before converting, and every VMX float op canonicalizes NaNs
(`ppu_vmx.h`: `vmx_vnan2`, `vmx_fix`) and handles VSCR[NJ] in software. No
lifted code reads host FP flags. So most of the lifted FP is already defined
by C semantics plus IEEE-754, which arm64 implements the same way.

### Risks, one by one

| risk | x86-64 PC | Apple Silicon (arm64) | status |
|---|---|---|---|
| fused multiply-add contraction | off (`-ffp-contract=off`) | Apple clang fuses `a*b+c` **by default** (`-ffp-contract=on`) | `-ffp-contract=off` must reach the lifted PPU, SPU and runtime code; CMake now passes it with either compiler driver (`test_lifted_code_never_contracted`). Compiling the real lifted FP code for arm64 (this branch, `fp_vectors.cpp -S`) gives fused instructions in exactly the 10 instructions that are fused on the PPU (`fmadd/fmsub/fnmadd/fnmsub`, both precisions, `vmaddfp`, `vnmsubfp` -> `fmla.4s`), and nowhere else |
| default NaN of an invalid operation with no NaN input | `0xFFF8000000000000` (sign set) | `0x7FF8000000000000` (sign clear) | **the one known difference.** The lifter wraps add/sub/mul/div/fma, but `fsqrt`, `fsqrts` and `frsqrte` pass the host result through: `sqrt(-x)` is `0xFFF8...` on a PC (seen in `fp_vectors.py --dump fsqrt`) and is expected to be `0x7FF8...` on a Mac (ARM's default NaN has the sign clear; not yet observed, no Mac). The PS3 itself gives `0x7FF8...`. Fix: route the three through a helper that returns the quieted input NaN or the PPC default NaN (like `ppu_fp_bin`) on **every** host. It changes PC results for negative square roots, so it must ship in one release for everybody (the lobby's build-id check already forces equal builds) and needs `tools/cross_build_test.py` once more |
| NaN propagation with two NaN inputs (x86: first source; arm64: signalling before quiet) | -- | -- | not reachable: the lifter and `ppu_vmx.h` choose the propagated NaN themselves before the host op |
| flush-to-zero / denormals-are-zero | MXCSR `0x1F80`: off | FPCR.FZ = 0 by default: off | arm64 needs its own check: `ppu_fp_env_check` reads MXCSR only (`#ifdef PPU_FP_X64`). Add an FPCR check (`mrs fpcr`, expect 0: nearest, no FZ, no DN, no AH) at thread start and after HLE calls, like 0032 does for MXCSR (`t5p_fp_control()` already reads it for the log line). Apple's frameworks (Accelerate, CoreAudio render threads) may set FZ on threads they own; guest code never runs on those |
| rounding mode | nearest | nearest | same; FPSCR[RN] is not emulated (the title never changes it) |
| float -> int out of range | `0x80000000` ("indefinite") | saturates | not reachable from lifted code (`ppu_f2i32/64` and `vctsxs/vctuxs` clamp first); check runtime HLE that converts guest floats with plain casts (none in the state path found) |
| underflow tininess before/after rounding | after | flags differ in edge cases | results are identical; nothing reads host flags |
| C library math | none in lifted code (0032) | `ppu_fp_det.h`'s non-x86 branch uses `nearbyint`/`floorf`/`ceilf`/`truncf`/`__builtin_sqrt` | these are exact operations (one correct result), lowered to `frint*`/`fsqrt`; libm version does not matter |
| `long double`, x87 | not used | 64-bit on arm64 macOS | grep finds none in the lifter, runtime or `src/` |
| memory ordering (x86 TSO vs weak arm64) | forgiving | not | the lifter emits C11 fences for `sync`/`lwsync`/`eieio`/`isync` (dmb on arm64) and `lwarx/stwcx.` as CAS -- the game ran on a weaker PPC, so faithful barriers are enough. Risk is in host code written for x86: 52 `volatile` lines in our runtime patches and a few in `src/netplay/t5_hooks.cpp` (kernel semaphore peeks) need `__atomic` loads with acquire/release. Not a determinism issue in itself, but a lost update between threads becomes a desync |
| SPU float (sound core, skinning) | exact / near-exact emulation | same C, NEON paths in `spu_helpers.h` | render- and audio-only; neither is in the hashed state |
| HLE results that depend on the OS | -- | -- | `sys_get_random_number` (OS random; netplay reseeds), clocks (`PS3_FIXED_TIME`), `printf` of floats (UCRT vs Apple libc: both correctly rounded). The title imports no libc math, `qsort` or `strtod` from firmware |
| compiler flags and versions | clang-cl (LLVM 23), `-O2` | Apple clang or bundled LLVM | IEEE ops do not depend on the optimizer once contraction is off; the fp_vectors digests and the pair test decide. Prefer the bundled LLVM release on both sides so one compiler version produces both builds |

### Rollback on macOS: what to measure first

Windows commits the rollback state in ~1.3 ms per frame for ~700 dirty 4 KB
pages (docs/ROLLBACK.md). The POSIX write watch (`t5_plat_posix.c`) costs one
page fault per dirty 16 KB page per frame plus one `mprotect` per run of dirty
pages at each commit -- a few hundred faults a frame, each a signal round trip.
Unmeasured. If it is too slow: leave the pages that are dirty every frame (the
"hot set", docs/ROLLBACK.md) unprotected and compare them against the shadow
copy at commit (a 16 KB `memcmp` is ~1 us), protecting only the cold pages.
Also on the list: the runtime's host writes into guest memory through the
kernel (`read(2)`, `recv(2)`) must touch the destination first (EFAULT
otherwise), and the rollback detours become lifter hook slots.

### How to prove it (on the Mac)

1. `python3 tools/fp_vectors.py --ps3recomp deps/ps3recomp --compare tests/data/fp_vectors_x64.txt`
   Prediction: everything matches except `fsqrt`, `fsqrts`, `frsqrte`. Any
   other name is a new finding: `--dump <name> --count 50` on both machines
   and diff.
2. Fix the three in the lifter, regenerate the reference on the PC, confirm
   PC baseline/v3/soft-fma and the Mac all print the same digests.
3. Mac vs PC pairs with `T5_NET_DESYNC_DUMP=1`: rollback and lockstep, the
   `cross_build_test.py` matrix (several matches per mode, a persistent game,
   KO cameras), then a long soak. Only after that may a Mac join ranked.

## Recommended order

**arm64 (Apple Silicon) first, with an x86-64 macOS build as a test tool only.**

- Nearly every Mac sold since 2020 is Apple Silicon; Apple has said macOS 26
  is the last release for Intel Macs, and that Rosetta 2 stays general-purpose
  only through macOS 27. A shipped Intel build would be dead weight.
- An x86-64 macOS build running under Rosetta on the same Mac is still worth
  having during bring-up: Rosetta runs x86 code with x86 FP and memory-order
  semantics, so "x86-64 build matches the PC but arm64 does not" isolates an
  arm64 problem from a port problem. Build it, do not ship it.
- Not a product either: the Windows release under CrossOver / Apple's Game
  Porting Toolkit (D3D12 through D3DMetal, x86 through Rosetta). If the owner
  already has such a setup it is a one-evening curiosity; it tells nothing
  about the native port and depends on Rosetta's future.

Phases (each ends with something the owner can see):

1. **Boot** (1-2 weeks): runtime on macOS with the existing Metal path --
   guest memory by `mmap`, guest main thread on a 256 MB pthread with AppKit on
   the main thread, getenv cache, Application Support paths, CMake build of the
   lifted code on the Mac. Done when: title screen and a fight run, picture
   imperfect, no sound.
2. **Determinism gate** (1 week, can run beside 1): `fp_vectors` on the Mac,
   the sqrt NaN fix (one release for everybody), FPCR check, lockstep pair Mac
   vs PC with direct fight. Done when: 0 mismatching frames over many matches.
3. **Picture** (4-6 weeks): the renderer table above, frame pacing,
   resolution setting. Done when: frame dumps match Windows on all stages,
   60 fps on an M1.
4. **Sound and input** (2 weeks): CoreAudio device thread, GameController +
   IOHID + keyboard, controls.ini, tap latch, movies optional.
5. **Rollback** (1-2 weeks): POSIX write watch measured (fault cost per frame,
   16 KB pages), kernel-write touch points, lifter hook slots instead of
   detours, rollback pairs Mac vs PC at RTT 150 / loss 3 %.
6. **Launcher, packaging, signing, updater** (2 weeks), then a closed test with
   Mac players.

## What the owner needs to provide or decide

| item | why | cost |
|---|---|---|
| **A Mac with Apple Silicon** (M1 or newer; 16 GB memory recommended -- clang needs 2-4 GB per lifted chunk), macOS 14 or newer | nothing past the groundwork can be checked without one | owned or ~600-1,000 USD (a used M1/M2 Mac mini is enough) |
| a way for an agent to use it: Remote Login (SSH) from this PC, or Claude Code installed on the Mac | builds, runs, frame dumps | -- |
| Xcode Command Line Tools (free, `xcode-select --install`), Homebrew with cmake, ninja, python 3.12, glslang, spirv-cross (and sdl2: ps3recomp's CMake insists on it off Windows) | build | free |
| **Apple Developer Program**: decision by the owner. Gives a Developer ID certificate for signing and notarization, so players open the game normally. Without it: the game runs, but each player must allow it once in System Settings > Privacy & Security > "Open Anyway" (macOS 15 removed the right-click shortcut), and again after updates | player experience | **99 USD a year**; the owner creates the account, never an agent |
| a Mac player or two for online tests against PCs, later a closed test | Mac vs PC over the internet | -- |
| optional: macOS runners in GitHub Actions for the private Dev repository | CI for the Mac build | billed at 10x the Linux minute rate |

## How the groundwork is used on the Mac (first session)

    git clone ... && cd T5DROnline && git checkout macos-port
    python3 tools/fp_vectors.py --ps3recomp deps/ps3recomp --compare tests/data/fp_vectors_x64.txt
    python3 -m unittest discover -s tests -p "test_macos_port.py" -v    # now against the real SDK headers
    cmake -S . -B build/cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DPS3RECOMP_DIR=deps/ps3recomp ...

Then compile `src/` for real (the C++ files have only been checked by the
lint here: no libc++ headers on the PC) and fix what the compiler finds.

## Appendix: the platform interface

`src/platform/t5_plat.h` (C, used from C++). Windows: inline wrappers.
POSIX: `t5_plat_posix.c`.

| function | Windows | POSIX |
|---|---|---|
| `t5p_exit_now(code)` | `TerminateProcess(self)` | `fflush` + `_exit` |
| `t5p_game_symbol(name)` | `GetProcAddress(t5dr_game.dll)` | `dlopen(t5dr_game.dylib/.so, RTLD_NOLOAD)` + `dlsym` |
| `t5p_getenv_os`, `t5p_setenv_os` | `Get/SetEnvironmentVariableA` (+ `_putenv_s`) | `getenv`, `setenv` |
| `t5p_module_of(addr, ...)` | `GetModuleHandleExA` + `GetModuleFileNameA` | `dladdr` |
| `t5p_process_uptime_s()` | `GetProcessTimes` | since a static constructor |
| `t5p_cycles()`, `t5p_thread_cycles()` | `__rdtsc`, `QueryThreadCycleTime` (TSC ticks) | `CLOCK_MONOTONIC_RAW`, `CLOCK_THREAD_CPUTIME_ID` (ns); callers calibrate against QPC |
| `t5p_replace_file`, `t5p_file_stamp`, `t5p_open_read_shared`/`t5p_read`/`t5p_close` | `MoveFileExA(REPLACE_EXISTING)`, `GetFileAttributesExA`, `CreateFileA(FILE_SHARE_DELETE)` | `rename`, `stat` mtime ns, `open`/`read` |
| `t5p_write_watch_available`, `t5p_write_watch`, `t5p_write_watch_reset`, `t5p_write_watch_touch` | `GetWriteWatch`, `ResetWriteWatch` | page protection + SIGSEGV/SIGBUS handler (chains to the previous one) |
| `t5p_code_patching`, `t5p_exec_alloc_near`, `t5p_code_write`, `t5p_icache_flush` | `VirtualAlloc(RWX)` near the code, `VirtualProtect`, `FlushInstructionCache` | x86-64 Linux: `mmap`/`mprotect`; macOS x86-64 only with `T5DR_CODE_PATCH=1` (no hardened runtime); arm64: refused |
| `t5p_fp_control()` | MXCSR control bits | MXCSR or FPCR |
| `T5P_SEP`, `T5P_CTX_PC(ctx)` | `"\\"`, `ctx->Rip` | `"/"`, `ctx->Pc` |

`src/platform/t5_sock.h`: `t5s_socket`, `t5s_socklen`, `T5S_INVALID`,
`T5S_ERROR`, `t5s_startup`, `t5s_close`, `t5s_last_error`,
`t5s_set_recv_timeout`, `t5s_no_connreset`, `t5s_error_is_transient`.

## Evidence

All on the development PC, 2026-10-19, `macos-port` built with the runtime
series 0001..0042 (`build/series`), lifted code `build/recomp`, other agents'
games and builds running at the same time.

- Object code: `build/mac/objdiff.py` (local tool) over the 23 `src/` objects
  before and after: 3,503 functions identical, 19 differ (the edited call
  sites: `state_commit`, `collect`, `measure_on_frame`, `offer`, `detour`,
  `ctl_poll`, `guard_veh`, six perf wrappers, `h_cellGcmSetFlip`,
  `h_wait_flip`, and `begin_frame`/`rb_begin` which inline the FP log line).
- `build.ninja`: compile flags, defines and include paths identical.
- FP vectors: 55/55 equal for baseline, x86-64-v3 and software fma.
- `python tests/ci_unittest.py` (with `PS3RECOMP_DIR`): 491 tests OK, none
  skipped (includes `test_macos_port` and `test_fp_vectors`).
- Smoke quick (`tools/smoke/run.py`, muted, below-normal priority, up to 9
  other games running): PASS, 5 tests, 81 checks PASS, 0 FAIL.
- Rollback pair (`tools/rollback_net_test.py --fight 26,33,20,2 --next
  26,33,20,2 --rtt 150 --jitter 5 --loss 3 --delay 1 --matches 2 --polite`):
  two matches each side, sync through frame 10,799 with 0 mismatching frames,
  the same result hashes on both sides (`d4b75e00154439fa`,
  `9f3ea672fd60ddcf`), 2,336 rollbacks / 7,549 re-simulated frames, write watch
  through `t5p_write_watch` (commit 0.6-0.9 ms), the direct-call cut's six
  detours installed through `t5p_code_write`, sockets through `t5_sock.h`.
  40 fps because 8 compilers and 9 other games ran at the start (not a
  result about this change).
