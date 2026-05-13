meta: 
  id: rhoksat
  title: RHOKSAT Beacon Telemetry 

doc: |
  :field dest_callsign_raw_callsign: ax25_frame.ax25_header.dest_callsign_raw.dest_callsign_ror.dest_callsign
  :field dest_ssid_raw_mask: ax25_frame.ax25_header.dest_ssid_raw.ssid_mask
  :field dest_ssid_raw_ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field dest_ssid_raw_value: ax25_frame.ax25_header.dest_ssid_raw.value
  :field src_callsign_raw_callsign: ax25_frame.ax25_header.src_callsign_raw.src_callsign_ror.src_callsign
  :field src_ssid_raw_ssid_mask: ax25_frame.ax25_header.src_ssid_raw.ssid_mask
  :field src_ssid_raw_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field src_ssid_raw_value: ax25_frame.ax25_header.src_ssid_raw.value
  :field ctl: ax25_frame.ax25_header.ctl
  :field pid: ax25_frame.payload.pid
  :field beacon_id: ax25_frame.payload.beacon.beacon_id
  :field num_reboots: ax25_frame.payload.beacon.num_reboots
  :field bat_voltage: ax25_frame.payload.beacon.bat_voltage
  :field rate_x: ax25_frame.payload.beacon.imtq.rate_x
  :field rate_y: ax25_frame.payload.beacon.imtq.rate_y
  :field rate_z: ax25_frame.payload.beacon.imtq.rate_z
  :field total: ax25_frame.payload.beacon.imtq.total
  :field num_of_sweeps: ax25_frame.payload.beacon.num_of_sweeps
  :field num_of_logs: ax25_frame.payload.beacon.num_of_logs
  :field time: ax25_frame.payload.beacon.time
  :field sdcard_id: ax25_frame.payload.beacon.sdcard_id
  :field gyro_x_raw: ax25_frame.payload.beacon.gyro.gyro_x_raw
  :field gyro_y_raw: ax25_frame.payload.beacon.gyro.gyro_y_raw
  :field gyro_z_raw: ax25_frame.payload.beacon.gyro.gyro_z_raw
  :field acc_x_raw: ax25_frame.payload.beacon.accelerometer.acc_x_raw
  :field acc_y_raw: ax25_frame.payload.beacon.accelerometer.acc_y_raw
  :field acc_z_raw: ax25_frame.payload.beacon.accelerometer.acc_z_raw
  :field tl: ax25_frame.payload.beacon.sun_sensor.tl
  :field bl: ax25_frame.payload.beacon.sun_sensor.bl
  :field br: ax25_frame.payload.beacon.sun_sensor.br
  :field tr: ax25_frame.payload.beacon.sun_sensor.tr
  :field pd_z_minus: ax25_frame.payload.beacon.panels.pd_z_minus
  :field pd_x_minus: ax25_frame.payload.beacon.panels.pd_x_minus
  :field pd_x_plus: ax25_frame.payload.beacon.panels.pd_x_plus
  :field pd_y_plus: ax25_frame.payload.beacon.panels.pd_y_plus
  :field pd_y_minus: ax25_frame.payload.beacon.panels.pd_y_minus

seq:
  - id: ax25_frame
    type: ax25_frame
    doc-ref: 'https://www.tapr.org/pub_ax25.html'

