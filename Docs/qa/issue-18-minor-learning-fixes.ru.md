# QA issue #18 — мелкие правки обучения

Ветка: `team/issue-18-minor-learning-fixes`. Раунд 1 проверил HEAD `6322391` (полный `63223915c51a7a3e0637b1b4d8377757978eb5d9`).
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/63
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/18
Спека: [issue-18-minor-learning-fixes.ru.md](../specs/issue-18-minor-learning-fixes.ru.md).
English: [issue-18-minor-learning-fixes.en.md](issue-18-minor-learning-fixes.en.md).

Продуктовые коммиты этого среза: `da6509e` (feedback, sleep alpha, граница `V`), `b03baa7` (спека и Phase 5.0), `6322391` (Phase 5.0.1). Этот проход QA добавил только отчёт. Слияния не было. Новый PR не открывался.

Машина: Python 3.12.3, pytest 9.2.0. Проба шла с `NOWA_STRICT_LEARNING=1` и `PYTHONPATH=src`.

## Вердикт

**PASS** (`6322391`).

`apply_feedback_to_last_experience(1.5)` записывает `reward_signal` `0.75`. `0.7` записывает `0.35`. Целое `2` записывает `1.0`. `NaN` не меняет число эпизодов и уже лежащую награду (`updated=False`). `+inf` записывает `+1`, `-inf` записывает `-1`. Обратная связь наяву оставляет стабильный Q равным `0`. Его двигает сон.

Новый `ValueLayer` имеет `alpha_sleep_default == 0.0075`, то есть `0.25 * alpha_online_default` (`0.03`). Значения конструктора `0.08` и `0.5`, и те же числа, присвоенные перед сном, в сне дают `0.0075`. Save/load сохраняет `alpha_sleep_ratio` `0.1` и на слое, и на `SleepManager`. Старый словарь value layer и старый pickle агента без этого ключа загружаются.

Повтор `reward=1` при `gamma=0.95` поднимает `V` выше `1` (пик `19.999977142975936` за 4000 шагов) и держит его не выше `20`. `reward_scale` остаётся `1.0`. Онлайн `delta_clipped` остаётся в `[-1, 1]` (`td_clip_online` остаётся `1.0`).

Стабильный Q после `sleep(cycles=3)` равен `0.06551004180326182`. После `sleep(cycles=2)` — `0.044164640181267326`. Обе цифры одинаковы после 10 эпизодов и после 80. TD-обновление, tonic/phasic dopamine, следы eligibility и двухъярусное разделение по-прежнему стоят в путях сна и ценности. Ядро по-прежнему ставит wall-clock время, когда нет timestamp или `dt`, а `get_lifetime()` по-прежнему идёт от wall clock.

`python3 -m pytest -q tests`: **917 passed, 5 skipped**, код 0, 212.47 с. Это совпадает со счётчиком в спеке. Тесты Virtual company и Warriner, которые импортируют ядро репозитория, с `-m "not slow and not perf"`: **844 passed, 7 skipped, 6 deselected**, код 0, 3.75 с.

Два края обрезки — minor и вердикт не меняют. Они записаны в дефектах.

## Покрытие

Сценарии: **12 пройдено / 0 провалено / 2 не запускалось**.

| # | Сценарий | Результат |
| --- | --- | --- |
| 1 | `1.5` → `0.75`, `0.7` → `0.35`, целое `2` → `1.0` | Pass. Сохранённые reward и `feedback_rating` совпали |
| 2 | `NaN` не пишет эпизод и не переписывает уже лежащую награду | Pass. `updated=False`, число эпизодов `0→0`, награда остаётся `0.0` |
| 3 | `+inf` → `+1`, `-inf` → `-1` | Pass. Рейтинги `+2.0` и `-2.0` |
| 4 | Обратная связь наяву оставляет стабильный Q равным `0`; сон его двигает | Pass. Q остаётся `0` через `1.5`, `0.7`, `2`, `+inf`, `-inf`. Один цикл сна добавляет `0.022331671875` |
| 5 | Новый `ValueLayer`: `alpha_sleep_default == 0.0075` и `<= 0.25 * alpha_online` | Pass. Online `0.03`, ratio `0.25` |
| 6 | Явные `0.08` и `0.5` не выходят за ratio во сне | Pass. Резолвер и один реальный `sleep(cycles=1)` оба берут `0.0075`. Шаг Q совпадает с дефолтом |
| 7 | Save/load хранит `alpha_sleep_ratio`; старые сохранения грузятся | Pass. Ratio `0.1` и stored default `0.002` проходят круг. Старый словарь и старый pickle без ключа грузятся с ratio `0.25`; legacy `0.08` становится `0.0075`; значение `0.4` остаётся |
| 8 | Повтор `r=1`, `gamma=0.95`: `V` выше `1` и не выше `20`; `reward_scale` остаётся `1`; клип дельты прежний | Pass. Пик `19.999977142975936`, граница `19.999999999999982`, `reward_scale` `1.0`, max `abs(delta_clipped)` `1.0`, значение клипа `1.0`. Прямая запись `100` сохраняет границу |
| 9 | `sleep(cycles=3)` — стабильный Q около `0.066`; два цикла около `0.044` | Pass. `0.06551004180326182` и `0.044164640181267326` и на 10, и на 80 эпизодах. Q наяву остаётся `0` |
| 10 | Биологический путь обучения сохранён; ядро по-прежнему использует wall-clock время | Pass. См. доказательства. Пропущенный `dt` идёт в wall-clock fallback (`host_clock` `1.0` на первом шаге, `_last_step_time` выставлен). `get_lifetime()` был `0.0515` с после короткого ожидания по стене. `ValueLayer.update` с `timestamp=None` записал Unix `last_update_ts` |
| 11 | `python3 -m pytest -q tests` | **917 passed, 5 skipped**, 2 предупреждения, код 0, 212.47 с. Предупреждения: pygame `pkg_resources` и тик роя, который пропускает падающего агента |
| 12 | Тесты Virtual company и Warriner, импортирующие ядро репозитория, `-m "not slow and not perf"` | **844 passed, 7 skipped, 6 deselected**, 10 предупреждений, код 0, 3.75 с |

