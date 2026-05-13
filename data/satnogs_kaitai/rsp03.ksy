---
meta:
  id: rsp03
  title: RSP-03 GMSK decoder
  endian: le
doc-ref: "https://rsp03.rymansat.com/assets/pdfs/RSP-03_HK_Beacon_Format(JP)_Rev1R0.pdf"
# 2025-08-03, <czh00361 or JS1YOY>, 2025-10-13 DL7NDR Update for type: f4 problem

doc: |
  ## GMSK AX.25(w/G3RUH SatNOGS Default set)
  :field dest_callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field ctl: ax25_frame.ax25_header.ctl
  :field pid: ax25_frame.ax25_header.pid
  :field no001_header: ax25_frame.payload.no001_header

  :field no002_time: ax25_frame.payload.no002_time
  :field no003_time: ax25_frame.payload.no003_time
  :field packet_type: ax25_frame.payload.no004_packet_type.packet_type
  :field no005_telemetry_id: ax25_frame.payload.no004_packet_type.type_check.no005_telemetry_id
  :field no006_cobc_boot_count: ax25_frame.payload.no004_packet_type.type_check.no006_cobc_boot_count
  :field no007_cobc_elapsed_time: ax25_frame.payload.no004_packet_type.type_check.no007_cobc_elapsed_time
  :field no008_satellite_system_time: ax25_frame.payload.no004_packet_type.type_check.no008_satellite_system_time
  :field no009_cobc_temperature: ax25_frame.payload.no004_packet_type.type_check.no009_cobc_temperature
  :field no010_satellite_operation_mode: ax25_frame.payload.no004_packet_type.type_check.no010_satellite_operation_mode
  :field no011_antenna_deployment_status: ax25_frame.payload.no004_packet_type.type_check.no011_antenna_deployment_status
  :field no011_flag_0: ax25_frame.payload.no004_packet_type.type_check.no011_flag_0
  :field no011_flag_1: ax25_frame.payload.no004_packet_type.type_check.no011_flag_1
  :field no011_flag_2: ax25_frame.payload.no004_packet_type.type_check.no011_flag_2
  :field no011_flag_3: ax25_frame.payload.no004_packet_type.type_check.no011_flag_3
  :field no011_flag_4: ax25_frame.payload.no004_packet_type.type_check.no011_flag_4
  :field no011_flag_5: ax25_frame.payload.no004_packet_type.type_check.no011_flag_5
  :field no011_flag_6: ax25_frame.payload.no004_packet_type.type_check.no011_flag_6
  :field no011_flag_7: ax25_frame.payload.no004_packet_type.type_check.no011_flag_7

  :field no012_uplink_command_reception_count: ax25_frame.payload.no004_packet_type.type_check.no012_uplink_command_reception_count
  :field no013_cobc_temperature_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no013_cobc_temperature_upper_limit_exceed_count
  :field no014_cobc_temperature_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no014_cobc_temperature_lower_limit_exceed_count
  :field no015_cobc_voltage_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no015_cobc_voltage_upper_limit_exceed_count
  :field no016_cobc_voltage_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no016_cobc_voltage_lower_limit_exceed_count
  :field no017_cobc_current_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no017_cobc_current_upper_limit_exceed_count
  :field no018_cobc_current_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no018_cobc_current_lower_limit_exceed_count
  :field no019_main_radio_temperature_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no019_main_radio_temperature_upper_limit_exceed_count
  :field no020_main_radio_temperature_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no020_main_radio_temperature_lower_limit_exceed_count
  :field no021_main_radio_voltage_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no021_main_radio_voltage_upper_limit_exceed_count
  :field no022_main_radio_voltage_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no022_main_radio_voltage_lower_limit_exceed_count
  :field no023_main_radio_current_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no023_main_radio_current_upper_limit_exceed_count
  :field no024_main_radio_current_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no024_main_radio_current_lower_limit_exceed_count
  :field no025_sub_radio_temperature_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no025_sub_radio_temperature_upper_limit_exceed_count
  :field no026_sub_radio_temperature_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no026_sub_radio_temperature_lower_limit_exceed_count
  :field no027_sub_radio_voltage_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no027_sub_radio_voltage_upper_limit_exceed_count
  :field no028_sub_radio_voltage_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no028_sub_radio_voltage_lower_limit_exceed_count
  :field no029_sub_radio_current_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no029_sub_radio_current_upper_limit_exceed_count
  :field no030_sub_radio_current_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no030_sub_radio_current_lower_limit_exceed_count
  :field no031_aobc_temperature_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no031_aobc_temperature_upper_limit_exceed_count
  :field no032_aobc_temperature_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no032_aobc_temperature_lower_limit_exceed_count
  :field no033_aobc_voltage_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no033_aobc_voltage_upper_limit_exceed_count
  :field no034_aobc_voltage_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no034_aobc_voltage_lower_limit_exceed_count
  :field no035_aobc_current_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no035_aobc_current_upper_limit_exceed_count
  :field no036_aobc_current_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no036_aobc_current_lower_limit_exceed_count
  :field no037_mobc_temperature_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no037_mobc_temperature_upper_limit_exceed_count
  :field no038_mobc_temperature_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no038_mobc_temperature_lower_limit_exceed_count
  :field no039_mobc_voltage_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no039_mobc_voltage_upper_limit_exceed_count
  :field no040_mobc_voltage_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no040_mobc_voltage_lower_limit_exceed_count
  :field no041_mobc_current_upper_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no041_mobc_current_upper_limit_exceed_count
  :field no042_mobc_current_lower_limit_exceed_count: ax25_frame.payload.no004_packet_type.type_check.no042_mobc_current_lower_limit_exceed_count
  :field no043_magnetic_torque_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no043_magnetic_torque_consumption_current
  :field no044_reaction_wheel_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no044_reaction_wheel_consumption_current
  :field no045_antenna_deployment_heater_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no045_antenna_deployment_heater_consumption_current
  :field no046_main_radio_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no046_main_radio_consumption_current
  :field no047_sub_radio_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no047_sub_radio_consumption_current
  :field no048_mobc_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no048_mobc_consumption_current
  :field no049_cobc_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no049_cobc_consumption_current
  :field no050_aobc_consumption_current: ax25_frame.payload.no004_packet_type.type_check.no050_aobc_consumption_current
  :field no051_5v_bus_voltage: ax25_frame.payload.no004_packet_type.type_check.no051_5v_bus_voltage
  :field no052_33v_line_voltage: ax25_frame.payload.no004_packet_type.type_check.no052_33v_line_voltage
  :field no053_bus_current: ax25_frame.payload.no004_packet_type.type_check.no053_bus_current
  :field no054_sap_z_face_voltage: ax25_frame.payload.no004_packet_type.type_check.no054_sap_z_face_voltage
  :field no055_sap_z_face_temperature: ax25_frame.payload.no004_packet_type.type_check.no055_sap_z_face_temperature
  :field no056_sap__z_face_voltage: ax25_frame.payload.no004_packet_type.type_check.no056_sap__z_face_voltage
  :field no057_sap__z_face_temperature: ax25_frame.payload.no004_packet_type.type_check.no057_sap__z_face_temperature
  :field no058_sap_y_face_voltage: ax25_frame.payload.no004_packet_type.type_check.no058_sap_y_face_voltage
  :field no059_sap_y_face_temperature: ax25_frame.payload.no004_packet_type.type_check.no059_sap_y_face_temperature
  :field no060_sap__x_face_voltage: ax25_frame.payload.no004_packet_type.type_check.no060_sap__x_face_voltage
  :field no061_sap__x_face_temperature: ax25_frame.payload.no004_packet_type.type_check.no061_sap__x_face_temperature
  :field no062_sap__y_face_voltage: ax25_frame.payload.no004_packet_type.type_check.no062_sap__y_face_voltage
  :field no063_sap__y_face_temperature: ax25_frame.payload.no004_packet_type.type_check.no063_sap__y_face_temperature
  :field no064_sap_z_face_current: ax25_frame.payload.no004_packet_type.type_check.no064_sap_z_face_current
  :field no065_sap__z_face_current: ax25_frame.payload.no004_packet_type.type_check.no065_sap__z_face_current
  :field no066_sap_y_face_current: ax25_frame.payload.no004_packet_type.type_check.no066_sap_y_face_current
  :field no067_sap__x_face_current: ax25_frame.payload.no004_packet_type.type_check.no067_sap__x_face_current
  :field no068_sap__y_face_current: ax25_frame.payload.no004_packet_type.type_check.no068_sap__y_face_current
  :field no069_battery_1_output_voltage: ax25_frame.payload.no004_packet_type.type_check.no069_battery_1_output_voltage
  :field no070_battery_1_charging_current: ax25_frame.payload.no004_packet_type.type_check.no070_battery_1_charging_current
  :field no071_battery_1_discharging_current: ax25_frame.payload.no004_packet_type.type_check.no071_battery_1_discharging_current
  :field no072_battery_1_temperature: ax25_frame.payload.no004_packet_type.type_check.no072_battery_1_temperature
  :field no073_battery_1_cumulative_charge: ax25_frame.payload.no004_packet_type.type_check.no073_battery_1_cumulative_charge
  :field no074_battery_1_cumulative_discharge: ax25_frame.payload.no004_packet_type.type_check.no074_battery_1_cumulative_discharge
  :field no075_battery_2_output_voltage: ax25_frame.payload.no004_packet_type.type_check.no075_battery_2_output_voltage
  :field no076_battery_2_charging_current: ax25_frame.payload.no004_packet_type.type_check.no076_battery_2_charging_current
  :field no077_battery_2_discharging_current: ax25_frame.payload.no004_packet_type.type_check.no077_battery_2_discharging_current
  :field no078_battery_2_temperature: ax25_frame.payload.no004_packet_type.type_check.no078_battery_2_temperature
  :field no079_battery_2_cumulative_charge: ax25_frame.payload.no004_packet_type.type_check.no079_battery_2_cumulative_charge
  :field no080_battery_2_cumulative_discharge: ax25_frame.payload.no004_packet_type.type_check.no080_battery_2_cumulative_discharge
  :field no081_equipment_power_anomaly_status: ax25_frame.payload.no004_packet_type.type_check.no081_equipment_power_anomaly_status
  :field no081_flag_0: ax25_frame.payload.no004_packet_type.type_check.no081_flag_0
  :field no081_flag_1: ax25_frame.payload.no004_packet_type.type_check.no081_flag_1
  :field no081_flag_2: ax25_frame.payload.no004_packet_type.type_check.no081_flag_2
  :field no081_flag_3: ax25_frame.payload.no004_packet_type.type_check.no081_flag_3
  :field no081_flag_4: ax25_frame.payload.no004_packet_type.type_check.no081_flag_4
  :field no081_flag_5: ax25_frame.payload.no004_packet_type.type_check.no081_flag_5
  :field no081_flag_6: ax25_frame.payload.no004_packet_type.type_check.no081_flag_6
  :field no081_flag_7: ax25_frame.payload.no004_packet_type.type_check.no081_flag_7

  :field no082_equipment_power_status: ax25_frame.payload.no004_packet_type.type_check.no082_equipment_power_status
  :field no082_flag_0: ax25_frame.payload.no004_packet_type.type_check.no082_flag_0
  :field no082_flag_1: ax25_frame.payload.no004_packet_type.type_check.no082_flag_1
  :field no082_flag_2: ax25_frame.payload.no004_packet_type.type_check.no082_flag_2
  :field no082_flag_3: ax25_frame.payload.no004_packet_type.type_check.no082_flag_3
  :field no082_flag_4: ax25_frame.payload.no004_packet_type.type_check.no082_flag_4
  :field no082_flag_5: ax25_frame.payload.no004_packet_type.type_check.no082_flag_5
  :field no082_flag_6: ax25_frame.payload.no004_packet_type.type_check.no082_flag_6
  :field no082_flag_7: ax25_frame.payload.no004_packet_type.type_check.no082_flag_7

  :field no083_mppt_status: ax25_frame.payload.no004_packet_type.type_check.no083_mppt_status
  :field no083_flag_0: ax25_frame.payload.no004_packet_type.type_check.no083_flag_0
  :field no083_flag_1: ax25_frame.payload.no004_packet_type.type_check.no083_flag_1
  :field no083_flag_2: ax25_frame.payload.no004_packet_type.type_check.no083_flag_2
  :field no083_flag_3: ax25_frame.payload.no004_packet_type.type_check.no083_flag_3
  :field no083_flag_4: ax25_frame.payload.no004_packet_type.type_check.no083_flag_4
  :field no083_flag_5: ax25_frame.payload.no004_packet_type.type_check.no083_flag_5
  :field no083_flag_6: ax25_frame.payload.no004_packet_type.type_check.no083_flag_6
  :field no083_flag_7: ax25_frame.payload.no004_packet_type.type_check.no083_flag_7

  :field no084_battery_chargedischarge_controller_status: ax25_frame.payload.no004_packet_type.type_check.no084_battery_chargedischarge_controller_status
  :field no084_flag_0: ax25_frame.payload.no004_packet_type.type_check.no084_flag_0
  :field no084_flag_1: ax25_frame.payload.no004_packet_type.type_check.no084_flag_1
  :field no084_flag_2: ax25_frame.payload.no004_packet_type.type_check.no084_flag_2
  :field no084_flag_3: ax25_frame.payload.no004_packet_type.type_check.no084_flag_3
  :field no084_flag_4: ax25_frame.payload.no004_packet_type.type_check.no084_flag_4
  :field no084_flag_5: ax25_frame.payload.no004_packet_type.type_check.no084_flag_5
  :field no084_flag_6: ax25_frame.payload.no004_packet_type.type_check.no084_flag_6
  :field no084_flag_7: ax25_frame.payload.no004_packet_type.type_check.no084_flag_7

  :field no085_internal_equipment_communication_error_status: ax25_frame.payload.no004_packet_type.type_check.no085_internal_equipment_communication_error_status
  :field no085_flag_0: ax25_frame.payload.no004_packet_type.type_check.no085_flag_0
  :field no085_flag_1: ax25_frame.payload.no004_packet_type.type_check.no085_flag_1
  :field no085_flag_2: ax25_frame.payload.no004_packet_type.type_check.no085_flag_2
  :field no085_flag_3: ax25_frame.payload.no004_packet_type.type_check.no085_flag_3
  :field no085_flag_4: ax25_frame.payload.no004_packet_type.type_check.no085_flag_4
  :field no085_flag_5: ax25_frame.payload.no004_packet_type.type_check.no085_flag_5
  :field no085_flag_6: ax25_frame.payload.no004_packet_type.type_check.no085_flag_6
  :field no085_flag_7: ax25_frame.payload.no004_packet_type.type_check.no085_flag_7
 
  :field no086_main_radio_boot_count: ax25_frame.payload.no004_packet_type.type_check.no086_main_radio_boot_count
  :field no087_main_radio_elapsed_time: ax25_frame.payload.no004_packet_type.type_check.no087_main_radio_elapsed_time
  :field no088_main_radio_no_reception_time: ax25_frame.payload.no004_packet_type.type_check.no088_main_radio_no_reception_time
  :field no089_main_radio_rssi: ax25_frame.payload.no004_packet_type.type_check.no089_main_radio_rssi
  :field no090_main_radio_uplink_reception_counter: ax25_frame.payload.no004_packet_type.type_check.no090_main_radio_uplink_reception_counter
  :field no091_main_radio_uplink_modulation: ax25_frame.payload.no004_packet_type.type_check.no091_main_radio_uplink_modulation
  :field no092_main_radio_downlink_modulation: ax25_frame.payload.no004_packet_type.type_check.no092_main_radio_downlink_modulation
  :field no093_main_radio_downlink_protocol: ax25_frame.payload.no004_packet_type.type_check.no093_main_radio_downlink_protocol
  :field no094_main_radio_frequency_lock: ax25_frame.payload.no004_packet_type.type_check.no094_main_radio_frequency_lock
  :field no095_main_radio_pa_temperature: ax25_frame.payload.no004_packet_type.type_check.no095_main_radio_pa_temperature
  :field no096_main_radio_pa_current: ax25_frame.payload.no004_packet_type.type_check.no096_main_radio_pa_current
  :field no097_main_radio_mcu_temperature_: ax25_frame.payload.no004_packet_type.type_check.no097_main_radio_mcu_temperature_
  :field no098_sub_radio_boot_count: ax25_frame.payload.no004_packet_type.type_check.no098_sub_radio_boot_count
  :field no099_sub_radio_elapsed_time: ax25_frame.payload.no004_packet_type.type_check.no099_sub_radio_elapsed_time
  :field no100_sub_radio_no_reception_time: ax25_frame.payload.no004_packet_type.type_check.no100_sub_radio_no_reception_time
  :field no101_sub_radio_rssi: ax25_frame.payload.no004_packet_type.type_check.no101_sub_radio_rssi
  :field no102_sub_radio_uplink_reception_counter: ax25_frame.payload.no004_packet_type.type_check.no102_sub_radio_uplink_reception_counter
  :field no103_sub_radio_uplink_modulation: ax25_frame.payload.no004_packet_type.type_check.no103_sub_radio_uplink_modulation
  :field no104_sub_radio_downlink_modulation: ax25_frame.payload.no004_packet_type.type_check.no104_sub_radio_downlink_modulation
  :field no105_sub_radio_downlink_protocol: ax25_frame.payload.no004_packet_type.type_check.no105_sub_radio_downlink_protocol
  :field no106_sub_radio_frequency_lock: ax25_frame.payload.no004_packet_type.type_check.no106_sub_radio_frequency_lock
  :field no107_sub_radio_pa_temperature: ax25_frame.payload.no004_packet_type.type_check.no107_sub_radio_pa_temperature
  :field no108_sub_radio_pa_current: ax25_frame.payload.no004_packet_type.type_check.no108_sub_radio_pa_current
  :field no109_sub_radio_mcu_temperature: ax25_frame.payload.no004_packet_type.type_check.no109_sub_radio_mcu_temperature

  :field no006_cobc_uptime_: ax25_frame.payload.no004_packet_type.type_check.no006_cobc_uptime_
  :field no007_satellite_system_time: ax25_frame.payload.no004_packet_type.type_check.no007_satellite_system_time
  :field no008_mission_command_execution_result: ax25_frame.payload.no004_packet_type.type_check.no008_mission_command_execution_result
  :field no009_mission_command_execution_result_details: ax25_frame.payload.no004_packet_type.type_check.no009_mission_command_execution_result_details
  :field no010_os_time_at_telemetry_generation: ax25_frame.payload.no004_packet_type.type_check.no010_os_time_at_telemetry_generation
  :field no011_system_time_at_telemetry_generation: ax25_frame.payload.no004_packet_type.type_check.no011_system_time_at_telemetry_generation
  :field no012_mobc_temperature: ax25_frame.payload.no004_packet_type.type_check.no012_mobc_temperature
  :field no013_composition_system_status: ax25_frame.payload.no004_packet_type.type_check.no013_composition_system_status
  :field no014_stt_status: ax25_frame.payload.no004_packet_type.type_check.no014_stt_status
  :field no015_right_ascension_last_acquired_by_stt: ax25_frame.payload.no004_packet_type.type_check.no015_right_ascension_last_acquired_by_stt
  :field no016_declination_last_acquired_by_stt: ax25_frame.payload.no004_packet_type.type_check.no016_declination_last_acquired_by_stt
  :field no017_roll_angle_last_acquired_by_stt: ax25_frame.payload.no004_packet_type.type_check.no017_roll_angle_last_acquired_by_stt
  :field no018_validity_of_acquired_coordinates: ax25_frame.payload.no004_packet_type.type_check.no018_validity_of_acquired_coordinates
  :field no019_image_capture_time: ax25_frame.payload.no004_packet_type.type_check.no019_image_capture_time
  :field no020_most_recent_command_id_1: ax25_frame.payload.no004_packet_type.type_check.no020_most_recent_command_id_1
  :field no021_most_recent_command_result_1: ax25_frame.payload.no004_packet_type.type_check.no021_most_recent_command_result_1
  :field no022_most_recent_command_result_detail_1: ax25_frame.payload.no004_packet_type.type_check.no022_most_recent_command_result_detail_1
  :field no023_most_recent_command_id_2: ax25_frame.payload.no004_packet_type.type_check.no023_most_recent_command_id_2
  :field no024_most_recent_command_result_2: ax25_frame.payload.no004_packet_type.type_check.no024_most_recent_command_result_2
  :field no025_most_recent_command_result_detail_2: ax25_frame.payload.no004_packet_type.type_check.no025_most_recent_command_result_detail_2
  :field no026_most_recent_command_id_3: ax25_frame.payload.no004_packet_type.type_check.no026_most_recent_command_id_3
  :field no027_most_recent_command_result_3: ax25_frame.payload.no004_packet_type.type_check.no027_most_recent_command_result_3
  :field no028_most_recent_command_result_detail_3: ax25_frame.payload.no004_packet_type.type_check.no028_most_recent_command_result_detail_3

  :field no006_cobc_uptime: ax25_frame.payload.no004_packet_type.type_check.no006_cobc_uptime
  :field no007_satellite_system_time: ax25_frame.payload.no004_packet_type.type_check.no007_satellite_system_time
  :field no008_telemetry_type: ax25_frame.payload.no004_packet_type.type_check.no008_telemetry_type
  :field no009_attitude_control_mode: ax25_frame.payload.no004_packet_type.type_check.no009_attitude_control_mode
  :field no010_ground_packet_reception_count: ax25_frame.payload.no004_packet_type.type_check.no010_ground_packet_reception_count
  :field no011_x_axis_rw_mode: ax25_frame.payload.no004_packet_type.type_check.no011_x_axis_rw_mode
  :field no012_x_axis_rw_speed: ax25_frame.payload.no004_packet_type.type_check.no012_x_axis_rw_speed
  :field no013_x_axis_rw_status: ax25_frame.payload.no004_packet_type.type_check.no013_x_axis_rw_status
  :field no014_y_axis_rw_mode: ax25_frame.payload.no004_packet_type.type_check.no014_y_axis_rw_mode
  :field no015_y_axis_rw_speed: ax25_frame.payload.no004_packet_type.type_check.no015_y_axis_rw_speed
  :field no016_y_axis_rw_status: ax25_frame.payload.no004_packet_type.type_check.no016_y_axis_rw_status
  :field no017_z_axis_rw_mode: ax25_frame.payload.no004_packet_type.type_check.no017_z_axis_rw_mode
  :field no018_z_axis_rw_speed: ax25_frame.payload.no004_packet_type.type_check.no018_z_axis_rw_speed
  :field no019_z_axis_rw_status: ax25_frame.payload.no004_packet_type.type_check.no019_z_axis_rw_status
  :field no020_x_axis_mtq_mode: ax25_frame.payload.no004_packet_type.type_check.no020_x_axis_mtq_mode
  :field no021_x_axis_mtq_set_voltage: ax25_frame.payload.no004_packet_type.type_check.no021_x_axis_mtq_set_voltage
  :field no022_x_axis_mtq_status: ax25_frame.payload.no004_packet_type.type_check.no022_x_axis_mtq_status
  :field no023_y_axis_mtq_mode: ax25_frame.payload.no004_packet_type.type_check.no023_y_axis_mtq_mode
  :field no024_y_axis_mtq_set_voltage: ax25_frame.payload.no004_packet_type.type_check.no024_y_axis_mtq_set_voltage
  :field no025_y_axis_mtq_status: ax25_frame.payload.no004_packet_type.type_check.no025_y_axis_mtq_status
  :field no026_z_axis_mtq_mode: ax25_frame.payload.no004_packet_type.type_check.no026_z_axis_mtq_mode
  :field no027_z_axis_mtq_set_voltage: ax25_frame.payload.no004_packet_type.type_check.no027_z_axis_mtq_set_voltage
  :field no028_z_axis_mtq_status: ax25_frame.payload.no004_packet_type.type_check.no028_z_axis_mtq_status
  :field no029_imu1_x_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no029_imu1_x_axis_acceleration
  :field no030_imu1_y_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no030_imu1_y_axis_acceleration
  :field no031_imu1_z_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no031_imu1_z_axis_acceleration
  :field no032_imu1_x_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no032_imu1_x_axis_angular_velocity
  :field no033_imu1_y_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no033_imu1_y_axis_angular_velocity
  :field no034_imu1_z_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no034_imu1_z_axis_angular_velocity
  :field no035_imu1_x_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no035_imu1_x_axis_magnetic_field
  :field no036_imu1_y_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no036_imu1_y_axis_magnetic_field
  :field no037_imu1_z_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no037_imu1_z_axis_magnetic_field
  :field no038_imu1_temperature: ax25_frame.payload.no004_packet_type.type_check.no038_imu1_temperature
  :field no039_imu1_status: ax25_frame.payload.no004_packet_type.type_check.no039_imu1_status
  :field no040_imu2_x_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no040_imu2_x_axis_acceleration
  :field no041_imu2_y_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no041_imu2_y_axis_acceleration
  :field no042_imu2_z_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no042_imu2_z_axis_acceleration
  :field no043_imu2_x_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no043_imu2_x_axis_angular_velocity
  :field no044_imu2_y_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no044_imu2_y_axis_angular_velocity
  :field no045_imu2_z_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no045_imu2_z_axis_angular_velocity
  :field no046_imu2_x_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no046_imu2_x_axis_magnetic_field
  :field no047_imu2_y_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no047_imu2_y_axis_magnetic_field
  :field no048_imu2_z_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no048_imu2_z_axis_magnetic_field
  :field no049_imu2_temperature: ax25_frame.payload.no004_packet_type.type_check.no049_imu2_temperature
  :field no050_imu2_status: ax25_frame.payload.no004_packet_type.type_check.no050_imu2_status
  :field no051_imu3_x_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no051_imu3_x_axis_acceleration
  :field no052_imu3_y_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no052_imu3_y_axis_acceleration
  :field no053_imu3_z_axis_acceleration: ax25_frame.payload.no004_packet_type.type_check.no053_imu3_z_axis_acceleration
  :field no054_imu3_x_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no054_imu3_x_axis_angular_velocity
  :field no055_imu3_y_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no055_imu3_y_axis_angular_velocity
  :field no056_imu3_z_axis_angular_velocity: ax25_frame.payload.no004_packet_type.type_check.no056_imu3_z_axis_angular_velocity
  :field no057_imu3_x_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no057_imu3_x_axis_magnetic_field
  :field no058_imu3_y_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no058_imu3_y_axis_magnetic_field
  :field no059_imu3_z_axis_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no059_imu3_z_axis_magnetic_field
  :field no060_imu3_temperature: ax25_frame.payload.no004_packet_type.type_check.no060_imu3_temperature
  :field no061_imu3_status: ax25_frame.payload.no004_packet_type.type_check.no061_imu3_status
  :field no062_x_axis_rw_proportional_gain: ax25_frame.payload.no004_packet_type.type_check.no062_x_axis_rw_proportional_gain
  :field no063_x_axis_rw_derivative_gain: ax25_frame.payload.no004_packet_type.type_check.no063_x_axis_rw_derivative_gain
  :field no064_y_axis_rw_proportional_gain: ax25_frame.payload.no004_packet_type.type_check.no064_y_axis_rw_proportional_gain
  :field no065_y_axis_rw_derivative_gain: ax25_frame.payload.no004_packet_type.type_check.no065_y_axis_rw_derivative_gain
  :field no066_z_axis_rw_proportional_gain: ax25_frame.payload.no004_packet_type.type_check.no066_z_axis_rw_proportional_gain
  :field no067_z_axis_rw_derivative_gain: ax25_frame.payload.no004_packet_type.type_check.no067_z_axis_rw_derivative_gain
  :field no068_commissioning_runtime_: ax25_frame.payload.no004_packet_type.type_check.no068_commissioning_runtime_
  :field no069_imu_fault_detection_threshold: ax25_frame.payload.no004_packet_type.type_check.no069_imu_fault_detection_threshold
  :field no070_active_imu: ax25_frame.payload.no004_packet_type.type_check.no070_active_imu
  :field no071_bdot_control_voltage: ax25_frame.payload.no004_packet_type.type_check.no071_bdot_control_voltage
  :field no072_bdot_reference_magnetic_field: ax25_frame.payload.no004_packet_type.type_check.no072_bdot_reference_magnetic_field

  # CW-related fields for Grafana/InfluxDB export
  :field cw_beacon: ax25_frame.cw_beacon
  :field cw_type: ax25_frame.cw_type
  :field cw_no001_Message_Identifier: ax25_frame.no001_message_identifier

  # ---------- CW 'G' (ASCII beacon) ----------

  :field cw_g_no002_Telemetry_Type: ax25_frame.no002_telemetry_type_value
  :field cw_g_no003_COBC_Boot_Count: ax25_frame.no003_cobc_boot_count_value
  :field cw_g_no004_COBC_Uptime_seconds: ax25_frame.no004_cobc_uptime_seconds_value
  :field cw_g_no005_COBC_Temperature_c: ax25_frame.no005_cobc_temperature_degc_value
  :field cw_g_no006_Satellite_Operation_Mode: ax25_frame.no006_satellite_operation_mode_value
  :field cw_g_no007_Antenna_Deployment_Status: ax25_frame.no007_antenna_deployment_status_value
  :field cw_g_no007_AntDep_plusX: ax25_frame.no007_antdep_bit_pos_x
  :field cw_g_no007_AntDep_minusX: ax25_frame.no007_antdep_bit_neg_x
  :field cw_g_no007_AntDep_plusY: ax25_frame.no007_antdep_bit_pos_y
  :field cw_g_no007_AntDep_minusY: ax25_frame.no007_antdep_bit_neg_y
  :field cw_g_no008_Uplink_Reception_Count: ax25_frame.no008_uplink_reception_count_value
  :field cw_g_no009_Battery1_V_mV: ax25_frame.no009_battery_1_voltage_mv_value
  :field cw_g_no010_Battery1_Charging_Current_First_mA: ax25_frame.no010_battery_1_charging_current_first_half_ma_value

  # ---------- CW 'H' (ASCII beacon) ----------

  :field cw_h_no002_Batt1_Charging_mA_second: ax25_frame.no002_battery_1_charging_current_second_half_ma_value
  :field cw_h_no003_Batt1_Discharging_mA: ax25_frame.no003_battery_1_discharging_current_ma_value
  :field cw_h_no004_Batt1_Temp_c: ax25_frame.no004_battery_1_temperature_degc_value
  :field cw_h_no005_Batt2_V_mV: ax25_frame.no005_battery_2_voltage_mv_value
  :field cw_h_no006_Batt2_Charging_mA: ax25_frame.no006_battery_2_charging_current_ma_value
  :field cw_h_no007_Batt2_Discharging_mA: ax25_frame.no007_battery_2_discharging_current_ma_value
  :field cw_h_no008_Batt2_Temp_c: ax25_frame.no008_battery_2_temperature_degc_value
  :field cw_h_no009_Subsys_PowerFault_bitmap: ax25_frame.no009_subsystem_power_fault_status_value
  :field cw_h_no009_NoFault_MOBC: ax25_frame.no009_fault_ok_mobc
  :field cw_h_no009_NoFault_TOBC_SUB: ax25_frame.no009_fault_ok_tobc_sub
  :field cw_h_no009_NoFault_RW: ax25_frame.no009_fault_ok_rw
  :field cw_h_no009_NoFault_ANTH: ax25_frame.no009_fault_ok_anth
  :field cw_h_no009_NoFault_TOBC_MAIN: ax25_frame.no009_fault_ok_tobc_main
  :field cw_h_no009_NoFault_MTQ: ax25_frame.no009_fault_ok_mtq
  :field cw_h_no009_NoFault_AOBC: ax25_frame.no009_fault_ok_aobc
  :field cw_h_no010_Subsys_OnOff_bitmap: ax25_frame.no010_subsystem_power_onoff_status_value
  :field cw_h_no010_On_MOBC: ax25_frame.no010_on_mobc
  :field cw_h_no010_On_AOBC: ax25_frame.no010_on_aobc
  :field cw_h_no010_On_TOBC_MAIN: ax25_frame.no010_on_tobc_main
  :field cw_h_no010_On_ANTDEP: ax25_frame.no010_on_antdep
  :field cw_h_no010_On_RW: ax25_frame.no010_on_rw
  :field cw_h_no010_On_TOBC_SUB: ax25_frame.no010_on_tobc_sub
  :field cw_h_no010_On_MTQ: ax25_frame.no010_on_mtq
  :field cw_h_no011_TOBC_Main_Boot_Count: ax25_frame.no011_tobc_main_boot_count_value

  # ---------- CW 'I' (ASCII beacon) ----------

  :field cw_i_no002_Main_TOBC_Operating_h: ax25_frame.no002_main_tobc_operating_time_hour_value
  :field cw_i_no003_Main_TOBC_Reception_Count: ax25_frame.no003_main_tobc_reception_count_value
  :field cw_i_no004_Sub_TOBC_Boot_Count: ax25_frame.no004_sub_tobc_boot_count_value
  :field cw_i_no005_Sub_TOBC_Operating_h: ax25_frame.no005_sub_tobc_operating_time_hour_value
  :field cw_i_no006_Sub_TOBC_Reception_Count: ax25_frame.no006_sub_tobc_reception_count_value
  :field cw_i_no007_AOBC_Operation_Mode: ax25_frame.no007_aobc_operation_mode_value
  :field cw_i_no008_ACS_Power_bitmap: ax25_frame.no008_attctrl_power_status_value
  :field cw_i_no008_On_RW1: ax25_frame.no008_on_rw1
  :field cw_i_no008_On_RW2: ax25_frame.no008_on_rw2
  :field cw_i_no008_On_RW3: ax25_frame.no008_on_rw3
  :field cw_i_no008_On_MTQ1: ax25_frame.no008_on_mtq1
  :field cw_i_no008_On_MTQ2: ax25_frame.no008_on_mtq2
  :field cw_i_no008_On_MTQ3: ax25_frame.no008_on_mtq3
  :field cw_i_no009_X_gyro_mdeg_s: ax25_frame.no009_x_axis_angular_velocity_mdeg_s_s16
  :field cw_i_no010_Y_gyro_mdeg_s: ax25_frame.no010_y_axis_angular_velocity_mdeg_s_s16
  :field cw_i_no011_Z_gyro_mdeg_s: ax25_frame.no011_z_axis_angular_velocity_mdeg_s_s16
  :field cw_i_no012_MOBC_Composition: ax25_frame.no012_composition_status
  :field cw_i_no012_MOBC_STT: ax25_frame.no012_stt_status
