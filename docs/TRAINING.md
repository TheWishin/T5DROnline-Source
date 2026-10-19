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
result, and when it is shown or hidden; the tests read it),
`T5_TRAINING_STATS=1` (the hook's CPU time every 600 fight frames),
`T5_TRAINING_AB=<n>` (cost measurement: everything off in every other block of
n fight frames, see "Cost"), `T5_TRAINING_TRACE=<file>` (research: the fight
block of every live frame, see below).

Button numbers are the game's default button setting (1 = Square, 2 =
Triangle, 3 = Cross, 4 = Circle; keyboard A S Z X). The display shows the
pad buttons that were pressed: if the button layout was changed in the game's
own Options menu, Square still shows as 1 even if it is a kick there.

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
two rounds to win, games muted at below-normal priority on a PC busy with other
agents' games:

| Run | Netcode, network | Overlay (host) | Sync | Result hash, host / joiner |
|---|---|---|---|---|
| rb150 (Jin vs Lili, stage 20) | rollback, RTT 150 ms +-5, 3 % loss | own inputs every frame | 0 mismatching frames (checked through frame 5,999, the match 6,530 frames); host 2,022 rollbacks, 14,646 frames re-simulated | `044469dcaf79bf9d` / `044469dcaf79bf9d` |
| ls50 (Jin vs Lili, stage 20) | lockstep, RTT 50 ms, 1 % loss | own inputs every frame | 0 mismatching frames (checked through frame 6,599, the match 6,530 frames) | `cfacb338e8e54943` / `cfacb338e8e54943` |
| rb150f (Lili vs Jin, stage 33), final build | rollback, RTT 150 ms +-5, 3 % loss | own inputs every frame | 0 mismatching frames (through 3,599, the match 3,822 frames); 953 rollbacks, 1,838 frames re-simulated | `418bb04e1217c36d` / `418bb04e1217c36d` |
| ls30f (Lili vs Jin, stage 33), final build | lockstep, RTT 30 ms, 1 % loss | own inputs every frame | 0 mismatching frames (through 3,599, the match 3,822 frames) | `22f00a0a5bedee45` / `22f00a0a5bedee45` |
| rbm (Steve vs Hwoarang, stage 27), merged with main b5c55fa (0043 in the series) | rollback, RTT 100 ms +-5, 3 % loss | own inputs every frame | 0 mismatching frames (through 6,599, the match 6,587 frames); 1,490 rollbacks, 2,301 frames re-simulated | `10f206fe9f8434f5` / `10f206fe9f8434f5` |
| lsm (Steve vs Hwoarang, stage 27), merged | lockstep, RTT 30 ms, 1 % loss | own inputs every frame | 0 mismatching frames (through 6,599, the match 6,587 frames) | `06b0b4ada03bee07` / `06b0b4ada03bee07` |

Both sides reported the same winner and score in every pair. The host's log
(`T5_TRAINING_LOG`) has its own player's input rows only (the final build
does not even follow the opponent online), the present drew the panel in every
frame of the fights (`RSX_OVERLAY_STATS`: ~60 quads per present).

## Cost

Measured on the development PC (Ryzen 9 7950X, RTX 3090) while other agents'
games kept 27-31 of its 32 processors busy, so frame rates say little; the
overlay's own counters do:

| Part | Where | Cost |
|---|---|---|
| Training hook (read both fighters, history, tracker, build the list) | main thread, once per frame | **16-21 us** CPU mean per frame, 40-53 us max (`T5_TRAINING_STATS`, the thread's own CPU time; the wall time is larger only when the busy PC preempts the thread) |
| Overlay in the present (copy the list, lay out ~90-190 quads, one draw) | present thread | **14-16 us** CPU mean per present, 50-170 us max (`RSX_OVERLAY_STATS`) |
| GPU | one draw of a few hundred small quads | not measurable: GPU time per frame median 514 us with the overlay, 521 us without |
| Nothing published (setting Off, or outside its modes) | present thread | one load |

GPU and frame times come from `T5_TRAINING_AB=300` in one direct fight
(Lili vs Asuka, both panels and the frame data shown, `tools/fight_bench.py`,
100 s): everything off in every other 5-second block, so the PC's load hits
both halves alike: frame time p50 18.21 ms on / 18.04 ms off, mean 21.21 /
21.24 ms, GPU p50 514 / 521 us -- the same within the noise. At 60 fps a
frame has 16,700 us; the overlay's CPU work is about 0.2 % of it, on two
threads. The first list after start-up costs nothing extra: the pipeline is
built at the first present when `T5_TRAINING` is on (`rsx_overlay_prepare`),
not in the fight (~0.1 s for the shader compile).

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
| +0x168 | the current move (animation): 0x8001xxxx standing; 0x8002xxxx..0x80FFxxxx the defaults of other stances, among them lying on the ground after a sweep or a throw (0x8004..0x8007 seen) |
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
5. a defender that lies on the ground during the exchange (a sweep, a throw),
   or cannot act 90 frames after the attacker could: **knockdown**, without a
   number (it could act again lying down, which says little);
6. an attack whose active frames touched nothing: **whiff**, with the frames
   until its user could act again.

**Checked against the game itself**: in local lockstep both fighters pressed
the jab on every second frame (both phases) right after an exchange, so each
jab came out at the first frame its fighter was able to. The difference of the
two jab starts is the true frame advantage; it matched the overlay's number in
every case: Jin's jab (1) is i10, **+3 on block, +9 on hit** (P1 or P2
attacking, defender idle or pressing), whiffs 25 frames. Other values the
traces gave: Jin d+4 i16, -15 on block, -4 on hit; a throw i12 (knockdown).
In Practice Lili's jab against the dummy: i10, +4 on hit; her d+4 i16,
knockdown.

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
  jab mashed after recovery, a sweep that leaves the defender lying, a
  defender that cannot act for long, a counter hit); the font (every
  character used has its own glyph, no two letters, digits or arrows alike) and
  the layout (whole pixels, whole font pixels at 1366x768 ... 3840x2160, the
  letterbox of a 16:10 window, alignment, shadows, UTF-8, unpublished lists);
- checks that `src/training` only reads guest memory and is called only for
  live frames;
- checks that patch 0045 changes `rsx_live_draw.c` by exactly two added lines;
- checks the launcher setting (default, every choice, the two options, a
  broken saved value) and that every choice has a German text.

In the game:

- `python tools/training_check.py [--exe ...]`: one game in local lockstep
  (both players scripted frame by frame) with the overlay on: P1's and P2's jab
  on block and on hit, with the attacker or the defender pressing the jab again
  as early as possible, and a whiff. PASS = every result is i10 +3 on block,
  i10 +9 on hit, 25 frames for the whiff (on the final build: 25 results, all
  as expected; again after the merge with main b5c55fa).
- Practice through the smoke harness's menu driver with the overlay on,
  scripted attacks and backbuffer read-backs (`RSX_TEST_BB_SHOT`): the panels
  in place, the input rows (the dummy's CPU inputs included) and the
  frame-data lines as in the log, German texts with a German Windows; back to
  the title: hidden (`hide phase 0` in the log, nothing on the title screen);
  the test card at 1920 x 1080 (`RSX_OVERLAY_TEST=1`).
- The smoke suite (quick) runs without the overlay, as players with the
  setting Off and every existing test do.

## Limits

- The frame hook is the netplay hooks' boundary: with `T5_LATE_INPUT=0` or the
  rollback research modes (`T5_RB_MODE=test|measure`) there is no overlay.
- One frame late on screen: the list is built at the start of the next frame
  from the frame that just ran, and the present of that next frame shows it.
  The numbers themselves are exact.
- Two attacks hitting in the same frame (a trade) give one of the two results.
- Throws, sweeps and juggles: the startup is right; when the defender ends
  up on the ground the result is `KNOCKDOWN` without a number. Juggles are one
  exchange (the last hit counts); a juggle that ends without a knockdown shows
  the advantage after the last hit.
