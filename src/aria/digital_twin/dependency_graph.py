"""Subsystem dependency graph — which parts need which other parts.

Answers questions like:
  * "If the fusion reactor fails, what goes down?"
  * "What does the habitat ring depend on?"
  * "Show me a failure-propagation tree from shield layer 4."

The graph is a directed DAG: an edge `A → B` means **A depends on B**
(A cannot function without B). "A feeds B" is the reverse direction.

Dependencies are data-only; the physics of how each subsystem degrades
under a lost dependency is left to the individual subsystem models.
This module is the *topology*, not the physics.

References
----------
Dependency taxonomy follows NASA's System-of-Systems analysis framework
(NASA/SP-2016-6105 Rev2 "NASA Systems Engineering Handbook", §4.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class DependencyEdge:
    """An A-depends-on-B edge with human-readable rationale."""

    src: str        # the part that has the dependency
    dst: str        # the part it depends on
    kind: str       # 'power' / 'coolant' / 'structural' / 'data' / 'fuel' / 'ecs'
    critical: bool  # True = src immediately fails if dst fails; False = degraded mode possible
    note: str = ""


# Master dependency list. Each edge: (src, dst, kind, critical, note).
# Kept flat + declarative so it's easy to audit and diff.
_RAW_EDGES: List[Tuple[str, str, str, bool, str]] = [
    # ── Reactor is the root power source ──────────────────────────
    ("power_distribution",  "reactor_engine",   "power", True,  "Primary electrical source"),
    ("magnetic_nozzle",     "reactor_engine",   "fuel",  True,  "Plasma exhaust from fusion chamber"),
    ("magnetic_nozzle",     "power_distribution","power",True,  "Superconducting magnet coil power"),

    # ── Reactor needs fuel + cooling + structural support ─────────
    ("reactor_engine",      "fuel_tank_0",      "fuel",  True,  "He-3 feed"),
    ("reactor_engine",      "fuel_tank_1",      "fuel",  True,  "D feed"),
    ("reactor_engine",      "fuel_tank_2",      "fuel",  False, "Tritium breeding blanket topup (non-critical if TBR>1)"),
    ("reactor_engine",      "thermal_loop",     "coolant",True, "Li-Pb breeding blanket removes fusion heat"),
    ("reactor_engine",      "hull_main",        "structural",True,"Reactor pressure vessel anchored to hull frame"),

    # ── Thermal loop → radiators (heat rejection) ─────────────────
    ("thermal_loop",        "radiator_array_0", "coolant",False,"Wing +Y (loss halves capacity, degraded mode OK short-term)"),
    ("thermal_loop",        "radiator_array_1", "coolant",False,"Wing −Y (loss halves capacity)"),
    ("thermal_loop",        "power_distribution","power", True, "Pump power"),

    # ── Habitat ring rotation + life support ──────────────────────
    ("habitat_ring",        "spoke_0",          "structural",True,"6 spokes = 6 independent load paths, ANY 2 can fail"),
    ("habitat_ring",        "spoke_3",          "structural",True,"Opposite spoke; paired redundancy"),
    ("habitat_ring",        "hull_main",        "structural",True,"Spokes anchor at hull centreline"),
    ("habitat_ring",        "power_distribution","power", True, "Lighting, ECLSS, gravity-ring bearing"),
    ("habitat_ring",        "thermal_loop",     "coolant",True, "Crew metabolic heat rejection"),

    # ── Habitat modules → ring → hull → reactor ───────────────────
    *[(f"hab_module_{i}",   "habitat_ring",     "structural",True,"Module perched on ring rim")
      for i in range(24)],
    *[(f"hab_module_{i}",   "eclss",            "ecs",   True, "Atmosphere + water + food loop")
      for i in range(24)],

    # ── ECLSS depends on power, thermal, hydroponics ──────────────
    ("eclss",               "power_distribution","power", True, "Pumps, scrubbers, LED grow lights"),
    ("eclss",               "thermal_loop",     "coolant",False,"Latent heat removal via condenser (degraded w/o thermal)"),
    ("eclss",               "fuel_tank_2",      "fuel",  False, "Nitrogen makeup from pressurant"),
    ("agriculture",         "eclss",            "ecs",   True,  "CO₂ supply + nutrient water"),
    ("agriculture",         "power_distribution","power", True, "LED photosynthesis lighting"),

    # ── Shield stack (7 layers, outer→inner) ─────────────────────
    ("shield_layer_0",      "power_distribution","power", True, "LIDAR detection array"),
    ("shield_layer_1",      "power_distribution","power", True, "Active plasma deflector needs MW-class power"),
    ("shield_layer_2",      "power_distribution","power", True, "Superconducting magnet coils"),
    ("shield_layer_2",      "thermal_loop",     "coolant",True, "Magnet cryocooling to <4 K"),
    ("shield_layer_3",      "power_distribution","power", False,"Electrostatic grid trickle current"),
    ("shield_layer_5",      "shield_layer_4",   "structural",True,"Whipple bumper stands off from ablation ice"),
    ("shield_layer_6",      "hull_main",        "structural",True,"Inner structural layer bolted to hull"),
    ("hull_main",           "shield_layer_0",   "ecs",   False, "Outermost shield protects hull from GCR — hull degrades faster without it"),

    # ── Propulsion ───────────────────────────────────────────────
    ("engine_bell_0",       "power_distribution","power", True, "NE attitude thruster arc-jet power"),
    ("engine_bell_1",       "power_distribution","power", True, "NW attitude thruster"),
    ("engine_bell_2",       "power_distribution","power", True, "SW attitude thruster"),
    ("engine_bell_3",       "power_distribution","power", True, "SE attitude thruster"),
    ("engine_bell_0",       "fuel_tank_2",      "fuel",  True, "RCS propellant tap (Xenon)"),

    # ── Hull structure ───────────────────────────────────────────
    *[(f"hull_stiffener_{i}","hull_main",       "structural",True,"Ring-frame stiffener welded to hull shell")
      for i in range(5)],

    # ── Comms + sensors ───────────────────────────────────────────
    ("bow_sensor_ring",     "power_distribution","power", True, "Star trackers + LIDAR"),
    ("bow_sensor_ring",     "hull_main",        "structural",True,"Mounted to bow cap"),
    ("bow_sensor_ring",     "avionics",         "data",  True, "Sensor data telemetry"),
    *[(f"comm_antenna_{i}", "power_distribution","power", True, "Ka-band RF amplifier")
      for i in range(4)],
    *[(f"comm_antenna_{i}", "avionics",         "data",  True, "Modem baseband")
      for i in range(4)],

    # ── Avionics ──────────────────────────────────────────────────
    ("avionics",            "power_distribution","power", True, "Computing cluster"),
    ("avionics",            "thermal_loop",     "coolant",False,"CPU cooling (throttles without active cooling)"),

    # ── Docking ports ─────────────────────────────────────────────
    *[(f"docking_port_{i}", "hull_main",        "structural",True,"Cut into hull pressure shell")
      for i in range(4)],
    *[(f"docking_port_{i}", "eclss",            "ecs",   True, "Airlock pressurisation")
      for i in range(4)],
]


# ── Builder API ──────────────────────────────────────────────────────

class DependencyGraph:
    """Directed dependency graph of ship subsystems.

    Nodes are part identifiers (strings — match the mesh names in
    :func:`aria.digital_twin.export_gltf.build_ship_gltf`). Edges carry
    a `kind` and `critical` flag.
    """

    def __init__(self, edges: Iterable[DependencyEdge] | None = None) -> None:
        if edges is None:
            edges = [
                DependencyEdge(src=s, dst=d, kind=k, critical=c, note=n)
                for s, d, k, c, n in _RAW_EDGES
            ]
        self._edges: List[DependencyEdge] = list(edges)

    # ── basic accessors ───────────────────────────────────────────

    @property
    def edges(self) -> List[DependencyEdge]:
        return list(self._edges)

    def nodes(self) -> Set[str]:
        """Return the set of all part ids present in the graph."""
        out: Set[str] = set()
        for e in self._edges:
            out.add(e.src)
            out.add(e.dst)
        return out

    # ── upstream / downstream traversal ───────────────────────────

    def depends_on(self, part_id: str, *, critical_only: bool = False) -> List[DependencyEdge]:
        """Direct dependencies of `part_id` (what it needs to function)."""
        return [e for e in self._edges
                if e.src == part_id and (not critical_only or e.critical)]

    def feeds(self, part_id: str, *, critical_only: bool = False) -> List[DependencyEdge]:
        """Parts that depend on `part_id` (reverse of depends_on)."""
        return [e for e in self._edges
                if e.dst == part_id and (not critical_only or e.critical)]

    def all_upstream(self, part_id: str, *, critical_only: bool = False) -> Set[str]:
        """Transitive closure of `depends_on` — everything `part_id` needs."""
        visited: Set[str] = set()
        stack = [part_id]
        while stack:
            cur = stack.pop()
            for e in self.depends_on(cur, critical_only=critical_only):
                if e.dst not in visited:
                    visited.add(e.dst)
                    stack.append(e.dst)
        return visited

    def failure_cascade(self, failed_id: str, *, critical_only: bool = True) -> Set[str]:
        """If `failed_id` goes down, what else goes down?

        Walks the *reverse* graph: anything that depends on failed_id
        (critical edge only, by default) fails too, recursively.
        """
        doomed: Set[str] = set()
        stack = [failed_id]
        while stack:
            cur = stack.pop()
            for e in self.feeds(cur, critical_only=critical_only):
                if e.src not in doomed:
                    doomed.add(e.src)
                    stack.append(e.src)
        return doomed

    # ── serialisation ─────────────────────────────────────────────

    def to_dict(self) -> dict:
        """JSON-serialisable dict of nodes + edges (for the web API)."""
        return {
            "nodes": sorted(self.nodes()),
            "edges": [
                {"src": e.src, "dst": e.dst, "kind": e.kind,
                 "critical": e.critical, "note": e.note}
                for e in self._edges
            ],
        }


# Default global instance — caches the declaratively-defined graph
_DEFAULT_GRAPH: Optional[DependencyGraph] = None


def get_dependency_graph() -> DependencyGraph:
    """Module-level singleton so callers don't rebuild it constantly."""
    global _DEFAULT_GRAPH
    if _DEFAULT_GRAPH is None:
        _DEFAULT_GRAPH = DependencyGraph()
    return _DEFAULT_GRAPH
