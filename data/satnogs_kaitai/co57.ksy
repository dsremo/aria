---
meta:
  id: co57
  title: CO-57 (XI-IV) CW Beacon Decoder
  endian: be
doc-ref: "https://web.archive.org/web/20040826163856fw_/http://www.space.t.u-tokyo.ac.jp/nlab_gs/xi-iv_operation/satelliteinfo_ja.html"
# 2025-03-09, DL7NDR
doc: |
  :field ut: ut
  :field beacon_type: beacon_types.type_check.beacon_type
  :field time_counter: beacon_types.type_check.time_counter
  :field uplink_counter: beacon_types.type_check.uplink_counter
  :field camera_counter: beacon_types.type_check.camera_counter
  :field sel_reset_counter: beacon_types.type_check.sel_reset_counter
  :field antenna_deployed: beacon_types.type_check.antenna_deployed
  :field cw_duty_ratio: beacon_types.type_check.cw_duty_ratio
  :field obc_reset: beacon_types.type_check.obc_reset
  :field state_of_charge: beacon_types.type_check.state_of_charge
  :field state_of_obc: beacon_types.type_check.state_of_obc
  :field state_of_tx_tnc: beacon_types.type_check.state_of_tx_tnc
  :field undefined: beacon_types.type_check.undefined
  :field rssi_max_between_ut1_and_ut3: beacon_types.type_check.rssi_max_between_ut1_and_ut3
  :field batt_v: beacon_types.type_check.batt_v
  :field sol_v: beacon_types.type_check.sol_v
  :field batt_t_ut4: beacon_types.type_check.batt_t_ut4
  :field plus_x_i: beacon_types.type_check.plus_x_i
  :field minus_x_i: beacon_types.type_check.minus_x_i
  :field plus_y_i: beacon_types.type_check.plus_y_i
  :field minus_y_i: beacon_types.type_check.minus_y_i
  :field plus_z_i: beacon_types.type_check.plus_z_i
  :field minus_z_i: beacon_types.type_check.minus_z_i
  :field plus_x_t: beacon_types.type_check.plus_x_t
  :field minus_x_t: beacon_types.type_check.minus_x_t
  :field plus_y_t: beacon_types.type_check.plus_y_t
  :field minus_y_t: beacon_types.type_check.minus_y_t
  :field plus_z_t: beacon_types.type_check.plus_z_t
  :field minus_z_t: beacon_types.type_check.minus_z_t
  :field battery_t_ut6: beacon_types.type_check.battery_t_ut6
  :field fm_transmitter_t: beacon_types.type_check.fm_transmitter_t
  :field rssi_max_between_ut4_and_ut6: beacon_types.type_check.rssi_max_between_ut4_and_ut6
  :field beacon: beacon_types.type_check.beacon
  :field discard: beacon_types.type_check.discard_discard

seq:
  - id: ut
    type: str
    size: 2
    encoding: ASCII
    valid: '"ut"' # 75 74

  - id: beacon_types
    type: beacon_types_t

types:
  beacon_types_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x3220: ut2
            0x3320: ut3
            0x3420: ut4
            0x3520: ut5
            0x3620: ut6
            _: discard

    instances:
      check:
        type: u2


  ut2:
   seq:
     - id: time_counter
       type: b24 # 1 = 1 second
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '2'

