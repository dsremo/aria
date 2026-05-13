---
meta:
  id: fo29
  title: FO-29 CW decoder
  endian: be 
doc-ref: https://www.jarl.org/Japanese/3_Fuji/teleme/tlm.htm
# 2025-01-18, DL7NDR
doc: |
  :field header_hihi: header_hihi
  :field main_relay: main_relay
  :field dcm: dcm
  :field sram: sram
  :field packet: packet
  :field jta: jta
  :field jtd: jtd
  :field geomagnetism_sensor: geomagnetism_sensor
  :field sun_sensor: sun_sensor
  :field uvc: uvc
  :field uvc_level: uvc_level
  :field pcu_mode: pcu_mode
  :field pcu_level: pcu_level
  :field battery_mode: battery_mode
  :field battery_logic: battery_logic
  :field data_collect_mode: data_collect_mode
  :field repro_mode: repro_mode
  :field packet_hk_date_mode: packet_hk_date_mode
  :field packet_date_collect_mode: packet_date_collect_mode
  :field digitalker_mode: digitalker_mode
  :field double_cmd_ena_dis: double_cmd_ena_dis
  :field uvc_active_passive: uvc_active_passive
  :field cpu_run_reset: cpu_run_reset
  :field ecc_1d: ecc_1d
  :field wdt_1d: wdt_1d
  :field crc_error_1d: crc_error_1d
  :field sc_1d: sc_1d
  :field mem_sel_1_1d: mem_sel_1_1d
  :field mem_sel_2_1d: mem_sel_2_1d
  :field frame_counter_error_1d: frame_counter_error_1d
  :field fm_1d: fm_1d
  :field engineering_data_2a: engineering_data_2a
  :field engineering_data_2b: engineering_data_2b
  :field spin_period: spin_period
  :field magnetorquer_mtq_x_1: magnetorquer_mtq_x_1
  :field magnetorquer_mtq_x_2: magnetorquer_mtq_x_2
  :field magnetorquer_mtq_x_mbc_cont: magnetorquer_mtq_x_mbc_cont
  :field magnetorquer_mtq_x_plus: magnetorquer_mtq_x_plus
  :field magnetorquer_mtq_y_spin_null: magnetorquer_mtq_y_spin_null
  :field magnetorquer_mtq_y_spin: magnetorquer_mtq_y_spin
  :field magnetorquer_mtq_y_1: magnetorquer_mtq_y_1
  :field magnetorquer_mtq_y_2: magnetorquer_mtq_y_2
  :field sun_angle_changed: sun_angle_changed
  :field sun_angle: sun_angle
  :field magnet_sensor_z_axis: magnet_sensor_z_axis
  :field magnet_sensor_x_axis: magnet_sensor_x_axis
  :field current_from_solar_cells: current_from_solar_cells
  :field battery_charge_and_discharge_current: battery_charge_and_discharge_current
  :field battery_voltage: battery_voltage
  :field battery_intermediate_terminal_voltage: battery_intermediate_terminal_voltage
  :field bus_voltage: bus_voltage
  :field jta_tx_power: jta_tx_power
  :field structure_temperature_1: structure_temperature_1
  :field structure_temperature_2: structure_temperature_2
  :field structure_temperature_3: structure_temperature_3
  :field structure_temperature_4: structure_temperature_4
  :field battery_temperature: battery_temperature
  :field beacon: beacon
  :field necessary_for_lengthcheck: necessary_for_lengthcheck

seq:
  - id: header_hihi
    type: str
    size: 4
    encoding: ASCII
    valid: '"HIHI"'
      
  - id: byte_1a_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_1b_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_1c_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_1d_ascii
    type: str
    size: 2
    encoding: ASCII
    
  - id: byte_2a_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_2b_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_2c_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_2d_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_3a_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_3b_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_3c_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_3d_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_4a_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_4b_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_4c_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_4d_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_5a_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_5b_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_5c_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_5d_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_6a_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_6b_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: byte_6c_ascii
    type: str
    size: 2
    encoding: ASCII

  - id: lengthcheck 
    type: str
    encoding: utf-8
    size-eos: true # accepts zero length


