---
meta:
  id: grbalpha
  title: GRBAlpha beacon + digipeater decoder
  endian: le
# 2024-10-08, DL7NDR [bugfixed and extended by digipeater decoder]
# 2025-04-29, DL7NDR [added support for new GPS beacon]
doc: |
  :field uptime_total: grbalpha.type_check.uptime_total
  :field uptime_since_last: grbalpha.type_check.uptime_since_last
  :field reset_count: grbalpha.type_check.reset_count
  :field mcu_10mv: grbalpha.type_check.mcu_10mv
  :field batt: grbalpha.type_check.batt
  :field temp_cpu: grbalpha.type_check.temp_cpu
  :field temp_pa_ntc: grbalpha.type_check.temp_pa_ntc
  :field sig_rx_immediate: grbalpha.type_check.sig_rx_immediate
  :field sig_rx_avg: grbalpha.type_check.sig_rx_avg
  :field sig_rx_max: grbalpha.type_check.sig_rx_max
  :field sig_background_avg: grbalpha.type_check.sig_background_avg
  :field sig_background_immediate: grbalpha.type_check.sig_background_immediate
  :field sig_background_max: grbalpha.type_check.sig_background_max
  :field rf_packets_received: grbalpha.type_check.rf_packets_received
  :field rf_packets_transmitted: grbalpha.type_check.rf_packets_transmitted
  :field ax25_packets_received: grbalpha.type_check.ax25_packets_received
  :field ax25_packets_transmitted: grbalpha.type_check.ax25_packets_transmitted
  :field digipeater_rx_count: grbalpha.type_check.digipeater_rx_count
  :field digipeater_tx_count: grbalpha.type_check.digipeater_tx_count
  :field csp_received: grbalpha.type_check.csp_received
  :field csp_transmitted: grbalpha.type_check.csp_transmitted
  :field i2c1_received: grbalpha.type_check.i2c1_received
  :field i2c1_transmitted: grbalpha.type_check.i2c1_transmitted
  :field i2c2_received: grbalpha.type_check.i2c2_received
  :field i2c2_transmitted: grbalpha.type_check.i2c2_transmitted
  :field rs485_received: grbalpha.type_check.rs485_received
  :field rs485_transmitted: grbalpha.type_check.rs485_transmitted
  :field csp_mcu_received: grbalpha.type_check.csp_mcu_received
  :field csp_mcu_transmitted: grbalpha.type_check.csp_mcu_transmitted
  :field unix_time: grbalpha.type_check.obc_gps.type_check_2.unix_time
  :field lock_count: grbalpha.type_check.obc_gps.type_check_2.lock_count
  :field latitude: grbalpha.type_check.obc_gps.type_check_2.latitude
  :field longitude: grbalpha.type_check.obc_gps.type_check_2.longitude
  :field altitude: grbalpha.type_check.obc_gps.type_check_2.altitude
  :field obc_timestamp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_timestamp
  :field obc_temp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_temp
  :field obc_tmp112_xp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_tmp112_xp
  :field obc_tmp112_yp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_tmp112_yp
  :field obc_tmp112_xn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_tmp112_xn
  :field obc_tmp112_yn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_tmp112_yn
  :field obc_tmp112_zp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_tmp112_zp
  :field obc_mag_mmc_x: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_mag_mmc_x
  :field obc_mag_mmc_y: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_mag_mmc_y
  :field obc_mag_mmc_z: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_mag_mmc_z
  :field obc_mag_mpu_x: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_mag_mpu_x
  :field obc_mag_mpu_y: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_mag_mpu_y
  :field obc_mag_mpu_z: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_mag_mpu_z
  :field obc_mpu_temp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_mpu_temp
  :field obc_gyr_mpu_x: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_gyr_mpu_x
  :field obc_gyr_mpu_y: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_gyr_mpu_y
  :field obc_gyr_mpu_z: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_gyr_mpu_z
  :field obc_acc_mpu_x: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_acc_mpu_x
  :field obc_acc_mpu_y: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_acc_mpu_y
  :field obc_acc_mpu_z: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_acc_mpu_z
  :field obc_uptime_rst: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_uptime_rst
  :field obc_uptime_total: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_uptime_total
  :field obc_rst_cnt: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_rst_cnt
  :field obc_packet_rec_cnt: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_packet_rec_cnt
  :field obc_suns_temp_yn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_temp_yn
  :field obc_suns_temp_yp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_temp_yp
  :field obc_suns_temp_xp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_temp_xp
  :field obc_suns_temp_xn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_temp_xn
  :field obc_suns_temp_zn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_temp_zn
  :field obc_suns_irad_yn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_irad_yn
  :field obc_suns_irad_yp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_irad_yp
  :field obc_suns_irad_xp: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_irad_xp
  :field obc_suns_irad_xn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_irad_xn
  :field obc_suns_irad_zn: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_suns_irad_zn
  :field gps_rst_cnt: grbalpha.type_check.obc_gps.type_check_2.bytes.gps_rst_cnt
  :field gps_fix_quality: grbalpha.type_check.obc_gps.type_check_2.bytes.gps_fix_quality
  :field gps_tracked: grbalpha.type_check.obc_gps.type_check_2.bytes.gps_tracked
  :field gps_temp: grbalpha.type_check.obc_gps.type_check_2.bytes.gps_temp
  :field obc_free_mem: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_free_mem
  :field obc_crc: grbalpha.type_check.obc_gps.type_check_2.bytes.obc_crc
  :field src_callsign: grbalpha.type_check.ax25_frame.ax25_header.dnxd_src_callsign_raw.callsign_ror.callsign
  :field src_ssid: grbalpha.type_check.ax25_frame.ax25_header.dnxd_src_ssid_raw.ssid
  :field dest_callsign: grbalpha.type_check.ax25_frame.ax25_header.dnxd_dest_callsign_raw.callsign_ror.callsign
  :field dest_ssid: grbalpha.type_check.ax25_frame.ax25_header.dnxd_dest_ssid_raw.ssid
  :field dnxd_message: grbalpha.type_check.ax25_frame.dnxd_message
  :field src_callsign: grbalpha.type_check.digi_ax25_frame.digi_ax25_header.digi_src_callsign_raw.callsign_ror.callsign
  :field src_ssid: grbalpha.type_check.digi_ax25_frame.digi_ax25_header.digi_src_ssid_raw.ssid
  :field dest_callsign: grbalpha.type_check.digi_ax25_frame.digi_ax25_header.digi_dest_callsign_raw.callsign_ror.callsign
  :field dest_ssid: grbalpha.type_check.digi_ax25_frame.digi_ax25_header.digi_dest_ssid_raw.ssid
  :field rpt_instance_callsign: grbalpha.type_check.digi_ax25_frame.digi_ax25_header.repeater.rpt_instance.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance_ssid: grbalpha.type_check.digi_ax25_frame.digi_ax25_header.repeater.rpt_instance.rpt_ssid_raw.ssid
  :field digi_message: grbalpha.type_check.digi_ax25_frame.digi_message

