# Issue #65 — Save/load колонии: повторное применение генома и meta наследования

Закрывает #65. PR #66. Связано: [issue-27-inheritance.ru.md](issue-27-inheritance.ru.md) (`genome_inheritance_meta`), [issue-24-silent-failures.ru.md](issue-24-silent-failures.ru.md) (геном и поля зачатия в сохранении).

English: [issue-65-save-genome.en.md](issue-65-save-genome.en.md)

Область: **Colony chinchillas** (`Demo/Colony chinchillas/`), `ColonyStorage` в `colony_storage.py`.

---

## 1. Проблема

После issue #24 в JSON колонии сохранялся `genome` агента, но при загрузке не вызывался `AgentFactory._apply_genome_to_agent`. Фенотип из генов (`axis_decay`, пороги драйвов, half-life нейромодуляторов и т.д.) оставался на дефолтах конструктора, хотя `GenomeVector` в файле был верным. Meta рождения (`genome_inheritance_meta`) не записывалась и не читалась.

---

## 2. Решение

При десериализации: восстановить runtime и affect, назначить `agent.genome`, пересчитать `max_lifespan_age_s`, затем **`_apply_saved_genome`**: вызвать `_apply_genome_to_agent` с `genome.to_agent_params()` и вернуть моментальные **energy**, **social_drive** и концентрации **нейромодуляторов** из файла.

Две новые записи на агента при сохранении:

| Поле | Расположение | Содержимое |
| --- | --- | --- |
| `genome_inheritance_meta` | объект агента верхнего уровня | JSON-копия `agent.genome_inheritance_meta` (пустой dict, если нет). |
| `neuromodulator_levels` | `runtime` | `dopamine`, `norepinephrine`, `serotonin`, `cortisol`, `acetylcholine`, если есть на `agent.neuromodulators`. |

Порядок в `_restore_saved_agent`: runtime (в т.ч. `neuromodulator_levels` при наличии ключа) → affect → genome + lifespan → `_apply_saved_genome` → `genome_inheritance_meta`, если ключ есть.

`SCHEMA_VERSION` по-прежнему `1`; новые ключи опциональны при чтении.

---

## 3. Изменения по файлам

| Файл | Изменение |
| --- | --- |
| `Demo/Colony chinchillas/src/colony_storage.py` | Сериализация `genome_inheritance_meta`, `runtime.neuromodulator_levels`; `_apply_saved_genome`, хелперы NM; при загрузке — `_apply_saved_genome` до meta. |
| `Demo/Colony chinchillas/tests/test_storage.py` | Round-trip темперамента/lineage; legacy без новых ключей; агент без `genome`. |

---

## 4. Обратная совместимость

| Форма сохранения | Поведение загрузки |
| --- | --- |
| Текущее save с геномом и новыми полями | Геном применён; energy, `social_drive`, NM и `genome_inheritance_meta` как до save (`test_storage_roundtrip_keeps_genome_temperament_and_lineage`). |
| Save с `genome`, без `genome_inheritance_meta` / `neuromodulator_levels` | Геном применён; `genome_inheritance_meta == {}`; energy и `social_drive` сохранены (`test_storage_old_save_without_new_fields_reapplies_genome`). |
| Save без ключа `genome` | `genome is None`; дефолтный lifespan колонии; дефолтный `axis_decay` (`test_storage_old_save_without_genome_loads`). |

---

## 5. Известные ограничения

| Тема | Поведение |
| --- | --- |
| **`affective_space.axes["curiosity"]`** | Отдельно не хранится. Сохраняется `affect.boredom`; при загрузке `curiosity = 1.0 − boredom`, а не фактическая ось curiosity до save, если она расходилась с этой связью. |
| **Текущие уровни драйвов `exploration` / `curiosity`** | После `_apply_genome_to_agent` обратно подставляются только **energy** и **social_drive**. Интеграторы автономных драйвов (`exploration`, `curiosity` и др.) пересобираются из baselines генома, а не из сохранённого моментального состояния драйва. |

Концентрации нейромодуляторов **сохраняются** в `runtime.neuromodulator_levels` и восстанавливаются после apply генома.

---

## 6. Тесты и приёмка

**Основной:** `Demo/Colony chinchillas/tests/test_storage.py`

- `test_storage_roundtrip_keeps_genome_temperament_and_lineage` — `axis_decay`, `lambda_reg`, half-life NM, social threshold, energy, NM, meta (`crossover_mode == "uniform"`, без требования к `crossover_alpha`).
- `test_storage_old_save_without_new_fields_reapplies_genome` — из legacy JSON убраны новые ключи; фенотип генома всё равно применяется.
- `test_storage_old_save_without_genome_loads` — без генома семантика как в #24.

**Критерии приёмки:**

1. Загрузка повторно применяет сохранённый геном через `_apply_genome_to_agent`.
2. После apply совпадают energy, `social_drive` и уровни нейромодуляторов из файла.
3. `genome_inheritance_meta` round-trip при наличии в save.
4. Файлы без новых ключей загружаются без ошибки.
