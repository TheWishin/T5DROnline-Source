"""Operator-approved simulation compatibility; never inferred from a release or title.

The empty default keeps exact build matching. Groups contain complete build ids
whose game/netplay behaviour has been verified together. A client cannot choose
its group: the server derives it from the recomputed build id and wire version.
"""
import json
import re

CAP = "compat_groups"
_ID = re.compile(r"[0-9a-f]{16}\Z")
_GROUP = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
REGIONS = {
    "be80165b84e30b6334baa6d6331b9db4ffd5a6a4": "US",
    "586baa2074e3d259b303879fc7cbea1000041b60": "EU",
    "a26bc6e037e5a8faf40250849acfa8a40d027fff": "EU",
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


def compatible(a, b):
    """Exact builds always work; different builds require both accepted group memberships."""
    if a.build_id == b.build_id:
        return True
    group = getattr(a, "compat_group", "")
    return bool(group and group == getattr(b, "compat_group", ""))


def wire_compatible(build_id, group, entry):
    """Client-side check of server-derived lobby/match metadata (old servers omit group)."""
    return entry.get("build") == build_id or bool(group and group == entry.get("compat_group"))
