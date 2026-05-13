---
meta:
  id: co58
  title: CO-58 (XI-V) CW Beacon Decoder
  endian: be
doc-ref: "https://web.archive.org/web/20120516012116/http:/www.space.t.u-tokyo.ac.jp/gs/application.html"
# 2025-03-12, DL7NDR
doc: |
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
  :field rssi_max_between_xiv1_and_xiv2: beacon_types.type_check.rssi_max_between_xiv1_and_xiv2
  :field batt_v: beacon_types.type_check.batt_v
  :field sol_v: beacon_types.type_check.sol_v
  :field batt_t_from_ad_conversion: beacon_types.type_check.batt_t_from_ad_conversion
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
  :field fm_transmitter_t: beacon_types.type_check.fm_transmitter_t
  :field batt_v_from_obc: beacon_types.type_check.batt_v_from_obc
  :field sol_v_from_obc: beacon_types.type_check.sol_v_from_obc
  :field batt_t_from_obc: beacon_types.type_check.batt_t_from_obc
  :field rssi_max_between_xiv3_and_xiv6: beacon_types.type_check.rssi_max_between_xiv3_and_xiv6
  :field beacon: beacon_types.type_check.beacon
  :field discard: beacon_types.type_check.discard_discard

seq:
  - id: xiv
    type: str
    size: 3
    encoding: ASCII
    valid: '"xiv"' # 78 69 76

  - id: beacon_types
    type: beacon_types_t

types:
  beacon_types_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x3120: xiv1
            0x3220: xiv2
            0x3320: xiv3
            0x3420: xiv4
            0x3520: xiv5
            0x3620: xiv6
            _: discard

    instances:
      check:
        type: u2


  xiv1:
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
       value: '1'

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
        value: '"xiv1 "+ value1_hex + value2_hex + value3_hex'




  xiv2:
   seq:
     - id: byte_1
       type: u1
     - id: byte_2
       type: u1
     - id: byte_3
       type: u1
     - id: rssi_max_between_xiv1_and_xiv2_raw # see xiv6 for conversion explanation
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

     rssi_max_between_xiv1_and_xiv2:
       value: rssi_max_between_xiv1_and_xiv2_raw * 4.77 * 4 / 255 - 107
# The unit is dBµV (as RMS, I hope). "- 107" converts it into dBm.

     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

     beacon_type:
       value: '2'

# reconstructing beacon

     value1:
        value: byte_1
     value2:
        value: byte_2
     value3:
        value: byte_3
     value4:
        value: rssi_max_between_xiv1_and_xiv2_raw


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
        value: '"xiv2 "+ value1_hex + value2_hex + value3_hex + value4_hex'


  xiv3:
   seq:
     - id: batt_v_raw
       type: u1
     - id: sol_v_raw
       type: u1
     - id: batt_t_from_ad_conversion_raw
       type: u1
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
# There is no conversion mentioned in the documentation.
# However the XIV CW Decoder must use something like "* 0.07526666".
     batt_v:
        value: batt_v_raw * 0.07526666
# and here: * 0.0754
     sol_v:
        value: sol_v_raw * 0.0754
     batt_t_from_ad_conversion:
# I'm using here the same conversion as for batt_t_from_obc.
# However the XIV CW Decoder seems to uses a different conversion.
# The value of batt_t_from_ad_conversion should be near the value of batt_t_from_obc.
# The XIV CW Decoder produces big differences, my conversion is not so big.
# At the end, we should rely on the obc value with a given conversion.
        value: batt_t_from_ad_conversion_raw *0.5948 - 67.203
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '3'

# reconstructing beacon

     value1:
        value: batt_v_raw
     value2:
        value: sol_v_raw
     value3:
        value: batt_t_from_ad_conversion_raw


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
        value: '"xiv3 "+ value1_hex + value2_hex + value3_hex'


  xiv4:
   seq:
     - id: plus_x_i_raw
       type: u1
     - id: minus_x_i_raw
       type: u1
     - id: plus_y_i_raw
       type: u1
     - id: minus_y_i_raw
       type: u1
     - id: plus_z_i_raw
       type: u1
     - id: minus_z_i_raw
       type: u1
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
# The conversions are given with a "+" for the last mathematical term.
# plus_x_i_raw * 2.3957 + 2.7037
# minus_x_i_raw * 2.3823 + 2.3217
# plus_y_i_raw * 2.4234 + 1.6915
# minus_y_i_raw * 2.3724 + 3.2306
# plus_z_i_raw * 2.3840 + 2.1696
# minus_z_i_raw * 2.4341 + 4.7714
# This means no value can ever reach 0 mA.
# I've seen many xiv4 beacons like "010101010101" (but never "000000000000") what probably should return zero values.
# So there must be something wrong, even if the "XI-V CW Converter" tool also uses theses conversions.
# Therefore I like to go the way using "- 2.4" for the last term and "* 2.4" for the first term which seems accurate enough regarding a step width of 2 mA.
# "010101010101" should then return zero values.

     plus_x_i:
       value: plus_x_i_raw * 2.4 - 2.4
     minus_x_i:
       value: minus_x_i_raw * 2.4 - 2.4
     plus_y_i:
       value: plus_y_i_raw * 2.4 - 2.4
     minus_y_i:
       value: minus_y_i_raw * 2.4 - 2.4
     plus_z_i:
       value: plus_z_i_raw * 2.4 - 2.4
     minus_z_i:
       value: minus_z_i_raw * 2.4 - 2.4
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '4'


