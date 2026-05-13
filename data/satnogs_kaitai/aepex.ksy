---
meta:
  id: aepex
  title: AEPEX 70cm Beacon Packet Struct
  endian: be
doc: |
  :field dest_callsign: ax25_frame.ax25_header.dest_callsign_raw.callsign_ror.callsign
  :field src_callsign: ax25_frame.ax25_header.src_callsign_raw.callsign_ror.callsign
  :field src_ssid: ax25_frame.ax25_header.src_ssid_raw.ssid
  :field dest_ssid: ax25_frame.ax25_header.dest_ssid_raw.ssid
  :field ctl: ax25_frame.ax25_header.ctl
  :field pid: ax25_frame.payload.pid
  :field ccsds_version: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.ccsds_version
  :field packet_type: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.packet_type
  :field secondary_header_flag: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.secondary_header_flag
  :field is_stored_data: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.is_stored_data
  :field application_process_id: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.application_process_id
  :field grouping_flag: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.grouping_flag
  :field sequence_count: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.sequence_count
  :field packet_length: ax25_frame.payload.ax25_info.ccsds_space_packet.packet_primary_header.packet_length
  :field time_stamp_seconds: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.secondary_header.time_stamp_seconds
  :field sub_seconds: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.secondary_header.sub_seconds
  :field padding: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.secondary_header.padding
  :field sw_cmd_recv_count: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_recv_count
  :field sw_cmd_fmt_count: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_fmt_count
  :field sw_cmd_rjct_count: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_rjct_count
  :field sw_cmd_succ_count: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_succ_count
  :field padding1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.padding1
  :field padding2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.padding2
  :field sw_cmd_fail_code: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_fail_code
  :field sw_cmd_xsum_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_xsum_state
  :field reusable_spare_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_1
  :field reusable_spare_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_2
  :field reusable_spare_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_3
  :field reusable_spare_4: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_4
  :field reusable_spare_5: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_5
  :field sw_cmd_arm_state_uhf: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_arm_state_uhf
  :field sw_cmd_arm_state_seq: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_arm_state_seq
  :field sw_cmd_arm_state_dbg: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_cmd_arm_state_dbg
  :field reusable_spare_6: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_6
  :field sw_eps_pwr_state_inst4: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_eps_pwr_state_inst4
  :field sw_eps_pwr_state_inst3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_eps_pwr_state_inst3
  :field sw_eps_pwr_state_inst2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_eps_pwr_state_inst2
  :field sw_eps_pwr_state_inst1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_eps_pwr_state_inst1
  :field sw_eps_pwr_state_sband: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_eps_pwr_state_sband
  :field sw_eps_pwr_state_uhf: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_eps_pwr_state_uhf
  :field sw_eps_pwr_state_adcs: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_eps_pwr_state_adcs
  :field sw_time_since_rx: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_time_since_rx
  :field reusable_spare_7: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_7
  :field reusable_spare_8: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_8
  :field reusable_spare_9: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_9
  :field reusable_spare_10: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_10
  :field reusable_spare_11: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_11
  :field reusable_spare_12: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_12
  :field reusable_spare_13: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_13
  :field sw_bat_alive_state_battery0: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_bat_alive_state_battery0
  :field sw_mode_clt_count: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_mode_clt_count
  :field sw_mode_system_mode: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_mode_system_mode
  :field reusable_spare_14: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_14
  :field sw_sband_pa_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_sband_pa_temp
  :field sw_sband_pa_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_sband_pa_curr
  :field reusable_spare_15: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_15
  :field sw_uhf_alive: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_uhf_alive
  :field sw_uhf_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_uhf_temp
  :field reusable_spare_16: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_16
  :field sw_seq_state_auto: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_state_auto
  :field sw_seq_state_op1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_state_op1
  :field sw_seq_state_op2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_state_op2
  :field sw_seq_state_op3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_state_op3
  :field sw_seq_stop_code_auto: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_stop_code_auto
  :field sw_seq_stop_code_op1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_stop_code_op1
  :field sw_seq_stop_code_op2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_stop_code_op2
  :field sw_seq_stop_code_op3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_stop_code_op3
  :field sw_seq_exec_buf_auto: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_exec_buf_auto
  :field sw_seq_exec_buf_op1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_exec_buf_op1
  :field sw_seq_exec_buf_op2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_exec_buf_op2
  :field sw_seq_exec_buf_op3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_seq_exec_buf_op3
  :field sw_store_partition_write_misc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_write_misc
  :field sw_store_partition_read_misc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_read_misc
  :field sw_store_partition_write_adcs: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_write_adcs
  :field sw_store_partition_read_adcs: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_read_adcs
  :field sw_store_partition_write_beacon: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_write_beacon
  :field sw_store_partition_read_beacon: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_read_beacon
  :field sw_store_partition_write_log: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_write_log
  :field sw_store_partition_read_log: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_read_log
  :field sw_store_partition_write_sci: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_write_sci
  :field sw_store_partition_read_sci: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_store_partition_read_sci
  :field sw_fp_resp_count: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_fp_resp_count
  :field sw_ana_bus_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_bus_v
  :field sw_ana_3p3_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_3p3_v
  :field sw_ana_2p5_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_2p5_v
  :field sw_ana_1p8_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_1p8_v
  :field sw_ana_1p0_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_1p0_v
  :field sw_ana_3p3_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_3p3_i
  :field sw_ana_1p8_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_1p8_i
  :field sw_ana_1p0_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_1p0_i
  :field sw_ana_cdh_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_cdh_temp
  :field sw_ana_cdh_3p3_ref: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_cdh_3p3_ref
  :field sw_ana_sa1_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_sa1_v
  :field sw_ana_sa1_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_sa1_i
  :field sw_ana_sa2_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_sa2_v
  :field sw_ana_sa2_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_sa2_i
  :field sw_ana_bat1_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_bat1_v
  :field sw_ana_eps_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_eps_temp
  :field sw_ana_eps_3p3_ref: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_eps_3p3_ref
  :field sw_ana_eps_bus_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_eps_bus_v
  :field sw_ana_eps_bus_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_eps_bus_i
  :field sw_ana_xact_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_xact_v
  :field sw_ana_xact_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_xact_i
  :field sw_ana_uhf_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_uhf_v
  :field sw_ana_uhf_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_uhf_i
  :field sw_ana_sband_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_sband_v
  :field sw_ana_sband_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_sband_i
  :field sw_ana_axis1_volt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_axis1_volt
  :field sw_ana_axis1_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_axis1_curr
  :field sw_ana_axis2_volt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_axis2_volt
  :field sw_ana_axis2_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_axis2_curr
  :field sw_ana_axis3_volt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_axis3_volt
  :field sw_ana_axis3_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_axis3_curr
  :field sw_ana_afire_volt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_afire_volt
  :field sw_ana_afire_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_afire_curr
  :field sw_ana_ifb_therm1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_ana_ifb_therm1
  :field sw_adcs_alive: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_alive
  :field sw_adcs_eclipse: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_eclipse
  :field sw_adcs_att_valid: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_att_valid
  :field sw_adcs_ref_valid: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_ref_valid
  :field sw_adcs_time_valid: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_time_valid
  :field sw_adcs_mode: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_mode
  :field sw_adcs_recommend_sun_point: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_recommend_sun_point
  :field sw_adcs_sun_point_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_sun_point_state
  :field reusable_spare_17: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_17
  :field sw_adcs_analogs_voltage_2p5: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_voltage_2p5
  :field sw_adcs_analogs_voltage_1p8: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_voltage_1p8
  :field sw_adcs_analogs_voltage_1p0: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_voltage_1p0
  :field sw_adcs_analogs_det_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_det_temp
  :field sw_adcs_analogs_motor1_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_motor1_temp
  :field sw_adcs_analogs_motor2_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_motor2_temp
  :field sw_adcs_analogs_motor3_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_motor3_temp
  :field sw_adcs_analogs_digital_bus_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_analogs_digital_bus_v
  :field sw_adcs_cmd_acpt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_cmd_acpt
  :field sw_adcs_cmd_fail: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_cmd_fail
  :field sw_adcs_sun_vec1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_sun_vec1
  :field sw_adcs_sun_vec2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_sun_vec2
  :field sw_adcs_sun_vec3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_sun_vec3
  :field sw_adcs_wheel_sp1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_wheel_sp1
  :field sw_adcs_wheel_sp2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_wheel_sp2
  :field sw_adcs_wheel_sp3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_wheel_sp3
  :field sw_adcs_body_rt1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_body_rt1
  :field sw_adcs_body_rt2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_body_rt2
  :field sw_adcs_body_rt3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_body_rt3
  :field sw_adcs_body_quat1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_body_quat1
  :field sw_adcs_body_quat2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_body_quat2
  :field sw_adcs_body_quat3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_body_quat3
  :field sw_adcs_body_quat4: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_adcs_body_quat4
  :field des_met_time_seconds: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..des_met_time_seconds
  :field sw_im_id: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..sw_im_id
  :field payload_alive_axis1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..payload_alive_axis1
  :field payload_alive_axis2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..payload_alive_axis2
  :field payload_alive_axis3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..payload_alive_axis3
  :field payload_alive_afire: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..payload_alive_afire
  :field reusable_spare_18: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_18
  :field reusable_spare_18: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_19
  :field reusable_spare_18: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..reusable_spare_20
  :field reusable_spare_18: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field..checksum

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
      - id: ctl
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
            - '"APX   "'
            - '"LASP  "'
  ssid_mask:
    seq:
      - id: ssid_mask
        type: u1
    instances:
      ssid:
        value: (ssid_mask & 0x0f) >> 1
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
      - id: ccsds_space_packet
        type: ccsds_space_packet_t
  ccsds_space_packet_t:
    seq:
      - id: packet_primary_header
        type: packet_primary_header_t
        size: 6
      - id: data_section
        type: data_section_t

  packet_primary_header_t:
    seq:
      - id: ccsds_version
        type: b3
      - id: packet_type
        type: b1
      - id: secondary_header_flag
        type: b1
      - id: is_stored_data
        type: b1
      - id: application_process_id
        type: b10
      - id: grouping_flag
        type: b2
      - id: sequence_count
        type: b14
      - id: packet_length
        type: u2
  data_section_t:
    seq:
      - id: secondary_header
        type: secondary_header_t
        size: 6
        if: _parent.packet_primary_header.secondary_header_flag
      - id: user_data_field
        type:
          switch-on: _parent.packet_primary_header.application_process_id
          cases:
            0x01: aepex_sw_stat
  secondary_header_t:
    doc: |
      The Secondary Header is a feature of the Space Packet which allows
      additional types of information that may be useful to the user
      application (e.g., a time code) to be included.
      See: 4.1.3.2 in CCSDS 133.0-B-1
    seq:
      - id: time_stamp_seconds
        type: u4
      - id: sub_seconds
        type: u2
  sw_stat_t:
    seq:
      - id: sw_cmd_recv_count
        type: u2
        doc: |
          Number of received commands
      - id: sw_cmd_fmt_count
        type: u2
        doc: |
          Number of bad format commands
      - id: sw_cmd_rjct_count
        type: u2
        doc: |
          Number of received commands
      - id: sw_cmd_succ_count
        type: u2
        doc: |
          Number of successful commands
      - id: padding1
        type: u2
      - id: padding2
        type: u2
      - id: sw_cmd_fail_code
        type: u1
        doc: |
          Command failure code
          Enumeration values: 0/SUCCESS 1/MODE 2/ARM 3/SOURCE 4/OPCODE 5/METHOD
          6/LENGTH 7/RANGE 8/CHECKSUM 9/PKT_TYPE
      - id: sw_cmd_xsum_state
        type: u1
        doc: |
          Checksum checking state
          Enumeration values: 0/DIS 1/ENA
      - id: reusable_spare_1
        type: b1
      - id: reusable_spare_2
        type: b1
      - id: reusable_spare_3
        type: b1
      - id: reusable_spare_4
        type: b1
      - id: reusable_spare_5
        type: b1
      - id: sw_cmd_arm_state_uhf
        type: b1
        doc: |
          Command arm state uhf
          Enumeration values: 0/OFF 1/ARMED
      - id: sw_cmd_arm_state_seq
        type: b1
        doc: |
          Command arm state seq
          Enumeration values: 0/OFF 1/ARMED
      - id: sw_cmd_arm_state_dbg
        type: b1
        doc: |
          Command arm state dbg
          Enumeration values: 0/OFF 1/ARMED
      - id: reusable_spare_6
        type: b1
      - id: sw_eps_pwr_state_inst4
        type: b1
        doc: |
          Power States inst4
          Enumeration values: 0/OFF 1/ON
      - id: sw_eps_pwr_state_inst3
        type: b1
        doc: |
          Power States inst3
          Enumeration values: 0/OFF 1/ON
      - id: sw_eps_pwr_state_inst2
        type: b1
        doc: |
          Power States inst2
          Enumeration values: 0/OFF 1/ON
      - id: sw_eps_pwr_state_inst1
        type: b1
        doc: |
          Power States inst1
          Enumeration values: 0/OFF 1/ON
      - id: sw_eps_pwr_state_sband
        type: b1
        doc: |
          Power States sband
          Enumeration values: 0/OFF 1/ON
      - id: sw_eps_pwr_state_uhf
        type: b1
        doc: |
          Power States uhf
          Enumeration values: 0/OFF 1/ON
      - id: sw_eps_pwr_state_adcs
        type: b1
        doc: |
          Power States adcs
          Enumeration values: 0/OFF 1/ON
      - id: sw_time_since_rx
        type: u4
        doc: |
          Time since last packet received
      - id: reusable_spare_7
        type: b1
      - id: reusable_spare_8
        type: b1
      - id: reusable_spare_9
        type: b1
      - id: reusable_spare_10
        type: b1
      - id: reusable_spare_11
        type: b1
      - id: reusable_spare_12
        type: b1
      - id: reusable_spare_13
        type: b1
      - id: sw_bat_alive_state_battery0
        type: b1
        doc: |
          Battery State battery0
          Enumeration values: 0/DEAD 1/ALIVE
      - id: sw_mode_clt_count
        type: u1
        doc: |
          CLT Count
      - id: sw_mode_system_mode
        type: u1
        doc: |
          System mode
          Enumeration values: 0/PHOENIX 1/SAFE 2/NOMINAL
      - id: reusable_spare_14
        type: u1
      - id: sw_sband_pa_temp
        type: u2
        doc: |
          SBAND Power Amplifier Temp
          Conversion coefficients: c0=-5.000000e+01 c1=7.324219e-02
          Eng. units: Celsius (C)
      - id: sw_sband_pa_curr
        type: u2
        doc: |
          SBAND Power Amplifier current
          Conversion coefficients: c0=0.000000e+00 c1=4.000000e-05
          Eng. units: Amps (a)
      - id: reusable_spare_15
        type: u1
      - id: sw_uhf_alive
        type: u1
        doc: |
          Indicates good communication with UHF
      - id: sw_uhf_temp
        type: s1
        doc: |
          UHF Temperature
          Conversion coefficients: c0=0.0e+00 c1=2.0e+00
      - id: reusable_spare_16
        type: u1
      - id: sw_seq_state_auto
        type: u1
        doc: |
          State of the engines auto
          Enumeration values: 0/IDLE 1/ACTIVE 2/SUSPEND 3/PAUSE 4/STALE
      - id: sw_seq_state_op1
        type: u1
        doc: |
          State of the engines op1
          Enumeration values: 0/IDLE 1/ACTIVE 2/SUSPEND 3/PAUSE 4/STALE
      - id: sw_seq_state_op2
        type: u1
        doc: |
          State of the engines op2
          Enumeration values: 0/IDLE 1/ACTIVE 2/SUSPEND 3/PAUSE 4/STALE
      - id: sw_seq_state_op3
        type: u1
        doc: |
          State of the engines op3
          Enumeration values: 0/IDLE 1/ACTIVE 2/SUSPEND 3/PAUSE 4/STALE
      - id: sw_seq_stop_code_auto
        type: u1
        doc: |
          Reason for last termination auto
          Enumeration values: 0/NOMINAL 1/CMD 2/INIT 3/REJECT 4/STALE 5/BAD_INT
          6/INT_FAIL
      - id: sw_seq_stop_code_op1
        type: u1
        doc: |
          Reason for last termination op1
          Enumeration values: 0/NOMINAL 1/CMD 2/INIT 3/REJECT 4/STALE 5/BAD_INT
          6/INT_FAIL
      - id: sw_seq_stop_code_op2
        type: u1
        doc: |
          Reason for last termination op2
          Enumeration values: 0/NOMINAL 1/CMD 2/INIT 3/REJECT 4/STALE 5/BAD_INT
          6/INT_FAIL
      - id: sw_seq_stop_code_op3
        type: u1
        doc: |
          Reason for last termination op3
          Enumeration values: 0/NOMINAL 1/CMD 2/INIT 3/REJECT 4/STALE 5/BAD_INT
          6/INT_FAIL
      - id: sw_seq_exec_buf_auto
        type: u2
        doc: |
          Buffer ID of Top level sequence auto
          Enumeration values: 0/NVM_SMALL0 1/NVM_SMALL1 2/NVM_SMALL2
          3/NVM_SMALL3 4/NVM_SMALL4 5/NVM_SMALL5 6/NVM_SMALL6 7/NVM_SMALL7
          8/NVM_SMALL8 9/NVM_SMALL9 10/NVM_SMALL10 11/NVM_SMALL11
          12/NVM_SMALL12 13/NVM_SMALL13 14/NVM_SMALL14 15/NVM_SMALL15
          16/NVM_SMALL16 17/NVM_SMALL17 18/NVM_SMALL18 19/NVM_SMALL19
          20/NVM_SMALL20 21/NVM_SMALL21 22/NVM_SMALL22 23/NVM_SMALL23
          24/NVM_SMALL24 25/NVM_SMALL25 26/NVM_SMALL26 27/NVM_SMALL27
          28/NVM_SMALL28 29/NVM_SMALL29 30/NVM_SMALL30 31/NVM_SMALL31
          32/NVM_SMALL32 33/NVM_SMALL33 34/NVM_SMALL34 35/NVM_SMALL35
          36/NVM_SMALL36 37/NVM_SMALL37 38/NVM_SMALL38 39/NVM_SMALL39
          40/NVM_SMALL40 41/NVM_SMALL41 42/NVM_SMALL42 43/NVM_SMALL43
          44/NVM_SMALL44 45/NVM_SMALL45 46/NVM_SMALL46 47/NVM_SMALL47
          48/NVM_SMALL48 49/NVM_SMALL49 50/NVM_SMALL50 51/NVM_SMALL51
          52/NVM_SMALL52 53/NVM_SMALL53 54/NVM_SMALL54 55/NVM_SMALL55
          56/NVM_SMALL56 57/NVM_SMALL57 58/NVM_SMALL58 59/NVM_SMALL59
          60/NVM_SMALL60 61/NVM_SMALL61 62/NVM_SMALL62 63/NVM_SMALL63
          64/NVM_SMALL64 65/NVM_SMALL65 66/NVM_SMALL66 67/NVM_SMALL67
          68/NVM_SMALL68 69/NVM_SMALL69 70/NVM_SMALL70 71/NVM_SMALL71
          72/NVM_SMALL72 73/NVM_SMALL73 74/NVM_SMALL74 75/NVM_SMALL75
          76/NVM_SMALL76 77/NVM_SMALL77 78/NVM_SMALL78 79/NVM_SMALL79
          80/NVM_LARGE0 81/NVM_LARGE1 82/HOLDING0
      - id: sw_seq_exec_buf_op1
        type: u2
        doc: |
          Buffer ID of Top level sequence op1
          Enumeration values: 0/NVM_SMALL0 1/NVM_SMALL1 2/NVM_SMALL2
          3/NVM_SMALL3 4/NVM_SMALL4 5/NVM_SMALL5 6/NVM_SMALL6 7/NVM_SMALL7
          8/NVM_SMALL8 9/NVM_SMALL9 10/NVM_SMALL10 11/NVM_SMALL11
          12/NVM_SMALL12 13/NVM_SMALL13 14/NVM_SMALL14 15/NVM_SMALL15
          16/NVM_SMALL16 17/NVM_SMALL17 18/NVM_SMALL18 19/NVM_SMALL19
          20/NVM_SMALL20 21/NVM_SMALL21 22/NVM_SMALL22 23/NVM_SMALL23
          24/NVM_SMALL24 25/NVM_SMALL25 26/NVM_SMALL26 27/NVM_SMALL27
          28/NVM_SMALL28 29/NVM_SMALL29 30/NVM_SMALL30 31/NVM_SMALL31
          32/NVM_SMALL32 33/NVM_SMALL33 34/NVM_SMALL34 35/NVM_SMALL35
          36/NVM_SMALL36 37/NVM_SMALL37 38/NVM_SMALL38 39/NVM_SMALL39
          40/NVM_SMALL40 41/NVM_SMALL41 42/NVM_SMALL42 43/NVM_SMALL43
          44/NVM_SMALL44 45/NVM_SMALL45 46/NVM_SMALL46 47/NVM_SMALL47
          48/NVM_SMALL48 49/NVM_SMALL49 50/NVM_SMALL50 51/NVM_SMALL51
          52/NVM_SMALL52 53/NVM_SMALL53 54/NVM_SMALL54 55/NVM_SMALL55
          56/NVM_SMALL56 57/NVM_SMALL57 58/NVM_SMALL58 59/NVM_SMALL59
          60/NVM_SMALL60 61/NVM_SMALL61 62/NVM_SMALL62 63/NVM_SMALL63
          64/NVM_SMALL64 65/NVM_SMALL65 66/NVM_SMALL66 67/NVM_SMALL67
          68/NVM_SMALL68 69/NVM_SMALL69 70/NVM_SMALL70 71/NVM_SMALL71
          72/NVM_SMALL72 73/NVM_SMALL73 74/NVM_SMALL74 75/NVM_SMALL75
          76/NVM_SMALL76 77/NVM_SMALL77 78/NVM_SMALL78 79/NVM_SMALL79
          80/NVM_LARGE0 81/NVM_LARGE1 82/HOLDING0
      - id: sw_seq_exec_buf_op2
        type: u2
        doc: |
          Buffer ID of Top level sequence op2
          Enumeration values: 0/NVM_SMALL0 1/NVM_SMALL1 2/NVM_SMALL2
          3/NVM_SMALL3 4/NVM_SMALL4 5/NVM_SMALL5 6/NVM_SMALL6 7/NVM_SMALL7
          8/NVM_SMALL8 9/NVM_SMALL9 10/NVM_SMALL10 11/NVM_SMALL11
          12/NVM_SMALL12 13/NVM_SMALL13 14/NVM_SMALL14 15/NVM_SMALL15
          16/NVM_SMALL16 17/NVM_SMALL17 18/NVM_SMALL18 19/NVM_SMALL19
          20/NVM_SMALL20 21/NVM_SMALL21 22/NVM_SMALL22 23/NVM_SMALL23
          24/NVM_SMALL24 25/NVM_SMALL25 26/NVM_SMALL26 27/NVM_SMALL27
          28/NVM_SMALL28 29/NVM_SMALL29 30/NVM_SMALL30 31/NVM_SMALL31
          32/NVM_SMALL32 33/NVM_SMALL33 34/NVM_SMALL34 35/NVM_SMALL35
          36/NVM_SMALL36 37/NVM_SMALL37 38/NVM_SMALL38 39/NVM_SMALL39
          40/NVM_SMALL40 41/NVM_SMALL41 42/NVM_SMALL42 43/NVM_SMALL43
          44/NVM_SMALL44 45/NVM_SMALL45 46/NVM_SMALL46 47/NVM_SMALL47
          48/NVM_SMALL48 49/NVM_SMALL49 50/NVM_SMALL50 51/NVM_SMALL51
          52/NVM_SMALL52 53/NVM_SMALL53 54/NVM_SMALL54 55/NVM_SMALL55
          56/NVM_SMALL56 57/NVM_SMALL57 58/NVM_SMALL58 59/NVM_SMALL59
          60/NVM_SMALL60 61/NVM_SMALL61 62/NVM_SMALL62 63/NVM_SMALL63
          64/NVM_SMALL64 65/NVM_SMALL65 66/NVM_SMALL66 67/NVM_SMALL67
          68/NVM_SMALL68 69/NVM_SMALL69 70/NVM_SMALL70 71/NVM_SMALL71
          72/NVM_SMALL72 73/NVM_SMALL73 74/NVM_SMALL74 75/NVM_SMALL75
          76/NVM_SMALL76 77/NVM_SMALL77 78/NVM_SMALL78 79/NVM_SMALL79
          80/NVM_LARGE0 81/NVM_LARGE1 82/HOLDING0
      - id: sw_seq_exec_buf_op3
        type: u2
        doc: |
          Buffer ID of Top level sequence op3
          Enumeration values: 0/NVM_SMALL0 1/NVM_SMALL1 2/NVM_SMALL2
          3/NVM_SMALL3 4/NVM_SMALL4 5/NVM_SMALL5 6/NVM_SMALL6 7/NVM_SMALL7
          8/NVM_SMALL8 9/NVM_SMALL9 10/NVM_SMALL10 11/NVM_SMALL11
          12/NVM_SMALL12 13/NVM_SMALL13 14/NVM_SMALL14 15/NVM_SMALL15
          16/NVM_SMALL16 17/NVM_SMALL17 18/NVM_SMALL18 19/NVM_SMALL19
          20/NVM_SMALL20 21/NVM_SMALL21 22/NVM_SMALL22 23/NVM_SMALL23
          24/NVM_SMALL24 25/NVM_SMALL25 26/NVM_SMALL26 27/NVM_SMALL27
          28/NVM_SMALL28 29/NVM_SMALL29 30/NVM_SMALL30 31/NVM_SMALL31
          32/NVM_SMALL32 33/NVM_SMALL33 34/NVM_SMALL34 35/NVM_SMALL35
          36/NVM_SMALL36 37/NVM_SMALL37 38/NVM_SMALL38 39/NVM_SMALL39
          40/NVM_SMALL40 41/NVM_SMALL41 42/NVM_SMALL42 43/NVM_SMALL43
          44/NVM_SMALL44 45/NVM_SMALL45 46/NVM_SMALL46 47/NVM_SMALL47
          48/NVM_SMALL48 49/NVM_SMALL49 50/NVM_SMALL50 51/NVM_SMALL51
          52/NVM_SMALL52 53/NVM_SMALL53 54/NVM_SMALL54 55/NVM_SMALL55
          56/NVM_SMALL56 57/NVM_SMALL57 58/NVM_SMALL58 59/NVM_SMALL59
          60/NVM_SMALL60 61/NVM_SMALL61 62/NVM_SMALL62 63/NVM_SMALL63
          64/NVM_SMALL64 65/NVM_SMALL65 66/NVM_SMALL66 67/NVM_SMALL67
          68/NVM_SMALL68 69/NVM_SMALL69 70/NVM_SMALL70 71/NVM_SMALL71
          72/NVM_SMALL72 73/NVM_SMALL73 74/NVM_SMALL74 75/NVM_SMALL75
          76/NVM_SMALL76 77/NVM_SMALL77 78/NVM_SMALL78 79/NVM_SMALL79
          80/NVM_LARGE0 81/NVM_LARGE1 82/HOLDING0
      - id: sw_store_partition_write_misc
        type: u4
        doc: |
          Partition write address
      - id: sw_store_partition_read_misc
        type: u4
        doc: |
          Partition read address
      - id: sw_store_partition_write_adcs
        type: u4
        doc: |
          Partition write address
      - id: sw_store_partition_read_adcs
        type: u4
        doc: |
          Partition read address
      - id: sw_store_partition_write_beacon
        type: u4
        doc: |
          Partition write address
      - id: sw_store_partition_read_beacon
        type: u4
        doc: |
          Partition read address
      - id: sw_store_partition_write_log
        type: u4
        doc: |
          Partition write address
      - id: sw_store_partition_read_log
        type: u4
        doc: |
          Partition read address
      - id: sw_store_partition_write_sci
        type: u4
        doc: |
          Partition write address
      - id: sw_store_partition_read_sci
        type: u4
        doc: |
          Partition read address
      - id: sw_fp_resp_count
        type: u2
        doc: |
          FP Response Count
      - id: sw_ana_bus_v
        type: u2
        doc: |
          Bus Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.862300e-03
          Eng. units: Volts (v)
      - id: sw_ana_3p3_v
        type: u2
        doc: |
          3p3 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=1.611300e-03
          Eng. units: Volts (v)
      - id: sw_ana_2p5_v
        type: u2
        doc: |
          2p5 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.056600e-04
          Eng. units: Volts (v)
      - id: sw_ana_1p8_v
        type: u2
        doc: |
          1p8 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.056600e-04
          Eng. units: Volts (v)
      - id: sw_ana_1p0_v
        type: u2
        doc: |
          1p0 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.056600e-04
          Eng. units: Volts (v)
      - id: sw_ana_3p3_i
        type: u2
        doc: |
          3p3 Current
          Conversion coefficients: c0=0.000000e+00 c1=8.056600e-05
          Eng. units: Amps (a)
      - id: sw_ana_1p8_i
        type: u2
        doc: |
          1p8 Current
          Conversion coefficients: c0=0.000000e+00 c1=8.056600e-05
          Eng. units: Amps (a)
      - id: sw_ana_1p0_i
        type: u2
        doc: |
          1p0 Current
          Conversion coefficients: c0=0.000000e+00 c1=8.056600e-05
          Eng. units: Amps (a)
      - id: sw_ana_cdh_temp
        type: u2
        doc: |
          CDH Temperature
          Conversion coefficients: c0=1.255500e+02 c1=-1.362200e-01
          c2=9.861100e-05 c3=-4.417600e-08 c4=1.012500e-11 c5=-9.390500e-16
          Eng. units: Celsius (C)
      - id: sw_ana_cdh_3p3_ref
        type: u2
        doc: |
          CDH 3.3 RefV
          Conversion coefficients: c0=0.000000e+00 c1=1.611300e-03
          Eng. units: Volts (v)
      - id: sw_ana_sa1_v
        type: u2
        doc: |
          Solar Array 1 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=9.659200e-03
          Eng. units: Volts (v)
      - id: sw_ana_sa1_i
        type: u2
        doc: |
          Solar Array 1 Current
          Conversion coefficients: c0=0.000000e+00 c1=2.014200e-03
          Eng. units: Amps (a)
      - id: sw_ana_sa2_v
        type: u2
        doc: |
          Solar Array 2 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=9.659200e-03
          Eng. units: Volts (v)
      - id: sw_ana_sa2_i
        type: u2
        doc: |
          Solar Array 2 Current
          Conversion coefficients: c0=0.000000e+00 c1=2.014200e-03
          Eng. units: Amps (a)
      - id: sw_ana_bat1_v
        type: u2
        doc: |
          Battery 1 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.862300e-03
          Eng. units: Volts (v)
      - id: sw_ana_eps_temp
        type: u2
        doc: |
          EPS Board Temperature
          Conversion coefficients: c0=1.255500e+02 c1=-1.362200e-01
          c2=9.861100e-05 c3=-4.417600e-08 c4=1.012500e-11 c5=-9.390500e-16
          Eng. units: Celsius (C)
      - id: sw_ana_eps_3p3_ref
        type: u2
        doc: |
          EPS Board 3.3V Ref
          Conversion coefficients: c0=0.000000e+00 c1=1.611300e-03
          Eng. units: Volts (v)
      - id: sw_ana_eps_bus_v
        type: u2
        doc: |
          EPS Bus Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.862300e-03
          Eng. units: Volts (v)
      - id: sw_ana_eps_bus_i
        type: u2
        doc: |
          EPS Bus Current
          Conversion coefficients: c0=0.000000e+00 c1=1.220700e-03
          Eng. units: Amps (a)
      - id: sw_ana_xact_v
        type: u2
        doc: |
          XACT Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.862300e-03
          Eng. units: Volts (v)
      - id: sw_ana_xact_i
        type: u2
        doc: |
          XACT Current
          Conversion coefficients: c0=0.000000e+00 c1=2.014200e-03
          Eng. units: Amps (a)
      - id: sw_ana_uhf_v
        type: u2
        doc: |
          UHF Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.862300e-03
          Eng. units: Volts (v)
      - id: sw_ana_uhf_i
        type: u2
        doc: |
          UHF Current
          Conversion coefficients: c0=0.000000e+00 c1=2.014200e-03
          Eng. units: Amps (a)
      - id: sw_ana_sband_v
        type: u2
        doc: |
          SBAND Voltage
          Conversion coefficients: c0=0.000000e+00 c1=8.862300e-03
          Eng. units: Volts (v)
      - id: sw_ana_sband_i
        type: u2
        doc: |
          SBAND Current
          Conversion coefficients: c0=0.000000e+00 c1=2.014200e-03
          Eng. units: Amps (a)
      - id: sw_ana_axis1_volt
        type: u2
        doc: |
          AXIS1 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=3.963900e-03
          Eng. units: Volts (v)
      - id: sw_ana_axis1_curr
        type: u2
        doc: |
          AXIS1 Current
          Conversion coefficients: c0=0.000000e+00 c1=1.220700e-03
          Eng. units: Amps (a)
      - id: sw_ana_axis2_volt
        type: u2
        doc: |
          AXIS2 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=3.963900e-03
          Eng. units: Volts (v)
      - id: sw_ana_axis2_curr
        type: u2
        doc: |
          AXIS2 Current
          Conversion coefficients: c0=0.000000e+00 c1=1.220700e-03
          Eng. units: Amps (a)
      - id: sw_ana_axis3_volt
        type: u2
        doc: |
          AXIS3 Voltage
          Conversion coefficients: c0=0.000000e+00 c1=3.963900e-03
          Eng. units: Volts (v)
      - id: sw_ana_axis3_curr
        type: u2
        doc: |
          AXIS3 Current
          Conversion coefficients: c0=0.000000e+00 c1=1.220700e-03
          Eng. units: Amps (a)
      - id: sw_ana_afire_volt
        type: u2
        doc: |
          AFIRE Voltage
          Conversion coefficients: c0=0.000000e+00 c1=3.963900e-03
          Eng. units: Volts (v)
      - id: sw_ana_afire_curr
        type: u2
        doc: |
          AFIRE Current
          Conversion coefficients: c0=0.000000e+00 c1=1.220700e-03
          Eng. units: Amps (a)
      - id: sw_ana_ifb_therm1
        type: u2
        doc: |
          Interface Board Temperature
          Conversion coefficients: c0=1.255500e+02 c1=-1.362200e-01
          c2=9.861100e-05 c3=-4.417600e-08 c4=1.012500e-11 c5=-9.390500e-16
          Eng. units: Celsius (C)
      - id: sw_adcs_alive
        type: u1
        doc: |
          Alive state of communication
          Enumeration values: 0/OFF 1/DEAD 2/ALIVE
      - id: sw_adcs_eclipse
        type: u1
        doc: |
          State of eclipse
      - id: sw_adcs_att_valid
        type: b1
        doc: |
          Attitude Valid
          Enumeration values: 0/NO 1/YES
      - id: sw_adcs_ref_valid
        type: b1
        doc: |
          Refs Valid
          Enumeration values: 0/NO 1/YES
      - id: sw_adcs_time_valid
        type: b1
        doc: |
          Time Valid
          Enumeration values: 0/NO 1/YES
      - id: sw_adcs_mode
        type: b1
        doc: |
          ADCS Mode
          Enumeration values: 0/SUN_POINT 1/FINE_REF_POINT
      - id: sw_adcs_recommend_sun_point
        type: b1
        doc: |
          Recommend Sun Point
          Enumeration values: 0/NO 1/YES
      - id: sw_adcs_sun_point_state
        type: b3
        doc: |
          Sun Point State
          Enumeration values: 7/NOT_ACTIVE 2/SEARCH_INIT 4/WAITING
          5/CONVERGING 6/ON_SUN 3/SEARCHING 0/SUN_POINT 1/FINE_REF_POINT
      - id: reusable_spare_17
        type: u1
      - id: sw_adcs_analogs_voltage_2p5
        type: u1
        doc: |
          Voltage_2p5
          Conversion coefficients: c0=0.000000e+00 c1=1.500000e-02
          Eng. units: Volts (v)
      - id: sw_adcs_analogs_voltage_1p8
        type: u1
        doc: |
          Voltage_1p8
          Conversion coefficients: c0=0.000000e+00 c1=1.500000e-02
          Eng. units: Volts (v)
      - id: sw_adcs_analogs_voltage_1p0
        type: u1
        doc: |
          Voltage_1p0
          Conversion coefficients: c0=0.000000e+00 c1=1.500000e-02
          Eng. units: Volts (v)
      - id: sw_adcs_analogs_det_temp
        type: s1
        doc: |
          Tracker Detector temperature
          Conversion coefficients: c0=0.000000e+00 c1=8.000000e-01
          Eng. units: Celsius (C)
      - id: sw_adcs_analogs_motor1_temp
        type: s2
        doc: |
          Wheel 1 Temp
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-03
          Eng. units: Celsius (C)
      - id: sw_adcs_analogs_motor2_temp
        type: s2
        doc: |
          Wheel 2 Temp
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-03
          Eng. units: Celsius (C)
      - id: sw_adcs_analogs_motor3_temp
        type: s2
        doc: |
          Wheel 3 Temp
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-03
          Eng. units: Volts (v)
      - id: sw_adcs_analogs_digital_bus_v
        type: s2
        doc: |
          Digital Bus Voltage
          Conversion coefficients: c0=0.000000e+00 c1=1.250000e-03
          Eng. units: Volts (v)
      - id: sw_adcs_cmd_acpt
        type: u1
        doc: |
          ADCS Command Accept Count
      - id: sw_adcs_cmd_fail
        type: u1
        doc: |
          ADCS Command Reject Count
      - id: sw_adcs_sun_vec1
        type: s2
        doc: |
          ADCS Sun Vector 1
          Conversion coefficients: c0=0.000000e+00 c1=1.000000e-04
      - id: sw_adcs_sun_vec2
        type: s2
        doc: |
          ADCS Sun Vector 2
          Conversion coefficients: c0=0.000000e+00 c1=1.000000e-04
      - id: sw_adcs_sun_vec3
        type: s2
        doc: |
          ADCS Sun Vector 3
          Conversion coefficients: c0=0.000000e+00 c1=1.000000e-04
      - id: sw_adcs_wheel_sp1
        type: s2
        doc: |
          ADCS Wheel Speed 1
          Conversion coefficients: c0=0.000000e+00 c1=4.000000e-01
          Eng. units: RPM (rpm)
      - id: sw_adcs_wheel_sp2
        type: s2
        doc: |
          ADCS Wheel Speed 2
          Conversion coefficients: c0=0.000000e+00 c1=4.000000e-01
          Eng. units: RPM (rpm)
      - id: sw_adcs_wheel_sp3
        type: s2
        doc: |
          ADCS Wheel Speed 3
          Conversion coefficients: c0=0.000000e+00 c1=4.000000e-01
          Eng. units: RPM (rpm)
      - id: sw_adcs_body_rt1
        type: s4
        doc: |
          ADCS Body Frame Rate 1
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-09
          Eng. units: Rad/s (rps)
      - id: sw_adcs_body_rt2
        type: s4
        doc: |
          ADCS Body Frame Rate 2
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-09
          Eng. units: Rad/s (rps)
      - id: sw_adcs_body_rt3
        type: s4
        doc: |
          ADCS Body Frame Rate 3
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-09
          Eng. units: Rad/s (rps)
      - id: sw_adcs_body_quat1
        type: s4
        doc: |
          ADCS Body Quat 1
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-10
      - id: sw_adcs_body_quat2
        type: s4
        doc: |
          ADCS Body Quat 2
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-10
      - id: sw_adcs_body_quat3
        type: s4
        doc: |
          ADCS Body Quat 3
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-10
      - id: sw_adcs_body_quat4
        type: s4
        doc: |
          ADCS Body Quat 4
          Conversion coefficients: c0=0.000000e+00 c1=5.000000e-10
      - id: des_met_time_seconds
        type: u4
        doc: |
          DES MET TIME
      - id: sw_im_id
        type: u1
        doc: |
          SW Image version
      - id: payload_alive_axis1
        type: u1
        doc: |
          AXIS1 alive
      - id: payload_alive_axis2
        type: u1
        doc: |
          AXIS2 alive
      - id: payload_alive_axis3
        type: u1
        doc: |
          AXIS3 alive
      - id: payload_alive_afire
        type: u1
        doc: |
          AFIRE alive
      - id: reusable_spare_18
        type: u1
      - id: reusable_spare_19
        type: u1
      - id: reusable_spare_20
        type: u1
      - id: checksum
        type: u4
  aepex_sw_stat:
    seq:
      - id: sw_stat_t
        type: sw_stat_t
