# Always left: 1.2.0 partial renderer repair

Status: **partial; the reported name/bar bug is not yet acceptance-tested or fully fixed.** Changes are host presentation only in `patches/ps3recomp/0086-always-left.patch`. No guest state, game addresses, controller assignment, or match simulation is changed by this renderer repair. The default remains off. The setting still applies only where `src/netplay/always_left.h` allows it.

## Why the old code can garble names and hide bars

The old renderer evaluated up to 64 vertices and reduced an entire draw to one bounding box. It inferred strings from the preceding frame. A glyph outside a known string box moved to its own horizontally reflected box. Thus three right-side glyphs at x=1000,1022,1044 moved to x=260,238,216 on the first frame: the glyph art remained readable, but letter order reversed. Later the same glyphs used a shared string displacement, and entering or changing glyphs could use a different displacement from their neighbours. This supplies a source-level reproduction of the reported garble without using game data.

The old scene-copy test accepted an oversized render target bound in texture unit 0. Binding state alone does not say that the current fragment program samples that unit, nor that the draw covers the picture. HUD draws can retain scene bindings while the camera changes. A false scene-copy detection reflected the HUD and restarted the preceding-frame layout, producing flicker. The bar scissor then followed whichever inconsistent transform was chosen; wholly offscreen scissors also needed both ends clamped before conversion to unsigned scaled coordinates. These paths are consistent with the life-bar symptom attributed to issue #31; the report's exact game draw sequence has not been captured or verified here.

## What this change does

- A side HUD draw moves exactly half the target width, preserving glyph order and the relative positions of its name, frame, and health fill. Displacement no longer depends on the individual glyph's width, the previous string's bounds, or whether equal health bars happened to form a mirrored pair. HUD art and fill direction remain as drawn; this is a half translation, not exact reflected anchoring.
- A scene copy must evaluate to all four screen corners, within two guest pixels, and sample the oversized non-display render target in texture unit 0. The actual fragment-program texture mask is decoded on every renderer tier. The tier-2 descriptor fallback mask `0xFFFF` is not used as proof that a unit is sampled.
- HUD texture identity comes from the textures actually sampled by the current program, instead of the stale texture-0 binding.
- Both horizontal scissor ends are clamped to the target before host scaling, including wholly offscreen empty rectangles.
- A draw with more than six vertices spanning the centre is left intact and does not seed a false centre-overlay box for the next frame.

`al_picture_quad`, `al_clip_scissor`, and `al_hud_place` are pure helpers extracted by the existing game-free renderer test. New regression cases are authored in `tests/c/always_left_render_test.c` and wiring checks in `tests/test_always_left.py`. No test, compiler, build, or game was run for this task, as requested.

## Remaining implementation work

An entire batch containing independent elements on both sides still has only one transform. Leaving it intact avoids introducing an arbitrary split through its glyphs, but does not swap those names or bars. The complete fix needs a verified hook that partitions by complete primitive or HUD element using its evaluated screen position, applies one transform consistently to every vertex of that element, and carries its scissor with it. Splitting by raw attribute x, camera constants, or by each vertex separately would cut or distort triangles and glyphs.

The complete upstream `rsx_live_draw.c` capture/reset implementation is absent from this clone: the checked-in patch series exposes pieces, not the complete lifetime of `dc.arr`, `dc.idx`, vertex translation buffers, and draw submission. Replaying the sink recursively or rewriting capture ranges without that lifetime evidence would be speculative. No external runtime or other T5DR folder was opened. No new guest address was invented.

Centre overlays still partly use preceding-frame adjacency (for example the separate `1` next to `ROUND`). A newly appearing multi-draw centre title and a changing batch layout require first-frame checks and may need current-frame buffering. Unsupported vertex programs and draws over 64 source vertices remain unchanged. Fullscreen copy shapes other than the documented four-vertex quad or six-vertex triangle-list quad are not recognized. These limits block calling item 2 complete.

## Required maintainer build and game checks

Apply the patch series in the maintainer's real runtime tree and build there. First run the game-free regression tests there, including the renderer C test and its optional decompiler encoding check. Patch applicability and compilation were not proved in this working copy.

In a casual match, make the local player P2. Use distinct long mixed-width names (including the reported strings), different characters, unequal health, and different round-win marks. Compare Always left off/on from the very first displayed fight frame. The on view must preserve every letter's order and spacing, show the correct name with the correct fighter, retain both nonempty health bars, update damage and recoverable portions continuously, and keep timer digits and round marks correctly associated. Check names that lengthen or change, shadows, simultaneous name batches, partially scissored fills, round transitions, and the separate ROUND/FIGHT/K.O. overlays. A failure to swap a mixed-side batch is an expected remaining blocker, not a passed test.

Repeat while the camera pans, zooms, rotates, changes sides, and during KO slow-motion/replays. Toggle between matches; cover character intro, result, and menus to ensure the renderer request stops at the intended boundaries. Check 720p, the existing internal scales, and the intended output/window sizes. Inspect asymmetric bar art and fill direction: the partial half-translation intentionally retains their source orientation and must be judged before acceptance.

Use one PC with the option enabled and one disabled. Both must show the same health, round result, and match outcome, and a full set must record **0 simulation mismatches**. The pictures may differ. Also test offline Versus, ranked/Quick/tournament exclusions, and replay exclusion under the existing policy. These are proposed checks, not results obtained here.
