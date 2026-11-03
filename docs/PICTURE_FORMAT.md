# Picture format and own window size (1.2.0, ps3recomp patch 0107)

Players with 16:10 and 3:2 screens (laptops, a Discord request) saw black bars above and below the picture and
could not pick a window size of their own. Two launcher settings now cover that:

- **Settings -> Display -> "Window, my own size"**: the inside of the game window (client area) in physical
  pixels, any shape, e.g. 2160 x 1440 on a 3:2 laptop or 1680 x 1050 on a 16:10 monitor. Whole numbers, width
  320-7680, height 240-4320 (`core.window_size`); anything else is refused in the field and the last valid size
  stays. A size larger than the monitor's work area is scaled down to fit with its shape kept (`core.fit_client`),
  like the fixed window presets. Borderless fullscreen still follows the monitor.
- **Settings -> Picture format** (`PS3_PICTURE`): how the game's 16:9 picture fills a window or screen of
  another shape.

| Picture format | `PS3_PICTURE` | What you see |
|---|---|---|
| Whole picture (default) | `fit` (unset) | the whole 16:9 picture, black bars where the window has another shape -- the present before 0107, to the pixel |
| Fill the screen | `fill` | no bars, the shape kept, the picture enlarged until it covers the window: on 16:10 5 % of the width is cut on each side, on 3:2 7.8 %, on 4:3 12.5 % (the outer ends of the life bars and names too) |
| Stretch to the screen | `stretch` | no bars, the whole picture pulled to the window's shape: on 16:10 everything is 11 % wider than it should be, on 3:2 19 % |
| 4:3 | `4:3` | the middle 960 x 720 of the picture in a 4:3 frame, bars left and right on a wide screen; on a 4:3 screen it fills the screen |
| True 4:3 (offline only) | `PS3_VIDEO_ASPECT=4:3` | the game draws for a 4:3 TV: its own 4:3 3D view and HUD, shown as 4:3 with bars left and right on a wide screen. A game started for online play (or a replay) gets the `4:3` choice instead (below) |

Fill and Stretch are honest names for what a final-picture change can do: the game draws 16:9 or 4:3 only, so a
16:10 or 3:2 screen either gets bars, cuts the sides or widens everything. A real 16:10 / 3:2 picture with more of
the stage above and below would need the game to draw a taller 3D view and to place its HUD for it; it has no
such layout -- only 16:9 and 4:3 (below).

The 3D picture, the HUD and the menus all go the same way (they are one picture by then). The training overlay
is laid out in the 16:9 rectangle that fits inside what is visible, so it is never cut or stretched.

## Host pixels only

Both settings (every picture format but True 4:3, below) change only where the present (`libs/video/rsx_live_draw.c` `ld_present_copy`) and the overlay
(`libs/video/rsx_overlay.c` `ovl_viewport`) put the finished picture in the window. One pure function decides the
rectangles for both, `rsx_picture_rect()` in `libs/video/rsx_picture_rect.h`: the viewport the whole picture is
drawn into (it may reach past the window for Fill and past the visible part for 4:3; the scissor keeps the
visible part), the visible rectangle, and the overlay's 16:9 canvas. Nothing the game reads changes: no guest
memory, no command, no display mode, no timing. So the two players of an online match can choose differently,
and a replay plays back the same with any setting.

`fit` takes exactly the old code path: the same viewport, scissor and clear, and when the window has the
picture's size the plain copy (`tests/c/picture_rect_test.c` compares the new function with the old formula on
26 window shapes). The game log says once which format is used:
`[display] picture fill (PS3_PICTURE): 1920x1200 window, picture 2133x1200 at -107,0, visible 0,0..1920,1200`.

Windows only: the macOS (Metal) present keeps its own letterbox.

## True 4:3

The game does have a 4:3 mode. At boot it asks the system for the display mode (`cellVideoOutGetState`) and keeps
"wide = aspect is not 4:3" in its display object (code at 0x25A34C: `+0x69 = (aspect ^ 1) != 0`). The display
object is read back by at least seven functions; the camera set-up (0x816D4) picks the 3D projection's aspect
from it -- 16/9 (0x469860) when wide, 4/3 (0x46985C) when not -- and stores it with the near/far planes
(100, 5,000,000) in the camera object.

