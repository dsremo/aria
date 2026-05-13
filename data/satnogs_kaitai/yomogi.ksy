---
meta:
  id: yomogi
  title: YOMOGI CW, HK + Digi decoder
  endian: be 
doc-ref: https://sites.google.com/s.chibakoudai.jp/gardens-01-yomogi/eng/satellite-eng/documents/transmission-format
# 2024-12-08, DL7NDR + 徳永 大輝 (TOKUNAGA Daiki)
doc: |
  :field beacon_type: yomogi.type_check.beacon_type
  :field header: yomogi.type_check.header
  :field rssi_temp_or_sms: yomogi.type_check.rssi_temp_or_sms
  :field type_id: yomogi.type_check.type_id
  :field batt_v: yomogi.type_check.batt_v
  :field batt_i: yomogi.type_check.batt_i
  :field batt_t: yomogi.type_check.batt_t
  :field ad_counter: yomogi.type_check.ad_counter
  :field batt_heater: yomogi.type_check.batt_heater
  :field kill_sw_main: yomogi.type_check.kill_sw_main
  :field kill_sw_fab: yomogi.type_check.kill_sw_fab
  :field sap_minus_x: yomogi.type_check.sap_minus_x
  :field sap_plus_y: yomogi.type_check.sap_plus_y
  :field sap_minus_y: yomogi.type_check.sap_minus_y
  :field sap_plus_z: yomogi.type_check.sap_plus_z
  :field sap_minus_z: yomogi.type_check.sap_minus_z
  :field time_after_reset: yomogi.type_check.time_after_reset
  :field raw_i: yomogi.type_check.raw_i
  :field reset_raw_v_mon: yomogi.type_check.reset_raw_v_mon
  :field lcl_uhf_com: yomogi.type_check.lcl_uhf_com
  :field lcl_5v0: yomogi.type_check.lcl_5v0
  :field dcdc_fab: yomogi.type_check.dcdc_fab
  :field lcl_depant: yomogi.type_check.lcl_depant
  :field lcl_3v3_2: yomogi.type_check.lcl_3v3_2
  :field lcl_fab: yomogi.type_check.lcl_fab
  :field dcdc_5v0: yomogi.type_check.dcdc_5v0
  :field dcdc_3v3_2: yomogi.type_check.dcdc_3v3_2
  :field lcl_compic: yomogi.type_check.lcl_compic
  :field lcl_mainpic: yomogi.type_check.lcl_mainpic
  :field gmsk_cmd_counter: yomogi.type_check.gmsk_cmd_counter
  :field reserve_cmd_counter: yomogi.type_check.reserve_cmd_counter
  :field uplink_success: yomogi.type_check.uplink_success
  :field kill_counter: yomogi.type_check.kill_counter
  :field bpb_t: yomogi.type_check.bpb_t
  :field cw_beacon: yomogi.type_check.cw_beacon
  :field hk_header_2: yomogi.type_check.hk_header_2
  :field hk_seconds: yomogi.type_check.hk_seconds
  :field hk_minutes: yomogi.type_check.hk_minutes
  :field hk_hours: yomogi.type_check.hk_hours
  :field hk_days: yomogi.type_check.hk_days
  :field hk_temp_plus_x: yomogi.type_check.hk_temp_plus_x
  :field hk_temp_minus_x: yomogi.type_check.hk_temp_minus_x
  :field hk_temp_plus_y: yomogi.type_check.hk_temp_plus_y
  :field hk_temp_minus_y: yomogi.type_check.hk_temp_minus_y
  :field hk_temp_plus_z: yomogi.type_check.hk_temp_plus_z
  :field hk_temp_minus_z: yomogi.type_check.hk_temp_minus_z
  :field hk_bpb_t: yomogi.type_check.hk_bpb_t
  :field hk_voltage_minus_x: yomogi.type_check.hk_voltage_minus_x
  :field hk_voltage_plus_y: yomogi.type_check.hk_voltage_plus_y
  :field hk_voltage_minus_y: yomogi.type_check.hk_voltage_minus_y
  :field hk_voltage_plus_z: yomogi.type_check.hk_voltage_plus_z
  :field hk_voltage_minus_z: yomogi.type_check.hk_voltage_minus_z
  :field hk_current_minus_x: yomogi.type_check.hk_current_minus_x
  :field hk_current_plus_y: yomogi.type_check.hk_current_plus_y
  :field hk_current_minus_y: yomogi.type_check.hk_current_minus_y
  :field hk_current_plus_z: yomogi.type_check.hk_current_plus_z
  :field hk_current_minus_z: yomogi.type_check.hk_current_minus_z
  :field hk_batt_t: yomogi.type_check.hk_batt_t
  :field hk_batt_v: yomogi.type_check.hk_batt_v
  :field hk_batt_i: yomogi.type_check.hk_batt_i
  :field hk_fab_raw_v: yomogi.type_check.hk_fab_raw_v
  :field hk_fab_raw_i: yomogi.type_check.hk_fab_raw_i
  :field hk_src_v: yomogi.type_check.hk_src_v
  :field hk_src_i: yomogi.type_check.hk_src_i
  :field hk_heater_flag: yomogi.type_check.hk_heater_flag
  :field hk_kill_sw: yomogi.type_check.hk_kill_sw
  :field hk_reset_raw_v: yomogi.type_check.hk_reset_raw_v
  :field hk_v3_3_no1_i: yomogi.type_check.hk_v3_3_no1_i
  :field hk_v3_3_no2_i: yomogi.type_check.hk_v3_3_no2_i
  :field hk_uhf_com_i: yomogi.type_check.hk_uhf_com_i
  :field hk_ant_dep_i: yomogi.type_check.hk_ant_dep_i
  :field hk_v5_0_i: yomogi.type_check.hk_v5_0_i
  :field hk_reset_sw_status: yomogi.type_check.hk_reset_sw_status
  :field hk_reserve_cmd_0_cmd0: yomogi.type_check.hk_reserve_cmd_0_cmd0
  :field hk_reserve_cmd_0_cmd1: yomogi.type_check.hk_reserve_cmd_0_cmd1
  :field hk_reserve_cmd_0_cmd2: yomogi.type_check.hk_reserve_cmd_0_cmd2
  :field hk_reserve_cmd_0_cmd3: yomogi.type_check.hk_reserve_cmd_0_cmd3
  :field hk_reserve_cmd_0_cmd4: yomogi.type_check.hk_reserve_cmd_0_cmd4
  :field hk_reserve_cmd_0_cmd5: yomogi.type_check.hk_reserve_cmd_0_cmd5
  :field hk_reserve_cmd_0_cmd6: yomogi.type_check.hk_reserve_cmd_0_cmd6
  :field hk_reserve_cmd_0_cmd7: yomogi.type_check.hk_reserve_cmd_0_cmd7
  :field hk_reserve_cmd_1_cmd0: yomogi.type_check.hk_reserve_cmd_1_cmd0
  :field hk_reserve_cmd_1_cmd1: yomogi.type_check.hk_reserve_cmd_1_cmd1
  :field hk_reserve_cmd_1_cmd2: yomogi.type_check.hk_reserve_cmd_1_cmd2
  :field hk_reserve_cmd_1_cmd3: yomogi.type_check.hk_reserve_cmd_1_cmd3
  :field hk_reserve_cmd_1_cmd4: yomogi.type_check.hk_reserve_cmd_1_cmd4
  :field hk_reserve_cmd_1_cmd5: yomogi.type_check.hk_reserve_cmd_1_cmd5
  :field hk_reserve_cmd_1_cmd6: yomogi.type_check.hk_reserve_cmd_1_cmd6
  :field hk_reserve_cmd_1_cmd7: yomogi.type_check.hk_reserve_cmd_1_cmd7
  :field digi_dest_callsign: yomogi.type_check.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field digi_src_callsign: yomogi.type_check.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field digi_src_ssid: yomogi.type_check.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field digi_dest_ssid: yomogi.type_check.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: yomogi.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: yomogi.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: yomogi.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field digi_ctl: yomogi.type_check.ax25_frame.ax25_header.ctl
  :field digi_pid: yomogi.type_check.ax25_frame.ax25_header.pid
  :field digi_message: yomogi.type_check.ax25_frame.ax25_info.digi_message
        
