---
meta:
  id: botan
  title: Botan CW, HK, CAM, GYRO beacon + Digi decoder
  endian: be
doc-ref: "https://sites.google.com/p.chibakoudai.jp/gardens-04/satellite/downlink-format"
# 2025-10-12, DL7NDR
doc: |
  :field cw_batt_v: satellite.type_check.cw_batt_v
  :field cw_batt_i: satellite.type_check.cw_batt_i
  :field cw_batt_t: satellite.type_check.cw_batt_t
  :field cw_bpb_t: satellite.type_check.cw_bpb_t
  :field cw_raw_i: satellite.type_check.cw_raw_i
  :field cw_power_5v0: satellite.type_check.cw_power_5v0
  :field cw_pwr_ant_dep: satellite.type_check.cw_pwr_ant_dep
  :field cw_power_com: satellite.type_check.cw_power_com
  :field cw_sap_minus_x: satellite.type_check.cw_sap_minus_x
  :field cw_sap_plus_y: satellite.type_check.cw_sap_plus_y
  :field cw_sap_minus_y: satellite.type_check.cw_sap_minus_y
  :field cw_sap_plus_z: satellite.type_check.cw_sap_plus_z
  :field cw_sap_minus_z: satellite.type_check.cw_sap_minus_z
  :field cw_reserve_cmd_counter: satellite.type_check.cw_reserve_cmd_counter
  :field cw_gmsk_cmd_counter: satellite.type_check.cw_gmsk_cmd_counter
  :field cw_kill_sw: satellite.type_check.cw_kill_sw
  :field cw_kill_counter: satellite.type_check.cw_kill_counter
  :field cw_mission_pic_on_off: satellite.type_check.cw_mission_pic_on_off
  :field cw_mis_error_flag: satellite.type_check.cw_mis_error_flag
  :field cw_mis_end_flag: satellite.type_check.cw_mis_end_flag
  :field cw_aprs_flag: satellite.type_check.cw_aprs_flag
  :field cw_current_mis: satellite.type_check.cw_current_mis
  :field cw_beacon: satellite.type_check.cw_beacon
  :field beacon_type: satellite.type_check.beacon_type

  :field hk_packet_sequence_number: satellite.type_check.type_check_1.hk_packet_sequence_number
  :field seconds: satellite.type_check.type_check_1.seconds
  :field minutes: satellite.type_check.type_check_1.minutes
  :field hours: satellite.type_check.type_check_1.hours
  :field days: satellite.type_check.type_check_1.days
  :field temp_plus_x: satellite.type_check.type_check_1.temp_plus_x
  :field temp_minus_x: satellite.type_check.type_check_1.temp_minus_x
  :field temp_plus_y: satellite.type_check.type_check_1.temp_plus_y
  :field temp_minus_y: satellite.type_check.type_check_1.temp_minus_y
  :field temp_plus_z: satellite.type_check.type_check_1.temp_plus_z
  :field temp_minus_z: satellite.type_check.type_check_1.temp_minus_z
  :field temp_cigs: satellite.type_check.type_check_1.temp_cigs
  :field bpb_t: satellite.type_check.type_check_1.bpb_t
  :field voltage_minus_x: satellite.type_check.type_check_1.voltage_minus_x
  :field voltage_plus_y: satellite.type_check.type_check_1.voltage_plus_y
  :field voltage_minus_y: satellite.type_check.type_check_1.voltage_minus_y
  :field voltage_plus_z: satellite.type_check.type_check_1.voltage_plus_z
  :field voltage_minus_z: satellite.type_check.type_check_1.voltage_minus_z
  :field current_minus_x: satellite.type_check.type_check_1.current_minus_x
  :field current_plus_y: satellite.type_check.type_check_1.current_plus_y
  :field current_minus_y: satellite.type_check.type_check_1.current_minus_y
  :field current_plus_z: satellite.type_check.type_check_1.current_plus_z
  :field current_minus_z: satellite.type_check.type_check_1.current_minus_z
  :field batt_t: satellite.type_check.type_check_1.batt_t
  :field batt_v: satellite.type_check.type_check_1.batt_v
  :field batt_i: satellite.type_check.type_check_1.batt_i
  :field raw_v: satellite.type_check.type_check_1.raw_v
  :field raw_i: satellite.type_check.type_check_1.raw_i
  :field src_v: satellite.type_check.type_check_1.src_v
  :field src_i: satellite.type_check.type_check_1.src_i
  :field kill_sw: satellite.type_check.type_check_1.kill_sw
  :field raw_v_1: satellite.type_check.type_check_1.raw_v_1
  :field q3v3_1_i: satellite.type_check.type_check_1.q3v3_1_i
  :field q3v3_2_i: satellite.type_check.type_check_1.q3v3_2_i
  :field com_i: satellite.type_check.type_check_1.com_i
  :field ant_dep_i: satellite.type_check.type_check_1.ant_dep_i
  :field q5v0_i: satellite.type_check.type_check_1.q5v0_i
  :field reset_raw_v_mon: satellite.type_check.type_check_1.reset_raw_v_mon
  :field power_com: satellite.type_check.type_check_1.power_com
  :field power_5v0: satellite.type_check.type_check_1.power_5v0
  :field dcdc_3v3_1: satellite.type_check.type_check_1.dcdc_3v3_1
  :field pwr_ant_dep: satellite.type_check.type_check_1.pwr_ant_dep
  :field pwr_3v3_2: satellite.type_check.type_check_1.pwr_3v3_2
  :field pwr_3v3_1: satellite.type_check.type_check_1.pwr_3v3_1
  :field dcdc_5v0: satellite.type_check.type_check_1.dcdc_5v0
  :field dcdc_3v3_2: satellite.type_check.type_check_1.dcdc_3v3_2
  :field pwr_compic: satellite.type_check.type_check_1.pwr_compic
  :field pwr_mainpic: satellite.type_check.type_check_1.pwr_mainpic
  :field empty: satellite.type_check.type_check_1.empty
  :field mp_reset_counter: satellite.type_check.type_check_1.mp_reset_counter
  :field rssi: satellite.type_check.type_check_1.rssi
  :field com_t: satellite.type_check.type_check_1.com_t
  :field com_seq_counter: satellite.type_check.type_check_1.com_seq_counter
  :field mis_ack: satellite.type_check.type_check_1.mis_ack
  :field n_a_2: satellite.type_check.type_check_1.n_a_2
  :field current_mis: satellite.type_check.type_check_1.current_mis
  :field mis_counter: satellite.type_check.type_check_1.mis_counter
  :field checksum: satellite.type_check.type_check_1.checksum
  :field beacon_type: satellite.type_check.type_check_1.beacon_type

  :field gyro_sat_id: satellite.type_check.type_check_1.type_check_2.gyro_sat_id
  :field gyro_packet_id: satellite.type_check.type_check_1.type_check_2.gyro_packet_id
  :field gyro_reserved_1: satellite.type_check.type_check_1.type_check_2.gyro_reserved_1
  :field gyro_header: satellite.type_check.type_check_1.type_check_2.gyro_header
  :field gyro_packet_number: satellite.type_check.type_check_1.type_check_2.gyro_packet_number
  :field gyro_time: satellite.type_check.type_check_1.type_check_2.gyro_time
  :field gyro_n_a_1: satellite.type_check.type_check_1.type_check_2.gyro_n_a_1
  :field gyro_n_a_2: satellite.type_check.type_check_1.type_check_2.gyro_n_a_2
  :field gyro_n_a_3: satellite.type_check.type_check_1.type_check_2.gyro_n_a_3
  :field gyro_vector_i: satellite.type_check.type_check_1.type_check_2.gyro_vector_i
  :field gyro_vector_j: satellite.type_check.type_check_1.type_check_2.gyro_vector_j
  :field gyro_vector_k: satellite.type_check.type_check_1.type_check_2.gyro_vector_k
  :field gyro_vector_w: satellite.type_check.type_check_1.type_check_2.gyro_vector_w
  :field gyro_reserved_2: satellite.type_check.type_check_1.type_check_2.gyro_reserved_2
  :field gyro_sap_current_minus_x: satellite.type_check.type_check_1.type_check_2.gyro_sap_current_minus_x
  :field gyro_sap_current_plus_y: satellite.type_check.type_check_1.type_check_2.gyro_sap_current_plus_y
  :field gyro_sap_current_minus_y: satellite.type_check.type_check_1.type_check_2.gyro_sap_current_minus_y
  :field gyro_sap_current_plus_z: satellite.type_check.type_check_1.type_check_2.gyro_sap_current_plus_z
  :field gyro_sap_current_minus_z: satellite.type_check.type_check_1.type_check_2.gyro_sap_current_minus_z
  :field gyro_reserved_3: satellite.type_check.type_check_1.type_check_2.gyro_reserved_3
  :field beacon_type: satellite.type_check.type_check_1.type_check_2.beacon_type

  :field cam_sat_id: satellite.type_check.type_check_1.type_check_2.cam_sat_id
  :field cam_packet_id: satellite.type_check.type_check_1.type_check_2.cam_packet_id
  :field cam_reserved: satellite.type_check.type_check_1.type_check_2.cam_reserved
  :field cam_packet_number: satellite.type_check.type_check_1.type_check_2.cam_packet_number
  :field cam_data_b64_encoded: satellite.type_check.type_check_1.type_check_2.cam_data.b64encstring.cam_data_b64_encoded
  :field beacon_type: satellite.type_check.type_check_1.type_check_2.beacon_type

  :field dest_callsign: satellite.type_check.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: satellite.type_check.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: satellite.type_check.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: satellite.type_check.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: satellite.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: satellite.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: satellite.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field ctl: satellite.type_check.ax25_frame.ax25_header.ctl
  :field pid: satellite.type_check.ax25_frame.ax25_header.pid
  :field digi_message: satellite.type_check.ax25_frame.ax25_info.digi_message
  :field beacon_type: satellite.type_check.beacon_type