seq:
  - id: grbalpha
    type: grbalpha_t

types:
  grbalpha_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x8EA48461: comd # GRB-0
            0x8EA4847F: obc_or_gps # GRB-15
            0x8EA48471: dnxd # GRB-8 for "busy" or "thank you for using" messages from DNxD
            _: digi # everything else (for via OM9GRB-8 or -7)

    instances:
        check:
              type: u4be
              pos: 10

  comd:
    doc-ref: "https://needronix.eu/products/cormorant/hamradio-user-guide/"
    seq:
      - id: skip_ax25_header_and_first_comma
        type: b136
        valid: '45813505712886752328085782188142543237164' # 86A240404040E09E9A728EA4846103F02C = CQ-0 OM9GRB-0 03F0 ,
      - id: comd
        type: str
        terminator: 0x2c
        encoding: utf8
        valid: '"COMd"'
      - id: pass_uptime
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"U"'
      - id: uptime_total_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: uptime_since_last_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_resets
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"R"'
      - id: reset_count_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_mcuv
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"V"'
      - id: mcu_10mv_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_battv
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"Ve"'
      - id: batt_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_temp
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"T"'
      - id: temp_cpu_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: temp_pa_ntc_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_sig
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"Sig"'
      - id: sig_rx_immediate_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: sig_rx_avg_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: sig_rx_max_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: sig_background_immediate_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: sig_background_avg_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: sig_background_max_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_rf
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"RX"'
      - id: rf_packets_received_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: rf_packets_transmitted_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_ax25
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"Ax"'
      - id: ax25_packets_received_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: ax25_packets_transmitted_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_digi
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"Digi"'
      - id: digipeater_rx_count_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: digipeater_tx_count_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_csp
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"CSP"'
      - id: csp_received_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: csp_transmitted_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_i2c1
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"I2C1"'
      - id: i2c1_received_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: i2c1_transmitted_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_i2c2
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"I2C2"'
      - id: i2c2_received_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: i2c2_transmitted_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_rs485
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"RS485"'
      - id: rs485_received_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: rs485_transmitted_raw
        type: str
        terminator: 0x2C
        encoding: utf8
      - id: pass_csp_mcu
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"MCU"'
      - id: csp_mcu_received_raw
        type: str
        terminator: 0x2C
        encoding: utf8
        consume: false # we move the terminator (0x2C = ",") to the next field (csp_mcu_transmitted_raw). This is necessary to be able to process this field in case nothing follows after ",".
      - id: csp_mcu_transmitted_raw
        type: str
        size-eos: true
        encoding: utf8

    instances:
      uptime_total:
        value: uptime_total_raw.to_i
      uptime_since_last:
        value: uptime_since_last_raw.to_i
      reset_count:
        value: reset_count_raw.to_i
      mcu_10mv:
        value: mcu_10mv_raw.to_i
      batt:
        value: batt_raw.to_i
      temp_cpu:
        value: temp_cpu_raw.to_i
      temp_pa_ntc:
        value: temp_pa_ntc_raw.to_i
      sig_rx_immediate:
        value: sig_rx_immediate_raw.to_i
      sig_rx_avg:
        value: sig_rx_avg_raw.to_i
      sig_rx_max:
        value: sig_rx_max_raw.to_i
      sig_background_avg:
        value: sig_background_avg_raw.to_i
      sig_background_immediate:
        value: sig_background_immediate_raw.to_i
      sig_background_max:
        value: sig_background_max_raw.to_i
      rf_packets_received:
        value: rf_packets_received_raw.to_i
      rf_packets_transmitted:
        value: rf_packets_transmitted_raw.to_i
      ax25_packets_received:
        value: ax25_packets_received_raw.to_i
      ax25_packets_transmitted:
        value: ax25_packets_transmitted_raw.to_i
      digipeater_rx_count:
        value: digipeater_rx_count_raw.to_i
      digipeater_tx_count:
        value: digipeater_tx_count_raw.to_i
      csp_received:
        value: csp_received_raw.to_i
      csp_transmitted:
        value: csp_transmitted_raw.to_i
      i2c1_received:
        value: i2c1_received_raw.to_i
      i2c1_transmitted:
        value: i2c1_transmitted_raw.to_i
      i2c2_received:
        value: i2c2_received_raw.to_i
      i2c2_transmitted:
        value: i2c2_transmitted_raw.to_i
      rs485_received:
        value: rs485_received_raw.to_i
      rs485_transmitted:
        value: rs485_transmitted_raw.to_i
      csp_mcu_received:
        value: csp_mcu_received_raw.to_i
      csp_mcu_transmitted: # 62% of all COMd packets lack this value.
        if: csp_mcu_transmitted_raw != "," # will be processed only if field is more than just ",". If only ",", then field will return NULL.
        value: csp_mcu_transmitted_raw.substring(1,csp_mcu_transmitted_raw.length).to_i

  obc_or_gps:
    seq:
      - id: skip_ax25_header
        type: b128
        valid: '178959006690963876281585086672433775600' # 86A240404040E09E9A728EA4847F03F0 = CQ-0 OM9GRB-15 03F0


      - id: obc_gps
        type: obc_gps_t

    types:
      obc_gps_t:
        seq:
          - id: type_check_2
            type:
              switch-on: check_2
              cases:
                0x4750533A: gps # GPS":"
                _: obc

        instances:
            check_2:
                  type: u4be
                  pos: 16

      gps:
        seq:
          - id: gps
            type: u4
            valid: '978538567' # 0x4750533A
          - id: unix_time_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: lock_count_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: latitude_before_dot_raw
            type: str
            terminator: 0x2E
            encoding: utf8
          - id: latitude_after_dot_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: longitude_before_dot_raw
            type: str
            terminator: 0x2E
            encoding: utf8
          - id: longitude_after_dot_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: altitude_before_dot_raw
            type: str
            terminator: 0x2E
            encoding: utf8
          - id: altitude_after_dot_raw
            type: str
            size-eos: true
            encoding: utf8


        instances:
          unix_time:
            value: unix_time_raw.to_i
          lock_count:
            value: lock_count_raw.to_i
          latitude_before_dot:
            value: latitude_before_dot_raw.to_i
          latitude_after_dot:
            value: latitude_after_dot_raw.to_i
          latitude:
            value: 'latitude_before_dot_raw.substring(0,1) == "-" ? latitude_before_dot - 0.00001*latitude_after_dot : latitude_before_dot + 0.00001*latitude_after_dot'
          longitude_before_dot:
            value: longitude_before_dot_raw.to_i
          longitude_after_dot:
            value: longitude_after_dot_raw.to_i
          longitude:
            value: 'longitude_before_dot_raw.substring(0,1) == "-" ? longitude_before_dot - 0.00001*longitude_after_dot : longitude_before_dot + 0.00001*longitude_after_dot'
          altitude_before_dot:
            value: altitude_before_dot_raw.to_i
          altitude_after_dot:
            value: altitude_after_dot_raw.to_i
          altitude:
            value: altitude_before_dot + 0.1*altitude_after_dot

      obc:
        seq:
          - id: bytes
            process: satnogsdecoders.process.b64decode
            type: obc_bytes
            size: 124

      obc_bytes:
        seq:
          - id: obc_timestamp
            type: u4
          - id: obc_temp
            type: s2
          - id: obc_tmp112_xp
            type: s2
          - id: obc_tmp112_yp
            type: s2
          - id: obc_tmp112_xn
            type: s2
          - id: obc_tmp112_yn
            type: s2
          - id: obc_tmp112_zp
            type: s2
          - id: obc_mag_mmc_x
            type: s2
          - id: obc_mag_mmc_y
            type: s2
          - id: obc_mag_mmc_z
            type: s2
          - id: obc_mag_mpu_x
            type: s2
          - id: obc_mag_mpu_y
            type: s2
          - id: obc_mag_mpu_z
            type: s2
          - id: obc_mpu_temp
            type: f4
          - id: obc_gyr_mpu_x
            type: s2
          - id: obc_gyr_mpu_y
            type: s2
          - id: obc_gyr_mpu_z
            type: s2
          - id: obc_acc_mpu_x
            type: s2
          - id: obc_acc_mpu_y
            type: s2
          - id: obc_acc_mpu_z
            type: s2
          - id: obc_uptime_rst
            type: u4
          - id: obc_uptime_total
            type: u4
          - id: obc_rst_cnt
            type: u4
          - id: obc_packet_rec_cnt
            type: u4
          - id: obc_suns_temp_yn
            type: u2
          - id: obc_suns_temp_yp
            type: u2
          - id: obc_suns_temp_xp
            type: u2
          - id: obc_suns_temp_xn
            type: u2
          - id: obc_suns_temp_zn
            type: u2
          - id: obc_suns_irad_yn
            type: u2
          - id: obc_suns_irad_yp
            type: u2
          - id: obc_suns_irad_xp
            type: u2
          - id: obc_suns_irad_xn
            type: u2
          - id: obc_suns_irad_zn
            type: u2
          - id: gps_rst_cnt
            type: u4
          - id: gps_fix_quality
            type: u1
          - id: gps_tracked
            type: u1
          - id: gps_temp
            type: s2
          - id: obc_free_mem
            type: u2
          - id: obc_crc
            type: u2

  dnxd:
    seq:
      - id: ax25_frame
        type: ax25_frame
        doc-ref: 'https://www.tapr.org/pub_ax25.html'

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: dnxd_message
            type: str
            encoding: utf-8
            size-eos: true

      ax25_header:
        seq:
          - id: dnxd_dest_callsign_raw
            type: callsign_raw
          - id: dnxd_dest_ssid_raw
            type: ssid_mask
          - id: dnxd_src_callsign_raw
            type: callsign_raw
          - id: dnxd_src_ssid_raw
            type: ssid_mask
            if: dnxd_src_callsign_raw.callsign_ror.callsign == "OM9GRB"
          - id: ctl_pid
            type: u2
            if: dnxd_src_ssid_raw.ssid == 8

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

  digi:
    seq:
      - id: digi_ax25_frame
        type: ax25_frame
        doc-ref: 'https://www.tapr.org/pub_ax25.html'

    types:
      ax25_frame:
        seq:
          - id: digi_ax25_header
            type: ax25_header
          - id: digi_message
            type: str
            encoding: utf-8
            size-eos: true

      ax25_header:
        seq:
          - id: digi_dest_callsign_raw
            type: callsign_raw
          - id: digi_dest_ssid_raw
            type: ssid_mask
          - id: digi_src_callsign_raw
            type: callsign_raw
          - id: digi_src_ssid_raw
            type: ssid_mask
          - id: repeater
            type: repeater
            if: (digi_src_ssid_raw.ssid_mask & 0x01) == 0
            doc: "Repeater flag is set!"
          - id: ctl
            type: u1
            if: repeater.rpt_instance.rpt_callsign_raw.callsign_ror.callsign == "OM9GRB"
          - id: pid
            type: u1
            if: repeater.rpt_instance.rpt_ssid_raw.ssid == 7 or repeater.rpt_instance.rpt_ssid_raw.ssid == 8 # -7 normal Digi, -8 DNxD

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

      repeater:
        seq:
          - id: rpt_instance
            type: repeaters

      repeaters:
        seq:
          - id: rpt_callsign_raw
            type: callsign_raw
          - id: rpt_ssid_raw
            type: ssid_mask
