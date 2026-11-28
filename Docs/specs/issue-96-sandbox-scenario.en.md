# Issue #96: domain-neutral sandbox scenario layer

Russian: [issue-96-sandbox-scenario.ru.md](issue-96-sandbox-scenario.ru.md)

QA report (do not duplicate): [issue-96-scenario.en.md](../qa/issue-96-scenario.en.md). Branch: `team/issue-96-scenario`, baseline fixtures: commit `0e486e1` on `main`.

## Audience and goal

This guide is for developers who want to plug a new simulated domain into the Virtual company sandbox, and for maintainers of the procurement buyer path. It describes **as-built** behaviour in `Demo/Virtual company/src/nowa_sandbox/` on the issue branch — not a wish list.

Procurement remains the default: CLI (`run_sandbox`), GUI, curriculum editor, and the World tab stay buyer-specific and do not read `scenario.name` from YAML. A foreign domain host builds `ScenarioTrainer(agent, MyScenario(...))` itself.

---

## Architecture: generic layer and domain plugin

| Layer | Modules | Role |
|---|---|---|
| Generic | `scenario.py`, `scenario_trainer.py`, `numeric_memory.py`, `stage_mechanics.py` | Domain-neutral day/period loop, EMA memory, graduation helpers |
| Procurement plugin | `procurement_scenario.py`, `procurement_fitness.py`, `procurement_world.py`, motor/encoder helpers | Buyer world, KPIs, tools |
| Facade | `training_loop.py` → `SandboxTrainer` | Same public constructor as before; delegates to `ProcurementScenario` inside `ScenarioTrainer` |
| Thin wrapper | `price_memory.py` | `PriceMemory` over `NumericMemory` with `record_key="skus"` (backward compatible key) |

`procurement_fitness.py` still owns buyer KPI formulas; graduation and non-regression for criteria names are delegated to `stage_mechanics`.

A **lexicon guard** in `tests/test_issue_96_scenario.py` forbids buyer vocabulary in the four generic modules (`scenario.py`, `scenario_trainer.py`, `numeric_memory.py`, `stage_mechanics.py`). Extend domains in plugin or test code, not in those stems.

---

## `Scenario` contract

Base class: `nowa_sandbox.scenario.Scenario`. Value types: `Observation`, `Call`, `Outcome`.

### Required methods

| Method | Purpose |
|---|---|
| `observe(world)` | Build a read-only `Observation` |
| `encode(world, tick_result, observation)` | `context_events` for `agent.step` |
| `action_label(intent)` | Map agent output to a domain action string |
| `resolve(action, observation, agent)` | Optional `Call` (tool + arguments) |
| `apply(world, call, observation)` | `Outcome` (immediate `result`, optional delayed `pending`) |
| `store` / `note` / `remember` | Side effects on memory, hippocampus, notes (defaults are no-ops) |
| `row(...)` | One decision-log dict per day |
| `evaluate(world, decision_log)` | Period fitness object (must expose `as_dict()` for summaries) |
| `graduation_report(fitness)` | Per-period graduation dict (use `stage_mechanics.graduation_report`) |
| `config_for_step(world_config, period_index)` | Config slice for this period |
| `open_period(config, period_index)` | `(world, labels)` — `labels` merge into quarter summary |
| `stage_name()` | Stage id for streak logic (buyer: `"1a"` / `"1b"`) |
| `minimum_streak()` | Consecutive qualifying periods required for graduation |

### Optional roster hooks

When `run_quarters(..., carry_roster=True)` and the scenario implements roster support:

- `has_roster()`, `drop_roster()`, `apply_roster(world)`, `capture_roster(world)`, `roster_boundary(period_index, stage_start)`

Buyer Stage 1b uses these; a toy domain may leave defaults (`has_roster()` → `False`).

### Default world cycle hooks

Override only if the domain is not a tick/day world with `history` and `bankrupt`:

- `halted`, `previous_tick`, `advance`, `day`, `world_summary`, `period_length`, `apply_feedback`, `begin_period`, `trace`, `fitness_line`, `summary_extras`, `non_regression`

