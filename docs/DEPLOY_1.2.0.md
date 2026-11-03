# Deploying 1.2.0 drafts (unreleased)

This combines the badge/mention, TCP 443 fallback and casual-room deployment drafts. It is a maintainer
checklist, not a deployment record. Nothing has been built, deployed or released by this integration;
no server has been started or contacted and no firewall has been changed. `codex/accounts` remains separate.
Use the feature-specific checks and rollback steps below together when deploying the combined lobby.
Runtime changes elsewhere in 1.2.0 also require the build and real-pair checks in their own feature documents.

## Package 5 readiness gates (pending owner checks)

These steps describe work to complete in the owner's permitted test and deployment environment. They are
not execution evidence: no launcher, server, migration or deployment was run for this checklist. Do not
accept package 5 from green source-only tests or a schema-version number alone.

1. Resolve and execute the two reported test failures first. The casual-set test bypasses
   `MatchDriver.__init__`; construct the real driver and dispatch the result through public `on_event`
   before verifying its automatic next-game acknowledgement. The release-notice test still expects
   `your 1.1.1` from an intentionally removed incompatibility claim: compatibility groups can permit
   cross-release play. Update the assertion to check update guidance without restoring the false
   "cannot play against" wording. Show the reported failures before the corrections and passing tests
   afterward through the actual test entry points. Neither correction is claimed implemented here.
2. Run the actual launcher entry through `main()`, `App` and the Tk mainloop, with bounded clean shutdown
   and isolated settings. Check startup, login/search, clear display of `kicked` with no automatic
   relogin loop, then match/ready/result, rooms/friends and tournaments/spectating in that order. Keep
   the existing T5DR launcher in the mixed-client checks. Fake widgets and extracted-method tests do
   not establish launcher startup. Decide saved-login sharing and how both launchers refuse another
   search while a game is already running before accepting the new launcher.
3. Exercise real historical client code read from git against the real new server code in the owner's
   test environment, and new clients against the intended older server. Record the exact revisions
   and executed cases. The legacy fixture's default `v1.1.6` tag is absent in this checkout and can
   silently skip those tests; a skipped fixture is not compatibility evidence. Supply an available,
   intended historical revision through `T5L_SIDES_OLD_REF` (`test_sides.py`) and `T5L_COMPAT_REF`
   (`test_relays.py`, whose default `v1.1.0` is also absent). Verify each revision contains the intended
   shipped client source; an available commit alone does not prove it was released. Require the cases
   to execute. Keep lobby protocol version 1.
4. Rehearse storage changes on a private backup copy and verify existing accounts, sessions, matches,
   sets, character stats and intended code rollback. Use a single database opener: stop the service,
   administrator timers and every other process opening that database during rehearsal and upgrade.
   Serialize backup jobs too: concurrent filename reservation and stale partial-file cleanup are not
   proved safe. Keep scheduled and manual backup jobs from overlapping the upgrade backup.
   `Store` reads the schema version before acquiring each migration's write lock; its column
   check/`ALTER TABLE` sequence can also race with another opener. Setup DDL runs outside the numbered
   migration transaction. These source findings mean concurrent live migration safety is unproved.
   Use the existing administrator tool for the pre-upgrade drain and backup, before new code opens
   production storage. Preserve the upgraded database on code rollback as described below; do not
   replace newer records with an old backup merely to remove additive schema changes.
5. Complete the feature checks in [INTEGRATION_1.2.0.md](INTEGRATION_1.2.0.md),
   [COMPATIBILITY_GROUPS.md](COMPATIBILITY_GROUPS.md), [CHAT_FILTER.md](CHAT_FILTER.md),
   [NETPLAY.md](NETPLAY.md) and [RANKED.md](RANKED.md):
   - Lobby-supplied update metadata, version refusal, stale/malformed metadata and fallback must still
     accept only valid signed updates. Verify real TLS on normal TCP 7781 and fallback TCP 443.
   - Negotiate Auto and manual delay limits, including 8, across sets and rematches; old peers retain
     their legacy limits. Check chat delivery, filter configuration/reload and rate limits.
   - Verify per-character ranked stats survive reopening without changing unrelated character stats;
     verify casual/ranked set scores, continuation, abandonment and room rotation with mixed clients.
   - Keep `T5L_COMPAT_GROUPS` empty until the owner approves complete build IDs after real cross-build
     pair tests with **0 mismatches**. Check excluded builds and peers fail closed; retain documented
     exact-build restrictions for tournaments and spectators. Test direct and relay game paths too.
