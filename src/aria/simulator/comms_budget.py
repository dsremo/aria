"""Earth-link communications budget — light-time delay + bandwidth model.

As the ship moves away from Earth, two things happen:
  1. **Light-time delay** grows linearly with distance — at α Cen A
     (4.365 ly) one-way delay is ~4.4 yr. Each round-trip query takes
     8.7 yr.
  2. **Bandwidth drops with distance²** — Friis transmission equation
     gives received power proportional to 1/r² for a fixed transmit
     aperture. Modulation order steps down (BPSK at the limit).

Tracks an outbound-message queue: the operator drops a packet on the
queue, the model assigns it an ETA-Earth (= time + distance/c). A separate
queue holds inbound replies (currently empty until a backend system to
simulate Earth-side activity is added).

References
----------
  * NASA DSN 810-005 Telecom Design Handbook §3 (link budget)
  * Friis 1946 "A Note on a Simple Transmission Formula", Proc. IRE 34
  * Jet Propulsion Lab DSN ITU Recommendation SA.1014 — Ka-band 32 GHz uplink
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import get_phase_controller


# ── Physical constants + link parameters ───────────────────────────

C_M_PER_S: float = 299_792_458.0
LY_M:      float = 9.460730472580800e15
AU_M:      float = 1.495978707e11

# DSN Ka-band uplink baseline (NASA DSN 810-005 §3, generation-ship antenna):
TX_POWER_W:        float = 80_000.0      # 80 kW Ka-band transmit (parameters)
TX_ANTENNA_DIAM_M: float = 5.0           # 5 m comm dish (parameters)
RX_ANTENNA_DIAM_M: float = 70.0          # 70 m DSN ground antenna (Goldstone)
FREQ_HZ:           float = 32e9          # 32 GHz Ka-band (DSN allocation)
NOISE_TEMP_K:      float = 50.0          # ground-station system noise (DSN)
SHANNON_BW_HZ:     float = 50e6          # 50 MHz Ka allocation, ITU-R SA.1014

# Modulation order vs SNR thresholds (rough rules-of-thumb):
# (SNR_min_dB, name, useful_bits_per_symbol)
MODULATION_LADDER: List[tuple[float, str, int]] = [
    (-3.0, "BPSK + heavy LDPC",   1),
    (3.0,  "BPSK",                1),
    (8.0,  "QPSK",                2),
    (15.0, "8-PSK",               3),
    (20.0, "16-QAM",              4),
    (28.0, "64-QAM",              6),
]


@dataclass
class OutboundMessage:
    msg_id: str
    label: str
    bytes_size: int
    queued_at_yr: float
    eta_earth_yr: float       # mission-year when Earth receives it
    status: str = "queued"    # 'queued' / 'transmitting' / 'in_flight' / 'received'


@dataclass
class CommsBudgetState:
    """Earth-link comms model."""

    queue: List[OutboundMessage] = field(default_factory=list)
    next_msg_id: int = 1

    # Live computed
    distance_ly: float = 0.0
    one_way_delay_s: float = 0.0
    rx_power_w: float = 0.0
    snr_db: float = 0.0
    link_modulation: str = "—"
    achievable_bps: float = 0.0
    cumulative_bytes_tx: int = 0
    # One-shot gate for the bandwidth-cliff alert. Old code fired a
    # `comms.below_threshold` warning every tick while snr_db stayed
    # below the lowest modulation — a 100-yr Proxima coast spammed it
    # 989× (once per tick). Edge-trigger it instead: fire once when the
    # link first drops below threshold, re-arm only after a 2-dB
    # hysteresis (link recovered above threshold + 2 dB).
    _below_threshold_fired: bool = False

    # ── tick ────────────────────────────────────────────────────

    def tick(self, dt_s: float) -> None:
        bus = get_event_bus()
        phase = get_phase_controller()

        # Get current distance from trajectory_state
        try:
            from aria.simulator.trajectory_state import get_trajectory_state
            self.distance_ly = get_trajectory_state().position_ly
        except Exception:
            self.distance_ly = 0.0

        # BUG-034 (2026-04-24, walkthrough): operator saw
        # `DISTANCE FROM EARTH = 0.0000 ly` next to
        # `LIGHT DELAY (ONE-WAY) = 3.3 s` — contradictory.  The 1 Gm
        # floor was necessary for the Friis path-loss denominator but
        # shouldn't pollute the displayed one_way_delay_s.  Separate
        # the two: `distance_m_true` drives the delay (zero → zero s);
        # `distance_m_safe` is the floored value used only inside the
        # path-loss calc where a div-by-zero would blow up.
        distance_m_true = max(0.0, self.distance_ly * LY_M)
        self.one_way_delay_s = distance_m_true / C_M_PER_S

        distance_m_safe = max(1e9, distance_m_true)
        wavelength_m = C_M_PER_S / FREQ_HZ
        g_tx = (math.pi * TX_ANTENNA_DIAM_M / wavelength_m) ** 2
        g_rx = (math.pi * RX_ANTENNA_DIAM_M / wavelength_m) ** 2
        path_loss = (wavelength_m / (4 * math.pi * distance_m_safe)) ** 2
        self.rx_power_w = TX_POWER_W * g_tx * g_rx * path_loss

        # Noise power: kTB
        k_b = 1.380649e-23
        noise_w = k_b * NOISE_TEMP_K * SHANNON_BW_HZ
        snr_lin = self.rx_power_w / noise_w if noise_w > 0 else 0.0
        self.snr_db = 10 * math.log10(max(1e-30, snr_lin))

        # Pick best modulation that fits SNR
        best = MODULATION_LADDER[0]
        for entry in MODULATION_LADDER:
            if self.snr_db >= entry[0]:
                best = entry
        self.link_modulation = best[1]
        # Achievable bits/sec = min(modulation capacity, Shannon capacity).
        # Old code returned modulation capacity (bandwidth × bits-per-symbol)
        # even at SNR below the modulation's demodulation threshold, so a
        # Proxima-distance link at SNR=-59 dB was reported as 50 Mbps when
        # the Shannon limit is ~89 bps — a ~560 000× over-report that made
        # the comms panel worthless on deep-space legs. Gate on Shannon.
        mod_capacity_bps = SHANNON_BW_HZ * best[2]
        shannon_bps = SHANNON_BW_HZ * math.log2(max(1.0 + snr_lin, 1.0))
        self.achievable_bps = max(0.0, min(mod_capacity_bps, shannon_bps))

        # Process queue: any 'queued' message whose budget allows starts
        # transmitting; transmitting messages drain bytes_size / achievable_bps
        # seconds, then become in_flight; in_flight finish when sim time
        # reaches eta_earth_yr.
        for m in self.queue:
            if m.status == "queued" and self.achievable_bps > 0:
                tx_time_s = m.bytes_size * 8 / self.achievable_bps
                m.eta_earth_yr = phase.elapsed_yr + (tx_time_s + self.one_way_delay_s) / (365.25 * 24 * 3600)
                m.status = "in_flight"
                self.cumulative_bytes_tx += m.bytes_size
                bus.publish("comms.transmitted",
                            severity="info", source="comms_budget",
                            payload={"msg_id": m.msg_id, "bytes": m.bytes_size,
                                     "eta_earth_yr": round(m.eta_earth_yr, 4),
                                     "modulation": self.link_modulation},
                            sim_time_yr=phase.elapsed_yr)
            elif m.status == "in_flight" and phase.elapsed_yr >= m.eta_earth_yr:
                m.status = "received"
                bus.publish("comms.delivered",
                            severity="info", source="comms_budget",
                            payload={"msg_id": m.msg_id, "label": m.label},
                            sim_time_yr=phase.elapsed_yr)

        # Bandwidth-cliff alert: snr_db dropping below the lowest mod.
        # Edge-triggered with 2-dB hysteresis so a link hovering around
        # the threshold doesn't spam the bus every tick.
        threshold_db = MODULATION_LADDER[0][0]
        if (self.snr_db < threshold_db
                and self.distance_ly > 0.001
                and not self._below_threshold_fired):
            self._below_threshold_fired = True
            bus.publish("comms.below_threshold",
                        severity="warning", source="comms_budget",
                        payload={"snr_db": round(self.snr_db, 2),
                                 "distance_ly": round(self.distance_ly, 4)},
                        sim_time_yr=phase.elapsed_yr)
        elif self.snr_db >= threshold_db + 2.0 and self._below_threshold_fired:
            self._below_threshold_fired = False
            bus.publish("comms.recovered",
                        severity="info", source="comms_budget",
                        payload={"snr_db": round(self.snr_db, 2)},
                        sim_time_yr=phase.elapsed_yr)

    # ── operator API ───────────────────────────────────────────

    def queue_message(self, label: str, bytes_size: int) -> OutboundMessage:
        phase = get_phase_controller()
        msg = OutboundMessage(
            msg_id=f"msg_{self.next_msg_id:04d}",
            label=label,
            bytes_size=bytes_size,
            queued_at_yr=phase.elapsed_yr,
            eta_earth_yr=0.0,
        )
        self.next_msg_id += 1
        self.queue.append(msg)
        return msg

    def clear_received(self) -> int:
        before = len(self.queue)
        self.queue = [m for m in self.queue if m.status != "received"]
        return before - len(self.queue)

    # ── serialisation ──────────────────────────────────────────

    def to_dict(self) -> dict:
        delay_min = self.one_way_delay_s / 60.0
        delay_yr  = self.one_way_delay_s / (365.25 * 24 * 3600)
        return {
            "link": {
                "distance_ly":       round(self.distance_ly, 6),
                "one_way_delay_s":   round(self.one_way_delay_s, 1),
                "one_way_delay_min": round(delay_min, 3),
                "one_way_delay_yr":  round(delay_yr, 6),
                "rx_power_w":        f"{self.rx_power_w:.3e}",
                "snr_db":            round(self.snr_db, 2),
                "modulation":        self.link_modulation,
                "achievable_bps":    self.achievable_bps,
                "achievable_bps_human": _fmt_bps(self.achievable_bps),
            },
            "config": {
                "tx_power_w":        TX_POWER_W,
                "tx_antenna_diam_m": TX_ANTENNA_DIAM_M,
                "rx_antenna_diam_m": RX_ANTENNA_DIAM_M,
                "freq_hz":           FREQ_HZ,
                "shannon_bw_hz":     SHANNON_BW_HZ,
            },
            "queue": [
                {
                    "msg_id":      m.msg_id,
                    "label":       m.label,
                    "bytes_size":  m.bytes_size,
                    "queued_at_yr": round(m.queued_at_yr, 3),
                    "eta_earth_yr": round(m.eta_earth_yr, 4),
                    "status":      m.status,
                }
                for m in self.queue
            ],
            "stats": {
                "cumulative_bytes_tx": self.cumulative_bytes_tx,
                "queue_depth": len(self.queue),
            },
        }


def _fmt_bps(bps: float) -> str:
    if bps >= 1e9: return f"{bps/1e9:.2f} Gbps"
    if bps >= 1e6: return f"{bps/1e6:.2f} Mbps"
    if bps >= 1e3: return f"{bps/1e3:.2f} kbps"
    return f"{bps:.0f} bps"


_DEFAULT: Optional[CommsBudgetState] = None


def get_comms_budget() -> CommsBudgetState:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = CommsBudgetState()
    return _DEFAULT


def reset_comms_budget() -> None:
    global _DEFAULT
    _DEFAULT = CommsBudgetState()


def register_with_tick_engine() -> None:
    from aria.simulator.tick_engine import get_tick_engine
    get_tick_engine().register("comms_budget", get_comms_budget().tick, order=46)
