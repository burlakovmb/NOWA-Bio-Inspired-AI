# QA issue #76 task 2 — coarse price band and felt cost

Branch: `team/vc76-price-2`. Commit under test: `ed635febca064b119ee8e804fd791ebb83ec43bb` (`Add a coarse price band and felt cost for accepted orders`). Parent: `66ba6a8`. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/93. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/76.
Russian: [issue-76-task2-qa.ru.md](issue-76-task2-qa.ru.md).

Scope is that commit, and only `Demo/Virtual company/`. Product code was not changed. CI on this head is already green (run 45670643716); the full suite was not repeated.

Machine: Linux, Python 3.12.3, pytest 9.2.0. Demo tests insert `Demo/Virtual company/src` and the repo `src/` via `Demo/Virtual company/tests/conftest.py`.

## Verdict

**PASS.**

A deficit SKU with no reference is `price:{pid}:average`. The band is the mean of status-ok quotes from the same supplier book the motor sees, compared with the per-SKU EMA that was current before today's update. `z = ±0.5` stays `average`; the next step past the threshold changes the band. An accepted order pays `0.4 + 0.3·clip(−z, −1, 1)`, which stays in `[0.1, 0.7]`. Store and next-day feedback both use the reference captured on the decision day. `--no-price-perception` drops the `price:` tokens, keeps the accepted reward at 0.4, and matches `66ba6a8` on one 90-day quarter, seed 42, once the pre-existing unseeded selector and wall clock are held fixed. An old checkpoint without `price_memory` loads an empty reference. The price path does not read `base_price_multiplier` or `world.offers`.

## Coverage

15 scenarios run, 0 failed, 0 not run.

| # | Check | Result |
| --- | --- | --- |
| 1 | Band boundaries `z = ±0.5` and the `1e-6` scale floor | Pass |
| 2 | First deficit day is `average`; a later quote shift changes the token; the same quote does not | Pass |
| 3 | The band is the mean of status-ok quotes; other statuses are ignored | Pass |
| 4 | Reward sign and `[0.1, 0.7]` at gain 0.3; no reference, flag off, or a non-finite price stays 0.4 | Pass |
| 5 | Live two-day loop: store and next-day feedback share the decision-day reference; the EMA moves only after that read | Pass |
| 6 | A one-day quarter's trailing feedback uses the saved reference, not the memory updated later that day | Pass |
| 7 | The first accepted order, with an empty reference, is 0.4 in both places even after the memory has been filled | Pass |
| 8 | `price_perception` off: no `price:` tokens, accepted reward exactly 0.4, a preloaded reference is not updated | Pass |
| 9 | Flag off versus `66ba6a8`, 1 quarter, seed 42, 90 days | Pass. Actions, tokens, rewards, and quarter metrics match |
| 10 | Old checkpoint without `price_memory`; new checkpoint round-trip | Pass |
| 11 | Hidden price fields do not change the token or the reward | Pass. Source review and a mutation behind a fixed quote book |
| 12 | YAML round-trip, range checks, CLI `--no-price-perception`, GUI config plumbing | Pass |
| 13 | `src/`, `procurement_motor_adapter.py`, and `PROFESSIONAL_SEED_EPISODES` untouched; `agent.step` gets no reward; `value_layer` is not updated | Pass |
| 14 | Known: the reference is keyed by `product_id` and survives a stage 1a world change | Assessed. Not a miss against the stated key. See below |
| 15 | Known: a paid price for a SKU outside the day's context also updates that SKU | Assessed. The branch is real. The measured day loop did not hit it |

### 1–3. Tokens

`classify_price_band` uses a strict comparison. With EMA 10 and spread 2, price 11 (`z = 0.5`) and price 9 (`z = −0.5`) are `average`. Price `11 + 1e-6` is `expensive`. Price `9 − 1e-6` is `cheap`.

With spread 0 the denominator is `1e-6`. The largest computed `z` that is still `≤ 0.5` is `0.49999999873762135` (`average`). The next bisection step, `z = 0.5000000005139782`, is `expensive`. The symmetric negative step is `cheap`. `0.5 * 1e-6` is not an exact binary value, so a price written as `ema + 0.5·eps` lands slightly above 0.5 and is `expensive`. That follows the formula.

A deficit SKU with no reference encodes `price:sku:average` even when the visible quote is 4.0. After that quote is folded in, EMA is `(4.0, 0.0)`. The same quote on the next call stays `average`. A quote of 4.2 becomes `expensive`.

Two ok quotes at 10 and 12, plus an unavailable quote at 100, produce the price list `[10.0, 12.0]`. Against reference `(10, 1)` the mean is `expensive`.

### 4–8. Reward and the decision-day reference

Against `(10, 1)` and gain 0.3: price 9 → 0.7, price 10 → 0.4, price 11 → `0.10000000000000003`. A price of `1e9` or `50` sits on that same lower value; a price of `0` or `−1e9` sits on 0.7. No reference, `enabled=False`, and NaN all return 0.4. The binary value `0.10000000000000003` is `0.4 − 0.3` and stays inside `[0.1, 0.7]`.

