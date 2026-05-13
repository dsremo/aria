"""R42 §2.1 — thermal-protection ablation modelling.

Currently empty submodule namespace housing the Goldstein-1965
charring/ablation model added in R42 (`ablation.py`).
"""

from aria.physics.thermal_protection.ablation import (
    AblationConfig, AblationResult, simulate_ablation, recession_rate_m_s,
    TPS_MATERIALS,
)

__all__ = [
    "AblationConfig", "AblationResult", "simulate_ablation",
    "recession_rate_m_s", "TPS_MATERIALS",
]
