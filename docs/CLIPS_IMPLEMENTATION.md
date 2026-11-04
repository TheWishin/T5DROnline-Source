# Clips implementation report

Implemented on branch `clips`; changes remain uncommitted. No push, release,
account login, game session, or network access was performed. Implementation,
outputs, and test scratch are in this worktree. Only the required shared heavy
slot files were created outside it, and each owned lock was released.

## Design

`0119-clips.patch` follows hidden-game audio (`0118`), preserving
the rematch tap latch (`0116`) and online borderless (`0117`).
The render thread records a copy of the actual presented RGBA backbuffer into
three fenced D3D12 readbacks. Fence checks, queue handoff, and pad-cache reads
never wait. A mapped readback is borrowed by the worker until conversion
finishes; there is no CPU pixel copy on the render or game thread. Busy capture
slots and a full one-frame queue drop frames. Move-only view ownership returns
readbacks on normal completion, rejection, exceptions, and shutdown.

The BelowNormal worker scales/letterboxes to 1280x720 NV12 at up to 30 fps.
Media Foundation sink writers encode standalone two-second H.264/AAC MP4
segments entirely into capped memory streams, with hardware transforms enabled
and software fallback. The own-mixer tap supplies stereo 48 kHz audio before
host muting, using the same monotonic clock as video. Missing audio becomes
silence. There is no loopback, microphone, desktop capture, guest-state write,
protocol change, or consuming input read.

The encoded ring defaults to 30 seconds, charges allocation capacity against
64 MiB, and evicts whole segments so its beginning remains independently
decodable. It has a 512-segment metadata cap and an 8 MiB current-stream cap.
The three readbacks use at most 94.9 MiB at 4K; there are no additional raw
CPU-frame buffers. NV12, bounded audio queues, remux scratch, and MF/encoder
allocations are additional. This is an explicit bounded queue design, not a
claim that total process RAM is 64 MiB.

Ctrl+F10 (focused) or Select+R3 held one second on one pad coalesces a save
request. A continued hold fires once until released. The worker compressed-remuxes
retained segments to a temporary MP4, then renames it into the Windows Videos
known folder's `T5DR Online` subfolder. It supports Unicode/redirected known
folders and collision-resistant timestamp/process/counter names. Failed saves
remove their temporary output; stale captures are refused. Saving can drop
new capture frames while the worker is doing disk work.

The launcher stores an off-by-default `clips` preference, exposes the control
help in all seven languages, and suppresses capture under effective power
saving. Runtime power policy is checked too, including late iGPU detection.
Missing Media Foundation disables capture safely; both MF DLLs are delay-loaded.
`PS3_CLIPS_SECONDS=5..120` and `PS3_CLIPS_SOFTWARE=1` are diagnostic options.
The launcher uses 30 seconds. Whole-segment eviction normally yields about
28-30 seconds at the default, with less footage before warm-up or after drops.

## Files changed

- `patches/ps3recomp/0119-clips.patch`: runtime CMake integration; new
  `libs/video/rsx_clips.cpp`, `rsx_clips.h`, `rsx_clips_ring.h`; D3D12 present
  readbacks and controls; `cellAudio.c` mixer tap; cached pad API in
  `libs/input/pad_host.h` and `pad_host_win32.c`.
- `CMakeLists.txt`: delay-load `mfreadwrite.dll` as well as `mfplat.dll`.
- `launcher/core.py`: persisted preference, power policy and launch environment.
- `launcher/t5dr_launcher.pyw`: Video clips card, checkbox and control help.
- `launcher/problem_report.py`: include the clip preference in diagnostics.
- `lobby/t5lobby/i18n_de.py`, `i18n_es.py`, `i18n_fr.py`, `i18n_ja.py`,
  `i18n_ko.py`, `i18n_pt_br.py`: translated text; English is the source catalog.
- `tests/c/clips_ring_test.cpp`, `tests/test_clips_ring.py`: native bounded-ring
  edge cases and 20,000 pressure iterations, compiled from the shipped patch.
- `tests/c/clips_mf_test.cpp`, `tests/test_clips_mf.py`: opt-in synthetic Windows
  MF integration, startup policy, mapped-view ownership, pitched input, bounded
  stream overflow, jittered encoding, remux and decode checks.
- `tests/test_clips_setting.py`: eight launcher behavior/catalog tests.
- `docs/CLIPS.md`: player usage, architecture, limits, diagnostics and exact
  pending game-run matrix.
- `docs/CLIPS_IMPLEMENTATION.md`: this report, results and proposed commit.

## Validation and run records

All paths below are relative to this worktree. Shared heavy slots were acquired
atomically and released between builds/encoder runs. Child processes used
BelowNormal priority, muted/background flags, and isolated application folders.
Launcher suites also put TEMP/TMP inside this worktree. Recorded real OpenRecomp
config hashes are unchanged.

