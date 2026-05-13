meta:
  id: cp16
  endian: be
  
doc: |
  :field cp16_dest_callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field cp16_dest_ssid_mask: ax25_frame.ax25_header.dest_ssid_raw.ssid_mask
  :field cp16_dest_ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field cp16_src_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field cp16_src_ssid_mask: ax25_frame.ax25_header.src_ssid_raw.ssid_mask
  :field cp16_src_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field cp16_ctl: ax25_frame.ax25_header.ctl
  :field cp16_pid: ax25_frame.payload.pid
  :field cp16_daughter_a_temp: ax25_frame.payload.ax25_info.contents.various_temp.daughter_a_temp
  :field cp16_payload_3v3_temp: ax25_frame.payload.ax25_info.contents.various_temp.payload_3v3_temp
  :field cp16_rf_amp_temp: ax25_frame.payload.ax25_info.contents.various_temp.rf_amp_temp
  :field cp16_atmel_pwr_curr: ax25_frame.payload.ax25_info.contents.various_power.atmel_pwr_curr
  :field cp16_atmel_pwr_volt: ax25_frame.payload.ax25_info.contents.various_power.atmel_pwr_volt
  :field cp16_bus_3v3_curr: ax25_frame.payload.ax25_info.contents.various_power.bus_3v3_curr
  :field cp16_bus_3v3_volt: ax25_frame.payload.ax25_info.contents.various_power.bus_3v3_volt
  :field cp16_payload_3v3_curr: ax25_frame.payload.ax25_info.contents.various_power.payload_3v3_curr
  :field cp16_payload_3v3_volt: ax25_frame.payload.ax25_info.contents.various_power.payload_3v3_volt
  :field cp16_payload_5v0_curr: ax25_frame.payload.ax25_info.contents.various_power.payload_5v0_curr
  :field cp16_payload_5v0_volt: ax25_frame.payload.ax25_info.contents.various_power.payload_5v0_volt
  :field cp16_rf_amp_curr: ax25_frame.payload.ax25_info.contents.various_power.rf_amp_curr
  :field cp16_rf_amp_volt: ax25_frame.payload.ax25_info.contents.various_power.rf_amp_volt
  :field cp16_neg_x_solar1_volt: ax25_frame.payload.ax25_info.contents.neg_x.solar1_volt
  :field cp16_neg_x_solar1_curr: ax25_frame.payload.ax25_info.contents.neg_x.solar1_curr
  :field cp16_neg_x_solar2_volt: ax25_frame.payload.ax25_info.contents.neg_x.solar2_volt
  :field cp16_neg_x_solar2_curr: ax25_frame.payload.ax25_info.contents.neg_x.solar2_curr
  :field cp16_neg_x_solar3_volt: ax25_frame.payload.ax25_info.contents.neg_x.solar3_volt
  :field cp16_neg_x_solar3_curr: ax25_frame.payload.ax25_info.contents.neg_x.solar3_curr
  :field cp16_neg_x_side_temp: ax25_frame.payload.ax25_info.contents.neg_x.side_temp
  :field cp16_pos_x_solar1_volt: ax25_frame.payload.ax25_info.contents.pos_x.solar1_volt
  :field cp16_pos_x_solar1_curr: ax25_frame.payload.ax25_info.contents.pos_x.solar1_curr
  :field cp16_pos_x_solar2_volt: ax25_frame.payload.ax25_info.contents.pos_x.solar2_volt
  :field cp16_pos_x_solar2_curr: ax25_frame.payload.ax25_info.contents.pos_x.solar2_curr
  :field cp16_pos_x_solar3_volt: ax25_frame.payload.ax25_info.contents.pos_x.solar3_volt
  :field cp16_pos_x_solar3_curr: ax25_frame.payload.ax25_info.contents.pos_x.solar3_curr
  :field cp16_pos_x_side_temp: ax25_frame.payload.ax25_info.contents.pos_x.side_temp
  :field cp16_neg_y_solar1_volt: ax25_frame.payload.ax25_info.contents.neg_y.solar1_volt
  :field cp16_neg_y_solar1_curr: ax25_frame.payload.ax25_info.contents.neg_y.solar1_curr
  :field cp16_neg_y_solar2_volt: ax25_frame.payload.ax25_info.contents.neg_y.solar2_volt
  :field cp16_neg_y_solar2_curr: ax25_frame.payload.ax25_info.contents.neg_y.solar2_curr
  :field cp16_neg_y_solar3_volt: ax25_frame.payload.ax25_info.contents.neg_y.solar3_volt
  :field cp16_neg_y_solar3_curr: ax25_frame.payload.ax25_info.contents.neg_y.solar3_curr
  :field cp16_neg_y_side_temp: ax25_frame.payload.ax25_info.contents.neg_y.side_temp
  :field cp16_pos_y_solar1_volt: ax25_frame.payload.ax25_info.contents.pos_y.solar1_volt
  :field cp16_pos_y_solar1_curr: ax25_frame.payload.ax25_info.contents.pos_y.solar1_curr
  :field cp16_pos_y_solar2_volt: ax25_frame.payload.ax25_info.contents.pos_y.solar2_volt
  :field cp16_pos_y_solar2_curr: ax25_frame.payload.ax25_info.contents.pos_y.solar2_curr
  :field cp16_pos_y_solar3_volt: ax25_frame.payload.ax25_info.contents.pos_y.solar3_volt
  :field cp16_pos_y_solar3_curr: ax25_frame.payload.ax25_info.contents.pos_y.solar3_curr
  :field cp16_pos_y_side_temp: ax25_frame.payload.ax25_info.contents.pos_y.side_temp
  :field cp16_neg_z_temp: ax25_frame.payload.ax25_info.contents.neg_z_temp
  :field cp16_user_cpu_time: ax25_frame.payload.ax25_info.contents.flight_software_telem.user_cpu_time
  :field cp16_nice_cpu_time: ax25_frame.payload.ax25_info.contents.flight_software_telem.nice_cpu_time
  :field cp16_sys_cpu_time: ax25_frame.payload.ax25_info.contents.flight_software_telem.sys_cpu_time
  :field cp16_idle_cpu_time: ax25_frame.payload.ax25_info.contents.flight_software_telem.idle_cpu_time
  :field cp16_processes: ax25_frame.payload.ax25_info.contents.flight_software_telem.processes
  :field cp16_procs_running: ax25_frame.payload.ax25_info.contents.flight_software_telem.procs_running
  :field cp16_procs_blocked: ax25_frame.payload.ax25_info.contents.flight_software_telem.procs_blocked
  :field cp16_mem_free: ax25_frame.payload.ax25_info.contents.flight_software_telem.mem_free
  :field cp16_mem_buffered: ax25_frame.payload.ax25_info.contents.flight_software_telem.mem_buffered
  :field cp16_mem_cached: ax25_frame.payload.ax25_info.contents.flight_software_telem.mem_cached
  :field cp16_vmalloc_total: ax25_frame.payload.ax25_info.contents.flight_software_telem.vmalloc_total
  :field cp16_vmalloc_used: ax25_frame.payload.ax25_info.contents.flight_software_telem.vmalloc_used
  :field cp16_dir_data_free_is_kb: ax25_frame.payload.ax25_info.contents.flight_software_telem.dir_data_free.is_kb
  :field cp16_dir_data_free_value: ax25_frame.payload.ax25_info.contents.flight_software_telem.dir_data_free.value
  :field cp16_dir_sdcard_free_is_kb: ax25_frame.payload.ax25_info.contents.flight_software_telem.dir_sdcard_free.is_kb
  :field cp16_dir_sdcard_free_value: ax25_frame.payload.ax25_info.contents.flight_software_telem.dir_sdcard_free.value
  :field cp16_lo_bytes: ax25_frame.payload.ax25_info.contents.flight_software_telem.lo_bytes
  :field cp16_lo_packets: ax25_frame.payload.ax25_info.contents.flight_software_telem.lo_packets
  :field cp16_nand_erasures: ax25_frame.payload.ax25_info.contents.flight_software_telem.nand_erasures
  :field cp16_load_1min: ax25_frame.payload.ax25_info.contents.flight_software_telem.load_1min
  :field cp16_load_5min: ax25_frame.payload.ax25_info.contents.flight_software_telem.load_5min
  :field cp16_load_15min: ax25_frame.payload.ax25_info.contents.flight_software_telem.load_15min
  :field cp16_beacon_count: ax25_frame.payload.ax25_info.contents.flight_software_telem.beacon_count
  :field cp16_rtc: ax25_frame.payload.ax25_info.contents.flight_software_telem.rtc
  :field cp16_boot_time: ax25_frame.payload.ax25_info.contents.flight_software_telem.boot_time
  :field cp16_long_dur_counter: ax25_frame.payload.ax25_info.contents.flight_software_telem.long_dur_counter
  :field cp16_rx_packets_raw: ax25_frame.payload.ax25_info.contents.comms_parameters.rx_packets_raw
  :field cp16_tx_packets_raw: ax25_frame.payload.ax25_info.contents.comms_parameters.tx_packets_raw
  :field cp16_rx_bytes_raw: ax25_frame.payload.ax25_info.contents.comms_parameters.rx_bytes_raw
  :field cp16_tx_bytes_raw: ax25_frame.payload.ax25_info.contents.comms_parameters.tx_bytes_raw
  :field cp16_comms_parameters_callsign0_callsign: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign0.callsign
  :field cp16_comms_parameters_callsign0_ssid_char_raw: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign0.ssid_char_raw
  :field cp16_comms_parameters_callsign0_last_rx: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign0.last_rx
  :field cp16_comms_parameters_callsign0_ssid_num: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign0.ssid_num
  :field cp16_comms_parameters_callsign1_callsign: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign1.callsign
  :field cp16_comms_parameters_callsign1_ssid_char_raw: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign1.ssid_char_raw
  :field cp16_comms_parameters_callsign1_last_rx: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign1.last_rx
  :field cp16_comms_parameters_callsign1_ssid_num: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign1.ssid_num
  :field cp16_comms_parameters_callsign2_callsign: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign2.callsign
  :field cp16_comms_parameters_callsign2_ssid_char_raw: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign2.ssid_char_raw
  :field cp16_comms_parameters_callsign2_last_rx: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign2.last_rx
  :field cp16_comms_parameters_callsign2_ssid_num: ax25_frame.payload.ax25_info.contents.comms_parameters.callsign2.ssid_num
  :field cp16_rx_packets: ax25_frame.payload.ax25_info.contents.comms_parameters.rx_packets
  :field cp16_tx_packets: ax25_frame.payload.ax25_info.contents.comms_parameters.tx_packets
  :field cp16_rx_bytes: ax25_frame.payload.ax25_info.contents.comms_parameters.rx_bytes
  :field cp16_tx_bytes: ax25_frame.payload.ax25_info.contents.comms_parameters.tx_bytes
  :field cp16_carp_b_3v3_volt: ax25_frame.payload.ax25_info.contents.carp.carp_b_3v3_volt
  :field cp16_carp_b_3v3_curr: ax25_frame.payload.ax25_info.contents.carp.carp_b_3v3_curr
  :field cp16_carp_b_1v8_volt: ax25_frame.payload.ax25_info.contents.carp.carp_b_1v8_volt
  :field cp16_carp_b_1v8_curr: ax25_frame.payload.ax25_info.contents.carp.carp_b_1v8_curr
  :field cp16_carp_b_event_count: ax25_frame.payload.ax25_info.contents.carp.carp_b_event_count
  :field cp16_carp_b_latch_count: ax25_frame.payload.ax25_info.contents.carp.carp_b_latch_count
  :field cp16_pib_temp_intern: ax25_frame.payload.ax25_info.contents.carp.pib_temp_intern
  :field cp16_pib_temp_extern: ax25_frame.payload.ax25_info.contents.carp.pib_temp_extern
  :field cp16_owl_latest_radio_cfg: ax25_frame.payload.ax25_info.contents.owl.owl_latest_radio_cfg
  :field cp16_owl_last_rx_action_cmd: ax25_frame.payload.ax25_info.contents.owl.owl_last_rx_action_cmd
  :field cp16_owl_rssi_latest: ax25_frame.payload.ax25_info.contents.owl.owl_rssi_latest
  :field cp16_owl_snr_latest: ax25_frame.payload.ax25_info.contents.owl.owl_snr_latest
  :field cp16_owl_var_byte1: ax25_frame.payload.ax25_info.contents.owl.owl_var_byte1
  :field cp16_owl_var_byte2: ax25_frame.payload.ax25_info.contents.owl.owl_var_byte2
  :field cp16_owl_var_byte3: ax25_frame.payload.ax25_info.contents.owl.owl_var_byte3
  :field cp16_owl_var_byte4: ax25_frame.payload.ax25_info.contents.owl.owl_var_byte4
  :field cp16_accel_x: ax25_frame.payload.ax25_info.contents.imu_data.accel_x
  :field cp16_accel_y: ax25_frame.payload.ax25_info.contents.imu_data.accel_y
  :field cp16_accel_z: ax25_frame.payload.ax25_info.contents.imu_data.accel_z
  :field cp16_gyro_x: ax25_frame.payload.ax25_info.contents.imu_data.gyro_x
  :field cp16_gyro_y: ax25_frame.payload.ax25_info.contents.imu_data.gyro_y
  :field cp16_gyro_z: ax25_frame.payload.ax25_info.contents.imu_data.gyro_z
  :field cp16_mag_x: ax25_frame.payload.ax25_info.contents.imu_data.mag_x
  :field cp16_mag_y: ax25_frame.payload.ax25_info.contents.imu_data.mag_y
  :field cp16_mag_z: ax25_frame.payload.ax25_info.contents.imu_data.mag_z
  :field cp16_picture_count: ax25_frame.payload.ax25_info.contents.camera.picture_count
  :field cp16_thumbnail_count: ax25_frame.payload.ax25_info.contents.camera.thumbnail_count

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
          #0x11: s_frame

  ax25_header:
    seq:
      - id: dest_callsign_raw
        type: callsign_raw
      - id: dest_ssid_raw
        type: ssid_mask
      - id: src_callsign_raw
        type: callsign_raw
        valid:
          expr: _.callsign_ror.callsign == "KK6HIT"
      - id: src_ssid_raw
        type: ssid_mask
        valid:
          expr: _.ssid == 6
      - id: repeater
        type: repeater
        if: (src_ssid_raw.ssid_mask & 0x01) == 0
      - id: ctl
        type: u1
        
  repeater:
    seq:
    - id: rpt_instance
      type: repeaters
      repeat: until
      repeat-until: ((_.rpt_ssid_raw.ssid_mask & 0x01) == 0x01)

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
        value: (ssid_mask >> 1) & 0x0f

  i_frame:
    seq:
      - id: pid
        type: u1
      - id: ax25_info
        size-eos: true

  ui_frame:
    seq:
      - id: pid
        type: u1
        valid:
          eq: 0xCC
      - id: ax25_info
        type: ipv4_packet
  
  ipv4_packet:
    seq:
    - id: ipv4_and_udp_header
      size: 29
    - id: contents
      type: cp16_data

  cp16_data:
    seq:
      - id: various_temp
        type: various_temp_vals
      - id: various_power
        type: various_power_vals
      - id: neg_x
        type: side_panel_vals
      - id: pos_x
        type: side_panel_vals
      - id: neg_y
        doc: incorrectly populated solar cell 3 volt and curr, should be ignored
        type: side_panel_vals
      - id: pos_y
        type: side_panel_vals
      - id: neg_z_temp
        type: u1
      - id: flight_software_telem
        type: flight_software_telem_vals
      - id: comms_parameters
        type: comms_parameters_vals
      - id: carp
        type: carp_vals
      - id: owl
        type: owl_vals
      - id: imu_data
        type: imu_data_vals
      - id: camera
        type: camera_vals
        
  various_temp_vals:
    seq:
      - id: daughter_a_temp
        type: u1
      - id: payload_3v3_temp
        type: u1  
      - id: rf_amp_temp
        type: u1
        
  various_power_vals:
    seq:
    - id: atmel_pwr_curr
      type: u1
    - id: atmel_pwr_volt
      type: u1  
    - id: bus_3v3_curr
      type: u1
    - id: bus_3v3_volt
      type: u1
    - id: payload_3v3_curr
      type: u1
    - id: payload_3v3_volt
      type: u1  
    - id: payload_5v0_curr
      type: u1
    - id: payload_5v0_volt
      type: u1
    - id: rf_amp_curr
      type: u1
    - id: rf_amp_volt
      type: u1
      
  side_panel_vals:
    seq:
    - id: solar1_volt
      type: u1
    - id: solar1_curr
      type: s1
    - id: solar2_volt
      type: u1    
    - id: solar2_curr
      type: s1    
    - id: solar3_volt
      type: u1     
    - id: solar3_curr
      type: s1     
    - id: side_temp
      type: u1     
      
  flight_software_telem_vals:
    seq:
    - id: user_cpu_time
      type: u4
    - id: nice_cpu_time
      type: u4
    - id: sys_cpu_time
      type: u4
    - id: idle_cpu_time
      type: u4
    - id: processes
      type: u2
    - id: procs_running
      type: u2
    - id: procs_blocked
      type: u2
    - id: mem_free
      type: u4
    - id: mem_buffered
      type: u4
    - id: mem_cached
      type: u4
    - id: vmalloc_total
      type: u4
    - id: vmalloc_used
      type: u4
    - id: dir_data_free
      type: bytes_val
    - id: dir_sdcard_free
      type: bytes_val
    - id: lo_bytes
      type: u4
    - id: lo_packets
      type: u2
    - id: nand_erasures
      type: u4
    - id: load_1min
      type: u2
    - id: load_5min
      type: u2
    - id: load_15min
      type: u2
    - id: beacon_count
      type: u2
    - id: rtc
      type: u4
    - id: boot_time
      type: u4
    - id: long_dur_counter
      type: u2
  
  bytes_val:
    seq:
      - id: raw
        type: u4
        
    instances:
      is_kb:
        value: (raw & 0x80000000) != 0
      value:
        value: raw & 0x7fffffff
      
  comms_parameters_vals:
    seq:
    - id: rx_packets_raw
      doc: incorrectly populated, so we reconstruct
      type: u2
    - id: tx_packets_raw
      doc: incorrectly populated, so we reconstruct
      type: u2
    - id: rx_bytes_raw
      doc: incorrectly populated, so we reconstruct
      type: u2  
    - id: tx_bytes_raw
      doc: incorrectly populated, so we reconstruct
      type: u2
    - id: callsign0
      type: callsign_val
    - id: callsign1
      type: callsign_val
    - id: callsign2
      type: callsign_val
      
    instances:
      rx_packets:
        value: rx_packets_raw << 16
        doc: lossy reconstruction due to bug
      tx_packets:
        value: tx_packets_raw << 16
        doc: lossy reconstruction due to bug
      rx_bytes:
        value: rx_bytes_raw << 16
        doc: lossy reconstruction due to bug
      tx_bytes:
        value: tx_bytes_raw << 16
        doc: lossy reconstruction due to bug
      
  callsign_val:
    seq:
    - id: callsign
      type: str
      size: 6
      encoding: ASCII
    - id: ssid_char_raw
      type: u1
    - id: padding
      type: u1
    - id: last_rx
      type: u4
    
    instances:
      ssid_num:
        doc: workaround bug in our ax25 code
        value: 'ssid_char_raw == 0 ? 0 : ssid_char_raw >= 0x41 ? ssid_char_raw - 0x41 : ssid_char_raw - 0x30'
       
  imu_data_vals:
    seq:
    - id: accel_x
      type: s1
    - id: accel_y
      type: s1
    - id: accel_z
      type: s1
    - id: gyro_x
      type: s1
    - id: gyro_y
      type: s1
    - id: gyro_z
      type: s1
    - id: mag_x
      type: s1
    - id: mag_y
      type: s1
    - id: mag_z
      type: s1
      
  camera_vals:
    seq:
    - id: picture_count
      type: u2
    - id: thumbnail_count
      type: u1
      
  carp_vals:
    seq:
    - id: carp_b_3v3_volt
      type: u1
    - id: carp_b_3v3_curr
      type: u1
    - id: carp_b_1v8_volt
      type: u1
    - id: carp_b_1v8_curr
      type: u1
    - id: carp_b_event_count
      type: u2
    - id: carp_b_latch_count
      type: u2
    - id: pib_temp_intern
      type: u1
    - id: pib_temp_extern
      type: u1
      
  owl_vals:
    seq:
    - id: owl_latest_radio_cfg
      type: u1
    - id: owl_last_rx_action_cmd
      type: u1
    - id: owl_rssi_latest
      type: u1
    - id: owl_snr_latest
      type: s1
    - id: owl_var_byte1
      type: u1
    - id: owl_var_byte2
      type: u1
    - id: owl_var_byte3
      type: u1
    - id: owl_var_byte4
      type: u1
    
  
      
      

