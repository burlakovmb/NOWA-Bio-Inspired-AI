# Документация проекта NOWA-Cognitive

English version: [00_INDEX.en.md](00_INDEX.en.md)

**Статус (27 сентября 2026 г.).** Указатель устарел. Порядок чтения: [INDEX.ru.md](INDEX.ru.md) и [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md).

**Версия:** 3.3  
**Последнее обновление:** 23 марта 2026  
**Статус:** готов к эксплуатации (Phase 5 EDPC + Phase 6 интегрированы + замена семантического сходства)

---

## Структура документации

### Начало работы
- **[START_HERE.md](START_HERE.ru.md)** — начинать чтение отсюда, если проект незнаком
- **[QUICK_START_RU.md](QUICK_START_RU.ru.md)** — краткое руководство по запуску (русский)
- **[INSTALLATION.ru.md](INSTALLATION.ru.md)** — установка и настройка

### Архитектура и проект
- **[ARCHITECTURE.md](ARCHITECTURE.ru.md)** — общая архитектура системы
- **[ARCHITECTURE_UPDATED.md](ARCHITECTURE_UPDATED.ru.md)** — текущая карта архитектуры (EDPC + Phase 6)
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.ru.md)** — структура каталогов проекта
- **[EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.ru.md)** — обзор системы верхнего уровня
- **[Phase_4_Affective_Space_Spec.md](Phase_4_Affective_Space_Spec.ru.md)** — спецификация аффективного пространства Phase 4 (предварительная)

### Основные компоненты

#### Phase 1: основание
- Аффективная система (AffectiveState)
- Система нейромедиаторов (NeuromodulatorState)
- Базовая генерация действий

#### Phase 2: расширенные возможности
- **[README_AFFECTIVE_SYSTEM.md](README_AFFECTIVE_SYSTEM.ru.md)** — аффективная регуляция
- **[Phase2_Wakefulness_PFC_Extension.md](Phase2_Wakefulness_PFC_Extension.ru.md)** — бодрствование и PFC
- **[spec_circadian_process_c.md](spec_circadian_process_c.ru.md)** — циркадный процесс C для модели бодрствования
- **[NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.ru.md)** — справочник по нейромедиаторам

#### Phase 3: базальные ганглии (новое — февраль 2026)
- **[Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.ru.md)** — спецификация BG
- **[REFACTORING_REPORT.md](../REFACTORING_REPORT.md)** — полный отчёт о рефакторинге
- **[REFACTORING_SUMMARY.py](../REFACTORING_SUMMARY.py)** — краткая сводка (исполняемая)

#### Phase 4 (предварительная): аффективное пространство (новое — февраль 2026)
- **[Phase_4_Affective_Space_Spec.md](Phase_4_Affective_Space_Spec.ru.md)** — формальная спецификация

#### Phase 5: EDPC (новое — март 2026)
- **[spec_phase5_edpc.md](spec_phase5_edpc.ru.md)** — спецификация Experience-Driven Predictive Consolidation
- **[Phase_5_0_1_Value_Layer_RU_Spec.md](Phase_5_0_1_Value_Layer_RU_Spec.ru.md)** — базовая линия слоя ценности
- **[spec_semantic_similarity_replacement.md](spec_semantic_similarity_replacement.ru.md)** — детерминированное семантическое хеширование для сходства состояний
- **[Phase_5_A_1_BG_Sleep_Replay_RU_Spec.md](Phase_5_A_1_BG_Sleep_Replay_RU_Spec.ru.md)** — базовая линия воспроизведения во сне

### Тестирование и разработка
- **[TESTING.ru.md](TESTING.ru.md)** — руководство по тестированию
- **[DEVELOPMENT.md](DEVELOPMENT.ru.md)** — руководство по разработке
- **[CHANGELOG.md](CHANGELOG.ru.md)** — журнал изменений проекта

### Справочник API
- **[API.md](API.ru.md)** — полная документация API

### Отчёты и статус
- **[PROJECT_STATUS_FINAL.ru.md](PROJECT_STATUS_FINAL.ru.md)** — текущий статус проекта
- **[PROJECT_STATISTICS.md](PROJECT_STATISTICS.ru.md)** — метрики и статистика проекта
- **[PROJECT_PROGRESS.md](PROJECT_PROGRESS.ru.md)** — ход разработки

---

## Быстрая навигация по роли

### Для новых разработчиков
1. Прочитать [START_HERE.md](START_HERE.ru.md)
2. Изучить [ARCHITECTURE.md](ARCHITECTURE.ru.md)
3. Следовать [INSTALLATION.ru.md](INSTALLATION.ru.md)
4. Открыть [QUICK_START_RU.md](QUICK_START_RU.ru.md)
5. Осмотреть [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.ru.md)

### Для системных архитекторов
1. Изучить [ARCHITECTURE.md](ARCHITECTURE.ru.md)
2. Прочитать [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.ru.md)
3. Открыть [Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.ru.md)
4. Изучить [API.md](API.ru.md)

### Для контроля качества и тестировщиков
1. Прочитать [TESTING.ru.md](TESTING.ru.md)
2. Изучить [PROJECT_STATISTICS.md](PROJECT_STATISTICS.ru.md)
3. Открыть [FULL_PROJECT_TEST_REPORT.md](FULL_PROJECT_TEST_REPORT.ru.md)