# reconstructing beacon

     value1:
        value: time_counter >> 16
     value2:
        value: (time_counter >> 8)  & 0xff
     value3:
        value: time_counter & 0xff



     value1_hex_left:
        value: value1 / 16

     value1_hex_left_digit:
        value: 'value1_hex_left.to_s == "10" ? "a" : (value1_hex_left.to_s == "11" ? "b" : (value1_hex_left.to_s == "12" ? "c" : (value1_hex_left.to_s == "13" ? "d" : (value1_hex_left.to_s == "14" ? "e" : (value1_hex_left.to_s == "15" ? "f" : value1_hex_left.to_s)))))'

     value1_hex_right:
        value: value1 % 16

     value1_hex_right_digit:
        value: 'value1_hex_right.to_s == "10" ? "a" : (value1_hex_right.to_s == "11" ? "b" : (value1_hex_right.to_s == "12" ? "c" : (value1_hex_right.to_s == "13" ? "d" : (value1_hex_right.to_s == "14" ? "e" : (value1_hex_right.to_s == "15" ? "f" : value1_hex_right.to_s)))))'

     value1_hex:
        value: value1_hex_left_digit + value1_hex_right_digit


     value2_hex_left:
        value: value2 / 16

     value2_hex_left_digit:
        value: 'value2_hex_left.to_s == "10" ? "a" : (value2_hex_left.to_s == "11" ? "b" : (value2_hex_left.to_s == "12" ? "c" : (value2_hex_left.to_s == "13" ? "d" : (value2_hex_left.to_s == "14" ? "e" : (value2_hex_left.to_s == "15" ? "f" : value2_hex_left.to_s)))))'

     value2_hex_right:
        value: value2 % 16

     value2_hex_right_digit:
        value: 'value2_hex_right.to_s == "10" ? "a" : (value2_hex_right.to_s == "11" ? "b" : (value2_hex_right.to_s == "12" ? "c" : (value2_hex_right.to_s == "13" ? "d" : (value2_hex_right.to_s == "14" ? "e" : (value2_hex_right.to_s == "15" ? "f" : value2_hex_right.to_s)))))'

     value2_hex:
        value: value2_hex_left_digit + value2_hex_right_digit


     value3_hex_left:
        value: value3 / 16

     value3_hex_left_digit:
        value: 'value3_hex_left.to_s == "10" ? "a" : (value3_hex_left.to_s == "11" ? "b" : (value3_hex_left.to_s == "12" ? "c" : (value3_hex_left.to_s == "13" ? "d" : (value3_hex_left.to_s == "14" ? "e" : (value3_hex_left.to_s == "15" ? "f" : value3_hex_left.to_s)))))'

     value3_hex_right:
        value: value3 % 16

     value3_hex_right_digit:
        value: 'value3_hex_right.to_s == "10" ? "a" : (value3_hex_right.to_s == "11" ? "b" : (value3_hex_right.to_s == "12" ? "c" : (value3_hex_right.to_s == "13" ? "d" : (value3_hex_right.to_s == "14" ? "e" : (value3_hex_right.to_s == "15" ? "f" : value3_hex_right.to_s)))))'

     value3_hex:
        value: value3_hex_left_digit + value3_hex_right_digit


     beacon:
        value: '"UT2 "+ value1_hex + value2_hex + value3_hex'




  ut3:
   seq:
     - id: byte_1
       type: u1
     - id: byte_2
       type: u1
     - id: byte_3
       type: u1
     - id: rssi_max_between_ut1_and_ut3_raw # see UT6 for conversion explanation
       type: u1
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
     camera_counter:
       value: byte_1 >> 5
     uplink_counter:
       value: byte_1 & 0x1F

     state_of_charge:
       value: byte_2 >> 7
     obc_reset:
       value: (byte_2 >> 6) & 0x1
     cw_duty_ratio: # 0=0; 1= <0.3; 2= 0.3; 3= >0.3
       value: (byte_2 >> 4) & 0x3
     antenna_deployed:
       value: (byte_2 >> 3) & 0x1
     sel_reset_counter:
       value: byte_2 & 0x7

     undefined:
       value: byte_3 >> 2
     state_of_tx_tnc:
       value: (byte_3 >> 1) & 0x1
     state_of_obc:
       value: byte_3 & 0x1

     rssi_max_between_ut1_and_ut3:
       value: (rssi_max_between_ut1_and_ut3_raw * 4.77 * 4 / 255) - 107 # unit dBm

     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

     beacon_type:
       value: '3'

