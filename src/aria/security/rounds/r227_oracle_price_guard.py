"""R227 — DeFi oracle price-manipulation guard.

Threat: a single-source spot-price oracle (e.g. Uniswap-v2 reserves)
can be flash-loaned out of true value for 1 block, draining lending
markets.  bZx 2020 ($350K), Cream Finance 2022 ($130M), Mango 2022
($117M) all had spot-oracle dependence.

Defence: enforce a *median* of N independent oracle reads,
time-weighted-average-price (TWAP) over a configurable window, and a
deviation cap that refuses any single sample > X% from TWAP.
"""

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _PriceFeed:
    samples: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=4096))


_FEEDS: Dict[str, _PriceFeed] = {}
_LOCK = threading.Lock()


def record_sample(asset: str, price: float, *, ts: float = 0.0) -> None:
    t = ts or time.time()
    with _LOCK:
        feed = _FEEDS.setdefault(asset, _PriceFeed())
        feed.samples.append((t, price))


def get_safe_price(
    asset: str,
    *,
    twap_window_seconds: float = 1800.0,
    max_deviation_pct: float = 5.0,
    now: float = 0.0,
) -> Tuple[bool, float, str]:
    t = now or time.time()
    with _LOCK:
        feed = _FEEDS.get(asset)
        samples = list(feed.samples) if feed else []
    in_window = [(ts, p) for ts, p in samples if t - ts <= twap_window_seconds]
    if len(in_window) < 3:
        return False, 0.0, f"oracle.insufficient_samples n={len(in_window)}"
    prices = [p for _, p in in_window]
    twap = statistics.mean(prices)
    median = statistics.median(prices)
    last_ts, last_price = in_window[-1]
    deviation_pct = abs(last_price - twap) / twap * 100.0 if twap else 0.0
    if deviation_pct > max_deviation_pct:
        return False, twap, f"oracle.deviation last={last_price:.4f} twap={twap:.4f} dev={deviation_pct:.1f}%"
    return True, median, f"oracle.ok n={len(in_window)} twap={twap:.4f}"


def median_of(samples: Iterable[float]) -> float:
    s = list(samples)
    return statistics.median(s) if s else 0.0


register(DefencePlugin(
    round_id="R227",
    name="oracle_price_guard",
    description="DeFi oracle price-feed median + TWAP + deviation cap.",
))
