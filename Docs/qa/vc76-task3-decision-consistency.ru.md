# QA issue #76 task 3 — decision consistency

Ветка: `team/vc76-consistency-3`. Коммит под проверкой: `efb0bc64bfdc425018dc07101e0081ca4e2616b0` (`Bind decision consistency to the action and set the threshold to 0.79`), он включает `5fc25f00ca37d3df9dbec28a4e74e93633bb52f9`. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/97. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/76.
English: [vc76-task3-decision-consistency.en.md](vc76-task3-decision-consistency.en.md).

Объём — этот head и только узкий чеклист по `Demo/Virtual company/`. Код продукта не менялся. Калибровку тимлида (5 сидов, Stage 1b, random 4% кварталов, always-cheap 98%) не повторял. CI не ждал.

Машина: Linux, Python 3.12.3, pytest 9.2.0. Тесты демо добавляют `Demo/Virtual company/src` и `src/` репозитория через `Demo/Virtual company/tests/conftest.py`. Живые числа ниже сняты одноразовым пробником, в дерево он не входил.

## Вердикт

**PASS.**

На реальном дне энкодера, где `P1` и `P10` оба ниже точки заказа, ситуация каждого SKU — его токен `product:`, его токен `price:` и `status:below_reorder_point`. `P1` не забирает токены `P10`. Реальные токены `event:` и `budget:critical`, поставленные между `product:` и `status:`, отцепляют status от сущности. `--no-price-perception` убирает все токены `price:` из контекста и из ситуации. `choice` — строка стратегии, переданная в `resolve`, в том числе после перезаписи `OrderParams.strategy`. День без заказа хранит `entity=None` и `situation=[]` и в счёт не идёт. Отказы мира (`insufficient_budget`) в счёт не идут; принятые строки идут. YAML без раздела `consistency` получает `DEFAULT_CONSISTENCY`. `choice_field: supplier_id` меняет значение с 1.0 на 0.5 на одном и том же прогоне с чередованием поставщиков. Этот объект конфига доходит до evaluator и trainer и из `run_sandbox.main`, и из `RunController._execute_run`. Graduation Stage 1b на evaluator, который собрал `main`, использует 0.79: 0.789 не проходит, 0.79 проходит, старый порог 0.60 не проходит. В `decision_consistency.py` нет закупочных слов, а тест «логист» проверяет конкретные токены и значение, которое расходится со старым средним по сущности. `pytest` по `Demo/Virtual company/tests` зелёный. `git diff origin/main...HEAD` не трогает `src/`, энкодер, функции награды, мотор и `price_memory.py`. Список `situation` за 90 дней содержит не больше 3 токенов.

## Покрытие

22 проверки пробника, 0 провалов. Полный набор демо: 1023 passed, 7 skipped, код выхода 0.

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | Два SKU, реальный энкодер: `status:` / `price:` не утекают; `P1` и `P10`; `budget:` и `event:` рвут привязку; `--no-price-perception` | Pass |
| 2 | `choice` — стратегия, переданная мотору; пустые дни не считаются; отклонённые строки по-прежнему только вне `accepted` | Pass |
| 3 | Старый YAML получает дефолты; `choice_field: supplier_id` переключает метрику; CLI и GUI доносят конфиг; Stage 1b использует 0.79 | Pass |
| 4 | В `decision_consistency.py` нет закупочных слов; тест «логист» не тавтология | Pass |
| 5 | Полный pytest демо; diff не трогает ядро, энкодер, награду, мотор, `price_memory`; `situation` остаётся коротким списком | Pass |

### 1. Ситуация на выходе энкодера

Мир собран через `ProcurementWorld.from_quarter_spec`: товары `P1`, `P10` (запас 0, reorder point 100) и `other` (запас 5000, reorder point 10), два поставщика, бюджет оставлен на 1% от выделенного, в history лежат demand shock и поздняя поставка. Контекст даёт `SandboxEncoder.encode_daily_context` по `SandboxTrainer._prepare_stock_observation` и `_prepare_supplier_observation`, `price_perception=True`.

Токены по порядку:

`event:demand_shock`, `valence:negative`, `domain:procurement`, `domain:novelty`, `event:order_arrived_late`, `valence:negative`, `domain:procurement`, `domain:risk`, `product:P1`, `status:below_reorder_point`, `price:P1:average`, `product:P10`, `status:below_reorder_point`, `price:P10:average`, `budget:critical`.

