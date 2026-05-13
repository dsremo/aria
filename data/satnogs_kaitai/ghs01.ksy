---
meta:
  id: ghs01
  title: GHS-01 CW decoder
  endian: be
doc-ref: "https://gifuhs2022.wordpress.com/通信フォーマット仕様/"
# 2025-09-12, DL7NDR
doc: |
  :field callsign: callsign
  :field s: s
  :field rssi: rssi
  :field bat_1v: bat_1v
  :field bat_2v: bat_2v
  :field bat_t: bat_t
  :field solar_minus_x: solar_minus_x
  :field solar_plus_x: solar_plus_x
  :field solar_plus_y: solar_plus_y
  :field solar_minus_y: solar_minus_y
  :field necessary_for_lengthcheck: necessary_for_lengthcheck
  :field beacon: beacon

seq:
  - id: callsign
    type: str
    size: 12
    encoding: ASCII
    valid: '"jj2yza ghs01"' # 6A 6A 32 79 7A 61 20 67 68 73 30 31

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
        if: s == "s1"
        value: value1

  bat_1v:
        if: s == "s1"
        value: value2 * 5.0 / 256

  bat_2v:
        if: s == "s1"
        value: value3 * 5.0 / 256

  bat_t:
        if: s == "s1"
        value: value4 * 5.0 / 256

  solar_minus_x:
        if: s == "s2"
        value: value1 * 5.0 / 256

  solar_plus_x:
        if: s == "s2"
        value: value2 * 5.0 / 256

  solar_plus_y:
        if: s == "s2"
        value: value3 * 5.0 / 256

  solar_minus_y:
        if: s == "s2"
        value: value4 * 5.0 / 256


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
