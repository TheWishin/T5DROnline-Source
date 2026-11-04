# Linux and Steam Deck (Proton, Wine)

T5DR Online is a Windows program. On Linux and the Steam Deck it can run through **Proton** (Steam) or **Wine**.
This is **not tested by us**: we have no Linux PC and no Steam Deck. What is below comes from reading our code
against what Wine and Proton do, and from player reports. If you try it, please tell us how it went
([Test checklist](#test-checklist-for-linux-players)).

Contents:

- [Quick start (Steam Deck or any Linux with Steam)](#quick-start-steam-deck-or-any-linux-with-steam)
- [Which Proton](#which-proton)
- [Known problems and what to try](#known-problems-and-what-to-try)
- [Plain Wine (Lutris, Bottles, wine on the command line)](#plain-wine-lutris-bottles-wine-on-the-command-line)
- [What the launcher does by itself under Wine](#what-the-launcher-does-by-itself-under-wine)
- [Which log to send](#which-log-to-send)
- [Test checklist for Linux players](#test-checklist-for-linux-players)
- [Why things differ (for developers)](#why-things-differ-for-developers)

## Quick start (Steam Deck or any Linux with Steam)

1. Extract the release zip into your **Linux home**, for example `~/Games/T5DR` (not into
   `steamapps/compatdata`). On a Steam Deck do this in **Desktop Mode**.
2. Put your own package (`.pkg`) and license (`.rap`) into `~/Downloads` (or your Desktop or Documents). The
   launcher looks there by itself.
3. Steam -> **Games -> Add a Non-Steam Game to My Library** -> Browse -> pick `T5DR Online.exe` in that folder.
4. In Steam, right-click the new entry -> **Properties -> Compatibility** -> tick **"Force the use of a specific
   Steam Play compatibility tool"** -> pick **Proton Experimental** (see [Which Proton](#which-proton)).
5. Start it. The first start of a Proton prefix takes a minute (Steam sets it up).
6. Do **BUILD GAME** once (in Desktop Mode on a Deck: the build is long and you may want to watch it). It needs
   the same as on Windows: about 10 GB free and some minutes; under Proton it is slower than on Windows.
7. Then play. On a Steam Deck the built-in controls are an Xbox pad for the game (Steam Input, on by default):
   that works offline and online.

Launch options are not needed. To collect a Proton log for a bug report, set the launch options to
`PROTON_LOG=1 %command%` (Proton writes `~/steam-<number>.log`).

## Which Proton

| Proton | What we know |
|---|---|
| Proton Experimental (Valve) | the default to start with |
| GE-Proton (GloriousEggroll) | ships the video codecs (intro movies should play). One player (GitHub #26, CachyOS, 1.1.x) got a dark blue window with sound with the default GE-Proton |
| proton-cachyos-slr (CachyOS) | the same player: works |
| Proton 9 / 10 (Valve stable) | not reported |

If one does not work, try the next: it costs only a restart (Properties -> Compatibility).

## Known problems and what to try

- **Dark blue window, sound plays** (GitHub #26). The dark blue is the empty game window: the game's
  Direct3D 12 renderer did not start. The game log says why: open `native/logs/game-<date>-<time>.log` and look
  for `[rsx] live-draw init FAILED`, `[pso-fail]`, `[display] present shader compile failed` or
  `[gpu] FATAL (exit code 13)`. Since 1.2.0 the launcher's **Check my problem** finds these lines and says
  what to do:
  1. Try another Proton (table above).
  2. Install Microsoft's shader compiler into the game's prefix. The game compiles all its shaders while it
     runs, with `d3dcompiler_47.dll`; Proton has its own version of it (from Wine's vkd3d), which may not
     compile everything the game needs. With [protontricks](https://github.com/Matoking/protontricks):
     `protontricks -l` lists your games and their ids (a Non-Steam Game has a long number);
     then `protontricks <that id> d3dcompiler_47`. Start the game again. **(untested)**
  3. Send the game log (see [Which log to send](#which-log-to-send)).
- **Black intro movies with sound.** Valve's Proton may have no H.264 video decoder for this game. Press START to
  skip; everything else works. GE-Proton ships the codecs and should play them. **(untested)**
- **Small stutter (a picture shown twice now and then).** Wine has no real display clock for the game's
  "display lock". Try Settings -> "Advanced: extra settings" -> `PS3_DISPLAY_LOCK=0`. **(untested)**
- **Online with rollback runs slower than offline.** The game's rollback watches which memory pages each frame
  writes; Windows does that in the kernel, Wine with a page fault per page. If online fights drop below 60 fps
  while offline ones do not, tell us (with the report). To compare, one player can set `T5_RB_MODE=off` in the extra
  settings: the match then uses the delay-based netcode for both. **(untested)**
- **Stages flash black, fighters drawn wrong**: fixed in 1.1.5 (the launcher sets two safe defaults under Wine, see
  below). If you see it again, send the report.
- **The game window does not come to the front in Steam Deck Game Mode.** The launcher and the game are two
  windows; Game Mode shows one. Use Desktop Mode for the first build; if the game hides behind the launcher in
  Game Mode, tell us. **(untested)**
- **Firewall hints**: Linux has no Windows Firewall, so the launcher's firewall check stays quiet. If online matches
  never connect directly, check your Linux firewall (UDP to the game's port must be allowed out and back in).

## Plain Wine (Lutris, Bottles, wine on the command line)

- You need **vkd3d-proton** in the prefix (Bottles: "VKD3D" on; Lutris: "Enable VKD3D"). Wine's own Direct3D 12
  does not have what the game needs.
- DXVK is not needed for the game (it uses Direct3D 12 only).
- `winetricks d3dcompiler_47` if you get the dark blue window.
- Wine 9 or newer.

## What the launcher does by itself under Wine

- Since 1.1.5: the game gets `RSX_VERTEX_THREADS=0` and `PS3_LWM_FAST=0` (vertex work on one thread, locks through
  the kernel path). A value you set yourself in the extra settings wins.
- The first line of every game log and a line in `launcher.log` say what was found, for example
  `[wine] Wine 10.0 Proton: GE-Proton10-11 on Linux 6.17 -- RSX_VERTEX_THREADS=0, PS3_LWM_FAST=0 -- d3d12: vkd3d-proton (native), d3dcompiler_47: Wine's own`.
  Only the name of the Proton folder goes into the logs, never its path (it has your Linux user name).
- Since 1.2.0:
  - the launcher looks for the package in your Linux Downloads, Desktop and Documents (as named in
    `~/.config/user-dirs.dirs`) and your home folder; Proton's own `C:\users\steamuser` folders are hidden deep in
    `steamapps/compatdata`, so nobody saves anything there;
  - **Report a problem** saves its zip on your **Linux Desktop** (else in your home folder) and removes your Linux user
    name from it (Proton's Windows user is only "steamuser");
  - the report's `system.txt` has a "Wine / Proton" line with the same facts;
  - **Check my problem** names a failed graphics start under Wine (above);
  - the online port forwarding (UPnP / NAT-PMP) reads the router address from Linux's own routing table.

## Which log to send

**Report a problem** in the launcher. It makes one zip on your Linux Desktop with the launcher log, the build log
and the last game logs (names and addresses removed). Attach it to an issue at
https://github.com/TheWishin/T5DROnline/issues and write:

- your Linux (distribution and version) or "Steam Deck LCD/OLED, SteamOS version",
- the Proton or Wine build (and which others you tried),
- your graphics card,
- what you saw.

If asked for more: the Proton log (`PROTON_LOG=1 %command%` as launch options, then `~/steam-<number>.log`). That file
has your Linux user name and folder paths in it: look through it before you post it.

## Test checklist for Linux players

Give this list to a Linux or Steam Deck player. One line per step: OK, or what happened.

| # | Step | Expected |
|---|---|---|
| 0 | Note: Linux / SteamOS version, Proton build, CPU, GPU, Deck LCD or OLED | |
| 1 | Start `T5DR Online.exe` through Steam (Quick start above) | the launcher window opens, text readable |
| 2 | Move around the launcher with the pad / Deck controls | the selection moves, A presses |
| 3 | Build tab: is the package found by itself (in `~/Downloads`)? | yes, with the license |
| 4 | BUILD GAME | finishes; note the time and any red line |
| 5 | Shader warm-up after the build | finishes or can be skipped |
| 6 | Play offline: intro movie | picture, or black with sound (START skips) |
| 7 | Title and menus | picture, sound, smooth |
| 8 | Arcade or VS fight | 60 fps? note the fps in fights, stage name |
| 9 | Sound during fights | music and hits, no crackle |
| 10 | Pad in the game (Deck controls, or a DualSense / Xbox pad) | every button works |
| 11 | Close the game with the window's X or Esc | the launcher comes back |
| 12 | Check my problem | lists "Wine or Proton"; nothing red unless something failed |
| 13 | Report a problem -> Save | a zip appears on the Linux Desktop |
| 14 | Online: log in as guest, quick match against a friend (Windows or Linux) | match starts, both see the fight |
| 15 | Online fight | fps (rollback), lag, desync message? |
| 16 | A second match / rematch | starts again |
| 17 | If a newer version comes out: the launcher's update | updates and starts again |

Send the list with the report zip (step 13).

## Why things differ (for developers)

From the code audit of 1.2.0 (ps3recomp f17bcd3 + patches 0001..0112, launcher, tools). Nothing of this was run
on Linux.

| Area | Windows | Wine / Proton |
|---|---|---|
| Window | null backend window, GDI-painted `RGB(0,0,64)` until the D3D12 renderer takes over (`rsx_null_backend.c`, `boot_main.cpp`) | a renderer that fails to start leaves that dark blue |
| Direct3D 12 | the driver | Proton: vkd3d-proton; plain Wine: Wine's vkd3d (not enough) |
| HLSL compiler (`D3DCompile`, every guest shader at run time; t5dr.exe imports `d3dcompiler_47.dll`, the release does not ship it) | Windows' own | Wine's own (vkd3d-shader) unless Microsoft's is installed (protontricks) |
| Display lock (`PS3_DISPLAY_LOCK`, `DwmGetCompositionTimingInfo`) | real vblank clock | Wine reports a synthetic clock; the lock follows it (no gain) |
| Movies (Media Foundation H.264) | Windows' decoder | Valve Proton: maybe none (black movie, sound, START skips: the 0053 fallback); GE-Proton: gstreamer with codecs |
| Sound (WASAPI) | | winepulse (PipeWire/PulseAudio); device-change notifications may not come, the 1 s poll covers it |
| Timers, WaitOnAddress, high-resolution waitable timers | | implemented (futex); the unknown-flag fallback exists anyway |
| CPU sets, EcoQoS, ideal processors, thread priorities (`host_sched.c`) | used | mostly ignored: thread placement does nothing |
| Rollback snapshots (`MEM_WRITE_WATCH` / `GetWriteWatch`) | kernel dirty bits | page protection + one fault per first write to a page per frame: more CPU per online frame |
| Guest memory demand commit (vectored exception handler) | | a signal per first touch of a 64 KB block (boot only) |
| Controllers (XInput, DirectInput, direct HID for PlayStation pads) | | Steam Input: a virtual Xbox pad (the Deck's controls too) on port 1; Steam-listed PS pads are left to Steam already |
| BUILD GAME (bundled Python 3.12 + pycryptodome, multiprocessing lift, bundled clang-cl + lld-link) | | plain 64-bit Windows programs; they should run under Wine, slower. Not tried |
| AVX2 check for the lifted code (`IsProcessorFeaturePresent(40)`) | | modern Wine reports it; if not, the baseline build (same results, slower) |
| Known folders (Desktop, Downloads) | the user's | Proton: `C:\users\steamuser\...` inside compatdata -> since 1.2.0 the Linux folders (WINEHOMEDIR, user-dirs.dirs) |
| Firewall check (registry, netsh) | Windows Firewall | no rules -> "unknown" -> no hint |
| Router address for UPnP / NAT-PMP (`route print`) | route.exe | since 1.2.0 `Z:\proc\net\route` |
| Lobby TLS | pinned fingerprint | the same; the updater uses Wine's root store (from the Linux certificates) |
