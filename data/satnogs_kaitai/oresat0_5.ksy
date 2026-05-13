meta:
  endian: le
  id: oresat0_5
  title: oresat0_5 Decoder Struct
doc: |
  :field callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field ssid_mask: ax25_frame.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid_raw_ssid_mask: ax25_frame.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field ctl: ax25_frame.ax25_header.ctl
  :field pid: ax25_frame.payload.pid
  :field beacon_start_chars: ax25_frame.payload.ax25_info.beacon_start_chars
  :field satellite_id: ax25_frame.payload.ax25_info.satellite_id
  :field beacon_revision: ax25_frame.payload.ax25_info.beacon_revision
  :field status: ax25_frame.payload.ax25_info.status
  :field mode: ax25_frame.payload.ax25_info.mode
  :field system_uptime: ax25_frame.payload.ax25_info.system_uptime
  :field system_unix_time: ax25_frame.payload.ax25_info.system_unix_time
  :field system_power_cycles: ax25_frame.payload.ax25_info.system_power_cycles
  :field system_storage_percent: ax25_frame.payload.ax25_info.system_storage_percent
  :field lband_rx_bytes: ax25_frame.payload.ax25_info.lband_rx_bytes
  :field lband_rx_packets: ax25_frame.payload.ax25_info.lband_rx_packets
  :field lband_rssi: ax25_frame.payload.ax25_info.lband_rssi
  :field lband_synth_relock_count: ax25_frame.payload.ax25_info.lband_synth_relock_count
  :field uhf_rx_bytes: ax25_frame.payload.ax25_info.uhf_rx_bytes
  :field uhf_rx_packets: ax25_frame.payload.ax25_info.uhf_rx_packets
  :field uhf_rssi: ax25_frame.payload.ax25_info.uhf_rssi
  :field edl_sequence_count: ax25_frame.payload.ax25_info.edl_sequence_count
  :field edl_rejected_count: ax25_frame.payload.ax25_info.edl_rejected_count
  :field fread_cache_length: ax25_frame.payload.ax25_info.fread_cache_length
  :field fwrite_cache_length: ax25_frame.payload.ax25_info.fwrite_cache_length
  :field updater_cache_length: ax25_frame.payload.ax25_info.updater_cache_length
  :field adcs_manager_mode: ax25_frame.payload.ax25_info.adcs_manager_mode
  :field battery_1_pack_1_vbatt: ax25_frame.payload.ax25_info.battery_1_pack_1_vbatt
  :field battery_1_pack_1_vcell: ax25_frame.payload.ax25_info.battery_1_pack_1_vcell
  :field battery_1_pack_1_vcell_max: ax25_frame.payload.ax25_info.battery_1_pack_1_vcell_max
  :field battery_1_pack_1_vcell_min: ax25_frame.payload.ax25_info.battery_1_pack_1_vcell_min
  :field battery_1_pack_1_vcell_1: ax25_frame.payload.ax25_info.battery_1_pack_1_vcell_1
  :field battery_1_pack_1_vcell_2: ax25_frame.payload.ax25_info.battery_1_pack_1_vcell_2
  :field battery_1_pack_1_vcell_avg: ax25_frame.payload.ax25_info.battery_1_pack_1_vcell_avg
  :field battery_1_pack_1_temperature: ax25_frame.payload.ax25_info.battery_1_pack_1_temperature
  :field battery_1_pack_1_temperature_avg: ax25_frame.payload.ax25_info.battery_1_pack_1_temperature_avg
  :field battery_1_pack_1_temperature_max: ax25_frame.payload.ax25_info.battery_1_pack_1_temperature_max
  :field battery_1_pack_1_temperature_min: ax25_frame.payload.ax25_info.battery_1_pack_1_temperature_min
  :field battery_1_pack_1_current: ax25_frame.payload.ax25_info.battery_1_pack_1_current
  :field battery_1_pack_1_current_avg: ax25_frame.payload.ax25_info.battery_1_pack_1_current_avg
  :field battery_1_pack_1_current_max: ax25_frame.payload.ax25_info.battery_1_pack_1_current_max
  :field battery_1_pack_1_current_min: ax25_frame.payload.ax25_info.battery_1_pack_1_current_min
  :field battery_1_pack_1_status: ax25_frame.payload.ax25_info.battery_1_pack_1_status
  :field battery_1_pack_1_reported_state_of_charge: ax25_frame.payload.ax25_info.battery_1_pack_1_reported_state_of_charge
  :field battery_1_pack_1_full_capacity: ax25_frame.payload.ax25_info.battery_1_pack_1_full_capacity
  :field battery_1_pack_1_reported_capacity: ax25_frame.payload.ax25_info.battery_1_pack_1_reported_capacity
  :field battery_1_pack_2_vbatt: ax25_frame.payload.ax25_info.battery_1_pack_2_vbatt
  :field battery_1_pack_2_vcell: ax25_frame.payload.ax25_info.battery_1_pack_2_vcell
  :field battery_1_pack_2_vcell_max: ax25_frame.payload.ax25_info.battery_1_pack_2_vcell_max
  :field battery_1_pack_2_vcell_min: ax25_frame.payload.ax25_info.battery_1_pack_2_vcell_min
  :field battery_1_pack_2_vcell_1: ax25_frame.payload.ax25_info.battery_1_pack_2_vcell_1
  :field battery_1_pack_2_vcell_2: ax25_frame.payload.ax25_info.battery_1_pack_2_vcell_2
  :field battery_1_pack_2_vcell_avg: ax25_frame.payload.ax25_info.battery_1_pack_2_vcell_avg
  :field battery_1_pack_2_temperature: ax25_frame.payload.ax25_info.battery_1_pack_2_temperature
  :field battery_1_pack_2_temperature_avg: ax25_frame.payload.ax25_info.battery_1_pack_2_temperature_avg
  :field battery_1_pack_2_temperature_max: ax25_frame.payload.ax25_info.battery_1_pack_2_temperature_max
  :field battery_1_pack_2_temperature_min: ax25_frame.payload.ax25_info.battery_1_pack_2_temperature_min
  :field battery_1_pack_2_current: ax25_frame.payload.ax25_info.battery_1_pack_2_current
  :field battery_1_pack_2_current_avg: ax25_frame.payload.ax25_info.battery_1_pack_2_current_avg
  :field battery_1_pack_2_current_max: ax25_frame.payload.ax25_info.battery_1_pack_2_current_max
  :field battery_1_pack_2_current_min: ax25_frame.payload.ax25_info.battery_1_pack_2_current_min
  :field battery_1_pack_2_status: ax25_frame.payload.ax25_info.battery_1_pack_2_status
  :field battery_1_pack_2_reported_state_of_charge: ax25_frame.payload.ax25_info.battery_1_pack_2_reported_state_of_charge
  :field battery_1_pack_2_full_capacity: ax25_frame.payload.ax25_info.battery_1_pack_2_full_capacity
  :field battery_1_pack_2_reported_capacity: ax25_frame.payload.ax25_info.battery_1_pack_2_reported_capacity
  :field solar_1_output_voltage_avg: ax25_frame.payload.ax25_info.solar_1_output_voltage_avg
  :field solar_1_output_current_avg: ax25_frame.payload.ax25_info.solar_1_output_current_avg
  :field solar_1_output_power_avg: ax25_frame.payload.ax25_info.solar_1_output_power_avg
  :field solar_1_output_voltage_max: ax25_frame.payload.ax25_info.solar_1_output_voltage_max
  :field solar_1_output_current_max: ax25_frame.payload.ax25_info.solar_1_output_current_max
  :field solar_1_output_power_max: ax25_frame.payload.ax25_info.solar_1_output_power_max
  :field solar_1_output_energy: ax25_frame.payload.ax25_info.solar_1_output_energy
  :field solar_2_output_voltage_avg: ax25_frame.payload.ax25_info.solar_2_output_voltage_avg
  :field solar_2_output_current_avg: ax25_frame.payload.ax25_info.solar_2_output_current_avg
  :field solar_2_output_power_avg: ax25_frame.payload.ax25_info.solar_2_output_power_avg
  :field solar_2_output_voltage_max: ax25_frame.payload.ax25_info.solar_2_output_voltage_max
  :field solar_2_output_current_max: ax25_frame.payload.ax25_info.solar_2_output_current_max
  :field solar_2_output_power_max: ax25_frame.payload.ax25_info.solar_2_output_power_max
  :field solar_2_output_energy: ax25_frame.payload.ax25_info.solar_2_output_energy
  :field solar_3_output_voltage_avg: ax25_frame.payload.ax25_info.solar_3_output_voltage_avg
  :field solar_3_output_current_avg: ax25_frame.payload.ax25_info.solar_3_output_current_avg
  :field solar_3_output_power_avg: ax25_frame.payload.ax25_info.solar_3_output_power_avg
  :field solar_3_output_voltage_max: ax25_frame.payload.ax25_info.solar_3_output_voltage_max
  :field solar_3_output_current_max: ax25_frame.payload.ax25_info.solar_3_output_current_max
  :field solar_3_output_power_max: ax25_frame.payload.ax25_info.solar_3_output_power_max
  :field solar_3_output_energy: ax25_frame.payload.ax25_info.solar_3_output_energy
  :field solar_4_output_voltage_avg: ax25_frame.payload.ax25_info.solar_4_output_voltage_avg
  :field solar_4_output_current_avg: ax25_frame.payload.ax25_info.solar_4_output_current_avg
  :field solar_4_output_power_avg: ax25_frame.payload.ax25_info.solar_4_output_power_avg
  :field solar_4_output_voltage_max: ax25_frame.payload.ax25_info.solar_4_output_voltage_max
  :field solar_4_output_current_max: ax25_frame.payload.ax25_info.solar_4_output_current_max
  :field solar_4_output_power_max: ax25_frame.payload.ax25_info.solar_4_output_power_max
  :field solar_4_output_energy: ax25_frame.payload.ax25_info.solar_4_output_energy
  :field solar_5_output_voltage_avg: ax25_frame.payload.ax25_info.solar_5_output_voltage_avg
  :field solar_5_output_current_avg: ax25_frame.payload.ax25_info.solar_5_output_current_avg
  :field solar_5_output_power_avg: ax25_frame.payload.ax25_info.solar_5_output_power_avg
  :field solar_5_output_voltage_max: ax25_frame.payload.ax25_info.solar_5_output_voltage_max
  :field solar_5_output_current_max: ax25_frame.payload.ax25_info.solar_5_output_current_max
  :field solar_5_output_power_max: ax25_frame.payload.ax25_info.solar_5_output_power_max
  :field solar_5_output_energy: ax25_frame.payload.ax25_info.solar_5_output_energy
  :field solar_6_output_voltage_avg: ax25_frame.payload.ax25_info.solar_6_output_voltage_avg
  :field solar_6_output_current_avg: ax25_frame.payload.ax25_info.solar_6_output_current_avg
  :field solar_6_output_power_avg: ax25_frame.payload.ax25_info.solar_6_output_power_avg
  :field solar_6_output_voltage_max: ax25_frame.payload.ax25_info.solar_6_output_voltage_max
  :field solar_6_output_current_max: ax25_frame.payload.ax25_info.solar_6_output_current_max
  :field solar_6_output_power_max: ax25_frame.payload.ax25_info.solar_6_output_power_max
  :field solar_6_output_energy: ax25_frame.payload.ax25_info.solar_6_output_energy
  :field star_tracker_1_system_storage_percent: ax25_frame.payload.ax25_info.star_tracker_1_system_storage_percent
  :field star_tracker_1_status: ax25_frame.payload.ax25_info.star_tracker_1_status
  :field gps_system_storage_percent: ax25_frame.payload.ax25_info.gps_system_storage_percent
  :field gps_status: ax25_frame.payload.ax25_info.gps_status
  :field gps_skytraq_number_of_sv: ax25_frame.payload.ax25_info.gps_skytraq_number_of_sv
  :field gps_skytraq_fix_mode: ax25_frame.payload.ax25_info.gps_skytraq_fix_mode
  :field adcs_gyroscope_roll_rate: ax25_frame.payload.ax25_info.adcs_gyroscope_roll_rate
  :field adcs_gyroscope_pitch_rate: ax25_frame.payload.ax25_info.adcs_gyroscope_pitch_rate
  :field adcs_gyroscope_yaw_rate: ax25_frame.payload.ax25_info.adcs_gyroscope_yaw_rate
  :field dxwifi_system_storage_percent: ax25_frame.payload.ax25_info.dxwifi_system_storage_percent
  :field dxwifi_status: ax25_frame.payload.ax25_info.dxwifi_status
  :field dxwifi_radio_temperature: ax25_frame.payload.ax25_info.dxwifi_radio_temperature
  :field cfc_processor_system_storage_percent: ax25_frame.payload.ax25_info.cfc_processor_system_storage_percent
  :field cfc_processor_camera_status: ax25_frame.payload.ax25_info.cfc_processor_camera_status
  :field cfc_processor_camera_temperature: ax25_frame.payload.ax25_info.cfc_processor_camera_temperature
  :field cfc_processor_tec_status: ax25_frame.payload.ax25_info.cfc_processor_tec_status
  :field refcs: ax25_frame.ax25_trunk.refcs

