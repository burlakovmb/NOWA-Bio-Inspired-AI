# NOWA — Changes and new functionality

Russian version: [CHANGELOG.ru.md](CHANGELOG.ru.md)

## 2026-11-28 — Virtual company: domain-neutral sandbox scenario (issue #96)

Developer-facing documentation for the `Scenario` / `ScenarioTrainer` layer and backward-compatible `SandboxTrainer` facade. Procurement CLI, GUI, and default YAML behaviour unchanged.

Updated files:

- `Docs/specs/issue-96-sandbox-scenario.en.md` (new)
- `Docs/specs/issue-96-sandbox-scenario.ru.md` (new)
- `Demo/Virtual company/README.en.md`, `README.ru.md`
- `Demo/Virtual company/Docs/SCIENTIFIC_DESCRIPTION.en.md`, `SCIENTIFIC_DESCRIPTION.ru.md`
- `Demo/Virtual company/Docs/NOWA_Procurement_Sandbox_Spec.en.md` (as-built note)

Key points documented:

- `Scenario` contract and day order in `ScenarioTrainer._run_single_quarter`
- `NumericMemory`, `stage_mechanics` graduation helpers, optional YAML `scenario:`
- Toy logistics reference under `tests/logistics_scenario.py`
- Golden gate: `tools/golden_issue_96.py`, fixture regeneration, core-agent requirement

QA evidence remains in `Docs/qa/issue-96-scenario.*.md` (not rewritten).

---

## 2026-09-27 — Scientific exposition in two languages


The entry documents and the scientific accounts of the platforms were updated. `README.md` places the English text first and the Russian text after it. The other scientific texts are split into `*.en.md` and `*.ru.md` files, so a link stays in the chosen language.

- `README.md`
- `Docs/SCIENTIFIC_DESCRIPTION.md`
- `Docs/INDEX.md`
- `Docs/START_HERE_NEW.md`
- `Demo/Colony chinchillas/Docs/COLONY_SPEC.md`
- `Demo/Colony chinchillas/Docs/IMPLEMENTATION_DESCRIPTION.md`
- `Demo/Tamagochi Chinchilla/README.md`
- `Demo/Tamagochi Chinchilla/Docs/SCIENTIFIC_DESCRIPTION.md`
- `Demo/Tamagochi Chinchilla/Docs/PROJECT_COMPLETE_SUMMARY.md`
- `Demo/Virtual company/README.md`
- `Demo/Virtual company/Docs/SCIENTIFIC_DESCRIPTION.md`
- `Demo/Warriner Validation/Docs/SCIENTIFIC_DESCRIPTION.md`


Normative specifications of the platforms receive a bilingual scientific preface and retain the contract text. Core documents in `Docs/` (other than the preprint and the new scientific exposition) open with a bilingual status; beneath it the original drafting of the contract or of the laboratory record is retained. The phase inventory `Docs/ARCHITECTURE_UPDATED.md` and the indexes `Docs/00_INDEX.md`, `Docs/00_INDEX_NEW.md` are marked as historical.

---

## 2026-03-26 - SwarmEnvironment (Package E) implementation and documentation sync

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/GENOME_VECTOR.md`
- `Docs/SWARM_ENVIRONMENT.md` (new)
- `Docs/CHANGELOG.md`

Key updates:
- Added Package E coverage in documentation for `src/swarm.py`:
 - spatial model (`Position3D`, `SpaceBounds`)
 - social signaling (`SocialSignal`, attenuation, sleeping-source factor)
 - autonomous sleep/wake tick behavior and swarm metrics
- Documented default context fallback behavior when `context_events_fn` is not provided:
 - `agent_active/agent_sleeping`
 - `wakefulness_high/mid/low`
 - social marker events from incoming signals
- Synced GenomeVector documentation with new gene:
 - `dr_perception_radius_factor`
 - `to_agent_params()["autonomous"]["perception_radius_factor"]`
- Added dedicated implementation guide:
 - `Docs/SWARM_ENVIRONMENT.md`
- Refreshed testing commands and verification snapshot to include Package E focused tests.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `701 passed, 3 skipped` (`pytest -q tests`).
- SwarmEnvironment focused run: `37 passed` (`pytest -q tests/test_swarm_environment.py`).
- GenomeVector focused run: `17 passed` (`pytest -q tests/test_genome_vector.py`).

---

## 2026-03-25 - FitnessEvaluator (Package D) documentation sync

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`
- `Docs/FITNESS_EVALUATOR.md` (new)

Key updates:
- Added Package D references to root and docs indexes.
- Added API coverage for `src/fitness.py`:
 - `FitnessVector`, `ParetoRank`, `FitnessEvaluator`
 - criteria/weights/constants contract
 - Pareto ranking and scalar fallback behavior
- Added explicit runtime contract for rolling fitness histories in `Agent.step(...)`:
 - `affective_history`
 - `td_error_history`
 - `cortisol_history`
- Added dedicated Package D implementation guide `Docs/FITNESS_EVALUATOR.md`.
- Synced testing commands and verification snapshot with current run.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `681 passed, 3 skipped` (`pytest -q tests`).
- FitnessEvaluator focused run: `21 passed` (`pytest -q tests/test_fitness.py tests/test_fitness_agent_integration.py`).

---

## 2026-03-25 - AgentFactory (Package C) implementation and documentation sync

Updated files:
- `src/agent_factory.py`
- `tests/test_agent_factory.py`
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/AGENT_FACTORY.md`
- `Docs/CHANGELOG.md`

Key updates:
- Added Package C implementation in `src/agent_factory.py`:
 - `AgentConfig` and `AgentFactory` public API
 - spawn paths: `spawn`, `spawn_random`, `spawn_default`, `spawn_child`
 - extraction paths: `extract_genome`, `extract_epigenome`
 - robust genome application/injection/reconstruction helpers with warning-based fail-safe behavior
- Added Package C validation suite `tests/test_agent_factory.py`:
 - TC-01..TC-16 from `Docs/SPEC_C_AgentFactory.md`
 - additional round-trip consistency test for neuromodulator interaction matrix mapping
- Added dedicated guide `Docs/AGENT_FACTORY.md`.
- Synced project documentation references, API surface, and testing commands for Package C.
- Refreshed verification snapshot in docs to current baseline run.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `660 passed, 3 skipped` (`pytest -q tests`).
- AgentFactory focused run: `17 passed` (`pytest -q tests/test_agent_factory.py`).
- GenomeVector focused run: `17 passed` (`pytest -q tests/test_genome_vector.py`).
- EpigenomeSnapshot focused run: `16 passed` (`pytest -q tests/test_epigenome_snapshot.py`).

---

## 2026-03-24 - EpigenomeSnapshot implementation and documentation sync

Updated files:
- `src/epigenome.py`
- `tests/test_epigenome_snapshot.py`
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/EPIGENOME_SNAPSHOT.md`
- `Docs/GENOME_VECTOR.md`
- `Docs/CHANGELOG.md`

