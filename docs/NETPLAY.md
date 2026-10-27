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

**Match result** (`src/netplay/match_score.h`, 1.1.3). `score` is the rounds
each player won: the u8 at +0xA1 of each fighter's block (P1 0x10090030 ->
0x100900D1, P2 0x10090900 -> 0x100909A1; +0xA2 is an i16 with the fighter's
last round, 1 won / -1 lost). The game counts a round there on its KO frame --
the last one on the very frame the decided byte 0x1008EBD5 rises -- and clears
both counts when the next match's game mode starts, ~230 frames after its FIGHT
START (the decided byte goes back to 0 on the same frame). `winner` is the one
with more rounds (equal = a draw, `null`). The decided byte itself says how the
match ended: 1 P1 won, 2 P2 won, 3 a draw (a time-out with equal health or a
double KO in the deciding round counts the round for both: a no-input pair,
first to 1, ended 1-1). Before 1.1.3 the score came from the
battle config's bytes 0x1008EBDA/DB, which a menu-driven VS game was thought to
count rounds in: they stay 0 in direct fights, so the score was made up from
the winner byte 0x1008EBD6 as rounds-to-win : 0 (every 3-2 and 3-1 read 3-0),
and the few times one of them was 1 at the end (mashing rollback pairs) that was
the score: `[0, 1]` for a match P2 won 3-0, `[1, 0]` for P1's. A drawn match
was P1's win (the winner byte is 0 in a draw). The winner was right otherwise
(it decides ratings and sets), but the lobby also decides on
the score: a result whose opponent reports a lost connection stands only with a
full score -- the winner at the rounds to win (docs/RANKED.md "Results") -- so
`[0, 1]` turned a won match into a void there; history, result cards and the
admin's match list showed the made-up score. Found by dumping guest memory at
every round's replay of a rollback pair and watching the words frame by frame
(`T5_DF_WATCH`): 3-2, 3-1, 0-3 and 3-0 matches. When the counts cannot be the
match's (both 0, above the rounds to win, or another verdict than the decided
byte's) the decided byte decides with rounds-to-win : 0 and the log says so
("do not fit the match"). A
session that ends mid-match writes the rounds won so far (0-0 while the last
match's decided byte is still up: its counts are still there).

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

### Bind address

Windows Firewall asks "allow public and private networks to access this app?"
once per exe path when a program binds a non-loopback address; loopback is
never filtered. Test runs start `t5dr.exe` from many build folders with both
games on 127.0.0.1, so they bind 127.0.0.1 (`src/netplay/net_bind.h`):

- `T5_NET_BIND=<IPv4>` binds exactly that address (`0.0.0.0` = every
  interface). Anything else is noted in the log and every interface is used.
- Unset: 127.0.0.1 when `T5_NET_PEER` is a loopback address (127.x.x.x or
  `localhost`) outside a lobby match (`T5_NET_MATCH` unset); otherwise every
  interface, as before. A lobby match keeps every interface even with a
  loopback peer: the launcher's relay bridge hands players
  `T5_NET_PEER=127.0.0.1:<port>`, and a player's game does not change.
- The log says what was bound and why: `hosting on UDP 127.0.0.1:7461 (bind:
  T5_NET_BIND)`, `joining 127.0.0.1:7462 from UDP 127.0.0.1:63463 (bind:
  T5_NET_BIND)`; a player's game says `0.0.0.0 ... (bind: default)`.

The launcher never sets it. Every tool that starts games for a pair on this PC
sets `T5_NET_BIND=127.0.0.1` with `setdefault` (an explicit value wins); with a
lobby on this PC (e2e, `lobby/tools/*`, `dryrun_online.py --server
127.0.0.1:PORT`) the lobby client's game socket follows it too
(`t5lobby/nat.py bind_ip`), so the punch only finds 127.0.0.1 and the game is
reachable there. Stub games bind 127.0.0.1; lobby tests set it in
`lobby/tests/util.py`. The runtime's own sockets: `sys_net` P2P sockets already
bind `PS3_NET_BIND` (default 127.0.0.1, patch 0011); other `sys_net` sockets
exist only in the game's dead PSN online mode; `cellHttp`/psnr only connect out.
Tests: `tests/test_net_bind.py`.

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
  as `T5_RB_NET_DELAY` on both PCs, and it wins over the player's setting;
- **far matches** (1.1.5, ranked or not): above 150 ms measured round trip the
  lobby server sends at least 3 frames the same way, 4 above 250 ms
  (`T5L_PING_DELAYS`, default `150:3,250:4`; ranked: the higher of the two
  values), never above the session's lockstep delay. About a quarter of the
  matches are relayed, many of them far: with 2 frames a 200 ms match predicts
  ~4 frames of the opponent's input and rolls back that deep on every surprise;
  3-4 frames of delay make the jumps smaller. Both PCs get the same number, so
  the host's pick is that number ("both players set 3"); a launcher from 1.1.4
  passes it on too (it passes any `input_delay` of `match_start`). A rematch
  inside the running games keeps its session's delay.

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

**Protocol v4** (costumes-online, 1.1.3): the COSTUME packet below. A v3 game
never sends one and the stage confirm waits for it, so a v3 peer is a
different build (`build_mismatch`, NETPLAY_VERSION 4).

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

## Which controller plays online (1.1.2)

Player report on 1.1.1: "my DualSense works only offline; the launcher doesn't see it at all". The runtime
(patch 0009) gives every controller a port in the order it finds them -- XInput pads first, then the
PlayStation pads it reads as HID devices (0042), then DirectInput -- and the keyboard joins port 1 while the
game window has the focus. Offline the title reads every port, so a pad on port 2 plays (player 2, and the
menus take either). Netplay took the local player from port 1 only (`sample_local` -> `device_input(0)`), so a
DualSense behind any other controller -- a virtual Xbox pad (DS4Windows, DSX, ViGEm), a handheld's built-in
pad, a second pad or a wheel -- did nothing online. The in-game select (`df_pick.cpp`) and the replay controls
read port 1 too.

Now (`src/netplay/local_pad.cpp`, `local_pad.h`): online the local player is **the controller pressed last**.
Every local port with something on it is read at every live sample (`cellPad_sample_local`, each with its
own tap latch); a port whose buttons, or a stick pushed past half way (with hysteresis), went down becomes the
player at once, that press included. A port that never changes (an idle pad, a virtual pad nobody uses, a
pedal resting at one end, a button held since it was plugged in) never takes over; while the player's port
was pressed in the last 100 ms another port cannot take over, so one pad seen twice (DS4Windows' virtual pad
and the real one) never makes the input jump. Port 1 only, as before: `[port1] device = ...` pinned in
`controls.ini` (read once with the runtime's rules), local mode (two players at one PC), netplay off, or
`T5_NET_PADPORT=N` (that port only; `1` = 1.1.1's behaviour). The log names the rule and every switch:
`[netplay] local player: port 2 now (pressed there; ...)`.

Why not merge all ports: a controller resting with something held (a pedal, a stick's drift past half, a
stuck button on a cheap pad) would then hold that input for the player all match. Why not "the first port
with a device": a virtual pad or a handheld's own pad is that port. Sync is untouched: only this PC's sample
changes, and it is exchanged like any input; rollback re-simulation replays exchanged inputs and never reads
devices (`sample_local` runs at live boundaries only). Reading the pads does not depend on the focus (XInput,
the HID reader, DirectInput with `background = 1`); only the keyboard does, by design -- the launcher now
brings the game window forward when a match starts while the launcher is in front (docs/ONLINE.md).

Test: `tools/e2e/run.py --only net_dualsense [--netcode lockstep]` -- the launcher's own Online tab and game
start (persistent game, window minimized and never in front), one player with a fake DualSense on Bluetooth in
its extended mode (`PS3_PAD_HID_FAKE`, reports from `tools/ps_hid_reports.py`) that the runtime puts on port 2
(port 1: the picker's pad file, plus the keyboard), mashing through the fake pad; two matches (two sessions,
picks with the pad file in between). Checks: the presses are in the other PC's frame log, 0 mismatching
frames, the same result hash. On 1.1.1's code: 695 presses sent, 0 frames with them on the other PC.
`tests/test_local_pad.py` (tests/c/local_pad_test.cpp) checks the rule with fake ports.

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

## In-game select: picks and a paused lockstep

With the in-game select (docs/DIRECTFIGHT.md "Character select in the game")
each player picks on the game's own select screen, which runs on each PC on its
own; only the picks cross the network. Two small additions, both on the
session's own socket and key:

- **PICK packets** (type 6): `{key, pick, ack}` -- the match the pick is for
  (the session's match number), the sender's pick (character, confirm button,
  model id, cursor cell; 0 = none yet) and the key of the peer's pick the
  sender holds. The network thread resends our pick every 100 ms until the peer
  acknowledges it, and acknowledges a received pick three times (never at
  once: two sides answering each other would not stop). `t5_netplay_pick_send()`
  / `t5_netplay_pick_peer()`.
- **COSTUME packets** (type 7, docs/DIRECTFIGHT.md "Custom costumes online"):
  `{hash, total, offset, len, ack_mask, ack_hash}` + up to 1,024 bytes -- a
  piece of the sender's custom costume table (at most 9,283 bytes, so at most
  10 pieces; len 0 = an acknowledgement only), which pieces of the receiver's
  table the sender holds, and that table's FNV-1a hash once the sender has all
  of it and the hash matched. Sent by the network thread from the moment both
  are connected: up to three missing pieces every 100 ms until the peer
  acknowledges the whole table by its hash; each received piece is
  acknowledged three times. A table is taken once, when its pieces add up to
  its hash; malformed pieces (above the bound, between pieces, of the wrong
  length or longer than the packet) are dropped; a restarted peer process
  starts both tables over. `t5_netplay_costume_set()` /
  `t5_netplay_costume_peer()`; tests/c/netplay_fuzz.cpp checks all of it.
- **A paused lockstep** between two matches of a session: `t5_netplay_pause()`
  makes the next frame a sync point (a scene barrier; under rollback every
  input before it is confirmed first), then the lockstep (or the rollback loop,
  which stops and drops its undo logs) is paused and the hooks run as between
  two sessions of a persistent game -- keyread tick on the main thread with
  neutral pads plus the direct-fight driver's injections; the socket,
  keepalives and the timeouts stay. `t5_netplay_start()` at the next fight
  resumes at the paused frame number: another sync point, then the game's frame
  counters, input ring and random seeds are set equal as at a fresh start (the
  two select screens ran for different numbers of frames), the match's
  mismatch count starts there, and the rollback loop starts again.

## No pause online (branch online-no-pause, 1.1.2)

Player report (1.1.1): "you gotta remove the fact that you can pause when you're playing against
the opponent. I was in the middle of doing my combo, the guy spammed pause." START opens the
game's pause menu in a VS fight (RETURN TO GAME PLAY, COMMAND LIST, CONTROLLER SETUP, RETURN TO
TITLE SCREEN). Online START was an input like any other: both games get both players' inputs, so
either player's START paused the fight in both games. Tekken 6 and 7 online have no pause. Now
nobody can pause an online fight. src/ only, no runtime patch (0054 stays unused).

**The rule** (`src/netplay/no_pause.h`, applied by `t5_hooks.cpp` `no_pause_rule()`): in every
direct-fight session -- every online match (quick, ranked, casual, rooms, invites) and the replay
of one -- START is taken out of **both** players' inputs of a frame right where they go to the
game (`g_cur`, what `cellPadGetData` returns): live frames, frames a rollback re-simulates, and
frames a replay plays back alike, after the exchange and after any prediction. Two exceptions,
both places where START skips something and cannot pause:

| where (game state at the frame's boundary) | START | why |
|---|---|---|
| fight phase 17, round state `0x1009322C` 1, 2 (the fighters' intros), 8, 9, 0xC (after a round: KO slow motion, replay, on to the next round) | the rule's own presses once **both** players pressed START there (1.1.4, "Skipping intros and replays online" below); until then taken out | the skip; one player alone skips nothing (1.1.2/1.1.3 kept START in the replay for either player, but no player's START ever left the PC, so nobody could skip it) |
| from 40 frames after the match was decided in this fight (decided byte `0x1008EBD5` rising after a fought frame) until the game asks for the select screen | kept | the direct-fight driver (lockstep, `df_fight.cpp post_match_skip`) and the rollback loop's post-match rule (`rb_net.cpp post_record`) skip the last KO replay and the win pose with START from 40 frames after the decision ("After the match", DIRECTFIGHT.md) |
| everything else: the round's READY/FIGHT (round state 4), the fight (5), the KO frame (6), the loading (phase 0..12), a rematch's select screen in lockstep | taken out | the pause menu |

The window after the decision opens only where the decided byte rises after a frame that was
fought: the last match's byte is still set ~230 frames into a rematch's fight, where the pause
menu works again.

**Each player's own START goes out only where it can skip** (`netplay_core.cpp device_input`,
`np::set_no_start`, `t5_hooks.cpp start_gate`): in a direct-fight session the local devices' START
bit -- the pad's START, the keyboard's Enter, any remap or macro that ends in START -- is dropped
before the input is sent, except while the live boundary shows a skip part (1.1.4). The driver's own
presses (`g_local_inject`), the rollback rule's forced input and the test inputs
(`T5_NET_SCRIPT`, `T5_NET_PADFILE`) are not touched there; the tests use the latter to play a
modified client that sends START anyway, and the frame rule takes it out again.

**Why both games stay equal (the proof).** What the rule does to frame f is a function of the game
state at the boundaries up to f's (the phase word, the decided byte, the round state, the mode
manager's next mode -- the same on both PCs while they are in sync, which the per-frame state hash
checks) and of frame f's two inputs (the same on both PCs: lockstep exchanges them before the
frame runs; under rollback the final re-simulation runs with the confirmed inputs; a replay reads
them from the file). It never looks at which PC runs it, which slot is local or where an input
came from, and it treats P1 and P2 alike (`apply(swap(in)) == swap(apply(in))`). So both games
hand the game identical inputs for every frame, by induction identical states. The window's start
is kept per boundary (frame mod 4096, tagged with the frame) and is not part of the rollback
snapshot: a re-simulated boundary is recorded again from the restored state, and the boundary a
record reads (its predecessor) always comes from the latest run of that frame -- a rollback to
first_wrong re-runs every boundary from first_wrong on, and the ones before it ran on correct
inputs. The records are cleared at every frame 0 (a session numbers its frames anew). The replay
recorder keeps the raw inputs from the rings; playback applies the same rule at the same
boundaries, so a recording plays back identically. The replay viewer's own START (pause the
playback, docs/REPLAYS.md) is read from this PC's pad, outside the session's inputs, and works as
before. Offline (no netplay, also an offline `T5_FIGHT`) nothing changes: START pauses.

**The pause menu in memory** (for tests; probes p1/p4 in build/nopause): `0x10092EA0` goes 0 -> 2
when the menu opens and back to 0 when it closes, together with `0x1008F0B4`/`B8` 1 -> 0 and
`0x100996B4` 1 -> 3. `tools/fight_flow_test.py` and `tools/pick_flow_test.py` take
`--mash-start N` (with `--mash`: about every N-th mashed input is START, alone or with an attack);
they watch that word (`T5_DF_WATCH`) and fail the run if the menu ever opens, and print how many
START frames the rule took out of each player's input and kept (round replays and the match end;
the game's log line calls both "the post-match skip") from the games' `no pause online` log lines. `--net-timeout S` gives the games more slack on a PC busy with
other games. The log says `frame N: START taken out of P1's input (no pause online; ...)` once
per match and the tally at its end and at the next sync point (`no pause online, the match: ...`,
`after the last match: ...`). The tally counts live frames; under rollback those include
predicted inputs (the last input repeats, START too), so the two PCs' tallies differ -- what has
to agree is the state hash, and it does.

**Tests.** `tests/test_no_pause.py`: `tests/c/no_pause_test.cpp` runs the rule against a model of
the game (rounds with KO, replay and the next round's intro; the pause menu in every round state
but the replay; a decided byte that stays set into the next fight; START mashed by P1, P2 or both)
on two PCs in lockstep, under rollback (inputs 0-9 frames late, predictions, ~8,000 rollbacks per
PC per run) and as a replay: identical hashes on both PCs at every frame, the pause menu never
opens, round replays and match ends are still skipped by START; without the rule the same inputs
do pause (the model has teeth; a rule that let START through in the KO slow motion, or on the
stale decided byte, fails it). The source checks: both places that hand inputs to the game run the
rule first, the device path drops START, the rule names no slot.

In the game (build/nopause/runs; two games on this PC, minimized, muted, below-normal priority;
"START out / kept" = the games' tallies, P1 + P2):

| run | what | result |
|---|---|---|
| p1, p4 (main's code) | local lockstep, START at frame 900, then every 60 frames | the PAUSE menu (screenshot); opened 18 times |
| p5 (this branch) | the same presses | no menu, the fight's timer runs on (screenshots) |
| ffA_rb | rollback, persistent game, new session + 2 rematches, first to 3 rounds, both players mash (every ~8th input START), Lili/Dragunov, Jin/Xiaoyu, Kazuya/Heihachi | 3/3 confirmed, same winner and hash (d0dc4cf2.., 89c5ef7a.., 2b7d413a..), 0 mismatching frames through 23,399; menu opened 0 times; START out 1129 + 1130 / 3211 + 2754 frames (predictions included), kept 55 / 74 (round replays, match ends) |
| ffB_ls | the same in lockstep (`T5_RB_MODE=off`), Bryan/Steve, King/Christie, Asuka/Law | 3/3, hashes 4387a2b6.., c120376c.., 1024092d.., 0 mismatching frames through 17,399; menu 0; START out 818 + 842 and kept 51 -- the same numbers on both PCs |
| pfA_rb_ranked | rollback, in-game select (Jin RP vs Lili LK picked on the select screen), then games 2 and 3 locked: a best-of-3 ranked set (2-1), mashing START, 2 rounds | 3/3, 0 mismatching frames through 12,599; menu 0; START out 691 + 775 / 657 + 679, kept 44 / 43 |
| pfB_ls_picks | lockstep, in-game select in every match: Jin vs Lili, then two rematches picked again (random vs Kazuya LP: Anna; Asuka vs Xiaoyu), the lockstep paused at each select screen and resumed, mashing START, 2 rounds | 3/3, 0 mismatching frames through 11,999; menu 0; START out 581 + 572 and kept 43 on both PCs |
| ffC_rb_merged | rollback after merging main 06adda9 (loopback bind), new session + rematch, first to 3, Yoshimitsu/Feng, Steve/Hwoarang, START every ~6th input | 2/2, 0 mismatching frames through 12,599; menu 0 |
| replays of pfA | both players' recordings of the ranked set played back (`tools/replay_play.py --press 8:START,13:START`: the viewer's own pause) | both IDENTICAL: 217 hashes, 3 results, 6/6 sync points each; "paused ... going on (paused 5.0 s)" |
| dev2 | local lockstep, this PC's "pad" (PS3_PAD_FILE, the device path) pressing START + CROSS 1,007 times | CROSS in P1's input on 3,350 of 6,642 frames, START on none, menu 0 |
| s1760 / s1900 (main's code) | START in a round's KO slow motion / in its replay | nothing / the replay skipped 5 frames later; no menu either time |
| off1 | offline direct fight (no netplay), START in the fight | the PAUSE menu opens (0x10092EA0 -> 2 at the press; screenshot) |
| smoke quick | offline menus, arcade, VS with two pads, practice, title twice | PASS (81 checks) with up to 10 other games running; an earlier run beside 16-20 other games failed `practice` (black frames, no fight HUD) -- main's exe failed it the same way at that load |

## Online training and the health handicap (1.1.5, branch online-training-115)

Two match rules that change what the game simulates, so both PCs must apply them on the same frames
(`src/netplay/match_rules.h`, the lobby's side in docs/ONLINE.md "Training rooms and the health handicap"):

- **Training** (a training room's fights, `train=1` on the fight line): endless health like Tekken 8's
  practice lobby, no round timer, nothing counted. A player who holds SELECT for a second gives up: their
  health goes to 0 and the game KOs them at the next frame, which ends the fight (training fights have one
  round); both launchers then go back to the select screen by themselves (a rematch), so this is also how
  two friends pick other fighters.
- **Health handicap** (`life=P1|P2`, percent): the game's own VS handicap. The battle config holds each
  side's percent (0x1008EBF4 / 0x1008EBF8, 100 after the select screen's handicap bar); the game mode's
  set-up turns it into the fighters' maximum health (fighter block +0x6C0, 16.16 fixed point: 145.0 at 100 %,
  72.5 at 50 %, 108.75 at 75 %) and their health at each round start (+0x6BC). The direct-fight driver writes
  both words at the game mode's first frame, before that set-up runs, on both PCs alike. The bars show the
  smaller maximum as a shorter bar.

**The training rule** (`np::TrainingRule`, called by `training_rule()` in `t5_hooks.cpp` right after the
no-pause rule): on the game state at the boundary of every frame that runs -- live, re-simulated by the
rollback loop, played back from a replay or a live stream -- after that run's inputs are final:

- only while the round is fought (round state 0x1009322C = 5, the decided byte 0);
- the round timer (0x1008F054, frames) is held at 3600 (60 s): no time-out;
- a fighter's health goes back to its maximum once it has taken no damage for 60 frames: a second after the
  last hit of a combo, standing, blocking or on the ground; a stream of hits keeps it down as in a real fight;
- SELECT held 60 frames (in that player's input of those frames, the exchanged one) sets their health to 0.

Found by probes of the running game (offline, `T5_DF_WATCH` / `T5_DF_POKE`, build/int115/h-runs): health and
maximum per fighter block, the timer counting 3600 down from round state 5, the handicap words read at the
game mode's first frame, and a health word set to 0 at a boundary KOs that fighter in the next frame
(MATCH OVER, the winner the other side).

**Why both PCs stay equal.** The rule reads only the game state at the boundary and the frame's two inputs
(the exchanged ones), never which PC runs it or which side is local, and it treats both slots alike. Its
writes happen after the boundary's state hash and snapshot (lockstep: after `state_hash`; rollback: after
`on_boundary` commits), so a rollback's restore undoes them with the rest of the frame (the write watch sees
host writes too) and the re-simulation writes them again from the restored state. Two counters per player
(frames without damage, frames SELECT held) are kept per frame (frame mod 4096, tagged with the frame), each
from its predecessor's entry -- the no-pause rule's scheme: a re-simulated boundary is recomputed from the
restored state and its final inputs, and the boundaries before a rollback's first wrong frame ran with the
right inputs. A sync point renumbers frames differently on the two PCs (the side that got there first skips
numbers), so the counters are cleared at every sync point and at frame 0 on both alike; no rollback crosses a
sync point. The rules themselves come from the fight line both launchers got from the lobby (and a replay
from its file, format 5), latched by the driver at FIGHT START before `t5_netplay_start()`. The handicap
words are in the hashed battle state, health and maximum in the hashed fighter blocks: a PC that applied
other rules would show as a desync at once.

**Older games are kept out** by the build id: `tools/build_game.py` CODE_VERSION 7 changes the code id, so a
1.1.5 game is never paired with an older one (rooms included); the lobby offers training rooms and the
handicap only to launchers whose game has them (cap `match_rules`; the game binary's
`T5_DF_RULES`).

Tests: `tests/test_match_rules.py` (`tests/c/match_rules_test.cpp`: the rule against a model of a fight --
refill, timer, give-up, slot symmetry, and lockstep vs rollback with late inputs, predictions and sync points
vs replay: the same state every frame; plus source checks), `tests/test_replays.py` (format 5),
`lobby/tests/test_training.py`, `tools/fight_flow_test.py --line-extra "train=1 life=70|100"
--give-up-every 2400` (real pairs), e2e `net_training` (a training room through the lobby: rollback with RTT
80 ms, loss and jitter, and lockstep), e2e `spectate_training`.

Tested (2026-10-27, this PC, build/int115/h-runs; both players mashing with a gap of up to 25 frames, a SELECT
hold every 2400 frames): `fight_flow_test` persistent pairs, a new session then rematches, P1 at 70 % --
rollback with the joiner stuttering (20 ms suspends): 4/4 and 4/4 fights (runs ff2, ff4; 260 rollbacks on one
side in ff2), lockstep with P2 at 50 %: 3/3 (ff3) -- every fight ended by the give-up, health refilled in all
of them, 0 mismatching frames, the same result hash on both PCs; the 8 replays the four games recorded (ff4,
ff3) play back identical (every recorded hash and result). Through the lobby (e2e, the launchers' own Online
tab, a local server): `net_training` rollback RTT 80 ms +-10 ms, 2 % loss (279 and 108 rollbacks per fight),
rollback RTT 20, lockstep RTT 20 -- 6 training fights, each `training` in the lobby, the same hash, 0
mismatching frames, the next fight started by itself, Leave room during a fight ended it ("left") on both;
`spectate_training`: a spectator from the start plays both fights identical (82 hashes compared, 0
different).

## Skipping intros and replays online (branch skip-114, 1.1.4)

Owner's request: "replays should be skippable, and the intro at match start" -- the replay after a
round's KO, the fighters' intros before round 1, the way to the next round. **Rule: online a part is
skipped once both players have pressed START in it** (not at the same time: each press counts until
the part ends). Offline nothing changes (any press skips as the game does); a replay file or a
spectator's stream plays the recorded presses through the same rule, so it shows exactly what the
live match did.

**How the game skips (offline).** The round's state machine (`func_00044398`, a switch on the round
state `0x1009322C` read by `func_0004137C`) runs every fight frame. State 1 is the P1 fighter's intro
(171 frames), 2 the P2 fighter's (240): their cases (`0x44B28`, `0x44E18`) skip to the next state
when that fighter's player has a button of mask `0x8F0` newly pressed in the game's per-player button
word (`[TOC-0x7748] + 0 / + 4`; in VS START is one of them, the attack buttons and directions are not:
mashing them never shortened an intro) or the intro animation is done (`func_0001377C`). State 9
(the replay, 524 frames) and 0xC (on to the next round, 149 frames) go on with START too
(`func_000425F0`, `func_00042028`). Measured with the rule's test override (probe2/probe3, rollback
pair, `T5_DF_WATCH`): START cut state 1 to 42 frames, 2 to 32, 0xC to 43, 9 ends 2-3 frames after a
press; it did nothing in READY/FIGHT (4: 169 frames either way) and the KO slow motion (8), and the
pause menu (`0x10092EA0`) never opened. Online none of it was reachable: the rule took START out
everywhere but the replay, and no player's START ever left the PC (`set_no_start`), so the 1.1.2
"either player skips the replay" never happened in a real match.

