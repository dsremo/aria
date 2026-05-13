"""ARIA CLI — Shield analysis commands.

Usage:
    aria shield analyze --velocity 0.1 --distance 100
    aria shield budget
    aria shield erosion --velocity 0.1 --material carbon
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from aria.cli.formatting import (
    Color,
    bold,
    colored,
    dim,
    error,
    get_context,
    info,
    print_header,
    print_json,
    print_kv,
    print_subheader,
    print_table,
    success,
    warning,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'shield' service and its subcommands."""
    shield_parser = subparsers.add_parser(
        "shield",
        help="Multi-layer shield system analysis",
        description="Analyze relativistic shield performance, mass budgets, and erosion rates.",
    )
    shield_subs = shield_parser.add_subparsers(dest="shield_command")

    # --- shield analyze ---
    an_p = shield_subs.add_parser("analyze", help="Analyze shield performance at given velocity/distance")
    an_p.add_argument("--velocity", "-v", type=float, default=0.1,
                       help="Cruise velocity as fraction of c (default: 0.1)")
    an_p.add_argument("--distance", "-d", type=float, default=100,
                       help="Journey distance in light-years (default: 100)")
    an_p.add_argument("--shield-mass", type=float, default=10000,
                       help="Initial ablation shield mass in kg (default: 10000)")

    # --- shield budget ---
    shield_subs.add_parser("budget", help="Show mass and power budget for all shield layers")

    # --- shield erosion ---
    er_p = shield_subs.add_parser("erosion", help="Calculate erosion rates")
    er_p.add_argument("--velocity", "-v", type=float, default=0.1,
                       help="Cruise velocity as fraction of c")
    er_p.add_argument("--material", "-m", default="carbon",
                       choices=["carbon", "beryllium", "tungsten", "ice", "aluminum"],
                       help="Shield material")
    er_p.add_argument("--area", type=float, default=100.0,
                       help="Forward-facing area in m^2 (default: 100)")
    er_p.add_argument("--years", type=int, default=1000,
                       help="Journey duration in years (default: 1000)")

    # --- shield help ---
    shield_subs.add_parser("help", help="Show shield help")


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch shield subcommands."""
    cmd = getattr(args, "shield_command", None)
    if cmd == "analyze":
        _cmd_analyze(args)
    elif cmd == "budget":
        _cmd_budget(args)
    elif cmd == "erosion":
        _cmd_erosion(args)
    elif cmd == "help" or cmd is None:
        _cmd_help()
    else:
        print(error(f"Unknown shield command: {cmd}"))
        sys.exit(1)


# ────────────────────────────────────────────────────────────────
#  Physical constants (mirrored from shield_system.py)
# ────────────────────────────────────────────────────────────────

C_M_S = 2.998e8
PROTON_MASS_KG = 1.673e-27
ISM_DENSITY_M3 = 1e6  # atoms/m^3 (warm neutral medium)


# ────────────────────────────────────────────────────────────────
#  shield analyze
# ────────────────────────────────────────────────────────────────

def _cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze shield performance for a given mission profile."""
    ctx = get_context()
    velocity_c = getattr(args, "velocity", 0.1)
    distance_ly = getattr(args, "distance", 100.0)
    shield_mass_kg = getattr(args, "shield_mass", 36800.0)  # Default 36.8 tonnes

    velocity_ms = velocity_c * C_M_S
    journey_years = distance_ly / velocity_c
    journey_seconds = journey_years * 365.25 * 24 * 3600

    # Kinetic energy of ISM particles
    proton_ke_j = 0.5 * PROTON_MASS_KG * velocity_ms ** 2
    proton_ke_kev = proton_ke_j / 1.602e-16

    # Particle flux
    flux_per_m2_s = ISM_DENSITY_M3 * velocity_ms

    # Dust grain impact energy (typical 0.1um grain, ~1e-15 kg)
    dust_ke_j = 0.5 * 1e-15 * velocity_ms ** 2
    dust_ke_tnt_kg = dust_ke_j / 4.184e6

    # Sputtering erosion estimate (Hoang et al. scaling)
    # ~40 ug/ly/cm^2 at 0.3c, scales as v^3
    erosion_rate_ug_ly_cm2 = 40.0 * (velocity_c / 0.3) ** 3
    total_erosion_ug_cm2 = erosion_rate_ug_ly_cm2 * distance_ly
    total_erosion_kg_m2 = total_erosion_ug_cm2 * 1e-6 * 1e-3 * 1e4  # ug/cm2 -> kg/m2

    data: dict[str, Any] = {
        "velocity_c": velocity_c,
        "velocity_km_s": round(velocity_ms / 1000, 1),
        "distance_ly": distance_ly,
        "journey_years": round(journey_years, 1),
        "proton_ke_kev": round(proton_ke_kev, 2),
        "flux_per_m2_s": f"{flux_per_m2_s:.2e}",
        "dust_grain_ke_j": round(dust_ke_j, 4),
        "dust_grain_tnt_equivalent_kg": round(dust_ke_tnt_kg, 6),
        "sputtering_erosion_ug_ly_cm2": round(erosion_rate_ug_ly_cm2, 4),
        "total_erosion_kg_m2": round(total_erosion_kg_m2, 4),
        "shield_mass_kg": shield_mass_kg,
    }

    if ctx.is_json:
        print_json(data)
        return

    print_header(f"Shield Analysis: {velocity_c}c over {distance_ly} ly")

    print_subheader("Mission Profile")
    print_kv("Cruise velocity", f"{velocity_c}c ({velocity_ms / 1000:,.0f} km/s)")
    print_kv("Distance", f"{distance_ly} light-years")
    print_kv("Journey time", f"{journey_years:,.0f} years")

    print_subheader("ISM Threat Environment")
    print_kv("Proton kinetic energy", f"{proton_ke_kev:.1f} keV")
    print_kv("Particle flux", f"{flux_per_m2_s:.2e} atoms/m2/s")
    print_kv("Dust grain KE", f"{dust_ke_j:.4f} J per grain")
    if dust_ke_tnt_kg > 0.001:
        print_kv("Dust grain TNT equiv", warning(f"{dust_ke_tnt_kg:.3f} kg"))

    print_subheader("Erosion Analysis")
    print_kv("Sputtering rate", f"{erosion_rate_ug_ly_cm2:.4f} ug/ly/cm2")
    print_kv("Total erosion", f"{total_erosion_kg_m2:.4f} kg/m2 over {distance_ly} ly")
    print_kv("Shield mass", f"{shield_mass_kg:,.0f} kg (initial)")

    # Assess survivability
    forward_area_m2 = 100.0  # Assumed
    total_eroded_kg = total_erosion_kg_m2 * forward_area_m2
    remaining_pct = max(0, (shield_mass_kg - total_eroded_kg) / shield_mass_kg * 100)

    if remaining_pct > 50:
        status = success(f"{remaining_pct:.0f}% remaining -- NOMINAL")
    elif remaining_pct > 10:
        status = warning(f"{remaining_pct:.0f}% remaining -- MARGINAL")
    else:
        status = error(f"{remaining_pct:.0f}% remaining -- CRITICAL")

    print_kv("Shield status", status)
    print()


