# Screen side in 1.2.0

`T5_SCREEN_SIDE=dealt|left|right` selects the picture on this PC. As dealt is the default. If the variable is
absent, `T5_ALWAYS_LEFT=1` retains the old checkbox behavior; an explicit new value takes precedence, including
`dealt` and invalid values (both disable mirroring). The launcher migrates the old saved checkbox to its
three-way screen-side choice.

Always left mirrors a casual P2's picture. Always right mirrors a casual P1's picture using exactly the same
renderer transformation from patch 0086: mirror a verified full-screen scene copy, then place every HUD draw
from its own evaluated box alone (no frame history): a side draw of the top HUD band -- bar frame, both fill
layers, round marks, plates, each name glyph -- moves by exactly half the target width, so a side's HUD arrives
whole and glyphs keep their order; the round intro's PLAYER DATA panels swap places with their numbers; the
timer and the centred titles stay; the scissor moves with its draw. The scene-copy test checks the fragment
program's actual texture reads and evaluated geometry. Batches larger than six vertices across the middle are
left whole (never seen in a fight). Issue #31 (own bar empty, names jumping) is fixed by this; see
[ALWAYS_LEFT_FIX.md](ALWAYS_LEFT_FIX.md) for the measured HUD and the rule. It needs no additional
shader or memory address. The old runtime
function names remain for compatibility. Ranked, Quick, tournaments, watched replays and the attract demo
keep their normal picture. Offline Versus retains the old preview behavior: left previews P2, right previews
P1; the corresponding player's pad is mirrored.

The direction swap stays in `sample_local` before network exchange. Both PCs simulate the same exchanged
input; no fighter, camera or battle-state guest field is written by the screen-side code. Offline only the
selected pad's returned data is transformed. This choice changes presentation and how local directions are
translated, never the shared simulation rules.

Added regression: `tests/test_screen_side.py` builds/runs the pure C++ policy matrix in
`tests/c/screen_side_test.cpp`; the old header cannot compile these new choice tests. It also checks the
session and renderer wiring. These tests were authored but remain unexecuted here;
the native policy harness requires a build, which is forbidden in this mirror.

Maintainer validation still required: real build and a casual pair test with **0 mismatches**, testing each
side choice from both assigned slots, normal/mirrored players together, rematches, persistent-session choice
changes, and casual-to-ranked/Quick/tournament transitions. Confirm readable HUD names, bars, timer, scissor
clipping, correct toward/away directions for D-pad and both sticks, and unchanged watched replays. For the
offline preview, check both pad ports independently. No game run or renderer capture was made here.
