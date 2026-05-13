"""Space weather indices and solar flare event detection.

Space weather affects:
- Atmospheric drag (F10.7 solar flux)
- Spacecraft charging (Kp index — geomagnetic activity)
- SEU rates (solar flares, CME events)
- Communication (ionospheric scintillation)

This module provides models for:
- F10.7 solar radio flux (mean + variability)
- Kp and Ap geomagnetic indices
- Solar flare classification (X/M/C/B/A class)
- CME (Coronal Mass Ejection) arrival time + intensity
- SEP (Solar Energetic Particle) event dose estimation

References:
    Tapping (2013) Space Weather 11:394 (F10.7 review)
    Bartels (1939) Terr. Mag. Atmos. Elec. 44:411 (K-index)
    Feynman & Gabriel (1990) J. Spacecraft 27(6):716 (SEP climatology)
    Cane & Richardson (2003) J. Geophys. Res. 108:1156 (CME arrival)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional


# ══════════════════════════════════════════════════════════════════
#  F10.7 solar flux
# ══════════════════════════════════════════════════════════════════

def estimate_f107_by_cycle_phase(years_since_solar_min: float) -> float:
    """Approximate F10.7 (Penticton) flux by solar cycle phase.

    Solar cycle is ~11 years: F10.7 rises from ~70 at minimum to
    ~200-250 at maximum, then declines. This is a sinusoidal approximation
    — actual F10.7 has daily/monthly variability of ±30%.

    Args:
        years_since_solar_min: years since most recent solar minimum

    Returns:
        Monthly-averaged F10.7 [sfu = 10⁻²² W/m²/Hz]

    Reference: Tapping 2013 Space Weather 11:394.
    """
    cycle_years = 11.0
    # Solar minimum F10.7 ~ 70, maximum ~ 200
    f_min = 70.0
    f_max = 200.0
    phase = (years_since_solar_min / cycle_years) * 2 * math.pi
    # Peak happens ~ 4 years after minimum (asymmetric cycle)
    # Simple sinusoidal approximation
    return f_min + 0.5 * (f_max - f_min) * (1 - math.cos(phase))


# ══════════════════════════════════════════════════════════════════
#  Geomagnetic activity
# ══════════════════════════════════════════════════════════════════

def kp_to_ap(kp: float) -> float:
    """Convert Kp to ap (equivalent range).

    Lookup table from Bartels' K-index definition. Quasi-logarithmic:
    Kp=0 → ap=0, Kp=3 → ap=15, Kp=5 → ap=48, Kp=9 → ap=400.
    """
    # Standard Kp-to-ap table (Bartels 1939)
    kp_rounded = round(kp * 3) / 3  # snap to Kp± levels
    ap_table = {
        0.0: 0, 0.33: 2, 0.67: 3, 1.0: 4, 1.33: 5, 1.67: 6,
        2.0: 7, 2.33: 9, 2.67: 12, 3.0: 15, 3.33: 18, 3.67: 22,
        4.0: 27, 4.33: 32, 4.67: 39, 5.0: 48, 5.33: 56, 5.67: 67,
        6.0: 80, 6.33: 94, 6.67: 111, 7.0: 132, 7.33: 154, 7.67: 179,
        8.0: 207, 8.33: 236, 8.67: 300, 9.0: 400,
    }
    return float(ap_table.get(kp_rounded, 27))


def classify_geomagnetic_storm(kp: float) -> str:
    """NOAA G-scale classification of geomagnetic storm intensity.

    G1 (minor): Kp=5
    G2 (moderate): Kp=6
    G3 (strong): Kp=7
    G4 (severe): Kp=8 to 9-
    G5 (extreme): Kp=9

    Reference: NOAA Space Weather Scales (2013)
    """
    if kp < 5:
        return "quiet"
    elif kp < 6:
        return "G1_minor"
    elif kp < 7:
        return "G2_moderate"
    elif kp < 8:
        return "G3_strong"
    elif kp < 9:
        return "G4_severe"
    else:
        return "G5_extreme"


# ══════════════════════════════════════════════════════════════════
#  Solar flare classification
# ══════════════════════════════════════════════════════════════════

class FlareClass(Enum):
    """GOES X-ray flux class for solar flares.

    Letter = order of magnitude, number = multiplier.
    A1 = 1e-8 W/m², B1 = 1e-7, C1 = 1e-6, M1 = 1e-5, X1 = 1e-4.
    """
    A = "A"  # 1e-8 — 1e-7 W/m²
    B = "B"  # 1e-7 — 1e-6
    C = "C"  # 1e-6 — 1e-5 (weak)
    M = "M"  # 1e-5 — 1e-4 (medium)
    X = "X"  # >= 1e-4 W/m² (strong)


def classify_flare(x_ray_flux_wm2: float) -> tuple[FlareClass, float]:
    """Classify solar flare by 1-8 Å X-ray flux.

    Args:
        x_ray_flux_wm2: peak flux from GOES XRS-B [W/m²]

    Returns:
        (class, multiplier) e.g., (FlareClass.X, 1.5) = X1.5

    Reference: NOAA SWPC solar flare scale.
    """
    if x_ray_flux_wm2 < 1e-7:
        cls = FlareClass.A
        exp = -8
    elif x_ray_flux_wm2 < 1e-6:
        cls = FlareClass.B
        exp = -7
    elif x_ray_flux_wm2 < 1e-5:
        cls = FlareClass.C
        exp = -6
    elif x_ray_flux_wm2 < 1e-4:
        cls = FlareClass.M
        exp = -5
    else:
        cls = FlareClass.X
        exp = -4

    multiplier = x_ray_flux_wm2 / (10 ** exp)
    return cls, multiplier


# ══════════════════════════════════════════════════════════════════
#  CME arrival time prediction
# ══════════════════════════════════════════════════════════════════

def cme_arrival_time_hours(
    initial_speed_km_s: float,
    sun_earth_distance_au: float = 1.0,
) -> float:
    """Estimate CME arrival time at Earth from speed.

    Uses Gopalswamy's empirical drag model: CMEs decelerate during
    propagation. Fast CMEs decelerate more, slow ones accelerate.

    Effective travel time for 1 AU ≈ 20-90 hours depending on speed.

    Args:
        initial_speed_km_s: CME speed at Sun (from coronagraph)
        sun_earth_distance_au: Earth distance at event time

    Returns:
        Arrival time [hours]

    Reference: Gopalswamy et al. (2001) JGR 106:29219
    """
    # Empirical fit: v(t) decelerates toward ambient solar wind speed (400 km/s)
    # For simplicity use constant average: v_avg ~ 0.5*(v_initial + 400)
    if initial_speed_km_s <= 0:
        return float("inf")

    v_solar_wind = 400.0  # km/s ambient
    v_avg = 0.5 * (initial_speed_km_s + v_solar_wind)
    distance_km = sun_earth_distance_au * 1.496e8
    return distance_km / v_avg / 3600.0


def cme_severity(initial_speed_km_s: float) -> str:
    """Classify CME severity by speed.

    <500 km/s: slow, unlikely to cause geomagnetic storm
    500-1000: moderate
    1000-2000: fast, strong geomagnetic storm likely
    >2000: extremely fast, severe storm, aurora at low latitudes

    Reference: Cane & Richardson 2003 JGR 108:1156.
    """
    if initial_speed_km_s < 500:
        return "slow"
    elif initial_speed_km_s < 1000:
        return "moderate"
    elif initial_speed_km_s < 2000:
        return "fast"
    else:
        return "extreme"


# ══════════════════════════════════════════════════════════════════
#  SEP (Solar Energetic Particle) event
# ══════════════════════════════════════════════════════════════════

@dataclass
class SEPEvent:
    """A solar energetic particle event."""
    start_time: datetime
    peak_proton_flux_pfu: float  # Proton Flux Units = #/cm²/s/sr @ >10MeV
    duration_hours: float
    classification: str          # S1-S5 NOAA scale

    @property
    def integrated_fluence_per_cm2(self) -> float:
        """Time-integrated >10 MeV proton fluence."""
        # Assume Gaussian time profile with FWHM = duration/2
        peak_rate = self.peak_proton_flux_pfu
        duration_s = self.duration_hours * 3600
        # Integral of Gaussian: ~ peak_rate × duration × 0.6
        return peak_rate * duration_s * 0.6


def classify_sep(peak_flux_pfu: float) -> str:
    """NOAA S-scale for solar radiation storm.

    S1 (minor): 10 pfu
    S2 (moderate): 100 pfu
    S3 (strong): 1000 pfu
    S4 (severe): 10000 pfu
    S5 (extreme): 100000 pfu

    pfu = proton flux unit = #/cm²/s/sr at >10 MeV
    """
    if peak_flux_pfu < 10:
        return "quiet"
    elif peak_flux_pfu < 100:
        return "S1_minor"
    elif peak_flux_pfu < 1000:
        return "S2_moderate"
    elif peak_flux_pfu < 10000:
        return "S3_strong"
    elif peak_flux_pfu < 100000:
        return "S4_severe"
    else:
        return "S5_extreme"


# ══════════════════════════════════════════════════════════════════
#  Space weather summary
# ══════════════════════════════════════════════════════════════════

@dataclass
class SpaceWeatherState:
    """Current state of space weather affecting operations."""
    f107: float                  # solar flux
    kp: float                    # geomagnetic index
    active_flares: List[str] = field(default_factory=list)
    sep_events: List[SEPEvent] = field(default_factory=list)
    timestamp: Optional[datetime] = None

    def atmosphere_density_multiplier(self) -> float:
        """Drag density multiplier from current space weather.

        Higher F10.7 and Ap → higher thermospheric density → more drag.
        """
        # Linear in F10.7, exponential in Ap (simplified)
        f_factor = (self.f107 / 150.0) ** 1.5
        ap = kp_to_ap(self.kp)
        a_factor = math.exp(0.005 * max(ap - 10, 0))
        return f_factor * a_factor

    def charging_risk_elevated(self) -> bool:
        """True if geomagnetic activity or SEP raises charging risk."""
        return self.kp >= 6 or len(self.sep_events) > 0

    def operations_advisory(self) -> List[str]:
        """Generate ops advisories from current state."""
        advisories: List[str] = []
        storm = classify_geomagnetic_storm(self.kp)
        if storm != "quiet":
            advisories.append(
                f"Geomagnetic storm in progress: {storm}; monitor charging"
            )
        if self.f107 > 200:
            advisories.append(
                f"High solar flux (F10.7={self.f107:.0f}): increased LEO drag"
            )
        for sep in self.sep_events:
            advisories.append(
                f"SEP event {sep.classification}: elevated radiation — "
                f"defer EVA, consider shielding"
            )
        if any("X" in f for f in self.active_flares):
            advisories.append(
                "X-class flare active: comms blackout possible, HF degraded"
            )
        return advisories
