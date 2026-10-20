"""Texts for tournaments (docs/TOURNAMENTS.md) in the player's language: round names, states, what a server event
means. No UI here: the Online tab (tk_tour.py) shows these strings. Every text goes through t5lobby.i18n (German in
i18n_de.py).

    round_label(info)        "Winners semi-final", "Losers round 2", "Grand final reset", "Final" ...
                             (info: a bracket set {bracket, round} plus the bracket's {format, rounds, losers_rounds})
    state_text(state)        "Sign-up", "Check-in", "Running", "Finished", "Cancelled"
    format_text(summary)     "Double elimination, best of 3"
    notice_text(ev)          a tour_notice event as one line
    call_end_text(ev)        a tour_call_end event as one line (or "" when nothing needs saying)
    set_line(row)            one bracket set as a line: "W1-2  Alice 2-1 Bob (done)"
"""
from .i18n import N_, stamp, t

STATE_TEXT = {"signup": N_("Sign-up"), "checkin": N_("Check-in"), "running": N_("Running"),
              "finished": N_("Finished"), "cancelled": N_("Cancelled")}
FORMAT_TEXT = {"single": N_("Single elimination"), "double": N_("Double elimination")}
SEEDING_TEXT = {"random": N_("Random seeding"), "rating": N_("Seeded by rating")}
# why a set was decided without the games, or why it waits
SET_REASON = {"bye": N_("bye"), "empty": N_("nobody"), "skipped": N_("not needed"), "no_show": N_("no-show"),
              "dq": N_("disqualified"), "forfeit": N_("forfeit"), "organizer": N_("decided by the organizer"),
              "disputed": N_("results disputed"), "hash_mismatch": N_("results disputed")}
DQ_TEXT = {"no_show": N_("did not show up"), "organizer": N_("disqualified by the organizer"),
           "withdrew": N_("withdrew")}


def tr(text):
    """t() for a text marked with N_() elsewhere (a table entry, a choice): the one dynamic lookup of tournaments."""
    return t(text)


def _word(table, key):
    return tr(table[key]) if key in table else str(key or "")


def seeding_text(seeding):
    return _word(SEEDING_TEXT, seeding or "random")


def state_text(state):
    return _word(STATE_TEXT, state)


def round_label(info):
    """The name of a set's round for a player: 'Winners semi-final', 'Losers round 2', 'Grand final' ..."""
    b, r = info.get("bracket"), int(info.get("round") or 1)
    k = int(info.get("rounds") or 1)
    double = info.get("format") == "double"
    if b == "GF":
        return t("Grand final") if r == 1 else t("Grand final reset")
    if b == "L":
        lr = int(info.get("losers_rounds") or 0)
        if r == lr:
            return t("Losers final")
        if r == lr - 1:
            return t("Losers semi-final")
        return t("Losers round {number}", number=r)
    if r == k:
        return t("Winners final") if double else t("Final")
    if r == k - 1:
        return t("Winners semi-final") if double else t("Semi-final")
    if r == k - 2 and not double:
        return t("Quarter-final")
    return t("Winners round {number}", number=r) if double else t("Round {number}", number=r)


def format_text(s):
    """'Double elimination, best of 3' (a tournament summary)."""
    return t("{format}, best of {best}", format=_word(FORMAT_TEXT, s.get("format")), best=s.get("best_of", 3))


def when_text(s):
    """When it starts or started: 'starts 18 Oct 21:05' / 'started 18 Oct 21:05' / 'ended ...'."""
    st = s.get("state")
    if st in ("finished", "cancelled") and s.get("ended"):
        return t("ended {time}", time=stamp(s["ended"]))
    if st == "running" and s.get("started"):
        return t("started {time}", time=stamp(s["started"]))
    return t("starts {time}", time=stamp(s.get("start") or 0))


def place_text(place):
    return t("place {place}", place=place) if place else ""


def dq_text(why):
    return _word(DQ_TEXT, why)


def set_reason_text(reason):
    return _word(SET_REASON, reason) if reason else ""


def notice_text(ev):
    """One line for a tour_notice event."""
    code = ev.get("code")
    name = (ev.get("tournament") or {}).get("name") or "?"
    if code == "started":
        return t("The tournament {name} has started: you are seed {seed} of {players}. Your sets are called here.",
                 name=name, seed=ev.get("seed"), players=ev.get("players"))
    if code == "checkin_open":
        return t("Check-in for {name} is open: check in on the Tournaments page, or you are not in the bracket.",
                 name=name)
    if code == "no_checkin":
        return t("You did not check in for {name}; the tournament started without you.", name=name)
    if code == "dq":
        return t("You are out of {name}: {why}.", name=name, why=dq_text(ev.get("reason")))
    if code == "eliminated":
        if ev.get("place"):
            return t("You are out of {name}: {place}.", name=name, place=place_text(ev.get("place")))
        return t("You are out of {name}.", name=name)
    if code == "finished":
        if ev.get("place") == 1:
            return t("You won the tournament {name}!", name=name)
        if ev.get("place"):
            return t("The tournament {name} is over: {champion} won it. You finished {place}.", name=name,
                     champion=ev.get("champion") or "?", place=place_text(ev.get("place")))
        return t("The tournament {name} is over: {champion} won it.", name=name, champion=ev.get("champion") or "?")
    if code == "cancelled":
        if ev.get("reason") == "not_enough":
            return t("The tournament {name} was cancelled: not enough players.", name=name)
        return t("The tournament {name} was cancelled by its organizer.", name=name)
    if code == "attention":
        return t("Tournament {name}: set {set} needs you ({why}). Report the result or reset it.", name=name,
                 set=ev.get("set") or "?", why=set_reason_text(ev.get("why")) or str(ev.get("why") or ""))
    return t("Tournament {name}: {code}", name=name, code=str(code))


def call_end_text(ev):
    """A tour_call_end event as a line for the player ('' when the next event says it anyway)."""
    r = ev.get("reason")
    if r == "no_show":
        return t("Your opponent did not show up: you win the set.")
    if r == "opponent_out":
        return t("Your opponent is out of the tournament: you win the set.")
    if r == "decided":
        return t("The organizer decided your tournament set.")
    if r == "reset":
        return t("The organizer reset your tournament set; it is called again.")
    if r == "attention":
        return t("Your tournament set has no result; the organizer decides how it goes on.")
    if r == "cancelled":
        return t("The tournament was cancelled.")
    return ""


def set_line(row, info):
    """One set as a line (lists, tests): 'Winners round 1: Alice 2-1 Bob (bye)'."""
    names = [n or "-" for n in row.get("p") or ["", ""]]
    sc = row.get("score")
    mid = f" {sc[0]}-{sc[1]} " if isinstance(sc, list) and len(sc) == 2 else " - "
    text = round_label(dict(info, **row)) + ": " + names[0] + mid + names[1]
    why = set_reason_text(row.get("reason")) or set_reason_text(row.get("why"))
    return text + (f" ({why})" if why else "")