instances:
  necessary_for_lengthcheck:
    if: lengthcheck.length != 0 # if so, whole frame will be discarded
    value: lengthcheck.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

# byte 1 (1A)
  main_relay:
    if: byte_1a_ascii.substring(0,1) != "*" and byte_1a_ascii.substring(1,2) != "*" # discards this value, if at least one part of the ascii-byte is an asterisk (*)
    value: (byte_1a_ascii.to_i(16) & 0b00000001) # 0 = ON (for all other values like this, 0 means OFF)

  dcm: # dcm= satellite's computer. if OFF, only the top 3 bits of byte 3B will be outputed
    if: byte_1a_ascii.substring(0,1) != "*" and byte_1a_ascii.substring(1,2) != "*"
    value: (byte_1a_ascii.to_i(16) & 0b00000010) >> 1

  sram:
    if: byte_1a_ascii.substring(0,1) != "*" and byte_1a_ascii.substring(1,2) != "*"
    value: (byte_1a_ascii.to_i(16) & 0b00000100) >> 2

  packet:
    if: byte_1a_ascii.substring(0,1) != "*" and byte_1a_ascii.substring(1,2) != "*"
    value: (byte_1a_ascii.to_i(16) & 0b00011000) >> 3 # b00 = OFF; b01 = 1200; b10 = 9600; b11 = not used

  jta:
    if: byte_1a_ascii.substring(0,1) != "*" and byte_1a_ascii.substring(1,2) != "*"
    value: (byte_1a_ascii.to_i(16) & 0b00100000) >> 5

  jtd:
    if: byte_1a_ascii.substring(0,1) != "*" and byte_1a_ascii.substring(1,2) != "*"
    value: (byte_1a_ascii.to_i(16) & 0b01000000) >> 6

  geomagnetism_sensor:
    if: byte_1a_ascii.substring(0,1) != "*" and byte_1a_ascii.substring(1,2) != "*"
    value: (byte_1a_ascii.to_i(16) & 0b10000000) >> 7

# byte 2 (1B)
  sun_sensor:
    if: byte_1b_ascii.substring(0,1) != "*" and byte_1b_ascii.substring(1,2) != "*"
    value: (byte_1b_ascii.to_i(16) & 0b00000001)

  uvc:
    if: byte_1b_ascii.substring(0,1) != "*" and byte_1b_ascii.substring(1,2) != "*"
    value: (byte_1b_ascii.to_i(16) & 0b00000010) >> 1

  uvc_level:
    if: byte_1b_ascii.substring(0,1) != "*" and byte_1b_ascii.substring(1,2) != "*"
    value: (byte_1b_ascii.to_i(16) & 0b00000100) >> 2 # 1 = 2; 0 = 1

  pcu_mode:
    if: byte_1b_ascii.substring(0,1) != "*" and byte_1b_ascii.substring(1,2) != "*"
    value: (byte_1b_ascii.to_i(16) & 0b00001000) >> 3 # 1 = manual; 0 = auto

  pcu_level:
    if: byte_1b_ascii.substring(0,1) != "*" and byte_1b_ascii.substring(1,2) != "*"
    value: (byte_1b_ascii.to_i(16) & 0b00110000) >> 4 # b00 = 0; b01 = 2; b10 = 3; b11 = not used

  battery_mode:
    if: byte_1b_ascii.substring(0,1) != "*" and byte_1b_ascii.substring(1,2) != "*"
    value: (byte_1b_ascii.to_i(16) & 0b01000000) >> 6 # 1 = trickle (=slow charging); 0 = full

  battery_logic:
    if: byte_1b_ascii.substring(0,1) != "*" and byte_1b_ascii.substring(1,2) != "*"
    value: (byte_1b_ascii.to_i(16) & 0b10000000) >> 7 # 1 = trickle (=slow charging); 0 = full

