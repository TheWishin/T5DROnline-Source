# Deploying lobby 1.1.7: random sides in ranked (central server only)

1.1.7's lobby change for the server: the sides of ranked and quick matches are drawn by a coin
([RANKED.md "Sides: P1 and P2 by a coin"](RANKED.md#sides-p1-and-p2-by-a-coin-117)). It is **lobby code only**
and works with the launchers players have (1.1.6, and older ones of the same game build), so it can go out before
or without a client release. **Not rehearsed against the real servers**; nothing here was run on them.

The steps are the ones of [DEPLOY_1.1.5.md](DEPLOY_1.1.5.md) with `1.1.7` in place of `1.1.5` (archive name
`lobby_117.tgz`, folder `/opt/src/t5dr-lobby-1.1.7`): P1 build the archive from the commit to deploy, P2 unpack
and check it (`code ok`, the database line on a copy of the backup), C1 notice, C2 `drain --wait 900`, backup,
`install.sh --self-signed --firewall none`, C3 checks. The relay node stays as it is. Rollback: `install.sh` of
the folder the server runs now (`ls /opt/src`; production runs the 1.1.5 lobby, whose server code is identical
to v1.1.6's), no database step.

## What changes on the server

- Files: `lobby/t5lobby/server/casual.py`, `server/lobby.py`, `server/rooms.py` (if other 1.1.7 lobby changes
  ship in the same deploy, their notes add to this list).
- **Database: no change**, no new table or column, no migration. Matches and sets are stored as before (P1 / P2
  names, the winner's side).
- **Settings: none.** No new `T5L_*` value; the env file stays as it is.
- **Protocol: unchanged.** `match_found` / `match_reveal` / `match_start` carry `role` and `slot` as always; only
  who gets which differs. A ranked rematch whose coin swaps the sides comes with `keep: false` (a new netplay
  session), which every launcher handles (the same as a rematch after a closed game); after a ranked set the
  launchers since 1.1.5 start a new session anyway.
- The server log has one line per drawn match: `sides: <P1> P1, <P2> P2 (drawn, ranked queue)`.

## What players see

- In ranked and quick, the lower-ping player is no longer always P1: each set (each quick match) is a coin flip.
  Inside a ranked set the sides stay.
- A Rematch after a ranked set is a new set with its sides drawn again (it was a new connection before too).
- Casual challenges, invites and rooms keep the players' side wishes; tournaments keep the bracket's order.

## C3 additions

- `journalctl -u t5lobby --since "-30 min" --no-pager | grep "sides:"` after the first queue matches: lines
  with `(drawn, ranked queue)` / `(drawn, quick queue)`.
- With two launchers at hand (any 1.1.x of the current game build): a few ranked sets; over them both players
  get P1 and P2, and the set's winner gains rating whichever side they played.

## What was checked (on this PC, 127.0.0.1 only)

- `lobby/tests/test_sides.py` (the coin over 400 queue matches per mode, a set with the lower ping on P2 and its
  rating / record / history / profile, rematches, ranked rooms, the v1.1.6 client), the lobby test modules each in
  their own process, and the real-game e2e scenario `ranked_sides` with the v1.1.6 launcher code (RANKED.md
  "Sides").