# reconstructing beacon

     value1:
        value: byte_1
     value2:
        value: byte_2
     value3:
        value: byte_3
     value4:
        value: rssi_max_between_ut1_and_ut3_raw


     value1_hex_left:
        value: value1 / 16

     value1_hex_left_digit:
        value: 'value1_hex_left.to_s == "10" ? "a" : (value1_hex_left.to_s == "11" ? "b" : (value1_hex_left.to_s == "12" ? "c" : (value1_hex_left.to_s == "13" ? "d" : (value1_hex_left.to_s == "14" ? "e" : (value1_hex_left.to_s == "15" ? "f" : value1_hex_left.to_s)))))'

     value1_hex_right:
        value: value1 % 16

     value1_hex_right_digit:
        value: 'value1_hex_right.to_s == "10" ? "a" : (value1_hex_right.to_s == "11" ? "b" : (value1_hex_right.to_s == "12" ? "c" : (value1_hex_right.to_s == "13" ? "d" : (value1_hex_right.to_s == "14" ? "e" : (value1_hex_right.to_s == "15" ? "f" : value1_hex_right.to_s)))))'

     value1_hex:
        value: value1_hex_left_digit + value1_hex_right_digit


     value2_hex_left:
        value: value2 / 16

     value2_hex_left_digit:
        value: 'value2_hex_left.to_s == "10" ? "a" : (value2_hex_left.to_s == "11" ? "b" : (value2_hex_left.to_s == "12" ? "c" : (value2_hex_left.to_s == "13" ? "d" : (value2_hex_left.to_s == "14" ? "e" : (value2_hex_left.to_s == "15" ? "f" : value2_hex_left.to_s)))))'

     value2_hex_right:
        value: value2 % 16

     value2_hex_right_digit:
        value: 'value2_hex_right.to_s == "10" ? "a" : (value2_hex_right.to_s == "11" ? "b" : (value2_hex_right.to_s == "12" ? "c" : (value2_hex_right.to_s == "13" ? "d" : (value2_hex_right.to_s == "14" ? "e" : (value2_hex_right.to_s == "15" ? "f" : value2_hex_right.to_s)))))'

     value2_hex:
        value: value2_hex_left_digit + value2_hex_right_digit


     value3_hex_left:
        value: value3 / 16

     value3_hex_left_digit:
        value: 'value3_hex_left.to_s == "10" ? "a" : (value3_hex_left.to_s == "11" ? "b" : (value3_hex_left.to_s == "12" ? "c" : (value3_hex_left.to_s == "13" ? "d" : (value3_hex_left.to_s == "14" ? "e" : (value3_hex_left.to_s == "15" ? "f" : value3_hex_left.to_s)))))'

     value3_hex_right:
        value: value3 % 16

     value3_hex_right_digit:
        value: 'value3_hex_right.to_s == "10" ? "a" : (value3_hex_right.to_s == "11" ? "b" : (value3_hex_right.to_s == "12" ? "c" : (value3_hex_right.to_s == "13" ? "d" : (value3_hex_right.to_s == "14" ? "e" : (value3_hex_right.to_s == "15" ? "f" : value3_hex_right.to_s)))))'

     value3_hex:
        value: value3_hex_left_digit + value3_hex_right_digit


     value4_hex_left:
        value: value4 / 16

     value4_hex_left_digit:
        value: 'value4_hex_left.to_s == "10" ? "a" : (value4_hex_left.to_s == "11" ? "b" : (value4_hex_left.to_s == "12" ? "c" : (value4_hex_left.to_s == "13" ? "d" : (value4_hex_left.to_s == "14" ? "e" : (value4_hex_left.to_s == "15" ? "f" : value4_hex_left.to_s)))))'

     value4_hex_right:
        value: value4 % 16

     value4_hex_right_digit:
        value: 'value4_hex_right.to_s == "10" ? "a" : (value4_hex_right.to_s == "11" ? "b" : (value4_hex_right.to_s == "12" ? "c" : (value4_hex_right.to_s == "13" ? "d" : (value4_hex_right.to_s == "14" ? "e" : (value4_hex_right.to_s == "15" ? "f" : value4_hex_right.to_s)))))'

     value4_hex:
        value: value4_hex_left_digit + value4_hex_right_digit


     beacon:
        value: '"UT3 "+ value1_hex + value2_hex + value3_hex + value4_hex'


  ut4:
   seq:
     - id: batt_v_raw
       type: u1
     - id: sol_v_raw
       type: u1
     - id: batt_t_ut4_raw
       type: u1
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
     batt_v:
        value: batt_v_raw * 4.77 * 4 / 255
     sol_v:
        value: sol_v_raw * 4.77 * 4 / 255
     batt_t_ut4:
        value: (batt_t_ut4_raw + 297.06) / 149.31 * 105.86 - 287.71
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '4'

