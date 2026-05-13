---
meta:
  id: enso
  endian: le
doc: |
  :field callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field ssid_mask: ax25_frame.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid_raw_ssid_mask: ax25_frame.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field repeater_rpt_instance_rpt_callsign_raw_callsign: ax25_frame.ax25_header.repeater.rpt_instance.rpt_callsign_raw.callsign_ror.callsign
  :field repeater_rpt_instance_rpt_ssid_raw_ssid_mask: ax25_frame.ax25_header.repeater.rpt_instance.rpt_ssid_raw.ssid_mask
  :field repeater_rpt_instance_rpt_ssid_raw_ssid: ax25_frame.ax25_header.repeater.rpt_instance.rpt_ssid_raw.ssid
  :field ctl: ax25_frame.ax25_header.ctl
  :field pid: ax25_frame.payload.pid
  :field length: ax25_frame.payload.ax25_info.length
  :field frame_type: ax25_frame.payload.ax25_info.frame_type
  :field var_ts: ax25_frame.payload.ax25_info.var_ts
  :field obdh_timestamp: ax25_frame.payload.ax25_info.obdh_timestamp
  :field sat_mode: ax25_frame.payload.ax25_info.sat_mode
  :field obdh_mode: ax25_frame.payload.ax25_info.obdh_mode
  :field obdh_nb_bytes_to_transmit: ax25_frame.payload.ax25_info.obdh_nb_bytes_to_transmit
  :field obdh_nb_of_obdh_resets: ax25_frame.payload.ax25_info.obdh_nb_of_obdh_resets
  :field obdh_nb_of_errors: ax25_frame.payload.ax25_info.obdh_nb_of_errors
  :field eps_eps_mode: ax25_frame.payload.ax25_info.eps_eps_mode
  :field eps_bat_temp: ax25_frame.payload.ax25_info.eps_bat_temp
  :field eps_temp_z_minus: ax25_frame.payload.ax25_info.eps_temp_z_minus
  :field eps_obdh_cur: ax25_frame.payload.ax25_info.eps_obdh_cur
  :field eps_eps_cur: ax25_frame.payload.ax25_info.eps_eps_cur
  :field eps_ttc_micro_cur: ax25_frame.payload.ax25_info.eps_ttc_micro_cur
  :field eps_temp_x_plus: ax25_frame.payload.ax25_info.eps_temp_x_plus
  :field eps_temp_x_minus: ax25_frame.payload.ax25_info.eps_temp_x_minus
  :field eps_temp_y_plus: ax25_frame.payload.ax25_info.eps_temp_y_plus
  :field eps_temp_y_minus: ax25_frame.payload.ax25_info.eps_temp_y_minus
  :field eps_temp_z_plus: ax25_frame.payload.ax25_info.eps_temp_z_plus
  :field eps_temp_5v_reg: ax25_frame.payload.ax25_info.eps_temp_5v_reg
  :field eps_temp_6v_reg: ax25_frame.payload.ax25_info.eps_temp_6v_reg
  :field ttc_mode: ax25_frame.payload.ax25_info.ttc_mode
  :field ttc_resets: ax25_frame.payload.ax25_info.ttc_resets
  :field ttc_last_reset_cause: ax25_frame.payload.ax25_info.ttc_last_reset_cause
  :field ttc_total_valid_rcv_packets: ax25_frame.payload.ax25_info.ttc_total_valid_rcv_packets
  :field ttc_tx_packets: ax25_frame.payload.ax25_info.ttc_tx_packets
  :field ttc_power_fw_val: ax25_frame.payload.ax25_info.ttc_power_fw_val
  :field ttc_power_rev_val: ax25_frame.payload.ax25_info.ttc_power_rev_val
  :field ttc_last_err_code: ax25_frame.payload.ax25_info.ttc_last_err_code
  :field ttc_pwr_config: ax25_frame.payload.ax25_info.ttc_pwr_config
  :field ttc_pwr_amp_temp: ax25_frame.payload.ax25_info.ttc_pwr_amp_temp
  :field ttc_beacon_period: ax25_frame.payload.ax25_info.ttc_beacon_period
  :field tweet: ax25_frame.payload.ax25_info.tweet
  :field eps_bat_volt_val: ax25_frame.payload.ax25_info.eps_bat_volt_val
  :field eps_bat_volt_min_val: ax25_frame.payload.ax25_info.eps_bat_volt_min_val
  :field eps_bat_volt_max_val: ax25_frame.payload.ax25_info.eps_bat_volt_max_val
  :field eps_bat_volt_avg_val: ax25_frame.payload.ax25_info.eps_bat_volt_avg_val
  :field eps_avg_charge_cur_val: ax25_frame.payload.ax25_info.eps_avg_charge_cur_val
  :field eps_max_charge_cur_val: ax25_frame.payload.ax25_info.eps_max_charge_cur_val
  :field eps_ttc_tx_cur_val: ax25_frame.payload.ax25_info.eps_ttc_tx_cur_val
  :field eps_ttc_tx_cur_max_val: ax25_frame.payload.ax25_info.eps_ttc_tx_cur_max_val
  :field eps_pl_cur_val: ax25_frame.payload.ax25_info.eps_pl_cur_val
  :field eps_obdh_volt_val: ax25_frame.payload.ax25_info.eps_obdh_volt_val
  :field eps_ttc_volt_val: ax25_frame.payload.ax25_info.eps_ttc_volt_val
  :field eps_pl_volt_val: ax25_frame.payload.ax25_info.eps_pl_volt_val
  :field eps_mos1_volt_val: ax25_frame.payload.ax25_info.eps_mos1_volt_val
  :field eps_mos2_volt_val: ax25_frame.payload.ax25_info.eps_mos2_volt_val
  :field eps_mos3_volt_val: ax25_frame.payload.ax25_info.eps_mos3_volt_val
  :field eps_ref_volt_val: ax25_frame.payload.ax25_info.eps_ref_volt_val
  :field eps_ttc_mcu_volt_val: ax25_frame.payload.ax25_info.eps_ttc_mcu_volt_val
  :field ttc_rssi_last_packet_val: ax25_frame.payload.ax25_info.ttc_rssi_last_packet_val
  :field ttc_freq_dev_last_packet_val: ax25_frame.payload.ax25_info.ttc_freq_dev_last_packet_val
  :field temperature_val: ax25_frame.payload.ax25_info.temperature_val
  :field eps_charge_cur_val: ax25_frame.payload.ax25_info.eps_charge_cur_val
  :field payload: ax25_frame.payload.ax25_info.payload.payload_raw

