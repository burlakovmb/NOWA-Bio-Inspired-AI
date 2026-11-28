# QA issue #100 — colony action duration

Russian: [issue-100-colony-duration.ru.md](issue-100-colony-duration.ru.md).

Branch: `team/issue-100-colony-duration`. HEAD: `8a7b94b` (`8a7b94bbe88ce631a40f1e3cfa5eb4527969fdf0`). PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/101. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/100. Base: `main` `08930d8` (`08930d8e116ad19fb1fec5039b4cab75df617f33`), which is also the merge-base. Product code was not changed in this pass. No merge.

Machine: Linux, Python 3.12.3, pytest 9.2.0. CI on `8a7b94b`: GitHub Actions `pytest` run [46156597667](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/46156597667), **6 failed, 2386 passed, 12 skipped**, 244.35 s. The full suite was not re-run locally. The six failures were reproduced locally, and the tests this PR added or edited were run locally.

## Verdict

**FAIL**

The 120 s headless measurement matches the implementation note (46 action changes, completed medians inside the dataset ranges, eat median 22.25 s). `src/` is empty against `main`. Hold off restores a decision every tick. Danger, forced sleep, and the drive gates interrupt a hold.

The long run does not. At 1200 s, seed 42, `dt=0.25`, 4 agents, **3 of 4 die of exhaustion**. Once hunger and thirst are both in the penalty band, the hold of `eat` is cut by thirst and the hold of `drink` is cut by hunger, so the action that would stop the penalty cannot be held. 55.5% of bouts in that run last 0.5 s. CI is red: six existing tests still expect a per-tick episode or the old 40 s courtship window.

## Coverage

- scenarios: 7 passed / 2 failed / 0 not run

| # | Check | Result |
| --- | --- | --- |
| 1 | Seed 42, 4 agents, `dt=0.25`: 120 s and 600 s medians and survival; 1200 s survival and how often the hold collapses to 0.5 s | **Fail.** 120 s and 600 s match the note and nobody is dead. 1200 s: 3 exhaustion deaths, 259/467 bouts ≤ 0.5 s |
| 2 | `action_hold: false` decides every tick | Pass. 8/8 `step()` calls in the unit probe. 30 s colony: 440 action changes, mean dwell 0.27 s |
| 3 | Danger, forced sleep, hunger 0.61 / 0.91, thirst; the brain decides on the next tick | Pass. Hunger ≥ 0.60 and thirst ≥ 0.58 cut a `play` hold; 0.59 and 0.57 do not. Wake 0.90 cuts, 0.89 does not. Danger and drives call `step()` on the next tick. Forced sleep does not: the body enters need-sleep and the next tick skips `step()` |
| 4 | `dt=0.1` vs `0.25`, 60 s, seed 42 | Pass. Completed medians stay inside the dataset ranges. Largest gap is `groom_self` 29.3 vs 22.1 (n=2 and n=2) |
| 5 | Save/load of an active hold; an old save without the field | Pass for the timer. Remaining 19.75 s round-trips; a save with no `action_hold` key loads as hold 0 and no commit. Neuromodulator `dt` on the closing commit differs from a live bout (minor, below) |
| 6 | Loader: missing file, unknown action, crooked `duration` | Pass for the DoD fallback. Missing file and a non-list / one-element / non-numeric duration fall back to `(10, 30)` with one warning. `min>max` is swapped and kept. `0` and negatives are kept |
| 7 | `python3 -m colony_gui --headless` and `run_headless_ticks` | Pass. Both exit 0, `sim_time=00:00:02`, 4 agents |
| 8 | `git diff main -- src/` | Pass. 0 bytes |
| 9 | Each DoD item of issue #100 | **Fail** on "existing tests green". The 120 s eat median, interrupts, dt, the off switch, and untouched `src/` hold. Bilingual product docs are a later writer pass and are not in this PR |

Local pytest of the PR's colony tests plus the six CI failures: **6 failed, 30 passed**, 1.41 s. The 30 include `Demo/Colony chinchillas/tests/test_action_hold.py`, the three edited dt-invariance tests, `test_issue_80_travel_goal.py`, `test_knowledge.py::test_tc02_first_meeting_of_strangers`, and `test_nowa_agent.py::test_tc05_hippocampus_accumulates_experience`.

## What the 120 s run did

