# Issue #18 — Minor learning fixes: implementation spec

Closes #18 (cognitive **core** in `src/`). Related: [issue-18-vc-body-lessons.en.md](issue-18-vc-body-lessons.en.md) (Virtual company body layer), [spec_dopaminergic_td_learning.en.md](../spec_dopaminergic_td_learning.en.md), [architecture/two-tier-plasticity.en.md](../architecture/two-tier-plasticity.en.md), PR #63.

Russian: [issue-18-minor-learning-fixes.ru.md](issue-18-minor-learning-fixes.ru.md)

This PR does **not** change demo hosts. A checkout that vendors a frozen copy of `src/` without these patches keeps the old feedback quantization and unit `V` clamp.

---

## 1. Problem

Three small mismatches between the learning spec and runtime behaviour showed up when filing fractional user ratings and when replaying constant positive feedback during sleep:

| Symptom | Cause |
| --- | --- |
| Rating `1.5` → reward `0.5`, `0.7` → `0` | `apply_feedback_to_last_experience` treated ratings as integers before halving. |
| Sleep value replay moved too fast | `alpha_sleep_default` could stay at legacy `0.08`, above the `0.25 × alpha_online` ceiling. |
| `V(s)` stuck near `±1` under `r = 1` | Value table and sleep replay clamped `V` to `[-1, 1]` while unit rewards imply a discounted-return bound `1 / (1 − γ)` (e.g. `20` at `γ = 0.95`). |

Stable Q / tabular value consolidation still follows two-tier plasticity: waking feedback writes the **labile** path; the **stable** tier is not rewritten while awake (only during sleep consolidation).

---

## 2. Feedback rating coercion

**File:** `src/agent.py` — `Agent._coerce_feedback_rating`, used by `apply_feedback_to_last_experience` (and the same rule as `step` / `commit` for ±inf).

| Input | Result |
| --- | --- |
| `None`, `bool`, non-numeric | Unknown → `None` (no episode rewrite). |
| `NaN` | Unknown → `None`. |
| `+inf` / `-inf` | Rating `±2`, reward `±1`. |
| Finite numeric | Rating kept as **float**, clamped to `[-2, 2]`; **reward** = `rating / 2` (e.g. `1.5` → `0.75`, `0.7` → `0.35`, `2` → `1.0`). |

Fractional ratings are no longer passed through `int()`.

---

## 3. Sleep learning rate (`alpha_sleep`)

**Files:** `src/value_layer.py` (`effective_alpha_sleep`, `derived_alpha_sleep`, `ValueLayer._resolve_alpha`), `src/sleep.py` (`SleepManager._resolved_alpha_sleep`), `src/storage.py` (persist `alpha_sleep_ratio`).

Rules:

1. **Derived step:** `alpha_sleep = alpha_online × alpha_sleep_ratio`, with `alpha_sleep_ratio` clamped to at most `0.25` (`ALPHA_SLEEP_RATIO_MAX`).
2. **`alpha_sleep_default is None`:** derive from online rate and ratio (no separate legacy default).
3. **Stored default:** a finite saved `alpha_sleep_default` may only make the rate **smaller** than the derived value (`min(stored, derived)`). Example: online `0.03`, stored `0.08` → effective `0.0075` (= `0.25 × 0.03`), not `0.08`. A tighter stored value (e.g. `0.001`) is kept; the floor `0.001` does not push the rate above the ratio cap.
4. **SleepManager** applies `min(saved, alpha_online × ratio)` again when resolving replay alpha, then gates and `sleep_alpha_cap`.
5. **Persistence:** `alpha_sleep_ratio` is saved and loaded with the agent / sleep manager state.

`ValueLayer` construction normalises an over-large historical `alpha_sleep_default` to the capped value.

---

## 4. Value magnitude bound (not reward scaling)

**Files:** `src/value_layer.py` (`discounted_value_bound`, `ValueLayer.value_abs_bound`), `src/sleep.py` (`SleepManager._resolved_value_cap`).

For rewards with `|r| ≤ 1` and `γ ∈ [0, 0.999]`:

```text
|V(s)| ≤ 1 / (1 − γ)
```

