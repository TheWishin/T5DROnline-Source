#!/usr/bin/env python3
"""Exercise simultaneous room tables with in-memory stub clients only.

    python lobby/tools/room_tables_session.py

No listener, socket, server process, game process or output file is created. The
normal room, ready, result, set and watch handlers run against a memory database;
only connection negotiation is replaced by a deterministic transport stub. This
checks orchestration, not game synchronization, NAT, relay traffic or the UI.
"""
import asyncio
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto  # noqa: E402
from t5lobby.server.config import Config  # noqa: E402
from t5lobby.server.lobby import LobbyServer, Player  # noqa: E402


CAPS = {"private_rooms", "room_tables", "sets", "casual_sets", "spectate"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class StubClient:
    """A handler client whose server-to-client messages stay in memory."""
    def __init__(self, server, name, number, caps=None):
        self.server = server
        self.caps = set(CAPS if caps is None else caps)
        self.build_id = "room-tables-stub"
        self.release = "1.2.0"
        self.ip = self.akey = f"192.0.2.{number}"
        self.closed = False
        self.pending = 0
        self.events = []
        self.player = Player(self, name, True)
        self.player.spec_allow = True
        server.players[self.player.id] = self.player
        server.by_name[name.lower()] = self.player

    def send(self, message):
        self.events.append(copy.deepcopy(message))

    async def request(self, kind, **message):
        response = await getattr(self.server, "h_" + kind)(self, message)
        if response is not None:
            self.send(response)
        return response

    async def ready(self, accept=True):
        match = self.player.match
        require(match is not None, "stub client has no ready check")
        return await self.request("ready", match=match.id, accept=accept)

    async def report(self, winner):
        match = self.player.match
        require(match is not None, "stub client has no match to report")
        score = [3, 0] if winner == 0 else [0, 3]
        return await self.request("result", match=match.id, winner=winner, score=score,
                                  source="game", frames=3600, desync=0,
                                  hash="0123456789abcdef0123456789abcdef")


def stub_transport(server, match):
    """Finish only the transport negotiation; normal match start/result code runs."""
    match.results = [{"rtt": 1.0, "jitter": 0.0, "peer": ["192.0.2.1", 10001]},
                     {"rtt": 1.0, "jitter": 0.0, "peer": ["192.0.2.2", 10002]}]
    server._start_match(match, "direct")


def start_table(server, table):
    require(table.next_timer is not None, "table has no scheduled pair")
    table.next_timer.cancel()
    server._room_table_next(table)
    require(table.match is not None, "scheduled table did not start a match")
    return table.match


async def finish_game(clients, match, winner):
    """Both stub players submit their own result through the public handler."""
    by_id = {client.player.id: client for client in clients}
    for player in match.players:
        await by_id[player.id].report(winner)
    require(match.state == "done", "two agreeing result reports did not finish the game")
    require(match.final["status"] == "confirmed", "stub result was not confirmed")


async def run_session():
    cfg = Config(db=":memory:", room_max_size=8, room_next_seconds=60.0,
                 set_next_seconds=60.0, min_match_seconds=0.0, old_stages=False,
                 status_port=0, relays="", name_blocklist="")
    server = LobbyServer(cfg)
    # Never call start(): replacing this method also prevents NAT setup for each
    # automatic next game. _start_match still creates the real match payload.
    server._start_nat = lambda match: stub_transport(server, match)
    clients = [StubClient(server, name, number) for number, name in enumerate(
        ("Host", "Second", "Third", "Fourth", "Watcher"), 1)]
    host, second, third, fourth, watcher = clients
    legacy = StubClient(server, "Legacy", 6, CAPS - {"room_tables"})
    outsider = StubClient(server, "Outsider", 7)
    checks = []
    room = None
    try:
        created = await host.request("room_create", name="Stub tables", size=6,
                                     mode="tables", first_to=2, private="code")
        room = host.player.room
        require(room.mode == "tables" and len(room.tables) == 3,
                "room did not retain bounded simultaneous table metadata")
        code = created["code"]
        for client in clients[1:]:
            await client.request("room_join", code=code)
        try:
            await legacy.request("room_join", code=code)
        except proto.LobbyError as error:
            require("update" in error.msg, "old client refusal has no update guidance")
        else:
            raise AssertionError("an old launcher entered a simultaneous table room")
        require(legacy.player.room is None, "refused old client became a room member")
        checks.append("private invite-code admission and clear old-client refusal")

        await watcher.request("room_line", **{"in": False})
        await host.request("room_pair", table=1, players=[host.player.id, third.player.id])
        await host.request("room_pair", table=2, players=[second.player.id, fourth.player.id])
        first, other = room.tables[:2]
        match1, match2 = start_table(server, first), start_table(server, other)
        require(match1 is not match2 and match1.set is not match2.set,
                "tables share a match or first-to set")
        require(match1.key != match2.key and match1.tokens != match2.tokens,
                "tables share connection credentials")
        require({p.id for p in match1.players} == {host.player.id, third.player.id},
                "host's first table pairing was ignored")
        require({p.id for p in match2.players} == {second.player.id, fourth.player.id},
                "host's second table pairing was ignored")
        for client in clients[:4]:
            await client.ready()
        require(match1.state == match2.state == "playing", "both matches are not live together")
        require(watcher.player.match is None and watcher.player not in room.line,
                "an away member was paired")
        checks.append("host pairs, two concurrent independent matches and away exclusion")

        watching = await watcher.request("watch", room=room.id, table=2)
        require(watching["match"] == match2.id and watching["table"] == 2,
                "table-specific watch selected the wrong match")
        try:
            await outsider.request("watch", room=room.id, table=1)
        except proto.LobbyError:
            pass
        else:
            raise AssertionError("a nonmember watched a private room table")
        require(outsider.player.watching is None, "private stream leaked to an outsider")
        streamer = server.streams[watching["stream"]].streamer
        await watcher.request("unwatch")
        await next(client for client in clients if client.player is streamer).request(
            "spec_fail", stream=watching["stream"], why="stub session stopped")
        checks.append("specific-table spectating and private membership boundary")

        first_set, other_set = match1.set, match2.set
        await finish_game(clients, match1, 0)
        require(first_set.score() == [1, 0] and first_set.state == "active",
                "first table did not retain its unfinished FT2 set")
        require(other.match is match2 and match2.state == "playing" and other_set.score() == [0, 0],
                "a result on one table changed the other table")
        require(first.set is first_set and first.match is None,
                "the first-to countdown lost table ownership")
        first_set.next_timer.cancel()
        server._set_next(first_set)
        next_match = first.match
        require(next_match is not None and next_match.set is first_set and next_match.table is first,
                "automatic next game lost its table or set")
        require(next_match.state == "playing", "stub transport did not start the automatic next game")
        await finish_game(clients, next_match, 0)
        require(first_set.state == "ended" and first_set.score() == [2, 0],
                "first table's FT2 set did not conclude")
        require(other.match is match2 and other_set.state == "active" and other_set.score() == [0, 0],
                "finishing one table's set interrupted its neighbour")
        await finish_game(clients, match2, 1)
        require(other_set.state == "active" and other_set.score() == [0, 1],
                "second table's independent score was lost")
        checks.append("independent FT2 scoring, automatic next game and set completion")

        # Declining one table's next ready check makes only that player away.
        again = start_table(server, first)
        declining = next(client for client in clients if client.player is again.players[0])
        await declining.ready(False)
        require(declining.player not in room.line, "declining player was immediately paired again")
        require(other.set is other_set and other_set.state == "active",
                "declining one ready check ended another table's set")
        require(any(event.get("code") == "room_away" for event in declining.events),
                "declining player was not told they are away")
        checks.append("ready decline isolates the affected table")

        summary = {"ok": True, "checks": checks,
                   "confirmed_games": sum(event.get("t") == "match_result"
                                          for client in clients for event in client.events) // 2,
                   "tables": len(room.tables), "members": len(room.members),
                   "network": "none", "game_processes": 0}
        # Leave between games: the unfinished neighbouring set ends locally,
        # then every room member and each per-table countdown is removed.
        for client in clients:
            if client.player.room is room:
                await client.request("room_leave")
        require(room.id not in server.rooms, "empty room was not closed")
        require(all(table.next_timer is None for table in room.tables),
                "closing the room leaked a table countdown")
        require(not server.matches and not server.streams, "session leaked an active match or stream")
        require(all(client.player.room is None and client.player.match is None
                    for client in clients), "session leaked room or match membership")
        checks.append("leave and empty-room cleanup")
        return summary
    finally:
        # A failed assertion must also leave no pending callback using a closed
        # database. Services were never started, so none need network shutdown.
        for match in list(server.matches.values()) + list(server.recent.values()):
            server._cancel_timers(match)
            if match.set is not None:
                server._close_set(match.set)
        for active_room in list(server.rooms.values()):
            server._room_close(active_room)
        for stream in list(server.streams.values()):
            server._spec_end(stream, "stopped", flush=False)
        server.store.close()


def main():
    print(json.dumps(asyncio.run(run_session()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
