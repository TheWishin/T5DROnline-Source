"""T5DR Online lobby: matchmaking service and client library.

Everything here is standard-library Python (3.10+), so the launcher and a
self-hosted server need nothing installed. See docs/ONLINE.md.

    t5lobby.proto      wire format shared by client and server
    t5lobby.client     LobbyClient -- what the launcher uses
    t5lobby.handover   MatchTicket -> environment for t5dr.exe (netplay)
    t5lobby.buildid    the build identity both players must share
    t5lobby.rating     Glicko-2
    t5lobby.server     the lobby server (python -m t5lobby.server)
"""
__version__ = "0.1.0"

from .proto import PROTO_VERSION, DEFAULT_PORT, LobbyError  # noqa: F401
from .buildid import BuildInfo  # noqa: F401


def __getattr__(name):
    # Lazy: importing the package for the server must not pull in client code and vice versa.
    if name == "LobbyClient":
        from .client import LobbyClient
        return LobbyClient
    if name == "MatchTicket":
        from .handover import MatchTicket
        return MatchTicket
    raise AttributeError(name)
