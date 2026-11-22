# QA issue #80 — bite at the bowl, and the walk that gets there

Russian: [issue-80-colony-food-economy.ru.md](issue-80-colony-food-economy.ru.md)

Branch: `team/issue-80-colony-food-economy`. HEAD: `b955c38` (`b955c385af8cf779896dc45192b0d2190b0a42a4`). PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/88. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/80. Base: `origin/main` `226e928` (`226e928dfe41875dd017cd815e485b256c1e7721`). Commits added after the `83e1741` pass: `53f7b17` (eat and drink only at the bowl or the waterer, `strict`) and `b955c38` (hold the walk, first slice of #56).

Product code was not changed in this pass. No new PR, no merge. CI was not waited on. The 16-agent measurement was not repeated.

Machine: Python 3.12.3, pytest 9.2.0.

The earlier pass on `83e1741` was **PASS** for that checklist (passive sip removed; `src/` against the then `main` `89c10a0` was empty). This report replaces it.

## Verdict

**PASS** on items 1–7, 9, and 10. Item 8 **FAIL**.

Bowl and travel behavior matches the checklist. The only defect: the branch does not contain `main` commit `b698959` (`src/storage.py`, issue #87), so the literal `git diff origin/main -- src/` is not empty. The commits of this PR do not edit `src/`.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | `bowl_pellets` spends only pellets, `bowl_hay` only hay; away from a bowl nothing is spent and hunger does not fall | Pass. Probe: at the pellet bowl with hay preferred, `food_pellets` `1 → 0.994`, `hay` `1`, hunger `0.9 → 0.42`. At the hay bowl the opposite. From `house`, one step to `floor`, both bowls `1`, hunger `0.9`, affect unchanged |
| 2 | Empty favorite bowl → the other bowl, then a bite; both empty → no spend, a "no food" impulse; no impulse on the path | Pass. From `bowl_pellets` with `pellets=0`, `hay=1`, one step to `bowl_hay`, hay `0.994`, hunger `0.42`. Both zero: levels `0`, hunger `0.9`, affect axes match impulse `stress=0.2`, `valence=-0.3`, `intensity=0.8`. From `house` with full bowls, the step to `floor` has no impulse and no spend |
| 3 | `drink` only at the `waterer`; from `floor` and from `house` the walk arrives and takes a portion even if the core picks something else in between | Pass. Both `physiology_as_policy` True and False. Core script: `drink`, then `socialize` / `play`. `floor → bowl_hay → waterer` in `2.5` s, water `0.994`, thirst `< 0.5`. `house → floor → bowl_hay → waterer` in `3.75` s, same portion. Water stays `1` until the `waterer` |
| 4 | Clear the walk: 15 s, `alarm_call`, a different reflex, sleep, death; a save does not carry the walk; critical thirst during a food walk switches to water | Pass. Timeout at `sim_time` `4 → 19`: action `play`, walk empty. `alarm_call` → `hide`, `reflex:panic_hide`. A `flee` reflex on `boom` clears the walk. `sleep` clears it. Death via `_apply_mortality`: `current_action=dead`, travel fields empty. `ColonyStorage`: JSON has no `_travel_action`, loaded fields are `None`. Thirst `0.82` during a food walk: `drink`, target `waterer`, timer reset to `3.0` |
| 5 | `panic_hide` from `high_stress` alone during a walk does not cancel the walk or take cooldown; a real alarm still hides; fear outside a walk is not muted | Pass. During a walk, `high_stress` + `thirst_critical`: stays `drink`, `panic_hide` absent from `_reflex_last_activation`. The next `alarm_call` at the same `sim_time` `5.0` hides and stamps cooldown `5.0` (the suppressed stress did not take it). Outside a walk, `high_stress` → `hide`, cooldown `8.0`, and a repeat at that moment is already `explore`. A separate `predator` reflex → `flee` during a walk clears it. In the colony profile `panic_hide` triggers are only `alarm_call` and `high_stress`; there is no separate threat event |
| 6 | A sleeper does not eat or drink; both `physiology_as_policy` modes | Pass. True and False: sleep at the bowl and at the waterer leaves stocks and hunger/thirst `0.9` unchanged. An awake animal eats at `bowl_pellets` (`0.994` / hay `1`) and from `wheel` only steps to `floor`, hunger stays `0.9` |
| 7 | `_bowl_crowd_conflict` does not count an animal that is only walking, outside the bowl zone | Pass. An eater in `bowl_pellets` and a walker in `floor` with `current_action=eat` and `_travel_action=eat`: the observer in the zone gets `0.15` (one extra; the walker is not counted). The same animal inside the zone: `0.30`. A lone walker in `floor`: `0` |
| 8 | `git diff origin/main -- src/` is empty | **Fail.** 6978 bytes, only `src/storage.py` (`+16/−53` toward HEAD). Not a PR edit: `git diff origin/main...HEAD -- src/` is empty. `main` has `b698959` (`fix(issue-87): save_agent and load_agent take every component from agent=`), and this branch does not. Merge-base is still `89c10a0` |
| 9 | The requested pytest, including the long files once | Pass. `103 passed`, `278.11` s, exit 0. A pygame `pkg_resources` warning, not a failure |
| 10 | Why sleep is about half | Pass as an explanation, not as a defect. See below |

Scenario probe for items 1–7: 34/34. The process then exited while printing the death registry, after those checks. The sleep rerun below finished on its own.

Pytest, exit 0:

```
SDL_VIDEODRIVER=dummy python3 -m pytest \
  "Demo/Colony chinchillas/tests/test_issue_80_travel_goal.py" \
  "Demo/Colony chinchillas/tests/test_issue_80_food_economy.py" \
  "Demo/Colony chinchillas/tests/test_nowa_agent.py" \
  "Demo/Colony chinchillas/tests/test_issue_79_contagion.py" \
  "Demo/Colony chinchillas/tests/test_resources.py" \
  "Demo/Colony chinchillas/tests/test_fix_colony_no_rest.py" \
  "Demo/Colony chinchillas/tests/test_colony_dt_invariance.py" -q --tb=line
```

`103 passed, 1 warning in 278.11s`

## Item 10 — why sleep is about half

Team-lead context, not reproduced here (16 agents, 1500 s, seeds 1 and 2, means): thirst `0.28` (before variant B `0.26`, on `53f7b17` `0.60`), hunger `0.30`, cortisol `0.24`, energy `0.97`, deaths `0`. Mean sleepers `1.2` versus `2.2` before variant B. `eat+drink` about 50% of ticks because of the walk.

Code. The walk does not replace an explicit `sleep`: in `_resolve_executed_action`, `sleep`, `alarm_call`, or another reflex clears the goal and returns immediately. Otherwise the hold substitutes `eat`/`drink` until one portion, an empty goal, or 15 s. With `physiology_as_policy=True` the homeostatic sleep force is not applied. `_finish_travel_goal` ends the walk only when stock actually fell or nothing is left to eat. If the animal is already at the bowl but hunger is below `HUNGER_AVAILABILITY_THRESHOLD` (`0.50`), or thirst is below `0.48`, `_try_acquire_resource` returns without a portion and the walk continues until timeout. Sleep before Process S `0.7` is still discarded in `_apply_sleep_recovery`. At `WAKEFULNESS_ACCUMULATION_FACTOR=30` and rate `1/(16*3600)`, `0.7` from zero is about `1344` s of continuous wakefulness.

Runs: 4 agents, `dt=0.25`, seed 1, product code unchanged.

From rest, 600 s: sleepers `0`, `eat+drink` `0.659`, travel `0.654`, mean hunger `0.290`, thirst `0.262`, energy `0.973`. Process S does not reach `0.7` in 600 s, so this window cannot compare `1.2` with `2.2`. Of 528 `_wake_from_sleep` calls, only 6 were a need (all thirst): the rest cancel a "sleep" chosen before onset.

Separate case: a walk started at hunger `0.2` from `floor`. On the first landing the animal is in `bowl_pellets`, pellets `1`, hunger `0.2`, and `_travel_action` stays `eat` across six `1.25` s steps.

With Process S set to `0.65` (so 600 s reaches the regime the 1500 s run enters after about 1344 s): mean sleepers `1.026` of 4 (`0.256` of ticks), `eat+drink` `0.227`, travel `0.224`, hunger `0.479`, thirst `0.557`, mean Process S `0.698`, max `0.819`. At `wake>=0.7` the core chose `sleep` 1498 times, 1482 of those were executed, 16 were replaced. Travel hold in that band: 846 ticks. Of 542 walk starts, 197 began below the bite gate.

Conclusion. The walk does not mute a `sleep` decision (16 of 1498 replaced). Sleep is lower because the approach, and especially a walk that never bites, holds `eat`/`drink` for up to 15 s instead of the single tick from before the bowl rule. On a rested start that is already 66% of ticks before onset. Thirst still sits near `0.26–0.28`: they do reach the waterer, they just spend the trip awake. That matches ~50% `eat+drink` and the drop `2.2 → 1.2` without a thirst increase. There is no separate sleep break.

## Defects

`[LOW]` The branch is behind `origin/main` `226e928` by `b698959` (`src/storage.py`, issue #87). `git diff origin/main -- src/` is not empty. The PR commits do not touch `src/`, and a three-way merge does not revert that core fix.

## Recommendations

Merge current `main` before landing this PR, so item 8 is empty. Walks that start below the bite gate sit out the 15 s timeout at a full bowl and inflate the `eat+drink` share; that is the item 10 explanation, not a checklist hole.

## Readiness

Yes for #80 behavior at `b955c38`. Item 8 is closed by merging `main`, not by editing the demo.
