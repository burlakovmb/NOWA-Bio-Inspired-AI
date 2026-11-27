# QA issue #96 — доменно-нейтральный сценарий песочницы

Ветка: `team/issue-96-scenario`. Голова: `2a2046d`. База: `0e486e1` (`origin/main`). Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/96. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/99.
English: [issue-96-scenario.en.md](issue-96-scenario.en.md).

Машина: Linux, Python 3.12.3, pytest 9.2.0. CI фиксирует Python 3.12 (`.github/workflows/tests.yml`). Полный набор не перезапускался; по заданию CI на `d79f516` зелёный.

## Вердикт

**FAIL.**

Этапы 1–4 в ветке. `src/` не тронут. Исправленная заморозка (целый seed, как в `tests/logistics_scenario.py`) прогоняет пять эталонных срезов на настоящем `agent.Agent` и совпадает с `0e486e1` по полям. Зафиксированный эталон этого агента не измеряет. `tools/golden_issue_96.py` сеет незасеянный `random.Random()` кортежем. Python 3.12 кортеж отвергает, `SleepManager` не создаётся, `create_procurement_agent` глотает ошибку и возвращает `_FallbackAgent`. Все пять фикстур — этот fallback: каждое действие `wait_and_monitor`, заказов нет.

## Покрытие

- сценарии: 11 пройдено / 1 провалено / 2 не запускалось

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | Родитель коммита эталона `5e5b165` — `0e486e1`; коммит добавляет только инструмент, тест и пять фикстур | Pass |
| 2 | `--check` сравнивает байты канонического JSON (`sort_keys`, `allow_nan=False`), не `math.isclose` | Pass (тест зелёный; байты — fallback) |
| 3 | Фикстуры 10 дней и 90 дней — ядровый агент | Fail, дефект 1 |
| 4 | Те же пять срезов с целым seed: `agent.Agent`, HEAD равен `0e486e1` (action, supplier, product, qty, result, situation, ценовые токены, фитнес, `cost_vs_chance`, выпуск) | Pass (проба, в набор не входит) |
| 5 | Сторож читает четыре общих модуля и падает, если вставить `supplier` | Pass (вставка откатена, не закоммичена) |
| 6 | YAML без `scenario:`, другое `scenario.name`, `compute_stage_1a_baseline()` без `criteria`, старые `carried_suppliers` / `price_memory` | Pass |
| 7 | `python -m nowa_sandbox.run_sandbox`, один квартал, два дня, seed 42 | Pass, код 0 |
| 8 | Этап 4, логист на общем слое, настоящий агент, два свежих процесса | Pass, дважды |
| 9 | `last_decision_log`, `n_orders`, форма книги котировок | Pass как ограничения, не дефекты (ниже) |
| 10 | `git diff origin/main...HEAD -- src/` | Pass, пусто |
| 11 | Новые тесты дважды; проба с целым seed дважды для seed 42, цена включена | Pass, совпало |

Не запускалось: GUI (вызов в `gui_controller.py` по-прежнему строит `SandboxTrainer` с теми же аргументами). Полный pytest.

Соседний прогон, `-m "not slow"`: `test_issue_96_golden`, `test_issue_96_scenario`, `test_logistics_scenario`, `test_sandbox_config`, `test_stage_baseline`, `test_price_perception`, `test_graduation_non_regression`, `test_staged_graduation`, `test_sandbox_checkpoint`, `test_persistent_suppliers`. Итог: `189 passed in 1.95s`. Только новые файлы: `14 passed` дважды (`1.01s`, `1.00s`).

## Что реально снято в эталон

`_install_freeze` в `Demo/Virtual company/tools/golden_issue_96.py` подменяет `random.Random`. Незасеянный конструктор ставит seed `(42, n)`. На Python 3.12.3:

```text
TypeError: The only supported seed types are: None,
int, float, str, bytes, and bytearray.
```

Трассировка под этой заморозкой, до кварталов:

```text
agent_factory.py:301 SleepManager(...)
sleep.py:293 self._rng = random.Random()
golden_issue_96.py seed((42, n))
```

