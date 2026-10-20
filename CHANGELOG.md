# Changelog

All notable changes, newest first. The project is a test release. Short commit hashes are in parentheses. The state of each
part is in the README's status table.

## v1.1.3 (not released yet)

### Picture and speed
- **Less GPU work at 1080p, 1440p and 4K** (ps3recomp patch 0051). The stages with a blur or a glow
  filter a PS3-size copy of the picture (1.1.2); making that copy and shrinking a large picture
  into a smaller window are now done with fewer texture reads, with exactly the same result.
  On integrated graphics this cut 17-40 % of the GPU time around the 3D scene at 1440p and 4K.
  With power saving on (on by itself with integrated graphics) the shadow map and the sun's glow
  keep the PS3's size above Native as well. The log can show where the GPU time of a frame goes
  (`RSX_GPU_PASSES=1`).
- **A PC that is a bit too slow for 60 fps now runs fights at 45-55 instead of 30-45**
  (ps3recomp patch 0059). The game shows a frame on a screen refresh, as on the PS3; a
  frame that took a little longer than one refresh waited for the next one, so a fight
  frame of 18-20 ms took 33 ms. Now that frame is shown as soon as it is ready. A slowed
  test game went from 40 to 49-50 fps and from 30 to 43-44 fps; online, a match against
  such a PC from 32 to 46 fps, in sync. PCs that make 60 already see no change; the game
  still never runs faster than 60. `PS3_LATE_FLIP=0` (extra settings) is the old way.
  Why those PCs are slow (one processor core's speed, not the graphics API -- no Vulkan
  needed) and a checklist for players: docs/WEAK_PC.md.
- **Problem reports say more about slow fights.** The game log's `[slow-frames]` lines name
  the frames shown late and what other programs used of the processor; a frame that only
  waited for its own translation is no longer blamed on the vblank thread. `system.txt`
  adds Windows' Game Mode and GPU scheduling settings and the online match's speed
  against this PC's own.
