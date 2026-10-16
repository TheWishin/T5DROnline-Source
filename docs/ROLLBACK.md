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
