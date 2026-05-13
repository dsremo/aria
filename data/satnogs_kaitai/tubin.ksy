meta:
  id: tubin
  title: TUBIN telemetry decoder struct
  endian: be
doc-ref: |
    'https://www.tu.berlin/en/raumfahrttechnik/institute/amateur-radio'
    'https://www.static.tu.berlin/fileadmin/www/10002275/Amateur_Radio/TechnoSat_Telemetry_Format.ods'

doc: |
  :field msgtype: mf.msgtype
  :field block_length: mf.block_length
  :field target_address: mf.target_address
  :field target_sub_address: mf.target_sub_address
  :field ack_flag: mf.ack_flag
  :field baudrate_flag: mf.baudrate_flag
  :field callsign: mf.callsign
  :field callsign_crc: mf.callsign_crc
  :field scid: mf.tf.scid
  :field version: mf.tf.version
  :field counter: mf.tf.counter

  :field spcrc: mf.tf.sp.spcrc
  :field gs_quality_byte: mf.gs_quality_byte
  :field gs_error_marker: mf.gs_error_marker
  :field gs_tnc_temperature: mf.gs_tnc_temperature
seq:
  - id: mf
    doc: Master Frame
    type: master_frame

types:
  master_frame:
    seq:
      - id: msgtype
        doc: |
          Message Type
          0x0 = ACK,
          0x1 = Regular (TM/TC),
          0x7 = Error Correction
        type: b3
      - id: block_length
        doc: |
          Block Length
          Number of Mobitex Data Blocks in User Data
        type: b5
      - id: target_address
        doc: |
          Target Address
          0x0 = G/S,
          0xF = Broadcast
        type: b4
      - id: target_sub_address
        doc: |
          Target Sub-Address
          0x0 = Primary G/S,
          0x1 = Secondary G/S,
          0x3 = Broadcast
        type: b2
      - id: ack_flag
        doc: Acknowledge Flag
        type: b1
      - id: baudrate_flag
        doc: |
          Baudrate Flag
          0b0 = 4k8 bps,
          0b1 = 9k6 bps
        type: b1
      - id: callsign
        doc: S/C Callsign
        type: strz
        encoding: ascii
        size: 6
        valid: '"DP0TBN"'
      - id: callsign_crc
        doc: CRC16 of the Callsign
        type: u2
      - id: tf
        doc: Transfer frame
        type: transfer_frame
        size: "(block_length + 1) * 18"
      - id: gs_quality_byte
        doc: (GS) Quality Byte
        type: u1
      - id: gs_error_marker
        doc: (GS) Error Marker
        type: u4
      - id: gs_tnc_temperature
        doc: (GS) TNC Temperature
        type: u1

  transfer_frame:
    seq:
      - id: scid
        type: b12
        doc: |
          The S/C‘s unique identifier
      - id: version
        type: b4
        doc: |
          TF-Version Number
      - id: counter
        type: u2
        doc: |
          Incremental TF counter
      - id: sp
        doc: Source Packets
        type: source_packet
        repeat: until
        repeat-until: _io.pos >= _io.size or _.length_msb == 0xFF
      - id: tfpad
        size-eos: true
  source_packet:
    seq:
      - id: length_msb
        type: u1
      - id: length_lsb
        type: u1
        if: length_msb != 0xFF
      - id: padding
        size-eos: true
        if: length_msb == 0xFF
      - id: vcid
        doc: |
          Virtual Channel Identifier
          Virtual Channel for this SP
        type: b4
        if: length_msb != 0xFF
      - id: rtfrac
        doc: |
          Recording Time Fraction
          10th of seconds of the Recording Time
        type: b4
        if: length_msb != 0xFF
      - id: rtsec
        doc: |
          Recording Time Seconds
          SP Recording Time in seconds since 01.01.2000
        type: u4
        if: length_msb != 0xFF
      - id: nodid
        doc: |
          Node of Origin
          The recording node of this SP
        type: u1
        if: length_msb != 0xFF
      - id: spid
        doc: |
          Source Packet Identifier
          Identification Number of the SP
        type: u1
        if: length_msb != 0xFF
      - id: user_data
        doc: |
          Source Packet User data
            - id: content
        size: splen
        type:
          switch-on: spid
          cases:
            16: sp_type16
            21: sp_type21
            41: sp_type41
            60: sp_std_tm_aocs
            131: sp_tm_aocs_state_estimation_a
            249: sp_type249
        if: length_msb != 0xFF
      - id: spcrc
        doc: |
          Source Packet CRC
          CRC over all fields of the SP except SPCRC itself
        type: u2
        if: length_msb != 0xFF
    instances:
      splen:
        value: '(length_msb << 8) | (length_msb != 0xFF ? length_lsb : 0)'
        if: length_msb != 0xFF
  sp_type16:
    seq:
      - id: data
        size: 16
  sp_type21:
    seq:
      - id: data
        size: 28
  sp_type41:
    doc: |
      Standard AOCS data
    seq:
      - id: data
        size: 7
  sp_std_tm_aocs:
    doc: |
      Type 60
    seq:
      - id: nodeno
        type: b1
      - id: rst_en
        doc: |
          WTD Reset Enabled
        type: b1
      - id: botslt
        doc: |
          Boot Slot
          0=#0;
          1=#1;
          2=#2;
          3=#3;
          7=BOOT
        type: b3
      - id: synpps
        type: b1
      - id: disutc
        type: b1
      - id: dulbsy
        type: b1
      - id: acs_mode
        type: b5be
        doc: |
          0=DIAGNOSIS
          1=MANUAL
          2=SUSPEND
          3=DAMPING_BDOT
          4=DAMPING_CROSS
          5=NADIR_COARSE
          6=NADIR_FINE
          7=INERTIAL_COARSE
          8=INERTIAL_FINE
          9=RATE_CONTROL
      - id: mfs_received
        type: b1
      - id: sss_received
        type: b1
      - id: gyr_received
        type: b1
      - id: for_received
        type: b1
      - id: str_received
        type: b1
      - id: res_1_bit
        type: b1
      - id: mts_received
        type: b1
      - id: rw0_received
        type: b1
      - id: rw1_received
        type: b1
      - id: rw2_received
        type: b1
      - id: rw3_received
        type: b1
      - id: std_q_s
        type: s2
      - id: std_q_x
        type: s2
      - id: std_q_y
        type: s2
      - id: std_q_z
        type: s2
      - id: std_rate_x
        type: s1
      - id: std_rate_y
        type: s1
      - id: std_rate_z
        type: s1
      - id: std_r_x
        type: s1
      - id: std_r_y
        type: s1
      - id: std_r_z
        type: s1
  sp_tm_aocs_state_estimation_a:
    seq:
      - id: esta_q_s
        type: s4
      - id: esta_q_x
        type: s4
      - id: esta_q_y
        type: s4
      - id: esta_q_z
        type: s4
      - id: esta_rate_x
        type: s2
      - id: esta_rate_y
        type: s2
      - id: esta_rate_z
        type: s2
      - id: esta_acc_x
        type: s2
      - id: esta_acc_y
        type: s2
      - id: esta_acc_z
        type: s2
      - id: esta_b_sat_x
        type: s2
      - id: esta_b_sat_y
        type: s2
      - id: esta_b_sat_z
        type: s2
      - id: esta_s_sat_x
        type: s2
      - id: esta_s_sat_y
        type: s2
      - id: esta_s_sat_z
        type: s2
      - id: esta_b_tod_x
        type: s2
      - id: esta_b_tod_y
        type: s2
      - id: esta_b_tod_z
        type: s2
      - id: esta_s_tod_x
        type: s2
      - id: esta_s_tod_y
        type: s2
      - id: esta_s_tod_z
        type: s2
      - id: esta_r_x
        type: s2
      - id: esta_r_y
        type: s2
      - id: esta_r_z
        type: s2
      - id: esta_v_x
        type: s2
      - id: esta_v_y
        type: s2
      - id: esta_v_z
        type: s2
      - id: esta_occultatio
        type: u1
  sp_type249:
    seq:
      - id: data
        size: 3
