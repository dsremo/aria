meta:
  id: hadesr
  title: AMSAT-EA - HADES-R, HADES-ICM, MARIA-G, and UNNE-1 Telemetry Decoder
  endian: le
  bit-endian: be

doc: |
  :field type: cubesat_frame.first_header.type
  :field address: cubesat_frame.first_header.address
  :field sclock: cubesat_frame.metadata.sclock
  :field peaksignal: cubesat_frame.metadata.peaksignal
  :field modasignal: cubesat_frame.metadata.modasignal
  :field lastcmdsignal: cubesat_frame.metadata.lastcmdsignal
  :field lastcmdnoise: cubesat_frame.metadata.lastcmdnoise
  :field spi: cubesat_frame.metadata.spi
  :field spa: cubesat_frame.metadata.spa
  :field spb: cubesat_frame.metadata.spb
  :field spc: cubesat_frame.metadata.spc
  :field spd: cubesat_frame.metadata.spd
  :field vbus1: cubesat_frame.metadata.vbus1
  :field vbus2: cubesat_frame.metadata.vbus2
  :field vbus3: cubesat_frame.metadata.vbus3
  :field vbat1: cubesat_frame.metadata.vbat1
  :field vbat2: cubesat_frame.metadata.vbat2
  :field vbus1_vbat1: cubesat_frame.metadata.vbus1_vbat1
  :field vbus3_vbus2: cubesat_frame.metadata.vbus3_vbus2
  :field vcpu: cubesat_frame.metadata.vcpu
  :field icpu: cubesat_frame.metadata.icpu
  :field ipl: cubesat_frame.metadata.ipl
  :field ibat: cubesat_frame.metadata.ibat
  :field tpa: cubesat_frame.metadata.tpa
  :field tpb: cubesat_frame.metadata.tpb
  :field tpc: cubesat_frame.metadata.tpc
  :field tpd: cubesat_frame.metadata.tpd
  :field ttx: cubesat_frame.metadata.ttx
  :field ttx2: cubesat_frame.metadata.ttx2
  :field trx: cubesat_frame.metadata.trx
  :field tcpu: cubesat_frame.metadata.tcpu
  :field uptime: cubesat_frame.metadata.uptime
  :field nrun: cubesat_frame.metadata.nrun
  :field npayload: cubesat_frame.metadata.npayload
  :field nwire: cubesat_frame.metadata.nwire
  :field ntransponder: cubesat_frame.metadata.ntransponder
  :field ntasksnotexecuted: cubesat_frame.metadata.ntasksnotexecuted
  :field antennadeployed: cubesat_frame.metadata.antennadeployed
  :field nexteepromerrors: cubesat_frame.metadata.nexteepromerrors
  :field last_failed_task_id: cubesat_frame.metadata.last_failed_task_id
  :field messaging_enabled: cubesat_frame.metadata.messaging_enabled
  :field strfwd0_id: cubesat_frame.metadata.strfwd0_id
  :field strfwd1_key: cubesat_frame.metadata.strfwd1_key
  :field strfwd2_value: cubesat_frame.metadata.strfwd2_value
  :field strfwd3_num_tcmds: cubesat_frame.metadata.strfwd3_num_tcmds
  :field npayloadfails: cubesat_frame.metadata.npayloadfails
  :field last_reset_cause: cubesat_frame.metadata.last_reset_cause
  :field bate_battery: cubesat_frame.metadata.bate_battery
  :field mote_transponder: cubesat_frame.metadata.mote_transponder
  :field minicpu: cubesat_frame.metadata.minicpu
  :field minipl: cubesat_frame.metadata.minipl
  :field maxibat: cubesat_frame.metadata.maxibat
  :field maxicpu: cubesat_frame.metadata.maxicpu
  :field ibat_tx_off_charging: cubesat_frame.metadata.ibat_tx_off_charging
  :field ibat_tx_off_discharging: cubesat_frame.metadata.ibat_tx_off_discharging
  :field ibat_tx_low_power_charging: cubesat_frame.metadata.ibat_tx_low_power_charging
  :field ibat_tx_low_power_discharging: cubesat_frame.metadata.ibat_tx_low_power_discharging
  :field ibat_tx_high_power_charging: cubesat_frame.metadata.ibat_tx_high_power_charging
  :field ibat_tx_high_power_discharging: cubesat_frame.metadata.ibat_tx_high_power_discharging
  :field minvbus1: cubesat_frame.metadata.minvbus1
  :field minvbat1: cubesat_frame.metadata.minvbat1
  :field minvcpu: cubesat_frame.metadata.minvcpu
  :field minvbus2: cubesat_frame.metadata.minvbus2
  :field minvbus3: cubesat_frame.metadata.minvbus3
  :field minvbat2: cubesat_frame.metadata.minvbat2
  :field minibat: cubesat_frame.metadata.minibat
  :field maxvbus1: cubesat_frame.metadata.maxvbus1
  :field maxvbat1: cubesat_frame.metadata.maxvbat1
  :field maxvcpu: cubesat_frame.metadata.maxvcpu
  :field maxvbus2: cubesat_frame.metadata.maxvbus2
  :field maxvbus3: cubesat_frame.metadata.maxvbus3
  :field maxvbat2: cubesat_frame.metadata.maxvbat2
  :field maxipl: cubesat_frame.metadata.maxipl
  :field mintpa: cubesat_frame.metadata.mintpa
  :field mintpb: cubesat_frame.metadata.mintpb
  :field mintpc: cubesat_frame.metadata.mintpc
  :field mintpd: cubesat_frame.metadata.mintpd
  :field minttx: cubesat_frame.metadata.minttx
  :field minttx2: cubesat_frame.metadata.minttx2
  :field mintrx: cubesat_frame.metadata.mintrx
  :field mintcpu: cubesat_frame.metadata.mintcpu
  :field maxtpa: cubesat_frame.metadata.maxtpa
  :field maxtpb: cubesat_frame.metadata.maxtpb
  :field maxtpc: cubesat_frame.metadata.maxtpc
  :field maxtpd: cubesat_frame.metadata.maxtpd
  :field maxteps: cubesat_frame.metadata.maxteps
  :field maxttx: cubesat_frame.metadata.maxttx
  :field maxttx2: cubesat_frame.metadata.maxttx2
  :field maxtrx: cubesat_frame.metadata.maxtrx
  :field maxtcpu: cubesat_frame.metadata.maxtcpu
  :field vloc: cubesat_frame.metadata.vloc
  :field v1: cubesat_frame.metadata.v1
  :field i1: cubesat_frame.metadata.i1
  :field i1pk: cubesat_frame.metadata.i1pk
  :field r1: cubesat_frame.metadata.r1
  :field v2oc: cubesat_frame.metadata.v2oc
  :field v2: cubesat_frame.metadata.v2
  :field r2: cubesat_frame.metadata.r2
  :field t0: cubesat_frame.metadata.t0
  :field td: cubesat_frame.metadata.td
  :field state_begin: cubesat_frame.metadata.state_begin
  :field state_end: cubesat_frame.metadata.state_end
  :field state_now: cubesat_frame.metadata.state_now
  :field enable: cubesat_frame.metadata.enable
  :field counter: cubesat_frame.metadata.counter
  :field tmp: cubesat_frame.metadata.tmp
  :field v0: cubesat_frame.metadata.v0
  :field i0: cubesat_frame.metadata.i0
  :field p0: cubesat_frame.metadata.p0
  :field vp0: cubesat_frame.metadata.vp0
  :field ip0: cubesat_frame.metadata.ip0
  :field pp0: cubesat_frame.metadata.pp0
  :field p1: cubesat_frame.metadata.p1
  :field vp1: cubesat_frame.metadata.vp1
  :field ip1: cubesat_frame.metadata.ip1
  :field pp1: cubesat_frame.metadata.pp1
  :field i2: cubesat_frame.metadata.i2
  :field p2: cubesat_frame.metadata.p2
  :field vp2: cubesat_frame.metadata.vp2
  :field ip2: cubesat_frame.metadata.ip2
  :field pp2: cubesat_frame.metadata.pp2
  :field v3: cubesat_frame.metadata.v3
  :field i3: cubesat_frame.metadata.i3
  :field p3: cubesat_frame.metadata.p3
  :field vp3: cubesat_frame.metadata.vp3
  :field ip3: cubesat_frame.metadata.ip3
  :field pp3: cubesat_frame.metadata.pp3
  :field v4: cubesat_frame.metadata.v4
  :field i4: cubesat_frame.metadata.i4
  :field p4: cubesat_frame.metadata.p4
  :field vp4: cubesat_frame.metadata.vp4
  :field ip4: cubesat_frame.metadata.ip4
  :field pp4: cubesat_frame.metadata.pp4
  :field v5: cubesat_frame.metadata.v5
  :field i5: cubesat_frame.metadata.i5
  :field p5: cubesat_frame.metadata.p5
  :field vp5: cubesat_frame.metadata.vp5
  :field ip5: cubesat_frame.metadata.ip5
  :field pp5: cubesat_frame.metadata.pp5
  :field v6: cubesat_frame.metadata.v6
  :field i6: cubesat_frame.metadata.i6
  :field p6: cubesat_frame.metadata.p6
  :field vp6: cubesat_frame.metadata.vp6
  :field ip6: cubesat_frame.metadata.ip6
  :field pp6: cubesat_frame.metadata.pp6
  :field v7: cubesat_frame.metadata.v7
  :field i7: cubesat_frame.metadata.i7
  :field p7: cubesat_frame.metadata.p7
  :field vp7: cubesat_frame.metadata.vp7
  :field ip7: cubesat_frame.metadata.ip7
  :field pp7: cubesat_frame.metadata.pp7
  :field v8: cubesat_frame.metadata.v8
  :field i8: cubesat_frame.metadata.i8
  :field p8: cubesat_frame.metadata.p8
  :field vp8: cubesat_frame.metadata.vp8
  :field ip8: cubesat_frame.metadata.ip8
  :field pp8: cubesat_frame.metadata.pp8
  :field v9: cubesat_frame.metadata.v9
  :field i9: cubesat_frame.metadata.i9
  :field p9: cubesat_frame.metadata.p9
  :field vp9: cubesat_frame.metadata.vp9
  :field ip9: cubesat_frame.metadata.ip9
  :field pp9: cubesat_frame.metadata.pp9
  :field experiment_clock: cubesat_frame.metadata.experiment_clock
  :field experiment_id: cubesat_frame.metadata.experiment_id
  :field frame_number: cubesat_frame.metadata.frame_number