`sandbox_agent_factory._create_core_agent` ловит `Exception` и возвращает `None`. Дальше `create_procurement_agent` строит `_create_fallback_agent.<locals>._FallbackAgent`. Воркер вызывает `_install_freeze` до `capture_case`, а `capture_case` вызывает `create_procurement_agent`. Фикстуры в коммите написал этот воркер (`5e5b165` кладёт инструмент и фикстуры вместе).

`_FallbackAgent.step` возвращает только `wait_and_monitor`, `urgent_reorder` или `diversify_supplier`. Фикстуры не уходят с первого варианта.

| Срез | Фикстура | Ядро, целый seed (HEAD = `0e486e1`) |
| --- | --- | --- |
| seed 42, цена вкл., 10 дней × 2 | 20 × `wait_and_monitor`, 0 заказов, `cost_vs_chance` 0.0, `cost_efficiency` 0.5 | Q1: 6 заказов, `cost_vs_chance` -0.05331208452168168, `cost_efficiency` 0.310122846568195; среди действий есть `place_order_cheap_supplier` |
| seed 42, цена вкл., 90 дней × 1 | 90 × `wait_and_monitor`, 0 заказов, `cost_vs_chance` 0.0, `cost_efficiency` 0.5 | 34 заказа, `cost_vs_chance` -0.09060087344927437, `cost_efficiency` 0.2728340576406023; смесь `diversify_supplier` 30, `place_order_cheap_supplier` 24, `urgent_reorder` 19, `place_order_reliable_supplier` 9, `wait_and_monitor` 8 |

Без заморозки `create_procurement_agent` возвращает `agent.Agent`. Обычный CLI на fallback не сидит. Тихий `except` в `_create_core_agent` старше этого PR (`sandbox_agent_factory.py` в diff нет). Его включает новая заморозка.

`tests/logistics_scenario.py` кортеж уже обходит (`FROZEN_RANDOM_SEED * 1_000_003 + counter`), журнал двух периодов повторяется. Там создаётся ядровый агент.

## Дефекты

### [CRITICAL] Эталон записывает запасного закупщика, контроль ядра пустой

- **Шаги**: 1) На Python 3.12 запустить воркер `Demo/Virtual company/tools/golden_issue_96.py` (`_install_freeze`, затем `capture_case`). 2) Напечатать класс из `create_procurement_agent`. 3) Прочитать `tests/fixtures/issue_96_golden/*.json`. 4) Повторить те же срезы с целым seed для незасеянного `random.Random()` на `0e486e1` и на HEAD.
- **Ожидалось**: Фикстуры — ядровый агент. Фитнес, `cost_vs_chance`, выпуск и в журнале action / supplier / product / qty / result (и ценовые токены) совпадают с этим агентом.
- **Факт**: Воркер создаёт `_FallbackAgent`. Каждая строка фикстур — `wait_and_monitor` с пустыми supplier, product, qty и result. `cost_vs_chance` равен 0.0. `--check` зелёный, потому что повтор идёт с той же заморозкой. Целый seed даёт `agent.Agent`, заказы и совпадение с `0e486e1` на всех пяти срезах; этих чисел в байтах фикстур нет.
- **Где**: `Demo/Virtual company/tools/golden_issue_96.py` (`_FrozenRandom`), срабатывает через `src/sleep.py` и глотается в `Demo/Virtual company/src/nowa_sandbox/sandbox_agent_factory.py` (`_create_core_agent`).
- **Severity**: critical

### [MINOR] Имена закупочных критериев лежат в общем тренере, сторож их не видит

