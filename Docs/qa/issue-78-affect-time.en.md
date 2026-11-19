# QA issue #78 — affect and cortisol versus dt

Branch: `team/issue-78-affect-time`. HEAD at run time: `4bc99db` (`4bc99dbb1dedbb16a3edf494773c9ffc4b7bb935`). PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/82. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/78. Baseline for the old curve: `a2bab8f` (main, parent of the three commits on this branch).
Russian: [issue-78-affect-time.ru.md](issue-78-affect-time.ru.md).

Product code was not changed in this pass. No new PR was opened and nothing was merged. CI was not awaited. The full pytest suite was not run.

Machine: Python 3.12.3, pytest 9.2.0. Core probes used `PYTHONPATH=src`. The old curve used `a2bab8f` copies of `src/{agent,neuromodulators,affective_space,autonomous_organism}.py`; the rest of `src/` is the branch tree (no other `src/` files differ from `a2bab8f`).

## Verdict

**PASS** (`4bc99db`).

All six checklist items pass. At `dt=1`, agent stress and cortisol on an 8-commit schedule match `a2bab8f` (max |Δcortisol| `5.6e-17`, |Δstress| `0`). A fed sleeper does not accumulate cortisol, and hunger raises it. There is one positive affect step per tick. Overload discharge pulls toward the setpoint from both sides. Core genes and constants are unchanged; the only demo edit is the `id()` test.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | dt 0.1 / 0.25 / 1.0, affect and cortisol | Pass. The test's stress tolerance is 0.08 over 10 s at reward −0.05. Probe: stress `0.1210 / 0.1250 / 0.1448`, spread `0.0238`. Strong signal (−0.8, conflict 0.4), 10 s: stress `0.7398 / 0.7791 / 0.7475`, spread `0.0393`. On `a2bab8f` the same mild run had stress spread `0.695` (fine dt stuck near `0.84`). The HPA integrator alone, 24 s, reward −0.8 and conflict 0.4: ends `0.776254 / 0.776255 / 0.776256`, spread `1.5e-6`. One `dt=1` step, reward −0.8, conflict 0: cortisol `0.21`, identical to the legacy formula, \|Δ\| `0`. Live-agent cortisol over 10 s at zero wakefulness: `0.1075 / 0.0884 / 0.0789`, spread `0.0286`. That gap is not the integrator; see questions |
| 2 | `dt=1` matches main | Pass. Eight commits, wakefulness pinned at 0.6, rewards `−0.2, 0.15, −0.8, 0, −0.5, 0.3, −0.15, 0`, conflicts `0, 0, 0.4, 0.2, 0.1, 0, 0.5, 0`. Max \|Δcortisol\| against `a2bab8f` is `5.6e-17`, \|Δstress\| is `0` |
| 3 | Fed sleep and hunger | Pass. Colony, seed 78, hunger 0.1, thirst 0.1, wakefulness 0.95, `sim_step(1)`: from second 2 the action is `sleep`, stress stays `0` for all 16 s. Cortisol `0.0593` (1 s, still the entry tick) → `0.0518` (8 s) → `0.0532` (16 s), no ramp. Same shape on the core: 20 s of sleep, reward `0.2`, conflict `0`, wakefulness `0.95`, pending dt cleared, `advance(..., asleep=True)`, commit with a zero appraisal: secretion on the clearance step is `0`, the `0.01·wakefulness` dose in the impulse is `0`, cortisol `0.05 → 0.0532`; at 60 s it is `0.0533`. Sleep with reward `−0.6` and conflict `0.4`: `0.40 → 0.0596` in 8 s, stress `0.5 → 1.3e-5`. Colony hunger, seed 79, hunger held ≥ 0.95, no food, 6× `sim_step(1)`: stress `0 → 0.804`, cortisol `0.05 → 0.664`. Core, colony penalty `-(1.0-0.4)·0.25 = -0.15`, 60 s, `dt=1`, wakefulness 0.5: stress `0.700` versus `0` when fed (`+0.05`), cortisol `0.139` versus `0.065`. Then 20 s of reward `+0.4`: stress `0.0012`, cortisol `0.064` |
| 4 | One affect step, sleep and wake | Pass. `organism_step(0.25)` with overload and an internal cycle: `time_elapsed` calls `[0.25, 0.0, 0.0]`, one positive. Wake: commit of `host_dt`, then body slices of `1/12` s. Positive dt: `0.1 → [0.1]`, `0.25 → [0.25]` (3 slices), `1.0 → [1.0]` (12 slices). Sleep of 12 s and 20 s: the sum of positive dt equals the number of seconds, one `1.0` per second; the commit contributes `0`. `colony_agent._advance_autonomous_body` does not run the body while `is_sleeping` |
| 5 | Discharge toward the setpoint from both sides | Pass. Overload, setpoint `0`, `dt=1`: stress `0.9 → 0.530` and `−0.9 → −0.530`, no positive dt. Setpoint `0.2`: `0.8 → 0.504`, `−0.4 → −0.229`. Allostasis `_relax_deviation`: `0.6 → 0.42`, `−0.6 → −0.42`, sign preserved |
| 6 | Constants, genes, demo | Pass. `git diff --name-only a2bab8f..HEAD`: seven files; `src/genome.py` and `src/wakefulness.py` are absent (`git diff --exit-code` on them is 0). `CORT_REWARD_NEGATIVE=0.2`, `CORT_CONFLICT=0.25`, `ACC_CORT_HOMEOSTATIC_DECAY=0.4`, `BASELINE_CORT=0.05`, `CORTISOL_INCREASE=0.01` match `a2bab8f`. `affective_space.py` only adds `affect_time_credit_s=0.0`. Demo: only `Demo/Colony chinchillas/tests/test_colony_dt_invariance.py`, a list of objects instead of bare `id()` in `test_lifespan_factor_runner_matches_at_nominal_1x_and_10x`. That test: 1 passed, 0.46 s |