# reconstructing beacon

     value1:
        value: batt_v_raw
     value2:
        value: sol_v_raw
     value3:
        value: batt_t_ut4_raw


     value1_hex_left:
        value: value1 / 16

     value1_hex_left_digit:
        value: 'value1_hex_left.to_s == "10" ? "a" : (value1_hex_left.to_s == "11" ? "b" : (value1_hex_left.to_s == "12" ? "c" : (value1_hex_left.to_s == "13" ? "d" : (value1_hex_left.to_s == "14" ? "e" : (value1_hex_left.to_s == "15" ? "f" : value1_hex_left.to_s)))))'

     value1_hex_right:
        value: value1 % 16

     value1_hex_right_digit:
        value: 'value1_hex_right.to_s == "10" ? "a" : (value1_hex_right.to_s == "11" ? "b" : (value1_hex_right.to_s == "12" ? "c" : (value1_hex_right.to_s == "13" ? "d" : (value1_hex_right.to_s == "14" ? "e" : (value1_hex_right.to_s == "15" ? "f" : value1_hex_right.to_s)))))'

     value1_hex:
        value: value1_hex_left_digit + value1_hex_right_digit


     value2_hex_left:
        value: value2 / 16

     value2_hex_left_digit:
        value: 'value2_hex_left.to_s == "10" ? "a" : (value2_hex_left.to_s == "11" ? "b" : (value2_hex_left.to_s == "12" ? "c" : (value2_hex_left.to_s == "13" ? "d" : (value2_hex_left.to_s == "14" ? "e" : (value2_hex_left.to_s == "15" ? "f" : value2_hex_left.to_s)))))'

     value2_hex_right:
        value: value2 % 16

     value2_hex_right_digit:
        value: 'value2_hex_right.to_s == "10" ? "a" : (value2_hex_right.to_s == "11" ? "b" : (value2_hex_right.to_s == "12" ? "c" : (value2_hex_right.to_s == "13" ? "d" : (value2_hex_right.to_s == "14" ? "e" : (value2_hex_right.to_s == "15" ? "f" : value2_hex_right.to_s)))))'

     value2_hex:
        value: value2_hex_left_digit + value2_hex_right_digit


     value3_hex_left:
        value: value3 / 16

     value3_hex_left_digit:
        value: 'value3_hex_left.to_s == "10" ? "a" : (value3_hex_left.to_s == "11" ? "b" : (value3_hex_left.to_s == "12" ? "c" : (value3_hex_left.to_s == "13" ? "d" : (value3_hex_left.to_s == "14" ? "e" : (value3_hex_left.to_s == "15" ? "f" : value3_hex_left.to_s)))))'

     value3_hex_right:
        value: value3 % 16

     value3_hex_right_digit:
        value: 'value3_hex_right.to_s == "10" ? "a" : (value3_hex_right.to_s == "11" ? "b" : (value3_hex_right.to_s == "12" ? "c" : (value3_hex_right.to_s == "13" ? "d" : (value3_hex_right.to_s == "14" ? "e" : (value3_hex_right.to_s == "15" ? "f" : value3_hex_right.to_s)))))'

     value3_hex:
        value: value3_hex_left_digit + value3_hex_right_digit

     beacon:
        value: '"UT4 "+ value1_hex + value2_hex + value3_hex'


  ut5:
