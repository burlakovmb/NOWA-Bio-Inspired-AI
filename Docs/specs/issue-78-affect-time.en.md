# Issue #78 — Affect and cortisol dt invariance

Russian: [issue-78-affect-time.ru.md](issue-78-affect-time.ru.md)

PR #82, branch `team/issue-78-affect-time`. Builds on simulated-second affect ([issue-54-affect-simulated-time.en.md](issue-54-affect-simulated-time.en.md)). Baseline for the legacy curve: `a2bab8f`.

Code: `src/agent.py`, `src/affective_space.py`, `src/neuromodulators.py`, `src/autonomous_organism.py`. Tests: `tests/test_issue_78_affect_time.py`, extended `tests/test_neuromodulators_phase2.py`. Demo (flake only): `Demo/Colony chinchillas/tests/test_colony_dt_invariance.py`.

---

## 1. Problem

Before this fix, stress and affect trajectories depended on the host step `dt`:

- **Affective appraisal:** `_derive_affective_space_inputs` returns per-second drives; commit applied them **without** `× dt`, so fine steps over-applied stress (e.g. mild negative reward: spread ~`0.695` across `dt ∈ {0.1, 0.25, 1.0}` on `a2bab8f`, fine `dt` stuck near `0.84`).
- **Double integration:** A cognitive commit plus body slices could call `AffectiveSpace.step` twice for the same host interval (sleep/wake paths).
- **Cortisol HPA:** `update_from_signals` added the full one-second secretion every call and cleared excess with a fixed `0.4` pull, **ignoring** `dt`. Steady level and sleep clearance were not invariant to sub-stepping.
- **Sleep:** Host seconds advanced without appraisal still skipped cortisol clearance; wakefulness HPA dose (`0.01 × wakefulness`) fired on sleep commits as if `dt = 1`, letting cortisol rise while asleep.

Genes and neuromodulator constants were **not** retuned.

---

## 2. Solution

### 2.1 Affective impulse = rate × dt

On `commit_executed_transition`, when `affective_inputs` is omitted, each derived axis is multiplied by host `time_elapsed` before `AffectiveSpace.step` (`src/agent.py`). At `dt = 1` the kick matches the legacy one-second step.

### 2.2 One affect advance per host tick

| Mechanism | Role |
| --- | --- |
| `affect_time_credit_s` on `AffectiveSpace` | Commit records the interval already integrated; body slices spend credit via `AutonomousOrganismAgent.update_affect` without a second retention pass |
| Sleep commit | Pending `time_elapsed` cleared; commit uses `0`; host seconds still run cortisol clearance |
| `regulate_affect` / internal overload | Uses `time_elapsed=0` (impulse-only regulation) |

Colony: `_advance_autonomous_body` does not run the body while `is_sleeping`.

### 2.3 Cortisol — `_integrate_cortisol(secretion, dt)`

`src/neuromodulators.py`. Pull `ACC_CORT_HOMEOSTATIC_DECAY = 0.4` → retain `0.6` per second.

- Clearance of excess over `BASELINE_CORT`: factor `0.6^dt` on `(current − baseline)`.
- Constant secretion (legacy one-second dose): delivered amount `secretion × (1 − 0.6^dt) / 0.4` (closed form for constant rate against the same clearance).
- `dt = 1`: identical to the old map `cortisol += 0.4 × (baseline − current) + secretion`.
- Steady level `baseline + secretion / pull` does not depend on `dt`; one step of `dt` matches two steps of `dt/2`.

`update_from_signals(..., dt=...)` routes cortisol only through `_integrate_cortisol`. On sleep commits, `Agent` integrates any host seconds not yet cleared with `secretion = 0` before appraisal at `dt = 0`.

### 2.4 Wakefulness HPA dose

`wakefulness.get_neuromodulator_deltas()` cortisol increment is multiplied by `_nm_appraisal_dt` (host appraisal interval). Sleep commits keep appraisal `dt = 0`, so tonic dose is off while clearance runs.

---

## 3. Invariants and tests

| Invariant | Test |
| --- | --- |
| Stress over fixed sim time, `dt ∈ {0.1, 0.25, 1.0}` | `test_derived_stress_over_fixed_time_is_invariant_to_dt` (`DT_INVARIANCE_TOLERANCE = 0.08`, 10 s) |
| `_relax_deviation` sign-correct toward setpoint | `test_allostatic_map_relaxes_both_signs_toward_the_setpoint`, overload discharge tests |
| One positive `time_elapsed` per organism tick | `test_organism_tick_advances_affect_once_even_with_overload_and_internal_cycle`, `test_commit_plus_body_slices_integrate_the_host_interval_once` |
| Fed sleep clears cortisol; hunger raises it | `test_fed_sleep_clears_cortisol_and_does_not_secrete`, `test_unmet_need_raises_stress_and_cortisol_and_relief_relaxes_them` |
| `dt = 1` agent schedule matches `a2bab8f` | QA probe (not a single named test) |
| Cortisol steady state vs `dt` | `test_cortisol_steady_level_does_not_depend_on_dt`, `test_four_quarter_seconds_are_not_four_full_cortisol_doses` in `test_neuromodulators_phase2.py` |

Run:

```bash
python3 -m pytest -q tests/test_issue_78_affect_time.py tests/test_neuromodulators_phase2.py
```

Demo flake fix (object refs, not bare `id()`): `test_lifespan_factor_runner_matches_at_nominal_1x_and_10x` in `test_colony_dt_invariance.py`.

---

## 4. QA

Report: [issue-78-affect-time.en.md](../qa/issue-78-affect-time.en.md) — **PASS** at `4bc99db`.

- `dt = 1` vs `a2bab8f` (8 commits): max \|Δcortisol\| `5.6e-17`, \|Δstress\| `0`.
- Mild stress invariance (10 s, reward −0.05): spread `0.0238` (was ~`0.695` on old code).
- Fed sleep 16 s: cortisol `0.0593 → 0.0532`, no ramp; HPA integrator alone at 24 s: spread `1.5e-6` across `dt`.
- Targeted pytest: **25 passed** in 0.43 s.

---

## 5. Known limitations

| Item | Notes |
| --- | --- |
| CER cortisol nudge | `EmotionalRegulation.apply_neuromodulator_guidance(..., gain=0.5)` on each commit is **not** scaled by `dt`. Live-agent cortisol over 10 s at zero wakefulness: spread `0.0286` (test stress tolerance `0.08`; at `dt = 1` curves match main). |
| Long hunger penalty | 30 s colony-style penalty: stress spread `0.111` — outside the 10 s / −0.05 test scenario; fine `dt` no longer sticks high. |
| Demo stress plateau | as_is plateau ≥ 0.45 — **issue #79**, out of scope here. |

---

## 6. Design principle

Strict biological fidelity: the cognitive **core** is not retuned for demo hosts. Only time-integration of existing per-second rates and doses changed; genome and `CORT_*` / `ACC_CORT_HOMEOSTATIC_DECAY` constants match `a2bab8f`.