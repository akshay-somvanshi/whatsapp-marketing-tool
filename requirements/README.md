# Requirements

Explicit, per-phase requirements for building the WhatsApp marketing platform into a sellable SaaS.

## Workflow (per phase)

1. **Write requirements** — a `REQUIREMENTS.md` under `phases/phase-N-<slug>/` defining scope, data model, API contract, acceptance criteria, and out-of-scope items *before* any code.
2. **Make code changes** — implement strictly against the requirements.
3. **Code review** — a reviewer pass (tests + logic) that holistically checks the built feature for errors, gaps, and regressions. Findings are recorded in `REVIEW.md` next to the requirements.

## Phases

| Phase | Slug | Status |
|-------|------|--------|
| 1 | multi-tenancy-auth | ✅ Complete (88 tests green; review fixes applied) |

Phases are driven by `IMPROVEMENT_PLAN.md` at the repo root (blockers + roadmap).
