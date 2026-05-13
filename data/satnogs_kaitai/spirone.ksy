---
meta:
  id: spirone
  title: Spirone Telemetry Decoder
  endian: be 
doc-ref: Sejong University
# 2026-01-06, DL7NDR
# 2026-01-09, DL7NDR; corrected version
doc: |
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
  :field power_switch_rp: beacon_types.type_check.power_switch_rp
  :field power_switch_cameras: beacon_types.type_check.power_switch_cameras
  :field power_switch_leo_nav: beacon_types.type_check.power_switch_leo_nav
  :field power_switch_s_band: beacon_types.type_check.power_switch_s_band
  :field power_switch_gps_receiver: beacon_types.type_check.power_switch_gps_receiver
  :field power_switch_uhf_transceiver: beacon_types.type_check.power_switch_uhf_transceiver
  :field power_switch_current_uhf_transceiver: beacon_types.type_check.power_switch_current_uhf_transceiver
  :field power_switch_current_gps_receiver: beacon_types.type_check.power_switch_current_gps_receiver
  :field power_switch_current_s_band: beacon_types.type_check.power_switch_current_s_band
  :field power_switch_current_leo_nav: beacon_types.type_check.power_switch_current_leo_nav
  :field power_switch_current_cameras: beacon_types.type_check.power_switch_current_cameras
  :field power_switch_current_rp: beacon_types.type_check.power_switch_current_rp
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
  :field current_operation_mode: beacon_types.type_check.current_operation_mode
  :field elapsed_time: beacon_types.type_check.elapsed_time
  :field temperature_obc_1: beacon_types.type_check.temperature_obc_1
  :field temperature_obc_2: beacon_types.type_check.temperature_obc_2
  :field temperature_eps_p31u_1: beacon_types.type_check.temperature_eps_p31u_1
  :field temperature_eps_p31u_2: beacon_types.type_check.temperature_eps_p31u_2
  :field temperature_eps_p31u_3: beacon_types.type_check.temperature_eps_p31u_3
  :field temperature_eps_p31u_4: beacon_types.type_check.temperature_eps_p31u_4
  :field temperature_eps_bp4_1: beacon_types.type_check.temperature_eps_bp4_1
  :field temperature_eps_bp4_2: beacon_types.type_check.temperature_eps_bp4_2
  :field temperature_uhf_ax100_brd: beacon_types.type_check.temperature_uhf_ax100_brd
  :field temperature_uhf_ax100_pa: beacon_types.type_check.temperature_uhf_ax100_pa
  :field deploy_status_s_band_antenna: beacon_types.type_check.deploy_status_s_band_antenna
  :field deploy_status_uhf_antenna: beacon_types.type_check.deploy_status_uhf_antenna
  :field deploy_attempts_uhf: beacon_types.type_check.deploy_attempts_uhf
  :field deploy_attempts_s_band: beacon_types.type_check.deploy_attempts_s_band
  :field total_tx_data_volume: beacon_types.type_check.total_tx_data_volume
  :field total_rx_data_volume: beacon_types.type_check.total_rx_data_volume
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
            0x3c524f4e: simple # <RON
            _: full

    instances:
      check:
        type: u4
        pos: 59

  full:
   seq:
     - id: ax25_header
       type: u1
       repeat: expr
       repeat-expr: 16

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
       size: 4
       valid: '"SPI>"'

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

     - id: power_switch_rp
       type: b1

     - id: power_switch_cameras
       type: b1

     - id: power_switch_leo_nav
       type: b1

     - id: power_switch_s_band
       type: b1

     - id: power_switch_gps_receiver
       type: b1

     - id: power_switch_uhf_transceiver
       type: b1

     - id: power_switch_current_uhf_transceiver
       type: u2

     - id: power_switch_current_gps_receiver
       type: u2

     - id: power_switch_current_s_band
       type: u2

     - id: power_switch_current_leo_nav
       type: u2

     - id: power_switch_current_cameras
       type: u2

     - id: power_switch_current_rp
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

     - id: estimated_attitude_q0_check
       type: f4

     - id: estimated_attitude_q1_check
       type: f4

     - id: estimated_attitude_q2_check
       type: f4

     - id: estimated_attitude_q3_check
       type: f4

     - id: estimated_gyro_bias_roll_check
       type: f4

     - id: estimated_gyro_bias_pitch_check
       type: f4

     - id: estimated_gyro_bias_yaw_check
       type: f4

     - id: estimated_angular_rate_roll_check
       type: f4

     - id: estimated_angular_rate_pitch_check
       type: f4

     - id: estimated_angular_rate_yaw_check
       type: f4

     - id: measured_angular_rate_roll_check
       type: f4

     - id: measured_angular_rate_pitch_check
       type: f4

     - id: measured_angular_rate_yaw_check
       type: f4

     - id: not_used_1
       type: b7

     - id: sun_eclipse
       type: b1
       doc: '1=sun, 0=eclipse'

     - id: current_operation_mode
       type: u1

     - id: elapsed_time
       type: u4
       doc: 'in seconds'

     - id: not_used_2
       type: s1
       repeat: expr
       repeat-expr: 5

     - id: temperature_obc_1
       type: s1

     - id: temperature_obc_2
       type: s1

     - id: temperature_eps_p31u_1
       type: s1

     - id: temperature_eps_p31u_2
       type: s1

     - id: temperature_eps_p31u_3
       type: s1

     - id: temperature_eps_p31u_4
       type: s1

     - id: temperature_eps_bp4_1
       type: s1

     - id: temperature_eps_bp4_2
       type: s1

     - id: temperature_uhf_ax100_brd
       type: s1

     - id: temperature_uhf_ax100_pa
       type: s1

     - id: not_used_3
       type: b6

     - id: deploy_status_s_band_antenna
       type: b1

     - id: deploy_status_uhf_antenna
       type: b1

     - id: deploy_attempts_uhf
       type: u1

     - id: deploy_attempts_s_band
       type: u1

     - id: total_tx_data_volume
       type: u4

     - id: total_rx_data_volume
       type: u4

     - id: end_id
       type: str
       encoding: UTF-8
       size: 5
       valid: '"<RONE"'


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


    estimated_attitude_q0:
     if: estimated_attitude_q0_check == estimated_attitude_q0_check
     value: estimated_attitude_q0_check

    estimated_attitude_q1:
     if: estimated_attitude_q1_check == estimated_attitude_q1_check
     value: estimated_attitude_q1_check

    estimated_attitude_q2:
     if: estimated_attitude_q2_check == estimated_attitude_q2_check
     value: estimated_attitude_q2_check

    estimated_attitude_q3:
     if: estimated_attitude_q2_check == estimated_attitude_q2_check
     value: estimated_attitude_q2_check

    estimated_gyro_bias_roll:
     if: estimated_gyro_bias_roll_check == estimated_gyro_bias_roll_check
     value: estimated_gyro_bias_roll_check

    estimated_gyro_bias_pitch:
     if: estimated_gyro_bias_pitch_check == estimated_gyro_bias_pitch_check
     value: estimated_gyro_bias_pitch_check

    estimated_gyro_bias_yaw:
     if: estimated_gyro_bias_yaw_check == estimated_gyro_bias_yaw_check
     value: estimated_gyro_bias_yaw_check

    estimated_angular_rate_roll:
     if: estimated_angular_rate_roll_check == estimated_angular_rate_roll_check
     value: estimated_angular_rate_roll_check

    estimated_angular_rate_pitch:
     if: estimated_angular_rate_pitch_check == estimated_angular_rate_pitch_check
     value: estimated_angular_rate_pitch_check

    estimated_angular_rate_yaw:
     if: estimated_angular_rate_yaw_check == estimated_angular_rate_yaw_check
     value: estimated_angular_rate_yaw_check

    measured_angular_rate_roll:
     if: measured_angular_rate_roll_check == measured_angular_rate_roll_check
     value: measured_angular_rate_roll_check

    measured_angular_rate_pitch:
     if: measured_angular_rate_pitch_check == measured_angular_rate_pitch_check
     value: measured_angular_rate_pitch_check

    measured_angular_rate_yaw:
     if: measured_angular_rate_yaw_check == measured_angular_rate_yaw_check
     value: measured_angular_rate_yaw_check


  simple:
   seq:
     - id: ax25_header
       type: u1
       repeat: expr
       repeat-expr: 16

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
       size: 4
       valid: '"SPI>"'

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
       size: 5
       valid: '"<RONE"'


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