Key updates:
- Added Package B implementation in `src/epigenome.py`:
 - immutable data structures: `InheritedPattern`, `InheritedAction`, `InheritedValue`, `EpigenomeSnapshot`
 - extraction API from raw dictionaries with top-N selection and threshold filtering
 - in-place injection API with bounded noise and conflict-safe merge policy
 - blend API for two-parent inheritance merge with bounded output and lineage truncation
 - serialization (`to_dict/from_dict`) and diagnostics (`validate/summary/size/is_empty`)
- Added Package B validation suite `tests/test_epigenome_snapshot.py`:
 - TC-01..TC-16 from `Docs/SPEC_B_EpigenomeSnapshot.md`
- Added dedicated guide `Docs/EPIGENOME_SNAPSHOT.md`.
- Synced project documentation references, API surface, and testing commands for Package B.
- Refreshed verification snapshot in docs to current baseline run.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `643 passed, 3 skipped` (`pytest -q tests`).
- GenomeVector focused run: `17 passed` (`pytest -q tests/test_genome_vector.py`).
- EpigenomeSnapshot focused run: `16 passed` (`pytest -q tests/test_epigenome_snapshot.py`).

---

## 2026-03-24 - GenomeVector documentation sync

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/GENOME_VECTOR.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Added documentation coverage for implemented Package A genome functionality in `src/genome.py`.
- Added dedicated implementation guide `Docs/GENOME_VECTOR.md`:
 - `GeneDescriptor`, deterministic `GENE_REGISTRY`, `GenomeVector` API
 - mutation/crossover modes (`arithmetic`, `uniform`, `sbx`)
 - serialization and `to_agent_params()` mapping contract
 - determinism and range-safety guarantees
- Updated API reference with explicit `GenomeVector` section and invariants.
- Updated testing guide and root README with new focused command:
 - `pytest -q tests/test_genome_vector.py`
- Synchronized verification snapshot values with current test runs.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `627 passed, 3 skipped` (`pytest -q tests`).
- GenomeVector focused run: `17 passed` (`pytest -q tests/test_genome_vector.py`).

---

## 2026-03-24 - ACC conflict modulation documentation sync

Updated files:
- `README.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_acc_conflict_modulation.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Synced `NeuromodulatorState.update_from_signals(...)` API with implemented ACC behavior:
 - split conflict channels (`cognitive_conflict`, `affective_conflict`)
 - shared `dt` timescale for ACC smoothing and interaction field update
 - combined conflict trace as ACC state metric
 - persistence/backward-compatibility notes for ACC traces
- Added implementation-status section to ACC spec with current stabilization mechanics:
 - bounded gain deltas
 - serotonin inhibition
 - soft normalization
 - homeostatic NE/CORT decay
 - trace-based temporal dynamics
- Updated neuromodulator regression test commands to include:
 - `tests/test_acc_conflict_modulation.py`

Validation status reflected in docs:
- Core codebase run (excluding Demo): `610 passed, 3 skipped` (`pytest -q tests`).
- Neuromodulator interaction focused run: `44 passed` (`pytest -q tests/test_acc_conflict_modulation.py tests/test_neuromodulators_phase2.py tests/test_neuromodulator_integration.py tests/test_neuromodulator_interaction_layer.py`).

---

## 2026-03-23 - Wakefulness Process C documentation sync

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/00_INDEX.md`
- `Docs/00_INDEX_NEW.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_basal_ganglia_integration.md`
- `Docs/Phase2_Wakefulness_PFC_Extension.md`
- `Docs/spec_circadian_process_c.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Wakefulness documentation was synchronized with the implemented Process S + Process C model.
- The formulas are fixed:
 - `C(t) = A * sin(2πt / T + phase)`
 - `wake_drive = C - S`
 - `alertness = base - S + C`
- The semantics of cognitive reliability were updated:
 - primary path: `get_cognitive_reliability()` (through alertness, with clamp)
 - the fallback `(1 - wakefulness)` is retained as legacy compatibility.
- Persistence fields of wakefulness and the circadian process were specified in the API and storage documentation.
- Documentation index pages were updated with a link to `spec_circadian_process_c.md`.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `595 passed, 3 skipped` (`pytest -q tests`).
- Wakefulness + circadian focused run: `44 passed` (`pytest -q tests/test_wakefulness.py tests/test_agent_lifetime_save_load.py`).

---

## 2026-03-22 - Neuromodulator interaction layer documentation sync

Updated files:
- `Docs/NEUROMODULATOR_INTERACTION_LAYER.md`
- `Docs/API.md`
- `Docs/INDEX.md`
- `Docs/TESTING.md`
- `Docs/NEUROMODULATORS_QUICK_REFERENCE.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- A separate document was added for `NeuromodulatorField` and the coupled dynamics of `DA/5HT/NE/ACh`.
- The implemented baseline-centered coupling formula is fixed:
 - `dM/dt = base_signal + W * (M - baseline) - decay * (M - baseline)`
- The neuromodulator section of the API was updated:
 - `NeuromodulatorField`
 - the updated `NeuromodulatorState.update_from_signals(...)`
 - serialization and deserialization of `interaction_field`
- The index and the testing guide were updated:
 - links and commands for the interaction-layer regression bundle were added.
- `NEUROMODULATORS_QUICK_REFERENCE.md` was synchronized with the current interface and behavior.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `589 passed, 3 skipped` (`pytest -q tests`).
- Neuromodulator interaction focused run: `29 passed` (`pytest -q tests/test_neuromodulators_phase2.py tests/test_neuromodulator_integration.py tests/test_neuromodulator_interaction_layer.py`).

---

## 2026-03-22 - Semantic similarity replacement documentation sync

