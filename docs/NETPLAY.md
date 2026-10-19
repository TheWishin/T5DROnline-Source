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
input delay drops to the rollback input delay -- by default 1 frame up to
~60 ms round trip and 2 above, measured by the game itself (below,
"Input delay").
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
result. Rollback (the default) runs in every session: it is offered in a
persistent game too, and `rb::net::session_reset()` stops the loop and drops
its undo logs between sessions (`state_reset`).

**Direct fight: the fight's loading is not compared, and its end is a sync
point.** From FIGHT START until the fight phase word (0x1008F070) passes 12
(game mode start, loading, intros; also between rounds) the state hash is a
fixed value on both sides (`kIntroHash`; `rb_net.cpp` the same): nothing there
takes input, and the loading's progress depends on the game's caches -- a
persistent game that has played loads faster than one that has just started
(docs/DIRECTFIGHT.md). The end of the fight's loading -- the first frame the
phase word shows the intros (11, 12) or the fight (17) after a fight start --
is a scene barrier in both modes (`g_await_load`, `fight_loaded_now()`; before,
only the lockstep re-aligned a fight's loading, and then the first ring reset
after a fight start was used, which is "Fight!" itself: a played and a fresh
game ran their Fight! frame on different random states and Asuka vs Law
desynced; docs/DIRECTFIGHT.md "After a session ends"), and the first frame
after a scene barrier is not
compared under rollback (one side hashed it before the barrier's reseed, the
other after). The result file is replaced with retries (the launcher may have the
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
state hash; under rollback also `f F <hash>`, the frame's final hash once every
input before it is confirmed); `game.log` has the `[netplay]` lines, including
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

## Input delay

Like Tekken 6 Native Online, the rollback input delay follows the ping
(latency branch, 2026-10-17). Each player has a setting -- the launcher's
**Settings -> Online input delay** (`T5_RB_NET_DELAY` = `auto`, `0`, `1` or
`2`; default `auto`) -- and the match's value is picked by the host when the
match starts:

- both players set the same number: that number;
- otherwise (different numbers, or `auto` on either side): auto -- **1 frame up
  to 60 ms round trip, 2 above** (`T5_RB_NET_DELAY_AUTO=<ms>` moves the
  threshold);
- never above the session's lockstep delay (`T5_NET_DELAY`, the lobby's
  suggestion; tests that start with 0 stay at 0);
- **ranked matches** use a fixed value for everybody: the lobby server sends
  `T5L_RANKED_INPUT_DELAY` (default 2) in `match_start`, the launcher passes it
  as `T5_RB_NET_DELAY` on both PCs, and it wins over the player's setting.

The round trip is measured by the game, not taken from the lobby: from the
handshake to the match start both games send a PING every 200 ms when nothing
else goes out, each carrying the sender's clock (microseconds) and the echo of
the last PING it received with how long it held it; the receiver's round trip
is now - echo - hold (the median of the last 32; the lobby's `T5_NET_RTT_MS`
only if no sample came in). Both PCs must use the same delay from the same
frame, so the joiner does not decide: the host's pick travels in every PING
and INPUT packet after its match started, and the joiner's rollback loop
waits at its first frame until it has it (`rollback agreed: input delay 6 -> 2
(the host's pick)` in its log; the host logs `rollback input delay for this
match: 2 frame(s) (auto: round trip 152 ms (32 samples) -> 2 ...)`).

**Protocol v3** (latency branch): PING carries the time stamps, the echo and
the host's pick; INPUT carries the pick; HELLO's flags bits 8-15 carry the
sender's setting (0xFF = auto). A v2 peer is refused like any other build
(`build_mismatch`); the lobby's build id includes the version
(`lobby/t5lobby/buildid.py` NETPLAY_VERSION 3).

Tested (two games on this PC through `tools/rollback_net_test.py`'s proxy,
direct fight, 3 % loss, +-5 ms jitter; `build/lat/netruns/`), one match each (Asuka vs Lili,
stage 20, 2 rounds), 8 logical processors per game:

| run | settings (host / joiner) | round trip measured | input delay picked | sync check | result hash |
|---|---|---|---|---|---|
| S0 | auto / auto, RTT 0 | 4 ms | 1 | 0 mismatching frames through 4199 | same on both |
| S50 | auto / auto, RTT 50 | 51 ms | 1 | 0 | same |
| RA1, RA2 | auto / auto, RTT 150 | 151 ms | 2 | 0 | same |
| D11 | 1 / 1, RTT 150 | -- | 1 (both set 1) | 0 | same |
| D0a | 0 / auto, RTT 0 | 3 ms | 1 (auto: the settings differ) | 0 | same |
| K0, K50, K150 | lockstep (`T5_RB_MODE=off`), RTT 0/50/150 | -- | lockstep delay 6 | 0 | same |

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

Offline the same take-over and main-thread tick run too (latency branch,
`T5_LATE_INPUT`, default on; nothing else of netplay): the keyread thread read
the pads at the vblank, then waited for the frame lock the main thread holds,
and wrote the ring after the main thread had taken this frame's entry -- 5-12 %
of presses reached the game a frame late (docs/RENDER_PERF.md "Input
latency"). `T5_LATE_INPUT=0` leaves the pads to the game's own thread.

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
| This player closes the game window (Alt+F4, the X button, Esc) | The game ends (ps3recomp patch 0035; before it ran on without its window at about one frame a second, still in the session -- the opponent stalled and went out of sync, the match was voided as a desync). With a session set up: the result file gets `"reason": "quit"` (unless this match's result is out: a game closed after the KO keeps its result), BYE, exit code **7**; the launcher reports the match as this player's quit (a loss, docs/RANKED.md), the opponent's game sees `peer_quit`. Esc asks for a second press within 3 s while a session is set up (the window caption says so); Alt+F4 and X close at once |
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

**A closed game never comes back into its old session.** The launcher starts
a game again only for the next match, with that match's session (new ports,
key, match id); a persistent game that exits with code 7 (the player closed
it) is not a control-channel failure, so the launcher's fallback (a new game
process for the match whose command a persistent game never took) does not
fire for it either (`lobby/t5lobby/match_driver.py` `_watch_ctl`). Tested with
`tools/fight_flow_test.py --close 2:join:8`: the closed joiner ended 0.3 s
after WM_CLOSE with exit code 7 and "quit", the host's result said
`peer_quit`, the next match was a new session against a freshly started game,
in sync.

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

## Same game state on every CPU

Every player compiles the lifted game code on their own PC
(`tools/build_game_dll.py`, the launcher's Build): `-march=x86-64-v3` (AVX2,
FMA, BMI2, MOVBE) when the PC has AVX2, else the x86-64 baseline. Two PCs
play each other whatever they built, so both builds, on any x64 CPU (Intel or
AMD), must compute bit-identical game state. Since ps3recomp patch 0032
(branch cross-cpu, 2026-10-17) they do; the build ID does not need the CPU
class and the lobby keeps pairing everyone.

What can make two x64 PCs compute different floating-point results, and what
the lifted code does about each:

