# Issue #76 — Virtual company sandbox graduation metrics

Russian: [issue-76-vc-graduation-metrics.ru.md](issue-76-vc-graduation-metrics.ru.md)

Scope: `Demo/Virtual company/src/nowa_sandbox/` and `Demo/Virtual company/configs/default_world.yaml`. Issue [#76](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/76). QA: [issue-76-task1-optionA-qa.en.md](../qa/issue-76-task1-optionA-qa.en.md), [issue-76-task2-qa.en.md](../qa/issue-76-task2-qa.en.md), [vc76-task3-decision-consistency.en.md](../qa/vc76-task3-decision-consistency.en.md).

Related: two-stage curriculum ([Demo/Virtual company/Docs/v1.1_two_stage_curriculum.en.md](../../Demo/Virtual%20company/Docs/v1.1_two_stage_curriculum.en.md)), sandbox host plasticity ([issue-58-sandbox-two-tier-plasticity.en.md](issue-58-sandbox-two-tier-plasticity.en.md)).

---

## Overview

Six criteria are always measured; which gate graduation depends on `training.stage` (`1a` vs `1b`). Code defaults and the shipped YAML agree on thresholds in `procurement_fitness.GRADUATION_THRESHOLDS` and `graduation_thresholds` in `configs/default_world.yaml`.

| Criterion | Stage | Default threshold |
| --- | --- | --- |
| `cost_efficiency` | 1a | 0.60 |
| `stockout_avoidance` | 1a | 0.85 |
| `budget_discipline` | 1a | 0.95 |
| `reaction_to_risk_events` | 1a | 0.50 |
| `supplier_diversification` | 1b | 0.40 |
| `decision_consistency` | 1b | **0.79** |

Stage 1b also runs the non-regression guard on the four Stage 1a criteria (issue #76 task 1). Details: [issue-76-task1-optionA-qa.en.md](../qa/issue-76-task1-optionA-qa.en.md).

---

## Task 1 (brief) — fair Stage 1b cost floor

Stage 1b must not pass on a degenerate Stage 1a baseline. The cost guard uses `stage_baseline.cost_vs_chance_floor_delta` (default `0.03`, allowed `0.02`–`0.05` in `sandbox_config`). Floor formula and probes are in the task‑1 QA report; no change to the six headline thresholds above.

---

## Task 2 — price perception (experience, not a rule)

Implementation: `price_memory.py`, wired from `training_loop.SandboxTrainer` and `sandbox_encoder.SandboxEncoder`.

### What the agent sees

For each SKU below the reorder point, the encoder may emit `price:{product_id}:{band}` after `product:{id}` and `status:below_reorder_point`. Bands are `cheap`, `average`, or `expensive` — not numeric prices.

- **Today's quotes:** mean of status-`ok` `unit_price` values from the same supplier observation book the motor uses (`visible_unit_prices`).
- **Reference:** per-SKU EMA level and EMA absolute deviation (`PriceMemory`), built only from past visible quotes and paid unit prices on accepted orders.
- **Band:** `z = (mean_today − ema) / max(spread, PRICE_SCALE_EPS)` with `PRICE_SCALE_EPS = 1e-6`. Strict thresholds: `z < −z_threshold` → cheap; `z > z_threshold` → expensive; else average. No reference or no quotes → `average` (including first deficit day).

Constants (defaults match `configs/default_world.yaml`):

| Symbol / key | Default | Role |
| --- | --- | --- |
| `DEFAULT_PRICE_MEMORY_ALPHA` / `price_memory_alpha` | 0.1 | EMA update |
| `DEFAULT_PRICE_BUCKET_Z` / `price_bucket_z` | 0.5 | Band width |
| `DEFAULT_PRICE_REWARD_GAIN` / `price_reward_gain` | 0.3 | Felt cost on accept |
| `ACCEPTED_BASE_REWARD` | 0.4 | Base labile reward when perception is off or reference missing |

### Causal order (no same-day leak)

1. Before the decision: `price_refs = price_memory.snapshot()`.
2. Encoder and felt reward read that snapshot only.
3. After the decision (and after `world.tick()` scheduling in the day loop): `price_memory.observe_day(...)` folds today's quotes and optional paid price.

Accepted-order labile reward: `felt_accepted_reward` → `0.4 + gain·clip(−z_paid, −1, 1)` in `[0.1, 0.7]` at default gain. Store and next-day feedback both use the reference captured at decision time.

### Configuration

`training.price_perception` (default `true`). CLI `--no-price-perception` sets it false: no `price:` tokens, accepted reward stays `0.4`, behaviour matches pre–task‑2 runs under fixed seeds (see task‑2 QA). Checkpoint field `price_memory` round-trips in `sandbox_checkpoint`.

The price path does not read hidden fields such as `base_price_multiplier`; only observable quotes and paid prices update the reference.

---

## Task 3 — decision consistency by situation

Implementation: domain-neutral `decision_consistency.py`; procurement binding in `DEFAULT_CONSISTENCY`, YAML `consistency:`, and `ProcurementFitnessEvaluator.consistency`.

### Definition

Among **accepted** decisions (see `counted_statuses`), group rows by `(entity, situation)` where `situation` is the sorted unique set of context tokens that belong to that entity on that day. For each group with at least `min_decisions` rows, take the share of the dominant `choice`. The score is the total dominant count divided by the total row count in all qualifying groups, clamped to `[0, 1]`. If no group qualifies, the score is `neutral` (default `0.5`).

`choice` is whatever field `ConsistencyConfig.choice_field` names on the call record (see below). Graduation uses this value; diagnostics still expose the old supplier concentration (see Diagnostics).

### `ConsistencyConfig`

| Field | Procurement default | Meaning |
| --- | --- | --- |
| `entity_field` | `product_id` | Entity id for grouping |
| `choice_field` | `action` | Strategy string the brain passed to the motor (e.g. `place_order_cheap_supplier`) |
| `attached_prefixes` | `("status:",)` | Attached tokens follow the nearest previous non-attached token for the same entity |
| `counted_statuses` | `("accepted",)` | Only these `result.status` values count (`insufficient_budget` etc. are out) |
| `min_decisions` | `3` | Minimum rows per `(entity, situation)` group |
| `neutral` | `0.5` | Score when no qualifying group |

Procurement-specific words do not appear in `decision_consistency.py`; a logistics-style host is covered in `tests/test_decision_consistency.py` with `route_id` / `carrier_id`.

### Situation tokens

Function: `situation_tokens(context_events, entity_id, attached_prefixes)`.

- A token belongs to entity `E` when `str(E)` equals **one of the colon-separated fields after the first** (the type prefix before the first `:` is not compared). Matching is exact on fields, not substring (`P1` does not match `P10` or `price:P10:…`).
- Tokens whose names start with `attached_prefixes` attach to the entity of the **nearest previous** token that does not start with an attached prefix. Any other non-attached token between them **breaks** the link (e.g. `event:…`, `budget:…`).
- Typical deficit SKU situation (price perception on): `product:{pid}`, `price:{pid}:{band}`, `status:below_reorder_point`. With `price_perception` off, `price:` tokens are absent from context and situation.

Idle days (no order): `entity=None`, `situation=[]`, excluded from the score.

### Decision log fields

Each day append in `training_loop` merges `decision_fields(call, tool, context_events, config)`:

| Field | When set |
| --- | --- |
| `tool` | `place_order` if an order was attempted; else `None` |
| `entity` | From `entity_field` on the call |
| `choice` | From `choice_field`; for procurement the call dict includes `action` set to the strategy type passed into `resolve` (not overwritten `OrderParams.strategy`) |
| `situation` | Token list from `situation_tokens` for that entity |

Legacy rows without `choice` still work via fallback to `entity_field` / `choice_field` on the row body.

### Threshold 0.79

Shipped: `GRADUATION_THRESHOLDS["decision_consistency"]` and `graduation_thresholds.decision_consistency` in `default_world.yaml`. YAML may override; old files that still pin `0.60` keep that bar.

Calibration (team lead, five Stage 1b seeds; cited in issue #76, **not** re-run in [vc76-task3 QA](../qa/vc76-task3-decision-consistency.en.md)):

| Baseline policy | Typical score | Share of quarters ≥ 0.79 |
| --- | --- | --- |
| Random strategy | ≈ 0.545 | ≈ 4% |
| Always cheap strategy | ≈ 0.990 | ≈ 98% |
| Learning agent (current) | ≈ 0.598 | below gate |

QA on PR #97 confirms the gate itself: on a Stage 1b evaluator, `0.789` fails and `0.79` passes; `0.60` fails against the new bar.

With `choice_field: supplier_id`, alternating suppliers on a fixed strategy yields `0.5` while `action` yields `1.0` on the same log — so **no** threshold separates random from perfect supplier stickiness; graduation intentionally scores **strategy** (`action`), not supplier id.

### Diagnostics (quarter JSON)

From `ProcurementFitnessEvaluator.consistency_diagnostics`:

| Key | Meaning |
| --- | --- |
| `decision_consistency` | Gating score (`choice_field` binding) |
| `decision_consistency_by_product` | Legacy-style concentration of `supplier_id` per `product_id` (`by_entity_legacy`) |
| `decision_consistency_situations` | Number of `(entity, situation)` groups used |
| `decision_consistency_decisions_used` | Row count in those groups |

### Another role via config only

Point `entity_field`, `choice_field`, and `attached_prefixes` at the new host's call shape and encoder tokens. Pass the same `ConsistencyConfig` into `SandboxTrainer` and `ProcurementFitnessEvaluator` (CLI/GUI load it from YAML). No change to `decision_consistency.py` is required for a future role (e.g. logistics) if the log and tokens follow the contract above.

---

## Known limitations

The sandbox trainer, encoder tokens, `price_memory`, `ORDER_TOOL = place_order`, and staged fitness are still **procurement-shaped**. Reusing the metric for other company roles needs host wiring beyond YAML; tracking: [issue #96](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/96) (when opened).

Historical demo specs under `Demo/Virtual company/Docs/NOWA_Procurement_Sandbox_Spec*.md` may still describe `decision_consistency` at `0.60` and supplier-id stickiness; the normative graduation description for #76 is this document and the code defaults above.