seq:
- doc-ref: https://www.tapr.org/pub_ax25.html
  id: ax25_frame
  type: ax25_frame
types:
  ax25_frame:
    seq:
    - id: ax25_header
      type: ax25_header
    - id: payload
      type:
        cases:
          '0x00': i_frame
          '0x02': i_frame
          '0x03': ui_frame
          '0x10': i_frame
          '0x12': i_frame
          '0x13': ui_frame
        switch-on: ax25_header.ctl & 0x13
    - id: ax25_trunk
      type: ax25_trunk
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
    - doc: Repeater flag is set!
      id: repeater
      if: (src_ssid_raw.ssid_mask & 0x01) == 0
      type: repeater
    - id: ctl
      type: u1
  ax25_info_data:
    seq:
    - doc: the aprs start characters
      encoding: ASCII
      id: beacon_start_chars
      size: 3
      type: str
    - doc: the unique oresat satellite id
      id: satellite_id
      type: u1
    - doc: the beacon revision number
      id: beacon_revision
      type: u1
    - doc: ''
      id: status
      type: u1
    - doc: the oresat system mode
      id: mode
      type: u1
    - doc: uptime
      id: system_uptime
      type: u4
    - doc: unix time
      id: system_unix_time
      type: u4
    - doc: the number of power cycles
      id: system_power_cycles
      type: u2
    - doc: the current storage percent used
      id: system_storage_percent
      type: u1
    - doc: lband received byte count
      id: lband_rx_bytes
      type: u4
    - doc: lband received packet count
      id: lband_rx_packets
      type: u4
    - doc: lband rssi of last packet received after lna, filters, and digital channel
        filter
      id: lband_rssi
      type: s1
    - doc: lband si41xx synthesizer relock count since boot
      id: lband_synth_relock_count
      type: u1
    - doc: uhf received byte count
      id: uhf_rx_bytes
      type: u4
    - doc: uhf received packet count
      id: uhf_rx_packets
      type: u4
    - doc: uhf rssi of last packet received after lna, filters, and digital channel
        filter
      id: uhf_rssi
      type: s1
    - doc: edl sequence count
      id: edl_sequence_count
      type: u4
    - doc: edl sequence count
      id: edl_rejected_count
      type: u4
    - doc: number of files in fread cache
      id: fread_cache_length
      type: u1
    - doc: number of files in fwrite cache
      id: fwrite_cache_length
      type: u1
    - doc: number of updates cached
      id: updater_cache_length
      type: u1
    - doc: requested adcs mission mode to follow
      id: adcs_manager_mode
      type: u1
    - doc: pack voltage
      id: battery_1_pack_1_vbatt
      type: u2
    - doc: lowest cell voltage
      id: battery_1_pack_1_vcell
      type: u2
    - doc: max voltage for a cell
      id: battery_1_pack_1_vcell_max
      type: u2
    - doc: min voltage for a cell
      id: battery_1_pack_1_vcell_min
      type: u2
    - doc: cell 1 voltage
      id: battery_1_pack_1_vcell_1
      type: u2
    - doc: cell 2 voltage
      id: battery_1_pack_1_vcell_2
      type: u2
    - doc: average voltage of both cells
      id: battery_1_pack_1_vcell_avg
      type: u2
    - doc: temperature of battery pack
      id: battery_1_pack_1_temperature
      type: s1
    - doc: average temperature of battery pack
      id: battery_1_pack_1_temperature_avg
      type: s1
    - doc: max temperature of battery pack
      id: battery_1_pack_1_temperature_max
      type: s1
    - doc: min temperature of battery pack
      id: battery_1_pack_1_temperature_min
      type: s1
    - doc: pack current
      id: battery_1_pack_1_current
      type: s2
    - doc: pack average current
      id: battery_1_pack_1_current_avg
      type: s2
    - doc: pack max current
      id: battery_1_pack_1_current_max
      type: s2
    - doc: pack min current
      id: battery_1_pack_1_current_min
      type: s2
    - doc: ''
      id: battery_1_pack_1_status
      type: u1
    - doc: reported charge percent
      id: battery_1_pack_1_reported_state_of_charge
      type: u1
    - doc: capacity of battery pack
      id: battery_1_pack_1_full_capacity
      type: u2
    - doc: reported capacity of battery pack
      id: battery_1_pack_1_reported_capacity
      type: u2
    - doc: pack voltage
      id: battery_1_pack_2_vbatt
      type: u2
    - doc: lowest cell voltage
      id: battery_1_pack_2_vcell
      type: u2
    - doc: max voltage for a cell
      id: battery_1_pack_2_vcell_max
      type: u2
    - doc: min voltage for a cell
      id: battery_1_pack_2_vcell_min
      type: u2
    - doc: cell 1 voltage
      id: battery_1_pack_2_vcell_1
      type: u2
    - doc: cell 2 voltage
      id: battery_1_pack_2_vcell_2
      type: u2
    - doc: average voltage of both cells
      id: battery_1_pack_2_vcell_avg
      type: u2
    - doc: temperature of battery pack
      id: battery_1_pack_2_temperature
      type: s1
    - doc: average temperature of battery pack
      id: battery_1_pack_2_temperature_avg
      type: s1
    - doc: max temperature of battery pack
      id: battery_1_pack_2_temperature_max
      type: s1
    - doc: min temperature of battery pack
      id: battery_1_pack_2_temperature_min
      type: s1
    - doc: pack current
      id: battery_1_pack_2_current
      type: s2
    - doc: pack average current
      id: battery_1_pack_2_current_avg
      type: s2
    - doc: pack max current
      id: battery_1_pack_2_current_max
      type: s2
    - doc: pack min current
      id: battery_1_pack_2_current_min
      type: s2
    - doc: ''
      id: battery_1_pack_2_status
      type: u1
    - doc: reported charge percent
      id: battery_1_pack_2_reported_state_of_charge
      type: u1
    - doc: capacity of battery pack
      id: battery_1_pack_2_full_capacity
      type: u2
    - doc: reported capacity of battery pack
      id: battery_1_pack_2_reported_capacity
      type: u2
    - doc: average voltage
      id: solar_1_output_voltage_avg
      type: u2
    - doc: average current
      id: solar_1_output_current_avg
      type: s2
    - doc: average power
      id: solar_1_output_power_avg
      type: u2
    - doc: max voltage
      id: solar_1_output_voltage_max
      type: u2
    - doc: max current
      id: solar_1_output_current_max
      type: s2
    - doc: max power
      id: solar_1_output_power_max
      type: u2
    - doc: storing energy
      id: solar_1_output_energy
      type: u2
    - doc: average voltage
      id: solar_2_output_voltage_avg
      type: u2
    - doc: average current
      id: solar_2_output_current_avg
      type: s2
    - doc: average power
      id: solar_2_output_power_avg
      type: u2
    - doc: max voltage
      id: solar_2_output_voltage_max
      type: u2
    - doc: max current
      id: solar_2_output_current_max
      type: s2
    - doc: max power
      id: solar_2_output_power_max
      type: u2
    - doc: storing energy
      id: solar_2_output_energy
      type: u2
    - doc: average voltage
      id: solar_3_output_voltage_avg
      type: u2
    - doc: average current
      id: solar_3_output_current_avg
      type: s2
    - doc: average power
      id: solar_3_output_power_avg
      type: u2
    - doc: max voltage
      id: solar_3_output_voltage_max
      type: u2
    - doc: max current
      id: solar_3_output_current_max
      type: s2
    - doc: max power
      id: solar_3_output_power_max
      type: u2
    - doc: storing energy
      id: solar_3_output_energy
      type: u2
    - doc: average voltage
      id: solar_4_output_voltage_avg
      type: u2
    - doc: average current
      id: solar_4_output_current_avg
      type: s2
    - doc: average power
      id: solar_4_output_power_avg
      type: u2
    - doc: max voltage
      id: solar_4_output_voltage_max
      type: u2
    - doc: max current
      id: solar_4_output_current_max
      type: s2
    - doc: max power
      id: solar_4_output_power_max
      type: u2
    - doc: storing energy
      id: solar_4_output_energy
      type: u2
    - doc: average voltage
      id: solar_5_output_voltage_avg
      type: u2
    - doc: average current
      id: solar_5_output_current_avg
      type: s2
    - doc: average power
      id: solar_5_output_power_avg
      type: u2
    - doc: max voltage
      id: solar_5_output_voltage_max
      type: u2
    - doc: max current
      id: solar_5_output_current_max
      type: s2
    - doc: max power
      id: solar_5_output_power_max
      type: u2
    - doc: storing energy
      id: solar_5_output_energy
      type: u2
    - doc: average voltage
      id: solar_6_output_voltage_avg
      type: u2
    - doc: average current
      id: solar_6_output_current_avg
      type: s2
    - doc: average power
      id: solar_6_output_power_avg
      type: u2
    - doc: max voltage
      id: solar_6_output_voltage_max
      type: u2
    - doc: max current
      id: solar_6_output_current_max
      type: s2
    - doc: max power
      id: solar_6_output_power_max
      type: u2
    - doc: storing energy
      id: solar_6_output_energy
      type: u2
    - doc: the current storage percent used
      id: star_tracker_1_system_storage_percent
      type: u1
    - doc: ''
      id: star_tracker_1_status
      type: u1
    - doc: the current storage percent used
      id: gps_system_storage_percent
      type: u1
    - doc: ''
      id: gps_status
      type: u1
    - doc: number of gps satellites locked onto
      id: gps_skytraq_number_of_sv
      type: u1
    - doc: ''
      id: gps_skytraq_fix_mode
      type: u1
    - doc: z-axis rate
      id: adcs_gyroscope_roll_rate
      type: s2
    - doc: x-axis rate
      id: adcs_gyroscope_pitch_rate
      type: s2
    - doc: y-axis rate
      id: adcs_gyroscope_yaw_rate
      type: s2
    - doc: the current storage percent used
      id: dxwifi_system_storage_percent
      type: u1
    - doc: the dxwifi status
      id: dxwifi_status
      type: u1
    - doc: the temperature of the radio
      id: dxwifi_radio_temperature
      type: s1
    - doc: the current storage percent used
      id: cfc_processor_system_storage_percent
      type: u1
    - doc: ''
      id: cfc_processor_camera_status
      type: u1
    - doc: the camera temperature
      id: cfc_processor_camera_temperature
      type: s1
    - doc: the tec controller status
      id: cfc_processor_tec_status
      type: b1
  ax25_trunk:
    seq:
    - id: refcs
      type: u4
  callsign:
    seq:
    - encoding: ASCII
      id: callsign
      size: 6
      type: str
      valid:
        any-of:
        - '"KJ7SAT"'
        - '"SPACE "'
  callsign_raw:
    seq:
    - id: callsign_ror
      process: ror(1)
      size: 6
      type: callsign
  i_frame:
    seq:
    - id: pid
      type: u1
    - id: ax25_info
      size: 216
      type: ax25_info_data
  repeater:
    seq:
    - doc: Repeat until no repeater flag is set!
      id: rpt_instance
      repeat: until
      repeat-until: ((_.rpt_ssid_raw.ssid_mask & 0x1) == 0x1)
      type: repeaters
  repeaters:
    seq:
    - id: rpt_callsign_raw
      type: callsign_raw
    - id: rpt_ssid_raw
      type: ssid_mask
  ssid_mask:
    instances:
      ssid:
        value: (ssid_mask & 0x0f) >> 1
    seq:
    - id: ssid_mask
      type: u1
  ui_frame:
    seq:
    - id: pid
      type: u1
    - id: ax25_info
      size: 216
      type: ax25_info_data
