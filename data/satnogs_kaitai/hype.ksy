---
meta:
  id: hype
  endian: be
# 2025-01-29, DL7NDR - HYPE LoRa Telemetry Decoder
# doc-ref: https://wiki.satlab.agh.edu.pl/s/docs/doc/receiving-telemetry-beacons-M9QaX5CSGV
doc: |
  :field service: service
  :field callsign: callsign
  :field counter: counter
  :field sat_mode: sat_mode
  :field vbus: vbus
  :field balance: balance
  :field charge: charge
  :field sat_temp: sat_temp
  :field sw_ver: sw_ver
  :field restart_counter: restart_counter
  :field uptime: uptime
  :field x_rate: x_rate
  :field y_rate: y_rate
  :field z_rate: z_rate
  :field sys_status: sys_status
  :field sys_status_dbm: sys_status_dbm
  :field sys_status_reserved: sys_status_reserved
  :field sys_status_software_slot_selected: sys_status_software_slot_selected

seq:
  - id: service
    type: u1
  - id: callsign
    type: str
    size: 4
    encoding: ASCII
    valid: "'HYPE'"
  - id: counter
    type: u4
  - id: sat_mode
    type: u1
  - id: vbus
    type: u2
  - id: balance_raw
    type: s2
  - id: charge_raw
    type: u2
  - id: sat_temp
    type: s2
  - id: sw_ver
    type: u2
  - id: restart_counter
    type: u4
  - id: uptime
    type: u4
  - id: x_rate_raw
    type: s2
  - id: y_rate_raw
    type: s2
  - id: z_rate_raw
    type: s2
  - id: sys_status
    type: u1

instances:
  balance:
    if: sat_mode != 0
    value: balance_raw
  charge:
    if: sat_mode != 0
    value: charge_raw
  x_rate:
    if: sat_mode != 0
    value: x_rate_raw
  y_rate:
    if: sat_mode != 0
    value: y_rate_raw
  z_rate:
    if: sat_mode != 0
    value: z_rate_raw
  sys_status_dbm:
    value: (sys_status & 0b00111111)
  sys_status_reserved:
    value: (sys_status & 0b01000000) >> 6
  sys_status_software_slot_selected:
    value: (sys_status & 0b10000000) >> 7
