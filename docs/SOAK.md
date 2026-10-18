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

## Audio measurements

`[audio-rate]` (AUDIO_RATE=1) counted silent blocks after `PS3_AUDIO_MUTE`
had zeroed them, so every muted test game read 100 % silent. Patch 0041 takes
the share before the mute. The two numbers that mean audible holes are
"not written" (the game's sound engine had not written the block when its
time plus `PS3_AUDIO_WAIT_US` came) and "starved" (the device queue ran
empty). Since 0041 every player's log also gets a line when they add up to
5 or more in 5 s:

    [cellAudio] sound glitches: 41 audio block(s) not written by the game in time, 0 device underrun(s) in 1 window(s) of 5 s (937 blocks in the last one) [t=123.4s]

`[spu-raw-rtt]` (with AUDIO_RATE=1 or SPU_RAW_RTT=1) times the sound core's
answer to each audio tick: the PPU's 'STAT' mailbox write to its read of the
'END ' reply, against the 5.33 ms tick.

## Results

(filled in below by the soak runs)