Implementation:

- `discounted_value_bound(gamma, reward_abs_max=1.0)` returns `reward_abs_max / (1 − γ)` (default `γ = 0.95` → `20`).
- Online `ValueLayer.update` clamps stored and bootstrap `V` with `value_abs_bound()` (tracks `gamma_default`; per-step `gamma` can widen the bound).
- **`reward_scale` stays `1.0`.** Rewards are not divided by `(1 − γ)` to fit the old unit clamp ([spec_dopaminergic_td_learning.en.md](../spec_dopaminergic_td_learning.en.md): do not rescale `r` to dodge saturation).
- **TD error clamp** (`δ_t` in `[-1, 1]` online) is **unchanged**. Large `|V|` can grow slowly because each step moves `V` by at most about one clipped delta per update.

**Sleep replay:** `SleepManager._resolved_value_cap()` returns at least `discounted_value_bound(γ, 1.0)`. Legacy `value_cap = 1` is lifted to that minimum; an explicit larger cap (e.g. `10`) is preserved.

---

## 5. Risks and non-goals

| Risk | Note |
| --- | --- |
| `alpha_online` raised after layer creation | Sleep rate does not automatically rise with a later online bump; stored sleep settings still cap at `ratio × alpha_online` at resolve time. |
| Slow approach to full return | With `|δ| ≤ 1`, reaching `V ≈ 20` under repeated `r = 1` takes many steps (by design). |
| Demo `src/` copies | Patches apply only to repo `src/`; vendored demo trees need a manual sync. |

---

## 6. Files touched (implementation, for traceability)

| File | Role |
| --- | --- |
| `src/agent.py` | `_coerce_feedback_rating`, feedback application |
| `src/value_layer.py` | `discounted_value_bound`, `effective_alpha_sleep`, `value_abs_bound`, sleep alpha resolve |
| `src/sleep.py` | `_resolved_alpha_sleep`, `_resolved_value_cap` |
| `src/storage.py` | `alpha_sleep_ratio`, `value_cap` persistence |
| `tests/test_issue18_minor_learning.py` | Primary acceptance tests for this slice of #18 |
| `tests/test_value_layer.py` | Sleep alpha ratio threshold (`test_sleep_alpha_stays_within_online_ratio`) |
| `tests/test_issue9_sleep_value_replay.py`, `tests/test_qa_pr35_sleep_learning.py` | Sleep replay expectations for capped `alpha_sleep` |

---

## 7. Tests and verification

**Primary:** `tests/test_issue18_minor_learning.py`

- Fractional feedback rewards (`1.5` → `0.75`, `0.7` → `0.35`).
- Non-numeric / NaN / bool rejected; clamp and ±inf behaviour.
- Default and explicit `alpha_sleep_default` vs `0.25 × alpha_online`.
- `discounted_value_bound` and `value_abs_bound` at `γ = 0.95` and `0.5`.
- Table can hold `V` up to the new bound; constant `r = 1` online learning exceeds old `±1` cap but stays within `value_abs_bound`.
- `_resolved_value_cap` lifts legacy `1` to `20`, respects wider configured cap; `reward_scale == 1`.

**Suite (at implementation time):** `python -m pytest -q` — **917 passed, 5 skipped**.

**Doc alignment:** [Phase_5_0_Value_Layer_RU_Spec.en.md](../Phase_5_0_Value_Layer_RU_Spec.en.md) / `.ru.md` — `V(s)` bound updated to `|V| ≤ 1/(1−γ)`; `δ_t` remains `[-1, 1]`.

---

## 8. Acceptance criteria

1. Fractional feedback ratings map to `reward = rating/2` without integer quantization.
2. Effective sleep alpha never exceeds `0.25 × alpha_online` (ratio clamp included).
3. `|V|` may reach `1/(1−γ)` for unit rewards without changing `reward_scale` or widening `δ` clamp.
4. Legacy `value_cap = 1` in sleep replay is widened to the gamma return bound; larger explicit caps unchanged.
5. Waking feedback does not write the stable value table; consolidation remains sleep-only (two-tier invariant).
