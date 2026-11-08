# QA issue #18 — minor learning fixes

Branch: `team/issue-18-minor-learning-fixes`. Round 1 checked HEAD `6322391` (full `63223915c51a7a3e0637b1b4d8377757978eb5d9`).
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/63
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/18
Spec: [issue-18-minor-learning-fixes.en.md](../specs/issue-18-minor-learning-fixes.en.md).
Russian: [issue-18-minor-learning-fixes.ru.md](issue-18-minor-learning-fixes.ru.md).

Product commits on this slice: `da6509e` (feedback, sleep alpha, value bound), `b03baa7` (spec and Phase 5.0), `6322391` (Phase 5.0.1). This QA pass added the report only. No merge. No new PR.

Machine: Python 3.12.3, pytest 9.2.0. Probe ran with `NOWA_STRICT_LEARNING=1` and `PYTHONPATH=src`.

## Verdict

**PASS** (`6322391`).

`apply_feedback_to_last_experience(1.5)` stores `reward_signal` `0.75`. `0.7` stores `0.35`. Integer `2` stores `1.0`. `NaN` leaves the episode count and any existing reward unchanged (`updated=False`). `+inf` stores `+1`, `-inf` stores `-1`. Awake feedback leaves stable Q at `0`. Sleep is what moves it.

A new `ValueLayer` has `alpha_sleep_default == 0.0075`, which is `0.25 * alpha_online_default` (`0.03`). Constructor values `0.08` and `0.5`, and the same numbers assigned before sleep, resolve to `0.0075` during sleep. Save/load keeps `alpha_sleep_ratio` `0.1` on the layer and on `SleepManager`. An old value-layer dict and an old agent pickle that omit the key still load.

Repeated `reward=1` at `gamma=0.95` lifts `V` above `1` (peak `19.999977142975936` after 4000 steps) and stays at or under `20`. `reward_scale` stays `1.0`. Online `delta_clipped` stays inside `[-1, 1]` (`td_clip_online` stays `1.0`).

`sleep(cycles=3)` stable Q is `0.06551004180326182`. `sleep(cycles=2)` is `0.044164640181267326`. Both figures are the same after 10 episodes and after 80. The TD update, tonic/phasic dopamine, eligibility traces, and the two-tier split are still in the sleep and value paths. The core still stamps wall-clock time when a timestamp or `dt` is omitted, and `get_lifetime()` still follows the wall clock.

`python3 -m pytest -q tests`: **917 passed, 5 skipped**, exit 0, 212.47 s. That matches the count in the spec. Virtual company and Warriner tests, which import the repo core, with `-m "not slow and not perf"`: **844 passed, 7 skipped, 6 deselected**, exit 0, 3.75 s.

Two clamp edges are minor and do not change this verdict. They are written under Defects.

## Coverage

Scenarios: **12 passed / 0 failed / 2 not run**.

| # | Scenario | Result |
| --- | --- | --- |
| 1 | `1.5` → `0.75`, `0.7` → `0.35`, integer `2` → `1.0` | Pass. Stored reward and `feedback_rating` match |
| 2 | `NaN` writes no episode and does not rewrite an existing reward | Pass. `updated=False`, episode count `0→0`, existing reward stays `0.0` |
| 3 | `+inf` → `+1`, `-inf` → `-1` | Pass. Ratings `+2.0` and `-2.0` |
| 4 | Awake feedback leaves stable Q at `0`; sleep moves it | Pass. Q stays `0` through `1.5`, `0.7`, `2`, `+inf`, `-inf`. One sleep cycle then adds `0.022331671875` |
| 5 | New `ValueLayer`: `alpha_sleep_default == 0.0075` and `<= 0.25 * alpha_online` | Pass. Online `0.03`, ratio `0.25` |
| 6 | Explicit `0.08` and `0.5` stay inside the ratio during sleep | Pass. Resolver and one real `sleep(cycles=1)` both use `0.0075`. Q steps match the default |
| 7 | Save/load keeps `alpha_sleep_ratio`; old saves load | Pass. Ratio `0.1` and stored default `0.002` round-trip. Old dict and old pickle without the key load at ratio `0.25`; legacy `0.08` becomes `0.0075`; stored value `0.4` remains |
| 8 | Repeated `r=1`, `gamma=0.95`: `V` above `1`, never above `20`; `reward_scale` stays `1`; delta clip unchanged | Pass. Peak `19.999977142975936`, bound `19.999999999999982`, `reward_scale` `1.0`, max `abs(delta_clipped)` `1.0`, clip value `1.0`. A direct write of `100` stores the bound |
| 9 | `sleep(cycles=3)` stable Q about `0.066`; two cycles about `0.044` | Pass. `0.06551004180326182` and `0.044164640181267326` at both 10 and 80 episodes. Awake Q stays `0` |
| 10 | Biological learning path kept; core still uses wall-clock time | Pass. See evidence. Omitted `dt` takes the wall-clock fallback (`host_clock` `1.0` on the first step, `_last_step_time` set). `get_lifetime()` was `0.0515` s after a short wall wait. `ValueLayer.update` with `timestamp=None` stored a Unix `last_update_ts` |
| 11 | `python3 -m pytest -q tests` | **917 passed, 5 skipped**, 2 warnings, exit 0, 212.47 s. Warnings: pygame `pkg_resources`, and the swarm tick that skips a crashing agent |
| 12 | Virtual company and Warriner tests that import the repo core, `-m "not slow and not perf"` | **844 passed, 7 skipped, 6 deselected**, 10 warnings, exit 0, 3.75 s |