`situation_tokens(..., attached_prefixes=("status:",))`:

| Сущность | Ситуация |
| --- | --- |
| `P1` | `price:P1:average`, `product:P1`, `status:below_reorder_point` |
| `P10` | `price:P10:average`, `product:P10`, `status:below_reorder_point` |

`other` токена не даёт. `P1` — подстрока `P10` и `price:P10:average`; разбиение по полям оставляет ситуации разными.

Энкодер пишет события первыми, а `budget:critical` последним, поэтому в этом естественном порядке `status:` по-прежнему стоит сразу после своего `product:`. Те же выпущенные токены, если поставить `event:demand_shock` или `budget:critical` между `product:P1` и `status:below_reorder_point`, оставляют ситуацию `("product:P1",)`.

При `price_perception=False` на том же мире контекст и обе ситуации содержат `product:` и `status:below_reorder_point` и не содержат токена с префиксом `price:`. `resolve_config` на `configs/default_world.yaml` оставляет `training.price_perception` равным true; тот же файл с `--no-price-perception` ставит false. `run_sandbox.main` с этим флагом собрал trainer с `price_perception=False`. За 3 дня этого прогона Stage 1b заказа не было, сохранённые ситуации пустые.

### 2. Choice, дни без заказа, отклонённые решения

Сценарный мозг, 16 дней, действия чередуются: `wait_and_monitor` и `place_order_cheap_supplier`. Обёртка мотора записывает аргумент `action_type` у `resolve`. В каждой строке с заказом `choice == action ==` этот аргумент (`place_order_cheap_supplier`), и `choice` отличается от `supplier_id` (`S1`). Ситуация в строке равна `situation_tokens` от списка контекста, который `step` получил в этот день. После каждого `step` мозг ставит `last_intent` в `RECOMPUTED_LATER`; `choice` остаётся возвращённой стратегией.

Второй прогон после возврата `resolve` переписывает `OrderParams.strategy` в `NOT_THE_ARGUMENT`. Поле strategy до перезаписи равно `place_order_cheap_supplier`. Записанный `choice` остаётся `place_order_cheap_supplier`.

Пустая строка: `action=wait_and_monitor`, `supplier_id=None`, `product_id=None`, `qty=None`, `confidence=None`, `result=None`, `tool=None`, `entity=None`, `choice=None`, `situation=[]`. Таких строк 8. Если их убрать, `value`, `decisions_used` и `situations_used` не меняются.

Каждый второй `place_order` шёл с `budget`, принудительно равным 0, затем бюджет восстанавливался. Мир вернул `status=rejected`, `reason=insufficient_budget` (4 отказа, 4 принятых). Отчёт по полному журналу совпадает с отчётом только по принятым строкам. Три копии одной принятой строки дают 1.0 и `decisions_used=3`. Те же три строки со статусом rejected дают нейтральные 0.5 и `decisions_used=0`. Принятые вместе с отклонёнными по-прежнему используют 3 и дают 1.0.

### 3. Конфиг и порог 0.79

`configs/default_world.yaml` без раздела `consistency:` загружает `DEFAULT_CONSISTENCY`: `entity_field=product_id`, `choice_field=action`, `attached_prefixes=("status:",)`, `counted_statuses=("accepted",)`, `min_decisions=3`, `neutral=0.5`, и `graduation_thresholds.decision_consistency=0.79` из оставшегося ключа порога. Файл, в котором есть только `world.n_products: 4`, получает тот же дефолт consistency и 0.79. Файл, который задаёт только `consistency.choice_field: supplier_id`, сохраняет остальные дефолты consistency.

Восемь принятых заказов, одна повторяющаяся ситуация `["product:P1", "status:below_reorder_point"]`, действие всегда `place_order_cheap_supplier`, поставщик чередуется `S1`/`S2`, `price_perception` выключен:

| `choice_field` | Сохранённый `choice` | `decision_consistency` | `decision_consistency_by_product` | решений в зачёте |
| --- | --- | --- | --- | --- |
| `action` | действие, восемь раз | 1.0 | 0.5 | 8 |
| `supplier_id` | `S1`, `S2`, … | 0.5 | 0.5 | 8 |

