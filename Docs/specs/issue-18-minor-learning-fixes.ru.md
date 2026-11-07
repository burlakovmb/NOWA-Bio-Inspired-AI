# Issue #18 — мелкие правки обучения: спецификация реализации

Закрывает #18 (**ядро** в `src/`). Связано: [issue-18-vc-body-lessons.ru.md](issue-18-vc-body-lessons.ru.md) (слой тела Virtual company), [spec_dopaminergic_td_learning.ru.md](../spec_dopaminergic_td_learning.ru.md), [architecture/two-tier-plasticity.ru.md](../architecture/two-tier-plasticity.ru.md), PR #63.

English: [issue-18-minor-learning-fixes.en.md](issue-18-minor-learning-fixes.en.md)

Этот PR **не** меняет демо-хосты. Сборка с зафиксированной копией `src/` без этих патчей сохраняет старую квантизацию отзыва и кламп `V` в единичный диапазон.

---

## 1. Проблема

Три расхождения между спецификацией обучения и рантаймом проявились при дробных пользовательских оценках и при сонном replay постоянного положительного feedback:

| Симптом | Причина |
| --- | --- |
| Оценка `1.5` → reward `0.5`, `0.7` → `0` | `apply_feedback_to_last_experience` приводил рейтинг к `int` перед делением на 2. |
| Сонный replay ценности слишком быстрый | `alpha_sleep_default` мог оставаться на legacy `0.08`, выше потолка `0.25 × alpha_online`. |
| `V(s)` застревал около `±1` при `r = 1` | Таблица `V` и sleep replay обрезали `V` до `[-1, 1]`, тогда как unit reward задаёт границу дисконтированной доходности `1 / (1 − γ)` (напр. `20` при `γ = 0.95`). |

Стабильное Q / табличная консолидация ценности по-прежнему в двухуровневой пластичности: дневной feedback пишет **лабильный** след; **стабильный** уровень наяву не переписывается (только при консолидации во сне).

---

## 2. Приведение рейтинга feedback

**Файл:** `src/agent.py` — `Agent._coerce_feedback_rating`, вызывается из `apply_feedback_to_last_experience` (для ±inf то же правило, что в `step` / `commit`).

| Ввод | Результат |
| --- | --- |
| `None`, `bool`, нечисловое | Неизвестно → `None` (эпизод не переписывается). |
| `NaN` | Неизвестно → `None`. |
| `+inf` / `-inf` | Рейтинг `±2`, reward `±1`. |
| Конечное число | Рейтинг как **float**, clamp `[-2, 2]`; **reward** = `rating / 2` (напр. `1.5` → `0.75`, `0.7` → `0.35`, `2` → `1.0`). |

Дробные рейтинги больше не проходят через `int()`.

---

## 3. Скорость обучения во сне (`alpha_sleep`)

**Файлы:** `src/value_layer.py` (`effective_alpha_sleep`, `derived_alpha_sleep`, `ValueLayer._resolve_alpha`), `src/sleep.py` (`SleepManager._resolved_alpha_sleep`), `src/storage.py` (сохранение `alpha_sleep_ratio`).

Правила:

1. **Выведенный шаг:** `alpha_sleep = alpha_online × alpha_sleep_ratio`, `alpha_sleep_ratio` ограничен сверху `0.25` (`ALPHA_SLEEP_RATIO_MAX`).
2. **`alpha_sleep_default is None`:** вывод из online-ставки и ratio (отдельного legacy-дефолта нет).
3. **Сохранённый дефолт:** конечный `alpha_sleep_default` может только **уменьшить** ставку относительно выведенной (`min(stored, derived)`). Пример: online `0.03`, stored `0.08` → effective `0.0075` (= `0.25 × 0.03`), не `0.08`. Более жёсткое stored (напр. `0.001`) сохраняется; пол `0.001` не поднимает ставку выше потолка ratio.
4. **SleepManager** при resolve replay снова берёт `min(saved, alpha_online × ratio)`, затем gate и `sleep_alpha_cap`.
5. **Персистентность:** `alpha_sleep_ratio` сохраняется и загружается вместе с состоянием агента / sleep manager.

При создании `ValueLayer` слишком большой исторический `alpha_sleep_default` нормируется до capped-значения.

---

## 4. Граница величины V (не масштабирование reward)

**Файлы:** `src/value_layer.py` (`discounted_value_bound`, `ValueLayer.value_abs_bound`), `src/sleep.py` (`SleepManager._resolved_value_cap`).

