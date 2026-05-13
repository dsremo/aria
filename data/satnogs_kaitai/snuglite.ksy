---
meta:
  id: snuglite
  title: SNUGLITE-I Telemetry Decoder
  endian: be 
doc-ref: https://snuglitecubesat.wixsite.com/website/post/snuglite-beacon-structure
# 2025-04-20, DL7NDR
doc: |
  :field destination_callsign: beacon_types.type_check.destination_callsign
  :field source_callsign: beacon_types.type_check.source_callsign
  :field csp_header_priority: beacon_types.type_check.csp_header_priority
  :field csp_header_source: beacon_types.type_check.csp_header_source
  :field csp_header_destination: beacon_types.type_check.csp_header_destination
  :field csp_header_destination_port: beacon_types.type_check.csp_header_destination_port
  :field csp_header_source_port: beacon_types.type_check.csp_header_source_port
  :field csp_header_reserved: beacon_types.type_check.csp_header_reserved
  :field csp_header_flags: beacon_types.type_check.csp_header_flags
  :field firmware_version: beacon_types.type_check.firmware_version
  :field positioning_flag: beacon_types.type_check.positioning_flag
  :field position_x: beacon_types.type_check.position_x
  :field position_y: beacon_types.type_check.position_y
  :field position_z: beacon_types.type_check.position_z
  :field velocity_x: beacon_types.type_check.velocity_x
  :field velocity_y: beacon_types.type_check.velocity_y
  :field velocity_z: beacon_types.type_check.velocity_z
  :field battery_mode: beacon_types.type_check.battery_mode
  :field battery_voltage: beacon_types.type_check.battery_voltage
  :field battery_current: beacon_types.type_check.battery_current
  :field power_switch_gps_side: beacon_types.type_check.power_switch_gps_side
  :field power_switch_magnetometer: beacon_types.type_check.power_switch_magnetometer
  :field power_switch_sd_card: beacon_types.type_check.power_switch_sd_card
  :field power_switch_gps_up: beacon_types.type_check.power_switch_gps_up
  :field power_switch_uhf: beacon_types.type_check.power_switch_uhf
  :field power_switch_boom: beacon_types.type_check.power_switch_boom
  :field power_supply_current_boom: beacon_types.type_check.power_supply_current_boom
  :field power_supply_current_uhf: beacon_types.type_check.power_supply_current_uhf
  :field power_supply_current_gps_up: beacon_types.type_check.power_supply_current_gps_up
  :field power_supply_current_sd_card: beacon_types.type_check.power_supply_current_sd_card
  :field power_supply_current_magnetometer: beacon_types.type_check.power_supply_current_magnetometer
  :field power_supply_current_gps_side: beacon_types.type_check.power_supply_current_gps_side
  :field solar_cell_input_voltage_x: beacon_types.type_check.solar_cell_input_voltage_x
  :field solar_cell_input_voltage_y: beacon_types.type_check.solar_cell_input_voltage_y
  :field solar_cell_input_voltage_z: beacon_types.type_check.solar_cell_input_voltage_z
  :field solar_cell_input_current_x: beacon_types.type_check.solar_cell_input_current_x
  :field solar_cell_input_current_y: beacon_types.type_check.solar_cell_input_current_y
  :field solar_cell_input_current_z: beacon_types.type_check.solar_cell_input_current_z
  :field estimated_attitude_q0: beacon_types.type_check.estimated_attitude_q0
  :field estimated_attitude_q1: beacon_types.type_check.estimated_attitude_q1
  :field estimated_attitude_q2: beacon_types.type_check.estimated_attitude_q2
  :field estimated_attitude_q3: beacon_types.type_check.estimated_attitude_q3
  :field estimated_gyro_bias_roll: beacon_types.type_check.estimated_gyro_bias_roll
  :field estimated_gyro_bias_pitch: beacon_types.type_check.estimated_gyro_bias_pitch
  :field estimated_gyro_bias_yaw: beacon_types.type_check.estimated_gyro_bias_yaw
  :field estimated_angular_rate_roll: beacon_types.type_check.estimated_angular_rate_roll
  :field estimated_angular_rate_pitch: beacon_types.type_check.estimated_angular_rate_pitch
  :field estimated_angular_rate_yaw: beacon_types.type_check.estimated_angular_rate_yaw
  :field measured_angular_rate_roll: beacon_types.type_check.measured_angular_rate_roll
  :field measured_angular_rate_pitch: beacon_types.type_check.measured_angular_rate_pitch
  :field measured_angular_rate_yaw: beacon_types.type_check.measured_angular_rate_yaw
  :field sun_eclipse: beacon_types.type_check.sun_eclipse
  :field attitude_convergence: beacon_types.type_check.attitude_convergence
  :field attitude_variance_q0: beacon_types.type_check.attitude_variance_q0
  :field attitude_variance_q1: beacon_types.type_check.attitude_variance_q1
  :field attitude_variance_q2: beacon_types.type_check.attitude_variance_q2
  :field attitude_variance_q3: beacon_types.type_check.attitude_variance_q3
  :field current_operation_mode: beacon_types.type_check.current_operation_mode
  :field elapsed_time: beacon_types.type_check.elapsed_time
  :field temperature_solar_panel_plus_x: beacon_types.type_check.temperature_solar_panel_plus_x
  :field temperature_solar_panel_plus_y: beacon_types.type_check.temperature_solar_panel_plus_y
  :field temperature_solar_panel_minus_x: beacon_types.type_check.temperature_solar_panel_minus_x
  :field temperature_solar_panel_minus_y: beacon_types.type_check.temperature_solar_panel_minus_y
  :field temperature_solar_panel_minus_z: beacon_types.type_check.temperature_solar_panel_minus_z
  :field temperature_obc_1: beacon_types.type_check.temperature_obc_1
  :field temperature_obc_2: beacon_types.type_check.temperature_obc_2
  :field temperature_eps_module_1: beacon_types.type_check.temperature_eps_module_1
  :field temperature_eps_module_2: beacon_types.type_check.temperature_eps_module_2
  :field temperature_eps_module_3: beacon_types.type_check.temperature_eps_module_3
  :field temperature_eps_module_4: beacon_types.type_check.temperature_eps_module_4
  :field temperature_uhf_module_1: beacon_types.type_check.temperature_uhf_module_1
  :field temperature_uhf_module_2: beacon_types.type_check.temperature_uhf_module_2
  :field boom_release_status: beacon_types.type_check.boom_release_status
  :field antenna_release_status: beacon_types.type_check.antenna_release_status
  :field count_antenna_release_trial: beacon_types.type_check.count_antenna_release_trial
  :field count_boom_release_trial: beacon_types.type_check.count_boom_release_trial
  :field beacon_type: beacon_types.type_check.beacon_type
  :field satellite_time: beacon_types.type_check.satellite_time

