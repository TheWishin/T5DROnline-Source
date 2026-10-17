# Troubleshooting

This is a test release. It was tested on one development PC only (Windows 11,
16-core Ryzen 9). Fixes marked **(untested)** are standard advice that we have
not tried on this project. Everything else comes from the code, the launcher or
our QA run on 2026-10-16.

Contents:

- [Where things are](#where-things-are)
- [Building the game](#building-the-game)
- [The launcher does not start](#the-launcher-does-not-start)
- [SmartScreen and antivirus](#smartscreen-and-antivirus)
- [The Play tab](#the-play-tab)
- [The game starts, but...](#the-game-starts-but)
- [No sound](#no-sound)
- [Controllers and keyboard](#controllers-and-keyboard)
- [Online play](#online-play)
- [Windows versions and other PCs](#windows-versions-and-other-pcs)
- [Low frame rate](#low-frame-rate)
- [White screen or crash after a few minutes](#white-screen-or-crash-after-a-few-minutes)
- [Saves](#saves)
- [Other known problems](#other-known-problems)
- [How to collect logs](#how-to-collect-logs)

## Where things are

In the folder where you extracted the release (say `C:\T5DR`):

| Path | What it is |
|---|---|
| `T5DR Online.exe` | The launcher's starter. |
| `launcher.json` | The launcher's settings (made on first use). |
| `native\` | Everything built from your copy. Game data. Do not share it. |
| `native\build.log` | The log of the last build. Overwritten by every build. |
| `native\logs\game-<date>-<time>.log` | One log per game start. The last 10 are kept. |
| `native\gamedata\` | Your saves. |
| `native\controls.ini` | Your own control settings (optional, you make it). |
| `native\game\`, `native\build\`, `native\keys\` | Unpacked game, build output, key file. Game data. |

To start over completely, delete `native\` (you lose your saves: copy
`native\gamedata` first).

## Building the game

The launcher shows one red sentence when the build stops. Find it here. The
steps and times are in the [README](../README.md).

### "This copy is a different version of the game"

The port supports exactly one program: **TEKKEN 5 DARK RESURRECTION ONLINE, US
PSN, `NPUB30009`, version 01.00.** The builder checks it within seconds and
refuses everything else. Not supported: disc copies, other regions, other
versions or updates.

How to tell what you have: choose the `.pkg` in the Build tab. The line under it
shows the content ID and size.

- Green check, "the supported version": content ID
  `UP0700-NPUB30009_00-UPDATE0000010000`, size 619,430,240 bytes. This is right.
- Yellow warning "Tekken 5 DR, but not the supported package": the right game,
  a different version. There is no workaround. The port supports only this one
  version today.

### "This package is ... The port needs ..."

The `.pkg` is another game (or an add-on or theme). Choose the right file.

### "The license (.rap) does not belong to this package"

The `.rap` is for another package. Use the one whose name contains the
package's content ID:
`UP0700-NPUB30009_00-UPDATE0000010000.rap`. It is exactly 16 bytes.

### "Choose your license file (.rap) first" or "is not a PS3 license"

The build cannot run without the `.rap`. It is the license of your own purchase.
We cannot provide it. On a PS3 that has the game activated, licenses are stored
in the user's `exdata` folder (**untested**: general PS3 knowledge, not
checked by us).

"A .rap file is exactly 16 bytes" means the file is damaged, or it is not a
`.rap` (for example a web page saved under that name).

### "Decrypting the game program failed"

Usually the package is incomplete. It should be exactly **619,430,240 bytes**.
Download it again from your account. If the size is right, send `native\build.log`.

### "Could not download the public PS3 key data from github.com"

The first build fetches about 50 KB (two text files) from
`raw.githubusercontent.com`. Check the internet connection. A VPN, proxy,
firewall or antivirus "web shield" may block it. Press BUILD GAME again once it
works. The build continues where it stopped.

### "The ps3recomp copy in this folder does not match this version of the port"

Parts of two different releases are mixed in one folder. Download the release
again and extract it into an **empty** folder. To keep your game data, copy only
the `native` folder over (see "Updating" in the README).

### "clang-cl.exe and lld-link.exe were not found in toolchain\llvm\bin"

The zip was not extracted completely, or antivirus removed files. Extract the
whole zip again into an empty folder. See [SmartScreen and
antivirus](#smartscreen-and-antivirus).

### "step ... failed: a tool exited with code N"

Something in the build failed. The lines above the message in the Build tab's
log say what. Open `native\build.log` (button **Open build.log**) and send it.
Try "Redo every step" once if you suspect a damaged earlier result.

### The build is slow, or the PC is unresponsive

The translate step uses all CPU cores. Tick **Keep the PC responsive (slower)**
before you start. Close other programs. Disk space: you need about 1.5 GB free.
The build takes about 90 seconds on a fast 16-core PC. On slower PCs we expect
minutes (an estimate). It runs once. **Cancel** is safe: BUILD GAME continues
where it stopped.

### Which folder? (a warning in the Build tab)

Any folder you can write to works, on any drive (tested: `D:\`), also with
spaces and letters like `ü`, `Ł` or `東京` in its name or in your Windows user
name (tested: `D:\...\Tekken Früh Ł東京`, with `TEMP` and `LOCALAPPDATA` under
`Jürgen Ä Ł`). The Build tab shows a yellow warning for these cases:

- **"...has a long path"**: Windows allows 260 characters for a file path, and
  the build writes files about 100 characters below the folder. Move the folder
  to a short path such as `C:\Games\T5DR`. Tested: a folder path of 155
  characters works; with 213 the build stops with "The folder path is too long
  for Windows". Windows' own zip extraction may fail even earlier: the zip
  holds paths of up to about 110 characters.
- **"...is inside OneDrive"**: OneDrive would upload about 1 GB of game data
  and can lock files while the build writes them. Move the folder out of
  OneDrive. (A `.pkg` on a OneDrive Desktop or Documents is fine: the launcher
  finds it there too. Files that are only in the cloud are skipped by the
  automatic search; choose them with Browse.)
- **"...is in Program Files"** or **"Windows does not let the launcher write
  into this folder"**: use a folder of your own.
- **"...is on a network share"**: slow, not tested. Copy it to a local drive.

### Developer build: "C++ build tools ... are not installed"

This only applies to a checkout from source (no `runtime\t5dr.exe`). Click
**Install missing...** in the Build tab. It runs winget to install Visual Studio
2022 Build Tools (about 2.5 GB download, about 7 GB on disk, administrator
rights, 10-20 minutes). A release zip does not need this.

## The launcher does not start

`T5DR Online.exe` starts `python\pythonw.exe launcher\t5dr_launcher.pyw` from its
own folder. If that fails, it shows: "Could not start the launcher. The folder
must contain python\pythonw.exe and launcher\t5dr_launcher.pyw -- extract the
whole zip again."

- Did you run it from inside the zip viewer? Extract all first.
- Did antivirus remove `python\` files? Restore them, or extract again.
- Is the folder in Program Files? Use another folder.

## SmartScreen and antivirus

**"Windows protected your PC" when you start `T5DR Online.exe`.** The file is a
tiny starter (3.5 KB; its source is `launcher/stub/t5dr_stub.c` in the
repository) and it is not signed. Code signing is not set up yet. Click "More info", then "Run anyway".

**Antivirus complains or deletes files.** The release holds a compiler
(`toolchain\llvm\bin\clang-cl.exe`, `lld-link.exe`), a private Python and, after
the build, a 39 MB `t5dr_game.dll` that your own PC just compiled. Unsigned
programs like these can trigger a scanner. On the development PC this did not
happen, but we have not run the zip on other PCs yet. **(untested)**

What to do:

1. Look in your antivirus' quarantine list. Restore what is from the release
   folder.
2. Add an exclusion for the release folder only (for example `C:\T5DR`). Do not
   switch your antivirus off.
3. Extract the zip again if files are missing, and press BUILD GAME.

If you do not trust the zip, do not run it. All source is public: this
repository holds our code and our patches, and ps3recomp is on GitHub too. You
can build everything yourself (see "Building from source" in the README).

## The Play tab

| Message | What to do |
|---|---|
| "The game is not built yet." | Open the Build tab, choose `.pkg` and `.rap`, click BUILD GAME. |
| "t5dr.exe is there but the game data is missing." | Build again. |
| "The decrypted program has SHA-1 ..., not the supported version." | Build again from the supported package. |
| "This version of the launcher changes the game code." | Click BUILD GAME. Your game data is kept. Only the code is rebuilt. |
| PLAY is grey | The build is not finished or the check above failed. Read the text on the Play tab. |
| "Close the game first." (when you click BUILD GAME) | A game is still running. Click Stop game, or end `t5dr.exe` in the Task Manager. |

## The game starts, but...

### The window is black

The first seconds can be black while the game loads. If it stays black:

- **Start the game with PLAY in the launcher.** The launcher sets
  `RSX_LIVE_DRAW=1`. Without it the default renderer shows only black. If you
  start `t5dr.exe` by hand, it also lacks the other settings it needs.
- Open **Settings**, "extra settings". There must be no line `RSX_LIVE_DRAW=0`.
  Also check that you have no Windows environment variable called
  `RSX_LIVE_DRAW` set to something else.
- Update your graphics driver. The game needs a DirectX 12 card. Run `dxdiag`.
  On the Display tab, "DDI Version" should say 12. **(untested)**
- Laptops with two graphics chips: the game picks the fast (high-performance)
  chip by itself. If you set `t5dr.exe` in Windows Settings > System > Display >
  Graphics, that choice wins. The game log names the chip it uses: the line
  `[gpu] adapter: ...`.
- `RSX_ADAPTER=warp` (Settings, extra settings) draws with Windows' software
  renderer instead of the graphics card. It is slow, but shows whether the
  card or its driver is the problem. `RSX_ADAPTER=1` (or part of a name, like
  `RSX_ADAPTER=Intel`) picks another graphics chip.

### "The graphics card stopped working for the game"

The graphics driver crashed, was reset (Windows does that after about 2
seconds without an answer from the card), or was updated while the game ran.
Windows does not give the card back to a running game, so the game closes
with this message. Start it again. If it happens again: update the graphics
driver, close other programs that use the graphics card (browsers with videos,
recorders, overlays), and check that the PC does not overheat. Tested with a
simulated driver reset (`RSX_TEST_DEVICE_REMOVED`), not with a real one.

### "Direct3D 12 not available"

Windows found no graphics card that can run Direct3D 12 at feature level 11_0.
Install the newest driver from AMD, Intel or NVIDIA (Windows Update often
installs an old or a basic one). Remote desktop sessions and many virtual
machines cannot run the game.

### "This processor is too old" or "build the game again"

- **No SSE4.1**: processors before about 2008 (Intel) or 2011 (AMD) cannot run
  the game.
- **"This game build was made on a PC whose processor has AVX2"**: the
  `native` folder was built on a newer PC and copied here. Press BUILD GAME on
  this PC. The build checks the processor and makes code that runs on it. Your
  saves are kept.

### The window is not where I want it, or too big

Settings > Display. The window size options never exceed your screen's work
area. "Borderless fullscreen" is experimental and was not tested with the real
game window. The game draws at 1280 x 720 and scales up.

- **Display scaling (125 %, 150 %, 200 %)**: the window opens at 1280 x 720
  times the scaling (1920 x 1080 pixels at 150 %), as far as the screen
  allows. The picture stays sharp: Windows does not stretch it. Dragged to a
  monitor with other scaling, the window keeps its size on screen. Only checked
  at 100 % (the test PC has one monitor at 100 %).
- **Several monitors**: the game opens on the monitor the launcher window is
  on. Move the launcher first. Alt+Enter or F11 fills the monitor the game
  window is on. Not tested: the test PC has one monitor.
- **Alt+Tab**: borderless fullscreen (the default) switches like any window.
  With `PS3_FULLSCREEN=exclusive`, Alt+Tab leaves exclusive mode; Alt+Enter
  goes back. Not tested.

### High refresh rate (120/144/165 Hz), G-Sync/FreeSync, 50 Hz TVs

The game always runs at the PS3's speed: 59.94 frames per second, timed by
the PC's clock, never by the monitor.

- **Faster monitors** (75, 120, 144, 165, 240 Hz): the game speed stays the
  same. Each picture is shown at the next refresh. On 120 Hz every picture
  stays on screen for two refreshes: smooth. On 144 or 165 Hz pictures stay
  for 2 or 3 refreshes, which looks slightly uneven. For the smoothest picture
  set the monitor to 120 Hz or 60 Hz, or use G-Sync/FreeSync (VRR) in
  borderless fullscreen (Alt+Enter); then the monitor follows the game.
- **Slower monitors and TVs** (50 Hz, 30 Hz): the game used to slow down to
  the monitor's rate (50 Hz = 83 % speed). Now it keeps its speed and presents
  without waiting for the monitor; some pictures are skipped. The log says
  `[pacing] display 50 Hz: slower than the game's 59.94 Hz`.
- Tested with simulated 30, 50 and 144 Hz monitors (`RSX_TEST_DISPLAY_HZ`),
  not with real ones: the test PC has a 59.94 Hz monitor.

### The game closes by itself

The Play tab says "The game stopped (exit code N)..." and adds "after a crash"
when the log has a `[CRASH]` line. Open the newest game log (Play tab) and look
at the last lines. Then see [How to collect logs](#how-to-collect-logs).

Known causes:

- The memory bug (see below).
- The game's own **Online** menu entry crashes after the terms screen (known).
- Once in 8 test runs of the release build, the game ended by itself after about
  48 seconds with exit code -1 and no `[CRASH]` line. Not explained yet. If it
  happens to you, please send the log.

### The movies do not play

Intro and title movies are decoded with Windows Media Foundation. The Play tab
still says "Intro movies are skipped in this version". That text is out of date.
Movies play. Movies slow down when the game runs under 60 fps.

On Windows "N" editions (Europe/Korea) Media Foundation is missing until the
**Media Feature Pack** is installed (Settings > Apps > Optional features). The
game starts anyway; the movies stay black (with sound, START skips them) and
the log says `Windows Media Foundation (mfplat.dll) is not installed`. Before
this version `t5dr.exe` did not start at all there. Tested by simulating the
missing DLL (`PS3_TEST_NO_MEDIA_FOUNDATION=1`), not on a real N edition.

## No sound

The game plays through the **default Windows playback device** (WASAPI, shared
mode, 48 kHz; Windows converts other rates).

1. Right-click the speaker icon > Sound settings. Choose the device you want as
   the default output. The game follows the default device: if you plug in
   headphones, switch to Bluetooth or turn off an HDMI monitor while it runs, the
   sound moves to the new default within about a second. If Windows has no
   playback device at all, the game still runs normally, only silent. It looks
   for a device every 2 seconds and the sound starts when one appears. You do not
   need to restart the game for any of this.
2. Open the Volume Mixer while the game runs. `t5dr.exe` should appear. Check that
   it is not muted.
3. Settings > "Mute sound" must be off. (It sets `PS3_NO_AUDIO=1`, which tells the
   game that audio is not available.)
4. Open the newest game log and search for `[cellAudio] audio device`. Every change
   of the sound device gets one line (`t=` is the seconds since the game's audio
   started):
   - `audio device opened "Speakers (Realtek)" at 48000 Hz (...)`: sound plays on
     that device. The first number is the rate the game sends; "device mix" is the
     rate Windows runs the device at (Windows converts).
   - `audio device lost: AUDCLNT_E_DEVICE_INVALIDATED ...`: the device went away
     (unplugged, switched off, driver restart). The game keeps running and opens
     the default device again at once.
   - `audio device waiting: no audio device (E_NOTFOUND) (0x80070490)`: Windows
     has no playback device, or none is enabled (Sound settings > Output). The
     game runs silent and tries again every 2 seconds.
   - `default audio device changed, switching`: you changed the default; the next
     line names the new device.

   Other errors on the "waiting" line (`AUDCLNT_E_UNSUPPORTED_FORMAT`,
   `AUDCLNT_E_DEVICE_IN_USE`) mean Windows refused the device. Send the log.
5. Bluetooth headphones add delay. A wired output or speakers are safer.
6. Crackling: the sound drops a little when the frame rate dips (0.1-3.6 % of the
   audio blocks in our QA run, 14.6 % at worst in 5 seconds). See [Low frame
   rate](#low-frame-rate).

## Controllers and keyboard

Default keys and buttons are in the README. Pads are read even when the window is
not focused. The keyboard works only while the game window has the focus.

### A controller is not detected

- Plug it in. Pads can be plugged in or out while the game runs. A new pad takes
  the lowest free automatic port.
- Does Windows see it? Open `joy.cpl` ("Set up USB game controllers") and press a
  button.
- Xbox pads and XInput-mode sticks use XInput. Other controllers (DualShock 4,
  DualSense, Switch Pro, generic USB pads, PS3/PS4-mode arcade sticks and
  hitboxes) use DirectInput. Both are on by default.
- Look in the newest game log for the lines starting with `[pad]`. For example:
  `[pad] port 1 (player 1): XInput #0 (gamepad), layout standard`, or
  `[pad] found DInput 'name' VVVV:PPPP`. No `[pad]` line for your device means
  the game did not see it. The line `[pad] controls: ...` tells which
  `controls.ini` was loaded (or that the built-in defaults are used).
- Support for PlayStation pads and arcade sticks has **not been tried on real
  hardware by a person yet**. If yours fails, please send the log.
- A test zip made before the evening of 2026-10-16 has only keyboard and Xbox
  pads.

### The buttons are wrong, or I want other buttons

Make `native\controls.ini` (the sample with every default and all key names is
[controls.ini](controls.ini)) and restart the game. To see the raw button names
of an unknown pad, add this line under "extra settings" in the launcher's Settings
and start the game:

```
PS3_PAD_LOG=2
```

The log then prints each press, for example `[pad] port 2 Wireless Controller: B6
pressed -> R1`. Use the `B6`-style names in `controls.ini`. For one pad model use
a section named like `[dinput.0F0D:00EE]` (vendor:product IDs, shown in the
`[pad] found DInput` log lines).

### Two pads, or my pad acts as player 1 *and* player 2 (DS4Windows, Steam Input)

DS4Windows and Steam Input add a **virtual Xbox pad** for your real controller.
The real controller is still visible as a DirectInput device, so the game sees
two pads. Pick one of these:

1. In DS4Windows, turn on "Hide DS4 Controller". Or close DS4Windows and use the
   DualShock/DualSense directly (DirectInput, layout "ps"). Nothing has to be
   installed. **(untested with this game)**
2. Turn off Steam Input for the launcher if you started it from Steam.
   **(untested)**
3. Pin the ports in `native\controls.ini`:

   ```
   [port1]
   device = xinput:0
   [port2]
   device = none
   ```

   Pin a specific pad with `device = dinput:Hori` (part of the product name) or
   `device = dinput:054C:09CC` (vendor:product ID).

For two real players, pin each pad to its own port:

```
[port1]
device = dinput:Hori
[port2]
device = xinput:0
```

### The keyboard does nothing

The game window needs the focus: click it. Keyboard and the first pad both drive
player 1. For a second player on the same keyboard, see the README.

### Pad input goes into the game while I use another window

Pads are read while the window is unfocused by default. Put this in
`native\controls.ini`:

```
[general]
background = 0
```

### Left and right (or up and down) at the same time

Arcade sticks and keyboards can press opposite directions at once. The default
`socd = neutral` cancels them. Other choices are in
[controls.ini](controls.ini).

## Online play

How a match goes: **Online** tab, pick the server (the public one is the
default), type a name and click **Play as guest** (accounts are needed for
ranked matches only), pick a character, click **Quick match**. When an opponent
is found both of you get a bar with the ping and **Accept** / **Decline**. You
have 15 seconds. Then the game opens by itself, straight in the fight (first to
three rounds). The result is sent to the lobby by itself. After the match the
game stays open at the character select, and the bar offers a **Rematch**.
Closing the game ends the session with that opponent.

### Windows asks whether `t5dr.exe` may use the network

The first time a game starts a match, Windows Firewall shows "Do you want to
allow public and private networks to access this app?" for `t5dr.exe`
(publisher "unknown": the program is not signed). Click **Allow**. The window can
open behind the (minimized) game window or only flash on the taskbar; look for
it if the match does not start. Windows asks once per folder the program runs
from, so a new release extracted to a new folder asks again. If you clicked
Cancel, Windows keeps blocking incoming packets for that program: open Windows
Security > Firewall & network protection > Allow an app through firewall and
tick `t5dr.exe` for private networks. The launcher does not need administrator
rights, and neither does the game. Windows itself asks for them only if you
change the firewall. (We did not test a match with the firewall left blocking.)

### "Lobby: ..." or "Lobby error: ..." when you log in

The launcher could not talk to the lobby server. Check the internet connection;
the lobby uses TCP port 7781 and UDP ports 7781 and 7782 (outgoing). A
company or school network, a VPN or an antivirus "network shield" may block
them. If the server is down, the Online tab says so; try again later or use a
friend's server (README, "Online"). **(untested)**

### The match is found but the game does not start, or the status bar says...

| Message | What it means |
|---|---|
| "Nobody accepted in time." | One of you did not click Accept within 15 seconds. Search again. |
| "No UDP connection to the lobby server (firewall?)." | UDP 7781/7782 to the server is blocked. Allow `t5dr.exe` (and, if Windows asks, the launcher's `python\pythonw.exe`) through the firewall, or leave the VPN. |
| "Could not connect the two PCs, not even through the relay." | Neither a direct connection nor the lobby's relay worked. Same checks; then try again. |
| "Your opponent's game could not be reached (firewall or router?)." | The game on the other side did not answer. They may have closed it, or their firewall prompt is still open. |
| "Your opponent's game is a different build." | You do not run the same release. See below. |
| "Your opponent closed the game." / "The connection to your opponent's game was lost." | The match ended early. It is not counted as a win for the one who left. |

### I never get matched / the lobby shows "other build"

You are only matched with players who have the same build: the same release
**and** a build made from it. After you update to a new release, click BUILD
GAME again (the Play tab tells you). Ask your opponent to do the same.

### Lag during an online match

A match needs a steady connection more than a fast one: the two games advance in
lockstep, so a late packet makes both wait. The lobby suggests an input delay from
the measured ping (2 frames on one PC or LAN, 3 at about 40 ms, 5 at about 100
ms). Use a cable instead of Wi-Fi, stop downloads, and close other games. The
result bar can show how many frames behind a match was.

## Windows versions and other PCs

- **Windows 10 version 1909 or newer, Windows 11**: supported. Nothing has to
  be installed: the game and its compiler bring their own C runtime, the
  launcher its own Python. Only the test PC (Windows 11) was tried.
- **Windows 10 before 1909, Windows 8.1, 7**: not supported. Folders with
  characters outside your Windows language (for example `Ł` on a German
  Windows) need 1903 or newer.
- **Windows on ARM** (Snapdragon laptops): not tested, we have no such PC.
  What we expect: Windows 11 (24H2 or newer) runs the launcher, the compiler
  and the game through its x64 emulation; the build takes longer, and the game
  may not reach 60 fps in fights. The graphics chip there supports Direct3D 12.
  If the emulation hides AVX2, the build makes code without it by itself.
  Windows 10 on ARM cannot run 64-bit x64 programs at all, so the game does not
  run there.
- **Virtual machines and remote desktop**: usually no Direct3D 12 graphics
  card; the game says "Direct3D 12 not available".

## Low frame rate

Menus run at 60 fps. Fights ran at 59.7-59.9 fps in the release dry run of
2026-10-17 (two games on one PC with other test programs running). Earlier notes
said 30-45 fps; that was fixed by later work. On a weaker PC:

- **Weak graphics card** (laptop, integrated graphics): in the launcher,
  **Settings** -> **3D resolution** -> **Lower**, or **Lowest** if that is not
  enough. The picture gets softer; the game itself does not change, so you can
  play online against someone who uses Original.
- **Few CPU cores**: the game sets its number of helper threads to the cores
  it may use; there is nothing to set. In our tests (fast desktop cores held to
  4-8 threads) fights ran at 60 fps from 4 threads up. Online against a far-away
  player (150 ms) rollback costs more: about 50 fps with 4-8 threads while
  other programs were running. Online, both games run at the speed of the
  slower PC, so close other programs on both.

What may help as well:

- Close other programs, especially browsers, game overlays and recorders.
- Do not build the game while playing. Do not run a second copy.
- Laptops: plug in the charger and choose the "High performance" power mode.
  Make sure the game uses the fast graphics chip (see [The window is
  black](#the-window-is-black)). **(untested)**
- Slow frame rates also make the movies slow and the sound drop out (see [No
  sound](#no-sound)).

## White screen or crash after a few minutes

**Known memory bug.** When the game leaves a screen it frees memory, but our
runtime does not reuse the freed ranges yet. After about two trips through the
title screen, the third large request fails. The result is a white screen (the
game keeps running at 60 fps) or a crash (`[CRASH]` in the log). Leaving the game
idle at the title or attract screen reaches the same state after about 3 minutes.

- **Workaround: close the game (Esc or Stop game) and start it again.** Your
  settings are kept. Save before you leave a mode (see [Saves](#saves)).
- Go back to the title as little as you can. A 10-minute Survival run that never
  went back to the title stayed stable (memory flat after about 6 minutes).
- Do not leave the game idle at the title.
- A fix is in progress.

## Saves

Saves live in `native\gamedata\dev_hdd0\home\00000001\savedata\`. In the Play
tab, **Open saves folder** opens `native\gamedata`. Folder names look like
`NPUB30009-SYSNET` (system data) and `NPUB30009-CN1970...` (play data).

Known problems (from our QA run):

- **The first save on a fresh profile can fail silently.** The folder is left with
  only a `PARAM.SFO`, and the next start says "Unable to load Play Data". On a
  fresh profile, the online terms screen may say "Unable to save properly". Saves
  did work in other tests (saved and reloaded). Our runtime lacks a system call
  that the save code needs.
- **The clock reads 1970.** New save folders with `1970` in their name keep
  appearing.
- **Options > Delete Save Data does nothing.**

What to do:

- Back up `native\gamedata` now and then. Copying `native` to a new release folder
  keeps your saves.
- If "Unable to load Play Data" appears: close the game, back up
  `native\gamedata`, and delete the save folders that hold only a `PARAM.SFO`.
  **(untested)** Then start the game again.
- To delete a save, close the game and delete its folder by hand. **(untested)**

## Other known problems

From our QA report of 2026-10-16. None of these is a problem with your PC.

- **Every fighter's face is dark** (brown or black). The rest of the skin is fine.
- **Light see-through rectangles** on floors and walls in some fights (temple,
  Chinatown). They move with the camera.
- **Some background figures are flat white** (spectators at the construction site,
  wolves in the forest).
- **Gallery** needs PSN. Offline it fails cleanly (no crash). The Online Manual
  (it opens a browser) is missing.
- **Online** (the game's own menu): crashes after you accept the terms. Do not use
  it. See "Online" in the README.

## How to collect logs

1. Close the game. (The launcher keeps the log of each start.)
2. Build problem: open `native\build.log` (Build tab, **Open build.log**). It is
   overwritten by the next build: copy it first.
3. Game problem: open the newest `native\logs\game-<date>-<time>.log` (Play tab,
   **Open newest game log**).
4. In the game log, these lines matter:
   - `[CRASH]` — the game crashed. The lines after it say where.
   - `[fps]` — one line every 5 seconds with the frame rate.
   - `[hle] unresolved NID 0x...` — a system function that is not implemented yet.
   - `[pad]` — what the game sees as controllers.
   - `[cellAudio]` — sound device problems.
5. Write down: your Windows version, graphics card and driver version, what you
   were doing, and how long the game had been running.
6. Open an issue at https://github.com/TheWishin/T5DROnline/issues and attach the
   files (zip a large log first).

The logs contain no game data and no keys. They contain folder paths, which can
include your Windows user name. Look before you post them in public.

**Do not send** anything from `native\game\`, `native\build\` or `native\keys\`,
or your `.pkg` / `.rap`. Those are game data and keys.

For more detail in a log, the **extra settings** box in Settings accepts one
`NAME=VALUE` per line. `PS3_PAD_LOG=1` (or `2`) logs controller input.
`PS3_VERBOSE=1` logs a lot more but slows the game a lot (about 34 fps in an
earlier test), so use it only when asked.