Updated files:
- `Docs/API.md`
- `Docs/Phase_5_0_1_Value_Layer_RU_Spec.md`
- `Docs/INDEX.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- The description of `state_similarity` / `state_vector` was synchronized with the implemented
 deterministic semantic hashing in `src/value_layer.py`.
- A formal description of the algorithm for text features was added:
 - tokenization (`eat_food -> ["eat", "food"]`)
 - stable unit vectors of words through a hash
 - averaging and normalization of the phrase vector
 - cosine similarity for matching states
- The general documentation index was updated:
 - the specification `spec_semantic_similarity_replacement.md` was added
 - the timestamp and the verification snapshot were brought up to date.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `584 passed, 3 skipped` (`pytest -q tests`).

---

## 2026-03-22 - Slow tonic dopamine documentation sync

Updated files:
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Synced ValueLayer documentation with implemented slow tonic dopamine behavior:
 - tonic tracks filtered phasic mean via `tonic_slow_rate` (default `0.01`)
 - CER stress controls tonic target base (no instant tonic jump)
 - runtime update diagnostics now include `mean_phasic`
- Added snapshot/persistence field docs for tonic dynamics:
 - `td_tonic_slow_rate`
 - `td_phasic_mean`
 - `td_tonic_target_base`
- Updated architecture notes and runtime limits to reflect phasic/tonic separation.
- Extended Phase 5.x testing coverage list with new tonic drift and persistence scenarios.
- Refreshed verification date/counters in core docs.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `580 passed, 3 skipped` (`pytest -q tests`).

---

## 2026-03-21 - Per-axis affective decay documentation sync

Updated files:
- `README.md`
- `Docs/spec_per_axis_affective_decay.md`
- `Docs/affective_core_phase4_spec.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/START_HERE_NEW.md`
- `Docs/INDEX.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Synced Phase 4 docs with implemented per-axis inertia model (`axis_decay` / alias `affective_decay`).
- Replaced outdated “single `alpha` for all axes” wording with axis-specific update equation.
- Added documented defaults for biologically distinct timescales:
 - `valence=0.92`, `arousal=0.80`, `dominance=0.97`
 - `stress=0.75`, `curiosity=0.78`, `trust=0.95`
- Documented legacy compatibility (`pleasure -> valence` and related axis alias mapping).
- Updated save/load and test coverage references for the new fields.
- Synced onboarding/index pages to expose the new Phase 4 docs and refreshed core-suite counters.
- Synced top-level README quick navigation and Phase 4 behavior summary.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `578 passed, 3 skipped` (`pytest -q tests`).

---

## 2026-03-21 - HIE-003 documentation sync (project docs update)

Updated files:
- `README.md`
- `Docs/API.md`
- `Docs/INDEX.md`
- `Docs/TESTING.md`
- `Docs/spec_deliberative_planning_v2.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Updated runtime docs from HIE-002-only planning to HIE-003 tree mode with HIE-002 fallback.
- Documented new imagination controls:
 - `imagination_enable_action_sequences`
 - `imagination_action_branching`
 - `imagination_max_tree_nodes`
 - `imagination_action_temperature`
 - `imagination_value_backup`
- Updated planning aggregation rule:
 - from `max(memory_rollout, imagined_value)` to blend
 - `rollout_value = (1 - imagination_value_blend) * memory_rollout + imagination_value_blend * imagined_value`
- Added planning telemetry fields:
 - `planning_imagination_tree_nodes`
 - `planning_imagination_tree_edges`
 - `planning_imagination_action_count`
 - `planning_imagination_branching`
- Added `tests/test_hie_003.py` to imagination/planning regression bundles.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `575 passed, 3 skipped` (`pytest -q tests`).
- Decision/planning/credit focused run: `68 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_imagination_engine_spec_001.py tests/test_hie_002.py tests/test_hie_003.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).
- HIE-focused run: `15 passed` (`pytest -q tests/test_imagination_engine_spec_001.py tests/test_hie_002.py tests/test_hie_003.py`).

---

## 2026-03-21 - HIE-002 documentation sync (project docs update)

Updated files:
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/INDEX.md`
- `Docs/TESTING.md`
- `Docs/spec_deliberative_planning_v2.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Updated project-level docs from HIE-001 baseline to HIE-002 runtime behavior.
- Documented `generate_structured_imagination(...)` integration in deliberative planning with HIE-001 compatibility wrapper.
- Updated imagination complexity guards:
 - `samples <= 8`, `depth <= 5`, `branching <= 4`
 - `max_graph_nodes <= 96`, `max_graph_edges <= 192`
 - trajectory confidence bounded in `[0, 1]`
- Added new planning telemetry fields:
 - `planning_imagined_trajectory_count`
 - `planning_imagined_confidence_mean`
 - `planning_imagined_novelty_mean`
- Added `tests/test_hie_002.py` to regression bundles and imagination-focused test commands.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `571 passed, 3 skipped` (`pytest -q tests`).
- Decision/planning/credit focused run: `64 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_imagination_engine_spec_001.py tests/test_hie_002.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).
- HIE-focused run: `11 passed` (`pytest -q tests/test_imagination_engine_spec_001.py tests/test_hie_002.py`).

---

## 2026-03-20 - HIE-001 documentation sync (project docs update)

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_deliberative_planning_v2.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Added HIE-001 references to main navigation/index pages.
- Documented implemented `HippocampalImagineEngine` integration in planning:
 - `rollout_value = max(memory_rollout, quantile(imagined_rollouts, 0.7))`
 - hard caps for imagination branch (`samples/depth/branching/max_nodes`)
 - novelty bonus behavior and bounded stop conditions.
- Added planning telemetry fields for imagination to API/spec docs.
- Updated focused test bundles and verification counters with `tests/test_imagination_engine_spec_001.py`.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `566 passed, 3 skipped` (`pytest -q tests`).
- Decision/planning/credit focused run: `59 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_imagination_engine_spec_001.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).
- HIE-focused run: `6 passed` (`pytest -q tests/test_imagination_engine_spec_001.py`).

---

## 2026-03-20 - Documentation sync for Deliberative Planning v2 implementation

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Added Deliberative Planning v2 spec to primary navigation and documentation index.
- Documented implemented `DecisionArbitrator` contract:
 - uncertainty composition + EMA
 - hysteresis mode switching
 - uncertainty-driven policy temperature
 - policy reliability coupling with replay causality/stability