# byte 3 (1C)
  data_collect_mode:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b00000001)

  repro_mode:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b00000010) >> 1

  packet_hk_date_mode:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b00000100) >> 2

  packet_date_collect_mode:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b00001000) >> 3

  digitalker_mode:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b00010000) >> 4

  double_cmd_ena_dis:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b00100000) >> 5

  uvc_active_passive:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b01000000) >> 6

  cpu_run_reset:
    if: byte_1c_ascii.substring(0,1) != "*" and byte_1c_ascii.substring(1,2) != "*"
    value: (byte_1c_ascii.to_i(16) & 0b10000000) >> 7

# byte 4 (1D)
  ecc_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b00000001)

  wdt_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b00000010) >> 1

  crc_error_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b00000100) >> 2

  sc_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b00001000) >> 3

  mem_sel_1_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b00010000) >> 4

  mem_sel_2_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b00100000) >> 5

  frame_counter_error_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b01000000) >> 6

  fm_1d:
    if: byte_1d_ascii.substring(0,1) != "*" and byte_1d_ascii.substring(1,2) != "*"
    value: (byte_1d_ascii.to_i(16) & 0b10000000) >> 7



# byte 5 (2A)
  engineering_data_2a:
    if: byte_2a_ascii.substring(0,1) != "*" and byte_2a_ascii.substring(1,2) != "*"
    value: byte_2a_ascii.to_i(16)

# byte 6 (2B)
  engineering_data_2b:
    if: byte_2b_ascii.substring(0,1) != "*" and byte_2b_ascii.substring(1,2) != "*"
    value: byte_2b_ascii.to_i(16)

# byte 7 (2C) + byte 8 (2D)
  spin_period:
    if: byte_2c_ascii.substring(0,1) != "*" and byte_2c_ascii.substring(1,2) != "*" and byte_2d_ascii.substring(0,1) != "*" and byte_2d_ascii.substring(1,2) != "*"
    value: ((byte_2c_ascii.to_i(16) & 0b00000100) >> 2) * 8192 + ((byte_2c_ascii.to_i(16) & 0b00001000) >> 3) * 4096 + ((byte_2c_ascii.to_i(16) & 0b00010000) >> 4) * 2048 + ((byte_2c_ascii.to_i(16) & 0b00100000) >> 5) * 1024 + ((byte_2c_ascii.to_i(16) & 0b01000000) >> 6) * 512 + ((byte_2c_ascii.to_i(16) & 0b10000000) >> 7) * 256 + (byte_2d_ascii.to_i(16) & 0b00000001) * 128 + ((byte_2d_ascii.to_i(16) & 0b00000010) >> 1) * 64 + ((byte_2d_ascii.to_i(16) & 0b00000100) >> 2) * 32 + ((byte_2d_ascii.to_i(16) & 0b00001000) >> 3) * 16 + ((byte_2d_ascii.to_i(16) & 0b00010000) >> 4) * 8 + ((byte_2d_ascii.to_i(16) & 0b00100000) >> 5) * 4 + ((byte_2d_ascii.to_i(16) & 0b01000000) >> 6) * 2 + ((byte_2d_ascii.to_i(16) & 0b10000000) >> 7)



