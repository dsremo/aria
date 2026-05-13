"""Render a self-contained HTML status page for the ARIA services.

Usage:
    python scripts/render_status_page.py --output /var/www/status.html

Probes ``/v1/healthz`` on the configured screener + advisor URLs (or
local default) and emits a static HTML page suitable for upload to a
status subdomain.  No JavaScript, no external CDN, no cookies — pure
HTML so it works through firewalls.

Run from cron every 60 s:

    * * * * * /usr/bin/python3 /opt/aria-core/scripts/render_status_page.py \
        --output /var/www/status.html
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Tuple


def _probe(url: str, timeout: float = 3.0) -> Tuple[str, float, str]:
    """Return (status, latency_ms, detail)."""
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")[:200]
            elapsed = (time.monotonic() - t0) * 1000.0
            if r.status == 200:
                return ("up", elapsed, body)
            return ("degraded", elapsed, f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - t0) * 1000.0
        return ("degraded", elapsed, f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
        elapsed = (time.monotonic() - t0) * 1000.0
        return ("down", elapsed, f"unreachable: {e}")
    except Exception as e:                                    # pragma: no cover
        elapsed = (time.monotonic() - t0) * 1000.0
        return ("down", elapsed, f"error: {type(e).__name__}: {e}")


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ARIA Service Status</title>
<style>
  body  {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
           color: #222; max-width: 720px; margin: 32px auto; padding: 0 24px; }}
  h1    {{ color: #003366; margin-bottom: 4px; }}
  .gen  {{ color: #888; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 24px; font-size: 14px; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }}
  th    {{ background: #f3f5f7; }}
  .up       {{ color: #1f7a3a; font-weight: 600; }}
  .down     {{ color: #a8232c; font-weight: 600; }}
  .degraded {{ color: #b27200; font-weight: 600; }}
  code  {{ background: #f3f5f7; padding: 2px 5px; border-radius: 3px; }}
  footer {{ margin-top: 24px; font-size: 12px; color: #666; }}
</style>
</head>
<body>
<h1>ARIA Service Status</h1>
<p class="gen">Last checked: {generated}</p>
<table>
<thead><tr><th>Service</th><th>Endpoint</th><th>Status</th><th>Latency</th><th>Detail</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<footer>This is a static page rendered by
<code>scripts/render_status_page.py</code>.  Re-run on a 60 s cron
for live updates.  Operator-side incidents and post-mortems are
posted to the operator's blog or status feed.</footer>
</body></html>
"""


def render(probes: List[Dict[str, str]]) -> str:
    rows = []
    for p in probes:
        rows.append(
            f"<tr><td>{html.escape(p['name'])}</td>"
            f"<td><code>{html.escape(p['url'])}</code></td>"
            f"<td class=\"{p['status']}\">{p['status'].upper()}</td>"
            f"<td>{p['latency']:.0f} ms</td>"
            f"<td>{html.escape(p['detail'])}</td></tr>"
        )
    return _HTML.format(
        generated=_dt.datetime.now(tz=_dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"),
        rows="\n".join(rows),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="aria-status-page")
    parser.add_argument(
        "--screener-url", default="http://127.0.0.1:8443/v1/healthz",
    )
    parser.add_argument(
        "--advisor-url", default="http://127.0.0.1:8444/v1/healthz",
    )
    parser.add_argument("--output", default="-")
    parser.add_argument(
        "--json", action="store_true",
        help="emit JSON instead of HTML (for monitoring integrations)",
    )
    args = parser.parse_args(argv)

    probes: List[Dict[str, object]] = []
    for name, url in [
        ("Conjunction Screener", args.screener_url),
        ("CubeSat De-Orbit Advisor", args.advisor_url),
    ]:
        status, latency, detail = _probe(url)
        probes.append({
            "name": name, "url": url,
            "status": status, "latency": latency, "detail": detail,
        })

    if args.json:
        out = json.dumps({"checked_at": _dt.datetime.now(
            tz=_dt.timezone.utc).isoformat(), "probes": probes}, indent=2)
    else:
        out = render(probes)

    if args.output == "-":
        sys.stdout.write(out)
    else:
        from pathlib import Path
        Path(args.output).write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
