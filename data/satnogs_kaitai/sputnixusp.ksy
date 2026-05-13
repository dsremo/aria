---
meta:
  id: sputnixusp
  title: Sputnix Unified Protocol decoder
  endian: le

doc: |
  :field callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field ssid_mask: ax25_frame.ax25_header.dest_ssid_raw.ssid_mask
  :field ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field src_callsign_raw_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid_raw_ssid_mask: ax25_frame.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field ctl: ax25_frame.ax25_header.ctl
  :field pid: ax25_frame.ax25_header.pid
  :field payload___packet_type: ax25_frame.payload.___.packet_type
  :field t_amp: ax25_frame.payload.0.tlm.t_amp
  :field t_uhf: ax25_frame.payload.0.tlm.t_uhf
  :field rssi_rx: ax25_frame.payload.0.tlm.rssi_rx
  :field pf: ax25_frame.payload.0.tlm.pf
  :field pb: ax25_frame.payload.0.tlm.pb
  :field nres_uhf: ax25_frame.payload.0.tlm.nres_uhf
  :field fl_uhf: ax25_frame.payload.0.tlm.fl_uhf
  :field time_uhf: ax25_frame.payload.0.tlm.time_uhf
  :field uptime_uhf: ax25_frame.payload.0.tlm.uptime_uhf
  :field current_uhf: ax25_frame.payload.0.tlm.current_uhf
  :field uuhf: ax25_frame.payload.0.tlm.uuhf
  :field rssi_idle: ax25_frame.payload.0.tlm.rssi_idle
  :field rxbitrate: ax25_frame.payload.0.tlm.rxbitrate
  :field num_active_schedules: ax25_frame.payload.0.tlm.num_active_schedules
  :field reset_during_sch: ax25_frame.payload.0.tlm.reset_during_sch
  :field backup_sch_active: ax25_frame.payload.0.tlm.backup_sch_active
  :field usb1: ax25_frame.payload.1.tlm.usb1
  :field usb2: ax25_frame.payload.1.tlm.usb2
  :field usb3: ax25_frame.payload.1.tlm.usb3
  :field isb1: ax25_frame.payload.1.tlm.isb1
  :field isb2: ax25_frame.payload.1.tlm.isb2
  :field isb3: ax25_frame.payload.1.tlm.isb3
  :field iab: ax25_frame.payload.1.tlm.iab
  :field ich1: ax25_frame.payload.1.tlm.ich1
  :field ich2: ax25_frame.payload.1.tlm.ich2
  :field ich3: ax25_frame.payload.1.tlm.ich3
  :field ich4: ax25_frame.payload.1.tlm.ich4
  :field ich5: ax25_frame.payload.1.tlm.ich5
  :field t1_pw: ax25_frame.payload.1.tlm.t1_pw
  :field t2_pw: ax25_frame.payload.1.tlm.t2_pw
  :field t3_pw: ax25_frame.payload.1.tlm.t3_pw
  :field t4_pw: ax25_frame.payload.1.tlm.t4_pw
  :field flags1: ax25_frame.payload.1.tlm.flags1
  :field flags2: ax25_frame.payload.1.tlm.flags2
  :field flags3: ax25_frame.payload.1.tlm.flags3
  :field reserved1: ax25_frame.payload.1.tlm.reserved1
  :field uab: ax25_frame.payload.1.tlm.uab
  :field reg_tel_id: ax25_frame.payload.1.tlm.reg_tel_id
  :field time: ax25_frame.payload.1.tlm.time
  :field nres_ps: ax25_frame.payload.1.tlm.nres_ps
  :field fl_ps: ax25_frame.payload.1.tlm.fl_ps
  :field uab1: ax25_frame.payload.1.tlm.uab1
  :field uab2: ax25_frame.payload.1.tlm.uab2
  :field capacity: ax25_frame.payload.1.tlm.capacity

seq:
  - id: ax25_frame
    type: ax25_frame
    doc-ref: 'https://www.tapr.org/pdf/AX25.2.2.pdf'
