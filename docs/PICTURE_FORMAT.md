# Picture format plan for 1.2.0

Status: design only. The current default stays unchanged: the game's 16:9 picture is scaled to fit the window, with black bars where necessary. No new setting, game-reported aspect, resolution, or launcher text is implemented by this document.

## What the mirror establishes

- `patches/ps3recomp/0010-render-quality.patch`, `ld_present_copy`, uses the guest display dimensions `aw:ah`, computes `k = min(backbuffer_width / aw, backbuffer_height / ah)`, and centres the resulting rectangle. A taller monitor therefore has bars above and below a 16:9 picture. At a 1920 x 1280 client area (3:2), the expected picture is 1920 x 1080 with 100 pixels above and below: 15.625% of the total height is bars. At 1920 x 1200 (16:10), it is 1920 x 1080 with 60 pixels at each edge. Substantially larger bars need the actual client, backbuffer and picture rectangles checked; the report alone does not establish their cause.
- `patches/ps3recomp/0038-internal-resolution.patch` changes host resource sizes while retaining guest surface dimensions, memory and commands. Below Native it reduces the large 3D targets while retaining the 1280 x 720 display buffers for HUD and text. Its existing numeric option is a uniform factor or scalar output height, not an arbitrary width and height.
- `launcher/core.py`, `DEFAULTS`, `DISPLAY_MODES` and `_place_window`, offers fixed window presets, maximized and borderless modes; fixed windows retain 16:9 and fit the monitor's work area. There is no saved custom width/height setting.
- `patches/ps3recomp/0045-training-overlay.patch`, `ovl_viewport`, independently repeats the present rectangle calculation for the 1280 x 720 overlay canvas. Changing presentation without changing that mapping moves overlays away from their intended positions.
- The mirror contains neither the video-output aspect-report implementation nor the game's consumers of a reported aspect. The movie decoder's aspect metadata in patch 0006 is not evidence of game layout support. There is no verified aspect-control address here. Do not guess one or claim the game supports a native 4:3, 16:10 or 3:2 layout from these files.

## Proposed choices

Keep picture format, output resolution and Internal resolution as separate settings. Increasing pixel count must not silently change picture shape or vice versa.

| Picture format | Intended behaviour | Release condition |
| --- | --- | --- |
| 16:9 (default) | Preserve today's complete picture and shape, fitted inside the available client area. | Existing behaviour; retain as fallback for every unsupported format. |
| 4:3 | Use a verified native 4:3 layout if the game has one, including its HUD and camera framing. | Trace the game's aspect report reads and verify the complete layout first. This extends the existing requested 4:3 work; it does not mark it implemented. |
| Fit to screen | Use the actual client ratio for 16:10 and 3:2 only if their complete layout survives the checks below. Re-evaluate on resize or monitor change. | Experimental and unavailable until both ratios pass; fall back to 16:9 with a clear reason when unsupported. Do not automatically treat arbitrary ratios as supported. |

A final-blit stretch can remove bars without changing simulation, but it squeezes or stretches fighters, text and circles; that is not proof of a native layout. A crop can preserve shape but cuts the sides of a 16:9 picture on taller screens, including names, life bars and other edge content. Neither is an acceptable substitute for the proposed complete-layout Fit to screen mode. If a separate distorted stretch option is ever wanted, label it honestly and keep it opt-in; it is outside this plan.

Before implementing a native format, the maintainer must establish what the game actually does with its reported aspect: does it change 3D projection, HUD anchors and safe areas, display buffers, menus, or a combination? A reported aspect that only changes projection can still leave 16:9 HUD assumptions; a reported resolution that only resizes buffers does not reflow text. The missing implementation and consumer evidence must be supplied in the real project before enabling such a path.

## Custom resolution

Add validated custom **output client width and height**, in physical pixels, alongside the existing window presets. Persist them separately from picture format and `internal_res`; use them for window placement/backbuffer sizing only. Borderless continues to follow the selected monitor. A 3:2 output size must not itself request a different guest aspect or remove bars in 16:9 mode.

