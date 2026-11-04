# Clips: save the last 30 seconds

Clips are an optional Windows host feature. Enable **Keep the last 30 seconds**
in the launcher's settings, then press **Ctrl+F10** while the game has focus, or
hold **Select + R3** on one controller for one second. Release the chord before
using it again. Clips are saved as MP4 in the Windows Videos known folder under
`T5DR Online`. A redirected Videos folder and Unicode Windows user names are
supported. No login, upload, microphone, desktop capture, or loopback recording
is involved.

Recording starts disabled. Power saving disables recording even when the clip
preference is enabled; the preference is retained for the next launch without
power saving. The launcher and runtime both enforce that policy.

## Design

Runtime patch `0119-clips.patch` follows hidden-game audio (`0118`), preserving
the rematch tap latch (`0116`) and online borderless (`0117`).
The feature hooks only the host renderer, host mixer and physical input view.
It does not write guest memory, consume a game button, change input packets,
or participate in rollback snapshots, deterministic state hashes or replays.
The game thread does not encode, copy captured pixels, wait for capture fences,
write files or mux MP4. The less-than-1-ms game-thread requirement still needs
the measured runs below; separation of threads is not a performance measurement.

The D3D12 render thread copies the completed present image into a bounded set
of GPU readback slots. It checks fences without waiting and drops capture work
when slots or the worker queue are busy. The renderer transfers ownership of
a mapped RGBA readback view to a separate worker, which scales to a bounded recording resolution and feeds Media
Foundation. The sink writer permits hardware transforms, with software encoding
available when the machine has no suitable hardware encoder.
The production `rsx_live_draw.c` path captures the composed backbuffer after
the game overlay and letterboxing, before its command list is submitted. Its
dedicated capture fence is signalled after that submission. The older
`rsx_d3d12_backend.c` diagnostic renderer also retains its capture hook.
Recording is 1280×720 at up to 30 frames/s, H.264 at 4 Mbit/s and stereo AAC
at 160 kbit/s. Frames preserve the display aspect ratio with letterboxing.

The audio tap reads the game's own mixed stereo PCM before output muting.
Video and audio use the same host monotonic clock. Audio comes from the mixer,
including when device output is muted; it never comes from a Windows recording
device. `PS3_AUDIO_MUTE=1` retains the mix for recording; `PS3_NO_AUDIO=1`
disables the mixer and consequently records silence. Missing capture work produces a gap or silence rather than block
the mixer or game thread.

Short independently decodable H.264/AAC MP4 segments are encoded into memory.
The compressed ring is limited by both duration and bytes. Whole old segments
are evicted; a save therefore starts at a decodable boundary and can contain
slightly less than the requested duration. Saves age out old segments and refuse
footage older than two seconds when capture has stalled. Saving remuxes the retained segments
on the worker into a temporary file, then exposes the finished MP4. Neither
the ring nor intermediate MP4 segments are written to disk during recording.
The ring also retains at most 512 segments, bounding container metadata even
when repeated saves produce very short segments. The byte budget charges
allocated vector capacity rather than only compressed payload length.

The compressed ring is capped at 64 MiB, with an 8 MiB current-segment stream.
Three D3D12 readbacks hold at most 94.9 MiB together at 3840x2160.
The worker borrows mapped views until conversion finishes; there are no extra
CPU raw-frame buffers or render-thread CPU pixel copies. Capture above that output size is
skipped. A swapchain size change disables capture safely until game restart.
Shutdown joins the encoder before releasing completed readbacks. If a failed
present or shutdown submission leaves a copy in flight, its buffer and fence
remain retained until process teardown, within the same three-slot bound.
Media Foundation and encoder-owned allocations are additional to these
explicit payload caps; they are not an unbounded queue owned by this feature.

`PS3_CLIPS=1` enables recording outside the launcher. `PS3_CLIPS_SECONDS`
chooses a duration from 5 to 120 seconds (default 30), still subject to the
64 MiB cap and whole-segment eviction. `PS3_CLIPS_SOFTWARE=1` disables hardware
transforms for diagnostic fallback runs. Effective power saving still suppresses
capture. `PS3_TEST_NO_MEDIA_FOUNDATION=1` exercises the unavailable-MF path.

`PS3_CLIPS_DIR` optionally selects a clip output directory instead of the Videos
folder. Spaces and Unicode are supported. Its parent directory must already
exist; the selected directory is created if necessary. This also lets local
diagnostics keep their clips in an isolated scratch folder.

## Tests without the game

`python tests/test_clips_ring.py -v` compiles the exact header extracted from
patch `0119` and runs `tests/c/clips_ring_test.cpp`. It covers time eviction,
byte eviction, independently decodable segment boundaries, oversized and empty
segments, invalid timestamps, clock gaps, clear/reuse, signed-limit timestamps,
allocation-capacity accounting, 512-segment metadata eviction, stale capture
expiry, and 20,000
iterations under variable bitrate and time pressure. Before the
patch is emitted, `PS3RECOMP_DIR` can name the prepared runtime checkout.

`python -m unittest discover -s tests -p test_clips_live.py -v` guards the actual
live present hook and compiles the shipped resource-release helper against
synthetic COM objects. It checks incomplete-copy retention, completed-copy
release, device removal, and worker shutdown ordering without opening a GPU,
encoder, game, audio endpoint or input device.

The opt-in Windows integration test is:

```powershell
$env:PS3_CLIPS_MF_TEST = '1'
$env:PS3_CLIPS_WAIT_SLOT = '180'
python -m unittest discover -s tests -p test_clips_mf.py -v
```