# ────────────────────────────────────────────────────────────────
#  shield budget
# ────────────────────────────────────────────────────────────────

SHIELD_LAYERS = [
    {
        "id": 1,
        "name": "Forward Detection",
        "range": "100,000+ km",
        "mass_kg": 500,
        "power_kw": 50,
        "description": "LIDAR + radar forward scanning",
    },
    {
        "id": 2,
        "name": "Active Deflection",
        "range": "10,000-100,000 km",
        "mass_kg": 2000,
        "power_kw": 80000,
        "description": "8x 10MW point defense lasers",
    },
    {
        "id": 3,
        "name": "Magnetic Deflector",
        "range": "1,000 km",
        "mass_kg": 3000,
        "power_kw": 5000,
        "description": "Superconducting loop (dual-use magsail)",
    },
    {
        "id": 4,
        "name": "Electrostatic Grid",
        "range": "100 m",
        "mass_kg": 200,
        "power_kw": 1000,
        "description": "High-voltage ionization grid",
    },
    {
        "id": 5,
        "name": "Ablation Shield",
        "range": "contact",
        "mass_kg": 10000,
        "power_kw": 0,
        "description": "Water/ice sacrificial layer",
    },
    {
        "id": 6,
        "name": "Whipple Shield",
        "range": "contact",
        "mass_kg": 1500,
        "power_kw": 0,
        "description": "Ceramic + Kevlar + aluminum layers",
    },
    {
        "id": 7,
        "name": "Structural Hull",
        "range": "contact",
        "mass_kg": 5000,
        "power_kw": 10,
        "description": "Ti-Al hull + self-healing composites",
    },
]


def _cmd_budget(args: argparse.Namespace) -> None:
    """Show mass and power budget for all shield layers."""
    ctx = get_context()

    total_mass = sum(layer["mass_kg"] for layer in SHIELD_LAYERS)
    total_power = sum(layer["power_kw"] for layer in SHIELD_LAYERS)

    if ctx.is_json:
        print_json({
            "layers": SHIELD_LAYERS,
            "total_mass_kg": total_mass,
            "total_power_kw": total_power,
        })
        return

    print_header("Multi-Layer Shield Budget")

    rows = []
    for layer in SHIELD_LAYERS:
        rows.append([
            f"L{layer['id']}",
            bold(layer["name"]),
            layer["range"],
            f"{layer['mass_kg']:,} kg",
            f"{layer['power_kw']:,} kW" if layer["power_kw"] > 0 else dim("passive"),
        ])
    rows.append([
        "",
        bold("TOTAL"),
        "",
        bold(f"{total_mass:,} kg"),
        bold(f"{total_power:,} kW"),
    ])

    print_table(
        ["#", "Layer", "Range", "Mass", "Power"],
        rows,
        col_widths=[5, 22, 20, 14, 14],
    )

    print_subheader("Layer Details")
    for layer in SHIELD_LAYERS:
        lid = layer["id"]
        lname = layer["name"]
        ldesc = layer["description"]
        print(f"  {bold(f'L{lid}: {lname}')} -- {dim(ldesc)}")
    print()