**The rule** (`no_pause.h`, `t5_hooks.cpp no_pause_rule`): two skip parts, by round state in the
game mode's fight (phase 17, the select screen not asked for, the match not decided in this fight):
the intro (1, 2) and after a round (8, 9, 0xC; the KO slow motion counts presses although START does
nothing there). Per boundary the rule records the part and which players' START it has seen in this
part, frame f's inputs included (bit 0 = P1, bit 1 = P2), and the frame both had. Until both: START
taken out of both inputs, as everywhere. From that frame on the rule presses START for **both**
players itself -- 3 frames, then every 20 frames while the part lasts: one press skips the P1 intro,
the next the P2 intro (each fighter's intro listens to its own player), the replay, the way to the
next round. The players' own START does not reach the game there either. Everything else is the
1.1.2 rule unchanged: the post-match window (the last KO replay and the win pose, skipped by the
driver / the rollback loop's post-match rule without anybody pressing) keeps START as it comes,
the decided match has no skip part, START never reaches the fight. The rule is a function of the
game state at the boundaries and the frames' two inputs, treats P1 and P2 alike and is re-recorded
for re-simulated frames, so both PCs give the game the same inputs (the argument above). Each
player's device START goes out only while this PC's live boundary shows a skip part (`start_gate`,
before the sample: the rollback loop's boundary, lockstep's `begin_frame`): elsewhere it would only
make the peer mispredict. Under rollback a press is predicted like any input (the last input
repeats); the frames between a press and its arrival are re-simulated as usual (these parts are
ordinary fight frames: no loads, compared state hashes). The log says who pressed: `frame N: the
intro (round state 1): START pressed by P1 (skipped once P2 presses it too)` / `... by both players
-- skipped` (live frames; under rollback a predicted press can still be taken back), and the match
tally adds "skipped on N (both players pressed)".

Test hook `T5_TEST_SKIP_PRESS=N[:M]`: this PC's player presses START (3 frames, like a script, not
filtered) N frames into every intro and M frames into every part after a round (-1 = never).
`tests/c/no_pause_test.cpp` (tests/test_no_pause.py) models it: intros, KO slow motion, replay and
the way to the next round with their START reactions; P1 alone, P2 alone and both mashing START
(also as a modified client), lockstep, rollback (inputs 0-9 frames late, ~8,000-9,000 rollbacks per
PC) and replay: identical on both PCs at every frame, never paused, one player never skips a thing,
both skip every intro, replay and way to the next round.

**Proof** (build/skip114/runs; `tools/fight_flow_test.py --flow persistent --pattern NR --matches 2
--rounds 2 --mash --polite`: a new session and a rematch, first to 2 rounds, two games on this PC, both
recording replays; round-state durations from `T5_DF_WATCH=1009322C` in frames, natural lengths: P1
intro 171-200, P2 intro 176-240, replay 524, on to the next round 149):

| run | who presses START | intros (P1 / P2) | replay, next round | result |
|---|---|---|---|---|
| rb_one / ls_one (rollback / lockstep) | P1 only (20 frames into each intro, 150 after each round) | 171, 200 / 240, 176: full | 524, 149: full | same results and final hashes on both PCs (2461a6ef.., ed2d272b.. / 34361a19.., ef73a330..), 0 mismatching frames; P1's START taken out (9-10 frames per match) |
| rb_both / ls_both | P1 as above, P2 50 / 200 frames in | 52-53 / 20 | 85-86, 19 | same results and hashes (83066c2c.., 746ac84b.. / 82330c53.., 752a87e8..), 0 mismatching frames; both PCs' round states identical frame for frame |
| rb_mash / ls_mash | both mash START (`--mash-start 4`: every ~4th input, alone or with an attack) | 34-68 / 20 | 4-20, 19 | same results and hashes, 0 mismatching frames; pause menu opened 0 times; START taken out on ~385 + 382 frames |
| rb_stress / ls_stress | both press as in rb_both and mash START; joiner stalled 60 ms every 0.2-0.6 s (`--stutter 60`), 5 % of packets dropped | 20-53 / 20 | 4-16, 19 | same results and hashes, 0 mismatching frames, pause menu 0; 1,267 rollbacks (rollback) |
| replays | the 16 recordings of these 8 pairs (both sides) played back (`tools/replay_play.py`) | | | 16 of 16 IDENTICAL (2,914 hashes compared, 0 different, every result and sync point equal); the playbacks skip on the recorded frames (60 "pressed by both players" lines, round-state durations as live) |

The post-match part (the last KO replay, the win pose) was skipped by the driver / the rollback rule as
before in every match (2-3 frames of replay). Offline (smoke quick: arcade, VS with two pads,
practice) PASS.

## Connection problems

How a session starts, survives trouble, and ends when it cannot go on
(2026-10-17, after the netplay QA run in build/nq):

| Situation | What happens |
|---|---|
| Handshake | From boot on (network thread): HELLO every 100 ms until the peer answers. No answer within `T5_NET_CONNECT_TIMEOUT` (default max(60, 2 x `T5_NET_TIMEOUT`) s; 0 = wait forever) -> `no_peer` |
| Other build | A peer with another `T5_NET_BUILD`, or another netplay protocol version (older builds), is refused at the first HELLO, and told so (REJECT) -> `build_mismatch` within a second or two of boot, on both sides. A HELLO of another protocol version counts only when it proves it is the opponent's (the match key's tag, or without a key the address the lobby named; since 1.1.2 -- before, one 6-byte packet from anybody who found the port ended the session) |
| Packets | With `T5_NET_KEY` (the lobby's per-match secret, sent only over the lobby's TCP channel) every packet ends in a SipHash-2-4 tag; without it the key comes from `T5_NET_MATCH` + `T5_NET_SEED` when both are set, else packets are unauthenticated (direct-IP play). Packets with a wrong tag, an unknown session or another peer process's nonce are dropped |
| Who is the peer | The first authenticated HELLO (unauthenticated: only from the IP in `T5_NET_PEER` when it is given); after the handshake only that process (session id + nonce + tag) |
| A firewall blocks the game | Windows Firewall (Cancel on its question, a block rule) drops only unsolicited packets: both games send first, the replies get in, the handshake works. A game that hears nothing at all on the direct path (a firewall that drops even replies, a router that forgot the punched mapping): its log says `nothing arrived yet`, and after 15 s the launcher moves the match onto the relay (`nat_fallback`, "When Windows Firewall blocks the game" below) |
| Lobby could not connect the two PCs directly | The relay: the lobby server's own, or for two 1.1.1 launchers whichever relay (the lobby server's or a regional relay-only server) has the smallest sum of both players' round trips (docs/ONLINE.md "Regional relays"); between two 1.1.1 launchers the match moves onto the direct path as soon as it works ("Getting a direct connection" below) |
| NAT rebinding / new relay mapping | The peer's packets arrive from a new address: they still prove who sent them, so the game answers there from then on ("the peer's address changed ... following it") -- but only for a packet that carries something new (a newer PING clock, inputs, hashes or scene changes not seen yet, a newer acknowledgement), or any packet once the known address has been quiet for 1 s. The tag proves who made a packet, not that it is new: before 1.1.2 a recorded packet played back from another address moved the session there ("old packet of the opponent's ... dropped" now). Test: `tests/test_netplay_fuzz.py` (`tests/c/netplay_fuzz.cpp`, which also fuzzes the parser under AddressSanitizer) |
| Short outage / loss / jitter | Lockstep stalls and resumes; resends every 15 ms; nothing is lost while the outage is shorter than `T5_NET_TIMEOUT` |
| Peer silent for `T5_NET_TIMEOUT` | `peer_timeout` (keepalives every 200 ms; a frozen process is silent) |
| Peer alive but no input for `T5_NET_TIMEOUT` mid-match | `peer_stalled` |
| Match start, peer alive but still loading | Waits up to `T5_NET_START_TIMEOUT` (default 120 s), then `start_timeout` |
| This PC's loads are slow (slow disk, busy PC) | The frame waits for them, however long ("Slow loading" below); after 1 s every PING says so (`PING_LOADING`) and the peer's stall limits leave that time out |
| One frame's loads take longer than `T5_NET_LOAD_TIMEOUT` (default 120 s) | This side ends the match: `load_timeout` (BYE with the reason: the peer gets `peer_load_timeout` at once) |
| Peer closed its game | BYE -> `peer_quit` at once |
| This player closes the game window (Alt+F4, the X button, Esc) | The game ends (ps3recomp patch 0035; before it ran on without its window at about one frame a second, still in the session -- the opponent stalled and went out of sync, the match was voided as a desync). With a session set up: the result file gets `"reason": "quit"` (unless this match's result is out: a game closed after the KO keeps its result), BYE, exit code **7**; the launcher reports the match as this player's quit (a loss, docs/RANKED.md), the opponent's game sees `peer_quit`. Esc asks for a second press within 3 s while a session is set up (the window caption says so); Alt+F4 and X close at once |
| Peer's game restarted | A HELLO from a new process of the peer: before any lockstep input was exchanged it simply takes the old one's place; mid-match the session cannot be resumed (the new game knows nothing of it): the old side ends with `peer_restarted`, the new one is refused (REJECT -> `rejected`) instead of hanging in the handshake |

**When a session cannot go on** (`T5_NET_ON_LOST=exit`, the default) the match
ends there, nobody plays on against an idle opponent: the result file gets
`"winner": null` and the reason (unless this match's result was already
written -- an opponent leaving after the match does not undo it), the peer is
told (BYE), and the game closes with exit code **3** (peer lost: `peer_quit`, `load_timeout`, `peer_load_timeout`,
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

## Getting a direct connection (lobby, 1.1.1)

How the lobby connects the two games before a match (lobby/t5lobby/nat.py, client.py, server/lobby.py;
protocol details in docs/ONLINE.md "NAT traversal and the relay"). Branch nat-robust, 2026-10-19.

**The report (1.1.0).** Two players in Southern California, two homes: "a few times it is letting us
have a direct connection and plays decent. Other times it says direct connection not possible and
that is when it is bad". On the relay every packet goes through the only lobby server, in Nuremberg:
300-400 ms round trip instead of ~20.

**Why the same two homes sometimes got through and sometimes not (1.1.0).**

- The punch was a 3-second race that each side started the moment the server's message reached it.
  That message comes over TCP from Germany: the two launchers get it tens of milliseconds apart (a
  segment TCP has to send again: 0.3-1 s). Between two homes ~10 ms apart that decides whose punches
  reach the other router first -- before that router has sent anything toward them. Many routers just
  drop such a packet, and then the order does not matter. Others do not: a Linux router whose WAN side
  takes the packet keeps a connection entry for it (30 s, renewed by every further punch), and its own
  side's punches then have to leave from another port, which a port-restricted NAT on the other side
  drops; others answer with an ICMP error or count the punches as a flood and block the sender. With
  such a router at either end the result depends on which message arrived first and by how much -- in
  the simulator below 84-90 % direct, the rest relay, for the same pair (lower with a slower or lossier
  path to the server, higher when both homes happen to get it within a few milliseconds).
- The first side to give up switched both to the relay at once; the server never waited for the
  other side's report.
- A NAT that gives every destination its own port ("symmetric": many carrier-grade NATs and some ISP
  gateways) next to a port-restricted one never got through (no port prediction), and two symmetric
  NATs went to the relay without trying.
- The game socket's port was never forwarded on the router (UPnP / NAT-PMP was only used for "Host
  for friends").

**What 1.1.1 does.** In the lobby code; the netplay protocol is unchanged. (1.1.1 as a release also
changes the game -- patches 0039 and 0042 -- so its build id differs and 1.1.0 and 1.1.1 players are
not paired; the old/new client mixes below matter for a later launcher-only update.)

- *A plan from the server* (`nat2` cap on both sides): the NAT type comes from what the server itself
  saw (the game socket's endpoint at UDP 7781 and at 7782 -- different ports = symmetric; a small
  step = its ports count up and the next ones can be guessed). Both launchers start at the same server
  time (`start_at`; each one syncs its clock with the server at login, so a message TCP had to resend
  still starts on time).
- *Low-TTL opening*: the first punches go out with TTL 2 and 3 only. They open this side's own NAT (or
  a second NAT right behind it) toward the opponent and die before the opponent's router. Each launcher
  tells the other through the server when it has started (`nat_punching` -> `nat_peer_punching`), and
  the full punches begin only when that word has come (at least 0.15 s, at most 2 s; against a 1.1.0
  client, which cannot say it, 0.5 s from the moment the message arrived). By then both routers have
  sent toward each other: neither sees an unsolicited punch first, so none of the behaviours above can
  start -- even when TCP had to resend one side's message.
- *A 6-second window at a steady rate* (`T5L_PUNCH_TIMEOUT`, was 3): 20 punches a second to every
  candidate, every candidate at once (against a 1.1.0 client 5 a second for the first 0.6 s of full
  punches, for routers that count unsolicited packets).
- *Candidates*: the opponent's public endpoint, its router forward, its LAN addresses (same public
  address only), and for a symmetric NAT whose ports count up the next 24 ports
  (`T5L_PREDICT_PORTS`), walked in the order that NAT hands them out -- so two such NATs can meet too
  (the n-th new port on each side). Every address a punch comes from is punched back.
