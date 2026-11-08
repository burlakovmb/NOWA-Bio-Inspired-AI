# QA issue #27 — Mendelian colony inheritance

Branch: `team/issue-27-inheritance`. Reviewed HEAD `2b7874c` (spec on top of `ba77db9`, `71c872d`).
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/64
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/27
Baseline: `main` @ `039fd0a` (merge-base).
Russian: [issue-27-inheritance.ru.md](issue-27-inheritance.ru.md).
Spec: [issue-27-inheritance.en.md](../specs/issue-27-inheritance.en.md).

Product code was not changed by this QA pass. No new PR. Full `pytest` was not run locally.

Machine: Python 3.12.3, pygame 2.6.1, pytest 9.2.0. Probes and the targeted pytest set `NOWA_STRICT_LEARNING=1`.

## Verdict

**PASS** (`2b7874c`).

Colony birth copies each gene whole from the mother or the father (`mode="uniform"`), then `mutate(rate=0.05)`. Two offspring of one extreme pair differ. Before mutation every gene is a parental endpoint. Over 8 generations, uniform genetic variance stays far above arithmetic collapse (ratios 66 to 384 on five seeds). A newborn does not receive parental cortisol, dopamine, or serotonin. Energy is `1.0` when both parents are near empty. `social_drive` and all seven `axis_decay` axes match the child's own genes. Birth without a genome logs the warning and returns. The inspector and portrait do not crash on a uniform offspring or on meta that still contains `crossover_alpha`. Old saves load. `inherit_scalar` has no remaining Python callers. `git diff 039fd0a...2b7874c -- src` is empty. Swarm `crossover_mode` stays `arithmetic`.

CI pytest on `2b7874c` passed in 14m25s (run [42476117464](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/42476117464)).

Two spec sentences are imprecise. They are minor and do not fail the acceptance criteria.

## Coverage

Scenarios: **16 passed / 0 failed** in the targeted pytest (5.13 s), plus the independent probes below. Full-suite pytest was left to CI.

| # | Scenario | Result |
| --- | --- | --- |
| 1 | Two offspring, identity mutation: pre-mutation genes are mother or father; siblings differ | Pass. 39/39 endpoints, siblings differ at 18/39 loci. Post-mutation distance 0.679484 |
| 2 | Meta `crossover_mode == "uniform"`, no `crossover_alpha`, rate 0.05 | Pass. Sister mother-share 16/39 = 0.41025641025641024. Brother 20/39 = 0.5128205128205128 |
| 3 | Uniform vs arithmetic variance, 24 founders, 8 generations, mutation on | Pass. Seeds 1, 7, 27, 271, 404. Ratios 158.84, 147.10, 384.32, 107.02, 66.45. All `uniform > arithmetic × 5` and `uniform > initial × 0.4` |
| 4 | Same pedigree through `_create_offspring`, identity mutation, 8 animals, 4 generations, 37 genes with range ≤ 2 | Pass. No non-endpoint allele. Variance 0.030052 → uniform 0.017524 vs arithmetic 0.003450 |
| 5 | Parents cortisol 0.97/0.91, dopamine/serotonin/NE/ACh 0.97/0.91, energy 0.03/0.07, social drive 0.01/0.99, mother stress decay forced to 0.99 | Pass. Child cortisol 0.05, dopamine 0.1, serotonin 0.1, energy 1.0. Sister drive 0.45 and stress decay 0.88 (father maxima). Brother drive 0.05 and stress decay 0.55 (mother minima). All 7 decay axes match the child's genes. Stress axis stays 0.0, not the mother's 0.95 |
| 6 | Birth with `genome is None` | Pass. Warning contains `without a recombined genome`. `genome is None`, energy 1.0, cortisol 0.05, `parents[1] == "father-already-gone"`. No exception under strict learning |
| 7 | Conception snapshot after the live father genome is replaced | Pass. Litter 1. Pre-mutation alleles match the mother or the snapshot. `lt_max_lifespan_factor` uses the snapshot. Energy 1.0. Snapshot cleared after birth |
| 8 | Portrait and inspector on a uniform offspring, then with `crossover_alpha: 0.5` injected | Pass. Both portraits build. Inspector data builds. The uniform meta has no `crossover_alpha` |
| 9 | Save/load of that offspring, a pre-genome save, and extra `crossover_alpha` keys | Pass. No crash. See the minor spec note: meta is not stored |
| 10 | `git grep inherit_scalar -- "*.py"` and `git diff 039fd0a...2b7874c -- src` | Empty. `crossover_alpha` remains only as the `AgentFactory` arithmetic argument (`src/agent_factory.py`, `tests/test_agent_factory.py`) and the absence assertion in the new test |
| 11 | `.github/workflows/tests.yml` | Pass for behavior. Push is `branches: [main]`. `pull_request:` is present. Concurrency group `tests-${{ github.ref }}`, `cancel-in-progress: true`. This branch's runs are `pull_request` only. `main` push run 42473655509 (`039fd0a`) succeeded |
| 12 | Targeted pytest | **16 passed**, 5.13 s, exit 0. Files: `test_issue27_inheritance.py` (4), `test_issue24_silent_failures.py` (11), `test_tc07_newborn_does_not_inherit_parent_neuromodulator_levels` |
| 13 | Spec pair | 98 lines each. 45 numeric tokens identical. Acceptance items 1–6 match the code |

