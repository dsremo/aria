---
meta:
  id: dragonfly
  title: Dragonfly (BIRDS-X) CW, GMSK Beacon and Digi Decoder
  endian: be
doc-ref: "https://birds-x.birds-project.com/satellite-information/"
# 2025-09-16, DL7NDR
doc: |
  :field cw_name_callsign: id1.id2.cw_name_callsign
  :field bat_v: id1.id2.bat_v
  :field bat_i: id1.id2.bat_i
  :field bat_t: id1.id2.bat_t
  :field kill_main: id1.id2.kill_main
  :field kill_fab: id1.id2.kill_fab
  :field solar_cell_plus_x: id1.id2.solar_cell_plus_x
  :field solar_cell_plus_y: id1.id2.solar_cell_plus_y
  :field solar_cell_plus_z: id1.id2.solar_cell_plus_z
  :field solar_cell_minus_x: id1.id2.solar_cell_minus_x
  :field solar_cell_minus_y: id1.id2.solar_cell_minus_y
  :field solar_cell_minus_z: id1.id2.solar_cell_minus_z
  :field ant_1_deploy: id1.id2.ant_1_deploy
  :field ant_1_set_count: id1.id2.ant_1_set_count
  :field ant_2_deploy: id1.id2.ant_2_deploy
  :field ant_2_set_count: id1.id2.ant_2_set_count
  :field aprs_reference_1: id1.id2.aprs_reference_1
  :field aprs_reference_2: id1.id2.aprs_reference_2
  :field aprs_payload_1: id1.id2.aprs_payload_1
  :field aprs_payload_2: id1.id2.aprs_payload_2
  :field aprs_payload_3: id1.id2.aprs_payload_3
  :field aprs_payload_4: id1.id2.aprs_payload_4
  :field aprs_payload_5: id1.id2.aprs_payload_5
  :field main_pic_power_line_status: id1.id2.main_pic_power_line_status
  :field com_pic_power_line_status: id1.id2.com_pic_power_line_status
  :field v3_3_1_status: id1.id2.v3_3_1_status
  :field v3_3_2_status: id1.id2.v3_3_2_status
  :field v5_status: id1.id2.v5_status
  :field unreg1_status: id1.id2.unreg1_status
  :field unreg2_status: id1.id2.unreg2_status
  :field time_after_last_reset: id1.id2.time_after_last_reset
  :field necessary_for_lengthcheck: id1.id2.necessary_for_lengthcheck
  :field beacon_type: id1.id2.beacon_type
  :field cw_beacon: id1.id2.cw_beacon

  :field packet_number: id1.id2.id3.packet_number
  :field bat_v: id1.id2.id3.bat_v
  :field bat_i: id1.id2.id3.bat_i
  :field bat_t: id1.id2.id3.bat_t
  :field kill_main: id1.id2.id3.kill_main
  :field kill_fab: id1.id2.id3.kill_fab
  :field solar_cell_plus_x: id1.id2.id3.solar_cell_plus_x
  :field solar_cell_plus_y: id1.id2.id3.solar_cell_plus_y
  :field solar_cell_plus_z: id1.id2.id3.solar_cell_plus_z
  :field solar_cell_minus_x: id1.id2.id3.solar_cell_minus_x
  :field solar_cell_minus_y: id1.id2.id3.solar_cell_minus_y
  :field solar_cell_minus_z: id1.id2.id3.solar_cell_minus_z
  :field ant_1_deploy: id1.id2.id3.ant_1_deploy
  :field ant_1_set_count: id1.id2.id3.ant_1_set_count
  :field ant_2_deploy: id1.id2.id3.ant_2_deploy
  :field ant_2_set_count: id1.id2.id3.ant_2_set_count
  :field aprs_reference_1: id1.id2.id3.aprs_reference_1
  :field aprs_reference_2: id1.id2.id3.aprs_reference_2
  :field aprs_payload_1: id1.id2.id3.aprs_payload_1
  :field aprs_payload_2: id1.id2.id3.aprs_payload_2
  :field aprs_payload_3: id1.id2.id3.aprs_payload_3
  :field aprs_payload_4: id1.id2.id3.aprs_payload_4
  :field aprs_payload_5: id1.id2.id3.aprs_payload_5
  :field main_pic_power_line_status: id1.id2.id3.main_pic_power_line_status
  :field com_pic_power_line_status: id1.id2.id3.com_pic_power_line_status
  :field v3_3_1_status: id1.id2.id3.v3_3_1_status
  :field v3_3_2_status: id1.id2.id3.v3_3_2_status
  :field v5_status: id1.id2.id3.v5_status
  :field unreg1_status: id1.id2.id3.unreg1_status
  :field unreg2_status: id1.id2.id3.unreg2_status
  :field time_after_last_reset: id1.id2.id3.time_after_last_reset
  :field necessary_for_lengthcheck: id1.id2.id3.necessary_for_lengthcheck
  :field beacon_type: id1.id2.id3.beacon_type

  :field digi_dest_callsign: id1.id2.id3.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field digi_src_callsign: id1.id2.id3.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field digi_src_ssid: id1.id2.id3.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field digi_dest_ssid: id1.id2.id3.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: id1.id2.id3.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: id1.id2.id3.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: id1.id2.id3.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field digi_ctl: id1.id2.id3.ax25_frame.ax25_header.ctl
  :field digi_pid: id1.id2.id3.ax25_frame.ax25_header.pid
  :field digi_message: id1.id2.id3.ax25_frame.ax25_info.digi_message