Same harness as `tests/test_action_hold.py::_measure`: seed 42, 120 s, `dt=0.25`, 4 agents, hold on. Action changes **46** (the note's 1512 → 46). Bouts 54, interrupted 36 (`drive:thirst` 24, `drive:hunger` 11, no interrupt reason 1). Nobody dead. Energies at the end: 0.7625, 0.92, 1.0, 0.9075.

Completed medians (dataset range in parentheses):

| Action | Completed | Median s | Dataset s |
| --- | --- | --- | --- |
| drink | 5 of 7 | 6.5 | 4–10 |
| eat | 2 of 11 | 22.25 | 8–60 |
| explore | 3 of 5 | 16 | 6–30 |
| groom_self | 3 of 6 | 26.75 | 2–30 |
| play | 1 of 6 | 38.25 | 6–40 |
| rest | 1 of 7 | 30 | 20–60 |
| socialize | 3 of 6 | 10 | 4–20 |
| hide | 0 of 3 | — | 10–240 |
| run_wheel | 0 of 3 | — | 10–80 |

Eat median 22.25 ≥ 10. Every completed median is inside its dataset range. `hide` and `run_wheel` have no completed bout, same as the note.

600 s, same seed: changes 262, bouts 294, interrupted 202 (`drive:thirst` 126, `drive:hunger` 71, no reason 5). Nobody dead. Lowest energy 0.2825. Completed medians still inside the ranges (`eat` 32.5, `drink` 6.75, `hide` 50.25 on 2 completed, `run_wheel` still none completed).

1200 s, same seed: **3 of 4 dead, cause `exhaustion`**, energies 0.0763, 0.0763, 0.0750, survivor 0.1600 (hunger 0.563, thirst 0.302, action `hide`). Bouts 467. 259 (55.5%) last ≤ 0.5 s. Of 316 interrupted bouts, 259 (82.0%) last ≤ 0.5 s; their median is 0.500 s and the minimum is 0.500 s. Completed bouts: 151, none ≤ 1 s, median 14.75 s, min 2.5 s, max 89.5 s. A per-tick colony would change action on the order of 4 × (1200 / 0.25) = 19200 times. 467 bouts is still far below that. The 0.5 s mass is the penalty band, not a return to every tick for the whole run.

`action_hold: false`, 30 s, seed 42, `dt=0.25`, 4 agents: 440 changes. There is no hold bout, because the off switch commits on the tick. Intervals where a change can be seen: 4 × 119 = 476. Mean dwell 30 × 4 / (440 + 4) = 0.27 s.

## Penalty band

Constants in code: thirst rises `0.0045/s` (`THIRST_ACCUMULATION_PER_S`), unmet thirst costs `0.025` energy/s from thirst ≥ `0.58` (`UNMET_THIRST_ENERGY_PER_S`, `THIRST_NEED_THRESHOLD`). Hunger is `0.0035/s` and `0.02` energy/s from `0.60`. Death is energy ≤ `0.05` (`MortalitySystem.critical_energy_threshold`).

From thirst `0.58` and energy `1.0`, penalty only, energy reaches `0.05` in `(1-0.05)/0.025 = 38` s. Thirst is then `0.58 + 0.0045×38 = 0.751`. To energy `0` it is `0.760`. A stuck `play` hold (the policy is pinned to `play`, so each interrupt starts `play` again) dies at sim time 54.75 s, thirst **0.743**, energy 0.075, cause `exhaustion`. The courtship pair below dies at thirst **0.731**. The note's ~0.73 is the right neighbourhood. Waiting for thirst `0.9` or hunger `0.9` would spend the animal first. A yield at `0.58` / `0.60` is justified.

The yield does not choose `drink` or `eat`. `physiology_as_policy` only adds a bias. And the two bands cancel each other:

- `eat` held, thirst set to `0.58`: interrupted, reason `drive:thirst`.
- `drink` held, hunger set to `0.60`: interrupted, reason `drive:hunger`.
- `eat` while hunger `0.61` and thirst `0.59`: interrupted, reason `drive:thirst`.

Hunger is checked first and does not exempt `drink`. Thirst does not exempt `eat`. When both needs are in band, neither relieving action can be held past the next tick. The decision tick still runs the motor once; the following tick cuts the hold (`motor=False`) and does not ask the brain until the tick after that. Measured length of those bouts is 0.5 s.

The K01 courtship pair (seed 11, `action_hold` true, the setup of `test_core_births_keep_generated_names_and_rest_does_not` without the rest couple) dies at **step 118**, cause `exhaustion`, energy 0.07, hunger 0.613, thirst 0.731, not pregnant, no offspring. With `action_hold` false the same setup has **3 offspring by step 3**.

Reward of one groom bout with per-tick rewards 0.2, 0.4, 0.6, 0.8 commits once, value **0.5**. One transition per bout holds for that probe.

## Save/load and the commit context

`ColonyStorage` writes `runtime.action_hold` from `export_action_hold`. A live hold of 19.75 s loads as 19.75 s, action `play`, commit action `play`. Stripping the key and loading resets `_action_hold_s` to 0 and `_hold_commit` to `None`.

A real `step()` stashes `step_elapsed=1.0` and `time_elapsed=0.25` (this tick's `dt`) and sets `_nm_use_host_dt=True`. `_advance_affect_while_awake` then writes both elapsed fields to **0.0** so the later commit does not integrate affect twice. The closing commit of that live bout calls `neuromodulators.update_from_signals` with **`dt=0.0`**.

After save/load the new agent has `_pending_commit_context is None`, `_nm_use_host_dt` unset, `_host_clock_s=0.0`. The hold timer is what was saved. The affect advance on the closing tick creates a pending dict with `step_elapsed=0.0` and `time_elapsed=0.0`. Because the host-dt flag is missing, `_commit_waking_transition` takes the legacy branch and integrates neuromodulators with **`dt=1.0`**. The decision's modulation dict is not in the save, so this commit does not reuse it.

The note said the post-load commit uses a new pending context with `step_elapsed` 1.0 and a neuromodulator `dt` of 0. Measured the other way around: elapsed fields are 0, neuromodulator `dt` is 1. The live commit is `dt=0`.

## Loader

`eat` → `eat_pellets` + `eat_hay`, union **(8, 60)**. Other colony ranges read from `scenario_datasets`: drink (4, 10), sleep (240, 960), groom_self (2, 30), run_wheel (10, 80), hide (10, 240), explore (6, 30), socialize (4, 20), play (6, 40), rest (20, 60), flee (4, 14).

Social offers come from `chinchilla_realizations_colony_social.json`, not from `SOCIAL_OFFER_TYPES.duration`. Examples: `sniff_greet` (3, 8) vs hardcoded 5; `allogroom` (10, 36) vs 30; `mount_display` (3, 10) vs 15.

Unknown action: `(10, 30)`, one warning, a second unknown action does not warn again. Missing file: `(10, 30)` for `eat`, one warning that names the file. A duration that is not a pair of finite numbers is skipped; if nothing remains, the same fallback warns once. `[30, 10]` is swapped to `(10, 30)` and stored, no warning. `[0, 0]`, `[-4, -1]`, and `[-2, 5]` are stored as those ranges.

## Tests that were edited

They were not loosened into vacuous checks.

- `test_colony_dt_invariance.py`: brain `step()` counts are equal at 1× and 10× and strictly below the tick count. `lived_steps` at old age, which increments inside `Agent.step`, is equal across speeds. Age and cause asserts are unchanged. The old `steps_1x > steps_10x` was the per-tick rate this issue retires.
- `test_issue_80_travel_goal.py`: the walk still arrives and drinks. The script `socialize` / `play` is still unconsumed during the drink bout. Policy mode takes one sip for the bout; the legacy body takes one sip per tick of the bout.
- `test_knowledge.py`: the meeting assert is the same. The loop is 60 ticks of 1 s so the greet can happen after the first held bout.
- `test_nowa_agent.py`: still asserts that the hippocampus gained at least one episode. The loop waits until that commit, up to 150 s, instead of five 0.1 s ticks that can no longer finish a bout.

`test_action_hold.py` covers the loader, one commit per bout, hold off, danger, forced sleep, hunger 0.5 vs 0.91, hunger 0.61, save/load of the timer, the 120 s eat median, and a 60 s dt comparison with a 50% relative tolerance. That tolerance would accept the `groom_self` gap above. The gap is small-n and both medians sit in (2, 30); it is not a failure.

## Defects

### [MAJOR] A long colony dies of exhaustion, and most bouts become 0.5 s

- **Steps**: 1) Run 4 agents, seed 42, `dt=0.25`, `action_hold` true, for 1200 s. 2) Separately, hold `eat` at the pellet bowl and set thirst to 0.58. 3) Hold `drink` at the waterer and set hunger to 0.60.
- **Expected**: The penalty-band yield lets the animal drink or eat before energy hits 0.05, and a long run does not replace dataset-length bouts with half-second switching.
- **Fact**: At 1200 s, 3 of 4 are dead (`exhaustion`). 259 of 467 bouts last 0.5 s (82% of interrupts). `eat` is interrupted by thirst ≥ 0.58. `drink` is interrupted by hunger ≥ 0.60. With both bands on, neither hold survives the next tick. The courtship female (seed 11, the PR-36 birth setup) dies at step 118, thirst 0.731, hunger 0.613, energy 0.07, no offspring. `action_hold` false on that setup bears 3 offspring by step 3.
- **Where**: `ChinchillaAgent._hold_interrupt_reason` (`Demo/Colony chinchillas/src/colony_agent.py`). Hunger is tested before thirst. `current != "eat"` does not exempt `drink`, and `current != "drink"` does not exempt `eat`.
- **Severity**: major

