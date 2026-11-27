# QA issue #96 — domain-neutral sandbox scenario

Branch: `team/issue-96-scenario`. First pass: `2a2046d`. Re-check: `f959f0a`, `815d2e9`. Baseline: `0e486e1` (`origin/main`). Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/96. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/99.
Russian: [issue-96-scenario.ru.md](issue-96-scenario.ru.md).

Machine: Linux, Python 3.12.3, pytest 9.2.0. CI workflow pins Python 3.12 (`.github/workflows/tests.yml`). Full suite was not re-run; the user reported CI green on `d79f516`.

## Verdict

**PASS** after the re-check of `f959f0a` and `815d2e9`. The first pass on `2a2046d` was FAIL. Both defects from that pass are closed. The first-pass text below is the record of what failed; the re-check is the current result.

Stages 1–4 are in the branch. `src/` is untouched. On `2a2046d` the committed golden did not measure the core agent: `tools/golden_issue_96.py` seeded unseeded `random.Random()` with a tuple, Python 3.12 rejected it, and `create_procurement_agent` returned `_FallbackAgent`. All five fixtures were that fallback.

## Coverage

- scenarios: 11 passed / 1 failed / 2 not run

| # | Check | Result |
| --- | --- | --- |
| 1 | Golden commit `5e5b165` parent is `0e486e1`; that commit adds only the tool, the test, and five fixtures | Pass |
| 2 | `--check` compares canonical JSON bytes (`sort_keys`, `allow_nan=False`), not `math.isclose` | Pass (test green; the bytes are the fallback) |
| 3 | 10-day and 90-day fixtures are the core agent | Fail, defect 1 |
| 4 | Same five slices with an int seed: `agent.Agent`, HEAD equals `0e486e1` (actions, supplier, product, qty, result, situation, price tokens, fitness, `cost_vs_chance`, graduation) | Pass (probe, not in the suite) |
| 5 | Lexicon guard reads the four generic modules and fails if `supplier` is inserted | Pass (insertion reverted, not committed) |
| 6 | YAML without `scenario:`, other `scenario.name`, `compute_stage_1a_baseline()` without `criteria`, old `carried_suppliers` / `price_memory` | Pass |
| 7 | `python -m nowa_sandbox.run_sandbox` one quarter, two days, seed 42 | Pass, exit 0 |
| 8 | Stage 4 logistics on the generic layer, real agent, two fresh processes | Pass, twice |
| 9 | `last_decision_log`, `n_orders`, quote-book shape | Pass as limits, not defects (below) |
| 10 | `git diff origin/main...HEAD -- src/` | Pass, empty |
| 11 | New tests twice; int-seed probe twice for seed 42, price on | Pass, identical |

Not run: GUI (call site in `gui_controller.py` still builds `SandboxTrainer` with the same arguments). Full pytest.

Neighbor run, `-m "not slow"`: `test_issue_96_golden`, `test_issue_96_scenario`, `test_logistics_scenario`, `test_sandbox_config`, `test_stage_baseline`, `test_price_perception`, `test_graduation_non_regression`, `test_staged_graduation`, `test_sandbox_checkpoint`, `test_persistent_suppliers`. Result: `189 passed in 1.95s`. The new files alone: `14 passed` twice (`1.01s`, `1.00s`).

## What the golden actually records

`_install_freeze` in `Demo/Virtual company/tools/golden_issue_96.py` replaces `random.Random`. An unseeded constructor sets the seed to `(42, n)`. On Python 3.12.3:

```text
TypeError: The only supported seed types are: None,
int, float, str, bytes, and bytearray.
```

Trace under that freeze, before any quarter runs:

```text
agent_factory.py:301 SleepManager(...)
sleep.py:293 self._rng = random.Random()
golden_issue_96.py seed((42, n))
```

`sandbox_agent_factory._create_core_agent` catches `Exception` and returns `None`. `create_procurement_agent` then builds `_create_fallback_agent.<locals>._FallbackAgent`. The worker calls `_install_freeze` before `capture_case`, and `capture_case` calls `create_procurement_agent`. The committed fixtures were written by that worker (`5e5b165` adds the tool and the fixtures together).

`_FallbackAgent.step` only returns `wait_and_monitor`, `urgent_reorder`, or `diversify_supplier`. The fixtures never leave the first of those.

