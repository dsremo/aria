---
meta:
  id: teikyosat4
  title: TeikyoSat-4 CW decoder
  endian: be
doc-ref: "https://drive.usercontent.google.com/download?id=1pdAPBraX38qtzIzjj6hehnZAioILPKhL&export=download"
# 2025-03-16, DL7NDR
doc: |
  :field s: s
  :field rssi_vhf: rssi_vhf
  :field rssi_shf: rssi_shf
  :field debug_connector: debug_connector
  :field gnd: gnd
  :field plus_x: plus_x
  :field plus_y: plus_y
  :field minus_x: minus_x
  :field minus_y: minus_y
  :field necessary_for_lengthcheck: necessary_for_lengthcheck
  :field beacon: beacon

seq:
  - id: s
    type: str
    size: 2
    encoding: ASCII
    valid:
      any-of:
        - '"s1"'
        - '"s2"'
        - '"S1"'
        - '"S2"'

  - id: value1
    type: u1

  - id: value2
    type: u1

  - id: value3
    type: u1

  - id: value4
    type: u1

  - id: lengthcheck # The beacon should end with value4. If there is more to parse, the whole frame will be discarded due to 'necessary_for_lengthcheck'
    type: str
    encoding: utf-8 # if un-encodeable, whole frame will be discarded
    size-eos: true


instances:
  necessary_for_lengthcheck:
        if: lengthcheck.length != 0 # if so, whole frame will be discarded
        value: lengthcheck.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

  rssi_vhf:
        if: s == "s1" or s == "S1"
        value: value1 * 5.00 / 255

  rssi_shf:
        if: s == "s1" or s == "S1"
        value: value2 * 5.00 / 255

  debug_connector:
        if: s == "s1" or s == "S1"
        value: value3

  gnd:
        if: s == "s1" or s == "S1"
        value: value4

  plus_x:
        if: s == "s2" or s == "S2"
        value: value1 * 5.00 / 255

  plus_y:
        if: s == "s2" or s == "S2"
        value: value2 * 5.00 / 255

  minus_x:
        if: s == "s2" or s == "S2"
        value: value3 * 5.00 / 255

  minus_y:
        if: s == "s2" or s == "S2"
        value: value4 * 5.00 / 255


# reformating from integer to hex to show beacon

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


  beacon:
        value: 's + " " + value1_hex + " " + value2_hex + " " + value3_hex + " " + value4_hex'
