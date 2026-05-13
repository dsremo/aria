"""Vendor cell-level Electrical Power System models.

Replaces ARIA's single-Isp / single-efficiency power numbers with
real cell-level fidelity drawn from published vendor datasheets:

  * Solar cells — Spectrolab XTJ-Prime, Azur Space 3G30A
    (triple-junction GaInP/GaInAs/Ge; 29.5–30 % BOL)
  * Lithium-ion batteries — Saft VES180 (50 Ah, 180 Wh, the
    canonical space Li-ion cell flown on dozens of LEO + GEO
    spacecraft)

Used by:
  * aria.agents.power — replaces parametric defaults
  * aria.simulation.* — high-fidelity orbit-power profiles
  * aria.products.cubesat_deorbit — realistic battery health margin
"""
