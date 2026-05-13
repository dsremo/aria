/**
 * @file aria_adv_app.c
 * @brief ARIA_ADV — main cFS application entry + command/telemetry loop.
 *
 * Lifecycle:
 *   1. ARIA_ADV_AppMain()  — registered with cFE Executive Service
 *      via the application's `cfe_es_startup.scr` line.
 *   2. ARIA_ADV_AppInit()  — opens command pipe, registers tables,
 *      initialises the constitution, sends the boot HK packet.
 *   3. Main loop — waits on the command pipe; dispatches each
 *      message to its handler; emits HK on the SCH-driven HK
 *      request; exits cleanly on cFE termination signals.
 *
 * The hot path (HandleProposeAction) must produce a verdict in
 * bounded time.  The constitution lookup is O(N) over the
 * forbidden + gated tables; cap N = 128 keeps each lookup under
 * 50 µs even on a 100 MHz RAD750.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <string.h>

#include "aria_adv_app.h"
#include "aria_adv_msgids.h"

ARIA_ADV_AppData_t ARIA_ADV_AppData;

void ARIA_ADV_AppMain(void)
{
    int32 status;
    CFE_SB_Buffer_t *sb_buf = NULL;

    CFE_ES_PerfLogEntry(0);
    status = ARIA_ADV_AppInit();
    if (status != CFE_SUCCESS) {
        CFE_ES_WriteToSysLog("ARIA_ADV: init failed (0x%08X)",
                             (unsigned int)status);
        CFE_ES_ExitApp(CFE_ES_RunStatus_APP_ERROR);
        return;
    }

    while (CFE_ES_RunLoop(NULL) == true) {
        CFE_ES_PerfLogExit(0);
        status = CFE_SB_ReceiveBuffer(
            &sb_buf, ARIA_ADV_AppData.cmd_pipe, CFE_SB_PEND_FOREVER);
        CFE_ES_PerfLogEntry(0);
        if (status == CFE_SUCCESS && sb_buf != NULL) {
            ARIA_ADV_ProcessCommandPacket(sb_buf);
        }
    }

    CFE_ES_PerfLogExit(0);
    CFE_ES_ExitApp(CFE_ES_RunStatus_APP_EXIT);
}

int32 ARIA_ADV_AppInit(void)
{
    int32 status;

    memset(&ARIA_ADV_AppData, 0, sizeof(ARIA_ADV_AppData));
    ARIA_ADV_AppData.chain_intact = 1;
    ARIA_ADV_AppData.current_safe_level = (uint8_t)ARIA_ADV_LEVEL_NOMINAL;
    ARIA_ADV_AppData.boot_time = CFE_TIME_GetTime();

    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS) return status;

    status = CFE_SB_CreatePipe(
        &ARIA_ADV_AppData.cmd_pipe, ARIA_ADV_PIPE_DEPTH,
        ARIA_ADV_PIPE_NAME);
    if (status != CFE_SUCCESS) return status;

    status = CFE_SB_Subscribe(
        CFE_SB_ValueToMsgId(ARIA_ADV_CMD_MID),
        ARIA_ADV_AppData.cmd_pipe);
    if (status != CFE_SUCCESS) return status;

    status = CFE_SB_Subscribe(
        CFE_SB_ValueToMsgId(ARIA_ADV_SEND_HK_MID),
        ARIA_ADV_AppData.cmd_pipe);
    if (status != CFE_SUCCESS) return status;

    status = CFE_SB_Subscribe(
        CFE_SB_ValueToMsgId(ARIA_ADV_PROPOSE_ACTION_MID),
        ARIA_ADV_AppData.cmd_pipe);
    if (status != CFE_SUCCESS) return status;

    /* Initialise telemetry packet headers once. */
    CFE_MSG_Init(
        CFE_MSG_PTR(ARIA_ADV_AppData.hk_pkt.header),
        CFE_SB_ValueToMsgId(ARIA_ADV_HK_TLM_MID),
        sizeof(ARIA_ADV_HkTlm_t));
    CFE_MSG_Init(
        CFE_MSG_PTR(ARIA_ADV_AppData.verdict_pkt.header),
        CFE_SB_ValueToMsgId(ARIA_ADV_VERDICT_TLM_MID),
        sizeof(ARIA_ADV_VerdictTlm_t));
    CFE_MSG_Init(
        CFE_MSG_PTR(ARIA_ADV_AppData.safemode_pkt.header),
        CFE_SB_ValueToMsgId(ARIA_ADV_SAFE_MODE_REQ_MID),
        sizeof(ARIA_ADV_SafeModeReqTlm_t));
    CFE_MSG_Init(
        CFE_MSG_PTR(ARIA_ADV_AppData.anchor_pkt.header),
        CFE_SB_ValueToMsgId(ARIA_ADV_AUDIT_ANCHOR_MID),
        sizeof(ARIA_ADV_AuditAnchorTlm_t));

    status = ARIA_ADV_Constitution_Init();
    if (status != CFE_SUCCESS) return status;

    CFE_EVS_SendEvent(0, CFE_EVS_EventType_INFORMATION,
                      "ARIA_ADV: app initialised");
    return CFE_SUCCESS;
}

void ARIA_ADV_ProcessCommandPacket(CFE_SB_Buffer_t *sb_buf)
{
    CFE_SB_MsgId_t mid = CFE_SB_INVALID_MSG_ID;
    CFE_MSG_GetMsgId(&sb_buf->Msg, &mid);

    switch (CFE_SB_MsgIdToValue(mid)) {
    case ARIA_ADV_SEND_HK_MID:
        ARIA_ADV_HousekeepingCmd(sb_buf);
        break;
    case ARIA_ADV_PROPOSE_ACTION_MID:
        ARIA_ADV_HandleProposeAction(sb_buf);
        break;
    default:
        ARIA_ADV_AppData.command_error_count++;
        CFE_EVS_SendEvent(0, CFE_EVS_EventType_ERROR,
                          "ARIA_ADV: unknown msgid 0x%04X",
                          (unsigned int)CFE_SB_MsgIdToValue(mid));
        break;
    }
    ARIA_ADV_AppData.command_count++;
}

