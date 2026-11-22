# Issue #80 — colony food economy (eat/drink-only bowl drain)

Russian: [issue-80-colony-food-economy.ru.md](issue-80-colony-food-economy.ru.md)

PR #88, branch `team/issue-80-colony-food-economy`. Closes the Colony side of [issue #80](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/80). Related: [issue #74](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/74), [issue #56](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/56) (action duration — **out of scope** here). Builds on alarm, affect, and contagion work ([issue-54-affect-simulated-time.en.md](issue-54-affect-simulated-time.en.md), [issue-78-affect-time.en.md](issue-78-affect-time.en.md), [issue-79-colony-contagion.en.md](issue-79-colony-contagion.en.md)).

Code (demo only): `Demo/Colony chinchillas/src/colony_agent.py`. Tests: `Demo/Colony chinchillas/tests/test_issue_80_food_economy.py`, `Demo/Colony chinchillas/tests/test_resources.py`. **`src/` is unchanged** — no core retuning for the demo.

---

## 1. Problem

Each simulated second, `_apply_metabolism_second` (called from `_resource_metabolism_step` when the per-agent metabolism accumulator reaches 1 s) ran for every **awake** agent and **unconditionally** reduced shared bowl levels:

- **Food:** `consume_food(0.0003 * RESOURCE_CONSUMPTION_MULTIPLIER, …)` every second per waking agent.
- **Water:** `water -= 0.0001 * RESOURCE_CONSUMPTION_MULTIPLIER` every second per waking agent.

This drain did **not** depend on `eat` / `drink` actions, successful acquisition, or hunger/thirst above availability thresholds. Real bites already happen in `_try_acquire_resource` at `0.003 * RESOURCE_CONSUMPTION_MULTIPLIER` once per action tick.