seq:
  - id: yomogi
    type: yomogi_t

types:
  yomogi_t:
    seq:
      - id: type_check
        type:
          switch-on: format_identifier
          cases:
           0x796f6d6f6769206a: cw
           0x4a4736594257304a: hk
           _: aprs

    instances:
        format_identifier:
              type: u8
              pos: 0

  cw:
    seq:
      - id: header
        type: str
        size: 14
        encoding: ASCII
        valid: '"yomogi js1ymx "' # 79 6F 6D 6F 67 69 20 6A 73 31 79 6D 78 20
      
      - id: rssi_temp_or_sms # RSSI & Temp or Short Messaging Service
        type: str
        size: 6
        encoding: ASCII

      - id: space
        type: str
        size: 1
        encoding: ASCII
        valid: '" "' # 20

      - id: byte_1
        type: u1

      - id: byte_2
        type: u1

      - id: byte_3
        type: u1

      - id: byte_4
        type: u1

      - id: byte_5
        type: u1

      - id: lengthcheck 
        type: str
        encoding: utf-8
        size-eos: true # accepts zero length


    instances:
      necessary_for_lengthcheck:
        if: lengthcheck.length != 0 # if so, whole frame will be discarded
        value: lengthcheck.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

# acquiring type id
      type_id:
        value: (byte_4 & 0b10000000) >> 7