### Для эксплуатации и развёртывания
1. Прочитать [INSTALLATION.ru.md](INSTALLATION.ru.md)
2. Изучить [PROJECT_STATUS_FINAL.ru.md](PROJECT_STATUS_FINAL.ru.md)
3. Открыть [DEVELOPMENT.md](DEVELOPMENT.ru.md)

---

## Phase 3: базальные ганглии (последнее обновление)

### Что такое Phase 3?
Phase 3 реализует систему **Basal Ganglia Action Gating** — биологически правдоподобный механизм выбора действий, который включает:

- **Конкуренцию Go/NoGo**: действия соревнуются через конкурирующие каналы
- **Модуляцию нейромедиаторами**: дофамин, кортизол, серотонин, норадреналин
- **Совещательную роль PFC**: префронтальная кора может предлагать, но не диктовать
- **Двухуровневая пластичность**: лабильные смещения Q/Go/NoGo днём; стабильные значения, привычки и каналы консолидируются во сне
- **Силу привычки**: выученное поведение влияет на последующий выбор

### Ключевые документы
- [Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.ru.md) — спецификация
- [REFACTORING_REPORT.md](../REFACTORING_REPORT.md) — полный отчёт о реализации
- [FINAL_RESULT.txt](../FINAL_RESULT.txt) — краткая сводка

### Результаты тестов
- **29/29** тестов Phase 3 пройдены
- **584 пройдено, 3 пропущено** — тесты проекта в целом пройдены
- **0** отказов тестов
- **100%** соответствие спецификации

---

## Компоненты системы

### Основные классы
```
src/
├── agent.py                 # Главный класс агента
├── affect.py               # AffectiveState
├── neuromodulators.py      # NeuromodulatorState
├── wakefulness.py          # WakefulnessState
├── basal_ganglia.py        # Phase 3 — система BG
├── affective_space.py      # Phase 4 — каноническое аффективное ядро
├── memory.py               # Системы памяти
├── intent_memory.py        # Память намерений
└── gui.py                  # Визуализация GUI
```

### Набор тестов
```
tests/
├── test_affect.py
├── test_neuromodulators.py
├── test_wakefulness.py
├── test_basal_ganglia.py   # тесты Phase 3 (29 тестов)
├── test_affective_space.py # базовые тесты Phase 4
├── test_phase_5_edpc.py    # тесты Phase 5 EDPC
├── test_agent.py
└── ... (всего 500+ тестов)
```

---

## Быстрый запуск

### Установка
```bash
# Clone repository
git clone https://github.com/burlakovmb/NOWA-Cognitive.git
cd NOWA-Cognitive

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -q
```

### Запуск демонстрации
```bash
python basal_ganglia_demo.py
```

### Использование в коде
```python
from src.agent import Agent

agent = Agent()
agent.register_action_channel("attack", go_weight=0.8, nogo_weight=0.2)
action = agent.choose_action_via_basal_ganglia(pfc_pressure=1.0)
agent.record_action_outcome(action, success=True, dopamine=1.5)
agent.sleep()  # Consolidate learning
```

---

## Статистика проекта

| Показатель | Значение |
|--------|-------|
| **Всего тестов** | 507 (504 пройдено, 3 пропущено) |
| **Доля прохождения** | 100% |
| **Версия Python** | 3.13+ |
| **Основных классов** | 20+ |
| **Завершённых фаз** | 19 |
| **Файлов документации** | 70+ |

---

## Последние изменения (обновление Phase 5 EDPC — 3 марта 2026)

### EDPC интегрирован
- `ValueLayer` теперь ведёт память ожидания для каждого закодированного состояния
  (`expected_reward_mean/var`, `confirmation_count`, `confidence_score`, `stability_score`)
- Избирательная пластичность применяется через эффективное затухание alpha в EDPC
- Обнаруживается шок предсказания и передаётся в сигналы воспроизведения и стресса
- Приоритет воспроизведения во сне включает факторы EDPC (шок и устойчивость ожидания)
- Рабочие метрики включают:
  - распределения уверенности и устойчивости
  - частоту шока
  - индекс разнообразия воспроизведения
  - траекторию эффективной alpha

### Ссылка на спецификацию
См. `Docs/spec_phase5_edpc.md` и обновлённые `Docs/API.md`, `Docs/ARCHITECTURE_UPDATED.md`.

---

## Поддержка и участие

По вопросам, ошибкам и вкладу:
1. Открыть [DEVELOPMENT.md](DEVELOPMENT.ru.md)
2. Изучить [TESTING.ru.md](TESTING.ru.md)
3. См. [CHANGELOG.md](CHANGELOG.ru.md) для сведений о версии

---

## Организация файлов

Вся документация собрана в каталоге `Docs/`:
- документы по архитектуре и проектированию ядра
- руководства по отдельным компонентам
- справочник API
- руководства по тестированию и разработке
- отчёты о статусе и журналы изменений

**Расположение:** `e:\git\NOWA-Cognitive\Docs\`

---

## Рекомендуемый порядок чтения

1. **START_HERE.md** — обзор и введение
2. **QUICK_START_RU.md** — быстрый запуск
3. **ARCHITECTURE.md** — устройство системы
4. **Phase_3_Basal_Ganglia_Action_Gating_refactoring.md** — последняя возможность
5. **API.md** — программный справочник
6. **TESTING.ru.md** — как тестировать
7. **DEVELOPMENT.md** — руководство для участников

---

**Последнее обновление:** 2026-03-03  
**Версия:** 3.3  
**Статус:** готов к эксплуатации (EDPC интегрирован)
