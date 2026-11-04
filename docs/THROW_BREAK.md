# Throw breaks at offline timing online

New online sessions extend the **end** of a throw victim's timed input command
by the agreed session input delay. A window `[start, end]` becomes
`[start, end + delay]`. The game still checks the original start, input edges,
button combination, buffered command, and throw outcome. Nothing presses a
button, rewinds an animation, or extends an attacker's attack window.

The change requires CODE_VERSION 12 and replay format 8 (SESSION 4). Older
recordings keep their original timing. A rollback replay uses its recorded
rollback delay, not the playback input-delivery delay. The negotiated delay is
fixed for the session; the existing adaptive selection chooses it at startup.

## RAM evidence (US NPUB30009 v01.00 only)

The training block bases are P1 `0x10090030`, P2 `0x10090900`. The engine's
fighter pointers are **0x10 bytes later**, at `0x10090040` / `0x10090910`.
Offsets below use the engine pointer:

- `+0xC4` is the current move pointer (training block `+0xD4`). Its `+0x14`
  points to timed command records, each `0x18` bytes. Ordinary input records
  have kind 0; kind `0x8000` ends the list. The inclusive start/end are big
  endian halfwords at record `+0x10/+0x12`.
- `+0x96` is the integer animation age (training `+0xA6`). The evaluator
  `0xEF790` / body `0xEF7BC` compares this age to both bounds.
- Signed halfword `+0x148` identifies paired animation roles: leader positive,
  follower negative. The rule requires a canonical fighter pair, a negative
  victim role and a positive opponent role. It changes ordinary input records
  only, leaving automatic/special commands alone. Special indirect lists,
  malformed ranges and lists without a terminator within 128 records are left
  untouched.

In a scripted offline Jin 1+3 throw, the victim move was at `0x46FE0BA8`, its
command list at `0x46FBA08C`: start at `0x46FBA09C` = 1, end at
`0x46FBA09E` = 15. These heap addresses describe the probe, not constants in
the implementation. The victim current-move pointer lives at `0x100909D4`,
its role at `0x10090A58`, and its animation age at `0x100909A6`.

Private evidence under `build/throwbreak/` (not distributed):

- `offline_close_base`: no net mode; `T5_RB_SCRIPT=@1600:60:20,1680:1:c000`,
  P2 neutral. Contact trace record 1693, victim age 1, command `[1,15]`;
  victim health 145, then 133, then 110. Extra trace ranges are
  `46fe0b00:200,46fba000:200`, so the record stride is `0x4670`.
- `offline_close_break1698`: same throw, one P2 Square at script frame 1698.
  The game selects the break and both fighters retain 145 health. The original
  command bounds remain `[1,15]`.
- `throw1`, `break866`, `break869`: original monolithic host, local lockstep,
  zero delay, P1 walk 800..827 and throw 840. Contact at net frame 853.
  Square at 866 selects the break; at 869 it fails and the throw damages P2.
- Training `+0x2D0/+0x2D2` countdowns were investigated and **rejected**:
  their consumers interpolate position/rotation. They are not break timers.

`rb_test.cpp` now exposes the existing read-only trace in its uninterrupted
offline test frames too; re-simulated frames do not emit duplicate records.
No game program, command table, trace, screenshot or lifted code is shipped.

## Determinism and implementation

Both input handovers in `t5_hooks.cpp` select the same rule after final frame
inputs: lockstep, rollback live/re-simulated frames, and replay. Every boundary
first disables the policy, covering menus, offline play and persistent-host
session exits. Old replays disable it explicitly.

`throw_break.cpp` detours the complete evaluator body `0xEF7BC`. Its scoped
wrapper extends eligible endpoints while the original evaluator runs and
restores the exact bytes before returning. This avoids modifying shared move
data permanently, accumulating extensions, recording host-only history, or
depending on how many times a rollback frame runs. It preserves start bounds
and all original command/input checks. Only the current victim move's own list
qualifies; candidate next-move command lists keep their original bounds.
A required detour failure aborts before
online simulation rather than silently running different rules.

`T5_THROW_BREAK_LOG=<file>` optionally records evaluator ages, fighter/list
addresses and original/extended endpoints (at most 4096 lines). It has no
effect on the rule or inputs.

Delay is clamped to the protocol's 0..30 range and signed endpoints saturate
at 32767. The supplied tests cover boundary math, role/type gates, byte
restoration, repeat evaluation, both player slots, simulated rollback and
legacy replay policy. Native game proof remains necessary for button buffering,
paired-animation classification and all special throw families.

## Coordinator acceptance runs

Completed in this worktree (same x86-64-v3 target on both peers):