**Observed failure mode (issue #80, stress repro):** ~93% of measured food consumption was passive drain without eating; with **16 agents** the shared food bowl was empty ~54–65% of simulated time while refill cadence (`REFILL_DAY_S = 600` s in `config_colony.py` / `simulation_runner.py`) could not keep up. Animals accumulated hunger stress even when they were not at the bowl eating. That masked behavioural dynamics (crowding, policy, contagion) and made chronic hunger the dominant stress driver in colony runs (see also [issue-79-colony-contagion.en.md](issue-79-colony-contagion.en.md) §5 plateau note).

---

## 2. Solution (host only)

All behaviour lives in `colony_agent.py`. Shared resource types and refill logic (`shared_resources.py`, `simulation_runner.py`, `config_colony.py`) are **unchanged** in this PR.

### 2.1 Remove passive bowl debit from metabolism

In `_apply_metabolism_second`, after hunger/thirst accumulation and critical thirst/hunger impulses, and after the early return for sleep:

| Removed | Kept |
| --- | --- |
| Per-second `consume_food(0.0003 * …)` | Hunger/thirst growth (`HUNGER_ACCUMULATION_PER_S`, `THIRST_ACCUMULATION_PER_S`) |
| Per-second `water -= 0.0001 * …` | Critical hunger/thirst affect impulses |
| — | Early return when `is_sleeping` or `current_action == "sleep"` |
| — | **Empty-bowl penalties:** if `pellets + hay <= 0`, affect + `RESOURCE_MISSING_ENERGY_PENALTY_PER_S`; if `water <= 0`, affect + `WATER_MISSING_ENERGY_PENALTY_PER_S` (both scaled by `RESOURCE_CONSUMPTION_MULTIPLIER`) |

Awake agents no longer sip shared stock by merely metabolizing.

### 2.2 Consumption only on successful eat/drink

Bowl levels drop **only** in `_try_acquire_resource`, unchanged portion size and once per invocation:

| Resource | Condition (summary) | Debit |
| --- | --- | --- |
| `food_pellets` | Not sleeping; optional physiology gate; availability > 0.05 | `consume_food(0.003 * RESOURCE_CONSUMPTION_MULTIPLIER, …)` + `EAT_RELIEF` on hunger |
| `water` | Not sleeping; optional physiology gate; water > 0.02 | `water -= 0.003 * RESOURCE_CONSUMPTION_MULTIPLIER` + `DRINK_RELIEF` on thirst |

`sim_step` still calls `_interpret_action` once per tick; `eat` and `drink` branches are mutually exclusive, so at most **one** acquire path runs per tick per agent.

**Explicit non-goals (this issue):**

- No spoilage / passive decay rate added.
- `REFILL_DAY_S` not changed (`600.0`).
- No changes to action duration (#56).
- **`src/`** genome, appraisal, and hippocampus paths untouched (strict biofidelity).

### 2.3 Biological meaning

Shared food and water represent a **physical bowl**. A chinchilla reduces that stock only when it **eats** or **drinks** at the bowl (host action + acquire), not by standing awake elsewhere. Hunger and thirst still rise with simulated time; empty bowls still hurt via affect and energy penalties — scarcity without invisible evaporation.

### 2.4 Unchanged colony semantics

`_bowl_crowd_conflict`, `current_action == "eat"` for crowding, and `sim_step` ordering (conflict before `_interpret_action`) are **not** modified in this PR; issue #79 crowding tests remain valid.

---

## 3. Tests

### 3.1 `test_issue_80_food_economy.py`

| Test | Covers |
| --- | --- |
| `test_awake_animals_below_the_need_do_not_drain_the_bowls` | 24 s, three awake agents under eat/drink thresholds; bowls unchanged; hunger/thirst grow |
| `test_empty_colony_does_not_drain_the_bowls` | 30 s, zero agents; bowls unchanged |
| `test_eat_and_drink_events_match_the_bowl_on_a_metabolism_tick` | One bite (`BITE = 0.003 * RESOURCE_CONSUMPTION_MULTIPLIER`) per eat/drink tick; nine fed ticks + idle explore tick; bowl drop equals summed intake |
| `test_hunger_and_thirst_still_accumulate_while_awake` | 20 s awake, full bowls, needs rise, no consumption |
| `test_empty_bowls_still_cost_energy_and_are_not_sipped` | Empty bowls: energy penalties, bowls stay at 0, no passive drain |
| `test_sleep_still_skips_the_empty_bowl_penalty_and_the_bowls` | Sleep: no bowl change, no empty-bowl energy penalty, hunger/thirst still grow |

### 3.2 `test_resources.py`

| Test | Covers |
| --- | --- |
| `test_tc01_two_agents_basic_survival_loop` | **Updated:** 300 s, two agents; `abs(food_drop - sum(eaten)) <= 1e-9` and same for water; drop > 0 iff intake list non-empty |
| `test_tc01_two_agents_survive_300s` | Survival regression |
| `test_tc04_wheel_is_exclusive_resource` | Unrelated resource exclusivity regression |

### 3.3 Regression neighbours (QA)

`Demo/Colony chinchillas/tests/test_issue_79_contagion.py` (including `test_bowl_crowding_counts_extra_eaters_in_that_zone`). QA did not re-run `test_tc26d_sleeping_agent_does_not_consume_shared_food_or_water` or `test_tc26e_sleeping_agent_cannot_directly_eat_or_drink` in the fixed pytest set; they remain logically aligned with sleep early-return and acquire guards.

---

## 4. QA

Report: [issue-80-colony-food-economy.ru.md](../qa/issue-80-colony-food-economy.ru.md) — **PASS** at `83e1741`. `git diff origin/main -- src/` empty.

---

## 5. Observable effect (headless run, tech lead)

Colony run **1500 s simulated**, **16 agents**, seeds **1** and **2**. Compare **`origin/main`** `89c10a0` vs **PR** `83e1741`:

| Metric | main `89c10a0` | PR `83e1741` |
| --- | ---: | ---: |
| Time with empty food bowl | 54% | 0% |
| Time with empty water bowl | 50% | 0% |
| Mean hunger | 0.60 | 0.28 |
| Fraction hungry (H > 0.4) | 0.64 | 0.25 |
| Mean cortisol | 0.47 | 0.26 |
| Mean energy | 0.71 | 0.97 |
| Mean stress (seed 1 / seed 2) | 0.68 / 0.66 | 0.63 / 0.58 |
| Fraction fearful (seed 1 / seed 2) | 0.74 / 0.72 | 0.65 / 0.64 |

---

## 6. Conclusion and limits

**Hunger is no longer the main stress driver** in the 16-agent scenario after fixing passive drain: bowl-empty time and mean hunger drop sharply; energy and cortisol improve. **Remaining stress and fearful fractions** (~0.58–0.65 stress, ~64–65% fearful on PR) come from other host and core sources (alarm, contagion, social conflict, policy frustration, etc.) and are **out of scope for #80**.

Tuning population vs `REFILL_DAY_S`, adding explicit spoilage, or binding consumption to action duration (#56) are separate demo-environment or follow-up issues — not part of this fix.

---

## 7. Design principle

Strict biological fidelity in `src/`: only the Colony **host** (`colony_agent.py`) changed. Metabolism still integrates per simulated second per agent; only the **accounting** of shared bowls moved to real eat/drink acquisition.