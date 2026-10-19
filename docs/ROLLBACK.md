# Rollback netcode for the native Tekken 5 DR build -- feasibility, findings, design

Branch `rollback`, code in `src/rollback/`, runtime change in
`patches/ps3recomp/0008-rollback.patch`. All guest addresses are for
NPUB30009 v01.00 and this runtime's memory map (`PS3_VM_WRITE_WATCH=1`).

**Status (phase 10, branch `rollback10`): rollback is the online default**
-- offered with direct fight unless `T5_RB_MODE=off`, lockstep when the peer
does not offer it. Sections 20-25 are the current state, with sections
26-30 (latency branch: 60 fps at RTT 150, input delay by ping, the
end-of-match hang under heavy rollback), 31 (rematch-fix: rematches, the GCM
ring end, post-match and select-screen rules) and 32 (rollback-crash branch:
the file manager, the music stream object and the sound library's heap left
out of the rollback state); the earlier sections are the history that led
there.

## Verdict

Rollback is feasible. The core mechanism works in the prototype:

- The complete simulation state of a fight lives in ~104 MB of guest memory
  (six ranges, listed below); a frame of fight changes ~330 pages (1.3 MB)
  of it, plus ~550 pages of render/audio data that need neither saving nor
  hashing.
- Saving and restoring it at the main thread's frame boundary is safe: the
  side threads touch none of it except known, excluded handoff areas, and a
  restore reproduces the saved state hash exactly.
- Re-simulating N frames from a restored state with the same inputs
  reproduces the uninterrupted run's state hash at every frame boundary
  (`T5_RB_MODE=test`, runs t5/t7/t8/t11: 8-frame rollbacks every 60 frames
  through a scripted VS fight with attacks, 0 mismatching boundaries once
  the dozen wall-clock words listed below are masked).
- A re-simulated frame runs the game's own main-loop iteration with the
  GPU/vblank handshake bypassed, so N frames run back to back.

The problem is cost, not correctness: a re-simulated frame costs as much
CPU as a normal frame (~65 M cycles of main-thread time, about 15 ms at
this CPU's 4.5 GHz; measured with other instances loading the machine,
so take it as an upper bound) because the game pushes its draw packets
from inside the scene update, interleaved with the logic -- there is no
sim-only phase to call. Re-simulating 8 frames therefore takes ~120 ms.
Rollback at full rate needs either a faster lifted build (the fight frame
already costs 13-17 ms of main-thread CPU in the normal build) or a cut of
the NU draw-packet submission during re-simulation (an indirect-call
redirect in the runtime, see section 5). With 2-3 frames of input delay
and rollbacks of 1-2 frames it is workable today at a hitch per rollback.

What is NOT done: the draw cut, incremental (dirty-page) snapshots, the
input-prediction / rollback decision logic of a real GGPO loop, and the
integration with np's transport. The design for those is below.

## 1. Where the simulation state is

### Main loop (runtime backtrace at the frame boundary, every run)

```
func_00010244 (ELF entry) -> func_00010250 (main) -> func_00011040 (game main loop)
  loop body, once per frame (0x110B0..0x11150):
    0x25B71C                handle check
    0x259F68 -> 0x259E90    frame begin
    0x31F7E4                PRESENT: 0x34DDB4 -> 0x383C9C -> 0x34BA30
                            (frame clock 0x106D4D88++, cellGcmSetUserCommand,
                             poll cellGcmGetFlipStatus with usleep(100),
                             sys_semaphore_wait(0x106D4A30)  <-- FRAME BOUNDARY HOOK
                             then usleep(1000)-loop until >= [0x106D4D98] vblanks passed)
    0x259958 -> 0x36C4B8    timebase stamp (mftb) for profiling
    0x1423A8 -> 0x1423CC    SIM UPDATE: 0x142300(scene) with scene = [0x10532DF0]
    0x25C61C, 0x9A784       misc / loader state machine (sys_semaphore_trywait)
    0xAA1D4 -> 0xAA200      returns at once if [0x10065B70] == 0 (it is 0 while the
                            title renders), else 0xAAA18, 0xAC424, 0x9BFE8, 0x32819C
                            -- NOT the frame's draw: the scene update above pushes
                            the draw packets itself (indirect-call trace of one fight
                            frame: ~930 vtable calls, 263x 0x355C70, 230x 0x355B34,
                            87x 0x3559E4 ... all NU::Draw packet functions)
```

The frame semaphore 0x106D4A30 is posted by the vblank handler 0x34BC08
(`[0x106D4A00+0x30]`), which also runs the callback list at 0x106D4BE0 and
used to wake the keyread thread. So a frame = flip done AND a vblank; the
sim runs exactly one step per rendered frame (counter 0x1008EB9C advances by
1 every frame, 969/969 frames checked -- there is no catch-up logic).

### Memory (measure mode, `GetWriteWatch` over the committed guest memory)

Committed guest memory in a fight is 108 MB: ELF image 0x00010000+0x470000,
main thread TLS 0x0E000000 (+0x20000), GCM context 0x0F800000, main thread
stack 0x0FEF0000, ELF data/bss 0x10000000+0x770000, other threads' TLS
0x10F00000, HLE GCM window 0x20000000, the game's heap 0x40000000+0x5F00000
(cellGcm IO memory starts at 0x40100000: FIFO ring 0x40100000..0x40500000),
cellAudio buffers 0x58000000, side-thread stacks 0xD00xxxxx.

Per frame (fight, VS mode): ~880 pages written in total (3.5 MB). Hot set
(pages written in >= half the frames, `tools/rollback_measure_analyze.py`):

| region | pages/frame | what |
|---|---|---|
| 0x10114000+0x58000 | 88 | sound core (bnusCore) mix/output, written by the sound thread while main is parked |
| 0x43D00000+0xA0000 / 0x43EA0000+0xA0000 | 93 each, alternating | double-buffered draw list |
| 0x444F9000+0x6E000 | 97 | per-frame render scratch |
| 0x40100000+0x400000 | varies | GCM FIFO |
| 0x10000000+0x770000 (data) | ~190 | game state: 0x1041C000+0x39000, 0x10612000+0x32000, 0x10082000+0x2F000, 0x1073D000, 0x106C8000, 0x10532000, 0x10052000 ... |
| heap objects 0x41A11000, 0x41D39000, 0x41B4A000, 0x41E74000, 0x42xxxxxx | ~60 | characters, animation, matrices |
| 0x58000000 | 16 | cellAudio port buffer (audio thread) |

Side threads (NU::File/Draw/Geometry request managers, TNUD::ASync,
keyread, sound, decoder) write, while the main thread is parked at the
boundary: only the sound areas (0x10114000+0x58000, 0x4000C000.., 0x4002D000..),
the audio buffer, the vblank counter page 0x106D4000, single words at
0x10532000/0x10624000/0x10752000 (vblank copies, request counters), the
decoder area 0x45F00000 and their own stacks. The draw request managers are
idle at the boundary. So the main thread owns the state at that point.

### State set used by the prototype (`rb_test.cpp`, `kSave`)

```
0x0E000000+0x20000   main thread TLS (per-frame random word at +0, libc rand seed set by 0x3AFF24)
0x0F800000+0x10000   CellGcmContextData (mask the FIFO write pointer +8)
0x0FEF0000+0x10000   main thread stack (restored, not hashed)
0x10000000+0x770000  ELF data + bss
0x10F00000+0xF0000   TLS blocks of created threads (lifter image)
0x40000000+0x5F00000 heap
```
Excluded from restore and hash (`kExclude`): 0x10114000+0x58000 (sound),
0x40000000+0x100000 (first heap chunk: bnusCore voice slots/requests, written
by the sound threads), 0x45F00000+0x100000 (decoder/streaming). Restored but
not hashed (`kHashExclude`): main stack, 0x10532000 and 0x10750000+0x3000
(engine request counters, NU::File request list -- follow the draw phase),
GCM FIFO, draw lists, render scratch. Masked words inside hashed pages
(`kMask`): vblank counter and its copies 0x106D4D90+0x18, render-duration
statistics 0x106D4520+0xF0, flip flag 0x106D4A44, callback-list lock
0x106D4BE0+0x10, 0x105320C4, 0x10624720+0x30, mftb stamp 0x1074F9F8, async
counter 0x106CF0FC, a frame-time float 0x1062E454, GCM `current` 0x0F800008,
double-buffer selectors 0x10053800+0x100 and 0x40049210, and the draw-enable
word 0x10065B70 while draws are skipped. Every one of these was found by the
test's per-page diff against the captured original frame; nothing in the
list is fight state.

## 2. Saving and restoring at the frame boundary

Hook: lv2 syscall 92 (`sys_semaphore_wait`) on the main thread for the id at
0x106D4A30, after the wait returned -- the point right before the sim of the
next frame, with the main thread's host stack always in the same shape
(main loop -> 0x31F7E4 -> 0x34DDB4 -> 0x383C9C -> 0x34BA30 -> syscall). The
restore writes guest memory only; the lifted frames' callee-saved copies
(`_cs_` locals) hold loop-invariant object pointers (checked in 0x11040,
0x383C9C, 0x34BA30: r27..r31 are TOC-loaded pointers or constants), so no
register state needs restoring. ppu_context is untouched.

Input: the keyread thread (0x120BB0) is parked by swallowing the vblank's
posts to its semaphore (0x104CB5C0); the main thread runs one keyread tick at
each boundary (np's finding: 0x9A204, 0x8F3A4 pad update, 0x120764 ring reset
when [0x104CCDF8], 0x8F6F0 port masks into the ring 0x104CCDFC, 0x12071C,
0x13F91C), with `cellPadGetData` overridden to answer for the logical frame.
Input is then a function of the frame number, and the ring/pad blocks are
part of the restored state.

Measured (prototype, full copies): snapshot of the 104 MB set 4.5-18 ms,
restore 23-35 ms (includes rehashing 24.7k pages). A restore reproduces the
snapshot's hash (`== snapshot` in every rollback of t7/t8/t11).

What breaks on restore: nothing fatal in 60+ rollbacks across runs (no
crash, the fight continues, 60 fps resumes). The sound areas are left alone
(voices already requested keep playing; re-simulated frames re-request
sounds -- audible duplicates are the expected glitch). The GCM FIFO is not
touched; the re-simulated frames do not submit draws.

## 3. Re-simulation

While re-simulating (`set_bypass(true)`): `sys_semaphore_wait` on the frame
semaphore returns at once and the vblank's posts to it are swallowed (no
pile-up); `cellGcmSetUserCommand` is a no-op (no GPU handshake, no flip),
`cellGcmGetFlipStatus` reports DONE, `cellGcmResetFlipStatus` is a no-op;
the pacing field `[0x106D4D98]` (u64 min vblanks per frame) is zeroed so the
usleep(1000) loop never runs. `T5_RB_SKIPDRAW=1` zeroes 0x10065B70, which
turned out not to remove the draw work (see above). The game's own loop
then runs its iterations back to back; the frame after the last
re-simulated one is a normal frame with the waits back on.

Cost per re-simulated frame (t11, `QueryThreadCycleTime` of the main
thread, so other processes' load is mostly excluded): 58-73 M cycles,
the same as a normal frame (66.6 M average over 1389 frames, which
includes the 0.4 ms hash update) -- i.e. ~15 ms at 4.5 GHz. Wall clock
per re-simulated frame was 16-25 ms on a quiet machine (t7, still with the
vblank pacing loop active) and 31-45 ms with six instances running. The
main thread's normal work per fight frame (boundary to
cellGcmSetUserCommand, `uc` in measure logs) is 13-17 ms under that load,
2.4 ms in menus; a title-screen frame traced on a quiet machine had 3 ms
of work in 16.5 ms.

## 4. Determinism

Sources checked:

- `sys_time_get_current_time` seeds the Mersenne Twister at boot (0xAE6C8;
  state 0x10095168, index 0x10053578; np reseeds it from the session seed).
  The libc `srand` 0x3AFF24 writes a per-thread seed in TLS+0 (0x0E000000);
  the TLS block is part of the state set and re-simulates identically.
- mftb (`ppu_timebase_now`) is read by 19 lifted functions; the ones hit per
  frame (0x36C4B8 via 0x259958, the stamp at 0x1074F9F8, the render
  duration statistics at 0x106D4520..) only feed profiling/statistics words.
- The vblank counter 0x106D4D90 (written by the vblank handler on the
  ticker thread) paces the present and nothing else: the sim counter
  advances exactly once per frame regardless of vblank deltas.
- Thread timing: the side threads' writes are confined to the excluded
  areas; the draw request managers are quiescent at the boundary.
- Floating point: the lifted code reproduced bit-identical results across
  all rollbacks (hash over 24.7k pages including every character/animation
  page); SPURS skinning output (0x4363C000.. vertex pages) matched too when
  the draw ran during re-simulation (t5).
- cellPad: the keyread parking makes the ring deterministic per frame.

Result: 8-frame re-simulations reproduce the uninterrupted run's hash at
every boundary (hash = per-page 64-bit mix of all hashed pages, combined by
page index).

## 5. Design for the real thing

1. **Snapshots**: keep a shadow copy of the state set and, per frame, the
   kernel's dirty-page list (`GetWriteWatch`, 0.3-0.9 ms for 108 MB): copy
   the pre-image of each dirty page from the shadow into an undo log for
   that frame, then refresh the shadow (~330-700 pages, 1.3-2.8 MB per
   frame -- about 1 ms). Rolling back k frames = applying k undo logs
   newest-first (k x ~1.3 MB). No 104 MB copies. The write-watch
   reservation needs `PS3_VM_WRITE_WATCH=1` (patch 0008).
2. **Save point**: the frame-semaphore hook, as in the prototype.
3. **Resim**: as in the prototype -- the game's own loop with the waits
   bypassed, keyread tick per logical frame with the (predicted or
   confirmed) inputs. To make it affordable the draw-packet submission
   must be cut during re-simulation: the NU::Draw packet functions are
   reached through vtables, i.e. through `ps3_indirect_call` in the
   runtime, so a small runtime addition (an indirect-call redirect table:
   target -> replacement, consulted only while re-simulating) can route
   0x355C70 / 0x355B34 / 0x3559E4 / ... to a returning stub; the state
   hash tells whether the sim depends on their results. Without the cut,
   budget ~15 ms per re-simulated frame and limit rollbacks to 1-2 frames
   (input delay 2-3). A faster lifted build (inlined guest memory access --
   `vm_write32` showed up as a call in the samples) lowers both the normal
   frame and the resim.
4. **Inputs**: np's transport provides remote inputs; local input delay 0-2
   frames, prediction = repeat last input; on a late packet that differs,
   roll back to that frame and re-simulate up to the current one.
5. **Desync check**: the per-frame state hash already exists (incremental,
   cheap); exchange it with the peer every frame or every N frames.
6. **Sound**: leave the sound areas alone across rollbacks (as now); a
   re-simulated frame re-issues sound requests -- suppress them during
   re-simulation if the duplicates are audible (the bnusCore request API
   is in 0x40000000+0x100000 handoff memory).

## Risks

