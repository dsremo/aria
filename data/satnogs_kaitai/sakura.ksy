---
meta:
  id: sakura
  title: Sakura CW, HK, AUTO GMSK beacon + CAM downlink + Digi decoder
  endian: be
doc-ref: "https://sites.google.com/p.chibakoudai.jp/gardens-03/home-english/documents/transmission-format"
# 2024-09-11, DL7NDR + 徳永 大輝 (TOKUNAGA Daiki) [bugfixed 2024-09-25]
doc: |
  :field cw_callsign_and_satellite_name: sakura.type_check.cw_callsign_and_satellite_name
  :field cw_batt_v: sakura.type_check.cw_batt_v
  :field cw_batt_i: sakura.type_check.cw_batt_i
  :field cw_batt_t: sakura.type_check.cw_batt_t
  :field cw_bpb_t: sakura.type_check.cw_bpb_t
  :field cw_raw_i: sakura.type_check.cw_raw_i
  :field cw_power_5v0: sakura.type_check.cw_power_5v0
  :field cw_pwr_ant_dep: sakura.type_check.cw_pwr_ant_dep
  :field cw_power_com: sakura.type_check.cw_power_com
  :field cw_sap_minus_x: sakura.type_check.cw_sap_minus_x
  :field cw_sap_plus_y: sakura.type_check.cw_sap_plus_y
  :field cw_sap_minus_y: sakura.type_check.cw_sap_minus_y
  :field cw_sap_plus_z: sakura.type_check.cw_sap_plus_z
  :field cw_sap_minus_z: sakura.type_check.cw_sap_minus_z
  :field cw_reserve_cmd_counter: sakura.type_check.cw_reserve_cmd_counter
  :field cw_gmsk_cmd_counter: sakura.type_check.cw_gmsk_cmd_counter
  :field cw_kill_sw: sakura.type_check.cw_kill_sw
  :field cw_kill_counter: sakura.type_check.cw_kill_counter
  :field cw_mission_pic_on_off: sakura.type_check.cw_mission_pic_on_off
  :field cw_mis_error_flag: sakura.type_check.cw_mis_error_flag
  :field cw_mis_end_flag: sakura.type_check.cw_mis_end_flag
  :field cw_aprs_flag: sakura.type_check.cw_aprs_flag
  :field cw_current_mis: sakura.type_check.cw_current_mis
  :field cw_beacon: sakura.type_check.cw_beacon
  :field beacon_type: sakura.type_check.beacon_type
  :field cam_callsign_header: sakura.type_check.type_check_1.cam_callsign_header
  :field cam_ctrl: sakura.type_check.type_check_1.cam_ctrl
  :field cam_pid: sakura.type_check.type_check_1.cam_pid
  :field cam_sat_id: sakura.type_check.type_check_1.cam_sat_id
  :field cam_packet_id: sakura.type_check.type_check_1.cam_packet_id
  :field cam_reserved: sakura.type_check.type_check_1.cam_reserved
  :field cam_packet_number: sakura.type_check.type_check_1.cam_packet_number
  :field cam_soi: sakura.type_check.type_check_1.cam_soi
  :field cam_jfif_marker: sakura.type_check.type_check_1.cam_jfif_marker
  :field cam_data_length: sakura.type_check.type_check_1.cam_data_length
  :field cam_jfif_id: sakura.type_check.type_check_1.cam_jfif_id
  :field cam_data_b64_encoded: sakura.type_check.type_check_1.cam_data.b64encstring.cam_data_b64_encoded
  :field beacon_type: sakura.type_check.type_check_1.beacon_type
  :field hk_callsign_header: sakura.type_check.type_check_1.type_check_2.hk_callsign_header
  :field seconds: sakura.type_check.type_check_1.type_check_2.seconds
  :field minutes: sakura.type_check.type_check_1.type_check_2.minutes
  :field hours: sakura.type_check.type_check_1.type_check_2.hours
  :field days: sakura.type_check.type_check_1.type_check_2.days
  :field n_a: sakura.type_check.type_check_1.type_check_2.n_a
  :field temp_minus_x: sakura.type_check.type_check_1.type_check_2.temp_minus_x
  :field temp_plus_y: sakura.type_check.type_check_1.type_check_2.temp_plus_y
  :field temp_minus_y: sakura.type_check.type_check_1.type_check_2.temp_minus_y
  :field temp_plus_z: sakura.type_check.type_check_1.type_check_2.temp_minus_z
  :field temp_minus_z: sakura.type_check.type_check_1.type_check_2.temp_plus_z
  :field bpb_t: sakura.type_check.type_check_1.type_check_2.bpb_t
  :field voltage_minus_x: sakura.type_check.type_check_1.type_check_2.voltage_minus_x
  :field voltage_plus_y: sakura.type_check.type_check_1.type_check_2.voltage_plus_y
  :field voltage_minus_y: sakura.type_check.type_check_1.type_check_2.voltage_minus_y
  :field voltage_plus_z: sakura.type_check.type_check_1.type_check_2.voltage_plus_z
  :field voltage_minus_z: sakura.type_check.type_check_1.type_check_2.voltage_minus_z
  :field current_minus_x: sakura.type_check.type_check_1.type_check_2.current_minus_x
  :field current_plus_y: sakura.type_check.type_check_1.type_check_2.current_plus_y
  :field current_minus_y: sakura.type_check.type_check_1.type_check_2.current_minus_y
  :field current_plus_z: sakura.type_check.type_check_1.type_check_2.current_plus_z
  :field current_minus_z: sakura.type_check.type_check_1.type_check_2.current_plus_z
  :field batt_t: sakura.type_check.type_check_1.type_check_2.batt_t
  :field batt_v: sakura.type_check.type_check_1.type_check_2.batt_v
  :field batt_i: sakura.type_check.type_check_1.type_check_2.batt_i
  :field raw_v: sakura.type_check.type_check_1.type_check_2.raw_v
  :field raw_i: sakura.type_check.type_check_1.type_check_2.raw_i
  :field src_v: sakura.type_check.type_check_1.type_check_2.src_v
  :field src_i: sakura.type_check.type_check_1.type_check_2.src_i
  :field kill_sw: sakura.type_check.type_check_1.type_check_2.kill_sw
  :field raw_v_1: sakura.type_check.type_check_1.type_check_2.raw_v_1
  :field q3v3_1_i: sakura.type_check.type_check_1.type_check_2.q3v3_1_i
  :field q3v3_2_i: sakura.type_check.type_check_1.type_check_2.q3v3_2_i
  :field com_i: sakura.type_check.type_check_1.type_check_2.com_i
  :field ant_dep_i: sakura.type_check.type_check_1.type_check_2.ant_dep_i
  :field q5v0_i: sakura.type_check.type_check_1.type_check_2.q5v0_i
  :field reset_raw_v_mon: sakura.type_check.type_check_1.type_check_2.reset_raw_v_mon
  :field power_com: sakura.type_check.type_check_1.type_check_2.power_com
  :field power_5v0: sakura.type_check.type_check_1.type_check_2.power_5v0
  :field dcdc_3v3_1: sakura.type_check.type_check_1.type_check_2.dcdc_3v3_1
  :field pwr_ant_dep: sakura.type_check.type_check_1.type_check_2.pwr_ant_dep
  :field pwr_3v3_2: sakura.type_check.type_check_1.type_check_2.pwr_3v3_2
  :field pwr_3v3_1: sakura.type_check.type_check_1.type_check_2.pwr_3v3_1
  :field dcdc_5v0: sakura.type_check.type_check_1.type_check_2.dcdc_5v0
  :field dcdc_3v3_2: sakura.type_check.type_check_1.type_check_2.dcdc_3v3_2
  :field pwr_compic: sakura.type_check.type_check_1.type_check_2.pwr_compic
  :field pwr_mainpic: sakura.type_check.type_check_1.type_check_2.pwr_mainpic
  :field empty: sakura.type_check.type_check_1.type_check_2.empty
  :field mp_reset_counter: sakura.type_check.type_check_1.type_check_2.mp_reset_counter
  :field rssi: sakura.type_check.type_check_1.type_check_2.rssi
  :field com_t: sakura.type_check.type_check_1.type_check_2.com_t
  :field com_seq_counter: sakura.type_check.type_check_1.type_check_2.com_seq_counter
  :field cmd_uplink_counter: sakura.type_check.type_check_1.type_check_2.cmd_uplink_counter
  :field mis_ack: sakura.type_check.type_check_1.type_check_2.mis_ack
  :field n_a_2: sakura.type_check.type_check_1.type_check_2.n_a_2
  :field current_mis: sakura.type_check.type_check_1.type_check_2.current_mis
  :field mis_counter: sakura.type_check.type_check_1.type_check_2.mis_counter
  :field checksum: sakura.type_check.type_check_1.type_check_2.checksum
  :field beacon_type: sakura.type_check.type_check_1.type_check_2.beacon_type
  :field auto_gmsk_callsign_header: sakura.type_check.type_check_1.type_check_2.auto_gmsk_callsign_header
  :field flag_data_address: sakura.type_check.type_check_1.type_check_2.flag_data_address
  :field commands_reserved_data_address: sakura.type_check.type_check_1.type_check_2.commands_reserved_data_address
  :field log_data_address: sakura.type_check.type_check_1.type_check_2.log_data_address
  :field hk_data_address: sakura.type_check.type_check_1.type_check_2.hk_data_address
  :field cw_data_address: sakura.type_check.type_check_1.type_check_2.cw_data_address
  :field high_sampling_hk_data_address: sakura.type_check.type_check_1.type_check_2.high_sampling_hk_data_address
  :field aprs_message_data_address: sakura.type_check.type_check_1.type_check_2type_check.aprs_message_data_address
  :field aprs_log_data_address: sakura.type_check.type_check_1.type_check_2.aprs_log_data_address
  :field mission_log_data_address: sakura.type_check.type_check_1.type_check_2.mission_log_data_address
  :field sun_camera_thumbnail_address: sakura.type_check.type_check_1.type_check_2.sun_camera_thumbnail_address
  :field earth_camera_thumbnail_address: sakura.type_check.type_check_1.type_check_2.earth_camera_image_address
  :field sun_camera_image_address: sakura.type_check.type_check_1.type_check_2.sun_camera_image_address
  :field earth_camera_image_address: sakura.type_check.type_check_1.type_check_2.earth_camera_image_address
  :field sun_sensor_log_data_address: sakura.type_check.type_check_1.type_check_2.sun_sensor_log_data_address
  :field flash_memory_rewrite_count: sakura.type_check.type_check_1.type_check_2.flash_memory_rewrite_count
  :field antenna_deployment_attempts_count: sakura.type_check.type_check_1.type_check_2.antenna_deployment_attempts_count
  :field ongoing_mission: sakura.type_check.type_check_1.type_check_2.type_check_1.type_check_2type_check.ongoing_mission
  :field reserved_command: sakura.type_check.type_check_1.type_check_2.reserved_command
  :field kill_switch_flag: sakura.type_check.type_check_1.type_check_2.kill_switch_flag
  :field beacon_type: sakura.type_check.type_check_1.type_check_2.beacon_type
  :field dest_callsign: sakura.type_check.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: sakura.type_check.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: sakura.type_check.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: sakura.type_check.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: sakura.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: sakura.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: sakura.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field ctl: sakura.type_check.ax25_frame.ax25_header.ctl
  :field pid: sakura.type_check.ax25_frame.payload.pid
  :field monitor: sakura.type_check.ax25_frame.payload.ax25_info.data_monitor
  :field beacon_type: sakura.type_check.beacon_type

