---
meta:
  id: silversat
  title: SilverSat CW + SSDV decoder
  endian: be
doc-ref: "https://github.com/silver-sat/systems/wiki/Beacon-Operations"
# "https://ukhas.org.uk/doku.php?id=guides:ssdv"
# 2026-01-17, DL7NDR
doc: |
  :field cw_callsign: silversat.cw_or_ssdv.cw_callsign
  :field power: silversat.cw_or_ssdv.power
  :field avionics: silversat.cw_or_ssdv.avionics
  :field payload: silversat.cw_or_ssdv.payload
  :field radio: silversat.cw_or_ssdv.radio
  :field cw_beacon: silversat.cw_or_ssdv.cw_beacon
  :field dest_callsign: silversat.cw_or_ssdv.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: silversat.cw_or_ssdv.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: silversat.cw_or_ssdv.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: silversat.cw_or_ssdv.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field ctl: silversat.cw_or_ssdv.ax25_frame.ax25_header.ctl
  :field pid: silversat.cw_or_ssdv.ax25_frame.ax25_header.pid
  :field ssdv_sync_byte: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_sync_byte
  :field ssdv_packet_type: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_packet_type
  :field ssdv_callsign: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_callsign
  :field ssdv_image_id: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_image_id
  :field ssdv_packet_id: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_packet_id
  :field ssdv_width: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_width
  :field ssdv_height: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_height
  :field ssdv_flags: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_flags
  :field ssdv_mcu_offset: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_mcu_offset
  :field ssdv_mcu_index: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_mcu_index
  :field ssdv_image: silversat.cw_or_ssdv.ax25_frame.ax25_info.ssdv_image

seq:
  - id: silversat
    type: silversat_t

types:
  silversat_t:
    seq:
      - id: cw_or_ssdv
        type:
          switch-on: cw_or_ssdv_switch_on
          cases:
            0x77703278: cw #  wp2x
            _: ssdv # everything else

    instances:
        cw_or_ssdv_switch_on:
              type: u4
              pos: 0

  cw:
    seq:
      - id: cw_callsign
        type: str
        size: 7
        encoding: ASCII
        valid: '"wp2xgw "' # 77 70 32 78 67 77 20

      - id: power
        type: str
        size: 1
        encoding: ASCII
        valid:
           any-of: ['"s"', '"e"', '"i"', '"t"', '"a"']

      - id: avionics
        type: str
        size: 1
        encoding: ASCII
        valid:
           any-of: ['"e"', '"s"', '"a"', '"h"', '"n"', '"u"', '"i"', '"d"', '"r"', '"t"', '"5"']

      - id: payload
        type: str
        size: 1
        encoding: ASCII
        valid:
           any-of: ['"e"', '"i"', '"v"', '"w"', '"l"', '"5"', '"a"', '"h"', '"m"', '"4"', '"6"', '"c"', '"b"', '"s"', '"t"', '"n"', '"r"', '"u"', '"d"', '"f"', '"g"', '"k"', '"o"', '"7"', '"x"', '"z"', '"p"', '"3"', '"j"', '"q"', '"9"', '"0"']

      - id: radio
        type: str
        size: 1
        encoding: ASCII
        valid:
           any-of: ['"e"', '"i"', '"s"', '"t"', '"n"', '"a"', '"h"', '"d"', '"r"', '"u"', '"5"', '"b"', '"v"', '"f"', '"l"', '"m"', '"4"', '"g"']

      - id: lengthcheck # the beacon should end by value4. if there is more to parse, the whole frame will be discarded due to 'necessary_for_lengthcheck'
        type: str
        encoding: utf-8 # if un-encodeable, whole frame will be discarded
        size-eos: true

    instances:
      necessary_for_lengthcheck:
        if: lengthcheck.length != 0 # if so, whole frame will be discarded
        value: lengthcheck.to_i / 0 # produces 'ZeroDivisionError' and stops parsing

      cw_beacon:
        value: power + avionics + payload + radio



  ssdv:
    seq:
      - id: ax25_frame
        type: ax25_frame

    types:
      ax25_frame:
        seq:
          - id: ax25_header
            type: ax25_header
          - id: ax25_info
            type: ssdv_payload
#            size-eos: true

      ssdv_payload:
        seq:
          - id: ssdv_sync_byte
            type: u1
            valid: 0x55

          - id: ssdv_packet_type
            type: u1
            valid:
              any-of: [0x66, 0x67]

          - id: ssdv_callsign
            type: u4
            valid: "3739973996" # de eb 79 6c

          - id: ssdv_image_id
            type: u1

          - id: ssdv_packet_id
            type: u2

          - id: ssdv_width
            type: u1

          - id: ssdv_height
            type: u1

          - id: ssdv_flags
            type: u1

          - id: ssdv_mcu_offset
            type: u1

          - id: ssdv_mcu_index
            type: u2

          - id: ssdv_image
            type: u1
            repeat: eos

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
          hbit:
            value: (ssid_mask & 0x80) >> 7
