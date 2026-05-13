"""Default spacecraft procedures loaded into ARIA's semantic memory.

These are the standard operating procedures and emergency checklists
that ARIA can reference during reasoning.
"""

from __future__ import annotations

from aria.memory.store import MemoryStore


def load_default_procedures(memory: MemoryStore) -> int:
    """Load standard spacecraft procedures into memory. Returns count loaded."""
    procedures = [
        # Emergency procedures
        {
            "title": "Cabin Depressurization Emergency",
            "content": (
                "1. Sound general alarm. 2. All crew don pressure suits. "
                "3. Identify leaking module via pressure differential sensors. "
                "4. Isolate leaking module by closing hatches. "
                "5. Activate emergency repressurization from O2/N2 tanks. "
                "6. Assess structural damage. 7. Report to ground."
            ),
            "category": "emergency",
            "subsystem": "eclss",
            "tags": ["depressurization", "leak", "pressure"],
        },
        {
            "title": "Fire Response Procedure",
            "content": (
                "1. Sound fire alarm. 2. Identify fire location and type. "
                "3. If electrical: de-energize affected circuit. "
                "4. Deploy CO2 or water mist suppression. "
                "5. If atmosphere contaminated: don masks, ventilate after suppression. "
                "6. Monitor for re-ignition for 30 minutes. "
                "7. Assess damage and report."
            ),
            "category": "emergency",
            "subsystem": "eclss",
            "tags": ["fire", "smoke", "suppression"],
        },
        {
            "title": "CO2 Scrubber Failure",
            "content": (
                "1. Activate backup CDRA sorbent bed. "
                "2. If backup fails: deploy LiOH emergency canisters. "
                "3. Reduce crew activity to lower metabolic CO2 output. "
                "4. Monitor CO2 levels every 5 minutes. "
                "5. Begin troubleshooting primary scrubber. "
                "6. LiOH provides 48 hours backup capacity."
            ),
            "category": "emergency",
            "subsystem": "eclss",
            "tags": ["co2", "scrubber", "backup"],
        },
        {
            "title": "Battery Thermal Runaway Response",
            "content": (
                "1. Isolate affected battery string from main bus. "
                "2. Activate thermal suppression (CO2 + active cooling). "
                "3. Evacuate crew from battery compartment. "
                "4. Monitor adjacent batteries for cascade. "
                "5. Switch to backup battery strings. "
                "6. Do NOT attempt to recharge until thermal analysis complete."
            ),
            "category": "emergency",
            "subsystem": "power",
            "tags": ["battery", "thermal", "runaway", "fire"],
        },
        {
            "title": "Collision Avoidance Maneuver",
            "content": (
                "1. ConjunctionWatch identifies Pc > 1e-4. "
                "2. ARIA presents maneuver options to Captain. "
                "3. Captain approves maneuver plan. "
                "4. Stow science instruments and secure loose items. "
                "5. Orient spacecraft for maneuver burn. "
                "6. Execute burn with real-time monitoring. "
                "7. Verify post-maneuver state vector. "
                "8. Confirm post-maneuver Pc < 1e-6. "
                "9. Resume nominal operations."
            ),
            "category": "operations",
            "subsystem": "navigation",
            "tags": ["conjunction", "maneuver", "collision", "avoidance"],
        },
        # Maintenance procedures
        {
            "title": "Solar Array Inspection",
            "content": (
                "1. Command array to inspection attitude. "
                "2. Capture images of each panel string. "
                "3. Run image analysis for damage, contamination, delamination. "
                "4. Compare output power per string to BOL predictions. "
                "5. Flag strings with >10% degradation for EVA inspection."
            ),
            "category": "maintenance",
            "subsystem": "power",
            "tags": ["solar", "inspection", "degradation"],
        },
        {
            "title": "Reaction Wheel Health Check",
            "content": (
                "1. Record current wheel speeds and temperatures. "
                "2. Run each wheel through low-speed ramp test. "
                "3. Monitor vibration spectrum for bearing signatures. "
                "4. Check for BPFO/BPFI frequencies indicating wear. "
                "5. Compare friction torque to baseline. "
                "6. Schedule desaturation if any wheel > 80% max speed."
            ),
            "category": "maintenance",
            "subsystem": "navigation",
            "tags": ["reaction wheel", "bearing", "vibration", "health"],
        },
        {
            "title": "Water Quality Testing",
            "content": (
                "1. Collect sample from potable water dispenser. "
                "2. Measure conductivity (limit: <500 µS/cm). "
                "3. Measure pH (acceptable: 6.0-8.5). "
                "4. Measure total organic carbon (limit: <500 µg/L). "
                "5. Run microbial colony count (limit: <50 CFU/mL). "
                "6. If any parameter out of spec: switch to backup supply, "
                "run WRS troubleshooting procedure."
            ),
            "category": "maintenance",
            "subsystem": "eclss",
            "tags": ["water", "quality", "testing"],
        },
        # Operational procedures
        {
            "title": "Eclipse Entry Preparation",
            "content": (
                "1. Verify battery SoC > 80% (or >60% with load reduction). "
                "2. Pre-heat critical thermal zones (battery, propulsion). "
                "3. Reduce non-essential loads (science, experiments). "
                "4. Stow deployable antennas if thermal risk. "
                "5. Monitor power margin throughout eclipse."
            ),
            "category": "operations",
            "subsystem": "power",
            "tags": ["eclipse", "power", "thermal", "preparation"],
        },
        {
            "title": "Ground Communication Pass",
            "content": (
                "1. Predict next ground station visibility window. "
                "2. Pre-position antenna for acquisition of signal. "
                "3. Prioritize downlink queue: commands → anomaly data → science. "
                "4. Upload any pending TLE updates, model updates, commands. "
                "5. Verify link margin and BER. "
                "6. Log pass statistics (duration, data volume, errors)."
            ),
            "category": "operations",
            "subsystem": "communication",
            "tags": ["ground", "communication", "downlink", "uplink"],
        },
        # Propulsion procedures
        {
            "title": "Pre-Maneuver Checklist",
            "content": (
                "1. Verify maneuver plan approved by ground/captain. "
                "2. Check propellant reserves > planned consumption + 20% margin. "
                "3. Verify tank pressure within limits (100-350 psi). "
                "4. Test thruster valves (open/close cycle). "
                "5. Stow deployables (solar arrays, antennas if applicable). "
                "6. Orient spacecraft to burn attitude. "
                "7. Arm propulsion system. "
                "8. Countdown and execute burn. "
                "9. Monitor chamber pressure during burn. "
                "10. Verify delta-V achieved matches plan within 2%."
            ),
            "category": "operations",
            "subsystem": "propulsion",
            "tags": ["maneuver", "burn", "thruster", "checklist"],
        },
        {
            "title": "Propellant Leak Response",
            "content": (
                "1. Isolate suspect feed line (close isolation valves). "
                "2. Monitor tank pressure for continued drop. "
                "3. If leak confirmed: close all propulsion valves. "
                "4. Assess remaining delta-V budget. "
                "5. Recalculate mission profile with reduced fuel. "
                "6. Notify ground of fuel status. "
                "7. Preserve fuel for collision avoidance only if critical."
            ),
            "category": "emergency",
            "subsystem": "propulsion",
            "tags": ["propellant", "leak", "isolation", "fuel"],
        },
        # Communication procedures
        {
            "title": "Loss of Signal Recovery",
            "content": (
                "1. Verify antenna pointing (auto-repoint to last known ground station). "
                "2. Switch to omnidirectional low-gain antenna. "
                "3. Increase transmit power to maximum. "
                "4. Check for RF interference (spectrum analysis). "
                "5. If planned blackout: wait for next contact window. "
                "6. If unexpected: activate emergency beacon mode. "
                "7. After 48 hours without contact: enter autonomous ops mode."
            ),
            "category": "emergency",
            "subsystem": "communication",
            "tags": ["signal", "loss", "antenna", "beacon"],
        },
        # Science / Radiation procedures
        {
            "title": "Solar Particle Event Response",
            "content": (
                "1. Confirm SPE via radiation monitors (dose rate > 1000 µSv/hr). "
                "2. IMMEDIATE: All crew to radiation shelter (command module). "
                "3. Power down radiation-sensitive equipment. "
                "4. Switch to low-gain antenna (HGA more susceptible to noise). "
                "5. Enable enhanced ECC on all memory banks. "
                "6. Begin crew dosimetry monitoring (every 15 min). "
                "7. Coordinate with ground on SPE duration forecast. "
                "8. All-clear: dose rate < 200 µSv/hr for 2 consecutive hours."
            ),
            "category": "emergency",
            "subsystem": "science",
            "tags": ["radiation", "spe", "shelter", "crew safety"],
        },
        {
            "title": "Crew Radiation Dose Limit Approach",
            "content": (
                "1. Assess cumulative dose vs NASA-STD-3001 career limits. "
                "2. If approaching 80% limit: restrict EVA and high-exposure activities. "
                "3. Optimize shielding placement for high-dose crew members. "
                "4. Adjust work schedule to equalize exposure across crew. "
                "5. Report to flight surgeon for medical assessment."
            ),
            "category": "operations",
            "subsystem": "science",
            "tags": ["radiation", "dose", "limit", "crew"],
        },
        # EVA and docking
        {
            "title": "EVA Pre-Breathe Protocol",
            "content": (
                "1. Begin O2 pre-breathe 4 hours before EVA. "
                "2. Reduce suit pressure to 4.3 psi (29.6 kPa). "
                "3. Monitor crew vital signs continuously during pre-breathe. "
                "4. Check EVA suit integrity (leak check at 4.3 psi for 5 min). "
                "5. Verify communications with suit radio. "
                "6. Final go/no-go from flight surgeon and EVA lead."
            ),
            "category": "operations",
            "subsystem": "eclss",
            "tags": ["eva", "pre-breathe", "suit", "decompression"],
        },
        {
            "title": "Docking Approach Procedure",
            "content": (
                "1. Establish communication with target vehicle. "
                "2. Begin approach at 200m — verify closing rate < 0.1 m/s. "
                "3. LIDAR tracking active for range/rate. "
                "4. At 30m — go/no-go decision point. "
                "5. Final approach: maintain closing rate 0.03 m/s. "
                "6. Contact — verify capture latches engaged. "
                "7. Retract to hard dock — verify seal. "
                "8. Equalize pressure before opening hatches."
            ),
            "category": "operations",
            "subsystem": "navigation",
            "tags": ["docking", "proximity", "rendezvous"],
        },
        {
            "title": "Orbit Transfer Burn Procedure",
            "content": (
                "1. Verify maneuver plan approved (ground + captain). "
                "2. Configure propulsion for main engine burn. "
                "3. Stow all deployables (arrays, antennas, radiators). "
                "4. Orient to burn attitude (verify within 0.5 deg). "
                "5. T-5 min: arm propulsion, final health check. "
                "6. Execute burn — monitor chamber pressure and temps. "
                "7. Post-burn: verify delta-V achieved within 2%. "
                "8. Orbit determination — confirm new orbit. "
                "9. Deploy stowed systems. Resume nominal ops."
            ),
            "category": "operations",
            "subsystem": "propulsion",
            "tags": ["orbit", "transfer", "burn", "maneuver"],
        },
    ]

    count = 0
    for proc in procedures:
        memory.add_procedure(**proc)
        count += 1

    return count
