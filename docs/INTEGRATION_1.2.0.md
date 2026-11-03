# T5DR 1.2.0 draft integration

Unreleased source integration for maintainer review. Nothing was built, compiled, started or contacted:
no game, test executable or server. All edits remain in this working tree. Git was used read-only;
no fetch, index update, commit, merge, push, tag, release or pull request was made. Work stayed inside
this repository. Starting HEAD for this audit is `2f05eb64dfd8d4f4f8ff9fdddc681db2395cc96f`; the local `origin/main`
reference is `11b9f988b7e92bd883c7bfa3a355a66e44e9a723`. They are different: HEAD already contains the
prior integration and follow-up fixes. No other T5DR/Tekken checkout or game data was opened.

## Branch disposition and application order

The prior integrated tree retains paste-fix, update, delay, badge, port443, charstats, replaydir,
costume-fix, titleskip, rooms, rematch and pacing, plus the existing automatic-spectating work and
follow-up fixes. Accounts remains separate. `docs/PLAN_1.2.0.md` is retained unchanged as the original
proposal; its open acceptance points are tracked below rather than treated as completed results.

For the previous continuation, each responsible agent read its complete path-scoped
`git diff origin/main <branch>`. Together those scopes cover every changed path in all three diffs.
Edits landed in branch **name order**, with shared files released between stages:

| Order | Branch | Inspected revision | Disposition |
| --- | --- | --- | --- |
| 1 | `codex/practice-tip` | `9c36d2ac2027ac688076696a068b0d18444cdfdf` | Shadow advantage logic/reader, opt-in offline comparison, synthetic regressions and training evidence/limits. |
| 2 | `codex/rest` | `c29a44bcfb093e522ba72d82de39de5668f8e4d1` | Three-way screen side, hidden background warmup, controls guidance, GPU advisory, explicit compatibility groups, frozen initial jitter delay, experimental SIMD and request audits. |
| 3 | `codex/waiting` | `1c890a90f51675d7e3a8cbcd57e80d3dd6d4d061` | Private chat/reporting, START/device-loss diagnostics, conservative address mapping and EU review tooling/docs. |
| 4 | `codex/discord3` | `e1798f9536eed7e5c6ae4c2fe37e2f89016bd85c` | Reconciled reset-chord suppression, reflected-copy/HUD screen-side fixes and picture-format investigation with the integrated rules and diagnostics. Compatibility and real-pair gates remain below. |

No branch was merged or applied wholesale over the integrated files. Additive changes were reconciled
with the existing behavior; new files were copied only after their diffs were read.

## Conflicts and resolutions

- **Training:** practice-tip overlaps the earlier contact diagnostics and title-cover integration.
  Kept both configuration/import/read/tracker paths, preserved the boot cover's overlay ownership,
  and reset comparison/old-anchor history at the existing fight transition. The shadow reader remains
  observation-only and fails closed at the documented move-pointer/position-X mapping conflict.
- **Launcher settings and lifetime:** retained replay-directory and auto-spectate validation, updater
  behavior and bounded spectator handoff. Rest's warmup wrapper delegates to the existing game tail;
  waiting's selected-GPU evidence is collected inside that tail. Screen-side migration preserves the
  old left checkbox as a fallback. First-start controls guidance and GPU pre-build advice coexist.
- **Lobby negotiation:** retained the legacy first 16 capabilities and all earlier additions, appending
  `compat_groups`, `private_chat` and `mutes`. Fully enabled clients now send **28**, within the server's
  first-32 limit. Release discovery/TLS cleanup, badges, FT sets, table rooms, rematch UI and skip consent
  remain. Compatibility groups do not bypass table capabilities or automatically enable EU online;
  tournament and spectator matching retain exact-build restrictions.
- **Identity and private chat:** private-message targets use authoritative player row IDs/raw names,
  not rendered DEV badge labels. Chat is negotiated independently and retains the existing roster,
  profile and lifecycle paths. Explicit report receipts do not turn all private chat into retained logs.
- **Runtime:** retained Unicode replay paths, rule agreement and VRR hold markers while adding screen
  side, frozen host-selected jitter delay and once-per-process START diagnostics. No memory address
  was guessed. Rest's new training/string cases retain the earlier issue-30/31 regressions.
- **Patch collision:** rest's `0103-low-end.patch` collided with existing `0103-vrr-pacing.patch`.
  Kept pacing at 0103; renamed low-end to **0104** and rest's `0104-warmup-hidden.patch` to **0105**.
  Updated internal comments, test paths, native runner and docs together.
