# QA issue #76 task 1 — option A, cost floor at least δ

Branch: `team/vc76-fair-1b`. Commit under test: `01bd07460cf67dd39c28fbaff21e2a43d4dee785` (`fix(issue-76): keep the stage 1b cost floor at least delta`). Parent: `b35676a`. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/91. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/76.
Russian: [issue-76-task1-optionA-qa.ru.md](issue-76-task1-optionA-qa.ru.md).

Scope is that commit only (option A). The parent commit that introduced `cost_vs_chance` is out of scope. No simulation seed runs. Product code was not changed.

Machine: Linux, Python 3.12.3, pytest 9.2.0. Demo tests insert `Demo/Virtual company/src` and the repo `src/` via `Demo/Virtual company/tests/conftest.py`.

## Verdict

**PASS.**

The Stage 1b cost guard is `max(min(0.9*median, median-IQR), δ)` with δ = `stage_baseline.cost_vs_chance_floor_delta`, default 0.03, clamped to 0.02–0.05. A chance-level `cost_vs_chance` of 0 does not pass a near-zero or negative baseline. When both `0.9*median` and `median-IQR` are above δ, the floor stays on the previous statistical value. Other criteria keep the previous floor. `src/` is untouched. The targeted tests pass.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | Formula in `stage_baseline.non_regression_floor` and use in `ProcurementFitnessEvaluator.check_non_regression` | Pass. `base_multiplier` is `NON_REGRESSION_FLOOR` (0.9). `lower_bound` is the clamped δ. Display helper `nr_floors_from_baseline` calls the same function |
| 2 | Boundaries: median < 0, IQR = 0, IQR > median, empty baseline | Pass, table 1. Guard and displayed floor matched on every row. A raw criterion still clips at 0: `non_regression_floor(0.1, 0.5)` is 0.0, and the stockout floor for median 0.9 / IQR 0 stayed 0.81 |
| 3 | δ from YAML, missing key, out of range, non-numeric; old baseline and checkpoint without δ | Pass, table 2. Shipped `configs/default_world.yaml` is 0.03. `SandboxConfig.load(None)` is 0.03 |
| 4 | `run_sandbox.py`, `gui_controller.py`, `gui_app.py`, `quarter_diagnostics.py`, `sandbox_config.py` | Pass. Diff is δ plumbing and the cost-floor display. Resume, seeding, supplier carry, and the other config sections are unchanged. Round-trip of `default_world.yaml` through `to_dict` / `from_mapping` is equal |
| 5 | `src/` and hardcoded agent preferences | Pass. `git diff main...HEAD -- src/` and `git diff 01bd074^..01bd074 -- src/` are empty. `git diff 01bd074^..01bd074 -G 'preference\|intuition\|prior\|bias\|reward'` is empty. `seed_intuition` is not in the diff |
| 6 | Tests: random with baseline ≈ 0 fails; both terms > δ keeps the old floor; δ comes from config | Pass. Names below. Full targeted run: 176 passed, 1 skipped, 1.64s |

Table 1 — probe of `non_regression_floor(..., lower_bound=0.03)` against `max(min(0.9*median, median-IQR), 0.03)`. Negative IQR is clamped to 0 before the formula, same as the loader. `cost_vs_chance = 0` is the chance level. `passes` is `check_non_regression` for `cost_efficiency`.

| Case | median | IQR | statistical | floor | 0 passes |
| --- | --- | --- | --- | --- | --- |
| median < 0 | -0.08 | 0.02 | -0.10 | 0.03 | no |
| median < 0, IQR = 0 | -0.08 | 0 | -0.08 | 0.03 | no |
| IQR = 0, high median | 0.40 | 0 | 0.36 | 0.36 | no |
| IQR = 0, near zero | 0.02 | 0 | 0.018 | 0.03 | no |
| IQR > median | 0.10 | 0.25 | -0.15 | 0.03 | no |
| IQR > median, high median | 0.50 | 0.60 | -0.10 | 0.03 | no |
| both terms > δ | 0.40 | 0.05 | 0.35 | 0.35 | no |
| both zero | 0 | 0 | 0 | 0.03 | no |
| baseline ≈ 0 | 0.001 | 0.004 | -0.003 | 0.03 | no |

On the “both terms > δ” row, `cost_vs_chance` 0.01 below 0.35 fails and 0.01 above passes. `budget_discipline` and `stockout_avoidance` stay passing. Raising δ to 0.04 does not move that boundary, because 0.35 > 0.04. With median 0 and IQR 0, `cost_vs_chance` 0.035 passes at δ 0.02 and fails at δ 0.05, so the configured value is the one the guard uses.

Empty baseline:

- `compute_stage_1a_baseline([])` raises `ValueError`.
- `check_non_regression` on `{}` reports all four Stage 1a criteria passing (missing data, δ not applied). `nr_floors_from_baseline({})` is `{}`.
- 15 quarters with no `cost_vs_chance` omit `cost_vs_chance_median` and `cost_vs_chance_iqr`. The raw cost check remains: cost 0.5 against baseline 0.8 fails (`0.5 < 0.8*0.9`), cost 0.9 passes. δ is not applied.
- `{}` as a baseline file raises `ValueError`. A bare criterion map loads and has no normalized keys.

Table 2 — `SandboxConfig.from_mapping` / YAML.

| Input | δ |
| --- | --- |
| missing `stage_baseline`, missing key, null, `abc`, `''`, `.nan`, `.inf`, `[0.04]` | 0.03 |
| 0.01 | 0.02 |
| 0.2 | 0.05 |
| 0.02, 0.05, 0.04, `'0.04'` | 0.02, 0.05, 0.04, 0.04 |
| shipped `default_world.yaml`, `SandboxConfig.load(None)` | 0.03 |

`ProcurementFitnessEvaluator(cost_vs_chance_floor_delta=...)` clamps the same way: 0.01 → 0.02, 0.9 → 0.05, `"nope"` → 0.03, `None` → 0.03.

Old files: a baseline JSON with `cost_vs_chance_median` / `cost_vs_chance_iqr` and no δ key loads both numbers and does not invent a δ field. A checkpoint written with `dump_state` (`format` `nowa-sandbox-checkpoint`, schema 2) and no δ key loads: `last_quarter` 2, `world_summary.cost_vs_chance` 0.01, fitness 0.4. δ is read from the current config at resume, not from the checkpoint.

`gui_app.SandboxLabApp._refresh_nr_floors` (no window): a baseline with median 0 and IQR 0.05 plus YAML δ 0.04 displays cost floor 0.04 and stockout floor 0.81. An empty config path displays 0.03. A missing baseline path keeps `controller.last_nr_floors`.

Tests that lock the three required cases:

- `TestNormalizedCostGuard.test_random_policy_fails_near_zero_baseline_because_of_delta` — median 0, IQR 0.05, `cost_vs_chance` 0 fails; stockout still passes.
- `TestNormalizedCostGuard.test_floor_matches_previous_formula_when_both_terms_exceed_delta` and `TestNormalizedSavingsBaseline.test_floor_unchanged_when_both_terms_exceed_delta` — median 0.40, IQR 0.05, floor `min(0.36, 0.35)`.
- `TestCostVsChanceFloorDelta.test_delta_is_read_from_config` — shipped 0.03, YAML 0.04 stored on the evaluator, 0.01 clamped to 0.02, 0.2 clamped to 0.05.
- `test_old_baseline_file_loads_and_keeps_the_raw_cost_guard` — pre-normalized baseline file, raw cost check.

```
python3 -m pytest -q --no-header -rs -p no:warnings \
  "Demo/Virtual company/tests/test_baseline_methodology.py" \
  "Demo/Virtual company/tests/test_graduation_non_regression.py" \
  "Demo/Virtual company/tests/test_sandbox_config.py" \
  "Demo/Virtual company/tests/test_stage_baseline.py" \
  "Demo/Virtual company/tests/test_stage_baseline_strictness.py" \
  "Demo/Virtual company/tests/test_procurement_fitness.py" \
  "Demo/Virtual company/tests/test_gui_controller.py" \
  "Demo/Virtual company/tests/test_run_sandbox.py"
```

`176 passed, 1 skipped in 1.64s`. Skip: `test_gui_controller.py::TestFitnessChartSmoke::test_set_data_and_clear` — Tk/Tcl is not usable here. The other `test_gui_controller` and `test_run_sandbox` tests passed, including checkpoint resume.

## Defects

None.

## Recommendations

- The unit tests do not lock median < 0, IQR = 0, IQR > median, the empty baseline, a missing YAML key, or a non-numeric value. The probe above did. A later edit can drop one of those without a red test.
- `test_delta_is_read_from_config` checks the stored attribute. It does not show that 0.035 passes at δ 0.02 and fails at δ 0.05. The probe did.
- YAML `true` / `yes` becomes 0.05, not 0.03. PyYAML parses them as booleans, and `float(True)` is 1.0, which then clamps to the top of the band. Strings, null, NaN, and inf fall back to 0.03. The result stays inside 0.02–0.05 and makes the floor stricter, so a chance-level policy still fails.
- If the baseline file loads but the config file does not, `_refresh_nr_floors` displays δ 0.03 instead of `controller.last_nr_floors`. The training path does not use that refresh; it uses the config object already loaded for the run.
