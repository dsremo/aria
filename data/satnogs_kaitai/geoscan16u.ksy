---
meta:
  id: geoscan16u
  title: Geoscan 16U platform beacon deocoder
  endian: le

doc: |
  :field callsign_start_str: data.ax25_header.dest_callsign_raw.callsign_ror.callsign_start.callsign_start_str
  :field callsign_end_str: data.ax25_header.dest_callsign_raw.callsign_ror.callsign_end.callsign_end_str
  :field ssid_mask: data.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: data.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign_start_str: data.ax25_header.src_callsign_raw.callsign_ror.callsign_start.callsign_start_str
  :field src_callsign_raw_callsign_end_str: data.ax25_header.src_callsign_raw.callsign_ror.callsign_end.callsign_end_str
  :field src_ssid_raw_ssid_mask: data.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: data.ax25_header.src_ssid_raw.ssid
  :field ctl: data.ax25_header.ctl
  :field pid: data.ax25_header.pid
  :field beacon_id: data.payload.beacon_id
  :field eps_1_mode: data.payload.eps_1_mode
  :field eps_1_consumption_current: data.payload.eps_1_consumption_current
  :field eps_1_solar_cells_current: data.payload.eps_1_solar_cells_current
  :field eps_1_cell_voltage_full: data.payload.eps_1_cell_voltage_full
  :field eps_1_battery_temperature: data.payload.eps_1_battery_temperature
  :field eps_1_temperature_sp_y_pos: data.payload.eps_1_temperature_sp_y_pos
  :field eps_1_temperature_sp_y_neg: data.payload.eps_1_temperature_sp_y_neg
  :field eps_1_temperature_sp_x_pos: data.payload.eps_1_temperature_sp_x_pos
  :field eps_1_temperature_sp_x_neg: data.payload.eps_1_temperature_sp_x_neg
  :field eps_1_systems_status: data.payload.eps_1_systems_status
  :field eps_1_boot_count: data.payload.eps_1_boot_count
  :field eps_2_mode: data.payload.eps_2_mode
  :field eps_2_consumption_current: data.payload.eps_2_consumption_current
  :field eps_2_solar_cells_current: data.payload.eps_2_solar_cells_current
  :field eps_2_cell_voltage_full: data.payload.eps_2_cell_voltage_full
  :field eps_2_battery_temperature: data.payload.eps_2_battery_temperature
  :field eps_2_temperature_sp_y_pos: data.payload.eps_2_temperature_sp_y_pos
  :field eps_2_temperature_sp_y_neg: data.payload.eps_2_temperature_sp_y_neg
  :field eps_2_temperature_sp_x_pos: data.payload.eps_2_temperature_sp_x_pos
  :field eps_2_temperature_sp_x_neg: data.payload.eps_2_temperature_sp_x_neg
  :field eps_2_systems_status: data.payload.eps_2_systems_status
  :field eps_2_boot_count: data.payload.eps_2_boot_count
  :field adcs_mt_mode: data.payload.adcs_mt_mode
  :field adcs_rm_mode: data.payload.adcs_rm_mode
  :field adcs_kf_mode: data.payload.adcs_kf_mode
  :field adcs_filter_reset_count: data.payload.adcs_filter_reset_count
  :field adcs_sensors_state: data.payload.adcs_sensors_state
  :field adcs_flywheel_state: data.payload.adcs_flywheel_state
  :field comm_type: data.payload.comm_type
  :field comm_vbus_voltage: data.payload.comm_vbus_voltage
  :field comm_boot_count: data.payload.comm_boot_count
  :field comm_rssi: data.payload.comm_rssi
  :field comm_rssi_minimal: data.payload.comm_rssi_minimal
  :field comm_received_valid_packets: data.payload.comm_received_valid_packets
  :field comm_received_invalid_packets: data.payload.comm_received_invalid_packets
  :field comm_sent_packets: data.payload.comm_sent_packets
  :field comm_status: data.payload.comm_status
  :field comm_mode: data.payload.comm_mode
  :field comm_amp_temperature: data.payload.comm_amp_temperature
  :field comm_reserved_1: data.payload.comm_reserved_1
  :field comm_reserved_2: data.payload.comm_reserved_2
  :field eps_1_mcu1ch1_obc: data.payload.eps_1_mcu1ch1_obc
  :field eps_1_mcu1ch2_commu1: data.payload.eps_1_mcu1ch2_commu1
  :field eps_1_mcu2ch1_comms_plasgu: data.payload.eps_1_mcu2ch1_comms_plasgu
  :field eps_1_mcu2ch2_commu2: data.payload.eps_1_mcu2ch2_commu2
  :field eps_1_mcu3ch1_adcs1: data.payload.eps_1_mcu3ch1_adcs1
  :field eps_1_mcu3ch2_starsns1: data.payload.eps_1_mcu3ch2_starsns1
  :field eps_1_mcu4ch1_payload3_lepton_bridge: data.payload.eps_1_mcu4ch1_payload3_lepton_bridge
  :field eps_1_mcu4ch2_commx: data.payload.eps_1_mcu4ch2_commx
  :field eps_1_mcu5ch1_gyro1: data.payload.eps_1_mcu5ch1_gyro1
  :field eps_1_mcu6ch1_adcs2: data.payload.eps_1_mcu6ch1_adcs2
  :field eps_1_mcu6ch2_starsns2: data.payload.eps_1_mcu6ch2_starsns2
  :field eps_1_mcu7ch1_rws: data.payload.eps_1_mcu7ch1_rws
  :field eps_1_mcu7ch2_fecu_rtr: data.payload.eps_1_mcu7ch2_fecu_rtr
  :field eps_1_mcu8ch1_payload1_heater: data.payload.eps_1_mcu8ch1_payload1_heater
  :field eps_1_mcu8ch2_payload2_camera_heater: data.payload.eps_1_mcu8ch2_payload2_camera_heater
  :field eps_1_timekeeper: data.payload.eps_1_timekeeper
  :field eps_2_mcu1ch1_obc: data.payload.eps_2_mcu1ch1_obc
  :field eps_2_mcu1ch2_commu1: data.payload.eps_2_mcu1ch2_commu1
  :field eps_2_mcu2ch1_comms_plasgu: data.payload.eps_2_mcu2ch1_comms_plasgu
  :field eps_2_mcu2ch2_commu2: data.payload.eps_2_mcu2ch2_commu2
  :field eps_2_mcu3ch1_adcs1: data.payload.eps_2_mcu3ch1_adcs1
  :field eps_2_mcu3ch2_starsns1: data.payload.eps_2_mcu3ch2_starsns1
  :field eps_2_mcu4ch1_payload3_lepton_bridge: data.payload.eps_2_mcu4ch1_payload3_lepton_bridge
  :field eps_2_mcu4ch2_commx: data.payload.eps_2_mcu4ch2_commx
  :field eps_2_mcu5ch1_gyro1: data.payload.eps_2_mcu5ch1_gyro1
  :field eps_2_mcu6ch1_adcs2: data.payload.eps_2_mcu6ch1_adcs2
  :field eps_2_mcu6ch2_starsns2: data.payload.eps_2_mcu6ch2_starsns2
  :field eps_2_mcu7ch1_rws: data.payload.eps_2_mcu7ch1_rws
  :field eps_2_mcu7ch2_fecu_rtr: data.payload.eps_2_mcu7ch2_fecu_rtr
  :field eps_2_mcu8ch1_payload1_heater: data.payload.eps_2_mcu8ch1_payload1_heater
  :field eps_2_mcu8ch2_payload2_camera_heater: data.payload.eps_2_mcu8ch2_payload2_camera_heater
  :field eps_2_timekeeper: data.payload.eps_2_timekeeper
  :field comm_antenna_detector: data.payload.comm_antenna_detector
  :field comm_mode_correct: data.payload.comm_mode_correct
  :field comm_fec_on: data.payload.comm_fec_on
  :field packet_id: data.data_header.packet_id
  :field packet_size: data.data_header.packet_size
  :field system: data.data_payload.system
  :field gnss_type_byte: data.data_payload.payload.gnss_type_byte
  :field posix_time_ms: data.data_payload.payload.gnss_payload.posix_time_ms
  :field coord_x: data.data_payload.payload.gnss_payload.coord_x
  :field coord_y: data.data_payload.payload.gnss_payload.coord_y
  :field coord_z: data.data_payload.payload.gnss_payload.coord_z
  :field velocity_x: data.data_payload.payload.gnss_payload.velocity_x
  :field velocity_y: data.data_payload.payload.gnss_payload.velocity_y
  :field velocity_z: data.data_payload.payload.gnss_payload.velocity_z
  :field quaternion_q0: data.data_payload.payload.gnss_payload.quaternion_q0
  :field quaternion_q1: data.data_payload.payload.gnss_payload.quaternion_q1
  :field quaternion_q2: data.data_payload.payload.gnss_payload.quaternion_q2
  :field quaternion_q3: data.data_payload.payload.gnss_payload.quaternion_q3
  :field ref_motion_mode: data.data_payload.payload.gnss_payload.ref_motion_mode
  :field mag_torquer_mode: data.data_payload.payload.gnss_payload.mag_torquer_mode
  :field filter_type: data.data_payload.payload.gnss_payload.filter_type
  :field orientation_system_status: data.data_payload.payload.gnss_payload.orientation_system_status
  :field reserved: data.data_payload.payload.gnss_payload.reserved
  :field azdk_quaternion_q1: data.data_payload.payload.gnss_payload.azdk_quaternion_q1
  :field azdk_quaternion_q2: data.data_payload.payload.gnss_payload.azdk_quaternion_q2
  :field azdk_quaternion_q3: data.data_payload.payload.gnss_payload.azdk_quaternion_q3
  :field posix_time_s: data.data_payload.payload.gnss_payload.posix_time_s
  :field angular_velocity_x: data.data_payload.payload.gnss_payload.angular_velocity_x
  :field angular_velocity_y: data.data_payload.payload.gnss_payload.angular_velocity_y
  :field angular_velocity_z: data.data_payload.payload.gnss_payload.angular_velocity_z
  :field reserved0: data.data_payload.payload.gnss_payload.reserved0
  :field reserved1: data.data_payload.payload.gnss_payload.reserved1
  :field num: data.data_payload.payload.gnss_payload.num
  :field posix_time_s_1: data.data_payload.payload.gnss_payload.posix_time_s_1
  :field coord_x_1: data.data_payload.payload.gnss_payload.coord_x_1
  :field coord_y_1: data.data_payload.payload.gnss_payload.coord_y_1
  :field coord_z_1: data.data_payload.payload.gnss_payload.coord_z_1
  :field velocity_x_1: data.data_payload.payload.gnss_payload.velocity_x_1
  :field velocity_y_1: data.data_payload.payload.gnss_payload.velocity_y_1
  :field velocity_z_1: data.data_payload.payload.gnss_payload.velocity_z_1
  :field posix_time_s_2: data.data_payload.payload.gnss_payload.posix_time_s_2
  :field coord_x_2: data.data_payload.payload.gnss_payload.coord_x_2
  :field coord_y_2: data.data_payload.payload.gnss_payload.coord_y_2
  :field coord_z_2: data.data_payload.payload.gnss_payload.coord_z_2
  :field velocity_x_2: data.data_payload.payload.gnss_payload.velocity_x_2
  :field velocity_y_2: data.data_payload.payload.gnss_payload.velocity_y_2
  :field velocity_z_2: data.data_payload.payload.gnss_payload.velocity_z_2
  :field eps_beacon_base_info_raw: data.data_payload.payload.eps_beacon_base_info_raw
  :field eps_beacon_reboot_count: data.data_payload.payload.eps_beacon_reboot_count
  :field eps_beacon_firmware_image: data.data_payload.payload.eps_beacon_firmware_image
  :field eps_beacon_switcher_info_raw: data.data_payload.payload.eps_beacon_switcher_info_raw
  :field eps_beacon_balancer_info_raw: data.data_payload.payload.eps_beacon_balancer_info_raw
  :field eps_beacon_deployer_info_raw: data.data_payload.payload.eps_beacon_deployer_info_raw
  :field eps_beacon_heater_info_raw_1: data.data_payload.payload.eps_beacon_heater_info_raw_1
  :field eps_beacon_heater_info_raw_2: data.data_payload.payload.eps_beacon_heater_info_raw_2
  :field eps_beacon_error_mask_raw_1: data.data_payload.payload.eps_beacon_error_mask_raw_1
  :field eps_beacon_error_mask_raw_2: data.data_payload.payload.eps_beacon_error_mask_raw_2
  :field eps_beacon_load_current: data.data_payload.payload.eps_beacon_load_current
  :field eps_beacon_solar_current: data.data_payload.payload.eps_beacon_solar_current
  :field eps_beacon_cell1_voltage: data.data_payload.payload.eps_beacon_cell1_voltage
  :field eps_beacon_cell2_voltage: data.data_payload.payload.eps_beacon_cell2_voltage
  :field eps_beacon_cell3_voltage: data.data_payload.payload.eps_beacon_cell3_voltage
  :field eps_beacon_coulomb_counter: data.data_payload.payload.eps_beacon_coulomb_counter
  :field eps_beacon_mask_enabled_ext_devices_raw: data.data_payload.payload.eps_beacon_mask_enabled_ext_devices_raw
  :field eps_beacon_mask_enabled_int_devices_raw: data.data_payload.payload.eps_beacon_mask_enabled_int_devices_raw
  :field eps_beacon_temp_eps_battery: data.data_payload.payload.eps_beacon_temp_eps_battery
  :field eps_beacon_temp_eps_main: data.data_payload.payload.eps_beacon_temp_eps_main
  :field eps_beacon_temp_commu: data.data_payload.payload.eps_beacon_temp_commu
  :field eps_beacon_temp_commx: data.data_payload.payload.eps_beacon_temp_commx
  :field eps_beacon_temp_plasgu: data.data_payload.payload.eps_beacon_temp_plasgu
  :field eps_beacon_temp_rws0: data.data_payload.payload.eps_beacon_temp_rws0
  :field eps_beacon_temp_rws1: data.data_payload.payload.eps_beacon_temp_rws1
  :field eps_beacon_temp_rws2: data.data_payload.payload.eps_beacon_temp_rws2
  :field eps_beacon_temp_rws3: data.data_payload.payload.eps_beacon_temp_rws3
  :field eps_beacon_temp_solar_wing_y_pos: data.data_payload.payload.eps_beacon_temp_solar_wing_y_pos
  :field eps_beacon_temp_solar_wing_y_neg: data.data_payload.payload.eps_beacon_temp_solar_wing_y_neg
  :field eps_beacon_temp_camera_internal: data.data_payload.payload.eps_beacon_temp_camera_internal
  :field eps_beacon_temp_camera_heater_plate: data.data_payload.payload.eps_beacon_temp_camera_heater_plate
  :field eps_beacon_base_info_eps_mod: data.data_payload.payload.eps_beacon_base_info_eps_mod
  :field eps_beacon_base_info_self_addr: data.data_payload.payload.eps_beacon_base_info_self_addr
  :field eps_beacon_switcher_current_commu: data.data_payload.payload.eps_beacon_switcher_current_commu
  :field eps_beacon_switcher_state: data.data_payload.payload.eps_beacon_switcher_state
  :field eps_beacon_switcher_switching_state: data.data_payload.payload.eps_beacon_switcher_switching_state
  :field eps_beacon_switcher_relay_switch_error: data.data_payload.payload.eps_beacon_switcher_relay_switch_error
  :field eps_beacon_switcher_read_data_error: data.data_payload.payload.eps_beacon_switcher_read_data_error
  :field eps_beacon_balancer_state: data.data_payload.payload.eps_beacon_balancer_state
  :field eps_beacon_balancer_error: data.data_payload.payload.eps_beacon_balancer_error
  :field eps_beacon_balancer_is_balancing: data.data_payload.payload.eps_beacon_balancer_is_balancing
  :field eps_beacon_balancer_active_balancer: data.data_payload.payload.eps_beacon_balancer_active_balancer
  :field eps_beacon_balancer_ind_balancing_cell: data.data_payload.payload.eps_beacon_balancer_ind_balancing_cell
  :field eps_beacon_deployer_state: data.data_payload.payload.eps_beacon_deployer_state
  :field eps_beacon_deployer_storage_error: data.data_payload.payload.eps_beacon_deployer_storage_error
  :field eps_beacon_deployer_deployed_channels_mask: data.data_payload.payload.eps_beacon_deployer_deployed_channels_mask
  :field eps_beacon_heater_mode: data.data_payload.payload.eps_beacon_heater_mode
  :field eps_beacon_heater_active_heater_mask: data.data_payload.payload.eps_beacon_heater_active_heater_mask
  :field eps_beacon_heater_mask_tmp_src: data.data_payload.payload.eps_beacon_heater_mask_tmp_src
  :field eps_beacon_error_i2c_bat_monitor: data.data_payload.payload.eps_beacon_error_i2c_bat_monitor
  :field eps_beacon_error_spi_bat_monitor: data.data_payload.payload.eps_beacon_error_spi_bat_monitor
  :field eps_beacon_error_spi_fram: data.data_payload.payload.eps_beacon_error_spi_fram
  :field eps_beacon_error_i2c_fram1: data.data_payload.payload.eps_beacon_error_i2c_fram1
  :field eps_beacon_error_i2c_fram2: data.data_payload.payload.eps_beacon_error_i2c_fram2
  :field eps_beacon_error_mcu1_i2c: data.data_payload.payload.eps_beacon_error_mcu1_i2c
  :field eps_beacon_error_mcu2_i2c: data.data_payload.payload.eps_beacon_error_mcu2_i2c
  :field eps_beacon_error_mcu3_i2c: data.data_payload.payload.eps_beacon_error_mcu3_i2c
  :field eps_beacon_error_mcu4_i2c: data.data_payload.payload.eps_beacon_error_mcu4_i2c
  :field eps_beacon_error_mcu5_i2c: data.data_payload.payload.eps_beacon_error_mcu5_i2c
  :field eps_beacon_error_mcu6_i2c: data.data_payload.payload.eps_beacon_error_mcu6_i2c
  :field eps_beacon_error_mcu7_i2c: data.data_payload.payload.eps_beacon_error_mcu7_i2c
  :field eps_beacon_error_mcu8_i2c: data.data_payload.payload.eps_beacon_error_mcu8_i2c
  :field eps_beacon_ext_mcu1ch1: data.data_payload.payload.eps_beacon_ext_mcu1ch1
  :field eps_beacon_ext_mcu1ch2: data.data_payload.payload.eps_beacon_ext_mcu1ch2
  :field eps_beacon_ext_mcu2ch1: data.data_payload.payload.eps_beacon_ext_mcu2ch1
  :field eps_beacon_ext_mcu2ch2: data.data_payload.payload.eps_beacon_ext_mcu2ch2
  :field eps_beacon_ext_mcu3ch1: data.data_payload.payload.eps_beacon_ext_mcu3ch1
  :field eps_beacon_ext_mcu3ch2: data.data_payload.payload.eps_beacon_ext_mcu3ch2
  :field eps_beacon_ext_mcu4ch1: data.data_payload.payload.eps_beacon_ext_mcu4ch1
  :field eps_beacon_ext_mcu4ch2: data.data_payload.payload.eps_beacon_ext_mcu4ch2
  :field eps_beacon_ext_mcu5ch1: data.data_payload.payload.eps_beacon_ext_mcu5ch1
  :field eps_beacon_ext_mcu6ch1: data.data_payload.payload.eps_beacon_ext_mcu6ch1
  :field eps_beacon_ext_mcu6ch2: data.data_payload.payload.eps_beacon_ext_mcu6ch2
  :field eps_beacon_ext_mcu7ch1: data.data_payload.payload.eps_beacon_ext_mcu7ch1
  :field eps_beacon_ext_mcu7ch2: data.data_payload.payload.eps_beacon_ext_mcu7ch2
  :field eps_beacon_ext_mcu8ch1: data.data_payload.payload.eps_beacon_ext_mcu8ch1
  :field eps_beacon_ext_mcu8ch2: data.data_payload.payload.eps_beacon_ext_mcu8ch2
  :field eps_beacon_ext_timekeeper: data.data_payload.payload.eps_beacon_ext_timekeeper
  :field eps_beacon_int_mcu_pwr1: data.data_payload.payload.eps_beacon_int_mcu_pwr1
  :field eps_beacon_int_mcu_pwr2: data.data_payload.payload.eps_beacon_int_mcu_pwr2
  :field eps_beacon_int_ds_bus1: data.data_payload.payload.eps_beacon_int_ds_bus1
  :field eps_beacon_int_ds_bus2: data.data_payload.payload.eps_beacon_int_ds_bus2
  :field eps_beacon_int_can1: data.data_payload.payload.eps_beacon_int_can1
  :field eps_beacon_int_can2: data.data_payload.payload.eps_beacon_int_can2
  :field eps_beacon_int_timebus: data.data_payload.payload.eps_beacon_int_timebus
  :field eps_beacon_int_buxbus: data.data_payload.payload.eps_beacon_int_buxbus
  :field eps_beacon_int_fram1: data.data_payload.payload.eps_beacon_int_fram1
  :field eps_beacon_int_fram2: data.data_payload.payload.eps_beacon_int_fram2
  :field eps_beacon_int_bat_balancer1: data.data_payload.payload.eps_beacon_int_bat_balancer1
  :field eps_beacon_int_bat_balancer2: data.data_payload.payload.eps_beacon_int_bat_balancer2
  :field len: len
  :field type: type

