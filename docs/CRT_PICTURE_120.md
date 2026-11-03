# Picture format: 4:3 / 480p investigation for 1.2.0

Status: **not implemented; default display behaviour is unchanged**. Do not
advertise a working `Picture format` choice until the guest video-out path has
been inspected and the checks below pass. There is no enabled switch, shader,
game-memory write, or new runtime patch for this item in this working copy.

## Missing source evidence

The requested implementation point is `libs/video/cellVideoOut.c` in
ps3recomp. That source is not present in this public mirror, and none of the
checked-in patches contains its functions, structures, resolution constants,
aspect constants, or byte-order handling. The mirror contains a pinned
dependency description, not a local dependency source tree. Reading another
working copy or fetching that dependency is outside this task's constraints.
Consequently there is no evidence here for a safe hunk that changes the guest's
reported video mode to 480p and its reported aspect to 4:3. No ABI fields,
numeric constants, or game addresses have been guessed.

The maintainer must supply the pinned video-out implementation and its headers
inside the allowed working copy. Inspect all entry points that enumerate modes,
report current state, accept a configuration, or report an available mode. An
opt-in setting must report a consistent progressive 480-line mode and 4:3
aspect through all of those paths, using the actual ABI constants and guest
endianness. Preserve the existing answers when the setting is off. Do not
assume that a 480-line PS3 buffer is 640 pixels wide: scan dimensions and
display aspect are separate contracts.

## What the existing presentation code shows

Patch `0010-render-quality.patch` introduces `ld_present_copy` in
`libs/video/rsx_live_draw.c`. It scales the guest display dimensions `aw:ah`
into the output area, preserving their ratio and clearing uncovered pixels to
black. Patch `0038-internal-resolution.patch` keeps this presentation path
while changing internal render scaling. This is evidence that changing only
the launcher window size would retain bars for a widescreen guest image.

Removing the bars by stretching that widescreen image does not establish true
4:3. The game must first select its own 4:3 projection and layout using the
video-out reports. Presentation must then honour the reported display aspect,
including non-square pixels if used by the 480p mode. Inspect both the D3D12
and Metal presentation paths before offering a cross-platform setting. The
guest's render-buffer dimensions, display aspect, internal render scale and
physical output dimensions must remain distinct.

## Required tests before enabling the choice

Add host-only ABI tests against the supplied source: off preserves each
existing answer; on consistently enumerates/reports/configures 480p with 4:3;
unsupported requests and secondary-output behaviour stay valid; byte order is
correct. Add presentation-geometry tests for a 4:3 output, non-square source
pixels where applicable, internal-resolution scaling, and switching back to
the default. They must fail with the previous implementation. No source fix
has been made here, so no test is presented as a passing regression for one.

The maintainer must then build and check the game on an actual 4:3 output:

- Confirm the game reads the intended mode/aspect and selects a 4:3 projection;
  circles and character proportions must be correct, with no horizontal
  stretch or widescreen crop masquerading as 4:3.
- Check the full title/menu flow, character and stage selection, fights,
  practice overlays, HUD edges, movies, pause screens and window/fullscreen
  transitions. Distinguish bars authored in movie content from presenter bars.
- Verify the desktop/driver/CRT output is the intended progressive 480-line
  mode. Check the presenter covers the physical 4:3 output without bars or
  overscan hiding the HUD. A launcher setting cannot prove driver scan timing.
- Compare the option off/on in a real two-PC pair test, including rollback,
  with **0 mismatches**. A display option must not change simulation, RNG,
  collision, input mapping, timing, or replay results. If the guest changes
  simulation state in response to the video-out reports, resolve that before
  allowing peers to choose the option independently.

No build, test program, game, or server was run for this investigation.
