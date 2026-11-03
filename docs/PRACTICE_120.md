# Practice: 1.2.0 request audit

This records the `codex/rest` request audit. The integrated tree also carries
the separate, default-off advantage comparison from `codex/practice-tip`;
see [TRAINING.md](TRAINING.md) for its unsupported-map and diagnostic limits.

The bottom frame-data option, each string part's own startup, and active
windows are already implemented in this public mirror (the 1.1.9 changes in
`docs/TRAINING.md`). No new runtime patch or setting is needed for those parts.

Choose **Settings -> Training overlay -> Position: Bottom**. This saves
`training_pos=bottom` and sets `T5_TRAINING_POS=bottom`; the default remains
`top`. The existing switch positions the input panels and frame-data panel
together. Frame data requires `T5_TRAINING=frames`; online the existing gates
suppress frame data even if the overlay is allowed for this PC's inputs.

`src/training/training_logic.h` tracks a new string part separately and keeps
the first and last frame of its observed active window. It formats `i13~14`
when both frames were observed and `i13` for a one-frame window. Unknown
startup is left absent; the display does not invent move-table data. The
documented measurements apply to NPUB30009 v01.00, not unsupported EU data.

`tests/c/training_test.cpp` already covers Devil Jin's three-part string,
Jin's two-frame active window, and bottom layout. The additional
`test_string_unequal_startups` uses synthetic timelines in both player slots:
`i10~11` followed by `i13~14`, contact on the last active frame, and a whiffed
first part. These are regression fixtures, not claims about a real fighter's
move. They protect against returning the first startup for every string part
or counting the next hit from the original string start.

## Full-neutral position reset: not implemented

The existing offline Practice reset restores **positions**, not a complete
neutral simulation state. `practice.cpp::put_place` has evidence for these
fields only (fighter blocks `0x10090030` / `0x10090900`, NPUB30009 v01.00):

| Field | Proven use |
|---|---|
| `+0x10`, `+0x18`, `+0x30` | base x/z and facing |
| `+0x24`, `+0x2C`, `+0x84` | animated root x/z and facing |
| `+0x700`, `+0x740`, `+0x780` | current and previous root world matrices |

The overlay can **read** attack class (`+0x15C`), animation (`+0x168`), new-move
and active flags (`+0x20C`, `+0x214`), can-act flags (`+0x21C`, `+0x220`),
health (`+0x6BC`), and input (`+0x6D6`). Read observations do not prove those
fields can be safely written or that they are the whole state. In particular,
can-act includes cancellable recovery and is not proof of full neutral.

Before adding full neutral, research must identify the complete animation
controller and transition state, animation time, movement/root-motion and
vertical velocity, hit/block/throw/knockdown and recovery state, active hitbox
and contact bookkeeping, collision state, buffered inputs and pending cancels,
and dummy/recording state that must be cleared or restored. Their complete
locations, safe write values and ordering are missing from this mirror.
Copying a whole fighter block or zeroing guessed flags is not justified.
The existing position-reset implementation therefore remains unchanged.

## Checks still required

No build, test execution, game run, or server contact was performed for this
audit. The maintainer must build and run the training tests, then check bottom
layout at target resolutions, real strings and late-contact active windows in
offline Practice, and position resets while standing, attacking, airborne,
guarding, knocked down and in a throw. Those resets are still positional and
must not be reported as full neutral. Overlay changes are display-only; any
future runtime change must also be tested on a real online pair with the
overlay enabled on one PC and **0 mismatching simulation frames**.
