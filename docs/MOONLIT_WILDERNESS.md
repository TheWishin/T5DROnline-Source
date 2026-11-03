# Moonlit Wilderness: the thin black line (ps3recomp patch 0106)

Report (1.2.0 list): thin black lines on Moonlit Wilderness (**stage 5**, `t5s06`, see the stage table in
[DIRECTFIGHT.md](DIRECTFIGHT.md); stage 22, Great Plains, is its Dark Resurrection replacement).

## What it was

With **Stage blur / glow On** (launcher Settings; `PS3_STAGE_BLUR=1`, Off is the default since 1.1.4) the last
row of the picture was about a third as bright as the rows above it, and the last column about three quarters:
a thin dark line along the bottom and the right edge, every frame of every fight. Measured on the display
buffers (`tools/flicker_check.py --keep`, 90-240 frames per run; ratio = mean brightness of the edge row/column
over the row / column two pixels further in):

| run (stage 5 unless named) | bottom row | right column | top / left |
|---|---|---|---|
| blur Off, Native / 1440p / 1080p / Lower / Lowest | 1.00-1.03 | 1.00-1.01 | 0.99-1.01 |
| blur On, Native, before 0106 (`RSX_KERNEL_EDGE=0`) | **0.35** | **0.75-0.81** | 0.99-1.01 |
| blur On, Native, 0106 | 1.00 | 1.00 | 1.01 / 1.00 |
| blur On, 1080p, 0106 | 1.00 | 1.00 | 1.00 |
| blur On, Lowest (0106 does not act below Native: 0038 already draws one host pixel = 2 guest texels past the scissor there) | 1.00 | 1.00 | 1.00 |
| stage 34 (the misty swamp), blur On, before / 0106 | 0.35 / 1.00 | 0.79 / 1.00 | 1.00 |

So Moonlit Wilderness has a soft-focus filter like the stages in
[RENDER_PERF.md "Stage blur and glow"](RENDER_PERF.md) (0043's survey covered stages 17-34 only), and the line
was on every soft-focus stage with blur On, not only this one.

Why: the 3D pass draws into part of the 2048 x 1440 target -- on Moonlit 1536 x 1280, scissor = viewport, and
the game's clear of that target is held to the same scissor, so the rest of it is black. The soft-focus
downsample reads the target with a centre tap and taps 2 guest texels around it (a filter kernel,
`rsx_fp_texture_tap_mask`). For the last display row the centre is at guest row ~1279 and the taps reach rows
1280-1281: black. Top and left are not affected: there the taps leave the texture itself and the sampler clamps
to its edge row, which is drawn. Visible in the surface dumps (`T5_DF_SHOT` + `LD_SURF_DUMP`): row 1279 mean 54,
row 1280 0; column 1535 38, column 1536 0.

## The fix

A filter kernel that reads a render target whose draws this frame left an undrawn margin reads it through a
view (0043's guest-size view, `ld_guest_view_srv`, now also at Native) whose texels past the drawn part repeat
its last row and column -- what the scene's continuation would be. Every texel inside is the same as before
(the view's shader clamps the texel position first: `pos.xy = min(floor(pos.xy), lim) + 0.5`, a no-op inside).
The drawn part is the furthest right/bottom of this frame's draw scissors on that target (`ext_r` / `ext_b`
per surface, `ld_kernel_edge`). Nothing changes for single-tap reads (the plain downsample of the other stages,
the heat haze), with blur Off (the kernel then reads one tap at its centre, 0043), or for a target drawn to its
edges. `RSX_KERNEL_EDGE=0` turns it off (the old picture, for comparisons). Host pixels only: no guest memory,
command or timing changes, so the two players of a match may have it on or off.

Cost: one 2048 x 1440 copy pass per frame on soft-focus stages with blur On at Native (above Native the view
was made anyway).

## Checked

- The table above (offline direct fights, Kazuya vs Raven, 1.5 s windows 12 s after the fight state).
- Frame-exact: a lockstep pair, blur On on both, host `RSX_KERNEL_EDGE=0` and joiner 0106, stages 5 and 34,
  every surface dumped at the same fight frames on both PCs (`T5_DF_SHOT=++300,++600`): both matches confirmed,
  0 mismatching frames, the same hashes (the setting is host-only). Where the two PCs' 3D targets were identical
  (stage 5 frame +300, stage 34 frame +600), the display buffers differed only in the last 3 rows and columns:
  the last row's mean brightness 62 -> 168 (stage 5) and 48 -> 125 (stage 34), against 169 / 133 three rows up.
  In the other two frames the 3D targets themselves already differed in 1,300-2,900 pixels (secondary motion,
  as in same-build pairs).
- Other things looked at, no line found: Native, 1440p, Lower, Lowest, 1080p with blur Off; a later part of the
  fight; dark-line search over every frame (only HUD panel and text edges). A dark-blue stepped strip in the far
  grass (sky between two distant grass cards) is the same at every internal resolution and with blur on or off;
  it is not changed by this patch. If players mean that, a screenshot of the spot is needed.