- *Router forward of the game port* (launcher Settings, "Open the game's port on my router during
  online matches", on by default; PCP, then NAT-PMP, then UPnP; `T5_PORTMAP=0` switches it off): made
  before the socket sends anything, external port = internal port, so the endpoint the server sees is
  the forwarded one and every opponent gets in, whatever its own NAT. 10-minute lease renewed while a
  match runs, closed 2 minutes after the last one; a router that only takes permanent UPnP mappings is
  not used. Not tried when the lobby server is on this PC or the LAN.
- *The server waits for both reports* (or the end of the window). When one side got through and the
  other did not, the failed side punches once more for 2.5 s (it now has the addresses it heard from).
  Only when both fail: the relay.
- *The game socket is the punched one*: on the direct path the launcher hands the punched port to the
  game (`T5_NET_PORT`) right after a last round of punches that refreshes both NATs; the router
  forward, when there is one, stays for the match.
- *Relay bridge, upgrade during the match*: between two 1.1.1 launchers the relayed match keeps the
  punched socket in the launcher (`nat.RelayBridge`). The game talks to 127.0.0.1 (`T5_NET_PEER`) and
  sees one address the whole time; the launcher carries its packets to the relay and tries the direct
  path in 3-second bursts every 40 s (low TTL first, both launchers at the same server time: the match
  start + 35 s). The silence in between matters: a router's leftover entry or flood block lasts 30 s
  from the last packet. When a burst gets punches back both ways the launcher sends the game's packets
  straight to the opponent; the opponent's launcher does the same on its own; packets from either path
  are taken all the time, so the switch costs the game nothing. If the direct path goes quiet for 2.5 s
  it goes back to the relay (kept alive by a ping every 5 s). The netplay itself would follow a new
  address (see "Connection problems"), but it never sends to one first -- without the bridge only a
  game change (a new build id) could start an upgrade. Players see "Direct connection found: the match
  no longer goes through the lobby server."; the server logs it and counts `relay_upgrades`.

**Measured with the NAT simulator** (`lobby/tools/natsim.py`): the real lobby server (relay and probe
port included) and real LobbyClients on this PC, each client behind a simulated home router -- its game
socket's packets go through a NAT object that maps them to a public endpoint (a real UDP socket on a
loopback address of its own), filters what comes back by the NAT type, delays and drops. Home to server
75-95 ms one way (the Nuremberg server from California), home to home 8-14 ms, 2 % UDP loss on every
leg; the control channel through a TCP proxy with the same delay, 3 % of the messages resent after
0.25-1 s. After `match_start` a stub game takes the port over (or the bridge's local port) and must get
packets through in both directions -- the "game ok" column. NAT types: full cone, restricted cone,
port-restricted cone, symmetric (sequential ports, other devices taking a port now and then), and three
extra rows: symmetric with random ports (carrier-grade NAT), port-restricted with a flood guard (>20
unsolicited packets in 2 s block the sender for 30 s) and port-restricted on a Linux router that keeps
an entry for an early punch ("poison"). 50 trials per pair; before = the 1.1.0 lobby (server and both
clients, main 1c4cd05), after = this branch.

| pair | before: direct | after: direct | after: game link ok | setup to match_start, direct (s) before / after |
|---|---|---|---|---|
| full + full | 100 % | 100 % | 50/50 | 1.8 / 2.3 |
| full + restricted | 100 % | 100 % | 50/50 | 1.8 / 2.2 |
| full + port | 100 % | 100 % | 50/50 | 1.7 / 2.2 |
| full + symmetric | 100 % | 100 % | 50/50 | 1.7 / 2.3 |
| full + symrand | 100 % | 100 % | 50/50 | 1.9 / 2.1 |
| full + port-guard | 98 % | 100 % | 50/50 | 1.7 / 2.3 |
| full + port-poison | 100 % | 100 % | 50/50 | 1.9 / 2.1 |
| restricted + restricted | 100 % | 100 % | 50/50 | 1.8 / 2.1 |
| restricted + port | 100 % | 100 % | 50/50 | 1.7 / 2.2 |
| restricted + symmetric | 100 % | 100 % | 50/50 | 1.7 / 2.3 |
| restricted + symrand | 100 % | 100 % | 50/50 | 1.8 / 2.3 |
| restricted + port-guard | 96 % | 100 % | 50/50 | 1.6 / 2.1 |
| restricted + port-poison | 100 % | 100 % | 50/50 | 1.8 / 2.1 |
| port + port | 100 % | 100 % | 50/50 | 1.5 / 2.0 |
| port + symmetric | 0 % | 100 % | 50/50 | - / 2.2 |
| port + symrand | 0 % | 0 % | 50/50 | - / - |
| port + port-guard | 100 % | 100 % | 50/50 | 1.6 / 2.1 |
| port + port-poison | 84 % | 100 % | 50/50 | 1.6 / 2.1 |
| symmetric + symmetric | 0 % | 60 % | 50/50 | - / 2.1 |
| symmetric + symrand | 0 % | 0 % | 50/50 | - / - |
| symmetric + port-guard | 0 % | 100 % | 50/50 | - / 2.2 |
| symmetric + port-poison | 0 % | 100 % | 50/50 | - / 2.4 |
| symrand + symrand | 0 % | 0 % | 50/50 | - / - |
| symrand + port-guard | 0 % | 0 % | 50/50 | - / - |
| symrand + port-poison | 0 % | 0 % | 50/50 | - / - |
| port-guard + port-guard | 98 % | 100 % | 50/50 | 1.9 / 2.5 |
| port-guard + port-poison | 90 % | 100 % | 50/50 | 1.6 / 2.4 |
| port-poison + port-poison | 86 % | 100 % | 50/50 | 1.6 / 2.2 |

All pairs together: 926 of 1,400 trials direct before, 1,130 after. The price: a direct connection
is ready ~0.5 s later (the opening and the common start), and a pair that cannot connect directly
reaches the relay after ~8.7 s instead of ~5.5 s (the longer window). Every remaining relay row is a
symmetric NAT with random ports next to a NAT that filters by port or maps per destination too --
no amount of punching opens that; a router forward on either side does (next table).

With a router that forwards the game port at home A (PCP / NAT-PMP / UPnP answered by the simulated
router; 1.1.0 never asks):

| pair (A has the forward) | before: direct | after: direct |
|---|---|---|
| symrand + port | 0 % | 100 % |
| symrand + symrand | 0 % | 100 % |
| symrand + symmetric | 0 % | 100 % |
| symmetric + symmetric | 0 % | 98 % (1 trial: the simulator's own login timed out) |
| port + symmetric | 0 % | 100 % |

The relay bridge: with the control channel losing half of its messages (TCP resends, `--tcp-rto 0.5`)
and before the opening waited for the opponent's start, 8 of 20 poison pairs went to the relay and 7 of
those moved onto the direct path at the first burst, 35 s into the match, while the stub games kept
exchanging packets (the eighth was still on the relay when the 45 s ended). With the final code the
same setting gives 20 of 20 direct at once, so the bridge is left for what the punch cannot know
about; `tests/test_nat2.py` (RelayUpgradeTest) opens the direct path in the middle of a relayed match
and checks that both sides switch and the games' packets keep flowing. A real game pair (two t5dr.exe,
`lobby/tools/two_players.py --exe ... --relay`) played 3,600 lockstep frames in sync at 60 fps through
two bridges and the relay; stub games through the same path finished a match with a confirmed result.

Compatibility (same simulator, 20 trials per pair; pairs full + full, port + port, port + symmetric
both ways, symmetric + symmetric, poison + poison): every mix of a 1.1.0 or 1.1.1 server with 1.1.0
and 1.1.1 clients connected in every trial (direct or relay) and the game link worked in every trial
(one trial lost to the simulator's own login timeout). An older client keeps its old behaviour (punch
on receipt, 30 ms, the server's window); a 1.1.1 server gives it the longer window, the predicted ports (8, ahead of the public
endpoint) and the second chance, so 1.1.0 clients behind a symmetric NAT next to a port-restricted one
get through as well; a 1.1.1 client paired with a 1.1.0 one starts on receipt like it, with the low-TTL
opening; a 1.1.1 client with a 1.1.0 server behaves like 1.1.0 except that it still forwards its port
when allowed. `tests/test_nat2.py` runs the clients and server of the newest release tag in git
(v1.0.0) against this tree in the simulator (skipped in a checkout without tags).

**Limits.**
- The simulator models routers; real routers were not available here (and this PC's router is never
  asked for a forward by any test: fakes only). The TTL opening assumes this PC's NAT is at most two
  hops away; a NAT further away just misses the opening (as 1.1.0).
- Two symmetric NATs with random ports and no router forward on either side stay on the relay. Two
  symmetric NATs whose ports count up meet only when neither handed out a port to another device
  between the probe and the punch.
- The relay bridge needs the launcher running for the whole match, and upgrades only between two 1.1.1
  launchers on a 1.1.1 server. The direct path is found only at the bursts (35 s after the start, then
  every 40 s).
- The prediction needs the server's second UDP port (7782) open; the lobby server has to run this
  branch for everything but the router forward.


**Regional relays (branch regional-relays, 1.1.1).** What the punch cannot open still goes through a
relay, and with one lobby server in Nuremberg that relay was always in Germany. The central server can
now list relay-only servers in other regions (docs/HOSTING.md "Adding a relay server"); 1.1.1 launchers
measure their round trip to each, and a match that needs a relay takes the one with the smallest sum of
both players' round trips (two players in California: a node in Oregon, ~30-80 ms instead of 300-400).
Lobby, accounts and ranking stay on the one server. The relay bridge works the same way through a
regional relay: the match moves onto the direct path when a burst gets through
(`lobby/tests/test_relays.py` UpgradeFromRegionalTest). Older launchers keep the central relay. Two
real games through a regional relay on this PC (`lobby/tools/relay_e2e.py --exe`, simulated round trips,
the path ~130 ms): 4,270 frames of rollback through both relay bridges, 0 mismatching, result confirmed.

## When Windows Firewall blocks the game (1.1.3)

Branch firewall-fallback, 2026-10-20. Until 1.1.2 the docs said: "We did not test a match with the firewall left
blocking." This section is that test, and what it changed.

**What Windows does.** When someone clicks Cancel on Windows' question ("allow public and private networks to access
this app?"), or never answers it, or a rule blocks `t5dr.exe`, Windows Firewall drops every *unsolicited* inbound
packet for that program. It still lets in the replies to the program's own packets: the firewall is stateful, and a
UDP datagram from an address:port the socket has sent to belongs to that flow. Both games send first (HELLO every
100 ms to `T5_NET_PEER`, from boot), and so do both launchers in the punch (low-TTL opening, then full punches), so
in most cases the two sides still meet. What a blocked side loses: a path that needs the other side's packet to
arrive first -- a punch from a port this side never sent to (a NAT with random ports on the other side), the
netplay following the opponent to a new address (NAT rebinding mid-match), a router forward of the game port (the
forward opens the router, not the PC).

**The test switch** (the real firewall is never touched; `netsh` is never asked to change anything):

- Game: `T5_NET_TEST_INBOUND=stateful|block` (`src/netplay/netplay_core.cpp`, `test_inbound_pass`), on the session's
  socket. `stateful`: a datagram from an address:port this socket has not sent to is dropped before the netplay sees
  it -- Windows for a blocked program. `block`: everything not from 127.0.0.1 is dropped, replies too -- stricter than
  Windows Firewall (some third-party firewalls and antivirus "network shields"); the launcher's relay bridge on
  127.0.0.1 still gets through. The log says `TEST: inbound firewall emulated (...)`, the first drops per address, and
  the count at the session's end.
- Launcher: the same two modes on the lobby client's UDP sockets (`LobbyClient(test_inbound=...)`, default
  `T5_NET_TEST_INBOUND` from the environment; `nat.InboundFilter`): registration, punch, relay, the relay bridge's
  socket to the network, the RTT pings.