`PS3_VIDEO_ASPECT=4:3` (patch 0107) makes `cellVideoOutGetState` report a 4:3 TV; the default report stays
16:9 (`s_report_aspect`). `PS3_VIDEO_RESOLUTION=480|576|720|1080` reports that resolution (the game then makes
display buffers of that size). Both are read once and logged (`[cellVideoOut] reported display mode: ...`).

What the game does with it (stage 5, Kazuya vs Raven, window pictures through `RSX_TEST_BB_SHOT`):

- **4:3 at 720p**: the 3D view gets the 4:3 projection (drawn squeezed into the 1280 x 720 buffer: the moon is an
  ellipse until the picture is shown as 4:3) and the HUD a 4:3 layout -- but off-centre: life bars, timer and
  names sit left of the middle and do not line up with each other. 720p with a 4:3 TV is not a combination a
  PS3 gives a game (HD output is 16:9), and the game was not made for it.
- **4:3 at 480 (SD)**, what a 4:3 TV gives the PS3: display buffers 720 x 480, the HUD centred and complete,
  the moon round once the picture is shown as 4:3. That is the game's real 4:3 picture: more of the stage above
  and below, less at the sides.
- 1080 lines with 4:3: the same off-centre HUD as 720p.

So **True 4:3** = `PS3_VIDEO_ASPECT=4:3`, which by itself reports 480 lines (unless `PS3_VIDEO_RESOLUTION` says
otherwise). The present then shows the display buffers as 4:3, whatever their pixel size
(`cellVideoOut_report_4_3`, `pic_w` in `ld_present_body`), so Whole picture gives a 4:3 picture with bars on a
wide screen and the other formats work from that shape; the training overlay keeps its own 16:9 canvas inside
the visible part (`ovl_viewport`), so its letters are never squeezed. Internal resolution counts from 720 lines
in this mode (`cellVideoOut_res_boost`: x1.5 at 480, x1.25 at 576): Native draws 720 lines, 1080p 1080 lines,
Lowest keeps 480-line display buffers with a smaller 3D pass; the log and the window title name the step
(`rsx_internal_res_label`). Checked: boot (rating screen, intro movie, attract), fights at Lowest / Native /
1080p in 1024 x 768, 1440 x 1080 and 1920 x 1080 windows.

**Offline only.** The 4:3 TV changes what the game sets up -- its display buffers, camera and HUD objects --
and that reaches the state both PCs compare: a lockstep pair with one side on True 4:3 desynced from frame 1,484
of 1,707 (`runs/pair_ar`). The launcher therefore sends `PS3_VIDEO_ASPECT` only to offline games; a game started
for online play, a replay or a spectator's game gets the picture-only `4:3` choice instead and loses any
`PS3_VIDEO_ASPECT` / `PS3_VIDEO_RESOLUTION` (`core.online_picture_env`, also out of an inherited Windows
environment).

## Tests

- `tests/test_picture_format.py`: builds and runs `tests/c/picture_rect_test.c` (every format on 26 window
  shapes, fit = the old present, the overlay always 16:9 inside the visible part); the launcher's size parser
  and fit, the settings refusing junk, `PS3_PICTURE` reaching the game only for a non-default format, Extra
  settings naming it, the problem report's lines, the texts in all six catalogs; the patch's files and the
  documented switches.
- In the game: `RSX_TEST_CLIENT_SIZE=WxH` (swap chain as if the window had that size) + `RSX_TEST_BB_SHOT=<file>`
  (read back what the window shows) give the window picture of every format without taking the screen.

Results (2026-11-03, this PC, RTX 3090): window pictures of Whole picture at 1280 x 720 (the plain copy) and
1920 x 1200 (1920 x 1080 with 60 px bars above and below), Fill at 1920 x 1200 and 2160 x 1440, Stretch at
1920 x 1200, 4:3 at 1920 x 1200 and 1024 x 768, each with the training overlay on: as in the table, the overlay
whole inside the visible part. Online with different settings on the two PCs (host Fill in a 1920 x 1200 window,
joiner 4:3 in 1280 x 720; `fight_flow_test --flow persistent --matches 2 --mash`, stages 5 and 22): rollback
2/2 and lockstep 2/2 matches confirmed, 0 mismatching frames, the same hashes on both PCs; the 8 replays the
two pairs recorded played back identical with the default picture (`replay_play.py`).