# i'm not sure how to interpret the bits for byte 3a (magnetorquer) https://www.jarl.org/Japanese/3_Fuji/teleme/tlm.htm
# byte 9 (3A)
  magnetorquer_mtq_x_1:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: byte_3a_ascii.to_i(16) & 0b00000001

  magnetorquer_mtq_x_2:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: (byte_3a_ascii.to_i(16) & 0b00000010) >> 1

  magnetorquer_mtq_x_mbc_cont:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: (byte_3a_ascii.to_i(16) & 0b00000100) >> 2

  magnetorquer_mtq_x_plus:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: (byte_3a_ascii.to_i(16) & 0b00001000) >> 3

  magnetorquer_mtq_y_spin_null:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: (byte_3a_ascii.to_i(16) & 0b00010000) >> 4

  magnetorquer_mtq_y_spin:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: (byte_3a_ascii.to_i(16) & 0b00100000) >> 5

  magnetorquer_mtq_y_1:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: (byte_3a_ascii.to_i(16) & 0b01000000) >> 6

  magnetorquer_mtq_y_2:
    if: byte_3a_ascii.substring(0,1) != "*" and byte_3a_ascii.substring(1,2) != "*"
    value: (byte_3a_ascii.to_i(16) & 0b10000000) >> 7

# byte 10 (3B)
  sun_angle_changed: # ... since last value: 1 = yes; 0 = no
    if: byte_3b_ascii.substring(0,1) != "*" and byte_3b_ascii.substring(1,2) != "*" and dcm == 1  # if dcm == 0, values wouldn't be valid
    value: (byte_3b_ascii.to_i(16) & 0b10000000) >> 7

  sun_bin: # need this only for calculating of sun_angle
    if: byte_3b_ascii.substring(0,1) != "*" and byte_3b_ascii.substring(1,2) != "*" and dcm == 1  # if dcm == 0, values wouldn't be valid
    value: byte_3b_ascii.to_i(16) & 0b01111111

  sun_angle:
    if: byte_3b_ascii.substring(0,1) != "*" and byte_3b_ascii.substring(1,2) != "*" and dcm == 1  # if dcm == 0, values wouldn't be valid
    value: 'sun_bin == 1 ? 27.5 : (sun_bin == 3 ? 28.5 : sun_bin == 2 ? 29.5 : sun_bin == 6 ? 30.5 : sun_bin == 7 ? 31.5 : sun_bin == 5 ? 32.5 : sun_bin == 4 ? 33.5 : sun_bin == 12 ? 34.5 : sun_bin == 13 ? 35.5 : sun_bin == 15 ? 36.5 : sun_bin == 14 ? 37.5 : sun_bin == 10 ? 38.5 : sun_bin == 11 ? 39.5 : sun_bin == 9 ? 40.5 : sun_bin == 8 ? 41.5 : sun_bin == 24 ? 42.5 : sun_bin == 25 ? 43.5 : sun_bin == 27 ? 44.5 : sun_bin == 26 ? 45.5 : sun_bin == 30 ? 46.5 : sun_bin == 31 ? 47.5 : sun_bin == 29 ? 48.5 : sun_bin == 28 ? 49.5 : sun_bin == 20 ? 50.5 : sun_bin == 21 ? 51.5 : sun_bin == 23 ? 52.5 : sun_bin == 22 ? 53.5 : sun_bin == 18 ? 54.5 : sun_bin == 19 ? 55.5 : sun_bin ==17 ? 56.5 : sun_bin == 16 ? 57.5 : sun_bin == 48 ? 58.5 : sun_bin == 49 ? 59.5 : sun_bin == 51 ? 60.5 : sun_bin == 50 ? 61.5 : sun_bin == 54 ? 62.5 : sun_bin == 55 ? 63.5 : sun_bin == 53 ? 64.5 : sun_bin == 52 ? 65.5 : sun_bin == 60 ? 66.5 : sun_bin == 61 ? 67.5 : sun_bin == 63 ? 68.5 : sun_bin == 62 ? 69.5 : sun_bin == 58 ? 70.5 : sun_bin == 59 ? 71.5 : sun_bin == 57 ? 72.5 : sun_bin == 56 ? 73.5 : sun_bin == 40 ? 74.5 : sun_bin == 41 ? 75.5 : sun_bin == 43 ? 76.5 : sun_bin == 42 ? 77.5 : sun_bin == 46 ? 78.5 : sun_bin == 47 ? 79.5 : sun_bin == 45 ? 80.5 : sun_bin == 44 ? 81.5 : sun_bin == 36 ? 82.5 : sun_bin == 37 ? 83.5 : sun_bin == 39 ? 84.5 : sun_bin == 38 ? 85.5 : sun_bin == 34 ? 86.5 : sun_bin == 35 ? 87.5 : sun_bin == 33 ? 88.5 : sun_bin == 32 ? 89.5 : sun_bin == 96 ? 90.5 : sun_bin == 97 ? 91.5 : sun_bin == 99 ? 92.5 : sun_bin == 98 ? 93.5 : sun_bin == 102 ? 94.5 : sun_bin == 103 ? 95.5 : sun_bin == 101 ? 96.5 : sun_bin == 100 ? 97.5 : sun_bin == 108 ? 98.5 : sun_bin == 109 ? 99.5 : sun_bin == 111 ? 100.5 : sun_bin == 110 ? 101.5 : sun_bin == 106 ? 102.5 : sun_bin == 107 ? 103.5 : sun_bin == 105 ? 104.5 : sun_bin == 104 ? 105.5 : sun_bin == 120 ? 106.5 : sun_bin == 121 ? 107.5 : sun_bin == 123 ? 108.5 : sun_bin == 122 ? 109.5 : sun_bin == 126 ? 110.5 : sun_bin == 127 ? 111.5 : sun_bin == 125 ? 112.5 : sun_bin == 124 ? 113.5 : sun_bin == 116 ? 114.5 : sun_bin == 117 ? 115.5 : sun_bin == 119 ? 116.5 : sun_bin == 118 ? 117.5 : sun_bin == 114 ? 118.5 : sun_bin == 115 ? 119.5 : sun_bin == 113 ? 120.5 : sun_bin == 112 ? 121.5 : sun_bin == 80 ? 122.5 : sun_bin == 81 ? 123.5 : sun_bin == 83 ? 124.5 : sun_bin == 82 ? 125.5 : sun_bin == 86 ? 126.5 : sun_bin == 87 ? 127.5 : sun_bin == 85 ? 128.5 : sun_bin == 84 ? 129.5 : sun_bin == 92 ? 130.5 : sun_bin == 93 ? 131.5 : sun_bin == 95 ? 132.5 : sun_bin == 94 ? 133.5 : sun_bin == 90 ? 134.5 : sun_bin == 91 ? 135.5 : sun_bin == 89 ? 136.5 : sun_bin == 88 ? 137.5 : sun_bin == 72 ? 138.5 : sun_bin == 73 ? 139.5 : sun_bin == 75 ? 140.5 : sun_bin == 74 ? 141.5 : sun_bin == 78 ? 142.5 : sun_bin == 79 ? 143.5 : sun_bin == 77 ? 144.5 : sun_bin == 76 ? 145.5 : sun_bin == 68 ? 146.5 : sun_bin == 69 ? 147.5 : sun_bin == 71 ? 148.5 : sun_bin == 70 ? 149.5 : sun_bin == 66 ? 150.5 : sun_bin == 67 ? 151.5 : sun_bin == 65 ? 152.5 : sun_bin == 64 ? 153.5 : 0)'


