"""Parametric fusion reactor module geometry for the ARIA generation ship.

Creates nested cylindrical shells representing the reactor vessel,
breeding blanket, neutron shield, and biological shield.
"""

from __future__ import annotations

import cadquery as cq

from aria.digital_twin.parameters import ShipParameters


def create_reactor_module(params: ShipParameters) -> cq.Workplane:
    """Build the reactor module as four nested cylindrical shells.

    From innermost to outermost:
      1. Fusion reactor vessel — R=reactor_radius_m, L=reactor_length_m
      2. Breeding blanket (Li2TiO3) — 0.5 m thick shell
      3. Neutron shield (B4C) — 0.3 m thick shell
      4. Biological shield (concrete/water) — 1.0 m thick shell

    Each shell is capped at both ends.

    Parameters
    ----------
    params : ShipParameters
        Ship dimensions dataclass.

    Returns
    -------
    cq.Workplane
        The combined reactor module solid.
    """
    r_reactor = params.reactor_radius_m
    length = params.reactor_length_m

    # Shell radii (cumulative)
    blanket_thickness = 0.5
    neutron_shield_thickness = 0.3
    bioshield_thickness = 1.0

    r_blanket = r_reactor + blanket_thickness
    r_neutron = r_blanket + neutron_shield_thickness
    r_bioshield = r_neutron + bioshield_thickness

    # Build from outside in: outer solid minus inner void for each layer,
    # then union all layers together.

    def _capped_cylinder(radius: float, half_length: float) -> cq.Workplane:
        """Cylinder centered on the origin, extending +/-half_length in Z."""
        return (
            cq.Workplane("XY")
            .transformed(offset=cq.Vector(0, 0, -half_length))
            .circle(radius)
            .extrude(2.0 * half_length)
        )

    hl = length / 2.0

    # Layer 1: reactor vessel (solid cylinder — simplified, no internal void)
    reactor_outer = _capped_cylinder(r_reactor, hl)
    reactor_inner = _capped_cylinder(r_reactor - 0.1, hl)  # 100mm wall
    reactor_vessel = reactor_outer.cut(reactor_inner)

    # Layer 2: breeding blanket shell
    blanket_outer = _capped_cylinder(r_blanket, hl)
    blanket_inner = _capped_cylinder(r_reactor, hl)
    blanket_shell = blanket_outer.cut(blanket_inner)

    # Layer 3: neutron shield shell
    neutron_outer = _capped_cylinder(r_neutron, hl)
    neutron_inner = _capped_cylinder(r_blanket, hl)
    neutron_shell = neutron_outer.cut(neutron_inner)

    # Layer 4: biological shield shell
    bio_outer = _capped_cylinder(r_bioshield, hl)
    bio_inner = _capped_cylinder(r_neutron, hl)
    bio_shell = bio_outer.cut(bio_inner)

    # Combine all layers
    module = reactor_vessel.union(blanket_shell).union(neutron_shell).union(bio_shell)

    return module
