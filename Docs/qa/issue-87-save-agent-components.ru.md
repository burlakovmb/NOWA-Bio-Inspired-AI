# QA issue #87 — `save_agent` / `load_agent` с `agent=`

Ветка: `fix/issue-87-save-agent-components`. HEAD на момент прогона: `b698959`. База: `89c10a0` (main). Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/87.
English: [issue-87-save-agent-components.en.md](issue-87-save-agent-components.en.md). Спека: [issue-87-save-agent-components.ru.md](../specs/issue-87-save-agent-components.ru.md).

Машина: Windows, Python 3.14.7, pytest 9.2.0, `NOWA_STRICT_LEARNING=1` из `tests/conftest.py`. Базовые прогоны шли на копии `src/` с `src/storage.py` из `89c10a0`; остальной `src/` — дерево ветки (другие файлы `src/` не отличаются).

## Вердикт

**PASS** (`b698959`).

Обученный агент, сохранённый и загруженный только с `agent=`, сохраняет все 8 разделов `stable_payload` и все 9 компонентов аффекта; на базе терялись 2 раздела и 9 компонентов. Загрузка с `agent=` равна загрузке, где все компоненты переданы явно. Объект нейромодуляторов остаётся общим у агента и его менеджера сна. Наборы ядра, Virtual company и Tamagochi проходят.

## Покрытие

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | Обучение не пустое | Pass. 300 решений при `dt = 1.5`, сон после 150-го и 300-го: 128 эпизодов, 483 временные цепочки, 5 строк `slow_affect` |
| 2 | Круг с `agent=` против исходного, `stable_payload` | Pass. Ветка: расходятся 0 из 8 разделов. База: 2 из 8 (`temporal_chains`, `slow_affect`) |
| 3 | Круг с `agent=` против исходного, компоненты аффекта | Pass. Ветка: расходятся 0 из 9. База: 9 из 9 (`neuromodulators`, `affective_persistence`, `affective_background`, `affective_space`, `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation`, `stability_monitor`). `affect_state` при загрузке по замыслу пересчитывается из `affective_space` и проверяется в п. 4 |
| 4 | Загрузка с `agent=` против явной | Pass. Ветка: 0 разделов и 0 из 10 компонентов расходятся, включая `affect_state`. Файлы: все 15 ключей компонентов на месте и равны |
| 5 | Явная загрузка на базе | `stable_payload`: 0 из 8 расходятся; `stability_monitor` расходится (`history.baseline_buffer` после загрузки пуст). Ветка: 0. Исправлено двумя добавленными атрибутами восстановления |
| 6 | Общие нейромодуляторы | Pass. Ветка: `sleep_manager.neuromodulators is agent.neuromodulators` после обеих загрузок. База: `False` после явной загрузки (объект заменялся копией) |
| 7 | Явный аргумент важнее | Pass. `affective_space=` вместе с `agent=`: в файле явный объект; при загрузке данные получает явная цель (stress `0.75`), собственный `affective_space` агента не меняется |
| 8 | Вызывающие | `src/gui.py` и Tamagochi передают все компоненты: без изменений. Virtual company передаёт часть с `agent=`: теперь сохраняет и восстанавливает остальные; её набор проходит |

Новый тест на базовом `storage.py`: 5 failed, 2 passed (проходят предусловие обучения и приоритет явного аргумента). На ветке: 7 passed, три прогона подряд.

```
python -m pytest -q tests/test_issue_87_save_agent_components.py
```

`7 passed in 1.30s`

```
python -m pytest -q tests
```

Ветка: `958 passed, 4 skipped, 1 warning in 564.90s`. База `89c10a0`: `951 passed, 4 skipped, 1 warning in 511.24s`.

```
python -m pytest -q "Demo/Virtual company/tests"
python -m pytest -q "Demo/Tamagochi Chinchilla/tests"
```

`955 passed, 1 skipped, 10 warnings in 224.15s`; `27 passed, 14 warnings in 1.04s`. Прогон Tamagochi перезаписывает отслеживаемые `Demo/Tamagochi Chinchilla/saves/memory.json` и `nowa_state.json`; они возвращены через `git checkout` и в изменение не входят.

## Не прогонялось

- `Demo/Colony chinchillas/tests` и полный `python -m pytest -q`: для Python 3.14 на этой машине нет сборки pygame. Colony не вызывает `save_agent` / `load_agent`.
- `Demo/Warriner Validation`: свои зависимости, API сохранения не использует.

## Дефекты

Нет.

## Вопросы

`emotional_regulation.last_inputs` не восстанавливается в `EmotionalRegulationLayer.from_dict` (`last_time_delta` читается как `1.0`). Эти поля пишутся на каждом шаге и нигде не читаются, поэтому не заведено; тест не включает их в сравнение.

## Готовность к выпуску

Готово по этому чек-листу. CI не дожидались.
