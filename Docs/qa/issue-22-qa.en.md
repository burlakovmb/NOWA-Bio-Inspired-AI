# QA issue #22 — colony old age in sim-seconds

Branch: `team/issue-22-colony-lifespan-sim-seconds`. Checked `73c2e87` (this note is the next commit).
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/61
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/22
Baseline: `main` @ `a8d7503` (merge-base).
Russian: [issue-22-qa.ru.md](issue-22-qa.ru.md).
Scope: read-only check of the two commits on this branch. Product code was not changed. The PR body was not edited.

Machine: Python 3.12.3, pygame 2.6.1, pytest 9.2.0 for the suites below. The five core failures were re-run on pytest 8.3.5.

## Verdict

**PASS** (`73c2e87`).

Old age in Demo/Colony chinchillas is biological age in sim-seconds. Each `ChinchillaAgent` builds its own `MortalitySystem` with `max_lifespan_age_s = 13500` (`15 * MATURITY_AGE_S`). `git diff origin/main -- src` is empty. Death is `old_age` at age 13500 at 1× and 10× and at `dt` of `1/12`, `0.25`, `1`, `2.5`, `10`, and an odd `0.07` s frame. A young animal with `lived_steps` above 20000 stays alive. Exhaustion and sleep deprivation still kill earlier. Unmet hunger and thirst still spend energy. Founders and a newborn do not share an `Agent` or a `MortalitySystem`. Both media scripts register `old_age`. The colony suite is green. The spec pair matches the code. One colony spec section still describes the old step budget; that residual does not change the measured behaviour.

## Coverage

| Check | Result |
| --- | --- |
| `git diff origin/main -- src` | Empty |
| `COLONY_MAX_LIFESPAN_AGE_S` | `15 * 900 = 13500`; `13500 / 300 = 45` gestations |
| Old age at several `dt` and at 1× / 10× | `old_age` at age 13500; decision counts differ |
| Young animal, `lived_steps` 20050 and 50012 | Alive |
| Exhaustion at age 400.5; sleep deprivation at age 800.25 | Those causes, not `old_age` |
| Unmet hunger `dt=1` and unmet thirst `dt=2.5` | Energy drop 0.02 and 0.0625 |
| Separate NOWA stack for mother, father, newborn | Pass |
| `tools/render_evolution_media.py`, `tools/render_promo_media.py` | Journal cause `old_age` |
| `python3 -m pytest -q "Demo/Colony chinchillas/tests"` | **228 passed, 1 warning**, exit 0, 398.74 s |
| `test_founders_do_not_die_of_exhaustion_at_10x` | Passed inside that run (not rerun) |
| `python3 -m pytest -q tests` on pytest 9.2.0 | **5 failed, 900 passed, 5 skipped, 2 warnings**, exit 1, 584.79 s |
| Same five tests on pytest 8.3.5 | **5 passed**, 1.67 s |
| `git status` after the suites | Clean. `Demo/Colony chinchillas/logs/` is gitignored |
| Spec pair and colony lifecycle docs | Numbers match. See the residual in section 6 |
| PR #61 body | Contains `Closes #22` (English section and Russian section) |
| Lowercase `docs/` directory | Absent |

## 1. Core is unchanged; the cap is per chinchilla

`git diff origin/main -- src` prints nothing. `src/mortality.py` is the same file as `main`. With `max_lifespan_age_s` set, `MortalitySystem.update` registers `old_age` when `biological_age_s >= max_lifespan_age_s` and does not consult `max_lifespan_steps` for that cause. The step field stays 20000 for snapshots and the health-index normaliser.

`ChinchillaAgent.__init__` passes `max_lifespan_age_s=COLONY_MAX_LIFESPAN_AGE_S` and `max_lifespan_steps=COLONY_MAX_LIFESPAN_STEPS`. A founder built with `GenomeVector.random` still has age cap 13500 and step field 20000. `_apply_genome_to_agent` does not replace `mortality_system`. Colony birth does not call `AgentFactory.spawn`, which is the core path that builds a step-only `MortalitySystem`.

Senescence coefficients on the colony system are the pre-change values: start fraction 0.75, vitality loss rate 0.00018, critical energy 0.08. Critical wakefulness stays the core default 0.95.

## 2. Age 13500 at 1×, 10×, and other `dt`

`_age_step` is the colony clock. It adds `dt` to `age` and passes `biological_age_s=self.age`. It does not increment `lived_steps`. A full life from age 0, energy 0.9, wakefulness 0.2, cortisol 0.05, `lived_steps` fixed at 3:

