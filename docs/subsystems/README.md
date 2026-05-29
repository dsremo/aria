# ARIA subsystem deep-dives

The [top-level README](../../README.md) describes each `src/aria/` subpackage in one line. This directory is the next level down: one detailed, code-verified doc per subsystem, for people evaluating the architecture or deciding where to contribute.

Every doc here is written **from the source on disk**, not from memory — counts, class names, and capabilities were checked against the actual code. Where a doc's numbers differ from the README's one-liner, the doc is the more current figure. ARIA is a research prototype (TRL 3–5); each doc has a *Current limitations* section that says plainly what is approximate, skeleton, or not yet built.

## The reasoning core

- [Cognitive engine](./cognitive.md) — the single reasoning loop: sealed system prompt (F-1), the constitution it cannot rewrite (F-3), per-tool capability tokens (F-6), the eval-vs-prod marker (F-11), and the model-agnostic backend (cloud LLM / rule-based fallback).
- [Subsystem agents & core types](./agents-and-core.md) — the per-domain agent framework and the shared type vocabulary (severity, authority, ALLOW/GATE/DENY) that every trust boundary speaks.

## The guardrails

- [Security & guard library](./security.md) — the largest package: execution guard, hash-chained audit (F-8), capability tokens, per-actuator rate limits (F-4), TOCTOU/replay defense (F-19), and the layered adversarial-guard library.
- [Safety & the independent monitor](./safety-and-monitor.md) — the 4-level safe-mode hierarchy (F-10), cumulative resource gate (F-5), the read-only 2-of-3 independent monitor (F-7), and continuous safety-test replay (F-13).

## The domain models

- [Physics pods](./physics.md) — gravity, attitude, thermal, radiation, CFD, impact and more, as analytical/parametric pods called by the engine's tools.
- [Digital twin](./digital-twin.md) — parametric CadQuery geometry, FEA, a cited materials database, components, and mass/power budgets.
- [Telemetry anomaly detection (Dsremo)](./anomaly-detection.md) — the 12-detector ensemble that turns raw telemetry into scored, severity-tagged anomalies.
- [Conjunction screening](./conjunction.md) — the CARA-style pipeline: TLE → SGP4 → smart sieve → probability-of-collision → CDM.
- [Genastra](./genastra.md) — genome & astrobiology analysis (biosignature spectroscopy, radiation biology, gene expression, protein structure).

## Mission simulation & evidence

- [Mission simulation](./simulation.md) — the scenario engine: LEO, lunar/Apollo/Artemis, Mars, reentry/EDL, ECLSS, and multi-decade interstellar runs.
- [Generation-ship engineering lab](./engineering-lab.md) — the interactive, tickable whole-ship simulator with a large REST API and a React console.
- [Replay & the closed-loop demonstration](./replay.md) — the harness behind ARIA's headline falsifiable result: the [Apollo 13 cryo-stir closed-loop run](../APOLLO13_REPLAY_REPORT.md).

## Edges, tooling & products

- [Integrations & external-tool bridges](./integrations.md) — GMAT, OpenC3, Basilisk, NASA-42, OpenMCT bridges, telemetry decoders, and the HAL sidecar boundary.
- [Doctrine & lessons-learned retrieval](./knowledge.md) — the TF-IDF corpus (doctrine + NASA lessons + ECSS) that grounds the advisor's recommendations.
- [Product-line wrappers](./products.md) — narrowly-scoped reference applications (conjunction-screener, cubesat-deorbit) built on the core.
- [The `aria` CLI](./cli.md) — the full command reference the top-level README only samples.
- [Supporting packages](./supporting-packages.md) — boot verification (F-18), the cognitive tool registry, API/dashboard, state, persistence, observability, and validation.
