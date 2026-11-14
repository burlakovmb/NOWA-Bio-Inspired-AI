# Issue #13 — Tamagochi demo on two-tier plasticity

Stage: adapt `Demo/Tamagochi Chinchilla` to the merged core (PRs #37, #40, #41).
The core in `src/` is not retuned for the cage. Host rules: [Docs/architecture/two-tier-plasticity.en.md](../architecture/two-tier-plasticity.en.md).
Normative core spec: [issue-13-two-tier-plasticity.md](issue-13-two-tier-plasticity.en.md).
Colony host, used as the pattern: [issue-13-demo-colony.md](issue-13-demo-colony.en.md).

---

## 1. Goal

`ChinchillaAgent` in `Demo/Tamagochi Chinchilla/src/main.py` is a host of the general-purpose core. It is not a subclass of `Agent`. The cage keeps its own chain loop, pygame timing, and the objects it already built (`value_layer`, `bg_channels`, hippocampus, cortex, intent memory, sleep manager, external interaction layer).

After load, `_bind_two_tier_host` constructs one core `Agent` (`self.nowa`) with `sleep_manager=None` (so `Agent.__init__` does not replace the cage's value layer) and `PlasticityConfig(expected_wake_interval_s=...)`. `_rewire_two_tier_host` then points that agent at the cage's objects and attaches `labile`, `plasticity`, and `_host_agent` on the cage's `SleepManager`.

- Every simulation tick supplies game `dt` on the host-clock contract.
- Waking chain outcomes stay in the labile tier.
- Stable parameters change only while a sleep behavior runs `SleepManager.deep_sleep` / `sleep_cycle` (both open `learning_allowed()`). Go/NoGo and habit strength are written once, inside `deep_sleep`. The cage does not run a second BG step afterwards.
- `SleepManager` is constructed with the cage `intent_memory`, and `_rewire_two_tier_host` sets that same object again. Capture's `apply_outcome` therefore updates the trace `note_selection` created.
- Construction, JSON restore of channel weights, and registration of a new dynamic-chain channel run under `initializing()`.

## 2. Host time

`sim_step(dt)` calls `nowa.advance_time` once with that game `dt`.

The cage does not call `Agent.step`. `step` would run the core decision pipeline and `wakefulness.update_waking()` with no elapsed argument, which reads the wall clock. The cage already integrates wakefulness, affect, and action timers from `dt`. `advance_time` moves only the core host clock and decays labile tags. It does not take the wall-clock fallback. Non-finite or negative `dt` is passed as `0`, which is still an explicit `dt`.

The render loop accumulates wall time and drains it in steps of `SIM_DT` (0.1 s). Action durations in config are in the same seconds. One realtime second is one host second while the loop keeps up. `dt` is that sim second, not a separate compression factor.

`expected_wake_interval_s` is `tamagochi_expected_wake_interval_s()`:

- sleep pressure accumulates at `1 / (4 * 3600)` per waking host second (the rate installed on the cage's `WakefulnessState`);
- bedtime is boosted once pressure exceeds `0.7` (`_build_candidate_chains`);
- the climb from full rest (pressure 0) to that onset is `0.7 * 4 * 3600 = 10080` host seconds.

The first session starts at pressure `0.1`, so its first climb is `8640` s. The configured value is the rested-to-onset span, not that first climb, not the `1200` s circadian tint (`SchedulingSystem.cycle_period`, suggestion bias only), and not the core fallback of `3600` s. `tau_labile_s` stays the core default (`1.0 *` the interval).

Stable consolidation is still the cage's existing schedule, not a new one:

- a sleep behavior (`bedtime_routine`, `extreme_fear`, or actions `sleep_house` / `doze_shelf` / `hide_house`) and pressure `< 0.3` → `deep_sleep(cycles=2)`;
- the same behaviors and pressure in `[0.3, 0.5)` → one `sleep_cycle`.

`deep_sleep` runs the two-tier capture because the sleep manager's `_host_agent` is the core agent. A waking tick does not call either.

## 3. What may be written while awake

A finished chain stores one hippocampal episode, then `_commit_waking_chain_outcome` calls `Agent._record_known_outcome`. That tags `L_Q` and `L_go` / `L_nogo` and sets `td_outcome_committed` for later capture. It does not call `ValueLayer.update`.

Removed or redirected daytime stable writers:

| Call | What happened | Now |
| --- | --- | --- |
| `value_layer.update(mode="online")` on chain end | Stable Q. Production skipped it; strict mode raised `WakingLearningError` | Labile tag via `_record_known_outcome` |
| `intent_memory.strengthen_trace` | Stable habit strength. Same skip / raise | `note_selection` (strength 0 until sleep) |
| `intent_memory.record_trace` when a chain starts | Stable strength (`+= 1`). Strict mode raises `WakingLearningError`; the caller used to catch `Exception` and hide it | `note_selection` on the pre-chain context. That context is stored on the episode, so sleep `apply_outcome` updates the same trace. The call is not wrapped in `except Exception` |
| `ActionChannel.update_weights` when `demo_training_mode` | Stable Go/NoGo/habit. Same skip / raise | Removed. The flag remains. The labile tag is the waking trace |
| `eil.apply_learning_hooks` on an owner rating | Stable strategy weights. Same skip / raise | Rating is queued. `_flush_owner_feedback` runs inside `learning_allowed()` on the next light or deep sleep. Coefficients (`alpha=0.15`, `learning_rate=0.08`) are unchanged |
| New dynamic-chain channel | New `ActionChannel` while awake | `nowa.register_action_channel`, which enters `initializing()` |

`ActionChannel.record_outcome` still runs while awake. It updates selection counts, not `go_weight` / `nogo_weight` / `habit_strength`.

After `deep_sleep` returns, the cage does not call `apply_sleep_learning` or `consolidate_habits`, and it does not replace channel objects. Those methods were a second Go/NoGo/habit step on the same night. Owner-rating flush still runs inside `learning_allowed()`. Intent traces are then modulated and `degrade_unused(0.85)` runs, after capture has already applied the outcome, so a strength-0 selection trace is not deleted before it is strengthened.

Fast affect, neuromodulator levels, wakefulness, drives, and the scheduling cycles remain state and may move while awake.

## 4. Initialization and load

- Channel objects are built in `__init__` before their weights are sealed.
- `load_nowa_state` still assigns saved `go_weight` / `nogo_weight` / `habit_strength` inside `initializing()`.
- The same JSON now also stores `plasticity`, `labile`, `host_clock_s`, and `pending_owner_feedback`. Restore happens before `_rewire_two_tier_host`.
- `AgentStorage.load_agent` / `save_agent` receive the cage as `agent`. Once `labile`, `plasticity`, and `bg_action_channels` live on the cage, the core storage path persists them in `agent_save.nowa` (`nowa-agent-state` schema `1`). After either load, `_rewire_two_tier_host` points `nowa` at the restored value layer, channels, labile layer, and clock.
- Legacy pickle session files (`.pkl`) are rejected; recreate the session save from the running demo. See [issue-16-31-safe-agent-state.en.md](issue-16-31-safe-agent-state.en.md).

## 5. Check

`Demo/Tamagochi Chinchilla/tests/test_two_tier_host.py`, with `NOWA_STRICT_LEARNING=1`:

- `expected_wake_interval_s` is `10080`;
- four waking `sim_step(1)` leave `stable_fingerprint(nowa)` unchanged, add `4` to `_host_clock_s`, and leave `_dt_warning_sent` false;
- one waking chain outcome tags a channel offset and still does not change the fingerprint;
- `_run_sleep_consolidation` changes the fingerprint;
- `sleep_manager.intent_memory` is the cage memory, and a strength-0 selection trace is still present with strength `> 0` after that sleep;
- channel object identity and Go/NoGo/habit weights after `deep_sleep` match the weights after `_run_sleep_consolidation` returns;
- starting a chain with `sim_step` does not raise `WakingLearningError`.

An autouse fixture in that file counts `WakingLearningError` instances. If one was raised and caught, the test fails. The tamagochi suite under strict mode must not raise `WakingLearningError`.

## 6. Demo-specific (not a core requirement)

- The cage does not subclass `Agent` and does not call `Agent.step` or `Agent.sleep`. `SleepManager.deep_sleep` is the only Go/NoGo and habit writer that night, with the core agent attached as `_host_agent` and the cage `intent_memory` on the manager.
- Affective background, semantic emotions, emotional memory, emotional expectations, and conflict-arbitration outcome stats stay free-standing. `_stable_owner` is not set on them, so the guard does not treat them as the core stable tier. The live HUD and `test_additional_nowa_layers_update` still update them while awake. They are not part of `stable_fingerprint(nowa)` (that fingerprint reads the core agent's own copies, which the cage does not write).
- `demo_training_mode` no longer changes stable weights during the day.
- Owner ratings update strategy weights on the next sleep, not on the click.
- One `sleep_house` lasts 240–960 s and drops pressure by at most `960 / (2 * 3600) ≈ 0.133`. A bout that starts at 0.7 can end above the 0.5 consolidation band. That schedule is unchanged.

## 7. Out of scope

- Core fallbacks, replay caps, and plasticity coefficients.
- Colony, Virtual company, Warriner Validation.
- pygame UI.

## 8. Acceptance

1. Cage ticks pass game `dt` through `advance_time` and do not use the wall-clock fallback.
2. `expected_wake_interval_s` is `10080`, not `3600`.
3. Waking chain outcomes and owner ratings do not change `stable_fingerprint(nowa)`. Sleep through `_run_sleep_consolidation` does, once per night for Go/NoGo and habit, without replacing the channel object. The selection trace is strengthened by capture's `apply_outcome`.
4. Channel restore and new channel registration run under `initializing()`.
5. `pytest` of `Demo/Tamagochi Chinchilla` passes with and without `NOWA_STRICT_LEARNING=1`. A swallowed `WakingLearningError` fails the host tests. `src/` is unchanged.
