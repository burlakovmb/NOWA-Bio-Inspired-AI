# Issue #76 — метрики выпуска песочницы Virtual company

English: [issue-76-vc-graduation-metrics.en.md](issue-76-vc-graduation-metrics.en.md)

Объём: `Demo/Virtual company/src/nowa_sandbox/` и `Demo/Virtual company/configs/default_world.yaml`. Issue [#76](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/76). QA: [issue-76-task1-optionA-qa.ru.md](../qa/issue-76-task1-optionA-qa.ru.md), [issue-76-task2-qa.ru.md](../qa/issue-76-task2-qa.ru.md), [vc76-task3-decision-consistency.ru.md](../qa/vc76-task3-decision-consistency.ru.md).

См. также: двухстадийная программа ([Demo/Virtual company/Docs/v1.1_two_stage_curriculum.ru.md](../../Demo/Virtual%20company/Docs/v1.1_two_stage_curriculum.ru.md)), пластичность хоста песочницы ([issue-58-sandbox-two-tier-plasticity.ru.md](issue-58-sandbox-two-tier-plasticity.ru.md)).

---

## Обзор

Все шесть критериев всегда считаются; от `training.stage` (`1a` / `1b`) зависит, какие из них **гейтят** выпуск. Дефолты в коде и в поставленном YAML согласованы: `procurement_fitness.GRADUATION_THRESHOLDS` и `graduation_thresholds` в `configs/default_world.yaml`.

| Критерий | Стадия | Порог по умолчанию |
| --- | --- | --- |
| `cost_efficiency` | 1a | 0.60 |
| `stockout_avoidance` | 1a | 0.85 |
| `budget_discipline` | 1a | 0.95 |
| `reaction_to_risk_events` | 1a | 0.50 |
| `supplier_diversification` | 1b | 0.40 |
| `decision_consistency` | 1b | **0.79** |

На Stage 1b дополнительно работает сторож нерегрессии по четырём критериям 1a (задача 1 issue #76). Подробности: [issue-76-task1-optionA-qa.ru.md](../qa/issue-76-task1-optionA-qa.ru.md).

---

## Задача 1 (кратко) — честный cost floor на 1b

Stage 1b не должен проходить при вырожденном baseline 1a. Для cost используется `stage_baseline.cost_vs_chance_floor_delta` (по умолчанию `0.03`, допустимо `0.02`–`0.05` в `sandbox_config`). Формула пола и пробы — в QA задачи 1; шесть порогов выпуска выше не меняются.

---

## Задача 2 — восприятие цены (из опыта, не правило)

Код: `price_memory.py`, связка через `training_loop.SandboxTrainer` и `sandbox_encoder.SandboxEncoder`.

### Что видит агент

Для каждого SKU ниже точки заказа энкодер может выдать `price:{product_id}:{band}` после `product:{id}` и `status:below_reorder_point`. Полосы: `cheap`, `average`, `expensive` — не числовая цена.

- **Котировки дня:** среднее `unit_price` со статусом `ok` из той же книги поставщиков, что и у мотора (`visible_unit_prices`).
- **Опорная линия:** EMA уровня и EMA абсолютного отклонения по SKU (`PriceMemory`) только из прошлых видимых котировок и оплаченных цен принятых заказов.
- **Полоса:** `z = (mean_today − ema) / max(spread, PRICE_SCALE_EPS)`, `PRICE_SCALE_EPS = 1e-6`. Строго: `z < −z_threshold` → cheap; `z > z_threshold` → expensive; иначе average. Нет опоры или котировок → `average` (в т.ч. первый день дефицита).

Константы (дефолты = `configs/default_world.yaml`):

| Символ / ключ | Default | Роль |
| --- | --- | --- |
| `DEFAULT_PRICE_MEMORY_ALPHA` / `price_memory_alpha` | 0.1 | обновление EMA |
| `DEFAULT_PRICE_BUCKET_Z` / `price_bucket_z` | 0.5 | ширина полосы |
| `DEFAULT_PRICE_REWARD_GAIN` / `price_reward_gain` | 0.3 | «ощутимая» цена при accept |
| `ACCEPTED_BASE_REWARD` | 0.4 | базовая labile-награда без восприятия или без опоры |

### Порядок по времени (без утечки в тот же день)

1. До решения: `price_refs = price_memory.snapshot()`.
2. Энкодер и felt reward читают только этот снимок.
3. После решения: `price_memory.observe_day(...)` учитывает котировки дня и при необходимости оплаченную цену.

Награда за принятый заказ: `felt_accepted_reward` → `0.4 + gain·clip(−z_paid, −1, 1)` в `[0.1, 0.7]` при дефолтном gain. И store, и feedback на следующий день используют опору момента решения.

### Конфигурация

`training.price_perception` (по умолчанию `true`). CLI `--no-price-perception` отключает: нет токенов `price:`, accept = `0.4`, поведение как до задачи 2 при фиксированных сидах (QA задачи 2). Поле чекпоинта `price_memory` сохраняется в `sandbox_checkpoint`.

Путь цены не читает скрытые поля вроде `base_price_multiplier`; в опору идут только наблюдаемые котировки и оплата.

---

## Задача 3 — согласованность решений по ситуации

Код: доменно-нейтральный `decision_consistency.py`; привязка закупщика — `DEFAULT_CONSISTENCY`, YAML `consistency:`, `ProcurementFitnessEvaluator.consistency`.

### Определение

Среди **принятых** решений (`counted_statuses`) строки группируются по `(entity, situation)`, где `situation` — отсортированное множество токенов контекста, принадлежащих сущности в этот день. Для групп не короче `min_decisions` берётся доля доминирующего `choice`. Итог — сумма счётчиков доминанты, делённая на сумму размеров групп, с отсечкой в `[0, 1]`. Нет ни одной подходящей группы → `neutral` (по умолчанию `0.5`).

`choice` — поле `ConsistencyConfig.choice_field` в записи вызова. Для выпуска используется это значение; отдельно считается старая концентрация по поставщику (Diagnostics).

### `ConsistencyConfig`

| Поле | Дефолт закупки | Смысл |
| --- | --- | --- |
| `entity_field` | `product_id` | id сущности для групп |
| `choice_field` | `action` | строка стратегии, которую мозг передал мотору |
| `attached_prefixes` | `("status:",)` | «прицепленные» токены следуют за ближайшим не-прицепленным токеном той же сущности |
| `counted_statuses` | `("accepted",)` | в зачёт только эти `result.status` |
| `min_decisions` | `3` | минимум строк в группе `(entity, situation)` |
| `neutral` | `0.5` | оценка при отсутствии групп |

В `decision_consistency.py` нет закупочной лексики; логистический пример — `tests/test_decision_consistency.py` (`route_id` / `carrier_id`).

### Токены ситуации

Функция: `situation_tokens(context_events, entity_id, attached_prefixes)`.

- Токен принадлежит сущности `E`, если `str(E)` **совпадает с одним из полей после первого** `:` (тип до первого `:` не сравнивается). Точное совпадение полей, не подстрока (`P1` ≠ `P10`, ≠ `price:P10:…`).
- Токены с префиксом из `attached_prefixes` цепляются к сущности **ближайшего предыдущего** токена без такого префикса. Любой другой не-прицепленный токен между ними **рвёт** связь (`event:…`, `budget:…`).
- Типичная ситуация дефицита (восприятие цены вкл.): `product:{pid}`, `price:{pid}:{band}`, `status:below_reorder_point`. При `price_perception` off токенов `price:` нет.

День без заказа: `entity=None`, `situation=[]`, в счёт не входит.

### Поля decision log

Каждый день в `training_loop` дополняется `decision_fields(call, tool, context_events, config)`:

| Поле | Когда |
| --- | --- |
| `tool` | `place_order`, если был заказ; иначе `None` |
| `entity` | из `entity_field` вызова |
| `choice` | из `choice_field`; для закупки в call есть `action` = тип стратегии в `resolve` |
| `situation` | список из `situation_tokens` для этой сущности |

Старые строки без `choice` читаются через fallback к полям строки.

### Порог 0.79

В поставке: `GRADUATION_THRESHOLDS["decision_consistency"]` и `graduation_thresholds.decision_consistency` в `default_world.yaml`. YAML может переопределить; файлы с `0.60` сохраняют старую планку.

Калибровка (тимлид, пять сидов Stage 1b; issue #76, в [QA vc76-task3](../qa/vc76-task3-decision-consistency.ru.md) **не** перегонялась):

| Baseline | Типичный score | Доля кварталов ≥ 0.79 |
| --- | --- | --- |
| Случайная стратегия | ≈ 0.545 | ≈ 4% |
| Всегда cheap | ≈ 0.990 | ≈ 98% |
| Обучаемый агент (сейчас) | ≈ 0.598 | ниже порога |

QA PR #97: на evaluator Stage 1b `0.789` не проходит, `0.79` проходит; `0.60` не проходит новую планку.

При `choice_field: supplier_id` при чередовании поставщиков на одной стратегии score `0.5`, при `action` — `1.0` на том же логе; **подходящего порога нет** — выпуск сознательно смотрит на **стратегию** (`action`), не на `supplier_id`.

### Диагностика (JSON квартала)

`ProcurementFitnessEvaluator.consistency_diagnostics`:

| Ключ | Смысл |
| --- | --- |
| `decision_consistency` | гейтящая оценка (`choice_field`) |
| `decision_consistency_by_product` | legacy: концентрация `supplier_id` по `product_id` |
| `decision_consistency_situations` | число групп `(entity, situation)` |
| `decision_consistency_decisions_used` | строк в этих группах |

### Другая роль только конфигом

Задать `entity_field`, `choice_field`, `attached_prefixes` под вызов и токены энкодера новой роли. Тот же `ConsistencyConfig` — в `SandboxTrainer` и `ProcurementFitnessEvaluator` (CLI/GUI из YAML). Менять `decision_consistency.py` для будущего «логиста» не обязательно, если лог и токены соблюдают контракт.

---

## Ограничения

Тренер, токены энкодера, `price_memory`, `ORDER_TOOL = place_order` и стадии fitness пока **заточены под закупку**. Перенос метрики на другие роли компании требует доработки хоста, не только YAML; учёт: [issue #96](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/96) (когда заведён).

Старые спеки в `Demo/Virtual company/Docs/NOWA_Procurement_Sandbox_Spec*.md` могут ещё описывать `decision_consistency` с порогом `0.60` и залипанием на `supplier_id`; норматив для #76 — этот документ и дефолты в коде выше.