---
meta:
  id: snuglite3
  title: SNUGLITE-III Telemetry Decoder
  endian: be
doc-ref: https://gnss.snu.ac.kr/snuglite/251126/
# 2025-12-06, DL7NDR
doc: |
  :field destination_callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field source_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field csp_header_priority: payload.csp_header_priority
  :field csp_header_source: payload.csp_header_source
  :field csp_header_destination: payload.csp_header_destination
  :field csp_header_destination_port: payload.csp_header_destination_port
  :field csp_header_source_port: payload.csp_header_source_port
  :field csp_header_reserved: payload.csp_header_reserved
  :field csp_header_flags: payload.csp_header_flags

  :field last_telecommand_number: payload.last_telecommand_number
  :field telecommand_counter: payload.telecommand_counter
  :field gpstime_itow: payload.gpstime_itow
  :field gpstime_ftow: payload.gpstime_ftow
  :field position_flag: payload.position_flag
  :field position_x: payload.position_x
  :field position_y: payload.position_y
  :field position_z: payload.position_z
  :field velocity_x: payload.velocity_x
  :field velocity_y: payload.velocity_y
  :field velocity_z: payload.velocity_z
  :field battery_mode: payload.battery_mode
  :field battery_voltage: payload.battery_voltage
  :field target_altitude_q1: payload.target_altitude_q1
  :field target_altitude_q2: payload.target_altitude_q2
  :field target_altitude_q3: payload.target_altitude_q3
  :field estimated_altitude_q1: payload.estimated_altitude_q1
  :field estimated_altitude_q2: payload.estimated_altitude_q2
  :field estimated_altitude_q3: payload.estimated_altitude_q3
  :field estimated_angular_rate_roll: payload.estimated_angular_rate_roll
  :field estimated_angular_rate_pitch: payload.estimated_angular_rate_pitch
  :field estimated_angular_rate_yaw: payload.estimated_angular_rate_yaw
  :field sun_measurement_x: payload.sun_measurement_x
  :field sun_measurement_y: payload.sun_measurement_y
  :field sun_measurement_z: payload.sun_measurement_z
  :field relnav_mode: payload.relnav_mode
  :field ocs_mode: payload.ocs_mode
  :field ocs_mode_sate: payload.ocs_mode_sate
  :field target_relative_distance: payload.target_relative_distance
  :field current_relative_vector_x: payload.current_relative_vector_x
  :field current_relative_vector_y: payload.current_relative_vector_y
  :field current_relative_vector_z: payload.current_relative_vector_z
  :field current_relative_velocity_x: payload.current_relative_velocity_x
  :field current_relative_velocity_y: payload.current_relative_velocity_y
  :field current_relative_velocity_z: payload.current_relative_velocity_z
  :field operational_mode: payload.operational_mode
  :field deploy_flag: payload.deploy_flag
  :field satellite_time: payload.satellite_time

  :field page_active_bitmask: payload.full_beacon_page_number.page_number.page_active_bitmask
  :field battery_current: payload.full_beacon_page_number.page_number.battery_current
  :field power_switch_status_gps_0: payload.full_beacon_page_number.page_number.power_switch_status_gps_0
  :field power_switch_status_gps_1: payload.full_beacon_page_number.page_number.power_switch_status_gps_1
  :field power_switch_status_gps_2: payload.full_beacon_page_number.page_number.power_switch_status_gps_2
  :field power_switch_status_deploy: payload.full_beacon_page_number.page_number.power_switch_status_deploy
  :field power_switch_status_sub_trx: payload.full_beacon_page_number.page_number.power_switch_status_sub_trx
  :field power_switch_status_main_trx: payload.full_beacon_page_number.page_number.power_switch_status_main_trx
  :field power_switch_current_1: payload.full_beacon_page_number.page_number.power_switch_current_1
  :field power_switch_current_2: payload.full_beacon_page_number.page_number.power_switch_current_2
  :field power_switch_current_3: payload.full_beacon_page_number.page_number.power_switch_current_3
  :field power_switch_current_4: payload.full_beacon_page_number.page_number.power_switch_current_4
  :field power_switch_current_5: payload.full_beacon_page_number.page_number.power_switch_current_5
  :field power_switch_current_6: payload.full_beacon_page_number.page_number.power_switch_current_6
  :field solar_panel_input_voltage_z: payload.full_beacon_page_number.page_number.solar_panel_input_voltage_z
  :field solar_panel_input_voltage_y: payload.full_beacon_page_number.page_number.solar_panel_input_voltage_y
  :field solar_panel_input_voltage_deployed_panel: payload.full_beacon_page_number.page_number.solar_panel_input_voltage_deployed_panel
  :field solar_panel_input_current_z: payload.full_beacon_page_number.page_number.solar_panel_input_current_z
  :field solar_panel_input_current_y: payload.full_beacon_page_number.page_number.solar_panel_input_current_y
  :field solar_panel_input_current_deployed_panel: payload.full_beacon_page_number.page_number.solar_panel_input_current_deployed_panel
  :field mode_1: payload.full_beacon_page_number.page_number.mode_1
  :field mode_2: payload.full_beacon_page_number.page_number.mode_2
  :field mode_entry_time: payload.full_beacon_page_number.page_number.mode_entry_time
  :field dgps_relative_vector_x: payload.full_beacon_page_number.page_number.dgps_relative_vector_x
  :field dgps_relative_vector_y: payload.full_beacon_page_number.page_number.dgps_relative_vector_y
  :field dgps_relative_vector_z: payload.full_beacon_page_number.page_number.dgps_relative_vector_z
  :field raf_relative_vector_x: payload.full_beacon_page_number.page_number.raf_relative_vector_x
  :field raf_relative_vector_y: payload.full_beacon_page_number.page_number.raf_relative_vector_y
  :field raf_relative_vector_z: payload.full_beacon_page_number.page_number.raf_relative_vector_z
  :field rtk_relative_vector_x: payload.full_beacon_page_number.page_number.rtk_relative_vector_x
  :field rtk_relative_vector_y: payload.full_beacon_page_number.page_number.rtk_relative_vector_y
  :field rtk_relative_vector_z: payload.full_beacon_page_number.page_number.rtk_relative_vector_z
  :field id2: payload.full_beacon_page_number.page_number.id2
  :field page_type: payload.full_beacon_page_number.page_number.page_type

  :field page_active_bitmask: payload.full_beacon_page_number.page_number.page_active_bitmask
  :field star_tracker_q1: payload.full_beacon_page_number.page_number.star_tracker_q1
  :field star_tracker_q2: payload.full_beacon_page_number.page_number.star_tracker_q2
  :field star_tracker_q3: payload.full_beacon_page_number.page_number.star_tracker_q3
  :field gyroscope_x: payload.full_beacon_page_number.page_number.gyroscope_x
  :field gyroscope_y: payload.full_beacon_page_number.page_number.gyroscope_y
  :field gyroscope_z: payload.full_beacon_page_number.page_number.gyroscope_z
  :field magnetometer_x: payload.full_beacon_page_number.page_number.magnetometer_x
  :field magnetometer_y: payload.full_beacon_page_number.page_number.magnetometer_y
  :field magnetometer_z: payload.full_beacon_page_number.page_number.magnetometer_z
  :field estimated_gyro_bias_roll: payload.full_beacon_page_number.page_number.estimated_gyro_bias_roll
  :field estimated_gyro_bias_pitch: payload.full_beacon_page_number.page_number.estimated_gyro_bias_pitch
  :field estimated_gyro_bias_yaw: payload.full_beacon_page_number.page_number.estimated_gyro_bias_yaw
  :field reaction_wheel_speed_x: payload.full_beacon_page_number.page_number.reaction_wheel_speed_x
  :field reaction_wheel_speed_y: payload.full_beacon_page_number.page_number.reaction_wheel_speed_y
  :field reaction_wheel_speed_z: payload.full_beacon_page_number.page_number.reaction_wheel_speed_z
  :field external_panel_plus_x: payload.full_beacon_page_number.page_number.external_panel_plus_x
  :field external_panel_plus_y: payload.full_beacon_page_number.page_number.external_panel_plus_y
  :field external_panel_minus_y: payload.full_beacon_page_number.page_number.external_panel_minus_y
  :field external_panel_plus_z: payload.full_beacon_page_number.page_number.external_panel_plus_z
  :field external_panel_minus_z: payload.full_beacon_page_number.page_number.external_panel_minus_z
  :field obc_main_1: payload.full_beacon_page_number.page_number.obc_main_1
  :field obc_main_2: payload.full_beacon_page_number.page_number.obc_main_2
  :field obc_sub_1: payload.full_beacon_page_number.page_number.obc_sub_1
  :field obc_sub_2: payload.full_beacon_page_number.page_number.obc_sub_2
  :field eps_board_1: payload.full_beacon_page_number.page_number.eps_board_1
  :field eps_board_2: payload.full_beacon_page_number.page_number.eps_board_2
  :field eps_board_3: payload.full_beacon_page_number.page_number.eps_board_3
  :field eps_board_4: payload.full_beacon_page_number.page_number.eps_board_4
  :field eps_battery_1: payload.full_beacon_page_number.page_number.eps_battery_1
  :field eps_battery_2: payload.full_beacon_page_number.page_number.eps_battery_2
  :field obc_gpio_1: payload.full_beacon_page_number.page_number.obc_gpio_1
  :field obc_gpio_2: payload.full_beacon_page_number.page_number.obc_gpio_2
  :field obc_pwm: payload.full_beacon_page_number.page_number.obc_pwm
  :field relnav_flag_1: payload.full_beacon_page_number.page_number.relnav_flag_1
  :field relnav_flag_2: payload.full_beacon_page_number.page_number.relnav_flag_2
  :field relnav_flag_3: payload.full_beacon_page_number.page_number.relnav_flag_3
  :field id2: payload.full_beacon_page_number.page_number.id2
  :field page_type: payload.full_beacon_page_number.page_number.page_type