seq:
  - id: id1
    type: type1

types:
  type1:
    seq:
      - id: id2
        type:
          switch-on: message_type1
          cases:
            0x647261676F6E666C: cw # dragonfl
            _: gmsk_or_digi

    instances:
      message_type1:
        type: u8
        pos: 0

  cw:
   seq:
     - id: cw_name_callsign
       type: str
       size: 15
       encoding: ASCII
       valid: '"dragonflyjg6yow"' # 64 72 61 67 6F 6E 66 6C 79 6A 67 36 79 6F 77

     - id: bat_v_raw
       type: u1

     - id: bat_i_raw
       type: u1

     - id: bat_t_raw
       type: u1

     - id: value1 # kill_main until solar_cell_minus_z
       type: u1

     - id: value2 # ant_1_deploy until ant_2_set_count
       type: u1

     - id: value3 # aprs_reference_1 until aprs_payload_5
       type: u1

     - id: value4 # main_pic_power_line_status until unreg2_status
       type: u1

     - id: time_after_last_reset
       type: u1

     - id: lengthcheck # the beacon should end by time_after_last_reset. if there is more to parse, the whole frame will be discarded due to 'necessary_for_lengthcheck'
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true

   instances:
          necessary_for_lengthcheck:
            if: lengthcheck.length != 0 # if so, whole frame will be discarded
            value: lengthcheck.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

          bat_v:
            value: 6.512 * bat_v_raw / 256

          bat_i:
            value: -2.99589 * bat_i_raw + 6129.78533

          bat_t:
            value: 75 - (bat_t_raw * 97.68 / 256)

          kill_main:
            value: (value1 & 0b10000000) >> 7

          kill_fab:
            value: (value1 & 0b01000000) >> 6

          solar_cell_plus_x:
            value: (value1 & 0b00100000) >> 5

          solar_cell_plus_y:
            value: (value1 & 0b00010000) >> 4

          solar_cell_plus_z:
            value: (value1 & 0b00001000) >> 3

          solar_cell_minus_x:
            value: (value1 & 0b00000100) >> 2

          solar_cell_minus_y:
            value: (value1 & 0b00000010) >> 1

          solar_cell_minus_z:
            value: value1 & 0b00000001

          ant_1_deploy:
            value: (value2 & 0b10000000) >> 7

          ant_1_set_count:
            value: (value2 & 0b01110000) >> 4

          ant_2_deploy:
            value: (value2 & 0b00001000) >> 3

          ant_2_set_count:
            value: value2 & 0b00000111

          aprs_reference_1:
            value: (value3 & 0b10000000) >> 7

          aprs_reference_2:
            value: (value3 & 0b01000000) >> 6

          aprs_payload_1:
            value: (value3 & 0b00100000) >> 5

          aprs_payload_2:
            value: (value3 & 0b00010000) >> 4

          aprs_payload_3:
            value: (value3 & 0b00001000) >> 3

          aprs_payload_4:
            value: (value3 & 0b00000100) >> 2

          aprs_payload_5:
            value: (value3 & 0b00000010) >> 1

          main_pic_power_line_status:
            value: (value4 & 0b10000000) >> 7

          com_pic_power_line_status:
            value: (value4 & 0b01000000) >> 6

          v3_3_1_status:
            value: (value4 & 0b00100000) >> 5

          v3_3_2_status:
            value: (value4 & 0b00010000) >> 4

          v5_status:
            value: (value4 & 0b00001000) >> 3

          unreg1_status:
            value: (value4 & 0b00000100) >> 2

          unreg2_status:
            value: (value4 & 0b00000010) >> 1

          beacon_type:
            value: '"CW"'


