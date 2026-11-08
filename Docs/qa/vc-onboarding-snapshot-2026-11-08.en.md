# VC onboarding: checkpoint before upstream synchronization

Russian: [vc-onboarding-snapshot-2026-11-08.ru.md](vc-onboarding-snapshot-2026-11-08.ru.md)

## Version and purpose

This WIP checkpoint preserves existing VC implementation on base
`a8d75030a54679915b71499e5503c8df78344b15`, core tree
`5f09b3180ee7dfda31c688770b9e10102c413f94`, before merging newer upstream.
Known upstream at preparation is `039fd0ae857268de8fc40314e299eacbac6bae3d`.
Its PR #63 changes fractional feedback, effective sleep alpha and the V bound.
Old-core outcomes are not current-upstream acceptance.

Included: offline lessons and unjudged observations, optional role outcome
judges, employee/sandbox checkpoint extensions, explicit sandbox time and the
full Agent sleep entry. Specifications: [offline onboarding](../specs/vc-offline-onboarding.en.md)
and [issue #58](../specs/issue-58-sandbox-two-tier-plasticity.en.md).
No core implementation is changed by this checkpoint. Private corpora, minds,
experimental scripts/output, session notes and local tools/settings are excluded.

## Verification and limits

The earlier independent issue #58 code review passed with `99` executed cases.
That verdict covers the specified host/persistence changes, not a qualified
purchasing employee or all later experimental evidence tooling.

Pre-merge VC regression: `868 passed, 1 skipped, 10 deselected`, `38.50` s.
Command from the repository root: `.venv/Scripts/python.exe -m pytest
"Demo/Virtual company/tests" -q -m "not slow and not tk" --basetemp <scratch>`.
Environment: Python `3.14`, `NOWA_STRICT_LEARNING=1`, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONUTF8=1`, SDL dummy drivers, VC `src` on `PYTHONPATH`; `TEMP` and `TMP`
point to dedicated workspace scratch. Fixtures are synthetic; no employee
training, external LLM, live ERP or write operation was run.

The full five-seed Stage 1a/1b qualification remains open. Private old-core
reconstruction demonstrated checkpoint/RNG mechanics but its candidate decision
evaluations were interrupted. A separate experimental comparator has an open
P2: it does not enforce all expected old/fresh probe rows and trusts a budget
summary. No candidate behavioral PASS or adoption is claimed. That comparator
is outside this repository checkpoint and must be corrected before reuse.

After synchronization, independently check VC regressions, old checkpoint
loading, sleep learning rates, persistence and new value bounds. Freeze a new
versioned experiment before further learning. Existing minds remain preserved.
