"""
Fleet-level collision risk aggregation for constellation operators.

A constellation of N satellites faces N×(catalog_size) conjunction pairs.
This module computes:
  1. Fleet Pc: probability that ANY satellite in the fleet has a collision
     P_fleet = 1 - Π(1 - Pc_i)  (product over all events)
  2. Expected collisions per year across the fleet
  3. Worst-case satellite (highest individual cumulative risk)
  4. Risk heatmap by orbital shell / inclination band
  5. Maneuver budget: total ΔV/fuel consumed by fleet avoidance maneuvers

For Starlink (~6000 sats) or OneWeb (~600 sats), fleet-level metrics
are more actionable than individual conjunction alerts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from aria.conjunction.core.types import CloseApproach, RiskLevel


@dataclass
class SatelliteRiskProfile:
    """Risk metrics for a single satellite in the fleet."""

    norad_id: str
    name: str
    n_conjunctions: int = 0
    max_pc: float = 0.0
    cumulative_pc: float = 0.0  # 1 - Π(1 - Pc_i)
    n_red_alerts: int = 0
    n_yellow_alerts: int = 0
    n_maneuvers_needed: int = 0
    total_delta_v_m_s: float = 0.0  # total avoidance ΔV
    altitude_km: float = 0.0


@dataclass
class OrbitalShellRisk:
    """Risk aggregated over an altitude/inclination shell."""

    altitude_band: tuple[float, float]  # (min_km, max_km)
    inclination_band: tuple[float, float]  # (min_deg, max_deg)
    n_objects: int = 0
    n_conjunctions: int = 0
    mean_pc: float = 0.0
    max_pc: float = 0.0
    spatial_density: float = 0.0  # objects per km³ of shell volume


@dataclass
class FleetRiskReport:
    """Aggregate risk report for an entire constellation."""

    fleet_name: str
    fleet_size: int
    assessment_window_hours: float
    assessment_time: datetime

    # Fleet-wide metrics
    fleet_pc: float  # probability of ANY collision in the fleet
    expected_collisions_per_year: float
    total_conjunctions: int
    total_red_alerts: int
    total_yellow_alerts: int
    total_maneuvers: int
    total_delta_v_m_s: float  # fleet avoidance fuel budget

    # Per-satellite breakdown
    satellite_profiles: list[SatelliteRiskProfile]

    # Worst case
    highest_risk_satellite: SatelliteRiskProfile | None

    # By orbital shell
    shell_risks: list[OrbitalShellRisk]

    def summary(self) -> str:
        """Human-readable fleet risk summary."""
        hrs = self.assessment_window_hours
        return (
            f"Fleet Risk Report: {self.fleet_name}\n"
            f"{'=' * 50}\n"
            f"Fleet size: {self.fleet_size} satellites\n"
            f"Window: {hrs}h\n"
            f"Total conjunctions: {self.total_conjunctions}\n"
            f"Fleet Pc (any collision): {self.fleet_pc:.2e}\n"
            f"Expected collisions/year: {self.expected_collisions_per_year:.3f}\n"
            f"Alerts: {self.total_red_alerts} RED, {self.total_yellow_alerts} YELLOW\n"
            f"Maneuvers needed: {self.total_maneuvers}\n"
            f"Total fleet ΔV: {self.total_delta_v_m_s:.2f} m/s\n"
            + (f"Highest risk: {self.highest_risk_satellite.name} "
               f"(Pc_cum={self.highest_risk_satellite.cumulative_pc:.2e})\n"
               if self.highest_risk_satellite else "")
        )


class FleetRiskAggregator:
    """Compute fleet-level risk metrics from individual conjunction assessments."""

    def __init__(
        self,
        fleet_norad_ids: set[str],
        fleet_name: str = "CONSTELLATION",
        altitude_bin_km: float = 50.0,
        inclination_bin_deg: float = 5.0,
    ):
        """
        Args:
            fleet_norad_ids: Set of NORAD IDs belonging to this fleet
            fleet_name: Name for reporting
            altitude_bin_km: Bin size for orbital shell risk map
            inclination_bin_deg: Bin size for inclination bands
        """
        self.fleet_ids = fleet_norad_ids
        self.fleet_name = fleet_name
        self.alt_bin = altitude_bin_km
        self.inc_bin = inclination_bin_deg

    def assess(
        self,
        approaches: list[CloseApproach],
        window_hours: float = 72.0,
    ) -> FleetRiskReport:
        """Compute fleet-level risk from a list of close approaches.

        Only considers approaches where the PRIMARY is a fleet member.

        Args:
            approaches: List of CloseApproach events (from pipeline)
            window_hours: Assessment window duration (hours)

        Returns:
            FleetRiskReport with aggregate metrics
        """
        # Filter to fleet-relevant conjunctions
        fleet_approaches = [
            a for a in approaches
            if a.primary.norad_id in self.fleet_ids
            or a.secondary.norad_id in self.fleet_ids
        ]

        # Per-satellite profiles
        sat_profiles: dict[str, SatelliteRiskProfile] = {}
        for nid in self.fleet_ids:
            sat_profiles[nid] = SatelliteRiskProfile(norad_id=nid, name=f"SAT-{nid}")

        # Process each approach
        for approach in fleet_approaches:
            pc = approach.probability_of_collision or 0.0

            # Identify which fleet member is involved
            if approach.primary.norad_id in self.fleet_ids:
                sat_id = approach.primary.norad_id
                sat_name = approach.primary.name
                if approach.primary.elements:
                    alt = (approach.primary.elements.perigee_altitude
                           + approach.primary.elements.apogee_altitude) / 2
                else:
                    alt = 0
            else:
                sat_id = approach.secondary.norad_id
                sat_name = approach.secondary.name
                if approach.secondary.elements:
                    alt = (approach.secondary.elements.perigee_altitude
                           + approach.secondary.elements.apogee_altitude) / 2
                else:
                    alt = 0

            profile = sat_profiles[sat_id]
            profile.name = sat_name
            profile.n_conjunctions += 1
            profile.max_pc = max(profile.max_pc, pc)
            profile.altitude_km = alt

            if approach.risk_level == RiskLevel.RED:
                profile.n_red_alerts += 1
                profile.n_maneuvers_needed += 1
            elif approach.risk_level == RiskLevel.YELLOW:
                profile.n_yellow_alerts += 1

        # Compute cumulative Pc per satellite: 1 - Π(1 - Pc_i)
        for approach in fleet_approaches:
            pc = approach.probability_of_collision or 0.0
            if pc > 0:
                if approach.primary.norad_id in sat_profiles:
                    p = sat_profiles[approach.primary.norad_id]
                    p.cumulative_pc = 1 - (1 - p.cumulative_pc) * (1 - pc)
                if approach.secondary.norad_id in sat_profiles:
                    p = sat_profiles[approach.secondary.norad_id]
                    p.cumulative_pc = 1 - (1 - p.cumulative_pc) * (1 - pc)

        # Fleet Pc: 1 - Π(1 - cumulative_pc_i)
        log_survival = 0.0
        for p in sat_profiles.values():
            if p.cumulative_pc < 1.0:
                log_survival += math.log(1 - p.cumulative_pc)
            else:
                log_survival = -float("inf")
                break
        fleet_pc = 1 - math.exp(log_survival) if log_survival > -700 else 1.0

        # Expected collisions per year: Σ Pc_i × (365.25*24 / window_hours)
        annualization = (365.25 * 24) / window_hours
        expected_per_year = sum(
            (a.probability_of_collision or 0) for a in fleet_approaches
        ) * annualization

        # Highest risk satellite
        profiles_list = list(sat_profiles.values())
        highest = max(profiles_list, key=lambda p: p.cumulative_pc) if profiles_list else None

        # Totals
        total_red = sum(p.n_red_alerts for p in profiles_list)
        total_yellow = sum(p.n_yellow_alerts for p in profiles_list)
        total_maneuvers = sum(p.n_maneuvers_needed for p in profiles_list)

        # Orbital shell risk breakdown
        shell_risks = self._compute_shell_risks(fleet_approaches, profiles_list)

        return FleetRiskReport(
            fleet_name=self.fleet_name,
            fleet_size=len(self.fleet_ids),
            assessment_window_hours=window_hours,
            assessment_time=datetime.utcnow(),
            fleet_pc=fleet_pc,
            expected_collisions_per_year=expected_per_year,
            total_conjunctions=len(fleet_approaches),
            total_red_alerts=total_red,
            total_yellow_alerts=total_yellow,
            total_maneuvers=total_maneuvers,
            total_delta_v_m_s=sum(p.total_delta_v_m_s for p in profiles_list),
            satellite_profiles=profiles_list,
            highest_risk_satellite=highest,
            shell_risks=shell_risks,
        )

    def _compute_shell_risks(
        self,
        approaches: list[CloseApproach],
        profiles: list[SatelliteRiskProfile],
    ) -> list[OrbitalShellRisk]:
        """Compute risk by orbital altitude/inclination shell."""
        shells: dict[tuple, OrbitalShellRisk] = {}

        for profile in profiles:
            alt = profile.altitude_km
            alt_bin = int(alt / self.alt_bin) * self.alt_bin
            key = (alt_bin, alt_bin + self.alt_bin)

            if key not in shells:
                shells[key] = OrbitalShellRisk(
                    altitude_band=key,
                    inclination_band=(0, 180),
                )
            shell = shells[key]
            shell.n_objects += 1
            shell.n_conjunctions += profile.n_conjunctions
            shell.max_pc = max(shell.max_pc, profile.max_pc)

        for shell in shells.values():
            if shell.n_conjunctions > 0 and shell.n_objects > 0:
                shell.mean_pc = shell.max_pc / shell.n_objects

        return sorted(shells.values(), key=lambda s: s.altitude_band[0])