При `|r| ≤ 1` и `γ ∈ [0, 0.999]`:

```text
|V(s)| ≤ 1 / (1 − γ)
```

Реализация:

- `discounted_value_bound(gamma, reward_abs_max=1.0)` → `reward_abs_max / (1 − γ)` (дефолт `γ = 0.95` → `20`).
- Online `ValueLayer.update` clamp'ит сохранённое и bootstrap `V` через `value_abs_bound()` (от `gamma_default`; `gamma` шага может расширить границу).
- **`reward_scale` остаётся `1.0`.** Награду **не** делят на `(1 − γ)`, чтобы влезть в старый unit-clamp ([spec_dopaminergic_td_learning.ru.md](../spec_dopaminergic_td_learning.ru.md): не масштабировать `r` из-за насыщения).
- **Кламп TD error** (`δ_t` в `[-1, 1]` online) **без изменений**. Большое `|V|` растёт медленно: за шаг сдвиг ограничен clipped delta.

**Sleep replay:** `SleepManager._resolved_value_cap()` возвращает не меньше `discounted_value_bound(γ, 1.0)`. Legacy `value_cap = 1` поднимается до этого минимума; явный больший cap (напр. `10`) сохраняется.

---

## 5. Риски и вне scope

| Риск | Заметка |
| --- | --- |
| Рост `alpha_online` после создания слоя | Sleep-ставка автоматически не догоняет поздний online; при resolve по-прежнему потолок `ratio × alpha_online`. |
| Медленный выход на полную доходность | При `|δ| ≤ 1` выход к `V ≈ 20` при повторном `r = 1` требует много шагов (задумано). |
| Копии `src/` в демо | Патчи только в `src/` репозитория; vendored-деревья синхронизируются вручную. |

---

## 6. Затронутые файлы (реализация, для трассировки)

| Файл | Роль |
| --- | --- |
| `src/agent.py` | `_coerce_feedback_rating`, применение feedback |
| `src/value_layer.py` | `discounted_value_bound`, `effective_alpha_sleep`, `value_abs_bound`, resolve sleep alpha |
| `src/sleep.py` | `_resolved_alpha_sleep`, `_resolved_value_cap` |
| `src/storage.py` | персистентность `alpha_sleep_ratio`, `value_cap` |
| `tests/test_issue18_minor_learning.py` | основные приёмочные тесты этого среза #18 |
| `tests/test_value_layer.py` | порог sleep alpha (`test_sleep_alpha_stays_within_online_ratio`) |
| `tests/test_issue9_sleep_value_replay.py`, `tests/test_qa_pr35_sleep_learning.py` | ожидания sleep replay при capped `alpha_sleep` |

---

## 7. Тесты и верификация

**Основной файл:** `tests/test_issue18_minor_learning.py`

- Дробные reward из feedback (`1.5` → `0.75`, `0.7` → `0.35`).
- Нечисловое / NaN / bool отклоняются; clamp и ±inf.
- Дефолтный и явный `alpha_sleep_default` относительно `0.25 × alpha_online`.
- `discounted_value_bound` и `value_abs_bound` при `γ = 0.95` и `0.5`.
- Таблица держит `V` до новой границы; постоянный `r = 1` online превышает старый `±1`, но не `value_abs_bound`.
- `_resolved_value_cap` поднимает legacy `1` до `20`, уважает больший cap; `reward_scale == 1`.

**Сьют (на момент реализации):** `python -m pytest -q` — **917 passed, 5 skipped**.

**Согласование доков:** [Phase_5_0_Value_Layer_RU_Spec.ru.md](../Phase_5_0_Value_Layer_RU_Spec.ru.md) / `.en.md` — граница `V(s)` обновлена до `|V| ≤ 1/(1−γ)`; `δ_t` по-прежнему `[-1, 1]`.

---

## 8. Критерии приёмки

1. Дробные рейтинги feedback дают `reward = rating/2` без integer-квантизации.
2. Эффективная sleep alpha не превышает `0.25 × alpha_online` (включая clamp ratio).
3. `|V|` может достигать `1/(1−γ)` для unit reward без смены `reward_scale` и без расширения клампа `δ`.
4. Legacy `value_cap = 1` в sleep replay расширяется до gamma-return bound; больший явный cap без изменений.
5. Дневной feedback не пишет стабильную таблицу ценности; консолидация только во сне (инвариант two-tier).
