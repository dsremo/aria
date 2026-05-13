/**
 * @file aria_adv_msgids.h
 * @brief NASA cFS Software Bus message IDs for ARIA_ADV.
 *
 * These IDs slot into the project-wide msgid range.  Concrete
 * numeric values are deployment-specific; the ranges below assume
 * the cFS sample mission allocates 0x18A0–0x18AF to ARIA_ADV.
 * Re-allocate per the host project's mission_msgids.h.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef ARIA_ADV_MSGIDS_H
#define ARIA_ADV_MSGIDS_H

#include "cfe_msgids.h"

/* ── Command message IDs ─────────────────────────────────────── */
/* Operator commands sent TO ARIA_ADV. */

#define ARIA_ADV_CMD_MID            0x18A0  /* generic command pipe       */
#define ARIA_ADV_SEND_HK_MID        0x18A1  /* send-housekeeping request  */
#define ARIA_ADV_PROPOSE_ACTION_MID 0x18A2  /* downstream agent proposes  */
                                            /*   an action; ADV verdicts  */

/* ── Telemetry message IDs ─────────────────────────────────────── */
/* Outputs ARIA_ADV publishes onto the bus. */

#define ARIA_ADV_HK_TLM_MID          0x08A0  /* housekeeping packet       */
#define ARIA_ADV_VERDICT_TLM_MID     0x08A1  /* per-action verdict        */
#define ARIA_ADV_SAFE_MODE_REQ_MID   0x08A2  /* request safe-mode         */
#define ARIA_ADV_AUDIT_ANCHOR_MID    0x08A3  /* hourly hash-chain anchor  */

#endif /* ARIA_ADV_MSGIDS_H */
