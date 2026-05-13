# Security policy

ARIA is a safety-first onboard AI for spacecraft. We take security reports seriously.

## Supported version

Only `main` is supported. There is no LTS branch. Security fixes land on `main` as soon as they are triaged.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security findings.** Instead, either:

- Email the maintainer at the address listed in `pyproject.toml`, or
- Open a private GitHub security advisory on this repository (Security → Advisories → New draft).

A good report includes:

- A short description.
- Reproduction steps (smallest possible test case).
- The commit hash you observed it on.
- A proposed patch as a unified diff, if you have one.

You will receive an acknowledgement within **7 days**. We aim to ship a fix within **90 days** of the first response. The disclosure window is 90 days from that response, following common industry practice.

## In scope

- Authentication bypass on any `/v1/*` endpoint (`/v1/screen`, `/v1/screen_bulk`, `/v1/usage`, `/v1/rotate_key`, `/v1/admin/*`).
- Tenant-data leak across the persistence store.
- Path traversal or SSRF through TLE / orbital-element input fields.
- Constitution-table tamper that bypasses the sealed-image check.
- Audit-chain forgery against `aria.security.audit_chain` or `aria.security.audit_downlink`.
- Any failure of failsafes **F-1 … F-19** as described in `README.md` (and in the private design docs referenced therein).
- Capability-token forgery (HMAC-Ed25519 confused-deputy).
- Bypass of the two-person rule on `crew_life_critical` actions.

## Out of scope

- Issues that depend on a non-default deployment posture (e.g. running the screener without TLS, ignoring the per-tenant rate limit, bypassing FIDO2 in dev mode).
- Findings that require root on the host running the service.
- "Best practice" suggestions without a demonstrated exploit path.
- Issues in third-party dependencies — please report upstream and link the advisory here once it's public.

## Hall of fame

Reporters will be credited in release notes unless they ask for anonymity.