seq:
  - id: ax25_frame
    type: ax25_frame
    doc-ref: 'https://www.tapr.org/pub_ax25.html'

types:
  ax25_frame:
    seq:
      - id: ax25_header
        type: ax25_header
      - id: payload
        type:
          switch-on: ax25_header.ctl & 0x13
          cases:
            0x03: ui_frame
            0x13: ui_frame
            0x00: i_frame
            0x02: i_frame
            0x10: i_frame
            0x12: i_frame
            # 0x11: s_frame

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
        valid:
          any-of:
            - '"F4KJX "'
            - '"FX6FRC"'

  ssid_mask:
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x0f) >> 1

  i_frame:
    seq:
      - id: pid
        type: u1
      - id: ax25_info
        type: ax25_info_data
        size-eos: true

  ui_frame:
    seq:
      - id: pid
        type: u1
      - id: ax25_info
        type: ax25_info_data
        size-eos: true

  payload_t:
    seq:
      - id: payload_raw
        type: str
        size: 48
        encoding: ASCII

  ax25_info_data:
    seq:
      - id: length
        type: u1
      - id: frame_type
        type: u1
        valid: 0x10
      - id: var_ts
        type: u4
      - id: obdh_timestamp
        type: u4
      - id: temperature
        type: u2
        doc: |
          if >= 4095 temperature is an unsigned int
          else temperature is a 13 bits signed int (8192 = 2^13)
          unit : Celsius
      - id: sat_mode
        type: u1
        doc: |
          Satellite Mode:
          0x00: STANDBY
          0x01: DEPLOY
          0x02: COMMISSIONNING
          0x03: COMM_PL
          0x04: MISSION
          0x05: LOW_P_MISSION
          0x06: TRANSMIT
          0x07: SURVIVAL
          0x08: SILENT
      - id: obdh_mode
        type: u1
        doc: |
          Mode of the OBDH subsystem:
          0x11: STANDBY
          0x22: DEPLOY
          0x33: COMMISSIONNING
          0x44: COMM_PL
          0x55: MISSION
          0x66: LOW_POWER_MISSION
          0x77: SILENT
          0xFF: POR
      - id: obdh_nb_bytes_to_transmit
        type: u4
      - id: obdh_nb_of_obdh_resets
        type: u2
      - id: obdh_nb_of_errors
        type: u2
      - id: eps_eps_mode
        type: u1
        doc: |
          Mode of the EPS subsystem:
          0x00: IDLE
          0x11: SURVIVAL
          0x22: STANDBY
          0x33: DEPLOY
          0x44: COMMISSIONNING
          0x55: MISSION
          0x66: LOW_POWER_MISSION
          0x77: SILENT
      - id: eps_bat_volt
        type: u1
        doc: 'mV'
      - id: eps_bat_temp
        type: s1
        doc: 'Celsius'
      - id: eps_bat_volt_min
        type: u1
        doc: 'mV'
      - id: eps_bat_volt_max
        type: u1
        doc: 'mV'
      - id: eps_bat_volt_avg
        type: u1
        doc: 'mV'
      - id: eps_avg_charge_cur
        type: u1
        doc: 'mA'
      - id: eps_max_charge_cur
        type: u1
        doc: 'mA'
      - id: eps_temp_z_minus
        type: s1
        doc: 'Celsius'
      - id: eps_obdh_cur
        type: u1
        doc: 'mA'
      - id: eps_eps_cur
        type: u1
        doc: 'mA'
      - id: eps_ttc_micro_cur
        type: u1
        doc: 'mA'
      - id: eps_ttc_tx_cur
        type: u1
        doc: 'mA'
      - id: eps_ttc_tx_cur_max
        type: u1
        doc: 'mA'
      - id: eps_pl_cur
        type: u1
        doc: 'mA'
      - id: eps_charge_cur
        type: u1
        doc: 'mA'
      - id: eps_temp_x_plus
        type: s1
      - id: eps_temp_x_minus
        type: s1
      - id: eps_temp_y_plus
        type: s1
      - id: eps_temp_y_minus
        type: s1
      - id: eps_temp_z_plus
        type: s1
      - id: eps_obdh_volt
        type: u1
        doc: 'mV'
      - id: eps_ttc_volt
        type: u1
        doc: 'mV'
      - id: eps_pl_volt
        type: u1
        doc: 'mV'
      - id: eps_mos1_volt
        type: u1
        doc: 'mV'
      - id: eps_mos2_volt
        type: u1
        doc: 'mV'
      - id: eps_mos3_volt
        type: u1
        doc: 'mV'
      - id: eps_ref_volt
        type: u2
        doc: 'mV'
      - id: eps_temp_5v_reg
        type: s1
      - id: eps_temp_6v_reg
        type: s1
      - id: eps_ttc_mcu_volt
        type: u1
        doc: 'mV'
      - id: ttc_mode
        type: u1
        doc: |
          Mode of the TTC subsystem:
          0x01: IDLE
          0x11: BEACON
          0x22: COMMISSIONNING
          0x44: SILENT
      - id: ttc_resets
        type: u2
      - id: ttc_last_reset_cause
        type: u1
        doc: |
          Cause of the last TTC reset:
          0x11: POR (Power supply reset)
          0x22: WDTTO (Watchdog)
          0x33: OSC (Oscillator Error)
          0x44: HW (Reset Pin)
          0x55: DEBUG (Debugger Reset)
          0x77: RI (Software Reset)
      - id: ttc_total_valid_rcv_packets
        type: u2
      - id: ttc_tx_packets
        type: u2
      - id: ttc_power_fw
        type: u1
      - id: ttc_power_rev
        type: u1
      - id: ttc_last_err_code
        type: u1
        doc: |
          Cause of the last error in the TTC:
          0x00: NULL
          0x11: RADIO_HW_ERROR
          0x22: TX_QUEUE_FULL
          0x33: RX_QUEUE_FULL
          0x44: TX_BUS_QUEUE_FULL
          0x55: RX_BUS_QUEUE_FULL
          0x66: OBC_TEMP_HW_ERROR
          0x77: OBC_TEMP_H_LIMIT_ERROR
          0x88: OBC_TEMP_L_LIMIT_ERROR
          0x99: PA_TEMP_HW_ERROR
          0xAA: PA_TEMP_H_LIMIT_ERROR
          0xBB: PA_TEMP_L_LIMIT_ERROR
          0xCC: OBDH_NACK
          0xDD: PF_RESET_REQ
          0xD1: TTC_RESET_REQ
          0xEE: RADIO_TASK_TIMEOUT
          0xFF: RADIO_UNQUEUE
          0x01: OBDH_STATUS_REQ
          0x02: OBDH_BDR_REQ
          0xA1: FRAM_ID_ERROR
          0xA2: FRAM_HW_ERROR
          0xA3: FRAM_READ_ERROR
          0xA4: FRAM_WRITE_ERROR
          0xA5: EVENT_QUEUE_READ_ERROR
      - id: ttc_pwr_config
        type: u1
      - id: ttc_pwr_amp_temp
        type: s1
        doc: 'Celsius'
      - id: ttc_rssi_last_packet
        type: u1
        doc: 'dBm'
      - id: ttc_freq_dev_last_packet
        type: s1
        doc: 'Hz'
      - id: ttc_beacon_period
        type: u1
        doc: 'seconds'
      - id: payload
        process: satnogsdecoders.process.hexl
        type: payload_t
        size: 48
      - id: tweet
        type: str
        encoding: utf-8
        size-eos: true
    
    instances:
      eps_bat_volt_val:
        value: eps_bat_volt * 20
      eps_bat_volt_min_val:
        value: eps_bat_volt_min * 20
      eps_bat_volt_max_val:
        value: eps_bat_volt_max * 20
      eps_bat_volt_avg_val:
        value: eps_bat_volt_avg * 20
      eps_avg_charge_cur_val:
        value: eps_avg_charge_cur * 12
      eps_max_charge_cur_val:
        value: eps_max_charge_cur * 12
      eps_ttc_tx_cur_val:
        value: eps_ttc_tx_cur * 5
      eps_ttc_tx_cur_max_val:
        value: eps_ttc_tx_cur_max * 5
      eps_pl_cur_val:
        value: eps_pl_cur * 5
      eps_obdh_volt_val:
        value: (eps_obdh_volt * 10) + 4000
      eps_ttc_volt_val:
        value: (eps_ttc_volt * 10) + 4000
      eps_pl_volt_val:
        value: (eps_pl_volt * 10) + 4000
      eps_mos1_volt_val:
        value: (eps_mos1_volt + 2200) * 0.805
      eps_mos2_volt_val:
        value: (eps_mos2_volt + 2200) * 0.805
      eps_mos3_volt_val:
        value: (eps_mos3_volt + 2200) * 0.805
      eps_ref_volt_val:
        value: eps_ref_volt * 0.805
      eps_ttc_mcu_volt_val:
        value: (eps_ttc_mcu_volt * 10) + 4000
      ttc_rssi_last_packet_val:
        value: (ttc_rssi_last_packet * -1)
      ttc_freq_dev_last_packet_val:
        value: (ttc_freq_dev_last_packet * 17)
      eps_charge_cur_val:
        value: eps_charge_cur * 12
      temperature_val:
        value: 'temperature <= 4095 ? (temperature * 0.0625) : (temperature - 8192) * 0.0625'
      ttc_power_fw_val:
        value: ttc_power_fw * 10
      ttc_power_rev_val:
        value: ttc_power_rev * 10
