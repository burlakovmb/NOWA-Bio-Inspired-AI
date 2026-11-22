# Issue #87 — `save_agent` / `load_agent` take every component from `agent=`

Russian: [issue-87-save-agent-components.ru.md](issue-87-save-agent-components.ru.md)

Branch `fix/issue-87-save-agent-components`. Baseline: `89c10a0` (main).

Code: `src/storage.py`. Test: `tests/test_issue_87_save_agent_components.py`.

---

## 1. Problem

`AgentStorage.save_agent(..., agent=a)` and `load_agent(..., agent=a)` took only `value_layer`, `conflict_arbitration` and `intent_memory` from `agent=`. Every other optional component was saved and restored only when the caller passed it by name. A host that called the short form lost data without an error:

- `temporal_chains` of `learning_guard.stable_payload` — the chains live in the sleep manager, and `sleep_manager` was not taken from `agent=`;
- `slow_affect` of `stable_payload`;
- nine affect components: `neuromodulators`, `affective_persistence`, `affective_background`, `affective_space`, `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation`, `stability_monitor`.

Measured on `89c10a0` with the test's agent (300 decisions, 2 sleeps, 483 temporal chains): the `agent=` round trip differs in 2 of the 8 `stable_payload` sections and in all 9 affect components.

Two defects of the same restore path showed up on the explicit form as well:

- **Neuromodulators lose their shared object.** `Agent.__init__` gives the agent and its sleep manager one `NeuromodulatorState`. `load_agent` restored that object in place and then replaced `sleep_manager.neuromodulators` with a fresh copy. After a load, sleep wrote its dopamine delta (`SleepManager`, sleep-time dopamine) into the copy, and the waking agent never saw it.
- **The stability baseline warm-up restarts.** The restore list for `emotional_stability` did not include `_background_baseline_buffer` and `baseline_warmup_samples`. While `baseline_background` is still `None`, the monitor collects that buffer and sets the baseline from its median. After a load the buffer was empty and the warm-up started again.

---

## 2. Solution

### 2.1 Components from `agent=`

New module helper `_agent_component(agent, explicit, attribute)`: returns the explicit argument when it is not `None`, otherwise `getattr(agent, attribute, None)`. `save_agent` and `load_agent` call it at the top for every optional component:

| Argument | `Agent` attribute |
| --- | --- |
| `affect_state`, `temporal`, `sleep_manager`, `neuromodulators` | same name |
| `affective_persistence`, `affective_background`, `affective_space` | same name |
| `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation` | same name |
| `emotional_stability` | `stability_monitor` (as `src/gui.py` passes it) |
| `value_layer`, `conflict_arbitration`, `intent_memory` | same name (unchanged behaviour) |

An explicitly passed argument still wins. Without `agent=` nothing changes. Every component is restored in place (attributes copied from `from_dict`), so taking the agent's own objects is safe: no local name is rebound.

### 2.2 Shared neuromodulators

In `load_agent`, `sleep_manager.neuromodulators` is replaced only when it is not the object already restored as `neuromodulators`. A sleep manager with its own separate object keeps the old behaviour.

### 2.3 Stability monitor warm-up

`baseline_warmup_samples` and `_background_baseline_buffer` are added to the attributes copied from the restored `StabilityMonitoringLayer`. `from_dict` already reads both; only the copy list missed them.

### 2.4 What stays as is

- `affect_state` is reprojected from `affective_space` on load (`# Canon wins` block and `Agent._project_legacy_affect_from_affective_space(blend=1.0)`). It is fast state outside `stable_payload`. The test compares it with the explicit load, not with the source agent.
- `emotional_regulation.last_inputs` (`_last_reward_signal`, `_last_prediction_error`, `_last_policy_entropy`, `last_time_delta`) are the inputs of the last regulation call. They are written every step and read by nothing, and `from_dict` does not restore them. The test leaves them out of the comparison.

### 2.5 Callers

- `src/gui.py` and the Tamagochi demo pass every component explicitly: no change. `ChinchillaAgent` has no `affect_state`, so `agent=self` adds nothing there.
- Virtual company (`employee_checkpoint.py`, `sandbox_checkpoint.py`) passes a subset plus `agent=`. Its saves now also carry `temporal` (employee checkpoint), `affective_persistence`, `affective_background`, `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation` and `emotional_stability`, and its loads restore them. The file schema is unchanged; old files load as before.

---

## 3. Invariants and tests

`tests/test_issue_87_save_agent_components.py`, one trained agent per module (300 decisions at `dt = 1.5`, a sleep after decisions 150 and 300):

| Invariant | Test |
| --- | --- |
| Training fills `temporal_chains` and `slow_affect` (the check is not vacuous) | `test_training_fills_the_sections_the_short_form_used_to_drop` |
| The `agent=` save writes every component key, equal to the explicit save | `test_agent_only_save_writes_what_the_explicit_save_writes` |
| All 8 `stable_payload` sections match the source after an `agent=` round trip | `test_agent_only_round_trip_keeps_all_stable_sections` |
| The 9 affect components match the source | `test_agent_only_round_trip_keeps_affect_components` |
| An `agent=` load equals an explicit load, `affect_state` included | `test_agent_only_load_matches_explicit_load` |
| `sleep_manager.neuromodulators is agent.neuromodulators` after both loads | `test_load_keeps_sleep_manager_neuromodulators_shared` |
| An explicit argument wins on save and on load; the agent's own component stays untouched | `test_explicit_component_wins_over_agent` |

On the baseline `storage.py` five of the seven tests fail; the two that pass are the training precondition and explicit-wins.

Run:

```bash
python -m pytest -q tests/test_issue_87_save_agent_components.py
python -m pytest -q tests
```

---

## 4. QA

Report: [issue-87-save-agent-components.en.md](../qa/issue-87-save-agent-components.en.md).

---

## 5. Design principle

Storage API only. No learning rule, gene or constant changed; the file schema and its version are unchanged.
