---
meta:
  id: lasarsat
  title: LASARSAT FSK and CW Beacon and Digi Decoder
  endian: be
doc-ref: "https://lasar.info/lasarsat"
# Based on Veronika satellite decoder, including contribution by DL7NDR to improve experience with CW and digipeated messages
doc: |
  :field uptime_total: id1.id2.uptime_total
  :field reset_number: id1.id2.reset_number
  :field temp_mcu: id1.id2.temp_mcu
  :field temp_pa: id1.id2.temp_pa
  :field cw_beacon: id1.id2.cw_beacon

  :field digi_dest_callsign: id1.id2.id3.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field digi_src_callsign: id1.id2.id3.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field digi_src_ssid: id1.id2.id3.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field digi_dest_ssid: id1.id2.id3.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: id1.id2.id3.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: id1.id2.id3.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: id1.id2.id3.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field digi_ctl: id1.id2.id3.ax25_frame.ax25_header.ctl
  :field digi_pid: id1.id2.id3.ax25_frame.ax25_header.pid
  :field digi_message: id1.id2.id3.ax25_frame.ax25_info.digi_message

  :field dest_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field obc_reset_cnt: id1.id2.id3.id4.ax25_frame.obc_reset_cnt
  :field obc_uptime: id1.id2.id3.id4.ax25_frame.obc_uptime
  :field obc_uptime_tot: id1.id2.id3.id4.ax25_frame.obc_uptime_tot
  :field obc_temp_mcu: id1.id2.id3.id4.ax25_frame.obc_temp_mcu
  :field obc_freemem: id1.id2.id3.id4.ax25_frame.obc_freemem

  :field dest_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field psu_reset_cnt: id1.id2.id3.id4.ax25_frame.psu_reset_cnt
  :field psu_uptime: id1.id2.id3.id4.ax25_frame.psu_uptime
  :field psu_uptime_tot: id1.id2.id3.id4.ax25_frame.psu_uptime_tot
  :field psu_battery: id1.id2.id3.id4.ax25_frame.psu_battery
  :field psu_temp_sys: id1.id2.id3.id4.ax25_frame.psu_temp_sys
  :field psu_temp_bat: id1.id2.id3.id4.ax25_frame.psu_temp_bat
  :field psu_cur_in: id1.id2.id3.id4.ax25_frame.psu_cur_in
  :field psu_cur_out: id1.id2.id3.id4.ax25_frame.psu_cur_out
  :field psu_ch_state_num: id1.id2.id3.id4.ax25_frame.psu_ch_state_num
  :field psu_ch0_state: id1.id2.id3.id4.ax25_frame.psu_ch0_state
  :field psu_ch1_state: id1.id2.id3.id4.ax25_frame.psu_ch1_state
  :field psu_ch2_state: id1.id2.id3.id4.ax25_frame.psu_ch2_state
  :field psu_ch3_state: id1.id2.id3.id4.ax25_frame.psu_ch3_state
  :field psu_ch4_state: id1.id2.id3.id4.ax25_frame.psu_ch4_state
  :field psu_ch5_state: id1.id2.id3.id4.ax25_frame.psu_ch5_state
  :field psu_ch6_state: id1.id2.id3.id4.ax25_frame.psu_ch6_state
  :field psu_sys_state: id1.id2.id3.id4.ax25_frame.psu_sys_state
  :field psu_gnd_wdt: id1.id2.id3.id4.ax25_frame.psu_gnd_wdt

  :field dest_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field mgs_temp_int_mag: id1.id2.id3.id4.ax25_frame.mgs_temp_int_mag
  :field mgs_temp_int_gyr: id1.id2.id3.id4.ax25_frame.mgs_temp_int_gyr
  :field mgs_int_mag_x: id1.id2.id3.id4.ax25_frame.mgs_int_mag_x
  :field mgs_int_mag_y: id1.id2.id3.id4.ax25_frame.mgs_int_mag_y
  :field mgs_int_mag_z: id1.id2.id3.id4.ax25_frame.mgs_int_mag_z
  :field mgs_int_gyr_x: id1.id2.id3.id4.ax25_frame.mgs_int_gyr_x
  :field mgs_int_gyr_y: id1.id2.id3.id4.ax25_frame.mgs_int_gyr_y
  :field mgs_int_gyr_z: id1.id2.id3.id4.ax25_frame.mgs_int_gyr_z

  :field dest_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.id3.id4.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field sol_temp_zp: id1.id2.id3.id4.ax25_frame.sol_temp_zp
  :field sol_temp_xp: id1.id2.id3.id4.ax25_frame.sol_temp_xp
  :field sol_temp_yp: id1.id2.id3.id4.ax25_frame.sol_temp_yp
  :field sol_temp_zn: id1.id2.id3.id4.ax25_frame.sol_temp_zn
  :field sol_temp_xn: id1.id2.id3.id4.ax25_frame.sol_temp_xn
  :field sol_temp_yn: id1.id2.id3.id4.ax25_frame.sol_temp_yn
  :field sol_diode_zp: id1.id2.id3.id4.ax25_frame.sol_diode_zp
  :field sol_diode_xp: id1.id2.id3.id4.ax25_frame.sol_diode_xp
  :field sol_diode_yp: id1.id2.id3.id4.ax25_frame.sol_diode_yp
  :field sol_diode_zn: id1.id2.id3.id4.ax25_frame.sol_diode_zn
  :field sol_diode_xn: id1.id2.id3.id4.ax25_frame.sol_diode_xn
  :field sol_diode_yn: id1.id2.id3.id4.ax25_frame.sol_diode_yn

  :field dos_mode: id1.id2.id3.id4.ax25_frame.dos_mode
  :field dos_gyr_x: id1.id2.id3.id4.ax25_frame.dos_gyr_x
  :field dos_gyr_y: id1.id2.id3.id4.ax25_frame.dos_gyr_y
  :field dos_gyr_z: id1.id2.id3.id4.ax25_frame.dos_gyr_z
  :field dos_mag_x: id1.id2.id3.id4.ax25_frame.dos_mag_x
  :field dos_mag_y: id1.id2.id3.id4.ax25_frame.dos_mag_y
  :field dos_mag_z: id1.id2.id3.id4.ax25_frame.dos_mag_z
  :field dos_plasma: id1.id2.id3.id4.ax25_frame.dos_plasma
  :field dos_phd: id1.id2.id3.id4.ax25_frame.dos_phd
  :field dos_dozi: id1.id2.id3.id4.ax25_frame.dos_dozi
  :field dos_gyr_t: id1.id2.id3.id4.ax25_frame.dos_gyr_t
  :field dos_mag_t: id1.id2.id3.id4.ax25_frame.dos_mag_t
  :field dos_lppa: id1.id2.id3.id4.ax25_frame.dos_lppa
  :field dos_bus_cur: id1.id2.id3.id4.ax25_frame.dos_bus_cur
  :field dos_bus_vol: id1.id2.id3.id4.ax25_frame.dos_bus_vol
  :field dos_uptime: id1.id2.id3.id4.ax25_frame.dos_uptime

  :field nav_week: id1.id2.id3.id4.ax25_frame.nav_week
  :field nav_time: id1.id2.id3.id4.ax25_frame.nav_time
  :field nav_pos_x: id1.id2.id3.id4.ax25_frame.nav_pos_x
  :field nav_pos_y: id1.id2.id3.id4.ax25_frame.nav_pos_y
  :field nav_pos_z: id1.id2.id3.id4.ax25_frame.nav_pos_z
  :field nav_vel_x: id1.id2.id3.id4.ax25_frame.nav_vel_x
  :field nav_vel_y: id1.id2.id3.id4.ax25_frame.nav_vel_y
  :field nav_vel_z: id1.id2.id3.id4.ax25_frame.nav_vel_z
  :field nav_sats: id1.id2.id3.id4.ax25_frame.nav_sats
  :field nav_dop: id1.id2.id3.id4.ax25_frame.nav_dop
  :field nav_ant_cur: id1.id2.id3.id4.ax25_frame.nav_ant_cur
  :field nav_volt: id1.id2.id3.id4.ax25_frame.nav_volt
  :field nav_max_snr: id1.id2.id3.id4.ax25_frame.nav_max_snr

  :field dest_callsign: id1.id2.id3.id4.id5.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.id3.id4.id5.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field uhf_uptime: id1.id2.id3.id4.id5.ax25_frame.uhf_uptime
  :field uhf_uptime_tot: id1.id2.id3.id4.id5.ax25_frame.uhf_uptime_tot
  :field uhf_reset_cnt: id1.id2.id3.id4.id5.ax25_frame.uhf_reset_cnt
  :field uhf_rf_reset_cnt: id1.id2.id3.id4.id5.ax25_frame.uhf_rf_reset_cnt
  :field uhf_trx_temp: id1.id2.id3.id4.id5.ax25_frame.uhf_trx_temp
  :field uhf_rf_temp: id1.id2.id3.id4.id5.ax25_frame.uhf_rf_temp
  :field uhf_pa_temp: id1.id2.id3.id4.id5.ax25_frame.uhf_pa_temp
  :field uhf_digipeater_cnt: id1.id2.id3.id4.id5.ax25_frame.uhf_digipeater_cnt
  :field uhf_last_digipeater: id1.id2.id3.id4.id5.ax25_frame.uhf_last_digipeater
  :field uhf_rx_cnt: id1.id2.id3.id4.id5.ax25_frame.uhf_rx_cnt
  :field uhf_tx_cnt: id1.id2.id3.id4.id5.ax25_frame.uhf_tx_cnt
  :field uhf_act_rssi_raw: id1.id2.id3.id4.id5.ax25_frame.uhf_act_rssi_raw
  :field uhf_dcd_rssi_raw: id1.id2.id3.id4.id5.ax25_frame.uhf_dcd_rssi_raw

  :field dest_callsign: id1.id2.id3.id4.id5.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.id3.id4.id5.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field vhf_uptime: id1.id2.id3.id4.id5.ax25_frame.vhf_uptime
  :field vhf_uptime_tot: id1.id2.id3.id4.id5.ax25_frame.vhf_uptime_tot
  :field vhf_reset_cnt: id1.id2.id3.id4.id5.ax25_frame.vhf_reset_cnt
  :field vhf_rf_reset_cnt: id1.id2.id3.id4.id5.ax25_frame.vhf_rf_reset_cnt
  :field vhf_trx_temp: id1.id2.id3.id4.id5.ax25_frame.vhf_trx_temp
  :field vhf_rf_temp: id1.id2.id3.id4.id5.ax25_frame.vhf_rf_temp
  :field vhf_pa_temp: id1.id2.id3.id4.id5.ax25_frame.vhf_pa_temp
  :field vhf_digipeater_cnt: id1.id2.id3.id4.id5.ax25_frame.vhf_digipeater_cnt
  :field vhf_last_digipeater: id1.id2.id3.id4.id5.ax25_frame.vhf_last_digipeater
  :field vhf_rx_cnt: id1.id2.id3.id4.id5.ax25_frame.vhf_rx_cnt
  :field vhf_tx_cnt: id1.id2.id3.id4.id5.ax25_frame.vhf_tx_cnt
  :field vhf_act_rssi_raw: id1.id2.id3.id4.id5.ax25_frame.vhf_act_rssi_raw
  :field vhf_dcd_rssi_raw: id1.id2.id3.id4.id5.ax25_frame.vhf_dcd_rssi_raw

  :field dest_callsign: id1.id2.id3.id4.id5.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.id3.id4.id5.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field lasarsat_message: id1.id2.id3.id4.id5.ax25_frame.lasarsat_message