# byte 11 (3C)
  magnet_sensor_z_axis: # according to https://www.jarl.org/Japanese/3_Fuji/teleme/jatlm.htm
# according to https://www.jarl.org/Japanese/3_Fuji/teleme/tlm.htm it's Y axis
    if: byte_3c_ascii.substring(0,1) != "*" and byte_3c_ascii.substring(1,2) != "*"
    value: byte_3c_ascii.to_i(16) * 490.196 # in nT

# byte 12 (3D)
  magnet_sensor_x_axis: # according to https://www.jarl.org/Japanese/3_Fuji/teleme/jatlm.htm
# according to https://www.jarl.org/Japanese/3_Fuji/teleme/tlm.htm it's Z axis
    if: byte_3d_ascii.substring(0,1) != "*" and byte_3d_ascii.substring(1,2) != "*"
    value: (byte_3d_ascii.to_i(16) +102) * 490.196 - 50000 # in nT



# byte 13 (4A)
  current_from_solar_cells:
    if: byte_4a_ascii.substring(0,1) != "*" and byte_4a_ascii.substring(1,2) != "*"
    value: byte_4a_ascii.to_i(16) * 0.009804 # in A

# byte 14 (4B)
  battery_charge_and_discharge_current:
    if: byte_4b_ascii.substring(0,1) != "*" and byte_4b_ascii.substring(1,2) != "*"
    value: -(2 - byte_4b_ascii.to_i(16) * 0.0196) # in A