- Scene changes (round start/end, KO slow-motion, stage transitions)
  within a rollback window: untested; the loader state machine 0x9A784
  waits on a semaphore -- a rollback across a load would need the load to
  be complete on both sides (np's scene barrier).
- Sound: duplicate/missed sound effects on rollback; the sound core's
  shared memory must stay excluded from restore (restoring it hung nothing
  in tests, but it is written by three threads).
- Hidden wall-clock dependence: every non-sim word found so far was a
  statistic; a dependence that only shows in rare situations (e.g. the
  NU::File streaming requests that the draw issues) would show up as a
  hash mismatch -- keep the desync check on.
- Performance: the re-simulation of N frames must fit in the frame budget;
  the sim step cost on an unloaded machine still has to be confirmed (the
  numbers here were taken with other instances running).
- The prototype restores the main thread stack and the created threads' TLS
  blocks wholesale; both were harmless in tests but are more than needed.

## How to run

```
PS3_VM_WRITE_WATCH=1 T5_RB_MODE=measure  ...   per-frame dirty pages (tools/rollback_measure_analyze.py)
PS3_VM_WRITE_WATCH=1 T5_RB_MODE=test T5_RB_START=3000 T5_RB_SAVE_EVERY=60 T5_RB_RESIM=8 T5_RB_SKIPDRAW=1
    T5_RB_SCRIPT=... T5_RB_SCRIPT2=...   (tools/rollback_test.py sets a script that reaches a VS fight)
```
Optional: `T5_RB_TRACE=1` (syscall timeline of one normal and one resim
frame), `T5_RB_SAMPLE=1` (RIP samples of the first resim; resolve against
t5dr.map), `T5_RB_PADDBG=1`, `T5_RB_HASH_EXCLUDE=addr:len,...`.
The log `rb_frames.log` has one `F` line per frame (hash, dirty pages,
counters), `R` lines for re-simulated boundaries with MATCH/MISMATCH, and
`[rb]` notes with per-page word diffs on a mismatch.

## Evidence

Runs are under build/rb/runs/<name>/ (game.log, rb_frames.log, shots).

- m2/m3 (`measure`, 100 s, scripted into a VS fight): 880 dirty pages per
  fight frame, hot set 557-618 pages; menus 250-270. Side-thread writes
  while main is parked: 88-page sound block, audio buffer, 0x106D4000,
  single words in 0x10532000/0x10624000, 0x4000C000.., 0x4002D000..,
  0x45F00000... Main thread work per fight frame 13-17 ms (`uc`).
- t5 (`test`, attract-mode CPU fight, draw running during resim): rollbacks
  at 2700 and 2940, 8 frames each: `mismatching boundaries 0`; the one at
  2820 differed only in the sound voice slots (0x4000A000) -- since
  excluded. Restore hash `== snapshot`.
- t7 (`test`, 13 rollbacks every 60 frames): 12 clean; the one mismatch was
  the flip flag 0x106D4A44 (since masked). t8 (16 rollbacks): 15 clean, the
  other the callback-list lock owner 0x106D4BE0 (since masked).
- t9/t10/t11 (`test`, VS fight Lili vs Dragunov with scripted attacks,
  rollback every 60 frames from 3000, shots confirm the fight): every
  mismatch was one of 0x106CF0FC (async counter), 0x1062E454/458 (two
  statistics floats) or a draw-list link page beyond the excluded range --
  all masked/excluded now; the first frame after a restore reproduced the
  original frame's content in all other 24.7k pages.
- Restore faithful: `hash == snapshot` in all 40+ rollbacks after the sound
  chunk was excluded; before that, 0x4001B000 (sound entries) broke it.
- Per-frame hashed-state dirty set during the fight: 330-394 pages.
- Syscall timeline (t7): a normal title frame = 64 syscalls in the first
  3 ms (NU resource-manager mutex/cond ops, one sys_event_queue_receive),
  then the flip/vblank wait until 16.2 ms; a re-simulated frame had the same
  64 syscalls -- the draw work was not skipped.
- RIP samples over a resim (t8/t9): with the pacing field half-zeroed 91 %
  of samples were in system DLLs (the usleep loop); after the u64 fix the
  in-exe samples were in the prototype's own hash/diff code, `vm_write32`,
  `vmx_vmaddfp` and NU draw functions 0x355C70/0x355B34/0x35375C.

---

# Phase 2 -- making rollback affordable (branch `rollback2`, build/rb2)

Runtime change: `patches/ps3recomp/0016-icall-hook.patch` (one hook in
`ps3_indirect_call`, see 6). New code in `src/rollback/`: `rb_state.*` (state
set, hash, undo-log snapshots), `rb_icall.cpp` (draw cut, per-target timing),
`rb_sample.cpp` (stack-sampling profiler), `rb_wft.cpp` (write-fault tracer),
`rb_net.*` (the GGPO-style loop), `rb_test.cpp` (the test mode, rewritten on
the state module). Netplay additions: `np::rb_*` in `src/netplay/netplay_core.cpp`
(the transport without the per-frame block) and the `T5_RB_MODE=net` branch
in `src/netplay/t5_hooks.cpp`. Test harness: `tools/rollback_net_test.py`.
Runs are under build/rb2/runs/<name>/ (game.log, rb_frames.log).

## 6. The draw cut

**Where the time went.** Two new tools answered it: a stack-sampling
profiler of the main thread (`T5_RB_SAMPLE=1`: SuspendThread + RtlVirtualUnwind
every 150 us, host frames mapped to lifted functions, inclusive/self tables
and folded stacks in `rb_prof_<tag>.txt`) and an inclusive/exclusive timer of
every vtable call (`T5_RB_ICALL_TIMING=1`, through the new hook). A fight
frame of the main thread splits into the present (`0x31F7E4 -> 0x34DDB4 ->
0x383C9C`: flip, the wait for the draw thread, the per-frame semaphore) and the
scene update (`0x25C518 -> 0x25B580` recursion over the scene nodes). Inside
the update the fighter node (`0x2683F4`) calls each model's draw through a
vtable (`0x352F80` -> slot +0x34 -> `0x387324` / `0x3872A8`: matrices,
materials, skinning kick; 3-4 calls per frame, ~2.5 ms exclusive each on this
CPU), and the stage, effects and shadows push their packets through
`0x158D6C`, `0x1357A0`, `0x1EC6FC`, `0x9DC04`, `0x264220`. All of them end in
the NU::Draw packet writers (`0x355C70` 16-byte move, `0x355B34`, `0x389788`,
`0x389820`, `0x3898D0`, `0x389A88`, `0x389A0C`, `0x389AA0`, `0x38988C`,
`0x397AF8`, `0x354160`, `0x353E68`, `0x3559E4`, `0x357F88`) -- confirmed by the
write-fault tracer (`T5_RB_WFT=43D00000:340000,...`: the draw-list pages are
made read-only for one frame and every first write faults into a handler
that records the lifted call chain).

Two waits also had to go: the present's `cellGcmSetFlip` + `cellGcmSetWaitFlip`
(the HLE sleeps up to 64 ms for a flip nobody requested; 35 % of a
re-simulated frame's wall time in phase 1) are no-ops while re-simulating,
like `cellGcmSetUserCommand` and the flip status before.

**The hook** (patch 0016): `ps3_icall_hook(ctx, target)` is consulted in
`ps3_indirect_call` with the resolved target; a non-zero return means the hook
handled the call (stubbed it, or forwarded it through
`ps3_indirect_call_direct`). NULL by default, one load and a predictable
branch per indirect call otherwise. Direct (`bl`) calls are compiled in and
cannot be redirected, so a cut is only complete for targets reached through
vtables -- which the whole draw submission is.

**The cut** (`kDrawCut` in `rb_icall.cpp`, `T5_RB_CUT=addr,...` overrides,
`T5_RB_CUT=none` disables): while re-simulating, the 21 targets above return 0
without running (they all return 0 when live: `ret0` column of the timing).

**What the cut may not touch -- and the verdict.** The full-state hash of a
re-simulated frame differs from the original's after a cut frame: the draw
keeps bookkeeping (NU::Draw allocation cursors in `0x10742000..0x1074B000`, a
48 KB matrix block in the heap whose address changes per run, per-model
packet pointers in the model instances). None of it is gameplay, and the two
peers of a match roll back at different moments anyway, so render bookkeeping
can never be part of the desync hash. The verdict of the cut is therefore the
**gameplay hash** (`state_game_hash()`: the netplay desync check's regions --
pad blocks, input ring, frame clock, all random generators, round state, both
fighters, ~25 KB) at every re-simulated boundary, including the boundary
after the last re-simulated frame ran *with* the draw again (`T5_RB_CUT_TAIL`,
the situation after a real rollback):

| cut set | gameplay hash | full-state hash at the final boundary |
|---|---|---|
| none (r0) | 0 mismatches / 112 boundaries, 14 rollbacks | matches (undo-log restore + resim reproduce phase 1) |
| model draw only (c2) | 2 / 32 (two transient words, see 8) | differs (bookkeeping) |
| model draw + packet writers (c3) | **0 / 104**, 13 rollbacks | differs (bookkeeping) |
| + stage/effect/shadow passes (c6) | **0 / 32** | differs (bookkeeping) |
| + `0x50B68`, `0x264B04` (c5) | 88 / 88 -- gameplay | -- |
| + `0x259A64` (c4) | 4 / 8 | -- |

`0x264B04` (called once per fighter) and `0x50B68` are the character
animation / skeleton update (`0x2884AC -> 0x27F3DC -> 0x2844E4 -> 0x28C17C`,
trig-heavy) and the match manager: the fight reads their results, they stay.
`0x259A64` is the main loop's wait for the draw thread's previous list
(`0x267FE4 -> 0x34CA64 -> callback 0x380A10 -> sys_event_queue_receive`); it is
not cut either, its cost is a wait, not CPU.

The draw path writes the libc TLS page and the `rand()` state page thousands
of times per frame (`T5_RB_WFT_ALL=1` single-step trace), but those are libm
scratch words next to the generators, not `rand()` calls: the generator
states are in the gameplay hash and match.

**Cost** (`rb_frames.log` `R` lines: QueryThreadCycleTime of the main thread
and wall time per re-simulated frame; the machine ran 4-6 other game
instances of other agents during every measurement, so absolute numbers are
an upper bound):

| per frame (medians over a run; cycles at ~4.5 GHz) | main-thread cycles | wall |
|---|---|---|
| normal fight frame (draw + present waits), same runs | 69-77 M | 40-50 ms (17-24 fps under that load) |
| re-simulated frame, no cut (phase 1 / r0) | 115 M = the normal frame of that run (118 M) | 33 ms |
| re-simulated frame, cut B (c3, 16 targets) | 43 M (62 % of normal) | 19.7 ms, min 8.4 |
| re-simulated frame, cut C (m1, 21 targets) | **34.6 M (46 %)**, p10 31.6, min 24.3 | 14.7 ms, p10 9.0, min 5.4 |
| cut C + sound update skipped (c7, section 8) | **27.7 M (36 %)**, p10 25.7, min 22.2 | 10.5 ms, p10 6.8, min 5.7 |
| the invalid cut c5 (animation/skeleton update removed, for scale) | 25.9 M | -- |

m1: 23 rollbacks of 8 frames, 0 gameplay-hash mismatches in 184 re-simulated
boundaries; c7: 20 rollbacks, 0 in 160. 27.7 M cycles are ~6 ms on this
CPU with 20 other game instances competing for it; the same count on a
quiet machine was not measured (no quiet moment during this session).

The syscall timeline of a cut frame (`T5_RB_TRACE=1`, run t1) shows where the
rest is: ~9 ms of lifted sim code (the two fighters' animation and logic,
`0x2683F4` subtree), then the present's 1.5 ms `sys_cond_wait` for the draw
thread (`0x357714`) and 0.7 ms `sys_event_queue_receive` (`0x380A10`),
both waits on the draw thread that still runs the (now nearly empty) lists.
So a re-simulated frame costs a third of a normal frame, not the 2-3 ms
target: the fighters' animation/skeleton update alone (`0x264B04` x2 +
`0x50B68`, c5) is ~9 M cycles, the sim logic the rest. What remains is
runtime overhead (the `cpu`/`pf` work: inlined guest memory access, `vmx_*`
helpers), which scales both, and the two draw-thread waits in the present
(a direct-call path; they could be bypassed at the syscall level once the
draw thread is known to be idle).

## 7. Undo-log snapshots (`rb_state.cpp`)

`state_init()` takes one shadow copy of the state set (103 MB, ~50 ms, once)
and resets the write watch. `state_commit(f)` at every boundary:
`GetWriteWatch(RESET)` over the six ranges (0.3-0.9 ms), then per dirty page
(700-760 in a fight, 330 of them hashed): append `{ea, old hash}` + the page's
pre-image (from the shadow) to the undo ring, refresh the shadow, rehash the
page. **1.0-1.9 ms per frame** (`commit` field of the `F` lines; max 4 ms on a
loaded machine). The ring holds 24 576 pages (96 MB, ~32 fight frames; 64
log slots). `state_rollback(to)` applies the logs newest-first: **5-9 ms for
8 frames** (5 400-7 500 page restores, 2 memcpy each + hash fix-up), i.e. 0.7-1
ms per frame rolled back; `hash == point` on every rollback of every run (no
full rehash needed). A scene barrier drops the logs (`state_drop_logs`).

## 8. Sound during re-simulation

The main thread's only writes into the bnusCore handoff area
(`0x40000000+0x100000`, write-fault trace w2) come from the main loop's sound
update `0xAA200 -> 0x32819C` (`0x32C820`, `0x32C4F0`, `0x32C368`, ...); the
rest are the sound threads'. `0xAA200` returns at once when the word its TOC
slot (`r2 - 0x61E8`, -> `0x10065B70`) points to is 0. `sound_skip(true)`
zeroes it for re-simulated frames (`T5_RB_SKIPSOUND=1` in the test,
`T5_RB_NET_SKIPSOUND` in the loop, on by default) and restores it for the
live frame; the word is masked out of the hash. Verified: c7, 20 rollbacks,
0 gameplay-hash mismatches in 160 boundaries, and the sound update turned
out to be ~7 M cycles per frame (the c7 row above). What is NOT verified: the
audible result (no AUDIO_WAV analysis), and the `0xAAA18`/`0xAC424`/`0x9BFE8`
calls that the same word gates (the gameplay hash does not see them).

## 9. The rollback loop (`rb_net.*`, `T5_RB_MODE=net`)

Runs inside netplay's hooks (`t5_hooks.cpp` hands every boundary to
`rb::net::on_boundary()` once lockstep frame `T5_RB_NET_START` is reached;
until then the delay-based lockstep runs unchanged, which is how the two
test instances get through the menus in sync). Per boundary of frame f:
commit (undo log + hash); `np::rb_sample_local(f)` (this PC's input for
f + delay, sent at once with the usual redundancy); `np::rb_poll()`; the
first frame g < min(f, peer inputs known) whose confirmed remote input
differs from the one it was simulated with -> `state_rollback(g)`, waits,
draw and sound off, re-simulate g..f-1 (the same hook path: the frame
semaphore wait returns at once), then the live frame f draws; if the peer is
more than `T5_RB_NET_MAXPRED` (8) frames behind, wait for it; hand the final
hashes (frames with every input confirmed) to the transport's desync check;
return the inputs of the frame to run (remote = confirmed, or the last
confirmed input repeated). A scene change (ring reset / `t5_netplay_start`)
is acted on only after every input before it is confirmed, then it is the
lockstep's sync point and a floor for rollbacks. Statistics every 300 frames
(`[rbnet]` lines): fps, rollbacks, frames re-simulated, depth histogram,
ms per rollback, stalls, frames run on predicted input, desync mismatches.

`tools/rollback_net_test.py --rtt 100 --loss 5 --delay 2` runs a host and a
joiner on one PC through a UDP proxy that adds the latency (+-jitter) and
loss, with varied scripted attacks on both sides from the fight on.

**Results** (one PC, 15-20 game instances of other agents running at the
same time, so 15-18 fps; delay 2, prediction window 8; menus in np's lockstep,
rollback from lockstep frame 3400 -- runs under build/rb2/netruns/):

| | n1: RTT 0 | n3: RTT 150 ms, +-5 ms jitter, 2 % loss |
|---|---|---|
| joiner, per 300 frames | 22-39 rollbacks, 54-90 frames re-simulated, depth 1-7 (mostly 2-3) | 38-40 rollbacks, 107-178 frames re-simulated, depth 1-8 (mostly 3-5) |
| ms per rollback (restore + resim, loaded machine) | 27-44 ms (max 121) | 26-63 ms (max 129) |
| stalls | 1 (104 ms) | 0, plus one 396 ms wait at a scene change |
| host | 0-1 rollbacks, 0-4 frames on predicted input | 0 rollbacks |

Both sides stayed at the same fps as in lockstep; no crash, no failed
restore. The asymmetry is expected without GGPO's time synchronisation: the
joiner runs ahead by the input delay, so it predicts every host input and
takes every rollback while the host always has the joiner's input in time.
The frame-advantage balancing (the side that is ahead sleeps a frame now
and then) is the next step. Open: the n2 run (RTT 100 ms) never got past the
handshake (the joiner sent 3 packets; a port or proxy issue of the test
harness, not seen at 0 or 150 ms); the desync counters of these runs are
meaningless because np's lockstep diverged in the menus before the fight
(its known menu non-determinism under load, frame 2211-2217 in every run),
so the gameplay-hash agreement between two peers across rollbacks is
verified in-process only (m1/c7), not yet peer-to-peer.

## What is left

- Time sync between the peers (frame advantage), and a quiet-machine
  measurement of the re-simulated frame (27.7 M cycles under load).
- Rollbacks across round start/end and KO slow-motion were only exercised
  incidentally (the scripted fights ran through rounds in m1/c7 with
  rollbacks every 40 frames and 0 gameplay mismatches, and n3 stalled
  correctly at a scene change); a targeted test of the barrier rule is
  still to do. Rule as implemented: a scene change (input-ring reset) is a
  barrier -- all inputs before it must be confirmed, it is a lockstep sync
  point, no rollback reaches back before it.
- The sound skip's audible effect (AUDIO_WAV) and the other calls gated by
  the same word.
- The two draw-thread waits in the present (1.5 + 0.7 ms per re-simulated
  frame) and the sim's own cost, which only the runtime's speed work
  (`cpu`/`pf`) lowers.
- Direct-fight integration: `t5_netplay_start()` works unchanged (rollback
  from frame 0 with `T5_RB_NET_START=0`), untested.

---

# Phase 3 -- time sync, negotiation, barrier tests, sound, the draw thread (branch `rollback3`)

Online now means: lobby -> direct fight -> this netplay. Rollback is the
default when both peers have it; the delay-based lockstep is the fallback.

## 10. What changed

