# Screen side: real P1 / P2 choice and the mirrored picture

For the 1.2.0 player reports, prefer **P1 (left)** or **P2 (right)** in the Online tab's
**Challenges, invites, rooms** row when the player wants the real game side without reversed
costumes, stage lettering or handedness. Set the separate **Screen side** preference to
**As dealt** for an unmirrored picture. A real side wish changes which player occupies the game's P1 / P2 slot;
it does not reflect the camera image. It chooses the starting side, not a promise to remain
on that side after the fighters move past one another.

The integrated 1.2.0 launcher offers **As dealt / Always left / Always right** through
`screen_side` and `T5_SCREEN_SIDE=dealt/left/right`. Always left mirrors actual P2; Always
right mirrors actual P1. The old `always_left` checkbox migrates to the new preference; it
is only a legacy fallback when `T5_SCREEN_SIDE` is absent. Neither presentation choice changes
the server-assigned real slot. See [SCREEN_SIDE_120.md](SCREEN_SIDE_120.md).

## This already exists in the mirror

The 1.1.5 P1 / P2 / any work is implemented end to end, rather than a plan still needing a
new game hook. No additional implementation or second capability is introduced here:

| Part | Existing implementation |
|---|---|
| Advertise support | `lobby/t5lobby/server/lobby.py`: server feature `casual_choice`; welcome includes `casual.stages` |
| Save and send a wish | `lobby/t5lobby/tk_casual.py`: `CasualUI.on_change` saves `casual_side` in online.json; `new_client` supplies it before login |
| Feature gate | `lobby/t5lobby/client.py`: `casual_ok`, `set_casual_prefs`, `_casual_after_login`; send `casual_prefs {side: 0 / 1 / null, stage}` only to a server advertising `casual_choice` |
| Pick the actual slots | `lobby/t5lobby/server/casual.py`: `_casual_sides` orders `(P1, P2)` from the wishes |
| Use the chosen order | `server/lobby.py`: accepted challenges and casual invites call `_casual_sides`; `server/rooms.py` does so for casual room matches |
| Start the game | `lobby/t5lobby/handover.py`: the ticket's host/join role becomes `T5_NET_MODE`; `src/netplay/netplay_core.cpp` maps host to slot 0 (P1), join to slot 1 (P2) |
| Swap on a rematch | `server/lobby.py` reorders the players and disallows `keep` when swapping; a new netplay session supplies the new role |

