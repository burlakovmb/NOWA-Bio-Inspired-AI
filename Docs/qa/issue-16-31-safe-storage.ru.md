# QA issues #16 и #31 — безопасное версионированное состояние агента

Ветка: `team/issue-16-31-safe-storage`. Код прогона: `1c50cd1`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/71
Issues: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16, https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/31
English: [issue-16-31-safe-storage.en.md](issue-16-31-safe-storage.en.md).

Код продукта в этом проходе не менялся. PR не создавался и не мержился. Полный `pytest` локально не запускался. По условию задачи CI pytest на `1c50cd1` зелёный; Actions в этом прогоне не перечитывались.

Машина: Python 3.12.3, pytest 9.2.0. Пробы и тесты шли с `NOWA_STRICT_LEARNING=1`. Tamagochi: `use_pygame=False`, `use_gui=False`, `SDL_VIDEODRIVER=dummy`.

Решение владельца учтено: старые pickle-сохранения не поддерживаются, миграции нет. Пункт про fallback для старых файлов без `last_decay_ts` закрыт отказом грузить pickle, а не конвертацией.

## Вердикт

**PASS** (`1c50cd1`).

`load_agent`, `load_checkpoint` и `load_mind` отвергают pickle и чужой JSON до вызова чего-либо из файла. Полезная нагрузка `__reduce__` в `os.system` (`touch` файла `/tmp/nowa-qa-16-31-marker`), включая protocol 0 (`cposix`) и сырой GLOBAL `cos\nsystem`, маркер не создала.

Репро затухания из #16 больше не применяет интервал дважды. После часа энергия `0.5485`. Save/load в тот же момент оставляет `0.5485`. Второй `_apply_decay()` в тот же момент оставляет `0.5485` и у непрерывного экземпляра, и у загруженного (раньше у загруженного было `0.30085225`). `last_decay_ts` возвращается как `1790003600.0`, `last_activated` остаётся `1790000000.0`.

Один minor: документ схемы 1, где список эпизодов и паттерны коры — строки, применяется, и `load_agent` возвращает управление. Это не исполнение кода и не срыв приёмки #16 / #31.

## Покрытие

**9 пройдено / 1 провалено / 3 не запускалось.**

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | Вредоносный pickle, schema 99, чужой format, битый JSON, неизвестный тип из закрытого списка в `load_agent`, `load_checkpoint`, `load_mind` | Пройдено. Маркер не появился. Protocol 4: `StateFormatError` / `CheckpointError` `Old pickle saves are not supported and cannot be loaded.` Protocol 0 и сырой GLOBAL: `Unrecognized save format; expected a JSON … document.` Schema 99: `Unsupported schema version 99` (агент и mind читают версию 1, чекпоинт — версию 2). Объект `os.system`: `unknown stored type 'os.system'`. Тег `call`: `unknown state tag 'call'`. Enum с именем `os.system`: `unknown stored enum`. `decode_tree` так же отвергает `subprocess.Popen` |
| 2 | `pickle.load` / `pickle.loads` / `allow_pickle=True` / `eval(` / `exec(` на путях загрузки состояния | Пройдено. Поиск по `*.py` репозитория: этих вызовов нет. `pickle.dumps` есть только в `tests/test_safe_agent_state.py` и `Demo/Virtual company/tests/test_sandbox_checkpoint.py`. В `src/`, `Demo/Virtual company/src` и `Demo/Tamagochi Chinchilla` нет `pickle.load`. `ast.literal_eval` в `gui_configurator_controller.py` к этой загрузке не относится |
| 3 | Эпизоды, привычка, арбитр, лабильный слой: save, load в новый экземпляр, те же давления и победитель | Пройдено. Контекст `["bin", "north"]`: `go` `0.6653165402701486`, `stop` `0.0`, победитель `go` у обоих. Словарь intent и снимок арбитража совпали. Два следа, режим `habitual` |
| 4 | `last_decay_ts`, два save/load в один момент, следующий такой же интервал и один `_apply_decay()` | Пройдено. Энергия после первого часа и после двух циклов save/load: `0.5485` (вес `0.5485`). Второй decay в тот же момент: оба `0.5485`. Следующие 3600 с и один decay: оба `0.30085225`, один и тот же `last_decay_ts` |
| 5 | `_bind_restored_two_tier`, rebind в `Agent.sleep`, файл без `labile_layer` | Пройдено. Живой вклад `ep-1` остаётся на том же объекте слоя, если из файла убран `labile_layer`. Pytest: `test_save_load_restores_labile_clock_and_config`, `test_load_rebinds_sleep_manager_and_consolidates_restored_labile`, `test_sleep_rebinds_manager_when_the_agent_layer_was_replaced` |
| 6 | Sandbox `--resume-from`: квартал, RNG, геном, поставщики stage 1b, привычки | Пройдено. `test_sandbox_checkpoint.py` (геном, RNG, привычки, чужой pickle, схема). `test_resume_extends_the_run` (кварталы `1,2,3,4`). `test_checkpoint_carries_suppliers_across_a_resume` (карта reliability та же). `test_resume_from_missing_checkpoint_raises` |
| 7 | Employee `mind.nowa`, сон после load, onboarding `baseline.nowa` / `cycle-001.nowa` | Пройдено. `test_employee_checkpoint_plasticity.py` (сон после load совпадает со сном без перезагрузки). `test_real_core_sleep_checkpoint_and_reload` пишет `cycle-001.nowa`, фиксирует событие baseline, а `evaluate` грузит `training/baseline.nowa` и `mind.nowa`. `test_legacy_mind_without_intent_extension_still_loads` |
| 8 | GUI save/load на уровне кода и юнита | Пройдено. `save_state` / `load_state` передают `conflict_arbitration`, `intent_memory` и `neuromodulators`. После трёх шагов `to_dict` загруженного объекта совпал: dopamine `0.20119146386152442`, cortisol `0.12385272848128315`, остальные ключи тоже, сравнение не включало `timestamp`. `get_save_files` по-прежнему показывает `.pkl`. `load_agent` на этом файле даёт `StateFormatError` с текстом `Old pickle saves are not supported and cannot be loaded.` `load_selected` ловит `Exception` и кладёт `str(e)` в диалог ошибки. Сам диалог Tk не нажимался. Tamagochi `test_session_persists_runtime_counters` прошёл (`total_sim_time` `123.4`, `tick_count` `321`) |
| 9 | Регрессия storage, выборка существующих тестов | Пройдено. `test_save_load_affect.py`, `test_chains_save_load.py`, `test_conflict_arbitration_storage.py`, `test_agent_lifetime_save_load.py`, плюс `test_safe_agent_state.py`. Весь целевой pytest: **41 passed** за 2.07 с |
| 10 | Документ схемы 1 со строкой вместо списка эпизодов и строкой вместо паттернов | Провал. См. дефект |

