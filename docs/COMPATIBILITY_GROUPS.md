# Build compatibility groups (1.2.0)

The server and launcher can match different complete build IDs only when the
operator explicitly approves them in `T5L_COMPAT_GROUPS`, and both launchers
announce `compat_groups`. The default is empty: exact build IDs as before.
Neither release labels, region, a client-supplied group nor title IDs grant
compatibility. The server recomputes each build ID from its ELF hash, code ID
and netplay version, then looks up the approved group for that wire version.
`T5L_BUILDS` admission rules still apply.

The JSON shape is `{ "approved-group": { "net": 4, "builds": ["<16 lowercase hex build ID>", "<another ID>"] } }`.
These are placeholders, not usable IDs. There is intentionally no shipped EU/US
group. Invalid JSON, duplicate build memberships or invalid IDs stop server
initialization instead of broadening matchmaking.

Groups apply to quick/ranked queues, challenges, casual invites and rooms. Room
joins check every current member, so an old exact-build client cannot be mixed
with a different build through a newer host. Match creation checks compatibility
again; new clients validate the server's accepted group before starting or
continuing a match. Old launchers/servers retain exact matching. Session resumes
still require the original exact build and accepted group. Tournaments and
spectating retain exact-build checks: no stream or persistent tournament format
is widened by this change.

Lobby player rows show `[US]` or `[EU]`, derived from program fingerprints
already recorded in `docs/EU.md`; these identify the game edition's region,
not the player's location. Region is informational and never a match key.

EU game support is outside this change. EU v01.00 is already proven incompatible
by different fighter data and must never be grouped with US. EU Online v02.00 is
unsupported; identical fighter data alone does not prove simulation, protocol,
state layout or rollback compatibility. Before approving any cross-build pair,
the maintainer must port and verify all game hooks and run real pair tests at
**0 mismatches**, including rollback, rematches and stage/character coverage.

Added offline tests: `lobby/tests/test_compatibility_groups.py` covers approved
matching, default-off/unknown/wrong-wire rejection, legacy clients, launcher
validation, region labels and mixed room safety. No build, test, game or server
was run for this change; these tests still need execution in an authorized check.
