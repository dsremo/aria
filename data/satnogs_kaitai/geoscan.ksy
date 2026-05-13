---
meta:
  id: geoscan
  title: Geoscan Educational Platform Decoder Struct
  endian: le

doc: |
  :field callsign_start_str: data.ax25_header.dest_callsign_raw.callsign_ror.callsign_start.callsign_start_str
  :field callsign_end_str: data.ax25_header.dest_callsign_raw.callsign_ror.callsign_end.callsign_end_str
  :field ssid_mask: data.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: data.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign_start_str: data.ax25_header.src_callsign_raw.callsign_ror.callsign_start.callsign_start_str
  :field src_callsign_raw_callsign_end_str: data.ax25_header.src_callsign_raw.callsign_ror.callsign_end.callsign_end_str
  :field src_ssid_raw_ssid_mask: data.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: data.ax25_header.src_ssid_raw.ssid
  :field ctl: data.ax25_header.ctl
  :field pid: data.ax25_header.pid
  :field beacon_id: data.payload.beacon_id
  :field eps_timestamp: data.payload.eps_timestamp
  :field eps_mode: data.payload.eps_mode
  :field eps_switch_count: data.payload.eps_switch_count
  :field eps_consumption_current: data.payload.eps_consumption_current
  :field eps_solar_cells_current: data.payload.eps_solar_cells_current
  :field eps_cell_voltage_half: data.payload.eps_cell_voltage_half
  :field eps_cell_voltage_full: data.payload.eps_cell_voltage_full
  :field eps_systems_status: data.payload.eps_systems_status
  :field eps_temperature_cell1: data.payload.eps_temperature_cell1
  :field eps_temperature_cell2: data.payload.eps_temperature_cell2
  :field eps_boot_count: data.payload.eps_boot_count
  :field eps_heater_mode: data.payload.eps_heater_mode
  :field eps_reserved: data.payload.eps_reserved
  :field obc_boot_count: data.payload.obc_boot_count
  :field obc_active_status: data.payload.obc_active_status
  :field obc_temperature_pos_x: data.payload.obc_temperature_pos_x
  :field obc_temperature_neg_x: data.payload.obc_temperature_neg_x
  :field obc_temperature_pos_y: data.payload.obc_temperature_pos_y
  :field obc_temperature_neg_y: data.payload.obc_temperature_neg_y
  :field gnss_sat_number: data.payload.gnss_sat_number
  :field adcs_mode: data.payload.adcs_mode
  :field adcs_reserved: data.payload.adcs_reserved
  :field cam_photos_number: data.payload.cam_photos_number
  :field cam_mode: data.payload.cam_mode
  :field cam_reserved: data.payload.cam_reserved
  :field comm_type: data.payload.comm_type
  :field comm_bus_voltage: data.payload.comm_bus_voltage
  :field comm_boot_count: data.payload.comm_boot_count
  :field comm_rssi: data.payload.comm_rssi
  :field comm_rssi_minimal: data.payload.comm_rssi_minimal
  :field comm_received_valid_packets: data.payload.comm_received_valid_packets
  :field comm_received_invalid_packets: data.payload.comm_received_invalid_packets
  :field comm_sent_packets: data.payload.comm_sent_packets
  :field comm_status: data.payload.comm_status
  :field comm_mode: data.payload.comm_mode
  :field comm_temperature: data.payload.comm_temperature
  :field comm_qso_received: data.payload.comm_qso_received
  :field comm_reserved: data.payload.comm_reserved
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
      - id: callsign_start
        type: callsign_start_raw
      - id: callsign_end
        type: callsign_end_raw

  callsign_start_raw:
    seq:
      - id: callsign_start_str
        type: str
        encoding: ASCII
        size: 2
        valid:
          any-of:
            - '"BE"'
            - '"RS"'

  callsign_end_raw:
    seq:
      - id: callsign_end_str
        type: str
        encoding: ASCII
        size: 4

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
      - id: eps_timestamp
        type: u4
        doc: |
          OBC Time (Unix timestamp)
      - id: eps_mode
        type: u1
        doc: |
          0 - init, 1 - reserved, 2 - safe, 3 - normal
      - id: eps_switch_count
        type: u1
        doc: |
          Number of EPS switches
      - id: eps_consumption_current
        type: u2
        doc: |
          Current of consumption [mA]
      - id: eps_solar_cells_current
        type: u2
        doc: |
          Current from sun panels [mA]
      - id: eps_cell_voltage_half
        type: u2
        doc: |
          Voltage of one battery [mV]
      - id: eps_cell_voltage_full
        type: u2
        doc: |
          Voltage of both batteries [mV]
      - id: eps_systems_status
        type: u2
        doc: |
          Status of all systems [bitfield]
          0: COMMu1
          1: COMMu2
          2: OBC
          3: RWS
          4: COMMx
          5: PL1
          6: PL2
          7: PL3
          8: PL4
          9…15: Reserved
      - id: eps_temperature_cell1
        type: s1
        doc: |
          Temperature on battery cell 1 [°C]
      - id: eps_temperature_cell2
        type: s1
        doc: |
          Temperature on battery cell 2 [°C]
      - id: eps_boot_count
        type: u2
        doc: |
      - id: eps_heater_mode
        type: u1
        doc: |
          Bits 0 - 3:
          0 - Turned Off
          1 - Threshold
          2 - Manual
          Bits 4 - 6:
          0 - Middle D1 and D2
          1 - 1-Wire
          2 - Sensor 1
          3 - Sensor 2
          Bit 7:
          0 - Heater Tured Off
          1 - Heater Tured On
      - id: eps_reserved
        type: u2
        doc: |
      - id: obc_boot_count
        type: u2
        doc: |
          Total number of OBC reboots
      - id: obc_active_status
        type: u1
        doc: |
          0: RWS
          1: Torques
          2: INS
          3: Camera
          4: Panel Х+
          5: Panel Х-
          6: Panel Y+
          7: Panel Y-
      - id: obc_temperature_pos_x
        type: s1
        doc: |
          Temperature on panel X+ [°C]
      - id: obc_temperature_neg_x
        type: s1
        doc: |
          Temperature on panel X- [°C]
      - id: obc_temperature_pos_y
        type: s1
        doc: |
          Temperature on panel Y+ [°C]
      - id: obc_temperature_neg_y
        type: s1
        doc: |
          Temperature on panel Y- [°C]
      - id: gnss_sat_number
        type: u1
        doc: |
          Number of fixed satellites
      - id: adcs_mode
        type: u1
        doc: |
          0 - Turned Off
          1 - B-Dot
          2 - Three-axis
      - id: adcs_reserved
        type: u1
        doc: |
      - id: cam_photos_number
        type: u1
        doc: |
          Total number of made images
      - id: cam_mode
        type: u1
        doc: |
          0 - Waiting
          1 - Single Photo
          2 - Serial Photo
          3 - Video
          4 - Control
          255 - Turned Off
      - id: cam_reserved
        type: u4
      - id: comm_type
        type: u1
        doc: |
          3 - Comm #1
          13 - Comm #2
      - id: comm_bus_voltage
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
          1: Battery Status Detector
          2-7: Reserved
      - id: comm_mode
        type: u1
        doc: |
          0 - Mode I
          1 - Mode III
          2 - Mode II
          3-244 - Reserved
      - id: comm_temperature
        type: s1
        doc: |
          COMM board temperature [°C]
      - id: comm_qso_received
        type: u1
        doc: |
          Number of received QSO
      - id: comm_reserved
        type: u2
