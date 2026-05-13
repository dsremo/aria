---
meta:
  id: kosen1
  title: KOSEN-1 CW decoder
  endian: be
doc-ref: "https://space.kochi-ct.jp/kosen-1/"
# 2024-10-23, DL7NDR
doc: |
  :field callsign: callsign
  :field s: s
  :field rssi: rssi
  :field battery_temperature: bat_t
  :field battery_voltage: bat_v
  :field battery_current: bat_i
  :field load_current: load_i
  :field solar_cell_output_current_minus_z: sc_z
  :field solar_cell_output_current_minus_y: sc_y
  :field solar_cell_output_current_minus_x: sc_x
  :field necessary_for_lengthcheck: necessary_for_lengthcheck
  :field beacon: beacon

seq:
  - id: callsign
    type: str
    size: 8
    encoding: ASCII
    valid: '"kosen-1 "' # 6B 6F 73 65 6E 2D 31 20 (like a sync word)

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

  - id: lengthcheck # the beacon should end by value4. if there is more to parse, the whole frame will be discarded due to 'necessary_for_lengthcheck'
    type: str
    encoding: utf-8 # if un-encodeable, whole frame will be discarded
    size-eos: true


instances:
  necessary_for_lengthcheck:
        if: lengthcheck.length != 0 # if so, whole frame will be discarded
        value: lengthcheck.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

  rssi:
        if: value1 != 255 and s == "s1" # if value1 == 255, this value will be 'null'. 0xff (=255) has to be sent, if character of a pair couldn't be received correctly, but other values shall be processed.
        value: 0.409 * value1 - 127.4

  bat_t:
        if: value2 != 255 and s == "s1"
        value: 0.00003 * value2 * value2 * value2 - 0.011 * value2 * value2 + 1.49 * value2 - 28.1

  bat_v:
        if: value3 != 255 and s == "s1"
        value: 0.0253 * value3

  bat_i:
        if: value4 != 255 and s == "s1"
        value: (value4 - 128) / 0.0512

  load_i:
        if: value1 != 255 and s == "s2"
        value: value1 / 0.1024

  sc_z:
        if: value2 != 255 and s == "s2"
        value: value2 / 0.256

  sc_y:
        if: value3 != 255 and s == "s2"
        value: value3 / 0.256

  sc_x:
        if: value4 != 255 and s == "s2" # "and" has to be written with lower case letters
        value: value4 / 0.256


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