| Slice | Fixture | Core agent, int seed (HEAD = `0e486e1`) |
| --- | --- | --- |
| seed 42, price on, 10 days × 2 | 20 × `wait_and_monitor`, 0 placed, `cost_vs_chance` 0.0, `cost_efficiency` 0.5 | Q1: 6 placed, `cost_vs_chance` -0.05331208452168168, `cost_efficiency` 0.310122846568195; actions include `place_order_cheap_supplier` |
| seed 42, price on, 90 days × 1 | 90 × `wait_and_monitor`, 0 placed, `cost_vs_chance` 0.0, `cost_efficiency` 0.5 | 34 placed, `cost_vs_chance` -0.09060087344927437, `cost_efficiency` 0.2728340576406023; mix `diversify_supplier` 30, `place_order_cheap_supplier` 24, `urgent_reorder` 19, `place_order_reliable_supplier` 9, `wait_and_monitor` 8 |

Without the freeze, `create_procurement_agent` returns `agent.Agent`. The normal CLI path is not stuck on the fallback. The silent `except` in `_create_core_agent` is older than this PR (`sandbox_agent_factory.py` is not in the diff). The new freeze is what trips it.

`tests/logistics_scenario.py` already avoids the tuple (`FROZEN_RANDOM_SEED * 1_000_003 + counter`) and its two-period journal repeats. That path does create the core agent.

## Defects

### [CRITICAL] Golden slice records the fallback buyer, so the gate does not protect the core

- **Steps**: 1) On Python 3.12 run `Demo/Virtual company/tools/golden_issue_96.py` worker (`_install_freeze` then `capture_case`). 2) Print the class from `create_procurement_agent`. 3) Read `tests/fixtures/issue_96_golden/*.json`. 4) Repeat the same slices with an int seed for unseeded `random.Random()` against `0e486e1` and against HEAD.
- **Expected**: Fixtures are the core agent. Fitness, `cost_vs_chance`, graduation, and decision-log action / supplier / product / qty / result (and price tokens) match that agent.
- **Actual**: The worker creates `_FallbackAgent`. Every fixture row is `wait_and_monitor` with null supplier, product, qty, and result. `cost_vs_chance` is 0.0. `--check` still passes, because the replay uses the same freeze. An int seed yields `agent.Agent`, places orders, and matches `0e486e1` on all five slices; those numbers are not the fixture bytes.
- **Where**: `Demo/Virtual company/tools/golden_issue_96.py` (`_FrozenRandom`), triggered through `src/sleep.py` and swallowed by `Demo/Virtual company/src/nowa_sandbox/sandbox_agent_factory.py` (`_create_core_agent`).
- **Severity**: critical

### [MINOR] Buyer criterion names sit in the generic trainer, and the guard does not see them

- **Steps**: 1) Search `scenario_trainer.py` for `stockout_avoidance` and `supplier_diversification`. 2) Apply the guard regex `\b(place_order|supplier|product|stock|price|sku|procurement)\b` to those stems. 3) Insert a bare `supplier` into `scenario.py` and run `TestLexiconGuard`.
- **Expected**: The generic trainer does not name the six buyer criteria. The guard fails on buyer words in the four modules.
- **Actual**: `_fitness_summary` lists the six buyer criteria and uses them when the fitness object has all six attributes. The regex does not match `stockout_avoidance` or `supplier_diversification` (`\b` does not split `_`, and `stock` is not a whole word inside `stockout`). A bare `supplier` in `scenario.py` fails the test: `scenario.py contains 'supplier'`. Logistics fitness lacks the six attributes, so its summary uses `as_dict()` (`on_time_share=` is asserted).
- **Where**: `Demo/Virtual company/src/nowa_sandbox/scenario_trainer.py` (`_fitness_summary`); `Demo/Virtual company/tests/test_issue_96_scenario.py` (`FORBIDDEN`).
- **Severity**: minor

## Stage 4 notes (not defects)

- `last_decision_log` is replaced each period (`scenario_trainer.py`, assignment after `_run_single_quarter`). The same assignment is on `0e486e1` at `training_loop.py:343`. The golden tool already loops one quarter at a time. Logistics keeps its own `journal`. Pre-existing limit.
- `graduation_report` copies `n_orders` (`getattr`, default 0). Procurement reports already had that field (`test_staged_graduation.py` asserts it). Logistics sets it to the accepted-assignment count and asserts `2`. A domain that omits the attribute gets 0. The name is buyer-flavored; it does not block the second domain.
- `collect_values` / `band_token` / `observe_day` still walk a counterparty book: nested map, `status == "ok"`, then the numeric field. Logistics passes `nested_field="quotes"` and `value_field="unit_cost"` and does not edit the generic modules. Stage 4's proof holds. The book shape is tighter than "a number on an entity".

## Other checks

