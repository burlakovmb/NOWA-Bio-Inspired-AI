# Issue #54 — Affective core in simulated seconds

Russian: [issue-54-affect-simulated-time.ru.md](issue-54-affect-simulated-time.ru.md)

**Part 1 (core):** PR #72 — `src/…`, `tests/test_affective_time.py`.  
**Part 2 (Colony demo):** PR #73 — `Demo/Colony chinchillas/src/colony_agent.py`, `colony_storage.py`, `tests/test_issue_54_alarm.py`, `src/swarm.py` (§7).

Code (core): `src/affective_space.py`, `src/agent.py`, `src/sleep.py`, `src/storage.py`, `src/genome.py`, `src/affective_persistence.py`, `src/affective_background.py`, `src/mcp_body/_compat.py`, `Demo/Virtual company/src/nowa_sandbox/training_loop.py`.

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
| Colony alarm / host `dt` | Addressed in §7 (part 2) |
| `src/swarm.py` social fallback | Fixed in part 2: `time_elapsed=0.0` (§7) |

---

## 7. Part 2 — Colony demo

PR #73. Host: `ChinchillaAgent.sim_step` in `Demo/Colony chinchillas/src/colony_agent.py`. Tests: `Demo/Colony chinchillas/tests/test_issue_54_alarm.py`.

### 7.1 Impulses vs affect integration

| Path | Behavior |
| --- | --- |
| `_apply_affect_impulse` | `affective_space.apply_impulses(inputs=…)` only — **no** retention / baseline / norm-cap for that call. Rates such as `stress * dt` stay scaled by the caller. |
| Awake `sim_step` | `step(…, decision_only=True, dt=host_dt)` advances affect once; `commit_executed_transition` does not add a second host `dt`. |
| Need-sleep tick (no `step`) | `advance_time(host_dt)` then `_advance_affect_while_asleep(host_dt)`: zeros `_pending_commit_context` `time_elapsed` and `step_elapsed`, then `affective_space.advance(elapsed, asleep=True)`. Commit gets `affective_inputs` all `0.0` so the waking appraisal does not cancel sleep recovery. |
| `deep_sleep(…, sleep_duration_seconds=0.0)` | Affect already advanced once per tick while asleep; a non-zero bout duration would **double-count** the same interval inside `deep_sleep`. |

### 7.2 Alarm as an acute event (not `stress > 0.7`)

Constants at top of `colony_agent.py` (symbols `ALARM_*`).

| Parameter | Value | Role |
| --- | ---: | --- |
| `ALARM_RISE_WINDOW_S` | 4.0 | Stress trace window for rise |
| `ALARM_RISE_MIN` | 0.35 | Min rise in window to open a bout |
| `ALARM_REFRACTORY_S` | 15.0 | Pause before another bout |
| `ALARM_CALL_AUDIBLE_S` | 2.0 | Emitter visible to neighbours |
| `ALARM_KNOWN_STRESS` / `ALARM_UNKNOWN_STRESS` | 0.30 / 0.15 | Base stress impulse (× scale below) |
| `ALARM_AROUSAL` | 0.10 | Arousal impulse (× scale) |
| `ALARM_IMPULSE_INTENSITY` | 0.7 | Passed to `apply_impulses` |
| `ALARM_SLEEP_HEARING_GAIN` | 0.35 | Listener gain while sleeping |
| `ALARM_BUFFER_AFFINITY` | 0.65 | Min partner `affinity` for buffer |
| `ALARM_BUFFER_GAIN` | 0.60 | Impulse multiplier when buffered |
| `ALARM_HABITUATION_RETAIN` | 0.60 | Sensitivity after each heard bout |
| `ALARM_HABITUATION_FLOOR` | 0.30 | Minimum sensitivity to a caller |
| `ALARM_HABITUATION_TAU_S` | 120.0 | Recovery time constant (~2 min quiet) |

**Emit:** `_ensure_alarm_call` (via `_is_emitting_alarm`). Sleeping agents do not bark (`_alarm_call_open` cleared). A bout needs rise ≥ `ALARM_RISE_MIN` over `ALARM_RISE_WINDOW_S` against `_alarm_stress_trace`; a level that merely stays high does not retrigger. One `event_id` per bout; refractory blocks chains on fast ticks.

**Hear:** `_perceive_alarm_calls` (from `_social_step`). Caller in **same or adjacent zone** (`is_same_or_adjacent`). At most **one** impulse per `(listener, caller, event_id)` via `_alarm_heard`. Familiar caller (`knowledge`) uses `ALARM_KNOWN_STRESS`; stranger uses `ALARM_UNKNOWN_STRESS`. Scales: `_alarm_caller_gain` (habituation), `_alarm_social_buffer` (bonded neighbour other than caller), sleep hearing gain.

**Anchor on load/create:** `_anchor_alarm_stress` so a high saved stress is not treated as an in-window spike.

Context tag `alarm_call` still comes from perceived `affect_tone == "fearful"`, not from a fixed stress threshold.

### 7.3 Colony save — `runtime.alarm`

`ColonyStorage` writes `runtime.alarm` from `_export_alarm_state()` (`refractory_until`, `event_id`, `event_until`, `call_open`, `emit_count`, `stress_trace`, `habituation`, `heard`). Load calls `_restore_alarm_state` or `_anchor_alarm_stress()` when the key is missing (legacy saves with high `affect.stress` do not auto-bark).

### 7.4 `src/swarm.py` fallback

`SwarmEnvironment.apply_social_signal`: if only `step` exists, `time_elapsed=0.0` (impulse-only; avoids default 1 s per signal). Covered by `tests/test_swarm_environment.py`.

---

## 8. Known limitations (part 2)

| Item | Status |
| --- | --- |
| Reproduction gated by **slow** cortisol dynamics | **Not implemented** — mating still uses instantaneous cortisol in `_apply_reproduction` / `ReproductiveSystem.update`. |
| Awake `commit_executed_transition` | Reward-derived affective appraisal is **not** scaled by host `dt`; under chronic stress the stress axis can sit **~0.78** while recovery and impulses fight the commit term. |
| `AffectivePersistence` clock on need-sleep ticks | `affective_persistence.update` runs from `Agent.step`; mandatory sleep skips `step`, so trace decay / clocks do not advance for that tick. |