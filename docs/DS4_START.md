# DualShock 4 USB: Options / Start (B10)

Reading the source does not show a DS4 USB B10 mapping bug. Patch 0042's
`ps_parse(PSM_DS4, ...)` reads USB report 0x01 button bytes at offset 5.
`ps_fill` puts Options (the second button byte's bit 5) into raw button bit 9,
which is B10. Patch 0009's `ps` preset binds `START=B10`.
`tests/c/ps_hid_test.c` already checks every button through the parser and
effective preset, including Options to START. Custom sections can change that
binding; the code alone cannot tell which settings the affected player used.

The likely explanation **when this happens during an online fight** is the
intentional no-pause rule. `set_no_start(true)` makes
`netplay_core.cpp::pad_into` remove mapped local START before sending it.
Previously this happened silently, before the later `no_pause_rule` diagnostic
could see it. The new diagnostic reports the first mapped START observed in
each gate result, at most two lines per process:

* `START received from mapped local input: blocked by no-pause online before sending`
* `START received from mapped local input: passed by the local START gate; online skips still require both players`

This confirms receipt after mapping; it does not identify a physical device or
prove that the game accepted a skip. The gate and the inputs are unchanged.
In direct fight, both players must press START during an intro or the
between-round skip part; `no_pause.h` applies the same decision to both players,
including rollback and replay. START is deliberately removed during fighting.
The post-match rule keeps START in its window from 40 frames after the match's
decision; this diagnostic alone does not prove a post-match physical press
gets through the earlier local gate.

## Tell the cases apart on the player's PC

Set `log = 2` in `[general]` of `controls.ini` (or `PS3_PAD_LOG=2`), then release
Options and press it again. Existing raw input diagnostics print its effective
mapping. Do not submit full logs or player information to this repository.

| Observation | Meaning / next check |
| --- | --- |
| `B10 pressed -> START`, followed by the new `blocked` line | The mapping reached netplay. Online fighting deliberately blocks pause; test an intro skip with the opponent also pressing START. |
| `B10 pressed -> START`, followed by the new `passed` line | The local gate passed START. Both-player agreement and the frame's final no-pause rule still decide an online skip. |
| `B10 pressed -> (unbound)` or a different target | The effective controls mapping differs. Check `[dinput]`, the model section and that port's override; restore `preset = ps` / `START = B10` only where appropriate. |
| No B10 raw line | Receipt is unproven. Check that the log lists this device and the intended port, whether Steam Input supplies an XInput virtual pad, and USB/direct-HID versus DirectInput selection. An XInput virtual pad logs its own `START` name instead of B10. |
| DirectInput only, Start was already held at connection/port assignment | Patch 0087 holds initial buttons/directions out until released once. Release and press again. This hold rule does not apply to the direct-HID reader. |
| Raw `B10 -> START`, but no new mapped line | Inconclusive: the line is limited to once per result per process; offline menu reads and a controller not selected as the local player do not go through this netplay sample. Check the selected local port and reproduce in a fresh process. |

No speculative remap or pause-rule change was made. The owner must build the
changed core and run `tests/test_start_diagnostic.py` (fake samples, no game),
the existing HID parser test, and the no-pause rule tests in an authorized build
environment. They were not built or run in this working copy. The affected
player must confirm DS4 USB Options in an offline menu and in an online intro,
fight and between-round replay. A real pair test must show **0 mismatches**;
the diagnostic change is intended to leave simulation inputs identical.