seq:
  - id: data
    type:
      switch-on: type
      cases:
        0x848a: ax25_frame
        _: data_frame
instances:
  len:
    value: _io.size
  type:
    type: u2be
    pos: 0
types:
  data_frame:
    seq:
      - id: data_header
        type: data_header
      - id: data_payload
        type: data_tlm

  data_header:
    seq:
      - id: packet_id
        type: u2
      - id: packet_size
        type: u1

  data_tlm:
    seq:
      - id: system
        type: u2
        valid:
          any-of:
            - '0xBD35'
            - '0xBD29'
      - id: payload
        type:
          switch-on: system
          cases:
            0xBD35: gnss_tlm
            0xBD29: eps_beacon_tlm

  eps_beacon_tlm:
    seq:
      - id: eps_beacon_base_info_raw
        type: u1
      - id: eps_beacon_reboot_count
        type: u2
      - id: eps_beacon_firmware_image
        type: u1
      - id: eps_beacon_switcher_info_raw
        type: u1
      - id: eps_beacon_balancer_info_raw
        type: u1
      - id: eps_beacon_deployer_info_raw
        type: u1
      - id: eps_beacon_heater_info_raw_1
        type: u1
      - id: eps_beacon_heater_info_raw_2
        type: u1
      - id: eps_beacon_error_mask_raw_1
        type: u1
      - id: eps_beacon_error_mask_raw_2
        type: u1
      - id: eps_beacon_load_current
        type: u2
      - id: eps_beacon_solar_current
        type: u2
      - id: eps_beacon_cell1_voltage
        type: u2
      - id: eps_beacon_cell2_voltage
        type: u2
      - id: eps_beacon_cell3_voltage
        type: u2
      - id: eps_beacon_coulomb_counter
        type: s4
      - id: eps_beacon_mask_enabled_ext_devices_raw
        type: u2
      - id: eps_beacon_mask_enabled_int_devices_raw
        type: u2
      - id: eps_beacon_temp_eps_battery
        type: s1
      - id: eps_beacon_temp_eps_main
        type: s1
      - id: eps_beacon_temp_commu
        type: s1
      - id: eps_beacon_temp_commx
        type: s1
      - id: eps_beacon_temp_plasgu
        type: s1
      - id: eps_beacon_temp_rws0
        type: s1
      - id: eps_beacon_temp_rws1
        type: s1
      - id: eps_beacon_temp_rws2
        type: s1
      - id: eps_beacon_temp_rws3
        type: s1
      - id: eps_beacon_temp_solar_wing_y_pos
        type: s1
      - id: eps_beacon_temp_solar_wing_y_neg
        type: s1
      - id: eps_beacon_temp_camera_internal
        type: s1
      - id: eps_beacon_temp_camera_heater_plate
        type: s1
    instances:
      eps_beacon_base_info_eps_mod:
        value: (eps_beacon_base_info_raw >> 0) & 7
      eps_beacon_base_info_self_addr:
        value: (eps_beacon_base_info_raw >> 3) & 31
      eps_beacon_switcher_current_commu:
        value: (eps_beacon_switcher_info_raw >> 0) & 1
      eps_beacon_switcher_state:
        value: (eps_beacon_switcher_info_raw >> 1) & 3
      eps_beacon_switcher_switching_state:
        value: (eps_beacon_switcher_info_raw >> 3) & 3
      eps_beacon_switcher_relay_switch_error:
        value: (eps_beacon_switcher_info_raw >> 5) & 1
      eps_beacon_switcher_read_data_error:
        value: (eps_beacon_switcher_info_raw >> 6) & 1
      eps_beacon_balancer_state:
        value: (eps_beacon_balancer_info_raw >> 0) & 3
      eps_beacon_balancer_error:
        value: (eps_beacon_balancer_info_raw >> 2) & 1
      eps_beacon_balancer_is_balancing:
        value: (eps_beacon_balancer_info_raw >> 3) & 1
      eps_beacon_balancer_active_balancer:
        value: (eps_beacon_balancer_info_raw >> 4) & 3
      eps_beacon_balancer_ind_balancing_cell:
        value: (eps_beacon_balancer_info_raw >> 6) & 3
      eps_beacon_deployer_state:
        value: (eps_beacon_deployer_info_raw >> 0) & 3
      eps_beacon_deployer_storage_error:
        value: (eps_beacon_deployer_info_raw >> 2) & 1
      eps_beacon_deployer_deployed_channels_mask:
        value: (eps_beacon_deployer_info_raw >> 4) & 15
      eps_beacon_heater_mode:
        value: (eps_beacon_heater_info_raw_1 >> 0) & 3
      eps_beacon_heater_active_heater_mask:
        value: (eps_beacon_heater_info_raw_1 >> 2) & 3
      eps_beacon_heater_mask_tmp_src:
        value: (eps_beacon_heater_info_raw_1 >> 4) & 15
      eps_beacon_error_i2c_bat_monitor:
        value: (eps_beacon_error_mask_raw_1 >> 0) & 1
      eps_beacon_error_spi_bat_monitor:
        value: (eps_beacon_error_mask_raw_1 >> 1) & 1
      eps_beacon_error_spi_fram:
        value: (eps_beacon_error_mask_raw_1 >> 2) & 1
      eps_beacon_error_i2c_fram1:
        value: (eps_beacon_error_mask_raw_1 >> 3) & 1
      eps_beacon_error_i2c_fram2:
        value: (eps_beacon_error_mask_raw_1 >> 4) & 1
      eps_beacon_error_mcu1_i2c:
        value: (eps_beacon_error_mask_raw_1 >> 5) & 1
      eps_beacon_error_mcu2_i2c:
        value: (eps_beacon_error_mask_raw_1 >> 6) & 1
      eps_beacon_error_mcu3_i2c:
        value: (eps_beacon_error_mask_raw_1 >> 7) & 1
      eps_beacon_error_mcu4_i2c:
        value: (eps_beacon_error_mask_raw_2 >> 0) & 1
      eps_beacon_error_mcu5_i2c:
        value: (eps_beacon_error_mask_raw_2 >> 1) & 1
      eps_beacon_error_mcu6_i2c:
        value: (eps_beacon_error_mask_raw_2 >> 2) & 1
      eps_beacon_error_mcu7_i2c:
        value: (eps_beacon_error_mask_raw_2 >> 3) & 1
      eps_beacon_error_mcu8_i2c:
        value: (eps_beacon_error_mask_raw_2 >> 4) & 1
      eps_beacon_ext_mcu1ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 0) & 1
      eps_beacon_ext_mcu1ch2:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 1) & 1
      eps_beacon_ext_mcu2ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 2) & 1
      eps_beacon_ext_mcu2ch2:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 3) & 1
      eps_beacon_ext_mcu3ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 4) & 1
      eps_beacon_ext_mcu3ch2:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 5) & 1
      eps_beacon_ext_mcu4ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 6) & 1
      eps_beacon_ext_mcu4ch2:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 7) & 1
      eps_beacon_ext_mcu5ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 8) & 1
      eps_beacon_ext_mcu6ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 9) & 1
      eps_beacon_ext_mcu6ch2:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 10) & 1
      eps_beacon_ext_mcu7ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 11) & 1
      eps_beacon_ext_mcu7ch2:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 12) & 1
      eps_beacon_ext_mcu8ch1:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 13) & 1
      eps_beacon_ext_mcu8ch2:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 14) & 1
      eps_beacon_ext_timekeeper:
        value: (eps_beacon_mask_enabled_ext_devices_raw >> 15) & 1
      eps_beacon_int_mcu_pwr1:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 0) & 1
      eps_beacon_int_mcu_pwr2:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 1) & 1
      eps_beacon_int_ds_bus1:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 2) & 1
      eps_beacon_int_ds_bus2:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 3) & 1
      eps_beacon_int_can1:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 4) & 1
      eps_beacon_int_can2:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 5) & 1
      eps_beacon_int_timebus:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 6) & 1
      eps_beacon_int_buxbus:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 7) & 1
      eps_beacon_int_fram1:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 8) & 1
      eps_beacon_int_fram2:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 9) & 1
      eps_beacon_int_bat_balancer1:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 10) & 1
      eps_beacon_int_bat_balancer2:
        value: (eps_beacon_mask_enabled_int_devices_raw >> 11) & 1

  gnss_tlm:
    seq:
      - id: gnss_type_byte
        type: u1
      - id: gnss_payload
        type:
          switch-on: gnss_type_byte
          cases:
            0x42: gnss_tlm_66
            0x43: gnss_tlm_67
            0x46: gnss_tlm_70

  gnss_tlm_66:
    seq:
      - id: posix_time_ms
        type: u8
      - id: coord_x
        type: f4
      - id: coord_y
        type: f4
      - id: coord_z
        type: f4
      - id: velocity_x
        type: f4
      - id: velocity_y
        type: f4
      - id: velocity_z
        type: f4
      - id: quaternion_q0
        type: f4
      - id: quaternion_q1
        type: f4
      - id: quaternion_q2
        type: f4
      - id: quaternion_q3
        type: f4
      - id: ref_motion_mode
        type: u1
      - id: mag_torquer_mode
        type: u1
      - id: filter_type
        type: u1
      - id: orientation_system_status
        type: u1
      - id: reserved
        type: u2
      - id: azdk_quaternion_q1
        type: f4
      - id: azdk_quaternion_q2
        type: f4
      - id: azdk_quaternion_q3
        type: f4

  gnss_tlm_67:
    seq:
      - id: posix_time_s
        type: u4
      - id: coord_x
        type: f4
      - id: coord_y
        type: f4
      - id: coord_z
        type: f4
      - id: velocity_x
        type: f4
      - id: velocity_y
        type: f4
      - id: velocity_z
        type: f4
      - id: quaternion_q0
        type: f4
      - id: quaternion_q1
        type: f4
      - id: quaternion_q2
        type: f4
      - id: quaternion_q3
        type: f4
      - id: angular_velocity_x
        type: f4
      - id: angular_velocity_y
        type: f4
      - id: angular_velocity_z
        type: f4
      - id: reserved0
        type: u2
      - id: reserved1
        type: u8

  gnss_tlm_70:
    seq:
      - id: num
        type: u4
      - id: posix_time_s_1
        type: u4
      - id: coord_x_1
        type: s4
      - id: coord_y_1
        type: s4
      - id: coord_z_1
        type: s4
      - id: velocity_x_1
        type: s4
      - id: velocity_y_1
        type: s4
      - id: velocity_z_1
        type: s4
      - id: posix_time_s_2
        type: u4
      - id: coord_x_2
        type: s4
      - id: coord_y_2
        type: s4
      - id: coord_z_2
        type: s4
      - id: velocity_x_2
        type: s4
      - id: velocity_y_2
        type: s4
      - id: velocity_z_2
        type: s4
      - id: reserved0
        type: u4
      - id: reserved1
        type: u2

  ax25_frame:
    seq:
      - id: ax25_header
        type: ax25_header
      - id: payload
        type: geoscan_beacon_tlm

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
      - id: callsign_start
        type: callsign_start_raw
      - id: callsign_end
        type: callsign_end_raw

  callsign_start_raw:
    seq:
      - id: callsign_start_str
        type: str
        encoding: ASCII
        size: 2
        valid:
          any-of:
            - '"BE"'
            - '"RS"'

  callsign_end_raw:
    seq:
      - id: callsign_end_str
        type: str
        encoding: ASCII
        size: 4

  ssid_mask:
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x0f) >> 1

  geoscan_beacon_tlm:
    seq:
      - id: beacon_id
        type: u1
      - id: eps_1_mode
        type: u1
      - id: eps_1_consumption_current
        type: u2
      - id: eps_1_solar_cells_current
        type: u2
      - id: eps_1_cell_voltage_full
        type: u2
      - id: eps_1_battery_temperature
        type: s1
      - id: eps_1_temperature_sp_y_pos
        type: s1
      - id: eps_1_temperature_sp_y_neg
        type: s1
      - id: eps_1_temperature_sp_x_pos
        type: s1
      - id: eps_1_temperature_sp_x_neg
        type: s1
      - id: eps_1_systems_status
        type: u2
      - id: eps_1_boot_count
        type: u2
      - id: eps_2_mode
        type: u1
      - id: eps_2_consumption_current
        type: u2
      - id: eps_2_solar_cells_current
        type: u2
      - id: eps_2_cell_voltage_full
        type: u2
      - id: eps_2_battery_temperature
        type: s1
      - id: eps_2_temperature_sp_y_pos
        type: s1
      - id: eps_2_temperature_sp_y_neg
        type: s1
      - id: eps_2_temperature_sp_x_pos
        type: s1
      - id: eps_2_temperature_sp_x_neg
        type: s1
      - id: eps_2_systems_status
        type: u2
      - id: eps_2_boot_count
        type: u2
      - id: adcs_mt_mode
        type: u1
      - id: adcs_rm_mode
        type: u1
      - id: adcs_kf_mode
        type: u1
      - id: adcs_filter_reset_count
        type: u1
      - id: adcs_sensors_state
        type: u2
      - id: adcs_flywheel_state
        type: u1
      - id: comm_type
        type: u1
      - id: comm_vbus_voltage
        type: u2
      - id: comm_boot_count
        type: u2
      - id: comm_rssi
        type: s1
      - id: comm_rssi_minimal
        type: s1
      - id: comm_received_valid_packets
        type: u1
      - id: comm_received_invalid_packets
        type: u1
      - id: comm_sent_packets
        type: u1
      - id: comm_status
        type: u1
      - id: comm_mode
        type: u1
      - id: comm_amp_temperature
        type: s1
      - id: comm_reserved_1
        type: u2
      - id: comm_reserved_2
        type: u1
    instances: 
      eps_1_mcu1ch1_obc:
        value: (eps_1_systems_status >> 0) & 1
      eps_1_mcu1ch2_commu1:
        value: (eps_1_systems_status >> 1) & 1
      eps_1_mcu2ch1_comms_plasgu:
        value: (eps_1_systems_status >> 2) & 1
      eps_1_mcu2ch2_commu2:
        value: (eps_1_systems_status >> 3) & 1
      eps_1_mcu3ch1_adcs1:
        value: (eps_1_systems_status >> 4) & 1
      eps_1_mcu3ch2_starsns1:
        value: (eps_1_systems_status >> 5) & 1
      eps_1_mcu4ch1_payload3_lepton_bridge:
        value: (eps_1_systems_status >> 6) & 1
      eps_1_mcu4ch2_commx:
        value: (eps_1_systems_status >> 7) & 1
      eps_1_mcu5ch1_gyro1:
        value: (eps_1_systems_status >> 8) & 1
      eps_1_mcu6ch1_adcs2:
        value: (eps_1_systems_status >> 9) & 1
      eps_1_mcu6ch2_starsns2:
        value: (eps_1_systems_status >> 10) & 1
      eps_1_mcu7ch1_rws:
        value: (eps_1_systems_status >> 11) & 1
      eps_1_mcu7ch2_fecu_rtr:
        value: (eps_1_systems_status >> 12) & 1
      eps_1_mcu8ch1_payload1_heater:
        value: (eps_1_systems_status >> 13) & 1
      eps_1_mcu8ch2_payload2_camera_heater:
        value: (eps_1_systems_status >> 14) & 1
      eps_1_timekeeper:
        value: (eps_1_systems_status >> 15) & 1
      eps_2_mcu1ch1_obc:
        value: (eps_2_systems_status >> 0) & 1
      eps_2_mcu1ch2_commu1:
        value: (eps_2_systems_status >> 1) & 1
      eps_2_mcu2ch1_comms_plasgu:
        value: (eps_2_systems_status >> 2) & 1
      eps_2_mcu2ch2_commu2:
        value: (eps_2_systems_status >> 3) & 1
      eps_2_mcu3ch1_adcs1:
        value: (eps_2_systems_status >> 4) & 1
      eps_2_mcu3ch2_starsns1:
        value: (eps_2_systems_status >> 5) & 1
      eps_2_mcu4ch1_payload3_lepton_bridge:
        value: (eps_2_systems_status >> 6) & 1
      eps_2_mcu4ch2_commx:
        value: (eps_2_systems_status >> 7) & 1
      eps_2_mcu5ch1_gyro1:
        value: (eps_2_systems_status >> 8) & 1
      eps_2_mcu6ch1_adcs2:
        value: (eps_2_systems_status >> 9) & 1
      eps_2_mcu6ch2_starsns2:
        value: (eps_2_systems_status >> 10) & 1
      eps_2_mcu7ch1_rws:
        value: (eps_2_systems_status >> 11) & 1
      eps_2_mcu7ch2_fecu_rtr:
        value: (eps_2_systems_status >> 12) & 1
      eps_2_mcu8ch1_payload1_heater:
        value: (eps_2_systems_status >> 13) & 1
      eps_2_mcu8ch2_payload2_camera_heater:
        value: (eps_2_systems_status >> 14) & 1
      eps_2_timekeeper:
        value: (eps_2_systems_status >> 15) & 1
      comm_antenna_detector:
        value: (comm_status >> 0) & 1
      comm_mode_correct:
        value: (comm_status >> 1) & 1
      comm_fec_on:
        value: (comm_status >> 2) & 1
