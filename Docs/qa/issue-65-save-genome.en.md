# QA issue #65 — colony save/load keeps genome temperament and lineage

Branch: `team/issue-65-save-genome`. Reviewed code `fac946f`. Spec on top: `6ee14ba`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/66
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/65
Baseline: `origin/main` @ `6055c6a` (merge of #64). Storage on that commit is the pre-fix save format.
Russian: [issue-65-save-genome.ru.md](issue-65-save-genome.ru.md).
Spec: [issue-65-save-genome.en.md](../specs/issue-65-save-genome.en.md).

Product code was not changed by this QA pass. No new PR. Full `pytest` was not run locally.

Machine: Python 3.12.3, pygame 2.6.1, pytest 9.2.0. The probe and the targeted pytest set `NOWA_STRICT_LEARNING=1`. `SDL_VIDEODRIVER=dummy`.

## Verdict

**PASS** (`fac946f`).

Load assigns the saved genome after `ChinchillaAgent` is constructed, then `_apply_saved_genome` runs `AgentFactory._apply_genome_to_agent` and writes back momentary energy, `social_drive`, and the five neuromodulator levels. `axis_decay["stress"]` on a real offspring came back as the gene `0.860535`, not the constructor default `0.75`. `genome_inheritance_meta` round-trips, including a legacy `crossover_alpha`. The offspring stays `mode == "recombined"`. The mother stays `mode == "founder"`. A file written by `origin/main`'s `ColonyStorage` (no new keys) loads, reapplies the genome, keeps energy and `social_drive`, and leaves meta `{}` instead of stamping founder. `SCHEMA_VERSION` stays `1`. `git diff origin/main...fac946f -- src` is empty.

CI pytest on the code commit `fac946f` passed (run [42484846043](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/42484846043), 14m36s). `gh pr checks 66` at review time was still `pending` on the docs commit `6ee14ba` (run [42486161645](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/42486161645)). That run was not watched.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | Diff logic: reapply genome, then put back energy, `social_drive`, neuromodulator levels; meta restored; offspring does not become a founder | Pass. See below |
| 2 | `tests/test_storage.py` and `tests/test_issue27_inheritance.py` | **11 passed**, 0.33 s, exit 0 |
| 3 | One real birth (`_start_pregnancy` → `_give_birth`), save → load | Pass. Phenotype, lived energy / social / NM / affect curiosity, and meta match. Mother remains founder |
| 4 | Same colony saved by `origin/main` `ColonyStorage` (`6055c6a`) and loaded by the fix | Pass. No new keys in the file. Stress axis `0.860535`. Meta `{}`. The pre-fix loader of that same file still leaves stress at `0.75` |
| 5 | Curiosity / exploration drives after 60 simulated seconds | Known limitation, not a FAIL. See below |

Not run:

| # | Scenario | Why |
| --- | --- | --- |
| 1 | Full `python3 -m pytest -q` | CI pytest on `fac946f` |
| 2 | Multi-generation or multi-seed runs | Out of scope for this pass. One litter, one seed |
| 3 | Interactive colony GUI | Inspector draw list was read. No display session |

## What the diff does

`_restore_saved_agent` restores runtime (energy, `social_drive`, and `neuromodulator_levels` when that key exists) and affect, then assigns `agent.genome` and lifespan, then calls `_apply_saved_genome`. That helper reads `genome.to_agent_params()`, snapshots energy, `social_drive`, and the five concentrations, calls `_apply_genome_to_agent` inside `initializing()`, and writes the snapshot back.

`_apply_autonomous_params` calls `init_autonomous_runtime` without `force_recreate`. The deserializer has already built a fresh runtime, so the call keeps that object and `set_drive` writes the gene baselines for `curiosity`, `social_drive`, and `exploration`. The following assignment `agent.social_drive = social_drive` puts the lived social value back. Energy uses the same order. Neuromodulator concentrations are set again after apply.

`genome_inheritance_meta` is written on every agent. On load it replaces meta only when the key is present. `ChinchillaAgent.__init__` stamps `mode: "founder"` only when a genome is passed into the constructor. Load does not pass one, so a missing meta key stays `{}` and does not become founder. A present offspring meta overwrites that empty dict after apply.

`_serialize_inheritance_meta` keeps any JSON-safe extra key. A probe value `crossover_alpha: 0.5` survived.

## Probe

Parents at opposite `GENE_REGISTRY` bounds. Mother `rng_seed=65`, father `rng_seed=66`. Birth is `_start_pregnancy(father.agent_id)` then `_give_birth` (the colony path that calls `_create_offspring`). Litter 1: `G1A1SF`, generation 1, parents `mom-65` / `dad-65`, lineage `adaxlin`, `crossover_mode == "uniform"`.

`af_decay_stress` on that genome is `0.860535` (mutated off the parental endpoints `0.55` and `0.88`). After the new save/load, `axis_decay["stress"]` is `0.860535`. The same file loaded by the pre-fix class leaves `0.75` (`DEFAULT_AFFECTIVE_DECAY` in `src/affective_space.py`).

Lived values set on the kit, then saved: energy `0.37`, `social_drive` `0.15`, affect curiosity `0.31` (boredom `0.69`), dopamine `0.61`, norepinephrine `0.58`, serotonin `0.27`, cortisol `0.44`, acetylcholine `0.36`. New load matched all of them. No load warnings. The gene social baseline on this kit is `0.05`, so `0.15` is the lived value, not the baseline written by `set_drive`. Meta matched, including `crossover_alpha == 0.5`. Offspring mode stayed `recombined`. Mother mode stayed `founder`. Lineage stayed `adaxlin`, not the child's name.

The main-era file has `genome` and does not have `genome_inheritance_meta` or `runtime.neuromodulator_levels`. New loader: phenotype matched (stress `0.860535`), energy `0.37`, `social_drive` `0.15`, meta `{}`, lineage `adaxlin`. Neuromodulator levels fell back to the fresh agent: dopamine `0.1`, norepinephrine `0.1`, serotonin `0.1`, cortisol `0.05`, acetylcholine `0.1`. That is the pre-#65 file, which never stored concentrations. A new save does store them (`schema_version` `1`).

## Curiosity and exploration

Not saved. After 60 simulated seconds of `_advance_autonomous_body` (wall `0.088` s, step `COLONY_BODY_STEP_S` = `1/12`) the kit's drives had left the gene baselines:

| Drive | At birth | After 60 s | After load |
| --- | --- | --- | --- |
| `curiosity` | 0.0500 | 1.0000 | 0.0500 |
| `exploration` | 0.3500 | 0.8493 | 0.3500 |
| `goal_tension` | 0.0800 | 0.6777 | 0.0800 |
| `energy_need` | 0.0200 | 0.0308 | 0.0200 |
| `social_drive` | 0.0500 | 0.5000, then set to 0.15 | 0.1500 |

`curiosity` and `exploration` return to the gene baselines (`dr_curiosity_baseline` `0.05`, `dr_exploration_baseline` `0.35` on this extreme kit). `goal_tension` and `energy_need` return to the fresh-runtime initials. The spec's "etc." covers them. `social_drive` is the one drive that is put back.

The NOWA inspector tab draws affect curiosity, energy, `social_drive`, and the five neuromodulator bars. It does not draw the autonomous `curiosity` / `exploration` drives. Affect curiosity is stored as `affect.boredom`, and `ChinchillaAgent.boredom` is `1 - curiosity_level`, so the axis round-trips. This kit kept `0.31` / `0.69`. The spec sentence about a curiosity axis that diverged from `1 - boredom` does not show up on this class.

What a player can notice is a short gap before those drives cross threshold again, not a forgotten temperament. Bare accumulation in `DriveRule` is `0.020` per simulated second for curiosity and `0.011` for exploration (`src/autonomous_organism.py`), ignoring the affect term.

| Genome | Gap back to threshold | Sim time at the bare rate |
| --- | --- | --- |
| This kit, curiosity `0.05` → threshold `0.30` | 0.25 | 12.5 s |
| This kit, exploration `0.35` → runtime threshold `0.48` | 0.13 | 11.8 s |
| Registry defaults, curiosity `0.18` → `0.45` | 0.27 | 13.5 s |
| Registry defaults, exploration `0.12` → `0.48` | 0.36 | 32.7 s |

At 1x that is a brief lull. At 10x it is a few seconds of wall clock. Decay, thresholds, and half-life stay on the genes. This was one litter and one 60 s interval, not a sweep.

A pre-#65 file is more visible on the neuro bars: lived cortisol `0.44` loaded as `0.05`, because the old schema has no `neuromodulator_levels`. New saves keep the five values.

## Defects

No blocker, critical, major, or minor defects.

## Release readiness

**With the documented drive caveat.** Acceptance criteria in the spec hold: genome reapplied, energy / `social_drive` / neuromodulator levels put back, meta round-trips, old files load. Targeted tests passed. CI on `fac946f` passed. This note does not merge the PR.

## Questions / blockers

No blockers.
