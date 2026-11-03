# Background shader warm-up (1.2.0)

BUILD GAME completes when the build process exits. The launcher then schedules
`tools/shader_warmup.py --background --fights 6 --fight-seconds 3 --minutes 3`
separately on Windows. Both worker and hidden game run below normal priority;
the game is muted and uses `PS3_WINDOW_BACKGROUND` plus `PS3_WINDOW_HIDDEN=1`
(runtime patch 0105). Other
platforms and the unsupported European direct-fight program are skipped.

The cap is six short fights and a three-minute worker budget, checked throughout
fight/neutral waits; process startup and shutdown can add to that budget. The explicit
developer tool's default plan remains eighteen fights; it is no longer part of
the launcher's build command. No shader binaries or cache artifacts are shipped.

Before starting a real game, the launcher pauses the worker. It requests a
cooperative shutdown, then kills only the worker's process tree if shutdown gets
stuck. Failure to stop it blocks the real game launch. This closes the hidden
game rather than suspending GPU threads while they hold driver resources. After
the real game exits, the worker resumes from its last fully completed fight.
Opaque per-game holds prevent an old game reader finishing late from resuming
warm-up during a newer game. Those holds cover every output directory and newly
created controllers too, so changing Output folder cannot bypass a real game's
hold. Starting a build and closing the launcher stop queues in every previously
selected folder. The hidden child has an active marker, removed only
after its exit is confirmed. An unexpectedly dead worker with that marker still
present triggers a read-only Windows process-handle exit check for its recorded
child PID. A confirmed exit clears the stale marker, including after the forced
tree-stop fallback. Live children, reused live PIDs and access-denied/unknown
checks block launch. The recorded PID is never itself killed. If the worker died
in the narrow interval before recording the child PID, maintainer recovery must
first confirm the old hidden game is gone before removing `logs/warmup.child`.
The checkpoint is invalidated when the executable stamp or plan changes. Closing
the launcher or starting another build stops the worker too.

`tests/test_background_warmup.py` mocks every process and covers the nonblocking
start, hidden/priority flags, pause/resume lifecycle, fail-closed stop and partial
checkpoints. These tests were written but remain unexecuted in this mirror.
No build, game or server was started. A real Windows build/game run must verify
cache reuse, hidden-window behavior, shutdown under driver stalls, and that a real
game never overlaps the warm-up. This is launcher scheduling and display-cache
work; no simulation fields or memory addresses are changed.
The host runtime must include patch 0105: an older prebuilt host ignores the new
hidden switch and still minimizes its background window. Patch application and a
full runtime build have not been checked here.
