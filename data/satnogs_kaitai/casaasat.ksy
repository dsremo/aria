---
meta:
  id: casaasat
  title: CASAA-Sat Telemetry Decoder (dosimeter + magnetic field)
  endian: be 
doc-ref: https://site.amsat-f.org/download/120557/?tmstv=1735221517
# 2024-12-26, DL7NDR
doc: |
  :field dest_callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field frame_id: ax25_frame.ax25_info.frame_id
  :field checksum: ax25_frame.ax25_info.checksum
  :field tm_code: ax25_frame.ax25_info.tm_code
  :field count: ax25_frame.ax25_info.count
  :field values___date: ax25_frame.ax25_info.values.___.type_check.date
  :field values___dosim_x1: ax25_frame.ax25_info.values.___.type_check.dosim_x1
  :field values___dosim_x2: ax25_frame.ax25_info.values.___.type_check.dosim_x2
  :field values___dosim_z1: ax25_frame.ax25_info.values.___.type_check.dosim_z1
  :field values___dosim_z2: ax25_frame.ax25_info.values.___.type_check.dosim_z2
  :field values___dosim_y1: ax25_frame.ax25_info.values.___.type_check.dosim_y1
  :field values___dosim_y2: ax25_frame.ax25_info.values.___.type_check.dosim_y2
  :field values___field_plus_y: ax25_frame.ax25_info.values.___.type_check.field_plus_y
  :field values___field_plus_x: ax25_frame.ax25_info.values.___.type_check.field_plus_x
  :field values___field_minus_z: ax25_frame.ax25_info.values.___.type_check.field_minus_z
  :field values___raw_minus_y: ax25_frame.ax25_info.values.___.type_check.raw_minus_y
  :field values___raw_minus_x: ax25_frame.ax25_info.values.___.type_check.raw_minus_x
  :field values___raw_minus_z: ax25_frame.ax25_info.values.___.type_check.raw_minus_z
  :field values___gain: ax25_frame.ax25_info.values.___.type_check.gain

seq:
  - id: ax25_frame
    type: ax25_frame

types:
  ax25_frame:
    seq:
      - id: ax25_header
        type: ax25_header
      - id: ax25_info
        type: ax25_info_data
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

  ax25_info_data:
    seq:
      - id: frame_id
        type: u2

      - id: checksum
        type: u4

      - id: tm_code
        type: u1
        valid:
          any-of: [0x8a, 0x8b]

      - id: count
        type: u1

      - id: values
        type: values_t
        repeat: expr
        repeat-expr: count

    types:
      values_t:
        seq:
          - id: type_check
            type:
              switch-on: tm_code_switch
              cases:
               0x8a: dosimeter
               0x8b: magnetic_field

        instances:
            tm_code_switch:
                  type: u1
                  pos: 6

      dosimeter:
        seq:
          - id: date # in 1/10 seconds from 2020-01-01 00:00:00 on
            type: u4

          - id: dosim_x1
            type: u2

          - id: dosim_x2
            type: u2

          - id: dosim_z1
            type: u2

          - id: dosim_z2
            type: u2

          - id: dosim_y1
            type: u2

          - id: dosim_y2
            type: u2


      magnetic_field:
        seq:
          - id: date # in 1/10 seconds from 2020-01-01 00:00:00 on
            type: u4

          - id: field_plus_y
            type: u4

          - id: field_plus_x
            type: u4

          - id: field_minus_z
            type: u4

          - id: raw_minus_y
            type: u2

          - id: raw_minus_x
            type: u2

          - id: raw_minus_z
            type: u2

          - id: gain
            type: u1