- Documented Deliberative Planning v2 behavior in `Agent.step()`:
 - similarity-filtered episodic candidates
 - uncertainty-adaptive rollout depth
 - rollout value as max discounted trajectory return
 - value-of-information exploration bonus (`gain * (1 - confidence)`)
 - safety guards (`support >= 0.05`, `confidence >= planning_min_confidence`)
 - complexity guards (`actions <= 32`, `samples <= 8`, `depth <= 6`)
 - planning metadata/telemetry fields: rollout depth/samples/used, exploration bonus mean
 - pressure-only biasing (no planning-driven policy-temperature relief)
- Documented replay credit-assignment behavior:
 - reward-anchored causal depth
 - anchor selection priority (reward -> TD shock -> midpoint fallback)
 - eligibility/credit-window diagnostics in sleep stats and `Agent.get_state()`
- Refreshed verification counters in high-level docs and testing guide.

Validation status reflected in docs:
- Core codebase run (excluding Demo): `560 passed, 3 skipped` (`pytest -q tests`).
- Spec 011/011a focused run: `53 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).

---

## 2026-03-17 - EDPC <-> SAC sync + documentation refresh

Updated files:
- `src/sleep.py`
- `src/value_layer.py`
- `src/selector.py`
- `src/storage.py`
- `tests/test_edpc_sac_synchronization.py`
- `Docs/spec_edpc_sac_synchronization.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key implementation updates:
- Sleep-only EDPC <-> SAC synchronization (EMA transfer + TD-based stability updates).
- Conflict gating with `conflict_flag` and per-sleep-cycle reset.
- Energy budget enforcement with normalized replay-priority cost.
- Prediction-shock score vs flag separation.
- REM `td_variance` growth clamped to `[0, 1]`.
- Expectation memory kept as `OrderedDict` for LRU-safe updates.

Validation status:
- Sync/EDPC focused run: `21 passed` (`pytest -q tests/test_edpc_sac_synchronization.py tests/test_phase_5_edpc.py tests/test_value_layer.py tests/test_value_layer_storage.py`).

---


## 2026-03-03 - SAC SWS/REM hardening + documentation refresh

Updated files:
- `src/sleep.py`
- `src/storage.py`
- `tests/test_semantic_action_consolidation.py`
- `tests/test_sleep_replay_storage.py`
- `README.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key runtime updates reflected in docs:
- SAC phase separation now includes strict hard constraints and explicit one-phase-per-action guard.
- SAC global phase is derived from effectively update-eligible rows (post-gating and precondition checks).
- Episode-level SAC gating is enforced before phase aggregation.
- Replay weighting uses hybrid quality-priority formula:
 - `weight = replay_priority * confidence * stability * (1 - shock)`
- Added REM stability floor:
 - `sac_stability_floor_rem`
- Added structural-alert lifecycle reset after calm cycles:
 - `sac_structural_alert_reset_cycles`
- Added semantic-confidence per-cycle step cap:
 - `sac_semantic_confidence_step_cap`
- Added persistence coverage for new SAC parameters in storage round-trip.

Validation status:
- Full project run: `519 passed, 3 skipped` (`pytest -q`).
- SAC/storage focused run: `16 passed` (`pytest -q tests/test_semantic_action_consolidation.py tests/test_sleep_replay_storage.py`).

---

## 2026-03-03 - SAC integration + variance floor + docs sync

Updated files:
- `src/selector.py`
- `src/agent.py`
- `src/sleep.py`
- `src/storage.py`
- `tests/test_semantic_action_consolidation.py`
- `tests/test_sleep_replay_storage.py`
- `Docs/spec_semantic_action_consolidation.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key implementation updates:
- Implemented Semantic Action Consolidation (SAC) in `SleepManager`:
 - sleep-only semantic updates by `action_id` into `selector.action_metadata`
 - replay gating by confidence/stability/shock/consolidation probability
 - weighted aggregation for observed/predicted outcomes and success/failure beta updates
 - hard constraints (`sac_alpha_slow <= 0.01`, shock mean block, minimum replay count)
 - runtime SAC diagnostics (`sac_rejected_*`, drift/growth/overconfidence indices)
- Added anti-crystallization variance floor:
 - `sigma_new = max(sac_sigma_floor, sigma_new)`
 - default `sac_sigma_floor = 0.01`
- Added persistence support:
 - `selector_action_metadata`
 - `sac_*` configuration and `last_sac_stats` in storage save/load path
- Added SAC test coverage (including variance-floor scenario) and extended storage round-trip checks.

Validation status:
- Full project run: `512 passed, 3 skipped` (`pytest -q`).
- SAC/storage focused run: `9 passed` (`pytest -q tests/test_semantic_action_consolidation.py tests/test_sleep_replay_storage.py`).

---

## 2026-03-03 - Phase 5 EDPC implementation + docs sync

Updated files:
- `src/value_layer.py`
- `src/agent.py`
- `src/sleep.py`
- `src/storage.py`
- `tests/test_phase_5_edpc.py`
- `tests/test_value_layer_storage.py`
- `tests/test_sleep_replay_storage.py`
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key implementation updates:
- Added Phase 5 EDPC in `ValueLayer`:
 - expectation memory (`expected_reward_mean/var`, `confirmation_count`, `confidence_score`, `stability_score`)
 - selective-plasticity alpha damping from confidence/stability
 - prediction-shock detection with temporary plasticity boost
 - EDPC runtime metrics (`confidence_distribution`, `stability_distribution`, `shock_frequency`, `effective_alpha_trajectory`)
- Integrated EDPC metadata into agent replay traces and feedback path:
 - `replay_priority`, `consolidation_weight`, confidence/stability snapshots
 - shock flag propagation and stress response
- Updated sleep replay logic:
 - EDPC replay-priority formula with shock/stability factors
 - replay diversity/shock/confidence/stability cycle metrics
 - EDPC replay controls persisted via storage
- Added dedicated EDPC test suite and storage coverage.

Validation status:
- Full project run: `504 passed, 3 skipped` (`pytest -q`).
- EDPC focused run: `5 passed` (`pytest -q tests/test_phase_5_edpc.py`).
- Targeted replay/value/storage regression bundle: `36 passed, 1 skipped`.

---

## 2026-02-26 - Dopaminergic TD documentation sync

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Synced ValueLayer API docs with implemented Dopaminergic TD behavior:
 - raw reward preserved (`reward_raw`) with optional scaling (`reward_scale`)
 - online clipping telemetry (`td_was_clipped`, `td_clip_frequency`, `td_clip_frequency_ema`)
 - adaptive online clip controls (`adaptive_td_clip_enabled`, target-rate adaptation)
 - stress-linked dip amplification and stress-linked alpha scaling
 - exploration coupling unfreeze floor and inhibit-mode guardrails in agent integration
