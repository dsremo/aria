"""Thermodynamic disequilibrium metric for biosignature assessment.

BUILD-F12 (Witten): "The Gibbs free energy of atmospheric disequilibrium
is the most mathematically elegant biosignature metric."

Earth: ΔG_diseq ≈ -2326 J/mol (driven by O₂-CH₄ coexistence)
Mars: ΔG_diseq ≈ -4 J/mol (near thermodynamic equilibrium)
Venus: ΔG_diseq ≈ -0.2 J/mol (near equilibrium despite extreme conditions)

Reference: Krissansen-Totton, Bergsman, Catling (2016) ApJ 817:31
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import structlog

logger = structlog.get_logger()

# Gas constant
R = 8.314462  # CODATA 2018: R = 8.314462618 J/(mol·K) (NIST SRD 121)

# Standard chemical potentials at 298 K, 1 bar (kJ/mol)
# Source: NIST-JANAF Thermochemical Tables, 4th ed. (Chase 1998)
MU_STANDARD: dict[str, float] = {
    "N2":   0.0,     # Chase 1998 NIST-JANAF: ΔGf°(N2) = 0 by convention (reference element)
    "O2":   0.0,     # Chase 1998 NIST-JANAF: ΔGf°(O2) = 0 by convention (reference element)
    "H2O":  -228.6,  # Chase 1998 NIST-JANAF Table H2O-1: ΔGf°(H2O, g) = -228.6 kJ/mol
    "CO2":  -394.4,  # Chase 1998 NIST-JANAF Table CO2-1: ΔGf°(CO2) = -394.4 kJ/mol
    "CH4":  -50.5,   # Chase 1998 NIST-JANAF Table CH4-1: ΔGf°(CH4) = -50.5 kJ/mol
    "H2":   0.0,     # Chase 1998 NIST-JANAF: ΔGf°(H2) = 0 by convention (reference element)
    "He":   0.0,     # Chase 1998 NIST-JANAF: ΔGf°(He) = 0 by convention (reference element)
    "CO":   -137.2,  # Chase 1998 NIST-JANAF Table CO-1: ΔGf°(CO) = -137.2 kJ/mol
    "N2O":  104.2,   # Chase 1998 NIST-JANAF Table N2O-1: ΔGf°(N2O) = 104.2 kJ/mol
    "NH3":  -16.4,   # Chase 1998 NIST-JANAF Table NH3-1: ΔGf°(NH3) = -16.4 kJ/mol
    "O3":   163.2,   # Chase 1998 NIST-JANAF Table O3-1: ΔGf°(O3) = 163.2 kJ/mol
    "SO2":  -300.1,  # Chase 1998 NIST-JANAF Table SO2-1: ΔGf°(SO2) = -300.1 kJ/mol
    "H2S":  -33.4,   # Chase 1998 NIST-JANAF Table H2S-1: ΔGf°(H2S) = -33.4 kJ/mol
    "DMS":  -37.0,   # ESTIMATE — ΔGf°(dimethyl sulfide, g) ≈ -37 kJ/mol (Benson 1976 group contribution)
    "DMDS": -24.0,   # ESTIMATE — ΔGf°(dimethyl disulfide, g) ≈ -24 kJ/mol (Benson 1976 group contribution)
}

# Elemental composition (C, H, O, N, S atoms per molecule)
ELEMENTAL_COMP: dict[str, dict[str, int]] = {
    "N2": {"N": 2},
    "O2": {"O": 2},
    "H2O": {"H": 2, "O": 1},
    "CO2": {"C": 1, "O": 2},
    "CH4": {"C": 1, "H": 4},
    "H2": {"H": 2},
    "He": {},
    "CO": {"C": 1, "O": 1},
    "N2O": {"N": 2, "O": 1},
    "NH3": {"N": 1, "H": 3},
    "O3": {"O": 3},
    "SO2": {"S": 1, "O": 2},
    "H2S": {"H": 2, "S": 1},
    "DMS": {"C": 2, "H": 6, "S": 1},
    "DMDS": {"C": 2, "H": 6, "S": 2},
}


@dataclass(frozen=True)
class DisequilibriumResult:
    """Thermodynamic disequilibrium analysis result."""

    delta_g_j_per_mol: float  # Gibbs free energy of disequilibrium (J/mol)
    delta_g_kj_per_mol: float  # Same in kJ/mol
    g_actual: float  # Gibbs energy of observed atmosphere
    g_equilibrium: float  # Gibbs energy at thermodynamic equilibrium
    classification: str  # "strong_disequilibrium", "moderate", "near_equilibrium"
    earth_comparison: float  # ratio to Earth's disequilibrium
    interpretation: str
    actual_composition: dict[str, float]  # observed mixing ratios
    equilibrium_composition: dict[str, float]  # computed equilibrium


def compute_gibbs_energy(
    mixing_ratios: dict[str, float],
    temperature_k: float,
) -> float:
    """Compute Gibbs free energy of an atmospheric mixture.

    G_mix = Σᵢ xᵢ × (μ°ᵢ(T) + RT × ln(xᵢ))

    where xᵢ is the mixing ratio (mole fraction) and μ°ᵢ is the
    standard chemical potential.

    Args:
        mixing_ratios: {species: mole_fraction}. Must sum to ≤ 1.
        temperature_k: Atmospheric temperature in Kelvin.

    Returns:
        Gibbs free energy in J/mol.
    """
    g = 0.0
    for species, x in mixing_ratios.items():
        if x <= 0 or species not in MU_STANDARD:
            continue
        mu_standard = MU_STANDARD[species] * 1000  # kJ → J
        # Temperature correction (approximate: ΔG(T) ≈ ΔG(298) - TΔS)
        # For simplicity, use ideal gas mixing entropy only
        g += x * (mu_standard + R * temperature_k * math.log(max(x, 1e-30)))
    return g


def _prereact_composition(
    composition: dict[str, float],
) -> dict[str, float]:
    """Drive known spontaneous reactions to completion to get a pre-reacted starting point.

    This gives the optimizer a head-start near the true equilibrium rather than
    starting from the (thermodynamically metastable) actual composition.

    Reactions driven to completion (in order, limited by stoichiometry):
      CH4 + 2 O2  → CO2 + 2 H2O   (ΔG°_rxn ≈ -801 kJ/mol)
      H2  + ½ O2  → H2O            (ΔG°_rxn ≈ -228 kJ/mol)
      N2O → N2   + ½ O2            (ΔG°_rxn ≈ -104 kJ/mol)
      O3  → 3/2 O2                  (ΔG°_rxn ≈ -163 kJ/mol)
      CO  + ½ O2  → CO2             (ΔG°_rxn ≈ -257 kJ/mol)
    """
    comp = dict(composition)

    def get(sp: str) -> float:
        return max(comp.get(sp, 0.0), 0.0)

    def set_(sp: str, val: float) -> None:
        comp[sp] = max(val, 1e-30)

    # CH4 + 2 O2 → CO2 + 2 H2O
    if get("CH4") > 0 and get("O2") > 0:
        extent = min(get("CH4"), get("O2") / 2.0)
        set_("CH4", get("CH4") - extent)
        set_("O2", get("O2") - 2.0 * extent)
        set_("CO2", get("CO2") + extent)
        set_("H2O", get("H2O") + 2.0 * extent)

    # H2 + ½ O2 → H2O
    if get("H2") > 0 and get("O2") > 0:
        extent = min(get("H2"), get("O2") * 2.0)
        set_("H2", get("H2") - extent)
        set_("O2", get("O2") - extent / 2.0)
        set_("H2O", get("H2O") + extent)

    # N2O → N2 + ½ O2
    if get("N2O") > 0:
        extent = get("N2O")
        set_("N2O", 0.0)
        set_("N2", get("N2") + extent)
        set_("O2", get("O2") + extent / 2.0)

    # O3 → 3/2 O2
    if get("O3") > 0:
        extent = get("O3")
        set_("O3", 0.0)
        set_("O2", get("O2") + 1.5 * extent)

    # CO + ½ O2 → CO2
    if get("CO") > 0 and get("O2") > 0:
        extent = min(get("CO"), get("O2") * 2.0)
        set_("CO", get("CO") - extent)
        set_("O2", get("O2") - extent / 2.0)
        set_("CO2", get("CO2") + extent)

    return comp


def compute_equilibrium_composition(
    actual_composition: dict[str, float],
    temperature_k: float,
    pressure_bar: float = 1.0,  # noqa: ARG001
) -> dict[str, float]:
    """Compute thermodynamic equilibrium composition.

    Minimizes G = Σᵢ nᵢμᵢ subject to elemental conservation constraints.
    Uses scipy.optimize.minimize with elemental balance constraints.

    This is a constrained optimization:
    - Objective: minimize G(x₁, ..., xₙ)
    - Constraints: Σᵢ aᵢⱼ xᵢ = bⱼ for each element j (C, H, O, N, S)
    - Bounds: xᵢ ≥ 0 for all species

    Key improvements over naive SLSQP:
    1. Expand species list with potential reaction products (CO2, H2O, SO2)
       so the optimizer has room to transfer atoms between species.
    2. Use a pre-reacted starting point (known spontaneous reactions driven to
       completion) so the optimizer starts near the true equilibrium.
    3. Skip constraints for elements that appear in only one species (those
       species are fixed by stoichiometry and create overdetermined systems).
    """
    from scipy.optimize import minimize

    # ── Expand species list with potential reaction products ──────────────────
    # These sink species allow the optimizer to convert reactive pairs to stable
    # products (e.g., CH4 + O2 → CO2 + H2O).
    expanded = dict(actual_composition)
    elemental_budget_check: dict[str, float] = {}
    for sp, x in actual_composition.items():
        if sp not in MU_STANDARD:
            continue
        for el, cnt in ELEMENTAL_COMP.get(sp, {}).items():
            elemental_budget_check[el] = elemental_budget_check.get(el, 0.0) + x * cnt

    # Add CO2 if both C and O are in the budget but CO2 isn't present
    if elemental_budget_check.get("C", 0) > 0 and elemental_budget_check.get("O", 0) > 0 and "CO2" not in expanded:
        expanded["CO2"] = 1e-30
    # Add H2O if both H and O are in the budget but H2O isn't present
    if elemental_budget_check.get("H", 0) > 0 and elemental_budget_check.get("O", 0) > 0 and "H2O" not in expanded:
        expanded["H2O"] = 1e-30
    # Add SO2 if both S and O are in the budget but SO2 isn't present
    if elemental_budget_check.get("S", 0) > 0 and elemental_budget_check.get("O", 0) > 0 and "SO2" not in expanded:
        expanded["SO2"] = 1e-30

    species_list = [s for s in expanded if s in MU_STANDARD]
    n_species = len(species_list)

    if n_species == 0:
        return {}

    # ── Compute elemental budget ──────────────────────────────────────────────
    elements = set()
    for sp in species_list:
        elements.update(ELEMENTAL_COMP.get(sp, {}).keys())
    elements = sorted(elements)

    element_budget: dict[str, float] = dict.fromkeys(elements, 0.0)
    for sp in species_list:
        x = actual_composition.get(sp, 0.0)
        for el, count in ELEMENTAL_COMP.get(sp, {}).items():
            element_budget[el] += x * count

    # ── Only constrain elements that appear in ≥ 2 species ───────────────────
    # Elements that appear in only 1 species create redundant constraints that
    # over-specify the problem and cause SLSQP to report "more equality
    # constraints than independent variables".
    element_species_count: dict[str, int] = {}
    for el in elements:
        count = sum(1 for sp in species_list if ELEMENTAL_COMP.get(sp, {}).get(el, 0) > 0)
        element_species_count[el] = count

    active_elements = [el for el in elements
                       if element_budget.get(el, 0) > 0 and element_species_count[el] >= 2]

    # ── Objective: Gibbs energy ───────────────────────────────────────────────
    def gibbs_objective(x_vec: np.ndarray) -> float:
        g = 0.0
        for i, sp in enumerate(species_list):
            xi = max(x_vec[i], 1e-30)
            mu = MU_STANDARD[sp] * 1000  # J/mol
            g += xi * (mu + R * temperature_k * math.log(xi))
        return g

    # ── Constraints: elemental conservation ──────────────────────────────────
    constraints = []
    for el in active_elements:
        def make_constraint(element: str, budget: float):
            def constraint_func(x_vec: np.ndarray) -> float:
                total = 0.0
                for i, sp in enumerate(species_list):
                    total += x_vec[i] * ELEMENTAL_COMP.get(sp, {}).get(element, 0)
                return total - budget
            return {"type": "eq", "fun": constraint_func}
        constraints.append(make_constraint(el, element_budget[el]))

    # ── Starting point: pre-reacted composition ───────────────────────────────
    prereacted = _prereact_composition(expanded)
    x0 = np.array([max(prereacted.get(sp, 1e-30), 1e-30) for sp in species_list])

    # Bounds: all mixing ratios ≥ 0
    bounds = [(1e-30, 1.0) for _ in species_list]

    # ── Optimization: try multiple starting points ────────────────────────────
    best_result = None
    best_g = float("inf")

    starting_points = [
        x0,  # pre-reacted
        np.array([max(actual_composition.get(sp, 1e-30), 1e-30) for sp in species_list]),  # actual
    ]

    for x_start in starting_points:
        result = minimize(
            gibbs_objective, x_start, method="SLSQP",
            bounds=bounds, constraints=constraints,
            options={"maxiter": 2000, "ftol": 1e-14},
        )
        if result.fun < best_g:
            best_g = result.fun
            best_result = result
        if result.success:
            break

    if best_result is not None and best_result.success:
        return {sp: max(float(best_result.x[i]), 0.0) for i, sp in enumerate(species_list)}
    # Fallback: use pre-reacted composition as "equilibrium estimate"
    # This is physically more meaningful than returning the actual composition
    # (which would give ΔG = 0).
    if best_result is not None and best_result.fun < gibbs_objective(x0):
        logger.warning("equilibrium_optimization_partial", message=getattr(best_result, "message", ""))
        return {sp: max(float(best_result.x[i]), 0.0) for i, sp in enumerate(species_list)}
    logger.warning("equilibrium_optimization_failed_using_prereacted",
                   message=getattr(best_result, "message", "unknown"))
    return {sp: prereacted.get(sp, 0.0) for sp in species_list}


def compute_disequilibrium(
    mixing_ratios: dict[str, float],
    temperature_k: float,
    pressure_bar: float = 1.0,
) -> DisequilibriumResult:
    """Compute the thermodynamic disequilibrium of an atmosphere.

    ΔG_diseq = G_actual - G_equilibrium

    Large negative ΔG → strong disequilibrium → possible biosignature.
    Earth: ≈ -2326 J/mol. Mars: ≈ -4 J/mol. Venus: ≈ -0.2 J/mol.

    Args:
        mixing_ratios: Observed atmospheric composition {species: mole_fraction}.
        temperature_k: Mean atmospheric temperature (K).
        pressure_bar: Surface pressure (bar).

    Returns:
        DisequilibriumResult with ΔG, classification, and interpretation.
    """
    g_actual = compute_gibbs_energy(mixing_ratios, temperature_k)

    eq_composition = compute_equilibrium_composition(
        mixing_ratios, temperature_k, pressure_bar
    )

    g_equilibrium = compute_gibbs_energy(eq_composition, temperature_k)

    # ΔG = G_equilibrium - G_actual  # noqa: ERA001
    # Negative = actual is ABOVE equilibrium = disequilibrium (convention from Krissansen-Totton 2016)
    # Large negative ΔG → strong disequilibrium → possible biosignature.
    # Note: our model uses 298K chemical potentials; results at extreme T/P (Venus, Mars)
    # are qualitative only.
    delta_g = g_equilibrium - g_actual

    # Earth reference
    earth_delta_g = -2326.0  # Krissansen-Totton et al. 2016 ApJ 817 31: ΔG_diseq(Earth) = -2326 J/mol
    earth_ratio = abs(delta_g) / abs(earth_delta_g) if earth_delta_g != 0 else 0

    # Classification thresholds — Krissansen-Totton 2016 ApJ 817 31: Earth ≈ 2326 J/mol (strong),
    # Mars ≈ 4 J/mol (near-equilibrium), Venus ≈ 0.2 J/mol (near-equilibrium)
    abs_dg = abs(delta_g)
    if abs_dg > 1000:  # ESTIMATE — >1000 J/mol → "strong" (approaching Earth level)
        classification = "strong_disequilibrium"
    elif abs_dg > 100:  # ESTIMATE — 100-1000 J/mol → "moderate" (Krissansen-Totton 2016 scale)
        classification = "moderate_disequilibrium"
    elif abs_dg > 10:   # ESTIMATE — 10-100 J/mol → "weak" (above Mars, below ~1% Earth)
        classification = "weak_disequilibrium"
    else:               # ESTIMATE — <10 J/mol → near-equilibrium (Mars/Venus class)
        classification = "near_equilibrium"

    # Interpretation
    parts = [f"ΔG = {delta_g:.1f} J/mol ({delta_g/1000:.2f} kJ/mol)."]

    if classification == "strong_disequilibrium":
        parts.append(
            f"This atmosphere is in STRONG thermodynamic disequilibrium "
            f"({earth_ratio:.1%} of Earth's disequilibrium). "
            f"On Earth, this level is maintained by biological activity (photosynthesis + methanogenesis)."
        )
    elif classification == "moderate_disequilibrium":
        parts.append(
            "Moderate disequilibrium — could indicate biological activity, "
            "but geological processes (volcanism, photochemistry) can also produce this level."
        )
    elif classification == "weak_disequilibrium":
        parts.append(
            "Weak disequilibrium — consistent with abiotic photochemistry. "
            "Not strong evidence for biology."
        )
    else:
        parts.append(
            "Near thermodynamic equilibrium — no evidence for biological activity "
            "from atmospheric chemistry alone."
        )

    return DisequilibriumResult(
        delta_g_j_per_mol=delta_g,
        delta_g_kj_per_mol=delta_g / 1000,
        g_actual=g_actual,
        g_equilibrium=g_equilibrium,
        classification=classification,
        earth_comparison=earth_ratio,
        interpretation=" ".join(parts),
        actual_composition=mixing_ratios,
        equilibrium_composition=eq_composition,
    )


# ── Reference atmospheres for validation ───────────────────────────

# Earth atmosphere — Seinfeld & Pandis 2016 "Atmospheric Chemistry and Physics" Table 1.1
EARTH_ATMOSPHERE: dict[str, float] = {
    "N2":  0.7808,   # Seinfeld & Pandis 2016 Table 1.1: N2 = 78.08%
    "O2":  0.2095,   # Seinfeld & Pandis 2016 Table 1.1: O2 = 20.95%
    "H2O": 0.01,     # ESTIMATE — global mean ~1% (Trenberth 2007 J Clim 20 1295)
    "CO2": 4.2e-4,   # NOAA GML 2024: CO2 ≈ 420 ppm (updated from 2016 baseline)
    "CH4": 1.9e-6,   # NOAA GML 2024: CH4 ≈ 1920 ppb
    "N2O": 3.3e-7,   # NOAA GML 2024: N2O ≈ 335 ppb
    "O3":  1e-5,     # ESTIMATE — stratospheric peak ~10 ppm (WMO 2022 Ozone Assessment)
    "H2":  5.5e-7,   # Novelli 1999 J Geophys Res 104 30427: global mean H2 ≈ 550 ppb
}

# Mars atmosphere — Mahaffy 2013 Science 341 263 (SAM/MSL); Owen 1977 J Geophys Res 82 4635
MARS_ATMOSPHERE: dict[str, float] = {
    "CO2": 0.953,     # Mahaffy 2013 Science 341 263: CO2 = 95.3%
    "N2":  0.027,     # Mahaffy 2013: N2 = 2.7%
    "O2":  0.0013,    # Mahaffy 2013: O2 = 0.13%
    "CO":  8e-4,      # Mahaffy 2013: CO = 800 ppm
    "H2O": 2e-4,      # ESTIMATE — seasonal mean ~200 ppm (Smith 2004 Icarus 167 148)
    "CH4": 4.1e-10,   # Webster 2015 Science 347 415: Curiosity TLS 0.41 ppb background
}

# Venus atmosphere — Seiff 1985 Adv Space Res 5 3 (Pioneer Venus); Hoffman 1980 Science 205 49
VENUS_ATMOSPHERE: dict[str, float] = {
    "CO2": 0.965,    # Seiff 1985: CO2 = 96.5%
    "N2":  0.035,    # Seiff 1985: N2 = 3.5%
    "SO2": 1.5e-4,   # Hoffman 1980 Science 205 49: SO2 = 130-185 ppm (average ~150 ppm)
    "H2O": 3e-5,     # ESTIMATE — cloud-deck region ~30 ppm; Marcq 2008 J Geophys Res 113 E00B07
    "CO":  2e-5,     # Seiff 1985: CO ≈ 20 ppm below clouds
}
