meta:
  id: dora
  endian: be # Default big endian
doc: |
  :field openlst_header_uart_start_seq: uart_start_seq
  :field openlst_header_packet_size: packet_size
  :field openlst_header_destination_hwid: destination_hwid
  :field openlst_header_sequence_number: sequence_number
  :field openlst_header_system_byte: system_byte
  :field callsign: callsign
  :field ccsds_version: ccsds_frame.ccsds_header.ccsds_version
  :field ccsds_packet_type: ccsds_frame.ccsds_header.packet_type
  :field ccsds_secondary_header_flag: ccsds_frame.ccsds_header.secondary_header_flag
  :field ccsds_apid: ccsds_frame.ccsds_header.apid
  :field ccsds_sequence_flags: ccsds_frame.ccsds_header.sequence_flags
  :field ccsds_sequence_count: ccsds_frame.ccsds_header.sequence_count
  :field ccsds_packet_length: ccsds_frame.ccsds_header.packet_length
  :field obc_timestamp: ccsds_frame.ccsds_data.timestamp
  :field obc_missionticks: ccsds_frame.ccsds_data.missionticks
  :field obc_state: ccsds_frame.ccsds_data.state
  :field obc_received_packets: ccsds_frame.ccsds_data.received_packets
  :field obc_last_logged_error_thread: ccsds_frame.ccsds_data.last_logged_error_thread
  :field obc_last_logged_error_code: ccsds_frame.ccsds_data.last_logged_error_code
  :field obc_obc_reboot_count: ccsds_frame.ccsds_data.obc_reboot_count
  :field adcs_adcs_commissioning_done_flag: ccsds_frame.ccsds_data.adcs_telemetry.adcs_commissioning_done_flag
  :field adcs_adcs_current_commissioning_state: ccsds_frame.ccsds_data.adcs_telemetry.adcs_current_commissioning_state
  :field adcs_boot_status: ccsds_frame.ccsds_data.adcs_telemetry.boot_status
  :field adcs_boot_count: ccsds_frame.ccsds_data.adcs_telemetry.boot_count
  :field adcs_current_adcs_controlmode: ccsds_frame.ccsds_data.adcs_telemetry.current_adcs_controlmode
  :field adcs_current_adcs_attitudeestimation: ccsds_frame.ccsds_data.adcs_telemetry.current_adcs_attitudeestimation
  :field adcs_cubesense2_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubesense2_enabled
  :field adcs_cubesense1_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubesense1_enabled
  :field adcs_cubecontrolmotor_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubecontrolmotor_enabled
  :field adcs_cubecontrolsignal_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubecontrolsignal_enabled
  :field adcs_asgp4_mode: ccsds_frame.ccsds_data.adcs_telemetry.asgp4_mode
  :field adcs_currentadcs_adcs_run_mode: ccsds_frame.ccsds_data.adcs_telemetry.currentadcs_adcs_run_mode
  :field adcs_sun_is_above_local_horizon: ccsds_frame.ccsds_data.adcs_telemetry.sun_is_above_local_horizon
  :field adcs_motor_driver_enabled: ccsds_frame.ccsds_data.adcs_telemetry.motor_driver_enabled
  :field adcs_gps_lna_power_enabled: ccsds_frame.ccsds_data.adcs_telemetry.gps_lna_power_enabled
  :field adcs_gps_receiver_enable: ccsds_frame.ccsds_data.adcs_telemetry.gps_receiver_enable
  :field adcs_cubestar_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubestar_enabled
  :field adcs_cubewheel3_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubewheel3_enabled
  :field adcs_cubewheel2_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubewheel2_enabled
  :field adcs_cubewheel1_enabled: ccsds_frame.ccsds_data.adcs_telemetry.cubewheel1_enabled
  :field adcs_cubestar_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubestar_comms_error
  :field adcs_cubewheel3_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubewheel3_comms_error
  :field adcs_cubewheel2_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubewheel2_comms_error
  :field adcs_cubewheel1_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubewheel1_comms_error
  :field adcs_cubecontrol_motor_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubecontrol_motor_comms_error
  :field adcs_cubecontrol_signal_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubecontrol_signal_comms_error
  :field adcs_cubesense2_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubesense2_comms_error
  :field adcs_cubesense1_comms_error: ccsds_frame.ccsds_data.adcs_telemetry.cubesense1_comms_error
  :field adcs_cam2_3v3_overcurrent_detected: ccsds_frame.ccsds_data.adcs_telemetry.cam2_3v3_overcurrent_detected
  :field adcs_cam2_sram_overcurrent_detected: ccsds_frame.ccsds_data.adcs_telemetry.cam2_sram_overcurrent_detected
  :field adcs_sun_sensor_range_error: ccsds_frame.ccsds_data.adcs_telemetry.sun_sensor_range_error
  :field adcs_cam1_sensor_detection_error: ccsds_frame.ccsds_data.adcs_telemetry.cam1_sensor_detection_error
  :field adcs_cam1_sensor_busy_error: ccsds_frame.ccsds_data.adcs_telemetry.cam1_sensor_busy_error
  :field adcs_cam1_3v3_overcurrent_detected: ccsds_frame.ccsds_data.adcs_telemetry.cam1_3v3_overcurrent_detected
  :field adcs_cam1_sram_overcurrent_detected: ccsds_frame.ccsds_data.adcs_telemetry.cam1_sram_overcurrent_detected
  :field adcs_magnetometer_range_error: ccsds_frame.ccsds_data.adcs_telemetry.magnetometer_range_error
  :field adcs_star_tracker_overcurrent_detected: ccsds_frame.ccsds_data.adcs_telemetry.star_tracker_overcurrent_detected
  :field adcs_startracker_match_error: ccsds_frame.ccsds_data.adcs_telemetry.startracker_match_error
  :field adcs_coarse_sun_sensor_error: ccsds_frame.ccsds_data.adcs_telemetry.coarse_sun_sensor_error
  :field adcs_wheel_speed_range_error: ccsds_frame.ccsds_data.adcs_telemetry.wheel_speed_range_error
  :field adcs_rate_sensor_range_error: ccsds_frame.ccsds_data.adcs_telemetry.rate_sensor_range_error
  :field adcs_nadir_sensor_range_error: ccsds_frame.ccsds_data.adcs_telemetry.nadir_sensor_range_error
  :field adcs_cam2_sensor_detection_error: ccsds_frame.ccsds_data.adcs_telemetry.cam2_sensor_detection_error
  :field adcs_cam2_sensor_busy_error: ccsds_frame.ccsds_data.adcs_telemetry.cam2_sensor_busy_error
  :field adcs_cubecontrl_cur_3v3: ccsds_frame.ccsds_data.adcs_telemetry.cubecontrl_cur_3v3
  :field adcs_cubecontrl_cur_5v: ccsds_frame.ccsds_data.adcs_telemetry.cubecontrl_cur_5v
  :field adcs_cubecontrol_cur_vbat: ccsds_frame.ccsds_data.adcs_telemetry.cubecontrol_cur_vbat
  :field adcs_fine_est_ang_rates_x: ccsds_frame.ccsds_data.adcs_telemetry.fine_est_ang_rates_x
  :field adcs_fine_est_ang_rates_y: ccsds_frame.ccsds_data.adcs_telemetry.fine_est_ang_rates_y
  :field adcs_fine_est_ang_rates_z: ccsds_frame.ccsds_data.adcs_telemetry.fine_est_ang_rates_z
  :field adcs_fine_sv_x: ccsds_frame.ccsds_data.adcs_telemetry.fine_sv_x
  :field adcs_fine_sv_y: ccsds_frame.ccsds_data.adcs_telemetry.fine_sv_y
  :field adcs_fine_sv_z: ccsds_frame.ccsds_data.adcs_telemetry.fine_sv_z
  :field adcs_mcu_temp: ccsds_frame.ccsds_data.adcs_telemetry.mcu_temp
  :field adcs_temp_mag: ccsds_frame.ccsds_data.adcs_telemetry.temp_mag
  :field adcs_temp_redmag: ccsds_frame.ccsds_data.adcs_telemetry.temp_redmag
  :field adcs_wheel1_current: ccsds_frame.ccsds_data.adcs_telemetry.wheel1_current
  :field adcs_wheel2_current: ccsds_frame.ccsds_data.adcs_telemetry.wheel2_current
  :field adcs_wheel3_current: ccsds_frame.ccsds_data.adcs_telemetry.wheel3_current
  :field adcs_magnetorquer_current: ccsds_frame.ccsds_data.adcs_telemetry.magnetorquer_current
  :field adcs_cubesenes1_3v3_current: ccsds_frame.ccsds_data.adcs_telemetry.cubesenes1_3v3_current
  :field adcs_cubesenes1_sram_current: ccsds_frame.ccsds_data.adcs_telemetry.cubesenes1_sram_current
  :field adcs_cubesenes2_3v3_current: ccsds_frame.ccsds_data.adcs_telemetry.cubesenes2_3v3_current
  :field adcs_cubesenes2_sram_current: ccsds_frame.ccsds_data.adcs_telemetry.cubesenes2_sram_current
  :field eps_output_voltage_battery: ccsds_frame.ccsds_data.eps_telemetry.output_voltage_battery
  :field eps_output_current_battery: ccsds_frame.ccsds_data.eps_telemetry.output_current_battery
  :field eps_bcr_output_current: ccsds_frame.ccsds_data.eps_telemetry.bcr_output_current
  :field eps_motherboard_temperature: ccsds_frame.ccsds_data.eps_telemetry.motherboard_temperature
  :field eps_actual_pdm_states_unused: ccsds_frame.ccsds_data.eps_telemetry.actual_pdm_states_unused
  :field eps_sdr_actual_switch_state: ccsds_frame.ccsds_data.eps_telemetry.sdr_actual_switch_state
  :field eps_cm4_pdm_actual_switch_state: ccsds_frame.ccsds_data.eps_telemetry.cm4_pdm_actual_switch_state
  :field eps_sipm_pdm_actual_switch_state: ccsds_frame.ccsds_data.eps_telemetry.sipm_pdm_actual_switch_state
  :field eps_pdm_actual_switch_state_unused2: ccsds_frame.ccsds_data.eps_telemetry.pdm_actual_switch_state_unused2
  :field eps_daughterboard_temperature: ccsds_frame.ccsds_data.eps_telemetry.daughterboard_temperature
  :field eps_output_current_5v: ccsds_frame.ccsds_data.eps_telemetry.output_current_5v
  :field eps_output_voltage_5v: ccsds_frame.ccsds_data.eps_telemetry.output_voltage_5v
  :field eps_output_current_3v3: ccsds_frame.ccsds_data.eps_telemetry.output_current_3v3
  :field eps_output_voltage_3v3: ccsds_frame.ccsds_data.eps_telemetry.output_voltage_3v3
  :field eps_output_voltage_switch_5: ccsds_frame.ccsds_data.eps_telemetry.output_voltage_switch_5
  :field eps_output_current_switch_5: ccsds_frame.ccsds_data.eps_telemetry.output_current_switch_5
  :field eps_output_voltage_switch_6: ccsds_frame.ccsds_data.eps_telemetry.output_voltage_switch_6
  :field eps_output_current_switch_6: ccsds_frame.ccsds_data.eps_telemetry.output_current_switch_6
  :field eps_output_voltage_switch_7: ccsds_frame.ccsds_data.eps_telemetry.output_voltage_switch_7
  :field eps_output_current_switch_7: ccsds_frame.ccsds_data.eps_telemetry.output_current_switch_7
  :field eps_voltage_feeding_bcr6: ccsds_frame.ccsds_data.eps_telemetry.voltage_feeding_bcr6
  :field eps_current_bcr6_connector_sa6a: ccsds_frame.ccsds_data.eps_telemetry.current_bcr6_connector_sa6a
  :field eps_current_bcr6_connector_sa6b: ccsds_frame.ccsds_data.eps_telemetry.current_bcr6_connector_sa6b
  :field eps_voltage_feeding_bcr7: ccsds_frame.ccsds_data.eps_telemetry.voltage_feeding_bcr7
  :field eps_current_bcr7_connector_sa7a: ccsds_frame.ccsds_data.eps_telemetry.current_bcr7_connector_sa7a
  :field eps_current_bcr7_connector_sa7b: ccsds_frame.ccsds_data.eps_telemetry.current_bcr7_connector_sa7b
  :field eps_voltage_feeding_bcr8: ccsds_frame.ccsds_data.eps_telemetry.voltage_feeding_bcr8
  :field eps_current_bcr8_connector_sa8a: ccsds_frame.ccsds_data.eps_telemetry.current_bcr8_connector_sa8a
  :field eps_current_bcr8_connector_sa8b: ccsds_frame.ccsds_data.eps_telemetry.current_bcr8_connector_sa8b
  :field eps_voltage_feeding_bcr9: ccsds_frame.ccsds_data.eps_telemetry.voltage_feeding_bcr9
  :field eps_current_bcr9_connector_sa9a: ccsds_frame.ccsds_data.eps_telemetry.current_bcr9_connector_sa9a
  :field eps_current_bcr9_connector_sa9b: ccsds_frame.ccsds_data.eps_telemetry.current_bcr9_connector_sa9b
  :field battery_motherboard_temperature: ccsds_frame.ccsds_data.battery_telemetry.motherboard_temperature
  :field battery_output_voltage_battery: ccsds_frame.ccsds_data.battery_telemetry.output_voltage_battery
  :field battery_current_magnitude: ccsds_frame.ccsds_data.battery_telemetry.current_magnitude
  :field battery_daughter_temp1: ccsds_frame.ccsds_data.battery_telemetry.daughter_temp1
  :field battery_daughter_temp2: ccsds_frame.ccsds_data.battery_telemetry.daughter_temp2
  :field battery_daughter_temp3: ccsds_frame.ccsds_data.battery_telemetry.daughter_temp3
  :field battery_heater_status1: ccsds_frame.ccsds_data.battery_telemetry.heater_status1
  :field battery_heater_status2: ccsds_frame.ccsds_data.battery_telemetry.heater_status2
  :field battery_heater_status3: ccsds_frame.ccsds_data.battery_telemetry.heater_status3
  :field battery_current_direction: ccsds_frame.ccsds_data.battery_telemetry.current_direction
  :field payload_sipm_adc_value: ccsds_frame.ccsds_data.payload_telemetry_1.sipm_adc_value
  :field payload_current_payload_schedule: ccsds_frame.ccsds_data.payload_telemetry_1.current_payload_schedule
  :field payload_timestamp: ccsds_frame.ccsds_data.payload_telemetry_1.timestamp
  :field payload_mode: ccsds_frame.ccsds_data.payload_telemetry_1.mode
  :field payload_available_storage: ccsds_frame.ccsds_data.payload_telemetry_1.available_storage
  :field payload_available_memory: ccsds_frame.ccsds_data.payload_telemetry_1.available_memory
  :field payload_cpu_load: ccsds_frame.ccsds_data.payload_telemetry_1.cpu_load
  :field payload_rpi_uptime: ccsds_frame.ccsds_data.payload_telemetry_1.rpi_uptime
  :field payload_reboot_count: ccsds_frame.ccsds_data.payload_telemetry_1.reboot_count
  :field payload_number_of_received_commands: ccsds_frame.ccsds_data.payload_telemetry_1.number_of_received_commands
  :field payload_last_received_command: ccsds_frame.ccsds_data.payload_telemetry_1.last_received_command
  :field payload_error_count: ccsds_frame.ccsds_data.payload_telemetry_1.error_count
  :field payload_filter_bank_power_ch1: ccsds_frame.ccsds_data.payload_telemetry_1.filter_bank_power_ch1
  :field payload_filter_bank_power_ch2: ccsds_frame.ccsds_data.payload_telemetry_1.filter_bank_power_ch2
  :field payload_filter_bank_power_ch2: ccsds_frame.ccsds_data.payload_telemetry_2.filter_bank_power_ch3
  :field payload_filter_bank_power_ch4: ccsds_frame.ccsds_data.payload_telemetry_2.filter_bank_power_ch4
  :field payload_filter_bank_power_ch5: ccsds_frame.ccsds_data.payload_telemetry_2.filter_bank_power_ch5
  :field payload_filter_bank_power_ch6: ccsds_frame.ccsds_data.payload_telemetry_2.filter_bank_power_ch6
  :field payload_filter_bank_power_ch7: ccsds_frame.ccsds_data.payload_telemetry_2.filter_bank_power_ch7
  :field payload_filter_bank_power_ch8: ccsds_frame.ccsds_data.payload_telemetry_2.filter_bank_power_ch8
  :field payload_sdr_power: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_power
  :field payload_sdr_bright_1: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_1
  :field payload_sdr_bright_2: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_2
  :field payload_sdr_bright_3: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_3
  :field payload_sdr_bright_4: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_4
  :field payload_sdr_bright_5: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_5
  :field payload_sdr_bright_6: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_6
  :field payload_sdr_bright_7: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_7
  :field payload_sdr_bright_8: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_8
  :field payload_sdr_bright_9: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_9
  :field payload_sdr_bright_10: ccsds_frame.ccsds_data.payload_telemetry_2.sdr_bright_10
