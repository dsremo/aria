---
meta:
   id: sr0
   title: SR0 DemoSAT decoder
   endian: le
# 2024-08-19, DL7NDR - 2024-08-22 little fix in line 33
doc: |
  :field callsign_lora: id1.id2.callsign_lora
  :field frame_number: id1.id2.frame_number
  :field message_type: id1.id2.message_type
  :field transmission_power: id1.id2.transmission_power
  :field satellite_unix_time: id1.id2.satellite_unix_time
  :field obc_temperature_celsius: id1.id2.obc_temperature_celsius
  :field battery_temperature_celsius: id1.id2.battery_temperature_celsius
  :field external_temperature_celsius: id1.id2.external_temperature_celsius
  :field base_plate_temperature_celsius: id1.id2.base_plate_temperature_celsius
  :field solar_panel_temperature_celsius: id1.id2.solar_panel_temperature_celsius
  :field radiation_microsv_per_h: id1.id2.radiation_microsv_per_h
  :field bus_voltage_v: id1.id2.bus_voltage_v
  :field bus_current_a: id1.id2.bus_current_a
  :field battery_maximum_capacity_ah: id1.id2.battery_maximum_capacity_ah
  :field battery_remaining_capacity_ah: id1.id2.battery_remaining_capacity_ah
  :field solar_bus_voltage_v: id1.id2.solar_bus_voltage_v
  :field solar_bus_current_a: id1.id2.solar_bus_current_a
  :field boot_counter: id1.id2.boot_counter
  :field checksum: id1.id2.checksum
  :field dest_callsign: id1.id2.ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: id1.id2.ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: id1.id2.ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: id1.id2.ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field ctl: id1.id2.ax25_frame.ax25_header.ctl
  :field pid: id1.id2.ax25_frame.ax25_header.pid
  :field callsign_fsk: id1.id2.ax25_frame.ax25_payload.callsign_fsk
  :field frame_number: id1.id2.ax25_frame.ax25_payload.frame_number
  :field message_type: id1.id2.ax25_frame.ax25_payload.message_type
  :field transmission_power: id1.id2.ax25_frame.ax25_payload.transmission_power
  :field satellite_unix_time: id1.id2.ax25_frame.ax25_payload.satellite_unix_time
  :field obc_temperature_celsius: id1.id2.ax25_frame.ax25_payload.obc_temperature_celsius
  :field battery_temperature_celsius: id1.id2.ax25_frame.ax25_payload.battery_temperature_celsius
  :field external_temperature_celsius: id1.id2.ax25_frame.ax25_payload.external_temperature_celsius
  :field base_plate_temperature_celsius: id1.id2.ax25_frame.ax25_payload.base_plate_temperature_celsius
  :field solar_panel_temperature_celsius: id1.id2.ax25_frame.ax25_payload.solar_panel_temperature_celsius
  :field radiation_microsv_per_h: id1.id2.ax25_frame.ax25_payload.radiation_microsv_per_h
  :field bus_voltage_v: id1.id2.ax25_frame.ax25_payload.bus_voltage_v
  :field bus_current_a: id1.id2.ax25_frame.ax25_payload.bus_current_a
  :field battery_maximum_capacity_ah: id1.id2.ax25_frame.ax25_payload.battery_maximum_capacity_ah
  :field battery_remaining_capacity_ah: id1.id2.ax25_frame.ax25_payload.battery_remaining_capacity_ah
  :field solar_bus_voltage_v: id1.id2.ax25_frame.ax25_payload.solar_bus_voltage_v
  :field solar_bus_current_a: id1.id2.ax25_frame.ax25_payload.solar_bus_current_a
  :field boot_counter: id1.id2.ax25_frame.ax25_payload.boot_counter
  :field checksum: id1.id2.ax25_frame.ax25_payload.checksum

seq:
  - id: id1
    type: type1

