# Training overlay: input display and frame data

Competitive players train with an input display and frame data, as in modern
Tekken. Tekken 5 DR has neither, so the port draws them itself, over the
finished picture:

- **Input display**: each player's last inputs, newest at the top, with how
  many frames each was held: the direction as an arrow in Tekken notation
  (forward is toward the opponent, whichever side the fighter stands on; a dot
  is neutral) and the buttons as 1 2 3 4.
- **Frame data** after each exchange: who attacked, the startup of the move
  (`i10`: it hits on its 10th frame), what happened (`BLOCK`, `HIT`,
  `COUNTER HIT`, `WHIFF`, `KNOCKDOWN`) and the frame advantage: how many frames
  earlier than the opponent the attacker can act again (`+3`, `-15`). A whiff
  shows how many frames the move took until its user could act again. The last
  three exchanges are listed, the newest on top.

Where: P1's inputs at the left edge under the health bar, P2's at the right
edge, the frame data in the middle under the timer (no screenshot here: it
would show the game). Example lines: `P1  i10  BLOCK +3`, `P2  i16  HIT -4`,
`P1  i10  WHIFF 25F`.

## Turning it on

Launcher: **Settings -> Training overlay** (German: *Trainings-Anzeige*).

| Setting | Effect | Environment |
|---|---|---|
| Off | nothing is read, nothing is drawn | `T5_TRAINING=off` |
| Inputs | the input display | `T5_TRAINING=inputs` |
| **Inputs + frame data** (default) | both | `T5_TRAINING=frames` |
| Also in the other offline modes | Arcade, Versus, Survival, Ghost too, not only Practice | `T5_TRAINING_ALL=1` |
| Also online | in online matches: only this PC's own inputs, no frame data | `T5_TRAINING_ONLINE=1` |

By default it is shown in **Practice** only. Online it is off unless "Also
online" is ticked, and then it shows nothing about the opponent: no inputs
(they could be the rollback's prediction for a moment) and no frame data.
The attract demo never shows it.

**F2** in the game (while its window has the focus) cycles Off -> Inputs ->
Inputs + frame data for the rest of the session, as long as the setting is not
Off. The texts follow the launcher's language (`T5_TRAINING_LANG=de|en`;
without it the Windows display language): German labels are `GEBLOCKT`,
`TREFFER`, `KONTER`, `DANEBEN`, `AM BODEN`.

Other variables: `T5_TRAINING_ROWS=4..24` (input rows, default 14),
`T5_TRAINING_LOG=<file>` (one line per new input row and per frame-data
result; the tests read it), `T5_TRAINING_STATS=1` (the hook's CPU time every
600 fight frames), `T5_TRAINING_TRACE=<file>` (research: the fight block of
every live frame, see below).

Button numbers are the game's default button setting (1 = Square, 2 =
Triangle, 3 = Cross, 4 = Circle; keyboard A S Z X). If the button layout is
changed in the game's own Options menu, the display still names the
PlayStation buttons by their default meaning.

## It never changes the game

- `src/training/training.cpp` only **reads** guest memory, through three read
  helpers (`rd8/rd16/rd32`); it never stores into it, never calls into the game
  and never touches its input. `tests/test_training.py` checks the source for
  that (every statement naming guest memory must be one of the read helpers).
- It runs at the netplay hooks' frame boundary on the main thread
  (`src/netplay/t5_hooks.cpp` `on_frame_start`, one line), and only for live
  frames: never in a frame a rollback re-simulates (`rb::net::bypass()`), so it
  sees each displayed frame once and never the rollback's work in between.
- Drawing happens on the present thread, into the swap chain's backbuffer,
  after the game's picture was copied there. No game surface, no guest memory
  and no game timing is involved.

### Online pairs with the overlay on one side

The host with `T5_TRAINING=frames T5_TRAINING_ALL=1 T5_TRAINING_ONLINE=1`
(its own inputs drawn every frame), the joiner without it, both sides mashing
buttons and directions (`tools/rollback_net_test.py --mash`), one match of
two rounds to win, Jin vs Lili on stage 20, games muted at below-normal
priority on a PC busy with other agents' games:

