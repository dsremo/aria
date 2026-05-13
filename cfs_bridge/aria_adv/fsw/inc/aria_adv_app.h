/**
 * @file aria_adv_app.h
 * @brief Application-level types + lifecycle for ARIA_ADV.
 *
 * ARIA_ADV runs as one cFS application.  The lifecycle is the
 * standard cFS pattern:
 *     ARIA_ADV_AppMain                 — entry point (called by ES)
 *     ARIA_ADV_AppInit                 — register pipes + tables
 *     ARIA_ADV_ProcessCommandPacket   — pull from CMD pipe, dispatch
 *     ARIA_ADV_HousekeepingCmd        — emit HK telemetry
 *
 * The verdict handler is the safety-critical hot path — it must
 * produce a verdict in bounded time (<5 ms is the design budget on
 * a 100 MHz RAD750-class flight CPU).
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef ARIA_ADV_APP_H
#define ARIA_ADV_APP_H

#include "cfe.h"
#include "aria_adv_msg.h"
#include "aria_adv_constitution.h"

#define ARIA_ADV_PIPE_DEPTH    16
#define ARIA_ADV_PIPE_NAME     "ARIA_ADV_CMD_PIPE"

typedef struct {
    /* cFS pipe handles. */
    CFE_SB_PipeId_t cmd_pipe;

    /* Tables (cFE Table Services). */
    CFE_TBL_Handle_t            constitution_tbl_handle;
    ARIA_ADV_ConstitutionTbl_t *constitution_tbl;

    /* Static telemetry buffers — pre-allocated, no malloc in flight. */
    ARIA_ADV_HkTlm_t           hk_pkt;
    ARIA_ADV_VerdictTlm_t      verdict_pkt;
    ARIA_ADV_SafeModeReqTlm_t  safemode_pkt;
    ARIA_ADV_AuditAnchorTlm_t  anchor_pkt;

    /* Counters — these are exactly the fields published in HK. */
    uint32_t command_count;
    uint32_t command_error_count;
    uint32_t proposals_seen;
    uint32_t verdicts_allow;
    uint32_t verdicts_gate;
    uint32_t verdicts_deny;
    uint32_t safe_mode_requests;
    uint32_t audit_anchor_count;

    /* Hash-chain head (32 bytes SHA-256). */
    uint8_t  chain_head[32];
    uint32_t chain_head_seq;
    uint8_t  chain_intact;

    /* Current safe-mode level (last published). */
    uint8_t  current_safe_level;

    /* Boot timestamp for uptime reporting. */
    CFE_TIME_SysTime_t boot_time;
} ARIA_ADV_AppData_t;

extern ARIA_ADV_AppData_t ARIA_ADV_AppData;

/* Lifecycle. */
void  ARIA_ADV_AppMain(void);
int32 ARIA_ADV_AppInit(void);

/* Hot-path handlers. */
void  ARIA_ADV_ProcessCommandPacket(CFE_SB_Buffer_t *sb_buf);
void  ARIA_ADV_HousekeepingCmd(const CFE_SB_Buffer_t *sb_buf);
void  ARIA_ADV_HandleProposeAction(const CFE_SB_Buffer_t *sb_buf);

/* Anchor publisher — called by SCH every hour. */
void  ARIA_ADV_PublishAuditAnchor(void);

#endif /* ARIA_ADV_APP_H */