types:
  type1:
    seq:
      - id: id2
        type:
          switch-on: lora_or_fsk
          cases:
            0x53523053: lora # sr0s(at)
            0xA6A0A496: fsk

    instances:
      lora_or_fsk:
        type: u4be
        pos: 0

  lora:
   seq:
     - id: callsign_lora
       type: str
       size: 6
       encoding: ASCII
       valid:
        any-of:
          - '"SR0SAT"'

     - id: frame_number
       type: u2

     - id: message_type
       type: u1

     - id: transmission_power
       type: u1

     - id: satellite_unix_time
       type: u4

     - id: obc_temperature
       type: s2

     - id: battery_temperature
       type: s2

     - id: external_temperature
       type: s2

     - id: base_plate_temperature
       type: s2

     - id: solar_panel_temperature
       type: s2

     - id: radiation
       type: s2

     - id: bus_voltage
       type: u2

     - id: bus_current
       type: s2

     - id: battery_maximum_capacity
       type: u2

     - id: battery_remaining_capacity
       type: u2

     - id: solar_bus_voltage
       type: u2

     - id: solar_bus_current
       type: u2

     - id: boot_counter
       type: u2

     - id: checksum
       type: u1 

   instances:
      obc_temperature_celsius:
        value: obc_temperature / 10.0

      battery_temperature_celsius:
        value: battery_temperature / 10.0

      external_temperature_celsius:
        value: external_temperature / 10.0

      base_plate_temperature_celsius:
        value: base_plate_temperature / 10.0

      solar_panel_temperature_celsius:
        value: solar_panel_temperature / 10.0

      radiation_microsv_per_h:
        value: radiation / 100.0

      bus_voltage_v:
        value: bus_voltage / 1000.0

      bus_current_a:
        value: bus_current / 1000.0

      battery_maximum_capacity_ah:
        value: battery_maximum_capacity / 1000.0

      battery_remaining_capacity_ah:
        value: battery_remaining_capacity / 1000.0

      solar_bus_voltage_v:
        value: solar_bus_voltage / 1000.0

      solar_bus_current_a:
        value: solar_bus_current / 1000.0


  fsk:
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
             value: (ssid_mask & 0x0f) >> 1

      ax25_payload:
        seq:
          - id: callsign_fsk
            type: str
            size: 6
            encoding: ASCII
            valid:
             any-of:
               - '"SR0SAT"'

          - id: frame_number
            type: u2

          - id: message_type
            type: u1

          - id: transmission_power
            type: u1

          - id: satellite_unix_time
            type: u4

          - id: obc_temperature
            type: s2

          - id: battery_temperature
            type: s2

          - id: external_temperature
            type: s2

          - id: base_plate_temperature
            type: s2

          - id: solar_panel_temperature
            type: s2

          - id: radiation
            type: s2

          - id: bus_voltage
            type: u2

          - id: bus_current
            type: s2

          - id: battery_maximum_capacity
            type: u2

          - id: battery_remaining_capacity
            type: u2

          - id: solar_bus_voltage
            type: u2

          - id: solar_bus_current
            type: u2

          - id: boot_counter
            type: u2

          - id: checksum
            type: u1 

        instances:
              obc_temperature_celsius:
                value: obc_temperature / 10.0

              battery_temperature_celsius:
               value: battery_temperature / 10.0

              external_temperature_celsius:
                value: external_temperature / 10.0

              base_plate_temperature_celsius:
                value: base_plate_temperature / 10.0

              solar_panel_temperature_celsius:
                value: solar_panel_temperature / 10.0

              radiation_microsv_per_h:
                value: radiation / 100.0

              bus_voltage_v:
                value: bus_voltage / 1000.0

              bus_current_a:
                value: bus_current / 1000.0

              battery_maximum_capacity_ah:
                value: battery_maximum_capacity / 1000.0

              battery_remaining_capacity_ah:
                value: battery_remaining_capacity / 1000.0

              solar_bus_voltage_v:
                value: solar_bus_voltage / 1000.0

              solar_bus_current_a:
                value: solar_bus_current / 1000.0
