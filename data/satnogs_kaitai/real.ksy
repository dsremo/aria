meta:
  id: real
  title: REAL Beacons Protocol
  endian: be
doc: |
  :field callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field ssid_mask: ax25_frame.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid_raw_ssid_mask: ax25_frame.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field ctl: ax25_frame.ax25_header.ctl
  :field ccsds_header_first: ax25_frame.ccsds_header.ccsds_header_first
  :field length: ax25_frame.ccsds_header.length
  :field ccsds_header_second: ax25_frame.ccsds_header.ccsds_header_second
  :field service_type: ax25_frame.real_header.service_type
  :field service_sub_type: ax25_frame.real_header.service_sub_type
  :field structure_id: ax25_frame.real_header.structure_id
  :field syncword: ax25_frame.real_header.syncword.syncword
  :field bat_charging_status: ax25_frame.payload.bat_charging_status
  :field v5_bat_current: ax25_frame.payload.v5_bat_current
  :field v3_3_bat_current: ax25_frame.payload.v3_3_bat_current
  :field vbat_bat_current: ax25_frame.payload.vbat_bat_current
  :field v3_3_bat_voltage: ax25_frame.payload.v3_3_bat_voltage
  :field v5_bat_voltage: ax25_frame.payload.v5_bat_voltage
  :field vbat_bat_voltage: ax25_frame.payload.vbat_bat_voltage
  :field bat_board_temperature: ax25_frame.payload.bat_board_temperature
  :field bat_cell_1_temperature: ax25_frame.payload.bat_cell_1_temperature
  :field bat_cell_2_temperature: ax25_frame.payload.bat_cell_2_temperature
  :field bat_cell_3_temperature: ax25_frame.payload.bat_cell_3_temperature
  :field bat_cell_4_temperature: ax25_frame.payload.bat_cell_4_temperature
  :field battery_heater_status_0: ax25_frame.payload.battery_heater_status_0
  :field battery_heater_status_1: ax25_frame.payload.battery_heater_status_1
  :field battery_heater_status_2: ax25_frame.payload.battery_heater_status_2
  :field battery_heater_status_3: ax25_frame.payload.battery_heater_status_3
  :field vbat_eps_voltage: ax25_frame.payload.vbat_eps_voltage
  :field v3_3_eps_voltage: ax25_frame.payload.v3_3_eps_voltage
  :field v5_eps_voltage: ax25_frame.payload.v5_eps_voltage
  :field v12_eps_voltage: ax25_frame.payload.v12_eps_voltage
  :field vbat_eps_current: ax25_frame.payload.vbat_eps_current
  :field v3_3_eps_current: ax25_frame.payload.v3_3_eps_current
  :field v5_eps_current: ax25_frame.payload.v5_eps_current
  :field v12_eps_current: ax25_frame.payload.v12_eps_current
  :field sw1_unused_voltage: ax25_frame.payload.sw1_unused_voltage
  :field sw2_unused_voltage: ax25_frame.payload.sw2_unused_voltage
  :field sw3_instrument_voltage: ax25_frame.payload.sw3_instrument_voltage
  :field sw4_li2_voltage: ax25_frame.payload.sw4_li2_voltage
  :field sw5_uhf_temp_sensor_voltage: ax25_frame.payload.sw5_uhf_temp_sensor_voltage
  :field sw6_unused_voltage: ax25_frame.payload.sw6_unused_voltage
  :field sw7_unused_voltage: ax25_frame.payload.sw7_unused_voltage
  :field sw8_xact_serial_voltage: ax25_frame.payload.sw8_xact_serial_voltage
  :field sw9_gps_voltage: ax25_frame.payload.sw9_gps_voltage
  :field sw10_instrument_lvds_voltage: ax25_frame.payload.sw10_instrument_lvds_voltage
  :field sw1_unused_current: ax25_frame.payload.sw1_unused_current
  :field sw2_unused_current: ax25_frame.payload.sw2_unused_current
  :field sw3_instrument_current: ax25_frame.payload.sw3_instrument_current
  :field sw4_li2_current: ax25_frame.payload.sw4_li2_current
  :field sw5_uhf_temp_sensor_current: ax25_frame.payload.sw5_uhf_temp_sensor_current
  :field sw6_unused_current: ax25_frame.payload.sw6_unused_current
  :field sw7_unused_current: ax25_frame.payload.sw7_unused_current
  :field sw8_xact_serial_current: ax25_frame.payload.sw8_xact_serial_current
  :field sw9_gps_current: ax25_frame.payload.sw9_gps_current
  :field sw10_instrument_lvds_current: ax25_frame.payload.sw10_instrument_lvds_current
  :field eps_mb_temperature: ax25_frame.payload.eps_mb_temperature
  :field eps_db_temperature: ax25_frame.payload.eps_db_temperature
  :field sa1_salw_inner_voltage: ax25_frame.payload.sa1_salw_inner_voltage
  :field sa2_salw_outer_voltage: ax25_frame.payload.sa2_salw_outer_voltage
  :field sa4_sarw_inner_voltage: ax25_frame.payload.sa4_sarw_inner_voltage
  :field sa5_sarw_outer_voltage: ax25_frame.payload.sa5_sarw_outer_voltage
  :field sa1_salw_inner_current: ax25_frame.payload.sa1_salw_inner_current
  :field sa2_salw_outer_current: ax25_frame.payload.sa2_salw_outer_current
  :field sa4_sarw_inner_current: ax25_frame.payload.sa4_sarw_inner_current
  :field sa5_sarw_outer_current: ax25_frame.payload.sa5_sarw_outer_current
  :field sa1_salw_inner_temperature: ax25_frame.payload.sa1_salw_inner_temperature
  :field sa2_salw_outer_temperature: ax25_frame.payload.sa2_salw_outer_temperature
  :field sa4_sarw_inner_temperature: ax25_frame.payload.sa4_sarw_inner_temperature
  :field sa5_sarw_outer_temperature: ax25_frame.payload.sa5_sarw_outer_temperature
  :field curr_boot_image: ax25_frame.payload.curr_boot_image
  :field image_valid: ax25_frame.payload.image_valid
  :field image_priority_0: ax25_frame.payload.image_priority_0
  :field image_priority_1: ax25_frame.payload.image_priority_1
  :field image_priority_2: ax25_frame.payload.image_priority_2
  :field image_is_stable: ax25_frame.payload.image_is_stable
  :field adc_enable: ax25_frame.payload.adc_enable
  :field last_reset_cause: ax25_frame.payload.last_reset_cause
  :field last_boot_count: ax25_frame.payload.last_boot_count
  :field version: ax25_frame.payload.version
  :field interface_baud_rate: ax25_frame.payload.interface_baud_rate
  :field rx_rf_baud_rate: ax25_frame.payload.rx_rf_baud_rate
  :field rx_modulation: ax25_frame.payload.rx_modulation
  :field rx_frequency: ax25_frame.payload.rx_frequency
  :field tx_power_amp_level: ax25_frame.payload.tx_power_amp_level
  :field tx_rf_baud_rate: ax25_frame.payload.tx_rf_baud_rate
  :field tx_modulation: ax25_frame.payload.tx_modulation
  :field tx_frequency: ax25_frame.payload.tx_frequency
  :field source_callsign_byte_0: ax25_frame.payload.source_callsign_byte_0
  :field source_callsign_byte_1: ax25_frame.payload.source_callsign_byte_1
  :field source_callsign_byte_2: ax25_frame.payload.source_callsign_byte_2
  :field source_callsign_byte_3: ax25_frame.payload.source_callsign_byte_3
  :field source_callsign_byte_4: ax25_frame.payload.source_callsign_byte_4
  :field source_callsign_byte_5: ax25_frame.payload.source_callsign_byte_5
  :field destination_callsign_byte_0: ax25_frame.payload.destination_callsign_byte_0
  :field destination_callsign_byte_1: ax25_frame.payload.destination_callsign_byte_1
  :field destination_callsign_byte_2: ax25_frame.payload.destination_callsign_byte_2
  :field destination_callsign_byte_3: ax25_frame.payload.destination_callsign_byte_3
  :field destination_callsign_byte_4: ax25_frame.payload.destination_callsign_byte_4
  :field destination_callsign_byte_5: ax25_frame.payload.destination_callsign_byte_5
  :field rssi: ax25_frame.payload.rssi
  :field vbat_obc_voltage: ax25_frame.payload.vbat_obc_voltage
  :field vbat_obc_current: ax25_frame.payload.vbat_obc_current
  :field vbat_plat_voltage: ax25_frame.payload.vbat_plat_voltage
  :field v3_3_plat_voltage: ax25_frame.payload.v3_3_plat_voltage
  :field v1_2_obc_voltage: ax25_frame.payload.v1_2_obc_voltage
  :field obc_temperature_1: ax25_frame.payload.obc_temperature_1
  :field v3_3_obc_voltage: ax25_frame.payload.v3_3_obc_voltage
  :field v3_3_obc_current: ax25_frame.payload.v3_3_obc_current
  :field v3_3_memory_voltage: ax25_frame.payload.v3_3_memory_voltage
  :field v3_3_memory_current: ax25_frame.payload.v3_3_memory_current
  :field vbat_periph_current: ax25_frame.payload.vbat_periph_current
  :field v3_3_periph_current: ax25_frame.payload.v3_3_periph_current
  :field v2_5_periph_current: ax25_frame.payload.v2_5_periph_current
  :field obc_temperature_2: ax25_frame.payload.obc_temperature_2
  :field obc_temperature_3: ax25_frame.payload.obc_temperature_3
  :field v3_3_gps_voltage: ax25_frame.payload.v3_3_gps_voltage
  :field v3_3_gps_current: ax25_frame.payload.v3_3_gps_current
  :field v2_5_obc_voltage: ax25_frame.payload.v2_5_obc_voltage
  :field v2_5_periph_voltage: ax25_frame.payload.v2_5_periph_voltage
  :field vbat_periph_voltage: ax25_frame.payload.vbat_periph_voltage
  :field v3_3_periph_voltage: ax25_frame.payload.v3_3_periph_voltage
  :field system_mode: ax25_frame.payload.system_mode
  :field startup_mode: ax25_frame.payload.startup_mode
  :field pass_in_progress: ax25_frame.payload.pass_in_progress
  :field digital_bus_voltage: ax25_frame.payload.digital_bus_voltage
  :field wheel_bus_voltage: ax25_frame.payload.wheel_bus_voltage
  :field rod_bus_voltage: ax25_frame.payload.rod_bus_voltage
  :field wheel_1_speed: ax25_frame.payload.wheel_1_speed
  :field wheel_2_speed: ax25_frame.payload.wheel_2_speed
  :field wheel_3_speed: ax25_frame.payload.wheel_3_speed
  :field adcs_mode: ax25_frame.payload.adcs_mode
  :field wheel_1_current: ax25_frame.payload.wheel_1_current
  :field wheel_2_current: ax25_frame.payload.wheel_2_current
  :field wheel_3_current: ax25_frame.payload.wheel_3_current
  :field imu_temp: ax25_frame.payload.imu_temp
  :field wheel_1_temperature: ax25_frame.payload.wheel_1_temperature
  :field wheel_2_temperature: ax25_frame.payload.wheel_2_temperature
  :field wheel_3_temperature: ax25_frame.payload.wheel_3_temperature
  :field crc: ax25_frame.payload.crc
  :field last_uptime: ax25_frame.payload.last_uptime
  :field time_fine_seconds: ax25_frame.payload.time_fine_seconds
  :field time_fine_fractional_seconds: ax25_frame.payload.time_fine_fractional_seconds
  :field time_onboard: ax25_frame.payload.time_onboard
  :field uptime: ax25_frame.payload.uptime
  :field mode_checkpoint_time: ax25_frame.payload.mode_checkpoint_time
  :field gps_time: ax25_frame.payload.gps_time
  :field tai_seconds: ax25_frame.payload.tai_seconds