seq:
  - id: beacon_types
    type: beacon_types_t

types:
  beacon_types_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x3c495445: simple # <ITE
            _: full

    instances:
      check:
        type: u4
        pos: 61

  full:
   seq:
     - id: destination_callsign
       type: str
       encoding: UTF-8
       size: 5
       valid: '"DS0DH"'
       doc: 'it is not bitshifted contrary to AX.25'

     - id: last_digit_of_destination_callsign_and_destination_ssid
       type: u2

     - id: source_callsign
       type: str
       encoding: UTF-8
       size: 5
       valid: '"DS0DH"'
       doc: 'it is not bitshifted contrary to AX.25'

     - id: last_digit_of_source_callsign_and_source_ssid
       type: u2

     - id: control_and_pid
       type: u2

     - id: csp_header_priority
       type: b2

     - id: csp_header_source
       type: b5

     - id: csp_header_destination
       type: b5

     - id: csp_header_destination_port
       type: b6

     - id: csp_header_source_port
       type: b6

     - id: csp_header_reserved
       type: b4

     - id: csp_header_flags
       type: b4

     - id: start_id
       type: str
       encoding: UTF-8
       size: 6
       valid: '"SNUGL>"'

     - id: firmware_version
       type: u1

     - id: time_year
       type: u1

     - id: time_month
       type: u1

     - id: time_day
       type: u1

     - id: time_hour
       type: u1

     - id: time_minute
       type: u1

     - id: time_second
       type: u1

     - id: positioning_flag
       type: u1
       doc: '0 = TLE, 1 = GPS, 255 = not used'

     - id: position_x
       type: s4

     - id: position_y
       type: s4

     - id: position_z
       type: s4

     - id: velocity_x
       type: s4

     - id: velocity_y
       type: s4

     - id: velocity_z
       type: s4

     - id: battery_mode
       type: u1
       doc: '0=initial, 1=undervoltage, 2=safemode, 3=nominal, 4=full'

     - id: battery_voltage
       type: u2

     - id: battery_current
       type: u2

     - id: not_used
       type: b2

     - id: power_switch_gps_side
       type: b1

     - id: power_switch_magnetometer
       type: b1

     - id: power_switch_sd_card
       type: b1

     - id: power_switch_gps_up
       type: b1

     - id: power_switch_uhf
       type: b1

     - id: power_switch_boom
       type: b1

     - id: power_supply_current_boom
       type: u2

     - id: power_supply_current_uhf
       type: u2

     - id: power_supply_current_gps_up
       type: u2

     - id: power_supply_current_sd_card
       type: u2

     - id: power_supply_current_magnetometer
       type: u2

     - id: power_supply_current_gps_side
       type: u2

     - id: solar_cell_input_voltage_x
       type: u2

     - id: solar_cell_input_voltage_y
       type: u2

     - id: solar_cell_input_voltage_z
       type: u2

     - id: solar_cell_input_current_x
       type: u2

     - id: solar_cell_input_current_y
       type: u2

     - id: solar_cell_input_current_z
       type: u2

     - id: estimated_attitude_q0
       type: f4

     - id: estimated_attitude_q1
       type: f4

     - id: estimated_attitude_q2
       type: f4

     - id: estimated_attitude_q3
       type: f4

     - id: estimated_gyro_bias_roll
       type: f4

     - id: estimated_gyro_bias_pitch
       type: f4

     - id: estimated_gyro_bias_yaw
       type: f4

     - id: estimated_angular_rate_roll
       type: f4

     - id: estimated_angular_rate_pitch
       type: f4

     - id: estimated_angular_rate_yaw
       type: f4

     - id: measured_angular_rate_roll
       type: f4

     - id: measured_angular_rate_pitch
       type: f4

     - id: measured_angular_rate_yaw
       type: f4

     - id: not_used_1
       type: b6

     - id: sun_eclipse
       type: b1
       doc: '1=sun, 0=eclipse'

     - id: attitude_convergence
       type: b1
       doc: '1=convergent, 0=not convergent'

     - id: attitude_variance_q0
       type: f4

     - id: attitude_variance_q1
       type: f4

     - id: attitude_variance_q2
       type: f4

     - id: attitude_variance_q3
       type: f4

     - id: current_operation_mode
       type: u1
       doc: '0=init mode, 1=standby'

     - id: elapsed_time
       type: s4
       doc: 'in minutes'

     - id: temperature_solar_panel_plus_x
       type: s1

     - id: temperature_solar_panel_plus_y
       type: s1

     - id: temperature_solar_panel_minus_x
       type: s1

     - id: temperature_solar_panel_minus_y
       type: s1

     - id: temperature_solar_panel_minus_z
       type: s1

     - id: temperature_obc_1
       type: s1

     - id: temperature_obc_2
       type: s1

     - id: temperature_eps_module_1
       type: s1

     - id: temperature_eps_module_2
       type: s1

     - id: temperature_eps_module_3
       type: s1

     - id: temperature_eps_module_4
       type: s1

     - id: temperature_uhf_module_1
       type: s1

     - id: temperature_uhf_module_2
       type: s1

     - id: not_used_2
       type: b6

     - id: boom_release_status
       type: b1

     - id: antenna_release_status
       type: b1

     - id: count_antenna_release_trial
       type: u1

     - id: count_boom_release_trial
       type: u1

     - id: end_id
       type: str
       encoding: UTF-8
       size: 4
       valid: '"<ITE"'

