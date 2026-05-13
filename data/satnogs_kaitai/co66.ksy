---
meta:
  id: co66
  title: CO-66 CW decoder
  endian: be
doc-ref: "https://web.archive.org/web/20100215214032/http://cubesat.aero.cst.nihon-u.ac.jp/image/telemetry/CW_e/CW_Telemetry_Format_For_SEEDS_English.pdf"
# 2025-04-05, DL7NDR
doc: |
  :field whole_beacon_ascii: mode.mode_check.whole_beacon_ascii
  :field beacon_mode: mode.mode_check.beacon_mode
  :field satellite_time: mode.mode_check.satellite_time
  :field batteries_voltage: mode.mode_check.batteries_voltage
  :field bus_voltage: mode.mode_check.bus_voltage
  :field solar_cell_1_current: mode.mode_check.solar_cell_1_current
  :field solar_cell_2_current: mode.mode_check.solar_cell_2_current
  :field solar_cell_3_current: mode.mode_check.solar_cell_3_current
  :field solar_cell_4_current: mode.mode_check.solar_cell_4_current
  :field solar_cell_5_current: mode.mode_check.solar_cell_5_current
  :field solar_cell_6_current: mode.mode_check.solar_cell_6_current
  :field battery_1_temperature: mode.mode_check.battery_1_temperature
  :field battery_2_temperature: mode.mode_check.battery_2_temperature
  :field transmitter_temperature: mode.mode_check.transmitter_temperature
  :field receiver_temperature: mode.mode_check.receiver_temperature
  :field cw_transmission_interval: mode.mode_check.cw_transmission_interval
  :field status_of_switch_1: mode.mode_check.status_of_switch_1
  :field status_of_switch_2: mode.mode_check.status_of_switch_2
  :field status_of_switch_3: mode.mode_check.status_of_switch_3
  :field mpu_reset_times_eps: mode.mode_check.mpu_reset_times_eps
  :field mpu_reset_times_fmr: mode.mode_check.mpu_reset_times_fmr
  :field mpu_reset_times_cdh: mode.mode_check.mpu_reset_times_cdh
  :field mpu_reset_times_cw: mode.mode_check.mpu_reset_times_cw
  :field cw_transmission_count: mode.mode_check.cw_transmission_count
  :field uplink_count: mode.mode_check.uplink_count
  :field command_status: mode.mode_check.command_status
  :field forced_no_charge_mode: mode.mode_check.forced_no_charge_mode
  :field mode_of_shunt_circuit: mode.mode_check.mode_of_shunt_circuit
  :field status_of_shunt_circuit: mode.mode_check.status_of_shunt_circuit
  :field address_block: mode.mode_check.address_block
  :field necessary_for_lengthcheck: mode.mode_check.necessary_for_lengthcheck

seq:
  - id: preamble
    type: str
    size: 5
    encoding: ASCII
    valid: '"seeds"' # 7365656473 (SatNOGS CW decoder uses upper case letters.)

  - id: mode
    type: mode_t

