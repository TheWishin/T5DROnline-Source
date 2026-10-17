"""Start the lobby tools with any Python 3.10+, including the release zip's bundled one (its
python312._pth ignores PYTHONPATH and the current folder, so `-m t5lobby...` cannot be found):

    python lobby/run.py server [--port N ...]     the lobby server        (= python -m t5lobby.server)
    python lobby/run.py host [--map-ports ...]    Host for friends        (= python -m t5lobby.server.host)
    python lobby/run.py admin COMMAND ...         administration          (= python -m t5lobby.server.admin)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if cmd == "server":
        from t5lobby.server.__main__ import main as run
    elif cmd == "host":
        from t5lobby.server.host import main as run
    elif cmd == "admin":
        from t5lobby.server.admin import main as run
    else:
        print(__doc__)
        return 2
    sys.argv[0] = f"run.py {cmd}"
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
