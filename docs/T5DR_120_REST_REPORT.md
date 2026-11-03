# T5DR 1.2.0 remaining-list working-tree report

This is the `codex/rest` branch-scope report, carried into the integrated tree.
The current integration sequence, combined acceptance checklist and agents for
this run are recorded in [INTEGRATION_1.2.0.md](INTEGRATION_1.2.0.md).

Changes are left in this clone for maintainer review. No build, test program,
launcher, game, diagnostic capture, server or network request was run. Git was
used for inspection only; nothing was committed, pushed, merged or released.
No addresses or missing game ABI fields were invented. This branch did not
change private chat; the later `codex/waiting` integration has its own review.

"Done" below means implemented or documented in this working tree, **not proven
in a build or game**. Confidence describes source inspection. Every added test
is unexecuted; old-code failure and new-code success still need demonstration.

| Item | Status and change | Switch or cap | Confidence | Test and remaining proof |
| --- | --- | --- | --- | --- |
| 1. Always right | **Done in source.** Reuses patch 0086's mirror and local input transform for casual P1. Settings and casual lobby row share three choices; old checkbox migrates. | `screen_side=dealt/left/right`; `T5_SCREEN_SIDE`; legacy `T5_ALWAYS_LEFT` fallback. Default dealt. | High policy confidence; presentation unverified. | `test_screen_side.py`, `c/screen_side_test.cpp`, updated `test_always_left.py` and lobby `test_tk_casual.py`. Build, check P1/P2 controls and readable HUD, ranked/Quick/tournament exclusions, persistent changes and replays. Real pair: **0 mismatches**. |
| 2. EU/US lobby | **Infrastructure done; actual cross-region play not enabled.** Server-approved complete build groups, region labels, client validation and room-member checks. Old clients/servers retain exact matching. | `T5L_COMPAT_GROUPS` defaults empty; both clients need `compat_groups`. Tournaments and spectating stay exact-build. | High policy confidence; no cross-build simulation proof. | `lobby/tests/test_compatibility_groups.py`: policy, handshake, client, queue and room fixtures without starting a server. No EU group ships. EU v01.00 is documented incompatible; unsupported EU Online needs game-hook work outside scope and real **0-mismatch** pair coverage before grouping. |
| 3. Background warm-up | **Done in source.** BUILD GAME omits blocking warm-up; separate low-priority queue, hidden window, completed-fight checkpoints, game ownership tokens, all-output pause/close and conservative child-exit checks. Mandatory helper modules added to release packaging. | Six three-second fights; three-minute work budget. Background only on Windows/supported US direct-fight builds. `PS3_WINDOW_HIDDEN=1`, patch 0105. Explicit developer foreground warm-up retained. | Moderate; Windows lifecycle and patch application unverified. | `test_background_warmup.py`, updated `test_speed_115.py`, `test_120_launcher_integration.py`. Build host with 0105; prove hidden behavior, cache reuse, forced-stop recovery and no overlap with any real game. Old prebuilt hosts only minimize. No shaders shipped. |
| 4. Rollback feel | **Partial.** Added jitter-log report and opt-in pre-match p95 delay selection. Delay freezes for the session and travels in the existing wire fields. New corrected-frame audio/video behavior and mid-match adaptation **not done**. | `T5_RB_NET_ADAPTIVE_DELAY=1`, default off; `T5_RB_NET_ADAPTIVE_CAP=1..6`, default 3, bounded by existing delay. | Moderate policy confidence; improvement unmeasured. | `test_rollback_jitter.py`, `c/rollback_delay_test.cpp`. Repeat 110/150/180 ms jitter/loss matrix, correction duration/depth and audio/video submission checks. Old/new host/joiner, replay and persistent paths; real pair **0 mismatches**. |
| 5. True CRT 4:3 | **Not done.** Guest video-out source, structures and constants are absent. No fake enabled Picture format option or guessed ABI patch. | No switch added; existing default unchanged. | High confidence in the evidence gap. | No runtime regression can validate missing implementation. Obtain actual `cellVideoOut.c`/ABI first, then verify 480p status/configuration, PS3 aspect/pixel geometry, output without bars, HUD/camera/effects/menus and pair state equality. |
| 6. Low-end | **Partial.** Experimental SSE2 two-lane software VMX FMA; preserves scalar operation order and fallback. Sound optimization and targeted cheaper lightning setting **not done**: no new profile or verified lightning draw signature. | Compile cap `PPU_VMX_SOFT2=1`, default 0; baseline x64 only, finite operands and canonical MXCSR. Patch 0104. | Moderate arithmetic reasoning; bit identity/performance unproved. | `test_low_end_120.py`, `c/vmx_soft2_test.c`, registered native runner `--only vmx_soft2`. Whole-series apply/build, edge/random bit comparisons, existing FP/SPU suites and strict FP audit; repeatable speed gain and mixed-cap real pair **0 mismatches** before enabling. |
| 7. Unsupported GPU warning | **Done in source.** Conservative local Intel HD 4400-class adapter advisory before worker creation; declining prevents build. Names alone do not prove driver capability; unknown GPUs remain inconclusive. | `gpu_build_warning=true` by default, can be disabled in settings file. | High advisory logic confidence; affected hardware unverified. | `test_gpu_build_warning.py`, `test_120_launcher_integration.py`. Real launcher first-build warning/cancel/continue checks and driver behavior on affected/hybrid hardware. |
| 8. Controller hint | **Done in source.** Once-only first-start explanation plus persistent Controls-window reminder that launcher bindings/macros take priority over Controller Setup. | Persisted `controls_hint_shown` marker; read-only launcher skips it. | High logic confidence; UI layout unverified. | `test_first_start.py`: persistence/restart, modal reentry, save/dialog failure and localization fixtures. Check first-start and Controls layout in each language. Simulation unchanged. |
| 9. Practice | **Display already present and strengthened with tests. Full-neutral reset not done.** Existing bottom placement, per-string-part startup and active windows retained; position reset does not claim a complete neutral state. | `training_pos=bottom` / `T5_TRAINING_POS=bottom`, default top; existing training mode gate. | High source confidence; game observations unverified here. | New unequal-startup `i10~11` then `i13~14`, late-contact and whiff cases in `c/training_test.cpp`, exercised by existing `test_training.py`. Full neutral still needs proven animation/timer/velocity/reaction/contact/collision/input-buffer/dummy fields. |
| 10. Moonlit lines | **Requested investigation done; renderer fix not claimed.** Exact stage-5 capture matrix and conditional code-supported sampling/async-draw leads documented. | Existing resolution, blur/shadow and vertex-thread diagnostic switches; no new behavior. | High command interpretation confidence; low stage-specific cause confidence. | Existing `test_flicker_check.py` covers whole-frame darkness only. Maintainer must run documented captures and inspect narrow lines: exit 0 does not prove line-free output. Any eventual fix needs an old-failing regression and real pair **0 mismatches**. |

