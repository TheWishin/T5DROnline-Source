# DirectInput phantom review (patch 0087)

Reviewed from source only. No build, tests, controller or game were run for this review.

| Code today | Consequence for other PS4-mode sticks |
| --- | --- |
| `0009-controls.patch` uses DirectInput for PS3/PS4-mode sticks, including the Hori, Mad Catz, Qanba, Brook and GP2040-CE families named in its comments. The `ps` preset maps B1-B4 to Square/Cross/Circle/Triangle and B10 to Start. | Those comments describe a layout, not proof that every model/firmware reports it. Keep a model's existing bindings; inspect its raw presses before changing them. |
| `0042-playstation-hid.patch` selects the direct Sony HID parser only for its listed Sony VID/PID pairs. | A third-party stick is not assumed to emit DS4 reports just because its mode switch says PS4. It normally follows DirectInput. |
| `0087-dinput-flap.patch` puts **every DirectInput device** through 1,000 ms probation before assigning a port. There is no Panthera name or VID/PID condition. | The same protection applies to other DirectInput sticks. A healthy new connection gets its port about a second later; it can wait longer if reads/reacquisition fail. |
| A lost device counts as a flap only when lost less than 10,000 ms after discovery. Three such losses within a strict 30,000 ms window quarantine it. Identity matches its instance GUID **or** nonempty HID path. | A second healthy device sharing a product name/VID:PID is not quarantined just for sharing those values. A device that only disconnects later does not meet the short-life condition. A device with valid but incorrect reports that never fails its reads is outside this fix. |
| Quarantine is checked before assigning a port, and is forgotten after absence from enumeration for 5,000 ms on a later scan. The tracking table has eight entries. | Recovery needs a real removal from the device list, not just a button release. This is bounded tracking, not a persistent device blacklist; exhaustion/replacement of the table is not covered by the existing scenario. |
| `di_hold` treats the first DirectInput port read as a baseline: buttons, hat directions and axis directions already held are suppressed until released. | Release controls after plug/replug, then press again. This includes Start held during connection. Direct Sony HID and XInput devices do not use this baseline filter. |

## Regression coverage

`tests/c/pad_flap_test.c` already supplied a fake DirectInput device pair, running the runtime's own hotplug thread, sampler and game reads. The fake phantom initially reports axes at minimum and hat-up, then fails its reads. The scenario checks no phantom port, no ghost presses/movement, quarantine after at most three creations, a working healthy stick with the same product identity, and release/repress after reconnect with B3 held. It is designed to fail against the runtime before 0087.

The scenario now also runs with a clearly synthetic non-Razer identity and the same PS-style button states. This checks that quarantine does not depend on a Panthera product name/VID:PID. Synthetic identifiers and states are test fixtures, not captured device data. No production change was justified by the source review. Both variants remain unexecuted here because the native harness requires a build, which is forbidden in this mirror; the maintainer must build it against the prepared runtime and compare before/after 0087 to confirm its regression claim.

## Still needed

The maintainer must build the runtime and harness. Players with the affected Panthera and other PS4-mode sticks must check normal connection, unplug/replug, held-at-connect controls, two real same-model sticks, and a mode switch while connected. Confirm both normal inputs and the one-second connection delay are acceptable. Hardware identities/report formats not present in this repository remain unknown; no additional VID/PID or report format is inferred here.

For online acceptance, run a real two-PC pair test with **0 simulation mismatches** and correct input on both sides, including reconnect. This review and the synthetic harness cannot prove hardware behavior or online determinism.