- Absent `scenario:`: `scenario is None`, stage `1a`, `price_perception` true, `supplier_set_count` 4, unknown threshold `telepathy` dropped (`TestScenarioConfig` and a one-off YAML).
- `scenario.name: dispatch` keeps `on_time` / `telepathy` and stage `beta`.
- `compute_stage_1a_baseline(quarters)` with no `criteria` still fills `STAGE_1A_CRITERIA` (`test_covers_exactly_the_stage_1a_criteria`).
- `restore_checkpoint_metadata` reads `carried_suppliers` and `price_memory`. An old document `{"skus": {"product_000": {"ema": 1.5, "spread": 0.2}}}` restores that reference. A metadata dict without `price_memory` leaves the memory empty. `checkpoint_metadata()` still writes those two keys.
- Empty book and a non-finite paid value leave `NumericMemory` empty. `band_token` with no quotes is `cost:R7:average`.
- `PriceMemory` remains a thin binding (`unit_price`, `price:`, `product:`, record key `skus`).
- CLI and GUI still construct `SandboxTrainer` with the pre-refactor arguments. CLI smoke: `--quarters 1 --days-per-quarter 2 --seed 42 --stage 1a --no-stop-on-graduation --quiet`, exit 0. GUI was not clicked.

## Re-check

Fixes under test: `f959f0a` (integer seed `42 * 1_000_003 + n`, worker refuses a fallback, five fixtures recaptured) and `815d2e9` (buyer summary line moved to `ProcurementScenario.fitness_line`, guard matches stems inside identifiers). Machine: Linux, Python 3.12.3, pytest 9.2.0. Product code was not edited during this pass.

- scenarios: 6 passed / 0 failed / 2 not run

| # | Check | Result |
| --- | --- | --- |
| 1 | Copy the fixed `tools/golden_issue_96.py` onto a clean `0e486e1` worktree and `--write --include-long` | Pass. stderr is `core-agent agent.Agent` on all five slices |
| 2 | `cmp` those five files with the fixtures committed on the branch | Pass, byte-identical (8096, 6314, 7823, 6320, 26256 bytes) |
| 3 | `--check --include-long` on HEAD | Pass, exit 0, five `ok`, each worker prints `core-agent agent.Agent` |
| 4 | Put the tuple seed back, run `test_issue_96_golden_matches_fixtures`, restore the file | Pass as a negative check. The test failed in 0.65s: `RuntimeError: golden slice requires core agent.Agent, got nowa_sandbox.sandbox_agent_factory._FallbackAgent`. Not committed |
| 5 | Append `supplier_diversification`, then `stockout_avoidance`, to `scenario_trainer.py` and run the guard | Pass as a negative check. Failures: `scenario_trainer.py contains 'supplier'` and `contains 'stockout'`. Both insertions reverted |
| 6 | Buyer `summary()` for seed 42, price on, 10 days × 2, integer freeze, HEAD vs `0e486e1` | Pass, `cmp` identical |

The 90-day file recaptured on `0e486e1` is the core buyer: 34 placed orders, `cost_efficiency` 0.2728340576406023, `cost_vs_chance` -0.09060087344927437, mix `diversify_supplier` 30, `place_order_cheap_supplier` 24, `urgent_reorder` 19, `place_order_reliable_supplier` 9, `wait_and_monitor` 8.

Identical summary text:

```text
=== Sandbox Training Summary ===
Quarter 1: [...] cost_eff=0.31 stockout_avoid=1.00 budget_disc=1.00 diversif=0.80 consist=0.50 risk_react=1.00 qualifying_streak=0
Quarter 2: [...] cost_eff=0.33 stockout_avoid=1.00 budget_disc=1.00 diversif=0.85 consist=0.50 risk_react=1.00 qualifying_streak=0

NOT YET GRADUATED - continue training
```

Targeted pytest, `-m "not slow"`, the three issue-96 modules plus config, stage baseline, price perception, graduation, checkpoint, and persistent suppliers: `191 passed in 3.28s`. That includes the logistician. CLI: `python -m nowa_sandbox.run_sandbox --quarters 1 --seed 42 --stage 1a --no-stop-on-graduation --quiet`, exit 0, one quarter, `n_days` 90.

Not run: GUI. Full pytest (CI not waited on).

## Recommendations

- The two defects from the first pass are closed. No further product change is required for them.
- Quote-book shape, `n_orders`, and `last_decision_log` stay accepted limits.
- GUI was not clicked on this pass. The two fix commits do not touch it.

## Release readiness

- yes, with the limit that this pass did not click the GUI and did not run the full suite. The golden gate now watches the core agent, and the buyer summary line matches `0e486e1` on the probed slice.
