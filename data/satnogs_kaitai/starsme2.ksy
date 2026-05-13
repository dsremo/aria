---
meta:
  id: starsme2
  title: STARS-Me2 CW decoder
  endian: be
doc-ref: "http://stars.eng.shizuoka.ac.jp/english/CW_Telemetry_format.pdf"
# 2025-09-17, DL7NDR
# only s1 and s2 beacons
doc: |
  :field s: s
  :field beacon_no: beacon_no
  :field rssi: rssi
  :field micro_switch_status_deployment: micro_switch_status_deployment
  :field micro_switch_status_mission: micro_switch_status_mission
  :field micro_switch_status_paddle: micro_switch_status_paddle
  :field bus_voltage: bus_voltage
  :field bus_current: bus_current
  :field main_cpu_voltage: main_cpu_voltage
  :field battery_voltage: battery_voltage
  :field beacon: beacon

seq:
  - id: identifier
    type: str
    size: 6
    encoding: ASCII
    valid:
      any-of:
        - '"jj2yxo"'

  - id: s
    type: str
    size: 1
    encoding: ASCII
    valid:
      any-of:
        - '"s"'

  - id: beacon_no
    type: str
    size: 1
    encoding: ASCII
    valid:
      any-of:
        - '"1"'
        - '"2"'

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
        if: lengthcheck.length != 0
        value: lengthcheck.to_i / 0 # in case of an integer, this produces 'ZeroDivisionError' and stops parsing else it produces 'ValueError: invalid literal for int()'

  rssi:
        if: beacon_no == "1"
        value: value1

  micro_switch_status_deployment:
        if: beacon_no == "1"
        value: value2

  micro_switch_status_mission:
        if: beacon_no == "1"
        value: value3

  micro_switch_status_paddle:
        if: beacon_no == "1"
        value: value4

  bus_voltage:
        if: beacon_no == "2"
        value: value1 * 0.039

  bus_current:
        if: beacon_no == "2"
        value: value2 * 0.0296

  main_cpu_voltage:
        if: beacon_no == "2"
        value: value3 * 0.039

  battery_voltage:
        if: beacon_no == "2"
        value: value4 * 0.0195


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
        value: 'value1_hex_left_digit + value1_hex_right_digit'


  value2_hex_left:
        value: value2 / 16

  value2_hex_left_digit:
        value: 'value2_hex_left.to_s == "10" ? "a" : (value2_hex_left.to_s == "11" ? "b" : (value2_hex_left.to_s == "12" ? "c" : (value2_hex_left.to_s == "13" ? "d" : (value2_hex_left.to_s == "14" ? "e" : (value2_hex_left.to_s == "15" ? "f" : value2_hex_left.to_s)))))'

  value2_hex_right:
        value: value2 % 16

  value2_hex_right_digit:
        value: 'value2_hex_right.to_s == "10" ? "a" : (value2_hex_right.to_s == "11" ? "b" : (value2_hex_right.to_s == "12" ? "c" : (value2_hex_right.to_s == "13" ? "d" : (value2_hex_right.to_s == "14" ? "e" : (value2_hex_right.to_s == "15" ? "f" : value2_hex_right.to_s)))))'

  value2_hex:
        value: 'value2_hex_left_digit + value2_hex_right_digit'


  value3_hex_left:
        value: value3 / 16

  value3_hex_left_digit:
        value: 'value3_hex_left.to_s == "10" ? "a" : (value3_hex_left.to_s == "11" ? "b" : (value3_hex_left.to_s == "12" ? "c" : (value3_hex_left.to_s == "13" ? "d" : (value3_hex_left.to_s == "14" ? "e" : (value3_hex_left.to_s == "15" ? "f" : value3_hex_left.to_s)))))'

  value3_hex_right:
        value: value3 % 16

  value3_hex_right_digit:
        value: 'value3_hex_right.to_s == "10" ? "a" : (value3_hex_right.to_s == "11" ? "b" : (value3_hex_right.to_s == "12" ? "c" : (value3_hex_right.to_s == "13" ? "d" : (value3_hex_right.to_s == "14" ? "e" : (value3_hex_right.to_s == "15" ? "f" : value3_hex_right.to_s)))))'

  value3_hex:
        value: 'value3_hex_left_digit + value3_hex_right_digit'


  value4_hex_left:
        value: value4 / 16

  value4_hex_left_digit:
        value: 'value4_hex_left.to_s == "10" ? "a" : (value4_hex_left.to_s == "11" ? "b" : (value4_hex_left.to_s == "12" ? "c" : (value4_hex_left.to_s == "13" ? "d" : (value4_hex_left.to_s == "14" ? "e" : (value4_hex_left.to_s == "15" ? "f" : value4_hex_left.to_s)))))'

  value4_hex_right:
        value: value4 % 16

  value4_hex_right_digit:
        value: 'value4_hex_right.to_s == "10" ? "a" : (value4_hex_right.to_s == "11" ? "b" : (value4_hex_right.to_s == "12" ? "c" : (value4_hex_right.to_s == "13" ? "d" : (value4_hex_right.to_s == "14" ? "e" : (value4_hex_right.to_s == "15" ? "f" : value4_hex_right.to_s)))))'

  value4_hex:
        value: 'value4_hex_left_digit + value4_hex_right_digit'


  beacon:
        value: 's + beacon_no + " " + value1_hex + " " + value2_hex + " " + value3_hex + " " + value4_hex'
