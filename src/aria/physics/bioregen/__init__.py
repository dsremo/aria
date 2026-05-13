"""MELiSSA-fidelity bioregenerative life-support model (TRL 4-6).

Bounded to **1-3 person scale**, matching the European Space Agency's
MELiSSA (Micro-Ecological Life Support System Alternative) pilot
plant in Barcelona, which is the most advanced operational closed-
loop bioregenerative life-support system on Earth.

This module replaces the earlier ECLSS overclaim ("100% food self-
sufficiency at 100 crew via ring agriculture") with a real,
citation-grade compartment model bounded to actual TRL 4-6
fidelity. Earlier banner is retired; this is the authoritative
model.

Compartments (MELiSSA architecture, after Lasseur 2010):

  C-I    Liquefying — Thermoanaerobacterium thermosaccharolyticum,
         55 °C anaerobic; converts crew waste + food waste to
         volatile fatty acids (VFAs).
  C-II   Photoheterotrophic — Rhodospirillum rubrum (purple non-
         sulfur bacteria); consumes VFAs in light, produces NH4.
  C-III  Nitrification — Nitrosomonas + Nitrobacter; oxidises NH4
         → NO2 → NO3.
  C-IV-A Higher plants — lettuce, beet, wheat; uptake NO3 + CO2,
         produce O2 + edible biomass (Photosynthetic Photon Flux
         Density driven).
  C-IV-B Spirulina (Arthrospira platensis) — secondary photo-
         autotroph; also CO2 → O2 + edible biomass.
  C-V    Crew — 1-3 humans, metabolic loads from NASA BVAD.

What this module does NOT do:

  * It does not simulate cell-level metabolism (no Doyle-Fuller-
    Newman-equivalent for microbes).
  * It does not predict yield instability under upset conditions
    (real MELiSSA experiments show this is hard).
  * It does not include compartment-to-compartment transport delays
    (treated as steady-state mass balance only).
  * It does not do nutrient micro-balance (Fe, Mg, K, etc.) — only
    the macro fluxes (C, N, O, H2O).
  * It does not model atmospheric trace contaminants.

Citations are inline per CLAUDE.md mandate.

Sources:

  * Lasseur et al. 2010 'MELiSSA: the European project of closed
    life support system' Gravitational and Space Biology 23(2): 3-12.
  * Hendrickx et al. 2006 'Microbial ecology of the closed artificial
    ecosystem MELiSSA' Research in Microbiology 157(1): 77-86.
  * Godia et al. 2002 'MELiSSA: a loop of interconnected bioreactors'
    Journal of Biotechnology 99(3): 319-330.
  * NASA TP-2015-218570 'Baseline Values and Assumptions Document'
    (BVAD) for crew metabolic loads.
  * ESA MELiSSA Pilot Plant Annual Reports 2009-2024 (Barcelona).
  * Czerny 2024 'Critical investments in bioregenerative life
    support systems' PMC12357894 (review of BLSS state-of-art).
"""

__all__ = (
    "Crew",
    "CompartmentI",
    "CompartmentII",
    "CompartmentIII",
    "CompartmentIVA",
    "CompartmentIVB",
    "MELiSSALoop",
    "LoopBalance",
    "MAX_VALIDATED_CREW",
)


from aria.physics.bioregen.crew import Crew, MAX_VALIDATED_CREW
from aria.physics.bioregen.compartments import (
    CompartmentI,
    CompartmentII,
    CompartmentIII,
    CompartmentIVA,
    CompartmentIVB,
)
from aria.physics.bioregen.flows import MELiSSALoop, LoopBalance