seq:
  - id: uart_start_seq
    type: u2
  - id: packet_size
    type: u1
  - id: destination_hwid
    type: u2
  - id: sequence_number
    type: u2
  - id: system_byte
    type: u1
  - id: callsign
    type: str
    encoding: ASCII
    size: 6
    valid:
      any-of:
        - '"KE7DHQ"'
  - id: dora_syncbytes
    contents: [0x35, 0x2e, 0xf8, 0x53]
  - id: ccsds_frame
    type: ccsds_frame

types:
  ccsds_frame:
    seq:
      - id: ccsds_header
        type: ccsds_header
      - id: ccsds_data
        type: 
          switch-on: ccsds_header.sequence_flags
          cases:
            1: first_dora_packet
            2: second_dora_packet


  ccsds_header:
      seq:
        - id: ccsds_version
          type: b3
        - id: packet_type
          type: b1
        - id: secondary_header_flag
          type: b1
        - id: apid
          type: b11
          valid:
            any-of:
              - '3'
        - id: sequence_flags
          type: b2
        - id: sequence_count
          type: b14
        - id: packet_length
          type: b16

  first_dora_packet:
    seq:
      - id: timestamp
        type: u8
      - id: missionticks_raw
        type: u8
        doc: |
          Applying a 48bits mask on it because
          InfluxDB doesn t support uint64, only int64.
          So we need to put a limitation on the max value
          on fields with u8 types.
      - id: state
        type: u1
      - id: received_packets
        type: u4
      - id: last_logged_error_thread
        type: u1
      - id: last_logged_error_code
        type: u1
      - id: obc_reboot_count
        type: u4

      - id: adcs_telemetry
        type: adcs_telemetry
      - id: eps_telemetry
        type: eps_telemetry
      - id: battery_telemetry
        type: battery_telemetry
      - id: payload_telemetry_1
        type: payload_telemetry_1

    instances:
      missionticks:
        value: 'missionticks_raw & 0xFFFFFFFFFFFF'

  adcs_telemetry:
    seq:
      - id: adcs_commissioning_done_flag
        type: b1
      - id: adcs_current_commissioning_state
        type: b7
      - id: boot_status
        type: u1
      - id: boot_count
        type: u2
      - id: current_adcs_controlmode
        type: b4
      - id: current_adcs_attitudeestimation
        type: b4
      - id: cubesense2_enabled
        type: b1
      - id: cubesense1_enabled
        type: b1
      - id: cubecontrolmotor_enabled
        type: b1
      - id: cubecontrolsignal_enabled
        type: b1
      - id: asgp4_mode
        type: b2
      - id: currentadcs_adcs_run_mode
        type: b2
      - id: sun_is_above_local_horizon
        type: b1
      - id: motor_driver_enabled
        type: b1
      - id: gps_lna_power_enabled
        type: b1
      - id: gps_receiver_enable
        type: b1
      - id: cubestar_enabled
        type: b1
      - id: cubewheel3_enabled
        type: b1
      - id: cubewheel2_enabled
        type: b1
      - id: cubewheel1_enabled
        type: b1
      - id: cubestar_comms_error
        type: b1
      - id: cubewheel3_comms_error
        type: b1
      - id: cubewheel2_comms_error
        type: b1
      - id: cubewheel1_comms_error
        type: b1
      - id: cubecontrol_motor_comms_error
        type: b1
      - id: cubecontrol_signal_comms_error
        type: b1
      - id: cubesense2_comms_error
        type: b1
      - id: cubesense1_comms_error
        type: b1
      - id: cam2_3v3_overcurrent_detected
        type: b1
      - id: cam2_sram_overcurrent_detected
        type: b1
      - id: sun_sensor_range_error
        type: b1
      - id: cam1_sensor_detection_error
        type: b1
      - id: cam1_sensor_busy_error
        type: b1
      - id: cam1_3v3_overcurrent_detected
        type: b1
      - id: cam1_sram_overcurrent_detected
        type: b1
      - id: magnetometer_range_error
        type: b1
      - id: star_tracker_overcurrent_detected
        type: b1
      - id: startracker_match_error
        type: b1
      - id: coarse_sun_sensor_error
        type: b1
      - id: wheel_speed_range_error
        type: b1
      - id: rate_sensor_range_error
        type: b1
      - id: nadir_sensor_range_error
        type: b1
      - id: cam2_sensor_detection_error
        type: b1
      - id: cam2_sensor_busy_error
        type: b1

      - id: cubecontrl_cur_3v3_raw
        type: u2le
      - id: cubecontrl_cur_5v_raw
        type: u2le
      - id: cubecontrol_cur_vbat_raw
        type: u2le
      - id: fine_est_ang_rates_x_raw
        type: u2le
      - id: fine_est_ang_rates_y_raw
        type: u2le
      - id: fine_est_ang_rates_z_raw
        type: u2le
      - id: fine_sv_x_raw
        type: u2le
      - id: fine_sv_y_raw
        type: u2le
      - id: fine_sv_z_raw
        type: u2le
      - id: mcu_temp
        type: u2le
      - id: temp_mag_raw
        type: u2le
      - id: temp_redmag_raw
        type: u2le
      - id: wheel1_current_raw
        type: u2le
      - id: wheel2_current_raw
        type: u2le
      - id: wheel3_current_raw
        type: u2le
      - id: magnetorquer_current_raw
        type: u2le
      - id: cubesenes1_3v3_current_raw
        type: u2le
      - id: cubesenes1_sram_current_raw
        type: u2le
      - id: cubesenes2_3v3_current_raw
        type: u2le
      - id: cubesenes2_sram_current_raw
        type: u2le
    instances:
      cubecontrl_cur_3v3:
        value: cubecontrl_cur_3v3_raw * 0.48828125
      cubecontrl_cur_5v:
        value: cubecontrl_cur_5v_raw * 0.48828125
      cubecontrol_cur_vbat:
        value: cubecontrol_cur_vbat_raw * 0.48828125
      fine_est_ang_rates_x:
        value: fine_est_ang_rates_x_raw * 0.001
      fine_est_ang_rates_y:
        value: fine_est_ang_rates_y_raw * 0.001
      fine_est_ang_rates_z:
        value: fine_est_ang_rates_z_raw * 0.001
      fine_sv_x:
        value: fine_sv_x_raw * 0.0001
      fine_sv_y:
        value: fine_sv_y_raw * 0.0001
      fine_sv_z:
        value: fine_sv_z_raw * 0.0001
      temp_mag:
        value: temp_mag_raw * 0.1
      temp_redmag:
        value: temp_redmag_raw * 0.1
      wheel1_current:
        value: wheel1_current_raw * 0.01
      wheel2_current:
        value: wheel2_current_raw * 0.01
      wheel3_current:
        value: wheel3_current_raw * 0.01
      magnetorquer_current:
        value: magnetorquer_current_raw * 0.01
      cubesenes1_3v3_current:
        value: cubesenes1_3v3_current_raw * 0.01
      cubesenes1_sram_current:
        value: cubesenes1_sram_current_raw * 0.01
      cubesenes2_3v3_current:
        value: cubesenes2_3v3_current_raw * 0.01
      cubesenes2_sram_current:
        value: cubesenes2_sram_current_raw * 0.01


  eps_telemetry:
    seq:
      - id: output_voltage_battery_raw
        type: u2
      - id: output_current_battery_raw
        type: u2
      - id: bcr_output_current_raw
        type: u2
      - id: motherboard_temperature_raw
        type: u2
      - id: actual_pdm_states_unused
        type: b8
      - id: sdr_actual_switch_state
        type: b1
      - id: cm4_pdm_actual_switch_state
        type: b1
      - id: sipm_pdm_actual_switch_state
        type: b1
      - id: pdm_actual_switch_state_unused2
        type: b5
      - id: daughterboard_temperature_raw
        type: u2
      - id: output_current_5v_raw
        type: u2
      - id: output_voltage_5v_raw
        type: u2
      - id: output_current_3v3_raw
        type: u2
      - id: output_voltage_3v3_raw
        type: u2
      - id: output_voltage_switch_5_raw
        type: u2
      - id: output_current_switch_5_raw
        type: u2
      - id: output_voltage_switch_6_raw
        type: u2
      - id: output_current_switch_6_raw
        type: u2
      - id: output_voltage_switch_7_raw
        type: u2
      - id: output_current_switch_7_raw
        type: u2
      - id: voltage_feeding_bcr6_raw
        type: u2
      - id: current_bcr6_connector_sa6a_raw
        type: u2
      - id: current_bcr6_connector_sa6b_raw
        type: u2
      - id: voltage_feeding_bcr7_raw
        type: u2
      - id: current_bcr7_connector_sa7a_raw
        type: u2
      - id: current_bcr7_connector_sa7b_raw
        type: u2
      - id: voltage_feeding_bcr8_raw
        type: u2
      - id: current_bcr8_connector_sa8a_raw
        type: u2
      - id: current_bcr8_connector_sa8b_raw
        type: u2
      - id: voltage_feeding_bcr9_raw
        type: u2
      - id: current_bcr9_connector_sa9a_raw
        type: u2
      - id: current_bcr9_connector_sa9b_raw
        type: u2
    instances:
      output_voltage_battery:
        value: output_voltage_battery_raw * 0.008978
      output_current_battery:
        value: output_current_battery_raw * 0.00681988679
      bcr_output_current:
        value: bcr_output_current_raw * 0.014662757
      motherboard_temperature:
        value: motherboard_temperature_raw * 0.372434 - 273.15
      daughterboard_temperature:
        value: motherboard_temperature_raw * 0.372434 - 273.15
      output_current_5v:
        value: output_current_5v_raw * 0.00681988679
      output_voltage_5v:
        value: output_voltage_5v_raw * 0.005865
      output_current_3v3:
        value: output_current_3v3_raw * 0.00681988679
      output_voltage_3v3:
        value: output_voltage_3v3_raw * 0.004311
      output_voltage_switch_5:
        value: output_voltage_switch_5_raw * 0.005865
      output_current_switch_5:
        value: output_current_switch_5_raw * 0.001328
      output_voltage_switch_6:
        value: output_voltage_switch_6_raw * 0.005865
      output_current_switch_6:
        value: output_current_switch_6_raw * 0.001328
      output_voltage_switch_7:
        value: output_voltage_switch_7_raw * 0.005865
      output_current_switch_7:
        value: output_current_switch_7_raw * 0.001328
      voltage_feeding_bcr6:
        value: voltage_feeding_bcr6_raw * 0.0322581
      current_bcr6_connector_sa6a:
        value: current_bcr6_connector_sa6a_raw * 0.0009775
      current_bcr6_connector_sa6b:
        value: current_bcr6_connector_sa6b_raw * 0.0009775
      voltage_feeding_bcr7:
        value: voltage_feeding_bcr7_raw * 0.0322581
      current_bcr7_connector_sa7a:
        value: current_bcr7_connector_sa7a_raw * 0.0009775
      current_bcr7_connector_sa7b:
        value: current_bcr7_connector_sa7b_raw * 0.0009775
      voltage_feeding_bcr8:
        value: voltage_feeding_bcr8_raw * 0.0322581
      current_bcr8_connector_sa8a:
        value: current_bcr8_connector_sa8a_raw * 0.0009775
      current_bcr8_connector_sa8b:
        value: current_bcr8_connector_sa8b_raw * 0.0009775
      voltage_feeding_bcr9:
        value: voltage_feeding_bcr9_raw * 0.0322581
      current_bcr9_connector_sa9a:
        value: current_bcr9_connector_sa9a_raw * 0.0009775
      current_bcr9_connector_sa9b:
        value: current_bcr9_connector_sa9b_raw * 0.0009775

  battery_telemetry:
    seq:
      - id: motherboard_temperature_raw
        type: u2
      - id: output_voltage_battery_raw
        type: u2 
      - id: current_magnitude_raw
        type: u2 
      - id: daughter_temp1_raw
        type: u2
      - id: daughter_temp2_raw
        type: u2
      - id: daughter_temp3_raw
        type: u2
      - id: heater_status1
        type: b1
      - id: heater_status2
        type: b1
      - id: heater_status3
        type: b1
      - id: current_direction
        type: b5
    instances:
      motherboard_temperature:
        value: motherboard_temperature_raw * 0.372434 - 273.15
      output_voltage_battery:
        value: output_voltage_battery_raw * 0.008993
      current_magnitude:
        value: current_magnitude_raw * 14.662757
      daughter_temp1:
        value: daughter_temp1_raw * 0.397600 - 238.57
      daughter_temp2:
        value: daughter_temp2_raw * 0.397600 - 238.57
      daughter_temp3:
        value: daughter_temp3_raw * 0.397600 - 238.57


  payload_telemetry_1:
    seq:
      - id: sipm_adc_value
        type: u2
      - id: current_payload_schedule
        type: u2
      - id: timestamp_raw
        type: u8
      - id: mode
        type: u1
      - id: available_storage
        type: u4
      - id: available_memory
        type: u4
      - id: cpu_load
        type: u4
      - id: rpi_uptime
        type: u4
      - id: reboot_count
        type: u4
      - id: number_of_received_commands
        type: u4
      - id: last_received_command
        type: u1
      - id: error_count
        type: u4
      - id: filter_bank_power_ch1
        type: u1
      - id: filter_bank_power_ch2
        type: u1
    instances:
        timestamp:
          value: 'timestamp_raw & 0xFFFFFFFF'

  second_dora_packet:
    seq:
      - id: payload_telemetry_2
        type: payload_telemetry_2

  payload_telemetry_2:
    seq:
      - id: filter_bank_power_ch3
        type: u1
      - id: filter_bank_power_ch4
        type: u1
      - id: filter_bank_power_ch5
        type: u1
      - id: filter_bank_power_ch6
        type: u1
      - id: filter_bank_power_ch7
        type: u1
      - id: filter_bank_power_ch8
        type: u1
      - id: sdr_power
        type: u2
      - id: sdr_bright_1
        type: u2
      - id: sdr_bright_2
        type: u2
      - id: sdr_bright_3
        type: u2
      - id: sdr_bright_4
        type: u2
      - id: sdr_bright_5
        type: u2
      - id: sdr_bright_6
        type: u2
      - id: sdr_bright_7
        type: u2
      - id: sdr_bright_8
        type: u2
      - id: sdr_bright_9
        type: u2
      - id: sdr_bright_10
        type: u2

