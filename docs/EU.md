# The European PSN release (NPEA00019)

Since 1.1.9 the build accepts the European PSN release of the game next to the US one:

| | US (what the port is made for) | Europe |
|---|---|---|
| Title in PARAM.SFO | TEKKEN 5 DARK RESURRECTION ONLINE | TEKKEN 5 DARK RESURRECTION |
| Title ID, version | NPUB30009, 01.00 | NPEA00019, 01.00 |
| Package content ID | UP0700-NPUB30009_00-UPDATE0000010000 (or ...-0000000000010000) | EP9000-NPEA00019_00-0000000000000000 |
| Package size | 619,430,240 bytes | 599,050,576 bytes |
| License (.rap) | UP0700-NPUB30009_00-UPDATE0000010000.rap | EP9000-NPEA00019_00-0000000000000000.rap |
| Decrypted EBOOT.elf | 5,294,536 bytes, SHA-1 be80165b84e30b6334baa6d6331b9db4ffd5a6a4 | 4,168,760 bytes, SHA-1 586baa2074e3d259b303879fc7cbea1000041b60 |
| What works | everything | offline only for now: its modes (below), sound, movies; online play comes in a later update |

**The European version plays offline only for now; online play for it comes in a later update.** Its title
menu has five modes: ARCADE BATTLE, GHOST BATTLE, VS BATTLE, GALLERY, OPTIONS (no PRACTICE and no SURVIVAL:
those came with the US "Online" edition). It does not have yet: online play, the training overlay (input display,
frame data), the launcher's unlocks, "late input" (the pads read at the top of each frame, a few ms less input
lag) and the shader warm-up after BUILD GAME. All of these read or change the game at the US program's
addresses, and the European program is not the same program (below). The game says so in its log
(`[t5] ... off -- this game is NPEA00019 v01.00 (EU)`); the launcher says "offline only for now, online play
in a later update" on the Build tab (package line), on the Online tab (when you log in) and in "Check my
problem" (a hint for a European build).

### Checked on the real game (1.1.9)

From the release zip (`package_release.py --release`), unzipped, BUILD GAME run the way the launcher runs it
(its own Python, `launcher/core.BuildRun`, bare PATH) with the European package and license: 65 s (lift 26 s,
sound core and jobs 4 s, compile 25 s; the warm-up skipped). Then `tools/smoke/run.py` on that build:

* boot (intro skipped, title menu, cursor down/up), VS BATTLE with both pads (pick, stage, 15 s fight, 60 fps),
  GHOST BATTLE (15 s fight): PASS. The smoke suite's PRACTICE test lands in ARCADE BATTLE on this menu (fight
  PASS, stage 1) -- the European edition has no practice mode.
* Sound: the game's own sound core (`bnusCore`, lifted from the European program) and the ATRAC music streams
  from the European T55DATA1.BIN run; `[audio-rate]` shows 0 % silent mixed blocks in menus and fights (100 %
  only before the title). The mixed output (AUDIO_WAV) of a Ghost fight: about -20 dBFS RMS, peaks to 0.66.