### [MAJOR] Six existing tests fail; CI on the PR is red

- **Steps**: 1) Open the `pytest` job on `8a7b94b` (run 46156597667). 2) Re-run the six tests locally.
- **Expected**: DoD: existing tests green, updated where they encode one episode per tick.
- **Fact**: CI: 6 failed, 2386 passed, 12 skipped. Locally the same six fail; the PR's new and edited colony tests pass (30).
  - `tests/test_k01_colony_ablation.py::test_policy_mode_does_not_force_eat_and_still_reports_reflexes` — `IndexError` at `experiences[-1]` (line 193). The action is already `hide`; the episode is committed at the end of the bout, not on the 0.1 s tick.
  - `tests/test_k02_decide_act_learn.py::test_colony_episode_follows_executed_outcome_not_pre_action_choice` — `IndexError` at line 120. `current_action` is `eat` and hunger has fallen; the episode is not stored yet.
  - `tests/test_qa_pr36_colony_core.py::test_colony_override_credits_hide_not_the_rest_choice` — `IndexError` at line 172, after `current_action == "hide"`.
  - `tests/test_qa_pr36_colony_core.py::test_reward_ignores_valence_and_is_scored_after_the_action` — `IndexError` at line 215, after the eat asserts.
  - `tests/test_k01_colony_ablation.py::test_rest_policy_loses_survival_and_reproduction_to_the_core` — line 210, `core.energy` is 0.300, not `> 0.5`. Core is alive after 30 steps (hunger 0.905, thirst 0.265, action `play`). Rest is dead of exhaustion at step 21, energy 0.055. The contrast "rest dies, core lives" still holds; the energy floor does not.
  - `tests/test_qa_pr36_colony_core.py::test_core_births_keep_generated_names_and_rest_does_not` — `births == []` after 40 steps. See the courtship death in the major defect above.
