"""Operator-approved simulation compatibility; never inferred from a release or title.

The empty default keeps exact build matching. Groups contain complete build ids
whose game/netplay behaviour has been verified together. A client cannot choose
its group: the server derives it from the recomputed build id and wire version.

1.2.1 adds the declared crossplay group (CrossplayPolicy): a release declares in its
build stamp / release.json the group its editions share (tools/build_game.py
crossplay_group()), the launcher sends it in its hello with its edition, and the
server accepts it only for a program in CROSSPLAY_EDITIONS (the US program and the
two EU Online programs, on which US/EU and EU/EU pairs were proven at 0 mismatching
frames) and only with the compat_groups capability. Two players match when they
send the same accepted group; anything else still needs an exact build id.
"""
import json
import re

CAP = "compat_groups"
CROSSPLAY_RE = re.compile(r"t5x-[0-9a-f]{12}")
_ID = re.compile(r"[0-9a-f]{16}\Z")
_GROUP = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
REGIONS = {
    "be80165b84e30b6334baa6d6331b9db4ffd5a6a4": "US",
    "586baa2074e3d259b303879fc7cbea1000041b60": "EU",
    "a26bc6e037e5a8faf40250849acfa8a40d027fff": "EU",
    "ff07efe07be23a30e37601049f4e849ddc2cff02": "EU",   # EU Online v02.01 (EP9000-NPEA00019_00-TEKKENRETAIL0000)
}


class BuildGroups:
    def __init__(self, spec=""):
        data = json.loads(spec) if spec else {}
        if not isinstance(data, dict):
            raise ValueError("compatibility groups must be a JSON object")
        self.builds = {}
        for group, policy in data.items():
            if not isinstance(group, str) or not _GROUP.fullmatch(group) or not isinstance(policy, dict):
                raise ValueError("invalid compatibility group")
            net, ids = policy.get("net"), policy.get("builds")
            if isinstance(net, bool) or not isinstance(net, int) or net <= 0 or not isinstance(ids, list) or not ids:
                raise ValueError("compatibility groups need a positive net and nonempty builds list")
            for bid in ids:
                if not isinstance(bid, str) or not _ID.fullmatch(bid) or bid in self.builds:
                    raise ValueError("invalid or repeated compatibility build id")
                self.builds[bid] = (group, net)

    def group(self, bid, net, caps):
        policy = self.builds.get(bid)
        return policy[0] if CAP in caps and policy and policy[1] == net else ""


# Programs (SHA-1 of the decrypted EBOOT.elf) that may declare a crossplay group, with their edition name.
# EU v01.00 (586baa20...) is another game (different fighter data) and is deliberately absent.
CROSSPLAY_EDITIONS = {
    "be80165b84e30b6334baa6d6331b9db4ffd5a6a4": "US",
    "a26bc6e037e5a8faf40250849acfa8a40d027fff": "EU-Online",    # EU Online v02.00
    "ff07efe07be23a30e37601049f4e849ddc2cff02": "EU-Online",    # EU Online v02.01
}


class CrossplayPolicy:
    """Which declared crossplay groups the server accepts (T5L_CROSSPLAY / T5L_CROSSPLAY_GROUPS).

    `enabled` False: nothing is accepted (exact builds only, as 1.2.0). `allowed`: a set of group ids the operator
    approves; empty = any well-formed declaration from a known program. The result is "<declared group>-n<net>", so two
    equal results also share the wire version."""

    def __init__(self, enabled=True, allowed=()):
        self.enabled = bool(enabled)
        self.allowed = frozenset(a.strip().lower() for a in allowed if a.strip())
        for a in self.allowed:
            if not CROSSPLAY_RE.fullmatch(a):
                raise ValueError("invalid crossplay group: " + a)

    def group(self, build, caps):
        """The accepted group for a hello's build dict ('' = exact matching only)."""
        if not self.enabled or CAP not in caps or not isinstance(build, dict):
            return ""
        claim, elf, net = build.get("crossplay"), str(build.get("elf", "")).lower(), build.get("net")
        edition = CROSSPLAY_EDITIONS.get(elf)
        if (edition is None or not isinstance(claim, str) or not CROSSPLAY_RE.fullmatch(claim)
                or isinstance(net, bool) or not isinstance(net, int) or net <= 0):
            return ""
        if build.get("edition") not in (None, "", edition):     # a declared edition must be the program's own
            return ""
        if self.allowed and claim not in self.allowed:
            return ""
        return f"{claim}-n{net}"


def compatible(a, b):
    """Exact builds always work; different builds require both accepted group memberships."""
    if a.build_id == b.build_id:
        return True
    group = getattr(a, "compat_group", "")
    return bool(group and group == getattr(b, "compat_group", ""))


def wire_compatible(build_id, group, entry):
    """Client-side check of server-derived lobby/match metadata (old servers omit group)."""
    return entry.get("build") == build_id or bool(group and group == entry.get("compat_group"))