# reconstructing beacon

     value1:
        value: plus_x_i_raw
     value2:
        value: minus_x_i_raw
     value3:
        value: plus_y_i_raw
     value4:
        value: minus_y_i_raw
     value5:
        value: plus_z_i_raw
     value6:
        value: minus_z_i_raw


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


     value5_hex_left:
        value: value5 / 16

     value5_hex_left_digit:
        value: 'value5_hex_left.to_s == "10" ? "a" : (value5_hex_left.to_s == "11" ? "b" : (value5_hex_left.to_s == "12" ? "c" : (value5_hex_left.to_s == "13" ? "d" : (value5_hex_left.to_s == "14" ? "e" : (value5_hex_left.to_s == "15" ? "f" : value5_hex_left.to_s)))))'

     value5_hex_right:
        value: value5 % 16

     value5_hex_right_digit:
        value: 'value5_hex_right.to_s == "10" ? "a" : (value5_hex_right.to_s == "11" ? "b" : (value5_hex_right.to_s == "12" ? "c" : (value5_hex_right.to_s == "13" ? "d" : (value5_hex_right.to_s == "14" ? "e" : (value5_hex_right.to_s == "15" ? "f" : value5_hex_right.to_s)))))'

     value5_hex:
        value: value5_hex_left_digit + value5_hex_right_digit


     value6_hex_left:
        value: value6 / 16

     value6_hex_left_digit:
        value: 'value6_hex_left.to_s == "10" ? "a" : (value6_hex_left.to_s == "11" ? "b" : (value6_hex_left.to_s == "12" ? "c" : (value6_hex_left.to_s == "13" ? "d" : (value6_hex_left.to_s == "14" ? "e" : (value6_hex_left.to_s == "15" ? "f" : value6_hex_left.to_s)))))'

     value6_hex_right:
        value: value6 % 16

     value6_hex_right_digit:
        value: 'value6_hex_right.to_s == "10" ? "a" : (value6_hex_right.to_s == "11" ? "b" : (value6_hex_right.to_s == "12" ? "c" : (value6_hex_right.to_s == "13" ? "d" : (value6_hex_right.to_s == "14" ? "e" : (value6_hex_right.to_s == "15" ? "f" : value6_hex_right.to_s)))))'

     value6_hex:
        value: value6_hex_left_digit + value6_hex_right_digit


     beacon:
        value: '"xiv4 "+ value1_hex + value2_hex + value3_hex + value4_hex + value5_hex + value6_hex'




  xiv5:
   seq:
     - id: plus_x_t_raw
       type: u1
     - id: minus_x_t_raw
       type: u1
     - id: plus_y_t_raw
       type: u1
     - id: minus_y_t_raw
       type: u1
     - id: plus_z_t_raw
       type: u1
     - id: minus_z_t_raw
       type: u1
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length


   instances:
# The conversions given in the link mentioned in the doc-ref part have an error.
# It's not "+65.xxx" but "-65.xxx"
     plus_x_t:
       value: plus_x_t_raw *0.5896 - 65.614
     minus_x_t:
       value: minus_x_t_raw *0.5916 - 66.133 
     plus_y_t:
       value: plus_y_t_raw *0.5862 - 65.813
     minus_y_t:
       value: minus_y_t_raw *0.5846 - 66.280
     plus_z_t:
       value: plus_z_t_raw *0.5880 - 64.903
     minus_z_t:
       value: minus_z_t_raw *0.5932 - 66.483
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '5'