Не запускалось:

| # | Сценарий | Почему |
| --- | --- | --- |
| 1 | Шесть тестов Virtual company с маркером `slow` или `perf` в `test_sandbox_integration.py` | Фильтр маркеров. Сняты: три теста полного цикла песочницы и три теста бюджета производительности |
| 2 | Слияние и второй PR | Вне этого раунда |

Пропущены внутри демо-прогона, сборка их видела: пять GUI-тестов Tk/Tcl (нет дисплея) и `test_gui_configurator_controller.py`, потому что Drive MCP не опубликован на localhost.

`git status` до этого отчёта: чисто. Этот коммит добавляет только пару QA EN/RU.

## Дефекты

### [MINOR] Больший gamma шага не расширяет сохранённый клип V

- **Шаги**: 1) Собрать `ValueLayer(gamma_default=0.95)`. 2) Вызвать `value_abs_bound(0.99)`. 3) Прогнать 80 шагов `update` с `reward=1`, `gamma=0.99`, `alpha=0.3`, `mode="online"`, `max_update_l2=1`, адаптивный клип выключен.
- **Ожидание**: Раздел 4 спеки: `value_abs_bound()` следит за `gamma_default`, а больший gamma шага может расширить границу. `value_abs_bound(0.99)` равен `99.99999999999991`.
- **Факт**: `update` вызывает `value_abs_bound()` без gamma. `_get_value` и `_set_value` делают то же. Сохранённый `V` останавливается на `19.999999999999982`, границе `gamma_default`.
- **Где**: `ValueLayer.update`, `ValueLayer._get_value`, `ValueLayer._set_value` в `src/value_layer.py`.
- **Серьёзность**: minor

Запрошенный случай `gamma=0.95` поднимается выше `1` и остаётся в пределах `20`. Этот край вне того случая.

### [MINOR] Явный sleep `value_cap` выше старого единичного клипа — это не то, что хранит таблица

- **Шаги**: 1) `ValueLayer()` и `SleepManager.value_cap = 10`. 2) Прочитать `_resolved_value_cap()` при `gamma_default` `0.95` и при `0.5`. 3) `_set_value(..., 10)` при `gamma_default` `0.5`.
- **Ожидание**: Раздел 4 спеки и критерий 4: legacy `value_cap = 1` поднимается до gamma-return bound, а больший явный cap (пример — `10`) сохраняется.
- **Факт**: При `gamma_default` `0.95` `_resolved_value_cap()` равен `19.999999999999982`, поэтому `10` поднимается до gamma-границы. При `gamma_default` `0.5` резолвер возвращает `10.0`, а `value_abs_bound()` равен `2.0`. `_set_value` затем сохраняет `2.0`. Юнит-тест `test_sleep_value_cap_is_at_least_the_gamma_return` проверяет резолвер после установки gamma в `0.5`, поэтому остаётся зелёным.
- **Где**: `SleepManager._resolved_value_cap` в `src/sleep.py`; `ValueLayer._set_value` в `src/value_layer.py`.
- **Серьёзность**: minor

Phase 5.0 в этой же ветке говорит `|V| ≤ 1/(1−γ)`. Таблица следует этой фразе. Пример с сохранением cap `10` для сохранённого `V` не выполняется.

Блокеров, critical и major нет.

## Известные оговорки (не FAIL)