Not run:

| # | Scenario | Why |
| --- | --- | --- |
| 1 | Six Virtual company tests marked `slow` or `perf` in `test_sandbox_integration.py` | Marker filter. Deselected: three full-sandbox cycle tests and three performance-budget tests |
| 2 | Merge, and a second PR | Out of scope for this round |

Skipped inside the demo run, so they did execute collection: five Tk/Tcl GUI tests (no display), and `test_gui_configurator_controller.py` because Drive MCP is not published on localhost.

`git status` before this report: clean. This commit adds only the EN/RU QA pair.

## Defects

### [MINOR] A larger per-step gamma does not widen the stored V clamp

- **Steps**: 1) Build `ValueLayer(gamma_default=0.95)`. 2) Call `value_abs_bound(0.99)`. 3) Run 80 `update` steps with `reward=1`, `gamma=0.99`, `alpha=0.3`, `mode="online"`, `max_update_l2=1`, adaptive clip off.
- **Expected**: Spec section 4: `value_abs_bound()` tracks `gamma_default`, and a larger per-step `gamma` can widen the bound. `value_abs_bound(0.99)` is `99.99999999999991`.
- **Actual**: `update` calls `value_abs_bound()` with no gamma. `_get_value` and `_set_value` do the same. Stored `V` stops at `19.999999999999982`, the `gamma_default` bound.
- **Where**: `ValueLayer.update`, `ValueLayer._get_value`, `ValueLayer._set_value` in `src/value_layer.py`.
- **Severity**: minor

The requested case `gamma=0.95` does rise above `1` and stays within `20`. This edge is outside that case.

### [MINOR] An explicit sleep `value_cap` above the legacy unit clamp is not what the table stores

- **Steps**: 1) `ValueLayer()` with `SleepManager.value_cap = 10`. 2) Read `_resolved_value_cap()` at `gamma_default` `0.95` and at `0.5`. 3) `_set_value(..., 10)` at `gamma_default` `0.5`.
- **Expected**: Spec section 4 and acceptance item 4: legacy `value_cap = 1` rises to the gamma return bound, and a larger explicit cap (the example is `10`) is kept.
- **Actual**: At `gamma_default` `0.95`, `_resolved_value_cap()` is `19.999999999999982`, so `10` is lifted to the gamma bound. At `gamma_default` `0.5`, the resolver returns `10.0` and `value_abs_bound()` is `2.0`. `_set_value` then stores `2.0`. The unit test `test_sleep_value_cap_is_at_least_the_gamma_return` checks the resolver after setting gamma to `0.5`, so it stays green.
- **Where**: `SleepManager._resolved_value_cap` in `src/sleep.py`; `ValueLayer._set_value` in `src/value_layer.py`.
- **Severity**: minor

Phase 5.0 in this same branch states `|V| ≤ 1/(1−γ)`. The table follows that sentence. The example that keeps cap `10` does not hold for stored `V`.

No blocker, critical, or major defects.

## Known caveats (not FAIL)