---

## Day order inside one period

Implemented in `ScenarioTrainer._run_single_quarter` (`scenario_trainer.py`). For each day until `period_length` or `halted(world)`:

1. Stop if `scenario.halted(world)`
2. `tick_result = scenario.previous_tick(world)`
3. If delayed feedback `pending` from the prior day: `scenario.apply_feedback(pending)`
4. `observation = scenario.observe(world)`
5. `tokens = scenario.encode(...)`
6. **One** `agent.step(tokens, ...)` (via `_agent_step`, `dt=86400.0` when accepted)
7. `action = scenario.action_label(intent)`
8. `call = scenario.resolve(action, observation, agent)`
9. If `call` is not `None`: `outcome = scenario.apply(...)`; set `pending = outcome.pending`; `store` → `note`
10. `scenario.remember(...)`
11. Append `scenario.row(...)` to the decision log
12. `scenario.trace(...)`
13. `scenario.advance(world)`
14. Every `sleep_every_n_days`: agent sleep/consolidation

After the day loop, any remaining `pending` is flushed through `apply_feedback`.

Period orchestration in `run_quarters`: `config_for_step` → `open_period` → optional roster → `_run_single_quarter` → `evaluate` → `graduation_report` → streak/graduation flags. `last_decision_log` holds **only the last completed period** (same as pre-refactor buyer behaviour).

---

## `NumericMemory` and buyer `PriceMemory`

`NumericMemory` keeps an EMA level and EMA absolute deviation per entity id. Parameters:

| Parameter | Meaning |
|---|---|
| `value_field` | Field name read from offer/book rows |
| `token_prefix` | Prefix for band tokens (e.g. `price:`, `cost:`) |
| `entity_prefix` | Prefix for entity tokens in context |
| `record_key` | Key in observation payloads (`PriceMemory` uses `skus`) |

API highlights: `observe_day`, `band_token`, `felt_reward`, `update`. References are updated **after** the decision step so today's quote book does not leak into today's token.

Quote-book shape for `band_token` / `observe_day` is domain-specific (nested `offers` by default); logistics uses its own book layout in tests.

---

## Thresholds, graduation, non-regression

Shared helpers in `stage_mechanics.py` (no hard-coded criterion names in call sites):

- `merge_thresholds(raw, defaults)` — unknown YAML keys dropped when defaults exist; all finite keys kept when `defaults is None`
- `graduation_report(vector, thresholds, stage, gating)` — only names in `gating` set `all_passed`
- `check_non_regression` — used from domain fitness wrappers
- Streak helpers: `current_qualifying_streak`, `period_qualifies`, `roster_period_boundary`

Buyer thresholds still live in `configs/default_world.yaml` and `procurement_fitness.GRADUATION_THRESHOLDS`; formulas unchanged.

---

## Optional YAML `scenario:` section

Parsed in `sandbox_config.py` → `ScenarioConfig`. **Absent section** → buyer behaviour unchanged (`scenario is None`, Stage 1a defaults, price perception on, `supplier_set_count` 4).

When present:

```yaml
scenario:
  name: procurement   # or another id for non-buyer memory defaults
  memory:
    value_field: unit_price
    token_prefix: price
    entity_prefix: product
  consistency:          # optional; overrides top-level consistency when set
    entity_field: ...
```

Rules:

- `name: procurement` — memory defaults `unit_price` / `price` / `product`; buyer-specific world/training fields still apply
- Any other `name` — generic defaults `value` / `level` / `entity`; world section is not auto-switched (host must wire the scenario class)
- `run_sandbox`, GUI, and curriculum do **not** dispatch on `scenario.name` today

---

## Minimal integration recipe

