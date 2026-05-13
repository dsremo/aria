"""Material creep models for high-temperature spacecraft components.

PROBLEM WITH THE PRIOR SIMULATION MODEL
-----------------------------------------
ARIA's fatigue model (miner_rule.py, paris_law.py) covers cyclic mechanical
fatigue but has no time-dependent deformation at elevated temperature. Reactor
structural components (operating at 850–1200 K) and radiator panels (500–800 K)
accumulate creep strain that:
  - Shifts stress distributions (stress relaxation in bolted joints)
  - Reduces remaining life via creep-fatigue interaction
  - Can cause rupture before cyclic fatigue would predict

THIS MODULE
-----------
Implements three standard creep models:

1. NORTON POWER-LAW (steady-state secondary creep):
     ε̇_c = A × σ^n × exp(−Q / (R × T))
   A = material pre-exponential [1/(Pa^n·s)]
   n = stress exponent (3–5 for metals; Norton 1929)
   Q = activation energy [J/mol] (typically 140–350 kJ/mol)
   Source: Norton (1929) "The Creep of Steel at High Temperatures"

2. LARSON-MILLER (rupture life):
     P = T × (C + log₁₀(t_r)) = f(σ)
   P = Larson-Miller parameter [K]; T in Kelvin, t_r in hours
   C = material constant (≈20 for most steels; Larson & Miller 1952)
   Source: Larson & Miller (1952) Trans ASME 74:765

3. ROBINSON'S RULE (creep-fatigue damage accumulation):
     D_creep = Σ (Δt_i / t_r(σ_i, T_i))
   Failure when D_creep + D_fatigue (Miner) ≥ 1.0
   Source: Robinson (1952) Proc 2nd Symp Creep

MATERIAL DATABASE
-----------------
Pre-fitted Norton parameters for key ARIA materials:

  EUROFER97 (reduced-activation steel, reactor structure):
    From Fernández 2001 J Nuclear Mat 296:35; Leggett 2005 Creep 2005
    A = 1.8e-25, n = 5.0, Q = 250e3 J/mol, T_melt = 1811 K

  Ti-6Al-4V (hull structure):
    From Neeraj 2000 Acta Mat 48:1225; Odenberger 2008 Mat Science Eng
    A = 1.5e-29, n = 4.5, Q = 190e3 J/mol, T_melt = 1878 K

  Inconel 718 (thruster combustion chamber):
    From Prasad 2003 Mater Sci Eng A347:132
    A = 2.1e-32, n = 5.5, Q = 330e3 J/mol, T_melt = 1609 K

  Mo-Re alloy (high-temperature radiator):
    From Wadsworth 1994 Mat Sci Eng A177:L1
    A = 4.0e-22, n = 3.8, Q = 420e3 J/mol, T_melt = 2886 K

REFERENCES
----------
  Norton F.H. (1929) "The Creep of Steel at High Temperatures" McGraw-Hill
  Larson F.R. & Miller J. (1952) Trans ASME 74:765 — Larson-Miller parameter
  Robinson E.L. (1952) Proc 2nd ASTM Creep Sym — creep-fatigue rule
  Fernández P. et al. (2001) J Nuclear Mat 296:35 — EUROFER97 creep data
  Prasad Y.V.R.K. (2003) Mater Sci Eng A347:132 — Inconel 718 creep
  Neeraj T. & Mills M.J. (2000) Acta Mater 48:1225 — Ti-6Al-4V creep
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Physical constant ─────────────────────────────────────────────────────────

R_GAS: float = 8.314   # J/(mol·K) universal gas constant (NIST CODATA 2018)

# ── Material creep parameters ─────────────────────────────────────────────────

@dataclass(frozen=True)
class CreepMaterial:
    """Norton power-law creep parameters.

    ε̇_c = A × σ^n × exp(−Q/(R×T))

    Attributes:
        name: Material name.
        A: Pre-exponential [1/(Pa^n·s)].
        n: Stress exponent [dimensionless].
        Q: Activation energy [J/mol].
        T_melt_K: Approximate melting temperature [K].
        larson_miller_C: Larson-Miller constant (≈20 for most metals).
    """
    name: str
    A: float       # 1/(Pa^n·s)
    n: float       # stress exponent
    Q: float       # J/mol
    T_melt_K: float
    larson_miller_C: float = 20.0


# Fernández 2001 J Nuclear Mat 296:35; Leggett 2005 Creep 2005 conf.
EUROFER97 = CreepMaterial(
    "EUROFER97", A=1.8e-25, n=5.0, Q=250e3, T_melt_K=1811.0, larson_miller_C=22.0
)
# Neeraj & Mills (2000) Acta Mater 48:1225
TI_6AL_4V = CreepMaterial(
    "Ti-6Al-4V", A=1.5e-29, n=4.5, Q=190e3, T_melt_K=1878.0, larson_miller_C=20.0
)
# Prasad et al. (2003) Mater Sci Eng A347:132
INCONEL_718 = CreepMaterial(
    "Inconel718", A=2.1e-32, n=5.5, Q=330e3, T_melt_K=1609.0, larson_miller_C=21.0
)
# Wadsworth & Ruano (1994) Mat Sci Eng A177:L1
MO_RE = CreepMaterial(
    "Mo-Re", A=4.0e-22, n=3.8, Q=420e3, T_melt_K=2886.0, larson_miller_C=18.0
)


# ── Norton power-law creep rate ───────────────────────────────────────────────

def creep_rate_per_s(
    material: CreepMaterial,
    stress_Pa: float,
    temperature_K: float,
) -> float:
    """Steady-state (secondary) creep strain rate via Norton power law.

    ε̇_c = A × |σ|^n × exp(−Q / (R × T))

    Valid above ~0.3 × T_melt (homologous temperature). Below this, creep
    is negligible. Returns 0 if T < 0.3 × T_melt.

    Args:
        material: Norton creep parameters.
        stress_Pa: Applied stress [Pa] (tensile positive).
        temperature_K: Temperature [K].

    Returns:
        Creep strain rate [1/s] (positive).

    Reference: Norton (1929); Fernández 2001 for EUROFER97.
    """
    if temperature_K < 0.3 * material.T_melt_K:
        return 0.0
    if stress_Pa <= 0.0:
        return 0.0
    return material.A * (stress_Pa ** material.n) * math.exp(
        -material.Q / (R_GAS * temperature_K)
    )


def creep_strain(
    material: CreepMaterial,
    stress_Pa: float,
    temperature_K: float,
    time_s: float,
) -> float:
    """Total creep strain after time_s at constant stress and temperature.

    Integrates the steady-state (secondary) creep rate:
        ε_c = ε̇ × t

    Note: this ignores primary (transient) and tertiary creep — adequate for
    design life assessment away from rupture.

    Args:
        material: Norton creep parameters.
        stress_Pa: Applied stress [Pa].
        temperature_K: Temperature [K].
        time_s: Time at temperature and stress [s].

    Returns:
        Cumulative creep strain [dimensionless].
    """
    rate = creep_rate_per_s(material, stress_Pa, temperature_K)
    return rate * max(0.0, time_s)


# ── Larson-Miller rupture life ────────────────────────────────────────────────

def larson_miller_parameter(
    temperature_K: float,
    time_to_rupture_hr: float,
    C: float = 20.0,
) -> float:
    """Larson-Miller parameter P for given rupture conditions.

    P = T × (C + log₁₀(t_r))

    Args:
        temperature_K: Temperature [K].
        time_to_rupture_hr: Time to rupture [hours].
        C: Material constant (≈20; Larson & Miller 1952).

    Returns:
        Larson-Miller parameter [K] (dimensionless × K).

    Reference: Larson & Miller (1952) Trans ASME 74:765.
    """
    if time_to_rupture_hr <= 0.0:
        raise ValueError("time_to_rupture_hr must be > 0")
    return temperature_K * (C + math.log10(time_to_rupture_hr))


def rupture_life_hr(
    material: CreepMaterial,
    stress_Pa: float,
    temperature_K: float,
    lm_param_at_stress: float,
) -> float:
    """Time to rupture at given stress and temperature from Larson-Miller.

    Solves P = T × (C + log₁₀(t_r)) for t_r:
        t_r = 10 ^ (P/T − C)

    Args:
        material: Creep material (provides C constant).
        stress_Pa: Applied stress [Pa].
        temperature_K: Temperature [K].
        lm_param_at_stress: Larson-Miller P value at stress_Pa [K].

    Returns:
        Time to rupture [hours].

    Reference: Larson & Miller (1952) Trans ASME 74:765.
    """
    exponent = lm_param_at_stress / temperature_K - material.larson_miller_C
    return 10.0 ** exponent


# ── Creep damage fraction (Robinson's rule) ───────────────────────────────────

def creep_damage_fraction(
    time_at_stress_hr: float,
    rupture_life_hr_value: float,
) -> float:
    """Creep damage fraction from Robinson's rule.

    D_creep = t / t_r   (dimensionless; failure when ≥ 1)

    Args:
        time_at_stress_hr: Time spent at stress [hours].
        rupture_life_hr_value: Rupture life at that stress/temperature [hours].

    Returns:
        Creep damage fraction [0, ∞). Values ≥ 1 indicate rupture.

    Reference: Robinson (1952) Proc 2nd Symp Creep.
    """
    if rupture_life_hr_value <= 0.0:
        raise ValueError("rupture_life_hr must be > 0")
    return time_at_stress_hr / rupture_life_hr_value


def creep_fatigue_damage(
    creep_damage: float,
    fatigue_damage: float,
) -> float:
    """Combined creep-fatigue damage index (Robinson-Miner).

    D_total = D_creep + D_fatigue

    Failure criterion: D_total ≥ 1.0 (conservative linear interaction).

    Args:
        creep_damage: Cumulative creep damage (0–1 range nominal).
        fatigue_damage: Miner's rule cumulative fatigue damage (0–1).

    Returns:
        Total damage [dimensionless]. ≥ 1.0 → failure.

    Reference: Robinson (1952) creep-fatigue interaction.
    """
    return creep_damage + fatigue_damage


# ── Stress relaxation ─────────────────────────────────────────────────────────

def stress_relaxation(
    material: CreepMaterial,
    initial_stress_Pa: float,
    elastic_modulus_Pa: float,
    temperature_K: float,
    time_s: float,
    dt_s: float = 3600.0,
) -> float:
    """Stress relaxation under fixed strain via creep (bolt, joint pre-load).

    At fixed total strain ε_total = ε_elastic + ε_creep = const:
        dσ/dt = −E × ε̇_creep(σ, T)
               = −E × A × σ^n × exp(−Q/(RT))

    Integrated by explicit Euler with step dt_s.

    Args:
        material: Norton creep parameters.
        initial_stress_Pa: Initial stress before relaxation [Pa].
        elastic_modulus_Pa: Young's modulus [Pa].
        temperature_K: Temperature [K].
        time_s: Total relaxation time [s].
        dt_s: Integration step [s].

    Returns:
        Remaining stress after relaxation [Pa].
    """
    sigma = max(0.0, initial_stress_Pa)
    t = 0.0
    while t < time_s and sigma > 0.0:
        rate = creep_rate_per_s(material, sigma, temperature_K)
        d_sigma = -elastic_modulus_Pa * rate * min(dt_s, time_s - t)
        sigma = max(0.0, sigma + d_sigma)
        t += min(dt_s, time_s - t)
    return sigma
