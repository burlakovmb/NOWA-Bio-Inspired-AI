# Two-tier plasticity (NOWA core)

Russian: [two-tier-plasticity.ru.md](two-tier-plasticity.ru.md)

Normative detail: [Docs/specs/issue-13-two-tier-plasticity.en.md](../specs/issue-13-two-tier-plasticity.en.md).  
Sleep cycle ordering: [Docs/SLEEP.en.md](../../Docs/SLEEP.en.md).  
API surface: [Docs/API.en.md](../../Docs/API.en.md).

The cognitive core in `src/` is a **general-purpose engine**. Host applications supply time, outcomes, and when to sleep; they are not part of this document. Sample hosts live under `Demo/` and are mentioned only in [Demo hosts](#demo-hosts) below.

## Tiers

| Tier | What it holds | When it writes |
|------|----------------|----------------|
| **Stable** | `ValueLayer` Q/V and expectation stats; stable action visit counts; habit trace strengths (&gt; 0); BG `go_weight` / `nogo_weight` / `habit_strength`; cortex patterns; temporal chains; external strategy weights and learned selector metadata; slow affective statistics; neuromodulator baselines (in fingerprint) | Only inside `Agent.sleep()` under `learning_allowed()` |
| **Labile** | Bounded offsets `L_Q`, `L_go`, `L_nogo`; per-episode contributions; waking visit counters (no decay) | While awake, when an outcome is committed |
| **State** | Neuromodulator levels, fast affect (space position, valence/arousal, regulation output), wakefulness, working context, hippocampal episodes, host clock | Waking and sleep (not in `stable_fingerprint`) |

**Invariant W:** Between two `Agent.sleep()` calls, `stable_fingerprint(agent)` is unchanged no matter what waking APIs run.

**Invariant S:** Stable parameters change only in the consolidation path opened by `Agent.sleep()`. Each episode with a known outcome is consolidated **at most once** per sleep night (a rating change *after* consolidation is a **new** observation on the next sleep, not a rollback).

**Selection:** Effective values use stable + labile: `Q_eff = Q_stable + L_Q`, `go_eff = clamp01(go_stable + L_go)`, same for NoGo. Habit strength in the gate is the **stable** trace only.

## Waking learning (`LabileLayer`)

Implementation: `src/labile_layer.py`, wired from `Agent.step`, `commit_executed_transition`, and `apply_feedback_to_last_experience`.

When an outcome is known:

- TD error δ is computed on **effective** Q.
- `ΔL_Q = clamp(η_L · g_DA · δ, ±a_step)` then clamp total `L_Q` to `±A_Q`. Default `η_L = 0.1 × alpha_reference` (with `alpha_reference` usually `ValueLayer.alpha_default`, 0.03 → `η_L ≈ 0.003`). Defaults: `a_step = 0.05`, `A_Q = 0.2`.
- Channel tags: for `r > 0`, `ΔL_go = η_Lc·r`, `ΔL_nogo = −½η_Lc·r`; for `r < 0`, magnitudes swap with the ½ factor on Go. Defaults: `η_Lc = 0.02`, `A_c = 0.1`.
- **`g_DA` is fixed at 1** (not scaled by dopamine level).
- Habits: `intent_memory.note_selection` may create a **strength-0** trace; outcome does not change habit strength while awake.
- **Rewards:** `NaN` = unknown (no labile write). `±inf` → `±1` on `step` / `commit_executed_transition`. Integer feedback uses a separate parser (see discrepancies in the PR if docs and paths differ).

**Decay:** `L ← L · exp(−Δt/τ_L)` lazily per entry. Host time advances by `dt` on waking calls or `agent.advance_time(dt)`. Default `τ_L = tau_labile_ratio × expected_wake_interval_s` (ratio default `1.0`). If `expected_wake_interval_s` is unset, the core logs once and uses **3600 s**. Entries with `|L| < labile_epsilon` (`1e-6`) are dropped.

**Idempotent feedback:** Same rating → no-op. Changed rating → remove the episode’s stored contribution (with the same decay as tags), apply the new one once.

**Visits:** Waking increments labile visit counters; they **do not decay**. Sleep transfers them into `_action_visit_counts` and clears the labile counter (`take_visits()`).

## Learning guard

Implementation: `src/learning_guard.py`.

| Context | Purpose |
|---------|---------|
| `learning_allowed()` | Entered by `Agent.sleep()` / `SleepManager.deep_sleep()` for the two-tier pass and stable writers |
| `initializing()` | Construction, load, host seeding; `register_action_channel` enters this **internally** |
| `NOWA_STRICT_LEARNING=1` | Core tests: stable write while awake → `WakingLearningError` |
| Production (unset) | Log once per writer name and **skip** the write |

Only the sleep path opens the guard for learning. `SleepManager._apply_replay_td_bg` does **not** open it; a direct daytime call raises (strict) or skips (production).

## `stable_fingerprint` and `labile_snapshot`

`stable_fingerprint(agent)` is SHA-256 of canonical JSON for category A:

- `value_layer` (values + expectation_memory)
- `visit_counts` (stable `_action_visit_counts`)
- `intent_strengths` (traces with strength &gt; 0 only)
- `channels` (Go/NoGo/habit + priors)
- `cortex` patterns
- `temporal_chains`
- `strategies` (external strategy weights, selector `strategy_weight` metadata, `bg_learning_rate`, neuromodulator baselines, serialized `PlasticityConfig`)
- `slow_affect` (background, semantic emotions, emotional memory, expectations, conflict outcome stats — timestamps stripped)

**Not** in the fingerprint: labile offsets, hippocampal episodes, fast affect state, live neuromodulator levels, host clock, RNG.

`labile_snapshot(agent)` materializes the labile tier at `_host_clock_s`.

## Host integration (embedding apps)

1. **Construct** `Agent(..., plasticity_config=PlasticityConfig(expected_wake_interval_s=...))` with the mean waking interval between sleeps in **your** time units.
2. **Every waking tick**, pass the same units: `agent.step(..., dt=Δt)` and/or `commit_executed_transition(..., dt=Δt)`, or call `agent.advance_time(Δt)` when no step runs.
3. **Sleep** when your application’s schedule says so: `agent.sleep(cycles=...)`. Without sleep, stable memory never updates (by design).
4. **Register channels** for new actions: `register_action_channel(action_id)` (stable seeding under `initializing()`).
5. **After load**, wrap any manual stable seeding in `with initializing(): ...`.
6. **Tests / CI:** set `NOWA_STRICT_LEARNING=1` to catch accidental stable writes while awake.

`PlasticityConfig` is persisted in agent save/load with the labile layer and host clock.

On disk these fields live in a `nowa-agent-state` JSON document (schema version `1`, extension `.nowa`), not pickle. See [issue-16-31-safe-agent-state.en.md](../specs/issue-16-31-safe-agent-state.en.md). Legacy `.pkl` saves are rejected; recreate checkpoints after upgrading.

## Demo hosts

Under `Demo/`, each sample application chooses its own sleep schedule and should pass `dt` and `expected_wake_interval_s` to match simulation time. Adapting demos is separate from core documentation; see the appendix in issue #13 spec.
