"""Entry point for ``python -m draughts.engine``.

Two modes:

1. UCI-like text protocol (default) — reads commands from stdin, writes
   responses to stdout::

       $ python -m draughts.engine

2. DXP server (item #33) — listens on a TCP port for FMJD DXP-formatted
   game negotiations::

       $ python -m draughts.engine --dxp [--port 27531] [--level 4]

DXP lets external draughts GUIs (CheckerBoard, Dam 3.0, …) host this
engine, and enables self-play tournaments via the FMJD-standard protocol.
"""

from __future__ import annotations

import argparse
import logging
import sys

from draughts.engine import run_engine_main
from draughts.engine.dxp_server import DEFAULT_PORT, serve_forever


def main() -> None:
    parser = argparse.ArgumentParser(prog="draughts.engine")
    parser.add_argument("--dxp", action="store_true", help="start a DXP TCP server instead of the UCI-like protocol")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port for --dxp mode (default %(default)s)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address for --dxp mode")
    parser.add_argument("--level", type=int, default=4, help="engine difficulty 1-6 (default 4)")
    parser.add_argument("--max-games", type=int, default=None, help="serve only N games then exit (useful for tests)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log to stderr at INFO level")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(message)s")

    if args.dxp:
        serve_forever(host=args.host, port=args.port, difficulty=args.level, max_games=args.max_games)
    else:
        run_engine_main()


if __name__ == "__main__":
    main()
