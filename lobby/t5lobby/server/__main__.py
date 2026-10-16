"""python -m t5lobby.server [--port N] [--udp-port N] [--db FILE] ...

Command-line options override the T5L_* environment variables of the same name."""
import argparse
import asyncio
import logging
import signal
import sys

from .. import proto
from .config import Config
from .lobby import LobbyServer


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m t5lobby.server", description="T5DR Online lobby server")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--udp-port", type=int)
    ap.add_argument("--udp-port2", type=int, help="NAT probe port, 0 = off")
    ap.add_argument("--db")
    ap.add_argument("--log-level")
    ap.add_argument("--force-relay", action="store_true", default=None)
    a = ap.parse_args(argv)
    over = {k: v for k, v in vars(a).items() if v is not None}
    cfg = Config.from_env(**over)
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    loop = proto.new_event_loop()
    asyncio.set_event_loop(loop)
    srv = LobbyServer(cfg)
    stop = asyncio.Event()

    async def run():
        await srv.start()
        print(f"t5lobby: TCP {srv.port}, UDP {srv.udp.port}" + (f"/{srv.udp.port2}" if srv.udp.port2 else ""),
              flush=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError):
                pass   # Windows: Ctrl+C raises KeyboardInterrupt instead
        await stop.wait()
        await srv.stop()

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        loop.run_until_complete(srv.stop())
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
