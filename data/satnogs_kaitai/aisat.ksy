---
meta:
  id: aisat
  title: AISat CW Beacon Decoder
  endian: be
doc-ref: ""
# 2025-02-14, DL7NDR
doc: |
  :field callsign: callsign
  :field beacon_type: beacon_types.check
  :field volts: beacon_types.type_check.volts
  :field dbm: beacon_types.type_check.dbm
  :field pa: beacon_types.type_check.pa
  :field pcb: beacon_types.type_check.pcb
  :field beacon: beacon_types.type_check.beacon

seq:
  - id: callsign
    type: str
    size: 6
    encoding: ASCII
    valid: '"dp0ais"' # 64 70 30 61 69 73

  - id: beacon_types
    type: beacon_types_t

types:
  beacon_types_t:
    seq:
      - id: type_check
        type:
          switch-on: check
          cases:
            0x01: volts
            0x02: dbm
            0x03: pa
            0x04: pcb

    instances:
      check:
        type: u1


  volts:
   seq:
     - id: volts
       type: u2 # / 100

   instances:
     beacon:
       value: '(volts.to_s).substring(0,1) + "." +  (volts.to_s).substring(1,3) + " V"'

  dbm:
   seq:
     - id: dbm
       type: u1 # * (-1)

   instances:
     beacon:
       value: '((-1)*dbm).to_s + " dBm"'

  pa:
   seq:
     - id: pa
       type: s1

   instances:
     beacon:
       value: '"PA " + pa.to_s + " C"'

  pcb:
   seq:
     - id: pcb
       type: s1

   instances:
     beacon:
       value: '"PCB " + pcb.to_s + " C"'
