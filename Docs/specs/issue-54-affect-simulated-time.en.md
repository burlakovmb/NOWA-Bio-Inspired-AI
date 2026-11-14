# Issue #54 (part 1) — Affective core in simulated seconds

Russian: [issue-54-affect-simulated-time.ru.md](issue-54-affect-simulated-time.ru.md)

Core only. PR #72. Colony alarm / host `dt` wiring is part 2 (#54).

Code: `src/affective_space.py`, `src/agent.py`, `src/sleep.py`, `src/storage.py`, `src/genome.py`, `src/affective_persistence.py`, `src/affective_background.py`, `src/mcp_body/_compat.py`, `Demo/Virtual company/src/nowa_sandbox/training_loop.py`.

Tests: `tests/test_affective_time.py`.

---

## 1. Time base

Affective retention, baseline allostasis, norm-cap drift, persistence trace decay, and background-field decay all use **simulated seconds** (`time_elapsed` / host `dt`), not “one decision = one second” unless the host passes `dt=1`.

Per axis, one second of homeostatic retention uses multiplier  
`m = clamp(axis_decay[axis] − lambda_reg, 0, 0.999)`.  
A step of length `dt` applies `m ** dt` toward the moving baseline. At `dt = 1` this matches the pre-#54 discrete step. Ten steps of 1 s equals one step of 10 s (`test_one_second_steps_match_ten_second_steps`).

`apply_impulses` and `step(..., time_elapsed=0)` add impulses only: no retention, baseline motion, or norm-cap update. `advance(dt)` advances time with no impulses. Full `step` integrates over `dt` first, then applies impulse sums at the **end** of the interval.

---

## 2. Baseline and setpoint `b0`

| Field | Role |
| --- | --- |
| `baseline` | Slow allostatic level; tracks sustained axis offset |
| `baseline_setpoint` (`b0`) | Fixed personality anchor; copied from `baseline` at construction; **no new genome gene** |

`baseline_adapt_rate` is **per simulated second**. Default `1/(6×3600) ≈ 4.63×10⁻⁵` (τ ≈ 6 h toward the lived axis). Gene `af_baseline_adapt_rate`: range `[0, 0.01]`, default and sigma halved vs the old per-step default (see genome table in [SPEC_A_GenomeVector.en.md](../SPEC_A_GenomeVector.en.md)).

Recovery of `baseline` toward `b0` uses `0.25 × baseline_adapt_rate` (τ ≈ 24 h). Under chronic stress, axis and baseline equilibrate with baseline roughly **80%** of the way from `b0` toward the sustained axis deviation (allostatic load does not accelerate while asleep).

---

## 3. Sleep

During consolidation cycles, `AffectiveSpace.step(..., asleep=True)`:

- Clears axis deviation toward baseline and baseline toward `b0` with `SLEEP_RECOVERY_SCALE = 4` (sleep does **not** speed chronic load acquisition).
- Uses `time_elapsed` from `SleepManager._affective_cycle_dt()`.

`deep_sleep(cycles, sleep_duration_seconds=…)` splits total simulated sleep evenly across cycles. If `sleep_duration_seconds` is omitted, total time is `cycles × SECONDS_PER_SLEEP_CYCLE` (`1800` s). Standalone `sleep_cycle()` advances one `SECONDS_PER_SLEEP_CYCLE` slice.

---

## 4. Agent and hosts

| Path | `time_elapsed` |
| --- | --- |
| Normal `Agent.step` / commit | Host `dt` from `_advance_host_clock` |
| `decision_only=True` | Recall via `apply_impulses` (`0`); single affect advance on `commit_executed_transition` with host `dt` |
| `mcp_body/_compat.apply_impulses`, VC `training_loop` impulse calls | `0` (impulse-only) |
| `AffectivePersistence` / `AffectiveBackground` updates from agent | Host `dt` (not “one call = one second” when `dt=0`) |

---

## 5. `.nowa` persistence

`baseline_setpoint` is stored in the affective block. If the key is missing on load, each axis falls back to the loaded `baseline` for that axis (`AgentStorage` / `tests/test_affective_time.py::test_setpoint_roundtrip_and_missing_field`).

**Backward compatibility:** Saves that store the old default `baseline_adapt_rate = 0.002` are interpreted as **per second** (τ ≈ 8 min), not per decision.

---

## 6. Known limitations (core, part 1)

| Item | Behavior |
| --- | --- |
| `src/swarm.py` social fallback | Calls `affective_space.step(inputs=…)` without `time_elapsed` → default **1.0** simulated second per signal |
| Colony `deep_sleep` / alarms | Demo passes `sleep_duration_seconds=0.0` and related wiring — tracked for part 2 |
| `test_tc05` Colony | `_is_emitting_alarm` frozen so lawful stress can cross alarm threshold `0.7` under new dynamics |