| Run / check | Result | Evidence |
| --- | --- | --- |
| Initial existing series preparation | PASS, 85 patches | `build/clips/prepare.log`, `build/clips/baseline-prepare.log` |
| Final clean complete series | PASS, 86 patches | `build/clips/verified-series.log` |
| Final compiled source equality against clean series | PASS | `build/clips/verified-source-check.log` |
| C hook syntax compilation | PASS | `build/clips/hook-compile.log`; initial warning-only pass in `hook-compile-initial.log` |
| Mapped-readback hook syntax compilation | PASS | `build/clips/hook-zero-copy-compile.log` |
| Encoder translation unit compilation | PASS after correcting ICodecAPI include and explicit stream-ID casts | `build/clips/encoder-compile.log` |
| First full host build | FAIL: missing cached-pad declaration in emitted patch | `build/clips/host-build.initial.log`, `host-build.initial.result.log` |
| Corrected intermediate full host builds | PASS | `build/clips/host-build.before-review.log`, `host-build.before-mapped-views.log` |
| Final full Windows host build/link, Release/game-DLL host, two compiler jobs | PASS, exit 0 | `build/clips/host-build.log`, `host-build.result.log`, `host-build.config-guard.log` |
| Native bounded ring | PASS, repeated during review | `build/clips/ring-tests/run.log`, `build/clips/ring-final.log` |
| First standalone synthetic software encode/remux | PASS: 120 decoded video frames, 192512 stereo audio frames; script did not retain a numeric process exit code | `build/clips/mf-software.stdout.log`, `mf-software.stderr.log`, `mf-software.result.log` |
| Immediate opt-in integration attempt while slots occupied | NOT RUN: slot acquisition failed before child launch | `build/clips/mf-suite.initial-slot-busy.log` |
| Opt-in integration with slot waiting | PASS, software and hardware | `build/clips/mf-suite.before-review.log`, `build/clips/mf-suite-final.log` |
| Clip suite before mapped-view optimization | PASS, 10 tests | `build/clips/final-suite/tests-before-mapped-views.log` |
| Final clip suite, including mapped-view ownership and timestamp jitter | PASS, 10 tests, exit 0 | `build/clips/final-suite/tests.log`, `result.log`, `config-guard.log` |
| Disabled, power-saving and missing-MF child runs | PASS: no worker or frame storage | `build/clips/mf-tests/disabled.log`, `power-saving.log`, `missing-mf.log` |
| Final software MP4 round trip | PASS: 120 decoded video frames; 192512 stereo audio frames; monotonic timestamps and tone energy | `build/clips/mf-tests/software.log`, `synthetic software.mp4` |
| Final hardware MP4 round trip | PASS: same decode checks; asynchronous MFT and hardware identity reported | `build/clips/mf-tests/hardware.log`, `synthetic hardware.mp4` |
| Launcher preference/catalog tests | PASS, 8 tests | `build/clips-launcher-tests/clips-setting.log` and final clip suite |
| Initial i18n/catalog checks | PASS, 48 tests | `build/clips-launcher-tests/i18n.log` |
| Existing launcher regressions | PASS, 12 tests | `build/clips-launcher-tests/launcher-regressions.log` |
| First full i18n/UI attempt | FAIL: installed Tcl init not found; 5 errors, 38 skips | `build/clips-launcher-tests/i18n-full.log` |
| Full i18n/UI with worktree-local Tcl scripts | PASS, 98 tests, no skips; seven languages at 100/133/150 percent | `build/clips-launcher-tests/i18n-full-local-tcl.log` and associated config guard |
| Working-tree source/data guard and whitespace | PASS | `build/clips/source-guard.log`, `build/clips/whitespace.log` |
| Real game runs | NONE | Pending matrix in `docs/CLIPS.md` |

The native integration inputs are a generated color ramp and sine tone. MP4s
are synthetic test artifacts kept under ignored `build/`, not repository data.
The full build compiles the host with generic lifter declarations; it does not
include or produce lifted game sources.

## Game runs still required

The exact configurations, directories, actions, durations, and acceptance
criteria are in the table in `docs/CLIPS.md`:

1. Disabled baseline, 90 seconds, both save controls attempted.
2. Hardware capture, 90 seconds, saves at 45 and 75 seconds.
3. Software capture, 90 seconds, save at 45 seconds.
4. Short warm-up save at 3 seconds and a full-ring save.
5. Focused keyboard and held-chord tests on XInput/HID pads and every local port.
6. Muted own-mixer capture, device absence/loss, real A/V sync and channel order.
7. Power saving On/Auto/Off across relaunches.
8. Window/fullscreen/resolution transitions through 720p, 1080p and 4K.
9. Five-minute memory pressure, repeated saves, denied destination and shutdown.
10. Missing-MF boot/fight with capture both enabled and disabled; real Windows N.
11. Interleaved disabled/enabled 90-second performance runs with TWO heavy slots.
12. Loopback-only rollback and lockstep pairs, saving on one/both peers, with
    zero mismatching confirmed frames and identical replay playback hashes.

The <1 ms/frame game-thread budget is NOT yet measured or proven. No capture,
conversion, encoding or file work runs on that thread, and the large render
CPU copy was removed, but thread separation is not a substitute for the
performance pair. Physical input behavior, game audio sync and long-run device
failure behavior also require the above game runs. This change is ready for
that validation, not a claim of completed game-level release acceptance.

`PS3_AUDIO_MUTE=1` preserves the mix for clips. The pre-existing
`PS3_NO_AUDIO=1`/launcher mute path disables the mixer and records silence;
that unrelated behavior was not changed. Dynamic swapchain size changes fail
closed for capture until restart, and output above 4K is skipped.

## Proposed commit message

`feat(clips): add bounded host-side instant replay capture`

Player-facing changelog proposal (CHANGELOG.md was not edited):

- Optional video clips: save the last 30 seconds with Ctrl+F10 or hold Select+R3.
  MP4 clips include game audio and go to Videos/T5DR Online. Recording stays off
  in power saving mode.