# format: ABCDEF where A=plus_x_i, B=minus_x_i, C=plus_y_i, D=minus_y_i ...
# xi-iv sends only the upper 4 bits. that means we have to fill up the lower 4 bits with zeros or just add "0" to the single hex value.
# example: if AB=0xff, then A = 0xf0 and B = 0xf0
   seq:
     - id: plus_x_i_upper_four_bits
       type: b4
     - id: minus_x_i_upper_four_bits
       type: b4
     - id: plus_y_i_upper_four_bits
       type: b4
     - id: minus_y_i_upper_four_bits
       type: b4
     - id: plus_z_i_upper_four_bits
       type: b4
     - id: minus_z_i_upper_four_bits
       type: b4
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
     plus_x_i:
       if: plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 90 and plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 0
# if all values are either "f" or "0" then this must definitely due to a malfunctioning sensor => need to be recognized as NaN to discard it.
       value: (plus_x_i_upper_four_bits << 4) * 4.77 * 10 * 10.49881 / 255
     minus_x_i:
       if: plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 90 and plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 0
       value: (8.251522329 * (minus_x_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (0.482939447 * (plus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (0.024941879 * (minus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (0.636795098 * (plus_z_i_upper_four_bits << 4) * 4.77 * 10 / 255)
     plus_y_i:
       if: plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 90 and plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 0
       value: (-0.482939447 * (minus_x_i_upper_four_bits << 4) * 4.77 * 10 / 255) + (6.672955921 * (plus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (0.017974511 * (minus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (1.050451843 * (plus_z_i_upper_four_bits << 4) * 4.77 * 10 / 255)
     minus_y_i:
       if: plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 90 and plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 0
       value: (-0.024941879 * (minus_x_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (0.017974511 * (plus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) + (9.840646080 * (minus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (0.023700861 * (plus_z_i_upper_four_bits << 4) * 4.77 * 10 / 255)
     plus_z_i:
       if: plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 90 and plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 0
       value: (-0.636795098 * (minus_x_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (1.050451843 * (plus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) - (0.023700861 * (minus_y_i_upper_four_bits << 4) * 4.77 * 10 / 255) + (8.464182598 * (plus_z_i_upper_four_bits << 4) * 4.77 * 10 / 255)
     minus_z_i:
       if: plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 90 and plus_x_i_upper_four_bits + minus_x_i_upper_four_bits + plus_y_i_upper_four_bits + minus_y_i_upper_four_bits + plus_z_i_upper_four_bits + minus_z_i_upper_four_bits != 0
       value: 7.515946019 * ((minus_z_i_upper_four_bits << 4) * 4.77 * 10 / 255)
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '5'


# reconstructing beacon

     value1:
        value: plus_x_i_upper_four_bits << 4
     value2:
        value: minus_x_i_upper_four_bits << 4
     value3:
        value: plus_y_i_upper_four_bits << 4
     value4:
        value: minus_y_i_upper_four_bits << 4
     value5:
        value: plus_z_i_upper_four_bits << 4
     value6:
        value: minus_z_i_upper_four_bits << 4


     value1_hex_left:
        value: value1 / 16

     value1_hex_left_digit:
        value: 'value1_hex_left.to_s == "10" ? "a" : (value1_hex_left.to_s == "11" ? "b" : (value1_hex_left.to_s == "12" ? "c" : (value1_hex_left.to_s == "13" ? "d" : (value1_hex_left.to_s == "14" ? "e" : (value1_hex_left.to_s == "15" ? "f" : value1_hex_left.to_s)))))'

     value1_hex:
        value: value1_hex_left_digit


     value2_hex_left:
        value: value2 / 16

     value2_hex_left_digit:
        value: 'value2_hex_left.to_s == "10" ? "a" : (value2_hex_left.to_s == "11" ? "b" : (value2_hex_left.to_s == "12" ? "c" : (value2_hex_left.to_s == "13" ? "d" : (value2_hex_left.to_s == "14" ? "e" : (value2_hex_left.to_s == "15" ? "f" : value2_hex_left.to_s)))))'

     value2_hex:
        value: value2_hex_left_digit


     value3_hex_left:
        value: value3 / 16

     value3_hex_left_digit:
        value: 'value3_hex_left.to_s == "10" ? "a" : (value3_hex_left.to_s == "11" ? "b" : (value3_hex_left.to_s == "12" ? "c" : (value3_hex_left.to_s == "13" ? "d" : (value3_hex_left.to_s == "14" ? "e" : (value3_hex_left.to_s == "15" ? "f" : value3_hex_left.to_s)))))'

     value3_hex:
        value: value3_hex_left_digit


     value4_hex_left:
        value: value4 / 16

     value4_hex_left_digit:
        value: 'value4_hex_left.to_s == "10" ? "a" : (value4_hex_left.to_s == "11" ? "b" : (value4_hex_left.to_s == "12" ? "c" : (value4_hex_left.to_s == "13" ? "d" : (value4_hex_left.to_s == "14" ? "e" : (value4_hex_left.to_s == "15" ? "f" : value4_hex_left.to_s)))))'

     value4_hex:
        value: value4_hex_left_digit


     value5_hex_left:
        value: value5 / 16

     value5_hex_left_digit:
        value: 'value5_hex_left.to_s == "10" ? "a" : (value5_hex_left.to_s == "11" ? "b" : (value5_hex_left.to_s == "12" ? "c" : (value5_hex_left.to_s == "13" ? "d" : (value5_hex_left.to_s == "14" ? "e" : (value5_hex_left.to_s == "15" ? "f" : value5_hex_left.to_s)))))'

     value5_hex:
        value: value5_hex_left_digit


     value6_hex_left:
        value: value6 / 16

     value6_hex_left_digit:
        value: 'value6_hex_left.to_s == "10" ? "a" : (value6_hex_left.to_s == "11" ? "b" : (value6_hex_left.to_s == "12" ? "c" : (value6_hex_left.to_s == "13" ? "d" : (value6_hex_left.to_s == "14" ? "e" : (value6_hex_left.to_s == "15" ? "f" : value6_hex_left.to_s)))))'

     value6_hex:
        value: value6_hex_left_digit


     beacon:
        value: '"UT5 "+ value1_hex + value2_hex + value3_hex + value4_hex + value5_hex + value6_hex'



  ut6:
   seq:
     - id: plus_x_t_upper_four_bits
       type: b4
     - id: minus_x_t_upper_four_bits
       type: b4
     - id: plus_y_t_upper_four_bits
       type: b4
     - id: minus_y_t_upper_four_bits
       type: b4
     - id: plus_z_t_upper_four_bits
       type: b4
     - id: minus_z_t_upper_four_bits
       type: b4
     - id: battery_t_upper_four_bits
       type: b4
     - id: fm_transmitter_t_upper_four_bits
       type: b4
     - id: rssi_max_between_ut4_and_ut6_raw
# There is no conversion given for this value. However the XI CW Converter provided by ISSL seems to use the conversion I'm going to use under 'instances' (*).
       type: u1
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length


   instances:
     plus_x_t:
       value: ((plus_x_t_upper_four_bits << 4) + 298.43) / 149.66 * 105.25 - 287.12
     minus_x_t:
       value: ((minus_x_t_upper_four_bits << 4) + 298.36) / 149.82 * 105.82 - 287.89
     plus_y_t:
       value: ((minus_x_t_upper_four_bits << 4) + 296.79) / 149.13 * 104.96 - 287.44
     minus_y_t:
       value: ((minus_x_t_upper_four_bits << 4) + 297.80) / 149.51 * 106.16 - 288.55
     plus_z_t:
       value: ((minus_x_t_upper_four_bits << 4) + 298.51) / 149.75 * 104.55 - 285.08
     minus_z_t:
       value: ((minus_z_t_upper_four_bits << 4) + 297.81) / 149.55 * 106.57 - 289.76
     battery_t_ut6:
# according to https://web.archive.org/web/20120516012116/http:/www.space.t.u-tokyo.ac.jp/gs/application.html this is the value for the secondary battery as the value in UT4 is.
# according to the document linked in the header of this file, this values is called battery temperature, the same as the UT4 value.
       value: ((battery_t_upper_four_bits << 4) + 297.06) / 149.31 * 105.86 - 287.71
     fm_transmitter_t:
       value: ((fm_transmitter_t_upper_four_bits << 4) + 299.60) / 150.17 * 106.91 - 290.31
     rssi_max_between_ut4_and_ut6:
# (*) This would be dBµV. To convert this into dBm for a resistor of 50 ohms, we substract 107.
       value: (rssi_max_between_ut4_and_ut6_raw * 4.77 * 4 / 255) - 107 # dBµV - 107 = dBm
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '6'


# reconstructing beacon

     value1:
        value: plus_x_t_upper_four_bits << 4
     value2:
        value: minus_x_t_upper_four_bits << 4
     value3:
        value: plus_y_t_upper_four_bits << 4
     value4:
        value: minus_y_t_upper_four_bits << 4
     value5:
        value: plus_z_t_upper_four_bits << 4
     value6:
        value: minus_z_t_upper_four_bits << 4
     value7:
        value: battery_t_upper_four_bits << 4
     value8:
        value: fm_transmitter_t_upper_four_bits << 4
     value9:
        value: rssi_max_between_ut4_and_ut6_raw



     value1_hex_left:
        value: value1 / 16

     value1_hex_left_digit:
        value: 'value1_hex_left.to_s == "10" ? "a" : (value1_hex_left.to_s == "11" ? "b" : (value1_hex_left.to_s == "12" ? "c" : (value1_hex_left.to_s == "13" ? "d" : (value1_hex_left.to_s == "14" ? "e" : (value1_hex_left.to_s == "15" ? "f" : value1_hex_left.to_s)))))'

     value1_hex:
        value: value1_hex_left_digit


     value2_hex_left:
        value: value2 / 16

     value2_hex_left_digit:
        value: 'value2_hex_left.to_s == "10" ? "a" : (value2_hex_left.to_s == "11" ? "b" : (value2_hex_left.to_s == "12" ? "c" : (value2_hex_left.to_s == "13" ? "d" : (value2_hex_left.to_s == "14" ? "e" : (value2_hex_left.to_s == "15" ? "f" : value2_hex_left.to_s)))))'

     value2_hex:
        value: value2_hex_left_digit


     value3_hex_left:
        value: value3 / 16

     value3_hex_left_digit:
        value: 'value3_hex_left.to_s == "10" ? "a" : (value3_hex_left.to_s == "11" ? "b" : (value3_hex_left.to_s == "12" ? "c" : (value3_hex_left.to_s == "13" ? "d" : (value3_hex_left.to_s == "14" ? "e" : (value3_hex_left.to_s == "15" ? "f" : value3_hex_left.to_s)))))'

     value3_hex:
        value: value3_hex_left_digit


     value4_hex_left:
        value: value4 / 16

     value4_hex_left_digit:
        value: 'value4_hex_left.to_s == "10" ? "a" : (value4_hex_left.to_s == "11" ? "b" : (value4_hex_left.to_s == "12" ? "c" : (value4_hex_left.to_s == "13" ? "d" : (value4_hex_left.to_s == "14" ? "e" : (value4_hex_left.to_s == "15" ? "f" : value4_hex_left.to_s)))))'

     value4_hex:
        value: value4_hex_left_digit


     value5_hex_left:
        value: value5 / 16

     value5_hex_left_digit:
        value: 'value5_hex_left.to_s == "10" ? "a" : (value5_hex_left.to_s == "11" ? "b" : (value5_hex_left.to_s == "12" ? "c" : (value5_hex_left.to_s == "13" ? "d" : (value5_hex_left.to_s == "14" ? "e" : (value5_hex_left.to_s == "15" ? "f" : value5_hex_left.to_s)))))'

     value5_hex:
        value: value5_hex_left_digit


     value6_hex_left:
        value: value6 / 16

     value6_hex_left_digit:
        value: 'value6_hex_left.to_s == "10" ? "a" : (value6_hex_left.to_s == "11" ? "b" : (value6_hex_left.to_s == "12" ? "c" : (value6_hex_left.to_s == "13" ? "d" : (value6_hex_left.to_s == "14" ? "e" : (value6_hex_left.to_s == "15" ? "f" : value6_hex_left.to_s)))))'

     value6_hex:
        value: value6_hex_left_digit


     value7_hex_left:
        value: value7 / 16

     value7_hex_left_digit:
        value: 'value7_hex_left.to_s == "10" ? "a" : (value7_hex_left.to_s == "11" ? "b" : (value7_hex_left.to_s == "12" ? "c" : (value7_hex_left.to_s == "13" ? "d" : (value7_hex_left.to_s == "14" ? "e" : (value7_hex_left.to_s == "15" ? "f" : value7_hex_left.to_s)))))'

     value7_hex:
        value: value7_hex_left_digit


     value8_hex_left:
        value: value8 / 16

     value8_hex_left_digit:
        value: 'value8_hex_left.to_s == "10" ? "a" : (value8_hex_left.to_s == "11" ? "b" : (value8_hex_left.to_s == "12" ? "c" : (value8_hex_left.to_s == "13" ? "d" : (value8_hex_left.to_s == "14" ? "e" : (value8_hex_left.to_s == "15" ? "f" : value8_hex_left.to_s)))))'

     value8_hex:
        value: value8_hex_left_digit


     value9_hex_left:
        value: value9 / 16

     value9_hex_left_digit:
        value: 'value9_hex_left.to_s == "10" ? "a" : (value9_hex_left.to_s == "11" ? "b" : (value9_hex_left.to_s == "12" ? "c" : (value9_hex_left.to_s == "13" ? "d" : (value9_hex_left.to_s == "14" ? "e" : (value9_hex_left.to_s == "15" ? "f" : value9_hex_left.to_s)))))'

     value9_hex_right:
        value: value9 % 16

     value9_hex_right_digit:
        value: 'value9_hex_right.to_s == "10" ? "a" : (value9_hex_right.to_s == "11" ? "b" : (value9_hex_right.to_s == "12" ? "c" : (value9_hex_right.to_s == "13" ? "d" : (value9_hex_right.to_s == "14" ? "e" : (value9_hex_right.to_s == "15" ? "f" : value9_hex_right.to_s)))))'

     value9_hex:
        value: value9_hex_left_digit + value9_hex_right_digit


     beacon:
       value: '"UT6 "+ value1_hex + value2_hex + value3_hex + value4_hex + value5_hex + value6_hex + value7_hex + value8_hex + value9_hex'




  discard: # this leads to a 'integer division or modulo by zero' and discards also the already parsed value "ut"
   seq:
     - id: discard
       type: b1

   instances:
     discard_discard:
       value: discard.to_i / 0
