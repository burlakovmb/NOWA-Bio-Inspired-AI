# Issue #13 — Virtual company employee on two-tier plasticity

Russian: [issue-13-demo-virtual-company.ru.md](issue-13-demo-virtual-company.ru.md)

Stage: adapt the employee host of `Demo/Virtual company` to the merged core (PRs #37, #40, #41).
The core in `src/` is not retuned for the employee. Host rules: [Docs/architecture/two-tier-plasticity.en.md](../architecture/two-tier-plasticity.en.md).
Normative core spec: [issue-13-two-tier-plasticity.en.md](issue-13-two-tier-plasticity.en.md).
Other hosts, used as the pattern: [issue-13-demo-colony.en.md](issue-13-demo-colony.en.md), [issue-13-demo-tamagochi.en.md](issue-13-demo-tamagochi.en.md).
Body lessons used here: [NOWA_Body_Lessons.en.md](../../Demo/Virtual%20company/Docs/NOWA_Body_Lessons.en.md).

---

## 1. Goal

The employee is a core `Agent` (`AgentFactory.spawn_default`) driven by the employee's `BusinessAgentRuntime` (`Demo/Virtual company/src/nowa_body/runtime.py`), a subclass of the platform runtime (`src/mcp_body/runtime.py`, not changed). The same runtime drives the Body Lab (`nowa_body/lab_session.py`, through `GuidedAgent`).

- Every decision cycle supplies host `dt` (seconds) on the host-clock contract.
- Waking outcomes (approvals, rejections, body lessons) stay in the labile tier.
- Stable parameters change only inside `Agent.sleep()`.

## 2. Host time

`run_cycle(observations, now)` computes `dt` once per cycle (`_host_dt`):

- `simulated_tick_seconds`, when the host sets it (the employee sets it to its tick interval: it is what the host says a tick is);
- otherwise the gap between this cycle's `now` and the previous one; the first cycle is `0`.

The runtime passes `dt` to `step(..., decision_only=True, dt=dt)` when `step` declares a `dt` parameter. A `**kwargs` wrapper does not count. Otherwise, and when the agent has no `step`, it calls `advance_time(dt)`. The wall-clock fallback in the core is not used. `GuidedAgent.step` forwards `dt` to the inner agent; a forced lab action skips the mind but still calls `advance_time(dt)`.

`expected_wake_interval_s` comes from the sleep schedule (`SleepScheduler.expected_wake_interval_s`):

- nightly window and no fatigue trigger: `max(24 h, min_interval_s)`;
- fatigue trigger set: the anti-thrash interval (`min_interval_s`, or `min_ticks_between_sleep × seconds_per_tick` in the lab), the shortest span after which sleep can come.

With the employee defaults (window 02–05, fatigue 0.85, `min_interval_s` 3600) this is `3600` s. The procurement experiments ran with fatigue off and got `86400` s. `tau_labile_s` stays the core default (`1.0 ×` the interval).

`configure_plasticity(agent, scheduler)` writes that value right after the employee or the lab agent is spawned, before the first cycle, and again after a checkpoint load, since the checkpoint may carry an older one. The core is not changed: `AgentFactory` builds the agent with the default `PlasticityConfig`, so the core logs "`expected_wake_interval_s` is unset" once at construction; the `3600` s fallback is never used, because the value is set before the first cycle. Passing the config through `AgentConfig` would remove that warning; it is a core change and is left to a separate issue.

## 3. Sleep

When `SleepScheduler.should_sleep` says so, the runtime calls `Agent.sleep(cycles=sleep_cycles)` (default 1). That runs the two-tier capture of Go/NoGo tags and habits, then replay. `sleep_manager.sleep_cycle()` is used only for agents without `sleep` (lab stubs). `mark_slept` runs only after a successful sleep.

## 4. What may be written while awake

| Writer | Now |
| --- | --- |
| Approval feedback (`apply_feedback_to_agent`) | Hippocampal episode + `Agent._record_known_outcome` (labile tag, continuous reward) through `store_lesson` |
| Body lessons (`runtime.teach`: strict-binding miss, business-limit block) | Same path |
| Rejection | Lesson "wait" via `store_lesson`; `record_action_outcome` updates selection counts only |
| Affect impulses from reads and outcomes | State, may move while awake |

## 5. Initialization and load

- Role seeds (`HippocampusSeeder`) write hippocampal episodes, which are state, not the stable tier (see [NOWA_Body_Lessons.en.md](../../Demo/Virtual%20company/Docs/NOWA_Body_Lessons.en.md) §5). Strict-mode tests raise no `WakingLearningError` on spawn + seed.
- The mind checkpoint (`save_mind` / `load_mind`, `AgentStorage`) loads in strict mode, and a labile tag written before `save_mind` is present after `load_mind`.

## 6. Check

`Demo/Virtual company/tests/test_two_tier_host.py`, with `NOWA_STRICT_LEARNING=1` and a fixture that fails the test if a `WakingLearningError` was raised and caught:

- nightly schedule → `86400`; fatigue → anti-thrash interval; lab ticks → `min_ticks × seconds_per_tick`; a core agent gets the value, a stub is left alone;
- an employee spawned with its schedule has the interval before its first cycle; the lab agent likewise, on the core backend;
- four cycles 15 min apart add `3 × 900` s to `_host_clock_s` and leave `_dt_warning_sent` false; `simulated_tick_seconds` wins over the cycle clock;
- a day of cycles and a lesson leave `stable_fingerprint` unchanged and tag the labile tier; the night's sleep changes the fingerprint and marks the lesson `consolidated`;
- a lesson is consolidated once.


Effect on the procurement employee (VC simulator, hard world, 30 simulated days, 5 seeds): without the adaptation the day-30 probe on seed 21 is 81 (92 before #13); with it day 10 86 ± 6, day 30 83 ± 3, overspend 0.

## 7. Out of scope

- `Demo/Virtual company/src/nowa_sandbox/` (the procurement sandbox): its training loop still calls `sleep_manager.sleep_cycle()` and passes no `dt`. Tracked in a separate issue.
- The platform runtime `src/mcp_body/runtime.py`: it still calls `step` without `dt` and sleeps through `sleep_manager.sleep_cycle()`. The employee overrides `run_cycle` and the decision cycle in the demo; fixing the platform runtime is a core change for the maintainer.
- Core fallbacks, replay caps, plasticity coefficients.
- Save/load gaps of the core (#16).

## 8. Acceptance

1. Employee and lab cycles pass host `dt`; no wall-clock fallback warning.
2. `expected_wake_interval_s` comes from the schedule before the first cycle and after load, not from the core fallback of `3600` s.
3. Waking outcomes do not change `stable_fingerprint`; `Agent.sleep()` does, once per lesson.
4. `pytest -m "not slow"` of `Demo/Virtual company` passes. The cognitive core is not changed.