enums:
  aobc_operation_mode:       # CW I No.7
    1: standby
    2: stabilizing
    3: pointing
    4: unloading
    5: commissioning

  stt_status_cw_i:           # CW I No.12
    0: stopped
    1: standby
    2: calculating

  mission_cmd_result:        # Packet2 No.8
    0x00: success
    0xF1: crc_error
    0xF2: command_execution_error
    0xFF: command_not_executable

  mission_cmd_detail:        # Packet2 No.9
    0xFF00: async_command_received
    0xFFFF: mission_system_abnormal_termination
    0xFF01: json_parse_error
    0xFF02: command_processing_result_error
    0xFF03: command_id_not_found

  composition_status:        # Packet2 No.13
    0: stopped
    1: standby
    2: composing

  stt_status:                # Packet2 No.14
    0: stopped
    1: standby
    2: computing

  attitude_ctrl_mode:        # Packet3 No.9
    1: standby
    2: stabilizing
    3: pointing
    4: unloading
    5: commissioning

  enable_disable:            # Packet3 RW Mode (0:disable / 1:enable)
    0: disabled
    1: enabled

  mtq_mode:                  # Packet3 MTQ Mode (0:off / 1:active)
    0: off
    1: active

  active_imu:                # Packet3 No.70 (0/1/2)
    0: imu0
    1: imu1
    2: imu2

