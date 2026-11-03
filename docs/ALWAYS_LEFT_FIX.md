# Always left / Always right: the HUD fix (issue #31)

Status (2026-11-03, branch `fix-31-hpbar`): **fixed and checked in the game.** Host presentation only, in
`patches/ps3recomp/0086-always-left.patch` (`libs/video/rsx_always_left.h` + the hook in `rsx_live_draw.c`).
No guest memory, game address, controller rule or simulated state changes; the setting's policy
(`src/netplay/always_left.h`: casual online, offline Versus as a preview) is unchanged.

## The report

GitHub issue #31, Always left with the local player as P2: "my own life bar is empty, the right bar is mine",
names garbled or flickering.

## What the game draws (measured)

`RSX_ALWAYS_LEFT_TRACE` on a 1.2.0 offline Versus fight (guest 1280 x 720, one record per draw after the
mirrored 3D copy). Tekken 5 DR draws its fight HUD **one draw per quad**, in this order: the timer's two digits
(564..666 and 618..719 across the middle), the round marks of each side (396..575 / 706..885), P1's bar frame
(41..588), P1's two fill layers (life and the orange drain, both ending at 569 -- next to the timer's first digit
at 564.7), P2's frame (693..1240) and fills (from 712), the name plates (53..477 / 804..1228), the rank plates
(53..181 / 1100..1228), then every glyph of both names as its own draw (P1 left-aligned from 58, P2 right-aligned
to 1226, y 89..113). Below that, centred titles (ROUND n, READY, FIGHT, K.O., one draw per letter, y 245..445),
the round intro's PLAYER DATA strip (one panel per side 522..594, wider than its half and reaching past the
screen edge; the numbers one draw per glyph at 557..581), an intro text line across the middle (632..656) and
REPLAY (bottom right). No draw in a fight holds elements of both sides.

## Why the old code broke the bars and names

The 1.1.8-1.2.0 renderer grouped the previous frame's quads into "elements" (strings, flipped pairs) and
placed this frame's draws by them. P1's fills end 5 px from the timer's first digit, so they were grouped with
the timer -- the centre element, which stays -- while P1's frame moved to the right: the left frame held P2's
fill, the right frame was empty or held only part of a fill. Which draw joined which element changed as the
fill shrank and as digits changed, so bars and names jumped between frames, and on the first mirrored frame
(no previous layout) every glyph was placed on its own. Captured with the old runtime (`runs/B_left`):
the left bar empty while the right one still had life, the right frame missing, and frames in which the whole
HUD stood unmoved.

## The rule now (stateless)

`al_hud_place(q, n, &why)` decides from the draw's own evaluated box, the same way on every frame -- no
history, so nothing changes between frames or on the first mirrored one:

- **Top band** (the draw ends above 30 % of the height): a draw wholly on one side moves by exactly half the
  width to the other side. Frame, both fill layers at any length, round marks, plates and every name glyph
  of a side move by the same amount, so each side's HUD arrives whole, in order and inside its own frame. A
  draw across the middle (the timer's digits) stays.
- **PLAYER DATA strip** (wholly inside 500..600 of 720): a panel (wider than 1/8 of the width) takes the
  other panel's place (its box mirrored, art as drawn); its numbers move by half the width, in order, inside
  the moved panel.
- **Everything else below the band** stays: centred titles (one draw per letter -- a letter must not move
  alone), ROUND n and its separate digit, the intro line, REPLAY.
- A draw of more than six vertices across the middle in the band (both sides in one batch; never seen in
  Tekken 5 DR) is left whole, never cut.
- The scissor moves with its draw (`al_clip_scissor`); a frame whose 3D picture was mirrored keeps its HUD
  on the mirrored side even if the game's request goes off before that HUD is drawn.

The look: each side's HUD is the other side's art moved across -- the bars fill toward the timer from the
outer end, the round marks sit at the outer end and the name is aligned toward the timer. Placing each name
at the mirrored anchor would need the string's width before its first glyph is drawn (only the previous
frame knows it -- the history that caused the bug), so it is not done.

Scene-copy detection is unchanged from 1.2.0: a full-screen quad (all four corners within two guest pixels)
that samples the oversized non-display target in unit 0, checked against the fragment program's real
texture mask.

## Tests

- `tests/c/always_left_render_test.c` (built by `tests/test_always_left.py`): the measured HUD frame placed
  three times (no history: identical every pass), each fill inside its own moved frame at nine life steps
  with unequal life, names of every length glyph by glyph in order under their own bar, the timer, titles,
  ROUND 1, intro line, REPLAY, the band's edge, both-sides batches, the PLAYER DATA strip, the scissor
  diagnostics; plus the vertex-program evaluator and the scene-copy shape.
- `tests/test_always_left.py`: wiring (placement from the draw alone, no frame history in the renderer,
  scissor trace before host scaling, presentation only, series order) and the game/launcher side.

## Checked in the game

See NETPLAY.md "Issue #31" for the runs and numbers. Tools (scratch, not in the repo): offline Versus in
netplay local mode with scripted pads (`T5_NET_MODE=local`, `T5_NET_SCRIPT`/`T5_NET_SCRIPT2`), frame-exact
backbuffer pictures (`T5_DF_SHOT=+n` + `LD_SURF_DUMP` + `LD_SURF_DUMP_BB_ONLY=1`), the trace only at those
frames (`RSX_ALWAYS_LEFT_TRACE=gate[:n]` with `LD_SURF_DUMP_GATE`), every frame of a window
(`LD_FRAME_DUMP` + `LD_FRAME_DUMP_GATE`) for the switch-on, pixel checks of both bars' teal run and of the
name boxes.

## Diagnostics

- `RSX_ALWAYS_LEFT_TRACE=<first>:<count>` (renderer frames) or `gate[:n]` (n frames each time the file
  `LD_SURF_DUMP_GATE` appears): one `[always-left-trace]` line per draw -- outcome (`copy-mirrored`,
  `hud-moved`, `hud-panel-swapped`, `hud-stays-across`, `hud-stays-centre`, `mixed-side-batch`, ...), raw
  and scissor-clipped box, texture hash, U direction, scissor before/after. Text only.
- Every 600 mirrored frames: `[always-left] N frames mirrored: ... HUD draws M moved / K kept in place / L
  left as they were`.