Targeted tests, exit 0:

```
python3 -m pytest -q --no-header -p no:warnings tests/test_issue_78_affect_time.py tests/test_neuromodulators_phase2.py | tail -n 30
```

`25 passed in 0.43s`

```
SDL_VIDEODRIVER=dummy python3 -m pytest -q --no-header -p no:warnings "Demo/Colony chinchillas/tests/test_colony_dt_invariance.py::test_lifespan_factor_runner_matches_at_nominal_1x_and_10x" | tail -n 30
```

`1 passed in 0.46s`

## Defects

None.

## Questions / blockers

Agent cortisol at zero wakefulness over 10 s spreads by `0.0286` (`0.1075 / 0.0884 / 0.0789`). The HPA integrator itself converges (spread `1.5e-6` at 24 s). The extra impulse on every commit is `EmotionalRegulation.apply_neuromodulator_guidance(..., gain=0.5)` in `Agent._commit_waking_transition`: the cortisol delta is about `0.001` and is not multiplied by dt. `src/emotional_regulation.py` is not in the diff. During sleep that addition levels off near `0.053` from a baseline of `0.05`, with no ramp. Not filed: the spread is under the stress test's tolerance of `0.08`, the `dt=1` curve matches main, and HPA secretion during sleep is zero.

30 s of the hunger penalty `−0.1375` (wakefulness 0.5): stress `0.472 / 0.477 / 0.583`, spread `0.111`. That is longer and stronger than the test scenario (10 s, −0.05, tolerance 0.08). Fine dt no longer locks: on `a2bab8f` the same run was `0.830 / 0.841 / 0.583`. The test already says the post-retention impulse is not bit-identical.

`stress_repro/repro.py` and the as_is plateau ≥ 0.45 were outside this checklist (the PR text leaves them in #79) and were not run. Restoring food for seed 79 did not lower hunger: the actions were not `eat`, hunger reached `1.0`, and stress stayed near `0.81`. That is not a fed-agent check.

## Recommendations

If agent cortisol must spread like the integrator rather than by about `0.03`, the CER impulse has to be multiplied by dt or folded into `_integrate_cortisol`. The wakefulness doses for norepinephrine and serotonin are still added in full on every commit; the cortisol dose is already multiplied by the appraisal dt.

The full pytest suite stays with CI.

## Release readiness

Ready on this checklist. The full suite was not run locally, and CI was not awaited.