types:
  # ===== AX25 HEADERS =====
  ax25_frame:
    meta:
      endian: be # AX.25 is big-endian
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
    meta:
      endian: be
    seq:
      - id: dest_callsign_raw
        type: dest_callsign_raw
      - id: dest_ssid_raw
        type: ssid_mask
      - id: src_callsign_raw
        type: src_callsign_raw
      - id: src_ssid_raw
        type: ssid_mask
      - id: ctl
        type: u1

  dest_callsign_raw:
    meta:
      endian: be
    seq:
      - id: dest_callsign_ror
        process: ror(1)
        size: 6
        type: dest_callsign

  dest_callsign:
    meta:
      endian: be
    seq:
      - id: dest_callsign
        type: str
        encoding: ASCII
        size: 6

  src_callsign_raw:
    meta:
      endian: be
    seq:
      - id: src_callsign_ror
        process: ror(1)
        size: 6
        type: src_callsign

  src_callsign:
    meta:
      endian: be
    seq:
      - id: src_callsign
        type: str
        encoding: ASCII
        size: 6
        valid: '"WP2XJL"'

  ssid_mask:
    meta:
      endian: be
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x0f) >> 1

  i_frame:
    meta:
      endian: be
    seq:
      - id: pid
        type: u1
      - id: beacon 
        type: beacon

  ui_frame:
    meta:
      endian: be
    seq:
      - id: pid
        type: u1
      - id: beacon 
        type: beacon

  # ===== RHOKSAT TELEMETRY =====
  imtq: 
    meta:
      endian: le
    seq: 
      - id: rate_x 
        type: u2
        doc: "Magnetorquer angular rate along the x-axis"
      - id: rate_y 
        type: u2
        doc: "Magnetorquer angular rate along the y-axis"     
      - id: rate_z 
        type: u2
        doc: "Magnetorquer angular rate along the z-axis" 
      - id: total
        type: u2
        doc: "Magnetorquer angular rate vector magnitude"

  sun_sensor:
    meta:
      endian: le
    seq:
      - id: tl 
        type: f4
        doc: "Top left photodiode"
      - id: bl
        type: f4
        doc: "Bottom left photodiode"    
      - id: br
        type: f4
        doc: "Bottom right photodiode"  
      - id: tr
        type: f4
        doc: "Top right photodiode"    

  panels:
    meta:
      endian: le
    seq:
      - id: pd_z_minus  
        type: u4
        doc: "Diode readings of solar panel on Z- face"
      - id: pd_x_minus 
        type: u4
        doc: "Diode readings of solar panel on X- face"
      - id: pd_x_plus
        type: u4
        doc: "Diode readings of solar panel on X+ face"
      - id: pd_y_plus
        type: u4
        doc: "Diode readings of solar panel on Y+ face"
      - id: pd_y_minus 
        type: u4
        doc: "Diode readings of solar panel on Y- face"

  gyro:
    meta:
      endian: le
    seq:
      - id: gyro_x_raw
        type: u2
        doc: "Raw gyroscope readings along the x-axis"
      - id: gyro_y_raw 
        type: u2
        doc: "Raw gyroscope readings along the y-axis"    
      - id: gyro_z_raw
        type: u2
        doc: "Raw gyroscope readings along the z-axis"      

  accelerometer:
    meta:
      endian: le
    seq:
      - id: acc_x_raw 
        type: u2
        doc: "Raw accelerometer readings along the x-axis"
      - id: acc_y_raw 
        type: u2
        doc: "Raw accelerometer readings along the y-axis"    
      - id: acc_z_raw 
        type: u2
        doc: "Raw accelerometer readings along the z-axis"  

  beacon: 
    meta:
      endian: le # RHOKSAT payload is little-endian
    seq: 
      - id: beacon_id
        type: u1
        doc: "Identifier for beacon message"
        valid: 0xFD
      - id: num_reboots
        type: s4
        doc: "Number of times satellite has rebooted since launch"
      - id: bat_voltage 
        type: s4
        doc: "Battery voltage (mV)"
      - id: imtq
        type: imtq
        doc: "Magnetorquer angular rates along three axes (deg/s)"
      - id: num_of_sweeps 
        type: u4
        doc: "Number of experimental IV sweep files stored on the SD card"
      - id: num_of_logs 
        type: u4
        doc: "Number of log entries stored on the SD card"
      - id: time 
        type: u4
        doc: "Unix epoch time (s)"
      - id: sdcard_id 
        type: u1
        doc: "SD card ID indicates primary (0) or backup (1)"
        valid:
          any-of:
            - 0 
            - 1
      - id: gyro
        type: gyro
        doc: "Gyroscope angular velocities along three axes (deg/s)" 
      - id: accelerometer
        type: accelerometer
        doc: "Accelerometer linear acceleration along three axes (m/s^2)"
      - id: sun_sensor
        type: sun_sensor
        doc: "Quad-photodiode used to trigger experiments based on light angle and intensity (V)"
      - id: panels
        type: panels
        doc: "Solar panel diode data used to monitor power generation for charging (mV)"
