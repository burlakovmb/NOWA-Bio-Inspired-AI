# Issues #16 / #31: safe agent-state persistence

Russian: [issue-16-31-safe-agent-state.ru.md](issue-16-31-safe-agent-state.ru.md)

## Summary

Agent save and load no longer use Python `pickle`. State is written as UTF-8 JSON with a named format and integer schema version. A closed codec (`src/state_codec.py`) serialises a fixed set of core types and plain containers; nothing in a file is imported or executed. Bytes that look like pickle are rejected before parsing.

**There is no migration.** Legacy `.pkl` agent saves and old sandbox pickle checkpoints cannot be loaded. Recreate checkpoints from a fresh run or an in-app save.

## Envelope (all persisted documents)

Every file is a single JSON object:

| Field | Meaning |
|---|---|
| `format` | Logical format id (string) |
| `schema_version` | Integer version this build accepts for that format |
| `state` | Payload tree produced by `encode_tree` |

Read path: `load_state` → decode tree. Write path: `encode_tree` → `dump_state` (write temp file in the target directory, `fsync`, `os.replace`).

Errors raise `StateFormatError` (`src/state_codec.py`). Sandbox and employee wrappers map that to `CheckpointError`.

### Agent mind document

| Property | Value |
|---|---|
| Format id | `nowa-agent-state` (`AGENT_STATE_FORMAT`) |
| Schema version | `1` (`AGENT_STATE_SCHEMA_VERSION`) |
| Typical extension | `.nowa` |
| Entry points | `read_agent_state`, `write_agent_state`, `AgentStorage.save_agent` / `load_agent` (`src/storage.py`) |

Default filename pattern: `agent_save_YYYYMMDD_HHMMSS.nowa`.

### Sandbox training checkpoint

| Property | Value |
|---|---|
| Metadata format id | `nowa-sandbox-checkpoint` (`CHECKPOINT_FORMAT`) |
| Metadata schema version | `2` (`CHECKPOINT_VERSION`) |
| Typical paths | `something.ckpt` plus sibling `something.ckpt.agent.nowa` |
| Module | `Demo/Virtual company/src/nowa_sandbox/sandbox_checkpoint.py` |

The `.ckpt` file holds quarter history, graduation flags, RNG state, `GenomeVector.to_dict()` output, and a pointer to the agent sidecar. The sidecar uses the same `nowa-agent-state` schema as core storage (optionally extended; see below).

### Employee mind checkpoint

| Property | Value |
|---|---|
| Filename | `mind.nowa` under `nowa_employees/<agent_id>/` |
| Atomic temp | `mind.nowa.tmp` |
| Module | `Demo/Virtual company/src/nowa_body/employee_checkpoint.py` |

## Codec allow-list

Registered types (`state_codec._ensure_registry`):

- `Experience`, `Path`, `Event`, `EventType` (`src/experience.py`)
- `EmotionalTrace` (`src/affective_space.py`)
- `SignatureTrace` (`src/hippocampus.py`)
- `CorticalPattern` (`src/sleep.py`)

Containers: `dict`, `list`, `tuple`, `set`, `frozenset`, `collections.deque`, and JSON scalars. Shared object identity is preserved via `__nowa_type__: ref` tags.

Types outside this set cannot be serialised; `encode_tree` raises `StateFormatError`.

## What `AgentStorage` persists

The `state` mapping is built in `AgentStorage.save_agent` and restored in `load_agent`. Highlights for issues #16 / #31:

### Hippocampus (episodes + decision store)

- `hippocampus_experiences`, `hippocampus_episode_seq`, `cortex_patterns`, selector fields.
- When `NOWAHippocampus.export_persistent_state` exists, `hippocampus_decision` includes:
  - `signatures` (with `last_decay_ts`, `context_tokens`, `context_vector`, `timestamp`, link to experience via `source_experience`)
  - `recent_event_window`, `novelty_history`
  - `_feature_bits` / `_token_bits` as `feature_bits` / `token_bits`
  - `_nov_ids` / `_nov_valid` as `nov_ids` / `nov_valid`

