"""CLI entry — supports two sub-commands:

    python -m aria.products.cubesat_deorbit          # one-shot CLI advisor
    python -m aria.products.cubesat_deorbit serve    # HTTP service

The bare form preserves backward compatibility with the original
single-shot CLI; ``serve`` runs the aiohttp service.
"""

from __future__ import annotations

import argparse
import sys


def _run_serve(argv) -> int:
    from aiohttp import web
    from aria.products.cubesat_deorbit.service import create_app

    p = argparse.ArgumentParser(prog="cubesat-advisor serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8444)
    p.add_argument("--legacy-token", default=None)
    args = p.parse_args(argv)

    app = create_app(legacy_token_hex=args.legacy_token)
    web.run_app(app, host=args.host, port=args.port, access_log=None)
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        return _run_serve(sys.argv[2:])
    from aria.products.cubesat_deorbit.advisor import main as advisor_main
    return advisor_main()


if __name__ == "__main__":
    raise SystemExit(main())