- Updated architecture notes with current clipping/adaptation model and known modeling limits.
- Extended testing guide with dedicated Phase 5.x TD coverage and commands.
- Refreshed verification counters in high-level docs.

Validation status reflected in docs:
- Full project run: `499 passed, 3 skipped` (`pytest -q`).
- TD/value-layer focused run: `20 passed` (`pytest -q tests/test_dopaminergic_td_layer.py tests/test_value_layer_integration.py tests/test_value_layer_storage.py`).

---

## 2026-02-25 - ACC documentation sync and behavioral clarifications

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Key documentation updates:
- Added ACC-like conflict arbitration to top-level project status and navigation.
- Documented implemented ACC contracts in API:
 - arbitration metrics and outputs
 - hard constraints (hysteresis, refractory, control cost)
 - non-direct action rule (ACC modulates control only)
- Documented ACC/CER interaction constraints:
 - learning-rate boost is tied to `error_likelihood`
 - `inhibit` path works through threshold modulation (not direct pressure-vector suppression)
 - `control_demand` includes decision latency
 - combined CER+ACC threshold shift cap to avoid over-suppression resonance
- Extended testing guide with dedicated ACC coverage and commands.
- Refreshed verification counters in project docs.

Validation status reflected in docs:
- Full project run: `485 passed, 3 skipped` (`pytest -q`).
- ACC focused run: `15 passed` (`pytest -q tests/test_conflict_arbitration_layer.py tests/test_conflict_arbitration_integration.py tests/test_conflict_arbitration_storage.py`).
- CER/BG/ACC focused run: `34 passed` (`pytest -q tests/test_emotional_regulation.py tests/test_emotional_regulation_integration.py tests/test_basal_ganglia_integration_spec.py tests/test_conflict_arbitration_layer.py tests/test_conflict_arbitration_integration.py tests/test_conflict_arbitration_storage.py`).

---

