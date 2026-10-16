# Netplay (prototype): delay-based lockstep

Two copies of the game, one per PC, play local Versus. Each PC's pad is one
player; the other player's input comes over UDP. Both games run the same
frames with the same inputs, so they stay identical without ever sending game
state. The code is ours (`src/netplay/`); no ps3recomp changes beyond the
patch series in `patches/ps3recomp/`.

## Running it

Host (P1) and joiner (P2), same build on both PCs:

```
T5_NET_MODE=host T5_NET_PORT=7000                     python tools/run_game.py
T5_NET_MODE=join T5_NET_PEER=<host ip>:7000            python tools/run_game.py
```

Optional: `T5_NET_DELAY` (frames, default 3; the host's value is used),
`T5_NET_TIMEOUT` (seconds without the peer before P2 goes idle, default 30),
`T5_NET_START` (`boot`, default: lockstep from the first frames after boot;
`external`: from the frame the game calls `t5_netplay_start()`, see below).
The host must accept UDP on its port (port forward, or the lobby's punch/relay:
the lobby sets `T5_NET_PORT`/`T5_NET_PEER` itself, see `docs/ONLINE.md`). The
local player is whatever the runtime's controls put on port 1 (pads, sticks,
keyboard, remapping). Without `T5_NET_MODE` nothing changes.

