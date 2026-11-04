# Rematch focus audit (1.2.0)

The launcher could activate itself during an in-game rematch. This is a queue-ordering race:

1. `MatchDriver.on_event` queues `rematch_offer` for the opponent's offer.
2. `OnlineTab` drains lobby events before driver notes. A subsequent `match_start`
   clears the in-game prompt, but the last sampled game state can still be `over` or `neutral`.
3. The queued offer then calls `_come_forward`. The former prompt/state checks allow it,
   and `winfront._raise_hwnd` restores and activates the launcher using `AttachThreadInput`,
   `BringWindowToTop` and `SetForegroundWindow`.
4. A DXGI exclusive-fullscreen game can minimize when it loses foreground.

`lobby/tests/test_rematch_focus.py` reproduces that ordering using the real driver,
fake game handles, and fake window/notification hooks. It opens no windows.

## Focus policy

Automatic launcher handoffs wait until the game has closed, regardless of the
overlay acknowledgement, ticket, or sampled game phase. The foreground check reads
the game's process ID without changing any window. A foreground game suppresses
notification sound and taskbar flash; a background game permits the existing
taskbar-only notification. Starting a match can still hand focus from the launcher
to the game when the player is using the launcher; it does nothing when the game
already owns foreground or another application is in front.

Online fullscreen uses the existing borderless path even with
`PS3_FULLSCREEN=exclusive` or `2`. The launcher normalizes the effective launch
environment, including inherited settings. Runtime patch 0116 also enforces the
policy for direct host/join launches and launcher-managed persistent processes
(`T5_CTL_DIR`), including waits between sessions. Offline exclusive mode remains
available. Focus loss does not restore or reactivate the game, so Alt+Tab works.

## Audited paths

| Path | Finding / handling |
| --- | --- |
| `lobby/t5lobby/tk_tab.py`: result, set end, rematch offer, UI fallback, manual result recovery | All automatic launcher raises share `_come_forward`; guarded by the running game, including queued notes after prompt teardown. |
| `lobby/t5lobby/tk_tour.py`: tournament call | Uses the same guarded `_come_forward`. |
| `lobby/t5lobby/match_driver.py`: rematch/`ingame_rematch`, `set_next`, next `match_start` | Reuses the game/control channel. No window API or new console; the queued offer was the focus trigger. |
| `lobby/t5lobby/winfront.py` | Contains Tk `deiconify`/`lift`/`focus_force` and Win32 restore/activation helpers. Automatic callers are blocked while the game lives. Failed handoff now uses taskbar-only `FlashWindowEx`, replacing `FlashWindow`. |
| `OnlineTab._game_forward` (pad-online handoff) | Requires launcher foreground; explicitly skips an already foreground game. |
| `lobby/t5lobby/notify.py`, `announcer.py` | Sound is a daemon-thread `winsound` call, without windows or subprocesses. Taskbar flags are `FLASHW_TRAY \| FLASHW_TIMERNOFG`; foreground is rechecked before flashing. |
| `lobby/t5lobby/tk_views.py`: Online cards/popups | Match, challenge, invite, result and error cards are child widgets. Child Frame `lift` only changes stacking within the launcher. |
| Private-chat, character, search and account dialogs | Arrival updates content; window-show/raise paths require user actions. No rematch-triggered modal. |
| Windows toast / Tk `-topmost` | No implementation found in launcher or lobby. |
| `launcher/t5dr_launcher.pyw`: fatal game-log dialog | Delayed modal/raise now waits for both the captured game and any newly started game to stop. |
| `launcher/updater.py` | Automatic offers already wait while busy; delayed lift/focus now checks again at execution time. |
| `launcher/core.py`, `launcher/warmup.py` | Game/worker subprocesses use `CREATE_NO_WINDOW`; warmup is paused before player launch. Game-window placement runs on process startup, not persistent rematches. |
| Runtime patch 0010 | Configures DXGI exclusive and calls `SetFullscreenState`; patch 0116 disables exclusive for online processes. |
| Runtime patch 0031 | Existing exclusive-loss handling detects the lost exclusive state; it did not prevent minimization. Its explicit `SW_MINIMIZE` belongs to a fatal GPU-error path immediately before process exit. |
| Runtime patches 0001, 0021, 0105 | Initial background-window show/minimize and hidden warmup handling, not match/rematch events. |
| Runtime patch 0033 | System UI uses a separate topmost panel with `SWP_NOACTIVATE`, then hides it. The rematch question is drawn in the game overlay instead. |
| `src/` and runtime patches | No rematch-triggered `ShowWindow`, activation, or console creation found. |

Validation uses the specified Python 3.12, with temporary output inside this
worktree. Fake-window regressions cover the queue race, set continuation,
foreground/background notifications and delayed dialogs. Fullscreen tests compile
the actual new C policy against a fake environment without loading DXGI or user32.
Native Tk coverage requires a working Tcl/Tk installation; no game/fullscreen
smoke test was performed here. No player-visible strings changed.
