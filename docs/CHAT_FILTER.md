# Server chat filter (1.2.0)

The lobby server checks chat and new names against a separate, maintainer-reviewed
hate-term list. A blocked chat message is never broadcast. The sender receives
`Message blocked: hate terms are not allowed.` as a normal protocol error; other
players receive nothing. This works with older clients without a protocol update.
Updated launchers translate the notices in every existing catalog language.

## Coverage and existing names

The `chat` request and `h_chat` handler serve the lobby, including players in rooms
or matches. There is no separate room-chat channel: the room view uses this same
chat path. Private messages use the relay-only `private_message` handler described
in [Private chat](PRIVATE_CHAT.md). Both handlers check the same server policy
before delivering text. The submitted text and the sanitized, length-limited text
are checked, so truncation or control-character removal cannot expose an unchecked
term. A client capability, room membership or an extra scope field cannot skip
these checks. Game input and relay packets are not interpreted as chat.

New account registrations, guest names and new room names are checked server-side.
Existing account names are neither changed nor refused at login because of this list.
Admins can report them with `flagged-names`; the report is local admin output and is
not sent to players. Rooms already created are not renamed on a term-list reload.
The older `T5L_NAME_BLOCKLIST` and reserved-name checks remain separate policies.

## Settings and deployment

| Setting | Default | Purpose |
|---|---|---|
| `T5L_CHAT_FILTER` | `1` | Set to `0` to disable hate-term matching |
| `T5L_CHAT_FILTER_PATH` | `t5lobby/server/data/chat_filter_terms.json` beside the installed server code | UTF-8 JSON data file, resolved independently of the working directory for the packaged default |

Deploy the server code and its `server/data` directory together. The starter list is
server data, separate from catalogs, and is not part of the chat protocol. For a local
policy, copy the reviewed JSON file outside the installed code and set an absolute
`T5L_CHAT_FILTER_PATH`, for example `/etc/t5lobby/chat-filter/chat_filter_terms.json`. The service
user needs read permission; its ordinary account must not need write permission.
Environment changes need a server restart. Changes to the contents of the configured
term file are loaded on the next text check after its file metadata changes, without
restarting the lobby.

Source installations, the server Docker image, and the Linux/macOS server installers
include the default server data file. Player release archives exclude the term list.
Someone using **Host for friends** from a player archive must provide a reviewed
server-only file through `T5L_CHAT_FILTER_PATH`, or explicitly opt out with
`T5L_CHAT_FILTER=0`; the enabled default cannot start there without its data file.
The launcher reports `Cannot load the chat filter. Check T5L_CHAT_FILTER_PATH.`;
that startup notice is translated in every catalog.
The maintainer should review this hosting/distribution choice before release.

For Docker, mount the directory containing the reviewed list read-only into the
container, and point `T5L_CHAT_FILTER_PATH` at the file inside that directory. Mount
the directory rather than a single file when publishing updates by atomic rename.
The compose example uses `./chat-filter:/chat-filter:ro` and
`T5L_CHAT_FILTER_PATH=/chat-filter/chat_filter_terms.json`. Keep the term data out of
launcher/client artifacts.

Publish term-list changes by replacing the complete UTF-8 JSON file atomically.
Malformed or unreadable updates retain the last valid policy. An enabled filter with
an invalid initial file refuses startup rather than silently starting without a list.
Keep the previous reviewed file available for rollback. Check the operator diagnostics
and verify the newly deployed policy before declaring the update complete.

## Policy and false positives

The starter data covers English, German, Spanish, French, Brazilian Portuguese,
Japanese and Korean with a deliberately small selection of unambiguous hate terms.
It is not a general profanity list. Each entry carries language metadata for review;
matching is multilingual for every player, regardless of their selected UI language.

The UTF-8 JSON document has `version: 1`, a `terms` array and optional review metadata.
Each term entry has a `term` string, `languages` tags and a `match` policy. Ordinary
Latin-script entries use `word`; explicit plural forms are separate entries. The
specific Japanese and Korean entries use `substring` so unspaced sentences and
attached particles do not bypass them. Review that broader matching mode separately
before applying it to any new entry.
Language tags and review notes are documentation; the matcher ignores extra metadata.
The loader accepts at most 256 terms, 64 characters per term and a 256 KiB file.
Terms must consist of letters; the matcher supplies the evasion variants.

