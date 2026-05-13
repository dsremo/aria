"""V3-Sch4: Causal ordering of cascade anomalies within incidents.

When the incident grouper clusters 8 anomalies within 300 seconds, the
output lists them all without causal ordering.  Operators need to know:
which failed first and caused the cascade?

This module applies Granger causality on pre-anomaly time series to build
a directed propagation graph, identifying source nodes (primary faults)
and propagation chains.

Reference: Granger, C.W.J. (1969). "Investigating causal relations by
           econometric models." Econometrica 37(3):424–438.
"""

from __future__ import annotations

import numpy as np
import structlog

logger = structlog.get_logger()


def order_incident_anomalies(
    anomalies: list[dict],
    time_series: dict[str, list[float]] | None = None,
) -> list[dict]:
    """Order anomalies within an incident by likely causal sequence.

    Primary ordering: by detection timestamp (first detected = likely cause).
    Secondary: by subsystem dependency graph (EPS → ADCS → COMMS).

    If time_series data is provided for the involved parameters,
    Granger causality is tested to refine the ordering.

    Args:
        anomalies: List of anomaly dicts with "parameter", "timestamp",
                   "subsystem", "severity", "confidence".
        time_series: Optional {parameter: [values]} for Granger testing.

    Returns:
        Same anomalies, sorted by causal priority (primary cause first).
        Each dict gets an added "causal_rank" field (1 = primary cause).
    """
    if not anomalies:
        return []

    # Step 1: Sort by timestamp (earliest = likely root cause).
    sorted_anoms = sorted(anomalies, key=lambda a: a.get("timestamp", ""))

    # Step 2: Apply subsystem priority (EPS faults propagate to everything).
    subsystem_priority = {
        "eps": 0,
        "adcs": 1,
        "thermal": 2,
        "comms": 3,
    }

    def _sort_key(a: dict) -> tuple:
        ts = a.get("timestamp", "")
        sub_p = subsystem_priority.get(a.get("subsystem", ""), 4)
        return (ts, sub_p)

    sorted_anoms = sorted(anomalies, key=_sort_key)

    # Step 3: Granger causality (if time series data available).
    if time_series and len(anomalies) >= 2:
        try:
            causal_edges = _granger_pairs(time_series, sorted_anoms)
            if causal_edges:
                sorted_anoms = _reorder_by_granger(sorted_anoms, causal_edges)
        except Exception:
            pass  # fall back to timestamp ordering

    # Add causal rank.
    for i, a in enumerate(sorted_anoms):
        a["causal_rank"] = i + 1

    # Build causal chain description.
    if len(sorted_anoms) >= 2:
        chain = " → ".join(a.get("parameter", "?") for a in sorted_anoms[:5])
        sorted_anoms[0]["causal_chain"] = f"Primary: {chain}"

    return sorted_anoms


def _granger_pairs(
    time_series: dict[str, list[float]],
    anomalies: list[dict],
    max_lag: int = 10,
) -> list[tuple[str, str]]:
    """Test pairwise Granger causality between anomaly parameters.

    Returns list of (cause, effect) parameter name tuples.
    """
    params = [a.get("parameter", "") for a in anomalies if a.get("parameter")]
    params = [p for p in params if p in time_series and len(time_series[p]) >= 30]

    if len(params) < 2:
        return []

    edges: list[tuple[str, str]] = []

    for i, p1 in enumerate(params):
        for p2 in params[i + 1:]:
            x = np.array(time_series[p1][-100:], dtype=np.float64)
            y = np.array(time_series[p2][-100:], dtype=np.float64)
            n = min(len(x), len(y))
            if n < max_lag + 5:
                continue
            x, y = x[-n:], y[-n:]

            # Simple F-test: does lagged X improve prediction of Y?
            gc_xy = _simple_granger_f(x, y, max_lag)
            gc_yx = _simple_granger_f(y, x, max_lag)

            if gc_xy > gc_yx and gc_xy > 2.0:
                edges.append((p1, p2))
            elif gc_yx > gc_xy and gc_yx > 2.0:
                edges.append((p2, p1))

    return edges


def _simple_granger_f(
    x: np.ndarray,
    y: np.ndarray,
    max_lag: int,
) -> float:
    """Simplified Granger F-statistic: does x Granger-cause y?

    Compares RSS of AR(p) model for y vs AR(p) model for y with lagged x.
    Returns approximate F statistic (higher = more evidence x causes y).
    """
    n = len(y)
    if n <= max_lag + 1:
        return 0.0

    # Restricted model: y_t = Σ a_k y_{t-k} + e_t
    Y = y[max_lag:]
    X_r = np.column_stack([y[max_lag - k - 1: n - k - 1] for k in range(max_lag)])

    # Unrestricted: y_t = Σ a_k y_{t-k} + Σ b_k x_{t-k} + e_t
    X_u = np.column_stack([
        X_r,
        *[x[max_lag - k - 1: n - k - 1].reshape(-1, 1) for k in range(max_lag)],
    ])

    try:
        # Least squares.
        _, rss_r, _, _ = np.linalg.lstsq(X_r, Y, rcond=None)
        _, rss_u, _, _ = np.linalg.lstsq(X_u, Y, rcond=None)

        rss_r = float(rss_r[0]) if len(rss_r) > 0 else float(np.sum((Y - X_r @ np.linalg.lstsq(X_r, Y, rcond=None)[0]) ** 2))
        rss_u = float(rss_u[0]) if len(rss_u) > 0 else float(np.sum((Y - X_u @ np.linalg.lstsq(X_u, Y, rcond=None)[0]) ** 2))

        if rss_u <= 0 or rss_r <= 0:
            return 0.0

        df1 = max_lag
        df2 = len(Y) - 2 * max_lag
        if df2 <= 0:
            return 0.0

        f_stat = ((rss_r - rss_u) / df1) / (rss_u / df2)
        return max(0.0, f_stat)
    except (np.linalg.LinAlgError, ValueError):
        return 0.0


def _reorder_by_granger(
    anomalies: list[dict],
    edges: list[tuple[str, str]],
) -> list[dict]:
    """Reorder anomalies using Granger causal edges (topological sort)."""
    # Build adjacency: cause → set of effects.
    adj: dict[str, set[str]] = {}
    all_params = {a.get("parameter", "") for a in anomalies}

    for cause, effect in edges:
        if cause in all_params and effect in all_params:
            adj.setdefault(cause, set()).add(effect)

    # Source nodes: parameters that cause others but aren't caused.
    all_effects = set()
    for effects in adj.values():
        all_effects |= effects
    sources = [p for p in adj if p not in all_effects]

    # Sort: sources first, then by original order.
    param_order = {a.get("parameter", ""): i for i, a in enumerate(anomalies)}
    for s in sources:
        param_order[s] = -1  # sources go first

    return sorted(anomalies, key=lambda a: param_order.get(a.get("parameter", ""), 999))
