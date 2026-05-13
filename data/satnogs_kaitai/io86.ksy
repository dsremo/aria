---
meta:
  id: io86
  title: IO-86 (LAPAN-A2, Orari) Digi and VHF Telemetry Decoder
  endian: be
#  2024-09-21, DL7NDR
doc: |
  :field telemetry_beacon: io86.type_check.ax25_frame.payload.ax25_info.telemetry_beacon
  :field counter: io86.type_check.ax25_frame.payload.ax25_info.counter
  :field analog1: io86.type_check.ax25_frame.payload.ax25_info.analog1
  :field analog2: io86.type_check.ax25_frame.payload.ax25_info.analog2
  :field analog3: io86.type_check.ax25_frame.payload.ax25_info.analog3
  :field analog4: io86.type_check.ax25_frame.payload.ax25_info.analog4
  :field analog5: io86.type_check.ax25_frame.payload.ax25_info.analog5
  :field digital1: io86.type_check.ax25_frame.payload.ax25_info.digital1
  :field digital2: io86.type_check.ax25_frame.payload.ax25_info.digital2
  :field digital3: io86.type_check.ax25_frame.payload.ax25_info.digital3
  :field digital4: io86.type_check.ax25_frame.payload.ax25_info.digital4
  :field digital5: io86.type_check.ax25_frame.payload.ax25_info.digital5
  :field digital6: io86.type_check.ax25_frame.payload.ax25_info.digital6
  :field digital7: io86.type_check.ax25_frame.payload.ax25_info.digital7
  :field digital8: io86.type_check.ax25_frame.payload.ax25_info.digital8
  :field dest_callsign: io86.type_check.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: io86.type_check.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: io86.type_check.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: io86.type_check.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: io86.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: io86.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: io86.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field ctl: io86.type_check.ax25_frame.ax25_header.ctl
  :field pid: io86.type_check.ax25_frame.payload.pid
  :field monitor: io86.type_check.ax25_frame.payload.ax25_info.data_monitor

seq:
  - id: io86
    type: io86_t

types:
  io86_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x5423: telemetry # T#
            _: digi

    instances:
        check:
              type: u2
              pos: 23

  telemetry:
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
          - id: telemetry
            type: str
            encoding: ASCII
            size: 2
            valid: '"T#"'
          - id: counter_ascii
            type: str
            encoding: ASCII
            terminator: 0x2C # ","
          - id: analog1_ascii
            type: str
            encoding: ASCII
            terminator: 0x2C # ","
          - id: analog2_ascii
            type: str
            encoding: ASCII
            terminator: 0x2C # ","
          - id: analog3_ascii
            type: str
            encoding: ASCII
            terminator: 0x2C # ","
          - id: analog4_ascii
            type: str
            encoding: ASCII
            terminator: 0x2C # ","
          - id: analog5_ascii
            type: str
            encoding: ASCII
            terminator: 0x2C # ","
          - id: digital1_ascii
            type: str
            encoding: ASCII
            size: 1
          - id: digital2_ascii
            type: str
            encoding: ASCII
            size: 1
          - id: digital3_ascii
            type: str
            encoding: ASCII
            size: 1
          - id: digital4_ascii
            type: str
            encoding: ASCII
            size: 1
          - id: digital5_ascii
            type: str
            encoding: ASCII
            size: 1
          - id: digital6_ascii
            type: str
            encoding: ASCII
            size: 1
          - id: digital7_ascii
            type: str
            encoding: ASCII
            size: 1
          - id: digital8_ascii
            type: str
            encoding: ASCII
            size: 1

        instances:
               telemetry_beacon:
                 value:  telemetry + counter_ascii + "," + analog1_ascii + "," + analog2_ascii + "," + analog3_ascii + "," + analog4_ascii + "," + analog5_ascii + "," + digital1_ascii + digital1_ascii + digital3_ascii + digital4_ascii + digital5_ascii + digital6_ascii + digital7_ascii + digital8_ascii

               counter:
                 value:  counter_ascii.to_i

               analog1:
                 value:  analog1_ascii.to_i

               analog2:
                 value:  analog2_ascii.to_i

               analog3:
                 value:  analog3_ascii.to_i

               analog4:
                 value:  analog4_ascii.to_i

               analog5:
                 value:  analog5_ascii.to_i

               digital1:
                 value:  digital1_ascii.to_i

               digital2:
                 value:  digital2_ascii.to_i

               digital3:
                 value:  digital3_ascii.to_i

               digital4:
                 value:  digital4_ascii.to_i

               digital5:
                 value:  digital5_ascii.to_i

               digital6:
                 value:  digital6_ascii.to_i

               digital7:
                 value:  digital7_ascii.to_i

               digital8:
                 value:  digital8_ascii.to_i


  digi:
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