6. Keep shared T4 accounts and concurrent per-game sessions behind the separate post-T4-release review.
   The account draft is absent from the working tree but readable without checkout using
   `git show origin/codex/accounts:docs/PLAN_ACCOUNTS.md`. It describes an unrun opt-in split-store
   implementation, with T4 authentication/social features only and gameplay blocked pending a verified
   adapter. Its numeric T4 rating fallback leaves authoritative text rank names and owner-approved
   thresholds pending. Review it after the agreed reset and T4-release gates; do not import or deploy
   `codex/accounts` as part of this deployment. Current T5DR login behavior is account-global:
   one connection per account; a second login takes over and
   kicks the first. The future shared-account policy must allow T5DR and T4 online simultaneously with
   separate sessions, matches and ranks per game, carrying over existing T5DR accounts. It must not
   give other game developers access to these accounts. Do not claim T4 ready or deploy that draft.

After these gates pass, follow the drain, backup, installation, optional TCP 443 and rollback procedures
below. Publication and deployment remain owner actions; this checklist authorizes no deployment.

## Combined database and private-chat rollout

Review the complete integrated schema before deploying: badge migration 2 is not the only additive database
change. Opening this server or administrator tool also creates the `private_reports` table through the base
`SCHEMA`, even when private chat is disabled. This table does not increase `PRAGMA user_version` beyond 2.
On a private backup copy, check the upgrade, existing account/match/set records, reopening with the new code,
and reading with the intended older rollback code. Retain the upgraded database when rolling code back;
restoring an old backup would lose records created since that backup.

Private chat defaults on (`T5L_PRIVATE_CHAT=true`) for clients negotiating `private_chat`. To stage the rest
of 1.2.0 before enabling that feature, explicitly set `T5L_PRIVATE_CHAT=false`. Neither setting stores ordinary
conversation transcripts. Explicit reports store only the player's selected 1–5 authenticated lines in
`private_reports`. Before enabling it, assign moderators, communicate that selected reports are retained,
and review `T5L_PRIVATE_REPORT_DAYS` (30 days) and `T5L_MAX_PRIVATE_REPORTS` (1000). Verify report receipt,
pruning, deletion and backup retention on the private test database. Code rollback does not erase retained
reports or database backups. See [PRIVATE_CHAT.md](PRIVATE_CHAT.md) for limits, review commands and the
required two-launcher checks. These are pending owner checks; no migration, server or deployment was run here.

## Account developer badges and public chat mentions

The central lobby server must be deployed for these social features. Badges and mentions leave regional relay nodes
and the game simulation unchanged. All changes are left in the working tree for maintainer review; no deployment has been performed.

### Server changes

- Numbered schema migration 2 adds `accounts.badge`, constrained to `''` or `'dev'`, with `''` as the default.
  The existing migration runner applies it once when the new server or administrator tool opens the database.
- The administrator tool gains `t5lobby-admin badge NAME dev` and `t5lobby-admin badge NAME --clear`.
  Names containing spaces must be quoted. The badge is account metadata, not a permission or a player-editable field.
- Connected accounts pick up changes within `T5L_ADMIN_POLL` seconds. New logins load the stored badge.
- Capabilities `badges` and `mentions` gate the new fields per recipient, including full and delta rosters.
  The server resolves mention targets from sanitized public chat and its current online roster. Existing chat
  rate limits apply. No private messaging endpoint is added.

### Maintainer deployment steps

Use the established process in [DEPLOY_1.1.9.md](DEPLOY_1.1.9.md), with a backup before migration:

1. Review and test the working-tree changes in the maintained project. Run the three new offline test modules
   listed below, the localization checks, and the full lobby suite in the maintainer's permitted environment.
2. Exercise schema 1 to schema 2 on a copy of a backup. Confirm existing accounts receive an empty badge, changing
   and clearing a badge persists, and reopening the database leaves it at version 2.
3. Announce maintenance, drain matches and ranked sets, and back up the production database with the existing
   administrator tool. Deploy the reviewed 1.2.0 lobby code and administrator wrapper, then restart the lobby.
4. Confirm schema version 2 and normal server health. No new environment variables are required for badges and mentions; the optional TCP fallback setting is described below.
5. Use the administrator command on the intended account. With two 1.2.0 launchers, verify the DEV marker in the
   player list and chat, then clear it and verify its removal after the polling interval. Guests and ordinary
   accounts must have no marker. Test logout, remembered login and session reconnection.
6. Mention the second player with exact names, case differences, spaces and punctuation. Check Tab completion,
   highlighting, and a chime/flash while the recipient is elsewhere. Verify the notification setting and ordinary
   chat rate limits. Unknown names and forged client target/badge fields must not create a ping or badge.
7. Check an old launcher against the new server and a new launcher against an old server: chat and roster updates
   continue normally, with new fields only after negotiation. Also check mixed recipients and roster deltas after
   granting or clearing a badge.

### Badge rollback

The migration only adds an account column. Earlier lobby code leaves it alone and should continue reading the
upgraded database; verify this on a backup copy before deploying. Drain before switching code back. A database
restore is only needed to undo the migration itself and would discard any account/match changes after the backup.
Do not restore an old backup over newer production records merely to remove this additive column.

### Badge and mention verification

New regression tests live in `lobby/tests/test_social_server.py`, `test_social_client.py`, and
`test_chat_features.py`. They use in-memory stores and fake connections/widgets, without starting or contacting
a server or running a game. Run each through unittest discovery, for example:

```text
python -B -m unittest discover -s lobby/tests -p test_social_server.py -v
python -B -m unittest discover -s lobby/tests -p test_social_client.py -v
python -B -m unittest discover -s lobby/tests -p test_chat_features.py -v
python -B tools/i18n_extract.py
```

These commands are pending maintainer checks; this document does not claim that they have run. No build, server, or game was started or contacted as part of this integration. A real launcher build is needed
to prove packaged UI layout and notification behavior; a deployed lobby is needed to prove live polling, mixed
client compatibility and delivery. Badges and mentions do not change the game simulation.

## TCP 443 fallback

Central lobby and 1.2.0 launcher changes. Relay-only nodes stay as they are. Nothing in these instructions was
run against production, and no firewall was changed. Local socket tests cannot prove reachability from the
affected player's network.

The normal listener remains TCP 7781. A second listener can accept the **same TLS lobby protocol** on TCP 443,
using the same certificate, session store, connection limits and handlers. This is raw TLS, **not HTTPS**:
an HTTP reverse proxy or a network that permits only real HTTPS may still reject it. Keep the existing
`servers.json` entry, host and certificate fingerprint. A new pin or a switch to unverified TLS is not needed.
The server can be deployed first; older launchers keep using 7781 and need a launcher update for automatic
fallback. No database migration or wire protocol change is needed for this listener.

### Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `T5L_TCP_FALLBACK_PORT` | `0` (off) | Additional TCP control listener on `T5L_HOST`; use `443` on the public lobby. Requires the existing TLS certificate and key. |

The normal `T5L_PORT` and UDP settings stay as they are. Setting a fallback port does not move any UDP traffic
to that port. Certificate renewals follow the existing reload path on both TLS listeners.

### Maintainer steps (Linux/systemd)

Use the archive, staging checks, notice, drain and backup procedure in [DEPLOY_1.1.9.md](DEPLOY_1.1.9.md) with
the 1.2.0 code. Do not run the installer here or against a live server as part of a coding-agent check.

