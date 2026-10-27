"""The build identity both players of a match must share.

Lockstep netplay only works when both PCs run identical game code. That code
is fixed by three things:

    elf_sha1  SHA-1 of the decrypted EBOOT.elf (the game itself; the builder pins it)
    code_id   build_game.code_id(): ps3recomp commit, our patches, lifter settings,
              CMakeLists -- recorded in <out>/build/t5dr_build.json at build time
    net       the netplay wire version this launcher speaks (NETPLAY_VERSION)

build id = first 16 hex digits of SHA-1("t5dr-build:<elf_sha1>:<code_id>:<net>").
The release string is informational only (shown in the lobby).
"""
import hashlib
import json
import os
from dataclasses import dataclass, field

NETPLAY_VERSION = 4    # src/netplay kVersion; raise together with it (3: round trip + rollback input delay in PING/INPUT;
                       # 4: COSTUME, each player's custom costume table at the start of a session)


def sha1_file(path, chunk=1 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


@dataclass
class BuildInfo:
    elf_sha1: str
    code_id: str
    release: str = "dev"
    net: int = NETPLAY_VERSION
    build_id: str = field(default="")

    def __post_init__(self):
        if not self.build_id:
            s = f"t5dr-build:{self.elf_sha1.lower()}:{self.code_id.lower()}:{self.net}"
            self.build_id = hashlib.sha1(s.encode()).hexdigest()[:16]

    def as_wire(self):
        return {"id": self.build_id, "elf": self.elf_sha1, "code": self.code_id,
                "net": self.net, "release": self.release}

    @staticmethod
    def wire_id(build):
        """Recompute the id from a wire dict (the server does not trust the client's "id")."""
        return BuildInfo(str(build.get("elf", "")), str(build.get("code", "")),
                         str(build.get("release", "")), int(build.get("net", 0))).build_id

    @staticmethod
    def has_online(out):
        """Does the game built in `out` have the online modules (netplay, rollback, direct fight)? A Windows
        build always has them; a macOS build only when built with tools/build_game.py --macos-online, which
        records "online": true in <out>/build/t5dr_build.json (docs/MACOS_ONLINE_TEST.md). An unreadable
        stamp answers True: from_out_dir() reports that problem."""
        try:
            with open(os.path.join(out, "build", "t5dr_build.json"), encoding="utf-8") as f:
                return json.load(f).get("online", True) is not False
        except (OSError, ValueError):
            return True

    @classmethod
    def from_out_dir(cls, out, release="dev"):
        """From a build made by tools/build_game.py: <out>/game/EBOOT.elf and
        <out>/build/t5dr_build.json (code_id). Raises OSError/ValueError when it is not built."""
        elf = os.path.join(out, "game", "EBOOT.elf")
        stamp = os.path.join(out, "build", "t5dr_build.json")
        with open(stamp, encoding="utf-8") as f:
            info = json.load(f)
        code = info.get("code_id")
        if not code:
            raise ValueError(f"{stamp} has no code_id")
        return cls(sha1_file(elf), code, release)   # hash the file itself (5 MB, a few ms)
