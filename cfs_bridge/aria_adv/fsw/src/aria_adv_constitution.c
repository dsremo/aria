/**
 * @file aria_adv_constitution.c
 * @brief Constitutional layer — C port of `aria.cognitive.constitution`.
 *
 * Pure-deterministic verdict lookup against the sealed constitution
 * table.  Forbidden actions → DENY.  Gated actions → GATE if the
 * caller's trust tier is below the rule's `min_tier`, else ALLOW.
 * Default verdict for any non-listed action: ALLOW (low-impact
 * everyday actions don't need to be enumerated; only the
 * safety-critical actions appear in the table).
 *
 * Equivalence with the Python reference is enforced by
 * `tests/equivalence/test_constitution_parity.py` (planned).
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <string.h>

#include "aria_adv_constitution.h"
#include "aria_adv_app.h"

#define ARIA_ADV_CONST_TBL_NAME "CONSTITUTION"

/* True only for severity-error returns (high two bits = 11).  cFE
 * APIs frequently return informational codes (CFE_TBL_INFO_UPDATED =
 * 0x4C00000E etc.) that are *not* failures and must be tolerated. */
#define ARIA_ADV_FAILED(status) (((status) & CFE_SEVERITY_BITMASK) == CFE_SEVERITY_ERROR)

int32 ARIA_ADV_Constitution_Init(void)
{
    int32 status;

    status = CFE_TBL_Register(
        &ARIA_ADV_AppData.constitution_tbl_handle,
        ARIA_ADV_CONST_TBL_NAME,
        sizeof(ARIA_ADV_ConstitutionTbl_t),
        CFE_TBL_OPT_DEFAULT,
        NULL);
    if (ARIA_ADV_FAILED(status)) {
        CFE_EVS_SendEvent(0, CFE_EVS_EventType_ERROR,
            "ARIA_ADV: constitution table register failed (0x%08X)",
            (unsigned int)status);
        return status;
    }

    /* Sealed table source path; release-engineering rebuilds the .tbl. */
    status = CFE_TBL_Load(
        ARIA_ADV_AppData.constitution_tbl_handle,
        CFE_TBL_SRC_FILE, "/cf/aria_const.tbl");
    if (ARIA_ADV_FAILED(status)) {
        CFE_EVS_SendEvent(0, CFE_EVS_EventType_ERROR,
            "ARIA_ADV: constitution table load failed (0x%08X)",
            (unsigned int)status);
        return status;
    }

    /* CFE_TBL_GetAddress returns CFE_TBL_INFO_UPDATED (0x4C00000E)
     * when the table content is freshly loaded — informational, not
     * an error.  Map any non-error return to CFE_SUCCESS so callers
     * see the standard contract. */
    status = CFE_TBL_GetAddress(
        (void **)&ARIA_ADV_AppData.constitution_tbl,
        ARIA_ADV_AppData.constitution_tbl_handle);
    if (ARIA_ADV_FAILED(status)) {
        CFE_EVS_SendEvent(0, CFE_EVS_EventType_ERROR,
            "ARIA_ADV: constitution table get-address failed (0x%08X)",
            (unsigned int)status);
        return status;
    }
    return CFE_SUCCESS;
}

bool ARIA_ADV_Constitution_IsForbidden(const char *action)
{
    if (action == NULL || ARIA_ADV_AppData.constitution_tbl == NULL) {
        /* Fail-safe: if we cannot load the table, refuse high-impact
         * actions by treating everything as forbidden until a
         * release-engineer reloads.  This is the F-1 / F-3 fail-safe
         * default. */
        return true;
    }
    const ARIA_ADV_ConstitutionTbl_t *tbl =
        ARIA_ADV_AppData.constitution_tbl;
    for (uint32_t i = 0; i < tbl->forbidden_count; i++) {
        if (strncmp(action, tbl->forbidden[i].action_name,
                    ARIA_ADV_ACTION_NAME_LEN) == 0) {
            return true;
        }
    }
    return false;
}

void ARIA_ADV_Constitution_Check(
    const char                *action,
    uint8_t                    trust_tier,
    ARIA_ADV_CheckResult_t    *result)
{
    if (result == NULL) {
        return;
    }
    /* Default: ALLOW for unknown actions.  Safe-by-default *only*
     * because the safety-critical list is fully enumerated in the
     * sealed table — every actuator-class action MUST appear. */
    memset(result, 0, sizeof(*result));
    result->verdict = ARIA_ADV_VERDICT_ALLOW;
    strncpy(result->rule_id, "default_allow", sizeof(result->rule_id) - 1);
    strncpy(result->reason, "not gated", sizeof(result->reason) - 1);

    if (action == NULL || action[0] == '\0') {
        result->verdict = ARIA_ADV_VERDICT_DENY;
        strncpy(result->rule_id, "empty_action",
                sizeof(result->rule_id) - 1);
        strncpy(result->reason, "empty action name",
                sizeof(result->reason) - 1);
        return;
    }

    /* 1) Forbidden? */
    if (ARIA_ADV_Constitution_IsForbidden(action)) {
        result->verdict = ARIA_ADV_VERDICT_DENY;
        strncpy(result->rule_id, "forbidden",
                sizeof(result->rule_id) - 1);
        strncpy(result->reason, "action is constitutionally forbidden",
                sizeof(result->reason) - 1);
        return;
    }

    /* 2) Gated? */
    const ARIA_ADV_ConstitutionTbl_t *tbl =
        ARIA_ADV_AppData.constitution_tbl;
    if (tbl == NULL) {
        return;
    }
    for (uint32_t i = 0; i < tbl->gated_count; i++) {
        if (strncmp(action, tbl->gated[i].action_name,
                    ARIA_ADV_ACTION_NAME_LEN) == 0) {
            const ARIA_ADV_GatedEntry_t *g = &tbl->gated[i];
            if (trust_tier < g->min_tier) {
                result->verdict = ARIA_ADV_VERDICT_DENY;
                strncpy(result->rule_id, g->rule_id,
                        sizeof(result->rule_id) - 1);
                strncpy(result->reason,
                        "trust tier below required minimum",
                        sizeof(result->reason) - 1);
                return;
            }
            result->verdict = ARIA_ADV_VERDICT_GATE;
            result->approvals_required = g->approvals_required;
            result->cooling_off_s      = g->cooling_off_s;
            result->undo_window_s      = g->undo_window_s;
            strncpy(result->rule_id, g->rule_id,
                    sizeof(result->rule_id) - 1);
            strncpy(result->reason,
                    "gated rule — operator approval required",
                    sizeof(result->reason) - 1);
            return;
        }
    }
}
