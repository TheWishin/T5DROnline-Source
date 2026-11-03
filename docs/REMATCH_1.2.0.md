# In-game rematch: implementation and maintainer verification

This working-tree change implements the rematch portion of
`codex/plans:docs/PLAN_1.2.0.md`. It does not implement the independent VRR plan.
No build, test program, game, server connection, or runtime measurement was run.
There are no new guest-memory addresses. Static review cannot prove compilation,
input ownership, renderer behavior, or simulation equality on a real pair.

## Rollout and authority

- The server switch is `T5L_INGAME_REMATCH=1`; it defaults off.
- The launcher switch is `T5_INGAME_REMATCH=1`; it defaults off.
- `ingame_rematch_v1` gates the optional server metadata and room settings.
  `auto_skip_after_round_v1` additionally gates automatic round skipping.
  Launcher capability detection checks the game binary for feature markers.
- `T5L_CASUAL_REMATCH_POLICY` accepts `both_confirm` (default) or
  `auto_unless_declined`. Classic casual rooms have the same server-owned
  `rematch_policy` setting. Ranked sets retain their existing rules. Community
  rooms retain rotation and ready checks.
- Each client casts its own rematch vote. Automatic mode defers that vote until
  the visible, cancellable countdown ends. The server owns eligibility and
  expiry; a local countdown cannot start a fight.
- Room skip permission and each player's skip consent are separate. The server
  sends one immutable `auto_skip_after_round` fight rule only when both agree
  and both advertise support. The input rule, including rollback and replay,
  applies symmetric START pulses in eligible nonfinal after-round parts.
- New recordings use replay format 7 and guarded live SESSION 3 whether
  automatic skipping is enabled or disabled. This additionally versions the
  integrated START+SELECT reset guard. Formats 1–6 and SESSION 1/2 retain their
  historical reset policy; the earlier skip draft's format 6 / SESSION 2 remains
  readable. A reserved header stops old native spectators before unsupported
  rules, and old native replay readers reject format 7. See [REPLAYS.md](REPLAYS.md).
  Changing the agreed skip flag requests a fresh game connection; repeated
  rematches with the same flag may retain their existing connection.
- Runtime patch **0089-ingame-rematch-overlay.patch** follows the online boot
  overlay at **0088**. It was renumbered from the rematch draft's duplicate
  **0088** so patches retain one unambiguous numeric sequence in filename order.
  The existing 0100–0102 patches follow it; VRR pacing remains **0103**.

## Components and static confidence

| Part | Implementation | Confidence and outstanding proof |
|---|---|---|
| Server | Default explicit votes, optional automatic policy, per-room controls, bounded offers, capability gates, mutual skip consent, community line metadata | High source confidence; in-process rule and expiry tests must be run by maintainer |
| Launcher transport | Separate versioned UI channel, action identity/sequence checks, asynchronous deduplication, acknowledgement, waiting/expiry, persistent and process lifecycle | Moderate source confidence; run fake-endpoint tests and repeat real process/persistent transitions |
| Launcher UI | Healthy acknowledged prompts suppress focus changes; legacy rematch button retained; room controls, player skip option, language catalogs | High Python source confidence; Tk layout, localization, focus and unsupported-game fallback require launcher validation |
| Host menu | Host-only worker, bounded parsing, live-only pad edges, release-to-arm, focus guard, one pending action, overlay publication | Moderate C++ confidence; real host build/link and pad ownership need proof |
| Runtime overlay | Separate training/menu layers, raw non-consuming pad peek, focus query, Unicode glyph handling | Moderate C confidence; apply the full series and build all supported backends before claiming compatibility |
| Fight integration | Existing barriers retained, live hook excludes re-simulation/replay, per-match rule agreement before fight release | Moderate C++ confidence; same-session rematches and asymmetric arrival need pair tests |
| Deterministic skip and recording | Match-rule packing, after-round voting, peer rule verification, versioned replay/spectator recording and readers | High pure-rule confidence, moderate integration confidence; compile rule tests and prove 0 mismatching frames on a real pair |

## Game-free tests to run later

New regression sources accompany each component. They use fake pads, clocks,
file endpoints, clients and rule state; no game assets or external server are
needed. The C++ rule/menu tests require compilation. The repository's existing
no-pause, match-rule, local-pad, persistent-driver, room, ranked-set, replay,
spectator, overlay and language-catalog suites must also pass. No test result is
claimed in this change: the instruction for this lane prohibits running them.

New regression entry points:

- `lobby/tests/test_rematch_server.py`
- `lobby/tests/test_ingame_ui.py`, `test_driver_ingame_ui.py`,
  `test_tk_ingame_ui.py`, `test_tk_rematch_rules.py`
- `tests/test_rematch_ui.py`, `test_rematch_runtime.py`,
  `test_rematch_integration.py`, `test_replay_skip_compat.py`
- `tests/c/rematch_ui_test.cpp`, plus added local-pad, match-rule and no-pause
  cases in the existing C++ harnesses. `tests/test_replays.py` also specifies
  enabled-skip file/live recording through the standalone replay harness.

## Exact real-pair acceptance procedure

Run this in the maintainer's real project, keeping game assets and runtime
captures out of this mirror. Use the existing mismatch/hash reporting on both
PCs and compare the same agreed fight inputs, rules and results.

1. Build the full patched runtime and host on both PCs. Start with both feature
   switches off and establish the existing launcher rematch and ranked-set
   behavior. Repeat with one old client/game and with a new launcher using an
   old game: ordinary rematches must work through the launcher, the new skip
   rule must remain disabled, and no unacknowledged overlay may hide the UI.
2. Enable both switches on both PCs. For casual and classic private rooms
   (password, invite and hidden), test `both_confirm`: accept on PC A with only
   its pad/stick, verify waiting on A, accept on B, then select characters and
   start the next fight with the launcher behind. Repeat ten rematches, changing
   characters/stage, then use decline/Next/ready to change opponents. Require
   one result report and one vote/action per player, no stuck select and no
   duplicate match start.
3. Set the server/room rule to `auto_unless_declined`. Verify the visible
   countdown on both PCs, cancellation just before its end on either PC, then
   an uncancelled automatic rematch. Hold an attack/confirm button through KO,
   opening, focus loss/return and controller reconnection: none may accept
   until released and pressed again. Leave one PC unconfirmed in explicit mode
   and let the offer expire: return to lobby fallback without launching a fight.
4. Disconnect either game or launcher during the offer, an outstanding action,
   waiting, and a ready check. Restart it and present old action/UI files:
   generation/session/prompt/match checks must reject stale requests. Test a
   slow asynchronous vote and duplicated input: at most one server request.
   Missing heartbeat, missing glyphs/backend support or failed acknowledgements
   must restore the ordinary launcher decision path.
5. Exercise a private community room with at least three members under each
   rotation rule. Rotation, waiting-player priority and ready checks must stay
   authoritative; no classic match-ID rematch may bypass the line, and no Next
   action from any private room may enter public matchmaking. Run ranked sets
   and tournament matches too: next-game and explicit leave behavior must match
   baseline.
6. For each flow above, cover direct and relay paths, lockstep and rollback,
   process and persistent games, and asymmetric fast/slow PCs. Include packet
   delay/jitter/loss and repeated reused-session rematches. Require **0
   mismatching simulation frames**, identical results, and no extra/missing
   simulation frames for every completed fight.
7. Run skip consent combinations off/off, on/off, off/on and on/on. Only the
   last may enable the agreed rule; ranked and unsupported peers must retain
   baseline behavior. Observe nonfinal KO slow motion, replay and transition
   states 8/9/0xC, unchanged manual intro voting, unpausable fighting, and the
   existing final-match 40-frame skip guard. Force rollback across entry/exit of
   each part, repeated corrections and delayed START. Require **0 mismatching
   simulation frames** with skipping both enabled and disabled.
8. Deliberately give the peers different packed rules before a first fight and
   before a reused-session rematch. They must reject or time out before stage
   confirmation/FIGHT START releases the fight. Record/play back enabled and
   disabled fights and spectate them; compare hashes/results with **0
   mismatches**. Old readers must reject the new format explicitly; new readers
   must play old formats with automatic skipping off.

Check long names, every language (including Japanese/Korean), wrapping, scaling,
overlay priority, training hide/clear, and mapped button hints on the built
renderer. Missing fonts must trigger an honest launcher fallback. Visual and
latency claims need actual focused game-window validation.

## Agent ownership and review

Implementation agents: `server_rules`, `launcher_driver`, `launcher_ui`,
`room_settings`, `host_ui`, `runtime_overlay`, `fight_integration`, `skip_core`,
and `replay_readers`. `compatibility_audit` performed a separate read-only
architecture audit. `final_diff_review` performed the independent final diff
review. The root agent coordinated file ownership and wrote this report.
Changes remain in the working tree; no commit, push, merge or pull request was
made.
