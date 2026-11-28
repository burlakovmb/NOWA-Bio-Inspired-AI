# NOWA — Изменения и новая функциональность

English version: [CHANGELOG.en.md](CHANGELOG.en.md)

## 2026-11-28 — Virtual company: доменно-нейтральный сценарий песочницы (issue #96)

Документация для разработчика по слою `Scenario` / `ScenarioTrainer` и фасаду `SandboxTrainer` с обратной совместимостью. Поведение закупщика в CLI, GUI и YAML по умолчанию без изменений.

Обновлённые файлы:

- `Docs/specs/issue-96-sandbox-scenario.en.md` (новый)
- `Docs/specs/issue-96-sandbox-scenario.ru.md` (новый)
- `Demo/Virtual company/README.en.md`, `README.ru.md`
- `Demo/Virtual company/Docs/SCIENTIFIC_DESCRIPTION.en.md`, `SCIENTIFIC_DESCRIPTION.ru.md`
- `Demo/Virtual company/Docs/NOWA_Procurement_Sandbox_Spec.en.md` (заметка as-built)

Зафиксировано в текстах:

- контракт `Scenario` и порядок дня в `ScenarioTrainer._run_single_quarter`
- `NumericMemory`, выпуск через `stage_mechanics`, необязательный YAML `scenario:`
- образец логистики в `tests/logistics_scenario.py`
- golden gate: `tools/golden_issue_96.py`, пересъёмка фикстур, требование ядрового агента

Отчёт QA: `Docs/qa/issue-96-scenario.*.md` (не переписывался).

---

## 2026-09-27 — Научное изложение на двух языках

Обновлены входные документы и научные описания установок. В `README.md` сначала идёт английский текст, затем русский. Остальные научные тексты разведены по файлам `*.en.md` и `*.ru.md`, так что ссылка остаётся в выбранном языке.


- `README.md`
- `Docs/SCIENTIFIC_DESCRIPTION.md`
- `Docs/INDEX.md`
- `Docs/START_HERE_NEW.md`
- `Demo/Colony chinchillas/Docs/COLONY_SPEC.md`
- `Demo/Colony chinchillas/Docs/IMPLEMENTATION_DESCRIPTION.md`
- `Demo/Tamagochi Chinchilla/README.md`
- `Demo/Tamagochi Chinchilla/Docs/SCIENTIFIC_DESCRIPTION.md`
- `Demo/Tamagochi Chinchilla/Docs/PROJECT_COMPLETE_SUMMARY.md`
- `Demo/Virtual company/README.md`
- `Demo/Virtual company/Docs/SCIENTIFIC_DESCRIPTION.md`
- `Demo/Warriner Validation/Docs/SCIENTIFIC_DESCRIPTION.md`

Нормативные спецификации установок получают двуязычное научное предисловие и сохраняют контрактный текст. Документы ядра в `Docs/` (кроме препринта и нового научного изложения) открываются двуязычным статусом; ниже него сохранена исходная редакция контракта или лабораторной записи. Инвентарь фаз `Docs/ARCHITECTURE_UPDATED.md` и указатели `Docs/00_INDEX.md`, `Docs/00_INDEX_NEW.md` помечены как исторические.


---

## 2026-03-26 — Реализация SwarmEnvironment (Package E) и синхронизация документации

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/GENOME_VECTOR.md`
- `Docs/SWARM_ENVIRONMENT.md` (новый)
- `Docs/CHANGELOG.md`

Основные обновления:
- В документацию добавлено покрытие Package E для `src/swarm.py`:
 - пространственная модель (`Position3D`, `SpaceBounds`)
 - социальная сигнализация (`SocialSignal`, ослабление, множитель спящего источника)
 - поведение такта автономного сна и пробуждения и метрики роя
- Задокументировано поведение отката к контексту по умолчанию, когда `context_events_fn` не задана:
 - `agent_active/agent_sleeping`
 - `wakefulness_high/mid/low`
 - события социальных маркеров от входящих сигналов
- Документация GenomeVector синхронизирована с новым геном:
 - `dr_perception_radius_factor`
 - `to_agent_params()["autonomous"]["perception_radius_factor"]`
- Добавлено отдельное руководство по реализации:
 - `Docs/SWARM_ENVIRONMENT.md`
- Обновлены команды тестирования и снимок проверки, чтобы включить целевые тесты Package E.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `701 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон SwarmEnvironment: `37 passed` (`pytest -q tests/test_swarm_environment.py`).
- Целевой прогон GenomeVector: `17 passed` (`pytest -q tests/test_genome_vector.py`).

---

## 2026-03-25 — Синхронизация документации FitnessEvaluator (Package D)

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`
- `Docs/FITNESS_EVALUATOR.md` (новый)

Основные обновления:
- В корневой указатель и указатели документов добавлены ссылки на Package D.
- Добавлено покрытие API для `src/fitness.py`:
 - `FitnessVector`, `ParetoRank`, `FitnessEvaluator`
 - контракт критериев, весов и констант
 - ранжирование Парето и поведение скалярного отката
- Добавлен явный контракт исполнения для скользящих историй приспособленности в `Agent.step(...)`:
 - `affective_history`
 - `td_error_history`
 - `cortisol_history`
- Добавлено отдельное руководство по реализации Package D: `Docs/FITNESS_EVALUATOR.md`.
- Команды тестирования и снимок проверки синхронизированы с текущим прогоном.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `681 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон FitnessEvaluator: `21 passed` (`pytest -q tests/test_fitness.py tests/test_fitness_agent_integration.py`).

---

## 2026-03-25 — Реализация AgentFactory (Package C) и синхронизация документации

Обновлённые файлы:
- `src/agent_factory.py`
- `tests/test_agent_factory.py`
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/AGENT_FACTORY.md`
- `Docs/CHANGELOG.md`

Основные обновления:
- Добавлена реализация Package C в `src/agent_factory.py`:
 - публичный API `AgentConfig` и `AgentFactory`
 - пути порождения: `spawn`, `spawn_random`, `spawn_default`, `spawn_child`
 - пути извлечения: `extract_genome`, `extract_epigenome`
 - устойчивые помощники применения, инъекции и восстановления генома с отказоустойчивостью через предупреждения
- Добавлен набор проверки Package C `tests/test_agent_factory.py`:
 - TC-01..TC-16 из `Docs/SPEC_C_AgentFactory.md`
 - дополнительный тест согласованности кругового прохода отображения матрицы нейромодуляторов
- Добавлено отдельное руководство `Docs/AGENT_FACTORY.md`.
- Синхронизированы ссылки проектной документации, поверхность API и команды тестирования для Package C.
- Снимок проверки в документах обновлён до текущего базового прогона.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `660 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон AgentFactory: `17 passed` (`pytest -q tests/test_agent_factory.py`).
- Целевой прогон GenomeVector: `17 passed` (`pytest -q tests/test_genome_vector.py`).
- Целевой прогон EpigenomeSnapshot: `16 passed` (`pytest -q tests/test_epigenome_snapshot.py`).

---

## 2026-03-24 — Реализация EpigenomeSnapshot и синхронизация документации

