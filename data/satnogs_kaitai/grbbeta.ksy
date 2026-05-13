---
meta:
  id: grbbeta
  title: GRBBeta beacon, message and digi decoder
  endian: be
doc-ref: "https://grbbeta.tuke.sk/index.php/en/home/"
# 2024-08-01, DL7NDR; 2024-10-27, extended by Samuel Toman to process PSU HK
doc: |
  :field uptime_total: id1.id2.uptime_total
  :field radio_boot_count: id1.id2.radio_boot_count
  :field radio_mcu_act_temperature: id1.id2.radio_mcu_act_temperature
  :field rf_power_amplifier_act_temperature: id1.id2.rf_power_amplifier_act_temperature
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
  :field digi_message: id1.id2.id3.ax25_frame.digi_message
  :field uhf_uptime_since_reset: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_uptime_since_reset
  :field uhf_uptime_total: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_uptime_total
  :field uhf_radio_boot_count: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_radio_boot_count
  :field uhf_rf_segment_reset_count: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_rf_segment_reset_count
  :field uhf_radio_mcu_act_temperature: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_radio_mcu_act_temperature
  :field uhf_rf_chip_act_temperature: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_rf_chip_act_temperature
  :field uhf_rf_power_amplifier_act_temperature: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_rf_power_amplifier_act_temperature
  :field uhf_digipeater_forwarded_message_count: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_digipeater_forwarded_message_count
  :field uhf_last_digipeater_user_sender_s_callsign: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_last_digipeater_user_sender_s_callsign
  :field uhf_rx_data_packets: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_rx_data_packets
  :field uhf_tx_data_packets: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_tx_data_packets
  :field uhf_actual_rssi: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_actual_rssi
  :field uhf_value_of_rssi_when_carrier_detected: id1.id2.id3.id4.ax25_frame.ax25_payload.uhf_value_of_rssi_when_carrier_detected
  :field vhf_uptime_since_reset: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_uptime_since_reset
  :field vhf_uptime_total: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_uptime_total
  :field vhf_radio_boot_count: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_radio_boot_count
  :field vhf_rf_segment_reset_count: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_rf_segment_reset_count
  :field vhf_radio_mcu_act_temperature: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_radio_mcu_act_temperature
  :field vhf_rf_chip_act_temperature: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_rf_chip_act_temperature
  :field vhf_rf_power_amplifier_act_temperature: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_rf_power_amplifier_act_temperature
  :field vhf_digipeater_forwarded_message_count: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_digipeater_forwarded_message_count
  :field vhf_last_digipeater_user_sender_s_callsign: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_last_digipeater_user_sender_s_callsign
  :field vhf_rx_data_packets: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_rx_data_packets
  :field vhf_tx_data_packets: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_tx_data_packets
  :field vhf_actual_rssi: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_actual_rssi
  :field vhf_value_of_rssi_when_carrier_detected: id1.id2.id3.id4.ax25_frame.ax25_payload.vhf_value_of_rssi_when_carrier_detected
  :field message: id1.id2.id3.id4.id5.ax25_frame.message
  :field csp_hdr_crc: id1.id2.id3.id4.id5.csp_header.crc
  :field csp_hdr_rdp: id1.id2.id3.id4.id5.csp_header.rdp
  :field csp_hdr_xtea: id1.id2.id3.id4.id5.csp_header.xtea
  :field csp_hdr_hmac: id1.id2.id3.id4.id5.csp_header.hmac
  :field csp_hdr_src_port: id1.id2.id3.id4.id5.csp_header.source_port
  :field csp_hdr_dst_port: id1.id2.id3.id4.id5.csp_header.destination_port
  :field csp_hdr_destination: id1.id2.id3.id4.id5.csp_header.destination
  :field csp_hdr_source: id1.id2.id3.id4.id5.csp_header.source
  :field csp_hdr_priority: id1.id2.id3.id4.id5.csp_header.priority
  :field psu_utc_time_stamp_rtc: id1.id2.id3.id4.id5.csp_data.telemetry.utc_time_stamp_rtc
  :field psu_uptime_rst: id1.id2.id3.id4.id5.csp_data.telemetry.uptime_rst
  :field psu_uptime_tot: id1.id2.id3.id4.id5.csp_data.telemetry.uptime_tot
  :field psu_reset_cnt: id1.id2.id3.id4.id5.csp_data.telemetry.reset_cnt
  :field psu_last_rst_src: id1.id2.id3.id4.id5.csp_data.telemetry.last_rst_src
  :field psu_packets_recvd_cnt: id1.id2.id3.id4.id5.csp_data.telemetry.packets_recvd_cnt
  :field psu_psu_error_count: id1.id2.id3.id4.id5.csp_data.telemetry.psu_error_count
  :field psu_pv_in_volt1: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_volt1
  :field psu_pv_in_volt2: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_volt2
  :field psu_pv_in_volt3: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_volt3
  :field psu_pv_in_amp1: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_amp1
  :field psu_pv_in_amp2: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_amp2
  :field psu_pv_in_amp3: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_amp3
  :field psu_pv_in_power1: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_power1
  :field psu_pv_in_power2: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_power2
  :field psu_pv_in_power3: id1.id2.id3.id4.id5.csp_data.telemetry.pv_in_power3
  :field psu_system_state: id1.id2.id3.id4.id5.csp_data.telemetry.system_state
  :field psu_out_sys_ch_amp1: id1.id2.id3.id4.id5.csp_data.telemetry.out_sys_ch_amp1
  :field psu_out_sys_ch_amp2: id1.id2.id3.id4.id5.csp_data.telemetry.out_sys_ch_amp2
  :field psu_out_sys_ch_amp3: id1.id2.id3.id4.id5.csp_data.telemetry.out_sys_ch_amp3
  :field psu_out_sys_ch_amp4: id1.id2.id3.id4.id5.csp_data.telemetry.out_sys_ch_amp4
  :field psu_out_sys_ch_amp5: id1.id2.id3.id4.id5.csp_data.telemetry.out_sys_ch_amp5
  :field psu_out_sys_ch_amp6: id1.id2.id3.id4.id5.csp_data.telemetry.out_sys_ch_amp6
  :field psu_out_sys_bat_unreg_amp: id1.id2.id3.id4.id5.csp_data.telemetry.out_sys_bat_unreg_amp
  :field psu_bat_volt: id1.id2.id3.id4.id5.csp_data.telemetry.bat_volt
  :field psu_bat_amp_charge: id1.id2.id3.id4.id5.csp_data.telemetry.bat_amp_charge
  :field psu_bat_amp_discharge: id1.id2.id3.id4.id5.csp_data.telemetry.bat_amp_discharge
  :field psu_bat_temp_kelvin: id1.id2.id3.id4.id5.csp_data.telemetry.bat_temp_kelvin
  :field psu_system_temp_kelvin: id1.id2.id3.id4.id5.csp_data.telemetry.system_temp_kelvin
  :field psu_channel_0_status: id1.id2.id3.id4.id5.csp_data.telemetry.channel_0_status
  :field psu_channel_1_status: id1.id2.id3.id4.id5.csp_data.telemetry.channel_1_status
  :field psu_channel_2_status: id1.id2.id3.id4.id5.csp_data.telemetry.channel_2_status
  :field psu_channel_3_status: id1.id2.id3.id4.id5.csp_data.telemetry.channel_3_status
  :field psu_channel_4_status: id1.id2.id3.id4.id5.csp_data.telemetry.channel_4_status
  :field psu_channel_5_status: id1.id2.id3.id4.id5.csp_data.telemetry.channel_5_status
  :field psu_channel_6_status: id1.id2.id3.id4.id5.csp_data.telemetry.channel_6_status
  :field psu_mppt_ch1_state: id1.id2.id3.id4.id5.csp_data.telemetry.mppt_ch1_state
  :field psu_mppt_ch2_state: id1.id2.id3.id4.id5.csp_data.telemetry.mppt_ch2_state
  :field psu_mppt_ch3_state: id1.id2.id3.id4.id5.csp_data.telemetry.mppt_ch3_state
  
  
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
            0x6465206861326772: cw_message # de ha2gr
            _: not_cw_message

    instances:
      message_type1:
        type: u8
        pos: 0

  cw_message:
   seq:
     - id: de_ha2grb
       type: str
       size: 13
       encoding: ASCII
       valid:
        any-of:
          - '"de ha2grb = u"'
          - '"DE HA2GRB = U"'

     - id: uptime_total_raw
       type: str
       terminator: 0x72  # r
       encoding: UTF-8

     - id: radio_boot_count_raw
       type: str
       terminator: 0x74  # t
       encoding: UTF-8

     - id: radio_mcu_act_temperature_raw
       type: str
       terminator: 0x70  # p
       encoding: UTF-8

     - id: rf_power_amplifier_act_temperature_raw
       type: str
       encoding: UTF-8
       terminator: 0x20 # 'space'

   instances:
          uptime_total:
            value: uptime_total_raw.to_i *60 # to get seconds
          radio_boot_count:
            value: radio_boot_count_raw.to_i
          radio_mcu_act_temperature:
            value: radio_mcu_act_temperature_raw.to_i
          rf_power_amplifier_act_temperature:
            value: rf_power_amplifier_act_temperature_raw.to_i
          cw_beacon:
             value: '"u"+uptime_total_raw+"r"+radio_boot_count_raw+"t"+radio_mcu_act_temperature_raw+"p"+rf_power_amplifier_act_temperature_raw'

