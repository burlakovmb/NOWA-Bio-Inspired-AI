# Issue #96: доменно-нейтральный слой сценария песочницы

English: [issue-96-sandbox-scenario.en.md](issue-96-sandbox-scenario.en.md)

Отчёт QA (не дублировать): [issue-96-scenario.ru.md](../qa/issue-96-scenario.ru.md). Ветка: `team/issue-96-scenario`, эталон фикстур: коммит `0e486e1` на `main`.

## Аудитория и цель

Руководство для разработчика, который подключает новый симулированный домен к песочнице Virtual company, и для сопровождения закупщика. Описано **фактическое** поведение в `Demo/Virtual company/src/nowa_sandbox/` на ветке issue — не план.

Закупщик остаётся по умолчанию: CLI (`run_sandbox`), GUI, редактор учебного плана и вкладка World по-прежнему закупочные и **не** читают `scenario.name` из YAML. Хост чужого домена сам собирает `ScenarioTrainer(agent, MyScenario(...))`.

---

## Архитектура: общий слой и плагин домена

| Слой | Модули | Роль |
|---|---|---|
| Общий | `scenario.py`, `scenario_trainer.py`, `numeric_memory.py`, `stage_mechanics.py` | Нейтральный цикл дня/периода, EMA-память, выпуск |
| Плагин закупок | `procurement_scenario.py`, `procurement_fitness.py`, `procurement_world.py`, мотор/кодировщик | Мир покупателя, KPI, инструменты |
| Фасад | `training_loop.py` → `SandboxTrainer` | Прежний публичный конструктор; внутри `ProcurementScenario` в `ScenarioTrainer` |
| Обёртка | `price_memory.py` | `PriceMemory` над `NumericMemory` с `record_key="skus"` (прежний ключ) |

`procurement_fitness.py` по-прежнему считает KPI закупщика; выпуск и non-regression по именам критериев делегируются в `stage_mechanics`.

**Сторож лексики** в `tests/test_issue_96_scenario.py` запрещает закупочную лексику в четырёх общих модулях (`scenario.py`, `scenario_trainer.py`, `numeric_memory.py`, `stage_mechanics.py`). Новые домены расширяют плагин или тесты, не эти файлы.

---

## Контракт `Scenario`

Базовый класс: `nowa_sandbox.scenario.Scenario`. Типы: `Observation`, `Call`, `Outcome`.

### Обязательные методы

| Метод | Назначение |
|---|---|
| `observe(world)` | Снимок `Observation` только для чтения |
| `encode(world, tick_result, observation)` | `context_events` для `agent.step` |
| `action_label(intent)` | Намерение агента → строка действия домена |
| `resolve(action, observation, agent)` | Необязательный `Call` (инструмент + аргументы) |
| `apply(world, call, observation)` | `Outcome` (`result`, опционально отложенный `pending`) |
| `store` / `note` / `remember` | Побочные эффекты памяти (по умолчанию no-op) |
| `row(...)` | Одна строка журнала решений за день |
| `evaluate(world, decision_log)` | Фитнес периода (нужен `as_dict()` для сводок) |
| `graduation_report(fitness)` | Отчёт выпуска (через `stage_mechanics.graduation_report`) |
| `config_for_step(world_config, period_index)` | Конфиг шага периода |
| `open_period(config, period_index)` | `(world, labels)` — `labels` попадают в сводку квартала |
| `stage_name()` | Ид ступени для серии (закупщик: `"1a"` / `"1b"`) |
| `minimum_streak()` | Число подряд идущих прошедших периодов для выпуска |

### Опциональный ростер

При `run_quarters(..., carry_roster=True)` и поддержке в сценарии:

- `has_roster()`, `drop_roster()`, `apply_roster(world)`, `capture_roster(world)`, `roster_boundary(period_index, stage_start)`

Ступень 1b закупщика их использует; игрушечный домен может оставить значения по умолчанию (`has_roster()` → `False`).

### Хуки цикла мира по умолчанию

Переопределяйте, если домен не tick/day с `history` и `bankrupt`:

- `halted`, `previous_tick`, `advance`, `day`, `world_summary`, `period_length`, `apply_feedback`, `begin_period`, `trace`, `fitness_line`, `summary_extras`, `non_regression`