#cw_1
      batt_v:
        if: type_id == 0
        value: byte_1
      batt_i:
        if: type_id == 0
        value: byte_2
      batt_t:
        if: type_id == 0
        value: byte_3
      ad_counter:
        if: type_id == 0
        value: (byte_4 & 0b00000110) >> 1
      batt_heater:
        if: type_id == 0
        value: (byte_4 & 0b00001000) >> 3
      kill_sw_main:
        if: type_id == 0
        value: (byte_4 & 0b00010000) >> 4
      kill_sw_fab:
        if: type_id == 0
        value: (byte_4 & 0b00100000) >> 5
      sap_minus_x:
        if: type_id == 0
        value: (byte_4 & 0b01000000) >> 6
      sap_plus_y:
        if: type_id == 0
        value: (byte_4 & 0b10000000) >> 7
      sap_minus_y:
        if: type_id == 0
        value: (byte_5 & 0b00000001)
      sap_plus_z:
        if: type_id == 0
        value: (byte_5 & 0b00000010) >> 1
      sap_minus_z:
        if: type_id == 0
        value: (byte_5 & 0b00000100) >> 2
      time_after_reset:
        if: type_id == 0
        value: (byte_5 & 0b11111000) >> 3
#cw_2
      raw_i:
        if: type_id == 1
        value: byte_1
      reset_raw_v_mon:
        if: type_id == 1
        value: (byte_2 & 0b00000001)
      lcl_uhf_com:
        if: type_id == 1
        value: (byte_2 & 0b00000010) >> 1
      lcl_5v0:
        if: type_id == 1
        value: (byte_2 & 0b00000100) >> 2
      dcdc_fab:
        if: type_id == 1
        value: (byte_2 & 0b00001000) >>3
      lcl_depant:
        if: type_id == 1
        value: (byte_2 & 0b00010000) >>4
      lcl_3v3_2:
        if: type_id == 1
        value: (byte_2 & 0b00100000) >>5
      lcl_fab:
        if: type_id == 1
        value: (byte_2 & 0b01000000) >>6
      dcdc_5v0:
        if: type_id == 1
        value: (byte_2 & 0b10000000) >>7
      dcdc_3v3_2:
        if: type_id == 1
        value: (byte_3 & 0b00000001) 
      lcl_compic:
        if: type_id == 1
        value: (byte_3 & 0b00000010) >>1
      lcl_mainpic:
        if: type_id == 1
        value: (byte_3 & 0b00000100) >>2
      gmsk_cmd_counter:
        if: type_id == 1
        value: (byte_3 & 0b11111000) >>3
      reserve_cmd_counter:
        if: type_id == 1
        value: (byte_4 & 0b00001110) >>1
      uplink_success:
        if: type_id == 1
        value: (byte_4 & 0b00010000) >>4
      kill_counter:
        if: type_id == 1
        value: (byte_4 & 0b11100000) >>5
      bpb_t:
        if: type_id == 1
        value: byte_5

      beacon_type:
        value:  '0 == 0 ? "CW" : "CW"'