seq:
  - id: satellite
    type: satellite_t

types:
  satellite_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x626F7461: cw # bota
            0x94a662b2: digital_beacon # JS1Y  :decision, if HK, CAM or GYRO
            _: digi # everything else

    instances:
        check:
              type: u4
              pos: 0

  cw:
    seq:
      - id: cw_callsign_and_satellite_name
        type: str
        size: 12
        encoding: ASCII
        valid: '"botan js1ypt"' # 62 6F 74 61 6E 20 6A 73 31 79 70 74
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
            0x11: hk
            0xcc: gyro_or_cam
            _: discard

    instances:
        check_1:
              type: u1
              pos: 17

  hk:
    seq:
      - id: hk_callsign_header_1
        type: u8
        valid: 0x94a662b29ab26094
      - id: hk_callsign_header_2
        type: u8
        valid: 0xa662b2a0a86103f0
      - id: hk_callsign_header_3
        type: u2
        valid: 0x4211
      - id: hk_callsign_header_4
        type: u1
        valid: 0xff
      - id: hk_packet_sequence_number
        type: b24
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
      - id: temp_plus_x
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
      - id: temp_cigs
        type: u1
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

  discard:
    seq:
      - id: first_byte
        type: u1
        valid: 0x00


  gyro_or_cam:
    seq:
      - id: type_check_2
        type:
          switch-on: check_2
          cases:
            0xD0: gyro
            _: cam

    instances:
        check_2:
              type: u1
              pos: 19

  gyro:
    seq:
      - id: gyro_callsign_header_1
        type: u8
        valid: 0x94a662b29ab26094
      - id: gyro_callsign_header_2
        type: u8
        valid: 0xa662b2a0a8613ef0
      - id: gyro_sat_id
        type: u1
        valid: 0x42
      - id: gyro_packet_id
        type: u1
        valid: 0xcc
      - id: gyro_reserved_1
        type: u1
        valid: 0xff
      - id: gyro_header
        type: u1
        valid: 0xd0
      - id: gyro_packet_number
        type: u2
      - id: gyro_time
        type: u2
      - id: gyro_n_a_1
        type: u4
      - id: gyro_n_a_2
        type: u2
      - id: gyro_n_a_3
        type: u1
      - id: gyro_vector_i
        type: u2
      - id: gyro_vector_j
        type: u2
      - id: gyro_vector_k
        type: u2
      - id: gyro_vector_w
        type: u2
      - id: gyro_reserved_2
        type: u1
      - id: gyro_sap_current_minus_x
        type: u2
      - id: gyro_sap_current_plus_y
        type: u2
      - id: gyro_sap_current_minus_y
        type: u2
      - id: gyro_sap_current_plus_z
        type: u2
      - id: gyro_sap_current_minus_z
        type: u2
      - id: gyro_reserved_3
        type: u1

    instances:
        beacon_type:
              value:  '0 == 0 ? "GYRO" : "GYRO"'


  cam:
    seq:
      - id: cam_callsign_header_1
        type: u8
        valid: 0x94a662b29ab26094
      - id: cam_callsign_header_2
        type: u8
        valid: 0xa662b2a0a8613ef0
      - id: cam_sat_id
        type: u1
        valid: 0x42
      - id: cam_packet_id
        type: u1
        valid: 0xcc
      - id: cam_reserved
        type: u1
        valid: 0xff
      - id: cam_packet_number
        type: b24
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
        beacon_type:
              value:  '0 == 0 ? "CAM" : "CAM"'



  digi:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: ax25_info
            type: ax25_info_data
            size-eos: true

      ax25_info_data:
        seq:
          - id: digi_message
            type: str
            encoding: utf-8
            size-eos: true


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
          - id: pid
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
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

    instances:
        beacon_type:
              value:  '0 == 0 ? "DIGI" : "DIGI"'