seq:
  - id: ax25_frame
    type: ax25_frame
    doc-ref: 'https://www.tapr.org/pub_ax25.html'

types:
  ax25_frame:
    seq:
    - id: ax25_header
      type: ax25_header
    - id: ccsds_header
      type: ccsds_header
    - id: real_header
      type: real_header
    - id: payload
      type:
          switch-on: ccsds_header.length
          cases:
            0xC0: health_beacon
            0x2D: time_beacon
      
  ax25_header:
    seq:
      - id: dest_callsign_raw
        type: callsign_raw
      - id: dest_ssid_raw
        type: ssid_mask
      - id: src_callsign_raw
        type: callsign_raw
      - id: src_ssid_raw
        type: ssid_mask
      - id: ctl
        type: u2

  callsign_raw:
    seq:
      - id: callsign_ror
        process: ror(1)
        size: 6
        type: callsign

  callsign:
    seq:
      - id: callsign
        type: str
        encoding: ASCII
        size: 6
        valid: '"WR9XTX"'

  real_syncword:
    seq:
      - id: syncword
        type: str
        encoding: ASCII
        size: 4
        valid: '"REAL"'

  ssid_mask:
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x0f) >> 1

  ccsds_header:
    seq:
      - id: ccsds_header_first
        type: u4
      - id: length
        type: u2
      - id: ccsds_header_second
        type: u1
            
  real_header:
    seq:
      - id: service_type
        type: u1
      - id: service_sub_type
        type: u1
      - id: structure_id
        type: u1
      - id: syncword
        type: real_syncword
      
      
  health_beacon:
    seq:
      - id: bat_charging_status
        type: b1
      - id: v5_bat_current
        type: b10
      - id: v3_3_bat_current
        type: b10
      - id: vbat_bat_current
        type: b10
      - id: v3_3_bat_voltage
        type: b10
      - id: v5_bat_voltage
        type: b10
      - id: vbat_bat_voltage
        type: b10
      - id: bat_board_temperature
        type: b10
      - id: bat_cell_1_temperature
        type: b10
      - id: bat_cell_2_temperature
        type: b10
      - id: bat_cell_3_temperature
        type: b10
      - id: bat_cell_4_temperature
        type: b10
      - id: battery_heater_status_0
        type: b10
      - id: battery_heater_status_1
        type: b10
      - id: battery_heater_status_2
        type: b10
      - id: battery_heater_status_3
        type: b10
      - id: vbat_eps_voltage
        type: b10
      - id: v3_3_eps_voltage
        type: b10
      - id: v5_eps_voltage
        type: b10
      - id: v12_eps_voltage
        type: b10
      - id: vbat_eps_current
        type: b10
      - id: v3_3_eps_current
        type: b10
      - id: v5_eps_current
        type: b10
      - id: v12_eps_current
        type: b10
      - id: sw1_unused_voltage
        type: b10
      - id: sw2_unused_voltage
        type: b10
      - id: sw3_instrument_voltage
        type: b10
      - id: sw4_li2_voltage
        type: b10
      - id: sw5_uhf_temp_sensor_voltage
        type: b10
      - id: sw6_unused_voltage
        type: b10
      - id: sw7_unused_voltage
        type: b10
      - id: sw8_xact_serial_voltage
        type: b10
      - id: sw9_gps_voltage
        type: b10
      - id: sw10_instrument_lvds_voltage
        type: b10
      - id: sw1_unused_current
        type: b10
      - id: sw2_unused_current
        type: b10
      - id: sw3_instrument_current
        type: b10
      - id: sw4_li2_current
        type: b10
      - id: sw5_uhf_temp_sensor_current
        type: b10
      - id: sw6_unused_current
        type: b10
      - id: sw7_unused_current
        type: b10
      - id: sw8_xact_serial_current
        type: b10
      - id: sw9_gps_current
        type: b10
      - id: sw10_instrument_lvds_current
        type: b10
      - id: eps_mb_temperature
        type: b10
      - id: eps_db_temperature
        type: b10
      - id: sa1_salw_inner_voltage
        type: b10
      - id: sa2_salw_outer_voltage
        type: b10
      - id: sa4_sarw_inner_voltage
        type: b10
      - id: sa5_sarw_outer_voltage
        type: b10
      - id: sa1_salw_inner_current
        type: b10
      - id: sa2_salw_outer_current
        type: b10
      - id: sa4_sarw_inner_current
        type: b10
      - id: sa5_sarw_outer_current
        type: b10
      - id: sa1_salw_inner_temperature
        type: b10
      - id: sa2_salw_outer_temperature
        type: b10
      - id: sa4_sarw_inner_temperature
        type: b10
      - id: sa5_sarw_outer_temperature
        type: b10
      - id: curr_boot_image
        type: b8
      - id: image_valid
        type: b3
      - id: image_priority_0
        type: b32
      - id: image_priority_1
        type: b32
      - id: image_priority_2
        type: b32
      - id: image_is_stable
        type: b3
      - id: adc_enable
        type: b1
      - id: last_reset_cause
        type: b2
      - id: last_boot_count
        type: b32
      - id: version
        type: b32
      - id: interface_baud_rate
        type: b3
      - id: rx_rf_baud_rate
        type: b2
      - id: rx_modulation
        type: b2
      - id: rx_frequency
        type: b32
      - id: tx_power_amp_level
        type: b8
      - id: tx_rf_baud_rate
        type: b2
      - id: tx_modulation
        type: b2
      - id: tx_frequency
        type: b32
      - id: source_callsign_byte_0
        type: b8
      - id: source_callsign_byte_1
        type: b8
      - id: source_callsign_byte_2
        type: b8
      - id: source_callsign_byte_3
        type: b8
      - id: source_callsign_byte_4
        type: b8
      - id: source_callsign_byte_5
        type: b8
      - id: destination_callsign_byte_0
        type: b8
      - id: destination_callsign_byte_1
        type: b8
      - id: destination_callsign_byte_2
        type: b8
      - id: destination_callsign_byte_3
        type: b8
      - id: destination_callsign_byte_4
        type: b8
      - id: destination_callsign_byte_5
        type: b8
      - id: rssi
        type: b8
      - id: vbat_obc_voltage
        type: b12
      - id: vbat_obc_current
        type: b12
      - id: vbat_plat_voltage
        type: b12
      - id: unused_a
        type: b12
      - id: v3_3_plat_voltage
        type: b12
      - id: v1_2_obc_voltage
        type: b12
      - id: unused_b
        type: b12
      - id: obc_temperature_1
        type: b12
      - id: v3_3_obc_voltage
        type: b12
      - id: v3_3_obc_current
        type: b12
      - id: v3_3_memory_voltage
        type: b12
      - id: v3_3_memory_current
        type: b12
      - id: vbat_periph_current
        type: b12
      - id: v3_3_periph_current
        type: b12
      - id: v2_5_periph_current
        type: b12
      - id: obc_temperature_2
        type: b12
      - id: obc_temperature_3
        type: b12
      - id: v3_3_gps_voltage
        type: b12
      - id: v3_3_gps_current
        type: b12
      - id: v2_5_obc_voltage
        type: b12
      - id: v2_5_periph_voltage
        type: b12
      - id: vbat_periph_voltage
        type: b12
      - id: v3_3_periph_voltage
        type: b12
      - id: unused_c
        type: b12
      - id: system_mode
        type: b3
      - id: startup_mode
        type: b3
      - id: pass_in_progress
        type: b1
      - id: digital_bus_voltage
        type: b16
      - id: wheel_bus_voltage
        type: b16
      - id: rod_bus_voltage
        type: b16
      - id: wheel_1_speed
        type: b16
      - id: wheel_2_speed
        type: b16
      - id: wheel_3_speed
        type: b16
      - id: adcs_mode
        type: b8
      - id: wheel_1_current 
        type: b16
      - id: wheel_2_current
        type: b16
      - id: wheel_3_current
        type: b16
      - id: imu_temp
        type: b16
      - id: wheel_1_temperature
        type: b16
      - id: wheel_2_temperature
        type: b16
      - id: wheel_3_temperature
        type: b16
      - id: unused_j
        type: b16
      - id: crc
        type: b16
    
  time_beacon:
    seq:
      - id: last_uptime
        type: u4
      - id: time_fine_seconds
        type: u4
      - id: time_fine_fractional_seconds
        type: u4
      - id: time_onboard
        type: u4
      - id: uptime
        type: u4
      - id: mode_checkpoint_time
        type: u4
      - id: gps_time
        type: u4
      - id: tai_seconds
        type: f8
      - id: crc
        type: b16
