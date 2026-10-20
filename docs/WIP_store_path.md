# WIP: cheaper guest store path (branch `store-path-114`, ps3recomp patch 0069)

Paused on the owner's instruction (2026-10-20 ~19:15). State of the work:

## The change (in patch 0069 + `tools/gamedll/t5dr_game_dll.c`)

- Every inline guest store checked the SPU reservation bitmap twice (before and
  after the store), each time: load the import slot of `vm_coh_bitmap`, load the
  pointer, NULL test, line/byte index, byte load, `and 7`, `bt`, branch -- 13.2
  instructions per check (132,898 check sequences in `t5dr_game.dll`).
- New (`ppu_recomp.h` `PPU_COH_LOCAL`, the lifter's header): the runtime hands
  the DLL the bitmap's address once with the gates (`ppu_game_set_coh`,
  `vm_coh_bm_k`, DLL-local, treated as constant); the check tests the whole
  bitmap BYTE of the line's 1 KB block (`bm[ea >> 10] != 0`): 4.9 instructions,
  no NULL test (the bitmap is all zero until the first mark). Both checks stay
  (store, then re-check: the barrier protocol of `spu_coh_reserve` is unchanged).
  A block hit goes out of line (`vm_write*`), where the runtime does the exact
  protocol on the line's own bit, so a store to a reserved line's seven
  neighbours only takes the call.
- Why it stays correct (to be written up in RENDER_PERF): the block byte is the
  same memory byte the old check read, and "byte != 0" is a superset of "bit
  set" (bits are never cleared): the post-store re-check sees the mark whenever
  the old one did (same byte, same barrier argument); an extra post-store notify
  acts only on reservations of the store's own line (none on a free line); the
  pre-check sends to the exact runtime protocol everything the old one did, plus
  the neighbours (exact protocol there = plain store + exact re-check, as the old
  inline path). stwcx/`reserve_addr`, the SPU side and DMA paths are untouched.
  The pre-existing first-reservation window (a PPU thread stalled between its
  check and its store across a whole GETLLAR..PUTLLC) is unchanged, not widened.
- Switches: `PS3_COH_LOCAL=0` (runtime: no bitmap handed out, the DLL keeps its
  store window shut -- every lifted store out of line, the runtime's exact
  path); compile with `/DPPU_NO_COH_LOCAL` for exactly the 1.1.4 inline code.
  An old runtime with a new DLL also gets every store out of line (window shut
  until `ppu_game_set_coh`); a new runtime with an old DLL works as before.

## Measured (this PC, pool stage unless noted)

- Static: DLL 9.00 M -> 7.86 M instructions (-12.7 %), 39.2 -> 35.2 MB.
- Micro-benchmark (`build/storepath/micro`, TSC cycles per store, 4 workloads:
  struct fill / byte copy / scattered RMW / float stores): 1.1.4 check
  5.2 / 7.3 / 14.6 / 5.8; 0069 2.4 / 4.8 / 11.6 / 3.0; no check at all
  1.5 / 2.7 / 10.9 / 3.0. (Local pointer + byte bit: 3.9 / 6.4 / 13.8 / 4.6;
  local + 32-bit word: 3.3 / 5.7 / 12.8 / 3.7; a byte per line: = 0069.)
- How often (counting build, fight window): main thread 538 k inline stores and
  626 k inline loads per frame; draw thread 441 k / 389 k. Stores on a reserved
  line 45 per frame (0.008 %), on a reserved block 57 (so +12 out-of-line calls
  per frame), post-store re-check hits 0, stores/loads outside the window 0.
  A "no reservation active" fast path would not help: the bitmap is armed from
  boot (SPURS) and the check is now one load.
- thread_sampler (one run each, not paired): share of the DLL's samples on the
  check instructions: main 21.0 % -> 8.8 %, draw thread 48.1 % -> 24.3 %.
- PGO: 15 of 22,796 profiled functions out of date (`vm_st_reserved`, one per
  chunk; it has no branch left) -> no retrain needed.
- Paired rotated bench (`build/storepath/bench`, 2 builds on 0x550000 /
  0x55000000, 4 cores each, polite; stopped after 6 rounds): game thread CPU
  per frame 0.89-0.92x, game part 0.86-0.97x, draw thread 0.75-0.90x, game CPU
  0.95-0.99x, B better in every round; fps 60 either way on this PC.

## Open / next steps

1. Re-run `tools/storepath_diff.py` (hot functions x 20,000 inputs; all 23,059
   x 300 armed, x 100 `--unarmed`; `--march none`). The first all-functions run
   showed "mem DIFFERENT, trace same" only in runs stopped at the event limit:
   a harness artifact (the inline store's event was recorded after the store,
   the out-of-line one before) -- fixed in the tool, not re-run yet. The 4-hot-
   function run: 0 differences; `--self-check` (new check blinded) is caught.
2. Build and run `runtime/ppu/tests/test_storepath_race.c` (written, never
   compiled): threads against the real `spu_coherency.c`; variants new / old /
   break_post / break_pre; needs its driver `tools/test_ppu_storepath.py`
   (not written yet).
3. Finish the paired bench (6 rounds x 4 conditions), estimate.py for the
   i5-7300HQ; CODE_VERSION 6 in build_game.py (+ tests/test_regpromo.py's
   check); `T5DR_COH_LOCAL=0` in build_game_dll.py; RENDER_PERF section,
   CHANGELOG line; rollback/lockstep pairs incl. cross_build_pair vs
   integration-114; smoke quick.
4. Possible extra, not started: the load gate's `ea != vm_refpoll_k` compare is
   needed only for 32-bit loads (only `vm_read32` polls the ref word).

Local evidence: `build/storepath/` (bin_base = integration-114 rebuilt, bin_new,
bin_stats counting build, runs/, bench/, ana/, micro/).