The matcher normalizes case and accents, selected Unicode look-alikes and common
letter/number swaps, and checks limited spacing and repeated-letter evasions. The
ordinary `word` policy uses word boundaries rather than rejecting every longer word
that contains a listed term. Adjacent digits are allowed as name suffixes; they do
not protect a listed term from matching. The explicit Japanese/Korean `substring` exceptions
trade that boundary protection for coverage in writing without word spaces.
At most three spacing/punctuation characters may occur between matched letters;
letters and digits cannot simply be skipped. Natural doubled letters are preserved
as a minimum, so the country name Niger is not equated with the differently spelled
English slur. This also means a spelling with a required letter removed can evade
the policy; review that tradeoff before widening normalization.
Innocent-word regression cases are maintained in `lobby/tests/test_chatfilter_core.py`.
Normalization is intentionally limited: the filter is a moderation aid, not a promise
to recognize every spelling, language, or encoding trick.

This lexical policy also blocks quotations, discussion of the terms and reclaimed
uses. It cannot infer the speaker's identity or intent. The maintainer must review
that consequence along with cross-language false positives.

Before deploying, the maintainer should review every term with speakers of its listed
languages, including its everyday uses in the other supported languages. Review the
normalization examples and innocent-word cases together. Add an explicit regression
case for each accepted spelling or false positive when changing the policy. Spacing
normalization can join ordinary fragments across word boundaries, so review harmless
multiword phrases across all supported languages too. The starter omits French
entries that would also match the ordinary English phrase "you pin" and its plural;
French coverage retains the narrower racist terms. Do not
add ordinary swear words or ambiguous short fragments merely to increase coverage.

## Counts and manual mutes

Blocked text attempts by an authenticated account increment its durable aggregate count.
This stores no message text, matching term, or new chat transcript. Registration and
guest-name refusals have no existing account to charge, and guests have no durable
account count. The filter does not create an automatic ban or mute. Existing chat
rate limits still apply to blocked and muted senders.

Use the ordinary local `t5lobby-admin` wrapper with the server's database and environment:

```sh
t5lobby-admin chat-counts --limit 50
t5lobby-admin mute PlayerName --hours 2
t5lobby-admin unmute PlayerName
t5lobby-admin flagged-names
t5lobby-admin flagged-names --terms /etc/t5lobby/chat-filter/chat_filter_terms.json
```

`chat-counts` lists accounts with blocked attempts or an active mute. `mute` accepts
positive `--hours` or `--days`; without a duration it is permanent. Mutes affect chat
only and do not disconnect players or prevent matches. Lobby/room chat and private
messages check the database mute state on every send, including changes made while
connected. Its notice is `Chat is muted for this account.`; the error also supplies
`muted_until` as a Unix deadline for a timed mute. Disabling the lexical filter does
not disable this moderation check. Clients negotiating `mutes` also receive
`login_ok.chat_moderation: {muted_until: number|null}` on login/resume, allowing an
active mute notice before the first send; older clients still receive the normal
error when they attempt to send. This is separate from a player's personal mute,
which hides another player's messages only for that recipient. See the personal
mute and launcher protocol reference in [Private chat](PRIVATE_CHAT.md).
Existing-name scans use the requested term list even
when matching is disabled for player traffic; scanning does not modify account records.

## What remains to prove

This working-copy change was prepared without building, starting a game or
contacting a server. The implementation report records which offline tests were
run and their results. The maintainer must complete the existing lobby/catalog/deploy
checks in an approved environment and review the short term list and translations
before publishing it.

The feature takes effect only after deploying the updated lobby server and data file;
updating clients alone cannot enforce it. On a staging server, verify that a modified
or old client cannot broadcast blocked chat, recipients see no event, rate limits still
hold, existing names still log in, counts survive reconnects, mutes apply while connected,
and good/bad list updates behave as documented without a restart. Verify server packages
include the list and client packages exclude it. No simulation or memory-address change
is intended; this filter does not require a gameplay pair test to establish its text policy.