# reformating from integer to hex to get beacon

      byte_1_hex_left:
        value: byte_1 / 16

      byte_1_hex_left_digit:
        value: 'byte_1_hex_left.to_s == "10" ? "a" : (byte_1_hex_left.to_s == "11" ? "b" : (byte_1_hex_left.to_s == "12" ? "c" : (byte_1_hex_left.to_s == "13" ? "d" : (byte_1_hex_left.to_s == "14" ? "e" : (byte_1_hex_left.to_s == "15" ? "f" : byte_1_hex_left.to_s)))))'

      byte_1_hex_right:
        value: byte_1 % 16

      byte_1_hex_right_digit:
        value: 'byte_1_hex_right.to_s == "10" ? "a" : (byte_1_hex_right.to_s == "11" ? "b" : (byte_1_hex_right.to_s == "12" ? "c" : (byte_1_hex_right.to_s == "13" ? "d" : (byte_1_hex_right.to_s == "14" ? "e" : (byte_1_hex_right.to_s == "15" ? "f" : byte_1_hex_right.to_s)))))'

      byte_1_hex:
        value: byte_1_hex_left_digit + byte_1_hex_right_digit


      byte_2_hex_left:
        value: byte_2 / 16

      byte_2_hex_left_digit:
        value: 'byte_2_hex_left.to_s == "10" ? "a" : (byte_2_hex_left.to_s == "11" ? "b" : (byte_2_hex_left.to_s == "12" ? "c" : (byte_2_hex_left.to_s == "13" ? "d" : (byte_2_hex_left.to_s == "14" ? "e" : (byte_2_hex_left.to_s == "15" ? "f" : byte_2_hex_left.to_s)))))'

      byte_2_hex_right:
        value: byte_2 % 16

      byte_2_hex_right_digit:
        value: 'byte_2_hex_right.to_s == "10" ? "a" : (byte_2_hex_right.to_s == "11" ? "b" : (byte_2_hex_right.to_s == "12" ? "c" : (byte_2_hex_right.to_s == "13" ? "d" : (byte_2_hex_right.to_s == "14" ? "e" : (byte_2_hex_right.to_s == "15" ? "f" : byte_2_hex_right.to_s)))))'

      byte_2_hex:
        value: byte_2_hex_left_digit + byte_2_hex_right_digit


      byte_3_hex_left:
        value: byte_3 / 16

      byte_3_hex_left_digit:
        value: 'byte_3_hex_left.to_s == "10" ? "a" : (byte_3_hex_left.to_s == "11" ? "b" : (byte_3_hex_left.to_s == "12" ? "c" : (byte_3_hex_left.to_s == "13" ? "d" : (byte_3_hex_left.to_s == "14" ? "e" : (byte_3_hex_left.to_s == "15" ? "f" : byte_3_hex_left.to_s)))))'

      byte_3_hex_right:
        value: byte_3 % 16

      byte_3_hex_right_digit:
        value: 'byte_3_hex_right.to_s == "10" ? "a" : (byte_3_hex_right.to_s == "11" ? "b" : (byte_3_hex_right.to_s == "12" ? "c" : (byte_3_hex_right.to_s == "13" ? "d" : (byte_3_hex_right.to_s == "14" ? "e" : (byte_3_hex_right.to_s == "15" ? "f" : byte_3_hex_right.to_s)))))'

      byte_3_hex:
        value: byte_3_hex_left_digit + byte_3_hex_right_digit


      byte_4_hex_left:
        value: byte_4 / 16

      byte_4_hex_left_digit:
        value: 'byte_4_hex_left.to_s == "10" ? "a" : (byte_4_hex_left.to_s == "11" ? "b" : (byte_4_hex_left.to_s == "12" ? "c" : (byte_4_hex_left.to_s == "13" ? "d" : (byte_4_hex_left.to_s == "14" ? "e" : (byte_4_hex_left.to_s == "15" ? "f" : byte_4_hex_left.to_s)))))'

      byte_4_hex_right:
        value: byte_4 % 16

      byte_4_hex_right_digit:
        value: 'byte_4_hex_right.to_s == "10" ? "a" : (byte_4_hex_right.to_s == "11" ? "b" : (byte_4_hex_right.to_s == "12" ? "c" : (byte_4_hex_right.to_s == "13" ? "d" : (byte_4_hex_right.to_s == "14" ? "e" : (byte_4_hex_right.to_s == "15" ? "f" : byte_4_hex_right.to_s)))))'

      byte_4_hex:
        value: byte_4_hex_left_digit + byte_4_hex_right_digit


      byte_5_hex_left:
        value: byte_5 / 16

      byte_5_hex_left_digit:
        value: 'byte_5_hex_left.to_s == "10" ? "a" : (byte_5_hex_left.to_s == "11" ? "b" : (byte_5_hex_left.to_s == "12" ? "c" : (byte_5_hex_left.to_s == "13" ? "d" : (byte_5_hex_left.to_s == "14" ? "e" : (byte_5_hex_left.to_s == "15" ? "f" : byte_5_hex_left.to_s)))))'

      byte_5_hex_right:
        value: byte_5 % 16

      byte_5_hex_right_digit:
        value: 'byte_5_hex_right.to_s == "10" ? "a" : (byte_5_hex_right.to_s == "11" ? "b" : (byte_5_hex_right.to_s == "12" ? "c" : (byte_5_hex_right.to_s == "13" ? "d" : (byte_5_hex_right.to_s == "14" ? "e" : (byte_5_hex_right.to_s == "15" ? "f" : byte_5_hex_right.to_s)))))'

      byte_5_hex:
        value: byte_5_hex_left_digit + byte_5_hex_right_digit


      cw_beacon:
        value: byte_1_hex + " " + byte_2_hex + " " + byte_3_hex + " " + byte_4_hex + " " + byte_5_hex


  hk:
    seq:
      - id: hk_header_1
        type: str
        size: 14
        encoding: ASCII
        valid: '"JG6YBW0JG6YMX0"' # 4a4736594257304a4736594d5830

      - id: hk_header_2 # e3f0fff0ff000002 can be different
        type: u8

      - id: hk_header_3
        type: u2
        valid: 0x3333

      - id: hk_seconds
        type: u1 
      - id: hk_minutes
        type: u1
      - id: hk_hours 
        type: u1 
      - id: hk_days 
        type: u2

      - id: hk_delimiter_1
        type: b24
        valid: 0xaaaaaa

      - id: hk_temp_plus_x
        type: u2
      - id: hk_temp_minus_x
        type: u2
      - id: hk_temp_plus_y
        type: u2
      - id: hk_temp_minus_y
        type: u2
      - id: hk_temp_plus_z
        type: u2
      - id: hk_temp_minus_z
        type: u2
      - id: hk_bpb_t
        type: u2
      - id: hk_voltage_minus_x
        type: u2
      - id: hk_voltage_plus_y
        type: u2
      - id: hk_voltage_minus_y
        type: u2
      - id: hk_voltage_plus_z
        type: u2
      - id: hk_voltage_minus_z
        type: u2
      - id: hk_current_minus_x
        type: u1
      - id: hk_current_plus_y
        type: u1
      - id: hk_current_minus_y
        type: u1
      - id: hk_current_plus_z
        type: u1
      - id: hk_current_minus_z
        type: u1
      - id: hk_batt_t
        type: u1
      - id: hk_batt_v
        type: u1
      - id: hk_batt_i
        type: u2
      - id: hk_fab_raw_v
        type: u1
      - id: hk_fab_raw_i
        type: u1
      - id: hk_src_v
        type: u1
      - id: hk_src_i 
        type: u2
      - id: hk_heater_flag
        type: u1
      - id: hk_kill_sw
        type: u1

      - id: delimiter_2
        type: u1
        valid: 0xbb

      - id: hk_reset_raw_v
        type: u1
      - id: hk_v3_3_no1_i
        type: u1
      - id: hk_v3_3_no2_i
        type: u1
      - id: hk_uhf_com_i
        type: u1
      - id: hk_ant_dep_i
        type: u1
      - id: hk_v5_i
        type: u1
      - id: hk_reset_sw_status
        type: u2

      - id: delimiter_3
        type: u1
        valid: 0xcc

      - id: hk_reserve_cmd_0_cmd0
        type: u1
      - id: hk_reserve_cmd_0_cmd1
        type: u1
      - id: hk_reserve_cmd_0_cmd2
        type: u1
      - id: hk_reserve_cmd_0_cmd3
        type: u1
      - id: hk_reserve_cmd_0_cmd4
        type: u1
      - id: hk_reserve_cmd_0_cmd5
        type: u1
      - id: hk_reserve_cmd_0_cmd6
        type: u1
      - id: hk_reserve_cmd_0_cmd7
        type: u1

      - id: hk_reserve_cmd_1_cmd0
        type: u1
      - id: hk_reserve_cmd_1_cmd1
        type: u1
      - id: hk_reserve_cmd_1_cmd2
        type: u1
      - id: hk_reserve_cmd_1_cmd3
        type: u1
      - id: hk_reserve_cmd_1_cmd4
        type: u1
      - id: hk_reserve_cmd_1_cmd5
        type: u1
      - id: hk_reserve_cmd_1_cmd6
        type: u1
      - id: hk_reserve_cmd_1_cmd7
        type: u1

      - id: delimiter_4
        type: u4
        valid: 0x44444444

    instances:
        beacon_type:
              value:  '0 == 0 ? "HK" : "HK"'


  aprs:
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
