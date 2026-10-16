# Releasing T5DR Online

How a player gets from a downloaded zip to a running game, modelled on
[Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online):
download a zip with no game content, start the launcher, pick your own `.pkg`
and `.rap`, click **BUILD GAME**, wait, play. The launcher will also host the
online lobby (see "Online" below).

All numbers below were measured on the development PC (AMD Ryzen 9 7950X,
16 cores / 32 threads, 31 GB RAM, Windows 11) on 2026-10-16, while other
agents ran 3-5 game instances on the same machine. Estimates are marked as such.

## Recommendation

**Ship the runtime precompiled and compile only the game-derived code on the
player's PC, with a clang-cl + lld-link that ship in the zip. The player
installs nothing.** (Option C below, in its "header-free" form.)

- The player's PC compiles only what comes out of their own copy -- the 15
  lifted PPU chunks, the lifted SPU sound core and SPURS jobs, and two small
  glue files -- into
  `t5dr_game.dll`. That code needs **no** Microsoft C runtime or Windows SDK
  headers or libraries: clang's own headers plus 8 small declaration headers
  of ours are enough, and it links against two import libraries made from our
  own `.def` files. So no Visual Studio, no Windows SDK, no CMake, no Git, no
  installed Python.
- The runtime (`t5dr.exe`: ps3recomp's HLE libraries, loader, D3D12 renderer,
  audio, input -- everything that is not the game) is built once by us,
  game-independently, and shipped. It uses the static C runtime, so not even
  the Visual C++ redistributable is needed.
- **Verified end to end** on this PC with a packaged zip
  (`T5DR-Online-0.1.0-rc1.zip`, main's patches up to 0007 included: skinning
  jobs, ATRAC music, movies) run in an environment whose PATH held only
  Windows' own folders: BUILD GAME took **90 s** (unpack 16 s, lift 28 s, SPU
  5 s, compile 40 s), the game booted from `t5dr.exe` + `t5dr_game.dll` and ran
  at **60 fps** for the 60 s measured, the lifted SPURS jobs dispatched from
  the DLL (no "dispatch MISS"), no crash. Same fps profile as the normal build.
- **Size: 90.0 MB zip, 250 MB unpacked.** Player disk after the build: 0.8 GB
  more (unpacked game 596 MB, build 171 MB).

The alternative that works without any runtime change -- the launcher installs
Visual Studio Build Tools through winget (option A) -- costs the player about
6.4 GB of disk, an administrator prompt and a 10-20 minute install before the
first build. It is kept as the fallback for developer builds
(`build_game.py --full-compile`, or a zip made without `--prebuilt-host`).

## What the build needs today (repository, `tools/build_game.py`)

| step | tool | on this PC |
|---|---|---|
| deps | Git (clone ps3recomp, apply `patches/ps3recomp`), pip | Git 2.55 (358 MB installed) |
| keys, decrypt, unpack, lift, spu | Python 3.10+ with pycryptodome | Python 3.12 (190 MB) |
| compile | VS 2022 Build Tools: MSVC headers/libs (STL, CRT), Windows SDK (Windows, D3D12, XInput headers + import libs), CMake + Ninja (VS component) | 3.4 GB + SDK 1.7 GB + package cache 1.3 GB |
| compile | clang-cl + lld-link (LLVM; the CMake build already links with lld-link, llvm-lib, llvm-mt) | LLVM 23.1, 3.0 GB installed |

Clean compile of a copy of the main build (`Measure-Command`, no other agent
compiling; main at c6ca38e, before patches 0002-0007): **54 s** = configure
3.4 s + build 49 s. (At the current main, with the job lifting, music and
movies, the same CMake compile step took 76 s while other agents were busy.)
CPU time by part:

| part | objects | CPU time | game-derived? |
|---|---|---|---|
| ps3recomp runtime library | 153 | 297 s | no |
| boot harness, loader, HLE table | 7 | 11 s | no |
| lifted PPU chunks | 15 | 413 s (12-33 s each) | **yes** |
| lifted SPU sound core + glue | 3 | 16 s | **yes** |
| link (lld-link) | 1 | 0.2 s | -- |

