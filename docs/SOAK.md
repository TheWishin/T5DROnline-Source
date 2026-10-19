# Offline soak

`tools/soak/` drives the offline game for a long time and in every mode with
scripted pads, tracks the process (handles, threads, memory, CPU) and scans
the log for problems. Where `tools/smoke/` answers "did this build break
something" in minutes, the soak answers "does the offline game run like on a
PS3 for an hour, on 4 to 32 processors". It reuses the smoke suite's driver
(`tools/smoke/game.py`: scripted pads, log tail, the runtime's frame
read-back), so nothing on the desktop changes and the clipboard is never
touched.

    python tools/soak/soak.py modes   --exe EXE --out DIR          # every main-menu entry, then a second boot
    python tools/soak/soak.py arcade  --exe EXE --out DIR --chars 3  # ARCADE to the end, 3 characters
    python tools/soak/soak.py idle    --exe EXE --out DIR --minutes 30
    python tools/soak/soak.py mixed   --exe EXE --out DIR --minutes 60
    python tools/soak/soak.py ringcheck --exe EXE --out DIR --cpus 4 [--cpu-offset 8] [--online-repeats 4]
    python tools/soak/problems.py game.log          # the problem scan of any log, also a player's
    python tools/soak/threads.py PID [seconds]      # per-thread CPU of a running game, with thread names
    python tools/soak/explore.py --exe EXE --dir DIR  # closed-loop explorer (commands in DIR/cmd.txt)

Every game runs minimized without focus (`PS3_WINDOW_BACKGROUND=1`,
`PAD_NO_KEYBOARD=1`) at below-normal priority; `--mute` adds
`PS3_AUDIO_MUTE=1` (the mix is still measured, see below). `--cpus N` sets
the process's affinity to N logical processors (from `--cpu-offset`) and
`PS3_CPUS=N`, so the runtime sizes its pools as on an N-thread PC.

## What a run writes

Per run directory: `game.log`, `events.tsv` (phases, modes, fps, audio,
shots), `resources.tsv` (every 10 s: handle count, thread count, private
bytes, working set, GDI/USER objects, CPU seconds, the last fps, the
system's load and how many other `t5dr.exe` and compilers ran),
`frames/` (one small JPEG per read-back frame), named `*.png` shots,
`problems.json` and `summary.md` (resource trends with the slope over the
second half of the run, the log scan, the milestones, every mode change).
Frames and shots are game content: they stay under `build/`, never in git.

## Navigation

The scenarios do not wait for fixed times. They read the game's own mode
manager through the direct-fight probe (`T5_DF_PROBE=1`: one read-only note
per mode change, `[df] frame N: mode cur=C ... (tcb_*mode_t)`) and the game
type word (`T5_DF_WATCH=1008EBAC`), and they recognise the title's main menu
by frame (`soakgame.title_menu_check`: the four red menu rows below the logo
vs the single PRESS START line; lightning flashes wash single frames out).
The `idle` plan runs without the probe, exactly as a player's game.

Fights are steered through the runtime's debug console (`PS3_DEBUG=<file>`,
new verb `poke16`): while the fight HUD is up the driver writes a fighter's
health (P2 i16 at 0x10090FBC, P1 at 0x100906EC) every second -- P2 at 1 HP
wins every stage, P1 at 1 HP loses on purpose. That is how ARCADE reaches
the boss and the end, and how SURVIVAL and GHOST end on demand.

Modes and game types seen (`tcb_*mode_t`): 0 initialize, 1 title (intro and
title movies, PRESS START, the main menu), 4 game (every fight; game type 0
arcade, 1 ghost, 2 attract demo, 4 VS, 10 practice), 5 Namco logo, 6 select,
8 end, 10 rankings, 11 result, 13 online.

### Menu flows

- Main menu: ARCADE, GHOST, VS, ONLINE, SURVIVAL, PRACTICE, GALLERY, OPTIONS.
  The cursor stays where it was left and wraps; the menu ignores input for
  about a second while it slides in. START on the open menu picks the item,
  so the driver presses START only when no menu is on screen.
