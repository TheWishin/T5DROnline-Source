# Troubleshooting

This is a test release. It was tested on one development PC only (Windows 11,
16-core Ryzen 9). Fixes marked **(untested)** are standard advice that we have
not tried on this project. Everything else comes from the code, the launcher or
our QA run on 2026-10-16.

**Problems? Click "Report a problem"** (launcher, Play offline tab; also in the Build tab
and in the Online tab after a match). It makes one zip on your Desktop. Send the
zip to the person who gave you the game, or attach it to an issue at
https://github.com/TheWishin/T5DROnline/issues. Details:
[How to collect logs](#how-to-collect-logs).

Contents:

- [Where things are](#where-things-are)
- [Building the game](#building-the-game)
- [The launcher does not start](#the-launcher-does-not-start)
- [Updates](#updates)
- [SmartScreen and antivirus](#smartscreen-and-antivirus)
- [The Play offline tab](#the-play-offline-tab)
- [The game starts, but...](#the-game-starts-but)
- [No sound](#no-sound)
- [Controllers and keyboard](#controllers-and-keyboard)
- [Online play](#online-play)
- [Windows versions and other PCs](#windows-versions-and-other-pcs)
- [Low frame rate](#low-frame-rate) -- also [Game speeds up or slows down on a laptop or handheld](#game-speeds-up-or-slows-down-on-a-laptop-or-handheld)
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
| `launcher.log` | What the launcher did and saw (builds, game starts and exits, errors, status messages). The last two runs' worth; `launcher.log.1` is the older part. |
| `T5DR-report-<date>-<time>.zip` | A problem report, on your Desktop (see [How to collect logs](#how-to-collect-logs)). |
| `native\` | Everything built from your copy. Game data. Do not share it. |
| `native\build.log` | The log of the last build. Overwritten by every build. |
| `native\logs\game-<date>-<time>.log` | One log per game start. The last 10 are kept. |
| `native\gamedata\` | Your saves. |
| `native\controls.ini` | Your own control settings (optional). The launcher's Settings -> Set up controllers... writes it; you can edit it by hand too. |
| `native\game\`, `native\build\`, `native\keys\` | Unpacked game, build output, key file. Game data. |
| `native\logs\update-<date>-<time>.log` | What the last self-update did (one per update). |
| `update-check.json` | When the launcher last asked GitHub for a new version. |
| `C:\T5DR.update\` | Only while an update is installed, next to your folder. Removed afterwards. |

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

The translate step uses up to 8 CPU cores (fewer when little memory is free).
Tick **Keep the PC responsive (slower)** before you start. Close other programs. Disk space: you need about 1.5 GB free.
The build takes about 90 seconds on a fast 16-core PC. On slower PCs we expect
minutes (an estimate). It runs once. **Cancel** is safe: BUILD GAME continues
where it stopped.

### The build stops at "Translate code"

"Translate code" runs several helper processes side by side. Up to 1.1.1, an
antivirus or a lack of free memory could stop one of them, and the build then
waited for it for ever (a player's build sat at 68 %). Since 1.1.2 the build
notices and does that part itself; the result is the same. What the log shows:

- `jobs: 6 -- 8 processors, only 1.8 GB free memory: ...`: how many helpers it
  starts and why. With little free memory it starts fewer, or none
  (`serial lift`: one process does everything, a bit slower).
- `... still lifting: 3 chunks left, elapsed 1.5m`: about every 30 seconds while
  it works. Wait.
- `parallel lift: worker process 2 stopped ...` or `no chunk finished for ...`:
  a helper stopped or got stuck. The build goes on by itself.

If the log prints nothing at all for 3 minutes, the Build tab says so. Close
other programs (browser, games) to free memory and wait a little. If nothing
changes, press **Cancel**, then **BUILD GAME** again. If it happens again,
send `native\build.log` (**Report a problem...**) and look at
[SmartScreen and antivirus](#smartscreen-and-antivirus).

### The build fails at "Compile"

"Compile" runs one compiler per processor, but only as many as fit in the free
memory (about 1 GB each; one needs at most about 0.6 GB). Since 1.1.3 a file
that fails is compiled once more at the end, alone, and the build goes on if
that works (a lack of memory or an antivirus scan can make one attempt fail).
What the log shows:

- `jobs: 8 -- 12 processors, only 9.7 GB free memory: ...`: how many compilers
  run at once and why.
- `[2/22] ppu_recomp_002.cpp: 5.7 s FAILED (exit code 1)`, then the compiler's
  error lines and its last lines, then `full output: ...\gamedll_obj\<file>.log`.
- `compiled on the second try`: it worked; nothing to do.

If it fails twice, close other programs and press **BUILD GAME** again. If it
fails again, press **Report a problem...**: the report includes the compiler's
messages for the files that failed (`file(line,col): error: ...`, never a line of
the game's code: the compiler does not quote it, and the report keeps only those
message lines of the compiler's output and of build.log).

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

## Updates

The launcher looks for a new version at start (at most once an hour) and when
you click **Check for updates**. It only offers releases that are published on
https://github.com/TheWishin/T5DROnline/releases. How it works: README,
"Updating".

**"Could not check for updates."** No connection to GitHub (offline, a
firewall, a proxy), or GitHub limits checks for a while ("Try again later";
GitHub allows 60 checks an hour per internet connection). Nothing is wrong
with your install. Try again later, or look at the releases page yourself.

**The update window says the game, a build or an online match is running.**
The launcher never updates while the game, a build, an online match or a
search, or **Host for friends** runs. Finish or stop it, then click the update
button at the top again. "Other programs from this folder are still running"
means a second launcher window, a game or a lobby server started from this
folder: close it (or end it in the Task Manager).

**"The download is damaged or not the published file" / "SHA256SUMS ..."**
The downloaded zip did not match the published checksum. Nothing was changed.
Try again; if it keeps happening, download the zip from the releases page and
update by hand (README, "Updating").

**"Not enough free disk space."** The update needs about 600 MB free on the
drive of the launcher's folder for a moment (download, unpacked copy). Free
some space and try again.

**"The launcher cannot write next to its folder or into it."** The folder is
read-only for your Windows user (for example in Program Files). Move the whole
folder to one of your own, for example `C:\Games\T5DR`, then update.

**"The update to ... did not work" after the launcher restarted.** The
launcher put the old files back and starts as the old version; the message says
why (a file held by antivirus, the new launcher did not start, ...). Your
`native` folder was never touched. `native\logs\update-<date>-<time>.log` has
the details; please attach it to a bug report.

**The launcher does not come back after an update** (rare: the PC was switched
off in the middle of it). An update never touches your `native` folder. If a
folder named like yours plus `.update` (for example `C:\T5DR.update`) exists
next to it, its `backup` folder holds the old program files. Easiest fix:
extract the newest release zip over your folder (say yes to replacing files);
`native` and your settings stay. Then delete the `.update` folder.

**The game asks to be built again after an update.** The new version changed
the game code: the Play offline tab says "Build the game once (about 2 minutes)". Click
**BUILD GAME**. The unpacked game and your saves are kept.

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

## The Play offline tab

| Message | What to do |
|---|---|
| "The game is not built yet." | Open the Build tab, choose `.pkg` and `.rap`, click BUILD GAME. |
| "t5dr.exe is there but the game data is missing." | Build again. |
| "The decrypted program has SHA-1 ..., not the supported version." | Build again from the supported package. |
| "Build the game once (about 2 minutes)" (after an update) | Click BUILD GAME on the Play offline tab. Your game data and saves are kept. Only the code is rebuilt. |
| PLAY OFFLINE is grey | The build is not finished or the check above failed. Read the text on the Play offline tab. |
| "Close the game first." (when you click BUILD GAME) | A game is still running. Click Stop game, or end `t5dr.exe` in the Task Manager. |

## The game starts, but...

### The window is black

The first seconds can be black while the game loads. If it stays black:

- **Start the game with PLAY OFFLINE in the launcher.** The launcher sets
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
area. "Borderless fullscreen" starts the game in its own borderless
fullscreen (the same as Alt+Enter or F11 in the game: Esc or Alt+Enter goes
back to a window). The picture is scaled to the window with its 16:9 shape
kept (black bars on 16:10 or ultra-wide screens); how sharp it is depends on
Settings > Internal resolution, not on the window size (see [The picture is
blurry](#the-picture-is-blurry-on-a-big-screen)).

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

### The picture is blurry on a big screen

The game draws at the PS3's 1280 x 720 (Settings > Internal resolution:
Native) and scales that up to the window. On a 1920 x 1080 or larger screen,
in fullscreen or a big window, that looks soft. Choose the step that matches
your screen (the launcher names it under Internal resolution): **1080p** for
1920 x 1080, **1440p** for 2560 x 1440, **4K** for 3840 x 2160. Higher steps
need a stronger graphics card (2.25, 4 and 9 times the pixels of Native; an
RTX 3090 needs 1-2 ms of a 16.7 ms frame at 4K); if fights drop below 60 fps,
go one step down. A step larger than the window is
fine too: the picture is then scaled down with a filter, which smooths edges
(like anti-aliasing). The other player online may use any step; the game
itself is the same.

- **Lower** and **Lowest** only draw the 3D scene smaller; the health bars,
  names and menus stay at full sharpness.
- The log names the step: `[display] internal resolution 1440p (2x) ...`, and
  the window title shows it.
- Old settings `PS3_RES_SCALE` and `PS3_RENDER_SCALE` (extra settings) still
  work and mean the same; `PS3_INTERNAL_RES` (what the launcher sets) wins
  when both are there.

### High refresh rate (120/144/165 Hz), G-Sync/FreeSync, 50 Hz TVs

The game runs at the PS3's speed: 59.94 frames per second, timed by the
PC's clock -- except on a 60 Hz monitor, where it follows the monitor.

- **60 Hz monitors** (59.94 or 60 Hz, vsync on): the game times its frames by
  the monitor's own refresh, like a PS3 on that TV (59.94 or 60.00 frames per
  second), and starts each frame just early enough to show it at the next
  refresh: a press reaches the screen about a frame sooner than before. The
  log says `[pacing] display lock on`. If the picture stutters on your PC,
  Settings -> "Advanced: extra settings" -> `PS3_DISPLAY_LOCK=0` brings back
  the PC clock (docs/RENDER_PERF.md "Input latency").
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

The Play offline tab says "The game stopped (exit code N)..." and adds "after a crash"
when the log has a `[CRASH]` line. Open the newest game log (Play offline tab) and look
at the last lines. Then see [How to collect logs](#how-to-collect-logs).

Known causes:

- The memory bug (see below).
- Once in 8 test runs of the release build, the game ended by itself after about
  48 seconds with exit code -1 and no `[CRASH]` line. Not explained yet. If it
  happens to you, please send the log.

### The movies do not play

Intro and title movies are decoded with Windows Media Foundation. The Play offline tab
still says "Intro movies are skipped in this version". That text is out of date.
Movies play. Movies slow down when the game runs under 60 fps.

On Windows "N" editions (Europe/Korea) Media Foundation is missing until the
**Media Feature Pack** is installed (Settings > Apps > Optional features). The
game starts anyway; the movies stay black (with sound, START skips them) and
the log says `Windows Media Foundation (mfplat.dll) is not installed`. Before
this version `t5dr.exe` did not start at all there. Tested by simulating the
missing DLL (`PS3_TEST_NO_MEDIA_FOUNDATION=1`), not on a real N edition.

**White screen at the intro movie, START does nothing** (1.1.1 and older, rare: seen
on a PC short of memory and processors). The video decoder did not answer, so the
game waited for it for ever. Since 1.1.2 the decoder is started while the game boots,
and if it still does not answer within 5 seconds the movie goes on black with its
sound: START skips it, and the game goes on as usual. The log then says
`the H.264 decoder has not answered for ... ms`. Later movies try the decoder again.
`PS3_VDEC_STALL_MS` changes the 5 seconds (0 = wait for ever, as before).

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
6. Crackling or sound that breaks up: search the log for `[cellAudio] sound
   glitches`. The line appears when 5 or more audio blocks in 5 seconds came too
   late from the game's sound engine (or the device ran dry), and counts them.
   The game's sound engine needs one processor core for itself all the time;
   if other programs keep the processor busy (a game, a browser with video, a
   virus scan, a build), close them. Builds with patch 0041 need about 40 % less
   of that core for the sound, so 6-core PCs from 2018-2019 keep up. A low
   frame rate makes it worse too: see [Low frame
   rate](#low-frame-rate).

## Controllers and keyboard

Default keys and buttons are in the README. Pads are read even when the window is
not focused. The keyboard works only while the game window has the focus.

### A controller is not detected

- Plug it in. Pads can be plugged in or out while the game runs. A new pad takes
  the lowest free automatic port.
- Does Windows see it? Open `joy.cpl` ("Set up USB game controllers") and press a
  button.
- Xbox pads and XInput-mode sticks use XInput. DualShock 4 and DualSense are
  read directly (see [PlayStation controllers and
  Steam](#playstation-controllers-dualshock-4-dualsense-and-steam)). Other
  controllers (Switch Pro, generic USB pads, PS3/PS4-mode arcade sticks and
  hitboxes) use DirectInput. All are on by default.
- Look in the newest game log for the lines starting with `[pad]`. For example:
  `[pad] port 1 (player 1): XInput #0 (gamepad), layout standard`,
  `[pad] found HID 'DualSense Wireless Controller' 054C:0CE6 (DualSense, Bluetooth), read directly`,
  or `[pad] found DInput 'name' VVVV:PPPP`. No `[pad]` line for your device means
  the game did not see it. The line `[pad] controls: ...` tells which
  `controls.ini` was loaded (or that the built-in defaults are used).
- Support for PlayStation pads and arcade sticks has **not been tried on real
  hardware by a person yet**. If yours fails, please send the log.
- A test zip made before the evening of 2026-10-16 has only keyboard and Xbox
  pads.

### The buttons are wrong, or I want other buttons

Use the launcher: **Settings** -> **Set up controllers...** (see the README,
"Controls"), for pads, sticks and the keyboard (click the keyboard's row). Every
PS3 button (L1 R1 L2 R2 L3 R3 Start Select) and every Tekken combo can have a key
or button of its own. It writes `native\controls.ini` for you and keeps what is
already in that file. The rest of this section is for editing the file by hand.

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
`[pad] found DInput` and `[pad] found HID` log lines). A DualShock 4 or DualSense
has the names DirectInput gives it: B1 Square, B2 Cross, B3 Circle, B4 Triangle,
B5 L1, B6 R1, B7 L2, B8 R2, B9 Share/Create, B10 Options, B11 L3, B12 R3, B13 PS,
B14 touchpad click; the game also reads B15 = mute (DualSense) and B16-B19 = the
DualSense Edge's Fn buttons and back paddles (left Fn, right Fn, left paddle,
right paddle).

### PlayStation controllers (DualShock 4, DualSense) and Steam

Since 1.1.1 the game reads DualShock 4, DualSense and DualSense Edge itself, over
USB and Bluetooth. **Steam is not needed**, and it does not matter whether Steam
or DS4Windows used the pad before. The log shows it:

```
[pad] found HID 'DualSense Wireless Controller' 054C:0CE6 (DualSense, Bluetooth), read directly
[pad] port 1 (player 1): HID 'DualSense Wireless Controller' 054C:0CE6 (DualSense, Bluetooth), layout ps
[pad] HID 'DualSense Wireless Controller': Bluetooth extended reports (0x31)
```

- **Why it "only worked through Steam" before.** Over Bluetooth these pads first
  send a short report that DirectInput understands. Steam ("PlayStation
  Controller Support"), DS4Windows and many games switch the pad to its full
  report, and the pad keeps sending that until it is turned off. DirectInput (and
  every program that reads pads through it, also the game before 1.1.1) gets no
  input from the full report. The game now reads both. It never sends anything to
  the pad, so the pad stays as it is for your other programs. (With 1.1.0 or
  older: turn the pad off -- hold PS for 10 seconds -- and on again without Steam
  running, or use a USB cable.)
- **Started through Steam with Steam Input on.** Steam then gives the game a
  virtual Xbox pad for your controller. The game uses that one and leaves the
  real pad alone, so one pad is one player. The log says `[pad] started by Steam
  with Steam Input ...` and `Steam Input handles this pad`. The buttons are then
  Steam's (Steam's controller settings for the game), not `controls.ini`'s
  `[dinput]` ones. To have the game read the pad itself, turn Steam Input off
  for the game in Steam (Properties > Controller), or put this in
  `native\controls.ini`:

  ```
  [general]
  steam_input = 0
  ```

  If the pad still acts as player 1 *and* player 2, see [Two
  pads](#two-pads-or-my-pad-acts-as-player-1-and-player-2-ds4windows-steam-input).
- **`cannot open it (error 5, another program holds it) -- read through
  DirectInput`.** Another program opened the pad for itself (DS4Windows with
  "Hide DS4 Controller", or its exclusive mode). The game then reads DS4Windows'
  virtual Xbox pad. Nothing to do.
- **No vibration and no light bar** for these pads (the game never sends anything
  to them; through DirectInput there was none either).
- **The launcher sees these pads too since 1.1.2** (the Online tab's A/B
  buttons and Settings -> Set up controllers...): it reads them the way the game
  does, in every mode, only while the launcher is in front, and never sends
  anything to them. In 1.1.1 the launcher read them through the Windows joystick
  API, which has DirectInput's blind spot: a Bluetooth pad that Steam or
  DS4Windows switched over did nothing in the launcher (it did in the game). With
  1.1.1, turn the pad off and on again (hold PS for 10 seconds, then press PS)
  while Steam is closed, or use the mouse.
- **Back to the old way:** `hid = 0` under `[general]` in `native\controls.ini`
  (or `PS3_PAD_HID=0` under "extra settings") reads these pads through DirectInput
  again, as up to 1.1.0.
- Tested without a real pad: reports of every kind (USB, Bluetooth short and full
  report) were built from the published formats and fed into the game, which
  turned every button, direction, stick and trigger and every short tap into the
  right input. If yours does something odd, send the log (Report a problem) and
  say which pad and how it is connected. A different PlayStation-compatible pad
  (other vendor, or the DualShock 4 USB wireless adaptor) is read through
  DirectInput as before.

### My pad works offline but not online

Offline the game reads every player port, so a pad that got port 2 still plays
(as player 2, or in the menus). Online there is one player on your PC, and up to
1.1.1 the game took it from **port 1 only**. A pad lands on port 2 when another
controller was found first: a virtual Xbox pad (DS4Windows, DSX, other ViGEm
tools), the built-in pad of a handheld (ROG Ally, Legion Go, ...), a second pad
or a wheel that is plugged in. Xbox-type pads are given their ports first. The
game log says which pad got which port:

```
[pad] port 1 (player 1): XInput #0 (gamepad), layout standard
[pad] port 2 (player 2): HID 'DualSense Wireless Controller' 054C:0CE6 (DualSense, Bluetooth), layout ps
```

**Since 1.1.2** online play follows the controller you press: whatever port it
has, the first press on it makes it yours (the log says `[netplay] local player:
port 2 now`). A controller that is plugged in but not used never takes over.

**With 1.1.1**, either make the other controller go away (close DS4Windows / DSX,
unplug the other pad) or put your pad on port 1 in `native\controls.ini`:

```
[port1]
device = dinput:054C:0CE6
```

(`054C:0CE6` = DualSense, `054C:0DF2` = DualSense Edge, `054C:09CC` or
`054C:05C4` = DualShock 4; the `[pad] found HID` line shows yours.) If the other
controller is an Xbox-type one you never use, `xinput = 0` under `[general]`
does the same. A pinned port 1 stays the only online player in 1.1.2 too.

### The Controls screen (Settings -> Set up controllers...)

Not tried with a real arcade stick by a person yet: it was checked with simulated
controllers and against the game's own reading of `controls.ini`. If it does
something odd with yours, send the report (Report a problem) and say which
controller it is.

- **It shows no controller, or the row does not light up when I press a button.**
  The window reads controllers only while it is the window in front (nothing is
  read while the game or another program has the focus). Click into it and
  press again. Does Windows see the controller? Open `joy.cpl` and press a
  button. Xbox pads and XInput-mode sticks show as "Xbox pad (XInput)", everything
  else as "DirectInput controller". The screen reads DirectInput controllers
  through the Windows joystick API, which knows buttons B1 to B32 and one hat;
  a button above B32 has to be written by hand (`1 = B40`). A DualShock 4 or
  DualSense on Bluetooth that Steam or DS4Windows used since it was turned on
  is not seen here (the game reads it): turn the pad off and on with Steam
  closed (see [PlayStation controllers and
  Steam](#playstation-controllers-dualshock-4-dualsense-and-steam)).
- **"That was several buttons at once".** Two buttons (or a stick moved
  diagonally) went down together. Press one button, or move the stick in one
  direction only. Macros like 1+2 are set by pressing the one button that should
  do both.
- **Pressing buttons to test them starts a question or clears a button.** With
  "Move through this window with the controller" ticked, Cross sets the chosen
  row, Triangle clears it, Start saves and Circle closes the window. Untick it to
  only watch the lamps.
- **A game button shows "-".** It has no controller button. Pressing a button
  that another game button used takes it from that one ("B2 was 3 (Left Kick);
  that one has no button now"): a controller button can only be one game button.
  Set the other one again, or press Revert.
- **A trigger or stick direction (for example RX-) seems pressed all the time.**
  Some controllers rest their triggers at the end of the range. The screen
  ignores such an axis until it has moved once.
- **I saved, but the game plays as before.** The game reads the file when it
  starts: close it and start it again (a game that is already running says so
  in the status line). The line `[pad] controls: ...` in the game log shows which
  file the game loaded. If there is a `controls.ini` next to `t5dr.exe`
  (`native\build\cmake`), it wins over `native\controls.ini`, and `PS3_CONTROLS=`
  under "extra settings" wins over both; the screen writes to the one the game
  reads.
- **"controls.ini changed".** The file was edited by you or another program
  while the window was open. Say Yes to overwrite it with the screen's version;
  the file as it was is kept as `controls.ini.bak`. (The first save of each
  session keeps the old file there as well.)
- **Reset to defaults** removes the button lines, the layout and the player
  options of the chosen controller, and asks before it also removes the lines
  that are for all controllers of that kind. Comments, `[general]` and which
  controller is which player stay.
- **Two pads of the same model have to have different buttons.** The buttons
  are kept per model (one section `[dinput.VVVV:PPPP]` in the file), so two
  identical pads share them. Choose "Only the controller on player N's port"
  under "Your changes apply to" to set one of them on its own.
- **The game seems to ignore the layout of one controller.** The screen keeps
  buttons per model by the USB IDs it shows in brackets (for example 0F0D:00EE). The
  game names the same IDs in its log line `[pad] found DInput 'name' VVVV:PPPP`.
  If the two differ, choose "All DirectInput controllers" under "Your changes apply
  to" and set the buttons again (or put the IDs from the game log in the section
  name by hand).
- **Hitbox: both directions at once.** Pick what you want under "Opposite
  directions" (both cancel is the default). For a hitbox set to left-stick mode
  choose "8-way d-pad presses" under "Left stick".

### Two pads, or my pad acts as player 1 *and* player 2 (DS4Windows, Steam Input)

DS4Windows and Steam Input add a **virtual Xbox pad** for your real controller.
If the real controller is still visible to the game, it sees two pads. (When
Steam starts the game with Steam Input on, the game leaves a DualShock 4 or
DualSense that Steam names to Steam's virtual pad by itself -- see [PlayStation
controllers and Steam](#playstation-controllers-dualshock-4-dualsense-and-steam).)
Pick one of these:

1. Close DS4Windows and use the DualShock/DualSense directly (read directly,
   layout "ps", also over Bluetooth). Nothing has to be installed. Or in
   DS4Windows turn on "Hide DS4 Controller". **(untested with this game)**
2. Turn off Steam Input for the launcher if you started it from Steam: Steam is
   not needed for PlayStation pads since 1.1.1. **(untested)**
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
open behind the (minimized) game window or only flash on the taskbar. Windows
asks once per folder the program runs from, so a new release extracted to a new
folder asks again. It may ask about the launcher too (`python\pythonw.exe` or
`T5DR Online.exe`): allow it as well. The launcher does not need administrator
rights, and neither does the game. Windows itself asks for them only if you
change the firewall.

If you clicked Cancel (or never answered), the match still starts: Windows then
blocks only packets the game did not ask for, and lets in every reply to the
game's own packets -- both games send first, so they still meet. We tested it
(1.1.3, with the firewall's behaviour emulated in the game and the launcher,
never by changing this PC's firewall): one side blocked, both sides blocked,
blocked behind every kind of home router -- every match connected, directly or
through a relay. What you lose: a direct connection that needs the other side's
packet to arrive first. Then the match goes through a relay server, with more
lag. The Online tab tells you when the firewall blocks the game: see below.

### The firewall blocks the game

The Online tab shows a line marked **FIREWALL** with a **How to fix** link when

- Windows Firewall has a rule that blocks `t5dr.exe` (or the launcher) on the
  network you are on -- usually because Cancel was clicked when Windows asked;
  the line names the program. The launcher only *reads* the firewall's rules
  for the exact `t5dr.exe` it starts; it never changes them and never asks for
  administrator rights. Or
- a match showed it: this PC's UDP never reached the lobby server, or the game
  on a direct connection heard nothing at all from the other game (a firewall
  that blocks the game completely -- some antivirus firewalls do). The launcher
  then moves that match onto the relay by itself (both games start the match
  again; it takes about 20 seconds) instead of failing with "could not be
  reached".

Matches still connect either way, but some only through a relay (more lag). To
fix it:

1. Open **Windows Security** > **Firewall & network protection** > **Allow an
   app through firewall**, click **Change settings**, find `t5dr` (and
   `pythonw` / `T5DR Online`) and tick **Private** (and **Public** if you play on
   a network Windows calls public). Windows asks for administrator rights here:
   that is Windows, not the launcher.
2. Still blocked? A Cancel on Windows' question leaves **block rules**, which win
   over the tick above: open **Windows Defender Firewall with Advanced Security**
   (Start, type `wf.msc`), **Inbound Rules**, sort by **Name**, and delete (or
   set to **Allow**) every `t5dr` rule with a red block sign whose **Program** is
   your `t5dr.exe` (the folder of this release: `native\build\cmake\t5dr.exe`).
3. Another firewall (Norton, Kaspersky, ESET, Bitdefender, a company network):
   allow `t5dr.exe` and the launcher in its settings.
4. Back in the launcher, the line goes away the next time the Online tab is
   shown (or click **Dismiss**).

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
| "Your opponent's game could not be reached (firewall or router?)." | The game on the other side did not answer. They may have closed it, or their game crashed. A firewall alone no longer causes this between two 1.1.3 launchers: a game that hears nothing on a direct connection gets the relay ([The firewall blocks the game](#the-firewall-blocks-the-game)). |
| "Your opponent's game is a different build." | You do not run the same release. See below. |
| "Your opponent closed the game." / "The connection to your opponent's game was lost." | The match ended early. It is not counted as a win for the one who left. |

### I never get matched / the lobby shows "other build"

You are only matched with players who have the same build: the same release
**and** a build made from it. After you update to a new release, click BUILD
GAME again (the Play offline tab tells you). Ask your opponent to do the same.

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

- **Fights at 40-50 fps** on an older or slower processor, or a laptop: the
  game needs one fast processor core for its own frame. Until 1.1.2 a frame
  that was a little too slow also waited for the next screen refresh, so a
  PC that could do 50-55 fps showed 30-45; since 1.1.3 such a frame is shown
  as soon as it is ready (`PS3_LATE_FLIP=0` in the extra settings brings back
  the old way). What to check, in a list you can follow step by step:
  [docs/WEAK_PC.md "Player checklist"](WEAK_PC.md#player-checklist). A
  Vulkan renderer would not help here: the graphics calls are about 5 % of a
  frame ([why](WEAK_PC.md#d3d12-or-vulkan)).
- **Weak graphics card** (laptop, integrated graphics): in the launcher,
  **Settings** -> **Internal resolution** -> **Lower**, or **Lowest** if that
  is not enough. The 3D scene gets softer, the HUD stays sharp; the game
  itself does not change, so you can play online against someone who uses
  another step. If you chose 1080p, 1440p or 4K, go back to **Native** first:
  those need a strong graphics card.
- **Few CPU cores**: the game sets its number of helper threads to the cores
  it may use; there is nothing to set. In our tests (fast desktop cores held to
  4-8 threads) fights ran at 60 fps from 4 threads up. Online against a far-away
  player (150 ms) rollback costs more: about 50 fps with 4-8 threads while
  other programs were running. Online, both games run at the speed of the
  slower PC, so close other programs on both.

What may help as well:

- Close other programs, especially browsers, game overlays and recorders.
- Do not build the game while playing. Do not run a second copy.
- Laptops and handhelds: see [Game speeds up or slows down on a laptop or
  handheld](#game-speeds-up-or-slows-down-on-a-laptop-or-handheld).
- Slow frame rates also make the movies slow and the sound drop out (see [No
  sound](#no-sound)).

### Game speeds up or slows down on a laptop or handheld

The game's speed is its frame rate, like on the PS3: one game frame per
picture, 60 a second. When the PC cannot make 60 pictures a second, the whole
game gets slower (fights, timers, music tempo stays). It never runs faster
than 60: a game that "speeds up again" was slow before and got its 60 back.

On a laptop or a Windows handheld (ROG Ally, Legion Go, MSI Claw and other
Steam Deck-style PCs) the usual cause is **power or heat**: the processor
runs fast at first, gets hot or reaches its power limit after a few minutes,
and lowers its clock until the game misses frames. On a handheld, a laptop
or a mini PC with an AMD/Intel APU (processor and graphics on one chip, e.g.
Radeon 780M) the processor and the graphics share one power budget (15-65
W), so everything the processor wastes is taken from both. On 8-core
processors with 16 threads the game used to busy-wait on several threads,
which slowed its own main thread on the same cores; since 1.1.2 it does
not (on every PC, power saving or not).

- **Power saving** (launcher **Settings -> Power saving**, default **Auto**):
  the game stops busy-waiting and uses fewer helper threads, so the processor
  stays cooler and keeps its clock. Auto turns it on by itself when the PC has
  a battery, battery saver or the "Power saver" plan is on, the processor is a
  mobile one, or the game runs on integrated graphics. The game log says
  `[sched] power saving on (...)` and the window title shows "power saving".
  The game itself does not change, so you can play online against a PC
  without it.
- **Plug in the charger** and pick the fastest power mode (Windows: Settings
  -> System -> Power -> Power mode "Best performance"; handhelds: the
  maker's Turbo/Performance mode, e.g. Armoury Crate on the ROG Ally, Legion
  Space on the Legion Go). On battery many handhelds and laptops limit the
  power a lot.
- **Internal resolution Lower or Lowest** on integrated graphics: less work
  for the graphics leaves more of the shared power budget to the processor.
  Above Native the graphics work grows with the pixels: on integrated graphics
  1080p takes about 2.6 times Native's GPU time per frame, 1440p 4 times, 4K
  8-9 times (docs/RENDER_PERF.md "GPU time on integrated graphics"); Native or
  1080p is the sensible choice there. With power saving on (on by itself with
  integrated graphics), the shadow map and the sun's glow stay at their PS3
  size above Native -- shadow edges then look as they do at Native.
- **4K (or 1440p) on integrated graphics** with a 1080p screen: this game's
  3D scene at 4K is 6144 x 4320 pixels, and on an APU the graphics share the
  processor's memory and power -- so the busy graphics also slow the game's
  own work (a long "game" time in `[slow-frames]`, not the graphics' own
  time). Choose **1080p**, or **Auto (matches the screen)**, which picks
  1080p there (since 1.1.3; since 1.1.4 the default on integrated graphics,
  and above Auto's step Settings and, after every game, the Play offline tab
  say "4K (3x) on integrated graphics: a busy built-in GPU slows the
  processor too ..."). On a 1080p screen 1080p still looks sharp.
  docs/RENDER_PERF.md "4K on integrated graphics".
- **"Your processor ran at 2.26 GHz (81 % of its normal speed): set Windows
  power mode to Best performance."** (the Play offline tab, once, since
  1.1.4): fights had late frames while the processor, on AC power, averaged
  well under its normal clock (the `processors at ... GHz` part of
  `[slow-frames]`). Windows Settings -> System -> Power (& battery) -> Power
  mode -> **Best performance**; the launcher changes no Windows setting
  itself. On integrated graphics a lower Internal resolution also leaves the
  processor more of the shared power.
- **The log says `power saving off (PS3_LAPTOP=0 ...)` although Settings
  shows Auto**: a `PS3_LAPTOP=0` line in Settings -> "Advanced: extra
  settings" (it wins over the choice; since 1.1.3 Settings says so), or a
  `PS3_LAPTOP` variable in Windows' environment (since 1.1.3 Auto overrules
  that one).
- **Two graphics chips** (NVIDIA Optimus, AMD switchable graphics): the game
  picks the fast chip. The screen is still driven by the integrated chip and
  every picture is copied across; the log says `[gpu] display: ... hybrid
  present`. If Windows' Settings -> System -> Display -> Graphics has a
  choice for `t5dr.exe`, it wins over the game's own choice: set it to "High
  performance".
- Keep the air vents free; a laptop stand helps. Some laptops have a "fan
  boost" or performance key in their own control app.
- **Intel processors with performance and efficiency cores** (12th gen and
  newer, Core Ultra) and **Ryzen processors with two core groups** (7900X,
  7950X, ...): since 1.1.3 the game keeps its main threads on the
  performance cores, or in one core group, by itself. The game log's
  `[sched] processors:` and `[sched] placement:` lines say what it found and
  where the threads run. Do not limit the game to some cores in Task Manager
  or tools like Process Lasso: it then gets only those (`[sched] processors:
  4 logical ... (of 16)`).

**What the log says.** Every 30 seconds with slow frames the game log has a
line like

    [slow-frames] last 30 s: 1702 frames, 214 slow (over 20.9 ms): CPU 201 (game 187, render translation 9,
    vblank thread late 5), GPU 9, present 4; 380 late for their vblank, shown when translated; ...
    vblank clock 54.10 Hz; other programs 3.1 of 8 logical processors busy, the game 2.4 (of 8 it may
    use) | on battery (battery 61 %), power plan "Balanced", processor clock limit 2100 of 3800 MHz
    (held back: heat or the power plan)

- **CPU** slow frames: the processor was too slow for the frame -- power
  saving, the charger, the power mode, closing programs.
- **GPU** slow frames: the graphics were too slow -- a lower Internal
  resolution.
- **present** slow frames: showing the picture took long -- on a laptop with
  two GPUs the copy between them, or the compositor; try borderless
  fullscreen (Alt+Enter).
- "processor clock limit ... (held back ...)" means Windows says the
  processor may not run at its full speed right now: heat, the power plan, or
  the battery.
- "late for their vblank, shown when translated" (1.1.3): frames that took
  longer than one screen refresh and were shown as soon as they were ready;
  with many of them the `vblank clock` goes below 59.9 Hz -- the game ran a
  bit slower than 60 instead of dropping to 30-45.
- "other programs X of Y logical processors busy" (1.1.3): what the rest of
  the PC used at the same time. A large X: close programs.
- "game part ... main thread running A, waiting for the renderer C, for
  other game threads D" (1.1.3): what the game's own frame was made of. C large: the game waited for the graphics (counted as GPU).
  A large with C near 0: the processor's work itself was slow.
- "GPU busy X ms a frame (Y % of the time)" (1.1.3): the graphics' own time.
  Near 100 %: the line ends with "GPU-bound" -- a lower Internal resolution
  helps. On integrated graphics already 50 % and more slow the processor
  ("integrated graphics busy ..." at the end of the line).
- "processors at X GHz on average (Y % of their Z)" (1.1.3): the real clock
  while playing; well below 100 % on an APU while the graphics are busy, or
  on a laptop that is hot or on battery.

**Report a problem** (launcher) puts the power source, power plan, power
mode, processor clock limit and (where Windows has one) the temperature
sensor into `system.txt`, plus the last `[slow-frames]` lines of the game
log.

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
`NPUB30009-SYSNET` ("PLAY DATA") and `NPUB30009-CN<date>` ("CUSTOMIZE DATA").
The game keeps using the same folders; new ones do not pile up.

**Options > Delete Save Data** opens a list of the game's saves over the game
window, like the PS3's own list: the save's picture, name, date and size. Pick
one with up/down and CROSS (or Enter), confirm with "Yes", go back with CIRCLE
(or Esc). Nothing is lost for good: a deleted save is moved to
`savedata\.deleted\<folder>.<date-time>`. To get it back, close the game and
move the folder back into `savedata` (drop the `.<date-time>` part of its name).

Back up `native\gamedata` now and then. Copying `native` to a new release folder
keeps your saves.

## Other known problems

From our QA report of 2026-10-16. None of these is a problem with your PC.

- **Gallery** downloads its list of movies and pictures from Namco's update
  server, which is gone. The game says "Unable to update content list" and
  offers to go back to the title. On a PS3 today it is the same.
- **Options > Online Manual** opened the PS3's web browser on a page that no
  longer exists. The port has no PS3 browser: nothing happens when you choose it.
- **Online** (the game's own menu): after the terms screen the game says "A
  network error occurred. Returning to the title screen." and goes back to the
  title. It needs Sony's servers, which are gone. Use the launcher's Online tab
  instead (see "Online" in the README).

Not a problem: when the camera swings behind scaffolding, pillars or boards,
those objects turn see-through for a moment, so you can still see the
fighters. The game does this itself.

Also not a problem: after you beat the final boss in Arcade, the game shows
"GAME OVER" and goes back to the title. There is no ending movie in this
version of the game. The first time, the title then says that Jinpachi is now
a playable character.

Fixed since the QA report of 2026-10-16: dark faces, see-through rectangles on
floors, flat white background figures (spectators, wolves), the 1970 clock and
the failing first save.

## How to collect logs

**The easy way: Report a problem.** Click **Report a problem...** in the launcher:
the Play offline tab, the Build tab, or the Play online tab after a match. A window lists what
would go into the zip, with a box "What happened?". Click **Save report on the
Desktop**. The launcher makes ONE file, `T5DR-report-<date>-<time>.zip`, and opens
its folder with the file selected. Nothing is uploaded: you send it yourself, to
the person who gave you the game, or by attaching it to an issue at
https://github.com/TheWishin/T5DROnline/issues.

What is in the zip (each part only when it exists; you can untick a part):

| In the zip | What it is |
|---|---|
| `system.txt` | Windows version, processor (name, cores), graphics card (name, driver, video memory), RAM, every screen (size, refresh rate, scaling), the release version and build id, and the settings you use: window, internal resolution, online input delay (netcode), extra settings. |
| `report.txt` | What you wrote in "What happened?". |
| `logs\game-*.log` | The newest two game logs, and `rb_frames.log` / `df_frames.log`. |
| `build.log` | The last build. Ticked by itself when the last build failed or was cancelled. |
| `launcher.log` | The launcher's own log. |
| `online\` | The files of your last online match: result, status, the game's control files, and a short summary of the lobby and the match (server, ping, input delay). |
| `controls.ini` | Your button settings, if you made one. |
| `desync\*.bin` | Game state numbers of a desync (only if the game was started with `T5_NET_DESYNC_DUMP=1`). Binary. |
| `contents.txt` | The list of files and what was removed. |

Before a text file goes into the zip it is cleaned:

- Your Windows user name in a path (`C:\Users\Name\...` and `C:/Users/Name/...`)
  becomes `<user>`, and your user and PC name anywhere else too.
- Internet IP addresses (IPv4 and IPv6) become `<ip>`; a port after it stays.
  Addresses of your own network (`127.0.0.1`, `192.168.x.x`, `10.x.x.x`,
  `172.16-31.x.x`, link-local, `::1`) are kept.
- Passwords, tokens, match keys and cookies are left out (`<removed>`), also a long
  hex string. Your lobby login (`online.json`) and `launcher.json` are never put
  in the zip; their secret values are removed from every file.
- E-mail addresses become `<email>`, the file name of your `.pkg` becomes
  `<package>.pkg`, the company name in `OneDrive - Company` becomes `<org>`.

You can open the zip and read it before you send it. Your game data, keys, `.pkg`
and `.rap` are never in it. The desync dumps are the only binary files.

**Size limit: 20 MB** of content (the zip is much smaller). The newest files come
first. A log that does not fit keeps its start and its end; the middle is
replaced by one line saying how many bytes were removed.

**By hand** (when the launcher does not start):

1. Close the game. (The launcher keeps the log of each start.)
2. Build problem: open `native\build.log` (Build tab, **Open build.log**). It is
   overwritten by the next build: copy it first.
3. Game problem: open the newest `native\logs\game-<date>-<time>.log` (Play offline tab,
   **Open newest game log**).
4. In the game log, these lines matter:
   - `[CRASH]` — the game crashed. The lines after it say where.
   - `[fps]` — one line every 5 seconds with the frame rate.
   - `[hle] unresolved NID 0x...` — a system function that is not implemented yet.
   - `[pad]` — what the game sees as controllers.
   - `[cellAudio]` — sound device problems.
5. Write down: your Windows version, graphics card and driver version, what you
   were doing, and how long the game had been running.
6. Send the files as above (zip a large log first).

Files you send by hand are not cleaned. They contain folder paths, which can
include your Windows user name, and (online) the other player's IP address. Look
before you post them in public.

**Do not send** anything from `native\game\`, `native\build\` or `native\keys\`,
or your `.pkg` / `.rap`. Those are game data and keys.

For more detail in a log, the **extra settings** box in Settings accepts one
`NAME=VALUE` per line. `PS3_PAD_LOG=1` (or `2`) logs controller input.
`PS3_VERBOSE=1` logs a lot more but slows the game a lot (about 34 fps in an
earlier test), so use it only when asked.