seq:
  - id: ax25_frame
    type: ax25_frame
  - id: payload
    type: payload


types:
  ax25_frame:
    seq:
      - id: ax25_header
        type: ax25_header

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
        type: u1
      - id: pid
        type: u1

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
        valid:
          any-of:
            - '"DS0DH"'
            - '"DS0DH "'
            - '"DS0DH0"' # for ground testing only

  ssid_mask:
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x1f) >> 1



  payload:
    seq:
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

     - id: id1
       type: str
       encoding: UTF-8
       size: 7
       valid: '"SNUGL3>"'

     - id: last_telecommand_number
       type: u1

     - id: telecommand_counter
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

     - id: gpstime_itow
       type: s4

     - id: gpstime_ftow
       type: s4

     - id: position_flag
       type: u1

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

     - id: target_altitude_q1
       type: s2

     - id: target_altitude_q2
       type: s2

     - id: target_altitude_q3
       type: s2

     - id: estimated_altitude_q1
       type: s2

     - id: estimated_altitude_q2
       type: s2

     - id: estimated_altitude_q3
       type: s2

     - id: estimated_angular_rate_roll
       type: f4

     - id: estimated_angular_rate_pitch
       type: f4

     - id: estimated_angular_rate_yaw
       type: f4

     - id: sun_measurement_x
       type: s2

     - id: sun_measurement_y
       type: s2

     - id: sun_measurement_z
       type: s2

     - id: relnav_mode
       type: u1

     - id: ocs_mode
       type: u1

     - id: ocs_mode_sate
       type: u1

     - id: target_relative_distance
       type: s2

     - id: current_relative_vector_x
       type: f4

     - id: current_relative_vector_y
       type: f4

     - id: current_relative_vector_z
       type: f4

     - id: current_relative_velocity_x
       type: f4

     - id: current_relative_velocity_y
       type: f4

     - id: current_relative_velocity_z
       type: f4

     - id: operational_mode
       type: b3le
       doc: '0=initial, 1=standby'

     - id: skipping_rest_2
       type: b5

     - id: deploy_flag
       type: u1

     - id: full_beacon_page_number
       type: full_beacon_page_number_t

    instances:
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



  full_beacon_page_number_t:
    seq:
      - id: page_number
        type:
          switch-on: check
          cases:
            0b00: page1
            0b01: page2

    instances:
      check:
        type: b2le


  page1:
    seq:
     - id: page_active_bitmask
       type: b4le

     - id: skipping_rest_0
       type: b2

     - id: battery_current
       type: u2

     - id: power_switch_status_gps_0
       type: b1le

     - id: power_switch_status_gps_1
       type: b1le

     - id: power_switch_status_gps_2
       type: b1le

     - id: power_switch_status_deploy
       type: b1le

     - id: power_switch_status_sub_trx
       type: b1le

     - id: power_switch_status_main_trx
       type: b1le

     - id: skipping_rest_1
       type: b2

     - id: power_switch_current_1
       type: u2

     - id: power_switch_current_2
       type: u2

     - id: power_switch_current_3
       type: u2

     - id: power_switch_current_4
       type: u2

     - id: power_switch_current_5
       type: u2

     - id: power_switch_current_6
       type: u2

     - id: solar_panel_input_voltage_z
       type: u2

     - id: solar_panel_input_voltage_y
       type: u2

     - id: solar_panel_input_voltage_deployed_panel
       type: u2

     - id: solar_panel_input_current_z
       type: u2

     - id: solar_panel_input_current_y
       type: u2

     - id: solar_panel_input_current_deployed_panel
       type: u2

     - id: mode_1
       type: u1

     - id: mode_2
       type: u1

     - id: mode_entry_time
       type: u4

     - id: dgps_relative_vector_x
       type: f4

     - id: dgps_relative_vector_y
       type: f4

     - id: dgps_relative_vector_z
       type: f4

     - id: raf_relative_vector_x
       type: f4

     - id: raf_relative_vector_y
       type: f4

     - id: raf_relative_vector_z
       type: f4

     - id: rtk_relative_vector_x
       type: f4

     - id: rtk_relative_vector_y
       type: f4

     - id: rtk_relative_vector_z
       type: f4

     - id: id2
       type: str
       encoding: UTF-8
       size: 5
       valid:
         any-of:
           - '"<HANA"'
           - '"<DURI"'

     - id: skipping_last_byte
       type: u1

    instances:
        page_type:
              value:  '0 == 0 ? "1" : "1"'

  page2:
    seq:
     - id: page_active_bitmask
       type: b4le

     - id: skipping_rest
       type: b2

     - id: star_tracker_q1
       type: s2

     - id: star_tracker_q2
       type: s2

     - id: star_tracker_q3
       type: s2

     - id: gyroscope_x
       type: f4

     - id: gyroscope_y
       type: f4

     - id: gyroscope_z
       type: f4

     - id: magnetometer_x
       type: f4

     - id: magnetometer_y
       type: f4

     - id: magnetometer_z
       type: f4

     - id: estimated_gyro_bias_roll
       type: f4

     - id: estimated_gyro_bias_pitch
       type: f4

     - id: estimated_gyro_bias_yaw
       type: f4

     - id: reaction_wheel_speed_x
       type: s2

     - id: reaction_wheel_speed_y
       type: s2

     - id: reaction_wheel_speed_z
       type: s2

     - id: external_panel_plus_x
       type: u1

     - id: external_panel_plus_y
       type: u1

     - id: external_panel_minus_y
       type: u1

     - id: external_panel_plus_z
       type: u1

     - id: external_panel_minus_z
       type: u1

     - id: obc_main_1
       type: u1

     - id: obc_main_2
       type: u1

     - id: obc_sub_1
       type: u1

     - id: obc_sub_2
       type: u1

     - id: eps_board_1
       type: u1

     - id: eps_board_2
       type: u1

     - id: eps_board_3
       type: u1

     - id: eps_board_4
       type: u1

     - id: eps_battery_1
       type: u1

     - id: eps_battery_2
       type: u1

     - id: obc_gpio_1
       type: u1

     - id: obc_gpio_2
       type: u1

     - id: obc_pwm
       type: u1

     - id: relnav_flag_1
       type: u1

     - id: relnav_flag_2
       type: u1

     - id: relnav_flag_3
       type: u1

     - id: id2
       type: str
       encoding: UTF-8
       size: 5
       valid:
         any-of:
           - '"<HANA"'
           - '"<DURI"'

     - id: skipping_last_byte
       type: u1

    instances:
        page_type:
              value:  '0 == 0 ? "2" : "2"'