# reconstructing beacon

     value1:
        value: plus_x_t_raw
     value2:
        value: minus_x_t_raw
     value3:
        value: plus_y_t_raw
     value4:
        value: minus_y_t_raw
     value5:
        value: plus_z_t_raw
     value6:
        value: minus_z_t_raw


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


     value5_hex_left:
        value: value5 / 16

     value5_hex_left_digit:
        value: 'value5_hex_left.to_s == "10" ? "a" : (value5_hex_left.to_s == "11" ? "b" : (value5_hex_left.to_s == "12" ? "c" : (value5_hex_left.to_s == "13" ? "d" : (value5_hex_left.to_s == "14" ? "e" : (value5_hex_left.to_s == "15" ? "f" : value5_hex_left.to_s)))))'

     value5_hex_right:
        value: value5 % 16

     value5_hex_right_digit:
        value: 'value5_hex_right.to_s == "10" ? "a" : (value5_hex_right.to_s == "11" ? "b" : (value5_hex_right.to_s == "12" ? "c" : (value5_hex_right.to_s == "13" ? "d" : (value5_hex_right.to_s == "14" ? "e" : (value5_hex_right.to_s == "15" ? "f" : value5_hex_right.to_s)))))'

     value5_hex:
        value: value5_hex_left_digit + value5_hex_right_digit


     value6_hex_left:
        value: value6 / 16

     value6_hex_left_digit:
        value: 'value6_hex_left.to_s == "10" ? "a" : (value6_hex_left.to_s == "11" ? "b" : (value6_hex_left.to_s == "12" ? "c" : (value6_hex_left.to_s == "13" ? "d" : (value6_hex_left.to_s == "14" ? "e" : (value6_hex_left.to_s == "15" ? "f" : value6_hex_left.to_s)))))'

     value6_hex_right:
        value: value6 % 16

     value6_hex_right_digit:
        value: 'value6_hex_right.to_s == "10" ? "a" : (value6_hex_right.to_s == "11" ? "b" : (value6_hex_right.to_s == "12" ? "c" : (value6_hex_right.to_s == "13" ? "d" : (value6_hex_right.to_s == "14" ? "e" : (value6_hex_right.to_s == "15" ? "f" : value6_hex_right.to_s)))))'

     value6_hex:
        value: value6_hex_left_digit + value6_hex_right_digit

     beacon:
       value: '"xiv5 "+ value1_hex + value2_hex + value3_hex + value4_hex + value5_hex + value6_hex'




  xiv6:
   seq:
     - id: fm_transmitter_t_raw
       type: u1
     - id: batt_v_from_obc_raw
       type: u1
     - id: sol_v_from_obc_raw
       type: u1
     - id: batt_t_from_obc_raw
       type: u1
     - id: rssi_max_between_xiv3_and_xiv6_raw
# There is no conversion given for this value. Look for (*) for more explanation.
       type: u1
     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
     fm_transmitter_t:
       value: fm_transmitter_t_raw * 0.5811 - 67.055
     batt_v_from_obc:
        value: batt_v_from_obc_raw * 4.5 / 255
     sol_v_from_obc:
        value: sol_v_from_obc_raw * 4.5 * 74.9 / 18.7 / 255
     batt_t_from_obc:
        value: batt_t_from_obc_raw * 0.5948 - 67.203 
     rssi_max_between_xiv3_and_xiv6:
# (*)
# There is no conversion given for CO-58. Using the one for CO-57 (* 4.77 * 4 / 255), it produces values different from those from the XI-V CW Converter.
# From the values XI-V CW Converter produces, I've gained "* 0.0188".
# However, this would generate only values between 0 dBµV and 4.8 dBµV (for 0xff) [-102.2 dBm if dBµV is RMS].
# I prefer the conversion used for CO-57. For 0xff this makes 19.08 dBµV.
# If we interpret dBµV as RMS, 19.08 dBµV would make -87.9 dBm.
# Using the CO-57 conversion, we have a much wider (more realistic) RSSI range.
       value: rssi_max_between_xiv3_and_xiv6_raw * 4.77 * 4 / 255 - 107
# The unit is dBµV. To convert it into dBm (at 50 Ohm), I do "- 107"
     discard_discard:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing
     beacon_type:
       value: '6'

# reconstructing beacon

     value1:
        value: fm_transmitter_t_raw
     value2:
        value: batt_v_from_obc_raw
     value3:
        value: sol_v_from_obc_raw
     value4:
        value: batt_t_from_obc_raw
     value5:
        value: rssi_max_between_xiv3_and_xiv6_raw


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


     value5_hex_left:
        value: value5 / 16

     value5_hex_left_digit:
        value: 'value5_hex_left.to_s == "10" ? "a" : (value5_hex_left.to_s == "11" ? "b" : (value5_hex_left.to_s == "12" ? "c" : (value5_hex_left.to_s == "13" ? "d" : (value5_hex_left.to_s == "14" ? "e" : (value5_hex_left.to_s == "15" ? "f" : value5_hex_left.to_s)))))'

     value5_hex_right:
        value: value5 % 16

     value5_hex_right_digit:
        value: 'value5_hex_right.to_s == "10" ? "a" : (value5_hex_right.to_s == "11" ? "b" : (value5_hex_right.to_s == "12" ? "c" : (value5_hex_right.to_s == "13" ? "d" : (value5_hex_right.to_s == "14" ? "e" : (value5_hex_right.to_s == "15" ? "f" : value5_hex_right.to_s)))))'

     value5_hex:
        value: value5_hex_left_digit + value5_hex_right_digit



     beacon:
       value: '"xiv6 "+ value1_hex + value2_hex + value3_hex + value4_hex + value5_hex'




  discard: # this leads to a 'integer division or modulo by zero' and discards also the already parsed value "ut"
   seq:
     - id: discard
       type: b1

   instances:
     discard_discard:
       value: discard.to_i / 0