1. Before enabling the listener, check that **TCP 443 is free on every address the lobby binds**, including
   IPv6 (`sudo ss -ltnp 'sport = :443'`). A web server on that address must be moved or use a different address;
   the lobby cannot share its socket with HTTPS. Preserve the current TLS certificate and fingerprint.
2. Drain and back up, then install the code with `install.sh --self-signed --firewall none` from the reviewed
   release folder, as in the earlier deploy notes. Keep the existing env file and TLS files. For an instance
   using another TLS provisioning method, preserve that method rather than replacing its certificate.
3. From that release folder, install this **optional** drop-in:

   ```sh
   sudo install -d -m 0755 /etc/systemd/system/t5lobby.service.d
   sudo install -m 0644 lobby/deploy/linux/t5lobby-tcp443.conf /etc/systemd/system/t5lobby.service.d/tcp443.conf
   ```

   It grants only `CAP_NET_BIND_SERVICE` through both `CapabilityBoundingSet` and `AmbientCapabilities`.
   The base unit's `User=t5lobby`, `Group=t5lobby`, `NoNewPrivileges=yes` and other hardening remain in effect.
   Do not run Python as root or apply `setcap` to a shared Python executable. Do not install this drop-in on a
   relay-only node. The drop-in survives routine installs of the base unit.
4. In `/etc/t5lobby/t5lobby.env`, add or replace a single line `T5L_TCP_FALLBACK_PORT=443`. Verify the existing
   `T5L_TLS_CERT` and `T5L_TLS_KEY` still point to the current readable files. No separate certificate is used.
5. Run `sudo systemctl daemon-reload`, then `sudo systemctl restart t5lobby`. Check:

   ```sh
   sudo systemctl show t5lobby -p User -p Group -p NoNewPrivileges -p CapabilityBoundingSet -p AmbientCapabilities
   sudo ss -ltnp '( sport = :7781 or sport = :443 )'
   sudo t5lobby-admin health
   sudo journalctl -u t5lobby --since '-5 min' --no-pager
   ```

   Both TCP listeners must belong to the lobby service, the process must run as `t5lobby`, and the only granted
   capability must be `CAP_NET_BIND_SERVICE`. A bind failure must be fixed before accepting deployment as done;
   do not hide it by disabling certificate verification or running the service as root.
6. The maintainer must separately allow **inbound TCP 443** in the host and provider firewalls if required,
   retaining the existing TCP 7781 and UDP rules. For an existing ufw deployment, the reviewed change would be
   `sudo ufw allow 443/tcp comment t5lobby-tls-fallback`; for nftables, add the equivalent TCP rule to the maintained
   ruleset and load it through the normal operations procedure. No installer or firewall template in this
   change opens 443 automatically. Keep status/metrics on loopback; no UDP 443 rule is needed.

### Docker alternative

Keep the unprivileged container user and `cap_drop: [ALL]`. Set `T5L_TCP_FALLBACK_PORT=8443` in the container's
env file, with its normal TLS certificate paths, and add `"443:8443/tcp"` to the Compose `ports` list beside
`"7781:7781/tcp"`. The host publishes 443 to a high container port, so the Python process needs no low-port
capability. Do not also set the container listener to 443. The host firewall and port-occupancy checks above
still apply. No container build or deployment was performed here.

### What the blocked-network check must show

Use the 1.2.0 launcher from the affected country, both with WARP off and with the player's usual WARP setup.
Record the result of each path; success through WARP alone does not prove the blocked route works.

- With TCP 7781 unavailable, login, chat and lobby lists must work automatically through TCP 443 on the same
  host. No manual server edit, new certificate prompt or weakened pin is acceptable.
- Let a normal-port session run long enough to reproduce the previous reset (`WinError 10054`), or arrange an
  equivalent interruption during an agreed test. The launcher must reconnect through 443 within the existing
  reconnect window, retain its authenticated identity, and remain connected longer than the previous cutoff.
  Check that reconnecting does not duplicate a challenge, queue action or result report.
- Repeat with the configured pin deliberately wrong: connection must be refused on both paths. Restore the
  correct pin before further tests. A successful TLS connection must never become a plaintext retry.
