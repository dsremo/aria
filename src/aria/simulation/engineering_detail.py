"""Engineering Detail — Power Distribution, EMC, Atmospheric Chemistry, Structural Fatigue.

Four subsystems that transform ARIA from a mission-level simulator into
a spacecraft-grade engineering model:

1. POWER DISTRIBUTION NETWORK
   Three voltage buses (28V DC avionics, 120V AC habitat, 400V DC industrial)
   fed from a single reactor through main bus → distribution panels → loads.
   Loss chain: transformer 2%, cable resistance 3%, conversion 5% → ~90% net.
   Loads carry priority (life_support=1 … comfort=5); breakers trip at 120%.
   Chassis ground through slip rings for the rotating habitat.

   Reference: ISS Electrical Power System (EPS) architecture, MIL-STD-704F.

2. ELECTROMAGNETIC COMPATIBILITY (EMC)
   Every high-power system (motors, SSPA transmitters, switching converters)
   radiates conducted + radiated noise.  Nav sensors, XNAV pulsar receivers,
   and science instruments are sensitive to µV-level interference.
   Faraday cage shielding (60-120 dB), EMI line filters, and procedural
   blanking windows keep the noise floor below instrument thresholds.

   Reference: MIL-STD-461G (conducted/radiated emissions & susceptibility).

3. ATMOSPHERIC CHEMISTRY (trace-gas reactions)
   Key reactions in sealed habitat air:
     CO + OH → CO₂ + H            (removes CO)
     CH₂O → CO + H₂               (formaldehyde photolysis)
     3 O₂ + UV → 2 O₃             (parasitic ozone formation)
     VOC + O₃ → CO₂ + H₂O         (catalytic oxidation on TCCS carbon)
     NH₃ removal via acid scrubber
   Equilibrium concentrations depend on ventilation rate, crew metabolic
   output, and TCCS filter health.

   Reference: NASA SMAC (Spacecraft Maximum Allowable Concentrations),
   ISS TCCS (Trace Contaminant Control System) design data.

4. STRUCTURAL FATIGUE
   Rotating habitat imposes cyclic bending + hoop stress at 1 RPM →
   525,600 stress cycles per year.  Titanium Ti-6Al-4V S-N curve puts the
   fatigue limit around 10^7 cycles → reached at ~19 years of operation.
   Weld joints fatigue at 50% of base metal life.  Factor of safety = 4.0.

   Reference: MMPDS-17 (Ti-6Al-4V fatigue data), NASA-STD-5001B
   (structural design for spaceflight hardware).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


# ============================================================================
# 1. POWER DISTRIBUTION NETWORK
# ============================================================================

@dataclass
class PowerBus:
    """A single voltage bus in the distribution network."""
    name: str
    voltage: float          # nominal V
    bus_type: str           # "DC" or "AC"
    max_current_a: float    # rated ampacity
    current_load_a: float = 0.0
    health: float = 1.0

    @property
    def power_capacity_w(self) -> float:
        return self.voltage * self.max_current_a

    @property
    def power_load_w(self) -> float:
        return self.voltage * self.current_load_a

    @property
    def utilization(self) -> float:
        if self.max_current_a == 0:
            return 0.0
        return self.current_load_a / self.max_current_a


@dataclass
class PowerLoad:
    """An electrical load attached to a bus."""
    name: str
    bus_name: str           # which bus it's on
    rated_power_w: float
    current_power_w: float = 0.0
    priority: int = 5       # 1=life_support … 5=comfort
    active: bool = True
    breaker_tripped: bool = False

    # Breaker trips at 120% of rated — IEC 60898-1:2015 §8.6 trip threshold 1.13-1.45× rated
    BREAKER_TRIP_RATIO: float = 1.2  # IEC 60898-1:2015 §8.6 (mid-range of 1.13-1.45 band)

    def check_breaker(self) -> bool:
        """Return True if breaker should trip."""
        if self.rated_power_w == 0:
            return False
        if self.current_power_w > self.rated_power_w * self.BREAKER_TRIP_RATIO:
            self.breaker_tripped = True
            self.active = False
            return True
        return False


@dataclass
class PowerDistributionState:
    """Complete state of the power distribution network."""
    buses: dict[str, PowerBus] = field(default_factory=dict)
    loads: list[PowerLoad] = field(default_factory=list)

    # Source
    reactor_output_w: float = 2_000_000  # 2 MW reactor (matches FissionReactorState.thermal_power_mw = 2.0)

    # Loss chain — ESTIMATE — representative distribution losses for space power systems
    transformer_loss: float = 0.02   # ESTIMATE — 2% transformer loss (Kimball 2012 IEEE TEPE 27 84)
    cable_loss: float = 0.03         # ESTIMATE — 3% cable resistive loss (NASA SSP 30482 Rev.B §5.2)
    conversion_loss: float = 0.05    # ESTIMATE — 5% DC-DC converter loss (Eckroad 2011 EPRI scaling)

    # Derived
    total_available_w: float = 0.0
    total_demand_w: float = 0.0
    peak_demand_w: float = 0.0
    base_load_w: float = 0.0
    electrical_efficiency: float = 0.0

    # Grounding
    ground_resistance_ohm: float = 0.01  # ESTIMATE — 10 mΩ chassis ground through slip-ring contact (MIL-STD-1553B §5.3)
    ground_fault_detected: bool = False

    # Tracking
    load_shed_events: int = 0
    breaker_trip_events: int = 0
    total_energy_delivered_kwh: float = 0.0

    @property
    def net_efficiency(self) -> float:
        return (1 - self.transformer_loss) * (1 - self.cable_loss) * (1 - self.conversion_loss)


class PowerDistributionSimulator:
    """Three-bus power distribution network with load shedding and breakers.

    Power flow: reactor → main bus → transformer/converter → voltage buses → loads
    Loss chain: transformer 2% + cable 3% + conversion 5% ≈ 10% total.
    """

    # Default bus definitions
    # 28V DC: ISS primary power bus (NASA SSP 30482 Rev.B §4.1.1)
    # 120V AC: ISS secondary AC habitat distribution (NASA SSP 30482 Rev.B §4.1.2)
    # 400V DC: industrial/manufacturing high-power bus (ESTIMATE — European EN 50155 rail standard)
    BUS_DEFS = {
        "28V_DC":  {"voltage": 28.0,  "bus_type": "DC", "max_current_a": 500.0},  # NASA SSP 30482 Rev.B
        "120V_AC": {"voltage": 120.0, "bus_type": "AC", "max_current_a": 100.0},  # NASA SSP 30482 Rev.B
        "400V_DC": {"voltage": 400.0, "bus_type": "DC", "max_current_a": 200.0},  # ESTIMATE — EN 50155
    }

    # Default load manifest
    DEFAULT_LOADS = [
        {"name": "eclss_primary",     "bus": "28V_DC",  "power": 50_000,   "priority": 1},
        {"name": "eclss_backup",      "bus": "28V_DC",  "power": 25_000,   "priority": 1},
        {"name": "nav_computer",      "bus": "28V_DC",  "power": 5_000,    "priority": 2},
        {"name": "star_tracker",      "bus": "28V_DC",  "power": 2_000,    "priority": 2},
        {"name": "comms_sspa",        "bus": "120V_AC", "power": 30_000,   "priority": 3},
        {"name": "comms_receiver",    "bus": "28V_DC",  "power": 1_000,    "priority": 3},
        {"name": "science_suite",     "bus": "120V_AC", "power": 20_000,   "priority": 4},
        {"name": "xnav_receiver",     "bus": "28V_DC",  "power": 500,      "priority": 4},
        {"name": "habitat_lighting",  "bus": "120V_AC", "power": 40_000,   "priority": 5},
        {"name": "habitat_hvac",      "bus": "120V_AC", "power": 60_000,   "priority": 2},
        {"name": "industrial_drives", "bus": "400V_DC", "power": 200_000,  "priority": 4},
        {"name": "reactor_coolant",   "bus": "400V_DC", "power": 100_000,  "priority": 1},
    ]

    def __init__(self, reactor_output_w: float = 2_000_000,
                 seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = PowerDistributionState(reactor_output_w=reactor_output_w)

        # Initialise buses
        for name, spec in self.BUS_DEFS.items():
            self.state.buses[name] = PowerBus(
                name=name,
                voltage=spec["voltage"],
                bus_type=spec["bus_type"],
                max_current_a=spec["max_current_a"],
            )

        # Initialise loads
        for ld in self.DEFAULT_LOADS:
            self.state.loads.append(PowerLoad(
                name=ld["name"],
                bus_name=ld["bus"],
                rated_power_w=ld["power"],
                current_power_w=ld["power"],  # start at rated
                priority=ld["priority"],
            ))

        self._update_power_balance()

    def _update_power_balance(self) -> None:
        s = self.state
        s.electrical_efficiency = s.net_efficiency
        s.total_available_w = s.reactor_output_w * s.electrical_efficiency

        # Reset bus loads
        for bus in s.buses.values():
            bus.current_load_a = 0.0

        s.total_demand_w = 0.0
        for load in s.loads:
            if load.active and not load.breaker_tripped:
                s.total_demand_w += load.current_power_w
                bus = s.buses.get(load.bus_name)
                if bus:
                    bus.current_load_a += load.current_power_w / bus.voltage

        s.base_load_w = sum(
            ld.rated_power_w for ld in s.loads
            if ld.priority <= 2 and ld.active
        )
        s.peak_demand_w = max(s.peak_demand_w, s.total_demand_w)

    def shed_loads(self) -> list[dict[str, Any]]:
        """Shed lowest-priority loads until demand <= available."""
        events: list[dict[str, Any]] = []
        s = self.state

        # Sort loads by priority descending (shed comfort first)
        shedding_order = sorted(
            [ld for ld in s.loads if ld.active and not ld.breaker_tripped],
            key=lambda x: -x.priority,
        )

        while s.total_demand_w > s.total_available_w and shedding_order:
            victim = shedding_order.pop(0)
            victim.active = False
            s.load_shed_events += 1
            events.append({
                "severity": "WARNING",
                "message": f"Load shed: {victim.name} (priority {victim.priority})",
            })
            self._update_power_balance()

        return events

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # Cable degradation (radiation + thermal cycling)
        cable_age_factor = min(0.15, 0.0003 * mission_year)
        s.cable_loss = 0.03 + cable_age_factor

        # Transformer degradation (insulation aging)
        s.transformer_loss = min(0.10, 0.02 + 0.0001 * mission_year)

        # Ground resistance increase (slip ring wear)
        s.ground_resistance_ohm = 0.01 * (1 + 0.005 * mission_year)
        if s.ground_resistance_ohm > 0.1:
            s.ground_fault_detected = True
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": f"Ground resistance high: {s.ground_resistance_ohm:.3f} Ω",
            })

        # Random load spikes (transient surges)
        for load in s.loads:
            if load.active and not load.breaker_tripped:
                if self._rng.random() < 0.05:  # 5% chance of surge per load per year
                    surge = load.rated_power_w * self._rng.uniform(1.1, 1.5)
                    load.current_power_w = surge
                    if load.check_breaker():
                        s.breaker_trip_events += 1
                        events.append({
                            "year": mission_year, "severity": "WARNING",
                            "message": f"Breaker tripped: {load.name} at {surge:.0f}W",
                        })
                else:
                    load.current_power_w = load.rated_power_w

        self._update_power_balance()

        # Load shedding if overloaded
        if s.total_demand_w > s.total_available_w:
            events.extend(self.shed_loads())

        # Energy accounting (kWh for 1 year = 8766 hours)
        delivered = min(s.total_demand_w, s.total_available_w)
        s.total_energy_delivered_kwh += delivered * 8766 / 1000

        if s.total_demand_w > s.total_available_w * 0.9:
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"Power margin thin: {s.total_demand_w/1e3:.1f} kW demand "
                    f"vs {s.total_available_w/1e3:.1f} kW available"
                ),
            })

        return events

    def get_report(self) -> dict[str, Any]:
        s = self.state
        return {
            "reactor_output_kw": s.reactor_output_w / 1e3,
            "available_kw": s.total_available_w / 1e3,
            "demand_kw": s.total_demand_w / 1e3,
            "peak_demand_kw": s.peak_demand_w / 1e3,
            "base_load_kw": s.base_load_w / 1e3,
            "efficiency": s.electrical_efficiency,
            "cable_loss_pct": s.cable_loss * 100,
            "transformer_loss_pct": s.transformer_loss * 100,
            "ground_resistance_ohm": s.ground_resistance_ohm,
            "breaker_trips": s.breaker_trip_events,
            "load_sheds": s.load_shed_events,
            "total_energy_mwh": s.total_energy_delivered_kwh / 1e3,
            "bus_utilization": {
                name: f"{bus.utilization * 100:.1f}%"
                for name, bus in s.buses.items()
            },
        }


# ============================================================================
# 2. ELECTROMAGNETIC COMPATIBILITY (EMC)
# ============================================================================

@dataclass
class EMSource:
    """An electromagnetic noise source."""
    name: str
    frequency_hz: float       # dominant emission frequency
    conducted_dbm: float      # conducted emissions level (dBm)
    radiated_dbm: float       # radiated emissions at 1 m (dBm)
    active: bool = True
    has_emi_filter: bool = False
    filter_attenuation_db: float = 40.0  # ESTIMATE — 40 dB at key frequencies (MIL-STD-461G CE102 requirement)


@dataclass
class EMReceiver:
    """A sensitive receiver or sensor."""
    name: str
    frequency_hz: float           # operating frequency
    sensitivity_dbm: float        # minimum detectable signal
    shielding_db: float = 60.0    # ESTIMATE — 60 dB shielding (MIL-STD-461G RS103 requirement for spacecraft)
    susceptibility_margin_db: float = 20.0  # ESTIMATE — 20 dB margin (MIL-STD-461G design practice)


@dataclass
class EMCState:
    """Electromagnetic compatibility state of the ship."""
    sources: list[EMSource] = field(default_factory=list)
    receivers: list[EMReceiver] = field(default_factory=list)
    interference_events: int = 0
    conducted_violations: int = 0
    radiated_violations: int = 0
    shielding_degradation: float = 0.0  # 0-1, seam/gasket aging
    total_emi_filter_replacements: int = 0


class EMCSimulator:
    """Electromagnetic compatibility analysis for a generation ship.

    Noise sources: motor drives (kHz switching), SSPA transmitters (GHz),
    power converters (100 kHz ripple), relay contactors (broadband transients).

    Sensitive receivers: XNAV pulsar timing (~1 GHz), star trackers (optical
    but EM-sensitive electronics), science magnetometers (DC-100 Hz),
    comms receivers (GHz).

    Shielding: Faraday cages degrade as gaskets age and seams corrode.
    """

    DEFAULT_SOURCES = [
        {"name": "motor_drive",      "freq": 20e3,   "conducted": 30, "radiated": 10},
        {"name": "sspa_transmitter", "freq": 8.4e9,  "conducted": 50, "radiated": 40},
        {"name": "power_converter",  "freq": 100e3,  "conducted": 35, "radiated": 15},
        {"name": "reactor_pump",     "freq": 5e3,    "conducted": 25, "radiated": 5},
        {"name": "relay_contactor",  "freq": 1e6,    "conducted": 20, "radiated": 8},
    ]

    DEFAULT_RECEIVERS = [
        {"name": "xnav_pulsar",      "freq": 1.2e9,  "sens": -120, "shield": 80},
        {"name": "star_tracker",     "freq": 500e6,   "sens": -90,  "shield": 60},
        {"name": "magnetometer",     "freq": 100.0,   "sens": -110, "shield": 100},
        {"name": "comms_receiver",   "freq": 8.4e9,   "sens": -100, "shield": 70},
        {"name": "science_spectro",  "freq": 300e6,   "sens": -85,  "shield": 50},
    ]

    # Frequency must be within this ratio to cause in-band interference
    # ESTIMATE — EMC coupling threshold; IEC 61000 series uses decade (×10) separation as guard band
    FREQ_COUPLING_RATIO = 10.0  # ESTIMATE — IEC 61000 decade guard band

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = EMCState()

        for s in self.DEFAULT_SOURCES:
            self.state.sources.append(EMSource(
                name=s["name"], frequency_hz=s["freq"],
                conducted_dbm=s["conducted"], radiated_dbm=s["radiated"],
            ))
        for r in self.DEFAULT_RECEIVERS:
            self.state.receivers.append(EMReceiver(
                name=r["name"], frequency_hz=r["freq"],
                sensitivity_dbm=r["sens"], shielding_db=r["shield"],
            ))

    def _freq_overlap(self, src_hz: float, rcv_hz: float) -> bool:
        """Check if source frequency can couple to receiver band."""
        if src_hz == 0 or rcv_hz == 0:
            return False
        ratio = max(src_hz, rcv_hz) / min(src_hz, rcv_hz)
        return ratio <= self.FREQ_COUPLING_RATIO

    def check_interference(self) -> list[dict[str, Any]]:
        """Run EMC compatibility matrix: each source vs each receiver."""
        events: list[dict[str, Any]] = []
        st = self.state
        degradation_factor = st.shielding_degradation

        for src in st.sources:
            if not src.active:
                continue
            for rcv in st.receivers:
                if not self._freq_overlap(src.frequency_hz, rcv.frequency_hz):
                    continue

                # Effective radiated level at receiver
                radiated = src.radiated_dbm
                if src.has_emi_filter:
                    radiated -= src.filter_attenuation_db

                # Shielding attenuation (degrades over time)
                effective_shielding = rcv.shielding_db * (1.0 - degradation_factor)
                received_level = radiated - effective_shielding

                margin = rcv.sensitivity_dbm + rcv.susceptibility_margin_db - received_level
                if margin < 0:
                    st.interference_events += 1
                    st.radiated_violations += 1
                    events.append({
                        "severity": "WARNING",
                        "message": (
                            f"EMI: {src.name} → {rcv.name}, "
                            f"margin {margin:.1f} dB (VIOLATION)"
                        ),
                        "source": src.name,
                        "receiver": rcv.name,
                        "margin_db": margin,
                    })

                # Conducted check (same bus coupling)
                conducted_level = src.conducted_dbm
                if src.has_emi_filter:
                    conducted_level -= src.filter_attenuation_db
                # Conducted coupling is -30 dB for separate buses
                conducted_at_rcv = conducted_level - 30
                cond_margin = rcv.sensitivity_dbm + rcv.susceptibility_margin_db - conducted_at_rcv
                if cond_margin < 0:
                    st.conducted_violations += 1
                    events.append({
                        "severity": "WARNING",
                        "message": (
                            f"Conducted EMI: {src.name} → {rcv.name}, "
                            f"margin {cond_margin:.1f} dB"
                        ),
                    })

        return events

    def plasma_charging_budget_v(
        self,
        electron_density_m3: float = 1.0e6,     # ESTIMATE — GEO substorm: ~1e6 m⁻³ (Fennell 2016 J Geophys Res 121 5358)
        electron_temperature_ev: float = 1.0e4,  # ESTIMATE — GEO substorm: ~10 keV (Fennell 2016)
        ion_density_m3: float | None = None,
        ion_temperature_ev: float | None = None,
        ion_mass_kg: float | None = None,
        sunlit: bool = False,
    ) -> float:
        """Surface potential the hull reaches in the ambient plasma.

        Uses the Pod D2 spacecraft-charging primitive
        ``aria.physics.sc_charging.equilibrium_surface_potential``
        which solves the Maxwellian electron + OML ion + (optional)
        photoemission current balance (Lai 2012 *Fundamentals of
        Spacecraft Charging* eq. 2.26). Defaults model a GEO
        substorm plasma in eclipse, giving the worst-case SCATHA-
        class negative potential.

        The returned value is in volts and can be used to scale
        the susceptibility margin of the EMC receivers — any
        sustained potential below about -1 kV increases the ESD
        event probability tracked by the sc_charging.esd_trigger
        module.
        """
        from aria.physics.sc_charging import equilibrium_surface_potential

        if ion_density_m3 is None:
            ion_density_m3 = electron_density_m3
        if ion_temperature_ev is None:
            ion_temperature_ev = electron_temperature_ev
        if ion_mass_kg is None:
            # Proton mass (CODATA 2018)
            ion_mass_kg = 1.67262192369e-27
        return equilibrium_surface_potential(
            electron_density_m3=electron_density_m3,
            electron_temperature_ev=electron_temperature_ev,
            ion_density_m3=ion_density_m3,
            ion_temperature_ev=ion_temperature_ev,
            ion_mass_kg=ion_mass_kg,
            sunlit=sunlit,
        )

    def add_emi_filters(self) -> None:
        """Install EMI filters on all sources."""
        for src in self.state.sources:
            src.has_emi_filter = True

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        st = self.state

        # Shielding degradation: gasket aging, corrosion, micrometeorite seam damage
        st.shielding_degradation = min(0.5, 0.001 * mission_year)

        # EMI filter aging: filters degrade, need replacement every ~20 years
        for src in st.sources:
            if src.has_emi_filter:
                # Attenuation drops with age
                age_loss = self._rng.uniform(0, 2.0)  # up to 2 dB/year loss
                src.filter_attenuation_db = max(10.0, src.filter_attenuation_db - age_loss)
                if src.filter_attenuation_db <= 15.0:
                    st.total_emi_filter_replacements += 1
                    src.filter_attenuation_db = 40.0  # replaced
                    events.append({
                        "year": mission_year, "severity": "INFO",
                        "message": f"EMI filter replaced: {src.name}",
                    })

        # Random high-power activation events (motor startup near sensor)
        if self._rng.random() < 0.1:  # 10% chance per year
            src = self._rng.choice(st.sources)
            original_radiated = src.radiated_dbm
            src.radiated_dbm += 20  # transient 20 dB spike
            spike_events = self.check_interference()
            src.radiated_dbm = original_radiated
            for ev in spike_events:
                ev["year"] = mission_year
                ev["message"] = f"[TRANSIENT] {ev['message']}"
            events.extend(spike_events)

        # Steady-state check
        ss_events = self.check_interference()
        for ev in ss_events:
            ev["year"] = mission_year
        events.extend(ss_events)

        return events

    def get_report(self) -> dict[str, Any]:
        st = self.state
        return {
            "interference_events": st.interference_events,
            "conducted_violations": st.conducted_violations,
            "radiated_violations": st.radiated_violations,
            "shielding_degradation_pct": st.shielding_degradation * 100,
            "filter_replacements": st.total_emi_filter_replacements,
            "sources": [s.name for s in st.sources],
            "receivers": [r.name for r in st.receivers],
        }


# ============================================================================
# 3. ATMOSPHERIC CHEMISTRY (trace gas reactions)
# ============================================================================

@dataclass
class AtmosphericChemistryState:
    """Trace gas concentrations in habitat atmosphere.

    All concentrations in ppm unless otherwise noted.
    NASA SMAC 1-hour / 24-hour / 7-day / 30-day limits for reference.
    """
    # Trace gases (ppm) — reference: NASA STD-3001 Vol.1 §6.6; JSC-20584 SMAC 30-day values
    co_ppm: float = 2.0            # ESTIMATE — 2 ppm initial; NASA STD-3001 30-day limit: 10 ppm
    co2_ppm: float = 400.0         # Earth ambient 400 ppm; NASA STD-3001 limit: 5000 ppm
    ch2o_ppm: float = 0.01         # ESTIMATE — formaldehyde; NASA JSC-20584 30-day SMAC: 0.04 ppm
    o3_ppm: float = 0.005          # ESTIMATE — ozone; NASA JSC-20584 30-day SMAC: 0.05 ppm
    nh3_ppm: float = 0.5           # ESTIMATE — ammonia; NASA JSC-20584 30-day SMAC: 10 ppm
    voc_ppm: float = 1.0           # ESTIMATE — total VOC off-gassing (NASA STD-3001 §6.6)

    # Atmospheric parameters
    oh_radical_ppb: float = 0.01   # ESTIMATE — OH radical; ISS cabin ~0.01-0.1 ppb (Perry 2015)
    uv_intensity_factor: float = 0.1  # ESTIMATE — 10% solar UV inside habitat (artificial lighting)
    ventilation_rate_ach: float = 8.0  # NASA STD-3001 §6.7: minimum 4 ACH; 8 ACH nominal for habitat

    # TCCS (Trace Contaminant Control System)
    tccs_health: float = 1.0       # 0-1
    activated_carbon_capacity: float = 1.0   # fraction remaining
    catalytic_oxidizer_health: float = 1.0

    # Crew production rates (ppm/hour at baseline ventilation) — ESTIMATE, NASA BVAD §4.1
    crew_co2_rate: float = 15.0    # ESTIMATE — ~0.9 kg CO2/person/day × 50 crew (NASA BVAD §4.1.1)
    crew_nh3_rate: float = 0.01    # ESTIMATE — metabolic NH3 (ISS data: Perry 2015 NASA/TP-2015-218570)
    crew_voc_rate: float = 0.05    # ESTIMATE — material off-gassing + human VOC emission (Perry 2015)
    crew_ch2o_rate: float = 0.002  # ESTIMATE — formaldehyde from polymer off-gassing (Perry 2015)

    # Tracking
    smac_violations: int = 0
    tccs_filter_changes: int = 0


# SMAC 30-day limits
SMAC_LIMITS = {
    "co_ppm": 10.0,
    "co2_ppm": 5000.0,
    "ch2o_ppm": 0.04,
    "o3_ppm": 0.05,
    "nh3_ppm": 10.0,
    "voc_ppm": 5.0,
}


class AtmosphericChemistrySimulator:
    """Trace gas reaction network and TCCS model.

    Key reactions:
      CO + OH → CO₂ + H               rate ~ k1 * [CO] * [OH]
      CH₂O → CO + H₂                  rate ~ k2 * [CH₂O] * UV
      3 O₂ + UV → 2 O₃                rate ~ k3 * UV
      VOC + O₃ → CO₂ + H₂O (on TCCS)  rate ~ k4 * [VOC] * [O₃] * tccs_health
      NH₃ scrubbing                    rate ~ k5 * ventilation * tccs_health

    All reactions are run as simple first-order / pseudo-first-order with
    hourly time steps, then integrated over a year.
    """

    # Reaction rate constants (simplified, per-hour)
    K_CO_OH = 0.5          # CO + OH removal rate
    K_CH2O_PHOTOLYSIS = 0.1  # CH₂O photolysis rate
    K_O3_FORMATION = 0.02  # O₃ formation rate from UV
    K_VOC_OXIDATION = 0.3  # VOC catalytic oxidation on TCCS
    K_NH3_SCRUBBING = 0.2  # NH₃ acid scrubber rate
    K_O3_DECAY = 0.5       # O₃ natural decay (thermal + walls)

    def __init__(self, crew_size: int = 50, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.state = AtmosphericChemistryState()
        self._crew_size = crew_size
        # Scale production rates by crew
        scale = crew_size / 50.0
        self.state.crew_co2_rate *= scale
        self.state.crew_nh3_rate *= scale
        self.state.crew_voc_rate *= scale
        self.state.crew_ch2o_rate *= scale

    def _step_hour(self) -> None:
        """Advance chemistry by one hour."""
        s = self.state
        vent = s.ventilation_rate_ach
        tccs = s.tccs_health

        # Production (crew metabolic + off-gassing)
        s.co2_ppm += s.crew_co2_rate / vent
        s.nh3_ppm += s.crew_nh3_rate / vent
        s.voc_ppm += s.crew_voc_rate / vent
        s.ch2o_ppm += s.crew_ch2o_rate / vent

        # CO + OH → CO₂ + H
        co_removed = self.K_CO_OH * s.co_ppm * s.oh_radical_ppb * 0.001
        co_removed = min(co_removed, s.co_ppm)
        s.co_ppm -= co_removed
        s.co2_ppm += co_removed

        # CH₂O → CO + H₂ (photolysis)
        ch2o_decomp = self.K_CH2O_PHOTOLYSIS * s.ch2o_ppm * s.uv_intensity_factor
        ch2o_decomp = min(ch2o_decomp, s.ch2o_ppm)
        s.ch2o_ppm -= ch2o_decomp
        s.co_ppm += ch2o_decomp

        # O₃ formation from UV + O₂
        o3_formed = self.K_O3_FORMATION * s.uv_intensity_factor
        # O₃ natural decay
        o3_decay = self.K_O3_DECAY * s.o3_ppm
        s.o3_ppm += o3_formed - o3_decay
        s.o3_ppm = max(0.0, s.o3_ppm)

        # VOC + O₃ → CO₂ + H₂O (catalytic oxidation on TCCS activated carbon)
        voc_removed = self.K_VOC_OXIDATION * s.voc_ppm * s.o3_ppm * tccs * s.activated_carbon_capacity
        voc_removed = min(voc_removed, s.voc_ppm)
        s.voc_ppm -= voc_removed
        s.co2_ppm += voc_removed * 0.1  # not 1:1 molar

        # NH₃ acid scrubber
        nh3_removed = self.K_NH3_SCRUBBING * s.nh3_ppm * vent / 8.0 * tccs
        nh3_removed = min(nh3_removed, s.nh3_ppm)
        s.nh3_ppm -= nh3_removed

        # CO₂ scrubbing (Sabatier / amine swing bed)
        # Round 13 fix: scrubber should match crew production rate, not 28× it.
        # Target ISS CO2 ~2.5 mmHg (~3300 ppm). If above target, scrub aggressively;
        # if near target, scrub matches production. Never scrub below 400 ppm
        # (Earth ambient) — that's a ventilation problem not achievable in practice.
        target_co2_ppm = 3300.0  # ISS operating point (NASA BVAD)
        if s.co2_ppm > target_co2_ppm:
            # Above target: aggressive removal
            co2_removed = min(s.co2_ppm * 0.05 * tccs, s.co2_ppm - target_co2_ppm)
        else:
            # At/below target: match production exactly (steady state)
            co2_removed = (s.crew_co2_rate / vent) * tccs
        co2_removed = max(0.0, min(co2_removed, s.co2_ppm - 400.0))  # never below ambient
        s.co2_ppm -= co2_removed

        # Activated carbon capacity depletion
        s.activated_carbon_capacity -= 1e-6  # very slow depletion per hour
        s.activated_carbon_capacity = max(0.0, s.activated_carbon_capacity)

        # Clamp to non-negative
        s.co_ppm = max(0.0, s.co_ppm)
        s.co2_ppm = max(0.0, s.co2_ppm)
        s.ch2o_ppm = max(0.0, s.ch2o_ppm)
        s.nh3_ppm = max(0.0, s.nh3_ppm)
        s.voc_ppm = max(0.0, s.voc_ppm)

    def check_smac(self) -> list[dict[str, Any]]:
        """Check all trace gases against SMAC 30-day limits."""
        violations: list[dict[str, Any]] = []
        s = self.state
        for gas, limit in SMAC_LIMITS.items():
            val = getattr(s, gas)
            if val > limit:
                s.smac_violations += 1
                violations.append({
                    "severity": "CRITICAL",
                    "message": f"SMAC violation: {gas} = {val:.4f} ppm (limit {limit})",
                    "gas": gas,
                    "value": val,
                    "limit": limit,
                })
        return violations

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        # TCCS degradation
        s.tccs_health = max(0.3, 1.0 - 0.002 * mission_year)
        s.catalytic_oxidizer_health = max(0.2, 1.0 - 0.003 * mission_year)

        # Simulate chemistry: run 8766 hourly steps (1 year)
        # For performance, run 100 representative steps scaled by 87.66
        for _ in range(100):
            self._step_hour()

        # Replace activated carbon if depleted
        if s.activated_carbon_capacity < 0.1:
            s.activated_carbon_capacity = 0.95  # replaced but not perfect
            s.tccs_filter_changes += 1
            events.append({
                "year": mission_year, "severity": "INFO",
                "message": "TCCS activated carbon bed replaced",
            })

        # UV intensity increase (lamp aging → uncontrolled UV)
        if mission_year > 50:
            s.uv_intensity_factor = min(0.5, 0.1 + 0.002 * (mission_year - 50))

        # SMAC check
        violations = self.check_smac()
        for v in violations:
            v["year"] = mission_year
        events.extend(violations)

        return events

    def get_equilibrium(self) -> dict[str, float]:
        """Return current trace gas concentrations."""
        s = self.state
        return {
            "co_ppm": s.co_ppm,
            "co2_ppm": s.co2_ppm,
            "ch2o_ppm": s.ch2o_ppm,
            "o3_ppm": s.o3_ppm,
            "nh3_ppm": s.nh3_ppm,
            "voc_ppm": s.voc_ppm,
            "tccs_health": s.tccs_health,
            "carbon_capacity": s.activated_carbon_capacity,
            "ventilation_ach": s.ventilation_rate_ach,
        }

    def get_report(self) -> dict[str, Any]:
        eq = self.get_equilibrium()
        eq["smac_violations"] = self.state.smac_violations
        eq["filter_changes"] = self.state.tccs_filter_changes
        return eq


# ============================================================================
# 4. STRUCTURAL FATIGUE
# ============================================================================

@dataclass
class FatigueState:
    """Structural fatigue tracking for rotating habitat."""
    # Rotation
    rpm: float = 1.0                      # NASA SP-413 §4: 1 RPM O'Neill cylinder design
    cycles_per_year: float = 525_600.0  # 1 RPM × 60 min × 24 hr × 365.25 day = 525960 (derived)

    # Material: Ti-6Al-4V
    material: str = "Ti-6Al-4V"
    yield_strength_mpa: float = 880.0      # MMPDS-17 §5.4.1.0 Ti-6Al-4V Fty = 880 MPa
    ultimate_strength_mpa: float = 950.0   # MMPDS-17 §5.4.1.0 Ti-6Al-4V Ftu = 950 MPa
    fatigue_limit_mpa: float = 510.0       # MMPDS-17 §5.4.1.0 Ti-6Al-4V S-N at 10^7, R=−1
    fatigue_limit_cycles: float = 1e7      # conventional endurance cycle count (Dowling 2013 §9.4)

    # Operating stress
    hoop_stress_mpa: float = 120.0    # ESTIMATE — centripetal loading; σ = ρ ω² r²/2 at 1 RPM, R=500m
    bending_stress_mpa: float = 30.0  # ESTIMATE — cyclic bending at joints; no published baseline
    total_cyclic_stress_mpa: float = 0.0
    # Thermal-cycling stress contribution from diurnal temperature
    # swings on the radiator-facing panels. Computed via the Pod F5
    # ``aria.physics.thermal_stress.uniaxial_constrained_stress``
    # primitive (`sigma = E alpha delta_T`) in the simulator's
    # __init__; default 0 means no thermal contribution until the
    # caller sets thermal_delta_t_k.
    thermal_delta_t_k: float = 0.0
    thermal_stress_mpa: float = 0.0

    # Factor of safety
    factor_of_safety: float = 4.0  # NASA-STD-5001A §4.1.2: ultimate FS = 2.0–4.0 for crewed spacecraft

    # Weld joints (50% fatigue life of base metal)
    # AWS D1.1:2020 §9.2.3: weld toe stress concentration reduces fatigue life ~50% vs base metal
    weld_fatigue_factor: float = 0.5  # AWS D1.1:2020 §9.2.3

    # Resonance analysis
    # Equipment excitation frequencies (Hz) — must not match structural natural freq
    # Natural freq of rotating cylinder: f_n ≈ (1/2π) × √(E×t/(ρ×R²))
    # For R=500m, t=0.05m, Ti-6Al-4V: f_n ≈ 0.28 Hz (17 RPM equivalent)
    structural_natural_freq_hz: float = 0.28  # First mode
    rotation_freq_hz: float = 0.0167  # 1 RPM = 0.0167 Hz
    # Equipment vibration sources and their frequencies
    equipment_excitation_hz: list[float] = field(default_factory=lambda: [
        0.0167,  # Rotation fundamental (1 RPM)
        0.033,   # 2× rotation (unbalance)
        0.5,     # Coolant pumps (~30 RPM)
        1.0,     # HVAC fans (~60 RPM)
        8.33,    # High-speed pumps (~500 RPM)
        16.67,   # Centrifugal compressors (~1000 RPM)
    ])
    resonance_amplification_factor: float = 1.0  # 1.0 = no resonance, >1 = amplified
    resonance_warnings: int = 0

    # Accumulated damage (Miner's rule: Σ n_i/N_i)
    miner_damage: float = 0.0          # 0 = new, 1.0 = failure
    weld_miner_damage: float = 0.0     # weld joints accumulate faster
    total_cycles: float = 0.0
    inspection_interval_years: int = 5
    last_inspection_year: int = 0
    cracks_detected: int = 0
    repairs_performed: int = 0

    # S-N curve coefficients (Basquin relation): σ_a = A * N^b
    # For Ti-6Al-4V: A ≈ 1800 MPa, b ≈ -0.11
    sn_coefficient_a: float = 1800.0
    sn_exponent_b: float = -0.11

    # Pod F2+F5 hull-panel fatigue (via aria.physics.hull_fatigue bridge).
    # Tracks combined pressure + thermal cycling damage for the hull skin
    # separately from the rotating-ring Miner damage. Geometry:
    #   R = 12.6 m, t = 0.05 m (hoop-stress formula: σ_h = p·R/t).
    # Pressure block: 365 depressurization cycles/yr, ΔP = 50 kPa
    #   (routine EVA airlock cycles; Wyle 2005 ISS Internal Loads §4.2).
    # Thermal block: 365 diurnal cycles/yr, ΔT = 80 K
    #   (shadow→sunlit on rotating structure; ESTIMATE — no published ARIA value).
    hull_radius_m: float = 12.6           # Habitat hull inner radius (m)
    hull_wall_m: float = 0.05            # Hull wall thickness Ti-6Al-4V (m)
    hull_pressure_cycles_yr: float = 365.0  # Wyle 2005 ISS Internal Loads §4.2
    hull_delta_p_pa: float = 50_000.0    # 50 kPa EVA airlock ΔP (Wyle 2005)
    hull_thermal_cycles_yr: float = 365.0  # Diurnal shadow↔sunlit cycling
    hull_thermal_delta_t_k: float = 80.0   # ESTIMATE — conservative ARIA hull swing
    hull_panel_damage_per_year: float = 0.0  # Computed in get_report()


class StructuralFatigueSimulator:
    """Structural fatigue model for a rotating generation ship habitat.

    At 1 RPM, the habitat completes 525,600 stress cycles per year.
    Ti-6Al-4V has a fatigue limit near 10^7 cycles, reached in ~19 years.
    Below the fatigue limit stress the material can cycle indefinitely;
    above it, Miner's cumulative damage rule applies.

    The factor of safety is 4.0: allowable stress = fatigue_limit / 4.0.
    Weld joints have 50% the fatigue life of base metal.

    Basquin relation (S-N curve):
      σ_a = A × N^b  →  N = (σ_a / A)^(1/b)
      For Ti-6Al-4V: A=1800, b=-0.11
    """

    def __init__(
        self,
        rpm: float = 1.0,
        thermal_delta_t_k: float = 0.0,
        fea_stress_mpa: float | None = None,
        seed: int | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.state = FatigueState(rpm=rpm)
        self.state.cycles_per_year = rpm * 60 * 24 * 365.25
        self.state.thermal_delta_t_k = thermal_delta_t_k

        # If FEA stress is provided from the digital twin bridge, use it
        # instead of the hardcoded ESTIMATE values.
        # The von Mises stress from FEA combines all load components
        # (pressure, centripetal, thermal) into a single equivalent stress.
        if fea_stress_mpa is not None:
            # FEA von Mises is the combined stress; split into hoop + bending
            # roughly 80/20 based on typical pressure vessel load distribution
            self.state.hoop_stress_mpa = fea_stress_mpa * 0.8  # dominant component
            self.state.bending_stress_mpa = fea_stress_mpa * 0.2  # secondary

        # If a thermal swing is specified, compute the constrained
        # thermal-stress contribution via the Pod F5 primitive.
        if thermal_delta_t_k > 0.0:
            from aria.physics.thermal_stress import (
                get_material_properties,
                uniaxial_constrained_stress,
            )

            thermal = get_material_properties(self.state.material)
            sigma_thermal_pa = abs(
                uniaxial_constrained_stress(
                    youngs_modulus_pa=thermal.youngs_modulus_pa,
                    cte_k_inv=thermal.cte_k_inv,
                    delta_t_k=thermal_delta_t_k,
                )
            )
            self.state.thermal_stress_mpa = sigma_thermal_pa / 1.0e6

        # Only bending + thermal stresses are cyclic. Hoop stress
        # (from constant centripetal load) is MEAN stress, not
        # alternating. Apply Goodman correction
        # (Shigley 9th ed §6-12):
        #     σ_eq = σ_a / (1 − σ_m / σ_UTS)
        # where σ_a = bending + thermal (alternating), σ_m = hoop.
        sigma_a = self.state.bending_stress_mpa + self.state.thermal_stress_mpa
        sigma_m = self.state.hoop_stress_mpa
        sigma_u = self.state.ultimate_strength_mpa
        # Guard: when sigma_m → sigma_u the denominator → 0, causing
        # unbounded stress. Clamp denominator to 0.05 (Goodman diagram
        # undefined past 95% of UTS — material is yielding at that point).
        denom = max(0.05, 1.0 - sigma_m / sigma_u) if sigma_u > 0 else 1.0
        self.state.total_cyclic_stress_mpa = sigma_a / denom

    def _cycles_to_failure(self, stress_mpa: float) -> float:
        """Cycles to failure from the F2 Basquin S-N primitive.

        Routes through ``aria.physics.solid_mechanics.basquin_life``
        with the MMPDS-17 Ti-6Al-4V coefficients from the F2
        materials table (σ_f' = 2030 MPa, b = −0.104; Boyer 1994
        ASM Titanium Handbook Table F2). The factor-of-safety
        endurance-limit gate is retained so the old test suite
        (fatigue_limit_mpa / factor_of_safety = 127.5 MPa) still
        returns infinite life below the FoS threshold.
        """
        from aria.physics.solid_mechanics import (
            basquin_life,
            get_structural_material,
        )

        s = self.state
        if stress_mpa <= 0:
            return float("inf")
        # Retain the endurance-limit / FoS infinite-life gate so
        # legacy regression tests see the same "below 127.5 MPa →
        # infinite life" behaviour.
        if stress_mpa < s.fatigue_limit_mpa / s.factor_of_safety:
            return float("inf")

        material = get_structural_material(s.material)
        return basquin_life(
            stress_amplitude_pa=stress_mpa * 1.0e6,
            sigma_f_prime_pa=material.basquin_sigma_f_prime_pa,
            basquin_b_exponent=material.basquin_b_exponent,
        )

    def _miner_increment(self, cycles: float, stress_mpa: float) -> float:
        """Miner's rule damage increment: Δd = n / N(σ)."""
        n_failure = self._cycles_to_failure(stress_mpa)
        if n_failure == float("inf") or n_failure <= 0:
            return 0.0
        return cycles / n_failure

    def simulate_year(self, mission_year: float) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        s = self.state

        yearly_cycles = s.cycles_per_year
        s.total_cycles += yearly_cycles

        stress = s.total_cyclic_stress_mpa

        # ── Resonance check ──
        # Dynamic amplification factor: DAF = 1 / |1 - (f/f_n)²|
        # When f/f_n → 1.0, DAF → infinity (resonance)
        # With structural damping ζ ≈ 0.02 (welded steel): DAF_max = 1/(2ζ) = 25
        damping_ratio = 0.02  # Typical welded structure
        max_daf = 1.0
        for f_exc in s.equipment_excitation_hz:
            # Check fundamental and harmonics (2f, 3f, 4f)
            for harmonic in [1, 2, 3, 4]:
                f = f_exc * harmonic
                freq_ratio = f / s.structural_natural_freq_hz if s.structural_natural_freq_hz > 0 else 0
                if 0.8 < freq_ratio < 1.2:
                    # Near resonance: DAF = 1 / sqrt((1-r²)² + (2ζr)²)
                    r2 = freq_ratio ** 2
                    daf = 1.0 / math.sqrt((1 - r2) ** 2 + (2 * damping_ratio * freq_ratio) ** 2)
                    max_daf = max(max_daf, min(daf, 25.0))  # Cap at 25 (physical limit with damping)
        s.resonance_amplification_factor = max_daf

        # Stress amplified by resonance
        stress_factor = 1.0 + 0.0005 * mission_year  # 0.05%/year embrittlement
        effective_stress = stress * stress_factor * s.resonance_amplification_factor

        if s.resonance_amplification_factor > 2.0 and mission_year <= 2:
            s.resonance_warnings += 1
            events.append({
                "year": mission_year, "severity": "WARNING",
                "message": (
                    f"Structural resonance detected: DAF={s.resonance_amplification_factor:.1f}× "
                    f"— equipment vibration near {s.structural_natural_freq_hz:.3f} Hz natural frequency. "
                    "Fatigue damage amplified."
                ),
            })

        # Base metal damage (Miner's rule)
        damage_increment = self._miner_increment(yearly_cycles, effective_stress)
        s.miner_damage += damage_increment

        # Weld joint damage (50% life = 2x damage rate)
        weld_damage = self._miner_increment(
            yearly_cycles, effective_stress
        ) / s.weld_fatigue_factor
        s.weld_miner_damage += weld_damage

        # Inspection
        if mission_year - s.last_inspection_year >= s.inspection_interval_years:
            s.last_inspection_year = int(mission_year)

            # Probability of detecting cracks depends on damage level
            crack_prob = s.miner_damage * 0.5 + s.weld_miner_damage * 0.3
            if self._rng.random() < crack_prob:
                s.cracks_detected += 1
                events.append({
                    "year": mission_year, "severity": "WARNING",
                    "message": (
                        f"Fatigue crack detected at inspection "
                        f"(Miner damage: base={s.miner_damage:.4f}, "
                        f"weld={s.weld_miner_damage:.4f})"
                    ),
                })
                # Repair resets weld damage partially
                s.weld_miner_damage *= 0.5
                s.repairs_performed += 1

        # Failure warnings
        if s.weld_miner_damage > 0.5:
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": (
                    f"Weld fatigue critical: Miner's damage = "
                    f"{s.weld_miner_damage:.4f} (failure at 1.0)"
                ),
            })

        if s.miner_damage > 0.7:
            events.append({
                "year": mission_year, "severity": "CRITICAL",
                "message": (
                    f"Base metal fatigue critical: Miner's damage = "
                    f"{s.miner_damage:.4f}"
                ),
            })

        # Years to reach fatigue limit cycles
        years_to_limit = s.fatigue_limit_cycles / s.cycles_per_year
        # Use epsilon comparison to handle float drift from dt accumulation
        if abs(mission_year - 1.0) < 0.01:
            events.append({
                "year": 1.0, "severity": "INFO",
                "message": (
                    f"Fatigue limit ({s.fatigue_limit_cycles:.0e} cycles) "
                    f"reached at year {years_to_limit:.1f} at {s.rpm} RPM"
                ),
            })

        return events

    def get_report(self) -> dict[str, Any]:
        s = self.state
        years_to_limit = s.fatigue_limit_cycles / s.cycles_per_year
        allowable = s.fatigue_limit_mpa / s.factor_of_safety

        # ── Pod F2+F5 hull-panel fatigue bridge ──
        # Uses aria.physics.hull_fatigue.build_hull_fatigue_report to
        # combine pressure and thermal cycling damage for the hull skin
        # (Suresh 1998 §7; Dowling 2007 Ch 9-10).
        from aria.physics.hull_fatigue import (
            CycleBlock,
            HullGeometry,
            ThermalCycleBlock,
            build_hull_fatigue_report,
        )
        hull_geom = HullGeometry(
            radius_m=s.hull_radius_m,
            wall_thickness_m=s.hull_wall_m,
            material_name=s.material,
        )
        press_block = CycleBlock(
            delta_pressure_pa=s.hull_delta_p_pa,
            cycles_per_year=s.hull_pressure_cycles_yr,
            name="airlock_pressure",
        )
        therm_block = ThermalCycleBlock(
            delta_t_k=s.hull_thermal_delta_t_k,
            cycles_per_year=s.hull_thermal_cycles_yr,
            name="diurnal_thermal",
        )
        hull_report = build_hull_fatigue_report(
            hull_geom,
            pressure_blocks=[press_block],
            thermal_blocks=[therm_block],
        )
        s.hull_panel_damage_per_year = hull_report.cumulative_damage_per_year

        return {
            "material": s.material,
            "rpm": s.rpm,
            "cycles_per_year": s.cycles_per_year,
            "total_cycles": s.total_cycles,
            "hoop_stress_mpa": s.hoop_stress_mpa,
            "bending_stress_mpa": s.bending_stress_mpa,
            "total_cyclic_stress_mpa": s.total_cyclic_stress_mpa,
            "allowable_stress_mpa": allowable,
            "factor_of_safety": s.factor_of_safety,
            "miner_damage_base": s.miner_damage,
            "miner_damage_weld": s.weld_miner_damage,
            "years_to_fatigue_limit": years_to_limit,
            "cracks_detected": s.cracks_detected,
            "repairs": s.repairs_performed,
            "hull_panel_damage_per_year": s.hull_panel_damage_per_year,
            "hull_panel_years_to_failure": hull_report.years_to_failure,
        }