It acquires/releases a heavy slot per child process and checks disabled,
power-saving, and missing-MF startup without a worker; bounded stream overflow;
mapped-view ownership/rejection; pitched RGBA conversion; software and hardware
H.264/AAC encoding; four-second compressed remux under timestamp jitter; decode
frame counts, monotonic timestamps and stereo tone energy. Artifacts and logs
stay in `build/clips/mf-tests`. All inputs are synthetic.

The launcher tests check the preference default, launch environment, power
saving policy, persistence and all seven language catalogs. Test environments
must set `OPENRECOMP_HOME`, `APPDATA` and `LOCALAPPDATA` to worktree scratch
directories. Record the real OpenRecomp config hash before and after every
suite. No test should use the owner's settings.

## Exact game runs required before release

All game runs in this checklist are pending until recorded as completed in
the implementation report.

All runs are local/offline. Never log in or contact a public lobby. For each
run use a distinct directory under `build/clips/runs/<name>`, with isolated
`OPENRECOMP_HOME`, `APPDATA` and `LOCALAPPDATA`. Acquire a heavy slot atomically
and release it in a `finally` block. Every game uses `PS3_AUDIO_MUTE=1`,
`PS3_WINDOW_BACKGROUND=1` and BelowNormal priority. Performance runs acquire
two heavy slots. Keep game-derived MP4s, screenshots, samples and dumps under
the ignored `build` directory; do not add them to git.

| Run directory | Configuration and actions | Required evidence |
| --- | --- | --- |
| `disabled` | Direct offline fight, 90 s, `PS3_CLIPS=0`. Attempt both save controls. | No capture worker, ring allocations or output MP4. Baseline frame log and process memory. |
| `hardware-30s` | Same fight and renderer settings, 90 s, `PS3_CLIPS=1`, `PS3_CLIPS_SECONDS=30`, power saving off. Save after 45 s and 75 s. | Two valid H.264/AAC MP4s, independently playable from their first frame, approximately 28–30 s each. Verify the last captured action occurs at each save. Record whether hardware encoding was available/selected, audio/video start/end timestamps and ring peak bytes. |
| `software-30s` | Same test on a machine without hardware H.264 encoding, or the documented software-only diagnostic mode. Save at 45 s. | Software fallback succeeds without render/game waits; valid audio/video and bounded memory. A hardware-enabled attribute alone is not proof that hardware was selected. |
| `warmup-short` | Save 3 s after the first rendered fight frame, then save again after a full ring. | A playable short clip, followed by a normal clip; no fabricated pre-start material. |
| `controls` | Physical keyboard and one XInput plus one direct HID PlayStation controller. Ctrl+F10 while focused; hold Select+R3 0.5 s, then 1.5 s, keep holding 5 s, release and repeat. Try the chord on each local pad port. | Keyboard saves once per press; short hold does not save; a sustained hold saves once until release; each pad works. Physical game input remains visible unchanged. Background keyboard presses do not save. |
| `audio-muted` | Offline fight with music and hit sounds, `PS3_AUDIO_MUTE=1` and clips enabled. Also test absence/loss of the Windows playback device. | Clip retains the game's mix, correct channel order and stable sync; no microphone or other app audio. Silence/device changes never block recording or the game. |
| `power-saving` | Launch with preference enabled and power saving On, then Auto on battery/power saver. Repeat Off on AC. | On/effective Auto suppresses capture; Off permits it. Preference survives relaunch. No MP4 from disabled cases. |
| `resize` | Enable clips, exercise window resize, fullscreen transitions, 720p/1080p/4K output, then save before and after each change. | No stale readback, use-after-free, GPU error or partial MP4. Unsupported dimensions fail safely; captured images have correct orientation, aspect and colors. |
| `pressure-save` | Run 5 min with clips enabled, save rapidly, then deny access to the destination folder and retry. Close the game while saving. | Memory plateaus at documented caps; no unbounded save queue; failures are reported, unfinished temporary files are removed; shutdown completes. |
| `missing-mf` | `PS3_TEST_NO_MEDIA_FOUNDATION=1`, clips enabled, 30 s offline boot/fight; repeat clips disabled. | Game starts without capture; no delayed-import crash. Windows N without the Media Feature Pack still needs one real machine smoke test. |
| `thread-cost` | Interleaved disabled/enabled/disabled/enabled 90 s fights with identical scripts and renderer settings. Two heavy slots, warmed shader cache. | Game-thread added work stays below 1 ms/frame; include median/p95/p99 and worst-case hook durations, dropped captures, render cost, audio underruns and total frame pacing. Record capture/encoder overload separately. |
| `local-netplay` | One rollback pair and one lockstep pair, loopback lobby/P2P only, identical fighter/stage/input scripts; one peer saves at 45 s, then both save. | Zero mismatching confirmed frames, unchanged input logs and replay playback hashes. No public server involved. This is a host-side regression smoke, not a new protocol/state rule. |

For noninteractive fight runs the existing harness accepts
`tools/rollback_test.py --out <name> --runs build/clips/runs --seconds 90 --fight 0,1,0 --polite`
plus `--exe`, `--vfs` and repeated `--env NAME=VALUE` arguments naming the local
build and local game data. The controller/focus run requires supervised input;
do not bring a background game to the foreground while the owner uses the PC.
Use the implementation's synthetic encoder integration test for automated
export before attempting a real game run.

The implementation report distinguishes runs actually completed from this
release checklist. A successful unit test does not establish hardware encoder
selection, game audio sync, controller behavior or the game-thread budget.
