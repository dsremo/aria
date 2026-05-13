"""Historical solar proton event catalog — the biggest events on record.

Sources (all published peer-reviewed data):

  - Shea & Smart (1990) "A summary of major solar proton events,"
      Solar Physics 127(2):297 — Apollo-era events.
  - Reames, D. V. (1999) "Particle acceleration at the Sun and in the
      heliosphere," Space Sci. Rev. 90:413.
  - Reames, D. V. (2015) "What are the sources of solar energetic
      particles?" Space Sci. Rev. 194:303.
  - Mewaldt, R. A. et al. (2005) "Proton, helium, and electron spectra,"
      JGR 110:A09S18.
  - NOAA SWPC SEP Archive (public)
  - Jiggens, P. et al. (2012) "ESA SEPEM reference data set,"
      Space Weather 10(S03003).

Each entry lists the reported peak proton flux at >10 MeV and the
integrated fluence (cumulative particles per cm² above 10 MeV) as the
two parameters most relevant for EVA dose calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SPEEvent:
    date: str                      # ISO format
    peak_flux_pfu: float           # >10 MeV pfu
    fluence_per_cm2: float         # integrated >10 MeV
    duration_hours: float
    classification: str            # Reames event class: "gradual" / "impulsive"
    assoc_flare_class: str         # X-class flare association
    reference: str


# Historical catalog — 17 major events, chronological order.
MAJOR_SPES: List[SPEEvent] = [
    SPEEvent("1956-02-23", peak_flux_pfu=5_000.0, fluence_per_cm2=1.0e9,
             duration_hours=48.0, classification="gradual",
             assoc_flare_class="?", reference="Meyer & Parker 1956 Phys.Rev.104:768"),
    SPEEvent("1972-08-04", peak_flux_pfu=46_000.0, fluence_per_cm2=1.0e10,
             duration_hours=72.0, classification="gradual",
             assoc_flare_class="X5", reference="Shea & Smart 1990 SolPhys127:297"),
    SPEEvent("1989-08-12", peak_flux_pfu=15_000.0, fluence_per_cm2=5.5e9,
             duration_hours=48.0, classification="gradual",
             assoc_flare_class="X4.5", reference="Reames 1999 SSRv90:413"),
    SPEEvent("1989-10-19", peak_flux_pfu=40_000.0, fluence_per_cm2=1.3e10,
             duration_hours=96.0, classification="gradual",
             assoc_flare_class="X13", reference="Reames 1999 SSRv90:413"),
    SPEEvent("1991-06-15", peak_flux_pfu=2_000.0, fluence_per_cm2=1.0e9,
             duration_hours=48.0, classification="gradual",
             assoc_flare_class="X12", reference="Cliver 2004 JASTP66:1229"),
    SPEEvent("2000-07-14", peak_flux_pfu=24_000.0, fluence_per_cm2=5.0e9,
             duration_hours=72.0, classification="gradual",
             assoc_flare_class="X5.7", reference="Mewaldt 2005 JGR110:A09S18  (Bastille Day event)"),
    SPEEvent("2001-11-04", peak_flux_pfu=31_700.0, fluence_per_cm2=1.0e10,
             duration_hours=96.0, classification="gradual",
             assoc_flare_class="X1.0", reference="Mewaldt 2005 JGR110:A09S18"),
    SPEEvent("2003-10-28", peak_flux_pfu=29_500.0, fluence_per_cm2=1.5e10,
             duration_hours=120.0, classification="gradual",
             assoc_flare_class="X17.2", reference="Mewaldt 2005 — Halloween storms start"),
    SPEEvent("2003-10-29", peak_flux_pfu=2_300.0, fluence_per_cm2=1.0e9,
             duration_hours=24.0, classification="gradual",
             assoc_flare_class="X10", reference="Mewaldt 2005 — Halloween peak 2"),
    SPEEvent("2003-11-02", peak_flux_pfu=1_570.0, fluence_per_cm2=8.0e8,
             duration_hours=24.0, classification="gradual",
             assoc_flare_class="X8.3", reference="Mewaldt 2005"),
    SPEEvent("2005-01-20", peak_flux_pfu=1_860.0, fluence_per_cm2=6.0e8,
             duration_hours=36.0, classification="gradual",
             assoc_flare_class="X7.1", reference="Mewaldt 2005"),
    SPEEvent("2006-12-13", peak_flux_pfu=700.0, fluence_per_cm2=3.0e8,
             duration_hours=48.0, classification="gradual",
             assoc_flare_class="X3.4", reference="SWPC archive"),
    SPEEvent("2012-03-07", peak_flux_pfu=6_530.0, fluence_per_cm2=4.0e9,
             duration_hours=72.0, classification="gradual",
             assoc_flare_class="X5.4", reference="Lario 2013 ApJ767:41"),
    SPEEvent("2017-09-10", peak_flux_pfu=1_490.0, fluence_per_cm2=7.0e8,
             duration_hours=72.0, classification="gradual",
             assoc_flare_class="X8.2", reference="Luhmann 2018 SWJ16:354"),
    SPEEvent("2022-01-29", peak_flux_pfu=78.0, fluence_per_cm2=1.0e8,
             duration_hours=24.0, classification="gradual",
             assoc_flare_class="M1.1", reference="SWPC archive"),
    SPEEvent("2024-05-11", peak_flux_pfu=1_000.0, fluence_per_cm2=5.0e8,
             duration_hours=72.0, classification="gradual",
             assoc_flare_class="X5.8", reference="SWPC May 2024 storm"),
    SPEEvent("2024-10-09", peak_flux_pfu=2_300.0, fluence_per_cm2=1.5e9,
             duration_hours=72.0, classification="gradual",
             assoc_flare_class="X1.8", reference="SWPC October 2024 storm"),
]


def events_in_range(start: str, end: str) -> List[SPEEvent]:
    """Return SPEs with date within [start, end] ISO strings."""
    return [e for e in MAJOR_SPES if start <= e.date <= end]


def worst_case_fluence_per_cm2(mission_years: float) -> float:
    """Estimated worst-case >10 MeV proton fluence for a mission of
    the given duration, assuming one August-1972-class event per 11-yr
    solar cycle.
    """
    cycles_spanned = mission_years / 11.0
    # Take the 2 largest events in the catalog to bound the worst case
    big_events = sorted(MAJOR_SPES, key=lambda e: -e.fluence_per_cm2)[:2]
    base = sum(e.fluence_per_cm2 for e in big_events) / 2
    return base * max(1.0, cycles_spanned)


def total_fluence_in_catalog() -> float:
    """Sum of integrated proton fluences across all catalogued events."""
    return sum(e.fluence_per_cm2 for e in MAJOR_SPES)