- Check a normal network too: 7781 remains usable and older launchers still work. A busy 443 or missing Linux
  capability must be visible as an operator error, with a working rollback procedure below.

**What stays on UDP:** lobby ping and NAT registration/measurement (normally UDP 7781 and the second probe on
7782), hole punching, peer-to-peer game packets, and game relay packets (including regional relay nodes).
TCP 443 does not carry game traffic and cannot fix blocked UDP, poor routing, jitter or packet loss on those
paths. Lobby login success alone does not establish that a match is playable. Prove a direct match and, where
needed, a relay match separately on the real network. A real two-PC game test must complete with **0 sync
mismatches**; this transport change does not alter the simulation.

### TCP fallback rollback

Drain and back up before changing the running service. Set `T5L_TCP_FALLBACK_PORT=0` (or remove it), remove only
`/etc/systemd/system/t5lobby.service.d/tcp443.conf`, then run `sudo systemctl daemon-reload` and restart. Confirm
the base unit has empty capability sets and serves the original listener. If reverting to pre-1.2.0 server
code, use its reviewed installer after the drain; the listener itself needs no database rollback; also follow the badge migration guidance above when reverting the combined server. The maintainer
should remove any newly added TCP 443 firewall rule separately if it is no longer needed. Existing 1.2.0
launchers can still connect on the normal port; a network blocking that port loses the fallback when disabled.

### TCP fallback verification

Local socket regressions live in `lobby/tests/test_tcp_listener.py` and `lobby/tests/test_tcp_fallback.py`.
`lobby/tests/test_deploy.py` checks that the opt-in systemd drop-in grants only low-port binding while retaining
the unprivileged user and hardening, and that an ordinary install keeps empty capability sets. These checks do
not execute systemd, change a firewall or contact a public server. Real Linux binding to 443, release packaging
and the blocked-network checks above remain maintainer checks.

The draft's socket tests require a separately permitted environment and were not run as part of this integration. The socket tests replace the TLS boundary with stand-ins;
they inspect context/hostname/pin handling but do not prove an actual TLS handshake. The deployment test is a
static check of the templates, not a proof of Linux runtime capability handling. Pending commands, from the
repository root:

```sh
python -m unittest discover -s lobby/tests -p test_tcp_listener.py -v
python -m unittest discover -s lobby/tests -p test_tcp_fallback.py -v
python -m unittest discover -s lobby/tests -p test_deploy.py -k Tcp443ServiceTest -v
```

Run these before deployment, then verify real TLS interoperability, Linux capability handling and the blocked
network as described above. No build or game run was performed here.

## Casual first-to sets