| Source | Before | Now |
|---|---|---|
| FMA contraction (a*b+c fused where the PPU code had two ops) | `-ffp-contract=off` for the lifted PPU code | unchanged |
| The C runtime's math (ucrtbase.dll) | a baseline build imported `fma`, `fmaf`, `trunc`, `truncf`, `ldexp`, `sqrt`, `sqrtf` from ucrtbase (every build `ldexp`, `sqrt`, `sqrtf`: the errno path of a negative square root). ucrtbase picks its path by CPU: `fma`/`fmaf` are one `vfmadd` with FMA3 and a software routine without (`_set_FMA3_enable`); `sin`/`exp`/`pow`/`atan2` have an FMA3 and an SSE2 version that disagree in 0.01-1 % of results; and the DLL's version comes with Windows | no library math in the lifted PPU or SPU code (`fp_audit.py`: "C runtime math imported: none" for v3, baseline and native builds). `runtime/ppu/ppu_fp_det.h`: square roots are `sqrtsd`/`sqrtss`, conversions `cvtsd2si`/`cvttsd2si`, rounding `roundss` (or an SSE2 version that matches it on all 2^32 floats), scaling an exact multiply |
| Fused multiply-add without FMA instructions | the C runtime's `fma`/`fmaf` | an exact software fma (128-bit integer product, one rounding) and fmaf (the double sum rounded to odd, then to single); a baseline build on a CPU with FMA3 uses the instruction. Checked against `vfmadd` on 300 M random and 4 913 special cases: 0 different results |
| `rcpps`/`rsqrtps` (Intel and AMD return different bits) | none in any build | none (`fp_audit.py` checks for them, their AVX-512 forms, `dpps`/`dppd`, x87 and `ldmxcsr`). The PPU estimates (`fres`, `frsqrte`, `vrefp`, `vrsqrtefp`) are the correctly rounded 1/x and 1/sqrt(x), the SPU's `frest`/`frsqest` the hardware table |
| MXCSR (rounding mode, flush-to-zero, denormals-are-zero) | nothing set or checked it | `runtime/platform/fp_env.c`: every runtime thread sets 0x1F80 when it starts (`host_sched_thread_start`), every lifted SPU run and guest callback checks it, and so does the return of every HLE call and lv2 syscall (OS or driver code on a guest thread could change it): restored, logged as `[fp] MXCSR changed to ...` |
| x87 | none (x64 code is SSE) | `fp_audit.py` checks |
| Code generation, undefined behaviour, uninitialised memory | -- | the cross-build pairs below: v3, baseline and `-march=native` (AVX-512 on this Ryzen) code agree on every frame |
| `vexptefp`/`vlogefp` (not used by this title) | `exp2f`/`log2f` from the C runtime | fixed double-precision formulas, within 1 ulp of the library |

**The regression check: `tools/cross_build_test.py`.** It runs a netplay
pair whose host and joiner are different builds of the same lift (same
runtime, different game DLLs) through `tools/rollback_net_test.py` -- direct
fight, scripted attacks, two full matches with KOs, RTT 50 +-5 ms, 3 % loss --
once with rollback (what players get) and once with `T5_RB_MODE=off`
(lockstep), and compares the two games' state hash of every frame (rollback:
the final hash, `f F <hash>` in frames.log, written when every input before
the frame is confirmed; lockstep: `f I ... <hash>`). Exit code 1 on any
differing frame, on a mismatch the built-in check reported, on result files
that disagree (winner, score, hash), on a crash or hang, on a side that did not
run the expected loop, or when fewer than 3000 frames were compared.
`report.txt` in the run directory has the verdict per mode and match.

One command, given the build folder of a runtime made with
`-DT5DR_GAME_DLL=ON` (it holds t5dr.exe + t5dr.lib, as a release ships them;
`build/cmake-dll` here):

```
python tools/cross_build_test.py --build build/cmake-dll --out v3_vs_base
```