seq:
  - id: sakura
    type: sakura_t

types:
  sakura_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x73616B757261206A: cw # sakura j
            0x4a5331594d59304a: digital_beacon # JS1YMY0J  :decision, if AUTO GMSK or HK or CAM
            _: digi # everything else

    instances:
        check:
              type: u8
              pos: 0

  cw:
    seq:
      - id: cw_callsign_and_satellite_name
        type: str
        size: 21
        encoding: ASCII
        valid: '"sakura js1ymy js1yni "' # 73616B757261206A7331796D79206A7331796E6920
      - id: cw_batt_v
        type: u1
      - id: cw_batt_i
        type: u1
      - id: cw_batt_t
        type: u1
      - id: cw_bpb_t
        type: u1
      - id: cw_raw_i
        type: u1
      - id: cw_power_5v0
        type: b1
      - id: cw_pwr_ant_dep
        type: b1
      - id: cw_power_com
        type: b1
      - id: cw_sap_minus_x
        type: b1
      - id: cw_sap_plus_y
        type: b1
      - id: cw_sap_minus_y
        type: b1
      - id: cw_sap_plus_z
        type: b1
      - id: cw_sap_minus_z
        type: b1
      - id: cw_reserve_cmd_counter
        type: b4
      - id: cw_gmsk_cmd_counter
        type: b3
      - id: cw_kill_sw
        type: b1
      - id: cw_kill_counter
        type: b2
      - id: cw_mission_pic_on_off
        type: b1
      - id: cw_mis_error_flag
        type: b1
      - id: cw_mis_end_flag
        type: b1
      - id: cw_aprs_flag
        type: b1
      - id: cw_current_mis
        type: b2

    instances:
        beacon_type:
              value:  '0 == 0 ? "CW" : "CW"'

