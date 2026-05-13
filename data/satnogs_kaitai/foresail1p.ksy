---
meta:
  id: foresail1p
  title: FORESAIL-1p
  endian: be
doc-ref: 'https://foresail.github.io/docs/FS1p_Space_Ground_Interface_Control_Sheet.pdf'
doc: |
  :field version_and_identity_len: skylink.version_and_identity_len
  :field identity: skylink.identity
  :field flags: skylink.header.flags
  :field frame_sequence: skylink.header.frame_sequence
  :field extension_length: skylink.header.extension_length
  :field vc: skylink.header.vc
  :field is_arq_on: skylink.header.is_arq_on
  :field is_authenticated: skylink.header.is_authenticated
  :field is_crced: skylink.header.is_crced
  :field sequence_control: skylink.header.sequence_control
  :field version: skylink.version
  :field len_identity: skylink.len_identity
  :field packet_id: pus.header.packet_id
  :field sequence: pus.header.sequence
  :field length: pus.header.length
  :field secondary_header: pus.header.secondary_header
  :field service_type: pus.header.service_type
  :field service_subtype: pus.header.service_subtype

  :field timestamp: pus.obc_housekeeping.timestamp.timestamp
  :field side: pus.obc_housekeeping.side
  :field fdir_mode: pus.obc_housekeeping.fdir_mode
  :field sys_watchdog_counter: pus.obc_housekeeping.sys_watchdog_counter
  :field scheduler: pus.obc_housekeeping.scheduler
  :field software_revision: pus.obc_housekeeping.software_revision
  :field uptime: pus.obc_housekeeping.uptime
  :field heap_free: pus.obc_housekeeping.heap_free
  :field cpu_load: pus.obc_housekeeping.cpu_load
  :field fs_free_space: pus.obc_housekeeping.fs_free_space
  :field arbiter_uptime: pus.obc_housekeeping.arbiter_uptime
  :field arbiter_age: pus.obc_housekeeping.arbiter_age
  :field arbiter_bootcount: pus.obc_housekeeping.arbiter_bootcount
  :field arbiter_temperature: pus.obc_housekeeping.arbiter_temperature
  :field side_a_bootcount: pus.obc_housekeeping.side_a_bootcount
  :field side_a_heartbeat: pus.obc_housekeeping.side_a_heartbeat
  :field side_a_fail_counter: pus.obc_housekeeping.side_a_fail_counter
  :field side_a_fail_reason: pus.obc_housekeeping.side_a_fail_reason
  :field side_b_bootcount: pus.obc_housekeeping.side_b_bootcount
  :field side_b_heartbeat: pus.obc_housekeeping.side_b_heartbeat
  :field side_b_fail_counter: pus.obc_housekeeping.side_b_fail_counter
  :field side_b_fail_reason: pus.obc_housekeeping.side_b_fail_reason
  :field arbiter_log_1: pus.obc_housekeeping.arbiter_log_1
  :field arbiter_log_2: pus.obc_housekeeping.arbiter_log_2
  :field arbiter_log_3: pus.obc_housekeeping.arbiter_log_3
  :field arbiter_log_4: pus.obc_housekeeping.arbiter_log_4

  :field eps_housekeeping_timestamp: pus.eps_housekeeping.timestamp.timestamp
  :field pcdu_uptime: pus.eps_housekeeping.pcdu_uptime
  :field pcdu_boot_count: pus.eps_housekeeping.pcdu_boot_count
  :field bb_boot_count: pus.eps_housekeeping.bb_boot_count
  :field apr_boot_count: pus.eps_housekeeping.apr_boot_count
  :field pdm_expected: pus.eps_housekeeping.pdm_expected
  :field pdm_faulted: pus.eps_housekeeping.pdm_faulted
  :field padding_byte: pus.eps_housekeeping.padding_byte
  :field eps_subsystem_state: pus.eps_housekeeping.eps_subsystem_state
  :field heater_pwm_on_time: pus.eps_housekeeping.heater_pwm_on_time
  :field current_apr_x: pus.eps_housekeeping.current_apr_x
  :field current_apr_y: pus.eps_housekeeping.current_apr_y
  :field voltage_apr_x: pus.eps_housekeeping.voltage_apr_x
  :field voltage_apr_y: pus.eps_housekeeping.voltage_apr_y
  :field current_apr_x_at_mpp: pus.eps_housekeeping.current_apr_x_at_mpp
  :field voltage_apr_x_at_mpp: pus.eps_housekeeping.voltage_apr_x_at_mpp
  :field current_apr_y_at_mpp: pus.eps_housekeeping.current_apr_y_at_mpp
  :field voltage_apr_y_at_mpp: pus.eps_housekeeping.voltage_apr_y_at_mpp
  :field voltage_battery: pus.eps_housekeeping.voltage_battery
  :field voltage_battery_lower: pus.eps_housekeeping.voltage_battery_lower
  :field voltage_payloads: pus.eps_housekeeping.voltage_payloads
  :field voltage_obc_adcs: pus.eps_housekeeping.voltage_obc_adcs
  :field voltage_uhf: pus.eps_housekeeping.voltage_uhf
  :field temperature_mcu_pcdu: pus.eps_housekeeping.temperature_mcu_pcdu
  :field temperature_mcu_bb: pus.eps_housekeeping.temperature_mcu_bb
  :field temperature_mcu_apr: pus.eps_housekeeping.temperature_mcu_apr
  :field temperature_battery: pus.eps_housekeeping.temperature_battery
  :field temperature_sp_x_minus: pus.eps_housekeeping.temperature_sp_x_minus
  :field temperature_sp_x_plus: pus.eps_housekeeping.temperature_sp_x_plus
  :field temperature_sp_y_minus: pus.eps_housekeeping.temperature_sp_y_minus
  :field temperature_sp_y_plus: pus.eps_housekeeping.temperature_sp_y_plus
  :field current_battery: pus.eps_housekeeping.current_battery
  :field current_battery_min: pus.eps_housekeeping.current_battery_min
  :field current_battery_max: pus.eps_housekeeping.current_battery_max
  :field current_pate_batt: pus.eps_housekeeping.current_pate_batt
  :field current_pb_batt: pus.eps_housekeeping.current_pb_batt
  :field current_pb_3v6: pus.eps_housekeeping.current_pb_3v6
  :field current_cam_3v6: pus.eps_housekeeping.current_cam_3v6
  :field current_mag_3v6: pus.eps_housekeeping.current_mag_3v6
  :field current_obc_3v6: pus.eps_housekeeping.current_obc_3v6
  :field current_uhf_3v6: pus.eps_housekeeping.current_uhf_3v6
  :field current_adcs_3v6: pus.eps_housekeeping.current_adcs_3v6
  :field current_min_pate: pus.eps_housekeeping.current_min_pate
  :field current_min_pb_batt: pus.eps_housekeeping.current_min_pb_batt
  :field current_min_pb_3v6: pus.eps_housekeeping.current_min_pb_3v6
  :field current_min_cam_3v6: pus.eps_housekeeping.current_min_cam_3v6
  :field current_min_mag_3v6: pus.eps_housekeeping.current_min_mag_3v6
  :field current_min_obc_3v6: pus.eps_housekeeping.current_min_obc_3v6
  :field current_min_uhf_3v6: pus.eps_housekeeping.current_min_uhf_3v6
  :field current_min_adcs_3v6: pus.eps_housekeeping.current_min_adcs_3v6
  :field current_max_pate: pus.eps_housekeeping.current_max_pate
  :field current_max_pb_batt: pus.eps_housekeeping.current_max_pb_batt
  :field current_max_pb_3v6: pus.eps_housekeeping.current_max_pb_3v6
  :field current_max_cam_3v6: pus.eps_housekeeping.current_max_cam_3v6
  :field current_max_mag_3v6: pus.eps_housekeeping.current_max_mag_3v6
  :field current_max_obc_3v6: pus.eps_housekeeping.current_max_obc_3v6
  :field current_max_uhf_3v6: pus.eps_housekeeping.current_max_uhf_3v6
  :field current_max_adcs_3v6: pus.eps_housekeeping.current_max_adcs_3v6

  :field uhf_housekeeping_timestamp: pus.uhf_housekeeping.timestamp.timestamp
  :field uhf_housekeeping_uptime: pus.uhf_housekeeping.uptime
  :field bootcount: pus.uhf_housekeeping.bootcount
  :field fdir_counter: pus.uhf_housekeeping.fdir_counter
  :field mcu_wd_reset_count: pus.uhf_housekeeping.mcu_wd_reset_count
  :field mbe_count: pus.uhf_housekeeping.mbe_count
  :field bus_sync_errors: pus.uhf_housekeeping.bus_sync_errors
  :field bus_len_errors: pus.uhf_housekeeping.bus_len_errors
  :field bus_crc_errors: pus.uhf_housekeeping.bus_crc_errors
  :field bus_receive_timeouts: pus.uhf_housekeeping.bus_receive_timeouts
  :field total_tx_frames: pus.uhf_housekeeping.total_tx_frames
  :field total_rx_frames: pus.uhf_housekeeping.total_rx_frames
  :field total_ham_tx_frames: pus.uhf_housekeeping.total_ham_tx_frames
  :field total_ham_rx_frames: pus.uhf_housekeeping.total_ham_rx_frames
  :field hardware_side_a_bootcount: pus.uhf_housekeeping.hardware_side_a_bootcount
  :field hardware_side_b_bootcount: pus.uhf_housekeeping.hardware_side_b_bootcount
  :field uhf_housekeeping_side: pus.uhf_housekeeping.side
  :field symbol_rate_rx: pus.uhf_housekeeping.symbol_rate_rx
  :field symbol_rate_tx: pus.uhf_housekeeping.symbol_rate_tx
  :field my_window_length: pus.uhf_housekeeping.my_window_length
  :field peer_window_length: pus.uhf_housekeeping.peer_window_length
  :field mcu_temperature: pus.uhf_housekeeping.mcu_temperature
  :field pa_temperature: pus.uhf_housekeeping.pa_temperature
  :field background_rssi: pus.uhf_housekeeping.background_rssi
  :field background_max_rssi: pus.uhf_housekeeping.background_max_rssi
  :field last_rssi: pus.uhf_housekeeping.last_rssi
  :field last_freq_offset: pus.uhf_housekeeping.last_freq_offset

  :field adcs_housekeeping_timestamp: pus.adcs_housekeeping.timestamp.timestamp
  :field determination_mode: pus.adcs_housekeeping.determination_mode
  :field control_mode: pus.adcs_housekeeping.control_mode
  :field mjd: pus.adcs_housekeeping.mjd
  :field position_x: pus.adcs_housekeeping.position_x
  :field position_y: pus.adcs_housekeeping.position_y
  :field position_z: pus.adcs_housekeeping.position_z
  :field velocity_x: pus.adcs_housekeeping.velocity_x
  :field velocity_y: pus.adcs_housekeeping.velocity_y
  :field velocity_z: pus.adcs_housekeeping.velocity_z
  :field low: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.low
  :field high: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.high
  :field combined_u5: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.combined_u5
  :field q1: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.q1
  :field q2: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.q2
  :field q3: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.q3
  :field q4_metadata: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.q4_metadata
  :field q4_index: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.q4_index
  :field q4_sign: pus.adcs_housekeeping.estimated_attitude_compressed_quaternion.q4_sign
  :field estimated_angular_rate_x: pus.adcs_housekeeping.estimated_angular_rate_x
  :field estimated_angular_rate_y: pus.adcs_housekeeping.estimated_angular_rate_y
  :field estimated_angular_rate_z: pus.adcs_housekeeping.estimated_angular_rate_z
  :field estimated_magnetometer_bias_x: pus.adcs_housekeeping.estimated_magnetometer_bias_x
  :field estimated_magnetometer_bias_y: pus.adcs_housekeeping.estimated_magnetometer_bias_y
  :field estimated_magnetometer_bias_z: pus.adcs_housekeeping.estimated_magnetometer_bias_z
  :field estimated_gyro_bias_x: pus.adcs_housekeeping.estimated_gyro_bias_x
  :field estimated_gyro_bias_y: pus.adcs_housekeeping.estimated_gyro_bias_y
  :field estimated_gyro_bias_z: pus.adcs_housekeeping.estimated_gyro_bias_z
  :field attitude_variance: pus.adcs_housekeeping.attitude_variance
  :field angular_velocity_variance: pus.adcs_housekeeping.angular_velocity_variance
  :field mag_bias_variance: pus.adcs_housekeeping.mag_bias_variance
  :field gyro_bias_variance: pus.adcs_housekeeping.gyro_bias_variance
  :field magnetometer_measurement_x: pus.adcs_housekeeping.magnetometer_measurement_x
  :field magnetometer_measurement_y: pus.adcs_housekeeping.magnetometer_measurement_y
  :field magnetometer_measurement_z: pus.adcs_housekeeping.magnetometer_measurement_z
  :field gyroscope_measurement_x: pus.adcs_housekeeping.gyroscope_measurement_x
  :field gyroscope_measurement_y: pus.adcs_housekeeping.gyroscope_measurement_y
  :field gyroscope_measurement_z: pus.adcs_housekeeping.gyroscope_measurement_z
  :field sun_vector_measurement_x: pus.adcs_housekeeping.sun_vector_measurement_x
  :field sun_vector_measurement_y: pus.adcs_housekeeping.sun_vector_measurement_y
  :field sun_vector_measurement_z: pus.adcs_housekeeping.sun_vector_measurement_z

  :field event_timestamp: pus.event.timestamp.timestamp
  :field rid: pus.event.rid
  :field info: pus.event.info.b64encstring.info_data_b64_encoded

  :field callsign: repeater.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field ssid_mask: repeater.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: repeater.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign: repeater.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid_raw_ssid_mask: repeater.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: repeater.ax25_header.src_ssid_raw.ssid
  :field ctl: repeater.ax25_header.ctl
  :field pid: repeater.ax25_header.pid
  :field payload: repeater.payload
  :field fcs: repeater.fcs

