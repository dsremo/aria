"""Real space medical incidence rates from peer-reviewed literature.

Primary source: Crucian B, Babiak-Vazquez A, Johnston S, Pierson DL, Ott CM,
Sams C. "Incidence of clinical symptoms during long-duration orbital
spaceflight." Int J Gen Med. 2016;9:383-391. doi:10.2147/IJGM.S114188

Study parameters:
  - 46 long-duration US ISS crew members (34 male, 12 female)
  - Average age: 47.51 years at flight
  - 38 six-month missions (5 astronauts repeated missions)
  - Total: 20.57 flight years (7,058 days)
  - Average mission: 162.95 days

Supplementary sources:
  - Barratt & Pool (2008), Principles of Clinical Medicine for Space Flight
  - NASA Flight Surgeon reports, ISS medical event logs (JSC, 2020 review)
  - Kanas (2015), Space Psychology and Psychiatry (2nd ed.)
  - Tansey (2000), US Navy submarine medical records
  - Lugg (2000), Antarctic winter-over station medical records
  - Cherry DK et al. (2003), National Ambulatory Medical Care Survey: 2001.
    Advance Data No. 337:1-44 (terrestrial baselines)

Notes on applicability:
  The ISS incidence data represents the best available evidence for
  exploration-class missions. Deep-space missions beyond LEO will likely
  see HIGHER rates due to increased radiation, no evacuation option,
  chronic immune dysregulation, and psychological stressors of isolation.
  The Crucian et al. study likely underestimates true incidence as it
  only captured immunologically-related events from available records.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


# ════════════════════════════════════════════════════════════════════
#  INCIDENCE RATES — from Crucian et al. 2016, Table 1
# ════════════════════════════════════════════════════════════════════
# All rates are events per person per year (events/flight-year),
# derived from 70 total events across 20.57 flight years.

# Immune-dysregulation-related events (Table 1, Crucian et al. 2016)
ALLERGIC_HYPERSENSITIVITY_RATE = 0.10    # 2 events / 20.57 FY
UPPER_RESPIRATORY_RATE = 0.97            # 20 events / 20.57 FY
HERPES_VIRUS_RATE = 0.29                 # 6 events / 20.57 FY
EAR_RELATED_RATE = 0.29                  # 6 events / 20.57 FY
PHARYNGITIS_RATE = 0.05                  # 1 event / 20.57 FY
SKIN_INFECTION_RATE = 0.29               # 6 events / 20.57 FY
SKIN_RASH_HYPERSENSITIVITY_RATE = 1.12   # 23 events / 20.57 FY
URINARY_TRACT_INFECTION_RATE = 0.10      # 2 events / 20.57 FY
OTHER_INFECTION_RATE = 0.19              # 4 events / 20.57 FY

# Combined rate from Crucian et al. 2016
ISS_TOTAL_IMMUNE_EVENT_RATE = 3.40       # 70 events / 20.57 FY

# Terrestrial comparison (Cherry et al. 2003, NAMCS 2001)
TERRESTRIAL_RASH_RATE = 0.044            # persistent rashes, US population
ISS_RASH_ELEVATION_FACTOR = 25.0         # ISS rate is ~25x terrestrial


# ════════════════════════════════════════════════════════════════════
#  BROADER MEDICAL RATES — NASA flight surgeon data + literature
# ════════════════════════════════════════════════════════════════════
# These cover categories beyond the immune-focused Crucian study.
# Sources: Barratt & Pool (2008), NASA JSC medical reviews,
# Tansey (2000) submarine data, Lugg (2000) Antarctic stations.

# Cardiac events — rare in astronaut population (highly screened),
# but non-zero for generation ship with unscreened general population.
# ISS: ~0 events in Crucian data (screened astronauts).
# Submarine/Antarctic analogs: ~0.5-1.0 per 1000 person-years for
# healthy adults (Barratt & Pool 2008, Ch.25). Generation ship
# general population estimate: ~2-4 per 1000 person-years.
CARDIAC_EVENT_RATE = 0.003               # per person-year (general pop estimate)

# Dental — among most common in-flight issues (Barratt & Pool 2008).
# ISS flight surgeon logs indicate ~0.2 dental events per person-year
# across all missions (not limited to immune-related events).
DENTAL_EVENT_RATE = 0.20                 # per person-year

# Musculoskeletal — extremely common in spaceflight.
# Back pain affects ~50% of astronauts (Wing 1991, Kerstman 2012).
# MSK injuries: strains, sprains, overuse from exercise countermeasures.
# ISS data: ~0.3-0.5 MSK events per person-year (Scheuring 2009).
MSK_INJURY_RATE = 0.40                   # per person-year

# Ophthalmological — Spaceflight-Associated Neuro-ocular Syndrome (SANS)
# affects ~70% of long-duration astronauts (Mader 2011, Lee 2020).
# Clinically significant events requiring intervention: ~0.1/person-yr.
OPHTHALMOLOGICAL_RATE = 0.10             # per person-year

# Behavioral/psychiatric — Kanas (2015) reports ~2 significant
# behavioral health events per 100 person-years in ISS crews.
# Antarctic winter-over (Palinkas 2003): 3-5 per 100 person-years.
# Generation ship (confined, permanent): estimate 3.0 per 100.
PSYCHIATRIC_RATE = 0.03                  # per person-year (significant events)

# Trauma — submarine/Antarctic analog: ~5-8 per 100 person-years.
# ISS: lower (fewer physical hazards), ~2-3 per 100 person-years.
# Generation ship (industrial work at 0.56g): ~5 per 100 person-years.
TRAUMA_RATE = 0.05                       # per person-year

# Burns — ISS: rare (~0.5 per 100 person-years).
# Generation ship (manufacturing, reactors): ~1-2 per 100 person-years.
BURN_RATE = 0.015                        # per person-year

# Radiation sickness (acute) — depends on shielding and SPE frequency.
# ISS behind shielding: ~0 acute cases (well-shielded in LEO).
# Deep space: ~0.5-1.0 per 100 person-years during solar maximum.
RADIATION_ACUTE_RATE = 0.005             # per person-year (deep space estimate)


# ════════════════════════════════════════════════════════════════════
#  COMBINED CATEGORY MAPPING
# ════════════════════════════════════════════════════════════════════

class MedicalCondition(Enum):
    """Medical condition categories with empirical incidence rates."""
    # Crucian et al. 2016 (immune-related, directly from Table 1)
    ALLERGIC_HYPERSENSITIVITY = auto()
    UPPER_RESPIRATORY = auto()
    HERPES_VIRUS = auto()
    EAR_RELATED = auto()
    PHARYNGITIS = auto()
    SKIN_INFECTION = auto()
    SKIN_RASH = auto()
    URINARY_TRACT = auto()
    OTHER_INFECTION = auto()
    # Broader medical categories (NASA flight surgeon + analogs)
    CARDIAC = auto()
    DENTAL = auto()
    MUSCULOSKELETAL = auto()
    OPHTHALMOLOGICAL = auto()
    PSYCHIATRIC = auto()
    TRAUMA = auto()
    BURN = auto()
    RADIATION_ACUTE = auto()


@dataclass(frozen=True)
class IncidenceRecord:
    """A single incidence rate with provenance."""
    condition: MedicalCondition
    rate_per_person_year: float
    source: str
    total_events: int | None = None    # raw event count if from Crucian
    total_flight_years: float | None = None
    notes: str = ""


# Master registry — every rate with its source
INCIDENCE_REGISTRY: dict[MedicalCondition, IncidenceRecord] = {
    MedicalCondition.ALLERGIC_HYPERSENSITIVITY: IncidenceRecord(
        condition=MedicalCondition.ALLERGIC_HYPERSENSITIVITY,
        rate_per_person_year=ALLERGIC_HYPERSENSITIVITY_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=2, total_flight_years=20.57,
        notes="Allergic reaction (hypersensitivity)",
    ),
    MedicalCondition.UPPER_RESPIRATORY: IncidenceRecord(
        condition=MedicalCondition.UPPER_RESPIRATORY,
        rate_per_person_year=UPPER_RESPIRATORY_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=20, total_flight_years=20.57,
        notes="Prolonged congestion, rhinitis, sneezing",
    ),
    MedicalCondition.HERPES_VIRUS: IncidenceRecord(
        condition=MedicalCondition.HERPES_VIRUS,
        rate_per_person_year=HERPES_VIRUS_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=6, total_flight_years=20.57,
        notes="Cold sores — latent herpesvirus reactivation",
    ),
    MedicalCondition.EAR_RELATED: IncidenceRecord(
        condition=MedicalCondition.EAR_RELATED,
        rate_per_person_year=EAR_RELATED_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=6, total_flight_years=20.57,
        notes="Pain, congestion, itchiness (otitis media + externa combined)",
    ),
    MedicalCondition.PHARYNGITIS: IncidenceRecord(
        condition=MedicalCondition.PHARYNGITIS,
        rate_per_person_year=PHARYNGITIS_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=1, total_flight_years=20.57,
        notes="Sore throat",
    ),
    MedicalCondition.SKIN_INFECTION: IncidenceRecord(
        condition=MedicalCondition.SKIN_INFECTION,
        rate_per_person_year=SKIN_INFECTION_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=6, total_flight_years=20.57,
        notes="Pus-forming wounds on wrist, finger, feet",
    ),
    MedicalCondition.SKIN_RASH: IncidenceRecord(
        condition=MedicalCondition.SKIN_RASH,
        rate_per_person_year=SKIN_RASH_HYPERSENSITIVITY_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=23, total_flight_years=20.57,
        notes="25x terrestrial rate. Tinea versicolor, dermatitis, rosacea. "
              "Likely Th2 immune shift.",
    ),
    MedicalCondition.URINARY_TRACT: IncidenceRecord(
        condition=MedicalCondition.URINARY_TRACT,
        rate_per_person_year=URINARY_TRACT_INFECTION_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=2, total_flight_years=20.57,
        notes="UTI — historically notable (Apollo 13 incident led to HSP)",
    ),
    MedicalCondition.OTHER_INFECTION: IncidenceRecord(
        condition=MedicalCondition.OTHER_INFECTION,
        rate_per_person_year=OTHER_INFECTION_RATE,
        source="Crucian et al. 2016, Table 1",
        total_events=4, total_flight_years=20.57,
        notes="Fever, aphthous ulcer, lymphadenitis",
    ),
    MedicalCondition.CARDIAC: IncidenceRecord(
        condition=MedicalCondition.CARDIAC,
        rate_per_person_year=CARDIAC_EVENT_RATE,
        source="Barratt & Pool 2008; generation ship population estimate",
        notes="ISS crew are pre-screened; general population rate higher",
    ),
    MedicalCondition.DENTAL: IncidenceRecord(
        condition=MedicalCondition.DENTAL,
        rate_per_person_year=DENTAL_EVENT_RATE,
        source="Barratt & Pool 2008 Ch.29; NASA flight surgeon logs",
        notes="Cavities, extractions, abscesses — no Earth resupply",
    ),
    MedicalCondition.MUSCULOSKELETAL: IncidenceRecord(
        condition=MedicalCondition.MUSCULOSKELETAL,
        rate_per_person_year=MSK_INJURY_RATE,
        source="Scheuring 2009; Kerstman 2012",
        notes="Back pain, strains, exercise-countermeasure injuries",
    ),
    MedicalCondition.OPHTHALMOLOGICAL: IncidenceRecord(
        condition=MedicalCondition.OPHTHALMOLOGICAL,
        rate_per_person_year=OPHTHALMOLOGICAL_RATE,
        source="Mader 2011; Lee 2020 (SANS)",
        notes="SANS affects ~70% long-duration crew; clinical events ~10%",
    ),
    MedicalCondition.PSYCHIATRIC: IncidenceRecord(
        condition=MedicalCondition.PSYCHIATRIC,
        rate_per_person_year=PSYCHIATRIC_RATE,
        source="Kanas 2015; Palinkas 2003 (Antarctic analog)",
        notes="Significant behavioral health events",
    ),
    MedicalCondition.TRAUMA: IncidenceRecord(
        condition=MedicalCondition.TRAUMA,
        rate_per_person_year=TRAUMA_RATE,
        source="Tansey 2000 (submarine); Lugg 2000 (Antarctic)",
        notes="Generation ship: industrial work at 0.56g",
    ),
    MedicalCondition.BURN: IncidenceRecord(
        condition=MedicalCondition.BURN,
        rate_per_person_year=BURN_RATE,
        source="Tansey 2000 (submarine); generation ship estimate",
        notes="Manufacturing, reactor maintenance, electrical",
    ),
    MedicalCondition.RADIATION_ACUTE: IncidenceRecord(
        condition=MedicalCondition.RADIATION_ACUTE,
        rate_per_person_year=RADIATION_ACUTE_RATE,
        source="NASA SPE models; deep space estimate",
        notes="Depends heavily on shielding and solar cycle phase",
    ),
}


# ════════════════════════════════════════════════════════════════════
#  AGGREGATE RATES
# ════════════════════════════════════════════════════════════════════

# All-cause medical event rate per person per year.
# Crucian immune-related: 3.40/yr + non-immune categories.
# Total estimate for generation ship: ~4.5 events/person/year
# (aligns with "5-10 per 100 crew" docstring in medical_robotics.py
#  when noting that 5-10 per 100 = 0.05-0.10 per person, which was
#  for significant events only; minor events push total higher).
ALL_CAUSE_RATE = sum(
    r.rate_per_person_year for r in INCIDENCE_REGISTRY.values()
)


def get_incidence_rate(
    condition: str,
    crew_size: int = 1000,
) -> float:
    """Return the annual probability of at least one event for a crew.

    For a single person, the rate is simply events/person/year from
    the registry. For a crew, we compute the expected number of
    events per year: rate * crew_size. This is returned as the
    expected annual count (Poisson lambda), NOT a probability.

    To get probability of zero events in a year:
        P(0) = exp(-lambda)
    To get probability of at least one event:
        P(>=1) = 1 - exp(-lambda)

    Args:
        condition: Condition name (case-insensitive). Accepts enum names
            (e.g. "SKIN_RASH") or partial matches (e.g. "cardiac", "dental").
        crew_size: Number of crew members. Default 1000.

    Returns:
        Expected number of events per year for the given crew size
        (Poisson lambda).

    Raises:
        KeyError: If condition name cannot be matched.
    """
    condition_upper = condition.upper().replace(" ", "_")

    # Exact match first
    for mc in MedicalCondition:
        if mc.name == condition_upper:
            return INCIDENCE_REGISTRY[mc].rate_per_person_year * crew_size

    # Partial / substring match
    for mc in MedicalCondition:
        if condition_upper in mc.name or mc.name in condition_upper:
            return INCIDENCE_REGISTRY[mc].rate_per_person_year * crew_size

    available = [mc.name for mc in MedicalCondition]
    raise KeyError(
        f"Unknown condition: {condition!r}. "
        f"Available: {available}"
    )


def get_all_rates(crew_size: int = 1) -> dict[str, float]:
    """Return all incidence rates scaled to crew_size.

    Args:
        crew_size: Number of crew members. Default 1 (per-person rates).

    Returns:
        Dict mapping condition name to expected annual events.
    """
    return {
        mc.name: rec.rate_per_person_year * crew_size
        for mc, rec in INCIDENCE_REGISTRY.items()
    }


def get_record(condition: str) -> IncidenceRecord:
    """Look up the full IncidenceRecord for a condition.

    Args:
        condition: Condition name (case-insensitive, partial match OK).

    Returns:
        The IncidenceRecord with rate, source, and notes.

    Raises:
        KeyError: If condition name cannot be matched.
    """
    condition_upper = condition.upper().replace(" ", "_")

    for mc in MedicalCondition:
        if mc.name == condition_upper:
            return INCIDENCE_REGISTRY[mc]

    for mc in MedicalCondition:
        if condition_upper in mc.name or mc.name in condition_upper:
            return INCIDENCE_REGISTRY[mc]

    available = [mc.name for mc in MedicalCondition]
    raise KeyError(
        f"Unknown condition: {condition!r}. "
        f"Available: {available}"
    )


# ════════════════════════════════════════════════════════════════════
#  MAPPING TO MEDICAL ROBOTICS EVENT TYPES
# ════════════════════════════════════════════════════════════════════
# Maps the simulation's MedicalEventType enum values to empirical rates.
# Used by medical_robotics.py to replace hardcoded EVENT_DISTRIBUTION.

def get_event_distribution_from_empirical() -> dict[str, float]:
    """Compute EVENT_DISTRIBUTION weights from real incidence data.

    Maps empirical conditions to the MedicalEventType categories used
    in medical_robotics.py, then normalizes to sum to 1.0.

    Mapping:
        TRAUMA      <- TRAUMA + MUSCULOSKELETAL
        DENTAL      <- DENTAL
        INFECTION   <- all Crucian immune-related categories
        PSYCHOLOGICAL <- PSYCHIATRIC
        BURN        <- BURN
        CARDIAC     <- CARDIAC
        RADIATION_CHRONIC <- (fixed small fraction, no direct empirical)
        RADIATION_ACUTE   <- RADIATION_ACUTE
        CHILDBIRTH  <- (population-dependent, not incidence-based)
        SURGICAL    <- (derived from surgery probabilities, not standalone)

    Returns:
        Dict mapping MedicalEventType value strings to normalized weights.
    """
    # For infection: only count events requiring medical intervention,
    # not all immune-related symptoms. Crucian et al. 2016 found 42/70
    # events were "notable" (>1 week, recurring, or treatment-resistant).
    # We include: skin infections, UTIs, herpes (active), pharyngitis,
    # other infections, and a fraction of rashes/respiratory that
    # escalated to require treatment (~40% of rash events were notable).
    infection_intervention_rate = (
        SKIN_INFECTION_RATE                           # 0.29 — all require treatment
        + URINARY_TRACT_INFECTION_RATE                # 0.10 — all require antibiotics
        + HERPES_VIRUS_RATE                           # 0.29 — antiviral treatment
        + PHARYNGITIS_RATE                            # 0.05 — treatment needed
        + OTHER_INFECTION_RATE                        # 0.19 — fever, ulcer, lymphadenitis
        + ALLERGIC_HYPERSENSITIVITY_RATE              # 0.10 — antihistamines
        + SKIN_RASH_HYPERSENSITIVITY_RATE * 0.40      # ~40% notable (Crucian Fig 1)
        + UPPER_RESPIRATORY_RATE * 0.20               # ~20% persistent >1 week
    )

    raw: dict[str, float] = {
        "trauma": TRAUMA_RATE + MSK_INJURY_RATE,          # 0.05 + 0.40 = 0.45
        "dental": DENTAL_EVENT_RATE,                       # 0.20
        "infection": infection_intervention_rate,           # ~1.46
        "psychological": PSYCHIATRIC_RATE,                 # 0.03
        "burn": BURN_RATE,                                 # 0.015
        "cardiac": CARDIAC_EVENT_RATE,                     # 0.003
        "radiation_acute": RADIATION_ACUTE_RATE,           # 0.005
        "radiation_chronic": 0.01,                         # no direct empirical data
        "childbirth": 0.02,                                # population dependent
        "surgical": 0.01,                                  # derived category
    }

    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}