- After the intro movie the title runs the attract demo (a fight, game type
  2), then the rankings (mode 10), the Namco logo and the title again.
- ARCADE and GHOST have no pause menu. A lost match: continue countdown,
  rankings, Namco logo, title.
- PRACTICE: START opens the practice menu; RETURN TO TITLE SCREEN is its 10th
  item, then RIGHT ([No] -> [Yes]) and CROSS.
- ONLINE: four pages of terms, CIRCLE cancels; YES saves the profile and runs
  the game's online check (sceNp init, the "net ranking" thread, cellHttp),
  then "A network error occurred. Returning to the title screen."
- GALLERY: "Unable to update content list. Retry?" NO, then YES to return.
- OPTIONS is mode 3 (tcb_optionmode_t); EXIT leaves it. GALLERY is mode 12.
- After the fighter is picked (ARCADE, GHOST, SURVIVAL) a small menu offers
  ITEM SHOP & EQUIP / GAME START / NAME ENTRY: CROSS takes GAME START.
- At the select screen all four attack buttons confirm (with different
  costumes); CIRCLE does not cancel. VS loops between the select screen and
  the fight; the way out is the soft reset **START+SELECT**, which returns to
  the title from the select screens (the driver's general "back to the title").
- SURVIVAL: a lost fight ends at the result mode (11), then the title.
- Game types for the menu check: 0 arcade, 1 ghost, 4 VS, 9 survival, 10
  practice. A pick is verified against the mode / game type it leads to; a
  press lost on a slow PC (or the title running into its demo) re-syncs the
  tracked cursor and retries.

## Audio measurements

`[audio-rate]` (AUDIO_RATE=1) counted silent blocks after `PS3_AUDIO_MUTE`
had zeroed them, so every muted test game read 100 % silent. Patch 0041 takes
the share before the mute. The two numbers that mean audible holes are
"not written" (the game's sound engine had not written the block when its
time plus `PS3_AUDIO_WAIT_US` came) and "starved" (the device queue ran
empty). Since 0041 every player's log also gets a line when they add up to
5 or more in 5 s:

    [cellAudio] sound glitches: 41 audio block(s) not written by the game in time, 0 device underrun(s) in 1 window(s) of 5 s (937 blocks in the last one) [t=123.4s]

`[spu-tick]` (with AUDIO_RATE=1 or SPU_TICK_STATS=1) times the sound core's
answer to each audio tick -- the SPU thread's receive_event returning the PPU's
'STAT' to its next send_event -- every 5 s: wall time (what the audio sees)
and the thread's own CPU cycles per answer (QueryThreadCycleTime: the work,
which a busy PC's preemption does not inflate):

    [spu-tick] tid 0x2000: 937 answers, mean 3.10 ms, p95 3.75, p99 4.50, max 6.20, over 5.33 ms: 2; on the CPU 14.30 M cycles per answer

## Patch 0041 (ps3recomp) and repo changes

| change | why |
|---|---|
| sound core (bnuscore) built with `SPU_NEAR_FLOAT` (`spu_helpers.h`; CMake `T5DR_SPU_NEAR_SOUND`, `build_game_dll.py`; `CODE_VERSION` 3) | the exact float path costs 70-100 % of the 5.33 ms audio tick on a fast core; slower CPUs drop audio (below) |
| `[spu-tick]` per lv2 SPU thread: wall time and own CPU cycles per answered request (`SPU_TICK_STATS=1` or `AUDIO_RATE=1`) | measure the sound core against its tick |
| `[cellAudio] sound glitches` line in every log (5+ late/missing blocks in 5 s) | the friend's log had nothing to say about broken sound |
| `[audio-rate]` silent share taken before `PS3_AUDIO_MUTE` | every muted test game read 100 % silent |
| the 8 s / 15 s `[WATCHDOG]` thread dumps only when no frame was presented in the last 0.5 s (`WATCHDOG_ALWAYS=1` forces them) | ~1 300 lines in every player's log, every thread suspended in turn during the intro movie, module names resolved under the loader lock while a thread is suspended |
| debug console `poke16` | the soak holds a fighter's health (an i16) |
| a detached PPU thread's host handles, each thread's sleep timer: closed when the thread ends; threads created without JOINABLE are detached | ~70 handles an hour leaked, thread slots ran out after a few hours (below) |
| guest thread TLS blocks go back on a free list when the thread ends; when the 1 MB TLS window is full a block comes from the stack region; a thread left without one logs `[ppu] TLS: no free block ... (shared TLS fallback #n)` (`ppu_loader.cpp`, `sys_ppu_thread.c`); `problems.py` counts it (`tls`) | from the 10th thread on, every thread shared one TLS block (below) |
| `tests/run_ps3recomp_tests.py`: `spu_near_float`; `tests/test_soak.py` | |

## Results (2026-10-19, patch 0041 on the series to 0035; 0038/0040 since)

The PC (Ryzen 9 7950X, 32 logical processors) was shared with other agents'
games and builds the whole time: 8-18 other `t5dr.exe`, the system 90-100 %
busy in every run. Frame rates and wall-clock audio numbers below are what a
game gets on a saturated PC, not what it gets alone; the resource counts, the
problem scan and the per-tick CPU cycles do not depend on that.

### The two players' 1.0.0 logs: FIFO ring

Both logs (6-core Intel desktop; 8-thread Lunar Lake laptop) show the same
signature: 8x `recycled the title's own ring` at the first fight-scene load
(the attract demo's 212-job skinning list), then `queued flip never reached
by the FIFO walker` and a frozen picture. That is the drain-thread recycle
patch 0035 removed. `soak.py ringcheck` takes the second player's path (boot,
intro, attract demo, rankings, title, ONLINE with the terms accepted -- the
game's online check -- then 2-4 min in the menus) with affinity + `PS3_CPUS`:

| build | CPUs | runs | recycles | flips never reached |
|---|---|---|---|---|
| 1.0.0 release (t5dr.exe + t5dr_game.dll) | 8, 4, 2 | 3 | 8 each, at the demo's fight load | 0 (the stall after it is racy) |
| series to 0035 (main) | 8, 6, 4, 2 | 6, online check 1-5 times each | 0 | 0 |

### Sound: the sound core misses its tick on slower CPUs

The friend's "audio problems": Tekken 5 DR mixes its sound on an SPU thread
("bnusCore") that must answer every 5.33 ms audio tick. `[spu-tick]` shows
what it costs: with the exact SPU float emulation **25.2 M cycles per tick**
on the thread's own clock (5.6 ms at this PC's 4.5 GHz TSC, with the SMT
sibling busy; on a quiet PC 0003 measured 4-4.7 ms, before 0027/0033 trimmed
it a little) -- 70-100 % of the tick on one of the fastest desktop cores
there is. A 6-core Intel desktop core of 2018-2019 (the friend's: 6 logical
processors, GTX 1660) does roughly 1.4-1.6x less per thread and clock: by
that estimate 5.5-7 ms per 5.33 ms tick, so the game's audio blocks come late
("not written") and the sound breaks up whatever the frame rate. The
FFT butterflies of fa/fs/fma ops dominate (profile: functions 0xB1E8 29 %,
0xA868 15 %, 0xAF58 12 % of the thread).

Fix (patch 0041, `SPU_NEAR_FLOAT` for the bnuscore image, CMake option
`T5DR_SPU_NEAR_SOUND`, also in `build_game_dll.py`; `CODE_VERSION` 3): IEEE
single precision with the SPU's rules (no denormals, +0, extended range and
overflow on the exact path), rounding to nearest instead of toward zero. Same
run, same PC, the two builds side by side on 6 processors each:

| sound core | M cycles per tick (median of 14 windows) | wall ms per tick | ticks over 5.33 ms |
|---|---|---|---|
| exact (0035) | 25.2 | 6.8-8.2 | 389-565 of ~900 per 5 s |
| near (0041) | 14.3 (-43 %) | 5.1-6.5 | 282-348 |

(wall time and misses are inflated by the saturated PC; the cycle count is
the work.) `test_spu_near_float`: 7.07 M lane checks, worst 1 ulp (fa/fs/fm)
and 2 ulp (multiply-adds) from the exact path, SPU zero/extended rules
bit-identical, a decaying IIR reaches +0, and the same checksum for the
SSE4.1 and the x86-64-v3 build (no FMA dependence: the multiply-add rounds
twice). Audio captures of both builds: no NaN/Inf, the same levels. The
sound core only makes audio samples, both PCs of a match run the same code
(the build id changes with `CODE_VERSION`), so netplay sees no difference.

### 30 minutes idle on the title (player-identical: no probe)

| | 0-5 min | 15-20 min | 25-30 min |
|---|---|---|---|
| handles | 782-812 | 792-804 | 794-810 |
| threads | 59-71 | 65-67 | 65-68 |
| private MB | 1056-1115 | 1184-1235 | 1191-1237 |
| GDI / USER objects | 7 / 7 | 7 / 7 | 7 / 7 |

Private bytes grow in the first 15-20 min (caches filling: textures, PSOs,
movie buffers) and then stay flat. No crash, NID, syscall, render drop,
decode failure or FIFO line; 12 texture-cache LRU evictions (normal).

Fights on 6 processors (`tools/fight_bench.py`, the two builds side by side
on their own 6-processor sets, swapped for a second round; the PC was also
running other games, 27-30 processors busy):

| round | sound core | sound core cycles per tick | ticks over 5.33 ms per 5 s | audio blocks not written (last 40 s) | fps |
|---|---|---|---|---|---|
| 1 | exact, CPUs 2-7 | 21.1-23.3 M | 432-569 | 1 332 | 41.5 |
| 1 | near, CPUs 8-13 | 12.2-12.6 M | 0-12 | 14 | 50.6 |
| 2 | exact, CPUs 8-13 | 20.0-20.4 M | 225-359 | 623 | 35.9 |
| 2 | near, CPUs 2-7 | 14.0-14.4 M | 5-15 | 597 | 29.8 |

Fight fps moved with the CPU set (others' load), not with the build. The
sound core misses its tick about 30x less often with the near path; in round
2 the near build's CPU set was so busy that the title's own audio thread came
late too.

### Every mode (scripted, `soak.py modes` / `arcade`)

| mode | what ran | result |
|---|---|---|
| boot | Namco logo, intro movie to its end (2 094 pictures), title movie, attract demo, rankings | ok |
| ARCADE | 3 characters (EASY, 1 round, CPU held at 1 HP) through every stage, the FINAL STAGE boss Jinpachi, GAME OVER; Jinpachi and the random cell unlocked on the next select screen. Also a lost run: continue countdown, rankings, title | ok |
| GHOST | 2 ghosts beaten, then lost: rankings, title | ok |
| VS | two pads, full matches (P2 at 1 HP), back to the select screen, START+SELECT to the title | ok |
| ONLINE | terms of use, CANCEL; and accepted: the online check, "A network error occurred", title | ok |
| SURVIVAL | 3-4 opponents beaten, then lost: result mode, title | ok |
| PRACTICE | 25-30 s of attacks, practice menu, RETURN TO TITLE SCREEN, YES | ok |
| GALLERY | offline: retry NO, return YES | ok |
| OPTIONS | game, sound (BGM changed), controller pages, EXIT: the profile is saved | ok |
| save / load | second boot on the same gamedata: the save loads (`LOAD ... new=0`) | ok |

No `[CRASH]`, unresolved NID, unimplemented syscall, render drop, texture
decode failure, white fallback bind, shader TODO, movie/ATRAC decode error,
FIFO recycle/stall/resync or watchdog sample in any of these runs.

### 4 and 6 processors (`soak.py mixed --cpus N`, 20 min each)

Everything in turn (arcade to the end, VS matches, survival, practice, ghost,
options, gallery/online, idle with the attract demo); the PC 92 % busy:

| | 4 (2 cores/4 threads) | 6 (3 cores/6 threads) |
|---|---|---|
| segments | 11, all ok | 10, all ok |
| fps (5-s windows) | median 51.2, min 28.5 | median 53.6, min 32.7 |
| sound core | 12.5 M cycles/tick, 651 of 242 948 ticks over 5.33 ms | 12.0 M, 1 353 of 280 462 |
| audio blocks not written | 436 of ~243 000 (0.18 %) | 257 of ~280 000 (0.09 %) |
| handles / threads | 727-750 / 44-50 | 739-760 / 46-53 |
| private MB | 1 266-1 329, flat after 10 min | 1 275-1 326, flat |
| problems | none | none |

Below 12 processors the pools are smaller (44-53 threads instead of 65-71).
fps below 59 here is the busy PC: the same runs' frame rates follow the
other games' load, not the processor count.

### 60 minutes of everything (`soak.py mixed --minutes 60`, all processors)

61 min, 29 segments: 4 each of arcade to the end (4 characters), VS (2
matches each), survival, practice, ghost; options, gallery/online, attract
idle; two menu presses lost and recovered. The PC 90 % busy (up to 10 other games).

| | 0-10 min | 20-30 min | 40-50 min | 60-70 min |
|---|---|---|---|---|
| handles | 793-816 | 816-839 | 834-860 | 867-879 |
| threads | 66-72 | 66-69 | 66-69 | 67-69 |
| private MB | 1 189-1 330 | 1 304-1 351 | 1 376-1 422 | 1 385-1 388 |
| fps (mean of 5-s windows) | 48.1 | 51.5 | 49.0 | 56.1 |

No crash, NID, syscall, guest fault, render drop, decode error, FIFO line;
the sound core 13.4 M cycles per tick, 2 300 of 690 371 ticks over 5.33 ms;
803 of ~690 000 audio blocks not written (0.12 %). Private memory steps up
when new characters and stages load (texture and pipeline caches) and is
flat over the last 30 minutes.

**Handle leak (fixed in 0041).** Handles crept by ~70 an hour at a steady
thread count. By type (`tools/soak/handles.py`, a 12-minute diff): IRTimer
+6, Event +5, Thread +4. The title starts ~300 threads an hour (sound
decoders, particles, demuxers, autosaves); two kinds of handle stayed behind:

- a **detached** guest thread frees its own slot when it ends, but on Windows
  its host thread handle and join event were never closed (the POSIX half
  detaches) -- `sys_ppu_thread.c` now closes them, and no longer signals an
  event of a slot that may already belong to a new thread;
- each thread's high-resolution sleep timer (`host_sched.c`) was kept for
  good -- now closed at thread exit (a fiber-local-storage destructor).
- **thread slots**: the runtime ignored `sys_ppu_thread_create`'s flags and
  made every thread joinable. The title creates its autosave and network-check
  threads without `SYS_PPU_THREAD_CREATE_JOINABLE` and never joins them, so
  each one kept its slot (`FINISHED`) for good: thread ids climbed to 40 of
  `PPU_THREAD_MAX` = 64 in the 60-minute soak (7 autosaves, 3 online checks,
  2 boot loads leaked; the reused slots are the joined particle, sound decoder
  and demuxer threads), so a few hours of play would have exhausted them and
  thread creation would have failed (`CELL_EAGAIN`) -- an autosave, a
  particle or a sound decoder thread that never starts. Such threads are now
  detached from the start, as on lv2 (`PS3_THREAD_ALL_JOINABLE=1` restores
  the old behaviour), and the create line says `detached`.
- **40 minutes with these fixes** (`mixed --minutes 40`, 19 segments, the
  PC 41 % busy): handles 793-805 from minute 5 to the end (+6 an hour over
  the second half, was +78), threads 68-74, the highest thread id 16 (was
  40), private 1 281 MB at 5 min, 1 306 MB at 35 min, 1 371 MB after the last
  arcade run loaded new stages. No problem lines; fps median 58.0.
- not fixed, for the record: guest thread stacks come from a bump allocator
  over the 256 MB stack region that never frees (`vm_stack_allocate`); the
  title's ~380 threads an hour take ~10 MB, so it lasts ~25 hours of play in
  one process.

### Thread TLS: from the 10th thread on, all threads shared one block (fixed in 0041)

Found by the rollback-crash work (454 threads in one long session), checked
here. A thread made by `sys_ppu_thread_create` gets its TLS block from
`ppu_tls_new_block` (`ppu_loader.cpp`): a bump allocator over the 1 MB window
at 0x10F00000 that never freed. Tekken 5 DR's TLS segment is 64 KB (memsz
0x101C0), 0x18000 per block, so the window holds the loader's first image
and **9 blocks**. The title starts 11-12 threads at boot (the sound core's
decoder server, the SPU printf server and update thread are the 10th-12th)
and then one per sound stream, movie, particle job, autosave and network
check: 157 in the 40-minute soak, 148 of them past the 9th. Every one of those
ran with r13 = 0x10F07000, the loader's first image -- not the main thread's
block (the CRT's `sys_initialize_tls` moved main to 0x0E000000), but one
block shared by all of them at once: errno, the allocator's per-thread
context and anything else the title keeps in `__thread` storage, between a
sound decoder, a demuxer and a particle thread running side by side. (The
runtime's own comment on the allocator: Guitar Hero III could not allocate
at all with one shared block.) Nothing logged it.

Now a block goes back on a free list when its thread ends (the thread
procedure, after the entry returned or unwound out of `sys_ppu_thread_exit`)
and is re-initialised from the template for the next thread; when the window
is full a block is taken from the guest stack region once and reused after
that. The shared fallback is left only for a full 128-entry table and logs
`[ppu] TLS: no free block -- thread N shares 0x10F07000 ... (shared TLS
fallback #n)`; `problems.py` counts those lines (`tls`) and the blocks made
(`[ppu] TLS: block N at ... (TLS window | stack region)`).

| run | threads created | blocks made (window / stack region) | shared fallbacks |
|---|---|---|---|
| before (om8, 40 min mixed) | 157 | 9 / 0 | 148 (by the allocator: every thread after the 9th) |
| every mode (om9: boot, intro, demo, VS, online, survival, practice, gallery, options; then the reload boot) | 59; 15 | 9 / 5; 9 / 3 | 0; 0 |
| 40 min mixed (om10) | see below | | |

The first nine blocks are carved in the same order as before, so the boot
threads (file, draw and geometry request managers, ASync, keyread, ZsAread,
decoder) keep their addresses. For the rollback (`src/rollback/rb_state.cpp`
saves 0x10F00000+0xF0000 as "TLS blocks of created threads"): the later
threads' blocks now live in the stack region, outside that range, where
before they all shared the image at 0x10F00000 inside it -- side threads
(sound, decoders, demuxer, autosave), whose memory the rollback leaves out
anyway.

Not changed, for the netplay owners: callbacks the runtime runs into guest
code (`ppu_guest_call`: sysutil, GCM handlers) still get r13 = 0x10F07000,
the loader's image, also when they run on a guest thread -- on hardware they
would see that thread's TLS. Giving them the caller's TLS would move any
draws such a callback makes from the title's TLS random generator (0x3AFC3C)
onto the main thread's generator, which 0040's desync work reseeds; so that
is a netplay decision, not a soak fix.

### Open: NULL resource lookups in the draw thread (seen once)

One 4-processor run (2 cores / 4 threads, the PC 100 % busy, the
near-float build) logged 100 `[ppu] bctr to NULL` and NULL reads in the
title's draw request thread (guest tid 4, `func_00392670`) during the stage
4 load of an arcade run: a draw entry's resource id was not found
(`func_00351F9C` -> map lookup `0x3845C8` returned 0) and the title
called a method through the NULL object; the runtime skips such calls. The
game went on (frames around it show the stage and both fighters normally) and
it did not come back in the later 4- and 6-processor runs or any other run.
Likely a race between the draw thread and the stage load's resource
(un)registration that a starved 4-processor PC exposes; not root-caused.