Gain 0.4, which the config allows, saturates at 0.0 and 0.8. The interval `[0.1, 0.7]` is the shipped gain 0.3, not every legal gain.

Live loop, real agent, action forced to `place_order_cheap_supplier`, one product held below the reorder point, alpha 0.5, preload `(10, 1)`:

- Day 1 paid 1.0143. Store reward 0.7. The snapshot saved for feedback is `(10.0, 1.0)`.
- `observe_day` then moves the memory to `(2.145775, 3.5029)`.
- Day 2 feedback is still 0.7 and still carries the saved `(10.0, 1.0)`, while the live memory is already the updated pair.
- `agent.step` was called with `decision_only=True` and without a `reward` argument. `Agent._coerce_step_reward(None)` is `(0.0, False)`, so the step does not treat the felt cost as a known outcome.

A one-day quarter applies feedback only after `observe_day`. Paid 0.9294, stored reward 0.7, trailing feedback 0.7. The live memory at feedback time was `(2.069375, 3.526475)`, which would have produced about 0.497. The saved reference was still `(10, 1)`.

Empty memory, two days, alpha 0.1: the first store is 0.4 at paid 1.0995 with reference `None`. The next day's feedback is 0.4 with saved reference `None`, while the live memory is already `(1.105323, 0.00647)`. The second day's own store uses that new reference and, at paid 1.1139, clips to `0.10000000000000003`. Both call sites agree on each decision day.

With `price_perception=False` and a reference already loaded, two accepted orders stored 0.4, both feedbacks were 0.4, no context token started with `price:`, and the snapshot after the quarter was the snapshot from before it.

`value_layer.update_count` stayed 0 across the empty-memory quarter.

### 9. Flag off versus `66ba6a8`

`git diff --name-only 66ba6a8...HEAD` is the eleven files of this commit. It does not include `src/`, `procurement_motor_adapter.py`, or `procurement_hippocampus_seeder.py`. `git diff 66ba6a8...HEAD -G value_layer` is empty.

Two runs of the same commit, without extra controls, do not repeat. The action selector draws with the global `random` module, and several core clocks read `time.time()`. That is true on `66ba6a8` as well. The comparison below freezes both: `PYTHONHASHSEED=0`, `random.seed(42)` after imports and again before `run_quarters`, and `time.time` fixed at `1700000000.0`.

One quarter, seed 42, `days_per_quarter=90`, default world, `seed_intuition=True`, perception off:

| | head `ed635fe` | base `66ba6a8` |
| --- | --- | --- |
| days | 90 | 90 |
| `price:` tokens | 0 | 0 |
| orders placed | 34 | 34 |
| accepted feedback rewards | all 0.4 | all 0.4 |
| action / token / store / feedback sequences | equal to the base, and equal to a second head run | |
| `cost_efficiency` | 0.23844758873606597 | same |
| `stockout_avoidance` | 0.97853343752049 | same |
| `budget_discipline` | 1.0 | same |
| `supplier_diversification` | 0.6294117647058823 | same |
| `decision_consistency` | 0.6666666666666666 | same |
| `reaction_to_risk_events` | 1.0 | same |
| budget left | 74984.39 | same |
| stockout units | 74.55 | same |
| `cost_vs_chance` | −0.1249873423538107 | same |

### 10. Checkpoints

A checkpoint written with `carried_suppliers` and no `price_memory` loads. Restore clears a reference that had been updated to 9, leaves `skus` empty, and keeps `supplier_000`.

A checkpoint written from `checkpoint_metadata()` after updates `[4.0, 8.0]` at alpha 0.25 restores the reference `(5.0, 1.0)`. The file records alpha 0.25. `restore_checkpoint_metadata` then builds the memory with the trainer's current alpha. A trainer constructed at alpha 0.1 keeps the levels and uses alpha 0.1 afterwards. The same config therefore reproduces the same alpha; a changed config keeps the levels and steps with the new alpha.

### 11. No leak

`price_memory.py` and `sandbox_encoder.py` have no attribute read of `base_price_multiplier`, `offers`, or `price_volatility`. `_felt_accepted_reward`, `_apply_order_feedback`, and `_store_order_experience` do not mention `base_price_multiplier` or `world.offers`. The quote reader uses `status` and `unit_price` from the book it is given. The encoder still calls `observe_stock_levels` and `observe_budget_status`; those snapshots do not carry the supplier multiplier.

On a real one-product world the captured supplier book was encoded, then every supplier's `base_price_multiplier` was set to 50. The second encode of the same book produced the same tokens, including `price:product_000:cheap`, and `felt_accepted_reward(1.1, (1.0, 0.2), gain=0.3)` stayed 0.25. Building a new book from the mutated world did change the quotes.