Not run:

| # | Scenario | Why |
| --- | --- | --- |
| 1 | Full `python3 -m pytest -q` | CI job `pytest` on `2b7874c` |
| 2 | Interactive colony GUI click-through | Inspector and portrait were called in-process. No display session was required |

## Defects

### [MINOR] Spec says saved meta may still show `crossover_alpha`

- **Steps**: 1) Build a mother and a father whose genomes sit on opposite `GENE_REGISTRY` bounds. 2) `child = mother._create_offspring(father)`. 3) `ColonyStorage._serialize_agent(child)`. 4) `_deserialize_agent` that payload. 5) Read `Docs/specs/issue-27-inheritance.en.md` section 5.
- **Expected**: The spec says a saved offspring meta may still show pre-#27 `crossover_mode` / `crossover_alpha`.
- **Actual**: `genome_inheritance_meta` is not in the save schema. The JSON has no `crossover_alpha`. After load, meta is `{}`. `axis_decay["stress"]` is the constructor default `0.75` (`DEFAULT_AFFECTIVE_DECAY` in `src/affective_space.py`) while `af_decay_stress` on the restored genome stays the inherited endpoint (`0.88` on the sister). Load does not crash. An old file with no `genome` key, a top-level `crossover_alpha`, and the same key inside the genome dict also loads (`GenomeVector.from_dict` ignores unknown keys). `colony_storage.py` is not in the PR diff, so this is not a new schema break. The spec sentence overstates what colony saves keep.
- **Where**: `Docs/specs/issue-27-inheritance.en.md` and `.ru.md`, section 5. Save path: `ColonyStorage._serialize_agent` / `_restore_saved_agent`.
- **Severity**: minor

### [MINOR] Spec credits concurrency for removing duplicate branch-push and PR runs

- **Steps**: 1) Read `.github/workflows/tests.yml`. 2) Compare `github.ref` for `pull_request` (`refs/pull/64/merge`) with `github.ref` for a push of this head (`refs/heads/team/issue-27-inheritance`). 3) `gh run list --workflow=tests.yml`.
- **Expected**: If the parenthetical were the mechanism, branch push and the PR would share one concurrency group.
- **Actual**: The group is `tests-${{ github.ref }}`. Those two refs differ, so concurrency would not collapse them. The duplicate is avoided because `push` is limited to `main`. That filter is doing the job: runs 42476117464 (`2b7874c`) and 42475225442 (`71c872d`) are `pull_request` only, both success. Push to `main` still runs (42473655509). `cancel-in-progress: true` is present and applies to a later push of the same ref. The YAML matches the spec's snippet. Only the "avoids duplicate runs" clause names the wrong lever.
- **Where**: `Docs/specs/issue-27-inheritance.en.md` and `.ru.md`, section 3, workflow row.
- **Severity**: minor

No blocker, critical, or major defects.

## Known caveats (not FAIL)

| Topic | What was checked |
| --- | --- |
| Portrait calls segregation a mutation | `build_portrait` on the extreme-cross sister returned 8 effects. All 8 current values were an exact parental allele. `nm_decay_half_life` (range 45.0–180.0) was `major` with delta 67.5, which is half the parental span, not a mutation. Spec section 4 already says `midpoint_shift` now highlights loci where the parents differed. The portrait strings were not updated. Nothing raised |
| Mutation rate | `rate=0.05` and `random() <= rate` in `GenomeVector.mutate` are unchanged. About 2 of 39 loci move per birth. That is the pre-#27 rate, not a new choice |
| Haploid loci, no linkage | One continuous value per gene, copied whole, independently. That is the Mendelian rule the spec chose for this vector. Dominance and linkage are not represented |
| `test_tc07_*` | The renamed test builds mother, father, and child with `genome is None`, so it locks the removed unconditional neuromodulator average. The recombined path is locked by `test_maternal_stress_and_parent_energy_stay_with_the_parents` |
| Tiny mutated sample | A 4-animal ring with mutation left on is dominated by drift on wide genes and was not used. The n=8 identity-mutation pedigree and the n=24 suite check are the variance evidence |
| Maternal effects | Acute cortisol and current energy are intentionally not inherited. The spec chooses a rested neonatal start over prenatal transfer |

## Recommendations

- Correct the two spec sentences in both languages. Say that colony JSON does not store `genome_inheritance_meta`, and that duplicate push+PR runs are avoided by `push.branches: [main]`.
- A later change can persist meta (or stop calling endpoint shifts "mutations") if the portrait should distinguish segregation from mutation. Not required for this PASS.
- No product code change is required for the acceptance criteria.

## Release readiness

**With caveats.** Acceptance criteria 1–6 hold, the targeted tests are green, and CI on `2b7874c` passed. The two minor spec sentences should be corrected in a follow-up or before merge if the spec text must be exact. They are not behavior blockers. This note does not merge the PR.

## Questions / blockers

No blockers.
