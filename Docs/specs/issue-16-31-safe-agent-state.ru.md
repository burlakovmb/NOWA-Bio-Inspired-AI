# Issues #16 / #31: безопасное сохранение состояния агента

English: [issue-16-31-safe-agent-state.en.md](issue-16-31-safe-agent-state.en.md)

## Суть

Сохранение и загрузка агента больше не используют Python `pickle`. Состояние пишется в UTF-8 JSON с именованным форматом и целочисленной версией схемы. Закрытый кодек (`src/state_codec.py`) сериализует фиксированный набор типов ядра и обычные контейнеры; содержимое файла ничего не импортирует и не выполняет. Байты, похожие на pickle, отвергаются до разбора JSON.

**Миграции нет.** Старые сохранения агента `.pkl` и pickle-чекпоинты песочницы не открываются. Чекпоинты нужно пересоздать новым прогоном или сохранением из приложения.

## Конверт (все документы)

Один JSON-объект:

| Поле | Смысл |
|---|---|
| `format` | Идентификатор формата (строка) |
| `schema_version` | Целая версия, которую принимает эта сборка |
| `state` | Дерево полезной нагрузки из `encode_tree` |

Чтение: `load_state` → декодирование дерева. Запись: `encode_tree` → `dump_state` (временный файл в каталоге назначения, `fsync`, `os.replace`).

Ошибки — `StateFormatError` (`src/state_codec.py`). Обёртки песочницы и employee переводят её в `CheckpointError`.

### Документ разума агента

| Свойство | Значение |
|---|---|
| Id формата | `nowa-agent-state` (`AGENT_STATE_FORMAT`) |
| Версия схемы | `1` (`AGENT_STATE_SCHEMA_VERSION`) |
| Расширение | `.nowa` |
| API | `read_agent_state`, `write_agent_state`, `AgentStorage.save_agent` / `load_agent` (`src/storage.py`) |

Имя по умолчанию: `agent_save_YYYYMMDD_HHMMSS.nowa`.

### Чекпоинт обучения песочницы

| Свойство | Значение |
|---|---|
| Id формата метаданных | `nowa-sandbox-checkpoint` (`CHECKPOINT_FORMAT`) |
| Версия схемы метаданных | `2` (`CHECKPOINT_VERSION`) |
| Пути | `something.ckpt` и сосед `something.ckpt.agent.nowa` |
| Модуль | `Demo/Virtual company/src/nowa_sandbox/sandbox_checkpoint.py` |

В `.ckpt` — история кварталов, флаги выпуска, состояние RNG, `GenomeVector.to_dict()`, ссылка на sidecar агента. Sidecar — тот же `nowa-agent-state`, что и в ядре (с опциональными расширениями).

### Чекпоинт разума сотрудника

| Свойство | Значение |
|---|---|
| Файл | `mind.nowa` в `nowa_employees/<agent_id>/` |
| Временный файл | `mind.nowa.tmp` |
| Модуль | `Demo/Virtual company/src/nowa_body/employee_checkpoint.py` |

## Allow-list кодека

Зарегистрированные типы (`state_codec._ensure_registry`):

- `Experience`, `Path`, `Event`, `EventType` (`src/experience.py`)
- `EmotionalTrace` (`src/affective_space.py`)
- `SignatureTrace` (`src/hippocampus.py`)
- `CorticalPattern` (`src/sleep.py`)

Контейнеры: `dict`, `list`, `tuple`, `set`, `frozenset`, `collections.deque`, JSON-скаляры. Общие объекты — через теги `__nowa_type__: ref`.

Вне списка тип сериализовать нельзя: `StateFormatError`.

## Что пишет `AgentStorage`

Карта `state` собирается в `save_agent` и восстанавливается в `load_agent`. По issues #16 / #31:

### Гиппокамп (эпизоды + decision store)

- `hippocampus_experiences`, `hippocampus_episode_seq`, `cortex_patterns`, поля селектора.
- При наличии `export_persistent_state` ключ `hippocampus_decision` включает:
  - `signatures` (`last_decay_ts`, `context_tokens`, `context_vector`, `timestamp`, связь с experience через `source_experience`)
  - `recent_event_window`, `novelty_history`
  - `feature_bits` / `token_bits` (из `_feature_bits` / `_token_bits`)
  - `nov_ids` / `nov_valid` (из `_nov_*`)

При load с `hippocampus_decision` вызывается `import_persistent_state`: сигнатуры **не пересобираются**, якоря decay и novelty-кэши сохраняются. Повторный save/load не даёт двойного затухания (`tests/test_safe_agent_state.py`).

Без `hippocampus_decision` сигнатуры сбрасываются, novelty validity обнуляется.

### Слои, которые передают хосты

- Полный `conflict_arbitration` через `ConflictArbitration.to_dict()`.
- `intent_memory` через `IntentMemory.to_dict()`.
- `neuromodulators`, `value_layer`, `sleep_manager`, аффективные подсистемы — при передаче.
- С `agent=`: `labile_layer`, `plasticity_config`, `host_clock_s`, `bg_outcome_slots`, `bg_action_channels`, lifetime/runtime/wakefulness/autonomous.

После load `_bind_restored_two_tier` перепривязывает sleep managers к восстановленным `labile` и `plasticity`.

### Расширения демо (тот же `.nowa`)

| Ключ | Кто пишет | Где |
|---|---|---|
| `sandbox_intent_memory` | `sandbox_checkpoint` | Sidecar чекпоинта песочницы |
| `vc_intent_memory` | `employee_checkpoint.save_mind` | Stop сотрудника |

`load_agent` игнорирует неизвестные ключи; демо применяет расширения после базового restore.

## Отказ (без тихого отката)

| Ввод | Исход |
|---|---|
| Байты pickle | `StateFormatError`: old pickle saves are not supported |
| Не JSON или чужой `format` | `StateFormatError` |
| `schema_version` вне allow-list сборки | `StateFormatError` |
| Метаданные песочницы не v2 `nowa-sandbox-checkpoint` | `CheckpointError` |
| Битое дерево | `StateFormatError` при decode |

`get_save_files` может показывать `.pkl` в каталоге для уборки; `load_agent` их не откроет.

## Потребители

| Потребитель | Путь | Примечание |
|---|---|---|
| GUI ядра | `src/gui.py` | `AgentStorage`; `conflict_arbitration`, `intent_memory`, `neuromodulators`, `agent=` |
| Tamagochi | `Demo/Tamagochi Chinchilla/src/main.py` | `agent_save.nowa`, клетка как `agent=` |
| CLI песочницы VC | `run_sandbox.py` | `--checkpoint` / `--resume-from` для `.ckpt` + sidecar |
| GUI песочницы VC | `gui_app` | То же |
| Хост сотрудника VC | `employee_checkpoint.py` | `mind.nowa` на stop |
| Тесты | `test_safe_agent_state.py` и др. | Round-trip `.nowa` |

## Ограничения (не в файле)

1. **Гиперпараметры конструктора гиппокампа** (например `max_experiences`, константы decay при создании) не пишутся. После load действуют параметры живого объекта; эпизоды и `hippocampus_decision` восстанавливают recall/novelty.
2. **Эпигеном** не входит в чекпоинт песочницы (только genome dict). У employee — то же через `AgentStorage`.
3. **Состояние мира закупок** в чекпоинт песочницы намеренно не входит.

## Связанные документы

- [two-tier-plasticity.ru.md](../architecture/two-tier-plasticity.ru.md)
- [issue-58-sandbox-two-tier-plasticity.ru.md](issue-58-sandbox-two-tier-plasticity.ru.md)
- [API.ru.md](../API.ru.md)