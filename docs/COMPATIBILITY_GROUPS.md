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

## Declared crossplay group (1.2.1: US + European Online)

The operator-approved groups above stay as they are (`T5L_COMPAT_GROUPS`, build ID lists). 1.2.1 adds a second way into
a group that needs no per-release server edit: the release **declares** it.

* **Declaration.** `tools/build_game.py crossplay_group()` is `t5x-` plus 12 hex digits of what the simulation depends
  on and every crossplay program shares: the code version, the pinned ps3recomp and its patch series, the
  live-immediates table, `CMakeLists.txt`, and in a release the prebuilt runtime and the game-DLL sources. It leaves out
  what differs by program (the code end, the PGO profile only the US program has), so the US build and the European
  Online build of one release get the same group and another version gets a different one. The build stamp
  (`build/t5dr_build.json`: `edition` = `US` / `EU-Online`, `crossplay`) and the release's `release.json`
  (`crossplay.group`, `crossplay.editions`) carry it.
* **Client.** `BuildInfo.from_out_dir` reads the stamp; the hello's `build` then has `crossplay` and `edition` next to
  `elf`, `code`, `net` (absent for a build that declares nothing, so older launchers and servers see the 1.2.0 hello).
  The `compat_groups` capability is the one the 1.2.0 launcher already announces; no new capability.
* **Server** (`compatibility.CrossplayPolicy`). The declaration counts only when all of these hold: the client announced
  `compat_groups`; the program (`elf`) is in `CROSSPLAY_EDITIONS` (the US program and the two European Online
  programs; EU v01.00 is another game and is not there); the declaration is well formed (`t5x-` + 12 lowercase hex); a
  declared edition is the program's own; the wire version is a positive integer. The accepted group is
  `<declared>-n<net>`, so two equal groups also share the wire version. A client cannot name the group any other way, and
  `T5L_COMPAT_GROUPS` still wins where it applies. As before, the build ID in a hello is recomputed from `elf`, `code`
  and `net`; the declaration is as trustworthy as those fields (a modified client could lie in all of them) and the
  netplay hash check still voids a session that diverges.
* **Operator.** `T5L_CROSSPLAY` (default `1`) switches the declared group off with `0`: exact build IDs only, as 1.2.0.
  `T5L_CROSSPLAY_GROUPS=t5x-...,t5x-...` accepts only those declared groups (empty = any well-formed declaration of a
  known program). `T5L_BUILDS`, if set, must list the build IDs of both editions; it is checked before any group.
  Two different releases never share a group: the lobby's release gating stays as it was.
* **Scope.** Same as the operator groups: Quick and Ranked queues, challenges, casual invites, rooms (every member is
  checked against the joiner), match creation and the client's own check of `match_start`. Exact matching remains for
  older launchers (no capability or no declaration), other groups, other wire versions, unknown programs, EU v01.00.
  `T5_NET_BUILD` is the host's build ID for both games, so the netplay HELLO check passes.
* **Proof.** Pair tests (US host/EU joiner, EU host/US joiner, rollback and lockstep, 0 mismatching frames) are
  recorded in `docs/EU.md`; this change is covered by `lobby/tests/test_crossplay_group.py` (policy, forged fields,
  queue/challenge/room pairing, refusal of other groups, nets and programs, old clients, a real server with two
  clients).
