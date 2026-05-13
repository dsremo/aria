---
meta:
  id: cevrosat
  title: CEVROSAT-1 beacon + digipeater decoder
  endian: be
# 2025-11-02, DL7NDR
# https://cevrosat.cz/
doc: |
  :field uptime_total: id_one.type_check.uptime_total
  :field uptime_since_last: id_one.type_check.uptime_since_last
  :field reset_count: id_one.type_check.reset_count
  :field mcu_10mv: id_one.type_check.mcu_10mv
  :field batt: id_one.type_check.batt
  :field temp_cpu: id_one.type_check.temp_cpu
  :field temp_pa_ntc: id_one.type_check.temp_pa_ntc
  :field sig_rx_immediate: id_one.type_check.sig_rx_immediate
  :field sig_rx_avg: id_one.type_check.sig_rx_avg
  :field sig_rx_max: id_one.type_check.sig_rx_max
  :field sig_background_avg: id_one.type_check.sig_background_avg
  :field sig_background_immediate: id_one.type_check.sig_background_immediate
  :field sig_background_max: id_one.type_check.sig_background_max
  :field rf_packets_received: id_one.type_check.rf_packets_received
  :field rf_packets_transmitted: id_one.type_check.rf_packets_transmitted
  :field ax25_packets_received: id_one.type_check.ax25_packets_received
  :field ax25_packets_transmitted: id_one.type_check.ax25_packets_transmitted
  :field digipeater_rx_count: id_one.type_check.digipeater_rx_count
  :field digipeater_tx_count: id_one.type_check.digipeater_tx_count
  :field csp_received: id_one.type_check.csp_received
  :field csp_transmitted: id_one.type_check.csp_transmitted
  :field i2c1_received: id_one.type_check.i2c1_received
  :field i2c1_transmitted: id_one.type_check.i2c1_transmitted
  :field i2c2_received: id_one.type_check.i2c2_received
  :field i2c2_transmitted: id_one.type_check.i2c2_transmitted
  :field rs485_received: id_one.type_check.rs485_received
  :field rs485_transmitted: id_one.type_check.rs485_transmitted
  :field csp_mcu_received: id_one.type_check.csp_mcu_received
  :field csp_mcu_transmitted: id_one.type_check.csp_mcu_transmitted
  :field a: id_one.type_check.a
  :field tx1_telemetry: id_one.type_check.tx1_telemetry
  :field src_callsign: id_one.type_check.ax25_frame.ax25_header.dnxd_src_callsign_raw.callsign_ror.callsign
  :field src_ssid: id_one.type_check.ax25_frame.ax25_header.dnxd_src_ssid_raw.ssid
  :field dest_callsign: id_one.type_check.ax25_frame.ax25_header.dnxd_dest_callsign_raw.callsign_ror.callsign
  :field dest_ssid: id_one.type_check.ax25_frame.ax25_header.dnxd_dest_ssid_raw.ssid
  :field dnxd_message: id_one.type_check.ax25_frame.dnxd_message
  :field src_callsign: id_one.type_check.digi_ax25_frame.digi_ax25_header.digi_src_callsign_raw.callsign_ror.callsign
  :field src_ssid: id_one.type_check.digi_ax25_frame.digi_ax25_header.digi_src_ssid_raw.ssid
  :field dest_callsign: id_one.type_check.digi_ax25_frame.digi_ax25_header.digi_dest_callsign_raw.callsign_ror.callsign
  :field dest_ssid: id_one.type_check.digi_ax25_frame.digi_ax25_header.digi_dest_ssid_raw.ssid
  :field rpt_instance_callsign: id_one.type_check.digi_ax25_frame.digi_ax25_header.repeater.rpt_instance.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance_ssid: id_one.type_check.digi_ax25_frame.digi_ax25_header.repeater.rpt_instance.rpt_ssid_raw.ssid
  :field digi_message: id_one.type_check.digi_ax25_frame.digi_message

seq:
  - id: id_one
    type: id_one_type

types:
  id_one_type:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x86ACA461: tx_1 # CVR-0
            0x86ACA471: dnxd # CVR-8 for "busy" or "thank you for using" messages from DNxD
            _: digi # everything else (for via OK0CVR-8 or -7)

    instances:
        check:
              type: u4be
              pos: 10

  tx_1:
    seq:
      - id: skip_ax25_header_1
        type: u8
        valid: '9701387192009547934'
      - id: skip_ax25_header_2
        type: u8
        valid: '10835808779503731696'
      - id: first_comma
        type: u1
        valid: 0x2c
      - id: tx_1
        type: str
        terminator: 0x2c
        encoding: utf8
        valid: '"TX-1"'
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
      - id: csp_mcu_transmitted_raw
        type: str
        encoding: utf8
        terminator: 0x2C
      - id: pass_a
        type: str
        terminator: 0x2C
        encoding: utf8
        valid: '"A"'
      - id: a_raw
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
      csp_mcu_transmitted:
        value: csp_mcu_transmitted_raw.to_i
      a:
        value: a_raw.to_i

      tx1_telemetry:
        value: '",TX-1,U,"+uptime_total_raw+","+uptime_since_last_raw+",R,"+reset_count_raw+",V,"+mcu_10mv_raw+",Ve,"+batt_raw+",T,"+temp_cpu_raw+","+temp_pa_ntc_raw+",Sig,"+sig_rx_immediate_raw+","+sig_rx_avg_raw+","+sig_rx_max_raw+","+sig_background_immediate_raw+","+sig_background_avg_raw+","+sig_background_max_raw+",RX,"+rf_packets_received_raw+","+rf_packets_transmitted_raw+",Ax,"+ax25_packets_received_raw+","+ax25_packets_transmitted_raw+",Digi,"+digipeater_rx_count_raw+","+digipeater_tx_count_raw+",CSP,"+csp_received_raw+","+csp_transmitted_raw+",I2C1,"+i2c1_received_raw+","+i2c1_transmitted_raw+",I2C2,"+i2c2_received_raw+","+i2c2_received_raw+",RS485,"+rs485_received_raw+","+rs485_transmitted_raw+",MCU,"+csp_mcu_received_raw+","+csp_mcu_transmitted_raw+",A,"+a_raw'


  dnxd:
    seq:
      - id: ax25_frame
        type: ax25_frame

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
            if: dnxd_src_callsign_raw.callsign_ror.callsign == "OK0CVR"
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
            if: repeater.rpt_instance.rpt_callsign_raw.callsign_ror.callsign == "OK0CVR"
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