---

## Порядок дня внутри периода

Реализация: `ScenarioTrainer._run_single_quarter` (`scenario_trainer.py`). На каждый день до `period_length` или `halted(world)`:

1. Выход при `scenario.halted(world)`
2. `tick_result = scenario.previous_tick(world)`
3. Отложенная обратная связь `pending` с прошлого дня: `scenario.apply_feedback(pending)`
4. `observation = scenario.observe(world)`
5. `tokens = scenario.encode(...)`
6. **Один** `agent.step(tokens, ...)` (`_agent_step`, `dt=86400.0` если поддерживается)
7. `action = scenario.action_label(intent)`
8. `call = scenario.resolve(action, observation, agent)`
9. Если `call` не `None`: `outcome = scenario.apply(...)`; `pending = outcome.pending`; `store` → `note`
10. `scenario.remember(...)`
11. В журнал — `scenario.row(...)`
12. `scenario.trace(...)`
13. `scenario.advance(world)`
14. Каждые `sleep_every_n_days`: сон/консолидация агента

После цикла дней остаточный `pending` сбрасывается через `apply_feedback`.

Оркестрация периода в `run_quarters`: `config_for_step` → `open_period` → ростер → `_run_single_quarter` → `evaluate` → `graduation_report` → флаги серии/выпуска. `last_decision_log` хранит **только последний завершённый период** (как у закупщика до рефакторинга).

---

## `NumericMemory` и `PriceMemory`

`NumericMemory` — EMA уровня и EMA абсолютного отклонения на сущность. Параметры:

| Параметр | Смысл |
|---|---|
| `value_field` | Имя поля в строках котировок/книги |
| `token_prefix` | Префикс токенов диапазона (напр. `price:`, `cost:`) |
| `entity_prefix` | Префикс сущности в контексте |
| `record_key` | Ключ в наблюдении (`PriceMemory`: `skus`) |

Важно: `observe_day`, `band_token`, `felt_reward`, `update`. Эталон обновляется **после** шага решения — сегодняшняя книга котировок не протекает в сегодняшний токен.

Форма книги котировок для `band_token` / `observe_day` задаётся доменом (вложенные `offers` по умолчанию; логист в тестах — своя схема).

---

## Пороги, выпуск, non-regression

Общие функции в `stage_mechanics.py` (имена критериев не зашиты в общем слое):

- `merge_thresholds(raw, defaults)` — лишние ключи YAML отбрасываются при наличии defaults; при `defaults is None` сохраняются все конечные ключи из `raw`
- `graduation_report(vector, thresholds, stage, gating)` — `all_passed` только по именам из `gating`
- `check_non_regression` — вызывается из доменных обёрток фитнеса
- Серии: `current_qualifying_streak`, `period_qualifies`, `roster_period_boundary`

Пороги закупщика — `configs/default_world.yaml` и `procurement_fitness.GRADUATION_THRESHOLDS`; формулы KPI не менялись.

---

## Необязательный YAML `scenario:`

Разбор: `sandbox_config.py` → `ScenarioConfig`. **Без раздела** — поведение закупщика как раньше (`scenario is None`, ступень 1a, price perception, `supplier_set_count` 4).

При наличии:

```yaml
scenario:
  name: procurement   # или другой id для дефолтов памяти
  memory:
    value_field: unit_price
    token_prefix: price
    entity_prefix: product
  consistency:          # опционально; перекрывает верхний consistency
    entity_field: ...
```

Правила:

- `name: procurement` — память `unit_price` / `price` / `product`; поля world/training закупщика по-прежнему действуют
- Любой другой `name` — дефолты `value` / `level` / `entity`; мир YAML сам не переключается (хост подключает класс сценария)
- `run_sandbox`, GUI и curriculum **не** диспетчеризуют по `scenario.name`

---

## Минимальная интеграция

1. Реализовать `MyScenario(Scenario)` с типами мира и фитнеса (см. образец ниже).
2. Память: `NumericMemory(...)` или тонкий подкласс со своими префиксами.
3. Выпуск: `graduation_report(fitness, merge_thresholds(...), stage, gating)` и при необходимости `check_non_regression`.
4. Собрать `ScenarioTrainer(agent, my_scenario, sleep_every_n_days=...)`.
5. Вызвать `trainer.run_quarters(n_quarters=..., world_config=..., carry_roster=...)`.
6. Тесты в `Demo/Virtual company/tests/` (сторож лексики уже защищает общий слой).

