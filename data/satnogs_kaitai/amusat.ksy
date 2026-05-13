meta:
  id: amusat
  endian: be
  title: AMUSAT
doc-ref: 'https://amu-sat.github.io/'
doc: |
  :field flag1: flag1
  :field dest_address: ax25_header.dest_address
  :field dest_ssid: ax25_header.dest_ssid
  :field src_address: ax25_header.src_address
  :field src_ssid: ax25_header.src_ssid
  :field control_id: ax25_header.control_id
  :field pid: ax25_header.pid
  :field packet_type: information_field.packet_type
  :field sensor1: information_field.telemetry_data_1.sensor1
  :field sensor2: information_field.telemetry_data_1.sensor2
  :field sensor3: information_field.telemetry_data_1.sensor3
  :field sensor4: information_field.telemetry_data_1.sensor4
  :field battery_voltage: information_field.telemetry_data_1.battery_voltage
  :field battery_temperature: information_field.telemetry_data_1.battery_temperature
  :field battery_soc: information_field.telemetry_data_1.battery_soc
  :field battery_current: information_field.telemetry_data_1.battery_current
  :field temp_in: information_field.telemetry_data_1.temp_in
  :field temp_out: information_field.telemetry_data_1.temp_out
  :field temp_3: information_field.telemetry_data_1.temp_3
  :field pl_temp: information_field.telemetry_data_1.pl_temp
  :field rtc: information_field.telemetry_data_1.rtc
  :field temp_out_l: information_field.telemetry_data_1.temp_out_l
  :field temp_out_h: information_field.telemetry_data_1.temp_out_h
  :field acceleration_x: information_field.telemetry_data_1.acceleration_x
  :field acceleration_y: information_field.telemetry_data_1.acceleration_y
  :field acceleration_z: information_field.telemetry_data_1.acceleration_z
  :field magnetic_field_x: information_field.telemetry_data_1.magnetic_field_x
  :field magnetic_field_y: information_field.telemetry_data_1.magnetic_field_y
  :field magnetic_field_z: information_field.telemetry_data_1.magnetic_field_z
  :field angular_rate_x: information_field.telemetry_data_1.angular_rate_x
  :field angular_rate_y: information_field.telemetry_data_1.angular_rate_y
  :field angular_rate_z: information_field.telemetry_data_1.angular_rate_z
  :field velocity: information_field.telemetry_data_1.velocity
  :field latitude: information_field.telemetry_data_1.latitude
  :field longitude: information_field.telemetry_data_1.longitude
  :field gps_time: information_field.telemetry_data_1.gps_time
  :field solar_deployment_status: information_field.telemetry_data_1.solar_deployment_status
  :field eps_health_status: information_field.telemetry_data_1.eps_health_status
  :field adcs_health_status: information_field.telemetry_data_1.adcs_health_status
  :field payload_health_status: information_field.telemetry_data_1.payload_health_status
  :field com_health_status: information_field.telemetry_data_1.com_health_status
  :field battery1_health_status: information_field.telemetry_data_1.battery1_health_status
  :field battery2_health_status: information_field.telemetry_data_1.battery2_health_status
  :field image_number: information_field.image_data_0.image_number
  :field total_image_packets: information_field.image_data_0.total_image_packets
  :field image_packet_number: information_field.image_data_0.image_packet_number
  :field payload_array_size: information_field.image_data_0.payload_array_size
  :field payload_data: information_field.image_data_0.payload_data.b64encstring.image_data_b64_encoded
  :field fcs: fcs
  :field flag2: flag2

seq:
  - id: flag1
    type: u1
    doc: "AX.25 Flag 1 (1 byte)"

  - id: ax25_header
    type: ax25_header_struct
    doc: "AX.25 Header"

  - id: information_field
    type: information_field_struct
    doc: "Information Field"

  - id: fcs
    type: u2
    doc: "Frame Check Sequence (FCS) (2 bytes)"

  - id: flag2
    type: u1
    doc: "AX.25 Flag 2 (1 byte)"