# ────────────────────────────────────────────────────────────────
#  shield erosion
# ────────────────────────────────────────────────────────────────

MATERIAL_PROPERTIES = {
    "carbon": {"density_kg_m3": 2260, "sputtering_yield": 0.03, "name": "Carbon (graphite)"},
    "beryllium": {"density_kg_m3": 1850, "sputtering_yield": 0.01, "name": "Beryllium"},
    "tungsten": {"density_kg_m3": 19250, "sputtering_yield": 0.005, "name": "Tungsten"},
    "ice": {"density_kg_m3": 917, "sputtering_yield": 0.10, "name": "Water Ice"},
    "aluminum": {"density_kg_m3": 2700, "sputtering_yield": 0.05, "name": "Aluminum"},
}


def _cmd_erosion(args: argparse.Namespace) -> None:
    """Calculate erosion rates for a given material and velocity."""
    ctx = get_context()
    velocity_c = args.velocity
    material_key = args.material
    area_m2 = args.area
    years = args.years

    material = MATERIAL_PROPERTIES[material_key]
    velocity_ms = velocity_c * C_M_S

    # Sputtering erosion model
    # Flux = n_ISM * v
    flux = ISM_DENSITY_M3 * velocity_ms

    # Sputtering yield scales with energy (~v^2)
    # Base yield at 0.1c, scale from there
    base_yield = material["sputtering_yield"]
    scaled_yield = base_yield * (velocity_c / 0.1) ** 2

    # Mass loss rate per m^2 per second
    # Each sputtered atom has mass ~ proton_mass * average_atomic_mass
    # For simplicity, use target material's approximate atomic mass
    atomic_mass_map = {
        "carbon": 12, "beryllium": 9, "tungsten": 184,
        "ice": 18, "aluminum": 27,
    }
    target_atom_mass_kg = atomic_mass_map[material_key] * 1.66e-27

    mass_loss_rate = flux * scaled_yield * target_atom_mass_kg  # kg/m^2/s

    seconds_per_year = 365.25 * 24 * 3600
    mass_loss_per_year = mass_loss_rate * seconds_per_year  # kg/m^2/year
    total_mass_loss = mass_loss_per_year * years * area_m2  # kg total

    # Depth erosion rate
    depth_per_year_m = mass_loss_per_year / material["density_kg_m3"]
    total_depth_m = depth_per_year_m * years

    data: dict[str, Any] = {
        "material": material["name"],
        "velocity_c": velocity_c,
        "area_m2": area_m2,
        "years": years,
        "particle_flux_m2_s": f"{flux:.2e}",
        "sputtering_yield": round(scaled_yield, 6),
        "mass_loss_kg_m2_year": round(mass_loss_per_year, 8),
        "total_mass_loss_kg": round(total_mass_loss, 4),
        "depth_erosion_m_year": round(depth_per_year_m, 8),
        "total_depth_erosion_m": round(total_depth_m, 6),
    }

    if ctx.is_json:
        print_json(data)
        return

    print_header(f"Shield Erosion: {material['name']} at {velocity_c}c")

    print_subheader("Parameters")
    print_kv("Material", material["name"])
    print_kv("Density", f"{material['density_kg_m3']:,} kg/m3")
    print_kv("Velocity", f"{velocity_c}c ({velocity_ms / 1000:,.0f} km/s)")
    print_kv("Forward area", f"{area_m2} m2")
    print_kv("Duration", f"{years:,} years")

    print_subheader("Erosion Rates")
    print_kv("Particle flux", f"{flux:.2e} atoms/m2/s")
    print_kv("Sputtering yield", f"{scaled_yield:.6f} atoms/ion")
    print_kv("Mass loss", f"{mass_loss_per_year:.2e} kg/m2/year")
    print_kv("Depth erosion", f"{depth_per_year_m:.2e} m/year")

    print_subheader(f"Cumulative ({years:,} years)")
    print_kv("Total mass loss", f"{total_mass_loss:,.2f} kg")
    print_kv("Total depth", f"{total_depth_m * 100:.4f} cm ({total_depth_m * 1000:.2f} mm)")

    # Assessment
    if total_depth_m < 0.01:
        print_kv("Assessment", success("Minimal erosion -- material is viable"))
    elif total_depth_m < 0.1:
        print_kv("Assessment", warning("Moderate erosion -- replenishment needed"))
    else:
        print_kv("Assessment", error("Severe erosion -- material inadequate at this velocity"))

    print()


# ────────────────────────────────────────────────────────────────
#  shield help
# ────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    """Show shield help."""
    print_header("ARIA Shield Commands")
    print_table(
        headers=["Command", "Description"],
        rows=[
            ["aria shield analyze", "Analyze shield performance at given v and distance"],
            ["aria shield budget", "Mass and power budget for all 7 shield layers"],
            ["aria shield erosion", "Calculate sputtering erosion rates by material"],
        ],
        col_widths=[30, 48],
    )
    print(dim("  Materials: carbon, beryllium, tungsten, ice, aluminum"))
    print()