- **Where**: `tests/test_k01_colony_ablation.py`, `tests/test_k02_decide_act_learn.py`, `tests/test_qa_pr36_colony_core.py`. These files are not in the PR diff.
- **Severity**: major

### [MINOR] The commit that closes a restored hold integrates neuromodulators for 1 s

- **Steps**: 1) Let the brain `step()` once so a 20 s hold starts. 2) Save and load. 3) Finish the hold and record `update_from_signals(..., dt=)`. 4) Compare with a bout that is not saved.
- **Expected**: The note: a new pending context with `step_elapsed` 1.0 and neuromodulator `dt` 0.
- **Fact**: The live commit uses `dt=0.0` (`_nm_use_host_dt` true, elapsed fields already zeroed). The loaded agent has no pending context, no host-dt flag, and `_host_clock_s=0`. The closing commit uses `dt=1.0`. Pending elapsed at that commit is 0.0, not 1.0. The episode is still stored (1 experience, reason `completed`). The timer itself round-trips.
- **Where**: `ChinchillaAgent._advance_affect_while_awake` zeros elapsed fields. `export_action_hold` does not store `_pending_commit_context` or `_nm_use_host_dt`. `Agent._commit_waking_transition` uses `dt=1.0` when the flag is unset (`src/agent.py`, not modified).
- **Severity**: minor

## Recommendations

1. Fix the dual band before anything else. While thirst ≥ 0.58, do not cut `drink`. While hunger ≥ 0.60, do not cut `eat`. If both are in band, keep the worse one (thirst is the faster energy drain). Re-run seed 42 for 1200 s: zero exhaustion deaths, and the share of 0.5 s bouts should fall.
2. Update the six red tests. The four `IndexError`s need the episode after the bout ends, not after one 0.1 s tick. Re-baseline `core.energy > 0.5` only after the survival fix; 0.30 with hunger 0.905 is the animal playing instead of eating. The birth test should fail until the female no longer dies at step 118.
3. Add a regression that sets hunger and thirst together above the two bands and asserts that a drink or eat hold is not cut on the next tick, plus the 1200 s, seed 42, 4-agent exhaustion check.
4. The 50% band in `test_dt_invariant_action_lengths` is wide relative to the 60 s sample. Optional: compare a longer run, or assert each median is inside the dataset range the way the 120 s test does.
5. On load, either persist `_nm_use_host_dt` and the pending modulation, or commit the restored bout with `dt=0` the way a live bout does. Not a release blocker next to the deaths.
6. Crooked numeric durations are accepted (`0`, negatives, swapped `min>max`) with no warning. The DoD only requires a fallback for a missing file or action. A warning on a non-positive range would match the missing-file behaviour.

## Readiness

**No.** The 120 s acceptance numbers and the untouched core are in place. CI is red, and a 1200 s colony loses three animals to the penalty band the hold was widened to survive.
