---
meta:
  id: canvas
  title: CANVAS Beacon Parser
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
  :field bcn_fsw_major_version: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fsw_major_version
  :field bcn_fsw_minor_version: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fsw_minor_version
  :field bcn_fsw_patch_version: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fsw_patch_version
  :field bcn_fsw_image_id: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fsw_image_id
  :field bcn_seq_state_auto: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_state_auto
  :field bcn_seq_state_op: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_state_op
  :field bcn_seq_exec_buf0_auto: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_exec_buf0_auto
  :field bcn_seq_exec_buf0_op: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_exec_buf0_op
  :field bcn_fp_resp_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_resp_cnt
  :field bcn_fp_passive_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_passive_cnt
  :field bcn_fp_err_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_err_cnt
  :field bcn_des_met_time_sec: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_des_met_time_sec
  :field bcn_des_cycle_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_des_cycle_cnt
  :field bcn_cmd_recv_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_recv_cnt
  :field bcn_cmd_fmt_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_fmt_cnt
  :field bcn_cmd_rjct_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_rjct_cnt
  :field bcn_cmd_succ_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_succ_cnt
  :field bcn_cmd_fail_code: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_fail_code
  :field bcn_cmd_xsum_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_xsum_state
  :field bcn_store_partition_write_misc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_partition_write_misc
  :field bcn_store_partition_read_misc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_partition_read_misc
  :field bcn_store_partition_pbk_misc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_partition_pbk_misc
  :field bcn_store_partition_write_sci: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_partition_write_sci
  :field bcn_store_partition_read_sci: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_partition_read_sci
  :field bcn_store_partition_pbk_sci: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_partition_pbk_sci
  :field bcn_log_msgid_hdr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_log_msgid_hdr
  :field bcn_adcs_hk_pkt_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_hk_pkt_cnt
  :field bcn_adcs_alive: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_alive
  :field bcn_adcs_eclipse: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_eclipse
  :field bcn_adcs_msg_recv_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_msg_recv_cnt
  :field bcn_adcs_msg_rjct_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_msg_rjct_cnt
  :field bcn_eps_batt1_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_batt1_temp
  :field bcn_eps_batt2_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_batt2_temp
  :field bcn_eps_batt_pcb_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_batt_pcb_temp
  :field bcn_solar_panel1_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_solar_panel1_temp
  :field bcn_solar_panel2_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_solar_panel2_temp
  :field bcn_pwr_mntr1_all_pnl_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr1_all_pnl_curr
  :field bcn_pwr_mntr1_all_pnl_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr1_all_pnl_voltage
  :field bcn_pwr_mntr_pnl3_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr_pnl3_curr
  :field bcn_pwr_mntr_pnl3_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr_pnl3_voltage
  :field bcn_pwr_mntr1_xact_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr1_xact_curr
  :field bcn_pwr_mntr1_xact_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr1_xact_voltage
  :field bcn_pwr_mntr2_3v3_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr2_3v3_curr
  :field bcn_pwr_mntr2_3v3_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr2_3v3_voltage
  :field bcn_pwr_mntr2_pnl2_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr2_pnl2_curr
  :field bcn_pwr_mntr2_pnl2_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr2_pnl2_voltage
  :field bcn_pwr_mntr2_pnl1_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr2_pnl1_curr
  :field bcn_pwr_mntr2_pnl1_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr2_pnl1_voltage
  :field bcn_pwr_mntr3_main_bus_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr3_main_bus_curr
  :field bcn_pwr_mntr3_main_bus_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr3_main_bus_voltage
  :field bcn_pwr_mntr3_12vo_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr3_12vo_curr
  :field bcn_pwr_mntr3_12vo_voltage: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_mntr3_12vo_voltage
  :field bcn_temp_12vo: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_temp_12vo
  :field bcn_temp_3v3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_temp_3v3
  :field bcn_battery_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_battery_curr
  :field bcn_eps_battery_soc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_battery_soc
  :field bcn_battery_heater_status: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_battery_heater_status
  :field bcn_solar_panel1_ocv: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_solar_panel1_ocv
  :field bcn_solar_panel2_ocv: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_solar_panel2_ocv
  :field bcn_solar_panel3_ocv: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_solar_panel3_ocv
  :field bcn_mode_clt_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_mode_clt_cnt
  :field bcn_mode_system_mode: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_mode_system_mode
  :field bcn_adcs_cmd_tlm_cmd_acpt_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_cmd_tlm_cmd_acpt_cnt
  :field bcn_adcs_cmd_tlm_cmd_rjct_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_cmd_tlm_cmd_rjct_cnt
  :field bcn_eps_reg0_err_flags: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_reg0_err_flags
  :field bcn_eps_reg1_err_flags: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_reg1_err_flags
  :field bcn_sd0_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sd0_state
  :field bcn_sd1_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sd1_state
  :field bcn_sd2_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sd2_state
  :field reusable_spare_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_2
  :field bcn_pld_pwr_cycle_req: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pwr_cycle_req
  :field bcn_pld_pwr_off_req: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pwr_off_req
  :field bcn_pld_stat_msg_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_stat_msg_state
  :field bcn_pld_time_msg_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_time_msg_state
  :field bcn_pld_alive_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_alive_state
  :field reusable_spare_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_3
  :field bcn_eps_uhf_dep: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_uhf_dep
  :field bcn_eps_ant1_dep: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_ant1_dep
  :field bcn_eps_sap1_dep: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_sap1_dep
  :field bcn_eps_boom_dep: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_boom_dep
  :field bcn_eps_boom_enc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_boom_enc
  :field bcn_eps_boom_cnt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_boom_cnt
  :field bcn_eps_pld: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_pld
  :field bcn_eps_xact: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_xact
  :field bcn_eps_sband_tr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_sband_tr
  :field bcn_eps_sband_reset: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_sband_reset
  :field bcn_eps_sband_pwr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_sband_pwr
  :field bcn_eps_uhf_reset: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_uhf_reset
  :field bcn_eps_uhf_pwr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_uhf_pwr
  :field bcn_temp_digital: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_temp_digital
  :field bcn_temp_ana: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_temp_ana
  :field bcn_temp_cdh: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_temp_cdh
  :field bcn_temp_backplane: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_temp_backplane
  :field bcn_pld_digital_3p3_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_digital_3p3_i
  :field bcn_pld_digital_3p3_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_digital_3p3_v
  :field bcn_pld_digital_1p8_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_digital_1p8_i
  :field bcn_pld_digital_1p8_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_digital_1p8_v
  :field bcn_pld_digital_1p0_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_digital_1p0_i
  :field bcn_pld_digital_1p0_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_digital_1p0_v
  :field bcn_pld_ana_12p0_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_ana_12p0_i
  :field bcn_pld_ana_12p0_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_ana_12p0_v
  :field bcn_pld_ana_2p5_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_ana_2p5_i
  :field bcn_pld_ana_2p5_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_ana_2p5_v
  :field bcn_hstx_output_power: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_hstx_output_power
  :field bcn_hstx_pa_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_hstx_pa_temp
  :field bcn_hstx_pa_curr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_hstx_pa_curr
  :field bcn_mode_clt_threshold: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_mode_clt_threshold
  :field bcn_q_body_wrt_eci1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_q_body_wrt_eci1
  :field bcn_q_body_wrt_eci2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_q_body_wrt_eci2
  :field bcn_q_body_wrt_eci3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_q_body_wrt_eci3
  :field bcn_q_body_wrt_eci4: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_q_body_wrt_eci4
  :field bcn_body_rate1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_body_rate1
  :field bcn_body_rate2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_body_rate2
  :field bcn_body_rate3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_body_rate3
  :field bcn_rw_fltr_spd_rpm1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_rw_fltr_spd_rpm1
  :field bcn_rw_fltr_spd_rpm2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_rw_fltr_spd_rpm2
  :field bcn_rw_fltr_spd_rpm3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_rw_fltr_spd_rpm3
  :field bcn_sun_point_ang_err: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sun_point_ang_err
  :field bcn_adcs_css_sun_vec_body1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_css_sun_vec_body1
  :field bcn_adcs_css_sun_vec_body2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_css_sun_vec_body2
  :field bcn_adcs_css_sun_vec_body3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_css_sun_vec_body3
  :field bcn_adcs_att_cmd_adcs_mode: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_att_cmd_adcs_mode
  :field bcn_sun_point_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sun_point_state
  :field bcn_adcs_ana_det_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_ana_det_temp
  :field bcn_adcs_ana_motor1_temp: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_ana_motor1_temp

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
            - '"LASP  "'
            - '"CANVAS"'
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
            0x20: canvas_beacon_t
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
        type: u1
      - id: padding
        type: u1
  beacon_t:
    seq:
      - id: bcn_fsw_major_version
        type: u1
        doc: |
          Software Major Version
      - id: bcn_fsw_minor_version
        type: u1
        doc: |
          Software Minor Version
      - id: bcn_fsw_patch_version
        type: u1
        doc: |
          Software Patch Version
      - id: bcn_fsw_image_id
        type: u1
        doc: |
          Software Image ID
      - id: bcn_seq_state_auto
        type: u1
        doc: |
          State of the engine (Auto)
          Enumeration values: 0/IDLE 1/ACTIVE 2/SUSPEND 3/PAUSE 4/STALE
      - id: bcn_seq_state_op
        type: u1
        doc: |
          State of the engine (Op)
          Enumeration values: 0/IDLE 1/ACTIVE 2/SUSPEND 3/PAUSE 4/STALE
      - id: bcn_seq_exec_buf0_auto
        type: u2
        doc: |
          Buffer ID (Auto)
          Enumeration values: 0/RAM_SMALL0 1/RAM_SMALL1 2/RAM_SMALL2 3/RAM_SMALL3 4/RAM_SMALL4 5/RAM_SMALL5 6/RAM_SMALL6 7/RAM_SMALL7 8/RAM_LARGE0 9/RAM_LARGE1 10/RAM_LARGE2 11/RAM_LARGE3 12/NVM_MED0 13/NVM_MED1 14/NVM_MED2 15/NVM_MED3 16/NVM_MED4 17/NVM_MED5 18/NVM_MED6 19/NVM_MED7 20/NVM_MED8 21/NVM_MED9 22/NVM_MED10 23/NVM_MED11 24/NVM_MED12 25/NVM_MED13 26/NVM_MED14 27/NVM_MED15 28/NVM_MED16 29/NVM_MED17 30/NVM_MED18 31/NVM_MED19 32/NVM_MED20 33/NVM_MED21 34/NVM_MED22 35/NVM_MED23 36/NVM_MED24 37/NVM_MED25 38/NVM_MED26 39/NVM_MED27 40/NVM_MED28 41/NVM_MED29 42/NVM_MED30 43/NVM_MED31 44/NVM_MED32 45/NVM_MED33 46/NVM_MED34 47/NVM_MED35 48/NVM_MED36 49/NVM_MED37 50/NVM_MED38 51/NVM_MED39 52/NVM_MED40 53/NVM_MED41 54/NVM_MED42 55/NVM_MED43 56/NVM_MED44 57/NVM_MED45 58/NVM_MED46 59/NVM_MED47 60/NVM_MED48 61/NVM_MED49 62/NVM_MED50 63/NVM_MED51 64/NVM_MED52 65/NVM_MED53 66/NVM_MED54 67/NVM_MED55 68/NVM_MED56 69/NVM_MED57 70/NVM_MED58 71/NVM_MED59 72/NVM_MED60 73/NVM_MED61 74/NVM_MED62 75/NVM_MED63 76/NVM_MED64 77/NVM_MED65 78/NVM_MED66 79/NVM_MED67 80/NVM_MED68 81/NVM_MED69 82/NVM_MED70 83/NVM_MED71 84/NVM_MED72 85/NVM_MED73 86/NVM_MED74 87/NVM_MED75 88/NVM_MED76 89/NVM_MED77 90/NVM_MED78 91/NVM_MED79 92/NVM_LARGE0 93/NVM_LARGE1 94/HOLDING0
      - id: bcn_seq_exec_buf0_op
        type: u2
        doc: |
          Buffer ID (Op)
          Enumeration values: 0/RAM_SMALL0 1/RAM_SMALL1 2/RAM_SMALL2 3/RAM_SMALL3 4/RAM_SMALL4 5/RAM_SMALL5 6/RAM_SMALL6 7/RAM_SMALL7 8/RAM_LARGE0 9/RAM_LARGE1 10/RAM_LARGE2 11/RAM_LARGE3 12/NVM_MED0 13/NVM_MED1 14/NVM_MED2 15/NVM_MED3 16/NVM_MED4 17/NVM_MED5 18/NVM_MED6 19/NVM_MED7 20/NVM_MED8 21/NVM_MED9 22/NVM_MED10 23/NVM_MED11 24/NVM_MED12 25/NVM_MED13 26/NVM_MED14 27/NVM_MED15 28/NVM_MED16 29/NVM_MED17 30/NVM_MED18 31/NVM_MED19 32/NVM_MED20 33/NVM_MED21 34/NVM_MED22 35/NVM_MED23 36/NVM_MED24 37/NVM_MED25 38/NVM_MED26 39/NVM_MED27 40/NVM_MED28 41/NVM_MED29 42/NVM_MED30 43/NVM_MED31 44/NVM_MED32 45/NVM_MED33 46/NVM_MED34 47/NVM_MED35 48/NVM_MED36 49/NVM_MED37 50/NVM_MED38 51/NVM_MED39 52/NVM_MED40 53/NVM_MED41 54/NVM_MED42 55/NVM_MED43 56/NVM_MED44 57/NVM_MED45 58/NVM_MED46 59/NVM_MED47 60/NVM_MED48 61/NVM_MED49 62/NVM_MED50 63/NVM_MED51 64/NVM_MED52 65/NVM_MED53 66/NVM_MED54 67/NVM_MED55 68/NVM_MED56 69/NVM_MED57 70/NVM_MED58 71/NVM_MED59 72/NVM_MED60 73/NVM_MED61 74/NVM_MED62 75/NVM_MED63 76/NVM_MED64 77/NVM_MED65 78/NVM_MED66 79/NVM_MED67 80/NVM_MED68 81/NVM_MED69 82/NVM_MED70 83/NVM_MED71 84/NVM_MED72 85/NVM_MED73 86/NVM_MED74 87/NVM_MED75 88/NVM_MED76 89/NVM_MED77 90/NVM_MED78 91/NVM_MED79 92/NVM_LARGE0 93/NVM_LARGE1 94/HOLDING0
      - id: bcn_fp_resp_cnt
        type: u2
        doc: |
          Fault Protection Response Count
      - id: bcn_fp_passive_cnt
        type: u2
        doc: |
          Fault Protection Passive Count
      - id: bcn_fp_err_cnt
        type: u2
        doc: |
          Fault Protection Error Count
      - id: bcn_des_met_time_sec
        type: u4
        doc: |
          Current MET Seconds
      - id: bcn_des_cycle_cnt
        type: u2
        doc: |
          Number of Scheduled Cycles
      - id: bcn_cmd_recv_cnt
        type: u2
        doc: |
          Number of Received Commands
      - id: bcn_cmd_fmt_cnt
        type: u2
        doc: |
          Number of bad format Commands
      - id: bcn_cmd_rjct_cnt
        type: u2
        doc: |
          Number of Rejected Commands
      - id: bcn_cmd_succ_cnt
        type: u2
        doc: |
          Number of successful commands
      - id: padding1
        type: u4
        doc: |
          Padding 1
      - id: bcn_cmd_fail_code
        type: u1
        doc: |
          Command failure code
          Enumeration values: 0/SUCCESS 1/MODE 2/ARM 3/SOURCE 4/OPCODE 5/METHOD 6/LENGTH 7/RANGE 8/CHECKSUM 9/PKT_TYPE
      - id: bcn_cmd_xsum_state
        type: u1
        doc: |
          Checksum checking state
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_store_partition_write_misc
        type: u4
        doc: |
          Misc Partition Write Address
      - id: bcn_store_partition_read_misc
        type: u4
        doc: |
          Misc Partition Read Address
      - id: bcn_store_partition_pbk_misc
        type: u4
        doc: |
          Misc Partition Playback Address
      - id: bcn_store_partition_write_sci
        type: u4
        doc: |
          Science Partition Write Address
      - id: bcn_store_partition_read_sci
        type: u4
        doc: |
          Science Partition Read Address
      - id: bcn_store_partition_pbk_sci
        type: u4
        doc: |
          Science Partition Playback Address
      - id: bcn_log_msgid_hdr
        type: u2
        doc: |
          ID of the message
          Enumeration values: 0/MSG_CMD_RECEIVED 1/MSG_CMD_REJECTED 2/MSG_CMD_REJECTED_CODE 3/MSG_CMD_UNKNOWN_APID 4/MSG_CMD_BAD_APID 5/MSG_CMD_BAD_TYPE 6/MSG_CMD_BAD_LENGTH 7/MSG_CMD_BAD_XSUM 8/MSG_CMD_INVALID_LENGTH 9/MSG_CMD_BAD_SOURCE 10/MSG_CMD_BAD_FLETCH_EXPECTED 11/MSG_CMD_BAD_FLETCH_RECEIVED 12/MSG_CMD_GET_VERSION 512/MSG_SEQ_STATE 513/MSG_SEQ_CALL 514/MSG_SEQ_RETURN 515/MSG_SEQ_START 516/MSG_SEQ_FIND 517/MSG_SEQ_INFO 518/MSG_SEQ_ERROR_NO_SEQ 519/MSG_SEQ_ERROR_BAD_STATE 520/MSG_SEQ_ERROR_STOP 521/MSG_SEQ_ERROR_NESTED 522/MSG_SEQ_ERR_FIND 523/MSG_SEQ_CMD 524/MSG_SEQ_INT_CMD 768/MSG_MEM_BAD_SECTION 769/MSG_MEM_STATE 770/MSG_MEM_OP_FAIL 771/MSG_MEM_DEFAULT_CASE 1024/MSG_ERROR_DES_OVERRUN 1025/MSG_ERROR_DES_OVERRUN_TIME 1026/MSG_ERROR_DES_CMD_NYI 1027/MSG_PM_DES_TASK_ENTRY 1028/MSG_PM_DES_TASK_EXIT 1029/MSG_ERROR_DES_BAD_SLICE 1280/MSG_FP_WATCH_FIRED 1281/MSG_FP_WATCH_PASSIVE 1282/MSG_ERROR_FP_BAD_VALIDATE 1283/MSG_ERROR_FP_BAD_WATCH 1284/MSG_FP_BAD_TABLE_ERR 1536/MSG_TBL_UPDATE_PENDING 1537/MSG_TBL_UPDATE_COMPLETE 1538/MSG_TBL_VERIFY_BAD_CHECK 1539/MSG_TBL_VERIFY_BAD_VALIDATE 1540/MSG_TBL_COMMIT 1541/MSG_TBL_LOAD_START 1542/MSG_TBL_VERIFY_GOOD 1543/MSG_TBL_COMMIT_NO_VERIFY 1544/MSG_TBL_COMMIT_BAD_ID 1545/MSG_TBL_BAD_REG_DATA 1546/MSG_TBL_BAD_REG_TABLE 1547/MSG_TBL_BAD_STORAGE 1548/MSG_TBL_UPDATE_FAILED 1792/MSG_PKT_BAD_APID 1793/MSG_TLM_PKT_SEND_ERR 1794/MSG_TLM_PKT_SENT 1795/MSG_PKT_QUERY_RSEPONSE 1796/MSG_PKT_ISSUE_UNAV 1797/MSG_PKT_SYNC_RX_TIMEOUT 2048/MSG_STORE_PKT_SIZE_ERROR 2049/MSG_STORE_CARD_READ_ERR 2050/MSG_STORE_READ_TIME_PAGE_ERROR 2051/MSG_STORE_BAD_TABLE 2052/MSG_STORE_READ_BAD_LEN_ERR 2053/MSG_STORE_CARD_BAD_WRITE_ERR 2054/MSG_STORE_READ_START 2055/MSG_STORE_READ_HALT 2056/MSG_STORE_BAD_POINTERS 2057/MSG_STORE_INIT_PARTITION 2304/MSG_ADCS_ECLIPSE_STATE_MSG 2306/MSG_ADCS_DUMP_ERR_MSG 2307/MSG_ADCS_BAD_TABLE_ERR_MSG 2308/MSG_ADCS_STATUS_CHANGE_MSG 2309/MSG_ADCS_NO_HK_ERR_MSG 2310/MSG_ADCS_MSG_LEN_ERR_MSG 2311/MSG_ADCS_MSG_APID_ERR_MSG 2312/MSG_ADCS_MSG_PASS_ERR_MSG 2313/MSG_ADCS_DEFAULT_CASE_ERR_MSG 2314/MSG_ADCS_PASS_CMD_MSG 2560/MSG_SBAND_MODE_MSG 2561/MSG_SBAND_ALIVE_MSG 2562/MSG_SBAND_SYNC_TIMEOUT_ERR_MSG 2563/MSG_SBAND_DEAD_ERR_MSG 2816/MSG_UHF_MSG 2817/MSG_UHF_ERR_MSG 3072/MSG_SD_MSG 3073/MSG_SD_ERR_MSG 3328/MSG_EPS_SET_CFG_ACK 3329/MSG_EPS_MAX_MISSED_HK 3330/MSG_EPS_STATUS_CHANGE 3331/MSG_EPS_HEATER_STATUS_CHANGE 3332/MSG_EPS_MISSED_HK 3333/MSG_EPS_WDT_RESET_ACK 3334/MSG_EPS_CTRL_12V0_ACK 3335/MSG_EPS_CTRL_12V0_XACT_ACK 3336/MSG_EPS_BAD_TBL 3584/MSG_PAYLOAD_PASS_CMD_MSG 3586/MSG_PAYLOAD_PASS_ERR_MSG 3587/MSG_PAYLOAD_STATUS_MSG 3600/MSG_PAYLOAD_PASS_CMD_XSUM_MSG 3601/MSG_PAYLOAD_TIMESTAMP_REPLACED 3840/ERR_DEV_LIST_FULL 4096/MSG_DEPLOY_MSG 4097/MSG_DEPLOY_ERR_MSG 4352/MSG_MODE_CLT_FIRST_ERROR_MSG 4353/MSG_MODE_CLT_SECOND_ERROR_MSG 4354/MSG_MODE_BAD_TABLE_ERROR_MSG 4355/MSG_MODE_TRANSITION 4356/MSG_MODE_SEQ_ERROR 4609/MSG_INIT_SEQ_STAT
      - id: bcn_adcs_hk_pkt_cnt
        type: u2
        doc: |
          Number of HK Pkts Received from XACT
      - id: bcn_adcs_alive
        type: u1
        doc: |
          ADCS Alive state of communication
          Enumeration values: 0/OFF 1/DEAD 2/ALIVE
      - id: bcn_adcs_eclipse
        type: u1
        doc: |
          State of Eclipse
      - id: bcn_adcs_msg_recv_cnt
        type: u2
        doc: |
          Number of ADCS Received Msgs
      - id: bcn_adcs_msg_rjct_cnt
        type: u2
        doc: |
          Number of ADCS Rejected Msgs
      - id: bcn_eps_batt1_temp
        type: u2
        doc: |
          Temperature of battery 1
      - id: bcn_eps_batt2_temp
        type: u2
        doc: |
          Temperature of battery 2
      - id: bcn_eps_batt_pcb_temp
        type: u2
        doc: |
          Temperature of battery PCB
      - id: bcn_solar_panel1_temp
        type: u2
        doc: |
          Temperature from Solar Panel 1
      - id: bcn_solar_panel2_temp
        type: u2
        doc: |
          Temperature from Solar Panel 2
      - id: bcn_pwr_mntr1_all_pnl_curr
        type: u2
        doc: |
          Power Monitor 1 All Panels Current
      - id: bcn_pwr_mntr1_all_pnl_voltage
        type: u2
        doc: |
          Power Monitor 1 All Panels Voltage
      - id: bcn_pwr_mntr_pnl3_curr
        type: u2
        doc: |
          Power Monitor 1 Solar Panel 3 Current
      - id: bcn_pwr_mntr_pnl3_voltage
        type: u2
        doc: |
          Power Monitor 1 Solar Panel 3 Voltage
      - id: bcn_pwr_mntr1_xact_curr
        type: u2
        doc: |
          Power Monitor 1 12VO_XACT Current
      - id: bcn_pwr_mntr1_xact_voltage
        type: u2
        doc: |
          Power Monitor 1 12VO_XACT Voltage
      - id: bcn_pwr_mntr2_3v3_curr
        type: u2
        doc: |
          Power Monitor 2 3v3 Current
      - id: bcn_pwr_mntr2_3v3_voltage
        type: u2
        doc: |
          Power Monitor 2 3v3 Voltage
      - id: bcn_pwr_mntr2_pnl2_curr
        type: u2
        doc: |
          Power Monitor 2 Solar Panel 2 Current
      - id: bcn_pwr_mntr2_pnl2_voltage
        type: u2
        doc: |
          Power Monitor 2 Solar Panel 2 Voltage
      - id: bcn_pwr_mntr2_pnl1_curr
        type: u2
        doc: |
          Power Monitor 2 Solar Panel 1 Current
      - id: bcn_pwr_mntr2_pnl1_voltage
        type: u2
        doc: |
          Power Monitor 2 Solar Panel 1 Voltage
      - id: bcn_pwr_mntr3_main_bus_curr
        type: u2
        doc: |
          Power Monitor 3 Main Bus Current
      - id: bcn_pwr_mntr3_main_bus_voltage
        type: u2
        doc: |
          Power Monitor 3 Main Bus Voltage
      - id: bcn_pwr_mntr3_12vo_curr
        type: u2
        doc: |
          Power Monitor 3 12VO Current
      - id: bcn_pwr_mntr3_12vo_voltage
        type: u2
        doc: |
          Power Monitor 3 12VO Voltage
      - id: bcn_temp_12vo
        type: s2
        doc: |
          Temperature from 12VO Buck
      - id: bcn_temp_3v3
        type: s2
        doc: |
          Temperature from 3v3 Buck
      - id: bcn_battery_curr
        type: s2
        doc: |
          Battery Current
      - id: bcn_eps_battery_soc
        type: u2
        doc: |
          Battery State of Charge
      - id: bcn_battery_heater_status
        type: u2
        doc: |
          Battery Heater Status
          Enumeration values: 0/OFF 1/ON
      - id: bcn_solar_panel1_ocv
        type: u2
        doc: |
          Open circuit Voltage from Solar Panel 1
      - id: bcn_solar_panel2_ocv
        type: u2
        doc: |
          Open circuit Voltage from Solar Panel 2
      - id: bcn_solar_panel3_ocv
        type: u2
        doc: |
          Open circuit Voltage from Solar Panel 3
      - id: bcn_mode_clt_cnt
        type: u1
        doc: |
          CLT Count
      - id: bcn_mode_system_mode
        type: u1
        doc: |
          System Mode
          Enumeration values: 0/PHOENIX 1/SAFE 2/NOMINAL
      - id: bcn_adcs_cmd_tlm_cmd_acpt_cnt
        type: u1
        doc: |
          ADCS Command accept count
      - id: bcn_adcs_cmd_tlm_cmd_rjct_cnt
        type: u1
        doc: |
          ADCS Command reject count
      - id: bcn_eps_reg0_err_flags
        type: u4
        doc: |
          EPS Error Flags Register 0
      - id: bcn_eps_reg1_err_flags
        type: u4
        doc: |
          EPS Error Flags Register 1
      - id: bcn_sd0_state
        type: u1
        doc: |
          SD Card 0 or Number 1 State
          Enumeration values: 0/PWR_OFF 1/PWR_ON 2/Initialize 3/Send 4/CMD0 5/CMD8 6/CMD55 7/ACMD41 8/CMD58 9/CMD9 10/Read 11/Ready 15/FAILED
      - id: bcn_sd1_state
        type: u1
        doc: |
          SD Card 1 or Number 2 State
          Enumeration values: 0/PWR_OFF 1/PWR_ON 2/Initialize 3/Send 4/CMD0 5/CMD8 6/CMD55 7/ACMD41 8/CMD58 9/CMD9 10/Read 11/Ready 15/FAILED
      - id: bcn_sd2_state
        type: u1
        doc: |
          SD Card 2 or Number 3 State
          Enumeration values: 0/PWR_OFF 1/PWR_ON 2/Initialize 3/Send 4/CMD0 5/CMD8 6/CMD55 7/ACMD41 8/CMD58 9/CMD9 10/Read 11/Ready 15/FAILED
      - id: reusable_spare_2
        type: b2
      - id: bcn_pld_pwr_cycle_req
        type: b1
        doc: |
          Power Cycle Request State
          Enumeration values: 0/INACTIVE 1/ACTIVE
      - id: bcn_pld_pwr_off_req
        type: b1
        doc: |
          Power Off Request State
          Enumeration values: 0/INACTIVE 1/ACTIVE
      - id: bcn_pld_stat_msg_state
        type: b1
        doc: |
          Status Message State
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_pld_time_msg_state
        type: b1
        doc: |
          Time Message State
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_pld_alive_state
        type: b2
        doc: |
          Aliveness State
          Enumeration values: 0/OFF 1/DEAD 2/ALIVE
      - id: reusable_spare_3
        type: b3
      - id: bcn_eps_uhf_dep
        type: b1
        doc: |
          UHF Deploy Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_ant1_dep
        type: b1
        doc: |
          Antenna 1 Deploy
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_sap1_dep
        type: b1
        doc: |
          Solar Array Panel 1 Deploy
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_boom_dep
        type: b1
        doc: |
          Boom Deploy
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_boom_enc
        type: b1
        doc: |
          Boom Encoder
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_boom_cnt
        type: b1
        doc: |
          Boom Counter
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_pld
        type: b1
        doc: |
          Payload Power Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_xact
        type: b1
        doc: |
          XACT Power Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_sband_tr
        type: b1
        doc: |
          SBAND Transmit Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_sband_reset
        type: b1
        doc: |
          SBAND Reset Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_sband_pwr
        type: b1
        doc: |
          SBAND Power Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_uhf_reset
        type: b1
        doc: |
          UHF Reset Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_eps_uhf_pwr
        type: b1
        doc: |
          UHF Power Status
          Enumeration values: 0/DIS 1/ENA
      - id: bcn_temp_digital_raw
        type: u2
        doc: |
          Temperature of Payload Digital Board
      - id: bcn_temp_ana_raw
        type: u2
        doc: |
          Temperature of Payload Analog Board
      - id: bcn_temp_cdh_raw
        type: u2
        doc: |
          Temperature of CDH Board
      - id: bcn_temp_backplane_raw
        type: u2
        doc: |
          Temperature of Backplane Board
      - id: bcn_pld_digital_3p3_i
        type: s2
        doc: |
          Power Monitor DB 3.3V Current
      - id: bcn_pld_digital_3p3_v
        type: s2
        doc: |
          Power Monitor DB 3.3V Voltage
      - id: bcn_pld_digital_1p8_i
        type: s2
        doc: |
          Power Monitor DB 1.8V Current
      - id: bcn_pld_digital_1p8_v
        type: s2
        doc: |
          Power Monitor DB 1.8V Voltage
      - id: bcn_pld_digital_1p0_i
        type: s2
        doc: |
          Power Monitor DB 1.0V Current
      - id: bcn_pld_digital_1p0_v
        type: s2
        doc: |
          Power Monitor DB 1.0V Voltage
      - id: bcn_pld_ana_12p0_i
        type: s2
        doc: |
          Power Monitor AB 12V Current
      - id: bcn_pld_ana_12p0_v
        type: s2
        doc: |
          Power Monitor AB 12V Voltage
      - id: bcn_pld_ana_2p5_i
        type: s2
        doc: |
          Power Monitor AB 2.5V Current
      - id: bcn_pld_ana_2p5_v
        type: s2
        doc: |
          Power Monitor AB 2.5V Voltage
      - id: bcn_hstx_output_power
        type: u2
        doc: |
          SBand RF output power
      - id: bcn_hstx_pa_temp
        type: u2
        doc: |
          SBand pre-amplifier temperature
      - id: bcn_hstx_pa_curr
        type: u2
        doc: |
          SBand pre-amplifier current
      - id: bcn_mode_clt_threshold
        type: u4
        doc: |
          CLT Threshold
      - id: bcn_q_body_wrt_eci1
        type: u4
        doc: |
          Attitude Quaternion 1
      - id: bcn_q_body_wrt_eci2
        type: u4
        doc: |
          Attitude Quaternion 2
      - id: bcn_q_body_wrt_eci3
        type: u4
        doc: |
          Attitude Quaternion 3
      - id: bcn_q_body_wrt_eci4
        type: u4
        doc: |
          Attitude Quaternion 4
      - id: bcn_body_rate1
        type: u4
        doc: |
          Body Frame Rate 1
          Rad/s Conversion: c0 = 0.0 c1 = 5.000000e-09
          Deg/s Conversion: c0 = 0.0 c1 = 2.864788975654116e-07
          RPM   Conversion: c0 = 0.0 c1 = 4.77464829275686e-08
      - id: bcn_body_rate2
        type: u4
        doc: |
          Body Frame Rate 2
          Rad/s Conversion: c0 = 0.0 c1 = 5.000000e-09
          Deg/s Conversion: c0 = 0.0 c1 = 2.864788975654116e-07
          RPM   Conversion: c0 = 0.0 c1 = 4.77464829275686e-08
      - id: bcn_body_rate3
        type: u4
        doc: |
          Body Frame Rate 3
          Rad/s Conversion: c0 = 0.0 c1 = 5.000000e-09
          Deg/s Conversion: c0 = 0.0 c1 = 2.864788975654116e-07
          RPM   Conversion: c0 = 0.0 c1 = 4.77464829275686e-08
      - id: bcn_rw_fltr_spd_rpm1
        type: s2
        doc: |
          Wheel Number 1 Measured Speed
      - id: bcn_rw_fltr_spd_rpm2
        type: s2
        doc: |
          Wheel Number 2 Measured Speed
      - id: bcn_rw_fltr_spd_rpm3
        type: s2
        doc: |
          Wheel Number 3 Measured Speed
      - id: bcn_sun_point_ang_err
        type: u2
        doc: |
          Sun Angle Point Error
      - id: bcn_adcs_css_sun_vec_body1
        type: s2
        doc: |
          Measured Sun Body Vector X
      - id: bcn_adcs_css_sun_vec_body2
        type: s2
        doc: |
          Measured Sun Body Vector Y
      - id: bcn_adcs_css_sun_vec_body3
        type: s2
        doc: |
          Measured Sun Body Vector Z
      - id: bcn_adcs_att_cmd_adcs_mode
        type: u1
        doc: |
          ADCS System Mode
          Enumeration values: 0/SUN_POINT 1/FINE_REF_POINT
      - id: bcn_sun_point_state
        type: u1
        doc: |
          Sun Point State
          Enumeration values: 0/NA 2/SEARCH_INIT 3/SEARCHING 4/WAITING 5/CONVERGING 6/ON_SUN 7/NOT_ACTIVE
      - id: bcn_adcs_ana_det_temp
        type: s2
        doc: |
          XACT Tracker Detector Temperature
      - id: bcn_adcs_ana_motor1_temp
        type: s2
        doc: |
          Wheel 1 Temperature
      - id: checksum
        type: u4
    instances:
      bcn_temp_digital:
        value: '(bcn_temp_digital_raw & 0xFFF) >= 2048 ? (bcn_temp_digital_raw & 0xFFF) - 4096 : (bcn_temp_digital_raw & 0xFFF)'
      bcn_temp_ana:
        value: '(bcn_temp_ana_raw & 0xFFF) >= 2048 ? (bcn_temp_ana_raw & 0xFFF) - 4096 : (bcn_temp_ana_raw & 0xFFF)'
      bcn_temp_cdh:
        value: '(bcn_temp_cdh_raw & 0xFFF) >= 2048 ? (bcn_temp_cdh_raw & 0xFFF) - 4096 : (bcn_temp_cdh_raw & 0xFFF)'
      bcn_temp_backplane:
        value: '(bcn_temp_backplane_raw & 0xFFF) >= 2048 ? (bcn_temp_backplane_raw & 0xFFF) - 4096 : (bcn_temp_backplane_raw & 0xFFF)'

  canvas_beacon_t:
    seq:
      - id: beacon_t
        type: beacon_t