# reformating from integer to hex to show beacon

          bat_v_raw_hex_left:
            value: bat_v_raw / 16

          bat_v_raw_hex_left_digit:
            value: 'bat_v_raw_hex_left.to_s == "10" ? "a" : (bat_v_raw_hex_left.to_s == "11" ? "b" : (bat_v_raw_hex_left.to_s == "12" ? "c" : (bat_v_raw_hex_left.to_s == "13" ? "d" : (bat_v_raw_hex_left.to_s == "14" ? "e" : (bat_v_raw_hex_left.to_s == "15" ? "f" : bat_v_raw_hex_left.to_s)))))'

          bat_v_raw_hex_right:
            value: bat_v_raw % 16

          bat_v_raw_hex_right_digit:
            value: 'bat_v_raw_hex_right.to_s == "10" ? "a" : (bat_v_raw_hex_right.to_s == "11" ? "b" : (bat_v_raw_hex_right.to_s == "12" ? "c" : (bat_v_raw_hex_right.to_s == "13" ? "d" : (bat_v_raw_hex_right.to_s == "14" ? "e" : (bat_v_raw_hex_right.to_s == "15" ? "f" : bat_v_raw_hex_right.to_s)))))'

          bat_v_raw_hex:
            value: 'bat_v_raw_hex_left_digit + bat_v_raw_hex_right_digit == "ff" ? ".." : bat_v_raw_hex_left_digit + bat_v_raw_hex_right_digit' # "ff" is translated to ".."


          bat_i_raw_hex_left:
            value: bat_i_raw / 16

          bat_i_raw_hex_left_digit:
            value: 'bat_i_raw_hex_left.to_s == "10" ? "a" : (bat_i_raw_hex_left.to_s == "11" ? "b" : (bat_i_raw_hex_left.to_s == "12" ? "c" : (bat_i_raw_hex_left.to_s == "13" ? "d" : (bat_i_raw_hex_left.to_s == "14" ? "e" : (bat_i_raw_hex_left.to_s == "15" ? "f" : bat_i_raw_hex_left.to_s)))))'

          bat_i_raw_hex_right:
            value: bat_i_raw % 16

          bat_i_raw_hex_right_digit:
            value: 'bat_i_raw_hex_right.to_s == "10" ? "a" : (bat_i_raw_hex_right.to_s == "11" ? "b" : (bat_i_raw_hex_right.to_s == "12" ? "c" : (bat_i_raw_hex_right.to_s == "13" ? "d" : (bat_i_raw_hex_right.to_s == "14" ? "e" : (bat_i_raw_hex_right.to_s == "15" ? "f" : bat_i_raw_hex_right.to_s)))))'

          bat_i_raw_hex:
            value: 'bat_i_raw_hex_left_digit + bat_i_raw_hex_right_digit == "ff" ? ".." : bat_i_raw_hex_left_digit + bat_i_raw_hex_right_digit' # "ff" is translated to ".."


          bat_t_raw_hex_left:
            value: bat_t_raw / 16

          bat_t_raw_hex_left_digit:
            value: 'bat_t_raw_hex_left.to_s == "10" ? "a" : (bat_t_raw_hex_left.to_s == "11" ? "b" : (bat_t_raw_hex_left.to_s == "12" ? "c" : (bat_t_raw_hex_left.to_s == "13" ? "d" : (bat_t_raw_hex_left.to_s == "14" ? "e" : (bat_t_raw_hex_left.to_s == "15" ? "f" : bat_t_raw_hex_left.to_s)))))'

          bat_t_raw_hex_right:
            value: bat_t_raw % 16

          bat_t_raw_hex_right_digit:
            value: 'bat_t_raw_hex_right.to_s == "10" ? "a" : (bat_t_raw_hex_right.to_s == "11" ? "b" : (bat_t_raw_hex_right.to_s == "12" ? "c" : (bat_t_raw_hex_right.to_s == "13" ? "d" : (bat_t_raw_hex_right.to_s == "14" ? "e" : (bat_t_raw_hex_right.to_s == "15" ? "f" : bat_t_raw_hex_right.to_s)))))'

          bat_t_raw_hex:
            value: 'bat_t_raw_hex_left_digit + bat_t_raw_hex_right_digit == "ff" ? ".." : bat_t_raw_hex_left_digit + bat_t_raw_hex_right_digit' # "ff" is translated to ".."


          value1_hex_left:
            value: value1 / 16

          value1_hex_left_digit:
            value: 'value1_hex_left.to_s == "10" ? "a" : (value1_hex_left.to_s == "11" ? "b" : (value1_hex_left.to_s == "12" ? "c" : (value1_hex_left.to_s == "13" ? "d" : (value1_hex_left.to_s == "14" ? "e" : (value1_hex_left.to_s == "15" ? "f" : value1_hex_left.to_s)))))'

          value1_hex_right:
            value: value1 % 16

          value1_hex_right_digit:
            value: 'value1_hex_right.to_s == "10" ? "a" : (value1_hex_right.to_s == "11" ? "b" : (value1_hex_right.to_s == "12" ? "c" : (value1_hex_right.to_s == "13" ? "d" : (value1_hex_right.to_s == "14" ? "e" : (value1_hex_right.to_s == "15" ? "f" : value1_hex_right.to_s)))))'

          value1_hex:
            value: 'value1_hex_left_digit + value1_hex_right_digit == "ff" ? ".." : value1_hex_left_digit + value1_hex_right_digit' # "ff" is translated to ".."


          value2_hex_left:
            value: value2 / 16

          value2_hex_left_digit:
            value: 'value2_hex_left.to_s == "10" ? "a" : (value2_hex_left.to_s == "11" ? "b" : (value2_hex_left.to_s == "12" ? "c" : (value2_hex_left.to_s == "13" ? "d" : (value2_hex_left.to_s == "14" ? "e" : (value2_hex_left.to_s == "15" ? "f" : value2_hex_left.to_s)))))'

          value2_hex_right:
            value: value2 % 16

          value2_hex_right_digit:
            value: 'value2_hex_right.to_s == "10" ? "a" : (value2_hex_right.to_s == "11" ? "b" : (value2_hex_right.to_s == "12" ? "c" : (value2_hex_right.to_s == "13" ? "d" : (value2_hex_right.to_s == "14" ? "e" : (value2_hex_right.to_s == "15" ? "f" : value2_hex_right.to_s)))))'

          value2_hex:
            value: 'value2_hex_left_digit + value2_hex_right_digit == "ff" ? ".." : value2_hex_left_digit + value2_hex_right_digit'


          value3_hex_left:
            value: value3 / 16

          value3_hex_left_digit:
            value: 'value3_hex_left.to_s == "10" ? "a" : (value3_hex_left.to_s == "11" ? "b" : (value3_hex_left.to_s == "12" ? "c" : (value3_hex_left.to_s == "13" ? "d" : (value3_hex_left.to_s == "14" ? "e" : (value3_hex_left.to_s == "15" ? "f" : value3_hex_left.to_s)))))'

          value3_hex_right:
            value: value3 % 16

          value3_hex_right_digit:
            value: 'value3_hex_right.to_s == "10" ? "a" : (value3_hex_right.to_s == "11" ? "b" : (value3_hex_right.to_s == "12" ? "c" : (value3_hex_right.to_s == "13" ? "d" : (value3_hex_right.to_s == "14" ? "e" : (value3_hex_right.to_s == "15" ? "f" : value3_hex_right.to_s)))))'

          value3_hex:
            value: 'value3_hex_left_digit + value3_hex_right_digit == "ff" ? ".." : value3_hex_left_digit + value3_hex_right_digit'


          value4_hex_left:
            value: value4 / 16

          value4_hex_left_digit:
            value: 'value4_hex_left.to_s == "10" ? "a" : (value4_hex_left.to_s == "11" ? "b" : (value4_hex_left.to_s == "12" ? "c" : (value4_hex_left.to_s == "13" ? "d" : (value4_hex_left.to_s == "14" ? "e" : (value4_hex_left.to_s == "15" ? "f" : value4_hex_left.to_s)))))'

          value4_hex_right:
            value: value4 % 16

          value4_hex_right_digit:
            value: 'value4_hex_right.to_s == "10" ? "a" : (value4_hex_right.to_s == "11" ? "b" : (value4_hex_right.to_s == "12" ? "c" : (value4_hex_right.to_s == "13" ? "d" : (value4_hex_right.to_s == "14" ? "e" : (value4_hex_right.to_s == "15" ? "f" : value4_hex_right.to_s)))))'

          value4_hex:
            value: 'value4_hex_left_digit + value4_hex_right_digit == "ff" ? ".." : value4_hex_left_digit + value4_hex_right_digit'



          time_after_last_reset_hex_left:
            value: time_after_last_reset / 16

          time_after_last_reset_hex_left_digit:
            value: 'time_after_last_reset_hex_left.to_s == "10" ? "a" : (time_after_last_reset_hex_left.to_s == "11" ? "b" : (time_after_last_reset_hex_left.to_s == "12" ? "c" : (time_after_last_reset_hex_left.to_s == "13" ? "d" : (time_after_last_reset_hex_left.to_s == "14" ? "e" : (time_after_last_reset_hex_left.to_s == "15" ? "f" : time_after_last_reset_hex_left.to_s)))))'

          time_after_last_reset_hex_right:
            value: time_after_last_reset % 16

          time_after_last_reset_hex_right_digit:
            value: 'time_after_last_reset_hex_right.to_s == "10" ? "a" : (time_after_last_reset_hex_right.to_s == "11" ? "b" : (time_after_last_reset_hex_right.to_s == "12" ? "c" : (time_after_last_reset_hex_right.to_s == "13" ? "d" : (time_after_last_reset_hex_right.to_s == "14" ? "e" : (time_after_last_reset_hex_right.to_s == "15" ? "f" : time_after_last_reset_hex_right.to_s)))))'

          time_after_last_reset_hex:
            value: 'time_after_last_reset_hex_left_digit + time_after_last_reset_hex_right_digit == "ff" ? ".." : time_after_last_reset_hex_left_digit + time_after_last_reset_hex_right_digit' # "ff" is translated to ".."



          cw_beacon:
            value: bat_v_raw_hex + bat_i_raw_hex + bat_t_raw_hex + value1_hex + value2_hex + value3_hex + value4_hex + time_after_last_reset_hex


  gmsk_or_digi:
    seq:
      - id: id3
        type:
          switch-on: message_type2
          cases:
            0xf0fff0ff: gmsk
            _: digi

    instances:
      message_type2:
        type: u4
        pos: 15 # pid + reserved


  gmsk:
   seq:
     - id: header_and_reserved_1
       type: u8

     - id: header_and_reserved_2
       type: u8

     - id: header_and_reserved_3 # total 19 bytes
       type: b24


     - id: packet_number
       type: b24

     - id: bat_v_raw_1
       type: u1

     - id: bat_v_raw_2
       type: u1

     - id: bat_i_raw_1
       type: u1

     - id: bat_i_raw_2
       type: u1

     - id: bat_t_raw_1
       type: u1

     - id: bat_t_raw_2
       type: u1

     - id: free_1
       type: b4

     - id: kill_main_boolean
       type: b1

     - id: kill_fab_boolean
       type: b1

     - id: solar_cell_plus_x_boolean
       type: b1

     - id: solar_cell_plus_y_boolean
       type: b1

     - id: free_2
       type: b4

     - id: solar_cell_plus_z_boolean
       type: b1

     - id: solar_cell_minus_x_boolean
       type: b1

     - id: solar_cell_minus_y_boolean
       type: b1

     - id: solar_cell_minus_z_boolean
       type: b1

     - id: free_3
       type: b4

     - id: ant_1_deploy_boolean
       type: b1

     - id: ant_1_set_count
       type: b3

     - id: free_4
       type: b4

     - id: ant_2_deploy_boolean
       type: b1

     - id: ant_2_set_count
       type: b3

     - id: free_5
       type: b4

     - id: aprs_reference_1_boolean
       type: b1

     - id: aprs_reference_2_boolean
       type: b1

     - id: aprs_payload_1_boolean
       type: b1

     - id: aprs_payload_2_boolean
       type: b1

     - id: free_6
       type: b4

     - id: aprs_payload_3_boolean
       type: b1

     - id: aprs_payload_4_boolean
       type: b1

     - id: aprs_payload_5_boolean
       type: b1

     - id: free_7
       type: b5

     - id: main_pic_power_line_status_boolean
       type: b1

     - id: com_pic_power_line_status_boolean
       type: b1

     - id: v3_3_1_status_boolean
       type: b1

     - id: v3_3_2_status_boolean
       type: b1

     - id: free_8
       type: b4

     - id: v5_status_boolean
       type: b1

     - id: unreg1_status_boolean
       type: b1

     - id: unreg2_status_boolean
       type: b1

     - id: time_after_last_reset_1
       type: u1

     - id: time_after_last_reset_2
       type: u1

     - id: ff # the beacon should end by time_after_last_reset_2. if there is more to parse, the whole frame will be discarded due to 'necessary_for_lengthcheck'
       type: u1
       repeat: expr
       repeat-expr: 65

     - id: lengthcheck # the beacon should end by time_after_last_reset. if there is more to parse, the whole frame will be discarded due to 'necessary_for_lengthcheck'
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true

   instances:
          necessary_for_lengthcheck:
            if: lengthcheck.length != 0 # if so, whole frame will be discarded
            value: lengthcheck.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

          bat_v_raw:
            value: (bat_v_raw_1 << 4) + bat_v_raw_2

          bat_v:
            value: 6.512 * bat_v_raw / 256

          bat_i_raw:
            value: (bat_i_raw_1 << 4) + bat_i_raw_2

          bat_i:
            value: -2.99589 * bat_i_raw + 6129.78533

          bat_t_raw:
            value: (bat_t_raw_1 << 4) + bat_t_raw_2

          bat_t:
            value: 75 - (bat_t_raw * 97.68 / 256)

          kill_main:
            value: kill_main_boolean.to_i

          kill_fab:
            value: kill_fab_boolean.to_i

          solar_cell_plus_x:
            value: solar_cell_plus_x_boolean.to_i

          solar_cell_plus_y:
            value: solar_cell_plus_y_boolean.to_i

          solar_cell_plus_z:
            value: solar_cell_plus_z_boolean.to_i

          solar_cell_minus_x:
            value: solar_cell_minus_x_boolean.to_i

          solar_cell_minus_y:
            value: solar_cell_minus_y_boolean.to_i

          solar_cell_minus_z:
            value: solar_cell_minus_z_boolean.to_i

          ant_1_deploy:
            value: ant_1_deploy_boolean.to_i

          ant_2_deploy:
            value: ant_2_deploy_boolean.to_i

          aprs_reference_1:
            value: aprs_reference_1_boolean.to_i

          aprs_reference_2:
            value: aprs_reference_2_boolean.to_i

          aprs_payload_1:
            value: aprs_payload_1_boolean.to_i

          aprs_payload_2:
            value: aprs_payload_2_boolean.to_i

          aprs_payload_3:
            value: aprs_payload_3_boolean.to_i

          aprs_payload_4:
            value: aprs_payload_4_boolean.to_i

          aprs_payload_5:
            value: aprs_payload_5_boolean.to_i

          main_pic_power_line_status:
            value: main_pic_power_line_status_boolean.to_i

          com_pic_power_line_status:
            value: com_pic_power_line_status_boolean.to_i

          v3_3_1_status:
            value: v3_3_1_status_boolean.to_i

          v3_3_2_status:
            value: v3_3_2_status_boolean.to_i

          v5_status:
            value: v5_status_boolean.to_i

          unreg1_status:
            value: unreg1_status_boolean.to_i

          unreg2_status:
            value: unreg2_status_boolean.to_i

          time_after_last_reset:
            value: (time_after_last_reset_1 << 4) + time_after_last_reset_2

          beacon_type:
            value: '"GMSK"'



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
