"""Connect ShipParameters shield geometry to radiation Monte Carlo transport.

Bridges the gap between the parametric digital-twin geometry
(``parameters.ShipParameters``) and the radiation transport simulator
(``simulation.radiation_transport``).  Reads the actual shield layer
thicknesses from the ship model and converts them into the
``ShieldLayer`` format that ``RadiationTransportSimulator`` expects.
"""

from __future__ import annotations

from typing import Dict, List

from aria.digital_twin.parameters import ShieldLayerSpec, ShipParameters
from aria.simulation.radiation_transport import (
    RadiationTransportSimulator,
    ShieldLayer,
    _SyntheticFluxModel,
)


# ════════════════════════════════════════════════════════════════
#  MATERIAL DATABASE
# ════════════════════════════════════════════════════════════════
# Maps ShieldLayerSpec.material names to radiation-transport properties.

_MATERIAL_MAP: Dict[str, Dict] = {
    "sensor_array": {
        "rt_material": "aluminum",
        "density_g_cm3": 2.70,
        "z_target": 13.0,
        "a_target": 27.0,
    },
    "plasma_deflector": {
        "rt_material": "aluminum",
        "density_g_cm3": 2.70,
        "z_target": 13.0,
        "a_target": 27.0,
    },
    "superconducting_coil": {
        "rt_material": "aluminum",
        "density_g_cm3": 2.70,
        "z_target": 13.0,
        "a_target": 27.0,
        "has_magnetic_deflection": True,
        "rigidity_cutoff_gv": 1.5,
    },
    "tungsten_mesh": {
        "rt_material": "aluminum",
        "density_g_cm3": 19.3,
        "z_target": 74.0,
        "a_target": 183.8,
        "has_electrostatic": True,
        "ionization_efficiency": 0.80,
    },
    "water_ice": {
        "rt_material": "water",
        "density_g_cm3": 0.917,
        "z_target": 3.34,
        "a_target": 6.01,
    },
    "SiC_Kevlar_Al7075": {
        "rt_material": "aluminum",
        "density_g_cm3": 2.70,
        "z_target": 13.0,
        "a_target": 27.0,
    },
    "Ti-6Al-4V_HealTech": {
        "rt_material": "titanium",
        "density_g_cm3": 4.43,
        "z_target": 22.0,
        "a_target": 47.9,
    },
}


# ════════════════════════════════════════════════════════════════
#  PUBLIC API
# ════════════════════════════════════════════════════════════════

def create_shield_config_from_geometry(
    params: ShipParameters,
) -> List[Dict]:
    """Convert ``ShipParameters.shield_layers`` into a list of dicts.

    Each dict contains:
      - name:              layer name from ShieldLayerSpec
      - thickness_m:       physical thickness in metres
      - material:          ShieldLayerSpec.material string
      - density_g_cm3:     bulk density
      - areal_density_g_cm2:  thickness_m * density_g_cm3 * 100 (m->cm)

    Returns
    -------
    list[dict]
        One entry per shield layer, ordered bow-to-stern.
    """
    result: List[Dict] = []
    for layer in params.shield_layers:
        mat = _MATERIAL_MAP.get(layer.material)
        if mat is None:
            raise ValueError(
                f"Unknown shield material '{layer.material}' "
                f"in layer '{layer.name}'"
            )
        density = mat["density_g_cm3"]
        areal_density = layer.thickness_m * density * 100.0  # m -> cm
        result.append({
            "name": layer.name,
            "thickness_m": layer.thickness_m,
            "material": layer.material,
            "density_g_cm3": density,
            "areal_density_g_cm2": areal_density,
        })
    return result


def _spec_to_shield_layer(
    layer: ShieldLayerSpec,
    index: int,
) -> ShieldLayer:
    """Convert a single ``ShieldLayerSpec`` to a ``ShieldLayer``."""
    mat = _MATERIAL_MAP.get(layer.material)
    if mat is None:
        raise ValueError(
            f"Unknown shield material '{layer.material}' "
            f"in layer '{layer.name}'"
        )

    density = mat["density_g_cm3"]
    areal_density = layer.thickness_m * density * 100.0  # m -> cm

    return ShieldLayer(
        name=f"L{index + 1}_{layer.name}",
        material=mat["rt_material"],
        thickness_g_cm2=areal_density,
        z_target=mat["z_target"],
        a_target=mat["a_target"],
        density_g_cm3=density,
        has_magnetic_deflection=mat.get("has_magnetic_deflection", False),
        rigidity_cutoff_gv=mat.get("rigidity_cutoff_gv", 0.0),
        has_electrostatic=mat.get("has_electrostatic", False),
        ionization_efficiency=mat.get("ionization_efficiency", 0.0),
    )


def run_radiation_analysis(
    params: ShipParameters,
    velocity_c: float = 0.1,
    n_particles: int = 200,
    seed: int = 42,
) -> Dict:
    """End-to-end radiation analysis using actual ship shield geometry.

    1. Reads shield layer thicknesses from *params*.
    2. Converts them to ``ShieldLayer`` objects for the MC transport.
    3. Instantiates ``RadiationTransportSimulator``.
    4. Runs ``simulate_annual_dose`` with a synthetic flux model.
    5. Returns a summary dict with dose results.

    Parameters
    ----------
    params : ShipParameters
        Ship geometry with shield layer specs.
    velocity_c : float
        Ship velocity as fraction of *c*.
    n_particles : int
        Number of MC particles to simulate.
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    dict
        Keys: total_dose_msv, dose_by_organ, particles_simulated,
        particles_stopped, particles_deflected, mean_quality_factor,
        shield_config (list of layer dicts).
    """
    # Build ShieldLayer list from ship parameters
    shield_layers = [
        _spec_to_shield_layer(layer, idx)
        for idx, layer in enumerate(params.shield_layers)
    ]

    sim = RadiationTransportSimulator(
        shield_layers=shield_layers,
        seed=seed,
        n_particles=n_particles,
    )

    flux_model = _SyntheticFluxModel()
    solar_phase = 0.0  # Solar minimum (worst-case GCR)

    dose_result = sim.simulate_annual_dose(
        flux_model=flux_model,
        velocity_c=velocity_c,
        solar_phase=solar_phase,
        n_particles=n_particles,
    )

    shield_config = create_shield_config_from_geometry(params)

    return {
        "total_dose_msv": dose_result.total_dose_msv,
        "dose_by_organ": dict(dose_result.dose_by_organ),
        "particles_simulated": dose_result.particles_simulated,
        "particles_stopped": dose_result.particles_stopped,
        "particles_deflected": dose_result.particles_deflected,
        "mean_quality_factor": dose_result.mean_quality_factor,
        "shield_config": shield_config,
    }