Detailed evidence and maintainer commands are in [SCREEN_SIDE_120.md](SCREEN_SIDE_120.md),
[COMPATIBILITY_GROUPS.md](COMPATIBILITY_GROUPS.md),
[BACKGROUND_WARMUP_120.md](BACKGROUND_WARMUP_120.md),
[ROLLBACK_120.md](ROLLBACK_120.md), [CRT_PICTURE_120.md](CRT_PICTURE_120.md),
[LOW_END_120.md](LOW_END_120.md), [GPU_BUILD_WARNING_120.md](GPU_BUILD_WARNING_120.md),
[CONTROLS_FIRST_START.md](CONTROLS_FIRST_START.md), [PRACTICE_120.md](PRACTICE_120.md)
and [MOONLIT_WILDERNESS.md](MOONLIT_WILDERNESS.md). Those game commands are for
the maintainer's authorized game environment; they were not executed here.

All new player messages have entries in German, Spanish, French, Japanese,
Korean and Brazilian Portuguese. English remains the source catalog. Added
`test_120_catalogs.py` checks entries/placeholders statically when later run.
Full catalog extraction and multilingual UI layout checks remain unexecuted.

Integration renumbered the branch's patches to **0104 low-end** and
**0105 hidden warm-up**, after the existing **0103 VRR pacing** patch.
Items using existing runtime sources or already-present behavior needed no
additional patch number. Patch application and a real build remain unchecked.

The original `codex/rest` implementation used twelve sub-agents with separate
file ownership; these names describe that branch's work, not this integration run:
`screen_side`, `compat_lobby`, `shader_warmup`, `rollback_feel`, `crt_picture`,
`low_end`, `gpu_warning`, `macro_hint`, `practice`, `moonlit`, `catalogs_tests`
and independent read-only reviewer `final_review`. The parent integrated shared
launcher files and packaging. Review findings led to pause ownership tokens,
all-output handling, positive child-exit recovery and packaging fixes with
regressions. No test results are claimed from that source review.