Hand check, alpha 0.5: quotes 10 then 12, then a paid 8, end at `(9.5, 2.0)`. The day's token and reward are computed before that fold.

### 12. Config

Shipped `configs/default_world.yaml`: `price_perception: true`, alpha 0.1, `z` 0.5, gain 0.3. `to_dict` / `from_mapping` matches. Edges `false` / alpha 1 / `z` 0.01 / gain 0 round-trip.

Rejected with `ValueError`: alpha 0, 1.01, −0.1; `z` 0 and −1; gain −0.01 and 0.41. The string `nope` and YAML `.nan` fall back through `safe_float` to 0.1 and 0.5.

`--no-price-perception` forces the flag off on top of a YAML file that already says false. Without the flag, the shipped file stays on. `RunController._prepare_config` keeps a YAML `false` (alpha 1.0 came through with it) and keeps the shipped default on. The GUI namespace passes `no_price_perception=False`, so it does not override the file, and the trainer is built with `config.training.price_perception` and the three numeric fields.

### 13. Untouched core path

`_agent_step` still calls `step` with the context and, when supported, `decision_only` and `dt`. It does not pass `reward`. The diff of `_apply_order_feedback` and `_store_order_experience` is the shared `_felt_accepted_reward` call. Rejected rewards stay −0.5 for `insufficient_budget` and −0.3 otherwise.

### 14–15. Known characteristics

**Product id survives the world change.** Stage 1a builds a new world per quarter and reuses `product_000` … `product_009`. The memory lives on the trainer and is not cleared between quarters.

Controlled case, one day per quarter, quotes forced to 10 then to 1, alpha 0.5: quarter 1 starts with no reference and encodes `price:product_000:average`. Quarter 2 starts from `(10.0, 0.0)` and encodes `price:product_000:cheap`. An empty reference would still have said `average`.

Default world, seed 42, 90 days, alpha 0.1, perception on, clock and global `random` frozen as in scenario 9. At the first day of quarter 2 all ten SKUs already have a reference. Four of them are not `average`, which is what an empty reference returns:

| SKU | EMA | spread | new mean | z | band |
| --- | --- | --- | --- | --- | --- |
| product_002 | 1.0878 | 0.0891 | 1.1416 | 0.604 | expensive |
| product_005 | 1.1082 | 0.0949 | 1.0433 | −0.683 | cheap |
| product_007 | 1.0759 | 0.0801 | 1.0133 | −0.781 | cheap |
| product_008 | 1.0834 | 0.0744 | 1.0068 | −1.029 | cheap |

The other six stay `average`. The largest absolute z is 1.029. Prices in this generator sit near 1, so the carried level is the same order of magnitude as the new good. It is enough to flip the coarse band. Severity: **minor**. It does not block acceptance of task 2: the stated key is `product_id`, and no reset on a new world was required. The practical risk is the first days of each new stage 1a quarter, until new quotes move the EMA (alpha 0.1).

**Paid price outside the day's context.** `observe_day` appends the paid price to that SKU's quotes when the id is in the day's list, and otherwise updates that id from the paid price alone. A direct call with quotes for `shown` at 3 and a paid `hidden_sku` at 7.5 leaves `(3.0, 0.0)` and `(7.5, 0.0)`. In the forced deficit loop the ordered SKU was in the `product:` tokens. Across the two default quarters above, the paid id was outside the perceived set zero times: the motor orders a deficit SKU, and those are the SKUs that receive a `product:` token. Severity: **minor**. It does not block acceptance. The value written is the unit price the order result already returned, not a hidden world field, and the current day loop did not exercise the side path.

## Tests

```
python3 -m pytest -q --no-header -p no:warnings \
  "Demo/Virtual company/tests/test_price_perception.py" \
  "Demo/Virtual company/tests/test_sandbox_config.py" \
  "Demo/Virtual company/tests/test_run_sandbox.py" \
  "Demo/Virtual company/tests/test_sandbox_two_tier_host.py"
```

`92 passed in 1.40s`.

The live numbers above come from a throwaway probe under `/tmp`, not from the tree.

## Defects

None.

## Recommendations

- The identity check is only stable if the global `random` stream and `time.time` are fixed. The sandbox seed does not seed the selector. That predates this commit. A future comparison that ignores it will report a false regression.
- `restore_checkpoint_metadata` keeps ema and spread and then uses the trainer's alpha, not the alpha stored in the file.
- Non-numeric alpha and NaN `z` fall back to the defaults. Values outside `(0, 1]`, `> 0`, and `[0, 0.4]` raise.
- At gain 0.4 the felt reward reaches 0.0 and 0.8. The `[0.1, 0.7]` interval is the shipped gain 0.3.
- Stage 1a will keep labeling `product_NNN` with the previous world's EMA until the new quotes catch up. A reset on world change was not part of this task.

## Release readiness

Ready to accept task 2. The two known characteristics are real and are minor relative to the stated contract. They do not fail the token, the reward, the flag-off identity, the checkpoint, or the no-leak checks.
