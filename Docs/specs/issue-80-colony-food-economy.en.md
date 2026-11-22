# Issue #80 — colony food economy (bite at the bowl, walk to get there)

Russian: [issue-80-colony-food-economy.ru.md](issue-80-colony-food-economy.ru.md)

PR #88, branch `team/issue-80-colony-food-economy`. Product HEAD for this spec: `3479434`. Closes the Colony side of [issue #80](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/80). Related: [issue #74](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/74), [issue #56](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/56) (action **duration** — out of scope; **travel hold** here is phase 1 only). Builds on affect and contagion ([issue-54-affect-simulated-time.en.md](issue-54-affect-simulated-time.en.md), [issue-78-affect-time.en.md](issue-78-affect-time.en.md), [issue-79-colony-contagion.en.md](issue-79-colony-contagion.en.md)).

Code (demo): `Demo/Colony chinchillas/src/colony_agent.py`, `Demo/Colony chinchillas/src/shared_resources.py`. Tests: `test_issue_80_food_economy.py`, `test_issue_80_travel_goal.py`, `test_resources.py`. **PR commits do not edit `src/`** (strict biofidelity in core).

---

## 1. Problem

Each simulated second, `_apply_metabolism_second` used to debit shared bowls for every **awake** agent regardless of `eat` / `drink`:

- **Food:** `consume_food(0.0003 * RESOURCE_CONSUMPTION_MULTIPLIER, …)` per second.
- **Water:** `water -= 0.0001 * RESOURCE_CONSUMPTION_MULTIPLIER` per second.

