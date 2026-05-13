"""Pod D1 — Magnetohydrodynamics and fusion-reactor plasma physics.

Implements audit items §7.1-§7.19 (plasma fluid equations, MHD
instabilities, disruptions, neoclassical transport, ELMs, Alfvén
eigenmodes, runaway electrons, etc.).

**P1 scope (this commit):** closed-form analytic primitives that
every fusion-reactor design evaluation needs, anchored to ITER
Physics Basis 1999 and the canonical textbooks:

  - Plasma-physics constants (CODATA 2018, SI 2019 exact)
  - Alfvén speed and ideal-MHD characteristic timescales
  - Ion gyroradius and plasma beta
  - Spitzer resistivity (Wesson 2011 Tokamaks 4th ed)
  - Kruskal-Shafranov ideal-kink limit (q_a ≥ 1)
  - Greenwald density limit (Greenwald 2002 PPCF 44 R27)
  - Troyon beta limit (Troyon 1984 PPCF 26 209)
  - Eich heat-flux width λ_q (Eich 2013 Nucl Fusion 53 093031)
  - Dreicer runaway field (Dreicer 1960 Phys Rev 117 329)
  - Rosenbluth-Putvinski runaway avalanche amplification
    (Rosenbluth & Putvinski 1997 Nucl Fusion 37 1355)

**Deferred:** 2D Grad-Shafranov solver, linearised ideal-MHD
eigenvalue problem, full neoclassical transport ODE, Sauter
bootstrap-current fit — these need a PDE library (SLEPc/PETSc or
similar) that is an optional heavy dependency.

See `docs/pods/D1_mhd_fusion.md` for the full scope note.

Public API:
    PlasmaConstants, PLASMA_CONSTANTS          — CODATA 2018 + SI 2019
    alfven_speed                               — v_A = B/√(μ₀ ρ)
    ion_gyroradius                             — ρ_i = m_i v_⊥ / (qB)
    plasma_beta                                — β = 2μ₀ p / B²
    spitzer_resistivity                        — η_Sp [Ω·m]
    kruskal_shafranov_limit_ok                 — q_a ≥ 1 check
    greenwald_density_limit                    — n_G = I_p / (π a²) [10²⁰ m⁻³]
    troyon_beta_limit                          — β_max = C_T I_p / (a B_T)
    eich_lambda_q                              — λ_q scaling law
    dreicer_field                              — E_D [V/m]
    rosenbluth_putvinski_avalanche             — N_RA / N_seed
    ITER_BASELINE                              — reference parameters
"""

from .constants import PLASMA_CONSTANTS, PlasmaConstants
from .ideal_mhd import (
    alfven_speed,
    ion_gyroradius,
    plasma_beta,
)
from .spitzer import spitzer_resistivity
from .limits import (
    ITER_BASELINE,
    ITERBaselineParameters,
    greenwald_density_limit,
    kruskal_shafranov_limit_ok,
    troyon_beta_limit,
)
from .eich import eich_lambda_q
from .runaway import (
    dreicer_field,
    rosenbluth_putvinski_avalanche,
)

__all__ = [
    "PLASMA_CONSTANTS",
    "PlasmaConstants",
    "alfven_speed",
    "ion_gyroradius",
    "plasma_beta",
    "spitzer_resistivity",
    "kruskal_shafranov_limit_ok",
    "greenwald_density_limit",
    "troyon_beta_limit",
    "ITER_BASELINE",
    "ITERBaselineParameters",
    "eich_lambda_q",
    "dreicer_field",
    "rosenbluth_putvinski_avalanche",
]
