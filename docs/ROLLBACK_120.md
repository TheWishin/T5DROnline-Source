# Rollback feel experiment for 1.2.0

Status: implemented but unmeasured. No game, build, tests, sockets, or servers
were run for this change. The default behavior is unchanged.

`T5_RB_NET_ADAPTIVE_DELAY=1` opts the host into a bounded jitter policy when
choosing the match's initial rollback delay. It requires four valid PING RTT
samples, uses their p95, and only acts at 110 ms RTT or above. It budgets two
predicted frames at that RTT: `ceil(p95_RTT_ms * 60 / 2000) - 2`, with a minimum
of the existing automatic choice and a maximum of three input-delay frames.
`T5_RB_NET_ADAPTIVE_CAP=1..6` adjusts that maximum; the session's existing
lockstep delay is still an absolute ceiling. A cap below the existing automatic
choice never reduces that choice; it only prevents an increase. Equal explicit delay settings
from both players win. The local-mode and replay paths do not use this policy.
Bad or insufficient samples use the existing policy. The environment switches
are read per session and are not launcher or lobby text.

The choice is frozen for the entire session. The existing PING/INPUT delay
field distributes it to the joiner, including an older client; no packet,
capability, hash, or replay layout changes. Changing a delay during a match
would need a separate, negotiated frame-indexed protocol and replay support;
that is deliberately outside this experiment. This initial policy can react
to measured pre-match jitter, not jitter that first appears during the fight.
It does not claim to improve feel until the following measurements pass.

## Maintainer measurements (outside this public working copy)

Use only a private, authorized game workspace. These commands start games and
are instructions for later; they were not executed here. Keep the resulting
game/audio/latency logs outside this public source mirror.

For identical baseline and opt-in pairs, repeat at 110, 150, and 180 ms RTT,
with jitter 0, 5, 15, and 30 ms, and loss 0 and 3 percent. For example, after
substituting private paths:

```powershell
python tools/rollback_net_test.py --out jitter-base --runs PRIVATE_RUNS --exe PRIVATE_EXE --vfs PRIVATE_VFS --fight 26,33,20,2 --matches 3 --seconds 1500 --rtt 150 --jitter 15 --loss 3 --delay 3 --latlog --audio --env T5_RB_NET_DELAY=auto --env T5_RB_SNDTRACE=1 --env T5_RB_NET_ADAPTIVE_DELAY=0
python tools/rollback_net_test.py --out jitter-adapt --runs PRIVATE_RUNS --exe PRIVATE_EXE --vfs PRIVATE_VFS --fight 26,33,20,2 --matches 3 --seconds 1500 --rtt 150 --jitter 15 --loss 3 --delay 3 --latlog --audio --env T5_RB_NET_DELAY=auto --env T5_RB_SNDTRACE=1 --env T5_RB_NET_ADAPTIVE_DELAY=1
python tools/rollback_jitter_report.py PRIVATE_RUNS/jitter-adapt/host/lat.log --sound PRIVATE_RUNS/jitter-adapt/host/rb_sound.log
python tools/rollback_frame_times.py PRIVATE_RUNS/jitter-adapt/host/lat.log PRIVATE_RUNS/jitter-adapt/join/lat.log
python tools/rollback_sound_compare.py PRIVATE_RUNS/jitter-adapt/host/rb_sound.log
python tools/rollback_audio_check.py PRIVATE_RUNS/jitter-adapt/host --ref PRIVATE_RUNS/jitter-base/host
```

Repeat the reports for both peers, and compare baseline and experiment p95/p99
rollback depth, restore-plus-resimulation time, present intervals, late sound
starts, duplicate sounds, and audio gaps. Require **0 state mismatches** on
real paired machines, with forced rollback equivalence as described in
`docs/ROLLBACK.md`. Test new host/old joiner, old host/new joiner, fixed-delay
overrides, lockstep fallback, persistent-session reset, and replay playback.
An old host retains its own policy even if the new joiner enables the switch.

## Audio versus corrected video

The existing `T5_RB_SOUND=resim` policy keeps sounds from the first simulation,
deduplicates repeated starts, and starts newly corrected sounds late. It does
not undo a sound already heard. Re-simulated video is cut; only the final live
frame is submitted. New experimental A/V timing behavior is **not implemented**:
changing the sound-side return values can affect simulation, and delaying or
dropping corrected sounds needs evidence from these measurements first.

`rollback_jitter_report.py` reads existing logs without launching anything.
It reports depth and full restore-plus-resimulation duration from Q events
(M occurs after restore, so Q-minus-M undercounts it), the wait from correction
completion to the next present, and the corrected sound starts' lateness in
frames. These are host submission measures; neither the sound trace nor the
present event measures speaker/photon latency or proves A/V synchronization.
Incomplete and malformed rollback events are counted, and missing present or
sound data is reported as no samples, never zero latency.

Added regressions: `tests/test_rollback_jitter.py` (synthetic logs and wiring)
and `tests/c/rollback_delay_test.cpp` (the real pure policy, caps, insufficient
and invalid samples). They were written but not run, as requested. No runtime
patch is needed: the transport is source in this repository.
