"""Magsail-ISM Particle-In-Cell (PIC) Interaction Model.

Simulates the interaction between a magnetic sail and the interstellar medium
using a simplified Particle-In-Cell approach.

MAGSAIL PHYSICS (Zubrin & Andrews, 1991):
  A superconducting loop creates a magnetic dipole field.
  ISM ions (mostly protons) are deflected by the field → momentum transfer → drag.

  Drag force: F = Cd × ½ × ρ_ISM × v² × A_eff
  Where:
    Cd ≈ 4.0 for magnetic sail (Funaki et al. 2007)
    ρ_ISM = n × m_p (ISM density × proton mass)
    v = ship velocity
    A_eff = effective capture area of magnetic field

MAGNETIC FIELD:
  Dipole: B(r) = (μ₀/4π) × m / r³  (along axis)
  Where m = I × A = current × loop area
  ISM proton Larmor radius: r_L = m_p × v / (q × B)
  Effective area: A_eff ≈ π × r_mag² where r_mag = magnetopause radius

MAGNETOPAUSE (balance of magnetic and dynamic pressure):
  ½ρv² = B²/(2μ₀)
  → r_mag = [μ₀ × m² / (8π² × ρ × v²)]^(1/6)

ISM PHASES (from relativistic_physics.py):
  - Hot Ionized: n = 0.003 cm⁻³, T = 10⁶ K
  - Warm Ionized: n = 0.1 cm⁻³, T = 8000 K
  - Warm Neutral: n = 0.3 cm⁻³, T = 8000 K
  - Cold Neutral: n = 30 cm⁻³, T = 80 K
  - Local Bubble: n = 0.005 cm⁻³, T = 10⁶ K

PIC SIMPLIFICATION:
  Full PIC is computationally infeasible for the main simulation loop.
  We use pre-computed scaling laws from published PIC studies:
  - Funaki et al. (2007): "Thrust characteristics of magsail" AIAA
  - Nishida et al. (2006): "Verification of momentum transfer" AIAA
  - Cattell et al. (2019): "MHD simulation of M2P2" JGR Space Physics

References:
  - Zubrin & Andrews (1991): "Magnetic sails and interstellar travel"
    JBIS 44, 265-272
  - Andrews & Zubrin (1990): "Magnetic sails and interplanetary travel"
    AIAA-90-2367
  - Funaki et al. (2007): "Trust production of magneto plasma sail"
    AIAA-2007-5021
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

# Physical constants
MU_0 = 4 * math.pi * 1e-7       # Vacuum permeability (H/m)
M_PROTON = 1.6726e-27            # Proton mass (kg)
Q_PROTON = 1.6022e-19            # Proton charge (C)
C_LIGHT = 299_792_458.0          # Speed of light (m/s)
AU_TO_M = 1.496e11               # AU to meters
LY_TO_M = 9.461e15               # Light-year to meters

# ISM phases: (density_cm3, temperature_K, ionization_fraction)
ISM_PHASES = {
    "local_bubble": (0.005, 1e6, 0.9),
    "hot_ionized": (0.003, 1e6, 1.0),
    "warm_ionized": (0.1, 8000, 1.0),
    "warm_neutral": (0.3, 8000, 0.1),
    "cold_neutral": (30.0, 80, 0.001),
}


@dataclass
class MagsailState:
    """State of the magnetic sail system."""
    # Coil parameters
    loop_radius_m: float = 50_000.0  # 50 km radius superconducting loop
    current_a: float = 1e9           # 1 GA (superconducting)
    coil_mass_kg: float = 1e5        # 100 tonnes of HTS wire

    # Magnetic moment: m = I × π × R²
    magnetic_moment_am2: float = 0.0  # Computed

    # Performance
    magnetopause_radius_m: float = 0.0  # Effective capture radius
    effective_area_m2: float = 0.0
    drag_force_n: float = 0.0
    deceleration_ms2: float = 0.0
    power_dissipated_w: float = 0.0

    # ISM environment
    ism_phase: str = "local_bubble"
    ism_density_cm3: float = 0.005
    ism_temperature_k: float = 1e6
    ism_ionization: float = 0.9

    # Particle interaction stats (from PIC model)
    protons_deflected_per_s: float = 0.0
    mean_deflection_angle_deg: float = 0.0
    ion_larmor_radius_m: float = 0.0

    # Coil health
    coil_health: float = 1.0
    quench_events: int = 0


@dataclass
class PICParticle:
    """A macro-particle in the PIC simulation."""
    x: float = 0.0   # Position (m)
    y: float = 0.0
    vx: float = 0.0  # Velocity (m/s)
    vy: float = 0.0
    charge: float = Q_PROTON
    mass: float = M_PROTON
    weight: float = 1.0  # Number of real particles this represents


class MagsailPICSimulator:
    """Simplified PIC simulation of magsail-ISM interaction.

    Uses pre-computed scaling laws for the main simulation loop,
    with a detailed PIC kernel available for specific analysis.
    """

    def __init__(
        self,
        loop_radius_m: float = 50_000.0,
        current_a: float = 1e9,
        ship_mass_kg: float = 1e8,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._ship_mass = ship_mass_kg
        self.state = MagsailState(
            loop_radius_m=loop_radius_m,
            current_a=current_a,
        )
        self.state.magnetic_moment_am2 = current_a * math.pi * loop_radius_m ** 2
        self._update_derived(0.1 * C_LIGHT)

    def _update_derived(self, velocity_ms: float) -> None:
        """Update derived quantities from current state."""
        s = self.state
        v = max(velocity_ms, 1.0)  # Avoid div by zero

        # ISM mass density
        n = s.ism_density_cm3 * 1e6  # Convert cm⁻³ to m⁻³
        rho = n * M_PROTON  # Only protons for simplification

        # Magnetopause radius: r_mag = [μ₀ m² / (8π² ρ v²)]^(1/6)
        # From pressure balance: B²/(2μ₀) = ½ρv²
        if rho > 0 and v > 0:
            numerator = MU_0 * s.magnetic_moment_am2 ** 2
            denominator = 8 * math.pi ** 2 * rho * v ** 2
            if denominator > 0:
                s.magnetopause_radius_m = (numerator / denominator) ** (1.0 / 6.0)
            else:
                s.magnetopause_radius_m = s.loop_radius_m
        else:
            s.magnetopause_radius_m = s.loop_radius_m

        s.effective_area_m2 = math.pi * s.magnetopause_radius_m ** 2

        # Drag force: F = Cd × ½ρv² × A_eff
        # Cd ≈ 4.0 for magnetic sail (Funaki et al. 2007)
        # Only ionized fraction contributes
        cd = 4.0
        rho_ion = rho * s.ism_ionization
        s.drag_force_n = cd * 0.5 * rho_ion * v ** 2 * s.effective_area_m2 * s.coil_health

        # Deceleration
        s.deceleration_ms2 = s.drag_force_n / self._ship_mass if self._ship_mass > 0 else 0

        # Ion Larmor radius at the magnetopause. The dipole field
        # at |r| = r_mag is `B = μ₀ M / (4π r³)` (Griffiths 2017
        # *Introduction to Electrodynamics* 4th ed eq. 5.88), and
        # the gyroradius follows the Pod D1 ion_gyroradius
        # primitive
        # `ρ_i = m v_⊥ / (|q| B)` (Chen 2016 *Introduction to
        # Plasma Physics* 3rd ed eq. 1.10).
        b_magnetopause = MU_0 * s.magnetic_moment_am2 / (4 * math.pi * s.magnetopause_radius_m ** 3)
        if b_magnetopause > 0:
            from aria.physics.mhd_plasma import ion_gyroradius

            s.ion_larmor_radius_m = ion_gyroradius(
                ion_mass_kg=M_PROTON,
                perpendicular_velocity_m_s=v,
                charge_number=1,
                magnetic_field_t=b_magnetopause,
            )
        else:
            s.ion_larmor_radius_m = float('inf')

        # Proton deflection rate
        s.protons_deflected_per_s = n * s.ism_ionization * v * s.effective_area_m2

        # Mean deflection angle (from PIC scaling: θ ∝ r_L / r_mag)
        if s.magnetopause_radius_m > 0 and s.ion_larmor_radius_m > 0:
            ratio = s.ion_larmor_radius_m / s.magnetopause_radius_m
            s.mean_deflection_angle_deg = min(180, 90 * (1 - ratio)) if ratio < 1 else 5.0
        else:
            s.mean_deflection_angle_deg = 0.0

        # Ohmic dissipation: zero for ideal superconductor
        # But AC losses from fluctuating ISM: P ∝ f × B² × V_wire
        # Estimated ~1 kW for large sail (Zubrin 1991)
        s.power_dissipated_w = 1000.0 * s.coil_health

    def set_ism_phase(self, phase: str) -> None:
        """Set ISM environment phase."""
        if phase in ISM_PHASES:
            density, temp, ionization = ISM_PHASES[phase]
            self.state.ism_phase = phase
            self.state.ism_density_cm3 = density
            self.state.ism_temperature_k = temp
            self.state.ism_ionization = ionization

    def run_pic_snapshot(
        self, velocity_ms: float, n_particles: int = 1000
    ) -> dict[str, Any]:
        """Run a simplified 2D PIC snapshot.

        Traces n_particles through the magnetic field and computes
        momentum transfer statistics.
        """
        s = self.state
        self._update_derived(velocity_ms)

        # Initialize particles upstream
        r_max = s.magnetopause_radius_m * 2
        deflected = 0
        captured = 0
        total_momentum_transfer = 0.0

        for i in range(n_particles):
            # Random impact parameter (y position)
            y0 = self._rng.uniform(-r_max, r_max)
            particle = PICParticle(
                x=-r_max, y=y0,
                vx=velocity_ms, vy=0.0,
            )

            # Trace through field (simplified Boris pusher)
            dt = s.magnetopause_radius_m / velocity_ms / 100  # 100 steps across
            initial_vx = particle.vx

            for step in range(200):
                r = math.sqrt(particle.x ** 2 + particle.y ** 2)
                if r < 1.0:
                    r = 1.0  # Avoid singularity

                # Dipole field (simplified 2D)
                if r < s.magnetopause_radius_m * 3:
                    b_z = s.magnetic_moment_am2 * MU_0 / (4 * math.pi * r ** 3)
                else:
                    b_z = 0.0

                # Lorentz force: F = qv×B
                # In 2D with B in z: Fx = q*vy*Bz, Fy = -q*vx*Bz
                ax = particle.charge * particle.vy * b_z / particle.mass
                ay = -particle.charge * particle.vx * b_z / particle.mass

                particle.vx += ax * dt
                particle.vy += ay * dt
                particle.x += particle.vx * dt
                particle.y += particle.vy * dt

                # Check if passed through
                if particle.x > r_max:
                    break

            # Momentum change
            delta_px = particle.mass * (initial_vx - particle.vx)
            total_momentum_transfer += abs(delta_px)

            if abs(particle.vy) > 0.01 * velocity_ms:
                deflected += 1
            if particle.x < 0 and step >= 199:
                captured += 1

        # Scale to real flux
        real_flux = s.ism_density_cm3 * 1e6 * velocity_ms * s.effective_area_m2
        scale_factor = real_flux / max(n_particles, 1)

        return {
            "n_particles": n_particles,
            "deflected": deflected,
            "deflection_fraction": deflected / max(n_particles, 1),
            "captured": captured,
            "total_momentum_transfer_ns": total_momentum_transfer * 1e9,
            "scaled_force_n": total_momentum_transfer * scale_factor,
            "magnetopause_radius_km": s.magnetopause_radius_m / 1000,
            "effective_area_km2": s.effective_area_m2 / 1e6,
            "drag_force_n": s.drag_force_n,
            "deceleration_ms2": s.deceleration_ms2,
        }

    def simulate_year(self, mission_year: float, velocity_c: float = 0.1) -> list[dict[str, Any]]:
        """Simulate one year of magsail operation."""
        events: list[dict[str, Any]] = []
        velocity_ms = velocity_c * C_LIGHT
        self._update_derived(velocity_ms)
        s = self.state

        # Superconductor degradation from radiation + micrometeorite impacts
        radiation_damage = 0.001 * mission_year ** 0.5  # Slow cumulative
        s.coil_health = max(0.3, 1.0 - radiation_damage)

        # Quench risk: probability increases with age and ISM density
        quench_prob = 0.01 * (1.0 + s.ism_density_cm3 / 0.1) * (2.0 - s.coil_health)
        if self._rng.random() < quench_prob:
            s.quench_events += 1
            s.coil_health *= 0.95  # Permanent damage from quench
            events.append({
                "year": mission_year,
                "severity": "WARNING",
                "message": f"Magsail quench event #{s.quench_events}! "
                           f"Coil health: {s.coil_health:.1%}. "
                           f"Re-energizing superconductor.",
                "subsystem": "magsail",
            })

        # ISM phase transitions (simplified: stays in Local Bubble for first 50 ly)
        distance_ly = velocity_c * mission_year
        if distance_ly < 50:
            self.set_ism_phase("local_bubble")
        elif distance_ly < 200:
            self.set_ism_phase("warm_ionized")
        else:
            self.set_ism_phase("hot_ionized")

        # Delta-v from magsail this year
        if s.drag_force_n > 0:
            delta_v_year = s.deceleration_ms2 * 3.156e7  # seconds per year
            events.append({
                "year": mission_year,
                "severity": "NOMINAL",
                "message": f"Magsail: drag {s.drag_force_n:.2e} N, "
                           f"Δv={delta_v_year:.1f} m/s/yr, "
                           f"r_mag={s.magnetopause_radius_m/1e3:.0f} km, "
                           f"ISM={s.ism_phase} ({s.ism_density_cm3} cm⁻³)",
                "subsystem": "magsail",
            })

        # Critical: coil failing
        if s.coil_health < 0.5:
            events.append({
                "year": mission_year,
                "severity": "CRITICAL",
                "message": f"Magsail coil degraded to {s.coil_health:.1%}. "
                           "Braking capability severely reduced.",
                "subsystem": "magsail",
            })

        return events

    def get_report(self) -> dict[str, Any]:
        s = self.state
        return {
            "magnetic_moment_am2": s.magnetic_moment_am2,
            "magnetopause_radius_km": s.magnetopause_radius_m / 1000,
            "effective_area_km2": s.effective_area_m2 / 1e6,
            "drag_force_n": s.drag_force_n,
            "deceleration_ms2": s.deceleration_ms2,
            "coil_health": s.coil_health,
            "quench_events": s.quench_events,
            "ism_phase": s.ism_phase,
            "protons_deflected_per_s": s.protons_deflected_per_s,
            "mean_deflection_angle_deg": s.mean_deflection_angle_deg,
        }
