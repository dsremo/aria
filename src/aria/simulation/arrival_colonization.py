"""Arrival & Colonization — what happens after orbital insertion.

Phases:
  1. System Survey (years 1-2): deploy telescopes, map planets
  2. Orbit Selection (year 2-3): choose stable orbit
  3. Habitat Deployment (years 3-5): expand ship, deploy solar panels
  4. Resource Assessment (years 5-10): asteroid mining, water ice
  5. Surface Exploration (years 10-15): robotic probes to surface
  6. Colony Decision (year 15): vote to colonize or stay orbital
  7. Colony Establishment (years 15-30): build surface/orbital habitat
  8. Signal Home (ongoing): laser comm back to Sol
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class PlanetCandidate:
    name: str
    planet_type: str  # rocky, gas_giant, ice_giant, super_earth
    mass_earth: float = 1.0   # Earth-equivalent normalised units
    radius_earth: float = 1.0  # Earth-equivalent normalised units
    # 288 K = 15 °C global mean surface temperature for Earth baseline
    # (Hansen et al. 1981 *Science* 213 957; IPCC AR6 WG1 §2.3.1).
    surface_temp_k: float = 288.0  # Hansen 1981 Science 213 957 Earth baseline
    atmosphere: str = "none"
    water_present: bool = False
    habitability_score: float = 0.0  # 0-1
    tidally_locked: bool = False
    flare_risk: float = 0.0


@dataclass
class ArrivalState:
    phase: str = "APPROACH"
    year_since_arrival: float = 0.0
    system_surveyed: bool = False
    orbit_established: bool = False
    habitat_deployed: bool = False
    solar_panels_deployed: bool = False
    resource_survey_complete: bool = False
    surface_probes_landed: int = 0
    colony_decision_made: bool = False
    colony_type: str = ""  # "surface", "orbital", "undecided"
    colony_population: int = 0
    colony_food_production_kg_day: float = 0.0
    colony_power_kw: float = 0.0
    signal_sent_to_sol: bool = False
    signal_arrival_year: float = 0.0  # When Sol receives "we made it"
    planets_discovered: list = field(default_factory=list)
    asteroids_found: int = 0
    water_ice_found_tonnes: float = 0.0
    minerals_found: dict = field(default_factory=dict)


class ArrivalSimulator:
    """Simulates post-insertion activities at target star."""

    def __init__(self, star_distance_ly: float = 4.24, crew_size: int = 4,
                 launch_year: float = 0.0, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._crew = crew_size
        self._distance_ly = star_distance_ly
        self._launch_year = launch_year
        self.state = ArrivalState()

        # Generate target system
        self._generate_system()

    def _generate_system(self) -> None:
        """Generate planets for the target system."""
        # Proxima-like system
        self.state.planets_discovered = [
            PlanetCandidate(
                name="Target-b", planet_type="rocky", mass_earth=1.17,
                radius_earth=1.07, surface_temp_k=234, atmosphere="thin_CO2",
                water_present=True, habitability_score=0.6,
                tidally_locked=True, flare_risk=0.3,
            ),
            PlanetCandidate(
                name="Target-c", planet_type="super_earth", mass_earth=7.0,
                radius_earth=1.9, surface_temp_k=39, atmosphere="H2_He",
                habitability_score=0.1,
            ),
        ]

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events = []
        s = self.state
        s.year_since_arrival += 1
        yr = s.year_since_arrival

        # Phase 1: System Survey
        if yr == 1:
            s.phase = "SURVEY"
            s.asteroids_found = self._rng.randint(50, 500)
            events.append({"year": mission_year, "severity": "NOMINAL",
                           "message": f"System survey initiated. {len(s.planets_discovered)} planets, "
                                      f"{s.asteroids_found} asteroids detected.",
                           "subsystem": "arrival"})

        if yr == 2:
            s.system_surveyed = True
            best = max(s.planets_discovered, key=lambda p: p.habitability_score)
            events.append({"year": mission_year, "severity": "NOMINAL",
                           "message": f"Survey complete. Best candidate: {best.name} "
                                      f"(habitability {best.habitability_score:.0%}). "
                                      f"{'Tidally locked' if best.tidally_locked else 'Normal rotation'}.",
                           "subsystem": "arrival"})

        # Phase 2: Orbit Selection
        if yr == 3:
            s.phase = "ORBIT_SELECTION"
            s.orbit_established = True
            events.append({"year": mission_year, "severity": "NOMINAL",
                           "message": "Stable orbit established around Target-b. "
                                      "Station-keeping initiated.",
                           "subsystem": "arrival"})

        # Phase 3: Habitat Deployment
        if yr == 4:
            s.phase = "HABITAT_DEPLOYMENT"
            s.habitat_deployed = True
            s.solar_panels_deployed = True
            s.colony_power_kw = 500.0  # Solar panels!
            events.append({"year": mission_year, "severity": "NOMINAL",
                           "message": "Habitat modules expanded. Solar panels deployed — "
                                      f"first solar power in {self._distance_ly / 0.1 + yr:.0f} years! "
                                      f"Generating {s.colony_power_kw:.0f} kW.",
                           "subsystem": "arrival"})

        # Phase 4: Resource Assessment
        if 5 <= yr <= 10:
            s.phase = "RESOURCE_ASSESSMENT"
            # Mine asteroids for materials
            mined = self._rng.uniform(10, 100)
            s.water_ice_found_tonnes += mined * 0.3
            s.minerals_found["iron"] = s.minerals_found.get("iron", 0) + mined * 0.4
            s.minerals_found["nickel"] = s.minerals_found.get("nickel", 0) + mined * 0.1

            if yr == 5:
                events.append({"year": mission_year, "severity": "NOMINAL",
                               "message": "Asteroid mining operations begin. "
                                          "Replenishing depleted ship stores.",
                               "subsystem": "arrival"})
            if yr == 10:
                s.resource_survey_complete = True
                events.append({"year": mission_year, "severity": "NOMINAL",
                               "message": f"Resource survey complete. "
                                          f"Water ice: {s.water_ice_found_tonnes:.0f} tonnes. "
                                          f"Iron: {s.minerals_found.get('iron', 0):.0f} tonnes.",
                               "subsystem": "arrival"})

        # Phase 5: Surface Exploration
        if 10 <= yr <= 15:
            s.phase = "SURFACE_EXPLORATION"
            if yr == 11:
                s.surface_probes_landed = 3
                events.append({"year": mission_year, "severity": "NOMINAL",
                               "message": "3 robotic probes landed on Target-b nightside. "
                                          "Surface analysis in progress.",
                               "subsystem": "arrival"})

        # Phase 6: Colony Decision
        if yr == 15:
            s.phase = "COLONY_DECISION"
            s.colony_decision_made = True
            best = max(s.planets_discovered, key=lambda p: p.habitability_score)
            if best.habitability_score > 0.4:
                s.colony_type = "surface"
                events.append({"year": mission_year, "severity": "NOMINAL",
                               "message": f"Colony decision: SURFACE COLONY on {best.name}. "
                                          f"Habitability: {best.habitability_score:.0%}. "
                                          "Construction begins.",
                               "subsystem": "arrival"})
            else:
                s.colony_type = "orbital"
                events.append({"year": mission_year, "severity": "NOMINAL",
                               "message": "Colony decision: ORBITAL HABITAT. "
                                          "Planet not suitable for surface colony.",
                               "subsystem": "arrival"})

        # Phase 7: Colony Establishment
        if yr > 15:
            s.phase = "COLONY_ESTABLISHMENT"
            # Gradual colony growth
            s.colony_population = min(self._crew * 3, int(self._crew + (yr - 15) * 2))
            s.colony_food_production_kg_day = s.colony_population * 2.0 * 0.8
            s.colony_power_kw = 500 + (yr - 15) * 50

            if yr == 20:
                events.append({"year": mission_year, "severity": "NOMINAL",
                               "message": f"Colony population: {s.colony_population}. "
                                          f"Food self-sufficiency: {s.colony_food_production_kg_day / max(s.colony_population * 2, 1):.0%}.",
                               "subsystem": "arrival"})

        # Signal home
        if yr == 1 and not s.signal_sent_to_sol:
            s.signal_sent_to_sol = True
            s.signal_arrival_year = self._launch_year + self._distance_ly / 0.1 + yr + self._distance_ly
            events.append({"year": mission_year, "severity": "NOMINAL",
                           "message": f"'WE MADE IT' signal transmitted to Sol. "
                                      f"Arrival at Earth in {self._distance_ly:.1f} years "
                                      f"(year {s.signal_arrival_year:.0f} mission time).",
                           "subsystem": "communication"})

        return events


class CompleteInterstellarMission:
    """Chains: travel → brake → arrive → colonize."""

    def __init__(self, target_distance_ly: float = 4.24, crew_size: int = 4,
                 seed: int = 42) -> None:
        self._distance = target_distance_ly
        self._crew = crew_size
        self._seed = seed

    def run(self, colonization_years: int = 30) -> dict[str, Any]:
        from aria.simulation.generation_ship import GenerationShipSimulation, GenerationShipConfig

        travel_years = int(self._distance / 0.1) + 17  # +17 for braking
        cfg = GenerationShipConfig.breakthrough(seed=self._seed)
        cfg.target_distance_ly = self._distance

        # Phase 1: Travel + Braking
        travel_sim = GenerationShipSimulation(cfg)
        travel_r = travel_sim.run(travel_years)

        # Phase 2: Arrival + Colonization
        arrival = ArrivalSimulator(
            star_distance_ly=self._distance,
            crew_size=self._crew,
            launch_year=0,
            seed=self._seed,
        )
        arrival_events = []
        for yr in range(1, colonization_years + 1):
            events = arrival.simulate_year(float(travel_years + yr))
            arrival_events.extend(events)

        return {
            "target_distance_ly": self._distance,
            "travel_years": travel_years,
            "colonization_years": colonization_years,
            "total_years": travel_years + colonization_years,
            "travel_survived": travel_r.ship_survived,
            "travel_events": travel_r.total_events,
            "arrival_events": len(arrival_events),
            "total_events": travel_r.total_events + len(arrival_events),
            "colony_type": arrival.state.colony_type,
            "colony_population": arrival.state.colony_population,
            "water_ice_found": arrival.state.water_ice_found_tonnes,
            "signal_sent": arrival.state.signal_sent_to_sol,
            "hull_integrity": travel_r.final_hull_integrity,
        }