**Negotiation (HELLO).** `HelloExt` carries a `flags` word (bit 0 = this side
offers rollback; an older peer's 8-byte HELLO reads as no offer). The offer is
made in `h_cellPadInit` before the handshake (`rb::net::offer()`) whenever
`T5_NET_MODE` is set and `T5_RB_MODE` is unset or `net`; `T5_RB_MODE=lockstep`
(or `off`) withholds it. `np::rb_negotiated()` = both offered and connected;
`rb::net::enabled()` requires it, so a peer without rollback (or one that
asked for lockstep) gets the lockstep on both sides. Run n5 (joiner with
`T5_RB_MODE=lockstep`): host offered, joiner did not, both ran the lockstep
through frame 3600 with no rollback loop on either side.

**Direct fight.** With `T5_NET_START=external` the fight start
(`t5_netplay_start()` from `src/directfight`, branch `direct-fight`) is
lockstep frame 0: np's frame-0 handshake and RNG reseed run as before and the
rollback loop takes over at frame 1 (`T5_RB_NET_START` default 0 means "the
first frame after the handshake"). A later `t5_netplay_start()` (next match)
is a scene barrier. Not yet exercised with the direct-fight branch itself
(still in progress); the tests here switch at a lockstep frame in the fight.

**Time sync** (GGPO's frame-advantage balancing). Every input packet carries
the sender's lead estimate (`InputHdr.lead`: own frame minus the peer's
frame as implied by its latest input, i.e. `f - (remote_contig - 1 - delay)`);
the true advantage is `(mine - theirs) / 2` averaged over 30 frames; a side
ahead by >= 1 frame sleeps that many frames (<= 3) at the boundary, at most
once per 60 frames (`np::rb_wait_remote` with a timeout, so the socket stays
pumped). `T5_RB_NET_TIMESYNC=0` disables it. Run n4 (RTT 150 ms +-5, 2 %
loss, delay 2, both scripts attacking, 300-frame windows, loaded machine at
16-19 fps):

| window | joiner: advantage, rollbacks, sleeps | host: advantage, rollbacks, sleeps |
|---|---|---|
| 1 | +3.60 frames, 34 (117 frames re-simulated, depth <= 7), 5 sleeps (283 ms) | -3.27, 2, 0 |
| 2 | +1.06, 20 (41), 2 (94 ms) | -0.99, 2, 0 |
| 3 | +0.50, 19 (22, depth <= 2), 2 (50 ms) | -0.50, 3, 0 |
| 4 | -0.31, 8 (11), 1 (9 ms) | +0.33, 15 (24), 2 (44 ms) |

Without it (phase 2, n3) the joiner took every rollback (38-40 per window,
depth up to 8) and the host none.

**The draw thread's side** (`kDrawCut2`, `T5_RB_CUT2`). Profiling the draw
thread (`T5_RB_ICALL_TID=4`) during re-simulation showed it still processing
~900 packets per re-simulated frame (packets pushed by direct calls that the
main-thread cut cannot reach) and spending up to 20 ms per frame in one HLE
call, which is what the main thread's `sys_event_queue_receive` (0.7-8 ms)
and `sys_cond_wait` (1.5 ms) in the present were waiting for. The 18 per-packet
handlers of the NU::Draw request manager (`0x3552E0 0x392498 0x392334 0x397B54
0x385DBC 0x32659C 0x359A08 0x35E998 0x35933C 0x389914 0x389B28 0x355B78
0x385814 0x39229C 0x364CDC 0x36432C 0x362FDC 0x35ACEC`) are now stubbed on the
other threads while re-simulating. Run d2 (43 rollbacks, 0 gameplay
mismatches in 344 boundaries, no hang): the traced re-simulated frame ended at
7.0 ms with the receive at 0.34 ms and the cond wait at 0.005 ms, against
19.5 ms (receive 8.2 ms) in the same frame of d1 without it.

**Barrier rule under test** (`T5_RB_MODE=test`, rollbacks of 8 frames every
30, P2 idle so the rounds time out, 420 s, runs a1/a0/aref): the round timer
ran 3406 -> 0, the round ended (draw) and the next one started at ~frame
6700-7000 with the game's input-ring reset (the scene-change marker) at
frames 6707, 6708 and 6827; the rollbacks continued straight through --
a1: **190 rollbacks, 0 gameplay-hash mismatches in 1520 re-simulated
boundaries**, including two re-simulated boundaries that re-ran the ring
reset (R 6877/6878, both MATCH). So in-process, re-simulating across a round
end/start reproduces the game exactly. KO slow-motion and the match end are
covered by run a2 (both fighters attacking) -- see the table below. In the
netplay loop the rule stays conservative: a ring reset is acted on only once
every input before it is confirmed (a stall of one RTT), then it is a sync
point and the rollback floor.

**Sound** (`AUDIO_WAV`, `tools/rollback_audio_check.py`: silent stretches
>= 20 ms after the first sound, and transient onsets per minute as the
SFX-start rate):

| 420 s, same scripts, loaded machine | rollbacks | silent gaps | onsets/min |
|---|---|---|---|
| aref: no rollbacks | 0 | 93 (2.9 s) | 35 |
| a0: 8-frame rollbacks every 30 frames, sound update NOT skipped | 154 | 76 (2.8 s) | **50** |
| a1: same, sound update skipped in re-simulated frames | 190 | 125 (6.4 s) | 39 |

Without the skip, re-simulated frames re-issue their sound effects: +43 %
onsets (the duplicate-SFX artefact), plus 14 gameplay-hash mismatches of
1232 (the sound handles stored in the fighter blocks depend on the sound
thread's state). With the skip the onset rate is back at the reference
(+11 %, within run-to-run variation) and the hash is clean, but the silent
time doubles: the skipped update also feeds the music stream, and this test
skips it for 8 frames at a time 190 times. Real rollbacks are 1-4 frames
(n4), so the exposure is a few frames per rollback; the clean fix is to skip
only the SFX requests and keep the stream feed (`0x32819C`'s callees, to be
separated). Default stays skip on.

## 11. Cost with everything on, and what the long runs showed

Run a2 (both fighters attacking, 420 s, rollbacks every 30 frames): **76
rollbacks, 0 gameplay-hash mismatches in 608 re-simulated boundaries**; no
round was won in 420 s by either script (the scripted jabs do not land), so
KO slow-motion and the match end are still untested -- the round time-out
transition (a1) is the one covered.

**Time sync at RTT 100 ms** (n6, 11 windows of 300 frames): the joiner led
for five windows (advantage +1.4..+3.2 frames, 23-39 rollbacks per window,
3-5 sleeps), then the balance flipped (host 20/12/20 rollbacks, joiner 1/6/3)
and back again. It balances in aggregate but oscillates slowly: the estimate
lags (30-frame window) and a sleep is allowed only once per 60 frames. To
tune: shorter window, smaller and more frequent corrections (GGPO sleeps
whenever the averaged advantage rounds to >= 1 frame, every frame if needed).

Per re-simulated frame with everything on (a2, same loaded machine, medians):
**29.1 M main-thread cycles (27 % of that run's normal frame, p10 26.2 M,
min 19.5 M), 8.7 ms wall (p10 6.1, min 4.4), 182 dirty pages** (704-725 for
a normal frame; the cut frames touch a quarter of the memory), commit 1.26
ms, restore of 8 frames 6.0 ms. 26-29 M cycles are 5.8-6.5 ms at 4.5 GHz with
15-20 other instances fighting for the cores; the <= 5 ms target on a quiet
machine is plausible but unmeasured (the machine was never quiet).

**An open correctness issue.** Run m2 (same build and scripts as a2, started
at the same time) had gameplay-hash mismatches at every rollback from the
second re-simulated frame on (161 of 248 boundaries) while a2, d2 (0/344),
and g1-g4 (stages 19, 32, 31, 32; 0 mismatches in 368/336/272/264) were
clean. m2's fight wrote ~830 pages per frame instead of ~710, i.e. a
different, busier stage (the stage is the game's random pick; m2 ran before
the stage id was logged). So on at least one stage something the cuts remove
feeds the gameplay state. The test mode now logs the stage id at the first
rollback point and prints the first differing gameplay words on a mismatch
(`gameplay diff at`); the next step is to catch that stage again (run with
`--shots`), read the words, and bisect `T5_RB_CUT` / `T5_RB_CUT2` on it.
Until then rollback on that stage would desync (the per-frame hash exchange
catches it).

## What is left (phase 3)

- The stage-dependent mismatch above (find the stage, bisect the cut).
- Time-sync tuning (oscillation at RTT 100 ms).
- KO slow-motion / match end under rollback: a script that lands hits.
- Sound: skip only the SFX requests, keep the music stream feed
  (`0x32819C`'s callees), or shorten the skip to the rolled-back frames'
  new requests only.
- A quiet-machine cost measurement; the sim itself (animation/skeleton
  update, fight logic) is the floor until the runtime gets faster.
- Direct-fight: run the two instances through `src/directfight` with
  `T5_NET_START=external` once that branch lands; the handshake/negotiation
  path is the same as in the tests here.
- Peer-to-peer hash agreement across rollbacks is still only shown
  in-process: every two-instance run here diverged in np's lockstep menu
  phase before the fight (its known menu non-determinism under load, frame
  1590/2211), which the direct-fight start avoids.

---

# Phase 4 -- the stage mismatch, all stages, direct fight, time sync (branch `rollback4`)

## 12. The stage-specific mismatch was the C library `rand()` word

The test mode now forces the stage (`T5_RB_STAGE=17..34`, written to
`0x1008F088` from the stage confirm on, as direct fight does) and prints the
first differing gameplay words on a mismatch. Sweeping the 18 selectable
stages with 8-frame rollbacks every 30 frames (runs s17-s24, t25-t34):

| stage | rollbacks | gameplay-hash mismatches | differing word |
|---|---|---|---|
| 17, 19, 20, 21, 22, 23, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34 | 23-68 each | **0** (184-544 boundaries each) | -- |
| 18 | 34 | 12 of 272 | `0x1074F218` only |
| 24 (run m2's stage) | 45 | 279 of 360 | `0x1074F218` only |

`0x1074F218` is exactly the state word of the C library `rand()`
(`0x369228`: `state = state * 0x6C078965 + 12345`, pointer in the TOC slot
`0x4705CC`). Who calls it was found with the write-fault tracer narrowed to
that word over 40 live frames (`T5_RB_WFT=1074F000:1000 T5_RB_WFT_ALL=1
T5_RB_WFT_ADDR=1074F218 T5_RB_WFT_FRAMES=40`, run w6, stage 24): every call
comes from **`0x12C558` (8 call sites) <- `0x12CF34` <- `0x1230AC`, on a
side thread** (its chain roots in the runtime's thread trampoline, not in the
main loop), about 7 calls per frame on stage 24 and a few on stage 18 -- a
stage effect that runs at its own pace. The main thread's draw does not call
`rand()` at all (a first trace was polluted by the shield's own stores; the
`random()` lagged generator that the packet builders use lives outside the
hashed range). A consumer on another thread makes that word timing-dependent
with or without rollback, which is also what the direct-fight agent saw
between two PCs (the word diverged after match 2, everything else stayed
identical). It is therefore excluded from both gameplay hashes
(`rb_state.cpp` `kGameSkip`, `t5_hooks.cpp` `kDefaultHashSkip`); the fight
never read it in any of the 18 stages (no other word ever differed). A
`rand()` shield (private generator around the cut targets on live frames,
`T5_RB_RANDSHIELD=1`) was tried first and is kept off: it is not needed.

With the exclusion, stages 18 and 24 again (runs u18/u24) and 17 as control:
see the table at the end of this section.

**Rollback is the default online mode again** (`rb_net.cpp offered_by_env`):
offered in the HELLO whenever `T5_NET_MODE` is set unless
`T5_RB_MODE=lockstep` (or `off`); both peers offering = the rollback loop.

## 13. Direct fight, KO, time sync, sound

**Direct fight.** The test mode runs on top of `T5_FIGHT` (`tools/rollback_test.py
--fight p1,p2,stage[,rounds] [--ko]`): direct fight owns the pads and drives
the menus, the test injects its fight script per logical frame through
`df::inject()` from `T5_RB_START=auto` = `T5_RB_START_DELAY` (300) frames after
the game mode is first seen. A first try with 120 frames (run f1) rolled back
into the stage still streaming in and the game looped on null reads; with
300 frames (f2: Lili vs Dragunov, stage 24, 1 round) 203 rollbacks ran
cleanly. The netplay loop got the same protection: `T5_RB_NET_WARMUP` (180)
frames after its start it runs in lockstep (no prediction, no rollback), so
no rollback can reach into the fight's loading.

**KO slow-motion / match end: still not exercised.** Neither the original
scripts (both attacking), a launcher script against an idle P2 (k1, 7
minutes), nor the same on the direct fight (f2) dealt any damage: both health
bars stay full (screenshot build/rb2/runs/f2/shot_200s.png shows Lili's kick
on a guarding Dragunov), rounds end 0-0 by time-out. Rollbacks ran across
those time-out round ends with 0 mismatches (a1, f2 minus the rand word), but
the KO path needs real input (or a script that lands) and remains open.

**Time sync.** The first version (phase 3) slept 1000/60 ms per frame of
advantage; at the 15-18 fps of the loaded test machine that is a third of a
frame, so the side ahead never caught down (n7: host +1..+3.5 frames ahead
all run, 16-43 rollbacks per window, joiner 0). It now measures the frame
time (last 60 live frames) and sleeps in those units, every 10 frames, up to
2 frames (`T5_RB_NET_TS=win,interval,max`). Run n8 (RTT 100 ms, 2 % loss):
see below.

**Sound.** The 2-frame-rollback audio run (a3) was taken with 8 game
instances on the machine and its 20 s of silent gaps are CPU starvation, not
the skip (the no-rollback reference on a quieter machine had 2.9 s); the
SFX-only skip is still to do. Note that the sound update also runs on the
main thread, so its `rand()` use (none seen) is not the side-thread consumer
above.

**After the fix** (runs u18/u24/u17, 8-frame rollbacks every 30 frames):
stage 18: 38 rollbacks, **0 mismatches in 304 boundaries**; stage 24: 34,
**0 in 272**; stage 17 (control): 51, 0 in 408. Every selectable stage
(17-34) now re-simulates with the gameplay hash intact.

**Time sync at RTT 100 ms, retuned** (n8, sleeps at the boundary in measured
frame time, every 10 frames): the joiner stayed 1.1-2.0 frames ahead and took
every rollback (22-40 per 300 frames) through 19-30 sleeps per window, at the
same fps as the host -- the sleep is absorbed: the main thread sleeps while
the draw thread still works on the previous frame, so the frame pipeline is
not delayed at all. Taking the sleep inside the present's flip wait instead
(`T5_RB_NET_TS_FLIP=1`, n9) did delay the pipeline, but the host stalled for
a 75 s window and the pair fell apart (not understood yet), so it is off.
What is needed is a real frame skip (not advancing the game for one frame),
or a sleep placed after the draw thread's wait on the live path; left open.

---

# Phase 5 -- peer-to-peer agreement across rollbacks (branch `rollback5`)

## 14. The desync check in rollback mode

In rollback mode the loop now hands netplay's desync detector the
**gameplay hash of confirmed frames** (`np::rb_push_hash` with
`state_game_hash()`: a frame's hash is handed over once every input before it
is known on this side and any rollback that could change it has been
re-simulated), and writes `frames.log` (`f I <p1> <p2> <hash> R|P C|U`: the
inputs the frame ran with, R = remote confirmed / P = predicted). Before,
the full-state hash was pushed (render bookkeeping, legitimately different
between peers) and no frame line was written, which made every frame look
mismatching (the coordinator's npcheck4). `T5_NET_DESYNC_DUMP=1` now also
works here: the gameplay bytes of the last 64 boundaries, written as
`rb_desync_f<frame>.bin` on a mismatch (diff: build/rb2/tools/rb_desync_diff.py).

Test harness: `tools/rollback_net_test.py --fight p1,p2,stage,rounds` boots
both instances straight into the match (`T5_FIGHT`, `T5_NET_START=external`:
the fight is lockstep frame 0, the rollback loop takes over at frame 1 after
the warm-up), attack scripts (the ranked driver's: P1 square + forward, P2
triangle + back, varied) through files -- inline they exceeded the environment
and parsed as nothing, which is why the first batch (p0/p50/p150, q0/q50/q150)
ran with neutral input: in sync, but 0 rollbacks.

**Result, current build (patch series through 0022, input delay 0 so that
every frame is predicted; Asuka vs Lili, stage 20, 2 rounds, 3 % loss,
+-5 ms jitter):**

| run | RTT | rollbacks per 300 frames (frames re-simulated, max depth) | fps | sync check |
|---|---|---|---|---|
| d150, sound update skipped in resim (default) | 150 ms | host 33 (145, 9), joiner 37 (176, 9) | 34-38 | **0 mismatching frames through 9000** |
| d150b, sound update NOT skipped | 150 ms | joiner 37 (96, 5) | 29-47 | desync from frame 920: the whole Mersenne Twister state (0x10095168, 624 words) differs |

So the sound skip is needed for determinism, not only against duplicate
effects: the sound update consumes the game's Mersenne Twister, and a
re-simulated frame that runs it again consumes it once more than the live
frame on the other side. With the skip, the two peers agree on every
confirmed frame while rolling back 33-37 times per 300 frames. RTT 0 and
50 ms: see below.

**Open: the sound streamer's exit.** In one RTT-0 run of the old build (r0)
the host's sound streaming thread (`0x320228 -> 0x3201F8 -> 0x32089C ->
... -> 0x3A8704`) called `exit(1)` early in the match, i.e. the game quit.
That thread starves when the sound update is skipped for many consecutive
frames (section 10); the SFX-only skip is now the first thing to do.

**The RTT-0/50 desyncs and their cause.** With the attack scripts in place,
runs d0 and d50 (same build, sound skip on) desynced at frames 210 and 920,
d150b at 920 too, while d150 stayed in sync. The dumps and the logs agree on
the cause: the game resets its input ring at frames 225, 486, 751, 919 of the
fight (the lockstep treats every such reset as a scene change: sync point +
RNG reseed), and at 919 one peer saw the reset at a live boundary -- reseeded
the Mersenne Twister -- while the other, after a 1-frame rollback, saw it
again inside the re-simulated boundary, where only the keyread tick's ring
reset ran, no reseed. The whole MT state then differed (d150b's dump: 624
words at 0x10095168), and in d150 no reset ever reached a live boundary on
either side, which is why it stayed in sync. In rollback mode the ring
resets are now ordinary state (restored and replayed by rollbacks like
everything else; the peers are frame aligned, so the lockstep's re-alignment
and reseed are not needed); only `t5_netplay_start()` (the next match) is a
sync point. Verified by runs e0/e50/e150 below.

**Results with the ring-reset fix** (Asuka vs Lili, stage 20, 2 rounds, the
ranked driver's attack scripts -- hits land, rounds end by KO at ~frame 5370
--, input delay 0, 3 % loss, +-5 ms jitter; 330 s each):

| run | RTT | sound update in resim | rollbacks (host / joiner, whole run) | sync check |
|---|---|---|---|---|
| e0 | 0 | skipped | 761 / 878 | **0 mismatching frames through 10 800** (the full match, both rounds) |
| e50 | 50 | skipped | 1090 / 1094 | in sync until the round-end transition at frame 5369, then diverged |
| e150 | 150 | skipped | 699 / 1327 | diverged at frame 210 (the fight's first phase change) |
| g0 | 0 | not skipped | 456 / 371 | 29 mismatches by 5400, then the joiner's sound streamer called exit(1) |
| g50 | 50 | not skipped | 1074 / 1030 | diverged at frame 5369 (round end) |
| g150 | 150 | not skipped | 727 / 709 | 25 mismatches by 5400, then the joiner's sound streamer called exit(1) |

What differs when it diverges (dumps): the fight's **phase counter**
`0x1008F070` / `0x1008F078` (one peer one phase ahead: e150 12/11 at frame 210,
e50/g50 2/1 at the round end), the UI/setup block `0x100996B4..D4` it
triggers, and at the round end the block `0x1008E690..C0`. These are the
game's phase transitions (fight start, KO / round end): when a rollback
straddles one, the two peers come out of it one phase apart -- the transition
is not reproduced by re-simulation alone (it depends on something a rollback
does not restore: the excluded sound/loader areas), and e0 only stayed in
sync because none of its rollbacks straddled a transition. Rollbacks *within*
a round are reproduced exactly (e0: 1 639 rollbacks over a whole match).

So peer-to-peer agreement across rollbacks is shown within rounds, not yet
across round transitions; **rollback stays opt-in**. The missing piece is the
barrier at phase changes: the lockstep handled its scene changes with
`np::scene_barrier` (both continue at the later frame) -- the same, keyed on
`0x1008F070` changes at live boundaries and without the RNG reseed, is the
next step; alternatively the transition's wait has to be made a function of
the frame. The sound streamer's `exit(1)` (r0 with the skip, g0/g150
without it) is the other blocker: the streaming feed has to survive both
skipped and repeated sound updates.

---

# Phase 6 -- the phase barrier (branch `rollback6`)

## 15. Rollbacks across fight start, KO and round end

A phase change of `0x1008F070` seen at a live boundary now puts the loop into
lockstep for `T5_RB_NET_PHASE_LOCK` (600) frames: every frame after a
transition runs on confirmed inputs, so a re-simulation can only ever reach
across a transition from the few frames right before it (input delay + half
the RTT). The first variant also raised the rollback floor at the change;
that turned a 1-frame misprediction just before the transition into an
uncorrectable desync ("cannot be rolled back ... floor 210", runs h0/h150:
46/35 mismatching frames, the differing words being the inputs themselves),
so the floor is gone again. The warm-up after the start is 420 frames (the
fight-start phases at ~210 were straddled in e150).

Full matches, Asuka vs Lili, stage 20, 2 rounds, the ranked driver's attacks
(KOs at ~frame 5370), **input delay 1**, 3 % loss, +-5 ms jitter:

| run | RTT | rollbacks (host / joiner) | phase changes | sync check | sound streamer |
|---|---|---|---|---|---|
| i0 | 0 | 266 / 358 | 10 | **0 mismatching frames through 11 400 (the whole match)** | fine |
| i50 | 50 | 257 / 252 | 7 | **0 through 4 800** | joiner `exit(1)` at ~5 000 (round end) |
| i150 | 150 | 600 / 573 | 7 | **0 through 4 800** | joiner `exit(1)` at ~5 000 (round end) |

So peer-to-peer agreement now holds across the fight-start phases, KOs and
round ends (i0: both rounds, 10 phase changes, 624 rollbacks, 0 mismatches)
-- but the **sound streamer's `exit(1)`** at the round end (h50 host, i50 and
i150 joiners; before: r0, g0, g150) is not solved: a rollback that straddles
the round-end transition re-simulates the frame in which the sound update
switches the music/announcer stream; with the update skipped (default) the
streamer thread (`0x320228 -> 0x3201F8 -> 0x32089C -> ... -> 0x3A87E0`)
aborts the process, with the update re-run (g-runs) likewise. That is the one
remaining blocker, so **rollback stays opt-in**. Next: find what the
streamer asserts on (the stream switch request written by 0x32819C's callees
at the round end) and either replay it deterministically or hold the switch
until the frame is confirmed (extend the lockstep window to start a few
frames *before* a KO: health at 0 is visible one frame before the phase
changes).

---

# Phase 7 -- the sound streamer's abort (branch `rollback7`)

## 16. What aborts, and why it is not the rollback's state

The `exit(1)` is the title's own `abort()`: its stream reader
(`0x1ebb08 -> 0x1eb6f8 -> 0x67354 -> 0x37c4a0 -> 0x37f804`) gives up after
the HLE ATRAC3+ decoder reports `Invalid start bit` / `Frame data doesn't
match channel configuration` for the music stream -- the log shows the
errors start right after 1-frame rollbacks at the round end (5360, 5365)
and the abort follows a few frames later. The music is streamed by a side
thread (the one that opens T55DATA1.BIN and feeds `cellAtracAddStreamData`);
its bookkeeping is not rewound by a rollback (correctly: it is not the
simulation), while the main thread's half of the stream switch at the round
end is. Rewinding the HLE decoder's positions with the rollback (tried as
patch 0023: pos/next_frame/have/ring positions saved per boundary and put
back) made it far worse -- 1 100-2 700 decode errors per run instead of 2,
aborts just the same -- so that half belongs to the side thread too and the
patch was dropped. Runs with it, for the record (delay 1, 3 % loss): j0 and
j150 in sync (0 mismatches) until the joiner aborted at ~4 800; **j50: the
whole match (10 800 frames, 761 + 671 rollbacks, 10 phase changes) with 5
mismatching frames** -- the phase/UI words at the round end (5370), one peer
a phase ahead for five frames, then agreeing again (a transient, not a
divergence).

What remains to do: the main thread re-issues the stream switch when the
re-simulated frame reaches the round end again (its restored state says
"not switched yet"), so `cellAtracSetDataAndGetMemSize` runs twice for the
same handle while the feeder thread is mid-stream. The fix is to make that
second, identical request a no-op in the HLE (same handle, same buffer, same
file header: keep the slot), or to hold the switch in the title until the
frame is confirmed. Until then rollback stays opt-in (`T5_RB_MODE=net`).

---

# Phase 8 -- the music stream across rollbacks (branch `rollback8`, patch 0024)

## 17. What was tried, what the runs say

Patch 0024 (`libs/codec/cellAtrac.c`) does three things: a repeated
`cellAtracSetDataAndGetMemSize` for a live stream with the same handle, ring
and file header keeps the slot (it never fired: the title does not repeat
the call, so the double-switch hypothesis of section 16 was wrong); the HLE
lists its live streaming rings and the loop excludes those pages from the
rollback state (`cellAtrac_rb_live_rings`, `state_add_exclude`); and after a
restore the title's next stream adds are dropped until it asks
`cellAtracGetStreamDataInfo` again (`cellAtrac_rb_rolled_back`), on the
theory that the add was decided with a write position obtained before the
rollback. None of it stops the decode errors: with rollbacks running, both
peers log ~2 000 `Invalid start bit` per 10 000 frames whether or not they
abort, and the joiner still aborts at a round end at RTT 50-150 (k0, l50,
l150, m150), while whole matches at RTT 0 go through (l0: 12 000 frames,
790 rollbacks, 0 mismatches, no abort; m0: 10 200 frames, 648 rollbacks,
0 mismatches, no abort). Separately, m50 showed the round-end phase
divergence of section 15 again (4 830 mismatching frames from 5 370: one
side's rollback straddled the KO), so that barrier is probabilistic, not a
guarantee.

Standing hypothesis for the stream: the title's sound update (on the main
thread, skipped in re-simulated frames, its bookkeeping restored) writes the
next file chunk into the ring at a position and from a file offset it keeps
itself, not the ones the HLE hands back, so after a rollback it rewrites a
chunk the HLE has already consumed at the HLE's current write pointer and
the decoder reads garbage until the ring cycles. The way to settle it is an
`ATRAC_TRACE=1` run with rollbacks (every add with its ring and file
offsets) compared with the title's own counters in the restored memory --
not done. Rollback stays opt-in.

---

# Phase 9 -- the decisive trace (branch `rollback9`)

## 18. The stream corruption is rollback-made, and where it comes from

`ATRAC_TRACE=1` pair at RTT 50 (run t50, 634/421 rollbacks, no abort in
240 s) analysed with `tools/atrac_trace_analyze.py`:

- **Without rollbacks there are no decode errors at all**: 0 in the lockstep
  fight n5, in the no-rollback test run aref, in the neutral-input pair p0
  and in the coordinator's npcheck4. With rollbacks: 1 023 errors for 190
  rollbacks (a1, single instance, test mode), 281 for 23 (m1), 2 244 for
  634 (t50 host) -- 3 to 12 per rollback, in-process as much as online.
- The title's stream adds stay **perfectly sequential across every
  rollback**: 5 005 adds, file offsets continuing chunk after chunk, the
  single jump being the track's loop restart; the add right after a rollback
  continues at the expected file offset and ring position. So the HLE is not
  handed wrong *offsets*.
- The first decode error of each side comes a dozen adds after an ordinary
  1-2 frame rollback, with no offset anomaly before it.

So what is handed over is wrong *content*. The title streams the music from
its archive (T55DATA1.BIN) in 16 KB blocks into a staging buffer in the
sound heap (0x400DEFC0, outside the rollback state like the ring and the
stream object at 0x4000CF50), and its stream thread copies chunks of 688
bytes (one ATRAC3+ frame) from there to the ring at the write pointer the
HLE last gave it. The bookkeeping that decides *which* chunk comes next --
how much of the block has been fed, which block to request next -- is in the
rolled-back part of memory (it is not written by the stream thread: a
write-fault trace of two frames shows that thread touching nothing of the
state but the decoder's PCM output pages at 0x45C00000), so after a rollback
the reader is half rewound: traced single-instance runs (`runs/fs2`, `fs5`,
`arc1`, ATRAC_TRACE=1 + FS_READ_ALL=1) show it

- feeding the chunks of the rolled-back frames a second time (1-3 chunks
  back, exactly the rollback depth in feeds),
- feeding a block's tail from the staging buffer *after* the next block has
  replaced it there (135 of 136 bytes wrong), re-reading that next block
  (same archive offset, same bytes) and feeding its head a second time,
- or carrying on as if nothing happened, and only later, when its block
  counter catches up with the rewound one, feeding a whole block head again
  (3 168 bytes at the continuation position that are the image's bytes of
  2 752 earlier).

The HLE, not rewound, took all of that at face value: the byte count is the
only thing `cellAtracAddStreamData` carries, and the position those bytes
were taken from was its own -- a chunk of bytes fed again landed where the
*next* bytes belonged and the decoder read frames from the wrong bytes a
ring later. Patch 0024's drop of the first add after a rollback made it
worse when that add was a genuinely new chunk (the dropped bytes were gone
for good: the first decode error of t50 sits exactly in the chunk after the
drop).

Things tried and dropped on the way: rewinding the HLE's stream position
with the rollback (snapshot per commit, put back on restore -- consistent
with a title whose reader rewinds, wrong by the rollback depth for one that
carries on, which this title does half the time); following the title's own
copy of the last answer (the write pointer it holds names the ring place
*and* the file offset the answer stood for -- right for the ring position,
but the title's half-rewound reader does not feed what it says it feeds);
assembling the image by content (a chunk already in the image is a second
feed and goes where it is -- right for genuine second feeds, but a chunk of
digital silence matches a frame earlier and the position drifts, and the
block-tail garbage is in the image nowhere). Each cut the 600 decode errors
of a 75 s test-mode run (rollbacks every 30 frames) to 5-7, never to 0, and
two of them to several hundred in the wrong cases.

**The fix (patch 0028, `libs/codec/cellAtrac.c` + a hook in
`runtime/ppu/ppu_fs.cpp`): the library reads the stream from the archive
itself.** `cellFsRead` tells the library every read into guest memory
(buffer, archive offset, host path); the bytes the title feeds first (the
16 KB it sets the stream up with, then its first chunk) are found in those
blocks, which gives the stream's offset in the archive (two sightings must
agree and the archive must hold those bytes there, verified by reading it);
from then on the image is filled from the archive -- when the title's add
reaches past what the image holds, and on demand when the decoder needs a
frame the title has not fed yet. The title's adds only pace the stream: its
ring accounting is kept as before (write pointer followed, as the title's
copy of the last answer may be an earlier or a later one; a place no answer
named is a switch straddled by a rollback and is dropped), and what it
copies into the ring is not used (with ATRAC_TRACE=1 it is checked: after
the first rollback of a run it stays wrong for the rest of the stream, the
reader's bookkeeping and the library's position never meet again -- which no
longer matters). The ring fill is derived (what the title reads next less
what the decoder decodes next, a lap apart for a looping stream) instead of
counted, so a second feed does not fill the ring on paper. A stream fed
from memory, or one whose bytes no read is found for, is handled as before.

Result in test mode (`runs/arc1`, 75 s, rollbacks every 30 frames, 91
rollbacks): **0 decode errors** (593 with the series through 0024, same
test), gameplay hash unchanged; without rollbacks 0 title bytes differ from
the archive's over 654 adds (`runs/arc2`), so the mapping is exact. This is
the "music/stream position is output state, not match state" rule of
Tekken 6 Native Online's 2.2.4 release notes, taken to its end: the stream
is not rolled back, not restored, not re-fed -- it is read.

Full matches with the archive-backed stream alone (direct fight Asuka vs
Lili, stage 20, 2 rounds, KOs, delay 1, 3 % loss, 300 s; runs j0c/j50c/
j150c): 0 decode errors on all six instances, 174/68, 556/511 and 648/665
rollbacks -- and two leftovers, both at the first round's end:

- **RTT 0: the host stuck in fight phase 2** (the joiner went on to phase 3
  at 5371 and the rest of the match; 10 000 mismatching frames from there).
  The title's adds were still advancing the library's position, chunks fed
  again included, so after 174 rollbacks the position was a ring or more
  ahead of the decoder, the derived fill reported the ring full, the reader
  had no room to write and the title's round-end music switch waited for it
  for good. Fixed in 0028: the position follows the title's *reader* --
  bytes that are not the file's at the position they were asked for are
  looked for in the file nearby (one ring back, four ahead; the reader is
  behind after a rollback, re-feeding, or ahead, having gone on while a
  re-issued answer put the position back) and the position moves there;
  bytes found nowhere near (the wrong block) make no progress. The fill
  treats a position behind the decoder as an empty ring (the reader catches
  up) rather than as a lap ahead. Test mode: fill median 15 696, a transient
  two rings at most, 0 decode errors (`runs/arc5`).
- **RTT 50 and 150: the joiner's stream reader aborted** (the phase-7
  chain `0x3aabc0 <- 0x37f804 <- 0x37c4a0 <- 0x67354 <- 0x1eb6f8 <-
  0x1ebb08`) at ~5366, with 0 decode errors -- so the abort was never the
  decoder's doing. The log shows 1-frame rollbacks *inside* the lockstep
  window the phase change opened at 5348 (5350 -> 5349, 5365 -> 5364) and
  the archive opened four times for one music switch: the window waited for
  the peer's inputs up to f - 1 and still ran frame f on a prediction, the
  rollback re-ran the frame that had issued the switch, and the reader
  found a second switch in flight. Fixed in rb_net.cpp: in the warm-up and
  phase-change windows the boundary waits for the input of the frame about
  to run (`need = f + 1`), which with delay 1 the peer has sent a frame
  earlier -- the windows are lockstep now, not lockstep-but-one.

With those two (runs k0c/k50c/k150c, same setup): **RTT 50 a whole clean
match** -- 13 200 frames, 1 216 + 1 127 rollbacks, 0 mismatching frames, 0
decode errors, no abort, both peers through the same 10 phases; 0 decode
errors and no abort on the other four instances either. But RTT 0 had one
peer stuck in phase 2 again (this time the joiner, after 688 rollbacks; its
music stop was never issued -- no DeleteDecoder -- while its stream thread
went on feeding), and RTT 150 diverged at 5726, two frames before the
second round's phase 3 -> 4, in lockstep, with identical inputs. Both are
one thing: **the sound update's enable word is in the rollback state.**
The loop zeroes that word while it re-simulates (the title's sound update
is skipped in re-simulated frames, section 9) and puts the saved value back
afterwards -- but a frame committed *during* a re-simulation is committed
with the word at zero, and a later rollback to such a frame (a second
misprediction inside an earlier rollback's span, common with hundreds of
rollbacks) restores the zero; `sound_skip(true)` then saved that zero and
`sound_skip(false)` put the zero back, and the sound update was off for the
rest of the match: no round-end music stop (the phase machine waits for it:
k0c), and whatever the sound update does to the fight state at a round
start differed between the peers (k150c). Fixed in rb_hooks.cpp: the value
put back is the last *live* one; a restore that brings the word back as
zero is noted in the log.

With that (runs l0c/l50c/l150c): every instance through the whole match,
0 decode errors, no abort, the same phases on both peers (26/26, 26/26,
22/22), 54 + 25/51 + 67/63 such zero restores caught on the way -- and one
mismatching word from frame 5726 (RTT 0 and 50; 5826 at 150) to the end:
**0x1008F088, the stage id**, 0x13 on one peer and 0x1A on the other
(dumps of l0d, T5_NET_DESYNC_DUMP=1, nothing else differing in the 20
frames dumped). It is re-rolled from the C rand() -- the word a side thread
consumes at its own pace, out of both hashes since section 12 -- at the
second round's intro, and the fight does not use it (same phases, same
rounds, the same stage on screen). Left out of both gameplay hashes
(`kDefaultHashSkip`, `kGameSkip`) like the rand() word itself.

The next three (m0c/m50c/m150c, dumps on): 0 decode errors, no abort, the
same phases on both peers, and two more words of the same kind, set at
the *second match's* intro (frames 5826-5845, phase 10) and unchanged for
the rest of it: +0x830 of P2's fighter block, a pointer into 0x10670000
(0x10670AF0 on one peer, 0x106707F0 on the other; 0x1066F470 vs
0x1066F170 at RTT 150), and a unit vector at 0x100A0A10 ((0.17, -0.91,
0.37) vs (-0.41, -0.90, 0.13); in n0c a scale of (1, 1, 1) vs (0, 0, 0)
twenty words further, at 0x100A0A30: one record, 0x100A0A00+0x80 left out
whole) -- nothing else in the 20 frames dumped,
the fight on, the same rounds, the same phases. These never showed in the
phase 5-8 matches, which ran as far: those had the sound update silently
off on one or both peers after the first rollbacks (the zero restore
above), so whatever the sound side hands the fight at a match intro --
these look like a voice/effect handle and an emitter direction -- was
never handed over then. Both peers now run their sound update, each with
its own history (the effects of re-simulated frames are skipped on one
side and not the other), so sound handles stored in the fight state differ
from the first match intro after a rollback on. Left out of both hashes
with the five handle fields NETPLAY.md already lists. The right way, when
someone takes the sound side on, is Tekken 6 Native Online's: run the
sound update in re-simulated frames and start no sound twice.

One transient at RTT 150 (m150c, frame 5845, one dump of 20): a table of
pointers at 0x10091AB8 (fighter objects in the heap, 0x8D0 apart) filled
on one peer a frame before the other during the intro's loading --
asynchronous loading, lockstep window, no consequence seen.

## 19. Where phase 9 ends: the stream is solved, the sound side is not match state yet

Final pairs with everything above (o0c, o50c; same setup, dumps on):
0 decode errors, no abort, 0 "writable 0" stalls of the reader, the same
phases on both peers through both matches -- and still a sync-check
mismatch from the second match's intro (frame 5845) on: a table of twenty
heap pointers at 0x10091AB8 (objects 0x8D0 apart, in the fight block's
last page) filled on one peer and zero on the other for the rest of the
match (o0c; a one-frame transient of the same table in m150c), and in
o50c one more pointer into 0x10670000 at +0x1100 of P2's block (frame
5879, 0x1066FD70 vs 0x106713F0). Like the
stage re-roll, the handle and the effect record before it, it is set at
the intro by the side whose history now differs between the peers: with
the enable word fixed, both peers run the title's sound update, but each
skips it in its *own* re-simulated frames (section 9), so the sound side's
allocations (voices, handles, effect records) diverge from the first
rollback on, and whatever it hands the fight block at a match intro
differs. The fight does not read these back (identical phases, rounds and
positions through two matches in every run), but the detector cannot tell
that apart from a divergence, and three words were skipped on evidence
rather than on a layout.

So the online default **stays opt-in** (`T5_RB_MODE=net` offers rollback;
`offered_by_env` in rb_net.cpp), with the rule's "clean" unmet by the
detector though met by the fight. Two ways to finish, in order of
preference:

1. Tekken 6 Native Online's (release note 2.2.4): run the sound update in
   re-simulated frames too and have the sound side start no sound twice
   (a sound started in a frame that is re-simulated keeps playing, the
   re-simulation's start of the same sound is a no-op, nothing is cut).
   Then both peers' sound histories are the confirmed timeline and the
   words above agree. Needs the sound request path (0xAA200 -> 0x32819C
   and the bnusCore request areas at 0x10114000 / 0x40000000) understood
   well enough to key "the same sound".
2. Hash only the fight: the netplay/df owners of the fight-block layout
   take the sound side's fields (handles, the pointer table at +0x1AB8 of
   P2, the effect record at 0x100A0A00) out of `kDefaultHash`, as the five
   handle fields already are.

Everything else of the phase-9 brief is done: the ATRAC stream is read
from its archive (patch 0028), the j/k/l/m/n/o pairs at RTT 0/50/150 with
3 % loss and delay 1 ran 10 000-15 000 frames each with 0 decode errors
and no abort (18 instances), the round-end hang and the reader's abort are
gone, and the lockstep windows are lockstep.

---

# Phase 10 -- rollback becomes the online default (branch `rollback10`, patch 0029)

Code: `src/rollback/rb_sound.cpp` (new), `rb_detour.cpp` (new), `rb_net.cpp`,
`rb_state.cpp`, `rb_hooks.cpp`; `src/netplay/netplay_core.cpp` (rollback input
delay, neutral samples), `t5_hooks.cpp` (hash skips, loads, test gate);
runtime: `patches/ps3recomp/0029-rollback-pump-hold-atrac-mute.patch`. Tools:
`tools/rollback_net_test.py` (match series, audio, summary),
`tools/rollback_sound_compare.py` (new), `tools/rollback_audio_check.py`.
Runs: `build/rb3/netruns/<name>/`, single instances `build/rb3/runs/<name>/`.

## 20. The sound side in re-simulated frames (Tekken 6 Native Online's way)

**What the game does.** Every sound effect and voice of the fight starts
through the game's sound manager `0xAC594(group, id, channel, flags, pos,
handle_out)`, which passes it to the sound library's play core at once
(`0x32886C`/`0x328884` -> `0x3285B8`: one of 192 tracks is allocated and set
up). Once per frame the main loop's sound update (`0xAA1D4 -> 0xAA200`, the
enable word `0x10065B70`) runs the game-side bookkeeping (`0xAAA18`: the
sound-bank state machine, one step per frame; `0xAC424`; `0x9BFE8`) and then
the library's tick (`0x32819C`: sequencers, envelopes, 3D pan, commands to the
SPU core). The library's state (`0x40049210`, tracks from `0x400017C0`) lives in
the first heap chunk, which the rollback never restores. Stops (`0x328CC4`
group, `0x328D68` handle), a status query (`0x326C34`, via `0xAC814`) and the
music/bank calls (`0x3349B0`, `0x334628`, `0x33465C`, `0x3271DC`, `0x329158`,
`0x331E20`, `0x3270E0`) are the rest of what the game tells the library
during a match (call trace over every library and sound-manager entry point,
`T5_RB_CALLTRACE`, run ct1).

**Why phase 9's skip was wrong twice.** Zeroing the enable word in
re-simulated frames stopped the update, not the fight logic's play calls: a
re-simulated frame started its sounds a second time (trace snd1: 13 starts in
re-simulated frames, the same ids as the first run, the library allocating new
tracks for them). And the update's game-side half (bank state machine,
handles it writes back) skipped the re-simulated frames on one peer and ran
them live on the other. Same test, both modes (cost_skip / cost_resim, 8-frame
rollbacks every 30 frames through a whole match): skip **6 gameplay-hash
mismatches in 840** re-simulated boundaries, resim **0 in 1088**.

**What runs now (`T5_RB_SOUND=resim`, the default).** The sound update runs in
re-simulated frames like in any frame; the library sees every sound once:

- every play call is logged per frame (group, channel, flags, id for
  channel-less sounds, the handle it wrote back, its return value). A rollback
  pass re-simulates frames g..f-1; a play call in it that finds an entry no
  run of the pass has matched yet -- in its own frame, else in the nearest
  frame of the pass (the corrected timeline moved it by a frame or two) -- is
  not passed on: the sound keeps playing and the handle is written back. A
  play call with no entry is the corrected timeline's and starts now (late by
  the rollback depth). An entry no run of the pass asked for again belongs to
  the mispredicted timeline and plays on: nothing is cut;
- voices (channel >= 0) match without their id: the game picks a voice
  variation, and whether to say anything at all, from the C `rand()`, which a
  side thread consumes at its own pace (section 12) -- a re-simulated frame
  may ask for another variation, or for a voice its first run did not have;
- stops are never applied in re-simulated frames (a repeat was done already,
  a new one would cut a sound); music/bank calls a run of the pass made
  already are not repeated (a second music switch made the stream reader
  abort in phase 7); the status query gets the first run's answer for the same
  handle;
- the library tick is skipped in re-simulated frames: it runs once per
  displayed frame, like the SPU core, so tracks never advance faster.

The calls are reached by entry detours of the lifted functions
(`rb_detour.cpp`: a 5-byte jmp at the host entry to a relay, the moved
prologue in a trampoline; only the push / sub rsp / mov / vmovaps prologues
clang-cl emits are accepted, anything else is refused and the mode falls back
to skip). The game-DLL build publishes the lifted table after static init, so
there the hooks go in when the loop starts. One mistake on the way: matching
`0x329158` on r3 and r4, where r4 is no argument but whatever the previous call
left; a skipped previous call left a different r4, the bank call went through
a second time, failed (`0x80000020`), and "Fight!" came a frame later on one
peer (r50a, desync at 5778). The table now has each function's real arity
from its call sites.

**Cost.** Main-thread cycles per re-simulated frame (test mode, same match,
`T5_RB_RESIM=8` every 30 frames): resim median 18.0 M (p10 6.0, p90 38.9),
skip 24.2 M (p10 7.5, p90 45.0), a normal frame 64-65 M. The expensive part,
the library tick, is skipped in both: running the sound side in re-simulated
frames costs nothing measurable.

## 21. The words left out of the hash, with evidence

Phase 9's last flagged word, `0x100911D0` (+0x830 of the third 0x8D0 block),
differed again from match 2's intro in the first three-match pair (p50a). Its
writer (write-fault trace, `T5_RB_WFT_AT`, run wft2) is the character
animation update (`0x27F904 <- 0x2887E8 <- 0x264B28`): an address of an object
taken from a pool at a match intro. A **pure lockstep pair without rollback**
(e1lock: `T5_RB_MODE=off` both, RTT 50, delay 3, the same three matches)
showed the same word differing from match 2's intro (`0x106704F0` vs
`0x106701F0`) and nothing else -- so it is not rollback-made, and not match
state: the slot depends on what else came and went (the stage's effects run
on a side thread on stage 24). Left out of both hashes together with the same
field of the fourth block (`0x10091AA0`) and the twenty heap pointers at
`0x10091AB8` (o0c, m150c: the same kind of pool addresses).
With the sound side fixed nothing else differed in any later pair: the other
phase-9 words (stage re-roll, `+0x830` of P1/P2, the effect record) stay
skipped as before; no new word was needed.

Also found on the way: after a re-simulation with the draw cut, ~210 pages of
render bookkeeping (linked lists at `0x1042B000..0x10434FFF` among them)
differ from the uninterrupted run (now listed in full by the test mode's
diff). None of it is hashed; a pair with the cut off (e2nocut) stayed in sync
as well, so the cut is not what moves the pool addresses.

## 22. Lockstep windows: what they cost, what replaces them

The 600-frame lockstep window after every fight-phase change (phase 6) and
the 420-frame warm-up made the game crawl at high latency: lockstep with
input delay 1 waits one-way latency per frame (~13 fps at RTT 150). p50a (RTT
50): 31 of 32 s of stall time came from those windows, 47 phase changes kept
most of the match in them. Now:

- **Phase windows: off** (`T5_RB_NET_PHASE_LOCK`, default 0). With the sound
  side running in re-simulated frames, KO, round end and match end
  re-simulate like any frame (s0/s150/r50b/F*/G*: 43-45 phase changes per
  three-match session, 0 mismatches).
- **The intro takes no input** (`T5_RB_NET_INTRO`, on with direct fight). From
  the match-start barrier to "Fight!" the phase word is 7..12 (17 = fighting,
  select screens 1..5). A frame whose input is decided at a boundary in those
  phases gets neutral input: this side sends neutral without reading the
  devices (taps stay latched), and predicts neutral for the peer's frames
  decided in the same phases. The intro has no mispredictions, no rollback
  reaches into it, and its loads (stage, characters, voice banks: frames 7,
  38, 56, 92, 217 of match 1) need no lockstep.
- **Loads outside the intro** (the match end) lock 60 frames
  (`T5_RB_NET_LOAD_LOCK`): `drain_workers` tells the loop when it had to wait
  for the loader threads.
- **Warm-up**: 0 with direct fight (the intro rule covers it), 420 otherwise.
- A bug: a phase change set `g_lock_until = f + lock`, shortening a running
  warm-up or load window; the host of q150 rolled back across match 2's loads
  and came out two phases apart. Windows only ever extend now.

## 23. A race with the vblank handler (patch 0029)

r150a's host died in match 2 after ~700 rollbacks: garbage indirect calls
from `0x34CA64` (the vblank callback-list walk) on the thread that ran the
guest vblank handler (`0x34BC08`), then an SPU halt and silence. The handler
runs inside `ppu_gcm_pump` -- on the ticker thread or at any guest thread's HLE
call -- and walks the callback list at `0x106D4BE0` with its lock word, while
the main thread copies or restores those pages at the boundary. Patch 0029
adds `cellGcm_pump_hold(on, timeout_ms)` (`libs/video/cellGcmSys.c`): it takes
the pump's own entry guard (waiting up to the timeout for a handler in flight)
so handlers stay pending while `state_commit`, `state_rollback` and
`state_init` copy guest memory; the next pump delivers them. Not seen again in
the ~20 000 rollbacks of the later pairs. Patch 0029 also has `ATRAC_MUTE=1`
(tests: streams decoded and paced, the PCM handed to the title is silence) so
sound effects can be measured without the music.

## 24. Time sync, input delay, the default

**Time sync both ways.** Per 300-frame window both peers sleep when ahead
(s150: host 421 sleeps / 15 s, joiner 279 / 7.5 s over 430 s; advantage per
window between -0.8 and +0.6 frames except one window at +-2.4), and both roll
back (1738 / 1583). Phase 9's one-sided picture (o0c: the host +2.3 frames
ahead all match, 28 sleeps per window, the joiner 0 rollbacks) is gone: the
windows that made one side wait every frame are gone.

**Rollback input delay.** The lobby picks the session's input delay for the
lockstep (`proto.suggest_delay`: one-way latency + jitter, at least 2 frames,
6 at RTT 150). Once both peers offer rollback they switch to
min(that, `T5_RB_NET_DELAY`), default 2 frames, the host's value carried in
the HELLO flags (bits 8-15) so both agree; frames already decided keep their
inputs (`np::rb_apply_delay`, at the loop's start).

**The default.** `offered_by_env`: with `T5_NET_MODE` set and `T5_RB_MODE`
unset, rollback is offered when the match starts through direct fight
(`T5_NET_START=external`, what the lobby does); `T5_RB_MODE=net` forces the
offer, `T5_RB_MODE=off` (or `lockstep`) withholds it. A peer that does not
offer (an older build, `T5_RB_MODE=off`) gets the lockstep on both sides.
The rollback hooks switch `PS3_VM_WRITE_WATCH=1` on before `main()` when they
will offer (through the OS environment: the runtime's getenv cache keeps a
miss), and a session whose guest memory has no write watch does not offer.

**Results and speed under rollback.** The result file now carries the
deciding frame's gameplay hash once that frame is final (`rb::net::final_hash`;
the lobby compares the two players' hashes when their reports disagree) and
this PC's speed (`fps`): the loop feeds the lockstep's speed accounting with
every live frame and the time it waited for the peer, so the `speed:` lines
the launcher reads for the lag check are there again. A match end seen on a
predicted frame that a rollback then undoes cancels the pending result.

## 25. Results

All pairs: two instances on this PC through `tools/rollback_net_test.py`'s
proxy, +-5 ms jitter, 3 % loss, direct fight Asuka vs Lili on stage 20, then
Lili vs Dragunov on stage 24 twice (match 2 and the rematch, `T5_FIGHT_FILE`),
2 rounds to win, the ranked driver's attacks in fights only
(`T5_NET_SCRIPT_FIGHT=1`), desync dumps on. "Desync" is each match's result
file (mismatching frames from its sync point); every run also had
`sync check ... in sync` through its last full window.

**The default configuration** (no `T5_RB_MODE`, no `PS3_VM_WRITE_WATCH`, the
lobby's lockstep delay for the RTT -> rollback delay 2):

| run | layout | RTT | frames | rollbacks host / join | re-simulated | desync per match | decode errors | abort / hang | stall s host / join |
|---|---|---|---|---|---|---|---|---|---|
| F0 | exe | 0 | 18 900 | 67 / 43 | 115 / 60 | 0, 0, 0 | 0 | none | 2.7 / 0.8 |
| F50 | exe | 50 | 18 900 | 422 / 288 | 498 / 355 | 0, 0, 0 | 0 | none | 2.4 / 1.6 |
| F150 | exe | 150 | 18 900 | 1637 / 1601 | 3082 / 2866 | 0, 0, 0 | 0 | none | 6.8 / 4.3 |
| G0 | game DLL | 0 | 18 900 | 17 / 41 | 34 / 43 | 0, 0, 0 | 0 | none | 1.5 / 0.04 |
| G50 | game DLL | 50 | 18 900 | 271 / 128 | 339 / 179 | 0, 0, 0 | 0 | none | 2.8 / 1.0 |
| G150 | game DLL | 150 | 18 900 | 1574 / 1440 | 2323 / 2049 | 0, 0, 0 | 0 | none | 3.8 / 4.5 |

F* ran the developer exe before the result/speed changes of section 24; G*
are the final code in the release layout (`T5DR_GAME_DLL=ON`), the three pairs
at once with two other agents' instances on the machine (31-32 fps): each
match's result file has the same gameplay `hash` on both PCs. G150's sound:
0 doubled starts, 134 / 127 re-simulated starts kept from the first run, 19 /
16 started late (1-4 frames), 7 / 1 mispredicted sounds played on, 0 stops
applied in re-simulated frames.

**Stress, input delay 1** (`T5_RB_MODE=net`, before the default flip; more and
deeper rollbacks):

| run | RTT | frames | rollbacks host / join | re-simulated | desync per match | decode errors | abort / hang |
|---|---|---|---|---|---|---|---|
| s0 | 0 | 17 100 | 451 / 197 | 543 / 266 | 0, 0, 0 | 0 | none |
| r50b | 50 | 17 100 | 1207 / 1219 | 1975 / 1946 | 0, 0, (0 through 16 799) | 0 | none |
| s150 | 150 | 17 100 | 1738 / 1583 | 5433 / 4596 | 0, 0, 0 | 0 | none |

Stall time per match is the match-start barrier (the peer still loading the
fight) plus the prediction window at RTT 150: 0.3-2.5 s per match, none of it
in lockstep windows during fights.

**Lockstep fallback** (fallback: host default, joiner `T5_RB_MODE=off` as an
older build): the host offered, the joiner did not, both ran "lockstep starts:
frame 0, delay 3", in sync, identical result files.

**Release layout** (`-DT5DR_GAME_DLL=ON` + `t5dr_game.dll` from
`tools/build_game_dll.py`): the sound hooks go in when the loop starts
("lifted code not loaded yet" at static init); dll150 (RTT 150, delay 1, one
match): 533 / 530 rollbacks, in sync, results with the same `hash` on both
PCs.

**Sound** (RTT 150, delay 1, one match each, `ATRAC_MUTE=1`; request-level
counts from `tools/rollback_sound_compare.py` against a no-rollback reference
pair with the same scripts):

| run | doubled starts | re-simulated starts kept from a first run | late starts (frames) | mispredicted, played on | stops applied in re-simulated frames |
|---|---|---|---|---|---|
| aud_rb (resim) host / join | 0 / 0 | 64 / 80 | 12 / 8 (median 1-2, max 6) | 2 / 0 | 0 |
| aud_skip (phase 9) host / join | 55 / 89 | -- | -- | 52 / 90 | -- |
| nv_rb (voices off) host / join | 0 / 0 | 57 / 68 | 0 / 2 | 1 / 1 | 0 |
| nv_skip (voices off) | 37 / 42 by frame 2 750, then hung at the round end (skip without the phase windows) |

Sound effects started on the same frame as in the reference: 250 of 254 and
253 of 258 (nv_rb; the rest a frame off). The audio-level onset count of the
recordings (`tools/rollback_audio_check.py --match 1`) cannot resolve single
hits: host and join of the same no-rollback reference -- the same sounds --
differ by 24 of ~130 onsets, because how many transients the detector
separates depends on how far apart in wall time the sounds land, which
follows the frame rate; nv_rb lies inside that spread (129 and 148 against
148 and 124). Music during the fights (music on; mus_ref/mus_rb under load,
q_ref/q_150 on a quieter machine): 0 silent 20 ms windows in every run;
level dips of >= 40 ms more than 30 dB below the median: 0 / 0 with and 0 / 0
without rollbacks on the quieter machine, 1-3 vs 0-1 under heavy load (six
or more game instances and a compile on the machine). Decode errors: 0 in
every run.

**Cost** (release layout; two other agents' game instances on the 16-core
machine; one match):

| | fps (match average) | displayed frame p50 / p99 | rollbacks | re-simulated frames |
|---|---|---|---|---|
| q_ref: no rollback (RTT 0, delay 6) | 52.1 / 53.1 | 17 ms / 34-46 ms | 0 | 0 |
| q_150: default at RTT 150 | 47.2 / 47.9 | 17 ms / 50-51 ms | 523 / 507 | 1 359 / 1 349 (30 %) |
| ab_ref / ab_150, side by side (same load, 4 instances) | 33.6-34.0 / 31.7-32.1 | 32 / 33 ms; 48-52 / 54-66 ms | 0 / 367 | 0 / 604 |

Per re-simulated frame 18 M main-thread cycles (median, test mode), a normal
fight frame 64 M. Side by side RTT 150 runs 5 % slower than no rollback:
stalls and time-sync sleeps are ~3 % of the time, the rest is the
re-simulation. No slow motion beyond that: the lockstep crawl (one-way latency
per frame in every window) is gone, the typical frame stays at 17 ms.

## What is left

- Sound: voices are a random draw on each PC (the C `rand()` a side thread
  consumes), so the two players may hear different grunts; that was so in the
  lockstep too.
- Cost: a rollback-heavy RTT 150 match averages ~47 fps on this machine with
  others running (p99 51 ms); a faster sim or fewer re-simulated frames (a
  smarter prediction than "last input repeats") would bring it to 60. (Done
  differently in the latency branch, sections 26-29: 60.0 fps median window,
  p99 24 ms, on 8 logical processors.)
- `T5_RB_SOUND=skip` (the phase-9 behaviour) is kept for comparison only:
  without the old phase windows it hangs at a round end.
- The draw cut leaves ~210 pages of render bookkeeping different after a
  re-simulation; none of it is hashed and no run showed a consequence.

## Sessions in a persistent game (fight-polish, 2026-10-17)

The launcher's persistent game (T5_CTL_DIR, docs/DIRECTFIGHT.md "Persistent
game") plays every opponent in one process, a netplay session each. For the
rollback loop that means:

- `offered_by_env()` offers rollback in a persistent game (every session is a
  direct fight; T5_RB_MODE=off keeps the lockstep), `rb_hooks.cpp` registers
  its hooks and the write watch for it at boot, and the intro rule is on.
- `rb::net::session_reset()` (called by the netplay hooks when a session ends
  or the next begins): an unfinished re-simulation is abandoned (bypass, cut
  and sound skip off), the loop's history and statistics go, `state_reset()`
  drops the undo logs and brings the shadow up to date (frames count from 0
  again in the next session); `start()` then takes over as in a first match.
- The end of a fight's loading is a scene barrier in rollback mode too: a
  game that has played ends its loading frames apart from a fresh one (its
  caches), and without the barrier the two fought 2 frames apart (4,228
  mismatching frames, build/dp run rb_ps1). It lies in the intro, where both
  sides send neutral input, so no rollback crosses it. (Since reset-fix the
  barrier is the first frame showing phase 11..17; the first ring reset used
  before is "Fight!", after the intros -- see the next section.)
- In direct fight the frames of the game mode's start, loading and intros
  (phase 0..12) push a fixed hash, and `scene_change(nf)` also skips frame nf
  (the side that did not jump hashed it before the barrier's RNG reseed).
- `kGameSkip` leaves out two camera-relative float blocks (0x10099770,
  0x10099960, 0x128 bytes each) and 0x10090708 / 0x10090FD8: they differ
  between two PCs for exactly 100 frames about 20 s into a match, the fight
  unchanged (on main as well; docs/DIRECTFIGHT.md "Known transient mismatches").
  Branch cross-cpu widened it to the whole two camera blocks (0x10099730 and
  0x10099920, 0x1F0 bytes each, and 8 bytes at each counter) and added the
  point 0x1008FFF0: from a KO camera they differed for 21 frames, identical
  builds too -- 1 of 4 Bryan-vs-Steve lockstep runs, 7 of 9 rollback runs at
  RTT 50, 0 of 2 with `T5_RB_CUT=none` (the draw the cut skips keeps that
  camera state, so the cut makes it more likely).

Result: a persistent game against a freshly started one, then two more new
sessions, under rollback: 5 of 5 matches confirmed, 0 mismatching frames, up to
19 rollbacks per match (build/dp run rb_ps5).

## Session ends and the intro rule's first frames (reset-fix, 2026-10-17)

Release dry run 0.1.6 (persistent game, docs/DIRECTFIGHT.md "After a session
ends"): one player's fight never finished loading. The rollback loop had rolled
it back 9 frames, to frame 2 -- into the first frames of the fight's loading.
The peer's input for frame 2 was a press (the harness's pad file; a player
holding a button at the fight start does the same): it was sampled at lockstep
frame 0, the session's first boundary, where the game mode has only just set
the phase word to 2 -- outside the intro rule's 7..12, so it went out, and the
host had predicted neutral. The rule now counts every phase up to 12 as intro
while the mode manager is in the game mode (the game mode sets 0, then 2, then
7; `intro_phase(p, game_mode)`, `t5_df_game_mode()`); the flag is recorded per
boundary like the phase (`g_intro_flag`), and lockstep frame 0 samples neutral
under the same rule (`np::begin_frame(..., neutral_local)`). Select screens
(mode 6, phases 0-5) are untouched: a rematch's select is driven through the
exchanged input.

The end-of-loading barrier was "the first ring reset after a fight start",
which is the "Fight!" frame (phase 17), not the end of the loading: a played
game that reached the intros 2 frames after a fresh one ran its Fight! frame on
a different random state and clock, before the barrier's reseed. Asuka vs Law
on stage 25 desynced that way every time (rollback and lockstep, on main too);
the barrier is now the first boundary showing phase 11..17
(`t5_hooks.cpp` `fight_loaded_now()`), and the intros run in step.

`session_reset()` also puts back what `start()` changed in the game -- the
present's min-vblanks word 0x106D4D98, zeroed so re-simulated frames do not wait
for a vblank -- and calls `sound_reset()`: a session that ended inside a
re-simulation left the sound hooks "re-simulating" (play calls matched against
stale entries, the library tick skipped, stops dropped) for as long as the game
ran without a session.

---

# Latency branch -- rollback at RTT 150, input delay by ping (branch `latency`, patch 0034)

Code: `src/rollback/rb_net.cpp` (early rollback, time sync, statistics),
`rb_state.cpp` (ring out of the state, restore once per page, early
snapshot), `rb_icall.cpp` (direct-call cut), `rb_hooks.cpp` (flip-status
hook); `src/netplay/netplay_core.cpp` (input delay by round trip, protocol
v3), `t5_hooks.cpp` (early boundary, tick wait); runtime:
`patches/ps3recomp/0034-latency.patch` (present at translation, display lock,
latency probe, `cellGcm_xlat_presented`). Runs: `build/lat/netruns/<name>/`.

## 26. Where a re-simulated frame's time went, and what was cut

**The GCM command ring was in the rollback state.** A restore put earlier
frames' commands back into the ring between the FIFO walker's `get` and the
title's next flush, and the walker translated them again -- old flips
included. Latency probe of a pair at RTT 150 (L150, `PS3_LATENCY_LOG`): the
title asked for 5 601 flips, the walker reached 7 128 and presented ~1 400
stale frames, 730 of them while a re-simulation ran: CPU on the walker
thread, and pictures from frames already shown. The ring
(0x40100000+0x400000) is now neither saved nor restored, and the title's
CellGcmContextData (begin/end/current/callback at 0x0F800000) keeps its live
value across a restore (`kKeepWords`), so the write position only moves
forward and a re-simulated frame's commands are appended. After it (L150b):
5 594 flips asked for, 5 594 walked, 5 596 presents; ~150 fewer pages per
snapshot.

**Direct-call cut.** The stack profile of re-simulated frames in the netplay
loop (`T5_RB_NET_SAMPLE=N`: the first N rollbacks, "S" lines in
`rb_frames.log`) still had ~14 % in a render pass the scene nodes open and
close with direct calls (`0x31F778` begins it on the graphics object --
lwmutex, `0x383FC8` -- and sets the byte at `[r2-0x1044]`; `0x31F7A8` ends it
only when that byte is set). `0x31F778` is now an entry detour that returns at
once in re-simulated frames while the match is fought (phase 17, match not
decided); the end then does nothing by itself. Main-thread cycles per
re-simulated frame in test mode (same match, 3-frame rollbacks every 12
frames, quiet machine): 27.5 M without, 13.9 M with the cut; 0 gameplay-hash
mismatches in 1 419 re-simulated boundaries. Cutting the end as well broke the
pairing when the cut switched on or off between the two calls, and only the
begin is needed. Tried and left out: four more render calls (`0x15AD9C`,
`0x15B01C`, `0x1549FC`, `0x1548C0`, ~15 %) -- they are function *tails* the
function finder split off (no `stdu`, they pop a frame a predecessor pushed):
skipping one leaves the guest stack pointer off by its frame, and two pairs
crashed through a garbage pointer within a minute. A detour target must be a
whole function. Phase gate: run d1 showed 2 mismatching frames ~860 frames
after the deciding KO (result-screen records at 0x1008E690..C0, written
under the pass); none since the gate.

**Snapshots.** The netplay loop no longer keeps the full-state page hash (only
the test mode reads it; `T5_RB_NET_PAGEHASH=1` brings it back): a snapshot of
a fight frame went from ~0.9 to ~0.6 ms, and with the ring out to ~0.37 ms
(`rbnet: snapshots:` lines: write watch 0.20 ms, page copies 0.17 ms, pages
per range). A restore applies the logs oldest first and copies each page once
(its first entry is its content at the target boundary): a 3-frame rollback
restored ~1 800 page copies, now ~700 (1.26 ms per rollback in L150c).

## 27. Early rollback: the re-simulation in the time the frame waits

A frame's main thread is idle from the moment its commands are translated
until the vblank tick that completes its flip (with the display lock the tick
comes `lead` before the display's vblank). That window is ~6.7 ms (median, 8
logical processors). The netplay loop now uses it:

1. When the walker has reached the flip and the ticker has presented it
   (`cellGcm_xlat_presented`, patch 0034: vertex jobs drained, nothing on the
   GPU side reads guest memory any more), the main thread's flip-status poll
   (`rb_hooks.cpp h_cellGcmGetFlipStatus`) takes the next boundary's snapshot
   (`early_commit`; the boundary later adds the vblank handler's few pages to
   the same log) and checks the inputs that have arrived.
2. If a misprediction is known, the poll reports the flip done; the title goes
   on to its frame semaphore, where the hooks run the boundary at once
   (`early_pending`) instead of after the wait: restore and re-simulation run
   in the idle time.
3. At the end of the re-simulation (or right away if nothing was wrong after
   all) the boundary waits for the tick through the title's own semaphore wait
   (`frame_tick_wait`), then does the live part as before: the local input is
   read at the tick, the remote inputs polled again (a misprediction found now
   is rolled back after the tick, as before). A tick that came while the
   re-simulation ran was swallowed like every post during one; it is counted
   (`early_tick_posted`) and the live frame starts at once.

In L150c 98 % of the rollbacks ran early (`rbnet: early rollbacks ... 33 of
34`). Early start to tick wait (restore + re-simulation, mostly 3 frames):
median 9.4 ms, p90 12.1 ms; the window from the present to the tick: median
6.75 ms. So a typical early rollback still ends ~4.8 ms after the tick (p90
8.4 ms) and the live frame (9.6 ms from its start to translated) mostly makes
its vblank; the deepest ones do not. `T5_RB_NET_EARLY=0` turns it off.

## 28. Time sync without false alarms

The advantage estimate was the mean of `mine - theirs` over 20 frames; a lost
packet makes one side's estimate jump by a frame or two for a few frames, and
the mean then called for sleeps the next window had to undo. A median of these
whole frames was worse (it rounds half-frame advantages up: 128-143 sleeps per
side per match). It is now the mean of the middle 60 % (trimmed): 14-17 sleeps
per side per match at RTT 150 with 3 % loss, against 20-60 before and 130-140
with the median. Each sleep is a repeated picture on the screen.

Tried and dropped: sending each frame's inputs a second time ~4 ms after the
first (in the frame's wait for its vblank), against the deepest rollbacks that
a lost packet makes at 3 % loss -- two interleaved pairs each way (RN1/RN2 vs
RD1/RD2): the same depth histogram, the same p99 (24-25.5 ms).

## 29. Results

`tools/rollback_net_test.py --fight 26,33,20,2 --rtt 150 --jitter 5 --loss 3
--delay 6 --mode1 default --mode2 default --matches 1 --cpus1 0xFF0000 --cpus2
0xFF000000`: two games on this PC through the proxy, each on 8 logical
processors of its own (4 cores / 8 threads of the second CCD), one match of two
rounds with the attack scripts (582 / 560 rollbacks, the same in every run:
the scripts are deterministic). "main" is main 5337f7f (series 0001-0033), the
online default; "latency" is this branch, the online default (input delay 2 at
this ping either way). Runs interleaved main / latency; "busy" = processors in
use on the whole PC during the run, both games included (~7.5 = nothing else).

| run | build | busy | fps per game (whole match) | 300-frame windows, median | displayed frame p50 / p99 (ms) | time-sync sleeps (host / joiner) | sync |
|---|---|---|---|---|---|---|---|
| RB1 | main | 15.1 | 49.7 / 50.4 | 53.6 | 17.0 / 50.5 | 50 / 63 | 0 mismatching, same result hash |
| RA1 | latency (without 0x2AAD50) | 13.6 | 56.7 / 57.8 | 58.8 | 17.0 / 31.0, 27.5 | 18 / 12 | same |
| RB2 | main | 13.8 | 51.8 / 52.8 | 53.6 | 17.0 / 50.0 | 49 / 59 | same |
| RA2 | latency (without 0x2AAD50) | 12.0 | 57.0 / 58.1 | 58.8 | 17.0 / 28.5, 27.5 | 21 / 23 | same |
| RB3 | main | 16.9 | 51.5 / 52.4 | 53.6 | 17.0 / 50.0, 50.5 | 46 / 60 | same |
| RF1 | latency | 14.3 | 57.0 / 58.1 | 58.8 | 17.0 / 27.0, 26.5 | 16 / 14 | same |
| RB4 | main | 7.5 | 52.6 / 53.4 | 54.5 | 17.0 / 50.0 | 39 / 48 | same |
| RF2 | latency | 7.5 | 57.6 / 58.7 | **60.0** | 17.0 / **24.0** | 10 / 9 | same |
| RC1, RC2 | latency | 7.0, 8.7 | 57.7 / 58.8, 57.6 / 58.7 | **60.0** | 17.0 / 24.0, 23.5 | 13 / 8, 15 / 7 | same |

The whole-match fps includes the match start (the joiner loading, ~1.4 s of
stall) and the intros. On the quiet PC the median 300-frame window is 60.0
fps (target >= 59.5: met); the 99th percentile of the displayed frame time is
24 ms (target <= 20 ms: not met -- about 1 % of frames still take two
refreshes, the deepest rollbacks, section 27). Before, every 300-frame window
of the fight was at 53.6-54.5 fps with a p99 of 50 ms. Sound: 0 decode errors,
no abort, no hang in any run.

Correctness: every pair above in sync with the same result hash on both PCs;
the input-delay pairs (docs/NETPLAY.md "Input delay": RTT 0/50/150, settings
equal / different) and lockstep pairs at RTT 0/50/150 (K0/K50/K150) too;
test mode (in-process, 3-frame rollbacks every 12 frames through a whole match
with KOs): 0 gameplay-hash mismatches in 1 404-1 419 re-simulated boundaries
with the cut (d2, d5). The two crashes of section 26 were the tail cut, not
seen again in 20+ pairs since.

## 30. The hang at the end of a match under heavy rollback: a semaphore token the restore did not give back

What was seen (reset-fix, `tools/reset_cycle_test.py --stutter 80`: the
opponent suspended for 80 ms every 0.2-0.6 s): a match played to its end, the
driver's START skip taken, the game asks for the select mode (mode 4, next 6)
and never gets there; the screen fades to black, the fight music stops, the
select data is never read, and after 60 s `stuck_check` ends the game (exit
6). On this branch before the fix: 3 of the first 4 match ends of a cycle run
hung (`build/lat/runs/rc1`), always on S, the side whose opponent stutters --
the side that rolls back.

How it was found (`build/lat/runs/tr1`, `bz1`, `fd1`; the tracing builds are
not in the tree):

1. A call trace (`T5_RB_CALLTRACE`; every function of the game mode and the
   mode manager, 0x4F000-0x56000 and 0x25B000-0x25E000) of S and of its
   opponent through the same match: after the game's own mode request
   (0x25DA54(6)) both stop running the game mode's task and run one more task
   (0x10624980) every frame. On the opponent the mode switch (0x25DBD0, cur :=
   next) comes one frame later; on S never.
2. The mode manager (0x25E6AC) switches only when the query 0x272E84 on that
   task says "done": it sets the task's +0x58 = 2 and +0x5C = 1 and runs its
   subtree; every task of the class 0x10084768 (exec 0x274310) whose state
   (+0x48) is not 7 or 10 clears +0x5C.
3. An entry detour on 0x274310 that logged the busy tasks during the query:
   on the opponent one task busy for a few frames (states 4, 5, 6); on S task
   0x10628E80 in state 3 for good. State 3 (0x27279C) waits while its read
   request (task +0x7C, 0x1009FF68) has status 1 -- a request of the game's
   async reader (ZsAread).
4. A trace of the reader's functions: the main thread's reader service
   (0x9A784, once per frame) starts a request by posting the reader's request
   semaphore (service object 0x1009FE28 +0) and marks itself busy (+8 = 1);
   the reader thread reads and posts the completion semaphore (+4); a later
   frame's service takes that token with a trywait (0x9A884, the game's only
   trywait) and completes the request (0x9A4F4). On S: frame 226 took the
   token and completed a read; a rollback at frame 234 re-simulated from 226;
   the restored service was busy again, its trywait found the semaphore empty
   (CELL_EBUSY), and so on every frame until the game was ended.

Why: a kernel semaphore's count is not guest memory. A restore put the
service and the request back as they were before the token was taken, but
not the token. The loader task then waits forever; in the fight that shows
nothing (it loads in the background), at the match's end the game mode cannot
finish while a task of its scene is busy. It needs a rollback to a boundary
between the reader's post and the service's trywait -- frequent when the
opponent stutters (every frame predicted, rollbacks of 2-6 frames all match
long), rare otherwise (the reset-fix runs: 1 in 10 matches).

Fix:

- `src/rollback/rb_net.cpp`: the completion semaphore's count is part of the
  rollback state: saved at every boundary (`reader_sem_save`, the id read from
  0x1009FE2C) and put back with a restore (`reader_sem_restore`, via
  `t5_sem_count` / `t5_sem_set_count` in `t5_hooks.cpp`; only while nobody
  waits on it -- the main thread only ever trywaits). The session's last line
  counts the tokens given back ("reader tokens given back N").
- `src/netplay/t5_hooks.cpp`: the loaders (ZsAread, the decoder) are drained
  before the boundary's snapshot, not after it, so the reader has posted
  whatever it will post when the count (and the memory) is saved; the loop is
  told about the load after the boundary as before (`load_seen`). Drained
  first alone was not enough (`build/lat/runs/fx1`: still 3 hangs in 3).

Proof: `reset_cycle_test.py --stutter 80 --cycles 12` (`build/lat/runs/fx2`):
12 cycles, 11 passed, 0 hangs: S played 13 matches to their end under the
stutter and left every one for the next (no "STUCK"); in 3 of its sessions a
restore gave a token back (the match c002 that hung in every run before the
fix is one of them). The one failed cycle (5) is not the hang: S aborted at
the reset after its 7th match in NU::File::RequestManager (a request whose
virtual call went to `abort`, 0x374150 -> 0x3C3AAC, just after an archive
open got fd 6 -- fds 4 and 5 were still open); the same abort, at the same
place, is in the reset-fix agent's run on main (`build/rs/runs/stut_rb1`,
run2). Before the fix the same test hung at 3 of the first 4 match ends
(`rc1`), and with the drain-order change alone at 3 of 3 (`fx1`).

Rollback pairs with the fix (`rollback_net_test.py`, the section 29 command):
RTT 150 (RH1) 57.4 / 58.7 fps per match, 300-frame window median 60.0, p99
25 / 24 ms; RTT 0 (RH2) 57.7 / 59.0, median 60.0; both 0 mismatching frames
and the same result hash on both PCs; lockstep at RTT 50 (KH50L) in sync
too. These builds are on main with the reset-fix merge (section 29's were
before it), and the same numbers came out. The scripted match now ends 2-0
for P1 after 4456 frames instead of 0-2 for P2 after 4402: that comes with
the merge (the end of the fight's loading is the sync point, at phase 11,
where the RNGs are reseeded) -- the first build after the rebase, before this
fix, plays the same (RI3).

## 31. Rematches and long sessions (rematch-fix, 2026-10-18)

The owner's first two-PC sessions (0.1.9, 1.0.0) showed rematches that never
started, a frozen picture, desyncs with no rollback before them and a quit
counted as a desync. docs/DIRECTFIGHT.md "Rematches between two real PCs"
has the hang (the rematch's start test looked at P1's record) and the closed
window (a game that ran on without it); the rollback side:

**The GCM ring's last word, and the drain thread's recycle.** cellGcmInit's
context ended exactly at the ring's end (0x40500000), so a ring filled to the
brim had the buffer-full callback write its JUMP back to begin at 0x40500000
-- the first word of the title's own heap header after the ring in the same
IO allocation (a T5_DF_WATCH run: 0x405000C0 -> 0x20000000 at frame 1447 of
an offline fight, 18 such JUMPs in a 6-match run). And "current == end" was
taken for an overrun, which switched on the walker's own recycle for good:
from then on the drain thread rewound current, put and get to begin whenever
current came near the end -- under a title still writing there, with a frame
not yet flushed. The walker then parsed the previous lap's leftovers at
begin: "FIFO JUMP to unmapped IO 0x1F7FFFD0 (word 0x3F7FFFD1)" 0x58-0x64
bytes into the ring, a resync, the frame's flip skipped and the 1-second
flip valve ("queued flip never reached by the FIFO walker"): a frozen picture
and a stalled opponent, about once in six matches under rollback (runs f2,
g2, h1; the new put log, `[FIFOPUT]`, caught it in g3: put=0 cur=0x404FF094
get=0 -- the drain thread's recycle -- then garbage at 0x58). Patch 0035:
the context's end leaves the last word for the JUMP, only a real overrun
(current past end) turns the drain thread's recycle on, and a resync that
steps over a queued flip completes it like a walked one (it used to wait for
the valve). Since then no walker resync or stall in any run (rows below).

**The post-match input is a rule.** From the boundary where the game shows
the match decided (game mode, phase 17, the decided byte 0x1008EBD5 rising
during the fight -- not the last match's byte, which stays set ~230 frames
into a rematch's fight) both PCs send and predict the same input: neutral,
START for 3 frames every 20 from 40 frames after the decision until the game
asks for the select mode -- what the direct-fight driver did by hand. Before,
the driver's START presses and the last mashed input before its hold were
predicted as "the last input repeats": rollbacks all through the KO, the
replay skip and the result screen, where the game loads. `post-match frames
by rule` in the `rbnet:` lines (94-144 per match end). `T5_RB_NET_POSTMATCH=0`
turns it off.

**A rematch's select screen runs in lockstep.** Both drivers press their own
player's cursor there through the exchanged input and the game loads
portraits and models for each move; the select screen is a few seconds and
needs no prediction. `select screen frames in lockstep` (~250 per rematch);
`T5_RB_NET_SELECT_LOCK=0` turns it off. At a round trip up to ~2 x the input
delay in frames it runs at full speed (this PC: rematch command to FIGHT
START 1.8-4.3 s, as before).

**Still open: the file request thread.** Every file open, read and close of
the title is done by one worker, NU::File::RequestManager (thread 2: all 105
opens of an offline run, `FS_CALLER=1` now logs the thread), for requests of
the sound streamer, the draw and the main thread. A rollback across a frame
that queued or completed a request leaves the worker and the restored
request list disagreeing: a file handle stays open (the archive's opens move
from fd 3/4 to 5, 6, 7 over a session) and sooner or later the worker calls
through a stale request (`abort() is called from ... 0x374150`, exit code 1)
or reads the archive at a stale position (`inflate failed`, then the fight's
particle thread never joins). With both players mashing (fight_flow_test
--mash, other agents' games loading the PC), about once in 8 matches of one
session; never in lockstep. Tried and dropped: a journal of the fd table
(opens, closes and positions taken back by a restore) -- wrong, the worker's
operations are not re-run frames, and taking them back desynced the next
fight within seconds; keeping 0x10750000..0x10753000 (the manager's object
and lists) out of the rollback state -- those pages hold pad state too
(desync at frame 229 of match 1, 0x10099F38); keeping only the manager's
page out -- the abort after 2 matches. What it needs: the worker drained
(idle, nothing queued) before every snapshot and restore -- its semaphore is
shared with the sound streamer, which made a per-frame drain cost seconds in
the lockstep era -- or the requests of a frame that may be re-run held back
until the frame is final.

Runs (this PC, two games, persistent game, `tools/fight_flow_test.py`; other
agents' games running too; "FIFO" = walker resyncs / flip valve lines in all
game logs):

| run | mode | flow | matches fought | in sync, confirmed | FIFO | end |
|---|---|---|---|---|---|---|
| e2b (before the fix) | rollback | N R, --same-chars --skew 1.5 | 1 of 2 | 1 | 0 / 0 | rematch never reached FIGHT START on either side (150 s) |
| f1 | rollback | N R R, same, --mash | 3 | 3 | 0 / 0 | all reached the fight |
| f2 | rollback | N R, window closed in match 2, N R | 4 | 3 + the closed one (quit / peer_quit, exit 7) | 1 / 1 (before the ring fix) | -- |
| R1 | rollback, joiner 240 Hz | N R R, skew 1.5 random | 9 | 9 | 0 / 0 | -- |
| L1 | lockstep | N N R, skew 1.2 alt | 9 | 9 | 0 / 0 | -- |
| L2 | lockstep, joiner 240 Hz | N N R R, skew 2.0, P1 first | 9 | 9 | 0 / 0 | -- |
| R2 | rollback | N N R R, skew 2.0, P1 first | 9 | 8 | 0 / 0 | match 9: request-thread abort (fd 6) |
| P1 | rollback, post-match rule + select lockstep | same | 8 | 7 | 0 / 0 | match 8: request-thread abort (fd 5) |
| P2 | rollback, --stutter 60 | N R R R | 6 | 5 | 0 / 0 | match 6: `inflate failed`, host hung in a thread join |

| FRB (as committed) | rollback, joiner 240 Hz, --mash-gap 20 | N N R R, skew 2.0, P1 first | 7 | 6 | 0 / 0 | match 7: request-thread abort (fd 5) |
| FLS (as committed) | lockstep | N N R R, skew 1.5 alt, --mash | 12 | 12 | 0 / 0 | -- |
| FCR (as committed) | rollback | N R, P2 closes in match 2, P1 in match 4 | 5 | 3 + 2 closed (exit 7, quit / peer_quit, 0.3-2.7 s) | 0 / 0 | the matches after each close: new sessions against a fresh game, in sync |

Every rematch in these runs reached FIGHT START on both sides, 1.8-5.7 s
after its command; every match that was played to its end was confirmed with
the same winner and state hash and 0 mismatching frames (rollback and
lockstep); no walker resync or flip stall with the committed build.

Offline, one game limited to a few logical processors (affinity +
`PS3_CPUS`, muted, below-normal priority; a second player's 1.0.0 log, 6
cores, had eight "recycled the title's own ring" lines, then flip stalls):
Kazuya vs Heihachi, 100 s of fight each --

| build | CPUs | "recycled the title's own ring" | heap header 0x40500000 overwritten | flip stalls / resyncs | silent 10 ms blocks in the fight |
|---|---|---|---|---|---|
| main (series to 0034) | 6 | 8 (the print cap) | -- (not watched) | 0 / 0 | 0 of 9 926 |
| 0035 | 6 | 0 | -- | 0 / 0 | 0 of 10 040 |
| main | 4 | 8 | yes, frame 2203: 0x405000C0 -> 0x20000000 | 0 / 0 | 0 of 10 034 |
| 0035 | 4 | 0 | no | 0 / 0 | 0 of 10 044 |
| main | 2 | 8 | yes | 0 / 0 | 175 of 12 833 (~30 fps: too few CPUs) |
| 0035 | 2 | 0 | no | 0 / 0 | 97 of 12 830 (the same) |

The race that turns a drain-thread recycle into a stall did not come up in
these single offline fights (it did in the online runs above, about once in
six matches); its precondition, the recycle, is gone.

## 32. The abort in the file manager: memory of threads that run beside the frame (branch rollback-crash)

What was seen (section 30's fx2, reset-fix's stut_rb1): under `reset_cycle_test.py
--stutter 80`, the side that rolls back aborts after several matches in the
NU::File request manager's thread (`abort()` from 0x3C3AAC = `__cxa_pure_virtual`,
called by the manager's loop 0x37408C at 0x37414C: a queued request whose object
is already destroyed); just before, archive opens get fds 5 and 6 instead of 3
and 4. Here it came back in 4-5 cycles of every traced run (k2, k3).

**The tracer** (`src/rollback/rb_ktrace.cpp`, `T5_RB_KTRACE=1|2|3`, one
`rb_ktrace_<pid>.log` per process in the working directory): every event tagged
with the frame running and L(ive)/R(e-simulated). Level 1: the title's opens and
closes (entry detours on the cellFsOpen/Close import stubs -- `rb_detour.cpp`
now moves the stubs' `mov ecx, imm32` prologue -- and on the title's file
device, 0x38C90C / 0x38C798), lv2 object creates and destroys, sys_memory,
rollbacks, sessions. Level 2: reads and seeks, every request put into the file
manager's list (0x374438: thread, slot, id, call chain) and every call of a
request's process method (0x37414C, through the indirect-call hook), the
loader's inflate (0x671E4), the sound library's heap calls. Level 3: per
boundary, the main thread's wake/take syscalls of the frame that just ran.
Answers for the brief's suspects, three runs: the main thread opens and closes
no file and creates or destroys no lv2 object in a re-simulated frame (0 events
in k1-k3); it starts a load there almost never (the reader's post: 0 times, its
trywait: once -- section 30's case). What runs while the main thread
re-simulates is other threads' work: the file manager and the music stream
thread.

**The file manager.** Its thread (`NU::File::RequestManager`, tid 2) serves two
clients: the async reader ZsAread (open, seek, read, close of one archive entry
per request -- drained at every boundary) and the music stream thread
`CnuSound2Thread` (object 0x106CECD0: open/seek/read/close of the track at any
time, keeping the handle at +0x13C). The main thread never calls it. Its whole
state is guest memory in the rollback state: the file device 0x10750488 with 16
file objects at 0x107507D0 (stride 0x58, host fd at +0x18), the manager
0x10751A00 (lwmutex +8, semaphore +0x40, request ids +0x48, 16 request slots of
0x40 from +0x4C, the request list +0x44C, the slot free list +0x540) and its
node pool up to 0x10752034. A restore put those pages back to a boundary that
the manager's thread, its clients, their kernel semaphores and the host's open
files had all left behind. In k3 the slot ring stopped rotating (every request
in slot 0x10751A4C from one session on), then a ZsAread Read and Close found no
free slot -- handle 0x7B and fd 4 were never closed, the retry got fd 5 --, and
at the next session t8's Open and t16's Seek were handed the same slot at the
same moment; the manager processed the Open, the destructor reset the slot's
vtable, the Seek's node was still queued: pure virtual call, abort. Write-fault
trace w1 (`T5_RB_WFT_ADDRS=1`, every written word by guest thread and function)
confirms the ownership: in 0x10750000..0x10751FFF only the manager's thread,
ZsAread and the music thread write; in 0x10752000 the manager's node pool ends at
0x10752033 and the rest is the main thread's (lwmutexes, draw handshake).

**The music stream object** 0x106CECD0 (fields up to +0x5B4) is the stream
thread's: it writes the file handle and the read positions; the main thread only
through the library's music calls 0x334628 / 0x3349B0, which the sound hooks
never repeat in a re-simulated frame; bnusCoreUpdateThread writes +0x428..+0x437
and +0x480/+0x494. A restore gave the thread back a handle it had closed and lost
the one it held.

Fix 1 (`rb_state.cpp`): 0x10750000..0x10751FFF are `kExclude` (never saved or
restored), and a new byte-exact `kKeepLive` list -- bytes a restore writes
around, never over, not even for a moment as a save-and-rewrite would --
holds the stream object 0x106CECD0+0x5B8 and the node pool tail
0x10752000+0x40. They are masked out of the page hash.

Section 31 (rematch-fix, at the same time) tried two neighbours of this and
dropped them, for reasons this one avoids: 0x10750000..0x10753000 out of the
state desynced match 1 (pad state, 0x10099F38) -- the third page is the main
thread's from 0x10752088 on (the keyread tick's lwmutexes, the draw
handshake: write-fault trace w1), only its first 0x34 bytes are the manager's,
hence the byte-exact range; and the manager's page alone left the file
device's page (the file objects with their fds and positions) restored, and
the abort came back after two matches. Its fd journal (opens, closes and
positions taken back by a restore) closed files the worker had opened for the
music thread, which no re-simulated frame opens again.

**The second abort.** With fix 1 the file-manager abort was gone (fx1: 32
cycles, no fd above 4, no abort), but runs on the other schedule (fx3, from
cycle 5) and the opponent of i1 aborted elsewhere: `inflate failed. error
no:-3` (the loader thread's zlib inflate of an archive entry, 0x1EB58C ->
0x671E4), the music stream ends, then `abort()` from 0x3AABC0 in the C
library's `free()` (0x3AAA40), called by the ATRAC3+ decoder's teardown
0x349AA4 at 0x349EB4. The same sequence is in the rematch agent's run
`build/rm/runs/h1` (main + its branch, without this work): older than this fix.
The C library heap (malloc 0x3AB2C8, free 0x3AAA40) keeps its state at
0x10753EF0 -- rolled back -- and its first arena at 0x40000000 (excluded since
phase 1 as "sound") and a second one at 0x45C00000 (rolled back). The sound
library allocates from it through callbacks (0x10088F0C/F10, copied at init
to 0x10088F88/F8C): at init on the main thread, and when a track starts or
stops on the stream thread, the ATRAC3+ decoder thread and bnusCoreUpdateThread
(trace a2: ~1 MB live, 79 blocks; during a fight nothing else uses the heap, at
a KO, round end or match end these threads do). A restore rewound the free
lists under blocks that stayed in use, a block went out twice -- a loader's
compressed data overwritten (the inflate error), and the decoder's free()
found a broken chunk.

Fix 2 (`rb_sndheap.cpp`): every malloc whose caller is the sound library's code
(0x326000..0x34B000; callers seen 0x32938C..0x34A944) comes from a pool at guest
0x7F000000 (8 MB; nothing maps there -- sys_memory ends at 0x50000000, the HLE
heap at 0x58000000, cellAudio 2 MB per port from 0x58000000, sys_vm
0x60000000..0x70000000), bookkept in host memory; a free of a pool block, from
any caller, goes back to it (entry detours on malloc and free). The C library
heap is then only the main thread's and the drained loaders', whose work a
restore and its re-simulation undo and redo together. The sound library is
output state like the rest of the sound side (section 20): not rewound, not
repeated. `T5_RB_SNDHEAP=0` turns it off; the session's last `rbnet:` lines
give the pool's use (`sound heap: 1051 KB in use (peak 1051 KB) in 79 blocks`).
Where the library's blocks live changes the layout of the C library heap, and
that layout reaches the hashed state: a lockstep pair with the pool on one PC
only (host default, joiner `T5_RB_MODE=off`) desynced from the first fight frame
(MIX50: 4 233 mismatching frames; the same pair with `T5_RB_SNDHEAP=0` on the
host: 0). So the pool is installed in every online session, rollback or
lockstep, from the netplay hooks' cellPadInit (before the library's first
allocation, in the exe and the game-DLL build alike), and in the rollback test
modes; offline the game is unchanged. The final hash of a match changes with it
(the same inputs end with another hash than without the pool), equally on both
PCs.

No runtime change was needed. The host's open files follow the title's file
manager, which is no longer rewound, so the descriptor table needs no journal:
a restore takes back no open and no close, because no open or close ever
belonged to a re-simulated frame -- they are the file manager's thread's, done
for the reader (whose requests the boundary completes) and for the music thread
(whose state is now kept live). A journal that closed the files "opened in a
re-run frame" on a restore would close the music thread's track under it.
(Seen on the way: `runtime/ppu/ppu_fs.cpp` hands descriptor slots out and back
without a lock; two opens at the same moment on two threads could share an fd.
Not this bug's cause -- the file manager serialises the title's opens -- and
left alone.)

`tools/reset_cycle_test.py` now fails a cycle on the title's `abort()` in either
game (before, an abort of O counted as "O log: clean"), keeps the end of a
replaced game's log for the check, and has `--below-normal` / `--mute` for a PC
in use; `fight_flow_test.py`'s control file write retries a replace Windows
refuses (a run died on it after 15 cycles). `T5_NET_DESYNC_DUMP` writes up to 20
dumps per session (a deliberately desynced session used to take them all).

**Proof.** `reset_cycle_test.py --stutter 80` (O suspended 80 ms every 0.2-0.6 s:
S predicts and rolls back all match long), one S process per run, every log of
both games checked for `abort()`, `[CRASH]`, `inflate failed` and archive opens
at fd 5 or above. Schedule 1 = cycles from 1, schedule 5 = from cycle 5 (other
fighters and stages; the inflate abort only showed there).

| run | build | schedule, cycles | match ends (S) | S rollbacks | aborts (S / O) | opens at fd >= 5 | result |
|---|---|---|---|---|---|---|---|
| k2, k3 | tracer, no fix | 1, 5 + 4 | 4 + 3 | 1 346 + 984 | file manager: 1 + 1 / 0 | 13 + 24 | S died in cycle 5 / 4 |
| fx1 | fix 1 | 1, 32 | 33 | 10 447 | 0 / 0 | 0 | 29 pass, 3 "no_peer" (a fresh O took 25-30 s to boot under load, past the 20 s connect timeout) |
| fx3, i1 | fix 1 | 5, 8 + 15 | 9 + 13 | 2 396 + 3 920 | inflate + free(): 2 + 1 / 0 + 1 | 0 | S died twice in fx3, once in i1; O once |
| F5 + F6 | fixes 1 + 2 | 1 + 5, 22 + 15 | 24 + 17 | 6 351 + 5 407 | 0 / 0 | 0 | 36 pass; 1 cycle with a 3-frame transient (below) |
| F9 | final | 5, 21 (stopped at cycle 26 for a pause; to finish) | 24 | 7228 | 0 / 0 | 0 | 21 pass |

F5 and F6 were stopped early (F5 when the owner started playing on the PC, F6
by the control-file race above); F9 ran muted at below-normal priority.

Pairs (`rollback_net_test.py`, section 29's command, a whole match each). Before
the rebase: RTT 150 default/default (RB150c) 556 rollbacks on the joiner, 0
mismatching frames, the same result hash on both PCs; lockstep RTT 50 (LS50b,
both `T5_RB_MODE=off`) and the fallback (MIX50b, host default, joiner
`T5_RB_MODE=off`) 0 mismatching frames, the same hash. On the final build
(fixes 1-4, rebased on main d7fc019): AUD_P (RTT 150 default/default, recorded)
540 rollbacks on the joiner, 0 mismatching, the same hash; LS50c and MIX50c 0
mismatching, the same hash. Smoke quick: boot_menu, arcade_fight, title_twice
PASS; vs_two_pads and practice failed once with 13 other game instances and 7
compilers on the PC (a black select-screen shot; the hang check firing during
the test's own stop) and passed on the rerun (only fps/audio WARN under load;
offline the change is inert). tests/ 358 OK; lobby/tests 302, one ranked driver
test failed once under load and passed alone.

**Sound with the pool** (the music stream and the sound library's blocks
outside the rollback state; `--audio`, sound on, RTT 150, one match each,
`tools/rollback_audio_check.py --match 1`):

| run | rollbacks host / joiner | silent gaps >= 20 ms host / joiner | onsets per minute | re-triggers per minute | loudness | decode errors |
|---|---|---|---|---|---|---|
| AUD_P: pool (default) | 20 / 540 | 2 (0.04 s) / 0 | 51.1 / 55.4 | 2.8 / 1.8 | -22.5 / -22.0 dBFS | 0 |
| AUD_N: `T5_RB_SNDHEAP=0` | 285 / 524 | 1 (0.02 s) / 0 | 47.2 / 54.4 | 2.8 / 3.7 | -21.9 / -21.7 dBFS | 0 |

The same within the spread section 25 measured between two recordings of one
reference: the music streams without hiccups through rollbacks with the pool,
and nothing in the sound changes with it.

**Not explained: a 3-frame transient after a deliberately desynced session.** In
F5 (cycle 15) and the overloaded first try F2 (cycle 7), the match after the
`desync` cycle (the two games had fought on different stages) mismatched on
frames 225-227 -- "Fight!", the first frames the check compares after the
intros -- and agreed from 228 on, with the same final hash; both runs had the
sound heap. It did not come back in four replays of the same schedule (D1, D3,
D4, and F6's cycle 7) nor in fx1's four such matches without the pool; the
dumps of those runs were used up by the desynced session before (fixed now).
It is the "two games with different histories" kind (CLAUDE.md's open item b);
a dump of the next occurrence will name the words.

**The present hang (fix 3).** On the rebased build the rematch agent's scenario
(`fight_flow_test.py --flow persistent --pattern NNRR --mash --stutter 60 --skew
2.0`) hung the host twice: FF1 in match 15, FF2 in match 1. The window stays, its
log stops, the peer waits for input. `build/cr/hangwatch.py` asks a quiet game's
debug console (`PS3_DEBUG=dbg.cmd`) for `threads` and the managers' memory: the
main thread spins at 0x35C014, the geometry manager's thread is parked in its
semaphore wait, the draw manager waits for its wake counter. The present
(0x383C9C) starts with 0x35BF6C: it queues a request on
NU::Draw::Geometry::RequestManager (thread 5, object 0x10742880, loop 0x35B888)
and spins until the manager's busy count (+8) is 0. The manager is woken by one
semaphore post (id at +0x50) per queued request (0x35BE6C), adds 1 to +8 while
it works through its queue, posts "done" (+0x58), takes the 1 away and parks.
The spin is no barrier: the thread may not have woken yet when the main thread
looks, and the draw manager's sync right after (0x357714) hands it more work --
so at the boundary it is sometimes still working (FF3: 235 of 87 670 boundaries
on the host, 1 949 of 108 622 on the joiner, which re-simulates more; about
1 ms each until it parks, the longest 65 ms). A snapshot then holds +8 = 1; a
rollback to that frame writes the 1 back after the thread has parked; every
later wake adds and removes its own 1, so +8 never reaches 0 again, and the
next present spins for good. The same rule as the file manager: a thread that
runs beside the frame. Fix: before every rollback boundary (snapshot and
restore, live and re-simulated) the netplay hooks wait until the geometry
manager is parked with no post pending -- as the loaders are drained
(`t5_hooks.cpp side_drain`, at most 2 s; `T5_RB_SIDE_DRAIN=0` counts without
waiting). The `side drain:` line every 600 frames gives how often it was busy
and the wait. NU::Draw::RequestManager (thread 4, object 0x1074BE80) is idle at
the boundary by construction (the present's 0x357714 waits for its wake counter
at +0xA8 to drop to 0); its request list may already hold the next frame's
first requests, queued and not taken.

| run | build | flow | matches | result | rollbacks (host / joiner) |
|---|---|---|---|---|---|
| FF1 | fixes 1 + 2, rebased | persistent NNRR, mash, stutter 60, skew 2 s | 14 of 32 | host hung in match 15 | -- |
| FF2 | same, hang watcher | same | 0 of 32 | host hung in match 1 (the dump above) | -- |
| FF3 | + fix 3 | same | **32 of 32** | 0 mismatching frames, the same result hash on both PCs in every match, no hang, no abort, no fd above 4 | 3 981 / 9 577 |

FF3 ran muted at below-normal priority next to 3-7 other game instances (fps
11-40 in the busiest stretch).

**A whole-match desync after a title visit (fix 4, direct fight, not rollback).**
On the rebased build the first cycle of `reset_cycle_test.py --start-cycle 5`
(F11) desynced the next match from its first compared frame (226) to its end,
1 505 frames, while both games had played the same inputs. The dumps
(`tools/rb_desync_diff.py`) differ in 38 words of 0x1009xxxx, every pair
0x100000 apart: heap pointers. A persistent game visits the title for a new
opponent; the title starts the savedata autosave thread, which takes a 5 MB
memory container and 1 MB blocks from it; right after start VS the select
mode takes its 65 MB block (0x4120000) from the same sys_memory window. Which
comes first depends on when the autosave's host thread gets to run: on S the
select block went first (0x45C00000, the autosave's block then at
0x49D20000), on O the autosave's (0x45C00000, the select block at 0x45D00000):
the whole fight heap 1 MB apart, every pointer in the fight state with it. On
an idle PC the autosave finishes within the title's 30 frames (F9 passed this
cycle); under load (F11: the host thread started 30 frames after its
creation) it does not. Fix (`df_fight.cpp` Ph::Title): start VS waits until no
`savedata_autosave` thread is alive (at most 10 s), then the boot state goes
back and start VS runs as before. A desync of this kind needs no rollback at
all; it fits the "desync in match 2 with no rollback before it" reports
(CLAUDE.md), not proven.

**A predicted KO that a rollback took back (fix 5).** The e2e agent's
net_rollback scenario at RTT 250 (run g2, match m23fd877921c5) ended without a
result: both games voided it as "no_report". E2E Net1's game saw the KO on its
live frame -- `MATCH OVER ... winner P1`, `pads held neutral (the match is
decided)` -- and the next rollback took it back (`the match end seen at frame
2285 was rolled back -- no result yet`): with the peer's real input the hit did
not land. Net2 never saw a KO. The netplay result watch handled that
(`watch_match` cancels its pending result), the direct-fight driver did not:
it had gone to its "over" phase on the predicted KO for good, held its pads and,
from 40 frames on, pressed START every 20 frames to skip the replay -- in a
fight that went on. Under rollback the post-match rule decides the inputs only
while the game state shows the match decided, so with no KO in the state the
held pads and the START presses (START pauses a VS fight) went into the input
stream of both PCs; Net1's own attack script had stopped too (it runs only in
the driver's "fight" phase). The match did not end in the next 2 400 frames,
the launcher gave up, and the next match's reset waited 60 s in the game mode
and ended the game (exit 6). (No per-frame input log of that run exists; the
pause is inferred from the presses and the game staying in its fight phase.) The driver's acts on a match end are
irreversible, so under rollback it now acts only once the end is final
(`t5_netplay_match_end_final`, `df_fight.cpp` Ph::Fight): this side's match
watch has it and every frame up to it ran on confirmed input
(`rb::net::state_final`) -- or its result is out already. The frames after the
KO do not count (they cannot change it, and the post-match rule decides them);
"the whole live state final" would never hold at RTT 250, where the last 10-15
frames always rest on predictions (a first version of the fix waited for that
and only got out of its "fight" phase when the game left the game mode). It
costs a few frames between the KO and the driver's hold; the rule covers them.
Lockstep: unchanged (final at once). The log says `the match end rests on
predicted input -- acted on once confirmed` / `the match end is confirmed`.

**Not explained: a select screen that never loads, under heavy load.** Twice on
the rebased build with 9-13 game instances on the PC (F10 and F12, both in
cycle 5, both right after a title visit), S's select mode stayed in its loading
for good: mode 6, phase word 1, no file opened, every loader parked (ZsAread,
the file manager, the decoder), the music thread not started; the game itself
ran at full rate. No rollback had happened in that process (session 1: 0
rollbacks), so the restore is not involved. In F12 the reset's stuck check
ended the game after 60 s (exit 6: the launcher starts a fresh one); in F10 the
"fight" had come while the game sat in neutral, which had no such check, and
it waited there for good. Mitigation (`df_fight.cpp stuck_check`): a "fight"
pending in neutral counts too, from the moment the command came. Not seen in
F9 (21 cycles, pre-rebase) nor in F13 on the final build; what the select mode
waits for in phase 1 is not known yet -- `build/cr/stuckwatch.py` dumps the
threads of a game whose "fight" command is followed by no state change (with
`PS3_DEBUG`).

## What is left

- The file request thread under rollback (sections 30-31): fixed in section 32,
  with the sound library's heap, the geometry manager's drain (the present
  hang) and the title autosave's heap race; open there: a 3-frame transient at
  "Fight!" in the match after a deliberately desynced session.
- Rollbacks of 4+ frames at RTT 150 still end after the tick and cost their
  vblank. Further cuts need whole functions (see the tails above), or an early
  start at the flush instead of after the present, which needs the render
  inputs of the frame being translated (skinned vertices) kept out of the
  restore.
- The metric in the `rbnet:` lines ("displayed frame times") is boundary to
  boundary; with early rollbacks a late live start makes one long and one short
  interval without a missed vblank. `tools/latency_test.py`'s display cadence
  (presents against the display's vblank grid) is the closer measure.
- Other memory of threads that run beside the frame is still in the rollback
  state and was not seen to break anything: the rest of the sound library's
  ELF data (TOC globals 0x106CDE80..0x106CECCC and 0x106D1B50..0x106D4838,
  written by its tick on live frames only and by its threads), the "particle"
  thread (stage effects, the rand() consumer of section 12), TNUD::ASync, the
  draw request manager (idle at the boundary; the geometry manager is drained
  there since section 32's fix 3). `T5_RB_KTRACE` and
  `T5_RB_WFT_ADDRS=1` show who writes what; the rule from section 32 applies:
  a thread the boundary does not drain must not have its memory restored.