- **Catalogs and packaging:** combined both drafts' keys with every earlier feature in all six
  translations; retained active known-message groups. Added all four new launcher modules to release
  packaging; existing globs include new lobby/server modules.
- **Documents:** preserved existing ranked/character-statistics/FT and EU material. EU's standalone
  exact-match wording now distinguishes the default from explicit operator-approved groups; no EU
  group ships. Branch-only rest report claims are labeled historical, not results from this run.

## One patch sequence and build identity

The build discovers the complete patch series in filename order. Numeric prefixes are unique.
The integrated tail is:

1. `0088-online-boot-overlay.patch`.
2. `0089-ingame-rematch-overlay.patch` (previously reconciled from rematch's duplicate 0088).
3. `0100-macos-metal-slot-wait-warning.patch`.
4. `0101-macos-fps-slow-frames.patch`.
5. `0102-macos-pad-file2.patch`.
6. `0103-vrr-pacing.patch`.
7. `0104-low-end.patch` (rest's 0103).
8. `0105-warmup-hidden.patch` (rest's 0104).

`CODE_VERSION` is now **11**, separating the reset-input and audit changes from integrated
version 10, earlier version 9 and title-cover-only version 8. Patch digest changes also invalidate stale builds. Since
`code_id()` does not directly hash `src/`, the explicit version protects the source changes as well.
Full application to the pinned dependency and compilation remain unproved in this mirror.

## Ordered acceptance matrix: every 1.2.0 feature and PLAN open point

Perform rows in order in the **maintainer's real project**. Nothing in this table authorizes running
a build/game/server or storing captures in this mirror. Start with optional experiments off. An
"integrated" state means source is present, **not passed acceptance**. Every game/runtime row requires
identical agreed outcomes and **0 mismatching simulation frames on two PCs** in lockstep and rollback,
direct and relay, including repeated rematches and replay where applicable. Host-only changes must
leave simulation identical even when their settings differ between peers. Retain all captures privately
outside this mirror. Launcher/service-only rows explicitly say when a game is unnecessary.

| Order / feature | Switch / default | State and open point | Exact maintainer acceptance procedure |
| --- | --- | --- | --- |
| 1. Build, packaging, catalogs and baseline | `CODE_VERSION=11`; sorted patch filenames; experiments off | Source integrated; application/link/package/tests unproved | Run the named offline regressions below, apply the entire series to the pinned dependency, build native and launcher targets, check imports/exports, all language assets and old-build rebuild prompt. Establish a normal two-PC fight/rematch/replay baseline with **0 mismatches** before opt-ins. |
| 2. Clipboard and keyboard editing (`paste-fix`) | Always-on widget shortcuts | Integrated; real keyboard/layout behavior open | In real launcher entries/text/spinboxes on Latin and non-Latin layouts exercise Ctrl+C/V/X/A, AltGr and ordinary keys; verify no doubled/swallowed keys and selection/clipboard contents. Repeat all languages; game unnecessary. |
| 3. GPU pre-build warning (`rest`) | `gpu_build_warning=true` | Advisory integrated; cannot establish D3D12 support | On HD4400-class and hybrid PCs start first build: advisory appears before worker; Cancel starts none, Continue proceeds; unknown adapter remains inconclusive and selecting another GPU is respected. Check every translation. |
| 4. First-start controls guidance (`rest`) | `controls_hint_shown=false` until shown | Integrated; actual dialog persistence/layout open | Fresh launcher shows localized bindings/macros priority guidance once, restart does not, resetting marker repeats; read-only checks do not consume it. Open Controls and inspect reminder in every language; game unnecessary. |
| 5. Lobby-first signed updates (`update`) | Normal updater; cached lobby `latest_release` | Integrated; production cache/fallback/signatures unproved | In maintained test environment try valid cached metadata, lobby unavailable, version refusal, stale/malformed metadata and GitHub fallback; accept valid signed release only and reject wrong signature. Verify refusal metadata survives cleanup. Game unnecessary. |
| 6. TLS control fallback (`port443`) | Server `T5L_TCP_FALLBACK_PORT=0`; TLS client fallback 443 | Integrated opt-in; real reachability/session recovery open | Permit normal port, then block it and use 443 with same pin; reject wrong certificate, reconnect session. Direct/relay games still use UDP and give **0 mismatches**; 443 is not a UDP fallback. |
| 7. DEV badges, mentions and notifications (`badge`) | Negotiated `badges`/`mentions`; admin badge; notification preference | Integrated; schema upgrade/layout/focus open | Grant/clear DEV and verify roster/profile/chat; mention mixed-case/spaced names with Tab, focused/unfocused/muted notifications. Confirm decorated labels never alter raw action targets. Upgrade existing DB and review rollback. Game unnecessary. |
| 8. Per-fighter ranked statistics (`charstats`) | Profile; negotiated `ranked_chars` | Integrated; totals/layout open | Record ranked games/sets across multiple characters, draws/forfeits; profile every fighter's games/wins/losses/draws/rate against history, scroll long profiles, keep account rating unchanged and old-server fallback usable. |
| 9. Replay directory and verified moves (`replaydir`) | `replay_dir`, `replays`, `T5_REPLAY_DIR` | Integrated; Unicode I/O/move failure recovery open | Record and rematch into a Unicode path, browse/play and create a problem report; verify collision/corrupt-copy/failure retains source and never overwrites existing files. Pair recording/playback results/hashes: **0 mismatches**. |
| 10. Canonical costume fallback (`costume-fix`) | Automatic | Fixed historical absent/zero replay compatibility; runtime proof open | Both slots default/custom/missing/rejected customization and repeated rematches: same canonical live fallback bytes. Old absent/zero-block replays retain historical zero bytes; verify exact setup/hashes and **0 mismatches**. |
| 11. Online connecting cover (`titleskip`) | Normal online direct-fight cover | Integrated; slow-load handoff/render ownership open | Cold and deliberately slow logo/movie/title loads remain covered until interactive select/fight readiness; no input consumed or stale covered frame after handoff, offline presentation retained. Repeat rematches with **0 mismatches**. |
| 12. Auto / 0–8 challenge delay (`delay`) | `input_delay8`; explicit selection or Auto | Integrated; negotiation across FT/rematch open | New peers challenge each setting including 8 with FT and rematches; selected delay persists. Persistent ranked continuations retain the server-fixed delay even when local preferences differ. Old client/server permits legacy range only. Direct/relay lockstep/rollback fights: **0 mismatches**. |
| 13. Casual FT sets (`rooms`) | `first_to=1/2/3/5/10`; `casual_sets` | Integrated; next-game ownership/results open | Challenge/invite/classic-room sets through completion, disconnect/reconnect; keep score/sides/delay and prevent rematch prompt from pre-empting active automatic set progression. Require one result per game and **0 mismatches**. |
| 14. Simultaneous community tables (`rooms`) | Room `mode=tables`; `room_tables` | Integrated; concurrency/privacy/capacity open | At least four players run two tables plus viewers/relay concurrently; results, ready/cleanup and spectators stay with their table. Even size-two tables show no classic rematch/line controls; **0 mismatches** on both matches. |
| 15. Automatic spectating (preserved baseline) | `auto_spectate=false` | Existing behavior retained; warmup/PM integration needs checking | Enable after 15s continuously idle (own room, friends, public rooms); refuse while queued/challenged/ready or a game is running, retry >=30s and target cooldown 120s; keep hidden-room membership/stream quotas. End/switch match, then receive own challenge/ready/start: spectator cancels and stops within bounded handoff before own game starts. Disable/disconnect/close leaves no pending callback, reader or second game; warmup must also yield. |
| 16. Three-way screen side (`rest`) | `screen_side`, `T5_SCREEN_SIDE=dealt/left/right`; absent uses `T5_ALWAYS_LEFT` | Integrated; input/render mapping open | Casual P1/P2 with asymmetric choices: D-pad and both sticks toward/away, readable timer/HUD, scissor/clip, change choice on persistent rematch. Offline Versus mirrors selected port only; ranked/Quick/tournament/replay stay excluded. **0 mismatches**. |
| 17. Training strings, bottom layout and contact diagnostics | `training=frames`; `training_pos=top/bottom`; `T5_TRAINING_DIAG` unset | Integrated/retained; real move/recovery interpretation open | Offline both slots: unequal-startup strings, late active contact, whiff, knockdown/tech/crouch and scale changes; each hit owns startup/window and bottom panels fit. Online own-input-only gate hides advantage; overlay on/off pair remains **0 mismatches**. |
| 18. Shadow advantage comparison (`practice-tip`) | `T5_TRAINING_ADV_COMPARE=1` + `T5_TRAINING=frames` + working `T5_TRAINING_LOG`; off | Diagnostic integrated; live move-pointer/position-X conflict blocks replacement result | US offline Practice: Armor King f,n,d,df+1, b+4, b+4,3; Bryan d+4/taunt 1+3+4; Nina f,f+4, both slots/sides, guard/hit/whiff/string/reset. Normal overlay unchanged; current reader must report `new=unavailable`, `mapping_conflict_position_x`, never fabricate recovery. Gate exits/online/replay/spectator/resim do not sample; one peer enabled still **0 mismatches**. Establish missing map evidence before any new-result claim. |
| 19. Explicit pad-only rematch / Next / ready (PLAN) | `T5L_INGAME_REMATCH=1` + `T5_INGAME_REMATCH=1`, both off; `ingame_rematch_v1` | Candidate integrated; full pad/focus/room/process flow unproved | First switches off/old binary fallback. Then pad-only accept/wait/decline/Next/ready with launcher behind, ten rematches with character changes and fresh opponent in process and persistent modes. Password/invite/hidden classic rooms, both community rotations with >=3 members, ranked/tournament authority; one report/vote/start, no stuck select or public-queue escape, **0 mismatches**. |
| 20. Local UI protocol, input edges and multilingual overlay (PLAN) | Same rematch switches + game capability/ack | Candidate integrated; ownership, fonts and failure fallback open | Hold attack at KO; focus away/back and reconnect controller: require release then fresh edge. Inject stale/malformed/reordered/duplicate/expired/wrong generation/session/prompt/match actions with delayed async dispatch; no double vote or unintended fight. Lost ack/heartbeat/unsupported game falls back. Training hide/menu clear coexist; Japanese/Korean/long names/button hints wrap and scale. **0 mismatches**. |
| 21. Optional automatic casual rematch (PLAN) | `T5L_CASUAL_REMATCH_POLICY=both_confirm` default; `auto_unless_declined`; classic-room `rematch_policy` | Candidate integrated; countdown/cancellation authority open | Both clients show cancellable countdown; decline just before expiry sends no accept, uncancelled countdown produces mutual server-owned votes. Disconnect/expiry cancels, no ranked-forfeit confusion, community bypass or private-to-public queue. Repeated rematches **0 mismatches**. |
| 22. Agreed after-round auto-skip (PLAN) | Room permission + both player consents; `auto_skip_after_round_v1`; off | Simulation-affecting candidate; mandatory rule agreement proof | Test off/off, on/off, off/on retain mutual manual behavior; on/on eligible nonfinal states 8/9/0xC use symmetric pulses, intros remain manual, fighting never pauses, final decision retains 40-frame guard and 3/20 pulse cadence. Roll back at boundaries; mismatched packed rules refuse before fight including reused session; **0 mismatches**. |
| 23. Replay/spectator/session compatibility (PLAN + discord3) | New recordings format 7 / SESSION 3; readers retain formats 1–6 / SESSION 1–2 | Versioned reset-input semantics integrated; runtime proof open | Toggle agreed skip consent between games: changed rule starts fresh compatible session; unchanged rule can reuse. Replay legacy input/reset rules unchanged; current recording/playback/spectating uses guarded reset filtering. Old readers reject new versions before simulation, guarded upgrades cannot downgrade policy, single reports and **0 mismatches** throughout. |
| 24. Hidden post-build warmup (`rest`) | Launcher controller; six short fights, bounded worker; `PS3_WINDOW_HIDDEN=1` patch 0105 | Integrated; actual driver/cache/child-stop lifecycle unproved | After real build UI stays responsive, worker hidden/muted/low priority. Real game never overlaps worker across output folders/controllers/late reader tokens; crash/driver stall/unknown child blocks launch. Close/rebuild stops all workers; completed checkpoints resume and actual cache is reused; host-only, DLL-only and subsecond rebuilds invalidate the checkpoint identity. |
| 25. Frozen initial jitter delay and report (`rest`) | `T5_RB_NET_ADAPTIVE_DELAY=1` off; `T5_RB_NET_ADAPTIVE_CAP=1..6` default 3 | Opt-in integrated; real benefit/A-V correction unproved; no midmatch adaptation | Host/joiner fixed override and auto at RTT 110/150/180ms × jitter 0/5/15/30ms × loss 0/3%; require >=4 valid echoes, frozen agreed delay and existing lockstep ceiling. Check resets/rematches/replays; compare rollback depth/full-Q cost, late/duplicate presents and audio gaps, **0 mismatches**. A-V correction remains future work. |
| 26. VRR baseline and rare game-thread tail (PLAN) | `PS3_VRR_PACING=0`; frame/latency/game-thread logs, narrow scheduler trace | Measurement hooks/procedure integrated; cause of 14/19ms and ~0.5% stalls unknown | Focused visible player setup, no Special K/driver cap, >=10min quiet and loaded; correlate release/wake/game/SPURS/input/rollback/flip/ready/Present/display wall versus CPU. Measure logging overhead, p99.5/p99.9/worst and >17.5/20/33.4ms counts; include missing rows/time-sync skips, classify tail before optimizing. |
| 27. Timer-only / coordinated VRR cadence and latency (PLAN) | `PS3_VRR_PACING=0/1/2`; mode 2 tearing + overlap; `PS3_VRR_BUDGET_MS`; `PS3_VRR_SPIN_US` default 0, max 200 | Default-off candidate; no proven latency-neutral pacing gain | Alternate baseline/timer-only/controlled, fixed input delay, smallest stable budget. Measure actual Present-entry and independent displayed cadence ~16.6833ms (initial ±0.5ms tolerance needs evidence), p50/p95/tail random-phase input-to-visible must not worsen. No hidden dropped/duplicate frames, queue growth or catch-up pairs; report all misses separately. |
| 28. VRR recovery, platform and determinism (PLAN) | Same modes; existing fixed-refresh/unsupported fallback | Candidate; timer/renderer ownership and slow-PC throughput open | Deliberately slow CPU/GPU/backpressure; timer failure, occlusion/minimize/restore/resize/monitor/power, exclusive/borderless, VRR/fixed59/60/high-refresh nonVRR, dGPU/iGPU. Late picture presents once, no extra full wait/burst; stale targets reset, time-sync skip counted once, handover/ring safety retained. Different pacing modes per peer, replay/rematches: **0 mismatches**, no extra/missing simulation frame. |
| 29. Experimental low-end SIMD (`rest`) | Compile `PPU_VMX_SOFT2=1`; default 0, baseline x64 no-FMA, patch 0104 | Partial, off; bit identity and performance unproved | Before game run native edge/random/NaN/subnormal/NJ/alias/MXCSR tests against scalar with contraction off. Then repeat CPU A/B, pair cap on/off and hardware-FMA PCs in lockstep/rollback+jitter: **0 mismatches** and repeatable gain before enabling. Sound arithmetic unchanged. |
| 30. Sound and targeted lightning cost (`rest`) | No new switch; existing `PS3_EFFECTS=0` is broad diagnostic only | Not implemented; profiling evidence missing | Profile actual sound thread and EWGF draw costs privately first. Future sound bit tests plus cue onset/duration and targeted visual comparisons, full pair **0 mismatches**; broad effects suppression cannot prove targeted lightning optimization. |
| 31. True CRT 480p / 4:3 (`rest`) | No implemented switch | Blocked: pinned `cellVideoOut.c` ABI evidence absent | Obtain real mode/state/configuration ABI evidence before implementation; then actual progressive 480-line 4:3 projection/proportions, menus/HUD/movie without stretch/crop, switch-off baseline and mixed-setting pair **0 mismatches**. Window resizing alone is insufficient. |
| 32. Full-neutral Practice reset (`rest`) | No new switch; existing position reset only | Blocked: complete safe animation/timer/velocity/reaction/contact/collision/input/dummy writes missing | Check current resets standing/attacking/airborne/guard/KD/throw remain positional. Establish all missing fields/write ordering, then future neutral-state regression and pair **0 mismatches** where applicable. Do not zero guessed flags or copy fighter blocks. |
| 33. Moonlit Wilderness lines (`rest`) | No fix/switch; existing native/lowest/blur/shadows/thread diagnostics | Investigation only; focused surface/address evidence missing | Stage 5 / t5s06, Kazuya/Raven at documented moments: compare five documented capture variants and inspect thin strips/triangles/edges; whole-frame checker exit 0 is insufficient. Identify surface then write focused regression, visual and pair **0 mismatches** before claiming fix. |
| 34. Build compatibility groups (`rest`) | `T5L_COMPAT_GROUPS` empty default; `compat_groups` | Explicit operator allowlist integrated; no approved EU group ships | Default/different/unapproved/net3/no-cap refuse; only proven full build IDs/net version group. Exercise queue/challenge/invite/all members in classic/community/table rooms, FT/rematch and resume; old clients, spectators and tournaments retain documented exact restrictions. Approve group only after real cross-build pair **0 mismatches**. |
| 35. EU review / conservative address mapping (`waiting`) | EU v02 online hooks unsupported; `tools/eu_review.py`, `tools/addr_map.py` | Review tooling integrated; required license/layout/sound/SPURS/code-end/address evidence missing | Owner-local pinned-program review with no nearest-address inference; tied or unresolved mappings remain missing. Never group incompatible v01. Before approval run EU-EU then EU-US picks/stages/fights/FT/rematch/rollback with **0 mismatches** and all mapping evidence; reports/assets stay outside this mirror. |
| 36. DS4 START and phantom-pad diagnostics (`waiting`) | No input rule change; `PS3_PAD_LOG=2`; existing patch 0087 probation | Diagnostics/harness integrated; hardware diagnosis open | USB Options in offline menu, then online intro/fight/between-round with both players: mapped START receipt reports blocked/passed at most once each. Reconnect held buttons require release; two same-model/PS4-mode sticks and mode switch show no phantom port/press after 1s probation. Native flap harness first; pair **0 mismatches**. |
| 37. Selected-GPU device-loss advice (`waiting`) | Automatic evidence collection; real device-loss exit 12 versus init failure 13 | Advice integrated; renderer/driver not fixed | HD4400 actually selected + DXGI removal yields localized advice; hybrid different GPU, unknown adapter and init failure get appropriate distinct diagnosis. Evidence survives tail wrapper; build warning and warmup cleanup still operate. Collect real driver evidence privately; no promise that advice fixes rendering. |
| 38. Ranked policy owner confirmation (`waiting`) | Existing queue/lag/set/reconnect settings; no new policy switch | Documentation/request confirmation, not a changed ranking algorithm | Owner checks docs/RANKED.md table: between-game leave while opponent away at 0-0 versus after a win; normal close versus crash/loss early/late in fight, previous wins, both absent, tournament 0-0, lag-free exit, 90s recovery, side coin, ratings and leaderboard game/set counts. Real queue/set/disconnect/return/timeout/history tests retain authoritative outcomes; **0 mismatches**; record any requested policy change separately. |
| 39. Private chat, unread/mute/block (`waiting`) | `LobbyClient(private_chat=True)`; server `T5L_PRIVATE_CHAT=true`; cap + feature | Integrated; privacy and actual Tk lifecycle open | Maintained A/B/C clients: A↔B from roster/profile raw identity including DEV; C gets no PM/broadcast. Verify unread/focus, mute/unmute, both directions blocked, logout/reconnect session clearing. Old/disabled server controls unavailable and no PM requests. Game unnecessary. |
| 40. Explicit private-chat reports (`waiting`) | `T5L_PRIVATE_REPORT_DAYS=30`; `T5L_MAX_PRIVATE_REPORTS=1000` | Integrated; moderator receipt/prune/delete proof open | Explicitly select 1–5 signed lines to report; moderator inbox contains only those chosen lines. Reject forged/expired receipts and oversized/repeated-invalid requests; check retention pruning/deletion and muted/blocked context without storing all PMs. Game unnecessary. |
| 41. Spectator/replay exit and cleanup (preserved baseline) | Manual SELECT/window close; SELECT exits even `T5_REPLAY_EXIT=0` | Preserved; warmup and new callbacks require repeat proof | Recorded/live and lockstep/rollback: exit at no-SESSION/no-MATCH/loading/stalled-input/barrier/pause/rematch-gap/buffered-next-fight boundary. Own challenge/ready/start during request/answer/boot/playback cancels only owned spectator before driver dispatch; stale answer never boots. Disable/stop/disconnect/launcher close frees slot with no stuck white screen; measure event-to-death/own-game boot. Live players with/without viewers and replay remain **0 mismatches**. |
| 42. Online reset chord and reflected-copy HUD (`discord3`) | Reset guard in current online sessions; replay version gates; screen side as row 16 | Source integrated; native input consumers and partial HUD correction unproved | START+SELECT from one or both pads, scripted inputs, pause/intro/replay/post-match boundaries and rollback preserve SELECT but never deliver reset chord. Offline emergency reset remains. Legacy replay semantics remain as row 23. Reflect actual picture-copy quads only; texture flip flags alone do not identify copies. Check timer/HUD readability, sprites/scissors and asymmetrical side choices with **0 mismatches**. |
| 43. Release privacy and evidence scanner | Mandatory packaging scan; no game needed | Fixed replay signatures, player-data paths and ZIP separator bypass; actual archive scan open | In maintainer packaging environment scan the real archive and in-memory forbidden cases. Reject renamed replay/live payloads, replay backups, saves/screenshots/logs/game data and backslash ZIP names. Confirm performance comparison refuses absent/dropped runs or unequal hashes before calling a pair synchronized. |

Rows 19–23 and 26–28 carry forward the unresolved design/proof requirements from
[PLAN_1.2.0.md](PLAN_1.2.0.md): authoritative room-aware flow, independent bounded local UI sequencing,
worker-only file I/O, non-consuming live pad sampling, release/focus guards, multilingual composition,
compatibility/replay propagation, measurement before optimization, immutable rational deadlines,
high-resolution early-wake handling, renderer resource ownership, exactly-once skipped ticks, latency
and displayed-frame gates. Source candidates do not close those release gates. Do not advertise the
rematch/pacing goals as achieved if UI/latency or real-pair determinism fails.

## Ranked audit findings: fixed and open

This pass reviewed the whole 1.2.0 change set against local `origin/main`, including the prior
agent-written integration and discord3. P1 means data/privacy or historical simulation risk;
P2 means functional, authority, evidence or build/test defects. Fixed means source repaired and a
regression source provided, not executed acceptance.

| Rank | Status | Finding and resolution / remaining proof |
| --- | --- | --- |
| P1 | Fixed | Release scanning missed replay files/backups, renamed replay/live payloads, known player-data directories, atomic-settings temporary files and ZIP backslash basenames on POSIX. Added path/signature rejection and in-memory regressions. Actual packaged archive scanning remains required. |
| P1 release gate | Open | No full patch application, compile/link/import/package execution or real pair evidence exists here. Native syntax was reviewed, not compiled. Every simulation/input/rule change requires real lockstep/rollback pairs, asymmetric host settings, rematches and replay with **0 mismatches** before release. |
| P1 | Fixed | Direct settings writes could truncate the only copy on failure. Settings now use a synced sibling temporary file and atomic replacement, cleaning the temporary file after failure. Windows full-disk/rename behavior remains unexecuted. |
| P1 | Fixed | Reset suppression would mutate historical replay inputs. New recordings use payload 7 / guarded SESSION 3; formats 1–6 retain their old reset rules, including all four pad handover sites. Match policy is snapshotted so later live-session upgrades/results cannot change an earlier fight. Old readers refuse the new version before simulation. `CODE_VERSION=11` forces rebuild. |
| P1 | Fixed | Costume fallback rewrote missing/all-zero historical replay customization. Those replay bytes remain zero; live matches retain the canonical fallback and nonzero validation. Verify historical setup/hashes in real playback. |
| P2 | Fixed | Present diagnostics could reuse a previous sample, with an unset status on a possible skipped-Present path. Per-call invalidation sets `no_present` and retains only explicit previous-Present history. The absent pinned dependency body prevents proving that skip branch reachable; no confirmed crash claim. |
| P2 | Fixed | Performance comparison could announce synchronized pairs with absent/dropped runs, no matches or unequal final hashes. Those evidence gaps now fail, including new after-only scenarios and earlier failures hidden by a later successful repeat. |
| P2 release gate | Open | Existing database schema 1→2 badge migration and additive `private_reports` creation appear non-destructive in source, but require backup, upgrade, rollback and legacy-client tests in a maintained environment. Compatibility groups must not group pre/post-reset builds without actual 0-mismatch proof. |
| P2 | Open | `local_pad.cpp` UI peek uses cached fixed-port policy initialized by gameplay sampling. A first ready/rematch prompt before that sampling may miss port 2. Source call order does not prove hardware behavior; verify port 2/auto before the first fight and across reconnect/session changes before changing live-thread configuration reads. |
| P2 | Open | Screen-side renderer repair is partial: mixed-side batches, first-frame center overlays and screen-spanning scissored fills require real rendering evidence. HUD/copy changes are not a complete readability fix. |
| P2 | Fixed | Persistent continued tickets omitted the server-fixed input delay, letting a local preference override ranked policy. Continuations now inherit/use the authoritative delay; regression covers differing local preferences and casual fallback. |
| P2 | Fixed | Live replay/shared spectator handles still used ANSI Windows opens despite UTF-8 replay paths. Replay-local wide APIs and overlay-aware Unicode path lookup now preserve sharing flags and retries without changing unrelated platform callers. Unicode live record/play remains a maintainer runtime gate. |
| P2 | Fixed | Replay writer could report saved after exhausting replacement retries. Publication success is now the actual retry result; the previous destination survives failure. Native pure retry regression and source wiring checks added; real filesystem behavior remains unproved. |
| P2 | Fixed | Detached resume tokens could restore deleted accounts or bypass a new account ban before the admin poll. Resume rereads account existence/ban before binding. In-memory DB/fake-connection regressions added; no live database was accessed. |
| P2 | Fixed | Windows training harness omitted GDI/User32 libraries, and its old euro fallback fixture contradicted the new fail-closed Unicode path. Corrected linkage and separated supported bitmap layout from unsupported text rejection; stale replay/build-version assertions were updated to current contracts. No compiler was run. |
| P2 | Fixed | Stale pad-prompt expiry could affect a replacement prompt or an already-started match. Expiry now requires the outstanding hidden offer. PM focus callbacks, native table-window close and delayed room-save callbacks now respect window/client/room lifetime. |
| P3 | Fixed | Warmup checkpoint identity ignored a DLL-only or subsecond rebuild. It now includes host and optional sibling DLL size/mtime_ns; old markers invalidate naturally. Mock-stat regressions added. |
| Existing feature gates | Open | Advantage move-pointer/position-X conflict, EU hook/address evidence, true CRT ABI, complete neutral reset fields and targeted Moonlit/sound/lightning evidence remain missing. VRR latency/resource ownership and SIMD bit identity/performance remain unproved. See rows 18, 26–35; no address was guessed or experiment enabled by default. |

## Regression sources and verification limits

Python (`python`, `python3`, `py`) and `uv` were unavailable on PATH. No interpreter was installed or
searched for in other folders. **No Python test was executed**, and no C/C++ harness was compiled.
No build, game, server, network connection or live database was used. Static checks are not behavioral
results. The pre-existing `docs/CI.md` working-tree edit was preserved.

Performed static checks:

- `git diff --check` passed. HEAD/origin/main remain as recorded above and the staged diff is empty.
- All **76** patch filenames have unique numeric prefixes. All **1,511** hunks were counted in memory
  with exact old/new line counts. Patch 0089's ten overlay hunks were also reconstructed sequentially
  against the checked-in base patch. Full dependency application remains unproved.
- All six catalogs retain **1,897** unique keys each, identical key sets, nonempty values and matching
  named placeholders. No new user-facing text was introduced by the audit fixes.
- All **283** changed/new paths were checked in memory for UTF-8, control bytes, size and prohibited paths.
  No data files, rejects or temporary patches were introduced. This is not execution of either Python
  game-data scanner and does not certify an actual release archive.
- Separate read-only `final_review` completed the final stable delta review; no additional actionable
  source defect remained. Reviewer findings were fixed and rechecked. This is source review only,
  not compile/runtime acceptance.

Regression sources retained/extended include replay reset/skip protocol tests, legacy costume bytes,
renderer/no-pause native cases, `test_120_launcher_integration.py`, `test_replays.py`, and training
layout/linkage. New targeted sources are:

- `tests/test_audit_launcher.py`: atomic settings failure paths and replay version decoding/scrubbing.
- `tests/test_audit_release.py`: release privacy patterns and performance evidence failures.
- `tests/test_audit_warmup.py`: DLL-only/subsecond checkpoint invalidation using mocked stat results.
- `tests/test_audit_patches.py`: per-call Present diagnostics and changed patch hunk counts.
- `tests/test_harness_link_libraries.py`: fake compiler-command generation and training fixture contract.
- `tests/test_audit_docs.py`: source/document rollout, replay and HUD contracts.
- `tests/test_audit_netplay.py`, `tests/c/replay_publish_test.cpp`: reset-policy/source wiring and pure
  replay publication retry behavior and Unicode live-handle wiring; no file-backed replay fixture needed.
- `lobby/tests/test_audit_server_core.py`: detached banned/deleted-account resume authority.
- `lobby/tests/test_audit_client.py`: stale UI expiry and continued authoritative delay.
- `lobby/tests/test_audit_ui.py`: PM focus, table close and room-save lifetime using fakes.

Maintainer may run selected game-free tests with a working interpreter after reviewing side effects.
Do not use broad discovery here: existing native wrappers compile, address-map tests can write synthetic
ELF, EU-review tests write outside this repository, and diagnostic tests can create synthetic game logs.
In-memory/fake-transport tests are not evidence from a real server or two PCs.

## Agents used in this audit

Area agents: `discord_integration`, `netplay_replays`, `training_directfight`, `patches_native`,
`launcher_settings`, `server_core_db`, `server_rooms_sets`, `client_lifecycle`, `lobby_ui`,
`release_tooling`. Independent tests/catalog specialist: `catalogs_tests`. Documentation audit:
`documentation_audit`. Additional read-only native reviewers: `netplay_replays/netplay_core_syntax`
and `netplay_replays/rollback_syntax`. Separate read-only final-diff reviewer: `final_review`.
Root coordinated exclusive ownership, follow-up fixes, the acceptance/findings tables and final static
checks. Every agent read AGENTS.md; shared test/document edits were handed off before editing.
