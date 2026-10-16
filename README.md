# Tekken 5: Dark Resurrection Online — native Windows port

Tekken 5: Dark Resurrection (PS3, PlayStation Network release) recompiled to
run natively on Windows — no emulator — with online play between friends.

The model is the same as
[Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online):
this repository and its releases contain **no part of the game**. Each player
builds the game on their own PC from **their own copy** — the PSN package and
the license (`.rap`) from their own account.

## Status

**Not playable yet.** The game is recompiled to a native Windows `.exe` and
boots: its threads start, the DirectX 12 window opens and it loads its data.
It then waits for its sound engine, which runs on the PS3's SPU and is not
translated yet. Next: the sound engine, then the SPU skinning jobs (needed to
see the fighters).

## How it will work

1. The player points the launcher at their own `.pkg` and `.rap`.
2. The launcher unpacks the package, decrypts the game program with the
   player's license, and checks it is the exact version the port supports.
3. [ps3recomp](https://github.com/NoahBPeterson/ps3recomp/tree/infamous/upstream-sync)
   translates the PS3 program to C++, which is compiled on the player's PC
   and linked against ps3recomp's runtime (D3D12 graphics, WASAPI audio,
   XInput pads).
4. Online play: the two players' controller inputs are exchanged directly —
   delay-based first, rollback later — with a lobby on top. The game's own
   online mode cannot be used as-is; Sony's servers for it are gone.

Everything game-derived stays in `game/` and `build/` on the player's PC and is
ignored by git.

## Requirements (planned)

- Windows 10 or 11, 64-bit, DirectX 12 graphics card
- Your own Tekken 5: Dark Resurrection for PS3 (PSN package + license)
- Visual Studio 2022 Build Tools, CMake, Ninja, Python 3.10+, Git

## For players: the release zip

<!-- players:start -->
**Test release. Expect bugs.** The zip contains **no part of the game**. You
build the game yourself from **your own copy**: Tekken 5: Dark Resurrection
Online for PS3, US PSN (`NPUB30009`, version 01.00) -- the package (`.pkg`,
619,430,240 bytes) and the license (`.rap`) from your own account. Other
versions are refused by the builder.

### Requirements

- Windows 10 or 11, 64-bit, a graphics card with DirectX 12
- About 1.5 GB free disk space (the package folder 250 MB, the unpacked game
  600 MB, the build 170 MB)
- An internet connection during the first build (public key data, a few KB,
  is fetched from github.com; nothing about you or your game is sent)

Nothing else: the zip brings its own Python and its own compiler (clang-cl and
lld-link from LLVM), and the game engine's runtime comes precompiled; your PC
only translates and compiles the code from your copy of the game. You do not
need Visual Studio, Git or an installed Python. (A developer build without the
precompiled runtime needs Visual Studio 2022 Build Tools; the launcher then
offers to install them. See docs/RELEASE.md.)

### First start

1. Extract the zip into its own folder (not into Program Files).
2. Start `T5DR Online.exe`.
3. **Build** tab: choose your `.pkg` and `.rap` (the launcher finds them in
   Downloads/Desktop/Documents if they are there).
4. Click **BUILD GAME**. The launcher checks your copy (a wrong version is
   refused within seconds), unpacks it to `native\game`, translates the game's
   code and compiles it on your PC: about 1.5 minutes on a fast 16-core PC,
   about 3-6 minutes on a typical one. Everything stays in the folder. Windows
   may ask once whether to allow `T5DR Online.exe` (unsigned).
5. **Play** tab: click **PLAY**.

### Playing

Keyboard: arrows move, A = left punch (1), S = right punch (2), Z = left
kick (3), X = right kick (4), Q/W = L1/R1, 1/2 = L2/R2, Enter = Start,
Tab = Select, Esc quits. An Xbox-style controller works too. Window size and
other options are in **Settings**. Online play is not in this version yet;
the **Online** tab will hold the lobby.

### Updating

Extract a new release into a new folder and copy your old `native` folder
into it (keeps the unpacked game and your saves). If the new version changes
the game code, the Play tab says so: press BUILD GAME again (only the code is
rebuilt).

### Problems

Send `native\build.log` (build problems) or the newest file in
`native\logs\` (game problems). Neither contains game data or keys.
<!-- players:end -->

## Legal

No Sony or Namco code, keys or assets are in this repository. You must own
the game.
