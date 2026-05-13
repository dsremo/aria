"""Stand-alone load-test harness for the ARIA Conjunction Screener.

This is intentionally dependency-light (only ``aiohttp``).  It does
not replace ``locust`` or ``k6`` — those tools are available if the
operator needs distributed load — but it removes the need to install
anything beyond what the screener already pulls in.

Modes:

  * ``--mode warm`` : 1 request, used as a smoke test before the
    main load run.
  * ``--mode burst`` : ``--n`` parallel requests issued back-to-back.
  * ``--mode sustained`` : ``--rate`` requests per second for
    ``--duration`` seconds.

Outputs an end-of-run summary with p50 / p95 / p99 latency, error
rate, and observed throughput.

Usage::

    python deploy/screener/load_test.py \\
        --target http://127.0.0.1:8443 \\
        --token <api-key> \\
        --mode sustained --rate 5 --duration 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from typing import List, Tuple


# Iridium-Cosmos pair — pre-collision broadcast TLEs (SpaceTrack
# archive 2009-02-09).  Used as a deterministic load-test payload.
IRIDIUM_LINE1 = "1 24946U 97051C   09040.50000000  .00000147  00000-0  39150-4 0  9999"
IRIDIUM_LINE2 = "2 24946  86.3984 121.6730 0002247  90.5840 269.5520 14.34218054592839"
COSMOS_LINE1  = "1 22675U 93036A   09040.50000000  .00000044  00000-0  20000-4 0  9994"
COSMOS_LINE2  = "2 22675  74.0353  19.4937 0016000  64.5311 295.5912 14.31410830 75835"


def _payload() -> dict:
    return {
        "primary": {
            "norad_id": "24946", "name": "IRIDIUM 33",
            "line1": IRIDIUM_LINE1, "line2": IRIDIUM_LINE2,
            "radius_m": 1.5,
        },
        "secondaries": [{
            "norad_id": "22675", "name": "COSMOS 2251",
            "line1": COSMOS_LINE1, "line2": COSMOS_LINE2,
            "radius_m": 2.5,
        }],
        "approx_tca_utc": "2009-02-10T16:56:00Z",
    }


async def _hit(session, target: str, token: str) -> Tuple[float, int]:
    t0 = time.monotonic()
    try:
        async with session.post(
            f"{target}/v1/screen",
            json=_payload(),
            headers={"X-ARIA-Token": token},
            timeout=30.0,
        ) as r:
            await r.read()
            return (time.monotonic() - t0) * 1000.0, r.status
    except Exception:
        return (time.monotonic() - t0) * 1000.0, -1


async def _burst(target: str, token: str, n: int) -> List[Tuple[float, int]]:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        tasks = [_hit(session, target, token) for _ in range(n)]
        return await asyncio.gather(*tasks)


async def _sustained(
    target: str, token: str, rate: float, duration: float,
) -> List[Tuple[float, int]]:
    import aiohttp
    interval = 1.0 / rate
    end = time.monotonic() + duration
    out: List[Tuple[float, int]] = []
    async with aiohttp.ClientSession() as session:
        next_t = time.monotonic()
        while time.monotonic() < end:
            now = time.monotonic()
            if now < next_t:
                await asyncio.sleep(next_t - now)
            asyncio.create_task(_record(session, target, token, out))
            next_t += interval
        # Drain in-flight tasks.
        await asyncio.sleep(2.0)
    return out


async def _record(session, target, token, out):
    res = await _hit(session, target, token)
    out.append(res)


def _summary(results: List[Tuple[float, int]]) -> dict:
    if not results:
        return {"n": 0}
    latencies = [r[0] for r in results if r[1] != -1]
    statuses = [r[1] for r in results]
    ok = sum(1 for s in statuses if 200 <= s < 300)
    return {
        "n": len(results),
        "ok": ok,
        "error_rate": (len(results) - ok) / len(results),
        "p50_ms": statistics.median(latencies) if latencies else 0.0,
        "p95_ms": _quantile(latencies, 0.95) if latencies else 0.0,
        "p99_ms": _quantile(latencies, 0.99) if latencies else 0.0,
        "max_ms": max(latencies) if latencies else 0.0,
        "min_ms": min(latencies) if latencies else 0.0,
    }


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((len(s) - 1) * q))
    return s[max(0, min(k, len(s) - 1))]


async def _main() -> int:
    parser = argparse.ArgumentParser(prog="aria-screener-loadtest")
    parser.add_argument("--target", default="http://127.0.0.1:8443")
    parser.add_argument("--token", required=True)
    parser.add_argument("--mode", choices=["warm", "burst", "sustained"], default="warm")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--rate", type=float, default=5.0)
    parser.add_argument("--duration", type=float, default=30.0)
    args = parser.parse_args()

    if args.mode == "warm":
        import aiohttp
        async with aiohttp.ClientSession() as s:
            res = [await _hit(s, args.target, args.token)]
    elif args.mode == "burst":
        res = await _burst(args.target, args.token, args.n)
    else:
        res = await _sustained(args.target, args.token, args.rate, args.duration)

    summary = _summary(res)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("error_rate", 1.0) < 0.05 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