* Closing the window (WM_CLOSE, as the X button or Alt+F4) at the title: exit code 0 within 0.1 s.
* Lobby build IDs of the two builds from the same zip: US cf34b0ae2f3e8942, European 355fe12608fc1c86 (the ID
  contains the program's SHA-1); the European build also has `"online": false`, so the launcher does not log
  it in at all.

Why the co-developer's European build most likely had no sound (his build was not run here): it was the US
build of t5dr.exe with addresses patched for the European program. The sound core is an SPU program inside the
game's EBOOT, and the runtime runs the lifted copy registered for that program's fingerprint: the US build carries
only the US core's (0xE4AE7D71..., 0x4FFF1F00...); the European cores are other builds (version 01.00:
0xD1D7EF86..., 0x78004A8D...; the 02.00 "Online" edition's SPU program differs from the US one as well), so
nothing ran them. BUILD GAME lifts the sound core from the player's own program, which is why this build has
sound. (Lifting the European core with the US core's extra function list instead of its own still gave sound:
the list is not what decides it.)

## It is another build of the game, not the same code at other addresses

Measured on the two decrypted programs (tools of the 1.1.9 work, numbers only):

* **Code.** The US program has 3.88 MB of code and 22,473 functions, the European one 3.08 MB and 15,525.
  11,576 functions (52 % of the US code) are the same instructions in both (compared with the immediates --
  addresses, offsets -- masked, then by their place in the call graph); the rest differs or is not there
  (the US program has the online mode: 84 more imports, 50 of them sceNp). The firmware import stubs end at
  0x30388C (US 0x3C7100), the TOC is 0x3760E0 (US 0x470540).
* **Data.** The .bss starts 0x10000 lower and moves by different amounts in each part (-0x11F00 at the battle
  config, -0x72930 at the pad ring, -0x9D300 at the graphics object), and some structures have another layout:
  the battle phase word is 0x4C4 after the battle config in the US program and 0x220 after it in the European.
* **Sound core and skinning jobs.** The SPU sound core is another build (its effect table moved by 0x60, the
  functions by 0x88: `PROGRAMS[...]["spu_extra"]` in tools/build_game.py); of the three SPURS jobs only the signal
  job is the same, both skinning jobs are other builds (tools/lift_spu_jobs.py `JOBS_EU`).
* **Game data.** The data table in the program (US 0x10053FB0, 2,345 entries; EU 0x10043940, 2,329) points into
  T55DATA1.BIN (US 609.5 MB, EU 591.3 MB). 2,176 European entries are byte-identical to a US one; the 111
  entries 38-148 -- three per fighter -- all differ, mostly by 4 bytes in size. They are the fighters' data.
* **Frame rate.** Both run their game at 60 frames per second (the European PARAM.SFO lists the 720p/1080i
  modes as the US one does; the port paces both from the same vblank).

So the European game is an older build of Tekken 5 DR, with other fighter data. **European and US players
cannot play each other**: the two games would not compute the same fights, and their memory is laid out
differently, so not even the desync check could compare them. The lobby already pairs only players whose
build ID is the same, and the build ID contains the SHA-1 of the decrypted program (lobby/t5lobby/buildid.py):
a European game is only ever matched with a European game -- nothing in the lobby or the server had to change.

## The European "Online" edition (not supported yet)

There is a second European package: TEKKEN 5 DARK RESURRECTION ONLINE, content ID
UP0700-NPEA00019_00-TEKKEN5DRO000000 (PARAM.SFO VERSION 02.00, APP_VER 01.00), decrypted EBOOT.elf 5,363,592
bytes, SHA-1 a26bc6e037e5a8faf40250849acfa8a40d027fff, a free-licence program (no .rap needed). It is much closer
to the US program: 88 % of the US code is the same, every one of the 111 fighter data entries is identical, its
other data entries are all identical bar 25 (menus, texts). It is the candidate for European players **with** US
players. The build names it ("version 02.00 (Online) of the game") and refuses it for now: it needs the free
licence in tools/unself.py, its own sound-core and job tables, and every US address ported (below).

## How the build handles it

* `tools/build_game.py`: `PROGRAMS` holds per program what differs (title ID, content IDs, package size, code
  end, sound core functions, PGO profile yes/no, online yes/no); the decrypt step accepts both title IDs and pins
  the result to one of the two SHA-1s; the later steps follow the decrypted program: the game data under
  `/dev_hdd0/game/NPEA00019/USRDIR/`, the lift with its code end, the sound core with its functions, no PGO
  profile (the shipped one names the US program's functions), and the build stamp says `"title": "NPEA00019"`,
  `"online": false`. An output folder that held the other version starts again from the package chosen.
* `src/platform/t5_game.h`: the runtime tells the programs apart by the ELF header of the file it boots; the
  netplay hooks (with late input, the training overlay and the practice tools), the direct fight, rollback and
  the frame-timing log install nothing for any program but the US one. The game then runs on its own.
* The launcher: the Build tab names the European package ("the European version: it builds and plays offline
  ..."), the Online tab says that online play needs the US version, the rank plates and fighter pictures are not
  read from the European data (other entries), the shader warm-up is skipped.

## Porting the rest (plan)

Every US address in src/ needs its European counterpart, found -- not guessed -- from the two programs:

1. **Functions**: the function matcher (normalised instruction streams + call graph) maps 200 of the 286 code
   addresses src/ uses to the European program (185 function entries, 15 inside a matched function). The other 86
   are functions that differ (the start-game routine, the sound bank's play/stop, the camera, some icall targets):
   each needs a look at the code (fuzzy match by callers, strings, constants).
2. **Data**: pairing the absolute addresses matched functions compute gives 7,246 US -> EU data pairs (exact for
   the keyread semaphore, the input ring, the frame semaphore and clock, the battle config, the phase word, the
   pick records, the C library's rand state). Struct fields have to be checked one by one where the layout changed
   (battle config, fighter blocks: size, round-win byte, health, position).
3. **Runtime table**: the addresses become a per-program table chosen at start (t5_game.h), US values as today --
   the US build must stay byte-for-byte as fast.
4. **In this order**, each tested on the European game: late input; the training overlay (reads only); the
   practice tools; the direct fight (start a fight from the lobby); lockstep netplay; rollback (its state regions,
   hash ranges, sound detours) with the net suite at 0 mismatches between two European games.
5. Then the "Online" edition: free licence, its tables, and the cross-play test with US players (same fighter
   data; the state hashes then need a layout-independent form or identical layouts).

Never commit or ship anything of a European program either: no package, licence, decrypted program, lifted code,
data. Only the numbers above go into the repository, as for the US program.
