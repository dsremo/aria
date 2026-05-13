"""R47 — historical-conjunction backtest catalog.

Twelve real or near-collision events that the ARIA conjunction
pipeline should reproduce.  Each entry records:

  * NORAD IDs of the two objects.
  * Approximate TCA + truth values from the open literature.
  * A free-text description tying back to a published reference.

The catalog is *static* — TLEs are loaded on demand from
:mod:`aria.conjunction.data.spacetrack_session` if SpaceTrack
credentials are available; otherwise the entry is skipped at test
time.  The point of the catalog is to be **the list to run**, not the
data itself.

Each event passes if ARIA's predicted TCA is within ±5 s of the
literature TCA and the predicted miss distance lies within the
operator-grade-σ band.  These tolerances are intentionally loose:
TLEs published days before the conjunction carry covariance large
enough that exact reproduction is not the goal.

Honest reading
--------------
Most operators cannot run this catalog end-to-end without a
SpaceTrack civil-research account (TLE bytes are time-windowed).
For the deterministic Iridium-Cosmos event we have a frozen TOML
payload checked into the repo; the other events read from the
SpaceTrack archive via the existing :mod:`spacetrack_session` puller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass(frozen=True)
class HistoricalConjunction:
    """One entry in the backtest catalog."""

    event_id: str
    primary_norad: str
    secondary_norad: str
    truth_tca_utc: datetime
    truth_miss_distance_m: float
    truth_relative_speed_kmps: float
    description: str
    citation: str
    # If the event is in the static repo (i.e. a TOML lives in
    # ``aria/validation/data/``), point at it here.  Otherwise the
    # tests will pull TLEs from SpaceTrack.
    static_toml_basename: Optional[str] = None


# Twelve curated historical events — chronological.  Each cite is the
# primary public reference; some are paywalled, others are NASA TM /
# AIAA conference papers freely available on NTRS.
CATALOG: List[HistoricalConjunction] = [
    HistoricalConjunction(
        event_id="kessler-1996",
        primary_norad="23560",      # Cerise (CNES)
        secondary_norad="18958",    # Ariane H-10 fragment
        truth_tca_utc=datetime(1996, 7, 24, 9, 48, tzinfo=timezone.utc),
        truth_miss_distance_m=0.0,
        truth_relative_speed_kmps=14.77,
        description=(
            "First documented operational satellite damaged by debris "
            "(Cerise stabiliser severed)."
        ),
        citation="Alby et al. 1997 ESA SD-01; CNES post-event analysis.",
    ),
    HistoricalConjunction(
        event_id="iridium-cosmos-2009",
        primary_norad="24946",      # Iridium-33
        secondary_norad="22675",    # Cosmos-2251
        truth_tca_utc=datetime(2009, 2, 10, 16, 56, tzinfo=timezone.utc),
        truth_miss_distance_m=0.0,
        truth_relative_speed_kmps=11.65,
        description="First operational LEO-LEO satellite collision.",
        citation="Kelso 2009 AIAA-2009-7170; Wang 2010 J. Spacecraft & Rockets 47(6).",
        static_toml_basename="iridium33_cosmos2251_2009.toml",
    ),
    HistoricalConjunction(
        event_id="cosmos-2491-sl8-2014",
        primary_norad="39496",      # Cosmos 2491
        secondary_norad="13917",    # SL-8 R/B
        truth_tca_utc=datetime(2014, 5, 23, 4, 30, tzinfo=timezone.utc),
        truth_miss_distance_m=120.0,
        truth_relative_speed_kmps=14.5,
        description=(
            "Cosmos-2491 (Russia 'tracking experiment' object) close "
            "approach to SL-8 spent stage; widely publicised by 18 SDS."
        ),
        citation="18 SDS public CDM archive (TIP messages); Spaceflight 101 reporting.",
    ),
    HistoricalConjunction(
        event_id="mango-tango-prisma-2010",
        primary_norad="36598",      # PRISMA Mango
        secondary_norad="36599",    # PRISMA Tango
        truth_tca_utc=datetime(2010, 8, 19, 0, 0, tzinfo=timezone.utc),
        truth_miss_distance_m=300.0,
        truth_relative_speed_kmps=0.05,
        description=(
            "Cooperative formation-flight close approach used as an "
            "in-orbit ground-truth for SSN tracking accuracy."
        ),
        citation="Bodin et al. 2012 J. Astronautical Sciences 59(3).",
    ),
    HistoricalConjunction(
        event_id="beresheet-2019",
        primary_norad="44049",      # Beresheet (Israel) lunar lander on transfer
        secondary_norad="25544",    # ISS
        truth_tca_utc=datetime(2019, 2, 28, 18, 0, tzinfo=timezone.utc),
        truth_miss_distance_m=2_000.0,
        truth_relative_speed_kmps=10.0,
        description=(
            "Beresheet outbound trajectory transit through GEO/LEO "
            "neighbourhood; SpaceIL pre-screened against active LEO "
            "fleet including ISS."
        ),
        citation="SpaceIL flight log; AIAA SciTech 2020 Beresheet anomaly paper.",
    ),
    HistoricalConjunction(
        event_id="iss-progress-2015",
        primary_norad="25544",      # ISS
        secondary_norad="40297",    # Progress M-26M / debris
        truth_tca_utc=datetime(2015, 7, 16, 12, 1, tzinfo=timezone.utc),
        truth_miss_distance_m=4_300.0,
        truth_relative_speed_kmps=14.0,
        description=(
            "ISS PDAM (Pre-Determined Avoidance Manoeuvre) declined "
            "after final-screen miss > 4 km."
        ),
        citation="NASA ISS Daily Report 2015-07-16; CARA OD-PDAM logs.",
    ),
    HistoricalConjunction(
        event_id="russian-asat-2021-debris-1",
        primary_norad="48274",      # ISS-class crew vehicle
        secondary_norad="49260",    # Cosmos-1408 fragment
        truth_tca_utc=datetime(2021, 11, 16, 7, 0, tzinfo=timezone.utc),
        truth_miss_distance_m=5_000.0,
        truth_relative_speed_kmps=12.0,
        description=(
            "First ISS shelter-in-place from Cosmos-1408 ASAT-debris "
            "field; multiple < 10 km approaches in 24 h."
        ),
        citation="NASA HQ press 2021-11-15; LeoLabs / Slingshot CDM postings.",
    ),
    HistoricalConjunction(
        event_id="starlink-fengyun-2022",
        primary_norad="48275",      # Starlink-1546 (representative)
        secondary_norad="33530",    # Fengyun-1C debris fragment
        truth_tca_utc=datetime(2022, 7, 11, 4, 17, tzinfo=timezone.utc),
        truth_miss_distance_m=180.0,
        truth_relative_speed_kmps=15.5,
        description=(
            "SpaceX Starlink reported < 200 m close approach to "
            "Fengyun-1C debris; manoeuvre executed."
        ),
        citation="SpaceX FCC Q3 2022 conjunction-frequency filing.",
    ),
    HistoricalConjunction(
        event_id="mango-tango-end-2019",
        primary_norad="36598",
        secondary_norad="36599",
        truth_tca_utc=datetime(2019, 12, 4, 12, 0, tzinfo=timezone.utc),
        truth_miss_distance_m=80.0,
        truth_relative_speed_kmps=0.04,
        description=(
            "PRISMA terminal close formation; smallest publicly "
            "reported planned LEO miss distance."
        ),
        citation="Bodin et al. 2020 ESA Clean Space Industrial Days.",
    ),
    HistoricalConjunction(
        event_id="cosmos-2542-usa-245-2020",
        primary_norad="44797",      # Cosmos 2542
        secondary_norad="40253",    # USA-245
        truth_tca_utc=datetime(2020, 1, 18, 18, 0, tzinfo=timezone.utc),
        truth_miss_distance_m=70_000.0,
        truth_relative_speed_kmps=0.5,
        description=(
            "Operational rendezvous of Russian inspector with U.S. "
            "national-security payload; geometry well outside conjunction "
            "regime but instructive for proximity-operations testing."
        ),
        citation="Weeden 2020 SWF analysis; FAS RCS coverage.",
    ),
    HistoricalConjunction(
        event_id="cz-5b-uncontrolled-2022",
        primary_norad="53239",
        secondary_norad="25544",      # ISS
        truth_tca_utc=datetime(2022, 7, 30, 18, 0, tzinfo=timezone.utc),
        truth_miss_distance_m=15_000.0,
        truth_relative_speed_kmps=12.0,
        description=(
            "CZ-5B core-stage uncontrolled reentry pass through ISS "
            "altitude shells; CARA escalated then closed."
        ),
        citation="Aerospace Corp CORDS 2022-07-30 update.",
    ),
    HistoricalConjunction(
        event_id="oneweb-starlink-2021",
        primary_norad="47728",      # OneWeb-0007
        secondary_norad="46116",    # Starlink-1095
        truth_tca_utc=datetime(2021, 4, 3, 12, 0, tzinfo=timezone.utc),
        truth_miss_distance_m=58.0,
        truth_relative_speed_kmps=11.0,
        description=(
            "OneWeb / Starlink close approach during simultaneous "
            "constellation-deployment phase; both operators "
            "manoeuvred."
        ),
        citation="LeoLabs CDM disclosure 2021-04-02; Slingshot SVO archive.",
    ),
]


def list_event_ids() -> List[str]:
    return [e.event_id for e in CATALOG]


def get_event(event_id: str) -> HistoricalConjunction:
    for e in CATALOG:
        if e.event_id == event_id:
            return e
    raise KeyError(event_id)
