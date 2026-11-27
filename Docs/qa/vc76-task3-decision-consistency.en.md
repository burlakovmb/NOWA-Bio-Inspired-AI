# QA issue #76 task 3 — decision consistency

Branch: `team/vc76-consistency-3`. Commit under test: `efb0bc64bfdc425018dc07101e0081ca4e2616b0` (`Bind decision consistency to the action and set the threshold to 0.79`), which includes `5fc25f00ca37d3df9dbec28a4e74e93633bb52f9`. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/97. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/76.
Russian: [vc76-task3-decision-consistency.ru.md](vc76-task3-decision-consistency.ru.md).

Scope is that head, and only the narrow checklist for `Demo/Virtual company/`. Product code was not changed. The team-lead calibration (5 seeds, Stage 1b, random 4% of quarters, always-cheap 98%) was not repeated. CI was not waited on.

Machine: Linux, Python 3.12.3, pytest 9.2.0. Demo tests insert `Demo/Virtual company/src` and the repo `src/` via `Demo/Virtual company/tests/conftest.py`. Live numbers below come from a one-off probe that was not committed.

## Verdict

**PASS.**

On a real encoder day with `P1` and `P10` both below the reorder point, each situation is that SKU's `product:` token, its own `price:` token, and `status:below_reorder_point`. `P1` does not take `P10`'s tokens. A real `event:` token and `budget:critical` placed between `product:` and `status:` leave the status off the entity. `--no-price-perception` removes every `price:` token from the context and from the situation. `choice` is the strategy string passed into `resolve`, including after `OrderParams.strategy` is overwritten. Days without an order store `entity=None` and `situation=[]` and stay out of the score. World rejections (`insufficient_budget`) stay out; accepted rows stay in. A YAML file with no `consistency` section loads `DEFAULT_CONSISTENCY`. `choice_field: supplier_id` changes the score from 1.0 to 0.5 on the same alternating-supplier run. That config object reaches the evaluator and the trainer from `run_sandbox.main` and from `RunController._execute_run`. Stage 1b graduation on the evaluator `main` built uses 0.79: 0.789 fails, 0.79 passes, and the old 0.60 bar fails. `decision_consistency.py` has no procurement words, and the logistics test asserts concrete tokens and a score that diverges from the old by-entity mean. `pytest` on `Demo/Virtual company/tests` is green. `git diff origin/main...HEAD` does not touch `src/`, the encoder, the reward functions, the motor, or `price_memory.py`. A 90-day `situation` list is at most 3 tokens.

## Coverage

22 probe checks, 0 failed. Full demo suite: 1023 passed, 7 skipped, exit 0.

| # | Check | Result |
| --- | --- | --- |
| 1 | Two SKUs, real encoder: no cross-product `status:` / `price:` leak; `P1` vs `P10`; `budget:` and `event:` break attachment; `--no-price-perception` | Pass |
| 2 | `choice` is the strategy passed to the motor; idle rows are empty and uncounted; rejected rows stay accepted-only | Pass |
| 3 | Legacy YAML defaults; `choice_field: supplier_id` switches the metric; CLI and GUI deliver the config; Stage 1b uses 0.79 | Pass |
| 4 | No procurement words in `decision_consistency.py`; logistics test is not a tautology | Pass |
| 5 | Full demo pytest; diff leaves core, encoder, reward, motor, `price_memory`; `situation` stays a short list | Pass |

### 1. Situation on encoder output

World built with `ProcurementWorld.from_quarter_spec`: products `P1`, `P10` (stock 0, reorder point 100) and `other` (stock 5000, reorder point 10), two suppliers, budget left at 1% of the allocation, history holding a demand shock and a late arrival. Context comes from `SandboxEncoder.encode_daily_context` on `SandboxTrainer._prepare_stock_observation` and `_prepare_supplier_observation`, with `price_perception=True`.

Emitted tokens, in order:

`event:demand_shock`, `valence:negative`, `domain:procurement`, `domain:novelty`, `event:order_arrived_late`, `valence:negative`, `domain:procurement`, `domain:risk`, `product:P1`, `status:below_reorder_point`, `price:P1:average`, `product:P10`, `status:below_reorder_point`, `price:P10:average`, `budget:critical`.

`situation_tokens(..., attached_prefixes=("status:",))`:

| Entity | Situation |
| --- | --- |
| `P1` | `price:P1:average`, `product:P1`, `status:below_reorder_point` |
| `P10` | `price:P10:average`, `product:P10`, `status:below_reorder_point` |

`other` produces no token. `P1` is a substring of `P10` and of `price:P10:average`; the field split still keeps the two situations apart.

The encoder writes events first and `budget:critical` last, so in this natural order `status:` still follows its `product:`. Taking those same emitted tokens and placing `event:demand_shock` or `budget:critical` between `product:P1` and `status:below_reorder_point` leaves the situation as `("product:P1",)`.

With `price_perception=False` on the same world the context and both situations contain `product:` and `status:below_reorder_point` and no token that starts with `price:`. `resolve_config` on `configs/default_world.yaml` keeps `training.price_perception` true; the same file plus `--no-price-perception` sets it false. `run_sandbox.main` with that flag built a trainer whose `price_perception` is false. That 3-day Stage 1b run placed no order, so its stored situations were empty.

### 2. Choice, idle days, rejected orders

Scripted brain, 16 days, actions alternating `wait_and_monitor` and `place_order_cheap_supplier`. The motor wrapper records the `action_type` argument of `resolve`. Every ordered row has `choice == action ==` that argument (`place_order_cheap_supplier`), and `choice` differs from `supplier_id` (`S1`). The situation on the row equals `situation_tokens` of the context list captured inside `step` for that day. After each `step` the brain sets `last_intent` to `RECOMPUTED_LATER`; `choice` stays the returned strategy.

A second run overwrites `OrderParams.strategy` to `NOT_THE_ARGUMENT` after `resolve` returns. The strategy field before the overwrite is `place_order_cheap_supplier`. The logged `choice` is still `place_order_cheap_supplier`.

An idle row is `action=wait_and_monitor`, `supplier_id=None`, `product_id=None`, `qty=None`, `confidence=None`, `result=None`, `tool=None`, `entity=None`, `choice=None`, `situation=[]`. Eight idle rows. Dropping them leaves `value`, `decisions_used`, and `situations_used` unchanged.

Every second `place_order` ran with `budget` forced to 0 and then restored. The world returned `status=rejected`, `reason=insufficient_budget` (4 rejected, 4 accepted). The report on the full log equals the report on the accepted rows alone. Three copies of one accepted row score 1.0 with `decisions_used=3`. The same three rows marked rejected score the neutral 0.5 with `decisions_used=0`. Accepted plus rejected still uses 3 and scores 1.0.

### 3. Config and the 0.79 gate

`configs/default_world.yaml` with the `consistency:` section removed loads `DEFAULT_CONSISTENCY`: `entity_field=product_id`, `choice_field=action`, `attached_prefixes=("status:",)`, `counted_statuses=("accepted",)`, `min_decisions=3`, `neutral=0.5`, and `graduation_thresholds.decision_consistency=0.79` from the threshold key that remains. A file that is only `world.n_products: 4` loads the same consistency default and 0.79. A file that sets only `consistency.choice_field: supplier_id` keeps the other consistency defaults.

Eight accepted orders, one repeated situation `["product:P1", "status:below_reorder_point"]`, action always `place_order_cheap_supplier`, supplier alternating `S1`/`S2`, `price_perception` off:

| `choice_field` | Stored `choice` | `decision_consistency` | `decision_consistency_by_product` | decisions used |
| --- | --- | --- | --- | --- |
| `action` | the action, eight times | 1.0 | 0.5 | 8 |
| `supplier_id` | `S1`, `S2`, … | 0.5 | 0.5 | 8 |

