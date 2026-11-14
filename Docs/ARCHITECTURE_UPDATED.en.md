# System Architecture

Russian version: [ARCHITECTURE_UPDATED.ru.md](ARCHITECTURE_UPDATED.ru.md)

**Status (27 September 2026).** This file is a phase inventory as of March 2026. The current architecture of the complex is stated in [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The historical phase survey is retained below.

**Version**: 3.5  
**Updated**: March 22, 2026 - slow tonic dopamine integration synced in ValueLayer docs  
**Status**: Production Ready (Phase 6 + EDPC + decision arbitration + HIE-003/HIE-002 + credit assignment + autonomous runtime + external layer integrated)

---

## Executive Summary

NOWA (Neuro-Optimized Waking Observer Agent) - a biologically-inspired cognitive architecture implementing:

1. **Phase 1**: Foundational affective and memory systems
2. **Phase 2**: Neuromodulator regulation system
3. **Phase 3**: Basal Ganglia action selection (Go/NoGo gating)
4. **Phase 3.5**: Affective Persistence (durable affect traces)
5. **Phase 3.75**: Affective Background Field (inertial field + lifetime modulation)
6. **Phase 4**: Affective Core (canonical continuous affective state)
7. **Phase 4.1**: Semantic Emotions (interpretation layer)
8. **Phase 4.2**: Emotional Memory & Narratives (retrospective layer)
9. **Phase 4.3**: Emotional Expectations (prospective layer)
10. **Phase 4.4**: Emotional Regulation (expectation-based stabilization)
11. **Phase 4.5**: Stability Monitoring (read-only diagnostics & drift control)
12. **Phase 5.0/5.0.1**: Value Layer (TD learning + dopamine TD coupling)
13. **Phase 5 (EDPC)**: Expectation memory, confidence/stability accumulation, prediction-shock plasticity
14. **Spec 011 + Planning v2 + HIE-003**: Decision Arbitration + Deliberative Planning (uncertainty, reliability, episodic rollout, imagination tree/structured fallback, VOI bonus)
15. **Spec 011a**: Reward-anchored replay Credit Assignment (causal depth + eligibility traces)
16. **Phase 6.1**: Acetylcholine modulation (novelty-driven selectivity)
17. **Phase 6.2/6.2.1 + SAC**: Filtered Consolidation + Semantic Action Consolidation (sleep-only semantic update)
18. **Autonomous Organism (Spec v1)**: Real-time lifecycle, drives/energy/speech governance, physiology diagnostics
19. **External Interaction Layer**: environment bridge with delayed feedback, nonlinear drive updates, and strategy-policy coupling

All phases work together in a unified system.

---

## System Overview

```
┌─────────────────────────────────────────────────────┐
│                   AGENT                             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────────────────────────────────────┐  │
│  │  BASAL GANGLIA (Phase 3) - Action Selection  │  │
│  │  ├─ ActionChannels (Go/NoGo)                │  │
│  │  ├─ Softmax selection with temperature      │  │
│  │  ├─ PFC advisory integration                │  │
│  │  └─ Habit strength learning (×0.3)          │  │
│  └─────────────────────────────────────────────┘  │
│                         ↓⬅️⬆️↓                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  NEUROMODULATOR SYSTEM (Phase 2)             │  │
│  │  ├─ Dopamine (motivation)                   │  │
│  │  ├─ Cortisol (stress)                       │  │
│  │  ├─ Norepinephrine (attention)              │  │
│  │  └─ Serotonin (mood)                        │  │
│  └──────────────────────────────────────────────┘  │
│                         ↓⬅️⬆️↓                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  AFFECTIVE SYSTEM (Phase 1)                  │  │
│  │  ├─ Valence (positive/negative)             │  │
│  │  ├─ Arousal (calm/hyperactive)              │  │
│  │  ├─ Threat (safe/critical)                  │  │
│  │  └─ Curiosity (indifferent/exploring)       │  │
│  └──────────────────────────────────────────────┘  │
│                         ↓⬅️⬆️↓                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  AFFECTIVE PERSISTENCE (Phase 3.5)           │  │
│  │  ├─ Durable affective traces                │  │
│  │  ├─ Accumulation + slow decay               │  │
│  │  ├─ Uses T1/T2 baselines                    │  │
│  │  └─ No direct action influence              │  │
│  └──────────────────────────────────────────────┘  │
│                         ↓⬅️⬆️↓                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  AFFECTIVE BACKGROUND (Phase 3.75)           │  │
│  │  ├─ Inertial background field               │  │
│  │  ├─ Lifetime-modulated dynamics             │  │
│  │  └─ No direct action influence              │  │
│  └──────────────────────────────────────────────┘  │
│                         ↓⬅️⬆️↓                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  AFFECTIVE CORE (Phase 4)               │  │
│  │  ├─ 8 canonical axes [-1..1]                │  │
│  │  ├─ Dynamics: per-second axis_decay/lambda**dt + impulses + optional legacy compat │  │
│  │  ├─ Noise from wakefulness/uncertainty/conflict │  │
│  │  └─ No direct action influence              │  │
│  └──────────────────────────────────────────────┘  │
│                         ↓⬅️⬆️↓                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  SEMANTIC EMOTIONS (Phase 4.1)               │  │
│  │  ├─ Interpretation of affective space        │  │
│  │  ├─ Overlapping emotion attractors           │  │
│  │  ├─ Brief narrative summary (GUI only)       │  │
│  │  └─ No direct action influence               │  │
│  └──────────────────────────────────────────────┘  │
│                         ↓⬅️⬆️↓                        │
│  ┌──────────────────────────────────────────────┐  │
│  │  LEARNING SYSTEM                             │  │
│  │  ├─ Sleep consolidation (sleep only!)       │  │
│  │  ├─ Habit strength updates                  │  │
│  │  └─ Experience consolidation                │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Autonomous Organism Runtime (Spec v1, audited)

### Overview
Autonomous organism runtime adds continuous self-driven behavior on top of core cognition.
In GUI auto mode, the runtime advances in real time: `1 tick = 1 second`.

### Runtime Structure
1. `DriveSystem`: bounded autonomous drives (`[0..1]`) with affect and energy coupling.
   Active taxonomy: `curiosity`, `social_drive`, `goal_tension`, `exploration`, `energy_need`.
2. `EnergySystem`: energy and energetic fatigue dynamics with bounded recovery.
3. `InternalSimulationLoop`: drive-triggered internal cycles with hard rate limits.
4. `SpeechGovernor`: threshold + cooldown + interval controls for speech events.
5. `LifeLoopController`: optional loop helper with interval control.

`self_reflection` and `emotional_discharge` are no longer modeled as drives:
- `self_reflection` is represented as `agent_mode=REFLECTION`.
- affect discharge is represented as protective regulation (`regulate_affect`), outside drive competition.

### Internal Simulation Contract (current)
1. Simulation works only on hypothetical copies.
2. Action proposal and evaluation are split:
   - proposer: `ActionSelector.choose(...)`
   - evaluator: `ActionSelector.evaluate(hypothetical_state)`
3. Shared utility logic is centralized in `src/simulation_utility.py`.
4. Hypothetical drive seed is taken from live drive snapshot, not forced to `1.0`.
5. Final simulated action proposal follows the same gate path as live runtime:
   `compute_pressures -> BG.process -> ThalamicGate.select`.
6. Output contract includes:
   - `best_action`
   - `confidence`
   - `evaluated_variants`

### Physiology Model
Each tick is assigned a physiology mode:
- `idle`
- `passive`
- `internal_processing`
- `speaking`
- `low_energy`

Mode drives dynamic `cognitive_load` and `rest_time`.
This removes constant high-load behavior and enables fatigue recovery during idle.

### Tick Diagnostics
Per tick payload includes:
- base contract: `timestamp`, `dt`, `active_drive`, `energy_level`, `speech_event`, `internal_cycle_triggered`
- extended diagnostics: `dt_input`, `dt_clamped`, `physiology_mode`, `agent_mode`, `mode_signals`, `regulation`, `cognitive_load`, `load_components`, `energy_update`

### Failure and UI Semantics
Runtime writes structured records to `failure_log`.
GUI now distinguishes:
1. Critical errors (shown in `ошибки:N` link and details window).
2. Warnings/diagnostics (kept in runtime log but not counted as critical UI errors).

### Persistence
Save/load round-trip includes:
1. Autonomous runtime state (`drives`, `energy`, `speech`, `failures`, `tick_count`).
2. Wakefulness runtime state.
3. Post-restore tick contract compatibility.

---

## External Interaction Layer (implemented)

### Overview
Adds a dedicated environment-facing integration layer between runtime and the external world:
- observation ingest (manual and environment-polled)
- external action execution through environment interface
- delayed feedback queue and due-step resolution
- learning hooks that connect reward/feedback to drives, strategies, and policy.

### Learning Dynamics
1. Drive updates are nonlinear and bounded with:
   - `drive_decay`
   - `drive_saturation`
   - `drive_competition`
2. Strategy updates use:
   - logit-space update
   - `strategy_weight_decay`
   - softmax normalization with `strategy_temperature`
3. Drive-to-policy coupling is explicit:
   - `strategy_drive_coupling`
   - `drive_policy_gain`
   - selector pressure modulation through `action_metadata[*]["strategy_weight"]`.

### Runtime Integration Path
1. Agent receives feedback (`execute_external_action` / `resolve_external_feedback`).
2. External layer applies hooks (`apply_learning_hooks`).
3. Updated strategy weights are mirrored into selector metadata.
4. Selector pressure shifts policy while BG/Thalamic gate remains final arbiter.

### GUI Integration
`src/gui.py` exposes a dedicated RU panel:
- `Слой внешнего взаимодействия`
- observation controls (`источник`, `неопр.`, `данные JSON`)
- action controls (`действие`, `приор`, `задержка`, `прогноз`, `параметры JSON`)
- delayed feedback controls (`Обработать отложенные`, `Обновить статус`).

---

## Phase 3.75: Affective Background Field

### Overview
Introduces a slow-changing background field derived from durable affective traces.

### Key Properties
1. Inertial field computed from affective persistence traces (anxiety, tension, satisfaction, interest).
2. Lifetime progress modulates dynamics only (inertia, decay, competition sharpness).
3. Wakefulness influences update noise only.
4. No direct influence on action selection or neuromodulators.

### Main Components
1. Field Inertia: slower adaptation with higher lifetime progress.
2. Decay Modulation: older agents retain background longer.
3. Competition Sharpness: older agents converge to fewer dominant components.

---

## Phase 4: Affective Core (canonical)

### Overview
Implements a canonical continuous affective state `A(t)` used directly by decision paths.
Phase 4 now acts as the runtime emotional state integrator, while legacy fields remain
compatibility projections.

### Key Properties
1. Single source of truth: `AffectiveSpace.axes`.
2. Canonical axes are bounded per-axis in `[-1, 1]`.
3. Canonical update integrates per simulated second: retention `clamp(axis_decay−lambda_reg,0,0.999)**dt`, impulse sums at interval end (`AffectiveSpace.step` / `apply_impulses` / `advance`).
4. Recall impulses are constrained (per-impulse and total-share limits).
5. Runtime norm is bounded by dynamic cap (`dynamic_norm_cap`).
6. `dynamic_norm_cap` includes controlled growth and both conditional + global release.
7. Legacy additive dynamics are opt-in via `legacy_compat_weight` (default `0.0`).
8. Baseline adapts per simulated second via `baseline_adapt_rate`, with fixed `baseline_setpoint` (`b0`); sleep uses `asleep=True` and `SLEEP_RECOVERY_SCALE` (see [specs/issue-54-affect-simulated-time.en.md](specs/issue-54-affect-simulated-time.en.md)).

### Canonical Axes
- valence, arousal, dominance, stress
- trust, curiosity, stability, attachment

### Runtime Integration Notes
- Basal ganglia `choose()` receives canonical `affective_space`.
- Legacy `affect_state` is projected from canonical space for backward compatibility.
- Save/load includes dynamic baseline/cap/compat parameters.
- Selector `compute_pressures()` is cognitive-only in live pipeline;
  biological modulation is centralized in BG.
- `NO_ACTION` from thalamic gate is preserved (no random override).

### Metrics
- Distance: `D(A,B)=Σ w_i|A_i-B_i|`
- Speed: `V=|A(t)-A(t-1)|`
- Conflict: axis co-activation score over opposing pairs

---

## Phase 4.1: Semantic Emotions

### Overview
Interprets the affective space as a set of overlapping semantic emotion attractors.
This layer provides a stable semantic view of affective dynamics without driving behavior.

### Key Properties
1. Produces a list of active semantic emotions with activation, stability, and obsessiveness.
2. Emotions can co-exist and conflict; there is no normalization or suppression.
3. Obsessiveness derives from high inertia + low fall rate + high focus.
4. No direct influence on action selection or neuromodulators.

### Outputs
- `semantic_emotions`: list of `{emotion, activation, stability, obsessive}`
- `semantic_summary`: brief textual description (GUI-only, no behavioral effect)

### Integration
- Computed in `Agent.step()` after affective space update.
- Persisted in save/load state.
- Visualized in GUI (summary + detail list).

---

## Phase 4.2: Emotional Memory & Narratives

### Overview
Retrospective layer that aggregates semantic emotions into episodes and narratives.

### Key Properties
1. Builds time-bounded emotional episodes and consolidates recurring patterns with recency weighting.
2. Produces narrative fragments including temporal dominance and direction shifts (early vs recent).
3. Requires a minimum episode count before traits/patterns are rendered.
4. No direct influence on action selection or neuromodulators.

### Outputs
- `emotional_memory.episodes`
- `emotional_memory.patterns`
- `emotional_memory.narrative_fragments`
- `emotional_memory.character_traits`

### Integration
- Computed in `Agent.step()` after semantic emotions update.
- Persisted in save/load state.
- Visualized in GUI side panel (summary + metrics).

---

## Phase 4.3: Emotional Expectations

### Overview
Prospective forecasting layer built on emotional memory and semantic state.

### Key Properties
1. Estimates trend direction (increasing / stable / decreasing) from early vs recent episodes.
2. Produces probabilities and confidence in [0..1], with obsessive repetition risk handling.
3. Global outlook: stabilizing / volatile / escalating.
4. No direct influence on action selection or other layers.

### Outputs
- `emotional_expectations.expectations`
- `emotional_expectations.dominant_forecast`
- `emotional_expectations.global_outlook`

### Integration
- Computed in `Agent.step()` after emotional memory update.
- Persisted in save/load state.
- Visualized in GUI side panel (summary + metrics).

---

## Phase 4.4: Regulation Based on Expectations

### Overview
Regulatory layer that uses Phase 4.3 forecasts to gently stabilize background
and neuromodulators without influencing decision-making.

### Key Properties
1. Activation requires probability ≥ 0.8, confidence ≥ 0.6, risk_of_repetition = True,
   and global_outlook = "escalating".
2. Modes: stabilizing / dampening / containment (based on trend and confidence).
3. Adjustments are bounded: |delta| ≤ 0.1 per step and L2 norm ≤ 0.15.
4. No direct influence on action selection, memory, expectations, or affective space.
5. Neuromodulator adjustment is limited to serotonin only (DA/NE/CORT unchanged) to avoid indirect action selection effects.

### Outputs
- `emotional_regulation.regulation_active`
- `emotional_regulation.regulation_mode`
- `emotional_regulation.applied_adjustments`

### Integration
- Computed in `Agent.step()` after emotional expectations update.
- Applies small shifts to affective background and neuromodulators only.
- Persisted in save/load state.
- Visualized in GUI side panel (summary + deltas).

---

## Phase 4.5: Stability Monitoring & Drift Control

### Overview
Read-only diagnostic layer that monitors long-horizon stability of emotional dynamics,
background, neuromodulators, expectations, and Phase 4.4 activation frequency.

### Key Properties
1. Windowed analysis over configurable range: `500..2000` ticks.
2. Drift flags:
   - `regulation_overuse`
   - `background_drift`
   - `neuromodulator_drift`
   - `dominant_emotion_lock`
   - `outlook_bias`
3. Hysteresis for drift fixation: at least 2 consecutive windows (except regulation overuse).
4. Background baseline calibration uses warm-up median (not first-tick fixation).
5. No writes to affect/background/neuromodulators/memory/regulation.

### Outputs
- `stability_monitor.stability_index`
- `stability_monitor.drift_flags`
- `stability_monitor.recommendation`

Recommendation priority:
1. `inspect_regulation`
2. `inspect_neuromodulators`
3. `inspect_background`
4. `inspect_expectations`
5. `inspect_memory`
6. `none`

### Integration
- Computed in `Agent.step()` after Phase 4.4.
- Persisted in save/load state (`emotional_stability`).
- Visualized in GUI right panel and inspector.

---

## Phase 5.0/5.0.1 + Phase 5 EDPC: Value Layer, TD Error, Predictive Consolidation

### Overview
Value Layer introduces long-horizon state valuation via TD learning:

`delta_t = reward_scaled_t + gamma * V(s_{t+1}) - V(s_t)`

where `reward_scaled_t = reward_raw_t * reward_scale`.

### Key Properties
1. Deterministic `StateEncoder` based on normalized state snapshot only.
2. Tabular `V(s)` with bounded range `[-1, 1]` and LRU eviction (`max_states=50_000`).
3. TD reward pipeline:
   - `reward_raw` is preserved (no mandatory clamp inside ValueLayer)
   - optional `reward_scale` controls effective TD reward
   - raw/modulated/clipped TD values are exposed for diagnostics
4. Bounded update dynamics:
   - online phasic TD clipping via `td_clip_online`
   - clip saturation metrics (`td_clip_frequency`, `td_clip_frequency_ema`)
   - optional adaptive clip (`adaptive_td_clip_enabled`)
   - update magnitude clamp (`max_update_l2`) and one update per tick
5. Stability-aware learning rate scaling under low stability index.
6. CER stress modulation:
   - reduces effective learning rate in online updates
   - amplifies negative phasic responses via `stress_dip_gain`
7. Slow tonic dopamine dynamics:
   - `mean_phasic` is maintained as running low-pass of clipped phasic TD
   - `tonic_level` drifts slowly to tonic target with `tonic_slow_rate` (default `0.01`)
   - CER stress controls tonic target base, not instantaneous tonic jumps
8. Dopamine integration in `Agent.step()` uses TD signal:
   - reward-driven dopamine update disabled in agent path
   - additive `dopamine_delta = clamp(delta_t * k, -0.1, 0.1)`
9. TD-guided exploration coupling:
   - signed effect bounded by coupling fraction (`<= 20%`)
   - zero-baseline unfreeze support (`exploration_unfreeze_floor`)
   - agent-level guardrail against rapid exploration collapse in stacked ACC/CER/TD modulation
10. EDPC expectation memory per encoded state:
   - `expected_reward_mean`, `expected_reward_var`
   - `confirmation_count`
   - `confidence_score`, `stability_score`
11. EDPC selective plasticity:
   - effective alpha damping via confidence/stability
   - prediction-shock detection (high-confidence large mismatch)
   - temporary alpha boost and stress increase on shock
12. EDPC runtime diagnostics in `ValueLayer.snapshot()`:
   - confidence/stability distributions
   - shock counters and shock frequency
   - effective alpha trajectory
   - tonic runtime fields: `td_tonic_slow_rate`, `td_phasic_mean`, `td_tonic_target_base`

### Current Modeling Limits
1. Stress currently does not inject stochastic phasic noise; only dip amplification is modeled.
2. Large `reward_scale` or extreme rewards can increase clipping frequency; monitor `td_clip_frequency*` and tune normalization/clip settings when needed.

### Integration
- Computed in `Agent.step()` before affective regulation updates.
- Exposed via `Agent.get_state()["value_layer"]`.
- Persisted in save/load state (`value_layer`).
- Visualized in GUI side panel and inspector.

---

## Spec 011 + HIE-003/HIE-002 + Spec 011a: Decision Arbitration, Deliberative Planning, Credit Assignment

### Overview
The runtime decision path now includes a dedicated arbitration layer between ACC outputs and BG action gating:

`ValueLayer + metadata -> DecisionArbitrator -> (optional) Deliberative planning -> BG/Thalamic selection`

Sleep replay includes reward-anchored credit assignment for causal weighting.

### Decision Arbitration (Spec 011)
1. `DecisionArbitrator` computes:
   - `global_uncertainty_raw` from weighted TD variance, error likelihood, and surprise.
   - `global_uncertainty` via EMA smoothing (`uncertainty_ema_beta`).
2. Mode switch to `DELIBERATIVE` uses hysteresis and release multiplier to avoid mode thrashing.
3. Temperature is uncertainty-driven:
   - `policy_temperature = base_temp + uncertainty_gain * global_uncertainty`
4. Policy reliability combines stability, uncertainty, and replay causality:
   - low reliability can force deliberative mode.

### Deliberative Planning (Spec 011)
1. Planning runs only in deliberative mode and re-weights action pressures before BG.
2. Candidate episodic traces are action-indexed and similarity-filtered by state.
3. Rollout is uncertainty-adaptive in depth and bounded by hard caps.
4. Rollout valuation is max discounted trajectory return:
   - `trajectory_value = Σ (gamma^t * reward_t)`
   - `rollout_value = max(trajectory_value)`
5. Exploration bonus uses value-of-information form:
   - `exploration_bonus = planning_exploration_gain * (1 - confidence)`
6. Safety gates prevent noisy amplification:
   - action is skipped if `support < 0.05`
   - action is skipped if `confidence < planning_min_confidence`
7. Complexity bounds are enforced:
   - `max_actions_per_planning <= 32`
   - `max_rollout_samples_per_action <= 8`
   - `max_rollout_depth <= 6`
8. Planning modifies pressure vector only (no planning-driven policy-temperature relief).
9. HIE-003 imagination overlay contributes multi-action tree trajectories when enabled:
   - root-action value aggregation from imagination tree (`action_values`)
   - blend with memory rollout: `rollout_value = (1 - blend) * memory_rollout + blend * imagined_value`
   - hard caps: `action_branching<=4`, `max_tree_nodes<=128`, `depth<=5`
   - fallback to HIE-002 structured imagination remains available (`samples<=8`, `depth<=5`, `branching<=4`, `nodes<=96`, `edges<=192`)

### Credit Assignment (Spec 011a)
1. Replay assigns causal depth by temporal distance to reward anchor (not replay index order).
2. Anchor selection priority:
   - explicit reward anchor
   - strongest TD-shock anchor
   - midpoint fallback
3. Eligibility traces are bounded by replay credit window.
4. Runtime metrics exposed:
   - `eligibility_trace_mean`
   - `credit_window_usage`
   - `replay_causality_mean`

### Integration
- Decision snapshot: `Agent.get_state()["decision_arbitration"]`
- Credit snapshot: `Agent.get_state()["credit_assignment"]`
- Replay diagnostics: `Agent.get_state()["sleep_replay"]`

---

## Phase 6.1 + Phase 6.2/6.2.1 + SAC: ACh, Filtered Consolidation, Semantic Consolidation

### Overview
Phase 6 adds strict control over sleep consolidation:

1. **Phase 6.1 (ACh):**
   - ACh follows novelty/repetition dynamics with decay-to-baseline.
   - ACh modulates **online** alpha and replay selectivity.
   - ACh does **not** directly modify TD error or reward.
2. **Phase 6.2/6.2.1 (Filtered Consolidation):**
   - Replay is allowed only for episodes that pass strict gating.
   - Consolidation score is capped and replay updates are budget-limited.
   - Variance gate is mandatory and can block replay in unstable regimes.
3. **SAC (Semantic Action Consolidation):**
   - Runs only in sleep and updates only `selector.action_metadata`.
   - Uses replay-gated weighted aggregation by `action_id`.
   - Enforces hard constraints: `α_slow <= 0.01`, minimum replay count, shock mean limit.
   - Protects from semantic crystallization via variance floor (`σ_floor = 0.01` by default).
4. **EDPC <-> SAC Sync (sleep-only):**
   - Harmonizes EDPC `expectation_memory` with SAC `action_metadata`.
   - Applies EMA transfer (confidence/stability), TD-based stability updates, and conflict gating.
   - Enforces plasticity caps and sleep energy budget.

### Filter Criteria (sleep replay candidate)
- `|TD_mean| >= td_threshold`
- `TD_variance <= td_variance_cap`
- `salience >= salience_threshold`
- `reinforcement_count >= min_reinforcement_for_consolidation`
- `value_variance_ratio < variance_gate_threshold`
- `ACh_effective >= ach_min_for_consolidation`
- `stability_flag == True`

### Update Constraints (sleep only)
- `sleep_alpha <= sleep_alpha_cap`
- `|delta_value| <= per_update_cap`
- `L2(delta_value_total) <= max_l2_update_per_cycle`
- `sum(|delta_value|) <= global_sleep_update_budget`
- `consolidation_score <= consolidation_cap`

### Architectural Decision: TD History Variant A
- TD statistics (`td_history_snapshot`, `td_mean_snapshot`, `td_variance_snapshot`) are updated in waking/feedback paths.
- Sleep replay does **not** mutate TD history statistics.
- This prevents self-smoothing of TD confidence due to repeated sleep replay.

### Diagnostics
`SleepManager` reports:
- `total_episodes_examined`
- `total_episodes_consolidated`
- `rejected_due_to_*`
- `mean_consolidation_score`
- `sleep_update_l2_total`
- `variance_ratio`
- `consolidation_ratio`
- `replay_diversity_index` (per-cycle + averaged)
- `shock_frequency` / `total_shock_replays`
- replay-level EDPC aggregates (`replay_confidence_mean`, `replay_stability_mean`)
- SAC diagnostics (`sac_actions_updated`, `sac_rejected_*`, `semantic_drift_rate`, `stability_growth_rate`, `divergence_reduction_index`, `overconfidence_index`)
- EDPC<->SAC sync diagnostics (`edpc_sac_sync_*`)

### Integration
- Filtering and replay control: `src/sleep.py`
- TD statistics snapshots in waking/feedback: `src/agent.py`
- Save/load of Phase 6.2 parameters: `src/storage.py`
- Full compliance tests: `tests/test_phase_6_2_filtered_consolidation.py`
- SAC implementation and metrics: `src/sleep.py`
- SAC compliance tests: `tests/test_semantic_action_consolidation.py`

---


## Phase 3: Basal Ganglia Action Selection

### Overview
Implements biological action selection through competing Go/NoGo channels found in the basal ganglia circuit.

### Key Concept

**Actions compete, not cooperate.**

Each action has:
- **Go weight**: approach tendency
- **NoGo weight**: avoid tendency  
- **Habit strength**: learned preference

### Architecture

```
┌────────────────────────────────────────────────┐
│         ACTION CHANNELS                        │
├────────────────────────────────────────────────┤
│                                                │
│  For each possible action:                    │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │ "attack"                                 │ │
│  │ ├─ go_weight: 0.8                       │ │
│  │ ├─ nogo_weight: 0.2                     │ │
│  │ └─ habit_strength: 0.45 (learned)       │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │ "defend"                                 │ │
│  │ ├─ go_weight: 0.5                       │ │
│  │ ├─ nogo_weight: 0.5                     │ │
│  │ └─ habit_strength: 0.30 (learned)       │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │ "flee"                                   │ │
│  │ ├─ go_weight: 0.2                       │ │
│  │ ├─ nogo_weight: 0.8                     │ │
│  │ └─ habit_strength: 0.15 (learned)       │ │
│  └──────────────────────────────────────────┘ │
│                                                │
└────────────────────────────────────────────────┘
```

### Selection Formula

For each action channel:

```
Go_signal     = go_weight × dopamine × (1 + norepinephrine)
NoGo_signal   = nogo_weight × cortisol
Net_pressure  = Go_signal - 0.5×NoGo_signal + PFC_pressure 
              + habit_strength×0.3

Selected action = argmax(Net_pressure) via softmax
```

### Parameters

| Parameter | Range | Default | Meaning |
|-----------|-------|---------|---------|
| go_weight | 0-1 | varies | Approach tendency |
| nogo_weight | 0-1 | varies | Avoid tendency |
| habit_strength | 0-1 | 0.0 | Learned preference |
| dopamine | 0.1-2.0 | 1.0 | Motivation multiplier |
| cortisol | 0.05-2.0 | 0.5 | Stress multiplier |
| norepinephrine | 0.1-2.0 | 0.8 | Attention/exploration |
| pfc_pressure | 0-1 | 0.5 | Prefrontal advisor |

### Learning: Habit Strength

Waking outcomes do not change habit trace strength (only `note_selection` may create strength-0 traces). During sleep, issue #13 consolidation applies outcome-gated EMA: `habit_delta = 0.20 × clamp(affect_gain_at_encoding, 0.25, 1.5) × (target − strength)` with `target ∈ {0,1}` from reward sign, plus `intent_memory.apply_outcome` for context habits. Stable Go/NoGo use κ capture of labile tags and a compensated step `η_eff = eta_channel_sleep − capture_kappa × eta_labile_channel` (defaults **0.07**). See [Docs/architecture/two-tier-plasticity.en.md](../Docs/architecture/two-tier-plasticity.en.md).

### Integration with Neuromodulators

**Dopamine** (motivation):
- Increases all Go signals
- Strengthens habit learning during sleep

**Cortisol** (stress):
- Increases all NoGo signals
- Shifts behavior toward caution

**Norepinephrine** (attention):
- Increases softmax temperature
- Encourages exploration vs exploitation

**Serotonin** (mood):
- Affects consolidation threshold during sleep
- Modulates learning rate

---

## Phase 2: Neuromodulator System

### Overview
Four neuromodulators that modulate learning, consolidation, and behavior during waking and sleep.

### Neuromodulators

```
┌─────────────────────────────────────────────────┐
│         NEUROMODULATOR STATE                    │
├─────────────────────────────────────────────────┤
│                                                 │
│  DOPAMINE (DA)                                 │
│  ├─ Range: [0.1 - 2.0], Baseline: 1.0        │
│  ├─ Function: Motivation & reward             │
│  ├─ Effects:                                  │
│  │  ├─ Phase 3: Multiplies Go signals        │
│  │  ├─ Sleep: Strengthens consolidation      │
│  │  └─ Learning rate ↑                       │
│  └─ Update: reward > 0 → DA += 0.25*R        │
│                                                 │
│  CORTISOL (CORT)                              │
│  ├─ Range: [0.05 - 2.0], Baseline: 0.5      │
│  ├─ Function: Stress response                │
│  ├─ Effects:                                  │
│  │  ├─ Phase 3: Multiplies NoGo signals     │
│  │  ├─ Sleep: Increases forgetting          │
│  │  └─ Shifts behavior toward caution       │
│  └─ Update: reward < 0 → CORT += 0.25*|R|   │
│                                                 │
│  NOREPINEPHRINE (NE)                          │
│  ├─ Range: [0.1 - 2.0], Baseline: 0.8      │
│  ├─ Function: Attention & exploration       │
│  ├─ Effects:                                  │
│  │  ├─ Phase 3: Temperature for softmax    │
│  │  ├─ High NE: More stochastic choices     │
│  │  └─ Exploration incentive ↑              │
│  └─ Auto-update from novelty & conflict     │
│                                                 │
│  SEROTONIN (S)                                │
│  ├─ Range: [0.1 - 2.0], Baseline: 0.7      │
│  ├─ Function: Mood & stability              │
│  ├─ Effects:                                  │
│  │  ├─ Sleep: Consolidation threshold      │
│  │  ├─ Learning stability ↑                 │
│  │  └─ Habit formation ↑                    │
│  └─ Updates based on positive patterns      │
│                                                 │
│  Decay: Exponential toward baseline           │
│  Half-life: ~90 seconds                       │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Effects on Behavior

| Event | DA | CORT | NE | S |
|-------|-----|------|-----|-----|
| Success | ↑↑ | ↓ | ↑ | ↑ |
| Failure | ↓ | ↑↑ | ↑ | ↓ |
| Novel stimulus | ↑ | stable | ↑↑ | stable |
| Conflict | stable | ↑ | ↑↑ | ↓ |
| After sleep | toward baseline | toward baseline | toward baseline | toward baseline |

---

## Phase 1: Affective System

### Affective State

Four-dimensional emotional state:

```
┌──────────────────────────────────────────┐
│         AFFECTIVE STATE                  │
├──────────────────────────────────────────┤
│                                          │
│  VALENCE [-1.0 to +1.0]                 │
│  ├─ Positive/Negative                  │
│  ├─ Influenced by outcomes              │
│  └─ Affects habit learning              │
│                                          │
│  AROUSAL [0.0 to 2.0]                   │
│  ├─ Calm/Hyperactive                   │
│  ├─ Influenced by intensity             │
│  └─ Related to NE state                 │
│                                          │
│  THREAT [0.0 to 1.0]                    │
│  ├─ Safe/Critical                       │
│  ├─ Influenced by danger signals        │
│  └─ Related to CORT state               │
│                                          │
│  CURIOSITY [0.0 to 1.0]                 │
│  ├─ Indifferent/Exploring               │
│  ├─ Influenced by novelty               │
│  └─ Related to NE state                 │
│                                          │
│  READINESS [0.0 to 1.0]                 │
│  ├─ Processing state                    │
│  ├─ Phase 3: Influences softmax temp   │
│  └─ Indicates readiness for action      │
│                                          │
└──────────────────────────────────────────┘
```

---

## Integration: How It All Works Together

### Scenario: Agent facing a threat

```
WAKING STATE:
1. Threat stimulus detected
   ├─ Cortisol ↑↑ (stress response)
   ├─ Threat affective state ↑
   └─ Norepinephrine ↑ (alertness)

2. Basal Ganglia selection with high cortisol:
   ├─ "attack" - go_weight=0.8, nogo_weight=0.2
   │            Net = 0.8 - 0.5*0.2 = 0.75
   │            (with cortisol ×2.0, NoGo multiplied)
   │            Net = 0.8 - 0.5*0.4 = 0.6
   │
   ├─ "defend" - go_weight=0.5, nogo_weight=0.5
   │            Net = 0.5 - 0.5*0.5 = 0.25
   │            (with cortisol ×2.0)
   │            Net = 0.5 - 0.5*1.0 = 0.0
   │
   └─ "flee" - go_weight=0.2, nogo_weight=0.8
              Net = 0.2 - 0.5*0.8 = -0.2
              (with cortisol ×2.0)
              Net = 0.2 - 0.5*1.6 = -0.6
              → FLEE SELECTED (even with low go_weight!)

3. No learning yet (must happen during sleep)

SLEEPING STATE:
1. Sleep consolidation begins
   ├─ Recent experience reviewed
   ├─ Outcome recorded
   └─ Habit strength updated

2. If threat turned out well (dopamine high):
   ├─ Habit for chosen action ↑
   ├─ Cortisol effects during consolidation
   └─ Pattern stored in semantic memory

3. If threat turned out poorly (dopamine low):
   ├─ Habit for chosen action slightly decays
   ├─ Alternative actions considered
   └─ Negative pattern encoded
```

### Key Principles

| Principle | Description |
|-----------|------------|
| **Selective Learning** | Only learning during sleep, not during waking |
| **Modulation not Dictation** | Neuromodulators change HOW we learn, not WHAT we choose |
| **Competition not Cooperation** | Actions compete via Go/NoGo, winner takes all |
| **Biological Plausibility** | Maps to real brain circuits (BG, DA, cortisol, etc) |
| **Habit-based Behavior** | Experience shapes future behavior through habit strength |
| **PFC Advisory** | Prefrontal cortex can suggest but not force action |

---

## Code Structure

### Core Classes

```python
# Phase 3
class ActionChannel:
    """Individual action with go/nogo weights and habit."""
    action_id: str
    go_weight: float
    nogo_weight: float
    habit_strength: float

class BasalGangliaGate:
    """Action selection via Go/NoGo competition."""
    def choose(channels, pfc_pressure, affective_state, neuromodulators) -> str

# Phase 2
class NeuromodulatorState:
    """Dopamine, cortisol, norepinephrine, serotonin."""
    dopamine: float
    cortisol: float
    norepinephrine: float
    serotonin: float

# Phase 1
class AffectiveState:
    """Valence, arousal, threat, curiosity."""
    valence: float
    arousal: float
    threat: float
    curiosity: float
    readiness: float

# Main
class Agent:
    """Orchestrates all systems."""
    basal_ganglia: BasalGangliaGate
    neuromodulators: NeuromodulatorState
    affective_state: AffectiveState
    affective_space: AffectiveSpace
    # ... more systems
```

---

## Data Flow During Waking

```
Context Event
    ↓
    └─→ activates Action Channels
            ↓
            └─→ queries Neuromodulator State
                    ↓
                    └─→ Basal Ganglia computes Net pressures
                            ↓
                            └─→ Softmax selection
                                    ↓
                                    └─→ ACTION CHOSEN
                                            ↓
                                            └─→ Experience stored (immutable)
                                                    ↓
                                                    └─→ Affective state updates
                                                            ↓
                                                            ├─→ Neuromodulators update
                                                            ├─→ Affective persistence update
                                                            ├─→ Background field update
                                                            └─→ Affective space update
                                                                    ↓
                                                                    └─→ Awaiting action outcome
```

---

## Learning During Sleep

```
Sleep Trigger
    ↓
    └─→ Collect recent experiences
            ↓
            └─→ Cluster by context similarity
                    ↓
                    └─→ abstract successful patterns
                            ↓
                            └─→ Update habit_strength
                                    ↑
                                    Apply neuromodulator modifiers:
                                    - DA: strengthen consolidation
                                    - S: stabilize traces
                                    - CORT: increase forgetting
                                    ↓
                            └─→ Store in semantic memory
                                    ↓
                                    └─→ Sleep complete, ready to wake
```

---

## Testing

All systems tested comprehensively:

```
test_basal_ganglia.py:          29 tests ✅
test_neuromodulators.py:        20+ tests ✅
test_affective_regulators.py:   30+ tests ✅
test_affective_space.py:        5 tests ✅
test_affective_space_integration.py: 4 tests ✅
test_affective_space_storage.py: 1 test ✅
test_value_layer.py:            8 tests ✅
test_value_layer_integration.py: 3 tests ✅
test_value_layer_storage.py:    1 test ✅
test_decision_arbitration_spec_011.py: Decision arbitration coverage ✅
test_deliberative_planning_spec_011.py: Deliberative planning coverage ✅
test_hie_002.py: Structured imagination fallback (HIE-002) coverage ✅
test_hie_003.py: Multi-action imagination tree (HIE-003) coverage ✅
test_credit_assignment_spec_011a.py: Reward-anchored credit assignment coverage ✅
test_phase_6_1_ach.py:         Phase 6.1 coverage ✅
test_phase_6_2_filtered_consolidation.py: Phase 6.2/6.2.1 coverage ✅
test_semantic_action_consolidation.py: SAC coverage ✅
test_autonomous_organism.py:   Autonomous organism Spec v1 ✅
test_agent_lifetime_save_load.py: Wakefulness/autonomous persistence ✅
test_external_interaction_layer.py: External layer + coupling coverage ✅
test_agent.py:                  50+ tests ✅
test_sleep.py:                  20+ tests ✅
... (additional 150+ tests for integration)

TOTAL (core codebase, excluding Demo): 580 passed, 3 skipped ✅
```

Additional Phase 4.x coverage:
- `tests/test_emotional_memory_narratives.py` (6 tests)

---

## Best Practices

1. **Don't break the architecture**
   - Actions chosen by Basal Ganglia only
   - Learning only happens during sleep
   - Neuromodulators modulate, don't dictate

2. **Use proper data flows**
   - Input → Processing → Output
   - Never skip layers
   - Respect immutability principles

3. **Test incrementally**
   - Add feature
   - Write test
   - Run full test suite
   - Ensure `pytest -q` remains green

---

## Documentation Map

See [00_INDEX.md](00_INDEX.en.md) for complete documentation guide.

Key documents:
- [QUICK_START.md](QUICK_START.en.md) - Get started in 5 minutes
- [PHASE_3_GUIDE.md](PHASE_3_GUIDE.en.md) - Basal Ganglia details
- [affective_core_phase4_spec.md](affective_core_phase4_spec.en.md) - Canonical Phase 4 affective core (current runtime)
- [Phase_4_Affective_Space_Spec.md](Phase_4_Affective_Space_Spec.en.md) - Historical Phase 4 (pre) affective space
- [phase_4_1_semantic_emotions_spec.md](phase_4_1_semantic_emotions_spec.en.md) - Phase 4.1 semantic emotions
- [phase_4_2_emotional_memory_narratives.md](phase_4_2_emotional_memory_narratives.en.md) - Phase 4.2 emotional memory & narratives
- [Phase_4_3_Emotional_Expectations_Spec.md](Phase_4_3_Emotional_Expectations_Spec.en.md) - Phase 4.3 emotional expectations
- [Phase_4_4_Regulation_RU_Spec.md](Phase_4_4_Regulation_RU_Spec.en.md) - Phase 4.4 regulation
- [Phase_4_5_Stability_Monitoring_RU_Spec.md](Phase_4_5_Stability_Monitoring_RU_Spec.en.md) - Phase 4.5 stability monitoring
- [Phase_5_0_Value_Layer_RU_Spec.md](Phase_5_0_Value_Layer_RU_Spec.en.md) - Phase 5.0 Value Layer
- [Phase_5_0_1_Value_Layer_RU_Spec.md](Phase_5_0_1_Value_Layer_RU_Spec.en.md) - Phase 5.0.1 engineering clarifications
- [spec_phase5_edpc.md](spec_phase5_edpc.en.md) - Phase 5 EDPC predictive consolidation
- [spec_011_decision_arbitration.md](spec_011_decision_arbitration.en.md) - Decision arbitration
- [spec_deliberative_planning_v2.md](spec_deliberative_planning_v2.en.md) - Deliberative planning v2
- [spec_hie_002.md](spec_hie_002.en.md) - Hippocampal Imagine Engine v2 (structured imagination fallback)
- [spec_hie_003.md](spec_hie_003.en.md) - Hippocampal Imagine Engine v3 (multi-action imagination tree)
- [spec_011a_credit_assignment.md](spec_011a_credit_assignment.en.md) - Reward-anchored credit assignment
- [Phase_6_1_ACh_RU_Spec.md](Phase_6_1_ACh_RU_Spec.en.md) - Phase 6.1 acetylcholine modulation
- [Phase_6_2_Filtered_Consolidation_RU_Spec.md](Phase_6_2_Filtered_Consolidation_RU_Spec.en.md) - Phase 6.2 filtered consolidation
- [Phase_6_2_1_Filtered_Consolidation_FULL_RU_Spec.md](Phase_6_2_1_Filtered_Consolidation_FULL_RU_Spec.en.md) - Phase 6.2.1 full filtered consolidation spec
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.en.md) - Developer reference
- [API.md](API.en.md) - Complete API

---

**Last Updated:** March 22, 2026  
**Status:** ✅ Production Ready - Phase 6 + EDPC + Decision Arbitration + HIE-003/HIE-002 + Credit Assignment + SAC + autonomous + external layer integrated