# checking for Digi
  not_cw_message:
    seq:
      - id: id3
        type:
          switch-on: message_type2
          cases:
            0x9082648E: digi # HA2G
            _: not_digi

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

# checking for beacon
  not_digi:
    seq:
      - id: id4
        type:
          switch-on: message_type3
          cases:
            0x552C: beacon_uhf
            0x562C: beacon_vhf
            _: not_beacon

    instances:
      message_type3:
        type: u2
        pos: 16 # beginning of payload

  beacon_uhf:
    seq:
     - id: ax25_frame
       type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: ax25_payload
            type: ax25_payload

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
      ssid_mask:
         seq:
           - id: ssid_mask
             type: u1
         instances:
           ssid:
             value: (ssid_mask & 0x1f) >> 1

      ax25_payload:
        seq:
          - id: uhf_beacon_identification
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: uhf_uptime_since_reset_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_uptime_total_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_radio_boot_count_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_rf_segment_reset_count_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_radio_mcu_act_temperature_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_rf_chip_act_temperature_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_rf_power_amplifier_act_temperature_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_digipeater_forwarded_message_count_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_last_digipeater_user_sender_s_callsign
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_rx_data_packets_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_tx_data_packets_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_actual_rssi_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: uhf_value_of_rssi_when_carrier_detected_raw
            type: str
            terminator: 0x00
            encoding: utf8

        instances:
          uhf_uptime_since_reset:
            value: uhf_uptime_since_reset_raw.to_i
          uhf_uptime_total:
            value: uhf_uptime_total_raw.to_i
          uhf_radio_boot_count:
            value: uhf_radio_boot_count_raw.to_i
          uhf_rf_segment_reset_count:
            value: uhf_rf_segment_reset_count_raw.to_i
          uhf_radio_mcu_act_temperature:
            value: uhf_radio_mcu_act_temperature_raw.to_i
          uhf_rf_chip_act_temperature:
            value: uhf_rf_chip_act_temperature_raw.to_i
          uhf_rf_power_amplifier_act_temperature:
            value: uhf_rf_power_amplifier_act_temperature_raw.to_i
          uhf_digipeater_forwarded_message_count:
            value: uhf_digipeater_forwarded_message_count_raw.to_i
          uhf_rx_data_packets:
            value: uhf_rx_data_packets_raw.to_i
          uhf_tx_data_packets:
            value: uhf_tx_data_packets_raw.to_i
          uhf_actual_rssi:
            value: uhf_actual_rssi_raw.to_i
          uhf_value_of_rssi_when_carrier_detected:
            value: uhf_value_of_rssi_when_carrier_detected_raw.to_i

  beacon_vhf:
    seq:
     - id: ax25_frame
       type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: ax25_payload
            type: ax25_payload

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
      ssid_mask:
         seq:
           - id: ssid_mask
             type: u1
         instances:
           ssid:
             value: (ssid_mask & 0x1f) >> 1

      ax25_payload:
        seq:
          - id: vhf_beacon_identification
            type: str
            terminator: 0x2c
            encoding: utf8
          - id: vhf_uptime_since_reset_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_uptime_total_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_radio_boot_count_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_rf_segment_reset_count_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_radio_mcu_act_temperature_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_rf_chip_act_temperature_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_rf_power_amplifier_act_temperature_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_digipeater_forwarded_message_count_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_last_digipeater_user_sender_s_callsign
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_rx_data_packets_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_tx_data_packets_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_actual_rssi_raw
            type: str
            terminator: 0x2C
            encoding: utf8
          - id: vhf_value_of_rssi_when_carrier_detected_raw
            type: str
            terminator: 0x00
            encoding: utf8

        instances:
          vhf_uptime_since_reset:
            value: vhf_uptime_since_reset_raw.to_i
          vhf_uptime_total:
            value: vhf_uptime_total_raw.to_i
          vhf_radio_boot_count:
            value: vhf_radio_boot_count_raw.to_i
          vhf_rf_segment_reset_count:
            value: vhf_rf_segment_reset_count_raw.to_i
          vhf_radio_mcu_act_temperature:
            value: vhf_radio_mcu_act_temperature_raw.to_i
          vhf_rf_chip_act_temperature:
            value: vhf_rf_chip_act_temperature_raw.to_i
          vhf_rf_power_amplifier_act_temperature:
            value: vhf_rf_power_amplifier_act_temperature_raw.to_i
          vhf_digipeater_forwarded_message_count:
            value: vhf_digipeater_forwarded_message_count_raw.to_i
          vhf_rx_data_packets:
            value: vhf_rx_data_packets_raw.to_i
          vhf_tx_data_packets:
            value: vhf_tx_data_packets_raw.to_i
          vhf_actual_rssi:
            value: vhf_actual_rssi_raw.to_i
          vhf_value_of_rssi_when_carrier_detected:
            value: vhf_value_of_rssi_when_carrier_detected_raw.to_i
    