# byte 15 (4C)
  battery_voltage:
    if: byte_4c_ascii.substring(0,1) != "*" and byte_4c_ascii.substring(1,2) != "*"
    value: byte_4c_ascii.to_i(16) * 0.10761 # in V

# byte 16 (4D)
  battery_intermediate_terminal_voltage:
    if: byte_4d_ascii.substring(0,1) != "*" and byte_4d_ascii.substring(1,2) != "*"
    value: byte_4d_ascii.to_i(16) *0.04817 # in V



# byte 17 (5A)
  bus_voltage:
    if: byte_5a_ascii.substring(0,1) != "*" and byte_5a_ascii.substring(1,2) != "*"
    value: byte_5a_ascii.to_i(16) *0.09804 # in V

# byte 18 (5B)
  jta_tx_power:
    if: byte_5b_ascii.substring(0,1) != "*" and byte_5b_ascii.substring(1,2) != "*"
    value: byte_5b_ascii.to_i(16) * 6.4997 - 98.0863 # in mW

# byte 19 (5C)
  structure_temperature_1:
    if: byte_5c_ascii.substring(0,1) != "*" and byte_5c_ascii.substring(1,2) != "*"
    value: byte_5c_ascii.to_i(16) * (- 0.388375) + 81.883 # in °C

# byte 20 (5D)
  structure_temperature_2:
    if: byte_5d_ascii.substring(0,1) != "*" and byte_5d_ascii.substring(1,2) != "*"
    value: byte_5d_ascii.to_i(16) * (- 0.388375) + 81.883 # in °C



# byte 21 (6A)
  structure_temperature_3:
    if: byte_6a_ascii.substring(0,1) != "*" and byte_6a_ascii.substring(1,2) != "*"
    value: byte_6a_ascii.to_i(16) * (- 0.388375) + 81.883 # in °C

# byte 22 (6B)
  structure_temperature_4:
    if: byte_6b_ascii.substring(0,1) != "*" and byte_6b_ascii.substring(1,2) != "*"
    value: byte_6b_ascii.to_i(16) * (- 0.388375) + 81.883 # in °C

# byte 23 (6C)
  battery_temperature:
    if: byte_6c_ascii.substring(0,1) != "*" and byte_6c_ascii.substring(1,2) != "*"
    value: byte_6c_ascii.to_i(16) * (- 0.388375) + 81.883 # in °C



  beacon:
    value: header_hihi + " " + byte_1a_ascii + " " + byte_1b_ascii + " " + byte_1c_ascii + " " + byte_1d_ascii + " " + byte_2a_ascii + " " + byte_2b_ascii + " " + byte_2c_ascii + " " + byte_2d_ascii + " " + byte_3a_ascii + " " + byte_3b_ascii + " " + byte_3c_ascii + " " + byte_3d_ascii + " " + byte_4a_ascii + " " + byte_4b_ascii + " " + byte_4c_ascii + " " + byte_4d_ascii + " " + byte_5a_ascii + " " + byte_5b_ascii + " " + byte_5c_ascii + " " + byte_5d_ascii + " " + byte_6a_ascii + " " + byte_6b_ascii + " " + byte_6c_ascii