### Образец второго домена (только тесты)

Игрушечная логистика — не роль и не YAML-мир:

- Код: `Demo/Virtual company/tests/logistics_scenario.py`
- Тесты: `tests/test_logistics_scenario.py`
- Токены: `route:…`, `status:…`, `cost:…`; инструмент `assign_carrier`; критерии `on_time_share`, `carrier_stability`
- Прямой `ScenarioTrainer` со stub-агентом

Не переносить импорты закупок в общие модули.

---

## Golden gate (регрессия закупщика)

**Задача:** побайтовое сравнение JSON замороженного среза закупщика, чтобы рефакторинг не сдвигал журнал и float-KPI незаметно.

| Часть | Путь |
|---|---|
| Инструмент | `Demo/Virtual company/tools/golden_issue_96.py` |
| Фикстуры | `tests/fixtures/issue_96_golden/*.json` (четыре коротких + опционально `seed42_q1_d90_price_on`) |
| Pytest | `tests/test_issue_96_golden.py` |

### Что заморожено

- `PYTHONHASHSEED=0` (скрипт перезапускает себя, если не задано)
- `random.seed(42)` перед прогоном
- `time.time` → `1700000000.0`; monotonic/perf — счётчик
- ASLR выключен через `setarch -R` (нужен Linux) для стабильного порядка `id()` в ядре
- Несеянный `random.Random()` → целые `42 * 1_000_003 + n` (кортеж на Python 3.12 отвергается и ведёт к fallback-покупателю — **не** валидный golden-агент)

Каждый кейс — **отдельный дочерний процесс**. Кварталы снимаются по одному для чтения `trainer.last_decision_log` (эквивалент одного `run_quarters` с `stop_on_graduation=False`).

### Требование ядрового агента

`_require_core_agent` падает, если фабрика вернула `_FallbackAgent`. Сравнение с fallback не охраняет когнитивный контур. Тесты требуют `core-agent agent.Agent` в stderr и отсутствие `_FallbackAgent`.

### Перегенерация фикстур

Из каталога `Demo/Virtual company/` (Linux, доступен `setarch`):

```bash
PYTHONHASHSEED=0 python tools/golden_issue_96.py --write
PYTHONHASHSEED=0 python tools/golden_issue_96.py --write --include-long
PYTHONHASHSEED=0 python tools/golden_issue_96.py --check --include-long
```

Опции: `--only seed42_price_on,...`, `--out <dir>`. Срез: `configs/default_world.yaml`, ступень `1a`, семена 42 и 3, 10 дней × 2 квартала, price perception on/off; длинный кейс — 90 дней, seed 42, perception on.

Переснимать только при **намеренном** изменении поведения закупщика; указать базовый коммит в сообщении коммита. Фикстуры сняты на `0e486e1`.

---

## Известные ограничения интерфейса (принято)

| Тема | Поведение |
|---|---|
| `last_decision_log` | Перезаписывается каждый период; истории нескольких периодов на тренере нет |
| `n_orders` у вектора фитнеса | Общее имя поля для разных доменов (логист задаёт свою семантику) |
| `band_token` / `observe_day` | Ожидают форму книги котировок; домен обязан её поставить |
| `compute_stage_1a_baseline(..., criteria=None)` | По умолчанию `STAGE_1A_CRITERIA` закупщика; для другого домена передать `criteria` |
| `_fitness_summary` в `scenario_trainer` | Шесть полей закупщика, если есть; иначе `as_dict()` |
| GUI / CLI | Только закупщик; свой entry point для чужого домена |

---

## Связанные пути

| Путь | Примечание |
|---|---|
| `procurement_scenario.py` | `Scenario` закупщика |
| `sandbox_config.py` | разбор `scenario:` |
| `stage_baseline.py` | базис 1a (дефолт критериев закупщика) |
| `Docs/qa/issue-96-scenario.ru.md` | доказательства QA |