On load, if `hippocampus_decision` is present, `import_persistent_state` relinks signatures by position and **does not rebuild** them, so decay anchors and novelty caches are not recomputed. Repeated save/load therefore does not apply hippocampal decay twice (`tests/test_safe_agent_state.py`).

If `hippocampus_decision` is absent (very old logical saves), signatures are cleared and novelty validity is reset.

### Cognitive layers passed by hosts

- Full `conflict_arbitration` via `ConflictArbitration.to_dict()` when the object is passed (GUI and tests pass `agent.conflict_arbitration`).
- `intent_memory` via `IntentMemory.to_dict()` when passed.
- `neuromodulators`, `value_layer`, `sleep_manager` (including chain memory), affective subsystems when provided.
- With `agent=`: `labile_layer`, `plasticity_config`, `host_clock_s`, `bg_outcome_slots`, `bg_action_channels`, lifetime/runtime/wakefulness/autonomous snapshots.

After load, `_bind_restored_two_tier` reconnects sleep managers to restored `labile` and `plasticity` on the agent.

### Demo-specific extensions (same `.nowa` file)

| Key | Writer | When |
|---|---|---|
| `sandbox_intent_memory` | `sandbox_checkpoint._save_intent_memory_extension` | Sandbox checkpoint agent sidecar |
| `vc_intent_memory` | `employee_checkpoint.save_mind` | Employee stop checkpoint |

Core `load_agent` ignores unknown keys; demo loaders apply extensions after base restore.

## Rejection rules (no fallback)

| Input | Result |
|---|---|
| Pickle magic / legacy pickle bytes | `StateFormatError`: old pickle saves are not supported |
| Non-JSON or wrong `format` | `StateFormatError` |
| `schema_version` not in the build allow-list | `StateFormatError` |
| Sandbox metadata not `nowa-sandbox-checkpoint` v2 | `CheckpointError` |
| Corrupt or untyped tree | `StateFormatError` on decode |

`AgentStorage.get_save_files` may still list `.pkl` in the save directory for cleanup visibility; `load_agent` will not open them.

## Consumers

| Consumer | Path | Notes |
|---|---|---|
| Core GUI | `src/gui.py` | Saves/loads via `AgentStorage`; passes `conflict_arbitration`, `intent_memory`, `neuromodulators`, full `agent=` |
| Tamagochi host | `Demo/Tamagochi Chinchilla/src/main.py` | Session file `agent_save.nowa`; cage as `agent=` |
| VC sandbox CLI | `nowa_sandbox/run_sandbox.py` | `--checkpoint` / `--resume-from` on `.ckpt` + sidecar |
| VC sandbox GUI | `nowa_sandbox/gui_app` | Checkpoint resume uses same format |
| VC employee host | `nowa_body/employee_checkpoint.py` | `mind.nowa` on stop |
| Tests / tooling | `tests/test_safe_agent_state.py`, storage tests | `.nowa` round-trips |

## Limitations (not in the file)

1. **Hippocampus constructor hyperparameters** (for example `max_experiences`, decay constants configured at construct time) are not written. Load keeps the live hippocampus object’s parameters; only episodes and `hippocampus_decision` restore recall/novelty behaviour.
2. **Epigenome** is not part of sandbox checkpoints (genome dict only). Employee mind files follow `AgentStorage` and do not add epigenome either.
3. **Procurement world state** is intentionally not saved in sandbox checkpoints; resume creates a fresh world per spec.

## Related documents

- [two-tier-plasticity.en.md](../architecture/two-tier-plasticity.en.md) — labile/stable contract and `plasticity_config` in saves
- [issue-58-sandbox-two-tier-plasticity.en.md](issue-58-sandbox-two-tier-plasticity.en.md) — sandbox sleep/`dt` and checkpoint extensions
- [API.en.md](../API.en.md) — `AgentStorage` field inventory