| `dt` (s) | Age at death | Cause | Clock updates | `lived_steps` | Vitality | Senescence onset age |
| --- | --- | --- | --- | --- | --- | --- |
| 1/12 | 13500.0000000267 | `old_age` | 162000 | 3 | 0.681055 | 10125.000000002 |
| 0.25 | 13500.0 | `old_age` | 54000 | 3 | 0.681039 | 10125.25 |
| 1 | 13500.0 | `old_age` | 13500 | 3 | 0.680968 | 10126 |
| 2.5 | 13500.0 | `old_age` | 5400 | 3 | 0.680826 | 10127.5 |
| 10 | 13500.0 | `old_age` | 1350 | 3 | 0.680117 | 10130 |

The 1/12 run is 2.7e-8 s over 13500 after 162000 additions. Onset is the first sample at or past `0.75 * 13500 = 10125`. Vitality stays near 0.68, so senescence does not replace `old_age`. The 1/12 and 0.25 runs take more than 20000 clock updates and still do not die by the step budget.

`SimulationRunner` from age 13499, same energy and wakefulness. A frame larger than `MAX_TICK_DT` (0.25 s) is split. The animal is removed on the substep that reaches the cap, so age does not keep climbing inside that frame.

| Frame | Age | Cause | `lived_steps` | Journal | Removed |
| --- | --- | --- | --- | --- | --- |
| 1× = 1/12 s | 13500.000000000007 | `old_age` | 12 | `old_age` | yes |
| 0.25 s | 13500.0 | `old_age` | 4 | `old_age` | yes |
| 10× = 2.5 s | 13500.0 | `old_age` | 4 | `old_age` | yes |
| 0.07 s | 13500.05 | `old_age` | 15 | `old_age` | yes |
| 10 s (split) | 13500.0 | `old_age` | 4 | `old_age` | yes |

Nominal 1× takes 12 decisions for that last second. Nominal 10× takes 4 decisions of 0.25 s inside one 2.5 s frame. The spec's 12-versus-4 figure matches this run.

A direct `MortalitySystem.update` with `lived_steps=20000` and `biological_age_s=100` does not kill while the age cap is set.

## 3. Young animals, exhaustion, sleep, hunger

Young agent, age 10, `lived_steps = 20050`, then `_age_step(0.1)`: still alive, age 10.1, cause empty. `get_age_fraction` is `10.1 / 13500`, not `20050 / 20000`.

The same shape through the runner: age 20, `lived_steps = 50000`, then frames `1/12`, `2.5`, and `0.25`. Alive afterwards, age 22.833..., `lived_steps` 50012 (12 decisions), cause empty.

Exhaustion: age 400, energy 0.08, `_age_step(0.5)` → cause `exhaustion` at age 400.5.

Sleep deprivation: age 800, wakefulness 0.95, energy 0.9, `_age_step(0.25)` → cause `sleep_deprivation` at age 800.25.

If energy is already critical on the step that also crosses 13500, the core still registers `exhaustion` first. That order is in unchanged `src/mortality.py`.

Unmet needs, `physiology_as_policy=True`, action `idle`, energy 0.95:

- Hunger 0.9, thirst 0.1, `dt=1`: energy drop 0.020000000000000018, equal to `UNMET_HUNGER_ENERGY_PER_S` (0.02).
- Thirst 0.9, hunger 0.1, `dt=2.5`: energy drop 0.0625, equal to `0.025 * 2.5`.
- The same hunger with action `eat`: energy stays 0.95.

`_apply_unmet_need_cost` is not in the diff.

## 4. Separate agent and mortality system

Mother and father are genome founders (ages 1200 and 1300). Birth goes through `_give_birth` → `_create_offspring` → `_inherit_nowa_from`. The child is generation 1, age 0, and its age cap is still 13500.

These objects are three distinct identities for mother, father, and child: `mortality_system`, `hippocampus`, `cortex`, `selector`, `sleep_manager`, `intent_memory`, `neuromodulators`, `wakefulness`, `reproductive_system`, `affective_space`, `value_layer`. Driving the child across the age cap sets the child's cause to `old_age` and leaves both parents alive at their original ages, with an empty cause.

Two further GUI-style founders also have distinct `MortalitySystem` and `NOWAHippocampus` objects, both capped at 13500.

The child does share the mother's `random.Random`, the resources object, the colony list, and the `lru_cache`d behaviour profile. Those are the pre-change host links (`rng=self._rng`, `resources=self.resources`, `colony=self.colony`, `load_colony_behavior_profile`). They are not a shared NOWA agent or a shared `MortalitySystem`. This diff does not touch that constructor call.

## 5. Media scripts