Обновлённые файлы:
- `src/epigenome.py`
- `tests/test_epigenome_snapshot.py`
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/EPIGENOME_SNAPSHOT.md`
- `Docs/GENOME_VECTOR.md`
- `Docs/CHANGELOG.md`

Основные обновления:
- Добавлена реализация Package B в `src/epigenome.py`:
 - неизменяемые структуры данных: `InheritedPattern`, `InheritedAction`, `InheritedValue`, `EpigenomeSnapshot`
 - API извлечения из сырых словарей с отбором верхних N и фильтрацией по порогу
 - API инъекции на месте с ограниченным шумом и политикой слияния, безопасной при конфликте
 - API смешения для наследования от двух родителей с ограниченным выходом и усечением линии
 - сериализация (`to_dict/from_dict`) и диагностика (`validate/summary/size/is_empty`)
- Добавлен набор проверки Package B `tests/test_epigenome_snapshot.py`:
 - TC-01..TC-16 из `Docs/SPEC_B_EpigenomeSnapshot.md`
- Добавлено отдельное руководство `Docs/EPIGENOME_SNAPSHOT.md`.
- Синхронизированы ссылки проектной документации, поверхность API и команды тестирования для Package B.
- Снимок проверки в документах обновлён до текущего базового прогона.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `643 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон GenomeVector: `17 passed` (`pytest -q tests/test_genome_vector.py`).
- Целевой прогон EpigenomeSnapshot: `16 passed` (`pytest -q tests/test_epigenome_snapshot.py`).

---

## 2026-03-24 — Синхронизация документации GenomeVector

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/GENOME_VECTOR.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Добавлено документальное покрытие реализованной функциональности генома Package A в `src/genome.py`.
- Добавлено отдельное руководство по реализации `Docs/GENOME_VECTOR.md`:
 - `GeneDescriptor`, детерминированный `GENE_REGISTRY`, API `GenomeVector`
 - режимы мутации и скрещивания (`arithmetic`, `uniform`, `sbx`)
 - сериализация и контракт отображения `to_agent_params()`
 - гарантии детерминизма и безопасности диапазонов
- Справочник API обновлён явным разделом `GenomeVector` и инвариантами.
- Руководство по тестированию и корневой README обновлены новой целевой командой:
 - `pytest -q tests/test_genome_vector.py`
- Значения снимка проверки синхронизированы с текущими прогонами тестов.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `627 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон GenomeVector: `17 passed` (`pytest -q tests/test_genome_vector.py`).

---

## 2026-03-24 — Синхронизация документации модуляции конфликта ACC

Обновлённые файлы:
- `README.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_acc_conflict_modulation.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- API `NeuromodulatorState.update_from_signals(...)` синхронизирован с реализованным поведением ACC:
 - расщеплённые каналы конфликта (`cognitive_conflict`, `affective_conflict`)
 - общая шкала времени `dt` для сглаживания ACC и обновления поля взаимодействия
 - совместный след конфликта как метрика состояния ACC
 - примечания о сохранении и обратной совместимости следов ACC
- В спецификацию ACC добавлен раздел статуса реализации с текущей механикой стабилизации:
 - ограниченные дельты усиления
 - торможение серотонином
 - мягкая нормализация
 - гомеостатическое затухание NE и CORT
 - временная динамика на основе следов
- Команды регрессионных тестов нейромодуляторов обновлены и включают:
 - `tests/test_acc_conflict_modulation.py`

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `610 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон взаимодействия нейромодуляторов: `44 passed` (`pytest -q tests/test_acc_conflict_modulation.py tests/test_neuromodulators_phase2.py tests/test_neuromodulator_integration.py tests/test_neuromodulator_interaction_layer.py`).

---

## 2026-03-23 — Синхронизация документации Process C бодрствования

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/00_INDEX.md`
- `Docs/00_INDEX_NEW.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_basal_ganglia_integration.md`
- `Docs/Phase2_Wakefulness_PFC_Extension.md`
- `Docs/spec_circadian_process_c.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Синхронизирована документация wakefulness с реализованной моделью Process S + Process C.
- Зафиксированы формулы:
 - `C(t) = A * sin(2πt / T + phase)`
 - `wake_drive = C - S`
 - `alertness = base - S + C`
- Обновлена семантика cognitive reliability:
 - основной путь: `get_cognitive_reliability()` (через alertness с clamp)
 - fallback `(1 - wakefulness)` оставлен как legacy-совместимость.
- Уточнены persistence-поля wakefulness/circadian в API и storage-документации.
- Обновлены индексные страницы документации с ссылкой на `spec_circadian_process_c.md`.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `595 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон бодрствования и циркадного процесса: `44 passed` (`pytest -q tests/test_wakefulness.py tests/test_agent_lifetime_save_load.py`).

---

## 2026-03-22 — Синхронизация документации слоя взаимодействия нейромодуляторов

Обновлённые файлы:
- `Docs/NEUROMODULATOR_INTERACTION_LAYER.md`
- `Docs/API.md`
- `Docs/INDEX.md`
- `Docs/TESTING.md`
- `Docs/NEUROMODULATORS_QUICK_REFERENCE.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Добавлена отдельная документация по `NeuromodulatorField` и связанной динамике `DA/5HT/NE/ACh`.
- Зафиксирована реализованная формула baseline-centered coupling:
 - `dM/dt = base_signal + W * (M - baseline) - decay * (M - baseline)`
- Обновлён API-раздел нейромодуляторов:
 - `NeuromodulatorField`
 - обновлённый `NeuromodulatorState.update_from_signals(...)`
 - сериализация/десериализация `interaction_field`
- Обновлены индекс и testing guide:
 - добавлены ссылки и команды на interaction-layer regression bundle.
- Синхронизирован `NEUROMODULATORS_QUICK_REFERENCE.md` с текущим интерфейсом и поведением.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `589 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон взаимодействия нейромодуляторов: `29 passed` (`pytest -q tests/test_neuromodulators_phase2.py tests/test_neuromodulator_integration.py tests/test_neuromodulator_interaction_layer.py`).

---

## 2026-03-22 — Синхронизация документации замены семантического сходства

