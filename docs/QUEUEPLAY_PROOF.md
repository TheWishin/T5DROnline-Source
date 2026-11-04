# Practice-to-online verification

`tools/queueplay_test.py` checks the boundary that needs runtime proof: a
persistent process has spent minutes playing offline Practice, then fights a
newly booted opponent. It uses only loopback UDP and never opens a lobby or
logs in. Use a runtime built from the queueplay working tree; an older binary
cannot implement the `practice` control command.

The tool first sends `practice` (the optional offline `T5_FIGHT` is reserved;
the game confirms its initial native Practice cursors). It waits
for control state `practice` (the loaded Practice fight), then changes the
local pad file every second for 180 seconds by default. The inputs move,
crouch, attack and periodically reset positions. A native Practice-ready
log (`type=10 phase=17`) is required. For soaks of 10 seconds or longer the
Practice action log must also show a reset, proving that those pad changes
reached the Practice tools. The opponent process starts only after this interval and
waits at its fresh neutral select. Both then receive a new `fight` session.
The Practice process keeps its PID throughout the transition, exercising
the existing leave/select/title/boot-state restore path.

Each mode must independently pass all of these checks:

- Both games finish the same match with the same winner and final hash,
  and neither reports desync.
- Both logs contain real frame comparison checks, all with zero mismatching
  frames. Missing comparison evidence fails the tool.
- The requested loop runs on both peers. The rollback run also forces a
  four-frame rollback every 120 fight frames and requires completed
  resimulations in both logs, so a negotiated-but-unused rollback loop cannot
  pass as rollback coverage.
- Both recorded replays play back sequentially in fresh games with
  `identical: true`. Replays record a hash every frame.

The tool writes a new output folder and refuses to reuse one. Its
`report.json` includes the runtime SHA-256, actual Practice duration, input
changes, PIDs, both results, frame comparison checks and replay verdicts.
Game logs are `run1/game1.log` and `run2/game1.log`; replays are under each
game's `replays/`; playback details are `replay.log` and
`playback/verdicts.jsonl`. A PASS is required in both modes before claiming
the Practice reset is deterministic. Unit tests or an older persistent
versus fresh proof do not replace these runs.

## Exact local runs for the coordinator

Build the modified runtime into `build/queueplay/cmake/t5dr.exe` first using
the normal developer build and patched runtime dependencies. Set
`$queueExe` below to its actual location if it differs. The example VFS is
the existing local installation; game files are read there, and all run
outputs remain in this worktree.

Run this PowerShell from the worktree. It atomically takes one of the three
coordination slots and releases it even on failure. A slot is released
between rollback and lockstep. It records the owner's real config hash
before redirecting the runner's environment; every game and playback also
gets isolated environment paths, muted audio, a background window, and
BelowNormal priority. These are correctness runs, not timing measurements.

```powershell
$queueExe = (Resolve-Path 'build/queueplay/cmake/t5dr.exe').Path
$queueVfs = 'C:\T5DROnline\game\vfs'
$ownerConfig = Join-Path $env:LOCALAPPDATA 'OpenRecomp\config.json'
$ownerHash = if (Test-Path -LiteralPath $ownerConfig) {
    (Get-FileHash -LiteralPath $ownerConfig).Hash
} else { $null }

function Invoke-QueueProof([string] $mode, [int] $port) {
    $slot = $null
    foreach ($name in 'HEAVY.lock', 'HEAVY2.lock', 'HEAVY3.lock') {
        $candidate = Join-Path 'C:\T5DROnline\build\int115' $name
        try {
            New-Item -ItemType File -Path $candidate -ErrorAction Stop | Out-Null
            $slot = $candidate
            break
        } catch [System.IO.IOException] { }
    }
    if (!$slot) { throw 'All heavy slots are occupied; retry after one is released.' }
    try {
        Set-Content -LiteralPath $slot -Value "queueplay $(Get-Date -Format o) $mode Practice vs fresh + replays"
        $sandbox = Join-Path (Get-Location) "build/queueplay/sandbox-$mode"
        $env:OPENRECOMP_HOME = Join-Path $sandbox 'openrecomp'
        $env:APPDATA = Join-Path $sandbox 'appdata'
        $env:LOCALAPPDATA = Join-Path $sandbox 'localappdata'
        $queueProbeArgs = @()
        if ($mode -eq 'rollback') { $queueProbeArgs = @('--challenger-probe') }
        python tools/queueplay_test.py --exe $queueExe --vfs $queueVfs `
            --out "build/queueplay/proof-$mode" --mode $mode `
            --practice-seconds 180 --port $port @queueProbeArgs
        if ($LASTEXITCODE) { throw "$mode proof failed; inspect report.json and game logs" }
    } finally {
        Remove-Item -LiteralPath $slot
    }
}

try {
    Invoke-QueueProof rollback 27400
    Invoke-QueueProof lockstep 27420
} finally {
    $after = if (Test-Path -LiteralPath $ownerConfig) {
        (Get-FileHash -LiteralPath $ownerConfig).Hash
    } else { $null }
    if ($ownerHash -ne $after) { throw 'Owner OpenRecomp config changed during the suite' }
}
```

If either proof fails, preserve its output folder and rerun into a different
new folder after the fix. Do not describe a pending coordinator run as a
zero-mismatch result. A longer soak can use `--practice-seconds 600`; it must
still hold a slot, and the other peer must stay fresh until after the soak.

Add `--challenger-probe` to either mode's command for runtime panel coverage.
This starts the existing local `IngameUI` worker before game boot. After the
Practice soak and before starting the fresh peer, it publishes three
15-second challenger prompts. It requires a rendered revision and checks
that Cross held before arrival cannot accept, a new Cross press accepts
exactly once, Circle declines exactly once, both actions receive rendered
acknowledgments, and an unanswered panel expires once after 15 seconds.
The `challenger_probe` section of `report.json` preserves every offer,
rendered revision, action sequence, acknowledgment and expiry duration.
No lobby or account is involved. A missing/stale UI heartbeat, missing pad
action, repeated action, or early expiry fails the run.

Proof checker unit tests (no games or network):

```powershell
python -m unittest discover -s tests -p test_queueplay_proof.py -v
```

The separate launcher/driver tests cover queue start, cancellation, stale
offers, accept/decline and timeout. A human pad smoke can additionally check
the panel's appearance and readability while Practice is running.
