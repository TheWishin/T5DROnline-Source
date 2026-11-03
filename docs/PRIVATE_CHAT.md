# Private chat, personal mutes and launcher protocol (1.2.0)

Private messages use **server relay, with no ordinary private-message transcript
on the server**. The optional `private_chat` capability and welcome feature gate
the protocol. `T5L_PRIVATE_CHAT=0` disables it; older clients receive no
private-message events. This does not change game simulation or match messages.

The client opens its own private conversation view from a player list or profile,
keeps a bounded transcript in memory, and marks unread conversations. Delivery is
online only: there is no offline queue, history download or message recovery. An
accepted send returns `private_sent.message` for the sender's own view; only the
recipient receives `private_message`. An acknowledgement means queued to the
online connection, not read by the player. Closing the client loses its transcript.
Use the server's existing TLS settings; this is not end-to-end encryption.

## Mute, block and server-wide moderation

**Mute** means "hide this player's chat and stop their mentions and invites for me."
It covers lobby chat, the same chat shown in rooms and private messages, without
leaving a match, ending a friendship or preventing matchmaking. The launcher offers
the action on player rows, chat lines, profiles and room members, and one muted-player
list provides Unmute. A mute is one-way: it changes what the muting player receives.

**Block** prevents the pair from private messaging and being matched together,
ends their friendship and can leave a running fight/set under the ranked rules.
Account blocks retain their existing persistence; guest blocks retain their existing
session lifetime. A block in either direction prevents private delivery.

Personal mutes are separate from blocks. For accounts, the server stores the mute
list and restores it on login/resume. For guests, the launcher keeps its list locally
and reapplies it on login; it is not a durable server account preference. Server
mute lists use `T5L_MAX_BLOCKS` (default 200), independently of the block-list limit.
The bundled launcher keeps at most 200 local guest names, even if the server sets
a different limit. Muting an online target can use its player id; the named form
and muted-player list also
allow preferences to be managed after a target goes offline.
Account targets use their stable server account identity. Guests have only their
case-insensitive name: muting a guest name also mutes a later guest using that name,
and a guest changing names cannot be identified as the same person by this feature.
The sender sees the same unavailable response for an offline, incompatible,
blocked or muted recipient, without learning which preference caused it.

