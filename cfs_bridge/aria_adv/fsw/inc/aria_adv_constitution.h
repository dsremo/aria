/**
 * @file aria_adv_constitution.h
 * @brief Constitutional layer — C port of `aria.cognitive.constitution`.
 *
 * The constitution is sealed at build time + loaded once.  Subsequent
 * runtime calls are pure-deterministic lookups: same (action,
 * trust_tier) inputs always produce the same verdict.
 *
 * The C port does NOT support the gated-rule operator-approval
 * machinery — that lives in cFS Limit Checker / Stored Command apps
 * upstream.  ARIA_ADV emits a GATE verdict and the upstream operator
 * console handles the approval queue.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef ARIA_ADV_CONSTITUTION_H
#define ARIA_ADV_CONSTITUTION_H

#include "cfe.h"
#include "aria_adv_msg.h"

#define ARIA_ADV_MAX_FORBIDDEN_ACTIONS  64
#define ARIA_ADV_MAX_GATED_ACTIONS      64

typedef struct {
    char action_name[ARIA_ADV_ACTION_NAME_LEN];
} ARIA_ADV_ForbiddenEntry_t;

typedef struct {
    char    action_name[ARIA_ADV_ACTION_NAME_LEN];
    uint8_t min_tier;            /* lowest trust tier permitted        */
    uint8_t approvals_required;
    uint16_t cooling_off_s;
    uint16_t undo_window_s;
    char    rule_id[16];
} ARIA_ADV_GatedEntry_t;

typedef struct {
    uint32_t version;
    uint32_t forbidden_count;
    uint32_t gated_count;
    ARIA_ADV_ForbiddenEntry_t forbidden[ARIA_ADV_MAX_FORBIDDEN_ACTIONS];
    ARIA_ADV_GatedEntry_t     gated[ARIA_ADV_MAX_GATED_ACTIONS];
} ARIA_ADV_ConstitutionTbl_t;

/* Verdict result (memory-stable, no allocation). */
typedef struct {
    uint8_t  verdict;             /* ARIA_ADV_Verdict_t                */
    uint8_t  approvals_required;
    uint16_t cooling_off_s;
    uint16_t undo_window_s;
    char     rule_id[16];
    char     reason[ARIA_ADV_REASON_LEN];
} ARIA_ADV_CheckResult_t;

int32 ARIA_ADV_Constitution_Init(void);

void ARIA_ADV_Constitution_Check(
    const char                    *action,
    uint8_t                        trust_tier,
    ARIA_ADV_CheckResult_t        *result);

bool ARIA_ADV_Constitution_IsForbidden(const char *action);

#endif /* ARIA_ADV_CONSTITUTION_H */