## 2026-02-25 - CER/BG documentation sync

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_continuous_emotional_regulation.md`
- `Docs/spec_basal_ganglia_integration.md`

Key documentation updates:
- Synchronized project docs with implemented CER behavior:
 - nonlinear CER dynamics with saturation/threshold effects
 - `habit_gain_scale` modulation for habit pathway
 - bounded neuromodulator guidance in `[-0.006, +0.006]`
- Updated BG integration spec with CER-related process inputs:
 - `exploration_bias`, `decision_threshold_shift`, `habit_gain_scale`
 - uncertainty bonus cap and Go envelope cap
- Updated API reference with current CER and BG contracts.
- Updated testing guide with CER-focused regression coverage and commands.
- Refreshed verification counters in high-level docs.

Validation status reflected in docs:
- Full project run: `470 passed, 3 skipped` (`pytest -q`).
- CER/BG focused run: `19 passed` (`pytest -q tests/test_emotional_regulation.py tests/test_emotional_regulation_integration.py tests/test_basal_ganglia_integration_spec.py`).

---

## 2026-02-22 - External Interaction Layer docs sync

Updated files:
- `README.md`
- `Docs/INDEX.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_external_interaction_layer.md`

Key documentation updates:
- Replaced outdated external-layer spec text with implemented behavior:
 - nonlinear drive dynamics (`decay + saturation + competition`)
 - strategy logit updates (`weight decay + softmax/temperature`)
 - explicit drive-strategy-policy coupling
 - expanded Bayesian hypothesis recalibration (`P(E|¬H)` / optional `P(E)`)
- Added API-level contracts for new agent external methods and scheduler pipeline.
- Added architecture section documenting runtime path:
 `feedback -> learning hooks -> strategy weights -> selector pressure -> BG gate`.
- Added GUI external panel contract in Russian labels.
- Added dedicated testing documentation for `tests/test_external_interaction_layer.py`.

Validation status reflected in docs:
- Full project run: `448 passed, 3 skipped` (`pytest -q`).
- External interaction focused run: `15 passed` (`pytest -q tests/test_external_interaction_layer.py`).

---
## 2026-02-21 - Documentation sync for BG/Autonomous behavior fixes

Updated files:
- `README.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_basal_ganglia_integration.md`
- `Docs/PHASE_3_GUIDE.md`

Key documentation updates:
- Formalized single-point biological modulation: selector pressure is cognitive-only, BG applies affect/threat/fatigue/neuromodulator effects.
- Documented corrected wakefulness/fatigue semantics via cognitive reliability (`1 - wakefulness` path).
- Documented `NO_ACTION` contract (no random fallback after thalamic gate inhibition).
- Documented internal simulation parity with live pipeline (`compute_pressures -> BG.process -> ThalamicGate.select`).
- Documented GUI autonomous internal thought traces (`[AUTO] think: ...`) on internal cycle ticks.

Validation status reflected in docs:
- Full project run: `433 passed, 3 skipped` (`pytest -q`).

---

## 2026-02-20 — Autonomous Organism Spec v1 Audit Hardening + GUI Error UX

Updated files:
- `src/autonomous_organism.py`
- `src/agent.py`
- `src/gui.py`
- `src/storage.py`
- `tests/test_autonomous_organism.py`
- `tests/test_agent_lifetime_save_load.py`

Key changes:
- Introduced explicit physiology modes per autonomous tick:
 `idle`, `passive`, `internal_processing`, `speaking`, `low_energy`.
- Replaced constant full cognitive load with mode-driven dynamic load.
- Added `dt` sanitization and anomaly logging (`dt_anomaly`) with bounded runtime `dt`.
- Unified energy/fatigue update path to avoid double/triple energy spending.
- Added social-drive discharge after speech events.
- Added explicit logging for internal affect-apply failures (`internal_affect_apply_failed`).
- Extended tick diagnostics:
 `physiology_mode`, `cognitive_load`, `load_components`, `energy_update`, `dt_input`, `dt_clamped`.
- GUI autonomous error indicator now counts only critical errors and is clickable:
 clicking `ошибки:N` opens a details window with critical error records.
- Save/load compatibility verified for autonomous + wakefulness state.

Validation:
- Added/updated autonomous tests in:
 - `tests/test_autonomous_organism.py`
 - `tests/test_agent_lifetime_save_load.py`
- Full project test run after change: `419 passed, 3 skipped`.

---


## 2026-02-19 — Affective Core Stabilization

Updated files:
- `src/affective_space.py`
- `src/storage.py`
- `tests/test_affective_core_phase4.py`
- `tests/test_affective_space_storage.py`

Key changes:
- Legacy additive dynamics (`compat_delta`) are now opt-in via `legacy_compat_weight`.
- `AffectiveSpace` remains canonical source of truth; legacy affect state is projection-only.
- Dynamic norm cap updated with anti-sticky behavior:
 - headroom-aware growth near `norm_cap_max`
 - slow global release via `norm_cap_global_release_rate`
- Baseline is runtime-adaptive via `baseline_adapt_rate`.
- Save/load updated for new affective-space fields.

Validation:
- Added tests for legacy compat gating, global norm-cap release, and dynamic baseline drift.
- Full project test run after change: `403 passed, 3 skipped`.

---

## February 2026 — Phase 6.2/6.2.1 Filtered Consolidation

### Selective consolidation of episodes during sleep

**Files changed:** `src/sleep.py`, `src/agent.py`, `src/storage.py`, `tests/test_phase_6_2_filtered_consolidation.py`, `tests/test_sleep_replay_td_bg.py`

**Key changes:**
- Strict criteria for admitting episodes to replay consolidation were added:
 - `|TD_mean| >= td_threshold`
 - `TD_variance <= td_variance_cap`
 - `salience >= salience_threshold`
 - `reinforcement_count >= min_reinforcement_for_consolidation`
 - `value_variance_ratio < variance_gate_threshold`
 - `ACh_effective >= ach_min_for_consolidation`
 - `stability_flag == True`
- `consolidation_score` was added, bounded by `consolidation_cap`.
- Sleep updates were moved to the formula `delta_value = sleep_alpha * consolidation_score * sign(TD_mean)`, with the bounds:
 - `sleep_alpha_cap`
 - `per_update_cap`
 - `max_l2_update_per_cycle`
 - `global_sleep_update_budget`
- A mandatory variance gate was enabled (`variance_ratio >= 1.0` blocks replay in the sleep cycle).
- Extended sleep diagnostics were added:
 - `total_episodes_examined`
 - `total_episodes_consolidated`
 - `rejected_due_to_*`
 - `mean_consolidation_score`
 - `sleep_update_l2_total`
 - `variance_ratio`
 - `consolidation_ratio`

### Architectural clarifications of TD statistics (variant A)

- A per-episode TD history (`td_history_snapshot`) and the following quantities were introduced:
 - `td_mean_snapshot`
 - `td_variance_snapshot`
- TD history is updated only during wakefulness and feedback (in `Agent`).
- During sleep, replay does not change the episode TD statistics; sleep affects only `ValueLayer` and BG updates.
- For determinism, `value_variance` is frozen at the start of the sleep cycle and used at every stage of the cycle.

### Save/Load

- `AgentStorage` saves and restores the filtered-consolidation parameters:
 - filter thresholds (`td_threshold`, `td_variance_cap`, `salience_threshold`, `variance_gate_threshold`, `ach_min_for_consolidation`, `stability_index_threshold`)
 - score weights (`w_td`, `w_salience`, `w_importance`, `w_ach`, `w_encoding`)
 - caps/budgets (`sleep_alpha_cap`, `per_update_cap`, `max_l2_update_per_cycle`, `global_sleep_update_budget`)

### Tests

- Phase 6.2 tests were added:
 - `tests/test_phase_6_2_filtered_consolidation.py`
- Replay regression tests were updated:
 - `tests/test_sleep_replay_td_bg.py`
- Additional coverage:
 - correct calculation of TD-history mean and variance
 - operation of `td_variance_cap`
 - freezing of variance within one sleep cycle
 - the guarantee that sleep replay does not mutate TD history

**Current project status:** **403 passed, 3 skipped**
**Long stress (5000 cycles, opt-in):** **1 passed**

---

## February 2026 — Phase 5.A.2 Online/Sleep Plasticity Harmonization

### Wakeful and sleep plasticity were harmonized

**Files changed:** `src/value_layer.py`, `src/sleep.py`, `src/agent.py`, `src/storage.py`

**Key changes:**
- `ValueLayer.update(...)` received a mode flag `mode`: `online` / `sleep`
- Update counters were separated:
 - `online_update_count`
 - `sleep_update_count`
- Learning-rate defaults were separated:
 - `alpha_online_default`
 - `alpha_sleep_default`
- `td_clip_online` was added to bound the online TD amplitude
- The following were added to sleep replay:
 - stability modulation of sleep alpha (`clamp(stability, 0.3..1.0)`)
 - replay temperature decay (`effective_priority = priority * temperature`)
 - sleep dopamine scaling (a weakened DA shift through `apply_dopamine_delta`)
 - an extended summary (`total_value_delta_sleep`, `total_bg_delta_sleep`, `sleep_update_count`, `replay_blocked`)
 - immediate stop of replay when `value_total_cap` is reached

**Diagnostics:**
- `Agent.get_state()` / `Agent.snapshot()` now return:
 - `value_drift_ratio = sleep_update_count / (online_update_count + 1)`
 - `value_drift_warning` when `value_drift_ratio > 3.0`

**Save/Load:**
- Saving and restoring the new ValueLayer and SleepManager parameters were added to `AgentStorage`.

**Tests:**
- Added or updated:
 - `tests/test_value_layer.py`
 - `tests/test_value_layer_integration.py`
 - `tests/test_value_layer_storage.py`
 - `tests/test_sleep_replay_td_bg.py`
 - `tests/test_sleep_replay_storage.py`
- Overall project status after the changes: **369/369 PASS**

---

## February 2026 — Phase 5.0/5.0.1 Value Layer and TD Error

### A state value layer (Value Layer) was added

**New file:** `src/value_layer.py`

**Key changes:**
- TD learning was implemented: `δ = r + γV(s_next) - V(s)`
- A deterministic `StateEncoder` (normalization and a stable hash)
- Tabular `V(s)` with LRU eviction (`max_states=50_000`)
- Stability bounds:
 - clamp for `δ` and `V(s)`
 - a bound on the magnitude of an update
 - at most one update per tick
- Dopamine in `Agent.step()` now encodes the TD error:
 - reward-driven DA is disabled in the agent pipeline
 - an additive `dopamine_delta = clamp(δ * k, -0.1, 0.1)` is applied

**Integration:**
- `Agent.step()` updates `value_layer` and applies the TD shift of dopamine
- `Agent.get_state()` returns `value_layer`
- `storage.save_agent()` / `load_agent()` save and restore `value_layer`
- The GUI shows the Value Layer block in the right panel and in the inspector

**Tests:**
- `tests/test_value_layer.py`
- `tests/test_value_layer_integration.py`
- `tests/test_value_layer_storage.py`

### Reward and punishment sensitivity in the Affective Space derive logic was updated

**File:** `src/agent.py` (`_derive_affective_space_inputs`)

**Changes:**
- The asymmetry was removed: vulnerability affects both `pleasure` and `pain`
- A nonlinear response with saturation (saturating gain) was introduced
- Sensitivity modulation through `arousal` was added

**Tests:**
- `tests/test_affective_space_integration.py` was updated

---

## February 2026 — Phase 4.5 Stability Monitoring and Drift Control

### The Phase 4.5 diagnostic layer was added

**New file:** `src/stability_monitoring.py`

**Key changes:**
- Read-only stability monitoring, with no write side effects
- Analysis in a sliding window of `500..2000` ticks
- Drift flags:
 - `regulation_overuse`
 - `background_drift`
 - `neuromodulator_drift`
 - `dominant_emotion_lock`
 - `outlook_bias`
- Hysteresis (at least 2 consecutive windows) for drift flags
- Calibration of `baseline_background` on the warm-up median (the first tick is not used)
- Stability: `stability_index = 1.0 - weighted_sum(flags)` with clamp `[0..1]`
- Recommendations:
 - `inspect_regulation`
 - `inspect_neuromodulators`
 - `inspect_background`
 - `inspect_expectations`
 - `inspect_memory`
 - `none`

**Integration:**
- `Agent.step()` updates the layer after Phase 4.4
- `Agent.get_state()` returns `stability_monitor`
- `storage.save_agent()` / `load_agent()` save and restore `emotional_stability`
- The GUI shows the monitoring block in the right panel and in the inspector

**Tests:**
- `tests/test_stability_monitoring.py`
- `tests/test_stability_monitoring_storage.py`
- `tests/test_stability_monitoring_integration.py`

---

## February 2026 — Phase 4.4 Regulation (Emotional Expectations)

### The Phase 4.4 regulatory layer was added

**New file:** `src/emotional_regulation.py`

**Key changes:**
- Activation by forecast (prob≥0.8, conf≥0.6, risk=True, outlook=escalating)
- Modes stabilizing / dampening / containment
- Correction bounds: |delta| ≤ 0.1, L2 norm ≤ 0.15
- Only background parameters and serotonin are corrected (DA/NE/CORT are unchanged)

**Integration:**
- `Agent.step()` calls regulation after expectations
- `storage.save_agent()` / `load_agent()` save and restore the layer
- The GUI shows the mode and the latest deltas

**Tests:**
- `tests/test_emotional_regulation.py`
- `tests/test_emotional_regulation_storage.py`

---

## February 2026 — Phase 4.3 Emotional Expectations

### A predictive layer of emotional expectations was added

**New file:** `src/emotional_expectations.py`

**Key changes:**
- Emotion trends (increasing/stable/decreasing) over early and late episodes
- Probabilities and confidence in the range [0..1]
- Risk of recurrence of obsessive patterns (obsessive + inertia)
- Global forecast: stabilizing / volatile / escalating

**Integration:**
- `Agent.step()` updates expectations after emotional memory
- `storage.save_agent()` / `load_agent()` save and restore expectations
- The GUI (right panel) shows a short summary and expectation metrics

**Tests:**
- `tests/test_emotional_expectations.py`
- `tests/test_emotional_expectations_storage.py`

---

## February 2026 — Phase 4.2 Emotional Memory and Narratives

### A block of emotional memory and retrospective narratives was added

**New file:** `src/emotional_memory_narratives.py`

**Key changes:**
- Emotional episodes and patterns are formed from semantic emotions
- Recency weighting was introduced
- Patterns and traits are not built when the number of episodes is small (min_total_episodes)
- A dominance-shift sentence was added: «Ранее преобладала X, сейчас чаще возникает Y»
- `agent_lifetime` data are used in the narrative

**Integration:**
- `Agent.step()` updates emotional memory after semantic emotions
- `storage.save_agent()` / `load_agent()` save and restore emotional memory
- The GUI (right panel) shows the summary and the metrics

**Tests:**
- `tests/test_emotional_memory_narratives.py`
- `tests/test_emotional_memory_narratives_integration.py`
- `tests/test_emotional_memory_narratives_storage.py`

---

## February 2026 — Phase 4 (pre) Affective Space

### Contextual coupling of reward to pain

**Change:**
- `pain` now depends on vulnerability, and on the negative reward as well.

**Formula:**
```
pain = clamp(
    max(0.0, -reward) * intensity * (0.5 + 0.5 * vulnerability)
)
```

**Effect:**
- High vulnerability amplifies pain,
- resilience reduces the direct coupling of negative reward and pain.

**Files:**
- `src/agent.py` (mapping in `_derive_affective_space_inputs`)
- `tests/test_affective_space_integration.py` (new test)
- `Docs/Phase_4_Affective_Space_Spec.md` (implementation note)

---

## February 2026 — Phase 3.75 Affective Background Field

### An inertial affective background with lifetime modulation was added

**New file:** `src/affective_background.py`

**Class `AffectiveBackgroundField`:**
- forms background components from stable affective traces
- the dynamics depend on `lifetime_progress` (inertia, decay, competition)
- wakefulness affects only the update noise
- it does not affect the selector or motivation

**Integration:**
- `Agent.step()` updates the background after `AffectivePersistenceLayer`
- `storage.save_agent()` / `load_agent()` save and restore the background
- The GUI displays the background components (anxiety/tension/satisfaction/interest)

**Tests:**
- `tests/test_affective_background_field.py`

---

## February 2026 — Phase 3.5 Affective Persistence

### A layer of stable affective traces was added

**New file:** `src/affective_persistence.py`

**Class `AffectivePersistenceLayer`:**
- stores affective traces (anxiety, tension, satisfaction, interest)
- accumulates traces under repeated affect signals
- decays slowly (decay_rate 0.01–0.05)
- uses neuromodulators as retention factors
- reads T1/T2 for baseline deviations
- it does not affect the selector directly

**Integration:**
- `Agent.step()` updates traces on every step
- `storage.save_agent()` / `load_agent()` save and restore traces
- The GUI saves and loads traces together with the agent state

**Tests:**
- `tests/test_affective_persistence.py` (Persistence/Decay/Accumulation/No Action Influence)

### Saving the agent lifetime

**Storage:**
- `created_ts` and `_simulated_sleep_seconds` are saved
- they are restored on load (when `agent` is passed)

**Tests:**
- `tests/test_agent_lifetime_save_load.py`

---

## February 2026 — Neuromodulators

### A neuromodulator system was added

**New file:** `src/neuromodulators.py`

**Class `NeuromodulatorState`** implements four global regulatory signals:

| Neuromodulator | Function | Influence |
|---|---|---|
| **DA** (Dopamine) | Reinforcement and value | Strengthening of patterns during sleep |
| **NE** (Norepinephrine) | Mobilization and novelty | Formation of additional chains |
| **5-HT** (Serotonin) | Stability | Stabilization of experiences |
| **CORT** (Cortisol) | Stress | Aggressive forgetting |

**Methods:**
```python
# Инициализация
nm = NeuromodulatorState()