Обновлённые файлы:
- `Docs/API.md`
- `Docs/Phase_5_0_1_Value_Layer_RU_Spec.md`
- `Docs/INDEX.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Синхронизировано описание `state_similarity`/`state_vector` с реализованным
 deterministic semantic hashing в `src/value_layer.py`.
- Добавлено формальное описание алгоритма для текстовых признаков:
 - токенизация (`eat_food -> ["eat", "food"]`)
 - стабильные unit-векторы слов через hash
 - усреднение и нормализация фразового вектора
 - cosine similarity для сопоставления состояний
- Обновлён общий индекс документации:
 - добавлена спецификация `spec_semantic_similarity_replacement.md`
 - актуализирован timestamp и verification snapshot.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `584 passed, 3 skipped` (`pytest -q tests`).

---

## 2026-03-22 — Синхронизация документации медленного тонического дофамина

Обновлённые файлы:
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Документация ValueLayer синхронизирована с реализованным поведением медленного тонического дофамина:
 - тонический уровень отслеживает фильтрованное фазическое среднее через `tonic_slow_rate` (по умолчанию `0.01`)
 - стресс CER управляет базой тонической цели (мгновенного скачка тонического уровня нет)
 - диагностика обновления во время исполнения теперь включает `mean_phasic`
- Добавлена документация полей снимка и сохранения для тонической динамики:
 - `td_tonic_slow_rate`
 - `td_phasic_mean`
 - `td_tonic_target_base`
- Архитектурные заметки и пределы исполнения обновлены с учётом разделения фазического и тонического компонентов.
- Список покрытия тестов Phase 5.x расширен сценариями дрейфа тонического уровня и сохранения.
- Дата и счётчики проверки в документах ядра обновлены.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `580 passed, 3 skipped` (`pytest -q tests`).

---

## 2026-03-21 — Синхронизация документации поосевого аффективного затухания

Обновлённые файлы:
- `README.md`
- `Docs/spec_per_axis_affective_decay.md`
- `Docs/affective_core_phase4_spec.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/START_HERE_NEW.md`
- `Docs/INDEX.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Документы Phase 4 синхронизированы с реализованной моделью поосевой инерции (`axis_decay`, псевдоним `affective_decay`).
- Устаревшая формулировка «единая `alpha` для всех осей» заменена уравнением обновления, специфичным для оси.
- Добавлены задокументированные значения по умолчанию для биологически различных шкал времени:
 - `valence=0.92`, `arousal=0.80`, `dominance=0.97`
 - `stress=0.75`, `curiosity=0.78`, `trust=0.95`
- Задокументирована унаследованная совместимость (`pleasure -> valence` и связанное отображение псевдонимов осей).
- Обновлены ссылки на сохранение, загрузку и покрытие тестами для новых полей.
- Страницы входа и указатели синхронизированы, чтобы показать новые документы Phase 4, и обновлены счётчики основного набора.
- Синхронизированы быстрая навигация корневого README и сводка поведения Phase 4.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `578 passed, 3 skipped` (`pytest -q tests`).

---

## 2026-03-21 — Синхронизация документации HIE-003 (обновление документов проекта)

Обновлённые файлы:
- `README.md`
- `Docs/API.md`
- `Docs/INDEX.md`
- `Docs/TESTING.md`
- `Docs/spec_deliberative_planning_v2.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Документы исполнения обновлены: от планирования только HIE-002 к древесному режиму HIE-003 с резервом HIE-002.
- Задокументированы новые органы управления воображением:
 - `imagination_enable_action_sequences`
 - `imagination_action_branching`
 - `imagination_max_tree_nodes`
 - `imagination_action_temperature`
 - `imagination_value_backup`
- Обновлено правило агрегации планирования:
 - от `max(memory_rollout, imagined_value)` к смеси
 - `rollout_value = (1 - imagination_value_blend) * memory_rollout + imagination_value_blend * imagined_value`
- Добавлены поля телеметрии планирования:
 - `planning_imagination_tree_nodes`
 - `planning_imagination_tree_edges`
 - `planning_imagination_action_count`
 - `planning_imagination_branching`
- `tests/test_hie_003.py` добавлен в регрессионные наборы воображения и планирования.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `575 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон решения, планирования и кредита: `68 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_imagination_engine_spec_001.py tests/test_hie_002.py tests/test_hie_003.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).
- Целевой прогон HIE: `15 passed` (`pytest -q tests/test_imagination_engine_spec_001.py tests/test_hie_002.py tests/test_hie_003.py`).

---

## 2026-03-21 — Синхронизация документации HIE-002 (обновление документов проекта)

Обновлённые файлы:
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/INDEX.md`
- `Docs/TESTING.md`
- `Docs/spec_deliberative_planning_v2.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Документы уровня проекта обновлены от базовой линии HIE-001 к поведению исполнения HIE-002.
- Задокументирована интеграция `generate_structured_imagination(...)` в обдуманное планирование с оболочкой совместимости HIE-001.
- Обновлены ограничители сложности воображения:
 - `samples <= 8`, `depth <= 5`, `branching <= 4`
 - `max_graph_nodes <= 96`, `max_graph_edges <= 192`
 - уверенность траектории ограничена интервалом `[0, 1]`
- Добавлены новые поля телеметрии планирования:
 - `planning_imagined_trajectory_count`
 - `planning_imagined_confidence_mean`
 - `planning_imagined_novelty_mean`
- `tests/test_hie_002.py` добавлен в регрессионные наборы и в целевые команды тестов воображения.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `571 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон решения, планирования и кредита: `64 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_imagination_engine_spec_001.py tests/test_hie_002.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).
- Целевой прогон HIE: `11 passed` (`pytest -q tests/test_imagination_engine_spec_001.py tests/test_hie_002.py`).

---

## 2026-03-20 — Синхронизация документации HIE-001 (обновление документов проекта)

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_deliberative_planning_v2.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Ссылки на HIE-001 добавлены на главные страницы навигации и указателя.
- Задокументирована реализованная интеграция `HippocampalImagineEngine` в планирование:
 - `rollout_value = max(memory_rollout, quantile(imagined_rollouts, 0.7))`
 - жёсткие пределы ветви воображения (`samples/depth/branching/max_nodes`)
 - поведение бонуса новизны и ограниченные условия остановки.
- В документы API и спецификации добавлены поля телеметрии планирования для воображения.
- Целевые тестовые наборы и счётчики проверки обновлены с `tests/test_imagination_engine_spec_001.py`.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `566 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон решения, планирования и кредита: `59 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_imagination_engine_spec_001.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).
- Целевой прогон HIE: `6 passed` (`pytest -q tests/test_imagination_engine_spec_001.py`).

---

## 2026-03-20 — Синхронизация документации реализации обдуманного планирования v2

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Спецификация обдуманного планирования v2 добавлена в основную навигацию и указатель документации.
- Задокументирован реализованный контракт `DecisionArbitrator`:
 - состав неопределённости и EMA
 - переключение режима с гистерезисом
 - температура политики, ведомая неопределённостью
 - связь надёжности политики с причинностью и устойчивостью воспроизведения
- Задокументировано поведение обдуманного планирования v2 в `Agent.step()`:
 - эпизодические кандидаты, отфильтрованные по сходству
 - глубина прогона, адаптивная к неопределённости
 - ценность прогона как максимум дисконтированного возврата траектории
 - бонус исследования по ценности информации (`gain * (1 - confidence)`)
 - предохранители (`support >= 0.05`, `confidence >= planning_min_confidence`)
 - ограничители сложности (`actions <= 32`, `samples <= 8`, `depth <= 6`)
 - поля метаданных и телеметрии планирования: глубина, число образцов и факт использования прогона, среднее бонуса исследования
 - смещение только давления (планирование не ослабляет температуру политики)
- Задокументировано поведение присвоения кредита при воспроизведении:
 - причинная глубина с привязкой к награде
 - приоритет выбора якоря (награда -> TD-шок -> откат к середине)
 - диагностика следа соответствия и окна кредита в статистике сна и в `Agent.get_state()`
- Обновлены счётчики проверки в документах верхнего уровня и в руководстве по тестированию.

Статус проверки, отражённый в документах:
- Прогон ядра (без Demo): `560 passed, 3 skipped` (`pytest -q tests`).
- Целевой прогон Spec 011/011a: `53 passed` (`pytest -q tests/test_decision_arbitration_spec_011.py tests/test_credit_assignment_spec_011a.py tests/test_deliberative_planning_spec_011.py tests/test_sleep_replay_td_bg.py tests/test_value_layer.py`).

---

## 2026-03-17 — Синхронизация EDPC и SAC и обновление документации

Обновлённые файлы:
- `src/sleep.py`
- `src/value_layer.py`
- `src/selector.py`
- `src/storage.py`
- `tests/test_edpc_sac_synchronization.py`
- `Docs/spec_edpc_sac_synchronization.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления реализации:
- Синхронизация EDPC и SAC только во сне (перенос EMA и обновления устойчивости на основе TD).
- Допуск по конфликту с `conflict_flag` и сбросом на каждый цикл сна.
- Соблюдение энергетического бюджета с нормированной стоимостью приоритета воспроизведения.
- Разделение оценки шока предсказания и флага.
- Рост `td_variance` в REM ограничен интервалом `[0, 1]`.
- Память ожидания ведётся как `OrderedDict` для обновлений, безопасных в смысле LRU.