Old rows that have `action` and `supplier_id` and no `choice` key score 1.0 under `choice_field=action` and 0.5 under `choice_field=supplier_id`.

`run_sandbox.main` (`--stage 1b`, `--choice` via a YAML `choice_field: supplier_id`, `--no-price-perception`, 1 quarter, 3 days, exit 0) constructed the evaluator and the trainer with one shared config: `choice_field=supplier_id`, `price_perception=False`, stage `1b`, threshold 0.79. The quarter summary in the run's JSON contains `decision_consistency_by_product`, `decision_consistency_situations`, and `decision_consistency_decisions_used`.

`RunController._execute_run` (headless, no Tk window) on a YAML with `choice_field: supplier_id` put that field on both the evaluator and the trainer. `last_thresholds["decision_consistency"]` is 0.79.

Graduation on the Stage 1b evaluator `main` built, other criteria held at 1.0:

| `decision_consistency` | criterion passed | `all_passed` |
| --- | --- | --- |
| 0.789 | false | false |
| 0.79 | true | true |
| 0.60 | false | false |

Stage 1a with the same threshold table and `decision_consistency=0.10` records the criterion as not gating and `all_passed` true.

A YAML that still sets `graduation_thresholds.decision_consistency: 0.60` and has no `consistency` section loads threshold 0.60 and the default binding. On a Stage 1b evaluator built from that file, 0.70 passes. The shipped file and `GRADUATION_THRESHOLDS` are 0.79.

### 4. Domain neutrality

`decision_consistency.py` has no match for `product`, `supplier`, `price`, `stock`, `procurement`, `purchase`, `заказ`, `поставщик`, `товар`, or `цена`.

`Demo/Virtual company/tests/test_decision_consistency.py` asserts literals. `situation_tokens(["route:R10", "status:delayed"], "R1", ("status:",))` is empty. An `event:quiet_day` between `route:R7` and `status:delayed` leaves `("route:R7",)`. Two situations on route `R7` with different carriers score `value == 1.0` while `by_entity_legacy < 1.0`. The test does not compare `situation_tokens(...)` to itself.

### 5. Regressions

```
python3 -m pytest -q "Demo/Virtual company/tests" --tb=line -p no:cacheprovider
```

`1023 passed, 7 skipped, 10 warnings in 421.92s`, exit 0. Skips: five Tk tests in `test_gui_configurator_app.py` and `test_set_data_and_clear` in `test_gui_controller.py` (`tkinter` is missing), plus `test_live_drive_discover_with_suport_empty_password` (Drive MCP is not on localhost). The headless controller path in item 3 was executed.

`git diff --name-only origin/main...HEAD` is the eleven files of this PR (config, `decision_consistency.py`, fitness, trainer, CLI, GUI, sandbox config, and four test modules). A diff limited to `src/`, `sandbox_encoder.py`, `price_memory.py`, and `procurement_motor_adapter.py` is empty. A diff of `training_loop.py` limited to `_felt_accepted_reward`, `_apply_order_feedback`, and `_store_order_experience` is empty. `training_loop.py` does change, around the decision-log row and the trainer constructor.

90 scripted days, ten products, price perception on: JSON of the log is 26070 bytes, JSON of the previous fields alone is 16618 bytes, 105 extra bytes per day. Longest `situation` is 3 tokens. Mean length is 1.03 because idle days store `[]`.

## Defects

None.

## Recommendations

A file that still pins `graduation_thresholds.decision_consistency: 0.60` keeps that bar, and 0.70 then passes Stage 1b. The shipped YAML and the code default are 0.79. `Demo/Virtual company/Docs/NOWA_Procurement_Sandbox_Spec.en.md` still shows 0.60. That spec was outside this checklist.

## Readiness

Task 3 can be accepted. The checklist holds on this head. The 0.79 calibration was taken as given and was not re-run.