seq:
  - id: cubesat_frame
    type: cubesat_frame
    doc-ref: https://www.amsat-ea.org/app/download/13945587/AMSAT+EA+-+Transmissions+description+for+MARIA-G_UNNE-1_HADES-R_HADES-ICM.pdf

types:
  cubesat_frame:
    seq:
      - id: first_header
        type: first_header
      - id: metadata
        type:
          switch-on: first_header.type
          cases:
            0x1: power_frame
            0x2: temp_frame
            0x3: status_frame
            0x4: powerstats_frame
            0x5: tempstats_frame
            0x6: sunsensors_frame
            0x7: icmgamemsg_frame
            0x8: deploy_frame
            0x9: extpowerstats_frame
            0xA: nebrijagame_frame
            0xB: fraunhoferexp_frame
            0xC: ephemeris_frame
            0xE: timeseries_frame
            0xF: experiment_frame

  first_header:
    seq:
      - id: type
        type: b4
        valid:
          any-of: [0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0x9, 0xA, 0xB, 0xC, 0xE, 0xF]
      - id: address
        type: b4
        doc: |
          0x2 if the satellite is HADES-ICM,
          0xB if the satellite is MARIA-G,
          0xC if it is UNNE-1, or
          0xD if it is HADES-R
        valid:
          any-of: [0xD]

  power_frame:
    seq:
      - id: sclock
        type: u4
      - id: spa_tmp
        type: u1
      - id: spb_tmp
        type: u1
      - id: spc_tmp
        type: u1
      - id: spd_tmp
        type: u1
      - id: spi_tmp
        type: u2
      - id: vbusadc_vbatadc_hi_tmp
        type: u2
      - id: vbatadc_lo_vcpuadc_hi_tmp
        type: u2
      - id: vcpuadc_lo_vbus2_tmp
        type: u2
      - id: vbus3_vbat2_hi_tmp
        type: u2
      - id: vbat2_lo_ibat_hi_tmp
        type: u2
      - id: ibat_lo_icpu_hi_tmp
        type: u2
      - id: icpu_lo_ipl_tmp
        type: u2
      - id: peaksignal
        type: u1
      - id: modasignal
        type: u1
      - id: lastcmdsignal
        type: u1
      - id: lastcmdnoise
        type: u1

    instances:
      days:
        value: sclock / 86400
      hours:
        value: (sclock % 86400)/3600
      minutes:
        value: (sclock % 3600)/60
      seconds:
        value: sclock % 60
      spi:
          value: ((spi_tmp << 1))
      spa:
          value: ((spa_tmp << 1))
      spb:
          value: ((spb_tmp << 1))
      spc:
          value: ((spc_tmp << 1))
      spd:
          value: ((spd_tmp << 1))
      vbus1:
          value: ((vbusadc_vbatadc_hi_tmp >> 4)) * 1400 / 1000
      vbus2:
          value: ((vcpuadc_lo_vbus2_tmp & 0x0fff)) * 4
      vbus3:
          value: ((vbus3_vbat2_hi_tmp >> 4)) * 4
      vbat1:
          value: ((vbatadc_lo_vcpuadc_hi_tmp << 8 ) & 0x0f00 | (vbatadc_lo_vcpuadc_hi_tmp >> 8 ) & 0x0fff )  * 1400 / 1000
      vbat2:
          value: ((vbus3_vbat2_hi_tmp << 8) & 0x0f00 | vbat2_lo_ibat_hi_tmp >> 8) * 4
      vbus1_vbat1:
          value: ((vbus1 - vbat1))
      vbus3_vbus2:
          value: ((vbus3 - vbus2))
      vcpu:
          value: 1210*4096/((vbatadc_lo_vcpuadc_hi_tmp << 4 ) & 0x0ff0 | vcpuadc_lo_vbus2_tmp >> 12 )
      icpu:
          value: (( ibat_lo_icpu_hi_tmp << 4) & 0x0ff0 | icpu_lo_ipl_tmp >> 12)
      ipl:
          value: (( icpu_lo_ipl_tmp & 0x0fff))
      ibat:
        value: "((vbat2_lo_ibat_hi_tmp << 8) & 0x0f00 | (ibat_lo_icpu_hi_tmp >> 8) & 0x0fff) > 2047 ? ((vbat2_lo_ibat_hi_tmp << 8) & 0x0f00 | (ibat_lo_icpu_hi_tmp >> 8) & 0x0fff) - 4096 : ((vbat2_lo_ibat_hi_tmp << 8) & 0x0f00 | (ibat_lo_icpu_hi_tmp >> 8) & 0x0fff)"

  temp_frame:
    seq:
      - id: sclock
        type: u4
      - id: tpa_tmp
        type: u1
      - id: tpb_tmp
        type: u1
      - id: tpc_tmp
        type: u1
      - id: tpd_tmp
        type: u1
      - id: tpe_tmp
        type: u1
      - id: teps_tmp
        type: u1
      - id: ttx_tmp
        type: u1
      - id: ttx2_tmp
        type: u1
      - id: trx_tmp
        type: u1
      - id: tcpu_tmp
        type: u1

    instances:
      days:
        value: sclock / 86400
      hours:
        value: (sclock % 86400)/3600
      minutes:
        value: (sclock % 3600)/60
      seconds:
        value: sclock % 60
      tpa:
        value: (tpa_tmp/2.0) - 40.0
      tpb:
        value: (tpb_tmp/2.0) - 40.0
      tpc:
        value: (tpc_tmp/2.0) - 40.0
      tpd:
        value: (tpd_tmp/2.0) - 40.0
      teps:
        value: (teps_tmp/2.0) - 40.0
      ttx:
        value: (ttx_tmp/2.0) - 40.0
      ttx2:
        value: (ttx2_tmp/2.0) - 40.0
      trx:
        value: (trx_tmp/2.0) - 40.0
      tcpu:
        value: (tcpu_tmp/2.0) - 40.0

  status_frame:
    seq:
      - id: sclock
        type: u4
      - id: uptime
        type: u4
      - id: nrun
        type: u2
      - id: npayload
        type: u1
      - id: nwire
        type: u1
      - id: ntransponder
        type: u1
      - id: npayloadfails_lstrst_tmp
        type: u1
      - id: bate_mote_tmp
        type: u1
      - id: ntasksnotexecuted
        type: u1
      - id: antennadeployed
        type: u1
      - id: nexteepromerrors
        type: u1
      - id: last_failed_task_id
        type: u1
      - id: messaging_enabled
        type: u1
      - id: strfwd0_id
        type: u1
      - id: strfwd1_key
        type: u2
      - id: strfwd2_value
        type: u2
      - id: strfwd3_num_tcmds
        type: u1

    instances:
      days:
        value: sclock / 86400
      hours:
        value: (sclock % 86400)/3600
      minutes:
        value: (sclock % 3600)/60
      seconds:
        value: sclock % 60
      daysup:
        value: uptime / 86400
      hoursup:
        value: (uptime % 86400)/3600
      minutesup:
        value: (uptime % 3600)/60
      secondsup:
        value: uptime % 60
      npayloadfails:
          value: ((npayloadfails_lstrst_tmp >> 4))
      last_reset_cause:
          value: (( npayloadfails_lstrst_tmp & 0x0f ))
      bate_battery:
          value: (( bate_mote_tmp >> 4 ))
      mote_transponder:
          value: (( bate_mote_tmp & 0x0f ))

  powerstats_frame:
    seq:
      - id: sclock
        type: u4
      - id: minvbusadc_vbatadc_hi_tmp
        type: u2
      - id: minvbatadc_lo_vcpuadc_hi_tmp
        type: u2
      - id: minvcpuadc_lo_free_tmp
        type: u1
      - id: minvbus2_tmp
        type: u1
      - id: minvbus3_tmp
        type: u1
      - id: minvbat2_tmp
        type: u1
      - id: minibat_tmp
        type: u1
      - id: minicpu
        type: u1
      - id: minipl
        type: u1
      - id: maxvbusadc_vbatadc_hi_tmp
        type: u2
      - id: maxvbatadc_lo_vcpuadc_hi_tmp
        type: u2
      - id: maxvcpuadc_lo_free_tmp
        type: u1
      - id: maxvbus2_tmp
        type: u1
      - id: maxvbus3_tmp
        type: u1
      - id: maxvbat2_tmp
        type: u1
      - id: maxibat
        type: u1
      - id: maxicpu
        type: u1
      - id: maxipl_tmp
        type: u1
      - id: ibat_tx_off_charging
        type: u1
      - id: ibat_tx_off_discharging
        type: u1
      - id: ibat_tx_low_power_charging
        type: u1
      - id: ibat_tx_low_power_discharging
        type: u1
      - id: ibat_tx_high_power_charging
        type: u1
      - id: ibat_tx_high_power_discharging
        type: u1

    instances:
      days:
        value: sclock / 86400
      hours:
        value: (sclock % 86400)/3600
      minutes:
        value: (sclock % 3600)/60
      seconds:
        value: sclock % 60
      minvbus1:
        value: 1400*((minvbusadc_vbatadc_hi_tmp >> 4)) / 1000
      minvbat1:
        value: 1400*(((minvbusadc_vbatadc_hi_tmp << 8) & 0x0f00) | ((minvbatadc_lo_vcpuadc_hi_tmp >> 8) & 0x00ff))/1000
      minvcpu:
        #value: "minvcpuadc_lo_free_tmp > 4 ? 1210*4096/(((minvbatadc_lo_vcpuadc_hi_tmp << 4) & 0x0ff0) | 1) : 1210*4096/(((minvbatadc_lo_vcpuadc_hi_tmp << 4) & 0x0ff0))"
        value: 1210 * 4096 / ((minvbatadc_lo_vcpuadc_hi_tmp << 4) & 0x0ff0 | (minvcpuadc_lo_free_tmp >> 4))
      minvbus2:
        value: minvbus2_tmp*16*4
      minvbus3:
        value: minvbus3_tmp*16*4
      minvbat2:
        value: minvbat2_tmp*16*4
      minibat:
        value: minibat_tmp*-1
      maxvbus1:
        value: 1400*(maxvbusadc_vbatadc_hi_tmp >> 4)/1000
      maxvbat1:
        value: 1400*(((maxvbusadc_vbatadc_hi_tmp << 8) & 0x0f00) | ((maxvbatadc_lo_vcpuadc_hi_tmp >> 8) & 0x00ff))/1000
      maxvcpu:
        value: 1210 * 4096 / ((maxvbatadc_lo_vcpuadc_hi_tmp << 4) & 0x0ff0 | (maxvcpuadc_lo_free_tmp >> 4))
      maxvbus2:
        value: maxvbus2_tmp*16*4
      maxvbus3:
        value: maxvbus3_tmp*16*4
      maxvbat2:
        value: maxvbat2_tmp*16*4
      maxipl:
        value: maxipl_tmp << 2

  tempstats_frame:
    seq:
      - id: sclock
        type: u4
      - id: mintpa_tmp
        type: u1
      - id: mintpb_tmp
        type: u1
      - id: mintpc_tmp
        type: u1
      - id: mintpd_tmp
        type: u1
      - id: mintpe
        type: u1
      - id: minteps_tmp
        type: u1
      - id: minttx_tmp
        type: u1
      - id: minttx2_tmp
        type: u1
      - id: mintrx_tmp
        type: u1
      - id: mintcpu_tmp
        type: u1
      - id: maxtpa_tmp
        type: u1
      - id: maxtpb_tmp
        type: u1
      - id: maxtpc_tmp
        type: u1
      - id: maxtpd_tmp
        type: u1
      - id:  maxtpe
        type: u1
      - id: maxteps_tmp
        type: u1
      - id: maxttx_tmp
        type: u1
      - id: maxttx2_tmp
        type: u1
      - id: maxtrx_tmp
        type: u1
      - id: maxtcpu_tmp
        type: u1

    instances:
      days:
        value: sclock / 86400
      hours:
        value: (sclock % 86400)/3600
      minutes:
        value: (sclock % 3600)/60
      seconds:
        value: sclock % 60
      mintpa:
          value: (mintpa_tmp/2.0) - 40.0
      mintpb:
          value: (mintpb_tmp/2.0) - 40.0
      mintpc:
          value: (mintpc_tmp/2.0) - 40.0
      mintpd:
          value: (mintpd_tmp/2.0) - 40.0
      minteps:
          value: (minteps_tmp/2.0) - 40.0
      minttx:
          value: (minttx_tmp/2.0) - 40.0
      minttx2:
          value: (minttx2_tmp/2.0) - 40.0
      mintrx:
          value: (mintrx_tmp/2.0) - 40.0
      mintcpu:
          value: (mintcpu_tmp/2.0) - 40.0
      maxtpa:
          value: (maxtpa_tmp/2.0) - 40.0
      maxtpb:
          value: (maxtpb_tmp/2.0) - 40.0
      maxtpc:
          value: (maxtpc_tmp/2.0) - 40.0
      maxtpd:
          value: (maxtpd_tmp/2.0) - 40.0
      maxteps:
          value: (maxteps_tmp/2.0) - 40.0
      maxttx:
          value: (maxttx_tmp/2.0) - 40.0
      maxttx2:
          value: (maxttx2_tmp/2.0) - 40.0
      maxtrx:
          value: (maxtrx_tmp/2.0) - 40.0
      maxtcpu:
          value: (maxtcpu_tmp/2.0) - 40.0

  sunsensors_frame:
    seq:
      - id: no_value
        size: 0

  icmgamemsg_frame:
    seq:
      - id: sclock
        type: u4
      - id: msg_num
        type: u1
      - id: message
        type: str
        encoding: UTF-8
        size-eos: true

    instances:
      days:
        value: sclock / 86400
      hours:
        value: (sclock % 86400)/3600
      minutes:
        value: (sclock % 3600)/60
      seconds:
        value: sclock % 60

  deploy_frame:
    seq:
      - id: vloc
        type: u2
      - id: v1
        type: u2
      - id: i1
        type: u2
      - id: i1pk
        type: u2
      - id: r1
        type: u2
      - id: v2oc
        type: u2
      - id: v2
        type: u2
      - id: r2
        type: u2
      - id: t0
        type: u4
      - id: td
        type: u2
      - id: state_begin
        type: u1
      - id: state_end
        type: u1
      - id: state_now
        type: u1
      - id: enable
        type: u1
      - id: counter
        type: u1
      - id: tmp
        type: u1

  extpowerstats_frame:
    seq:
      - id: v0
        type: u2
      - id: i0
        type: u2
      - id: p0
        type: u2
      - id: vp0
        type: u2
      - id: ip0
        type: u2
      - id: pp0
        type: u2
      - id: v1
        type: u2
      - id: i1
        type: u2
      - id: p1
        type: u2
      - id: vp1
        type: u2
      - id: ip1
        type: u2
      - id: pp1
        type: u2
      - id: v2
        type: u2
      - id: i2
        type: u2
      - id: p2
        type: u2
      - id: vp2
        type: u2
      - id: ip2
        type: u2
      - id: pp2
        type: u2
      - id: v3
        type: u2
      - id: i3
        type: u2
      - id: p3
        type: u2
      - id: vp3
        type: u2
      - id: ip3
        type: u2
      - id: pp3
        type: u2
      - id: v4
        type: u2
      - id: i4
        type: u2
      - id: p4
        type: u2
      - id: vp4
        type: u2
      - id: ip4
        type: u2
      - id: pp4
        type: u2
      - id: v5
        type: u2
      - id: i5
        type: u2
      - id: p5
        type: u2
      - id: vp5
        type: u2
      - id: ip5
        type: u2
      - id: pp5
        type: u2
      - id: v6
        type: u2
      - id: i6
        type: u2
      - id: p6
        type: u2
      - id: vp6
        type: u2
      - id: ip6
        type: u2
      - id: pp6
        type: u2
      - id: v7
        type: u2
      - id: i7
        type: u2
      - id: p7
        type: u2
      - id: vp7
        type: u2
      - id: ip7
        type: u2
      - id: pp7
        type: u2
      - id: v8
        type: u2
      - id: i8
        type: u2
      - id: p8
        type: u2
      - id: vp8
        type: u2
      - id: ip8
        type: u2
      - id: pp8
        type: u2
      - id: v9
        type: u2
      - id: i9
        type: u2
      - id: p9
        type: u2
      - id: vp9
        type: u2
      - id: ip9
        type: u2
      - id: pp9
        type: u2

  nebrijagame_frame:
    seq:
      - id: no_value
        size: 0

  fraunhoferexp_frame:
    seq:
      - id: no_value
        size: 0

  ephemeris_frame:
    seq:
      - id: time_utc
        type: u4
      - id: adr
        type: u2
      - id: ful
        type: u4
      - id: fdl
        type: u4
      - id: tle_epoch
        type: u4
      - id: tle_xndt2o
        type: u4
      - id: tle_xndd6o
        type: u4
      - id: tle_bstar
        type: u4
      - id: tle_xincl
        type: u4
      - id: tle_xnodeo
        type: u4
      - id: tle_eo
        type: u4
      - id: tle_omegao
        type: u4
      - id: tle_xmo
        type: u4
      - id: tle_xno
        type: u4
      - id: lat
        type: u2
      - id: lon
        type: u2
      - id: alt
        type: u2
      - id: cnt
        type: u1

  timeseries_frame:
    seq:
      - id: no_value
        size: 0

  experiment_frame:
    seq:
      - id: experiment_clock
        type: u4
      - id: experiment_id
        type: u1
      - id: frame_number
        type: u1
      - id: experiment_data
        size-eos: true
