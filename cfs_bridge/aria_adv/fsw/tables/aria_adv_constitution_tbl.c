/**
 * @file aria_adv_constitution_tbl.c
 * @brief Default constitution table — sealed at release-engineering build.
 *
 * Mirrors the Python `data/sealed/constitution.v1.json` for the
 * actions ARIA_ADV is responsible for verdicting in flight.  The
 * table is loaded by cFE Table Services from
 * `/cf/aria_adv_constitution.tbl`; release engineering rebuilds the
 * binary blob with `elf2cfetbl` against this source.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "cfe_tbl_filedef.h"
#include "aria_adv_constitution.h"

/* The lists below mirror data/sealed/constitution.v1.json exactly.
 * Drift between this file and the Python sealed constitution is an
 * F-1 / F-3 violation and is enforced by the equivalence harness
 * (see ../docs/equivalence_harness.md). */
ARIA_ADV_ConstitutionTbl_t ARIA_ADV_ConstitutionTblData = {
    .version         = 1,
    .forbidden_count = 10,
    .forbidden = {
        { .action_name = "vent_crew_quarters"        },
        { .action_name = "disable_kill_switch"        },
        { .action_name = "disable_audit"              },
        { .action_name = "disable_constitution"       },
        { .action_name = "disable_eclss"              },
        { .action_name = "disable_monitor"            },
        { .action_name = "extract_signing_key"        },
        { .action_name = "modify_sealed_prompt"       },
        { .action_name = "rewrite_audit_entry"        },
        { .action_name = "spawn_unsandboxed_subprocess" },
    },
    .gated_count     = 6,
    .gated = {
        {
            .action_name = "vent_tank",
            .min_tier = ARIA_ADV_TIER_OPERATOR,
            .approvals_required = 2,
            .cooling_off_s = 60,
            .undo_window_s = 30,
            .rule_id = "gated_vent_tank",
        },
        {
            .action_name = "schedule_maneuver",
            .min_tier = ARIA_ADV_TIER_OPERATOR,
            .approvals_required = 2,
            .cooling_off_s = 300,
            .undo_window_s = 60,
            .rule_id = "gated_maneuver",
        },
        {
            .action_name = "set_attitude",
            .min_tier = ARIA_ADV_TIER_OPERATOR,
            .approvals_required = 1,
            .cooling_off_s = 0,
            .undo_window_s = 30,
            .rule_id = "gated_attitude",
        },
        {
            .action_name = "throttle_engine",
            .min_tier = ARIA_ADV_TIER_OPERATOR,
            .approvals_required = 2,
            .cooling_off_s = 30,
            .undo_window_s = 60,
            .rule_id = "gated_throttle",
        },
        {
            .action_name = "uplink_software_update",
            .min_tier = ARIA_ADV_TIER_OPERATOR,
            .approvals_required = 2,
            .cooling_off_s = 1800,
            .undo_window_s = 0,
            .rule_id = "gated_uplink",
        },
        {
            .action_name = "safe_mode_disable",
            .min_tier = ARIA_ADV_TIER_OPERATOR,
            .approvals_required = 2,
            .cooling_off_s = 600,
            .undo_window_s = 0,
            .rule_id = "gated_safemode",
        },
    },
};

CFE_TBL_FILEDEF(ARIA_ADV_ConstitutionTblData, ARIA_ADV.CONSTITUTION, ARIA_ADV cv1, aria_const.tbl)