# we skip parsing 32 bytes of Reed-Solomon here at the end

   instances:
    beacon_type:
     value: '"full"'

    year:
     value: 'time_year.to_s.length == 1 ? "0"+time_year.to_s : time_year.to_s'
     doc: 'only for calculation, do not display'

    month:
     value: 'time_month.to_s.length == 1 ? "0"+time_month.to_s : time_month.to_s'
     doc: 'only for calculation, do not display'

    day:
     value: 'time_day.to_s.length == 1 ? "0"+time_day.to_s : time_day.to_s'
     doc: 'only for calculation, do not display'

    hour:
     value: 'time_hour.to_s.length == 1 ? "0"+time_hour.to_s : time_hour.to_s'
     doc: 'only for calculation, do not display'

    minute:
     value: 'time_minute.to_s.length == 1 ? "0"+time_minute.to_s : time_minute.to_s'
     doc: 'only for calculation, do not display'

    second:
     value: 'time_second.to_s.length == 1 ? "0"+time_second.to_s : time_second.to_s'
     doc: 'only for calculation, do not display'

    satellite_time:
     value: '"20" + year + "-" + month + "-" + day + "T" + hour + ":" + minute + ":" + second + "Z"'




  simple:
   seq:
     - id: destination_callsign
       type: str
       encoding: UTF-8
       size: 5
       valid: '"DS0DH"'
       doc: 'it is not bitshifted contrary to AX.25'

     - id: last_digit_of_destination_callsign_and_destination_ssid
       type: u2

     - id: source_callsign
       type: str
       encoding: UTF-8
       size: 5
       valid: '"DS0DH"'
       doc: 'it is not bitshifted contrary to AX.25'

     - id: last_digit_of_source_callsign_and_source_ssid
       type: u2

     - id: control_and_pid
       type: u2

     - id: csp_header_priority
       type: b2

     - id: csp_header_source
       type: b5

     - id: csp_header_destination
       type: b5

     - id: csp_header_destination_port
       type: b6

     - id: csp_header_source_port
       type: b6

     - id: csp_header_reserved
       type: b4

     - id: csp_header_flags
       type: b4

     - id: start_id
       type: str
       encoding: UTF-8
       size: 6
       valid: '"SNUGL>"'

     - id: firmware_version
       type: u1

     - id: time_year
       type: u1

     - id: time_month
       type: u1

     - id: time_day
       type: u1

     - id: time_hour
       type: u1

     - id: time_minute
       type: u1

     - id: time_second
       type: u1

     - id: positioning_flag
       type: u1
       doc: '0 = TLE, 1 = GPS, 255 = not used'

     - id: position_x
       type: s4

     - id: position_y
       type: s4

     - id: position_z
       type: s4

     - id: velocity_x
       type: s4

     - id: velocity_y
       type: s4

     - id: velocity_z
       type: s4

     - id: battery_mode
       type: u1
       doc: '0=initial, 1=undervoltage, 2=safemode, 3=nominal, 4=full'

     - id: battery_voltage
       type: u2

     - id: end_id
       type: str
       encoding: UTF-8
       size: 4
       valid: '"<ITE"'

# we skip parsing 32 bytes of Reed-Solomon here at the end

   instances:
    beacon_type:
     value: '"simple"'

    year:
     value: 'time_year.to_s.length == 1 ? "0"+time_year.to_s : time_year.to_s'
     doc: 'only for calculation, do not display'

    month:
     value: 'time_month.to_s.length == 1 ? "0"+time_month.to_s : time_month.to_s'
     doc: 'only for calculation, do not display'

    day:
     value: 'time_day.to_s.length == 1 ? "0"+time_day.to_s : time_day.to_s'
     doc: 'only for calculation, do not display'

    hour:
     value: 'time_hour.to_s.length == 1 ? "0"+time_hour.to_s : time_hour.to_s'
     doc: 'only for calculation, do not display'

    minute:
     value: 'time_minute.to_s.length == 1 ? "0"+time_minute.to_s : time_minute.to_s'
     doc: 'only for calculation, do not display'

    second:
     value: 'time_second.to_s.length == 1 ? "0"+time_second.to_s : time_second.to_s'
     doc: 'only for calculation, do not display'

    satellite_time:
     value: '"20" + year + "-" + month + "-" + day + "T" + hour + ":" + minute + ":" + second + "Z"'