Lobby handover (`docs/ONLINE.md`) is supported: a host given `T5_NET_PEER`
calls it while waiting; `T5_NET_BUILD` goes into the HELLO and a different
build is refused; `T5_NET_SEED` (host's value) seeds the game's random
generators; `T5_NET_MATCH`/`PATH`/`RTT_MS` are logged; `T5_NET_RESULT_FILE`
gets `{"winner": 0|1|null, "score": [p1, p2]}` when a match ends.
`T5_NET_ROUNDS` is not applied yet (see limits).

**Starting at the fight (direct-fight mode).** Lockstep does not have to run
from boot. With `T5_NET_START=external` both games boot, load and do whatever
they do at their own pace with both pads neutral; when the game side calls
`t5_netplay_start()` (C linkage, `src/netplay/netplay.h`) on the main thread at
the frame its fight starts, the next frame becomes lockstep frame 0 on that PC:
the HELLO handshake is the ready barrier (each side waits there for the other),
the game's frame counters (0x106D4D88, 0x1008EB9C, 0x1008F07C, 0x1009442C) are
set to the same value on both, the input ring is cleared and the random
generators are seeded from the match seed. Calling it again while lockstep runs
(next match in the same process) is a sync point like a scene change. The
transport and lockstep core (`netplay_core.cpp`) do not care how the fight was
started. `T5_NET_START=frame:N` starts at the N-th main loop frame (tests).

Testing on one PC: `tools/netplay_test.py` starts a host and a joiner (or one
`local` instance) with minimized windows, host devices ignored, scripted input
(`T5_NET_SCRIPT`, `T5_NET_PADFILE`), per-frame logs and frame-exact
screenshots:

```
python tools/netplay_test.py --exe build/cmake/t5dr.exe --out build/nptest --pair --lobby \
    --seconds 330 --env T5_NET_DROP=10 --env T5_NET_SHOT=3500,6400 \
    --env1 T5_NET_SCRIPT=@1200:4:0x8,... --env2 T5_NET_SCRIPT=@1810:4:0x4000,...
```

`frames.log` in each instance directory has one line per frame (both inputs,
state hash); `game.log` has the `[netplay]` lines, including
`sync check through frame N: 0 mismatching frame(s) -- in sync` every 600 frames.

## Design

**Lockstep core** (`netplay_core.cpp`, game-independent). Frame f uses the
local input sampled at frame f - delay and the peer's input for f; the main
thread blocks until that has arrived. Every packet carries all inputs the peer
has not acknowledged (and at least the last 8), the last 8 state hashes and the
last scene changes, and is resent every 15 ms while a frame is stalled, so
lost packets only cost latency (tested with 10 % loss, `T5_NET_DROP`). The
handshake (HELLO with session id, delay, build id, seed) completes from either
side; a peer silent for `T5_NET_TIMEOUT` is dropped and its player idles.

**Game hooks** (`t5_hooks.cpp`). How the game reads pads, from its code: a
`keyread` thread, woken by the VBlank handler, polls `cellPadGetData` for both
ports and writes 16-bit masks into a ring; the main loop reads the newest ring
entry once per frame. Which sample a frame sees is a race between two threads
woken by the same (wall-clock) vblank. With netplay on:

1. `cellPadInit` / `cellPadGetInfo` / `cellPadGetData` are overridden
   (`ps3_hle_register_ctx`, dispatched before the NID table). The game always
   sees exactly two pads; GetData returns the lockstep inputs for the frame.
2. `sys_semaphore_wait` / `sys_semaphore_post` are wrapped in the lv2 syscall
   table. When the main thread returns from its per-frame wait (frame start),
   it runs one netplay frame, then **executes the keyread tick itself** (guest
   calls into the game's own functions). The real keyread thread is parked:
   its vblank wakes are dropped. (Waking keyread and waiting for it deadlocks:
   its pad update takes the lwmutex the main thread holds at that point.)
3. Frame numbers are the main loop's own frames, starting at its 2nd frame
   after boot; both games count the same frames.

## What had to be made deterministic

Found by running two instances with identical scripted input, comparing the
per-frame hashes, per-region hashes and memory dumps (`T5_NET_DUMP`,
`T5_NET_PAGEHASH`, `T5_NET_DESYNC_DUMP`, `tools/netplay_memdiff.py`):

| Source | Effect | Fix |
|---|---|---|
| Pad sampling on the vblank thread | input landed in different frames | keyread tick run by the main thread, once per frame |
| Mersenne Twister seeded from the clock at boot (0xAE6C8: `sys_time_get_current_time` -> init_by_array, state 0x10095168) | different random streams | reseeded with the shared seed at frame 0 and at every scene change |
| C library `rand()` (0x369228, state 0x1074F218; 91 callers) consumed at load-dependent times | **different random stage** on the two PCs, fights then diverged | reseeded with the MT at the same points; state hashed |
| Async loading (ZsAread thread, sem 8, feeding the file manager; "decoder", sem 10) | scene changes 1-20 frames apart (logo, char select, fight loading) | main thread waits at frame start until those loaders are parked with nothing queued (usually 0 ms; a few hundred ms on loading screens) |
| Anything left that moves a scene change | frame offset | scene change = sync point: both continue from the later frame, game frame clock (0x106D4D88) moved along on the other side, RNGs reseeded |
| Wall-clock vblank counters (0x106D4D90, the vblank list object +0xC0/+0xC8), key-repeat timestamps | none seen in game logic | not synced; frame clock 0x106D4D88 (used by key repeat) is per main-loop frame and is |

Things that still differ between the two PCs and do not matter: the penguin
crowd and similar stage props, two secondary-motion points (0x1008FF00 and
0x1008FFB0), five counters/handles in each fighter block, timestamps, sound,
render and decode buffers. The desync detector leaves them out.

**Match state** (what the detector hashes, `kDefaultHash`): the two pad state
blocks (0x10099F24), the input ring, the game frame clock, all random
generator states, and the fight block 0x1008E000-0x10091FFF: round state at
0x1008EBD0 (+0xA/+0xB rounds won by P1/P2, +0x5 non-zero once the match is
decided), round timer 0x1008F054 (frames left), the fighters at roughly
0x1008F800 and 0x100900D0 (0x8D0 apart), plus 0x10099600-0x10099BFF,
0x100A0900-0x100A0AFF and 0x100A3B00-0x100A3DFF. About 25 KB per frame.

## Tested

Two instances on one PC over 127.0.0.1, delay 3, 10 % packet loss
(`T5_NET_DROP`), scripted input on both sides: P1 picks Versus, both pick
fighters and stage, then both attack and move through a whole match (Lili vs
Dragunov, two rounds, P2 wins 2-0, back to character select). Evidence in
`build/np/` (`runs/*/run{1,2}/frames.log`, `game.log`, the
`netplay_*_host_vs_join.png` frame-exact screenshot pairs).

- Before the fixes above the same test diverged within the first loading
  screen; the two PCs even fought on different stages.
- With them, 3 of 6 full runs were in sync on every frame from boot through
  the menus, character select and the whole match (`0 mismatching frame(s)`
  through 7 200 / 8 400 / 7 200 frames). Screenshots of the same frame on both
  PCs are identical except the penguin crowd.
- In the other 3 runs (heavier CPU load: two pairs at once, or an intro movie
  skip landing a frame apart) the menu flow diverged right after "VS BATTLE"
  was picked (frame 1589, or at stage select): the Versus setup block
  (0x1008EBAC-0x1008EC08, 0x1008F060-0x1008F0B0, 0x100996B4-0x100996D4) was
  initialised one frame apart, and the random stage pick then differed. The
  fights themselves still ran in lockstep -- fighters, health, timer and
  outcome identical frame for frame on two different stages -- and both games
  wrote the same result file. The detector flags all of it.
- Lobby-style handover (fixed ports both sides, host calling the joiner,
  build id, seed, result file) connected through 10 % loss; a peer killed
  mid-match is detected after `T5_NET_TIMEOUT` and the survivor continues.
- Starting lockstep mid-game (`T5_NET_START=frame:300`, instances started 8 s
  apart) meets at the barrier and runs; it only stays in sync if the two games
  are in the same state at that frame, which is the direct-fight mode's job.

## Limits and next steps

- **Menu transitions are not fully deterministic.** Picking a mode or skipping
  the intro movie sometimes takes effect a frame apart on the two PCs (the
  culprit is still open: sound/movie completion or a loader not drained yet,
  e.g. `TNUD::ASync`), and Versus setup then differs. Scene changes are
  re-aligned, setup blocks are not. The direct-fight mode sidesteps this by
  starting lockstep at the fight; for menus in lockstep, the next step is to
  find what the transition waits for and make it a lockstep input (both PCs
  agree on the frame), or to copy the host's setup block to the joiner at the
  sync point.

- Delay-based: the input delay is felt (3 frames = 50 ms on LAN). Next step is
  **rollback**: keep the lockstep transport, predict the remote input, and
  re-simulate on misprediction. That needs a fast save/load of the match
  state; the regions above are where to start, but a full snapshot also needs
  the heap objects the fighters point to (animation state) and the sound/
  effect side effects of re-simulated frames must be suppressed.
- `T5_NET_ROUNDS` is not applied: 0x1008EBD0 holds 2 during a default match but
  writing it does not change when the game ends the match; the real setting is
  elsewhere (options block, to be found).
- The memory addresses are for NPUB30009 v01.00 only.
- The hash skip list was built from a handful of Lili-vs-Dragunov matches;
  other characters/stages may show more cosmetic noise (log with
  `T5_NET_DESYNC_DUMP=1`, diff, extend the list).
- A desync is detected and logged, not repaired.
- Both instances on one PC run ~35-40 fps (each at full speed alone);
  lockstep runs at the slower PC's speed.
- Rematch flows back to character select and stays in sync; menus after the
  match (continue, options) were not exercised.
