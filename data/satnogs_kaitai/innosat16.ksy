---
meta:
  id: innosat16
  title: InnoSat16 beacon deocoder
  endian: le

doc: |
  :field callsign: data.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field ssid_mask: data.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: data.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign: data.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid_raw_ssid_mask: data.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: data.ax25_header.src_ssid_raw.ssid
  :field ctl: data.ax25_header.ctl
  :field pid: data.ax25_header.pid
  :field beacon_id: data.payload.beacon_id
  :field eps_1_mode: data.payload.eps_1_mode
  :field eps_1_consumption_current: data.payload.eps_1_consumption_current
  :field eps_1_solar_cells_current: data.payload.eps_1_solar_cells_current
  :field eps_1_cell_voltage_full: data.payload.eps_1_cell_voltage_full
  :field eps_1_battery_temperature: data.payload.eps_1_battery_temperature
  :field eps_1_temperature_sp_y_pos: data.payload.eps_1_temperature_sp_y_pos
  :field eps_1_temperature_sp_y_neg: data.payload.eps_1_temperature_sp_y_neg
  :field eps_1_temperature_sp_x_pos: data.payload.eps_1_temperature_sp_x_pos
  :field eps_1_temperature_sp_x_neg: data.payload.eps_1_temperature_sp_x_neg
  :field eps_1_systems_status: data.payload.eps_1_systems_status
  :field eps_1_boot_count: data.payload.eps_1_boot_count
  :field eps_2_mode: data.payload.eps_2_mode
  :field eps_2_consumption_current: data.payload.eps_2_consumption_current
  :field eps_2_solar_cells_current: data.payload.eps_2_solar_cells_current
  :field eps_2_cell_voltage_full: data.payload.eps_2_cell_voltage_full
  :field eps_2_battery_temperature: data.payload.eps_2_battery_temperature
  :field eps_2_temperature_sp_y_pos: data.payload.eps_2_temperature_sp_y_pos
  :field eps_2_temperature_sp_y_neg: data.payload.eps_2_temperature_sp_y_neg
  :field eps_2_temperature_sp_x_pos: data.payload.eps_2_temperature_sp_x_pos
  :field eps_2_temperature_sp_x_neg: data.payload.eps_2_temperature_sp_x_neg
  :field eps_2_systems_status: data.payload.eps_2_systems_status
  :field eps_2_boot_count: data.payload.eps_2_boot_count
  :field adcs_mt_mode: data.payload.adcs_mt_mode
  :field adcs_rm_mode: data.payload.adcs_rm_mode
  :field adcs_kf_mode: data.payload.adcs_kf_mode
  :field adcs_filter_reset_count: data.payload.adcs_filter_reset_count
  :field adcs_sensors_state: data.payload.adcs_sensors_state
  :field adcs_flywheel_state: data.payload.adcs_flywheel_state
  :field comm_type: data.payload.comm_type
  :field comm_vbus_voltage: data.payload.comm_vbus_voltage
  :field comm_boot_count: data.payload.comm_boot_count
  :field comm_rssi: data.payload.comm_rssi
  :field comm_rssi_minimal: data.payload.comm_rssi_minimal
  :field comm_received_valid_packets: data.payload.comm_received_valid_packets
  :field comm_received_invalid_packets: data.payload.comm_received_invalid_packets
  :field comm_sent_packets: data.payload.comm_sent_packets
  :field comm_status: data.payload.comm_status
  :field comm_mode: data.payload.comm_mode
  :field comm_amp_temperature: data.payload.comm_amp_temperature
  :field comm_reserved_1: data.payload.comm_reserved_1
  :field comm_reserved_2: data.payload.comm_reserved_2
  :field packet_id: data.data_header.packet_id
  :field packet_size: data.data_header.packet_size
  :field packet_info: data.data_header.packet_info
  :field cmd: data.data_payload.cmd
  :field gnss_timestamp: data.data_payload.payload.gnss_timestamp
  :field gnss_x: data.data_payload.payload.gnss_x
  :field gnss_y: data.data_payload.payload.gnss_y
  :field gnss_z: data.data_payload.payload.gnss_z
  :field gnss_v_x: data.data_payload.payload.gnss_v_x
  :field gnss_v_y: data.data_payload.payload.gnss_v_y
  :field gnss_v_z: data.data_payload.payload.gnss_v_z
  :field gnss_value_1: data.data_payload.payload.gnss_value_1
  :field gnss_value_2: data.data_payload.payload.gnss_value_2
  :field gnss_value_3: data.data_payload.payload.gnss_value_3
  :field gnss_value_4: data.data_payload.payload.gnss_value_4
  :field gnss_value_5: data.data_payload.payload.gnss_value_5
  :field gnss_value_6: data.data_payload.payload.gnss_value_6
  :field gnss_value_7: data.data_payload.payload.gnss_value_7
  :field gnss_value_8: data.data_payload.payload.gnss_value_8
  :field gnss_value_9: data.data_payload.payload.gnss_value_9
  :field gnss_value_10: data.data_payload.payload.gnss_value_10
  :field gnss_value_11: data.data_payload.payload.gnss_value_11
  :field gnss_value_12: data.data_payload.payload.gnss_value_12
  :field len: len
  :field type: type