types:
  mode_t:
    seq:
      - id: mode_check
        type:
          switch-on: check
          cases:
            0x30: zero
            0x31: one
            0x33: three
            0x34: four
            0x36: six
            _: discard

    instances:
      check:
        type: u1


  zero:
   seq:
     - id: whole_beacon_ascii
       type: str
       encoding: utf-8
       size: 6

     - id: discard
       type: str
       encoding: utf-8 # if un-encodeable, whole frame will be discarded
       size-eos: true # accepts zero length

   instances:
     beacon_mode:
       value: '0'
     batteries_voltage:
       if: whole_beacon_ascii.substring(0,1) != "*" and whole_beacon_ascii.substring(1,2) != "*" and whole_beacon_ascii.substring(2,3) != "*"
      # discards this value, if at least one part is an asterisk (*)
       value: 5.0 * whole_beacon_ascii.substring(0,3).to_i(16) / 4096
     bus_voltage:
       if: whole_beacon_ascii.substring(3,4) != "*" and whole_beacon_ascii.substring(4,5) != "*" and whole_beacon_ascii.substring(5,6) != "*"
       value: 5.0 * whole_beacon_ascii.substring(3,6).to_i(16) / 4096
     necessary_for_lengthcheck:
       if: discard.length != 0 # if so, whole frame will be discarded
       value: discard.to_i / 0 # produces 'ZeroDivisionError' and stops parsing



  one:
   seq:
     - id: whole_beacon_ascii
       type: str
       encoding: utf-8
       size: 45

     - id: discard
       type: str
       encoding: utf-8
       size-eos: true

   instances:
     beacon_mode:
       value: '1'
     satellite_time:
       if: whole_beacon_ascii.substring(0,1) != "*" and whole_beacon_ascii.substring(1,2) != "*" and whole_beacon_ascii.substring(2,3) != "*" and whole_beacon_ascii.substring(3,4) != "*" and whole_beacon_ascii.substring(4,5) != "*" and whole_beacon_ascii.substring(5,6) != "*" and whole_beacon_ascii.substring(6,7) != "*" and whole_beacon_ascii.substring(7,8) != "*"
       value: whole_beacon_ascii.substring(0,8).to_i(16) / 2
     batteries_voltage:
       if: whole_beacon_ascii.substring(8,9) != "*" and whole_beacon_ascii.substring(9,10) != "*" and whole_beacon_ascii.substring(10,11) != "*"
       value: 5.0 * whole_beacon_ascii.substring(8,11).to_i(16) / 4096
     bus_voltage:
       if: whole_beacon_ascii.substring(11,12) != "*" and whole_beacon_ascii.substring(12,13) != "*" and whole_beacon_ascii.substring(13,14) != "*"
       value: 5.0 * whole_beacon_ascii.substring(11,14).to_i(16) / 4096
     solar_cell_1_current:
       if: whole_beacon_ascii.substring(14,15) != "*" and whole_beacon_ascii.substring(15,16) != "*" and whole_beacon_ascii.substring(16,17) != "*"
       value: 5.0 * whole_beacon_ascii.substring(14,17).to_i(16) / 4096 * 90.90909
     solar_cell_2_current:
       if: whole_beacon_ascii.substring(17,18) != "*" and whole_beacon_ascii.substring(18,19) != "*" and whole_beacon_ascii.substring(19,20) != "*"
       value: 5.0 * whole_beacon_ascii.substring(17,20).to_i(16) / 4096 * 90.90909
     solar_cell_3_current:
       if: whole_beacon_ascii.substring(20,21) != "*" and whole_beacon_ascii.substring(21,22) != "*" and whole_beacon_ascii.substring(22,23) != "*"
       value: 5.0 * whole_beacon_ascii.substring(20,23).to_i(16) / 4096 * 90.90909
     solar_cell_4_current:
       if: whole_beacon_ascii.substring(23,24) != "*" and whole_beacon_ascii.substring(24,25) != "*" and whole_beacon_ascii.substring(25,26) != "*"
       value: 5.0 * whole_beacon_ascii.substring(23,26).to_i(16) / 4096 * 90.90909
     solar_cell_5_current:
       if: whole_beacon_ascii.substring(26,27) != "*" and whole_beacon_ascii.substring(27,28) != "*" and whole_beacon_ascii.substring(28,29) != "*"
       value: 5.0 * whole_beacon_ascii.substring(26,29).to_i(16) / 4096 * 90.90909
     solar_cell_6_current:
       if: whole_beacon_ascii.substring(29,30) != "*" and whole_beacon_ascii.substring(30,31) != "*" and whole_beacon_ascii.substring(31,32) != "*"
       value: 5.0 * whole_beacon_ascii.substring(29,32).to_i(16) / 4096 * 90.90909
     battery_1_temperature:
       if: whole_beacon_ascii.substring(32,33) != "*" and whole_beacon_ascii.substring(33,34) != "*" and whole_beacon_ascii.substring(34,35) != "*"
       value: 0.15797 * ((5.0 * whole_beacon_ascii.substring(32,35).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(32,35).to_i(16) / 4096)) - 39.553 * (5.0 * whole_beacon_ascii.substring(32,35).to_i(16) / 4096) + 129.59
     battery_2_temperature:
       if: whole_beacon_ascii.substring(35,36) != "*" and whole_beacon_ascii.substring(36,37) != "*" and whole_beacon_ascii.substring(37,38) != "*"
       value: 0.18923 * ((5.0 * whole_beacon_ascii.substring(35,38).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(35,38).to_i(16) / 4096)) - 39.27 * (5.0 * whole_beacon_ascii.substring(35,38).to_i(16) / 4096) + 128.33
     transmitter_temperature:
       if: whole_beacon_ascii.substring(38,39) != "*" and whole_beacon_ascii.substring(39,40) != "*" and whole_beacon_ascii.substring(40,41) != "*"
       value: (-0.38082) * ((5.0 * whole_beacon_ascii.substring(38,41).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(38,41).to_i(16) / 4096)) - 36.125 * (5.0 * whole_beacon_ascii.substring(38,41).to_i(16) / 4096) + 121.31
     receiver_temperature:
       if: whole_beacon_ascii.substring(41,42) != "*" and whole_beacon_ascii.substring(42,43) != "*" and whole_beacon_ascii.substring(43,44) != "*"
       value: (-0.062626) * ((5.0 * whole_beacon_ascii.substring(41,44).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(41,44).to_i(16) / 4096)) - 38.305 * (5.0 * whole_beacon_ascii.substring(41,44).to_i(16) / 4096) + 126.89
     cw_transmission_interval:
       if: whole_beacon_ascii.substring(44,45) != "*"
       value: whole_beacon_ascii.substring(44,45).to_i(16) * 3
     necessary_for_lengthcheck:
       if: discard.length != 0
       value: discard.to_i / 0


  three:
   seq:
     - id: whole_beacon_ascii
       type: str
       encoding: utf-8
       size: 48

     - id: discard
       type: str
       encoding: utf-8
       size-eos: true

   instances:
     beacon_mode:
       value: '3'
     satellite_time:
       if: whole_beacon_ascii.substring(0,1) != "*" and whole_beacon_ascii.substring(1,2) != "*" and whole_beacon_ascii.substring(2,3) != "*" and whole_beacon_ascii.substring(3,4) != "*" and whole_beacon_ascii.substring(4,5) != "*" and whole_beacon_ascii.substring(5,6) != "*" and whole_beacon_ascii.substring(6,7) != "*" and whole_beacon_ascii.substring(7,8) != "*"
       value: whole_beacon_ascii.substring(0,8).to_i(16) / 2
     address_block:
       if: whole_beacon_ascii.substring(8,9) != "*" and whole_beacon_ascii.substring(9,10) != "*" and whole_beacon_ascii.substring(10,11) != "*" and whole_beacon_ascii.substring(11,12) != "*"
       value: whole_beacon_ascii.substring(8,12).to_i(16)
     solar_cell_1_current:
       if: whole_beacon_ascii.substring(12,13) != "*" and whole_beacon_ascii.substring(13,14) != "*" and whole_beacon_ascii.substring(14,115) != "*"
       value: 5.0 * whole_beacon_ascii.substring(12,15).to_i(16) / 4096 * 90.90909
     solar_cell_2_current:
       if: whole_beacon_ascii.substring(15,16) != "*" and whole_beacon_ascii.substring(16,17) != "*" and whole_beacon_ascii.substring(17,18) != "*"
       value: 5.0 * whole_beacon_ascii.substring(15,18).to_i(16) / 4096 * 90.90909
     solar_cell_3_current:
       if: whole_beacon_ascii.substring(18,19) != "*" and whole_beacon_ascii.substring(19,20) != "*" and whole_beacon_ascii.substring(20,21) != "*"
       value: 5.0 * whole_beacon_ascii.substring(18,21).to_i(16) / 4096 * 90.90909
     solar_cell_4_current:
       if: whole_beacon_ascii.substring(21,22) != "*" and whole_beacon_ascii.substring(22,23) != "*" and whole_beacon_ascii.substring(23,24) != "*"
       value: 5.0 * whole_beacon_ascii.substring(21,24).to_i(16) / 4096 * 90.90909
     solar_cell_5_current:
       if: whole_beacon_ascii.substring(24,25) != "*" and whole_beacon_ascii.substring(25,26) != "*" and whole_beacon_ascii.substring(26,27) != "*"
       value: 5.0 * whole_beacon_ascii.substring(24,27).to_i(16) / 4096 * 90.90909
     solar_cell_6_current:
       if: whole_beacon_ascii.substring(27,28) != "*" and whole_beacon_ascii.substring(28,29) != "*" and whole_beacon_ascii.substring(29,30) != "*"
       value: 5.0 * whole_beacon_ascii.substring(27,30).to_i(16) / 4096 * 90.90909
     battery_1_temperature:
       if: whole_beacon_ascii.substring(30,31) != "*" and whole_beacon_ascii.substring(31,32) != "*" and whole_beacon_ascii.substring(32,33) != "*"
       value: 0.15797 * ((5.0 * whole_beacon_ascii.substring(30,33).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(30,33).to_i(16) / 4096)) - 39.553 * (5.0 * whole_beacon_ascii.substring(30,33).to_i(16) / 4096) + 129.59
     battery_2_temperature:
       if: whole_beacon_ascii.substring(33,34) != "*" and whole_beacon_ascii.substring(34,35) != "*" and whole_beacon_ascii.substring(35,36) != "*"
       value: 0.18923 * ((5.0 * whole_beacon_ascii.substring(33,36).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(33,36).to_i(16) / 4096)) - 39.27 * (5.0 * whole_beacon_ascii.substring(33,36).to_i(16) / 4096) + 128.33
     transmitter_temperature:
       if: whole_beacon_ascii.substring(36,37) != "*" and whole_beacon_ascii.substring(37,38) != "*" and whole_beacon_ascii.substring(38,39) != "*"
       value: (-0.38082) * ((5.0 * whole_beacon_ascii.substring(36,39).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(36,39).to_i(16) / 4096)) - 36.125 * (5.0 * whole_beacon_ascii.substring(36,39).to_i(16) / 4096) + 121.31
     receiver_temperature:
       if: whole_beacon_ascii.substring(39,40) != "*" and whole_beacon_ascii.substring(40,41) != "*" and whole_beacon_ascii.substring(41,42) != "*"
       value: (-0.062626) * ((5.0 * whole_beacon_ascii.substring(39,42).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(39,42).to_i(16) / 4096)) - 38.305 * (5.0 * whole_beacon_ascii.substring(39,42).to_i(16) / 4096) + 126.89
     batteries_voltage:
       if: whole_beacon_ascii.substring(42,43) != "*" and whole_beacon_ascii.substring(43,44) != "*" and whole_beacon_ascii.substring(44,45) != "*"
       value: 5.0 * whole_beacon_ascii.substring(42,45).to_i(16) / 4096
     bus_voltage:
       if: whole_beacon_ascii.substring(45,46) != "*" and whole_beacon_ascii.substring(46,47) != "*" and whole_beacon_ascii.substring(47,48) != "*"
       value: 5.0 * whole_beacon_ascii.substring(45,48).to_i(16) / 4096
     necessary_for_lengthcheck:
       if: discard.length != 0
       value: discard.to_i / 0



  four:
   seq:
     - id: whole_beacon_ascii
       type: str
       encoding: utf-8
       size: 72

     - id: discard
       type: str
       encoding: utf-8
       size-eos: true

   instances:
     beacon_mode:
       value: '4'
     satellite_time:
       if: whole_beacon_ascii.substring(0,1) != "*" and whole_beacon_ascii.substring(1,2) != "*" and whole_beacon_ascii.substring(2,3) != "*" and whole_beacon_ascii.substring(3,4) != "*" and whole_beacon_ascii.substring(4,5) != "*" and whole_beacon_ascii.substring(5,6) != "*" and whole_beacon_ascii.substring(6,7) != "*" and whole_beacon_ascii.substring(7,8) != "*"
       value: whole_beacon_ascii.substring(0,8).to_i(16) / 2
     batteries_voltage:
       if: whole_beacon_ascii.substring(8,9) != "*" and whole_beacon_ascii.substring(9,10) != "*" and whole_beacon_ascii.substring(10,11) != "*"
       value: 5.0 * whole_beacon_ascii.substring(8,11).to_i(16) / 4096
     bus_voltage:
       if: whole_beacon_ascii.substring(11,12) != "*" and whole_beacon_ascii.substring(12,13) != "*" and whole_beacon_ascii.substring(13,14) != "*"
       value: 5.0 * whole_beacon_ascii.substring(11,14).to_i(16) / 4096
     solar_cell_1_current:
       if: whole_beacon_ascii.substring(14,15) != "*" and whole_beacon_ascii.substring(15,16) != "*" and whole_beacon_ascii.substring(16,17) != "*"
       value: 5.0 * whole_beacon_ascii.substring(14,17).to_i(16) / 4096 * 90.90909
     solar_cell_2_current:
       if: whole_beacon_ascii.substring(17,18) != "*" and whole_beacon_ascii.substring(18,19) != "*" and whole_beacon_ascii.substring(19,20) != "*"
       value: 5.0 * whole_beacon_ascii.substring(17,20).to_i(16) / 4096 * 90.90909
     solar_cell_3_current:
       if: whole_beacon_ascii.substring(20,21) != "*" and whole_beacon_ascii.substring(21,22) != "*" and whole_beacon_ascii.substring(22,23) != "*"
       value: 5.0 * whole_beacon_ascii.substring(20,23).to_i(16) / 4096 * 90.90909
     solar_cell_4_current:
       if: whole_beacon_ascii.substring(23,24) != "*" and whole_beacon_ascii.substring(24,25) != "*" and whole_beacon_ascii.substring(25,26) != "*"
       value: 5.0 * whole_beacon_ascii.substring(23,26).to_i(16) / 4096 * 90.90909
     solar_cell_5_current:
       if: whole_beacon_ascii.substring(26,27) != "*" and whole_beacon_ascii.substring(27,28) != "*" and whole_beacon_ascii.substring(28,29) != "*"
       value: 5.0 * whole_beacon_ascii.substring(26,29).to_i(16) / 4096 * 90.90909
     solar_cell_6_current:
       if: whole_beacon_ascii.substring(29,30) != "*" and whole_beacon_ascii.substring(30,31) != "*" and whole_beacon_ascii.substring(31,32) != "*"
       value: 5.0 * whole_beacon_ascii.substring(29,32).to_i(16) / 4096 * 90.90909
     battery_1_temperature:
       if: whole_beacon_ascii.substring(32,33) != "*" and whole_beacon_ascii.substring(33,34) != "*" and whole_beacon_ascii.substring(34,35) != "*"
       value: 0.15797 * ((5.0 * whole_beacon_ascii.substring(32,35).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(32,35).to_i(16) / 4096)) - 39.553 * (5.0 * whole_beacon_ascii.substring(32,35).to_i(16) / 4096) + 129.59
     battery_2_temperature:
       if: whole_beacon_ascii.substring(35,36) != "*" and whole_beacon_ascii.substring(36,37) != "*" and whole_beacon_ascii.substring(37,38) != "*"
       value: 0.18923 * ((5.0 * whole_beacon_ascii.substring(35,38).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(35,38).to_i(16) / 4096)) - 39.27 * (5.0 * whole_beacon_ascii.substring(35,38).to_i(16) / 4096) + 128.33
     transmitter_temperature:
       if: whole_beacon_ascii.substring(38,39) != "*" and whole_beacon_ascii.substring(39,40) != "*" and whole_beacon_ascii.substring(40,41) != "*"
       value: (-0.38082) * ((5.0 * whole_beacon_ascii.substring(38,41).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(38,41).to_i(16) / 4096)) - 36.125 * (5.0 * whole_beacon_ascii.substring(38,41).to_i(16) / 4096) + 121.31
     receiver_temperature:
       if: whole_beacon_ascii.substring(41,42) != "*" and whole_beacon_ascii.substring(42,43) != "*" and whole_beacon_ascii.substring(43,44) != "*"
       value: (-0.062626) * ((5.0 * whole_beacon_ascii.substring(41,44).to_i(16) / 4096) * (5.0 * whole_beacon_ascii.substring(41,44).to_i(16) / 4096)) - 38.305 * (5.0 * whole_beacon_ascii.substring(41,44).to_i(16) / 4096) + 126.89
     cw_transmission_interval:
       if: whole_beacon_ascii.substring(44,45) != "*"
       value: whole_beacon_ascii.substring(44,45).to_i(16) * 3
     status_of_switch_1:
       if: whole_beacon_ascii.substring(45,46) != "*"
       value: whole_beacon_ascii.substring(45,46).to_i(16) & 0b1
     status_of_switch_2:
       if: whole_beacon_ascii.substring(45,46) != "*"
       value: (whole_beacon_ascii.substring(45,46).to_i(16) >> 1) & 0b1
     status_of_switch_3:
       if: whole_beacon_ascii.substring(45,46) != "*"
       value: (whole_beacon_ascii.substring(45,46).to_i(16) >> 2) & 0b1
     mpu_reset_times_eps:
       if: whole_beacon_ascii.substring(46,47) != "*" and whole_beacon_ascii.substring(47,48) != "*" and whole_beacon_ascii.substring(48,49) != "*" and whole_beacon_ascii.substring(49,50) != "*"
       value: whole_beacon_ascii.substring(46,50).to_i(16)
     mpu_reset_times_fmr:
       if: whole_beacon_ascii.substring(50,51) != "*" and whole_beacon_ascii.substring(51,52) != "*" and whole_beacon_ascii.substring(52,53) != "*" and whole_beacon_ascii.substring(53,54) != "*"
       value: whole_beacon_ascii.substring(50,54).to_i(16)
     mpu_reset_times_cdh:
       if: whole_beacon_ascii.substring(54,55) != "*" and whole_beacon_ascii.substring(55,56) != "*" and whole_beacon_ascii.substring(56,57) != "*" and whole_beacon_ascii.substring(57,58) != "*"
       value: whole_beacon_ascii.substring(54,58).to_i(16)
     mpu_reset_times_cw:
       if: whole_beacon_ascii.substring(58,59) != "*" and whole_beacon_ascii.substring(59,60) != "*" and whole_beacon_ascii.substring(60,61) != "*" and whole_beacon_ascii.substring(61,62) != "*"
       value: whole_beacon_ascii.substring(58,62).to_i(16)
     cw_transmission_count:
       if: whole_beacon_ascii.substring(62,63) != "*" and whole_beacon_ascii.substring(63,64) != "*" and whole_beacon_ascii.substring(64,65) != "*" and whole_beacon_ascii.substring(65,66) != "*"
       value: whole_beacon_ascii.substring(62,66).to_i(16)
     uplink_count:
       if: whole_beacon_ascii.substring(66,67) != "*" and whole_beacon_ascii.substring(67,68) != "*"
       value: whole_beacon_ascii.substring(66,68).to_i(16)
     command_status:
       if: whole_beacon_ascii.substring(68,69) != "*" and whole_beacon_ascii.substring(69,70) != "*"
       value: whole_beacon_ascii.substring(68,70).to_i(16)
     forced_no_charge_mode:
       if: whole_beacon_ascii.substring(70,71) != "*"
       value: whole_beacon_ascii.substring(70,71).to_i(16) >> 3
     mode_of_shunt_circuit:
       if: whole_beacon_ascii.substring(71,72) != "*"
       value: whole_beacon_ascii.substring(71,72).to_i(16) & 0b11
     status_of_shunt_circuit:
       if: whole_beacon_ascii.substring(71,72) != "*"
       value: (whole_beacon_ascii.substring(71,72).to_i(16) >> 2) & 0b1
     necessary_for_lengthcheck:
       if: discard.length != 0
       value: discard.to_i / 0


  six:
   seq:
     - id: whole_beacon_ascii
       type: str
       encoding: utf-8
       size: 3

     - id: discard
       type: str
       encoding: utf-8
       size-eos: true

   instances:
     beacon_mode:
       value: '6'
     batteries_voltage:
       if: whole_beacon_ascii.substring(0,1) != "*" and whole_beacon_ascii.substring(1,2) != "*" and whole_beacon_ascii.substring(2,3) != "*"
       value: 5.0 * whole_beacon_ascii.substring(0,3).to_i(16) / 4096
     necessary_for_lengthcheck:
       if: discard.length != 0
       value: discard.to_i / 0



  discard:
   seq:
     - id: discard
       type: b1

   instances:
     necessary_for_lengthcheck:
       value: discard.to_i / 0
