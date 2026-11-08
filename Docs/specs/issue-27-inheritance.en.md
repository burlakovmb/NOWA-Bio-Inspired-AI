# Issue #27 — Mendelian colony inheritance: implementation spec

Closes #27. PR #64. Related: [issue-24-silent-failures.en.md](issue-24-silent-failures.en.md) (conception snapshot at birth). Implementation commits: `ba77db9`, `71c872d`.

Russian: [issue-27-inheritance.ru.md](issue-27-inheritance.ru.md)

Scope: **Colony chinchillas** demo (`Demo/Colony chinchillas/`). Repo **swarm** default crossover stays `arithmetic` (`src/swarm.py`); only chinchilla birth uses `uniform`.

---

## 1. Problem

Prior `_inherit_nowa_from` mixed Mendelian genome crossover with blended phenotypic inheritance:

| Symptom | Cause |
| --- | --- |
| Siblings nearly identical; population variance collapses over generations | `GenomeVector.crossover(..., alpha=0.5, mode="arithmetic")` averaged parental alleles → child at parental midpoint before mutation. |
| Parent acute stress passed to kits | Current neuromodulator levels (e.g. cortisol) were averaged from parents with noise. |
| `axis_decay` / `social_drive` inheritance ineffective | Values were averaged then overwritten by `AgentFactory._apply_genome_to_agent` from the recombined genome (`af_decay_*`, `dr_social_drive_baseline`). |
| Energy not allelic | `inherit_scalar` averaged parents’ **current** energy balances. |

---

## 2. Solution and biological rationale

**Decision (owner-aligned):** Maximise biological plausibility in colony reproduction — genotype from Mendelian whole-gene inheritance; neonatal physiology from genome defaults and constructor baselines, not parental momentary state.

| Mechanism | Behaviour |
| --- | --- |
| **Genome crossover** | `mode="uniform"`: each gene copied **whole** from mother or father (`random() >= 0.5` rule in `GenomeVector.crossover`), then `mutate(rate=0.05)` unchanged. |
| **Neuromodulators** | Not inherited; kit keeps constructor baselines (e.g. `NeuromodulatorState.BASELINE_CORT` ≈ `0.05`). |
| **`axis_decay`, `social_drive`** | Set only via genome → `AgentFactory._apply_genome_to_agent`; dead averaging loops removed. |
| **Energy** | Constant `NEWBORN_ENERGY = 1.0` (rested neonatal start; metabolic state ≠ allele). |
| **No genome path** | Unchanged: warning log, `genome is None`, fresh baselines (`issue #24`). |

Swarm evolution in `src/swarm.py` remains **arithmetic** by default; colony birth is **uniform** only.

---

## 3. File changes

| File | Change |
| --- | --- |
| `Demo/Colony chinchillas/src/colony_agent.py` | `NEWBORN_ENERGY`; `_inherit_nowa_from` uniform crossover, `pre_genes` for meta, removed NM/affect/social/energy averaging; `genome_inheritance_meta` updated; `self.energy = NEWBORN_ENERGY` after inheritance. |
| `Demo/Colony chinchillas/src/colony_reproduction_helpers.py` | Removed `inherit_scalar`. |
| `.github/workflows/tests.yml` | `push` only on `main`; `concurrency` group `tests-${{ github.ref }}`, `cancel-in-progress: true` (cancels superseded runs on the same ref). Duplicate branch push + PR runs are avoided by `push.branches: [main]`, not by sharing a concurrency group. |
| `Demo/Colony chinchillas/tests/test_issue27_inheritance.py` | New acceptance suite for #27. |
| `Demo/Colony chinchillas/tests/test_issue24_silent_failures.py` | Expectations under uniform crossover (pin RNG to father alleles). |
| `Demo/Colony chinchillas/tests/test_nowa_agent.py` | `test_tc07_*`: newborn does **not** copy parent NM levels. |

---

## 4. `genome_inheritance_meta` fields

| Field | Note |
| --- | --- |
| `crossover_mode` | `"uniform"` (was `"arithmetic"`). |
| `crossover_alpha` | **Removed** (unused by readers). |
| `mother_contrib_mean` / `father_contrib_mean` | Fraction of heterozygous loci where child allele matched mother vs father **before mutation** (`pre_genes` vs parental genes). |
| `top_shifted_genes[].midpoint_shift` | `child_val − (m_val + f_val)/2`; still useful but now often highlights loci where parents **differed** (child is an endpoint, not a blend). |

Other keys (`mode`, `mutation_rate`, `gene_count`, lineage, parent ids/names) unchanged.

---

## 5. Compatibility

| Area | Impact |
| --- | --- |
| Saves / loads | As of #65 ([issue-65-save-genome.en.md](issue-65-save-genome.en.md)), `ColonyStorage` persists and restores `genome_inheritance_meta` (post-#27 births: `crossover_mode` is `"uniform"`, no `crossover_alpha`). Saves written before #65 omit that key; load yields `{}`. A save file may still contain legacy `crossover_alpha` in meta if the agent was born before #27 and saved after #65. |
| Conception snapshot (#24) | Still used for paternal genome when father died; crossover mode change only affects recombination, not snapshot capture. |
| Core `src/` | Unchanged. Swarm `crossover_mode` default remains `arithmetic`. |
| API | `_inherit_from` alias unchanged; `inherit_scalar` removed from helpers (colony-only). |

---

## 6. Tests and acceptance criteria

**Primary:** `Demo/Colony chinchillas/tests/test_issue27_inheritance.py`

- Siblings differ; each gene (pre-mutation) equals mother **or** father allele; meta `crossover_mode == "uniform"`, no `crossover_alpha`.
- Simulated breeding: uniform variance does not collapse like arithmetic (`uniform > arithmetic × 5` over 8 generations).
- High maternal cortisol / parent energy / parent `social_drive` not copied; child energy `1.0`; `social_drive` and `axis_decay["stress"]` match genome genes.
- Birth without genome: warning retained, baselines + `NEWBORN_ENERGY`.

**Updated:** `test_issue24_silent_failures.py`, `test_nowa_agent.py` (see §3).

**CI:** workflow passes on PR #64 (pytest job).

**Acceptance criteria:**

1. Colony birth uses `uniform` crossover + `rate=0.05` mutation.
2. Neonatal neuromodulator levels are baselines, not parental averages.
3. `social_drive` and affective `axis_decay` come from genome application only.
4. Newborn `energy == NEWBORN_ENERGY` (`1.0`).
5. Population genetic variance under uniform breeding remains materially above arithmetic-averaging collapse (regression test).
6. Genome-less birth path still logs warning and does not fail silently.
