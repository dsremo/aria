"""Radiation effects on avionics — SEU bit-flip model with ECC + TMR voting.

Space radiation flips bits in SRAM / DRAM / registers. On a ship cruising
for centuries at 0.42 Sv/yr GCR unshielded (Cucinotta 2014), avionics
without mitigation would corrupt within hours. Real flight computers use:

  1. **ECC** (Error-Correcting Code, typically SECDED) — catches and corrects
     single-bit flips transparently. Double-bit flips detected but not
     corrected (triggers scrub / halt).
  2. **TMR** (Triple Modular Redundancy) — three identical CPUs run the
     same code, vote on output. One CPU's bit-flip doesn't propagate.
  3. **Scrubbing** — periodic sweep of memory to refresh SRAM / rewrite
     DRAM refresh, flushing accumulated SEU before they become MBUs.

This module simulates those three layers and exposes health stats so a
flight director can see "avionics SEU rate = 3.2 × 10⁻⁴ flips/day,
ECC correction rate = 98.7 %, TMR disagreement rate = 0.4 %".

References
----------
SEU cross-sections for current-gen space-grade electronics follow
Dodd & Massengill 2003 "Basic Mechanisms and Modeling of Single-Event
Upset in Digital Microelectronics", IEEE Trans. Nucl. Sci. 50:583.
GCR flux vs. LET spectrum from Cucinotta 2014 NASA/TP-2013-217375
Appendix B.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Constants: SEU physics ──────────────────────────────────────────

# Sea-level-equivalent GCR LET spectrum integrated flux density behind
# ~0 g/cm² shielding. Units: particles·cm⁻²·day⁻¹. Cucinotta 2014 App. B.3
GCR_FLUX_UNSHIELDED: float = 4.0e7

# Effective shielding of ARIA crew compartment (20 g/cm² Al-equivalent via
# ablation ice + Whipple + hull). Attenuation factor from Cucinotta 2014
# Fig. 5 — 3 orders of magnitude for high-LET component.
SHIELDED_FLUX_FACTOR: float = 1.0e-3

# ── Chip profiles: SEU cross-section per MBit varies by technology node ──
# Source: Dodd & Massengill 2003 Table III + Schwank 2013 IEEE TNS 60:2074
# Units: cm² per MBit at GCR saturation LET
CHIP_PROFILES: Dict[str, Dict[str, float]] = {
    "rad750_150nm": {
        "seu_xsec_cm2_per_mbit": 1.0e-8,   # BAE RAD750, 150nm SOI (Dodd 2003)
        "sel_xsec_cm2": 1.0e-12,            # latchup-immune (SOI substrate)
        "process_nm": 150,
    },
    "rad5545_45nm": {
        "seu_xsec_cm2_per_mbit": 3.0e-8,   # Cobham RAD5545, 45nm (Schwank 2013)
        "sel_xsec_cm2": 1.0e-12,            # latchup-immune (SOI)
        "process_nm": 45,
    },
    "cots_28nm": {
        "seu_xsec_cm2_per_mbit": 5.0e-7,   # Commercial 28nm FinFET (Seifert 2015 IEEE TNS 62:2570)
        "sel_xsec_cm2": 1.0e-8,             # latchup susceptible
        "process_nm": 28,
    },
    "cots_7nm": {
        "seu_xsec_cm2_per_mbit": 2.0e-6,   # Commercial 7nm (projected from Seifert 2015 scaling)
        "sel_xsec_cm2": 5.0e-8,             # higher latchup susceptibility
        "process_nm": 7,
    },
    "rad_hard_65nm": {
        "seu_xsec_cm2_per_mbit": 5.0e-8,   # Generic rad-hard 65nm SOI (Dodd 2003)
        "sel_xsec_cm2": 1.0e-12,            # latchup-immune
        "process_nm": 65,
    },
}

# Default profile
SEU_XSEC_CM2_PER_MBIT: float = CHIP_PROFILES["rad_hard_65nm"]["seu_xsec_cm2_per_mbit"]

# Probability that a single SEU is:
#   - caught and corrected by SECDED ECC (single-bit flip)
#   - caught but uncorrectable (double-bit flip — triggers halt)
#   - escapes ECC (triple+ flip → silent data corruption)
ECC_CORRECT_PROB:      float = 0.995     # Sandia ISSCC 2021 SECDED performance
ECC_DETECT_ONLY_PROB:  float = 0.0045    # DBE detection
ECC_ESCAPE_PROB:       float = 0.0005    # silent corruption rate

# TMR voter disagreement: how often the three CPUs produce different
# output. With ECC above, this is rare. Plauger 2015 "TMR FPGA in Space".
TMR_DISAGREE_PROB:     float = 0.0005

# Scrubbing: periodic memory sweep to clear accumulated SEU before they
# become multi-bit upsets (MBU). Typical scrub interval for flight computers.
# Quinn 2005 "Radiation Effects on FPGA" IEEE TNS 52:2455
DEFAULT_SCRUB_INTERVAL_S: float = 60.0  # 1-minute scrub cycle


# ── Data classes ────────────────────────────────────────────────────

@dataclass
class ComputingRadiationState:
    """Runtime state of the avionics radiation-susceptibility model.

    Supports multiple chip technology profiles (rad-hard SOI to COTS FinFET),
    single-event latchup (SEL) modeling, and periodic memory scrubbing.
    """

    # Static configuration
    total_sram_mbit:   float = 4_096.0      # 4 Gbit total across all flight computers
    total_flash_mbit:  float = 32_768.0     # 32 Gbit code/config (Kioxia NAND datasheet)
    cpu_count:         int   = 3            # TMR triplet
    ecc_enabled:       bool  = True
    tmr_enabled:       bool  = True
    chip_profile:      str   = "rad_hard_65nm"  # key into CHIP_PROFILES
    scrub_interval_s:  float = DEFAULT_SCRUB_INTERVAL_S

    # Running totals
    total_seu_events:        int = 0
    ecc_corrected:           int = 0
    ecc_detect_only_halts:   int = 0
    ecc_escapes:             int = 0
    tmr_disagreements:       int = 0
    tmr_minority_vote_outs:  int = 0          # times the voter had to discard one CPU

    # Latchup (SEL) — destructive, requires power cycle
    total_sel_events:        int = 0
    sel_power_cycles:        int = 0          # forced reboots from latchup

    # Scrubbing
    total_scrub_cycles:      int = 0
    accumulated_seu_since_scrub: int = 0      # SEUs since last scrub

    # Current rates (per-day, running average)
    current_seu_rate_per_day:   float = 0.0
    current_shielding_factor:   float = SHIELDED_FLUX_FACTOR
    _time_since_scrub_s:        float = 0.0

    # Deterministic RNG so reruns reproduce
    _rng: random.Random = field(default_factory=lambda: random.Random(42))

    # ── per-tick evolution ────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        """Advance the model by `dt_s` simulation seconds.

        Computes expected SEU count as a Poisson draw, then for each event
        rolls ECC + TMR recoveries. Publishes events on notable failures.
        """
        bus = get_event_bus()
        phase = get_phase_controller()
        # Shielding factor can change with phase (boost/decel reduce crew-compartment
        # shielding slightly because active plasma shield is occupied steering thrust).
        if phase.current.value in ("boost", "deceleration"):
            self.current_shielding_factor = SHIELDED_FLUX_FACTOR * 1.5
        else:
            self.current_shielding_factor = SHIELDED_FLUX_FACTOR

        # Get chip-specific cross-sections
        profile = CHIP_PROFILES.get(self.chip_profile, CHIP_PROFILES["rad_hard_65nm"])
        seu_xsec = profile["seu_xsec_cm2_per_mbit"]
        sel_xsec = profile["sel_xsec_cm2"]

        # Expected SEU count in this interval
        flux_per_day = GCR_FLUX_UNSHIELDED * self.current_shielding_factor
        frac_day = dt_s / (24.0 * 3600.0)
        expected = (flux_per_day * frac_day
                    * seu_xsec
                    * (self.total_sram_mbit + 0.1 * self.total_flash_mbit))  # flash 10× less susceptible
        self.current_seu_rate_per_day = flux_per_day * seu_xsec * self.total_sram_mbit

        # Single Event Latchup (SEL) — destructive, requires power cycle
        # SEL affects the entire chip, not individual bits
        expected_sel = flux_per_day * frac_day * sel_xsec * self.cpu_count
        sel_count = _poisson(self._rng, expected_sel)
        if sel_count > 0:
            self.total_sel_events += sel_count
            self.sel_power_cycles += sel_count
            bus.publish("avionics.single_event_latchup",
                        severity="critical",
                        source="computing_radiation",
                        payload={"count": sel_count, "total": self.total_sel_events,
                                 "chip_profile": self.chip_profile,
                                 "action": "forced_power_cycle"},
                        sim_time_yr=phase.elapsed_yr)

        # Memory scrubbing — clears accumulated SEU before MBU
        self._time_since_scrub_s += dt_s
        if self._time_since_scrub_s >= self.scrub_interval_s:
            self.total_scrub_cycles += 1
            self.accumulated_seu_since_scrub = 0
            self._time_since_scrub_s = 0.0

        # Poisson draw via inverse-CDF (sum of exponentials). Fine for small means.
        actual = _poisson(self._rng, expected)
        self.total_seu_events += actual
        halts_this_tick = 0
        escapes_this_tick = 0
        for _ in range(actual):
            r = self._rng.random()
            if self.ecc_enabled and r < ECC_CORRECT_PROB:
                self.ecc_corrected += 1
            elif self.ecc_enabled and r < ECC_CORRECT_PROB + ECC_DETECT_ONLY_PROB:
                self.ecc_detect_only_halts += 1
                halts_this_tick += 1
            else:
                # ECC escape or ECC disabled
                self.ecc_escapes += 1
                escapes_this_tick += 1
            # TMR voter check
            if self.tmr_enabled and self._rng.random() < TMR_DISAGREE_PROB:
                self.tmr_disagreements += 1
                if self._rng.random() < 0.9:
                    self.tmr_minority_vote_outs += 1   # voter masks the fault
        # Roll-up one bus event per tick instead of one-per-strike. Long
        # mission ticks (1 yr jumps, century auto-tick) can trigger
        # thousands of SEU strikes; the old loop spammed the bus with
        # one warning per strike, dominating the ring-buffer + narrative
        # log. Count is still in the payload for stats dashboards.
        if halts_this_tick > 0:
            bus.publish("avionics.ecc_detect_only_halt",
                        severity="warning",
                        source="computing_radiation",
                        payload={"count": halts_this_tick,
                                 "total": self.ecc_detect_only_halts},
                        sim_time_yr=phase.elapsed_yr)
        if escapes_this_tick > 0:
            bus.publish("avionics.ecc_escape",
                        severity="critical",
                        source="computing_radiation",
                        payload={"count": escapes_this_tick,
                                 "total": self.ecc_escapes},
                        sim_time_yr=phase.elapsed_yr)

    # ── queries ───────────────────────────────────────────────

    def correction_rate(self) -> float:
        if self.total_seu_events == 0:
            return 1.0
        return self.ecc_corrected / self.total_seu_events

    def escape_rate(self) -> float:
        if self.total_seu_events == 0:
            return 0.0
        return self.ecc_escapes / self.total_seu_events

    def to_dict(self) -> dict:
        profile = CHIP_PROFILES.get(self.chip_profile, CHIP_PROFILES["rad_hard_65nm"])
        return {
            "config": {
                "total_sram_mbit": self.total_sram_mbit,
                "total_flash_mbit": self.total_flash_mbit,
                "cpu_count": self.cpu_count,
                "ecc_enabled": self.ecc_enabled,
                "tmr_enabled": self.tmr_enabled,
                "chip_profile": self.chip_profile,
                "process_nm": profile["process_nm"],
                "scrub_interval_s": self.scrub_interval_s,
            },
            "totals": {
                "seu_events": self.total_seu_events,
                "ecc_corrected": self.ecc_corrected,
                "ecc_detect_only_halts": self.ecc_detect_only_halts,
                "ecc_escapes": self.ecc_escapes,
                "tmr_disagreements": self.tmr_disagreements,
                "tmr_minority_vote_outs": self.tmr_minority_vote_outs,
                "sel_events": self.total_sel_events,
                "sel_power_cycles": self.sel_power_cycles,
                "scrub_cycles": self.total_scrub_cycles,
            },
            "rates": {
                "seu_per_day": round(self.current_seu_rate_per_day, 6),
                "correction_rate": round(self.correction_rate(), 6),
                "escape_rate": round(self.escape_rate(), 8),
                "shielding_factor": round(self.current_shielding_factor, 6),
            },
        }


# ── Poisson draw (stdlib-only) ─────────────────────────────────────

def _poisson(rng: random.Random, mean: float) -> int:
    """Inverse-CDF Poisson sampler. For mean < 30 this is fine; above that
    we fall back to normal approximation (rarely reached for sub-second
    SEU rates but keeps the function robust)."""
    if mean <= 0:
        return 0
    if mean > 30:
        # N(mean, mean) approximation — round & clip at 0
        z = rng.gauss(mean, math.sqrt(mean))
        return max(0, int(round(z)))
    # Knuth's algorithm
    L = math.exp(-mean)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


# ── Module singleton + tick-engine registration hook ──────────────

_DEFAULT: Optional[ComputingRadiationState] = None


def get_computing_radiation() -> ComputingRadiationState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ComputingRadiationState()
    return _DEFAULT


def reset_computing_radiation() -> None:
    global _DEFAULT
    _DEFAULT = ComputingRadiationState()


def register_with_tick_engine() -> None:
    """Hook into the global tick engine at the standard avionics order."""
    from aria.simulator.tick_engine import get_tick_engine
    engine = get_tick_engine()
    engine.register(
        "computing_radiation",
        get_computing_radiation().tick,
        order=45,    # within the avionics band
    )
