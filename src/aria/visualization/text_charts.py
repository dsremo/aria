"""Text-based visualization for terminal output.

ASCII charts and tables for mission data — no GUI dependencies needed.
Works over SSH, in CI, and piped to files.
"""

from __future__ import annotations

from typing import Any


def bar_chart(
    data: dict[str, float],
    max_width: int = 40,
    title: str = "",
    unit: str = "",
    sort: bool = True,
) -> str:
    """Render a horizontal bar chart."""
    if not data:
        return "  (no data)"

    lines = []
    if title:
        lines.append(f"  {title}")
        lines.append(f"  {'─' * (max_width + 30)}")

    items = sorted(data.items(), key=lambda x: -x[1]) if sort else list(data.items())
    max_val = max(data.values()) if data.values() else 1
    max_key_len = max(len(k) for k in data) if data else 0

    for key, val in items:
        bar_len = int(val / max_val * max_width) if max_val > 0 else 0
        bar = "█" * bar_len
        lines.append(f"  {key:<{max_key_len}} {val:>10.1f}{unit}  {bar}")

    return "\n".join(lines)


def timeline_chart(
    data: list[tuple[float, float]],
    width: int = 60,
    title: str = "",
    y_label: str = "",
) -> str:
    """Render a simple timeline (year vs value) as ASCII sparkline."""
    if not data:
        return "  (no data)"

    lines = []
    if title:
        lines.append(f"  {title}")

    years = [d[0] for d in data]
    values = [d[1] for d in data]
    min_v, max_v = min(values), max(values)
    v_range = max_v - min_v if max_v > min_v else 1

    # Sample points to fit width
    step = max(1, len(data) // width)
    sampled = data[::step]

    # Build sparkline
    chars = " ▁▂▃▄▅▆▇█"
    sparkline = ""
    for _, v in sampled:
        idx = int((v - min_v) / v_range * 8)
        idx = max(0, min(8, idx))
        sparkline += chars[idx]

    lines.append(f"  {y_label}")
    lines.append(f"  {max_v:>8.1f} ┤")
    lines.append(f"           {sparkline}")
    lines.append(f"  {min_v:>8.1f} ┤")
    lines.append(f"           {'└' + '─' * len(sparkline)}")
    lines.append(f"           yr {years[0]:.0f}{' ' * (len(sparkline) - 10)}yr {years[-1]:.0f}")

    return "\n".join(lines)


def comparison_table(
    legacy: dict[str, Any],
    breakthrough: dict[str, Any],
    title: str = "Legacy vs Breakthrough",
) -> str:
    """Render a side-by-side comparison table."""
    lines = [
        f"  {title}",
        f"  {'─' * 60}",
        f"  {'Metric':<25} {'Legacy':>15} {'Breakthrough':>15}",
        f"  {'─' * 60}",
    ]

    all_keys = list(dict.fromkeys(list(legacy.keys()) + list(breakthrough.keys())))
    for key in all_keys:
        l_val = legacy.get(key, "—")
        b_val = breakthrough.get(key, "—")
        if isinstance(l_val, float):
            l_str = f"{l_val:.2f}"
        else:
            l_str = str(l_val)
        if isinstance(b_val, float):
            b_str = f"{b_val:.2f}"
        else:
            b_str = str(b_val)
        lines.append(f"  {key:<25} {l_str:>15} {b_str:>15}")

    return "\n".join(lines)


def severity_summary(counts: dict[str, int]) -> str:
    """Render severity distribution as colored summary."""
    colors = {
        "EMERGENCY": "\033[41m",  # Red bg
        "CRITICAL": "\033[31m",   # Red
        "WARNING": "\033[33m",    # Yellow
        "WATCH": "\033[36m",      # Cyan
        "NOMINAL": "\033[32m",    # Green
    }
    reset = "\033[0m"

    total = sum(counts.values())
    lines = [f"  Event Distribution (total: {total:,})"]

    for sev in ["EMERGENCY", "CRITICAL", "WARNING", "WATCH", "NOMINAL"]:
        count = counts.get(sev, 0)
        if count == 0:
            continue
        pct = count / total * 100 if total > 0 else 0
        bar_len = int(pct / 2)
        bar = "█" * bar_len
        color = colors.get(sev, "")
        lines.append(f"  {color}{sev:<12}{reset} {count:>8,} ({pct:>5.1f}%) {bar}")

    return "\n".join(lines)


def mission_summary_card(results: dict[str, Any]) -> str:
    """Render a mission results summary card."""
    lines = [
        f"  ┌{'─' * 56}┐",
        f"  │ {'Mission: ' + results.get('name', 'Unknown'):<54} │",
        f"  │ {'Type: ' + results.get('type', '?'):<54} │",
        f"  ├{'─' * 56}┤",
    ]

    fields = [
        ("Duration", f"{results.get('duration_s', 0):.0f}s"),
        ("Frames", f"{results.get('frames', 0):,}"),
        ("Events", f"{results.get('events', 0):,}"),
        ("Status", results.get("status", "UNKNOWN")),
    ]

    for label, value in fields:
        lines.append(f"  │ {label + ':':<20} {value:>34} │")

    lines.append(f"  └{'─' * 56}┘")
    return "\n".join(lines)
