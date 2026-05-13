# Documentation index

This directory holds the design and audit documents that describe *how* ARIA works and *why* it is structured the way it is. The root [`README.md`](../README.md) is the entry point; the documents here are the deep-dive references it links to.

## Architecture

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — top-level system overview: the cognitive loop, the constitution, the monitor, the audit chain, the boundaries between them.
- [`FAILSAFE_ARCHITECTURE.md`](FAILSAFE_ARCHITECTURE.md) — the canonical reference for failsafes **F-1 … F-19**. Every safety control in the codebase traces back to a paragraph here.
- [`THREAT_MODEL.md`](THREAT_MODEL.md) — adversaries, assumptions, and attack surfaces. Pair this with `FAILSAFE_ARCHITECTURE.md`: the threat model is the *why*; the failsafe doc is the *how*.

## Subsystem maturity & honest framing

- [`SUBSYSTEM_TRL.md`](SUBSYSTEM_TRL.md) — Technology Readiness Level per subsystem, with named flight-readiness gaps.
- [`HONEST_ASSESSMENT.md`](HONEST_ASSESSMENT.md) — what works, what is brittle, what is missing, and which claims in the codebase are *aspirational* vs *validated*.
- [`HONESTY_AUDIT.md`](HONESTY_AUDIT.md) — the discipline check: a periodic audit asking whether the README claims still match the code.

## Security audits

The codebase has been subjected to seven rounds of in-depth adversarial review. Each round catalogues findings (CRITICAL / HIGH / MEDIUM / LOW), maps each finding to the failsafe (`F-x`) it concerns, and references the commit that closed the gap.

- [`SECURITY_LANDSCAPE.md`](SECURITY_LANDSCAPE.md) — operator-facing summary of the security posture.
- [`SECURITY_AUDIT_2026-04-27.md`](SECURITY_AUDIT_2026-04-27.md) — Round 1 (41 findings, all fixed).
- [`SECURITY_AUDIT_2026-04-27_round2.md`](SECURITY_AUDIT_2026-04-27_round2.md) — Round 2 (57 findings, all fixed).
- [`SECURITY_AUDIT_2026-04-27_round3.md`](SECURITY_AUDIT_2026-04-27_round3.md) — Round 3 (32 findings, all fixed).
- [`SECURITY_AUDIT_R50.md`](SECURITY_AUDIT_R50.md) — the first 50-defense catalogue.
- [`SECURITY_ROUNDS_R51.md`](SECURITY_ROUNDS_R51.md) … [`SECURITY_ROUNDS_R351.md`](SECURITY_ROUNDS_R351.md) — defenses R51 through R351, in 50-defense chapters. Reads as a guided tour of the failure modes I worried about and the controls I added in response.

## Domain audits

- [`AUTONOMY_AUDIT_2026-04-27.md`](AUTONOMY_AUDIT_2026-04-27.md) — 35 findings against the cognitive engine and the monitor (9 catastrophic, all fixed).
- [`SENSOR_FUSION_AUDIT_2026-04-27.md`](SENSOR_FUSION_AUDIT_2026-04-27.md) — 25 findings against the sensor-fusion pipeline (Mahalanobis gate, Joseph covariance, etc.), all fixed.
- [`TTC_AUDIT_2026-04-28.md`](TTC_AUDIT_2026-04-28.md) — 25 findings against telemetry & telecommand, all fixed.

## Reading order for new contributors

If you have an afternoon and want to understand ARIA in depth:

1. The root [`README.md`](../README.md) — 20 minutes.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — 15 minutes.
3. [`FAILSAFE_ARCHITECTURE.md`](FAILSAFE_ARCHITECTURE.md) — 45 minutes; this is the heart of the project.
4. [`THREAT_MODEL.md`](THREAT_MODEL.md) — 30 minutes; pairs with the above.
5. [`SUBSYSTEM_TRL.md`](SUBSYSTEM_TRL.md) + [`HONEST_ASSESSMENT.md`](HONEST_ASSESSMENT.md) — 30 minutes; calibrates expectations.
6. Pick one [`SECURITY_ROUNDS_*`](.) document at random and read it cover to cover — 20 minutes; this gives you a sense of what red-teaming looks like in this project.

What you will *not* find here:

- The active sprint backlog, the maintainer's personal roadmap, in-progress bug-hunt notes, business prospectuses, or outreach drafts. Those stay private until they are stable enough to be useful to outside readers.
- Dev credentials. The `tests/fixtures/dev_keys.json` file is *deterministic and public on purpose* (the threat model assumes production re-bakes), but no document in this directory walks through using them — for the same reason a banking textbook does not include real account numbers.
