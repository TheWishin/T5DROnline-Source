# One set of T5DR settings for both launchers

Tekken 5 DR can be started from two launchers: T5DR's own (`T5DR Online`) and OpenRecomp. From the T5DR launcher after 1.2.2
and OpenRecomp 1.0.0 on they use the same settings and the same controls. A player who used one of them finds his
choices in the other one, with no step to take. This file is the same in both repositories
(`docs/SETTINGS_SYNC.md`), and so is the module that does the work (`launcher/settings_sync.py` in T5DR,
`openrecomp/settings_sync.py` in OpenRecomp: standard library only, keep the two copies identical).

## Where things are

| What | File | Who writes it |
| --- | --- | --- |
| Shared settings | `%APPDATA%\T5DROnline\settings.json` (next to `online.json`; `T5_SETTINGS_DIR`, then `T5_ONLINE_DIR`, move it) | both launchers |
| A T5DR folder's own settings + a copy of the shared ones | `<T5DR folder>\launcher.json` | T5DR's launcher; OpenRecomp only the shared settings it changed |
| Controls | `<output folder>\controls.ini` (or `PS3_CONTROLS`), the game's file | both launchers (since OpenRecomp 0.1.7, `controls_file.py`) and the game reads it |
| OpenRecomp's own choices for a T5DR folder | `%LOCALAPPDATA%\OpenRecomp\t5dr\<folder id>\settings.json` | OpenRecomp |
| OpenRecomp itself | `%LOCALAPPDATA%\OpenRecomp\config.json` | OpenRecomp |
| Backups made by a migration | `%APPDATA%\T5DROnline\settings-backup\*.bak` (the newest 20) | both |

`settings.json`:

```json
{"format": "t5dr-settings", "version": 1, "updated": 1794300000.0, "updated_by": "openrecomp",
 "values":   {"display": "borderless", "vsync": "off"},
 "stamps":   {"display": 1794300000.0, "vsync": 1794200000.0},
 "installs": {"<folder id>": {"seen": {"display": "window", "vsync": "off"}, "used": 1794300000.0}}}
```

* `version` is 1. A launcher keeps every field and every value it does not know and never lowers a higher number.
* `stamps`: when each setting was last changed. `installs.<id>.seen`: the shared values that folder's `launcher.json`
  had at the last sync (the newest 8 folders are remembered). The folder id is a hash of the folder's path.
* Writes go through a temporary file in the same folder and `os.replace`. A file another program holds (antivirus,
  the other launcher) is tried again for 2 seconds; it is never written in place, so a reader never sees half a file.
* A save reads the file again and puts only the settings changed in this launcher on top: what the other launcher
  saved meanwhile stays.
* A file that does not parse is read again a few times (the other launcher may be replacing it); if it stays
  unreadable it is moved aside as `settings.json.corrupt-<time>` and the launcher goes on with `launcher.json`.
* A held or broken shared folder never stops a launcher: it uses the folder's own values and says so in its log.

## Every setting

Shared = in `settings.json`, the same in both launchers. The key is the same everywhere (`launcher.json`, the shared
file's `values`, OpenRecomp's setting id).

| Key(s) | What | Shown in OpenRecomp | Lives in |
| --- | --- | --- | --- |
| `display`, `window_w`, `window_h`, `picture` | game window / picture format | Display (size and format: T5DR launcher only) | shared |
| `internal_res`, `internal_res_set` | internal resolution, "the player chose it" | Internal resolution | shared |
| `vsync`, `stage_blur`, `shadows`, `effects` | graphics | yes | shared |
| `old_pc`, `power_saving`, `clips` | Old PC settings done, power saving, clips | no | shared |
| `input_delay`, `online_feel`, `net_line` | online input delay, feel, connection line | input delay yes | shared |
| `training`, `training_all`, `training_online`, `training_pos` | training display | Training display | shared |
| `practice`, `practice_dummy`, `auto_skip_offline` | practice tools | Practice tools | shared |
| `screen_side`, `always_left` | your side on screen (`always_left` = the older form, kept in step) | Screen side | shared |
| `mute` | game sound off | yes | shared |
| `notify`, `notify_sound`, `notify_voice`, `notify_sound_name`, `notify_challenge_sound`, `notify_challenge_sound_name` | match / challenge sounds | no | shared (the chosen WAV itself stays in the T5DR folder) |
| `replays`, `replay_dir`, `replay_names` | replays | yes | shared |
| `spectators`, `spectators_ranked`, `auto_spectate`, `auto_watch_table` | spectating | the first three | shared |
| `unlock_stages`, `unlock_items`, `unlock_jinpachi` | offline unlocks | the first two | shared |
| `nickname`, `router_ports`, `discord_presence`, `discord_app_id` | online | name | shared |
| `extra_env`, `low_priority` | extra game settings, build priority | no | shared |
| `settings_version` | which defaults the values were saved under | no | shared |
| `pkg`, `rap`, `out` | this folder's package, licence, output folder | Build page | per folder: `launcher.json`; OpenRecomp's choice in its own file |
| `language` | launcher language | OpenRecomp has its own (`config.json` `language`) | per launcher |
| `background` | test switch | no | T5DR launcher only |
| `clock_hint_shown`, `controls_hint_shown`, `gpu_build_warning` | hints a launcher showed | no | T5DR launcher only |
| `[general]`, `[port1]`, `[port2]`, `[keys1]`, `[keys2]`, `[xinput]`, `[dinput]`, `[dinput.VVVV:PPPP]` | bindings, devices, presets | Controls page | `controls.ini` |

