# Netplay: delay-based lockstep, and rollback on top of it

Two copies of the game, one per PC, play local Versus. Each PC's pad is one
player; the other player's input comes over UDP. Both games run the same
frames with the same inputs, so they stay identical without ever sending game
state. The code is ours (`src/netplay/`); no ps3recomp changes beyond the
patch series in `patches/ps3recomp/`.

**Rollback is the online default** (since branch `rollback10`,
docs/ROLLBACK.md sections 20-25). When both games offer it in the HELLO --
every build from rollback10 on does, for a match started through direct
fight (`T5_NET_START=external`, the lobby's way) -- the rollback loop
(`src/rollback/rb_net.cpp`) runs on this transport: inputs are predicted,
a late input that differs rolls the game back and re-simulates, and the
input delay drops to `T5_RB_NET_DELAY` (default 2 frames, the host's value).
`T5_RB_MODE=off` (or `lockstep`) keeps the delay-based lockstep described
below; a peer that does not offer rollback (an older build, or one with
`T5_RB_MODE=off`) gets the lockstep on both sides. Menu-driven sessions from
boot (`T5_NET_START=boot`) stay lockstep unless `T5_RB_MODE=net`.

## Running it

Host (P1) and joiner (P2), same build on both PCs:

```
T5_NET_MODE=host T5_NET_PORT=7000                     python tools/run_game.py
T5_NET_MODE=join T5_NET_PEER=<host ip>:7000            python tools/run_game.py
```

Optional: `T5_NET_DELAY` (frames, default 3; the host's value is used),
`T5_NET_TIMEOUT` (seconds the peer may be silent or stall the match before it
counts as lost, default 30; the lobby passes 20), `T5_NET_START` (`boot`,
default: lockstep from the first frames after boot; `external`: from the frame
the game calls `t5_netplay_start()`, see below). What happens when the
connection fails is in [Connection problems](#connection-problems).
The host must accept UDP on its port (port forward, or the lobby's punch/relay:
the lobby sets `T5_NET_PORT`/`T5_NET_PEER` itself, see `docs/ONLINE.md`). The
local player is whatever the runtime's controls put on port 1 (pads, sticks,
keyboard, remapping). Without `T5_NET_MODE` nothing changes.

Lobby handover (`docs/ONLINE.md`) is supported: a host given `T5_NET_PEER`
calls it while waiting; `T5_NET_BUILD` goes into the HELLO and a different
build is refused; `T5_NET_SEED` (host's value) seeds the game's random
generators; `T5_NET_KEY` (the match secret) authenticates every packet;
`T5_NET_MATCH` goes into the result file; `T5_NET_PATH`/`RTT_MS` are logged;
`T5_NET_ROUNDS` sets the rounds to win of a menu-driven VS game (0x1008EBD4,
written at every sync point; direct fight takes the rounds from `T5_FIGHT`).
`T5_NET_RESULT_FILE` gets the match's result when it ends:

```json
{"match": "m752f00f03e2f", "winner": 1, "score": [0, 2], "desync": 0, "frames": 4589,
 "hash": "ceace43900b83115", "fps": 38.2}
```

`match` is the lobby's id (`T5_NET_MATCH`, or the `match=` of the direct-fight
line for later matches); `desync` counts mismatching frames from this match's
sync point (the file is written once the deciding frame's hash has been
compared with the peer's, a few frames after the end); `hash` is the state hash
of the deciding frame (equal on both PCs when they agree); `fps` is this PC's
own speed in the match (time waiting for the peer left out). A match that could
not be played to the end has `"winner": null` and a `reason` (next section).

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

**Many sessions in one game (persistent game, `T5_CTL_DIR`).** The game stays
open between opponents (docs/DIRECTFIGHT.md "Persistent game"): the hooks are
in from boot without a session, and the direct-fight control channel starts
one per opponent. `t5_netplay_session_begin()` reads the session's variables
from the **session environment overlay** (`t5_env_overlay_begin/set`,
`t5_env`: the runtime caches every `getenv()` value for good, so a running game
cannot take new `T5_NET_*` from the process environment), ends any running
session and sets netplay up exactly as at boot: a socket on the new
`T5_NET_PORT`, a new session id and nonce (to the peer it is a new process),
the handshake from then on. In the core all per-session state lives in one
struct (`Session`) that `np::session_end()` puts back to "netplay off" after a
BYE and closing the socket; the receive and keepalive threads stay and follow
the socket. After the first session the keyread thread stays parked: between
sessions the main thread runs its tick with neutral pads ("idle"), and the
next `t5_netplay_start()` begins the new session's lockstep at frame 0 like a
fresh external start. A session that fails or loses its peer writes its result
file with the reason as usual, then ends without closing the game
(`t5_netplay_take_session_lost()` tells the direct-fight driver);
`T5_NET_ON_LOST` and the exit codes are process mode only. A new session also
waits for the last match's "decided" flag to clear before it watches for a
result. The result file is replaced with retries (the launcher may have the
old one open at that moment; a single failed replace used to lose it).

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

`tools/fight_flow_test.py` plays many direct-fight matches in a row the way the
launcher drives them: `--flow rematch` (process mode, rematches through
`T5_FIGHT_FILE`) or `--flow persistent` (control commands, a new session per
match, `--fresh-at N` restarts one game), `--mash` (both sides press buttons
the whole time), `--rematch-wait S`; it checks every match's result on both
sides (same winner and hash, 0 mismatches) and prints command-to-FIGHT times.

Match series under rollback or lockstep, with a latency/loss proxy:
`tools/rollback_net_test.py --fight A --next B --next B --matches 3 --rtt 150
--loss 3 --mode1 default --mode2 default` (match 1, match 2 and a rematch in
one process, `summary.txt` per run; `--mode2 off` is the lockstep fallback).
`T5_NET_SCRIPT_FIGHT=1` (set by that tool) applies the scripted presses only
while direct fight is in a fight, so they never touch the menus it drives.

## Design

**Lockstep core** (`netplay_core.cpp`, game-independent). Frame f uses the
local input sampled at frame f - delay and the peer's input for f; the main
thread blocks until that has arrived. Every packet carries all inputs the peer
has not acknowledged (and at least the last 8), the last 8 state hashes and the
last scene changes, and is resent every 15 ms while a frame is stalled, so
lost packets only cost latency (tested with 10 % loss, `T5_NET_DROP`). The
handshake (HELLO with session id, delay, build id, seed) runs on a network
thread from boot on and completes from either side; keepalives (PING, every
200 ms when nothing else is sent) carry whether the sender's lockstep has
begun. Protocol v2 (2026-10-17): every packet header carries the sender's
per-process nonce, and with a key a SipHash-2-4 tag (below).

**Short taps** (ps3recomp patch 0025, `PAD_TAP_LATCH`): the local sample
(`cellPad_sample_local`, once per live frame, never in a rollback re-sim) also
carries every press the pad layer's 1 ms sampler saw since the previous
sample, so a tap between two frames is that frame's input and released in the
next. A frame whose local input a scene barrier already filled with neutral
input is not sampled at all, so such a press goes out with the next open
frame instead of being thrown away. Test: `tools/tap_latch_test.py --pair`
(also `--rollback`): 2-5 ms taps, each one press of exactly one frame, in sync.

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
3. **The take-over is at a fixed frame on both PCs**: the frame the start is
   due (boot: the main loop's first frame with a keyread thread; external: the
   frame `t5_netplay_start()` was called) stops the keyread wakes, the next
   frame takes over. Before 2026-10-17 it took over as soon as keyread "was in
   its wait" -- but a vblank post just before the stop had often already
   released the thread while the flag still said "waiting": ~9 % of boots took
   over at frame 1 instead of 2, mostly followed by a deadlock (the thread's
   own tick beside ours: it held lwmutex 0x10752088 and waited for 0x106D4D00,
   the main thread the other way round). Now "parked" means: wakes stopped, no
   post half-way through the wrapper (a counter brackets check and post), the
   thread in its wait, and the semaphore at 0 tokens with a waiter -- with posts
   stopped that state cannot change. Should the thread's last tick still be
   pending at the take-over frame (a loaded PC), the main thread hands the
   frame lwmutex over through the game's own `sys_lwmutex_unlock/lock` stubs
   (0x3C6F20/0x3C6F00) until the tick is done (`T5_NET_TAKEOVER_TEST=1` forces
   that path once). 100 boots: same take-over frame on both sides every time,
   no hang (see Tested).
4. Frame numbers are the main loop's own frames, starting at the take-over;
   both games count the same frames.

## Connection problems

How a session starts, survives trouble, and ends when it cannot go on
(2026-10-17, after the netplay QA run in build/nq):

| Situation | What happens |
|---|---|
| Handshake | From boot on (network thread): HELLO every 100 ms until the peer answers. No answer within `T5_NET_CONNECT_TIMEOUT` (default max(60, 2 x `T5_NET_TIMEOUT`) s; 0 = wait forever) -> `no_peer` |
| Other build | A peer with another `T5_NET_BUILD`, or another netplay protocol version (older builds), is refused at the first HELLO, and told so (REJECT) -> `build_mismatch` within a second or two of boot, on both sides |
| Packets | With `T5_NET_KEY` (the lobby's per-match secret, sent only over the lobby's TCP channel) every packet ends in a SipHash-2-4 tag; without it the key comes from `T5_NET_MATCH` + `T5_NET_SEED` when both are set, else packets are unauthenticated (direct-IP play). Packets with a wrong tag, an unknown session or another peer process's nonce are dropped |
| Who is the peer | The first authenticated HELLO (unauthenticated: only from the IP in `T5_NET_PEER` when it is given); after the handshake only that process (session id + nonce + tag) |
| NAT rebinding / new relay mapping | The peer's packets arrive from a new address: they still prove who sent them, so the game answers there from then on ("the peer's address changed ... following it") |
| Short outage / loss / jitter | Lockstep stalls and resumes; resends every 15 ms; nothing is lost while the outage is shorter than `T5_NET_TIMEOUT` |
| Peer silent for `T5_NET_TIMEOUT` | `peer_timeout` (keepalives every 200 ms; a frozen process is silent) |
| Peer alive but no input for `T5_NET_TIMEOUT` mid-match | `peer_stalled` |
| Match start, peer alive but still loading | Waits up to `T5_NET_START_TIMEOUT` (default 120 s), then `start_timeout` |
| Peer closed its game | BYE -> `peer_quit` at once |
| Peer's game restarted | A HELLO from a new process of the peer: before any lockstep input was exchanged it simply takes the old one's place; mid-match the session cannot be resumed (the new game knows nothing of it): the old side ends with `peer_restarted`, the new one is refused (REJECT -> `rejected`) instead of hanging in the handshake |

**When a session cannot go on** (`T5_NET_ON_LOST=exit`, the default) the match
ends there, nobody plays on against an idle opponent: the result file gets
`"winner": null` and the reason (unless this match's result was already
written -- an opponent leaving after the match does not undo it), the peer is
told (BYE), and the game closes with exit code **3** (peer lost: `peer_quit`,
`peer_timeout`, `peer_stalled`, `peer_restarted`), **4** (no session:
`no_peer`, `rejected`, `start_timeout`, `bind_failed`) or **5**
(`build_mismatch`). The log line the launcher looks for is `peer lost
(<reason>)` / `cannot connect (<reason>)`. If the main thread is blocked
somewhere else for 8 s, the network thread ends the session itself.
`T5_NET_ON_LOST=idle` keeps the old behaviour (result file written, then the
peer's player idles).

**Speed.** Every 600 lockstep frames the log has `speed: X fps, this PC Y fps
without the waits for the peer` -- Y is this PC's own speed (the launcher
reports it to the lobby, which warns before a match with a slow PC and keeps
PCs below `T5L_MIN_FPS` out of ranked; docs/RANKED.md).

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
render and decode buffers. The desync detector leaves them out. So it does
with what a side thread's pace decides: the C `rand()` word 0x1074F218 and
the stage id it re-rolls at a round intro (0x1008F088), and the addresses of
objects the animation update takes from a pool at a match intro -- +0x830 of
each of the four 0x8D0 blocks (0x10090030, 0x10090900, 0x100911D0,
0x10091AA0), twenty heap pointers at 0x10091AB8 and an effect record at
0x100A0A00 (plain lockstep without rollback showed 0x100911D0 differing from
the second match's intro, nothing else: docs/ROLLBACK.md section 21).

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

**Hardening (2026-10-17, branch netplay-hardening).** The netplay QA agent's
impairment proxy and runners (build/nq/tools: netem.py, nqrun.py, bootrace.py),
direct fight Lili vs Dragunov, two instances on this PC, before = the QA runs in
build/nq/runs, after = build/nh/runs:

| Scenario | Before | After |
|---|---|---|
| clean, 10 % loss, burst loss, 50+-30 ms reordered, 4 x 200 ms and 3 x 1 s outages | in sync | in sync, both result files identical (winner, score, frames, hash), desync 0 |
| rematch in the same games (5 % loss, 20+-10 ms) | 50 mismatching frames at the 2nd stage select | 0 mismatching frames over 25,799; match 2's result names match 2 |
| NAT rebinding mid-fight | both stall 30 s, play on alone, 2,060 mismatching frames | host follows the new address, no stall, finished in sync |
| 12 s outage, `T5_NET_TIMEOUT=10` | both play on alone, 4,816 mismatching frames | both end after 10 s: `peer_timeout`, exit 3 |
| 12 s outage, `T5_NET_TIMEOUT=20` | -- | 12 s pause, then finished in sync |
| other build | both frozen at boot | both refuse in < 1 s: `build_mismatch`, exit 5 |
| joiner restarted mid-fight | handshake, then deadlock | old side `peer_restarted` (exit 3), new joiner `rejected` (exit 4) |
| joiner restarted while booting | -- | the new joiner takes over, match in sync |
| host killed | joiner plays on alone | joiner ends after 20 s: `peer_timeout`, exit 3 |
| `T5_FIGHT=...,random` | two different stages, every frame mismatching | stage from the seed on both, in sync |
| boot take-over (boot mode, no input, 3 pairs at a time) | ~9 % at frame 1, mostly deadlocked (QA); 1 of 50 boots at frame 3, desync from frame 0 (same harness, main build) | 200 boots: all at frame 2 on both sides, no hang, no mismatch |

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
- `T5_NET_ROUNDS` is written to the battle config's rounds-to-win byte
  (0x1008EBD4, found by the direct-fight work) at every sync point of a VS
  game, so two saves with different options play the same match length.
- The memory addresses are for NPUB30009 v01.00 only.
- The hash skip list was built from a handful of Lili-vs-Dragunov matches;
  other characters/stages may show more cosmetic noise (log with
  `T5_NET_DESYNC_DUMP=1`, diff, extend the list).
- A desync is detected and logged, not repaired.
- Both instances on one PC run ~35-40 fps (each at full speed alone);
  lockstep runs at the slower PC's speed.
- Rematch flows back to character select and stays in sync. From the deciding
  KO to the next select the direct-fight driver holds the pads and skips the
  win pose itself (docs/DIRECTFIGHT.md "After the match"); mashing there used
  to start the game's own next battle. Pausing (START) in an online fight is
  not blocked.
