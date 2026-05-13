"""Statistical distributions of minor-body populations in the Solar System.

Shipping ~1M asteroid orbits is overkill for a web visualization; instead,
this module generates representative point clouds that reproduce the
observed radial density profile, including the Kirkwood resonant gaps.

Populations:
- **Main belt**: 1.7 AU to 4.2 AU, density peaks around 2.77 AU (Ceres),
  with characteristic gaps at mean-motion resonances with Jupiter.
- **Jupiter Trojans**: L4 / L5 libration points (±60° ahead / behind).
- **Kuiper belt**: Classical 42-48 AU, Plutinos at 39.5 AU (2:3 resonance).
- **Scattered disk**: 50-200 AU, highly inclined and eccentric.

These are stochastic models for visualization, not ephemerides. For
real minor-planet positions use MPCORB.

References:
    Dermott, S. F. & Murray, C. D. (1983) Nature 301:201 (Kirkwood gaps)
    Petit, J.-M. et al. (2011) AJ 142:131 (classical Kuiper belt)
    Minor Planet Center orbit statistics (open data).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Tuple


# Jupiter mean motion used to compute resonance positions: n_J = 360/4332.59 = 0.0831°/day
# Mean-motion resonance a_res = a_Jupiter * (p/q)^(-2/3), a_Jupiter = 5.2044 AU
_A_JUPITER = 5.2044
_A_NEPTUNE = 30.07


def _res_a(p: int, q: int, a_perturber: float) -> float:
    """Semi-major axis at p:q mean-motion resonance with perturber."""
    return a_perturber * (q / p) ** (2.0 / 3.0)


# Main-belt Kirkwood gap centers (Dermott & Murray 1983)
KIRKWOOD_GAPS: List[Tuple[float, float]] = [
    (_res_a(3, 1, _A_JUPITER), 0.02),    # 3:1 at 2.50 AU
    (_res_a(5, 2, _A_JUPITER), 0.02),    # 5:2 at 2.82 AU
    (_res_a(7, 3, _A_JUPITER), 0.015),   # 7:3 at 2.96 AU
    (_res_a(2, 1, _A_JUPITER), 0.03),    # 2:1 at 3.28 AU (Hecuba gap)
]


@dataclass
class BeltSample:
    """Random (a, e, i, Ω, ω, M) in the requested population."""
    a_au: float
    ecc: float
    inc_deg: float
    node_deg: float
    argp_deg: float
    M_deg: float
    family: str          # 'main_belt' / 'trojan_L4' / 'trojan_L5' / 'kuiper' / 'scattered'


# ════════════════════════════════════════════════════════════════════
#  Synthesizers
# ════════════════════════════════════════════════════════════════════

def synthesize_main_belt(n: int = 600, seed: int = 17) -> List[BeltSample]:
    """Generate n main-belt samples honoring the Kirkwood gaps."""
    rng = random.Random(seed)
    out: List[BeltSample] = []

    def _in_gap(a: float) -> bool:
        for a_gap, half_width in KIRKWOOD_GAPS:
            if abs(a - a_gap) < half_width:
                return True
        return False

    while len(out) < n:
        # Rejection sampling: bias toward the observed density peak ~2.77 AU
        a = rng.uniform(2.05, 3.70)
        peak = math.exp(-((a - 2.77) / 0.45) ** 2)
        if rng.random() > peak * 0.95:
            continue
        if _in_gap(a):
            if rng.random() > 0.10:   # 10% residual density inside gaps
                continue
        ecc = abs(rng.gauss(0.15, 0.08))
        if ecc > 0.35:
            continue
        inc = abs(rng.gauss(0, 7))       # degrees; narrow distribution
        out.append(BeltSample(
            a_au=a, ecc=ecc, inc_deg=inc,
            node_deg=rng.uniform(0, 360),
            argp_deg=rng.uniform(0, 360),
            M_deg=rng.uniform(0, 360),
            family="main_belt",
        ))
    return out


def synthesize_trojans(n: int = 100, seed: int = 29) -> List[BeltSample]:
    """Jupiter Trojans at L4 (Greek camp, leads Jupiter) and L5 (Trojan camp)."""
    rng = random.Random(seed)
    out: List[BeltSample] = []
    # At L4/L5 the semi-major axis is essentially Jupiter's and mean anomaly
    # differs from Jupiter's by ±60°.
    for camp in ("L4", "L5"):
        offset = 60.0 if camp == "L4" else -60.0
        for _ in range(n // 2):
            a = rng.gauss(_A_JUPITER, 0.12)
            ecc = abs(rng.gauss(0.07, 0.04))
            inc = abs(rng.gauss(8, 5))
            out.append(BeltSample(
                a_au=a, ecc=ecc, inc_deg=inc,
                node_deg=rng.uniform(0, 360),
                argp_deg=rng.uniform(0, 360),
                # Libration around ±60° relative to Jupiter's mean anomaly
                M_deg=(rng.uniform(-20, 20) + offset + 180) % 360,
                family=f"trojan_{camp}",
            ))
    return out


def synthesize_kuiper_belt(n: int = 300, seed: int = 47) -> List[BeltSample]:
    """Classical + resonant Kuiper belt. Density peak 42-48 AU."""
    rng = random.Random(seed)
    out: List[BeltSample] = []
    for _ in range(n):
        r = rng.random()
        if r < 0.25:
            # Plutinos at 3:2 resonance with Neptune — 39.5 AU
            a = rng.gauss(_res_a(3, 2, _A_NEPTUNE), 0.4)
            ecc = abs(rng.gauss(0.22, 0.08))
            inc = abs(rng.gauss(10, 8))
            family = "kuiper_plutino"
        elif r < 0.85:
            # Classical Kuiper belt 42-48 AU, low-e / low-i
            a = rng.uniform(41.0, 47.5)
            ecc = abs(rng.gauss(0.07, 0.04))
            inc = abs(rng.gauss(4, 4))
            family = "kuiper_classical"
        else:
            # 2:1 resonance at ~47.7 AU (twotinos)
            a = rng.gauss(_res_a(2, 1, _A_NEPTUNE), 0.5)
            ecc = abs(rng.gauss(0.20, 0.08))
            inc = abs(rng.gauss(8, 6))
            family = "kuiper_twotino"
        out.append(BeltSample(
            a_au=a, ecc=ecc, inc_deg=inc,
            node_deg=rng.uniform(0, 360),
            argp_deg=rng.uniform(0, 360),
            M_deg=rng.uniform(0, 360),
            family=family,
        ))
    return out


def synthesize_scattered_disk(n: int = 100, seed: int = 59) -> List[BeltSample]:
    """Scattered disk objects: high a (50-200 AU), high e, high i."""
    rng = random.Random(seed)
    out: List[BeltSample] = []
    for _ in range(n):
        a = math.exp(rng.uniform(math.log(50), math.log(200)))
        ecc = abs(rng.gauss(0.4, 0.15))
        if ecc > 0.8:
            ecc = 0.8 - rng.random() * 0.2
        inc = abs(rng.gauss(25, 15))
        if inc > 70:
            inc = 70
        out.append(BeltSample(
            a_au=a, ecc=ecc, inc_deg=inc,
            node_deg=rng.uniform(0, 360),
            argp_deg=rng.uniform(0, 360),
            M_deg=rng.uniform(0, 360),
            family="scattered_disk",
        ))
    return out


# ════════════════════════════════════════════════════════════════════
#  Project a BeltSample to a 3D heliocentric point (for visualization)
# ════════════════════════════════════════════════════════════════════

def sample_position(s: BeltSample) -> Tuple[float, float, float]:
    """Heliocentric ecliptic (x, y, z) at the sample's mean anomaly epoch."""
    # Solve Kepler once for this sample
    M = math.radians(s.M_deg) % (2 * math.pi)
    E = M + s.ecc * math.sin(M)
    for _ in range(15):
        dE = (E - s.ecc * math.sin(E) - M) / (1 - s.ecc * math.cos(E))
        E -= dE
        if abs(dE) < 1e-10:
            break
    cosE, sinE = math.cos(E), math.sin(E)
    x_orb = s.a_au * (cosE - s.ecc)
    y_orb = s.a_au * math.sqrt(1 - s.ecc * s.ecc) * sinE

    co, so = math.cos(math.radians(s.argp_deg)), math.sin(math.radians(s.argp_deg))
    cn, sn = math.cos(math.radians(s.node_deg)), math.sin(math.radians(s.node_deg))
    ci, si = math.cos(math.radians(s.inc_deg)), math.sin(math.radians(s.inc_deg))

    x = (co * cn - so * sn * ci) * x_orb + (-so * cn - co * sn * ci) * y_orb
    y = (co * sn + so * cn * ci) * x_orb + (-so * sn + co * cn * ci) * y_orb
    z = (so * si) * x_orb + (co * si) * y_orb
    return x, y, z
