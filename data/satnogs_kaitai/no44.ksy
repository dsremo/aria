---
meta:
  id: no44
  title: NO-44 (PCSAT, 26931) decoder
  endian: be
#  doc-ref: http://www.aprs.org/pcsat/tlm-eqns.htm
#  2024-06-29, DL7NDR
#  2025-03-14, DL7NDR (corrections)
doc: |
  :field counter: no44.type_check.counter
  :field current_plus_x: no44.type_check.current_plus_x
  :field current_plus_z: no44.type_check.current_plus_z
  :field current_plus_y: no44.type_check.current_plus_y
  :field current_minus_x: no44.type_check.current_minus_x
  :field temp_plus_y: no44.type_check.temp_plus_y
  :field temp_batt_a: no44.type_check.temp_batt_a
  :field temp_xmit_a: no44.type_check.temp_xmit_a
  :field temp_plus_z: no44.type_check.temp_plus_z
  :field temp_plus_x: no44.type_check.temp_plus_x
  :field temp_stack_a: no44.type_check.temp_stack_a
  :field current_minus_y: no44.type_check.current_minus_y
  :field current_batt_a: no44.type_check.current_batt_a
  :field a_batt_a_volt: no44.type_check.a_batt_a_volt
  :field a_batt_b_volt: no44.type_check.a_batt_b_volt
  :field power_out_a: no44.type_check.power_out_a
  :field eight_v_reg_a: no44.type_check.eight_v_reg_a
  :field current_minus_x: no44.type_check.current_minus_x
  :field current_minus_z: no44.type_check.current_minus_z
  :field current_minus_y: no44.type_check.current_minus_y
  :field current_plus_x: no44.type_check.current_plus_x
  :field temp_minus_y: no44.type_check.temp_minus_y
  :field temp_batt_b: no44.type_check.temp_batt_b
  :field temp_xmit_b: no44.type_check.temp_xmit_b
  :field temp_minus_z: no44.type_check.temp_minus_z
  :field temp_minus_x: no44.type_check.temp_minus_x
  :field temp_stack_b: no44.type_check.temp_stack_b
  :field current_plus_y: no44.type_check.current_plus_y
  :field current_batt_b: no44.type_check.current_batt_b
  :field b_batt_a_volt: no44.type_check.b_batt_a_volt
  :field b_batt_b_volt: no44.type_check.b_batt_b_volt
  :field power_out_b: no44.type_check.power_out_b
  :field eight_v_reg_b: no44.type_check.eight_v_reg_b
  :field monitor: no44.type_check.monitor
  :field dest_callsign: no44.type_check.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: no44.type_check.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: no44.type_check.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: no44.type_check.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: no44.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: no44.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: no44.type_check.ax25_frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field ctl: no44.type_check.ax25_frame.ax25_header.ctl
  :field pid: no44.type_check.ax25_frame.payload.pid
  :field monitor: no44.type_check.ax25_frame.payload.ax25_info.data_monitor

seq:
  - id: no44
    type: no44_t