seq:
  - id: ax25_frame
    type:
      switch-on: first_tag
      cases:
        0x47: cw_g   # 'G'
        0x48: cw_h   # 'H'
        0x49: cw_i   # 'I'
        _: ax25_frame_body

instances:
  first_tag:
    pos: 0
    type: u1
types:
  ax25_frame_body:
    seq:
      - id: ax25_header
        type: ax25_header
      - id: payload
        type: rsp03_payload

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
        valid:
          any-of:
            - '"JS1YOY"'
            - '"JS1YPA"'

  ssid_mask:
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x1f) >> 1

  rsp03_payload:
    seq:
      - id: no001_header
        type: u4
        doc: "Header 5 u40 Always 0x0018AD8001,0x00184A8001,0x0018DF8001"
      - id: no001_header_1
        type: u1
      - id: no002_time
        type: u4
      - id: no003_time
        type: u2
      - id: no004_packet_type
        type: no004_packet_type_t

    instances:
      no001_header_u40:
        value: >
          ((no001_header & 0xff) << 32) +
          (((no001_header >> 8)  & 0xff) << 24) +
          (((no001_header >> 16) & 0xff) << 16) +
          (((no001_header >> 24) & 0xff) << 8)  +
          no001_header_1
        doc: "5-byte header (u40) reconstructed as BE from u4le + u1"

      header_valid:
        value: >
          (no001_header_u40 == 0x0018AD8001 or
          no001_header_u40 == 0x00184A8001 or
          no001_header_u40 == 0x0018DF8001)
        doc: "True if header matches known patterns"

    types:
      no004_packet_type_t:
        seq:
          - id: packet_type
            type: u1
          - id: type_check
            type:
              switch-on: packet_type
              cases:
                0x01: packet1
                0x02: packet2
                0x03: packet3

  packet1:
    seq:
    - id: no005_telemetry_id
      type: u2
    - id: no006_cobc_boot_count
      type: u4
    - id: no007_cobc_elapsed_time
      doc: sec
      type: u8
    - id: no008_satellite_system_time
      doc: ms
      type: u8
    - id: no009_cobc_temperature
      doc: mc
      type: s1
    - id: no010_satellite_operation_mode
      type: u1
    - id: no011_antenna_deployment_status
      type: u1
      doc: |
        Antenna deployment status bitmap (bit field, 1=Deployed, 0=Not): bit0:+X, bit1:-X, bit2:+Y, bit3:-Y, bit4-7:reserved
    - id: no012_uplink_command_reception_count
      type: u2
    - id: no013_cobc_temperature_upper_limit_exceed_count
      type: u1
    - id: no014_cobc_temperature_lower_limit_exceed_count
      type: u1
    - id: no015_cobc_voltage_upper_limit_exceed_count
      type: u1
    - id: no016_cobc_voltage_lower_limit_exceed_count
      type: u1
    - id: no017_cobc_current_upper_limit_exceed_count
      type: u1
    - id: no018_cobc_current_lower_limit_exceed_count
      type: u1
    - id: no019_main_radio_temperature_upper_limit_exceed_count
      type: u1
    - id: no020_main_radio_temperature_lower_limit_exceed_count
      type: u1
    - id: no021_main_radio_voltage_upper_limit_exceed_count
      type: u1
    - id: no022_main_radio_voltage_lower_limit_exceed_count
      type: u1
    - id: no023_main_radio_current_upper_limit_exceed_count
      type: u1
    - id: no024_main_radio_current_lower_limit_exceed_count
      type: u1
    - id: no025_sub_radio_temperature_upper_limit_exceed_count
      type: u1
    - id: no026_sub_radio_temperature_lower_limit_exceed_count
      type: u1
    - id: no027_sub_radio_voltage_upper_limit_exceed_count
      type: u1
    - id: no028_sub_radio_voltage_lower_limit_exceed_count
      type: u1
    - id: no029_sub_radio_current_upper_limit_exceed_count
      type: u1
    - id: no030_sub_radio_current_lower_limit_exceed_count
      type: u1
    - id: no031_aobc_temperature_upper_limit_exceed_count
      type: u1
    - id: no032_aobc_temperature_lower_limit_exceed_count
      type: u1
    - id: no033_aobc_voltage_upper_limit_exceed_count
      type: u1
    - id: no034_aobc_voltage_lower_limit_exceed_count
      type: u1
    - id: no035_aobc_current_upper_limit_exceed_count
      type: u1
    - id: no036_aobc_current_lower_limit_exceed_count
      type: u1
    - id: no037_mobc_temperature_upper_limit_exceed_count
      type: u1
    - id: no038_mobc_temperature_lower_limit_exceed_count
      type: u1
    - id: no039_mobc_voltage_upper_limit_exceed_count
      type: u1
    - id: no040_mobc_voltage_lower_limit_exceed_count
      type: u1
    - id: no041_mobc_current_upper_limit_exceed_count
      type: u1
    - id: no042_mobc_current_lower_limit_exceed_count
      type: u1
    - id: no043_magnetic_torque_consumption_current
      doc: ma
      type: s2
    - id: no044_reaction_wheel_consumption_current
      doc: ma
      type: s2
    - id: no045_antenna_deployment_heater_consumption_current
      doc: ma
      type: s2
    - id: no046_main_radio_consumption_current
      doc: ma
      type: s2
    - id: no047_sub_radio_consumption_current
      doc: ma
      type: s2
    - id: no048_mobc_consumption_current
      doc: ma
      type: s2
    - id: no049_cobc_consumption_current
      doc: ma
      type: s2
    - id: no050_aobc_consumption_current
      doc: ma
      type: s2
    - id: no051_5v_bus_voltage
      doc: mv
      type: s2
    - id: no052_33v_line_voltage
      type: s2
    - id: no053_bus_current
      doc: ma
      type: s2
    - id: no054_sap_z_face_voltage
      type: s2
    - id: no055_sap_z_face_temperature
      type: s2
    - id: no056_sap__z_face_voltage
      type: s2
    - id: no057_sap__z_face_temperature
      type: s2
    - id: no058_sap_y_face_voltage
      type: s2
    - id: no059_sap_y_face_temperature
      type: s2
    - id: no060_sap__x_face_voltage
      type: s2
    - id: no061_sap__x_face_temperature
      type: s2
    - id: no062_sap__y_face_voltage
      type: s2
    - id: no063_sap__y_face_temperature
      type: s2
    - id: no064_sap_z_face_current
      type: s2
    - id: no065_sap__z_face_current
      type: s2
    - id: no066_sap_y_face_current
      type: s2
    - id: no067_sap__x_face_current
      type: s2
    - id: no068_sap__y_face_current
      type: s2
    - id: no069_battery_1_output_voltage
      doc: mv
      type: s2
    - id: no070_battery_1_charging_current
      doc: ms
      type: s2
    - id: no071_battery_1_discharging_current
      doc: ma
      type: s2
    - id: no072_battery_1_temperature
      doc: mc
      type: s2
    - id: no073_battery_1_cumulative_charge
      doc: mah
      type: u4
    - id: no074_battery_1_cumulative_discharge
      doc: mah
      type: u4
    - id: no075_battery_2_output_voltage
      doc: mv
      type: s2
    - id: no076_battery_2_charging_current
      doc: ma
      type: s2
    - id: no077_battery_2_discharging_current
      doc: ma
      type: s2
    - id: no078_battery_2_temperature
      doc: mc
      type: s2
    - id: no079_battery_2_cumulative_charge
      doc: mah
      type: u4
    - id: no080_battery_2_cumulative_discharge
      doc: mah
      type: u4
    - id: no081_equipment_power_anomaly_status
      type: u1
      doc: |
        Equipment power anomaly (1=No anomaly, 0=Anomaly): 0:MOBC 1:SubRadio 2:RW 3:ANTH 4:MainRadio 5:MTQ 6:AOBC 7:res
    - id: no082_equipment_power_status
      type: u1
      doc: |
        Power status (1=ON, 0=OFF): 0:MTQ 1:TOBC1 2:RW 3:ANTDEP 4:TOBC2 5:AOBC 6:MOBC 7:res
    - id: no083_mppt_status
      type: u1
      doc: |
        MPPT disable(1)/enable(0): 0:MPPT2 1:MPPT1 4:MPPT5 5:MPPT4 6:MPPT3
    - id: no084_battery_chargedischarge_controller_status
      type: u1
      doc: |
        Battery C/D ctrl (1:Disabled,0:Enabled):
          1:BAT2 Dis 2:BAT2 Chg 3:Forced enable BAT1,2 4:BAT1 Chg 5:BAT1 Dis
          6:BAT1 Dis PGOOD(1 good) 7:BAT2 Dis PGOOD(1 good)
    - id: no085_internal_equipment_communication_error_status
      type: u1
      doc: |
        Internal comm error (1:fail,0:ok): 0:FD 1:PSW 2:MPPT 3:BATSW 4:LOAD 5:SAPtemp 6:SAP 7:BAT
    - id: no086_main_radio_boot_count
      type: u1
    - id: no087_main_radio_elapsed_time
      doc: h
      type: u1
    - id: no088_main_radio_no_reception_time
      doc: h
      type: u1
    - id: no089_main_radio_rssi
      doc: dbm
      type: s1
    - id: no090_main_radio_uplink_reception_counter
      type: u1
    - id: no091_main_radio_uplink_modulation
      type: u1
    - id: no092_main_radio_downlink_modulation
      type: u1
    - id: no093_main_radio_downlink_protocol
      type: u1
    - id: no094_main_radio_frequency_lock
      type: u1
    - id: no095_main_radio_pa_temperature
      doc: mc
      type: s1
    - id: no096_main_radio_pa_current
      doc: ma
      type: s2
    - id: no097_main_radio_mcu_temperature_
      doc: mc
      type: s1
    - id: no098_sub_radio_boot_count
      type: u1
    - id: no099_sub_radio_elapsed_time
      doc: h
      type: u1
    - id: no100_sub_radio_no_reception_time
      doc: h
      type: u1
    - id: no101_sub_radio_rssi
      doc: dbm
      type: s1
    - id: no102_sub_radio_uplink_reception_counter
      type: u1
    - id: no103_sub_radio_uplink_modulation
      type: u1
    - id: no104_sub_radio_downlink_modulation
      type: u1
    - id: no105_sub_radio_downlink_protocol
      type: u1
    - id: no106_sub_radio_frequency_lock
      type: u1
    - id: no107_sub_radio_pa_temperature
      doc: mc
      type: s1
    - id: no108_sub_radio_pa_current
      doc: ma
      type: s2
    - id: no109_sub_radio_mcu_temperature
      doc: mc
      type: s1

    instances:
      # Beacon type:
      beacon_type:
        value: '1'
      # --- No.011 flags ---
      no011_flag_0:
        value: ( no011_antenna_deployment_status        & 1) != 0
      no011_flag_1:
        value: ((no011_antenna_deployment_status >> 1) & 1) != 0
      no011_flag_2:
        value: ((no011_antenna_deployment_status >> 2) & 1) != 0
      no011_flag_3:
        value: ((no011_antenna_deployment_status >> 3) & 1) != 0
      no011_flag_4:
        value: ((no011_antenna_deployment_status >> 4) & 1) != 0
      no011_flag_5:
        value: ((no011_antenna_deployment_status >> 5) & 1) != 0
      no011_flag_6:
        value: ((no011_antenna_deployment_status >> 6) & 1) != 0
      no011_flag_7:
        value: ((no011_antenna_deployment_status >> 7) & 1) != 0
      # --- No.081 flags ---
      no081_flag_0:
        value: ( no081_equipment_power_anomaly_status & 1) != 0
      no081_flag_1:
        value: ((no081_equipment_power_anomaly_status >> 1) & 1) != 0
      no081_flag_2:
        value: ((no081_equipment_power_anomaly_status >> 2) & 1) != 0
      no081_flag_3:
        value: ((no081_equipment_power_anomaly_status >> 3) & 1) != 0
      no081_flag_4:
        value: ((no081_equipment_power_anomaly_status >> 4) & 1) != 0
      no081_flag_5:
        value: ((no081_equipment_power_anomaly_status >> 5) & 1) != 0
      no081_flag_6:
        value: ((no081_equipment_power_anomaly_status >> 6) & 1) != 0
      no081_flag_7:
        value: ((no081_equipment_power_anomaly_status >> 7) & 1) != 0
      # --- No.082 flags ---
      no082_flag_0:
        value: ( no082_equipment_power_status & 1) != 0
      no082_flag_1:
        value: ((no082_equipment_power_status >> 1) & 1) != 0
      no082_flag_2:
        value: ((no082_equipment_power_status >> 2) & 1) != 0
      no082_flag_3:
        value: ((no082_equipment_power_status >> 3) & 1) != 0
      no082_flag_4:
        value: ((no082_equipment_power_status >> 4) & 1) != 0
      no082_flag_5:
        value: ((no082_equipment_power_status >> 5) & 1) != 0
      no082_flag_6:
        value: ((no082_equipment_power_status >> 6) & 1) != 0
      no082_flag_7:
        value: ((no082_equipment_power_status >> 7) & 1) != 0
      # --- No.083 flags ---
      no083_flag_0:
        value: ( no083_mppt_status & 1) != 0
      no083_flag_1:
        value: ((no083_mppt_status >> 1) & 1) != 0
      no083_flag_2:
        value: ((no083_mppt_status >> 2) & 1) != 0
      no083_flag_3:
        value: ((no083_mppt_status >> 3) & 1) != 0
      no083_flag_4:
        value: ((no083_mppt_status >> 4) & 1) != 0
      no083_flag_5:
        value: ((no083_mppt_status >> 5) & 1) != 0
      no083_flag_6:
        value: ((no083_mppt_status >> 6) & 1) != 0
      no083_flag_7:
        value: ((no083_mppt_status >> 7) & 1) != 0
      # --- No.084 flags ---
      no084_flag_0:
        value: ( no084_battery_chargedischarge_controller_status & 1) != 0
      no084_flag_1:
        value: ((no084_battery_chargedischarge_controller_status >> 1) & 1) != 0
      no084_flag_2:
        value: ((no084_battery_chargedischarge_controller_status >> 2) & 1) != 0
      no084_flag_3:
        value: ((no084_battery_chargedischarge_controller_status >> 3) & 1) != 0
      no084_flag_4:
        value: ((no084_battery_chargedischarge_controller_status >> 4) & 1) != 0
      no084_flag_5:
        value: ((no084_battery_chargedischarge_controller_status >> 5) & 1) != 0
      no084_flag_6:
        value: ((no084_battery_chargedischarge_controller_status >> 6) & 1) != 0
      no084_flag_7:
        value: ((no084_battery_chargedischarge_controller_status >> 7) & 1) != 0
      # --- No.085 flags ---
      no085_flag_0:
        value: ( no085_internal_equipment_communication_error_status & 1) != 0
      no085_flag_1:
        value: ((no085_internal_equipment_communication_error_status >> 1) & 1) != 0
      no085_flag_2:
        value: ((no085_internal_equipment_communication_error_status >> 2) & 1) != 0
      no085_flag_3:
        value: ((no085_internal_equipment_communication_error_status >> 3) & 1) != 0
      no085_flag_4:
        value: ((no085_internal_equipment_communication_error_status >> 4) & 1) != 0
      no085_flag_5:
        value: ((no085_internal_equipment_communication_error_status >> 5) & 1) != 0
      no085_flag_6:
        value: ((no085_internal_equipment_communication_error_status >> 6) & 1) != 0
      no085_flag_7:
        value: ((no085_internal_equipment_communication_error_status >> 7) & 1) != 0

  packet2:
    seq:
    - id: no005_telemetry_id
      type: u2
    - id: no006_cobc_uptime_
      doc: sec
      type: u8
    - id: no007_satellite_system_time
      doc: ms
      type: u8
    - id: no008_mission_command_execution_result
      type: u1
      doc: enum mission_cmd_result
    - id: no009_mission_command_execution_result_details
      type: u2
      doc: enum mission_cmd_detail
    - id: no010_os_time_at_telemetry_generation
      doc: ms
      type: u8
    - id: no011_system_time_at_telemetry_generation
      doc: ms
      type: u8
    - id: no012_mobc_temperature
      doc: uc
      type: s1
    - id: no013_composition_system_status
      type: u1
      enum: composition_status
    - id: no014_stt_status
      type: u1
      enum: stt_status
    - id: no015_right_ascension_last_acquired_by_stt_f4check
      doc: deg
      type: f4
    - id: no016_declination_last_acquired_by_stt_f4check
      doc: deg
      type: f4
    - id: no017_roll_angle_last_acquired_by_stt_f4check
      doc: deg_s
      type: f4
    - id: no018_validity_of_acquired_coordinates
      type: u1
    - id: no019_image_capture_time
      doc: ms
      type: u8
    - id: no020_most_recent_command_id_1
      type: u1
    - id: no021_most_recent_command_result_1
      type: u1
      enum: mission_cmd_result
    - id: no022_most_recent_command_result_detail_1
      type: u2
      enum: mission_cmd_detail
    - id: no023_most_recent_command_id_2
      type: u1
    - id: no024_most_recent_command_result_2
      type: u1
      enum: mission_cmd_result
    - id: no025_most_recent_command_result_detail_2
      type: u2
      enum: mission_cmd_detail
    - id: no026_most_recent_command_id_3
      type: u1
    - id: no027_most_recent_command_result_3
      type: u1
      enum: mission_cmd_result
    - id: no028_most_recent_command_result_detail_3
      type: u2
      enum: mission_cmd_detail

    instances:
       no015_right_ascension_last_acquired_by_stt:
         if: no015_right_ascension_last_acquired_by_stt_f4check != 0xffffffff
         value: no015_right_ascension_last_acquired_by_stt_f4check

       no016_declination_last_acquired_by_stt:
         if: no016_declination_last_acquired_by_stt_f4check != 0xffffffff
         value: no016_declination_last_acquired_by_stt_f4check

       no017_roll_angle_last_acquired_by_stt:
         if: no017_roll_angle_last_acquired_by_stt_f4check != 0xffffffff
         value: no017_roll_angle_last_acquired_by_stt_f4check

  packet3:
    seq:
    - id: no005_telemetry_id
      type: u2
    - id: no006_cobc_uptime
      doc: sec
      type: u8
    - id: no007_satellite_system_time
      doc: ms
      type: u8
    - id: no008_telemetry_type
      type: u1
      doc: Always 0x03
    - id: no009_attitude_control_mode
      type: u1
      enum: attitude_ctrl_mode
    - id: no010_ground_packet_reception_count
      type: u2
    - id: no011_x_axis_rw_mode
      type: u1
      enum: enable_disable
    - id: no012_x_axis_rw_speed
      doc: rpm
      type: s4
    - id: no013_x_axis_rw_status
      type: u1
    - id: no014_y_axis_rw_mode
      type: u1
      enum: enable_disable
    - id: no015_y_axis_rw_speed
      doc: rpm
      type: s4
    - id: no016_y_axis_rw_status
      type: u1
    - id: no017_z_axis_rw_mode
      type: u1
      enum: enable_disable
    - id: no018_z_axis_rw_speed
      doc: rpm
      type: s4
    - id: no019_z_axis_rw_status
      type: u1
    - id: no020_x_axis_mtq_mode
      type: u1
      enum: mtq_mode
    - id: no021_x_axis_mtq_set_voltage
      doc: mv
      type: s4
    - id: no022_x_axis_mtq_status
      type: u1
    - id: no023_y_axis_mtq_mode
      type: u1
      enum: mtq_mode
    - id: no024_y_axis_mtq_set_voltage
      doc: mv
      type: s4
    - id: no025_y_axis_mtq_status
      type: u1
    - id: no026_z_axis_mtq_mode
      type: u1
      enum: mtq_mode
    - id: no027_z_axis_mtq_set_voltage
      doc: mv
      type: s4
    - id: no028_z_axis_mtq_status
      type: u1
    - id: no029_imu1_x_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no030_imu1_y_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no031_imu1_z_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no032_imu1_x_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no033_imu1_y_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no034_imu1_z_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no035_imu1_x_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no036_imu1_y_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no037_imu1_z_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no038_imu1_temperature_f4check
      doc: mc
      type: f4
    - id: no039_imu1_status
      type: u1
    - id: no040_imu2_x_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no041_imu2_y_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no042_imu2_z_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no043_imu2_x_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no044_imu2_y_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no045_imu2_z_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no046_imu2_x_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no047_imu2_y_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no048_imu2_z_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no049_imu2_temperature_f4check
      doc: mc
      type: f4
    - id: no050_imu2_status
      type: u1
    - id: no051_imu3_x_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no052_imu3_y_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no053_imu3_z_axis_acceleration_f4check
      doc: g
      type: f4
    - id: no054_imu3_x_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no055_imu3_y_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no056_imu3_z_axis_angular_velocity_f4check
      doc: mdeg/s
      type: f4
    - id: no057_imu3_x_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no058_imu3_y_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no059_imu3_z_axis_magnetic_field_f4check
      doc: ut
      type: f4
    - id: no060_imu3_temperature_f4check
      doc: mc
      type: f4
    - id: no061_imu3_status
      type: u1
    - id: no062_x_axis_rw_proportional_gain_f4check
      type: f4
    - id: no063_x_axis_rw_derivative_gain_f4check
      type: f4
    - id: no064_y_axis_rw_proportional_gain_f4check
      type: f4
    - id: no065_y_axis_rw_derivative_gain_f4check
      type: f4
    - id: no066_z_axis_rw_proportional_gain_f4check
      type: f4
    - id: no067_z_axis_rw_derivative_gain_f4check
      type: f4
    - id: no068_commissioning_runtime_
      doc: s
      type: u4
    - id: no069_imu_fault_detection_threshold_f4check
      type: f4
    - id: no070_active_imu
      type: u1
      enum: active_imu
    - id: no071_bdot_control_voltage
      doc: mv
      type: u4
    - id: no072_bdot_reference_magnetic_field_f4check
      doc: ut
      type: f4

    instances:
       no029_imu1_x_axis_acceleration:
         if: no029_imu1_x_axis_acceleration_f4check != 0xffffffff
         value: no029_imu1_x_axis_acceleration_f4check

       no030_imu1_y_axis_acceleration:
         if: no030_imu1_y_axis_acceleration_f4check != 0xffffffff
         value: no030_imu1_y_axis_acceleration_f4check

       no031_imu1_z_axis_acceleration:
         if: no031_imu1_z_axis_acceleration_f4check != 0xffffffff
         value: no031_imu1_z_axis_acceleration_f4check

       no032_imu1_x_axis_angular_velocity:
         if: no032_imu1_x_axis_angular_velocity_f4check != 0xffffffff
         value: no032_imu1_x_axis_angular_velocity_f4check

       no033_imu1_y_axis_angular_velocity:
         if: no033_imu1_y_axis_angular_velocity_f4check != 0xffffffff
         value: no033_imu1_y_axis_angular_velocity_f4check

       no034_imu1_z_axis_angular_velocity:
         if: no034_imu1_z_axis_angular_velocity_f4check != 0xffffffff
         value: no034_imu1_z_axis_angular_velocity_f4check

       no035_imu1_x_axis_magnetic_field:
         if: no035_imu1_x_axis_magnetic_field_f4check != 0xffffffff
         value: no035_imu1_x_axis_magnetic_field_f4check

       no036_imu1_y_axis_magnetic_field:
         if: no036_imu1_y_axis_magnetic_field_f4check != 0xffffffff
         value: no036_imu1_y_axis_magnetic_field_f4check

       no037_imu1_z_axis_magnetic_field:
         if: no037_imu1_z_axis_magnetic_field_f4check != 0xffffffff
         value: no037_imu1_z_axis_magnetic_field_f4check

       no038_imu1_temperature:
         if: no038_imu1_temperature_f4check != 0xffffffff
         value: no038_imu1_temperature_f4check

       no040_imu2_x_axis_acceleration:
         if: no040_imu2_x_axis_acceleration_f4check != 0xffffffff
         value: no040_imu2_x_axis_acceleration_f4check

       no041_imu2_y_axis_acceleration:
         if: no041_imu2_y_axis_acceleration_f4check != 0xffffffff
         value: no041_imu2_y_axis_acceleration_f4check

       no042_imu2_z_axis_acceleration:
         if: no042_imu2_z_axis_acceleration_f4check != 0xffffffff
         value: no042_imu2_z_axis_acceleration_f4check

       no043_imu2_x_axis_angular_velocity:
         if: no043_imu2_x_axis_angular_velocity_f4check != 0xffffffff
         value: no043_imu2_x_axis_angular_velocity_f4check

       no044_imu2_y_axis_angular_velocity:
         if: no044_imu2_y_axis_angular_velocity_f4check != 0xffffffff
         value: no044_imu2_y_axis_angular_velocity_f4check

       no045_imu2_z_axis_angular_velocity:
         if: no045_imu2_z_axis_angular_velocity_f4check != 0xffffffff
         value: no045_imu2_z_axis_angular_velocity_f4check

       no046_imu2_x_axis_magnetic_field:
         if: no046_imu2_x_axis_magnetic_field_f4check != 0xffffffff
         value: no046_imu2_x_axis_magnetic_field_f4check

       no047_imu2_y_axis_magnetic_field:
         if: no047_imu2_y_axis_magnetic_field_f4check != 0xffffffff
         value: no047_imu2_y_axis_magnetic_field_f4check

       no048_imu2_z_axis_magnetic_field:
         if: no048_imu2_z_axis_magnetic_field_f4check != 0xffffffff
         value: no048_imu2_z_axis_magnetic_field_f4check

       no049_imu2_temperature:
         if: no049_imu2_temperature_f4check != 0xffffffff
         value: no049_imu2_temperature_f4check

       no051_imu3_x_axis_acceleration:
         if: no051_imu3_x_axis_acceleration_f4check != 0xffffffff
         value: no051_imu3_x_axis_acceleration_f4check

       no052_imu3_y_axis_acceleration:
         if: no052_imu3_y_axis_acceleration_f4check != 0xffffffff
         value: no052_imu3_y_axis_acceleration_f4check

       no053_imu3_z_axis_acceleration:
         if: no053_imu3_z_axis_acceleration_f4check != 0xffffffff
         value: no053_imu3_z_axis_acceleration_f4check

       no054_imu3_x_axis_angular_velocity:
         if: no054_imu3_x_axis_angular_velocity_f4check != 0xffffffff
         value: no054_imu3_x_axis_angular_velocity_f4check

       no055_imu3_y_axis_angular_velocity:
         if: no055_imu3_y_axis_angular_velocity_f4check != 0xffffffff
         value: no055_imu3_y_axis_angular_velocity_f4check

       no056_imu3_z_axis_angular_velocity:
         if: no056_imu3_z_axis_angular_velocity_f4check != 0xffffffff
         value: no056_imu3_z_axis_angular_velocity_f4check

       no057_imu3_x_axis_magnetic_field:
         if: no057_imu3_x_axis_magnetic_field_f4check != 0xffffffff
         value: no057_imu3_x_axis_magnetic_field_f4check

       no058_imu3_y_axis_magnetic_field:
         if: no058_imu3_y_axis_magnetic_field_f4check != 0xffffffff
         value: no058_imu3_y_axis_magnetic_field_f4check

       no059_imu3_z_axis_magnetic_field:
         if: no059_imu3_z_axis_magnetic_field_f4check != 0xffffffff
         value: no059_imu3_z_axis_magnetic_field_f4check

       no060_imu3_temperature:
         if: no060_imu3_temperature_f4check != 0xffffffff
         value: no060_imu3_temperature_f4check

       no062_x_axis_rw_proportional_gain:
         if: no062_x_axis_rw_proportional_gain_f4check != 0xffffffff
         value: no062_x_axis_rw_proportional_gain_f4check

       no063_x_axis_rw_derivative_gain:
         if: no063_x_axis_rw_derivative_gain_f4check != 0xffffffff
         value: no063_x_axis_rw_derivative_gain_f4check

       no064_y_axis_rw_proportional_gain:
         if: no064_y_axis_rw_proportional_gain_f4check != 0xffffffff
         value: no064_y_axis_rw_proportional_gain_f4check

       no065_y_axis_rw_derivative_gain:
         if: no065_y_axis_rw_derivative_gain_f4check != 0xffffffff
         value: no065_y_axis_rw_derivative_gain_f4check

       no066_z_axis_rw_proportional_gain:
         if: no066_z_axis_rw_proportional_gain_f4check != 0xffffffff
         value: no066_z_axis_rw_proportional_gain_f4check

       no067_z_axis_rw_derivative_gain:
         if: no067_z_axis_rw_derivative_gain_f4check != 0xffffffff
         value: no067_z_axis_rw_derivative_gain_f4check

       no069_imu_fault_detection_threshold:
         if: no069_imu_fault_detection_threshold_f4check != 0xffffffff
         value: no069_imu_fault_detection_threshold_f4check

       no072_bdot_reference_magnetic_field:
         if: no072_bdot_reference_magnetic_field_f4check != 0xffffffff
         value: no072_bdot_reference_magnetic_field_f4check




  cw_g:
    seq:
      - id: no001_message_identifier
        type: str
        size: 1
        encoding: ASCII
        valid: '"G"'
      - id: no002_telemetry_type_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no003_cobc_boot_count_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no003_cobc_boot_count_hi_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no004_cobc_uptime_b0_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no004_cobc_uptime_b1_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no004_cobc_uptime_b2_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no004_cobc_uptime_b3_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no005_cobc_temperature_degc_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no006_satellite_operation_mode_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no007_antenna_deployment_status_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no008_uplink_reception_count_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no009_batt1_voltage_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no009_batt1_voltage_hi_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no010_battery_1_charging_current_first_half_ma_hex
        type: str
        size: 2
        encoding: ASCII

    instances:
      no002_telemetry_type_value:
        value: no002_telemetry_type_hex.to_i(16)
      # 16bit: lo + (hi<<8)
      no003_cobc_boot_count_value:
        value: no003_cobc_boot_count_lo_hex.to_i(16) + (no003_cobc_boot_count_hi_hex.to_i(16) << 8)
      # 32bit: b0 + (b1<<8) + (b2<<16) + (b3<<24)
      no004_cobc_uptime_seconds_value:
        value: no004_cobc_uptime_b0_hex.to_i(16) + (no004_cobc_uptime_b1_hex.to_i(16) << 8) + (no004_cobc_uptime_b2_hex.to_i(16) << 16) + (no004_cobc_uptime_b3_hex.to_i(16) << 24)
      no005_cobc_temperature_degc_value:
        value: no005_cobc_temperature_degc_hex.to_i(16)
      no006_satellite_operation_mode_value:
        value: no006_satellite_operation_mode_hex.to_i(16)
      no007_antenna_deployment_status_value:
        value: no007_antenna_deployment_status_hex.to_i(16)
      no008_uplink_reception_count_value:
        value: no008_uplink_reception_count_hex.to_i(16)
      # 16bit: lo + (hi<<8)
      no009_battery_1_voltage_mv_value:
        value: no009_batt1_voltage_lo_hex.to_i(16) + (no009_batt1_voltage_hi_hex.to_i(16) << 8)
      no010_battery_1_charging_current_first_half_ma_value:
        value: no010_battery_1_charging_current_first_half_ma_hex.to_i(16)
      no007_antdep_bit_pos_x: 
        value: (no007_antenna_deployment_status_value & 0x01) != 0
      no007_antdep_bit_neg_x: 
        value: (no007_antenna_deployment_status_value & 0x02) != 0
      no007_antdep_bit_pos_y: 
        value: (no007_antenna_deployment_status_value & 0x04) != 0
      no007_antdep_bit_neg_y: 
        value: (no007_antenna_deployment_status_value & 0x08) != 0

      cw_type:
        value: no001_message_identifier
      cw_beacon:
        value: no001_message_identifier + no002_telemetry_type_hex + no003_cobc_boot_count_lo_hex + no003_cobc_boot_count_hi_hex + no004_cobc_uptime_b0_hex + no004_cobc_uptime_b1_hex + no004_cobc_uptime_b2_hex + no004_cobc_uptime_b3_hex + no005_cobc_temperature_degc_hex + no006_satellite_operation_mode_hex + no007_antenna_deployment_status_hex + no008_uplink_reception_count_hex + no009_batt1_voltage_lo_hex + no009_batt1_voltage_hi_hex + no010_battery_1_charging_current_first_half_ma_hex

  cw_h:
    seq:
      - id: no001_message_identifier
        type: str
        size: 1
        encoding: ASCII
        valid: '"H"'
      - id: no002_battery_1_charging_current_second_half_ma_hex
        type: str
        size: 2
        encoding: ASCII
      # 2bytes->lo/hi
      - id: no003_batt1_discharging_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no003_batt1_discharging_hi_hex
        type: str
        size: 2
        encoding: ASCII
        
      - id: no004_battery_1_temperature_degc_hex
        type: str
        size: 2
        encoding: ASCII

      # 2bytes->lo/hi
      - id: no005_batt2_voltage_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no005_batt2_voltage_hi_hex
        type: str
        size: 2
        encoding: ASCII

      # 2bytes->lo/hi
      - id: no006_batt2_charging_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no006_batt2_charging_hi_hex
        type: str
        size: 2
        encoding: ASCII

      # 2bytes->lo/hi
      - id: no007_batt2_discharging_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no007_batt2_discharging_hi_hex
        type: str
        size: 2
        encoding: ASCII

      - id: no008_battery_2_temperature_degc_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no009_subsystem_power_fault_status_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no010_subsystem_power_onoff_status_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no011_tobc_main_boot_count_hex
        type: str
        size: 2
        encoding: ASCII

    instances:
      no002_battery_1_charging_current_second_half_ma_value:
        value: no002_battery_1_charging_current_second_half_ma_hex.to_i(16)
      no003_battery_1_discharging_current_ma_value:
        value: no003_batt1_discharging_lo_hex.to_i(16) + (no003_batt1_discharging_hi_hex.to_i(16) << 8)
      no004_battery_1_temperature_degc_value:
        value: no004_battery_1_temperature_degc_hex.to_i(16)
      no005_battery_2_voltage_mv_value:
        value: no005_batt2_voltage_lo_hex.to_i(16) + (no005_batt2_voltage_hi_hex.to_i(16) << 8)
      no006_battery_2_charging_current_ma_value:
        value: no006_batt2_charging_lo_hex.to_i(16) + (no006_batt2_charging_hi_hex.to_i(16) << 8)
      no007_battery_2_discharging_current_ma_value:
        value: no007_batt2_discharging_lo_hex.to_i(16) + (no007_batt2_discharging_hi_hex.to_i(16) << 8)
      no008_battery_2_temperature_degc_value:
        value: no008_battery_2_temperature_degc_hex.to_i(16)
      no009_subsystem_power_fault_status_value:
        value: no009_subsystem_power_fault_status_hex.to_i(16)
      no010_subsystem_power_onoff_status_value:
        value: no010_subsystem_power_onoff_status_hex.to_i(16)
      no011_tobc_main_boot_count_value:
        value: no011_tobc_main_boot_count_hex.to_i(16)

      no009_fault_ok_mobc: 
        value: (no009_subsystem_power_fault_status_value & 0x01) != 0
      no009_fault_ok_tobc_sub: 
        value: (no009_subsystem_power_fault_status_value & 0x02) != 0
      no009_fault_ok_rw: 
        value: (no009_subsystem_power_fault_status_value & 0x04) != 0
      no009_fault_ok_anth: 
        value: (no009_subsystem_power_fault_status_value & 0x08) != 0
      no009_fault_ok_tobc_main: 
        value: (no009_subsystem_power_fault_status_value & 0x10) != 0
      no009_fault_ok_mtq: 
        value: (no009_subsystem_power_fault_status_value & 0x20) != 0
      no009_fault_ok_aobc: 
        value: (no009_subsystem_power_fault_status_value & 0x40) != 0

      no010_on_mobc: 
        value: (no010_subsystem_power_onoff_status_value & 0x40) != 0
      no010_on_aobc:
        value: (no010_subsystem_power_onoff_status_value & 0x20) != 0
      no010_on_tobc_main: 
        value: (no010_subsystem_power_onoff_status_value & 0x10) != 0
      no010_on_antdep: 
        value: (no010_subsystem_power_onoff_status_value & 0x08) != 0
      no010_on_rw: 
        value: (no010_subsystem_power_onoff_status_value & 0x04) != 0
      no010_on_tobc_sub: 
        value: (no010_subsystem_power_onoff_status_value & 0x02) != 0
      no010_on_mtq: 
        value: (no010_subsystem_power_onoff_status_value & 0x01) != 0

      cw_type:
        value: no001_message_identifier
      cw_beacon:
        value: no001_message_identifier+no002_battery_1_charging_current_second_half_ma_hex + no003_batt1_discharging_lo_hex + no003_batt1_discharging_hi_hex + no004_battery_1_temperature_degc_hex + no005_batt2_voltage_lo_hex + no005_batt2_voltage_hi_hex + no006_batt2_charging_lo_hex + no006_batt2_charging_hi_hex + no007_batt2_discharging_lo_hex + no007_batt2_discharging_hi_hex + no008_battery_2_temperature_degc_hex + no009_subsystem_power_fault_status_hex + no010_subsystem_power_onoff_status_hex + no011_tobc_main_boot_count_hex
  cw_i:
    seq:
      - id: no001_message_identifier
        type: str
        size: 1
        encoding: ASCII
        valid: '"I"'
      - id: no002_main_tobc_operating_time_hour_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no003_main_tobc_reception_count_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no004_sub_tobc_boot_count_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no005_sub_tobc_operating_time_hour_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no006_sub_tobc_reception_count_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no007_aobc_operation_mode_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no008_attctrl_power_status_hex
        type: str
        size: 2
        encoding: ASCII

      # deg/s->lo/hi
      - id: no009_x_gyro_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no009_x_gyro_hi_hex
        type: str
        size: 2
        encoding: ASCII

      - id: no010_y_gyro_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no010_y_gyro_hi_hex
        type: str
        size: 2
        encoding: ASCII

      - id: no011_z_gyro_lo_hex
        type: str
        size: 2
        encoding: ASCII
      - id: no011_z_gyro_hi_hex
        type: str
        size: 2
        encoding: ASCII

      - id: no012_mobc_operation_mode_hex
        type: str
        size: 2
        encoding: ASCII

    instances:
      no002_main_tobc_operating_time_hour_value:
        value: no002_main_tobc_operating_time_hour_hex.to_i(16)
      no003_main_tobc_reception_count_value:
        value: no003_main_tobc_reception_count_hex.to_i(16)
      no004_sub_tobc_boot_count_value:
        value: no004_sub_tobc_boot_count_hex.to_i(16)
      no005_sub_tobc_operating_time_hour_value:
        value: no005_sub_tobc_operating_time_hour_hex.to_i(16)
      no006_sub_tobc_reception_count_value:
        value: no006_sub_tobc_reception_count_hex.to_i(16)
      no007_aobc_operation_mode_value:
        value: no007_aobc_operation_mode_hex.to_i(16)
        enum: aobc_operation_mode
      no008_attctrl_power_status_value:
        value: no008_attctrl_power_status_hex.to_i(16)

    # 16bitu16->s16
      no009_x_axis_angular_velocity_mdeg_s_u16:
        value: no009_x_gyro_lo_hex.to_i(16) + (no009_x_gyro_hi_hex.to_i(16) << 8)
      no009_x_axis_angular_velocity_mdeg_s_s16:
        value: '(no009_x_axis_angular_velocity_mdeg_s_u16 > 0x7FFF) ? (no009_x_axis_angular_velocity_mdeg_s_u16 - 0x10000) : no009_x_axis_angular_velocity_mdeg_s_u16'
      no010_y_axis_angular_velocity_mdeg_s_u16:
        value: no010_y_gyro_lo_hex.to_i(16) + (no010_y_gyro_hi_hex.to_i(16) << 8)
      no010_y_axis_angular_velocity_mdeg_s_s16:
        value: '(no010_y_axis_angular_velocity_mdeg_s_u16 > 0x7FFF) ? (no010_y_axis_angular_velocity_mdeg_s_u16 - 0x10000) : no010_y_axis_angular_velocity_mdeg_s_u16'
      no011_z_axis_angular_velocity_mdeg_s_u16:
        value: no011_z_gyro_lo_hex.to_i(16) + (no011_z_gyro_hi_hex.to_i(16) << 8)
      no011_z_axis_angular_velocity_mdeg_s_s16:
        value: '(no011_z_axis_angular_velocity_mdeg_s_u16 > 0x7FFF) ? (no011_z_axis_angular_velocity_mdeg_s_u16 - 0x10000) : no011_z_axis_angular_velocity_mdeg_s_u16'
      no012_mobc_operation_mode_value:
        value: no012_mobc_operation_mode_hex.to_i(16)
      no008_on_rw1:
        value: (no008_attctrl_power_status_value & 0x01) != 0
      no008_on_rw2:
        value: (no008_attctrl_power_status_value & 0x02) != 0
      no008_on_rw3:
        value: (no008_attctrl_power_status_value & 0x04) != 0
      no008_on_mtq1:
        value: (no008_attctrl_power_status_value & 0x08) != 0
      no008_on_mtq2:
        value: (no008_attctrl_power_status_value & 0x10) != 0
      no008_on_mtq3:
        value: (no008_attctrl_power_status_value & 0x20) != 0
      no012_mobc_composition_high_nibble:
        value: (no012_mobc_operation_mode_value >> 4) & 0x0F
      no012_mobc_stt_low_nibble:
        value: (no012_mobc_operation_mode_value     ) & 0x0F
      no012_composition_status:
        value: no012_mobc_composition_high_nibble
        enum: composition_status
      no012_stt_status:
        value: no012_mobc_stt_low_nibble
        enum: stt_status_cw_i
      cw_type:
        value: no001_message_identifier
      cw_beacon:
        value: no001_message_identifier + no002_main_tobc_operating_time_hour_hex + no003_main_tobc_reception_count_hex + no004_sub_tobc_boot_count_hex + no005_sub_tobc_operating_time_hour_hex + no006_sub_tobc_reception_count_hex + no007_aobc_operation_mode_hex + no008_attctrl_power_status_hex + no009_x_gyro_lo_hex+no009_x_gyro_hi_hex + no010_y_gyro_lo_hex+no010_y_gyro_hi_hex + no011_z_gyro_lo_hex+no011_z_gyro_hi_hex + no012_mobc_operation_mode_hex
