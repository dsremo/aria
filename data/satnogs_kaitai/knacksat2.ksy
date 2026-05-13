################################################################################
# File: knacksat2.ksy
# Create: Anol P. <anol.p@emone.space>
# Author: Anol P. <anol.p@emone.space>
# Created Date: 2026-02-08 09:00AM ICT
# Modified Date: 2026-04-15 12:20PM ICT
# version: v0.1.2-rc3
#
# License: MIT
#
# Copyright (c) 2026 EmOne
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#  
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#  
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
################################################################################

meta:
  id: knacksat2 #callsign HS0K
  file-extension: knacksat2
  endian: be
doc: |
  :field dest_callsign: id1.id2.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: id1.id2.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: id1.id2.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field ctl: id1.id2.ax25_frame.ax25_header.ctl
  :field pid: id1.id2.ax25_frame.payload.pid
  :field pcdu_en: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.pcdu.enable
  :field mppt_r1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.res.res_1
  :field mppt_r2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.res.res_2
  :field mppt_r3: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.res.res_3
  :field mppt_power_0: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.power_0
  :field mppt_power_1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.power_1
  :field mppt_power_2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.power_2
  :field mppt_power_3: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.power_3
  :field mppt_power_4: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.power_4
  :field mppt_power_5: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.power_5
  :field mppt_power_6: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.power_6
  :field mppt_vbus_0: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.vbus_0
  :field mppt_vbus_1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.vbus_1
  :field mppt_vbus_2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.vbus_2
  :field mppt_vbus_3: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.vbus_3
  :field mppt_vbus_4: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.vbus_4
  :field mppt_vbus_5: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.vbus_5
  :field mppt_vbus_6: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.vbus_6
  :field mppt_isens_0: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.isens_0
  :field mppt_isens_1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.isens_1
  :field mppt_isens_2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.isens_2
  :field mppt_isens_3: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.isens_3
  :field mppt_isens_4: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.isens_4
  :field mppt_isens_5: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.isens_5
  :field mppt_isens_6: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.solar.mppt.isens_6  
  :field batt_r1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.res.res_1
  :field batt_r2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.res.res_2
  :field batt_r3: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.res.res_3
  :field batt_heater_cnt: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.heater_cnt
  :field batt_vout: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.vout
  :field batt_iout: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.iout
  :field batt_vin: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.vin
  :field batt_iin: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.iin
  :field batt_temp_0: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.temperature_0
  :field batt_temp_1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.temperature_1
  :field batt_temp_2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.temperature_2
  :field batt_temp_3: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.battery.temperature_3
  :field ant_status_1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.antenna.isis_ant
  :field ant_status_2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.antenna.lora_ant
  :field obc_r1: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.obc.res.res_1
  :field obc_r2: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.obc.res.res_2
  :field obc_r3: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.obc.res.res_3
  :field ident: id1.id2.ax25_frame.ax25_payload.csp_data.tm_data.identify
  :field digi_dest_callsign: id1.id2.ax25frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field digi_src_callsign: id1.id2.ax25frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field digi_src_ssid: id1.id2.ax25frame.ax25_header.src_ssid_raw.ssid
  :field digi_dest_ssid: id1.id2.ax25frame.ax25_header.dest_ssid_raw.ssid
  :field rpt_instance___callsign: id1.id2.ax25frame.ax25_header.repeater.rpt_instance.___.rpt_callsign_raw.callsign_ror.callsign
  :field rpt_instance___ssid: id1.id2.ax25frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.ssid
  :field rpt_instance___hbit: id1.id2.ax25frame.ax25_header.repeater.rpt_instance.___.rpt_ssid_raw.hbit
  :field digi_ctl: id1.id2.ax25frame.ax25_header.ctl
  :field digi_pid: id1.id2.ax25frame.ax25_header.pid
  :field digi_message: id1.id2.ax25frame.digi_message

seq:
  - id: id1
    type: type1

types:
  type1:
# checking for telemetry
    seq:
      - id: id2
        type:
          switch-on: message_type1
          cases:
            0x90A66082: telemetry # 4 bytes of destination callsign (HS0A)
            _: digi
   
    instances:
      message_type1:
        type: u4
        pos: 0

  telemetry:
    seq:
     - id: ax25_frame
       type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: ax25_payload
            type: ax25_payload

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

      ax25_payload:
        seq:
          - id: csp_data
            type: csp_data_t

      csp_data_t:
        seq:
          - id: tm_data
            type:
              switch-on: tm_sign
              cases:
                'tm_type::beacon': tm_data_t
                'tm_type::filename': filename_t
                _: unknown_t

        instances:
          tm_sign:
            pos: 0x10
            type: u2
            enum: tm_type

        enums:
            tm_type:
              0x0000: beacon
              0x4054: unknown1
              0x405a: filename #Filename had been requested
              0x8054: unknown2 #ACK?
              0xffff: other #unpredictable
            
      filename_t:
        seq:
          - id: header
            type: u1
            repeat: expr
            repeat-expr: 8
          - id: filename
            type: str
            encoding: ASCII
            terminator: 0
          - id: unknown
            type: unknown_t

      unknown_t:
        seq:
          - id: data
            type: str
            encoding: ASCII
            size-eos: true

      tm_data_t:
        seq:
          - id: pcdu
            type: pcdu_t
          - id: comm
            type: comm_t
          - id: solar
            type: solar_t
          - id: battery
            type: battery_t
          - id: antenna
            type: antenna_t
          - id: obc
            type: obc_t
          - id: identify
            type: str
            encoding: ascii
            size: 3

      res_t:
        seq:
          - id: csp_flags
            type: u1
            repeat: expr
            repeat-expr: 5

        instances:
          res_1:
            value: >-
              (
              (csp_flags[0])
              )
          res_2:
            value: >-
              (
              (csp_flags[1] << 8) | (csp_flags[2])
              )
          res_3:
            value: >-
             (
             (csp_flags[3] << 8) | (csp_flags[4])
             )
          crc:
            value: >-
              (
              (csp_flags[0])
              ) & 0x1
          rdp:
            value: >-
              (
              (
              (csp_flags[0])
              ) >> 1
              ) & 0x1
          xtea:
            value: >-
              (
              (
              (csp_flags[0])
              ) >> 2
              ) & 0x1
          hmac:
            value: >-
              (
              (
              (csp_flags[0])
              ) >> 3
              ) & 0x1
          reserved:
            value: >-
              (
              (csp_flags[0])
              ) >> 4
          src_port:
            value: >-
              (
              (csp_flags[1])
              ) & 0x3F
          dst_port:
            value: >-
              (
              (
              (csp_flags[1]) |
              (csp_flags[2] << 8)
              ) >> 6
              ) & 0x3F
          destination:
            value: >-
              (
              (
              (csp_flags[2]) |
              (csp_flags[3] << 8)
              ) >> 4
              ) & 0x1F
          source:
            value: >-
              (
              (
              (csp_flags[3])
              ) >> 1
              ) & 0x1F
          priority:
            value: >-
              (
              (csp_flags[3])
              ) >> 6
      
      pcdu_t:
        seq:
          - id: res
            type: res_t
          - id: enable
            type: u1

      comm_t:
        seq:
          - id: res
            type: res_t

      solar_t:
        seq:
        - id: mppt
          type: mppt_t

      mppt_t:
        seq:
          - id: res
            type: res_t
          - id: isens
            type: f4le
            repeat: expr
            repeat-expr: 7
          - id: power
            type: f4le
            repeat: expr
            repeat-expr: 7
          - id: vbus
            type: f4le
            repeat: expr
            repeat-expr: 7
        instances:
          isens_0:
            value: isens[0]
          isens_1:
            value: isens[1]
          isens_2:
            value: isens[2]
          isens_3:
            value: isens[3]
          isens_4:
            value: isens[4]
          isens_5:
            value: isens[5]
          isens_6:
            value: isens[6]
          
          power_0:
            value: power[0]
          power_1:
            value: power[1]
          power_2:
            value: power[2]
          power_3:
            value: power[3]
          power_4:
            value: power[4]
          power_5:
            value: power[5]
          power_6:
            value: power[6]
            
          vbus_0:
            value: vbus[0]
          vbus_1:
            value: vbus[1]
          vbus_2:
            value: vbus[2]
          vbus_3:
            value: vbus[3]
          vbus_4:
            value: vbus[4]
          vbus_5:
            value: vbus[5]
          vbus_6:
            value: vbus[6]

      battery_t:
        seq:
          - id: res
            type: res_t
          - id: heater_cnt
            type: u2le
          - id: temperature
            type: f4le
            repeat: expr
            repeat-expr: 4
          - id: vout
            type: f4le
          - id: iout
            type: f4le
          - id: vin
            type: f4le
          - id: iin
            type: f4le
        instances:
          temperature_0:
            value: temperature[0]
          temperature_1:
            value: temperature[1]
          temperature_2:
            value: temperature[2]
          temperature_3:
            value: temperature[3]

      antenna_t:
        seq:
          - id: antenna_status
            type: u1
            repeat: expr
            repeat-expr: 2

        instances:
          isis_ant:
            value: antenna_status[0]
          lora_ant:
            value: antenna_status[1]

      obc_t:
        seq:
          - id: res
            type: res_t

  digi:
    seq:
      - id: ax25frame
        type: ax25frame

    types:
      ax25frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: digi_message
            type: str
            encoding: utf-8
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
          - id: repeater
            type: repeater
            if: (src_ssid_raw.ssid_mask & 0x01) == 0
            doc: 'Repeater flag is set!'
          - id: ctl
            type: u1
          - id: pid
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