Accept complete positive integers within documented renderer/resource limits, reject malformed, zero, negative and overflowing values, and handle a size that cannot be created by reverting to a supported preset. Keep a window inside the current monitor's work area, including its frame and DPI; show the actual applied size when clamped. Revalidate saved values on load and after monitor changes. Determine limits from the real renderer/device checks before choosing numbers; this mirror does not establish a safe arbitrary maximum for custom output.

Keep the current Internal resolution presets and uniform scaling semantics. If an advanced custom internal height is exposed later, route it through the existing validated uniform-scale path, retaining its 0.25x to 4x bounds and guest surface identity. Do not interpret arbitrary output `width x height` as anisotropic internal rendering or as a replacement guest display size. Higher custom output sizes need not increase 3D detail, and lower Internal resolution does not repair an aspect/layout error.

Any new launcher labels, hints, validation messages and fallback messages must be added to every existing language catalog using the surrounding translation conventions. None are added by this plan.

## Keep changes display-only

The safe implementation boundary is host presentation and resource allocation: the peers retain identical guest inputs, commands, memory, clock, camera decisions and side assignment. Share one computed picture rectangle between the present blit and training/status overlays. Check patch 0086 against that same coordinate system: HUD element placement, viewport/scissor clipping and the distinction between 3D and HUD must use the draw's real coordinates rather than assume a new canvas is 1280 pixels wide.

Changing the aspect reported to the guest is **not yet proven display-only**. `src/netplay/t5_hooks.cpp` documents that camera-projected fighter side flags affect sidestep direction and remain in the gameplay hash; excluding some render/camera records from a hash is not proof that an arbitrary aspect change cannot feed back into gameplay. Prefer a verified host-only projection/HUD transform after the game's decisions. If a native layout needs guest-visible configuration, trace its writes and all gameplay consumers, and prove identical simulation before allowing different local preferences online. Do not weaken hash coverage to make a format pass.

## Acceptance tests for the maintainer

These require the real build and game; none were run in this checkout.

1. Preserve the default: with a clean settings file, compare the existing 16:9 picture and overlays in 1280 x 720, 1920 x 1080, 1920 x 1200 and 1920 x 1280 clients, windowed and borderless. Verify the exact expected centred rectangles above, with no second scaling/letterbox applied. Check DPI at 100%, 125% and 150%, Alt+Enter, resize and moving between monitors. The 3:2 GT 1030 report should record the monitor's actual mode and the actual client/backbuffer/picture sizes, then compare those to the formula.
2. Verify the full layout separately for proposed 4:3, 16:10 and 3:2: main menus, character/stage select, customization, Practice, fight intros, side switches, walls/corners, KO slow motion, end-of-round replays, victory and rematch. Check round marks, timer, long names on both sides, life bars at full/partial/empty health, sparks, subtitles, pause/offline menus and training overlays. No clipping, garbled text, stretched geometry, displaced bars or missing UI; reject a format that fails rather than silently crop it.
3. Repeat each enabled format with Always show me on the left off and on as actual P2, at Native, Lowest and an above-Native internal resolution. Check moving cameras and full/partial scissors so the name/bar fix remains correct across host scale changes.
4. On the player's GT 1030 and 3:2 monitor, compare Native, Lower and Lowest Internal resolution using the same stage and fight sequence; measure frame time and verify 60 fps where the hardware can sustain it. Do not promise that a shape or output-size setting will cure GPU or CPU limits. Keep a known supported preset recoverable after invalid or excessive custom values.
5. For every format admitted online, run a real pair with one PC at default 16:9 and the other at the new format/custom output, then swap PCs and actual P1/P2 roles. Exercise sidesteps, camera turns, side switches, walls, KO replays and rematch under rollback as well as normal play. Require **0 gameplay mismatches**, identical health/timer/side flags and results, and successful replay playback with a different local display preference. A guest-reported-aspect implementation cannot ship online before this passes.

Before game testing, add game-free regression tests for the eventual rectangle and settings helpers: exact aspect-fit bounds, shared overlay mapping, custom-value parsing/clamping/fallback, default compatibility and all-catalog coverage. Since this change is a plan and implements no helper, it supplies acceptance criteria rather than claiming an executed regression test or a fixed player report.