types:
  no44_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0xAE668288: side_a # = W3AD (O -1)
            0xA086A682: side_b # = PCSA (T -11)
            _: aprs

    instances:
        check:
              type: u4
              pos: 7 # checks from 8th byte on (=beginning of sender's callsign)

  side_a:
         seq:
            - id: header_0
              type: u8
              valid:
                any-of:
                  - 0x848A82869E9C60AE
            - id: header_1
              type: u8
              valid:
                any-of:
                  - 0x6682889E4062A68E
            - id: header_2
              type: u8
              valid:
                any-of:
                  - 0x82A88A406103F054
            - id: header_3
              type: u1
              valid:
                any-of:
                  - 0x23
            - id: counter
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_1
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_2
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_3
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_4
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: five_v_reference
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: ones
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: cycle_count
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: last_number
              type: str
              terminator: 0x0D
              encoding: ASCII

         instances:
               current_plus_x:
                 value:  0.0012 * (value_1.to_i * value_1.to_i) + 0.646 * value_1.to_i - 25.96
                 if: cycle_count.substring(2,4) == "00"

               current_plus_z:
                 value:  0.0048 * (value_2.to_i * value_2.to_i) + 0.75 * value_2.to_i - 54.6
                 if: cycle_count.substring(2,4) == "00"

               current_plus_y:
                 value:  0.0031 * (value_3.to_i * value_3.to_i) + 0.241 * value_3.to_i - 25.3
                 if: cycle_count.substring(2,4) == "00"

               current_minus_x:
                 value:  0.0024 * (value_4.to_i * value_4.to_i) + 0.414 * value_4.to_i - 25.3
                 if: cycle_count.substring(2,4) == "00"

               temp_plus_y:
                 value:  0.3414 * value_1.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_batt_a:
                 value:  0.3414 * value_2.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_xmit_a:
                 value:  0.3414 * value_3.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_plus_z:
                 value:  0.3414 * value_4.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_plus_x:
                 value:  0.3414 * value_1.to_i - 19.71
                 if: cycle_count.substring(2,4) == "10"

               temp_stack_a:
                 value:  0.3414 * value_2.to_i - 19.71
                 if: cycle_count.substring(2,4) == "10"

               current_minus_y:
                 value:  0.0037 * (value_3.to_i * value_3.to_i) + 0.0264 * value_3.to_i - 18.5
                 if: cycle_count.substring(2,4) == "10"

               current_batt_a:
                 value:  -0.00004 * (value_4.to_i * value_4.to_i * value_4.to_i) + 0.0114 * (value_4.to_i * value_4.to_i) - 2.56 * value_4.to_i + 252
                 if: cycle_count.substring(2,4) == "10"

               a_batt_a_volt:
                 value:  0.0984 * value_1.to_i
                 if: cycle_count.substring(2,4) == "11"

               a_batt_b_volt:
                 value:  0.09826 * value_2.to_i
                 if: cycle_count.substring(2,4) == "11"

               power_out_a:
                 value:  0.0311 * value_3.to_i
                 if: cycle_count.substring(2,4) == "11"

               eight_v_reg_a:
                 value:  0.0356 * value_4.to_i
                 if: cycle_count.substring(2,4) == "11"

               monitor:
                 value:  '"T#"+counter+","+value_1+","+value_2+","+value_3+","+value_4+","+five_v_reference+","+ones+","+cycle_count+","+last_number'


  side_b:
         seq:
            - id: header_0
              type: u8
              valid:
                any-of:
                  - 0x848A82869E9C60a0
            - id: header_1
              type: u8
              valid:
                any-of:
                  - 0x86A682A84076A68E
            - id: header_2
              type: u8
              valid:
                any-of:
                  - 0x82A88A406103F054
            - id: header_3
              type: u1
              valid:
                any-of:
                  - 0x23
            - id: counter
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_1
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_2
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_3
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: value_4
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: five_v_reference
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: ones
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: cycle_count
              type: str
              terminator: 0x2C
              encoding: ASCII
            - id: last_number
              type: str
              terminator: 0x0D
              encoding: ASCII

         instances:
               current_minus_x:
                 value:  0.0034 * (value_1.to_i * value_1.to_i) + 0.2284 * value_1.to_i - 26.6
                 if: cycle_count.substring(2,4) == "00"

               current_minus_z:
                 value:  0.0096 * (value_2.to_i * value_2.to_i) + 0.864 * value_2.to_i - 53.8
                 if: cycle_count.substring(2,4) == "00"

               current_minus_y:
                 value:  0.0023 * (value_3.to_i * value_3.to_i) + 0.473 * value_3.to_i - 23.2
                 if: cycle_count.substring(2,4) == "00"

               current_plus_x:
                 value:  0.003 * (value_4.to_i * value_4.to_i) + 0.4 * value_4.to_i - 26.6
                 if: cycle_count.substring(2,4) == "00"

               temp_minus_y:
                 value:  0.3414 * value_1.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_batt_b:
                 value:  0.3414 * value_2.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_xmit_b:
                 value:  0.3414 * value_3.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_minus_z:
                 value:  0.3414 * value_4.to_i - 19.71
                 if: cycle_count.substring(2,4) == "01"

               temp_minus_x:
                 value:  0.3414 * value_1.to_i - 19.71
                 if: cycle_count.substring(2,4) == "10"

               temp_stack_b:
                 value:  0.3414 * value_2.to_i - 19.71
                 if: cycle_count.substring(2,4) == "10"

               current_plus_y:
                 value:  0.0038 * (value_3.to_i * value_3.to_i) + 0.0084 * value_3.to_i - 19.8
                 if: cycle_count.substring(2,4) == "10"

               current_batt_b:
                 value:  -0.00004 * (value_4.to_i * value_4.to_i * value_4.to_i) + 0.0158 * (value_4.to_i * value_4.to_i) - 3.32 * value_4.to_i + 259
                 if: cycle_count.substring(2,4) == "10"

               b_batt_a_volt:
                 value:  0.09774 * value_1.to_i
                 if: cycle_count.substring(2,4) == "11"

               b_batt_b_volt:
                 value:  0.09457 * value_2.to_i
                 if: cycle_count.substring(2,4) == "11"

               power_out_b:
                 value:  0.0223 * value_3.to_i
                 if: cycle_count.substring(2,4) == "11"

               eight_v_reg_b:
                 value:  0.0351 * value_4.to_i
                 if: cycle_count.substring(2,4) == "11"

               monitor:
                 value:  '"T#"+counter+","+value_1+","+value_2+","+value_3+","+value_4+","+five_v_reference+","+ones+","+cycle_count+","+last_number'



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
            value: (ssid_mask & 0x1f) >> 1
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