An administrator's server-wide mute is a different control: it stops the account
from sending chat to anyone. Every lobby/room and private send checks it on the
server. Changing launcher, omitting capability flags, reconnecting or using an old
client does not bypass an active mute for that account. A new launcher shows an
active mute on login/resume from `login_ok.chat_moderation`. A mute imposed while
already connected takes effect on the account's next send. The error says `Chat is
muted for this account.` and supplies `muted_until`, so launchers can show the
deadline. See [Chat filter](CHAT_FILTER.md) for `t5lobby-admin mute`, `unmute` and
counts. This guarantee identifies accounts, not people: the server cannot reliably
link an unrelated account or guest identity to the muted account. It does not
silence every account sharing a network address.

## Message and request limits

The relay sanitizes text to 200 printable characters. The shared server
[chat filter](CHAT_FILTER.md) checks both submitted and sanitized text before
delivery; using private messages cannot skip an enabled filter.
Sends are limited by account (guests: session) to 1/second after a burst of 5,
by address to 2/second after 10, by recipient to 5/second after 10, and globally
to 20/second after 40. The sender, address and global budgets are checked in that
order, stopping at the first exhausted budget. Attempts refused later by recipient,
mute or text checks have already consumed all three budgets. Normal connection
request and output-queue limits still apply.
Reports allow 2 immediately, then 1/minute per account/session; the address permits
4, then 1/30 seconds. Mute changes use the existing state-change budget.
Buckets are periodically pruned.

## Explicit reports are the only content retained

The Report action sends **only 1-5 lines selected by the reporting player**, plus
their optional reason, to the moderator inbox. The server never uploads the rest
of the conversation. Each relayed line has an HMAC receipt covering its sender,
recipient, text, time and id. The server checks that the reporter was a participant,
that all selected lines belong to one conversation, and that each line is genuine
and distinct. It stores only the chosen lines, without their receipt, and the
reporter's name/account, peer name, report time and reason in `private_reports`.
Selected context may be incomplete; moderators must not treat a report as a full
transcript or proof of everything said in a conversation.

Receipts expire after 24 hours and the secret is process memory only. A server
restart invalidates earlier receipts; a fresh player session also cannot claim
lines addressed to its previous player id. The client must show a report failure
instead of claiming it reached moderators. Unreported text is never put in the
database, server diagnostic events, status endpoint or server logs by this feature.

Moderators with access to the server database review reports locally:

```console
python -m t5lobby.server.admin --db PATH private-reports --limit 20
python -m t5lobby.server.admin --db PATH private-reports --json
python -m t5lobby.server.admin --db PATH private-reports --delete REPORT_ID
```

These commands are instructions for the owner; they were not run in this working
copy. The inbox defaults to at most 1000 reports (`T5L_MAX_PRIVATE_REPORTS`), dropping
the oldest when full. Reports older than 30 days (`T5L_PRIVATE_REPORT_DAYS`) are
pruned on report insertion and hourly server upkeep. Retention/deletion does not
erase existing database backups or the moderator's exported copies. The owner
must assign moderators, decide operational response and backup retention, and
tell players that submitting selected lines is consent to moderator storage.

## Wire reference for the new launcher

Clients announce optional capabilities in `hello.caps` and use the corresponding
entries in both `welcome.caps` and `welcome.features` before sending a new request.
`private_chat` enables private messages/reports. `mutes` enables unified personal
mute requests and the private `login_ok.mutes` and `login_ok.chat_moderation`
fields. Neither is required to
connect or use existing lobby chat. Old clients receive no private-message events;
extra mute fields are gated on `mutes`. Server filter and admin-mute enforcement
apply to old clients too.

| Request | Result |
| --- | --- |
| `private_message {player OR name, text}` | `private_sent {message}` to the requester; `private_message {id, from, to, text, time, receipt}` to the recipient |
| `mute {player OR name, muted: bool}` | `muted {name, muted, rows: [{name, guest, since}]}` |
| `mutes {}` | `mutes {rows: [{name, guest, since}], max}` |
| `private_mute {player OR name, muted: bool}` | Compatibility alias using `private_chat`; `private_muted {name, muted, rows}` changes the same personal mute preference |
| `private_report {lines: [original envelopes], reason?}` | `private_reported {id, lines: count}` |

Requests use the normal `t` discriminator and optional `rid` correlation; the table
shows the payload after `t`. `player` is a server player id and `name` is the player
name. `muted` defaults to `true` and, if supplied, must be a JSON boolean. `since`,
message `time` and timed `muted_until` are Unix seconds. Use returned rows as the
authoritative account list. `login_ok.mutes` has the same row shape as `mutes.rows`
and is sent only to the list's owner; another player's preferences do not belong
in public player rows or profiles.

On fresh login and resume, `login_ok.chat_moderation` is `{muted_until: number|null}`
for clients announcing `mutes`. The number is the active account-mute deadline;
`null` means guest, unmuted or expired. A permanent mute uses the existing server
sentinel `32503680000` (year 3000). The Python client exposes `chat_moderation` as
`{muted_until: number}` for an active mute and `{}` otherwise, and emits a
`chat_moderation` event when an active login/resume mute is received. This is a
login snapshot, not a live administrator push: server send checks remain the
authority after login, and their errors include the current `muted_until`.

For the Python client, use `mutes_ok()`, `mute(name, muted=True)`, `mutes()` and
`is_muted(name)`. The client exposes current `mute_rows` and emits a `mutes` event
when they change. Guest persistence belongs to the launcher: the bundled launcher
stores name arrays under `guest_mutes[server_key]` in its existing `online.json`
settings, passes that server's names as `Client(..., guest_mutes=names)`, and saves
updates only when `client.me.guest` is true. The client itself does not write
settings. It reapplies saved names on guest login/resume when `mutes` is negotiated.
The local guest list remains authoritative for local hiding even if an individual
replay request is refused or rate limited; a server's partial replay list must not
erase local preferences. Local event filtering also protects guests on an old
server. Accounts require the
new server for durable personal mutes; do not silently claim server persistence on
an older server. These settings contain preferences, never conversation text.

`from` and `to` contain only `{id, name, guest}`. Existing `block`/`unblock` requests
are reused. A report does not require the peer to remain online. Generic unavailable
errors avoid confirming delivery preferences. Five full-length Unicode envelopes
fit within the existing 8192-byte request cap. A report reason is sanitized to
200 printable characters. Preserve the original envelope and receipt for reports.

The launcher keeps at most 32 conversations and 100 lines per conversation in
memory. Append `private_sent.message` for the sender only after acceptance; do not
mark an unacknowledged send as delivered. Reading a conversation clears its unread
count; incoming messages to other conversations increment their markers. Muted
incoming messages create neither transcript lines nor unread, mention or invite
alerts. Previously received incoming lines are hidden while muted, with original
envelopes and receipts retained in bounded session memory. Unmute restores their
visibility so they can be selected explicitly for a report; hidden lines are never
attached automatically. Mute is not deletion.

## What a store would add later

A future owner decision to store ordinary messages could enable offline delivery,
history on another PC, recovery after client/server restart, longer-lived reporting
receipts, and delivery/read synchronization. It also requires a new explicit
retention/deletion policy, access controls, encryption/key handling, account deletion
and export rules, backup policy, quotas, database migrations, and player-facing
consent/privacy text. None of those features or a server transcript is enabled by
this relay implementation.

## Verification still needed

`lobby/tests/test_private_chat_server.py` uses fake connections and an in-memory
database, with no listener or game. It covers capability gates, sender/recipient
routing, absence of unreported storage, block/mute, limits, authenticated selected
reports, forged/expired receipts, wire size and inbox retention/capacity. New mute
and filter regressions under `lobby/tests` cover shared policy and persistence.
The implementation report records which checks could run in this mirror.

The maintainer must run the offline regressions in an environment with Python,
then check two launchers against a local server for list/profile/room actions,
unread state, blocks, personal mutes, reconnect, timed admin mutes, old-client
compatibility and moderator review before release. No build, game or server was
started for these edits. No game pair test is needed for text policy itself; no
simulation or memory-address change is intended.
