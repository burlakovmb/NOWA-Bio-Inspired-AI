# QA issue #22 — colony old age in sim-seconds

Branch: `team/issue-22-colony-lifespan-sim-seconds`. Round 2 checked HEAD `9d49e96`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/61
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/22
Baseline: `main` @ `a8d7503` (merge-base).
Russian: [issue-22-qa.ru.md](issue-22-qa.ru.md).
Spec: [issue-22-colony-lifespan-sim-seconds.en.md](../specs/issue-22-colony-lifespan-sim-seconds.en.md).

Round 1 PASS was product commit `73c2e87` (QA notes `3c3cb54`, `b26956e`). This note covers that scope plus `eecc611` (gene multiplier), `f372606` (scripted media cap), `9d49e96` (spec and colony docs), and the adjacent labile-test fix `8b722f7`. Product code was not changed by this QA pass. No new PR.

Machine: Python 3.12.3, pygame 2.6.1, pytest 9.2.0.

## Verdict

**PASS** (`9d49e96`).

`lt_max_lifespan_factor` is applied. `max_lifespan_age_s = COLONY_MAX_LIFESPAN_AGE_S * genome.genes.get("lt_max_lifespan_factor", 1.0)`. Measured caps are 6750, 13500, and 27000 s. No genome stays 13500 s. A newborn after crossover gets its own cap. `colony_scripted_old_age_s` reads that animal's `MortalitySystem.max_lifespan_age_s`. A founder with factor 2.0 is forced at 27000 s with cause `old_age`. A promo-style agent with no genome is forced at 13500 s with the same cause. `git diff origin/main -- src` is empty. The spec pair matches the code and matches itself. The colony suite is green.

These stay known caveats and are not a FAIL: the ×15 versus ×22.5 base, the health-index lifespan share, and colony save/load dropping `genome`. One colony module spec section still describes the old step budget (minor).

## Coverage

Scenarios: **17 passed / 0 failed / 3 not run**.

| # | Scenario | Result |
| --- | --- | --- |
| 1 | No genome and factor 1.0 → 13500 s; factors 0.5 and 2.0 → 6750 s and 27000 s; step field 20000 | Pass |
| 2 | `old_age` at the same sim-age for dt 1 s and 10 s, including factor 2.0 still alive at 13500 s | Pass (`test_lifespan_factor_scales_old_age_and_matches_across_dt`) |
| 3 | Runner at nominal 1× and 10× dies at that individual's cap; decision counts differ | Pass (`test_lifespan_factor_runner_matches_at_nominal_1x_and_10x`) |
| 4 | Newborn cap follows the post-crossover gene; parents keep 27000 s and 6750 s; three `MortalitySystem` objects | Pass. Probe seeds 13/14: child factor 1.25 → 16875 s |
| 5 | Birth with only one parent genome | Pass. Child genome is `None`, cap 13500 s; the parent who has a genome keeps 27000 s or 6750 s |
| 6 | `colony_scripted_old_age_s` | Pass. 27000 / 6750 / 13500 for factor 2.0, factor 0.5, and no genome |
| 7 | `render_evolution_media._kill_oldest` on those three | Pass. Cause `old_age`, `agent.age` stays 250, `lived_steps` stays 17, runner list empty |
| 8 | Promo-equivalent `MortalitySystem.update` with no genome | Pass. Cause `old_age`, cap 13500 s, `age` stays 250, `lived_steps` stays 9 |
| 9 | Registry bounds | Pass. 0.5 and 2.0 construct; 0.499, 2.001, 0.0, and 3.0 raise `ValueError` |
| 10 | Young animal, factor 2.0, `lived_steps` 50000, then `_age_step(0.1)` | Pass. Alive, age 10.1, empty cause |
| 11 | Exhaustion at age 400, energy 0.08, factor 0.5, `_age_step(0.5)` | Pass. `exhaustion` at 400.5, not `old_age` |
| 12 | Age already above the cap; `max_lifespan_age_s is None` | Pass. Age 30000 s with factor 2.0 still `old_age` and age unchanged. A cleared cap falls back to the gene formula (6750 s) |
| 13 | Random founder, `GenomeVector.random` from `random.Random(11)` | Pass. Factor 0.8563250131981743, cap 11560.387678175353, helper returns that cap |
| 14 | `git diff origin/main -- src` | Empty. `colony_storage.py` and `swarm_analytics.py` are not in the branch diff |
| 15 | Spec pair, `COLONY_SPEC`, `IMPLEMENTATION_DESCRIPTION` | Pass. Spec files are 94 lines each. Numeric tokens are identical (100 = 100), including 6750, 13500, 27000, 20250 |
| 16 | `python3 -m pytest -q "Demo/Colony chinchillas/tests"` | **232 passed, 1 warning**, exit 0, 327.60 s. The warning is pygame `pkg_resources`. `test_founders_do_not_die_of_exhaustion_at_10x` passed inside this run (not rerun alone) |
| 17 | Five labile tests that previously raised `TypeError` from nested `pytest.approx` | **5 passed**, 0.21 s, after `8b722f7`. Not re-failed |

