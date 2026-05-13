---
meta:
  id: cosmogirlsat
  title: CosmoGirl-Sat CW and Digipeater decoder
  endian: be
doc-ref: "https://cosmosgirlham.org/communication/"
# 2024-09-17, DL7NDR
doc: |
  :field satellitename_and_callsign: cosmo.cw_or_digi.satellitename_and_callsign
  :field type_id: cosmo.cw_or_digi.type_id
  :field battery_voltage_v: cosmo.cw_or_digi.battery_voltage_v
  :field battery_current_ma: cosmo.cw_or_digi.battery_current_ma
  :field battery_temperature_c: cosmo.cw_or_digi.battery_temperature_c
  :field operation_modes: cosmo.cw_or_digi.operation_modes
  :field kill_switch_main: cosmo.cw_or_digi.kill_switch_main
  :field kill_switch_fab: cosmo.cw_or_digi.kill_switch_fab
  :field antenna_deploy_status: cosmo.cw_or_digi.antenna_deploy_status
  :field solar_cell_plus_y: cosmo.cw_or_digi.solar_cell_plus_y
  :field solar_cell_plus_x: cosmo.cw_or_digi.solar_cell_plus_x
  :field solar_cell_minus_z: cosmo.cw_or_digi.solar_cell_minus_z
  :field solar_cell_minus_x: cosmo.cw_or_digi.solar_cell_minus_x
  :field solar_cell_plus_z: cosmo.cw_or_digi.solar_cell_plus_z
  :field hours_after_last_reset: cosmo.cw_or_digi.hours_after_last_reset
  :field gyro_x: cosmo.cw_or_digi.gyro_x
  :field gyro_y: cosmo.cw_or_digi.gyro_y
  :field gyro_z: cosmo.cw_or_digi.gyro_z
  :field hssc_automatical_trial: cosmo.cw_or_digi.hssc_automatical_trial
  :field com_to_main_flag: cosmo.cw_or_digi.com_to_main_flag
  :field reset_to_main_flag: cosmo.cw_or_digi.reset_to_main_flag
  :field fab_to_main_flag: cosmo.cw_or_digi.fab_to_main_flag
  :field battery_heater: cosmo.cw_or_digi.battery_heater
  :field reservation_command: cosmo.cw_or_digi.reservation_command
  :field uplink_success: cosmo.cw_or_digi.uplink_success
  :field mission_satus: cosmo.cw_or_digi.mission_satus
  :field mission_operating_status: cosmo.cw_or_digi.mission_operating_status
  :field cw_beacon: cosmo.cw_or_digi.cw_beacon
  :field dest_callsign: cosmo.cw_or_digi.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: cosmo.cw_or_digi.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: cosmo.cw_or_digi.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: cosmo.cw_or_digi.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: cosmo.cw_or_digi.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: cosmo.cw_or_digi.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: cosmo.cw_or_digi.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field ctl: cosmo.cw_or_digi.ax25_frame.ax25_header.ctl
  :field pid: cosmo.cw_or_digi.ax25_frame.payload.pid
  :field monitor: cosmo.cw_or_digi.ax25_frame.payload.ax25_info.data_monitor

seq:
  - id: cosmo
    type: cosmo_t

types:
  cosmo_t:
    seq:
      - id: cw_or_digi
        type:
          switch-on: cw_or_digi_switch_on
          cases:
            0x636F736D6F30206A: cw #  "cosmo0 j"
            _: digi # everything else

    instances:
        cw_or_digi_switch_on:
              type: u8
              pos: 0

  cw:
    seq:
      - id: satellitename_and_callsign
        type: str
        size: 21
        encoding: ASCII
        valid: '"cosmo0 js1yoi 000000 "' # 636F736D6F30206A7331796F692030303030303020

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

    instances:
# acquiring type id
      type_id:
        value: (byte_4 & 0b10000000) >> 7

# assigning values according to beacon type 1
      battery_voltage_v:
        if: type_id == 0
        value: byte_1 # * 0.02578

      battery_current_ma:
        if: type_id == 0
        value: byte_2 # * (-50.05) + 6330

      battery_temperature_c:
        if: type_id == 0
        value: byte_3 # (1185000/(-ln((256/byte_3_hex)-1)*298+3976))-273

      operation_modes:
        if: type_id == 0
        value: (byte_4 & 0b01100000) >> 5

      kill_switch_main:
        if: type_id == 0
        value: (byte_4 & 0b00010000) >> 4

      kill_switch_fab:
        if: type_id == 0
        value: (byte_4 & 0b00001000) >> 3

      antenna_deploy_status:
        if: type_id == 0
        value: (byte_4 & 0b00000100) >> 2

      solar_cell_plus_y:
        if: type_id == 0
        value: (byte_4 & 0b00000010) >> 1

      solar_cell_plus_x:
        if: type_id == 0
        value: byte_4 & 0b00000001

      solar_cell_minus_z:
        if: type_id == 0
        value: (byte_5 & 0b10000000) >> 7

      solar_cell_minus_x:
        if: type_id == 0
        value: (byte_5 & 0b01000000) >> 6

      solar_cell_plus_z:
        if: type_id == 0
        value: (byte_5 & 0b00100000) >> 5

      hours_after_last_reset:
        if: type_id == 0
        value: byte_5 & 0b00011111

# assigning values according to beacon type 2
      gyro_x:
        if: type_id == 1
        value: byte_1 # there are no gyros

      gyro_y:
        if: type_id == 1
        value: byte_2 # there are no gyros

      gyro_z:
        if: type_id == 1
        value: byte_3 # there are no gyros

      hssc_automatical_trial:
        if: type_id == 1
        value: (byte_4 & 0b01000000) >> 6

      com_to_main_flag:
        if: type_id == 1
        value: (byte_4 & 0b00100000) >> 5

      reset_to_main_flag:
        if: type_id == 1
        value: (byte_4 & 0b00010000) >> 4

      fab_to_main_flag: # fab could be "Fault Acquisition and Bypass" or "Fault Analysis Board"
        if: type_id == 1
        value: (byte_4 & 0b00001000) >> 3

      battery_heater:
        if: type_id == 1
        value: (byte_4 & 0b00000100) >> 2

      reservation_command:
        if: type_id == 1
        value: (byte_4 & 0b00000010) >> 1

      uplink_success:
        if: type_id == 1
        value: byte_4 & 0b00000001

      mission_satus:
        if: type_id == 1
        value: (byte_5 & 0b11110000) >> 4

      mission_operating_status:
        if: type_id == 1
        value: byte_5 & 0b00001111

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