### What each launcher keeps for itself

* T5DR's launcher: `pkg`, `rap`, `out`, `language`, `background`, `clock_hint_shown`, `controls_hint_shown`,
  `gpu_build_warning` (`settings_sync.LOCAL_KEYS`), its window, `update-check.json`, `launcher.log`.
* OpenRecomp: everything in `config.json` (language, text size, colours, sounds, fullscreen, start with Windows,
  game folders, prompt style, online identity), and per T5DR folder the package / licence / output folder chosen in
  OpenRecomp.
* Saved logins stay as they are (`online.json` of each launcher; see T5DR_COEXISTENCE.md).
* **Playtime stays per launcher**: T5DR's launcher counts the games it started (`playtime.json` next to
  `launcher.json`), OpenRecomp counts the ones it started (`openrecomp/playtime.py`). They are not added up. The two
  count different things (one launcher's own starts) and a shared counter would need both to agree on one writer;
  say so if one total is wanted.
* Controls are one file per output folder, as before. Two T5DR folders have two `controls.ini`.

## Start of a launcher (`settings_sync.sync`)

1. **No shared file yet.** `launcher.json`'s values are used; nothing is written. The first save makes the file from
   `launcher.json` (copied to `settings-backup` first) plus the change.
2. **No shared file, but OpenRecomp 0.1.x overrides** (it kept every edit in its own `settings.json`): the shared
   file is made at once from `launcher.json` and the overrides. Where both name a setting and differ, **the file
   written last wins**; a setting only one of them has is kept. Both files are copied to `settings-backup` first, so
   the losing values are still there. OpenRecomp's own file keeps only what is its own.
3. **Shared file there.** Its values win, with two exceptions:
   * a setting whose `launcher.json` value differs from `seen` was changed by a T5DR launcher that does not know the
     shared file (1.2.2 or older). It is taken over when `launcher.json` is newer than that setting's stamp.
   * leftover OpenRecomp overrides win where their file is newer than the setting's stamp.
4. **A T5DR folder seen for the first time** (new download next to an old one, a second install): it gets the shared
   values; only settings the shared file does not have yet are taken from its `launcher.json`, which is copied to
   `settings-backup` first if it differs. A brand-new folder without `launcher.json` starts with the player's
   settings.

Nothing is ever deleted: a file that loses is copied to `settings-backup`, a damaged one is renamed.

## Saving

* T5DR's launcher writes `launcher.json` as always (all settings, so tools and older launchers keep working), then
  the settings changed since its start into the shared file.
* OpenRecomp writes the changed shared settings into the shared file **and into that folder's `launcher.json`**
  (only those keys, everything else untouched, same atomic write): a T5DR launcher of 1.2.2 or older reads only that
  file and so shows the change too. Its own choices (package, licence, output folder) go to its own file.
  If the shared file cannot be written, the edit waits in OpenRecomp's own file and moves at the next start.
* A choice another launcher version saved that this version does not have (a new display mode) is not shown and not
  overwritten until the player chooses something here. OpenRecomp asks the installed launcher's own `Settings` to
  check shared values, so each T5DR version applies its own rules.

## Limits

* Changes show in the other launcher at its next start, not while it is open. With both open, the one that saves a
  setting last wins for that setting. A T5DR launcher of 1.2.2 or older that is open while OpenRecomp changes a
  setting writes its old value back when it saves.
* The player's own match sound (`match_sound.wav`) is a file in the T5DR folder; with two T5DR folders the choice
  "custom" is shared but the file is not.
* A drill with a settings copy (`t5dr_settings_copy`, tools/update_drill.py) stays read-only and uses no shared file.

## Tests

No test reads or writes the player's files: T5DR's `Settings` uses a shared folder only for its own default
`launcher.json`, and never in a test run that names no folder (`T5_SETTINGS_DIR` / `T5_ONLINE_DIR`); OpenRecomp's
test runs keep the shared file inside each test's own home.

* T5DR: `tests/test_settings_sync.py`. The file (version, unknown fields, held file retried, damaged file moved
  aside, half-written file read again), migration in both directions, both launchers on one folder, a 1.2.2 launcher
  changing `launcher.json`, a new folder. With `T5DR_TEST_OPENRECOMP_SRC=<OpenRecomp checkout>` the same against
  OpenRecomp's real settings class, and the two module copies are compared byte for byte.
* OpenRecomp: `tests/test_settings_sync.py` (the module) and `tests/test_t5_coexist_settings.py` (its settings class
  with the shared file, the mirror into `launcher.json`, its old overrides moving).
