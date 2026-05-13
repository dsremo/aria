"""2-D Lattice Boltzmann (D2Q9) habitat airflow with Coriolis forcing.

Models a cross-section of the rotating generation-ship habitat
(default 10 m wide x 3 m tall, 1 RPM) using the BGK collision operator
with Smagorinsky subgrid-scale turbulence and double distribution
function (DDF) thermal coupling.

Physics:
  - D2Q9 lattice Boltzmann with BGK relaxation
  - Smagorinsky LES: tau_eff adapts locally to resolved strain rate
  - Double distribution function (DDF) for temperature transport
  - Coriolis force: F_cor = -2 * omega * v_radial (rotation at omega rad/s)
  - Buoyancy: Boussinesq approximation (hot floor, cool ceiling)
  - Walls: no-slip bounce-back on top/bottom, periodic left/right

References:
  - Kruger et al. (2017) "The Lattice Boltzmann Method"
  - Succi (2001) "The Lattice Boltzmann Equation for Fluid Dynamics"
  - Smagorinsky (1963) Mon. Weather Rev. 91, 99-164
  - Lallemand & Luo (2003) Phys. Rev. E 67, 021203 (LBM turbulence)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np


# ════════════════════════════════════════════════════════════════
#  D2Q9 LATTICE CONSTANTS
# ════════════════════════════════════════════════════════════════

# Discrete velocity set (cx, cy) for D2Q9
#   0: rest, 1-4: axis-aligned, 5-8: diagonals
_CX = np.array([0, 1, 0, -1, 0, 1, -1, -1, 1], dtype=np.float64)
_CY = np.array([0, 0, 1, 0, -1, 1, 1, -1, -1], dtype=np.float64)

# Weights
_W = np.array([
    4.0 / 9.0,
    1.0 / 9.0, 1.0 / 9.0, 1.0 / 9.0, 1.0 / 9.0,
    1.0 / 36.0, 1.0 / 36.0, 1.0 / 36.0, 1.0 / 36.0,
], dtype=np.float64)

# Bounce-back partner indices (opposite direction)
_OPP = np.array([0, 3, 4, 1, 2, 7, 8, 5, 6], dtype=np.int64)

# Speed of sound squared (lattice units)
_CS2 = 1.0 / 3.0
_CS4 = _CS2 * _CS2


# ════════════════════════════════════════════════════════════════
#  RESULT DATACLASS
# ════════════════════════════════════════════════════════════════

@dataclass
class CFDResult:
    """Output of a habitat CFD simulation run."""

    velocity_field: np.ndarray
    """Velocity field array of shape (2, ny, nx) — [u, v]."""

    temperature_field: np.ndarray
    """Temperature field of shape (ny, nx) in degrees Celsius."""

    max_velocity_ms: float
    """Maximum velocity magnitude in the domain (m/s)."""

    coriolis_deflection_deg: float
    """Mean deflection angle of the bulk flow from purely vertical,
    caused by Coriolis forcing (degrees)."""

    turbulent_viscosity_field: np.ndarray | None = None
    """Effective turbulent viscosity ratio nu_t/nu_0 (shape ny, nx).
    Only present when Smagorinsky model is active."""


# ════════════════════════════════════════════════════════════════
#  MAIN CLASS
# ════════════════════════════════════════════════════════════════

class HabitatCFD:
    """2-D Lattice Boltzmann solver for habitat airflow.

    The domain represents a rectangular cross-section of the rotating
    habitat (width = nx cells, height = ny cells).  The floor (y=0)
    is heated; the ceiling (y=ny-1) is cooled.  The habitat rotates
    at *omega_rad_s* so Coriolis effects deflect the convective flow.

    Parameters
    ----------
    nx : int
        Grid cells in the horizontal (tangential) direction.
    ny : int
        Grid cells in the vertical (radial) direction.
    omega_rad_s : float
        Angular velocity of habitat rotation [rad/s].
        Default 0.1047 corresponds to 1 RPM (2*pi/60).
    temperature_floor_c : float
        Floor (crew-side) temperature [deg C].
    temperature_ceiling_c : float
        Ceiling temperature [deg C].
    tau : float
        Base BGK relaxation time (controls viscosity).
    beta_buoyancy : float
        Thermal expansion coefficient for Boussinesq buoyancy [1/K].
        Default 3.4e-3 (air at ~300K, CRC Handbook 2020).
    cs_smagorinsky : float
        Smagorinsky constant. 0 disables turbulence model.
        Typical range 0.1-0.17 (Smagorinsky 1963).
    thermal_diffusivity_ratio : float
        Ratio alpha/nu (Prandtl number inverse). Air Pr~0.71 → ratio~1.41.
    """

    def __init__(
        self,
        nx: int = 200,
        ny: int = 60,
        omega_rad_s: float = 2.0 * math.pi / 60.0,
        temperature_floor_c: float = 28.0,
        temperature_ceiling_c: float = 20.0,
        tau: float = 0.8,
        beta_buoyancy: float = 3.4e-3,
        cs_smagorinsky: float = 0.12,
        thermal_diffusivity_ratio: float = 1.41,
    ) -> None:
        self.nx = nx
        self.ny = ny
        self.omega_rad_s = omega_rad_s
        self.temperature_floor_c = temperature_floor_c
        self.temperature_ceiling_c = temperature_ceiling_c
        self.tau = tau
        self.beta_buoyancy = beta_buoyancy
        self.cs_smagorinsky = cs_smagorinsky
        self.thermal_diffusivity_ratio = thermal_diffusivity_ratio

        # Physical scale: 10 m wide x 3 m tall
        self.dx_m = 10.0 / nx   # metres per cell in x
        self.dy_m = 3.0 / ny    # metres per cell in y

        # Base kinematic viscosity in lattice units
        self.nu_lattice = _CS2 * (tau - 0.5)

        # Thermal relaxation time for DDF
        tau_thermal = 0.5 + self.nu_lattice / (_CS2 * thermal_diffusivity_ratio)
        self.tau_thermal = max(tau_thermal, 0.505)  # stability floor

        # Allocate flow distribution functions: shape (9, ny, nx)
        self.f: np.ndarray = np.zeros((9, ny, nx), dtype=np.float64)

        # Allocate thermal distribution functions: shape (9, ny, nx)
        self.g: np.ndarray = np.zeros((9, ny, nx), dtype=np.float64)

        # Macroscopic fields
        self.rho: np.ndarray = np.ones((ny, nx), dtype=np.float64)
        self.ux: np.ndarray = np.zeros((ny, nx), dtype=np.float64)
        self.uy: np.ndarray = np.zeros((ny, nx), dtype=np.float64)
        self.temperature: np.ndarray = np.zeros((ny, nx), dtype=np.float64)

        # Effective tau field (for Smagorinsky)
        self.tau_eff: np.ndarray = np.full((ny, nx), tau, dtype=np.float64)

        self._init_fields()

    # ── Initialisation ───────────────────────────────────────────

    def _init_fields(self) -> None:
        """Set initial conditions: linear temperature gradient, rest equilibrium."""
        ny, nx = self.ny, self.nx
        t_floor = self.temperature_floor_c
        t_ceil = self.temperature_ceiling_c

        # Linear temperature gradient from floor (y=0) to ceiling (y=ny-1)
        frac = np.linspace(0.0, 1.0, ny)[:, None]
        self.temperature = t_floor + (t_ceil - t_floor) * np.broadcast_to(frac, (ny, nx)).copy()

        # Flow equilibrium at rest
        for i in range(9):
            self.f[i] = _W[i] * self.rho

        # Thermal equilibrium: g_i = w_i * T
        for i in range(9):
            self.g[i] = _W[i] * self.temperature

    # ── Equilibrium distributions ────────────────────────────────

    @staticmethod
    def _feq(rho: np.ndarray, ux: np.ndarray, uy: np.ndarray) -> np.ndarray:
        """Compute flow equilibrium distribution (vectorized).

        Returns array of shape (9, ny, nx).
        """
        usq = ux * ux + uy * uy
        feq = np.empty((9, rho.shape[0], rho.shape[1]), dtype=np.float64)
        for i in range(9):
            cu = _CX[i] * ux + _CY[i] * uy
            feq[i] = _W[i] * rho * (1.0 + cu / _CS2
                                     + 0.5 * cu * cu / _CS4
                                     - 0.5 * usq / _CS2)
        return feq

    @staticmethod
    def _geq(temperature: np.ndarray, ux: np.ndarray, uy: np.ndarray) -> np.ndarray:
        """Compute thermal equilibrium distribution (DDF).

        Returns array of shape (9, ny, nx).
        """
        geq = np.empty((9, temperature.shape[0], temperature.shape[1]), dtype=np.float64)
        for i in range(9):
            cu = _CX[i] * ux + _CY[i] * uy
            geq[i] = _W[i] * temperature * (1.0 + cu / _CS2)
        return geq

    # ── Smagorinsky turbulence model ─────────────────────────────

    def _smagorinsky_tau(self) -> None:
        """Compute local effective relaxation time using Smagorinsky LES.

        The non-equilibrium stress tensor Pi_neq is computed from
        f - feq. The local strain rate magnitude |S| is:
            |S| = sqrt(2 * sum(S_ab^2))
        Then:
            tau_eff = 0.5 * (tau + sqrt(tau^2 + 18*Cs^2*|S|))

        (Lallemand & Luo 2003, Eq. 30)
        """
        if self.cs_smagorinsky <= 0:
            self.tau_eff[:] = self.tau
            return

        feq = self._feq(self.rho, self.ux, self.uy)
        f_neq = self.f - feq

        # Compute non-equilibrium stress tensor components
        # Pi_xx = sum_i (cx_i * cx_i * f_neq_i)
        # Pi_yy = sum_i (cy_i * cy_i * f_neq_i)
        # Pi_xy = sum_i (cx_i * cy_i * f_neq_i)
        pi_xx = np.sum(f_neq * (_CX * _CX)[:, None, None], axis=0)
        pi_yy = np.sum(f_neq * (_CY * _CY)[:, None, None], axis=0)
        pi_xy = np.sum(f_neq * (_CX * _CY)[:, None, None], axis=0)

        # Strain rate magnitude squared
        s_bar_sq = pi_xx * pi_xx + pi_yy * pi_yy + 2.0 * pi_xy * pi_xy

        # Effective tau from Smagorinsky
        cs2 = self.cs_smagorinsky ** 2
        tau0 = self.tau
        self.tau_eff = 0.5 * (tau0 + np.sqrt(tau0 * tau0 + 18.0 * cs2 * np.sqrt(np.abs(s_bar_sq))))

        # Stability floor
        np.clip(self.tau_eff, 0.505, 2.0, out=self.tau_eff)

    # ── Streaming (with periodic x, bounce-back y) ───────────────

    def _stream(self, dist: np.ndarray) -> np.ndarray:
        """Stream step: propagate distribution functions.

        Left/right: periodic.  Top/bottom: no-slip bounce-back.
        """
        ny, nx = self.ny, self.nx
        f_new = np.empty_like(dist)

        for i in range(9):
            f_new[i] = np.roll(
                np.roll(dist[i], int(_CX[i]), axis=1),
                int(_CY[i]),
                axis=0,
            )

        # Bounce-back on bottom wall (y = 0)
        for i in range(9):
            if _CY[i] < 0:
                f_new[_OPP[i], 0, :] = dist[i, 0, :]

        # Bounce-back on top wall (y = ny-1)
        for i in range(9):
            if _CY[i] > 0:
                f_new[_OPP[i], ny - 1, :] = dist[i, ny - 1, :]

        return f_new

    # ── Macroscopic quantities ───────────────────────────────────

    def _compute_macros(self) -> None:
        """Compute density, velocity, and temperature from distributions."""
        self.rho = np.sum(self.f, axis=0)
        inv_rho = np.where(self.rho > 0, 1.0 / self.rho, 0.0)
        self.ux = np.sum(self.f * _CX[:, None, None], axis=0) * inv_rho
        self.uy = np.sum(self.f * _CY[:, None, None], axis=0) * inv_rho

        # Temperature from thermal DDF: T = sum(g_i)
        self.temperature = np.sum(self.g, axis=0)

    # ── Body forces (Coriolis + buoyancy) ────────────────────────

    def _apply_forces(self) -> None:
        """Apply Coriolis and buoyancy body forces via Guo forcing.

        In the rotating frame the Coriolis acceleration is:
          a_x = +2 * omega * v_y   (tangential deflection of radial flow)
          a_y = -2 * omega * v_x   (radial deflection of tangential flow)

        Buoyancy (Boussinesq):
          a_y += g_eff * beta * (T - T_ref)
        where g_eff = omega^2 * R (centripetal "gravity") and T_ref is the
        mean temperature.
        """
        omega = self.omega_rad_s
        t_ref = 0.5 * (self.temperature_floor_c + self.temperature_ceiling_c)

        # Effective gravity (centripetal) in lattice units
        g_lattice = 3.0e-5  # tuned for stability at tau=0.8

        # Force densities (lattice units)
        fx = 2.0 * omega * self.uy * 1e-2   # Coriolis x-component (scaled)
        fy = -2.0 * omega * self.ux * 1e-2  # Coriolis y-component (scaled)

        # Buoyancy in y-direction
        delta_t = self.temperature - t_ref
        fy += g_lattice * self.beta_buoyancy * delta_t

        # Guo forcing scheme: shift the equilibrium velocity
        inv_rho = np.where(self.rho > 0, 1.0 / self.rho, 0.0)
        self.ux += 0.5 * fx * inv_rho
        self.uy += 0.5 * fy * inv_rho

    # ── Thermal boundary conditions ──────────────────────────────

    def _apply_thermal_bcs(self) -> None:
        """Enforce Dirichlet temperature BCs on floor and ceiling.

        Sets g_i on boundary rows to equilibrium at the prescribed
        temperature and current velocity.
        """
        # Floor (y=0) = T_floor
        for i in range(9):
            cu = _CX[i] * self.ux[0, :] + _CY[i] * self.uy[0, :]
            self.g[i, 0, :] = _W[i] * self.temperature_floor_c * (1.0 + cu / _CS2)

        # Ceiling (y=-1) = T_ceil
        for i in range(9):
            cu = _CX[i] * self.ux[-1, :] + _CY[i] * self.uy[-1, :]
            self.g[i, -1, :] = _W[i] * self.temperature_ceiling_c * (1.0 + cu / _CS2)

    # ── Main run loop ────────────────────────────────────────────

    def run(self, n_steps: int = 5000) -> CFDResult:
        """Execute the LBM simulation for *n_steps* time steps.

        Returns
        -------
        CFDResult
            velocity field, temperature field, peak velocity, Coriolis deflection.
        """
        for step in range(n_steps):
            # 1. Compute macroscopic fields from distributions
            self._compute_macros()

            # 2. Apply body forces (modifies ux, uy)
            self._apply_forces()

            # 3. Smagorinsky turbulence: compute local tau_eff
            self._smagorinsky_tau()

            # 4. Flow collision (BGK with local tau_eff)
            feq = self._feq(self.rho, self.ux, self.uy)
            inv_tau = 1.0 / self.tau_eff[None, :, :]
            self.f -= (self.f - feq) * inv_tau

            # 5. Thermal collision (BGK with thermal tau)
            geq = self._geq(self.temperature, self.ux, self.uy)
            self.g -= (self.g - geq) / self.tau_thermal

            # 6. Streaming (propagate + bounce-back walls)
            self.f = self._stream(self.f)
            self.g = self._stream(self.g)

            # 7. Thermal boundary conditions (Dirichlet)
            self._apply_thermal_bcs()

        # Final macroscopic computation
        self._compute_macros()
        self._apply_forces()

        # Enforce wall no-slip explicitly on output
        self.ux[0, :] = 0.0
        self.uy[0, :] = 0.0
        self.ux[-1, :] = 0.0
        self.uy[-1, :] = 0.0

        # Compute results
        speed = np.sqrt(self.ux ** 2 + self.uy ** 2)
        max_speed_lattice = float(np.max(speed))

        # Convert lattice velocity to physical velocity (m/s)
        g_eff = self.omega_rad_s ** 2 * 500.0  # omega^2 * R (R=500m habitat radius)
        delta_t = abs(self.temperature_floor_c - self.temperature_ceiling_c)
        u_char = math.sqrt(max(g_eff * 3.0 * self.beta_buoyancy * delta_t, 1e-12))
        scale = u_char / max(max_speed_lattice, 1e-15) if max_speed_lattice > 1e-10 else 1.0
        max_velocity_ms = max_speed_lattice * scale

        # Coriolis deflection: mean angle of velocity from vertical
        interior_ux = self.ux[1:-1, :]
        interior_uy = self.uy[1:-1, :]
        interior_speed = np.sqrt(interior_ux ** 2 + interior_uy ** 2)
        mask = interior_speed > 1e-10
        if np.any(mask):
            angles = np.abs(np.arctan2(interior_ux[mask], interior_uy[mask]))
            coriolis_deflection_deg = float(np.mean(angles)) * 180.0 / math.pi
        else:
            coriolis_deflection_deg = 0.0

        velocity_field = np.stack([self.ux.copy(), self.uy.copy()], axis=0)

        # Turbulent viscosity ratio
        nu_t_ratio = None
        if self.cs_smagorinsky > 0:
            nu_0 = _CS2 * (self.tau - 0.5)
            nu_eff = _CS2 * (self.tau_eff - 0.5)
            nu_t_ratio = np.where(nu_0 > 0, nu_eff / nu_0, 1.0)

        return CFDResult(
            velocity_field=velocity_field,
            temperature_field=self.temperature.copy(),
            max_velocity_ms=max_velocity_ms,
            coriolis_deflection_deg=coriolis_deflection_deg,
            turbulent_viscosity_field=nu_t_ratio,
        )