`--build` compiles the lift (`--recomp build/recomp --spu build/spu --deps
deps/ps3recomp` by default) twice with `tools/build_game_dll.py`, `--march
x86-64-v3` for the host and `--march none` for the joiner (`--march1`,
`--march2`; objects stay in `build/cross-build-runs/bin/<march>/`, so a rerun
only recompiles what changed), adds `--audit` (`tools/fp_audit.py --strict` on
both DLLs), and runs the baseline joiner as a PC without FMA3 runs it:
`PS3_FP_SOFT_FMA=1` (the software fma although this CPU has FMA3) and
`PS3_CRT_FMA3=0` (the C runtime's own non-FMA3 paths); `--hw-fma` keeps the
instructions. With two finished builds instead:

```
python tools/cross_build_test.py --exe1 X/v3/t5dr.exe --exe2 X/base/t5dr.exe --out v3_vs_base \
    --audit --env2 PS3_FP_SOFT_FMA=1 --env2 PS3_CRT_FMA3=0 [--fight 13,17,28,2 --next 8,31,17,2]
```

`--flow persistent` plays the matches in games that stay open (a netplay
session per match, `tools/fight_flow_test.py --mash`); `--control` runs the
host's build on both sides afterwards with the same matches, which tells a
difference between the builds from a rollback or timing problem the port has
anyway. `PS3_FP_TEST_MXCSR=<value>` runs the guest threads with another MXCSR
(a negative test); ps3recomp's `runtime/ppu/tests/test_fp_det.c` checks the
software paths against the instructions (PASS/FAIL). The netplay log says
what each side ran: `fp: game code -march=x86-64-v3, main thread MXCSR 0x1F80`.

**Results** (2026-10-17, one Ryzen 9 7950X, Windows 11; patch series 0001-0029
+ 0031 + 0032, one lift; v3 = `-march=x86-64-v3`, base = no `-march` with the
software fma and the C runtime's non-FMA3 paths, native = `-march=native`,
which on this Zen 4 means AVX-512). Every match was two rounds to a KO;
the rollback runs had 49-481 rollbacks per side (up to 664 re-simulated
frames). Run directories: `build/xc/runs5/<pair>/{rollback,lockstep}`:

| host vs joiner | matches (stage) | rollback: frames compared, different | lockstep: frames, different |
|---|---|---|---|
| v3 vs base | Asuka vs Lili (20), Lili vs Dragunov (24) | 8,997, **0** | 9,002, **0** |
| base vs v3 | Kazuya vs Jin (31), Nina vs Hwoarang (33) | 10,617, **0** | 10,602, **0** |
| native vs base | Law vs Paul (25), King vs Marduk (22) | 11,937, **0** | 12,501, **0** |
| v3 vs base, persistent game, 3 sessions, both sides mashing | Lili vs Dragunov (33), Kazuya vs Heihachi (25), Lili vs Dragunov (31) | 16,454, **0** | 16,499, **0** |
| v3 vs base (`--build`) | Bryan vs Steve (28), Christie vs Feng (17) | 9,417, **0** | 11,601, **0** |
| v3 vs native | Bryan vs Steve, Christie vs Feng | 9,417, **0** | 11,641, **0** |
| base vs native | Bryan vs Steve, Christie vs Feng | 9,417, **0** | 11,622, **0** |

Every result file pair agreed (winner, score, hash), the built-in check
reported 0 mismatches, and `fp_audit.py --strict` passed on both DLLs. The
first four rows ran before the hash change described next (they compared more
words); the Bryan-vs-Steve rows after it. Earlier runs of the same kind in
`build/xc/runs` (b2-b4 builds, the same result) are not counted here.

Before patch 0032 a v3 build and a baseline build also played in sync on this
PC (runs `before_v3_vs_none`: 11,453 rollback and 9,602 lockstep frames, 0
different): the C runtime's `fma` gave the same bits as `vfmadd` here. A PC
without FMA3 would have run ucrtbase's software `fma`, and its `sin`/`exp`
family has separate FMA3 and SSE2 code; 0032 takes all of that out of the
game code instead of trusting it.

Negative tests (same build both sides, one side with `PS3_FP_TEST_MXCSR`):
round toward zero (0x7F80) -- every frame different from frame 225 on, in
rollback and lockstep, and `[fp]` names the MXCSR; flush-to-zero +
denormals-are-zero (0x9FC0) -- 4,439 frames, 0 different (this match makes no
denormal), so FTZ/DAZ would only show where the game produces denormals,
which the MXCSR check rules out anyway. Offline (`T5_NET_MODE=local`, the same
scripted Bryan-vs-Steve match one instance at a time): v3, v3, native, native
gave the same hash on all 7,141-7,321 frames.

**The KO camera.** At first the Bryan-vs-Steve pairs failed: 21 frames from
the final KO camera (frame 4239) had different hashes, then they were equal
again and both results matched. It is not the builds: identical builds did
the same (base vs base under rollback, v3 vs v3 in lockstep). Under rollback
it came in 7 of 9 runs at RTT 50 (none at RTT 0), in lockstep in 1 of 4
(`control_lockstep` of `xB2_v3_vs_native_bryan`), with `T5_RB_CUT=none`
(re-simulated frames run the draw too) in 0 of 2. The words (`T5_NET_DESYNC_DUMP=1`): camera state
that follows timing rather than input -- the rest of the two 0x1F0-byte camera
blocks at 0x10099730 / 0x10099920 whose tails fight-polish had already left
out after its 100-frame lockstep transient, and the second word of the
counters at +0x638 of the second and third fighter block. Christie vs Feng
showed a 12-byte secondary-motion point at 0x1008FFF0 the same way (13-33
frames under rollback; v3 vs v3 and native vs native too). Both are now left out of the state hash
(`kDefaultHashSkip`, `kGameSkip`; docs/DIRECTFIGHT.md "Known transient
mismatches"). Before that, a ranked match with such a KO was voided (any
desync voids it, docs/RANKED.md).

**Cost** (main-thread busy ms per fight frame, offline Asuka vs Lili, median
of 3000 frames from the `T5_PERF_LOG` busy column, two instances at a time on a quiet
machine; two runs of one build differ by up to ~0.5 ms, so each was run at
least twice, once in each start order):

| game DLL | before 0032 | with 0032 |
|---|---|---|
| v3 | 4.90, 5.34 | 5.51, 5.15 |
| base on a CPU with FMA3 (uses the instruction) | 5.34, 5.54 | 5.84, 5.94, 5.39 |
| base as on a CPU without FMA3 (software fma) | -- | 6.07, 5.53 |
| native (AVX-512 here) | -- | 4.93 |

All ran at 59.9 fps. On average 0032 added ~0.2 ms (v3) and ~0.3 ms (base)
per frame, inside the ~0.5 ms spread between runs; the software fma (a PC
without FMA3) about 0.1-0.2 ms more. The frame budget is 16.7 ms. No reason to
build the game code the same way everywhere: the targets agree, and v3 stays
cheaper than the baseline (~0.4 ms a frame here).

**What one PC cannot show.** Intel against AMD: the game code is made of
IEEE-754 basic operations, conversions and square roots only (no estimate
instruction, no x87, no library math, `fp_audit.py`), which every x64 CPU
computes alike under the same MXCSR; that is the argument, not a run. A real
CPU without FMA3 or AVX2: stood in for by the baseline build with
`PS3_FP_SOFT_FMA=1 PS3_CRT_FMA3=0`.

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

## Desync hunt (branch desync-hunt, 2026-10-19)

Real players saw desyncs with no rollback before them (0.1.9 match 2, 1.0.0
19:38 match 1) and, in the owner's 1.0.0 logs of 2026-10-18, more: after an
opponent switch every frame different from the first compared one (Heihachi
vs Kazuya and Heihachi vs Heihachi on stage 29, two opponents: 4,998 of 5,221
and 7,393 of 7,619 frames), a rematch against Mokujin likewise, and in other
matches 829-1,298 mismatching frames that began mid-round and ended at the
next round (Jin vs Dragunov, Kazuya vs Heihachi). None of it reproduced with
two games on one PC as the tests ran them.

**The cause: the title's second random generator.** 0x3AFC3C is a shuffled
LCG (x * 0x19660D + 0x3C6EF35F, a 32-word table) kept in the calling thread's
TLS -- state at TLS+0, a "seeded" byte at +0x10094, the last draw at +0x10098,
the table at +0x1009C; only the main thread draws from it, so it lives in the
main thread's TLS block 0x0E000000. Netplay reseeded the Mersenne Twister and
the C rand() at its sync points, never this one. Most of the game draws from
it: the fighters' move effects, the camera (0x878CC: angle and distance of a
camera move), the game mode's set-up, and also effect and stage tasks beside
the scene (the stage emitter 0xA1768, ~10 draws a frame; effects that spawn
9-11 particles when they first play). Three ways it went apart between PCs:

1. *History.* Its state at a match depended on everything the process had
   drawn since boot: a game that had played other opponents and one just
   started began the fight from different states -- the opponent-switch
   desyncs.
2. *Timing.* An effect plays its first burst on the frame its data has come
   in from the file thread, which no loader drain waits for: a frame or a few
   apart on two PCs (two runs of one scripted match in one process: the burst
   at frame 470 in one, 477 in the other), and every draw after that differed.
3. *The select screen.* The game mode's set-up picks Mokujin's fighter for the
   match from it (0x121E0C <- 0x5A304 <- 0x53C88, game mode phase 2), before
   lockstep frame 0, after however many draws each PC's select screen made:
   Mokujin copied Feng on one PC and Kazuya on the other (0x1009094C 0x1001F
   vs 0x1000F) -- the ingame-select agent's "Mokujin desyncs" too.

**Why it was gameplay, not cosmetic.** The camera words are left out of the
hashes as display state, and so is +0x6C8 of each fighter block (0x10090708,
0x10090FD8): the fighter's camera-projected screen x. But 0x808D8 compares the
two and writes which fighter stands on the left (+0x1C2/+0x1C3 of the blocks
at 0x10090040 / 0x10090910), and that decides which way an up or down tap
sidesteps. Two PCs with different camera draws turned the same sidestep
different ways (the first differing words of every such run: the side flags,
then the fighters' processed input, DOWN on one PC and UP on the other), and
the fight came apart -- or, when the round ended the same way, came back
together at the next round: the mid-round transients of the owner's logs.
The side flags were in the hash all along (they flagged it); the camera
draws were not.

**The fix** (`src/rollback/rb_rand.cpp`, `src/netplay/t5_hooks.cpp`
`reseed()`; T5_TLS_RAND=0 turns it off):

- the scene (the scene task 0x10BD8: menus, game mode, fight) draws from the
  TLS generator as before; every other draw on the main thread -- effect and
  stage tasks, render passes -- comes from a private generator in host
  memory, so they can no longer move the scene's sequence, whenever they run
  (a rollback's draw cut, which skips some of them in re-simulated frames,
  cannot either);
- netplay reseeds the TLS generator at every sync point (frame 0 of a
  session, every scene barrier) from the match seed, like the Twister and
  rand(): the process's history no longer reaches a match;
- with a direct-fight session set up, the generator is pinned to the session
  seed (T5_NET_SEED, the lobby's, the same on both PCs before the handshake)
  at every boundary while the select mode runs, so the game mode's set-up
  (Mokujin's pick) draws the same on both PCs however long the select took.

The TLS block (0x0E000000, 128 KB) is in the rollback state already
(`rb_state.cpp` kSave): a restore puts the generator back with the frame,
and the re-simulation draws the same numbers (rb_equiv_test --lag and
--force below: equal on every frame).

The hashes keep the camera words out and the side flags in (comments at
kDefaultHashSkip / kGameSkip).

**New tools.**

- `tools/rb_equiv_test.py`: one game, the same scripted match twice (netplay's
  local mode: both players scripted with motion inputs, the rollback loop
  running, a fixed seed and clock), compared frame by frame on the final
  gameplay hash. The test run adds `--lag N` (T5_NET_LOCAL_LAG: the second
  player's input known N frames late -- predicted, mispredicted, rolled back
  as against a peer N frames away), `--force every:depth` (T5_RB_NET_FORCE:
  rollbacks with the same inputs), `--cpus N`, `--test-env` (any hardware
  stand-in below); `--full` hashes without the skip list (T5_RB_HASH_FULL),
  `--dump` diffs the words around the first difference (T5_RB_DUMP_AT,
  `tools/rb_desync_diff.py --first-diff`). A deterministic game gives the
  same hash on every frame, at any fps, with or without rollbacks; before the
  fix no two runs of Jin vs Dragunov did (all twelve apart from frame 1546).
- `tools/fight_flow_test.py`: `--cpus1/--cpus2` (affinity + PS3_CPUS),
  `--hitch2 MS[:MIN:MAX]` (T5_TEST_HITCH: the joiner's main thread stalls
  while its other threads run on), `--gamedata1/2` (a player's own save),
  `--clock2 S`, `--fresh-every K --fresh-role alt` (opponent switches against
  fresh games), `--colors` (costumes), `--moves` (motion inputs: electrics,
  hellsweeps, qcf/hcb, dashes, sidesteps, throws, ki charge -- a random mash
  almost never does them).
- Runtime (patch 0040): `PS3_TEST_FS_DELAY=ms[:ms_per_MB]`, a slow or cold disk
  on one PC. Diagnostics: `T5_RAND_TRACE=1|2|3` (rand() and TLS-generator
  calls per thread and caller, distinct caller chains with mode and phase,
  per-frame draws), `T5_RB_WFT_NET=from:frames` (the write-fault tracer in the
  netplay loop).

**What was tested** (this PC, Ryzen 9 7950X, other agents' games running;
fixed build unless marked):

| test | build | what | runs / matches | frames compared | result |
|---|---|---|---|---|---|
| rb_equiv, no rollback, Jin vs Dragunov 25 | before | two runs of one scripted match, one process | 12 runs | ~2,000 each | every pair apart from frame 1546 (the TLS draws) |
| rb_equiv, no rollback, Jin vs Dragunov 25 | fixed | the same, fps 22 vs 28 | 2 | 1,979 | equal |
| rb_equiv `--lag 3/4` (390-570 rollbacks) | fixed | Kazuya vs Feng 32, Jin vs Dragunov 25, Heihachi vs Mokujin 29 (twice), Devil Jin (Triangle) vs Dragunov 25, Marduk vs King 22 (2 rounds, KOs, 1,047 rollbacks), Law vs Marduk 26 | 8 | 1,799-4,738 each | equal on every frame, same result |
| rb_equiv `--force 9:5` (223 forced) | fixed | Kazuya vs Heihachi 30 | 1 | 2,339 | equal |
| pair, persistent, both fresh, `--moves` | before (main) | Kazuya vs Feng 32 | 1 | -- | 1,265 / 2,822 mismatching, different results |
| pair, opponent switches (fresh vs persistent, alternating), rollback | fixed | 12 matches, 11 switches: Mokujin, Heihachi, Kazuya, Devil Jin (Triangle), Jin, Dragunov, Feng, Lili; stages 17-33 | 12 | -- | 12/12 confirmed, 0 mismatching frames |
| the same, lockstep | fixed | 12 matches, 11 switches | 12 | -- | 12/12, 0 mismatching frames |
| the same with the TLS isolation but no select pin | fixed (partial) | match 1 Mokujin vs Heihachi | 1 | -- | Mokujin's pick apart: failed (led to the select pin) |

The hardware matrix (4/6/16 cores, 240 Hz, hitches, stutter, slow disk,
launcher mute, clock skew, mixed delays, FMA against no FMA) follows on this
branch.

**Left open.** Two PCs that differ in the CPU's make (Intel vs AMD) or a real
display at 240/500 Hz were stood in for, not used. The private generator
makes effect particles and stage emitters differ between the two PCs' screens
(display only, as the camera may).

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