- **Шаги**: 1) Найти в `scenario_trainer.py` `stockout_avoidance` и `supplier_diversification`. 2) Прогнать сторож `\b(place_order|supplier|product|stock|price|sku|procurement)\b` по этим основам. 3) Вставить голое `supplier` в `scenario.py` и запустить `TestLexiconGuard`.
- **Ожидалось**: Общий тренер не называет шесть критериев закупщика. Сторож падает на закупочных словах в четырёх модулях.
- **Факт**: `_fitness_summary` перечисляет шесть критериев закупщика и использует их, если у вектора есть все шесть атрибутов. Регулярное выражение не совпадает с `stockout_avoidance` и `supplier_diversification` (`\b` не режет `_`, а `stock` внутри `stockout` — не отдельное слово). Голое `supplier` в `scenario.py` роняет тест: `scenario.py contains 'supplier'`. У фитнеса логиста этих шести атрибутов нет, сводка идёт через `as_dict()` (в тесте есть `on_time_share=`).
- **Где**: `Demo/Virtual company/src/nowa_sandbox/scenario_trainer.py` (`_fitness_summary`); `Demo/Virtual company/tests/test_issue_96_scenario.py` (`FORBIDDEN`).
- **Severity**: minor

## Замечания этапа 4 (не дефекты)

- `last_decision_log` заменяется каждый период (`scenario_trainer.py`, присваивание после `_run_single_quarter`). То же присваивание есть на `0e486e1` в `training_loop.py:343`. Инструмент эталона и так идёт по одному кварталу. Логист ведёт свой `journal`. Старое ограничение.
- `graduation_report` копирует `n_orders` (`getattr`, по умолчанию 0). В закупочном отчёте поле уже было (`test_staged_graduation.py` его проверяет). Логист кладёт туда число принятых назначений и ждёт `2`. Домен без атрибута получает 0. Имя закупочное; второй домен из-за него не встаёт.
- `collect_values` / `band_token` / `observe_day` по-прежнему обходят книгу контрагентов: вложенная карта, `status == "ok"`, затем числовое поле. Логист передаёт `nested_field="quotes"` и `value_field="unit_cost"` и общие модули не правит. Доказательство этапа 4 выполнено. Форма книги уже, чем «число на сущности».

## Остальные проверки

- Без `scenario:`: `scenario is None`, стадия `1a`, `price_perception` включено, `supplier_set_count` 4, неизвестный порог `telepathy` отброшен (`TestScenarioConfig` и отдельный YAML).
- `scenario.name: dispatch` сохраняет `on_time` / `telepathy` и стадию `beta`.
- `compute_stage_1a_baseline(quarters)` без `criteria` по-прежнему заполняет `STAGE_1A_CRITERIA` (`test_covers_exactly_the_stage_1a_criteria`).
- `restore_checkpoint_metadata` читает `carried_suppliers` и `price_memory`. Старый документ `{"skus": {"product_000": {"ema": 1.5, "spread": 0.2}}}` восстанавливает эту опору. Метаданные без `price_memory` оставляют память пустой. `checkpoint_metadata()` по-прежнему пишет эти два ключа.
- Пустая книга и небесконечная уплаченная величина оставляют `NumericMemory` пустой. `band_token` без котировок — `cost:R7:average`.
- `PriceMemory` остаётся тонкой привязкой (`unit_price`, `price:`, `product:`, ключ записи `skus`).
- CLI и GUI по-прежнему строят `SandboxTrainer` с прежними аргументами. Дым CLI: `--quarters 1 --days-per-quarter 2 --seed 42 --stage 1a --no-stop-on-graduation --quiet`, код 0. GUI не нажимался.

## Рекомендации

- Починить seed эталона так, как уже сделано у логиста: целое число, не `(42, n)`. Переснять пять фикстур на ядровом агенте и оставить сравнение байтов. Проба с целым seed уже совпала с `0e486e1` на этих срезах, поэтому пересъём на HEAD должен зафиксировать настоящего закупщика, а не новое поведение.
- Не считать зелёный `test_issue_96_golden` доказательством, что выбор мотора, награды и выпуск ядрового агента сохранились.
- По желанию: расширить сторож, чтобы `supplier_diversification` и `stockout_avoidance` в `scenario_trainer.py` его роняли, либо перенести этот формат сводки к плагину закупщика.
- Новые продуктовые тесты на форму книги, `n_orders` и `last_decision_log` не нужны, пока интерфейс не расширяют.

## Готовность к релизу

- нет. Структурное разделение и игрушечный логист прогнаны, проверенные срезы ядра совпали с main, но обязательный эталон за ядром не следит.