seq:
  - id: id1
    type: type1

types:
  type1:
# checking for CW
    seq:
      - id: id2
        type:
          switch-on: message_type1
          cases:
            0x6465206F6B306C73: cw_message # de ok0ls
            _: not_cw_message

    instances:
      message_type1:
        type: u8
        pos: 0

  cw_message:
   seq:
     - id: de_ok0lsr
       type: str
       size: 13
       encoding: ASCII
       valid: '"de ok0lsr = u"' # 64 65 20 6F 6B 30 6C 73 72 20 3D 20 75

     - id: uptime_total_raw
       type: str
       terminator: 0x72  # r
       encoding: UTF-8

     - id: reset_number_raw
       type: str
       terminator: 0x74  # t
       encoding: UTF-8

     - id: temp_mcu_raw
       type: str
       terminator: 0x70  # p
       encoding: UTF-8

     - id: temp_pa_raw
       type: str
       encoding: UTF-8
       terminator: 0x20 #  "space"

     - id: ar
       type: str
       encoding: UTF-8
       size: 2
       valid: '"ar"' # 61 72

   instances:
          uptime_total:
            if: uptime_total_raw.substring(uptime_total_raw.length-1,uptime_total_raw.length) != "." and uptime_total_raw.substring(uptime_total_raw.length-2,uptime_total_raw.length-1) != "." and uptime_total_raw.substring(uptime_total_raw.length-3,uptime_total_raw.length-2) != "." and uptime_total_raw.substring(uptime_total_raw.length-4,uptime_total_raw.length-3) != "." and uptime_total_raw.substring(uptime_total_raw.length-5,uptime_total_raw.length-4) != "." and uptime_total_raw.substring(uptime_total_raw.length-6,uptime_total_raw.length-5) != "." and uptime_total_raw.substring(uptime_total_raw.length-7,uptime_total_raw.length-6) != "." and uptime_total_raw.substring(uptime_total_raw.length-8,uptime_total_raw.length-7) != "." and uptime_total_raw.substring(uptime_total_raw.length-9,uptime_total_raw.length-8) != "."
