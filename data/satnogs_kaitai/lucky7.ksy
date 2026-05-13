---
meta:
  id: lucky7
  endian: be
# 2024-05-30, DL7NDR
# 2024-06-04, DL7NDR - removed enums because of problems in grafana and corrected "battery_voltage" to u1
# 2024-06-08, DL7NDR - corrected mission_counter, total_reset_counter and swap_reset_counter to unsigned integers
# doc-ref: https://www.lucky7satellite.org/download/Lucky-7_-_Amateur_Radio_Information.pdf
doc: |
  :field obc_id: obc_id
  :field mission_counter: mission_counter
  :field callsign_and_satellite_name: callsign_and_satellite_name
  :field total_reset_counter: total_reset_counter
  :field swap_reset_counter: swap_reset_counter
  :field battery_voltage: battery_voltage
  :field mcu_temperature: mcu_temperature
  :field pa_temperature: pa_temperature
  :field processor_current: processor_current
  :field mcu_voltage_3v3: mcu_voltage_3v3
  :field mcu_voltage_1v2: mcu_voltage_1v2
  :field angular_rate_x_axis: angular_rate_x_axis
  :field angular_rate_y_axis: angular_rate_y_axis
  :field angular_rate_z_axis: angular_rate_z_axis
  :field antenna_burnwire: antenna_burnwire

seq:
  - id: obc_id
    type: s2le
    doc: '00000 = Nominal, 0080 = Redundant'
  - id: mission_counter
    type: u4
    doc: 'last byte (unused) borrowed from obc_id to be able to use type s4; Counter since OBC Reset or OBC Swap in [s]'
  - id: callsign_and_satellite_name
    type: str
    size: 12
    encoding: ASCII
    valid: "'OK0SATLUCKY7'"
  - id: total_reset_counter
    type: u2
    doc: 'Total no. of resets'
  - id: swap_reset_counter
    type: u2
    doc: 'No. of resets since OBC Swap'
  - id: battery_voltage
    type: u1
    doc: '* 0.02 V (doc-ref says incorrectly"* 50 mV"'
  - id: mcu_temperature
    type: s1
    doc: '[°C]'
  - id: pa_temperature
    type: s1
    doc: '[°C]'
  - id: processor_current
    type: u1
    doc: '[mA]'
  - id: mcu_voltage_3v3
    type: u1
    doc: '* 0.02 V (doc-ref says incorrectly"* 50 mV"'
  - id: mcu_voltage_1v2
    type: u1
    doc: '* 0.02 V (doc-ref says incorrectly"* 50 mV"'
  - id: angular_rate_x_axis
    type: s2
    doc: 'X [°/s], range +/- 2000 °/s; 0x07d1 = 2001 = Gyro off'
  - id: angular_rate_y_axis
    type: s2
    doc: 'Y [°/s], range +/- 2000 °/s; 0x07d1 = 2001 = Gyro off'
  - id: angular_rate_z_axis
    type: s2
    doc: 'Z [°/s], range +/- 2000 °/s; 0x07d1 = 2001 = Gyro off'
  - id: antenna_burnwire
    type: u1
    doc: '0x01 = enabled, normally 0x00 = disabled'