seq:
  - id: data
    type:
      switch-on: type
      cases:
        0x848a: ax25_frame
        _: data_frame
instances:
  len:
    value: _io.size
  type:
    type: u2be
    pos: 0
types:
  data_frame:
    seq:
      - id: data_header
        type: data_header
      - id: data_payload
        type: data_tlm

  data_header:
    seq:
      - id: packet_id
        type: u2
      - id: packet_size
        type: u1
      - id: packet_info
        type: u1

  data_tlm:
    seq:
      - id: cmd
        type: u2
      - id: payload
        type:
          switch-on: cmd
          cases:
            0x42BD: gnss_tlm_1
            0x43BD: gnss_tlm_2

  gnss_tlm_1:
    seq:
      - id: gnss_timestamp
        type: u8
        doc: |
          Time (POSIX timestamp, ms)
      - id: gnss_x
        type: f4
      - id: gnss_y
        type: f4
      - id: gnss_z
        type: f4
      - id: gnss_v_x
        type: f4
      - id: gnss_v_y
        type: f4
      - id: gnss_v_z
        type: f4
      - id: gnss_value_1
        type: f4
      - id: gnss_value_2
        type: f4
      - id: gnss_value_3
        type: f4
      - id: gnss_value_4
        type: f4
      - id: gnss_value_5
        type: u1
      - id: gnss_value_6
        type: u1
      - id: gnss_value_7
        type: u1
      - id: gnss_value_8
        type: u1
      - id: gnss_value_9
        type: u2
      - id: gnss_value_10
        type: f4
      - id: gnss_value_11
        type: f4
      - id: gnss_value_12
        type: f4

  gnss_tlm_2:
    seq:
      - id: gnss_timestamp
        type: u4
        doc: |
          Time (POSIX timestamp, ms)
      - id: gnss_x
        type: f4
      - id: gnss_y
        type: f4
      - id: gnss_z
        type: f4
      - id: gnss_v_x
        type: f4
      - id: gnss_v_y
        type: f4
      - id: gnss_v_z
        type: f4
      - id: gnss_value_1
        type: f4
      - id: gnss_value_2
        type: f4
      - id: gnss_value_3
        type: f4
      - id: gnss_value_4
        type: f4
      - id: gnss_value_5
        type: f4
      - id: gnss_value_6
        type: f4
      - id: gnss_value_7
        type: f4
      - id: gnss_value_8
        type: u2
      - id: gnss_value_9
        type: u8

  ax25_frame:
    seq:
      - id: ax25_header
        type: ax25_header
      - id: payload
        type: geoscan_beacon_tlm

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
          any-of:
            - '"BEACON"'
            - '"RS92S7"'

  ssid_mask:
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x0f) >> 1

  geoscan_beacon_tlm:
    seq:
      - id: beacon_id
        type: u1
      - id: eps_1_mode
        type: u1
        doc: |
          0 - init, 1 - reserved, 2 - safe, 3 - normal
      - id: eps_1_consumption_current
        type: u2
        doc: |
          Current of consumption [mA]
      - id: eps_1_solar_cells_current
        type: u2
        doc: |
          Current from sun panels [mA]
      - id: eps_1_cell_voltage_full
        type: u2
        doc: |
          Voltage of both batteries [mV]
      - id: eps_1_battery_temperature
        type: s1
        doc: |
          Temperature of batteries [°C]
      - id: eps_1_temperature_sp_y_pos
        type: s1
        doc: |
          Temperature SP Y pos [°C]
      - id: eps_1_temperature_sp_y_neg
        type: s1
        doc: |
          Temperature SP Y neg [°C]
      - id: eps_1_temperature_sp_x_pos
        type: s1
        doc: |
          Temperature SP X pos [°C]
      - id: eps_1_temperature_sp_x_neg
        type: s1
        doc: |
          Temperature SP X neg [°C]
      - id: eps_1_systems_status
        type: u2
        doc: |
          Status of all systems [bitfield]
          0: Ch1.1
          1: Ch1.2
          2: Ch2.1
          3: Ch2.2
          4: Ch3.1
          5: Ch3.2
          6: Ch4.1
          7: Ch4.2
          8: Ch5.1
          9: Ch5.2
          10: Ch6.1
          11: Ch6.2
          12: Ch7.1
          13: Ch7.2
          14: Ch8.1
          15: Ch8.2
      - id: eps_1_boot_count
        type: u2
        doc: |
          Boot cound of EPS
      - id: eps_2_mode
        type: u1
        doc: |
          0 - init, 1 - reserved, 2 - safe, 3 - normal
      - id: eps_2_consumption_current
        type: u2
        doc: |
          Current of consumption [mA]
      - id: eps_2_solar_cells_current
        type: u2
        doc: |
          Current from sun panels [mA]
      - id: eps_2_cell_voltage_full
        type: u2
        doc: |
          Voltage of both batteries [mV]
      - id: eps_2_battery_temperature
        type: s1
        doc: |
          Temperature of batteries [°C]
      - id: eps_2_temperature_sp_y_pos
        type: s1
        doc: |
          Temperature SP Y pos [°C]
      - id: eps_2_temperature_sp_y_neg
        type: s1
        doc: |
          Temperature SP Y neg [°C]
      - id: eps_2_temperature_sp_x_pos
        type: s1
        doc: |
          Temperature SP X pos [°C]
      - id: eps_2_temperature_sp_x_neg
        type: s1
        doc: |
          Temperature SP X neg [°C]
      - id: eps_2_systems_status
        type: u2
        doc: |
          Status of all systems [bitfield]
          0: Ch1.1
          1: Ch1.2
          2: Ch2.1
          3: Ch2.2
          4: Ch3.1
          5: Ch3.2
          6: Ch4.1
          7: Ch4.2
          8: Ch5.1
          9: Ch5.2
          10: Ch6.1
          11: Ch6.2
          12: Ch7.1
          13: Ch7.2
          14: Ch8.1
          15: Ch8.2
      - id: eps_2_boot_count
        type: u2
        doc: |
          Boot cound of EPS
      - id: adcs_mt_mode
        type: u1
        doc: |
          Mag torquer mode
      - id: adcs_rm_mode
        type: u1
        doc: |
          Ref motion mode
      - id: adcs_kf_mode
        type: u1
        doc: |
          Kalman filter mode
      - id: adcs_filter_reset_count
        type: u1
        doc: |
          Kalman filter reset count
      - id: adcs_sensors_state
        type: u2
        doc: |
          Sensors_state
      - id: adcs_flywheel_state
        type: u1
        doc: |
          flywheel state
      - id: comm_type
        type: u1
        doc: |
          Active modem
      - id: comm_vbus_voltage
        type: u2
        doc: | 
          Voltage of VBUS [mV]
      - id: comm_boot_count
        type: u2
        doc: | 
          Total COMM boot count
      - id: comm_rssi
        type: s1
        doc: |
          COMM received signal strength indicator [dBm]
      - id: comm_rssi_minimal
        type: s1
        doc: |
          COMM received minimal signal strength indicator [dBm]
      - id: comm_received_valid_packets
        type: u1
        doc: |
          Number of received valid packets
      - id: comm_received_invalid_packets
        type: u1
        doc: |
          Number of received invalid packets
      - id: comm_sent_packets
        type: u1
        doc: |
          Number of sent packets
      - id: comm_status
        type: u1
        doc: |
          0: Antenna Detector
          1: Mode correct
          2: FEC ON
          3-7: Reserved
      - id: comm_mode
        type: u1
      - id: comm_amp_temperature
        type: s1
        doc: |
          COMM Amp temperature [°C]
      - id: comm_reserved_1
        type: u2
      - id: comm_reserved_2
        type: u1
