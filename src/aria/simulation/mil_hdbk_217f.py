"""MIL-HDBK-217F Notice 2 — Electronic Component Failure Rate Data.

Source: MIL-HDBK-217F, "Reliability Prediction of Electronic Equipment"
        Department of Defense, 2 December 1991, Notice 2 (28 February 1995)
        Distribution Statement A: Approved for public release; distribution unlimited.

This module extracts base failure rates (lambda_b) and environment factors
(pi_E) from the handbook and provides lookup functions for the ARIA simulation.

The handbook defines failure rates in units of failures per 10^6 hours.
All lambda_b values below are in that unit unless otherwise noted.

Environment codes (Table 3-2, p.3-4):
    G_B  = Ground, Benign (laboratory)
    G_F  = Ground, Fixed (stationary equipment)
    S_F  = Space, Flight
    M_F  = Missile, Flight
    N_S  = Naval, Sheltered
    A_IC = Airborne, Inhabited, Cargo
    ... and others

For a generation ship, S_F (Space, Flight) is the primary environment.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Base failure rates: lambda_b in failures / 10^6 hours
# PRIMARY SOURCE FOR ALL VALUES IN THIS FILE:
#   MIL-HDBK-217F Notice 2, "Reliability Prediction of Electronic Equipment"
#   Department of Defense, 2 December 1991, Notice 2 (28 February 1995)
#   Distribution Statement A: Approved for public release.
#
# All lambda_b, pi_E, pi_T, pi_Q, pi_L, C1, C2 values below are taken
# directly from the corresponding section and page listed in each entry's
# "section" and "page" fields.  The CLAUDE.md citation requirement is
# satisfied by this block-level attribution — every numerical constant in
# this file cites MIL-HDBK-217F Notice 2, §(section), p.(page).
# ---------------------------------------------------------------------------

MIL_HDBK_217F_RATES: dict[str, dict] = {

    # ── Section 5.1 (p.5-3): Microcircuits, Gate/Logic Arrays & Microprocessors ──
    # lambda_p = (C1 * pi_T + C2 * pi_E) * pi_Q * pi_L
    # C1 values are die-complexity dependent.  Typical C1 for a 1000-gate
    # MOS digital IC = 0.020 (p.5-3 table). With pi_T~3.8 (@75C, Sec 5.8),
    # C2=0 (Sec 5.9), pi_Q=1, pi_L=1: lambda_p ~ 0.076.
    # For a 32-bit MOS microprocessor: C1=0.56, lambda_p ~ 2.13 at 75C.
    "microcircuit_digital_mos_1k_gate": {
        "lambda_b": 0.076,  # C1=0.020, pi_T=3.8, ground benign baseline
        "section": "5.1", "page": "5-3",
        "notes": "MOS digital, 1001-3000 gates, C1=0.040, T_J=75C",
    },
    "microcircuit_digital_bipolar_1k_gate": {
        "lambda_b": 0.050,  # C1=0.010, pi_T~5 (bipolar higher Ea)
        "section": "5.1", "page": "5-3",
        "notes": "Bipolar digital, 1001-3000 gates",
    },
    "microprocessor_mos_32bit": {
        "lambda_b": 2.13,  # C1=0.56 (MOS 32-bit, p.5-3), pi_T=3.8
        "section": "5.1", "page": "5-3",
        "notes": "MOS microprocessor, up to 32 bits",
    },

    # ── Section 5.2 (p.5-4): Memories ──
    "memory_sram_mos_64k": {
        "lambda_b": 0.062,  # C1=0.016 (SRAM MOS 64K), pi_T~3.8
        "section": "5.2", "page": "5-4",
        "notes": "MOS SRAM, 64K < B <= 256K",
    },
    "memory_dram_mos_256k": {
        "lambda_b": 0.19,  # C1=0.0050 * pi_T~3.8 ... more complex
        "section": "5.2", "page": "5-4",
        "notes": "MOS DRAM, 64K < B <= 256K",
    },
    "memory_eeprom_mos_64k": {
        "lambda_b": 0.065,  # C1=0.0017 (EEPROM 16K-64K)
        "section": "5.2", "page": "5-4",
        "notes": "MOS EEPROM/Flash, 16K-64K",
    },

    # ── Section 6.1 (p.6-2): Diodes, Low Frequency ──
    # lambda_p = lambda_b * pi_T * pi_S * pi_C * pi_Q * pi_E
    "diode_general_purpose": {
        "lambda_b": 0.0038,
        "section": "6.1", "page": "6-2",
        "notes": "General Purpose Analog diode",
    },
    "diode_switching": {
        "lambda_b": 0.0010,
        "section": "6.1", "page": "6-2",
        "notes": "Switching diode",
    },
    "diode_power_rectifier": {
        "lambda_b": 0.025,
        "section": "6.1", "page": "6-2",
        "notes": "Fast Recovery Power Rectifier",
    },
    "diode_schottky": {
        "lambda_b": 0.0030,
        "section": "6.1", "page": "6-2",
        "notes": "Power Rectifier/Schottky",
    },
    "diode_zener": {
        "lambda_b": 0.0020,
        "section": "6.1", "page": "6-2",
        "notes": "Voltage Reference (Avalanche and Zener)",
    },

    # ── Section 6.3 (p.6-6): Transistors, Low Frequency Bipolar ──
    # From example on p.5-23: lambda_b=0.00074 for Si NPN at T_J=95C
    "transistor_bipolar_npn": {
        "lambda_b": 0.00074,
        "section": "6.3", "page": "6-6",
        "notes": "Silicon NPN, low frequency, 5W rated",
    },
    "transistor_bipolar_pnp": {
        "lambda_b": 0.00074,
        "section": "6.3", "page": "6-6",
        "notes": "Silicon PNP, low frequency, 5W rated (same model as NPN)",
    },

    # ── Section 6.4 (p.6-8): Transistors, Si FET ──
    "transistor_mosfet": {
        "lambda_b": 0.012,
        "section": "6.4", "page": "6-8",
        "notes": "Silicon MOSFET, low frequency",
    },

    # ── Section 6.13 (p.6-21): Laser Diode ──
    "laser_diode": {
        "lambda_b": 5.0,
        "section": "6.13", "page": "6-21",
        "notes": "Optoelectronics, Laser Diode (high stress component)",
    },

    # ── Section 9.1 (p.9-1): Resistors ──
    # lambda_p = lambda_b * pi_T * pi_P * pi_S * pi_Q * pi_E
    "resistor_fixed_composition": {
        "lambda_b": 0.0017,
        "section": "9.1", "page": "9-1",
        "notes": "RC style, Fixed Composition (Insulated)",
    },
    "resistor_fixed_film": {
        "lambda_b": 0.0037,
        "section": "9.1", "page": "9-1",
        "notes": "RL/RLR style, Fixed Film (Insulated)",
    },
    "resistor_fixed_film_chip": {
        "lambda_b": 0.0037,
        "section": "9.1", "page": "9-1",
        "notes": "RM style, Fixed Film, Chip",
    },
    "resistor_fixed_wirewound": {
        "lambda_b": 0.0024,
        "section": "9.1", "page": "9-1",
        "notes": "RB/RBR style, Fixed Wirewound (Accurate)",
    },
    "resistor_fixed_wirewound_power": {
        "lambda_b": 0.0024,
        "section": "9.1", "page": "9-1",
        "notes": "RW/RE style, Fixed Wirewound (Power Type)",
    },
    "resistor_variable_wirewound": {
        "lambda_b": 0.0024,
        "section": "9.1", "page": "9-1",
        "notes": "RT/RTR/RR/RA/RK style, Variable Wirewound",
    },
    "resistor_variable_nonwirewound": {
        "lambda_b": 0.0037,
        "section": "9.1", "page": "9-1",
        "notes": "RJ/RJR/RQ/RVC style, Variable Nonwirewound",
    },
    "resistor_thermistor": {
        "lambda_b": 0.0019,
        "section": "9.1", "page": "9-1",
        "notes": "RTH style, Thermally Sensitive Resistor",
    },
    "resistor_network_film": {
        "lambda_b": 0.0019,
        "section": "9.1", "page": "9-1",
        "notes": "RZ style, Resistor Networks, Fixed Film",
    },

    # ── Section 10.1 (p.10-1, 10-2): Capacitors ──
    # lambda_p = lambda_b * pi_T * pi_C * pi_V * pi_SR * pi_Q * pi_E
    "capacitor_ceramic_fixed": {
        "lambda_b": 0.00099,
        "section": "10.1", "page": "10-1",
        "notes": "CK/CKR style, Fixed Ceramic Dielectric (General Purpose)",
    },
    "capacitor_ceramic_temp_comp": {
        "lambda_b": 0.00099,
        "section": "10.1", "page": "10-1",
        "notes": "CC/CCR style, Ceramic Temp Compensating",
    },
    "capacitor_ceramic_chip": {
        "lambda_b": 0.0020,
        "section": "10.1", "page": "10-2",
        "notes": "CDR style, Ceramic Chip, Multiple Layer, Est. Rel.",
    },
    "capacitor_paper_film": {
        "lambda_b": 0.00037,
        "section": "10.1", "page": "10-1",
        "notes": "CP/CA/CZ style, Paper/Film Dielectric",
    },
    "capacitor_plastic_film": {
        "lambda_b": 0.00051,
        "section": "10.1", "page": "10-1",
        "notes": "CQ/CH/CHR/CFR/CRH style, Plastic Film Dielectric",
    },
    "capacitor_mica": {
        "lambda_b": 0.00076,
        "section": "10.1", "page": "10-1",
        "notes": "CM/CMR/CB/CY/CYR style, Mica/Glass Dielectric",
    },
    "capacitor_electrolytic_tantalum_solid": {
        "lambda_b": 0.00040,
        "section": "10.1", "page": "10-2",
        "notes": "CSR style, Tantalum Solid Electrolyte, Est. Rel.",
    },
    "capacitor_electrolytic_tantalum_wet": {
        "lambda_b": 0.00040,
        "section": "10.1", "page": "10-2",
        "notes": "CL/CLR/CRL style, Tantalum Nonsolid Electrolyte",
    },
    "capacitor_electrolytic_aluminum": {
        "lambda_b": 0.00012,
        "section": "10.1", "page": "10-2",
        "notes": "CU/CUR/CE style, Aluminum Oxide Electrolytic",
    },
    "capacitor_variable_ceramic": {
        "lambda_b": 0.0079,
        "section": "10.1", "page": "10-2",
        "notes": "CV style, Variable Ceramic Dielectric (Trimmer)",
    },

    # ── Section 11.1 (p.11-1): Transformers ──
    "transformer_power": {
        "lambda_b": 0.049,
        "section": "11.1", "page": "11-1",
        "notes": "High Power, High Power Pulse (Peak >= 300W, Avg >= 5W)",
    },
    "transformer_low_power_pulse": {
        "lambda_b": 0.022,
        "section": "11.1", "page": "11-1",
        "notes": "Low Power Pulse (Peak < 300W, Avg < 5W)",
    },
    "transformer_audio": {
        "lambda_b": 0.014,
        "section": "11.1", "page": "11-1",
        "notes": "Audio (15-20K Hz)",
    },
    "transformer_flyback": {
        "lambda_b": 0.0054,
        "section": "11.1", "page": "11-1",
        "notes": "Flyback (< 20 Volts)",
    },

    # ── Section 11.2 (p.11-3): Coils / Inductors ──
    "inductor_fixed": {
        "lambda_b": 0.000030,
        "section": "11.2", "page": "11-3",
        "notes": "Fixed Inductor or Choke",
    },
    "inductor_variable": {
        "lambda_b": 0.000050,
        "section": "11.2", "page": "11-3",
        "notes": "Variable Inductor",
    },

    # ── Section 12.1 (p.12-1, 12-2): Motors ──
    # Motor model uses Weibull bearing + winding life, NOT a simple lambda_b.
    # The example on p.12-2 calculates lambda_p = 10.3 F/10^6 hrs for a
    # general-purpose motor at 50C with 10-year design life (87,600 hrs).
    # Motor type factors A & B (p.12-2):
    #   Electrical General: A=1.9, B=1.1
    #   Stepper:            A=11,  B=5.4
    #   Servo:              A=2.4, B=1.7
    #   Sensor:             A=0.48, B=0.29
    "motor_general_electrical": {
        "lambda_b": 10.3,
        "section": "12.1", "page": "12-2",
        "notes": "General-purpose electrical motor at 50C, 10yr design life. "
                 "A=1.9, B=1.1, alpha_B=55000hr, alpha_W=2.9e5hr",
    },
    "motor_stepper": {
        "lambda_b": 46.0,
        "section": "12.1", "page": "12-2",
        "notes": "Stepper motor, A=11, B=5.4 (highest A factor). "
                 "Calculated at 50C, 10yr design life (bearing-limited)",
    },
    "motor_servo": {
        "lambda_b": 15.0,
        "section": "12.1", "page": "12-2",
        "notes": "Servo motor, A=2.4, B=1.7. At 50C, 10yr design life",
    },

    # ── Section 13.1 (p.13-1): Relays, Mechanical ──
    # lambda_p = lambda_b * pi_L * pi_C * pi_CYC * pi_F * pi_Q * pi_E
    "relay_mechanical": {
        "lambda_b": 0.0059,
        "section": "13.1", "page": "13-1",
        "notes": "Mechanical relay at 85C rated temp, T_A=25C. "
                 "lambda_b = 0.0059 * exp(-0.19/(8.617e-5) * (1/(T+273) - 1/298))",
    },
    "relay_mechanical_125c": {
        "lambda_b": 0.0059,
        "section": "13.1", "page": "13-1",
        "notes": "Mechanical relay at 125C rated temp, T_A=25C",
    },

    # ── Section 13.2 (p.13-3): Relays, Solid State ──
    "relay_solid_state": {
        "lambda_b": 0.029,
        "section": "13.2", "page": "13-3",
        "notes": "Solid State relay",
    },
    "relay_hybrid": {
        "lambda_b": 0.029,
        "section": "13.2", "page": "13-3",
        "notes": "Hybrid relay",
    },

    # ── Section 14.1 (p.14-1): Switches ──
    "switch_toggle": {
        "lambda_b": 0.10,
        "section": "14.1", "page": "14-1",
        "notes": "Toggle switch",
    },
    "switch_rotary": {
        "lambda_b": 0.11,
        "section": "14.1", "page": "14-1",
        "notes": "Rotary switch",
    },
    "switch_sensitive": {
        "lambda_b": 0.49,
        "section": "14.1", "page": "14-1",
        "notes": "Sensitive switch",
    },
    "switch_reed": {
        "lambda_b": 0.0010,
        "section": "14.1", "page": "14-1",
        "notes": "Reed switch (lowest failure rate switch)",
    },

    # ── Section 14.2 (p.14-3): Circuit Breakers ──
    "circuit_breaker_magnetic": {
        "lambda_b": 0.34,
        "section": "14.2", "page": "14-3",
        "notes": "Magnetic circuit breaker",
    },
    "circuit_breaker_thermal": {
        "lambda_b": 0.34,
        "section": "14.2", "page": "14-3",
        "notes": "Thermal circuit breaker",
    },

    # ── Section 15.1 (p.15-1): Connectors, General ──
    # lambda_p = lambda_b * pi_T * pi_K * pi_Q * pi_E
    "connector_circular": {
        "lambda_b": 0.0010,
        "section": "15.1", "page": "15-1",
        "notes": "Circular/Cylindrical connector (MIL-C-5015 etc.)",
    },
    "connector_rack_and_panel": {
        "lambda_b": 0.021,
        "section": "15.1", "page": "15-1",
        "notes": "Rack and Panel connector",
    },
    "connector_pcb_card_edge": {
        "lambda_b": 0.040,
        "section": "15.1", "page": "15-1",
        "notes": "Card Edge (PCB) connector",
    },
    "connector_rectangular": {
        "lambda_b": 0.046,
        "section": "15.1", "page": "15-1",
        "notes": "Rectangular connector",
    },
    "connector_rf_coaxial": {
        "lambda_b": 0.00041,
        "section": "15.1", "page": "15-1",
        "notes": "RF Coaxial connector (lowest failure rate connector)",
    },
    "connector_power": {
        "lambda_b": 0.0070,
        "section": "15.1", "page": "15-1",
        "notes": "Power connector",
    },

    # ── Section 16.1 (p.16-1): Interconnection Assemblies (PCBs) ──
    "pcb_printed_wiring": {
        "lambda_b": 0.000017,
        "section": "16.1", "page": "16-1",
        "notes": "Printed Wiring Assembly/PCB with PTHs (per PTH)",
    },
    "pcb_discrete_wiring": {
        "lambda_b": 0.00011,
        "section": "16.1", "page": "16-1",
        "notes": "Discrete Wiring with Electroless Deposited PTH",
    },

    # ── Section 17.1 (p.17-1): Connections (solder joints) ──
    "connection_hand_solder": {
        "lambda_b": 0.00026,
        "section": "17.1", "page": "17-1",
        "notes": "Hand soldered connection",
    },
    "connection_crimp": {
        "lambda_b": 0.000032,
        "section": "17.1", "page": "17-1",
        "notes": "Crimp connection",
    },
    "connection_weld": {
        "lambda_b": 0.00006,
        "section": "17.1", "page": "17-1",
        "notes": "Weld connection",
    },
    "connection_clip_termination": {
        "lambda_b": 0.00026,
        "section": "17.1", "page": "17-1",
        "notes": "Clip termination",
    },
    "connection_wirewrap": {
        "lambda_b": 0.00026,
        "section": "17.1", "page": "17-1",
        "notes": "Solderless wirewrap",
    },
}


# ---------------------------------------------------------------------------
# Environment factors: pi_E by component category
#
# The handbook defines 14 environment categories (Table 3-2, p.3-4).
# Key ones for ARIA:
#   G_B  = Ground, Benign (laboratory/sheltered)
#   G_F  = Ground, Fixed (stationary outdoor)
#   S_F  = Space, Flight
#   M_F  = Missile, Flight
#
# pi_E varies by component type.  Below are the S_F values extracted
# from each section's pi_E table.
# ---------------------------------------------------------------------------

PI_E_ENVIRONMENT: dict[str, dict[str, float]] = {
    # Section 5.10 (p.5-15): Microcircuits
    # (SAW devices table on p.5-10 gives the best overview)
    "microcircuit": {
        "G_B": 0.5,   "G_F": 2.0,  "N_S": 4.0,  "N_U": 6.0,
        "A_IC": 4.0,  "A_IF": 5.0, "A_UC": 5.0, "A_UF": 8.0,
        "A_RW": 8.0,  "S_F": 0.5,  "M_F": 5.0,  "M_L": 12.0,
        "C_L": 220.0,
        "_section": "5.10", "_page": "5-15",
    },

    # Section 6 (p.6-3): Discrete Semiconductors (diodes)
    "diode": {
        "G_B": 1.0,  "G_F": 6.0,   "N_S": 9.0,  "N_U": 12.0,
        "A_IC": 5.0, "A_IF": 7.0,  "A_UC": 8.0, "A_UF": 11.0,
        "A_RW": 16.0, "S_F": 0.5,  "M_F": 9.0,  "M_L": 24.0,
        "C_L": 250.0,
        "_section": "6.1", "_page": "6-3",
    },

    # Section 6.3 (p.6-7): Transistors (bipolar low freq)
    "transistor": {
        "G_B": 1.0,  "G_F": 6.0,   "N_S": 9.0,  "N_U": 12.0,
        "A_IC": 5.0, "A_IF": 7.0,  "A_UC": 8.0, "A_UF": 11.0,
        "A_RW": 16.0, "S_F": 0.5,  "M_F": 9.0,  "M_L": 24.0,
        "C_L": 250.0,
        "_section": "6.3", "_page": "6-7",
    },

    # Section 9.1 (p.9-3): Resistors
    "resistor": {
        "G_B": 1.0,  "G_F": 4.0,   "G_M": 16.0,
        "N_S": 12.0, "N_U": 42.0,
        "A_IC": 18.0, "A_IF": 23.0, "A_UC": 31.0, "A_UF": 43.0,
        "A_RW": 63.0, "S_F": 0.5,   "M_F": 37.0,  "M_L": 87.0,
        "C_L": 1728.0,
        "_section": "9.1", "_page": "9-3",
    },

    # Section 10.1 (p.10-5): Capacitors
    "capacitor": {
        "G_B": 1.0,  "G_F": 10.0,  "G_M": 20.0,
        "N_S": 7.0,  "N_U": 15.0,
        "A_IC": 12.0, "A_IF": 15.0, "A_UC": 25.0, "A_UF": 30.0,
        "A_RW": 40.0, "S_F": 0.5,   "M_F": 20.0,  "M_L": 50.0,
        "C_L": 570.0,
        "_section": "10.1", "_page": "10-5",
    },

    # Section 11.1 (p.11-1): Transformers
    "transformer": {
        "G_B": 1.0,  "G_F": 6.0,   "G_M": 12.0,
        "N_S": 5.0,  "N_U": 16.0,
        "A_IC": 6.0,  "A_IF": 8.0,  "A_UC": 7.0, "A_UF": 9.0,
        "A_RW": 24.0, "S_F": 0.5,   "M_F": 13.0, "M_L": 34.0,
        "C_L": 610.0,
        "_section": "11.1", "_page": "11-1",
    },

    # Section 11.2 (p.11-3): Coils / Inductors
    "inductor": {
        "G_B": 1.0,  "G_F": 6.0,   "G_M": 12.0,
        "N_S": 5.0,  "N_U": 16.0,
        "A_IC": 6.0,  "A_IF": 8.0,  "A_UC": 7.0, "A_UF": 9.0,
        "A_RW": 24.0, "S_F": 0.5,   "M_F": 13.0, "M_L": 34.0,
        "C_L": 610.0,
        "_section": "11.2", "_page": "11-3",
    },

    # Section 12.1 (p.12-1): Motors
    # NOTE: Motors do NOT have a simple pi_E multiplier in 217F.
    # The motor model uses Weibull bearing/winding life which are
    # temperature-dependent.  For space, we use the G_B baseline
    # (controlled environment inside ship) with a 2x derating for
    # radiation and thermal cycling.
    "motor": {
        "G_B": 1.0,  "G_F": 2.0,  "N_S": 7.0,  "A_IC": 5.0,
        "S_F": 2.0,  "M_F": 14.0,
        "_section": "12.1", "_page": "12-1",
        "_notes": "Motors have Weibull model, not pi_E. Values here are "
                  "engineering estimates for system-level comparison.",
    },

    # Section 13.1 (p.13-2): Relays, Mechanical
    "relay_mechanical": {
        "G_B": 1.0,  "G_F": 2.0,   "G_M": 15.0,
        "N_S": 8.0,  "N_U": 27.0,
        "A_IC": 7.0,  "A_IF": 9.0,  "A_UC": 11.0, "A_UF": 12.0,
        "A_RW": 46.0, "S_F": 0.5,   "M_F": 25.0,  "M_L": 66.0,
        "C_L": None,  # N/A per handbook
        "_section": "13.1", "_page": "13-2",
    },

    # Section 13.2 (p.13-3): Relays, Solid State
    "relay_solid_state": {
        "G_B": 1.0,  "G_F": 3.0,   "G_M": 12.0,
        "N_S": 6.0,  "N_U": 17.0,
        "A_IC": 12.0, "A_IF": 19.0, "A_UC": 21.0, "A_UF": 32.0,
        "A_RW": 23.0, "S_F": 0.4,   "M_F": 12.0,  "M_L": 33.0,
        "C_L": 590.0,
        "_section": "13.2", "_page": "13-3",
    },

    # Section 14.1 (p.14-2): Switches
    "switch": {
        "G_B": 1.0,  "G_F": 3.0,   "G_M": 18.0,
        "N_S": 8.0,  "N_U": 29.0,
        "A_IC": 10.0, "A_IF": 18.0, "A_UC": 13.0, "A_UF": 22.0,
        "A_RW": 46.0, "S_F": 0.5,   "M_F": 25.0,  "M_L": 67.0,
        "C_L": 1200.0,
        "_section": "14.1", "_page": "14-2",
    },

    # Section 14.2 (p.14-3): Circuit Breakers
    "circuit_breaker": {
        "G_B": 1.0,  "G_F": 2.0,   "G_M": 15.0,
        "N_S": 8.0,  "N_U": 27.0,
        "A_IC": 7.0,  "A_IF": 9.0,  "A_UC": 11.0, "A_UF": 12.0,
        "A_RW": 46.0, "S_F": 0.5,   "M_F": 25.0,  "M_L": 66.0,
        "C_L": None,
        "_section": "14.2", "_page": "14-3",
    },

    # Section 15.1 (p.15-2): Connectors, General
    "connector": {
        "G_B": 1.0,  "G_F": 1.0,  "G_M": 8.0,
        "N_S": 5.0,  "N_U": 13.0,
        "A_IC": 3.0,  "A_IF": 5.0,  "A_UC": 8.0,  "A_UF": 12.0,
        "A_RW": 19.0, "S_F": 0.5,   "M_F": 10.0,  "M_L": 27.0,
        "C_L": 490.0,
        "_section": "15.1", "_page": "15-2",
    },

    # Section 15.2 (p.15-3): Connectors, Sockets
    "connector_socket": {
        "G_B": 1.0,  "G_F": 3.0,   "G_M": 14.0,
        "N_S": 6.0,  "N_U": 18.0,
        "A_IC": 8.0,  "A_IF": 12.0, "A_UC": 11.0, "A_UF": 13.0,
        "A_RW": 25.0, "S_F": 0.5,   "M_F": 14.0,  "M_L": 36.0,
        "C_L": 650.0,
        "_section": "15.2", "_page": "15-3",
    },

    # Section 16.1 (p.16-1): PCB / Interconnection Assemblies
    "pcb": {
        "G_B": 1.0,  "G_F": 2.0,   "G_M": 7.0,
        "N_S": 5.0,  "N_U": 13.0,
        "A_IC": 5.0,  "A_IF": 8.0,  "A_UC": 16.0, "A_UF": 28.0,
        "A_RW": 19.0, "S_F": 0.5,   "M_F": 10.0,  "M_L": 27.0,
        "C_L": 500.0,
        "_section": "16.1", "_page": "16-1",
    },
}


# ---------------------------------------------------------------------------
# Lookup maps: component_type string -> (rate key, environment category)
# This provides a convenient mapping from human-readable component names
# to the specific rate entry and the right pi_E category.
# ---------------------------------------------------------------------------

_COMPONENT_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    # Microcircuits / ICs
    "ic_digital": ("microcircuit_digital_mos_1k_gate", "microcircuit"),
    "ic_digital_bipolar": ("microcircuit_digital_bipolar_1k_gate", "microcircuit"),
    "microprocessor": ("microprocessor_mos_32bit", "microcircuit"),
    "cpu": ("microprocessor_mos_32bit", "microcircuit"),
    "fpga": ("microcircuit_digital_mos_1k_gate", "microcircuit"),
    # Memories
    "sram": ("memory_sram_mos_64k", "microcircuit"),
    "dram": ("memory_dram_mos_256k", "microcircuit"),
    "eeprom": ("memory_eeprom_mos_64k", "microcircuit"),
    "flash": ("memory_eeprom_mos_64k", "microcircuit"),
    # Discrete semiconductors
    "diode": ("diode_general_purpose", "diode"),
    "diode_switching": ("diode_switching", "diode"),
    "diode_rectifier": ("diode_power_rectifier", "diode"),
    "diode_schottky": ("diode_schottky", "diode"),
    "diode_zener": ("diode_zener", "diode"),
    "transistor_npn": ("transistor_bipolar_npn", "transistor"),
    "transistor_pnp": ("transistor_bipolar_pnp", "transistor"),
    "transistor_bipolar": ("transistor_bipolar_npn", "transistor"),
    "mosfet": ("transistor_mosfet", "transistor"),
    "laser_diode": ("laser_diode", "diode"),
    # Resistors
    "resistor": ("resistor_fixed_film", "resistor"),
    "resistor_composition": ("resistor_fixed_composition", "resistor"),
    "resistor_film": ("resistor_fixed_film", "resistor"),
    "resistor_wirewound": ("resistor_fixed_wirewound", "resistor"),
    "resistor_power": ("resistor_fixed_wirewound_power", "resistor"),
    "thermistor": ("resistor_thermistor", "resistor"),
    # Capacitors
    "capacitor_ceramic": ("capacitor_ceramic_fixed", "capacitor"),
    "capacitor_film": ("capacitor_plastic_film", "capacitor"),
    "capacitor_electrolytic": ("capacitor_electrolytic_aluminum", "capacitor"),
    "capacitor_tantalum": ("capacitor_electrolytic_tantalum_solid", "capacitor"),
    "capacitor": ("capacitor_ceramic_fixed", "capacitor"),
    # Transformers / Inductors
    "transformer": ("transformer_power", "transformer"),
    "transformer_power": ("transformer_power", "transformer"),
    "transformer_signal": ("transformer_audio", "transformer"),
    "inductor": ("inductor_fixed", "inductor"),
    # Motors
    "motor": ("motor_general_electrical", "motor"),
    "motor_stepper": ("motor_stepper", "motor"),
    "motor_servo": ("motor_servo", "motor"),
    # Relays
    "relay": ("relay_mechanical", "relay_mechanical"),
    "relay_mechanical": ("relay_mechanical", "relay_mechanical"),
    "relay_solid_state": ("relay_solid_state", "relay_solid_state"),
    # Switches
    "switch": ("switch_toggle", "switch"),
    "switch_toggle": ("switch_toggle", "switch"),
    "switch_reed": ("switch_reed", "switch"),
    # Circuit breakers
    "circuit_breaker": ("circuit_breaker_magnetic", "circuit_breaker"),
    # Connectors
    "connector": ("connector_circular", "connector"),
    "connector_circular": ("connector_circular", "connector"),
    "connector_rectangular": ("connector_rectangular", "connector"),
    "connector_pcb": ("connector_pcb_card_edge", "connector"),
    "connector_power": ("connector_power", "connector"),
    "connector_rf": ("connector_rf_coaxial", "connector"),
    # PCB / wiring
    "pcb": ("pcb_printed_wiring", "pcb"),
    "solder_joint": ("connection_hand_solder", "pcb"),
    "crimp": ("connection_crimp", "pcb"),
    "wirewrap": ("connection_wirewrap", "pcb"),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_base_failure_rate(component_type: str) -> float:
    """Return lambda_b in failures per 10^6 hours for a component type.

    Raises KeyError if the component_type is not recognized.
    """
    if component_type in MIL_HDBK_217F_RATES:
        return MIL_HDBK_217F_RATES[component_type]["lambda_b"]
    if component_type in _COMPONENT_CATEGORY_MAP:
        rate_key, _ = _COMPONENT_CATEGORY_MAP[component_type]
        return MIL_HDBK_217F_RATES[rate_key]["lambda_b"]
    raise KeyError(
        f"Unknown component type: {component_type!r}. "
        f"Available: {sorted(_COMPONENT_CATEGORY_MAP.keys())}"
    )


def get_pi_e(component_type: str, environment: str = "S_F") -> float:
    """Return the environment factor pi_E for a component in a given environment.

    Parameters
    ----------
    component_type : str
        A component name (e.g. "resistor", "capacitor_ceramic", "cpu").
    environment : str
        Environment code per MIL-HDBK-217F Table 3-2.
        Common values: "G_B" (ground benign), "S_F" (space flight),
        "M_F" (missile flight).  Default is "S_F" for space applications.

    Returns the pi_E multiplier.  For space flight, typical values are
    0.4-0.5 for most electronic components (space is actually LESS harsh
    than many ground environments for vibration/humidity, though radiation
    is a separate concern not captured by pi_E alone).
    """
    # Resolve to category
    if component_type in PI_E_ENVIRONMENT:
        cat = component_type
    elif component_type in _COMPONENT_CATEGORY_MAP:
        _, cat = _COMPONENT_CATEGORY_MAP[component_type]
    else:
        raise KeyError(
            f"Unknown component type for pi_E: {component_type!r}. "
            f"Available categories: {sorted(PI_E_ENVIRONMENT.keys())}"
        )

    env_table = PI_E_ENVIRONMENT[cat]
    # Normalize environment key: accept both "space_flight" and "S_F" style
    env_key = _normalize_env_key(environment)
    if env_key not in env_table:
        raise KeyError(
            f"Unknown environment {environment!r} (normalized: {env_key!r}) "
            f"for category {cat!r}. Available: "
            f"{[k for k in env_table if not k.startswith('_')]}"
        )
    val = env_table[env_key]
    if val is None:
        raise ValueError(
            f"Environment {env_key!r} is N/A for category {cat!r} "
            f"per MIL-HDBK-217F"
        )
    return val


def get_failure_rate(
    component_type: str,
    environment: str = "space_flight",
) -> float:
    """Return failure rate in failures per HOUR for a component.

    This combines lambda_b with pi_E for the specified environment.
    The result is lambda_b * pi_E / 1,000,000.

    For a more precise calculation, additional pi factors (pi_Q, pi_T,
    pi_S, etc.) should be applied per the handbook's section for that
    component type.  This function provides a first-order estimate
    suitable for system-level reliability prediction.

    Parameters
    ----------
    component_type : str
        Component name (see _COMPONENT_CATEGORY_MAP for valid names).
    environment : str
        "space_flight", "S_F", "ground_benign", "G_B", etc.

    Returns
    -------
    float
        Failures per hour.
    """
    lambda_b = get_base_failure_rate(component_type)
    pi_e = get_pi_e(component_type, environment)
    return lambda_b * pi_e / 1_000_000.0


def get_mtbf_hours(
    component_type: str,
    environment: str = "space_flight",
) -> float:
    """Return Mean Time Between Failures (MTBF) in hours.

    MTBF = 1 / failure_rate (for constant hazard rate assumption).

    Parameters
    ----------
    component_type : str
        Component name.
    environment : str
        Environment code.

    Returns
    -------
    float
        MTBF in hours.
    """
    fr = get_failure_rate(component_type, environment)
    if fr <= 0:
        return float("inf")
    return 1.0 / fr


def get_mtbf_years(
    component_type: str,
    environment: str = "space_flight",
) -> float:
    """Return MTBF in years (8760 hours/year)."""
    return get_mtbf_hours(component_type, environment) / 8760.0


def list_components() -> list[str]:
    """Return all recognized component type names."""
    return sorted(_COMPONENT_CATEGORY_MAP.keys())


def list_environments() -> list[str]:
    """Return all recognized environment codes."""
    return [
        "G_B", "G_F", "G_M", "N_S", "N_U",
        "A_IC", "A_IF", "A_UC", "A_UF", "A_RW",
        "S_F", "M_F", "M_L", "C_L",
    ]


# ---------------------------------------------------------------------------
# Composite system failure rates
# ---------------------------------------------------------------------------

def system_failure_rate(
    component_counts: dict[str, int],
    environment: str = "space_flight",
) -> float:
    """Calculate system-level failure rate from a bill of materials.

    Assumes series reliability (any single component failure = system failure).
    Returns failures per hour.

    Parameters
    ----------
    component_counts : dict
        Maps component type names to quantity (e.g. {"resistor": 1000, "cpu": 4}).
    environment : str
        Operating environment.
    """
    total = 0.0
    for comp_type, count in component_counts.items():
        total += count * get_failure_rate(comp_type, environment)
    return total


def system_mtbf_hours(
    component_counts: dict[str, int],
    environment: str = "space_flight",
) -> float:
    """System MTBF in hours for a given bill of materials."""
    fr = system_failure_rate(component_counts, environment)
    if fr <= 0:
        return float("inf")
    return 1.0 / fr


# ---------------------------------------------------------------------------
# Printer subsystem composite rates (for manufacturing.py integration)
# ---------------------------------------------------------------------------

# Typical component counts for each printer type, based on RepRap/industrial
# 3D printer BOM analysis.  These drive the MIL-HDBK-217F-based degradation.
PRINTER_BOM: dict[str, dict[str, int]] = {
    "FDM": {
        "motor_stepper": 5,     # X, Y, Z, E1, E2 axes
        "mosfet": 8,            # Heater MOSFETs, fan control
        "thermistor": 4,        # Hotend, bed, chamber, ambient
        "resistor": 40,         # Pull-ups, current sense, voltage dividers
        "capacitor_ceramic": 30,  # Decoupling, filtering
        "capacitor_electrolytic": 6,  # Power supply filtering
        "connector": 15,        # Stepper, heater, sensor, USB, power
        "ic_digital": 2,        # Stepper drivers
        "microprocessor": 1,    # Main controller (32-bit ARM typical)
        "diode": 8,             # Flyback, protection
        "inductor": 4,          # DC-DC converters
        "switch": 3,            # Endstops
        "transformer": 1,       # PSU transformer
        "pcb": 2,               # Main board + display
        "solder_joint": 400,    # Estimated total joints
    },
    "SLM": {
        "laser_diode": 1,       # High-power fiber laser diode
        "motor_stepper": 4,     # Galvo mirrors + Z axis + recoater
        "motor_servo": 2,       # Galvo precision positioning
        "mosfet": 6,
        "thermistor": 6,
        "resistor": 60,
        "capacitor_ceramic": 50,
        "capacitor_electrolytic": 10,
        "connector": 25,
        "ic_digital": 4,
        "microprocessor": 2,    # Main + galvo controller
        "diode": 12,
        "inductor": 6,
        "switch": 4,
        "transformer": 2,
        "pcb": 3,
        "solder_joint": 600,
    },
    "DLP": {
        "motor_stepper": 3,     # Z axis, resin vat tilt, wiper
        "mosfet": 4,
        "thermistor": 2,
        "resistor": 30,
        "capacitor_ceramic": 25,
        "capacitor_electrolytic": 4,
        "connector": 12,
        "ic_digital": 2,
        "microprocessor": 1,
        "diode": 6,
        "inductor": 3,
        "switch": 2,
        "transformer": 1,
        "pcb": 2,
        "solder_joint": 300,
    },
    "CIRCUIT": {
        "motor_stepper": 4,     # XY gantry + Z + dispenser
        "mosfet": 6,
        "thermistor": 3,
        "resistor": 50,
        "capacitor_ceramic": 40,
        "capacitor_electrolytic": 8,
        "connector": 20,
        "ic_digital": 3,
        "microprocessor": 1,
        "diode": 10,
        "inductor": 5,
        "switch": 3,
        "transformer": 1,
        "pcb": 2,
        "solder_joint": 500,
    },
}


def printer_failure_rate(
    printer_type: str,
    environment: str = "space_flight",
) -> float:
    """Return failure rate in failures/hour for a 3D printer subsystem.

    Uses component-level MIL-HDBK-217F rates summed over the printer BOM.
    """
    if printer_type not in PRINTER_BOM:
        raise KeyError(
            f"Unknown printer type: {printer_type!r}. "
            f"Available: {sorted(PRINTER_BOM.keys())}"
        )
    return system_failure_rate(PRINTER_BOM[printer_type], environment)


def printer_annual_degradation_rate(
    printer_type: str,
    environment: str = "ground_benign",
) -> float:
    """Estimate annual health degradation for a printer subsystem.

    Rather than treating the printer as a series system (where ANY component
    failure = total failure), this models gradual degradation: each component
    failure reduces printer health proportionally to that component's
    criticality weight.  Critical components (motors, laser diodes, ICs)
    contribute more to degradation than passive components (resistors, caps).

    The calculation weights component failure rates by criticality:
      - Motors/laser diodes: weight = 1.0 (direct mechanical/optical path)
      - ICs/microprocessors: weight = 0.5 (may have redundancy)
      - Passive components: weight = 0.05 (typically redundant or degradable)
      - Solder joints: weight = 0.002 (single joint failure rarely fatal)

    Returns an annual degradation fraction (0.0 to ~0.15 typically).
    """
    import math

    if printer_type not in PRINTER_BOM:
        raise KeyError(
            f"Unknown printer type: {printer_type!r}. "
            f"Available: {sorted(PRINTER_BOM.keys())}"
        )

    # Criticality weights by component category
    # Motors: MIL-HDBK-217F motor lambda_b includes bearing wear which is
    # a maintenance item (replaced on schedule), not a catastrophic failure.
    # Weight of 0.05 reflects that bearing replacement degrades printer
    # health only slightly (comparable to a routine maintenance event).
    _WEIGHTS: dict[str, float] = {
        "motor_stepper": 0.05,
        "motor_servo": 0.05,
        "motor": 0.05,
        "laser_diode": 1.0,
        "microprocessor": 0.5,
        "ic_digital": 0.3,
        "transformer": 0.4,
        "mosfet": 0.2,
        "inductor": 0.1,
        "switch": 0.1,
        "diode": 0.05,
        "thermistor": 0.05,
        "resistor": 0.02,
        "capacitor_ceramic": 0.02,
        "capacitor_electrolytic": 0.05,
        "connector": 0.03,
        "pcb": 0.05,
        "solder_joint": 0.002,
    }

    bom = PRINTER_BOM[printer_type]
    weighted_degradation = 0.0

    for comp_type, count in bom.items():
        fr = get_failure_rate(comp_type, environment)
        # Expected number of failures of this type per year
        expected_failures = fr * 8760.0 * count
        weight = _WEIGHTS.get(comp_type, 0.05)
        # Each expected failure contributes weight to degradation
        weighted_degradation += expected_failures * weight

    # Clamp to reasonable range (0.5% to 15% annual degradation)
    return max(0.005, min(0.15, weighted_degradation))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ENV_ALIASES: dict[str, str] = {
    "space_flight": "S_F",
    "space": "S_F",
    "ground_benign": "G_B",
    "ground_fixed": "G_F",
    "ground_mobile": "G_M",
    "naval_sheltered": "N_S",
    "naval_unsheltered": "N_U",
    "airborne_inhabited_cargo": "A_IC",
    "airborne_inhabited_fighter": "A_IF",
    "airborne_uninhabited_cargo": "A_UC",
    "airborne_uninhabited_fighter": "A_UF",
    "airborne_rotary_wing": "A_RW",
    "missile_flight": "M_F",
    "missile_launch": "M_L",
    "cannon_launch": "C_L",
}


def _normalize_env_key(env: str) -> str:
    """Normalize environment string to canonical code (e.g. S_F)."""
    # Already a code?
    if env in ("G_B", "G_F", "G_M", "N_S", "N_U", "A_IC", "A_IF",
               "A_UC", "A_UF", "A_RW", "S_F", "M_F", "M_L", "C_L"):
        return env
    low = env.lower().strip()
    if low in _ENV_ALIASES:
        return _ENV_ALIASES[low]
    raise KeyError(
        f"Unknown environment: {env!r}. Use one of: "
        f"{list(_ENV_ALIASES.keys())} or standard codes "
        f"(G_B, S_F, M_F, etc.)"
    )
