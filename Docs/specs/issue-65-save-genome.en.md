# Issue #65 — Colony save/load: re-apply genome and persist lineage meta

Closes #65. PR #66. Related: [issue-27-inheritance.en.md](issue-27-inheritance.en.md) (`genome_inheritance_meta`), [issue-24-silent-failures.en.md](issue-24-silent-failures.en.md) (genome and conception fields on save).

Russian: [issue-65-save-genome.ru.md](issue-65-save-genome.ru.md)

Scope: **Colony chinchillas** (`Demo/Colony chinchillas/`), `ColonyStorage` in `colony_storage.py`.

---

## 1. Problem

After issue #24, colony JSON stored each agent’s `genome`, but load did not run `AgentFactory._apply_genome_to_agent`. Phenotype derived from genes (`axis_decay`, drive thresholds, neuromodulator decay half-life, etc.) fell back to constructor defaults while the `GenomeVector` on disk stayed correct. Birth lineage metadata (`genome_inheritance_meta`) was not written to or read from saves.

---

## 2. Solution

On deserialize, restore runtime and affect, assign `agent.genome`, recompute `max_lifespan_age_s`, then **`_apply_saved_genome`**: call `_apply_genome_to_agent` with `genome.to_agent_params()`, and put back momentary **energy**, **social_drive**, and **neuromodulator** concentrations saved in the file.

Serialize two additions per agent:

| Field | Location | Content |
| --- | --- | --- |
| `genome_inheritance_meta` | top-level agent object | JSON copy of `agent.genome_inheritance_meta` (empty dict if absent). |
| `neuromodulator_levels` | `runtime` | `dopamine`, `norepinephrine`, `serotonin`, `cortisol`, `acetylcholine` when present on `agent.neuromodulators`. |

Restore order in `_restore_saved_agent`: runtime (including `neuromodulator_levels` when key present) → affect → genome + lifespan → `_apply_saved_genome` → `genome_inheritance_meta` if key present.

`SCHEMA_VERSION` remains `1`; new keys are optional on read.

---

## 3. File changes

| File | Change |
| --- | --- |
| `Demo/Colony chinchillas/src/colony_storage.py` | Serialize `genome_inheritance_meta`, `runtime.neuromodulator_levels`; `_apply_saved_genome`, NM restore helpers; load path calls `_apply_saved_genome` before restoring meta. |
| `Demo/Colony chinchillas/tests/test_storage.py` | Round-trip temperament/lineage; legacy saves without new keys; agent without `genome`. |

---

## 4. Backward compatibility

| Save shape | Load behaviour |
| --- | --- |
| Current save with genome + new fields | Genome re-applied; energy, `social_drive`, NM levels, and `genome_inheritance_meta` match pre-save values (see `test_storage_roundtrip_keeps_genome_temperament_and_lineage`). |
| Save with `genome` but without `genome_inheritance_meta` / `neuromodulator_levels` | Genome re-applied; `genome_inheritance_meta == {}`; energy and `social_drive` preserved (`test_storage_old_save_without_new_fields_reapplies_genome`). |
| Save without `genome` key | `genome is None`; default colony lifespan; default `axis_decay` (`test_storage_old_save_without_genome_loads`). |

---

## 5. Known limitations

| Topic | Behaviour |
| --- | --- |
| **`affective_space.axes["curiosity"]`** | Not stored as its own field. `affect.boredom` is saved; on load `curiosity` is set to `1.0 − boredom`, not the pre-save curiosity axis if it diverged from that identity. |
| **Current `exploration` / `curiosity` drive levels** | Only **energy** and **social_drive** are snapshotted and restored after `_apply_genome_to_agent`. Autonomous drive integrators (`exploration`, `curiosity`, etc.) are rebuilt from genome baselines during apply, not from saved momentary drive state. |

Neuromodulator levels *are* persisted via `runtime.neuromodulator_levels` and restored after genome apply.

---

## 6. Tests and acceptance

**Primary:** `Demo/Colony chinchillas/tests/test_storage.py`

- `test_storage_roundtrip_keeps_genome_temperament_and_lineage` — `axis_decay`, `lambda_reg`, NM half-life, social threshold, energy, NM concentrations, meta (`crossover_mode == "uniform"`, no requirement on `crossover_alpha`).
- `test_storage_old_save_without_new_fields_reapplies_genome` — legacy JSON strips new keys; genome phenotype still applied.
- `test_storage_old_save_without_genome_loads` — missing genome unchanged from #24 semantics.

**Acceptance criteria:**

1. Load re-applies saved genome through `_apply_genome_to_agent`.
2. After apply, saved energy, `social_drive`, and neuromodulator levels match the file.
3. `genome_inheritance_meta` round-trips when present.
4. Saves without the new keys still load without error.
