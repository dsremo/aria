"""CLI entry — `python -m aria.products.conjunction_screener serve`."""

from __future__ import annotations

import argparse
import sys


def serve_cmd(args: argparse.Namespace) -> int:
    from aiohttp import web
    from aria.products.conjunction_screener.service import create_app
    app = create_app()
    web.run_app(app, host=args.host, port=args.port, access_log=None)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="aria-screener")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the conjunction-screener HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8443)
    s.set_defaults(fn=serve_cmd)
    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        p.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
