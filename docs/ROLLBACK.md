# Rollback netcode for the native Tekken 5 DR build -- feasibility, findings, design

Branch `rollback`, code in `src/rollback/`, runtime change in
`patches/ps3recomp/0008-rollback.patch`. All guest addresses are for
NPUB30009 v01.00 and this runtime's memory map (`PS3_VM_WRITE_WATCH=1`).

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
