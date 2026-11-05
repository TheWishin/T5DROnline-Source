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

## The European "Online" edition (experimental, offline only)

There are two more European packages, both TEKKEN 5 DARK RESURRECTION ONLINE (NPEA00019):

| | v02.00 | v02.01 |
|---|---|---|
| Package content ID | UP0700-NPEA00019_00-TEKKEN5DRO000000 | EP9000-NPEA00019_00-TEKKENRETAIL0000 |
| Package size | 628,324,080 bytes (from the co-developer's build script, not measured here) | 631,901,088 bytes |
| License | free (NPD license type 3, no .rap) | .rap (license type 2), EP9000-NPEA00019_00-TEKKENRETAIL0000.rap |
| PARAM.SFO | VERSION 02.00, APP_VER 01.00 | VERSION 02.01, APP_VER 01.00 |
| Decrypted EBOOT.elf | 5,363,592 bytes, SHA-1 a26bc6e037e5a8faf40250849acfa8a40d027fff | 5,363,592 bytes, SHA-1 ff07efe07be23a30e37601049f4e849ddc2cff02 |

v02.01 is the v02.00 program with three bytes changed (an age-rating compare after
sceNpManagerGetContentRatingFlag, 11 -> 15, and two data words next to it) and the same T55DATA1.BIN entry for entry:
the same game. (The US "non-Online" package, UP0700-NPUB30009_00-0000000000000000, PARAM.SFO "TEKKEN 5 DARK
RESURRECTION" VERSION 01.01, ELF 4,206,424 bytes, SHA-1 aa047e02e79e96955835f6bcfd4e6c44d47cdd78, is the "v01.01"
some players have: the US counterpart of EU v01.00.)

**Build (1.2.1, offline):** both packages are accepted without an opt-in (v02.01 with its .rap; v02.00 without one,
using the free-license key from the local keys file). The old `--eu-online` / `T5DR_EU_ONLINE=1` options remain
accepted for scripts and change nothing. Its tables: code end 0x3D7884 (the last of its 256 import stubs + 0x20), the sound core's 13
effect functions from its own effect table (`EU_ONLINE_SPU_EXTRA`), the skinning jobs (the US images byte for byte,
0x600 further on) and its own signal job (`JOBS_EU_ONLINE` in tools/lift_spu_jobs.py), no PGO profile. It plays
**offline only**: both versions have `"online": false` in the build table and stamp, so the launcher cannot log
them into the lobby. Enable online only after EU-vs-EU rollback and lockstep pairs pass with zero mismatches.
The EU Online hooks now use the per-program table in `src/platform/t5_addr.h` / `t5_addr_eu_online.inc`;
EU v01.00 hooks remain disabled. 1.2.1: the two Online versions log in and share the lobby's declared crossplay
group with the US program (docs/COMPATIBILITY_GROUPS.md, "Declared crossplay group"); EU v01.00 never joins it.

**Late-input boot fix (1.2.1):** the keyread takeover called EU code with the wrong TOC base in r2. Its function
descriptor specifies `0x481000`; the address table had mapped the US TOC base to `0x481130`, a TOC slot rather
than the base. The wrong r2 made the takeover's calls read unrelated globals, stopping boot before sound setup
or at the BANDAI NAMCO logo depending on takeover timing. Use the EU descriptor's actual TOC base; US addresses
and paths remain unchanged. The EU keyread's once-a-second counter is 50 rather than 60, but only that function
uses it; it does not explain the boot hang. Offline boot and EU pair validation remain separate gates.

**Sound needs runtime patch 0108.** The EU Online program starts its sound core's SPU thread with
`sys_spu_thread_initialize(..., spu_num 0xFF, ...)` (the US program and EU v01.00 pass 1). The PS3 kernel numbers a
group's threads 0..255 (a 256-entry map) and gives the thread the next free place; our runtime refused every number
from 8 up, so the thread never existed, the PPU never got its mixed blocks and the game ran silent (`[audio-rate] ...
not written 937` every 5 s). `patches/ps3recomp/0108-spu-thread-num.patch`: numbers 0..255; 0..7 keep their place as
before (the US program's path is unchanged), a higher number takes the lowest free place, a repeated number is
EBUSY.

Checked on the owner's v02.01 package (2026-11-03, 1.2.0 preflight zip + this branch's tools, BUILD GAME the
launcher's way with `--eu-online`: 165 s; then `tools/smoke/run.py`): boot to the title menu, VS with both pads,
Arcade, Practice (the Online edition has it), title twice: PASS; Ghost: the fight runs (its end picture caught the
ghost's KO replay, a test-timing miss). Without 0108 every fight had 100 % unwritten audio blocks; with it 0 %
silent blocks, the sound core answering every 5.33 ms tick (mean 1.3 ms). The US build through the same tools:
lifted sources, all objects and the build stamp identical to integrated-120's tools, smoke quick PASS with and
without 0108.

### Which versions could play each other (measured 2026-11-03)

Five programs compared with the tools of this page (function matcher, whole-text alignment of the instruction
streams with branch targets and immediates masked, the data table's entries decoded and hashed, the PGO profile's
call counts of boot + menus + 7 fights as the "what runs" weight). Numbers only; the tables stay private.

| pair | fighter data (T55DATA1 entries 38-148) | code (masked) | verdict |
|---|---|---|---|
| US 01.00 vs EU Online 02.00 / 02.01 | 111 / 111 identical; 2,219 of 2,244 US entries identical at the same index | game code (below 0x330000) 98.4 % equal, 99.0 % of what runs; libraries 82 %; whole 95.7 % | **possible, with conditions** (below) |
| EU Online 02.00 vs 02.01 | identical (all entries) | 100 % (3 bytes) | **possible**: the same game; needs only the same address table and a compatibility group |
| US 01.00 vs EU 01.00 | 0 / 111 identical | 52 % | impossible |
| US 01.00 vs US 01.01 | 0 / 111 identical | 51 % | impossible |
| US 01.01 vs EU 01.00 | 1 / 111 identical | 81 % | impossible |
| EU 01.00 vs EU Online | 0 / 111 identical | 63 % | impossible |

Different fighter data means different fights by definition; those editions can only ever play their own kind (one
lobby, separate compatibility groups -- which the exact build ID already gives).

What differs between US 01.00 and EU Online, as far as read:

* **Libraries** (0x330000 up): the graphics command library, the sound library and the C runtime are other builds
  (other register allocation, other stack frames): render and sound work, not the fight.
* **Game code**: text and font rendering (more languages), the pad code (EU Online imports cellPadGetCapabilityInfo
  and cellPadSetActDirect: vibration), the online/NP code, some menu structures that grew, a resident-resource id
  space with 4 more entries (ids from ~0x8B on are +4, the table bound 198 -> 202), and the keyread thread's
  once-a-second counter (60 -> 50; nothing else reads it). No change was found in the fighter structures (no
  0x8D0 block size or field offset change in any matched function), and no 60 Hz <-> 50 Hz constant pattern in its
  data (60.0f / 50.0f / 1/60 / 1/50 occur as often in both). The fight's core is equal: the round state machine,
  the scene/fight update chain, the side-flag code (0x808D8), the camera move (0x878CC), the projection setters and
  the fight's generator 0xE859C; the title's TLS generator (0x3AFC3C) is the same algorithm in other compiler output.
* **But:** 46 of the 4,867 game functions that ran in the training differ beyond compiler noise, 19 of them every
  fight frame or more. One is identified and matters: the camera update (US 0x82598, the block at 0x825C8) got
  smoothing in EU Online -- the US code stores the new eye/target, the EU code interpolates when the jump is small.
  The camera decides which fighter stands on the left (the side flags, i.e. which way a sidestep goes), so a US and
  an EU game could turn the same input into different fights. Three are text rendering, one the pad code; the
  others (0x101080/0x1010A4, 0x1F0364, 0x28C17C, 0x32A268, 0x493B8, 0x68964, 0x8676C/0x86798 near the camera,
  0x95BCC, 0xA236C, 0xAA200, 0xC4C74, 0xC5BF8) are not identified yet.
* **Memory layout**: the data moved by a different small shift per link unit (the fight state +0x808 / +0x810 /
  +0x838 / +0x900 / +0x9E0, the input ring +0x980, the graphics object and the C rand state +0x8000), and a few
  menu structures have another size. The function matcher agrees with the co-developer's independently measured
  v02.00 addresses on all 29 of his direct entries (0 different; 16 more are fields of those).

Follow-up (2026-11-04): the EU camera smoothing is 50 Hz frame blending, gated by the mode manager's refresh-rate
phase. The runtime reports 59.94 Hz, which leaves the phase at 7 and the blend weight at 1.0. Under that setting
the camera uses the new position like US; confirm phase 7 in fight dumps when testing pairs.

The fighters' data and most of the fight are the same, but cross-play is not proven: (a) every differing per-frame
function must be identified and shown harmless or made to behave as the US one on the EU side,
(b) the random generators' consumption around a match (menus and loads differ in code), and (c) the state hash: the US hash covers whole address ranges whose inner layout differs by program and holds
pointers, so a US-vs-EU desync check needs a canonical, per-variable form. The conditions, in order:

1. a per-program address table for every address src/ uses (430 literals: 320 have direct evidence, 30 more are
   fields between evidenced neighbours, the rest are constants or need reading), reviewed, EU Online values only
   where the program's own code proves them;
2. the hooks, direct fight, lockstep and rollback for EU Online vs EU Online at 0 mismatching frames;
3. a canonical cross-program state hash (the same fields, pointers left out or translated);
4. a real US-vs-EU Online pair through picks, full matches, rematches, every stage and fighter, both netcodes, at 0
   mismatching frames; only then an approved compatibility group in `T5L_COMPAT_GROUPS`.

Step 1 now uses a public, explicit EU Online address table in `src/platform/t5_addr_eu_online.inc`, with separate
regions where lengths differ. A missing EU mapping aborts instead of falling back to a US address. The evidence
and generated study tables remain private. Steps 2 through 4 still require game runs; address coverage alone
does not enable the lobby.

## How the build handles it

* `tools/build_game.py`: `PROGRAMS` holds per program what differs (title ID, content IDs, package size, code
  end, sound core functions, PGO profile yes/no, online yes/no); the decrypt step accepts both title IDs and pins
  the result to a supported program's SHA-1; the later steps follow the decrypted program: the game data under
  `/dev_hdd0/game/NPEA00019/USRDIR/`, the lift with its code end, the sound core with its functions, no PGO
  profile (the shipped one names the US program's functions), and the build stamp says `"title": "NPEA00019"`,
  `"online": false`. An output folder that held the other version starts again from the package chosen.
* `src/platform/t5_game.h`: the runtime tells the programs apart by the ELF header of the file it boots. US and
  EU Online hooks use `src/platform/t5_addr.h`; US values are unchanged, EU Online values use its explicit
  table. EU v01.00 hooks remain disabled. The build stamp separately gates lobby access.
* The launcher: the Build tab names the European package ("the European version: it builds and plays offline
  ..."), the Online tab says that online play needs the US version, the rank plates and fighter pictures are not
  read from the European data (other entries), the shader warm-up is skipped.

## Porting the rest (historical EU v01.00 plan)

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
data. The existing numbers above describe earlier work; newly generated analysis and mapping tables stay private.

## EU Online v02.00: owner-local review handoff

**Historical review workflow; US cross-play remains unproven.** This section was written in 1.1.9 without a
European package. In 1.2.0 the comparison above was repeated on the owner's v02.01 package and the co-developer's
v02.00 program. The current branch builds EU Online without an opt-in and has its runtime address table;
the private evidence workflow below remains useful when reviewing new addresses.
The earlier measurements above are recorded evidence, not a substitute for repeating the comparison on the owner's
exact package.
EU v01.00 and EU Online v02.00 must remain separate targets; neither is a constant shift of the US program.

`tools/eu_review.py` gives the owner two local steps. All package, key, decrypted-program, prepared ps3recomp
and scratch paths must be **outside this working copy**. Its guards resolve paths first (including symlinks)
and refuse this repository. Use fresh scratch directories: the tool refuses to overwrite them. Commands below
are for a later run on the owner's PC; none were run here. There are no network, build, lifter or game steps.

```powershell
# Set these to the owner's PRIVATE paths, outside the public working copy.
# $Deps is an already prepared ps3recomp tree; nothing is downloaded by this tool.
python tools/eu_review.py extract --package $EuOnlinePackage --deps $Deps --keys $LocalKeys --scratch $ExtractScratch
```

The tool checks the package header's content ID against the v02.00 ID above, then runs the prepared
`pkg_extract.py PACKAGE SCRATCH/package --only PARAM.SFO` and the same command with `--only EBOOT.BIN`.
It does not unpack T55DATA or the rest of the package. The owner checks the extracted SFO's `TITLE_ID`
(`NPEA00019`), `VERSION` (`02.00`) and `APP_VER` (`01.00`), plus the title. A content ID alone does not prove
the version or authenticity of a package.

**Decrypting (1.2.0):** `tools/unself.py` now handles the free licence (NPD license type 3): the klicensee is
NP_KLIC_FREE from the local keys file (not shipped, not in this repository) and the .rap argument is not read;
tests/test_unself.py checks it on a synthetic SELF with fake keys. It was not run on a real v02.00 SELF here (none
was available, and this PC's keys file has no NP_KLIC_FREE); the owner's v02.01 package decrypts with its .rap to the
SHA-1 above. Do not pass a dummy RAP, invent key bytes, or bypass the refusal.

Keep the resulting ELF private; the later comparison
requires its SHA-1 to equal the existing v02.00 pin `a26bc6e037e5a8faf40250849acfa8a40d027fff`. The US ELF must
equal the US pin in the table above. Unknown programs stop before analysis.

Once the owner has both verified decrypted programs:

```powershell
python tools/eu_review.py compare --us $UsElf --eu $EuOnlineElf --deps $Deps --scratch $CompareScratch
```

For each program the script runs `ppu_loader.py ELF -o ANALYSIS`, then
`find_functions.py ELF --seed-json ANALYSIS/EBOOT.functions.json -o ANALYSIS/functions.json`, following the
existing build's analysis commands. It calls the matcher directly; it never runs `ppu_lifter.py`, compiles,
or launches anything. It verifies both ELF hashes before running those tools. The owner must record which
prepared ps3recomp revision/patch series supplied them when reviewing the result.

The private `review/` directory contains these reviewable tables:

| File | What the owner reviews |
|---|---|
| `functions.csv` | Every US function: candidate EU entry + instruction count, or an unresolved row. Normalised instruction equality masks immediates, so a match is a candidate, not a proof of identical semantics. |
| `data.csv` | Direct address-pair candidates and observation counts. Equal-count conflicts are omitted as unresolved. No nearest-address delta is applied. Struct sizes, fields and pointer meaning still need individual checks. |
| `source_literals.csv` | Source file, line and every 5–8 digit hex literal under `src/`, deliberately **unclassified**. The owner separates guest addresses from sizes, masks and constants, and adds calculated addresses, offsets and state ranges found by reading their uses. This is an inventory aid, not a complete address parser. |
| `required.csv` | Explicitly requested US addresses with candidate/evidence or an empty unresolved target; blank owner decision and notes columns. No address is approved automatically. |
| `summary.json`, `programs.json` | Program pins, TOCs, coverage and explicit `approved_for_runtime: false` / `crossplay_proven: false`. No opcodes, game bytes, licences or keys are emitted in the review tables. |

The initial `required.csv` has only its header. After classifying the literal inventory and reading the code,
the owner repeats `compare` into a **new** scratch directory with `--required US_HEX_ADDRESS ...` for the actual
addresses evidenced by source. Alternatively, with the already generated function lists:

```powershell
python tools/addr_map.py --us $UsElf --us-functions $UsFunctions --other $EuOnlineElf --other-functions $EuFunctions --review-dir $NewPrivateReview US_HEX_ADDRESS
```

`addr_map.py` also refuses game-derived input/output paths inside this repository. Its console lookups now
leave absent data addresses unresolved instead of suggesting a neighbour's delta. There is no runtime-table
generator: review evidence cannot accidentally become hooks. Keep **all** outputs, even CSV/JSON, on the owner's
private PC outside this repo; share the review decisions separately without attaching game-derived files here.

### Selecting addresses in the game

`src/platform/t5_game.h` identifies the ELF by recorded entry point and file size; the build separately pins the
decrypted SHA-1. In 1.2.1, `hooks_ok()` enables US and EU Online (plus the historical `Unread` test-harness fallback).
The explicit per-program table preserves US values and maps EU Online readers/writers, hook targets, icalls,
state/hash regions and sound detours; missing EU mappings fail closed. EU v01.00 remains disabled. Field layouts
and region lengths are separate where they differ. The address review accounts for individual locations,
rather than applying one overall delta.

Done in 1.2.0: free-licence support, the EU Online sound-core function table, its SPURS job tables and code end
(`EU_ONLINE_PROGRAMS` in tools/build_game.py, `JOBS_EU_ONLINE`). In 1.2.1 the opt-in is removed and the address
table enables offline hook testing. Test late input, training/practice, direct fight, lockstep and rollback in
stages before enabling lobby access. Any implementation must preserve the simulation on both PCs. Two EU Online PCs require
**0 mismatches**, followed by a real EU Online–US pair at **0 mismatches** through picks, complete fights, rematches
and rollback. Equal fighter data alone proves neither matching simulation nor compatible state hashing;
cross-version canonical hashes and the complete compatible-build contract need review before approving any
cross-build group. The integrated lobby defaults to exact build IDs; `T5L_COMPAT_GROUPS` permits only explicit
operator-approved groups when both clients support them (see [COMPATIBILITY_GROUPS.md](COMPATIBILITY_GROUPS.md)).
No EU/US group ships, EU v01.00 remains incompatible, and EU Online must not be grouped with US merely because
fighter data matches. Identifying the region does not grant compatibility.

## US-vs-EU crossplay proof (2026-11-05, branch eu-crossplay-2)

Host `t5dr.exe` e8aabbb6ec197cb7 (+ game DLLs: US 1baae969..., EU 443dceaa...), 1.2.1 sources of this branch.
Fight `jin,jin,20,2` then three more matches (king/nina stage 27, christie/feng stage 17 twice), RTT 150 ms,
jitter 5 ms, 3 % loss, muted, below-normal, one process pair per run:

| pair | netcode | frames compared | differing | match results |
|---|---|---|---|---|
| US host / EU joiner | rollback | 13,611 | 0 | 4 of 4 equal |
| EU host / US joiner | rollback | 13,648 | 0 | 4 of 4 equal |
| US host / EU joiner | lockstep | 13,579 | 0 | 4 of 4 equal |
| EU host / US joiner | lockstep | 13,579 | 0 | 4 of 4 equal |
| US / US control | rollback | 13,767 | 0 | 4 of 4 equal |
| US / US control | lockstep | 13,719 | 0 | 4 of 4 equal |
| EU / EU control | rollback | 13,748 | 0 | 4 of 4 equal |
| EU / EU control | lockstep | 13,700 | 0 | 4 of 4 equal |

Every mixed recording (16 files) plays back identical (0 hash mismatches, 225-228 hashes) on both editions.
A same-edition recording (format 8) is for its own edition only: played on the other edition it parts at its first
compared frame (by design: that edition hashes its own layout). Harness: `tools/rollback_net_test.py` with
`tools/cross_build_test.py check_run`, then `tools/replay_play.py` per recording and edition.
