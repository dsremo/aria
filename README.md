# ARIA

**Autonomous Reasoning & Integration Architecture** — a safety-first onboard AI for spacecraft. One reasoning engine plans the mission; a tamper-proof "constitution" and an independent monitor decide what it's actually allowed to do.

> Source-available · research prototype (TRL 3–5) · not flight-qualified

## The idea

Most "AI for space" projects build a clever model and stop there. ARIA's hard part is the *wiring* — keeping an AI useful while making it incapable of doing something catastrophic on its own:

- **A constitution above the AI.** Forbidden actions, two-person rules, resource ceilings, and an Ed25519-signed sealed boot image live *outside* the model. The AI can propose; only the constitution can authorise. Nineteen explicit failsafes (F-1…F-19) cover prompt injection, token forgery, sensor spoofing, and the operator console itself.
- **An independent monitor.** A separate process — different code, different model family — votes 2-of-3 on every actuator-impacting command and can veto it or force safe mode. It never executes commands itself.
- **One cognitive loop over 55+ tools** spanning orbital mechanics, attitude control, anomaly detection, collision screening, life support, and radiation.

The five stages — **propose → authorise → execute → observe → record** — are split across process boundaries, so compromising the AI still leaves the constitution, the monitor, and a tamper-evident audit log intact, and any of them can force the craft into safe mode.

## The result worth pointing at: Apollo 13

Fed reconstructed Apollo 13 cryo-tank telemetry, ARIA's full loop flagged the O₂ tank-2 pressure excursion **94 seconds before the historical master alarm** — and the advisor returned an isolation plan matching documented EECOM procedure, including preparing the lunar-module "lifeboat" checklist ~13 minutes earlier than the real mission issued it. End to end in under 16 seconds. (Honest caveats + a reproducible run: [docs/APOLLO13_REPLAY_REPORT.md](docs/APOLLO13_REPLAY_REPORT.md).)

## Scale & honest status

A research prototype — nothing here has flown. Read it as evidence of an architecture that *could* fly with the right partner and hardware, not something to launch tomorrow.

- ~1,300 Python modules across 35 subsystems; 488 test files; 19 coded failsafes
- React + WebSocket mission dashboard
- All bundled data is public-source (NASA, NOAA, CISA, ECSS) — no external IP or customer data
- Not there yet: flight heritage, DO-178C paperwork, a rad-hard target, an on-device model

## Dig deeper

[System architecture](docs/ARCHITECTURE.md) · [Failsafe design](docs/FAILSAFE_ARCHITECTURE.md) · [Honest assessment](docs/HONEST_ASSESSMENT.md) · [doc index](docs/INDEX.md) · full original overview in [docs/OVERVIEW.md](docs/OVERVIEW.md)

## Quick start

```bash
git clone https://github.com/dsremo/aria.git && cd aria
pip install -e .
aria --help     # CLI dispatcher
# Optional: set ANTHROPIC_API_KEY for the LLM backend; otherwise a deterministic rule-based fallback runs.
```

## License

Source-available under the [ARIA Source-Available License v1](LICENSE) — perpetual, with no change date and no auto-conversion to open source. Free to read, learn from, and use for personal/hobby and unfunded academic work; all commercial or production use requires a paid licence.

Built by Ashutosh Tiwari.