# "if" checks for "." in field. if found, it returns a "null" but keeps on parsing following fields.
            value: uptime_total_raw.to_i # ('.to_i' will even convert a "-" in front of a number into a negative integer)
          reset_number:
            if: reset_number_raw.substring(reset_number_raw.length-1,reset_number_raw.length) != "." and reset_number_raw.substring(reset_number_raw.length-2,reset_number_raw.length-1) != "." and reset_number_raw.substring(reset_number_raw.length-3,reset_number_raw.length-2) != "." and reset_number_raw.substring(reset_number_raw.length-4,reset_number_raw.length-3) != "." and reset_number_raw.substring(reset_number_raw.length-5,reset_number_raw.length-4) != "." and reset_number_raw.substring(reset_number_raw.length-6,reset_number_raw.length-5) != "." and reset_number_raw.substring(reset_number_raw.length-7,reset_number_raw.length-6) != "." and reset_number_raw.substring(reset_number_raw.length-8,reset_number_raw.length-7) != "." and reset_number_raw.substring(reset_number_raw.length-9,reset_number_raw.length-8) != "."
            value: reset_number_raw.to_i
          temp_mcu:
            if: temp_mcu_raw.substring(temp_mcu_raw.length-1,temp_mcu_raw.length) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-2,temp_mcu_raw.length-1) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-3,temp_mcu_raw.length-2) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-4,temp_mcu_raw.length-3) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-5,temp_mcu_raw.length-4) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-6,temp_mcu_raw.length-5) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-7,temp_mcu_raw.length-6) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-8,temp_mcu_raw.length-7) != "." and temp_mcu_raw.substring(temp_mcu_raw.length-9,temp_mcu_raw.length-8) != "."
            value: temp_mcu_raw.to_i
          temp_pa:
            if: temp_pa_raw.substring(temp_pa_raw.length-1,temp_pa_raw.length) != "." and temp_pa_raw.substring(temp_pa_raw.length-2,temp_pa_raw.length-1) != "." and temp_pa_raw.substring(temp_pa_raw.length-3,temp_pa_raw.length-2) != "." and temp_pa_raw.substring(temp_pa_raw.length-4,temp_pa_raw.length-3) != "." and temp_pa_raw.substring(temp_pa_raw.length-5,temp_pa_raw.length-4) != "." and temp_pa_raw.substring(temp_pa_raw.length-6,temp_pa_raw.length-5) != "." and temp_pa_raw.substring(temp_pa_raw.length-7,temp_pa_raw.length-6) != "." and temp_pa_raw.substring(temp_pa_raw.length-8,temp_pa_raw.length-7) != "." and temp_pa_raw.substring(temp_pa_raw.length-9,temp_pa_raw.length-8) != "."
            value: temp_pa_raw.to_i
          cw_beacon:
            value: '"u"+uptime_total_raw+"r"+reset_number_raw+"t"+temp_mcu_raw+"p"+temp_pa_raw'

