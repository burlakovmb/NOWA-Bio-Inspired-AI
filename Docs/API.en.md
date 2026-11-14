# API Reference - NOWA Cognitive (Phase 5 EDPC + Decision Arbitration + Deliberative Planning v2 + HIE-003/HIE-002 + Credit Assignment + Phase 6.2.1 + SAC + Autonomous Runtime + External Interaction Layer + CER + ACC + Packages A/B/C/D/E/F)

Russian version: [API.ru.md](API.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.


This document reflects the current implementation in:
- `src/agent.py`
- `src/autonomous_organism.py`
- `src/simulation_utility.py`
- `src/selector.py`
- `src/external_interaction_layer.py`
- `src/neuromodulators.py`
- `src/genome.py`
- `src/epigenome.py`
- `src/agent_factory.py`
- `src/fitness.py`
- `src/swarm.py`
- `src/reproduction.py`
- `src/mortality.py`
- `src/ecology.py`
- `src/population_observer.py`
- `src/value_layer.py`
- `src/conflict_arbitration.py`
- `src/decision_arbitrator.py`
- `src/hippocampal_imagine_engine.py`
- `src/sleep.py`
- `src/wakefulness.py`
- `src/storage.py`

Last verified: October 20, 2026 (two-tier plasticity, issue #13).

---

## Host contract and plasticity

The core does not choose when to sleep or how fast simulated time runs.

| Obligation | API |
|------------|-----|
| Declare mean waking interval between sleeps | `PlasticityConfig(expected_wake_interval_s=...)` on `Agent(..., plasticity_config=...)` |
| Advance host clock on each tick | `Agent.step(..., dt=seconds)` and/or `commit_executed_transition(..., dt=seconds)`, or `Agent.advance_time(dt)` |
| Consolidate stable memory | `Agent.sleep(cycles=...)` (opens `learning_allowed()`) |
| Register new action channels | `register_action_channel(action_id, ...)` — enters `initializing()` internally |
| Seed stable weights after load | `with initializing(): ...` around direct writes |

`PlasticityConfig` (`src/labile_layer.py`): defaults include `tau_labile_ratio=1.0`, `capture_kappa=0.5`, `eta_channel_sleep=0.08`, `eta_labile_channel=0.02`, `replay_priority_weights=(1.0, 0.5, 0.25, 0.25)`, `labile_epsilon=1e-6`. Resolved `η_L = 0.1 × alpha_reference` when `eta_labile_q` is unset.

**Learning guard** (`src/learning_guard.py`): `NOWA_STRICT_LEARNING=1` (core tests) raises `WakingLearningError` on stable writes while awake; otherwise the write is skipped with a one-time log. `stable_fingerprint(agent)` hashes category-A parameters; `labile_snapshot(agent)` materializes labile offsets at `_host_clock_s`.

Narrative: [Docs/architecture/two-tier-plasticity.en.md](../Docs/architecture/two-tier-plasticity.en.md), [SLEEP.en.md](SLEEP.en.md).

### Контракт с хостом и пластичность

Ядро не решает, когда спать и с какой скоростью идёт время. Таблица выше: `PlasticityConfig`, `dt` / `advance_time`, `sleep()`, `register_action_channel`, `initializing()`. Guard: `NOWA_STRICT_LEARNING`, `WakingLearningError`, `stable_fingerprint`, `labile_snapshot`. Текст: [two-tier-plasticity.ru.md](../Docs/architecture/two-tier-plasticity.ru.md), [SLEEP.ru.md](SLEEP.ru.md).

---

## Agent

File: `src/agent.py`

### `Agent.step(...) -> str`
```python
def step(
    self,
    context_events: list,
    consequence: Event = None,
    intensity: float = 1.0,
    reward: Optional[float] = None,
    novelty: float = 0.0,
    conflict: float = 0.0,
    affective_inputs: dict = None,
    decision_only: bool = False,
    terminal: bool = False,
    physiological_bias: dict = None,
    dt: Optional[float] = None,
) -> str
```

Behavior notes:
1. Updates non-reward neuromodulator dynamics first (`update_from_signals(..., use_reward_for_dopamine=False)`).
2. When `reward` is known, writes **labile** Q and Go/NoGo offsets only (`LabileLayer`); stable `ValueLayer` is unchanged until sleep. `reward=None` defers the labile write to feedback. `NaN` = unknown; `±inf` → `±1`.
3. `dt` advances `_host_clock_s` and labile decay; if omitted, wall-clock fallback with a one-time warning.
4. Does **not** use online `ValueLayer.update` while awake.
5. Stores replay metadata in hippocampus experience:
   - `td_error_snapshot`
   - `replay_salience`
   - `replay_importance`
   - `acetylcholine_snapshot`
   - `encoding_strength`
6. Dopamine is updated from TD delta on effective values (labile path).
7. Uses mandatory decision pipeline:
   - `ActionSelector.compute_pressures(...)`
   - `BasalGangliaGate.process(...)`
   - `ThalamicGate.select(...)`
8. `ActionSelector.compute_pressures(...)` returns cortical/cognitive pressure only.
   Affective and physiological modulation is applied in BG (single point of modulation).
9. If all selector pressures are zero but context is non-empty, agent injects a tiny
   context bootstrap pressure (`0.12`) for one context-derived action candidate.
10. `NO_ACTION` is valid when gated scores sum to zero (no random action fallback).
11. ACC-like arbitration is applied between selector pressure and BG gating:
   - computes control mode and deltas from conflict/error metrics
   - modifies BG threshold/habit/exploration parameters only
   - never selects action directly
12. Combined CER + ACC threshold shift is capped to prevent over-suppression resonance.
13. Decision arbitration is applied after ACC and before BG selection:
   - `DecisionArbitrator.arbitrate(...)` computes uncertainty and policy temperature
   - if mode is `DELIBERATIVE`, planning can re-shape pressure vector
14. Deliberative planning contract:
    - uses similarity-filtered episodic memories for each action
    - computes memory rollout and imagined rollout, then blends by:
      `rollout_value = (1 - imagination_value_blend) * memory_rollout + imagination_value_blend * imagined_value`
    - in HIE-003 mode (`imagination_enable_action_sequences=True`), `imagined_value` comes from root-action tree aggregation
    - in fallback mode (`imagination_enable_action_sequences=False`), `imagined_value` comes from HIE-002 structured imagination (`quantile(imagined_rollouts, 0.7)`)
    - combines reward estimate, model value, rollout value, optional EDPC bias, and VOI bonus
    - rollout depth is uncertainty-adaptive (bounded by implementation caps)
    - exploration bonus is `planning_exploration_gain * (1 - confidence)`
    - action is skipped if `support < 0.05` or `confidence < planning_min_confidence`
    - planning modifies pressure vector only
15. Hippocampal imagination contract:
    - global toggle: `imagination_enabled`
    - HIE-003 tree path: `Agent._generate_action_tree_imagination(...)` -> `HippocampalImagineEngine.generate_action_tree_imagination(...)`
    - HIE-002 structured fallback: `Agent._generate_structured_imagination(...)` -> `HippocampalImagineEngine.generate_structured_imagination(...)`
    - compatibility wrapper is preserved: `Agent._generate_imagined_rollouts(...)`
    - imagined trajectories expose `root_action`, `cumulative_reward`, `terminal_state_value`, `value_estimate`, `novelty_score`, `confidence`, `depth`
    - HIE-003 hard caps:
      - `imagination_action_branching <= 4`
      - `imagination_max_tree_nodes <= 128`
      - `imagination_depth <= 5`
    - HIE-002 hard caps:
      - `imagination_samples <= 8`
      - `imagination_depth <= 5`
      - `imagination_branching <= 4`
      - `imagination_max_graph_nodes <= 96`
      - `imagination_max_graph_edges <= 192`
      - `imagination_max_nodes <= 96`
    - confidence is clamped to `[0.0, 1.0]`
    - early stop when rollout discount falls below `0.02`
    - novelty term is computed from unseen imagined states and blended into trajectory value
14. Decision diagnostics for the last step are stored in
   `Agent._last_decision_arbitration_output` and exposed via `Agent.get_state()`.
15. Keeps rolling evaluation histories for evolutionary fitness diagnostics:
    - `affective_history` (affective-space axis snapshots)
    - `td_error_history` (current TD error trajectory)
    - `cortisol_history` (stress trajectory)
    with default limit `256` via `agent._fitness_history_limit`.

### `Agent.sleep(...) -> dict`
```python
def sleep(self, cycles: int = 3, sleep_duration_seconds: float = None) -> dict
```

Opens `learning_allowed()` and delegates to `SleepManager.deep_sleep()`. Stable-tier writers run here: two-tier capture/habits/visits/slow affect, then per-cycle replay of **stable Q**, cortex, SHY, SAC, etc. Returns aggregated stats (including `two_tier_consolidated` when present). If autonomous runtime is initialized, sleep also recovers autonomous energetic fatigue.

### `Agent.advance_time(dt: float) -> float`

Advances `_host_clock_s` and applies labile decay without a full `step`.

### `Agent.register_action_channel(...)`

Creates a basal-ganglia channel under `initializing()` (host seeding, not waking learning).

### `Agent.get_state() -> dict`
Returns a combined snapshot. Diagnostics include:
- `value_drift_ratio`
- `value_drift_warning`
- `neuromodulators` (includes ACh fields)
- `sleep_replay` (includes ACh/variance replay stats)
- `decision_arbitration` (mode, uncertainty, reliability, planning diagnostics)
- `credit_assignment` (`eligibility_trace_mean`, `credit_window_usage`, `replay_causality_mean`)
- `autonomous_runtime` (when initialized)

### Autonomous runtime methods
```python
def init_autonomous_runtime(...) -> Optional[AutonomousOrganismAgent]
def autonomous_tick(dt: float = 1.0) -> dict
def get_autonomous_state() -> dict
def restore_autonomous_state(state: dict, force_recreate: bool = True) -> bool
```

Behavior notes:
1. `autonomous_tick()` advances autonomous organism and wakefulness in one call.
2. Runtime snapshot is persisted/restored through storage.
3. Tick payload contains physiology diagnostics and energy update details.

### External interaction methods
```python
def set_environment_interface(self, environment_interface) -> None

def observe_external_input(
    self,
    source: str,
    payload: Optional[Mapping[str, Any]] = None,
    uncertainty: float = 0.0,
    timestamp: Optional[float] = None,
) -> Observation

def get_external_observation_history(self, limit: Optional[int] = None)

def create_external_action(... ) -> ExternalAction

def poll_external_observation_non_blocking()
async def poll_external_observation_once()
async def execute_external_action(... ) -> dict

def resolve_external_feedback(current_step: Optional[int] = None) -> dict

def run_parallel_internal_simulations(simulation_requests: list) -> list

def get_external_interaction_state() -> dict
```

Behavior notes:
1. `execute_external_action(...)` supports immediate and delayed feedback (`delay_feedback_steps`).
2. `resolve_external_feedback(...)` applies all due delayed signals and returns learning updates.
3. Agent learning bridge maps selector `predicted_effect.drives` into `strategy_drive_coupling` and passes it into external learning hooks.
4. Updated strategy weights are mirrored into `selector.action_metadata[action]["strategy_weight"]`.

### BG/Thalamic selection contract in Agent
```python
def _select_action_via_basal_ganglia_pipeline(
    self,
    pressure_vector: dict,
    cer_modulation_factors: Optional[Mapping[str, Any]] = None,
) -> str
```

Behavior notes:
1. Builds habit and per-channel modulators from registered `ActionChannel`s.
2. Computes `aversive_signal` from affective core stress (`axes["stress"]`) with legacy fallback to `affect_state.threat`.
3. Reads CER factors:
   - `exploration_bias`
   - `decision_threshold_shift`
   - `habit_gain_scale`
4. Reads ACC-adjusted control factors merged into CER modulation:
   - capped combined `decision_threshold_shift`
   - ACC-informed `habit_gain_scale`
   - ACC-informed `learning_rate_scale` for ValueLayer online alpha
5. Calls BG `process(...)` with merged factors and then `ThalamicGate.select(...)`.
6. Does not replace `NO_ACTION` with random actions.

---

## Continuous Emotional Regulation (CER)

File: `src/emotional_regulation.py`

### `EmotionalRegulationLayer.update(...) -> Dict[str, Any]`
```python
def update(
    self,
    reward_signal: float = 0.0,
    prediction_error: float = 0.0,
    novelty_score: float = 0.0,
    policy_entropy: float = 0.0,
    resolution_success: float = 0.0,
    time_delta: float = 1.0,
    timestamp: Optional[float] = None,
    **legacy_kwargs: Any,
) -> Dict[str, Any]
```

Behavior notes:
1. Maintains continuous state:
   - `valence` in `[-1.0, 1.0]`
   - `arousal` in `[0.0, 1.0]`
   - `uncertainty_tension` in `[0.0, 1.0]`
2. Uses nonlinear bounded dynamics with threshold effects and EMA over prediction error.
3. Enforces hard per-step jump limit `<= 0.3` on each core variable.
4. Supports `recovery_mode` and `saturation_guard` for runaway prevention.
5. Emits `modulation_factors`:
   - `exploration_bias`
   - `learning_rate_scale`
   - `novelty_sensitivity_scale`
   - `decision_threshold_shift`
   - `habit_gain_scale`
6. Emits bounded `neuromodulator_guidance` deltas in range `[-0.006, +0.006]`.

### `EmotionalRegulationLayer.apply_neuromodulator_guidance(...)`
```python
def apply_neuromodulator_guidance(
    self,
    neuromodulators: Any,
    guidance: Optional[Dict[str, float]] = None,
    gain: float = 1.0,
) -> Dict[str, float]
```

Behavior notes:
1. Applies indirect CER guidance to neuromodulator state.
2. Keeps changes bounded and clamped by neuromodulator safety limits.

---

## Conflict Arbitration Layer (ACC-like)

File: `src/conflict_arbitration.py`

### `ConflictArbitrationLayer.arbitrate(...) -> Dict[str, Any]`
```python
def arbitrate(
    self,
    *,
    go_signals: Optional[Iterable[Any]] = None,
    top2_gap: Optional[float] = None,
    policy_entropy: float = 0.0,
    decision_latency: float = 0.0,
    threshold_current: float = 0.0,
    arousal: float = 0.0,
    stress_level: float = 0.0,
    valence: float = 0.0,
    novelty_score: float = 0.0,
    pattern_completion_confidence: float = 0.0,
    prediction_error: float = 0.0,
    recent_failure_rate: Optional[float] = None,
    error_history_window: Optional[Iterable[Any]] = None,
    working_memory_load: float = 0.0,
    task_complexity: float = 0.0,
) -> Dict[str, Any]
```

Behavior notes:
1. Computes:
   - `conflict_score`
   - `error_likelihood`
   - `control_demand` (includes latency term)
2. Selects `control_mode` from:
   - `habitual`, `balanced`, `deliberative`, `inhibit`
3. Hard constraints:
   - hysteresis thresholds
   - refractory period after deliberative
   - control-cost penalty and forced downshift
   - max consecutive inhibit streak
4. Returns control outputs only:
   - `threshold_delta`
   - `control_gain_multiplier`
   - `wm_boost_flag`
   - `exploration_override`
   - `request_additional_evaluation`
5. Conflict metric is intentionally independent from valence/arousal to avoid CER duplication.
6. `inhibit` is implemented via threshold pressure in BG path, not direct motor-pressure zeroing.

### `ConflictArbitrationLayer.register_outcome(reward_signal, prediction_error)`
Updates rolling failure/error windows used by arbitration.

### `ConflictArbitrationLayer.snapshot() -> Dict[str, Any]`
Returns runtime diagnostics and counters:
- mode distribution
- control cost utilization
- refractory/inhibit counters
- last computed metrics and outputs

---

## Decision Arbitration Layer (Spec 011)

File: `src/decision_arbitrator.py`

### `DecisionArbitrator.arbitrate(...) -> Dict[str, Any]`
```python
def arbitrate(
    self,
    *,
    pressure_vector: Optional[Mapping[str, float]] = None,
    action_metadata: Optional[Mapping[str, Mapping[str, Any]]] = None,
    error_likelihood: Optional[float] = None,
    surprise: Optional[float] = None,
    stress_level: Optional[float] = None,
    action_stability_mean: Optional[float] = None,
    causality_mean: Optional[float] = None,
) -> Dict[str, Any]
```

Behavior notes:
1. Computes weighted uncertainty:
   - `global_uncertainty_raw = w_td * td_var + w_error * error + w_surprise * surprise`
   - `global_uncertainty` is EMA-smoothed (`uncertainty_ema_beta`)
2. Applies stress-aware threshold shift:
   - `effective_threshold = clamp(base_threshold - stress_gain * stress, min_threshold, 1.0)`
3. Applies mode hysteresis:
   - previous `DELIBERATIVE` mode is not immediately dropped unless uncertainty goes below downshift boundary
4. Computes policy temperature:
   - `policy_temperature = clamp(base_temp + uncertainty_gain * global_uncertainty, temp_min, temp_max)`
5. Computes policy reliability when stability/causality are provided:
   - `policy_reliability = clamp(stability_mean * (1 - uncertainty) * causality_mean, 0, 1)`
   - low reliability can force `DELIBERATIVE` mode
6. Returns:
   - `decision_mode`
   - `global_uncertainty`, `global_uncertainty_raw`, `uncertainty_ema`
   - `policy_temperature`
   - `policy_reliability`
   - `effective_threshold`
   - `normalized_td_variance`
   - `hysteresis_margin`

### Agent integration (`src/agent.py`)
1. `DecisionArbitrator` output is captured in `_last_decision_arbitration_output`.
2. Planning metadata fields include:
   - `planning_bias_applied`
   - `planning_supported_actions`
   - `planning_support_mean`
   - `planning_rollout_depth`
   - `planning_rollout_samples`
   - `planning_rollout_used`
   - `planning_exploration_bonus_mean`
   - `planning_imagination_enabled`
   - `planning_imagination_samples`
   - `planning_imagination_depth`
   - `planning_imagined_rollouts_used`
   - `planning_imagined_value_mean`
   - `planning_imagined_value_max`
   - `planning_imagined_trajectory_count`
   - `planning_imagined_confidence_mean`
   - `planning_imagined_novelty_mean`
   - `planning_imagination_novelty_hits`
   - `planning_imagination_tree_nodes`
   - `planning_imagination_tree_edges`
   - `planning_imagination_action_count`
   - `planning_imagination_branching`
   - `planning_temperature_factor`
      (kept for compatibility, currently `1.0` from planning path)
3. Combined snapshot is exposed via:
   - `Agent.get_state()["decision_arbitration"]`
   - `Agent.get_state()["credit_assignment"]`

---

## Autonomous Organism Runtime (Spec v1)

Files:
- `src/autonomous_organism.py`
- `src/agent.py`
- `src/gui.py`

### Main classes
1. `AutonomousOrganismAgent`
2. `DriveSystem`
3. `EnergySystem`
4. `InternalSimulationLoop`
5. `SpeechGovernor`
6. `LifeLoopController`

### Drive taxonomy (current)
Autonomous drives:
- `curiosity`
- `social_drive`
- `goal_tension`
- `exploration`
- `energy_need`

Not drives:
- `self_reflection` -> `agent_mode="REFLECTION"`
- `emotional_discharge` -> affect regulation path (`regulate_affect`)

### `AutonomousOrganismAgent.organism_step(dt) -> dict`
Core output fields:
- `timestamp`, `dt`, `dt_input`, `dt_clamped`
- `active_drive`, `active_drive_score`
- `internal_cycle_triggered`, `speech_event`, `speech_reason`, `speech_output`
- `agent_mode`, `mode_signals`
- `regulation`
- `physiology_mode`
- `cognitive_load`, `rest_time`, `load_components`
- `energy_level`, `energy_update`, `energy_snapshot`
- `drives`, `recall_impulse_share`

### `InternalSimulationLoop.run_cycle(...) -> dict`
```python
def run_cycle(
    self,
    active_drive: str,
    now: float,
    dt: float = 1.0,
    live_drives: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]
```

Simulation behavior:
1. Operates on hypothetical copies only.
2. Proposer path: `selector.choose(...)`.
3. Evaluator path: `selector.evaluate(hypothetical_state)` (utility-only).
4. Shared utility computation is centralized in `src/simulation_utility.py`.
5. Hypothetical drive seed is taken from `live_drives` snapshot when available.
6. Action proposal path is aligned with runtime decision pipeline:
   `compute_pressures -> BG.process -> ThalamicGate.select`.

Simulation output contract (core fields):
- `best_action`
- `confidence`
- `evaluated_variants`
- `decision`
- `fallback_used`

### Physiology modes
- `idle`
- `passive`
- `internal_processing`
- `speaking`
- `low_energy`

### Failure log contract
Failure entries have shape:
```python
{
    "timestamp": float,
    "failure_mode": str,
    "details": dict,
}
```

Common modes:
- `drive_runaway_growth`
- `infinite_internal_cycle_loop`
- `speech_spam`
- `dt_anomaly`
- `internal_affect_apply_failed`
- `internal_decision_eval_failed`
- `decision_engine_choose_disallowed`
- `invariant_violation`
- `energy_deadlock`

---

## GUI Autonomous Trace Notes

File: `src/gui.py`

### `NOWAGUI._autonomous_lifecycle_tick()`
Behavior notes:
1. Runs one autonomous tick every lifecycle interval (`1s` by default).
2. Emits speech to chat as `[AUTO] ...` when `speech_event=True`.
3. Emits internal thought trace as `[AUTO] think: ...` when `internal_cycle_triggered=True`.

### `NOWAGUI._format_autonomous_internal_thought(tick) -> str`
Behavior notes:
1. Reads best action/confidence from `tick` and `runtime.internal_loop.last_result`.
2. Shows explicit inhibition text for `NO_ACTION`:
   `NO_ACTION (BG gate inhibited)`.
3. Suppresses duplicate thought lines for ~4 seconds.

---

## External Interaction Layer

File: `src/external_interaction_layer.py`

### Main classes
1. `Observation`
2. `ExternalAction`
3. `Feedback`
4. `Hypothesis`
5. `DelayedFeedback`
6. `ExternalInteractionLayer`
7. `AsyncInteractionScheduler`

### `ExternalInteractionLayer.apply_learning_hooks(...) -> dict`
Core behavior:
1. Drive updates use bounded nonlinear dynamics with `drive_decay`, `drive_saturation`, `drive_competition`.
2. Strategy updates run in logit space with `strategy_weight_decay` and softmax normalization (`strategy_temperature`).
3. Drive-to-policy coupling is supported via `strategy_drive_coupling` + `drive_policy_gain`.
4. Hypothesis recalibration supports explicit `P(E|¬H)` (`likelihood_not_h`) and optional evidence base rate.

Returned diagnostics include:
- `drive_updates`, `strategy_updates`, `strategy_logits`
- `drive_levels`, `strategy_drive_signal`
- tuning values (`drive_decay`, `strategy_temperature`, etc.)

### Selector policy coupling contract
File: `src/selector.py`

`ActionSelector.compute_pressures(...)` additionally reads optional:
- `action_metadata[action]["strategy_weight"]`

This weight is centered relative to uniform baseline and injected into pressure,
so external strategy learning affects actual policy selection.

`action_metadata[action]` also stores SAC semantic fields:
- `expected_effect_mean`
- `expected_effect_variance`
- `success_alpha`
- `success_beta`
- `risk_estimate`
- `semantic_confidence`
- EDPC↔SAC sync fields:
  - `confidence`, `stability`
  - `td_mean`, `td_variance`
  - `consolidated`, `consolidation_flag`
  - `conflict_flag`, `last_state_key`

### GUI interactive contract
File: `src/gui.py`

`Слой внешнего взаимодействия` supports:
- manual observation ingest (`источник`, `неопр.`, `данные JSON`)
- environment polling (`Опрос среды`)
- action execution (`действие`, `приор`, `задержка`, `прогноз`, `параметры JSON`)
- delayed feedback resolution and status refresh.

---

## Neuromodulators

File: `src/neuromodulators.py`

### `NeuromodulatorField`
Coupled interaction layer for `DA/5HT/NE/ACh`.

Core behavior:
1. Keeps per-axis levels and baselines for:
   - `dopamine`
   - `serotonin`
   - `norepinephrine`
   - `acetylcholine`
2. Uses interaction matrix `W` from `spec_neuromodulator_interaction_layer.md`.
3. Applies baseline-centered coupled update:
   - `dM/dt = base_signal + W * (M - baseline) - decay * (M - baseline)`
4. Exposes:
   - `update(signals: Optional[Dict[str, float]] = None, dt: Optional[float] = None) -> Dict[str, float]`
   - `snapshot()`, `reset()`
   - `to_dict()` / `from_dict()`

### `NeuromodulatorState`
Constructor:
```python
NeuromodulatorState(
    dopamine: float = None,
    norepinephrine: float = None,
    serotonin: float = None,
    cortisol: float = None,
    acetylcholine: float = None,
)
```

Core fields:
- scalar neuromodulators: `dopamine`, `serotonin`, `norepinephrine`, `cortisol`, `acetylcholine`
- coupled interaction object: `interaction_field` (`NeuromodulatorField`)
- ACC conflict traces:
  - `acc_combined_conflict_trace`
  - `acc_cognitive_conflict_trace`
  - `acc_affective_conflict_trace`

Core ACh parameters:
- `acetylcholine` in `[0.0, 1.0]`
- `ach_baseline`
- `ach_decay_rate`
- `ach_novelty_gain`
- `ach_repetition_penalty`
- `ach_novelty_filter`
- `ach_novelty_trace`
- `ach_alpha_gain`
- `ach_replay_gain`

### `update_acetylcholine(...)`
```python
def update_acetylcholine(self, novelty: float = 0.0, stable_repetition: bool = False)
```

Rules:
1. Smooth novelty with `ach_novelty_filter` into `ach_novelty_trace`.
2. Increase ACh only when effective novelty is high.
3. Decrease ACh on stable repetition.
4. Decay ACh toward baseline and clamp to `[0.0, 1.0]`.

### `update_from_signals(...)`
```python
def update_from_signals(
    self,
    reward: float = 0.0,
    novelty: float = 0.0,
    conflict: float = 0.0,
    stable_repetition: bool = False,
    use_reward_for_dopamine: bool = True,
    cognitive_conflict: Optional[float] = None,
    affective_conflict: Optional[float] = None,
    dt: float = 1.0,
)
```

ACC-aware behavior:
1. Resolves scalar/split conflict channels with symmetric `None` semantics:
   - if both are `None` -> both use `conflict`
   - if one is `None` -> mirror the provided channel
2. Computes target ACC conflicts (`combined/cognitive/affective`) from a state snapshot (`NE/CORT/5HT`) via `_compute_effective_conflict_from_state(...)`.
3. Applies low-pass temporal smoothing with `alpha = 1 - exp(-dt / tau)` for all three traces.
4. Uses smoothed channels for neuromodulator updates:
   - `NE` gets cognitively-modulated conflict + homeostatic decay toward baseline.
   - `CORT` gets affectively-modulated conflict + homeostatic decay toward baseline.
5. `5HT` reward gain is gated by the smoothed combined conflict trace (`reward > 0 and effective_conflict_combined <= 0.0`).
6. Computes ACh delta from novelty/repetition + decay-to-baseline.
7. Applies fast coupled dynamics (`DA/5HT/NE/ACh`) through `interaction_field.update(..., dt=dt)` on the same step timescale.
8. Clamps all values and updates timestamp.
9. `cortisol` is intentionally updated outside `NeuromodulatorField` (slow stress axis by design).

### Snapshot/Persistence
- `snapshot()` and `to_dict()` include:
  - all ACh-related fields
  - ACC traces (`acc_combined/cognitive/affective_conflict_trace`)
  - `interaction_field`
- `from_dict()` restores ACh/ACC/interaction-layer state.
- Backward compatibility:
  - payloads without `interaction_field` are still supported.
  - legacy `acc_conflict_trace` is accepted as fallback when split traces are absent.

---

## Genome Vector (Package A)

File: `src/genome.py`

### Main objects
1. `GeneDescriptor`
2. `GENE_REGISTRY` (deterministic ordered catalog)
3. `GenomeVector`

### `GenomeVector` creation API
```python
GenomeVector.default() -> GenomeVector
GenomeVector.random(rng: random.Random | None = None) -> GenomeVector
GenomeVector.from_dict(data: dict) -> GenomeVector
GenomeVector.from_array(array: List[float], generation: int = 0) -> GenomeVector
```

Behavior notes:
1. `from_dict(...)` ignores unknown gene keys.
2. Missing genes are filled by descriptor defaults.
3. Out-of-range values are clamped into descriptor bounds.
4. Gene ordering is deterministic (`GENE_REGISTRY` order).

### Evolution API
```python
GenomeVector.mutate(rate=0.05, sigma_scale=1.0, rng=None) -> GenomeVector
GenomeVector.crossover(other, alpha=0.5, mode="arithmetic", rng=None) -> tuple[GenomeVector, GenomeVector]
```

Behavior notes:
1. `mutate(...)` clamps `rate` to `[0.0, 1.0]`.
2. `mutate(...)` clamps `sigma_scale` to `[0.1, 5.0]`.
3. `crossover(...)` modes:
   - `arithmetic`
   - `uniform`
   - `sbx` (`eta=2`)
4. Unknown crossover mode raises `ValueError`.
5. Child generation is `max(parent_a.generation, parent_b.generation) + 1`.
6. Child lineage is composed as `f"{a.lineage_id}x{b.lineage_id}"[:64]`.

### Diagnostics and conversion
```python
GenomeVector.distance(other) -> float
GenomeVector.similarity(other) -> float
GenomeVector.validate() -> List[str]
GenomeVector.summary() -> dict
GenomeVector.to_dict() -> dict
GenomeVector.to_array() -> List[float]
GenomeVector.to_agent_params() -> dict
```

Behavior notes:
1. `distance(...)` is normalized Euclidean distance in `[0.0, 1.0]`.
2. `summary()` reports per-group (`NM/AF/WK/DR/LR/IM`) stats:
   - `mean`
   - `std`
   - `deviation_from_default`
3. `to_agent_params()` expands genome values for:
   - `affective_space`
   - `wakefulness`
   - `neuromodulators`
   - `autonomous`
   - `value_layer`
   - `hippocampus`
   - `sleep`
   - `imagination`
4. `to_agent_params()["autonomous"]` includes `perception_radius_factor` from
   `dr_perception_radius_factor` for swarm perception scaling.

### Coverage
1. `tests/test_genome_vector.py` validates TC-01..TC-14 from `Docs/SPEC_A_GenomeVector.md`.
2. Additional tests cover SBX determinism and lineage truncation.

---

## Epigenome Snapshot (Package B)

File: `src/epigenome.py`

### Main objects
1. `InheritedPattern`
2. `InheritedAction`
3. `InheritedValue`
4. `EpigenomeSnapshot`

### Constants
1. `EPIGENOME_VERSION = "1.0"`
2. `MAX_PATTERNS = 32`
3. `MAX_ACTIONS = 16`
4. `MAX_VALUES = 24`

### `EpigenomeSnapshot` creation API
```python
EpigenomeSnapshot.extract(
    cortex_patterns: List[dict],
    action_metadata: Dict[str, dict],
    value_profiles: Dict[str, dict],
    source_generation: int = 0,
    source_lineage_id: str = "",
    max_patterns: int = 32,
    max_actions: int = 16,
    max_values: int = 24,
    min_reinforcement: int = 2,
    min_stability: float = 0.5,
    min_confirmation: float = 1.0,
) -> EpigenomeSnapshot
EpigenomeSnapshot.from_dict(data: dict) -> EpigenomeSnapshot
EpigenomeSnapshot.empty() -> EpigenomeSnapshot
```

Behavior notes:
1. `extract(...)` accepts only dict/list payloads and skips malformed rows without raising.
2. `extract(...)` clamps `max_*` parameters to `[1, 256]`.
3. Selection policy:
   - patterns: top-N by `reinforcement_count` (descending)
   - actions: top-N by `stability_score` (descending), only `consolidated=True`
   - values: top-N by `confirmation_count` (descending)
4. `source_generation` is normalized to non-negative.
5. `extraction_timestamp` is assigned on extract.

### Transfer API
```python
EpigenomeSnapshot.inject(
    target_cortex_patterns: list,
    target_action_metadata: dict,
    target_value_profiles: dict,
    noise_level: float = 0.1,
    rng: random.Random | None = None,
) -> dict
```

Behavior notes:
1. `inject(...)` mutates targets in place.
2. `noise_level` is clamped to `[0.0, 1.0]`.
3. Existing action/value keys are preserved (no overwrite).
4. Pattern entries are replaced only if inherited `strength` is higher.
5. Returns transfer counters:
   - `patterns_injected`, `patterns_skipped`
   - `actions_injected`, `actions_skipped`
   - `values_injected`, `values_skipped`
   - `noise_level`

### Blend API
```python
EpigenomeSnapshot.blend(
    other: EpigenomeSnapshot,
    alpha: float = 0.5,
    rng: random.Random | None = None,
) -> EpigenomeSnapshot
```

Behavior notes:
1. `alpha` is clamped to `[0.0, 1.0]`.
2. Pattern duplicates use higher `strength`.
3. Action duplicates use higher `stability_score`.
4. Value duplicates are merged:
   - `value = alpha * self + (1 - alpha) * other`
   - `confidence = min(self, other)`
5. Output sizes are capped by `MAX_PATTERNS`, `MAX_ACTIONS`, `MAX_VALUES`.
6. Lineage is composed as `f"{left}+{right}"[:64]`.

### Diagnostics and serialization API
```python
EpigenomeSnapshot.to_dict() -> dict
EpigenomeSnapshot.is_empty() -> bool
EpigenomeSnapshot.size() -> dict
EpigenomeSnapshot.validate() -> List[str]
EpigenomeSnapshot.summary() -> dict
```

Behavior notes:
1. `to_dict()` sorts rows:
   - patterns by strength
   - actions by stability
   - values by confirmation count
2. `from_dict(...)` skips malformed rows with warnings.
3. `validate()` checks ranges, finite values, duplicates, and negative counters.
4. Snapshot internals stay immutable (`frozen=True` + tuple storage).

### Coverage
1. `tests/test_epigenome_snapshot.py` validates TC-01..TC-16 from `Docs/SPEC_B_EpigenomeSnapshot.md`.

---

## Agent Factory (Package C)

File: `src/agent_factory.py`

### Main objects
1. `AgentConfig`
2. `AgentFactory`

### `AgentConfig`
```python
AgentConfig(
    actions: List[str],
    hippocampus_capacity: int = 512,
    cortex_capacity: int = 256,
    sleep_cycles_default: int = 3,
    intent_memory_enabled: bool = True,
    environment_id: str = "",
)
```

### Creation API
```python
AgentFactory.spawn(
    genome: GenomeVector,
    epigenome: EpigenomeSnapshot | None = None,
    epigenome_noise: float = 0.1,
    rng: random.Random | None = None,
    agent_id: str = "",
) -> Agent

AgentFactory.spawn_random(
    rng: random.Random | None = None,
    agent_id: str = "",
) -> Agent

AgentFactory.spawn_default(agent_id: str = "") -> Agent

AgentFactory.spawn_child(
    parent_a: Agent,
    parent_b: Agent,
    mutation_rate: float = 0.05,
    sigma_scale: float = 1.0,
    crossover_alpha: float = 0.5,
    crossover_mode: str = "arithmetic",
    epigenome_noise: float = 0.1,
    blend_epigenomes: bool = True,
    rng: random.Random | None = None,
    agent_id: str = "",
) -> Agent
```

Behavior notes:
1. `spawn(...)` always returns a working `Agent` and attaches:
   - `agent.genome`
   - `agent.epigenome`
   - `agent.agent_id`
   - `agent.lineage_id`
   - `agent.factory_config`
2. `epigenome_noise` is clamped to `[0.0, 1.0]`.
3. Invalid epigenome payloads do not crash spawn.
4. `spawn_child(...)` creates one child (second crossover child is ignored).
5. `spawn_child(...)` clamps mutation and crossover parameters to safe ranges.

### Extraction API
```python
AgentFactory.extract_genome(agent: Agent) -> GenomeVector

AgentFactory.extract_epigenome(
    agent: Agent,
    max_patterns: int = 32,
    max_actions: int = 16,
    max_values: int = 24,
    min_reinforcement: int = 2,
    min_stability: float = 0.5,
    min_confirmation: float = 1.0,
) -> EpigenomeSnapshot
```

Behavior notes:
1. `extract_genome(...)` returns `agent.genome` when available; otherwise reconstructs from live modules.
2. `extract_epigenome(...)` uses public runtime state (`cortex`, `selector.action_metadata`, `value_layer.expectation_memory`) and delegates to `EpigenomeSnapshot.extract(...)`.
3. Reconstruction/injection paths are fail-safe and emit warnings instead of raising.

### Neuromodulator matrix mapping contract

For neuromodulator genes, matrix indices are interpreted as `W[target][source]`:
1. `nm_da_ne_weight` -> `W[NE][DA]`
2. `nm_ne_da_weight` -> `W[DA][NE]`
3. `nm_da_ach_weight` -> `W[ACh][DA]`
4. `nm_ach_da_weight` -> `W[DA][ACh]`

The same mapping is used consistently in both:
1. `_apply_neuromodulator_overrides(...)`
2. `_reconstruct_genome(...)`

### Coverage
1. `tests/test_agent_factory.py` validates TC-01..TC-16 from `Docs/SPEC_C_AgentFactory.md`.
2. Additional coverage includes neuromodulator matrix round-trip consistency.

---

## Fitness Evaluator (Package D)

File: `src/fitness.py`

### Main objects
1. `FitnessVector` (`frozen=True`)
2. `ParetoRank` (`frozen=True`)
3. `FitnessEvaluator`

### Constants
1. `FITNESS_VERSION = "1.0"`
2. `CRITERIA_ORDER`:
   - `longevity`
   - `affective_range`
   - `prediction_skill`
   - `stress_resilience`
   - `behavioral_diversity`
   - `learning_efficiency`
   - `memory_quality`
3. `DEFAULT_WEIGHTS`
4. `AFFECTIVE_RANGE_NORM = 0.5`
5. `LEARNING_EFFICIENCY_NORM = 3.0`
6. `MEMORY_QUALITY_SAMPLE_LIMIT = 128`

### Core API
```python
FitnessEvaluator(weights: Dict[str, float] | None = None)

FitnessEvaluator.evaluate(agent: Any) -> FitnessVector
FitnessEvaluator.evaluate_population(agents: List[Any]) -> List[FitnessVector]
FitnessEvaluator.pareto_rank(fitness_vectors: List[FitnessVector]) -> List[ParetoRank]
FitnessEvaluator.scalar_score(fitness: FitnessVector) -> float
FitnessEvaluator.dominates(a: FitnessVector, b: FitnessVector) -> bool
FitnessEvaluator.criteria_names() -> List[str]
FitnessEvaluator.fitness_to_dict(fitness: FitnessVector) -> dict
FitnessEvaluator.fitness_from_dict(data: dict) -> FitnessVector
```

Behavior notes:
1. Evaluation is read-only and exception-safe: malformed agent data degrades to `0.0` criteria values.
2. All criteria values are clamped to `[0.0, 1.0]`.
3. Missing histories fallback behavior:
   - prediction: uses `value_layer.snapshot()["last_td_error"]` when `td_error_history` is absent/empty
   - stress: uses `neuromodulators.cortisol` when `cortisol_history` is absent/empty
4. `pareto_rank(...)` is deterministic and returns sorted results by `(rank ASC, crowding_distance DESC)`.
5. Boundary vectors in each front receive `crowding_distance = float("inf")`.
6. `scalar_score(...)` uses normalized weights and returns value in `[0.0, 1.0]`.

### Agent-side runtime support
`Agent.step(...)` maintains rolling histories required by Package D:
1. `agent.affective_history: List[dict]`
2. `agent.td_error_history: List[float]`
3. `agent.cortisol_history: List[float]`
4. rolling cap via `agent._fitness_history_limit` (default `256`)

### Coverage
1. `tests/test_fitness.py` validates TC-01..TC-18 from `Docs/SPEC_D_FitnessEvaluator.md`.
2. `tests/test_fitness_agent_integration.py` validates runtime history accumulation contract in `Agent.step(...)`.

---

## Swarm Environment (Package E)

File: `src/swarm.py`

### Main objects
1. `Position3D`
2. `SpaceBounds`
3. `SocialSignal`
4. `AgentSlot`
5. `SwarmState`
6. `SwarmConfig`
7. `SwarmEnvironment`

### Constants
1. `SWARM_VERSION = "2.2"`
2. `MAX_POPULATION_SIZE = 256`
3. `MIN_AGENT_DISTANCE = 0.1`
4. `SIGNAL_MIN_STRENGTH = 0.01`
5. `MAX_SOCIAL_SIGNAL_GAIN = 0.5`
6. `SLEEP_HYSTERESIS_FACTOR = 0.7`
7. `SLEEPING_SIGNAL_FACTOR = 0.3`
8. `WAKE_SIGNAL_THRESHOLD = 0.6`

### Core API
```python
SwarmEnvironment(
    config: SwarmConfig,
    fitness_evaluator: FitnessEvaluator,
    rng: random.Random | None = None,
    factory: Any | None = None,
)

SwarmEnvironment.add_agent(agent: Any, position: Position3D | None = None) -> Position3D
SwarmEnvironment.remove_agent(agent_id: str) -> Any | None
SwarmEnvironment.move_agent(agent_id: str, new_position: Position3D) -> bool
SwarmEnvironment.get_agent(agent_id: str) -> Any | None
SwarmEnvironment.get_position(agent_id: str) -> Position3D | None
SwarmEnvironment.get_all_agents() -> List[Any]
SwarmEnvironment.replace_population(agents: List[Any]) -> None

SwarmEnvironment.get_agents_in_radius(
    agent_id: str,
    radius: float | None = None,
    include_sleeping: bool = True,
) -> List[Tuple[Any, float]]
SwarmEnvironment.collect_signals_for_agent(agent_id: str) -> List[SocialSignal]
SwarmEnvironment.apply_social_signal(agent: Any, signal: SocialSignal, gain: float) -> None

SwarmEnvironment.tick(dt: float = 1.0, context_override: Dict[str, List[str]] | None = None) -> SwarmState
SwarmEnvironment.run_generation(steps: int | None = None, dt: float = 1.0) -> List[SwarmState]

SwarmEnvironment.get_diversity() -> float
SwarmEnvironment.get_swarm_state() -> SwarmState
SwarmEnvironment.evaluate_all() -> List[FitnessVector]
SwarmEnvironment.get_sleeping_agents() -> List[str]
SwarmEnvironment.get_active_agents() -> List[str]
SwarmEnvironment.get_nearest_agents(position: Position3D, k: int = 5, include_sleeping: bool = True) -> List[Tuple[Any, float]]
SwarmEnvironment.get_spatial_density(position: Position3D, radius: float) -> float
```

### Behavior notes
1. Space is continuous 3D; 2D mode is represented by `SpaceBounds(z_min == z_max)`.
2. Placement enforces exclusion with minimum pairwise distance `MIN_AGENT_DISTANCE`.
3. `add_agent(...)` perception radius is genome-scaled:
   - `base_perception_radius * genome.genes["dr_perception_radius_factor"]`
4. Sleeping agents remain visible to neighbors and still receive signals.
5. Signals from sleeping sources are attenuated by `SLEEPING_SIGNAL_FACTOR`.
6. Wake-by-signal uses cumulative stress term:
   - `sum(signal.stress * signal.signal_strength) >= wake_signal_threshold`
7. `replace_population(...)` does not reset `global_step`.
8. Tick loop is deterministic by sorted `agent_id`; one failing agent does not stop others.
9. `context_events_fn` is optional; when absent, environment provides default context events:
   - activity state (`agent_active` / `agent_sleeping`)
   - wakefulness bucket (`wakefulness_high` / `wakefulness_mid` / `wakefulness_low`)
   - social markers (`social_signal_present`, `social_sleeping_neighbor`, `social_stress_high`)
10. Emergent lifecycle extension:
   - environment includes `ecology` resource layer
   - tick includes vitality updates, mortality checks, and decentralized reproduction pairing
   - `SwarmState` includes resource and birth/death metrics

### Coverage
1. `tests/test_swarm_environment.py` validates TC-01..TC-18 from
   `Docs/SPEC_E_SwarmEnvironment_v2.1.md`.
2. Additional tests validate default-context fallback events when no custom
   `context_events_fn` is provided.
3. `tests/test_emergent_evolution_v2.py` validates integration scenarios for resource/mortality/reproduction paths.

---

## Emergent Evolution (Package F)

Files:
1. `src/reproduction.py`
2. `src/mortality.py`
3. `src/ecology.py`
4. `src/population_observer.py`

Main APIs:
```python
ReproductiveSystem.update(
    energy: float,
    valence: float,
    cortisol: float,
    lived_steps: int,
    resource_share: float,
) -> None
ReproductiveSystem.is_ready() -> bool
ReproductiveSystem.register_reproduction(current_step: int) -> None
compute_compatibility(agent_a_snapshot: dict, agent_b_snapshot: dict) -> float

MortalitySystem.update(
    energy: float,
    wakefulness: float,
    lived_steps: int,
    cortisol_mean: float,
) -> bool
MortalitySystem.is_dead() -> bool
MortalitySystem.get_age_fraction(lived_steps: int) -> float

EcologyLayer.compute_resource_share(agent_count: int) -> float
EcologyLayer.consume(agent_count: int) -> float

PopulationObserver.observe() -> PopulationSnapshot
PopulationObserver.save(path: str) -> None
PopulationObserver.load(path: str, environment: SwarmEnvironment) -> PopulationObserver
```

---

## Value Layer

File: `src/value_layer.py`

### `ValueLayer.update(...) -> dict`
```python
def update(
    self,
    state_snapshot: Mapping[str, Any],
    reward: float,
    next_state_snapshot: Mapping[str, Any],
    gamma: float = 0.95,
    alpha: Optional[float] = None,
    timestamp: Optional[float] = None,
    stability_index: Optional[float] = None,
    mode: str = "online",
    acetylcholine: Optional[float] = None,
    acetylcholine_baseline: Optional[float] = None,
    acc_learning_boost: Optional[float] = None,
    cer_stress_level: Optional[float] = None,
    exploration_baseline: Optional[float] = None,
    reward_scale: Optional[float] = None,
) -> Dict[str, Any]
```

TD/reward behavior:
1. `reward_raw` is taken from environment as-is (no internal clamp to `[-1, 1]`).
2. Effective reward is `reward_scaled = reward_raw * reward_scale_v`.
3. Raw TD is preserved in diagnostics: `delta = reward_scaled + gamma * V(s_next) - V(s)`.
4. Online phasic TD is clipped by `td_clip_online`; sleep mode uses fixed clip `1.0`.
5. Returned diagnostics include `delta`, `delta_modulated`, `delta_clipped`, `td_was_clipped`, `td_clip_value`, `td_clip_frequency`, `td_clip_frequency_ema`.
6. Optional adaptive clipping (`adaptive_td_clip_enabled`) adjusts `td_clip_online` toward `td_clip_target_rate`.
7. Tonic dopamine is updated by a slow filter (`tonic_slow_rate`, default `0.01`) from running `mean_phasic`, rather than instant jumps.

Stress and exploration behavior:
1. CER stress reduces effective alpha (`stress_scale = max(0.2, 1 - 0.5 * stress)`).
2. CER stress amplifies negative phasic TD via `stress_dip_gain` (dip-only modulation).
3. TD sign controls exploration coupling with bounded amplitude (`<= 20%` of baseline).
4. When baseline exploration is near zero, `exploration_unfreeze_floor` is used to keep coupling active.
5. In `Agent.step()`, additional guardrails cap per-step TD exploration shift and enforce inhibit-mode floor (`0.05..0.20`).

Phasic/tonic diagnostics:
1. `update(...)` returns `phasic_burst`, `phasic_delta`, `mean_phasic`, `tonic_level`.
2. `snapshot()` exposes `td_tonic_slow_rate`, `td_phasic_mean`, `td_tonic_target_base`.
3. `to_dict()` / `from_dict()` persist and restore the same tonic-dynamics fields.

ACh behavior:
1. Applies only in `mode="online"`.
2. Uses baseline-relative signal: `ach_effective = max(0.0, ach - ach_baseline)`.
3. Online alpha scaling: `alpha = alpha * (1 + ach_alpha_gain * ach_effective)`.
4. Soft cap enforced by `alpha_online_soft_cap`.
5. In `mode="sleep"`, ACh does not scale alpha.

EDPC behavior (Phase 5):
1. Per-encoded-state expectation memory is tracked in `ValueLayer.expectation_memory`:
   - `expected_reward_mean`
   - `expected_reward_var`
   - `confirmation_count`
   - `confidence_score`
   - `stability_score`
   - `error_likelihood`
   - `prediction_shock` (score) and `prediction_shock_flag`
   - `predicted_value`
   - `last_updated_step`
2. `update(...)` computes EDPC diagnostics and returns:
   - `expected_reward_mean`, `expected_reward_var`
   - `confirmation_count`, `confidence_score`, `stability_score`
   - `surprise`
   - `prediction_shock` (bool) and `prediction_shock_score` (float)
   - `replay_priority`
   - `consolidation_weight`
   - `shock_replay_boost`
3. Online effective alpha includes selective damping and shock boost:
   - damping: `1 - confidence * stability * stability_damping`
   - shock: temporary multiplier `(1 + shock_plasticity_boost)` when shock is detected
4. `snapshot()` includes EDPC metrics:
   - `confidence_distribution`, `stability_distribution`
   - `shock_count_total`, `shock_frequency`, `shock_frequency_ema`
   - `effective_alpha_trajectory`
5. Similarity-assisted expectation retrieval for unseen states:
   - vectorized deterministic encoding (`state_vector` / `state_features`)
   - text fields use deterministic semantic hashing (no random text vectors):
     - tokenization is case-insensitive and split-based (`eat_food` -> `["eat", "food"]`)
     - each token maps to a stable unit vector via SHA-256-based hashing
     - phrase vector is normalized mean of token vectors
   - bucketed cosine candidate scan (`similarity_bucket_bits`, `similarity_bucket_radius`)
   - bounded candidate pool (`similarity_index_max_candidates`, `similarity_max_scan`)
   - weighted transfer of confidence/stability via quantile anchor (`similarity_transfer_quantile`)
6. Similarity runtime diagnostics are exposed in `snapshot()`:
   - `last_similar_state_count`
   - `last_similarity_scan_count`
   - similarity configuration fields
7. Persistence keeps full similarity index inputs (`state_vector` / `state_features`) in expectation profiles.

---

## Sleep Manager

File: `src/sleep.py`

### `SleepManager.sleep_cycle() -> dict`
Returns per-cycle replay and consolidation stats including:
- `replay_selected`, `replays`, `replay_blocked`
- `replay_diversity_index`
- `shock_replays`, `shock_frequency`
- `replay_confidence_mean`, `replay_stability_mean`
- `value_variance`, `value_variance_ratio`
- `total_value_delta_sleep`, `total_bg_delta_sleep`
- `sleep_update_count`
- `mean_ach_during_cycle`
- `mean_ach_above_baseline`
- SAC metrics:
  - `sac_episodes_gated`, `sac_actions_considered`, `sac_actions_updated`, `sac_actions_skipped`
  - `sac_rejected_*`
  - `sac_phase`, `phase_distribution`
  - `mean_sigma_change`, `mean_stability_change`, `structural_alert_count`
  - `semantic_drift_rate`, `stability_growth_rate`, `divergence_reduction_index`, `overconfidence_index`
- EDPC↔SAC sync metrics:
  - `edpc_sac_sync_enabled`, `edpc_sac_sync_phase`
  - `edpc_sac_sync_updates`, `edpc_sac_sync_conflicts`
  - `edpc_sac_sync_energy_used`, `edpc_sac_sync_skipped`
- credit-assignment diagnostics:
  - `eligibility_trace_mean`
  - `credit_window_usage`
  - `replay_causality_mean`
  - `anchor_source`
  - `reward_anchor_index`

### `SleepManager.deep_sleep(cycles=3) -> dict`
Aggregates cycle stats and averages:
- `mean_ach_during_cycle`
- `mean_ach_above_baseline`
- `value_variance_ratio`
- `mean_replay_diversity_index`
- `mean_replay_confidence`
- `mean_replay_stability`
- `eligibility_trace_mean`, `credit_window_usage`, `replay_causality_mean`
- `total_shock_replays`, `shock_frequency`
- aggregated SAC metrics, phase distribution, and drift indices

### SAC hard constraints (sleep manager)
- Runs only during sleep replay pipeline.
- `sac_alpha_slow <= 0.01` (violation raises `ValueError`).
- `sac_alpha_base <= 0.01` (violation raises `ValueError`).
- `sac_lambda_sws > sac_lambda_rem` (violation raises `ValueError`).
- Mean shock block threshold (`sac_shock_block_threshold`) and minimum replay count (`sac_replay_min_count`).
- Variance floor against crystallization: `sac_sigma_floor` (default `0.01`).
- One-phase-per-action enforcement: exactly one of `SWS/REM/TRANSITIONAL` is applied per action update.

### Reward-anchored credit assignment (Spec 011a)
1. Replay sequence uses reward-aware anchor selection:
   - explicit reward anchor (if available)
   - fallback to strongest TD-shock index
   - midpoint fallback when neither reward nor TD-shock anchor is available
2. Causal depth is temporal-distance based from anchor (not raw replay index order).
3. Eligibility traces are bounded by replay credit window and consolidated into per-cycle diagnostics.

### SAC phase/runtime behavior
- Phase classifier supports global mode and optional local mode (`local_phase_mode=True`).
- Global phase can be derived from rows that are effectively update-eligible (after gating and update preconditions).
- Episode-level SAC gating is enforced before aggregation:
  - confidence, stability, shock, consolidation probability thresholds
- Replay weighting is hybrid:
  - `weight = replay_priority * confidence * stability * (1 - shock)`
- REM stability is lower-bounded by `sac_stability_floor_rem`.
- Structural alert lifecycle:
  - `meta["structural_alert"]` is set in REM structural-shock cycles
  - alert is auto-reset after `sac_structural_alert_reset_cycles` calm cycles
- Semantic confidence update has bounded per-cycle step:
  - `sac_semantic_confidence_step_cap`

---

## Storage

Files: `src/storage.py`, `src/state_codec.py`

### On-disk format (issues #16 / #31)

Agent saves are UTF-8 JSON documents, not pickle.

| Field | Value |
|---|---|
| `format` | `nowa-agent-state` |
| `schema_version` | `1` (only version this build loads) |
| Extension | `.nowa` (default `agent_save_*.nowa`) |

`dump_state` / `load_state` in `state_codec.py` enforce the format, reject pickle bytes, and write atomically. Helpers: `read_agent_state(path)`, `write_agent_state(path, state)`. Spec: [specs/issue-16-31-safe-agent-state.en.md](specs/issue-16-31-safe-agent-state.en.md).

Legacy `.pkl` agent files raise `StateFormatError` on load. There is no migration.

### `AgentStorage.save_agent(...)` / `load_agent(...)`

The `state` mapping includes hippocampus episodes and, when supported, `hippocampus_decision` from `NOWAHippocampus.export_persistent_state` (signatures, novelty caches, event window — signatures are not rebuilt on load).

Persistence also includes:

1. Full neuromodulator payload (`to_dict()`), including ACh state and parameters.
2. Value layer and filtered-consolidation configuration/state.
   - ValueLayer EDPC parameters and expectation runtime state
   - SleepManager EDPC replay parameters (`edpc_priority_enabled`, `edpc_consolidation_blend`, `shock_priority_gain`)
   - SleepManager SAC parameters/state (`sac_*`, `last_sac_stats`)
   - Selector semantic metadata (`selector_action_metadata`)
3. `conflict_arbitration` and `intent_memory` when passed (core GUI passes both on `agent`).
4. Two-tier host fields when `agent=` is set: `labile_layer`, `plasticity_config`, `host_clock_s`, `bg_outcome_slots`, `bg_action_channels`, BG sleep memories, agent lifetime/runtime/wakefulness/autonomous snapshots.
5. Wakefulness runtime fields, including circadian parameters:
   - `wakefulness`, `last_update_ts`, `accumulated_waking_time`, `total_sleep_time`
   - `circadian_time_hours`, `circadian_period_hours`, `circadian_amplitude`, `circadian_phase`
6. Autonomous runtime snapshot (`drives`, `energy`, `speech`, `tick_count`, `failures`).

After load, `_bind_restored_two_tier(agent, sleep_manager)` reconnects managers to restored `labile` and `plasticity`.

**Not persisted:** hippocampus constructor hyperparameters (capacity, decay constants chosen at construct time). The live hippocampus object keeps its parameters.

### Sandbox and employee checkpoints

| Artifact | Format | Module |
|---|---|---|
| `*.ckpt` | `nowa-sandbox-checkpoint` schema `2` | `Demo/Virtual company/src/nowa_sandbox/sandbox_checkpoint.py` |
| `*.ckpt.agent.nowa` | `nowa-agent-state` schema `1` | same (optional `sandbox_intent_memory` key) |
| `mind.nowa` | `nowa-agent-state` schema `1` | `Demo/Virtual company/src/nowa_body/employee_checkpoint.py` (optional `vc_intent_memory`) |

Sandbox metadata stores `GenomeVector.to_dict()`; epigenome is not part of the checkpoint file.

---

## Core Invariants

1. ACh does not directly modify TD error formula.
2. ACh does not scale sleep alpha.
3. Autonomous and wakefulness values are clamped to safe numeric ranges.
4. Autonomous speech cooldown is enforced.
5. Utility formula for internal simulation is shared between selector/runtime.
6. Save/load round-trip keeps autonomous and wakefulness state consistent.
7. No double affect/threat modulation between selector pressure and BG gate.
8. Wakefulness-based fatigue uses `WakefulnessState.get_cognitive_reliability()` semantics:
   `clamp(base_alertness - sleep_pressure + circadian_signal, 0..1)`.
   Legacy fallback `(1 - wakefulness)` is compatibility-only.
9. `NO_ACTION` from thalamic gate is preserved (no random override).
10. Strategy weights used by selector are normalized probabilities (softmax).
11. Drive-to-policy coupling is applied through selector pressure modulation, not by bypassing BG gate.
12. Delayed feedback is applied only at/after due step.
13. ValueLayer keeps raw reward signal and exposes clipping diagnostics for saturation monitoring.
14. EDPC confidence and stability stay in `[0.0, 1.0]`.
15. Prediction shock is raised only when both confidence and delta thresholds are exceeded.
16. SAC phase update is sleep-only and action-level phase rule is mutually exclusive (`SWS xor REM xor TRANSITIONAL`).
17. SAC global phase is computed from effectively update-eligible data (not merely from raw replay potential).
18. `prediction_shock_score` and `prediction_shock_flag` are distinct; never use `bool(score)`.
19. EDPC↔SAC energy budget uses normalized cost (`clamp(replay_priority, 0..1)`).
20. `conflict_flag` is cleared at sleep start; `expectation_memory` is maintained as `OrderedDict`.
21. Decision arbitration uncertainty is EMA-smoothed and mode transition uses hysteresis.
22. Deliberative planning modifies pressure only in `DELIBERATIVE` mode, before BG/Thalamic selection.
23. Rollout planning uses similarity-filtered episodic candidates and bounded compute controls.
24. HIE-003 tree imagination has hard caps (`action_branching<=4`, `max_tree_nodes<=128`, `depth<=5`) and does not mutate episodic memory.
25. HIE-002 structured imagination fallback keeps independent hard caps (`samples/depth/branching/max_graph_nodes/max_graph_edges`).
26. Planning imagination uses blend composition (`memory` + `imagined`) instead of hard `max(...)`.
27. Structured imagination confidence is bounded in `[0.0, 1.0]`.
28. Credit assignment depth is reward-anchored (causal distance), not naive replay-position order.
29. Genome vectors keep deterministic key order and bounded per-gene ranges across all mutation/crossover/serialization paths.