So 41% of the compile work is game-independent and can be done once by us.
With 16+ hardware threads the wall time is bound by the largest chunk (~33-39
s); `ppu_lifter.py --max-chunk-lines 40000` (30 chunks) would cut that roughly
in half on many-core PCs.

## Options evaluated

### A. Launcher installs the prerequisites via winget (with consent)

Implemented as the launcher's **Install missing...** button
(`tools/prereqs.py install_command`). It installs exactly:

    winget install --exact --id Microsoft.VisualStudio.2022.BuildTools --override
      "--passive --wait --norestart
       --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64
       --add Microsoft.VisualStudio.Component.Windows11SDK.26100
       --add Microsoft.VisualStudio.Component.VC.CMake.Project
       --add Microsoft.VisualStudio.Component.VC.Llvm.Clang"

(or `setup.exe modify` when Build Tools already exist without a component),
so one install brings MSVC, the SDK, CMake + Ninja and Microsoft's clang-cl;
Python and Git are not needed from a release zip.

- Disk: this PC's Build Tools install (VCTools workload with the recommended
  components) takes **6.4 GB** (3.4 GB VS, 1.7 GB SDK, 1.3 GB package cache).
  The minimal selection above should be smaller; not measured -- that needs a
  test PC without Build Tools. Download: not measured here (the bootstrapper
  streams packages); expect 1.5-2.5 GB.
- Needs administrator rights (UAC), 10-20 minutes, and the player accepts
  Microsoft's Build Tools license (legal for an individual: the Build Tools
  may be used to build software, and the files come from Microsoft directly).
- Untested here: the build with Microsoft's bundled clang-cl (the
  `VC.Llvm.Clang` component, an older clang than the LLVM 23 used here).
  `prereqs.py` accepts any clang-cl >= 16.
- winget ships with Windows 11 and current Windows 10 ("App Installer").

Verdict: works, but it is the heavy part of the player's experience. Keep as
the fallback.

### B. Portable toolchain in the zip with llvm-mingw

clang-cl/lld-link are redistributable (Apache-2.0 WITH LLVM-exception); MSVC's
CRT/STL headers and libraries and the Windows SDK are not. llvm-mingw would
replace both with redistributable mingw-w64 headers/libs. For **ps3recomp's
runtime** that is a port: it is written for MSVC/clang-cl -- `__try/__except`
(1 file), `_Interlocked*` (7), `#pragma comment(lib)` (8),
`RtlCaptureStackBackTrace` (9), `_ReturnAddress` (3), `_BitScan*` (3),
`__declspec(selectany)`, `_aligned_malloc`, 15 files with `_MSC_VER`
branches -- and its C++ objects would get the Itanium ABI. Most of that exists
in mingw-w64, but it is unbuilt and untested, and it would have to keep up with
upstream ps3recomp.

Verdict: not needed. Option C removes the need for any C runtime headers on
the player's side, so the runtime can keep its MSVC build on our side.

### C. Precompile everything that is not game-derived (recommended)

What the player still needs depends on how the game code is joined to the
runtime:

- **C1, static link (today's single exe):** the final link of `t5dr.exe` needs
  the MSVC static CRT libraries and SDK import libraries, and the lifted code
  includes `<atomic>`, `<stdio.h>`, `<math.h>`, `<string.h>`, `<intrin.h>`.
  The player would still need Build Tools -- only 41% faster.
- **C2, game code in a DLL (built and verified):** `t5dr.exe` is the runtime
  alone, exports the 35 runtime symbols the generated code calls
  (`tools/gamedll/t5dr_host.def`: `vm_read*/vm_write*`, `ps3_hle_call`,
  `lv2_syscall`, the `spu_*` channel functions, data `vm_base`,
  `vm_inline_ok`, ...) and loads `t5dr_game.dll` at start. The DLL is compiled
  "header-free":
  - `clang-cl /X` (no system include paths), `/Zl /GS-`, a forced include
    (`tools/gamedll/include/t5dr_dll_prefix.h`) that spells `PPU_FENCE` with
    a compiler builtin instead of `<atomic>` and reaches the runtime's data
    through the import slots (`#define vm_base (*__imp_vm_base)`), and our
    own small `stdio.h/stdlib.h/string.h/math.h/malloc.h/setjmp.h` with the
    C prototypes the code uses. `/showIncludes` over a PPU chunk, the SPU
    core and the glue: 351 clang resource headers, 27 of ours, 9 ps3recomp
    headers, the lifted header -- **nothing from Visual Studio or the SDK**.
  - `lld-link /DLL /NOENTRY /NODEFAULTLIB` against `t5dr.lib` (the runtime's
    import library, ours) and `ucrt_min.lib` (made on the player's PC by
    `lld-link /lib /def:tools/gamedll/ucrt_min.def` -- the C functions from
    `ucrtbase.dll`, which is part of Windows 10/11). `/verbose`: it reads only
    our objects and these two libraries.
  - `tools/gamedll/t5dr_game_dll.c` supplies what a CRT would: the TLS
    directory, `_fltused`, `__chkstk` (the stack probe; the lifted skinning
    jobs have frames over a page), a loop over the `.CRT$XCU` constructors
    (the SPU image and job registration) and the thread-local
    `g_trampoline_fn`, which now
    lives in the DLL (the runtime reaches it through `ppu_game_tramp_slot()`).
  - Runtime side: `patches/ps3recomp/0020-game-dll.patch` (opt-in, compiled
    only with `PS3_GAME_DLL`): `ppu_game_dll.h`, `ppu_game_dll_load()` in
    `ppu_loader.cpp`, one call at the top of `boot_main.cpp`'s `main()`.
    CMake: `-DT5DR_GAME_DLL=ON` builds the host; it writes a generic
    `ppu_recomp.h` from `ppu_lifter.HEADER_PREAMBLE` (the lifter's fixed
    header part), so **the host build needs no game file at all**.

  Measured: host build 24 s (our side, 1.9 MB exe with static CRT, imports
  only Windows DLLs); game DLL 39 MB, compile 40 s + link 0.2 s on the
  player's side; boots with all 23,059 lifted functions, 60 fps; same log
  (unresolved NIDs, job chains, no crash) as the static build.

  What the player's PC still needs: clang-cl.exe (105 MB), lld-link.exe
  (72 MB) and clang's resource headers (16 MB) -- 201 MB raw, **72.6 MB
  zipped** -- all shipped in `toolchain/llvm`. Plus the bundled Python.

  Costs/risks: every read of `vm_base`/`vm_inline_ok` in the inline load
  path is one extra load through the import slot, and calls into the runtime
  go through import thunks; the fps counter could not show a difference (both
  builds sit at the 60 fps vblank cap), a frame-time comparison with an idle
  PC is still to do. One of eight DLL runs ended by itself after ~48 s with
  exit code -1 and no `[CRASH]` line while other agents' processes were
  running; the other seven (15-75 s) did not. Not explained yet -- watch for it.

### Python on the player's PC

Python runs the whole pipeline (pkg_extract, unself, ppu_loader,
find_functions, ppu_lifter, the SPU lifter) and the launcher. Options:

- **Bundled CPython (chosen):** `package_release.py --bundle-python` copies
  this PC's CPython 3.12 into `python/`: interpreter, stdlib without tests/IDLE,
  tkinter + Tcl/Tk, pycryptodome; a `python312._pth` isolates it from any
  other Python. **38.4 MB unpacked, ~13 MB zipped.** Redistributable (PSF
  license, Tcl/Tk license, pycryptodome BSD/public domain). Verified: the full
  build ran with PATH holding only Windows folders.
- **PyInstaller-frozen tools:** possible, but not better. The frozen exes
  carry the same interpreter (similar size), `ppu_lifter.py` uses
  `multiprocessing.Pool` and `build_spu_workloads.py` starts
  `sys.executable spu_lifter.py` -- both need special handling when frozen --
  and PyInstaller bootloaders are often flagged by antivirus products, which
  is the last thing an unsigned game download needs. Not measured.

## The release zip

`tools/package_release.py` builds `dist/T5DR-Online-<version>/` and the zip
from the repository:

    python tools/package_release.py --version 0.2.0 --bundle-python ^
        --llvm "C:\Program Files\LLVM" --prebuilt-host --zip ^
        --keys keys\ps3.keys --game-dir build\recomp --game-dir build\spu --game-dir game

| | without `--llvm --prebuilt-host` | with them (recommended) |
|---|---|---|
| player installs | VS Build Tools via the launcher (6.4 GB) | nothing |
| zip / unpacked | 16.3 MB / 46.7 MB | 90.0 MB / 250.0 MB |
| BUILD GAME on this PC | 120 s (below-normal priority, other agents busy; before main's 0002-0007) | 90 s |

Contents (recommended layout): `T5DR Online.exe` (3.5 KB starter, our C, built with
clang-cl, kernel32/user32 only), `launcher/`, `tools/`, `patches/`,
`CMakeLists.txt`, `deps/ps3recomp/` (MIT; pinned commit + our patches; only
`include libs runtime third_party`, top-level `tools/*.py|json`,
`CMakeLists.txt`, `LICENSE`), `python/`, `toolchain/llvm/`,
`runtime/t5dr.exe + t5dr.lib`, `LICENSES/` (ps3recomp MIT, at3_standalone
LGPL-2.1, Python PSF, LLVM Apache-2.0), `README.txt` (the players' section of
README.md), `release.json` (version, code ID).

**Kept out on purpose, and checked:**

- ps3recomp's `fw_spu/` holds Sony firmware modules (`libsre.prx`,
  `libatrac3plus.prx`, ...) and code lifted from them. The build does not use
  it; it is not shipped.
- ps3recomp's `tools/pkg_extract.py` carries the PS3/PSP package keys as
  literals. The packaged copy has them replaced by a lookup in the player's
  `keys/ps3.keys`, which `tools/make_keys.py` now also fills
  (`PKG_AES_KEY`, `PKG_AES_KEY2`, from RPCS3's public `key_vault.h`).
- The scan (on the folder, then again on the zip; the run fails on any hit):
  game files by name (`.pkg .rap .rif .edat .sdat .self .sprx .prx .elf`,
  `EBOOT`, `PARAM.SFO`, `T55DATA*`, `ppu_recomp*`, `spu_recomp*`,
  `t5dr_game.dll`, `launcher.json`, logs, `keys/ game/ native/ build/`
  folders), by content (PPC64/SPU ELF, `SCE\0`, `\x7FPKG`, `\0PSF` magic;
  lifted code under any name -- 100+ `func_XXXXXXXX` names, a 100 KB piece of
  a chunk has ~150, the most any ps3recomp source has is 38; binaries over
  20 MB outside `toolchain/llvm`), every key in `--keys` (raw, hex either
  case, C array), and byte-identical copies of anything under `--game-dir`.
  Tested negatively: planted PARAM.SFO (renamed), the original
  pkg_extract.py, a renamed `spu_workloads.c` and 300 KB/100 KB pieces of
  lifted PPU/SPU code were all caught.

The repository has no LICENSE file for our own code yet; a public release
should say under which license the launcher and tools are.

## The launcher (`launcher/`)

Python/tkinter (in the bundled Python), started by `T5DR Online.exe`.

- **Build:** choose `.pkg`/`.rap` (found automatically in
  Downloads/Desktop/Documents when the content ID matches; the package's
  content ID and the license name are checked on selection), build-tool
  status (collapsed when all is there; **Install missing...** runs winget
  after a yes), **BUILD GAME** with the eight steps, overall progress
  (weighted per step, sub-progress from the lifter's and the compiler's
  `[k/n]` output), the live log, `native\build.log`, Cancel, "Redo every
  step", "Keep the PC responsive" (below-normal priority). Errors appear as
  one plain sentence in red -- for example a wrong version:
  "This copy is a different version of the game: "TEKKEN 5 DARK
  RESURRECTION" version 01.01, content ID UP0700-NPUB30009_00-0000000000000000
  (program SHA-1 aa047e02e79e...). The port supports only ...", shown within
  **1.6 s** because `decrypt` now runs before the 600 MB `unpack`
  (it extracts only `EBOOT.BIN` + `PARAM.SFO` first). A wrong `.rap` gets
  "The license (.rap) does not belong to this package ...".
- **Play:** verifies the decrypted program's SHA-1 against the pinned one and
  the build stamp's code ID ("rebuild needed" after an update that changes the
  game code), starts `t5dr.exe` without a console with the defaults from
  `run_game.py` (`RSX_LIVE_DRAW=1`, `PS3_VERBOSE=0`, `PS3_GCM_TICKER_PUMP=1`),
  name (`PS3_NICKNAME`), logs to `native\logs\game-*.log` (last 10 kept),
  shows run time and the `[fps]` value, Stop.
- **Settings:** window 1280x720 / 1920x1080 / 2560x1440 (shrunk to the work
  area) / maximized / borderless fullscreen -- applied by the launcher to the
  game window, since the runtime's swap chain stretches its 1280x720 image to
  any window size (`DXGI_SCALING_STRETCH`, no `ResizeBuffers`); mute
  (`PS3_NO_AUDIO`); start minimized; extra `NAME=VALUE` settings; the
  keyboard/controller table. The placement code was checked on a stand-in
  window (1280x720, 1920x1080, 2403x1352 on a 2560x1440 screen, 2560x1440
  borderless); with the real game window it is **untested** (it would have
  covered the screen of the person at this PC).
- **Online:** placeholder. `launcher/online.py` documents the contract for the
  netplay work: `OnlineTab(parent, app)`, `on_show()`, `on_close()`, and
  `app.start_game(env)` to start a match with extra environment variables,
  `app.game` (running game: `.running()`, `.stop()`, `.fps`, `.log_path`),
  `app.settings["nickname"]`, `app.game_state()`.

`python launcher/t5dr_launcher.pyw --screenshots DIR [--build-steps ...]
[--play-seconds N]` renders the launcher invisibly (transparent,
click-through) and saves PNGs of each tab / of a build in progress / of a
running game -- used for the screenshots in `build/ln/shots`.

## Changes outside the launcher

- `tools/build_game.py`: `--out DIR` (game/, build/, keys/ under DIR; the
  launcher uses `<package>\native`), `--deps`, `[step]` / "already done" /
  `ERROR: <sentence>` output for the launcher, per-step timing, `decrypt`
  before `unpack`, PARAM.SFO and content-ID checks, a vendored ps3recomp
  (`.t5dr-vendored.json`) instead of a git clone, `compile` builds only the
  game DLL when `runtime/t5dr.exe` is shipped (`--full-compile` forces the
  CMake build), a build stamp with a code ID.
- `tools/run_game.py`: `--out`, `game_command()` for the launcher.
- `tools/make_keys.py`: also `PKG_AES_KEY`, `PKG_AES_KEY2`.
- `CMakeLists.txt`: option `T5DR_GAME_DLL`.
- `patches/ps3recomp/0020-game-dll.patch`, `0021-live-draw-window-background.patch`
  (apply on f17bcd3 + 0001, 0002, 0003, 0006, 0007; numbered high to stay out of the way).

## Found on the way

- **`PS3_WINDOW_BACKGROUND=1` does nothing with `RSX_LIVE_DRAW=1`.** Patch
  0001 handles it in `rsx_d3d12_backend.c`, but the live-draw engine shows
  its frames in the window `rsx_null_backend.c` creates, which was always
  visible. Measured: the game window was not minimized and was the foreground
  window in 5 of 133 samples over 15 s. With patch 0021 it stayed minimized
  in all 148 samples and never took the foreground. Every agent's "background"
  test runs have been popping up the game window.
- `tools/build_game.py`'s old `deps` step always ran `pip install -r
  requirements.txt` (capstone, construct, tabulate, tqdm); the build path
  imports only pycryptodome.

## Next steps

1. Frame-time comparison static vs. DLL build on an idle PC; then make the
   recommended layout the default of package_release.py.
2. Run the zip once on a PC that never had Visual Studio, LLVM or
   Python (a fresh Windows VM).
3. A license for our own code; code signing for `T5DR Online.exe` would
   avoid the SmartScreen warning.
4. Smaller chunks (`--max-chunk-lines 40000`) for faster builds on
   many-core PCs; trimming clang's resource headers and building a
   single X86-only `clang-cl` + `lld` binary would shrink the zip.
5. Netplay: fill in `launcher/online.py`.