Старые строки с `action` и `supplier_id` и без ключа `choice` дают 1.0 при `choice_field=action` и 0.5 при `choice_field=supplier_id`.

`run_sandbox.main` (`--stage 1b`, YAML с `choice_field: supplier_id`, `--no-price-perception`, 1 квартал, 3 дня, код выхода 0) собрал evaluator и trainer с одним общим конфигом: `choice_field=supplier_id`, `price_perception=False`, стадия `1b`, порог 0.79. В JSON сводке квартала есть `decision_consistency_by_product`, `decision_consistency_situations` и `decision_consistency_decisions_used`.

`RunController._execute_run` (без окна Tk) на YAML с `choice_field: supplier_id` положил это поле и в evaluator, и в trainer. `last_thresholds["decision_consistency"]` равен 0.79.

Graduation на evaluator Stage 1b, которого собрал `main`, остальные критерии держались на 1.0:

| `decision_consistency` | критерий пройден | `all_passed` |
| --- | --- | --- |
| 0.789 | false | false |
| 0.79 | true | true |
| 0.60 | false | false |

Stage 1a с той же таблицей порогов и `decision_consistency=0.10` помечает критерий как не гейтящий, `all_passed` равен true.

YAML, который по-прежнему задаёт `graduation_thresholds.decision_consistency: 0.60` и не содержит раздела `consistency`, загружает порог 0.60 и дефолтную привязку. На evaluator Stage 1b из этого файла значение 0.70 проходит. В поставленном файле и в `GRADUATION_THRESHOLDS` стоит 0.79.

### 4. Нейтральность к домену

В `decision_consistency.py` нет совпадений для `product`, `supplier`, `price`, `stock`, `procurement`, `purchase`, `заказ`, `поставщик`, `товар`, `цена`.

`Demo/Virtual company/tests/test_decision_consistency.py` проверяет литералы. `situation_tokens(["route:R10", "status:delayed"], "R1", ("status:",))` пуст. `event:quiet_day` между `route:R7` и `status:delayed` оставляет `("route:R7",)`. Две ситуации на маршруте `R7` с разными перевозчиками дают `value == 1.0` при `by_entity_legacy < 1.0`. Тест не сравнивает `situation_tokens(...)` с самим собой.

### 5. Регрессии

```
python3 -m pytest -q "Demo/Virtual company/tests" --tb=line -p no:cacheprovider
```

`1023 passed, 7 skipped, 10 warnings in 421.92s`, код выхода 0. Пропуски: пять Tk-тестов в `test_gui_configurator_app.py` и `test_set_data_and_clear` в `test_gui_controller.py` (`tkinter` отсутствует), плюс `test_live_drive_discover_with_suport_empty_password` (Drive MCP на localhost нет). Headless-путь контроллера из пункта 3 выполнен.

`git diff --name-only origin/main...HEAD` — одиннадцать файлов этого PR (конфиг, `decision_consistency.py`, fitness, trainer, CLI, GUI, sandbox config и четыре тестовых модуля). Diff по `src/`, `sandbox_encoder.py`, `price_memory.py` и `procurement_motor_adapter.py` пуст. Diff `training_loop.py`, ограниченный `_felt_accepted_reward`, `_apply_order_feedback` и `_store_order_experience`, пуст. Сам `training_loop.py` меняется: строка decision-log и конструктор trainer.

90 сценарных дней, десять товаров, price perception включён: JSON журнала 26070 байт, JSON только прежних полей 16618 байт, 105 дополнительных байт в день. Самый длинный `situation` — 3 токена. Средняя длина 1.03, потому что дни без заказа хранят `[]`.

## Дефекты

Нет.

## Рекомендации

Файл, который по-прежнему фиксирует `graduation_thresholds.decision_consistency: 0.60`, сохраняет эту планку, и тогда 0.70 проходит Stage 1b. В поставленном YAML и в дефолте кода стоит 0.79. `Demo/Virtual company/Docs/NOWA_Procurement_Sandbox_Spec.en.md` всё ещё показывает 0.60. Эта спецификация в чеклист не входила.

## Готовность

Задачу 3 можно принимать. Чеклист на этом head выполнен. Калибровка 0.79 принята как данная и заново не гонялась.