- **4K on integrated graphics: the launcher says what helps, the log says why** (ps3recomp
  patch 0063). A Radeon 780M mini PC ran fights at 32-38 fps at 4K on a 1080p screen. The
  game was not waiting for the graphics: at 4K this game's 3D scene is 6144 x 4320 pixels,
  and on a processor with built-in graphics a busy GPU also slows the processor (one memory,
  one power budget). Settings -> Internal resolution has a new choice, **Auto (matches the
  screen)**: the step that fits the screen, at most 1080p on integrated graphics (Native
  stays the default). A test fight on integrated graphics: 4K 33-35 fps, Auto 60. On
  integrated graphics a step larger than the screen gets a hint ("4K on integrated
  graphics: try 1080p for 60 fps"), and after a fight the graphics held back the Play tab
  says so. `[slow-frames]` now splits the game's part of a frame into the main thread's
  work and its waits, says how busy the GPU was and how fast the processors really ran,
  and ends with "GPU-bound" when the graphics are the limit; Report a problem sums it up
  in one line. Power saving **Auto** now always reaches the game: a `PS3_LAPTOP` left in
  Windows' environment no longer overrules it, and Settings names an Extra-settings line
  that does.

## v1.1.2 (2026-10-20)

**Friends and invites, replays of every online match, opponents nearby first, a training overlay, five more languages, all stages and items unlocked offline, less CPU on laptops.** Both players need 1.1.2
(the lobby pairs equal game builds, and 1.1.2 changes the game: ps3recomp patches 0043, 0044, 0045, 0047, 0048,
0052 and 0053). The launcher offers the update itself; after it, press **BUILD GAME** once.

### Online
- **Match scores are the real round counts.** The game reported the winner right, but the
  score was made up: a 3-2 or 3-1 showed as 3-0, and now and then a 3-0 showed as 0-1. A
  drawn match (time-out with equal health, or a double KO, in the deciding round) was counted
  as Player 1's win. The game now reads the rounds each fighter won and reports draws as
  draws. This matters beyond the result card: when the opponent's connection broke after the
  last round, only a full score lets the lobby keep the win (a wrong score voided the match).
  docs/NETPLAY.md "Match result".
- **Invite buttons show the wait after a no.** When a friend declines your invite (or you take
  it back), the lobby holds the next invite to that friend back for 30 seconds. The invite
  buttons are now off for that friend during the wait, and the one you would use counts the
  seconds down ("Invite in 27 s"), for match and room invites alike. The seconds come from the
  server, which still has the last word.
- **Friends and invites** (accounts): add friends by account name on the Online tab's new **Friends** page. The
  list shows who is online, searching, in a match or offline, as it changes. **Invite** a friend to a casual match
  or into your room: one click on **Accept** (or A / Cross on a pad) starts it, no ready check (a ranked room keeps
  its ready check, which says it is ranked). Blocking a player ends the friendship. Limits against spam: 20 friend
  requests a day (60 per internet address), 100 friends, one invite at a time; after a no, the same player can
  invite or challenge you again only after 30 seconds, and a friend request taken back and sent again does not pop
  up again.
- **No accepting a question by accident:** a challenge or invite only takes a controller press made after it came
  up (the A for the search button could accept one that popped up in that same moment).
- **Opponents nearby first.** Quick and ranked search try opponents with a low ping first and widen the search
  while you wait (any ping after 30 s in quick, 60 s in ranked). The ping shown for a found match now counts the
  nearest relay server: two players in California see about 50 ms instead of about 300 ms through Germany.
- **Replays.** Every online match is saved (a few KB, in `native\replays`). The new **Replays** tab lists them;
  **Watch** plays a match again in the game exactly as it happened and checks it against the live match. START
  pauses, SELECT ends it. Recording and the players' names can be switched off there. A replay needs the game
  version that recorded it; a damaged or odd replay file is refused with a reason and leaves the rest of the list
  alone. **Report a problem** adds your newest replay, without names.
- **No pausing online.** START in an online fight opened the pause menu in both games, so one player could freeze
  the other in the middle of a combo. Now nobody can pause an online fight; START still skips the replay after a
  round, and offline it pauses as before. To leave a match, close the game (counts as a loss, as before).
- **No more frozen character select before the next match.** On a busy PC the select screen for a rematch or a
  new opponent could stay frozen while loading until the game was closed. Fixed; and should a select screen ever
  stop loading anyway, the game closes itself after 10 seconds and the launcher starts a fresh one for the match.
- **No more broken game after cancelled matches.** When four to eleven matches in a row ended at the character
  select without a fight (the opponent left during the pick, or the lobby cancelled), the open game broke. Now 60
  in a row are fine.
- **No more voided matches at the start of a fight on stage 27** (the crowd of fighters behind the ring): in about
  one match in 30 the desync check saw a value that only belongs to the picture (the box the shadows are drawn in)
  differ for a few frames, and the match was voided although the fight was the same on both PCs. That value is no
  longer compared; everything the fight depends on still is.
- **Different saves no longer desync.** Another round time or unlocks in one player's save could make a match go
  apart and be voided. Online games now use a fresh save of their own (`gamedata-online`), the same on both PCs.
  Your own save is never touched online; the game's own OPTIONS (button layout, round time) apply offline only, so
  set your buttons in the launcher.
- **You stay logged in when the lobby server restarts.** A saved login was forgotten whenever the server could not
  be reached (an update, an outage). Now the launcher keeps it and logs you in again by itself once the server is
  back (not during a fight, and not after you logged out).
- **A slow PC no longer desyncs the whole match.** Online, each frame waits until the game's
  loading threads are done, so a load finishes in the same frame on both PCs. That wait gave up
  after 2 seconds: on a PC with a slow disk or a very busy CPU the game then went on with its
  loads still running, the fight's intro ended a frame earlier or later than on the other PC,
  and every frame of the fight was apart (the match was voided). Now the frame waits as long as
  the loading takes, and the other game waits for it (it knows the opponent is loading, so it
  does not give up on it). A load that really hangs ends the match after 2 minutes with
  "Loading the fight took too long" instead of a desync. Three more places that gave up after a
  fixed time and could part the two games now wait or end the match cleanly: with rollback a game
  no longer runs ahead on guessed input beyond its limit while the opponent is slow, the step before the
  character select waits for the title's autosave however long it takes, and a pick that never
  comes from the opponent ends the match instead of a guessed fighter (docs/NETPLAY.md "Slow
  loading").

### Controllers
- **A pad that works offline now works online too.** Online, the game takes your input from the
  controller you press, whatever player port it has. Before, online play read player port 1 only, so
  a DualSense behind another controller -- a virtual Xbox pad from DS4Windows or DSX, a handheld's
  built-in pad, a second pad -- got port 2 and did nothing online, while it still played offline
  (player report: "my DualSense works only in offline mode"). A controller you don't press never
  takes over. If you set player 1's controller in `controls.ini` (`[port1] device = ...`), that one
  stays the only one. Both netcodes, in sync (docs/NETPLAY.md "Which controller plays online").
- **The launcher sees DualShock 4, DualSense and DualSense Edge** -- also over Bluetooth after Steam
  or DS4Windows used them, when it saw nothing from them before. The Online tab's A / B buttons work
  with them, and **Settings -> Set up controllers...** lists them, so you can set their buttons and
  which player they are. The launcher reads them like the game does, only while its window is in
  front, never sends anything to the pad and never keeps it from the game.
- **The game window comes forward when a match starts** after you clicked Accept or Rematch in the
  launcher, so the keyboard works without clicking into the game first (pads always worked).
- **Every button gets its own key or button, also on the keyboard** (Settings -> Set up controllers...):
  L1, R1, L2, R2, L3, R3, Start and Select, the four attack buttons and every Tekken combo (1+2, 3+4,
  1+3, 2+4, 1+2+3+4 ...), on a pad, a stick or the keyboard. The keyboard is now in that window like a
  controller (click its row): press the key for a button, start from a keyboard layout (arrows + A S Z
  X, WASD + U I J K, or the number pad), choose which player it is. A key or button that did something
  else is taken from there and the window says so; the game's own keys (Esc, F11, F2) are refused.
  Online the bound buttons arrive as what you set (owner: "R2 and L2 should have their own binds
  too").
- The Controls window no longer keeps the launcher busy while it is open (it kept re-selecting its
  controller row).

### Launcher
- **Five more languages:** Español, 한국어 (Korean), 日本語 (Japanese), Português (Brasil) and Français, besides
  English and Deutsch. **Settings -> Language**; Auto follows Windows. The new translations were made with machine
  help: corrections are welcome.
- **Unlocks** (**Settings -> Unlocks**, offline only, both off by default): **Unlock all stages** gives you the
  Tekken 5 stages without the roughly 50 fights they normally take; your save is not changed.
  **Unlock all customization items** makes everything in ITEM SHOP & EQUIP cost 0 Fight Money; what you take
  stays in your save, which the launcher backs up once first (`save-backups`).
- **The Settings tab scrolls** (mouse wheel, scrollbar), so every setting is reachable at 133 % display scaling
  and more.

### Game
- **Training overlay** (**Settings -> Training overlay**, on by default in Practice): your inputs with how long each
  was held, and the frame data of the last move: startup (`i10`) and who can act first on block, hit or counter hit
  (`+3`, `-12`). It can also show in the other offline modes, and online (your own inputs only). **F2** switches it
  in the game.
- **Stage blur and glow look right at every internal resolution.** At 1080p, 1440p and 4K the soft focus of the
  misty swamp and three other stages showed two or three sharp copies of every edge, and the sun's glow on the
  scrapyard was blotchy. New: **Settings -> Stage blur / glow** Off shows those stages sharp; online each player
  chooses for themselves.
- **Less CPU, and power saving for laptops and handhelds.** The game no longer busy-waits around its frames: on 8
  cores / 16 threads a fight needs about 30 % less CPU for the same 60 fps. **Settings -> Power saving** (Auto: on
  with a battery, a power-saving plan, a mobile processor or integrated graphics) also uses fewer helper threads,
  so the processor stays cooler and keeps its clock; the window title then says "power saving". Online, the other
  player does not need the same setting. Not tried on a real laptop or handheld yet.
- On a display whose timing is off, the game keeps its own clock, and it never runs faster than 60 fps.
- **The log and Report a problem say why frames are slow:** processor, graphics or showing the picture, with the
  power plan, clock limit and temperatures.
- **The build no longer stops at "Translate code".** When a helper process stopped (an antivirus or low memory can
  do that), the build waited forever at about 68 %. Now it translates that part itself and finishes with the same
  result; if the step stays silent for 3 minutes, the Build tab says what to do.
- **The intro movie no longer freezes on a white screen.** On a busy PC the video decoder sometimes never
  answered, and the intro stayed white with START doing nothing. The decoder now starts while the game boots; if
  it still does not answer within 5 seconds, the movie goes on in black with its sound (START skips it).

### Security
- **A lobby server has less say over your launcher:** a match name could make it write or delete files outside its
  folder, and a relay list could make it send pings anywhere and as often as the server liked. Match names and
  relay addresses are checked now.
- **Matches are harder to disturb:** a stranger who found your game's port can no longer end a match before it
  starts, and recorded match traffic can no longer send your game's packets elsewhere.
- When an account was last online is shown only to its friends; problem reports also remove lobby recovery codes.
- Prepared, not active yet: the launcher can check a signature on each update (`SHA256SUMS.sig`, made with the
  project's release key) and refuse a release somebody else put on GitHub, once that key is set up. 1.1.2 has no
  key yet, so updates are checked as before, against the release's SHA-256 checksums.

### Servers
- Friends, invites and the ping estimate need the updated lobby server; 1.1.0 and 1.1.1 launchers keep working
  with it and see nothing new. Its database gets numbered schema upgrades (the first adds the friends tables);
  going back to 1.1.1 or 1.1.0 still works (docs/HOSTING.md "Updates and restarts").
- **Tekken 5 stages online** (`T5L_OLD_STAGES`, off by default): matches between two 1.1.2 launchers may also be
  drawn on the 15 Tekken 5 stages (each played in sync in both netcode modes).
- Hardening: relay tokens are sealed on the way to regional relays, relay nodes refuse requests recorded before
  their restart, a flood of pings no longer blocks match setup, password changes are rate-limited, and the database
  is readable only by the server's user (docs/HOSTING.md).
- **Update notice:** `t5lobby-admin release 1.1.2` (only once the release is published) tells every launcher on an
  older release, in its status bar, that the new version is out.
- `t5lobby-admin drain --wait` also waits for ranked sets between two games: a restart no longer voids a set and
  the game already won. Friends entries left behind by accounts an older server deleted are dropped at start.
- A ranked queue with `T5L_PING_START=0` no longer stalls, and a relay node whose clock runs ahead of the lobby
  server's stays up after a restart.

## v1.1.1 (2026-10-19)

**Better connections, smoother rollback, PlayStation pads without Steam.** Both players need 1.1.1
(the lobby pairs equal game builds, and 1.1.1 changes the game: patches 0039 and 0042). The launcher
offers the update itself; after it, press **BUILD GAME** once.

### Online
- **Direct connections are much more reliable.** Before, whether two homes connected directly was
  partly luck (who started sending first); then the match fell back to the relay in Germany. Both
  sides now start at the same moment, try every address at once for longer, predict the ports of
  routers that change them, and open the game's port on the router (UPnP / NAT-PMP / PCP). In a
  network simulator, direct connections went from 926 to 1,130 of 1,400 router pairs, and a match
  that had to start on a relay switches to direct as soon as that works.
- **A relay server in the USA** (Oregon): players in America no longer detour through Germany when
  their routers can't connect directly (see Servers).
- **Smoother rollback at high ping:** a rollback costs 15% less; at 150 ms ping the slowest frames
  went from 23.1 to 21.4 ms and visible stutters per match from 56 to 37 (at 250 ms: 389 to 221).
- **No more desyncs on stage 27.** The fighters in the crowd at the back of the stage start their
  fights on timers that the stage set up from a timing-dependent random source, and their moves
  draw from the same random numbers as the two players. When the two PCs' crowds started a fight
  at different moments, the players' moves went apart too, minutes into a match, in lockstep and
  rollback alike (3 of 7 real games on stage 27 were voided). The stage now gets the same random
  numbers on both PCs, and the ambient sound no longer steps a random number the fight uses
  (docs/NETPLAY.md "Desync hunt 2").

### Controllers
- **DualShock 4 and DualSense work without Steam**, over USB and Bluetooth (DualSense Edge
  too). Over Bluetooth these pads switch to a fuller report once Steam ("PlayStation
  Controller Support"), DS4Windows or another game has used them, and keep it until they are
  turned off; Windows' DirectInput, which the game used, gets no input from that report, so
  the pad "only worked through Steam". The game now reads these pads itself in every report
  mode, with the same buttons and layouts as before, short taps included. It sends nothing to
  the pad, so other programs see it as before. Started through Steam with Steam Input on, the
  game uses Steam's virtual pad and leaves the real one alone (one pad, one player).
  `hid = 0` in `controls.ini` goes back to DirectInput. Not tried with a real pad yet: tested
  with reports of every mode built from the published formats (ps3recomp patch 0042).

### Launcher
- **VSync on/off** (Settings -> VSync): Off shows each picture at once (lowest latency, the
  picture may tear). The game still runs at 60 fps, like on the PS3; there is no frame rate
  setting. Online, both players can choose differently.

### Servers
- **Regional relays.** When two routers cannot connect directly, the match goes through a
  relay, and with one lobby server in Germany that meant Germany even for two players in
  California (300-400 ms ping). The lobby can now use small relay-only servers in other regions:
  each launcher measures its ping to every one of them, and a match that needs a relay goes
  through the one with the smallest sum of both players' pings (the lobby server's own relay
  included). Lobby, accounts and ranks stay on the one server. Both players need 1.1.1 (a
  future launcher-only update that pairs with older ones falls back to the lobby server's relay). A relayed match still
  switches to the direct connection when one opens up. For hosts: `install.sh --relay-only` now
  sets up such a relay server (docs/HOSTING.md "Adding a relay server"); the old option of that
  name, relaying every match, is `--force-relay`.

## v1.1.0 (2026-10-19)

**Online that holds up, a new launcher, ranked sets.** Both players need 1.1.0 (the lobby
pairs equal versions). After the update press **BUILD GAME** once. From this version on the
launcher updates itself: it offers every new release, one click.

### Online fixes
- **Matches no longer go out of sync after switching opponents.** The game has a second
  random generator (the camera uses it, and the camera decides which fighter stands on the
  left, so which way a sidestep goes). Netplay never reset it, so a game that had played
  someone else, or had just shown other effects, drifted apart from a freshly started one.
  It is now set the same on both PCs at every match start. Checked with 24 opponent
  switches, 240 Hz against 60 Hz, 4 against 16 cores, FMA against non-FMA CPUs, stalls and
  slow disks: all in sync. This also fixes Mokujin's pick and Devil Jin's third costume.
- **Rollback no longer crashes or hangs.** About one match in eight ended with the game
  closing (the game's file thread) when both players mashed; a rare freeze waited for a
  draw thread forever; a KO taken back by a rollback could leave no result at high ping.
  32 of 32 heavy-stutter matches and 12 of 12 KO matches at 250 ms ping ran clean.
- **Rematch works**, also after a new session and when a player changes character
  (moving from Bruce or Kuma to the top row used to loop). Closing the game window counts
  as leaving (a loss), not as an out-of-sync match.
- **No more frozen picture.** The graphics command ring overflowed on the first fight load
  on some PCs (6 and 8 cores) and froze the picture in the menus; fixed.

### In-game character select
- Online, you now pick your fighter and costume on the game's own select screen, like on the
  PS3: the confirm button picks the costume, Select picks at random, and after 30 seconds the
  character set in the launcher is taken. A rematch goes back to the select screen, so you can
  change fighter. In a ranked set you pick in game 1; games 2 and 3 keep both fighters and
  costumes.

### Offline fixes
- Sound needs 43% less processor time (crackles on weaker PCs), long sessions no longer use
  up the game's thread slots, and every background thread has its own memory again.

### New launcher
- Dark theme; **Play offline** and **Play online** tabs; the Online tab as clear cards
  (login, lobby, searching, match found with ping, in match, result).
- **German and English** (Settings: Auto / Deutsch / English).
- **Internal resolution** in Settings: Lowest, Lower, Native (720p), 1080p, 1440p, 4K. Both
  players can use different settings online.
- **Updates itself** from the published releases (checks the download, keeps your game
  and settings, goes back to the old version if anything fails).
- Launcher exe built with Microsoft's compiler (fewer virus-scanner false alarms).


### Ranked sets: best of 3, rated once
- A ranked match is now a set: the first player to win 2 games wins it (each game is still first to 3
  rounds). The rank moves once, at the end of the set. Between two games the next one starts by itself
  after a short countdown, with the same characters; the Online tab shows "Set 1-0 -- game 2 of 3", and
  the names in the fight show the games won ("Alice [1]").
- Leaving or quitting in the middle of a set loses it. A game that went out of sync is played again (at
  most twice per set). The daily limit of ranked results between the same two players counts sets.
- Needs the new launcher on both sides; against an older one every ranked game counts on its own, as
  before. docs/RANKED.md "Ranked sets".

### Controls screen
- New in the launcher: **Settings -> Set up controllers...**. Pads, arcade sticks and
  hitboxes get their buttons there instead of by editing `controls.ini`. It lists
  the controllers per player with a live "press a button" test, asks "Press the
  button for 1 (Left Punch)..." one button at a time (1 2 3 4, the macros 1+2, 3+4,
  1+2+3+4 and the others, Start, Select, directions) with Skip and Clear, and starts
  from a layout if you like: Xbox, PlayStation, Switch, arcade stick with 8 buttons
  (Vewlix), 6 buttons (Noir / Sega Astro), hitbox. It also sets which player a
  controller is, the left stick mode and the SOCD mode (left+right at once).
- Save writes the `controls.ini` the game reads, in the same format; your comments and
  other keys stay (the old file is kept once as `controls.ini.bak`). **Reset to
  defaults** takes a controller back. The controller itself works the screen once it
  is chosen (Up / Down, Cross, Triangle, Start, Circle).
- Checked against the game's own `controls.ini` parser (a test compiles the runtime's
  file reader and compares hundreds of generated files) and with simulated controllers;
  not yet tried with a real arcade stick by a person.

### Lobby server hardening (server only; 1.0.0 launchers work unchanged)
- Ranked results: a desync reported by one side only is no longer an instant void (the other
  game's clean report wins it, the claimant gets a strike); nobody is blamed for not reporting
  a match that may still be running (`T5L_MAX_MATCH_SECONDS`); a winner who reported and then
  logged out no longer loses; "disconnect" against a finished game counts the finished result;
  repeat disputers lose disputes (`T5L_DISPUTE_LIMIT`); two accounts on one address never play
  ranked against each other (`T5L_RANKED_SAME_IP`); a player behind in a ranked set who makes the next
  game's connection setup fail (blocked UDP, mute on the relay) loses the set (the server's evidence names
  the side; void only when it cannot tell).
- Abuse limits: TLS handshake only after the address checks (10 s), a cap on connections that
  have not logged in, rate limits for expensive and lobby-changing requests and for lobby-wide
  chat, at most 2 password hashes at once, parallel password guesses counted, look-alike and
  disguised reserved names refused, client text cleaned, IPv6 counted per /64, clients that
  stop reading dropped at once, the relay carries only game packets (per address and time
  limits).
- Durability: one database transaction per server step (a crash never leaves half a ranked
  result), matches running at a restart are voided cleanly, `admin drain` for restarts without
  voiding matches, crash-safe certificate and `host.json` writes, interrupted backups cleaned.
- Tools: `lobby/tools/soak_test.py` (simulated players and abusers, CPU, memory, threads,
  latency over time).

### Report a problem
- New launcher button **Report a problem...** (Play tab, Build tab, and the Online
  tab after a match). It makes one zip on the Desktop and opens its folder: the
  newest game logs, `build.log` when the build failed, the launcher's own log
  (`launcher.log`, new), the files of the last online match, `controls.ini`, desync
  dumps and `system.txt` (Windows, processor, graphics card and driver, memory,
  screens with refresh rate and scaling, release version and build id, the
  settings in use). A box "What happened?" is saved as `report.txt`.
- Private data is removed first: the Windows user name in paths (`<user>`), internet
  IP addresses (`<ip>`, local network addresses stay), passwords, tokens and match
  keys. The zip holds at most 20 MB; a huge log keeps its start and its end.

## v1.0.0 (2026-10-18)

**Tekken 5: Dark Resurrection Online 1.0.** Tekken 5: Dark Resurrection runs
natively on Windows -- recompiled, not emulated -- built on your PC from your own
copy (`.pkg` + `.rap`), with online play like Tekken 6 Native Online. First
online matches between two real PCs over the internet were played on 2026-10-18:
direct connection, 26 ms ping, 60 fps, rollback not noticeable.

Same game as 0.1.9-preview. Both players need 1.0.0 (the lobby pairs equal
versions). After the update press **BUILD GAME** once.

### Play
- All offline modes at 60 fps, music, sound effects and movies, saves.
- Keyboard, Xbox pads, PlayStation pads, arcade sticks and hitboxes; short taps
  are never lost (tried with an Xbox pad and an arcade stick).
- Runs on weaker PCs (60 fps fights on 4 threads), 3D resolution setting,
  any refresh rate, Windows 10/11 incl. N editions, any folder name.

### Online
- Launcher **Online** tab: account (username + password) or guest, quick and
  ranked matches, lobby rooms, the public server preselected.
- **Rollback netcode**, input delay by ping (launcher Settings: Auto/0/1/2;
  ranked fixed), 60 fps at 150 ms ping, one frame less input lag than before.
- The game starts **directly in the fight** and stays open for the next match
  (about 4 seconds to the next fight).
- Ranked: Glicko-2 rating with Tekken 5's rank names; names and ranks in the
  fight; block players, strict matchmaking, post-game lag check.
- Direct connection between the PCs, relay through the lobby server when routers
  don't allow it. Any two x64 PCs compute the same game (Intel/AMD, with or
  without AVX2).

### Fewer virus-scanner false alarms
- The zip carries **no script files** any more (0.1.8/0.1.9 were flagged as
  "Generic.BAT.Downloader" by 8 of 62 scanners because of helper scripts that
  never ran). The release build now refuses any script file.
- `T5DR Online.exe` is now an ordinary Windows application with an icon,
  version information and a manifest (the old 3.5 KB starter was flagged by 3 of
  71 machine-learning scanners). It is not code-signed, so Windows SmartScreen
  may still ask once: "More info" -> "Run anyway".

### Known issues (fixes planned for 1.0.1)
- **Closing the game with Alt+F4 during a match** voids the match instead of
  counting it as a loss, and the next one or two matches against the same
  opponent can be voided as "desync". Please end matches normally.
- With a very bad connection a rare crash can still happen after many matches;
  the launcher then starts the game again.
- The game's own **Online** menu entry and the Gallery need Sony's/Namco's old
  servers and show an error; use the launcher's Online tab.

## v0.1.9-preview (2026-10-18)

Same game as 0.1.8, with one file fewer in the zip.

- **Virus-scanner false alarm fixed.** 8 of 65 scanners on VirusTotal flagged
  0.1.8's zip as "Generic.BAT.Downloader". The cause was a one-line helper script
  for macOS developers that ships with every Python (`fetch_macholib.bat`, it
  calls `svn export` with a web address). Nothing ever ran it. It is no longer in
  the zip, and the release build now refuses any batch file in its Python.
- 0.1.8 and 0.1.9 can play each other only if both have the same version: please
  both update.

## v0.1.8-preview (2026-10-17)

Less input lag, steadier online. Both players need 0.1.8. After the update press
**BUILD GAME** once.

- **One frame less input lag** offline and online: the game reads the pad later
  and shows the frame as soon as it is ready.
- **Online input delay follows the ping**, like Tekken 6 Native Online: as low as
  possible for your connection. New launcher setting (Settings): Auto, 0, 1 or
  2 frames; both players' choice must allow it. Ranked uses a fixed delay.
- **Rollback holds 60 fps** at 150 ms ping (median; was about 50).
- **No more hang at the end of a match** with a bad connection: tested with a
  stuttering opponent, 13 matches without a hang (it hung at 3 of 4 before).
- The lobby server is updated for the fixed ranked input delay.

## v0.1.7-preview (2026-10-17)

More robust online play. Both players need 0.1.7. After the update press
**BUILD GAME** once.

- **After an aborted match** (opponent gone, connection lost) the open game is
  clean again and the next match starts normally. Tested: 10 of 10 cycles of
  "match -> abort -> next match" in one game, with rollback and with delay netcode.
- A button pressed in the very first frames of a fight no longer makes the game
  hang while loading (rollback).
- Some pairings (e.g. Asuka vs Law) no longer go out of sync against a freshly
  started game.
- If the game still gets stuck, it closes itself after 60 seconds and the
  launcher starts a new one.

Known: with a very bad connection (many corrections right at the final KO) the
game can still get stuck at the end of a match; it then recovers as above. A
fix is in progress.

## v0.1.6-preview (2026-10-17)

**Important online fix:** choosing Devil Jin online gave you Feng and the other
way round, and Kuma came out as Panda. Every character is now the one you pick
(checked for all 35 on the select screen). Both players need 0.1.6. After the
update press **BUILD GAME** once (about 2 minutes).

- **Delete Save Data** no longer deletes every save at once: a list shows your
  saves, you pick one and confirm.
- 18 system functions the game asks for now answer properly (e.g. Options ->
  Online Manual says "not available" instead of failing).
- The sound core's 13 effect functions (reverb, pitch, mix, ...) run as compiled
  code instead of an interpreter: less CPU work in fights.
- Checked: all 35 characters and 34 stages render; the background figures and
  the game's own Online menu (clean "network error", no crash) are fine.

## v0.1.5-preview (2026-10-17)

Faster on weaker PCs, and online stays in sync between any two PCs. Both players
need 0.1.5. After the update press **BUILD GAME** once (about 2 minutes).

### Performance
- **60 fps in fights on 4-thread PCs** (was about 32). Thread counts follow the
  CPUs the game may use; the main thread no longer spins while waiting.
- Rollback at 150 ms ping: about 50 fps on 4-8 threads (was about 30).
- **New: 3D resolution** (launcher -> Settings): Original, Lower or Lowest, for
  weak graphics cards. Players with different settings stay in sync.

### Online
- **Any two x64 PCs compute the same game**: Intel or AMD, with or without
  AVX2/FMA. The game code no longer uses math that differs between CPUs.
  Tested: 160,000 frames compared between different builds, 0 differences.
- **Fewer void ranked matches:** camera and cloth-motion values that could
  differ for a few frames at a KO (e.g. Bryan vs Steve) no longer count as a
  desync.

## v0.1.4-preview (2026-10-17)

Online feels like Tekken 6 Native Online now, and the game runs on more PCs.
Both players need 0.1.4. After the update press **BUILD GAME** once (the game
code changed; it takes about 2 minutes).

### Online
- **The game stays open for a new opponent**, not only for a rematch: 5-7
  seconds from Accept to the fight (was about 20).
- **Your lobby names and ranks show in the fight** instead of "Unknown".
- **Mashing buttons at the final KO** no longer starts a stray VS battle that
  blocked the next match.
- **Fewer void ranked matches:** camera values that differed for a moment
  between the two PCs no longer count as a desync.

### Runs on more PCs
- Folder and Windows user names with any characters (e.g. `Ł`, `東京`) work; the
  game did not start there before.
- Windows N editions work (movies need the Media Feature Pack; without it they
  stay black and the game runs on).
- TVs and monitors below 60 Hz (50 Hz, 30 Hz) no longer slow the game down;
  120/144/165 Hz monitors keep the exact game speed.
- Laptops with two graphics chips use the fast one.
- A graphics driver crash shows a message instead of a frozen window.
- The window has the right size with Windows scaling (125-200 %).
- The launcher finds OneDrive folders and warns if the game folder is inside one.

## v0.1.3-preview (2026-10-17)

**Rollback netcode is the online default, like Tekken 6 Native Online.** Both
players need 0.1.3 (the lobby pairs only equal versions).

- **Rollback:** your own inputs act after 2 frames, whatever the ping. When the
  opponent's input arrives late, the game corrects itself in the background.
  Tested at 0, 50 and 150 ms ping with 3 % packet loss and jitter: two matches
  plus a rematch in one game, in sync, no crash, no hang.
- **Sound with rollback:** a sound is never played twice and never cut; music
  runs on without gaps.
- **Fallback:** if a match stutters because a PC is too slow, one player can
  switch to the older delay netcode: launcher -> Settings -> "Advanced: extra settings",
  add the line `T5_RB_MODE=off`. The match then runs with delay netcode on both PCs.
- Players who don't offer rollback (older builds of the same version) get delay
  netcode automatically.

## v0.1.2-preview (2026-10-17)

**Use this version for online play.** 0.1.0 and 0.1.1 could not play online:
their zip lacked part of the online code, and match results were not counted.

- **Online works from the zip.** The prebuilt game program now contains netplay
  and the direct start into the fight. A new check in the release test fails if
  they are ever missing again.
- **Match results count.** The winner is read correctly, so quick and ranked
  matches are confirmed instead of void (14 of 14 test matches, both winners).
- **Windows Firewall:** `TROUBLESHOOTING.md` has a new "Online play" section:
  what to click, where the prompt hides, what the status messages mean.
- **Tried on real hardware** (2026-10-17): an Xbox pad and an arcade stick, every
  input came through, the game ran smoothly.
- Launcher: use it with a pad or stick (A / Cross accepts and searches, B / Circle
  declines and cancels), only while the launcher is in front.
- Sound comes back when a headset or speaker is plugged in later, unplugged or
  switched; the game's timing never changes.
- Host for friends no longer crashes on a German Windows (router lookup).

## v0.1.1-preview (2026-10-17)

The first release on this page. Same as 0.1.0-preview (built and tested the
same day), plus:

- **Music is read straight from the game's archive.** The music stream no longer
  depends on how the game feeds it. This was needed for rollback netcode and also
  makes the music more robust offline.
- **License**: the project's own code is MIT-licensed; the text is in the zip
  (`LICENSES\T5DR-Online-MIT.txt`).

Test build. Tekken 5: Dark Resurrection runs natively on Windows,
built on your PC from your own copy (`.pkg` + `.rap`). Online play between
friends works through the launcher, the same way as Tekken 6 Native Online.
Expect bugs, and please report them.

### Play
- All offline modes: Arcade, Ghost, Versus (two players on one PC), Survival,
  Practice. Music, sound effects and movies.
- 60 fps in menus and fights, also with other programs busy on the PC.
- Fighters and stages render correctly: faces and floor shadows fixed. Resizable
  window, borderless fullscreen (Alt+Enter or F11), higher render resolutions.
- Saving works. The in-game clock shows the real date. The old white-screen
  memory bug is fixed.

### Controls
- Keyboard, Xbox pads (XInput), PlayStation pads, arcade sticks and hitboxes
  (DirectInput), two local players, `controls.ini` for remapping.
- Short taps are never lost: the pads are read every millisecond, and a press
  between two game reads still reaches the game, also online.

### Online
- Launcher Online tab: log in or play as a guest on the public server (preselected).
- Quick and ranked matches, lobby rooms. A found match shows the ping; accept it
  within 15 seconds. The game starts directly in the fight, first to 3 rounds,
  and stays open for Rematch / Next game.
- Ranked: Glicko-2 rating shown with Tekken 5's rank names. Leaving or
  disconnecting counts as a loss, a desync voids the match. Block players,
  optional strict matchmaking, character locked for a ranked set, a post-game lag
  check (too laggy -> leave without penalty).
- Direct connection between the two PCs, with a relay through the lobby server
  when the routers don't allow it. Tested with packet loss, jitter and outages.
- Delay-based netcode (2-3 frames of input delay). Rollback is being finished
  and comes in a later update.
- Run your own server: Linux VPS, Docker, Mac, or **Host for friends** in the
  launcher (`docs/HOSTING.md`).

### Known limits
- Tested on one development PC. Not yet tried on a clean PC or between two real
  PCs over the internet. Weaker PCs are not measured yet.
- Real arcade sticks are not yet tried by a person.
- Some background figures may look flat white.
- The game's own **Online** menu entry crashes after the terms screen. Use the
  launcher's Online tab.
- The first time, Windows Firewall asks about the network: allow it for private
  networks.

## v0.1.0-preview (2026-10-17)

First public test build. Tekken 5: Dark Resurrection runs natively on Windows,
built on your PC from your own copy (`.pkg` + `.rap`). Online play between
friends works through the launcher, the same way as Tekken 6 Native Online.
Expect bugs, and please report them.

### Play
- All offline modes: Arcade, Ghost, Versus (two players on one PC), Survival,
  Practice. Music, sound effects and movies.
- 60 fps in menus and fights, also with other programs busy on the PC.
- Fighters and stages render correctly: faces and floor shadows fixed. Resizable
  window, borderless fullscreen (Alt+Enter or F11), higher render resolutions.
- Saving works. The in-game clock shows the real date. The old white-screen
  memory bug is fixed.

### Controls
- Keyboard, Xbox pads (XInput), PlayStation pads, arcade sticks and hitboxes
  (DirectInput), two local players, `controls.ini` for remapping.
- Short taps are never lost: the pads are read every millisecond, and a press
  between two game reads still reaches the game, also online.

### Online
- Launcher Online tab: log in or play as a guest on the public server (preselected).
- Quick and ranked matches, lobby rooms. A found match shows the ping; accept it
  within 15 seconds. The game starts directly in the fight, first to 3 rounds,
  and stays open for Rematch / Next game.
- Ranked: Glicko-2 rating shown with Tekken 5's rank names. Leaving or
  disconnecting counts as a loss, a desync voids the match. Block players,
  optional strict matchmaking, character locked for a ranked set, a post-game lag
  check (too laggy -> leave without penalty).
- Direct connection between the two PCs, with a relay through the lobby server
  when the routers don't allow it. Tested with packet loss, jitter and outages.
- Delay-based netcode (2-3 frames of input delay). Rollback is being finished
  and comes in a later update.
- Run your own server: Linux VPS, Docker, Mac, or **Host for friends** in the
  launcher (`docs/HOSTING.md`).

### Known limits
- Tested on one development PC. Not yet tried on a clean PC or between two real
  PCs over the internet. Weaker PCs are not measured yet.
- Real arcade sticks are not yet tried by a person.
- Some background figures may look flat white.
- The game's own **Online** menu entry crashes after the terms screen. Use the
  launcher's Online tab.
- The first time, Windows Firewall asks about the network: allow it for private
  networks.

## 2026-10-16 (day one)

Everything below landed on `main` in one day, except the player docs.

### Docs, controls and CI

- **Player docs** (branch `player-docs`, not on `main` yet). The README is
  rewritten for players. New: a German README (`docs/README.de.md`),
  `docs/TROUBLESHOOTING.md` and this changelog.
- **Controls** (`f158ee2`, patch 0009). DirectInput 8 next to XInput, so
  PlayStation pads, DualShock 4, DualSense, arcade sticks and hitboxes work, also
  while the window is unfocused. Two local players, hot-plug, and a `controls.ini`
  for remapping with presets and macros (`docs/controls.ini` documents every
  default). Not yet tried on real hardware by a person.
- **CI on GitHub** (`c8ee350`, `5c2bb02`, `b38da79`). Every push and pull request
  runs a guard that fails on anything game-derived, Python tests, the lobby tests
  and a build of the patched runtime. No game data is used, so CI cannot boot the
  game. See `docs/CI.md`.

### Launcher, release and lobby

- **Launcher** (`43fb9e3`). A Windows program with four tabs: Build, Play,
  Settings, Online. Pick your `.pkg` and `.rap`, click BUILD GAME, click PLAY. It
  shows progress, one plain red sentence when something fails, and keeps the last
  10 game logs. The Online tab was a placeholder at first.
- **Build for players** (`88325eb`). Everything goes under one folder (`native`).
  The version and license are checked **before** the 600 MB unpack, so a wrong
  copy is refused within seconds (1.6 s measured).
- **No Visual Studio needed** (`88325eb`, `1b35ec4`, patch 0020). The runtime is
  shipped precompiled. The player's PC compiles only the game code into
  `t5dr_game.dll` with a bundled clang-cl and lld-link. Measured from the packaged
  zip with a bare Windows PATH: BUILD GAME 90 s, game at 60 fps, 90 MB zip.
- **Release zip** (`e91f37c`). `tools/package_release.py` builds the zip and scans
  it, and again after zipping, for game files, lifted code and keys. It refuses to
  package on any hit. `docs/RELEASE.md` has the numbers.
- **Lobby** (`ff5e5ea`, `d6b9c18`, `213b52f`). A server and client in plain Python:
  guest and account logins, rooms, quick and ranked matches (Glicko-2), NAT hole
  punching with a relay fallback, build check, rate limits. Hardened later:
  only private LAN addresses as punch candidates, a guard against deeply nested
  JSON, a rate-limited relay. 55 tests. The Online tab for it (`02f78ad`) exists
  in the lobby code but is not wired into the launcher yet. `docs/ONLINE.md`
  documents it, including running your own server. Tested on one PC only.
- `docs/RELEASE.md` (`1938fa5`) has the numbers measured from the 0.1.0-rc1 zip.

### Game: it plays

- **Movies** (`ea5020a`, patch 0006). Intro and title movies play with sound. H.264
  is decoded with Windows Media Foundation, and the ATRAC3plus audio is decoded
  too. About 30 pictures per second.
- **Music** (`277d475`, patch 0003). The ATRAC streaming API works, so music plays.
  The choppy sound is fixed: silent mixed blocks fell from about 55 % to about
  0.1-1.6 % (measured under load).
- **Fighters render** (`eb7a5b2`, patches 0002 and 0007). The SPURS skinning jobs
  run, so the fighters are visible. Menus 60 fps, fights about 40-44 fps.
- **60 fps timing** (`c6ca38e`). Vblank now runs at 59.94 Hz on the performance
  counter. Before, the game ran 4 % fast.
- **Quiet window for tests** (`32b2339`, patch 0021). `PS3_WINDOW_BACKGROUND=1`
  opens the game window minimized, also with the live-draw renderer.

### Game: first boot

- **Sound core and graphics** (`9b0d7bc`, `fb45576`). The SPU sound core is
  translated and runs. The D3D12 live-draw renderer is on by default. Audio pacing
  is even (5.33 ms blocks) and a non-48 kHz sound device no longer silences the
  game. The log is quiet (`PS3_VERBOSE=0`), which lifted the game from about 34 to
  about 63 fps. The game reaches menus and fights.
- **Build pipeline and first boot** (`a18f995`). `tools/build_game.py` goes from the
  `.pkg` and `.rap` to a running `t5dr.exe`: unpack, decrypt, check the program's
  SHA-1, translate 23,059 functions, compile with clang-cl. The game boots, opens
  its D3D12 window and loads its data.

### Start of the port

- **Decryptor** (`a811497`). Our own `tools/unself.py` decrypts the game's
  `EBOOT.BIN` with your `.rap`. The keys are read from a local, git-ignored file.
  First findings: 16,856 functions found, 252 imports in 20 libraries, one SPU
  sound core, PSN calls that we will bypass.
- **Project start** (`9a5ebe0`). Ground rules, the plan, and a `.gitignore` that
  blocks everything game-derived. The repository is public: nothing from the game
  goes in.

## Known problems at the end of the day

See the status table in the README and `docs/TROUBLESHOOTING.md`. The main ones:
fights run at 30-45 fps, every fighter's face is dark, a memory bug can turn the
screen white after repeated visits to the title, saving is unreliable, and
online play is not playable yet.