# checking for Digi
  not_cw_message:
    seq:
      - id: id3
        type:
          switch-on: message_type2
          cases:
            0x9E966098: digi # OK0L
            _: not_digi # going to telemetry beacons

    instances:
      message_type2:
        type: u4
        pos: 14 # beginning of digi callsign

  digi:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: ax25_info
            type: ax25_info_data
            size-eos: true

      ax25_info_data:
        seq:
          - id: digi_message
            type: str
            encoding: utf-8
            size-eos: true

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
          - id: pid
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
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

# checking for beacons
  not_digi:
    seq:
      - id: id4
        type:
          switch-on: message_type3
          cases:
            0x4D47532C: mgs # MGS,
            0x4F42432C: obc # OBC,
            0x5053552C: psu # PSU,
            0x534F4C2C: sol # SOL,
            0x444F532C: dos # DOS,
            0x4E41562C: nav # NAV,
            _: v_or_u # vhf or uhf beacon

    instances:
      message_type3:
        type: u4
        pos: 16

  mgs:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: mgs_pass_packet_type
            type: str
            terminator: 0x2C
            encoding: utf8
            valid: '"MGS"'
          - id: mgs_temp_int_mag_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: mgs_temp_int_gyr_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: mgs_int_mag_x_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: mgs_int_mag_y_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: mgs_int_mag_z_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: mgs_int_gyr_x_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: mgs_int_gyr_y_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: mgs_int_gyr_z_str
            type: str
            terminator: 0x00
            encoding: utf8

        instances:
          mgs_temp_int_mag:
            value: mgs_temp_int_mag_str.to_i
          mgs_temp_int_gyr:
            value: mgs_temp_int_gyr_str.to_i
          mgs_int_mag_x:
            value: mgs_int_mag_x_str.to_i
          mgs_int_mag_y:
            value: mgs_int_mag_y_str.to_i
          mgs_int_mag_z:
            value: mgs_int_mag_z_str.to_i
          mgs_int_gyr_x:
            value: mgs_int_gyr_x_str.to_i
          mgs_int_gyr_y:
            value: mgs_int_gyr_y_str.to_i
          mgs_int_gyr_z:
            value: mgs_int_gyr_z_str.to_i

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

  obc:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: obc_pass_packet_type
            type: str
            terminator: 0x2C
            encoding: utf8
            valid: '"OBC"'
          - id: obc_rst_cnt_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: obc_uptime_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: obc_uptime_tot_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: obc_temp_mcu_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: obc_freemem_str
            type: str
            terminator: 0x00
            encoding: utf8

        instances:
          obc_reset_cnt:
            value: obc_rst_cnt_str.to_i
          obc_uptime:
            value: obc_uptime_str.to_i
          obc_uptime_tot:
            value: obc_uptime_tot_str.to_i
          obc_temp_mcu:
            value: obc_temp_mcu_str.to_i
          obc_freemem:
            value: obc_freemem_str.to_i

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

  psu:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: psu_pass_packet_type
            type: str
            terminator: 0x2C
            encoding: utf8
            valid: '"PSU"'
          - id: psu_rst_cnt_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: psu_uptime_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_uptime_tot_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_bat_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_temp_sys_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_temp_bat_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_cur_in_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_cur_out_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_ch_state_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_sys_state_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: psu_gnd_wdt_str
            type: str
            terminator: 0x00
            encoding: utf8

        instances:
          psu_reset_cnt:
            value: psu_rst_cnt_str.to_i
          psu_uptime:
            value: psu_uptime_str.to_i
          psu_uptime_tot:
            value: psu_uptime_tot_str.to_i
          psu_battery:
            value: psu_bat_str.to_i
          psu_temp_sys:
            value: psu_temp_sys_str.to_i
          psu_temp_bat:
            value: psu_temp_bat_str.to_i
          psu_cur_in:
            value: psu_cur_in_str.to_i
          psu_cur_out:
            value: psu_cur_out_str.to_i
          psu_ch_state_num:
            value: psu_ch_state_str.to_i(16)
          psu_ch0_state:
            value: (psu_ch_state_num >> 0 ) & 0x01
          psu_ch1_state:
            value: (psu_ch_state_num >> 1 ) & 0x01
          psu_ch2_state:
            value: (psu_ch_state_num >> 2 ) & 0x01
          psu_ch3_state:
            value: (psu_ch_state_num >> 3 ) & 0x01
          psu_ch4_state:
            value: (psu_ch_state_num >> 4 ) & 0x01
          psu_ch5_state:
            value: (psu_ch_state_num >> 5 ) & 0x01
          psu_ch6_state:
            value: (psu_ch_state_num >> 6 ) & 0x01
          psu_sys_state:
            value: psu_sys_state_str.to_i
          psu_gnd_wdt:
            value: psu_gnd_wdt_str.to_i

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

  sol:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: sol_pass_packet_type
            type: str
            terminator: 0x2C
            encoding: utf8
            valid: '"SOL"'
          - id: sol_temp_zp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_temp_xp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_temp_yp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_temp_zn_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_temp_xn_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_temp_yn_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_diode_zp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_diode_xp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_diode_yp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_diode_zn_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_diode_xn_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: sol_diode_yn_str
            type: str
            terminator: 0x00
            encoding: utf8

        instances:
          sol_temp_zp:
            value: 'sol_temp_zp_str == "nan" ? -32768 : sol_temp_zp_str.to_i'
          sol_temp_xp:
            value: 'sol_temp_xp_str == "nan" ? -32768 : sol_temp_xp_str.to_i'
          sol_temp_yp:
            value: 'sol_temp_yp_str == "nan" ? -32768 : sol_temp_yp_str.to_i'
          sol_temp_zn:
            value: 'sol_temp_zn_str == "nan" ? -32768 : sol_temp_zn_str.to_i'
          sol_temp_xn:
            value: 'sol_temp_xn_str == "nan" ? -32768 : sol_temp_xn_str.to_i'
          sol_temp_yn:
            value: 'sol_temp_yn_str == "nan" ? -32768 : sol_temp_yn_str.to_i'
          sol_diode_zp:
            value: 'sol_diode_zp_str == "nan" ? -32768 : sol_diode_zp_str.to_i'
          sol_diode_xp:
            value: 'sol_diode_xp_str == "nan" ? -32768 : sol_diode_xp_str.to_i'
          sol_diode_yp:
            value: 'sol_diode_yp_str == "nan" ? -32768 : sol_diode_yp_str.to_i'
          sol_diode_zn:
            value: 'sol_diode_zn_str == "nan" ? -32768 : sol_diode_zn_str.to_i'
          sol_diode_xn:
            value: 'sol_diode_xn_str == "nan" ? -32768 : sol_diode_xn_str.to_i'
          sol_diode_yn:
            value: 'sol_diode_yn_str == "nan" ? -32768 : sol_diode_yn_str.to_i'

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

  dos:
      seq:
        - id: ax25_frame
          type: ax25_frame

      types:
        ax25_frame:
          seq:
            - id: ax25_header
              type: ax25_header

            - id: dos_pass_packet_type
              type: str
              terminator: 0x2C
              encoding: utf8
              valid: '"DOS"'
            - id: dos_mode_str
              type: str
              terminator: 0x2c
              encoding: utf8
            - id: dos_gyr_x_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_gyr_y_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_gyr_z_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_mag_x_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_mag_y_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_mag_z_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_plasma_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_phd_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_dozi_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_gyr_t_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_mag_t_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_lppa_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_bus_cur_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_bus_vol_str
              type: str
              terminator: 0x2C
              encoding: utf8
            - id: dos_uptime_str
              type: str
              terminator: 0x00
              encoding: utf8

          instances:
            dos_mode:
              value: dos_mode_str.to_i
            dos_gyr_x:
              value: dos_gyr_x_str.to_i
            dos_gyr_y:
              value: dos_gyr_y_str.to_i
            dos_gyr_z:
              value: dos_gyr_z_str.to_i
            dos_mag_x:
              value: dos_mag_x_str.to_i
            dos_mag_y:
              value: dos_mag_y_str.to_i
            dos_mag_z:
              value: dos_mag_z_str.to_i
            dos_plasma:
              value: dos_plasma_str.to_i
            dos_phd:
              value: dos_phd_str.to_i
            dos_dozi:
              value: dos_dozi_str.to_i
            dos_gyr_t:
              value: dos_gyr_t_str.to_i
            dos_mag_t:
              value: dos_mag_t_str.to_i
            dos_lppa:
              value: dos_lppa_str.to_i
            dos_bus_cur:
              value: dos_bus_cur_str.to_i
            dos_bus_vol:
              value: dos_bus_vol_str.to_i
            dos_uptime:
              value: dos_uptime_str.to_i

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
            - id: ctl
              type: u1
            - id: pid
              type: u1

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
              valid:
                any-of: ['"CQ    "','"OK0LSR"']
        ssid_mask:
          seq:
            - id: ssid_mask
              type: u1
          instances:
            ssid:
              value: (ssid_mask & 0x1f) >> 1
            hbit:
              value: (ssid_mask & 0x80) >> 7

  nav:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: nav_pass_packet_type
            type: str
            terminator: 0x2C
            encoding: utf8
            valid: '"NAV"'
          - id: nav_week_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_time_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_pos_x_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_pos_y_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_pos_z_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_vel_x_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_vel_y_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_vel_z_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_sats_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_dop_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_ant_cur_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_volt_str
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: nav_max_snr_str
            type: str
            terminator: 0x00
            encoding: utf8

        instances:
          nav_week:
            value: nav_week_str.to_i
          nav_time:
            value: nav_time_str.to_i
          nav_pos_x:
            value: nav_pos_x_str.to_i
          nav_pos_y:
            value: nav_pos_y_str.to_i
          nav_pos_z:
            value: nav_pos_z_str.to_i
          nav_vel_x:
            value: nav_vel_x_str.to_i
          nav_vel_y:
            value: nav_vel_y_str.to_i
          nav_vel_z:
            value: nav_vel_z_str.to_i
          nav_sats:
            value: nav_sats_str.to_i
          nav_dop:
            value: nav_dop_str.to_i
          nav_ant_cur:
            value: nav_ant_cur_str.to_i
          nav_volt:
            value: nav_volt_str.to_i
          nav_max_snr:
            value: nav_max_snr_str.to_i

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

  v_or_u:
    seq:
      - id: id5
        type:
          switch-on: message_type4
          cases:
            0x552C: u # U,
            0x562C: v # V,
            _: lasarsat_message # AX.25 message from LASARSAT

    instances:
      message_type4:
        type: u2
        pos: 16

  u:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: uhf_packet_id_str
            type: str
            terminator: 0x2C
            encoding: utf8
            valid: '"U"'
          - id: uhf_uptime_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_uptime_tot_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_reset_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_rf_reset_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_trx_temp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_rf_temp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_pa_temp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_digipeater_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_last_digipeater_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_rx_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_tx_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_act_rssi_raw_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_dcd_rssi_raw_str
            type: str
            terminator: 0
            encoding: utf8

        instances:
          uhf_uptime:
            value: uhf_uptime_str.to_i
          uhf_uptime_tot:
            value: uhf_uptime_tot_str.to_i
          uhf_reset_cnt:
            value: uhf_reset_cnt_str.to_i
          uhf_rf_reset_cnt:
            value: uhf_rf_reset_cnt_str.to_i
          uhf_trx_temp:
            value: uhf_trx_temp_str.to_i
          uhf_rf_temp:
            value: uhf_rf_temp_str.to_i
          uhf_pa_temp:
            value: uhf_pa_temp_str.to_i
          uhf_digipeater_cnt:
            value: uhf_digipeater_cnt_str.to_i
          uhf_last_digipeater:
            value: uhf_last_digipeater_str
          uhf_rx_cnt:
            value: uhf_rx_cnt_str.to_i
          uhf_tx_cnt:
            value: uhf_tx_cnt_str.to_i
          uhf_act_rssi_raw:
            value: uhf_act_rssi_raw_str.to_i
          uhf_dcd_rssi_raw:
            value: uhf_dcd_rssi_raw_str.to_i

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

  v:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: vhf_packet_id_str
            type: str
            terminator: 0x2C
            encoding: utf8
            valid: '"V"'
          - id: vhf_uptime_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_uptime_tot_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_reset_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_rf_reset_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_trx_temp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_rf_temp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_pa_temp_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_digipeater_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_last_digipeater_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_rx_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_tx_cnt_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_act_rssi_raw_str
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_dcd_rssi_raw_str
            type: str
            terminator: 0
            encoding: utf8

        instances:
          vhf_uptime:
            value: vhf_uptime_str.to_i
          vhf_uptime_tot:
            value: vhf_uptime_tot_str.to_i
          vhf_reset_cnt:
            value: vhf_reset_cnt_str.to_i
          vhf_rf_reset_cnt:
            value: vhf_rf_reset_cnt_str.to_i
          vhf_trx_temp:
            value: vhf_trx_temp_str.to_i
          vhf_rf_temp:
            value: vhf_rf_temp_str.to_i
          vhf_pa_temp:
            value: vhf_pa_temp_str.to_i
          vhf_digipeater_cnt:
            value: vhf_digipeater_cnt_str.to_i
          vhf_last_digipeater:
            value: vhf_last_digipeater_str
          vhf_rx_cnt:
            value: vhf_rx_cnt_str.to_i
          vhf_tx_cnt:
            value: vhf_tx_cnt_str.to_i
          vhf_act_rssi_raw:
            value: vhf_act_rssi_raw_str.to_i
          vhf_dcd_rssi_raw:
            value: vhf_dcd_rssi_raw_str.to_i

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

  lasarsat_message:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header

          - id: lasarsat_message
            type: str
            encoding: utf8
            size-eos: true

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
          - id: ctl
            type: u1
          - id: pid
            type: u1

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
            valid:
              any-of: ['"CQ    "','"OK0LSR"']
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7
