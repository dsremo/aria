---
meta:
  id: stars
  title: STARS CW decoder
  endian: be
doc-ref: "http://stars.eng.shizuoka.ac.jp/english/CW_Telemetry_format.pdf"
# 2025-06-09, DL7NDR
doc: |
  :field rm: rm
  :field beacon_no: beacon_no
  :field satellite_time: satellite_time
  :field condition: condition
  :field rssi: rssi
  :field temperature_1: temperature_1
  :field temperature_2: temperature_2
  :field temperature_3: temperature_3
  :field mode: mode
  :field reset_times_of_com_system: reset_times_of_com_system
  :field receive_times_of_cdh: receive_times_of_cdh
  :field solarcell_current: solarcell_current
  :field solarcell_voltage: solarcell_voltage
  :field total_system_current: total_system_current
  :field total_voltage: total_voltage
  :field solarcell_voltage_cdh: solarcell_voltage_cdh
  :field total_voltage_cdh: total_voltage_cdh
  :field necessary_for_lengthcheck: necessary_for_lengthcheck
  :field beacon: beacon

seq:
  - id: rm
    type: str
    size: 1
    encoding: ASCII
    valid:
      any-of:
        - '"r"'
        - '"m"'

  - id: beacon_no
    type: str
    size: 1
    encoding: ASCII
    valid:
      any-of:
        - '"2"'
        - '"3"'
        - '"4"'
        - '"5"'
        - '"6"'

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

  satellite_time:
        if: beacon_no == "2"
        value: (value1 << 16) | (value2 << 8) | value3

  condition:
        if: beacon_no == "2"
        value: value4

  rssi:
        if: beacon_no == "3"
        value: value1 / 2

  temperature_1:
        if: beacon_no == "3"
        value: value2
# ln (50 * value2 / 255) / (5 - ((5 * value2) / 255))) * (-24.96) + 87.802

  temperature_2:
        if: beacon_no == "3"
        value: value3

  temperature_3:
        if: beacon_no == "3"
        value: value4

  mode:
        if: beacon_no == "4"
        value: value1

  reset_times_of_com_system:
        if: beacon_no == "4"
        value: value2

  receive_times_of_cdh:
        if: beacon_no == "4"
        value: value4

  solarcell_current:
        if: beacon_no == "5"
        value: value1 * 0.007906

  solarcell_voltage:
        if: beacon_no == "5"
        value: value2 * 0.05888

  total_system_current:
        if: beacon_no == "5"
        value: value3 * 0.025138

  total_voltage:
        if: beacon_no == "5"
        value: value4 * 0.05888

  solarcell_voltage_cdh:
        if: beacon_no == "6"
        value: ((value1 << 8) | value2) * 0.05888

  total_voltage_cdh:
        if: beacon_no == "6"
        value: ((value3 << 8) | value4) * 0.05888


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
        value: 'rm + beacon_no + " " + value1_hex + " " + value2_hex + " " + value3_hex + " " + value4_hex'
