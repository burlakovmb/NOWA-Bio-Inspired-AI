# Specification: AffectiveSpace as the Platform Canon and an MCP Body without MotorAdapter

Russian version: [spec_affective_space_platform_body.ru.md](spec_affective_space_platform_body.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.

**Version:** 1.1  
**Status:** Ready for implementation — a document for the implementing agent  
**Date:** 2026-08-24  
**Patch 1.1:** the axes of A(t) are frozen forever in this specification; a real 1C system is the same transport contract, not a special case; an LLM does not participate in the body.  
**Audience:** the implementing agent (change the code strictly according to this text)  
**Platform (source of truth of the core):** `src/`  
**Current body layer (Demo, to be made universal):** `Demo/Virtual company/src/nowa_body/`

Related documents (do not rewrite them; only keep them consistent):

- `src/affective_space.py` — the as-built canon of A(t)
- `Docs/affective_core_phase4_spec.md`
- `Docs/spec_per_axis_affective_decay.md`
- `Demo/Virtual company/Docs/NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.md`
- `Demo/Virtual company/Docs/NOWA_Body_Layer_Phase1_Spec.md`

---

## 0. Assignment to the implementer (read this first)

Make two related changes to the architecture:

1. **Full coverage of the NOWA platform by the canonical `AffectiveSpace`.**  
   One vector A(t) is the sole source of affective state. Every module in `src/` that today reads `affect_state`, a parallel VAD, "stress" taken from somewhere else, or does not read affect at all when making decisions, receives an explicit contract: **it reads A(t) / `decision_bias()` / writes an `EmotionalImpulse`**, or it is explicitly marked affect-blind (data infrastructure).

2. **Abolish the concept of MotorAdapter as an extension point.**  
   A role is no longer written as a Python adapter of the form "action_type → parameters for 1C".  
   The contract of the body: **declare an MCP server → receive tools/list → the tools become organs → the NOWA mind controls the organs.**  
   Call parameters are assembled universally from the tool's JSON Schema, WorldState, and A(t), without domain Python.

The implementer does **not** add axes to A(t) (neither `urgent`, nor `budget`, nor any others), does **not** add a second emotional container, does **not** call MCP from `Agent.step`, and does **not** use a language model to assemble tool parameters.

---

## 1. The problem as built

### 1.1 AffectiveSpace is already the canon; coverage is not

The canon is already present in `src/affective_space.py`:

```
AXES = (valence, arousal, dominance, stress, trust, curiosity, stability, attachment)
range: [-1, 1]
A(t+1) = baseline + axis_decay*(A-baseline) + Σ impulses − λ*(A-baseline)  [+ optional legacy]
decision_bias() → {risk, response_speed, word_choice, empathy, goal_priority}
```

`Agent.affective_space` is the runtime source of truth. `affect_state` is a projection.

Gaps in coverage (to be repaired):

| Gap | Fact |
|---|---|
| Dual circuit | `emotional_regulation.py` keeps its own valence/arousal and is **not** an I/O path to A(t) |
| Semantics on the legacy form | `semantic_emotions.py` computes attractors from `legacy_axes_snapshot()`, not from the canon |
| Selector | `selector.py` takes the scalar `affect_modifier` and ignores the `decision_bias` vector |
| BG | aversive is almost only `stress`; it does not use `risk` / `trust` / `curiosity` |
| Sleep | `sleep.py` does not modulate the decay or the noise of A(t) |
| Memory | the hippocampus is not obliged to store an `EmotionalTrace` with the episode |
| Body | the encoder writes tokens; READ almost never calls `affective_space.step` |
| Outcome mapping | `encode_action_outcome` returns a mixture of valence/arousal/trust/stress — an incomplete canon, and the keys do not always match `AXES` |
| GUI / self_model | some panels still come from `affect_state` |

### 1.2 Why MotorAdapter cannot be scaled

The pipeline as built:

```
action_type (the role's dictionary: place_order_cheap_supplier, …)
    → MotorAdapter.resolve
        → capability_for_action(action_type)   # a parallel dictionary
        → _build_params(...)                   # NotImplemented / a role class
    → ProposedAction(tool_id, params)
```

This breaks on every new MCP:

- each server has its own set of tools and its own JSON Schema;
- `action_types` on a capability are a second language, which must be glued by hand to the BG channels;
- `_build_params` in `ProcurementBodyMotorAdapter` knows suppliers, coverage days, and strategies — that is **not the body**, it is a hidden domain brain;
- `register_from_mcp_discovery` is `NotImplementedError`;
- `event_classifier` is yet another piece of Python per role.

The owner of the platform: *declare an MCP server — receive the tools — the mind controls the tools as a body.*

MotorAdapter contradicts this. It is absent from the target architecture.

---

## 2. Principles (they must not be violated)

**P1. One affect.** Only `AffectiveSpace.axes`. Any other container is a projection or an interpretation (read-only).

**P2. Impulses, not assignment.** The external world and memory change A(t) through `EmotionalImpulse` (`source ∈ {external, memory, internal}`) and `AffectiveSpace.step(...)`. Assigning `axes["stress"] = 1.0` from the host or the body is forbidden.

**P3. The mind does not know MCP.** `Agent.step`, the selector, and the BG do not import the MCP SDK. They see context tokens, action channels (`tool_id` or `wait_and_monitor`), and A(t).

**P4. A tool is an organ.** After discovery, each tool is an `MCPCapability`. READ is a sensor. WRITE is a muscle. A `tool_id` of the form `mcp__<server>__<tool_name>` **is** the action channel of the basal ganglia.

**P5. No role-classes of muscles.** Subclasses of MotorAdapter are forbidden, and `motor_adapter: pkg.mod:Class` in YAML is forbidden as a required mechanism. The only thing permitted is a **declarative** hint (JSONPath / field aliases) in YAML, the same for any server.

**P6. Approval is outside.** HIGH_WRITE / IRREVERSIBLE are not bypassed by A(t). Stress does not disable `ApprovalGate`.

**P7. Learning during sleep.** The waking body: `decision_only=True`, and the episode is stored after the outcome is known. The path is immutable, and there is exactly one `EventType.ACTION`.

**P8. Money is not valence. Urgency is not an axis.**  
Cost, budget, and stock are scalars of `WorldState` and ranking features (`cost`, `quantity`).  
Urgency is the already existing `arousal` / `stress` plus `rank_weights().speed_seek`.  
**There will be no new axes of A(t).** The canon of `AXES`, eight names, is closed.

**P9. No projection of feelings.** Operational numbers and tokens. Nothing of the form "the agent is sad" as a control signal.

**P10. Universality is checked against a future 1C, not against the Mock.**  
This delivery may talk to MockMCP. When a real 1C MCP appears, it must stand **only** as one more `MCPTransport` (the same `list_tools` / `call_tool`). Zero edits to `AffectiveSpace`, SchemaBinder, Agent, ranking, or the YAML form of a role. If 1C requires a new Python class of muscle, the decision is not universal, and that is a bug in the specification.

**P11. Parameters are assembled by SchemaBinder, not by an "intelligence" outside.**  
The arguments of a tool are JSON Schema + WorldState + lexicon/aliases + `rank_weights()`. Neither a language model nor the domain code of a role takes part in this path.

---

## 3. The AffectiveSpace canon (freeze it)

File: `src/affective_space.py`.

The composition of `AXES` is **frozen**. Do not add axes, do not rename them, and do not make "temporary" axes for a domain. Without a separate decision of the owner, do not change:

- the composition of `AXES`, or the range [-1, 1];
- `EmotionalImpulse` / `EmotionalTrace`;
- the `step(...)` equation and the per-axis `axis_decay`;
- `decision_bias()` and `DECISION_DIMENSIONS`;
- `to_dict` / `from_dict` / the storage round-trip.

Permitted **additions** (without breaking signatures):

| API | Purpose |
|---|---|
| `AffectiveSpace.outcome_impulse(status: str, magnitude: float = 1.0) -> EmotionalImpulse` | A universal mapping from an MCP status to the canonical vector (see §6.6). Do not duplicate ad-hoc dictionaries in the encoder. |
| `AffectiveSpace.rank_weights() -> Dict[str, float]` | A convenient readout for the body: derived weights `{cost, speed, reliability, novelty, caution}` from `decision_bias()` and the axes. A pure function, with no I/O. |

The default mapping of `rank_weights()` (clamp every output to [-1, 1], then normalise into [0, 1] for the weights):

```
caution      = 0.5 + 0.5 * clamp(stress - 0.5*valence + 0.3*(1-trust))
cost_aversion = clamp(0.4 - 0.6*bias.risk + 0.4*caution)
speed_seek    = clamp(0.5 + 0.7*bias.response_speed + 0.3*max(0, arousal) - 0.2*stability)
reliability   = clamp(0.5 + 0.5*trust + 0.3*attachment - 0.4*bias.risk)
novelty_seek  = clamp(0.5 + 0.7*curiosity - 0.4*stress)
assertiveness = clamp(0.5 + 0.6*dominance + 0.3*bias.goal_priority)
```

`legacy_compat_weight` remains 0 by default.

---

## 4. Full coverage of `src/` — the contract matrix

Legend of modes:

- **R** — the module **reads** `axes` and/or `decision_bias()` / `rank_weights()`
- **W** — the module **writes** only through `EmotionalImpulse` + `step` (or returns an impulse to the agent)
- **P** — the module **projects** A(t) into the legacy form (a write to `affect_state` only from the Agent)
- **I** — interpretation (semantics, GUI); it does not control the choice
- **∅** — affect-blind (data/I/O); that is how it should be
- **X** — a gap today; after this specification, R/W is obligatory

The orchestrator of every W-call while awake is the `Agent` (and the body runtime for external impulses). Core modules do **not** call MCP.

### 4.1 The cognitive circuit

| Module | File | Mode | Contract |
|---|---|---|---|
| AffectiveSpace | `affective_space.py` | — | The canon. |
| Agent | `agent.py` | R/W/P | The sole orchestrator of `step()` for A(t). After every cognitive step: derive impulses (§7), `affective_space.step`, project `affect_state`. BG aversive = f(stress, caution). The selection modifier is not one scalar, but channel-wise from `decision_bias` (§7.2). |
| AffectiveState | `affect.py` | P | Projection only. `update_from_reward` is forbidden as a source of truth when `affective_space` is present. The GUI may read the projection. |
| ActionSelector | `selector.py` | R | `choose(..., affect_bias: Dict[str, float] \| None)`. The scalar `affect_modifier` is deprecated; leave it as a fallback equal to `1 + 0.2*response_speed - 0.25*max(0,stress)`. What is new: a per-action scale from the caller (the Agent), not domain logic inside the selector. |
| BasalGanglia | `basal_ganglia.py` | R | `aversive_signal` from the Agent: `max(0, stress, caution)`. Go gain rises with `response_speed`; NoGo rises with `caution`; exploration temperature rises with `novelty_seek`. Do not import AffectiveSpace; only a float or a dict from the Agent. |
| ThalamicGate | the same file | R | The Go threshold depends on `stability` (low → harder to let an impulsive signal through). |
| Hippocampus | `hippocampus.py` | R/W | On `store` after an outcome: `create_trace` together with the episode. On `activate`: `recall_trace` → memory impulses into Agent.step. It does not change A(t) itself. |
| Cortex | `cortex.py` | R | Consolidation and sleep may read `stability`/`arousal` as a plasticity gain (through SleepManager). |
| IntentMemory | `intent_memory.py` | R | Habits: reinforcement *= f(valence, threat←stress). Affect hooks already exist — move them onto a snapshot of A(t), not onto parallel fields. |
| ValueLayer | `value_layer.py` | W | A TD error becomes an internal impulse: `valence += tanh(td)`, `stress += max(0,-td)`, `curiosity += |td|*novelty`. Do not store an affect of its own. |
| PredictionLayer | `prediction_layer.py` | W | A prediction error or a shock becomes an impulse of stress/curiosity (low intensity). |
| DecisionArbitrator | `decision_arbitrator.py` | R | Weights of habitual versus deliberative: a high `axis_conflict` together with a low `stability` leads to the deliberative path. |
| ConflictArbitration | `conflict_arbitration.py` | R/W | `raw_conflict` is modulated by arousal/stress (as in the ACC specification). In return: a high perceived conflict becomes an internal impulse onto stress/arousal. There is no second state. |
| HippocampalImagineEngine | `hippocampal_imagine_engine.py` | R | Imagined outcomes do **not** write A(t). Scoring of trajectories uses the expected valence/stress from memory plus the current `rank_weights`. |
| Deliberative planning (Agent) | `agent.py` | R | Planning temperature rises with curiosity and falls with stress. The risk penalty of a rollout is multiplied by `cost_aversion`. |
| Experience / Path | `experience.py` | ∅ | A data structure. The ACTION label is `tool_id` in body mode. |
| Dataset / Sample / data_loader | `dataset.py`, `sample.py`, `data_loader.py` | ∅ | |
| ActionIntent / Realizer | `action_intent.py`, `action_realizer.py` | R | Natural-language generation and expression: `word_choice` and `empathy` from `decision_bias`. Do not confuse this with MCP muscles. |

### 4.2 The affective stack around the canon

| Module | File | Mode | Contract |
|---|---|---|---|
| AffectivePersistence | `affective_persistence.py` | R | Compute signals from a snapshot of A(t), not from threat/curiosity of `affect_state` treated as the truth. |
| AffectiveBackground | `affective_background.py` | R | It remains a modifier of decay, inertia, and noise for `step(background=...)`. It does not set the axes. |
| SemanticEmotions | `semantic_emotions.py` | I | **Move the attractors onto the canonical axes** (pleasure/pain are not primary). The legacy snapshot is for compatibility only. The layer still does not choose actions. |
| EmotionalMemoryNarratives | `emotional_memory_narratives.py` | I | Reads A(t) and the semantic layer. Does not write the axes. |
| EmotionalExpectations | `emotional_expectations.py` | R/W | Forecast versus fact: a mismatch becomes an impulse (the analogue of a prediction). |
| EmotionalRegulation | `emotional_regulation.py` | R/W | **A parallel VAD is forbidden as a source of truth.** CER either (a) becomes a pure modulator of `lambda_reg` / decay, reading A(t), or (b) emits internal impulses. Its own valence is no longer stored as the canon. |
| StabilityMonitoring | `stability_monitoring.py` | I | Metrics: `speed()`, `axis_conflict()`, the norm against the cap. Read-only. |
| SelfModel | `self_model.py` | I | Introspection from `snapshot()`, not "I feel". |

### 4.3 Physiology, sleep, learning

| Module | File | Mode | Contract |
|---|---|---|---|
| Neuromodulators | `neuromodulators.py` | R/W | The two-way link runs **through the Agent**, not through a cyclic import: DA↔valence/curiosity, 5HT↔stability/trust, NE↔arousal/stress, ACh↔curiosity and the analogue of focus (dominance). Neuromodulators do not duplicate the axes. |
| Wakefulness | `wakefulness.py` | R | It is already an argument of `step(wakefulness=)`. Process S does not come from A(t). High stress may accelerate `update_waking` (a coefficient, not a replacement of Process S). |
| Sleep | `sleep.py` | R/W | During sleep: `step(..., asleep=True, time_elapsed=<cycle dt>)` advances simulated sleep seconds per cycle (`SECONDS_PER_SLEEP_CYCLE` or `sleep_duration_seconds/cycles`), with `SLEEP_RECOVERY_SCALE` on clearance/recovery; external impulses are approximately 0. Replay may call `recall_trace`. Do not call MCP. See [specs/issue-54-affect-simulated-time.en.md](specs/issue-54-affect-simulated-time.en.md). |
| Temporal / TemporalChains | `temporal.py`, `temporal_chains.py` | R | Log a snapshot of A(t) into T0/T1 (today this is partly `affect_state`). |

### 4.4 Evolution, population, organism

| Module | File | Mode | Contract |
|---|---|---|---|
| Genome | `genome.py` | R | The genes `af_*` already exist — they map onto `axis_decay` / `lambda_reg` / `baseline_adapt_rate`. Adding genes for `decision_matrix` is **not** required in this delivery. |
| Epigenome | `epigenome.py` | R | A snapshot may include the `baseline` of A(t) as a slow drift (optional, and without breaking the format in the absence of a migration). |
| AgentFactory | `agent_factory.py` | R | It already applies the affective genes. Check that it does not write `affect_state` while bypassing the space. |
| Fitness | `fitness.py` | R | The affective-stability component: a low `axis_conflict`, a moderate stress, and no sticking at `norm_cap_max`. |
| Swarm | `swarm.py` | R/W | It already reads the axes in places — standardise on `snapshot()`. A social signal becomes an external impulse (attachment/trust), not a direct write. Fallback `step(inputs=…)` without `time_elapsed` still advances **1.0** simulated second (see issue #54 spec). |
| Ecology / Reproduction / Mortality | `ecology.py`, `reproduction.py`, `mortality.py` | R | Coupling of mortality and stress: a high sustained stress raises mortality pressure (if the layer can do that). Otherwise R without W. |
| PopulationObserver | `population_observer.py` | I | Aggregate the mean axes over the population. |
| AutonomousOrganism | `autonomous_organism.py` | R | Drives do not replace A(t). Energy and drives may emit internal impulses (arousal/stress under depletion). |
| SimulationUtility | `simulation_utility.py` | R | Utility may take `rank_weights` as a tie-breaker, not as a reward. |

### 4.5 The external circuit of the core versus the body

| Module | File | Mode | Contract |
|---|---|---|---|
| ExternalInteractionLayer | `external_interaction_layer.py` | W | Feedback.reward becomes an impulse through the same `outcome_impulse`. There is no parallel "emotion of the environment". For an MCP host the **body runtime is preferable**; EIL is a generic adapter. Do not grow a third path of learning. |
| GUI | `gui.py` | I | A panel of the 8 canonical axes, plus `decision_bias`, plus speed/conflict. The legacy 4 bars are an overlay of the projection. |
| Storage | `storage.py` | ∅/P | Persist `affective_space.to_dict()`. `affect_state` may be saved as a projection; a reload must not be allowed to overwrite the canon. |

---

## 5. Target architecture of the body: organs, not adapters

### 5.1 Metaphor

```
MCP server(s)          = the external world and the limbs
tools/list             = anatomy (which organs exist)
READ tools             = interoception and exteroception
WRITE tools            = muscles
WorldState             = the body schema / proprioception (the latest sensors)
AffectiveSpace         = how the body stands "toward this" (the canon)
Hippocampus + BG       = what to do with this body
SchemaBinder           = the spinal cord: assemble the posture of a muscle from the schema and proprioception
ApprovalGate           = an external prohibition (not part of the mind)
```

The mind **chooses an organ** (`tool_id`). The body **does not interpret a purchase**. If it cannot bind the schema, the muscle is unavailable on this tick (`wait_and_monitor`).

### 5.2 Pipeline (the replacement for MotorAdapter)

```
Host
  1. connect MCP servers from role YAML
  2. tools/list → MCPOrganRegistry.register_from_discovery(...)
  3. Agent.register_action_channel(tool_id) for every WRITE organ
     + synthetic wait_and_monitor
  4. poll READ organs → WorldState.update
  5. GenericEncoder.encode(world_state, last_results) → context_events
     + optional external EmotionalImpulse[]
  6. agent.step(context_events, decision_only=True) → chosen tool_id
  7. SchemaBinder.bind(capability, world_state, rank_weights, memory_hint)
       → params | None
  8. if None or wait_and_monitor → no WRITE, no store
  9. ProposedAction(tool_id, params, risk, affect_snapshot)
 10. ApprovalGate.route → mcp_executor (the only WRITE)
 11. GenericEncoder.encode_outcome(status, result)
       → tokens + EmotionalImpulse (via AffectiveSpace.outcome_impulse)
 12. hippocampus.store(path with ACTION=tool_id) + affective_space.step
 13. SleepScheduler as now (Process S + circadian)
```

The invariants B2–B9 as built are **kept**. B1 is replaced:

> **B1'** SchemaBinder, OrganRegistry, and the Encoder do not call `hippocampus.activate`, the selector, or `agent.step`. A read-only inspection of experiences for ranking is **permitted**, as the read-only hippocampus is permitted today in the procurement adapter, but without domain methods such as `_select_cheapest`.

### 5.3 What is deleted

| Delete or forbid | Replacement |
|---|---|
| `MotorAdapter` and the obligatory override of `_build_params` | `SchemaBinder` |
| `ProcurementBodyMotorAdapter` | a role is YAML + a seed + MCP servers |
| `MCPCapability.action_types` as a necessary index | `tool_id` is the action; leave the field deprecated and ignore it at runtime |
| `role.motor_adapter: python:Class` | absent |
| `role.event_classifier: python:fn` as obligatory | a generic encoder plus optional YAML rules |
| The parallel dictionary `place_order_*` | seed/ACTION = `mcp__...__create_purchase_order` |

`ProposedAction`, `ApprovalGate`, `HardConstraintViolation`, and `MCPToolRegistry` (the meaning is renamed to OrganRegistry; the file may stay) **remain**.

---

## 6. Universal components of the body

Target location: the package `src/mcp_body/` (the platform).  
In this delivery, `Demo/Virtual company/src/nowa_body/` may either (A) move into `src/mcp_body/` with a re-export, or (B) have its files replaced in place, leaving the package as a thin host. **Preference is A**, so that the core in `src/` is self-sufficient. The Demo is then: role YAML, MockMCP, the GUI, and the batch files.

The minimal set of new or rewritten modules:

```
src/mcp_body/
  mcp_capability.py      # as-is + action_types deprecated
  risk_classifier.py     # heuristic, as-is
  organ_registry.py      # MCPToolRegistry + working discovery
  mcp_client.py          # transport protocol (stdio/sse/mock)
  world_state.py         # NEW
  schema_binder.py       # NEW — replacement for MotorAdapter
  field_lexicon.py       # NEW — universal field names
  generic_encoder.py     # replacement for BusinessEventEncoder and the role classifier
  proposed_action.py     # ProposedAction dataclass (from motor_adapter.py)
  approval_gate.py
  hard_constraints.py
  feedback.py            # apply_feedback, status envelope
  runtime.py
  seeder.py              # ACTION = tool_id
```

### 6.1 MCP discovery (an obligatory implementation)

`register_from_mcp_discovery` is no longer a stub.

The client contract (minimal):

```python
class MCPTransport(Protocol):
    def list_tools(self) -> list[MCPToolDescriptor]: ...
    def call_tool(self, name: str, arguments: dict) -> dict: ...
```

`MCPToolDescriptor`:

```
name: str
description: str
input_schema: dict   # JSON Schema object
output_schema: dict  # optional
```

Registration:

```
tool_id = f"mcp__{server_id}__{sanitize(name)}"
risk = yaml_override | classify_risk_heuristic(name, description)
requires_approval = True if risk in {HIGH_WRITE, IRREVERSIBLE} else yaml_or_default
```

YAML **may** override risk, approval, and domain_tags; it **may not** specify a Python adapter.

Several servers on one agent are normal. A collision of `tool_id` is a configuration error.

A live 1C system (later) is one more `server_id` with `transport: stdio|sse` and the command or URL of the MCP server. The 1C tool catalogue arrives from `tools/list`, not from a hard-coded procurement list. If the 1C schema uses Russian field names, that is `field_aliases` in the role YAML, not new platform code.

### 6.2 WorldState (proprioception)

```python
class WorldState:
    """Last sensory snapshot. No domain types."""
    results: dict[str, dict]          # tool_id -> last result envelope
    entities: dict[str, list[dict]]   # collection_name -> rows
    scalars: dict[str, float]         # dotted or leaf numeric paths
    updated_at: dict[str, float]
```

Update after every READ:

1. Store the envelope (`status` plus the payload).
2. Recursively find **lists of objects** (list[dict] with id-like keys) and treat each as a collection. The collection name is the JSON key (`suppliers`, `items`, `orders`) or `{tool_leaf}_{key}`.
3. Scalars: every terminal number along a dotted path such as `stock.SKU1.qty`.
4. No procurement: there is no Supplier class.

### 6.3 Field lexicon (universal, not 1C)

`field_lexicon.py` holds tables of substrings (lowercase) mapped to a feature role:

| Role | Example substrings |
|---|---|
| `id` | `id`, `uuid`, `code`, `sku`, `number` (when it is not an amount) |
| `cost` | `price`, `cost`, `amount`, `budget`, `total`, `fee` |
| `time` | `lead`, `eta`, `delay`, `duration`, `days`, `hours`, `latency` |
| `reliability` | `reliab`, `rating`, `score`, `trust`, `success_rate`, `otd` |
| `quantity` | `qty`, `quantity`, `stock`, `count`, `volume`, `coverage` |
| `status` | `status`, `state`, `available`, `active` |

This is the **only** place where "name magic" lives. A new MCP with `unit_price` / `lead_time_days` works without role code. If a server names its fields `foo_bar`, an optional YAML alias is used:

```yaml
field_aliases:
  cost: ["cena", "stoimost"]
  id: ["ref_key"]
```

Aliases are merged into the lexicon **for the role**, not into Python.

### 6.4 SchemaBinder (the replacement for MotorAdapter)

Input: `MCPCapability`, `WorldState`, `rank_weights`, and an optional read-only `hippocampus`.  
Output: `dict | None`.

Algorithm:

1. Take `input_schema` (JSON Schema). If it is empty, the result is `{}` (a valid call with no arguments).
2. For each required property:
   - an **explicit binding** from the YAML `param_bindings` (a JSONPath into WorldState or the last result);
   - otherwise an **exact name** among the scalars or the top-level fields of the last payloads;
   - otherwise the **lexicon**: the property name is classified, and the best scalar of the same role is sought;
   - otherwise an **entity pick**: if the type is string or integer and collections exist, choose a row (see ranking) and take its id field;
   - otherwise the **schema default**;
   - otherwise the bind fails and the result is `None` (the muscle is unavailable).
3. Optional properties are filled when there is a confident match, and otherwise omitted.
4. An enum in the schema: choose the value by ranking (the enum strings are the candidates).
5. Never throw outward; errors become `None` (as `MotorAdapter.resolve` does).

**Candidate ranking** when there are several rows or enum values:

```
score(row) =
    - cost_aversion   * z(cost_field)
    - speed_seek      * z(time_field)     # less time is better under speed_seek
    + reliability     * z(reliability_field)
    + novelty_seek    * unseen_bonus(id)
    + memory_bonus    * past_reward(tool_id, id)   # read-only hippocampus
    + assertiveness   * z(quantity)       # with care: only if the role is quantity
```

`z` is the z-score inside the current candidate set. If a role has no field, the term is 0.  
`unseen_bonus` means the id has not occurred in the ACTION episodes of this `tool_id`.  
`memory_bonus` is the mean reward of episodes that carry this id token, clamped to [-1, 1].

**Forbidden** inside the binder: `if action_type == "urgent_reorder"`, `COVERAGE_DAYS = 30`, and role lists such as `_PRICE_KEYS`. Coverage and quantity: if the schema requires a quantity, take the quantity scalar as min(schema.minimum, the lexicon quantity); the heuristic "30 days of coverage" exists **only** as declarative YAML `param_bindings` / `computed_params`, not as Python.

Declarative computation (a narrow DSL, without eval):

```yaml
computed_params:
  quantity:
    op: max
    args: [10, {path: "stock.*.qty", reduce: min}]
```

If the DSL is not needed in the first iteration, **do not implement it**; quantity then comes only from the schema and the world. Do not carry a procurement formula into the core.

### 6.5 GenericEncoder

It replaces the obligatory `classify_procurement_events`.

READ produces tokens:

- `tool:<tool_id>`
- `server:<server_id>`
- `status:<status>`
- for each lexicon scalar: `field:<role>:<bucket>`, where bucket ∈ {low, mid, high, rising, falling} relative to the running statistics of WorldState
- `entity:<collection>:<id>` for selected or present ids (a cap of N=32)

An optional YAML overlay `affective_mapping` / `token_rules` (as events work today) is an **addition**, not a requirement.

READ produces impulses (weak, intensity ≤ 0.4):

- a failed `status` → `outcome_impulse("error")`
- a sharp rise in `cost` or a fall in `quantity` → stress rises, valence falls
- novelty of new keys → curiosity rises

Do not treat the role events `stock_critical_low` as the only path: they may remain a YAML overlay.

### 6.6 The status envelope and `outcome_impulse`

Keep the envelope as built: the executor always returns a `dict` with `status`.

Normalisation:

| status (normalized) | valence | stress | trust | arousal | curiosity |
|---|---|---|---|---|---|
| accepted, success, ok | +0.4 | −0.1 | +0.2 | +0.1 | 0 |
| rejected, failed, error | −0.4 | +0.4 | −0.2 | +0.3 | 0 |
| timeout, unknown | −0.1 | +0.2 | −0.1 | +0.2 | +0.2 |

The remaining axes are 0. Intensity is the magnitude (default 1, clamped to 0..1). The implementation is `AffectiveSpace.outcome_impulse`.

The ACTION label of feedback is **always** `action:<tool_id>`. The field `strategy` is no longer needed. The seed corpus migrates onto `tool_id`.

### 6.7 The synthetic organ `wait_and_monitor`

It is not an MCP tool. It is always among the BG channels. The binder is not called for it. There is no store (B8).

### 6.8 Role YAML (the target minimum)

```yaml
role_id: procurement
mcp_servers:
  - server_id: 1c_erp
    transport: mock | stdio | sse
    command: ...
    args: []
    url: ""
    enabled: true
    # optional per-tool overrides after discovery:
    tool_overrides:
      create_purchase_order:
        risk_level: medium_write
        requires_approval: true
        domain_tags: [procurement]
param_bindings: {}      # optional JSONPath
field_aliases: {}
affective_mapping: {}   # optional overlay
seed_corpus:
  - context_tokens: [field:quantity:low, domain:procurement]
    action: mcp__1c_erp__create_purchase_order
    consequence: stock_restored
    reward: 0.8
```

There is no `motor_adapter`. There is no obligatory `event_classifier`. There are no `action_types` on the tools.

A static list `mcp_capabilities` is **permitted as a fallback** (tests or a mock without a live list), but the runtime must be able to discover.

---

## 7. The link between the mind and the organs

### 7.1 BG channels are muscles

When the agent of a role is assembled:

```
for cap in registry.motor_capabilities():
    agent.register_action_channel(cap.tool_id)
agent.register_action_channel("wait_and_monitor")
```

Selector pressures are built from the tokens `action:<tool_id>` in the hippocampus. The seed is therefore **obliged** to use the same identifiers.

Do not register READ tools as muscles (otherwise the agent "acts" by polling). Polling belongs to the host and the runtime.

### 7.2 Per-channel affective modulation (the Agent)

In place of one `affect_modifier` on every action:

```
bias = affective_space.decision_bias()
w = affective_space.rank_weights()
for tool_id, pressure in pressures:
    cap = registry.get(tool_id)
    if cap is None: continue
    if cap.risk_level in HIGH/IRREVERSIBLE:
        pressure *= (1.0 - 0.5 * w.caution)
    if cap.risk_level == READ_ONLY:
        pass  # not a channel
    pressure *= (1.0 + 0.2 * w.novelty_seek * novelty(tool_id))
```

Implement this in `Agent._compute_affective_space_modifier` **or** beside it, in `_modulate_pressures_for_organs`. Not in SchemaBinder.

### 7.3 When the parameters could not be assembled

If a WRITE was chosen but `bind` returns None, treat the tick as a no-op (the equivalent of wait). Do **not** substitute an empty dict when schema.required is non-empty. A slight internal impulse of curiosity is permitted (the agent could not act — an incompleteness), with intensity ≤ 0.15.

### 7.4 Approval and affect

`ProposedAction.affective_context = affective_space.snapshot()["axes"]` (as today). The person in the UI sees A(t). A(t) does **not** auto-approve.

---

## 8. Changes to the core `src/` (the obligatory checklist)

1. `affective_space.py` — `outcome_impulse`, `rank_weights`.
2. `agent.py` — per-channel modulation; derive impulses without double counting; BG aversive from stress plus caution; hippocampal recall becomes memory impulses; project the legacy form after the step.
3. `selector.py` — accept an `affect_bias` dict; do not break the old tests (the scalar fallback remains).
4. `basal_ganglia.py` — optional float gains from the caller (aversive already exists); document the meaning.
5. `hippocampus.py` — a store/activate contract for EmotionalTrace (if it is absent, do it through the Agent; it is not obligatory to drag an import of the space into the hippocampus: Agent glue is acceptable).
6. `value_layer.py` / `prediction_layer.py` — emit impulses outward (return a dict); the Agent applies them.
7. `emotional_regulation.py` — remove the dual source of truth.
8. `semantic_emotions.py` — the canonical axes.
9. `sleep.py` — background and wakefulness enter the step during the cycle.
10. `storage.py` — the canon is not overwritten by the projection.
11. `gui.py` — 8 axes plus the bias.
12. `intent_memory.py`, `self_model.py`, `affective_persistence.py` — read a snapshot of A(t).
13. Tests: extend `tests/test_affective_space*.py` and the agent integration, plus a new `tests/test_mcp_body_schema_binder.py` (if the package lives in src).

Do not inflate `Agent.step` with domain procurement.

---

## 9. Migration of the Demo procurement role

1. Implement discovery on MockMCP (`list_tools` from the mock catalogue).
2. Rewrite the seed: `action: mcp__1c__create_purchase_order` (keep the current as-built style of `tool_id`, `mcp__1c__...`, if the mock names it that way — a **single** `server_id`).
3. Remove the use of `ProcurementBodyMotorAdapter` from the runtime and the configurator.
4. Configurator GUI: remove the obligatory motor class; Discover tools is a real list (the mock).
5. The old tests `test_motor_adapter.py` / `test_procurement_motor_adapter.py`: replace them with SchemaBinder plus ranking (a cheap supplier versus a reliable one arises from A(t) and the lexicon, not from `action_type`).
6. Regression: the same MockMCP scenario "critical stock → create an order" must pass without procurement Python.

The behavioural equivalent of the strategies:

| What it was (action_type) | What it becomes |
|---|---|
| place_order_cheap_supplier | the same tool; a high `cost_aversion` selects the row with the minimum price |
| place_order_reliable_supplier | a high `reliability` weight |
| urgent_reorder | a high `speed_seek` plus stress → the minimum lead time; the quantity comes from the scalars |
| diversify_supplier | a high `novelty_seek` → an unseen id |
| wait_and_monitor | the same synthetic channel |

The character of a role is set by the genome, by A(t), and by the seed, not by four Python branches.

---

## 10. Tests (obligatory)

The core:

- `outcome_impulse` maps a status onto axes in [-1, 1]
- monotonicity of `rank_weights`: stress rising implies caution rising; curiosity rising implies `novelty_seek` rising
- regulation no longer diverges from `axes` after N steps (one source)
- semantic emotions respond to the canonical valence/stress
- save and load preserve the new methods without breaking the old keys
- the selector's scalar fallback still works

The body:

- discovery: 4 mock tools → 3 sensory channels and 1 motor channel on the agent
- the binder: a schema `{supplier_id, sku, qty}` plus a world of suppliers and stock → a complete set of params
- the binder: no collection → None
- ranking: two suppliers, price and reliability; a high cost_aversion → the cheap id
- there is no import of MotorAdapter on the happy path of the runtime
- approval under B5–B6 is not broken
- a seed with `action: mcp__...` produces a non-zero pressure on that channel
- a second fictitious MCP (sending email) is registered by the same code, with no new adapter class

Forbidden: a test that requires `ProcurementBodyMotorAdapter`.

---

## 11. Order of work for the implementing agent

**Stage 0.** Freeze the as-built tests, and list those that fail after the motor is removed.

**Stage 1. Canonical coverage of the core** (`src/`): `outcome_impulse` and `rank_weights`; the contracts of CER, semantics, the selector, the BG, sleep, persistence, and the GUI in §4. Do not touch the Demo until the core is green.

**Stage 2. WorldState, SchemaBinder, and discovery** in `src/mcp_body` (or nowa_body). Unit tests, without the GUI.

**Stage 3.** A runtime without MotorAdapter; MockMCP; migration of the procurement YAML and seed.

**Stage 4.** The configurator GUI, and deletion of the dead code of motor_adapter and of the role's motor import.

**Stage 5.** As-built documentation: a short addendum stating that the Phase 1 MotorAdapter is superseded by this specification.

Each stage is a separate commit, and only at the user's request; do not commit without a request.

---

## 12. Explicitly out of scope, and prohibitions

This is not "we will do it differently later". These things are **not to be done at all** in this delivery or in later deliveries of the body and of affect:

| Topic | Why it surfaces in the specification at all | Rule |
|---|---|---|
| New axes of A(t) (`urgent`, `budget`, …) | An implementer may decide that "urgency has nowhere to go" and add an axis | Forbidden. Urgency is the dynamics of axes that already exist, plus ranking. Budget is WorldState and `cost`. |
| An LLM, or an LLM agent, for `params` | A frequent false path: "the schema is complicated — let the model fill in the JSON" | Forbidden. It breaks determinism, sovereignty, and universality: every new tool again depends on a prompt. The binder covers any MCP precisely because it does not generate; it **binds**. |
| Auto-approval of HIGH/IRREVERSIBLE | Stress or urgency may tempt one to bypass the gate | Forbidden. |
| Learning while awake, outside feedback-after-outcome | As the body works today | Do not extend it. |
| Rewriting `nowa_sandbox` | A neighbouring circuit | Do not touch it; the isolation is preserved. |

**Not out of scope — a deferred transport:** a real 1C MCP. We do **not** implement it in this delivery (Mock plus the `MCPTransport` protocol is enough), but the contract must accept it without changes to the core. The criterion: replacing Mock by a 1C MCP is a change of the YAML `mcp_servers` (plus aliases if they are needed), not a new package `nowa_roles.procurement.one_c_adapter`.

---

## 13. Criterion of completion

The platform is covered, and the body is universal, if:

1. In `src/` there is no module from §4 whose status is X.
2. A new MCP server (including a future 1C) is connected by YAML transport plus discovery, with **zero** new Python classes of muscle and **zero** new axes of A(t).
3. `grep MotorAdapter` on the runtime path finds only a deprecated shim (if one is needed for a single release) or nothing.
4. Procurement on MockMCP works through the ranking of A(t) and the schema. The same binder must be sufficient for the 1C tools when they appear.
5. The canon A(t) is the only write-target of affect; `affect_state` coincides with the projection after every step.
6. The bind/execute pipeline contains no calls to an LLM.

---

## 14. A note to the implementer on file names

On Windows, the paths `affective_space.py` and historical names may coincide in case. The landmark is this: the canon module is the one in which `AXES`, `AffectiveSpace`, and `decision_bias` are declared. The Demo body package today is `nowa_body` (`mcp_capability.py`, `motor_adapter.py`, `tool_registry.py`, `runtime.py`). Do not grow a parallel `MotorAdapter` under a new name — delete the concept; do not rename the class.