# reformating from integer to hex to show beacon

        batt_v_hex_left:
              value: cw_batt_v / 16

        batt_v_hex_left_digit:
              value: 'batt_v_hex_left.to_s == "10" ? "a" : (batt_v_hex_left.to_s == "11" ? "b" : (batt_v_hex_left.to_s == "12" ? "c" : (batt_v_hex_left.to_s == "13" ? "d" : (batt_v_hex_left.to_s == "14" ? "e" : (batt_v_hex_left.to_s == "15" ? "f" : batt_v_hex_left.to_s)))))'

        batt_v_hex_right:
              value: cw_batt_v % 16

        batt_v_hex_right_digit:
              value: 'batt_v_hex_right.to_s == "10" ? "a" : (batt_v_hex_right.to_s == "11" ? "b" : (batt_v_hex_right.to_s == "12" ? "c" : (batt_v_hex_right.to_s == "13" ? "d" : (batt_v_hex_right.to_s == "14" ? "e" : (batt_v_hex_right.to_s == "15" ? "f" : batt_v_hex_right.to_s)))))'

        batt_v_hex:
              value: batt_v_hex_left_digit + batt_v_hex_right_digit


        batt_i_hex_left:
              value: cw_batt_i / 16

        batt_i_hex_left_digit:
              value: 'batt_i_hex_left.to_s == "10" ? "a" : (batt_i_hex_left.to_s == "11" ? "b" : (batt_i_hex_left.to_s == "12" ? "c" : (batt_i_hex_left.to_s == "13" ? "d" : (batt_i_hex_left.to_s == "14" ? "e" : (batt_i_hex_left.to_s == "15" ? "f" : batt_i_hex_left.to_s)))))'

        batt_i_hex_right:
              value: cw_batt_i % 16

        batt_i_hex_right_digit:
              value: 'batt_i_hex_right.to_s == "10" ? "a" : (batt_i_hex_right.to_s == "11" ? "b" : (batt_i_hex_right.to_s == "12" ? "c" : (batt_i_hex_right.to_s == "13" ? "d" : (batt_i_hex_right.to_s == "14" ? "e" : (batt_i_hex_right.to_s == "15" ? "f" : batt_i_hex_right.to_s)))))'

        batt_i_hex:
              value: batt_i_hex_left_digit + batt_i_hex_right_digit


        batt_t_hex_left:
              value: cw_batt_t / 16

        batt_t_hex_left_digit:
              value: 'batt_t_hex_left.to_s == "10" ? "a" : (batt_t_hex_left.to_s == "11" ? "b" : (batt_t_hex_left.to_s == "12" ? "c" : (batt_t_hex_left.to_s == "13" ? "d" : (batt_t_hex_left.to_s == "14" ? "e" : (batt_t_hex_left.to_s == "15" ? "f" : batt_t_hex_left.to_s)))))'

        batt_t_hex_right:
              value: cw_batt_t % 16

        batt_t_hex_right_digit:
              value: 'batt_t_hex_right.to_s == "10" ? "a" : (batt_t_hex_right.to_s == "11" ? "b" : (batt_t_hex_right.to_s == "12" ? "c" : (batt_t_hex_right.to_s == "13" ? "d" : (batt_t_hex_right.to_s == "14" ? "e" : (batt_t_hex_right.to_s == "15" ? "f" : batt_t_hex_right.to_s)))))'

        batt_t_hex:
              value: batt_t_hex_left_digit + batt_t_hex_right_digit


        bpb_t_hex_left:
              value: cw_bpb_t / 16

        bpb_t_hex_left_digit:
              value: 'bpb_t_hex_left.to_s == "10" ? "a" : (bpb_t_hex_left.to_s == "11" ? "b" : (bpb_t_hex_left.to_s == "12" ? "c" : (bpb_t_hex_left.to_s == "13" ? "d" : (bpb_t_hex_left.to_s == "14" ? "e" : (bpb_t_hex_left.to_s == "15" ? "f" : bpb_t_hex_left.to_s)))))'

        bpb_t_hex_right:
              value: cw_bpb_t % 16

        bpb_t_hex_right_digit:
              value: 'bpb_t_hex_right.to_s == "10" ? "a" : (bpb_t_hex_right.to_s == "11" ? "b" : (bpb_t_hex_right.to_s == "12" ? "c" : (bpb_t_hex_right.to_s == "13" ? "d" : (bpb_t_hex_right.to_s == "14" ? "e" : (bpb_t_hex_right.to_s == "15" ? "f" : bpb_t_hex_right.to_s)))))'

        bpb_t_hex:
              value: bpb_t_hex_left_digit + bpb_t_hex_right_digit


        raw_i_hex_left:
              value: cw_raw_i / 16

        raw_i_hex_left_digit:
              value: 'raw_i_hex_left.to_s == "10" ? "a" : (raw_i_hex_left.to_s == "11" ? "b" : (raw_i_hex_left.to_s == "12" ? "c" : (raw_i_hex_left.to_s == "13" ? "d" : (raw_i_hex_left.to_s == "14" ? "e" : (raw_i_hex_left.to_s == "15" ? "f" : raw_i_hex_left.to_s)))))'

        raw_i_hex_right:
              value: cw_raw_i % 16

        raw_i_hex_right_digit:
              value: 'raw_i_hex_right.to_s == "10" ? "a" : (raw_i_hex_right.to_s == "11" ? "b" : (raw_i_hex_right.to_s == "12" ? "c" : (raw_i_hex_right.to_s == "13" ? "d" : (raw_i_hex_right.to_s == "14" ? "e" : (raw_i_hex_right.to_s == "15" ? "f" : raw_i_hex_right.to_s)))))'

        raw_i_hex:
              value: raw_i_hex_left_digit + raw_i_hex_right_digit



        data_1_dec_value_1:
              value: 'cw_power_5v0.to_i == 1 ? 128 : 0'
        data_1_dec_value_2:
              value: 'cw_pwr_ant_dep.to_i == 1 ? 64 : 0'
        data_1_dec_value_3:
              value: 'cw_power_com.to_i == 1 ? 32 : 0'
        data_1_dec_value_4:
              value: 'cw_sap_minus_x.to_i == 1 ? 16 : 0'
        data_1_dec_value_5:
              value: 'cw_sap_plus_y.to_i == 1 ? 8 : 0'
        data_1_dec_value_6:
              value: 'cw_sap_minus_y.to_i == 1 ? 4 : 0'
        data_1_dec_value_7:
              value: 'cw_sap_plus_z.to_i == 1 ? 2 : 0'
        data_1_dec_value_8:
              value: 'cw_sap_minus_z.to_i == 1 ? 1 : 0'

        data_1_dec:
              value: data_1_dec_value_1 + data_1_dec_value_2 + data_1_dec_value_3 + data_1_dec_value_4 + data_1_dec_value_5 + data_1_dec_value_6 + data_1_dec_value_7 + data_1_dec_value_8

        data_1_hex_left:
              value: data_1_dec / 16

        data_1_hex_left_digit:
              value: 'data_1_hex_left.to_s == "10" ? "a" : (data_1_hex_left.to_s == "11" ? "b" : (data_1_hex_left.to_s == "12" ? "c" : (data_1_hex_left.to_s == "13" ? "d" : (data_1_hex_left.to_s == "14" ? "e" : (data_1_hex_left.to_s == "15" ? "f" : data_1_hex_left.to_s)))))'

        data_1_hex_right:
              value: data_1_dec % 16

        data_1_hex_right_digit:
              value: 'data_1_hex_right.to_s == "10" ? "a" : (data_1_hex_right.to_s == "11" ? "b" : (data_1_hex_right.to_s == "12" ? "c" : (data_1_hex_right.to_s == "13" ? "d" : (data_1_hex_right.to_s == "14" ? "e" : (data_1_hex_right.to_s == "15" ? "f" : data_1_hex_right.to_s)))))'

        data_1_hex:
              value: data_1_hex_left_digit + data_1_hex_right_digit



        data_2_dec_value_1:
              value: cw_reserve_cmd_counter * 16
        data_2_dec_value_2:
              value: cw_gmsk_cmd_counter *2
        data_2_dec_value_3:
              value: 'cw_kill_sw.to_i == 1 ? 1 : 0'

        data_2_dec:
              value: data_2_dec_value_1 + data_2_dec_value_2 + data_2_dec_value_3

        data_2_hex_left:
              value: data_2_dec / 16

        data_2_hex_left_digit:
              value: 'data_2_hex_left.to_s == "10" ? "a" : (data_2_hex_left.to_s == "11" ? "b" : (data_2_hex_left.to_s == "12" ? "c" : (data_2_hex_left.to_s == "13" ? "d" : (data_2_hex_left.to_s == "14" ? "e" : (data_2_hex_left.to_s == "15" ? "f" : data_2_hex_left.to_s)))))'

        data_2_hex_right:
              value: data_2_dec % 16

        data_2_hex_right_digit:
              value: 'data_2_hex_right.to_s == "10" ? "a" : (data_2_hex_right.to_s == "11" ? "b" : (data_2_hex_right.to_s == "12" ? "c" : (data_2_hex_right.to_s == "13" ? "d" : (data_2_hex_right.to_s == "14" ? "e" : (data_2_hex_right.to_s == "15" ? "f" : data_2_hex_right.to_s)))))'

        data_2_hex:
              value: data_2_hex_left_digit + data_2_hex_right_digit



        data_3_dec_value_1:
              value: cw_kill_counter * 64
        data_3_dec_value_2:
              value: 'cw_mission_pic_on_off.to_i == 1 ? 32 : 0'
        data_3_dec_value_3:
              value: 'cw_mis_error_flag.to_i == 1 ? 16 : 0'
        data_3_dec_value_4:
              value: 'cw_mis_end_flag.to_i == 1 ? 8 : 0'
        data_3_dec_value_5:
              value: 'cw_aprs_flag.to_i == 1 ? 4 : 0'
        data_3_dec_value_6:
              value: cw_current_mis

        data_3_dec:
              value: data_3_dec_value_1 + data_3_dec_value_2 + data_3_dec_value_3 + data_3_dec_value_4 + data_3_dec_value_5 + data_3_dec_value_6

        data_3_hex_left:
              value: data_3_dec / 16

        data_3_hex_left_digit:
              value: 'data_3_hex_left.to_s == "10" ? "a" : (data_3_hex_left.to_s == "11" ? "b" : (data_3_hex_left.to_s == "12" ? "c" : (data_3_hex_left.to_s == "13" ? "d" : (data_3_hex_left.to_s == "14" ? "e" : (data_3_hex_left.to_s == "15" ? "f" : data_3_hex_left.to_s)))))'

        data_3_hex_right:
              value: data_3_dec % 16

        data_3_hex_right_digit:
              value: 'data_3_hex_right.to_s == "10" ? "a" : (data_3_hex_right.to_s == "11" ? "b" : (data_3_hex_right.to_s == "12" ? "c" : (data_3_hex_right.to_s == "13" ? "d" : (data_3_hex_right.to_s == "14" ? "e" : (data_3_hex_right.to_s == "15" ? "f" : data_3_hex_right.to_s)))))'

        data_3_hex:
              value: data_3_hex_left_digit + data_3_hex_right_digit



        cw_beacon:
              value: batt_v_hex + batt_i_hex + batt_t_hex + bpb_t_hex + raw_i_hex + data_1_hex + data_2_hex + data_3_hex



  digital_beacon:
    seq:
      - id: type_check_1
        type:
          switch-on: check_1
          cases:
            0xcc: cam
            0x11: auto_gmsk_or_hk
            _: discard

    instances:
        check_1:
              type: u1
              pos: 17

  cam:
    seq:
      - id: cam_callsign_header
        type: str
        size: 14
        encoding: ASCII
        valid: '"JS1YMY0JS1YNI0"'
      - id: cam_ctrl
        type: u1
        valid: 0x3e
      - id: cam_pid
        type: u1
        valid: 0xf0
      - id: cam_sat_id
        type: u1
        valid: 0x53
      - id: cam_packet_id
        type: u1
        valid: 0xcc
      - id: cam_reserved
        type: u1
      - id: packet_number_byte1
        type: u1
      - id: packet_number_byte2
        type: u1
      - id: packet_number_byte3
        type: u1
      - id: cam_soi # start of image
        type: u2
        valid: 0xffd8
      - id: cam_jfif_marker
        type: u2
        valid: 0xffe0
      - id: cam_data_length
        type: u2
      - id: cam_jfif_id
        type: str
        size: 4
        encoding: ASCII
        valid: '"JFIF"'
      - id: cam_data
        type: base64
        size-eos: true

    types:
      base64:
        seq:
          - id: b64encstring
            process: satnogsdecoders.process.b64encode
            type: base64string
            size-eos: true
      base64string:
        seq:
          - id: cam_data_b64_encoded
            type: str
            encoding: UTF-8
            size-eos: true

    instances:
        cam_packet_number:
              value: ((packet_number_byte1 << 16) | (packet_number_byte2 << 8) | packet_number_byte3)
        beacon_type:
              value:  '0 == 0 ? "CAM" : "CAM"'

  auto_gmsk_or_hk:
    seq:
      - id: type_check_2
        type:
          switch-on: check_2
          cases:
            0x33: hk # we hope that auto_gmsk will never be 0x33 at position 23
            _: auto_gmsk

    instances:
        check_2:
              type: u1
              pos: 22

  discard:
    seq:
      - id: first_byte
        type: u1
        valid: 0x00

  hk:
    seq:
      - id: hk_callsign_header
        type: str
        size: 14
        encoding: ASCII
        valid: '"JS1YMY0JS1YNI0"' # 4a5331594d59304a5331594e4930
      - id: hk_header_last_part_0
        type: u2
        valid: 0x3ef0
      - id: hk_header_last_part_1
        type: u2
        valid: 0x5311
      - id: hk_header_last_part_2
        type: u2
        valid: 0xff00
      - id: hk_header_last_part_3
        type: u2
        valid: 0x0001
      - id: hk_header
        valid: 0x33
        type: u1
      - id: seconds
        type: u1 
      - id: minutes
        type: u1
      - id: hours 
        type: u1 
      - id: days 
        type: u2
      - id: n_a
        type: u2
      - id: temp_minus_x
        type: u2
      - id: temp_plus_y
        type: u2
      - id: temp_minus_y
        type: u2
      - id: temp_plus_z
        type: u2
      - id: temp_minus_z
        type: u2
      - id: bpb_t
        type: u2
      - id: voltage_minus_x
        type: u2
      - id: voltage_plus_y
        type: u2
      - id: voltage_minus_y
        type: u2
      - id: voltage_plus_z
        type: u2
      - id: voltage_minus_z
        type: u2
      - id: current_minus_x
        type: u1
      - id: current_plus_y
        type: u1
      - id: current_minus_y
        type: u1
      - id: current_plus_z
        type: u1
      - id: current_minus_z
        type: u1
      - id: batt_t
        type: u1
      - id: batt_v
        type: u1
      - id: batt_i
        type: u2
      - id: raw_v # identical to latter one (named raw_v_1)
        type: u1
      - id: raw_i
        type: u2
      - id: src_v
        type: u1
      - id: src_i 
        type: u2
      - id: kill_sw
        type: u1
      - id: raw_v_1 # identical to raw_v
        type: u1
      - id: q3v3_1_i
        type: u1
      - id: q3v3_2_i
        type: u1
      - id: com_i
        type: u1
      - id: ant_dep_i
        type: u1
      - id: q5v0_i
        type: u1
      - id: reset_raw_v_mon
        type: b1
      - id: power_com
        type: b1
      - id: power_5v0
        type: b1
      - id: dcdc_3v3_1
        type: b1
      - id: pwr_ant_dep
        type: b1
      - id: pwr_3v3_2
        type: b1
      - id: pwr_3v3_1
        type: b1
      - id: dcdc_5v0
        type: b1
      - id: dcdc_3v3_2
        type: b1
      - id: pwr_compic
        type: b1
      - id: pwr_mainpic
        type: b1
      - id: empty
        type: b5
      - id: mp_reset_counter
        type: u1
      - id: rssi
        type: u1
      - id: com_t
        type: u1
      - id: com_seq_counter
        type: u1
      - id: cmd_uplink_counter
        type: u1
      - id: mis_ack
        type: u1
      - id: n_a_2
        type: u1
      - id: current_mis
        type: u1
      - id: mis_counter
        type: u1
      - id: checksum
        type: u1

    instances:
        beacon_type:
              value:  '0 == 0 ? "HK" : "HK"'

  auto_gmsk:
    seq:
      - id: auto_gmsk_callsign_header
        type: str
        size: 14
        encoding: ASCII
        valid: '"JS1YMY0JS1YNI0"' # 4a5331594d59304a5331594e4930
      - id: auto_gmsk_header_last_part
        type: u2
        valid: 0x3ef0
      - id: auto_gmsk_header_last_part_1
        type: u2
        valid: 0x5311
      - id: auto_gmsk_header_last_part_2
        type: u2
        valid: 0xff00
      - id: auto_gmsk_header_last_part_3
        type: u2
        valid: 0x0001
      - id: flag_data_address
        type: u4
      - id: commands_reserved_data_address
        type: u4
      - id: log_data_address
        type: u4
      - id: hk_data_address
        type: u4
      - id: cw_data_address
        type: u4
      - id: high_sampling_hk_data_address
        type: u4
      - id: aprs_message_data_address
        type: u4
      - id: aprs_log_data_address
        type: u4
      - id: mission_log_data_address
        type: u4
      - id: sun_camera_thumbnail_address
        type: u4
      - id: earth_camera_thumbnail_address
        type: u4
      - id: sun_camera_image_address
        type: u4
      - id: earth_camera_image_address
        type: u4
      - id: sun_sensor_log_data_address
        type: u4
      - id: flash_memory_rewrite_count
        type: u4
      - id: antenna_deployment_attempts_count
        type: u1
      - id: ongoing_mission
        type: u1
      - id: reserved_command
        type: u1
      - id: kill_switch_flag
        type: u1

    instances:
        beacon_type:
              value:  '0 == 0 ? "AUTO GMSK" : "AUTO GMSK"'

  digi:
    seq:
      - id: ax25_frame
        type: ax25_frame
        doc-ref: 'https://www.tapr.org/pub_ax25.html'

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: payload
            type:
              switch-on: ax25_header.ctl & 0x13
              cases:
                0x03: ui_frame
                0x13: ui_frame
                0x00: i_frame
                0x02: i_frame
                0x10: i_frame
                0x12: i_frame
                # 0x11: s_frame

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
          - id: repeater
            type: repeater
            if: (src_ssid_raw.ssid_mask & 0x01) == 0
            doc: 'Repeater flag is set!'
          - id: ctl
            type: u1

      repeater:
        seq:
          - id: rpt_instance
            type: repeaters
            repeat: until
            repeat-until: ((_.rpt_ssid_raw.ssid_mask & 0x1) == 0x1)
            doc: 'Repeat until no repeater flag is set!'

      repeaters:
        seq:
          - id: rpt_callsign_raw
            type: callsign_raw
          - id: rpt_ssid_raw
            type: ssid_mask

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

      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x0f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

      i_frame:
        seq:
          - id: pid
            type: u1
          - id: ax25_info
            type: ax25_info_data
            size-eos: true

      ui_frame:
        seq:
          - id: pid
            type: u1
          - id: ax25_info
            type: ax25_info_data
            size-eos: true

      ax25_info_data:
        seq:
          - id: data_monitor
            type: str
            encoding: utf-8
            size-eos: true

    instances:
        beacon_type:
              value:  '0 == 0 ? "DIGI" : "DIGI"'
