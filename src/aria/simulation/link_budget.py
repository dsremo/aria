"""RF and optical link budget calculator.

Computes end-to-end communications link performance:
- Free-space path loss (Friis equation)
- Atmospheric attenuation (gaseous + rain)
- Antenna gain (dish size + efficiency)
- Received signal power
- System noise temperature
- C/N₀ and Eb/N₀ with FEC coding gain
- Data rate capability (Shannon-Hartley + BER margin)

Used for comm system sizing:
- Deep space missions (DSN compatibility check)
- Ground station passes (required antenna size)
- Laser comm feasibility
- Link margin analysis (rain fade budget for Ka-band)

References:
    Sklar (2001) "Digital Communications" Ch. 5-6
    Pratt et al. (2020) "Satellite Communications" 3rd ed.
    NASA DSN Telecom Link Design Handbook (810-005)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# Constants
_C_LIGHT = 299792458.0       # m/s
_K_BOLTZMANN = 1.380649e-23  # J/K
_AU_M = 1.495978707e11


# ══════════════════════════════════════════════════════════════════
#  Friis free-space path loss
# ══════════════════════════════════════════════════════════════════

def free_space_path_loss_db(range_m: float, frequency_hz: float) -> float:
    """Free-space path loss in dB.

    FSPL = 20 log₁₀(4π R f / c)

    Reference: Friis 1946 Proc. IRE 34:254.
    """
    if range_m <= 0 or frequency_hz <= 0:
        return float("inf")
    wavelength = _C_LIGHT / frequency_hz
    return 20 * math.log10(4 * math.pi * range_m / wavelength)


def parabolic_antenna_gain_db(
    diameter_m: float, frequency_hz: float, efficiency: float = 0.55,
) -> float:
    """Parabolic dish antenna gain.

    G = η × (π D / λ)²    [linear]
    G_dB = 10 log₁₀(η (πD/λ)²)

    Typical efficiency: 0.50-0.70.

    Reference: Balanis "Antenna Theory" 4th ed. §15.
    """
    if diameter_m <= 0 or frequency_hz <= 0:
        return -float("inf")
    wavelength = _C_LIGHT / frequency_hz
    gain_linear = efficiency * (math.pi * diameter_m / wavelength) ** 2
    return 10 * math.log10(gain_linear)


def antenna_beamwidth_deg(
    diameter_m: float, frequency_hz: float,
) -> float:
    """Half-power beamwidth of a parabolic dish.

    θ_HPBW ≈ 70 × λ/D [deg]

    Reference: Pratt et al. 2020 §2.5.
    """
    if diameter_m <= 0 or frequency_hz <= 0:
        return 360.0
    wavelength = _C_LIGHT / frequency_hz
    return 70.0 * wavelength / diameter_m


# ══════════════════════════════════════════════════════════════════
#  System noise temperature
# ══════════════════════════════════════════════════════════════════

def system_noise_temperature_k(
    antenna_temp_k: float = 100.0,     # sky + background
    lna_noise_temp_k: float = 50.0,    # low-noise amp
    line_loss_db: float = 0.5,         # waveguide loss
) -> float:
    """System noise temperature referred to antenna input.

    T_sys = T_ant + T_LNA × L  (where L = 10^(loss_dB/10))

    Reference: Pratt et al. 2020 §5.3.
    """
    line_loss_factor = 10 ** (line_loss_db / 10)
    return antenna_temp_k + lna_noise_temp_k * line_loss_factor


# ══════════════════════════════════════════════════════════════════
#  Link budget calculation
# ══════════════════════════════════════════════════════════════════

@dataclass
class LinkBudget:
    """RF link budget computation result."""
    range_km: float
    frequency_ghz: float
    tx_power_w: float
    tx_gain_db: float
    rx_gain_db: float
    path_loss_db: float
    atmospheric_loss_db: float
    pointing_loss_db: float
    eirp_dbw: float              # effective isotropic radiated power
    received_power_dbw: float
    c_over_n0_dbhz: float        # carrier to noise density
    snr_db: float                # for given bandwidth
    max_data_rate_mbps: float
    margin_db: float
    shannon_capacity_mbps: float


def compute_link_budget(
    range_m: float,
    frequency_hz: float,
    tx_power_w: float,
    tx_antenna_diameter_m: float,
    rx_antenna_diameter_m: float,
    tx_efficiency: float = 0.55,
    rx_efficiency: float = 0.65,
    atmospheric_loss_db: float = 0.5,
    pointing_loss_db: float = 0.5,
    required_eb_n0_db: float = 9.0,         # BPSK+convolutional ~9 dB
    bandwidth_hz: float = 1e6,
    antenna_temp_k: float = 100.0,
    lna_temp_k: float = 50.0,
) -> LinkBudget:
    """Compute full RF link budget.

    Args:
        range_m: distance between TX and RX [m]
        frequency_hz: carrier frequency [Hz]
        tx_power_w: transmitter output power [W]
        tx/rx_antenna_diameter_m: dish diameters
        *_efficiency: antenna efficiencies
        atmospheric_loss_db: rain/gas attenuation
        pointing_loss_db: antenna mispointing loss
        required_eb_n0_db: threshold for given modulation + FEC
        bandwidth_hz: receiver bandwidth
        antenna_temp_k, lna_temp_k: noise temperatures

    Returns:
        LinkBudget with all intermediate + final values

    Reference: NASA DSN 810-005.
    """
    # Antenna gains
    tx_gain = parabolic_antenna_gain_db(tx_antenna_diameter_m, frequency_hz, tx_efficiency)
    rx_gain = parabolic_antenna_gain_db(rx_antenna_diameter_m, frequency_hz, rx_efficiency)

    # EIRP
    eirp_dbw = 10 * math.log10(tx_power_w) + tx_gain

    # Path loss
    fspl = free_space_path_loss_db(range_m, frequency_hz)

    # Received power at RX antenna output
    rx_power_dbw = eirp_dbw - fspl - atmospheric_loss_db - pointing_loss_db + rx_gain

    # System noise temperature
    t_sys = system_noise_temperature_k(antenna_temp_k, lna_temp_k)
    n0_dbw_per_hz = 10 * math.log10(_K_BOLTZMANN * t_sys)  # dBW/Hz

    # C/N₀
    c_over_n0 = rx_power_dbw - n0_dbw_per_hz

    # SNR in given bandwidth
    noise_power_dbw = n0_dbw_per_hz + 10 * math.log10(bandwidth_hz)
    snr = rx_power_dbw - noise_power_dbw

    # Shannon capacity: C = B log₂(1 + SNR_linear)
    snr_linear = 10 ** (snr / 10)
    shannon_bps = bandwidth_hz * math.log2(1 + max(snr_linear, 0.01))

    # Data rate assuming Eb/N₀ = C/N₀ - 10log10(Rb)
    # → Rb_max = C/N₀ - Eb/N₀_required
    max_data_rate_db = c_over_n0 - required_eb_n0_db
    max_data_rate_bps = 10 ** (max_data_rate_db / 10)

    # Margin = achieved Eb/N₀ (at 1 Mbps) - required
    achieved_eb_n0_at_1mbps = c_over_n0 - 60  # 10log10(1e6)
    margin = achieved_eb_n0_at_1mbps - required_eb_n0_db

    return LinkBudget(
        range_km=range_m / 1000.0,
        frequency_ghz=frequency_hz / 1e9,
        tx_power_w=tx_power_w,
        tx_gain_db=tx_gain,
        rx_gain_db=rx_gain,
        path_loss_db=fspl,
        atmospheric_loss_db=atmospheric_loss_db,
        pointing_loss_db=pointing_loss_db,
        eirp_dbw=eirp_dbw,
        received_power_dbw=rx_power_dbw,
        c_over_n0_dbhz=c_over_n0,
        snr_db=snr,
        max_data_rate_mbps=max_data_rate_bps / 1e6,
        margin_db=margin,
        shannon_capacity_mbps=shannon_bps / 1e6,
    )


# ══════════════════════════════════════════════════════════════════
#  Standard link budget scenarios
# ══════════════════════════════════════════════════════════════════

def mars_to_earth_link(
    distance_au: float = 1.5,
    tx_power_w: float = 100.0,
    tx_dish_m: float = 4.0,
    rx_dish_m: float = 34.0,       # DSN 34m
    frequency_hz: float = 8.4e9,   # X-band
) -> LinkBudget:
    """Deep-space link: Mars orbiter to DSN 34m Earth station."""
    return compute_link_budget(
        range_m=distance_au * _AU_M,
        frequency_hz=frequency_hz,
        tx_power_w=tx_power_w,
        tx_antenna_diameter_m=tx_dish_m,
        rx_antenna_diameter_m=rx_dish_m,
        antenna_temp_k=30.0,       # DSN cold sky
        lna_temp_k=20.0,           # cryogenic LNA
        atmospheric_loss_db=0.2,   # clear X-band
        required_eb_n0_db=3.0,     # turbo-coded
    )


def leo_to_ground_link(
    altitude_km: float = 500.0,
    tx_power_w: float = 5.0,
    tx_dish_m: float = 0.3,        # patch or small dish
    rx_dish_m: float = 3.0,        # typical ground station
    frequency_hz: float = 2.4e9,   # S-band
) -> LinkBudget:
    """LEO satellite downlink to a ground station."""
    # Slant range at 10° elevation
    r_earth = 6378137.0
    r_sat = r_earth + altitude_km * 1000
    elev_rad = math.radians(10)
    slant = math.sqrt(r_sat ** 2 - r_earth ** 2 * math.cos(elev_rad) ** 2) - r_earth * math.sin(elev_rad)
    return compute_link_budget(
        range_m=slant,
        frequency_hz=frequency_hz,
        tx_power_w=tx_power_w,
        tx_antenna_diameter_m=tx_dish_m,
        rx_antenna_diameter_m=rx_dish_m,
        antenna_temp_k=150.0,
        lna_temp_k=100.0,
        atmospheric_loss_db=0.5,
    )