Casual challenges, friends' casual invites and casual rooms can choose FT1, FT2, FT3, FT5 or FT10.
The central lobby server owns the target, score, next game and room turn. The launcher sends the choice and
displays that state. Ranked keeps its own best-of and rating; tournament brackets keep their existing rules.
Quick Match remains a single-game queue. See [ONLINE.md](ONLINE.md#casual-first-to-sets-120).

### Deployment scope

- Deploy the updated central lobby package, including `t5lobby/server/lobby.py`, `server/rooms.py` and the shared
  `proto.py`. Reuse the normal backup, drain, install and health-check procedure in
  [HOSTING.md](HOSTING.md); this document does not authorize running it against a server.
- Ship the matching launcher/client package for the selector and score display. A new launcher waits for the
  server feature `casual_sets`; a pair needs both clients to advertise `casual_sets` and `sets`. Older clients
  stay on single games, even when a room's configured target is longer. There is no protocol-version bump.
- No database migration, new rating effect, relay deployment or game-memory address is needed for this feature.
  Each casual game's existing result record is kept; summaries and game-to-set links use the existing set
  tables and match fields. Live casual set state is held in server memory and does not resume after a lobby restart.
- No new server setting is required. Ranked's existing set and away settings retain their ranked meaning;
  casual progression uses the existing next-game countdown.

### Fields for another launcher

Send `first_to` (an integer in `1, 2, 3, 5, 10`, default `1`) with `challenge`, a casual `invite`, or casual
`room_create`. Room metadata exposes the configured target; room members also receive the active `set`.
The effective target is negotiated per pair, so use the match/set metadata to render what will be played.

For casual sets, existing match events' `set` object carries `casual: true`, `rated: false`, `first_to`,
`wins_needed`, `wins`, `number`, `state`, and the existing `next` countdown. Match set scores use P1/P2 order;
`set_end` carries the set id in `set` and top-level `casual`, `rated`, `first_to`, `wins_needed`, `status`,
`outcome_reason`, `result`, `wins` in you/opponent order and `rating: null`. Legacy single games have no casual
set metadata. Use `set_next {keep}` for continuation and `leave_set` to
leave between games. The server counts wins and ends the set; clients do not calculate the room's next pair.

### Acceptance checks still required

No deployment, build or game run was performed for this working-tree change. The maintainer should check:

- Each target, including FT1 and a completed FT10, with score updates between games and no new game after
  the target; accepting a Rematch after completion starts a fresh set.
- Per-game casual character selection, stage wishes, and reconnecting a persistent game on direct and relay
  paths. Run a real pair test with **0 mismatches** to prove both PCs still simulate identically.
- A community room with at least three players: no rotation between games, winner-stays uses the set winner,
  and everyone-in-turn moves the longer-seated player back once per set. An abandoned set has no set winner;
  winner-stays moves both back, while everyone-in-turn keeps its normal one-player rotation.
- Leaving during a game applies the existing casual game result; leaving between games stops the set with no
  extra set loss or ranked penalty. Earlier game records remain and ratings do not move.
- New/new, new/old and old/old clients, plus a new launcher on the old server. Mixed pairs play single games.
  Ranked best-of, character locks, leave/away treatment, rating and tournament sets must remain unchanged.

The repository's game-free regression tests cover server state and launcher plumbing with fakes. Network
integration, actual launcher layout in every language, real builds and the checks above require separate
maintainer validation under the project's normal test/deploy process.

## Simultaneous room tables

The rooms draft also adds `room_tables`: deploy the matching central lobby and launcher together. New launchers
offer tables only when the server advertises the feature, and clients lacking the capability cannot join a table
room, including through an invite. Existing classic and line rooms retain their compatibility. Tables add no
schema migration and disappear on a server restart, so drain every table and its unfinished set before restarting.

Room limits stay unchanged: a room of N players has at most `floor(N / 2)` simultaneous tables, with each player
reserved for one table. Each table owns its match, first-to score and countdown. Host pairing, ready checks,
availability and spectating must remain independent. Private-room passwords, invite codes, hidden status,
kicking and barred guesses remain room-wide protections. See [ONLINE.md](ONLINE.md#simultaneous-tables-120)
for protocol fields and the complete capacity discussion.

Capacity must be assessed before deployment. Four relayed tables at the typical 85 kbit/s per player need about
680 kbit/s received and 680 kbit/s forwarded, before overhead and spectators; the default 512 kbit/s ceiling gives
4096 kbit/s in each direction. These are estimates, not measurements. Retained rematch connections can increase
transient relay occupancy. `T5L_MAX_RELAYS` and `T5L_MAX_RELAYS_PER_IP` still apply; four matches sharing one public
address can exceed the default per-IP limit of three. Four spectator streams can use four of `T5L_MAX_STREAMS`
and up to 8 MiB of compressed stream buffers at the default `T5L_SPECTATE_BUFFER_KB`, before viewer/output queues.

Run the offline `lobby/tests/test_room_tables_*.py` regressions and in-memory `lobby/tools/room_tables_session.py`
in the maintainer's permitted test environment. Then verify concurrent ready checks, independent FT scores,
host pairing, sit-out/return, leaving/disconnecting, password/code joins, kicking/barred guesses and switching
table spectators with real clients. Exercise direct and forced-relay paths, relay exhaustion and private-room
changes while another table keeps playing. Every real playing pair must finish with **0 mismatches**;
spectators must reproduce the selected session. Offline stubs do not establish build success, real network
behavior, translated launcher layout or production load capacity.