With **16 agents**, bowls emptied far before `REFILL_DAY_S = 600` s; ~93% of measured consumption was passive drain without eating (issue #80 stress repro). Chronic hunger masked other colony dynamics.

---

## 2. Solution (host + shared consume API)

### 2.1 No passive bowl debit (metabolism)

In `_apply_metabolism_second`, after hunger/thirst growth and critical impulses, and after sleep early-return:

| Removed | Kept |
| --- | --- |
| Per-second `consume_food(0.0003 * …)` and `water -= 0.0001 * …` | Need accumulation, critical impulses, empty-bowl affect + energy penalties (`RESOURCE_MISSING_ENERGY_PENALTY_PER_S`, `WATER_MISSING_ENERGY_PENALTY_PER_S`) |

Bowls change only on successful acquisition (below). No spoilage; `REFILL_DAY_S` unchanged.

### 2.2 Variant B — eat and drink only at the station (strict bowl)

**Food:** `_try_acquire_resource("food_pellets")` runs only when the agent stands in `bowl_pellets` or `bowl_hay`. It reads stock in **that** bowl (`_food_stock(here) > 0.05`), then:

```text
consume_food(0.003 * RESOURCE_CONSUMPTION_MULTIPLIER, primary=here, strict=True)
```

`strict=True` in `shared_resources.consume_food` takes **only** from `primary` (`food_pellets` or `hay`). The other bowl does **not** top up a failed bite. Walking elsewhere does not reduce hunger until a bowl step succeeds.

**Drink:** only at zone `waterer` (`position == "waterer"`); otherwise acquire returns `False` without moving water. One `0.003 * RESOURCE_CONSUMPTION_MULTIPLIER` debit per successful tick.

**Travel target for eat:** `_eat_travel_zone()` picks a bowl zone using `_food_primary_source()` (preference `_food_source_preference`, else the non-empty pool). Empty favorite sends the animal to the other bowl when that stock is above `0.05`; both empty → no walk target, “no food” impulse path.

**Biological reading:** the animal eats from the dish under its feet and drinks at the waterer; shared stock is not a invisible colony-wide sip.

### 2.3 Travel hold (issue #56, phase 1)

State (runtime only, **not** saved): `_travel_action`, `_travel_target`, `_travel_started_at`.

| Constant | Value |
| --- | ---: |
| `TRAVEL_GOAL_TIMEOUT_S` | 15.0 |

**Start:** In `_resolve_executed_action`, if the core chose `eat` or `drink` but `_at_consumption_goal` is false, `_begin_travel(action)` sets the three fields. Executed action is forced to `eat` or `drink` with override source `homeostatic:travel_eat` or `homeostatic:travel_drink` until the walk ends.

**During hold:** `_refresh_travel_target()` retargets eat walks when a favorite bowl dries; drink target stays `waterer`. `_interpret_action` still moves one graph step per tick toward the target, then tries acquire.

**End travel (`_clear_travel_goal` or `_finish_travel_goal`):**

| Event | Effect |
| --- | --- |
| Arrival + **one portion** taken (stock dropped vs pre-tick snapshot) | Clear after successful bite |
| `_travel_bite_impossible` on the arrival tick | Clear same tick (no 15 s wait) |
| `TRAVEL_GOAL_TIMEOUT_S` elapsed | Clear, core choice applies again |
| `alarm_call` in context, or `sleep` chosen, or reflex **other than** eat/drink (`hide`, `flee`, …) | Clear before return |
| Death (`_apply_mortality`) | Clear |
| Critical **thirst** during food walk | `_begin_travel("drink")` (timer reset) |
| Critical **hunger** during drink walk (thirst not critical) | `_begin_travel("eat")` or clear if no bowl to walk to |

**`panic_hide` exception:** If the only matched reflex trigger is `high_stress` (no `alarm_call`), `_reflex_is_only_need_stress` suppresses that reflex for this tick so need-driven walks are not cancelled by thirst/hunger stress alone. Real `alarm_call` still wins.

**Persistence:** `ColonyStorage` does not serialize `_travel_*`; loaded agents start with no active walk (`test_travel_is_not_saved_and_a_newborn_starts_without_one`).

**Not in this PR:** multi-tick action duration for eating/drinking (#56 remainder).

### 2.4 Bite gates (`physiology_as_policy`)

Module thresholds (unchanged in PR):

| Constant | Value |
| --- | ---: |
| `HUNGER_AVAILABILITY_THRESHOLD` | 0.50 |
| `THIRST_AVAILABILITY_THRESHOLD` | 0.48 |

`_needs_eat_action` / `_needs_drink_action`: need ≥ threshold; **pregnant** agents use threshold − 0.08 (same gates in `_try_acquire_resource` and `_travel_bite_impossible`).

At the bowl but below gate: no portion, no hunger/thirst relief. With an active travel goal, `_finish_travel_goal` calls `_travel_bite_impossible` first — empty bowls, dry waterer (`water <= 0.02`), or sub-threshold need in policy mode **ends the walk on that tick** instead of waiting 15 s.

Portion size remains `0.003 * RESOURCE_CONSUMPTION_MULTIPLIER` once per successful acquire per tick.

### 2.5 Unchanged neighbours

`_bowl_crowd_conflict` counts eaters **in the bowl zone**, not travelers elsewhere with `current_action == "eat"`. Issue #79 crowding semantics preserved.

---

## 3. Rejected variants

| Variant | Outcome |
| --- | --- |
| Passive metabolism sip (pre-PR) | Removed; see §1 |
| **Threshold removal** (commit `c75fbd1`, reverted) | Without 0.50 / 0.48 gates the colony consumed all food and water by ~300 s; by ~600 s mean hunger and thirst pinned at 1.0. Reverted — gates stay |
| Shared-pool bite away from bowls (non-strict top-up) | Superseded by variant B + walk |

---

## 4. Tests

| File | Role |
| --- | --- |
| `test_issue_80_food_economy.py` | Passive drain, strict bowl/waterer, policy gates, walk-without-spend |
| `test_issue_80_travel_goal.py` | Hold, timeout, alarm/reflex/sleep/death, redirect, panic_hide, save omission, `_travel_bite_impossible` |
| `test_resources.py` | `tc01` bowl drop equals summed eat/drink intake |
| `test_issue_79_contagion.py` | Crowding regression |

QA fixed run at `3479434` / `b955c38`: see [issue-80-colony-food-economy.en.md](../qa/issue-80-colony-food-economy.en.md) — **103 passed** on the issue #80 pytest set.

---

## 5. Observable effect (16 agents, 1500 s, seeds 1 and 2, means)

Deaths: **0** on all rows. Metrics are population means from tech-lead runs (not re-run for this doc).

| Stage | Mean hunger | Mean thirst | Mean cortisol | Mean sleepers | `eat+drink` share |
| --- | ---: | ---: | ---: | ---: | ---: |
| After passive drain removed | 0.28 | 0.26 | 0.26 | 2.2 | 11% |
| Variant A (pre–variant B / pre-strict station) | 0.30 | 0.28 | 0.24 | 1.2 | 50% |
| **Final (`3479434`)** | 0.31 | 0.31 | 0.30 | 1.2 | 16% |

Earlier vs `main` baseline (`89c10a0`): empty-bowl time and hunger-dominated stress dropped sharply once passive sip was removed; variant B and travel further reshaped sleep and action-mix without deaths.

---

## 6. Known limits and follow-ups

- **Mean sleepers ~1.2 vs ~2.2** before “eat only at the bowl” — not explained by stuck travel goals (timeouts and same-tick `_travel_bite_impossible` clear walks). QA analysis: travel hold keeps `eat`/`drink` executed longer; walks that start below the bite gate can sit at a full bowl until timeout. Tracked as a **separate task**, not a blocker for #80 behavior.
- **Action duration** while eating/drinking (#56, beyond travel hold) — out of this PR.
- Branch may lag `main` on unrelated `src/storage.py` (issue #87); PR diff `origin/main...HEAD -- src/` for #80 commits remains empty.

---

## 7. Design principle

Core `src/` stays biofidel. Colony host fixes **accounting** (no passive sip), **geometry** (strict bowl + waterer), and **execution** (travel hold until one portion or cancel). Hunger and thirst still integrate per simulated second; stress from empty bowls when awake is unchanged in kind, only the phantom drain is gone.