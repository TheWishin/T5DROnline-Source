# Tekken 5: Dark Resurrection Online — native Windows port

Tekken 5: Dark Resurrection (PS3, PlayStation Network release) recompiled to
run natively on Windows — no emulator — with online play between friends.

The model is the same as
[Tekken 6 Native Online](https://github.com/Ekspym/Tekken6-native-online):
this repository and its releases contain **no part of the game**. Each player
builds the game on their own PC from **their own copy** — the PSN package and
the license (`.rap`) from their own account.

## Status

**Not playable. Nothing runs yet.** The repository holds the plan and the
ground rules; the recompilation has not started.

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

## Legal

No Sony or Namco code, keys or assets are in this repository. You must own
the game.
