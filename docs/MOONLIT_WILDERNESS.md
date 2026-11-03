# Moonlit Wilderness: black-line investigation

Status: diagnostic plan and code-based hypothesis; no reproduced Moonlit
Wilderness failure and no renderer fix claimed. This task did not build, start
the game, capture frames, or execute tests.

Moonlit Wilderness is **stage 5**, `t5s06`, in
[the stage table](DIRECTFIGHT.md). Stage 22 is Great Plains, its Dark
Resurrection replacement. Stage 4, the default of `tools/flicker_check.py`, is
City at Sunset and will not exercise the reported stage.

## What the maintainer should run later

These commands are for an authorized, game-ready maintainer environment.
`GAME_OUT` and `DIAGNOSTICS_OUT` are placeholders for its existing build and
private diagnostics directory. Never run these commands in this public working
copy or put their game data, captured game art, or player logs here. The tool
needs the game's existing build plus NumPy; it does not build anything.

Run separate captures, with the same build, GPU, driver, fighters, and capture
timing. Replace each diagnostics directory with a fresh private directory.

```text
python tools/flicker_check.py --out GAME_OUT --stage 5 --fighters kaz,rav --at 9 --secs 12 --dir DIAGNOSTICS_OUT/native --keep PS3_INTERNAL_RES=native PS3_STAGE_BLUR=0
python tools/flicker_check.py --out GAME_OUT --stage 5 --fighters kaz,rav --at 9 --secs 12 --dir DIAGNOSTICS_OUT/lowest --keep PS3_INTERNAL_RES=lowest PS3_STAGE_BLUR=0
python tools/flicker_check.py --out GAME_OUT --stage 5 --fighters kaz,rav --at 9 --secs 12 --dir DIAGNOSTICS_OUT/blur --keep PS3_INTERNAL_RES=native PS3_STAGE_BLUR=1
python tools/flicker_check.py --out GAME_OUT --stage 5 --fighters kaz,rav --at 9 --secs 12 --dir DIAGNOSTICS_OUT/no-shadows --keep PS3_INTERNAL_RES=native PS3_STAGE_BLUR=0 PS3_SHADOWS=0
python tools/flicker_check.py --out GAME_OUT --stage 5 --fighters kaz,rav --at 9 --secs 12 --dir DIAGNOSTICS_OUT/synchronous-vertices --keep PS3_INTERNAL_RES=native PS3_STAGE_BLUR=0 RSX_VERTEX_THREADS=0
```

On Windows, repeat the native capture with `--cpus 0xFF` only if that mask is
valid for the machine. It restricts the game to eight logical processors and
can expose scheduling-sensitive failures hidden by more workers. On other
platforms this option does not set affinity. Do not compare a capture with a
different CPU mask without recording that difference.

The tool already enables `LD_FRAME_DUMP_ASYNC=1` and dumps every presented
frame during the capture interval. Keep that default: synchronous GPU readback
can hide a timing failure. `RSX_VERTEX_THREADS=0` changes vertex fetching to
the renderer's walker; it is a diagnostic comparison, with a performance cost.
`--keep` retains frames for visual comparison. Without it the frames are
deleted, but the tool still leaves its run directory and game log behind.

Inspect the retained consecutive frames, especially floor/vegetation edges
and the right and bottom picture edges. Record whether the line is stationary,
moves with geometry, lasts a single frame, changes with resolution, or
disappears with blur or shadows. Compare matching fight moments, allowing for
different startup timing between runs. Check the logs for skipped asynchronous
readbacks and dropped draws. Missing captures are gaps in the evidence.

Exit status 0 means no *whole-picture dark flash* was counted, 1 means one was
counted, and 2 means the run failed or fewer than 30 frames were read back.
`dark_frames()` averages a central crop with a four-pixel stride; a frame must
be under brightness 45 and less than half as bright as both neighbours to be
counted. **A narrow line, a persistent dark strip, or an artifact outside that
crop can produce exit status 0.** This tool does not prove Moonlit Wilderness
is line-free. Visual inspection of the retained frames is required, and any
line detector needs synthetic positive and negative cases before it becomes
a release gate.

## Likely cause to investigate in the code

For a stable dark line at the picture edge, the first code-supported hypothesis
is **sampling cleared-black padding beside the stage's rendered subrectangle**.
[Patch 0038](../patches/ps3recomp/0038-internal-resolution.patch), in
`libs/video/rsx_live_draw.c` / `sink_end_impl`, scales the target, viewport and
scissor. Its explicit below-native correction extends the scissor by one host
pixel at the right and bottom: the game's downsample taps can otherwise reach
the cleared black outside the scene, because a host texel spans more than one
guest texel. The patch's comment describes a darker right column and bottom
row. That is direct evidence for this *class* of edge artifact, not evidence
that stage 5 currently has it. A Lowest-only edge line supports this lead;
a line crossing the interior at Native needs a different explanation. Check
the actual stage 5 render-target dimensions, viewport/scissor and sampled
rectangle before changing any rounding or sampling rule.

For intermittent black triangles or slivers, investigate asynchronous vertex
job reservation and draw-skipping instead.
[Patch 0082](../patches/ps3recomp/0082-sunset-black-frames.patch) documents a
proven City at Sunset failure: a draw queues a vertex job, then returns before
recording; the next draw reuses its ring bytes, and whichever job finishes last
supplies the geometry. `sink_end()` now calls `ld_vjob_reserve_keep()` to
advance those reservations even after a skipped draw. This protection covers
dropped PSOs and debug skips as well as the stage-blur skip. A Moonlit failure
that disappears with synchronous vertices would justify auditing these paths,
but does not establish the same bug. The City at Sunset diagnosis is documented
in [RENDER_PERF.md](RENDER_PERF.md); it must not be relabelled as a confirmed
Moonlit cause. `RSX_VERTEX_KEEP_SKIPPED=0` deliberately restores the old failure
and is not a player workaround.

No stage 5 surface address is supplied here: it has not been established by
the repository evidence inspected for this item. Do not copy City at Sunset's
surface address into `LD_FRAME_DUMP_ASYNC_SURF` for Moonlit Wilderness. Discover
the actual surface from a future authorized capture before using that hook.

## Proof still needed

The maintainer must reproduce the reported line on stage 5, identify the
affected draw or sample region, and repeat the capture matrix on a real build.
This document changes no simulation or rendering behavior and adds no setting.
The switches above are existing, local rendering diagnostics; old clients and
network messages are unchanged. Any eventual renderer fix needs a focused
regression that fails on its old behavior, matching-scene visual checks and a
real two-PC game test with **0 simulation mismatches** before release.
