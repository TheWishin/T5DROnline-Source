"""The lobby client's tournament calls (docs/TOURNAMENTS.md), mixed into LobbyClient.

    c = LobbyClient(server, build, tournaments=True)     # announces the "tournaments" cap
    rows = c.tour_list()["rows"]                          # upcoming, running, finished
    t = c.tour_create("Friday Cup", fmt="double", set_wins=2, start=time.time() + 600, max_players=16,
                      checkin_minutes=10, seeding="rating")
    c.tour_join(t["id"]); c.tour_checkin(t["id"])
    ... event tour_call -> c.tour_accept(t["id"], ev["set"]["id"])     # "Your tournament set is ready"
    ... the set's games come as match_found / match_start / match_result like any best-of set
    c.tour_admin(t["id"], "report", set="W1-2", winner=0)             # the organizer

Events (pushed by the server, emitted as they come):

    tour_call       {tournament {id, name}, set {id, bracket, round, ...}, opponent, best_of, score, deadline,
                     accepted [you, opponent], replay}: a set is ready (again, after an accept or a reconnect)
    tour_call_end   {tournament, set, reason: started | no_show | reset | decided | cancelled | attention | opponent_out}
    tour_changed    {id, rev, state}: fetch the tournament again if it is on screen
    tour_notice     {code, tournament {id, name}, ...}: started, checkin_open, no_checkin, dq, eliminated, finished,
                     cancelled, attention (the organizer)
"""


class TourCalls:
    """Needs self._call(msg) (LobbyClient)."""

    def tour_list(self):
        """-> {"rows": [summary ...], "can_create": bool, "rated": bool}"""
        return self._call({"t": "tour_list"})

    def tour_get(self, tid):
        """The tournament with its entrants, bracket and standings."""
        return self._call({"t": "tour_get", "tournament": tid})["tournament"]

    def tour_create(self, name, fmt="single", set_wins=2, start=None, max_players=16, checkin_minutes=0,
                    seeding="random"):
        import time
        msg = {"t": "tour_create", "name": name, "format": fmt, "set_wins": int(set_wins),
               "start": float(start if start is not None else time.time() + 600), "max_players": int(max_players),
               "checkin_minutes": int(checkin_minutes), "seeding": seeding}
        return self._call(msg)["tournament"]

    def tour_join(self, tid):
        return self._call({"t": "tour_join", "tournament": tid})["tournament"]

    def tour_leave(self, tid):
        """Before the start: off the list. While it runs: withdraw (out of the tournament)."""
        return self._call({"t": "tour_leave", "tournament": tid})["tournament"]

    def tour_checkin(self, tid):
        return self._call({"t": "tour_checkin", "tournament": tid})["tournament"]

    def tour_accept(self, tid, set_id):
        """Accept a called set ("Your tournament set is ready")."""
        return self._call({"t": "tour_accept", "tournament": tid, "set": set_id})

    def tour_admin(self, tid, op, **kw):
        """The organizer: op = start | cancel | report (set, winner, score) | override (set, winner, score) |
        reset (set) | dq (player = name)."""
        msg = {"t": "tour_admin", "tournament": tid, "op": op}
        msg.update({k: v for k, v in kw.items() if v is not None})
        return self._call(msg)["tournament"]