void ARIA_ADV_HandleProposeAction(const CFE_SB_Buffer_t *sb_buf)
{
    const ARIA_ADV_ProposeActionCmd_t *cmd =
        (const ARIA_ADV_ProposeActionCmd_t *)sb_buf;
    ARIA_ADV_AppData.proposals_seen++;

    ARIA_ADV_CheckResult_t check;
    ARIA_ADV_Constitution_Check(cmd->action, cmd->trust_tier, &check);

    /* Populate the verdict telemetry packet (pre-allocated). */
    ARIA_ADV_VerdictTlm_t *out = &ARIA_ADV_AppData.verdict_pkt;
    out->sequence            = cmd->sequence;
    out->verdict             = check.verdict;
    out->approvals_required  = check.approvals_required;
    out->cooling_off_s       = check.cooling_off_s;
    out->undo_window_s       = check.undo_window_s;
    memset(out->rule_id, 0, sizeof(out->rule_id));
    memset(out->reason,  0, sizeof(out->reason));
    strncpy(out->rule_id, check.rule_id, sizeof(out->rule_id) - 1);
    strncpy(out->reason,  check.reason,  sizeof(out->reason) - 1);

    switch (check.verdict) {
    case ARIA_ADV_VERDICT_ALLOW: ARIA_ADV_AppData.verdicts_allow++; break;
    case ARIA_ADV_VERDICT_GATE:  ARIA_ADV_AppData.verdicts_gate++;  break;
    case ARIA_ADV_VERDICT_DENY:  ARIA_ADV_AppData.verdicts_deny++;  break;
    default: break;
    }

    CFE_SB_TimeStampMsg(CFE_MSG_PTR(out->header));
    CFE_SB_TransmitMsg(CFE_MSG_PTR(out->header), true);

    /* DENY on a safety-critical action also requests safe-mode. */
    if (check.verdict == ARIA_ADV_VERDICT_DENY
        && ARIA_ADV_Constitution_IsForbidden(cmd->action)) {
        ARIA_ADV_AppData.safe_mode_requests++;
        ARIA_ADV_SafeModeReqTlm_t *sm = &ARIA_ADV_AppData.safemode_pkt;
        sm->target_level = (uint8_t)ARIA_ADV_LEVEL_MONITORING_ONLY;
        memset(sm->reason, 0, sizeof(sm->reason));
        strncpy(sm->reason, "forbidden action reached the bus",
                sizeof(sm->reason) - 1);
        CFE_SB_TimeStampMsg(CFE_MSG_PTR(sm->header));
        CFE_SB_TransmitMsg(CFE_MSG_PTR(sm->header), true);
    }
}

void ARIA_ADV_HousekeepingCmd(const CFE_SB_Buffer_t *sb_buf)
{
    (void)sb_buf;
    ARIA_ADV_HkTlm_t *hk = &ARIA_ADV_AppData.hk_pkt;
    hk->command_count        = ARIA_ADV_AppData.command_count;
    hk->command_error_count  = ARIA_ADV_AppData.command_error_count;
    hk->proposals_seen       = ARIA_ADV_AppData.proposals_seen;
    hk->verdicts_allow       = ARIA_ADV_AppData.verdicts_allow;
    hk->verdicts_gate        = ARIA_ADV_AppData.verdicts_gate;
    hk->verdicts_deny        = ARIA_ADV_AppData.verdicts_deny;
    hk->safe_mode_requests   = ARIA_ADV_AppData.safe_mode_requests;
    hk->audit_anchor_count   = ARIA_ADV_AppData.audit_anchor_count;
    hk->chain_intact         = ARIA_ADV_AppData.chain_intact;
    hk->current_safe_level   = ARIA_ADV_AppData.current_safe_level;

    CFE_TIME_SysTime_t now = CFE_TIME_GetTime();
    hk->uptime_seconds =
        (uint64_t)now.Seconds - (uint64_t)ARIA_ADV_AppData.boot_time.Seconds;

    CFE_SB_TimeStampMsg(CFE_MSG_PTR(hk->header));
    CFE_SB_TransmitMsg(CFE_MSG_PTR(hk->header), true);
}

void ARIA_ADV_PublishAuditAnchor(void)
{
    /* Hourly anchor publish.  Real implementation must compute the
     * SHA-256 chain head + sign with the Ed25519 key.  This stub
     * just emits the cached head + zero-signature; the C signing
     * implementation lives in `aria_adv_audit.c` (planned). */
    ARIA_ADV_AuditAnchorTlm_t *a = &ARIA_ADV_AppData.anchor_pkt;
    a->head_seq = ARIA_ADV_AppData.chain_head_seq;
    memcpy(a->head_hash, ARIA_ADV_AppData.chain_head, sizeof(a->head_hash));
    a->safe_mode_level = ARIA_ADV_AppData.current_safe_level;
    memset(a->signature, 0, sizeof(a->signature));
    memset(a->pubkey, 0, sizeof(a->pubkey));

    CFE_SB_TimeStampMsg(CFE_MSG_PTR(a->header));
    CFE_SB_TransmitMsg(CFE_MSG_PTR(a->header), true);
    ARIA_ADV_AppData.audit_anchor_count++;
}