types:
  ax25_frame:
    seq:
      - id: ax25_header
        type: ax25_header
      - id: payload
        type: beacon_tlm
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
        value: (ssid_mask & 0x0f) >> 1

  beacon_tlm:
    seq:
      - id: packet_type
        type: u2
      - id: skip1
        type: u2
      - id: skip2
        type: u2
      - id: len
        type: u2
      - id: tlm
        size: len
        type:
          switch-on: packet_type
          cases:
            0x4216: general_tlm
            0x4246: uhf_beacon
            0xDE21: ps_regular_telemetry
            0xED21: ps_regular_telemetry_5ch
            0xDF25: regular_telemetry_6u

  general_tlm:
    seq:
      - id: ps
        type: ps_regular_telemetry
      - id: t_amp
        type: u1
        doc: |
          UHF amplifier temperature (degree C)
      - id: t_uhf
        type: u1
        doc: |
          UHF temperature (degree C)
      - id: rssi_rx
        type: s2be
        doc: |
          RX rssi
      - id: pf
        type: u1
        doc: |
          Direct radiation power
      - id: pb
        type: u1
        doc: |
          Back radiation power
      - id: nres_uhf
        type: u1
        doc: |
          Number of UHF reboots
      - id: fl_uhf
        type: u1
        doc: |
          UHF flags
      - id: time_uhf
        type: u4
        doc: |
          Time of last UHF telemetry
      - id: uptime_uhf
        type: u4
        doc: |
          UHF Uptime in seconds
      - id: current_uhf
        type: u2
        doc: |
          UHF current consumption
      - id: uuhf
        type: u2
        doc: |
          UHF voltage (mV)

  uhf_beacon:
    seq:
      - id: t_amp
        type: s1
        doc: |
          UHF amplifier temperature (degree C)
      - id: t_uhf
        type: s1
        doc: |
          UHF temperature (deg. C)
      - id: rss_rx
        type: u1
        doc: |
          Received singal strength indicator (negative)
      - id: rssi_idle
        type: u1
        doc: |
          Noise idle RSSI level (negative)
      - id: pf
        type: s1
        doc: |
          Forward wave power (dBm)
      - id: pb
        type: s1
        doc: |
          Reflected wave powe (dBm)
      - id: nres_uhf
        type: u1
        doc: |
          UHF reset counter
      - id: fl_uhf
        type: u1
        doc: |
          UHF service flags
      - id: time_uhf
        type: u4
        doc: |
          UHF timestamp
      - id: uptime_uhf
        type: u4
        doc: |
          Uptime (seconds)
      - id: rxbitrate
        type: u4
        doc: |
          Uplink bitrate
      - id: current_uhf
        type: u2
        doc: |
          UHF consumption current
      - id: uuhf
        type: u2
        doc: |
          UHF voltage (mV)
      - id: sch_reserved
        type: b1
        doc: |
          reserved
      - id: backup_sch_active
        type: b1
        doc: |
          Backup schedule execution in progress
      - id: reset_during_sch
        type: b1
        doc: |
          Reboot occured during schedule execution
      - id: num_active_schedules
        type: b5
        doc: |
          Number of Active Schedules in executor

  ps_regular_telemetry_5ch:
    seq:
      - id: usb1
        type: u2
        doc: |
          Voltage SB 1 (mV)
      - id: usb2
        type: u2
        doc: |
          Voltage SB 2 (mV)
      - id: usb3
        type: u2
        doc: |
          Voltage SB 3 (mV)
      - id: isb1
        type: u2
        doc: |
          SB1 current (mA)
      - id: isb2
        type: u2
        doc: |
          SB2 current (mA)
      - id: isb3
        type: u2
        doc: |
          SB3 current (mA)
      - id: iab
        type: s2
        doc: |
          Battery current (mA)
      - id: ich1
        type: u2
        doc: |
          Channel 1 current (mA)
      - id: ich2
        type: u2
        doc: |
          Channel 2 current (mA)
      - id: ich3
        type: u2
        doc: |
          Channel 3 current (mA)
      - id: ich4
        type: u2
        doc: |
          Channel 4 current (mA)
      - id: ich5
        type: u2
        doc: |
          Channel 5 current (mA)
      - id: t1_pw
        type: s2
        doc: |
          Battery temperature 1 (degree C)
      - id: t2_pw
        type: s2
        doc: |
          Battery temperature 2 (degree C)
      - id: t3_pw
        type: s2
        doc: |
          Battery temperature 3 (degree C)
      - id: t4_pw
        type: s2
        doc: |
          Battery temperature 4 (degree C)
      - id: flags1
        type: u1
        doc: |
          uab_crit:
            Flag "The battery is discharged to a critical level"
          uab_min:
            Flag "The battery is discharged to a minimal level"
          heater2_manual:
            Heater manual control flag 2
          heater1_manual:
            Heater manual control flag 1
          heater2_on:
            Heater enable flag 2
          heater1_on:
            Heater enable flag 1
          tab_max:
            Maximum temperature exceeded flag
          tab_min:
            "Low battery temperature" flag
      - id: flags2
        type: u1
        doc: |
          channelon5:
            Channel 5 status flag
          channelon4:
            Channel 4 status flag
          channelon3:
            Channel 3 status flag
          channelon2:
            Channel 2 status flag
          channelon1:
            Channel 1 status flag
          ich_limit5:
            Excess current flag for channel 5
          ich_limit4:
            Excess current flag for channel 4
          ich_limit3:
            Excess current flag for channel 3
      - id: flags3
        type: u1
        doc: |
          0-4 bit - reserved:
          ich_limit2:
            Excess current flag for channel 2
          ich_limit1:
            Excess current flag for channel 1
          7 bit - charger:
            Flag of presence of voltage at the charging connector
      - id: reserved1
        type: u1
        doc: |
      - id: uab
        type: u2
        doc: |
          Battery voltage (mV)
      - id: reg_tel_id
        type: u4
        doc: |
          PS telemetry number
      - id: time
        type: u4
        doc: |
          time of last PS telemetry
      - id: nres_ps
        type: u1
        doc: |
          Number of PS reboots
      - id: fl_ps
        type: u1
        doc: |
          ps flags

  regular_telemetry_6u:
    seq:
      - id: usb1
        type: u2
        doc: |
          Voltage SB 1 (mV)
      - id: usb2
        type: u2
        doc: |
          Voltage SB 2 (mV)
      - id: usb3
        type: u2
        doc: |
          Voltage SB 3 (mV)
      - id: isb1
        type: u2
        doc: |
          SB1 current (mA)
      - id: isb2
        type: u2
        doc: |
          SB2 current (mA)
      - id: isb3
        type: u2
        doc: |
          SB3 current (mA)
      - id: iab
        type: s2
        doc: |
          Battery current (mA)
      - id: uab
        type: u2
        doc: |
          Voltage on cell 1 (mA)
      - id: uab1
        type: u2
        doc: |
          Voltage on cell 1 (mA)
      - id: uab2
        type: u2
        doc: |
          Voltage on cell 2 (mA)
      - id: t1_pw
        type: s2
        doc: |
          Battery temperature 1 (degree C)
      - id: t2_pw
        type: s2
        doc: |
          Battery temperature 2 (degree C)
      - id: capacity
        type: u1
        doc: |
          Capacity
      - id: channel_status_ch1
        type: b1
        doc: |
          Channel on/off status
      - id: channel_status_ch2
        type: b1
        doc: |
          Channel on/off status
      - id: channel_status_ch3
        type: b1
        doc: |
          Channel on/off status
      - id: channel_status_ch4
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch5
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch6
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch7
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch8
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch9
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch10
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch11
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch12
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch13
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch14
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch15
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch16
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch17
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch18
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch19
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch20
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch21
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch22
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch23
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch24
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch25
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch26
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch27
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch28
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch29
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_ch30
        type: b1
        doc: |
          Channel on/off
      - id: channel_status_reserved
        type: b2
        doc: |
          reserved
      - id: flags1
        type: u1
        doc: |
          uab_crit:
            Flag "The battery is discharged to a critical level"
          uab_min:
            Flag "The battery is discharged to a minimal level"
          heater2_manual:
            Heater manual control flag 2
          heater1_manual:
            Heater manual control flag 1
          heater2_on:
            Heater enable flag 2
          heater1_on:
            Heater enable flag 1
          tab_max:
            Maximum temperature exceeded flag
          tab_min:
            "Low battery temperature" flag
      - id: flags2
        type: u1
        doc: |
          channelon4:
            Channel 4 status flag
          channelon3:
            Channel 3 status flag
          channelon2:
            Channel 2 status flag
          channelon1:
            Channel 1 status flag
          ich_limit4:
            Excess current flag for channel 4
          ich_limit3:
            Excess current flag for channel 3
          ich_limit2:
            Excess current flag for channel 2
          ich_limit1:
            Excess current flag for channel 1
      - id: flags3
        type: u1
        doc: |
          0-6 bit - reserved:
          7 bit - charger:
            Flag of presence of voltage at the charging connector
      - id: reserved1
        type: u1
        doc: |
      - id: reg_tel_id
        type: u4
        doc: |
          PS telemetry number
      - id: time
        type: u4
        doc: |
          time of last PS telemetry
      - id: nres_ps
        type: u1
        doc: |
          Number of PS reboots
      - id: fl_ps
        type: u1
        doc: |
          ps flags

  ps_regular_telemetry:
    seq:
      - id: usb1
        type: u2
        doc: |
          Voltage SB 1 (mV)
      - id: usb2
        type: u2
        doc: |
          Voltage SB 2 (mV)
      - id: usb3
        type: u2
        doc: |
          Voltage SB 3 (mV)
      - id: isb1
        type: u2
        doc: |
          SB1 current (mA)
      - id: isb2
        type: u2
        doc: |
          SB2 current (mA)
      - id: isb3
        type: u2
        doc: |
          SB3 current (mA)
      - id: iab
        type: s2
        doc: |
          Battery current (mA)
      - id: ich1
        type: u2
        doc: |
          Channel 1 current (mA)
      - id: ich2
        type: u2
        doc: |
          Channel 2 current (mA)
      - id: ich3
        type: u2
        doc: |
          Channel 3 current (mA)
      - id: ich4
        type: u2
        doc: |
          Channel 4 current (mA)
      - id: t1_pw
        type: s2
        doc: |
          Battery temperature 1 (degree C)
      - id: t2_pw
        type: s2
        doc: |
          Battery temperature 2 (degree C)
      - id: t3_pw
        type: s2
        doc: |
          Battery temperature 3 (degree C)
      - id: t4_pw
        type: s2
        doc: |
          Battery temperature 4 (degree C)
      - id: flags1
        type: u1
        doc: |
          uab_crit:
            Flag "The battery is discharged to a critical level"
          uab_min:
            Flag "The battery is discharged to a minimal level"
          heater2_manual:
            Heater manual control flag 2
          heater1_manual:
            Heater manual control flag 1
          heater2_on:
            Heater enable flag 2
          heater1_on:
            Heater enable flag 1
          tab_max:
            Maximum temperature exceeded flag
          tab_min:
            "Low battery temperature" flag
      - id: flags2
        type: u1
        doc: |
          channelon4:
            Channel 4 status flag
          channelon3:
            Channel 3 status flag
          channelon2:
            Channel 2 status flag
          channelon1:
            Channel 1 status flag
          ich_limit4:
            Excess current flag for channel 4
          ich_limit3:
            Excess current flag for channel 3
          ich_limit2:
            Excess current flag for channel 2
          ich_limit1:
            Excess current flag for channel 1
      - id: flags3
        type: u1
        doc: |
          0-6 bit - reserved:
          7 bit - charger:
            Flag of presence of voltage at the charging connector
      - id: reserved1
        type: u1
        doc: |
      - id: uab
        type: u2
        doc: |
          Battery voltage (mV)
      - id: reg_tel_id
        type: u4
        doc: |
          PS telemetry number
      - id: time
        type: u4
        doc: |
          time of last PS telemetry
      - id: nres_ps
        type: u1
        doc: |
          Number of PS reboots
      - id: fl_ps
        type: u1
        doc: |
          ps flags
