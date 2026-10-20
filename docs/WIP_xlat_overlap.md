# WIP: xlat-overlap (patch 0067, for 1.1.4) -- paused 2026-10-20 on the owner's instruction

Branch `xlat-overlap` in build/xlatov/repo (clone of integration-113 caa7158). Runtime tree: build/xlatov/ps3recomp
(int113 series + WIP commits); exes in build/xlatov/bin (base.exe = series to 0065, xo11.exe = this patch);
logs, runs and scripts in build/xlatov/{logs,runs,scripts,pairs,syncruns}.

## Done
- Measured where the game and the translation serialize (latency-log split + PS3_SCHED_TRACE, 4 LPs + slow_core,
  pool stage): game part 12 ms, translation 4.5, flip reached -> release 0.6 (2.5 for late frames: the present sat
  there). The game flushes once (SetUserCommand + SetFlip 5 us apart at the frame's end) and waits for the flip /
  user handler: incremental walking past `put` and releasing the game before the translation's last guest read are
  not possible without lying about RSX progress (docs/RENDER_PERF.md, new section "Overlap ...").
- Patch 0067-xlat-overlap.patch (applies last in name order; prepare_ps3recomp 49 patches OK):
  RSX_XLAT_OVERLAP=1: the walker drains the frame's vertex jobs, does the window's resize/fullscreen sync and hands
  the present (copy, overlay, Close/Execute, Present, frame log) to a new `rsx-render` thread; =2 (default): also
  every command-list call recorded through a 4 MB ring (libs/video/rsx_record_ring.h, proxy with the list's vtable,
  30 methods; Close/Execute/fence/Reset in ld_own_enter after the ring is empty); =0: old path. The next walk waits
  for the present (rsx_live_draw_sync in cellGcm_rsx_process_fifo). [slow-frames]/display lock adapted.
  RSX_XLAT_OVERLAP_AB=N: interleaved A/B diagnostic. Renderer thread woken every 256 calls, no spin (a first version
  with 16 calls + 300-pause spin cost ~2 ms CPU/frame and lost on CPU-saturated 4 LPs).
- Tests: tests/test_xlat_overlap.py + tests/c/xlat_ring_test.c (300k random calls across thread/ring wraps/full
  ring, logs byte-identical; mutations caught). `python -m unittest discover -s tests -q`: 787 OK. Guard exit 0.

## Measured
- Interleaved A/B, mode 2 vs everything on the walker, 4 LPs, final build (xo11): slow_core 72 (saturated, ~45
  fps): frame median -0.6..-0.86 ms in all 8 windows (e.g. 23.85->23.01, 20.55->19.97), frames >17.5 ms -2..-23 %,
  walker CPU -0.2..-0.3 ms; no slow_core (60 fps): frames equal, translation -0.14..-0.21 ms. Earlier build (spin
  version) at slow_core 40 / loaded PC: frame median -0.5..-1.8 ms where frames were late, -7..-18 % frames >17.5.
- Paired runs base vs xo11 (4 LPs, masks 0x55/0x5500 swapped; noisy, mask/load dominate): slow_core 72 pool stage
  42.47 -> 45.35 fps (+6.8 %, 3 of 4 rounds), p99 32.1 -> 27.9 ms; stage 20 40.20 -> 42.46 (+5.6 %, 2 of 4), p99
  31.2 -> 28.2; no slow_core pool 59.08 -> 59.95 (1 round only). Earlier xo9 paired sets (slow 40, quieter PC):
  pool +2.8 %, stage 20 +4.3 %, unslowed at the 60 cap.
- Same picture (xo9, same code paths as xo11 but the wake protocol): lockstep old host / new joiner, every surface +
  backbuffer at frames 300/900/1500: pool 15/15 and stage 34 15/15 byte-identical (counters equal); stage 20 pairs
  had counters 1 apart (puddles differ, shadow map + glow identical; new/new pool 1 apart differs the same way).
- Same game (xo9): rollback RTT 150/3 % and lockstep RTT 30/1 %, 2 matches (stage 20 + pool), new/new, old/new,
  new/old: 0 mismatching, same hashes both sides, ~1,320-1,380 rollbacks per side. Smoke quick (xo9) exit 0, 2 fps WARNs.

## Open / next step
1. Rerun on xo11 (only the wake/spin protocol changed since xo9): remaining paired rounds (Hn30 3 more, Hn20),
   frame-dump pairs (stage 20 until counters match), the 6 sync pairs, smoke quick -- scripts/final.sh steps 2-5.
2. Fill docs/RENDER_PERF.md "Results" with the final A/B + paired numbers (PAIRED_PLACEHOLDER, STAGE20_MORE),
   replace the spin-version A/B table, add the CLAUDE.md bullet, regenerate the patch, final commit; delete this note.