Статус проверки:
- Целевой прогон синхронизации и EDPC: `21 passed` (`pytest -q tests/test_edpc_sac_synchronization.py tests/test_phase_5_edpc.py tests/test_value_layer.py tests/test_value_layer_storage.py`).

---


## 2026-03-03 — Ужесточение SAC SWS/REM и обновление документации

Обновлённые файлы:
- `src/sleep.py`
- `src/storage.py`
- `tests/test_semantic_action_consolidation.py`
- `tests/test_sleep_replay_storage.py`
- `README.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления исполнения, отражённые в документах:
- Разделение фаз SAC теперь включает строгие жёсткие ограничения и явный предохранитель одной фазы на действие.
- Глобальная фаза SAC выводится из строк, фактически пригодных к обновлению (после допуска и проверок предусловий).
- Допуск SAC на уровне эпизода применяется до агрегации фаз.
- Взвешивание воспроизведения использует гибридную формулу качества и приоритета:
 - `weight = replay_priority * confidence * stability * (1 - shock)`
- Добавлен пол устойчивости REM:
 - `sac_stability_floor_rem`
- Добавлен сброс жизненного цикла структурного предупреждения после спокойных циклов:
 - `sac_structural_alert_reset_cycles`
- Добавлен предел шага семантической уверенности за цикл:
 - `sac_semantic_confidence_step_cap`
- Добавлено покрытие сохранения новых параметров SAC в круговом проходе хранилища.

Статус проверки:
- Полный прогон проекта: `519 passed, 3 skipped` (`pytest -q`).
- Целевой прогон SAC и хранилища: `16 passed` (`pytest -q tests/test_semantic_action_consolidation.py tests/test_sleep_replay_storage.py`).

---

## 2026-03-03 — Интеграция SAC, пол дисперсии и синхронизация документов

Обновлённые файлы:
- `src/selector.py`
- `src/agent.py`
- `src/sleep.py`
- `src/storage.py`
- `tests/test_semantic_action_consolidation.py`
- `tests/test_sleep_replay_storage.py`
- `Docs/spec_semantic_action_consolidation.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления реализации:
- Реализована семантическая консолидация действий (SAC) в `SleepManager`:
 - семантические обновления только во сне по `action_id` в `selector.action_metadata`
 - допуск воспроизведения по уверенности, устойчивости, шоку и вероятности консолидации
 - взвешенная агрегация наблюдаемых и предсказанных исходов и бета-обновления успеха и неудачи
 - жёсткие ограничения (`sac_alpha_slow <= 0.01`, блокировка по среднему шоку, минимальное число воспроизведений)
 - диагностика SAC во время исполнения (`sac_rejected_*`, индексы дрейфа, роста и избыточной уверенности)
- Добавлен пол дисперсии против кристаллизации:
 - `sigma_new = max(sac_sigma_floor, sigma_new)`
 - по умолчанию `sac_sigma_floor = 0.01`
- Добавлена поддержка сохранения:
 - `selector_action_metadata`
 - конфигурация `sac_*` и `last_sac_stats` на пути сохранения и загрузки хранилища
- Добавлено покрытие тестами SAC (включая сценарий пола дисперсии) и расширены проверки кругового прохода хранилища.

Статус проверки:
- Полный прогон проекта: `512 passed, 3 skipped` (`pytest -q`).
- Целевой прогон SAC и хранилища: `9 passed` (`pytest -q tests/test_semantic_action_consolidation.py tests/test_sleep_replay_storage.py`).

---

## 2026-03-03 — Реализация Phase 5 EDPC и синхронизация документов

Обновлённые файлы:
- `src/value_layer.py`
- `src/agent.py`
- `src/sleep.py`
- `src/storage.py`
- `tests/test_phase_5_edpc.py`
- `tests/test_value_layer_storage.py`
- `tests/test_sleep_replay_storage.py`
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления реализации:
- В `ValueLayer` добавлен Phase 5 EDPC:
 - память ожидания (`expected_reward_mean/var`, `confirmation_count`, `confidence_score`, `stability_score`)
 - демпфирование альфы избирательной пластичности от уверенности и устойчивости
 - обнаружение шока предсказания с временным усилением пластичности
 - метрики исполнения EDPC (`confidence_distribution`, `stability_distribution`, `shock_frequency`, `effective_alpha_trajectory`)
- Метаданные EDPC встроены в трассы воспроизведения агента и в путь обратной связи:
 - `replay_priority`, `consolidation_weight`, снимки уверенности и устойчивости
 - распространение флага шока и ответ на стресс
- Обновлена логика воспроизведения сна:
 - формула приоритета воспроизведения EDPC с факторами шока и устойчивости
 - метрики цикла по разнообразию, шоку, уверенности и устойчивости воспроизведения
 - органы управления воспроизведением EDPC сохраняются через хранилище
- Добавлены отдельный набор тестов EDPC и покрытие хранилища.

Статус проверки:
- Полный прогон проекта: `504 passed, 3 skipped` (`pytest -q`).
- Целевой прогон EDPC: `5 passed` (`pytest -q tests/test_phase_5_edpc.py`).
- Целевой регрессионный набор воспроизведения, ценности и хранилища: `36 passed, 1 skipped`.

---

## 2026-02-26 — Синхронизация документации дофаминергической TD

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- Документы API ValueLayer синхронизированы с реализованным поведением дофаминергической TD:
 - сырая награда сохраняется (`reward_raw`) с необязательным масштабированием (`reward_scale`)
 - телеметрия онлайн-обрезания (`td_was_clipped`, `td_clip_frequency`, `td_clip_frequency_ema`)
 - органы адаптивного онлайн-обрезания (`adaptive_td_clip_enabled`, адаптация к целевой частоте)
 - усиление провала, связанное со стрессом, и масштабирование альфы, связанное со стрессом
 - пол разморозки связи с исследованием и ограждения режима inhibit в интеграции агента
- Архитектурные заметки обновлены текущей моделью обрезания и адаптации и известными пределами моделирования.
- Руководство по тестированию расширено отдельным покрытием TD Phase 5.x и командами.
- Обновлены счётчики проверки в документах верхнего уровня.