RESULTS_PAIRS

## Cost

RESULTS_COST

## How the frame data is measured

The fight block of each fighter (P1 at 0x10090030, P2 at 0x10090900, 0x8D0
bytes apart; NPUB30009 v01.00) was traced frame by frame
(`T5_TRAINING_TRACE`) in scripted fights: direct fight with pad scripts, and
frame-exact ones in local lockstep (`T5_NET_MODE=local`, `T5_NET_SCRIPT` /
`T5_NET_SCRIPT2`), with jabs, lows, strings, throws, whiffs, walking,
crouching and blocking, on hit and on block, for both players. The words the
overlay reads:

| Offset | Meaning |
|---|---|
| +0x15C | attack class of the current move: 0 when not attacking; block and hit reactions have 0 or >= 0x10000 |
| +0x1D2 | 1 = the fighter stands on the right side (forward is LEFT) |
| +0x20C | bit 24: a new move (animation) started this frame |
| +0x214 | bits 16-17: the move's attack is active this frame |
| +0x21C, +0x220 | **can act**: +0x220 low byte 1 and either +0x220 bit 24 (the cancellable end of a move, of a block or a hit reaction) or +0x21C bit 0 (idle, walking, crouching) |
| +0x6BC | health (i16) |
| +0x6D6 | the pad input the fighter read this frame (the game's mask: up 0x1000, right 0x2000, down 0x4000, left 0x8000, Triangle 0x10, Circle 0x20, Cross 0x40, Square 0x80); the CPU's inputs (Practice dummy, Arcade) show here too |

Per live frame `src/training/training_logic.h` (no game, no screen: the C unit
test drives it) does:

1. a fighter that starts a new move in which it cannot act, and that is not
   a reaction to the other's attack, starts an attack; its first active frame
   gives the **startup** (`first active - start + 1`);
2. **contact**: the other fighter starts a block or hit reaction the frame
   after an active frame, or loses health while the move is active; health
   lost during the exchange makes it a **hit** (a **counter hit** when the
   defender was in an attack of its own);
3. **advantage** = the first frame the defender can act again minus the first
   frame the attacker can act again. If the attacker's next move hits before
   that (a string, a juggle), the exchange goes on and the last hit counts,
   with the first hit's startup;
4. a defender that pressed an attack button during its stun: the game opens
   its can-act window up to 5 frames early to keep the press, and starts the
   move at the end of the stun; the frame before that move counts (a press
   that started nothing: the window counts after 20 frames);
5. a defender that cannot act 90 frames after the attacker could: **knockdown**;
6. an attack whose active frames touched nothing: **whiff**, with the frames
   until its user could act again.

**Checked against the game itself**: in local lockstep both fighters pressed
the jab on every second frame (both phases) right after an exchange, so each
jab came out at the first frame its fighter was able to. The difference of the
two jab starts is the true frame advantage; it matched the overlay's number in
every case: Jin's jab (1) is i10, **+3 on block, +9 on hit** (P1 or P2
attacking, defender idle or pressing), whiffs 25 frames. Other values the
traces gave: Jin d+4 i16, -15 on block, -4 on hit; a throw i12. In Practice
Lili's jab against the dummy: i10, +4 on hit.

These are the game's own mechanics (who can start a move first). Published
frame data for other Tekken games often says "+1 / +8" for a jab; the numbers
here are measured, not copied, and both fighters are measured the same way.

## The overlay layer (ps3recomp patch 0045)

There was no text overlay in the runtime. Patch 0045 adds one in a new file,
`libs/video/rsx_overlay.c` / `.h`, and hooks it into `rsx_live_draw.c`'s
present path with two lines (a declaration and the call), between the copy of
the game's picture into the backbuffer and the backbuffer's transition to
PRESENT -- after internal-resolution scaling, so it is drawn at the window's
own resolution and stays sharp at any Internal resolution and window size.

