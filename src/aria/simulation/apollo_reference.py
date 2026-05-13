"""Apollo program reference data — the ground-truth Δv / timing / landing
coordinates for every crewed lunar mission.

Sources (all public-domain NASA publications):

  - NASA SP-4029 (Orloff 2000) "Apollo by the Numbers: A Statistical
    Reference for the Apollo Mission Set."
  - NASA MSC-04112 Apollo 11 Mission Report.
  - NASA NSSDCA Apollo landing-site coordinates
    (https://nssdc.gsfc.nasa.gov/planetary/lunar/apolloloc.html)
  - NASA History Office SP-350 "Apollo Expeditions to the Moon" §mass.

ARIA's end-to-end Moon mission simulator (moon_mission_e2e.py) should
match these numbers within a few % at every phase. Larger divergences
mean the simulator has drifted from reality and needs attention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ApolloMission:
    number: int
    launch_date: str                # ISO
    crew_size: int
    commander: str
    landing_site: Optional[str] = None
    lat_deg: Optional[float] = None
    lon_deg: Optional[float] = None
    # Published Δv (all in m/s)
    tli_dv_mps: Optional[float] = None
    loi_dv_mps: Optional[float] = None
    descent_dv_mps: Optional[float] = None
    ascent_dv_mps: Optional[float] = None
    tei_dv_mps: Optional[float] = None
    # Masses (kg)
    launch_mass_kg: Optional[float] = None
    cm_splashdown_mass_kg: Optional[float] = None
    surface_stay_h: Optional[float] = None
    peak_entry_g: Optional[float] = None
    mission_duration_h: Optional[float] = None


# Source: NASA SP-4029 (Orloff 2000), cross-checked with NSSDCA.
APOLLO_MISSIONS: List[ApolloMission] = [
    ApolloMission(
        number=8, launch_date="1968-12-21", crew_size=3,
        commander="Frank Borman",
        landing_site=None, lat_deg=None, lon_deg=None,
        tli_dv_mps=3143.0, loi_dv_mps=918.0,
        tei_dv_mps=1056.0, descent_dv_mps=None, ascent_dv_mps=None,
        launch_mass_kg=28_870.0, cm_splashdown_mass_kg=5_621.0,
        surface_stay_h=0.0, peak_entry_g=6.8, mission_duration_h=147.0,
    ),
    ApolloMission(
        number=11, launch_date="1969-07-16", crew_size=3,
        commander="Neil Armstrong",
        landing_site="Sea of Tranquility", lat_deg=0.67, lon_deg=23.49,
        tli_dv_mps=3131.0, loi_dv_mps=897.9,
        descent_dv_mps=2040.0, ascent_dv_mps=1845.0,
        tei_dv_mps=1076.0,
        launch_mass_kg=28_801.0, cm_splashdown_mass_kg=5_559.0,
        surface_stay_h=21.6, peak_entry_g=6.9, mission_duration_h=195.3,
    ),
    ApolloMission(
        number=12, launch_date="1969-11-14", crew_size=3,
        commander="Charles Conrad",
        landing_site="Ocean of Storms", lat_deg=-3.01, lon_deg=-23.42,
        tli_dv_mps=3107.0, loi_dv_mps=889.0,
        descent_dv_mps=2060.0, ascent_dv_mps=1851.0,
        tei_dv_mps=1062.0,
        launch_mass_kg=28_849.0, cm_splashdown_mass_kg=5_520.0,
        surface_stay_h=31.6, peak_entry_g=6.3, mission_duration_h=244.6,
    ),
    ApolloMission(
        number=14, launch_date="1971-01-31", crew_size=3,
        commander="Alan Shepard",
        landing_site="Fra Mauro", lat_deg=-3.65, lon_deg=-17.47,
        tli_dv_mps=3143.0, loi_dv_mps=890.0,
        descent_dv_mps=2050.0, ascent_dv_mps=1845.0,
        tei_dv_mps=1050.0,
        launch_mass_kg=29_107.0, cm_splashdown_mass_kg=5_491.0,
        surface_stay_h=33.5, peak_entry_g=6.0, mission_duration_h=216.0,
    ),
    ApolloMission(
        number=15, launch_date="1971-07-26", crew_size=3,
        commander="David Scott",
        landing_site="Hadley-Apennine", lat_deg=26.13, lon_deg=3.63,
        tli_dv_mps=3170.0, loi_dv_mps=892.0,
        descent_dv_mps=2064.0, ascent_dv_mps=1854.0,
        tei_dv_mps=1041.0,
        launch_mass_kg=30_343.0, cm_splashdown_mass_kg=5_875.0,
        surface_stay_h=66.9, peak_entry_g=6.0, mission_duration_h=295.2,
    ),
    ApolloMission(
        number=16, launch_date="1972-04-16", crew_size=3,
        commander="John Young",
        landing_site="Descartes", lat_deg=-8.97, lon_deg=15.50,
        tli_dv_mps=3156.0, loi_dv_mps=895.0,
        descent_dv_mps=2067.0, ascent_dv_mps=1860.0,
        tei_dv_mps=1013.0,
        launch_mass_kg=30_354.0, cm_splashdown_mass_kg=5_840.0,
        surface_stay_h=71.1, peak_entry_g=6.5, mission_duration_h=265.9,
    ),
    ApolloMission(
        number=17, launch_date="1972-12-07", crew_size=3,
        commander="Eugene Cernan",
        landing_site="Taurus-Littrow", lat_deg=20.19, lon_deg=30.77,
        tli_dv_mps=3148.0, loi_dv_mps=899.0,
        descent_dv_mps=2062.0, ascent_dv_mps=1862.0,
        tei_dv_mps=1054.0,
        launch_mass_kg=30_352.0, cm_splashdown_mass_kg=5_840.0,
        surface_stay_h=74.9, peak_entry_g=6.8, mission_duration_h=301.8,
    ),
]


def get_mission(number: int) -> ApolloMission:
    for m in APOLLO_MISSIONS:
        if m.number == number:
            return m
    raise KeyError(f"Apollo {number} not in reference set")


def landed_missions() -> List[ApolloMission]:
    return [m for m in APOLLO_MISSIONS if m.landing_site]


def average_dv_budget() -> dict:
    landed = landed_missions()
    avg = lambda fn: sum(fn(m) or 0 for m in landed) / max(1, sum(1 for m in landed if fn(m) is not None))
    return {
        "tli_mean_mps":     avg(lambda m: m.tli_dv_mps),
        "loi_mean_mps":     avg(lambda m: m.loi_dv_mps),
        "descent_mean_mps": avg(lambda m: m.descent_dv_mps),
        "ascent_mean_mps":  avg(lambda m: m.ascent_dv_mps),
        "tei_mean_mps":     avg(lambda m: m.tei_dv_mps),
        "peak_entry_g":     avg(lambda m: m.peak_entry_g),
    }