# Обновление от сигналов
nm.update_from_signals(reward=0.5, novelty=0.2, conflict=0.1)

# Спад во времени
nm.decay_over_time(elapsed=10.0)

# Сериализация
nm.to_dict()
NeuromodulatorState.from_dict(data)
```

**Integration:**
- The agent initializes `NeuromodulatorState` on creation
- `step()` updates neuromodulators from signals (reward, novelty, conflict)
- `sleep()` applies effects during consolidation:
 - DA strengthens cortical patterns
 - NE promotes the formation of chains
 - 5-HT stabilizes experiences
 - CORT removes unstable traces
- `storage.save_agent()` / `load_agent()` save and restore neuromodulators
- The GUI displays the diagnostic block DA/NE/5-HT/CORT

**Tests:** 4 new tests in `tests/test_neuromodulators.py`

---

## What was added earlier?

### 1. **Automatic selector training**

**New file:** `src/trainer.py`

**Class `SelectorTrainer`** provides:
- Automatic training of the selector on a dataset
- Computation of accuracy before and after training
- A detailed result for each experience
- A configurable learning rate

**Methods:**
```python
trainer = SelectorTrainer(selector, hippocampus, cortex)

# Один эпох на всех опытах
stats = trainer.train_epoch(experiences, learning_rate=1.0)