Not run:

| # | Scenario | Why |
| --- | --- | --- |
| 1 | Full `render_evolution_media` / `render_promo_media` GIF render | Would write `docs/media`. The death calls were executed directly |
| 2 | Full root `python3 -m pytest -q` | Out of this round's minimum. Only the colony suite and the five labile tests were run |
| 3 | Round-1 manual walk from age 0 at `dt = 1/12` (162000 updates) | Not repeated. The automated default-cap tests in the suite passed again (`test_old_age_lifespan_matches_across_dt`, `test_runner_old_age_matches_at_nominal_1x_and_10x`, `test_tc14_colony_old_age_uses_sim_seconds`, `test_tc28_old_age_follows_biological_age_not_decision_steps`). Targeted file plus those two named tests: **24 passed**, 98.75 s |

`git status` after the suites: clean. Ignored only: `.pytest_cache/`, `Demo/Colony chinchillas/logs/`, and `__pycache__`. No lowercase `docs/` directory.

## Defects

### [MINOR] Module spec still says old age follows the step budget

- **Steps**: 1) Open section 10 of `Demo/Colony chinchillas/Docs/SPEC_ChinchillaAgent_NOWA.en.md` and `.ru.md`. 2) Compare with `ChinchillaAgent` and with `Docs/specs/issue-22-colony-lifespan-sim-seconds.en.md`.
- **Expected**: Old age is biological age in sim-seconds, scaled by `lt_max_lifespan_factor`.
- **Actual**: Section 10 still says the colony does not enforce a hard lifespan in seconds and that `old_age` follows the step budget.
- **Where**: `Demo/Colony chinchillas/Docs/SPEC_ChinchillaAgent_NOWA.en.md`, `.ru.md`, section 10.
- **Severity**: minor

No blocker, critical, or major defects.

## Known caveats (not FAIL)

Confirmed against the code and the spec's open points. They do not change the verdict.

| Topic | What was checked |
| --- | --- |
| ×15 versus ×22.5 | Base constant is still `15 * MATURITY_AGE_S = 13500`. The alternative `22.5 * MATURITY_AGE_S = 20250` is only in spec section 6. The gene multiplies the ×15 base; it does not replace that choice |
| Health-index lifespan share | `compute_health_index` still sets `lifespan` to mean `lived_steps` divided by `_max_lifespan_steps` (`colony_gui/swarm_analytics.py`). The age cap does not enter that denominator. `swarm_analytics.py` is not in the branch diff |
| Save/load of genome | `ColonyStorage._serialize_agent` does not write `genome`. `_deserialize_agent` builds `ChinchillaAgent` without one. Probe: factor 2.0, age 14000 s, energy 0.9, `lived_steps` 40. After load, `genome is None`, cap is 13500 s, age is still 14000 s. The next `_age_step(0.1)` records `old_age` at age 14000.1. Spec section 6 calls this a pre-existing limitation |

## Recommendations

- Fix `SPEC_ChinchillaAgent_NOWA` section 10 in both languages so it matches the age cap. That is the only doc left in this tree that still describes the old rule.
- A later change can persist `genome` (or the resolved cap) in `ColonyStorage`, and can point the health-index lifespan term at `max_lifespan_age_s`. Both are already specified as follow-ups. Add a save/load test when that lands: factor 2.0 must survive reload.
- The gene, newborn, and scripted-death tests that the spec lists are present and green. No further test is required for this PASS.
- PR #61 body still says the spec files were left for a tech writer. `9d49e96` already updated them. Worth a one-line correction in the PR text. CLA checkboxes were not touched.