| Pair | Finalized common frames | Mismatching frames | Playback |
|---|---:|---:|---|
| Rollback, delay 3, RTT 80 / jitter 5 ms / loss 3% | 4486 | 0 | both recordings identical, 73 hashes each |
| Lockstep, delay 3, RTT 40 / jitter 2 ms / loss 1% | 4483 | 0 | both recordings identical, 73 hashes each |

Both completed with matching 1-0 results. Rollback performed 2 corrections /
12 re-simulated frames on the host and 19 / 19 on the joiner. The joiner's
delivered Square at victim age 17 broke with endpoint 18 and retained health
145; the original endpoint was 15. These runs did not force rollbacks.
Exact commands, traces, results and replay verdicts are under
`build/throwbreak/`, with the complete inventory in `REPORT.md`. This is
same-target evidence; it does not replace a cross-CPU or cross-platform gate.

Run from an isolated build with this worktree's host and the owner's US game
DLL. Use only loopback. Isolate OPENRECOMP_HOME, APPDATA, LOCALAPPDATA and the
HDD/save output under the run root; check the real OpenRecomp config hash
before/after. Every build/game/replay run must atomically acquire an available
coordination HEAVY slot and release it in `finally`, including failed runs.
All games must be muted, background and BelowNormal.

Generate each pair's inputs with:

```powershell
python tools/throw_break_scripts.py --out build/throwbreak/scripts/d3 --delay 3
```

The exact primary matrix is **eight pairs**: `rb-d0`, `rb-d1`, `rb-d3`,
`rb-d8`, `ls-d0`, `ls-d1`, `ls-d3`, `ls-d8`. Substitute D for 0/1/3/8 in
this rollback command; lockstep changes both modes to `off`, RTT/jitter/loss
to `40/2/1`, and output name to `ls-dD`:

```powershell
python tools/rollback_net_test.py --exe build/host/t5dr.exe --vfs <US-VFS> --runs build/throwbreak/pairs --out rb-dD --fight jin,jin,20,1 --matches 1 --seconds 240 --delay D --rtt 80 --jitter 5 --loss 3 --mode1 net --mode2 net --polite --mute --below-normal --dump --env T5_RB_NET_DELAY=D --env T5_RB_NET_FORCE=9:4 --env PS3_HDD0_ROOT=<PRIVATE-HDD> --env OPENRECOMP_HOME=<PRIVATE-HOME> --env APPDATA=<PRIVATE-APPDATA> --env LOCALAPPDATA=<PRIVATE-LOCALAPPDATA> --env T5_REPLAY_DIR=<PRIVATE-REPLAYS> --env1 T5_NET_SCRIPT=<ABS-SCRIPTS>/p1.txt --env2 T5_NET_SCRIPT=<ABS-SCRIPTS>/p2.txt
```

For each pair require a completed matching result, **0 mismatching frames**
and equality of every common finalized gameplay hash (F for rollback; I for
lockstep), with nonzero compared frames. Remove `T5_RB_NET_FORCE` for lockstep.
For rollback require actual re-simulation (the forced 9:4 checks cover the
throw window even when a large delay hides the artificial RTT), and record
prediction corrections separately. Do not accept a pair that never rolls
back. Play **both** recorded files with `tools/replay_play.py --parallel 1`
and require every recorded hash and final result to match. Merely reaching
the timeout or printing a zero desync count is not a pass.

Then repeat `rb-d3` and `ls-d3` with `--attacker 2` generated scripts, so
the other fighter is the victim. Check the actual break animation and intact
health before the later KO script starts, not just peer hash equality.

Offline checks (same isolated settings, fresh process per probe):

1. Generate `--offline`; run `T5_RB_MODE=test`, `T5_RB_START=auto`,
   `T5_RB_START_DELAY=0`, `T5_RB_SAVE_EVERY=100000`,
   `T5_FIGHT=jin,jin,20,3`. Both scripts use `T5_RB_SCRIPT/2`. Neutral P2
   must be thrown; Square 1698 must break. Verify the trace `[1,15]` and
   unchanged original command bytes after the evaluator returns.
2. Sweep single-frame correct presses across the first/last accepted ages
   and one frame either side. Held-before-contact input and a wrong button
   must retain the game's original failure behavior. Repeat with the online
   rule active at delays 0/1/3/8: only the endpoint gains D frames.
3. Repeat for 2+4 throws, an actual 1+2 command throw from the game's move
   list, both sides, side/back throws, unbreakable throws and chain throws.
   Character-dependent windows must keep their own original start/end.
   Inspect special-list cases explicitly; do not infer coverage from Jin's
   ordinary one-record break list.
4. Run Practice and Versus offline, then online -> idle/menu -> next session
   in a persistent host; old timing must remain offline and delay must not
   leak between sessions. Play pre-format-8 fixtures with their old hashes.

These are acceptance requirements, not claims that the entire matrix ran.