# Несколько эпох
history = trainer.train_full(experiences, epochs=5, learning_rate=0.5)

# Получить accuracy без обновления весов
accuracy = trainer.get_accuracy(experiences)

# Детальные результаты
results = trainer.get_detailed_results(experiences)
```

### 2. **GUI functionality**

**A new "Авто-тренировка" button** in the interface

**Opens a window with:**
- Settings (number of epochs, learning rate)
- A display of accuracy before and after
- The percentage of improvement
- History by epoch
- Detailed results for each experience

### 3. **Full test coverage**

**New file:** `tests/test_trainer.py` (7 tests)

**Total tests:** 23
- test_selector.py: 5 tests
- test_hippocampus.py: 6 tests
- test_agent.py: 5 tests
- test_trainer.py: 7 tests

**All tests passed:** 23/23

### 4. **Logic fixes**

**In selector.py:**
- A check `if a in scores` was added — the selector does not crash on unknown actions
- Filtering of negative experiences was added — the system prefers positive experience
- Influence weights were increased: 0.1→0.5 for experiences, 0.05→0.2 for patterns

### 5. **Usage examples**

**New file:** `examples_training.py`

**4 examples:**
1. Basic training on a dataset
2. Detailed analysis of results
3. Comparison of different learning rates
4. Integration with the agent

### 6. **Documentation**

**Files updated:**
- `LEARNING.md` — a full account of the architecture and of use
- A description of automatic training was added
- Usage examples were added

## How to use the new functionality

### Option 1: GUI (recommended)

```
1. Запустить gui.py
2. Нажать "Загрузить датасет"
3. Нажать "Авто-тренировка"
4. Установить параметры:
   - Количество эпох: 5-10
   - Learning rate: 0.5
5. Нажать "▶️ Начать тренировку"
6. Смотреть результаты!
```

### Option 2: Code

```python
from trainer import SelectorTrainer
from loader import load_experiences_from_datasets_folder

# Загружаем опыты
experiences = load_experiences_from_datasets_folder()

# Создаем тренер
trainer = SelectorTrainer(selector, hippocampus, cortex)

# Тренируем
history = trainer.train_full(experiences, epochs=5, learning_rate=0.5)

# Проверяем результаты
accuracy = trainer.get_accuracy(experiences)
print(f"Accuracy: {accuracy:.2%}")
```

### Option 3: Examples

```bash
python examples_training.py
```

## Why this works

### The principle of supervised learning

```
Датасет содержит правильные ответы:
  context="кто ты" → action="ответить_кто_я"

Тренировка:
  1. Берем контекст "кто ты"
  2. Селектор выбирает действие
  3. Если совпадает с правильным → reward=+1.0
  4. Если не совпадает → reward=-1.0
  5. Обновляем вес действия на: weight += learning_rate * reward

Результат:
  - Правильные действия получают выше веса
  - Неправильные действия получают ниже веса
  - Accuracy растет с каждым эпохом
```

## Statistics

**Code size:**
- trainer.py: ~150 lines
- GUI changes: ~200 lines
- Tests: ~130 lines
- Documentation: updated

**Performance:**
- Training on 3 or more experiences: <1 second
- Accuracy testing: <0.1 second

**Quality:**
- All 23 tests passed
- The code is tested and documented
- The GUI is direct and informative

## What can be improved next

1. **Batch processing**: process several experiences at once
2. **Validation**: split the dataset into train and val to check overfitting
3. **Plots**: add a visualization of accuracy by epoch
4. **Saving results**: save the training history to a file
5. **Adaptive learning rate**: change the learning rate during training

## Files changed or created

### New files:
- `src/trainer.py` — the training class
- `tests/test_trainer.py` — trainer tests
- `examples_training.py` — usage examples

### Changed files:
- `src/gui.py` — a button and a window for automatic training were added
- `src/selector.py` — the action-selection logic was fixed
- `src/loader.py` — prefixes for context and action were added
- `LEARNING.md` — the documentation was updated

### Documentation:
- `LEARNING.md` — a full guide to use

---

**Date:** January 12, 2026
**Status:** fully completed and tested

