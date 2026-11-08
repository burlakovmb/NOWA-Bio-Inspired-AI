# Issue #22 — Colony old age in sim-seconds

Russian: [issue-22-colony-lifespan-sim-seconds.ru.md](issue-22-colony-lifespan-sim-seconds.ru.md)

Closes #22 (demo host only). PR #61. Related: [issue-39-dt-robustness.en.md](issue-39-dt-robustness.en.md) (decision rate vs `dt`).

The cognitive **core** in `src/` (including `src/mortality.py`) is unchanged. Each chinchilla remains its own `Agent` with its own `MortalitySystem`.

---

## 1. Problem

In `Demo/Colony chinchillas`, death from **old age** followed `MortalitySystem.max_lifespan_steps` (`COLONY_MAX_LIFESPAN_STEPS = 20000`) because `max_lifespan_age_s` was left unset. The core then compares **decision count**, not biological age, whenever `max_lifespan_age_s` is `None`.

Simulated lifespan in seconds therefore tracked UI step size and acceleration:

| Step context | Approximate sim time at 20 000 decisions |
| --- | --- |
| Nominal 1× frame (`dt = 1/12` s) | ~1667 s |
| Load-adapted step (`dt = 0.25` s) | ~5000 s |

That contradicts the project rule that simulations stay correct at any time acceleration: the same animal should die of old age at the same **biological age**, not after the same number of decisions.

---

## 2. Decision and rationale

**Decision:** Set `max_lifespan_age_s` on each `ChinchillaAgent`’s `MortalitySystem` from the colony base and genome. Keep passing `biological_age_s=self.age` from the colony clock (already in place). Leave `COLONY_MAX_LIFESPAN_STEPS = 20000` as `max_lifespan_steps` for snapshots and health-index normalisation; the core **ignores** the step field for old-age death while `max_lifespan_age_s` is set.

**Base constant:**

```text
COLONY_MAX_LIFESPAN_AGE_S = 15 * MATURITY_AGE_S = 13500 s
```

(`MATURITY_AGE_S = 900` in `config_colony.py`.)

**Per individual:**

```text
max_lifespan_age_s = COLONY_MAX_LIFESPAN_AGE_S * genome.genes.get("lt_max_lifespan_factor", 1.0)
```

Gene `lt_max_lifespan_factor` is a plain multiplier (registry range **0.5..2.0**), so the old-age cap spans **6750..27000** s. No genome, or factor **1.0**, keeps **13500** s. Newborns receive their own genome after crossover; each animal’s `MortalitySystem` is constructed (or updated after birth) with that individual’s cap.

**Rationale (biology → demo time):** Captive chinchillas mature at about 8 months and live about 10 years on average — a ×15 ratio between adult lifespan and time to maturity. The demo already maps maturity to `MATURITY_AGE_S`, so the **base** old-age cap is 15 × 900 s. Check against reproduction: `13500 / GESTATION_S` (`GESTATION_S = 300`) is **45** gestations, within a real 10–15 year span (roughly 33–49 gestations of 111 days). The heat-cycle clock is a poorer anchor because the demo cycle is long relative to a real ~38-day cycle.

**Media scripts:** `tools/render_evolution_media.py` and `tools/render_promo_media.py` force scripted deaths by passing `biological_age_s=colony_scripted_old_age_s(agent)` — at least each agent’s own `MortalitySystem.max_lifespan_age_s` — still logging cause `old_age`, not by inflating `lived_steps` to the step budget.

---

## 3. Behaviour

- **Old age:** `MortalitySystem.update` registers `old_age` when `biological_age_s >= max_lifespan_age_s` (individual cap; default **13500** s). Decision count does not gate old age.
- **Still earlier than old age:** `exhaustion` (energy ≤ critical threshold) and `sleep_deprivation` (wakefulness ≥ critical threshold) unchanged; senescence vitality loss unchanged.
- **Per-agent core:** Each chinchilla constructs its own `MortalitySystem` (and full NOWA stack); offspring get new instances with caps from their own genomes.

---

## 4. Verification

**Host tests** (`Demo/Colony chinchillas/tests/`):

| Check | Expected |
| --- | --- |
| `test_old_age_lifespan_matches_across_dt` — `_age_step` until death at `dt = 1.0` vs `10.0` | Cause `old_age`; age ≥ 13500 s and &lt; cap + one step; same age across `dt`; `lived_steps` unchanged (3); decision counts differ |
| `test_runner_old_age_matches_at_nominal_1x_and_10x` — runner from age 13499 s | Cause `old_age`; age ≈ 13500 s at nominal 1× frame (`1/12` s) and 10× frame (`2.5` s split to `0.25` s); **12** decisions at 1× vs **4** at 10× for the same second of age |
| `test_tc14_colony_old_age_uses_sim_seconds` | Default agent: `max_lifespan_age_s == COLONY_MAX_LIFESPAN_AGE_S`; steps field still 20000 |
| `test_tc28_old_age_follows_biological_age_not_decision_steps` | Young agent: `lived_steps > 20000`, low age — not dead; old agent: age crosses cap with `lived_steps == 1` — `old_age` |
| `test_lifespan_factor_scales_old_age_and_matches_across_dt` | Factors 0.5 / 1.0 / 2.0 (and no genome): caps 6750 / 13500 / 27000 s; `old_age` at same sim-age across `dt` |
| `test_lifespan_factor_runner_matches_at_nominal_1x_and_10x` | Runner kills at each individual’s cap at 1× vs 10× with different decision counts |
| `test_newborn_lifespan_cap_follows_its_own_genome` | Offspring cap from its post-crossover genome, not the parents’ caps |
| `test_scripted_old_age_uses_each_agents_cap` | `colony_scripted_old_age_s` matches per-agent caps (including 2.0× and 0.5×) |

Run colony tests locally as in [COLONY_SPEC.en.md](../../Demo/Colony%20chinchillas/Docs/COLONY_SPEC.en.md).

---

## 5. Consequences

- Old age occurs at each animal’s **sim-second cap** regardless of UI speed or sub-tick splitting (default **13500** s; was ~1667 s at `1/12` s steps and ~5000 s at `0.25` s steps for the same 20 000-decision budget).
- Evolution can shorten or lengthen effective lifespan via `lt_max_lifespan_factor` (6750..27000 s) without changing the base constant.
- Longer effective lifespans at former nominal speeds; population and lineage timelines stretch unless other mortality dominates.
- **Debt:** Swarm analytics **lifespan** component still normalises mean `lived_steps` by `max_lifespan_steps` (`colony_gui/swarm_analytics.py`), not by `max_lifespan_age_s` — the health index can under-report “life spent” relative to the new old-age clock.

---

## 6. Open points

| Topic | Notes |
| --- | --- |
| ×15 vs ×22.5 adult span | Alternative **base** cap `22.5 * MATURITY_AGE_S = 20250` s (before `lt_max_lifespan_factor`) — product / biology choice |
| Health-index lifespan share | Align denominator with `max_lifespan_age_s` or age-at-death — follow-up to this issue |
| Colony save/load genome | `ColonyStorage` does not persist `genome`; a reloaded animal falls back to factor 1.0 (**13500** s cap) — pre-existing limitation, not introduced here |