1. Implement `MyScenario(Scenario)` with world + fitness types (see reference below).
2. Wire memory: `NumericMemory(...)` or a thin subclass with your prefixes.
3. Build graduation with `graduation_report(fitness, merge_thresholds(...), stage, gating)` and optional `check_non_regression`.
4. Construct `ScenarioTrainer(agent, my_scenario, sleep_every_n_days=...)`.
5. Call `trainer.run_quarters(n_quarters=..., world_config=..., carry_roster=...)`.
6. Add tests under `Demo/Virtual company/tests/` (lexicon guard already protects generic modules).

### Reference second domain (tests only)

Toy logistics — not a shipped role or YAML world:

- Implementation: `Demo/Virtual company/tests/logistics_scenario.py`
- Tests: `tests/test_logistics_scenario.py`
- Tokens: `route:…`, `status:…`, `cost:…`; tool `assign_carrier`; criteria `on_time_share`, `carrier_stability`
- Uses `ScenarioTrainer` directly with a stub agent

Do not copy procurement imports into generic modules.

---

## Golden gate (procurement regression)

**Purpose:** Exact JSON comparison of a frozen procurement slice so refactors do not drift buyer journals or float KPIs silently.

| Piece | Location |
|---|---|
| Tool | `Demo/Virtual company/tools/golden_issue_96.py` |
| Fixtures | `tests/fixtures/issue_96_golden/*.json` (four short + optional `seed42_q1_d90_price_on`) |
| Pytest | `tests/test_issue_96_golden.py` |

### What is frozen

- `PYTHONHASHSEED=0` (script re-execs if unset)
- `random.seed(42)` before each run
- `time.time` → `1700000000.0`; monotonic/perf counters stepped
- ASLR off via `setarch -R` (required on Linux) for stable `id()` order in the core
- Unseeded `random.Random()` replaced with integer seeds `42 * 1_000_003 + n` (tuple seeds are rejected on Python 3.12 and would route to fallback buyer — **not** a valid golden agent)

Each case runs in a **fresh child process**. Quarters are captured one at a time so `trainer.last_decision_log` is readable (equivalent to one `run_quarters` call with `stop_on_graduation=False`).

### Core agent requirement

`_require_core_agent` fails the capture if the factory returns `_FallbackAgent`. Green byte comparison against a fallback would not guard the real cognitive path. Tests assert `core-agent agent.Agent` on stderr and absence of `_FallbackAgent`.

### Regenerate fixtures

From `Demo/Virtual company/` (Linux with `setarch` available):

```bash
PYTHONHASHSEED=0 python tools/golden_issue_96.py --write
PYTHONHASHSEED=0 python tools/golden_issue_96.py --write --include-long
PYTHONHASHSEED=0 python tools/golden_issue_96.py --check --include-long
```

Options: `--only seed42_price_on,...`, `--out <dir>`. Slice config: `configs/default_world.yaml`, stage `1a`, seeds 42 and 3, ten-day quarters ×2, price perception on/off; long case — 90 days, seed 42, perception on.

Re-record only when buyer behaviour **intentionally** changes; note baseline commit in the commit message. Fixtures were shot at `0e486e1`.

---

## Known interface limitations (accepted)

| Topic | Behaviour |
|---|---|
| `last_decision_log` | Replaced after each period; no multi-period history on the trainer |
| `n_orders` on fitness vectors | Generic field name reused across domains (logistics sets its own semantics) |
| `band_token` / `observe_day` | Expect a quote-book shape; each domain supplies compatible data |
| `compute_stage_1a_baseline(..., criteria=None)` | Defaults to buyer `STAGE_1A_CRITERIA`; pass explicit `criteria` for other domains |
| `_fitness_summary` in `scenario_trainer` | Lists six buyer attributes when present; otherwise uses `as_dict()` |
| GUI / CLI host | Procurement-only; custom domains need their own entry point |

---

## Related paths

| Path | Note |
|---|---|
| `procurement_scenario.py` | Buyer `Scenario` implementation |
| `sandbox_config.py` | `scenario:` parsing |
| `stage_baseline.py` | Stage 1a baseline (buyer criteria default) |
| `Docs/qa/issue-96-scenario.en.md` | QA evidence |