seq:
  - id: skylink
    type: skylink_frame
  - id: pus
    if: ((skylink.header.vc == 0) or (skylink.header.vc == 1))
    type: foresail_pus_frame
    size: _io.size - _io.pos - 4 * skylink.header.is_authenticated
  - id: repeater
    if: (skylink.header.vc == 3)
    type: ax25_frame
    size: _io.size - _io.pos - 4 * skylink.header.is_crced
  - id: auth
    if: (skylink.header.is_authenticated == 1)
    size: 4
  - id: frame_crc
    if: (skylink.header.is_crced == 1)
    size: 4
    doc: |
      Skylink frame CRC that covers the entire frame. Can be used to validate repeater frames instead of FCS due to onboard unfixable bug.
      This CRC is only sent on virtual channel 3, which is the repeater channel.
    


types:

  sky_static_header:
    doc: 'Skylink static header'
    seq:
      - id: flags
        type: u1
        doc: |
          Flags:
              unsigned int vc : 2; // (LSB)
              unsigned int flag_arq_on : 1; // Avoid confusion with packets around ARQ disconnect event.
              unsigned int flag_authenticated : 1;
              unsigned int flag_crced : 1;
              unsigned int sequence_control : 2;
              unsigned int reserved : 1; // (MSB)
      - id: frame_sequence
        type: u2
        doc: 'Frame sequence number'

      - id: extension_length
        type: u1
        doc: 'Length of the extension field in bytes'

    instances:
      vc:
        value: 'flags & 0b00000011'
      is_arq_on:
        value: (flags & 0b00000100) >> 2
      is_authenticated:
        value: (flags & 0b00001000) >> 3
      is_crced:
        value: (flags & 0b00010000) >> 4
      sequence_control:
        value: (flags & 0b01100000) >> 5

  skylink_frame:
    doc-ref: 'Skylink Protocol Specification.pdf'
    seq:
    - id: version_and_identity_len
      type: u1
    - id: identity
      type: str
      encoding: ASCII
      size: len_identity
      valid: '"OH2F1S"'
    - id: header
      type: sky_static_header
    - id: extensions
      size: header.extension_length

    instances:
      version:
        value: (version_and_identity_len & 0b11111000) >> 3
      len_identity:
        value: version_and_identity_len & 0b00000111

  pus_header:
    doc: 'CCSDS PUS header'
    seq:
      - id: packet_id
        type: u2
      - id: sequence
        type: u2
      - id: length
        type: u2
      - id: secondary_header
        type: u1
      - id: service_type
        type: u1
      - id: service_subtype
        type: u1

  foresail_pus_frame:
    seq:
      - id: header
        type: pus_header
      - id: obc_housekeeping
        type: obc_housekeeping
        if: (header.service_type == 3) and (header.service_subtype == 2)
      - id: eps_housekeeping
        type: eps_housekeeping
        if: (header.service_type == 3) and (header.service_subtype == 3)
      - id: uhf_housekeeping
        type: uhf_housekeeping
        if: (header.service_type == 3) and (header.service_subtype == 4)
      - id: adcs_housekeeping
        type: adcs_housekeeping
        if: (header.service_type == 3) and (header.service_subtype == 5)
      - id: event
        type: event
        if: (header.service_type == 4) and (header.service_subtype == 1 or header.service_subtype == 2 or header.service_subtype == 3 or header.service_subtype == 4)

  pdms:
    seq:
      - id: val
        type: u1
    instances:
      pate_batt:
        value: '((val & 0x01) >> 0)'
      pb_batt:
        value: '((val & 0x02) >> 1)'
      pb_3v6:
        value: '((val & 0x04) >> 2)'
      cam_3v6:
        value: '((val & 0x08) >> 3)'
      mag_3v6:
        value: '((val & 0x10) >> 4)'
      obc_3v6:
        value: '((val & 0x20) >> 5)'
      uhf_3v6:
        value: '((val & 0x40) >> 6)'
      adcs_3v6:
        value: '((val & 0x80) >> 7)'

  unix_timestamp:
    meta:
      endian: be
    doc: 'Unix timestamp'
    seq:
      - id: timestamp
        type: u4

  compressed_quaternion:
    meta:
      endian: le
    seq:
      - id: low
        type: u4
      - id: high
        type: u1
    instances:
      combined_u5:
        value: '(low << 8) | high'
      q1:
        value: '(combined_u5 >> 28) & 0xFFF'
      q2:
        value: '(combined_u5 >> 16) & 0xFFF'
      q3:
        value: '(combined_u5 >> 4) & 0xFFF '
      q4_metadata:
        value: 'combined_u5 & 0xF'
      q4_index:
        value: '(q4_metadata >> 2) & 0x3'
      q4_sign:
        value: '(q4_metadata >> 1) & 0x1'
    doc: |
      Metadata for the last component:
      - 2 bits: Index of the largest component (0-2)
      - 1 bit: Sign of the largest component (0 = positive, 1 = negative)
      - 1 bit: Unused

  obc_housekeeping:
    meta:
      endian: le
    seq:
      - id: timestamp
        type: unix_timestamp
      - id: side
        type: u1
        doc: |
          OBC Redundancy side:
          0 = Side A
          1 = Side B
          2 = Side A Recovery
          3 = Side B Recovery
      - id: fdir_mode
        type: u1
        doc: |
          FDIR mode:
          0 = Nominal
          1 = Safe-mode: Recovery
          2 = Safe-mode: Unstable
          3 = Safe-mode: Low-battery
          9 = Safe-mode: Rebooting
      - id: sys_watchdog_counter
        type: u2
      - id: scheduler
        type: u1
      - id: software_revision
        type: u1
      - id: uptime
        type: u4
        doc: '[seconds]'

      - id: heap_free
        type: u1
        doc: 'value = 0.39215686274509803 * heap [%]'
      - id: cpu_load
        type: u1
        doc: 'value = 0.39215686274509803 * heap [%]'
      - id: fs_free_space
        type: u2
        doc: 'value = 4 * fs_used [kBytes]'

      - id: arbiter_uptime
        type: u2
        doc: '[seconds]'
      - id: arbiter_age
        type: u2
      - id: arbiter_bootcount
        type: u2
      - id: arbiter_temperature
        type: s2
        doc: 'value = arbiter_temperature / 10 [°C]'

      - id: side_a_bootcount
        type: u1
      - id: side_a_heartbeat
        type: u1
      - id: side_a_fail_counter
        type: u1
      - id: side_a_fail_reason
        type: u1

      - id: side_b_bootcount
        type: u1
      - id: side_b_heartbeat
        type: u1
      - id: side_b_fail_counter
        type: u1
      - id: side_b_fail_reason
        type: u1

      - id: arbiter_log_1
        type: u2
      - id: arbiter_log_2
        type: u2
      - id: arbiter_log_3
        type: u2
      - id: arbiter_log_4
        type: u2


  eps_housekeeping:
    meta:
      endian: le
    seq:
      - id: timestamp
        type: unix_timestamp

      - id: pcdu_uptime
        type: u4
        doc: 'PCDU uptime in seconds'

      - id: pcdu_boot_count
        type: u1
        doc: 'PCDU Boot Count'

      - id: bb_boot_count
        type: u1
        doc: 'Battery Board Boot Count'

      - id: apr_boot_count
        type: u1
        doc: 'APR Boot Count'

      - id: pdm_expected
        type: u1
        doc: |
          Power delivery switch expected states:
          1   = PATE_BATT
          2   = PB_BATT
          4   = PB_3V6
          8   = CAM_3V6
          16  = MAG_3V6
          32  = OBC_3V6
          64  = UHF_3V6
          128 = ADCS_3V6

      - id: pdm_faulted
        type: u1
        doc: |
          Power delivery switch fault state bitmask:
          1   = PATE_BATT
          2   = PB_BATT
          4   = PB_3V6
          8   = CAM_3V6
          16  = MAG_3V6
          32  = OBC_3V6
          64  = UHF_3V6
          128 = ADCS_3V6

      - id: padding_byte
        type: u1

      - id: eps_subsystem_state
        type: u2
        doc: |
          EPS subsystem state bitmask:
          { "value": 0,  "mask": 1,  "string": "BB OFF" },
          { "value": 1,  "mask": 1,  "string": "BB ON" },
          { "value": 0,  "mask": 14,  "string": "HEATER OFF" },
          { "value": 2,  "mask": 14,  "string": "HEATER ON" },
          { "value": 4,  "mask": 14,  "string": "HEATER FORCE_ON" },
          { "value": 0,  "mask": 112,  "string": "BALANCER OFF" },
          { "value": 16,  "mask": 112,  "string": "DISCHARGING LOWER CELLS" },
          { "value": 32,  "mask": 112,  "string": "DISCHARGING UPPER CELLS" },
          { "value": 0,  "mask": 128,  "string": "APR OFF" },
          { "value": 128,  "mask": 128,  "string": "APR ON" },
          { "value": 0,  "mask": 768,  "string": "APR X MPPT" },
          { "value": 256,  "mask": 768,  "string": "APR X MANUAL" },
          { "value": 512,  "mask": 768,  "string": "APR X MPPT" },
          { "value": 0,  "mask": 3072,  "string": "APR Y MPPT" },
          { "value": 1024,  "mask": 3072,  "string": "APR Y MANUAL" },
          { "value": 2048,  "mask": 3072,  "string": "APR Y MPPT" },
          { "value": 0,  "mask": 12288,  "string": "SCOPE IDLE" },
          { "value": 4096,  "mask": 12288,  "string": "SCOPE SCAN" },
          { "value": 8192,  "mask": 12288,  "string": "SCOPE TRACE" },
          { "value": 0,  "mask": 16384,  "string": "SCOPE MEM RDY" },
          { "value": 16384,  "mask": 16384,  "string": "SCOPE MEM BUSY" }

      - id: heater_pwm_on_time
        type: u2
      - id: current_apr_x
        type: s2
      - id: current_apr_y
        type: s2
      - id: voltage_apr_x
        type: s2
      - id: voltage_apr_y
        type: s2

      - id: current_apr_x_at_mpp
        type: s2
        doc: 'X+ Charger Max Current'

      - id: voltage_apr_x_at_mpp
        type: s2
        doc: 'X+ Panel Max Voltage'

      - id: current_apr_y_at_mpp
        type: s2
        doc: 'Y+ Charger Max Current'

      - id: voltage_apr_y_at_mpp
        type: s2
        doc: 'Y+ Panel Max Voltage'

      - id: voltage_battery
        type: s2
        doc: 'Battery Pack Voltage'

      - id: voltage_battery_lower
        type: s2
        doc: 'Battery Pack Lower Cell Voltage'

      - id: voltage_payloads
        type: s2
        doc: 'Payload Buck Output Voltage'

      - id: voltage_obc_adcs
        type: s2
        doc: 'OBC/ADCS Buck Output Voltage'

      - id: voltage_uhf
        type: s2

      - id: temperature_mcu_pcdu
        type: s2
        doc: 'PCDU MCU Temperature [deci°C]'

      - id: temperature_mcu_bb
        type: s2
        doc: 'BB MCU Temperature [deci°C]'

      - id: temperature_mcu_apr
        type: s2
        doc: 'APR MCU Temperature [deci°C]'

      - id: temperature_battery
        type: s2
        doc: 'Battery Pack Temperature [deci°C]'

      - id: temperature_sp_x_minus
        type: s2
        doc: 'X- Panel Temperature [deci°C]'

      - id: temperature_sp_x_plus
        type: s2
        doc: 'X+ Panel Temperature [deci°C]'

      - id: temperature_sp_y_minus
        type: s2
        doc: 'Y- Panel Temperature [deci°C]'

      - id: temperature_sp_y_plus
        type: s2
        doc: 'Y+ Panel Temperature [deci°C]'

      - id: current_battery
        type: s2
        doc: 'Battery Pack Current [mA]'

      - id: current_battery_min
        type: s2
        doc: 'Battery Pack Min Current [mA]'

      - id: current_battery_max
        type: s2
        doc: 'Battery Pack Max Current [mA]'

      - id: current_pate_batt
        type: s2
        doc: 'PATE Batt Current [mA]'

      - id: current_pb_batt
        type: s2
        doc: 'Plasma Brake Batt Current [mA]'

      - id: current_pb_3v6
        type: s2
        doc: 'Plasma Brake 3.6V Current [mA]'

      - id: current_cam_3v6
        type: s2
        doc: 'CAM 3.6V Current [mA]'

      - id: current_mag_3v6
        type: s2
        doc: 'MAG 3.6V Current [mA]'

      - id: current_obc_3v6
        type: s2
        doc: 'OBC 3.6V Current [mA]'

      - id: current_uhf_3v6
        type: s2
        doc: 'UHF 3.6V Current [mA]'

      - id: current_adcs_3v6
        type: s2
        doc: 'ADCS 3.6V Current [mA]'

      - id: current_min_pate
        type: s2
        doc: 'PATE Batt Min Current [mA]'

      - id: current_min_pb_batt
        type: s2
        doc: 'Plasma Brake Batt Min Current [mA]'

      - id: current_min_pb_3v6
        type: s2
        doc: 'Plasma Brake 3.6V Min Current [mA]'

      - id: current_min_cam_3v6
        type: s2
        doc: 'CAM 3.6V Min Current [mA]'

      - id: current_min_mag_3v6
        type: s2
        doc: 'MAG 3.6V Min Current [mA]'

      - id: current_min_obc_3v6
        type: s2
        doc: 'OBC 3.6V Min Current [mA]'

      - id: current_min_uhf_3v6
        type: s2
        doc: 'UHF 3.6V Min Current [mA]'

      - id: current_min_adcs_3v6
        type: s2
        doc: 'ADCS 3.6V Min Current [mA]'

      - id: current_max_pate
        type: s2
        doc: 'PATE Batt Max Current [mA]'

      - id: current_max_pb_batt
        type: s2
        doc: 'Plasma Brake Batt Max Current [mA]'

      - id: current_max_pb_3v6
        type: s2
        doc: 'Plasma Brake 3.6V Max Current [mA]'

      - id: current_max_cam_3v6
        type: s2
        doc: 'CAM 3.6V Max Current [mA]'

      - id: current_max_mag_3v6
        type: s2
        doc: 'MAG 3.6V Max Current [mA]'

      - id: current_max_obc_3v6
        type: s2
        doc: 'OBC 3.6V Max Current [mA]'

      - id: current_max_uhf_3v6
        type: s2
        doc: 'UHF 3.6V Max Current [mA]'

      - id: current_max_adcs_3v6
        type: s2
        doc: 'ADCS 3.6V Max Current [mA]'

  uhf_housekeeping:
    meta:
      endian: le
    seq:
      - id: timestamp
        type: unix_timestamp

      - id: uptime
        type: u4
        doc: '[seconds]'

      - id: bootcount
        type: u2

      - id: fdir_counter
        type: u1
        doc: "UHF FDIR Reset Counter"

      - id: mcu_wd_reset_count
        type: u1
        doc: "MCU Watchdog Reset Count"

      - id: mbe_count
        type: u1
        doc: "Memory Boot Error Count"

      - id: bus_sync_errors
        type: u1

      - id: bus_len_errors
        type: u1

      - id: bus_crc_errors
        type: u1

      - id: bus_receive_timeouts
        type: u1

      - id: total_tx_frames
        type: u4

      - id: total_rx_frames
        type: u4

      - id: total_ham_tx_frames
        type: u4

      - id: total_ham_rx_frames
        type: u4

      - id: hardware_side_a_bootcount
        type: u1
        doc: 'Hardware Side A Boot Count'

      - id: hardware_side_b_bootcount
        type: u1
        doc: 'Hardware Side B Boot Count'

      - id: side
        type: u1
        doc: |
          UHF Redundancy side:
          0 = Side A
          1 = Side B

      - id: symbol_rate_rx
        type: u1
        doc: |
          UHF RX Mode:
          0 = GFSK 4800
          1 = GFSK 9600
          2 = GFSK 19200
          3 = GFSK 38400

      - id: symbol_rate_tx
        type: u1
        doc: |
          UHF TX Mode:
          0 = GFSK 4800
          1 = GFSK 9600
          2 = GFSK 19200
          3 = GFSK 38400

      - id: my_window_length
        type: u4
        doc: 'Current own Skylink Window Length [ms]'

      - id: peer_window_length
        type: u4
        doc: 'Current peer Skylink Window Length [ms]'

      - id: mcu_temperature
        type: s2
        doc: 'UHF MCU Temperature [deci°C]'

      - id: pa_temperature
        type: s2
        doc: 'UHF PA Temperature [deci°C]'

      - id: background_rssi
        type: s2
        doc: 'UHF Background RSSI [dBm]'

      - id: background_max_rssi
        type: s2
        doc: 'UHF Background Max RSSI [dBm]'

      - id: last_rssi
        type: s2
        doc: 'UHF Last RSSI [dBm]'

      - id: last_freq_offset
        type: s2
        doc: 'UHF Last Frequency Offset [Hz]'

  adcs_housekeeping:
    meta:
      endian: le
    seq:
      - id: timestamp
        type: unix_timestamp

      - id: determination_mode
        type: u1
        doc: |
          ADCS Determination algorithm:
          0 = Off
          1 = Triad
          2 = Kalman

      - id: control_mode
        type: u1
        doc: |
          ADCS Control algorithm:
          0 = Off
          1 = BDOT
          2 = Ruiter
          3 = Attitude_PD

      - id: mjd
        type: f4
        doc: 'Modified Julian Date'

      - id: position_x
        type: f4
        doc: 'Satellite position in ECI frame [km]'

      - id: position_y
        type: f4
        doc: 'Satellite position in ECI frame [km]'

      - id: position_z
        type: f4
        doc: 'Satellite position in ECI frame [km]'

      - id: velocity_x
        type: f4
        doc: 'Satellite velocity in ECI frame [km/s]'

      - id: velocity_y
        type: f4
        doc: 'Satellite velocity in ECI frame [km/s]'

      - id: velocity_z
        type: f4
        doc: 'Satellite velocity in ECI frame [km/s]'

      - id: estimated_attitude_compressed_quaternion
        type: compressed_quaternion
        doc: |
          Compressed Estimated Attitude Quaternion (5 bytes)
          3 of the smallest components normalized to the range [0, 1] from the known range of +-1/sqrt(2)
          After this the components are quantized to 12 bits
          After 3 components the index of the largest component is stored in 2 bits and sign of it in 1 bit with 1 bit left unused
          Note: Not yet known which component this is due to it not being known which is largest and thus calculated

      - id: estimated_angular_rate_x
        type: u2
        doc: Estimated Angular Rate in Spacecraft [millirad/s]

      - id: estimated_angular_rate_y
        type: u2
        doc: Estimated Angular Rate in Spacecraft [millirad/s]

      - id: estimated_angular_rate_z
        type: u2
        doc: Estimated Angular Rate in Spacecraft [millirad/s]

      - id: estimated_magnetometer_bias_x
        type: u2
        doc: 'Estimated Magnetometer Bias X [microT]'

      - id: estimated_magnetometer_bias_y
        type: u2
        doc: 'Estimated Magnetometer Bias Y [microT]'

      - id: estimated_magnetometer_bias_z
        type: u2
        doc: 'Estimated Magnetometer Bias Z [microT]'

      - id: estimated_gyro_bias_x
        type: u2
        doc: 'Estimated Gyro Bias X [millirad/s]'

      - id: estimated_gyro_bias_y
        type: u2
        doc: 'Estimated Gyro Bias Y [millirad/s]'

      - id: estimated_gyro_bias_z
        type: u2
        doc: 'Estimated Gyro Bias Z [millirad/s]'

      - id: attitude_variance
        type: u2
        doc: 'UKF state covariances attitude [value*1000]'

      - id: angular_velocity_variance
        type: u2
        doc: 'UKF state covariances angular velocity [value*1000]'

      - id: mag_bias_variance
        type: u2
        doc: 'UKF state covariances magnetometer bias [value*1000]'

      - id: gyro_bias_variance
        type: u2
        doc: 'UKF state covariances gyroscope bias [value*1000]'

      - id: magnetometer_measurement_x
        type: s2
        doc: 'Magnetometer measurement X [microT]'

      - id: magnetometer_measurement_y
        type: s2
        doc: 'Magnetometer measurement Y [microT]'

      - id: magnetometer_measurement_z
        type: s2
        doc: 'Magnetometer measurement Z [microT]'

      - id: gyroscope_measurement_x
        type: s2
        doc: 'Gyroscope measurement X [millirad/s]'

      - id: gyroscope_measurement_y
        type: s2
        doc: 'Gyroscope measurement Y [millirad/s]'

      - id: gyroscope_measurement_z
        type: s2
        doc: 'Gyroscope measurement Z [millirad/s]'

      - id: sun_vector_measurement_x
        type: s2
        doc: 'Sun vector measurement X [(unit vector)*100]'

      - id: sun_vector_measurement_y
        type: s2
        doc: 'Sun vector measurement Y [(unit vector)*100]'

      - id: sun_vector_measurement_z
        type: s2
        doc: 'Sun vector measurement Z [(unit vector)*100]'

  event:
    seq:
    - id: timestamp
      type: unix_timestamp
    - id: rid
      type: u2
    - id: info
      type: base64
      size-eos: true
    types:
      base64:
        seq:
          - id: b64encstring
            process: satnogsdecoders.process.b64encode
            type: base64string
            size-eos: true
      base64string:
        seq:
          - id: info_data_b64_encoded
            type: str
            encoding: UTF-8
            size-eos: true


  ax25_frame:
    doc-ref: 'https://www.tapr.org/pub_ax25.html'
    seq:
      - id: ax25_header
        type: ax25_header
      - id: payload
        type: str
        encoding: ASCII
        size: _io.size - _io.pos - 2
      - id: fcs
        type: u2
        doc: |
          Due to an unpatchable bug onboard only the second byte is correct and the first one will be from the frame received by the satellite.
          Can use skylink frame CRC to check validity of frame instead.

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
      - id: digipeaters
        type: digipeater
        repeat: until
        repeat-until: (_.ssid_raw.ssid_mask & 0x01) != 0
        if: (src_ssid_raw.ssid_mask & 0x01) == 0
      - id: ctl
        type: u1
        valid:
          eq: 0x03
      - id: pid
        type: u1
        valid:
          eq: 0xF0

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
        value: (ssid_mask & 0x0f) >> 1

  digipeater:
    seq:
      - id: callsign_raw
        type: callsign_raw
      - id: ssid_raw
        type: ssid_mask
    instances:
      has_been_repeated:
        value: (ssid_raw.ssid_mask & 0x80) != 0