| Тема | Что проверено |
| --- | --- |
| Вещественная граница при `γ = 0.95` | `discounted_value_bound(0.95, 1.0)` равен `19.999999999999982`. Пик за 4000 шагов остаётся ниже этого значения и ниже `20` |
| `> 0.05` после трёх циклов сна | Измеренный Q — `0.06551`. Два цикла дают `0.04416`, это не проходит `> 0.05`, поэтому потерянный цикл по-прежнему валит `test_feedback_commits_one_td_update_and_reaches_the_reward` |
| Первый пропущенный `dt` | Первый шаг без предыдущей метки берёт elapsed `1.0` и затем записывает `time.time()`. Это существующий wall-clock fallback |
| Цифра `2` в спеке | Русская строка проблемы говорит «делением на 2». Английская говорит «halving». Остальные числовые токены совпадают |
| Копии `src/` в демо | Спека говорит, что вендорные копии сохраняют старое квантование. Этот раунд гнал наборы Virtual company и Warriner, которые импортируют `src/` репозитория |

## Рекомендации

- Потолок при `gamma=0.95` и cap sleep-alpha для этого слияния оставить как есть.
- Поздняя правка, которой нужно, чтобы gamma шага расширял сохранённый `V`, должна протащить этот gamma через `update`, `_set_value` и `_get_value`, с тестом, что `gamma=0.99` может пройти дефолтную границу `20`.
- Решить, хранится ли `value_cap` выше `1/(1−γ)`. Сейчас резолвер может вернуть `10` при `γ = 0.5`, а таблица хранит `2`. Согласовать пример в спеке issue с Phase 5.0 или научить таблицу держать более широкий cap, и в любом случае добавить тест записи и чтения.

## Готовность к выпуску

**С оговорками.** Проверки этого раунда проходят, оба набора зелёные, пара спеки EN/RU совпадает по всем числовым токенам, кроме русского слова для halving. Две заметки minor про клип — это продолжение. Они не блокируют дробный рейтинг, sleep-alpha и границу ценности при `γ = 0.95`.

## Вопросы / блокеры

Блокеров нет.

## Доказательства

Символы прочитаны через Serena (`get_symbols_overview`, `find_symbol` с `include_body`, `find_referencing_symbols`): `Agent._coerce_feedback_rating`, `Agent.apply_feedback_to_last_experience`, `Agent._apply_feedback_value_update`, `Agent._advance_host_clock`, `effective_alpha_sleep`, `derived_alpha_sleep`, `discounted_value_bound`, `ValueLayer.__post_init__`, `ValueLayer._resolve_alpha`, `ValueLayer.update`, `ValueLayer.value_abs_bound`, `ValueLayer.to_dict`, `ValueLayer.from_dict`, `ValueLayer._clip_update_delta`, `DopaminergicTDLayer.compute_td_error`, `SleepManager._resolved_alpha_sleep`, `SleepManager._resolved_value_cap`, `SleepManager._apply_replay_td_bg_unlocked`.

`_coerce_feedback_rating` держит конечный рейтинг как float в `[-2, 2]` и ставит `reward_signal = rating / 2`. `NaN`, `bool` и нечисловое значение возвращают `None`. `±inf` возвращает рейтинг `±2` и награду `±1`. `apply_feedback_to_last_experience` возвращается до `_resolve_feedback_experience`, если разбор не удался, поэтому эпизод не создаётся и не переписывается. `_apply_feedback_value_update` вызывает `ValueLayer.update`, и этот писатель сразу выходит, когда `assert_learning_allowed` ложен, то есть в бодрствовании при `NOWA_STRICT_LEARNING=1`.

`ValueLayer.__post_init__` ставит `alpha_sleep_default` через `effective_alpha_sleep` (`min` сохранённой ставки и `alpha_online * ratio`, ratio не выше `0.25`). Replay сна использует `_resolved_alpha_sleep`, который применяет тот же помощник ещё раз. Один цикл сна с stored `0.08`, stored `0.5` и выведенным дефолтом сдвинул Q на `0.022331671875`.

`to_dict` / `from_dict` хранят `alpha_sleep_ratio` (дефолт `0.25`, если ключа нет). `AgentStorage` копирует это поле с восстановленного слоя. Отсутствующий ключ в блобе sleep manager пропускается, поэтому менеджер сохраняет значение конструктора `0.25`.

Онлайн TD по-прежнему клипует через `min(1.0, td_clip_online)`, а `compute_td_error` по-прежнему применяет stress dip и tonic update. Replay сна по-прежнему масштабирует eligibility, credit weight и per-state variance gate, затем клипует через `_resolved_value_cap` и ещё раз внутри `_set_value`. `reward_scale` умножается на награду и остался `1.0` на прогоне в 4000 шагов. Дифф от `24c321e` до `6322391` эти пути не удаляет.

Wall clock, этот дифф его не трогал, и он жив: `ValueLayer.update` берёт `time.time()`, если `timestamp` опущен; replay сна присваивает `value_layer.last_update_ts = time.time()`; `Agent._advance_host_clock` берёт `time.time()`, если `dt` опущен, и пишет одноразовое предупреждение; `get_lifetime()` использует `time.time() - created_ts`.

Документы: числовые токены EN/RU у `Docs/Phase_5_0_Value_Layer_RU_Spec` и `Docs/Phase_5_0_1_Value_Layer_RU_Spec` совпадают (`49` и `90` токенов). Пара спеки issue — по `124` строки. Единственная разница числовых токенов — русское «на 2» для halving.