Статус проверки, отражённый в документах:
- Полный прогон проекта: `499 passed, 3 skipped` (`pytest -q`).
- Целевой прогон TD и слоя ценности: `20 passed` (`pytest -q tests/test_dopaminergic_td_layer.py tests/test_value_layer_integration.py tests/test_value_layer_storage.py`).

---

## 2026-02-25 — Синхронизация документации ACC и уточнения поведения

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/CHANGELOG.md`

Основные обновления документации:
- ACC-подобный арбитраж конфликта добавлен в статус проекта верхнего уровня и в навигацию.
- В API задокументированы реализованные контракты ACC:
 - метрики и выходы арбитража
 - жёсткие ограничения (гистерезис, рефрактерный период, стоимость управления)
 - правило косвенного действия (ACC модулирует только управление)
- Задокументированы ограничения взаимодействия ACC и CER:
 - усиление скорости обучения привязано к `error_likelihood`
 - путь `inhibit` работает через модуляцию порога (прямого подавления вектора давлений нет)
 - `control_demand` включает латентность решения
 - предел совместного сдвига порога CER и ACC, чтобы избежать резонанса избыточного подавления
- Руководство по тестированию расширено отдельным покрытием ACC и командами.
- Обновлены счётчики проверки в документах проекта.

Статус проверки, отражённый в документах:
- Полный прогон проекта: `485 passed, 3 skipped` (`pytest -q`).
- Целевой прогон ACC: `15 passed` (`pytest -q tests/test_conflict_arbitration_layer.py tests/test_conflict_arbitration_integration.py tests/test_conflict_arbitration_storage.py`).
- Целевой прогон CER, BG и ACC: `34 passed` (`pytest -q tests/test_emotional_regulation.py tests/test_emotional_regulation_integration.py tests/test_basal_ganglia_integration_spec.py tests/test_conflict_arbitration_layer.py tests/test_conflict_arbitration_integration.py tests/test_conflict_arbitration_storage.py`).

---

## 2026-02-25 — Синхронизация документации CER и BG

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_continuous_emotional_regulation.md`
- `Docs/spec_basal_ganglia_integration.md`

Основные обновления документации:
- Документы проекта синхронизированы с реализованным поведением CER:
 - нелинейная динамика CER с эффектами насыщения и порога
 - модуляция `habit_gain_scale` для пути привычки
 - ограниченное управление нейромодуляторами в диапазоне `[-0.006, +0.006]`
- Спецификация интеграции BG обновлена входами процесса, связанными с CER:
 - `exploration_bias`, `decision_threshold_shift`, `habit_gain_scale`
 - предел бонуса неопределённости и предел огибающей Go
- Справочник API обновлён текущими контрактами CER и BG.
- Руководство по тестированию обновлено регрессионным покрытием CER и командами.
- Обновлены счётчики проверки в документах верхнего уровня.

Статус проверки, отражённый в документах:
- Полный прогон проекта: `470 passed, 3 skipped` (`pytest -q`).
- Целевой прогон CER и BG: `19 passed` (`pytest -q tests/test_emotional_regulation.py tests/test_emotional_regulation_integration.py tests/test_basal_ganglia_integration_spec.py`).

---

## 2026-02-22 — Синхронизация документов слоя внешнего взаимодействия

Обновлённые файлы:
- `README.md`
- `Docs/INDEX.md`
- `Docs/ARCHITECTURE_UPDATED.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_external_interaction_layer.md`

Основные обновления документации:
- Устаревший текст спецификации внешнего слоя заменён реализованным поведением:
 - нелинейная динамика побуждений (`decay + saturation + competition`)
 - обновления логитов стратегий (`weight decay + softmax/temperature`)
 - явная связь побуждения, стратегии и политики
 - расширенный байесовский пересчёт гипотез (`P(E|¬H)`, необязательно `P(E)`)
- Добавлены контракты уровня API для новых внешних методов агента и конвейера планировщика.
- Добавлен архитектурный раздел, документирующий путь исполнения:
 `feedback -> learning hooks -> strategy weights -> selector pressure -> BG gate`.
- Добавлен контракт внешней панели GUI с русскими подписями.
- Добавлена отдельная тестовая документация для `tests/test_external_interaction_layer.py`.

Статус проверки, отражённый в документах:
- Полный прогон проекта: `448 passed, 3 skipped` (`pytest -q`).
- Целевой прогон внешнего взаимодействия: `15 passed` (`pytest -q tests/test_external_interaction_layer.py`).

---
## 2026-02-21 — Синхронизация документации исправлений поведения BG и автономности

Обновлённые файлы:
- `README.md`
- `Docs/API.md`
- `Docs/TESTING.md`
- `Docs/spec_basal_ganglia_integration.md`
- `Docs/PHASE_3_GUIDE.md`

Основные обновления документации:
- Формализована биологическая модуляция в одной точке: давление селектора только когнитивное, BG применяет эффекты аффекта, угрозы, усталости и нейромодуляторов.
- Задокументирована исправленная семантика бодрствования и усталости через когнитивную надёжность (путь `1 - wakefulness`).
- Задокументирован контракт `NO_ACTION` (случайного отката после торможения таламического вентиля нет).
- Задокументировано соответствие внутренней симуляции живому конвейеру (`compute_pressures -> BG.process -> ThalamicGate.select`).
- Задокументированы трассы внутренней мысли автономного GUI (`[AUTO] think: ...`) на тактах внутреннего цикла.

Статус проверки, отражённый в документах:
- Полный прогон проекта: `433 passed, 3 skipped` (`pytest -q`).

---

## 2026-02-20 — Ужесточение аудита спецификации автономного организма v1 и интерфейс ошибок GUI

Обновлённые файлы:
- `src/autonomous_organism.py`
- `src/agent.py`
- `src/gui.py`
- `src/storage.py`
- `tests/test_autonomous_organism.py`
- `tests/test_agent_lifetime_save_load.py`

Основные изменения:
- Введены явные режимы физиологии на каждый автономный такт:
 `idle`, `passive`, `internal_processing`, `speaking`, `low_energy`.
- Постоянная полная когнитивная нагрузка заменена динамической нагрузкой, ведомой режимом.
- Добавлены санация `dt` и журналирование аномалий (`dt_anomaly`) с ограниченным `dt` исполнения.
- Путь обновления энергии и усталости унифицирован, чтобы исключить двойной и тройной расход энергии.
- Добавлен разряд социального побуждения после речевых событий.
- Добавлено явное журналирование отказов применения внутреннего аффекта (`internal_affect_apply_failed`).
- Расширена диагностика такта:
 `physiology_mode`, `cognitive_load`, `load_components`, `energy_update`, `dt_input`, `dt_clamped`.
- Индикатор автономных ошибок GUI теперь считает только критические ошибки и доступен для нажатия:
 нажатие `ошибки:N` открывает окно подробностей с записями критических ошибок.
- Совместимость сохранения и загрузки проверена для состояния автономности и бодрствования.

Проверка:
- Добавлены и обновлены автономные тесты в:
 - `tests/test_autonomous_organism.py`
 - `tests/test_agent_lifetime_save_load.py`
