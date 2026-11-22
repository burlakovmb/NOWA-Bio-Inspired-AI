# Issue #87 — `save_agent` / `load_agent` берут все компоненты из `agent=`

English: [issue-87-save-agent-components.en.md](issue-87-save-agent-components.en.md)

Ветка `fix/issue-87-save-agent-components`. База: `89c10a0` (main).

Код: `src/storage.py`. Тест: `tests/test_issue_87_save_agent_components.py`.

---

## 1. Проблема

`AgentStorage.save_agent(..., agent=a)` и `load_agent(..., agent=a)` брали из `agent=` только `value_layer`, `conflict_arbitration` и `intent_memory`. Остальные необязательные компоненты сохранялись и восстанавливались, только если вызывающий передавал их по имени. Хост, вызвавший короткую форму, терял данные без ошибки:

- раздел `temporal_chains` в `learning_guard.stable_payload` — цепочки живут в менеджере сна, а `sleep_manager` из `agent=` не брался;
- раздел `slow_affect` в `stable_payload`;
- девять компонентов аффекта: `neuromodulators`, `affective_persistence`, `affective_background`, `affective_space`, `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation`, `stability_monitor`.

Замер на `89c10a0` на агенте из теста (300 решений, 2 сна, 483 временные цепочки): после сохранения и загрузки с `agent=` расходятся 2 из 8 разделов `stable_payload` и все 9 компонентов аффекта.

На том же пути восстановления нашлись ещё два дефекта, они проявляются и при явной передаче:

- **Нейромодуляторы теряют общий объект.** `Agent.__init__` даёт агенту и его менеджеру сна один `NeuromodulatorState`. `load_agent` восстанавливал этот объект на месте, а затем заменял `sleep_manager.neuromodulators` новой копией. После загрузки сон писал свой сдвиг дофамина (`SleepManager`, дофамин во сне) в копию, и бодрствующий агент его не видел.
- **Прогрев базовой линии стабильности начинается заново.** В списке восстанавливаемых полей `emotional_stability` не было `_background_baseline_buffer` и `baseline_warmup_samples`. Пока `baseline_background` равен `None`, монитор копит этот буфер и ставит базовую линию по его медиане. После загрузки буфер был пуст, и прогрев шёл с начала.

---

## 2. Решение

### 2.1 Компоненты из `agent=`

Новая функция модуля `_agent_component(agent, explicit, attribute)`: возвращает явный аргумент, если он не `None`, иначе `getattr(agent, attribute, None)`. `save_agent` и `load_agent` в начале вызывают её для каждого необязательного компонента:

| Аргумент | Атрибут `Agent` |
| --- | --- |
| `affect_state`, `temporal`, `sleep_manager`, `neuromodulators` | то же имя |
| `affective_persistence`, `affective_background`, `affective_space` | то же имя |
| `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation` | то же имя |
| `emotional_stability` | `stability_monitor` (так передаёт `src/gui.py`) |
| `value_layer`, `conflict_arbitration`, `intent_memory` | то же имя (поведение прежнее) |

Явно переданный аргумент по-прежнему важнее. Без `agent=` ничего не меняется. Каждый компонент восстанавливается на месте (атрибуты копируются из `from_dict`), поэтому брать собственные объекты агента безопасно: локальные имена не переприсваиваются.

### 2.2 Общие нейромодуляторы

В `load_agent` `sleep_manager.neuromodulators` заменяется, только если это не тот объект, что уже восстановлен как `neuromodulators`. Менеджер сна с собственным отдельным объектом ведёт себя как раньше.

### 2.3 Прогрев монитора стабильности

`baseline_warmup_samples` и `_background_baseline_buffer` добавлены в список атрибутов, копируемых из восстановленного `StabilityMonitoringLayer`. `from_dict` уже читает оба, пропущены они были только в списке копирования.

### 2.4 Что не меняется

- `affect_state` при загрузке пересчитывается из `affective_space` (блок `# Canon wins` и `Agent._project_legacy_affect_from_affective_space(blend=1.0)`). Это быстрое состояние вне `stable_payload`. Тест сравнивает его с явной загрузкой, а не с исходным агентом.
- `emotional_regulation.last_inputs` (`_last_reward_signal`, `_last_prediction_error`, `_last_policy_entropy`, `last_time_delta`) — входы последнего вызова регуляции. Они пишутся на каждом шаге и нигде не читаются, `from_dict` их не восстанавливает. Тест не включает их в сравнение.

### 2.5 Вызывающие

- `src/gui.py` и демо Tamagochi передают все компоненты явно: изменений нет. У `ChinchillaAgent` нет `affect_state`, поэтому `agent=self` там ничего не добавляет.
- Virtual company (`employee_checkpoint.py`, `sandbox_checkpoint.py`) передаёт часть компонентов и `agent=`. Теперь её сохранения несут также `temporal` (чекпойнт сотрудника), `affective_persistence`, `affective_background`, `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation` и `emotional_stability`, а загрузка их восстанавливает. Схема файла не меняется, старые файлы загружаются как раньше.

---

## 3. Инварианты и тесты

`tests/test_issue_87_save_agent_components.py`, один обученный агент на модуль (300 решений при `dt = 1.5`, сон после 150-го и 300-го решения):

| Инвариант | Тест |
| --- | --- |
| Обучение заполняет `temporal_chains` и `slow_affect` (проверка не пустая) | `test_training_fills_the_sections_the_short_form_used_to_drop` |
| Сохранение с `agent=` пишет все ключи компонентов, равные явному сохранению | `test_agent_only_save_writes_what_the_explicit_save_writes` |
| Все 8 разделов `stable_payload` совпадают с исходными после круга с `agent=` | `test_agent_only_round_trip_keeps_all_stable_sections` |
| 9 компонентов аффекта совпадают с исходными | `test_agent_only_round_trip_keeps_affect_components` |
| Загрузка с `agent=` равна явной загрузке, включая `affect_state` | `test_agent_only_load_matches_explicit_load` |
| `sleep_manager.neuromodulators is agent.neuromodulators` после обеих загрузок | `test_load_keeps_sleep_manager_neuromodulators_shared` |
| Явный аргумент важнее при сохранении и загрузке; собственный компонент агента не трогается | `test_explicit_component_wins_over_agent` |

На базовом `storage.py` падают пять тестов из семи; проходят предусловие обучения и проверка приоритета явного аргумента.

Запуск:

```bash
python -m pytest -q tests/test_issue_87_save_agent_components.py
python -m pytest -q tests
```

---

## 4. QA

Отчёт: [issue-87-save-agent-components.ru.md](../qa/issue-87-save-agent-components.ru.md).

---

## 5. Принцип

Только API сохранения. Правила обучения, гены и константы не менялись; схема файла и её версия прежние.
