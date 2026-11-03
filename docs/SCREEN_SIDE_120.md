# Screen side in 1.2.0

`T5_SCREEN_SIDE=dealt|left|right` selects the picture on this PC. As dealt is the default. If the variable is
absent, `T5_ALWAYS_LEFT=1` retains the old checkbox behavior; an explicit new value takes precedence, including
`dealt` and invalid values (both disable mirroring). The launcher migrates the old saved checkbox to its
three-way screen-side choice.

Always left mirrors a casual P2's picture. Always right mirrors a casual P1's picture using exactly the same
renderer transformation from patch 0086: mirror a verified full-screen scene copy, then place the HUD from
its own evaluated boxes alone (no frame history): the timer and the centred titles stay; the side HUD -- bar
frames, both fill layers, round marks, plates, names, the round intro's PLAYER DATA strip -- is placed together
right before the frame's command list runs, from this frame's draws only: art the game flips itself mirrored,
text moved whole to its mirrored box, so the picture has the normal view's layout with the players swapped
(names at the outer edges, bars draining as on that side normally, glyphs in order). The scene-copy test checks the fragment
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

Checked in the game for the HUD (issue #31, 2026-11-03; NETPLAY.md "Issue #31"): offline Always left and
Always right pictures at 720p and 1440p with long and short names (the normal view's layout), every frame
across the HUD's first appearance and the first damage,
a rollback pair (RTT 150 ms, 3 % loss, joiner Always left) and a lockstep pair (host Always right) with
**0 mismatches** and the same hashes, each mirrored bar the length of the other PC's bar for that player.
Not repeated there: rematches, persistent-session choice changes, casual-to-ranked/Quick/tournament
transitions, real sticks.
