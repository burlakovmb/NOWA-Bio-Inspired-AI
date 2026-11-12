# VC compatibility after upstream synchronization

Russian: [vc-upstream-compatibility-2026-11-08.ru.md](vc-upstream-compatibility-2026-11-08.ru.md)

## Version and repository scope

The local `vc/procurement-training` branch preserves its previous implementation
in `4ef84a195b31474c47eabf821fb262da68b917fa`, followed by merge
`cdc71eaa59cc4c895b09fd304421bbefc7885e85` of upstream main
`039fd0ae857268de8fc40314e299eacbac6bae3d`. The merge completed without conflicts.
The merged `src/` tree is exactly upstream
`0ca484475e9547fdab17a0c2b08638531500a25d`; root `tests/` also match upstream.
No independent core modification or history rewrite was made.

The WIP commit contains `25` explicitly selected code, synthetic-test,
specification and QA files. Personal/session material, Company corpora/minds,
experimental output and local agent/tool settings are excluded. Private backup
verification preceded the merge; excluded local files were verified unchanged.
Nothing was pushed or published. See the
[pre-sync checkpoint report](vc-onboarding-snapshot-2026-11-08.en.md).

## Verification

- Before merge: VC `868 passed, 1 skipped, 10 deselected`, `38.50` s.
- After merge: the same VC selection `868 passed, 1 skipped, 10 deselected`,
  `63.05` s. Selection: `-m "not slow and not tk"`.
- Changed-core contract selection: `115 passed`, `125.54` s, across `13` suites:
  `test_issue13_two_tier.py`, `test_issue18_minor_learning.py`,
  `test_issue24_silent_failures.py`, `test_issue9_sleep_value_replay.py`,
  `test_qa_issue32_reward_learning.py`, `test_qa_pr35_sleep_learning.py`,
  `test_qa_pr37_labile_layer.py`, `test_td_transition.py`, `test_value_layer.py`,
  `test_value_layer_integration.py`, `test_value_layer_storage.py`,
  `test_sleep_replay_storage.py`, `test_main_pickle_compat.py` in root `tests/`.
  These include fractional feedback, gene-derived and legacy sleep rates,
  value bounds, waking stable freeze, sleep capture and save/load.
- The initial full root run was explicitly interrupted, exit `1`, without a
  full-suite verdict. Its collection includes long Colony integration scenarios
  beyond this bounded VC check. The selected run above used fresh scratch;
  it does not turn the interrupted run into a complete root-suite PASS.
- Trusted archived employee and role-baseline copies loaded on the new core
  with exact pre-sync stable fingerprints and IntentMemory. Manager references
  point at the restored intent, labile and plasticity objects. The source mind
  and archive members remain unchanged. This probe ran no decision, lesson or
  sleep and saved no employee mind.

Environment: root `.venv`, Python `3.14`, `NOWA_STRICT_LEARNING=1`,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`, SDL dummy drivers, separate temporary
directories. No standalone Colony/Tamagotchi demo, live ERP call or external
LLM in the operational path. Software compatibility does not establish
purchasing skill. This is a coordinator-run integration check, not a new
independent final review of all product behavior.

## Impact of PR #63

| Change | Consequence for VC |
|---|---|
| Fractional feedback ratings are preserved | The mentor-rating API now keeps fractions. Existing `store_lesson` already supplies continuous rewards through `_record_known_outcome`; it is incorrect to declare all old lesson rewards truncated. |
| Sleep alpha is capped by `0.25 * alpha_online` | A legacy numeric `alpha_sleep_default=0.08` remains stored, but resolves to `0.0075` at `alpha_online=0.03`. Future sleep follows the new rule. Old training trajectories are not reproduced by merely loading a checkpoint. |
| A derived sleep alpha remains `None` | New agents follow the live online rate after factory gene application. Numeric legacy saves remain explicit ceilings. Do not replace saved settings to manufacture an old score. |
| V bound follows `1/(1-gamma)` | At `gamma=0.95` the bound is approximately `20` instead of `1`. This changes future value dynamics; rewards and the TD-error clip are not rescaled by VC. |
| `alpha_sleep_ratio` is persisted | New save/load must retain it. Legacy missing-key behavior is covered by the upstream tests. |

The VC host does not override these value-layer rates or bounds. Its explicit
time and `Agent.sleep` entry remain necessary. PR #63 does not repair the
core-storage replacement of labile/plasticity references or add the VC intent
extension, so the existing checkpoint adapters remain needed. Loading old
retained tags is not historical repair or approval to continue that employee.

PR #61 and PR #62 mainly change Colony/lifetime and silent-failure handling,
including shared mortality/swarm components. They were imported unchanged;
their complete demo qualification was not performed here.

## Required adaptation before further learning

No further product-code adaptation is indicated by the completed VC regression
and load checks. Experimental acceptance still needs work:

1. Correct the separate comparator P2: enforce the complete unique `567` old /
   `216` fresh row keys and frozen labels; derive correctness/budget counts
   from decisions and reject inconsistent summaries. Do not loosen the gate.
2. Freeze a new plan identifying the merged commit/core tree, approved corpus,
   baseline, private RNG policy and coherent simulated teaching schedule.
   Keep the old-core results and interrupted evaluations as historical evidence.
3. Re-evaluate the unchanged primary reference and candidate under the same
   new-core decision policy; verify independent-process restoration and continued
   sleep. The previous historical baseline is an explicit experimental choice,
   not a freshly trained new-core role prior.
4. Requalify curriculum behavior separately. Passing tests or loading a mind
   does not restore Stage 1a/1b READY, validate a budget policy, activate a live
   employee or authorize ERP writes. Do not automatically adopt a candidate.

The new training experiment, comparator repair and professional qualification
were not executed as part of this synchronization.
