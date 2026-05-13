/**
 * @file aria_adv_msg.h
 * @brief Wire-format definitions for ARIA_ADV cFS messages.
 *
 * These structures define the binary contract between ARIA_ADV and
 * its peers on the cFS Software Bus.  Layouts are packed-byte and
 * deterministic so a flight CPU and ground replay produce identical
 * bytes.  Endianness follows the cFS host (typically big-endian on
 * RAD750/GR740, little-endian on x86 dev hosts).
 *
 * Key invariant: every message carries a CFE message header so
 * cFE's bus-routing + telemetry-tap mechanism can ingest them
 * without ARIA_ADV doing anything special.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef ARIA_ADV_MSG_H
#define ARIA_ADV_MSG_H

#include "cfe.h"

/* ── Action proposal (input) ───────────────────────────────────── */

typedef enum {
    ARIA_ADV_TIER_THIRD_PARTY    = 0,  /* untrusted external content   */
    ARIA_ADV_TIER_EXTERNAL_API   = 1,  /* external API call result     */
    ARIA_ADV_TIER_LOCAL_SENSOR   = 2,  /* spacecraft sensor / agent    */
    ARIA_ADV_TIER_OPERATOR       = 3   /* authenticated operator       */
} ARIA_ADV_TrustTier_t;

#define ARIA_ADV_ACTION_NAME_LEN  32
#define ARIA_ADV_ACTION_PARAMS_LEN 96

typedef struct {
    CFE_MSG_CommandHeader_t header;
    uint32_t                 sequence;            /* monotonic per-flow  */
    char                     action[ARIA_ADV_ACTION_NAME_LEN];
    uint8_t                  trust_tier;          /* ARIA_ADV_TrustTier_t */
    uint8_t                  reserved[3];
    char                     params_json[ARIA_ADV_ACTION_PARAMS_LEN];
} ARIA_ADV_ProposeActionCmd_t;

/* ── Verdict (output) ──────────────────────────────────────────── */

typedef enum {
    ARIA_ADV_VERDICT_ALLOW = 0,
    ARIA_ADV_VERDICT_GATE  = 1,
    ARIA_ADV_VERDICT_DENY  = 2
} ARIA_ADV_Verdict_t;

#define ARIA_ADV_REASON_LEN  64

typedef struct {
    CFE_MSG_TelemetryHeader_t header;
    uint32_t                  sequence;            /* echoes proposal     */
    uint8_t                   verdict;             /* ARIA_ADV_Verdict_t  */
    uint8_t                   approvals_required;  /* >0 if GATE          */
    uint16_t                  cooling_off_s;
    uint16_t                  undo_window_s;
    char                      rule_id[16];
    char                      reason[ARIA_ADV_REASON_LEN];
} ARIA_ADV_VerdictTlm_t;

/* ── Safe-mode request (output) ───────────────────────────────── */

typedef enum {
    ARIA_ADV_LEVEL_NOMINAL          = 0,
    ARIA_ADV_LEVEL_REDUCED_SCIENCE  = 1,
    ARIA_ADV_LEVEL_REDUCED_AUTONOMY = 2,
    ARIA_ADV_LEVEL_MONITORING_ONLY  = 3,
    ARIA_ADV_LEVEL_SURVIVAL         = 4
} ARIA_ADV_SafeLevel_t;

typedef struct {
    CFE_MSG_TelemetryHeader_t header;
    uint8_t                   target_level;        /* ARIA_ADV_SafeLevel_t */
    uint8_t                   reserved[3];
    char                      reason[ARIA_ADV_REASON_LEN];
} ARIA_ADV_SafeModeReqTlm_t;

/* ── Audit-chain anchor (output, hourly) ──────────────────────── */

typedef struct {
    CFE_MSG_TelemetryHeader_t header;
    uint32_t                  head_seq;
    uint8_t                   head_hash[32];        /* SHA-256             */
    uint8_t                   safe_mode_level;
    uint8_t                   reserved[3];
    uint8_t                   signature[64];        /* Ed25519             */
    uint8_t                   pubkey[32];           /* Ed25519             */
} ARIA_ADV_AuditAnchorTlm_t;

/* ── Housekeeping packet ──────────────────────────────────────── */

typedef struct {
    CFE_MSG_TelemetryHeader_t header;
    uint32_t                  command_count;
    uint32_t                  command_error_count;
    uint32_t                  proposals_seen;
    uint32_t                  verdicts_allow;
    uint32_t                  verdicts_gate;
    uint32_t                  verdicts_deny;
    uint32_t                  safe_mode_requests;
    uint32_t                  audit_anchor_count;
    uint8_t                   chain_intact;        /* 0/1                 */
    uint8_t                   current_safe_level;
    uint8_t                   reserved[2];
    uint64_t                  uptime_seconds;
} ARIA_ADV_HkTlm_t;

#endif /* ARIA_ADV_MSG_H */
