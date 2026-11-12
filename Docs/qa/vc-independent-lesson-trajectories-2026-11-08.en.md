# Independent lesson trajectories: code acceptance

Русский: [vc-independent-lesson-trajectories-2026-11-08.ru.md](vc-independent-lesson-trajectories-2026-11-08.ru.md)

**PASS for the scoped body change.** New judged lessons receive an independent
`vc-lesson:<episode_id>` trajectory with step `0` before outcome registration.
This prevents unrelated lessons from sharing the core's legacy trajectory
fallback. Historical episodes, unjudged observations and role priors are unchanged.
See [specification](../specs/vc-independent-lesson-trajectories.en.md).

## Scope and independent review

Base: `3bfc5a3703704a3b426538bad5c4b9070005fe3a`. Implementation is limited to
`Demo/Virtual company/src/nowa_body/feedback_loop.py`; tests are in
`Demo/Virtual company/tests/test_lesson_trajectories.py`.
The core tree remains `0ca484475e9547fdab17a0c2b08638531500a25d`.

Independent final review initially found one P2 in supported-stub rollback:
a setter could mutate and then raise, leaving that attempted field outside the
rollback list. The correction records the attempt before invoking the setter.
Both original reproductions now pass; independent recheck: `16 passed`, `0.89` s,
no remaining P1/P2 in the bounded product diff. Restoration is promised only
where the object's attribute interface permits it.

Accepted source SHA256:
`c2c2ae658022584d0504023d2062033ea1b6df3e2545c928a4f9462ccd459fbb`.
Accepted test SHA256:
`6d6a5ba904792671acadd3ff0f9cfddefdb283980de14dd006aea3c2ceef7b42`.

## Executed checks

- Author's repaired focused body/host/checkpoint/onboarding selection:
  `51 passed`, `37.01` s.
- Final VC fast under strict learning, SDL dummy and task-local TEMP/TMP:
  `923 passed, 1 skipped, 6 deselected, 10 warnings`, `173.44` s.
  Command from `Demo/Virtual company`, root virtual environment:
  `python -m pytest -q -x -m "not slow and not perf" --basetemp <task-temp>`.
- Four direct core-contract files covering credit assignment, two-tier behavior,
  sleep-value replay and labile integration: `49 passed`, `17.00` s. These
  preceded the supported-stub correction; core code was unchanged.
- An intermediate full run had `922 passed` and one Windows `WinError 5` in an
  existing synthetic sidecar-replacement test. Its isolated repeat passed
  (`1 passed`, `5.46` s), followed by the clean full run above. The failure and
  repeated checks were retained; no unrelated file-write code was changed.

Real-core tests cover assignment before registration, unchanged kwargs/signature,
native trajectory/RNG invariants, duplicate-reference depth, legacy negative
controls, awake stable freeze, sleep capture once, save/restore and stub failures.
The awake fingerprint is captured before lesson storage. Synthetic checkpoints
and generic contexts only; no operational database was accessed.

## Limits

This accepts product code and its tests, not a completed behavioral study.
The full root suite and long curriculum qualification matrix were not run.
Terminal/bootstrap semantics and role-prior trajectories are separate contracts.
No historical checkpoint was retagged, candidate adopted or operational write
authorized. A successful software check is not employee qualification.