Не запускалось:

| # | Сценарий | Почему |
| --- | --- | --- |
| 1 | Полный `pytest` | CI на `1c50cd1` по условию задачи зелёный. Здесь не повторялся |
| 2 | Повторное чтение прогона Actions | В задаче сказано CI не ждать |
| 3 | Клик по диалогу Tk save/load | Проверено юнитом и чтением `load_selected` |

Целевая команда, код выхода 0:

`SDL_VIDEODRIVER=dummy python -m pytest -q --no-header -p no:warnings tests/test_safe_agent_state.py tests/test_issue13_two_tier.py::test_save_load_restores_labile_clock_and_config tests/test_issue13_two_tier.py::test_load_rebinds_sleep_manager_and_consolidates_restored_labile tests/test_issue13_two_tier.py::test_sleep_rebinds_manager_when_the_agent_layer_was_replaced tests/test_save_load_affect.py tests/test_chains_save_load.py tests/test_conflict_arbitration_storage.py tests/test_agent_lifetime_save_load.py "Demo/Virtual company/tests/test_sandbox_checkpoint.py" "Demo/Virtual company/tests/test_employee_checkpoint_plasticity.py" "Demo/Virtual company/tests/test_onboarding.py::test_legacy_mind_without_intent_extension_still_loads" "Demo/Virtual company/tests/test_onboarding.py::test_real_core_sleep_checkpoint_and_reload" "Demo/Virtual company/tests/test_run_sandbox.py::TestCheckpointing::test_resume_extends_the_run" "Demo/Virtual company/tests/test_run_sandbox.py::TestCheckpointing::test_resume_from_missing_checkpoint_raises" "Demo/Virtual company/tests/test_run_sandbox.py::TestStage1bCli::test_checkpoint_carries_suppliers_across_a_resume" "Demo/Tamagochi Chinchilla/tests/test_session_persistence.py"`

## Дефекты

### [MINOR] Документ схемы 1 со строкой вместо списка эпизодов применяется и считается успешной загрузкой

- Шаги: записать UTF-8 JSON с `format` `nowa-agent-state`, `schema_version` `1`, `state.hippocampus_experiences` = `"not-a-list"`, `state.cortex_patterns` = `"not-a-dict"`. Вызвать `AgentStorage.load_agent` на живом `NOWAHippocampus` и `CortexMemory`.
- Ожидалось: `StateFormatError`. Живые эпизоды, сигнатуры и паттерны остаются прежними.
- Факт: вызов вернул `None`. `experiences` стал строкой `not-a-list`, `signatures` стал `[]`, `patterns` стал строкой `not-a-dict`. Исключения нет, поэтому `GUI.load_state` считает загрузку успешной. Код из файла не исполнялся.
- Где: `src/storage.py`, `AgentStorage.load_agent`, присваивания `hippocampus.experiences` и `cortex.patterns`.
- Severity: minor.

## Рекомендации

- До присваивания отвергать документ, если `hippocampus_experiences` не список или `cortex_patterns` не словарь. Покрыть это в `tests/test_safe_agent_state.py`.
- Добавить тест с побочным эффектом: protocol 0 `__reduce__` в `os.system` и сырой GLOBAL `cos\nsystem` на `load_agent`, `load_checkpoint` и `load_mind`. Проверять, что файл-маркер не появился. Сейчас тест пиклит словарь протоколом по умолчанию и смотрит только `load_agent`.
- Тот же файл не покрывает битый JSON, неизвестный `__nowa_type__` и round-trip `to_dict` нейромодуляторов. Тесты чекпоинта покрывают pickle и schema 99 только для `load_checkpoint`.
- Protocol 0 отвергается как обычный не-JSON. Байты не распаковываются через pickle. Расширение `_looks_like_pickle` поменяет только текст ошибки на фразу про pickle.
- `load_agent` по-прежнему глотает ошибки восстановления ряда подсистем, включая intent и арбитраж (`except Exception: pass`). Битый словарь внутри иначе годного файла в этом прогоне не подавался. Имеет смысл тест: сломанный `intent_memory` не должен завершаться успехом с пустым хранилищем привычек.
- Новый round-trip тест проверяет, что затухание непрерывного и загруженного экземпляров совпадает. Историческую пару `0.5485` / `0.30085225` он не фиксирует. Проба её проверила.

## Готовность к релизу

К выпуску по #16 и #31 готово. Minor не возвращает исполнение pickle и не возвращает двойное затухание. Старые `.pkl` по-прежнему не грузятся, это совпадает с решением владельца.
