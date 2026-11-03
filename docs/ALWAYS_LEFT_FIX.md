# Always left / Always right: the HUD fix (issue #31)

Status (2026-11-03, branch `fix-31-hpbar`): **fixed and checked in the game.** Host presentation only, in
`patches/ps3recomp/0086-always-left.patch` (`libs/video/rsx_always_left.h` + the hook in `rsx_live_draw.c`).
No guest memory, game address, controller rule or simulated state changes; the setting's policy
(`src/netplay/always_left.h`: casual online, offline Versus as a preview) is unchanged. The mirrored HUD has
the normal (as dealt) view's layout with the players swapped (the owner's wish after the first fix, which
moved each side across by half the width and so showed the other side's art).

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
fill shrank and as digits changed, so bars and names jumped between frames, and while the HUD was new (no
previous layout yet) it was left unmoved: 27 frames in the capture below. Captured with the old runtime (`runs/B_left`):
the left bar empty while the right one still had life, the right frame missing, and frames in which the whole
HUD stood unmoved.

## The rule now (this frame only)

Nothing is remembered from an earlier frame. Each HUD draw after the mirrored 3D copy is first sorted by its
own evaluated box (`al_hud_place`):

- **Stays where the game put it**: a draw across the middle (the timer's digits) and everything below the
  top band except the PLAYER DATA strip -- centred titles (ROUND n and its separate digit, READY, FIGHT,
  K.O., one draw per letter), the intro line, REPLAY.
- **A side draw**: wholly on one side, in the top band (ends above 30 % of the height) or inside the PLAYER
  DATA strip (500..600 of 720). It is drawn with a constant block of its own and placed together with the
  frame's other side draws right before the command list that holds them runs (`ld_al_resolve` at the start
  of `ld_flush_owned`, before Close/Execute: the GPU has not read the block yet). `al_hud_layout` then looks
  at this frame's side draws only:
  - **art the game flips itself** -- a texture this frame draws with its art flipped somewhere (u running
    right to left: bar frames, both fill layers, round marks, name plates; the game draws P2's as P1's
    flipped) -- is mirrored (x -> -x, the art flipped with it). Each side gets exactly the art the game draws
    there: the bars drain as the normal view's bars on that side, the round marks sit next to the timer.
  - **everything else** (text and pictures with writing: name glyphs, rank plates, PLAYER DATA panels and
    numbers) is grouped per texture, side and line -- a whole name whatever its gaps -- and the group's box
    is mirrored as a whole, every member moved by the same amount: glyphs stay in order and readable, the
    left player's name is left-aligned at the left edge, the right player's right-aligned at the right edge,
    rank plates and PLAYER DATA panels take the other side's place.
- The result is the normal (as dealt) layout with the players swapped, from the first mirrored frame on.
- Fallbacks, never seen in Tekken 5 DR's fight HUD: a side draw with face culling on is not mirrored (the
  mirror reverses its winding) but placed like text; a side draw with a guest scissor narrower than the
  target is moved by half the width at once, its scissor with it (`al_clip_scissor`); a draw of more than six
  vertices across the middle in the band (both sides in one batch) is left whole, never cut.
- A flush in the middle of the HUD (a full ring, a readback) places what came so far; the log counts it
  ("placed before the frame's end", by flush reason). In normal play: 0; with picture dumps for tests: a
  few. The rest of that frame's HUD follows what was placed (patch 0110, `al_hud_layout_frame`, this frame's
  draws only): a text group split by the flush (a name between two glyphs) takes the translation its first
  part got, so its glyphs stay in order at their spacing -- before 0110 each part was mirrored on its own and
  "ABCD" split after "B" showed "CDAB" (review of fix-31-hpbar); a texture mirrored in an earlier part stays
  mirrored. In such a frame the split name sits by up to its second part's width away from the edge (its
  first part alone decided the place); art drawn before its texture's flip appeared is placed like text.
  `tests/c/always_left_render_test.c` cuts a whole HUD at every point and checks order, spacing and side.
- Stages with a soft-focus filter (34 Ominous Mist above Native, 5 Moonlit Wilderness at Native with
  its undrawn margin, and the other soft-focus stages above Native): the copy of the 3D picture onto the screen
  reads the 3D target through its guest-size view (patches 0043/0106), a surface that is not in the draw's own
  list. Before patch 0111 that copy was never recognised, so Always left never switched on there (trace outcome
  `before-copy` for the whole fight). 0111 counts the view as a surface the draw reads. Checked in the game
  (offline VS, stage 34 at 1080p): old build never on (3,346 copies `before-copy`), new build on from the
  fight's start (every later picture mirrored), HUD in its normal layout.
- A frame whose 3D picture was mirrored keeps its HUD on the mirrored side even if the game's request goes
  off before that HUD is drawn.

Scene-copy detection is unchanged from 1.2.0: a full-screen quad (all four corners within two guest pixels)
that samples the oversized non-display target in unit 0, checked against the fragment program's real
texture mask.

## Tests

- `tests/c/always_left_render_test.c` (built by `tests/test_always_left.py`): `al_hud_layout` on the
  measured HUD frame (boxes and flips from the trace) at nine life steps with unequal life, four name pairs
  (16 wide letters, 1 letter, mixed, wide gaps): frames, round marks and name plates at the other side's
  place and mirrored, each fill anchored at its bar's timer end, rank plates moved not mirrored, P2's name
  starting at the left edge and P1's ending at the right edge with every glyph in order; a KO'd side's
  missing fill, culling on, the PLAYER DATA strip, the same frame twice (same answer). Also the sorting
  (`al_hud_place`: timer, titles, ROUND 1, intro line, REPLAY, the band's edge, both-sides batches), the
  scissor diagnostics, the vertex-program evaluator and the scene-copy shape.
- `tests/test_always_left.py`: wiring (side draws placed by `ld_al_resolve` first thing in
  `ld_flush_owned`, before the list closes; their constant blocks never shared; no frame history; culling and
  scissor fallbacks; scissor trace before host scaling; presentation only; series order) and the
  game/launcher side.

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
  `hud-deferred`, `hud-moved`, `hud-stays-across`, `hud-stays-centre`, `mixed-side-batch`, ...), raw
  and scissor-clipped box, texture hash, U direction, scissor before/after; then one `placed i/n` line per
  side draw with where `al_hud_layout` put it (`mirrored` / `moved`, new x range). Text only.
- Every 600 mirrored frames: `[always-left] N frames mirrored: ... HUD draws M moved / X mirrored / K kept in
  place / L left as they were, E placed before the frame's end` (and the flush reasons when E > 0).