- Полный прогон тестов проекта после изменения: `419 passed, 3 skipped`.

---


## 2026-02-19 — Стабилизация аффективного ядра

Обновлённые файлы:
- `src/affective_space.py`
- `src/storage.py`
- `tests/test_affective_core_phase4.py`
- `tests/test_affective_space_storage.py`

Основные изменения:
- Унаследованная аддитивная динамика (`compat_delta`) теперь включается явно через `legacy_compat_weight`.
- `AffectiveSpace` остаётся каноническим источником истины; унаследованное аффективное состояние есть только проекция.
- Динамический предел нормы обновлён поведением против залипания:
 - рост с учётом запаса вблизи `norm_cap_max`
 - медленное глобальное отпускание через `norm_cap_global_release_rate`
- Базовая линия адаптивна во время исполнения через `baseline_adapt_rate`.
- Сохранение и загрузка обновлены для новых полей аффективного пространства.

Проверка:
- Добавлены тесты допуска унаследованной совместимости, глобального отпускания предела нормы и динамического дрейфа базовой линии.
- Полный прогон тестов проекта после изменения: `403 passed, 3 skipped`.

---

## Февраль 2026 — Phase 6.2/6.2.1 Filtered Consolidation

### Реализована селективная консолидация эпизодов во сне 

**Изменённые файлы:** `src/sleep.py`, `src/agent.py`, `src/storage.py`, `tests/test_phase_6_2_filtered_consolidation.py`, `tests/test_sleep_replay_td_bg.py`

**Ключевые изменения:**
- Добавлены строгие критерии допуска эпизодов к replay-консолидации:
 - `|TD_mean| >= td_threshold`
 - `TD_variance <= td_variance_cap`
 - `salience >= salience_threshold`
 - `reinforcement_count >= min_reinforcement_for_consolidation`
 - `value_variance_ratio < variance_gate_threshold`
 - `ACh_effective >= ach_min_for_consolidation`
 - `stability_flag == True`
- Добавлен `consolidation_score` с ограничением `consolidation_cap`.
- Sleep-обновления переведены на формулу `delta_value = sleep_alpha * consolidation_score * sign(TD_mean)` с ограничениями:
 - `sleep_alpha_cap`
 - `per_update_cap`
 - `max_l2_update_per_cycle`
 - `global_sleep_update_budget`
- Включён обязательный variance gate (`variance_ratio >= 1.0` блокирует replay в цикле сна).
- Добавлена расширенная диагностика сна:
 - `total_episodes_examined`
 - `total_episodes_consolidated`
 - `rejected_due_to_*`
 - `mean_consolidation_score`
 - `sleep_update_l2_total`
 - `variance_ratio`
 - `consolidation_ratio`

### Архитектурные уточнения TD статистики (вариант A) 

- Введена история TD на эпизод (`td_history_snapshot`) и расчёт:
 - `td_mean_snapshot`
 - `td_variance_snapshot`
- История TD обновляется только в бодрствовании/feedback (в `Agent`).
- Во сне replay **не изменяет TD-статистику эпизода**; sleep влияет только на `ValueLayer`/BG обновления.
- Для детерминизма `value_variance` замораживается в начале sleep-цикла и используется во всех этапах цикла.

### Сохранение и загрузка

- `AgentStorage` сохраняет и восстанавливает параметры filtered consolidation:
 - пороги фильтра (`td_threshold`, `td_variance_cap`, `salience_threshold`, `variance_gate_threshold`, `ach_min_for_consolidation`, `stability_index_threshold`)
 - веса score (`w_td`, `w_salience`, `w_importance`, `w_ach`, `w_encoding`)
 - пределы и бюджеты (`sleep_alpha_cap`, `per_update_cap`, `max_l2_update_per_cycle`, `global_sleep_update_budget`)

### Тесты

- Добавлены тесты фазы 6.2:
 - `tests/test_phase_6_2_filtered_consolidation.py`
- Обновлены replay regression тесты:
 - `tests/test_sleep_replay_td_bg.py`
- Дополнительно покрыты:
 - корректный расчёт TD history mean/variance
 - работа `td_variance_cap`
 - заморозка variance в одном sleep цикле
 - гарантия, что sleep replay не мутирует TD history

**Актуальный статус по проекту:** **403 passed, 3 skipped**  
**Длительный стресс (5000 циклов, по включению):** **1 passed**

---

## Февраль 2026 — Phase 5.A.2 Online/Sleep Plasticity Harmonization

### Гармонизирована пластичность бодрствования и сна 

**Изменённые файлы:** `src/value_layer.py`, `src/sleep.py`, `src/agent.py`, `src/storage.py`

**Ключевые изменения:**
- `ValueLayer.update(...)` получил флаг режима `mode`: `online` / `sleep`
- разделены счётчики обновлений:
 - `online_update_count`
 - `sleep_update_count`
- разделены learning rate defaults:
 - `alpha_online_default`
 - `alpha_sleep_default`
- добавлен `td_clip_online` для ограничения online TD amplitude
- в replay сна добавлены:
 - stability-модуляция sleep alpha (`clamp(stability, 0.3..1.0)`)
 - затухание температуры воспроизведения (`effective_priority = priority * temperature`)
 - sleep dopamine scaling (ослабленный DA сдвиг через `apply_dopamine_delta`)
 - расширенный summary (`total_value_delta_sleep`, `total_bg_delta_sleep`, `sleep_update_count`, `replay_blocked`)
 - немедленная остановка replay при достижении `value_total_cap`

**Диагностика:**
- `Agent.get_state()` / `Agent.snapshot()` теперь возвращают:
 - `value_drift_ratio = sleep_update_count / (online_update_count + 1)`
 - `value_drift_warning` при `value_drift_ratio > 3.0`

**Сохранение и загрузка:**
- сохранение и восстановление новых параметров ValueLayer/SleepManager добавлены в `AgentStorage`.

**Тесты:**
- добавлены/обновлены:
 - `tests/test_value_layer.py`
 - `tests/test_value_layer_integration.py`
 - `tests/test_value_layer_storage.py`
 - `tests/test_sleep_replay_td_bg.py`
 - `tests/test_sleep_replay_storage.py`
- общий статус проекта после изменений: **369/369 PASS**

---

## Февраль 2026 — Phase 5.0/5.0.1 Value Layer & TD Error

### Добавлен слой ценности состояний (Value Layer) 

**Новый файл:** `src/value_layer.py`

**Ключевые изменения:**
- реализовано TD-обучение: `δ = r + γV(s_next) - V(s)`
- детерминированный `StateEncoder` (нормализация + стабильный hash)
- табличное `V(s)` с LRU-удалением (`max_states=50_000`)
- ограничения устойчивости:
 - clamp для `δ` и `V(s)`
 - ограничение величины апдейта
 - не более одного update за тик
- дофамин в `Agent.step()` теперь кодирует TD error:
 - reward-driven DA отключён в агентном пайплайне
 - применяется additive `dopamine_delta = clamp(δ * k, -0.1, 0.1)`

**Интеграция:**
- `Agent.step()` обновляет `value_layer` и применяет TD-сдвиг дофамина
- `Agent.get_state()` возвращает `value_layer`
- `storage.save_agent()/load_agent()` сохраняют и восстанавливают `value_layer`
- GUI показывает блок Value Layer в правой панели и инспекторе

