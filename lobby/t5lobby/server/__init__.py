"""The lobby server. Run it with `python -m t5lobby.server` (from the lobby/ folder);
configuration comes from T5L_* environment variables (see config.py, docs/ONLINE.md)."""
from .config import Config  # noqa: F401
from .lobby import LobbyServer  # noqa: F401