- **API** (any producer thread, one at a time): `rsx_overlay_begin()`,
  `rsx_overlay_rect(x, y, w, h, rgba)`, `rsx_overlay_text(x, y, px, rgba, flags,
  utf8)` (flags: shadow, right-aligned, centred), `rsx_overlay_end()` publishes
  the list for every present from then on, `rsx_overlay_clear()`,
  `rsx_overlay_text_width()`, `rsx_overlay_prepare()` (build the pipeline at
  the next present -- start-up -- instead of at the first list: the shader
  compile takes ~0.1 s). Coordinates are a 1280 x 720 canvas over the picture
  (the letterbox bars are outside it).
- **Font**: our own 5 x 7 bitmap glyphs (ASCII, the German letters, the eight
  directions and neutral as bytes 1..9 in numpad notation), written for this
  overlay, not taken from the game or a font file. A font pixel is a whole
  number of window pixels (`round(px * window scale)`, at least 1) and every
  glyph sits on whole pixels: 2 x 2 pixels per font pixel in a 720p window, 3 x
  3 at 1080p, 4 x 4 at 1440p.
- **Drawing**: one draw call. The quads (48 bytes each) go into an upload
  buffer (8 slots, so a frame the GPU still reads is never overwritten) read as
  a structured buffer through a root SRV; the font is a 1 KB constant buffer
  (root CBV) the pixel shader tests bit by bit; alpha blending, RGB write mask.
  No texture, no sampler, no shader-visible heap: the present's own state is
  not touched; the backbuffer gets one RTV in a heap of the overlay's own.
- **Nothing published** (the default, and always with `T5_TRAINING` unset): the
  present does one load and returns.
- Diagnostics: `RSX_OVERLAY=0` (never draw), `RSX_OVERLAY_TEST=1` (a test card
  with every glyph, at three sizes, when nothing is published),
  `RSX_OVERLAY_STATS=1` (the present's CPU time for the overlay every 600
  presents). The overlay is in the backbuffer, not in the game's surfaces:
  `LD_FRAME_DUMP` shows the picture without it, `RSX_TEST_BB_SHOT=<request
  file>` (patch 0038) reads back the window's picture with it.

## Tests

`tests/test_training.py` (in `tests/`, the CI way):

- builds `tests/c/training_test.cpp` against `training_logic.h` and the
  patched `rsx_overlay.c` (without Direct3D) and runs it: notation for both
  sides, left+right, button combinations; the history; the tracker on frame
  sequences shaped like the traced exchanges (jab +3 on block, +9 on hit, P2
  attacking, a slow low -15, a defender pressing in its stun, a press that
  starts nothing, whiff 25, walking and backdashes give nothing, a string, a
  jab mashed after recovery, a knockdown, a counter hit); the font (every
  character used has its own glyph, no two letters, digits or arrows alike) and
  the layout (whole pixels, whole font pixels at 1366x768 ... 3840x2160, the
  letterbox of a 16:10 window, alignment, shadows, UTF-8, unpublished lists);
- checks that `src/training` only reads guest memory and is called only for
  live frames;
- checks that patch 0045 changes `rsx_live_draw.c` by exactly two added lines;
- checks the launcher setting (default, every choice, the two options, a
  broken saved value) and that every choice has a German text.

In the game: Practice through the smoke harness's menu driver with the overlay
on, scripted attacks and backbuffer read-backs (`RSX_TEST_BB_SHOT`): the panels
in place, the input rows and the frame-data lines as listed in the log; the
test card at 1920 x 1080 (`RSX_OVERLAY_TEST=1`). The smoke suite (quick) runs
without the overlay as before.

## Limits

- The frame hook is the netplay hooks' boundary: with `T5_LATE_INPUT=0` or the
  rollback research modes (`T5_RB_MODE=test|measure`) there is no overlay.
- One frame late on screen: the list is built at the start of the next frame
  from the frame that just ran, and the present of that next frame shows it.
  The numbers themselves are exact.
- Two attacks hitting in the same frame (a trade) give one of the two results.
- Throws, knockdowns and juggles: the startup is right; the advantage of a
  throw is measured until the thrown fighter gets up, a knockdown shows
  `KNOCKDOWN` without a number.
