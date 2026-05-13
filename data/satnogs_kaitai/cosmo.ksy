---
meta:
  id: cosmo
  title: COSMO 75cm beacon packet struct
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
  :field sc_fsw_28_ver: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_ver
  :field sc_fsw_28_type: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_type
  :field sc_fsw_28_sec_hdr_flag: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_sec_hdr_flag
  :field sc_fsw_28_pkt_apid: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_pkt_apid
  :field sc_fsw_28_seq_flgs: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_seq_flgs
  :field sc_fsw_28_seq_ctr: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_seq_ctr
  :field sc_fsw_28_pkt_len: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_pkt_len
  :field sc_fsw_28_shcoarse: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_shcoarse
  :field sc_fsw_28_shfine: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.sc_fsw_28_shfine
  :field bcn_adcs_tai_sec: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_tai_sec
  :field bcn_time_since_boot: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_time_since_boot
  :field bcn_hr_cyc_ct_safe: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_hr_cyc_ct_safe
  :field bcn_sec_in_mode: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sec_in_mode
  :field bcn_adcs_bod_rt_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_bod_rt_1
  :field bcn_adcs_bod_rt_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_bod_rt_2
  :field bcn_adcs_bod_rt_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_bod_rt_3
  :field bcn_adcs_att_resid_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_att_resid_1
  :field bcn_adcs_att_resid_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_att_resid_2
  :field bcn_adcs_att_resid_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_att_resid_3
  :field bcn_adcs_gps_pos_ecef_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_gps_pos_ecef_1
  :field bcn_adcs_gps_pos_ecef_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_gps_pos_ecef_2
  :field bcn_adcs_gps_pos_ecef_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_gps_pos_ecef_3
  :field bcn_cmd_rx_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_rx_ct
  :field bcn_cmd_rej_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_rej_ct
  :field bcn_cmd_succ_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_succ_ct
  :field bcn_pld_pass_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pass_ct
  :field bcn_pld_pass_err: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pass_err
  :field bcn_pld_pkt_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pkt_ct
  :field bcn_pld_5_v_0_reg_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_5_v_0_reg_t
  :field bcn_pld_3_v_3_reg_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_3_v_3_reg_t
  :field bcn_pld_sb_1_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_sb_1_t
  :field bcn_pld_sb_2_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_sb_2_t
  :field bcn_pld_vrum_t_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_vrum_t_1
  :field bcn_pld_vrum_t_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_vrum_t_2
  :field bcn_pld_pkt_rx_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pkt_rx_ct
  :field bcn_pld_pkt_ack_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pkt_ack_ct
  :field bcn_pld_pkt_nack_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pkt_nack_ct
  :field bcn_pld_err_reg_0_0: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_err_reg_0_0
  :field bcn_pld_err_reg_0_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_err_reg_0_1
  :field bcn_pld_err_reg_1_0: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_err_reg_1_0
  :field bcn_pld_err_reg_1_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_err_reg_1_1
  :field bcn_seq_exec_buf_auto: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_exec_buf_auto
  :field bcn_seq_exec_buf_op_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_exec_buf_op_1
  :field bcn_seq_exec_buf_op_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_exec_buf_op_2
  :field bcn_seq_exec_buf_op_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_exec_buf_op_3
  :field reusable_spare_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_1
  :field bcn_store_part_wr_log: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_wr_log
  :field bcn_store_part_rd_log: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_rd_log
  :field bcn_store_part_wr_adcs: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_wr_adcs
  :field bcn_store_part_rd_adcs: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_rd_adcs
  :field bcn_store_part_wr_hk: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_wr_hk
  :field bcn_store_part_rd_hk: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_rd_hk
  :field bcn_store_part_wr_sci: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_wr_sci
  :field bcn_store_part_rd_sci: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_store_part_rd_sci
  :field bcn_fp_resp_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_resp_ct
  :field bcn_bat_1_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_bat_1_v
  :field bcn_bat_2_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_bat_2_v
  :field bcn_bat_1_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_bat_1_t
  :field bcn_bat_2_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_bat_2_t
  :field bcn_3p3_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_3p3_i
  :field bcn_cdh_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cdh_t
  :field bcn_sa_1_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sa_1_v
  :field bcn_sa_1_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sa_1_i
  :field bcn_sa_2_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sa_2_v
  :field bcn_sa_2_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sa_2_i
  :field bcn_eps_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_t
  :field bcn_eps_bus_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_bus_v
  :field bcn_eps_bus_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_eps_bus_i
  :field bcn_xact_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_xact_v
  :field bcn_xact_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_xact_i
  :field bcn_uhf_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_uhf_v
  :field bcn_uhf_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_uhf_i
  :field bcn_sbd_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sbd_v
  :field bcn_sbd_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sbd_i
  :field bcn_vrum_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_vrum_v
  :field bcn_vrum_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_vrum_i
  :field bcn_gps_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_gps_v
  :field bcn_gps_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_gps_i
  :field bcn_boom_v: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_boom_v
  :field bcn_boom_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_boom_i
  :field bcn_ifb_t_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_ifb_t_1
  :field bcn_adcs_rw_1_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_rw_1_t
  :field bcn_adcs_rw_sp_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_rw_sp_1
  :field bcn_adcs_rw_sp_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_rw_sp_2
  :field bcn_adcs_rw_sp_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_rw_sp_3
  :field bcn_sun_pt_err: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sun_pt_err
  :field bcn_mag_vec_bod_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_mag_vec_bod_1
  :field bcn_mag_vec_bod_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_mag_vec_bod_2
  :field bcn_mag_vec_bod_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_mag_vec_bod_3
  :field bcn_sbd_pa_i: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sbd_pa_i
  :field bcn_sbd_pa_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sbd_pa_t
  :field bcn_cmd_fail_code: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_cmd_fail_code
  :field bcn_vrum_cmd_rej_rsn: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_vrum_cmd_rej_rsn
  :field bcn_clt_hr_left: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_clt_hr_left
  :field bcn_clt_ct: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_clt_ct
  :field bcn_sys_mode: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_sys_mode
  :field bcn_uhf_alive: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_uhf_alive
  :field reusable_spare_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_2
  :field bcn_pld_pwr_cyc_vrum: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pwr_cyc_vrum
  :field bcn_pld_pwr_off_vrum: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pwr_off_vrum
  :field bcn_pld_stat_st_vrum: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_stat_st_vrum
  :field bcn_pld_time_st_vrum: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_time_st_vrum
  :field bcn_pld_alive_st_vrum: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_alive_st_vrum
  :field reusable_spare_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_3
  :field bcn_pld_pwr_cyc_boom: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pwr_cyc_boom
  :field bcn_pld_pwr_off_boom: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_pwr_off_boom
  :field bcn_pld_stat_st_boom: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_stat_st_boom
  :field bcn_pld_time_st_boom: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_time_st_boom
  :field bcn_pld_alive_st_boom: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pld_alive_st_boom
  :field bcn_uhf_t: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_uhf_t
  :field bcn_seq_state_auto: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_state_auto
  :field bcn_seq_state_op_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_state_op_1
  :field bcn_seq_state_op_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_state_op_2
  :field bcn_seq_state_op_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_seq_state_op_3
  :field reusable_spare_4: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_4
  :field reusable_spare_5: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_5
  :field reusable_spare_6: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_6
  :field reusable_spare_7: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_7
  :field reusable_spare_8: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_8
  :field reusable_spare_9: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_9
  :field bcn_htr_pwr_state_bat_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_htr_pwr_state_bat_2
  :field bcn_htr_pwr_state_bat_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_htr_pwr_state_bat_1
  :field reusable_spare_10: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.reusable_spare_10
  :field bcn_pwr_state_boom: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_state_boom
  :field bcn_pwr_state_gps: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_state_gps
  :field bcn_pwr_state_unused: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_state_unused
  :field bcn_pwr_state_vrum: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_state_vrum
  :field bcn_pwr_state_sbd: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_state_sbd
  :field bcn_pwr_state_uhf: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_state_uhf
  :field bcn_pwr_state_adcs: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_pwr_state_adcs
  :field bcn_fp_task_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_task_state
  :field bcn_fp_state_wp_23: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_23
  :field bcn_fp_state_wp_22: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_22
  :field bcn_fp_state_wp_21: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_21
  :field bcn_fp_state_wp_20: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_20
  :field bcn_fp_state_wp_19: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_19
  :field bcn_fp_state_wp_18: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_18
  :field bcn_fp_state_wp_17: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_17
  :field bcn_fp_state_wp_16: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_16
  :field bcn_fp_state_wp_15: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_15
  :field bcn_fp_state_wp_14: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_14
  :field bcn_fp_state_wp_13: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_13
  :field bcn_fp_state_wp_12: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_12
  :field bcn_fp_state_wp_11: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_11
  :field bcn_fp_state_wp_10: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_10
  :field bcn_fp_state_wp_9: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_9
  :field bcn_fp_state_wp_8: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_8
  :field bcn_fp_state_wp_7: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_7
  :field bcn_fp_state_wp_6: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_6
  :field bcn_fp_state_wp_5: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_5
  :field bcn_fp_state_wp_4: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_4
  :field bcn_fp_state_wp_3: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_3
  :field bcn_fp_state_wp_2: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_2
  :field bcn_fp_state_wp_1: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_1
  :field bcn_fp_state_wp_0: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_fp_state_wp_0
  :field bcn_adcs_alive: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_alive
  :field bcn_adcs_att_vld: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_att_vld
  :field bcn_adcs_ref_vld: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_ref_vld
  :field bcn_adcs_time_vld: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_time_vld
  :field bcn_adcs_mode: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_mode
  :field bcn_adcs_rec_sun_pt: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_rec_sun_pt
  :field bcn_adcs_sun_pt_state: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_sun_pt_state
  :field bcn_adcs_cmd_acc: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_cmd_acc
  :field bcn_adcs_cmd_fail: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_cmd_fail
  :field bcn_adcs_cmd_stat: ax25_frame.payload.ax25_info.ccsds_space_packet.data_section.user_data_field.beacon_t.bcn_adcs_cmd_stat

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
        encoding: ascii
        size: 6
        valid:
          any-of:
            - '"LASP  "'
            - '"COSMO "'
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
            0x1C: cosmo_beacon_t
  secondary_header_t:
    doc: |
      the secondary header is a feature of the space packet which allows
      additional types of information that may be useful to the user
      application (e.g., a time code) to be included.
      see: 4.1.3.2 in ccsds 133.0-b-1
    seq:
      - id: time_stamp_seconds
        type: u4
      - id: sub_seconds
        type: u2
  beacon_t:
    seq:
      - id: bcn_adcs_tai_sec
        type: f8
        doc: |
          adcs time
      - id: bcn_time_since_boot
        type: u4
        doc: |
          des mission elapsed time
      - id: bcn_hr_cyc_ct_safe
        type: u4
        doc: |
          adcs 5hz timestamp of last safe mode
      - id: bcn_sec_in_mode
        type: u4
        doc: |
          seconds since last cdh mode change
      - id: bcn_adcs_bod_rt_1
        type: s4
        doc: |
          adcs body frame rate in sc x-axis
      - id: bcn_adcs_bod_rt_2
        type: s4
        doc: |
          adcs body frame rate in sc y-axis
      - id: bcn_adcs_bod_rt_3
        type: s4
        doc: |
          adcs body frame rate in sc z-axis
      - id: bcn_adcs_att_resid_1
        type: s4
        doc: |
          adcs attitude filter residual
      - id: bcn_adcs_att_resid_2
        type: s4
        doc: |
          adcs attitude filter residual
      - id: bcn_adcs_att_resid_3
        type: s4
        doc: |
          adcs attitude filter residual
      - id: bcn_adcs_gps_pos_ecef_1
        type: s4
        doc: |
          gps position in ecef-x axis
      - id: bcn_adcs_gps_pos_ecef_2
        type: s4
        doc: |
          gps position in ecef-y axis
      - id: bcn_adcs_gps_pos_ecef_3
        type: s4
        doc: |
          gps position in ecef-z axis
      - id: bcn_cmd_rx_ct
        type: u2
        doc: |
          cdh number of received commands
      - id: bcn_cmd_rej_ct
        type: u2
        doc: |
          cdh number of rejected commands
      - id: bcn_cmd_succ_ct
        type: u2
        doc: |
          cdh number of successful commands
      - id: bcn_pld_pass_ct
        type: u2
        doc: |
          cdh number of pass through commands sent to the payload
      - id: bcn_pld_pass_err
        type: u2
        doc: |
          cdh number of rejected pass through commands to the payload
      - id: bcn_pld_pkt_ct
        type: u2
        doc: |
          cdh number of packets received from payload
      - id: bcn_pld_5_v_0_reg_t
        type: u2
        doc: |
          temperature at 5v regulator - see _be instead
      - id: bcn_pld_3_v_3_reg_t
        type: u2
        doc: |
          temperature at 3v3 regulator - see _be instead
      - id: bcn_pld_sb_1_t
        type: u2
        doc: |
          temperature at scalar board no. 1 - see _be instead
      - id: bcn_pld_sb_2_t
        type: u2
        doc: |
          temperature at scalar board no. 2 - see _be instead
      - id: bcn_pld_vrum_t_1
        type: u2
        doc: |
          vrum temperature 1 - see _be instead
      - id: bcn_pld_vrum_t_2
        type: u2
        doc: |
          vrum temperature 2 - see _be instead
      - id: bcn_pld_pkt_rx_ct
        type: u2
        doc: |
          pld packet counter value for recieved packets
      - id: bcn_pld_pkt_ack_ct
        type: u2
        doc: |
          pld packet counter value for acknowledged packets
      - id: bcn_pld_pkt_nack_ct
        type: u2
        doc: |
          pld packet counter value for not acknowledged packets
      - id: bcn_pld_err_reg_0_0
        type: u2
        doc: |
          pld comm/hk/coil control tasks error flags
      - id: bcn_pld_err_reg_0_1
        type: u2
        doc: |
          pld comm/hk/coil control tasks error flags
      - id: bcn_pld_err_reg_1_0
        type: u2
        doc: |
          science task error flags
      - id: bcn_pld_err_reg_1_1
        type: u2
        doc: |
          science task error flags
      - id: bcn_seq_exec_buf_auto
        type: u2
        doc: |
          buffer id of top level sequence auto
          enumeration values: 0/nvm_small0 1/nvm_small1 2/nvm_small2 3/nvm_small3 4/nvm_small4 5/nvm_small5 6/nvm_small6 7/nvm_small7 8/nvm_small8 9/nvm_small9 10/nvm_small10 11/nvm_small11 12/nvm_small12 13/nvm_small13 14/nvm_small14 15/nvm_small15 16/nvm_small16 17/nvm_small17 18/nvm_small18 19/nvm_small19 20/nvm_small20 21/nvm_small21 22/nvm_small22 23/nvm_small23 24/nvm_small24 25/nvm_small25 26/nvm_small26 27/nvm_small27 28/nvm_small28 29/nvm_small29 30/nvm_small30 31/nvm_small31 32/nvm_small32 33/nvm_small33 34/nvm_small34 35/nvm_small35 36/nvm_small36 37/nvm_small37 38/nvm_small38 39/nvm_small39 40/nvm_small40 41/nvm_small41 42/nvm_small42 43/nvm_small43 44/nvm_small44 45/nvm_small45 46/nvm_small46 47/nvm_small47 48/nvm_small48 49/nvm_small49 50/nvm_small50 51/nvm_small51 52/nvm_small52 53/nvm_small53 54/nvm_small54 55/nvm_small55 56/nvm_small56 57/nvm_small57 58/nvm_small58 59/nvm_small59 60/nvm_small60 61/nvm_small61 62/nvm_small62 63/nvm_small63 64/nvm_small64 65/nvm_small65 66/nvm_small66 67/nvm_small67 68/nvm_small68 69/nvm_small69 70/nvm_small70 71/nvm_small71 72/nvm_small72 73/nvm_small73 74/nvm_small74 75/nvm_small75 76/nvm_small76 77/nvm_small77 78/nvm_small78 79/nvm_small79 80/nvm_large0 81/nvm_large1 82/holding0
      - id: bcn_seq_exec_buf_op_1
        type: u2
        doc: |
          buffer id of top level sequence op1
          enumeration values: 0/nvm_small0 1/nvm_small1 2/nvm_small2 3/nvm_small3 4/nvm_small4 5/nvm_small5 6/nvm_small6 7/nvm_small7 8/nvm_small8 9/nvm_small9 10/nvm_small10 11/nvm_small11 12/nvm_small12 13/nvm_small13 14/nvm_small14 15/nvm_small15 16/nvm_small16 17/nvm_small17 18/nvm_small18 19/nvm_small19 20/nvm_small20 21/nvm_small21 22/nvm_small22 23/nvm_small23 24/nvm_small24 25/nvm_small25 26/nvm_small26 27/nvm_small27 28/nvm_small28 29/nvm_small29 30/nvm_small30 31/nvm_small31 32/nvm_small32 33/nvm_small33 34/nvm_small34 35/nvm_small35 36/nvm_small36 37/nvm_small37 38/nvm_small38 39/nvm_small39 40/nvm_small40 41/nvm_small41 42/nvm_small42 43/nvm_small43 44/nvm_small44 45/nvm_small45 46/nvm_small46 47/nvm_small47 48/nvm_small48 49/nvm_small49 50/nvm_small50 51/nvm_small51 52/nvm_small52 53/nvm_small53 54/nvm_small54 55/nvm_small55 56/nvm_small56 57/nvm_small57 58/nvm_small58 59/nvm_small59 60/nvm_small60 61/nvm_small61 62/nvm_small62 63/nvm_small63 64/nvm_small64 65/nvm_small65 66/nvm_small66 67/nvm_small67 68/nvm_small68 69/nvm_small69 70/nvm_small70 71/nvm_small71 72/nvm_small72 73/nvm_small73 74/nvm_small74 75/nvm_small75 76/nvm_small76 77/nvm_small77 78/nvm_small78 79/nvm_small79 80/nvm_large0 81/nvm_large1 82/holding0
      - id: bcn_seq_exec_buf_op_2
        type: u2
        doc: |
          buffer id of top level sequence op2
          enumeration values: 0/nvm_small0 1/nvm_small1 2/nvm_small2 3/nvm_small3 4/nvm_small4 5/nvm_small5 6/nvm_small6 7/nvm_small7 8/nvm_small8 9/nvm_small9 10/nvm_small10 11/nvm_small11 12/nvm_small12 13/nvm_small13 14/nvm_small14 15/nvm_small15 16/nvm_small16 17/nvm_small17 18/nvm_small18 19/nvm_small19 20/nvm_small20 21/nvm_small21 22/nvm_small22 23/nvm_small23 24/nvm_small24 25/nvm_small25 26/nvm_small26 27/nvm_small27 28/nvm_small28 29/nvm_small29 30/nvm_small30 31/nvm_small31 32/nvm_small32 33/nvm_small33 34/nvm_small34 35/nvm_small35 36/nvm_small36 37/nvm_small37 38/nvm_small38 39/nvm_small39 40/nvm_small40 41/nvm_small41 42/nvm_small42 43/nvm_small43 44/nvm_small44 45/nvm_small45 46/nvm_small46 47/nvm_small47 48/nvm_small48 49/nvm_small49 50/nvm_small50 51/nvm_small51 52/nvm_small52 53/nvm_small53 54/nvm_small54 55/nvm_small55 56/nvm_small56 57/nvm_small57 58/nvm_small58 59/nvm_small59 60/nvm_small60 61/nvm_small61 62/nvm_small62 63/nvm_small63 64/nvm_small64 65/nvm_small65 66/nvm_small66 67/nvm_small67 68/nvm_small68 69/nvm_small69 70/nvm_small70 71/nvm_small71 72/nvm_small72 73/nvm_small73 74/nvm_small74 75/nvm_small75 76/nvm_small76 77/nvm_small77 78/nvm_small78 79/nvm_small79 80/nvm_large0 81/nvm_large1 82/holding0
      - id: bcn_seq_exec_buf_op_3
        type: u2
        doc: |
          buffer id of top level sequence op3
          enumeration values: 0/nvm_small0 1/nvm_small1 2/nvm_small2 3/nvm_small3 4/nvm_small4 5/nvm_small5 6/nvm_small6 7/nvm_small7 8/nvm_small8 9/nvm_small9 10/nvm_small10 11/nvm_small11 12/nvm_small12 13/nvm_small13 14/nvm_small14 15/nvm_small15 16/nvm_small16 17/nvm_small17 18/nvm_small18 19/nvm_small19 20/nvm_small20 21/nvm_small21 22/nvm_small22 23/nvm_small23 24/nvm_small24 25/nvm_small25 26/nvm_small26 27/nvm_small27 28/nvm_small28 29/nvm_small29 30/nvm_small30 31/nvm_small31 32/nvm_small32 33/nvm_small33 34/nvm_small34 35/nvm_small35 36/nvm_small36 37/nvm_small37 38/nvm_small38 39/nvm_small39 40/nvm_small40 41/nvm_small41 42/nvm_small42 43/nvm_small43 44/nvm_small44 45/nvm_small45 46/nvm_small46 47/nvm_small47 48/nvm_small48 49/nvm_small49 50/nvm_small50 51/nvm_small51 52/nvm_small52 53/nvm_small53 54/nvm_small54 55/nvm_small55 56/nvm_small56 57/nvm_small57 58/nvm_small58 59/nvm_small59 60/nvm_small60 61/nvm_small61 62/nvm_small62 63/nvm_small63 64/nvm_small64 65/nvm_small65 66/nvm_small66 67/nvm_small67 68/nvm_small68 69/nvm_small69 70/nvm_small70 71/nvm_small71 72/nvm_small72 73/nvm_small73 74/nvm_small74 75/nvm_small75 76/nvm_small76 77/nvm_small77 78/nvm_small78 79/nvm_small79 80/nvm_large0 81/nvm_large1 82/holding0
      - id: reusable_spare_1
        type: u2
      - id: bcn_store_part_wr_log
        type: u4
        doc: |
          partition write address
      - id: bcn_store_part_rd_log
        type: u4
        doc: |
          partition read address
      - id: bcn_store_part_wr_adcs
        type: u4
        doc: |
          partition write address
      - id: bcn_store_part_rd_adcs
        type: u4
        doc: |
          partition read address
      - id: bcn_store_part_wr_hk
        type: u4
        doc: |
          partition write address
      - id: bcn_store_part_rd_hk
        type: u4
        doc: |
          partition read address
      - id: bcn_store_part_wr_sci
        type: u4
        doc: |
          partition write address
      - id: bcn_store_part_rd_sci
        type: u4
        doc: |
          partition read address
      - id: bcn_fp_resp_ct
        type: u2
        doc: |
          fp response count
      - id: bcn_bat_1_v
        type: u2
        doc: |
          battery 1 voltage
      - id: bcn_bat_2_v
        type: u2
        doc: |
          battery 2 voltage
      - id: bcn_bat_1_t
        type: u2
        doc: |
          battery 1 temp dn
      - id: bcn_bat_2_t
        type: u2
        doc: |
          battery 2 temp dn
      - id: bcn_3p3_i
        type: u2
        doc: |
          3p3 current
      - id: bcn_cdh_t
        type: u2
        doc: |
          cdh temperature
      - id: bcn_sa_1_v
        type: u2
        doc: |
          solar array 1 voltage
      - id: bcn_sa_1_i
        type: u2
        doc: |
          solar array 1 current
      - id: bcn_sa_2_v
        type: u2
        doc: |
          solar array 2 voltage
      - id: bcn_sa_2_i
        type: u2
        doc: |
          solar array 2 current
      - id: bcn_eps_t
        type: u2
        doc: |
          eps board temperature
      - id: bcn_eps_bus_v
        type: u2
        doc: |
          eps bus voltage
      - id: bcn_eps_bus_i
        type: u2
        doc: |
          eps bus current
      - id: bcn_xact_v
        type: u2
        doc: |
          xact voltage
      - id: bcn_xact_i
        type: u2
        doc: |
          xact current
      - id: bcn_uhf_v
        type: u2
        doc: |
          uhf voltage
      - id: bcn_uhf_i
        type: u2
        doc: |
          uhf current
      - id: bcn_sbd_v
        type: u2
        doc: |
          sband voltage
      - id: bcn_sbd_i
        type: u2
        doc: |
          sband current
      - id: bcn_vrum_v
        type: u2
        doc: |
          vrum voltage
      - id: bcn_vrum_i
        type: u2
        doc: |
          vrum current
      - id: bcn_gps_v
        type: u2
        doc: |
          gps voltage
      - id: bcn_gps_i
        type: u2
        doc: |
          gps current
      - id: bcn_boom_v
        type: u2
        doc: |
          boom voltage
      - id: bcn_boom_i
        type: u2
        doc: |
          boom current
      - id: bcn_ifb_t_1
        type: u2
        doc: |
          interface board temperature
      - id: bcn_adcs_rw_1_t
        type: s2
        doc: |
          adcs wheel 1 temp
      - id: bcn_adcs_rw_sp_1
        type: s2
        doc: |
          adcs wheel speed 1
      - id: bcn_adcs_rw_sp_2
        type: s2
        doc: |
          adcs wheel speed 2
      - id: bcn_adcs_rw_sp_3
        type: s2
        doc: |
          adcs wheel speed 3
      - id: bcn_sun_pt_err
        type: u2
        doc: |
          sun point angle error
      - id: bcn_mag_vec_bod_1
        type: s2
        doc: |
          meas mag field body
      - id: bcn_mag_vec_bod_2
        type: s2
        doc: |
          meas mag field body
      - id: bcn_mag_vec_bod_3
        type: s2
        doc: |
          meas mag field body
      - id: bcn_sbd_pa_i
        type: u2
        doc: |
          s-band power amplifier current
      - id: bcn_sbd_pa_t
        type: u2
        doc: |
          s-band power amplifier temp
      - id: bcn_cmd_fail_code
        type: u1
        doc: |
          cdh command failure code
          enumeration values: 0/success 1/mode 2/arm 3/source 4/opcode 5/method 6/length 7/range 8/checksum 9/pkt_type
      - id: bcn_vrum_cmd_rej_rsn
        type: u1
        doc: |
          vrum packet reject reason
      - id: bcn_clt_hr_left
        type: u1
        doc: |
          hours until clt trigger
      - id: bcn_clt_ct
        type: u1
        doc: |
          clt count
      - id: bcn_sys_mode
        type: u1
        doc: |
          cdh system mode
          enumeration values: 0/phoenix 1/safe 2/science
      - id: bcn_uhf_alive
        type: u1
        doc: |
          uhf aliveness state
      - id: reusable_spare_2
        type: b2
      - id: bcn_pld_pwr_cyc_vrum
        type: b1
        doc: |
          vrum power cycle request state
          enumeration values: 0/inactive 1/active
      - id: bcn_pld_pwr_off_vrum
        type: b1
        doc: |
          vrum power off request state
          enumeration values: 0/inactive 1/active
      - id: bcn_pld_stat_st_vrum
        type: b1
        doc: |
          vrum status message state
          enumeration values: 0/dis 1/ena
      - id: bcn_pld_time_st_vrum
        type: b1
        doc: |
          vrum time message state
          enumeration values: 0/dis 1/ena
      - id: bcn_pld_alive_st_vrum
        type: b2
        doc: |
          vrum aliveness state
          enumeration values: 0/off 1/dead 2/alive
      - id: reusable_spare_3
        type: b2
      - id: bcn_pld_pwr_cyc_boom
        type: b1
        doc: |
          boom power cycle request state
          enumeration values: 0/inactive 1/active
      - id: bcn_pld_pwr_off_boom
        type: b1
        doc: |
          boom power off request state
          enumeration values: 0/inactive 1/active
      - id: bcn_pld_stat_st_boom
        type: b1
        doc: |
          boom status message state
          enumeration values: 0/dis 1/ena
      - id: bcn_pld_time_st_boom
        type: b1
        doc: |
          boom time message state
          enumeration values: 0/dis 1/ena
      - id: bcn_pld_alive_st_boom
        type: b2
        doc: |
          boom aliveness state
          enumeration values: 0/off 1/dead 2/alive
      - id: bcn_uhf_t
        type: s1
        doc: |
          uhf temperature
      - id: bcn_seq_state_auto
        type: u1
        doc: |
          state of the sequence engine auto
          enumeration values: 0/idle 1/active 2/suspend 3/pause 4/stale
      - id: bcn_seq_state_op_1
        type: u1
        doc: |
          state of the sequence engine op1
          enumeration values: 0/idle 1/active 2/suspend 3/pause 4/stale
      - id: bcn_seq_state_op_2
        type: u1
        doc: |
          state of the sequence engine op2
          enumeration values: 0/idle 1/active 2/suspend 3/pause 4/stale
      - id: bcn_seq_state_op_3
        type: u1
        doc: |
          state of the sequence engine op3
          enumeration values: 0/idle 1/active 2/suspend 3/pause 4/stale
      - id: reusable_spare_4
        type: b1
      - id: reusable_spare_5
        type: b1
      - id: reusable_spare_6
        type: b1
      - id: reusable_spare_7
        type: b1
      - id: reusable_spare_8
        type: b1
      - id: reusable_spare_9
        type: b1
      - id: bcn_htr_pwr_state_bat_2
        type: b1
        doc: |
          heater power states batt2
          enumeration values: 0/off 1/on
      - id: bcn_htr_pwr_state_bat_1
        type: b1
        doc: |
          heater power states batt1
          enumeration values: 0/off 1/on
      - id: reusable_spare_10
        type: b1
      - id: bcn_pwr_state_boom
        type: b1
        doc: |
          peripheral power states boom
          enumeration values: 0/off 1/on
      - id: bcn_pwr_state_gps
        type: b1
        doc: |
          peripheral power states gps
          enumeration values: 0/off 1/on
      - id: bcn_pwr_state_unused
        type: b1
        doc: |
          peripheral power states unused
          enumeration values: 0/off 1/on
      - id: bcn_pwr_state_vrum
        type: b1
        doc: |
          peripheral power states vrum
          enumeration values: 0/off 1/on
      - id: bcn_pwr_state_sbd
        type: b1
        doc: |
          peripheral power states sband
          enumeration values: 0/off 1/on
      - id: bcn_pwr_state_uhf
        type: b1
        doc: |
          peripheral power states uhf
          enumeration values: 0/off 1/on
      - id: bcn_pwr_state_adcs
        type: b1
        doc: |
          peripheral power states adcs
          enumeration values: 0/off 1/on
      - id: bcn_fp_task_state
        type: u1
        doc: |
          fp task state
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_23
        type: b2
        doc: |
          wp state wp23
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_22
        type: b2
        doc: |
          wp state wp22 - sbd on 15min -> sbd off (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_21
        type: b2
        doc: |
          wp state wp21 - sbd ov -> sbd off (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_20
        type: b2
        doc: |
          wp state wp20 - 3.3v ov -> cdh reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_19
        type: b2
        doc: |
          wp state wp19 - uhf ov -> uhf reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_18
        type: b2
        doc: |
          wp state wp18 - 1.0v oc -> cdh reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_17
        type: b2
        doc: |
          wp state wp17 - 1.8v oc -> cdh reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_16
        type: b2
        doc: |
          wp state wp16 - 3.3v oc -> cdh reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_15
        type: b2
        doc: |
          wp state wp15 - no pld-sc2 lck -> sc2 reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_14
        type: b2
        doc: |
          wp state wp14 - no pld-sc1 lck -> sc1 reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_13
        type: b2
        doc: |
          wp state wp13 - no pld-st2 sol -> st2 reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_12
        type: b2
        doc: |
          wp state wp12 - no pld-st1 sol -> st1 reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_11
        type: b2
        doc: |
          wp state wp11 - no pld hb -> pld off (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_10
        type: b2
        doc: |
          wp state wp10 - pld ifb uv -> pld off (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_9
        type: b2
        doc: |
          wp state wp9 - pld uv -> pld off (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_8
        type: b2
        doc: |
          wp state wp8 - pld ifb oc -> pld off (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_7
        type: b2
        doc: |
          wp state wp7 - pld oc -> pld off (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_6
        type: b2
        doc: |
          wp state wp6 - pld ifb ov -> pld off (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_5
        type: b2
        doc: |
          wp state wp5 - pld ov -> pld off (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_4
        type: b2
        doc: |
          wp state wp4 - sbd oc -> sbd off (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_3
        type: b2
        doc: |
          wp state wp3 - uhf oc -> uhf reset (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_2
        type: b2
        doc: |
          wp state wp2 - xact sun_point -> cdh safe (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_1
        type: b2
        doc: |
          wp state wp1 - xact oc -> xact reset (dflt ena)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_fp_state_wp_0
        type: b2
        doc: |
          wp state wp0 - bus oc -> cdh reset (dflt dis; ena in nom)
          enumeration values: 0/dis 1/passive 2/ena
      - id: bcn_adcs_alive
        type: u1
        doc: |
          adcs alive state of communication
          enumeration values: 0/off 1/dead 2/alive
      - id: bcn_adcs_att_vld
        type: b1
        doc: |
          adcs attitude valid
          enumeration values: 0/no 1/yes
      - id: bcn_adcs_ref_vld
        type: b1
        doc: |
          adcs refs valid
          enumeration values: 0/no 1/yes
      - id: bcn_adcs_time_vld
        type: b1
        doc: |
          adcs time valid
          enumeration values: 0/no 1/yes
      - id: bcn_adcs_mode
        type: b1
        doc: |
          adcs mode
          enumeration values: 0/sun_point 1/fine_ref_point
      - id: bcn_adcs_rec_sun_pt
        type: b1
        doc: |
          adcs recommend sun point
          enumeration values: 0/no 1/yes
      - id: bcn_adcs_sun_pt_state
        type: b3
        doc: |
          adcs sun point state
          enumeration values: 0/na 2/search_init 3/searching 4/waiting 5/converging 6/on_sun 7/not_active
      - id: bcn_adcs_cmd_acc
        type: u1
        doc: |
          adcs command accept count
      - id: bcn_adcs_cmd_fail
        type: u1
        doc: |
          adcs command reject count
      - id: bcn_adcs_cmd_stat
        type: u1
        doc: |
          adcs command status
          enumeration values: 0/ok 1/bad_apid 2/bad_opcode 3/bad_data 7/no_cmd_data 8/cmd_srvc_overrun 9/cmd_apid_overrun 12/tables_busy 13/flash_not_armed 14/thrusters_dis 15/att_err_too_high 16/async_refused
      - id: padding
        type: u2
      - id: padding2
        type: u1
      - id: checksum
        type: u4
        
  cosmo_beacon_t:
    seq:
      - id: beacon_t
        type: beacon_t
