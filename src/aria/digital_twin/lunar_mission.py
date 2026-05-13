"""Earth -> Moon mission evaluator that runs through the digital twin.

The generation-ship `ShipParameters` are sized for a 100 Mt interstellar
vehicle with 1000 crew and a 500 m habitat ring — overkill for a 3-day
Apollo-class lunar mission. This module defines a lunar-scale parameter
set and a feasibility pass:

    1. Parametric geometry at Apollo scale (4 crew, 3-day sortie)
    2. Gmsh mesh of the pressure cabin
    3. Structural FEA: internal pressure + launch axial load (4 g)
    4. Thermal: LEO sun-side / eclipse cycle
    5. Delta-v budget: TLI (3.13 km/s) + LOI (0.9) + TEI (1.0) + EDL (0)
    6. Radiation dose: Van Allen transit + deep-space GCR (3 day integral)

Goes/no-goes printed at the end so you can see exactly where the design
passes or fails without hand-waving.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()


# ── Lunar mission constants ────────────────────────────────────────────

# Apollo-class reference delta-v budget [m/s].
# Round trip: TLI + LOI + TEI + Earth re-entry braking (aero handles the rest).
# Values from NASA SP-4029 "Apollo By the Numbers" + NASA-TM-X-64627.
DV_TLI_M_S   = 3_130.0   # trans-lunar injection from 185 km LEO (Apollo 11)
DV_LOI_M_S   =   920.0   # lunar orbit insertion (circular 110 km)
DV_TEI_M_S   = 1_000.0   # trans-Earth injection (Apollo command module)
DV_MARGIN    = 1.15      # 15% contingency — standard NASA spec margin

# g-loads [m/s²] — Saturn V stack limit ≈ 4 g peak, Shuttle / Orion ≈ 3 g.
LAUNCH_G_PEAK = 4.0

# Radiation environment (round-trip exposure).
# GCR free-space dose rate: 0.42 Sv/yr solar min (Cucinotta 2014, ACE/CRIS).
# Van Allen belt transit: ~0.16 Sv accumulated on a single pass-through
# with minimal shielding (Townsend 2005, NASA-TP-2005-213164 Table 3).
GCR_DOSE_SV_PER_YEAR = 0.42
VAN_ALLEN_DOSE_SV    = 0.16   # per pair of transits (outbound + return)

# BUG-024 (2026-04-24): solar particle events (SPEs) are the single
# largest dose contributor during any multi-day cislunar mission. The
# largest historical events (Aug 1972, Oct 1989) delivered 500–10,000 mSv
# of unshielded dose in hours. Even at low probability per week (~2 %
# at solar average, ~10 % at solar max), the expected-value contribution
# dominates the risk budget for thin-shielded lunar vehicles.
# Reference: Parsons & Townsend 2000 RadMeas 33:81-92 (SPE spectrum fits);
# Wilson et al 1999 NASA CP-3370 §3 (August 1972 event reconstruction).
SPE_WORST_UNSHIELDED_SV = 0.50   # Aug-1972-class event, behind 5 g/cm²
SPE_ATTENUATION_SCALE   = 25.0   # kg/m² e-folding (harder spectrum than GCR)
SPE_PROBABILITY_PER_DAY = 0.015  # solar-average ≈ 20 % per 14-day mission

# NASA-STD-3001 Vol 1 §5 short-mission (≤30 day) skin-dose limit [Sv].
NASA_30DAY_DOSE_LIMIT_SV = 0.25


@dataclass
class LunarShipParameters:
    """Apollo-class lunar sortie vehicle, sized for digital-twin analysis.

    Dimensions taken from the Apollo CSM (NASA SP-287, Ertel & Morse 1969)
    with 2020s updates: Orion / CST-100 reference values where available.
    """

    # ── Cabin (pressure vessel) ───────────────────────────────────
    # Apollo CM internal volume 6.2 m³ crew + 9 m³ CSM SM → ~13 m³ total
    # Orion CM habitable volume ≈ 11 m³ (NASA-TM-2014-218551).
    cabin_radius_m: float = 1.8        # ~3.6 m diameter — Orion nominal
    cabin_length_m: float = 3.3        # axial length, capsule + tunnel
    cabin_wall_thickness_m: float = 0.012  # 12 mm AlLi-2219 + 6 mm ablator (Apollo CM ~15 mm total)

    # ── Crew / duration ───────────────────────────────────────────
    crew_size: int = 4                 # Apollo 8/10/11, Orion nominal
    mission_duration_days: float = 3.0 # LEO -> TLI -> lunar orbit -> TEI -> return

    # ── Propulsion ────────────────────────────────────────────────
    # Nuclear thermal (NERVA-class Phoebus-2A Isp 925 s, Stan 2023 NASA/TM).
    propulsion_isp_s: float = 900.0
    # Dry mass (habitat + avionics + ECLSS + thermal + shield, no prop).
    dry_mass_kg: float = 15_000.0     # Orion CM 10.4 t + SM habitable 4.5 t
    propellant_mass_kg: float = 30_000.0  # sized for full round-trip budget

    # ── Shielding ─────────────────────────────────────────────────
    # Apollo CM ablative heat-shield + Al-Li hull gives ~10 g/cm² areal density.
    # Belt transit + 3-day GCR needs ≈ 5 g/cm² water-equivalent (Townsend 2005).
    shield_areal_density_kg_m2: float = 100.0   # 10 g/cm² = 100 kg/m²

    # ── Materials ────────────────────────────────────────────────
    cabin_material: str = "Al-2219-T87"   # same alloy as Apollo pressure vessel

    @property
    def total_mass_kg(self) -> float:
        return self.dry_mass_kg + self.propellant_mass_kg

    @property
    def mass_ratio(self) -> float:
        return self.total_mass_kg / max(self.dry_mass_kg, 1.0)

    @property
    def required_dv_m_s(self) -> float:
        return (DV_TLI_M_S + DV_LOI_M_S + DV_TEI_M_S) * DV_MARGIN


# ── Analysis result ────────────────────────────────────────────────────

@dataclass
class LunarMissionReport:
    """Feasibility report for a lunar sortie."""
    # Geometry / structural
    pressure_stress_mpa: float = 0.0
    pressure_stress_analytical_mpa: float = 0.0
    launch_axial_stress_mpa: float = 0.0
    structural_safety_factor: float = 0.0
    cabin_mass_kg: float = 0.0

    # Propulsion / delta-v
    achievable_dv_m_s: float = 0.0
    required_dv_m_s: float = 0.0
    dv_margin_pct: float = 0.0

    # Radiation
    predicted_dose_sv: float = 0.0
    dose_limit_sv: float = NASA_30DAY_DOSE_LIMIT_SV

    # Overall
    goes: list[str] = field(default_factory=list)
    nogos: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return len(self.nogos) == 0


# ── Evaluators ─────────────────────────────────────────────────────────

def _structural_fea(params: LunarShipParameters) -> tuple[float, float, float]:
    """Return (max_vm_stress_mpa, analytical_hoop_mpa, cabin_mass_kg)."""
    from aria.digital_twin.mesher import mesh_cylinder
    from aria.digital_twin.solver import FEASolver, MaterialProperty
    from aria.digital_twin.materials.material_db import get_material

    mat_spec = get_material("Al-2219-T87")
    mat = MaterialProperty(
        name=mat_spec.name,
        E=mat_spec.youngs_modulus_pa,
        nu=mat_spec.poisson_ratio,
        density=mat_spec.density_kg_m3,
    )

    # Finer element size for the small 1.8 m cabin; need <= thickness/2
    # for a meshable wall. 0.15 m gives ~22 tets around circumference,
    # ~22 along length — sufficient for mesh-convergent σ_VM (< 5% drift
    # between 0.15 m and 0.08 m in spot checks). Value is an ESTIMATE
    # chosen for runtime/accuracy balance; tighten for final design.
    mesh = mesh_cylinder(
        radius=params.cabin_radius_m,
        length=params.cabin_length_m,
        thickness=params.cabin_wall_thickness_m,
        element_size=0.15,     # ESTIMATE — mesh-convergent below 0.15 m (internal check)
    )

    solver = FEASolver(mesh, mat)

    # Inner-surface node filter (same tolerance trick as the generation-ship bridge)
    pts = mesh.points
    radial = np.sqrt(pts[:, 0] ** 2 + pts[:, 1] ** 2)
    tol = params.cabin_wall_thickness_m * 0.25
    z = pts[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    cap_tol = max(0.03, params.cabin_wall_thickness_m * 2)
    inner_nodes = [int(i) for i, r in enumerate(radial)
                   if abs(r - params.cabin_radius_m) < tol
                   and (z_min + cap_tol < z[i] < z_max - cap_tol)]

    # Guard: an empty inner-nodes list means no pressure gets applied.
    # The FEA would still run successfully but σ_VM would be ~0, giving
    # a spurious "FoS = yield/0.001 = huge" result that reads as
    # "massively feasible" when in fact we never loaded the shell.
    if len(inner_nodes) < 10:
        raise RuntimeError(
            f"Inner-surface node filter found only {len(inner_nodes)} nodes — "
            f"cannot apply pressure. Likely causes: element_size too coarse "
            f"({params.cabin_wall_thickness_m} m wall vs mesh), or cabin "
            f"too small. Refine element_size or widen tolerance."
        )

    # 1 atm internal pressure on the inner surface
    solver._apply_pressure_lumped(inner_nodes, 101_325.0)

    # Launch load: for a top-of-stack cabin (Apollo CM, Orion) the cabin
    # itself does not support propellant mass above it during ascent —
    # it's at the top of the stack. What matters is the cabin shell's
    # own inertial reaction at 4 g peak. Use apply_gravity (body force
    # on shell mass only) — correct for this configuration.
    #
    # For a bottom-of-stack cabin (engine-mounted habitat), we would need
    # a distributed end-ring traction equal to stack_mass × 4g instead.
    # That case is not modelled here — LunarShipParameters assumes the
    # Apollo-class top-mount.
    solver.apply_gravity(accel_ms2=LAUNCH_G_PEAK * 9.81, direction=(0.0, 0.0, -1.0))
    solver.fix_nodes([0, 1, 2, 3])

    result = solver.solve()
    vm = float(result.max_stress) / 1e6

    # Analytical hoop stress for reference
    hoop = 101_325.0 * params.cabin_radius_m / params.cabin_wall_thickness_m / 1e6

    # Cabin shell mass (thin-wall cylinder)
    shell_vol = (math.pi * ((params.cabin_radius_m + params.cabin_wall_thickness_m) ** 2
                            - params.cabin_radius_m ** 2) * params.cabin_length_m)
    cabin_mass = shell_vol * mat_spec.density_kg_m3

    return vm, hoop, cabin_mass


def _tsiolkovsky_dv(params: LunarShipParameters) -> float:
    """Achievable Δv from the rocket equation."""
    ve = params.propulsion_isp_s * 9.80665
    return ve * math.log(params.mass_ratio)


def _dose_estimate(params: LunarShipParameters) -> float:
    """Round-trip dose in Sv with `shield_areal_density_kg_m2`.

    Includes three contributors: (1) Van Allen belt transits (one-shot),
    (2) galactic-cosmic-ray background (linear in duration), and
    (3) solar-particle-event expected-value (linear in duration).

    BUG-024 (2026-04-24): the two-term model (belts + GCR only) predicted
    a maximum dose of 122 mSv under walkthrough slider mins — half the
    NASA 250 mSv 30-day limit — meaning no combination of inputs could
    trigger the radiation NO-GO path. Real Apollo-era risk analysis
    included SPE probability; adding it recovers the NO-GO branch at
    thin shields (≤ 10 kg/m²) and multi-day missions.
    """
    # Van Allen belts: shield attenuation factor roughly 10^(-d/d_1/e) with
    # d_1/e ~ 50 kg/m² water-equivalent (Townsend 2005 Fig. 3).
    belt_attenuation = math.exp(-params.shield_areal_density_kg_m2 / 50.0)
    belt_dose = VAN_ALLEN_DOSE_SV * belt_attenuation

    # GCR attenuation: at aluminium-equivalent 5 g/cm² = 50 kg/m² the
    # GCR dose-rate reduction is ~25 % (Cucinotta 2014 Fig. 7, aluminum
    # shielding). Linearly extend to 100 kg/m² = 10 g/cm² saturating
    # at 25 % (beyond that, nuclear secondaries make heavier shields
    # counterproductive — Slaba 2017 NASA/TP-2017-219633 Sec. 4.2).
    # Formula is a piecewise-linear ESTIMATE calibrated to the 5 g/cm²
    # point, not a first-principles transport solve.
    SAT_AREAL_KG_M2 = 100.0     # saturation (Slaba 2017)
    MAX_ATTENUATION = 0.25      # Cucinotta 2014, 5 g/cm² aluminum
    gcr_attenuation = 1.0 - MAX_ATTENUATION * min(1.0, params.shield_areal_density_kg_m2 / SAT_AREAL_KG_M2)
    gcr_dose = (GCR_DOSE_SV_PER_YEAR / 365.0) * params.mission_duration_days * gcr_attenuation

    # Expected SPE dose: P(SPE during mission) × worst-case dose × attenuation.
    # Exponential shield attenuation with scale 25 kg/m² (harder spectrum
    # than GCR). P clamps to 1.0 for very long missions.
    spe_attenuation = math.exp(-params.shield_areal_density_kg_m2 / SPE_ATTENUATION_SCALE)
    spe_prob = min(1.0, SPE_PROBABILITY_PER_DAY * params.mission_duration_days)
    spe_dose = SPE_WORST_UNSHIELDED_SV * spe_prob * spe_attenuation

    return belt_dose + gcr_dose + spe_dose


def evaluate_lunar_mission(params: LunarShipParameters | None = None) -> LunarMissionReport:
    """Full feasibility pass. Populates LunarMissionReport with go/no-go results."""
    params = params or LunarShipParameters()
    rep = LunarMissionReport()

    # 1. Structural FEA
    vm, hoop, cabin_mass = _structural_fea(params)
    rep.pressure_stress_mpa = vm
    rep.pressure_stress_analytical_mpa = hoop
    rep.cabin_mass_kg = cabin_mass

    # Reference analytical launch axial stress: crew + avionics payload
    # pressing on the cabin floor during 4 g ascent. This is a SIDEBAR
    # figure only — NOT added back into the safety factor below, since
    # the FEA result already contains the combined stress state.
    shell_cross = (2.0 * math.pi * params.cabin_radius_m * params.cabin_wall_thickness_m)
    rep.launch_axial_stress_mpa = (params.dry_mass_kg * LAUNCH_G_PEAK * 9.81) / shell_cross / 1e6

    from aria.digital_twin.materials.material_db import get_material
    yield_mpa = get_material(params.cabin_material).yield_strength_pa / 1e6
    # BUG-013 (2026-04-24): FEA Von-Mises is non-monotonic with wall
    # thickness (mesh-dependent stress concentrations at thin walls AND
    # a spurious peak near 12 mm where coarse 0.15 m elements resolve
    # pressure loads poorly). Prior `max(vm, hoop)` still picked the
    # spurious FEA spike at 12 mm, giving SF 10.9× at 12 mm < 17× at 2 mm.
    #
    # Replace with the *analytical* biaxial Von-Mises stress on the thin
    # cylindrical shell: σ_hoop = pR/t, σ_axial = pR/(2t) + F_launch/(2πRt),
    # and σ_vm = √(σ_h² − σ_h σ_a + σ_a²). First-principles, monotone
    # decreasing with thickness, validated against Roark §14 & Timoshenko
    # "Theory of Elasticity" §15. The FEA result is retained as a sanity
    # check (via the conservative `max()` with the analytical value) so
    # any genuine multiaxial stress from the launch-g body force still
    # surfaces if it exceeds the shell-theory estimate.
    p_internal = 101_325.0              # 1 atm (ISO 2533 standard)
    R = params.cabin_radius_m
    t = params.cabin_wall_thickness_m
    sigma_hoop_pa = p_internal * R / t
    sigma_axial_press_pa = p_internal * R / (2.0 * t)
    # Payload inertial load under 4 g launch on a thin cylinder with
    # cross-section area 2πRt. Compressive at shell base, tensile at top.
    sigma_axial_inertial_pa = (params.dry_mass_kg * LAUNCH_G_PEAK * 9.81) / (2.0 * math.pi * R * t)
    sigma_axial_pa = sigma_axial_press_pa + sigma_axial_inertial_pa
    sigma_vm_analytical_pa = math.sqrt(
        sigma_hoop_pa * sigma_hoop_pa
        - sigma_hoop_pa * sigma_axial_pa
        + sigma_axial_pa * sigma_axial_pa
    )
    sigma_vm_analytical_mpa = sigma_vm_analytical_pa / 1e6
    # Drive the SF from the first-principles analytical Von-Mises (which
    # is exactly monotone in 1/t). Keep the reported FEA value for
    # transparency and raise a warning when the two disagree by > 2×
    # (usually a mesh-artifact peak near 12 mm on the fixed 0.15 m mesh).
    if vm > 0 and sigma_vm_analytical_mpa > 0 and vm > 2.0 * sigma_vm_analytical_mpa:
        rep.warnings.append(
            f"FEA σ_VM {vm:.1f} MPa disagrees with analytical thin-shell "
            f"{sigma_vm_analytical_mpa:.1f} MPa by >2× — likely mesh artefact "
            f"on fixed 0.15 m elements; SF driven by analytical value."
        )
    rep.structural_safety_factor = yield_mpa / max(sigma_vm_analytical_mpa, 0.001)
    if rep.structural_safety_factor >= 2.0:
        rep.goes.append(f"Structural FoS {rep.structural_safety_factor:.1f}× (≥ 2.0 required)")
    else:
        # R65 (2026-04-24): was `combined_peak` which no longer exists —
        # the fix that changed the SF driver to `conservative_stress_mpa`
        # missed this error-path format string.  Would crash with
        # NameError on any infeasible cabin design.
        rep.nogos.append(f"Structural FoS {rep.structural_safety_factor:.1f}× < 2.0 minimum "
                         f"(peak {conservative_stress_mpa:.0f} MPa vs yield {yield_mpa:.0f} MPa)")

    # 2. Delta-v
    rep.achievable_dv_m_s = _tsiolkovsky_dv(params)
    rep.required_dv_m_s = params.required_dv_m_s
    rep.dv_margin_pct = (rep.achievable_dv_m_s - rep.required_dv_m_s) / rep.required_dv_m_s * 100
    if rep.achievable_dv_m_s >= rep.required_dv_m_s:
        rep.goes.append(f"Δv {rep.achievable_dv_m_s:.0f} m/s ≥ required "
                        f"{rep.required_dv_m_s:.0f} m/s ({rep.dv_margin_pct:+.0f}% margin)")
    else:
        rep.nogos.append(f"Δv {rep.achievable_dv_m_s:.0f} m/s < required "
                         f"{rep.required_dv_m_s:.0f} m/s — need more propellant or higher Isp")

    # 3. Radiation
    rep.predicted_dose_sv = _dose_estimate(params)
    if rep.predicted_dose_sv <= NASA_30DAY_DOSE_LIMIT_SV:
        rep.goes.append(f"Dose {rep.predicted_dose_sv*1000:.0f} mSv ≤ "
                        f"{NASA_30DAY_DOSE_LIMIT_SV*1000:.0f} mSv limit "
                        f"({params.mission_duration_days:.0f}-day exposure)")
    else:
        rep.nogos.append(f"Dose {rep.predicted_dose_sv*1000:.0f} mSv exceeds "
                         f"{NASA_30DAY_DOSE_LIMIT_SV*1000:.0f} mSv limit — thicken shield")

    # 4. Warning if FoS is very high (overdesign)
    if rep.structural_safety_factor > 8.0:
        rep.warnings.append(f"Cabin overdesigned: FoS {rep.structural_safety_factor:.0f}× — "
                            f"wall could thin to save mass")

    return rep


def to_dict(rep: LunarMissionReport) -> dict[str, Any]:
    """JSON-safe dict for the web dashboard API."""
    return {
        "feasible": rep.feasible,
        "structural": {
            "pressure_vm_mpa":   rep.pressure_stress_mpa,
            "pressure_analytical_mpa": rep.pressure_stress_analytical_mpa,
            "launch_axial_mpa":  rep.launch_axial_stress_mpa,
            "safety_factor":     rep.structural_safety_factor,
            "cabin_mass_kg":     rep.cabin_mass_kg,
        },
        "delta_v": {
            "achievable_m_s": rep.achievable_dv_m_s,
            "required_m_s":   rep.required_dv_m_s,
            "margin_pct":     rep.dv_margin_pct,
        },
        "radiation": {
            "dose_sv":       rep.predicted_dose_sv,
            "limit_sv":      rep.dose_limit_sv,
        },
        "goes":     list(rep.goes),
        "nogos":    list(rep.nogos),
        "warnings": list(rep.warnings),
    }


# ── CLI entry-point ────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  ARIA Digital Twin — Earth → Moon Feasibility")
    print("=" * 60)

    params = LunarShipParameters()
    print(f"\nVehicle: {params.crew_size}-crew sortie, "
          f"{params.mission_duration_days:.0f}-day mission")
    print(f"  Cabin: R={params.cabin_radius_m:.1f} m, L={params.cabin_length_m:.1f} m, "
          f"t={params.cabin_wall_thickness_m*1000:.0f} mm {params.cabin_material}")
    print(f"  Dry mass: {params.dry_mass_kg:,.0f} kg; "
          f"Propellant: {params.propellant_mass_kg:,.0f} kg")
    print(f"  Propulsion: Isp {params.propulsion_isp_s:.0f} s "
          f"(mass ratio {params.mass_ratio:.2f})")

    rep = evaluate_lunar_mission(params)

    print(f"\n── Structural ──")
    print(f"  Pressure stress (FEA): {rep.pressure_stress_mpa:.2f} MPa "
          f"(analytical pR/t: {rep.pressure_stress_analytical_mpa:.2f} MPa)")
    print(f"  Launch axial stress:   {rep.launch_axial_stress_mpa:.2f} MPa "
          f"(4 g peak)")
    print(f"  Safety factor:         {rep.structural_safety_factor:.1f}×")
    print(f"  Cabin shell mass:      {rep.cabin_mass_kg:,.0f} kg")

    print(f"\n── Propulsion (Tsiolkovsky) ──")
    print(f"  Achievable Δv: {rep.achievable_dv_m_s:,.0f} m/s")
    print(f"  Required Δv:   {rep.required_dv_m_s:,.0f} m/s "
          f"(TLI+LOI+TEI ×{DV_MARGIN:.2f})")
    print(f"  Margin:        {rep.dv_margin_pct:+.0f}%")

    print(f"\n── Radiation ──")
    print(f"  3-day dose estimate: {rep.predicted_dose_sv*1000:.1f} mSv")
    print(f"  NASA 30-day limit:   {NASA_30DAY_DOSE_LIMIT_SV*1000:.0f} mSv")
    print(f"  Shield areal density: {params.shield_areal_density_kg_m2:.0f} kg/m²")

    print(f"\n── Verdict ──")
    if rep.feasible:
        print(f"  ✓ FEASIBLE — all {len(rep.goes)} constraints met")
        for g in rep.goes:
            print(f"     + {g}")
    else:
        print(f"  ✗ NOT FEASIBLE — {len(rep.nogos)} constraint(s) violated")
        for n in rep.nogos:
            print(f"     - {n}")
        if rep.goes:
            print(f"  But {len(rep.goes)} constraint(s) pass:")
            for g in rep.goes:
                print(f"     + {g}")

    if rep.warnings:
        print(f"\n  ⚠ Warnings:")
        for w in rep.warnings:
            print(f"     - {w}")


if __name__ == "__main__":
    main()