# checking for Message
  not_beacon:
    seq:
      - id: id5
        type:
          switch-on: message_type4
          cases:
            0x846103f0: msg # (HA2GR)B + ssid mask + ctl + pid
            _: not_message

    instances:
      message_type4:
        type: u4
        pos: 12

  msg:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: message
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
      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x1f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

# checking for CSP packets such as PSU HK
  not_message:

    seq:
      - id: csp_header
        type: csp_header_t
      - id: csp_data
        type: csp_data_t
    
    types:
      csp_header_t:
        seq:
          - id: csp_header_raw
            type: u4
        instances:
          priority:
            value: '(csp_header_raw >> 30)'
          source:
            value: '((csp_header_raw >> 25) & 0x1F)'
          destination:
            value: '((csp_header_raw >> 20) & 0x1F)'
          destination_port:
            value: '((csp_header_raw >> 14) & 0x3F)'
          source_port:
            value: '((csp_header_raw >> 8) & 0x3F)'
          reserved:
            value: '((csp_header_raw >> 4) & 0x0F)'
          hmac:
            value: '((csp_header_raw & 0x08) >> 3)'
          xtea:
            value: '((csp_header_raw & 0x04) >> 2)'
          rdp:
            value: '((csp_header_raw & 0x02) >> 1)'
          crc:
            value: '(csp_header_raw & 0x01)'
    
      csp_data_t:
        seq:
          - id: telemetry
            type: psu_hk_t
            if: (_parent.csp_header.source == 2) and (_parent.csp_header.source_port == 9)
    
      # beacon
      psu_hk_t:
        meta:
          endian: le  # Little-endian for this field
        seq:
          - id: utc_time_stamp_rtc
            type: u4
            doc: "Time epoch, seconds since 1970 (NMEA: RMC + PPS 1Hz)"
          - id: uptime_rst
            type: u4
            doc: "Uptime since last reset"
          - id: uptime_tot
            type: u4
            doc: "Total uptime"
          - id: reset_cnt
            type: u4
            doc: "Count of all MCU resets (nonvolatile)"
          - id: last_rst_src
            type: u2
            doc: "Source of last reset"
          - id: packets_recvd_cnt
            type: u4
            doc: "Count of all packets received (nonvolatile)"
          - id: psu_error_count
            type: u4
            doc: "Number of errors experienced"
        
          # Photovoltaic panels parameters
          - id: pv_in_volt1
            type: u2
            doc: "Voltage on PV input 1 (Volts)"
          - id: pv_in_volt2
            type: u2
            doc: "Voltage on PV input 2 (Volts)"
          - id: pv_in_volt3
            type: u2
            doc: "Voltage on PV input 3 (Volts)"
          - id: pv_in_amp1
            type: u2
            doc: "Current on PV input 1 (Amperes)"
          - id: pv_in_amp2
            type: u2
            doc: "Current on PV input 2 (Amperes)"
          - id: pv_in_amp3
            type: u2
            doc: "Current on PV input 3 (Amperes)"
          - id: pv_in_power1
            type: u2
            doc: "Power on PV input 1 (Watts)"
          - id: pv_in_power2
            type: u2
            doc: "Power on PV input 2 (Watts)"
          - id: pv_in_power3
            type: u2
            doc: "Power on PV input 3 (Watts)"
          - id: ppt_mode
            type: u1
            doc: "Current PPT mode (1<<0 MPPT1 ON, 1<<1 MPPT2 ON, 1<<2 MPPT3 ON)"
          - id: channel_status
            type: u1
            doc: "Bit-masked status of channels 1-6, unregulated"
          - id: system_state
            type: u1
            doc: "Power system state"
        
          # Output current in different power branches
          - id: out_sys_ch_amp1
            type: u2
            doc: "Output current channel 1"
          - id: out_sys_ch_amp2
            type: u2
            doc: "Output current channel 2"
          - id: out_sys_ch_amp3
            type: u2
            doc: "Output current channel 3"
          - id: out_sys_ch_amp4
            type: u2
            doc: "Output current channel 4"
          - id: out_sys_ch_amp5
            type: u2
            doc: "Output current channel 5"
          - id: out_sys_ch_amp6
            type: u2
            doc: "Output current channel 6"
          - id: out_sys_bat_unreg_amp
            type: u2
            doc: "Output current unregulated battery channel"
        
          # Battery and system measurements
          - id: bat_volt
            type: u2
            doc: "Battery voltage"
          - id: bat_amp_charge
            type: u2
            doc: "Battery charge current"
          - id: bat_amp_discharge
            type: u2
            doc: "Battery discharge current"
          - id: bat_temp_kelvin
            type: u2
            doc: "Battery temperature in Kelvin"
          - id: system_temp_kelvin
            type: u2
            doc: "System temperature in Kelvin"
        instances:
          channel_0_status:
            value: (channel_status >> 0 ) & 0x01
          channel_1_status:
            value: (channel_status >> 1 ) & 0x01
          channel_2_status:
            value: (channel_status >> 2 ) & 0x01
          channel_3_status:
            value: (channel_status >> 3 ) & 0x01
          channel_4_status:
            value: (channel_status >> 4 ) & 0x01
          channel_5_status:
            value: (channel_status >> 5 ) & 0x01
          channel_6_status:
            value: (channel_status >> 6 ) & 0x01

          mppt_ch1_state:
            value: (ppt_mode >> 0 ) & 0x01
          mppt_ch2_state:
            value: (ppt_mode >> 1 ) & 0x01
          mppt_ch3_state:
            value: (ppt_mode >> 2 ) & 0x01