| Topic | What was checked |
| --- | --- |
| Float bound at `γ = 0.95` | `discounted_value_bound(0.95, 1.0)` is `19.999999999999982`. The 4000-step peak stays under that value and under `20` |
| `> 0.05` after three sleep cycles | Measured Q is `0.06551`. Two cycles are `0.04416`, which fails `> 0.05`, so a missing cycle still fails `test_feedback_commits_one_td_update_and_reaches_the_reward` |
| First omitted `dt` | The first step with no previous stamp uses elapsed `1.0` and then records `time.time()`. That path is the existing wall-clock fallback |
| Spec digit `2` | The Russian problem row says «делением на 2». The English row says «halving». The other numeric tokens match |
| Demo `src/` copies | The spec says vendored copies keep the old quantization. This round ran the Virtual company and Warriner suites that import repo `src/` |

## Recommendations

- Leave the `gamma=0.95` ceiling and the sleep-alpha cap as they are for this merge.
- A later change that wants per-step `gamma` to widen stored `V` has to thread that gamma through `update`, `_set_value`, and `_get_value`, with a test that `gamma=0.99` can pass the default bound of `20`.
- Decide whether a `value_cap` above `1/(1−γ)` is stored. Today the resolver can return `10` at `γ = 0.5` while the table stores `2`. Align the issue spec example with Phase 5.0, or teach the table to keep the wider cap, and add a write/read test either way.

## Release readiness

**With caveats.** The checks requested for this round pass, both suites are green, and the EN/RU spec pair matches on every numeric token except the Russian word for halving. The two minor clamp notes are follow-ups. They do not block the fractional-rating, sleep-alpha, and `γ = 0.95` value-bound behavior.

## Questions / blockers

No blockers.

## Evidence

Symbols read with Serena (`get_symbols_overview`, `find_symbol` with `include_body`, `find_referencing_symbols`): `Agent._coerce_feedback_rating`, `Agent.apply_feedback_to_last_experience`, `Agent._apply_feedback_value_update`, `Agent._advance_host_clock`, `effective_alpha_sleep`, `derived_alpha_sleep`, `discounted_value_bound`, `ValueLayer.__post_init__`, `ValueLayer._resolve_alpha`, `ValueLayer.update`, `ValueLayer.value_abs_bound`, `ValueLayer.to_dict`, `ValueLayer.from_dict`, `ValueLayer._clip_update_delta`, `DopaminergicTDLayer.compute_td_error`, `SleepManager._resolved_alpha_sleep`, `SleepManager._resolved_value_cap`, `SleepManager._apply_replay_td_bg_unlocked`.

`_coerce_feedback_rating` keeps a finite rating as a float in `[-2, 2]` and sets `reward_signal = rating / 2`. `NaN`, `bool`, and non-numeric return `None`. `±inf` returns rating `±2` and reward `±1`. `apply_feedback_to_last_experience` returns before `_resolve_feedback_experience` when parsing fails, so no episode is created or rewritten. `_apply_feedback_value_update` calls `ValueLayer.update`, and that writer returns immediately when `assert_learning_allowed` is false, which is the waking state under `NOWA_STRICT_LEARNING=1`.

`ValueLayer.__post_init__` sets `alpha_sleep_default` through `effective_alpha_sleep` (`min` of the stored rate and `alpha_online * ratio`, ratio at most `0.25`). Sleep replay uses `_resolved_alpha_sleep`, which applies that helper again. A one-cycle sleep with stored `0.08`, stored `0.5`, and the derived default each moved Q by `0.022331671875`.

`to_dict` / `from_dict` persist `alpha_sleep_ratio` (default `0.25` when the key is absent). `AgentStorage` copies that field off the restored layer. A missing key on the sleep-manager blob is skipped, so the manager keeps its constructor value `0.25`.

Online TD still clips with `min(1.0, td_clip_online)` and `compute_td_error` still applies the stress dip and the tonic update. Sleep replay still scales by eligibility, credit weight, and the per-state variance gate, then clamps with `_resolved_value_cap` and again inside `_set_value`. `reward_scale` is multiplied into the reward and stayed `1.0` for the 4000-step run. The diff from `24c321e` to `6322391` does not remove those paths.

Wall clock, unchanged by this diff and still live: `ValueLayer.update` uses `time.time()` when `timestamp` is omitted; sleep replay assigns `value_layer.last_update_ts = time.time()`; `Agent._advance_host_clock` uses `time.time()` when `dt` is omitted and logs the one-time warning; `get_lifetime()` uses `time.time() - created_ts`.

Docs: `Docs/Phase_5_0_Value_Layer_RU_Spec` and `Docs/Phase_5_0_1_Value_Layer_RU_Spec` EN/RU numeric tokens match (`49` and `90` tokens). The issue spec pair is `124` lines each. The only numeric-token difference is the Russian «на 2» for halving.