**Тесты:**
- `tests/test_value_layer.py`
- `tests/test_value_layer_integration.py`
- `tests/test_value_layer_storage.py`

### Обновлена чувствительность reward/punishment в Affective Space derive logic 

**Файл:** `src/agent.py` (`_derive_affective_space_inputs`)

**Изменения:**
- устранена асимметрия: vulnerability влияет и на `pleasure`, и на `pain`
- введён нелинейный отклик с насыщением (saturating gain)
- добавлена модуляция чувствительности через `arousal`

**Тесты:**
- обновлён `tests/test_affective_space_integration.py`

---

## Февраль 2026 — Phase 4.5 Stability Monitoring & Drift Control

### Добавлен диагностический слой Phase 4.5 

**Новый файл:** `src/stability_monitoring.py`

**Ключевые изменения:**
- read-only мониторинг устойчивости без write side-effects
- анализ в скользящем окне `500..2000` тиков
- флаги drift:
 - `regulation_overuse`
 - `background_drift`
 - `neuromodulator_drift`
 - `dominant_emotion_lock`
 - `outlook_bias`
- гистерезис (минимум 2 окна подряд) для drift-флагов
- калибровка `baseline_background` по warm-up медиане (не первый тик)
- стабильность: `stability_index = 1.0 - weighted_sum(flags)` с clamp `[0..1]`
- рекомендации:
 - `inspect_regulation`
 - `inspect_neuromodulators`
 - `inspect_background`
 - `inspect_expectations`
 - `inspect_memory`
 - `none`

**Интеграция:**
- `Agent.step()` обновляет слой после Phase 4.4
- `Agent.get_state()` возвращает `stability_monitor`
- `storage.save_agent()/load_agent()` сохраняют и восстанавливают `emotional_stability`
- GUI показывает блок мониторинга в правой панели и в инспекторе

**Тесты:**
- `tests/test_stability_monitoring.py`
- `tests/test_stability_monitoring_storage.py`
- `tests/test_stability_monitoring_integration.py`

---

## Февраль 2026 — Phase 4.4 Regulation (Emotional Expectations)

### Добавлен регуляторный слой Phase 4.4 

**Новый файл:** `src/emotional_regulation.py`

**Ключевые изменения:**
- активация по прогнозу (prob≥0.8, conf≥0.6, risk=True, outlook=escalating)
- режимы stabilizing / dampening / containment
- ограничения коррекций: |delta| ≤ 0.1, L2-норма ≤ 0.15
- корректируются только background-параметры и серотонин (DA/NE/CORT не меняются)

**Интеграция:**
- `Agent.step()` вызывает регуляцию после ожиданий
- `storage.save_agent()/load_agent()` сохраняют и восстанавливают слой
- GUI показывает режим и последние дельты

**Тесты:**
- `tests/test_emotional_regulation.py`
- `tests/test_emotional_regulation_storage.py`

---

## Февраль 2026 — Phase 4.3 Emotional Expectations

### Добавлен прогнозный слой эмоциональных ожиданий 

**Новый файл:** `src/emotional_expectations.py`

**Ключевые изменения:**
- тренды эмоций (increasing/stable/decreasing) по ранним/поздним эпизодам
- вероятности и уверенность в диапазоне [0..1]
- риск повторения навязчивых паттернов (obsessive + inertia)
- глобальный прогноз: stabilizing / volatile / escalating

**Интеграция:**
- `Agent.step()` обновляет ожидания после emotional memory
- `storage.save_agent()/load_agent()` сохраняют и восстанавливают ожидания
- GUI (правая панель) показывает краткую сводку и метрики ожиданий

**Тесты:**
- `tests/test_emotional_expectations.py`
- `tests/test_emotional_expectations_storage.py`

---

## Февраль 2026 — Phase 4.2 Emotional Memory & Narratives

### Добавлен блок эмоциональной памяти и ретроспективных нарративов 

**Новый файл:** `src/emotional_memory_narratives.py`

**Ключевые изменения:**
- формируются эмоциональные эпизоды и паттерны на основе semantic emotions
- введено взвешивание по давности (recency weighting)
- паттерны и traits не строятся при малом числе эпизодов (min_total_episodes)
- добавлена фраза смены доминанты: «Ранее преобладала X, сейчас чаще возникает Y»
- используются данные `agent_lifetime` в нарративе

**Интеграция:**
- `Agent.step()` обновляет emotional memory после semantic emotions
- `storage.save_agent()/load_agent()` сохраняют и восстанавливают эмоциональную память
- GUI (правая панель) показывает сводку и метрики

**Тесты:**
- `tests/test_emotional_memory_narratives.py`
- `tests/test_emotional_memory_narratives_integration.py`
- `tests/test_emotional_memory_narratives_storage.py`

---

## Февраль 2026 — Phase 4 (pre) Affective Space

### Контекстная связь reward → pain 

**Изменение:**
- `pain` теперь зависит от уязвимости (vulnerability), а не только от негативного reward.

**Формула:**
```
pain = clamp(
    max(0.0, -reward) * intensity * (0.5 + 0.5 * vulnerability)
)
```

**Эффект:**
- высокая уязвимость усиливает боль,
- устойчивость снижает прямую связь негативного reward и боли.

**Файлы:**
- `src/agent.py` (mapping в `_derive_affective_space_inputs`)
- `tests/test_affective_space_integration.py` (новый тест)
- `Docs/Phase_4_Affective_Space_Spec.md` (примечание реализации)

---

## Февраль 2026 — Phase 3.75 Affective Background Field

### Добавлен инерционный аффективный фон с модуляцией lifetime 

**Новый файл:** `src/affective_background.py`

**Класс `AffectiveBackgroundField`:**
- формирует фоновые компоненты из устойчивых affective traces
- динамика зависит от `lifetime_progress` (инерция, затухание, конкуренция)
- бодрствование влияет только на шум обновления
- **НЕ влияет на selector и мотивацию**

**Интеграция:**
- `Agent.step()` обновляет фон после `AffectivePersistenceLayer`
- `storage.save_agent()/load_agent()` сохраняют и восстанавливают фон
- GUI отображает фоновые компоненты (anxiety/tension/satisfaction/interest)

**Тесты:**
- `tests/test_affective_background_field.py`

---

## Февраль 2026 — Phase 3.5 Affective Persistence

### Добавлен слой устойчивых аффективных следов 

**Новый файл:** `src/affective_persistence.py`

**Класс `AffectivePersistenceLayer`**:
- хранит аффективные traces (anxiety, tension, satisfaction, interest)
- накапливает следы при повторяющихся affect-сигналах
- медленно затухает (decay_rate 0.01–0.05)
- использует neuromodulators как факторы удержания
- читает T1/T2 для baseline-отклонений
- **НЕ влияет на selector напрямую**

**Интеграция:**
- `Agent.step()` обновляет traces каждый шаг
- `storage.save_agent()/load_agent()` сохраняют/восстанавливают traces
- GUI сохраняет/загружает traces вместе с состоянием агента