This is the existing **server feature gate**, not a new hello cap. Older launchers have no
wish and count as any; a new launcher connected to an older server hides the choice row.
Both games already accept their assigned role. There is no reason to add a guest memory
address or change the netplay protocol for this feature. The server's actual deployed
version and the player's launcher were not checked here; source availability does not
prove a public server advertises the feature. See [the existing behavior](ONLINE.md#sides-and-stages-by-choice)
and [the 1.1.5 deployment notes](DEPLOY_1.1.5.md).

## Which wishes can be granted

The server chooses once, before either game starts the session, and sends the same ordered
players to both launchers. Each PC must never decide its slot independently.

| Player A wishes | Player B wishes | Actual assignment |
|---|---|---|
| P1 | P2 | A=P1, B=P2 |
| P2 | P1 | B=P1, A=P2 |
| P1 or P2 | Any | A gets the requested side |
| Any | P1 or P2 | B gets the requested side |
| P1 | P1 | Server coin: one gets P1, the other P2 |
| P2 | P2 | Server coin: one gets P2, the other P1 |
| Any | Any | Existing order: challenger, inviter or room's first player is P1 |

Two players cannot both occupy P1, or both occupy P2, in the same shared simulation. The
existing same-side coin is the explicit compromise; it is unrelated to ping. The launcher
reports when the coin denied a wish. An optional personal mirror can still put the player
assigned P2 on the left of their own display, at the cost of reversing the scene. Granting
both identical wishes without that reflection would need a new local presentation method;
server ordering alone cannot do it. No alternate camera or game address sufficient for
that method has been established by this work. A claim of Tekken 7 / 8 parity is therefore
outside this plan.

The wishes apply to accepted challenges, friends' casual invites, casual rooms and their
rematches. Quick, Ranked, ranked rooms and tournament sets keep their existing side rules.
The mirroring option is restricted to casual matches by choice and offline Versus; it is
not a workaround for changing ranked or tournament slots.

## Keep identities and simulation separate from the picture

Real side choice deliberately changes the session's player ordering on **both** PCs. Names,
characters, costumes, health rules, scores and winners must follow that ordering together.
Accounts remain the same accounts when a player changes from P1 to P2. The existing match
tickets and P1 / P2 result fields provide the mapping; do not swap only names, pad ports or
the displayed result. A running netplay session keeps its slot, so **Rematch: swap sides**
must continue to create a new session rather than mutate the live slot. Community room
rotation must follow its participant line, independently of which participant got P1.

Mirroring is a separate local presentation preference. Patch 0086 changes rendered scene
and HUD placement; `always_left_input` swaps the local player's horizontal controls before
input exchange to match the picture. Both PCs therefore receive the same game-side inputs.
Do not use HUD placement to infer actual ownership, winner or account identity. Renderer
fixes must not alter fighter positions, camera/game simulation memory or the input exchange.

Replays store confirmed inputs in actual P1 / P2 order, session slot, fight setup and HUD
names (`src/netplay/replay.h`). Live spectators consume that same replay stream. Playback
does not activate the local always-left option (`al::active` rejects `replaying`). Keep this
behavior: spectators and replays show the recorded identities and simulation, irrespective
of either player's personal mirror setting. A swapped rematch starts its new session/stream
with the new ordering, never reinterpret the previous session's inputs.

## 1.2.0 acceptance work for the maintainer

No build, game, lobby server or tests were run for this document. The existing automated
coverage to inspect/run in the maintainer's authorized environment is
`lobby/tests/test_casual.py`, `lobby/tests/test_tk_casual.py` and
`lobby/tests/test_sides.py`; those suites include server/socket tests and are not executed
as part of this source-only task. `docs/ONLINE.md` also describes the existing
`net_casual_choice` real-game scenario. This document changes no launcher text or catalog.

1. With two compatible launchers, confirm the server advertises `casual_choice` and the
   side row appears. Choose A=P2, B=P1 with mirroring off, then challenge. Confirm the
   match cards, game roles, actual starting sides, fighter/name ownership and winner agree
   on both PCs. Repeat via a casual friend invite and a casual room.
2. Test P1/any, P2/any, opposite wishes, both P1, both P2 and any/any. For equal wishes,
   check the assigned complementary slots and the losing wish's coin explanation; neither
   side may locally override the assignment. Repeat across logins to check saved wishes.
3. Ask for **Rematch: swap sides** from either player. Confirm a new netplay session, the
   opposite starting slots and correct names, score and result ownership. Check a community
   room's winner/queue rotation follows people after a side swap. Check Ranked, Quick and
   tournament assignments ignore casual wishes and the mirror preference.
4. For the HUD fix, use distinct names with both short and long strings, spaces and repeated
   letters. On P2 only, enable mirroring; P1 leaves it off. Observe round intros, moving and
   rotating cameras, normal fighting, slow-motion KO replay, win pose and the next round.
   Names must remain readable and stable; both life bars must drain/fill on the correct
   owners, including a nearly empty bar. Check round markers, portraits, timer and clipped
   fills. Repeat with both players' setting on, off, and swapped roles, then offline Versus.
5. Confirm costume/stage lettering stays normal with real side choice and mirroring off;
   with mirroring on, the known scene reflection remains. Check the recorded replay and
   a spectator have the actual P1 / P2 names and matching results through the swapped
   rematch, without inheriting either player's mirror preference.
6. Every paired game in this matrix must finish with **0 mismatching frames** (both PCs),
   including opposite mirror settings. Source inspection cannot prove final visual output,
   runtime patch behavior, deployed feature availability or deterministic paired execution.
