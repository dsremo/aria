---
meta:
  id: co65
  title: CO-65 CW decoder
  endian: be
doc-ref: "https://web.archive.org/web/20210928003812/http://lss.mes.titech.ac.jp/ssp/cute1.7/cwtelemetry_e.html"
# 2024-08-14, DL7NDR
doc: |
  :field v3_3: v3_3
  :field v5: v5
  :field v_batt: v_batt
  :field v_batt_main_bus: v_batt_main_bus
  :field digipeater_mode: digipeater_mode
  :field dtmf_permission: dtmf_permission
  :field antenna_deployment: antenna_deployment
  :field tx_mutual_monitor: tx_mutual_monitor
  :field rx_mutual_monitor: rx_mutual_monitor
  :field usb_enable: usb_enable
  :field satellite_mode: satellite_mode
  :field temp_com_board: temp_com_board
  :field temp_batt: temp_batt
  :field i_batt: i_batt
  :field s_meter_144: s_meter_144
  :field s_meter_1200: s_meter_1200
  :field power_dj_c5_tx: power_dj_c5_tx
  :field power_cw_430_beacon: power_cw_430_beacon
  :field power_th_59_1200_uplink: power_th_59_1200_uplink
  :field power_pda: power_pda
  :field power_daq: power_daq
  :field power_apd_main: power_apd_main
  :field power_apd_3_3b: power_apd_3_3b
  :field power_apd_3_3a: power_apd_3_3a

seq:
  - id: callsign
    type: str
    size: 4
    encoding: ASCII
    valid:
     any-of:
       - '"CUTE"'
       - '"cute"'

  - id: v3_3_raw
    type: u1

  - id: v5_raw
    type: u1

  - id: v_batt_raw
    type: u1

  - id: v_batt_main_bus_raw
    type: u1

  - id: sat_status
    type: u1

  - id: temp_com_board_raw
    type: u1

  - id: temp_batt_raw
    type: u1

  - id: i_batt_raw
    type: u1

  - id: s_meter_144_raw
    type: u1

  - id: s_meter_1200_raw
    type: u1

  - id: fet_status
    type: u1

instances:
   v3_3:
     value: v3_3_raw*6.16/255

   v5:
     value: v5_raw*6.16/255

   v_batt:
     value: v_batt_raw*6.16/255

   v_batt_main_bus:
     value: v_batt_main_bus_raw*9.24/255

   temp_com_board:
     value: ((3.08*temp_com_board_raw/255)-0.424)/0.00625

   temp_batt:
     value: ((3.08*temp_batt_raw/255)-0.424)/0.00625

   i_batt:
     value: (-3.08924*i_batt_raw/255)+1.486

   s_meter_144:
     value: (202.972*s_meter_144_raw/255)-171.5

   s_meter_1200:
     value: (54.824*s_meter_1200_raw/255)-151.9

   satellite_mode:
     value: (sat_status & 0b10000000) >> 7

   usb_enable:
     value: (sat_status & 0b01000000) >> 6

   rx_mutual_monitor:
     value: (sat_status & 0b00100000) >> 5

   tx_mutual_monitor:
     value: (sat_status & 0b00010000) >> 4

   antenna_deployment:
     value: (sat_status & 0b00001000) >> 3

   dtmf_permission:
     value: (sat_status & 0b00000100) >> 2

   digipeater_mode:
     value: sat_status & 0b00000011

   power_apd_3_3a:
     value: (fet_status & 0b10000000) >> 7

   power_apd_3_3b:
     value: (fet_status & 0b01000000) >> 6

   power_apd_main:
     value: (fet_status & 0b00100000) >> 5

   power_daq:
     value: (fet_status & 0b00010000) >> 4

   power_pda:
     value: (fet_status & 0b00001000) >> 3

   power_th_59_1200_uplink:
     value: (fet_status & 0b00000100) >> 2

   power_cw_430_beacon:
     value: (fet_status & 0b00000010) >> 1

   power_dj_c5_tx:
     value: fet_status & 0b00000001