**Тесты:**
- `tests/test_affective_persistence.py` (Persistence/Decay/Accumulation/No Action Influence)

### Сохранение времени жизни агента 

**Хранилище:**
- сохраняются `created_ts` и `_simulated_sleep_seconds`
- восстанавливаются при загрузке (если передан `agent`)

**Тесты:**
- `tests/test_agent_lifetime_save_load.py`

---

## Февраль 2026 — Нейромодуляторы

### Добавлена система нейромодуляторов 

**Новый файл:** `src/neuromodulators.py`

**Класс `NeuromodulatorState`** реализует четыре глобальные регуляторные сигналы:

| Нейромодулятор | Функция | Влияние |
|---|---|---|
| **DA** (Dopamine) | Подкрепление/ценность | Усиление паттернов во время сна |
| **NE** (Norepinephrine) | Мобилизация/новизна | Формирование дополнительных цепочек |
| **5-HT** (Serotonin) | Стабильность | Стабилизация опытов |
| **CORT** (Cortisol) | Стресс | Агрессивное забывание |

**Методы:**
```python
# Инициализация
nm = NeuromodulatorState()

# Обновление от сигналов
nm.update_from_signals(reward=0.5, novelty=0.2, conflict=0.1)

# Спад во времени
nm.decay_over_time(elapsed=10.0)

# Сериализация
nm.to_dict()
NeuromodulatorState.from_dict(data)
```

**Интеграция:**
- Agent инициализирует `NeuromodulatorState` при создании
- `step()` обновляет нейромодуляторы от сигналов (reward, novelty, conflict)
- `sleep()` применяет эффекты во время консолидации:
 - DA усиливает кортикальные паттерны
 - NE способствует формированию цепочек
 - 5-HT стабилизирует опыты
 - CORT удаляет нестабильные трассы
- `storage.save_agent()/load_agent()` сохраняют/восстанавливают нейромодуляторы
- GUI отображает диагностический блок DA/NE/5-HT/CORT

**Тесты:** 4 новых теста в `tests/test_neuromodulators.py` 

---

## Что было добавлено ранее?

### 1. **Автоматическая тренировка селектора** 

**Новый файл:** `src/trainer.py`

**Класс `SelectorTrainer`** позволяет:
- Автоматически обучать селектор на датасете
- Вычислять accuracy (точность) перед и после тренировки
- Показывать детальные результаты каждого опыта
- Поддерживать настраиваемый learning rate

**Методы:**
```python
trainer = SelectorTrainer(selector, hippocampus, cortex)

# Один эпох на всех опытах
stats = trainer.train_epoch(experiences, learning_rate=1.0)

# Несколько эпох
history = trainer.train_full(experiences, epochs=5, learning_rate=0.5)

# Получить accuracy без обновления весов
accuracy = trainer.get_accuracy(experiences)

# Детальные результаты
results = trainer.get_detailed_results(experiences)
```

### 2. **GUI функционал** 

**Новая кнопка "Авто-тренировка"** в интерфейсе

**Открывает окно с:**
- Настройками (количество эпох, learning rate)
- Отображением accuracy ДО и ПОСЛЕ
- Процентом улучшения
- Историей по эпохам
- Детальными результатами для каждого опыта

### 3. **Полное покрытие тестами** 

**Новый файл:** `tests/test_trainer.py` (7 тестов)

**Всего тестов:** 23
- test_selector.py: 5 тестов
- test_hippocampus.py: 6 тестов
- test_agent.py: 5 тестов
- test_trainer.py: 7 тестов

**Все тесты пройдены:** 23/23

### 4. **Исправления логики** 

**В selector.py:**
- Добавлена проверка `if a in scores` - селектор не крашится на неизвестные действия
- Добавлена фильтрация отрицательных опытов - система предпочитает положительный опыт
- Увеличены веса влияния: 0.1→0.5 для опытов, 0.05→0.2 для паттернов

### 5. **Примеры использования** 

**Новый файл:** `examples_training.py`

**4 примера:**
1. Базовая тренировка на датасете
2. Детальный анализ результатов
3. Сравнение разных learning rates
4. Интеграция с агентом

### 6. **Документация** 

**Обновлены файлы:**
- `LEARNING.md` - полное объяснение архитектуры и использования
- Добавлено описание автоматической тренировки
- Добавлены примеры использования

## Как использовать новую функциональность?

### Вариант 1: GUI (рекомендуется)

```
1. Запустить gui.py
2. Нажать "Загрузить датасет"
3. Нажать "Авто-тренировка"
4. Установить параметры:
   - Количество эпох: 5-10
   - Learning rate: 0.5
5. Нажать "▶️ Начать тренировку"
6. Смотреть результаты!
```

### Вариант 2: Код

```python
from trainer import SelectorTrainer
from loader import load_experiences_from_datasets_folder

# Загружаем опыты
experiences = load_experiences_from_datasets_folder()

# Создаем тренер
trainer = SelectorTrainer(selector, hippocampus, cortex)

# Тренируем
history = trainer.train_full(experiences, epochs=5, learning_rate=0.5)

# Проверяем результаты
accuracy = trainer.get_accuracy(experiences)
print(f"Accuracy: {accuracy:.2%}")
```

### Вариант 3: Примеры

```bash
python examples_training.py
```

## Почему это работает?

### Принцип supervised learning (обучение с учителем)

```
Датасет содержит правильные ответы:
  context="кто ты" → action="ответить_кто_я"

Тренировка:
  1. Берем контекст "кто ты"
  2. Селектор выбирает действие
  3. Если совпадает с правильным → reward=+1.0
  4. Если не совпадает → reward=-1.0
  5. Обновляем вес действия на: weight += learning_rate * reward

Результат:
  - Правильные действия получают выше веса
  - Неправильные действия получают ниже веса
  - Accuracy растет с каждым эпохом
```

## Статистика

**Размер кода:**
- trainer.py: ~150 строк
- GUI изменения: ~200 строк
- Тесты: ~130 строк
- Документация: обновлена

**Производительность:**
- Тренировка на 3+ опытах: <1 секунда
- Тестирование accuracy: <0.1 секунды

**Качество:**
- Все 23 теста пройдены 
- Код протестирован и задокументирован
- GUI интуитивный и информативный

## Что можно улучшить дальше?

1. **Батч-обработка**: Обрабатывать несколько опытов за раз
2. **Валидация**: Разделить датасет на train/val для проверки переобучения
3. **Графики**: Добавить визуализацию accuracy по эпохам
4. **Сохранение результатов**: Сохранять историю тренировки в файл
5. **Адаптивный learning rate**: Менять learning rate во время обучения

## Файлы, измененные или созданные

### Новые файлы:
- `src/trainer.py` - класс для тренировки
- `tests/test_trainer.py` - тесты тренера
- `examples_training.py` - примеры использования

### Измененные файлы:
- `src/gui.py` - добавлена кнопка и окно для авто-тренировки
- `src/selector.py` - исправлена логика выбора действий
- `src/loader.py` - добавлены префиксы для контекста и действия
- `LEARNING.md` - обновлена документация

### Документация:
- `LEARNING.md` - полное руководство использования

---

**Дата:** January 12, 2026  
**Статус:** Полностью завершено и протестировано