types:
  base64:
    seq:
      - id: b64encstring
        process: satnogsdecoders.process.b64encode
        type: base64string
        size: 236
  base64string:
    seq:
      - id: image_data_b64_encoded
        type: str
        encoding: UTF-8
        size: 236
  ax25_header_struct:
    seq:
      - id: dest_address
        type: str
        size: 7
        encoding: "ASCII"
        doc: "Destination address (7 bytes)"

      - id: dest_ssid
        type: u1
        doc: "Destination SSID (1 byte)"

      - id: src_address
        type: str
        size: 7
        encoding: "ASCII"
        doc: "Source address (7 bytes)"

      - id: src_ssid
        type: u1
        doc: "Source SSID (1 byte)"

      - id: control_id
        type: u1
        doc: "Control ID (1 byte)"

      - id: pid
        type: u1
        doc: "Packet ID (1 byte)"

  information_field_struct:
    seq:
      - id: packet_type
        type: u1
        doc: "Packet Type (1 byte)"

      - id: telemetry_data_1
        type: telemetry_data_struct_1
        doc: "Telemetry Data (Type 1)"
        if: packet_type == 1

      - id: image_data_0
        type: image_data_struct_0
        doc: "Image Data (Type 0)"
        if: packet_type == 0

  telemetry_data_struct_1:
    seq:
      - id: sensor1
        type: f4
        doc: "CURRENT SENSOR_1 - Measures current (CURRENT)"

      - id: sensor2
        type: f4
        doc: "CURRENT SENSOR_2 - Measures current (CURRENT)"

      - id: sensor3
        type: f4
        doc: "CURRENT SENSOR_3 - Measures current (CURRENT)"

      - id: sensor4
        type: f4
        doc: "CURRENT SENSOR_4 - Measures current (CURRENT)"

      - id: battery_voltage
        type: f4
        doc: "BATTERY VOLT. FUEL GUAGE 1 - Battery voltage (CURRENT)"

      - id: battery_temperature
        type: f4
        doc: "BATTERY TEMP. FUEL GUAGE 1 - Temperature (CELSIUS)"

      - id: battery_soc
        type: f4
        doc: "BATTERY STATE OF CHARGE - SOC alarm level (percentage)"

      - id: battery_current
        type: f4
        doc: "BAT. CURRENT FUEL GUAGE 1 - Battery current (CURRENT)"

      - id: temp_in
        type: u1
        doc: "TEMP_IN - Temperature inside"

      - id: temp_out
        type: u1
        doc: "TEMP_OUT - Temperature outside"

      - id: temp_3
        type: u1
        doc: "TEMP_3 - Temperature data 2 LSB"

      - id: pl_temp
        type: u1
        doc: "PL_TEMP - Temperature payload"

      - id: rtc
        type: u8
        doc: "RTC - Seconds since Epoch time"

      - id: temp_out_l
        type: u1
        doc: "TEMP_OUT_L - Temperature data LSB"

      - id: temp_out_h
        type: u1
        doc: "TEMP_OUT_H - Temperature data MSB"

      - id: acceleration_x
        type: f4
        doc: "A_X - acceleration along X axis (m/s^2)"

      - id: acceleration_y
        type: f4
        doc: "A_Y - acceleration along Y axis (m/s^2)"

      - id: acceleration_z
        type: f4
        doc: "A_Z - acceleration along Z axis (m/s^2)"

      - id: magnetic_field_x
        type: f4
        doc: "MF_X - Magnetic field strength - X axis (uT)"

      - id: magnetic_field_y
        type: f4
        doc: "MF_Y - Magnetic field strength - Y axis (uT)"

      - id: magnetic_field_z
        type: f4
        doc: "MF_Z - Magnetic field strength - Z axis (uT)"

      - id: angular_rate_x
        type: f4
        doc: "AR_X - Angular rate along X-axis (dps)"

      - id: angular_rate_y
        type: f4
        doc: "AR_Y - Angular rate along Y-axis (dps)"

      - id: angular_rate_z
        type: f4
        doc: "AR_Z - Angular rate along Z-axis (dps)"

      - id: velocity
        type: f4
        doc: "VELOCITY - Velocity"

      - id: latitude
        type: f4
        doc: "LATITUDE - Latitude"

      - id: longitude
        type: f4
        doc: "LONGITUDE - Longitude"

      - id: gps_time
        type: u8
        doc: "TIME - GPS Time"

      - id: solar_deployment_status
        type: b1
        doc: "SOLAR DEPLOYMENT STATUS - Binary"

      - id: eps_health_status
        type: b1
        doc: "EPS HEALTH STATUS - Binary"

      - id: adcs_health_status
        type: b1
        doc: "ADCS HEALTH STATUS - Binary"

      - id: payload_health_status
        type: b1
        doc: "PAYLOAD HEALTH STATUS - Binary"

      - id: com_health_status
        type: b1
        doc: "COM HEALTH STATUS - Binary"

      - id: battery1_health_status
        type: b1
        doc: "BATTERY 1 HEALTH STATUS - Binary"

      - id: battery2_health_status
        type: b1
        doc: "BATTERY 2 HEALTH STATUS - Binary"
          
  image_data_struct_0:
    seq:
      - id: image_number
        type: u1
        doc: "Image Number (1 byte)"

      - id: total_image_packets
        type: u8
        doc: "Toal Image Packets (1 byte)"

      - id: image_packet_number
        type: u8
        doc: "Image Packet Number (1 byte)"

      - id: payload_array_size
        type: u1
        doc: "Payload Array Size (1 byte)"    

      - id: payload_data
        type: base64
        size: 236
        doc: "Image Payload Data (236 bytes)"