`_kill_oldest` in `tools/render_evolution_media.py` was called on two living agents (ages 250, `lived_steps` 17, energy 0.8). Both left the runner. Death journal and memorials say `old_age`. `lived_steps` stayed 17. `agent.age` stayed 250: the script passes `biological_age_s=max(age, 13500)` into `update` and does not write that value back onto `age`. The previous script also left `agent.age` alone and forced the cause through `update`. The cause is still `old_age`.

The promo update in `tools/render_promo_media.py` was executed as written (energy 0.5, wakefulness 0.2, `lived_steps` left at 9, `biological_age_s=max(age, COLONY_MAX_LIFESPAN_AGE_S)`, `dt_s=1`). The runner's death registration stored `old_age`. The full renderer was not launched, so it did not write `docs/media`.

## 6. Tests, git status, docs

Colony suite, from a clean tree: **228 passed, 1 warning**, exit 0, 398.74 s. The warning is pygame's `pkg_resources` deprecation. `test_founders_do_not_die_of_exhaustion_at_10x` is inside that file set and passed on this run, so it was not rerun.

Root suite `python3 -m pytest -q tests` on pytest 9.2.0: **5 failed, 900 passed, 5 skipped, 2 warnings**, exit 1, 584.79 s. Every failure is `TypeError: pytest.approx() does not support nested data structures` in labile-snapshot comparisons:

- `tests/test_issue13_two_tier.py::test_feedback_is_idempotent_and_a_changed_rating_replaces`
- `tests/test_issue13_two_tier.py::test_save_load_restores_labile_clock_and_config`
- `tests/test_issue13_two_tier.py::test_second_sleep_matches_shy_only_control`
- `tests/test_qa_pr37_labile_layer.py::test_feedback_idempotency_replacement_and_unknown_id`
- `tests/test_qa_pr37_labile_layer.py::test_save_load_legacy_empty_and_decay_continues`

`git diff origin/main -- tests` is empty, and `src/` is empty, so these tests are the same as `main`. The same five tests on pytest 8.3.5: **5 passed** in 1.67 s. This is the pytest 9.2 assertion API, not the lifespan change.

`git status` after both suites: clean working tree. `git status --short --ignored` shows `Demo/Colony chinchillas/logs/` ignored. No tracked log file changed.

Docs:

- `Docs/specs/issue-22-colony-lifespan-sim-seconds.en.md` and `.ru.md` exist (83 lines each). Numeric tokens are identical across the pair: 13500, 20000, 15, 900, 300, 45, 33–49, 111, 38, 1667, 5000, `1/12`, 0.25, 12, and 4. Those match `config_colony.py` and the runs above.
- `Demo/Colony chinchillas/Docs/COLONY_SPEC.en.md` / `.ru.md` and `IMPLEMENTATION_DESCRIPTION.en.md` / `.ru.md` now state the 13500 s cap and keep 20000 as the snapshot / health-index field only.
- No lowercase `docs/` directory in the tree. The media scripts' output path is still the pre-existing string `docs/media`; this check did not create it.
- Residual: `Demo/Colony chinchillas/Docs/SPEC_ChinchillaAgent_NOWA.en.md` and `.ru.md` section 10 still say the colony does not enforce a hard lifespan in seconds and that `old_age` follows the step budget. That section is stale. `Docs/arxiv_NOWA_en.md` and `Docs/arxiv_NOWA_ru.md` still mention a 20000-step old-age budget; they are outside the colony doc pair this branch updated.
- English spec section 6 has a spacing typo ("product/ biology"). The numbers in that row match the Russian row (`22.5 * MATURITY_AGE_S = 20250`).
- PR #61 body contains `Closes #22` in both language sections. Not edited.

## 7. Biological model

The diff adds one constructor argument. It does not remove exhaustion, sleep deprivation, senescence, or the cortisol term on vitality loss. Senescence still starts at 75% of the lifespan clock and still reduces vitality (about 0.32 by the cap at cortisol 0.05). The lifespan clock for that fraction is now sim-seconds, which is what `get_age_fraction` already did whenever `max_lifespan_age_s` was set. Onset in sim-seconds is therefore 10125 at every `dt`, instead of 15000 decisions.

The ×15 cap is the captive average cited in the spec (about 8 months to maturity, about 10 years of life). The ×22.5 alternative for a longer adult span is left open. `lt_max_lifespan_factor` still does not scale the colony cap; a random genome leaves 13500 in place. The swarm-analytics lifespan term still divides mean `lived_steps` by `max_lifespan_steps` (`colony_gui/swarm_analytics.py`). Both are written down in the spec as follow-ups. They are not a removed death condition.

Issue #22 also described energy recovery and sleep pressure. This diff does not change those functions. Sleep recovery duration on this tree is already `dt * SLEEP_RECOVERY_DURATION_FACTOR` (22). That path was not re-scored here.