## Release readiness

**With caveats.** The round-2 definition of done is met: gene formula, media helper, and the issue spec plus the updated colony lifecycle docs agree; gene and media tests are green; this EN/RU note matches that fact. Do not merge on the strength of this note alone if the minor spec section must be clean first. The three caveats above are accepted leftovers, not release blockers for #22.

## Questions / blockers

No blockers.

Non-blocking: should section 10 of `SPEC_ChinchillaAgent_NOWA` be corrected before merge, or in a follow-up? The acceptance spec and `COLONY_SPEC` / `IMPLEMENTATION_DESCRIPTION` already describe the gene.

## Round 2 evidence

Formula in `Demo/Colony chinchillas/src/colony_agent.py`:

```text
max_lifespan_age_s = COLONY_MAX_LIFESPAN_AGE_S * genome.genes.get("lt_max_lifespan_factor", 1.0)
```

`_colony_max_lifespan_age_s` uses 1.0 when `genome` is missing or the key is missing. `ChinchillaAgent.__init__` passes that value into `MortalitySystem` and still passes `max_lifespan_steps=COLONY_MAX_LIFESPAN_STEPS` (20000). After crossover, `_inherit_nowa_from` assigns the child genome and sets `mortality_system.max_lifespan_age_s` again. `GenomeVector` rejects values outside 0.5..2.0, so a real genome cannot leave 6750..27000 s. `AgentFactory.spawn` is still not the colony birth path. `git diff origin/main -- src` prints nothing, so `src/mortality.py` is unchanged: with the age cap set, `old_age` is `biological_age_s >= max_lifespan_age_s`, and the step field is not that gate.

`colony_scripted_old_age_s` reads `mortality_system.max_lifespan_age_s` and returns `max(agent.age, cap)`. If the cap is `None`, it falls back to the same gene formula. `tools/render_evolution_media.py` `_kill_oldest` and `tools/render_promo_media.py` `simulate_promo_lineage` both pass that value as `biological_age_s`. They do not assign it back to `agent.age` and do not set `lived_steps` to 20000. Energy 0.5 and wakefulness 0.2 keep exhaustion and sleep deprivation from firing first. Promo founders are constructed without a genome.

Default-cap regression inside the same suite: `test_tc14_colony_old_age_uses_sim_seconds` and `test_tc28_old_age_follows_biological_age_not_decision_steps` passed. A separate founder with factor 2.0, age 250, `lived_steps` 17, updated through the helper, left the runner with journal cause `old_age`.

Docs at `9d49e96`: `Docs/specs/issue-22-colony-lifespan-sim-seconds.en.md` and `.ru.md` state the formula, the 6750..27000 span, the media helper, the eight host checks, and the three open points. `Demo/Colony chinchillas/Docs/COLONY_SPEC.en.md` / `.ru.md` and `IMPLEMENTATION_DESCRIPTION.en.md` / `.ru.md` state the same per-animal product. The round-1 spacing typo in the English open point ("product/ biology") is gone; the row now reads `22.5 * MATURITY_AGE_S = 20250`. `Docs/arxiv_NOWA_en.md` and `Docs/arxiv_NOWA_ru.md` were not part of this diff.

## Round 1, not repeated by hand

The previous text of this file said the gene did not scale the cap. That sentence is withdrawn. Round 1 measured the unscaled cap: `old_age` at 13500 s for `dt` of `1/12`, `0.25`, `1`, `2.5`, and `10`, and runner frames `1/12` (12 decisions), `0.25`, `2.5` (4 decisions), `0.07`, and `10`. Those manual walks were not repeated. The automated tests that lock the default cap passed again inside the 232. Exhaustion, sleep deprivation, and the separate mother/father/child NOWA objects remain covered by the suite. The earlier CI snapshot (run 42061921160, five `pytest.approx` failures) was not re-queried. Locally those five tests now pass on pytest 9.2.0.
