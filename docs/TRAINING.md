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
  three exchanges are listed, the newest on top. Since 1.1.9 a string or a
  juggle lists **every hit on its own line** (Devil Jin 1,2,3: `i10`, `i10`,
  `i25~31 HIT KND`; the number of the move is only on the last hit), a move
  with several active frames shows them (`i13~14`: first and last active frame
  of Jin's d/f+1) and a knockdown reads `KND` at once, without a number.

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
| Position: Top / Bottom | where the lists sit on the picture (1.1.9); Top is the default | `T5_TRAINING_POS=top\|bottom` |

By default it is shown in **Practice** only. Online it is off unless "Also
online" is ticked, and then it shows nothing about the opponent: no inputs
(they could be the rollback's prediction for a moment) and no frame data.
The attract demo never shows it.

**F2** in the game (while its window has the focus) cycles Off -> Inputs ->
Inputs + frame data for the rest of the session, as long as the setting is not
Off. The texts follow the launcher's language (`T5_TRAINING_LANG=de|en`;
without it the Windows display language): German labels are `GEBLOCKT`,
`TREFFER`, `KONTER`, `DANEBEN`, `AM BODEN`.

Bottom puts the inputs' panels and the frame data at the bottom edge of the
picture (the frame data grows upward, the newest line still on top), for players
who want the top free; `training_pos` in `launcher.json`.

Other variables: `T5_TRAINING_ROWS=4..24` (input rows, default 14),
`T5_TRAINING_LOG=<file>` (one line per new input row and per frame-data
result, and when it is shown or hidden; the tests read it),
`T5_TRAINING_STATS=1` (the hook's CPU time every 600 fight frames),
`T5_TRAINING_AB=<n>` (cost measurement: everything off in every other block of
n fight frames, see "Cost"), `T5_TRAINING_TRACE=<file>` (research: the fight
block of every live frame, see below; `T5_TRAINING_TRACE_RANGES=addr:len[:every],...`
adds more guest ranges, hex, every n frames).

For advantage diagnostics, set `T5_TRAINING_DIAG=<file>` before starting the
game (PowerShell: `$env:T5_TRAINING_DIAG = 'training-diag.txt'`). It is off by
default; the text file is overwritten at startup. During tracked moves in
offline live frames it logs both full move IDs, raw flags, `can_act` /
`end_window` / effective `acts`, detected contacts, recovery frames and results.
It only reads game memory, never runs in rollback re-simulation and changes
no tracking rules or overlay numbers. Leave `T5_TRAINING_AB` unset for a
continuous trace; remove the diagnostic variable afterwards to disable it.

Compare Armor King's **f,n,d,df+1**, **b+4 alone**, and **b+4,3**, each against
a blocking dummy, recovering between attempts. Look for a `contact` per hit,
especially the later hit of b+4,3: compare move IDs, `new` and `active` with
b+4 alone. A new contact resets `att_act` / `def_act`; timestamps use `tick`
(0 = not recorded), and `adv_valid=1` means advantage is `def_act - att_act`.
For Bryan d+4 on hit, check whether `can_act` precedes `end_window` while
effective `acts` remains 0. Not compiled or run: a real build, these game
comparisons and a real online pair with 0 mismatches must verify the result.

Button numbers are the game's default button setting (1 = Square, 2 =
Triangle, 3 = Cross, 4 = Circle; keyboard A S Z X). The display shows the
pad buttons that were pressed: if the button layout was changed in the game's
own Options menu, Square still shows as 1 even if it is a kick there.

## Practice tools (1.1.5)

In **Practice**, offline, P1 steers a few practice helpers by holding
**SELECT** and pressing a button. While SELECT is held -- and afterwards
until the pad is let go completely -- the game sees nothing of P1's pad, so a
combo never makes P1 attack, walk or open the menu.

| Combo | What it does |
|---|---|
| SELECT + 3 | both fighters back to where the fight started |
| SELECT + f+3 | the dummy against the wall in front of you, you right in front of it |
| SELECT + b+3 | the dummy against the wall behind you, you in front of it (you switch sides) |
| SELECT + df+3 | you against the wall in front of you, the dummy in front of you (you switch sides) |
| SELECT + db+3 | you against the wall behind you, the dummy in front of you |
| SELECT + 1 | record the dummy in the current slot: your pad plays the dummy, your own fighter stands; again: stop (at most 20 s) |
| SELECT + 2 | play the current slot once; again: stop |
| SELECT + 4 | play the current slot again and again; again: stop |
| SELECT, tap up / down | the next / previous slot (5 slots) |
| SELECT, tap forward / back | what the dummy does: as set in the game's Practice menu, blocks after the first hit, crouches, walks forward and back, sidesteps |

The resets (SELECT + 3 and the four wall resets) happen when both fighters
stand (1.2.0, player report "after a launcher the opponent keeps flying /
is turned around after the reset"): pressed while the dummy is in the air,
lies on the floor or a fighter is in a move, the reset waits -- both pads
neutral, the dummy on the game's own *quick recovery*, a playing slot
paused, the overlay saying `RESET WHEN BOTH STAND` -- and comes as soon as
both stand (at most 4 s, then anyway). A reset only moves the fighters; it
cannot end a fall, a juggle or a move (see "How it works", *Resets wait*).

f and b are as you see them (f = toward the dummy): standing on the left,
f+3 puts the dummy against the right wall. While recording, your pad controls
the dummy in its screen directions: if the dummy stands on the right,
LEFT is its forward (toward you), and RIGHT is its back. After crossing sides,
use the dummy's new side. P1 stands still. Each frame is stored relative to
the dummy's facing, so playback keeps forward/back on either side, including
after a side switch during playback. SELECT shortcuts still use P1's side.

The slots live only in memory while the game runs; they are not saved to a
file. Issue #30 corrected recording directions that had used P1's side
instead of the dummy's. Existing slots already described the dummy's executed
forward/back motion and need no automatic flip. Restarting for an update
clears them, so re-record afterwards; there is no saved format to migrate.

The overlay shows what changed for two seconds under the frame data (`SLOT 2
(3.4s)  DUMMY: CROUCH`), and `REC 1  2.5s` / `PLAY 1  1.2/3.4s` /
`LOOP 1 ...` while a slot records or plays -- also with the overlay itself
Off.

Launcher: **Settings -> Practice tools** (German: *Trainingswerkzeuge*):
SELECT combos on or off (default on), the dummy's behaviour at the start, a
short help text. Environment: `T5_PRACTICE=1`, `T5_PRACTICE_DUMMY=game|block|
crouch|walk|step`, `T5_PRACTICE_LOG=<file>` (one line per action and the
places of both fighters; `tools/practice_check.py` reads it).

### Offline Practice only

Unlike the overlay, the practice tools change the game: P1's and the dummy's
pad masks before the game sees them, and the fighters' places. So
`src/training/practice.cpp` acts only when all of these hold, checked in every
frame:

- the game was started without netplay: no `T5_NET_MODE`, no `T5_CTL_DIR`,
  no `T5_REPLAY_FILE`, and `t5_netplay_enabled()` is 0. `t5_hooks.cpp` calls
  it only from its offline keyread tick (`g_offline`), which a lockstep or
  rollback session, a replay and a spectated match never run; there the ring
  is written in exactly the same order as before;
- the game type is Practice (10 at 0x1008EBAC) and the fight runs (phase 17);
- `T5_PRACTICE=1`.

`tests/test_training.py` checks these gates in the source. Online matches
run the code they ran before: CODE_VERSION is unchanged.

### How it works

- **Places** (traced in Practice, `T5_TRAINING_TRACE`): a fighter's place on
  the floor is x at +0x10 and z at +0x18 of its block (y, +0x14, is 0 on the
  ground) and the angle it faces at +0x30 (it looks along (sin a, cos a)).
  The root -- the place moved by the animation -- is at +0x24 / +0x2C with
  its angle at +0x84, and three 4x4 world matrices of the root (this frame and
  the two before) at +0x700, +0x740 and +0x780: rows 0-2 the rotation (row 2
  the facing direction), row 3 the position. The game takes the root's motion
  from the matrices: a place written to the base alone sprang back or jumped
  (a fighter put 4,000 units away moved another 1,273 in the next frame) and
  an angle written to +0x30 alone was undone. A reset moves and turns all of
  them alike. At the start of the fight the two stand 2,000 units apart
  facing each other (on stage 20: P1 at (1000, 0) facing -pi/2, the dummy at
  (-1000, 0) facing +pi/2; other stages turn the pair).
- **Round start**: the places of the first frame of the fight, kept.
- **Walls**: the walls are the stage's own collision, so they are found with
  it, not read from the stage. A place past a wall is one the game does not
  keep: it puts the fighter somewhere else inside the stage (traced: a fighter
  put 60,000 units out along the line came back 2,400 units off the line). The
  game also keeps the two fighters within about 6,300 units of each other (a
  fighter sliding away alone was held there, on a stage without a wall that
  near). So both slide along the line through them, 1,100 units apart, the one
  that goes to the wall in front, 500 units a frame; the first place the game
  did not keep (moved by more than 80 units: a fighter put down moves up to
  ~30 by itself) ends the slide, and five frames of halving between it and the
  last place it kept find the wall to 16 units. No wall within 30,000 units (a
  second of sliding): the places from before come back and the status line
  says `NO WALL THAT WAY`. They end 1,100 units apart at the wall. Checked in
  Practice on stage 19 (walls about 9,500 units either side of the start) and
  stage 20 (about 8,600): all four wall resets found them in 20-25 frames
  (`tools/practice_check.py`); on stages 17, 18, 21, 22 and 24 a fighter
  walked 8,000-13,000 units without reaching one.
- **Facing**: the game keeps each fighter's own facing -- an angle written
  to it is undone by the animation in the next frame -- and a fighter turns
  to the other one when it starts a move (traced: walking off after
  sidesteps). So when a reset leaves a fighter with its back to the other one
  (the resets that switch sides, and a round-start reset after them), it gets
  a tap toward the other one on its pad two frames later (the dummy on
  CONTROLLER for that tap): both turned around in the game (P1 with its turn
  move 0x0373), which also takes them ~300 units forward, so 24 frames later
  both go back to the places the reset gave them, facing as they now do.
- **Resets wait** (1.2.0, `training_logic.h` `ResetGate`): a reset moves
  places and nothing else. Traced in Practice (Lili vs Lili, the menu's first stage, df+2
  then SELECT+3 0.35 s later): the launched dummy (move 0x009B, class
  0x00010000, hips at ~2,230 instead of ~1,130) put back at its place kept
  falling there, lay (0x003D) and stood only ~120 frames later -- the facing
  tap two frames after the reset did nothing to it, so it could stay turned
  away -- and P1 reset during its own move (0x01C6) ended 1,078 units off its
  place. The game's round set-up is no way out: Practice's round state (17 at
  0x1009322C) is rewritten every frame (written 0, 12 or 38: no effect), and
  a full-neutral reset needs fields we do not know (docs/INTEGRATION_1.2.0.md
  item 32). So a reset (SELECT + 3 and the wall resets) is done only when both
  fighters stand (move 0x8001 at +0x168) and can act. Until then both pads
  are neutral, a playing slot pauses, the dummy is on TRAINING DUMMY 8 (quick
  recovery; the player's setting comes back with the reset) and the overlay
  says `RESET WHEN BOTH STAND`; after 240 frames it happens anyway. Measured:
  55, 59 and 79 frames of waiting after a launcher (0.9-1.3 s), then both
  standing at their places 30 frames later, facing each other.
- **The dummy** follows the game's own Practice menu, TRAINING DUMMY
  (0x1008EFF3, traced by stepping through the menu): 0 stand without
  guarding, 1 stand while guarding, 2 crouch without guarding, 3 crouch while
  guarding, 4 guard against all attacks, 5 standard auto guard, 6 / 7 quick
  roll (fore- / background), 8 quick recovery, 9 backward roll, 10
  CONTROLLER ("control with opponent controller": the dummy plays P2's pad).
  P2's pad alone does nothing to the dummy otherwise. That byte is what the
  menu shows; when the menu closes the game copies it to 0x1008EC63 and
  0x1008EC67, and the dummy acts on those (traced: 9 and 9 after "backward
  roll", 10 and 10 after CONTROLLER, and then the dummy walked and jabbed
  with P2's pad; with only 0x1008EFF3 written it stood still). So a behaviour
  writes all three while it is chosen and gives the player's own choice back
  when it is not (and while the pause menu is open, 0x1008F083 = 0, so the
  menu shows the player's choice): *blocks after the first hit* is the game's own guard --
  stand without guarding until the dummy is hit, then guard against all
  attacks (lows too) until it has been able to act for half a second;
  *crouches*, *walks* and *sidesteps* are CONTROLLER with the dummy's pad
  written into the game's input ring for P2 (down; forward / back 45 frames
  each; a tap of up or down every 50 frames); a recording records and plays on
  CONTROLLER the same way. Checked in the game: the first jab hit the
  blocking dummy and the next ones were blocked; the dummy crouched, walked
  forward and back and sidestepped both ways; a recording (forward, two jabs,
  back) played once and in a loop.

These slots use the game's CONTROLLER mode. This repository does not document
the game's own recording behaviour, so no native recording comparison is
verified for issue #30. The screen-side mirror is also separate: offline
mirroring applies only to Versus, never Practice, and recording adds no mirror
correction.

## The overlay never changes the game

(The practice tools above do, in offline Practice only; everything below is
about the overlay.)

- `src/training/training.cpp` only **reads** guest memory, through the read
  helpers (`rd8/rd16/rd32`) and the bounded experimental comparison reader;
  it never stores into it, never calls into the game and never touches its
  input. Source checks cover the ordinary read helpers and the comparison's
  bounded copy path.
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
| +0x21C, +0x220 | **can act**: +0x220 low byte 1 and either +0x220 bit 24 (the cancellable end of a move, of a block or a hit reaction) or +0x21C bit 0 (idle, walking, crouching). In a hit reaction (+0x15C >= 0x10000) only bit 24 counts (see below) |
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

**Hit reactions that look free too early (1.1.5).** Players saw Bryan's d+4
at -17 on hit. Traced in local lockstep (Bryan vs Jin): Jin's reaction to it
(+0x168 0x0307) sets the idle bit (+0x21C bit 0, +0x220 = 1) nine frames
in, while its cancellable end (+0x220 bit 24) comes at 29 and the standing
move at 30; a jab Jin mashed from the hit on came out only at 30. Every
other reaction traced (blocks, jab and kick hits, juggle hits, P1 and P2)
turns able to act with bit 24 itself. So inside a hit reaction the tracker
now counts bit 24 only: Bryan's d+4 is i15, **-13 on block, +3 on hit**,
both checked with the defender mashing a jab.

**Bryan's taunt (1+3+4).** Players saw it at +14 on hit. Traced the same way
(Jin walking into it, Jin guarding, Bryan or Jin mashing a jab): the +14 is
right, but the overlay called it a block and gave no startup (or the one of
the move before). The taunt is an animation in which Bryan can act from its
first frame -- it is cancellable: a jab pressed in its last active frame
starts in the next one -- so it never looked like a move of its own; its
attack is active 28 frames in. Jin's reaction is a stun (+0x15C 0x10000,
the hit counter of a combo, a guard has 0) for 0 damage, the same whether he
guards or not, and he can act again 15 frames after it began (a jab he
mashed started one frame later). Bryan's jab started 14 frames before Jin's.
Now an attack that comes out of such an animation is a move from the frame
that animation began, a hit reaction counts as a hit without damage, and an
older move no longer lends its startup: **i28, hit, +14**, guarded or not.

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
  defender that cannot act for long, a counter hit, a hit reaction that sets
  the idle bit early (Bryan's d+4), a wind-up and attack move (Bryan's f+1+2)
  and a sidestep into an attack); the practice tools (every SELECT combo
  from either side, P1 hidden until the pad is neutral, the dummy's
  behaviours, the five slots, the wall resets' probe and placement); the font (every
  character used has its own glyph, no two letters, digits or arrows alike) and
  the layout (whole pixels, whole font pixels at 1366x768 ... 3840x2160, the
  letterbox of a 16:10 window, alignment, shadows, UTF-8, unpublished lists);
- checks that the overlay (`training.cpp`, `training_logic.h`) only reads
  guest memory and is called only for live frames, and that the practice tools
  (`practice.cpp`) are called only from the offline keyread tick, act only
  behind their gate (offline, Practice, the fight, `T5_PRACTICE=1`), store
  only through their one helper and never call into the game;
- checks that patch 0045 changes `rsx_live_draw.c` by exactly two added lines;
- checks the launcher settings (default, every choice, the two options, a
  broken saved value; the practice tools on / off and the dummy's behaviour)
  and that every choice has a German text.

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
- `python tools/practice_check.py [--root <build> ...]`: Practice through the
  menu driver with the practice tools on: SELECT+3 after walking away, the four
  wall resets, the dummy's behaviours, a recording played once and in a loop;
  PASS = the places in the practice log are where they should be 30 frames
  after each reset, a wall found for each wall reset, the slot recorded and
  played (1.1.5 final build: PASS on stage 20 -- all four walls, every reset
  in place, the dummy's settings back afterwards; `tools/training_check.py`
  PASS as before, 25 results).
- The smoke suite (quick) runs without the overlay, as players with the
  setting Off and every existing test do.

Issue #30 Practice regression (requires a real build and game; not yet run):

1. With the dummy on the right, record LEFT (forward), RIGHT (back),
   down-left/down-right and a jab. The dummy must follow these screen
   directions while P1 stands still. Stop, then play once and loop: the same
   forward/back sequence must come out. Repeat with the dummy on the left,
   using RIGHT for forward and LEFT for back.
2. Play each slot after switching sides, and cross sides during playback and
   a loop: forward/back must follow the dummy's current side on every frame.
   Cross during a new recording too, changing the held direction for the
   dummy's new forward; replay it from either side. Check that SELECT combos
   and their held-button release frames still inject no recorded attack.
3. Repeat with Screen side set to "Always see me on the left". Practice must
   remain unmirrored with the same controls and playback.

### What 1.1.9 changed (found by players)

- **Strings and juggles** were one line with the first or even no startup
  (Devil Jin 1,2,3 showed `i10` or `startup 0`): each hit has its own line now.
- **Several active frames**: Jin's d/f+1 is `i13~14` (first and last active
  frame), not `i13`.
- **Knockdown** is the defender's hips below half or above 1.4 times its standing
  height, or a lying stance (0x8004 and up); a crouch (0x8002) is not lying. It is
  shown at once as `KND`. A tech roll or wake-up reaction is no longer taken for
  the defender's own move (Nina's d/f+2 showed `HIT +24` after a tech roll), and
  an attacker lying after its own move (a slide) gets no number.
- Checked in the game: `python tools/training_check.py` (jabs, as before) and
  `python tools/training_check.py --moves` (the three cases above in local
  lockstep with the real game; the 1.1.7 game fails it, this one passes).

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

## Experimental animation-frame advantage comparison (default off)

This is a second, diagnostic calculation under `src/training`, alongside the
existing tracker. The overlay continues to display the existing result. The
comparison reads guest memory, keeps its own host-side state and writes
diagnostic text; it never changes guest memory, inputs or game state. It is
limited to offline Practice and the existing live-frame hook, with no reads
from rollback re-simulation. Enabling the normal overlay outside Practice or
online does not widen this experimental gate.

**The supplied mapping currently fails a source-evidence check.** Its alleged
move pointer aliases the x-coordinate already used by this project. Runtime
comparison therefore fails closed: for every existing per-move result it logs
the old result together with
`new=unavailable new_status=mapping_conflict_position_x`, rather than following an
x-coordinate as a pointer or inventing a replacement address. Safely bounded
scalar diagnostics help investigate the claim. The independent new algorithm
and fake-frame tests can exercise hypothetical valid samples, but this
mapping cannot yet produce a justified second numeric result in the game.

The initial idea, address table and name groups came from an RPCS3 overlay
developer, **[contributor name, pending owner approval]**. These are one
person's partial notes, not verified memory documentation for this port. The
remainder of that developer's algorithm has not arrived. Places where the
implementation supplies a policy are marked as missing-algorithm assumptions
in the experimental headers; future notes may change those policies.

Enable deliberately for a maintainer's separately built US game, with a
diagnostic output path outside this source mirror:

```powershell
$env:T5_TRAINING = 'frames'
$env:T5_TRAINING_ADV_COMPARE = '1'
$env:T5_TRAINING_LOG = '<absolute path outside this source mirror>'
```

The new switch is unset/off by default. It has no launcher or lobby setting,
so it adds no launcher/lobby catalog strings. These lines only set variables;
they are not a build or a game launch. Do not collect traces, player logs,
screenshots, game files or saves in this mirror.

Sampling additionally requires a working log file, frame-data mode, a running
Practice fight, no netplay/replay/spectator launch, no local-net test mode and
`t5_netplay_enabled() == 0`. The comparison stays inactive when these conditions
are absent. Its unavailable field belongs to the old result being logged;
there is no pairing with an unrelated latest result from another tracker.
The launch gate rejects nonempty `T5_NET_MODE`, `T5_CTL_DIR` or
`T5_REPLAY_FILE`. Mapping lines include the candidate raw scalar words;
`adv_compare move` lines include `P1`/`P2`, `active_poll`, the old-active-window
anchor or `unknown`, `old`, `old_status`, `new`, and `new_status`. Old statuses
retain `available`, `no-advantage`, `whiff` or `down`, so a stored old number
must only be interpreted when its status permits it. Gate/fight/measurement
resets have separate reason lines.

### Address evidence and contradictions

All addresses below are 32-bit guest addresses, with big-endian values. The
contributor's `0x300000000` is an RPCS3 host mapping claim, not an offset to
add to this port's `vm_base + guest_address` reads. This source establishes
NPUB30009 v01.00 training blocks at P1 `0x10090030`, P2 `0x10090900`, a
`0x8D0` stride. Arithmetic agreement with that stride does not establish a
field's meaning or which player the contributor intended.

The table treats the supplied main-region addresses as candidate **P2**
addresses because of their proximity to our P2 block. That player assignment
is itself unproven:

| Contributor's claim | Candidate offset from our P2 block | Evidence in this mirror |
|---|---|---|
| `0x10090910 u32 MovePtr` | `+0x10`; candidate P1 `0x10090040` | **Conflicts with the existing position interpretation:** `practice.cpp` reads block `+0x10` as floating-point x. `t5_hooks.cpp` also uses these two addresses as block bases for side flags, not as proof of a move pointer. |
| `0x100908E4 u32 AnimFrame` | `-0x1C`; candidate P1 `0x10090014` | Before our documented block; no source proof that it is an animation frame. |
| `0x100909C0 u16 AnimLength` | `+0xC0`; candidate P1 `0x100900F0` | Neither the field nor its alleged copy from move `+0x26` is established here. |
| `0x10090A44 u8 HitboxActive` | `+0x144`; candidate P1 `0x10090174` | Different from the existing active word at block `+0x214` (bits 16-17); the proposed byte and rising-edge meaning are unproven. |
| `0x1009090C u32 MoveBaseIndirect` | `+0x0C`; candidate P1 `0x1009003C` | No source proof of this pointer or its `+0x1E0` move-array offset. |
| `0x100947B3` / `0x1009482B u8 CharId` | Separate addresses, `0x78` apart | Unverified. Existing direct-fight code instead reads a fighter identifier from the low byte of block `+0x4C`, with character-specific caveats. Do not substitute one for the other. |
| Move size `0x4C`; name pointer `+0x00`, HitRank `+0x10`, recovery pointer `+0x14`, Move_Id `+0x1C`, techId `+0x1E`, StartupFrom/To `+0x44/+0x46` | Pointer-relative claims | No prior source evidence for these meanings or the move-array indexing rule. |
| Up to 16 recovery entries, size `0x18`, nextMoveId `+0x08`, frames `+0x10`, type `+0x16` (`0x50` hit / `0x41` block) | Pointer-relative claims | Unverified, including terminators, marker handling and how move IDs resolve to records. |

What **does** fit our build by existing source evidence is the block pair,
stride and byte order, plus the fields already used by `read_fighter`:
`+0x15C` attack/reaction class, `+0x1D2` facing side, `+0x20C` new-move bit,
`+0x214` active bits, `+0x21C/+0x220` action windows, `+0x6BC` health and
`+0x6D6` input. Those existing fields do not validate the new table. In
particular, neither byte order nor readable memory makes a candidate pointer
semantically valid.

The claimed EU-to-US rule `A(x) = x + 0x10B00` is **not established** here.
The supplied main-region numbers are already close to our documented US
fighter blocks, while the contributor's table version is unknown. `EU.md`
documents region shifts that differ by subsystem, a changed phase/config
layout and fighter fields requiring individual checks; ordinary NPEA00019
v01.00 has no Practice mode. Its later EU Online release is a separate case.
No blanket `+0x10B00` or inverse shift is applied by this experiment. The
correct addresses and field meanings for the contributor's exact release
remain missing evidence.

### Provisional logic policies pending the missing notes

`advantage_shadow_logic.h` has no guest-memory access. It consumes synthetic
or validated samples and starts only on an observed low-to-high hitbox edge;
an already-high first sample does not invent a move start. These policies
complete the partial idea for testing and are explicitly **inferred**, not
claims from the collaborator:

- A shared measurement coordinate accumulates **the attacker's** animation
  deltas. A repeated frame contributes zero; a forward jump contributes its
  full delta. A pointer change or backward frame/reset stitches the old
  phase's remaining `AnimLength - AnimFrame` to the new phase's `AnimFrame`,
  without an invented extra tick, and marks the result phase-estimated.
  Whether this is right at cancellations and phase transitions is one of the
  missing decisions. No wall-clock duration supplies advantage.
- Neutral substring groups are checked first: `sKAM`, `cKAM`, `sWALK`,
  `cWALK`, `sDASH`, `sSTEP`, `sJUMP_00`, `sRUN`, `cr2st`, `st2cr`.
  Stun prefixes are `sGrd`, `cGrd`, `sHit`, `cHit`, `sDm`, `cDm`, `Male_`,
  `sDw`, `wDm`, `Ni_crst`. The groups themselves came from the notes;
  deciding action boundaries from names is provisional. Neutral wins even
  when a name also resembles stun or appears in a recovery graph.
- The root name captured at the rising edge and bounded recursively reached
  recovery names form continuation names, excluding neutral. A continuation
  hitbox edge merges into the pending move; an unrelated new edge supersedes
  it. A merged edge retains the move's identity and clock but clears earlier
  defender-contact/release evidence, so the final candidate refers to the
  latest reaction; renewed stun also clears an earlier release. How strings
  should split per hit awaits the remaining algorithm.
- First neutral/non-continuation is the attacker's endpoint, but an
  incomplete recovery graph permits only neutral to establish it. First
  non-stun after observed defender stun is the defender's endpoint. Stun
  already visible at the initial edge is provisionally attributed to that
  move and flagged. Stun on the attacker interrupts it. This can include
  zero-damage taunts without relying on health changes; it cannot prove
  cancellability such as Bryan's taunt.
- Candidate advantage is defender endpoint coordinate minus attacker
  endpoint coordinate, positive when the attacker acts earlier. Recovery
  without observed stun is `no-contact`, not a numeric advantage. Invalid
  samples/clocks, supersession, interruption and a 600-poll abandonment limit
  produce explicit unavailable statuses. The poll limit bounds diagnostic
  state; it is never used as animation time. Reset/gate gaps discard pending
  state rather than bridging sessions. Missing, repeated, backward or
  nonconsecutive poll identifiers abort with `discontinuity`; a character-ID
  change aborts with `identity-change`. Both establish a fresh edge baseline.
  A hitbox edge on a neutral name is ignored.

`advantage_shadow_reader.h` keeps the production mapping disabled at the
known pointer/position conflict. Its synthetic-memory path can check the
proposed big-endian schema, printable terminated names (64-byte bound),
16-entry recovery lists and a graph bounded to 32 move records including
the root. It skips marker IDs, bounds cycles and marks unreadable/unknown
descendants incomplete. These limits are host safety policies, not verified
game format limits. In particular, the notes do not give a proven move-array
extent or ID lookup rule; the `+0x1E0` claim cannot authorize guessed
production move lookups.

### Required maintainer validation

No build, game, test executable or script was run while preparing this
change. Synthetic logic and memory-reader tests are supplied for later
execution without game data. A real build must still establish compilation
on supported targets; fake sequences cannot prove any guest address, name
group, cancellation rule or actual frame advantage.

For a real game comparison, use the maintainer's game installation outside
this mirror. Confirm the title/version first and validate the candidate
fields against observed motion before interpreting any experimental number.
The `MovePtr`/position contradiction above must be resolved, not worked
around by inventing another address. Until it is resolved, an unavailable
experimental result is expected and must not be reported as a correction to
the existing overlay.

1. Start offline Practice on the supported US version, with the environment
   above and practice helpers disabled (`T5_PRACTICE=0`) for manual endpoint
   checking. Use an open stage, away from a wall, and record the character,
   player slot, facing direction and dummy setting separately outside this
   mirror. Confirm that leaving Practice and enabling an online session
   stops experimental sampling; F2 Off/Inputs and any measurement gap must
   discard pending comparisons rather than span unrelated frames.
2. For Armor King, test `f,n,d,df+1`, `b+4`, then `b+4,3`, including delayed
   second hits and `b+4` by itself. For Bryan, test `d+4` and taunt `1+3+4`;
   the taunt's zero-damage stun must still count as contact. For Nina, test
   `f,f+4`. Repeat each as attacker in P1 and P2, and after switching facing
   sides. Let each move finish before the next baseline trial.
3. For each applicable move, compare standing guard, crouching guard,
   standing hit, crouching hit and a clean whiff. Mark impossible conditions
   as such rather than assuming a block or hit. Add counter-hit and knockdown
   cases where applicable. Check string continuation, new attacks after
   recovery, interrupted attacks and phase transitions; an unavailable value
   must retain its reason and must never inherit a previous move's number.
4. Check each fighter's actual earliest action after contact by attempting
   a jab at the earliest legal frame in repeated trials, with both input
   phases. Compare the difference between jab starts with the old result
   and the new animation-frame result for the same move identity. Do not
   treat a stored recovery duration or a displayed number as proof of the
   game's action boundary. In particular recheck Bryan's early idle flag
   and the taunt's cancellability described above.
5. Repeat representative positive, negative and string cases while paused,
   during slow motion and across any animation-frame skip/reset that the
   supported setup can produce. Repeated samples must not add animation
   time; a skipped or ambiguous action boundary must be reported as such.
   Check the logged pair's player, move/phase identity, contact and endpoint
   frames before comparing numbers.
6. Finally run real rollback and lockstep pairs with the experimental switch
   set on one PC and unset on the other. The experimental Practice-only gate
   must remain inactive online. Require **0 mismatching frames**, equal
   result hashes/winner/score, and no experimental guest sampling in replay,
   spectator or re-simulated frames. This new change needs that pair test;
   the historical pair results above do not validate it.

Keep the resulting evidence with the maintainer's private build/test work,
outside this mirror. Obtain the remaining collaborator notes and owner credit
decision before presenting the experimental calculation as verified frame
data.