- Stub game (`lobby/tools/stub_game.py`), the NAT simulator (`natsim.py --fw-a/--fw-b stateful|block[:game|launcher]`:
  a firewall on home A's / B's PC for both programs or one) and the e2e runner (`Player.set_firewall(game, launcher)`;
  for `block` the shaper's proxy sits on 127.0.0.2, so the opponent is "not this PC" while the games bind 127.0.0.1).

**Measured, NAT simulator** (lobby code of this branch, real lobby server with relay, stub games; the seven NAT types
of "Getting a direct connection"; one-sided runs over all 49 ordered pairs so the firewall sits on each type once,
two-sided over the 28 pairs; "game link ok" = both stub games got their packets through on the path the lobby chose):

| firewall | matches | direct | relay | relay after the game heard nothing | no connection | game link ok |
|---|---|---|---|---|---|---|
| none (reference; 28 pairs x 20) | 560 | 447 | 113 | - | 0 | 560 |
| A stateful, game and launcher (49 ordered pairs x 20) | 980 | 749 | 231 | 0 | 0 | 980 |
| A stateful, game only (49 x 10) | 490 | 396 | 94 | 0 | 0 | 489 (1) |
| A and B stateful, game and launcher (28 x 20) | 560 | 410 | 148 | 2 | 0 | 560 |
| A block, game only -- 1.1.2 behaviour, no fallback (49 x 10) | 489 | 392 | 97 | - | 0 | **97** |
| A block, game only (49 x 10) | 490 | 0 | 95 | 395 | 0 | 490 |
| A and B block, games only (28 x 10) | 280 | 0 | 54 | 226 | 0 | 280 |
| A block, game and launcher (3 pairs x 5) | 9 | 0 | 0 | - | 9 (2) | 0 |

(1) one relayed trial whose stub games got too few packets through in their 2 s on the loaded PC (not a drop: the
emulated firewall dropped nothing in it). (2) Nothing reaches the launcher either: the lobby server's UDP answers never
arrive, the match is cancelled; the Online tab shows its hint. The rows "none", "A stateful" and "1.1.2 behaviour" ran
with the branch's first state (switch, no fallback, relay setup 6 s), the others with the final code; the simulator's
own login timeouts under load (a few per run) are left out. Raw results: build/fwhint/natsim/r1, r2 (not committed).

- **Stateful (what Windows does), one side or both: every match connected**, directly or through the relay. Two
  pairs lose their direct path when the firewall sits on the cone side: full + symmetric-random and restricted +
  symmetric-random (100 % direct without a firewall, relay with it: the random-port side's punches come from a port
  the blocked side never sent to). Every other pair has the same direct share with and without the firewall.
- **Found on the way: two symmetric NATs with both firewalls blocking.** The punch can open several pairs of
  mappings at once (each side walks the other's predicted ports); each launcher hands its game the pair it confirmed
  first, and the two may differ. Without a firewall the netplay follows the opponent to the other address and nobody
  notices; with both firewalls blocking, each game drops the other's packets (they come from an address it never
  sent to) and hears nothing: in the loaded first run 4 of 7 such direct matches had no game link. The fallback below
  moves them onto the relay.
- **Block (stricter than Windows) on the game: before this branch every direct match failed** (392 of 392 in the
  one-sided run; the lobby saw a working path -- the launchers' sockets -- and the game gave up after 60 s with "Your
  opponent's game could not be reached"); relayed matches worked (the bridge talks to the game on 127.0.0.1). With the
  fallback, all connect.
- Both programs blocked completely: UDP never reaches the lobby server, the match is cancelled with
  `udp_unreachable` (no relay can help: the launcher cannot send anything either) -- the Online tab shows its hint.
- Router forward (`--map-a`) and a blocked firewall on the same side: the forward no longer brings
  symmetric-random pairs onto the direct path (relay instead); the others stay direct.
- The few "no connection" trials in the loaded runs (other agents' games and builds on the PC, 12 trials in parallel)
  had setups of 13-25 s: the relay setup ran out of time (`T5L_RELAY_TIMEOUT` 6 s against a client's own bind up to
  4 s + measure up to 4.25 s). The server now gives it 10 s; reruns of those pairs: 0 failures.

**Measured, real games** (`tools/e2e/run.py --only net_firewall`, two `t5dr.exe` of this branch through the local lobby,
persistent games, rollback, one round; the cases also run with stub games: `firewall_stub`):

| case | firewall A (game, launcher) | firewall B | the punch | lobby's path | played on | result | mismatching frames | same hash |
|---|---|---|---|---|---|---|---|---|
| one side blocked | stateful, stateful | -, - | ok | direct | direct | confirmed | 0 / 0 | yes |
| both sides blocked | stateful, stateful | stateful, stateful | ok | direct | direct | confirmed | 0 / 0 | yes |
| both blocked, no direct path (symmetric NATs) | stateful, stateful | stateful, stateful | fails | relay | relay | confirmed | 0 / 0 | yes |
| one game blocked completely, no direct path | block, - | -, - | fails | relay | relay (bridge) | confirmed | 0 / 0 | yes |
| one game blocked completely, direct path found | block, - | -, - | ok | direct | relay after the fallback | confirmed | 0 / 0 | yes |

Every case connected; none ended with "could not be reached". The fallback case: the game logged 15 s of "nothing
arrived yet", the launcher asked for the relay, both persistent games started session 6 of the same match through
the bridges (`connected (join, P2) ... peer 127.0.0.1:...`), the fight began about 25 s later than on a working path
(queue to result 68-80 s against 52-57 s). In the game logs of the stateful cases the host drops the joiner's first
HELLO ("this socket never sent there") and connects 0.1 s later, when its own HELLO has gone out -- the effect the
switch emulates. Runs: the first build of the branch (all five, 128 checks), the final build after merging main's
`T5_NET_BIND` (cases 1, 3, 4, 5 in run game2; cases 1 and 2 again in game3 -- in game2 the "both sides blocked" match was
voided as a desync: the two games left the fight intro on different frames (frame 231: one hashed the intro value,
the other a fight state) and stayed apart; the emulated firewall had dropped nothing in that match, it is not a
network effect -- reported separately), the stub games (`firewall_stub`, five of five), and with
`T5_NET_TEST_INBOUND=stateful` for every launcher and stub game the existing `relay_regional_stub` (regional relay nodes
from relays.json, the closest by RTT sum, then the next when one dies), `relay_e2e_tool` and `relay_upgrade_stub`
(relay -> direct through the bridges): all PASS. The e2e quick suite (27 scenarios) passes on the final code.

**The fallback: a game that hears nothing gets the relay** (cap `game_fallback` on both clients and the server;
`T5L_GAME_FALLBACK`, default 90 s). While the handshake waits, the game's log says every 5 s whether anything at all
has arrived on its port (`waiting for the opponent's game to answer (15s, nothing arrived yet)`). The match driver
(`match_driver._watch_direct`) watches it on a direct or LAN path: 15 s of nothing means the launchers reached each
other but something drops what comes for the game. It shows the firewall hint and sends `nat_fallback`; the server
(`h_nat_fallback`: once per match, before any result, within the window, and not once either launcher has said its
game played the fight for a while -- `game_started {playing}`, sent at the game's first netplay speed or sync line after
FIGHT START, 600 lockstep frames that only run with the opponent's inputs; before 1.1.3's security review a player
losing round 1 could ask for the relay and both games began the match again) moves the running match onto the relay --
`nat_relay` with `fallback: true`, both launchers bind a new socket with the match's token (the game holds the old
port), keep it as the relay bridge, and get a second `match_start` for the same match. Both drivers start the
match's game session again (persistent game: a new session; a game that does not take the command within 10 s is
restarted in process mode), each with a result file of its own (whatever the first session writes later is not this
match's result). The games then talk only to 127.0.0.1; the bridge still tries the direct path at +35 s, through the
launcher. In the e2e run the fight began ~25 s later than on a working path. Older clients never get a second
`match_start`; a 1.1.3 client against an older server does not ask.

**With the other 1.1.3 features.** Custom costumes: the new session exchanges both costume tables again (COSTUME
packets, at most 1,064 bytes with the tag, through the relay's 2,048-byte limit; the first session's tables are
gone with it), so the fight after the move has both customizations. Tournament sets: the same game of the set,
played again on the relay (the set's game count is not raised; `_start_match`'s `again`). Spectators: the same
stream id, so the same live file -- a session that never shook hands leaves nothing but the magic in it, the new
one goes on from there, and the server keeps the stream while the match is on its way to the relay
(docs/SPECTATE.md "When the match moves onto the relay"). e2e `int_fw_costumes`: one game blocked completely,
costumes on both sides, a spectator watching from the start.

**The hint** (`lobby/t5lobby/fwcheck.py`, `tk_tab.fw_hint_text`): the Online tab reads Windows Firewall's rules for the
exact `t5dr.exe` the launcher starts (`core.game_exe` = `run_game.game_command`) and for its own process
(`GetModuleFileNameW`: `pythonw.exe`, or `T5DR Online.exe` with the in-process stub), when the tab is shown and after
each match (at most every 30 s), on a worker thread. Source: the firewall's own store in the registry
(`HKLM\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy`: `FirewallRules`, each profile's
`EnableFirewall` / `DoNotAllowExceptions` / `DisableNotifications`; Group Policy's
`HKLM\SOFTWARE\Policies\Microsoft\WindowsFirewall` on top), readable by every user: 0.2 s for 1,856 rules here.
`netsh advfirewall firewall show rule name=all verbose` was the first idea; on this PC it ran for more than two
minutes, printed 1.9 MB and labels every field in the Windows language ("Aktion: Blockieren"). `netsh` is used only
for the current network's profile: the heading of `show currentprofile` compared with the headings of `show
privateprofile` / `publicprofile` / `domainprofile`, so the language does not matter (about a second; without it every
profile with the firewall on counts). A program counts as blocked by an enabled inbound Block rule for its path (UDP
or any protocol; a block wins over an allow, as in Windows), "Block all incoming connections", or no allow rule while
Windows' notifications are off. The hint also comes up when a match showed it: the lobby server never answered this PC's UDP
(`udp_unreachable` blamed on this PC, or the launcher's registration got no answer: `nat_status` with `udp_blocked`),
or the game heard nothing (the fallback above, or a `no_peer` whose log line says `nothing arrived`). One line: "Windows
Firewall blocks t5dr.exe on this network. Matches still connect, but some only through a relay, with more lag." /
"A firewall seems to block T5DR Online's network traffic on this PC." with **How to fix** (TROUBLESHOOTING.md "The
firewall blocks the game" in the public repository) and Dismiss. Nothing is changed, no administrator rights are
asked for; "Report a problem" includes the check's result. `T5_FW_CHECK=0` switches the check off (the tests).

**Limits.** The firewall's behaviour is emulated, not Windows' own (this PC's firewall is off and stays untouched);
the emulation follows the documented stateful model per remote address and port. Third-party firewalls keep their
own rules: the hint sees them only through what a match shows. A NAT rebinding mid-match behind a blocked firewall is
not followed (the new address never sent to). Spectating or anything else that would have another PC send to a game
first needs the relay with a blocked firewall. Two symmetric NATs with both firewalls blocking can still lose 15 s to
the fallback (a consistent choice of the punched pair would avoid it: the other side would have to say in its
F_HEARD where it saw this side -- a punch format change).

**Rematches after the relay (1.1.5, lobby server only).** A rematch used to continue in the running games on the
path they had, so once a session was on the relay every rematch stayed there. Production, 2026-10-21 (1.1.4): one
player's firewall blocked his game, the fallback moved the match onto the relay (127 ms instead of 94 ms direct), and
each following ~3-minute rematch waited 4.5-8.5 s for inputs (freezes) -- the firewall was fixed on his PC meanwhile,
and a new match from the lobby went direct again. Now a rematch (or the next game of a ranked set) after a match on
the relay is a new connection: both launchers send their games back to idle and the lobby runs registration and the
punch as for a new match (`match_found` with `keep: false`, the old relay session is closed). Direct works: the
session continues direct. It fails again (punch, or the game hears nothing and the fallback runs once more): the
session stays on the relay for its following rematches (`Match.direct_again`), so a pair without a direct path pays
the extra setup (punch window, or the fallback's 15 s) once. Not tried again: `T5L_FORCE_RELAY`, two symmetric NATs
without predictable ports (nothing would change), both relay bridges already on the direct path. `T5L_REMATCH_DIRECT=0`
turns it off. 1.1.4 launchers need nothing new (a rematch with `keep: false` is what they did when one game had
closed). Tests: lobby/tests/test_firewall.py `RematchAfterRelay*`; e2e `net_relay_rematch` (real games, 1.1.4 build
with this lobby: fallback onto the relay, firewall fixed, the rematch plays direct in a new session, the next one
continues in it; punch blocked, the rematch tries once more and stays on the relay, the next one continues there: 6 of 6
confirmed, same hashes, 0 mismatching frames) and `relay_rematch_stub`.

## Relayed matches (branch relay-smooth, 1.1.4)

The request: "make rollback over the relay smoother". What a relayed match does differently from a direct one,
measured, and the one cause that was real.

**Measured: relayed against direct at the same network.** e2e scenario `net_relay_smooth` (docs/SMOKE.md): the
direct path through the shaper's proxy; the relayed path through a relay node (`run.py relay`) with each player's
leg shaped (half the round trip and half the jitter each, the loss that compounds to the total), the launchers'
relay bridges in between as on players' PCs; per case direct, relay with 1.1.3's bridge (`relay-old`) and relay
with the pump (below), interleaved in one run, one match of one round each, the same game build. Rollback
(rollbacks/s, mean and p95 depth: both games; stall ms outside the lockstep windows; time-sync sleeps; fps
host/joiner):

| RTT / jitter / loss | direct | relay, 1.1.3 bridge | relay, pump |
|---|---|---|---|
| 60 / 0 / 0 % | 3.98/s, 1.09, p95 2; 2 ms; 8; 58.3/58.3 | 3.42/s, 1.02, p95 1; 11 ms; 10; 58.7/59.0 | 2.90/s, 1.04, p95 1; 10 ms; 24; 58.9/58.8 |
| 60 / +-8 / 2 % | 7.78/s, 1.35, p95 2; 26 ms; 2; 59.3/59.3 (delay 1) | 3.13/s, 1.00, p95 1; 14 ms; 1; 59.3/59.3 | 2.63/s, 1.02, p95 1; 3 ms; 2; 59.0/59.0 |
| 120 / 0 / 0 % | 6.49/s, 2.01, p95 3; 52 ms; 25; 53.9/54.2 | 7.69/s, 2.02, p95 3; 54 ms; 15; 56.9/57.0 | 6.31/s, 2.06, p95 3; 16 ms; 30; 53.8/53.6 |
| 120 / +-8 / 2 % | 5.05/s, 1.82, p95 3; 48 ms; 50; 47.6/47.6 | 7.94/s, 2.06, p95 3; 47 ms; 7; 55.8/55.6 | 6.61/s, 2.01, p95 3; 56 ms; 10; 55.2/55.2 |
| 200 / 0 / 0 % | 6.61/s, 3.73, p95 5; 134 ms; 25; 50.1/50.3 | 8.09/s, 4.33, p95 6; 136 ms; 46; 57.0/57.1 | 7.66/s, 4.35, p95 6; 135 ms; 19; 55.9/55.9 |
| 200 / +-8 / 2 % | 7.62/s, 4.52, p95 6; 142 ms; 23; 58.2/58.0 | 6.84/s, 4.20, p95 6; 138 ms; 27; 55.0/55.1 | 7.00/s, 4.23, p95 6; 134 ms; 28; 54.4/54.4 |

The fps column moves with the other games on this PC (47-59 on any path), not with the path. Lockstep (`--netcode
lockstep`, the lobby's delay; time the frames waited for the peer, host/joiner; fps):

| RTT / jitter / loss | direct | relay, 1.1.3 bridge | relay, pump |
|---|---|---|---|
| 60 / +-8 / 2 % | delay 4; 1.0 / 2.2 %; 58.7/57.7 | delay 4; 0.0 / 4.5 %; 59.0/58.1 | delay 4; 0.0 / 2.3 %; 59.2/58.0 |
| 120 / +-8 / 2 % | delay 6; 0.2 / 2.4 %; 59.0/58.3 | delay 6; 0.5 / 2.2 %; 59.0/58.0 | delay 6; 0.5 / 2.8 %; 58.3/56.8 |
| 200 / +-8 / 2 % | delay 8; 0.2 / 3.4 %; 58.7/57.9 | delay 8; 0.0 / 1.0 %; 58.8/58.4 | delay 8; 0.0 / 1.6 %; 58.3/57.9 |

So at the same network a relayed match is as smooth as a direct one, and these were ruled out with numbers:
*the delay* -- the games measure the round trip themselves through whatever path they have (section "Input
delay"; relayed 120 ms: the game's 122 ms, the lobby's relay measurement 122.6 ms, direct 121 ms; the lockstep delay
from the lobby's measurement through the relay, 4/6/8, the same as direct); *lost packets* -- every INPUT carries
all inputs the peer has not acknowledged (at least the last 8 frames) and the ack: a lost packet costs the next
packet's 16.7 ms, no rollback of its own (2 % loss changes nothing above); *time sync* -- sleeps per minute the
same on both paths (17/min each in the first trial at 120/8/2); *the relay's choice* -- the smallest sum of both
players' round trips since 1.1.1 (`relay_regional` PASS); *the relay node* -- forwards each datagram in its
receive callback, no batching. The one threshold effect: the auto rollback delay switches from 1 to 2 frames at
60 ms, and a relay's few extra milliseconds can cross it (60/8/2 above: direct 59 ms -> 1 frame, relayed 62 ms ->
2 frames: fewer rollbacks, one frame more input lag).

**What was real: the launcher's hop.** On a relayed match between 1.1.1+ launchers every game packet passes
through the launcher's relay bridge on both PCs (so the match can move onto a direct path while it runs:
docs/ONLINE.md). The bridge forwarded on the lobby client's event loop -- one packet per loop pass, behind the
lobby's messages and timers -- on a thread of normal priority, while the game's own threads run at
THREAD_PRIORITY_HIGHEST (ps3recomp 0065; the game's network thread too, for this very reason: section "Thread
placement" in docs/RENDER_PERF.md). On a PC whose processors the game keeps busy, Windows let that thread wait a
time slice now and then. `lobby/tools/bridge_latency.py`: a stand-in game (its own process) sends 60 packets/s
through a real RelayBridge to a stand-in relay that echoes them -- two bridge passes per sample, as on a relayed
match; `--hog 4 --cpus 2`: the launcher on two processors kept busy by four threads at the game's priority (14 of
every 16.7 ms):

| extra round trip (ms) | p50 | p95 | p99 | max | > 5 ms |
|---|---|---|---|---|---|
| 1.1.3 bridge (event loop), run 1 / 2 | 5.66 / 5.86 | 13.31 / 13.12 | 14.12 / 14.02 | 23.49 / 26.47 | 499 / 502 of 900 |
| pump, run 1 / 2 | 0.12 / 0.19 | 0.21 / 0.29 | 0.26 / 0.38 | 0.47 / 1.86 | 0 / 0 of 900 |
| + a launcher thread busy in Python half the time (`--hog 2 --cpus 2 --py-load`): 1.1.3 / pump | 6.06 / 0.31 | 16.95 / 9.47 | 28.79 / 12.25 | 47.72 / 23.17 | 410 / 80 of 720 |
| a free processor left (`--hog 3 --cpus 4`): 1.1.3 / pump | 0.20 / 0.20 | 0.28 / 0.27 | 0.33 / 0.32 | 0.88 / 0.38 | 0 / 0 |

Late, bunched packets are what a rollback loop feels most: the peer's inputs arrive later (deeper rollbacks), in
bursts (the frame-advantage estimate jumps: time-sync sleeps), and in lockstep a frame waits. That is why the
relayed matches of busy PCs (4 cores, a browser, streaming) were worse than their round trip says.

**The fix (launcher only, `nat.RelayBridge` "The pump").** A thread of the bridge's own waits on both of its
sockets (the event loop's reading of them paused) and forwards every game packet the moment it arrives, at
THREAD_PRIORITY_HIGHEST like the game's network thread; whatever else arrives on the game socket (punches, the
lobby's peer pings, the relay's answers) is handed to the event loop as before, so the direct-path upgrade, the
keepalive and the measurements work unchanged. While a bridge pumps, the interpreter switches threads every 1 ms
instead of 5 (`sys.setswitchinterval`; put back with the last bridge), so another launcher thread busy in Python
holds a packet 1 ms, not 5. A low-TTL punch (the bridge's burst toward the direct path) sets the socket's TTL around
its send; the pump takes the same lock (`GameSocket.ttl_lock`) so no game packet leaves with that TTL.
`T5_RELAY_PUMP=0` is 1.1.3's way. Nothing on the wire changed: the relay server, the game and the netplay
protocol see the same packets; a 1.1.3 lobby/relay server needs nothing.
(`ctypes.windll.kernel32.SetThreadPriority(GetCurrentThread(), ...)` fails in Python -- the pseudo-handle comes
back as a 32-bit int, "invalid handle" -- so the pump types the handle; the e2e harness's own `_raise_this_thread`
has always failed that way, which keeps the runner's launcher threads two levels below the games' threads, the
same gap as on a player's PC.)

**Proof.** Sync: every match of the grids above (18 rollback, 9 lockstep, 6 more with launchers and games pinned
to 6 processors) and of `net_relay_upgrade`, `net_firewall` (the relay fallback), `net_mixed_fallback`,
`relay_regional` (all PASS, the pump on): 0 mismatching frames, the same result hash on both PCs; their 18
recorded sessions played back identical (`--replays`). With processors to spare the e2e numbers do not move
(the tables above, and pinned to 6 processors at 120 and 200 ms: relay 1.1.3 / pump 7.53 / 8.07 and 8.36 / 7.83
rollbacks/s, fps 59 everywhere -- two games and the runner did not saturate 6 processors); the gain is where the
processors are busy (the bridge table). Direct matches do not use the bridge. lobby/tests/test_nat2.py
`RelayBridgeTest`: the pump forwards both ways and is raised, lobby packets still reach the event loop (a peer
ping through the relay), the switch interval comes back, the TTL lock, `T5_RELAY_PUMP=0`; the whole lobby suite
(30 modules) passes.

**The rig itself** (tools/e2e): `net_rollback`'s "relay path" case had never shaped the relayed path (RTT 0,
unshaped), and the shaper's proxies waited in `select()` timeouts that Windows rounds to its 15.6 ms tick in a
process without `timeBeginPeriod(1)` -- up to 15 ms of jitter of the emulated network's own per hop, two hops on
a relayed path. The runner now asks for 1 ms and raises the proxy threads for real.

**Not done (choices for the owner).** At 200 ms the rollbacks are 4-5 frames deep on average (p95 6) on either
path with the auto delay of 2 frames; an auto delay of 3 above ~150 ms (as some games do) would take a frame off
every rollback for a frame more of input lag -- a feel decision, not a relay one. The lobby server's own relay
forwards in the server's event loop, behind the lobby's work (regional relay nodes do nothing else); moving it to a
thread like the pump would need a server deploy and was not measured as a problem.

## What had to be made deterministic

Found by running two instances with identical scripted input, comparing the
per-frame hashes, per-region hashes and memory dumps (`T5_NET_DUMP`,
`T5_NET_PAGEHASH`, `T5_NET_DESYNC_DUMP`, `tools/netplay_memdiff.py`):

| Source | Effect | Fix |
|---|---|---|
| Pad sampling on the vblank thread | input landed in different frames | keyread tick run by the main thread, once per frame |
| Mersenne Twister seeded from the clock at boot (0xAE6C8: `sys_time_get_current_time` -> init_by_array, state 0x10095168) | different random streams | reseeded with the shared seed at frame 0 and at every scene change |
| C library `rand()` (0x369228, state 0x1074F218; 91 callers) consumed at load-dependent times | **different random stage** on the two PCs, fights then diverged | reseeded with the MT at the same points; state hashed |
| Async loading (ZsAread thread, sem 8, feeding the file manager; "decoder", sem 10) | scene changes 1-20 frames apart (logo, char select, fight loading) | main thread waits at frame start until those loaders are parked with nothing queued (usually 0 ms; a few hundred ms on loading screens) -- however long that takes (until 1.1.2 at most 2 s: see "Slow loading") |
| Anything left that moves a scene change | frame offset | scene change = sync point: both continue from the later frame, game frame clock (0x106D4D88) moved along on the other side, RNGs reseeded |
| Wall-clock vblank counters (0x106D4D90, the vblank list object +0xC0/+0xC8), key-repeat timestamps | none seen in game logic | not synced; frame clock 0x106D4D88 (used by key repeat) is per main-loop frame and is |
| The player's own save: unlocks (Jinpachi's and the random cell in the select grid, the Tekken 5 stages in the stage lists and random pickers) | a lockstep rematch put the same presses on another costume on the two PCs (run ctrl_ls: Devil Jin 0x43 vs 0x45, 1,327 mismatching frames) | an online game answers the game's unlock check 0x2A732C as a fresh save does (1.1.2; DIRECTFIGHT.md "Unlocks") |
| The player's own save: the game's OPTIONS (Difficulty, Round Time, +7) copied into the battle state 0x1008F094/9C/98, Difficulty again by 0x1CC28 | every compared frame mismatching (run c2), a different round timer | an online game keeps a save of its own (patch 0044 `PS3_SAVEDATA_DIR`, the launcher's `gamedata-online`): both PCs start from the same fresh save (1.1.2) |

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
0x1008EBD0 (+0x5 non-zero once the match is decided), round timer 0x1008F054
(frames left), the fighters at roughly 0x1008F800 and 0x100900D0 (0x8D0 apart;
each one's rounds won at +0xA1 of its block, "Match result" above), plus 0x10099600-0x10099BFF,
0x100A0900-0x100A0AFF and 0x100A3B00-0x100A3DFF. About 25 KB per frame.

## One save for online play, and the unlocks (branch unlock-stages, 1.1.2)

Everything two netplay games must agree on has to be the same at FIGHT START
on both PCs. Pair tests with **different saves** (`fight_flow_test.py
--gamedata1`), which no test had used before, found two ways a player's own
save reaches the match (details and runs: DIRECTFIGHT.md "Unlocks"):

- **Unlocks.** The select grid (Jinpachi's and the random cell), the stage
  lists and the random stage pickers follow the save's unlock byte. In a
  lockstep rematch the peer replays this PC's cursor presses on its own grid:
  another costume, a desync (run ctrl_ls). Launcher Settings -> Unlocks
  (`T5_UNLOCK_STAGES`, `T5_UNLOCK_ITEMS`) would make it common. Rule: a game
  started for online play (`T5_NET_MODE`, `T5_CTL_DIR`, `T5_FIGHT`,
  `T5_FIGHT_FILE`) answers the unlock check as a fresh save does, whatever its
  save and settings (`src/directfight/df_unlock.cpp`). The item prices are
  only changed offline.
- **The game's own options.** Difficulty, Round Time and save +7 go into the
  hashed battle state (and the round timer), Difficulty again during the
  match: a player with other options desynced every match (run c2). Rule: an
  online game keeps a save of its own. ps3recomp patch 0044 adds
  `PS3_SAVEDATA_DIR`; the launcher sets it to `<game folder>/gamedata-online`
  for every online game. Both PCs start from the same fresh save; the
  player's own save is never read or written by online play. The game's own
  button layout, round time and volumes are therefore offline-only settings;
  the launcher's controls (controls.ini) work online as before.

Proof (two games on this PC, persistent game, both mashing with motion
inputs, 1 round; the host with a save that has every unlock, free-bought
items, both settings on and -- for the second pair -- EASY / 1-round options;
the joiner a fresh save and both settings off):

| run | mode | what | result |
|---|---|---|---|
| rule_rb / rule_ls | rollback / lockstep | NRRNR: two lockstep rematches crossing the top row, stages 0, 13, 15, 5, 9 (Tekken 5 stages) | 5/5 and 5/5, 0 mismatching frames, the same hash |
| ctrl_ls | lockstep | the same with `T5_UNLOCK_ONLINE=save` on the host (the old behaviour) | match 2 apart: 1,327 mismatching frames |
| c2 | lockstep | the EASY save as the host's save, no `PS3_SAVEDATA_DIR` | every compared frame mismatching |
| osave_rb / osave_ls | rollback / lockstep | the EASY save as the host's own save, its online save fresh (`PS3_SAVEDATA_DIR`) | 3/3 and 3/3, 0 mismatching frames |

The Tekken 5 stages (ids 0-13 and 15) online, every one in both modes: see
DIRECTFIGHT.md "Unlocks" (sweep runs old_rb / old_ls) and docs/RANKED.md
"Characters and stages" (the server's `T5L_OLD_STAGES`).

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
  **Since 1.1.4 the pin is mixed with the match number** (`select_seed()` in
  t5_hooks.cpp: `(session seed ^ 0x7E1EC7ED) + k * 0x9E3779B9`, k = the fights
  this session has started, counted by the direct-fight driver at FIGHT START --
  the same on both PCs at their select screens and in a playback): with the
  session seed alone every rematch drew the same, so Mokujin copied the same
  fighter in every match of a session (owner report; the integration-114 base
  build, run pair_base: Mokujin copied fighter 0x06 in all three matches of a
  session, on both PCs; this build, runs pair_rb / pair_ls: 0x0C, 0x16, 0x05,
  0x10 in four rematches, the same on both PCs). k = 0 is 1.1.3's seed; a
  replay of format 3 or older plays back with k = 0 for every match, as it was
  recorded (docs/REPLAYS.md "Format 4"). Each new seed is logged once ("select
  screen: TLS generator pinned to ... (session s, match k of it)"), and FIGHT
  START logs what each fighter block plays ("P1 plays 0x...", +0x4C of the
  blocks 0x10090030 / 0x10090900: Mokujin's block holds the fighter he copies).

**Offline** the generator is not reseeded by anything (no sync points), and it
starts from the same state word at every boot, so with the same timing the same
draws came out after every start (Mokujin's copy: runs off2, two boots, Christie
both times; run off0 differed only through the players' timing). An offline game
(no T5_NET_MODE / T5_CTL_DIR / T5_FIGHT / T5_FIGHT_FILE / T5_REPLAY_FILE) now
seeds it once at the first frame boundary from the OS's random numbers
(`offline_seed()`, BCryptGenRandom; the log says "offline: the scene's random
generator seeded with ..."). `T5_OFFLINE_SEED=<n>` (tests): that seed, and every
generator pinned at the select screens as online, so the same picks give the
same Mokujin copy at every start; `T5_OFFLINE_SEED=0`: not seeded (the old
behaviour). `tools/offline_random_test.py` checks both (two boots, VS, the
random cell and Mokujin): default seeding, two boots each (off3, off6): a
different Mokujin copy (0x08 / 0x1B) or a different random-cell fighter (Steve /
Jack-5); `T5_OFFLINE_SEED=123` (off4, off7, off9): Mokujin copied the same
fighter in both boots every time. The random cell itself does not repeat even
then: it follows the frame it is pressed on, not only the generators.

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

| pair, the e2e agent's voided matchups (2 rounds, KOs), rollback | fixed | Steve vs Hwoarang 34, Bruce vs Lee 25, Marduk vs Bryan 18, Kazuya vs Feng 32, Marduk vs King 22, Marduk vs Roger 21 (N R N R N R) | 6 | -- | 6/6, 0 mismatching frames |
| rb_equiv `--lag 3`, release layout (`-DT5DR_GAME_DLL=ON` + t5dr_game.dll) | fixed | Heihachi vs Mokujin 29 | 1 | 2,691 | equal, the same final hash as the exe build |

Two PCs that differ, stood in for on this PC (pairs, persistent game, both
players mashing with motion inputs, 1 round unless noted; rollback delay 2
unless noted):

| run | the second PC | mode | matches | result |
|---|---|---|---|---|
| hz240_rb / hz240_ls | display at 240 Hz (no display lock, the 59.94 Hz clock) | rollback / lockstep | 4 / 3 | all in sync |
| cpus4_rb | host 16, joiner 4 logical processors (affinity + PS3_CPUS), rollback delay 1 | rollback | 3 | 2 in sync; match 3 lost to a driver bug (below) |
| cpus4_rb2 | the same, joiner also suspended 40 ms every 0.2-0.6 s, 2 rounds | rollback | 2 | match 1 in sync; match 2: the known NU::File::RequestManager abort (0x374150, the rollback-crash agent's) |
| cpus6_ls | host 6, joiner 16 logical processors | lockstep | 3 | all in sync |
| hitch_rb | joiner's main thread stalls 150 ms every 30-90 frames (T5_TEST_HITCH) | rollback | 3 | all in sync |
| stutter_rb | joiner process suspended 60 ms every 0.2-0.6 s | rollback | 3 | all in sync |
| fsdelay_rb | joiner's disk: 3 ms per open/read + 40 ms per MB (PS3_TEST_FS_DELAY) | rollback | 3 | all in sync |
| noaudio_rb | joiner with the launcher's "Mute sound" (PS3_NO_AUDIO=1: no audio for the game) | rollback | 3 | all in sync |
| clock_rb | joiner's clock 37,000 s off | rollback | 3 | all in sync |
| throttle_rb | joiner minimized under Windows power throttling (PS3_SCHED_THROTTLE=0) | rollback | 3 | all in sync |
| mixdelay / mixdelay_ls | rollback setting 1 vs 2 / lockstep delay 2 vs 5 | rollback / lockstep | 3 / 3 | all in sync |
| fma_rb / fma_ls | joiner: baseline build (`-DT5DR_LIFTED_ARCH=none`), software fma (PS3_FP_SOFT_FMA=1), the C runtime's non-FMA3 paths; host x86-64-v3 | rollback / lockstep | 3 / 3 | all in sync |
| rematch10b | a session of 10 matches: 1 new, 9 rematches with the same fighters, commands 1.5 s apart, P1/P2 first in turn | rollback | 10 | all in sync |

One game visible against one minimized was not run (every test game stays
minimized while the owner uses this PC); throttle_rb covers what a minimized
window changes (Windows' timer and power throttling).

**Also found: a match end that a rollback takes back** (cpus4_rb match 3):
the KO seen on a predicted frame and undone, the direct-fight driver kept
holding the local player and pressed START into the running fight; fixed in
`df_fight.cpp`, docs/DIRECTFIGHT.md "A match end that a rollback takes back".

**Left open.** Two PCs that differ in the CPU's make (Intel vs AMD) or a real
display at 240/500 Hz were stood in for, not used. The private generators
make effect particles and stage emitters differ between the two PCs' screens
(display only, as the camera may). The NU::File::RequestManager abort under
heavy rollback (2 of ~110 matches here) is the rollback-crash agent's.

## Desync hunt 2: stage 27 (branch desync-hunt-2, 2026-10-19)

After the first hunt about 1 in 240 real matches still went apart: in the
e2e gate on 1c4cd05 (and fd9ed5e) Steve vs Hwoarang on stage 27, in a
rematch chain, ~900 frames into the fight, in rollback and in lockstep, the
same winner, the camera words 0x10099710, 0x100A09C0, 0x100A3B40 and
0x100A3BB4..CC apart to the end; the lobby voided the games.

**Reproduced** with one game (`rb_equiv_test.py --fight ste,hwo,27,3 --full`,
a reference run and a run with T5_TEST_HITCH): about half the runs on main
part from the reference -- and two reference runs side by side part from each
other too, no hitch needed -- with different winners (3-0 against 0-3) or
the same one. The first words apart are always the same: 0x1008F0D0, then
+0x174 of the fighter blocks (0x10090A84, 0x100901B4: a move's random
number), +0x1A0, +0x2D4, +0x830, the secondary-motion points, and ~1,200
frames later the camera matrix 0x100996E0.. and its copies -- the e2e words
(all but the camera on the hashes' skip lists). Pairs reproduce it too: a
rematch chain of Steve vs Hwoarang on stage 27 (`fight_flow_test.py
--pattern NRRRRR --same-chars --stages 27 --rounds 3 --mash --moves`) on
main went apart in match 2 in lockstep (1,563 mismatching frames, the same
winner, exactly the e2e words) and in rollback (different winners). Two
causes:

1. **The ambient sound task stepped the scene's LCG.** 0x1008F0C4 (x -> 5x+3,
   +0x64 of the battle object 0x1008F060) is drawn from by the fight logic
   (0x15A40: which camera, which effect variant). The ambient sound task
   0xA9140 -> 0xA8DB8 beside the scene steps it too, for the delay of its next
   sound, but only when its last sound has stopped (0xAC814, the audio clock):
   two PCs stepped it a different number of times. It was left out of the
   hashes as a "timestamp". Now the task steps a private copy (the word is
   swapped while it runs), netplay reseeds it at every sync point, and it is
   hashed.
2. **Stage 27's crowd timers came from a timing-dependent stream.** Stage 27
   has 42 background fighters (0x8D0-byte fighter blocks in the heap from
   0x425CE770), driven by 21 controllers (0xB90-byte objects from 0x425C0000).
   The stage's set-up (the stage task 0x271ABC -> 0x274338 -> 0x2726B4 ->
   0x272020 -> 0x76E6C -> 0x75ABC -> 0xC6884 -> 0xCB9A0, during the loading)
   gives each controller a timer of rand() % 2000 + 1000 from the TLS
   generator. Those draws are outside the scene task: before the first hunt
   they came from the shared generator between the emitters' and effects'
   draws, since then from the private one -- either way from a position that
   depended on how many stage-emitter draws the PC had made before the session
   (six a frame, thousands at frame 0: 6,794 in one run, 6,788 in another, as
   many as the frames each PC waited).
   When a timer runs out its two crowd fighters fight: the fight's own actor
   loop (0x15498 -> 0x17768 -> 0xF1A74, for the two players and all 42)
   starts a move for a crowd fighter, and the move draws from 0x1008F0D0 --
   the generator 0xE859C (x * 0xDEECE66D + 0xB) the two players' moves draw
   from as well (+0x176 of a fighter block). One crowd fighter starting a move
   on one PC and not on the other ~600 frames into the fight shifted every
   later draw of the players: gameplay. Proof, two runs of one scripted match:
   the crowd blocks equal from frame 200 to 844 except the 21 timers; frame
   846 a crowd fighter started a move in one run only (`T5_RAND_TRACE=4`, the
   draws with their actors); from 848 the players' numbers differ.

**The fix** (`src/rollback/rb_rand.cpp`): the private draws (everything on
the main thread outside the scene task) come from one stream per call site
(the guest return address), and every stream starts over from the match seed
at each sync point (netplay's `reseed()`, with the TLS generator). A call
site's numbers then depend on its own calls only: the stage set-up's are the
same on every PC; the emitters' and effects' (their count follows the PC's
timing) stay among themselves. The crowd lives in the heap, which the
rollback state saves, so a rollback puts it back with the frame.

0x1008F0D0 stays out of the hashes: before FIGHT START it is a counter the
intro's timing moves (frames 190-222), and at FIGHT START the game sets it.
The crowd blocks are not hashed either (heap addresses).

**Diagnostics.** `T5_RAND_TRACE=4`: every draw of the generator 0xE859C
with the frame, the state word, the state before, the actor each enclosing
fight function was called for and the caller chain, every TLS-generator draw
(P = private, S = scene) with its return address and chain, and the fight's
actor loop (0x17744: its flag and counter; 0xF1A28: each actor) -- rb_lcg.log.
`T5_NET_DUMP=frames` with `T5_NET_DUMP_RANGES=425C0000:30000` dumps the
crowd.

**What was tested** (this PC, other agents' games running; stage 27 unless
noted):

| test | build | what | runs / matches | result |
|---|---|---|---|---|
| rb_equiv `--full`, Steve vs Hwoarang, 1 and 3 rounds, a reference and runs with T5_TEST_HITCH (or a second reference beside it) | before (1c4cd05 + the sound-task fix) | one scripted match, one process | 13 comparisons | 6 apart (first word 0x1008F0D0 at frame 757 or 848); four different final states, winners 3-0 or 0-3 |
| the same | fixed | 1 round / 3 rounds | 8 + 8 comparisons, 20 runs | all equal; every run the same final hash; the crowd's 21 timers equal in all 20 (dump at frame 200) |
| pair, lockstep, `--pattern NRRRRR --same-chars --rounds 3`, Steve vs Hwoarang | before (main 1c4cd05) | a rematch chain | 2 matches | match 2 apart: 1,563 mismatching frames, same winner, the e2e words |
| pair, rollback, the same | before (main 1c4cd05) | a rematch chain | 2 matches | match 2 apart, different winners |
| the same two pairs | fixed | | 6 + 6 | all in sync |
| pair, rollback, Jin vs Lili, `NRRRRR` | fixed | | 6 | all in sync |
| pair, rollback, opponent switches (`NNNN`, a fresh game every 2nd match, host and joiner in turn), 2 rounds | fixed | | 4 | all in sync; the crowd's set-up runs again at every new session (41 draws) |
| rb_equiv `--full --lag 3`, Steve vs Hwoarang 2 rounds / Heihachi vs Mokujin 29 | fixed, on main 2c7ed8a | 1,047 / 533 rollbacks | 2 | equal on every frame |
| pairs, lockstep / rollback, 6 matches each (N R N N R N), 12 stages: 29 24 31 20 34 17 / 25 30 33 18 32 22, 12 fighters, 2 rounds | fixed, on main 2c7ed8a | the per-call-site streams elsewhere | 6 + 6 | all in sync |
| pairs, lockstep / rollback, stage 27, 6 matches each (N R R N R R: Jin vs Lili, Steve vs Hwoarang), 3 rounds | fixed, on main 2c7ed8a | | 6 + 6 | all in sync |
| rb_equiv `--full`, Jin vs Lili 3 rounds, T5_TEST_HITCH=100:20:60 | fixed, on main 2c7ed8a | | 1 | equal on all 6,299 frames |

Also run on main 2c7ed8a: tests/ (473, OK), the lobby's suite (15 modules, 455
tests, OK), smoke quick (5/5 PASS), the game-data guard (`--keys` and
`--history HEAD`: exit 0).

## Stage 27: the shadow box at the fight's start (branch s27-start-desync, 1.1.2)

The 1.1.2 e2e pre-gate (main 7486b0c, every real match forced onto stage 27)
voided one rollback match in about 30: Roger Jr. vs Armor King, RTT 80 ms, 2 %
loss, the eighth session of two persistent games. The two games disagreed for
10 frames at the very start of the fight (session frames 226-235, about 3.8 s
after FIGHT START), then agreed again; same final state, same winner. Only
four words differed, as +- pairs: 0x100996C8/CC (+-561..644) and
0x100996D0/D4 (+-990..1050), apart by 0.004-0.05 and less from frame to frame.

**What the words are.** 0x100996B4 is the renderer's current projection
(0x24 bytes): +0x0 its type, +0x4/+0x8 near and far, +0x10 the aspect, and
for an off-centre projection (type 3) left/right/top/bottom at
+0x14..+0x20 -- the four words. Two setters write it: 0x80A94 (perspective)
and 0x80C94 (off-centre, `-l, l, -t, t, near, far` in f1..f6, also handed to
the NU renderer by 0x35D27C). On stage 27, during the fight, the last
projection set before each frame boundary is the shadow pass's
(write-fault and access traces: render pass 0x268418 -> 0x15A974 ->
0x80C94, main thread, once per frame): 0x15A974 fits an orthographic box
around both fighters for the shadow map (0x15A3A0, the shadow projector
object 0x10627500) from six bone positions of each fighter's skeleton
(`[[fighter + 0x8A4] + 0x10]`, 0x159310 -> 0x158B3C), and the half-widths of
that box are the four words.

**Not rollback-made.** The first differing hash is frame 226, the state
after frame 225. Every input up to frame 225 was neutral on both PCs (the
intro rule: phase 12 until boundary 223, input delay 2; the first scripted
press took effect in frame 226), so no misprediction and no rollback can reach
frame 225, and a rollback never recomputes the hash of the boundary it
restores to. The box was computed differently on the two PCs from game state
that hashed the same -- the fighters' bones are not in the hashed areas (the
heap) -- and the difference faded within 10 frames as the fighters moved.
The record follows the render passes, not the fight, in other ways too: in a
traced pair it switched to the result screen's 2D projection (0, 1920, 0,
1080) one and two frames apart on the two PCs after a match's deciding KO
(frames no longer compared there).

**Never read by the game.** `T5_RB_RFT=100996B4:24 T5_RB_RFT_NET=300:40`
(rb_rft.cpp, below) watched every access to the record for 40 fight frames:
writes only by the two setters from render passes, reads of +0x0..+0x10 only
by the setters themselves, and of the four frustum words none by any game
code (only our own hash and snapshot copies). The rest of the fight -- the
camera matrix 0x100996E0 and its copies, the side flags, positions, health,
timer -- matched on every frame of that match. So the record is render state,
not match state: it is now left out of both state hashes
(`kDefaultHashSkip` in t5_hooks.cpp, `kGameSkip` in rb_state.cpp,
`100996B4:24`). The fighters' bones stay where they were (in the rollback
state, restored with the frame, not hashed); what they decide in the fight
(the camera-projected screen x and from it the side flags, hits) is hashed and
would still report a real desync. tests/test_hash_skip_sync.py checks that the
two skip lists are the same.

**What the traces did show: the fighters' bone blocks before the fight.** A
skeleton (`[fighter + 0x8A4]`) has two blocks of 27 x 0x90 bytes in the
game's own heap: the bones now (`+0x10`) and last frame's copy (`+0x14`,
copied by 0x28C17C every fight frame). The fight writes about two thirds of
them from its first frame on; before that -- the loading and the intros, which
the desync check does not compare -- they hold whatever that memory held
(a fresh game: 172 of 972 words set, the rest zero; a persistent game: what
its earlier matches left). In 6 of 30 traced e2e sessions one fighter's bone
block differed between the PCs through the loading and the intro, and became
equal on the first fight frame. The most likely origin of the gate's 10 frames
is such a leftover that the first fight frames of that pairing still read.
Clearing the blocks at the fight-loaded sync point would remove it, but which
of those words the game's own set-up writes before the fight is not known (a
fresh game's are not all zero), so it is left as a follow-up; the record that
showed it is not game state either way.

**Not reproduced on demand.** With the fighters' bones, the projector and the
skipped words traced on both PCs (`T5_RB_SHADOW_TRACE`, below) the box and its
inputs were identical on every frame in: 25 e2e net_rollback sessions on
stage 27 (the gate's flow: persistent games, in-game select, RTT 20-250, loss,
jitter, relay; old build), 3 + 7 pair matches Roger Jr. vs Armor King at RTT 80 /
2 % loss, a persistent pair with a slow disk on the joiner
(`PS3_TEST_FS_DELAY`), and one-process runs (`rb_equiv_test.py`, Roger Jr. vs
Armor King, stage 27) with forced rollbacks (`--force 5:3`, 255 rollbacks),
real mispredictions (`--lag 3`, 307), main-thread hitches and the SPURS job
pages kept in the state: equal on every frame, the record too. Where the
gate's bones came from is therefore not known; the words that showed it are
not game state.

**Diagnostics added** (off unless set):

- `T5_RB_SHADOW_TRACE=1` (`rb_shadowtrace.cpp`): `rb_shadow.log` in the game's
  folder. `S` lines, one per run of the shadow fit (0x15A3A0): frame,
  re-simulated or not, phase, the box, eye, target, light direction, per
  fighter the skeleton and bone block pointers, a hash of the bone block and
  the six bone positions the fit reads, the record. `B` lines, one per frame
  boundary up to `T5_RB_SHADOW_TRACE_TO` (default 400): hashes of the hashed
  areas taken whole (no skip list), of each fighter block and bone block, the
  skipped words that the moves use (0x1008F0D0, 0x1008F0C4, +0x174 of each
  fighter, the secondary-motion points) and the projector's words. The last
  line for a frame is its final state. Two PCs' logs diff per frame. With it,
  `T5_RB_SHADOW_DUMP=f1,f2,...` writes each fighter's skeleton blocks at those
  boundaries (`pose_f<f>_P<n>_{cur,prev,sk}.bin`).
- `T5_RB_RFT=addr:len` + `T5_RB_RFT_NET=from:frames` (`rb_rft.cpp`): every read
  and write of those bytes over those live frames, with the accessing guest
  function and its callers (game log and rb_frames.log `R` lines). The page
  is made inaccessible and each access single-stepped: slow, tests only.

**What was tested** (this PC, other agents' games running; stage 27):

| run | build | what | matches | result |
|---|---|---|---|---|
| e2e net_rollback `--stage s27`, traced (`T5_RB_SHADOW_TRACE`) | before the fix (record hashed) | the gate's flow: persistent games, in-game select, RTT 20-250, loss, jitter, relay | 30 | 0 mismatching frames; the box and its inputs identical in every fight frame on both PCs |
| pairs, RTT 80 / 2 %, Roger Jr. vs Armor King, traced | before the fix | process mode, mash with motion inputs | 3 | 0 mismatching; box, bones identical |
| rb_equiv, Roger Jr. vs Armor King, `--force 5:3` / `--lag 3` / `--lag 3` + `T5_RB_JOB_PAGES=keep` / `T5_TEST_HITCH=100:20:60` | before the fix | one process, a reference and a test run | 4 x 1 | equal on every frame (255 forced, 307 and 316 real rollbacks) |
| pair, RTT 80 / 2 % loss, 20 stage-27 matches (Roger Jr. vs Armor King first and last, 18 other pairs), 1 round, mash with motion inputs, traced | fixed (main f5bed92 merged) | `rollback_net_test.py` (`build/s27b/scripts/rbpair.sh`) | 20 | 0 mismatching frames in 43,200 per side; 8,993 / 8,772 rollbacks (9,972 / 9,758 frames re-simulated); every result (winner, score, frames, hash) the same on both PCs; the shadow box and its inputs identical on all 43,262 traced frames |
| the same, RTT 150 / 3 % loss | fixed | | 20 | 0 mismatching frames in 43,200 per side; 10,554 / 10,617 rollbacks (29,698 / 29,525 frames re-simulated); results the same; box and inputs identical on all 43,275 frames |
| e2e net_rollback, a normal pass (the lobby's stages: 18, 19, 22, 23, 26, 28, 31, 32) | fixed | RTT 20/80/150/250, delay Auto/0/1/2, 2 % and 10 % loss, jitter, relay | 11 | PASS, 245 checks, 0 mismatching frames |
| e2e net_lockstep `--stage s27` | fixed | RTT 20/150, 10 % loss with jitter, relay | 4 | PASS, 87 checks, 0 mismatching frames |
| pair, lockstep (`T5_RB_MODE=off` both), RTT 80 / 2 %, 10 stage-27 matches | fixed | | 10 | 0 mismatching frames through frame 19,799 on both PCs (delay 5); every result the same |

Also on the fixed build: smoke quick (3 PASS, 2 WARN: fps with 9 other games
running; exit 0), tests/ (630, OK, 9 skipped), the game-data guard (index and
`--history 760f8b0..HEAD`: exit 0).

**Not the same bug: the firewall e2e run's Asuka vs Wang on stage 26** (frames
231-1849 apart, the whole fight). There one game left the intro a frame
earlier than the other: from frame 231 the phase word itself (0x1008F070, 17
against 12), the round timer and the input ring differ -- the whole fight runs
a frame apart, with another final hash. Its log shows the cause's neighbourhood:
at 0.5 fps its loader drain gave up seven times ("frame 8..16, 31: loader
threads still busy after 2 s, going on", `t5_hooks.cpp drain_wait`), so loads
finished in frames that differed between the two PCs before the fight-loaded
barrier; the other game had no such timeout. That needs its own fix (the
drain's 2 s limit during a session's loading); the record has nothing to do
with it. (Fixed on branch load-drain-sync: "Slow loading" below.)

## Slow loading (branch load-drain-sync, 1.1.2)

**The bug** (e2e firewall run, Asuka vs Wang on stage 26, rollback; above). One game
ran at about 0.5 fps on an overloaded PC; its loader drain gave up again and again
("loader threads still busy after 2 s, going on" -- ten such lines, the log's cap,
then more without a line: that session's drains took 41.8 s in 53 frames, every one
of them cut at 2 s), the other game never. From frame 231 on the phase word was 17
on one PC and 12 on the other: the whole fight ran a frame apart (1,619 of 1,620
frames mismatching), the final hashes differed, the match was voided.

**Why.** The drain (`t5_hooks.cpp drain_wait`) is what makes a load finish in the
same frame on both PCs: at the top of every frame the main thread waits until the
loader threads it feeds (ZsAread, semaphore 8: the async reads; "decoder",
semaphore 10) are parked with nothing queued, so a load started in frame f is
always done, as far as the game can tell, when frame f + 1 starts. The intro rule
of the rollback loop and the fight-loaded sync point rely on it: from the loading's
end the intros run a fixed number of frames on both PCs. The drain gave up after
2 s of wall-clock time; on a PC that needed longer, frames started with their loads
still running, the game saw them done a frame or more later than the other PC did,
the loading took more frames there (203 against 196) -- which the fight-loaded sync
point put back together -- and the state the intros started from was not the same:
here the slow game left the intro one frame earlier. The 2 s limit was never needed
for anything but a loader that hangs.

Reproduced on demand with the old build: a persistent pair, the joiner on two
logical processors (`--cpus2 0xC0000000`) with a slow disk (`PS3_TEST_FS_DELAY=20:3000`:
20 ms per open/read + 3 s per MB), Asuka vs Wang on stage 26: its drain gave up
from frame 1 on (49 drains, 52.7 s), both games continued at frame 204 after the
fight-loaded sync point, the host's intro ended at 233, the joiner's at 237 -- 1,601 /
2,575 mismatching frames, different final hashes (run `repro1`).

**The rule now: no wall-clock time decides when a load is done.**

- The drain waits as long as the loads take while a session runs. A frame never
  starts with its loads running, however slow the disk or the CPU. After 2 s, 5 s,
  ... the log says so ("loader threads still busy after N s -- the frame waits for
  them"), and once the frame goes on, how long it took.
- The peer waits for that frame's input meanwhile. So that its stall limits do not
  end the match for a PC that is only slow, every PING says the sender is loading
  (`PING_LOADING`, set after 1 s in the drain; our inputs ride along every 200 ms so
  a lost packet costs nothing extra), and the peer's `T5_NET_TIMEOUT` /
  `T5_NET_START_TIMEOUT` clocks in its waits for our input or our scene change do
  not run while it says so (`StallClock` in netplay_core.cpp). A wait for one frame's
  input also starts its clock again whenever the peer shows progress (new inputs, or
  its lockstep beginning): a peer that took 60 s to start used to count as stalled
  for 60 s at once when its start switched the limit from 120 s to 20 s.
- A load that really hangs ends the match cleanly: one frame waiting longer than
  `T5_NET_LOAD_TIMEOUT` (default 120 s, 0 = never) -> this game ends the session with
  `load_timeout` ("LOADING TOOK TOO LONG" in the log, result file reason, BYE with the
  reason), the peer gets `peer_load_timeout` at once; the launcher shows "Loading the
  fight took too long on this PC / on your opponent's PC" (all catalogs). A session
  lost meanwhile (the peer left, timed out) stops the wait too: nothing is compared
  any more.
- `T5_TEST_DRAIN_HOLD=ms[:frame]` (tests): the drain also holds frame `frame`
  (default 5) of each session for at least `ms`.

**Other wall-clock limits between the select screen and the fight** (grep for
GetTickCount, timeouts, "going on" in src/netplay, src/rollback, src/directfight):

| where | what | could the two PCs diverge? | now |
|---|---|---|---|
| `t5_hooks.cpp drain_wait` | loaders busy 2 s -> the frame went on | yes (this bug) | waits; `T5_NET_LOAD_TIMEOUT` ends the match |
| `rb_net.cpp boundary` | lockstep windows (a scene change, 60 frames after a load, a rematch's select screen) and the end of the prediction window: 2 s for the peer's input, then the frame ran on a prediction | yes: a slow peer (now: one that waits for its loads) let the other side predict past the 8-frame window -- deeper than the undo log can reach after long stalls ("cannot be rolled back -- DESYNC likely") -- and inside the windows that keep rollbacks off loads and the select screen | `np::rb_wait_input`: waits like the lockstep's begin_frame until the input comes or the session is lost (silence, BYE, or `T5_NET_TIMEOUT` without progress and without a loading report: `peer_stalled`; before the peer started `T5_NET_START_TIMEOUT`: `start_timeout`) |
| `df_fight.cpp` Title | start VS waited for the title's savedata autosave at most 10 s | yes: start VS beside the autosave puts the fight heap 1 MB apart (reset-fix's whole-match desync); a disk slower than 10 s would bring it back | waits for the autosave; one that never ends is the stuck check's (60 s: exit 6, the launcher starts a fresh game) |
| `df_fight.cpp take_peer_pick` | no opponent pick 75 s after this select screen came up -> this PC took the line's character for the opponent | yes: an opponent whose select screen came up more than 45 s later (a slow PC loading it) could pick another fighter on its own screen | waits; nothing after 120 s -> the session ends (`peer_stalled`), never a guessed fighter. A select screen comes up within the stuck check's 60 s or that game ends itself |
| `t5_hooks.cpp side_drain` | the geometry request manager not parked after 2 s -> the boundary went on | no: a busy count in a snapshot, not frame timing (a rollback to it could hang the present; never seen: busy at most 2 ms in every log) | unchanged |
| `t5_hooks.cpp ensure_keyread_parked` | 5 s, then the take-over is postponed a frame | no: an offset before lockstep frame 0, which the fight-loaded sync point evens out (as for a persistent vs a fresh game) | unchanged |
| `netplay_core.cpp` handshake, `begin_frame`, `scene_barrier`, tick thread | `T5_NET_CONNECT_TIMEOUT`, `T5_NET_START_TIMEOUT`, `T5_NET_TIMEOUT` | no: they end the session (`no_peer`, `start_timeout`, `peer_stalled`, `peer_timeout`), never play on | the peer's loading no longer counts as a stall |
| `t5_hooks.cpp flush_result` | the result waits up to 3 s for the deciding frame's hash comparison | no: what is reported, not the game | unchanged |
| `rb_net.cpp` time sync, early rollback | sleeps, when a rollback runs | no: pacing only | a correction skips one vblank tick in the runtime (patch 0080, docs/ROLLBACK.md section 34) instead of sleeping on GetTickCount64 |
| `df_fight.cpp` pick clock (30 s), Select = random | this player's own pick | no: decided on one PC and sent to the other | unchanged |

**What was tested** (this PC, 32 logical processors, other agents' games running; two games of
one pair at a time, below-normal, persistent games, both players mashing with motion inputs,
1 round, `--net-timeout 20` as the lobby; runs in build/drain). The slow side ran on two logical
processors (`--cpus1/2 0xC0000000`) with one of: a slow disk, harsh (`PS3_TEST_FS_DELAY=20:3000`)
or moderate (`10:1500`); or starved loaders -- three busy processes on its two processors and its
low-priority guest threads (ZsAread 1002, decoder 1003) at `THREAD_PRIORITY_IDLE`
(`PS3_SCHED_PRIO_PPULO=-15`), so they run on Windows' starvation boosts only: the e2e run's
pattern (1-3 fps while loading, the decoder busy, "going on" from frame 8 on). Matches after the
first are rematches (`--pattern NRRR`): a new session re-enters the select screen from the title,
which on such a PC can stall at phase 1 (the select-stall bug, its own branch).

| run | build | mode | slow side | what | matches | result |
|---|---|---|---|---|---|---|
| repro1 | old (main df72a78) | rollback | joiner, harsh disk | Asuka vs Wang 26 | 1 | **DESYNC**: drain gave up from frame 1 on (49 frames, 52.7 s), loads ended at 194 / 204, intros 233 / 237, 2,575 / 1,601 mismatching frames, different final hashes |
| G1c | old | rollback | joiner, starved loaders | Asuka vs Wang 26 | 1 | drain gave up on the slow side only (22 frames, 25.7 s; the other side's longest wait 152 ms), loads ended at 194 / 196; this match happened to stay in sync -- with a final hash different from the fixed build's same match (2,205 frames against 1,948): when the loading ended still depended on the clock |
| fix2 | fixed | rollback | joiner, harsh disk | Nina vs Law 27; Steve vs Hwoarang 25 | 1 + 1 | match 1 in sync (frame 1 waited 20.9 s for the loads, the peer waited with "its game is loading"); match 2 never started: the joiner's select screen from the title stalled at phase 1 (select-stall), the host ended after 120 s -- no desync |
| A | fixed | rollback | joiner, harsh disk | stages 26, 32, 18, 27 | 4 | 4/4, 0 mismatching frames, same hashes; 16 frames waited >= 2 s for loads (longest 47.5 s) |
| C | fixed | rollback | host, moderate disk | stages 23, 34, 20, 17 | 4 | 4/4, 0 mismatching, same hashes; 14 long waits (longest 24.2 s) |
| E | fixed | rollback | joiner, moderate disk | stages 30, 21, 26, 31 | 4 | 4/4, 0 mismatching, same hashes; 13 long waits (longest 23.9 s) |
| G2c | fixed | rollback | joiner, starved loaders | stages 26, 32, 18, 27 | 4 | 4/4, 0 mismatching; 29 long waits (longest 5.3 s); the same four final hashes, frame counts, winners and load-end frames (194, 2449, 4614, 6687) as run A |
| B | fixed | lockstep | host, harsh disk | stages 26, 28, 31, 34 | 4 | 4/4, 0 mismatching, same hashes; 16 long waits (longest 47.5 s) |
| D | fixed | lockstep | joiner, moderate disk | stages 28, 20, 17, 25 | 4 | 4/4, 0 mismatching, same hashes; 16 long waits (longest 23.9 s) |
| F | fixed | lockstep | host, moderate disk | stages 26, 22, 32, 19 | 4 | 4/4, 0 mismatching, same hashes; 13 long waits (longest 23.8 s) |
| G3c | fixed | lockstep | host, starved loaders | stages 26, 28, 31, 34 | 4 | 4/4, 0 mismatching; the same final hashes and load-end frames as run B |
| hold_rb / hold_ls | fixed | rollback / lockstep | joiner / host: `T5_TEST_DRAIN_HOLD=35000` (frame 5 held 35 s, longer than `T5_NET_TIMEOUT` 20) | 2 + 2 | all in sync; the peer waited 35 s ("its game is loading") instead of ending with `peer_stalled` |
| lto_rb / lto_ls | fixed | rollback / lockstep | joiner / host: frame 5 held 40 s, `T5_NET_LOAD_TIMEOUT=25` | 1 + 1 | the match ends cleanly after 25 s: "LOADING TOOK TOO LONG", result `load_timeout` there, `peer_load_timeout` on the other side at once (BYE), 0 mismatching frames |

In total on the fixed build: rollback 17 fought matches (34,098 frames per side), lockstep 16
(31,574), on 15 different stages, the slow side as host and as joiner in both modes: 0 mismatching
frames, every result (winner, score, frames, hash) the same on both PCs, and in every match the
loading ended in the same frame on both PCs (no "scene change ... here at frame X, peer at Y"
line). Two different kinds of slow PC gave the identical match, frame for frame (A = G2c,
B = G3c). Also: smoke quick PASS (82 checks, 2 fps WARN with 8 other games running),
tests/ 634 OK (9 skipped), lobby/tests 571 OK, the game-data guard (index and
`--history df72a78..HEAD`) exit 0; tests/c/netplay_fuzz.cpp checks PING_LOADING, the BYE
reasons, give_up() and the stall clock (a mutation of the clock's restart fails it).

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
