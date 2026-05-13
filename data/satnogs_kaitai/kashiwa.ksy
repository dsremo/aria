---
meta:
  id: kashiwa
  title: Kashiwa CW beacon + APRS decoder
  endian: be
#  doc-ref: https://sites.google.com/view/gardens-02/english_ver/document/transmission-format
#  2024-07-12, DL7NDR
doc: |
  :field batt_v: kashiwa.type_check.batt_v
  :field batt_i: kashiwa.type_check.batt_i
  :field batt_t: kashiwa.type_check.batt_t
  :field bpb_t: kashiwa.type_check.bpb_t
  :field raw_i: kashiwa.type_check.raw_i
  :field lcl_5v0: kashiwa.type_check.lcl_5v0
  :field lcl_depand: kashiwa.type_check.lcl_depand
  :field lcl_compic: kashiwa.type_check.lcl_compic
  :field sap_minus_x: kashiwa.type_check.sap_minus_x
  :field sap_plus_y: kashiwa.type_check.sap_plus_y
  :field sap_minus_y: kashiwa.type_check.sap_minus_y
  :field sap_plus_z: kashiwa.type_check.sap_plus_z
  :field sap_minus_z: kashiwa.type_check.sap_minus_z
  :field sap_minus_z: kashiwa.type_check.sap_minus_z
  :field reserve: kashiwa.type_check.reserve
  :field reserve_cmd_counter: kashiwa.type_check.reserve_cmd_counter
  :field gmsk_cmd_counter: kashiwa.type_check.gmsk_cmd_counter
  :field kill_counter: kashiwa.type_check.kill_counter
  :field kill_sw: kashiwa.type_check.kill_sw
  :field boss_on_off: kashiwa.type_check.boss_on_off
  :field ack_mis_end: kashiwa.type_check.ack_mis_end
  :field ack_mis_error: kashiwa.type_check.ack_mis_error
  :field ack_mis_mog: kashiwa.type_check.ack_mis_mog
  :field mis_iss: kashiwa.type_check.mis_iss
  :field beacon_field: kashiwa.type_check.beacon_field
  :field dest_callsign: kashiwa.type_check.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: kashiwa.type_check.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: kashiwa.type_check.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: kashiwa.type_check.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: kashiwa.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: kashiwa.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: kashiwa.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field ctl: kashiwa.type_check.ax25_frame.ax25_header.ctl
  :field pid: kashiwa.type_check.ax25_frame.payload.pid
  :field monitor: kashiwa.type_check.ax25_frame.payload.ax25_info.data_monitor

seq:
  - id: kashiwa
    type: kashiwa_t

types:
  kashiwa_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x4A5331594D584B41: cw # JS1YMXKA
            0x6A7331796D786B61: cw # js1ymxka
            0x4A4736594257304A: special_beacon # JG6YBW0JG6YMX
            _: aprs # everything else

    instances:
        check:
              type: u8
              pos: 0

  cw:
    seq:
      - id: callsign_and_satellite_name
        type: str
        size: 13
        encoding: ASCII
        valid:
         any-of:
           - '"JS1YMXKASHIWA"'
           - '"js1ymxkashiwa"'
      - id: batt_v
        type: u1
      - id: batt_i
        type: u1
      - id: batt_t
        type: u1
      - id: bpb_t
        type: u1
      - id: raw_i
        type: u1
      - id: lcl_5v0
        type: b1
      - id: lcl_depand
        type: b1
      - id: lcl_compic
        type: b1
      - id: sap_minus_x
        type: b1
      - id: sap_plus_y
        type: b1
      - id: sap_minus_y
        type: b1
      - id: sap_plus_z
        type: b1
      - id: sap_minus_z
        type: b1
      - id: reserve
        type: b1
      - id: reserve_cmd_counter
        type: b4
      - id: gmsk_cmd_counter
        type: b3
      - id: kill_counter
        type: b2
      - id: kill_sw
        type: b1
      - id: boss_on_off
        type: b1
      - id: ack_mis_end
        type: b1
      - id: ack_mis_error
        type: b1
      - id: ack_mis_mog
        type: b1
      - id: mis_iss
        type: b1

  special_beacon:
    seq:
      - id: dest_source_callsign
        type: str
        size: 14
        encoding: ASCII
        valid:
         any-of:
           - '"JG6YBW0JG6YMX0"'
      - id: ctl_pid
        type: u2
      - id: beacon_field
        type: str
        encoding: UTF-16BE
        size-eos: true

  aprs:
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

      ssid_mask:
        seq:
          - id: ssid_mask
            type: u1
        instances:
          ssid:
            value: (ssid_mask & 0x0f) >> 1
          hbit:
            value: (ssid_mask & 0x80) >> 7

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

      ax25_info_data:
        seq:
          - id: data_monitor
            type: str
            encoding: utf-8
            size-eos: true
