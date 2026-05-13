"""R229 — MEV / front-running detector.

Threat: a searcher bot front-runs the user's pending tx in the
mempool to capture sandwich profit.  Flashbots 2024 estimate: $1B+
extracted yearly.  Beyond loss to user, MEV concentrates miner /
validator power.

Defence: ``score_mev_risk`` for an outbound tx against current
mempool / gas-price patterns; recommend a private bundle (Flashbots
Protect, Eden, MEV-Share) when the risk is high.
"""

from __future__ import annotations

from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


def score_mev_risk(
    *,
    tx_value_wei: int,
    gas_price_gwei: float,
    is_swap: bool = False,
    pool_liquidity_wei: int = 0,
    slippage_pct: float = 0.5,
    mempool_pending: int = 0,
) -> Tuple[float, str]:
    score = 0.0
    notes = []
    if is_swap:
        score += 0.3
        notes.append("swap")
    if pool_liquidity_wei and tx_value_wei > 0:
        impact = tx_value_wei / pool_liquidity_wei
        if impact > 0.005:
            score += 0.4
            notes.append(f"impact={impact * 100:.2f}%")
    if slippage_pct >= 1.0:
        score += 0.2
        notes.append(f"slippage={slippage_pct}")
    if gas_price_gwei < 5.0 and mempool_pending > 200:
        score += 0.2
        notes.append("low_gas+busy_mempool")
    score = min(1.0, score)
    return score, ",".join(notes) or "low_risk"


def recommend_protection(score: float) -> str:
    if score >= 0.6:
        return ("Use Flashbots Protect / MEV-Share private bundle; "
                "set hard slippage tolerance ≤ 0.5%; split into "
                "smaller orders if pool impact > 0.5%.")
    if score >= 0.3:
        return "Tighten slippage; consider a private mempool relay."
    return "Public mempool acceptable."


register(DefencePlugin(
    round_id="R229",
    name="mev_detect",
    description="Per-tx MEV risk score + private-bundle recommender.",
))
