# Contributing to ARIA

Thank you for considering a contribution. ARIA's value depends on careful, well-cited work — please read this short guide before you open a PR.

## Where to start

Three lanes, pick whichever fits your background:

1. **Physics / mission engineering.** Open `src/aria/physics/` or `src/aria/simulation/`. Replace an `# ESTIMATE` tag with a published citation, or add a new validation against real mission data (Apollo, Artemis, ISS, Mars Sample Return, etc.).
2. **AI safety / red-teaming.** Look at `src/aria/cognitive/`, `src/aria/security/`, and `src/aria/monitor/`. Try to break the constitution, forge a capability token, or make the monitor disagree with itself. File a finding even without a fix.
3. **Web / UX.** The two-person approval flow, stress-recall prompt, and conjunction visualisation in `web/` could all be more humane. Operator UX is a *design* problem.

Open a draft PR early — architecture conversations are easier when there is code to point at.

## Local development

```bash
git clone https://github.com/dsremo/aria.git
cd aria
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

make lint          # ruff + mypy strict
make test          # pytest -m "not slow and not noncore"
make test-slow     # 100+ year simulations
```

## Style

- **ARIA Source-Available License v1** for all new code (see [`LICENSE`](LICENSE)). Each commit you submit certifies your right to contribute under that licence — see [Sign-off](#sign-off) below.
- **Python 3.10+**, fully typed. `mypy --strict` must pass.
- **Descriptive identifiers.** In comprehensions, `for booking in bookings` — never `for b in bookings`. The same rule applies to `for` loops, `lambda`, and JS/TS `.map` callbacks. Use the domain noun.
- **Comments are rare.** The code and its tests should explain themselves; the *why* belongs in the PR description and commit message. Exceptions: tooling directives (`# noqa`, `# type: ignore`), license headers, shebang lines.
- **Numerical constants need a citation.** Every constant must trace to a published source (paper, standard, mission report). `# ESTIMATE` is a tag for review, not a free pass.
- **Tests with the change**, not after. Add or update unit tests in `tests/unit/`. End-to-end scenarios live in `tests/integration/`.

## Pull request flow

1. Fork, branch off `main`. Branch names: `lane/<short-description>` (e.g. `physics/lunar-j2-harmonics`).
2. Keep PRs focused. Multiple unrelated changes will be asked to split.
3. Run `make lint && make test` locally before pushing.
4. Fill in the PR template: what changed, why, how it was verified, citations for any new constants.
5. Expect review on architecture and on safety wiring — both matter.
6. Squash on merge; a clean linear history.

## Reviewing process

I aim to triage new PRs within 7 days. Safety- or constitution-touching changes go through an extra review pass and a red-team think. Bugfixes with a regression test are the fastest path to merge.

## A note on scope

ARIA is research-grade. It is not flight-qualified and it does not promise to be on any timeline. Contributions are welcome, but please do not file PRs that *claim* flight readiness — that is a partner, paperwork, and hardware problem, not a code problem.

## Sign-off

Every commit must be signed off with a `Signed-off-by:` trailer, certifying agreement with the [Developer Certificate of Origin v1.1](https://developercertificate.org/) — the same one Linux, Docker, and most large OSS projects use. Add it automatically with:

```bash
git commit -s -m "your message"
```

The sign-off line means: *I wrote this, or I have the right to submit it under the project's licence, and I am willing to have it redistributed under that licence in perpetuity.*

If your employer owns your work, please obtain an *Employer Contribution Letter* (or use a personal account for personal-time contributions) before submitting. We cannot accept contributions that cannot be cleanly licensed.

## A note on your contributions and commercial licensing

Your contributions are licensed under the **ARIA Source-Available License v1** (see [`LICENSE`](LICENSE)) — perpetually, with no auto-conversion to any other licence at any future date. The maintainer retains the right to offer paid commercial licences to ARIA as a whole; this is mechanically enabled by the DCO sign-off above, which grants distribution rights but does **not** transfer copyright. You keep your copyright; you grant a licence.

If you ever want to confirm the chain of provenance on a specific contribution, `git log --pretty=fuller` shows committer, author, and sign-off for every commit.

## Security

If you find a vulnerability, do **not** open a public issue. See [`SECURITY.md`](SECURITY.md).
